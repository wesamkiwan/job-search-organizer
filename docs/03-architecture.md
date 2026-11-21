# 3. Architecture

## Technology stack

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.13 | current, typed |
| Framework | Django 5.2 LTS | long-term support, batteries included, admin |
| Dependencies | uv (`pyproject.toml` + `uv.lock`) | fast, reproducible |
| Database | SQLite (local) → PostgreSQL (hosted) | zero setup now; changed through config only |
| Frontend | Server-rendered templates + HTMX + Alpine.js | interactive UI without a separate JavaScript application |
| Styling | Tailwind CSS via `django-tailwind-cli` | no Node.js needed; design tokens; consistent components |
| Charts | Apache ECharts (vendored) | rich chart types, themable, no build step |
| Background jobs | django-q2 (database as broker) | runs on Windows, no Redis needed |
| HTTP / parsing | httpx, selectolax/BeautifulSoup, extruct (JSON-LD) | Playwright only if really needed |
| Document text | pypdf, python-docx | text extraction for search and future AI |
| Configuration | django-environ, `.env` | twelve-factor config |
| Quality | ruff, mypy (django-stubs), pytest, pytest-django, factory-boy, coverage | |
| Automation | pre-commit, GitHub Actions CI | |
| Deployment (later) | Docker + docker-compose, gunicorn, whitenoise | |

## Repository layout

```
job-search-organizer/
├── config/                  # Django project: settings/, urls.py, wsgi.py, asgi.py
│   └── settings/            # base.py, local.py, test.py, production.py
├── organizer/               # all Django apps live in this package
│   ├── core/                # base models, user settings, shared UI components, utils
│   ├── companies/           # Company, Contact
│   ├── jobs/                # JobPosting, Tag, inbox/triage
│   ├── applications/        # Application, PipelineStage, events, interviews, tasks
│   ├── documents/           # DocumentType, Document, DocumentVersion
│   ├── customfields/        # FieldDefinition, BuiltinFieldSetting, SavedView, dynamic forms
│   ├── sources/             # Source, SearchProfile, SourceRun, adapters, import pipeline
│   └── analytics/           # metrics, widgets, goals, dashboard
├── templates/               # base layout + components/ (buttons, cards, tables, modals…)
├── static/                  # Tailwind input CSS, vendored JS (htmx, alpine, echarts)
├── tests/                   # pytest; mirrors organizer/ structure
├── docs/                    # this specification + ADRs
├── .github/workflows/       # CI
├── pyproject.toml, uv.lock, .env.example, .pre-commit-config.yaml
└── manage.py
```

## Layers inside each app

```
views (thin: HTTP, permissions, templates/HTMX partials)
  │
  ├── forms           input validation (including dynamic custom-field forms)
  ├── services.py     write operations and business rules (e.g. change_stage(), import_posting())
  └── selectors.py    read queries reused by views, the dashboard and exports
        │
      models          data and invariants
```

Rules:

- Views never contain business logic. Services are plain functions with type hints and
  are unit tested.
- Database writes that change several rows run inside `transaction.atomic()`.
- Cross-app interaction goes through services/selectors, not other apps' internals.

## Job source pipeline

```
Adapter.fetch(profile) ──► RawPosting ──► normalize ──► deduplicate ──► apply field mapping ──► JobPosting (Inbox)
                                           (dates,       (fingerprint:
                                            salary,      company + title
                                            location)    + location, URL)
```

- Every channel implements one `SourceAdapter` protocol (`fetch`, `test`). Built-in
  adapters and the generic configurable adapters (API/RSS/JSON-LD/HTML) are registered
  in an adapter registry. See [Job sources](04-job-sources.md).
- Requests are polite: rate limits per source, an identifying User-Agent, timeouts,
  retries with backoff.
- Adapters are tested against **recorded fixtures** (saved responses), never against
  live sites in CI.

## Analytics

A **metrics registry** (`analytics/metrics.py`): each metric is a function that takes a
filter context (date range, comparison period, filters) and returns typed data. A
**widget registry** maps widgets to metrics and chart types. Widgets render as HTMX
partials; chart data is served as JSON to ECharts. Expensive aggregations are cached
and invalidated on writes. See [Dashboard](05-dashboard.md).

## UI and design system

- `templates/components/`: reusable components (button, card, KPI tile, table, badge,
  modal, form field, empty state, chart container). Pages are assembled from these, so
  design improvements are made in one place.
- Design tokens (colors, spacing, radius, typography) are CSS variables, mapped into
  Tailwind. They drive light/dark mode and the chart theme.
- Accessible by default: semantic HTML, keyboard navigation, focus states, sufficient contrast.
- Responsive layout, usable on a phone once hosted.

## Security and privacy

- Login required on every page, even locally.
- Secrets only in `.env` (never in the database or the repository). A source's `config`
  refers to a secret by environment-variable name.
- `.gitignore` excludes `db.sqlite3`, `media/`, `.env`, backups.
- Production settings: `DEBUG=False`, HTTPS, secure cookies, `ALLOWED_HOSTS`, CSP.
- Uploads: file type and size checks; files are served through an authenticated view,
  never as public media.
- Bookmarklet endpoint: token-authenticated, CSRF-safe, accepts only posting data.

## Prepared for AI (not built yet)

- Full posting text and extracted document text are stored.
- An `organizer/ai/` app can later add services (match scoring, cover letter drafts,
  extraction) that use existing selectors/services without changing them.
- A provider interface sits behind settings, so no AI SDK is a hard dependency.

## Prepared for hosting

- Settings split per environment, all values from the environment.
- `DATABASE_URL` selects SQLite or PostgreSQL.
- Storage through Django's `STORAGES` setting (local disk → S3-compatible storage).
- A Dockerfile and docker-compose (web + worker + db) are added in the hosting phase.

## Engineering practices

- Conventional Commits; small, focused commits; feature branches + pull requests once hosted on GitHub.
- Code checks: ruff (lint + format), mypy, and pytest with coverage; enforced by pre-commit and CI.
- Tests: services, selectors and adapters are unit tested; views and HTMX flows have integration tests; fixtures are built with factory-boy.
- Migrations reviewed and committed; data migrations for default stages and document types.
- Backup and export: `manage.py backup` (database + media archive) and CSV/JSON export.
- Decisions recorded as ADRs in `docs/adr/`.
