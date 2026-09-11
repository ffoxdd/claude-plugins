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
   transcript under the session's `subagents/` directory. An agent is in
   flight while its newest assistant record is not a terminal stop (the
   harness appends attachments after the final message, so the last LINE
   says nothing) and it has not fallen silent for longer than the idle
   window. Some models' final message is recorded with no stop reason at
   all - one record per content block, none of them terminal - so a newest
   assistant record that awaits no tool result and carries no stop reason
   is read as the turn's end once the transcript has been quiet for the
   settle window, which is seconds where the idle window is minutes: a
   message still streaming writes its next block within it, a finished one
   never writes again. Those records lag the
   decision by one batch: spawns issued in one message are checked before
   any of them exists, which is exactly the shape of a review fan-out. So
   each approval is also written to a pending file, keyed by the call's
   tool_use_id, and stands in for the agent until the harness writes the
   meta carrying that same id — or expires unmatched, a spawn that never
   happened. The file is read and written under a lock so same-batch hooks
   see each other. The spawner and its ancestors are not counted: a fork
   spawning a helper is not competing with itself.

3. **A sub-agent spawns a bounded number of helpers.** The root session's
   spawns are the person's own choices, one at a time; a fan-out inside a
   fork — `/code-review`'s finder angles, spawned with no model of their own
   — is nobody's, and every angle re-reads the same diff. So a spawner that
   is itself a subagent may create only so many children in total, and fewer
   of them top-tier. Beyond the top-tier budget an angle takes `sonnet`;
   beyond the total, it folds into a helper already running.

The decision is deny, with a reason that names what is in flight and the
choices that remain, which turns the call into a retry that states its
choice. Never `updatedInput` with a default: a silently substituted cheaper
model narrows the rigor of whatever was being delegated without anyone
deciding to, and review is the case where that costs most.

Limits are plugin options, exported as `CLAUDE_PLUGIN_OPTION_<KEY>`; the
defaults here match the manifest's. A limit of 0 lifts that rule. The
pending file lives under `CLAUDE_PLUGIN_DATA`, the plugin's persistent
directory, one file per session.

A call the guard cannot read — malformed JSON, no tool_input, a transcript
path that resolves to no session — passes rather than blocking on the guard's
own failure. Exit status is always 0; the decision travels in the JSON on
stdout.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

CHEAP_TIER_MARKERS = ("sonnet", "haiku")

TERMINAL_STOP_REASONS = ("end_turn", "stop_sequence")

# What the newest assistant record says of an agent's turn (AgentRecord.standing).
ENDED, RESTING, WORKING = "ended", "resting", "working"

DEFAULTS = {
    "TOP_TIER_CONCURRENCY": 1,
    "AGENT_WIDTH": 8,
    "NESTED_TOP_TIER_BUDGET": 2,
    "NESTED_AGENT_BUDGET": 3,
    "IDLE_MINUTES": 30,
    "SETTLE_SECONDS": 120,
}

TAIL_BYTES = 65536

# An approval with no matching harness record after this long was a spawn that
# never happened — denied downstream, or failed — and stops counting.
PENDING_SECONDS = 120

LOCK_WAIT_SECONDS = 2.0

LOCK_STALE_SECONDS = 10.0

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

    with Pending.locked(session) as pending:
        decide(payload, tool_input, session, pending)


