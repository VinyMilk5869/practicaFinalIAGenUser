from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import UPLOAD_DIR, settings
from .database import db

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore

try:
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SearchableField,
        SimpleField,
    )
    from azure.storage.blob import BlobServiceClient
    from azure.ai.documentintelligence import DocumentIntelligenceClient
except ImportError:  # pragma: no cover
    AzureKeyCredential = None  # type: ignore
    SearchClient = None  # type: ignore
    SearchIndexClient = None  # type: ignore
    SearchField = None  # type: ignore
    SearchFieldDataType = None  # type: ignore
    SearchIndex = None  # type: ignore
    SearchableField = None  # type: ignore
    SimpleField = None  # type: ignore
    BlobServiceClient = None  # type: ignore
    DocumentIntelligenceClient = None  # type: ignore


def classify_incident(summary: str) -> tuple[str, float, str]:
    text = summary.lower()
    if any(token in text for token in ["retraso", "delay", "demora"]):
        return ("EU261_delay", 0.94, "Clasificacion heuristica por retraso prolongado.")
    if any(token in text for token in ["cancel", "cancelado", "cancelacion"]):
        return ("flight_cancellation", 0.91, "Clasificacion heuristica por cancelacion.")
    if any(token in text for token in ["equipaje", "maleta", "baggage"]):
        return ("baggage_issue", 0.93, "Clasificacion heuristica por equipaje.")
    return ("general_claim", 0.74, "Clasificacion generica a revisar por el agente.")


def estimate_compensation(incident: dict[str, Any]) -> float | None:
    category = str(incident.get("category", "")).lower()
    summary = str(incident.get("summary", "")).lower()
    if "delay" in category or "retraso" in category:
        return 250.0
    if "cancellation" in category or "cancel" in category:
        return 400.0
    if "baggage" in category or "equipaje" in category or "maleta" in summary:
        return 420.0
    return None


class StorageService:
    def __init__(self) -> None:
        self.local_dir = UPLOAD_DIR
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.client = None
        self.container_ready = False
        self.azure_required = bool(settings.blob_connection_string)
        if BlobServiceClient and settings.blob_connection_string:
            try:
                self.client = BlobServiceClient.from_connection_string(settings.blob_connection_string)
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo crear el cliente de Azure Blob Storage: {exc}") from exc
        elif self.azure_required:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING requiere azure-storage-blob instalado.")

    def ensure_container(self) -> None:
        if not self.client or self.container_ready:
            return
        container = self.client.get_container_client(settings.blob_container_name)
        if not container.exists():
            container.create_container()
        self.container_ready = True

    def save(self, filename: str, content: bytes) -> str:
        safe_name = f"{uuid4().hex}-{filename}"
        if self.client:
            try:
                self.ensure_container()
                blob_client = self.client.get_blob_client(container=settings.blob_container_name, blob=safe_name)
                blob_client.upload_blob(content, overwrite=True)
                return safe_name
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo guardar el archivo en Azure Blob Storage: {exc}") from exc
        if self.azure_required:
            raise RuntimeError("Azure Blob Storage esta configurado, pero el cliente no esta disponible.")
        destination = self.local_dir / safe_name
        destination.write_bytes(content)
        return f"local/{safe_name}"

    def delete(self, blob_name: str) -> bool:
        if blob_name.startswith("local/"):
            target = self.local_dir / blob_name.removeprefix("local/")
            if target.exists():
                target.unlink()
                return True
            return False

        if self.client:
            try:
                self.ensure_container()
                blob_client = self.client.get_blob_client(container=settings.blob_container_name, blob=blob_name)
                blob_client.delete_blob(delete_snapshots="include")
                return True
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo eliminar el archivo de Azure Blob Storage: {exc}") from exc
        return False

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.blob_connection_string),
            "client_ready": bool(self.client),
            "container": settings.blob_container_name,
            "mode": "azure_blob" if self.client else "local",
        }


