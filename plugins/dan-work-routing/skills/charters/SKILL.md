---
name: charters
description: Treating units of work as named objects — one question, one avenue, one recorded verdict, cited later by number. Covers when the word is worth having at all, how to FIND the next charter when nobody supplies one, what counts as an avenue, why a negative verdict is the cheap outcome rather than the failed one, and how a charter makes delegation possible. Use for autonomous or long-running loops, standing programmes with no fixed endpoint, "keep going until there is nothing left", resuming a programme someone else left, or any work where the next task must be discovered rather than assigned.
---

# Charters

A charter is the specification of one unit of work: **one question, one avenue
down which it can be answered, and a verdict recorded where the next piece of
work will find it.**

## When the word is worth having

Usually it is not. In an ordinary session the charter is just the prompt someone
gave you — the question and its scope arrive together, get done, and need no
name, because nothing ever has to refer back to them as a thing.

The word earns its keep at the **meta level**, when charters stop being the work
and become objects you talk about: generated rather than given, chosen among,
cited by later work, carrying verdicts that outlive them. That happens when

- **nobody is supplying the next one** — an autonomous or standing loop, where
  finding the work is most of the work;
- **someone has to resume a programme** they did not run, and needs to know what
  was already tried and what came back empty;
- **the unit is delegated**, so the specification has to travel without the
  history that produced it.

Below that bar, do not manufacture ceremony. A prompt is a fine charter and
naming it adds nothing.

The word is not invented here. Session-based exploratory testing has used
**charter** for a written mission for one timeboxed session, producing a report,
since about 2000 — mission in, verdict out. And the loop that generates its own
next charter and ranks the candidates is Lenat's **agenda** from AM and EURISKO,
where working one task produced more and each was rated for how interesting it
would be to settle. Charters plus an agenda is the whole pattern; both halves
have been named for decades.

## Numbering

Once charters are objects, they need identity. Give each the next number in the
sequence and cite by number: "Charter 39 closed that row" survives a rename, a
refactor, and the loss of everyone who was there. Titles have to stay accurate;
numbers never do.

## The loop

Open-ended work is the case that forces all of the above, and it fails in two
specific ways the charter's shape prevents. It drifts, because "improve X" never
finishes and never fails. And it repeats, because nothing recorded what was
already tried.

> discover the avenues → pick one → charter it → execute → verdict → record →
> discover again

Termination is the honest part: **stop when no avenue exists, never when the
work feels done.** Those differ, and the second is the one that quietly ends
programmes with obvious work left. If a discovery pass returns candidates, the
loop continues whatever else is true.

## Finding the next charter

This is the part that makes a loop autonomous, and the part most often skipped —
a loop that needs a person to supply each task is not open-ended, it is a queue
with extra steps.

**Build discovery instruments, do not re-derive the list each time.** A
discovery instrument enumerates candidate avenues mechanically and is rerun
rather than remembered. What makes one work is that it searches the COMPLEMENT
of what you already know:

- Grep for the code that never mentions the concept, not the code that does.
  Code that names the thing has already been considered; the finding is in what
  is silent about it.
- List the caveats that named their own expiry condition, then ask which
  conditions have since fired. A deferral is honest when written and becomes an
  undocumented assumption the moment its trigger passes, and nothing re-reads it.
- Keep a standing ledger of open rows and their dispositions. The rows still
  open ARE the candidate list.

A discovery pass returns candidates, not defects. Something can be silent about
a concept because it genuinely does not depend on it. The instrument narrows
where to look; the judgment stays a judgment.

**Whether discovery fans out is a routing decision, not a property of
discovery.** Most of it is running an instrument — a grep, a script, a ledger
read — which costs a tool call and no agents at all. Spawning probes for that
pays overhead to search ground you could have read directly.

Apply the primer's spawn test as you would anywhere: probes earn agents when
each reads ground this session would otherwise load, and when they partition.
Where that holds, the `charter-discovery` workflow encodes the pass — one probe
per place work could hide, a judge that drops topics and ranks what survives,
and an empty list returned plainly when there is nothing, which is the loop's
termination signal rather than a failure to find one. Where it does not, run the
instrument and read the list.

The LOOP is not a workflow either way. Executing a charter can mean hours behind
a job queue and a verdict that needs judging, so a script would block on the
first long job or have to be re-entrant.

## What counts as an avenue

An avenue is a specific next step whose outcome would change what you do next.
Not a topic, not an aspiration.

- **"Rank reflection may not hold on this ruleset"** — an avenue. It can be
  checked, and either answer redirects the work.
- **"Improve the scoring path"** — not an avenue. Nothing about it can come back
  negative, so nothing about it can finish.

If you cannot say what a negative result would look like, you have a topic. Turn
it into an avenue or drop it; do not charter it.

## Writing one

Keep it short enough that the executor reads all of it. A charter states:

- **The question**, in a form that admits a negative answer.
- **The avenue** — the specific work that answers it.
- **What would falsify it**, written before the work, because a prediction made
  afterward is a description.
- **What it does not license**, which is the half that gets forgotten and the
  half that stops a later reader over-reading the verdict.

Give it the next number in the sequence. Numbers beat titles for citation because
they never need to stay accurate.

## Verdicts

Every charter ends in one, recorded in the ledger rather than in a message.
Useful dispositions:

- **Closed** — answered, and say by what.
- **Closed, but not by the condition it named** — the honest and common case.
  A debt retired by making the branch unnecessary was still retired; record how,
  because the discharge condition it originally named will otherwise look unmet
  forever.
- **Negative** — the avenue was real and the answer was no. This is the CHEAP
  outcome, not the failed one: it removes an avenue permanently, which is
  progress in an open-ended programme and the whole reason to record it.
- **Parked**, with an unblock condition, and that condition belongs in the
  discovery instrument or it will not be re-read.
- **Still open**, with what remains.

A charter whose verdict is a paragraph in a chat log did not finish. The verdict
outlives the session; the message does not.

## Routing a charter

Charters and routing meet here, and the division follows the cost ordering in
this plugin's primer:

- **The top tier writes the charter and reads the verdict.** Framing a question
  so it can come back negative, and judging what a result licenses, is exactly
  the design-and-triage work the top tier is reserved for.
- **Cheaper tiers execute it.** A well-written charter is a context filter: it
  states the question and the avenue, so the executor does not need the history
  that produced it.

That is the routing argument for writing the document at all. A charter is the
artifact that makes delegation possible without re-transmitting the programme.

## When the question is empirical

Charters are not a measurement practice — a refactor sweep, a bug hunt or a
documentation gap charters exactly as well. But when a charter's question is
answered by a measurement, how its verdict may be read is governed by evidence
practice and not by this skill: what the number is a property of, what an
ablation licenses, and why a flat result is not automatically a null.

Reach for that separately. Do not restate it here; two copies drift.
