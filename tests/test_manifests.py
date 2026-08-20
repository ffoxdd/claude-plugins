"""The wiring tier: manifests parse, and everything they point at exists.

These are the cheapest assertions in the suite and they catch the most
embarrassing class of bug — one where nothing errors and the plugin simply does
nothing. A hook naming a script that moved, a context file renamed out from
under its injector, and a marketplace name the CLI rejects at `add` time all
present as silence.
"""

import json
import os
import re
import subprocess
import unittest

import support

PLUGIN_ROOT_REFERENCE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}(/[^\s\"']+)")

LAUNCHED_PATH = re.compile(r'\$\(dirname "\$0"\)([^"]*)"')


def executed_lines(path):
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


class MarketplaceTest(unittest.TestCase):
    def setUp(self):
        self.marketplace = support.read_json(support.MARKETPLACE_FILE)

    def test_name_does_not_impersonate_an_official_marketplace(self):
        # Claude Code refuses to register a marketplace whose name reads as an
        # official Anthropic one, and the refusal happens at `add` time — so the
        # repository is unusable rather than degraded. "claude-plugins" was
        # rejected on 2026-08-17 with "Marketplace name impersonates an official
        # Anthropic/Claude marketplace".
        self.assertNotIn("claude", self.marketplace["name"].lower())

    def test_lists_every_plugin_directory_exactly_once(self):
        listed = sorted(entry["name"] for entry in self.marketplace["plugins"])

        self.assertEqual(listed, support.plugin_names())

    def test_each_source_resolves_to_its_plugin(self):
        for entry in self.marketplace["plugins"]:
            with self.subTest(plugin=entry["name"]):
                source = (support.REPOSITORY_ROOT / entry["source"]).resolve()

                self.assertTrue(source.is_dir())
                self.assertEqual(source, support.plugin_root(entry["name"]).resolve())

    def test_each_entry_describes_itself(self):
        for entry in self.marketplace["plugins"]:
            with self.subTest(plugin=entry["name"]):
                self.assertTrue(entry.get("description", "").strip())

    def test_the_shelf_and_the_items_share_one_owner(self):
        """This marketplace is one person's preferences, so `owner` (the shelf)
        and each plugin's `author` (the item) are the same name — a plugin
        credited to anyone else belongs in their marketplace, not this one."""
        self.assertEqual(self.marketplace["owner"]["name"], "Dan Fox")

    def test_each_description_matches_the_plugin_it_lists(self):
        """Two surfaces show one plugin's description: `/plugin` renders the
        marketplace copy before install and the manifest copy after. They drift
        silently — a plugin whose pitch changes in one file goes on making the
        other pitch to everybody deciding whether to install it."""
        for entry in self.marketplace["plugins"]:
            with self.subTest(plugin=entry["name"]):
                manifest = support.read_json(
                    support.plugin_root(entry["name"]) / ".claude-plugin" / "plugin.json"
                )

                self.assertEqual(entry["description"], manifest["description"])


class PluginManifestTest(unittest.TestCase):
    def test_every_plugin_declares_a_matching_name_and_a_version(self):
        for plugin in support.plugin_names():
            with self.subTest(plugin=plugin):
                manifest = support.read_json(
                    support.plugin_root(plugin) / ".claude-plugin" / "plugin.json"
                )

                self.assertEqual(manifest["name"], plugin)
                self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
                self.assertTrue(manifest["description"].strip())


class NamingRuleTest(unittest.TestCase):
    """A bare name is a claim; a prefixed one is a signature.

    This repository holds two kinds of plugin. A **mechanism** encodes something
    true whether or not anyone likes it, and takes a bare name — which claims to
    be the organization's one way to do that thing. A **preference** is one
    person's taste, and takes that person's name as a prefix, so it can be added
    without anyone's approval and two people can each keep a code style without
    either becoming the default.

    The claim has to be checked here rather than at review time, because the
    failure is not an error: a preference that quietly takes a bare name reads as
    house policy to every person who installs it, and nothing anywhere says
    otherwise. `plugin.json` carries both halves — `keywords` declares the kind,
    `author` supplies the prefix — so the name can be checked against them.
    """

    KINDS = ("mechanism", "preference")

    def manifests(self):
        for plugin in support.plugin_names():
            yield plugin, support.read_json(
                support.plugin_root(plugin) / ".claude-plugin" / "plugin.json"
            )

    def test_every_plugin_names_a_person_as_its_author(self):
        """An unattributed plugin is the one thing this arrangement cannot carry:
        with nobody named, a reader has only the marketplace's own name to go on
        and reasonably reads the plugin as the organization's."""
        for plugin, manifest in self.manifests():
            with self.subTest(plugin=plugin):
                self.assertTrue(manifest.get("author", {}).get("name", "").strip())

    def test_every_plugin_declares_exactly_one_kind(self):
        for plugin, manifest in self.manifests():
            with self.subTest(plugin=plugin):
                declared = [
                    keyword
                    for keyword in manifest.get("keywords", [])
                    if keyword in self.KINDS
                ]

                self.assertEqual(
                    len(declared),
                    1,
                    f"{plugin} must carry exactly one of {self.KINDS} in keywords",
                )

    def test_a_preference_is_prefixed_with_its_author_and_a_mechanism_is_not(self):
        """The prefix is the first word of `author.name`, lowercased — so the rule
        needs no roster of contributors to check against, and the next person's
        plugin is validated the same way without anyone editing this file.

        Two contributors sharing a first name is the case this cannot resolve:
        pick something unambiguous and use it in both fields."""
        for plugin, manifest in self.manifests():
            keywords = manifest.get("keywords", [])
            author = manifest.get("author", {}).get("name", "")

            if not author or not any(kind in keywords for kind in self.KINDS):
                continue  # Reported by the two tests above.

            prefix = author.split()[0].lower()

            with self.subTest(plugin=plugin, author=author):
                if "preference" in keywords:
                    self.assertTrue(
                        plugin.startswith(f"{prefix}-"),
                        f"{plugin} is a preference, so it must be named "
                        f"{prefix}-{plugin} — a bare name claims to be the "
                        f"organization's one way to do this",
                    )
                else:
                    self.assertFalse(
                        plugin.startswith(f"{prefix}-"),
                        f"{plugin} is a mechanism, so the {prefix}- prefix "
                        f"understates it — either drop the prefix or declare it "
                        f"a preference",
                    )


class VersionPropagationTest(unittest.TestCase):
    """A plugin's `version` is what carries a change to anyone who installed it.

    Installed copies are compared by that string rather than by commit, so a
    commit that edits a plugin without bumping it reaches the marketplace clone
    and stops there: `plugin update` answers "already at the latest version",
    auto-update does the same nothing, and the repository disagrees with every
    install with no error raised anywhere. That happened twice — 480cc59 shipped
    a README per plugin and 7db4df0 rewrote the knowledge-base workflow docs,
    neither reaching an install — because the rule lived only in prose.

    So: the last commit touching a plugin's files must be the bump commit itself
    or older than it. History is the subject, not the working tree, which is what
    makes this quiet while a change is in progress and loud the moment one is
    committed without its bump.
    """

    def setUp(self):
        if self.git("rev-parse", "--git-dir").returncode != 0:
            self.skipTest("not a git checkout — nothing to compare against")

    def git(self, *arguments):
        return subprocess.run(
            ("git", "-C", str(support.REPOSITORY_ROOT)) + arguments,
            capture_output=True,
            text=True,
        )

    def last_commit_touching(self, *pathspecs):
        result = self.git("log", "-1", "--format=%H", "--", *pathspecs)

        return result.stdout.strip()

    def test_every_plugin_edit_was_committed_with_its_version_bump(self):
        for plugin in support.plugin_names():
            with self.subTest(plugin=plugin):
                manifest = f"plugins/{plugin}/.claude-plugin/plugin.json"
                content = self.last_commit_touching(
                    f"plugins/{plugin}", f":(exclude){manifest}"
                )
                bump = self.last_commit_touching(manifest)

                if not content:
                    continue  # Nothing of this plugin is committed yet.

                self.assertTrue(
                    bump,
                    f"{plugin} has committed files but no committed manifest",
                )
                self.assertEqual(
                    0,
                    self.git("merge-base", "--is-ancestor", content, bump).returncode,
                    f"{plugin} was last edited in {content[:7]}, which is newer than "
                    f"its last version bump {bump[:7]} — bump the version in "
                    f"{manifest} so the change reaches installed copies",
                )


class DocumentationTest(unittest.TestCase):
    """Each plugin documents itself, next to itself.

    The root README teaches what a plugin is and indexes what is here; the depth
    lives with the plugin, which is what every official Claude Code plugin does
    too. A plugin with no README is one whose only description is a single
    manifest line.
    """

    def test_every_plugin_has_its_own_readme(self):
        for plugin in support.plugin_names():
            with self.subTest(plugin=plugin):
                readme = support.plugin_root(plugin) / "README.md"

                self.assertTrue(readme.is_file(), f"{plugin} has no README.md")
                self.assertTrue(readme.read_text().startswith(f"# {plugin}"))

    def test_the_root_readme_links_every_plugin(self):
        """An index that silently omits a plugin is how one ends up undiscoverable:
        installed by nobody, because no instruction anywhere names it."""
        text = support.REPOSITORY_ROOT.joinpath("README.md").read_text()

        for plugin in support.plugin_names():
            with self.subTest(plugin=plugin):
                self.assertIn(f"plugins/{plugin}/README.md", text)
                self.assertIn(f"/plugin install {plugin}", text)


class HookWiringTest(unittest.TestCase):
    def hooks_files(self):
        for plugin in support.plugin_names():
            path = support.plugin_root(plugin) / "hooks" / "hooks.json"

            if path.exists():
                yield plugin, path

    def test_every_hooks_file_parses(self):
        for plugin, path in self.hooks_files():
            with self.subTest(plugin=plugin):
                self.assertIn("hooks", support.read_json(path))

    def test_every_referenced_path_exists_inside_its_plugin(self):
        """A hook command names its files through ${CLAUDE_PLUGIN_ROOT}, which the
        version-stamped install directory makes mandatory. Nothing checks those
        paths at load time: a hook pointing at a moved file simply never fires."""
        for plugin, path in self.hooks_files():
            for command in self.commands(support.read_json(path)):
                for reference in PLUGIN_ROOT_REFERENCE.findall(command):
                    with self.subTest(plugin=plugin, reference=reference):
                        self.assertTrue(
                            (support.plugin_root(plugin) / reference.lstrip("/")).exists()
                        )

    def test_no_command_names_a_path_outside_the_plugin(self):
        for plugin, path in self.hooks_files():
            for command in self.commands(support.read_json(path)):
                with self.subTest(plugin=plugin, command=command):
                    self.assertNotIn("~/", command)
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)

    def commands(self, hooks_file):
        for matchers in hooks_file["hooks"].values():
            for matcher in matchers:
                for hook in matcher["hooks"]:
                    yield hook["command"]


