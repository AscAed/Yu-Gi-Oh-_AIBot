import hashlib
import pathlib
import subprocess
import tempfile
import unittest
import contextlib
import os
import shutil
import uuid
from unittest.mock import patch

from ygo_data.identity import source_identity, checked_output, record_build, stable_source, runtime_identity, canonical, digest


@contextlib.contextmanager
def temporary_repo():
    # Python 3.14's private temporary-directory ACL can exclude child Git here.
    root = pathlib.Path(__file__).resolve().parents[1] / "data/tmp" / ("identity-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        def writable(function, path, _):
            os.chmod(path, 0o777)
            function(path)
        shutil.rmtree(root, onerror=writable)


class IdentityTests(unittest.TestCase):
    def test_failed_build_keeps_missing_artifact_and_exit_code(self):
        with temporary_repo() as root:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            with patch("ygo_data.identity.toolchain", return_value={"python":"test"}), patch("ygo_data.identity.run_build", return_value=subprocess.CompletedProcess([], 7)):
                record = record_build(root, ["dummy", "C:/private/path", "token=private"], {"cli":root / "missing"})
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["exit_code"], 7)
            self.assertIsNone(record["artifacts"]["cli"])
            self.assertNotIn("private", str(record))

    def test_rejects_source_changing_during_sample(self):
        with patch("ygo_data.identity.source_identity", side_effect=[{"identity":"a"}, {"identity":"b"}]):
            with self.assertRaisesRegex(ValueError, "changed"):
                stable_source(".")

    def test_runtime_digest_is_recomputed(self):
        value = {"schema_version": 1, "kind": "engine_identity", "consistent": True}
        value["identity"] = digest(canonical(value))
        value["consistent"] = False
        result = subprocess.CompletedProcess([], 0, __import__("json").dumps(value).encode())
        with patch("ygo_data.identity.subprocess.run", return_value=result):
            with self.assertRaisesRegex(ValueError, "digest"):
                runtime_identity(".", "ygo", "config")

    def test_noop_build_is_only_observed_and_never_proves_reproducibility(self):
        with temporary_repo() as root:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            artifact = root / "binary"
            artifact.write_bytes(b"old binary")
            with patch("ygo_data.identity.toolchain", return_value={"python":"test"}), patch("ygo_data.identity.run_build", return_value=subprocess.CompletedProcess([], 0)):
                record = record_build(root, ["noop"], {"cli":artifact})
            self.assertEqual(record["status"], "recorded")
            self.assertEqual(record["provenance"], "observed_command_only")
            self.assertFalse(record["reproducible_build_proven"])

    def test_source_includes_untracked_excludes_ignored_and_detects_change(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "new.py").write_text("a", encoding="utf-8")
            a = source_identity(root)
            (root / "ignored").mkdir()
            (root / "ignored/out").write_text("noise")
            self.assertEqual(a, source_identity(root))
            self.assertIn("new.py", a["files"])
            (root / "new.py").write_text("b")
            self.assertNotEqual(a["identity"], source_identity(root)["identity"])

    def test_output_must_be_ignored_to_prevent_self_reference(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            with self.assertRaises(ValueError):
                checked_output(root, root / "output.json")

    def test_output_rejects_git_ignore_inspection_errors(self):
        with temporary_repo() as root:
            for status in (2, 128):
                with self.subTest(status=status):
                    result = subprocess.CompletedProcess([], status)
                    with patch("ygo_data.identity.git", return_value=result):
                        with self.assertRaisesRegex(ValueError, "local git inspection failed"):
                            checked_output(root, root / "output.json")

    def test_output_rejects_git_tracked_inspection_errors(self):
        with temporary_repo() as root:
            for status in (2, 128):
                with self.subTest(status=status):
                    results = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], status)]
                    with patch("ygo_data.identity.git", side_effect=results):
                        with self.assertRaisesRegex(ValueError, "local git inspection failed"):
                            checked_output(root, root / "output.json")

    def test_output_requires_ignored_untracked_path(self):
        with temporary_repo() as root:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "ignored").mkdir()
            tracked = root / "ignored/tracked.json"
            tracked.write_text("{}", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "-f", "ignored/tracked.json"], check=True)
            untracked = root / "ignored/new.json"
            self.assertEqual(checked_output(root, untracked), untracked.absolute())
            self.assertFalse(untracked.exists())
            with self.assertRaisesRegex(ValueError, "output must not be tracked"):
                checked_output(root, tracked)
            with self.assertRaisesRegex(ValueError, "output must be ignored to prevent self reference"):
                checked_output(root, root / "visible.json")

    def test_output_reports_real_git_repository_failure(self):
        with temporary_repo() as root:
            (root / ".git").write_text("gitdir: missing\n", encoding="utf-8")
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", "output.json"],
                capture_output=True,
            )
            self.assertEqual(result.returncode, 128)
            with self.assertRaisesRegex(ValueError, "local git inspection failed"):
                checked_output(root, root / "output.json")
            self.assertFalse((root / "output.json").exists())

    def test_build_detects_source_change(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "src").write_text("before")
            def change(*args, **kwargs):
                (root / "src").write_text("after")
                return subprocess.CompletedProcess(args, 0)
            with patch("ygo_data.identity.toolchain", return_value={"python":"test"}), patch("ygo_data.identity.run_build", side_effect=change):
                record = record_build(root, ["dummy"], {})
            self.assertEqual(record["status"], "source_changed")
            self.assertFalse(record["reproducible_build_proven"])
