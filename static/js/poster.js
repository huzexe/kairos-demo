// Poster Desk behaviours: theme, dialogs, tabs, toasts, crossing off, sortable and selectable tables.
(function () {
  "use strict";

  // Theme: <button data-theme-set="light|dark|system">
  function setTheme(value) {
    const root = document.documentElement;
    if (value === "system") delete root.dataset.theme;
    else root.dataset.theme = value;
    try {
      if (value === "system") localStorage.removeItem("kairos-theme");
      else localStorage.setItem("kairos-theme", value);
    } catch (e) { /* no storage: the choice lasts for this page */ }
    document.querySelectorAll("[data-theme-set]").forEach((el) =>
      el.setAttribute("aria-pressed", el.dataset.themeSet === value ? "true" : "false"));
    document.dispatchEvent(new CustomEvent("kairos:theme"));
  }
  let current = "system";
  try { current = localStorage.getItem("kairos-theme") || "system"; } catch (e) { /* follow the system */ }
  document.querySelectorAll("[data-theme-set]").forEach((el) => {
    el.setAttribute("aria-pressed", el.dataset.themeSet === current ? "true" : "false");
    el.addEventListener("click", () => setTheme(el.dataset.themeSet));
  });

  // Dialogs: <button data-open="id">, <button data-close>. A click on the backdrop closes too.
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open]");
    if (opener) document.getElementById(opener.dataset.open)?.showModal();
    const closer = e.target.closest("[data-close]");
    if (closer) closer.closest("dialog")?.close();
    if (e.target instanceof HTMLDialogElement) e.target.close();
  });

  // Tabs: role="tablist" with arrow keys
  function initTabs(root) { root.querySelectorAll('[role="tablist"]').forEach((list) => {
    const tabs = [...list.querySelectorAll('[role="tab"]')];
    const select = (tab, focus) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        const panel = document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !on;
      });
      if (focus) tab.focus();
    };
    tabs.forEach((tab, i) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight") select(tabs[(i + 1) % tabs.length], true);
        if (e.key === "ArrowLeft") select(tabs[(i - 1 + tabs.length) % tabs.length], true);
      });
    });
  }); }
  initTabs(document);
  window.kairosTabs = initTabs;

  // A link to something inside a closed tab (#timeline, #invoices) opens that tab first.
  function openHash() {
    const id = location.hash.slice(1);
    const target = id && document.getElementById(id);
    const panel = target && target.closest('[role="tabpanel"]');
    if (!panel) return;
    const tab = document.querySelector(`[role="tab"][aria-controls="${panel.id}"]`);
    if (tab) { tab.click(); target.scrollIntoView(); }
  }
  openHash();
  window.addEventListener("hashchange", openHash);

  // Date presets: <button data-preset-days="3" data-preset-for="follow_up_date">
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-preset-days]");
    if (!btn) return;
    const field = btn.closest("form").querySelector(`[name="${btn.dataset.presetFor}"]`);
    const day = new Date();
    day.setDate(day.getDate() + Number(btn.dataset.presetDays));
    const pad = (n) => String(n).padStart(2, "0");
    if (field) field.value = `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
  });

  // Toasts: bottom-left, with Undo when the action can be reversed
  function toast(text, undo) {
    const box = document.getElementById("toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    const span = document.createElement("span");
    span.className = "toast-text";
    span.textContent = text;
    el.append(span);
    if (undo) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn";
      btn.textContent = "Undo";
      btn.addEventListener("click", () => { undo(); el.remove(); });
      el.append(btn);
    }
    box.append(el);
    setTimeout(() => el.remove(), undo ? 8000 : 4000);
  }
  window.kairosUndoToast = toast;
  if (!window.kairosToast) window.kairosToast = toast;

  // Crossing off: strike, then collapse, then save if the item sits in a form.
  document.querySelectorAll(".crossoff input[type=checkbox]").forEach((box) =>
    box.addEventListener("change", () => {
      const item = box.closest(".crossoff");
      item.classList.toggle("is-done", box.checked);
      item.classList.toggle("is-collapsing", box.checked);
      const form = box.closest("form");
      if (box.checked && form) setTimeout(() => form.submit(), 360);
    }));

  // The rail collapses to icons, and remembers it.
  document.querySelectorAll("[data-rail-toggle]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const root = document.documentElement;
      const collapsed = root.dataset.rail !== "collapsed";
      if (collapsed) root.dataset.rail = "collapsed"; else delete root.dataset.rail;
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      try { localStorage.setItem("kairos-rail", collapsed ? "collapsed" : "open"); } catch (e) { /* lasts for this page */ }
    }));

  // The top bar's light/dark button.
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const root = document.documentElement;
      const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      setTheme(dark ? "light" : "dark");
    }));

  // Close the "+ New" menu when clicking elsewhere.
  document.addEventListener("click", (e) => {
    document.querySelectorAll("details[data-menu][open]").forEach((menu) => { if (!menu.contains(e.target)) menu.open = false; });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details[data-menu][open]").forEach((menu) => {
      menu.open = false;
      menu.querySelector("summary").focus();
    });
  });

  // Keyboard shortcuts: g then a letter, n, /, ?, Ctrl+K.
  const GO = { d: "/", p: "/pipeline/", c: "/clients/", i: "/invoices/", f: "/activity/follow-ups/" };
  let pendingGo = false;
  const typing = (el) => el.closest("input, textarea, select, [contenteditable]");
  const openDialog = (id) => { const d = document.getElementById(id); if (d && !d.open) d.showModal(); };
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openDialog("palette"); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target) || document.querySelector("dialog[open]:not(.sg-dialog-demo)")) return;
    if (pendingGo) {
      pendingGo = false;
      if (GO[e.key]) location.href = GO[e.key];
      return;
    }
    if (e.key === "g") pendingGo = true;
    else if (e.key === "n" && document.body.dataset.newLead) location.href = document.body.dataset.newLead;
    else if (e.key === "?") openDialog("shortcuts");
    else if (e.key === "/") {
      e.preventDefault();
      const field = document.querySelector("main input[type=search]");
      if (field) field.focus(); else openDialog("palette");
    }
  });

  // Sortable tables: <th><button class="sort" data-sort="text|number">
  document.querySelectorAll("button.sort").forEach((btn) =>
    btn.addEventListener("click", () => {
      const th = btn.closest("th");
      const table = th.closest("table");
      const index = th.cellIndex;
      const asc = th.getAttribute("aria-sort") !== "ascending";
      table.querySelectorAll("th[aria-sort]").forEach((h) => h.removeAttribute("aria-sort"));
      th.setAttribute("aria-sort", asc ? "ascending" : "descending");
      const body = table.tBodies[0];
      const value = (row) => row.cells[index].dataset.value ?? row.cells[index].textContent.trim();
      const numeric = btn.dataset.sort === "number";
      [...body.rows]
        .sort((a, b) => {
          const order = numeric ? Number(value(a)) - Number(value(b)) : value(a).localeCompare(value(b));
          return asc ? order : -order;
        })
        .forEach((row) => body.append(row));
    }));

  // Selectable tables: rows with a checkbox reveal the action bar named by data-bar
  document.querySelectorAll("table[data-bar]").forEach((table) => {
    const bar = document.getElementById(table.dataset.bar);
    const count = bar?.querySelector("[data-count]");
    table.addEventListener("change", () => {
      let picked = 0;
      table.querySelectorAll("tbody tr").forEach((row) => {
        const on = row.querySelector("input[type=checkbox]")?.checked;
        row.classList.toggle("is-selected", !!on);
        if (on) picked += 1;
      });
      if (bar) bar.hidden = picked === 0;
      if (count) count.textContent = picked;
    });
  });
})();
