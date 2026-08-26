# Command conventions

A preference resting on a fact about Claude Code; the fact holds either way.

## Invoking commands

**The fact:** a Bash call is matched against the permission allowlist as
written. Shell variables, `$(…)`, and `${VAR}` — including in redirect targets
— defeat a rule like `Bash(git *)`, so the call prompts. Separately, a compound
command starting with `cd` trips gates built into Claude Code that no allow-rule
suppresses.

**The rule:** write statically-analyzable Bash. Use `git -C <dir>` and literal
absolute paths rather than `cd <dir> && …`; the two are semantically identical.
To run a command over several paths, issue one fully-literal call per path or
iterate inside Python — a shell `for` loop still substitutes in its body.

A PreToolUse hook denies the `cd`-then-git form and names the replacement.

## Git worktrees

- Name the directory `<repo>-<branch>` (`/` in the branch becomes `-`) at
  `git worktree add` time, so `git worktree list` is self-documenting.
- Assume several worktrees share one `.git`. `HEAD`, the index, and
  `refs/bisect|worktree|rewritten` are per-worktree; every other ref is shared,
  `refs/stash` included.
  - **Never `git stash`.** One global stack: a `pop` anywhere takes whatever is
    on top, so work crosses between trees and a conflicted `pop` strands an
    unrelated branch mid-merge; `-m` does not help. Set work aside with a WIP
    commit, undone by `git reset --soft HEAD^`. In scripts, `git stash create`
    returns a commit without touching refs; park it under `refs/worktree/<name>`
    if it needs a name.
  - **Never `git checkout <other-branch>` to inspect it** — it disturbs the
    tree, and git refuses when the branch is checked out elsewhere. Use
    `git show <rev>:<path>`, `git -C` against that branch's own worktree, or a
    throwaway `git worktree add`.
- **Never silence a state-changing git command.** `-q` / `2>/dev/null` on
  `stash`, `checkout`, `reset`, `merge` hides the one line saying it did
  something other than intended. Quiet flags are for read-only commands.
