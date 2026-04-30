const state = {
    token: localStorage.getItem("airclaim_token") || "",
    user: null,
    incidents: [],
    selectedIncidentId: null,
};

const authModal = document.getElementById("auth-modal");
const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const authFeedback = document.getElementById("auth-feedback");
const userCard = document.getElementById("user-card");
const incidentsList = document.getElementById("incidents-list");
const docsList = document.getElementById("docs-list");
const chatThread = document.getElementById("chat-thread");
const chatContext = document.getElementById("chat-context");
const toast = document.getElementById("toast");
const scrollPlane = document.getElementById("scroll-plane");

async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.token) {
        headers.set("Authorization", `Bearer ${state.token}`);
    }
    const response = await fetch(path, { ...options, headers });
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

function showAuth(view = "login") {
    authModal.classList.remove("hidden");
    switchAuthView(view);
}

function hideAuth() {
    authModal.classList.add("hidden");
    authFeedback.textContent = "";
}

function switchAuthView(view) {
    document.querySelectorAll("[data-auth-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.authView === view);
    });
    loginForm.classList.toggle("hidden", view !== "login");
    registerForm.classList.toggle("hidden", view !== "register");
    authFeedback.textContent = "";
}

function updateUserCard() {
    if (!state.user) {
        userCard.innerHTML = "<strong>No autenticado</strong><span>Accede para activar el panel operativo.</span>";
        return;
    }
    userCard.innerHTML = `
        <strong>${state.user.full_name}</strong>
        <span>${state.user.email}</span>
        <span>Panel listo para crear incidencias, subir documentos y hablar con el agente.</span>
    `;
}

function renderDocuments(items = []) {
    if (!items.length) {
        docsList.innerHTML = '<div class="empty-state">Todavia no hay documentos cargados.</div>';
        return;
    }
    docsList.innerHTML = items
        .map((item) => `
            <article class="incident-item">
                <strong>${item.filename}</strong>
                <div class="incident-meta">${item.source_kind || "upload"} · ${item.blob_name || ""}</div>
            </article>
        `)
        .join("");
}

