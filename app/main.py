from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .config import ROOT_DIR, settings
from .database import db
from .security import create_token, decode_token
from .services import (
    append_chat_message,
    claim_agent_service,
    classify_incident,
    delete_knowledge_document,
    get_knowledge_document,
    list_knowledge_documents,
    persist_training_document,
    update_knowledge_document,
)

AUTH_COOKIE_NAME = "airclaim_token"

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(ROOT_DIR / "app" / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "app" / "static")), name="static")


def extract_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    return cookie_token or None


def build_user_context(user: dict | None) -> dict:
    return {
        "app_name": settings.app_name,
        "current_user": user,
        "is_authenticated": bool(user),
        "is_admin": bool(user and user.get("role") == "admin"),
    }


def next_route_for_user(user: dict) -> str:
    return "/admin" if user.get("role") == "admin" else "/app"


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        token = extract_token_from_request(request)
        if token:
            try:
                payload = decode_token(token, settings.jwt_secret)
                user = db.fetchone(
                    "SELECT id, full_name, email, role, created_at FROM users WHERE id = ?",
                    (payload["sub"],),
                )
                request.state.user = user
            except Exception:  # noqa: BLE001
                request.state.user = None

        path = request.url.path
        if path.startswith("/admin"):
            if not request.state.user:
                return RedirectResponse(url=f"/login?{urlencode({'next': '/admin'})}", status_code=302)
            if request.state.user.get("role") != "admin":
                return RedirectResponse(url="/app", status_code=302)
        elif path.startswith("/app"):
            if not request.state.user:
                return RedirectResponse(url=f"/login?{urlencode({'next': '/app'})}", status_code=302)

        if path.startswith("/api/admin"):
            if not request.state.user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            if request.state.user.get("role") != "admin":
                return JSONResponse({"detail": "Admin access required"}, status_code=403)

        response = await call_next(request)
        return response


app.add_middleware(AuthContextMiddleware)


@app.on_event("startup")
def on_startup() -> None:
    db.init()


def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.jwt_exp_minutes * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("landing.html", {"request": request} | build_user_context(request.state.user))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if request.state.user:
        return RedirectResponse(url=next_route_for_user(request.state.user), status_code=302)
    return templates.TemplateResponse("login.html", {"request": request} | build_user_context(None))


@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "portal.html",
        {"request": request, "page_mode": "user", "page_title": "Mi panel"} | build_user_context(request.state.user),
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "portal.html",
        {"request": request, "page_mode": "admin", "page_title": "Consola admin"} | build_user_context(request.state.user),
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "database_backend": db.backend,
        "database_requested_backend": db.requested_backend,
        "database_last_error": db.last_error,
    }


@app.get("/api/stats")
def stats() -> dict:
    users = db.fetchone("SELECT COUNT(*) AS total FROM users") or {"total": 0}
    incidents = db.fetchone("SELECT COUNT(*) AS total FROM incidents") or {"total": 0}
    docs = db.fetchone("SELECT COUNT(*) AS total FROM knowledge_documents") or {"total": 0}
    avg_claim = db.fetchone("SELECT COALESCE(AVG(claim_amount), 0) AS avg_claim FROM incidents") or {"avg_claim": 0}
    return {
        "users": int(users["total"]),
        "incidents": int(incidents["total"]),
        "knowledge_docs": int(docs["total"]),
        "average_claim": round(float(avg_claim["avg_claim"]), 2),
        "success_rate": 93,
    }


@app.post("/api/auth/register")
async def register(
    response: Response,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
) -> dict:
    existing = db.fetchone("SELECT id FROM users WHERE email = ?", (email.lower(),))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = db.execute(
        "INSERT INTO users (full_name, email, password_plain, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (full_name, email.lower(), password, "user", db.now_iso()),
    )
    user = db.fetchone(
        "SELECT id, full_name, email, role, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    token = create_token({"sub": user_id, "email": email.lower(), "role": "user"}, settings.jwt_secret, settings.jwt_exp_minutes)
    set_auth_cookie(response, token)
    return {"token": token, "user": user, "redirect_to": "/app"}


@app.post("/api/auth/login")
async def login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
) -> dict:
    user = db.fetchone(
        "SELECT id, full_name, email, role, password_plain, created_at FROM users WHERE email = ?",
        (email.lower(),),
    )
    if not user or user["password_plain"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(
        {"sub": user["id"], "email": user["email"], "role": user["role"]},
        settings.jwt_secret,
        settings.jwt_exp_minutes,
    )
    set_auth_cookie(response, token)
    return {
        "token": token,
        "user": {k: user[k] for k in ("id", "full_name", "email", "role", "created_at")},
        "redirect_to": next_route_for_user(user),
    }


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    clear_auth_cookie(response)
    return {"message": "Logged out"}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user, "redirect_to": next_route_for_user(user)}


