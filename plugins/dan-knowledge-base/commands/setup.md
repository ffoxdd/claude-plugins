---
description: Fix the prerequisites for the sources this knowledge base declares
---

Walk the user through the prerequisites for **the sources this knowledge base
already declares** — never for sources it doesn't. Do every check yourself; for
the steps only the user can perform, give the exact command and wait for them to
confirm before moving on.

1. **Read what is declared.** Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/provision.py"` and read its notes.
   Each note becomes a step below. If it prints nothing, everything the register
   declares is set up — say so and stop. If it reports no register at all, this
   is not a knowledge base: offer `/dan-knowledge-base:init`.

2. **Resolution**, if the register declares the `chat` adapter. Run
   `command -v slack-client` yourself: provisioning runs in a hook, whose
   environment is not the one your Bash tool runs commands in, so only a call
   from here answers the question. Expect a path inside this plugin's `bin/`,
   which Claude Code puts on PATH for every installed plugin. If it resolves
   somewhere else, that is someone's own copy standing in for the shipped one —
   show them both paths and let them decide. Do not remove theirs for them. If
   it resolves to nothing, the plugin is not installed in this session; have
   them check `/plugin` rather than adding a symlink that goes stale at the
   next version.

3. **`uv`.** Both shipped adapters run on it, and the bundled `slack-client` is
   a `uv run --script` file with inline dependencies, so nothing works without
   it. Nothing here installs it; give them Astral's own installer —
   `curl -LsSf https://astral.sh/uv/install.sh | sh` on macOS and Linux,
   `powershell -c "irm https://astral.sh/uv/install.ps1|iex"` on Windows — and
   re-check with `uv --version`.

4. **The chat adapter's one-off setup**, if the register declares it, in this
   order — each step's failure looks like the previous step's success:

   - `uv run --with playwright playwright install chromium` — downloads the
     browser the login flow drives. Needs a desktop session; note that a
     headless container or a GUI-less WSL cannot complete step two.
   - `slack-client login` — opens a real browser and waits for the user to sign
     in, capturing the session to `~/.cache/slack-client/session.json`. Only
     they can do this, and they should run it **from a Claude Code session** —
     `! slack-client login` — since the launcher is on PATH only inside one. In
     a bare terminal the name resolves to nothing. Say plainly what it captures: a credential as sensitive
     as their Slack login, local-only, never to be committed or copied into a
     secret manager.
   - Confirm with a read-only call that touches no content, e.g.
     `slack-client memberships`.

5. **The email adapter's credential**, if the register declares it. It borrows a
   mail MCP server's existing token cache rather than minting anything, so the
   fix is to sign in through that server once and re-run the check. If the cache
   is present but calls are rejected, that is an **expired** credential rather
   than a missing one — the remedy is a fresh sign-in, not setup. Say which of
   the two you are looking at.

6. **Permissions.** None to add — say so and move on. A PreToolUse hook in this
   plugin approves the reads a sync runs, so nothing goes into
   `permissions.allow`. Two things still prompt, both deliberately:
   `slack-client login`, which is the browser flow from step 5 that only they
   can complete, and any call that chains a second command. If they are
   carrying a `Bash(slack-client *)` entry from an earlier version, it is
   harmless and needs no removing — nothing depends on it now.

7. **Re-run `provision.py`.** Silence is the confirmation. Then offer, without
   running it unbidden, a first sync against a deliberately recent watermark so
   the initial run is small rather than a backfill of all history. Say how one is
   started while you are offering it: a request like "sync the knowledge base".

Close with what is configured, what remains, and — for anything still unset —
the reminder that the next sync will skip that source and record the skip in the
watermarks, so the gap stays visible in the repo rather than only here.
