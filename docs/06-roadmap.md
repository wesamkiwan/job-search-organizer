# 6. Roadmap

Each phase ends with working, tested and documented software and a minor release (0.x).
Tasks within a phase are done on feature branches. Phases are numbered in the order they
are built: the dashboard (now Phase 3) was moved before custom fields (now Phase 4), because
it helps the job search sooner.

## Phase 0: Foundation
- uv project, Django 5.2, split settings, `.env.example`
- ruff, mypy, pytest, pre-commit, GitHub Actions CI
- Tailwind (django-tailwind-cli), HTMX, Alpine, base layout, design tokens, light/dark mode
- Core components (button, card, table, form field, modal, badge, empty state)
- Authentication (login/logout), `UserSettings`
- README with setup instructions

## Phase 1: Tracker MVP
- Company, Contact, JobPosting, Application, PipelineStage (+ default stages), ApplicationEvent, Tag, Task
- Basic Source (name, kind, website; defaults Manual, StepStone, LinkedIn), so every posting
  records where it was found from the start; Phase 6 extends it with adapters and configuration
- Services: create application, change stage (writes events), close application
- Application list (filters, search, sorting), detail page with timeline, kanban board
- Company and contact pages
- Django admin configured

## Phase 2: Documents
- DocumentType, Document, DocumentVersion, ApplicationDocument
- Upload with versioning, duplicate detection (sha256), text extraction
- Attach versions to applications; "used in" view per version; protected downloads

## Phase 3: Dashboard & analytics
- Metrics and widget registries, filter bar, KPI tiles, core charts (funnel, over time, by source/channel, outcomes)
- Goals, customizable layout, drill-down
- Document-version performance, rejection analysis, insights panel

## Phase 4: Flexible fields & views
- FieldDefinition + dynamic forms + validation; BuiltinFieldSetting
- SavedView: configurable table columns, filters, sorting
- Custom fields in list, detail, filters and export
- Choice and number custom fields as dashboard dimensions and measures

## Phase 5: Capture: URL import & bookmarklet
- Inbox and triage workflow (keyboard shortcuts)
- URL import (JSON-LD / meta parsing), deduplication pipeline
- Bookmarklet with token authentication

## Phase 6: Automated sources
- Adapter protocol and registry, SearchProfile, SourceRun, django-q2 scheduling
- Bundesagentur für Arbeit, Arbeitnow, Adzuna adapters
- Generic custom sources (API / RSS / JSON-LD / HTML) with field mapping and a test preview
- Source health widget

## Phase 7: Email alerts
- IMAP reader, parsers for StepStone / LinkedIn / Indeed alert emails

## Phase 8: Hosting readiness
- Docker + compose (web, worker, PostgreSQL), production settings, storage backend
- Backup/restore commands, CSV/JSON export & import

## Later (ideas)
- AI module: match scoring, cover-letter drafts, extraction, insights
- Browser extension, calendar (ICS) export for interviews, German UI translation
- Optional analysis playground (Jupyter/Streamlit) on a read-only database or export, see ADR 0005
