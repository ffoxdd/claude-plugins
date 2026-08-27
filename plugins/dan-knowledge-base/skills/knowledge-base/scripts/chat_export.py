#!/usr/bin/env python3
"""Assemble an incremental chat intake file from every conversation you're in.

The `chat` adapter, and the **mechanical half only**: fetch, filter noise, group
by conversation and thread, and report the new watermark. The judgment half — the
personal-data gate, and the structural-facts-only summaries for record-dense
conversations — belongs to an isolated agent that edits the file this produces.
`references/chat-sources.md` explains why the split falls there, and why this
script runs in the main session rather than inside that agent.

Nothing sensitive reaches a session merely from running this. Stdout carries the
output path, the new watermark, and any gaps; raw message text goes to the output
file, and **record-dense conversations' text is never written into that file at
all**. With `--sensitive-raw-directory` their text goes to side files under that
directory instead — local scratch for the isolated agent to read while writing
each section's summary, deleted once the summaries are in place. Without the flag
they are fetched only far enough to advance the watermark.

Three tiers, and only the first needs naming by hand:

  1. conversations listed as `dense_conversations` in the register — summarized,
     never pulled verbatim, because scrubbing text that is mostly per-person
     detail redacts it to nothing
  2. any other private conversation — pulled verbatim, marked scrub-mandatory
  3. everything else — pulled verbatim; the gate is a backstop, since the
     workspace convention says there should be nothing to find

Tier 2 is decided by the platform's own privacy flag, read live, so a newly
created private channel is handled safely with no config change.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import configuration

# The bundled client is a uv PEP-723 script; the automated path runs it through
# `uv run --script` directly rather than the bin/ launcher. Python's subprocess
# execs through CreateProcess on Windows, which appends only `.exe` and so cannot
# run the extensionless shell launcher — but it resolves `uv` as `uv.exe`. The
# launcher stays for the one command a person types by hand, `slack-client login`.
SLACK_CLIENT_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "slack-client"
DEFAULT_INVOCATION = ("uv", "run", "--script", str(SLACK_CLIENT_SCRIPT))
DEFAULT_HISTORY_LIMIT = 1000
DEFAULT_REPLIES_LIMIT = 200

LABELLED_LINK_PATTERN = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")
BARE_LINK_PATTERN = re.compile(r"<(https?://[^|>]+)>")
CHANNEL_REFERENCE_PATTERN = re.compile(r"<#[CG][A-Z0-9]+\|([^>]+)>")

NOISE_SUBTYPES = {
    "channel_join",
    "channel_leave",
    "group_join",
    "group_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "channel_archive",
    "channel_unarchive",
}

# Pleasantries only. "done", "yes", and "yep" are deliberately absent: as a reply
# they can carry the actual answer ("did you deploy it?" / "done"), and dropping
# substance costs more than keeping a little noise. A register may add to this
# set but the defaults are not removable, for that reason.
BARE_ACKNOWLEDGEMENTS = {
    "thanks", "thanks!", "thank you", "ty", "tysm", "np", "ok", "okay", "k",
    "sounds good", "+1", "nice", "great",
    "👍", "🙏", "✅", "🎉", "💯",
}


class ExportError(Exception):
    """A condition that should stop the export rather than write a partial file."""


class Client:
    """The chat CLI this adapter drives, plus the register's limits.

    Held as one object rather than module constants so the settings travel with
    the calls that use them, and so a test can drive a stub command.
    """

    def __init__(self, source):
        override = source.get("client_command")
        self.invocation = [override] if override else list(DEFAULT_INVOCATION)
        self.history_limit = int(source.get("history_limit", DEFAULT_HISTORY_LIMIT))
        self.replies_limit = int(source.get("replies_limit", DEFAULT_REPLIES_LIMIT))

    def run(self, *arguments):
        try:
            completed = subprocess.run(
                [*self.invocation, *arguments], capture_output=True, text=True, check=False
            )

        except OSError as error:
            raise ExportError(f"cannot run {self.invocation[0]!r}: {error}") from error

        if completed.returncode != 0:
            detail = completed.stderr.strip() or "no error output"

            raise ExportError(f"{self.invocation[0]} {' '.join(arguments)} failed: {detail}")

        return completed.stdout

    def memberships(self):
        """Read memberships live, so joining a conversation needs no config change.

        The scope is every conversation the session's user is a member of —
        channels, DMs, and group DMs. Each line is `id<TAB>lock<TAB>name`, where
        `locked` marks a private conversation. A two-field line (an older client)
        degrades to unlocked, leaving the register's named set as the safety net.
        """
        conversations = []

        for line in self.run("memberships").splitlines():
            if line.count("\t") >= 2:
                identifier, lock, name = line.split("\t", 2)
                conversations.append((identifier.strip(), name.strip(), lock.strip() == "locked"))

            elif "\t" in line:
                identifier, name = line.split("\t", 1)
                conversations.append((identifier.strip(), name.strip(), False))

        if not conversations:
            raise ExportError(f"`{self.command} memberships` returned nothing")

        return conversations

    def recent_window(self, identifier):
        """The most recent messages, deliberately unfiltered by the watermark.

        A reply does not bump its parent's `ts`, so asking the API for messages
        after the watermark hides every thread whose parent predates it — and
        hides that thread's new replies with it, permanently, because no later
        sync will have a lower watermark either. Scanning the whole window and
        consulting each parent's `latest_reply` is what makes those replies
        visible, and it costs the same single call.

        That call carries no cursor, so a conversation busier than the limit is
        silently truncated. Returning the at-limit condition lets the caller
        report it rather than lose messages.
        """
        messages = parse_message_lines(
            self.run("history", identifier, "--resolve", "--limit", str(self.history_limit))
        )

        return messages, len(messages) >= self.history_limit

    def thread_replies(self, identifier, thread_timestamp):
        """Replies only — the replies call leads with the thread parent."""
        try:
            output = self.run(
                "replies",
                identifier,
                thread_timestamp,
                "--resolve",
                "--limit",
                str(self.replies_limit),
            )

        except ExportError:
            return None

        return [
            message
            for message in parse_message_lines(output)
            if message.get("ts") != thread_timestamp
        ]


def parse_message_lines(output):
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def is_thread_parent(message):
    """True for a standalone message or a thread's own parent.

    A reply broadcast back to the channel also appears in history; rendering it
    top-level would duplicate it, since replies are emitted under their parent.
    """
    thread_timestamp = message.get("thread_ts")

    return not thread_timestamp or thread_timestamp == message.get("ts")


def split_by_watermark(messages, watermark):
    """Partition the window into newly-posted messages and revived threads.

    A revived thread was posted at or before the watermark but has a reply after
    it — the case a watermark alone cannot detect. Its parent is already
    processed, so only the replies are new.
    """
    posted = []
    revived = []

    for message in messages:
        if not is_thread_parent(message):
            continue

        if float(message["ts"]) > watermark:
            posted.append(message)
            continue

        latest_reply = message.get("latest_reply")

        if latest_reply and float(latest_reply) > watermark:
            revived.append(message)

    posted.sort(key=lambda message: float(message["ts"]))
    revived.sort(key=lambda message: float(message["latest_reply"]))

    return posted, revived


def readable_text(raw_text):
    """Undo the wire encoding so the intake file reads as prose.

    Slack escapes `& < >` as entities and wraps links in angle brackets, so raw
    text carries `&gt;` where a quote marker belongs and `<url|label>` where a
    link belongs. Both survive into notes if not decoded here.
    """
    text = raw_text or ""
    text = CHANNEL_REFERENCE_PATTERN.sub(r"#\1", text)
    text = LABELLED_LINK_PATTERN.sub(r"\2 (\1)", text)
    text = BARE_LINK_PATTERN.sub(r"\1", text)

    return html.unescape(text).strip()


def is_noise(message, acknowledgements):
    if message.get("subtype") in NOISE_SUBTYPES:
        return True

    text = readable_text(message.get("text"))

    if not text and not describe_link_unfurls(message):
        return True

    return text.lower() in acknowledgements


def is_repository_message(message):
    if (message.get("bot_profile") or {}).get("name", "").lower() == "github":
        return True

    return any(
        "github.com" in (attachment.get("title") or "")
        for attachment in message.get("attachments") or []
    )


def summarize_line(raw_text, limit=200):
    """First line only, decoded, truncated on a word boundary.

    A push event carries no title, so it falls back to a field whose remainder is
    a multi-line commit list: only the opening line is the event summary, and
    clipping mid-word reads as corrupted output rather than as elision.
    """
    text = readable_text(raw_text)

    if not text:
        return ""

    text = " ".join(text.splitlines()[0].split())

    if len(text) <= limit:
        return text

    return (text[:limit].rsplit(" ", 1)[0] or text[:limit]) + "…"


def describe_link_unfurls(message):
    """Collapse a repository bot's message to its event line plus number/title/URL.

    A pull-request description lives at `attachments[].text` and runs to thousands
    of characters — routinely more than half an export by volume, and retrievable
    on demand from the repository itself. That field is never read here; this is
    the one place content is deliberately dropped rather than reproduced.

    Number, title, and URL are not separate fields: they arrive packed into
    `attachments[].title` as `<url|#number title>`. A push event carries no
    `title` key at all, so it degrades to its event line.
    """
    if not is_repository_message(message):
        return []

    descriptions = []

    for attachment in message.get("attachments") or []:
        context = summarize_line(attachment.get("pretext"))
        link = LABELLED_LINK_PATTERN.search(attachment.get("title") or "")

        if link:
            url, label = link.group(1), summarize_line(link.group(2))
            descriptions.append(f"{context} — {label} — {url}" if context else f"{label} — {url}")

        elif context or attachment.get("fallback"):
            descriptions.append(context or summarize_line(attachment.get("fallback")))

    return descriptions


def format_timestamp(timestamp):
    moment = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)

    return moment.strftime("%Y-%m-%d %H:%M") + " UTC"


def render_message(message, indent=""):
    author = (
        message.get("user_name")
        or message.get("username")
        or message.get("bot_id")
        or "unknown"
    )
    stamp = f"[{format_timestamp(message['ts'])}]"
    unfurls = describe_link_unfurls(message)

    if unfurls:
        return [f"{indent}- {stamp} **{author}** (description omitted):"] + [
            f"{indent}  - {description}" for description in unfurls
        ]

    text = readable_text(message.get("text")).replace("\n", f"\n{indent}  ")

    return [f"{indent}- {stamp} **{author}**: {text}"]


def write_sensitive_raw_text(directory, name, lines):
    """Write a dense conversation's raw text where only the isolated agent reads it."""
    path = os.path.join(directory, f"{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}.md")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join([f"# {name} — raw text for the isolated agent", ""] + lines))

    return path


