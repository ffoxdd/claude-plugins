#!/usr/bin/env python3
"""Deletes processed intake older than the register's `layout.retention_days`.

Distilled intake is kept in `layout.processed` so a note can be traced back to
what produced it, and nothing else ever removes it. Raw intake is where personal
data lands, so a knowledge base may cap how long it is kept:

    "layout": {"inbox": "inbox", "processed": "inbox/processed", "retention_days": 90}

With the key, each file under the processed directory whose modification time
is older than that many days is deleted, and a folder left empty is removed.
Without it, nothing happens. The session-start provisioner runs this in every
knowledge base; it can be run by hand too.

**It refuses to act**, deleting nothing, unless the processed directory is inside
the intake directory, git-ignored, and reached through no symbolic link. Those
are what make the directory raw intake rather than notes, and a deletion aimed
by a typo at the wrong one is not recoverable. It never follows a link: a
symbolic link under the directory is neither deleted nor descended into.

It prints one line, the count deleted or the refusal, and never a filename,
since a filename can carry a meeting's title.
"""

import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "knowledge-base"
                       / "scripts"))

import configuration
import raw_directory

SECONDS_PER_DAY = 24 * 60 * 60

DEFAULT_PROCESSED = "processed"


class Refused(Exception):
    """Why nothing is deleted."""


@dataclass(frozen=True)
class Outcome:
    """What one run did: the line it reports, and how many files it deleted
    (None when it refused)."""
    line: str
    deleted: "int | None"


def retention_days(layout):
    """The register's retention in days, None when it names none."""
    days = layout.get("retention_days")

    if days is None:
        return None

    if isinstance(days, bool) or not isinstance(days, (int, float)) or days <= 0:
        raise Refused('"layout.retention_days" must be a number of days greater than zero')

    return days


def processed_directory(layout, root):
    """The processed directory, once it is known to be safe to delete from."""
    intake = Path(os.path.normpath(root / raw_directory.intake_setting({"layout": layout})))
    processed = Path(os.path.normpath(
        root / (layout.get("processed") or Path(intake) / DEFAULT_PROCESSED)))

    if intake not in processed.parents or root not in intake.parents:
        raise Refused(f"the processed directory {processed} is not inside the intake "
                      f"directory {intake} within the knowledge base")

    if linked_component(root, processed) is not None:
        raise Refused(f"the processed directory {processed} is reached through a symbolic "
                      "link")

    if processed.is_dir() and not git_ignores(processed):
        raise Refused(f"the processed directory {processed} is not git-ignored")

    return processed


def linked_component(root, processed):
    """The first folder from the processed directory up to the knowledge base's
    root, exclusive, that is a symbolic link, or None."""
    for path in [processed, *processed.parents]:
        if path == root:
            return None

        if path.is_symlink():
            return path

    return None


def git_ignores(directory):
    ignored = raw_directory.git(directory, "check-ignore", "--quiet", f"{directory}{os.sep}")

    return ignored is not None and ignored.returncode == 0


def is_expired(path, cutoff):
    status = os.lstat(path)

    return stat.S_ISREG(status.st_mode) and status.st_mtime < cutoff


def delete_expired(processed, days, now):
    """Delete every regular file older than the cutoff, then every folder left
    empty, bottom up. The walk does not follow links, and a link is never
    deleted. A file that cannot be deleted is left for the next run."""
    cutoff = now - days * SECONDS_PER_DAY
    deleted = 0

    for folder, folders, files in os.walk(processed, topdown=False, followlinks=False):
        for name in files:
            path = os.path.join(folder, name)

            try:
                if is_expired(path, cutoff):
                    os.unlink(path)
                    deleted += 1

            except OSError:
                continue

        for name in folders:
            remove_if_empty(os.path.join(folder, name))

    return deleted


def remove_if_empty(path):
    try:
        if not os.path.islink(path) and not os.listdir(path):
            os.rmdir(path)

    except OSError:
        pass


def enforce(document, root, now=None):
    """The outcome of applying the register's retention, or None when it sets
    none."""
    layout = document.get("layout") or {}

    try:
        days = retention_days(layout)

        if days is None:
            return None

        processed = processed_directory(layout, Path(root).resolve())

    except (Refused, configuration.ConfigurationError) as refusal:
        return Outcome(f"knowledge-base retention: nothing deleted; {refusal}", None)

    deleted = delete_expired(processed, days, now or time.time()) if processed.is_dir() else 0

    return Outcome(f"knowledge-base retention: {deleted} processed intake file(s) older than "
                   f"{days:g} day(s) deleted", deleted)


def main():
    try:
        document, root = configuration.load()

    except configuration.ConfigurationError as error:
        print(f"knowledge-base retention: nothing deleted; {error}")

        return 1

    outcome = enforce(document, root)

    if outcome is not None:
        print(outcome.line)

    return 0 if outcome is None or outcome.deleted is not None else 1


if __name__ == "__main__":
    sys.exit(main())
