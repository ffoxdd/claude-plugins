"""The dan-work-routing spawn guard denies one shape: an Agent call that names
no model and has no other declaration to stand on.

The rule it enforces is the primer's — set the model on every spawned agent —
and the hook is what makes that hold inside skills and forks the plugin does
not own. Its blast radius has to be exact: a fork, or a type whose definition
already chose, must pass, or the guard becomes an obstacle to the routing it is
meant to protect.
"""

import json
import tempfile
import unittest
from pathlib import Path

import support

GUARD = support.script("dan-work-routing", "agent_model_guard.py")


def decision(tool_input, **environment):
    payload = json.dumps({"tool_name": "Agent", "tool_input": tool_input})
    result = support.run_script(GUARD, stdin=payload, **environment)

    if not result.stdout.strip():
        return None

    return json.loads(result.stdout).get("hookSpecificOutput", {}).get("permissionDecision")


class DecisionTest(unittest.TestCase):
    def setUp(self):
        # A throwaway config directory, so the guard never resolves a type against
        # the developer's real agents and a test passes or fails on what it built.
        self.home = Path(tempfile.mkdtemp(prefix="agent-model-guard-test"))

    def spawn(self, tool_input):
        return decision(tool_input, CLAUDE_CONFIG_DIR=str(self.home))

    def define(self, plugin, agent, frontmatter):
        directory = self.home / "plugins" / "cache" / "shelf" / plugin / "agents"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{agent}.md").write_text(
            f"---\nname: {agent}\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8"
        )

    def test_denies_a_spawn_that_names_no_model(self):
        self.assertEqual(
            self.spawn({"subagent_type": "general-purpose", "prompt": "look around"}),
            "deny",
        )

    def test_denies_when_the_type_is_omitted_too(self):
        self.assertEqual(self.spawn({"prompt": "look around"}), "deny")

    def test_permits_a_spawn_that_names_its_model(self):
        self.assertIsNone(
            self.spawn({"subagent_type": "general-purpose", "model": "haiku", "prompt": "x"})
        )

    def test_permits_a_fork(self):
        """A fork runs on the parent's model and ignores the field; demanding it
        would only teach callers to type a value that changes nothing."""
        self.assertIsNone(self.spawn({"subagent_type": "fork", "prompt": "carry on"}))

    def test_permits_a_type_whose_definition_declares_a_model(self):
        self.define("shelf-plugin", "reader", "model: haiku\neffort: low")

        self.assertIsNone(self.spawn({"subagent_type": "shelf-plugin:reader", "prompt": "x"}))

    def test_inherit_is_a_declaration(self):
        """`inherit` names the session's model on purpose; the rule is against an
        omission, not against that choice."""
        self.define("shelf-plugin", "judge", "model: inherit\neffort: high")

        self.assertIsNone(self.spawn({"subagent_type": "shelf-plugin:judge", "prompt": "x"}))

    def test_denies_a_type_whose_definition_declares_no_model(self):
        self.define("shelf-plugin", "drifter", "effort: high")

        self.assertEqual(
            self.spawn({"subagent_type": "shelf-plugin:drifter", "prompt": "x"}), "deny"
        )

    def test_names_the_tiers_in_the_reason(self):
        payload = json.dumps({"tool_name": "Agent", "tool_input": {"prompt": "x"}})
        result = support.run_script(GUARD, stdin=payload, CLAUDE_CONFIG_DIR=str(self.home))
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]

        for tier in ("haiku", "sonnet", "fork"):
            self.assertIn(tier, reason)

    def test_states_the_routing_order_in_the_reason(self):
        """The reason is the one channel into a fan-out the plugin does not own,
        so it carries the order itself rather than pointing at the primer."""
        payload = json.dumps({"tool_name": "Agent", "tool_input": {"prompt": "x"}})
        result = support.run_script(GUARD, stdin=payload, CLAUDE_CONFIG_DIR=str(self.home))
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]

        self.assertLess(reason.index("top-tier"), reason.index("total tokens"))
        self.assertLess(reason.index("total tokens"), reason.index("wall-clock"))

    def test_passes_on_input_it_cannot_read(self):
        result = support.run_script(GUARD, stdin="not json")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class PluginAgentsTest(unittest.TestCase):
    """The plugin's own agents must satisfy the guard it ships."""

    def test_every_shipped_agent_declares_a_model(self):
        agents = support.plugin_root("dan-work-routing") / "agents"

        for path in sorted(agents.glob("*.md")):
            with self.subTest(agent=path.name):
                self.assertIn("model", support.frontmatter(path))


if __name__ == "__main__":
    unittest.main()
