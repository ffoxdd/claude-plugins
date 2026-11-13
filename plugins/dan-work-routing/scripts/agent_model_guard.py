#!/usr/bin/env python3
"""Decides whether an Agent spawn may proceed: it must say which model it runs on.

The routing primer's rule is advice while it lives only in context; this hook is
what makes it hold inside skills and forks the plugin does not own, since hooks
run in subagents too. A spawn that names no model takes whatever default the
platform falls back to, and a default nobody chose is where top-tier spend
leaks. So a spawn passes when any of these holds:

- the call sets `model`;
- it is a fork, which runs on the session's model and ignores the field;
- its agent type's definition declares `model:`, `inherit` included, since
  `inherit` is a stated decision;
- `CLAUDE_CODE_SUBAGENT_MODEL` is set in this process's environment to a model,
  in which case the platform gives an unnamed spawn that model rather than the
  session's (`inherit` there means the session's model, so it counts as unset).

Anything else is denied, with a reason that states the routing order and the
tiers, which turns the call into a retry that states its choice. Never
`updatedInput` with a default: a silently substituted model narrows the rigor of
whatever was being delegated without anyone deciding to.

The hook reads nothing but the PreToolUse payload, its own environment and agent
definition files. A call it cannot read passes rather than blocking on the
hook's own failure. Exit status is always 0; the decision travels in the JSON on
stdout.
"""

import json
import os
import sys
from pathlib import Path

DEFAULT_MODEL_VARIABLE = "CLAUDE_CODE_SUBAGENT_MODEL"

MODEL_REASON = (
    "Set `model` on this Agent call, or configure a default sub-agent model with "
    "the `CLAUDE_CODE_SUBAGENT_MODEL` environment variable. The routing order is "
    "fixed: spend on the top-tier model is minimized first, total tokens second, "
    "wall-clock time last, and a lower priority is never bought with a higher one. "
    "Never choose a model below what the task needs: checking another agent's work "
    "needs a model at least as capable as the one that produced it, so "
    "defect-finding and verification over top-tier work stay on the session's model "
    "(`inherit`, or name it), as do design, specification and adjudication. `opus` "
    "takes a build from a specification. `sonnet` takes reading, searching, "
    "summarizing, and convention, reuse or mechanical-shape checks; `haiku` takes "
    "mechanical edits and bounded lookups. A `fork` needs no model; an agent type "
    "whose definition declares `model:` passes as well."
)


def main():
    payload = read_payload()

    if payload is None:
        return

    if default_model_configured():
        return

    if not names_a_model(payload["tool_input"]):
        deny(MODEL_REASON)


def read_payload():
    try:
        # Claude Code writes the payload as UTF-8; left to the locale, a Windows
        # Python would read it as the code page and garble every non-ASCII character.
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        payload = json.load(sys.stdin)

    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return None

    return payload


def default_model_configured():
    value = os.environ.get(DEFAULT_MODEL_VARIABLE, "").strip()

    return bool(value) and value.lower() != "inherit"


def names_a_model(tool_input):
    if tool_input.get("model"):
        return True

    subagent_type = tool_input.get("subagent_type") or ""

    if subagent_type == "fork":
        return True

    return declared_model(subagent_type) is not None


def declared_model(subagent_type):
    if not subagent_type:
        return None

    plugin, _, agent = subagent_type.rpartition(":")

    for path in definition_files(plugin, agent):
        fields = frontmatter(path)

        if "model" in fields:
            return fields["model"] or "inherit"

    return None


def definition_files(plugin, agent):
    """Every agent definition an installed Claude Code could resolve the type to.

    Claude Code resolves a type against the project's `.claude/agents/`, the
    user's `~/.claude/agents/`, and each installed plugin's `agents/`. A plugin
    is installed under `~/.claude/plugins/cache/<marketplace>/<plugin>/` and
    the marketplace clone it came from sits under
    `~/.claude/plugins/marketplaces/<marketplace>/plugins/<plugin>/`; a
    plugin-qualified type is looked up only there, an unqualified one only
    outside the plugins.
    """
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    filename = f"{agent}.md"

    if plugin:
        yield from (home / "plugins" / "cache").glob(f"*/{plugin}/agents/{filename}")
        yield from (home / "plugins" / "marketplaces").glob(
            f"*/plugins/{plugin}/agents/{filename}"
        )
        return

    project = os.environ.get("CLAUDE_PROJECT_DIR")

    if project:
        yield Path(project) / ".claude" / "agents" / filename

    yield home / "agents" / filename


def frontmatter(path):
    """The top-level scalar keys of a markdown file's YAML frontmatter.

    Hand-parsed: the hook runs on a bare python3 with nothing installed. Only
    top-level `key: value` lines are read, which is all an agent declares.
    """
    try:
        text = path.read_text(encoding="utf-8")

    except OSError:
        return {}

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


def deny(reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception:
        pass

    sys.exit(0)