def render_message_window(client, identifier, name, posted, revived, watermark, notes,
                          acknowledgements):
    """Render new messages and revived threads, fetching replies as needed."""

    def render_replies(message, only_after=None):
        replies = client.thread_replies(identifier, message["ts"])

        if replies is None:
            notes.append(f"{name}: thread {message['ts']} could not be fetched")

            return []

        rendered = []

        for reply in replies:
            if only_after is not None and float(reply["ts"]) <= only_after:
                continue

            if not is_noise(reply, acknowledgements):
                rendered += render_message(reply, indent="  ")

        return rendered

    lines = []

    for message in posted:
        if is_noise(message, acknowledgements):
            continue

        lines += render_message(message)

        if message.get("reply_count"):
            lines += render_replies(message)

    for message in revived:
        lines += render_message(message)
        lines.append("  *(thread continued — parent above is context, already processed)*")
        lines += render_replies(message, only_after=watermark)

    return lines


def render_conversation(client, identifier, name, watermark, dense_names, acknowledgements,
                        sensitive_raw_directory=None, locked=False):
    """One conversation's section, its highest timestamp, and anything to report."""
    is_dense = name.lower() in dense_names
    watermark = float(watermark)
    window, possibly_truncated = client.recent_window(identifier)
    posted, revived = split_by_watermark(window, watermark)

    notes = []

    # Hitting the limit only means messages were lost if the window failed to
    # reach back past the watermark. An unfiltered fetch on a busy channel is at
    # the limit almost every run, so reporting the limit alone cries wolf.
    oldest_fetched = min((float(message["ts"]) for message in window), default=watermark)

    if possibly_truncated and oldest_fetched > watermark:
        notes.append(
            f"{name} ({identifier}) hit the {client.history_limit}-message fetch limit "
            "before reaching the watermark — messages were missed"
        )

    # `latest_reply` advances the watermark even when a reply is never rendered,
    # so a noise-filtered or unfetchable reply cannot strand the watermark and
    # cause the same thread to be re-reported every sync.
    highest = max(
        [float(message["ts"]) for message in posted]
        + [float(message["latest_reply"]) for message in revived],
        default=0.0,
    )

    lines = [f"## {name} ({identifier})", ""]

    if not posted and not revived:
        return lines + ["No new messages since the watermark.", ""], highest, notes

    if is_dense:
        lines += [
            f"**Record-dense — {len(posted)} new message(s) and replies on "
            f"{len(revived)} earlier thread(s) NOT pulled verbatim.**",
            "Replace this section with a structural-facts-only summary: policy decisions,",
            "mechanics, defect patterns with counts, named business entities. No personal",
            "names, identifiers, or per-person amounts.",
        ]

        if sensitive_raw_directory:
            raw_path = write_sensitive_raw_text(
                sensitive_raw_directory,
                name,
                render_message_window(
                    client, identifier, name, posted, revived, watermark, notes, acknowledgements
                ),
            )
            lines += [
                f"Raw text for this section: `{raw_path}` — local scratch,",
                "deleted once the summary is written.",
            ]

        return lines + [""], highest, notes

    if locked:
        lines += [
            "**🔒 Private conversation — personal data is permitted here.** Isolated agent:",
            "scrub this section before release; if person-level detail dominates, replace it",
            "with a structural-facts-only summary instead.",
            "",
        ]

    lines += render_message_window(
        client, identifier, name, posted, revived, watermark, notes, acknowledgements
    )

    return lines + [""], highest, notes