class InjectorTest(unittest.TestCase):
    """The injector is copied into each plugin, so the copies must not drift.

    It also has one contract worth pinning: SessionStart honours
    additionalContext only nested under hookSpecificOutput. Emitting it at the
    top level routes the text to the debug log instead, which is how every
    context file in this repository silently failed to load before 2026-08-17.
    """

    def injectors(self):
        return [
            support.script(plugin, "inject_context.py")
            for plugin in support.plugin_names()
            if support.script(plugin, "inject_context.py").exists()
        ]

    def test_every_copy_is_identical(self):
        """Names the copies that drifted, since "2 != 1" does not say which file
        to fix — and fixing it means copying one over the others by hand."""
        canonical = support.script("dan-work-routing", "inject_context.py")
        expected = canonical.read_text()

        for path in self.injectors():
            with self.subTest(copy=str(path)):
                self.assertEqual(path.read_text(), expected)

    def test_emits_the_shape_session_start_honours(self):
        injector = support.script("dan-work-routing", "inject_context.py")
        context_file = support.plugin_root("dan-work-routing") / "context" / "primer.md"

        result = support.run_script(injector, arguments=[context_file])
        payload = json.loads(result.stdout)["hookSpecificOutput"]

        self.assertEqual(payload["hookEventName"], "SessionStart")
        self.assertEqual(payload["additionalContext"], context_file.read_text())

    def test_a_missing_context_file_is_silent_rather_than_fatal(self):
        injector = support.script("dan-work-routing", "inject_context.py")

        result = support.run_script(injector, arguments=["/nonexistent/context.md"])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class ComponentFrontmatterTest(unittest.TestCase):
    def test_every_agent_declares_a_name_and_a_description(self):
        for plugin in support.plugin_names():
            for path in sorted((support.plugin_root(plugin) / "agents").glob("*.md")):
                with self.subTest(agent=path.name):
                    fields = support.frontmatter(path)

                    self.assertEqual(fields.get("name"), path.stem)
                    self.assertTrue(fields.get("description", "").strip())

    def test_every_command_declares_a_description(self):
        for plugin in support.plugin_names():
            for path in sorted((support.plugin_root(plugin) / "commands").glob("*.md")):
                with self.subTest(command=path.name):
                    self.assertTrue(support.frontmatter(path).get("description", "").strip())

    def test_every_skill_declares_a_matching_name_and_a_description(self):
        """A skill is selected by its description alone — that text is all Claude sees
        before deciding whether to load the body. A skill missing one is inert, and
        a name disagreeing with its directory is unaddressable."""
        for plugin in support.plugin_names():
            for path in sorted((support.plugin_root(plugin) / "skills").glob("*/SKILL.md")):
                with self.subTest(skill=f"{plugin}/{path.parent.name}"):
                    fields = support.frontmatter(path)

                    self.assertEqual(fields.get("name"), path.parent.name)
                    self.assertTrue(fields.get("description", "").strip())

    def test_every_reference_a_skill_names_exists(self):
        """A skill pointing at a moved reference degrades silently: the body loads,
        the pointer dangles, and the guidance it promised never arrives."""
        for plugin in support.plugin_names():
            for path in sorted((support.plugin_root(plugin) / "skills").glob("*/SKILL.md")):
                for reference in re.findall(r"`(references/[\w./-]+\.md)`", path.read_text()):
                    with self.subTest(skill=path.parent.name, reference=reference):
                        self.assertTrue((path.parent / reference).exists())

    def test_every_reference_file_is_named_by_its_skill(self):
        """The inverse direction: a reference file nothing points at is never loaded,
        so it is dead weight that reads as documentation."""
        for plugin in support.plugin_names():
            for path in sorted((support.plugin_root(plugin) / "skills").glob("*/SKILL.md")):
                named = set(re.findall(r"`(references/[\w./-]+\.md)`", path.read_text()))

                for reference in sorted((path.parent / "references").glob("*.md")):
                    relative = f"references/{reference.name}"

                    with self.subTest(skill=path.parent.name, reference=relative):
                        self.assertIn(relative, named)

    def test_every_script_a_skill_tells_you_to_run_exists(self):
        """A skill naming a moved script fails at the point of use, in a sync, with
        a shell error rather than anything that identifies the plugin as the cause."""
        for plugin in support.plugin_names():
            for path in sorted((support.plugin_root(plugin) / "skills").glob("*/SKILL.md")):
                body = path.read_text()

                for script in re.findall(r"<SKILL_DIR>/(scripts/[\w.-]+)", body):
                    with self.subTest(skill=path.parent.name, script=script):
                        self.assertTrue((path.parent / script).exists())


