# dan-work-routing

Classify work before doing it: a safety constraint governs where one applies,
cost governs everything else, never a blend. Injected at session start, so the
routing happens before the work rather than being remembered mid-task.

```
/plugin install dan-work-routing@ffoxdd
```

## What it carries

- **The routing primer** — the cost ordering (top-tier spend, then total
  tokens, then wall time), the two cost dials (model and effort), the sub-agent
  spawn test, the fan-out rules, and how to review a large diff by classifying
  it first.
- **The spawn guard** — a hook on every Agent call, so the primer's spawn
  rules hold inside skills and forks this plugin does not own. It denies a
  call naming no `model` (a fork passes, as does an agent type whose
  definition declares one, `inherit` included); a top-tier spawn while
  another top-tier agent is in flight; any spawn past a width ceiling; and a
  sub-agent's helpers past a small total budget, fewer of them top-tier,
  which is what caps a built-in review's fan-out. In-flight state comes from the harness's own
  subagent records, with the guard's approvals standing in until the harness
  records the agent, so spawns issued in one batch see each other; each
  denial names what is in flight. The six
  limits are plugin options (`/plugin` → configure).
- **Secret-handling rules** — never materialize a credential; reference it and
  let it resolve at runtime.
- **Agents** — `explorer` (bounded questions over many files), `reviewer`
  (read-only diff review), `bulk-editor` (mechanical edits, cheapest tier).
- **Workflows** — `explore` (fan readers over disjoint slices, one synthesis
  barrier), `bulk-edit` (batch a fully-specified edit across files, width scaled
  by work per item), and `charter-discovery` (fan probes over the places work
  could hide, returning ranked avenues or an honest empty list).
- **`/dan-work-routing:charter-loop`** — the entry point: discover avenues,
  delegate each to the cheapest capable tier, read the verdict yourself, repeat
  until discovery comes back empty.
- **The `charters` skill** — for when units of work become objects you talk
  about rather than just do: generated instead of assigned, cited by number,
  carrying verdicts that outlive the session. On demand, because in an ordinary
  session the charter is just the prompt and needs no name.

## Safety regimes live elsewhere

This plugin states the shape — one constraint governs, safety pre-empts cost —
and leaves the safety regime itself undefined, because what counts as sensitive
is a property of the environment. A deployment that handles regulated data
supplies its own plugin naming what falls under the regime and depends on this
one for the half that is the same everywhere. Where nothing establishes a
safety regime, every kind of work is cost-governed.
