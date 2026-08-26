---
description: Scaffold a knowledge-base repo — layout, gitignore, register, watermarks
---

Set up a knowledge base in the current repository, one step at a time. Do every
step you can yourself; stop and ask only where the answer is the user's to give.

Read `${CLAUDE_PLUGIN_ROOT}/skills/knowledge-base/SKILL.md` first if it is not
already in context — the layout and the reasoning are there; this command only
sequences the work.

1. **Check what already exists.** Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" --dry-run` and read what
   it reports; it creates nothing on this pass. If a `.knowledge-base.json`
   already exists, this repo is already a knowledge base — say so, show what it
   declares, and offer `/dan-knowledge-base:add-source` instead.

2. **Confirm the layout.** The defaults are `inbox/`, `inbox/processed/`, and
   `notes/`, with watermarks at `notes/.sync-state`. Ask only if the repo
   already has a conflicting structure worth preserving — otherwise take the
   defaults and say what you took.

3. **Create it.** Re-run `scaffold.py` without `--dry-run`. It writes the
   directories, the `.gitignore` entries, an empty watermark file, and a
   `.knowledge-base.json` declaring no sources. It never overwrites: anything
   already present is reported and left alone.

4. **Verify intake is actually ignored.** The failure here is committing the
   material the whole pattern exists to keep out, so prove it: run
   `git -C <repo> check-ignore -v inbox/probe.txt` and confirm it reports the
   rule. If the repo has no git history yet, say the check must be re-run after
   the first commit.

5. **Write the register's prose half.** Add a `## Sources` section to the repo's
   `CLAUDE.md` (creating it if absent) stating that `.knowledge-base.json` holds
   every value a script reads, this section holds the reasoning, and neither
   restates the other. Leave it otherwise empty; `add-source` fills it in.

6. **Name the menu, once**, so the option is known without being raised again:

   - **`email`** — sweeps a sender whitelist for meeting recaps and similar.
     Needs `uv` and a mail MCP server already signed in, whose token cache it
     borrows read-only.
   - **`chat`** — sweeps every conversation you are a member of, tiered by the
     platform's privacy flags. Needs `uv`, the bundled `slack-client`, a one-off
     `playwright install chromium`, and a captured session. It authenticates as
     you, not as an app — read `references/chat-sources.md` before adopting it.
   - **No adapter** — a source the model queries directly through its MCP
     server or CLI. The right default for anything with a server-side watermark
     filter; nothing to install.

   Then stop. Do not add a source unasked.

7. **Close** with what exists, what is gitignored, and how a sync is started —
   asking a session working in this repo to "sync the knowledge base", which
   commits the result and leaves the push to them. Then the two next steps:
   `/dan-knowledge-base:add-source` to declare a live source, or drop a file
   into `inbox/` named `YYYYMMDD_description.ext` and ask for that first sync.
