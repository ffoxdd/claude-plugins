"""Where a mail MCP server keeps its MSAL token cache, and how to read it.

The email adapter borrows `@softeria/ms-365-mcp-server`'s own sign-in rather
than minting a credential, so it has to find that server's cache the way the
server itself does. Current versions write an AES-256-GCM envelope to a
per-platform config directory and keep the key either in the system credential
store (through keytar) or, where that store is unusable, in a `.cache-key`
file beside the cache. Older versions, and a server routed through a custom
`MS365_MCP_AUTH_CACHE_COMMAND`, leave a plain file under `~/.config`; older
still kept the whole cache in the macOS keychain. All of those are read here,
most current first, so a register needs to name a path only when the server
was pointed somewhere unusual.

Pure resolution — which paths, in what order — takes its environment, platform
and home as arguments so it can be exercised on any machine; only the credential
store and the decryption touch the real one.
"""

import base64
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

SERVICE = "ms-365-mcp-server"
CACHE_FILE = ".token-cache.json"
KEY_FILE = ".cache-key"
KEY_ACCOUNT = "cache-key"
KEY_BYTES = 32
LEGACY_CACHE_FILE = "msal-token-cache.json"
LEGACY_CACHE_ACCOUNT = "msal-token-cache"
PATH_OVERRIDE = "MS365_MCP_TOKEN_CACHE_PATH"
ENVELOPE_VERSION = 2
ALGORITHM = "A256GCM"
PURPOSE = "token-cache"


class CacheError(Exception):
    """The cache could not be read; the message says where it was looked for and
    what to do, in one sentence a session-start note can carry."""


def candidate_paths(graph, environ=None, platform=None, home=None):
    """Every file the cache may be, most specific first: the register's own
    path, the server's environment override, the server's config directory on
    this platform, then the `~/.config` directory older versions and file-backed
    stores use."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)

    paths = []
    configured = graph.get("credential_cache")

    if configured:
        paths.append(Path(configured).expanduser())

    override = (environ.get(PATH_OVERRIDE) or "").strip()

    if override:
        paths.append(Path(override))

    paths.append(config_directory(environ, platform, home) / CACHE_FILE)

    legacy = home / ".config" / SERVICE
    paths.append(legacy / CACHE_FILE)
    paths.append(legacy / LEGACY_CACHE_FILE)

    return unique(paths)


def config_directory(environ, platform, home):
    """The server's own rule for its config directory, platform by platform."""
    if platform == "win32":
        appdata = (environ.get("APPDATA") or "").strip()
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"

        return base / SERVICE

    if platform == "darwin":
        return home / "Library" / "Application Support" / SERVICE

    xdg = (environ.get("XDG_CONFIG_HOME") or "").strip()

    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / SERVICE

    return home / ".config" / SERVICE


def unique(paths):
    seen = []

    for path in paths:
        if path not in seen:
            seen.append(path)

    return seen


def locate(graph, **context):
    """The first candidate that exists with something in it, or None."""
    for path in candidate_paths(graph, **context):
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            return path

    return None


def present(graph, **context):
    """Whether a sign-in exists to borrow, without reading it: a cache file, or
    on macOS the keychain entry the oldest versions used."""
    if locate(graph, **context):
        return True

    platform = context.get("platform", sys.platform)

    return platform == "darwin" and legacy_keychain_cache() is not None


def load(graph, **context):
    """The MSAL cache as the serialized JSON text MSAL deserializes."""
    path = locate(graph, **context)

    if path:
        return unwrap(open_envelope(path))

    platform = context.get("platform", sys.platform)
    text = legacy_keychain_cache() if platform == "darwin" else None

    if text:
        return unwrap(text)

    looked = ", ".join(str(path) for path in candidate_paths(graph, **context))

    raise CacheError(
        f"no MSAL cache at any of {looked}. Sign the mail MCP server in first, then re-run."
    )


def open_envelope(path, platform=None):
    """The cache file's content as the server would see it: decrypted when it
    is an encrypted envelope, as written when it is plain."""
    raw = path.read_text(encoding="utf-8").strip()
    envelope = encrypted_envelope(raw)

    if envelope is None:
        return raw

    keys = cache_keys(path.parent, platform)

    if not keys:
        raise CacheError(
            f"the MSAL cache at {path} is encrypted, and no key was found in "
            f"{path.parent / KEY_FILE} or in the system credential store under "
            f"{SERVICE}/{KEY_ACCOUNT}. Sign the mail MCP server in again, then re-run."
        )

    for key in keys:
        text = decrypt(envelope, key)

        if text is not None:
            return text

    raise CacheError(
        f"the MSAL cache at {path} is encrypted and none of the keys on this machine "
        "opens it. Sign the mail MCP server in again, then re-run."
    )


