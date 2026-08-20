# Data and schema

One of several files of conventions for the code Claude writes. Design
defaults, held loosely — any of them yields when the problem at hand genuinely
disagrees.

## Data and persistence
- **Persist raw inputs, derive features offline.** When recording data for later analysis or training, store the raw *state* needed to recompute any derived feature — not just the features you happen to want today. Recording only derived outputs (a computed score, a progress metric, an embedding) throws away the inputs, so every *new* feature forces you to regenerate the entire dataset by re-running the expensive producer. The test for a row: *"could I compute a brand-new feature from this alone, without re-running the producer?"* If not, you're persisting conclusions, not inputs. Record the full state even when today you only consume a scalar derived from it (e.g. store the complete hand — concealed tiles *and* melds — not just the four progress numbers you currently read off it). Derived columns are fine as a convenience/cache, but they must be *redundant* — reproducible from the raw columns in the same row — never the only copy.

## Relational databases (greenfield only)
- **Database tables are named as the plural of the entity each row holds** (e.g. `members`, `coverage_spans`, `field_value_candidates` — not `field_value_candidate`). A table name reads as "a collection of <entity>".
- **A table's primary key is `id`** — never `<entity>_id`, which stutters against the table name (`decisions.id`, not `decisions.decision_id`). A *foreign* key is `<referenced_entity_singular>_id` (`decision_id`), so a join reads `on d.id = c.decision_id` rather than sharing one column name across both sides.
- **Every table carries `created_at`**, defaulted to system time. It is an audit column and **never load-bearing** — no query filters or joins on it for logic, and no business rule reads it. Semantic clocks are their own named columns (`decided_at`, `first_seen`, `effective_date`); don't let `created_at` stand in for one, and don't reach for it as a point-in-time axis.
- **Database name pattern**: `<project>_<environment>` — `my_app_development`, `my_app_staging`, `my_app_production`. Predictable across projects.
- When working with an existing database, follow its existing conventions even if they differ from the above.
- **Database object names are spelled out too** — databases, schemas, tables, and columns included: `OPERATIONS`, not `OPS`.
