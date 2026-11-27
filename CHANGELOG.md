# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Each roadmap phase is a
minor release while the project is in early development (0.x).

## [Unreleased]

## [0.3.0] - 2026-11-27

Phase 2: documents.

### Added

- Documents with versions: document types (7 defaults), documents, immutable versions and a
  record of which version was sent with which application, each with an admin.
- Upload checks (PDF, DOCX, PNG, JPEG; by extension and file content; 10 MB limit) and
  duplicate detection by SHA-256 fingerprint.
- Sent versions can't be deleted; sending a version adds an entry to the application's
  timeline.
- Text and page count read from PDF and Word files at upload (page counts also for
  images), and an `extract_document_text` command for existing versions.
- Document library pages: list with search (also inside the files) and filters, add a
  document with its first file, detail page with the version history (size, date and
  pages per version), upload of new versions, edit, archive and delete.
- Downloads and previews only through a login-protected view, under the original file
  name; files are never served as public media URLs.
- "Documents sent" on the application page: record which versions you sent and when
  (with a timeline entry), and remove a record made by mistake.
- "Used in" on the document page: the applications each version was sent with, with
  their company, date and stage.

## [0.2.0] - 2026-11-27

Phase 1: the application tracker.

### Added

- Companies and contacts, job sources (default Manual, StepStone, LinkedIn), tags and job
  postings, each with an admin.
- Applications with customizable pipeline stages (9 defaults; logic depends on the stage
  category, not its name), a timeline of events, and tasks.
- Service layer for creating, moving, closing and deleting applications and for timeline
  entries, each in one transaction, with tested business rules (backdating, no future dates,
  timeline order, outcome stage, reopening).
- Application list with live search, filters (stage, status, priority, location, work mode),
  sortable columns incl. salary expectation, and pagination.
- Add, edit and detail pages for applications; stage changes, notes and closing from the
  detail page.
- Kanban board with drag and drop between stages (mouse and touch).
- Company and contact pages with search, details and related applications.
- Live date and time in the top bar.
- `seed_demo_data` management command with invented example data.

## [0.1.0] - 2026-11-25

Phase 0: the foundation.

### Added

- uv project with Django 5.2, split settings and `.env` configuration.
- ruff, mypy, pytest, pre-commit and GitHub Actions CI.
- Tailwind CSS design tokens with light and dark mode, HTMX and Alpine.js, base layout and
  UI components (django-cotton).
- Login and logout with a custom user model, and a settings page.
- README and MIT license.

[Unreleased]: https://github.com/wesamkiwan/job-search-organizer/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/wesamkiwan/job-search-organizer/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/wesamkiwan/job-search-organizer/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/wesamkiwan/job-search-organizer/releases/tag/v0.1.0
