---
name: controlled-experiments
description: Designing and reading experiments where you control the data-generating process — simulations, self-play, model evaluation harnesses, seeded benchmarks, anything you can rerun with one thing changed. Covers paired comparison against a pinned reference, measuring the headroom on a surface before improving it, and building a ceiling instrument you can trust. Use when designing an experiment, choosing a baseline, deciding how many runs are needed, or interpreting a result that came out flat.
---

# Experiments you can rerun

This is the half of measurement that depends on **owning the data-generating
process**: being able to replay the world with exactly one thing changed. It
applies to simulations, self-play, evaluation harnesses over fixed suites, and
seeded benchmarks.

It does not apply to observational or production data, where the intervention
already happened and cannot be replayed. The principles in this plugin's
always-loaded context still hold there; the procedures below mostly do not, and
their observational counterparts — blocking, matching, variance reduction from
pre-period covariates, difference-in-differences — are different techniques
resting on different assumptions. Reaching for a seeded paired comparison on
data you did not generate is the characteristic error.

## The three procedures

**Pair against a pinned reference** rather than comparing absolute levels. Most
of the variance in a run is common to both arms on the same input, and pairing
cancels it. `references/paired-comparison.md` covers the resolution this buys,
the reference you should pin, and the mistake of trying to tighten a level
comparison by adding arms.

**Measure the headroom before improving a surface.** Randomize the decision you
were about to improve and see whether it costs anything. If it does not, no
improvement there can pay — and finding that out is far cheaper than the
improvement. `references/headroom.md` covers the instrument, the positive
control it needs, and the one inference it does not license.

**Build a ceiling, and validate it before believing anything measured against
it.** An instrument with information the system lacks bounds what any
improvement could win. `references/oracles.md` covers construction, the
validation that has to come first, and how to tell a broken label from a real
negative.

## Choosing what to spend

Two different questions get confused, and they have different costs.

*"Is this change better than what we run?"* — paired, against the current
system, on shared inputs. Cheap and high-resolution. This is the primary
readout for anything new.

*"Where does the system actually stand?"* — a level comparison against a pinned
external reference. Expensive, low-resolution, and worth doing once rather than
repeatedly. Adding more arms never tightens it, because shared inputs make the
sampling error common rather than independent. Only more inputs tighten a level.

Decide which question you are asking before spending anything.

## Coverage comes from cells, not repetitions

For finding defects rather than estimating effects, an invariant either reaches
a broken path in a given configuration or it never does. Adding a configuration
finds bugs; adding another repetition of an existing one buys time and nothing
else. Any repetition count above a handful needs a stated reason, and "more is
safer" is not one.

This inverts for effect estimation, where repetitions are exactly what buys
resolution. Know which of the two you are doing.

## Name the reference, never "the current best"

A comparison is only interpretable if the thing compared against is identified
and frozen. A reference named by a moving label — *the default*, *the champion*
— stops meaning one thing the moment the defaults move, and every number taken
against it silently becomes incomparable.

Pin a specific frozen version, name it in the same sentence as the result, and
keep it available to run against indefinitely. Any comparison that must stay
valid across a change to the defaults names the frozen reference explicitly.

Regime parameters belong in that same sentence. A threshold or population
setting that changes the problem rather than tuning it makes results taken under
different values into different experiments that do not compare — even when
every other detail matches.
