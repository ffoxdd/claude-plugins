"""The dan-knowledge-base plugin: register discovery, register-driven provisioning, scaffolding.

Three properties here are worth more than the rest, because each one fails
silently in production:

  * A register that will not parse must be loud. A sync that reads no sources
    does nothing, successfully, and reports having swept everything it knew of.
  * Provisioning must say nothing outside a knowledge base, and nothing about a
    source the register does not declare. A plugin that nags about tools you
    never asked for gets disabled, which costs you the checks you did want.
  * The launcher on PATH must name `uv run --script` for the bundled Slack
    client. Anything else resolves cleanly and dies at `import playwright` — a
    correct-looking command with a broken interpreter, and the failure reads as
    a missing dependency rather than a wrong launcher.
"""

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support

PLUGIN = "dan-knowledge-base"


def register(**sources):
    return {"layout": {"notes": "notes"}, "sources": sources}


def write_register(directory, document):
    path = Path(directory) / ".knowledge-base.json"
    path.write_text(json.dumps(document))

    return path


def launched_path(launcher):
    """The file a bin/ launcher execs, resolved against the launcher's own directory."""
    suffix = re.search(r'\$\(dirname "\$0"\)([^"]*)"', launcher.read_text(encoding="utf-8")).group(1)

    return (launcher.parent / suffix.lstrip("/")).resolve()


def in_module(function_call):
    """Evaluates one expression against the plugin's scripts, in a subprocess.

    The suite runs scripts as subprocesses because argv/stdin/env/exit status is
    the contract Claude Code uses. Config discovery is not part of that contract —
    it is a pure function over a directory tree — so it is exercised directly.
    """
    directory = support.plugin_root(PLUGIN) / "scripts"
    program = (
        f"import sys; sys.path.insert(0, {str(directory)!r});"
        f"import provision, configuration, pathlib; print({function_call})"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )

    return result.stdout.strip()


class RegisterDiscoveryTest(unittest.TestCase):
    def test_finds_the_register_from_a_nested_directory(self):
        """A sync run from notes/engineering/ is the normal case, not the edge one."""
        with tempfile.TemporaryDirectory() as directory:
            write_register(directory, register(inbox={"adapter": None}))
            nested = Path(directory) / "notes" / "engineering"
            nested.mkdir(parents=True)

            found = in_module(f"configuration.find({str(nested)!r})")

            self.assertEqual(Path(found).parent, Path(directory).resolve())

    def test_the_root_is_the_registers_own_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            write_register(directory, register(inbox={"adapter": None}))

            root = in_module(f"configuration.load({str(directory)!r})[1]")

            self.assertEqual(Path(root), Path(directory).resolve())

    def test_no_register_anywhere_is_reported_not_guessed(self):
        result = self.load_expecting_failure(Path(tempfile.gettempdir()) / "definitely-absent")

        self.assertIn(".knowledge-base.json", result)
        self.assertIn("/dan-knowledge-base:init", result)

    def test_malformed_json_names_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            # Resolved, because Windows hands out a temporary directory by its 8.3
            # alias (C:\Users\RUNNER~1\…) while the loader reports the long name it
            # resolves to — the same path, spelled two ways, and the assertion is
            # about which file was named rather than how it was spelled.
            path = Path(directory).resolve() / ".knowledge-base.json"
            path.write_text("{not json")

            result = self.load_expecting_failure(directory)

            self.assertIn(str(path), result)
            self.assertIn("not valid JSON", result)

    def test_a_register_declaring_no_sources_object_is_refused(self):
        """Distinguishes "declares nothing yet" from "forgot the key". The first is
        a legitimate fresh knowledge base; the second would sweep nothing quietly."""
        with tempfile.TemporaryDirectory() as directory:
            write_register(directory, {"layout": {}})

            self.assertIn("no \"sources\"", self.load_expecting_failure(directory))

    def test_an_empty_sources_object_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            write_register(directory, register())

            self.assertEqual(in_module(f"configuration.sources({str(directory)!r})"), "{}")

    def load_expecting_failure(self, start):
        directory = support.plugin_root(PLUGIN) / "scripts"
        program = (
            f"import sys; sys.path.insert(0, {str(directory)!r});"
            "import configuration\n"
            f"try: configuration.load({str(start)!r})\n"
            "except configuration.ConfigurationError as error: print(error)\n"
            "else: print('NO ERROR RAISED')"
        )
        result = subprocess.run(
            [sys.executable, "-c", program], capture_output=True, text=True, check=True
        )

        return result.stdout.strip()


class ConfiguredPathTest(unittest.TestCase):
    """Every path in the register names something inside the knowledge base. A value
    that escapes would write intake outside the gitignored tree, which is the one
    outcome this plugin exists to prevent."""

    def test_a_relative_path_resolves_against_the_root(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = in_module(
                f"configuration.path_within({str(directory)!r}, 'notes/.sync-state')"
            )

            self.assertEqual(Path(resolved), Path(directory).resolve() / "notes" / ".sync-state")

    def test_a_path_escaping_the_knowledge_base_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            program = (
                f"import sys; sys.path.insert(0, {str(support.plugin_root(PLUGIN) / 'scripts')!r});"
                "import configuration\n"
                f"try: configuration.path_within({str(directory)!r}, '../outside')\n"
                "except configuration.ConfigurationError as error: print('refused')\n"
                "else: print('ALLOWED')"
            )
            result = subprocess.run(
                [sys.executable, "-c", program], capture_output=True, text=True, check=True
            )

            self.assertEqual(result.stdout.strip(), "refused")


class ProvisioningSilenceTest(unittest.TestCase):
    """What this plugin says when it has nothing to say."""

    def provision(self, config_file=None, cwd=None, home=None):
        return support.run_script(
            support.script(PLUGIN, "provision.py"),
            cwd=cwd,
            KNOWLEDGE_BASE_CONFIG_FILE=str(config_file) if config_file else None,
            HOME=str(home) if home else None,
        )

    def test_says_nothing_outside_a_knowledge_base(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.provision(cwd=directory)

            self.assertEqual(result.stdout.strip(), "")
            self.assertEqual(result.returncode, 0)

    def test_says_nothing_when_every_source_is_queried_directly(self):
        """adapter null needs nothing installed, so there is nothing to check."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(
                wiki={"adapter": None}, tasks={"adapter": None}
            ))

            self.assertEqual(self.provision(path, home=directory).stdout.strip(), "")

    def test_ignores_an_adapter_it_does_not_ship(self):
        """An unknown adapter name is the repo's own script, named in its register.
        It is not this plugin's business and must not become a complaint."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(custom={"adapter": "in-house-fetcher"}))

            self.assertEqual(self.provision(path, home=directory).stdout.strip(), "")

    def test_a_declared_adapter_reports_its_unmet_prerequisites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(chat={"adapter": "chat"}))

            output = self.provision(path, home=directory).stdout
            body = json.loads(output)["hookSpecificOutput"]["additionalContext"]

            self.assertIn("slack-client login", body)
            self.assertIn("/dan-knowledge-base:setup", body)

    def test_names_the_adapter_that_stops_working(self):
        """A note saying a tool is missing without saying which source it breaks
        leaves the reader to infer the consequence."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(chat={"adapter": "chat"}))

            body = json.loads(self.provision(path, home=directory).stdout)
            body = body["hookSpecificOutput"]["additionalContext"]

            self.assertIn("chat", body)

    def test_a_directly_queried_source_reports_a_command_it_declares_and_lacks(self):
        """`requires` is the only thing standing between an absent tool and a sync
        that reports having swept a source it could not reach."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(
                board={"adapter": None, "requires": {"commands": ["definitely-not-installed"]}}
            ))

            body = json.loads(self.provision(path, home=directory).stdout)
            body = body["hookSpecificOutput"]["additionalContext"]

            self.assertIn("definitely-not-installed", body)
            self.assertIn("board", body)

    def test_a_declared_command_that_resolves_is_not_mentioned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(
                board={"adapter": None, "requires": {"commands": ["sh"]}}
            ))

            self.assertEqual(self.provision(path, home=directory).stdout.strip(), "")

    def test_a_declared_mcp_server_is_left_to_setup(self):
        """Whether a server is reachable is a property of the session, which a hook
        in a subprocess cannot see. Reporting it here would nag about servers that
        are working."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(
                board={"adapter": None, "requires": {"mcp": ["notion"]}}
            ))

            self.assertEqual(self.provision(path, home=directory).stdout.strip(), "")

    def test_a_broken_register_is_reported_when_it_is_the_named_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".knowledge-base.json"
            path.write_text("{broken")

            body = json.loads(self.provision(path, home=directory).stdout)

            self.assertIn("not valid JSON", body["hookSpecificOutput"]["additionalContext"])

    def test_never_exits_nonzero(self):
        """A provisioner that fails a session start is worse than one that fails to
        provision."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".knowledge-base.json"
            path.write_text("{broken")

            self.assertEqual(self.provision(path, home=directory).returncode, 0)


