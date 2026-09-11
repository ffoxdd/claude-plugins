"""The dan-work-routing spawn guard applies the primer's spawn rules to one
Agent call: name the model, keep one top-tier agent in flight, keep the width
under a ceiling, and cap the top-tier helpers a sub-agent may create.

The hook is what makes those rules hold inside skills and forks the plugin does
not own. Its blast radius has to be exact: a fork, or a type whose definition
already chose, must pass the model rule; a spawner must never be counted as its
own competitor; a finished or dead agent must not hold the top-tier slot. It
reads the harness's own subagent records, holding its own approvals only until
those records appear, so the tests build the records — `agent-<id>.meta.json`
and a transcript — under a throwaway session directory, and a throwaway data
directory for the approvals.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import support

GUARD = support.script("dan-work-routing", "agent_spawn_guard.py")

SESSION_ID = "11111111-2222-3333-4444-555555555555"

RUNNING_LINE = json.dumps({"type": "user", "message": {"role": "user", "content": []}})

ENDED_LINE = json.dumps(
    {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn"}}
)

# What the harness appends after the final assistant message: bookkeeping
# records that carry no message at all.
ATTACHMENT_LINE = json.dumps({"type": "attachment", "attachment": {"type": "some-record"}})

# A final message as the harness records it for some models: one record per
# content block, none carrying a stop reason.
RESTING_LINE = json.dumps(
    {
        "type": "assistant",
        "message": {"role": "assistant", "stop_reason": None, "content": [{"type": "text", "text": "Findings."}]},
    }
)

# A tool call awaiting its result, recorded the same way.
TOOL_CALL_LINE = json.dumps(
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "stop_reason": None,
            "content": [{"type": "tool_use", "id": "toolu_x", "name": "Read", "input": {}}],
        },
    }
)

TOP = {"subagent_type": "general-purpose", "model": "opus", "prompt": "judge"}

CHEAP = {"subagent_type": "general-purpose", "model": "sonnet", "prompt": "read"}


def run(payload, **environment):
    result = support.run_script(GUARD, stdin=json.dumps(payload), **environment)

    if not result.stdout.strip():
        return None

    return json.loads(result.stdout)["hookSpecificOutput"]


class GuardCase(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp(prefix="agent-spawn-guard-test"))
        # A throwaway config directory, so the guard never resolves a type against
        # the developer's real agents and a test passes or fails on what it built.
        self.home = root / "home"
        self.home.mkdir()
        # The harness's layout: `<project dir>/<session>.jsonl` beside
        # `<project dir>/<session>/subagents/agent-<id>.{meta.json,jsonl}`.
        self.project = root / "projects" / "some-project"
        self.subagents = self.project / SESSION_ID / "subagents"
        self.subagents.mkdir(parents=True)
        self.root_transcript = self.project / f"{SESSION_ID}.jsonl"
        self.root_transcript.write_text("", encoding="utf-8")
        # The plugin's persistent directory, where approvals wait for their agent.
        self.data = root / "data"
        self.data.mkdir()
        self.options = {}
        self.calls = 0

    def define(self, plugin, agent, frontmatter):
        directory = self.home / "plugins" / "cache" / "shelf" / plugin / "agents"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{agent}.md").write_text(
            f"---\nname: {agent}\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8"
        )

    def record(
        self,
        agent_id,
        model=None,
        parent=None,
        description="some task",
        agent_type="general-purpose",
        ended=False,
        idle_seconds=0,
        transcript=True,
        trailing=(),
    ):
        meta = {"agentType": agent_type, "description": description, "spawnDepth": 1}

        if model:
            meta["model"] = model

        if parent:
            meta["parentAgentId"] = parent

        (self.subagents / f"agent-{agent_id}.meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )

        if not transcript:
            return

        path = self.subagents / f"agent-{agent_id}.jsonl"
        lines = [ENDED_LINE if ended else RUNNING_LINE, *trailing]
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")

        if idle_seconds:
            stamp = time.time() - idle_seconds
            os.utime(path, (stamp, stamp))

    def payload(self, tool_input, spawner=None, transcript=None, tool_use_id=None):
        self.calls += 1
        payload = {
            "tool_name": "Agent",
            "tool_input": tool_input,
            "tool_use_id": tool_use_id or f"toolu_{self.calls:04d}",
            "session_id": SESSION_ID,
            "transcript_path": str(transcript or self.root_transcript),
        }

        if spawner:
            payload["agent_id"] = spawner

        return payload

    def environment(self):
        environment = {
            f"CLAUDE_PLUGIN_OPTION_{key}": str(value) for key, value in self.options.items()
        }
        environment["CLAUDE_CONFIG_DIR"] = str(self.home)
        environment["CLAUDE_PLUGIN_DATA"] = str(self.data)

        return environment

    def decide(self, tool_input, **keywords):
        return run(self.payload(tool_input, **keywords), **self.environment())

    def pending_file(self):
        return self.data / "spawn-guard" / f"{SESSION_ID}.jsonl"

    def pending_entries(self):
        try:
            lines = self.pending_file().read_text(encoding="utf-8").splitlines()

        except OSError:
            return []

        return [json.loads(line) for line in lines if line.strip()]

    def decision(self, *arguments, **keywords):
        output = self.decide(*arguments, **keywords)

        return None if output is None else output["permissionDecision"]

    def reason(self, *arguments, **keywords):
        return self.decide(*arguments, **keywords)["permissionDecisionReason"]


class ModelRuleTest(GuardCase):
    def test_denies_a_spawn_that_names_no_model(self):
        self.assertEqual(
            self.decision({"subagent_type": "general-purpose", "prompt": "look around"}),
            "deny",
        )

    def test_denies_when_the_type_is_omitted_too(self):
        self.assertEqual(self.decision({"prompt": "look around"}), "deny")

    def test_permits_a_spawn_that_names_its_model(self):
        self.assertIsNone(self.decision(CHEAP))

    def test_permits_a_fork(self):
        """A fork runs on the parent's model and ignores the field; demanding it
        would only teach callers to type a value that changes nothing."""
        self.assertIsNone(self.decision({"subagent_type": "fork", "prompt": "carry on"}))

    def test_permits_a_type_whose_definition_declares_a_model(self):
        self.define("shelf-plugin", "reader", "model: haiku\neffort: low")

        self.assertIsNone(self.decision({"subagent_type": "shelf-plugin:reader", "prompt": "x"}))

    def test_inherit_is_a_declaration(self):
        """`inherit` names the session's model on purpose; the rule is against an
        omission, not against that choice."""
        self.define("shelf-plugin", "judge", "model: inherit\neffort: high")

        self.assertIsNone(self.decision({"subagent_type": "shelf-plugin:judge", "prompt": "x"}))

    def test_denies_a_type_whose_definition_declares_no_model(self):
        self.define("shelf-plugin", "drifter", "effort: high")

        self.assertEqual(
            self.decision({"subagent_type": "shelf-plugin:drifter", "prompt": "x"}), "deny"
        )

    def test_names_the_tiers_in_the_reason(self):
        reason = self.reason({"prompt": "x"})

        for tier in ("haiku", "sonnet", "fork"):
            self.assertIn(tier, reason)

    def test_states_the_routing_order_in_the_reason(self):
        """The reason is the one channel into a fan-out the plugin does not own,
        so it carries the order itself rather than pointing at the primer."""
        reason = self.reason({"prompt": "x"})

        self.assertLess(reason.index("top-tier"), reason.index("total tokens"))
        self.assertLess(reason.index("total tokens"), reason.index("wall-clock"))

    def test_passes_on_input_it_cannot_read(self):
        result = support.run_script(GUARD, stdin="not json")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_passes_when_the_session_cannot_be_located(self):
        """A model-naming call with no readable session is the guard's own gap,
        not the caller's; it never blocks on that."""
        payload = {"tool_name": "Agent", "tool_input": TOP, "session_id": "nope"}

        self.assertIsNone(run(payload, CLAUDE_CONFIG_DIR=str(self.home)))


