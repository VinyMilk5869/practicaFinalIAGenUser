from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "airclaims.db"


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AirClaim AI")
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_exp_minutes: int = int(os.getenv("JWT_EXP_MINUTES", "720"))
    database_backend: str = os.getenv("DATABASE_BACKEND", "sqlite")
    sqlserver_connection_string: str = os.getenv("SQLSERVER_CONNECTION_STRING", "")
    sqlite_path: str = os.getenv("SQLITE_PATH", str(DB_PATH))
    blob_connection_string: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    blob_container_name: str = os.getenv("AZURE_BLOB_CONTAINER", "training-documents")
    azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    azure_search_key: str = os.getenv("AZURE_SEARCH_KEY", "")
    azure_search_index: str = os.getenv("AZURE_SEARCH_INDEX", "airclaim-knowledge")
    azure_ocr_endpoint: str = os.getenv("AZURE_OCR_ENDPOINT", "")
    azure_ocr_key: str = os.getenv("AZURE_OCR_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    @property
    def is_sqlserver(self) -> bool:
        return self.database_backend.lower() == "sqlserver" and bool(self.sqlserver_connection_string)


settings = Settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
