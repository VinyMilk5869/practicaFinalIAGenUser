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
    if (!toast) return;
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

async function loadStats() {
    const stats = await api("/api/stats");
    Object.entries(stats).forEach(([key, value]) => {
        const target = document.querySelector(`[data-stat="${key}"]`);
        if (!target) return;
        target.textContent = key === "success_rate" ? `${value}%` : key === "average_claim" ? `${value} EUR` : value;
    });
}

window.addEventListener("scroll", updateScrollScene, { passive: true });
window.addEventListener("resize", updateScrollScene);

setupRevealAnimations();
updateScrollScene();
loadStats().catch(() => showToast("No se pudieron cargar algunas métricas."));
