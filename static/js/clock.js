// Live clock in the top bar (templates/partials/clock.html).
//
// Django already writes the current date and time into the page, so it is correct even
// before this script runs. This script only keeps it up to date while the page stays
// open: it updates exactly when the minute changes, then once a minute.
(function () {
  "use strict";

  const pad = (number) => String(number).padStart(2, "0");

  // The user's date format from Settings, as a Django format string: "d.m.Y", "Y-m-d"
  // or "d/m/Y". d = day, m = month, Y = four-digit year; other characters stay as they are.
  function formatDate(date, format) {
    return format.replace(/[dmY]/g, (letter) => {
      if (letter === "d") return pad(date.getDate());
      if (letter === "m") return pad(date.getMonth() + 1); // JavaScript months start at 0
      return String(date.getFullYear());
    });
  }

  function render(element) {
    const now = new Date();
    const weekday = now.toLocaleDateString("en-GB", { weekday: "short" }); // "Fri"
    const date = formatDate(now, element.dataset.dateFormat);
    const time = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    element.textContent = `${weekday}, ${date} · ${time}`;
    element.setAttribute("datetime", now.toISOString());
  }

  function start() {
    const element = document.querySelector("[data-clock]");
    if (!element) return;
    const tick = () => {
      render(element);
      // Wait until the next full minute (not just 60 s from now), so the clock never
      // lags behind the real minute change.
      setTimeout(tick, 60000 - (Date.now() % 60000));
    };
    tick();
  }

  start(); // the script is loaded with "defer", so the HTML is already there
})();