class TopTierConcurrencyTest(GuardCase):
    def test_denies_a_top_tier_spawn_while_a_top_tier_agent_runs(self):
        self.record("a1", model="opus", description="review the merge slice")

        self.assertEqual(self.decision(TOP), "deny")

    def test_an_inherited_model_is_top_tier(self):
        """The meta carries no `model` when the spawn inherited the session's;
        that is the expensive tier, not an unknown one."""
        self.record("a1")

        self.assertEqual(self.decision(TOP), "deny")

    def test_a_fork_counts_as_top_tier(self):
        self.record("a1")

        self.assertEqual(self.decision({"subagent_type": "fork", "prompt": "x"}), "deny")

    def test_a_definition_that_inherits_counts_as_top_tier(self):
        self.define("shelf-plugin", "judge", "model: inherit\neffort: high")
        self.record("a1")

        self.assertEqual(
            self.decision({"subagent_type": "shelf-plugin:judge", "prompt": "x"}), "deny"
        )

    def test_permits_a_cheap_spawn_beside_a_top_tier_agent(self):
        self.record("a1")

        self.assertIsNone(self.decision(CHEAP))

    def test_permits_a_top_tier_spawn_beside_cheap_agents(self):
        self.record("a1", model="sonnet")
        self.record("a2", model="haiku")

        self.assertIsNone(self.decision(TOP))

    def test_a_finished_agent_holds_no_slot(self):
        self.record("a1", ended=True)

        self.assertIsNone(self.decision(TOP))

    def test_a_finished_agent_followed_by_attachments_holds_no_slot(self):
        """The harness writes attachment records after the final assistant
        message, so the transcript's last line is never the terminal stop; the
        newest assistant record is what says the turn ended."""
        self.record("a1", ended=True, trailing=(ATTACHMENT_LINE, ATTACHMENT_LINE))

        self.assertIsNone(self.decision(TOP))

    def test_a_resumed_agent_is_in_flight_again(self):
        """A user record newer than the terminal stop is a new prompt or a tool
        result: the agent is running, whatever its earlier turn said."""
        self.record("a1", ended=True, trailing=(ATTACHMENT_LINE, RUNNING_LINE))

        self.assertEqual(self.decision(TOP), "deny")

    def test_a_final_message_recorded_without_a_stop_reason_frees_the_slot_once_settled(self):
        """Some models' final message is recorded one block at a time with no
        stop reason on any record; a newest assistant record that awaits no tool
        result is the turn's end once the transcript has been quiet for the
        settle window, not the idle window."""
        self.record("a1", trailing=(RESTING_LINE, ATTACHMENT_LINE), idle_seconds=3 * 60)

        self.assertIsNone(self.decision(TOP))

    def test_a_final_message_recorded_without_a_stop_reason_still_counts_while_fresh(self):
        """The same record is what a message still streaming looks like between
        its blocks, so it holds the slot until the transcript settles."""
        self.record("a1", trailing=(RESTING_LINE,), idle_seconds=30)

        self.assertEqual(self.decision(TOP), "deny")

    def test_a_tool_call_awaiting_its_result_holds_the_slot_past_the_settle_window(self):
        self.record("a1", trailing=(TOOL_CALL_LINE,), idle_seconds=3 * 60)

        self.assertEqual(self.decision(TOP), "deny")

    def test_the_settle_window_is_a_plugin_option(self):
        self.options["SETTLE_SECONDS"] = 0
        self.record("a1", trailing=(RESTING_LINE,), idle_seconds=3 * 60)

        self.assertEqual(self.decision(TOP), "deny")

    def test_a_silent_agent_is_taken_for_dead(self):
        """A killed agent writes no terminal line; past the idle window its
        silence is read as death rather than as a slot held forever."""
        self.record("a1", idle_seconds=31 * 60)

        self.assertIsNone(self.decision(TOP))

    def test_a_fresh_silent_agent_still_counts(self):
        self.record("a1", idle_seconds=5 * 60)

        self.assertEqual(self.decision(TOP), "deny")

    def test_a_spawn_with_no_transcript_yet_counts(self):
        self.record("a1", transcript=False)

        self.assertEqual(self.decision(TOP), "deny")

    def test_the_spawner_is_not_its_own_competitor(self):
        """Inside a fork the only top-tier agent in flight may be the fork
        itself; its first helper must pass."""
        self.record("fork1", agent_type="fork")

        self.assertIsNone(self.decision(TOP, spawner="fork1"))

    def test_the_spawners_ancestors_are_not_competitors_either(self):
        self.record("fork1", agent_type="fork")
        self.record("mid", parent="fork1")

        self.assertIsNone(self.decision(TOP, spawner="mid"))

    def test_a_sibling_inside_the_fork_is_a_competitor(self):
        self.record("fork1", agent_type="fork")
        self.record("angle1", parent="fork1", description="correctness angle")

        self.assertEqual(self.decision(TOP, spawner="fork1"), "deny")

    def test_locates_the_session_from_a_subagent_transcript(self):
        self.record("fork1", agent_type="fork")
        self.record("angle1", parent="fork1")

        transcript = self.subagents / "agent-fork1.jsonl"

        self.assertEqual(self.decision(TOP, spawner="fork1", transcript=transcript), "deny")

    def test_the_reason_names_what_is_in_flight(self):
        self.record("a1", model="opus", description="review the merge slice")

        reason = self.reason(TOP)

        self.assertIn("review the merge slice", reason)
        self.assertIn("opus", reason)
        self.assertIn("end the turn", reason)

    def test_the_limit_is_an_option(self):
        self.record("a1")
        self.options["TOP_TIER_CONCURRENCY"] = 2

        self.assertIsNone(self.decision(TOP))

    def test_zero_lifts_the_limit(self):
        self.record("a1")
        self.record("a2")
        self.options["TOP_TIER_CONCURRENCY"] = 0

        self.assertIsNone(self.decision(TOP))