class OCRService:
    def __init__(self) -> None:
        self.client = None
        self.azure_required = bool(settings.azure_ocr_endpoint or settings.azure_ocr_key)
        if DocumentIntelligenceClient and settings.azure_ocr_endpoint and settings.azure_ocr_key and AzureKeyCredential:
            try:
                self.client = DocumentIntelligenceClient(
                    endpoint=settings.azure_ocr_endpoint,
                    credential=AzureKeyCredential(settings.azure_ocr_key),
                )
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo crear el cliente de Azure OCR: {exc}") from exc
        elif self.azure_required:
            raise RuntimeError("Azure OCR requiere AZURE_OCR_ENDPOINT, AZURE_OCR_KEY y azure-ai-documentintelligence.")

    def extract_text(self, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".md", ".csv", ".json"}:
            return content.decode("utf-8", errors="ignore")

        if self.client:
            try:
                poller = self.client.begin_analyze_document("prebuilt-read", body=content)
                result = poller.result()
                lines: list[str] = []
                for page in result.pages:
                    for line in page.lines:
                        lines.append(line.content)
                return "\n".join(lines).strip()
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo ejecutar OCR en Azure Document Intelligence: {exc}") from exc

        if self.azure_required:
            raise RuntimeError("Azure OCR esta configurado, pero el cliente no esta disponible.")

        return (
            f"Documento {filename} cargado correctamente. "
            "No se pudo ejecutar OCR remoto en este entorno, asi que el contenido debe validarse manualmente."
        )

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.azure_ocr_endpoint and settings.azure_ocr_key),
            "client_ready": bool(self.client),
            "mode": "azure_document_intelligence" if self.client else "local_text_only",
        }


class SearchService:
    def __init__(self) -> None:
        self.search_client = None
        self.index_client = None
        self.index_checked = False
        self.azure_required = bool(settings.azure_search_endpoint or settings.azure_search_key)
        self.azure_ready = bool(
            SearchClient
            and SearchIndexClient
            and AzureKeyCredential
            and settings.azure_search_endpoint
            and settings.azure_search_key
        )
        if self.azure_ready:
            credential = AzureKeyCredential(settings.azure_search_key)
            try:
                self.index_client = SearchIndexClient(settings.azure_search_endpoint, credential)
                self.search_client = SearchClient(settings.azure_search_endpoint, settings.azure_search_index, credential)
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo crear el cliente de Azure AI Search: {exc}") from exc
        elif self.azure_required:
            raise RuntimeError("Azure AI Search requiere endpoint, key y azure-search-documents.")

    def ensure_index(self) -> None:
        if not self.index_client or self.index_checked:
            return
        existing = [idx.name for idx in self.index_client.list_indexes()]
        if settings.azure_search_index in existing:
            self.index_checked = True
            return
        index = SearchIndex(
            name=settings.azure_search_index,
            fields=[
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="filename", type=SearchFieldDataType.String),
                SearchableField(name="content", type=SearchFieldDataType.String),
                SearchField(name="source_kind", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="is_active", type=SearchFieldDataType.Boolean, filterable=True),
            ],
        )
        self.index_client.create_index(index)
        self.index_checked = True

    def index_document(self, doc_id: int, filename: str, content: str, source_kind: str, is_active: bool = True) -> None:
        if self.search_client:
            try:
                self.ensure_index()
                self.search_client.upload_documents(
                    [
                        {
                            "id": str(doc_id),
                            "filename": filename,
                            "content": content,
                            "source_kind": source_kind,
                            "is_active": is_active,
                        }
                    ]
                )
                return
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo indexar el documento en Azure AI Search: {exc}") from exc
        if self.azure_required:
            raise RuntimeError("Azure AI Search esta configurado, pero el cliente no esta disponible.")

    def delete_document(self, doc_id: int) -> None:
        if self.search_client:
            try:
                self.search_client.delete_documents([{"id": str(doc_id)}])
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo eliminar el documento de Azure AI Search: {exc}") from exc

    def set_document_active(self, doc_id: int, filename: str, content: str, source_kind: str, is_active: bool) -> None:
        self.index_document(doc_id, filename, content, source_kind, is_active=is_active)

    def search(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        if self.search_client:
            try:
                results = self.search_client.search(search_text=query, top=limit, filter="is_active eq true")
                return [
                    {"filename": item["filename"], "content": item["content"], "score": item.get("@search.score", 1)}
                    for item in results
                ]
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(f"No se pudo consultar Azure AI Search: {exc}") from exc

        if self.azure_required:
            raise RuntimeError("Azure AI Search esta configurado, pero el cliente no esta disponible.")

        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        docs = db.fetchall(
            """
            SELECT filename, content_text
            FROM knowledge_documents
            WHERE indexed = 1 AND is_active = 1
            ORDER BY id DESC
            """
        )
        scored: list[dict[str, Any]] = []
        for doc in docs:
            haystack = doc["content_text"].lower()
            score = sum(haystack.count(word) for word in words)
            if score:
                scored.append({"filename": doc["filename"], "content": doc["content_text"], "score": score})
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

    def reindex_active_documents(self) -> dict[str, Any]:
        docs = db.fetchall(
            """
            SELECT id, filename, content_text, source_kind, is_active
            FROM knowledge_documents
            WHERE indexed = 1 AND is_active = 1
            ORDER BY id ASC
            """
        )
        for doc in docs:
            self.index_document(
                int(doc["id"]),
                doc["filename"],
                doc["content_text"],
                doc["source_kind"],
                is_active=bool(doc["is_active"]),
            )
        return {"reindexed": len(docs), "index": settings.azure_search_index}

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.azure_search_endpoint and settings.azure_search_key),
            "client_ready": bool(self.search_client),
            "index": settings.azure_search_index,
            "mode": "azure_ai_search" if self.search_client else "local_keyword_search",
        }


