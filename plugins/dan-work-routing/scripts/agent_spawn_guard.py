#!/usr/bin/env python3
"""Decides whether an Agent spawn may proceed: it must name its tier, and it
must fit the session's budget for the top tier.

The routing primer's spawn rules are advice while they live only in context;
this hook is what makes them hold inside skills and forks the plugin does not
own, since hooks run in subagents too. It applies three of them, in order:

1. **The spawn names its model.** An omitted model inherits the session's,
   usually the most expensive tier, and a default nobody chose is where
   top-tier spend leaks. A fork passes (it runs on the parent's model and
   ignores the field), as does an agent type whose definition declares
   `model:`, `inherit` included — `inherit` is a stated decision.

2. **One top-tier agent runs at a time, and the width has a ceiling.** A
   fan-out of top-tier agents is what a usage-limit trip kills mid-flight,
   wasting every one's sunk reading. In-flight agents are read from the
   harness's own records — each subagent's `agent-<id>.meta.json` and
   transcript under the session's `subagents/` directory — so the guard
   keeps no ledger that could drift. An agent is in flight while its
   transcript neither ends in a terminal stop nor has fallen silent for
   longer than the idle window. The spawner and its ancestors are not
   counted: a fork spawning a helper is not competing with itself.

3. **A sub-agent spawns a bounded number of top-tier helpers.** The root
   session's spawns are the person's own choices, one at a time; a fan-out
   inside a fork — `/code-review`'s finder angles, spawned with no model of
   their own — is nobody's. So a spawner that is itself a subagent may create
   only so many top-tier children in total. Beyond that, an angle takes
   `sonnet` or folds into one already running.

The decision is deny, with a reason that names what is in flight and the
choices that remain, which turns the call into a retry that states its
choice. Never `updatedInput` with a default: a silently substituted cheaper
model narrows the rigor of whatever was being delegated without anyone
deciding to, and review is the case where that costs most.

Limits are plugin options, exported as `CLAUDE_PLUGIN_OPTION_<KEY>`; the
defaults here match the manifest's. A limit of 0 lifts that rule.

A call the guard cannot read — malformed JSON, no tool_input, a transcript
path that resolves to no session — passes rather than blocking on the guard's
own failure. Exit status is always 0; the decision travels in the JSON on
stdout.
"""

import json
import os
import sys
import time
from pathlib import Path

CHEAP_TIER_MARKERS = ("sonnet", "haiku")

TERMINAL_STOP_REASONS = ("end_turn", "stop_sequence")

DEFAULTS = {
    "TOP_TIER_CONCURRENCY": 1,
    "AGENT_WIDTH": 8,
    "NESTED_TOP_TIER_BUDGET": 2,
    "IDLE_MINUTES": 30,
}

TAIL_BYTES = 65536

