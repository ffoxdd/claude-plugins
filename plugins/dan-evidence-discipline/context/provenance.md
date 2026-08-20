# What a result rests on, and when it dies

Results accumulate, and yesterday's measurement becomes today's assumption. A
fitted constant is not a number — it is a conclusion someone reached, which now
silently underwrites everything built on top of it. Recording provenance is what
makes it possible to find out which conclusions a newly-found defect takes with
it.

## The goal is selective invalidation, not reconstruction

An artifact that cannot say what produced it cannot be invalidated
*selectively*, so a defect anywhere forces a choice between re-measuring
everything and trusting everything. Both are bad, and the second is what
actually happens.

So the bar is not "reproduce any past run exactly". It is **enumerate the
suspects without reading prose.** The judgment about which suspects are really
affected stays human and stays hard; records exist so that judgment is made on
facts and so nothing is silently skipped.

Aim there deliberately, and stop. Chasing exactness past this point buys
precision the next section shows you cannot have anyway.

## Why exactness is unreachable

**Identity is not structure.** Recording which inputs a run consumed gives you
their identity. Deciding what a defect invalidates needs their *causal
structure* — that this table feeds that term, which feeds the decision the
metric scores. That knowledge is not a field and cannot be made into one.

**The dependency graph has cycles across time.** A system generates data; the
data is fit into parameters; the parameters feed the system. No version number
expresses "this artifact is downstream of a defect in its own producer", because
producer and product trade places on each lap.

This is why a global "data epoch" counter is the wrong instrument: it needs a
person to bump it, and its failure mode is silent staleness — the exact failure
provenance exists to escape. Content-hash lockfiles over every input are more
honest but buy an exactness the missing structure denies you.

## What to record

**The code version.** A commit identifier, on every recorded result. Without it,
a defect with a time window — introduced here, fixed there — is untraceable, and
you are reduced to matching dates against history at day granularity.

**The selectors.** Configuration and environment that choose inputs living
outside the tree. These change the result under an identical commit, so a commit
alone is not enough wherever a path, a flag, or a pointer to an external
artifact is in play.

**The regime.** The conditions the run was valid under — the thresholds,
populations, and settings that make it a different problem rather than a
different tuning. A fitted artifact that cannot state the regime it was fit
under cannot warn anyone that the regime has moved.

**Fitted artifacts carry their own card**: what produced them, from which source
data, under which regime, when. Apply this to the derived artifact, not only to
the raw data — the derived one is what gets loaded and trusted, and it is
usually the one carrying nothing.

Where a field is unrecoverable, record that it is unrecoverable. An honest gap
beats a guessed value, which is indistinguishable from a real one forever after.

## Entity tags, and the intersection rule

Tag each result, artifact, and dataset with the **entities** it touches. Two
changes are in contact when their entity sets intersect.

This does not model *how* they interact — only "these are in contact, go look",
which is the narrowing job records actually have. It is a deliberately crude
stand-in for the causal structure you cannot record.

**It errs in the correct direction, which is what makes it safe to keep crude.**
A coarse tag yields a suspect list that is slightly too large, costing someone a
look. A missing tag yields one silently too small, costing a wrong conclusion
nobody knows to revisit. Prefer over-tagging, and resist adding relevance
scoring or weighting — sophistication here only moves errors from the cheap side
to the expensive one.

**Make the vocabulary closed**: enumerate the entity names in one place and
validate against it, so a drifted synonym is rejected rather than silently
failing to intersect. Keep it small and coarse. Since over-tagging is safe,
granularity buys nothing and costs drift.

## Scale the cost to the result

Full provenance on results you would cite again — the ones that get promoted,
quoted, or built on. The minimum on exploratory probes. Most recorded results
are never read twice, and paying full freight on all of them is how the practice
gets abandoned as bureaucracy.
