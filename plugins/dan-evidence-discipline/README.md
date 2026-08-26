# dan-evidence-discipline

One engineer's discipline for empirical work — measuring, and knowing what the
measurement is worth.

```
/plugin install dan-evidence-discipline@ffoxdd
```

## What it carries

Four skills, loaded on demand: empirical work is a fraction of what a session
does, so each costs its description until a number is actually in play.

- **`measuring`** — producing a number worth trusting. A number is a property
  of (object, arm, population, instrument), never of the programme.
- **`interpreting-results`** — what a number licenses and what it does not:
  ablations, nulls, results measured under a defect, sub-noise differences.
- **`result-provenance`** — what a result rests on, recorded so a newly-found
  defect invalidates selectively instead of all-or-nothing.
- **`controlled-experiments`** — the half that depends on owning the
  data-generating process: paired comparison, headroom, ceiling instruments.
  Does not apply to observational data.

## What it does not do

Nothing is enforced — no hook, no script. It carries no statistics library, no
experiment tracker, and no opinion about tooling: the material is judgment
about evidence, not a framework for collecting it, and the two rot at different
rates.
