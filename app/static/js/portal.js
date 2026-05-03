const pageMode = document.body.dataset.page;
const userCard = document.getElementById("user-card");
const incidentsList = document.getElementById("incidents-list");
const chatThread = document.getElementById("chat-thread");
const chatContext = document.getElementById("chat-context");
const docsList = document.getElementById("docs-list");
const toast = document.getElementById("toast");
const scrollPlane = document.getElementById("scroll-plane");
const docDetailForm = document.getElementById("doc-detail-form");
const deleteDocBtn = document.getElementById("delete-doc-btn");

const state = {
    user: null,
    incidents: [],
    selectedIncidentId: null,
    documents: [],
    selectedDocumentId: null,
};

async function api(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Ha ocurrido un error");
    }
    return response.json();
}

function showToast(message) {
    toast.textContent = message;
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), 2800);
}

function setupRevealAnimations() {
    const items = document.querySelectorAll("[data-reveal]");
    if (!("IntersectionObserver" in window)) {
        items.forEach((item) => item.classList.add("revealed"));
        return;
    }
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("revealed");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.14, rootMargin: "0px 0px -6% 0px" },
    );
    items.forEach((item, index) => {
        item.style.transitionDelay = `${Math.min(index % 4, 3) * 60}ms`;
        observer.observe(item);
    });
}

function updateScrollScene() {
    const scrollTop = window.scrollY || window.pageYOffset;
    const progress = Math.min(scrollTop / Math.max(document.body.scrollHeight - window.innerHeight, 1), 1);
    document.documentElement.style.setProperty("--scroll-progress", progress.toFixed(4));
    document.querySelectorAll(".bg-slide").forEach((slide, index) => {
        const activeIndex = Math.min(2, Math.floor(progress * 3.01));
        slide.classList.toggle("active", index === activeIndex);
    });
    if (!scrollPlane) return;
    const x = -16 + progress * 116;
    const y = 8 + progress * 50;
    scrollPlane.style.transform = `translate(${x}vw, ${y}vh) rotate(${progress * 12 - 7}deg) scale(${0.92 + progress * 0.14})`;
}

function updateUserCard() {
    if (!userCard || !state.user) return;
    userCard.innerHTML = `
        <strong>${state.user.full_name}</strong>
        <span>${state.user.email}</span>
        <span>Rol: ${state.user.role}</span>
    `;
}

function renderIncidents() {
    if (!incidentsList) return;
    if (!state.incidents.length) {
        incidentsList.innerHTML = '<div class="empty-state">No hay incidencias todavía. Crea la primera y seguimos.</div>';
        return;
    }
    incidentsList.innerHTML = state.incidents
        .map((item) => `
            <article class="incident-item ${item.id === state.selectedIncidentId ? "active" : ""}">
                <button type="button" data-incident-id="${item.id}">
                    <strong>${item.airline} · ${item.flight_number}</strong>
                    <div class="incident-meta">${item.category}</div>
                    <div>${item.summary}</div>
                    <div class="incident-meta">${item.status} · ${item.claim_amount} EUR</div>
                </button>
            </article>
        `)
        .join("");
    incidentsList.querySelectorAll("[data-incident-id]").forEach((button) => {
        button.addEventListener("click", () => selectIncident(Number(button.dataset.incidentId)));
    });
}

function renderMessages(items = []) {
    if (!chatThread) return;
    if (!items.length) {
        chatThread.innerHTML = '<div class="empty-state">Selecciona una incidencia para abrir la conversación.</div>';
        return;
    }
    chatThread.innerHTML = items
        .map((item) => {
            const citations = (item.citations || [])
                .map((citation) => `<div class="citation">Fuente: ${citation.filename}</div>`)
                .join("");
            return `
                <article class="chat-bubble ${item.role}">
                    <div>${item.content}</div>
                    ${citations}
                </article>
            `;
        })
        .join("");
    chatThread.scrollTop = chatThread.scrollHeight;
}

