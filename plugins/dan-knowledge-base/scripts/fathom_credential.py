#!/usr/bin/env python3
"""Finds the Fathom API key, and stores one a person types in.

The `fathom` adapter has no other tool's credential to borrow, so it holds its
own: a Fathom API key, generated in Fathom's settings, which sees the meetings
its owner recorded and the ones shared with them or their team. It is resolved
in this order:

    FATHOM_API_KEY        the environment, resolved before the session started
    credential.key_file   a file holding the key, ~/.config/fathom/api-key
                          unless the source's "credential" names another

**On POSIX a key file anyone but its owner can read is refused**, as ssh refuses
a private key: the fix is `chmod 600`, not a quieter check. Windows has no mode
bits to read, so there the check is skipped and the file's ACL is the control.

**Storing a key is a person's step, run in a terminal:**

    python3 <plugin>/scripts/fathom_credential.py [--key-file PATH]

It reads the key with `getpass`, so it is never echoed and never an argument a
process listing or shell history could show, writes it with mode 0600, and
prints only the path.

**The value never leaves this module except as a request header.** Errors name
the variable or the file, never the key, and `present` answers only whether a
usable one was found. A caller that prints what this returns has broken the
contract.
"""

import argparse
import getpass
import os
import re
import stat
import sys
from pathlib import Path

import file_modes

ENVIRONMENT_VARIABLE = "FATHOM_API_KEY"
DEFAULT_KEY_FILE = "~/.config/fathom/api-key"

# A header value with a control character or a space is refused by http.client
# with an exception whose message quotes the value. Refusing it here instead, in
# words that don't, is what keeps a bad paste out of a traceback.
WELL_FORMED_KEY = re.compile(r"[\x21-\x7e]+")


class CredentialError(Exception):
    """No usable key. The message is safe to print: it carries no value."""


def key_file_of(source):
    credential = (source or {}).get("credential") or {}

    return Path(credential.get("key_file") or DEFAULT_KEY_FILE).expanduser()


def checked(value, origin):
    key = value.strip()

    if not key:
        raise CredentialError(f"{origin} is empty")

    if not WELL_FORMED_KEY.fullmatch(key):
        raise CredentialError(f"the Fathom API key in {origin} is malformed (expected one word "
                              "with no spaces or control characters inside it)")

    return key


def refuse_shared_file(path):
    if os.name == "nt":
        return

    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise CredentialError(f"{path} is accessible to group or other users; run "
                              f"`chmod 600 {path}` and try again")


def key_from_file(path):
    try:
        refuse_shared_file(path)
        text = path.read_text(encoding="utf-8")

    except FileNotFoundError:
        raise CredentialError(
            f"no Fathom API key: {ENVIRONMENT_VARIABLE} is unset and {path} does not exist. "
            f"Store one by running `python3 {Path(__file__).resolve()}` in a terminal."
        ) from None

    except OSError as error:
        raise CredentialError(f"cannot read {path}: {error.strerror}") from None

    except UnicodeDecodeError:
        raise CredentialError(f"{path} is not text") from None

    return checked(text, str(path))


def api_key(source):
    """The `X-Api-Key` header value for the Fathom API."""
    environment_value = os.environ.get(ENVIRONMENT_VARIABLE)

    if environment_value:
        return checked(environment_value, ENVIRONMENT_VARIABLE)

    return key_from_file(key_file_of(source))


def problem(source):
    """Why no usable key was found, in words safe to print; None when one was."""
    try:
        api_key(source)

    except CredentialError as error:
        return str(error)

    return None


def present(source):
    return problem(source) is None


def store(path, key):
    """Write the key readable by its owner alone. The mode is given at creation and
    set again for a file that already existed, so there is no moment at which a
    fresh key sits in a file others can read."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")

    if os.name != "nt":
        os.chmod(path, 0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Store a Fathom API key for the knowledge-base fathom adapter. Run it in "
                    "a terminal: the key is read without echo and written with mode 0600.")
    parser.add_argument("--key-file", default=DEFAULT_KEY_FILE,
                        help=f"where to store it (default: {DEFAULT_KEY_FILE}); match the "
                             'source\'s "credential.key_file" if the register names one')
    arguments = parser.parse_args(argv)
    path = Path(arguments.key_file).expanduser()

    try:
        key = checked(getpass.getpass("Fathom API key (not echoed): "), "the key entered")

    except CredentialError as error:
        print(f"fathom_credential: {error}; nothing written", file=sys.stderr)

        return 1

    except (EOFError, KeyboardInterrupt):
        print("fathom_credential: no key entered; nothing written", file=sys.stderr)

        return 1

    store(path, key)
    print(path)

    return 0


if __name__ == "__main__":
    file_modes.owner_only()
    sys.exit(main())
