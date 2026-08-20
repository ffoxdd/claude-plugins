# dan-work-routing

Classify work before doing it: a safety constraint governs where one applies,
cost governs everything else, never a blend. Injected at session start, so the
routing happens before the work rather than being remembered mid-task.

```
/plugin install dan-work-routing@ffoxdd
```

## What it carries

- **The routing primer** — the cost ordering (top-tier spend, then total
  tokens, then wall time), the sub-agent spawn test, and the fan-out rules.
- **Secret-handling rules** — never materialize a credential; reference it and
  let it resolve at runtime.
- **Agents** — `explorer` (bounded questions over many files), `reviewer`
  (read-only diff review), `bulk-editor` (mechanical edits, cheapest tier).
- **Workflows** — `explore` (fan readers over disjoint slices, one synthesis
  barrier) and `bulk-edit` (batch a fully-specified edit across files, width
  scaled by work per item).

## Safety regimes live elsewhere

This plugin states the shape — one constraint governs, safety pre-empts cost —
and leaves the safety regime itself undefined, because what counts as sensitive
is a property of the environment. A deployment that handles regulated data
supplies its own plugin naming what falls under the regime and depends on this
one for the half that is the same everywhere. Where nothing establishes a
safety regime, every kind of work is cost-governed.
