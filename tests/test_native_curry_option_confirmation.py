import unittest
import json
import copy
import hashlib
import subprocess
import shutil
from time import time as wall_time
import uuid
import warnings
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

import ygo_eval.native_curry_option_validation as curry


class CurryOptionConfirmationScopeTests(unittest.TestCase):
    @contextmanager
    def _temporary_root(self):
        repo = Path(__file__).resolve().parents[1]
        parent = repo / "data" / "runtime" / "curry-confirmation-test-fixtures"
        parent.mkdir(parents=True, exist_ok=True)
        root = parent / uuid.uuid4().hex
        root.mkdir()
        try:
            yield root
        finally:
            shutil.rmtree(root)

    def _saved_build_fixture(self, root: Path):
        artifacts_dir = root / "native-artifacts"
        artifacts_dir.mkdir(parents=True)
        paths = {}
        artifacts = {}
        for role, name, content in (
            ("runner", "curry-option-confirmation.exe", b"runner"),
            ("worker", "ygo-engine-worker.exe", b"worker"),
            ("cli", "ygo-cli.exe", b"cli"),
        ):
            path = artifacts_dir / name
            path.write_bytes(content)
            paths[role] = path
            artifacts[role] = hashlib.sha256(content).hexdigest()

        source_file = {"module.py": hashlib.sha256(b"module").hexdigest()}
        source_head = "0123456789abcdef"
        source_identity = hashlib.sha256(
            curry.canonical({"head": source_head, "files": source_file})
        ).hexdigest()
        source = {
            "head": source_head,
            "files": source_file,
            "identity": source_identity,
        }
        listing = {
            "schema_version": 1,
            "kind": "workspace_source_archive",
            "head": source_head,
            "source_identity": source_identity,
            "file_count": 1,
            "files": source_file,
        }
        archive_path = root / "source-native.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("module.py", b"module")
        file_list_path = root / "source-native-file-list.json"
        file_list_path.write_bytes(curry.canonical(listing))
        paths["source_archive"] = archive_path
        paths["source_file_list"] = file_list_path

        identity_unsigned = {"kind": "workspace_identity", "source": source}
        identity_doc = {
            **identity_unsigned,
            "identity": hashlib.sha256(curry.canonical(identity_unsigned)).hexdigest(),
        }
        paths["identity"] = root / "identity.json"
        paths["identity"].write_bytes(curry.canonical(identity_doc))

        build_unsigned = {
            "kind": "build_record",
            "status": "recorded",
            "reproducible_build_proven": False,
            "source_before": source,
            "source_after": source,
            "artifacts": artifacts,
        }
        build_doc = {
            **build_unsigned,
            "identity": hashlib.sha256(curry.canonical(build_unsigned)).hexdigest(),
        }
        paths["build_record"] = root / "build-record.json"
        paths["build_record"].write_bytes(curry.canonical(build_doc))

        manifest = {
            "source": source,
            "request": {},
            "build": {
                "identity": build_doc["identity"],
                "record_sha256": hashlib.sha256(paths["build_record"].read_bytes()).hexdigest(),
                "artifacts": artifacts,
            },
            "input_sha256": {
                **artifacts,
                "build_record": hashlib.sha256(paths["build_record"].read_bytes()).hexdigest(),
                "identity": hashlib.sha256(paths["identity"].read_bytes()).hexdigest(),
                "source_archive": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "source_file_list": hashlib.sha256(file_list_path.read_bytes()).hexdigest(),
            },
            "source_archive": {
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "file_list_sha256": hashlib.sha256(file_list_path.read_bytes()).hexdigest(),
                "file_count": 1,
            },
        }
        return manifest, paths

    def test_saved_confirmation_build_verifies_archive_members_and_artifacts(self):
        with self._temporary_root() as root:
            manifest, paths = self._saved_build_fixture(root)
            with patch(
                "ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"
            ) as identity_check:
                curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)
            identity_check.assert_called_once()

    def test_saved_confirmation_build_rejects_changed_zip_member_even_when_archive_hash_is_rebound(self):
        with self._temporary_root() as root:
            manifest, paths = self._saved_build_fixture(root)
            with zipfile.ZipFile(paths["source_archive"], "w") as archive:
                archive.writestr("module.py", b"tampered")
            manifest["source_archive"]["sha256"] = hashlib.sha256(
                paths["source_archive"].read_bytes()
            ).hexdigest()
            manifest["input_sha256"]["source_archive"] = manifest["source_archive"]["sha256"]
            with patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"):
                with self.assertRaisesRegex(ValueError, "source_archive_member_hash_mismatch"):
                    curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)

    def test_saved_confirmation_build_rejects_mutated_isolated_artifact(self):
        for role in ("runner", "worker", "cli"):
            with self.subTest(role=role), self._temporary_root() as root:
                manifest, paths = self._saved_build_fixture(root)
                paths[role].write_bytes(b"changed artifact")
                with patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"):
                    with self.assertRaisesRegex(
                        ValueError, f"curry_saved_{role}_artifact_hash_mismatch"
                    ):
                        curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)

    def test_saved_confirmation_build_rejects_extra_archive_members_and_rebound_file_lists(self):
        bad_archives = (
            (("module.py", b"module"), ("extra.py", b"unexpected")),
            (("wrong.py", b"module"),),
            (("module.py", b"module"), ("module.py", b"module")),
        )
        for entries in bad_archives:
            with self.subTest(entries=tuple(name for name, _ in entries)), self._temporary_root() as root:
                manifest, paths = self._saved_build_fixture(root)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(paths["source_archive"], "w") as archive:
                        for name, content in entries:
                            archive.writestr(name, content)
                manifest["source_archive"]["sha256"] = hashlib.sha256(
                    paths["source_archive"].read_bytes()
                ).hexdigest()
                manifest["input_sha256"]["source_archive"] = manifest["source_archive"]["sha256"]
                with patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"):
                    with self.assertRaisesRegex(
                        ValueError, "curry_saved_source_archive_membership_invalid"
                    ):
                        curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)

        with self._temporary_root() as root:
            manifest, paths = self._saved_build_fixture(root)
            listing = json.loads(paths["source_file_list"].read_text(encoding="utf-8"))
            listing["source_identity"] = "f" * 64
            paths["source_file_list"].write_bytes(curry.canonical(listing))
            manifest["source_archive"]["file_list_sha256"] = hashlib.sha256(
                paths["source_file_list"].read_bytes()
            ).hexdigest()
            manifest["input_sha256"]["source_file_list"] = manifest["source_archive"]["file_list_sha256"]
            with patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"):
                with self.assertRaisesRegex(ValueError, "curry_saved_source_list_binding_invalid"):
                    curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)

    def test_saved_confirmation_build_rejects_tampered_identity_even_when_hash_is_rebound(self):
        with self._temporary_root() as root:
            manifest, paths = self._saved_build_fixture(root)
            identity = json.loads(paths["identity"].read_text(encoding="utf-8"))
            identity["source"] = {"identity": "f" * 64}
            identity_raw = curry.canonical(identity)
            paths["identity"].write_bytes(identity_raw)
            manifest["input_sha256"]["identity"] = hashlib.sha256(identity_raw).hexdigest()
            with patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"):
                with self.assertRaisesRegex(ValueError, "signed_record_identity_mismatch"):
                    curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)

    def test_saved_confirmation_build_requires_archive_role_hashes_to_match_manifest_inputs(self):
        for role in ("source_archive", "source_file_list"):
            with self.subTest(role=role), self._temporary_root() as root:
                manifest, paths = self._saved_build_fixture(root)
                manifest["input_sha256"][role] = "f" * 64
                with patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity"):
                    with self.assertRaisesRegex(
                        ValueError, f"curry_saved_{role}_role_hash_mismatch"
                    ):
                        curry._verify_saved_confirmation_build_and_archive(root, manifest, paths)

    def test_frozen_input_roles_use_object_hashes_and_preserve_raw_container_hashes(self):
        with self._temporary_root() as root:
            base = {"case_id": "rabbit", "request": {"seed": 1}}
            candidate = {"case_id": "prompt-14-curry-v1", "deck": [1, 2, 3]}
            container = root / "frozen-cases.json"
            container.write_text(
                json.dumps({"cases": [base, candidate, {"case_id": "other"}]}, indent=2)
                + "\n",
                encoding="utf-8",
            )
            files = {"base_request": container, "candidate_case": container}
            preparation = {"base_request": base, "candidate_case": candidate}

            hashes, raw_snapshot = curry._capture_manifest_input_state(
                files, preparation
            )

            self.assertEqual(
                hashes["base_request"],
                hashlib.sha256(curry._case_encode(base)).hexdigest(),
            )
            self.assertEqual(
                hashes["candidate_case"],
                hashlib.sha256(curry._case_encode(candidate)).hexdigest(),
            )
            container_sha = hashlib.sha256(container.read_bytes()).hexdigest()
            self.assertNotEqual(hashes["base_request"], container_sha)
            self.assertNotEqual(hashes["candidate_case"], container_sha)
            self.assertEqual(raw_snapshot[container.resolve()], container_sha)

    def test_raw_frozen_case_binding_rejects_synthetic_bytes(self):
        with self.assertRaisesRegex(ValueError, "curry_frozen_cases_file_hash_mismatch"):
            curry._verify_frozen_cases_raw_binding(b"synthetic frozen cases")

    def test_raw_frozen_case_container_has_its_own_fixed_binding(self):
        from ygo_eval.native_tenki_placement import FROZEN_CASES_SHA256

        repo = Path(__file__).resolve().parents[1]
        baseline = repo / "data/runtime/baseline-2026-10-19"
        try:
            baseline.lstat()
        except FileNotFoundError:
            self.skipTest("historical frozen cases baseline is not present")
        current = (repo / curry.FROZEN_CASES_PATH).read_bytes()
        self.assertEqual(curry._verify_frozen_cases_raw_binding(current), FROZEN_CASES_SHA256)
        self.assertNotEqual(curry._sha(current + b" "), FROZEN_CASES_SHA256)
        with self.assertRaisesRegex(ValueError, "curry_frozen_cases_file_hash_mismatch"):
            curry._verify_frozen_cases_raw_binding(current + b" ")

    def test_saved_manifest_input_mismatch_reports_stable_role_and_hashes(self):
        with self._temporary_root() as root:
            path = root / "frozen-cases.json"
            base = {"case_id": "rabbit", "request": {"seed": 1}}
            candidate = {"case_id": "prompt-14-curry-v1"}
            path.write_text(json.dumps({"cases": [base, candidate]}), encoding="utf-8")
            with self.assertRaises(curry.CurryFrozenInputMismatch) as raised:
                curry._verify_manifest_input_state(
                    {"base_request": path, "candidate_case": path},
                    {"base_request": base, "candidate_case": candidate},
                    {"base_request": "f" * 64, "candidate_case": "e" * 64},
                )
            self.assertEqual(raised.exception.role, "base_request")
            self.assertEqual(raised.exception.diagnostic, "curry_saved_base_request_hash_mismatch")
            self.assertEqual(raised.exception.expected_sha256, "f" * 64)
            self.assertEqual(
                raised.exception.found_sha256,
                hashlib.sha256(curry._case_encode(base)).hexdigest(),
            )

    def test_saved_adapter_codec_role_uses_authenticated_archive_hash_and_protects_live_bytes(self):
        with self._temporary_root() as root:
            path = root / "codec.rs"
            archived_bytes = b"historical adapter codec\n"
            live_bytes = b"later adapter codec with opcode 56\n"
            path.write_bytes(live_bytes)
            archived_hash = hashlib.sha256(archived_bytes).hexdigest()
            live_hash = hashlib.sha256(live_bytes).hexdigest()

            protected = curry._verify_manifest_input_state(
                {"adapter_codec": path}, {}, {"adapter_codec": archived_hash},
                archived_source_hashes={"adapter_codec": archived_hash},
            )

            self.assertEqual(protected[path.resolve()], live_hash)
            with self.assertRaises(curry.CurryFrozenInputMismatch) as raised:
                curry._verify_manifest_input_state(
                    {"adapter_codec": path}, {}, {"adapter_codec": archived_hash},
                )
            self.assertEqual(raised.exception.role, "adapter_codec")

    def test_confirmation_verify_only_reuses_saved_material_without_live_baseline_or_asset_scan(self):
        for prepared_flag, execution_ready in ((True, True), (False, False), (True, False)):
          with self.subTest(prepared=prepared_flag, execution_ready=execution_ready), self._temporary_root() as repo:
            (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
            root = repo / curry.CONFIRMATION_SCOPE.output_root
            output = root / "research"
            (root / "native-artifacts").mkdir(parents=True)
            output.mkdir(parents=True)
            manifest = {
                "schema_version": 1,
                "kind": "native_curry_option_confirmation_manifest",
                "scope": curry.CONFIRMATION_SCOPE.scope,
                "stage1_request_sha256": "a" * 64,
            }
            manifest_raw = curry.canonical(manifest)
            prepared = {
                "schema_version": 1,
                "kind": "native_curry_option_confirmation_prepared",
                "scope": curry.CONFIRMATION_SCOPE.scope,
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "stage1_request_sha256": manifest["stage1_request_sha256"],
                "prepared": prepared_flag,
                "execution_ready": execution_ready,
            }
            (output / "manifest.json").write_bytes(manifest_raw)
            (output / "prepared.json").write_bytes(curry.canonical(prepared))
            paths = {name: root / name for name in (
                "runner", "worker", "build_record", "identity", "window_start",
                "cli", "source_archive", "source_file_list", "ordinary_config",
                "tournament_config",
            )}
            paths["runner"].write_bytes(b"saved runner")
            args = type("Args", (), {
                "baseline_dir": repo / curry.CONFIRMATION_SCOPE.baseline_root,
                "preparation": repo / curry.PREPARATION_PATH,
                "cases": repo / curry.FROZEN_CASES_PATH,
                "core_source": repo / "data/tmp/ocgcore-source/operations.cpp",
                "runner": paths["runner"], "worker": paths["worker"],
                "build_record": paths["build_record"], "identity": paths["identity"],
                "window_start": paths["window_start"], "output": output,
                "prepare_only": False, "verify_only": True,
            })()
            with patch.object(curry, "_fixed_curry_paths", return_value=(root, output, paths)), \
                    patch.object(curry, "validate_curry_report"), \
                    patch.object(curry, "_verify_saved_confirmation_build_and_archive") as saved_build, \
                    patch.object(curry, "verify_curry_only", return_value={"valid": False, "native_calls": 0}) as verifier, \
                    patch.object(curry, "_verify_confirmation_baseline") as baseline, \
                    patch.object(curry, "verify_curry_preparation") as preparation, \
                    patch("ygo_eval.native_tenki_placement._capture_identity") as capture:
                if prepared_flag and execution_ready:
                    result = curry.native_curry_option_confirmation(args, repo)
                    self.assertEqual(result, {"valid": False, "native_calls": 0})
                    saved_build.assert_called_once()
                    verifier.assert_called_once()
                else:
                    with self.assertRaisesRegex(ValueError, "curry_confirmation_prepared_execution_gate_failed"):
                        curry.native_curry_option_confirmation(args, repo)
                    saved_build.assert_not_called()
                    verifier.assert_not_called()
            baseline.assert_not_called()
            preparation.assert_not_called()
            capture.assert_not_called()

    def test_confirmation_prepare_only_freezes_new_scope_and_audit_binding(self):
        from ygo_eval.native_curry_option_validation import (
            FROZEN_CASES_PATH,
            HISTORICAL_SOURCE_TRANSITION,
            PREPARATION_ACCEPTANCE_PATH,
            PREPARATION_PATH,
            PREPARATION_REPORT_PATH,
            native_curry_option_validation,
        )

        with self._temporary_root() as repo:
            (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
            spec = replace(
                curry.CONFIRMATION_SCOPE,
                output_root=Path("data/runtime/curry-confirmation-e2e"),
                baseline_root=Path("data/runtime/curry-confirmation-baseline"),
                candidate_config_root=Path("data/runtime/curry-candidate-source"),
            )
            root = repo / spec.output_root
            artifact_dir = root / "native-artifacts"
            artifact_dir.mkdir(parents=True)
            runner = artifact_dir / "curry-option-confirmation.exe"
            worker = artifact_dir / "ygo-engine-worker.exe"
            cli = artifact_dir / "ygo-cli.exe"
            for path, content in ((runner, b"runner"), (worker, b"worker"), (cli, b"cli")):
                path.write_bytes(content)
            build_record = root / "build-record.json"
            build_record.write_bytes(b"synthetic signed build record")

            baseline = repo / spec.baseline_root
            (baseline / "final-build").mkdir(parents=True)
            audit_bytes = b'{"kind":"synthetic audit","native_calls":0}'
            delivery_bytes = b'{"kind":"synthetic delivery","native_calls":0}'
            (baseline / "audit-report.json").write_bytes(audit_bytes)
            (baseline / "final-build" / "delivery.json").write_bytes(delivery_bytes)
            spec = replace(
                spec,
                baseline_audit_sha256=hashlib.sha256(audit_bytes).hexdigest(),
                delivery_sha256=hashlib.sha256(delivery_bytes).hexdigest(),
            )

            fixed_files = {
                "preparation": PREPARATION_PATH,
                "preparation_report": PREPARATION_REPORT_PATH,
                "preparation_acceptance": PREPARATION_ACCEPTANCE_PATH,
                "operations_source": Path("data/tmp/ocgcore-source/operations.cpp"),
                "base_request": FROZEN_CASES_PATH,
                "adapter_codec": Path(HISTORICAL_SOURCE_TRANSITION["path"]),
                "banlist": Path("data/runtime/banlist.json"),
            }
            file_hashes = {}
            for index, (role, relative) in enumerate(fixed_files.items()):
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"synthetic-{role}-{index}".encode())
                file_hashes[role] = hashlib.sha256(path.read_bytes()).hexdigest()

            main = [85_138_716, *range(1_000, 1_039)]
            rabbit_case = {
                "case_id": "rabbit",
                "deck": {"main": main, "extra": [20_001, 20_002, 20_003], "side": []},
                "opening_hand": [85_138_716, 2_964_201, 2_964_201, 2_964_201, 2_971_090],
                "seed": 1,
                "information": {"opponent_resources": {"hand": [], "main": main}},
            }
            candidate_case = curry._derived_curry_case(rabbit_case)
            base_request = {
                "protocol_version": 2, "seed": 1,
                "deck": copy.deepcopy(rabbit_case["deck"]),
                "opening_hand": copy.deepcopy(rabbit_case["opening_hand"]),
                "decisions": [{"old": "decision"}],
                "engine": {"worker_path": "frozen-worker.exe"},
            }
            base_request_sha = hashlib.sha256(curry._case_encode(base_request)).hexdigest()
            candidate_sha = hashlib.sha256(curry._case_encode(candidate_case)).hexdigest()
            prep_input_hashes = {
                "preparation": file_hashes["preparation"],
                "preparation_report": file_hashes["preparation_report"],
                "preparation_acceptance": file_hashes["preparation_acceptance"],
                "operations_source": file_hashes["operations_source"],
                "candidate_case": candidate_sha,
                "base_request": base_request_sha,
            }
            preparation = {
                "candidate": {"case": copy.deepcopy(candidate_case)},
                "candidate_case": candidate_case,
                "rabbit_case": rabbit_case,
                "base_request": base_request,
                "base_request_entry": {"banlist_path": "data/runtime/banlist.json"},
                "stage1_request_template": base_request,
                "frozen_cases_sha256": "1" * 64,
                "input_sha256": prep_input_hashes,
            }
            pinned = {
                "preparation": file_hashes["preparation"],
                "preparation_report": file_hashes["preparation_report"],
                "preparation_acceptance": file_hashes["preparation_acceptance"],
                "candidate_case": candidate_sha,
                "base_request": base_request_sha,
                "operations_source": file_hashes["operations_source"],
                "adapter_codec": file_hashes["adapter_codec"],
            }

            class PreflightRunner:
                def __init__(self):
                    self.commands = []

                def __call__(self, command, *, cwd, capture_output, timeout, check):
                    del cwd, capture_output, check
                    self.commands.append((list(command), timeout))
                    invocation = json.loads(Path(command[1]).read_text(encoding="utf-8"))
                    if ("--preflight-only" not in command
                            or "--trace-stderr" not in command
                            or "--prepared-sha256" in command
                            or invocation.get("batch_kind") != spec.batch_kind
                            or timeout > 900):
                        raise AssertionError("confirmation prepare called a non-preflight runner mode")
                    result = {
                        "preflight_passed": True,
                        "native_calls": 0,
                        "context": invocation["context"],
                        "identity_sha256": "b" * 64,
                    }
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(result).encode(), b"synthetic trace\n"
                    )

            fake_runner = PreflightRunner()

            from tests.test_native_curry_option_validation import (
                _idle_event, _option_event, _place_event, _receipt,
            )

            class SevenStageRunner:
                def __init__(self):
                    self.consumed = 0
                    self.completed = 0
                    self.normal_stages = []
                    self.verify_calls = 0

                def _stats(self):
                    return {
                        "consumed": self.consumed,
                        "completed": self.completed,
                        "unknown": 0,
                        "reserved": 0,
                        "abandoned": 0,
                        "limit": spec.limit,
                    }

                def __call__(self, command, *, cwd, capture_output, timeout, check):
                    del cwd, capture_output, timeout, check
                    command = list(command)
                    if "--stats" in command:
                        return subprocess.CompletedProcess(
                            command, 0,
                            json.dumps({"native_calls": 0, "ledger": self._stats()}).encode(),
                            b"synthetic stats trace\n",
                        )
                    if "--verify-recorded" in command:
                        self.verify_calls += 1
                        return subprocess.CompletedProcess(
                            command, 0,
                            json.dumps({"native_calls": 0, "verified_recorded": True}).encode(),
                            b"synthetic verification trace\n",
                        )
                    if "--prepared-sha256" not in command:
                        raise AssertionError("unexpected Curry runner mode")
                    invocation = json.loads(Path(command[1]).read_bytes())
                    if invocation.get("batch_kind") != spec.batch_kind:
                        raise AssertionError("normal request lost its fixed batch kind")
                    stage = invocation["stage"]
                    request = invocation["request"]
                    if stage == 2:
                        events = [_idle_event(10), _place_event(11)]
                        receipt = _receipt(
                            stage, request, events=events,
                            pending=events[-1]["fields"]["prompt"],
                        )
                    elif stage == 3:
                        events = [_idle_event(10), _place_event(11), _option_event(12)]
                        receipt = _receipt(
                            stage, request, events=events,
                            pending=events[-1]["fields"]["prompt"],
                        )
                    else:
                        receipt = _receipt(stage, request)
                    receipt.update({
                        "kind": curry._report_kind(spec, "stage"),
                        "scope": spec.scope,
                        "context": invocation["context"],
                        "ledger": self._stats(),
                        "assets_before": copy.deepcopy(invocation["expected_identity"]),
                        "assets_after": copy.deepcopy(invocation["expected_identity"]),
                    })
                    receipt["ledger"] = {
                        "consumed": stage, "completed": stage, "unknown": 0,
                        "reserved": 0, "abandoned": 0, "limit": spec.limit,
                    }
                    receipt_path = Path(invocation["output"])
                    with receipt_path.open("xb") as stream:
                        stream.write(curry.canonical(receipt))
                    ledger_path = Path(invocation["ledger"])
                    ledger_path.parent.mkdir(parents=True, exist_ok=True)
                    with ledger_path.open("ab") as stream:
                        stream.write(f"synthetic-{stage}\n".encode())
                    self.consumed = self.completed = stage
                    self.normal_stages.append(stage)
                    return subprocess.CompletedProcess(
                        command, 0,
                        json.dumps({"successful": True, "native_calls": 1,
                                    "ledger": self._stats()}).encode(),
                        b"synthetic normal trace\n",
                    )

            seven_stage_runner = SevenStageRunner()
            configs = {
                "ordinary": root / "ordinary-candidate.toml",
                "tournament": root / "tournament-candidate.toml",
            }

            def write_configs(_repo, _root, _worker, _baseline):
                for role, path in configs.items():
                    path.write_text(f"{role}=synthetic\n", encoding="utf-8")
                return configs

            archive_path = root / "source-native.zip"
            file_list_path = root / "source-native-file-list.json"

            def write_archive(_repo, _root, source):
                archive_path.write_bytes(b"synthetic source archive")
                file_list_path.write_bytes(b"{}")
                return {
                    "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                    "file_list_sha256": hashlib.sha256(file_list_path.read_bytes()).hexdigest(),
                    "file_count": len(source["files"]),
                }

            identity_path = root / "identity.json"

            def capture_identity(_repo, _cli, _configs, output_path):
                if not (root / "window-start.json").is_file():
                    raise AssertionError("candidate identity scan started before window creation")
                identity = {"identity": "d" * 64}
                output_path.write_text(json.dumps(identity), encoding="utf-8")
                return identity

            ordinary = {"identity": "b" * 64}
            tournament = {"identity": "c" * 64}
            build_hash = hashlib.sha256(build_record.read_bytes()).hexdigest()
            args = type("Args", (), {
                "baseline_dir": baseline,
                "preparation": repo / PREPARATION_PATH,
                "cases": repo / FROZEN_CASES_PATH,
                "core_source": repo / "data/tmp/ocgcore-source/operations.cpp",
                "runner": runner, "worker": worker, "build_record": build_record,
                "identity": identity_path, "window_start": root / "window-start.json",
                "output": root / "research", "prepare_only": True, "verify_only": False,
            })()
            with patch.object(curry, "CONFIRMATION_SCOPE", spec), \
                    patch.object(curry, "PINNED_INPUT_SHA256", pinned), \
                    patch.object(curry, "_verify_confirmation_baseline", return_value=({"verified": True}, {})) as baseline_check, \
                    patch.object(curry, "verify_curry_preparation", return_value=preparation), \
                    patch("ygo_data.identity.stable_source", return_value={
                        "head": "synthetic", "files": {}, "identity": "a" * 64,
                    }), \
                    patch("ygo_eval.native_tenki_placement._candidate_configs", side_effect=write_configs) as configs_mock, \
                    patch("ygo_eval.native_tenki_placement._archive_current_source", side_effect=write_archive), \
                    patch("ygo_eval.native_tenki_placement._capture_identity", side_effect=capture_identity), \
                    patch("ygo_eval.native_tenki_placement_confirmation._verify_build_and_identity", return_value=(
                        {"identity": "synthetic-build"},
                        {"runner": "r" * 64, "worker": "w" * 64, "cli": "c" * 64},
                        cli, build_hash,
                    )), \
                    patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity",
                          return_value=(ordinary, tournament)), \
                    patch.object(curry.time, "time", return_value=int(wall_time())):
                prepared = native_curry_option_validation(
                    args, repo, process_runner=fake_runner, spec=spec,
                )
                self.assertFalse((root / "research" / "calls.jsonl").exists())
                args.prepare_only = False
                with patch.object(
                    curry, "_verify_confirmation_baseline",
                    side_effect=ValueError("C:\\private\\source\\failure"),
                ):
                    with self.assertRaisesRegex(ValueError, "private.*failure"):
                        native_curry_option_validation(
                            args, repo, process_runner=seven_stage_runner, spec=spec,
                        )
                self.assertEqual(seven_stage_runner.normal_stages, [])
                self.assertFalse((root / "research" / "calls.jsonl").exists())
                drifted_preparation = copy.deepcopy(preparation)
                drifted_preparation["base_request"]["seed"] = 99
                with patch.object(curry, "verify_curry_preparation", return_value=drifted_preparation):
                    with self.assertRaisesRegex(
                        curry.CurryFrozenInputMismatch,
                        "curry_saved_base_request_hash_mismatch",
                    ):
                        native_curry_option_validation(
                            args, repo, process_runner=seven_stage_runner, spec=spec,
                        )
                diagnostics = list(
                    (repo / curry.RECOVERY_REFUSAL_DIAGNOSTICS_ROOT).glob("*.json")
                )
                self.assertEqual(len(diagnostics), 2)
                diagnostic_values = [json.loads(path.read_bytes()) for path in diagnostics]
                self.assertEqual(
                    {item["role"] for item in diagnostic_values}, {None, "base_request"}
                )
                self.assertTrue(all(b"private" not in path.read_bytes() for path in diagnostics))
                self.assertFalse((root / "research" / "calls.jsonl").exists())
                self.assertEqual(seven_stage_runner.normal_stages, [])
                summary = native_curry_option_validation(
                    args, repo, process_runner=seven_stage_runner, spec=spec,
                )

            self.assertTrue(prepared["prepared"])
            self.assertTrue(prepared["execution_ready"])
            self.assertEqual(prepared["native_calls"], 0)
            self.assertEqual(len(fake_runner.commands), 1)
            self.assertEqual(baseline_check.call_count, 3)
            self.assertEqual(configs_mock.call_args.args[-1], repo / spec.candidate_config_root)
            manifest = json.loads((root / "research" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["scope"], spec.scope)
            self.assertEqual(manifest["kind"], "native_curry_option_confirmation_manifest")
            self.assertEqual(manifest["input_sha256"]["baseline_audit"], spec.baseline_audit_sha256)
            self.assertEqual(manifest["input_sha256"]["baseline_delivery"], spec.delivery_sha256)
            self.assertEqual(len(manifest["input_sha256"]), len(curry.CONFIRMATION_INPUT_ROLES))
            self.assertTrue((root / "research" / "calls.jsonl").is_file())
            self.assertTrue((root / "research" / "stage-1-input-seal.json").is_file())
            self.assertTrue(summary["successful"])
            self.assertEqual(seven_stage_runner.normal_stages, list(range(1, 8)))
            self.assertEqual(summary["new_consumed"], 7)
            self.assertEqual(summary["cumulative_consumed"], 39)
            self.assertEqual(summary["unknown"], 0)
            self.assertEqual(summary["stages"][4]["independent_replay_matches"], True)
            self.assertEqual(summary["stages"][6]["independent_replay_matches"], True)

            args.verify_only = True
            with patch.object(curry, "CONFIRMATION_SCOPE", spec), \
                    patch.object(curry, "PINNED_INPUT_SHA256", pinned), \
                    patch.object(curry, "_verify_saved_confirmation_build_and_archive"):
                verification = native_curry_option_validation(
                    args, repo, process_runner=seven_stage_runner, spec=spec,
                )
            self.assertTrue(verification["valid"])
            self.assertEqual(verification["native_calls"], 0)
            self.assertEqual(seven_stage_runner.verify_calls, 7)

    def test_confirmation_protection_rechecks_legacy_evidence_and_audit_trees(self):
        repo = Path(__file__).resolve().parents[1]
        directory = repo / "target"
        legacy_spec = replace(curry.CONFIRMATION_SCOPE, baseline_root=Path("missing/audit"))
        with patch.object(curry, "CONFIRMATION_SCOPE", legacy_spec), patch.object(
            curry, "_protected_curry_hash", return_value="legacy-evidence-hash"
        ) as legacy_hash:
            self.assertEqual(
                curry._confirmation_protected_hash(directory, repo),
                "legacy-evidence-hash",
            )
            legacy_hash.assert_called_once_with(directory, directory)

        audit_spec = replace(curry.CONFIRMATION_SCOPE, baseline_root=Path("target"))
        snapshot = {"sample.json": {"kind": "file", "sha256": "a" * 64, "bytes": 1}}
        with patch.object(curry, "CONFIRMATION_SCOPE", audit_spec), patch(
            "ygo_eval.curry_asset_binding_audit._snapshot_tree", return_value=snapshot
        ) as tree_snapshot:
            expected = curry._sha(curry.canonical(snapshot))
            self.assertEqual(
                curry._confirmation_protected_hash(directory, repo), expected
            )
            tree_snapshot.assert_called_once_with(directory)

    def test_confirmation_uses_a_separate_fixed_scope_and_report_prefix(self):
        spec = getattr(curry, "CONFIRMATION_SCOPE", None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.scope, "curry-option-confirmation-v1")
        self.assertEqual(spec.limit, 7)
        self.assertEqual(spec.old_consumed, 32)
        self.assertNotEqual(spec.output_root, curry.CURRY_SCOPE.output_root)
        self.assertNotEqual(spec.input_seal_kind, curry.CURRY_SCOPE.input_seal_kind)
        self.assertEqual(spec.report_prefix, "native_curry_option_confirmation")

    def test_window_contract_preserves_old_kind_and_has_new_fixed_kind(self):
        self.assertEqual(
            curry._window_kind(curry.CURRY_SCOPE),
            "curry_option_validation_window_start",
        )
        self.assertEqual(
            curry._window_kind(curry.CONFIRMATION_SCOPE),
            "curry_option_confirmation_window_start",
        )

    def test_confirmation_uses_old_candidate_root_but_latest_audit_baseline(self):
        spec = curry.CONFIRMATION_SCOPE
        self.assertEqual(
            spec.candidate_config_root,
            curry.CURRY_SCOPE.output_root,
        )
        self.assertNotEqual(spec.candidate_config_root, spec.baseline_root)
        self.assertEqual(
            curry._manifest_roles(spec),
            (*curry.MANIFEST_INPUT_ROLES, "baseline_audit"),
        )
        self.assertEqual(
            curry._pinned_inputs(spec)["baseline_delivery"],
            curry.CONFIRMATION_DELIVERY_SHA256,
        )
        self.assertEqual(
            curry._pinned_inputs(spec)["baseline_audit"],
            curry.CONFIRMATION_AUDIT_SHA256,
        )

    def test_confirmation_summary_has_its_own_kind_and_cumulative_budget(self):
        spec = getattr(curry, "CONFIRMATION_SCOPE", None)
        self.assertIsNotNone(spec)
        report = curry.summarize_curry_validation(
            "a" * 64,
            [],
            {"consumed": 2, "completed": 1, "unknown": 1,
             "reserved": 0, "abandoned": 0, "limit": 7},
            "synthetic_partial",
            spec,
        )
        self.assertEqual(report["kind"], "native_curry_option_confirmation_summary")
        self.assertEqual(report["cumulative_consumed"], 34)
        curry.validate_curry_report(report, spec=spec)

    def test_confirmation_contract_is_separate_and_binds_the_audit_anchor(self):
        path = Path(__file__).resolve().parents[1] / "schemas/native-curry-option-confirmation.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        spec = curry.CONFIRMATION_SCOPE
        input_hashes = {role: "a" * 64 for role in curry._manifest_roles(spec)}
        input_hashes.update(curry._pinned_inputs(spec))
        manifest = {
            "schema_version": 1,
            "kind": "native_curry_option_confirmation_manifest",
            "scope": spec.scope,
            "context": "b" * 64,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "batch_kind": spec.batch_kind,
            "started_at": 1_798_000_000,
            "limit": 7,
            "planned_calls": 7,
            "wall_seconds": 7200,
            "old_consumed": 32,
            "baseline_audit_sha256": curry.CONFIRMATION_AUDIT_SHA256,
            "baseline_delivery_sha256": curry.CONFIRMATION_DELIVERY_SHA256,
            "input_sha256": input_hashes,
            "source": {},
            "historical_source_transition": curry.HISTORICAL_SOURCE_TRANSITION,
            "build": {},
            "assets": {},
            "stage1_request_sha256": "c" * 64,
            "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
            "request": {"protocol_version": 2, "seed": 1, "decisions": []},
        }
        validator.validate(manifest)
        forged = dict(manifest, scope=curry.CURRY_SCOPE.scope)
        self.assertTrue(list(validator.iter_errors(forged)))
        missing_audit = json.loads(json.dumps(manifest))
        missing_audit["input_sha256"].pop("baseline_audit")
        self.assertTrue(list(validator.iter_errors(missing_audit)))

        partial = curry.summarize_curry_validation(
            "b" * 64, [], None, "incomplete_saved_stages", spec,
        )
        validator.validate(partial)

        successful_stages = []
        for stage in range(1, spec.limit + 1):
            ledger = {
                "consumed": stage, "completed": stage, "unknown": 0,
                "reserved": 0, "abandoned": 0, "limit": spec.limit,
            }
            item = {
                "stage": stage, "successful": True, "native_calls": 1,
                "diagnostic": None, "diagnostic_sha256": "c" * 64,
                "receipt_sha256": "d" * 64, "ledger": ledger,
                "independent_replay_matches": True if stage in (5, 7) else None,
            }
            successful_stages.append(item)
        successful = curry.summarize_curry_validation(
            "b" * 64,
            successful_stages,
            {"consumed": 7, "completed": 7, "unknown": 0,
             "reserved": 0, "abandoned": 0, "limit": 7},
            spec=spec,
        )
        self.assertTrue(successful["successful"])
        validator.validate(successful)


if __name__ == "__main__":
    unittest.main()
