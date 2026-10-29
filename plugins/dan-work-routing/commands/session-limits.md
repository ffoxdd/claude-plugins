---
description: Widen or restore a spawn-guard limit for this session alone — e.g. let several top-tier reviews the person asked for run side by side
argument-hint: [top_tier_concurrency=3 … | reset]
---

Set the spawn guard's limits for this session: **$ARGUMENTS**

This is the person's decision, made by typing this command. Do not run it to
get past a denial; a denial is answered by waiting or by folding the work into
a helper already running.

Run exactly this and report its output:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_limits.py" --data "${CLAUDE_PLUGIN_DATA}" $ARGUMENTS
```

- With no arguments it prints the session's current grant.
- `reset` removes the grant, so the plugin options apply again.
- Otherwise each argument is `key=value` with a non-negative integer, where
  the keys are the plugin's option names — `top_tier_concurrency`,
  `strong_tier_concurrency`, `agent_width`, `nested_top_tier_budget`,
  `nested_agent_budget`,
  `idle_minutes`, `settle_seconds` — and `0` lifts that limit. Settings
  accumulate across runs until `reset`.

The grant is keyed by session id and read by the guard ahead of the options,
so it governs this session only and is inert once the session ends. The
session id comes from `CLAUDE_CODE_SESSION_ID`; if the script reports it
unset, pass `--session <id>` with the id from this session's own paths.

The common case is several `/code-review` runs side by side. Each is one
top-tier fork, plus its finder angles when the review runs at high effort,
so `top_tier_concurrency=N` for N reviews lets the forks run together while
their angles still wait on each other, and `top_tier_concurrency=0` lets the
angles run too. The width ceiling holds either way unless widened as well.
