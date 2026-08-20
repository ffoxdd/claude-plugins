---
description: Scaffold a knowledge-base repo — layout, gitignore, register, watermarks
---

Set up a knowledge base in the current repository, one step at a time. Do every
step you can yourself; stop and ask only where the answer is the user's to give.

Read `${CLAUDE_PLUGIN_ROOT}/skills/knowledge-base/SKILL.md` first if it is not
already in context — the layout and the reasoning behind it are there, and this
command only sequences the work.

1. **Check what already exists.** Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" --dry-run` and read what
   it reports. It creates nothing on this pass; it names what it would create and
   what it would leave alone. If a `.knowledge-base.json` already exists, this
   repo is already a knowledge base — say so, show what it declares, and offer
   `/dan-knowledge-base:add-source` instead.

2. **Confirm the layout.** The defaults are `inbox/`, `inbox/processed/`, and
   `notes/`, with watermarks at `notes/.sync-state`. Ask only if the repo already
   has a conflicting structure worth preserving — otherwise take the defaults and
   say what you took.

3. **Create it.** Re-run `scaffold.py` without `--dry-run`. It writes the
   directories, the `.gitignore` entries that keep intake out of version
   control, an empty watermark file, and a `.knowledge-base.json` declaring no
   sources yet. It never overwrites: anything already present is reported and
   left alone.

4. **Verify intake is actually ignored.** This is the one step worth proving
   rather than assuming, because the failure is committing the material the whole
   pattern exists to keep out. Run
   `git -C <repo> check-ignore -v inbox/probe.txt` and confirm it reports the
   rule. If the repo has no git history yet, say that the check cannot run and
   that it must be re-run after the first commit.

5. **Write the register's prose half.** Add a `## Sources` section to the repo's
   `CLAUDE.md` (creating it if absent) explaining that
   `.knowledge-base.json` holds every value a script reads and this section holds
   the reasoning — and stating the rule that neither restates the other. Leave it
   otherwise empty; `add-source` fills it in per source.

6. **Name the menu, once.** Tell the user which adapters ship with this plugin
   and what each costs to set up, so the option is known without being raised
   again later:

   - **`email`** — sweeps a sender whitelist for meeting recaps and similar.
     Needs `uv`, and a mail MCP server already signed in whose token cache it
     borrows read-only.
   - **`chat`** — sweeps every conversation you are a member of, tiered by the
     platform's own privacy flags. Needs `uv`, the bundled `slack-client`, a
     one-off `playwright install chromium`, and a captured session. Read
     `references/chat-sources.md` before adopting it: it authenticates as you
     rather than as an app, and rides an undocumented API.
   - **No adapter** — a source the model queries directly through its MCP server
     or CLI. This is the right default for anything with a server-side watermark
     filter, and it needs nothing installed.

   Then stop. Do not add a source unasked.

7. **Close** with what exists, what is gitignored, and — stated plainly, because
   it is the one thing nothing else will tell them — **how a sync is started**:
   asking a session working in this repo to "sync the knowledge base" (or "pull
   in what's new", or "integrate the inbox") runs the procedure, commits the
   result, and leaves the push to them. Then the two next steps:
   `/dan-knowledge-base:add-source` to declare a live source, or drop a file into
   `inbox/` named `YYYYMMDD_description.ext` and ask for that first sync.