function renderDocuments(items = []) {
    if (!docsList) return;
    if (!items.length) {
        docsList.innerHTML = '<div class="empty-state">Todavía no hay documentos indexados.</div>';
        populateDocumentForm(null);
        return;
    }
    docsList.innerHTML = items
        .map((item) => `
            <article class="document-item ${item.id === state.selectedDocumentId ? "active" : ""}">
                <button type="button" data-document-id="${item.id}">
                    <strong>${item.filename}</strong>
                    <div class="incident-meta">${item.source_kind || "admin_upload"} · ${item.created_at}</div>
                    <div class="document-badges">
                        <span>${item.is_active ? "Activo" : "Pausado"}</span>
                        <span>${item.indexed ? "Indexado" : "Sin índice"}</span>
                        <span>${formatBytes(item.file_size || 0)}</span>
                    </div>
                </button>
            </article>
        `)
        .join("");
    docsList.querySelectorAll("[data-document-id]").forEach((button) => {
        button.addEventListener("click", () => selectDocument(Number(button.dataset.documentId)));
    });
}

function populateDocumentForm(item) {
    if (!docDetailForm) return;
    const idInput = document.getElementById("doc-id");
    const filenameInput = document.getElementById("doc-filename");
    const sourceKindInput = document.getElementById("doc-source-kind");
    const activeInput = document.getElementById("doc-active");
    const indexedInput = document.getElementById("doc-indexed");
    const meta = document.getElementById("doc-meta");

    if (!item) {
        idInput.value = "";
        filenameInput.value = "";
        sourceKindInput.value = "";
        activeInput.checked = false;
        indexedInput.checked = false;
        meta.innerHTML = "<span>Selecciona un documento para ver tamaño, blob y extracto.</span>";
        if (deleteDocBtn) deleteDocBtn.disabled = true;
        return;
    }

    idInput.value = item.id;
    filenameInput.value = item.filename || "";
    sourceKindInput.value = item.source_kind || "";
    activeInput.checked = Boolean(item.is_active);
    indexedInput.checked = Boolean(item.indexed);
    meta.innerHTML = `
        <strong>Blob:</strong>
        <span>${item.blob_name}</span>
        <span>MIME: ${item.mime_type || "application/octet-stream"} · Tamaño: ${formatBytes(item.file_size || 0)}</span>
        <span>Extracto: ${item.content_preview || "Sin extracto disponible."}</span>
    `;
    if (deleteDocBtn) deleteDocBtn.disabled = false;
}

function formatBytes(bytes) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function loadStats() {
    const stats = await api("/api/stats");
    Object.entries(stats).forEach(([key, value]) => {
        const target = document.querySelector(`[data-stat="${key}"]`);
        if (!target) return;
        target.textContent = key === "success_rate" ? `${value}%` : key === "average_claim" ? `${value} EUR` : value;
    });
}

async function restoreSession() {
    const response = await api("/api/auth/me");
    state.user = response.user;
    updateUserCard();
}

async function loadIncidents() {
    const response = await api("/api/incidents");
    state.incidents = response.items;
    renderIncidents();
    if (state.incidents.length && !state.selectedIncidentId) {
        await selectIncident(state.incidents[0].id);
    } else if (!state.incidents.length) {
        renderMessages();
    }
}

async function selectIncident(incidentId) {
    state.selectedIncidentId = incidentId;
    const incident = state.incidents.find((item) => item.id === incidentId);
    if (chatContext) {
        chatContext.textContent = incident ? `${incident.airline} · ${incident.flight_number}` : "Selecciona una incidencia";
    }
    const response = await api(`/api/incidents/${incidentId}/messages`);
    renderMessages(response.items);
}

async function loadDocuments() {
    const response = await api("/api/admin/knowledge/documents");
    state.documents = response.items;
    if (!state.selectedDocumentId && state.documents.length) {
        state.selectedDocumentId = state.documents[0].id;
    }
    renderDocuments(state.documents);
    const selected = state.documents.find((item) => item.id === state.selectedDocumentId) || state.documents[0] || null;
    populateDocumentForm(selected);
}