@app.get("/api/incidents")
def list_incidents(user: dict = Depends(current_user)) -> dict:
    rows = db.fetchall(
        """
        SELECT id, flight_number, airline, category, status, summary, claim_amount, created_at
        FROM incidents WHERE user_id = ? ORDER BY id DESC
        """,
        (user["id"],),
    )
    return {"items": rows}


@app.post("/api/incidents")
async def create_incident(
    flight_number: str = Form(...),
    airline: str = Form(...),
    summary: str = Form(...),
    claim_amount: float = Form(250),
    user: dict = Depends(current_user),
) -> dict:
    category, confidence, notes = classify_incident(summary)
    incident_id = db.execute(
        """
        INSERT INTO incidents (user_id, flight_number, airline, category, status, summary, claim_amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user["id"], flight_number, airline, category, "Nuevo", summary, claim_amount, db.now_iso()),
    )
    db.execute_no_return(
        """
        INSERT INTO classified_incident_logs (incident_id, category, confidence, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (incident_id, category, confidence, notes, db.now_iso()),
    )
    return {
        "id": incident_id,
        "category": category,
        "classification_confidence": confidence,
        "status": "Nuevo",
    }


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: int, user: dict = Depends(current_user)) -> dict:
    incident = db.fetchone(
        """
        SELECT id, user_id, flight_number, airline, category, status, summary, claim_amount, created_at
        FROM incidents WHERE id = ?
        """,
        (incident_id,),
    )
    if not incident or incident["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Incident not found")
    logs = db.fetchall(
        """
        SELECT category, confidence, notes, created_at
        FROM classified_incident_logs WHERE incident_id = ? ORDER BY id DESC
        """,
        (incident_id,),
    )
    return {"incident": incident, "classification_logs": logs}


@app.get("/api/incidents/{incident_id}/messages")
def list_messages(incident_id: int, user: dict = Depends(current_user)) -> dict:
    incident = db.fetchone("SELECT id, user_id FROM incidents WHERE id = ?", (incident_id,))
    if not incident or incident["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Incident not found")
    messages = db.fetchall(
        """
        SELECT id, role, content, citations_json, created_at
        FROM chat_messages WHERE incident_id = ? ORDER BY id ASC
        """,
        (incident_id,),
    )
    for message in messages:
        message["citations"] = json.loads(message.get("citations_json") or "[]")
    return {"items": messages}


@app.post("/api/incidents/{incident_id}/messages")
async def create_message(
    incident_id: int,
    message: str = Form(...),
    user: dict = Depends(current_user),
) -> dict:
    incident = db.fetchone(
        """
        SELECT id, user_id, flight_number, airline, category, status, summary, claim_amount
        FROM incidents WHERE id = ?
        """,
        (incident_id,),
    )
    if not incident or incident["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Incident not found")
    append_chat_message(incident_id, "user", message)
    response = claim_agent_service.answer(incident, message)
    append_chat_message(incident_id, "assistant", response.answer, response.citations)
    return {"answer": response.answer, "citations": response.citations}


@app.get("/api/admin/knowledge/documents")
def list_admin_documents(admin: dict = Depends(admin_user)) -> dict:
    docs = list_knowledge_documents()
    return {"items": docs, "requested_by": admin["email"]}


@app.get("/api/admin/knowledge/documents/{doc_id}")
def get_admin_document(doc_id: int, admin: dict = Depends(admin_user)) -> dict:
    doc = get_knowledge_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"item": doc, "requested_by": admin["email"]}


@app.post("/api/admin/knowledge/upload")
async def upload_training_documents(
    files: list[UploadFile] = File(...),
    admin: dict = Depends(admin_user),
) -> dict:
    saved = []
    for file in files:
        content = await file.read()
        saved.append(persist_training_document(file.filename, content, source_kind="admin_upload"))
    return {"items": saved, "uploaded_by": admin["email"]}


@app.patch("/api/admin/knowledge/documents/{doc_id}")
async def update_admin_document(
    doc_id: int,
    payload: dict = Body(...),
    admin: dict = Depends(admin_user),
) -> dict:
    doc = update_knowledge_document(
        doc_id,
        filename=payload.get("filename"),
        source_kind=payload.get("source_kind"),
        indexed=payload.get("indexed"),
        is_active=payload.get("is_active"),
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"item": doc, "updated_by": admin["email"]}


@app.delete("/api/admin/knowledge/documents/{doc_id}")
def delete_admin_document(doc_id: int, admin: dict = Depends(admin_user)) -> dict:
    deleted = delete_knowledge_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True, "deleted_by": admin["email"]}


@app.post("/api/demo/bootstrap")
def bootstrap_demo() -> dict:
    return {"message": "Demo data already initialized on startup."}
