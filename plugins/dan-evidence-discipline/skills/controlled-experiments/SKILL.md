---
name: controlled-experiments
description: Designing and reading experiments where you control the data-generating process — simulations, self-play, model evaluation harnesses, seeded benchmarks, anything you can rerun with one thing changed. Covers paired comparison against a pinned reference, measuring the headroom on a surface before improving it, and building a ceiling instrument you can trust. Use when designing an experiment, choosing a baseline, deciding how many runs are needed, or interpreting a result that came out flat.
---

# Experiments you can rerun

The half of measurement that depends on **owning the data-generating process**:
replaying the world with exactly one thing changed. Simulations, self-play,
evaluation harnesses over fixed suites, seeded benchmarks.

It does not apply to observational or production data, where the intervention
already happened. The `measuring` and `interpreting-results` skills still hold
there; the procedures below mostly do not, and their observational counterparts
— blocking, matching, pre-period covariates, difference-in-differences — rest on
different assumptions. Reaching for a seeded paired comparison on data you did
not generate is the characteristic error.

## The three procedures

- **Pair against a pinned reference** rather than comparing absolute levels;
  most run-to-run variance is common to both arms on the same input, and
  pairing cancels it. `references/paired-comparison.md`.
- **Measure the headroom before improving a surface.** Randomize the decision
  you were about to improve; if that costs nothing, no improvement there can
  pay. `references/headroom.md`.
- **Build a ceiling, and validate it before believing anything measured
  against it.** `references/oracles.md`.

## Choosing what to spend

Two questions with different costs; decide which you are asking before
spending anything:

- *"Is this change better than what we run?"* — paired, against the current
  system, on shared inputs. Cheap, high-resolution, the primary readout.
- *"Where does the system stand?"* — a level comparison against a pinned
  external reference. Expensive, low-resolution, and tightened only by more
  inputs, never more arms. Do it once.

## Coverage comes from cells, not repetitions

For finding defects, an invariant either reaches a broken path in a given
configuration or never does: a new configuration finds bugs, another repetition
of an existing one buys nothing. Any repetition count above a handful needs a
stated reason. This inverts for effect estimation, where repetitions are what
buy resolution — know which of the two you are doing.

## Name the reference, never "the current best"

A reference named by a moving label — *the default*, *the champion* — stops
meaning one thing when the defaults move, and every number taken against it
silently becomes incomparable. Pin a frozen version, name it in the same
sentence as the result, and keep it runnable indefinitely.

Regime parameters belong in that sentence too. A threshold or population
setting that changes the problem rather than tuning it makes results under
different values different experiments, even when every other detail matches.
