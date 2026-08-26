# Paired comparison

## Why it is the default

Run two arms over the same inputs — same seeds, same suite, same fixtures — and
compare them input by input rather than comparing their averages. Most of the
variance in a run is a property of the *input* — which cases are easy, which
draws are lucky — and that component is common to both arms on a shared input,
so differencing removes it.

A measured instance: the same change read −3.10 ± 2.14 against an external
reference and +0.34 ± 0.52 paired against the current system, on the same 800
inputs — roughly four times the resolution for the same compute. The unpaired
contrast could not resolve anything smaller than about four units, larger than
every effect that programme had ever chased, and two rounds of work went into
explaining a difference that was never distinguishable from noise.

## The procedure

1. Fix an input set and use it for both arms.
2. Vary exactly one thing. If the arms differ in more than the change under
   test — build, reference, regime setting — the difference is not
   attributable.
3. Difference per input, then aggregate the differences. Aggregating each arm
   first discards the pairing.
4. Cancel any structural asymmetry the setup imposes. Where position, ordering,
   or role carries its own effect, run both assignments and cancel across them
   rather than trusting it to average out.

## What pairing cannot do

**It does not tighten a level.** "How good is this system, absolutely?" is
answered against an external reference, and shared inputs make that sampling
error common across arms rather than independent — so more arms do nothing and
only more inputs help. Budget for it once.

**It does not license a mechanism story from a small difference**, and pooling
repeated comparisons needs the heterogeneity reported beside the estimate. The
`interpreting-results` skill carries both.

## The reproducibility precondition

All of this assumes the same inputs really do produce the same run. Verify it:
run the identical configuration twice and confirm the outputs match.

Where they do not, find out why before measuring anything. Shared mutable state
across runs, thread scheduling reaching decisions, or an unseeded source of
randomness each put a floor under your resolution — invisible, because it looks
exactly like a small real effect. A known nondeterminism floor means every
comparison needs its own control run to establish it, a permanent tax until
fixed.
