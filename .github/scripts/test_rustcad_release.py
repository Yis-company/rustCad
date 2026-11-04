# SPDX-License-Identifier: LGPL-2.1-or-later
"""Release state transitions and negative controls; never contact GitHub."""

import base64
import json
from pathlib import Path
import tempfile
import unittest

from rustcad_release import publish, select_draft

TAG = "rustcad-v0.1.0-alpha.1"
SHA = "a" * 40
PACKAGE = "rustCad-0.1.0-alpha.1-Linux-x86_64.AppImage"
GATES = {"select": {"result": "success"}, "verify": {"result": "success"}}


class GitHubFixture:
    def __init__(self):
        self.sha = SHA
        self.version = "0.1.0-alpha.1"
        self.draft = True
        self.status = "identical"
        self.assets = {}
        self.uploads = []
        self.published = False
        self.move_during_upload = False

    def api(self, path, **fields):
        if fields:
            assert path == "releases/7"
            assert fields == {"draft": False, "prerelease": True, "make_latest": "false"}
            self.published = True
            self.draft = False
            return {}
        if path == f"releases/tags/{TAG}":
            return {"id": 7, "draft": self.draft, "prerelease": True}
        if path == f"git/ref/tags/{TAG}":
            return {"object": {"type": "commit", "sha": self.sha}}
        if path.startswith("compare/"):
            return {"status": self.status}
        if path.startswith("contents/rustcad-version.txt?ref="):
            return {"content": base64.b64encode(self.version.encode()).decode()}
        if path == "releases/7/assets?per_page=100":
            return [{"name": name, "size": len(data)} for name, data in self.assets.items()]
        raise AssertionError(path)

    def upload(self, tag, path):
        assert tag == TAG and path.name not in self.assets
        self.assets[path.name] = path.read_bytes()
        self.uploads.append(path.name)
        if self.move_during_upload:
            self.sha = "b" * 40

    def download(self, tag, name, folder):
        assert tag == TAG
        (folder / name).write_bytes(self.assets[name])


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.github = GitHubFixture()
        (self.folder / PACKAGE).write_bytes(b"tested package bytes")
        self.metadata = {
            "sha": SHA,
            "tag": TAG,
            "version": "0.1.0-alpha.1",
            "package_tests_passed": True,
            "dirty": False,
        }
        self.write_metadata()

    def write_metadata(self):
        (self.folder / "rustcad-evidence.json").write_text(json.dumps(self.metadata))

    def publish(self, gates=GATES):
        publish(self.github, TAG, SHA, gates, self.folder)

    def test_success_publishes_only_tested_bytes_as_prerelease(self):
        self.publish()
        self.assertTrue(self.github.published)
        self.assertEqual(self.github.assets[PACKAGE], (self.folder / PACKAGE).read_bytes())

    def test_every_gate_must_succeed(self):
        for status in ("failure", "cancelled", "skipped", "unknown", None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.publish({"verify": {"result": status}})
        with self.assertRaises(ValueError):
            self.publish({})
        with self.assertRaises(ValueError):
            self.publish({"verify": {"result": "success"}})
        self.assertFalse(self.github.assets or self.github.published)

    def test_invalid_identity_never_uploads(self):
        for field, bad in (
            ("sha", "b" * 40),
            ("version", "0.1.0-alpha.2"),
            ("tag", "rustcad-v0.1.0-alpha.2"),
            ("dirty", True),
            ("package_tests_passed", False),
        ):
            with self.subTest(field=field):
                original = self.metadata[field]
                self.metadata[field] = bad
                self.write_metadata()
                with self.assertRaises(ValueError):
                    self.publish()
                self.metadata[field] = original
        self.assertFalse(self.github.assets or self.github.published)

    def test_missing_package_never_uploads(self):
        (self.folder / PACKAGE).unlink()
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.github.assets)

    def test_rejects_published_wrong_commit_version_and_unmerged_commit(self):
        for field, bad in (
            ("draft", False),
            ("sha", "b" * 40),
            ("version", "0.1.0-alpha.2"),
            ("status", "diverged"),
        ):
            with self.subTest(field=field):
                original = getattr(self.github, field)
                setattr(self.github, field, bad)
                with self.assertRaises(ValueError):
                    self.publish()
                setattr(self.github, field, original)
        self.assertFalse(self.github.assets or self.github.published)

    def test_partial_upload_resumes_identical_assets_without_overwrite(self):
        self.github.assets[PACKAGE] = (self.folder / PACKAGE).read_bytes()
        self.publish()
        self.assertEqual(self.github.uploads, ["rustcad-evidence.json"])
        self.assertTrue(self.github.published)

    def test_same_size_collision_refuses_replacement(self):
        self.github.assets[PACKAGE] = b"X" * (self.folder / PACKAGE).stat().st_size
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self.publish()
        self.assertFalse(self.github.uploads or self.github.published)

    def test_unexpected_asset_and_size_collision_refuse_publication(self):
        for assets in ({"unrelated": b"other"}, {PACKAGE: b"truncated"}):
            self.github.assets = assets
            with self.assertRaises(ValueError):
                self.publish()
        self.assertFalse(self.github.uploads or self.github.published)

    def test_tag_move_during_upload_keeps_draft_unpublished(self):
        self.github.move_during_upload = True
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.github.published)

    def test_unrelated_or_mutable_tags_are_rejected(self):
        for tag in ("latest", "v0.1.0", "rustcad-v0.1.0", "rustcad-v0.1.0-alpha.0"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                select_draft(self.github, tag)


if __name__ == "__main__":
    unittest.main()
