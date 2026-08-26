---
name: interpreting-results
description: What a measurement licenses and what it does not, which is where most wasted work lives: why an ablation measures what the CURRENT rule extracts rather than what a better one could win, why a flat reading is not automatically a null, when a result transfers to another population, and what a joint measurement can and cannot settle. Use when reading an experiment, arguing from a number, or deciding whether a negative result closes a line.
---

# What a number licenses

A measurement supports some claims and not others, and the gap between the two
is where most wasted work lives. These are the inferences that look valid and
are not.

## An ablation measures what the current rule extracts, never what a better one could win

Replace part of a system with a random or trivial choice and measure the loss.
That quantity is `current − random`: how much the incumbent extracts on that
surface. It is not `optimal − current`, and the two come apart where it matters:

- **A large effect means the surface is decision-relevant** — the only
  direction the measurement licenses.
- **A small effect is ambiguous.** Either the surface does not matter, or the
  incumbent is no better than chance there — and the second case is exactly
  where a new approach has the most room.

So **never write a stopping rule whose trigger is a small ablation effect.**
The sound alternatives are a structural gate (does any measurable information
distinguish the candidates?) or substituting a *rival* — a better rule, or an
oracle with information the system lacks. `oracle − current` is a genuine
ceiling; a randomization is not. This error is a habit of gate-drafting rather
than a misunderstanding, so it re-derives itself after correction: watch for
the shape, not the topic.

**Run a positive control whenever you randomize**: perturb the whole surface.
If that does not clearly hurt, the wiring or harness is broken and nothing
measured through it is real.

## Before reporting a null, prove the change reached the system

A null and a change that never took effect produce identical output. Verify the
intervention moved the system — different decisions, different rows, a diff in
the stream — before writing down that it did nothing. This applies with full
force to a change you *expect* to be small: a null is a finding only once the
alternative explanation is excluded.

## A result measured under a defect still measured something

When a bug is found upstream of a body of results, each result still faithfully
measured the contrast between the variants it ran. What does not survive is
**transfer**: "X helps here" was reached on a system with a broken component,
so it may not hold once the component works. That is a weaker and more useful
claim than "throw it out" — it supports selective disposition: re-measure what
you would cite again, discard what you would not.

## Separate what is invalidated from how much it matters

Two disciplines that feel like one question. **Which results are affected** is
bookkeeping, with a definite answer that records can supply. **How much the
defect matters** is modelling, and only a measurement answers it. Conflating
them produces paralysis (everything might matter) or complacency (nothing seems
to). Answer them separately, in that order.

## A constant fitted on top of a defect is part of the defect

Anything calibrated while a component was broken may have been absorbing the
error. The visible form is a parameter wildly out of line with its siblings; the
common form is invisible — two summed terms whose relative scale was set while
one was crushed. A measurement of a fix, taken with constants fitted against the
unfixed system, is a **joint measurement of both**: a null there is the expected
reading and is not evidence against the fix. Re-fit, then read.

## Small effects do not carry mechanisms

A contrast that does not clear noise is not a mechanism to explain. Before
building an account of why a sub-threshold difference points one way, check
whether a cheaper, better-resolved instrument can bound it — it usually can, and
usually shows the sign was never stable.

Where several independent estimates exist, pool them by inverse-variance
weighting and **report the heterogeneity beside the estimate**; the
disagreement is the finding, and a pooled figure that hides it is worse than
either input alone. Two runs are too few to assess heterogeneity — expect to
need several, and call early pooled numbers provisional.
