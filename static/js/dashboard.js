// Dashboard "Customize" mode: drag widgets into another order, switch them between half
// and full width, or remove them. Every change is sent to Django right away (POST JSON to
// data-layout-url); Django checks it (analytics/layout.py) and saves the layout.
//
// The filter bar replaces #dashboard-content with HTMX, so everything here is set up
// again after each swap (htmx:afterSettle), on the new elements.
(function () {
  "use strict";

  let sortable = null;

  function setUp() {
    const content = document.getElementById("dashboard-content");
    const grid = document.getElementById("dashboard-grid");
    if (!content || !grid || !window.Sortable) return;
    const status = document.getElementById("layout-status");

    function showError(text) {
      status.textContent = text;
      status.hidden = false;
    }

    // The current layout, read from the page: the widgets in their DOM order.
    function layout() {
      return [...grid.querySelectorAll("[data-widget]")].map((section) => ({
        key: section.dataset.widget,
        size: section.dataset.size,
      }));
    }

    async function save() {
      status.hidden = true;
      const response = await fetch(content.dataset.layoutUrl, {
        method: "POST",
        headers: { "X-CSRFToken": content.dataset.csrfToken, "Content-Type": "application/json" },
        body: JSON.stringify({ widgets: layout() }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "The layout could not be saved.");
      }
    }

    if (sortable) sortable.destroy(); // the old grid was replaced by HTMX
    sortable = Sortable.create(grid, {
      handle: "[data-drag-handle]", // only the grip moves a widget (charts stay clickable)
      draggable: "[data-widget]",
      animation: 150,
      ghostClass: "opacity-40",
      onEnd(event) {
        if (event.oldIndex === event.newIndex) return;
        save().catch((error) => showError(error.message));
      },
    });

    // Event delegation: one listener on the grid handles the buttons of every widget.
    grid.addEventListener("click", (event) => {
      const section = event.target.closest("[data-widget]");
      if (!section) return;

      if (event.target.closest("[data-size-toggle]")) {
        const full = section.dataset.size !== "full";
        section.dataset.size = full ? "full" : "half";
        section.classList.toggle("lg:col-span-2", full);
        section.querySelector("[data-size-label]").textContent = full ? "Half width" : "Full width";
        save().catch((error) => showError(error.message));
      }

      if (event.target.closest("[data-remove]")) {
        section.remove();
        // Reload, so the removed widget appears under "Add a widget".
        save()
          .then(() => window.location.reload())
          .catch((error) => showError(error.message));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", setUp);
  document.addEventListener("htmx:afterSettle", (event) => {
    if (event.target.id === "dashboard-content") setUp();
  });
})();
