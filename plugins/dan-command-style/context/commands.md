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
