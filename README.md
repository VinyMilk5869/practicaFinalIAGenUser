# AirClaim AI

Aplicacion web para gestion de reclamaciones aereas con panel de usuario, consola administrativa, OCR documental, base de conocimiento para RAG y agente conversacional.

## Resumen funcional

- Backend `FastAPI`
- Frontend server-side con plantillas `Jinja2` y JS vanilla
- Autenticacion por cookie JWT
- CRUD de incidencias para usuario
- Chat contextual sobre incidencias
- Base documental administrativa
- OCR de documentos
- Recuperacion documental por Azure AI Search o fallback local
- Persistencia en `SQLite` o `Azure SQL / SQL Server`
- Almacenamiento documental en local o `Azure Blob Storage`
- Agente con `Azure OpenAI`, `OpenAI` o fallback local

## Stack tecnico

### Backend

- `FastAPI`
- `Starlette`
- `python-multipart`
- `python-dotenv`

### IA y cloud

- `openai`
- `azure-storage-blob`
- `azure-search-documents`
- `azure-ai-documentintelligence`
- `pyodbc`

### Frontend

- HTML con `Jinja2`
- CSS propio
- JavaScript vanilla

## Arquitectura del proyecto

```text
practicaFinal/
├─ app/
│  ├─ main.py              # rutas FastAPI y paginas
│  ├─ services.py          # OCR, storage, search y agente
│  ├─ database.py          # acceso a SQLite / SQL Server y seed
│  ├─ config.py            # carga de entorno
│  ├─ security.py          # JWT y helpers de auth
│  ├─ templates/           # landing, login, portal
│  └─ static/              # CSS, JS, imagenes
├─ data/
│  ├─ airclaims.db         # SQLite local
│  └─ uploads/             # ficheros locales si no hay Blob
├─ requirements.txt
├─ run_server.py
├─ start_local.ps1
└─ .env.example
```

## Componentes principales

### `app/main.py`

Responsable de:

- middleware de autenticacion
- paginas `/`, `/login`, `/app`, `/admin`
- API de auth
- CRUD de incidencias
- chat por incidencia
- panel admin de documentos y sincronizacion

### `app/services.py`

Contiene la logica de integracion:

- `StorageService`
  - guarda y elimina en Azure Blob o `data/uploads`
- `OCRService`
  - usa Azure Document Intelligence si existe configuracion
  - hace fallback local para ficheros de texto
- `SearchService`
  - usa Azure AI Search si esta disponible
  - hace fallback a busqueda keyword sobre `knowledge_documents`
- `ClaimAgentService`
  - usa Azure OpenAI si esta configurado
  - usa OpenAI si existe `OPENAI_API_KEY`
  - responde con fallback local si no hay proveedor accesible

### `app/database.py`

Gestiona:

- inicializacion de esquema
- compatibilidad SQLite / SQL Server
- migraciones ligeras
- seed demo

## Modelo de datos

### Tablas

- `users`
  - usuarios de la aplicacion
- `incidents`
  - expediente principal de reclamacion
- `chat_messages`
  - mensajes del chat por incidencia
- `classified_incident_logs`
  - historial de clasificacion y reclasificacion
- `knowledge_documents`
  - documentos del panel admin y material para RAG

## Flujo tecnico resumido

### Usuario

1. El usuario inicia sesion.
2. Crea o edita una incidencia.
3. El sistema clasifica el resumen.
4. El chat recupera contexto documental.
5. El agente responde y, si aplica, estima compensacion.

### Administrador

1. Sube documentos.
2. Se almacenan en Blob o disco local.
3. Se extrae texto con OCR.
4. Se persisten metadatos en `knowledge_documents`.
5. Se indexan en Azure AI Search o se dejan disponibles para fallback local.

## Configuracion por entorno

La app funciona en tres niveles:

### 1. Local minimo

- `SQLite`
- almacenamiento local
- OCR de texto simple
- busqueda local por keywords
- agente fallback

