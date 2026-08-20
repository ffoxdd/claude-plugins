#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["msal", "requests"]
# ///
"""Collect new digest emails from configured senders into one intake file.

The `email` adapter. Written for meeting-recap mail — Fathom, Grain, Otter, Gong
and their kind all send one summary per attendee — but nothing here knows which
vendor it is talking to. Senders, the marker that ends the useful half of a body,
and the phrases that identify one by shape are all read from the register.

Authenticates by **reusing a mail MCP server's existing MSAL token cache**, so it
needs no app registration of its own, no separate consent, and no credential to
rotate. It only ever reads, and it never writes that cache back — this process is
a guest in another tool's credential store, and a partial write would break the
owner's sign-in. Not persisting a rotated refresh token costs one extra refresh
next run.

Fetching every copy's body is free in the way that matters: bodies are truncated
and deduplicated here, before anything reaches a model, so the duplicate copies a
vendor sends one-per-attendee cost network time rather than context.

Deduplication only reaches copies landing in one window, so the run also keeps a
ledger of meetings already delivered and labels a returning one. The label
deliberately does not ask for a textual diff: two attendees' copies are
independently generated prose, so they disagree in wording wherever they agree in
substance, and a line diff reports almost everything changed. What the label
carries is the fact of recurrence, the date, and where the earlier copy went — so
the comparison can be made against the distilled notes, which is the only place
the earlier meeting still exists in a form worth comparing to.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

# Guarded so the parsing logic below — titles, meeting dates, dedup keys, sender
# matching — can be imported and tested by a bare `python3`, which is what the
# test suite runs. Under `uv run` both are present; a real fetch attempted
# without them fails in `acquire_access_token` with a sentence rather than an
# ImportError traceback.
try:
    import msal
    import requests

except ImportError:
    msal = requests = None

# The register and its loader live at the plugin root, beside the provisioner
# that also reads them. This file sits at
# <plugin>/skills/knowledge-base/scripts/, so the shared module is three levels
# up — a fixed offset inside one shipped subtree, not a guess about the install.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import configuration

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
PAGE_SIZE = 50
SCOPES = ["Mail.Read"]

DEFAULT_CACHE_FILE = "~/.config/ms-365-mcp-server/msal-token-cache.json"
DEFAULT_KEYCHAIN_SERVICE = "ms-365-mcp-server"
DEFAULT_KEYCHAIN_ACCOUNT = "msal-token-cache"

DEFAULT_RETENTION_DAYS = 180

# Long-form English dates. A vendor writing them another way needs this pattern
# extended rather than worked around: the meeting's own date is the dedup key, so
# failing to read it merges or splits meetings silently.
MEETING_DATE_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),\s+(\d{4})\b"
)

# Two shapes seen across vendors: a quoted subject, and a "shared a recap of X"
# forward. A sender whose subjects differ declares its own `title_patterns`.
DEFAULT_TITLE_PATTERNS = (
    r'Recap for\s*"([^"]+)"',
    r"shared a recap of\s+(.+?)\s*$",
)


class SweepError(Exception):
    """A condition that should stop the sweep rather than produce a partial answer."""


def graph_settings(source):
    return source.get("graph", {})


def read_token_cache(graph):
    """Load the mail MCP server's MSAL cache, from wherever that server put it.

    The server is typically installed via `npx -y`, so its version — and its
    cache location — can move without anything on this machine changing. Current
    versions write a file; older ones used the macOS login keychain. The file is
    checked first because it is what current versions maintain; a keychain entry
    may be a stale leftover.
    """
    cache_file = Path(graph.get("credential_cache", DEFAULT_CACHE_FILE)).expanduser()
    stored_text = read_file_cache(cache_file) or read_keychain_cache(graph)

    if not stored_text:
        raise SweepError(
            f"no MSAL cache at {cache_file}"
            + (
                f" and none in the keychain under {keychain_names(graph)}"
                if sys.platform == "darwin"
                else ""
            )
            + ". Sign the mail MCP server in first, then re-run."
        )

    stored = json.loads(stored_text)

    # The MCP server wraps the cache in {_cacheEnvelope, data, savedAt}. Handing
    # MSAL the envelope parses without error and yields zero accounts, which
    # reads as "signed out" rather than as a format mismatch.
    payload = stored["data"] if stored.get("_cacheEnvelope") else stored_text

    cache = msal.SerializableTokenCache()
    cache.deserialize(payload if isinstance(payload, str) else json.dumps(payload))

    return cache


def read_file_cache(path):
    if not path.exists():
        return None

    return path.read_text().strip() or None


def keychain_names(graph):
    service = graph.get("keychain_service", DEFAULT_KEYCHAIN_SERVICE)
    account = graph.get("keychain_account", DEFAULT_KEYCHAIN_ACCOUNT)

    return f"{service}/{account}"


def read_keychain_cache(graph):
    """macOS only, and stated as such: there is no keychain to consult elsewhere,
    so on Windows and Linux the file's absence is the whole answer."""
    if sys.platform != "darwin":
        return None

    service = graph.get("keychain_service", DEFAULT_KEYCHAIN_SERVICE)
    account = graph.get("keychain_account", DEFAULT_KEYCHAIN_ACCOUNT)

    completed = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", service, "-a", account],
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        return None

    return completed.stdout.strip() or None


