"""The dan-command-style guard denies one shape and nothing else.

A preference plugin that enforces with a hook has to be precise about its
blast radius: over-matching turns a convention into an obstacle, and the user
cannot argue with a denial.
"""

import unittest

import support

GUARD = support.script("dan-command-style", "command_style_guard.py")


class DecisionTest(unittest.TestCase):
    def decision(self, command):
        return support.hook_decision(GUARD, command)

    def test_denies_cd_then_git(self):
        self.assertEqual(self.decision("cd ~/Developer/dotfiles && git status"), "deny")

    def test_denies_cd_then_git_through_a_semicolon(self):
        self.assertEqual(self.decision("cd /tmp; git log --oneline"), "deny")

    def test_names_the_replacement_in_the_reason(self):
        import json

        payload = json.dumps({"tool_input": {"command": "cd /tmp && git status"}})
        result = support.run_script(GUARD, stdin=payload)
        reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]

        self.assertIn("git -C", reason)

    def test_permits_the_replacement_form(self):
        self.assertIsNone(self.decision("git -C ~/Developer/dotfiles status"))

    def test_denies_cd_then_git_across_a_newline(self):
        """A bare newline joins two commands in one Bash string exactly as `&&`
        does, and `cd` persists across it, so this is the same defeat of the
        allowlist — the most natural way to write it by accident."""
        self.assertEqual(self.decision("cd ~/Developer/dotfiles\ngit status"), "deny")

    def test_permits_cd_with_a_command_other_than_git(self):
        self.assertIsNone(self.decision("cd /tmp && ls -la"))

    def test_permits_a_binary_whose_name_merely_starts_with_git(self):
        """`git-secrets` and `git-lfs` are their own programs, not `git`; denying
        them with advice to use `git -C` is both wrong and unactionable."""
        self.assertIsNone(self.decision("cd /tmp && git-secrets --scan"))
        self.assertIsNone(self.decision("cd /tmp && git-lfs install"))

    def test_permits_git_without_a_leading_cd(self):
        self.assertIsNone(self.decision("git status && echo done"))

    def test_malformed_input_makes_no_decision(self):
        result = support.run_script(GUARD, stdin="not json at all")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
