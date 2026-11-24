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
the intake directory, git-ignored, and reached through no link. Those are what
make the directory raw intake rather than notes, and a deletion aimed by a typo
at the wrong one is not recoverable. Where git cannot judge the directory — no
git, or no work tree around it — it deletes nothing and says nothing, the way an
adapter accepts such a place but retention never deletes what it cannot confirm
is ignored. It never follows a link: a symbolic link, or on Windows a junction
or any other reparse point that stands for another location, under the
directory is neither deleted nor descended into. A folder it cannot list, or one
removed under it by another session, is skipped, and a file it cannot delete is
left for the next run; neither is named.

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


class Unjudged(Exception):
    """Git cannot say whether the processed directory is ignored, so nothing is
    deleted, and nothing is said: that is the ordinary state of a knowledge base
    outside a work tree."""


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
        raise Refused(f"the processed directory {processed} is reached through a link")

    if processed.is_dir():
        confirm_ignored(processed)

    return processed


def linked_component(root, processed):
    """The first folder from the processed directory up to the knowledge base's
    root, exclusive, that is a symbolic link, or None."""
    for path in [processed, *processed.parents]:
        if path == root:
            return None

        if is_link(path):
            return path

    return None


# Windows marks a junction, and every other kind of link, as a reparse point.
# Neither `is_symlink` nor a walk's `followlinks` knows a junction, so this is
# what keeps one from being descended into.
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

# Bit 29 of a reparse tag, the name-surrogate bit: set on every tag that stands
# for another named entity, symbolic links (0xA000000C) and junctions or mount
# points (0xA0000003) among them. A cloud-file placeholder (0x9000xx1A) and the
# other tags that keep their own content leave it clear, so a folder synced by a
# cloud client is not mistaken for a link.
NAME_SURROGATE = 0x20000000


def is_link(path):
    """Whether the path is a symbolic link, or a reparse point that stands for
    another location; a path that cannot be read counts as one, so it is never
    descended into or deleted."""
    try:
        status = os.lstat(path)

    except FileNotFoundError:
        return False

    except OSError:
        return True

    if stat.S_ISLNK(status.st_mode):
        return True

    if not getattr(status, "st_file_attributes", 0) & REPARSE_POINT:
        return False

    return redirects(getattr(status, "st_reparse_tag", 0))


def redirects(tag):
    """Whether a reparse tag stands for another location. A missing tag cannot be
    classified, and counts as one."""
    return not tag or bool(tag & NAME_SURROGATE)


def confirm_ignored(directory):
    """Raise unless git confirms the directory is ignored: Refused when git says it
    is not, or fails for a reason of its own; Unjudged when there is no git or no
    work tree around it."""
    ignored = raw_directory.git(directory, "check-ignore", "--quiet", f"{directory}{os.sep}")

    if ignored is None or raw_directory.OUTSIDE_ANY_REPOSITORY.search(ignored.stderr):
        raise Unjudged()

    if ignored.returncode != 0:
        raise Refused(f"the processed directory {directory} is not git-ignored")


def is_expired(path, cutoff):
    status = os.lstat(path)

    return stat.S_ISREG(status.st_mode) and status.st_mtime < cutoff


def delete_expired(folder, cutoff):
    """Delete every regular file under the folder older than the cutoff, and every
    folder that leaves empty. A link is never deleted or descended into. A file
    that cannot be deleted is left for the next run."""
    deleted = 0

    try:
        entries = list(os.scandir(folder))

    except OSError:
        return 0

    for entry in entries:
        if is_link(entry.path):
            continue

        try:
            if entry.is_dir(follow_symlinks=False):
                deleted += delete_expired(entry.path, cutoff)
                remove_if_empty(entry.path)

            elif is_expired(entry.path, cutoff):
                os.unlink(entry.path)
                deleted += 1

        except OSError:
            continue

    return deleted


def remove_if_empty(path):
    try:
        if not is_link(path) and not os.listdir(path):
            os.rmdir(path)

    except OSError:
        pass


def enforce(document, root, now=None):
    """The outcome of applying the register's retention, or None when it sets
    none or git cannot judge where it would delete."""
    layout = document.get("layout") or {}

    try:
        days = retention_days(layout)

        if days is None:
            return None

        processed = processed_directory(layout, Path(root).resolve())

    except Unjudged:
        return None

    except (Refused, configuration.ConfigurationError) as refusal:
        return Outcome(f"knowledge-base retention: nothing deleted; {refusal}", None)

    cutoff = (now or time.time()) - days * SECONDS_PER_DAY
    deleted = delete_expired(processed, cutoff) if processed.is_dir() else 0

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
