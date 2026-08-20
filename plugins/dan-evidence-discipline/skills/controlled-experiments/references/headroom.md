# Headroom: what is this surface worth at all?

Before improving a decision surface, find out whether decisions on it move the
outcome. The question is almost never asked, and it is far cheaper than the
improvement it might make unnecessary.

The case that motivates it: three rounds of work went into improving a decision
surface, producing two variants whose behaviour differed by nearly twice — and
whose outcomes were identical to within a fifth of a unit, flat in every
channel, while the signal they acted on predicted its own target at high
significance. Nobody had asked whether that surface carried any outcome value in
the first place. It did not.

## The instrument

Replace the system's choice on the target surface with a uniform random legal
choice, seeded deterministically from the input and the decision index so the
run stays reproducible and pairing still works. Measure paired against the
current system.

The magnitude of the loss is what the current policy extracts on that surface
over no information — the value the surface carries as the system currently uses
it.

## What it licenses, and what it does not

It measures `current − random`. That is **not** an upper bound on
`optimal − current`.

- **Large ⟹ the surface is decision-relevant.** Valid, and the only direction
  the instrument supports.
- **Small ⟹ ambiguous.** Either the surface does not matter, or the current
  policy is no better than chance on it — and the second case is where a new
  approach has the *most* room, not the least.

So a small headroom must never become a stopping rule. To turn "this surface
matters" into "how much of it are we capturing", substitute a **rival** — a
better rule, or an oracle — and measure paired. That contrast is the one that
says whether the current object earns its keep.

## The positive control

Randomize the whole surface, not just the part under study. If that does not
clearly hurt, the wiring or the harness is broken and nothing measured through
it means anything. Run this first; it is cheap and it fails loudly.

## Partition to get a map

Perturbing different slices separately — the region a policy covers versus the
region it does not, states early versus late, cases by difficulty — yields a
map of where outcome value actually lives. That is usually a question the
programme has never asked directly, and the answer reshapes priorities more than
any single improvement does.

Perturb only states the system actually visits, and report that denominator. A
surface that looks important across all opportunities can be irrelevant across
the ones the system reaches.