class WidthTest(GuardCase):
    def test_denies_any_spawn_at_the_width_ceiling(self):
        for index in range(8):
            self.record(f"a{index}", model="sonnet")

        self.assertEqual(self.decision(CHEAP), "deny")
        self.assertIn("ceiling", self.reason(CHEAP))

    def test_permits_under_the_ceiling(self):
        for index in range(7):
            self.record(f"a{index}", model="sonnet")

        self.assertIsNone(self.decision(CHEAP))

    def test_the_ceiling_is_an_option(self):
        for index in range(3):
            self.record(f"a{index}", model="sonnet")

        self.options["AGENT_WIDTH"] = 3

        self.assertEqual(self.decision(CHEAP), "deny")


class NestedBudgetTest(GuardCase):
    """A fan-out inside a fork is nobody's choice, so its top-tier helpers are
    counted in total — finished ones included — against a small budget."""

    def setUp(self):
        super().setUp()
        self.record("fork1", agent_type="fork", description="/code-review")

    def test_denies_a_third_top_tier_helper(self):
        self.record("angle1", parent="fork1", ended=True, description="correctness")
        self.record("angle2", parent="fork1", ended=True, description="verify")

        self.assertEqual(self.decision(TOP, spawner="fork1"), "deny")

    def test_the_reason_names_the_helpers_and_the_way_out(self):
        self.record("angle1", parent="fork1", ended=True, description="correctness")
        self.record("angle2", parent="fork1", ended=True, description="verify")

        reason = self.reason(TOP, spawner="fork1")

        self.assertIn("correctness", reason)
        self.assertIn("sonnet", reason)

    def test_permits_a_cheap_helper_past_the_budget(self):
        self.record("angle1", parent="fork1", ended=True)
        self.record("angle2", parent="fork1", ended=True)

        self.assertIsNone(self.decision(CHEAP, spawner="fork1"))

    def test_cheap_helpers_do_not_spend_the_top_tier_budget(self):
        self.record("angle1", parent="fork1", model="sonnet", ended=True)
        self.record("angle2", parent="fork1", model="sonnet", ended=True)

        self.assertIsNone(self.decision(TOP, spawner="fork1"))

    def test_another_forks_helpers_are_not_this_ones(self):
        self.record("fork2", agent_type="fork", ended=True)
        self.record("other1", parent="fork2", ended=True)
        self.record("other2", parent="fork2", ended=True)

        self.assertIsNone(self.decision(TOP, spawner="fork1"))

    def test_the_root_session_has_no_helper_budget(self):
        """The root's spawns are the person's own choices, governed by the
        concurrency rule alone."""
        self.record("fork1", agent_type="fork", ended=True)
        self.record("done1", ended=True)
        self.record("done2", ended=True)
        self.record("done3", ended=True)

        self.assertIsNone(self.decision(TOP))

    def test_the_budget_is_an_option(self):
        self.record("angle1", parent="fork1", ended=True)
        self.record("angle2", parent="fork1", ended=True)
        self.options["NESTED_TOP_TIER_BUDGET"] = 3

        self.assertIsNone(self.decision(TOP, spawner="fork1"))