Es la opcion recomendada para primer arranque y desarrollo funcional.

### 2. Local con servicios Azure parciales

Puedes activar solo lo que necesites:

- Blob sin Search
- Search sin SQL
- Azure OpenAI sin OCR

### 3. Entorno completo Azure

- `DATABASE_BACKEND=sqlserver`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_SEARCH_ENDPOINT` + `AZURE_SEARCH_KEY`
- `AZURE_OCR_ENDPOINT` + `AZURE_OCR_KEY`
- `AZURE_OPENAI_*` o `OPENAI_API_KEY`

## Variables de entorno

Base recomendada: copiar `.env.example` a `.env`.

### Generales

```env
APP_NAME=AirClaim AI
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
JWT_SECRET=replace-with-a-strong-secret
```

### Base de datos

```env
DATABASE_BACKEND=sqlite
SQLITE_PATH=data/airclaims.db
SQLSERVER_CONNECTION_STRING=
```

### Blob Storage

```env
AZURE_STORAGE_CONNECTION_STRING=
AZURE_BLOB_CONTAINER=training-documents
```

### Azure AI Search

```env
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_KEY=
AZURE_SEARCH_INDEX=airclaim-knowledge
```

### OCR

```env
AZURE_OCR_ENDPOINT=
AZURE_OCR_KEY=
AZURE_OCR_REGION=
```

### Modelos

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=
```

## Tutorial de despliegue local funcional y verificado

Esta ruta esta pensada para levantar el proyecto en local sin depender de Azure.

### Estado de verificacion

Verificado en este repositorio con:

- `DATABASE_BACKEND=sqlite`
- servicios Azure desactivados
- app importada con `TestClient`
- resultado:
  - `GET /health` -> `200`
  - `POST /api/auth/login` con usuario demo -> `200`
  - `GET /api/incidents` tras login demo -> `200`

### Requisitos

- Python `3.12`
- PowerShell en Windows
- Acceso al repo local

### Paso 1. Crear entorno virtual

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea activacion:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### Paso 2. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### Paso 3. Crear `.env`

```powershell
Copy-Item .env.example .env
```

### Paso 4. Ajustar `.env` para modo local

Usa esta configuracion minima:

```env
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
JWT_SECRET=dev-secret-change-me

DATABASE_BACKEND=sqlite
SQLITE_PATH=data/airclaims.db
SQLSERVER_CONNECTION_STRING=

AZURE_STORAGE_CONNECTION_STRING=
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_KEY=
AZURE_OCR_ENDPOINT=
AZURE_OCR_KEY=

OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_CHAT_DEPLOYMENT=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=
```

Con esto:

- la base de datos sera `SQLite`
- los documentos se guardaran en `data/uploads`
- el sistema no dependera de Azure Search
- el chat seguira funcionando con fallback local

### Paso 5. Arrancar la aplicacion

Opcion A, directa:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Opcion B, script incluido:

```powershell
python run_server.py
```

Opcion C, script PowerShell del repo:

```powershell
.\start_local.ps1
```

### Paso 6. Abrir la aplicacion

- Landing: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Login: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login)
- Admin: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Paso 7. Probar con la cuenta demo

```text
Email: demo@airclaim.ai
Password: demo1234
```

Administrador:

```text
Email: admin@airclaim.ai
Password: admin1234
```

### Paso 8. Verificacion manual recomendada

