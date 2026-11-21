# ADR 0003: Job sources respect site terms; adapters are pluggable

- **Status:** Accepted
- **Date:** 2026-11-21

## Context
The user's main job sites are StepStone and LinkedIn. Both forbid automated scraping in
their terms of service and actively block bots; LinkedIn may restrict accounts used for
automation. The user also wants to add arbitrary websites as sources.

## Decision
- StepStone and LinkedIn postings are captured through user-initiated channels (URL
  import, bookmarklet) and through their own job-alert emails, not through crawling.
- Automated fetching uses official APIs (Bundesagentur für Arbeit, Arbeitnow, Adzuna)
  and user-defined generic sources.
- All channels implement one `SourceAdapter` protocol registered in an adapter
  registry. Generic adapters (API/RSS/JSON-LD/HTML) are configured as data, not code.
- For user-added sites, the user is responsible for checking that the site allows automated access.

## Consequences
- Reliable, low-maintenance discovery without risk to the user's accounts.
- New channels can be added without touching the rest of the app.
- Discovery from StepStone/LinkedIn is less "instant" than crawling, but more robust.
