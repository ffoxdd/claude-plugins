---
description: Run an open-ended charter loop — find avenues, delegate each to the cheapest capable tier, record verdicts, repeat
argument-hint: [scope, e.g. "the scoring path" or "anything in this repo"]
---

Run a charter loop over: **$ARGUMENTS**

If that is empty, use the whole repository and say so before starting.

Read `${CLAUDE_PLUGIN_ROOT}/skills/charters/SKILL.md` first if it is not already
in context. It defines what a charter is, what separates an avenue from a topic,
and the verdict vocabulary; this command only sequences the cycle.

You keep the judgment and delegate the legwork. That split is this plugin's cost
ordering applied to open-ended work: framing a question so it can come back
negative, and reading what a verdict licenses, are top-tier work — executing a
well-written charter is not.

## The cycle

1. **Discover.** Find the avenues in this scope. Prefer searches over the
   COMPLEMENT of what is known — code that never names the concept, caveats whose
   stated expiry has passed, ledger rows still open.

   How to run that search is a routing decision, so make it rather than assuming
   one. Often it is a single instrument — a grep, a script, a ledger read — and
   costs a tool call with no agents at all. Use the `charter-discovery` workflow
   when the spawn test passes: probing is expensive enough that reading it here
   would cost more than a sub-agent, and the probes partition cleanly. Reaching
   for the workflow by default pays overhead to search ground you could have read
   directly.

2. **Pick one.** Take the top-ranked avenue. Do not batch several into one
   charter: a unit with two questions cannot come back negative on one of them.

3. **Write the charter.** Question, avenue, what would falsify it, what it does
   not license. Short enough that the executor reads all of it — it is a context
   filter, and its whole job is to travel without the history that produced it.

4. **Delegate it.** Spawn an agent at the cheapest tier that can do the work and
   **set the model explicitly** — an omitted model silently inherits this
   session's, which is the tier you are trying not to spend. Hand it the charter,
   not the programme.

5. **Read the verdict yourself.** Judge what came back and what it licenses. A
   negative is the cheap outcome, not the failed one: it removes an avenue
   permanently, which is the point.

6. **Record it** where the next discovery pass will find it — the ledger, the
   task tracker, the durable record this project already keeps. A verdict that
   lives only in this conversation did not happen.

7. **Go to 1.**

## When to stop

Stop when discovery returns nothing, and only then. Not when the work feels
finished — those differ, and the second is what quietly ends programmes with
obvious work left.

On an empty pass, widen the probes ONCE: look somewhere you have not, at a
coarser granularity, or at a class of work you have been treating as out of
scope. If the wider pass is also empty, stop and say so plainly.

**Never invent an avenue to keep the loop alive.** A manufactured charter costs
a delegation, pollutes the ledger with a verdict that means nothing, and makes
the next discovery pass harder by burying real candidates. An honest "nothing
left here" is a result.

## Between cycles

Keep interim messages to a line or two — the detail belongs in the charter and
its verdict, both of which outlive the session. If a charter's execution is long
or queued, launch it, end the turn, and resume on notification rather than
polling.
