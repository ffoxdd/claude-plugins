#!/usr/bin/env python3
"""Finds the four ways an installed plugin set drifts from what its marketplaces offer.

Detects; never mutates. Everything here is a read of four JSON files, so it is
cheap enough to run at every session start, and the repair it proposes stays
behind a person's confirmation in `/plugin-sync:sync`.

The four drifts, and why they are the whole list:

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
- **unsatisfied** — installed and still listed, but the dependency its
  marketplace declares is absent or at a version outside the declared range.
  Moving a plugin's pin is enough to cause it, and the plugin that stops loading
  is the dependent rather than the one that moved.

A version behind is not on the list. Auto-update ships versions; this repairs
breakage, and a healthy install is left exactly alone.

Retirement is inferred from absence, so a marketplace whose manifest cannot be
read is skipped entirely rather than read as having retired everything in it —
the one way a network or disk failure could otherwise talk someone into
uninstalling their whole shelf.
"""

import json
import re
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
    unsatisfied = find_unsatisfied(installed, offerings)
    duplicates = find_duplicates(installed)

    return {
        "orphans": orphans,
        "missing": find_missing(enabled, installed, offerings),
        "duplicates": duplicates,
        "unsatisfied": unsatisfied,
        "unreadable": sorted(
            set(record["marketplace"] for record in installed.values()) - set(offerings)
        ),
        "healthy": count_healthy(installed, orphans, unsatisfied, duplicates),
    }


def count_healthy(installed, orphans, unsatisfied, duplicates):
    """Installs touched by no drift. Counted as a set difference rather than by
    subtraction so an install caught by two drifts at once — a duplicate that is
    also an orphan — is not counted out twice, and a plugin with two unmet
    dependencies is not counted out for each."""
    drifting = set()

    drifting.update(record["identifier"] for record in orphans)
    drifting.update(finding["identifier"] for finding in unsatisfied)
    drifting.update(
        install["identifier"] for duplicate in duplicates for install in duplicate["installs"]
    )

    return len(set(installed) - drifting)


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
        by_name.setdefault(record["name"], []).append(record)

    return [
        {
            "name": name,
            "installs": sorted(
                ({"identifier": record["identifier"], "scope": record["scope"]} for record in records),
                key=lambda install: install["identifier"],
            ),
        }
        for name, records in sorted(by_name.items())
        if len(records) > 1
    ]


def find_unsatisfied(installed, offerings):
    """Installed plugins whose declared dependency is absent or out of range.

    The plugin that stops loading is the dependent, not the one that moved, so
    the finding names both and the version each side is at. A range written in
    syntax `satisfies` does not model yields no finding — the same rule the
    unreadable marketplaces follow, since a guess here would name a working
    plugin as broken.
    """
    by_name = {record["name"]: record for record in installed.values()}

    findings = []

    for record in sorted(installed.values(), key=lambda record: record["identifier"]):
        entry = offerings.get(record["marketplace"], {}).get(record["name"], {})

        for requirement in entry.get("dependencies", []):
            finding = unmet(record, requirement, by_name)

            if finding:
                findings.append(finding)

    return findings


def unmet(record, requirement, by_name):
    name = requirement.get("name")

    if not name:
        return None

    wanted = requirement.get("version", "")
    present = by_name.get(name)

    if present is None:
        return {
            "identifier": record["identifier"],
            "requires": name,
            "wanted": wanted,
            "installed": None,
        }

    if satisfies(present["version"], wanted) is False:
        return {
            "identifier": record["identifier"],
            "requires": name,
            "wanted": wanted,
            "installed": present["version"],
        }

    return None


def satisfies(version, requirement):
    """Whether an installed version meets a dependency range.

    None means the range is written in syntax this does not model, which is
    reported as nothing rather than as a failure. `^0.x` is deliberately among
    them: the major-zero carve-out differs between resolvers, and the cost of
    being wrong is telling someone a working plugin is broken.
    """
    installed = parse_version(version)

    if installed is None:
        return None

    requirement = requirement.strip()

    if not requirement or requirement == "*":
        return True

    if requirement[0].isdigit():
        wanted = parse_version(requirement)

        return None if wanted is None else installed == wanted

    if requirement[0] not in "~^":
        return None

    wanted = parse_version(requirement[1:])

    if wanted is None or (requirement[0] == "^" and wanted[0] == 0):
        return None

    if installed < wanted:
        return False

    if requirement[0] == "~":
        return installed[:2] == wanted[:2]

    return installed[0] == wanted[0]


def parse_version(text):
    core = re.split(r"[-+]", text.strip(), maxsplit=1)[0]
    parts = core.split(".")

    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None

    return tuple(int(part) for part in parts)


def read_offerings(claude_directory):
    """Each readable marketplace's offered plugins, by name.

    The whole entry rather than the name alone, since the dependencies a plugin
    must satisfy are declared there.

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
        entries = {
            plugin["name"]: plugin
            for plugin in (manifest or {}).get("plugins", [])
            if isinstance(plugin, dict) and plugin.get("name")
        }

        if entries:
            offerings[marketplace] = entries

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

    for record in survey["unsatisfied"]:
        if record["installed"] is None:
            notes.append(
                f"{record['identifier']} requires {record['requires']} "
                f"{record['wanted']}, which is not installed. It will not load."
            )
        else:
            notes.append(
                f"{record['identifier']} requires {record['requires']} "
                f"{record['wanted']}, but {record['installed']} is installed. "
                f"It will not load until {record['requires']} is updated."
            )

    for record in survey["duplicates"]:
        identifiers = [install["identifier"] for install in record["installs"]]
        notes.append(
            f"{record['name']} is installed twice, as {' and '.join(identifiers)}. "
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
