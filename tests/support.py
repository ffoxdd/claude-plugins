"""Shared helpers: locating the plugins, running their scripts, controlling the
environment those scripts read.

Every script here is invoked as a subprocess rather than imported. The contract
under test is the one Claude Code actually uses — argv, stdin, environment, exit
status, and the JSON on stdout — and importing would test a Python API that no
caller has.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

PLUGINS_DIRECTORY = REPOSITORY_ROOT / "plugins"

MARKETPLACE_FILE = REPOSITORY_ROOT / ".claude-plugin" / "marketplace.json"

# Variables the scripts read. Tests clear all of them and set back only what the
# case is about, so a value inherited from the developer's own session can never
# decide a result — a covered session running the suite would otherwise see the
# query guard stand down and every denial test pass vacuously.
CONTROLLED_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_PII_COVERED",
    "COVERED_ANTHROPIC_API_KEY",
    "CLAUDE_PLUGIN_OPTION_CONFIG_FILE",
    "KNOWLEDGE_BASE_CONFIG_FILE",
)


def plugin_names():
    return sorted(path.name for path in PLUGINS_DIRECTORY.iterdir() if path.is_dir())


def plugin_root(plugin):
    return PLUGINS_DIRECTORY / plugin


def script(plugin, name):
    return plugin_root(plugin) / "scripts" / name


def read_json(path):
    return json.loads(Path(path).read_text())


def environment(**overrides):
    values = {
        key: value
        for key, value in os.environ.items()
        if key not in CONTROLLED_VARIABLES
    }

    values.update({key: value for key, value in overrides.items() if value is not None})

    # A test redirecting HOME means "look at this throwaway home, not mine", and on
    # Windows `Path.home()` never consults HOME — ntpath.expanduser reads USERPROFILE,
    # then HOMEDRIVE/HOMEPATH. Left unmirrored, a script under test would read the
    # developer's real settings while the test believed it had isolated it, which is
    # the one failure mode a throwaway home exists to prevent.
    if os.name == "nt" and values.get("HOME"):
        values["USERPROFILE"] = values["HOME"]

    return values


def stub_command(path, source):
    """Writes `source` as a runnable command at `path`, and returns how to invoke it.

    A shebang is POSIX-only. Windows resolves a command name through PATHEXT and runs
    it through CreateProcess, which cannot execute an extensionless text file whatever
    its permission bits say — so a stub written the POSIX way is simply not found
    there. On Windows the Python goes into `<name>-stub.py` and a `<name>.cmd` beside
    it is what PATH resolves to; everywhere else the file itself carries the shebang.

    Returns the path a caller should invoke, which differs from `path` on Windows —
    tests that hand the stub's location to something else must use the return value.
    """
    if os.name == "nt":
        script = path.with_name(f"{path.name}-stub.py")
        script.write_text(source)

        launcher = path.with_name(f"{path.name}.cmd")
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n')

        return launcher

    path.write_text(f"#!{sys.executable}\n{source}")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)

    return path


def run_script(path, arguments=(), stdin="", cwd=None, **environment_overrides):
    """Runs a plugin script under this interpreter, whatever its shebang or name.

    sys.executable rather than the shebang, so the extensionless scripts run the
    same way on a machine whose `python3` differs from the one running the suite.
    """
    return subprocess.run(
        [sys.executable, str(path), *[str(argument) for argument in arguments]],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=environment(**environment_overrides),
    )


def hook_decision(path, command, **environment_overrides):
    """The PreToolUse decision for a Bash command: 'deny', or None when it passes."""
    payload = json.dumps({"tool_input": {"command": command}})
    result = run_script(path, stdin=payload, **environment_overrides)

    if not result.stdout.strip():
        return None

    return json.loads(result.stdout).get("hookSpecificOutput", {}).get("permissionDecision")


def frontmatter(path):
    """The top-level scalar fields of a markdown file's YAML frontmatter.

    Hand-parsed rather than pulled from PyYAML: the suite must run wherever the
    plugins do, which is a bare python3 with nothing installed. Only top-level
    `key: value` lines are read, which is all an agent or command declares.
    """
    text = Path(path).read_text()

    if not text.startswith("---\n"):
        return {}

    end = text.find("\n---", 4)

    if end == -1:
        return {}

    fields = {}

    for line in text[4:end].splitlines():
        if not line or line.startswith((" ", "\t", "-")) or ":" not in line:
            continue

        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    return fields
