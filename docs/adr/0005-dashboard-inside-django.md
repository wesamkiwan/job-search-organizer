# ADR 0005: Dashboard is built inside Django (not Streamlit)

- **Status:** Accepted
- **Date:** 2026-11-21

## Context
The analytics dashboard could be built as a separate Streamlit app or inside the Django
application. Streamlit is very fast for building data apps, but it runs as a separate
server with its own UI, state model and (missing) authentication.

## Decision
Build the dashboard inside Django: server-rendered widgets, HTMX for live filtering,
and Apache ECharts for charts. Metric logic lives in `organizer/analytics`.

## Consequences
- One login, one design system, one deployment. The same custom-field definitions and
  selectors are used everywhere.
- Drill-down is a plain link to the filtered application list.
- Charts require a bit more frontend work than Streamlit would.
- A free-form analysis tool (Jupyter/Streamlit reading the database read-only or an
  export) can be added later as an optional side tool; the product doesn't depend on it.
