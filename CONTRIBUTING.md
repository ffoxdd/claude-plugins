# Contributing

This marketplace is the organization's shelf. What sits on it is individually
authored: every plugin names its author, and none of them was ratified by
anyone. So adding yours needs nobody's approval — the naming rule below is what
makes that true without anyone's preferences becoming the house's.

## The naming rule

The name says whose a plugin is, and every plugin here is somebody's:

**Preference** — your way of working, where someone could defensibly choose
otherwise. It takes **your name as a prefix** (`dan-code-style`). Add one
whenever you like, with nobody's approval. Two people can each keep a code style
here and neither becomes the default, which is the whole reason the prefix
exists. **Every plugin currently on this shelf is one of these**, including the
one carrying a member-data rule that follows from an obligation rather than from
taste — because the workflow around that rule is still one person's, and the
prefix describes the plugin rather than its strongest sentence.

**Mechanism** — encodes something the organization has agreed is not declinable.
It takes a **bare name**, and the bare name is the claim: not that the author
feels strongly, but that the content is not a matter of taste and the people it
binds have accepted it. Nothing here claims one today. If you want to, get the
agreement first and expect to be asked for it — and if a reader can defensibly
choose otherwise, it was a preference, and renaming it is the fix.

Declare which kind in `plugin.json`, alongside your name:

```json
"author": { "name": "Dan Fox" },
"keywords": ["preference"]
```

The suite derives your prefix from the first word of `author.name`, lowercased —
so `"Dan Fox"` plus `preference` requires a plugin name starting `dan-`, and a
`mechanism` must *not* start with its author's prefix. If two contributors share
a first name, pick something unambiguous and put it in both fields.

The prefix is more than a label on the install screen. A plugin's name is the
namespace for everything inside it, so it is what a person types
(`/dan-code-style:principled`) and what they read in their settings
(`dan-code-style@aligned`). Seeing whose rules you are running, at the moment
you run them, is the point.

One thing the prefix cannot cover: **installing at `--scope project` writes to a
repository's `.claude/settings.json`, so everyone who clones it picks those
plugins up without choosing.** That is the one place something here arrives
without a person's decision, which makes it the wrong home for a preference —
your taste becomes the default for everyone who works in that repository.
Mechanisms there are fine; that is what they are for.

## Adding a plugin

1. Create `plugins/<name>/` with whichever parts you need:

   ```
   .claude-plugin/plugin.json   name, description, version,
                                author, keywords
   README.md                    must start with `# <name>`
   commands/<command>.md        /<name>:<command>
   agents/<agent>.md            name: must match the filename
   skills/<skill>/SKILL.md      name: must match the directory
   hooks/hooks.json             paths via ${CLAUDE_PLUGIN_ROOT}
   context/*.md                 text a SessionStart hook injects
   scripts/                     Python the hooks and commands run
   bin/                         commands to put on PATH
   ```

2. Register it in `.claude-plugin/marketplace.json`: the name, a
   `./plugins/<name>` source, and a description **identical** to the manifest's.
   The picker shows the marketplace copy before install and the manifest copy
   after, so the suite pins them equal rather than letting them drift.

3. Index it in the root `README.md` — link `plugins/<name>/README.md` and show
   `/plugin install <name>`. A plugin no instruction names is installed by
   nobody, so this is a test rather than a courtesy.

4. Run the suite: `python3 -m unittest discover -s tests`.

## Bump the version in the commit that changes the plugin

Installed copies are compared by the `version` string, not by commit. A commit
that edits a plugin without bumping it reaches the marketplace clone and stops
there: `plugin update` answers "already at the latest version", auto-update does
the same nothing, and the repository disagrees with every install with no error
raised anywhere.

This applies to a documentation-only change as much as a behavioral one — the
skill bodies and the READMEs *are* the product. The suite checks it against
history, so it stays quiet while your change is in progress and fails the moment
one is committed without its bump.

## Self-containment, which the suite also checks

A plugin is installed into a version-stamped directory that moves under it, so
nothing may assume its own location or reach outside itself:

- hook commands name files through `${CLAUDE_PLUGIN_ROOT}`, never `~/`
- `bin/` launchers are executable, name their interpreter rather than trusting a
  shebang, and resolve only paths inside the plugin
- every copy of `inject_context.py` is byte-identical — `dan-work-routing`'s is
  canonical, so copy that one rather than editing yours
- a skill's `references/*.md` and the pointers in its `SKILL.md` match in both
  directions; either half alone is dead weight or a dangling link

## Python 3, standard library only

Every script is invoked as `python3` — the one interpreter present on every
platform Claude Code runs on, including Windows, where its Bash tool is Git
Bash. No hook may depend on sh, zsh, or jq, and nothing may require a package
install. CI runs the suite on macOS, Linux, and Windows for that reason; with
auto-update on, `main` is the release channel, so a green suite is what stands
between a push and everyone's next session.

## Renaming or removing a plugin

The name is the install key, so a rename is an uninstall plus a fresh install
for everyone who had it — and any repository carrying the old name in
`.claude/settings.json` silently stops enabling it. A version bump does not
carry a rename. Do it early, or not at all, and say so in the commit message.