def acquire_access_token(graph):
    if msal is None or requests is None:
        raise SweepError(
            "msal and requests are unavailable, so this was not run under `uv`. "
            "Invoke it as `uv run <path>/email_sweep.py …` — the inline dependency "
            "block is what installs them."
        )

    client = graph.get("client_id")
    tenant = graph.get("tenant_id")

    if not client or not tenant:
        raise SweepError(
            "the register's email source declares no graph.client_id / graph.tenant_id. "
            "Both are the mail MCP server's own values — the cache was minted for that "
            "client, and a different one cannot refresh it."
        )

    application = msal.PublicClientApplication(
        client,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=read_token_cache(graph),
    )
    accounts = application.get_accounts()

    if not accounts:
        raise SweepError("the MSAL cache holds no account; sign the mail MCP server in again")

    result = application.acquire_token_silent(SCOPES, account=accounts[0])

    if not result or "access_token" not in result:
        description = (result or {}).get("error_description", "no token returned")
        raise SweepError(
            f"silent token acquisition failed: {description}\n"
            "If this mentions AADSTS65001, a scope is un-consented rather than the token "
            "being expired — re-running a device-code login will not fix it."
        )

    return result["access_token"]


def request_graph(access_token, url, prefer_plain_text=False):
    headers = {"Authorization": f"Bearer {access_token}"}

    if prefer_plain_text:
        headers["Prefer"] = 'outlook.body-content-type="text"'

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise SweepError(f"Graph returned HTTP {response.status_code}: {response.text[:200]}")

    return response.json()


def list_messages_since(access_token, watermark):
    """Every message received after the watermark, following pagination.

    Filtering on receivedDateTime is watermark-native — one pass, across all
    folders, nothing returned that was already processed. Deliberately not a
    `$search` for the sender: a KQL `from:` query cannot combine with `$filter`
    or `$orderby`, so it would return that sender's whole mailbox history in
    arbitrary order. The sender is matched client-side instead, which also keeps
    the local-part robustness a domain match is chosen for.

    Graph reports receivedDateTime rounded to the second but filters on the
    stored sub-second value, so a message received at 17:32:05.372Z is reported
    as 17:32:05Z and then matches `gt 17:32:05Z` on every subsequent run.
    Dropping messages whose reported second equals the watermark is what stops
    each cycle's boundary message being redelivered forever.
    """
    selected = "id,subject,from,receivedDateTime,bodyPreview"
    url = (
        f"{GRAPH_ROOT}/me/messages"
        f"?$filter=receivedDateTime%20gt%20{quote(watermark)}"
        f"&$orderby=receivedDateTime%20desc&$select={selected}&$top={PAGE_SIZE}"
    )

    messages = []

    while url:
        payload = request_graph(access_token, url)
        messages.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")

    return [message for message in messages if message["receivedDateTime"] > watermark]


def sender_address(message):
    return ((message.get("from") or {}).get("emailAddress") or {}).get("address", "").lower()


def matching_sender(message, senders):
    """The register entry this message came from, or None.

    Returns the entry rather than a boolean because the body marker and the title
    patterns are per-sender: which vendor sent it decides how it is parsed.
    """
    address = sender_address(message)

    for sender in senders:
        value = (sender.get("value") or "").lower()

        if not value:
            continue

        if sender.get("match", "domain") == "address":
            if address == value:
                return sender

        elif address.endswith(f"@{value}") or address.endswith(f".{value}"):
            return sender

    return None


def looks_like_digest(message, signatures):
    haystack = f"{message.get('subject', '')} {message.get('bodyPreview', '')}".lower()

    return any(signature.lower() in haystack for signature in signatures)


