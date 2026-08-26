# dan-code-style

Teaches Claude the conventions you would otherwise re-explain every session —
naming, structure, formatting, what to write down and what to leave out — and a
standing stance: build things the most normal way, in the field's own terms of
art, and refactor toward the principled form as it comes into view.

```
/plugin install dan-code-style@ffoxdd
```

Nothing is enforced. Claude reads the conventions and follows them, the same way
it follows text pasted into a `CLAUDE.md`; what you gain over pasting is that an
edit here reaches everyone who installed it.

## What it carries

- **`context/conventions.md`** — one document injected at session start. It
  opens with the principle that generates the rest: the structure of the code
  coincides with the best explanation of the system, and nothing varies that
  the explanation doesn't account for. Everything below is that principle
  applied at a particular scale, from a variable name to the deployment story.
- **`/dan-code-style:principled [target]`** — a deliberate pass against the
  essay in `context/checkable-explanation.md`: name the domain, state the
  canonical approach, diff the design against it with every deviation either
  justified by a named constraint or reported, hunt jank, and propose the
  refactor path smallest-first.
- **`path-independence` agent** — reads a diff's comments, docs, PR and review
  text for prose whose meaning depends on a previous version: stated history,
  and the harder shape, a contrastive reassurance that only lands for someone
  who saw the old state. Cheap tier on purpose, so it can run on everything.
