# AirClaim AI

SaaS completo para gestionar reclamaciones de aerolineas con:

- `FastAPI` como backend
- landing y dashboard servidos por el propio backend
- login con `JWT` basico
- OCR documental
- indexacion para RAG
- chat con agente de IA
- soporte para Azure Blob Storage, Azure AI Search, Azure OCR y Azure SQL
- uso de `OpenAI` oficial para el agente, sin Azure OpenAI

## Lo que incluye

- Landing con hero deslizante, stats desde base de datos, servicios, casos de exito y colaboradores
- Auth basica con cuenta demo incluida
- CRUD operativo minimo de incidencias
- Clasificacion inicial por categoria
- Subida documental para OCR e indexacion
- Chat de agente conectado al contexto de la incidencia y la base documental
- Fallback local para poder arrancar en desarrollo aunque falten servicios cloud

## Arquitectura

### Tablas

- `users`
- `incidents`
- `chat_messages`
- `classified_incident_logs`
- `knowledge_documents`

### Servicios

- `StorageService`: Azure Blob o almacenamiento local
- `OCRService`: Azure OCR o fallback local
- `SearchService`: Azure AI Search o recuperacion local por keywords
- `ClaimAgentService`: OpenAI oficial o respuesta fallback

## Arranque rapido

1. Crea un entorno y instala dependencias:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copia `.env.example` a `.env` y completa variables.

3. Inicia la app:

```powershell
uvicorn app.main:app --reload
```

4. Abre:

- [http://127.0.0.1:8000](http://127.0.0.1:8000)
- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Cuenta demo

- Email: `demo@airclaim.ai`
- Password: `demo1234`

## Variables importantes

### OpenAI oficial

Aunque compartiste credenciales de Azure OpenAI, la aplicacion esta preparada para `OPENAI_API_KEY` del API oficial porque pediste no usar Azure OpenAI.

### Azure AI Search

Hace falta el `AZURE_SEARCH_ENDPOINT` del servicio para activar la indexacion cloud. En esta entrega el sistema funciona con fallback local si ese dato no se define.

### Azure SQL

Para usar SQL Server/Azure SQL:

```env
DATABASE_BACKEND=sqlserver
SQLSERVER_CONNECTION_STRING=Driver={ODBC Driver 18 for SQL Server};Server=...
```

Si no, el entorno de desarrollo usa `SQLite` local y deja todo funcionando.

## Endpoints principales

- `GET /api/stats`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/incidents`
- `POST /api/incidents`
- `GET /api/incidents/{incident_id}`
- `GET /api/incidents/{incident_id}/messages`
- `POST /api/incidents/{incident_id}/messages`
- `GET /api/knowledge/documents`
- `POST /api/knowledge/upload`

## Nota de seguridad

No he incrustado secretos reales en el codigo. Lo correcto es ponerlos en `.env` local y rotar las claves que se hayan compartido fuera de un canal seguro.