def find_sender_drift(messages, senders, signatures):
    """Report digest-shaped mail from an unexpected sender rather than dropping it.

    A sender whitelist cannot notice a vendor moving domains, which would
    otherwise look exactly like a quiet week — silent, not loud. This is the net
    under that.
    """
    return [
        f"digest-shaped mail from unrecognized {sender_address(message)}: "
        f"{message.get('subject', '(no subject)')!r}"
        for message in messages
        if looks_like_digest(message, signatures) and not matching_sender(message, senders)
    ]


def title_patterns(sender):
    return [
        re.compile(pattern, re.IGNORECASE)
        for pattern in sender.get("title_patterns") or DEFAULT_TITLE_PATTERNS
    ]


def extract_meeting_title(message, sender):
    subject = message.get("subject") or ""

    for pattern in title_patterns(sender):
        found = pattern.search(subject)

        if found:
            return " ".join(found.group(1).split())

    return " ".join(subject.split()) or "(untitled meeting)"


def extract_meeting_date(body, marker):
    """The meeting's own date, taken from past the marker where there is one.

    Received-date is not meeting-date — a share-a-recap feature can deliver an
    old meeting long after the fact, and the dedup key must not confuse the two.
    The region past the marker is searched first because the summary half can
    itself mention a date ("deploys August 10, 2026"), which would otherwise win
    on a whole-body search and key the meeting to the wrong day.
    """
    regions = [body]

    if marker:
        _, _, footer = body.partition(marker)
        regions = [footer, body]

    for region in regions:
        found = MEETING_DATE_PATTERN.search(region)

        if found:
            month, day, year = found.groups()

            return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").strftime("%Y-%m-%d")

    return None


def summarize_body(body, marker):
    if not marker:
        return body.strip()

    return body.split(marker)[0].strip()


def fetch_digest(access_token, message, sender):
    payload = request_graph(
        access_token,
        f"{GRAPH_ROOT}/me/messages/{message['id']}?$select=body",
        prefer_plain_text=True,
    )
    body = ((payload.get("body") or {}).get("content")) or ""
    marker = sender.get("body_ends_at")

    return {
        "title": extract_meeting_title(message, sender),
        "meeting_date": extract_meeting_date(body, marker),
        "received": message["receivedDateTime"],
        "summary": summarize_body(body, marker),
    }


def meeting_key(digest):
    """Identify the meeting a copy is a copy of.

    Title plus the meeting's own date, so two same-titled standups on different
    days stay separate while six copies of one standup collapse. Falls back to
    the received date only when the body carried no meeting date, which keys the
    copy to the wrong day but never merges two distinct meetings.
    """
    return f"{digest['title'].lower()}|{digest['meeting_date'] or digest['received'][:10]}"


def deduplicate(digests):
    """Collapse the one-copy-per-attendee sends by meeting, not by email."""
    unique = {}
    duplicates = 0

    for digest in sorted(digests, key=lambda digest: digest["received"]):
        key = meeting_key(digest)

        if key in unique:
            duplicates += 1
            continue

        unique[key] = digest

    return list(unique.values()), duplicates


def read_ledger(path):
    """Meetings already delivered by an earlier run, keyed as `meeting_key` keys.

    Within one window, `deduplicate` collapses the per-attendee copies. Across
    windows it cannot: once a watermark falls between two copies, the second run
    sees only its own — and the copies are not interchangeable, since two
    attendees' summaries routinely cover different parts of the same meeting. So
    the ledger exists to say "you have had this meeting before", not to suppress
    it.

    An unreadable ledger degrades to an empty one and warns: losing the label for
    one run is a smaller failure than aborting a sweep that otherwise worked.
    """
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())

    except (OSError, json.JSONDecodeError) as error:
        print(f"email_sweep: ignoring unreadable ledger at {path}: {error}", file=sys.stderr)

        return {}


def find_returning(digests, ledger):
    return [(digest, ledger.get(meeting_key(digest))) for digest in digests]


