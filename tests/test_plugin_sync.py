"""plugin-sync's drift survey, run against throwaway homes.

The survey infers retirement from absence, which makes one failure mode worth
more tests than the rest: a marketplace that cannot be read looks exactly like a
marketplace that retired everything in it. Every way a read can fail has a case
here, and each asserts silence rather than a proposal to uninstall.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import support

SCRIPT = support.script("plugin-sync", "plugin_sync.py")


class ThrowawayHome:
    """A ~/.claude a survey can be pointed at, assembled one declaration at a time."""

    def __init__(self, root):
        self.root = Path(root)
        self.claude = self.root / ".claude"
        self.plugins = self.claude / "plugins"
        self.plugins.mkdir(parents=True)

        self.marketplaces = {}
        self.installed = {}
        self.enabled = {}

    def offering(self, marketplace, names, dependencies=None):
        location = self.root / "marketplaces" / marketplace
        (location / ".claude-plugin").mkdir(parents=True)

        entries = [{"name": name} for name in names]

        for entry in entries:
            if dependencies and entry["name"] in dependencies:
                entry["dependencies"] = dependencies[entry["name"]]

        self.write(
            location / ".claude-plugin" / "marketplace.json",
            {"name": marketplace, "plugins": entries},
        )

        self.marketplaces[marketplace] = {"installLocation": str(location)}

        return self

    def unreadable_offering(self, marketplace, manifest=None):
        """A registered marketplace whose manifest is absent, corrupt, or empty."""
        location = self.root / "marketplaces" / marketplace
        (location / ".claude-plugin").mkdir(parents=True)

        if manifest is not None:
            (location / ".claude-plugin" / "marketplace.json").write_text(manifest)

        self.marketplaces[marketplace] = {"installLocation": str(location)}

        return self

    def install(self, identifier, scope="user", version="1.0.0"):
        self.installed[identifier] = [{"scope": scope, "version": version}]

        return self

    def enable(self, identifier):
        self.enabled[identifier] = True

        return self

    def survey(self):
        self.write(self.plugins / "known_marketplaces.json", self.marketplaces)
        self.write(
            self.plugins / "installed_plugins.json",
            {"version": 2, "plugins": self.installed},
        )
        self.write(self.claude / "settings.json", {"enabledPlugins": self.enabled})

        result = support.run_script(SCRIPT, ["--json"], HOME=str(self.root))

        return json.loads(result.stdout)

    def notes(self):
        self.write(self.plugins / "known_marketplaces.json", self.marketplaces)
        self.write(
            self.plugins / "installed_plugins.json",
            {"version": 2, "plugins": self.installed},
        )
        self.write(self.claude / "settings.json", {"enabledPlugins": self.enabled})

        result = support.run_script(SCRIPT, HOME=str(self.root))

        return result.stdout.strip()

    @staticmethod
    def write(path, payload):
        path.write_text(json.dumps(payload), encoding="utf-8")


class SurveyTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.home = ThrowawayHome(self.directory.name)


class HealthyInstallTest(SurveyTest):
    """What a survey must never do is act on a plugin that is working."""

    def test_a_fully_healthy_shelf_reports_nothing_at_all(self):
        survey = (
            self.home.offering("ffoxdd", ["dan-code-style", "dan-work-routing"])
            .install("dan-code-style@ffoxdd")
            .install("dan-work-routing@ffoxdd")
            .enable("dan-code-style@ffoxdd")
            .enable("dan-work-routing@ffoxdd")
            .survey()
        )

        self.assertEqual(survey["orphans"], [])
        self.assertEqual(survey["missing"], [])
        self.assertEqual(survey["duplicates"], [])
        self.assertEqual(survey["healthy"], 2)

    def test_a_healthy_shelf_says_nothing_at_session_start(self):
        notes = (
            self.home.offering("ffoxdd", ["dan-code-style"])
            .install("dan-code-style@ffoxdd")
            .enable("dan-code-style@ffoxdd")
            .notes()
        )

        self.assertEqual(notes, "")

    def test_a_plugin_from_an_unregistered_marketplace_is_left_alone(self):
        """No manifest to judge it against, so it is not judged."""
        survey = (
            self.home.offering("ffoxdd", ["dan-code-style"])
            .install("dan-code-style@ffoxdd")
            .install("figma@claude-plugins-official")
            .survey()
        )

        self.assertEqual(survey["orphans"], [])
        self.assertEqual(survey["unreadable"], ["claude-plugins-official"])

    def test_a_version_behind_is_not_drift(self):
        """Auto-update ships versions; this repairs breakage. An install whose
        marketplace still lists it is healthy whatever version either one holds."""
        survey = (
            self.home.offering("ffoxdd", ["dan-code-style"])
            .install("dan-code-style@ffoxdd")
            .survey()
        )

        self.assertEqual(survey["orphans"], [])
        self.assertEqual(survey["healthy"], 1)


class UnreadableMarketplaceTest(SurveyTest):
    """Absence means retirement only where the manifest was actually read.

    Each case registers a marketplace holding an install and then breaks the
    manifest a different way. Every one must produce zero orphans: the survey has
    no evidence of retirement, and a proposal to uninstall built on a failed read
    is the one mistake that costs someone their shelf.
    """

    def assert_no_orphans(self, survey):
        self.assertEqual(survey["orphans"], [])
        self.assertEqual(survey["unreadable"], ["ffoxdd"])

    def test_a_manifest_that_is_not_there(self):
        survey = (
            self.home.unreadable_offering("ffoxdd")
            .install("dan-code-style@ffoxdd")
            .survey()
        )

        self.assert_no_orphans(survey)

    def test_a_manifest_that_will_not_parse(self):
        survey = (
            self.home.unreadable_offering("ffoxdd", "{ this is not json")
            .install("dan-code-style@ffoxdd")
            .survey()
        )

        self.assert_no_orphans(survey)

    def test_a_manifest_that_parses_but_lists_nothing(self):
        """A half-written clone, and the shape a truncated fetch leaves behind."""
        survey = (
            self.home.unreadable_offering("ffoxdd", '{"name": "ffoxdd", "plugins": []}')
            .install("dan-code-style@ffoxdd")
            .survey()
        )

        self.assert_no_orphans(survey)

    def test_one_broken_marketplace_does_not_silence_a_readable_one(self):
        survey = (
            self.home.offering("aligned", ["dan-hex-practices"])
            .unreadable_offering("ffoxdd", "{ broken")
            .install("dan-code-style@ffoxdd")
            .install("retired-plugin@aligned")
            .survey()
        )

        self.assertEqual(
            [record["identifier"] for record in survey["orphans"]],
            ["retired-plugin@aligned"],
        )
        self.assertEqual(survey["unreadable"], ["ffoxdd"])


class OrphanTest(SurveyTest):
    def test_an_install_its_marketplace_no_longer_lists_is_an_orphan(self):
        survey = (
            self.home.offering("aligned", ["dan-phi-routing"])
            .install("aligned-phi-routing@aligned")
            .survey()
        )

        self.assertEqual(
            [record["identifier"] for record in survey["orphans"]],
            ["aligned-phi-routing@aligned"],
        )

    def test_an_orphan_carries_the_scope_its_removal_needs(self):
        survey = (
            self.home.offering("aligned", ["dan-phi-routing"])
            .install("aligned-phi-routing@aligned", scope="project")
            .survey()
        )

        self.assertEqual(survey["orphans"][0]["scope"], "project")

    def test_the_session_start_note_names_the_plugin_and_the_command(self):
        notes = (
            self.home.offering("aligned", ["dan-phi-routing"])
            .install("aligned-phi-routing@aligned")
            .notes()
        )

        message = json.loads(notes)["systemMessage"]

        self.assertIn("aligned-phi-routing@aligned", message)
        self.assertIn("/plugin-sync:sync", message)


class MissingTest(SurveyTest):
    def test_enabled_but_not_installed_is_installable(self):
        survey = (
            self.home.offering("ffoxdd", ["dan-code-style"])
            .enable("dan-code-style@ffoxdd")
            .survey()
        )

        self.assertEqual(survey["missing"][0]["identifier"], "dan-code-style@ffoxdd")
        self.assertTrue(survey["missing"][0]["installable"])

    def test_an_enabled_name_no_marketplace_offers_is_a_leftover_key(self):
        """What a rename leaves in settings once the install itself is gone."""
        survey = (
            self.home.offering("aligned", ["dan-phi-routing"])
            .enable("aligned-phi-routing@aligned")
            .survey()
        )

        self.assertFalse(survey["missing"][0]["installable"])

    def test_an_installed_plugin_is_never_reported_missing(self):
        survey = (
            self.home.offering("ffoxdd", ["dan-code-style"])
            .install("dan-code-style@ffoxdd")
            .enable("dan-code-style@ffoxdd")
            .survey()
        )

        self.assertEqual(survey["missing"], [])


class DuplicateTest(SurveyTest):
    def test_one_name_from_two_marketplaces_is_reported_once(self):
        survey = (
            self.home.offering("ffoxdd", ["dan-work-routing"])
            .offering("aligned", ["dan-work-routing"])
            .install("dan-work-routing@ffoxdd")
            .install("dan-work-routing@aligned")
            .survey()
        )

        self.assertEqual(
            survey["duplicates"],
            [
                {
                    "name": "dan-work-routing",
                    "installs": [
                        {"identifier": "dan-work-routing@aligned", "scope": "user"},
                        {"identifier": "dan-work-routing@ffoxdd", "scope": "user"},
                    ],
                }
            ],
        )

    def test_each_copy_carries_the_scope_its_removal_needs(self):
        """The repair uninstalls one copy, and the exact command needs its scope —
        the same reason an orphan carries one."""
        survey = (
            self.home.offering("ffoxdd", ["dan-work-routing"])
            .offering("aligned", ["dan-work-routing"])
            .install("dan-work-routing@ffoxdd", scope="user")
            .install("dan-work-routing@aligned", scope="project")
            .survey()
        )

        scopes = {
            install["identifier"]: install["scope"]
            for install in survey["duplicates"][0]["installs"]
        }

        self.assertEqual(scopes["dan-work-routing@aligned"], "project")
        self.assertEqual(scopes["dan-work-routing@ffoxdd"], "user")

    def test_both_copies_are_counted_out_of_healthy(self):
        survey = (
            self.home.offering("ffoxdd", ["dan-work-routing"])
            .offering("aligned", ["dan-work-routing"])
            .install("dan-work-routing@ffoxdd")
            .install("dan-work-routing@aligned")
            .survey()
        )

        self.assertEqual(survey["healthy"], 0)

    def test_neither_copy_is_an_orphan(self):
        """Both marketplaces list it, so the fault is the doubling, not either install."""
        survey = (
            self.home.offering("ffoxdd", ["dan-work-routing"])
            .offering("aligned", ["dan-work-routing"])
            .install("dan-work-routing@ffoxdd")
            .install("dan-work-routing@aligned")
            .survey()
        )

        self.assertEqual(survey["orphans"], [])


class UnsatisfiedDependencyTest(SurveyTest):
    """Installed, still listed, and not loading — because something else moved.

    Moving one plugin's pin is enough to cause this, and the plugin that stops
    loading is the dependent rather than the one that moved. Nothing about the
    dependent changed, so it reads as healthy everywhere except the listing.
    """

    def shelf(self, requirement, installed_version):
        return (
            self.home.offering(
                "aligned",
                ["dan-phi-routing", "dan-work-routing"],
                dependencies={
                    "dan-phi-routing": [
                        {"name": "dan-work-routing", "version": requirement}
                    ]
                },
            )
            .install("dan-phi-routing@aligned")
            .install("dan-work-routing@aligned", version=installed_version)
        )

    def test_a_dependency_below_the_declared_range_is_reported(self):
        survey = self.shelf("~1.5.0", "1.3.3").survey()

        self.assertEqual(
            survey["unsatisfied"],
            [
                {
                    "identifier": "dan-phi-routing@aligned",
                    "requires": "dan-work-routing",
                    "wanted": "~1.5.0",
                    "installed": "1.3.3",
                }
            ],
        )

    def test_an_unsatisfied_dependent_is_not_counted_healthy(self):
        survey = self.shelf("~1.5.0", "1.3.3").survey()

        self.assertEqual(survey["healthy"], 1)

    def test_a_satisfied_dependency_is_silent(self):
        survey = self.shelf("~1.5.0", "1.5.2").survey()

        self.assertEqual(survey["unsatisfied"], [])
        self.assertEqual(survey["healthy"], 2)

    def test_a_tilde_range_excludes_the_next_minor(self):
        survey = self.shelf("~1.5.0", "1.6.0").survey()

        self.assertEqual(len(survey["unsatisfied"]), 1)

    def test_a_caret_range_allows_the_next_minor(self):
        survey = self.shelf("^1.5.0", "1.6.0").survey()

        self.assertEqual(survey["unsatisfied"], [])

    def test_a_version_suffix_does_not_defeat_the_comparison(self):
        """`plugin update` stamps a resolved commit onto the version it installs."""
        survey = self.shelf("~1.5.0", "1.5.0-611ad90cbea7").survey()

        self.assertEqual(survey["unsatisfied"], [])

    def test_a_dependency_that_is_not_installed_at_all_is_reported(self):
        survey = (
            self.home.offering(
                "aligned",
                ["dan-phi-routing"],
                dependencies={
                    "dan-phi-routing": [
                        {"name": "dan-work-routing", "version": "~1.5.0"}
                    ]
                },
            )
            .install("dan-phi-routing@aligned")
            .survey()
        )

        self.assertIsNone(survey["unsatisfied"][0]["installed"])

    def test_a_range_the_survey_cannot_model_yields_no_finding(self):
        """Guessing here would name a working plugin broken, so an unmodelled
        range is treated the same as an unreadable marketplace."""
        for requirement in (">=1.5.0 <2", "^0.4.0", "latest"):
            with self.subTest(requirement=requirement):
                self.setUp()

                survey = self.shelf(requirement, "1.3.3").survey()

                self.assertEqual(survey["unsatisfied"], [])

    def test_the_note_names_the_dependency_rather_than_the_dependent(self):
        notes = self.shelf("~1.5.0", "1.3.3").notes()
        message = json.loads(notes)["systemMessage"]

        self.assertIn("dan-phi-routing@aligned requires dan-work-routing", message)
        self.assertIn("until dan-work-routing is updated", message)


class ResilienceTest(SurveyTest):
    """A drift check runs at session start, so it fails quietly or not at all."""

    def test_a_home_with_no_claude_state_at_all_is_silent(self):
        with TemporaryDirectory() as empty:
            result = support.run_script(SCRIPT, HOME=empty)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    def test_unparseable_settings_do_not_stop_the_survey(self):
        self.home.offering("aligned", ["dan-phi-routing"]).install(
            "aligned-phi-routing@aligned"
        )

        self.home.write(self.home.plugins / "known_marketplaces.json", self.home.marketplaces)
        self.home.write(
            self.home.plugins / "installed_plugins.json",
            {"version": 2, "plugins": self.home.installed},
        )
        (self.home.claude / "settings.json").write_text("{ not json")

        result = support.run_script(SCRIPT, ["--json"], HOME=str(self.home.root))
        survey = json.loads(result.stdout)

        self.assertEqual(
            [record["identifier"] for record in survey["orphans"]],
            ["aligned-phi-routing@aligned"],
        )


if __name__ == "__main__":
    unittest.main()
