---
description: Re-derive the most principled, most standard form of a design and diff reality against it
argument-hint: [a file, module, or decision — blank for the work at hand]
---

Run a principled-design pass over: $ARGUMENTS

If no target was given, the target is the design currently under discussion or
construction in this conversation.

First Read `${CLAUDE_PLUGIN_ROOT}/context/checkable-explanation.md` — the north
star this pass measures against: the structure of the code coincides with the
best explanation of the system, and nothing varies that the explanation doesn't
account for.

This is a north-star pass, not a bug hunt — the question is never "does it
work?" but "is this the form a domain expert would recognize?". Work through
it in this order, and write the findings up in the same order:

1. **Name the domain.** What is this problem actually called in its field?
   What are the terms of art for its parts? If the code's vocabulary and the
   field's vocabulary differ, list the translations — wrong names are findings
   on their own, because they block every future search and question.

2. **State the canonical approach.** How does the standard treatment — the
   textbook chapter, the well-known library, the pattern with a name — model
   this problem? Describe that form concretely enough to compare against, and
   name the prior art so it can be looked up.

3. **Diff reality against the canon.** Walk the current design against the
   canonical form. Every deviation is one of two things: justified by a real,
   named constraint (say which), or a finding. "It grew that way" is not a
   constraint.

4. **Hunt jank explicitly.** Workarounds that route around the design instead
   of modeling the problem; state that exists because of an earlier accident;
   special cases that a better-shaped abstraction would dissolve. For each,
   name the principled replacement.

5. **Propose the path.** Order the refactors smallest-first, and separate
   pure renames (cheap, do now) from structural moves (schedule deliberately).
   The end state should read as the domain story in the domain's own words.

6. **Teach back.** Close with the standard vocabulary and concepts worth
   adopting from this pass — the point is that the next question gets asked
   in more standard terms than this one was.