def extended_ledger(ledger, digests, intake_file, retention_days):
    """The ledger with this run's meetings recorded and stale entries dropped.

    A meeting keeps the *first* copy's details, so a label always names the
    earliest delivery rather than the previous one.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    extended = {
        key: entry
        for key, entry in ledger.items()
        if entry.get("meeting_date", "9999-12-31") >= cutoff
    }

    for digest in digests:
        key = meeting_key(digest)

        if key not in extended:
            extended[key] = {
                "meeting_date": digest["meeting_date"] or digest["received"][:10],
                "first_seen": digest["received"],
                "intake_file": Path(intake_file).name,
            }

    return extended


def render_returning_notice(entry):
    return [
        "> [!important] Already distilled in an earlier sync — read it against the notes.",
        f"> A copy of this meeting was delivered on {entry['first_seen']}"
        f" in `{entry['intake_file']}`.",
        "> Two attendees' copies summarize different parts of the same meeting, so this is"
        " likely to carry ground the first one missed. Distil it normally and expect to add;"
        " skipping it as a duplicate is the failure mode this notice exists to prevent.",
        "",
    ]


def render(paired, watermark):
    lines = [
        f"# Meeting recaps — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"Digests received after `{watermark}`, deduplicated by meeting and truncated to",
        "the summary half. Collected mechanically by the knowledge-base email adapter.",
        "",
    ]

    for digest, earlier in sorted(paired, key=lambda pair: pair[0]["received"]):
        lines += [
            f"## {digest['title']} — {digest['meeting_date'] or 'date not found in body'}",
            "",
            f"*Digest email received {digest['received']}.*",
            "",
        ]

        if earlier:
            lines += render_returning_notice(earlier)

        lines += [digest["summary"], ""]

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("watermark", help="ISO-8601 UTC; collect mail received after this")
    parser.add_argument("output", help="path to write the intake file to")
    parser.add_argument("--source", default="email", help="register entry to read (default: email)")
    parser.add_argument("--ledger", type=Path, help="override the register's ledger path")
    arguments = parser.parse_args(argv)

    try:
        document, root = configuration.load()
        source = configuration.source(arguments.source)

    except configuration.ConfigurationError as error:
        print(f"email_sweep: {error}", file=sys.stderr)

        return 1

    senders = source.get("senders") or []

    if not senders:
        print(
            f"email_sweep: the register's {arguments.source!r} source declares no senders, "
            "so there is nothing to sweep. A whitelist is what makes mail tractable — "
            "without one every message would need judging for relevance.",
            file=sys.stderr,
        )

        return 1

    signatures = source.get("shape_signatures") or []
    ledger_path = arguments.ledger or configuration.path_within(
        root, source.get("ledger", "notes/.delivery-ledger")
    )

    try:
        access_token = acquire_access_token(graph_settings(source))
        messages = list_messages_since(access_token, arguments.watermark)
        drift = find_sender_drift(messages, senders, signatures)
        candidates = [
            (message, matching_sender(message, senders))
            for message in messages
            if matching_sender(message, senders)
        ]
        digests, duplicates = deduplicate(
            [fetch_digest(access_token, message, sender) for message, sender in candidates]
        )

    except SweepError as error:
        print(f"email_sweep: {error}", file=sys.stderr)

        return 1

    ledger = read_ledger(ledger_path)
    paired = find_returning(digests, ledger)

    Path(arguments.output).write_text(render(paired, arguments.watermark), encoding="utf-8")

    # Written only once the intake file exists, so a crash mid-write never leaves
    # a meeting marked delivered that nothing delivered.
    ledger_path.write_text(
        json.dumps(
            extended_ledger(
                ledger,
                digests,
                arguments.output,
                source.get("ledger_retention_days", DEFAULT_RETENTION_DAYS),
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    print(arguments.output)
    print(
        f"{len(digests)} meetings from {len(candidates)} emails "
        f"({duplicates} duplicate copies collapsed); {len(messages)} scanned"
    )

    returning = [(digest, earlier) for digest, earlier in paired if earlier]

    if returning:
        print(
            f"{len(returning)} already distilled in an earlier sync — "
            "read against the notes, don't skip as duplicates:"
        )

        for digest, earlier in returning:
            print(
                f"  - {digest['title']!r} — first delivered {earlier['first_seen']} "
                f"in {earlier['intake_file']}"
            )

    if candidates:
        print(f"New watermark: {max(message['receivedDateTime'] for message, _ in candidates)}")

    report_observed(candidates, senders)

    if drift:
        print("\nPossible sender drift — confirm and widen the register:", file=sys.stderr)

        for note in drift:
            print(f"  - {note}", file=sys.stderr)

    return 0


def report_observed(candidates, senders):
    """Say when the sending address differs from the one the register recorded.

    A vendor changing its local-part is harmless for a domain match and worth
    knowing about anyway: it is the cheapest early warning that the sender is
    being reorganized, and the register's baseline is what makes it visible.
    """
    baseline = {
        (sender.get("observed") or "").lower() for sender in senders if sender.get("observed")
    }
    observed = sorted({sender_address(message) for message, _ in candidates})

    if observed and baseline and set(observed) - baseline:
        print(
            f"\nSender differs from the register's baseline: {', '.join(observed)}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    sys.exit(main())
