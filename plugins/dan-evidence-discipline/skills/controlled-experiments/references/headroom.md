# Headroom: what is this surface worth at all?

Before improving a decision surface, find out whether decisions on it move the
outcome. The question is almost never asked, and it is far cheaper than the
improvement it might make unnecessary.

The case that motivates it: three rounds of work went into a decision surface,
producing two variants whose behaviour differed by nearly twice — and whose
outcomes were identical to within a fifth of a unit, flat in every channel,
while the signal they acted on predicted its own target at high significance.
Nobody had asked whether the surface carried any outcome value. It did not.

## The instrument

Replace the system's choice on the target surface with a uniform random legal
choice, seeded deterministically from the input and the decision index so the
run stays reproducible and pairing still works. Measure paired against the
current system. The loss is what the current policy extracts on that surface
over no information.

## What it licenses

It measures `current − random`, not `optimal − current`: large means the
surface is decision-relevant, small is ambiguous and must never become a
stopping rule. The `interpreting-results` skill carries that argument and the
rival/oracle substitution that turns "this surface matters" into "how much are
we capturing".

**Run the positive control first**: randomize the whole surface, not just the
part under study. If that does not clearly hurt, the harness is broken. It is
cheap and it fails loudly.

## Partition to get a map

Perturbing slices separately — the region a policy covers versus the region it
does not, early versus late states, cases by difficulty — yields a map of where
outcome value actually lives. That is usually a question the programme has
never asked directly, and the answer reshapes priorities more than any single
improvement does.

Perturb only states the system actually visits, and report that denominator. A
surface that looks important across all opportunities can be irrelevant across
the ones the system reaches.
