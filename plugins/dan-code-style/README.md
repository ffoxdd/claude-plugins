# dan-code-style

Teaches Claude the conventions you would otherwise re-explain every session —
naming, structure, what to write down and what to leave out — plus a stance on
solving problems the ordinary way instead of inventing a new one.

## What it does

Loads a conventions document at every session start, and adds one command,
`/principled`, that reviews code against them deliberately.

Nothing is enforced. Claude reads the conventions and follows them, the same way
it follows text pasted into a `CLAUDE.md`. What you gain over pasting is that an
edit here reaches everyone who installed it.

House conventions injected at session start, leading with a standing stance:
build things the most normal way, in the field's own terms of art, and
refactor toward the principled form as it comes into view. Standard shapes
compound — they let the model's training bear directly on the code, and the
vocabulary it teaches back makes your next question more standard too.

It also carries the review standard — every loaded rule gets its own pass, a
convention violation is proved by quoting the rule, a claimed defect needs a
concrete failure — which is what keeps the rest of the conventions from being
decorative.

`/principled [target]` runs that stance as a deliberate pass: name the domain,
state the canonical approach, diff the design against it with every deviation
either justified by a named constraint or reported, hunt jank explicitly, and
propose the refactor path smallest-first. The pass measures against the
unifying principle in `context/checkable-explanation.md` — the structure of
the code coincides with the best explanation of the system, and nothing varies
that the explanation doesn't account for.

`path-independence` is an agent for the one rule a person cannot reliably keep
while making the change: text describes its subject, never the route that
reached it. It reads a diff — code comments, docs, PR and issue text, review
comments — for stated history and for the harder shape, a contrastive
reassurance that only lands for someone who saw the old state. It runs at a
cheap tier on purpose, because a check narrow enough to run on everything is
worth more than one good enough to run occasionally.