@dataclass(slots=True)
class ChatResult:
    answer: str
    citations: list[dict[str, Any]]
    estimated_compensation: float | None = None


class ClaimAgentService:
    def __init__(self, search_service: SearchService) -> None:
        self.search_service = search_service
        self.client = OpenAI(api_key=settings.openai_api_key) if OpenAI and settings.openai_api_key else None

    def build_context(self, summary: str) -> list[dict[str, Any]]:
        return self.search_service.search(summary, limit=3)

    def answer(self, incident: dict[str, Any], user_message: str) -> ChatResult:
        context_docs = self.build_context(f"{incident['summary']} {user_message}")
        citations = [{"filename": item["filename"], "excerpt": item["content"][:220]} for item in context_docs]
        estimated_compensation = estimate_compensation(incident)

        if self.client:
            try:
                prompt = self._prompt(incident, user_message, context_docs, estimated_compensation)
                response = self.client.responses.create(
                    model=settings.openai_model,
                    input=prompt,
                    temperature=0.2,
                )
                text = getattr(response, "output_text", "").strip()
                if text:
                    return ChatResult(answer=text, citations=citations, estimated_compensation=estimated_compensation)
            except Exception:  # pragma: no cover
                pass

        return ChatResult(
            answer=self._fallback_answer(incident, user_message, context_docs, estimated_compensation),
            citations=citations,
            estimated_compensation=estimated_compensation,
        )

    @staticmethod
    def _prompt(
        incident: dict[str, Any],
        user_message: str,
        context_docs: list[dict[str, Any]],
        estimated_compensation: float | None,
    ) -> str:
        snippets = "\n\n".join(
            f"Fuente: {item['filename']}\nContenido: {item['content'][:1200]}" for item in context_docs
        )
        return f"""
Eres un agente experto en reclamaciones aereas para consumidores de la UE y LATAM.
Tu tono debe ser claro, profesional, amable y orientado a accion.

Incidente:
- Aerolinea: {incident['airline']}
- Vuelo: {incident['flight_number']}
- Categoria: {incident['category']}
- Estado: {incident['status']}
- Compensacion estimada por reglas del sistema: {f'{estimated_compensation:.0f} EUR' if estimated_compensation else 'pendiente de estimacion'}
- Resumen: {incident['summary']}

Contexto recuperado para RAG:
{snippets or 'Sin contexto documental adicional.'}

Solicitud del usuario:
{user_message}

Responde en espanol con:
1. Diagnostico rapido
2. Proxima accion recomendada
3. Compensacion orientativa si existe base suficiente
4. Borrador o fragmento util para la reclamacion si aplica
5. Lista corta de documentos faltantes
"""

    @staticmethod
    def _fallback_answer(
        incident: dict[str, Any],
        user_message: str,
        context_docs: list[dict[str, Any]],
        estimated_compensation: float | None,
    ) -> str:
        documents = ", ".join(doc["filename"] for doc in context_docs) if context_docs else "sin fuentes externas indexadas"
        compensation_line = (
            f"Compensacion orientativa: {estimated_compensation:.0f} EUR, pendiente de validar con la evidencia del caso.\n\n"
            if estimated_compensation
            else "Compensacion orientativa: pendiente de estimar; necesito mas detalle sobre tiempos, ruta y motivo comunicado por la aerolinea.\n\n"
        )
        return (
            f"Diagnostico rapido: el caso '{incident['category']}' para el vuelo {incident['flight_number']} "
            f"de {incident['airline']} tiene base razonable para reclamacion.\n\n"
            f"{compensation_line}"
            f"Proxima accion recomendada: consolidar tarjeta de embarque, justificante de retraso o incidencia "
            f"y gastos asociados antes de enviar la reclamacion formal.\n\n"
            f"Borrador util: \"Solicito la compensacion y el reembolso de gastos derivados de la incidencia "
            f"descrita en mi vuelo {incident['flight_number']}, conforme a la normativa aplicable y a la "
            f"documentacion aportada.\"\n\n"
            f"Documentos faltantes sugeridos: DNI o pasaporte, reserva, evidencia del incidente, tickets de gastos.\n\n"
            f"Consulta recibida: {user_message}\n"
            f"Fuentes consideradas: {documents}."
        )


