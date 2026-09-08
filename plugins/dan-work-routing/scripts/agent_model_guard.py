#!/usr/bin/env python3
"""Denies an Agent spawn that names no model.

The routing primer says to set the model explicitly on every spawned agent,
because an omitted model inherits the session's — usually the most expensive
tier — and a default nobody chose is where top-tier spend leaks. A rule that
lives only in context is advice; this hook is what makes it hold inside skills
and forks the plugin does not own, since hooks run in subagents too.

The decision is deny, with the reason stating the routing order and the tier
each kind of work takes, which turns the call into a retry that states its
choice. That reason is also the one channel into a built-in skill's fan-out:
`/code-review` spawns its finder angles as `general-purpose` with no model, so
inside its fork this guard is what makes each angle a stated choice: a
correctness angle over top-tier work stays on the session's model, a
convention or reuse angle can take a cheaper one. Never `updatedInput` with a default: a
silently substituted cheaper model narrows the rigor of whatever was being
delegated without anyone deciding to, and review is the case where that costs
most.

Three shapes pass without a model on the call itself:

- `subagent_type: fork` — a fork always runs on the parent's model and ignores
  the field, so there is nothing to declare.
- An agent type whose definition file declares `model:` — the choice was made
  where the agent was authored, `inherit` included, since `inherit` is a stated
  decision rather than a default.
- A call the guard cannot read — malformed JSON, no tool_input — passes rather
  than blocking on the guard's own failure.

Exit status is always 0; the decision travels in the JSON on stdout.
"""

import json
import os
import sys
from pathlib import Path

REASON = (
    "Set `model` on this Agent call. The routing order is fixed: spend on the "
    "top-tier model and on high effort is minimized first, total tokens second, "
    "wall-clock time last, and a lower priority is never bought with a higher one. "
    "Use the least powerful model the task accepts — which is not the cheapest: "
    "checking another agent's work needs a model at least as capable as the one "
    "that produced it, so defect-finding and verification over top-tier work stay "
    "on the session's model (`inherit`, or name it), as do design, specification "
    "and adjudication. `sonnet` takes reading, searching, summarizing, and "
    "convention, reuse or mechanical-shape checks; `haiku` takes mechanical edits "
    "and bounded lookups. A `fork` needs no model; an agent type whose definition "
    "declares `model:` passes as well."
)


def main():
    tool_input = read_tool_input()

    if tool_input is None:
        return

    if tool_input.get("model"):
        return

    subagent_type = tool_input.get("subagent_type") or ""

    if subagent_type == "fork":
        return

    if definition_declares_model(subagent_type):
        return

    deny(REASON)


def read_tool_input():
    try:
        payload = json.load(sys.stdin)

    except (json.JSONDecodeError, ValueError):
        return None

    tool_input = payload.get("tool_input")

    if not isinstance(tool_input, dict):
        return None

    return tool_input


def definition_declares_model(subagent_type):
    if not subagent_type:
        return False

    plugin, _, agent = subagent_type.rpartition(":")

    for path in definition_files(plugin, agent):
        if "model" in frontmatter(path):
            return True

    return False


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
