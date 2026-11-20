#!/usr/bin/env python3
"""Where an adapter writes raw text for the isolated agent, and the checks on it.

The chat, notion and fathom adapters each write text the session must not read
until an isolated agent has gated it. That text always lands in
`<intake>/<source name>/`: `<intake>` is the register's `layout.inbox` (`inbox`
when the layout omits it), resolved against the knowledge base's root, and the
source name is the adapter's `--source`. So `--source notion-covered` writes to
`inbox/notion-covered/`. The folder lives inside the repository, so the isolated
agent reaches it however its tools are scoped, and it is git-ignored, so nothing
in it can reach a commit.

Two checks run before an adapter's first request, and either refuses the run:

  * **The folder must be git-ignored when it is inside a git work tree.** One
    outside any work tree, or on a machine without git, is accepted; one git
    fails to judge for any other reason is refused.
  * **The folder must be absent or empty.** Files already there are a previous
    run's, not yet gated or not yet deleted, and a second run's files beside
    them would be gated, or deleted, as one batch.
"""

import os
import re
import subprocess
from pathlib import Path

import configuration

DEFAULT_INTAKE = "inbox"


def located(source_name, start=None):
    """The absolute folder `source_name`'s raw text goes to."""
    document, root = configuration.load(start)
    intake = (document.get("layout") or {}).get("inbox") or DEFAULT_INTAKE

    return configuration.path_within(root, Path(intake) / source_name)


def checked(source_name, start=None):
    """The folder for `source_name`'s raw text, once it is known to be safe to
    write to; raises configuration.ConfigurationError naming why it is not."""
    directory = located(source_name, start)
    refusal = ignore_refusal(directory) or occupied_refusal(directory)

    if refusal:
        raise configuration.ConfigurationError(refusal)

    return directory


def occupied_refusal(directory):
    if not directory.exists():
        return None

    if not directory.is_dir():
        return f"the raw-text folder {directory} is a file, not a folder"

    if any(directory.iterdir()):
        return (f"the raw-text folder {directory} is not empty: a previous run's working files "
                "are still there. Finish that run's gate, or delete the folder")

    return None


def existing_ancestor(path):
    while not path.exists() and path != path.parent:
        path = path.parent

    return path


# git's own answer when no repository encloses the path. Only this failure means
# "outside any work tree"; any other is a repository git could not judge.
OUTSIDE_ANY_REPOSITORY = re.compile(
    r"not a git repository \(or any (of the parent directories|parent up to mount point)")


def git(directory, *arguments):
    """A git command's result, or None on a machine without git. Messages in the C
    locale, so a failure can be classified by its words."""
    try:
        return subprocess.run(["git", "-C", str(directory), *arguments], capture_output=True,
                              text=True, env={**os.environ, "LC_ALL": "C"})

    except OSError:
        return None


def ignore_refusal(directory):
    """Why raw text may not be written to `directory`, or None when it may. The
    folder holds ungated text, so one in a work tree must be one git ignores."""
    ignored = git(existing_ancestor(directory), "check-ignore", "--quiet", f"{directory}{os.sep}")

    if ignored is None or ignored.returncode == 0:
        return None

    if ignored.returncode == 1:
        return (f"the raw-text folder {directory} is inside a git work tree and not "
                "git-ignored; it must be git-ignored because it holds ungated text")

    if OUTSIDE_ANY_REPOSITORY.search(ignored.stderr):
        return None

    return (f"the raw-text folder {directory}: git could not confirm that it is "
            "git-ignored, and it must be because it holds ungated text")
