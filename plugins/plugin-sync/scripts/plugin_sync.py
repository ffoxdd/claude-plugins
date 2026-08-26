#!/usr/bin/env python3
"""Finds the three ways an installed plugin set drifts from what its marketplaces offer.

Detects; never mutates. Everything here is a read of four JSON files, so it is
cheap enough to run at every session start, and the repair it proposes stays
behind a person's confirmation in `/plugin-sync:sync`.

The three drifts, and why they are the whole list:

- **orphan** — installed, but the marketplace it came from no longer lists it.
  A plugin's identity is `name@marketplace` and nothing in the manifest format
  carries an alias, so a rename upstream is a delete plus a create: the old name
  keeps its install, fails to load, and says so nowhere but `/plugin`.
- **missing** — enabled in settings, absent from the install record. What a
  teammate has after cloning a repository whose `.claude/settings.json` names
  plugins, and what a failed install leaves behind.
- **duplicate** — one name installed from two marketplaces at once. Both copies
  load, so their context is injected twice and their hooks registered twice,
  with the doubled listing as the only sign.

A version behind is not on the list. Auto-update ships versions; this repairs
breakage, and a healthy install is left exactly alone.

Retirement is inferred from absence, so a marketplace whose manifest cannot be
read is skipped entirely rather than read as having retired everything in it —
the one way a network or disk failure could otherwise talk someone into
uninstalling their whole shelf.
"""

import json
import sys
from pathlib import Path

CLAUDE_DIRECTORY = Path.home() / ".claude"


def main(argv):
    survey = survey_drift(CLAUDE_DIRECTORY)

    if "--json" in argv:
        json.dump(survey, sys.stdout, indent=2)
        return 0

    notes = notes_for(survey)

    if notes:
        report(notes)

    return 0


def survey_drift(claude_directory):
    offerings = read_offerings(claude_directory)
    installed = read_installed(claude_directory)
    enabled = read_enabled(claude_directory)

    judgable = {
        identifier: record
        for identifier, record in installed.items()
        if record["marketplace"] in offerings
    }

    orphans = find_orphans(judgable, offerings)

    return {
        "orphans": orphans,
        "missing": find_missing(enabled, installed, offerings),
        "duplicates": find_duplicates(installed),
        "unreadable": sorted(
            set(record["marketplace"] for record in installed.values()) - set(offerings)
        ),
        "healthy": len(installed) - len(orphans),
    }


def find_orphans(installed, offerings):
    """Installed plugins their own marketplace no longer lists.

    Only ever called with installs whose marketplace parsed, so absence here means
    the marketplace dropped the name rather than that nothing could be read.
    """
    return [
        record
        for identifier, record in sorted(installed.items())
        if record["name"] not in offerings[record["marketplace"]]
    ]


def find_missing(enabled, installed, offerings):
    """Enabled in settings, absent from the install record.

    An enabled name its marketplace does not offer either is a stale settings key
    rather than a missing install — there is nothing to install, so it is reported
    as an orphan of the same rename and cleaned the same way.
    """
    absent = sorted(identifier for identifier in enabled if identifier not in installed)

    return [
        {
            "identifier": identifier,
            "name": name,
            "marketplace": marketplace,
            "installable": name in offerings.get(marketplace, ()),
        }
        for identifier, name, marketplace in map(split_identifier, absent)
    ]


def find_duplicates(installed):
    """One plugin name installed from more than one marketplace.

    Both copies load. Nothing errors, and the doubled entry in `/plugin` is the
    only place it shows.
    """
    by_name = {}

    for record in installed.values():
        by_name.setdefault(record["name"], []).append(record["identifier"])

    return [
        {"name": name, "identifiers": sorted(identifiers)}
        for name, identifiers in sorted(by_name.items())
        if len(identifiers) > 1
    ]


def read_offerings(claude_directory):
    """Each readable marketplace's set of offered plugin names.

    A marketplace is omitted rather than recorded empty when its clone is absent,
    its manifest will not parse, or it lists nothing — the three ways a read can
    fail that would otherwise look exactly like a marketplace that retired
    everything.
    """
    known = read_json(claude_directory / "plugins" / "known_marketplaces.json") or {}

    offerings = {}

    for marketplace, entry in known.items():
        location = entry.get("installLocation")

        if not location:
            continue

        manifest = read_json(Path(location) / ".claude-plugin" / "marketplace.json")
        names = {
            plugin["name"]
            for plugin in (manifest or {}).get("plugins", [])
            if isinstance(plugin, dict) and plugin.get("name")
        }

        if names:
            offerings[marketplace] = names

    return offerings


def read_installed(claude_directory):
    record_file = read_json(claude_directory / "plugins" / "installed_plugins.json") or {}

    installed = {}

    for identifier, records in record_file.get("plugins", {}).items():
        if not records:
            continue

        identifier, name, marketplace = split_identifier(identifier)

        installed[identifier] = {
            "identifier": identifier,
            "name": name,
            "marketplace": marketplace,
            "scope": records[0].get("scope", "user"),
            "version": records[0].get("version", ""),
        }

    return installed


def read_enabled(claude_directory):
    settings = read_json(claude_directory / "settings.json") or {}

    return sorted(
        identifier
        for identifier, on in settings.get("enabledPlugins", {}).items()
        if on and "@" in identifier
    )


def split_identifier(identifier):
    name, _, marketplace = identifier.rpartition("@")

    return identifier, name, marketplace


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    except (OSError, ValueError):
        return None


def notes_for(survey):
    notes = []

    for record in survey["orphans"]:
        notes.append(
            f"{record['identifier']} is installed, but the '{record['marketplace']}' "
            "marketplace no longer lists it — most likely renamed or retired upstream. "
            "It will not load."
        )

    for record in survey["missing"]:
        if record["installable"]:
            notes.append(
                f"{record['identifier']} is enabled in settings but is not installed."
            )
        else:
            notes.append(
                f"{record['identifier']} is enabled in settings, but the "
                f"'{record['marketplace']}' marketplace does not offer it and nothing "
                "is installed under that name — a leftover key."
            )

    for record in survey["duplicates"]:
        notes.append(
            f"{record['name']} is installed twice, as {' and '.join(record['identifiers'])}. "
            "Both copies load, so its context is injected twice and its hooks run twice."
        )

    if notes:
        notes.append("run /plugin-sync:sync to review and repair.")

    return notes


def report(notes):
    body = "\n".join(f"- {note}" for note in notes)
    json.dump({"systemMessage": f"plugin-sync:\n{body}"}, sys.stdout)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))

    except Exception as error:
        json.dump({"systemMessage": f"plugin-sync: the drift check failed — {error}"}, sys.stdout)
        sys.exit(0)
