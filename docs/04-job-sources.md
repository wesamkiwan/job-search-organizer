# 4. Job sources

## Policy

StepStone and LinkedIn forbid automated scraping in their terms of service, and both
actively block bots. LinkedIn may restrict accounts that are used for automation. The
app therefore gets their jobs through **user-initiated or officially offered
channels**, and uses automated fetching only where it is allowed. Users can add any
site; whether that site allows automated access is the user's responsibility.

## Channels

| # | Channel | How it works | Typical use |
|---|---|---|---|
| A | **Manual entry** | Form with all fields | Jobs found anywhere |
| B | **Import from URL** | The user pastes a job URL; the app fetches that single page and parses its schema.org `JobPosting` JSON-LD (falls back to Open Graph/meta tags); the form is pre-filled for review | StepStone, Xing, Indeed, company career pages |
| C | **Bookmarklet** (browser extension later) | One click on the job page the user is viewing sends the page's structured data/HTML to the app's token-authenticated endpoint | LinkedIn and any other site |
| D | **Job-alert emails** | Reads a dedicated IMAP mailbox/folder; per-sender parsers extract postings from StepStone/LinkedIn/Indeed alert emails | Automatic discovery from StepStone and LinkedIn |
| E | **Built-in API adapters** | Scheduled searches based on Search Profiles | Bundesagentur für Arbeit Jobsuche API, Arbeitnow, Adzuna (DE) |
| F | **Generic custom sources** | User-defined in the UI (no code): `api` (JSON + field paths), `rss`, `jsonld` (list page + detail pages), `html` (CSS selectors) | Any site the user wants to add |

## Custom source definition (channel F)

Configured in the UI:

- **Request:** URL template with placeholders (`{keywords}`, `{location}`,
  `{radius}`, `{page}`), pagination rule, rate limit, max pages.
- **Extraction:** JSON paths, RSS fields, or CSS selectors for list items and for each
  field (title, company, location, url, date, salary, description…).
- **Detail pages:** optional; fetch each posting's page for the full description (JSON-LD preferred).
- **Field mapping:** extracted values → built-in fields or custom fields, with simple
  transforms (trim, regex, date format, split salary range).
- **Test button:** runs the definition once and previews the parsed postings and
  errors before saving.

## Processing

1. **Normalize:** dates to ISO; salaries to amount/currency/period; locations to city
   and postal code; remote type detected from the text (`remote`, `Homeoffice`, `hybrid`…).
2. **Deduplicate:** canonical URL, source + `external_id`, then a fingerprint of the
   normalized company + title + city. Duplicates update the existing posting and record
   the additional source.
3. **Filter:** excluded keywords, minimum salary, and other profile rules. Filtered
   postings are hidden rather than deleted, so the filters can be tuned.
4. **Store:** `raw_data` is kept so postings can be re-parsed when an adapter improves.
5. **Log:** each run writes a `SourceRun` (counts, errors) for monitoring and for
   source-quality analytics.

## Scheduling

django-q2 runs active search profiles on their schedule while the app (worker) runs. A
`manage.py run_sources` command allows manual runs or OS-level scheduling (Windows Task
Scheduler / cron).
