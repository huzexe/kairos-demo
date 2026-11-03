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
    el.innerHTML = '<span class="toast-text"></span><button type="button" data-dismiss aria-label="Dismiss">&times;</button>';
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

  // Show a chosen agency logo straight away (it's saved with the form).
  document.querySelectorAll("[data-logo-input]").forEach((input) =>
    input.addEventListener("change", () => {
      const box = document.querySelector("[data-logo-preview]");
      if (!box || !input.files[0]) return;
      const img = document.createElement("img");
      img.alt = "Your agency logo";
      img.src = URL.createObjectURL(input.files[0]);
      box.replaceChildren(img);
    }));

  // Money charts come once per currency: the switch shows one and is remembered.
  const showCurrency = (code) => {
    if (!document.querySelector(`[data-currency-panel="${CSS.escape(code)}"]`)) return;
    document.querySelectorAll("[data-currency-panel]").forEach((el) => { el.hidden = el.dataset.currencyPanel !== code; });
    document.querySelectorAll("[data-currency]").forEach((el) => el.setAttribute("aria-pressed", el.dataset.currency === code));
  };
  document.querySelectorAll("[data-currency]").forEach((el) =>
    el.addEventListener("click", () => {
      showCurrency(el.dataset.currency);
      try { localStorage.setItem("kairos-currency", el.dataset.currency); } catch (e) { /* private window */ }
    }));
  try { const saved = localStorage.getItem("kairos-currency"); if (saved) showCurrency(saved); } catch (e) { /* private window */ }

  // Chart tooltips: any mark with data-tip, on hover or keyboard focus.
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  const showTip = (mark) => {
    tip.textContent = mark.dataset.tip;
    tip.hidden = false;
    const box = mark.getBoundingClientRect();
    const left = Math.min(Math.max(8, box.left + box.width / 2 - tip.offsetWidth / 2), window.innerWidth - tip.offsetWidth - 8);
    const top = box.top - tip.offsetHeight - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${top < 8 ? box.bottom + 8 : top}px`;
  };
  const tipEvent = (e) => {
    const mark = e.target.closest && e.target.closest("[data-tip]");
    if (mark) showTip(mark); else tip.hidden = true;
  };
  document.addEventListener("mouseover", tipEvent);
  document.addEventListener("focusin", tipEvent);
  document.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true, capture: true });

  // Auto-submit filter dropdowns: <select data-autosubmit>
  document.querySelectorAll("[data-autosubmit]").forEach((el) =>
    el.addEventListener("change", () => el.form.submit()));
})();
