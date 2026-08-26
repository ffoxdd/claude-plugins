---
name: themed-commits
description: Requirements on a branch's final shape — each commit one revert-coherent theme, green on its own, fewer and larger over many and pure. Use when committing non-trivial work, when deciding whether work is one commit or several, or when splitting, squashing, or otherwise reorganizing a branch's commits.
---

# Themed commits

Requirements on a branch's final shape, not a workflow. However the work
actually happened, the history that ships satisfies these; the flow at the end
is one way to get there.

## The requirements

- **Each commit is a theme** — one atomic unit of work. The single-concept
  rule is held loosely: prefer fewer total commits, and resolve an ambiguous
  grouping toward the larger commit.

- **The revert lens sizes a theme.** Whatever someone would plausibly want to
  revert together belongs together. Test a grab-bag by asking what the
  consequences are of wanting to revert one small line out of it — usually
  none, so it stays together. A piece with a genuine independent revert story
  earns its own commit.

- **Every commit is green on its own** — it builds and passes tests. This
  requirement is hard where the others are soft: it is what lets bisect land
  on a cause and revert produce a working tree at any point in history.

- **Companions ride with their theme.** Tests land in the commit with the code
  they test, which is what keeps the green requirement meaningful. A
  mechanical move or rename stays separate from behavioral edits to the moved
  code — blended, the edit hides inside a rename-sized diff.

- **The message names the theme**: one claim in the subject line. A commit
  that cannot be titled as one claim is two themes, or half of one.

## Reshaping history that doesn't satisfy them

Ideas blended across commits usually mean the code separates too — disjoint
ideas touch disjoint code. Don't attempt surgical history editing: soft-reset
the run of commits back to its base and re-stage by theme — `git add` per
file, `-p` where one file mixes themes — committing green each time. The same
flow merges commits that were too small and splits commits that blended
themes.
