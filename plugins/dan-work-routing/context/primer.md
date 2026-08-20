# Routing work

Before starting work, classify it: is a safety constraint in play, or is cost
the only one? Exactly one constraint governs what follows; the other is off the
table. These are ordered constraints, never a blend — safety does not trade
against cost, because they never meet.

Most work is in the cost regime. A safety regime is the exception, and where it
applies it is absolute.

What establishes a safety regime is the environment, not this file. Where
sensitive data is in reach, the plugin that governs it defines what falls under
the regime, how to tell, and what the procedure is — and that definition wins
over anything here. Where nothing establishes one, every kind of work is
cost-governed.

## The cost regime

This is the default, and it governs more than data questions: writing code,
reading a codebase, running tests, drafting a document. Optimize in strict
order:

1. Minimize usage of the most expensive model tier.
2. Minimize total tokens.
3. Minimize wall-clock time.

Trade a lower priority for a higher one, never the reverse. Interactive work —
where a person is at the terminal, blocked — may promote wall time above total
tokens. It never promotes anything above spend on the top tier.

Delegate to the least powerful model that will do the job. Reserve the top tier
for design, specification, review, and triage.

**Set the model explicitly on every spawned agent.** An omitted model silently
inherits the session model, which is usually the most expensive tier available.
Choose per task: mechanical, bounded work gets the cheapest capable tier; the
session model only with a stated reason.

## When to spawn a sub-agent

Spawning is how the ordering above gets applied, so the test is a cost test.
Spawn to avoid reading, not to go faster. A sub-agent is a context filter first
and a parallelism primitive second — it carries fixed overhead (its own system
prompt and tool schemas) paid up front whatever the outcome. The test:

> Does the context the sub-agent loads cost less than the context it saves this
> session from loading?

- **Searching or exploring many files** — spawn. It reads fifty files and
  returns a paragraph; this session never sees the fifty. When the reading
  partitions by directory or subsystem, use the `explore` workflow rather than
  hand-rolling the fan-out: it fixes the reader tier, the disjoint slicing, and
  the synthesis barrier, so those decisions are made once in a script instead of
  re-derived each session.
- **Work needing context already in this window** — don't. You would pay to
  re-transmit what is already here, then pay again for the result.
- **Context that partitions cleanly** — each agent reading a different slice is
  near token-neutral, so fan out and take the speedup. Leaving a free speedup on
  the table is its own waste.
- **Context that overlaps** — serial. N agents re-reading the same files
  multiplies overhead to buy wall time, which inverts the ordering above.

Scale fan-out width by work per item, not item count. Twelve agents over twelve
substantial files is overhead as noise; twelve agents over twelve one-line
checks is overhead as the entire bill. For a fully-specified mechanical edit
across many files, the `bulk-edit` workflow encodes this: it batches files per
agent and holds each agent to the cheapest tier.

## Running agents you have already spawned

- **Reuse warm agents.** A follow-on task in the same code area goes to the
  existing agent as a message, not a cold respawn — the respawn pays the
  re-reading cost a second time for context that agent already holds.
- **Never kill in-flight work to fix its price tier.** The sunk reading cost
  usually exceeds the remaining premium. Fix the next spawn instead.
- **Launch, end the turn, resume on notification.** Never poll or busy-wait on
  tracked background work. Keep interim messages to a line or two and put the
  detail in durable records.
