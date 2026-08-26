---
name: measuring
description: Producing a number worth trusting: a number is a property of (object, arm, population, instrument) and never of the program, plus the design defaults that follow — naming the denominator, pinning the reference, cancelling the structure you are not measuring, and checking that an arm moved the thing at all before reporting a null. Use when designing a measurement, choosing what to compare against, or deciding whether a number means what it appears to.
---

# Producing a number worth trusting

How to measure, for empirical work of any kind — an experiment, a model
evaluation, a query against production data. Design defaults, held loosely.

One principle generates the rest: **a number is a property of (object, arm,
population, instrument) — never of the program.** Every rule below is that
sentence applied to whichever of the four gets dropped, and in practice one
always does, because prose summaries shed qualifiers in that order.

## Name the population

Every rate carries its denominator in the same sentence. "89% of
opportunities", "0.2% of the actions actually taken", "of the states the
policy visits" are three different numbers about the same system, and they
routinely differ by two orders of magnitude.

**Never multiply two population-wide rates to size an effect on a narrower
population.** The joint is almost always available from the same query that
produced the marginals; compute it directly.

Before acting on a rate, ask which population the *action* would touch. A
change applies to the states the system actually reaches, so a rate over all
opportunities is not the one that governs it.

## Name the arm

Work generates many variants and most are rejected, but their numbers stay in
the documents and start reading like facts about the system. Every number
entering a decision carries its arm in the same sentence — "shipped, with the
refit on: 1.000" beside "diagnostic variant, residue removed: 1.246". Before
building on a prior number, re-derive it on the variant actually deployed; a
stale premise is a finding, so say so early.

## Name the instrument, and validate it first

The instrument is the one people forget, and it fails in a way that mimics a
real result: an oracle or label set assembled from an existing component
inherits that component's question, not yours, and a broken one reads exactly
like a real negative. Validate before measuring anything against it — the
checks, and a worked case, are in the `controlled-experiments` skill.

**An absent column means the recorder does not populate it, not that the
quantity cannot be computed.** A zero from an instrument nobody verified was
populated is indistinguishable from a measured null. Before concluding "X
cannot be known", check the system that would compute it rather than the corpus
that happens not to carry it.

## Match resolution to the contrast

Choose a representation's resolution by what the decision *differentiates*, not
by what predicts outcomes on average. A coarse metric can be the best predictor
of levels while being useless for the deltas or rankings a decision compares.
Before reusing a validated metric in a new decision context, ask what this
decision contrasts and whether the metric moves across that contrast.
**Levels-validated is not ranking-valid.**

**A metric conditioned on success is invalid when the change moves the
conditioning population.** Mean-outcome-among-winners can confirm at high
significance while the system collapses, because the survivors are a selected
subset. A conditioned primary needs a stability guard on the conditioning
population or an unconditioned companion, decided before the run.

## Conditioning on the system's own choices

A validation conditioned on what the system chose can never certify those
choices: selection at the maximum picks the candidate whose estimate errs
upward, so conditioning on the choice marginalizes away the contrast the
decision consumed. A calibration over chosen rows supports a *pricing* claim,
never a *decision* claim; decision claims need an instrument that sees the
margin — recorded runner-up contrasts, a forced-flip probe, an override
variant. And before fitting a correction, check that the population you would
fit it on can see the error at all.

## Do not move the baseline

Structural correctness earns a place in the codebase, never a place in the
baseline. A change at a negative point estimate stays available and off by
default, and the stated baseline remains the system without it until it
demonstrably pays. "Kept for generality" must never appear in the same sentence
as "new baseline" — that ratchets the reference downward, and a real regression
gets laundered into parity one step at a time.

A give-away large enough to notice is a debt with a mechanism to find.
Non-significance is a thing to say plainly, not a reason to leave it alone.
