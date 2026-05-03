from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import settings

try:
    import pyodbc  # type: ignore
except ImportError:  # pragma: no cover
    pyodbc = None


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_plain TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    flight_number TEXT NOT NULL,
    airline TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    claim_amount REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS classified_incident_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    notes TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    blob_name TEXT NOT NULL,
    content_text TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    indexed INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    mime_type TEXT,
    file_size INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


SQLSERVER_SCHEMA = """
IF OBJECT_ID('users', 'U') IS NULL
CREATE TABLE users (
    id INT IDENTITY(1,1) PRIMARY KEY,
    full_name NVARCHAR(255) NOT NULL,
    email NVARCHAR(255) UNIQUE NOT NULL,
    password_plain NVARCHAR(255) NOT NULL,
    role NVARCHAR(32) NOT NULL DEFAULT 'user',
    created_at NVARCHAR(64) NOT NULL
);

IF OBJECT_ID('incidents', 'U') IS NULL
CREATE TABLE incidents (
    id INT IDENTITY(1,1) PRIMARY KEY,
    user_id INT NOT NULL,
    flight_number NVARCHAR(64) NOT NULL,
    airline NVARCHAR(255) NOT NULL,
    category NVARCHAR(255) NOT NULL,
    status NVARCHAR(255) NOT NULL,
    summary NVARCHAR(MAX) NOT NULL,
    claim_amount FLOAT NOT NULL DEFAULT 0,
    created_at NVARCHAR(64) NOT NULL
);

IF OBJECT_ID('chat_messages', 'U') IS NULL
CREATE TABLE chat_messages (
    id INT IDENTITY(1,1) PRIMARY KEY,
    incident_id INT NOT NULL,
    role NVARCHAR(50) NOT NULL,
    content NVARCHAR(MAX) NOT NULL,
    citations_json NVARCHAR(MAX),
    created_at NVARCHAR(64) NOT NULL
);

IF OBJECT_ID('classified_incident_logs', 'U') IS NULL
CREATE TABLE classified_incident_logs (
    id INT IDENTITY(1,1) PRIMARY KEY,
    incident_id INT NOT NULL,
    category NVARCHAR(255) NOT NULL,
    confidence FLOAT NOT NULL,
    notes NVARCHAR(MAX) NOT NULL,
    created_at NVARCHAR(64) NOT NULL
);

IF OBJECT_ID('knowledge_documents', 'U') IS NULL
CREATE TABLE knowledge_documents (
    id INT IDENTITY(1,1) PRIMARY KEY,
    filename NVARCHAR(255) NOT NULL,
    blob_name NVARCHAR(255) NOT NULL,
    content_text NVARCHAR(MAX) NOT NULL,
    source_kind NVARCHAR(100) NOT NULL,
    indexed BIT NOT NULL DEFAULT 0,
    is_active BIT NOT NULL DEFAULT 1,
    mime_type NVARCHAR(255) NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    created_at NVARCHAR(64) NOT NULL
);
"""


