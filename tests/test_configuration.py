"""Loading the local vocabulary, and the config-file override offered at
enable time.

The failure mode to guard against is a config that loads but is subtly wrong —
or one whose absence quietly widens what a guard permits.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

SCRIPTS_DIRECTORY = support.plugin_root("dan-work-routing") / "scripts"


def configuration_section(section, **environment_overrides):
    driver = (
        "import json, sys;"
        f"sys.path.insert(0, {str(SCRIPTS_DIRECTORY)!r});"
        "import configuration;"
        f"print(json.dumps(configuration.section({section!r})))"
    )

    result = subprocess.run(
        [sys.executable, "-c", driver],
        capture_output=True,
        text=True,
        env=support.environment(**environment_overrides),
    )

    return json.loads(result.stdout)


def write_configuration(payload):
    directory = tempfile.mkdtemp(prefix="configuration-test")
    path = Path(directory) / "organization.json"
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))

    return str(path)


class DefaultConfigurationTest(unittest.TestCase):
    def test_names_the_variable_that_supplies_the_covered_key(self):
        covered_endpoint = configuration_section("covered_endpoint")

        self.assertTrue(covered_endpoint["credential_variable"])

    def test_runs_no_resolver_and_names_no_secrets_manager(self):
        """The variable is the whole contract: populating it belongs to the
        user's own shell, so the config must carry nothing executable."""
        covered_endpoint = configuration_section("covered_endpoint")

        self.assertEqual(list(covered_endpoint), ["credential_variable"])

    def test_declares_the_warehouse_commands_the_analyst_uses(self):
        self.assertTrue(configuration_section("warehouse")["query_commands"])


class ConfigurationFileOverrideTest(unittest.TestCase):
    def test_swaps_the_whole_file(self):
        configuration = write_configuration(
            {"organization": {"internal_email_domains": ["example.test"]}}
        )

        self.assertEqual(
            configuration_section(
                "organization", CLAUDE_PLUGIN_OPTION_CONFIG_FILE=configuration
            ),
            {"internal_email_domains": ["example.test"]},
        )

    def test_a_missing_file_yields_no_vocabulary_rather_than_an_error(self):
        self.assertEqual(
            configuration_section(
                "organization", CLAUDE_PLUGIN_OPTION_CONFIG_FILE="/nonexistent/config.json"
            ),
            {},
        )

    def test_a_malformed_file_yields_no_vocabulary_rather_than_an_error(self):
        configuration = write_configuration("{ not json")

        self.assertEqual(
            configuration_section(
                "organization", CLAUDE_PLUGIN_OPTION_CONFIG_FILE=configuration
            ),
            {},
        )


if __name__ == "__main__":
    unittest.main()
