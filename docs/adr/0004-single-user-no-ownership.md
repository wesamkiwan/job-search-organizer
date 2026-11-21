# ADR 0004: Single user, no per-record ownership

- **Status:** Accepted
- **Date:** 2026-11-21

## Context
The app is personal: one user, data stored locally, possibly hosted later for the same
single user.

## Decision
Records do not carry an `owner` foreign key. Authentication is still required on every
page (Django auth), so hosting later is safe.

## Consequences
- Simpler models, queries and tests.
- Turning it into a multi-user app later would require adding ownership to all models
  and scoping all queries. This is accepted as unlikely.
