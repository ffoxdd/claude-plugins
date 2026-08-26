# dan-command-style

Stops Claude writing shell commands that make you approve them one at a time.

```
/plugin install dan-command-style@ffoxdd
```

Injects one fact about how Claude Code matches permission rules, the habit that
follows from it, and the git-worktree rules that share its shape. Alone among
the preference plugins, this one has teeth: a PreToolUse hook denies the
`cd <dir> && git …` form and names the replacement, so a mistake becomes a retry
rather than a prompt you have to answer. Uninstalling stops it binding.