function renderIncidents() {
    if (!state.incidents.length) {
        incidentsList.innerHTML = '<div class="empty-state">No hay incidencias todavia. Crea la primera y seguimos.</div>';
        return;
    }
    incidentsList.innerHTML = state.incidents
        .map((item) => `
            <article class="incident-item">
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
    if (!items.length) {
        chatThread.innerHTML = '<div class="empty-state">Selecciona una incidencia para abrir la conversacion.</div>';
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

async function loadStats() {
    const stats = await api("/api/stats");
    Object.entries(stats).forEach(([key, value]) => {
        const target = document.querySelector(`[data-stat="${key}"]`);
        if (!target) return;
        target.textContent = key === "success_rate" ? `${value}%` : key === "average_claim" ? `${value} EUR` : value;
    });
}

async function loadDocuments() {
    if (!state.token) {
        renderDocuments();
        return;
    }
    const response = await api("/api/knowledge/documents");
    renderDocuments(response.items);
}

async function loadIncidents() {
    if (!state.token) {
        state.incidents = [];
        renderIncidents();
        renderMessages();
        return;
    }
    const response = await api("/api/incidents");
    state.incidents = response.items;
    renderIncidents();
    if (state.incidents.length && !state.selectedIncidentId) {
        await selectIncident(state.incidents[0].id);
    }
}

async function selectIncident(incidentId) {
    state.selectedIncidentId = incidentId;
    const incident = state.incidents.find((item) => item.id === incidentId);
    chatContext.textContent = incident ? `${incident.airline} · ${incident.flight_number}` : "Selecciona una incidencia";
    const response = await api(`/api/incidents/${incidentId}/messages`);
    renderMessages(response.items);
}

async function restoreSession() {
    if (!state.token) {
        updateUserCard();
        renderIncidents();
        renderDocuments();
        renderMessages();
        return;
    }
    try {
        const response = await api("/api/auth/me");
        state.user = response.user;
        updateUserCard();
        await Promise.all([loadIncidents(), loadDocuments()]);
    } catch {
        logout();
    }
}

function setSession(token, user) {
    state.token = token;
    state.user = user;
    localStorage.setItem("airclaim_token", token);
    updateUserCard();
}

function logout() {
    state.token = "";
    state.user = null;
    state.incidents = [];
    state.selectedIncidentId = null;
    localStorage.removeItem("airclaim_token");
    updateUserCard();
    renderIncidents();
    renderDocuments();
    renderMessages();
    chatContext.textContent = "Selecciona una incidencia";
    showToast("Sesion cerrada.");
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
        { threshold: 0.16, rootMargin: "0px 0px -8% 0px" },
    );
    items.forEach((item, index) => {
        item.style.transitionDelay = `${Math.min(index % 4, 3) * 60}ms`;
        observer.observe(item);
    });
}

function updateScrollScene() {
    if (!scrollPlane) return;
    const scrollTop = window.scrollY || window.pageYOffset;
    const maxScroll = Math.max(document.body.scrollHeight - window.innerHeight, 1);
    const progress = Math.min(scrollTop / maxScroll, 1);
    const x = -22 + progress * 124;
    const y = 10 + progress * 58 + Math.sin(progress * Math.PI * 5) * 2.5;
    const rotate = -8 + progress * 13;
    const scale = 0.88 + progress * 0.2;
    scrollPlane.style.transform = `translate(${x}vw, ${y}vh) rotate(${rotate}deg) scale(${scale})`;
}

document.querySelectorAll("[data-open-auth]").forEach((button) => {
    button.addEventListener("click", () => showAuth(button.dataset.openAuth));
});

document.getElementById("close-auth").addEventListener("click", hideAuth);
document.querySelectorAll("[data-auth-view]").forEach((button) => {
    button.addEventListener("click", () => switchAuthView(button.dataset.authView));
});
document.getElementById("logout-btn").addEventListener("click", logout);

loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const formData = new FormData(loginForm);
        const response = await api("/api/auth/login", { method: "POST", body: formData });
        setSession(response.token, response.user);
        hideAuth();
        await Promise.all([loadIncidents(), loadDocuments()]);
        showToast("Bienvenido de vuelta.");
    } catch (error) {
        authFeedback.textContent = error.message;
    }
});

registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const formData = new FormData(registerForm);
        const response = await api("/api/auth/register", { method: "POST", body: formData });
        setSession(response.token, response.user);
        hideAuth();
        await Promise.all([loadIncidents(), loadDocuments()]);
        showToast("Cuenta creada correctamente.");
    } catch (error) {
        authFeedback.textContent = error.message;
    }
});

document.getElementById("incident-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.token) {
        showAuth("login");
        return;
    }
    try {
        const response = await api("/api/incidents", {
            method: "POST",
            body: new FormData(event.currentTarget),
        });
        showToast(`Incidencia creada y clasificada como ${response.category}.`);
        event.currentTarget.reset();
        await loadIncidents();
    } catch (error) {
        showToast(error.message);
    }
});

document.getElementById("docs-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.token) {
        showAuth("login");
        return;
    }
    const input = document.getElementById("docs-input");
    if (!input.files.length) {
        showToast("Selecciona al menos un documento.");
        return;
    }
    try {
        const formData = new FormData();
        Array.from(input.files).forEach((file) => formData.append("files", file));
        await api("/api/knowledge/upload", { method: "POST", body: formData });
        input.value = "";
        showToast("Documentos subidos e indexados.");
        await loadDocuments();
    } catch (error) {
        showToast(error.message);
    }
});

document.getElementById("chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.token) {
        showAuth("login");
        return;
    }
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

window.addEventListener("scroll", updateScrollScene, { passive: true });
window.addEventListener("resize", updateScrollScene);

setupRevealAnimations();
updateScrollScene();

Promise.all([loadStats(), restoreSession()]).catch(() => {
    showToast("La aplicacion ha cargado con datos parciales.");
});
