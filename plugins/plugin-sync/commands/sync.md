---
description: Review and repair plugin drift — an install its marketplace dropped, one enabled but never installed, one installed twice
---

Repair the drift the survey finds, in one pass, with the user confirming the
plan before anything is uninstalled. Never uninstall or install ahead of that
confirmation: an uninstall discards a plugin's persistent data directory, and
the user is the only one who knows whether a name they no longer recognize was
something they wanted.

1. **Refresh, then survey.** Run `claude plugin marketplace update` and then
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plugin_sync.py" --json`. Refresh
   first or the evidence is a stale clone. A refresh that fails is not a reason
   to stop — a marketplace whose manifest still parses is still good evidence,
   and one whose manifest does not is reported under `unreadable` and excluded
   from every judgement below.

2. **Stop early when it is clean.** Empty `orphans`, `missing`, and
   `duplicates` means there is nothing to do. Say so in one line and stop —
   do not offer to update anything. Versions are auto-update's business, and a
   plugin merely behind is not drift.

3. **Name what was skipped.** For each marketplace under `unreadable`, say it
   could not be read and was left out. If one of them is a marketplace the user
   cares about, the fix is `claude plugin marketplace update <name>`, or
   re-adding it — never a removal of the plugins that came from it.

4. **Propose a replacement for each orphan, and mark it as a guess.** An
   orphan is a plugin whose marketplace stopped listing it, which upstream
   almost always means renamed or retired. Nothing in the manifest format
   records which, so read that marketplace's current entries — names and
   descriptions — and say which one looks like the successor and why. A rename
   usually keeps most of the name or the whole description. Present it as your
   reading, not as fact, and say plainly when nothing looks like a successor
   and the plugin appears simply retired.

5. **Show the whole plan, then ask once.** One list, each line an exact
   command, grouped as removals and installs. Ask for a single confirmation of
   the lot rather than one per line — and if the user wants only part of it,
   run that part.

   - orphan, replaced: `claude plugin uninstall <old-id> -s <scope> -y` then
     `claude plugin install <new-name>@<marketplace> -s <scope>`
   - orphan, retired: the uninstall alone
   - missing and installable: `claude plugin install <id> -s <scope>`
   - missing and not installable: a leftover `enabledPlugins` key with no
     install behind it. Offer to remove the key from `~/.claude/settings.json`;
     nothing needs uninstalling.
   - duplicate: keep the copy from the marketplace the user actually follows
     and uninstall the other. Say which you would keep and why, and let them
     pick — from the outside the two copies are the same plugin, and only they
     know which marketplace they mean to track.

6. **Run it, then say what needs a restart.** Plugin changes apply at the next
   session start, so end by saying which changes are pending until then. Re-run
   the survey afterwards and report anything that did not clear.