class Database:
    def __init__(self) -> None:
        if settings.database_backend.lower() == "sqlserver" and not pyodbc:
            raise RuntimeError("DATABASE_BACKEND=sqlserver requiere pyodbc instalado.")
        self.requested_backend = "sqlserver" if settings.is_sqlserver else "sqlite"
        self.backend = self.requested_backend
        self.last_error = ""
        self.sqlite_path = Path(settings.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        if self.backend == "sqlserver":
            try:
                conn = pyodbc.connect(settings.sqlserver_connection_string)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                raise RuntimeError(f"No se pudo conectar a Azure SQL / SQL Server: {exc}") from exc
            else:
                try:
                    yield conn
                finally:
                    conn.close()
                return

        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def execute_script(self, script: str) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            if self.backend == "sqlserver":
                for statement in [s.strip() for s in script.split("\n\n") if s.strip()]:
                    cursor.execute(statement)
            else:
                cursor.executescript(script)
            conn.commit()

    def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return self._row_to_dict(cursor, row)

    def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_dict(cursor, row) for row in rows]

    def execute_no_return(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if self.backend == "sqlserver":
                conn.commit()
                match = re.search(r"INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", query, flags=re.IGNORECASE)
                if not match:
                    return 0
                table_name = match.group(1)
                row = cursor.execute(f"SELECT TOP 1 id FROM {table_name} ORDER BY id DESC").fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            conn.commit()
            return int(cursor.lastrowid)

    def init(self) -> None:
        if self.backend == "sqlserver":
            try:
                conn = pyodbc.connect(settings.sqlserver_connection_string)  # type: ignore[arg-type]
                try:
                    cursor = conn.cursor()
                    for statement in [s.strip() for s in SQLSERVER_SCHEMA.split("\n\n") if s.strip()]:
                        cursor.execute(statement)
                    conn.commit()
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                raise RuntimeError(f"No se pudo inicializar Azure SQL / SQL Server: {exc}") from exc
        else:
            self.execute_script(SQLITE_SCHEMA)
        self.ensure_schema_extensions()
        self.seed()

    def ensure_schema_extensions(self) -> None:
        self.ensure_users_role_column()
        self.ensure_knowledge_document_columns()

    def ensure_users_role_column(self) -> None:
        if self.backend == "sqlserver":
            result = self.fetchone(
                """
                SELECT COUNT(*) AS total
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'users' AND COLUMN_NAME = 'role'
                """
            )
            if result and int(result["total"]) == 0:
                self.execute_no_return("ALTER TABLE users ADD role NVARCHAR(32) NOT NULL DEFAULT 'user'")
            self.execute_no_return("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''")
            return

        result = self.fetchall("PRAGMA table_info(users)")
        columns = {row["name"] for row in result}
        if "role" not in columns:
            self.execute_no_return("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        self.execute_no_return("UPDATE users SET role = 'user' WHERE role IS NULL OR role = ''")

    def ensure_knowledge_document_columns(self) -> None:
        if self.backend == "sqlserver":
            self._ensure_sqlserver_column("knowledge_documents", "is_active", "BIT NOT NULL DEFAULT 1")
            self._ensure_sqlserver_column("knowledge_documents", "mime_type", "NVARCHAR(255) NULL")
            self._ensure_sqlserver_column("knowledge_documents", "file_size", "BIGINT NOT NULL DEFAULT 0")
            self.execute_no_return("UPDATE knowledge_documents SET is_active = 1 WHERE is_active IS NULL")
            self.execute_no_return("UPDATE knowledge_documents SET file_size = 0 WHERE file_size IS NULL")
            return

        columns = {row["name"] for row in self.fetchall("PRAGMA table_info(knowledge_documents)")}
        if "is_active" not in columns:
            self.execute_no_return("ALTER TABLE knowledge_documents ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "mime_type" not in columns:
            self.execute_no_return("ALTER TABLE knowledge_documents ADD COLUMN mime_type TEXT")
        if "file_size" not in columns:
            self.execute_no_return("ALTER TABLE knowledge_documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
        self.execute_no_return("UPDATE knowledge_documents SET is_active = 1 WHERE is_active IS NULL")
        self.execute_no_return("UPDATE knowledge_documents SET file_size = 0 WHERE file_size IS NULL")

    def _ensure_sqlserver_column(self, table_name: str, column_name: str, definition: str) -> None:
        result = self.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
            """,
            (table_name, column_name),
        )
        if result and int(result["total"]) == 0:
            self.execute_no_return(f"ALTER TABLE {table_name} ADD {column_name} {definition}")

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _row_to_dict(cursor, row) -> dict[str, Any] | None:
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return dict(row)
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row, strict=False))

    def seed(self) -> None:
        now = self.now_iso()
        user_id = self.ensure_user("Demo User", "demo@airclaim.ai", "demo1234", "user", now)
        self.ensure_user("Admin AirClaim", "admin@airclaim.ai", "admin1234", "admin", now)

        incidents = self.fetchone("SELECT COUNT(*) AS total FROM incidents")
        if incidents and int(incidents["total"]) > 0:
            self.ensure_seed_knowledge(now)
            return

        incident_1 = self.execute(
            """
            INSERT INTO incidents (user_id, flight_number, airline, category, status, summary, claim_amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                "IB3166",
                "Iberia",
                "Retraso superior a 3 horas",
                "Compensacion en revision",
                "Vuelo Madrid-Londres con retraso de 4 horas por reorganizacion operativa.",
                250.0,
                now,
            ),
        )
        incident_2 = self.execute(
            """
            INSERT INTO incidents (user_id, flight_number, airline, category, status, summary, claim_amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                "VY1284",
                "Vueling",
                "Equipaje extraviado",
                "Documentacion pendiente",
                "Maleta no entregada en destino y gastos esenciales ya documentados.",
                420.0,
                now,
            ),
        )
        self.execute_no_return(
            """
            INSERT INTO classified_incident_logs (incident_id, category, confidence, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (incident_1, "EU261_delay", 0.96, "Clasificado automaticamente por palabras clave y duracion.", now),
        )
        self.execute_no_return(
            """
            INSERT INTO classified_incident_logs (incident_id, category, confidence, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (incident_2, "baggage_loss", 0.92, "Clasificado automaticamente por menciones de maleta y destino.", now),
        )
        self.execute_no_return(
            """
            INSERT INTO chat_messages (incident_id, role, content, citations_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                incident_1,
                "assistant",
                "He preparado un borrador inicial de reclamacion EU261 y he marcado los documentos clave que faltan.",
                "[]",
                now,
            ),
        )
        self.ensure_seed_knowledge(now)

    def ensure_seed_knowledge(self, now: str) -> None:
        docs = self.fetchone("SELECT COUNT(*) AS total FROM knowledge_documents")
        if docs and int(docs["total"]) > 0:
            return
        self.execute_no_return(
            """
            INSERT INTO knowledge_documents (filename, blob_name, content_text, source_kind, indexed, is_active, mime_type, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "reglamento-eu261.txt",
                "local/reglamento-eu261.txt",
                "El Reglamento (CE) 261/2004 establece compensaciones por retrasos, cancelaciones y denegaciones de embarque.",
                "seed",
                1,
                1,
                "text/plain",
                110,
                now,
            ),
        )

    def ensure_user(self, full_name: str, email: str, password: str, role: str, created_at: str) -> int:
        user = self.fetchone("SELECT id, role FROM users WHERE email = ?", (email.lower(),))
        if user:
            if user.get("role") != role:
                self.execute_no_return("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
            return int(user["id"])
        return self.execute(
            "INSERT INTO users (full_name, email, password_plain, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (full_name, email.lower(), password, role, created_at),
        )


db = Database()
