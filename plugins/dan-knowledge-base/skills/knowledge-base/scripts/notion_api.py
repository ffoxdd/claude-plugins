"""The Notion REST client the knowledge-base scripts share, and the small set of
rules every one of them follows.

  * **Every failure is reduced to a status or an exception type.** A response
    body can quote page content and a header error quotes the header, so neither
    is passed on. `ExportError` carries a path and a status, nothing else.
  * **Requests are paced** below Notion's three-a-second allowance, and a 429 or
    transient 5xx is retried with backoff.
  * **Watermarks are inclusive at minute granularity.** Notion stamps
    `last_edited_time` to the minute, so a strict comparison against a
    seconds-precision clock would skip an edit made later in the same minute.
    `read_watermark` floors the watermark, and `edited_since` compares with `>=`.
  * **A gap withholds the watermark.** `Gaps` collects what a run could not
    cover; any entry means the caller keeps its old watermark.
"""

import http.client
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import configuration

DEFAULT_API_BASE = "https://api.notion.com/v1"
PAGE_SIZE = 100

EXIT_REFUSED = 1
EXIT_GAPS = 3

# Notion allows an average of three requests a second per integration, and a tree
# walk issues them back to back. Pacing below that rate avoids most 429s; the
# retry honours `Retry-After` for the rest, and backs off on a transient 5xx or
# dropped connection the same way.
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.35
RETRIES = 6
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Pinned rather than taken from the MCP server's headers: the database query
# endpoint this relies on moved in later API versions, and a version chosen by
# another tool's config would change these scripts' behaviour underneath them.
NOTION_VERSION = "2022-06-28"


class ExportError(Exception):
    """A request that failed. The message names the path and a status, nothing else."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Retryable(Exception):
    def __init__(self, description, wait_seconds):
        super().__init__(description)
        self.description = description
        self.wait_seconds = wait_seconds


class Gaps:
    """What this run could not cover. Any gap withholds the watermark."""

    def __init__(self):
        self.messages = []

    def add(self, message):
        self.messages.append(message)

    def __bool__(self):
        return bool(self.messages)


class Notion:
    """The few REST calls the scripts make, over the standard library."""

    def __init__(self, api_base, authorization, request_interval=DEFAULT_REQUEST_INTERVAL_SECONDS):
        self.api_base = api_base.rstrip("/")
        self.authorization = authorization
        self.request_interval = request_interval
        self.last_request = 0.0

    @classmethod
    def from_source(cls, source, authorization):
        return cls(
            source.get("api_base", DEFAULT_API_BASE),
            authorization,
            float(source.get("request_interval_seconds", DEFAULT_REQUEST_INTERVAL_SECONDS)),
        )

    def request(self, method, path, body=None):
        for attempt in range(RETRIES + 1):
            self.pace()

            try:
                return self.send(method, path, body)

            except Retryable as retryable:
                if attempt == RETRIES:
                    raise ExportError(
                        f"{method} {path} still failing after {RETRIES} retries "
                        f"({retryable.description})"
                    ) from None

                time.sleep(retryable.wait_seconds * (attempt + 1))

    def pace(self):
        wait = self.last_request + self.request_interval - time.monotonic()

        if wait > 0:
            time.sleep(wait)

        self.last_request = time.monotonic()

    def send(self, method, path, body):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": self.authorization,
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )

        # Every failure is reduced to a status or an exception *type*. Neither a
        # response body nor an exception's own message is ever passed on: a body
        # can quote page content, and a header error quotes the header.
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            if error.code in RETRYABLE_STATUSES:
                raise Retryable(f"status {error.code}", retry_after_seconds(error)) from None

            raise ExportError(
                f"{method} {path} returned {error.code} ({notion_error_code(error)})",
                status=error.code,
            ) from None

        except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
            raise Retryable(type(error).__name__, 1.0) from None

        except ValueError as error:
            raise ExportError(f"{method} {path} returned an unreadable body "
                              f"({type(error).__name__})") from None

    def paginated(self, method, path, body=None):
        cursor = None

        while True:
            if method == "GET":
                separator = "&" if "?" in path else "?"
                page_path = f"{path}{separator}page_size={PAGE_SIZE}"
                page_path += f"&start_cursor={cursor}" if cursor else ""
                result = self.request("GET", page_path)

            else:
                result = self.request(method, path, {**(body or {}), "page_size": PAGE_SIZE,
                                                     **({"start_cursor": cursor} if cursor else {})})

            yield from result.get("results") or []

            if not result.get("has_more"):
                return

            cursor = result.get("next_cursor")

    def page(self, page_id):
        return self.request("GET", f"/pages/{page_id}")

    def block(self, block_id):
        return self.request("GET", f"/blocks/{block_id}")

    def database(self, database_id):
        return self.request("GET", f"/databases/{database_id}")

    def user(self, user_id):
        return self.request("GET", f"/users/{user_id}")

    def children(self, block_id):
        return list(self.paginated("GET", f"/blocks/{block_id}/children"))

    def comments(self, block_id):
        return list(self.paginated("GET", f"/comments?block_id={block_id}"))

    def database_rows(self, database_id):
        return list(self.paginated("POST", f"/databases/{database_id}/query", {}))


def retry_after_seconds(error):
    try:
        return max(1.0, float(error.headers.get("Retry-After") or 1))

    except (TypeError, ValueError):
        return 1.0


def notion_error_code(error):
    """Notion's own error code, never its message: a message can quote content."""
    try:
        code = json.loads(error.read().decode("utf-8")).get("code")

    except (ValueError, OSError, AttributeError):
        return "no code"

    return code if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,64}", code) else "no code"


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def floor_to_minute(moment):
    return moment.replace(second=0, microsecond=0)


def edited_since(item, since):
    return parse_time(item["last_edited_time"]) >= since


def created_since(item, since):
    return parse_time(item["created_time"]) >= since


def format_time(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_watermark(value):
    try:
        moment = parse_time(value)

    except ValueError:
        raise configuration.ConfigurationError(f"{value!r} is not an ISO-8601 time") from None

    if moment.tzinfo is None:
        raise configuration.ConfigurationError(
            f"{value!r} has no timezone; give it as UTC, e.g. {value}T00:00:00Z"
            if "T" not in value else f"{value!r} has no timezone; end it with Z"
        )

    return floor_to_minute(moment)
