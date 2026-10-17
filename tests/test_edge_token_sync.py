"""Synthetic-only tests: NEVER load a real .env or transmit live JWTs."""

import base64
import json
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from bupt_activity_notifier.edge_token_sync import sync_candidate, token_claims


def fake_jwt(*, subject="123456", exp=None, login_type="web", alg="HS256", suffix="sig", admin=None):
    if exp is None:
        exp = int(time.time()) + 7200
    header = {"alg": alg, "typ": "JWT"}
    claims = {"sub": subject, "exp": exp, "iat": exp - 259200, "login_type": login_type}
    if admin is not None:
        claims["admin"] = admin
    def b64(data):
        return base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).decode().rstrip("=")
    return b64(header) + "." + b64(claims) + "." + suffix


class EdgeTokenSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.old = fake_jwt(exp=int(time.time()) + 7200, suffix="old")
        self.new = fake_jwt(exp=int(time.time()) + 259200, suffix="new")
        (self.root / ".env").write_text(
            "# Friendly comment\nSECONDCLASS_TOKEN=" + self.old
            + "\nSERVERCHAN_SENDKEY=dummy-no-secrets\nPOLL_SECONDS=300\n",
            encoding="utf-8",
        )
        self.validator = Mock()

    def config(self):
        return (self.root / ".env").read_text(encoding="utf-8")

    def test_valid_token_upgrades_in_place_without_reformatting_config(self):
        result = sync_candidate(self.new, self.root, validator=self.validator)
        self.assertEqual(result, "updated")
        self.validator.assert_called_once_with(self.new)
        self.assertIn("SECONDCLASS_TOKEN=" + self.new, self.config())
        self.assertNotIn("SECONDCLASS_TOKEN=" + self.old, self.config())
        self.assertIn("# Friendly comment\n", self.config())
        self.assertIn("SERVERCHAN_SENDKEY=dummy-no-secrets\n", self.config())
        self.assertIn("POLL_SECONDS=300\n", self.config())
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "already_current")
        self.validator.assert_called_once()

    def test_diff_account_never_validates_or_writes(self):
        other = fake_jwt(subject="654321", exp=int(time.time()) + 259200)
        self.assertEqual(sync_candidate(other, self.root, validator=self.validator), "wrong_account")
        self.validator.assert_not_called()
        self.assertIn(self.old, self.config())

    def test_login_context_change_rejected(self):
        other = fake_jwt(login_type="manager", exp=int(time.time()) + 259200)
        self.assertEqual(sync_candidate(other, self.root, validator=self.validator), "different_context")
        self.validator.assert_not_called()

    def test_admin_context_change_rejected(self):
        other = fake_jwt(admin=1, exp=int(time.time()) + 259200)
        self.assertEqual(sync_candidate(other, self.root, validator=self.validator), "different_context")
        self.validator.assert_not_called()

    def test_old_or_earlier_token_never_replaces_newer(self):
        earlier = fake_jwt(exp=int(time.time()) + 3601)
        self.assertEqual(sync_candidate(earlier, self.root, validator=self.validator), "not_newer")
        self.validator.assert_not_called()

    def test_expiring_token_rejected(self):
        expiring = fake_jwt(exp=int(time.time()) + 50)
        self.assertEqual(sync_candidate(expiring, self.root, validator=self.validator), "expired_candidate")
        self.validator.assert_not_called()

    def test_bad_format_and_alg_rejected(self):
        for value in ("", "foo", "a.b.c", "x" * 9000, fake_jwt(alg="none")):
            with self.subTest(value=value[:20]):
                self.assertEqual(sync_candidate(value, self.root, validator=self.validator), "invalid_candidate")
        self.validator.assert_not_called()

    def test_student_api_validation_failure_never_writes(self):
        self.validator.side_effect = RuntimeError("synthetic authentication failure")
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "verification_failed")
        self.assertIn(self.old, self.config())

    def test_missing_or_invalid_current_token_never_writes(self):
        (self.root / ".env").unlink()
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "missing_current")
        (self.root / ".env").write_text("SECONDCLASS_TOKEN=garbage\n", encoding="utf-8")
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "bad_config")
        self.validator.assert_not_called()

    def test_config_with_duplicate_token_lines_fails_safely(self):
        with (self.root / ".env").open("a", encoding="utf-8") as f:
            f.write("SECONDCLASS_TOKEN=" + self.old + "\n")
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "bad_config")

    def test_race_with_manual_edit_does_not_overwrite_it(self):
        alternate = fake_jwt(exp=int(time.time()) + 300000, suffix="manual")
        def manual_update(_):
            (self.root / ".env").write_text("SECONDCLASS_TOKEN=" + alternate + "\n", encoding="utf-8")
        self.validator.side_effect = manual_update
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "raced_change")
        self.assertIn(alternate, self.config())

    def test_private_token_file_is_updated_not_env_option(self):
        directory = self.root / "secrets"
        directory.mkdir()
        f = directory / "token.txt"
        f.write_text(self.old + "\n", encoding="utf-8")
        (self.root / ".env").write_text(
            "SECONDCLASS_TOKEN_FILE=secrets/token.txt\nSERVERCHAN_SENDKEY=dummy\n",
            encoding="utf-8",
        )
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "updated")
        self.assertEqual(f.read_text(encoding="utf-8").strip(), self.new)
        self.assertIn("SECONDCLASS_TOKEN_FILE=secrets/token.txt", self.config())
        self.assertNotIn(self.new, self.config())

    def test_outside_private_token_file_rejected(self):
        (self.root / ".env").write_text(
            "SECONDCLASS_TOKEN_FILE=../external/secret.txt\n",
            encoding="utf-8",
        )
        self.assertEqual(sync_candidate(self.new, self.root, validator=self.validator), "missing_current")
        self.validator.assert_not_called()

    def test_synthetic_claims_include_same_subject_and_expiration(self):
        subject, exp, claims = token_claims(self.new)
        self.assertEqual(subject, "123456")
        self.assertEqual(exp, claims["exp"])

    def test_extension_public_key_pins_the_expected_native_messaging_id(self):
        from scripts.edge_native_host import EXTENSION_ID
        directory = Path(__file__).resolve().parents[1] / "edge_token_sync"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        public = base64.b64decode(manifest["key"])
        identifier = "".join(
            chr(ord("a") + nibble)
            for byte in hashlib.sha256(public).digest()[:16]
            for nibble in (byte >> 4, byte & 15)
        )
        self.assertEqual(identifier, EXTENSION_ID)
        self.assertEqual(
            manifest["content_scripts"][0]["matches"],
            ["https://dekt.bupt.edu.cn/*"],
        )
        self.assertEqual(sorted(manifest["permissions"]), ["nativeMessaging", "storage"])

    def test_native_host_origin_and_framing(self):
        import io
        import struct
        from scripts.edge_native_host import ALLOWED_ORIGIN, _framed_read, _framed_write, handle
        self.assertEqual(handle({"kind": "ping"}, origin=ALLOWED_ORIGIN, root=self.root), "ready")
        self.assertEqual(handle({"kind": "ping"}, origin="chrome-extension://bad/", root=self.root), "invalid_origin")
        payload = json.dumps({"kind": "ping"}).encode()
        msg = struct.pack("<I", len(payload)) + payload
        self.assertEqual(_framed_read(io.BytesIO(msg)), {"kind": "ping"})
        self.assertIsNone(_framed_read(io.BytesIO(struct.pack("<I", 20000))))
        stream = io.BytesIO()
        _framed_write(stream, "ready")
        self.assertEqual(_framed_read(io.BytesIO(stream.getvalue())), {"status": "ready"})


if __name__ == "__main__":
    unittest.main()
