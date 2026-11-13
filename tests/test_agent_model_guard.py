"""The dan-work-routing model guard holds one of the primer's spawn rules on an
Agent call: the spawn says which model it runs on.

The hook is what makes that rule hold inside skills and forks the plugin does
not own. Its blast radius has to be exact: a fork, a type whose definition
already chose, and a session that configured a default sub-agent model must all
pass, and the denial must state the routing order itself, since it is the one
channel into a fan-out the plugin does not own. Agent definitions are built
under a throwaway config directory, so a test never resolves a type against the
developer's real agents.
"""

import json
import tempfile
import unittest
from pathlib import Path

import support

GUARD = support.script("dan-work-routing", "agent_model_guard.py")

UNNAMED = {"subagent_type": "general-purpose", "prompt": "look around"}


def run(payload, **environment):
    result = support.run_script(GUARD, stdin=json.dumps(payload), **environment)

    if not result.stdout.strip():
        return None

    return json.loads(result.stdout)["hookSpecificOutput"]


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="agent-model-guard-test"))

    def define(self, plugin, agent, frontmatter):
        directory = self.home / "plugins" / "cache" / "shelf" / plugin / "agents"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{agent}.md").write_text(
            f"---\nname: {agent}\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8"
        )

    def decide(self, tool_input, **environment):
        payload = {"tool_name": "Agent", "tool_input": tool_input}

        return run(payload, CLAUDE_CONFIG_DIR=str(self.home), **environment)

    def decision(self, *arguments, **environment):
        output = self.decide(*arguments, **environment)

        return None if output is None else output["permissionDecision"]

    def reason(self, *arguments, **environment):
        return self.decide(*arguments, **environment)["permissionDecisionReason"]


class ModelRuleTest(GuardCase):
    def test_denies_a_spawn_that_names_no_model(self):
        self.assertEqual(self.decision(UNNAMED), "deny")

    def test_denies_when_the_type_is_omitted_too(self):
        self.assertEqual(self.decision({"prompt": "look around"}), "deny")

    def test_permits_a_spawn_that_names_its_model(self):
        self.assertIsNone(self.decision({**UNNAMED, "model": "sonnet"}))

    def test_permits_a_fork(self):
        """A fork runs on the session's model and ignores the field; demanding it
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

        for tier in ("opus", "haiku", "sonnet", "fork"):
            self.assertIn(tier, reason)

    def test_states_the_routing_order_in_the_reason(self):
        """The reason is the one channel into a fan-out the plugin does not own,
        so it carries the order itself rather than pointing at the primer."""
        reason = self.reason({"prompt": "x"})

        self.assertLess(reason.index("top-tier"), reason.index("total tokens"))
        self.assertLess(reason.index("total tokens"), reason.index("wall-clock"))

    def test_names_the_default_model_variable_in_the_reason(self):
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL", self.reason(UNNAMED))

    def test_passes_on_input_it_cannot_read(self):
        result = support.run_script(GUARD, stdin="not json")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class DefaultModelTest(GuardCase):
    """With a default sub-agent model configured, the platform gives an unnamed
    spawn that model, so the omission is a configured choice rather than a leak."""

    def test_passes_an_unnamed_spawn_when_the_variable_is_set(self):
        self.assertIsNone(self.decision(UNNAMED, CLAUDE_CODE_SUBAGENT_MODEL="opus"))

    def test_denies_when_the_variable_is_empty(self):
        self.assertEqual(self.decision(UNNAMED, CLAUDE_CODE_SUBAGENT_MODEL=""), "deny")

    def test_denies_when_the_variable_is_only_whitespace(self):
        self.assertEqual(self.decision(UNNAMED, CLAUDE_CODE_SUBAGENT_MODEL="  "), "deny")

    def test_denies_when_the_variable_is_unset(self):
        self.assertEqual(self.decision(UNNAMED), "deny")

    def test_inherit_in_the_variable_is_no_default(self):
        """The platform reads `inherit` there as unset: the spawn would take the
        session's model, which is the default nobody chose."""
        self.assertEqual(self.decision(UNNAMED, CLAUDE_CODE_SUBAGENT_MODEL="inherit"), "deny")


class HookWiringTest(unittest.TestCase):
    def test_the_hook_runs_on_every_agent_call(self):
        hooks = support.read_json(
            support.plugin_root("dan-work-routing") / "hooks" / "hooks.json"
        )["hooks"]["PreToolUse"]

        commands = [
            hook["command"]
            for matcher in hooks
            if matcher.get("matcher") == "Agent"
            for hook in matcher["hooks"]
        ]

        self.assertTrue(any("agent_model_guard.py" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
