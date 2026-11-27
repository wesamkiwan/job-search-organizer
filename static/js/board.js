// Kanban board: drag a card to another column to change the application's stage.
//
// SortableJS (static/vendor/sortablejs) does the dragging, with mouse AND touch. After a
// drop we tell Django (POST to the card's data-move-url). Django runs the same service as
// the stage form on the detail page (change_stage), so the timeline is written too.
// If Django refuses (e.g. a business rule), the card goes back where it was.
(function () {
  "use strict";

  const board = document.querySelector("[data-board]");
  if (!board || !window.Sortable) return;

  const csrfToken = board.dataset.csrfToken; // Django refuses POSTs without it (CSRF)
  const statusBox = document.getElementById("board-status");
  let hideTimer;

  // Short message at the bottom of the screen; also read out by screen readers.
  function announce(text, isError) {
    statusBox.textContent = text;
    statusBox.dataset.tone = isError ? "danger" : "success";
    statusBox.hidden = false;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { statusBox.hidden = true; }, 4000);
  }

  // Each column header shows how many cards it has; an empty column shows a hint.
  function updateCounts() {
    board.querySelectorAll("[data-column]").forEach((column) => {
      const cards = column.querySelectorAll("[data-card]").length;
      column.querySelector("[data-count]").textContent = cards;
      column.querySelector("[data-empty]").hidden = cards > 0;
    });
  }

  async function saveMove(card, stageId) {
    const response = await fetch(card.dataset.moveUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
      body: new URLSearchParams({ stage: stageId }), // sent like a normal form
    });
    const data = await response.json().catch(() => ({})); // {} if the answer isn't JSON
    if (!response.ok) throw new Error(data.error || "The application could not be moved.");
    return data.message;
  }

  board.querySelectorAll("[data-cards]").forEach((list) => {
    Sortable.create(list, {
      group: "board", // cards can move between all lists of this group
      sort: false, // no reordering inside a column: the order is "most recently active"
      draggable: "[data-card]",
      animation: 150,
      ghostClass: "opacity-40", // the placeholder where the card will land
      onEnd(event) {
        if (event.from === event.to) return; // dropped back into the same column
        const card = event.item;
        saveMove(card, event.to.dataset.stageId)
          .then((message) => announce(message, false))
          .catch((error) => {
            // Put the card back at its old position, then explain why.
            event.from.insertBefore(card, event.from.children[event.oldIndex] || null);
            announce(error.message, true);
          })
          .finally(updateCounts);
      },
    });
  });
})();