class NestedTotalBudgetTest(GuardCase):
    """Every helper a fork spawns re-reads the fork's material, whatever its
    tier, so a sub-agent's helpers are also capped in total."""

    def setUp(self):
        super().setUp()
        self.record("fork1", agent_type="fork", description="/code-review")

    def test_denies_a_fourth_helper_of_any_tier(self):
        for index in range(3):
            self.record(f"angle{index}", parent="fork1", model="sonnet", ended=True)

        self.assertEqual(self.decision(CHEAP, spawner="fork1"), "deny")
        self.assertIn("at most 3 helpers in total", self.reason(CHEAP, spawner="fork1"))

    def test_permits_a_third(self):
        self.record("angle1", parent="fork1", model="sonnet", ended=True)
        self.record("angle2", parent="fork1", model="sonnet", ended=True)

        self.assertIsNone(self.decision(CHEAP, spawner="fork1"))

    def test_the_top_tier_budget_binds_first_within_the_total(self):
        """Three helpers, at most two top-tier: the third top-tier is refused by
        the tier budget while a cheap third still passes."""
        self.options["TOP_TIER_CONCURRENCY"] = 0
        self.record("angle1", parent="fork1", ended=True)
        self.record("angle2", parent="fork1", ended=True)

        self.assertIn("top-tier helpers", self.reason(TOP, spawner="fork1"))
        self.assertIsNone(self.decision(CHEAP, spawner="fork1"))

    def test_the_root_session_is_not_budgeted(self):
        for index in range(5):
            self.record(f"done{index}", model="sonnet", ended=True)

        self.assertIsNone(self.decision(CHEAP))

    def test_approvals_count(self):
        self.decision(CHEAP, spawner="fork1")
        self.decision(CHEAP, spawner="fork1")
        self.decision(CHEAP, spawner="fork1")

        self.assertEqual(self.decision(CHEAP, spawner="fork1"), "deny")

    def test_the_budget_is_an_option(self):
        for index in range(3):
            self.record(f"angle{index}", parent="fork1", model="sonnet", ended=True)

        self.options["NESTED_AGENT_BUDGET"] = 4

        self.assertIsNone(self.decision(CHEAP, spawner="fork1"))