def encrypted_envelope(raw):
    """The parsed envelope when the text is one the server encrypted, else None.
    The pre-encryption wrapper also carries `_cacheEnvelope` but no version, and
    its `data` is the cache itself, so `v` is what tells the two apart."""
    try:
        parsed = json.loads(raw)

    except ValueError:
        return None

    if not isinstance(parsed, dict) or parsed.get("_cacheEnvelope") is not True:
        return None

    if not isinstance(parsed.get("v"), int):
        return None

    if parsed["v"] != ENVELOPE_VERSION or parsed.get("alg") != ALGORITHM:
        raise CacheError(
            f"the MSAL cache is an encrypted envelope of version {parsed.get('v')} "
            f"({parsed.get('alg')}), which this adapter does not know; update the plugin."
        )

    if not all(isinstance(parsed.get(field), str) for field in ("iv", "tag", "data")):
        raise CacheError("the MSAL cache envelope is missing its iv, tag or data")

    return parsed


def unwrap(text):
    """The pre-encryption wrapper, {_cacheEnvelope, data, savedAt}, around the
    cache MSAL wants. Handing MSAL the wrapper parses without error and yields
    zero accounts, which reads as signed out rather than as a format mismatch."""
    try:
        parsed = json.loads(text)

    except ValueError:
        return text

    if isinstance(parsed, dict) and parsed.get("_cacheEnvelope") and isinstance(parsed.get("data"), str):
        return parsed["data"]

    return text


def cache_keys(directory, platform=None):
    """The keys that may open the cache: the file beside it, then the system
    credential store, in the order the server itself prefers them."""
    platform = sys.platform if platform is None else platform
    keys = []

    for encoded in (key_file(directory), stored_key(platform)):
        key = parse_key(encoded)

        if key is not None and key not in keys:
            keys.append(key)

    return keys


def key_file(directory):
    path = directory / KEY_FILE

    try:
        return path.read_text(encoding="utf-8")

    except OSError:
        return None


def parse_key(encoded):
    if not encoded:
        return None

    try:
        key = base64.b64decode(encoded.strip(), validate=True)

    except (ValueError, TypeError):
        return None

    return key if len(key) == KEY_BYTES else None


def stored_key(platform):
    """The key as keytar stored it for the server: a generic credential whose
    secret is the base64 text, under the service and account the server names."""
    if platform == "darwin":
        return keychain_password(SERVICE, KEY_ACCOUNT)

    if platform == "win32":
        return credential_manager_password(f"{SERVICE}/{KEY_ACCOUNT}")

    return secret_service_password(SERVICE, KEY_ACCOUNT)


def decrypt(envelope, key):
    """The plaintext, or None when this key is not the one; anything else wrong
    with the envelope was caught when it was parsed."""
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    except ImportError:
        raise CacheError(
            "the MSAL cache is encrypted and `cryptography` is unavailable, so this was "
            "not run under `uv`. Invoke the adapter as `uv run <path>/email_sweep.py …`."
        ) from None

    associated = f"ms365:v{envelope['v']}:{envelope['alg']}:{PURPOSE}".encode("utf-8")
    nonce = base64.b64decode(envelope["iv"])
    sealed = base64.b64decode(envelope["data"]) + base64.b64decode(envelope["tag"])

    try:
        return AESGCM(key).decrypt(nonce, sealed, associated).decode("utf-8")

    except InvalidTag:
        return None


def legacy_keychain_cache():
    """macOS only: the oldest versions kept the whole cache as a keychain item."""
    if sys.platform != "darwin":
        return None

    return keychain_password(SERVICE, LEGACY_CACHE_ACCOUNT)


def keychain_password(service, account):
    try:
        completed = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", service, "-a", account],
            capture_output=True,
            text=True,
            check=False,
        )

    except OSError:
        return None

    if completed.returncode != 0:
        return None

    return completed.stdout.strip() or None


def secret_service_password(service, account):
    """Linux: libsecret through secret-tool, which keytar writes to, where it exists."""
    try:
        completed = subprocess.run(
            ["secret-tool", "lookup", "service", service, "account", account],
            capture_output=True,
            text=True,
            check=False,
        )

    except OSError:
        return None

    if completed.returncode != 0:
        return None

    return completed.stdout.strip() or None


def credential_manager_password(target):
    """Windows: the generic credential keytar wrote, read through CredReadW. The
    blob is the secret's UTF-8 bytes, which is how keytar stores a password."""
    if os.name != "nt":
        return None

    import ctypes.wintypes as wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    generic = 1
    advapi32 = ctypes.windll.advapi32
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]

    found = ctypes.POINTER(Credential)()

    if not advapi32.CredReadW(target, generic, 0, ctypes.byref(found)):
        return None

    try:
        size = found.contents.CredentialBlobSize
        blob = ctypes.string_at(found.contents.CredentialBlob, size) if size else b""

    finally:
        advapi32.CredFree(found)

    return blob.decode("utf-8", errors="replace").strip() or None
