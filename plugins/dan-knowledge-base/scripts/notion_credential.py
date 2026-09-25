#!/usr/bin/env python3
"""Finds the Notion integration token an MCP server already holds.

The `notion` adapter authenticates the way the `email` adapter does: as a guest in
a credential another tool owns, so it needs no integration of its own and has no
secret to rotate. Here that tool is the Notion MCP server, whose token sits in
Claude Code's own config, `~/.claude.json`, as the server's environment.

The official server accepts the token in two shapes, and both are read:

    OPENAPI_MCP_HEADERS  a JSON object of request headers, `Authorization` among them
    NOTION_TOKEN         the bare token

The server is looked up by name at user scope first, then in every project's
entry, since `claude mcp add` defaults to a scope keyed on one directory.

**The value never leaves this module except as a request header.** Errors name the
file and the server, never the token, and `present` answers only whether one was
found. A caller that prints what this returns has broken the contract.
"""

import json
import re
from pathlib import Path

DEFAULT_CLAUDE_CONFIG = "~/.claude.json"
DEFAULT_MCP_SERVER = "notion"


class CredentialError(Exception):
    """No usable token. The message is safe to print: it carries no value."""


def settings_of(source):
    credential = source.get("credential") or {}

    return (
        Path(credential.get("claude_config", DEFAULT_CLAUDE_CONFIG)).expanduser(),
        credential.get("mcp_server", DEFAULT_MCP_SERVER),
    )


def server_entries(document, server):
    """The server's config at user scope, then under each project."""
    entries = [(document.get("mcpServers") or {}).get(server)]

    for project in (document.get("projects") or {}).values():
        if isinstance(project, dict):
            entries.append((project.get("mcpServers") or {}).get(server))

    return [entry for entry in entries if isinstance(entry, dict)]


def authorization_in(entry):
    value = raw_authorization_in(entry)

    return value.strip() if isinstance(value, str) else None


def raw_authorization_in(entry):
    environment = entry.get("env") or {}
    headers = environment.get("OPENAPI_MCP_HEADERS")

    if headers:
        try:
            value = (json.loads(headers) or {}).get("Authorization")

        except (json.JSONDecodeError, AttributeError):
            value = None

        if value:
            return value

    token = environment.get("NOTION_TOKEN")

    return f"Bearer {token}" if token else None


def authorization(source):
    """The `Authorization` header value for the Notion API."""
    path, server = settings_of(source)

    try:
        document = json.loads(path.read_text(encoding="utf-8"))

    except OSError as error:
        raise CredentialError(f"cannot read {path}: {error.strerror}") from None

    except json.JSONDecodeError:
        raise CredentialError(f"{path} is not valid JSON") from None

    for entry in server_entries(document, server):
        value = authorization_in(entry)

        if value:
            # A header value with a control character is refused by http.client with
            # an exception whose message quotes the value. Refuse it here instead,
            # in words that don't.
            if not re.fullmatch(r"[\x21-\x7e]+ [\x21-\x7e]+", value):
                raise CredentialError(
                    f"the Notion token for {server!r} in {path} is malformed (expected "
                    "'Bearer <token>' with no spaces or control characters inside it)"
                )

            return value

    raise CredentialError(
        f"no Notion token for an MCP server named {server!r} in {path}. Add the Notion "
        "MCP server at user scope, or name the right server under the source's "
        '"credential" in the register.'
    )


def present(source):
    try:
        authorization(source)

    except CredentialError:
        return False

    return True
