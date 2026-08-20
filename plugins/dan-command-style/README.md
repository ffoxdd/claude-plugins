# dan-command-style

Stops Claude writing shell commands that make you approve them one at a time.

## What it does

Injects one fact about how Claude Code matches permission rules at every session
start, plus the habit that follows from it. Alone among the preference plugins,
this one also has teeth: a PreToolUse hook refuses the awkward form and tells
Claude the replacement, so a mistake becomes a retry rather than a prompt you
have to answer.

One convention, stated as the fact it rests on plus the rule that follows —
so the fact is still useful to someone who declines the rule.

A Bash call is matched against the permission allowlist as written, so shell
variables and `$(…)` defeat a rule like `Bash(git *)`; separately, a compound
command starting with `cd` trips gates built into Claude Code that no
allow-rule suppresses. The rule: prefer `git -C <dir>` and literal paths,
which are semantically identical and give up nothing. A PreToolUse hook denies
the `cd`-then-git form and names the replacement — the only enforcement in any
preference plugin here, and uninstalling stops it.
