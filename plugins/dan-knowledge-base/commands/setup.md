---
description: Fix the prerequisites for the sources this knowledge base declares
---

Walk the user through the prerequisites for **the sources this knowledge base
already declares** — never for sources it doesn't. Do every check yourself; for
the steps only the user can perform, give the exact command and wait for them
to confirm before moving on.

1. **Read what is declared.** Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/provision.py"` and read its notes.
   Each note becomes a step below. If it prints nothing, everything the
   register declares is set up — say so and stop. If it reports no register at
   all, this is not a knowledge base: offer `/dan-knowledge-base:init`.

2. **Resolution**, if the register declares the `chat` adapter. Run
   `command -v slack-client` yourself: provisioning runs in a hook, whose
   environment is not the one your Bash tool uses, so only a call from here
   answers the question. Expect a path inside this plugin's `bin/`, which
   Claude Code puts on PATH for every installed plugin. If it resolves
   somewhere else, that is someone's own copy standing in for the shipped one —
   show both paths and let them decide; do not remove theirs. If it resolves
   to nothing, the plugin is not installed in this session; have them check
   `/plugin` rather than adding a symlink that goes stale at the next version.

3. **`uv`.** Both shipped adapters and the bundled `slack-client` are
   `uv run --script` files with inline dependencies, so nothing works without
   it. Nothing here installs it; give them Astral's own installer —
   `curl -LsSf https://astral.sh/uv/install.sh | sh` on macOS and Linux,
   `powershell -c "irm https://astral.sh/uv/install.ps1|iex"` on Windows — and
   re-check with `uv --version`.

4. **The chat adapter's one-off setup**, if the register declares it, in this
   order — each step's failure looks like the previous step's success:

   - `uv run --with playwright playwright install chromium` — downloads the
     browser the login flow drives. Needs a desktop session; a headless
     container or GUI-less WSL cannot complete the next step.
   - `slack-client login` — opens a real browser and waits for the user to sign
     in, capturing the session to `~/.cache/slack-client/session.json`. Only
     they can do this, and from **inside a Claude Code session** —
     `! slack-client login` — since the launcher is on PATH only there. Say
     plainly what it captures: a credential as sensitive as their Slack login,
     local-only, never to be committed or copied into a secret manager.
   - Confirm with a read-only call that touches no content, e.g.
     `slack-client memberships`.

5. **The email adapter's credential**, if the register declares it. It borrows
   a mail MCP server's existing token cache, so the fix is to sign in through
   that server once and re-run the check. A cache that is present but rejected
   is an **expired** credential, not a missing one — the remedy is a fresh
   sign-in. Say which of the two you are looking at.

6. **Permissions.** None to add — say so and move on. A PreToolUse hook in this
   plugin approves the reads a sync runs. Two things still prompt, both
   deliberately: `slack-client login`, and any call that chains a second
   command. A `Bash(slack-client *)` entry carried from an earlier version is
   harmless and needs no removing.

7. **Re-run `provision.py`.** Silence is the confirmation. Then offer, without
   running it unbidden, a first sync against a deliberately recent watermark so
   the initial run is small rather than a backfill of all history — started by
   asking "sync the knowledge base".

Close with what is configured, what remains, and — for anything still unset —
that the next sync will skip that source and record the skip in the watermarks,
so the gap stays visible in the repo.