#### Healthcheck

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
```

Debe devolver JSON con `status: ok`.

#### Flujo usuario

1. Entrar con `demo@airclaim.ai`
2. Crear una incidencia
3. Abrir la pestaña de chat
4. Enviar un mensaje al agente

#### Flujo admin

1. Entrar con `admin@airclaim.ai`
2. Ir a la base documental
3. Subir un `.txt` de prueba
4. Verificar que aparece en la lista

## Despliegue local con Azure

Si quieres usar servicios Azure reales en tu maquina:

1. Deja `DATABASE_BACKEND=sqlserver` solo si tu equipo resuelve y conecta contra el servidor SQL.
2. Configura `AZURE_STORAGE_CONNECTION_STRING`.
3. Configura `AZURE_SEARCH_ENDPOINT` y `AZURE_SEARCH_KEY`.
4. Configura `AZURE_OCR_ENDPOINT` y `AZURE_OCR_KEY`.
5. Configura `AZURE_OPENAI_*` o `OPENAI_API_KEY`.

## Azure AI Search: requisitos para que funcione correctamente

Para que el proyecto use Azure AI Search sin fallback local, deben cumplirse todas estas condiciones:

### 1. Endpoint correcto

`AZURE_SEARCH_ENDPOINT` debe ser el endpoint exacto del servicio, por ejemplo:

```env
AZURE_SEARCH_ENDPOINT=https://mi-servicio.search.windows.net
```

### 2. Clave con permisos de administracion

`AZURE_SEARCH_KEY` debe ser una `Admin key`, no una `Query key`.

### 3. Red accesible desde tu maquina

Comprueba:

- `nslookup <tu-servicio>.search.windows.net`
- acceso publico habilitado, o bien reglas de red que incluyan tu IP
- si usas `Private Endpoint`, DNS privado y red privada deben estar bien resueltos

### 4. Indice existente o creable

La app trabaja con `AZURE_SEARCH_INDEX`.

Si el indice no existe, la app intenta crearlo cuando puede conectarse con permisos suficientes.

### 5. Reindexado admin

Una vez corregida la conectividad, usa el panel admin y pulsa:

`Sincronizar RAG e indices`

Eso vuelve a subir a Search los documentos activos e indexados.

## Endpoints principales

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

### Usuario

- `GET /api/incidents`
- `POST /api/incidents`
- `GET /api/incidents/{incident_id}`
- `PATCH /api/incidents/{incident_id}`
- `DELETE /api/incidents/{incident_id}`
- `GET /api/incidents/{incident_id}/messages`
- `POST /api/incidents/{incident_id}/messages`

### Admin

- `GET /api/admin/system/status`
- `POST /api/admin/system/sync`
- `GET /api/admin/knowledge/documents`
- `GET /api/admin/knowledge/documents/{doc_id}`
- `POST /api/admin/knowledge/upload`
- `PATCH /api/admin/knowledge/documents/{doc_id}`
- `DELETE /api/admin/knowledge/documents/{doc_id}`

## Limitaciones y fallbacks importantes

- Si Azure Search falla, el chat usa busqueda local.
- Si Azure OCR no esta disponible, los `.txt`, `.md`, `.csv` y `.json` siguen siendo legibles localmente.
- Si no hay proveedor LLM, el agente responde con fallback heuristico.
- Si `SQL Server` no conecta, el modo recomendado para local es `SQLite`.

## Troubleshooting

### La app no arranca y falla SQL Server

Usa:

```env
DATABASE_BACKEND=sqlite
SQLSERVER_CONNECTION_STRING=
```

### El chat falla por Azure AI Search

Revisa:

- DNS del endpoint
- networking del servicio
- admin key

Mientras tanto, la app puede seguir con fallback local si `knowledge_documents` tiene contenido.

### `pyodbc` da problemas en Windows

Instala:

- ODBC Driver 18 for SQL Server

Y confirma que el connection string usa el driver correcto.

### PowerShell bloquea scripts

Ejecuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Seguridad

- No subas `.env` al repositorio
- rota cualquier clave real compartida fuera de un canal seguro
- usa secretos diferentes para desarrollo y produccion
- cambia `JWT_SECRET` antes de cualquier despliegue real

## Estado actual del README

Este documento se ha actualizado para reflejar el comportamiento real del proyecto y una ruta de arranque local que ha sido comprobada con:

- healthcheck OK
- login demo OK
- listado de incidencias OK
