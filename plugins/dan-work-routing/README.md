# dan-work-routing

Classify work before doing it: a safety constraint governs where one applies,
cost governs everything else, never a blend. Injected at session start, so the
routing happens before the work rather than being remembered mid-task.

```
/plugin install dan-work-routing@ffoxdd
```

## What it carries

- **The routing primer** — the cost ordering (top-tier spend, then total
  tokens, then wall time), the tiers and the two cost dials (model and effort),
  when to reuse a warm agent and when to start a fresh one, the sub-agent spawn
  test, the fan-out rules, and how to review a large diff by classifying it
  first. At session start it adds one line for each paired setting below that
  is unset.
- **The model guard** — one stateless hook on every Agent call, so a spawn
  says which model it runs on even inside skills and forks this plugin does not
  own. It refuses a call that names no `model` unless
  `CLAUDE_CODE_SUBAGENT_MODEL` is set, the call is a fork, or the agent type's
  definition declares a model (`inherit` included). It reads only the call,
  the hook process's environment and agent definition files. The hooks
  reference says a hook process inherits Claude Code's environment; it does not
  say in so many words that a settings `env` block reaches a hook, so the check
  reads the variable from the hook's own process, which is set either way when
  the variable is exported in the shell that starts Claude Code.
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

## Design stance

A hook earns its place only where the platform does not enforce a rule and
judgment cannot be trusted with it. Claude Code enforces the mechanical limits
itself: `CLAUDE_CODE_SUBAGENT_MODEL` gives a spawn that names no model a
default other than the session's model (a per-call `model` and an agent
definition's `model:` take precedence over it), `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`
caps how many sub-agents run at once (default 20), and
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` caps nesting (default 3 layers). What
matters most cannot be hooked: reasoning about token spend, including whether
to reuse a warm agent. So the plugin states its priorities, enforces the one
rule the platform leaves open, and reads no undocumented format, such as a
session's transcripts.

Nothing hard-stops a deliberate top-tier fan-out — several top-tier agents, or
a fork that fans out to finder angles on the session's model. Forks pass the
guard and run on the session's model. The statement of priorities in the
primer is the defence there.

## Settings to pair with it

A plugin cannot set Claude Code's environment, so these go in the `env` block
of `~/.claude/settings.json` (or are exported in the shell). The values are the
author's preference:

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus",
    "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "8"
  }
}
```

- `CLAUDE_CODE_SUBAGENT_MODEL` — the model a spawn that names none runs on;
  `opus` makes that the strong tier, never the session's top tier. Setting it
  to `inherit` is the same as leaving it unset.
- `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` — how many sub-agents may run at once
  before the Agent tool refuses another; `8` keeps a fan-out narrow.

## Safety regimes live elsewhere

This plugin states the shape — one constraint governs, safety pre-empts cost —
and leaves the safety regime itself undefined, because what counts as sensitive
is a property of the environment. A deployment that handles regulated data
supplies its own plugin naming what falls under the regime and depends on this
one for the half that is the same everywhere. Where nothing establishes a
safety regime, every kind of work is cost-governed.
