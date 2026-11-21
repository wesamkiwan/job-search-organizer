# 1. Concept

## Vision

A personal, local-first web application that organizes a job search end to end:
**discover** job postings, **triage** them, **track** applications and the exact
documents sent, and **analyze** the whole process to improve it continuously.

## Scope

| In scope | Out of scope (for now) |
|---|---|
| Single user, data stored locally | Multi-user / teams |
| German job market first, generic by design | Applying to jobs automatically |
| Manual entry, URL import, bookmarklet, email alerts, automated sources | Crawling sites whose terms forbid it |
| Flexible, user-defined fields and table views | AI features (architecture is prepared for them) |
| Analytics dashboard with KPIs and charts | Mobile app (responsive web UI instead) |

Constraints:

- Runs locally first (Windows dev machine), hostable later with configuration changes only.
- English UI, built translation-ready (Django i18n).
- Personal data (database, uploaded documents, secrets) never leaves the machine and is
  never committed to the repository.

## Core workflow

```
 DISCOVER ──────────► TRIAGE ──────────► TRACK ──────────► ANALYZE
 sources, URL import   inbox: ignore /     application,      dashboard: KPIs,
 bookmarklet, emails   save / apply        documents,        funnel, trends,
 manual entry                              timeline,         what works best
                                           interviews
```

1. **Discover.** Job postings arrive in the **Inbox** from any channel (see
   [Job sources](04-job-sources.md)).
2. **Triage.** For each posting: *Ignore*, *Save for later*, or *Apply*. Duplicates
   across channels are merged automatically.
3. **Track.** An application links a posting to the exact document versions sent, a
   status timeline, contacts, interviews, tasks/follow-ups and notes.
4. **Analyze.** The dashboard shows how the search is going and what works best
   (see [Dashboard & analytics](05-dashboard.md)).

## Key principles

1. **Everything the user sent is preserved.** Document versions never change after
   upload; each application points to the exact versions sent. The full job
   description is stored, because postings disappear.
2. **History, not just state.** Every status change is an event with a timestamp.
   This makes the timeline, the stage durations and the analytics possible.
3. **Flexible, but logic stays reliable.** The user can add custom fields, rename or
   hide built-in fields, and configure pipeline stages and table columns. The core
   logic depends only on stable built-in fields and stage *categories*.
4. **Respect site rules.** Only use automated access where it is allowed. Users can
   add any site they choose; whether that site allows scraping is the user's
   responsibility.
5. **Maintainability first.** Clear layers, typed code, tests, CI, documented
   decisions (see [Architecture](03-architecture.md) and [ADRs](adr/)).

## Main screens

| Screen | Purpose |
|---|---|
| Dashboard | KPIs, charts, goals, follow-ups due |
| Inbox | New postings from all channels; triage quickly (keyboard shortcuts) |
| Applications | Table view (configurable columns, filters, saved views) and kanban board by stage |
| Application detail | Overview, timeline, documents sent, contacts, interviews, tasks, notes |
| Companies / Contacts | Lists and details, with linked applications |
| Documents | Document library with versions; shows where each version was used |
| Sources & searches | Configure channels, search profiles, run history, "test source" |
| Settings | Custom fields, built-in field labels/visibility, pipeline stages, goals, backup/export |
