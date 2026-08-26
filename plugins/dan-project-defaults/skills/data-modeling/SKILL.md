---
name: data-modeling
description: Default conventions for a greenfield schema or a recorded dataset — table, column, key, and database naming, the created_at audit column, and persisting raw inputs rather than derived features. Use when designing tables, writing migrations or DDL, naming a new database, or deciding what a recorder writes for later analysis. An existing database keeps its own conventions.
---

# Data modeling defaults

Design defaults, held loosely. When working with an existing database, follow
its conventions even where they differ from these.

## Relational schema (greenfield)

- A table is named as the plural of the entity each row holds: `members`,
  `coverage_spans`, `field_value_candidates`. The name reads as "a collection
  of <entity>".
- The primary key is `id`, never `<entity>_id` (`decisions.id`, not
  `decisions.decision_id`). A foreign key is `<referenced_entity_singular>_id`
  (`decision_id`), so a join reads `on d.id = c.decision_id` rather than
  sharing one column name across both sides.
- Every table carries `created_at`, defaulted to system time. It is an audit
  column and never load-bearing: no query filters or joins on it for logic,
  and no business rule reads it. A semantic clock is its own named column
  (`decided_at`, `first_seen`, `effective_date`).
- The database is named `<project>_<environment>`: `my_app_development`,
  `my_app_staging`, `my_app_production`.
- Database object names are spelled out like every other identifier:
  `OPERATIONS`, not `OPS`.

## Recorded datasets

- Persist raw inputs, derive features offline. A row stores the raw state
  needed to recompute any derived feature, not only the features wanted today;
  recording derived outputs alone means every new feature forces re-running
  the expensive producer. Test for a row: could a brand-new feature be
  computed from this alone? Record the full state even when today only a
  scalar of it is read (the complete hand, concealed tiles and melds, not the
  four progress numbers).
- Derived columns are fine as a cache, but must be reproducible from the raw
  columns in the same row — never the only copy.
