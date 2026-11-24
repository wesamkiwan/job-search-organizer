// Light/dark theme toggle.
//
// The starting theme is already set by the small inline script in base.html <head>
// (it must run before the page is drawn, otherwise dark-mode users see a white flash).
// This file only handles changes: clicks on the toggle button and OS setting changes.
(function () {
  "use strict";

  const STORAGE_KEY = "theme";
  const root = document.documentElement; // the <html> element
  const osDark = window.matchMedia("(prefers-color-scheme: dark)");

  function storedTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY); // "light", "dark" or null (no choice yet)
    } catch {
      return null; // storage can be blocked (e.g. strict privacy settings)
    }
  }

  function applyTheme(theme, remember) {
    root.dataset.theme = theme; // sets <html data-theme="..."> and the CSS tokens follow
    if (remember) {
      try {
        localStorage.setItem(STORAGE_KEY, theme);
      } catch {
        // Not saved, but the theme still changes for this page.
      }
    }
    // Tell screen readers whether "Dark mode" is on.
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      button.setAttribute("aria-pressed", String(theme === "dark"));
    }
  }

  // One listener on the whole document ("event delegation"): it also works for buttons
  // that are added to the page later, e.g. by HTMX.
  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-theme-toggle]")) return;
    applyTheme(root.dataset.theme === "dark" ? "light" : "dark", true);
  });

  // If the user never chose a theme, follow the OS when it switches (e.g. at sunset).
  osDark.addEventListener("change", (event) => {
    if (storedTheme() === null) applyTheme(event.matches ? "dark" : "light", false);
  });

  // Sync the button state with the theme the inline script picked.
  applyTheme(root.dataset.theme, false);
})();