def build_export(client, watermark, dense_names, acknowledgements, sensitive_raw_directory=None):
    header = [
        f"# Chat export — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Incremental pull since watermark `{watermark}`. Assembled mechanically by the",
        "knowledge-base chat adapter; the personal-data gate and the dense-conversation",
        "summaries are not applied yet.",
        "",
    ]
    body = []
    highest = float(watermark)
    notes = []

    for identifier, name, locked in client.memberships():
        lines, conversation_highest, conversation_notes = render_conversation(
            client, identifier, name, watermark, dense_names, acknowledgements,
            sensitive_raw_directory, locked,
        )
        body += lines
        highest = max(highest, conversation_highest)
        notes += conversation_notes

    return "\n".join(header + body), highest, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="timestamp; pull messages strictly newer than this")
    parser.add_argument("output", help="path to write the intake file to")
    parser.add_argument("--source", default="chat", help="register entry to read (default: chat)")
    parser.add_argument(
        "--sensitive-raw-directory",
        help="write record-dense conversations' raw text here for the isolated agent",
    )
    arguments = parser.parse_args(argv)

    try:
        source = configuration.source(arguments.source)

    except configuration.ConfigurationError as error:
        print(f"chat_export: {error}", file=sys.stderr)

        return 1

    dense_names = {name.lstrip("#").lower() for name in source.get("dense_conversations") or []}
    acknowledgements = BARE_ACKNOWLEDGEMENTS | {
        text.lower() for text in source.get("extra_acknowledgements") or []
    }

    if arguments.sensitive_raw_directory:
        os.makedirs(arguments.sensitive_raw_directory, exist_ok=True)

    try:
        content, highest, notes = build_export(
            Client(source),
            arguments.watermark,
            dense_names,
            acknowledgements,
            arguments.sensitive_raw_directory,
        )

    except ExportError as error:
        print(f"chat_export: {error}", file=sys.stderr)

        return 1

    Path(arguments.output).write_text(content, encoding="utf-8")

    print(arguments.output)
    print(f"New watermark: {highest:.6f}")

    if dense_names and not arguments.sensitive_raw_directory:
        print(
            f"{len(dense_names)} record-dense conversation(s) were fetched only to advance "
            "the watermark; pass --sensitive-raw-directory to have them summarized."
        )

    if notes:
        print("\nGaps to report rather than chase:", file=sys.stderr)

        for note in notes:
            print(f"  - {note}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
