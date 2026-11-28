# ADR 0007: Dashboard charts drawn as server-rendered HTML

- **Status:** Accepted (replaces the "Apache ECharts" choice in the architecture document)
- **Date:** 2026-11-28

## Context
The architecture document planned Apache ECharts (vendored, about 1 MB of JavaScript)
for the dashboard: chart data as JSON, drawn in the browser, themed from the design
tokens. When the dashboard was built, the charts it actually needs turned out to be
simple forms:

- KPI tiles and a goal meter (numbers, not charts),
- horizontal bar lists (funnel, pipeline by stage, performance by source/channel/version),
- columns per week or weekday, a calendar heatmap,
- one segmented bar (outcomes) and small range plots (salaries).

Options considered:

- **ECharts:** many chart types, built-in tooltips and PNG export. But 1 MB of JavaScript,
  charts must be re-themed by script when light/dark mode changes, every HTMX swap must
  re-initialise them, and the numbers live in a canvas (not text), which needs a separate
  table for accessibility and is hard to test.
- **A smaller library (Chart.js and similar):** same trade-offs, smaller file.
- **Server-rendered HTML/SVG:** each mark is a `div` whose width or height is a
  percentage, styled with Tailwind classes from the design tokens.

## Decision
Draw the dashboard charts on the server as plain HTML (Django templates), with the chart
colours as design tokens (`--chart-1` … `--chart-5`, `--chart-heat-1` … `--chart-heat-5`)
validated for colour-blind separation and contrast against the light and dark surfaces.

- Every widget returns its data as a `Table` too: shown under the chart ("Show as table")
  and used for the CSV export.
- Values are printed as text beside or on the marks; tooltips only repeat them.
- Marks link to the applications behind them (drill-down).

## Consequences
- No chart library to vendor or update; light/dark mode and HTMX updates work without any
  chart code; every value is text (accessible, searchable, testable with `assertContains`).
- Fewer chart types are available. Line charts, box plots or scatter plots would need
  hand-written SVG; if the dashboard ever needs many of those, a library can be added for
  just those widgets (the widget registry allows it).
- "Export chart as PNG" from the dashboard spec is not built; the CSV export and the
  browser's own screenshot/print cover the need for now.
