# Ceiling instruments, and validating them first

An oracle is an observer with information the system does not have — the true
label, the future, the hidden state. Its value is that `oracle − current` is a
genuine ceiling: it bounds what any improvement on that channel could ever be
worth, which is the one bound a randomization cannot give you.

That makes it the right tool for deciding whether a channel deserves investment,
and it makes its correctness load-bearing for every number downstream.

## Validate before you trust

**An oracle assembled from an existing component inherits that component's
question, not yours.** This is the dominant failure and it is quiet.

A worked case: a danger oracle was built from a function that correctly answered
*what would this be worth if claimed* — and knew nothing about whether claiming
was legal at all. Nearly half its positive class turned out to be items that
could never be claimed. The classifier scored against it read 0.42, below
chance; against corrected labels, 0.84. **Only the label changed.**

Two checks, both cheap, both before anything is measured against it:

- **Name the question the source component actually answers**, and state the gap
  to the question you need. Writing that sentence out is usually enough to
  surface the mismatch.
- **Inspect the composition of the positive set.** "Half of my positives are one
  kind of thing" is visible at a glance and is the characteristic tell.

**Treat a below-chance score as a label bug until proven otherwise.** Genuine
signals fail at chance, not beneath it. A broken oracle looks exactly like a
real negative result, which is what makes this worth a standing rule.

## Select and evaluate on disjoint samples, or the ceiling is inflated

**An oracle that picks the best candidate and scores that same pick on the same
sample reports the noise it selected on.** Taking a max over N candidates whose
values are estimated with error biases the winner upward — the candidate that
looks best is disproportionately the one whose error ran high. Evaluating it on
the sample that chose it keeps the error.

The fix is cross-fitting: split the sample, select on one half, evaluate on the
other, then average both assignments. It costs nothing but arithmetic.

The diagnostic, when a split is not yet built: **sweep the selection budget.** An
unbiased estimate is flat in how much evidence the oracle used to choose; a
selected one climbs as the budget grows and the bias shrinks. A worked case swept
8, 16, 32 and 48 selection samples and read the value of switching to the
oracle's pick as −1.05, −0.64, +0.46, +0.85 — monotone in the budget, and never
significantly positive at any of them. The same-sample estimate had reported a
ceiling more than six times the largest honest reading, and above what the
programme had already certified as an upper bound.

**Pair it with a control the bias cannot manufacture.** Best-vs-WORST needs no
argmax to identify, so it stays measurable under cross-fitting. When the control
still shows the structure and the argmax value collapses, the instrument is
working and the effect was selection. When both collapse, suspect the split.

This is worth stating separately from validating an oracle's labels, because the
labels here are correct. The oracle answers exactly the right question, on data
that is exactly what it claims to be. Only the estimator is wrong, so every check
aimed at the label passes.

## When contamination is found, ask what it touches

The instinct is to discard everything measured against the bad labels. Usually
too strong.

A contaminated label can be **decisive for an instrument** — it determines what
a classifier is scored against — and **completely inert for a decision**, whose
outcome depends only on the cases where the correction changes what gets done.
In the case above, the corrected ceiling moved by a twentieth of a unit against
a contrast whose noise was a fifth: the mislabelled items were ones the system
rarely acted on anyway.

So before declaring downstream work unreliable, establish which of the two the
contamination reaches. Re-measuring at the same inputs is cheap and paired; a
blanket discard throws away arithmetic that was mostly fine.

## What a ceiling does not tell you

A ceiling bounds the channel; it says nothing about whether any implementable
policy gets near it. A large ceiling is permission to look, not evidence that
something is available — the gap between an oracle with hidden information and
the best rule using only visible information can be most of the ceiling.

Where possible, complement the oracle with a **realizable rival**: the best rule
you can actually build from information the system has. The oracle bounds the
channel, the rival estimates the reachable part, and the two together say
whether to spend.
