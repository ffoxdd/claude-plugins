#!/usr/bin/env python3
"""Locates and reads a knowledge base's own register of sources.

This configuration is **per-repository**, which is what makes it different from
the organization vocabulary the dan-work-routing plugin loads. That one is per-person
and the same wherever they work, so a plugin option naming a file is the right
shape for it. This one is not: a person can keep more than one knowledge base,
and which sources feed a given one is a property of that repository — committed
with it, reviewed in its diffs, and already correct for whoever clones it.

So the file is found by walking up from the working directory, the way `.git` is,
rather than being named by a plugin option. Its directory is the knowledge base's
root, which is what every path inside it resolves against.

A leading dot because a knowledge base's root is a place people read and browse —
notes, not source — and a config file they will edit twice a year does not earn a
line in that listing. It is still committed, and the visible `CLAUDE.md` points at
it, so nothing about hiding it costs a newcomer the ability to find it.

    KNOWLEDGE_BASE_CONFIG_FILE
        Read this file instead of searching. For the test suite, and for a
        script run from outside the repository it operates on.

A malformed or missing config raises rather than returning empty. The
dan-work-routing loader deliberately does the opposite, because there a missing file
must never stop a session from starting or widen what a guard permits. Here the
whole failure mode is the other one: a sync that reads no sources does nothing,
successfully, and reports having swept everything it knew about. Silence is the
bug, so the config refuses to be absent quietly.
"""

import json
import os
from pathlib import Path

CONFIG_FILENAME = ".knowledge-base.json"


class ConfigurationError(Exception):
    """Raised when the config is missing, unreadable, or not what it claims."""


def find(start=None):
    """The nearest config file at or above `start`, or None if there is none."""
    directory = Path(start or Path.cwd()).resolve()

    for candidate in (directory, *directory.parents):
        if (candidate / CONFIG_FILENAME).is_file():
            return candidate / CONFIG_FILENAME

    return None


def load(start=None):
    """The parsed config, plus the root every relative path in it resolves against."""
    override = os.environ.get("KNOWLEDGE_BASE_CONFIG_FILE")
    path = Path(override) if override else find(start)

    if path is None:
        raise ConfigurationError(
            f"No {CONFIG_FILENAME} at or above {Path(start or Path.cwd()).resolve()}. "
            "Run /dan-knowledge-base:init to scaffold one."
        )

    try:
        text = Path(path).read_text(encoding="utf-8")

    except OSError as error:
        raise ConfigurationError(f"Cannot read {path}: {error}") from error

    try:
        document = json.loads(text)

    except json.JSONDecodeError as error:
        raise ConfigurationError(f"{path} is not valid JSON: {error}") from error

    if not isinstance(document.get("sources"), dict):
        raise ConfigurationError(
            f'{path} declares no "sources" object. A config with no sources '
            "would let a sync report success having swept nothing."
        )

    return document, Path(path).parent


def sources(start=None):
    document, _ = load(start)

    return document["sources"]


def source(name, start=None):
    """One source's entry. Raises rather than defaulting — a sweep run against a
    source the register doesn't describe is a mistake, not a case to handle."""
    found = sources(start)

    if name not in found:
        known = ", ".join(sorted(found)) or "none"
        raise ConfigurationError(f"No source named {name!r} in the register (known: {known}).")

    return found[name]


def path_within(root, value):
    """Resolves a configured relative path, refusing to leave the knowledge base.

    Every path in the config names something inside the repository. A value that
    escapes it is a typo or a paste from another machine, and the failure it
    would otherwise cause — writing intake outside the gitignored tree — is the
    one this plugin exists to prevent.
    """
    resolved = (Path(root) / value).resolve()
    root = Path(root).resolve()

    if resolved != root and root not in resolved.parents:
        raise ConfigurationError(f"{value!r} resolves outside the knowledge base at {root}.")

    return resolved
