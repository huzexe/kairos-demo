/* Add / remove rows in a Django formset.
   Markup: a container [data-rows="prefix"], a <template id="prefix-template">
   holding one empty row with __prefix__ placeholders, and a button
   [data-add-row="prefix"]. Each row's DELETE checkbox sits inside .row-remove. */
(function () {
  "use strict";

  function hideIfDeleted(row) {
    const del = row.querySelector("input[name$='-DELETE']");
    if (del && del.checked) row.hidden = true;
  }

  document.addEventListener("click", (e) => {
    const add = e.target.closest("[data-add-row]");
    if (add) {
      const prefix = add.dataset.addRow;
      const total = document.getElementById("id_" + prefix + "-TOTAL_FORMS");
      const max = document.getElementById("id_" + prefix + "-MAX_NUM_FORMS");
      const index = parseInt(total.value, 10);
      if (max && index >= parseInt(max.value, 10)) return;
      const html = document.getElementById(prefix + "-template").innerHTML.replace(/__prefix__/g, index);
      const holder = document.createElement("div");
      holder.innerHTML = html.trim();
      const row = holder.firstElementChild;
      document.querySelector('[data-rows="' + prefix + '"]').appendChild(row);
      total.value = index + 1;
      const first = row.querySelector("input:not([type=hidden]):not([type=checkbox]), select");
      if (first) first.focus();
      document.dispatchEvent(new CustomEvent("rows:added", { detail: row }));
    }
  });

  // Ticking the hidden DELETE box (via the trash icon) hides the row.
  document.addEventListener("change", (e) => {
    if (e.target.matches("input[name$='-DELETE']")) {
      hideIfDeleted(e.target.closest("[data-row]"));
      document.dispatchEvent(new CustomEvent("rows:changed"));
    }
  });
  document.querySelectorAll("[data-row]").forEach(hideIfDeleted);
})();
