# ADR 0002: Custom fields stored as validated JSON

- **Status:** Accepted
- **Date:** 2026-11-21

## Context
The user must be able to add and remove fields on applications, postings, companies,
contacts and interviews at runtime, choose their type, and decide which data goes into
them. Options considered:

1. **Runtime schema changes** (adding real database columns): powerful, but risky
   migrations, hard to make portable, fragile.
2. **EAV** (one row per value): flexible, but complex queries, slow filtering, and
   awkward for analytics.
3. **`FieldDefinition` + a JSON column per entity:** simple, portable (SQLite JSON1 and
   PostgreSQL JSONB), filterable and sortable via JSON lookups.

## Decision
Option 3. `FieldDefinition` rows describe each field (type, choices, validation,
display). Values are stored in a `custom_data` JSON column on each entity, keyed by an
immutable field key. Forms, validation, table columns, filters and dashboard dimensions
are generated from the definitions. Built-in fields stay real columns; they can be
renamed or hidden, but not deleted.

## Consequences
- No migrations when the user changes fields.
- Values are validated in the application layer, not by database constraints.
- Changing a field's type requires a conversion step (handled by a service with a preview).
- If needed later, frequently filtered keys can be indexed (PostgreSQL GIN / expression indexes).
