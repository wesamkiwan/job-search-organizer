# Job Search Organizer

[![CI](https://github.com/wesamkiwan/job-search-organizer/actions/workflows/ci.yaml/badge.svg)](https://github.com/wesamkiwan/job-search-organizer/actions/workflows/ci.yaml)
![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![Django 5.2 LTS](https://img.shields.io/badge/django-5.2%20LTS-green)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

A personal, local-first Django application to organize a job search in Germany: collect
postings from StepStone, LinkedIn and any other source, track every application and the
exact documents sent, and improve the search with a dynamic analytics dashboard.

> **Status:** Phase 1 (application tracker) is complete: applications with a timeline and
> pipeline stages, a kanban board, companies and contacts.
> [Phase 2](docs/06-roadmap.md) (documents) is complete as well: a document library with
> versions, and a record of exactly which version was sent with which application.

## Features

**Available now**
- Applications: add, edit and track them through customizable pipeline stages (saved,
  applied, screening, interviewing, offer, accepted, rejected, ghosted, withdrawn)
- A timeline per application: stage changes, notes, calls and emails, with backdating
- Application list with live search, filters (stage, status, priority, location, work
  mode), sorting and your salary expectation next to the advertised range
- Kanban board: drag applications between stages (mouse or touch)
- Companies and contacts (recruiters, hiring managers, referrals) with their own pages
- Document library: CVs, cover letters and references with versions (PDF, Word, PNG,
  JPEG), duplicate detection, search inside the files, preview and private downloads
- Which version was sent where: record the documents sent with each application, and
  see for every version which applications it was used in
- Business rules in a tested service layer (timeline, closing, outcomes stay consistent)
- Login required on every page, settings (currency, date format, "ghosted" threshold),
  light and dark mode, responsive layout, demo data command

**Planned** (see the [roadmap](docs/06-roadmap.md))
- Custom fields and saved table views
- Analytics dashboard: funnel, response rates, sources, goals
- Import from URLs, a bookmarklet, job APIs and alert emails

## Tech stack

| Area | Tools |
|---|---|
| Backend | Python 3.13, Django 5.2 LTS, SQLite (PostgreSQL later) |
| Frontend | Server-rendered templates, HTMX, Alpine.js, Tailwind CSS v4 (no Node.js), django-cotton components |
| Quality | pytest + pytest-django + factory-boy, coverage (pytest-cov), ruff (lint + format), mypy + django-stubs, pre-commit |
| Automation | GitHub Actions CI on every pull request and push to `main` |
| Tooling | [uv](https://docs.astral.sh/uv/) for Python, dependencies and the lockfile |

## Getting started

### Prerequisites
- [uv](https://docs.astral.sh/uv/getting-started/installation/). It also installs the right
  Python version (3.13) automatically.
- [Git](https://git-scm.com/)

### Setup

```bash
# 1. Get the code
git clone https://github.com/wesamkiwan/job-search-organizer.git
cd job-search-organizer

# 2. Install Python and all dependencies (exact versions from uv.lock)
uv sync

# 3. Optional: local configuration. Works without it; see the comments in the file.
cp .env.example .env

# 4. Create the database and your login
uv run python manage.py migrate
uv run python manage.py createsuperuser

# 5. Start the development server (also rebuilds the CSS when templates change)
uv run python manage.py tailwind runserver
```

Open http://127.0.0.1:8000/ and log in with the user from step 4.

The first `tailwind runserver` downloads the Tailwind CSS command-line tool once (pinned
version, no Node.js needed).

**Optional: demo data.** To try the app with made-up example applications (invented
companies, backdated histories), run:

```bash
uv run python manage.py seed_demo_data          # add ~20 demo applications
uv run python manage.py seed_demo_data --reset  # remove them again and recreate them
```

Demo rows are marked, so `--reset` never touches your own data. The command only runs with
`DEBUG` on.

**Windows:** if printing in the Django shell fails with `UnicodeEncodeError`, switch Python
to UTF-8 mode once with `setx PYTHONUTF8 1` and restart the terminal.

## Development

### Checks

```bash
uv run pytest               # tests
uv run pytest --cov         # tests + coverage report (which lines no test runs)
uv run ruff check .         # lint
uv run ruff format .        # format
uv run mypy .               # type check
```

CI runs the same checks on every pull request.

### Pre-commit hooks

```bash
uv run pre-commit install   # once per clone
```

After that, ruff, mypy and some file checks run automatically on every `git commit`.

### Workflow
- Every change is made on a branch (e.g. `feature/applications`) and merged through a pull
  request.
- `main` is protected: merging requires a pull request and a green CI run.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, ...).

### Project layout

```
config/          Django project: settings (base / local / test / production), URLs
organizer/       Django apps (core, accounts, companies, sources, jobs, applications, documents)
templates/       Base layout, partials, UI components, icons
static/          Fonts, JavaScript, vendored HTMX + Alpine
assets/css/      Tailwind source with the design tokens
tests/           pytest tests
docs/            Specification and architecture decision records
```

## Documentation

1. [Concept](docs/01-concept.md): vision, scope, workflow, screens
2. [Data model](docs/02-data-model.md): entities, fields, flexible custom fields
3. [Architecture](docs/03-architecture.md): stack, layout, layers, security, practices
4. [Job sources](docs/04-job-sources.md): channels, custom sources, import pipeline
5. [Dashboard & analytics](docs/05-dashboard.md): KPIs, charts, insights
6. [Roadmap](docs/06-roadmap.md): phases
7. [Architecture decision records](docs/adr/): why key decisions were made

What changed in each version: [CHANGELOG.md](CHANGELOG.md).

## Privacy

All personal data (database, uploaded documents, `.env`) stays on your machine and is
excluded from version control.

## License

[MIT](LICENSE)
