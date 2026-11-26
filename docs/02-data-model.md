# 2. Data model

All models carry `created_at` / `updated_at`. Entities marked **(custom)** carry a
`custom_data` JSON column for user-defined fields (see
[Flexible fields](#flexible-fields)).

## Overview

```
Company 1───* JobPosting 1───0..1 Application *───1 PipelineStage
   │              │  *                │
   │              │  └──1 Source      ├──* ApplicationEvent (timeline)
   *              │                   ├──* ApplicationDocument *──1 DocumentVersion *──1 Document
Contact *─────────┼──────────────────*┤   (via ApplicationContact)
                  │                   ├──* Interview *──* Contact
                  │                   └──* Task
SearchProfile *──* Source 1──* SourceRun
FieldDefinition, BuiltinFieldSetting, SavedView, Goal, DashboardLayout  (configuration)
```

## Tracking

### Company (custom)
| Field | Notes |
|---|---|
| name, slug | unique slug |
| website, careers_url, linkedin_url | |
| industry | |
| size | choice: 1–10, 11–50, 51–200, 201–1000, 1001–5000, 5000+ |
| headquarters, locations | |
| description, notes | |
| rating | 1–5, personal impression |
| is_recruiting_agency | true for headhunter/agency companies |

### JobPosting (custom)
A posting exists before (and independently of) an application.

| Field | Notes |
|---|---|
| title | |
| company (FK, nullable), company_name_raw | raw name kept until matched to a Company |
| url, canonical_url | |
| source (FK), external_id | id at the source, if any |
| location_text, city, postal_code, country | country defaults to DE |
| remote_type | on-site / hybrid / remote |
| distance_km | optional, from the user's home location |
| employment_type | full-time / part-time / mini-job / internship / working student / freelance / apprenticeship |
| contract_type | permanent (*unbefristet*) / fixed-term (*befristet*) |
| seniority | junior / mid / senior / lead / executive |
| salary_min, salary_max, salary_currency, salary_period | stored as entered; normalized gross/year value computed for analytics |
| posting_language | de / en / … |
| description_html, description_text | full text always stored |
| date_posted, valid_through, found_at | |
| triage_status | new / saved / ignored / applied |
| fingerprint | normalized hash for detecting duplicates across sources |
| raw_data (JSON) | original payload from the source, for re-parsing |
| tags (M2M Tag) | |

### PipelineStage
User-configurable stages. The app's logic depends on the **category**, never on the name.

| Field | Notes |
|---|---|
| name, order, color | |
| category | `saved`, `applied`, `in_progress`, `offer`, `won`, `lost`, `withdrawn` |
| is_default_for_category | |

Default stages: Saved → Applied → Screening → Interviewing → Offer → Accepted, plus
Rejected, Withdrawn and Ghosted (category `lost`).

### Application (custom)
| Field | Notes |
|---|---|
| posting (1:1) | every application has a posting (manual entry creates one) |
| stage (FK PipelineStage) | current stage, kept in sync with events |
| applied_on | date; empty while the application is only saved |
| channel | company portal / email / applicant system / LinkedIn Easy Apply / Xing / recruiter / referral / other |
| referred_by (FK Contact, nullable) | |
| salary_expectation (+ currency) | *Gehaltsvorstellung* as stated in the application |
| earliest_start_date, notice_period | *Kündigungsfrist* |
| priority | low / medium / high |
| interest | 1–5 rating |
| follow_up_on | date |
| closed_at | set when the stage category becomes final (by the services) |
| outcome_stage | stage reached before rejection (for funnel analysis) |
| rejection_reason, rejection_details | choice + free text |
| notes | |
| is_archived | |
| tags (M2M Tag) | |

### ApplicationEvent
The timeline. Status changes are always written through a service that creates an event.

| Field | Notes |
|---|---|
| application (FK) | |
| kind | stage_change / note / email_sent / email_received / call / follow_up / document_sent / other |
| from_stage, to_stage | for stage changes |
| occurred_at | can be backdated |
| summary, details | |

### Interview (custom)
| Field | Notes |
|---|---|
| application (FK), round | |
| kind | phone screen / video / on-site / technical / case study / assessment center / HR / final |
| scheduled_at, duration_minutes, location_or_link | |
| interviewers (M2M Contact) | |
| preparation_notes, questions_asked, feedback | |
| outcome | pending / passed / failed / cancelled |
| self_rating | 1–5 |

### Contact (custom)
| Field | Notes |
|---|---|
| first_name, last_name, job_title | |
| company (FK, nullable) | |
| kind | internal recruiter / external recruiter (headhunter) / hiring manager / employee / referral / other |
| email, phone, linkedin_url | |
| notes, last_contacted_at | |

`ApplicationContact` (through table): application, contact, role.

### Task
Follow-ups and to-dos: `title`, `application (nullable)`, `due_on`, `done_at`, `notes`.

### Tag
`name`, `color`. Used on postings and applications.

## Documents

### DocumentType
Configurable. Defaults: CV (*Lebenslauf*), Cover letter (*Anschreiben*), Reference
(*Arbeitszeugnis*), Certificate (*Zertifikat*), Portfolio, Photo, Other.

### Document
A logical document, e.g. "CV – Backend Developer (EN)".

| Field | Notes |
|---|---|
| title, document_type (FK) | |
| language | de / en / … |
| description, tags | |
| is_archived | |

### DocumentVersion
Never changes after upload.

| Field | Notes |
|---|---|
| document (FK), version_number | auto-incremented per document |
| file | stored via Django's storage layer |
| sha256, size_bytes, mime_type, original_filename | the hash detects re-uploads of the same file |
| extracted_text | plain text pulled from PDF/DOCX (search, future AI) |
| change_notes | |

### ApplicationDocument
`application`, `document_version`, `sent_at`. Unique per (application, document_version).
A version that has been sent can no longer be deleted.

## Discovery

### Source
Phase 1 creates a basic version (name, kind, website, is_enabled) with the default sources
Manual, StepStone and LinkedIn; `adapter`, `config` and `field_mapping` follow in Phase 6.

| Field | Notes |
|---|---|
| name, kind | `manual`, `url_import`, `bookmarklet`, `email_alert`, `api`, `rss`, `jsonld`, `html` |
| adapter | built-in adapter key (e.g. `bundesagentur`, `arbeitnow`, `adzuna`) or `generic` |
| config (JSON) | adapter settings: URL templates, CSS selectors, credentials *reference* (never secrets in the database), rate limit |
| field_mapping (JSON) | source field → built-in or custom field |
| is_enabled | |

### SearchProfile
| Field | Notes |
|---|---|
| name | |
| keywords, excluded_keywords | |
| locations, radius_km | |
| remote_types, employment_types, contract_types | |
| min_salary | |
| sources (M2M Source) | |
| schedule | e.g. every 6 h / daily |
| is_active, last_run_at | |

### SourceRun
`source`, `search_profile`, `started_at`, `finished_at`, `status`, `found_count`,
`new_count`, `duplicate_count`, `error_log`. Used for monitoring and for source-quality analytics.

## Flexible fields

### FieldDefinition (custom fields)
| Field | Notes |
|---|---|
| entity | application / posting / company / contact / interview |
| key, label, help_text | `key` is immutable once created |
| field_type | text, long_text, number, money, date, boolean, single_choice, multi_choice, url, email, rating |
| choices (JSON) | for choice types |
| is_required, default_value | |
| order, show_in_table, is_filterable | |
| is_active | deactivating hides the field but keeps its data; deleting asks for confirmation |

Values live in each entity's `custom_data` JSON column, keyed by `key`, and are
validated by forms that are built from these definitions. Choice and number custom
fields automatically become available as **dimensions and measures in the dashboard**.
See [ADR 0002](adr/0002-custom-fields-json.md).

### BuiltinFieldSetting
`entity`, `field_name`, `label_override`, `is_hidden`. Built-in fields can be renamed
or hidden, but not deleted.

### SavedView
`entity`, `name`, `columns` (ordered list of built-in and custom field keys), `filters`,
`sort`, `is_default`. Drives the configurable tables.

## Analytics configuration

- **Goal:** `metric`, `target`, `period` (week / month), `is_active`. Example: 10 applications per week.
- **DashboardLayout:** an ordered list of widgets with their size and settings (JSON). See [Dashboard](05-dashboard.md).
- **UserSettings:** home location (for distance), default currency, the number of days without a response after which an application counts as ghosted (default 30), date format.
