# What a number licenses

A measurement supports some claims and not others, and the gap between the two
is where most wasted work lives. These are the inferences that look valid and
are not.

## An ablation measures what the current rule extracts, never what a better one could win

Replace part of a system with a random or trivial choice and measure the loss.
That quantity is `current − random`: **how much the incumbent is extracting on
that surface.** It is not `optimal − current`, and the two come apart exactly
where it matters.

- **A large effect means the surface is decision-relevant.** Valid, and the only
  direction the measurement licenses.
- **A small effect is ambiguous.** Either the surface does not matter, or the
  incumbent is already no better than chance there — and the second case is
  precisely where a new approach has the most room.

So **never write a stopping rule whose trigger is a small ablation effect.** If
you find yourself drafting one, the sound alternatives are a structural gate
(does any measurable information distinguish the candidates?) or substituting a
*rival* — a better rule, or an oracle with information the system lacks. An
oracle-minus-current contrast is a genuine ceiling and can be relied on;
a randomization cannot.

This error is easy to re-derive after being corrected, because it is a habit of
gate-drafting rather than a misunderstanding of the concept. Watch for the
shape, not the topic.

Run a **positive control** whenever you randomize: perturb the whole surface. If
that does not clearly hurt, the wiring or the harness is broken and no finding
from it is real.

## Before reporting a null, prove the change reached the system

A null and a change that never took effect produce identical output. Verify the
intervention actually moved the system — different decisions, different rows,
a diff in the stream — before writing down that it did nothing. Two separate
occasions of "no effect" have turned out to be an inert instrument.

This applies with full force to a change you *expect* to be small. A null is a
finding only once the alternative explanation is excluded.

## A result measured under a defect still measured something

When a bug is found upstream of a body of results, the results are not
retroactively wrong. Each faithfully measured the contrast between the variants
it ran. What does not survive is **transfer**: a conclusion of the form "X helps
here" was reached on a system with a broken component, so it may not hold once
the component works.

That is a weaker and more useful claim than "throw it out". It supports
selective disposition — re-measure what you would cite again, discard what you
would not — rather than a blanket re-run or a blanket act of faith.

## Separate what is invalidated from how much it matters

These feel like one question and are two disciplines.

**Which results are affected** is bookkeeping. It has a definite answer, and
records can make it answerable.

**How much the defect matters** is modelling — reasoning about the system to
estimate whether the correction changes behaviour and by how much. No amount of
recorded provenance answers it; only a measurement does.

Conflating them produces either paralysis (everything might matter) or
complacency (nothing seems to). Answer them separately and in that order.

## A constant fitted on top of a defect is part of the defect

When a component is corrected, anything calibrated while it was broken is
suspect — it may have been absorbing the error. A parameter that is wildly out
of line with its siblings is the visible form of this, but the invisible form is
more common: two terms summed together whose relative scale was set while one of
them was crushed.

So a measurement of a fix, taken with constants fitted against the unfixed
system, is a **joint measurement of both**. A null there is the expected reading
and is not evidence against the fix. Re-fit, then read.

## Small effects do not carry mechanisms

A contrast that does not clear noise is not a mechanism to explain. Before
building an account of why a sub-threshold difference points one way, check
whether a cheaper, better-resolved instrument can bound it — it usually can, and
usually shows the sign was never stable.

Where several independent estimates exist, pool them and report the
heterogeneity alongside the estimate. A pooled figure that hides wide
disagreement between its inputs is worse than either input alone.
