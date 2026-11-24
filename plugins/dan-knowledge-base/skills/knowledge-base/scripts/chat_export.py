#!/usr/bin/env python3
"""Assemble an incremental chat intake file from every conversation you're in.

The `chat` adapter, and the **mechanical half only**: fetch, filter noise, group
by conversation and thread, and report the new watermark. The judgment half — the
personal-data gate, and the structural-facts-only summaries for record-dense
conversations — belongs to an isolated agent that edits the file this produces.
`references/chat-sources.md` explains why the split falls there, and why this
script runs in the main session rather than inside that agent.

Nothing sensitive reaches a session merely from running this. Stdout and
stderr carry the output path, counts, the new watermark, and gaps named by
conversation id: never a message, and never a conversation's name, since a
direct message is named for the people in it. Raw message text goes to the
output file, which must lie under the register's intake directory, and
**record-dense conversations' text is never written into that file at all**.
Their text goes to side files under `<intake>/<source name>/` instead —
git-ignored working space for the isolated agent to read while writing each
section's summary, deleted once the summaries are in place. The run is refused
before any request unless the output lies under the intake directory, git
ignores both it and that folder, and the folder is absent or empty (see
`raw_directory.py`). With `--count-only` they are fetched only far enough to
advance the watermark, and nothing of theirs is written.

Three tiers, and only the first needs naming by hand:

  1. conversations listed as `dense_conversations` in the register — summarized,
     never pulled verbatim, because scrubbing text that is mostly per-person
     detail redacts it to nothing
  2. any other private conversation, any direct or group direct message, or one
     whose topic or purpose carries one of the register's
     `private_topic_markers` — pulled verbatim, marked scrub-mandatory
  3. everything else — pulled verbatim; the gate is a backstop, since the
     workspace convention says there should be nothing to find

Tier 2 is decided by the platform's own privacy flag, the conversation's kind,
its topic and its purpose, all read live, so a newly created private or newly
bannered channel is handled safely with no config change.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import configuration
import file_modes
import raw_directory

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


QUIET_SECTION = "No new messages since the watermark."

# The kinds the client reports for a conversation that is not a channel. Neither
# carries the lock a private channel shows, and both are where people speak most
# freely about one another, so both are scrub-mandatory.
DIRECT_KINDS = {"im", "mpim"}


@dataclass(frozen=True)
class Conversation:
    identifier: str
    name: str
    locked: bool
    topic: str
    kind: str = "channel"
    purpose: str = ""

    @property
    def is_direct(self):
        return self.kind in DIRECT_KINDS


@dataclass(frozen=True)
class Handling:
    """The register's designations, which decide each conversation's tier.

    A topic or purpose banner ("this channel may contain personal data") says the
    same thing the private flag does — personal data is permitted here — so it
    earns the same scrub-mandatory handling, and catches a bannered channel that
    was left public. So does a direct or group direct message, which carries no
    lock but is private by nature. None of these says how much of the traffic is
    per-person records, so none makes a conversation dense; only the hand-named
    list does that.
    """
    dense_names: frozenset
    private_topic_markers: tuple

    def is_dense(self, conversation):
        return conversation.name.lower() in self.dense_names

    def is_private(self, conversation):
        banners = f"{conversation.topic}\n{conversation.purpose}".lower()

        return conversation.locked or conversation.is_direct or any(
            marker in banners for marker in self.private_topic_markers
        )


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
        channels, DMs, and group DMs. Each line is
        `id<TAB>lock<TAB>name<TAB>topic<TAB>kind<TAB>purpose`, where `locked` marks
        a private channel and `kind` is `channel`, `im` or `mpim`. A shorter line
        (an older client) degrades to an unlocked channel with no topic or
        purpose, leaving the register's named set as the safety net.
        """
        conversations = [
            conversation
            for conversation in map(parse_membership, self.run("memberships").splitlines())
            if conversation
        ]

        if not conversations:
            raise ExportError("the chat client's `memberships` listed no conversation")

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


def parse_membership(line):
    """One `memberships` line as a Conversation, or None for a line too short to
    name one."""
    fields = [field.strip() for field in line.split("\t")]

    if len(fields) == 2:
        fields = [fields[0], "-", fields[1]]

    if len(fields) < 3:
        return None

    identifier, lock, name, *rest = fields
    topic, kind, purpose = (rest + ["", "", ""])[:3]

    return Conversation(identifier, name, lock == "locked", topic, kind or "channel", purpose)


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


def write_raw_text(directory, name, lines):
    """Write a dense conversation's raw text where only the isolated agent reads it."""
    path = os.path.join(directory, f"{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}.md")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join([f"# {name} — raw text for the isolated agent", ""] + lines))

    return path