storage_service = StorageService()
ocr_service = OCRService()
search_service = SearchService()
claim_agent_service = ClaimAgentService(search_service)


def persist_training_document(filename: str, content: bytes, source_kind: str = "upload") -> dict[str, Any]:
    blob_name = storage_service.save(filename, content)
    extracted_text = ocr_service.extract_text(filename, content)
    doc_id = db.execute(
        """
        INSERT INTO knowledge_documents (filename, blob_name, content_text, source_kind, indexed, is_active, mime_type, file_size, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            blob_name,
            extracted_text,
            source_kind,
            1,
            1,
            _guess_mime_type(filename),
            len(content),
            db.now_iso(),
        ),
    )
    search_service.index_document(doc_id, filename, extracted_text, source_kind, is_active=True)
    return get_knowledge_document(doc_id) or {"id": doc_id, "filename": filename, "blob_name": blob_name, "content_preview": extracted_text[:200]}


def get_knowledge_document(doc_id: int) -> dict[str, Any] | None:
    doc = db.fetchone(
        """
        SELECT id, filename, blob_name, content_text, source_kind, indexed, is_active, mime_type, file_size, created_at
        FROM knowledge_documents WHERE id = ?
        """,
        (doc_id,),
    )
    if not doc:
        return None
    doc["content_preview"] = doc["content_text"][:220]
    return doc


def list_knowledge_documents() -> list[dict[str, Any]]:
    docs = db.fetchall(
        """
        SELECT id, filename, blob_name, content_text, source_kind, indexed, is_active, mime_type, file_size, created_at
        FROM knowledge_documents
        ORDER BY id DESC
        """
    )
    for doc in docs:
        doc["content_preview"] = doc["content_text"][:180]
    return docs


def update_knowledge_document(doc_id: int, *, filename: str | None = None, source_kind: str | None = None, indexed: bool | None = None, is_active: bool | None = None) -> dict[str, Any] | None:
    current = get_knowledge_document(doc_id)
    if not current:
        return None

    next_filename = filename or current["filename"]
    next_source_kind = source_kind or current["source_kind"]
    next_indexed = int(indexed if indexed is not None else bool(current["indexed"]))
    next_is_active = int(is_active if is_active is not None else bool(current["is_active"]))

    db.execute_no_return(
        """
        UPDATE knowledge_documents
        SET filename = ?, source_kind = ?, indexed = ?, is_active = ?
        WHERE id = ?
        """,
        (next_filename, next_source_kind, next_indexed, next_is_active, doc_id),
    )

    if next_indexed:
        search_service.set_document_active(
            doc_id,
            next_filename,
            current["content_text"],
            next_source_kind,
            bool(next_is_active),
        )
    else:
        search_service.delete_document(doc_id)

    return get_knowledge_document(doc_id)


def delete_knowledge_document(doc_id: int) -> bool:
    current = get_knowledge_document(doc_id)
    if not current:
        return False
    storage_service.delete(current["blob_name"])
    search_service.delete_document(doc_id)
    db.execute_no_return("DELETE FROM knowledge_documents WHERE id = ?", (doc_id,))
    return True


def _guess_mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    mapping = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".pdf": "application/pdf",
        ".json": "application/json",
        ".csv": "text/csv",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return mapping.get(suffix, "application/octet-stream")


def append_chat_message(incident_id: int, role: str, content: str, citations: list[dict[str, Any]] | None = None) -> int:
    return db.execute(
        """
        INSERT INTO chat_messages (incident_id, role, content, citations_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (incident_id, role, content, json.dumps(citations or []), db.now_iso()),
    )
