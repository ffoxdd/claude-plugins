---
name: result-provenance
description: What a result rests on and when it dies: recording enough about a fitted constant, corpus or generated artifact that a newly-found defect invalidates selectively instead of all-or-nothing. Covers identity versus causal structure, why a version number cannot express "downstream of a defect in my own producer", and entity tags as the cheap stand-in. Use when a defect turns up under existing results, when deciding what to re-measure, or when designing what an artifact records about itself.
---

# What a result rests on, and when it dies

Yesterday's measurement becomes today's assumption. A fitted constant is a
conclusion someone reached, silently underwriting everything built on it, and
provenance is what makes it possible to find out which conclusions a
newly-found defect takes with it.

## The goal is selective invalidation, not reconstruction

An artifact that cannot say what produced it forces a choice, on any defect,
between re-measuring everything and trusting everything — and the second is
what actually happens. So the bar is not "reproduce any past run exactly" but
**enumerate the suspects without reading prose.** The judgment about which
suspects are really affected stays human; records exist so it is made on facts
and nothing is silently skipped. Aim there and stop: exactness past this point
is unreachable anyway.

## Why exactness is unreachable

**Identity is not structure.** Recording which inputs a run consumed gives
their identity. Deciding what a defect invalidates needs their *causal
structure* — this table feeds that term, which feeds the decision the metric
scores — and that is not a field.

**The dependency graph has cycles across time.** A system generates data; the
data is fit into parameters; the parameters feed the system. No version number
expresses "downstream of a defect in its own producer".

So a global "data epoch" counter is the wrong instrument — it needs a person to
bump it and fails as silent staleness, the exact failure provenance exists to
escape. Content-hash lockfiles are more honest but buy an exactness the missing
structure denies you.

## What to record

- **The code version** — a commit identifier on every result. Without it a
  defect with a time window is traceable only by matching dates at day
  granularity.
- **The selectors** — configuration and environment that choose inputs outside
  the tree: a path, a flag, a pointer to an external artifact. These change the
  result under an identical commit.
- **The regime** — the thresholds, populations and settings that make a run a
  different problem rather than a different tuning. An artifact that cannot
  state its regime cannot warn that the regime has moved.
- **Fitted artifacts carry their own card**: what produced them, from which
  source data, under which regime, when. The derived artifact is what gets
  loaded and trusted, and usually the one carrying nothing.

Where a field is unrecoverable, record that. An honest gap beats a guessed
value, which is indistinguishable from a real one forever after.

## Entity tags, and the intersection rule

Tag each result, artifact and dataset with the **entities** it touches; two
changes are in contact when their entity sets intersect. This models "go look",
not how they interact — a deliberately crude stand-in for the structure you
cannot record.

**It errs in the correct direction.** A coarse tag yields a suspect list
slightly too large, costing someone a look; a missing tag yields one silently
too small, costing a wrong conclusion nobody revisits. Over-tag, and resist
relevance scoring — sophistication here moves errors from the cheap side to the
expensive one.

**Make the vocabulary closed**: enumerate the entity names in one place and
validate against it, so a drifted synonym is rejected rather than silently
failing to intersect. Keep it small and coarse; granularity buys nothing and
costs drift.

## Scale the cost to the result

Full provenance on results you would cite again — promoted, quoted, built on.
The minimum on exploratory probes. Most recorded results are never read twice,
and paying full freight on all of them is how the practice gets abandoned as
bureaucracy.
