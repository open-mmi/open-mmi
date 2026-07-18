from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import update_policy


class UpdatePolicyTests(unittest.TestCase):
    def test_production_policy_path_ignores_environment_redirection(self):
        with patch.dict(os.environ, {"OPEN_MMI_UPDATE_POLICY_FILE": "/tmp/attacker-policy.json"}, clear=False):
            self.assertEqual(update_policy.policy_file(), update_policy.DEFAULT_POLICY_FILE)

    def test_missing_policy_is_legacy_nightly(self):
        with tempfile.TemporaryDirectory() as temporary:
            policy, state = update_policy.read_policy(Path(temporary) / "missing.json")
        self.assertEqual(state, "legacy-nightly")
        self.assertEqual(policy["channel"], "nightly")
        self.assertTrue(policy["implicit"])

    def test_atomic_writer_uses_fixed_schema_and_private_mutation_surface(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            payload = update_policy.write_policy("beta", path)
            rendered = json.loads(path.read_text(encoding="utf-8"))
            mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(payload["channel"], "beta")
        self.assertEqual(rendered["channel"], "beta")
        self.assertEqual(set(rendered), {"schema_version", "channel", "updated_at"})
        self.assertEqual(mode, 0o644)

    def test_invalid_channel_and_non_root_production_write_are_rejected(self):
        with self.assertRaises(update_policy.UpdatePolicyError):
            update_policy.validate_channel("development")
        with patch.object(os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(update_policy.UpdatePolicyError, "root privileges"):
                update_policy.write_policy("stable", update_policy.DEFAULT_POLICY_FILE)

    def test_legacy_development_policy_is_read_as_nightly(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "channel": "development",
                "updated_at": "2026-07-18T12:00:00+00:00",
            }), encoding="utf-8")
            path.chmod(0o644)
            policy, state = update_policy.read_policy(path)
        self.assertEqual(state, "migrated-development")
        self.assertEqual(policy["channel"], "nightly")
        self.assertFalse(policy["implicit"])

    def test_invalid_extra_fields_symlinks_and_writable_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps({
                "schema_version": 1,
                "channel": "stable",
                "repository": "https://evil.test/repo",
            }), encoding="utf-8")
            policy_path.chmod(0o644)
            self.assertEqual(update_policy.read_policy(policy_path), (None, "invalid"))

            policy_path.write_text(json.dumps({"schema_version": 1, "channel": "stable"}), encoding="utf-8")
            policy_path.chmod(0o666)
            self.assertEqual(update_policy.read_policy(policy_path), (None, "invalid"))

            target = root / "target.json"
            target.write_text(json.dumps({"schema_version": 1, "channel": "stable"}), encoding="utf-8")
            target.chmod(0o644)
            link = root / "link.json"
            link.symlink_to(target)
            self.assertEqual(update_policy.read_policy(link), (None, "invalid"))
            with self.assertRaisesRegex(update_policy.UpdatePolicyError, "symlink"):
                update_policy.write_policy("beta", link)

            dangling = root / "dangling.json"
            dangling.symlink_to(root / "missing-target.json")
            self.assertEqual(update_policy.read_policy(dangling), (None, "invalid"))

    def test_production_path_comparison_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            redirected_parent = Path(temporary) / "open-mmi"
            redirected_parent.mkdir()
            redirected = redirected_parent / "update-policy.json"
            self.assertFalse(update_policy._production_path(redirected))
            self.assertTrue(update_policy._production_path(update_policy.DEFAULT_POLICY_FILE))

    def test_only_official_https_and_ssh_repository_forms_are_trusted(self):
        accepted = (
            "https://github.com/open-mmi/open-mmi",
            "https://github.com/open-mmi/open-mmi.git",
            "git@github.com:open-mmi/open-mmi.git",
            "ssh://git@github.com/open-mmi/open-mmi.git",
        )
        for value in accepted:
            with self.subTest(value=value):
                self.assertTrue(update_policy.is_official_repository_url(value))
        for value in (
            "http://github.com/open-mmi/open-mmi.git",
            "https://github.com/example/open-mmi.git",
            "file:///tmp/open-mmi.git",
            "git://github.com/open-mmi/open-mmi.git",
        ):
            with self.subTest(value=value):
                self.assertFalse(update_policy.is_official_repository_url(value))


if __name__ == "__main__":
    unittest.main()