class LauncherTest(unittest.TestCase):
    """bin/ is a plugin's PATH surface.

    Claude Code adds every installed plugin's bin/ directory to PATH, so each file
    there is a command name the plugin claims on the machine — and each fails the
    same silent way. A file without the executable bit is simply not a command; a
    launcher naming a script that has since moved reports `No such file` at the one
    moment someone needed it, which for the covered runner is mid-analysis.
    """

    def launchers(self):
        for plugin in support.plugin_names():
            directory = support.plugin_root(plugin) / "bin"

            if not directory.is_dir():
                continue

            for launcher in sorted(directory.iterdir()):
                yield plugin, launcher

    def test_every_launcher_is_executable(self):
        for plugin, launcher in self.launchers():
            with self.subTest(plugin=plugin, launcher=launcher.name):
                self.assertTrue(os.access(launcher, os.X_OK))

    def test_every_launcher_names_a_file_that_exists(self):
        for plugin, launcher in self.launchers():
            suffixes = LAUNCHED_PATH.findall(launcher.read_text())

            with self.subTest(plugin=plugin, launcher=launcher.name):
                self.assertTrue(suffixes, "names no script to run")

                for suffix in suffixes:
                    self.assertTrue((launcher.parent / suffix.lstrip("/")).exists())

    def test_no_launcher_reaches_outside_its_plugin(self):
        """A relative path from bin/ is what survives the version-stamped install
        directory; an absolute one is a developer machine's path shipped to everyone.

        Read from the executed lines rather than the whole file, since a comment
        explaining that nothing lands in ~/.local/bin is not a path being used."""
        for plugin, launcher in self.launchers():
            with self.subTest(plugin=plugin, launcher=launcher.name):
                self.assertNotIn("~/", executed_lines(launcher))

                for suffix in LAUNCHED_PATH.findall(launcher.read_text()):
                    resolved = (launcher.parent / suffix.lstrip("/")).resolve()

                    self.assertTrue(
                        resolved.is_relative_to(support.plugin_root(plugin).resolve())
                    )


if __name__ == "__main__":
    unittest.main()
