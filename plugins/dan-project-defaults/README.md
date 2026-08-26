# dan-project-defaults

The choices you would otherwise re-state at the start of every project: how the
code is laid out, which library to reach for, where the documentation goes, and
what the build refuses to let through.

```
/plugin install dan-project-defaults@ffoxdd
```

Two skills, both loaded on demand — a session that never starts anything new
pays only for their descriptions.

- **`canonical-choices`** — take the ecosystem's canonical layout and its
  canonical libraries, with modernity as the one tiebreaker where it is also
  correctness; a `docs/` folder from the beginning, written for the agents
  working on the project as much as the people; a linter and formatter wired
  into the build rather than left to a step someone can skip.
- **`data-modeling`** — the defaults a greenfield schema follows: table, key
  and database naming, the `created_at` audit column, and persisting raw
  inputs so a new feature never forces re-running the producer.

## What it is not

It scaffolds nothing. No command generates a project, nothing is copied into a
new repository, and no file here is a template — the skills only shape what
Claude reaches for while building.

It also names very few tools, and pins no versions. Which tool is canonical is
a fact about an ecosystem at a moment, so a list of them here would need
revising more often than the rule that produced it; the rule is the durable
part and is what this carries.

**A project that has already chosen keeps its choice.** These are defaults for
an open decision, not a migration plan for a repository that settled it
differently.
