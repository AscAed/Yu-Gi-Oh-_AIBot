import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest
import contextlib
import os
import shutil
import uuid
import zipfile
from unittest.mock import patch

from ygo_data.identity import source_identity, checked_output, record_build, stable_source, runtime_identity, canonical, digest, create_source_bundle, verify_source_bundle, source_bound_build_record, verify_source_bound_build_record, create_workspace_state_bundle, verify_workspace_state_bundle


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

    def test_source_bound_build_record_binds_bundle_asset_and_artifact(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            source = root / "src.py"
            source.write_bytes(b"source bytes")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "src.py"], check=True)
            ignored = root / "ignored"
            ignored.mkdir()
            bundle = create_source_bundle(root, ignored / "source-bundle")
            asset = ignored / "engine.bin"
            asset.write_bytes(b"frozen engine asset")
            artifact = ignored / "candidate.exe"

            def build(*args, **kwargs):
                artifact.write_bytes(b"candidate artifact")
                return subprocess.CompletedProcess(args, 0)

            with patch("ygo_data.identity.toolchain", return_value={"python":"test", "rustc":"test", "cargo":"test", "git":"test"}), patch("ygo_data.identity.run_build", side_effect=build):
                record = source_bound_build_record(
                    root, [
                        "cargo", "build", "--offline", "--locked",
                        "--profile", "dev",
                        "-p", "ygo-cli", "--bin", "ygo-cli",
                        "-p", "ygo-engine-adapter", "--bin", "ygo-engine-worker",
                        "--target-dir", "target/private-dir", "token=private",
                    ],
                    {"cli": artifact}, bundle_dir=ignored / "source-bundle", assets={"engine": asset},
                )

            self.assertEqual(record["status"], "recorded")
            self.assertEqual(record["source_bundle_before"]["identity"], bundle["identity"])
            self.assertEqual(record["build_record"]["source_before"], bundle["source"])
            self.assertEqual(record["asset_inputs_before"]["engine"]["sha256"], digest(b"frozen engine asset"))
            self.assertEqual(record["build_record"]["artifacts"]["cli"], digest(b"candidate artifact"))
            self.assertIn("--bin", record["build_record"]["command"])
            self.assertIn("--profile", record["build_record"]["command"])
            self.assertIn("dev", record["build_record"]["command"])
            self.assertIn("ygo-engine-worker", record["build_record"]["command"])
            self.assertIn("--target-dir", record["build_record"]["command"])
            self.assertNotIn("target/private-dir", record["build_record"]["command"])
            self.assertNotIn("private", str(record))
            self.assertEqual(verify_source_bound_build_record(
                record, ignored / "source-bundle", {"cli": artifact}, {"engine": asset},
            )["identity"], record["identity"])

            tampered = dict(record)
            tampered["status"] = "failed"
            with self.assertRaisesRegex(ValueError, "identity"):
                verify_source_bound_build_record(tampered, ignored / "source-bundle", {"cli": artifact}, {"engine": asset})

            malformed_build = dict(record["build_record"])
            malformed_build["status"] = []
            malformed_unsigned = {
                key: value for key, value in malformed_build.items() if key != "identity"
            }
            malformed_build["identity"] = digest(canonical(malformed_unsigned))
            malformed = dict(record)
            malformed["build_record"] = malformed_build
            malformed_unsigned = {
                key: value for key, value in malformed.items() if key != "identity"
            }
            malformed["identity"] = digest(canonical(malformed_unsigned))
            with self.assertRaisesRegex(ValueError, "nested build status invalid"):
                verify_source_bound_build_record(
                    malformed, ignored / "source-bundle", {"cli": artifact}, {"engine": asset},
                )

    def test_source_bound_build_rejects_stale_bundle_before_running_command(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            source = root / "src.py"
            source.write_bytes(b"before")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "src.py"], check=True)
            ignored = root / "ignored"
            ignored.mkdir()
            create_source_bundle(root, ignored / "source-bundle")
            source.write_bytes(b"after")
            with patch("ygo_data.identity.run_build") as run_build:
                with self.assertRaisesRegex(ValueError, "does not match current workspace"):
                    source_bound_build_record(root, ["noop"], {}, ignored / "source-bundle")
            run_build.assert_not_called()

    def test_source_bound_build_rejects_preexisting_artifact_output(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            (root / "src.py").write_bytes(b"source")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "src.py"], check=True)
            ignored = root / "ignored"
            ignored.mkdir()
            create_source_bundle(root, ignored / "source-bundle")
            artifact = ignored / "candidate.exe"
            artifact.write_bytes(b"old artifact")
            with patch("ygo_data.identity.run_build") as run_build:
                with self.assertRaisesRegex(ValueError, "output already exists"):
                    source_bound_build_record(root, ["noop"], {"cli": artifact}, ignored / "source-bundle")
            run_build.assert_not_called()

    def test_source_bound_build_rechecks_assets_immediately_before_command(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            (root / "src.py").write_bytes(b"source")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "src.py"], check=True)
            ignored = root / "ignored"
            ignored.mkdir()
            create_source_bundle(root, ignored / "source-bundle")
            asset = ignored / "asset.bin"
            asset.write_bytes(b"before")

            def change_during_toolchain_capture():
                asset.write_bytes(b"changed before spawn")
                return {"python": "test"}

            with patch("ygo_data.identity.toolchain", side_effect=change_during_toolchain_capture), patch("ygo_data.identity.run_build") as run_build:
                with self.assertRaisesRegex(ValueError, "asset inputs changed before build"):
                    source_bound_build_record(root, ["noop"], {"cli": ignored / "candidate.exe"}, ignored / "source-bundle", {"engine": asset})
            run_build.assert_not_called()

    def test_source_bound_build_records_asset_drift_without_calling_it_stable(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            (root / "src.py").write_bytes(b"source")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "src.py"], check=True)
            ignored = root / "ignored"
            ignored.mkdir()
            create_source_bundle(root, ignored / "source-bundle")
            asset = ignored / "asset.bin"
            asset.write_bytes(b"before")
            artifact = ignored / "candidate.exe"

            def build(*args, **kwargs):
                asset.write_bytes(b"after")
                artifact.write_bytes(b"candidate")
                return subprocess.CompletedProcess(args, 0)

            with patch("ygo_data.identity.toolchain", return_value={"python":"test", "rustc":"test", "cargo":"test", "git":"test"}), patch("ygo_data.identity.run_build", side_effect=build):
                record = source_bound_build_record(root, ["noop"], {"cli": artifact}, ignored / "source-bundle", {"engine": asset})
            self.assertEqual(record["status"], "asset_changed")
            self.assertNotEqual(record["asset_inputs_before"], record["asset_inputs_after"])
            self.assertEqual(verify_source_bound_build_record(
                record, ignored / "source-bundle", {"cli": artifact}, {"engine": asset},
            )["status"], "asset_changed")

    def test_source_bound_build_records_and_verifies_bundle_drift(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            (root / "src.py").write_bytes(b"source")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "src.py"], check=True)
            ignored = root / "ignored"
            ignored.mkdir()
            active_bundle = ignored / "source-bundle"
            before_bundle = ignored / "source-bundle-before"
            create_source_bundle(root, active_bundle)
            create_source_bundle(root, before_bundle)
            artifact = ignored / "candidate.exe"

            def change_bundle_during_build(*args, **kwargs):
                archive_path = active_bundle / "source.zip"
                with zipfile.ZipFile(archive_path, "a") as archive:
                    archive.comment = b"changed during build"
                manifest_path = active_bundle / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                archive_bytes = archive_path.read_bytes()
                manifest["archive"]["bytes"] = len(archive_bytes)
                manifest["archive"]["sha256"] = digest(archive_bytes)
                unsigned = {key: item for key, item in manifest.items() if key != "identity"}
                manifest["identity"] = digest(canonical(unsigned))
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                artifact.write_bytes(b"candidate")
                return subprocess.CompletedProcess(args, 0)

            with patch("ygo_data.identity.toolchain", return_value={"python":"test", "rustc":"test", "cargo":"test", "git":"test"}), patch("ygo_data.identity.run_build", side_effect=change_bundle_during_build):
                record = source_bound_build_record(
                    root, ["noop"], {"cli": artifact}, active_bundle,
                )

            self.assertEqual(record["status"], "source_bundle_changed")
            self.assertNotEqual(record["source_bundle_before"], record["source_bundle_after"])
            self.assertEqual(
                verify_source_bound_build_record(
                    record, before_bundle, {"cli": artifact}, {},
                )["status"],
                "source_bundle_changed",
            )

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

    def test_source_identity_preserves_staged_tracked_deletion(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Identity Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "identity@example.invalid"], check=True)
            deleted = root / "staged-delete.txt"
            deleted.write_bytes(b"committed bytes")
            subprocess.run(["git", "-C", str(root), "add", "staged-delete.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            subprocess.run(["git", "-C", str(root), "rm", "-q", "staged-delete.txt"], check=True)

            identity = source_identity(root)

            self.assertIn("staged-delete.txt", identity["files"])
            self.assertIsNone(identity["files"]["staged-delete.txt"])

    def test_workspace_state_bundle_captures_index_patches_modes_and_source_binding(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Identity Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "identity@example.invalid"], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            tracked = root / "tracked.txt"
            tracked.write_bytes(b"head bytes\n")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            tracked.write_bytes(b"staged bytes\n")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            tracked.write_bytes(b"unstaged bytes\n")
            untracked = root / "new file.txt"
            untracked.write_bytes(b"untracked bytes\n")

            ignored = root / "ignored"
            ignored.mkdir()
            source_dir = ignored / "source"
            source_manifest = create_source_bundle(root, source_dir)
            index_path = root / ".git" / "index"
            index_before = index_path.read_bytes()
            state_dir = ignored / "state"
            manifest = create_workspace_state_bundle(root, source_dir, state_dir)

            self.assertEqual(manifest["source_bundle_identity"], source_manifest["identity"])
            self.assertEqual(manifest["git"]["head"], source_manifest["source"]["head"])
            self.assertEqual(manifest["git"]["index_sha256"], digest(index_before))
            self.assertEqual(index_path.read_bytes(), index_before)
            self.assertEqual(verify_workspace_state_bundle(state_dir, source_dir)["identity"], manifest["identity"])
            with zipfile.ZipFile(state_dir / "workspace-state.zip") as archive:
                self.assertEqual(set(archive.namelist()), {
                    "git-index.bin", "staged.patch", "unstaged.patch",
                    "index-entries.bin", "status.porcelain-v2", "file-modes.json",
                })
                self.assertIn(b"+staged bytes", archive.read("staged.patch"))
                self.assertIn(b"+unstaged bytes", archive.read("unstaged.patch"))
                self.assertIn(b"? new file.txt", archive.read("status.porcelain-v2"))
                modes = json.loads(archive.read("file-modes.json"))
                self.assertEqual(set(modes), {".gitignore", "tracked.txt", "new file.txt"})
                self.assertTrue(all(type(mode) is int and 0 <= mode <= 0o7777 for mode in modes.values()))

            second = create_workspace_state_bundle(root, source_dir, ignored / "state-copy")
            self.assertEqual(second["identity"], manifest["identity"])
            self.assertEqual(second["archive"], manifest["archive"])

    def test_workspace_state_bundle_refuses_an_active_git_index_lock(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            (root / "source.txt").write_bytes(b"source")
            ignored = root / "ignored"
            ignored.mkdir()
            source_dir = ignored / "source"
            create_source_bundle(root, source_dir)
            lock_path = root / ".git" / "index.lock"
            lock_path.write_bytes(b"writer active")
            output = ignored / "state"
            try:
                with self.assertRaisesRegex(ValueError, "index update is in progress"):
                    create_workspace_state_bundle(root, source_dir, output)
                self.assertFalse(output.exists())
            finally:
                lock_path.unlink()

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

    def test_source_bundle_preserves_current_bytes_and_rejects_member_tampering(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            tracked = root / "tracked.py"
            tracked.write_bytes(b"committed version")
            deleted = root / "deleted.py"
            deleted.write_bytes(b"will be deleted")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "tracked.py", "deleted.py"], check=True)
            tracked.write_bytes(b"current worktree version\x00")
            deleted.unlink()
            untracked = root / "nested" / "new.txt"
            untracked.parent.mkdir()
            untracked.write_bytes(b"untracked bytes\n")
            ignored = root / "ignored" / "secret.txt"
            ignored.parent.mkdir()
            ignored.write_bytes(b"ignored bytes")

            bundle_dir = root / "ignored" / "source-bundle"
            manifest = create_source_bundle(root, bundle_dir)

            self.assertEqual(manifest["kind"], "workspace_source_bundle")
            self.assertEqual(manifest["source"], source_identity(root))
            self.assertIsNone(manifest["source"]["files"]["deleted.py"])
            self.assertEqual(manifest["deleted_tracked_file_count"], 1)
            with zipfile.ZipFile(bundle_dir / "source.zip") as archive:
                self.assertEqual(set(archive.namelist()), {".gitignore", "tracked.py", "nested/new.txt"})
                self.assertEqual(archive.read("tracked.py"), b"current worktree version\x00")
                self.assertEqual(archive.read("nested/new.txt"), b"untracked bytes\n")
                self.assertNotIn(b"ignored bytes", archive.read("tracked.py"))
            self.assertEqual(verify_source_bundle(bundle_dir)["identity"], manifest["identity"])
            second = create_source_bundle(root, root / "ignored" / "source-bundle-copy")
            self.assertEqual(second["archive"], manifest["archive"])

            archive_path = bundle_dir / "source.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(".gitignore", b"tampered but structurally valid")
                archive.writestr("tracked.py", b"current worktree version\x00")
                archive.writestr("nested/new.txt", b"untracked bytes\n")
            manifest["archive"]["bytes"] = archive_path.stat().st_size
            manifest["archive"]["sha256"] = digest(archive_path.read_bytes())
            unsigned = dict(manifest)
            unsigned.pop("identity")
            manifest["identity"] = digest(canonical(unsigned))
            (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "member digest"):
                verify_source_bundle(bundle_dir)

    def test_source_bundle_rejects_existing_destination_and_visible_parent(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore"], check=True)
            visible = root / "visible"
            visible.mkdir()
            with self.assertRaisesRegex(ValueError, "output must be ignored"):
                create_source_bundle(root, visible / "bundle")
            ignored = root / "ignored" / "bundle"
            ignored.parent.mkdir()
            ignored.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                create_source_bundle(root, ignored)

    def test_source_bundle_does_not_publish_when_source_changes_mid_capture(self):
        with temporary_repo() as temp:
            root = pathlib.Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")
            (root / "source.py").write_bytes(b"original")
            subprocess.run(["git", "-C", str(root), "add", ".gitignore", "source.py"], check=True)
            before = source_identity(root)
            changed = dict(before)
            changed_files = dict(before["files"])
            changed_files["source.py"] = "a" * 64
            changed["files"] = changed_files
            changed["identity"] = digest(canonical({"head": changed["head"], "files": changed_files}))
            output = root / "ignored" / "bundle"
            with patch("ygo_data.identity.stable_source", side_effect=[before, changed]):
                with self.assertRaisesRegex(ValueError, "changed during bundle capture"):
                    create_source_bundle(root, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(output.parent.glob(".bundle.stage-*")), [])