def decide(payload, tool_input, session, pending):
    spawner = payload.get("agent_id") or None
    tier = spawn_tier(tool_input)
    in_flight = session.in_flight(excluding=spawner) + pending.in_flight()

    width = limit("AGENT_WIDTH")

    if width and len(in_flight) >= width:
        deny(
            f"{len(in_flight)} agents are already in flight, the session's ceiling of "
            f"{width}: {describe(in_flight)}. {RETRY_ADVICE}"
        )
        return

    total_budget = limit("NESTED_AGENT_BUDGET")

    if spawner and total_budget:
        children = session.children_of(spawner) + pending.children_of(spawner)

        if len(children) >= total_budget:
            deny(
                f"A sub-agent may spawn at most {total_budget} helpers in total, and this "
                f"one has spawned {len(children)}: {describe(children)}. A fan-out inside "
                f"a fork re-reads the same material once per helper, so it is capped "
                f"here; fold the remaining work into a helper already running, or do it "
                f"in this agent."
            )
            return

    if tier != "top":
        pending.record(payload, tool_input, tier, spawner)
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
            agent
            for agent in session.children_of(spawner) + pending.children_of(spawner)
            if agent.tier == "top"
        ]

        if len(children) >= budget:
            deny(
                f"A sub-agent may spawn at most {budget} top-tier helpers in total, and "
                f"this one has spawned {len(children)}: {describe(children)}. The root "
                f"session chooses its own top-tier spawns; a fan-out inside a fork is "
                f"nobody's choice, so it is capped here. Give the remaining angle to "
                f"`sonnet`, or fold it into a helper already running."
            )
            return

    pending.record(payload, tool_input, tier, spawner)


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
        self.tool_use_ids = {agent.tool_use_id for agent in self.agents.values()}

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
        settle_seconds = limit("SETTLE_SECONDS")

        return [
            agent
            for agent in self.agents.values()
            if agent.id not in lineage and agent.running(idle_seconds, settle_seconds)
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
        self.tool_use_id = meta.get("toolUseId")
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

    def running(self, idle_seconds, settle_seconds=0):
        """In flight until the newest assistant record is a terminal stop, or the
        transcript has been silent past the idle window - a killed agent leaves
        no terminal line, and its silence is the only record of its death - or a
        final message recorded with no stop reason has been quiet for the settle
        window."""
        try:
            stat = self.transcript.stat()

        except OSError:
            return True  # Spawned, transcript not yet written.

        silent = time.time() - stat.st_mtime

        if idle_seconds and silent > idle_seconds:
            return False

        standing = self.standing()

        if standing == ENDED:
            return False

        return not (standing == RESTING and settle_seconds and silent > settle_seconds)

    def standing(self):
        """What the newest assistant record says of the agent's turn: ENDED on a
        terminal stop; RESTING where the record carries no stop reason and awaits
        no tool result - the shape a finished message takes for a model whose
        final message the harness records one block at a time, and equally the
        shape of a text block whose message is still streaming, which is why
        RESTING frees a slot only once the transcript has settled; WORKING
        otherwise. The harness appends bookkeeping records - attachments, system
        notes - after the final assistant message, so the record read is the
        newest ASSISTANT one, not the newest line. A user record newer than it is
        a new prompt or a tool result: the agent is running again, whatever came
        before."""
        for line in reversed(tail_lines(self.transcript)):
            try:
                record = json.loads(line)

            except ValueError:
                continue

            kind = record.get("type")

            if kind == "user":
                return WORKING

            if kind == "assistant":
                message = record.get("message") or {}
                stop_reason = message.get("stop_reason")

                if stop_reason in TERMINAL_STOP_REASONS:
                    return ENDED

                if stop_reason is None and not awaits_tool_result(message):
                    return RESTING

                return WORKING

        return WORKING


# ── Approvals the harness has not yet recorded ───────────────────────────────


class PendingSpawn:
    """An approved spawn standing in for its agent until the meta appears."""

    def __init__(self, entry):
        self.tool_use_id = entry.get("tool_use_id")
        self.type = entry.get("type") or "agent"
        self.description = entry.get("description") or ""
        self.model = entry.get("model")
        self.parent = entry.get("spawner")
        self.at = entry.get("at") or 0
        self.tier = entry.get("tier") or "top"

    def to_entry(self):
        return {
            "tool_use_id": self.tool_use_id,
            "type": self.type,
            "description": self.description,
            "model": self.model,
            "spawner": self.parent,
            "at": self.at,
            "tier": self.tier,
        }

    def label(self):
        model = self.model or "session model"
        description = f"`{self.description}` " if self.description else ""

        return f"{description}({self.type}, {model}, just approved)"

    def live(self, session, now):
        if self.tool_use_id and self.tool_use_id in session.tool_use_ids:
            return False  # The harness's record has taken over.

        return now - self.at <= PENDING_SECONDS


class Pending:
    """The guard's own approvals for one session, in one JSONL file.

    Read whole and rewritten compacted under the lock, so an entry lives only
    until its agent's meta appears or its window passes.
    """

    def __init__(self, session, path):
        self.session = session
        self.path = path
        self.entries = []

    @classmethod
    def locked(cls, session):
        return _PendingContext(session)

    def load(self):
        now = time.time()

        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()

        except OSError:
            lines = []

        for line in lines:
            try:
                entry = PendingSpawn(json.loads(line))

            except ValueError:
                continue

            if entry.live(self.session, now):
                self.entries.append(entry)

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                "".join(json.dumps(entry.to_entry()) + "\n" for entry in self.entries),
                encoding="utf-8",
            )

        except OSError:
            pass

    def in_flight(self):
        return list(self.entries)

    def children_of(self, spawner):
        return [entry for entry in self.entries if entry.parent == spawner]

    def record(self, payload, tool_input, tier, spawner):
        self.entries.append(
            PendingSpawn(
                {
                    "tool_use_id": payload.get("tool_use_id"),
                    "type": tool_input.get("subagent_type") or "general-purpose",
                    "description": tool_input.get("description") or "",
                    "model": tool_input.get("model"),
                    "spawner": spawner,
                    "at": time.time(),
                    "tier": tier,
                }
            )
        )


class _PendingContext:
    def __init__(self, session):
        self.session = session
        self.path = pending_path(session)
        self.lock = self.path.with_suffix(".lock")
        self.held = False

    def __enter__(self):
        self.acquire()
        self.pending = Pending(self.session, self.path)
        self.pending.load()

        return self.pending

    def __exit__(self, *exception):
        self.pending.save()
        self.release()

        return False

    def acquire(self):
        """A create-exclusive lock file, waited on briefly; a lock nobody has
        released in LOCK_STALE_SECONDS belonged to a hook that died and is
        broken. Failing to acquire fails open — the guard never blocks on itself."""
        deadline = time.time() + LOCK_WAIT_SECONDS

        try:
            self.lock.parent.mkdir(parents=True, exist_ok=True)

        except OSError:
            return

        while True:
            try:
                os.close(os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                self.held = True
                return

            except FileExistsError:
                try:
                    if time.time() - self.lock.stat().st_mtime > LOCK_STALE_SECONDS:
                        self.lock.unlink()
                        continue

                except OSError:
                    continue

            except OSError:
                return

            if time.time() > deadline:
                return

            time.sleep(0.02)

    def release(self):
        if not self.held:
            return

        try:
            self.lock.unlink()

        except OSError:
            pass


def pending_path(session):
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        tempfile.gettempdir(), "dan-work-routing"
    )
    session_id = session.directory.parent.name

    return Path(base) / "spawn-guard" / f"{session_id}.jsonl"


def awaits_tool_result(message):
    """Whether an assistant message holds a tool call, whose result the harness
    will write as a user record."""
    content = message.get("content")

    if not isinstance(content, list):
        return False

    return any(isinstance(block, dict) and block.get("type") == "tool_use" for block in content)


def tail_lines(path):
    """The non-empty lines in the transcript's last TAIL_BYTES, oldest first;
    empty when the file cannot be read."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")

    except OSError:
        return []

    return [line for line in tail.splitlines() if line.strip()]


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
