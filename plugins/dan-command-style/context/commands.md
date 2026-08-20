# Command conventions

A preference, not mechanism. It rests on a fact about how Claude Code behaves;
the fact is worth knowing either way, and the rule is one defensible response
to it.

## Invoking commands

**The fact:** a Bash call is matched against the permission allowlist as
written. Shell variables, `$(…)`, and `${VAR}` — including in redirect targets
— defeat a rule like `Bash(git *)`, so the call prompts. Separately, a
compound command starting with `cd` trips gates built into Claude Code that no
allow-rule suppresses.

**The rule:** write statically-analyzable Bash. Use `git -C <dir>` and literal
absolute paths rather than `cd <dir> && …` — the two are semantically
identical, so nothing is given up. To run a command over several paths, issue
one fully-literal call per path, or iterate inside Python; a shell `for` loop
does not help, since its body still substitutes.

A PreToolUse hook in this plugin denies the `cd`-then-git form and names the
replacement, turning a prompt into a retry. Uninstall the plugin and the
convention stops binding.

## Git worktrees
- **Name the directory `<repo>-<branch>`** (replace `/` in the branch with `-`) at `git worktree add` time, so `git worktree list` is self-documenting.
- **Assume several worktrees share one `.git`** (`git worktree list` to see). `HEAD`, the index, and `refs/bisect|worktree|rewritten` are per-worktree; everything else in the ref namespace is **shared**, `refs/stash` included.
  - **Never `git stash`.** One global stack: your push is visible to every worktree, and a `pop` anywhere takes whatever is on top — so you can hand your work to someone else's tree, or pull theirs into yours, and a conflicted `pop` strands an unrelated branch mid-merge. Naming with `-m` does not help; bare `pop` ignores messages and indices shift under you. Set work aside with a WIP commit instead (`HEAD` is per-worktree), undone by `git reset --soft HEAD^`. In scripts, `git stash create` returns a commit *without* touching the ref namespace; park it under the per-worktree `refs/worktree/<name>` if it needs a name.
  - **Never `git checkout <other-branch>` just to inspect it** — it disturbs your tree, and git refuses outright when that branch is checked out in another worktree. Read other revisions with `git show <rev>:<path>`, point tools at that branch's own worktree via `git -C`, or `git worktree add` a throwaway.
- **Never silence a state-changing git command.** `-q` / `2>/dev/null` on `stash`, `checkout`, `reset`, `merge` hides the one line saying it did something other than intended ("No local changes to save", "is already used by worktree"). Quiet flags are for read-only commands.
