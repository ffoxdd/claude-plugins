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
import re
import subprocess
import sys
import tempfile
import unittest
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

STUB_CHAT_CLIENT = '''#!/usr/bin/env python3
import json, sys
command = sys.argv[1]
if command == "memberships":
    print("C001\\tunlocked\\tgeneral")
    print("C002\\tlocked\\tbilling-ops")
    print("C003\\tlocked\\tengineering")
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
    }
    for message in per[sys.argv[2]]:
        print(json.dumps(message))
elif command == "replies":
    print(json.dumps({"ts": "900.0", "user_name": "cy", "text": "older parent"}))
    print(json.dumps({"ts": "1600.0", "user_name": "cy", "text": "and the follow-up"}))
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


class EmailAdapterInvocationTest(unittest.TestCase):
    def test_a_source_declaring_no_senders_refuses_rather_than_sweeping_everything(self):
        """A whitelist is what makes mail tractable. Without one the adapter would
        have to judge every message for relevance, so it stops instead."""
        with tempfile.TemporaryDirectory() as directory:
            path = write_register(directory, register(email={"adapter": "email"}))

            result = support.run_script(
                adapter("email_sweep.py"),
                arguments=["2026-08-01T00:00:00Z", str(Path(directory) / "out.md")],
                KNOWLEDGE_BASE_CONFIG_FILE=str(path),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("no senders", result.stderr)


class ChatAdapterTest(unittest.TestCase):
    """The chat adapter against a stub client, which is the only way to reach this
    logic without a workspace. What is being pinned is not the stub's content but
    the four properties the design rests on: dense conversations never appear in
    the export, stdout never carries message text, noise is dropped, and a revived
    thread contributes only its new replies."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)

        # The register names the client by path, so the stub has to be invoked the
        # way the platform can: support.stub_command returns that path.
        self.client = support.stub_command(root / "stub-chat", STUB_CHAT_CLIENT)

        self.output = root / "export.md"
        self.raw = root / "raw"
        self.config = write_register(root, register(chat={
            "adapter": "chat",
            "client_command": str(self.client),
            "dense_conversations": ["#billing-ops"],
        }))

    def tearDown(self):
        self.directory.cleanup()

    def export(self, *extra):
        return support.run_script(
            adapter("chat_export.py"),
            arguments=["1000.0", str(self.output), *extra],
            KNOWLEDGE_BASE_CONFIG_FILE=str(self.config),
        )

    def test_a_dense_conversation_never_reaches_the_export(self):
        self.export("--sensitive-raw-directory", str(self.raw))

        self.assertNotIn("SENSITIVE-MARKER", self.output.read_text(encoding="utf-8"))
        self.assertIn("NOT pulled verbatim", self.output.read_text(encoding="utf-8"))

    def test_its_text_goes_to_the_side_file_the_placeholder_names(self):
        self.export("--sensitive-raw-directory", str(self.raw))

        side_files = list(self.raw.glob("*.md"))

        self.assertEqual(len(side_files), 1)
        self.assertIn("SENSITIVE-MARKER", side_files[0].read_text(encoding="utf-8"))
        self.assertIn(side_files[0].name, self.output.read_text(encoding="utf-8"))

    def test_without_the_flag_dense_text_is_written_nowhere(self):
        result = self.export()

        self.assertNotIn("SENSITIVE-MARKER", self.output.read_text(encoding="utf-8"))
        self.assertFalse(self.raw.exists())
        self.assertIn("only to advance the watermark", result.stdout)

    def test_stdout_carries_no_message_text(self):
        """What makes it safe for the main session to run this itself."""
        result = self.export("--sensitive-raw-directory", str(self.raw))

        for token in ("SENSITIVE-MARKER", "shipped the", "the follow-up"):
            with self.subTest(token=token):
                self.assertNotIn(token, result.stdout)

    def test_a_private_conversation_is_marked_scrub_mandatory(self):
        self.export()

        self.assertIn("scrub this section", self.output.read_text(encoding="utf-8"))

    def test_noise_and_bare_acknowledgements_are_dropped(self):
        self.export()
        text = self.output.read_text(encoding="utf-8")

        self.assertNotIn("thanks!", text)
        self.assertNotIn("channel_join", text)

    def test_wire_encoding_is_decoded_into_prose(self):
        self.export()
        text = self.output.read_text(encoding="utf-8")

        self.assertIn("<retry>", text)
        self.assertIn("the doc (https://x.test)", text)
        self.assertIn("#general", text)

    def test_a_revived_thread_contributes_only_its_new_replies(self):
        """A reply does not bump its parent's timestamp, so this is the case a
        watermark alone cannot see — and the parent must not be re-reported as new."""
        self.export()
        text = self.output.read_text(encoding="utf-8")

        self.assertIn("and the follow-up", text)
        self.assertIn("thread continued", text)

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
