---
name: canonical-choices
description: What to pick when a project has not already decided — the ecosystem's canonical layout, its canonical libraries and tools, a docs/ folder, and a linter and formatter wired into the build. Use when starting a project or a component, adding a library or a tool to one with no precedent, or laying out a directory tree. A project that has already chosen keeps its choice.
---

# Canonical choices

For a decision a project has not already made. A project that has chosen keeps
its choice; these are the defaults for an open question, not a migration plan.

## Take the ecosystem's canonical answer

**Lay the project out the way its ecosystem lays projects out**, and reach for
the library its ecosystem reaches for. Not the layout that seems tidiest, and
not the dependency with the nicest API — the one a practitioner in that
ecosystem would expect to find. Where a language has an official layout, a
default project generator, or a standard library that already covers the need,
that is the answer.

Canonical shapes compound: the model's training bears directly on them, tooling
assumes them, and a newcomer needs no orientation. This is the same principle
the code conventions apply to modeling a problem, applied here to the choices
made before any code exists.

**The one tiebreaker is modernity where it is also correctness.** Where an
ecosystem is split between an entrenched older tool and a newer one that is
clearly better and clearly winning, take the newer one — `uv` over `pip` and
hand-managed virtualenvs is the shape of this. A tool that is merely newer, or
merely fashionable, does not qualify; the older canonical choice wins by
default and the deviation has to be argued.

Where the canonical answer genuinely does not fit, say which constraint rules
it out, next to the deviation.

## Every project gets a `docs/`

Markdown, in a `docs/` directory, from the beginning. Its audience is both the
people working on the project and the agents working on it, which mostly means
writing down what neither can read off the code: why a decision went the way it
did, what a subsystem is for, and the constraints that are not visible in any
one file.

Write it so an agent can act on it — state the invariant rather than gesture at
it — and let the directory tree be its own index.

## Lint and format in the build

A linter and an automatic formatter, both wired into the build and CI so a
violation fails rather than accumulating — not a manual step, and not only a
pre-commit hook.

The ecosystem's own tools here too, configured as little as possible, so that
every editor and every checkout agree.
