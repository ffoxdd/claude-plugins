# claude-plugins

One engineer's Claude Code preferences, published so they install the same way
on any machine rather than living in a `CLAUDE.md` that has to be copied around.

```
claude plugin marketplace add ffoxdd/claude-plugins
```

| Plugin | What it does |
| --- | --- |
| [dan-work-routing](plugins/dan-work-routing/README.md) | Classifies work as safety- or cost-governed, orders the cost regime, and says when a sub-agent is worth spawning. Ships the generic agents, the fan-out workflows, and the secret-handling rules. Install: `/plugin install dan-work-routing@ffoxdd` |
| [dan-code-style](plugins/dan-code-style/README.md) | Conventions for the code Claude writes and reviews. No enforcement. Install: `/plugin install dan-code-style@ffoxdd` |
| [dan-command-style](plugins/dan-command-style/README.md) | Allowlist-friendly Bash, enforced by one hook. Install: `/plugin install dan-command-style@ffoxdd` |
| [dan-knowledge-base](plugins/dan-knowledge-base/README.md) | The pattern for a knowledge-base repo. Brings no sources of its own. Install: `/plugin install dan-knowledge-base@ffoxdd` |
| [dan-project-defaults](plugins/dan-project-defaults/README.md) | What to pick when a project has not already decided: the ecosystem's canonical layout and tooling, a `docs/` folder, lint and format in the build. Scaffolds nothing. Install: `/plugin install dan-project-defaults@ffoxdd` |
| [dan-evidence-discipline](plugins/dan-evidence-discipline/README.md) | Measuring, and knowing what the measurement is worth: denominators, what a number licenses, and what a defect invalidates. Install: `/plugin install dan-evidence-discipline@ffoxdd` |

## Safety regimes live elsewhere

`dan-work-routing` states the *shape* — one constraint governs, safety
pre-empts cost, never a blend — and leaves the safety regime itself undefined,
because what counts as sensitive is a property of the environment rather than of
a preference. A deployment that handles regulated data supplies its own plugin
naming what falls under the regime and what the procedure is, and depends on
this one for the half that is the same everywhere.

Nothing here names an employer, a data set, or a system of record. That is what
makes it installable on a personal machine and a work machine alike.