MODEL_REASON = (
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

RETRY_ADVICE = (
    "Do not re-issue this call unchanged in the same turn: end the turn and "
    "continue when the completion notification arrives, or pass `sonnet` or "
    "`haiku` if the task accepts a cheaper tier."
)


def main():
    payload = read_payload()

    if payload is None:
        return

    tool_input = payload["tool_input"]

    if not names_a_model(tool_input):
        deny(MODEL_REASON)
        return

    session = Session.from_payload(payload)

    if session is None:
        return

    spawner = payload.get("agent_id") or None
    in_flight = session.in_flight(excluding=spawner)

    width = limit("AGENT_WIDTH")

    if width and len(in_flight) >= width:
        deny(
            f"{len(in_flight)} agents are already in flight, the session's ceiling of "
            f"{width}: {describe(in_flight)}. {RETRY_ADVICE}"
        )
        return

    if spawn_tier(tool_input) != "top":
        return

    concurrency = limit("TOP_TIER_CONCURRENCY")
    top_tier = [agent for agent in in_flight if agent.tier == "top"]

    if concurrency and len(top_tier) >= concurrency:
        deny(
            f"One top-tier agent runs at a time (limit {concurrency}); in flight now: "
            f"{describe(top_tier)}. A top-tier fan-out is what a usage-limit trip "
            f"kills mid-flight, wasting every agent's reading. {RETRY_ADVICE}"
        )
        return

    budget = limit("NESTED_TOP_TIER_BUDGET")

    if spawner and budget:
        children = [
            agent for agent in session.children_of(spawner) if agent.tier == "top"
        ]

        if len(children) >= budget:
            deny(
                f"A sub-agent may spawn at most {budget} top-tier helpers in total, and "
                f"this one has spawned {len(children)}: {describe(children)}. The root "
                f"session chooses its own top-tier spawns; a fan-out inside a fork is "
                f"nobody's choice, so it is capped here. Give the remaining angle to "
                f"`sonnet`, or fold it into a helper already running."
            )


def read_payload():
    try:
        payload = json.load(sys.stdin)

    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return None

    return payload


def limit(key):
    value = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{key}")

    if value is None or value == "":
        return DEFAULTS[key]

    try:
        return max(0, int(float(value)))

    except ValueError:
        return DEFAULTS[key]


def describe(agents):
    return "; ".join(agent.label() for agent in agents)


# ── The spawn being proposed ─────────────────────────────────────────────────


def names_a_model(tool_input):
    if tool_input.get("model"):
        return True

    subagent_type = tool_input.get("subagent_type") or ""

    if subagent_type == "fork":
        return True

    return declared_model(subagent_type) is not None


def spawn_tier(tool_input):
    """`top` or `cheap`, for a call that names_a_model.

    A fork runs on the parent's model, which is the session's tier unless the
    session itself was started cheap — read as top, the conservative side.
    """
    model = tool_input.get("model")

    if model:
        return tier_of(model)

    subagent_type = tool_input.get("subagent_type") or ""

    if subagent_type == "fork":
        return "top"

    return tier_of(declared_model(subagent_type))


def tier_of(model):
    """A model name's tier. Anything not recognisably cheap — an inherited
    model, `inherit`, `opus`, a name this file has not heard of — is top."""
    if not model:
        return "top"

    name = model.lower()

    if any(marker in name for marker in CHEAP_TIER_MARKERS):
        return "cheap"

    return "top"


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


# ── The session's agents, from the harness's own records ─────────────────────


class Session:
    """The subagents a session has spawned, read from `<session>/subagents/`.

    Claude Code writes `agent-<id>.meta.json` beside each subagent's
    transcript: the type, the description, the explicit `model` when one was
    passed (absent when inherited), and the `parentAgentId` for a nested
    spawn. That directory is the ledger; this class only reads it.
    """

    def __init__(self, directory):
        self.directory = directory
        self.agents = {agent.id: agent for agent in self.read_all()}

    @classmethod
    def from_payload(cls, payload):
        """Locates `<project dir>/<session_id>/subagents/` from the transcript
        path, which is the root transcript in the main conversation and a
        subagent's own transcript inside one — both sit under the project dir."""
        session_id = payload.get("session_id")
        transcript = payload.get("transcript_path")

        if not session_id or not transcript:
            return None

        for directory in Path(transcript).parents:
            if (directory / f"{session_id}.jsonl").exists() or (
                directory / session_id / "subagents"
            ).is_dir():
                return cls(directory / session_id / "subagents")

        return None

    def read_all(self):
        if not self.directory.is_dir():
            return

        for meta in sorted(self.directory.glob("agent-*.meta.json")):
            agent = AgentRecord.read(meta)

            if agent is not None:
                yield agent

    def in_flight(self, excluding=None):
        """Agents still running, less the spawner and its ancestors — a fork
        spawning a helper is not competing with itself."""
        lineage = set(self.lineage(excluding))
        idle_seconds = limit("IDLE_MINUTES") * 60

        return [
            agent
            for agent in self.agents.values()
            if agent.id not in lineage and agent.running(idle_seconds)
        ]

    def children_of(self, spawner):
        return [agent for agent in self.agents.values() if agent.parent == spawner]

    def lineage(self, agent_id):
        seen = set()

        while agent_id and agent_id not in seen:
            seen.add(agent_id)
            yield agent_id

            agent = self.agents.get(agent_id)
            agent_id = agent.parent if agent else None


class AgentRecord:
    def __init__(self, agent_id, meta, transcript):
        self.id = agent_id
        self.type = meta.get("agentType") or "agent"
        self.description = meta.get("description") or ""
        self.model = meta.get("model")
        self.parent = meta.get("parentAgentId")
        self.transcript = transcript

    @classmethod
    def read(cls, meta_path):
        agent_id = meta_path.name[len("agent-") : -len(".meta.json")]

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        except (OSError, ValueError):
            return None

        if not isinstance(meta, dict):
            return None

        return cls(agent_id, meta, meta_path.with_name(f"agent-{agent_id}.jsonl"))

    @property
    def tier(self):
        return tier_of(self.model)

    def label(self):
        model = self.model or "session model"
        description = f"`{self.description}` " if self.description else ""

        return f"{description}({self.type}, {model})"

    def running(self, idle_seconds):
        """In flight until the transcript ends in a terminal stop, or has been
        silent past the idle window — a killed agent leaves no terminal line,
        and its silence is the only record of its death."""
        try:
            stat = self.transcript.stat()

        except OSError:
            return True  # Spawned, transcript not yet written.

        if idle_seconds and time.time() - stat.st_mtime > idle_seconds:
            return False

        return not self.ended()

    def ended(self):
        line = last_line(self.transcript)

        if line is None:
            return False

        try:
            record = json.loads(line)

        except ValueError:
            return False

        if record.get("type") != "assistant":
            return False

        message = record.get("message") or {}

        return message.get("stop_reason") in TERMINAL_STOP_REASONS


def last_line(path):
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")

    except OSError:
        return None

    lines = [line for line in tail.splitlines() if line.strip()]

    return lines[-1] if lines else None


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