async function selectDocument(docId) {
    const response = await api(`/api/admin/knowledge/documents/${docId}`);
    state.selectedDocumentId = docId;
    const detail = response.item;
    state.documents = state.documents.map((doc) => (doc.id === docId ? { ...doc, ...detail } : doc));
    renderDocuments(state.documents);
    populateDocumentForm(detail);
}

document.getElementById("logout-btn")?.addEventListener("click", async () => {
    try {
        await api("/api/auth/logout", { method: "POST" });
        window.location.href = "/login";
    } catch (error) {
        showToast(error.message);
    }
});

document.getElementById("incident-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const response = await api("/api/incidents", { method: "POST", body: new FormData(event.currentTarget) });
        showToast(`Incidencia creada y clasificada como ${response.category}.`);
        event.currentTarget.reset();
        await loadIncidents();
    } catch (error) {
        showToast(error.message);
    }
});

document.getElementById("chat-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selectedIncidentId) {
        showToast("Primero selecciona una incidencia.");
        return;
    }
    try {
        const form = event.currentTarget;
        const response = await api(`/api/incidents/${state.selectedIncidentId}/messages`, {
            method: "POST",
            body: new FormData(form),
        });
        form.reset();
        await selectIncident(state.selectedIncidentId);
        if (response.citations?.length) {
            showToast(`Respuesta generada con ${response.citations.length} fuente(s).`);
        }
    } catch (error) {
        showToast(error.message);
    }
});

document.getElementById("docs-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("docs-input");
    if (!input.files.length) {
        showToast("Selecciona al menos un documento.");
        return;
    }
    try {
        const formData = new FormData();
        Array.from(input.files).forEach((file) => formData.append("files", file));
        await api("/api/admin/knowledge/upload", { method: "POST", body: formData });
        input.value = "";
        showToast("Documentos ingresados al modelo.");
        await Promise.all([loadDocuments(), loadStats()]);
    } catch (error) {
        showToast(error.message);
    }
});

docDetailForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const docId = document.getElementById("doc-id").value;
    if (!docId) {
        showToast("Selecciona un documento antes de guardar.");
        return;
    }
    try {
        const payload = {
            filename: document.getElementById("doc-filename").value.trim(),
            source_kind: document.getElementById("doc-source-kind").value.trim(),
            is_active: document.getElementById("doc-active").checked,
            indexed: document.getElementById("doc-indexed").checked,
        };
        const response = await api(`/api/admin/knowledge/documents/${docId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        state.documents = state.documents.map((doc) => (doc.id === Number(docId) ? response.item : doc));
        renderDocuments(state.documents);
        populateDocumentForm(response.item);
        showToast("Documento actualizado.");
    } catch (error) {
        showToast(error.message);
    }
});

deleteDocBtn?.addEventListener("click", async () => {
    const docId = document.getElementById("doc-id").value;
    if (!docId) {
        showToast("Selecciona un documento antes de eliminar.");
        return;
    }
    try {
        await api(`/api/admin/knowledge/documents/${docId}`, { method: "DELETE" });
        state.documents = state.documents.filter((doc) => doc.id !== Number(docId));
        state.selectedDocumentId = state.documents[0]?.id || null;
        renderDocuments(state.documents);
        populateDocumentForm(state.documents[0] || null);
        await loadStats();
        showToast("Documento eliminado del blob y de la base.");
    } catch (error) {
        showToast(error.message);
    }
});

window.addEventListener("scroll", updateScrollScene, { passive: true });
window.addEventListener("resize", updateScrollScene);

setupRevealAnimations();
updateScrollScene();

restoreSession()
    .then(() => {
        if (pageMode === "admin") {
            return Promise.all([loadStats(), loadDocuments()]);
        }
        return loadIncidents();
    })
    .catch(() => {
        window.location.href = "/login";
    });