class PendingApprovalTest(GuardCase):
    """The harness writes an agent's record after the spawn, so two spawns in one
    batch are each checked before either exists. The guard's own approvals
    fill that gap, and hand over to the harness record once it appears."""

    def test_an_approval_is_recorded(self):
        self.assertIsNone(self.decision(TOP, tool_use_id="toolu_first"))

        entries = self.pending_entries()

        self.assertEqual([entry["tool_use_id"] for entry in entries], ["toolu_first"])
        self.assertEqual(entries[0]["tier"], "top")

    def test_a_denial_is_not_recorded(self):
        self.record("a1")

        self.assertEqual(self.decision(TOP), "deny")
        self.assertEqual(self.pending_entries(), [])

    def test_a_second_top_tier_spawn_in_the_same_batch_is_denied(self):
        self.assertIsNone(self.decision(TOP, tool_use_id="toolu_first"))

        self.assertEqual(self.decision(TOP, tool_use_id="toolu_second"), "deny")

    def test_the_reason_names_the_approved_spawn(self):
        self.decision({**TOP, "description": "review the merge slice"})

        reason = self.reason(TOP)

        self.assertIn("review the merge slice", reason)
        self.assertIn("just approved", reason)

    def test_a_cheap_approval_does_not_hold_the_top_tier_slot(self):
        self.assertIsNone(self.decision(CHEAP))

        self.assertIsNone(self.decision(TOP))

    def test_approvals_count_toward_the_width(self):
        self.options["AGENT_WIDTH"] = 2
        self.decision(CHEAP)
        self.decision(CHEAP)

        self.assertEqual(self.decision(CHEAP), "deny")

    def test_the_harness_record_takes_over_from_the_approval(self):
        """Once the meta carrying the approval's tool_use_id exists, the agent's
        real state governs — here, finished — and the approval is dropped."""
        self.assertIsNone(self.decision(TOP, tool_use_id="toolu_first"))

        meta = self.subagents / "agent-a1.meta.json"
        self.record("a1", ended=True)
        meta.write_text(
            json.dumps({**json.loads(meta.read_text()), "toolUseId": "toolu_first"}),
            encoding="utf-8",
        )

        self.assertIsNone(self.decision(TOP, tool_use_id="toolu_second"))
        self.assertNotIn("toolu_first", [e["tool_use_id"] for e in self.pending_entries()])

    def test_an_approval_expires_unmatched(self):
        """A spawn approved here but never recorded by the harness was refused
        downstream or failed; past its window it stops holding the slot."""
        self.pending_file().parent.mkdir(parents=True)
        self.pending_file().write_text(
            json.dumps(
                {
                    "tool_use_id": "toolu_old",
                    "type": "general-purpose",
                    "model": "opus",
                    "tier": "top",
                    "at": time.time() - 121,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertIsNone(self.decision(TOP))

    def test_approvals_count_toward_a_sub_agents_helper_budget(self):
        self.record("fork1", agent_type="fork")

        self.assertIsNone(self.decision(TOP, spawner="fork1", tool_use_id="toolu_1"))
        # The first helper now holds the concurrency slot; lift that rule to
        # isolate the budget.
        self.options["TOP_TIER_CONCURRENCY"] = 0
        self.assertIsNone(self.decision(TOP, spawner="fork1", tool_use_id="toolu_2"))

        reason = self.reason(TOP, spawner="fork1", tool_use_id="toolu_3")

        self.assertIn("at most 2 top-tier helpers", reason)

    def test_simultaneous_hooks_admit_exactly_one_top_tier_spawn(self):
        """Parallel tool calls run their hooks at once; the lock is what makes the
        second see the first."""
        import subprocess
        import sys

        processes = [
            subprocess.Popen(
                [sys.executable, str(GUARD)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                env=support.environment(**self.environment()),
            )
            for _ in range(4)
        ]
        outputs = [
            process.communicate(json.dumps(self.payload(TOP)))[0] for process in processes
        ]
        denials = [output for output in outputs if "deny" in output]

        self.assertEqual(len(denials), 3, outputs)
        self.assertFalse(self.pending_file().with_suffix(".lock").exists())


class PluginAgentsTest(unittest.TestCase):
    """The plugin's own agents must satisfy the guard it ships."""

    def test_every_shipped_agent_declares_a_model(self):
        agents = support.plugin_root("dan-work-routing") / "agents"

        for path in sorted(agents.glob("*.md")):
            with self.subTest(agent=path.name):
                self.assertIn("model", support.frontmatter(path))


class ManifestOptionsTest(unittest.TestCase):
    """Every limit the guard reads is declared to the person as an option, with
    the same default the script falls back to."""

    def test_each_limit_is_a_declared_option_with_the_scripts_default(self):
        manifest = support.read_json(
            support.plugin_root("dan-work-routing") / ".claude-plugin" / "plugin.json"
        )
        options = manifest["userConfig"]
        source = GUARD.read_text(encoding="utf-8")

        for key in (
            "top_tier_concurrency",
            "agent_width",
            "nested_top_tier_budget",
            "nested_agent_budget",
            "idle_minutes",
        ):
            with self.subTest(option=key):
                self.assertIn(key, options)
                self.assertEqual(options[key]["type"], "number")
                self.assertIn(f'"{key.upper()}": {options[key]["default"]},', source)


if __name__ == "__main__":
    unittest.main()
