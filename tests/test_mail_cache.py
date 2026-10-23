"""Finding and opening the mail MCP server's token cache.

The adapter borrows the server's sign-in, so the one property that matters is
that it looks where the server writes, on every platform and across the
server's versions: an encrypted envelope in a per-platform directory with its
key beside it or in the credential store, a plain file under ~/.config from a
custom cache command or an older version, and the register's own path ahead of
all of them. Resolution is a pure function of environment, platform and home,
so each platform is exercised here from any machine; only the decryption needs
the real library, and that test is skipped where the bare interpreter lacks it.
"""

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import support

sys.path.insert(0, str(support.plugin_root("dan-knowledge-base") / "scripts"))

import mail_cache  # noqa: E402

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

except ImportError:
    AESGCM = None


def envelope(plaintext, key, purpose="token-cache"):
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), f"ms365:v2:A256GCM:{purpose}".encode())

    return json.dumps(
        {
            "_cacheEnvelope": True,
            "v": 2,
            "alg": "A256GCM",
            "iv": base64.b64encode(nonce).decode(),
            "tag": base64.b64encode(sealed[-16:]).decode(),
            "data": base64.b64encode(sealed[:-16]).decode(),
        }
    )


class ResolutionTest(unittest.TestCase):
    def test_windows_looks_under_appdata_then_the_config_directory(self):
        paths = mail_cache.candidate_paths(
            {}, environ={"APPDATA": r"C:\Users\carolyn\AppData\Roaming"}, platform="win32", home=r"C:\Users\carolyn"
        )

        self.assertEqual(paths[0], Path(r"C:\Users\carolyn\AppData\Roaming") / "ms-365-mcp-server" / ".token-cache.json")
        self.assertEqual(paths[-1], Path(r"C:\Users\carolyn") / ".config" / "ms-365-mcp-server" / "msal-token-cache.json")

    def test_macos_looks_under_application_support(self):
        paths = mail_cache.candidate_paths({}, environ={}, platform="darwin", home="/Users/dan")

        self.assertEqual(paths[0], Path("/Users/dan/Library/Application Support/ms-365-mcp-server/.token-cache.json"))

    def test_linux_honours_xdg_config_home(self):
        paths = mail_cache.candidate_paths({}, environ={"XDG_CONFIG_HOME": "/srv/cfg"}, platform="linux", home="/home/dan")

        self.assertEqual(paths[0], Path("/srv/cfg/ms-365-mcp-server/.token-cache.json"))

    def test_the_register_path_then_the_server_override_come_first(self):
        paths = mail_cache.candidate_paths(
            {"credential_cache": "/custom/cache.json"},
            environ={"MS365_MCP_TOKEN_CACHE_PATH": "/override/cache.json"},
            platform="linux",
            home="/home/dan",
        )

        self.assertEqual(paths[:2], [Path("/custom/cache.json"), Path("/override/cache.json")])

    def test_locate_skips_missing_and_empty_files(self):
        with tempfile.TemporaryDirectory() as home:
            current = Path(home) / ".config" / "ms-365-mcp-server" / ".token-cache.json"
            legacy = current.with_name("msal-token-cache.json")
            current.parent.mkdir(parents=True)
            current.write_text("", encoding="utf-8")
            legacy.write_text('{"AccessToken": {}}', encoding="utf-8")

            self.assertEqual(mail_cache.locate({}, environ={}, platform="linux", home=home), legacy)
            self.assertTrue(mail_cache.present({}, environ={}, platform="linux", home=home))

    def test_absence_names_every_place_looked(self):
        with tempfile.TemporaryDirectory() as home:
            with self.assertRaises(mail_cache.CacheError) as caught:
                mail_cache.load({}, environ={}, platform="linux", home=home)

            self.assertIn("no MSAL cache", str(caught.exception))
            self.assertIn(".token-cache.json", str(caught.exception))
            self.assertIn("msal-token-cache.json", str(caught.exception))


class OpeningTest(unittest.TestCase):
    def test_a_plain_cache_passes_through_and_the_old_wrapper_unwraps(self):
        plain = '{"AccessToken": {}}'
        wrapped = json.dumps({"_cacheEnvelope": True, "data": plain, "savedAt": 1})

        self.assertEqual(mail_cache.unwrap(plain), plain)
        self.assertEqual(mail_cache.unwrap(wrapped), plain)
        self.assertIsNone(mail_cache.encrypted_envelope(wrapped))

    def test_an_encrypted_cache_with_no_key_says_where_a_key_would_be(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".token-cache.json"
            path.write_text(
                json.dumps({"_cacheEnvelope": True, "v": 2, "alg": "A256GCM", "iv": "AA==", "tag": "AA==", "data": "AA=="}),
                encoding="utf-8",
            )

            with self.assertRaises(mail_cache.CacheError) as caught:
                mail_cache.open_envelope(path, platform="none")

            self.assertIn(".cache-key", str(caught.exception))
            self.assertIn("ms-365-mcp-server/cache-key", str(caught.exception))

    def test_an_envelope_of_an_unknown_version_is_refused_rather_than_misread(self):
        with self.assertRaises(mail_cache.CacheError):
            mail_cache.encrypted_envelope(json.dumps({"_cacheEnvelope": True, "v": 3, "alg": "A256GCM"}))

    def test_a_key_that_is_not_32_bytes_is_not_a_key(self):
        self.assertIsNone(mail_cache.parse_key(base64.b64encode(b"short").decode()))
        self.assertIsNone(mail_cache.parse_key("not base64!"))
        self.assertEqual(len(mail_cache.parse_key(base64.b64encode(bytes(32)).decode())), 32)

    @unittest.skipUnless(AESGCM, "cryptography is installed only under uv")
    def test_the_key_file_beside_the_cache_opens_it(self):
        key = os.urandom(32)
        plain = '{"AccessToken": {"x": 1}}'

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".token-cache.json"
            path.write_text(envelope(plain, key), encoding="utf-8")
            (Path(directory) / ".cache-key").write_text(base64.b64encode(key).decode() + "\n", encoding="utf-8")

            self.assertEqual(mail_cache.open_envelope(path, platform="none"), plain)

    @unittest.skipUnless(AESGCM, "cryptography is installed only under uv")
    def test_the_wrong_key_is_reported_as_no_key_opening_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".token-cache.json"
            path.write_text(envelope("{}", os.urandom(32)), encoding="utf-8")
            (Path(directory) / ".cache-key").write_text(base64.b64encode(os.urandom(32)).decode(), encoding="utf-8")

            with self.assertRaises(mail_cache.CacheError) as caught:
                mail_cache.open_envelope(path, platform="none")

            self.assertIn("none of the keys", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
