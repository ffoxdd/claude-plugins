# dan-evidence-discipline

One engineer's discipline for empirical work — measuring, and knowing what the
measurement is worth.

Install:

```
/plugin install dan-evidence-discipline
```

## What it carries

Four skills, all loaded on demand. Empirical work is a fraction of what a
session does, so these carry a standing cost of their descriptions alone and
pull in their bodies when a number is actually in play.

**`measuring`** — producing a number worth trusting. One principle
generates the file: a number is a property of (object, arm, population,
instrument), never of the programme. Naming each of the four, validating an
instrument before believing it, matching a metric's resolution to the contrast a
decision actually makes, and why structural correctness never moves a baseline.

**`interpreting-results`** — what a number licenses. The inferences that look valid
and are not: reading an ablation as a ceiling, reporting a null without checking
the change reached the system, treating results measured under a defect as
worthless rather than as non-transferable, and reading a mechanism off a
difference that never cleared noise.

**`result-provenance`** — what a result rests on and when it dies. Recording
enough that a defect can be invalidated *selectively*, why exact traceability is
unreachable (identity is not structure, and the dependency graph has cycles
across time), and the entity-intersection rule that stands in for the structure
you cannot record.

**`controlled-experiments`** covers the half that depends on owning the
data-generating process: pairing against a pinned reference, measuring a
surface's headroom before improving it, and building a ceiling instrument you
can trust. It loads on demand, because it applies to simulations, self-play and
evaluation harnesses — and specifically does not apply to observational data,
where the intervention already happened and the procedures have different
counterparts resting on different assumptions.

## What it does not do

Nothing here is enforced. No hook blocks a tool call, no script rewrites
anything — the plugin only puts the conventions in front of Claude.

It also carries no statistics library, no experiment tracker, and no opinion
about tooling. The material is judgment about evidence, not a framework for
collecting it, and the two rot at different rates.
