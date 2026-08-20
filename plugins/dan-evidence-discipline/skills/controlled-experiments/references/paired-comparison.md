# Paired comparison

## Why it is the default

Run two arms over the same inputs — same seeds, same suite, same fixtures — and
compare them input by input rather than comparing their averages. Most of the
variance in a run is a property of the *input* rather than the arm: which cases
are easy, which draws are lucky, which starting positions favour whom. That
component is common to both arms on a shared input, so differencing removes it.

A measured instance: the same change read −3.10 ± 2.14 against an external
reference and +0.34 ± 0.52 paired against the current system, on the same 800
inputs. Roughly four times the resolution for the same compute. The unpaired
contrast could not resolve anything smaller than about four units — larger than
every effect that programme had ever chased, which meant two rounds of work were
spent explaining a difference that was never distinguishable from noise.

## The procedure

1. Fix an input set and use it for both arms.
2. Vary exactly one thing. If the two arms differ in more than the change under
   test — a different build, a different reference, a different regime setting —
   the difference is not attributable.
3. Difference per input, then aggregate the differences. Do not aggregate each
   arm and then subtract; that discards the pairing.
4. Cancel any structural asymmetry the setup imposes. Where position, ordering,
   or role carries its own effect, run both assignments and cancel across them
   rather than trusting the effect to average out.

## What pairing cannot do

**It does not tighten a level.** "How good is this system, absolutely?" is
answered against an external reference, and shared inputs make that sampling
error common across arms rather than independent. Adding arms does nothing for
it; only more inputs help. Budget for it once rather than repeatedly.

**It does not license a mechanism story from a small difference.** A paired
contrast that does not clear noise is not a finding with a direction. Before
authoring an explanation for one, check whether a better-resolved instrument can
bound it first.

## Pooling several runs

Where a comparison is repeated over disjoint input sets, combine them by
inverse-variance weighting and **report the heterogeneity beside the estimate.**
A pooled number hiding wide disagreement among its inputs is worse than any
single input, because the disagreement is the finding.

Two runs are not enough to assess heterogeneity — the statistic is too noisy at
that size to distinguish real disagreement from sampling. Expect to need
several, and be explicit that early pooled numbers are provisional rather than
treating the first two as a verdict.

## The reproducibility precondition

All of this assumes the same inputs really do produce the same run. Verify it
rather than assuming: run the identical configuration twice and confirm the
outputs match.

Where they do not, find out why before measuring anything. Shared mutable state
across runs, thread scheduling reaching decisions, or an unseeded source of
randomness will each put a floor under your resolution — and that floor is
invisible, because it looks exactly like a small real effect. A known
nondeterminism floor also means every comparison needs its own control run to
establish the floor, which is a permanent tax until it is fixed.
