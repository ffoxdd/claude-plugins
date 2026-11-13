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

Delegate to the least powerful model the task accepts — which is not the
cheapest. Never choose a model below what the task needs in order to save cost:
checking another agent's work needs a model at least as capable as the one that
produced it. Three tiers. The **top** tier is the session's own model, the
orchestrator's: reserve it for design, specification, review of top-tier work,
and triage, and run one of it at a time, as a matter of judgment. The **strong**
tier is `opus`: a build from a specification or a review of strong-tier work,
several of them side by side as the normal shape. The **cheap** tier is `sonnet`
and `haiku`: reading, searching, convention checks, mechanical edits. **Name the
model on every spawn, as a stated choice.** An omitted model takes the
configured default sub-agent model, which is a fallback, not a decision. One
rule is enforced by a hook: a spawn that names no model is refused unless a
default sub-agent model is configured, the spawn is a fork, or its agent type's
definition declares one.

Concurrent spend is agents generating at the same time. A parent that has ended
its turn to wait on a sub-agent it started is not spending; a builder that
pauses for its own reviewer is one stream of tokens, not two. Forks run on the
session's model, so a skill that forks and fans out — `/code-review` at high
effort — is top-tier spend however its angles are named.

Model is one of two dials. **Effort** is the other: how long a model reasons per
step, `low` through `max`, set per agent and per skill in frontmatter and per
session with `/effort`. The two are independent, so the cheap corner is a small
model at low effort and the expensive one a top-tier model at high. Choose model
by the judgment the work needs and effort by how much of the work is that
judgment: a mechanical edit wants both low; a bounded search wants a small model
and enough effort to be thorough; a review wants both high. Built-in skills that
fork, such as `/code-review`, expose only the effort dial, because a fork runs
on the session's model — so that is the dial to set on them.

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

## Reviewing a large diff

A review is the one task where the classification is cheap and the reading is
expensive, so classify first. Triage the diff at the cheap tier — the `explorer`
agent over the commit list and file stats — into slices of paths that change for
one reason, each marked mechanical (renames, symbol promotions, doc moves,
test-only edits) or logic (runtime behavior), with the logic slices ranked by
blast radius. Then dispatch by class. The built-in `/code-review` forks at the
session's model and, at high effort, fans out to several finder angles and a
verify pass. Choose each angle's model by this rule: a correctness or
verification angle over top-tier work stays on the session's model, since a
weaker model checking a stronger one's output is not a task it accepts; a
convention, reuse or mechanical-shape angle takes `sonnet`. Give `/code-review`
only the slices whose blast radius justifies it, one at a time, with nothing
else top-tier running beside it, because the fork and its correctness angles
read the whole slice at the session's tier. Other logic slices go to the
`reviewer` agent at the tier that wrote them, `opus` for a strong-tier build, at
high effort, one pass, no fan-out. Mechanical slices go to `reviewer` with a
cheaper `model` passed on the call; prose to a path-independence pass at the
cheapest tier. Diff against the upstream base (`origin/main...HEAD`), never a
local branch that may be stale. The expensive tier still reads every line that
needs judgment; it stops paying to read the lines that do not.

## Agents already spawned

- **Reuse is a token decision, made from context.** A follow-on task goes to a
  warm agent when the context it already holds is the context the task needs,
  rather than to a cold respawn that re-reads it. A task that needs none of that
  context goes to a fresh agent, because resuming an agent re-sends everything
  it holds on every step. So a review of someone else's change belongs with a
  fresh reviewer, not with a builder carrying a long build in context, even
  though the builder is already running.
- **Never kill in-flight work to fix its tier.** The sunk reading cost usually
  exceeds the remaining premium; fix the next spawn instead.
- **Launch, end the turn, resume on notification.** Never poll tracked
  background work. Interim messages are a line or two; detail goes in durable
  records.
- **A sub-agent hands its waits to whoever spawned it.** Once a sub-agent ends
  its turn, nothing it armed can wake it: its own Monitor or background command
  notifies no one. Only a message from its parent resumes it. A Monitor whose
  timeout expires inside a turn wakes the agent just to re-arm, and every wake
  re-sends its whole context. So a sub-agent facing a wait longer than one tool
  call arms nothing:
  1. Dispatch the work somewhere that outlives the turn (a job queue, or its
     parent's background command).
  2. Commit what is ready.
  3. End its turn naming what it is waiting on.

  The parent holds the wait and resumes it with the result. Stopping there is
  the correct behaviour, not stopping short.
