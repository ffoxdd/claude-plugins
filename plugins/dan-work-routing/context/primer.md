# Routing work

Before starting, classify the work: does a safety constraint apply, or is cost
the only one? Exactly one governs. They are ordered, never blended — safety does
not trade against cost, and where it applies it is absolute.

The environment establishes a safety regime, not this file. A plugin governing
sensitive data defines what falls under the regime, how to tell, and the
procedure, and that definition wins over anything here. Where nothing
establishes one, every kind of work is cost-governed, which is the usual case.

## Never a factor

Time, lateness, or fatigue. Do not mention the hour or the session's length, and
never stop, defer, checkpoint, or de-scope on that basis. Continuing or stopping
rests on correctness, verified evidence, risk to production, or an explicit
instruction. A risky change gets care because it is risky, never because "it's
late".

## The cost regime

It governs everything — writing code, reading a codebase, running tests,
drafting a document. Optimize in strict order, trading a lower priority for a
higher one and never the reverse:

1. Spend on the most expensive model tier.
2. Total tokens.
3. Wall-clock time.

Interactive work, with a person blocked at the terminal, may promote wall time
above total tokens — never above top-tier spend.

Delegate to the least powerful model that will do the job; reserve the top tier
for design, specification, review, and triage. **Set the model explicitly on
every spawned agent.** An omitted model inherits the session's, usually the most
expensive tier; the session model needs a stated reason.

## When to spawn a sub-agent

Spawn to avoid reading, not to go faster. A sub-agent is a context filter first
and a parallelism primitive second, and its system prompt and tool schemas are
paid up front whatever the outcome. The test: does the context it loads cost
less than the context it saves this session from loading?

- **Searching or exploring many files** — spawn. It reads fifty files and
  returns a paragraph. When the reading partitions by directory or subsystem,
  use the `explore` workflow rather than hand-rolling the fan-out.
- **Work needing context already in this window** — don't. You would pay to
  re-transmit it, then pay again for the result.
- **Context that partitions cleanly** — fan out. Each agent reading a
  different slice is near token-neutral, so the speedup is free.
- **Context that overlaps** — serial. N agents re-reading the same files buys
  wall time with tokens, which inverts the ordering.

Scale fan-out width by work per item, not item count: twelve agents over twelve
substantial files is overhead as noise, twelve over twelve one-line checks is
overhead as the whole bill. For a fully-specified mechanical edit across many
files, the `bulk-edit` workflow batches files per agent at the cheapest tier.

## Agents already spawned

- **Reuse warm agents.** A follow-on task in the same area goes to the existing
  agent as a message, not a cold respawn that re-reads what it already holds.
- **Never kill in-flight work to fix its tier.** The sunk reading cost usually
  exceeds the remaining premium; fix the next spawn instead.
- **Launch, end the turn, resume on notification.** Never poll tracked
  background work. Interim messages are a line or two; detail goes in durable
  records.
