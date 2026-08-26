# plugin-sync

A plugin's identity is `name@marketplace`, and the manifest format carries no
alias: nothing anywhere can say that one name replaced another. So a rename
upstream is a delete plus a create, and the copy already installed keeps its
place on the shelf, stops loading, and reports that nowhere but `/plugin`.

This finds that, and the two failures shaped like it, and repairs them on
request.

## What counts as drift

Four states, and the list is closed:

| | what it is | what it looks like |
|---|---|---|
| **orphan** | installed, but its marketplace no longer lists it | fails to load, silently |
| **missing** | enabled in settings, never installed | the plugin is simply not there |
| **duplicate** | one name installed from two marketplaces | context injected twice, hooks registered twice |
| **unsatisfied** | installed and listed, but its declared dependency is absent or out of range | fails to load, blaming a plugin that is fine |

**A version behind is not drift.** Auto-update ships versions; this repairs
breakage. An install its marketplace still lists is healthy whatever version
either side holds, and nothing here touches it — which is what makes the check
safe to run at every session start, and a no-op on a shelf that is fine.

Duplicates are worth the entry because nothing else reports them. Both copies
load, so a rule arrives twice and a hook runs twice, and the only sign is one
name appearing under two marketplaces in a listing nobody reads closely.

An unsatisfied dependency is the one drift a person causes by doing the right
thing: move a plugin's pin forward, and any plugin declaring a range that
excludes the new version stops loading. Nothing about the dependent changed,
which is why it reads as healthy everywhere — and why the report names the
dependency to update rather than the plugin that broke.

A range written in syntax the survey does not model produces no finding, on the
same rule the unreadable marketplaces follow: naming a working plugin broken
costs more than staying quiet.

## How it behaves

The check runs at session start and speaks only when something has drifted,
naming `/plugin-sync:sync` as the repair. The command refreshes the
marketplaces, surveys again, and puts one plan in front of you — removals and
installs as exact commands — before anything is touched.

Which name replaced which is the one part no manifest records, so the command
reads the marketplace's current entries and proposes the successor as a
reading rather than a fact. You confirm the plan; nothing is uninstalled ahead
of that.

Detection never mutates. It is four JSON reads:

```
~/.claude/settings.json                    enabledPlugins
~/.claude/plugins/installed_plugins.json   what is installed
~/.claude/plugins/known_marketplaces.json  where each clone is
<clone>/.claude-plugin/marketplace.json    what it offers
```

## The failure this is built around

Retirement is inferred from absence, which means a marketplace that cannot be
read looks exactly like one that retired everything in it. A survey that
believed a failed read would propose uninstalling an entire shelf.

So absence counts only where the manifest was positively read: a marketplace is
excluded from every judgement unless its manifest parses **and** lists at least
one plugin. A clone that is missing, corrupt, truncated, or half-written is
reported as unreadable and its plugins are left alone. Marketplaces you never
registered are left alone for the same reason — there is nothing to judge them
against.

## The one name that does not change

Every scheme for surviving renames needs a fixed point, and this is it. The
tool that repairs a rename cannot itself be renamed — the copy you had would
orphan, and the thing that fixes orphans would be the orphan.

So `plugin-sync` is the name, permanently, and that promise is the plugin's
main design constraint. It is why the name is bare rather than carrying its
author's prefix: an anchor everyone is expected to install cannot be one
person's, and a `dan-` prefixed one would say it was.

## Install

```
/plugin install plugin-sync
```

Nothing to configure. It reads your own Claude state and shells out to
`claude plugin` only from the command, only after you have agreed to the plan.
