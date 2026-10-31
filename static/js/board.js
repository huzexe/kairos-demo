/* Kanban board: drag cards between stages and save each move.
   Moving a card to Lost first asks for a lost reason; cancelling puts the
   card back where it was. */
(function () {
  "use strict";
  const board = document.getElementById("board");
  if (!board || board.hasAttribute("data-readonly") || !window.Sortable) return;

  const moveUrl = (id) => board.dataset.moveUrl.replace("/0/", "/" + id + "/");
  const dialog = document.getElementById("lost-dialog");
  const lostForm = document.getElementById("lost-form");

  // Same format as the server: "PKR 450,000 · USD 2,000"
  function formatTotals(totals) {
    return Object.keys(totals).sort().filter((c) => totals[c] > 0).map((code) => {
      const n = totals[code];
      const whole = Math.abs(n - Math.round(n)) < 0.005;
      return code + " " + n.toLocaleString("en-US", {
        minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2,
      });
    }).join(" · ");
  }

  function refreshColumn(list) {
    const column = list.closest(".column");
    const cards = list.querySelectorAll(".lead-card");
    const totals = {};
    cards.forEach((card) => {
      const value = parseFloat(card.dataset.value);
      if (!isNaN(value)) totals[card.dataset.currency] = (totals[card.dataset.currency] || 0) + value;
    });
    column.querySelector("[data-count]").textContent = cards.length;
    column.querySelector("[data-total]").textContent = formatTotals(totals);
  }

  function putBack(evt) {
    const ref = evt.from.children[evt.oldIndex] || null;
    evt.from.insertBefore(evt.item, ref);
    refreshColumn(evt.from);
    refreshColumn(evt.to);
  }

  // Ask for the lost reason. Resolves with FormData, or null if cancelled.
  function askLostReason() {
    return new Promise((resolve) => {
      lostForm.reset();
      const finish = (value) => {
        lostForm.removeEventListener("submit", onSubmit);
        dialog.removeEventListener("close", onClose);
        cancelBtn.removeEventListener("click", onCancel);
        resolve(value);
      };
      const onSubmit = (e) => {
        e.preventDefault();
        if (!lostForm.reportValidity()) return;
        const data = new FormData(lostForm);
        dialog.close("done");
        finish(data);
      };
      const onClose = () => { if (dialog.returnValue !== "done") finish(null); };
      const onCancel = () => dialog.close("cancel");
      const cancelBtn = lostForm.querySelector("[data-cancel]");
      lostForm.addEventListener("submit", onSubmit);
      dialog.addEventListener("close", onClose);
      cancelBtn.addEventListener("click", onCancel);
      dialog.returnValue = "";
      dialog.showModal();
    });
  }

  async function save(evt) {
    const card = evt.item;
    const stage = evt.to.dataset.stage;
    const sameColumn = evt.from === evt.to;
    if (sameColumn && evt.oldIndex === evt.newIndex) return;

    let data = new FormData();
    if (stage === "lost" && !sameColumn) {
      const answer = await askLostReason();
      if (!answer) { putBack(evt); return; }
      data = answer;
    }
    data.set("stage", stage);
    const next = card.nextElementSibling;
    if (next && next.dataset.id) data.set("before_id", next.dataset.id);

    card.classList.add("is-saving");
    try {
      const res = await fetch(moveUrl(card.dataset.id), {
        method: "POST",
        body: data,
        headers: { "X-CSRFToken": window.kairosCsrf(), Accept: "application/json" },
        credentials: "same-origin",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body.ok) throw new Error(body.error || "Couldn’t save that move.");
      if (!sameColumn) {
        // The card changed stage: reload it so tags, age and lost reason are current.
        window.kairosToast("Moved to " + body.stage_label + ".");
        const age = card.querySelector(".age");
        if (age) { age.classList.remove("is-stale"); age.lastChild.textContent = "Today"; }
        const why = card.querySelector(".lost-why");
        if (why && stage !== "lost") why.remove();
        if (stage === "lost") {
          const picked = dialog.querySelector("input[name=lost_reason]:checked");
          if (picked) {
            const el = why || document.createElement("div");
            el.className = "lost-why";
            el.textContent = picked.parentElement.textContent.trim();
            if (!why) card.querySelector(".foot").before(el);
          }
        }
        const junk = card.querySelector(".junk-btn");
        if (junk && stage === "won") junk.closest("form").remove();
        const wonRow = card.querySelector(".won-row");
        if (wonRow && stage !== "won") wonRow.remove();
        if (stage === "won" && body.convert_url && !wonRow) {
          const row = document.createElement("div");
          row.className = "won-row";
          row.innerHTML = '<a class="won-convert">Convert to client <svg class="icon"><use href="#i-arrow-right"/></svg></a>';
          row.querySelector("a").href = body.convert_url;
          card.querySelector(".foot").before(row);
        }
      }
    } catch (err) {
      putBack(evt);
      window.kairosToast(err.message || "Couldn’t save that move. Check your connection and try again.", "error");
    } finally {
      card.classList.remove("is-saving");
    }
  }

  board.querySelectorAll(".cards").forEach((list) => {
    Sortable.create(list, {
      group: "pipeline",
      animation: 160,
      delay: 160,              // on touch screens, hold briefly to drag
      delayOnTouchOnly: true,  // so swiping still scrolls the board
      filter: ".junk-btn",
      preventOnFilter: false,
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      dragClass: "sortable-drag",
      onEnd: (evt) => {
        refreshColumn(evt.from);
        if (evt.to !== evt.from) refreshColumn(evt.to);
        save(evt);
      },
    });
  });

  // Don't open the lead when a drag ends on its link. The flag only lives
  // until the drag's own trailing click, so later clicks work normally.
  let dragging = false;
  board.addEventListener("dragstart", () => { dragging = true; });
  board.addEventListener("dragend", () => { setTimeout(() => { dragging = false; }, 0); });
  board.addEventListener("click", (e) => {
    if (dragging && e.target.closest(".lead-card")) e.preventDefault();
  }, true);
})();
