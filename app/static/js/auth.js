const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const authFeedback = document.getElementById("auth-feedback");
const toast = document.getElementById("toast");
const scrollPlane = document.getElementById("scroll-plane");

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

function switchAuthView(view) {
    document.querySelectorAll("[data-auth-view]").forEach((button) => {
        button.classList.toggle("active", button.dataset.authView === view);
    });
    loginForm.classList.toggle("hidden", view !== "login");
    registerForm.classList.toggle("hidden", view !== "register");
    authFeedback.textContent = "";
}

function setupRevealAnimations() {
    const items = document.querySelectorAll("[data-reveal]");
    items.forEach((item, index) => {
        item.style.transitionDelay = `${index * 80}ms`;
        requestAnimationFrame(() => item.classList.add("revealed"));
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
    scrollPlane.style.transform = `translate(${6 + progress * 46}vw, ${12 + progress * 22}vh) rotate(-6deg) scale(0.96)`;
}

function nextDestination(payload) {
    const requested = new URLSearchParams(window.location.search).get("next");
    return requested || payload.redirect_to || (payload.user?.role === "admin" ? "/admin" : "/app");
}

document.querySelectorAll("[data-auth-view]").forEach((button) => {
    button.addEventListener("click", () => switchAuthView(button.dataset.authView));
});

loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const payload = await api("/api/auth/login", { method: "POST", body: new FormData(loginForm) });
        showToast("Acceso concedido.");
        document.body.classList.add("is-routing");
        window.location.href = nextDestination(payload);
    } catch (error) {
        authFeedback.textContent = error.message;
    }
});

registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const payload = await api("/api/auth/register", { method: "POST", body: new FormData(registerForm) });
        showToast("Cuenta creada correctamente.");
        document.body.classList.add("is-routing");
        window.location.href = nextDestination(payload);
    } catch (error) {
        authFeedback.textContent = error.message;
    }
});

window.addEventListener("scroll", updateScrollScene, { passive: true });
window.addEventListener("resize", updateScrollScene);

setupRevealAnimations();
updateScrollScene();
