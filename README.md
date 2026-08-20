# claude-plugins

One engineer's Claude Code preferences, published so they install the same way
on any machine rather than living in a `CLAUDE.md` that has to be copied around.

```
claude plugin marketplace add ffoxdd/claude-plugins
claude plugin install dan-code-style@ffoxdd
```

| Plugin | What it does |
| --- | --- |
| `dan-work-routing` | Classifies work as safety- or cost-governed, orders the cost regime, and says when a sub-agent is worth spawning. Ships the generic agents and the secret-handling rules. |
| `dan-code-style` | Conventions for the code Claude writes and reviews. No enforcement. |
| `dan-command-style` | Allowlist-friendly Bash, enforced by one hook. |
| `dan-knowledge-base` | The pattern for a knowledge-base repo. Brings no sources of its own. |

## Safety regimes live elsewhere

`dan-work-routing` states the *shape* — one constraint governs, safety
pre-empts cost, never a blend — and leaves the safety regime itself undefined,
because what counts as sensitive is a property of the environment rather than of
a preference. A deployment that handles regulated data supplies its own plugin
naming what falls under the regime and what the procedure is, and depends on
this one for the half that is the same everywhere.

Nothing here names an employer, a data set, or a system of record. That is what
makes it installable on a personal machine and a work machine alike.
