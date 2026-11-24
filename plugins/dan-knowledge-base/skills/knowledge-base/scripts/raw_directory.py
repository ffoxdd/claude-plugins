#!/usr/bin/env python3
"""Where an adapter writes what it fetches, and the checks on it.

Everything an adapter fetches lands under the intake directory: `<intake>` is
the register's `layout.inbox` (`inbox` when the layout omits it), resolved
against the knowledge base's root. A session with a covered gate cannot read a
file there until the gate releases it, so a path outside it would be a way
around the gate. Two kinds of file go there:

  * **The export**, the one file an adapter's `output` argument names.
    `output_checked` refuses a path that does not resolve under the intake
    directory, and one inside a git work tree that git does not ignore.
  * **Raw text for the isolated agent**, which the chat, notion and fathom
    adapters write to `<intake>/<source name>/`, the source name being the
    adapter's `--source`. So `--source notion-covered` writes to
    `inbox/notion-covered/`. The folder lives inside the repository, so the
    isolated agent reaches it however its tools are scoped, and it is
    git-ignored, so nothing in it can reach a commit.

Two checks run on the raw-text folder before an adapter's first request, and
either refuses the run:

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


def intake_setting(document):
    return (document.get("layout") or {}).get("inbox") or DEFAULT_INTAKE


def intake_directory(document, root):
    """The register's intake directory, resolved against the knowledge base's root."""
    return configuration.path_within(root, intake_setting(document))


def located(source_name, start=None):
    """The absolute folder `source_name`'s raw text goes to."""
    document, root = configuration.load(start)

    return configuration.path_within(root, Path(intake_setting(document)) / source_name)


def output_checked(output, start=None):
    """The absolute path an adapter's export goes to, once it is known to lie under
    the intake directory and, inside a work tree, to be git-ignored; raises
    configuration.ConfigurationError naming the intake directory when it is not.
    The path is resolved first, so a symbolic link out of the intake directory is
    judged by where it leads."""
    document, root = configuration.load(start)
    intake = intake_directory(document, root)
    path = Path(output).resolve()

    if intake not in path.parents:
        raise configuration.ConfigurationError(
            f"the output {path} is outside the intake directory {intake}; an adapter writes "
            "only under it, so give a path inside it")

    refusal = ignore_refusal(path, "the output", directory=False)

    if refusal:
        raise configuration.ConfigurationError(refusal)

    return path


def checked(source_name, start=None):
    """The folder for `source_name`'s raw text, once it is known to be safe to
    write to; raises configuration.ConfigurationError naming why it is not."""
    directory = located(source_name, start)
    refusal = ignore_refusal(directory, "the raw-text folder") or occupied_refusal(directory)

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


def ignore_refusal(path, label, directory=True):
    """Why ungated text may not be written to `path`, or None when it may. `label`
    names what the path is, for the refusal. The path holds ungated text, so one
    in a work tree must be one git ignores. A folder is asked about with a
    trailing separator, so a rule that ignores only folders applies to it."""
    if directory:
        ignored = git(existing_ancestor(path), "check-ignore", "--quiet", f"{path}{os.sep}")

    else:
        ignored = git(existing_ancestor(path.parent), "check-ignore", "--quiet", str(path))

    if ignored is None or ignored.returncode == 0:
        return None

    if ignored.returncode == 1:
        return (f"{label} {path} is inside a git work tree and not "
                "git-ignored; it must be git-ignored because it holds ungated text")

    if OUTSIDE_ANY_REPOSITORY.search(ignored.stderr):
        return None

    return (f"{label} {path}: git could not confirm that it is "
            "git-ignored, and it must be because it holds ungated text")
