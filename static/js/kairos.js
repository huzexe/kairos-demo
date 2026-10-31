/* Kairos — small helpers used on every page. */
(function () {
  "use strict";

  // Read Django's CSRF token from its cookie (needed for fetch() POSTs).
  window.kairosCsrf = function () {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  };

  // Show a toast message, the same style as Django's messages.
  window.kairosToast = function (text, kind) {
    const box = document.getElementById("toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.setAttribute("role", "status");
    el.innerHTML = '<svg class="icon"><use href="#i-' + (kind === "error" ? "alert" : "check-circle") +
      '"/></svg><span></span><button type="button" data-dismiss aria-label="Dismiss">&times;</button>';
    el.querySelector("span").textContent = text;
    box.appendChild(el);
    autoDismiss(el);
  };

  function dismiss(el) {
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 220);
  }
  function autoDismiss(el) {
    setTimeout(() => dismiss(el), el.classList.contains("error") ? 7000 : 4000);
  }
  document.querySelectorAll(".toast").forEach(autoDismiss);

  document.addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest("[data-dismiss]")) dismiss(t.closest(".toast"));
    if (t.closest("[data-open-nav]")) document.body.classList.add("nav-open");
    if (t.closest("[data-close-nav]")) document.body.classList.remove("nav-open");
  });

  // Ask before destructive actions: <form data-confirm="Delete this lead?">
  document.addEventListener("submit", (e) => {
    const form = e.target;
    const msg = (e.submitter && e.submitter.dataset.confirm) || form.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.body.classList.remove("nav-open");
  });

  // Give the top bar a border once the page scrolls.
  const bar = document.getElementById("topbar");
  if (bar) {
    const onScroll = () => bar.classList.toggle("is-scrolled", window.scrollY > 4);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Auto-submit filter dropdowns: <select data-autosubmit>
  document.querySelectorAll("[data-autosubmit]").forEach((el) =>
    el.addEventListener("change", () => el.form.submit()));
})();