class RetentionTest(unittest.TestCase):
    """The processed-intake retention: what it deletes, what it never touches, and
    the conditions under which it deletes nothing at all."""

    OLD = 40 * 24 * 60 * 60

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.processed = self.root / "inbox" / "processed"
        self.processed.mkdir(parents=True)
        self.layout = {"inbox": "inbox", "processed": "inbox/processed", "retention_days": 30}
        self.write_layout()

    def tearDown(self):
        self.directory.cleanup()

    def write_layout(self, **changes):
        self.config = write_register(self.root, {"layout": {**self.layout, **changes},
                                                 "sources": {}})

    def work_tree(self, ignored="inbox/\n"):
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)
        (self.root / ".gitignore").write_text(ignored, encoding="utf-8")

    def intake_file(self, relative, age=0):
        path = self.processed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("intake", encoding="utf-8")
        moment = datetime.now().timestamp() - age
        os.utime(path, (moment, moment))

        return path

    def enforce(self, **environment):
        return support.run_script(support.script(PLUGIN, "retention.py"),
                                  KNOWLEDGE_BASE_CONFIG_FILE=str(self.config), **environment)

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_deletes_old_files_and_the_folders_they_leave_empty(self):
        self.work_tree()
        old = self.intake_file("2026/OLD-NAME-MARKER.md", age=self.OLD)
        recent = self.intake_file("RECENT-NAME-MARKER.md")

        result = self.enforce()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.splitlines(), [
            "knowledge-base retention: 1 processed intake file(s) older than 30 day(s) deleted"])
        self.assertFalse(old.exists())
        self.assertFalse(old.parent.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(self.processed.is_dir())

    def test_without_the_key_does_nothing(self):
        self.layout.pop("retention_days")
        self.write_layout()
        old = self.intake_file("old.md", age=self.OLD)

        result = self.enforce()

        self.assertEqual(result.stdout, "")
        self.assertTrue(old.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_processed_directory_git_does_not_ignore_is_refused(self):
        self.work_tree(ignored="")
        old = self.intake_file("old.md", age=self.OLD)

        result = self.enforce()

        self.assertIn("nothing deleted", result.stdout)
        self.assertIn("not git-ignored", result.stdout)
        self.assertTrue(old.exists())

    def test_a_processed_directory_outside_the_intake_is_refused(self):
        self.write_layout(processed="notes")
        notes = self.root / "notes"
        notes.mkdir()
        old = notes / "old.md"
        old.write_text("a note", encoding="utf-8")
        os.utime(old, (0, 0))

        result = self.enforce()

        self.assertIn("not inside the intake directory", result.stdout)
        self.assertTrue(old.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_processed_directory_reached_through_a_link_is_refused(self):
        self.work_tree()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        old = elsewhere / "old.md"
        old.write_text("kept", encoding="utf-8")
        os.utime(old, (0, 0))
        shutil.rmtree(self.processed)

        try:
            self.processed.symlink_to(elsewhere, target_is_directory=True)

        except OSError:
            self.skipTest("this platform cannot create a symbolic link here")

        result = self.enforce()

        self.assertIn("reached through a link", result.stdout)
        self.assertTrue(old.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_link_inside_is_neither_followed_nor_deleted(self):
        self.work_tree()
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "old.md"
        target.write_text("kept", encoding="utf-8")
        os.utime(target, (0, 0))

        try:
            (self.processed / "file-link.md").symlink_to(target)
            (self.processed / "folder-link").symlink_to(outside, target_is_directory=True)

        except OSError:
            self.skipTest("this platform cannot create a symbolic link here")

        result = self.enforce()

        self.assertIn(" 0 processed intake file(s)", result.stdout)
        self.assertTrue(target.exists())
        self.assertTrue((self.processed / "file-link.md").is_symlink())
        self.assertTrue((self.processed / "folder-link").is_symlink())

    def in_process(self):
        sys.path.insert(0, str(support.plugin_root(PLUGIN) / "scripts"))
        import retention

        return retention

    def faking_reparse_point(self, retention, faked):
        """os.lstat, with the reparse-point attribute Windows gives a junction
        added for the one path `faked`."""
        from types import SimpleNamespace
        from unittest import mock

        real = os.lstat

        def lstat(path, *arguments, **options):
            status = real(path, *arguments, **options)

            if os.path.normpath(str(path)) != os.path.normpath(str(faked)):
                return status

            return SimpleNamespace(st_mode=status.st_mode, st_mtime=status.st_mtime,
                                   st_file_attributes=retention.REPARSE_POINT)

        return mock.patch.object(retention.os, "lstat", lstat)

    def test_a_junction_inside_is_neither_descended_nor_deleted(self):
        retention = self.in_process()
        junction = self.processed / "junction"
        old = junction / "old.md"
        junction.mkdir()
        old.write_text("at the junction's target", encoding="utf-8")
        os.utime(old, (0, 0))

        with self.faking_reparse_point(retention, junction):
            deleted = retention.delete_expired(str(self.processed), datetime.now().timestamp())

        self.assertEqual(deleted, 0)
        self.assertTrue(old.exists())

    def test_a_processed_directory_that_is_a_junction_is_refused(self):
        retention = self.in_process()

        with self.faking_reparse_point(retention, self.processed):
            with self.assertRaises(retention.Refused):
                retention.processed_directory(self.layout, self.root)

    def test_outside_any_work_tree_nothing_is_deleted_or_said(self):
        """git cannot judge the place, which an adapter accepts; retention still
        deletes nothing it cannot confirm is ignored, and stays quiet about it."""
        old = self.intake_file("old.md", age=self.OLD)

        result = self.enforce(GIT_CEILING_DIRECTORIES=str(self.root.parent))

        self.assertEqual(result.stdout, "")
        self.assertTrue(old.exists())

    def test_session_start_reports_a_layout_that_is_not_an_object(self):
        self.config = write_register(self.root, {"layout": [], "sources": {}})

        result = support.run_script(support.script(PLUGIN, "provision.py"),
                                    KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
                                    HOME=str(self.root))
        body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        self.assertEqual(result.returncode, 0)
        self.assertIn('"layout" that is not an object', body)

    def test_a_retention_that_is_not_a_positive_number_is_refused(self):
        self.write_layout(retention_days="ninety")
        old = self.intake_file("old.md", age=self.OLD)

        result = self.enforce()

        self.assertIn("retention_days", result.stdout)
        self.assertTrue(old.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_session_start_reports_a_deletion_in_one_line(self):
        self.work_tree()
        self.intake_file("old.md", age=self.OLD)

        result = support.run_script(support.script(PLUGIN, "provision.py"),
                                    KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
                                    HOME=str(self.root))
        body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        self.assertIn("1 processed intake file(s) older than 30 day(s) deleted", body)
        self.assertNotIn("old.md", body)
        self.assertEqual(list(self.processed.iterdir()), [])

    def provision_requiring_session(self, **environment):
        self.config = write_register(self.root, {
            "layout": self.layout, "sources": {},
            "session": {"required_variable": SESSION_VARIABLE}})

        return support.run_script(support.script(PLUGIN, "provision.py"),
                                  KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
                                  HOME=str(self.root), **environment)

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_session_start_says_a_sync_cannot_run_outside_the_required_session(self):
        self.work_tree()
        old = self.intake_file("old.md", age=self.OLD)

        result = self.provision_requiring_session()
        body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

        self.assertIn("a sync cannot run in this session", body)
        self.assertIn(SESSION_VARIABLE, body)
        self.assertIn("1 processed intake file(s)", body)
        self.assertFalse(old.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_session_start_says_nothing_inside_the_required_session(self):
        self.work_tree()

        result = self.provision_requiring_session(**{SESSION_VARIABLE: "1"})

        self.assertEqual(result.stdout.strip(), "")

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_session_start_says_nothing_when_nothing_was_deleted(self):
        self.work_tree()
        self.intake_file("recent.md")

        result = support.run_script(support.script(PLUGIN, "provision.py"),
                                    KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
                                    HOME=str(self.root))

        self.assertEqual(result.stdout.strip(), "")


class LauncherTest(unittest.TestCase):
    """The command this plugin puts on PATH.

    Claude Code adds every installed plugin's bin/ to PATH, so shipping this file
    is the whole of provisioning: nothing is written into anyone's home directory
    and nothing needs re-pointing when the version-stamped root changes.
    """

    LAUNCHER = support.plugin_root(PLUGIN) / "bin" / "slack-client"

    def test_it_runs_the_client_under_uv_rather_than_trusting_its_shebang(self):
        """The script's own `#!/usr/bin/env -S uv run --script` needs a GNU `-S`,
        which Git Bash on Windows is not worth betting the chat adapter on."""
        self.assertIn("exec uv run --script", self.LAUNCHER.read_text(encoding="utf-8"))
        self.assertNotIn("exec python3", self.LAUNCHER.read_text(encoding="utf-8"))

    def test_it_launches_the_script_this_plugin_ships(self):
        target = launched_path(self.LAUNCHER)

        self.assertEqual(target, support.script(PLUGIN, "slack-client").resolve())


class BundledSlackClientTest(unittest.TestCase):
    def test_it_is_executable_and_declares_its_dependencies_inline(self):
        """It ships as a uv script rather than a package, which is what lets the
        plugin provide it at all — there is no install step to ask for."""
        source = support.script(PLUGIN, "slack-client")
        text = source.read_text(encoding="utf-8")

        self.assertTrue(source.exists())
        self.assertIn("uv run --script", text.splitlines()[0])
        self.assertIn("# /// script", text)

    def test_it_carries_no_organization_specific_values(self):
        """It shipped verbatim from one machine, so this pins the property that made
        that safe rather than trusting the reading that established it."""
        text = support.script(PLUGIN, "slack-client").read_text(encoding="utf-8").lower()

        for token in ("aligned", "danfox", "alignedmarketplace"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


class ScaffoldTest(unittest.TestCase):
    def scaffold(self, directory, *arguments):
        return support.run_script(
            support.script(PLUGIN, "scaffold.py"), arguments=[directory, *arguments]
        )

    def test_creates_the_layout_and_the_register(self):
        with tempfile.TemporaryDirectory() as directory:
            self.scaffold(directory)
            root = Path(directory)

            for relative in ("inbox/.gitkeep", "inbox/processed", "notes/.sync-state",
                             ".knowledge-base.json", ".gitignore"):
                with self.subTest(path=relative):
                    self.assertTrue((root / relative).exists())

    def test_the_scaffolded_register_is_loadable(self):
        """Scaffolding something the loader then rejects would be the worst of both."""
        with tempfile.TemporaryDirectory() as directory:
            self.scaffold(directory)

            self.assertEqual(in_module(f"configuration.sources({str(directory)!r})"), "{}")

    def test_a_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.scaffold(directory, "--dry-run")

            self.assertIn("would create", result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_re_running_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.scaffold(directory)
            before = {
                path: path.read_bytes()
                for path in Path(directory).rglob("*") if path.is_file()
            }

            second = self.scaffold(directory)

            after = {
                path: path.read_bytes()
                for path in Path(directory).rglob("*") if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertNotIn("created:", second.stdout)

    def test_an_existing_gitignore_is_appended_to_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            gitignore = Path(directory) / ".gitignore"
            gitignore.write_text("# theirs\n*.secret\n")

            self.scaffold(directory)

            text = gitignore.read_text(encoding="utf-8")
            self.assertIn("*.secret", text)
            self.assertIn("inbox/*", text)

    def test_the_gitignore_rule_actually_ignores_intake(self):
        """The one claim worth proving against git rather than by inspection: the
        whole pattern rests on raw intake being unable to reach a commit."""
        with tempfile.TemporaryDirectory() as directory:
            self.scaffold(directory)
            subprocess.run(["git", "init", "-q", directory], check=True, capture_output=True)

            for relative in ("inbox/20260818_raw.txt", "inbox/processed/20260817_done.txt"):
                (Path(directory) / relative).write_text("raw content")

                with self.subTest(path=relative):
                    ignored = subprocess.run(
                        ["git", "-C", directory, "check-ignore", relative],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(ignored.returncode, 0, f"{relative} is NOT ignored")

    def test_the_register_and_watermarks_are_tracked(self):
        """The mirror of the rule above: the two files a clone needs must be committable."""
        with tempfile.TemporaryDirectory() as directory:
            self.scaffold(directory)
            subprocess.run(["git", "init", "-q", directory], check=True, capture_output=True)

            for relative in (".knowledge-base.json", "notes/.sync-state", "inbox/.gitkeep"):
                with self.subTest(path=relative):
                    ignored = subprocess.run(
                        ["git", "-C", directory, "check-ignore", relative],
                        capture_output=True, text=True,
                    )
                    self.assertNotEqual(ignored.returncode, 0, f"{relative} is ignored")


if __name__ == "__main__":
    unittest.main()


ADAPTER_SCRIPTS = "skills/knowledge-base/scripts"

# A variable no developer's environment sets, so its absence is the default.
SESSION_VARIABLE = "KNOWLEDGE_BASE_TEST_COVERED_SESSION"

STUB_CHAT_CLIENT = '''#!/usr/bin/env python3
import json, os, sys
command = sys.argv[1]
if os.environ.get("STUB_CALL_LOG"):
    with open(os.environ["STUB_CALL_LOG"], "a", encoding="utf-8") as log:
        log.write(" ".join(sys.argv[1:]) + "\\n")
if command == "history" and sys.argv[2] == os.environ.get("STUB_FAIL_HISTORY"):
    sys.exit("slack api error: internal_error")
if command == "memberships":
    print("C001\\tunlocked\\tgeneral")
    print("C002\\tlocked\\tbilling-ops")
    print("C003\\tlocked\\tengineering")
    print("C004\\tunlocked\\tcase-review\\t:lock: THIS CHANNEL MAY CONTAIN PHI/PII")
elif command == "history":
    per = {
        "C001": [
            {"ts": "1500.0", "user_name": "ana", "text": "shipped the &lt;retry&gt; fix"},
            {"ts": "1510.0", "user_name": "bo", "text": "thanks!"},
            {"ts": "1520.0", "user_name": "bo", "subtype": "channel_join", "text": ""},
            {"ts": "900.0", "user_name": "cy", "text": "older parent",
             "latest_reply": "1600.0", "reply_count": 1},
        ],
        "C002": [{"ts": "1700.0", "user_name": "dee", "text": "SENSITIVE-MARKER refund"}],
        "C003": [{"ts": "1800.0", "user_name": "eli",
                  "text": "see <https://x.test|the doc> for #general"}],
        "C004": [{"ts": "1750.0", "user_name": "fay", "text": "TOPIC-MARKER case"}],
    }
    for message in per[sys.argv[2]]:
        print(json.dumps(message))
elif command == "replies":
    print(json.dumps({"ts": "900.0", "user_name": "cy", "text": "older parent"}))
    print(json.dumps({"ts": "1600.0", "user_name": "cy", "text": "and the follow-up"}))
'''

# Conversations the platform marks only by kind or purpose: a direct message and a
# group direct message, each named for its people and with no lock, and a public
# channel whose purpose, not its topic, carries the banner. Every conversation has
# one message after the watermark.
STUB_CHAT_DIRECT = '''#!/usr/bin/env python3
import json, sys
command = sys.argv[1]
if command == "memberships":
    print("C010\\t-\\topen-channel\\t\\tchannel\\t")
    print("D011\\t-\\tPat PERSON-NAME\\t\\tim\\t")
    print("G012\\t-\\tLee PERSON-NAME, Kim PERSON-NAME\\t\\tmpim\\t")
    print("C013\\t-\\tcases\\t\\tchannel\\tMay Contain Personal Data")
elif command == "history":
    print(json.dumps({"ts": "1500.0", "user_name": "ana", "text": "MESSAGE-TEXT " + sys.argv[2]}))
'''

STUB_CHAT_EMPTY = '''#!/usr/bin/env python3
'''


def adapter(name):
    return support.plugin_root(PLUGIN) / ADAPTER_SCRIPTS / name


class EmailParsingTest(unittest.TestCase):
    """The email adapter's parsing, which decides what a copy is a copy *of*.

    Exercised in-process: these are pure functions over strings, and the module
    guards its network imports precisely so they can be reached by a bare
    `python3`. The Graph paths are not testable without credentials and are not
    pretended to be.
    """

    def setUp(self):
        sys.path.insert(0, str(support.plugin_root(PLUGIN) / ADAPTER_SCRIPTS))
        sys.path.insert(0, str(support.plugin_root(PLUGIN) / "scripts"))

        import email_sweep

        self.sweep = email_sweep

    def test_whitelisted_mail_without_a_recap_title_is_set_aside(self):
        """A vendor's marketing and its recording-access notices come from the same
        domain as its recaps. The subject already says which is which, so the
        whitelist stays a domain match and the title decides what gets parsed."""
        recap = {"subject": 'Recap for "Weekly sync"'}
        shared = {"subject": "Pat shared a recap of Planning"}
        marketing = {"subject": "Introducing Fathom Teams"}
        access = {"subject": "Pat shared a recording with you"}
        sender = {"match": "domain", "value": "fathom.video"}

        recaps, others = self.sweep.split_by_title(
            [(recap, sender), (marketing, sender), (shared, sender), (access, sender)]
        )

        self.assertEqual([message["subject"] for message, _ in recaps], [recap["subject"], shared["subject"]])
        self.assertEqual([message["subject"] for message, _ in others], [marketing["subject"], access["subject"]])

    def test_a_sender_with_its_own_title_patterns_is_judged_by_those(self):
        sender = {"value": "notes.example", "title_patterns": [r"^Notes: (.+)$"]}

        recaps, others = self.sweep.split_by_title(
            [({"subject": "Notes: Board prep"}, sender), ({"subject": 'Recap for "x"'}, sender)]
        )

        self.assertEqual(len(recaps), 1)
        self.assertEqual(others[0][0]["subject"], 'Recap for "x"')

    def test_the_footer_date_beats_a_date_mentioned_in_the_summary(self):
        """The whole reason a body marker is configured. A summary saying "deploys
        August 10" would otherwise key the meeting to the wrong day."""
        body = "we deploy on August 10, 2026 per the plan [FATHOM] Recorded August 14, 2026"

        self.assertEqual(self.sweep.extract_meeting_date(body, "[FATHOM]"), "2026-08-14")
        self.assertEqual(self.sweep.extract_meeting_date(body, None), "2026-08-10")

    def test_the_marker_truncates_the_duplicate_half(self):
        body = "the useful summary [FATHOM] a tracking-url-padded copy of it"

        self.assertEqual(self.sweep.summarize_body(body, "[FATHOM]"), "the useful summary")

    def test_a_domain_match_survives_a_changed_local_part(self):
        """The reason to match loosely: a pinned address breaks silently the day a
        vendor renames `no-reply@` to `notifications@`."""
        sender = {"match": "domain", "value": "vendor.example"}
        message = {"from": {"emailAddress": {"address": "notifications@vendor.example"}}}

        self.assertIs(self.sweep.matching_sender(message, [sender]), sender)

    def test_an_address_match_is_exact_when_that_is_what_was_asked_for(self):
        exact = {"match": "address", "value": "no-reply@vendor.example"}
        message = {"from": {"emailAddress": {"address": "notifications@vendor.example"}}}

        self.assertIsNone(self.sweep.matching_sender(message, [exact]))

    def test_copies_of_one_meeting_collapse_but_two_meetings_do_not(self):
        """Same title on different days must stay separate; the same standup
        delivered six times must not."""
        def digest(title, date, received):
            return {"title": title, "meeting_date": date, "received": received, "summary": ""}

        digests, duplicates = self.sweep.deduplicate([
            digest("Standup", "2026-08-17", "2026-08-17T09:00:00Z"),
            digest("Standup", "2026-08-17", "2026-08-17T09:05:00Z"),
            digest("Standup", "2026-08-18", "2026-08-18T09:00:00Z"),
        ])

        self.assertEqual(len(digests), 2)
        self.assertEqual(duplicates, 1)

    def test_a_body_with_no_date_keys_on_delivery_without_merging_meetings(self):
        first = {"title": "Sync", "meeting_date": None, "received": "2026-08-17T09:00:00Z"}
        second = {"title": "Sync", "meeting_date": None, "received": "2026-08-18T09:00:00Z"}

        self.assertNotEqual(self.sweep.meeting_key(first), self.sweep.meeting_key(second))

    def test_digest_shape_is_recognized_independently_of_the_sender(self):
        """The net under a whitelist: a vendor moving domains must go loud."""
        message = {"subject": "Ana shared a recap of Planning", "bodyPreview": ""}

        self.assertTrue(self.sweep.looks_like_digest(message, ["shared a recap"]))

    def test_drift_reports_digest_shaped_mail_from_an_unknown_sender(self):
        senders = [{"match": "domain", "value": "known.example"}]
        message = {
            "subject": "Ana shared a recap of Planning",
            "bodyPreview": "",
            "from": {"emailAddress": {"address": "no-reply@moved.example"}},
        }

        drift = self.sweep.find_sender_drift([message], senders, ["shared a recap"])

        self.assertEqual(len(drift), 1)
        self.assertIn("moved.example", drift[0])

    def test_running_without_uv_says_so_instead_of_raising_importerror(self):
        with self.assertRaises(self.sweep.SweepError) as raised:
            self.sweep.acquire_access_token({"client_id": "a", "tenant_id": "b"})

        self.assertIn("uv run", str(raised.exception))

    def digest(self, title="Pat TITLE-MARKER review", date="2026-08-17"):
        return {"title": title, "meeting_date": date, "received": f"{date}T09:00:00Z",
                "summary": ""}

    def test_a_meeting_is_keyed_by_a_hash_that_carries_no_title(self):
        """The ledger is committed, and a title can name a person."""
        key = self.sweep.meeting_key(self.digest())

        self.assertRegex(key, r"^[0-9a-f]{64}$")
        self.assertNotIn("title-marker", key)

    def test_a_ledger_written_with_plain_keys_still_labels_its_meetings(self):
        """An earlier ledger keyed each meeting by its lowercased title and date. Its
        records still match, and the next write keeps them under the hashed key."""
        digest = self.digest()
        earlier = {"meeting_date": "2026-08-17", "first_seen": "2026-08-17T09:00:00Z",
                   "intake_file": "earlier.md"}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".delivery-ledger"
            path.write_text(json.dumps({"pat title-marker review|2026-08-17": earlier}),
                            encoding="utf-8")
            ledger = self.sweep.read_ledger(path)

        self.assertEqual(self.sweep.find_returning([digest], ledger), [(digest, earlier)])

        written = self.sweep.extended_ledger(ledger, [digest], "later.md", 36500)

        self.assertEqual(list(written), [self.sweep.meeting_key(digest)])
        self.assertEqual(written[self.sweep.meeting_key(digest)], earlier)

    def test_a_returning_meeting_is_named_by_its_key_never_its_title(self):
        import contextlib
        import io

        digest = self.digest()
        earlier = {"first_seen": "2026-08-17T09:00:00Z", "intake_file": "earlier.md"}
        printed = io.StringIO()

        with contextlib.redirect_stdout(printed):
            self.sweep.report_returning([(digest, earlier)])

        self.assertIn(self.sweep.meeting_key(digest)[:12], printed.getvalue())
        self.assertNotIn("TITLE-MARKER", printed.getvalue())

    def test_subjects_and_addresses_go_into_the_intake_file(self):
        """They say why a message was set aside or noticed, and a subject can name a
        person, so they are written where the gate reads them, not printed."""
        sender = {"match": "domain", "value": "vendor.example"}
        message = {"subject": "Pat SUBJECT-MARKER shared a recording",
                   "from": {"emailAddress": {"address": "no-reply@vendor.example"}}}

        lines = "\n".join(self.sweep.notice_lines(
            [(message, sender)], ["digest-shaped mail from DRIFT-MARKER"], ["new@vendor.example"]))

        for text in ("SUBJECT-MARKER", "DRIFT-MARKER", "new@vendor.example"):
            with self.subTest(text=text):
                self.assertIn(text, lines)


class EmailAdapterInvocationTest(unittest.TestCase):
    def test_a_source_declaring_no_senders_refuses_rather_than_sweeping_everything(self):
        """A whitelist is what makes mail tractable. Without one the adapter would
        have to judge every message for relevance, so it stops instead."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(email={"adapter": "email"}))

            result = support.run_script(
                adapter("email_sweep.py"),
                arguments=["2026-08-01T00:00:00Z", str(Path(directory) / "inbox" / "out.md")],
                KNOWLEDGE_BASE_CONFIG_FILE=str(path),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("no senders", result.stderr)

    def email_source(self):
        return {
            "adapter": "email",
            "senders": [{"match": "domain", "value": "example.test"}],
            "graph": {"client_id": "x", "tenant_id": "y", "credential_cache": "/nonexistent"},
        }

    def test_a_watermark_past_the_lookback_cap_refuses_before_touching_the_mailbox(self):
        """A stale watermark would list every message in the gap before the whitelist
        narrows it; the refusal comes before any network call, and names both ways
        forward rather than clamping, since a clamp would skip the gap silently."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(email=self.email_source()))

            result = support.run_script(
                adapter("email_sweep.py"),
                arguments=["2020-01-01T00:00:00Z", str(Path(directory) / "inbox" / "out.md")],
                KNOWLEDGE_BASE_CONFIG_FILE=str(path),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("max_lookback_days", result.stderr)
            self.assertIn("--allow-backfill", result.stderr)

    def test_an_output_outside_the_intake_directory_is_refused_before_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(email=self.email_source()))
            output = Path(directory).resolve() / "out.md"

            result = support.run_script(
                adapter("email_sweep.py"),
                arguments=["2026-08-01T00:00:00Z", str(output)],
                KNOWLEDGE_BASE_CONFIG_FILE=str(path),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("outside the intake directory", result.stderr)
            self.assertIn(str(Path(directory).resolve() / "inbox"), result.stderr)
            self.assertFalse(output.exists())

    def test_the_register_sets_its_own_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.email_source() | {"max_lookback_days": 3650}
            path = write_register(directory, register(email=source))

            result = support.run_script(
                adapter("email_sweep.py"),
                arguments=["2020-01-01T00:00:00Z", str(Path(directory) / "inbox" / "out.md")],
                KNOWLEDGE_BASE_CONFIG_FILE=str(path),
            )

            # Past the cap check: the next failure is the credential cache, not the lookback.
            self.assertNotIn("max_lookback_days", result.stderr)


class ChatClientInvocationTest(unittest.TestCase):
    """How the adapter reaches the bundled client. Without a client_command
    override it runs the uv script directly, not the bin/ launcher — the launcher
    is extensionless, and Python's subprocess execs through CreateProcess on
    Windows, which appends only `.exe` and cannot run it, while `uv` resolves as
    `uv.exe`."""

    def invocation(self, source):
        directory = adapter("chat_export.py").parent
        program = (
            f"import sys, json; sys.path.insert(0, {str(directory)!r});"
            "import chat_export;"
            "print(json.dumps(chat_export.Client(json.loads(sys.argv[1])).invocation))"
        )
        result = subprocess.run(
            [sys.executable, "-c", program, json.dumps(source)],
            capture_output=True,
            text=True,
            check=True,
        )

        return json.loads(result.stdout)

    def test_the_default_runs_the_bundled_script_under_uv(self):
        invocation = self.invocation({})

        self.assertEqual(invocation[:3], ["uv", "run", "--script"])
        self.assertEqual(
            Path(invocation[3]).resolve(), support.script(PLUGIN, "slack-client").resolve()
        )

    def test_a_client_command_override_is_run_directly(self):
        self.assertEqual(self.invocation({"client_command": "/tmp/stub-client"}), ["/tmp/stub-client"])


class ChatAdapterTest(unittest.TestCase):
    """The chat adapter against a stub client, which is the only way to reach this
    logic without a workspace. What is being pinned is not the stub's content but
    the properties the design rests on: each active conversation is its own raw
    file and the index carries no message, no output stream carries message text
    or a direct message's name, noise is dropped, and a revived thread
    contributes only its new replies."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = self.root = Path(self.directory.name).resolve()

        # The register names the client by path, so the stub has to be invoked the
        # way the platform can: support.stub_command returns that path.
        self.client = support.stub_command(root / "stub-chat", STUB_CHAT_CLIENT)

        self.output = root / "inbox" / "export.md"
        self.raw = root / "inbox" / "chat"
        self.config = write_register(root, register(chat={
            "adapter": "chat",
            "client_command": str(self.client),
        }))

    def tearDown(self):
        self.directory.cleanup()

    def export(self, *extra, **environment):
        return support.run_script(
            adapter("chat_export.py"),
            arguments=["1000.0", str(self.output), *extra],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
            **environment,
        )

    def raw_text(self):
        return "".join(path.read_text(encoding="utf-8") for path in sorted(self.raw.glob("*.md")))

    def test_each_active_conversation_is_its_own_raw_file(self):
        """One conversation is one batch for the gate, a record-dense one included."""
        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(path.name for path in self.raw.glob("*.md")),
                         ["C001.md", "C002.md", "C003.md", "C004.md"])
        self.assertIn("SENSITIVE-MARKER", (self.raw / "C002.md").read_text(encoding="utf-8"))

    def test_the_index_names_each_raw_file_and_carries_no_message(self):
        result = self.export()
        index = self.output.read_text(encoding="utf-8")

        for identifier in ("C001", "C002", "C003", "C004"):
            with self.subTest(identifier=identifier):
                self.assertIn(str(self.raw / f"{identifier}.md"), index)
                self.assertIn(f"  {self.raw / f'{identifier}.md'}", result.stdout)

        for token in ("SENSITIVE-MARKER", "shipped the", "the follow-up", "TOPIC-MARKER"):
            with self.subTest(token=token):
                self.assertNotIn(token, index)

    def test_count_only_writes_no_message_anywhere(self):
        result = self.export("--count-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.raw.exists())
        self.assertIn("Counted only", self.output.read_text(encoding="utf-8"))
        self.assertNotIn("SENSITIVE-MARKER", self.output.read_text(encoding="utf-8"))
        self.assertIn("New watermark: 1800.0", result.stdout)

    def test_stdout_carries_no_message_text(self):
        """What makes it safe for the main session to run this itself."""
        result = self.export()

        for token in ("SENSITIVE-MARKER", "shipped the", "the follow-up"):
            with self.subTest(token=token):
                self.assertNotIn(token, result.stdout)

    def test_noise_and_bare_acknowledgements_are_dropped(self):
        self.export()
        text = self.raw_text()

        self.assertNotIn("thanks!", text)
        self.assertNotIn("channel_join", text)

    def test_wire_encoding_is_decoded_into_prose(self):
        self.export()
        text = self.raw_text()

        self.assertIn("<retry>", text)
        self.assertIn("the doc (https://x.test)", text)
        self.assertIn("#general", text)

    def test_a_revived_thread_contributes_only_its_new_replies(self):
        """A reply does not bump its parent's timestamp, so this is the case a
        watermark alone cannot see — and the parent must not be re-reported as new."""
        self.export()
        text = self.raw_text()

        self.assertIn("and the follow-up", text)
        self.assertIn("thread continued", text)

    def test_a_quiet_window_says_to_skip_the_isolated_agent(self):
        """With no new message anywhere, the gate has nothing to read."""
        result = support.run_script(
            adapter("chat_export.py"),
            arguments=["5000.0", str(self.output)],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

        self.assertIn("0 conversation(s) with new messages", result.stdout)
        self.assertIn("skip the gate", result.stdout)
        self.assertEqual(list(self.raw.glob("*.md")), [])

    def test_an_active_window_does_not_say_to_skip(self):
        result = self.export()

        self.assertIn("4 conversation(s) with new messages", result.stdout)
        self.assertNotIn("skip the gate", result.stdout)

    def test_the_watermark_advances_to_the_newest_activity(self):
        result = self.export()

        self.assertIn("New watermark: 1800.0", result.stdout)

    def test_a_missing_client_is_reported_rather_than_traced(self):
        self.client.unlink()

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("chat_export:", result.stderr)

    def test_a_source_absent_from_the_register_is_named(self):
        result = support.run_script(
            adapter("chat_export.py"),
            arguments=["1000.0", str(self.output), "--source", "nonexistent"],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("nonexistent", result.stderr)

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_folder_git_does_not_ignore_is_refused_before_any_fetch(self):
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("must be git-ignored", result.stderr)
        self.assertFalse(self.raw.exists())
        self.assertFalse(self.output.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_folder_git_ignores_is_accepted(self):
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)
        (self.root / ".gitignore").write_text("inbox/\n", encoding="utf-8")

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(self.raw.glob("*.md"))), 4)

    def test_a_folder_a_previous_run_left_files_in_is_refused_before_any_fetch(self):
        self.raw.mkdir(parents=True)
        (self.raw / "billing-ops.md").write_text("left over", encoding="utf-8")

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("previous run's working files", result.stderr)
        self.assertFalse(self.output.exists())

    def use_client(self, source, **settings):
        self.client = support.stub_command(self.root / "stub-direct", source)
        self.config.write_text(json.dumps(register(chat={
            "adapter": "chat",
            "client_command": str(self.client),
            **settings,
        })), encoding="utf-8")

    def exclude(self, **settings):
        self.config.write_text(json.dumps(register(chat={
            "adapter": "chat", "client_command": str(self.client), **settings,
        })), encoding="utf-8")
        log = self.root / "calls.log"
        log.unlink(missing_ok=True)
        result = self.export(STUB_CALL_LOG=str(log))
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []

        return result, calls

    def test_an_excluded_conversation_is_never_fetched_or_written(self):
        result, calls = self.exclude(excluded_conversations=["#billing-*"])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call.startswith("history C002") for call in calls), calls)
        self.assertTrue(any(call.startswith("history C001") for call in calls), calls)
        self.assertFalse((self.raw / "C002.md").exists())
        self.assertNotIn("billing-ops", self.output.read_text(encoding="utf-8"))
        self.assertNotIn("SENSITIVE-MARKER", self.raw_text())

    def test_the_run_counts_exclusions_without_naming_them(self):
        result, _ = self.exclude(excluded_conversations=["billing-ops", "engineering"])

        self.assertIn("2 conversation(s) excluded", result.stdout)
        self.assertNotIn("billing-ops", result.stdout + result.stderr)
        self.assertNotIn("engineering", result.stdout + result.stderr)

    def test_patterns_are_globs_case_insensitive_with_an_optional_hash(self):
        for pattern, excluded in (("ENGINEER*", "C003"), ("#general", "C001"),
                                  ("case-?eview", "C004"), ("gen", None)):
            with self.subTest(pattern=pattern):
                shutil.rmtree(self.raw, ignore_errors=True)
                result, calls = self.exclude(excluded_conversations=[pattern])
                fetched = {call.split()[1] for call in calls if call.startswith("history")}

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({"C001", "C002", "C003", "C004"} - fetched,
                                 {excluded} if excluded else set())

    def test_a_marked_conversation_is_excluded_when_the_register_says_so(self):
        result, calls = self.exclude(private_topic_markers=["this channel may contain"],
                                     marked_conversations="exclude")

        self.assertFalse(any(call.startswith("history C004") for call in calls), calls)
        self.assertIn("1 conversation(s) excluded", result.stdout)

    def test_a_marked_conversation_is_excluded_by_default(self):
        """A register listing markers meant them to keep a conversation from being
        read directly, so leaving the handling unset excludes it."""
        result, calls = self.exclude(private_topic_markers=["this channel may contain"])

        self.assertFalse(any(call.startswith("history C004") for call in calls), calls)
        self.assertIn("1 conversation(s) excluded", result.stdout)

    def test_a_marked_conversation_is_digested_when_the_register_says_so(self):
        for settings in ({"marked_conversations": "digest"}, {"marked_conversations": "scrub"}):
            with self.subTest(settings=settings):
                shutil.rmtree(self.raw, ignore_errors=True)
                result, calls = self.exclude(private_topic_markers=["this channel may contain"],
                                             **settings)

                self.assertTrue(any(call.startswith("history C004") for call in calls), calls)
                self.assertIn("0 conversation(s) excluded", result.stdout)

    def test_a_purpose_banner_excludes_too(self):
        self.client = support.stub_command(self.root / "stub-direct", STUB_CHAT_DIRECT)

        result, _ = self.exclude(private_topic_markers=["may contain personal data"],
                                 marked_conversations="exclude")

        self.assertIn("1 conversation(s) excluded", result.stdout)
        self.assertFalse((self.raw / "C013.md").exists())
        self.assertTrue((self.raw / "C010.md").exists())

    def test_a_dense_conversation_is_excluded(self):
        """Its text was never meant to be read directly."""
        result, calls = self.exclude(dense_conversations=["#billing-ops"])

        self.assertFalse(any(call.startswith("history C002") for call in calls), calls)
        self.assertFalse((self.raw / "C002.md").exists())
        self.assertIn("1 conversation(s) excluded", result.stdout)

    def test_dense_and_excluded_conversations_are_counted_together(self):
        result, _ = self.exclude(dense_conversations=["billing-ops"],
                                 excluded_conversations=["general"],
                                 private_topic_markers=["this channel may contain"])

        self.assertIn("3 conversation(s) excluded", result.stdout)

    def test_a_pattern_matches_a_conversation_id_too(self):
        """An id survives a rename, so it is the durable form."""
        result, calls = self.exclude(excluded_conversations=["c003"])

        self.assertFalse(any(call.startswith("history C003") for call in calls), calls)
        self.assertIn("1 conversation(s) excluded", result.stdout)

    def test_a_failed_run_takes_back_the_raw_files_it_wrote(self):
        log = self.root / "calls.log"

        result = self.export(STUB_CALL_LOG=str(log), STUB_FAIL_HISTORY="C003")

        self.assertEqual(result.returncode, 1)
        self.assertIn("raw files this run wrote were removed", result.stderr)
        self.assertIn("history C001", log.read_text(encoding="utf-8"))
        self.assertEqual(list(self.raw.glob("*")), [])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.export().returncode, 0)

    def test_an_unknown_marked_handling_is_refused_before_any_fetch(self):
        result, calls = self.exclude(marked_conversations="hide")

        self.assertEqual(result.returncode, 1)
        self.assertIn("marked_conversations", result.stderr)
        self.assertEqual(calls, [])

    def require_session(self):
        self.config.write_text(json.dumps({**register(chat={
            "adapter": "chat", "client_command": str(self.client)}),
            "session": {"required_variable": SESSION_VARIABLE}}), encoding="utf-8")

    def test_outside_the_required_session_nothing_is_fetched(self):
        self.require_session()
        log = self.root / "calls.log"

        for value in (None, ""):
            with self.subTest(value=value):
                result = self.export(STUB_CALL_LOG=str(log), **{SESSION_VARIABLE: value})

                self.assertEqual(result.returncode, 1)
                self.assertIn(f"syncs only in a session that sets {SESSION_VARIABLE}",
                              result.stderr)
                self.assertIn("nothing was fetched", result.stderr)
                self.assertFalse(log.exists())
                self.assertFalse(self.output.exists())
                self.assertFalse(self.raw.exists())

    def test_inside_the_required_session_the_run_goes_ahead(self):
        self.require_session()

        result = self.export(**{SESSION_VARIABLE: "1"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.raw / "C001.md").exists())

    def test_streams_name_a_conversation_by_id_never_by_its_name(self):
        """A direct message is named for its people. Each conversation fills the
        one-message limit without reaching the watermark, so each is a gap."""
        self.use_client(STUB_CHAT_DIRECT, history_limit=1)

        result = self.export()
        streams = result.stdout + result.stderr

        self.assertIn("D011 hit the 1-message fetch limit", result.stderr)
        self.assertNotIn("PERSON-NAME", streams)
        self.assertNotIn("MESSAGE-TEXT", streams)

    def test_an_empty_membership_list_is_refused_cleanly(self):
        self.use_client(STUB_CHAT_EMPTY)

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("listed no conversation", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_an_output_outside_the_intake_directory_is_refused_before_any_fetch(self):
        for extra in ((), ("--count-only",)):
            with self.subTest(extra=extra):
                self.output = self.root / "export.md"

                result = self.export(*extra)

                self.assertEqual(result.returncode, 1)
                self.assertIn(f"outside the intake directory {self.root / 'inbox'}", result.stderr)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.raw.exists())

    def test_an_output_linked_out_of_the_intake_directory_is_refused(self):
        outside = self.root / "outside.md"
        self.output.parent.mkdir(parents=True)

        try:
            self.output.symlink_to(outside)

        except OSError:
            self.skipTest("this platform cannot create a symbolic link here")

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the intake directory", result.stderr)
        self.assertFalse(outside.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_an_output_git_does_not_ignore_is_refused_before_any_fetch(self):
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)
        (self.root / ".gitignore").write_text("inbox/chat/\n", encoding="utf-8")

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(f"the output {self.output}", result.stderr)
        self.assertIn("must be git-ignored", result.stderr)
        self.assertFalse(self.output.exists())

    @unittest.skipIf(os.name == "nt", "Windows has no mode bits")
    def test_what_it_writes_is_its_owners_alone(self):
        self.export()
        side_file = next(self.raw.glob("*.md"))

        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(side_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.raw.stat().st_mode), 0o700)



def notion_page(identifier, edited, title, parent="page"):
    return {
        "object": "page",
        "id": identifier,
        "last_edited_time": edited,
        "parent": {"type": f"{parent}_id"},
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": title}]},
            "Stage": {"type": "select", "select": {"name": "PROPERTY-MARKER"}},
        },
    }


def notion_block(identifier, kind, text="", has_children=False, **content):
    return {
        "object": "block",
        "id": identifier,
        "type": kind,
        "has_children": has_children,
        kind: {"rich_text": [{"plain_text": text}], **content},
    }


class StubNotion:
    """A local stand-in for the Notion REST API, serving a fixed tree.

    hub (edited after the watermark)
      ├─ unchanged        child page, edited before it
      ├─ changed          child page: marker text, a person-shaped title, a one-off 503
      ├─ column_list → column → nested       found only by descending containers
      ├─ heading_2 (toggle) → under-heading  found only by descending any block with children
      └─ database         child database: one changed row, one old one

    `broken` holds children the renderer cannot handle; tests opt into it.
    """

    WATERMARK = "2026-09-20T10:30:45Z"

    PAGES = {
        "hub": notion_page("hub", "2026-09-21T09:00:00.000Z", "Operations hub"),
        "unchanged": notion_page("unchanged", "2026-09-01T09:00:00.000Z", "UNCHANGED-TITLE"),
        "changed": notion_page("changed", "2026-09-22T09:00:00.000Z", "Jane PERSON-TITLE"),
        "nested": notion_page("nested", "2026-09-20T10:30:00.000Z", "Nested page"),
        "under-heading": notion_page("under-heading", "2026-09-24T09:00:00.000Z", "Grouped"),
        "broken": notion_page("broken", "2026-09-24T09:00:00.000Z", "Broken"),
    }

    CHILDREN = {
        "hub": [
            notion_block("unchanged", "child_page", title="UNCHANGED-TITLE"),
            notion_block("changed", "child_page", title="Jane PERSON-TITLE"),
            notion_block("columns", "column_list", has_children=True),
            notion_block("heading", "heading_2", "Group", has_children=True, is_toggleable=True),
            notion_block("database", "child_database", title="Rows"),
        ],
        "columns": [notion_block("column", "column", has_children=True)],
        "column": [notion_block("nested", "child_page", title="Nested page")],
        "heading": [notion_block("under-heading", "child_page", title="Grouped")],
        "changed": [notion_block("paragraph", "paragraph", "SENSITIVE-MARKER detail")],
        "unchanged": [],
        "nested": [notion_block("paragraph-2", "paragraph", "nested text")],
        "under-heading": [],
        "row": [notion_block("paragraph-3", "paragraph", "ROW-MARKER text")],
        "old-row": [],
        "broken": [{"object": "block", "id": "no-type", "has_children": False}],
    }

    ROWS = {
        "database": [
            notion_page("row", "2026-09-23T09:00:00.000Z", "A row", "database"),
            notion_page("old-row", "2026-08-01T09:00:00.000Z", "An old row", "database"),
        ],
        "empty-database": [],
    }

    def __init__(self):
        import http.server
        import threading

        stub = self
        self.authorizations = []
        self.first_request_at = None
        self.failed_once = set()

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *arguments):
                pass

            def reply(self, status, document):
                body = json.dumps(document).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "0")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def once(self, key, status):
                if key in stub.failed_once:
                    return False

                stub.failed_once.add(key)
                self.reply(status, {"object": "error", "code": "transient"})

                return True

            def record(self):
                from datetime import datetime, timezone

                stub.first_request_at = stub.first_request_at or datetime.now(timezone.utc)
                stub.authorizations.append(self.headers.get("Authorization"))

            def not_found(self):
                self.reply(404, {"object": "error", "code": "object_not_found",
                                 "message": "LEAKY-ERROR-MESSAGE"})

            def do_GET(self):
                self.record()
                parts = self.path.split("?")[0].strip("/").split("/")

                if parts[0] == "pages" and parts[1] == "hub" and self.once("hub-429", 429):
                    return

                if parts[0] == "pages" and parts[1] in stub.PAGES:
                    return self.reply(200, stub.PAGES[parts[1]])

                if parts[0] == "blocks" and parts[1] == "changed" and self.once("changed-503", 503):
                    return

                if parts[0] == "blocks" and parts[1] in stub.CHILDREN:
                    return self.reply(200, {"results": stub.CHILDREN[parts[1]], "has_more": False})

                self.not_found()

            def do_POST(self):
                self.record()
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                parts = self.path.strip("/").split("/")

                if parts[0] == "databases" and parts[1] in stub.ROWS:
                    return self.reply(200, {"results": stub.ROWS[parts[1]], "has_more": False})

                self.not_found()

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def api_base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class NotionAdapterTest(unittest.TestCase):
    """The notion adapter against a stub API. The properties pinned are the ones the
    design rests on: a changed page's content, title and properties reach only its
    side file; no output stream carries content or the token, whatever fails;
    discovery finds pages under any block with children and in databases; and
    anything that could hide an edit withholds the watermark."""

    TOKEN = "Bearer secret-TOKEN-MARKER"
    CONTENT = ("SENSITIVE-MARKER", "PERSON-TITLE", "ROW-MARKER", "PROPERTY-MARKER",
               "LEAKY-ERROR-MESSAGE", "TOKEN-MARKER")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.stub = StubNotion()
        self.output = self.root / "inbox" / "export.md"
        self.raw = self.root / "inbox" / "notion-covered"
        self.claude_config = self.root / "claude.json"
        self.write_token(self.TOKEN)
        self.write_source([
            {"name": "Operations hub", "id": "hub"},
            {"name": "Playbooks", "id": "empty-database", "kind": "database"},
        ])

    def tearDown(self):
        self.stub.close()
        self.directory.cleanup()

    def write_token(self, value):
        self.claude_config.write_text(json.dumps({"mcpServers": {"notion": {
            "env": {"OPENAPI_MCP_HEADERS": json.dumps({"Authorization": value})},
        }}}))

    def write_source(self, locations):
        self.config = write_register(self.root, register(**{"notion-covered": {
            "adapter": "notion",
            "api_base": self.stub.api_base,
            "request_interval_seconds": 0,
            "credential": {"claude_config": str(self.claude_config)},
            "covered_locations": locations,
        }}))

    def export(self, *extra, watermark=StubNotion.WATERMARK):
        """A walk: the stub serves a tree and no search, which is what these tests
        pin. Search discovery has its own class below."""
        return support.run_script(
            adapter("notion_export.py"),
            arguments=[watermark, str(self.output), "--source", "notion-covered", "--walk",
                       *extra],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

    def export_text(self):
        return self.output.read_text(encoding="utf-8")

    def assert_nothing_leaked(self, result, files=()):
        streams = result.stdout + result.stderr + "".join(
            path.read_text(encoding="utf-8") for path in files if path.exists()
        )

        for token in self.CONTENT:
            with self.subTest(token=token):
                self.assertNotIn(token, streams)

    def test_a_changed_page_reaches_only_its_side_file(self):
        self.export()
        side_file = (self.raw / "changed.md").read_text(encoding="utf-8")

        for token in ("SENSITIVE-MARKER", "PERSON-TITLE", "PROPERTY-MARKER"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.export_text())
                self.assertIn(token, side_file)

        self.assertIn(str(self.raw / "changed.md"), self.export_text())

    def test_count_only_writes_nothing_of_a_page(self):
        result = self.export("--count-only")

        self.assertNotIn("SENSITIVE-MARKER", self.export_text())
        self.assertFalse(self.raw.exists())
        self.assertIn("listed only", result.stdout)

    def test_no_output_stream_carries_content_or_the_token(self):
        result = self.export()

        self.assert_nothing_leaked(result, files=[self.output])

    def test_the_token_is_sent_and_written_nowhere(self):
        self.export()
        written = self.export_text() + "".join(
            path.read_text(encoding="utf-8") for path in self.raw.glob("*.md")
        )

        self.assertEqual(set(self.stub.authorizations), {self.TOKEN})
        self.assertNotIn("TOKEN-MARKER", written)

    def test_a_token_with_a_line_break_is_refused_without_quoting_it(self):
        """http.client quotes a bad header value in its exception, and a traceback prints it."""
        self.write_token("Bearer secret-TOKEN\nMARKER")

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("malformed", result.stderr)
        self.assertNotIn("TOKEN", result.stderr.replace("Notion token", ""))
        self.assertNotIn("Traceback", result.stderr)

    def test_an_unchanged_page_or_row_is_not_listed(self):
        self.export()

        self.assertNotIn("`unchanged`", self.export_text())
        self.assertNotIn("`old-row`", self.export_text())

    def test_discovery_descends_every_block_with_children(self):
        """Containers, toggle headings, and child databases alike."""
        self.export()

        for page in ("nested", "under-heading", "row"):
            with self.subTest(page=page):
                self.assertIn(f"`{page}`", self.export_text())

    def test_an_edit_in_the_watermarks_own_minute_is_included(self):
        """`nested` was edited at 10:30:00 against a 10:30:45 watermark; a strict
        comparison would skip it for good."""
        self.export()

        self.assertIn("`nested`", self.export_text())

    def test_counts_include_every_row_checked_not_only_changed_ones(self):
        result = self.export()

        self.assertIn("2 location(s), 7 page(s) checked, 5 changed", result.stdout)

    def test_the_watermark_is_the_clock_before_the_first_request(self):
        from datetime import datetime

        result = self.export()
        printed = re.search(r"New watermark: (\S+)", result.stdout).group(1)

        self.assertLessEqual(datetime.fromisoformat(printed.replace("Z", "+00:00")),
                             self.stub.first_request_at)

    def test_rate_limits_and_transient_errors_are_retried(self):
        """The stub answers the hub's first fetch with a 429, and `changed`'s first
        children fetch with a 503."""
        result = self.export()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.stub.failed_once, {"hub-429", "changed-503"})
        self.assertIn("SENSITIVE-MARKER", (self.raw / "changed.md").read_text(encoding="utf-8"))

    def test_an_unreadable_location_withholds_the_watermark(self):
        self.write_source([
            {"name": "Operations hub", "id": "hub"},
            {"name": "Missing", "id": "not-shared"},
        ])

        result = self.export()

        self.assertEqual(result.returncode, 3)
        self.assertIn("Missing could not be read", result.stderr)
        self.assertIn("object_not_found", result.stderr)
        self.assertIn("Watermark not advanced", result.stdout)
        self.assertNotIn("New watermark", result.stdout)
        self.assertIn("`changed`", self.export_text())
        self.assert_nothing_leaked(result)

    def test_an_unqueryable_child_database_withholds_the_watermark(self):
        del StubNotion.ROWS["database"]

        try:
            result = self.export()

        finally:
            StubNotion.ROWS["database"] = [
                notion_page("row", "2026-09-23T09:00:00.000Z", "A row", "database"),
                notion_page("old-row", "2026-08-01T09:00:00.000Z", "An old row", "database"),
            ]

        self.assertEqual(result.returncode, 3)
        self.assertIn("a database could not be queried", result.stderr)
        self.assertNotIn("New watermark", result.stdout)
        self.assert_nothing_leaked(result)

    def test_a_failure_part_way_removes_the_side_files_it_wrote(self):
        """`broken` has a block the renderer cannot read, and it sorts after pages
        whose side files are already written."""
        self.write_source([{"name": "Operations hub", "id": "hub"},
                           {"name": "Broken", "id": "broken"}])

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("failed part-way", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(list(self.raw.glob("*.md")), [])
        self.assertFalse(self.output.exists())

    def test_a_quiet_window_says_to_skip_the_isolated_agent(self):
        """Nothing changed means nothing to summarize, and so no model call at all."""
        result = self.export(watermark="2026-09-30T00:00:00Z")

        self.assertEqual(result.returncode, 0)
        self.assertIn("0 changed", result.stdout)
        self.assertIn("skip the gate", result.stdout)
        self.assertEqual(list(self.raw.glob("*.md")), [])

    def test_nesting_past_the_limit_is_a_gap(self):
        """Below the limit a child page could hide, so an unsearched subtree must
        withhold the watermark rather than pass as searched."""
        self.write_source([{"name": "Operations hub", "id": "hub", "max_block_nesting": 1}])

        result = self.export()

        self.assertEqual(result.returncode, 3)
        self.assertIn("raise max_block_nesting", result.stderr)
        self.assertNotIn("New watermark", result.stdout)

    def test_a_watermark_without_a_timezone_is_refused(self):
        result = self.export(watermark="2026-09-20")

        self.assertEqual(result.returncode, 1)
        self.assertIn("no timezone", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_missing_credential_is_named_without_a_value(self):
        self.claude_config.write_text(json.dumps({"mcpServers": {}}))

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("no Notion token", result.stderr)

    def test_a_source_with_no_locations_refuses_to_run(self):
        self.write_source([])

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("covered_locations", result.stderr)

    def test_the_walk_reports_each_location_and_page_by_id_with_its_requests(self):
        """The hub's own blocks take four `children` requests: the hub, the column
        list, the column and the toggle heading. A title reaches no progress line."""
        result = self.export()
        progress = result.stderr.splitlines()

        self.assertEqual(result.returncode, 0)
        self.assertIn("location 1/2 Operations hub: walking", progress)
        self.assertIn("location 2/2 Playbooks: walking", progress)
        self.assertTrue(any(re.fullmatch(r"page 1 hub: 4 children request\(s\) in \d+\.\d s",
                                         line) for line in progress), progress)

        for page in ("unchanged", "changed", "nested", "under-heading"):
            with self.subTest(page=page):
                self.assertTrue(any(re.fullmatch(rf"page \d {page}: 1 children request\(s\) in "
                                                 r"\d+\.\d s", line) for line in progress),
                                progress)

        for title in ("UNCHANGED-TITLE", "PERSON-TITLE", "Nested page", "Grouped", "A row"):
            with self.subTest(title=title):
                self.assertNotIn(title, result.stderr)

    def test_the_walk_takes_no_lookback_and_so_no_ledger_notice(self):
        result = self.export()

        self.assertNotIn("ledger", result.stderr)

    def test_side_files_go_under_the_intake_folder_named_for_the_source(self):
        self.export()

        self.assertEqual(sorted(path.name for path in (self.root / "inbox").iterdir()),
                         ["export.md", "notion-covered"])
        self.assertTrue((self.root / "inbox" / "notion-covered" / "changed.md").is_file())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_folder_git_does_not_ignore_is_refused_before_any_request(self):
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("must be git-ignored", result.stderr)
        self.assertEqual(self.stub.authorizations, [])
        self.assertFalse(self.raw.exists())

    def test_an_output_outside_the_intake_directory_is_refused_before_any_request(self):
        self.output = self.root / "export.md"

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(f"outside the intake directory {self.root / 'inbox'}", result.stderr)
        self.assertEqual(self.stub.authorizations, [])
        self.assertFalse(self.output.exists())

    def test_a_folder_a_previous_run_left_files_in_is_refused_before_any_request(self):
        self.raw.mkdir(parents=True)
        (self.raw / "earlier.md").write_text("left over", encoding="utf-8")

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("previous run's working files", result.stderr)
        self.assertEqual(self.stub.authorizations, [])
        self.assertFalse(self.output.exists())


def search_item(identifier, edited, title, parent_type="workspace", parent_id=None, kind="page"):
    parent = {"type": parent_type, parent_type: parent_id or True}
    item = {"object": kind, "id": identifier, "last_edited_time": edited, "parent": parent}

    if kind == "database":
        item["title"] = [{"plain_text": title}]

    else:
        item["properties"] = {"Name": {"type": "title", "title": [{"plain_text": title}]}}

    return item


def search_block(identifier, kind, text, edited, has_children=False, **content):
    return {
        "object": "block",
        "id": identifier,
        "type": kind,
        "has_children": has_children,
        "created_time": edited,
        "last_edited_time": edited,
        kind: {"rich_text": [{"plain_text": text}], **content},
    }


def search_comment(identifier, created, author, text):
    return {
        "object": "comment",
        "id": identifier,
        "created_time": created,
        "created_by": {"object": "user", "id": author},
        "rich_text": [{"plain_text": text}],
    }


class StubNotionSearch:
    """A local stand-in for Notion's search and metadata endpoints.

    hub                     a covered location
      ├─ covered-child      page, person-shaped title
      │    └─ toggle        block → deep-covered, found only through the block
      └─ covered-db         database → covered-row
    team                    a page outside the hub → team-child; with `unseen`, a page
                            the integration cannot see (404)
    forbidden               a page that refuses (403), opt-in → restricted-child
    crm-db                  a database of call logs, opt-in → call-notes, pinned-notes
    recruiting              a page, opt-in → recruiting-toggle (block) → candidate

    Search pages hold two results each, and page 2's cursor names a covered item —
    the break that stalled a sweep run through the MCP server.
    """

    WATERMARK = "2026-09-20T10:30:45Z"

    RESULTS = [
        search_item("open-page", "2026-09-24T09:00:00.000Z", "Roadmap"),
        search_item("deep-covered", "2026-09-23T12:00:00.000Z", "DEEP-PERSON-TITLE",
                    "block_id", "toggle"),
        search_item("covered-row", "2026-09-23T09:00:00.000Z", "ROW-TITLE",
                    "database_id", "covered-db"),
        search_item("covered-child", "2026-09-22T09:00:00.000Z", "Jane PERSON-TITLE",
                    "page_id", "hub"),
        search_item("team-child", "2026-09-21T09:00:00.000Z", "Team | notes",
                    "page_id", "team"),
        search_item("same-minute", "2026-09-20T10:30:00.000Z", "Same minute"),
        search_item("old-page", "2026-09-01T09:00:00.000Z", "OLD-TITLE"),
        search_item("older-page", "2026-08-01T09:00:00.000Z", "OLDER-TITLE"),
        search_item("never-requested", "2026-07-01T09:00:00.000Z", "NEVER-TITLE"),
    ]

    GRANDCHILD = search_item("team-grandchild", "2026-09-25T09:00:00.000Z", "Grandchild notes",
                             "page_id", "team-child")

    RESTRICTED = search_item("restricted-child", "2026-09-21T10:00:00.000Z", "RESTRICTED-TITLE",
                             "page_id", "forbidden")

    # open-page's blocks, for the page-changes tool: an old heading holding one new
    # bullet, one old bullet somebody commented on, and one old bullet left alone;
    # then an old image and a new one whose file URL must never be printed.
    CHILDREN = {
        "open-page": [
            search_block("old-heading", "heading_2", "Agenda", "2026-09-01T09:00:00.000Z",
                         has_children=True),
            search_block("old-image", "image", "", "2026-09-01T09:00:00.000Z",
                         file={"url": "OLD-SIGNED-URL-MARKER"}),
            search_block("new-image", "image", "", "2026-09-24T09:00:00.000Z",
                         file={"url": "SIGNED-URL-MARKER"}),
        ],
        "old-heading": [
            search_block("new-bullet", "bulleted_list_item", "NEW-BULLET text",
                         "2026-09-24T09:00:00.000Z"),
            search_block("commented-bullet", "bulleted_list_item", "COMMENTED-BULLET text",
                         "2026-09-01T09:00:00.000Z"),
            search_block("quiet-bullet", "bulleted_list_item", "QUIET-BULLET text",
                         "2026-09-01T09:00:00.000Z"),
        ],
        "covered-child": [search_block("covered-paragraph", "paragraph", "SENSITIVE-MARKER detail",
                                       "2026-09-22T09:00:00.000Z")],
    }

    # Asked by page id, Notion also returns the comment anchored to a block; it
    # must print once, under that block.
    COMMENTS = {
        "commented-bullet": [search_comment("new-comment", "2026-09-24T10:00:00.000Z", "reviewer",
                                            "COMMENT-TEXT")],
        "open-page": [search_comment("old-comment", "2026-09-01T10:00:00.000Z", "reviewer",
                                     "OLD-COMMENT"),
                      search_comment("new-comment", "2026-09-24T10:00:00.000Z", "reviewer",
                                     "COMMENT-TEXT")],
    }

    USERS = {"reviewer": {"object": "user", "id": "reviewer", "name": "Reviewer Name"}}

    # The opt-in pages the reading rules are tried on. call-notes is flat but for
    # an old heading hiding a new bullet, which only a full walk finds, and a new
    # heading whose new child a shallow read still descends to, and a block edited
    # in the watermark's own minute, which a shallow read must still walk.
    # pinned-notes has new blocks at both ends, so a newest-first read shows by
    # what it leaves out.
    CALL_NOTES_RESULTS = [
        search_item("call-notes", "2026-09-23T15:00:00.000Z", "Acme calls",
                    "database_id", "crm-db"),
        search_item("pinned-notes", "2026-09-23T14:00:00.000Z", "Globex calls",
                    "database_id", "crm-db"),
        search_item("candidate", "2026-09-23T13:00:00.000Z", "Candidate notes",
                    "block_id", "recruiting-toggle"),
    ]

    CALL_NOTES_CHILDREN = {
        "call-notes": [
            search_block("old-call", "heading_2", "OLD-CALL", "2026-09-01T09:00:00.000Z",
                         has_children=True),
            search_block("mid-call", "heading_2", "MID-CALL text", "2026-09-23T15:00:00.000Z",
                         has_children=True),
            search_block("new-call", "paragraph", "NEW-CALL text", "2026-09-23T15:00:00.000Z"),
            search_block("minute-call", "paragraph", "MINUTE-CALL text",
                         "2026-09-20T10:30:00.000Z"),
        ],
        "old-call": [search_block("nested-call", "bulleted_list_item", "NESTED-CALL text",
                                  "2026-09-23T15:00:00.000Z")],
        "mid-call": [search_block("mid-detail", "bulleted_list_item", "MID-DETAIL text",
                                  "2026-09-23T15:00:00.000Z")],
        "pinned-notes": [
            search_block("pinned-top", "paragraph", "PINNED-TOP text",
                         "2026-09-23T14:00:00.000Z"),
            search_block("pinned-old", "paragraph", "PINNED-OLD", "2026-09-01T09:00:00.000Z"),
            search_block("pinned-bottom", "paragraph", "PINNED-BOTTOM text",
                         "2026-09-23T14:00:00.000Z"),
        ],
        "candidate": [search_block("candidate-paragraph", "paragraph", "CANDIDATE-MARKER text",
                                   "2026-09-23T13:00:00.000Z")],
    }

    CALL_NOTES_METADATA = {
        **{("pages", item["id"]): item for item in CALL_NOTES_RESULTS},
        ("databases", "crm-db"): search_item("crm-db", "2026-09-01T09:00:00.000Z", "CRM",
                                             kind="database"),
        ("blocks", "recruiting-toggle"): {"object": "block", "id": "recruiting-toggle",
                                          "parent": {"type": "page_id",
                                                     "page_id": "recruiting"}},
        ("pages", "recruiting"): search_item("recruiting", "2026-09-01T09:00:00.000Z",
                                             "Recruiting"),
    }

    # Opt-in results the index showed late: edited inside the 72-hour lookback but
    # before the watermark, one outside every covered location and one under the
    # hub. lagged-page holds the late edit's block and one older than the lookback.
    LAGGED_RESULTS = [
        search_item("lagged-page", "2026-09-19T12:00:00.000Z", "LAGGED-TITLE"),
        search_item("lagged-covered", "2026-09-19T09:00:00.000Z", "LAGGED-PERSON-TITLE",
                    "page_id", "hub"),
    ]

    LAGGED_CHILDREN = {
        "lagged-page": [
            search_block("lagged-block", "paragraph", "LAGGED-BLOCK text",
                         "2026-09-19T12:00:00.000Z"),
            search_block("pre-lookback-block", "paragraph", "PRE-LOOKBACK text",
                         "2026-09-10T09:00:00.000Z"),
        ],
        "lagged-covered": [search_block("lagged-covered-paragraph", "paragraph",
                                        "LAGGED-SENSITIVE-MARKER", "2026-09-19T09:00:00.000Z")],
    }

    METADATA = {
        ("pages", "hub"): search_item("hub", "2026-09-01T09:00:00.000Z", "Operations hub"),
        ("pages", "team"): search_item("team", "2026-09-01T09:00:00.000Z", "Team"),
        ("pages", "team-child"): search_item("team-child", "2026-09-21T09:00:00.000Z",
                                             "Team | notes", "page_id", "team"),
        ("pages", "open-page"): search_item("open-page", "2026-09-24T09:00:00.000Z", "Roadmap"),
        ("pages", "deep-covered"): search_item("deep-covered", "2026-09-23T12:00:00.000Z",
                                               "DEEP-PERSON-TITLE", "block_id", "toggle"),
        ("pages", "covered-row"): search_item("covered-row", "2026-09-23T09:00:00.000Z",
                                              "ROW-TITLE", "database_id", "covered-db"),
        ("pages", "covered-child"): search_item("covered-child", "2026-09-22T09:00:00.000Z",
                                                "Jane PERSON-TITLE", "page_id", "hub"),
        ("blocks", "toggle"): {"object": "block", "id": "toggle",
                               "parent": {"type": "page_id", "page_id": "covered-child"}},
        ("databases", "covered-db"): search_item("covered-db", "2026-09-01T09:00:00.000Z",
                                                 "Rows", "page_id", "hub", kind="database"),
    }

    def __init__(self, restricted=False, search_status=None, failing_comments=(),
                 failing_children=(), call_notes=False, lagged=False, unseen=False,
                 grandchild=False):
        import http.server
        import threading

        stub = self
        self.results = list(self.RESULTS)

        if lagged:
            older = [item["id"] for item in self.results].index("old-page")
            self.results[older:older] = self.LAGGED_RESULTS
            self.CHILDREN = {**self.CHILDREN, **self.LAGGED_CHILDREN}
        self.search_status = search_status
        self.failing_comments = set(failing_comments)
        self.failing_children = set(failing_children)
        self.search_requests = 0
        self.requested = []
        self.commented = []
        self.authorizations = []
        self.first_request_at = None

        if unseen:
            self.METADATA = {key: value for key, value in self.METADATA.items()
                             if key != ("pages", "team")}

        if grandchild:
            self.results.insert(0, self.GRANDCHILD)

        if restricted:
            self.results.insert(4, self.RESTRICTED)
            self.METADATA = {**self.METADATA, ("pages", "restricted-child"): self.RESTRICTED}

        if call_notes:
            self.results[1:1] = self.CALL_NOTES_RESULTS
            self.METADATA = {**self.METADATA, **self.CALL_NOTES_METADATA}
            self.CHILDREN = {**self.CHILDREN, **self.CALL_NOTES_CHILDREN}

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *arguments):
                pass

            def reply(self, status, document):
                body = json.dumps(document).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def record(self):
                from datetime import datetime, timezone

                stub.first_request_at = stub.first_request_at or datetime.now(timezone.utc)
                stub.authorizations.append(self.headers.get("Authorization"))

            def do_GET(self):
                self.record()
                path, _, query = self.path.partition("?")
                parts = tuple(path.strip("/").split("/"))
                stub.requested.append(parts)

                if parts == ("pages", "forbidden"):
                    return self.reply(403, {"object": "error", "code": "restricted_resource",
                                            "message": "LEAKY-ERROR-MESSAGE"})

                if parts in stub.METADATA:
                    return self.reply(200, stub.METADATA[parts])

                if len(parts) == 3 and parts[0] == "blocks" and parts[2] == "children":
                    if parts[1] in stub.failing_children:
                        return self.reply(403, {"object": "error", "code": "restricted_resource",
                                                "message": "LEAKY-ERROR-MESSAGE"})

                    return self.reply(200, {"results": stub.CHILDREN.get(parts[1], []),
                                            "has_more": False})

                if parts == ("comments",):
                    block = dict(pair.split("=") for pair in query.split("&")).get("block_id")
                    stub.commented.append(block)

                    if block in stub.failing_comments:
                        return self.reply(403, {"object": "error", "code": "restricted_resource",
                                                "message": "LEAKY-ERROR-MESSAGE"})

                    return self.reply(200, {"results": stub.COMMENTS.get(block, []),
                                            "has_more": False})

                if parts[0] == "users" and parts[1] in stub.USERS:
                    return self.reply(200, stub.USERS[parts[1]])

                self.reply(404, {"object": "error", "code": "object_not_found",
                                 "message": "LEAKY-ERROR-MESSAGE"})

            def do_POST(self):
                self.record()
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")

                if self.path.strip("/") != "search":
                    return self.reply(404, {"object": "error", "code": "object_not_found"})

                stub.search_requests += 1

                if stub.search_status:
                    return self.reply(stub.search_status, {"object": "error", "code": "unauthorized"})

                start = [item["id"] for item in stub.results].index(body["start_cursor"]) \
                    if body.get("start_cursor") else 0
                page = stub.results[start:start + 2]
                following = stub.results[start + 2:start + 3]
                self.reply(200, {"results": page, "has_more": bool(following),
                                 "next_cursor": following[0]["id"] if following else None})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def api_base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class NotionSweepTest(unittest.TestCase):
    """The notion-sweep adapter against a stub API. The properties pinned: nothing
    under a covered location is written anywhere but as a count, however it is
    nested; pagination runs through a covered item's cursor; the search stops at
    the watermark; and a result that cannot be placed withholds the watermark
    rather than being listed."""

    TOKEN = "Bearer secret-TOKEN-MARKER"
    COVERED = ("PERSON-TITLE", "DEEP-PERSON-TITLE", "ROW-TITLE", "`covered-child`",
               "`deep-covered`", "`covered-row`", "LEAKY-ERROR-MESSAGE", "TOKEN-MARKER")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.output = self.root / "inbox" / "sweep.md"
        self.claude_config = self.root / "claude.json"
        self.claude_config.write_text(json.dumps({"mcpServers": {"notion": {
            "env": {"OPENAPI_MCP_HEADERS": json.dumps({"Authorization": self.TOKEN})},
        }}}))
        self.stub = None
        self.start_stub()

    def tearDown(self):
        self.stub.close()
        self.directory.cleanup()

    def start_stub(self, **options):
        if self.stub:
            self.stub.close()

        self.stub = StubNotionSearch(**options)
        self.write_register({"covered_by": "notion-covered"})

    def write_register(self, exclusion):
        credential = {"claude_config": str(self.claude_config)}
        self.config = write_register(self.root, register(
            notion={"adapter": "notion-sweep", "api_base": self.stub.api_base,
                    "request_interval_seconds": 0, "credential": credential, **exclusion},
            **{"notion-covered": {"adapter": "notion",
                                  "covered_locations": [{"name": "Operations hub", "id": "hub"}]}},
        ))

    def list_for_comments(self, *entries):
        self.write_register({"covered_by": "notion-covered", "comment_pages": list(entries)})

    def write_listing(self, covered, opened):
        """The covered source with both lists, which is where the sweep reads them."""
        credential = {"claude_config": str(self.claude_config)}
        listing = {"covered_locations": covered}

        if opened is not None:
            listing["open_locations"] = opened

        self.config = write_register(self.root, register(
            notion={"adapter": "notion-sweep", "api_base": self.stub.api_base,
                    "request_interval_seconds": 0, "credential": credential,
                    "covered_by": "notion-covered"},
            **{"notion-covered": {"adapter": "notion", **listing}},
        ))

    def sweep(self, watermark=StubNotionSearch.WATERMARK):
        return support.run_script(
            adapter("notion_sweep.py"),
            arguments=[watermark, str(self.output)],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

    def manifest(self):
        return self.output.read_text(encoding="utf-8")

    def assert_nothing_covered_leaked(self, result):
        streams = result.stdout + result.stderr + (self.manifest() if self.output.exists() else "")

        for token in self.COVERED:
            with self.subTest(token=token):
                self.assertNotIn(token, streams)

    def test_items_outside_covered_locations_are_listed_with_titles(self):
        result = self.sweep()

        self.assertEqual(result.returncode, 0)

        for text in ("`open-page`", "Roadmap", "`team-child`", "Team \\| notes"):
            with self.subTest(text=text):
                self.assertIn(text, self.manifest())

    def test_nothing_under_a_covered_location_is_written_but_a_count(self):
        """Directly under it, under a block inside a page under it, and as a row of
        a database under it."""
        result = self.sweep()

        self.assert_nothing_covered_leaked(result)
        self.assertIn("- Operations hub: 3", self.manifest())
        self.assertIn("3 under covered locations", result.stdout)

    def test_pagination_runs_through_a_covered_items_cursor(self):
        self.sweep()

        self.assertIn("`same-minute`", self.manifest())

    def test_the_search_stops_after_the_first_page_past_the_watermark(self):
        self.sweep()

        self.assertEqual(self.stub.search_requests, 4)
        self.assertNotIn("OLD-TITLE", self.manifest())
        self.assertNotIn("NEVER-TITLE", self.manifest())

    def test_an_edit_in_the_watermarks_own_minute_is_included(self):
        self.sweep()

        self.assertIn("`same-minute`", self.manifest())

    def test_the_watermark_is_the_clock_before_the_first_request(self):
        from datetime import datetime

        result = self.sweep()
        printed = re.search(r"New watermark: (\S+)", result.stdout).group(1)

        self.assertLessEqual(datetime.fromisoformat(printed.replace("Z", "+00:00")),
                             self.stub.first_request_at)

    def test_the_token_is_sent_and_written_nowhere(self):
        result = self.sweep()

        self.assertEqual(set(self.stub.authorizations), {self.TOKEN})
        self.assertNotIn("TOKEN-MARKER", result.stdout + result.stderr + self.manifest())

    def test_an_unplaceable_item_is_withheld_and_withholds_the_watermark(self):
        self.start_stub(restricted=True)

        result = self.sweep()

        self.assertEqual(result.returncode, 3)
        self.assertIn("restricted-child could not be placed", result.stderr)
        self.assertNotIn("RESTRICTED-TITLE", self.manifest())
        self.assertNotIn("New watermark", result.stdout)
        self.assert_nothing_covered_leaked(result)

    def test_a_page_whose_ancestor_cannot_be_seen_is_unplaced_and_named_by_id(self):
        """Its parent returns 404 and open locations are listed, so what lies above
        might be a covered location or an open one."""
        self.start_stub(unseen=True)
        self.write_listing([{"name": "Operations hub", "id": "hub"}],
                           [{"name": "Wiki", "id": "open-page"},
                            {"name": "Minutes", "id": "same-minute"}])

        result = self.sweep()

        self.assertEqual(result.returncode, 3)
        self.assertIn("team-child could not be placed", result.stderr)
        self.assertIn("## Unplaced — not read; each is a gap (1)", self.manifest())
        self.assertIn("- `team-child`", self.manifest())
        self.assertNotIn("Team \\| notes", self.manifest())
        self.assertNotIn(("blocks", "team-child", "children"), self.stub.requested)
        self.assertIn("1 unplaced", result.stdout)
        self.assertNotIn("New watermark", result.stdout)

    def test_an_unseen_ancestor_is_the_top_once_every_covered_location_is_fetched(self):
        """Sharing reaches everything beneath a page, so a covered location this
        token can fetch cannot sit above a page it cannot see. Confirmed once."""
        self.start_stub(unseen=True, grandchild=True)

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("`team-child`", self.manifest())
        self.assertIn("`team-grandchild`", self.manifest())
        self.assertNotIn("Unplaced", self.manifest())
        self.assertEqual(self.stub.requested.count(("pages", "hub")), 1)

    def test_an_unseen_ancestor_stays_unplaceable_when_a_covered_location_is_not_fetched(self):
        self.start_stub(unseen=True)
        self.write_listing([{"name": "Operations hub", "id": "hub"},
                            {"name": "Elsewhere", "id": "nowhere"}], None)

        result = self.sweep()

        self.assertEqual(result.returncode, 3)
        self.assertIn("team-child could not be placed", result.stderr)

    def test_listing_the_shared_page_places_what_is_under_it(self):
        self.start_stub(unseen=True)
        self.write_listing([{"name": "Operations hub", "id": "hub"}],
                           [{"name": "Team", "id": "team-child"}, {"name": "Wiki", "id": "open-page"},
                            {"name": "Minutes", "id": "same-minute"}])

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("`team-child`", self.manifest())
        self.assertNotIn("Unplaced", self.manifest())

    def test_an_unseen_ancestor_stalls_nothing_when_no_location_is_listed(self):
        """With nothing listed there is nothing the hidden ancestor could place the
        page under, so it is read like any other."""
        self.start_stub(unseen=True)
        self.write_register({"covered_locations": []})

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| Team \\| notes | `team-child` |", self.manifest())
        self.assertNotIn("Unplaced", self.manifest())

    def test_a_listed_location_below_an_unseen_ancestor_places_the_page(self):
        """The walk meets the listed location before the 404 above it."""
        self.start_stub(unseen=True, grandchild=True)
        self.write_listing([{"name": "Team notes", "id": "team-child"}],
                           [{"name": "Wiki", "id": "open-page"},
                            {"name": "Minutes", "id": "same-minute"}])

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- Team notes: 2", self.manifest())
        self.assertNotIn("team-grandchild", self.manifest())
        self.assertNotIn(("pages", "team"), self.stub.requested)

    def test_with_open_locations_a_page_under_neither_list_is_named_by_id_only(self):
        self.write_listing([{"name": "Operations hub", "id": "hub"}], [{"name": "Team", "id": "team"}])

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| Team \\| notes | `team-child` |", self.manifest())
        self.assertIn("## Under no open location — not read, exported by `notion-covered` (2)",
                      self.manifest())

        for page in ("open-page", "same-minute"):
            with self.subTest(page=page):
                self.assertIn(f"- `{page}`", self.manifest())
                self.assertNotIn(("blocks", page, "children"), self.stub.requested)

        for title in ("Roadmap", "Same minute", "NEW-BULLET"):
            with self.subTest(title=title):
                self.assertNotIn(title, self.manifest() + result.stdout + result.stderr)

        self.assertIn("2 under no open location", result.stdout)
        self.assertIn("- Operations hub: 3", self.manifest())

    def test_an_empty_open_list_reads_nothing(self):
        self.write_listing([{"name": "Operations hub", "id": "hub"}], [])

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Changed (0)", self.manifest())
        self.assertIn("3 under no open location", result.stdout)

    def test_without_open_locations_there_is_no_unlisted_section(self):
        result = self.sweep()

        self.assertNotIn("Under no open location", self.manifest())
        self.assertNotIn("under no open location", result.stdout)

    def test_the_nearest_listed_ancestor_decides(self):
        """An open location under a covered one opens its subtree, and a covered
        location under an open one covers its own."""
        self.write_listing([{"name": "Covered rows", "id": "covered-db"}],
                           [{"name": "Operations hub", "id": "hub"},
                            {"name": "Child", "id": "covered-child"},
                            {"name": "Team", "id": "team"}])

        result = self.sweep()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("`covered-child`", self.manifest())
        self.assertIn("`deep-covered`", self.manifest())
        self.assertNotIn("`covered-row`", self.manifest())
        self.assertIn("- Covered rows: 1", self.manifest())

    def test_an_open_locations_entry_without_a_name_and_an_id_is_refused(self):
        self.write_listing([{"name": "Operations hub", "id": "hub"}], [{"id": "team"}])

        result = self.sweep()

        self.assertEqual(result.returncode, 1)
        self.assertIn('every entry in "open_locations" needs a "name" and an "id"', result.stderr)
        self.assertEqual(self.stub.search_requests, 0)

    def test_an_unreadable_search_withholds_the_watermark(self):
        self.start_stub(search_status=401)

        result = self.sweep()

        self.assertEqual(result.returncode, 3)
        self.assertIn("a search page could not be read", result.stderr)
        self.assertNotIn("New watermark", result.stdout)

    def test_a_manifest_outside_the_intake_directory_is_refused_before_any_request(self):
        self.output = self.root / "sweep.md"

        result = self.sweep()

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the intake directory", result.stderr)
        self.assertEqual(self.stub.search_requests, 0)
        self.assertFalse(self.output.exists())

    def test_outside_the_required_session_no_request_is_made(self):
        document = json.loads(self.config.read_text())
        self.config.write_text(json.dumps({**document,
                                           "session": {"required_variable": SESSION_VARIABLE}}))

        result = self.sweep()

        self.assertEqual(result.returncode, 1)
        self.assertIn(SESSION_VARIABLE, result.stderr)
        self.assertEqual(self.stub.search_requests, 0)
        self.assertEqual(self.stub.authorizations, [])
        self.assertFalse(self.output.exists())

    def test_a_source_naming_no_exclusions_refuses_to_run(self):
        self.write_register({})

        result = self.sweep()

        self.assertEqual(result.returncode, 1)
        self.assertIn("covered_by", result.stderr)
        self.assertEqual(self.stub.search_requests, 0)

    def test_an_explicitly_empty_exclusion_list_is_accepted(self):
        self.write_register({"covered_locations": []})

        result = self.sweep()

        self.assertEqual(result.returncode, 0)
        self.assertIn("Jane PERSON-TITLE", self.manifest())

    def test_every_listed_page_is_read_into_the_output_and_only_counts_reach_stdout(self):
        self.list_for_comments({"name": "Roadmap", "id": "open-page"})

        result = self.sweep()

        self.assertEqual(result.returncode, 0)

        for text in ("## Roadmap — changes since", "NEW-BULLET text", "COMMENT-TEXT"):
            with self.subTest(text=text):
                self.assertIn(text, self.manifest())

        self.assertNotIn("QUIET-BULLET", self.manifest())
        self.assertNotIn("SIGNED-URL-MARKER", self.manifest())
        self.assertIn("3 page(s) read: 2 changed block(s); comments read on 1 page(s) listed "
                      "under comment_pages, 1 new; 0 skipped", result.stdout)

        for text in ("NEW-BULLET", "COMMENT-TEXT", "Roadmap"):
            with self.subTest(stdout=text):
                self.assertNotIn(text, result.stdout + result.stderr)

    def test_a_comment_request_that_fails_withholds_the_watermark(self):
        """It used to read as "no comments", which is the silent loss this pins."""
        self.start_stub(failing_comments={"quiet-bullet"})
        self.list_for_comments({"name": "Roadmap", "id": "open-page"})

        result = self.sweep()

        self.assertEqual(result.returncode, 3)
        self.assertIn("comments on quiet-bullet could not be read", result.stderr)
        self.assertNotIn("New watermark", result.stdout)
        self.assertNotIn("LEAKY-ERROR-MESSAGE", result.stdout + result.stderr + self.manifest())
        self.assertIn("NEW-BULLET text", self.manifest())

    def test_a_page_that_cannot_be_read_is_marked_and_withholds_the_watermark(self):
        self.start_stub(failing_children={"old-heading"})

        result = self.sweep()

        self.assertEqual(result.returncode, 3)
        self.assertIn("page open-page could not be read", result.stderr)
        self.assertIn("## Roadmap — not read", self.manifest())
        self.assertIn("`same-minute`", self.manifest())
        self.assertNotIn("New watermark", result.stdout)

    def test_a_newest_first_page_is_walked_from_the_top_only(self):
        """open-page's first block holds the new bullet; the new image below it is
        past the limit, so it is neither printed nor asked for comments."""
        self.write_register({"covered_by": "notion-covered",
                             "newest_first_pages": [{"name": "Roadmap", "id": "open-page",
                                                     "blocks": 1}],
                             "comment_pages": [{"name": "Roadmap", "id": "open-page"}]})

        result = self.sweep()

        self.assertEqual(result.returncode, 0)
        self.assertIn("NEW-BULLET text", self.manifest())
        self.assertNotIn("*(image: )*", self.manifest())
        self.assertIn("only the first 1 top-level block(s) were walked; 2 older one(s) were not "
                      "read", self.manifest())
        self.assertIn("3 page(s) read: 1 changed block(s); comments read on 1 page(s) listed "
                      "under comment_pages, 1 new", result.stdout)
        self.assertNotIn("new-image", self.stub.commented)

    def test_a_newest_first_entry_without_a_block_count_is_refused(self):
        self.write_register({"covered_by": "notion-covered",
                             "newest_first_pages": [{"name": "Roadmap", "id": "open-page"}]})

        result = self.sweep()

        self.assertEqual(result.returncode, 1)
        self.assertIn("newest_first_pages entry 'Roadmap'", result.stderr)
        self.assertEqual(self.stub.search_requests, 0)

    def sweep_call_notes(self, **rules):
        self.start_stub(call_notes=True)
        self.write_register({"covered_by": "notion-covered", **rules})

        return self.sweep()

    def test_a_shallow_page_walks_only_its_edited_top_level_blocks(self):
        """call-notes is a row of crm-db. Its unchanged heading is asked for neither
        children nor comments, so the new bullet under it goes unseen; the new
        heading is walked into as usual, and the page's own comments still read."""
        result = self.sweep_call_notes(shallow_locations=[{"name": "CRM", "id": "crm-db"}],
                                       comment_pages=[{"name": "CRM", "id": "crm-db"}])

        self.assertEqual(result.returncode, 0)

        for text in ("MID-CALL text", "MID-DETAIL text", "NEW-CALL text"):
            with self.subTest(text=text):
                self.assertIn(text, self.manifest())

        self.assertNotIn("NESTED-CALL", self.manifest())
        self.assertIn("Read shallow: only top-level blocks edited since the watermark were "
                      "walked (3 of 4)", self.manifest())
        self.assertNotIn(("blocks", "old-call", "children"), self.stub.requested)
        self.assertNotIn("old-call", self.stub.commented)
        self.assertIn("mid-detail", self.stub.commented)
        self.assertIn("call-notes", self.stub.commented)

    def test_a_shallow_read_walks_a_block_edited_in_the_watermarks_own_minute(self):
        """The watermark is inclusive at minute granularity, top-level blocks too."""
        self.sweep_call_notes(shallow_locations=[{"name": "CRM", "id": "crm-db"}],
                              comment_pages=[{"name": "CRM", "id": "crm-db"}])

        self.assertIn("MINUTE-CALL text", self.manifest())
        self.assertIn("minute-call", self.stub.commented)

    def test_a_page_read_whole_finds_what_a_shallow_read_does_not(self):
        self.sweep_call_notes()

        self.assertIn("NESTED-CALL text", self.manifest())

    def test_two_shallow_locations_over_one_page_read_it_shallow(self):
        self.sweep_call_notes(shallow_locations=[{"name": "CRM", "id": "crm-db"},
                                                 {"name": "Acme calls", "id": "call-notes"}])

        self.assertIn("walked (3 of 4)", self.manifest())
        self.assertNotIn("NESTED-CALL", self.manifest())

    def test_a_pages_own_newest_first_entry_beats_a_shallow_location(self):
        result = self.sweep_call_notes(
            shallow_locations=[{"name": "CRM", "id": "crm-db"}],
            newest_first_pages=[{"name": "Globex calls", "id": "pinned-notes", "blocks": 1}])

        self.assertEqual(result.returncode, 0)
        self.assertIn("PINNED-TOP text", self.manifest())
        self.assertNotIn("PINNED-BOTTOM", self.manifest())
        self.assertIn("Listed as newest-first", self.manifest())

    def test_a_skipped_page_is_listed_but_walked_by_no_request(self):
        """candidate sits under recruiting through a block; it stays in the
        manifest, is named as skipped, and nothing of it is asked for."""
        result = self.sweep_call_notes(
            skipped_locations=[{"name": "Recruiting", "id": "recruiting"}])

        self.assertEqual(result.returncode, 0)
        self.assertIn("| Candidate notes | `candidate` |", self.manifest())
        self.assertIn("## Skipped — listed, not read (1)", self.manifest())
        self.assertIn("- `candidate`, under Recruiting", self.manifest())
        self.assertNotIn("- Candidate notes", self.manifest())
        self.assertNotIn("CANDIDATE-MARKER", self.manifest())
        self.assertNotIn(("blocks", "candidate", "children"), self.stub.requested)
        self.assertNotIn("candidate", self.stub.commented)
        self.assertIn("; 1 skipped", result.stdout)

    def test_a_skip_does_not_withhold_the_watermark(self):
        result = self.sweep_call_notes(
            skipped_locations=[{"name": "Recruiting", "id": "recruiting"}])

        self.assertEqual(result.returncode, 0)
        self.assertIn("New watermark", result.stdout)
        self.assertNotIn("Gaps", result.stderr)

    def test_a_skip_beats_a_shallow_location_and_a_newest_first_entry(self):
        self.sweep_call_notes(
            skipped_locations=[{"name": "CRM", "id": "crm-db"}],
            shallow_locations=[{"name": "CRM", "id": "crm-db"}],
            newest_first_pages=[{"name": "Globex calls", "id": "pinned-notes", "blocks": 1}])

        self.assertIn("## Skipped — listed, not read (2)", self.manifest())
        self.assertNotIn("PINNED-TOP", self.manifest())
        self.assertNotIn("NEW-CALL", self.manifest())

    def test_a_covered_location_wins_over_every_reading_rule(self):
        """call-notes is covered and sits under, and at, ids the rules name. It is
        counted and nothing more: not listed, read, asked for, or named as skipped."""
        rules = {"skipped_locations": [{"name": "CRM", "id": "crm-db"},
                                       {"name": "Acme", "id": "call-notes"}],
                 "shallow_locations": [{"name": "CRM", "id": "crm-db"},
                                       {"name": "Acme", "id": "call-notes"}]}

        for key, entries in rules.items():
            with self.subTest(rule=key):
                self.start_stub(call_notes=True)
                self.write_register({"covered_locations": [{"name": "Acme covered",
                                                            "id": "call-notes"}],
                                     key: entries})

                result = self.sweep()

                self.assertEqual(result.returncode, 0)
                self.assertIn("- Acme covered: 1", self.manifest())
                self.assertNotIn("`call-notes`", self.manifest())
                self.assertNotIn("Acme calls", self.manifest() + result.stdout + result.stderr)
                self.assertNotIn("CALL text", self.manifest())
                self.assertNotIn(("blocks", "call-notes", "children"), self.stub.requested)
                self.assertNotIn("call-notes", self.stub.commented)

    def test_the_reading_rules_fetch_no_ancestor_the_placement_fetched(self):
        self.sweep_call_notes(
            skipped_locations=[{"name": "Recruiting", "id": "recruiting"}],
            shallow_locations=[{"name": "CRM", "id": "crm-db"}])

        for ancestor in (("databases", "crm-db"), ("blocks", "recruiting-toggle"),
                         ("pages", "recruiting")):
            with self.subTest(ancestor=ancestor):
                self.assertEqual(self.stub.requested.count(ancestor), 1)

    def assert_refused(self, key, entry, label):
        self.write_register({"covered_by": "notion-covered", key: [entry]})

        result = self.sweep()

        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{key} entry {label!r}", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.stub.search_requests, 0)

    def test_a_location_entry_without_a_name_and_a_string_id_is_refused(self):
        for key in ("skipped_locations", "shallow_locations"):
            for entry, label in (({"name": "X"}, "X"), ({"name": "X", "id": 123}, "X"),
                                 ({"id": "crm-db"}, "crm-db")):
                with self.subTest(key=key, entry=entry):
                    self.assert_refused(key, entry, label)

    def test_a_newest_first_entry_with_a_non_string_id_is_refused(self):
        self.assert_refused("newest_first_pages", {"name": "X", "id": 123, "blocks": 1}, "X")

    def test_a_comment_pages_entry_without_a_name_and_an_id_is_refused(self):
        self.assert_refused("comment_pages", {"id": "open-page"}, "open-page")

    def test_an_unlisted_page_makes_no_comment_request(self):
        """No comment_pages at all: every page is walked, and none asked for
        comments, per block or as a page, so no author is looked up either."""
        result = self.sweep()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.stub.commented, [])
        self.assertFalse([path for path in self.stub.requested if path[0] == "users"])
        self.assertIn("NEW-BULLET text", self.manifest())
        self.assertNotIn("COMMENT-TEXT", self.manifest())
        self.assertIn("*2 changed block(s).* Comments not read: the page is not listed under "
                      "`comment_pages`.", self.manifest())
        self.assertIn("comments read on 0 page(s) listed under comment_pages, 0 new",
                      result.stdout)

    def test_a_listed_page_is_asked_for_comments_per_block_and_as_a_page(self):
        self.list_for_comments({"name": "Roadmap", "id": "open-page"})

        self.sweep()

        for block in ("open-page", "old-heading", "commented-bullet", "quiet-bullet",
                      "new-image"):
            with self.subTest(block=block):
                self.assertIn(block, self.stub.commented)

        self.assertNotIn("same-minute", self.stub.commented)
        self.assertIn("COMMENT-TEXT", self.manifest())

    def test_a_page_under_a_listed_parent_is_asked_for_comments(self):
        """call-notes and pinned-notes are rows of crm-db; the open page is not."""
        result = self.sweep_call_notes(comment_pages=[{"name": "CRM", "id": "crm-db"}])

        self.assertEqual(result.returncode, 0)

        for block in ("call-notes", "old-call", "nested-call", "pinned-notes", "pinned-old"):
            with self.subTest(block=block):
                self.assertIn(block, self.stub.commented)

        for block in ("open-page", "commented-bullet"):
            with self.subTest(unlisted=block):
                self.assertNotIn(block, self.stub.commented)

        self.assertIn("comments read on 2 page(s) listed under comment_pages", result.stdout)

    def test_progress_names_each_page_by_id_and_mode_and_never_by_title(self):
        result = self.sweep_call_notes(
            shallow_locations=[{"name": "CRM", "id": "crm-db"}],
            newest_first_pages=[{"name": "Globex calls", "id": "pinned-notes", "blocks": 1}],
            skipped_locations=[{"name": "Recruiting", "id": "recruiting"}],
            comment_pages=[{"name": "Acme calls", "id": "call-notes"}])
        progress = [line for line in result.stderr.splitlines() if line.startswith("page ")]

        self.assertEqual(result.returncode, 0)
        self.assertIn("page 1/6 open-page: full", progress)
        self.assertIn("page 2/6 call-notes: shallow, comments", progress)
        self.assertIn("page 3/6 pinned-notes: newest-first", progress)
        self.assertIn("page 4/6 candidate: skipped", progress)
        self.assertTrue(any(re.fullmatch(r"page 2/6 call-notes: \d+ block\(s\) walked in "
                                         r"\d+\.\d s", line) for line in progress), progress)

        for title in ("Roadmap", "Acme calls", "Globex calls", "Candidate notes", "Same minute",
                      "Team"):
            with self.subTest(title=title):
                self.assertNotIn(title, result.stderr)

    LEDGER = "notes/.notion-ledger"

    def sweep_lagged(self, records=None, **options):
        """A sweep over the lagged results, with a ledger holding `records`."""
        self.start_stub(lagged=True, **options)
        self.write_register({"covered_by": "notion-covered", "ledger": self.LEDGER})

        if records is not None:
            write_ledger(self.root / self.LEDGER, records)

        return self.sweep()

    def test_a_page_the_index_showed_late_is_read_from_the_lookback(self):
        """lagged-page was edited before the watermark, inside the lookback; read
        from the watermark, its edit would print nothing."""
        result = self.sweep_lagged()

        self.assertEqual(result.returncode, 0)
        self.assertIn("`lagged-page`", self.manifest())
        self.assertIn("## LAGGED-TITLE — changes since 2026-09-17T10:30:00Z", self.manifest())
        self.assertIn("LAGGED-BLOCK text", self.manifest())
        self.assertNotIn("PRE-LOOKBACK", self.manifest())

    def test_a_page_the_ledger_holds_at_its_edit_time_is_neither_listed_nor_read(self):
        result = self.sweep_lagged({"lagged-page": ledger_record("2026-09-19T12:00:00.000Z",
                                                                 "2026-09-19T13:00:00Z")})

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("lagged-page", self.manifest())
        self.assertNotIn("LAGGED", self.manifest())
        self.assertNotIn(("blocks", "lagged-page", "children"), self.stub.requested)

    def test_a_record_from_a_run_whose_watermark_was_not_accepted_skips_nothing(self):
        """The record's run printed a watermark later than the one passed, so its
        output was discarded and this run re-covers its window."""
        self.sweep_lagged({"lagged-page": ledger_record("2026-09-19T12:00:00.000Z",
                                                        "2026-09-21T00:00:00Z")})

        self.assertIn("LAGGED-BLOCK text", self.manifest())

    def test_a_page_with_an_older_record_is_read_from_the_minute_after_it(self):
        """open-page was processed at 09-19 00:00 and edited since: whatever came
        after that record is what may be unreported."""
        self.sweep_lagged({"open-page": ledger_record("2026-09-19T00:00:00.000Z",
                                                      "2026-09-19T01:00:00Z")})

        self.assertIn("## Roadmap — changes since 2026-09-19T00:01:00Z", self.manifest())

    def test_the_lookback_counts_nothing_more_under_a_covered_location(self):
        result = self.sweep_lagged()

        self.assertIn("- Operations hub: 3", self.manifest())
        self.assert_nothing_covered_leaked(result)

    def test_a_clean_run_writes_the_ledger_by_id_and_prunes_it(self):
        result = self.sweep_lagged({
            "pruned-page": ledger_record("2026-09-10T09:00:00.000Z", "2026-09-10T10:00:00Z"),
            "kept-page": ledger_record("2026-09-18T09:00:00.000Z", "2026-09-18T10:00:00Z"),
        })
        watermark = re.search(r"New watermark: (\S+)", result.stdout).group(1)
        ledger = json.loads((self.root / self.LEDGER).read_text(encoding="utf-8"))

        self.assertEqual(ledger["lagged-page"], ledger_record("2026-09-19T12:00:00.000Z",
                                                              watermark))
        self.assertIn("open-page", ledger)
        self.assertIn("kept-page", ledger)
        self.assertNotIn("pruned-page", ledger)
        self.assertNotIn("covered-child", ledger)

        for title in ("LAGGED-TITLE", "Roadmap", "Same minute"):
            with self.subTest(title=title):
                self.assertNotIn(title, (self.root / self.LEDGER).read_text(encoding="utf-8"))

    def test_a_gapped_run_writes_no_ledger(self):
        result = self.sweep_lagged(restricted=True)

        self.assertEqual(result.returncode, 3)
        self.assertFalse((self.root / self.LEDGER).exists())

    def test_a_run_without_a_ledger_says_so_once(self):
        result = self.sweep()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr.count('names no "ledger"'), 1)


def ledger_record(edited, watermark):
    return {"last_edited_time": edited, "watermark": watermark}


def write_ledger(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


class NotionAdapterSearchTest(unittest.TestCase):
    """The notion adapter's default discovery, by search, against the search stub.
    The properties pinned: changed pages under a covered location are found by
    search however they are nested, and nothing under the location is walked;
    the same leak rules hold as for the walk; and what the search cannot place
    withholds the watermark."""

    TOKEN = "Bearer secret-TOKEN-MARKER"
    COVERED = ("PERSON-TITLE", "DEEP-PERSON-TITLE", "ROW-TITLE", "SENSITIVE-MARKER",
               "LEAKY-ERROR-MESSAGE", "TOKEN-MARKER")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.output = self.root / "inbox" / "export.md"
        self.raw = self.root / "inbox" / "notion-covered"
        self.claude_config = self.root / "claude.json"
        self.claude_config.write_text(json.dumps({"mcpServers": {"notion": {
            "env": {"OPENAPI_MCP_HEADERS": json.dumps({"Authorization": self.TOKEN})},
        }}}))
        self.stub = None
        self.start_stub()

    def tearDown(self):
        self.stub.close()
        self.directory.cleanup()

    def start_stub(self, source=None, **options):
        if self.stub:
            self.stub.close()

        self.stub = StubNotionSearch(**options)
        self.config = write_register(self.root, register(**{"notion-covered": {
            "adapter": "notion",
            "api_base": self.stub.api_base,
            "request_interval_seconds": 0,
            "credential": {"claude_config": str(self.claude_config)},
            "covered_locations": [{"name": "Operations hub", "id": "hub"}],
            **(source or {}),
        }}))

    def export(self, *extra):
        return support.run_script(
            adapter("notion_export.py"),
            arguments=[StubNotionSearch.WATERMARK, str(self.output), "--source", "notion-covered",
                       *extra],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

    def export_text(self):
        return self.output.read_text(encoding="utf-8")

    def test_changed_pages_under_the_location_are_found_however_nested(self):
        """Directly under it, under a block inside a page under it, and as a row of a
        database under it: the three the sweep counts."""
        result = self.export()

        self.assertEqual(result.returncode, 0)
        self.assertIn("3 changed, found by search", result.stdout)

        for page in ("covered-child", "deep-covered", "covered-row"):
            with self.subTest(page=page):
                self.assertIn(f"### Page `{page}`", self.export_text())

        self.assertIn("SENSITIVE-MARKER", (self.raw / "covered-child.md").read_text(encoding="utf-8"))

    def test_nothing_under_the_location_is_walked(self):
        self.export()

        self.assertNotIn(("blocks", "hub", "children"), self.stub.requested)
        self.assertNotIn(("pages", "team-child"), self.stub.requested)

    def test_content_reaches_only_the_side_files(self):
        result = self.export()
        streams = result.stdout + result.stderr + self.export_text()

        for token in self.COVERED:
            with self.subTest(token=token):
                self.assertNotIn(token, streams)

    def test_a_search_result_that_cannot_be_placed_withholds_the_watermark(self):
        self.start_stub(restricted=True)

        result = self.export()

        self.assertEqual(result.returncode, 3)
        self.assertIn("could not be placed", result.stderr)
        self.assertNotIn("New watermark", result.stdout)

    def test_an_unreadable_search_withholds_the_watermark(self):
        self.start_stub(search_status=401)

        result = self.export()

        self.assertEqual(result.returncode, 3)
        self.assertIn("a search page could not be read", result.stderr)
        self.assertNotIn("New watermark", result.stdout)

    LEDGER = "notes/.notion-ledger"

    def export_lagged(self, records=None, **options):
        """An export over the lagged results, with a ledger holding `records`."""
        self.start_stub(source={"ledger": self.LEDGER}, lagged=True, **options)

        if records is not None:
            write_ledger(self.root / self.LEDGER, records)

        return self.export()

    def test_a_page_the_index_showed_late_is_exported(self):
        """lagged-covered was edited before the watermark, inside the lookback."""
        result = self.export_lagged()

        self.assertEqual(result.returncode, 0)
        self.assertIn("4 changed, found by search", result.stdout)
        self.assertIn("### Page `lagged-covered`", self.export_text())
        self.assertIn("LAGGED-SENSITIVE-MARKER",
                      (self.raw / "lagged-covered.md").read_text(encoding="utf-8"))
        self.assertNotIn("LAGGED-PERSON-TITLE", result.stdout + result.stderr + self.export_text())

    def test_a_page_the_ledger_holds_at_its_edit_time_is_not_exported_again(self):
        result = self.export_lagged({"lagged-covered": ledger_record("2026-09-19T09:00:00.000Z",
                                                                     "2026-09-19T10:00:00Z")})

        self.assertEqual(result.returncode, 0)
        self.assertIn("3 changed, found by search", result.stdout)
        self.assertNotIn("lagged-covered", self.export_text())
        self.assertFalse((self.raw / "lagged-covered.md").exists())

    def test_a_page_the_ledger_holds_at_an_older_edit_time_is_exported(self):
        self.export_lagged({"lagged-covered": ledger_record("2026-09-18T09:00:00.000Z",
                                                            "2026-09-18T10:00:00Z")})

        self.assertIn("### Page `lagged-covered`", self.export_text())

    def test_a_clean_run_writes_the_ledger_and_prunes_what_the_lookback_passed(self):
        result = self.export_lagged({
            "pruned-page": ledger_record("2026-09-10T09:00:00.000Z", "2026-09-10T10:00:00Z"),
        })
        watermark = re.search(r"New watermark: (\S+)", result.stdout).group(1)
        text = (self.root / self.LEDGER).read_text(encoding="utf-8")
        ledger = json.loads(text)

        self.assertEqual(set(ledger), {"lagged-covered", "covered-child", "deep-covered",
                                       "covered-row"})
        self.assertEqual(ledger["lagged-covered"]["watermark"], watermark)

        for token in self.COVERED + ("LAGGED-PERSON-TITLE",):
            with self.subTest(token=token):
                self.assertNotIn(token, text)

    def test_a_gapped_run_writes_no_ledger(self):
        result = self.export_lagged(restricted=True)

        self.assertEqual(result.returncode, 3)
        self.assertFalse((self.root / self.LEDGER).exists())

    def test_a_run_without_a_ledger_says_so_once_and_names_a_path_of_its_own(self):
        result = self.export()

        self.assertEqual(result.stderr.count('names no "ledger"'), 1)
        self.assertIn('"ledger": "notes/.notion-covered-ledger"', result.stderr)

    def test_a_walk_keeps_the_records_the_next_search_skips_by(self):
        """The walk searches from the watermark, but prunes against the lookback
        floor, so lagged-covered's record survives it."""
        record = ledger_record("2026-09-19T09:00:00.000Z", "2026-09-19T10:00:00Z")
        self.start_stub(source={"ledger": self.LEDGER}, lagged=True)
        write_ledger(self.root / self.LEDGER, {"lagged-covered": record})

        walked = self.export("--walk")
        ledger = json.loads((self.root / self.LEDGER).read_text(encoding="utf-8"))
        shutil.rmtree(self.raw)
        searched = self.export()

        self.assertEqual(walked.returncode, 0)
        self.assertEqual(ledger["lagged-covered"], record)
        self.assertEqual(searched.returncode, 0)
        self.assertNotIn("lagged-covered", self.export_text())

    def test_a_malformed_record_is_read_as_absent_with_one_warning(self):
        result = self.export_lagged({
            "lagged-covered": {"last_edited_time": None, "watermark": 123},
            "covered-child": "not a record",
            "covered-row": ledger_record("2026-09-23T09:00:00.000Z", "no timezone"),
        })

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr.count("ignoring 3 malformed record(s)"), 1)
        self.assertIn("### Page `lagged-covered`", self.export_text())
        self.assertNotIn("Traceback", result.stderr)

    def test_with_open_locations_a_page_under_neither_list_is_exported(self):
        """The sweep names it by id and reads none of it; this is its route to the
        isolated agent, through the same side file a covered page takes."""
        self.start_stub(source={"open_locations": [{"name": "Team", "id": "team"}]})

        result = self.export()
        text = self.export_text()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Under no listed location", text)

        for page in ("open-page", "same-minute"):
            with self.subTest(page=page):
                self.assertIn(f"### Page `{page}`", text)
                self.assertTrue((self.raw / f"{page}.md").is_file())

        self.assertNotIn("team-child", text)
        self.assertNotIn("Roadmap", text + result.stdout + result.stderr)
        self.assertIn("Roadmap", (self.raw / "open-page.md").read_text(encoding="utf-8"))

    def test_a_walk_finds_the_pages_under_neither_list_by_search(self):
        self.start_stub(source={"open_locations": [{"name": "Team", "id": "team"}]})

        result = self.export("--walk")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("### Page `open-page`", self.export_text())
        self.assertTrue((self.raw / "open-page.md").is_file())

    def test_a_source_with_only_open_locations_is_accepted(self):
        self.start_stub(source={"covered_locations": [],
                                "open_locations": [{"name": "Team", "id": "team"}]})

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("### Page `covered-child`", self.export_text())

    def test_an_index_lag_that_is_not_a_number_of_hours_is_refused(self):
        self.start_stub(source={"index_lag_hours": "three days"})

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("index_lag_hours", result.stderr)
        self.assertEqual(self.stub.search_requests, 0)


class NotionPageChangesTest(unittest.TestCase):
    """The page-changes tool against the search stub. The properties pinned: only
    edited blocks print, with unchanged ancestors as marked context; comments left
    since the watermark print under their block, on an unchanged block too; a file
    URL never prints; and a page under a covered location, or one that cannot be
    placed, is refused before anything of it is printed."""

    TOKEN = "Bearer secret-TOKEN-MARKER"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.claude_config = self.root / "claude.json"
        self.claude_config.write_text(json.dumps({"mcpServers": {"notion": {
            "env": {"OPENAPI_MCP_HEADERS": json.dumps({"Authorization": self.TOKEN})},
        }}}))
        self.stub = None
        self.start_stub()

    def tearDown(self):
        self.stub.close()
        self.directory.cleanup()

    def start_stub(self, rules=None, listing=None, **options):
        if self.stub:
            self.stub.close()

        self.stub = StubNotionSearch(**options)
        credential = {"claude_config": str(self.claude_config)}
        self.config = write_register(self.root, register(
            notion={"adapter": "notion-sweep", "api_base": self.stub.api_base,
                    "request_interval_seconds": 0, "credential": credential,
                    "covered_by": "notion-covered", **(rules or {})},
            **{"notion-covered": {"adapter": "notion",
                                  "covered_locations": [{"name": "Operations hub", "id": "hub"}],
                                  **(listing or {})}},
        ))

    def list_for_comments(self, **options):
        self.start_stub(rules={"comment_pages": [{"name": "Roadmap", "id": "open-page"}]},
                        **options)

    def changes(self, page_id):
        return support.run_script(
            adapter("notion_page_changes.py"),
            arguments=[page_id, StubNotionSearch.WATERMARK],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

    def test_only_edited_blocks_print_and_ancestors_are_marked_context(self):
        self.list_for_comments()

        result = self.changes("open-page")

        self.assertEqual(result.returncode, 0)
        self.assertIn("NEW-BULLET text", result.stdout)
        self.assertIn("#### Agenda *(unchanged, for context)*", result.stdout)
        self.assertNotIn("QUIET-BULLET", result.stdout)
        self.assertIn("2 changed block(s), 1 comment(s)", result.stdout)

    def test_a_comment_prints_under_its_block_even_when_the_block_is_unchanged(self):
        self.list_for_comments()

        result = self.changes("open-page")

        self.assertIn("COMMENTED-BULLET text *(unchanged, for context)*", result.stdout)
        self.assertIn("Reviewer Name", result.stdout)
        self.assertIn("COMMENT-TEXT", result.stdout)
        self.assertEqual(result.stdout.count("COMMENT-TEXT"), 1)
        self.assertNotIn("OLD-COMMENT", result.stdout)

    def test_a_file_url_never_prints(self):
        result = self.changes("open-page")

        self.assertIn("*(image: )*", result.stdout)
        self.assertNotIn("SIGNED-URL-MARKER", result.stdout)

    def test_a_page_under_a_covered_location_is_refused_with_nothing_printed(self):
        result = self.changes("covered-child")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("covered location 'Operations hub'", result.stderr)
        self.assertNotIn("SENSITIVE-MARKER", result.stderr)
        self.assertNotIn("PERSON-TITLE", result.stderr)

    def test_a_page_that_cannot_be_placed_is_refused(self):
        self.start_stub(restricted=True)

        result = self.changes("restricted-child")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("could not be placed", result.stderr)
        self.assertNotIn("RESTRICTED-TITLE", result.stderr)

    def test_a_page_whose_ancestor_cannot_be_seen_is_refused(self):
        self.start_stub(unseen=True, listing={"open_locations": [{"name": "Wiki",
                                                                   "id": "open-page"}]})

        result = self.changes("team-child")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("could not be placed", result.stderr)

    def test_with_open_locations_a_page_under_none_is_refused(self):
        self.start_stub(listing={"open_locations": [{"name": "Team", "id": "team"}]})

        result = self.changes("open-page")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("under no open location", result.stderr)

    def test_with_open_locations_a_page_under_one_is_printed(self):
        self.start_stub(listing={"open_locations": [{"name": "Roadmap", "id": "open-page"}]})

        result = self.changes("open-page")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NEW-BULLET", result.stdout)

    def test_the_token_is_sent_and_printed_nowhere(self):
        result = self.changes("open-page")

        self.assertEqual(set(self.stub.authorizations), {self.TOKEN})
        self.assertNotIn("TOKEN-MARKER", result.stdout + result.stderr)

    def test_a_comment_request_that_fails_is_a_gap_not_an_empty_list(self):
        self.list_for_comments(failing_comments={"commented-bullet"})

        result = self.changes("open-page")

        self.assertEqual(result.returncode, 3)
        self.assertIn("NEW-BULLET text", result.stdout)
        self.assertIn("comments on commented-bullet could not be read", result.stderr)
        self.assertNotIn("LEAKY-ERROR-MESSAGE", result.stdout + result.stderr)

    def test_a_page_under_a_shallow_location_is_read_shallow(self):
        self.start_stub(rules={"shallow_locations": [{"name": "CRM", "id": "crm-db"}]},
                        call_notes=True)

        result = self.changes("call-notes")

        self.assertEqual(result.returncode, 0)
        self.assertIn("NEW-CALL text", result.stdout)
        self.assertNotIn("NESTED-CALL", result.stdout)
        self.assertIn("Read shallow", result.stdout)

    def test_an_unlisted_page_makes_no_comment_request_and_says_so(self):
        result = self.changes("open-page")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.stub.commented, [])
        self.assertNotIn("COMMENT-TEXT", result.stdout)
        self.assertIn("*2 changed block(s).* Comments not read: the page is not listed under "
                      "`comment_pages`.", result.stdout)

    def test_a_page_under_a_listed_parent_is_asked_for_comments(self):
        self.start_stub(rules={"comment_pages": [{"name": "CRM", "id": "crm-db"}]},
                        call_notes=True)

        result = self.changes("call-notes")

        self.assertEqual(result.returncode, 0)

        for block in ("call-notes", "old-call", "nested-call"):
            with self.subTest(block=block):
                self.assertIn(block, self.stub.commented)

        self.assertIn("comment(s).*", result.stdout)

    def test_a_page_asked_for_by_hand_is_read_under_a_skipped_location(self):
        self.start_stub(rules={"skipped_locations": [{"name": "Recruiting", "id": "recruiting"}]},
                        call_notes=True)

        result = self.changes("candidate")

        self.assertEqual(result.returncode, 0)
        self.assertIn("CANDIDATE-MARKER text", result.stdout)



def fathom_time(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def fathom_meeting(identifier, created, title, summary, invitees, action_items=None):
    return {
        "recording_id": identifier,
        "title": title,
        "meeting_title": title,
        "created_at": fathom_time(created),
        "recording_start_time": fathom_time(created),
        "calendar_invitees": [{"name": name, "email": email,
                               "email_domain": email.split("@")[1], "is_external": True}
                              for name, email in invitees],
        "default_summary": None if summary is None else {"template_name": "General",
                                                         "markdown_formatted": summary},
        "action_items": [] if action_items is None else action_items,
    }


def transcript_line(speaker, text):
    return {"speaker": {"display_name": speaker, "matched_calendar_invitee_email":
                        "SPEAKER-EMAIL@customer.example"},
            "text": text, "timestamp": "00:00:07"}


TRANSCRIPTS = {
    "101": [transcript_line("Pat Speaker", "TRANSCRIPT-WORD um so we"),
            transcript_line("Pat Speaker", "decided Tuesday, maybe."),
            transcript_line(None, "UNNAMED-WORD question?"),
            transcript_line("Pat Speaker", "Yes.")],
    "104": [transcript_line("Lee Speaker", "LEDGERED-WORD")],
    "102": [transcript_line("Excluded Speaker", "EXCLUDED-WORD")],
}


class StubFathom:
    """A local stand-in for Fathom's `GET /meetings`, serving two cursor pages, and
    `GET /recordings/{id}/transcript`.

    page 1: 101 ready     a summary, a person-shaped title, a customer's invitee
            102 excluded  an invitee at a subdomain of an excluded domain
    page 2: 103 not ready no summary yet
            104 ledgered  the tests' ledger holds it

    `broken` adds 105, whose action items the renderer cannot read; `failing_cursor`
    answers the second page with that status; `rate_limited` answers the first
    request with a 429; `transcript_statuses` answers a recording's transcript with
    that status, and `transcripts` replaces the served transcripts; `held_transcript`
    names a recording whose transcript request is held open until the stub closes.
    """

    WATERMARK_TIME = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=1)
    WATERMARK = fathom_time(WATERMARK_TIME)

    def __init__(self, broken=False, failing_cursor=None, rate_limited=False,
                 transcript_statuses=None, transcripts=None, held_transcript=None):
        import http.server
        import threading
        import urllib.parse

        stub = self
        created = self.WATERMARK_TIME + timedelta(hours=2)
        first_page = [
            fathom_meeting(101, created, "Jane PERSON-TITLE", "SUMMARY-MARKER decided",
                           [("Jane Member", "jane.MEMBER-EMAIL@customer.example")],
                           [{"description": "ACTION-MARKER follow up",
                             "assignee": {"name": "Colleague", "email": "c@us.example"},
                             "completed": False}]),
            fathom_meeting(102, created, "EXCLUDED-TITLE", "EXCLUDED-SUMMARY",
                           [("Someone", "someone@Mail.FORBIDDEN.example")]),
        ]
        second_page = [
            fathom_meeting(103, created, "NOT-READY-TITLE", None, []),
            fathom_meeting(104, created, "LEDGERED-TITLE", "LEDGERED-SUMMARY", []),
        ]

        if broken:
            second_page.append(fathom_meeting(105, created + timedelta(hours=1), "Broken",
                                              "BROKEN-SUMMARY", [], action_items=5))

        self.pages = {None: (first_page, "page-2"), "page-2": (second_page, None)}
        self.queries = []
        self.transcript_requests = []
        self.transcripts = TRANSCRIPTS if transcripts is None else transcripts
        self.transcript_statuses = transcript_statuses or {}
        self.held_transcript = held_transcript
        self.holding = threading.Event()
        self.release = threading.Event()
        self.api_keys = []
        self.first_request_at = None
        self.rate_limited = rate_limited

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *arguments):
                pass

            def reply(self, status, document):
                body = json.dumps(document).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "0")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                stub.first_request_at = stub.first_request_at or datetime.now(timezone.utc)
                stub.api_keys.append(self.headers.get("X-Api-Key"))
                path, _, query = self.path.partition("?")
                transcript = re.fullmatch(r"/recordings/([^/]+)/transcript", path)

                if transcript:
                    return self.serve_transcript(transcript.group(1), query)

                parameters = dict(urllib.parse.parse_qsl(query))
                stub.queries.append(parameters)

                if stub.rate_limited:
                    stub.rate_limited = False
                    return self.reply(429, {"error": "LEAKY-ERROR-MESSAGE"})

                cursor = parameters.get("cursor")

                if path != "/meetings" or cursor not in stub.pages:
                    return self.reply(404, {"error": "LEAKY-ERROR-MESSAGE"})

                if cursor and failing_cursor:
                    return self.reply(failing_cursor, {"error": "LEAKY-ERROR-MESSAGE"})

                items, next_cursor = stub.pages[cursor]
                self.reply(200, {"items": items, "next_cursor": next_cursor, "limit": 10})

            def serve_transcript(self, identifier, query):
                stub.transcript_requests.append((identifier, query))

                if identifier == stub.held_transcript:
                    stub.holding.set()
                    stub.release.wait(timeout=60)

                if identifier in stub.transcript_statuses:
                    return self.reply(stub.transcript_statuses[identifier],
                                      {"error": "LEAKY-ERROR-MESSAGE"})

                if identifier not in stub.transcripts:
                    return self.reply(404, {"error": "LEAKY-ERROR-MESSAGE"})

                self.reply(200, {"transcript": stub.transcripts[identifier]})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def api_base(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


class FathomAdapterTest(unittest.TestCase):
    """The fathom adapter against a stub API. Pinned: a meeting's title, summary,
    action items, invitees and transcript reach only its meeting file, which opens
    with its title; a meeting with an excluded invitee reaches nothing at
    all and has no transcript requested; the listing looks back from the watermark
    and the ledger keeps the overlap from being exported twice; a summary not yet
    written is retried rather than recorded; a transcript that is absent is noted
    while one that cannot be read takes the export back; a meeting directory in a
    git work tree must be ignored there; and without the meeting-file flag nothing
    of a meeting is written and nothing advances."""

    KEY = "secret-KEY-MARKER"
    CONTENT = ("PERSON-TITLE", "SUMMARY-MARKER", "ACTION-MARKER", "MEMBER-EMAIL", "Jane",
               "EXCLUDED-TITLE", "EXCLUDED-SUMMARY", "NOT-READY-TITLE", "LEDGERED-TITLE",
               "LEAKY-ERROR-MESSAGE", "KEY-MARKER", "TRANSCRIPT-WORD", "UNNAMED-WORD",
               "LEDGERED-WORD", "Pat Speaker", "Lee Speaker", "SPEAKER-EMAIL")
    EXCLUDED = ("EXCLUDED-TITLE", "EXCLUDED-SUMMARY", "someone@", "forbidden",
                "EXCLUDED-WORD", "Excluded Speaker")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.output = self.root / "inbox" / "export.md"
        self.raw = self.root / "inbox" / "fathom"
        self.ledger = self.root / "notes" / ".fathom-ledger"
        self.key_file = self.root / "api-key"
        self.write_key(self.KEY)
        self.stub = None
        self.start_stub()

    def tearDown(self):
        self.stub.close()
        self.directory.cleanup()

    def write_key(self, value, mode=0o600):
        self.key_file.write_text(value + "\n", encoding="utf-8")
        self.key_file.chmod(mode)

    def start_stub(self, source=None, **options):
        if self.stub:
            self.stub.close()

        self.stub = StubFathom(**options)
        entry = {
            "adapter": "fathom",
            "api_base": self.stub.api_base,
            "request_interval_seconds": 0,
            "credential": {"key_file": str(self.key_file)},
            "ledger": "notes/.fathom-ledger",
            "lookback_hours": 72,
            "excluded_invitee_domains": ["forbidden.EXAMPLE"],
            "transcripts": True,
            "retry_wait_seconds": 0,
        }
        entry.update(source or {})
        self.config = write_register(self.root, register(fathom={
            key: value for key, value in entry.items() if value is not None}))

    def write_ledger_record(self, watermark):
        created = fathom_time(StubFathom.WATERMARK_TIME + timedelta(hours=2))
        write_ledger(self.ledger, {"104": {"created_at": created, "watermark": watermark}})

    def export(self, *extra, watermark=StubFathom.WATERMARK, **environment):
        return support.run_script(
            adapter("fathom_export.py"),
            arguments=[watermark, str(self.output), *extra],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
            **environment,
        )

    def written_files(self):
        return [path for path in self.root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(self.root).parts]

    def everything_written(self, result):
        return result.stdout + result.stderr + "".join(
            path.read_text(encoding="utf-8") for path in self.written_files()
            if path != self.config)

    def test_every_page_is_read_along_the_cursor(self):
        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([query.get("cursor") for query in self.stub.queries], [None, "page-2"])
        self.assertIn("4 meeting(s) listed", result.stdout)
        self.assertIn("1 summary not ready", result.stdout)

    def test_the_listing_looks_back_from_the_watermark_and_asks_for_no_transcript(self):
        self.export()
        floor = StubFathom.WATERMARK_TIME.replace(second=0) - timedelta(hours=72)

        for query in self.stub.queries:
            with self.subTest(query=query):
                self.assertEqual(query["created_after"], fathom_time(floor))
                self.assertEqual(query["include_summary"], "true")
                self.assertEqual(query["include_action_items"], "true")
                self.assertNotIn("include_transcript", query)

    def test_a_meeting_with_an_excluded_invitee_is_written_nowhere(self):
        result = self.export()
        written = self.everything_written(result)

        self.assertIn("1 skipped by invitee domain", result.stdout)

        for marker in self.EXCLUDED:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, written)

        self.assertFalse((self.raw / "fathom-102.md").exists())
        self.assertNotIn("`102`", self.output.read_text(encoding="utf-8"))

    def test_a_ready_meeting_reaches_only_its_side_file(self):
        result = self.export()
        side_file = (self.raw / "fathom-101.md").read_text(encoding="utf-8")
        export = self.output.read_text(encoding="utf-8")

        for marker in ("PERSON-TITLE", "SUMMARY-MARKER", "ACTION-MARKER"):
            with self.subTest(marker=marker):
                self.assertIn(marker, side_file)
                self.assertNotIn(marker, export)
                self.assertNotIn(marker, result.stdout + result.stderr)

        self.assertIn("customer.example", side_file)
        self.assertNotIn("MEMBER-EMAIL", side_file)
        self.assertIn(str(self.raw / "fathom-101.md"), export)
        self.assertIn("`101`", export)

    def test_no_output_stream_carries_a_title_a_summary_an_address_or_the_key(self):
        result = self.export()
        streams = result.stdout + result.stderr + self.output.read_text(encoding="utf-8")

        for marker in self.CONTENT:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, streams)

    def test_a_ledgered_meeting_is_not_exported_again(self):
        self.write_ledger_record(fathom_time(StubFathom.WATERMARK_TIME - timedelta(hours=1)))

        result = self.export()

        self.assertIn("1 already in the ledger", result.stdout)
        self.assertFalse((self.raw / "fathom-104.md").exists())
        self.assertNotIn("104", self.transcript_ids())

    def test_a_record_from_a_run_whose_watermark_was_not_accepted_skips_nothing(self):
        self.write_ledger_record(fathom_time(StubFathom.WATERMARK_TIME + timedelta(hours=1)))

        result = self.export()

        self.assertIn("0 already in the ledger", result.stdout)
        self.assertTrue((self.raw / "fathom-104.md").exists())

    def test_a_meeting_without_a_summary_is_retried_rather_than_recorded(self):
        result = self.export()
        records = json.loads(self.ledger.read_text(encoding="utf-8"))

        self.assertEqual(sorted(records), ["101", "104"])
        self.assertFalse((self.raw / "fathom-103.md").exists())
        self.assertIn("lookback: 103", result.stdout)

    def test_count_only_writes_nothing_and_advances_nothing(self):
        self.write_ledger_record(fathom_time(StubFathom.WATERMARK_TIME - timedelta(hours=1)))
        before = self.ledger.read_bytes()

        result = self.export("--count-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.raw.exists())
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertNotIn("New watermark", result.stdout)
        self.assertIn("listed only", result.stdout)
        self.assertNotIn("SUMMARY-MARKER", self.output.read_text(encoding="utf-8"))

    def test_the_watermark_is_the_clock_before_the_first_request(self):
        result = self.export()
        printed = re.search(r"New watermark: (\S+)", result.stdout).group(1)

        self.assertLessEqual(datetime.fromisoformat(printed.replace("Z", "+00:00")),
                             self.stub.first_request_at)

    def test_a_rate_limit_is_retried(self):
        self.start_stub(rate_limited=True)

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.stub.queries), 3)

    def test_an_unreadable_page_withholds_the_watermark_and_the_ledger(self):
        self.start_stub(failing_cursor=403)

        result = self.export()

        self.assertEqual(result.returncode, 3)
        self.assertIn("GET /meetings returned 403", result.stderr)
        self.assertNotIn("New watermark", result.stdout)
        self.assertFalse(self.ledger.exists())
        self.assertNotIn("LEAKY-ERROR-MESSAGE", result.stdout + result.stderr)

    def test_a_failure_part_way_removes_the_side_files_it_wrote(self):
        self.start_stub(broken=True)

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("failed part-way", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(list(self.raw.glob("*.md")), [])
        self.assertFalse(self.output.exists())

    def transcript_ids(self):
        return [identifier for identifier, _ in self.stub.transcript_requests]

    def meeting_file(self, identifier):
        return (self.raw / f"fathom-{identifier}.md").read_text(encoding="utf-8")

    def test_a_transcript_is_rendered_as_merged_speaker_turns(self):
        result = self.export()
        transcript = self.meeting_file("101").split("## Transcript\n\n", 1)[1]

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(transcript, "Pat Speaker: TRANSCRIPT-WORD um so we decided Tuesday, "
                                     "maybe.\n\nUnknown: UNNAMED-WORD question?\n\n"
                                     "Pat Speaker: Yes.\n")
        self.assertIn(("101", ""), self.stub.transcript_requests)
        self.assertIn("Transcripts: 2 fetched, 0 unavailable", result.stdout)

    def test_a_meeting_file_opens_with_its_title_and_its_sections_in_order(self):
        self.export()
        text = self.meeting_file("101")
        headings = [line for line in text.splitlines() if line.startswith("## ")]

        self.assertTrue(text.startswith("# "))
        self.assertEqual(headings, ["## Summary", "## Action items", "## Transcript"])
        self.assertNotIn("00:00:07", text)
        self.assertNotIn("SPEAKER-EMAIL", text)

    def test_without_transcripts_none_is_requested_or_written(self):
        self.start_stub(source={"transcripts": False})

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stub.transcript_requests, [])
        self.assertNotIn("## Transcript", self.meeting_file("101"))
        self.assertNotIn("Transcripts:", result.stdout)

    def test_a_transcripts_setting_that_is_not_a_boolean_refuses_to_run(self):
        self.start_stub(source={"transcripts": "yes"})

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn('"transcripts"', result.stderr)
        self.assertEqual(self.stub.queries, [])

    def test_an_absent_or_empty_transcript_is_noted_and_the_meeting_still_exported(self):
        self.start_stub(transcript_statuses={"101": 404}, transcripts={"104": []})

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)

        for identifier in ("101", "104"):
            with self.subTest(identifier=identifier):
                self.assertTrue(self.meeting_file(identifier).endswith(
                    "## Transcript\n\nTranscript unavailable.\n"))

        self.assertIn("Transcripts: 0 fetched, 2 unavailable", result.stdout)
        self.assertIn("exported without it: 101, 104", result.stdout)
        self.assertIn("New watermark", result.stdout)
        self.assertEqual(sorted(json.loads(self.ledger.read_text(encoding="utf-8"))),
                         ["101", "104"])

    def test_an_unreadable_transcript_takes_the_export_back(self):
        self.start_stub(transcript_statuses={"104": 500})

        result = self.export()

        self.assertEqual(result.returncode, 3)
        self.assertIn("GET /recordings/104/transcript", result.stderr)
        self.assertIn("status 500", result.stderr)
        self.assertNotIn("New watermark", result.stdout)
        self.assertFalse(self.ledger.exists())
        self.assertEqual(list(self.raw.glob("*.md")), [])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.transcript_ids().count("104"), 7)

        for marker in self.CONTENT:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, result.stdout + result.stderr)

    def test_an_excluded_meeting_has_no_transcript_requested(self):
        self.export()

        self.assertEqual(sorted(self.transcript_ids()), ["101", "104"])

    def test_an_unencodable_character_is_replaced_rather_than_failing_the_run(self):
        self.start_stub(transcripts={"101": [transcript_line("Pat Speaker", "before\ud800after")]})

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Pat Speaker: before?after", self.meeting_file("101"))

    @unittest.skipIf(sys.platform == "win32", "Windows has no SIGTERM to send")
    def test_a_terminated_run_removes_the_meeting_files_it_wrote(self):
        self.start_stub(held_transcript="104")
        process = subprocess.Popen(
            [sys.executable, str(adapter("fathom_export.py")), StubFathom.WATERMARK,
             str(self.output)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=support.environment(KNOWLEDGE_BASE_CONFIG_FILE=str(self.config)))

        self.assertTrue(self.stub.holding.wait(timeout=60))
        self.assertTrue((self.raw / "fathom-101.md").exists())
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=60)

        self.assertEqual(process.returncode, 128 + signal.SIGTERM)
        self.assertEqual(list(self.raw.glob("*.md")), [])
        self.assertFalse(self.output.exists())

    def make_work_tree(self, ignored):
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)
        (self.root / ".gitignore").write_text("inbox/\n" if ignored else "", encoding="utf-8")

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_directory_git_does_not_ignore_is_refused_before_any_request(self):
        self.make_work_tree(ignored=False)

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("must be git-ignored", result.stderr)
        self.assertEqual(self.stub.queries, [])
        self.assertFalse(self.raw.exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_directory_git_ignores_is_accepted(self):
        self.make_work_tree(ignored=True)

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.raw / "fathom-101.md").exists())

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_directory_a_nested_ignore_rule_covers_is_accepted(self):
        self.make_work_tree(ignored=False)
        self.config.write_text(json.dumps({**json.loads(self.config.read_text()),
                                           "layout": {"inbox": "intake"}}))
        intake = self.root / "intake"
        intake.mkdir()
        (intake / ".gitignore").write_text("fathom/\nexport.md\n", encoding="utf-8")
        self.output = intake / "export.md"

        result = self.export()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((intake / "fathom" / "fathom-101.md").exists())

    def test_an_output_outside_the_intake_directory_is_refused_before_any_request(self):
        self.output = self.root / "export.md"

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the intake directory", result.stderr)
        self.assertEqual(self.stub.queries, [])
        self.assertFalse(self.output.exists())

    @unittest.skipIf(os.name == "nt", "Windows has no mode bits")
    def test_what_it_writes_is_its_owners_alone(self):
        self.export()

        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.raw.stat().st_mode), 0o700)

        for path in self.raw.iterdir():
            with self.subTest(path=path.name):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_an_intake_outside_the_knowledge_base_is_refused(self):
        self.config.write_text(json.dumps({**json.loads(self.config.read_text()),
                                           "layout": {"inbox": "../elsewhere"}}))

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the knowledge base", result.stderr)
        self.assertEqual(self.stub.queries, [])

    @unittest.skipIf(shutil.which("git") is None, "needs git")
    def test_a_directory_git_cannot_judge_is_refused(self):
        result = self.export(GIT_DIR=str(self.root / "missing-repository"))

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("git could not confirm", result.stderr)
        self.assertNotIn("fatal", result.stderr)
        self.assertEqual(self.stub.queries, [])
        self.assertFalse(self.raw.exists())

    def test_a_folder_a_previous_run_left_files_in_is_refused_before_any_request(self):
        self.raw.mkdir(parents=True)
        (self.raw / "fathom-099.md").write_text("left over", encoding="utf-8")

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn(str(self.raw), result.stderr)
        self.assertIn("previous run's working files", result.stderr)
        self.assertEqual(self.stub.queries, [])
        self.assertEqual([path.name for path in self.raw.iterdir()], ["fathom-099.md"])

    def test_a_source_listing_no_excluded_domains_refuses_to_run(self):
        self.start_stub(source={"excluded_invitee_domains": None})

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("excluded_invitee_domains", result.stderr)
        self.assertEqual(self.stub.queries, [])

    def test_a_watermark_past_the_lookback_cap_is_refused_before_any_request(self):
        result = self.export(watermark="2020-01-01T00:00:00Z")

        self.assertEqual(result.returncode, 1)
        self.assertIn("max_lookback_days", result.stderr)
        self.assertEqual(self.stub.queries, [])

    def test_the_environment_key_wins_over_the_file(self):
        self.export(FATHOM_API_KEY="environment-KEY-MARKER")

        self.assertEqual(set(self.stub.api_keys), {"environment-KEY-MARKER"})

    def test_the_file_key_is_sent_and_written_nowhere(self):
        result = self.export()

        self.assertEqual(set(self.stub.api_keys), {self.KEY})
        self.assertNotIn("KEY-MARKER", self.everything_written(result).replace(
            self.key_file.read_text(encoding="utf-8"), ""))

    @unittest.skipIf(sys.platform == "win32", "Windows has no mode bits to check")
    def test_a_key_file_others_can_read_is_refused_without_quoting_it(self):
        self.write_key(self.KEY, mode=0o640)

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("group or other", result.stderr)
        self.assertNotIn("KEY-MARKER", result.stderr + result.stdout)
        self.assertEqual(self.stub.queries, [])

    def test_a_malformed_key_is_refused_without_quoting_it(self):
        result = self.export(FATHOM_API_KEY="secret KEY-MARKER")

        self.assertEqual(result.returncode, 1)
        self.assertIn("malformed", result.stderr)
        self.assertNotIn("KEY-MARKER", result.stderr + result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_missing_key_names_the_variable_and_the_file(self):
        self.key_file.unlink()

        result = self.export()

        self.assertEqual(result.returncode, 1)
        self.assertIn("FATHOM_API_KEY", result.stderr)
        self.assertIn(str(self.key_file), result.stderr)


class FathomKeySetupTest(unittest.TestCase):
    """The step a person runs to store a key: read without echo, written readable by
    its owner alone, and only the path printed."""

    def store(self, key, path):
        directory = support.plugin_root(PLUGIN) / "scripts"
        program = (
            f"import sys; sys.path.insert(0, {str(directory)!r});"
            "import getpass, fathom_credential;"
            f"getpass.getpass = lambda prompt='': {key!r};"
            f"sys.exit(fathom_credential.main(['--key-file', {str(path)!r}]))"
        )

        return subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)

    def test_the_key_is_stored_privately_and_only_the_path_printed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fathom" / "api-key"

            result = self.store("stored-KEY-MARKER", path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(path))
            self.assertNotIn("KEY-MARKER", result.stdout + result.stderr)
            self.assertEqual(path.read_text(encoding="utf-8").strip(), "stored-KEY-MARKER")

            if sys.platform != "win32":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_an_empty_key_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "api-key"

            result = self.store("", path)

            self.assertEqual(result.returncode, 1)
            self.assertFalse(path.exists())

    def test_session_start_names_the_missing_key_and_how_to_store_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(meetings={"adapter": "fathom"}))

            result = support.run_script(support.script(PLUGIN, "provision.py"),
                                        KNOWLEDGE_BASE_CONFIG_FILE=str(path), HOME=directory)
            body = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

            self.assertIn("fathom adapter cannot authenticate", body)
            self.assertIn("FATHOM_API_KEY", body)
            self.assertIn("fathom_credential.py", body)