def render_message_window(client, identifier, posted, revived, watermark, notes,
                          acknowledgements):
    """Render new messages and revived threads, fetching replies as needed."""

    def render_replies(message, only_after=None):
        replies = client.thread_replies(identifier, message["ts"])

        if replies is None:
            notes.append(f"{identifier}: thread {message['ts']} could not be fetched")

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


def render_conversation(client, conversation, watermark, handling, acknowledgements,
                        raw_text_directory=None):
    """One conversation's section, its highest timestamp, and anything to report."""
    identifier, name = conversation.identifier, conversation.name
    is_dense = handling.is_dense(conversation)
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
            f"{identifier} hit the {client.history_limit}-message fetch limit "
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
        return lines + [QUIET_SECTION, ""], highest, notes

    if is_dense:
        lines += [
            f"**Record-dense — {len(posted)} new message(s) and replies on "
            f"{len(revived)} earlier thread(s) NOT pulled verbatim.**",
            "Replace this section with a structural-facts-only summary: policy decisions,",
            "mechanics, defect patterns with counts, named business entities. No personal",
            "names, identifiers, or per-person amounts.",
        ]

        if raw_text_directory:
            raw_path = write_raw_text(
                raw_text_directory,
                name,
                render_message_window(
                    client, identifier, posted, revived, watermark, notes, acknowledgements
                ),
            )
            lines += [
                f"Raw text for this section: `{raw_path}` — working space,",
                "deleted once the summary is written.",
            ]

        return lines + [""], highest, notes

    if handling.is_private(conversation):
        lines += [
            "**🔒 Private conversation — personal data is permitted here.** Isolated agent:",
            "scrub this section before release; if person-level detail dominates, replace it",
            "with a structural-facts-only summary instead.",
            "",
        ]

    lines += render_message_window(
        client, identifier, posted, revived, watermark, notes, acknowledgements
    )

    return lines + [""], highest, notes


def build_export(client, watermark, handling, acknowledgements, raw_text_directory=None):
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

    for conversation in client.memberships():
        lines, conversation_highest, conversation_notes = render_conversation(
            client, conversation, watermark, handling, acknowledgements, raw_text_directory,
        )
        body += lines
        highest = max(highest, conversation_highest)
        notes += conversation_notes

    return "\n".join(header + body), highest, notes


def active_conversation_count(content):
    """Conversations whose section carries anything but the quiet line. Zero means
    the export holds no message text, so there is nothing for the gate to read."""
    sections = content.split("\n## ")[1:]

    return sum(1 for section in sections if QUIET_SECTION not in section)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="timestamp; pull messages strictly newer than this")
    parser.add_argument("output", help="path to write the intake file to, under the intake "
                                       "directory")
    parser.add_argument("--source", default="chat", help="register entry to read (default: chat)")
    parser.add_argument(
        "--count-only", action="store_true",
        help="fetch record-dense conversations only to advance the watermark, writing none "
             "of their text",
    )
    arguments = parser.parse_args(argv)

    try:
        source = configuration.source(arguments.source)
        raw_text_directory = None if arguments.count_only else raw_directory.checked(
            arguments.source)
        output = raw_directory.output_checked(arguments.output)

    except configuration.ConfigurationError as error:
        print(f"chat_export: {error}", file=sys.stderr)

        return 1

    handling = Handling(
        dense_names=frozenset(
            name.lstrip("#").lower() for name in source.get("dense_conversations") or []
        ),
        private_topic_markers=tuple(
            marker.lower() for marker in source.get("private_topic_markers") or []
        ),
    )
    acknowledgements = BARE_ACKNOWLEDGEMENTS | {
        text.lower() for text in source.get("extra_acknowledgements") or []
    }

    if raw_text_directory:
        raw_text_directory.mkdir(parents=True, exist_ok=True)

    try:
        content, highest, notes = build_export(
            Client(source),
            arguments.watermark,
            handling,
            acknowledgements,
            raw_text_directory,
        )

    except ExportError as error:
        print(f"chat_export: {error}", file=sys.stderr)

        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")

    active = active_conversation_count(content)

    print(output)
    print(f"{active} conversation(s) with new messages")
    print(f"New watermark: {highest:.6f}")

    if not active:
        print("Nothing to summarize or gate: skip the isolated agent.")

    if handling.dense_names and not raw_text_directory:
        print(
            f"{len(handling.dense_names)} record-dense conversation(s) were fetched only to advance "
            "the watermark; run without --count-only to have them summarized."
        )

    if notes:
        print("\nGaps to report rather than chase:", file=sys.stderr)

        for note in notes:
            print(f"  - {note}", file=sys.stderr)

    return 0


def utf8_streams():
    """Claude Code reads stdout and stderr as UTF-8; left to the locale, a Windows
    Python would encode them with the console code page and raise on the first
    character it lacks — a bullet, an em dash, an emoji in a page title."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    utf8_streams()
    file_modes.owner_only()
    sys.exit(main())
