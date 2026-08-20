# Producing a number worth trusting

How to measure, for empirical work of any kind — an experiment, a model
evaluation, a query against production data. Design defaults, held loosely; any
of them yields when the problem genuinely disagrees.

One principle generates the rest: **a number is a property of (object, arm,
population, instrument) — never of the program.** Every rule below is that
sentence applied to whichever of the four gets dropped, and in practice one
always does, because prose summaries shed qualifiers in that order.

## Name the population

Every rate carries its denominator in the same sentence. "89% of opportunities",
"0.2% of the actions actually taken", "of the states the policy visits" are
three different numbers about the same system, and they routinely differ by two
orders of magnitude.

**Never multiply two population-wide rates to size an effect on a narrower
population.** The joint is almost always available in the same query that
produced the marginals; compute it directly. Two correctly-measured rates
multiplied together produce a confidently wrong third.

Before acting on a rate, ask which population the *action* would touch. A change
applies to the states the system actually reaches, so a rate over all
opportunities is not the one that governs it.

## Name the arm

A measurement describes the variant that produced it. Work generates many
variants and most are rejected; their numbers stay in the documents and start
reading like facts about the system.

Every number entering a decision carries its arm in the same sentence —
"shipped, with the refit on: 1.000" beside "diagnostic variant, residue removed:
1.246". Before building on a prior number, re-derive it on the variant that is
actually deployed. If the premise turns out to be stale, say so plainly and
early; that is a finding, not an interruption.

## Name the instrument, and validate it first

The instrument is the one people forget, and it fails in a way that mimics a
real result.

**An oracle or label set assembled from an existing component inherits that
component's question, not yours.** Name the question it actually answers and the
gap to the one you need. Before trusting anything measured against it,
hand-check a sample of its positives and inspect what the positive set is made
of — "half of my positive class is one kind of thing" is visible immediately and
is the tell.

**A below-chance score is a label bug until proven otherwise.** Genuine signals
fail at chance, not below it. One measured case: the same classifier scored 0.42
against contaminated labels and 0.84 against corrected ones, with nothing but
the label changed.

**An absent column means the recorder does not populate it, not that the
quantity cannot be computed.** A zero from an instrument nobody verified was
populated is indistinguishable from a measured null in the output. Before
concluding "X cannot be known", check the system that would compute it rather
than the corpus that happens not to carry it.

When contamination turns up, ask which object it touches before discarding
anything downstream. A bad label can be decisive for an *instrument* — it
determines what a classifier is scored against — and completely inert for a
*decision*, whose outcome depends only on the cases the correction actually
changes. Prefer re-measuring to discarding the arithmetic.

## Match resolution to the contrast

Choose a representation's resolution by what the decision *differentiates*, not
by what predicts outcomes on average. A coarse metric can be the best predictor
of levels while being useless for the deltas or rankings a decision compares —
the decision often lives entirely in what the coarse metric quotients away.

Before reusing a validated metric in a new decision context, ask: what does this
decision contrast, and does the metric move across that contrast?
**Levels-validated is not ranking-valid.**

**A metric conditioned on success is invalid when the change moves the
conditioning population.** Mean-outcome-among-winners can confirm at high
significance while the system collapses, because the survivors are a selected
subset. A conditioned primary needs either a stability guard on the conditioning
population or an unconditioned companion, decided before the run rather than
after.

## Conditioning on the system's own choices

A validation conditioned on what the system chose can never certify those
choices. Selection at the maximum picks the candidate whose estimate errs
upward, so conditioning on what was chosen marginalizes away precisely the
contrast the decision consumed.

Consequences worth holding: a calibration over chosen rows supports a *pricing*
claim, never a *decision* claim; decision claims need an instrument that sees
the margin — recorded runner-up contrasts, a forced-flip probe, or an override
variant. And when designing a correction, check that the population you would
fit it on can even see the error before fitting it.

## Do not move the baseline

Structural correctness earns a place in the codebase, never a place in the
baseline. Keeping something on principle is a decision about what code exists;
it is not a reason to move the yardstick everything else is measured against.

A change at a negative point estimate stays available and off by default, and
the stated baseline remains the system without it until it demonstrably pays.
Re-admit on evidence. "Kept for generality" must never appear in the same
sentence as "new baseline" — that silently ratchets the reference point
downward, and a real regression can be laundered into parity one step at a time.

A give-away large enough to notice is a debt with a mechanism to find, and
non-significance is not a reason to leave it alone. Say plainly that it is not
significant; do not use that to avoid the chase.
