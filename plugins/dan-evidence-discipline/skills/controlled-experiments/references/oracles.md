# Ceiling instruments, and validating them first

An oracle is an observer with information the system does not have — the true
label, the future, the hidden state. `oracle − current` is a genuine ceiling on
what any improvement on that channel could be worth, which is the one bound a
randomization cannot give. That makes it the right tool for deciding whether a
channel deserves investment, and makes its correctness load-bearing for every
number downstream.

## Validate before you trust

**An oracle assembled from an existing component inherits that component's
question, not yours.** This is the dominant failure and it is quiet.

A worked case: a danger oracle was built from a function that correctly
answered *what would this be worth if claimed* — and knew nothing about whether
claiming was legal at all. Nearly half its positive class turned out to be
items that could never be claimed. The classifier scored against it read 0.42,
below chance; against corrected labels, 0.84. Only the label changed.

Two checks, both cheap, both before anything is measured against it:

- **Name the question the source component actually answers**, and the gap to
  the question you need. Writing that sentence out usually surfaces the
  mismatch.
- **Inspect the composition of the positive set.** "Half of my positives are
  one kind of thing" is visible at a glance and is the characteristic tell.

**A below-chance score is a label bug until proven otherwise.** Genuine signals
fail at chance, not beneath it, and a broken oracle looks exactly like a real
negative.

## Select and evaluate on disjoint samples, or the ceiling is inflated

**An oracle that picks the best candidate and scores that pick on the same
sample reports the noise it selected on.** A max over N candidates estimated
with error is biased upward — the one that looks best is disproportionately the
one whose error ran high — and evaluating on the selecting sample keeps that
error. The fix is cross-fitting: split the sample, select on one half, evaluate
on the other, average both assignments. It costs nothing but arithmetic.

The diagnostic when no split is built yet: **sweep the selection budget.** An
unbiased estimate is flat in how much evidence the oracle used to choose; a
selected one climbs as the budget grows. A worked case swept 8, 16, 32 and 48
selection samples and read the value of switching to the oracle's pick as
−1.05, −0.64, +0.46, +0.85 — monotone in the budget, never significantly
positive. The same-sample estimate had reported a ceiling more than six times
the largest honest reading, above what the programme had already certified as
an upper bound.

**Pair it with a control the bias cannot manufacture.** Best-vs-worst needs no
argmax to identify, so it stays measurable under cross-fitting. When the
control still shows the structure and the argmax value collapses, the
instrument is working and the effect was selection; when both collapse,
suspect the split.

This is a separate check from label validation because here the labels are
correct: the oracle answers the right question on the data it claims. Only the
estimator is wrong, so every check aimed at the label passes.

## When contamination is found, ask what it touches

The instinct is to discard everything measured against the bad labels; usually
too strong. A contaminated label can be **decisive for an instrument** — it
determines what a classifier is scored against — and **inert for a decision**,
whose outcome depends only on the cases where the correction changes what gets
done. In the case above, the corrected ceiling moved by a twentieth of a unit
against a contrast whose noise was a fifth: the mislabelled items were ones the
system rarely acted on. Establish which of the two the contamination reaches;
re-measuring at the same inputs is cheap and paired.

## What a ceiling does not tell you

A ceiling bounds the channel; it says nothing about whether any implementable
policy gets near it. A large ceiling is permission to look, not evidence that
something is available. Complement it with a **realizable rival** — the best
rule you can build from information the system has. The oracle bounds the
channel, the rival estimates the reachable part, and the two together say
whether to spend.
