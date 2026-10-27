"""Synthetic integration coverage for the fixed Tenki validation workflow.

No engine worker, candidate assets, or production call journal is used here.
The subprocess boundary is replaced with deterministic synthetic runner output;
the shared scheduler, request derivation, and receipt validators stay real.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid
from unittest.mock import patch

from ygo_data.identity import canonical, digest
from ygo_eval.native_tenki_placement_validation import (
    MANIFEST_INPUT_ROLES,
    VALIDATION_SCOPE,
    MANIFEST_INPUT_ROLES,
    _run_six_stages,
    native_tenki_placement_validation,
    validate_stage_receipt,
)


CONTEXT = "a" * 64
PREPARED_HASH = "b" * 64
ASSET_IDENTITY = {"ordinary": "c" * 64}
_TEST_TMP_BASE = (Path(__file__).resolve().parents[1] / "data/runtime"
                  / "p1-tenki-placement-validation-native-2026-10-23"
                  / "target/synthetic-workflow-tests")
STAGE1_REQUEST = {
    "decisions": [{
        "prompt_id": 10,
        "player": 0,
        "choice": {"kind": "command", "command": 5, "index": 0},
    }],
    "protocol": 2,
    "seed": 1,
}


class _TemporaryDirectory:
    def __enter__(self) -> str:
        _TEST_TMP_BASE.mkdir(parents=True, exist_ok=True)
        self.path = _TEST_TMP_BASE / f"run-{uuid.uuid4().hex}"
        self.path.mkdir(exist_ok=False)
        return str(self.path)

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        base = _TEST_TMP_BASE.resolve()
        path = self.path.resolve()
        if path.parent != base or not path.name.startswith("run-"):
            raise AssertionError("synthetic test cleanup escaped its fixed temp base")
        shutil.rmtree(path)


def _temporary_directory() -> _TemporaryDirectory:
    # Keep synthetic evidence in the already ignored scope-local target tree;
    # use direct creation because tempfile-created Windows directories inherit
    # restrictive ACLs in this environment.
    return _TemporaryDirectory()


def _u32(value: int) -> list[int]:
    return list(value.to_bytes(4, "little"))


def _event(prompt_id: int, raw: bytes, prompt: dict) -> dict:
    return {
        "sequence": prompt_id,
        "opcode": raw[0],
        "supported": True,
        "raw": list(raw),
        "fields": {"prompt": prompt},
    }


def _idle_event(prompt_id: int, command: int = 7) -> dict:
    raw = bytes([11, 0]) + bytes(24) + bytes([0, int(command == 7), int(command == 8)])
    prompt = {
        "id": prompt_id,
        "opcode": 11,
        "player": 0,
        "actions": [{
            "choice": {"kind": "command", "command": command, "index": 0},
            "bytes": _u32(command),
        }],
    }
    return _event(prompt_id, raw, prompt)


def _place_event(prompt_id: int = 12) -> dict:
    raw = bytes([18, 0, 1]) + (0xFFFFE0FF).to_bytes(4, "little")
    actions = [{
        "choice": {"kind": "place", "zones": [{
            "player": 0, "location": 8, "sequence": sequence,
        }]},
        "bytes": [0, 8, sequence],
    } for sequence in range(5)]
    return _event(prompt_id, raw, {
        "id": prompt_id, "opcode": 18, "player": 0, "actions": actions,
    })


def _yes_no_event(prompt_id: int = 13) -> dict:
    description = 59877851398144
    raw = bytes([13, 0]) + description.to_bytes(8, "little")
    actions = [
        {"choice": {"kind": "yes_no", "yes": False}, "bytes": [0, 0, 0, 0]},
        {"choice": {"kind": "yes_no", "yes": True}, "bytes": [1, 0, 0, 0]},
    ]
    return _event(prompt_id, raw, {
        "id": prompt_id, "opcode": 13, "player": 0, "actions": actions,
    })


def _targets_event(prompt_id: int = 15) -> dict:
    records = b""
    actions = []
    for index, sequence in enumerate((7, 8)):
        records += (69_247_929).to_bytes(4, "little") + bytes([0, 1])
        records += sequence.to_bytes(4, "little") + (1).to_bytes(4, "little")
        actions.append({
            "card_ids": [69_247_929],
            "choice": {"kind": "cards", "indices": [index]},
            "bytes": [0, 0, 0, 0, 1, 0, 0, 0, index, 0, 0, 0],
        })
    raw = bytes([15, 0, 0]) + (1).to_bytes(4, "little")
    raw += (1).to_bytes(4, "little") + (2).to_bytes(4, "little") + records
    return _event(prompt_id, raw, {
        "id": prompt_id, "opcode": 15, "player": 0, "actions": actions,
    })


def _result_for(stage: int, request: dict) -> dict:
    decisions = copy.deepcopy(request["decisions"])
    if stage == 1:
        automatic = {
            "prompt_id": 11,
            "player": 0,
            "choice": {"kind": "command", "command": 7, "index": 0},
        }
        resolved = decisions + [automatic]
        events = [_idle_event(11), _place_event()]
        pending = events[-1]["fields"]["prompt"]
    elif stage == 2:
        resolved = decisions
        event = _yes_no_event()
        events = [event]
        pending = event["fields"]["prompt"]
    elif stage in (3, 4):
        resolved = decisions
        event = _idle_event(14)
        events = [event]
        pending = event["fields"]["prompt"]
    else:
        resolved = decisions
        event = _targets_event()
        events = [event]
        pending = event["fields"]["prompt"]
    return {
        "status": "decision_required",
        "error": None,
        "coverage_gaps": [],
        "resolved_decisions": resolved,
        "prompt": copy.deepcopy(pending),
        "events": events,
    }


def _stage_receipt(stage: int, request: dict, context: str,
                   identity: dict, *, successful: bool = True) -> dict:
    return {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_stage",
        "scope": VALIDATION_SCOPE.scope,
        "context": context,
        "stage": stage,
        "request": copy.deepcopy(request),
        "successful": successful,
        "diagnostic": None if successful else "synthetic_stage_failure",
        "ledger": {
            "consumed": stage, "completed": stage, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 6,
        },
        "assets_unchanged": True,
        "assets_before": copy.deepcopy(identity),
        "assets_after": copy.deepcopy(identity),
        "window_valid_at_result": True,
        "validation": {"Ok": {
            "response_oracle_matches": True,
            "automatic_decisions_single_legal": True,
        }},
        "result": {"Ok": _result_for(stage, request)},
        "independent_replay_matches": True if stage in (4, 6) else None,
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }


class SyntheticRunner:
    """Pretend subprocess that writes only synthetic receipts in the temp tree."""

    def __init__(self, *, fail_stage: int | None = None):
        self.fail_stage = fail_stage
        self.modes: list[tuple[str, int | None]] = []
        self.normal_stages: list[int] = []
        self.consumed = 0
        self.completed = 0
        self.unknown = 0
        self.reserved = 0
        self.abandoned = 0
        self.limit = 6

    def stats(self) -> dict:
        return {
            "consumed": self.consumed,
            "completed": self.completed,
            "unknown": self.unknown,
            "reserved": self.reserved,
            "abandoned": self.abandoned,
            "limit": self.limit,
        }

    def __call__(self, command, *, cwd, capture_output, timeout, check):
        del cwd, capture_output, timeout, check
        if "--stats" in command:
            mode = "stats"
            stage = None
            self.modes.append((mode, stage))
            output = {"native_calls": 0, "ledger": self.stats()}
            return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), b"")
        if "--verify-recorded" in command:
            mode = "verify_recorded"
            stage = None
            self.modes.append((mode, stage))
            output = {
                "native_calls": 0,
                "verified_recorded": True,
                "successful": True,
                "ledger": self.stats(),
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), b"")
        if "--prepared-sha256" not in command:
            raise AssertionError(f"unexpected synthetic runner mode: {command}")

        mode = "normal"
        input_path = Path(command[1])
        invocation = json.loads(input_path.read_text(encoding="utf-8"))
        stage = invocation["stage"]
        self.modes.append((mode, stage))
        self.normal_stages.append(stage)
        self.consumed = stage
        self.completed = stage
        root_output = Path(invocation["output"])
        root_output.parent.mkdir(parents=True, exist_ok=True)
        if stage == self.fail_stage:
            receipt = _stage_receipt(stage, invocation["request"],
                                     invocation["context"],
                                     invocation["expected_identity"], successful=False)
            exit_code = 1
            successful = False
        else:
            receipt = _stage_receipt(stage, invocation["request"],
                                     invocation["context"],
                                     invocation["expected_identity"])
            exit_code = 0
            successful = True
        with root_output.open("xb") as stream:
            stream.write(json.dumps(receipt, sort_keys=True).encode("utf-8"))
        ledger = invocation["ledger"]
        Path(ledger).parent.mkdir(parents=True, exist_ok=True)
        # This is a synthetic placeholder. Stats are supplied by this fake
        # process boundary and never read by the production runner.
        Path(ledger).write_text(f"synthetic-stage-{stage}\n", encoding="utf-8")
        stdout = json.dumps({
            "successful": successful,
            "native_calls": 1,
            "ledger": self.stats(),
        }).encode("utf-8")
        return subprocess.CompletedProcess(command, exit_code, stdout, b"synthetic\n")


class TenkiValidationWorkflowIntegrationTests(unittest.TestCase):
    def _run_successful_workflow(self, temp: Path, fake: SyntheticRunner):
        root = temp / "experiment"
        output = root / "research"
        repo = temp / "repo"
        root.mkdir()
        output.mkdir(parents=True)
        repo.mkdir()
        runner = root / "native-artifacts" / "runner.exe"
        runner.parent.mkdir()
        runner.write_bytes(b"synthetic runner placeholder")
        manifest = {
            "context": CONTEXT,
            "started_at": 1_000,
            "request": copy.deepcopy(STAGE1_REQUEST),
            "assets": {"ordinary": copy.deepcopy(ASSET_IDENTITY)},
        }
        source = {"identity": "synthetic-source", "files": {}}
        with patch("ygo_eval.native_tenki_placement_validation.stable_source",
                   return_value=source), \
             patch("ygo_eval.native_tenki_placement_validation.validate_stage_receipt",
                   wraps=validate_stage_receipt) as receipt_validator:
            summary = _run_six_stages(
                root=root,
                output=output,
                runner=runner,
                repo=repo,
                manifest=manifest,
                prepared_hash=PREPARED_HASH,
                stage1_request=copy.deepcopy(STAGE1_REQUEST),
                expected_identity=copy.deepcopy(ASSET_IDENTITY),
                source=source,
                protected={},
                frozen_files={},
                process_runner=fake,
                clock=lambda: 2_000,
            )
        return root, output, repo, runner, manifest, source, summary, receipt_validator

    def test_shared_scheduler_runs_all_stages_and_derives_both_branches_and_replays(self):
        with _temporary_directory() as temporary:
            fake = SyntheticRunner()
            root, output, _repo, _runner, _manifest, _source, summary, validator = \
                self._run_successful_workflow(Path(temporary), fake)

            self.assertTrue(summary["successful"])
            self.assertEqual(fake.normal_stages, [1, 2, 3, 4, 5, 6])
            self.assertEqual(fake.stats(), {
                "consumed": 6, "completed": 6, "unknown": 0,
                "reserved": 0, "abandoned": 0, "limit": 6,
            })
            self.assertEqual(validator.call_count, 11)
            self.assertEqual(
                {stage: [call.args[3] for call in validator.call_args_list].count(stage)
                 for stage in range(1, 7)},
                {1: 2, 2: 3, 3: 2, 4: 1, 5: 2, 6: 1},
            )

            request = lambda stage: json.loads(
                (output / f"stage-{stage}-request.json").read_text(encoding="utf-8")
            )
            stage1 = request(1)
            self.assertEqual(stage1, STAGE1_REQUEST)
            stage2 = request(2)
            self.assertEqual(stage2["decisions"][:2], [
                *STAGE1_REQUEST["decisions"],
                {"prompt_id": 11, "player": 0,
                 "choice": {"kind": "command", "command": 7, "index": 0}},
            ])
            self.assertEqual(stage2["decisions"][-1], {
                "prompt_id": 12, "player": 0,
                "choice": {"kind": "place", "zones": [
                    {"player": 0, "location": 8, "sequence": 0},
                ]},
            })
            stage3 = request(3)
            stage4 = request(4)
            stage5 = request(5)
            stage6 = request(6)
            self.assertEqual(stage3["decisions"][:-1], stage2["decisions"])
            self.assertEqual(stage3["decisions"][-1], {
                "prompt_id": 13, "player": 0,
                "choice": {"kind": "yes_no", "yes": False},
            })
            self.assertEqual(stage4, stage3)
            self.assertEqual(stage5["decisions"][:-1], stage2["decisions"])
            self.assertEqual(stage5["decisions"][-1], {
                "prompt_id": 13, "player": 0,
                "choice": {"kind": "yes_no", "yes": True},
            })
            self.assertEqual(stage6, stage5)

            stage5_receipt = json.loads((output / "stage-5.json").read_text())
            candidate_event = stage5_receipt["result"]["Ok"]["events"][-1]
            raw = bytes(candidate_event["raw"])
            self.assertEqual([int.from_bytes(raw[i + 6:i + 10], "little")
                              for i in (15, 29)], [7, 8])
            self.assertEqual([action["choice"]["indices"]
                              for action in candidate_event["fields"]["prompt"]["actions"]],
                             [[0], [1]])
            for stage in (4, 6):
                receipt = json.loads((output / f"stage-{stage}.json").read_text())
                self.assertIs(receipt["independent_replay_matches"], True)
            self.assertTrue((root / "process-diagnostics").is_dir())

    def test_failed_parent_stops_before_any_later_stage_charge(self):
        with _temporary_directory() as temporary:
            fake = SyntheticRunner(fail_stage=2)
            root = Path(temporary) / "experiment"
            output = root / "research"
            repo = Path(temporary) / "repo"
            root.mkdir()
            output.mkdir(parents=True)
            repo.mkdir()
            runner = root / "runner.exe"
            runner.write_bytes(b"synthetic")
            source = {"identity": "synthetic-source", "files": {}}
            manifest = {"context": CONTEXT, "started_at": 1_000,
                        "request": copy.deepcopy(STAGE1_REQUEST),
                        "assets": {"ordinary": copy.deepcopy(ASSET_IDENTITY)}}
            with patch("ygo_eval.native_tenki_placement_validation.stable_source",
                       return_value=source):
                summary = _run_six_stages(
                    root=root, output=output, runner=runner, repo=repo,
                    manifest=manifest, prepared_hash=PREPARED_HASH,
                    stage1_request=copy.deepcopy(STAGE1_REQUEST),
                    expected_identity=copy.deepcopy(ASSET_IDENTITY), source=source,
                    protected={}, frozen_files={}, process_runner=fake,
                    clock=lambda: 2_000,
                )
            self.assertFalse(summary["successful"])
            self.assertEqual(fake.normal_stages, [1, 2])
            self.assertEqual([item["stage"] for item in summary["stages"]], [1, 2])
            self.assertEqual(summary["new_consumed"], 2)
            self.assertEqual(summary["unknown"], 0)
            self.assertFalse((output / "stage-3-input.json").exists())

    def test_failed_public_preflight_is_durable_read_only_and_never_retried(self):
        from argparse import Namespace
        from ygo_eval.native_tenki_placement_validation import ScopeSpec

        with _temporary_directory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
            spec = ScopeSpec(
                scope="tenki-placement-validation-v1",
                output_root=Path("data/runtime/synthetic-public-preflight"),
                baseline_root=Path("synthetic-baseline"),
                limit=6, wall_seconds=7200, old_consumed=26,
                batch_kind="tenki-placement-validation-v1",
                input_seal_kind="tenki_placement_validation_stage_input_seal",
                runner_role="tenki_placement_validation_runner",
                delivery_sha256="d" * 64,
            )
            root = repo / spec.output_root
            artifacts_dir = root / "native-artifacts"
            artifacts_dir.mkdir(parents=True)
            runner = artifacts_dir / "tenki-placement-probe.exe"
            worker = artifacts_dir / "ygo-engine-worker.exe"
            cli = artifacts_dir / "ygo-cli.exe"
            runner.write_bytes(b"synthetic runner")
            worker.write_bytes(b"synthetic worker")
            cli.write_bytes(b"synthetic cli")
            build_record = root / "build-record.json"
            build_record.write_bytes(b"synthetic build record")
            identity_path = root / "identity.json"
            ordinary_config = root / "ordinary-candidate.toml"
            tournament_config = root / "tournament-candidate.toml"
            ordinary_config.write_text("ordinary = true\n", encoding="utf-8")
            tournament_config.write_text("tournament = true\n", encoding="utf-8")
            archive_path = root / "source-native.zip"
            file_list_path = root / "source-native-file-list.json"
            archive_path.write_bytes(b"synthetic archive")
            file_list_path.write_bytes(b"synthetic file list")
            output = root / "research"
            args = Namespace(
                baseline_dir=repo / spec.baseline_root,
                runner=runner, worker=worker, build_record=build_record,
                identity=identity_path, window_start=root / "window-start.json",
                output=output, prepare_only=True, verify_only=False,
            )
            source = {"identity": "synthetic-source", "files": {}}
            ordinary = {"identity": "ordinary-identity"}
            tournament = {"identity": "tournament-identity"}
            identity = {"identity": "identity-envelope"}
            artifact_hashes = {
                "runner": hashlib.sha256(runner.read_bytes()).hexdigest(),
                "worker": hashlib.sha256(worker.read_bytes()).hexdigest(),
                "cli": hashlib.sha256(cli.read_bytes()).hexdigest(),
            }
            build_hash = hashlib.sha256(build_record.read_bytes()).hexdigest()
            frozen_case = {
                "preparation_sha256": "1" * 64,
                "banlist_sha256": "2" * 64,
                "old_stage1_sha256": "3" * 64,
                "old_stage2_request_sha256": "4" * 64,
            }
            archive_info = {
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "file_list_sha256": hashlib.sha256(file_list_path.read_bytes()).hexdigest(),
                "file_count": 0, "archive": "source-native.zip",
                "file_list": "source-native-file-list.json",
            }
            invocation_count = 0

            def derive_candidate_request(*_args, **_kwargs):
                self.assertTrue(
                    args.window_start.is_file(),
                    "window start must be durable before source validation scans assets",
                )
                return copy.deepcopy(STAGE1_REQUEST), frozen_case

            def fake_process(*_args, **_kwargs):
                nonlocal invocation_count
                invocation_count += 1
                return subprocess.CompletedProcess(
                    ["synthetic-runner"], 1, stdout=b"{}", stderr=b"preflight failed",
                )

            def save_identity(_repo, _cli, _configs, destination):
                destination.write_bytes(canonical(identity))
                return identity

            patches = [
                patch("ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                      return_value=({"audit_sha256": "5" * 64}, {})),
                patch("ygo_eval.native_tenki_placement_validation._validate_saved_build_inputs",
                      return_value={}),
                patch("ygo_eval.native_tenki_placement_validation.stable_source",
                      return_value=source),
                patch("ygo_eval.native_tenki_placement._archive_current_source",
                      return_value=archive_info),
                patch("ygo_eval.native_tenki_placement._candidate_configs",
                      return_value={"ordinary": ordinary_config,
                                    "tournament": tournament_config}),
                patch("ygo_eval.native_tenki_placement._capture_identity",
                      side_effect=save_identity),
                patch("ygo_eval.native_tenki_placement_confirmation._verify_build_and_identity",
                      return_value=({"identity": "build-identity"}, artifact_hashes,
                                    cli, build_hash)),
                patch("ygo_eval.native_tenki_placement_confirmation._candidate_request",
                      side_effect=derive_candidate_request),
                patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity",
                      return_value=(ordinary, tournament)),
                patch("ygo_eval.native_tenki_placement_validation._verify_frozen_stage1_request"),
            ]
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9]:
                failure = native_tenki_placement_validation(
                    args, repo=repo, spec=spec, process_runner=fake_process,
                )

                self.assertEqual(failure["kind"],
                                 "native_tenki_placement_validation_preflight_failure")
                self.assertFalse(failure["execution_ready"])
                self.assertEqual(failure["native_calls"], 0)
                self.assertFalse((output / "calls.jsonl").exists())
                self.assertTrue((output / "preflight-failure.json").is_file())
                self.assertEqual(invocation_count, 1)

                args.verify_only = True
                verified = native_tenki_placement_validation(
                    args, repo=repo, spec=spec, process_runner=fake_process,
                )
                self.assertEqual(verified, failure)
                args.verify_only = False
                resumed = native_tenki_placement_validation(
                    args, repo=repo, spec=spec, process_runner=fake_process,
                )
                self.assertEqual(resumed, failure)
                args.prepare_only = False
                with self.assertRaisesRegex(ValueError,
                                            "validation_preflight_failed_requires_verify_only"):
                    native_tenki_placement_validation(
                        args, repo=repo, spec=spec, process_runner=fake_process,
                    )
                self.assertEqual(invocation_count, 1)
                self.assertEqual(set(json.loads((output / "manifest.json").read_bytes())[
                    "input_sha256"]), set(MANIFEST_INPUT_ROLES))

    def _public_verify_fixture(self, repo: Path, fake: SyntheticRunner):
        spec = type(VALIDATION_SCOPE)(
            scope="tenki-placement-validation-v1",
            output_root=Path("data/runtime/synthetic-validation-workflow"),
            baseline_root=Path("synthetic-baseline"),
            limit=6, wall_seconds=7_200, old_consumed=26,
            batch_kind="tenki-placement-validation-v1",
            input_seal_kind="tenki_placement_validation_stage_input_seal",
            runner_role="tenki_placement_validation_runner",
            delivery_sha256="d" * 64,
        )
        (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
        root = repo / spec.output_root
        output = root / "research"
        output.mkdir(parents=True)
        (root / "native-artifacts").mkdir()
        runner = root / "native-artifacts" / "tenki-placement-probe.exe"
        runner.write_bytes(b"synthetic runner placeholder")
        # started_at is deliberately long expired. Verify-only must not use it
        # as permission to execute or as a reason to reject read-only checks.
        unsigned = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_manifest",
            "scope": spec.scope,
            "started_at": 1_000,
            "limit": spec.limit,
            "planned_calls": spec.limit,
            "wall_seconds": spec.wall_seconds,
            "old_consumed": spec.old_consumed,
            "baseline_delivery_sha256": spec.delivery_sha256,
            "input_sha256": {role: "e" * 64 for role in MANIFEST_INPUT_ROLES},
            "source": {"identity": "synthetic-source", "files": {}},
            "build": {},
            "assets": {"ordinary": copy.deepcopy(ASSET_IDENTITY)},
            "request": copy.deepcopy(STAGE1_REQUEST),
            "stage1_request_sha256": digest(canonical(STAGE1_REQUEST)),
            "request_derivation": "frozen-tenki-activation-only-worker-path-replaced",
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        manifest = {**unsigned, "context": digest(canonical(unsigned))}
        (output / "manifest.json").write_bytes(canonical(manifest))
        args = type("Args", (), {
            "baseline_dir": repo / spec.baseline_root,
            "runner": runner,
            "worker": root / "native-artifacts" / "ygo-engine-worker.exe",
            "build_record": root / "build-record.json",
            "identity": root / "identity.json",
            "window_start": root / "window-start.json",
            "output": output,
            "prepare_only": False,
            "verify_only": True,
        })()
        return spec, root, output, runner, manifest, args

    def test_public_verify_only_is_zero_normal_calls_after_expiry_and_preserves_prior_bytes(self):
        with _temporary_directory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            fake = SyntheticRunner()
            spec, root, output, runner, verify_manifest, args = self._public_verify_fixture(
                repo, fake,
            )
            source = verify_manifest["source"]
            with patch("ygo_eval.native_tenki_placement_validation.stable_source",
                       return_value=source):
                _run_six_stages(
                    root=root, output=output, runner=runner, repo=repo,
                    manifest=verify_manifest, prepared_hash=PREPARED_HASH,
                    stage1_request=copy.deepcopy(STAGE1_REQUEST),
                    expected_identity=copy.deepcopy(ASSET_IDENTITY), source=source,
                    protected={}, frozen_files={}, process_runner=fake,
                    clock=lambda: 2_000,
                )
            preserved = {path: path.read_bytes() for path in [
                output / "manifest.json", output / "summary.json", output / "calls.jsonl",
                *sorted(output.glob("stage-*-request.json")),
                *sorted(output.glob("stage-*-input.json")),
                *sorted(output.glob("stage-*-input-seal.json")),
                *sorted(output.glob("stage-*.json")),
                *sorted(root.glob("stage-*-process-diagnostic.json")),
            ] if path.is_file()}

            def no_asset_scan(*_args, **_kwargs):
                raise AssertionError("verify-only attempted an asset identity scan")

            fake.modes.clear()
            with patch("ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                       return_value=({"audit": {}, "audit_sha256": "e" * 64}, {})), \
                 patch("ygo_eval.native_tenki_placement_validation._validate_saved_build_inputs",
                       return_value={}), \
                 patch("ygo_eval.native_tenki_placement_validation._read_validation_prepared",
                       return_value=({}, PREPARED_HASH)), \
                 patch("ygo_eval.native_tenki_placement._capture_identity",
                       side_effect=no_asset_scan):
                first = native_tenki_placement_validation(args, repo=repo, spec=spec,
                                                          process_runner=fake)
                verification_path = output / "verification.json"
                first_bytes = verification_path.read_bytes()
                second = native_tenki_placement_validation(args, repo=repo, spec=spec,
                                                           process_runner=fake)

            self.assertTrue(first["valid"])
            self.assertEqual(second, first)
            self.assertEqual(verification_path.read_bytes(), first_bytes)
            self.assertNotIn("normal", [mode for mode, _stage in fake.modes])
            self.assertEqual([mode for mode, _stage in fake.modes].count("verify_recorded"), 12)
            self.assertEqual([mode for mode, _stage in fake.modes].count("stats"), 2)
            for path, raw in preserved.items():
                self.assertEqual(path.read_bytes(), raw, path.name)

    def test_prepare_only_resume_rejects_expired_window_without_resuming_or_restarting(self):
        from argparse import Namespace
        from ygo_eval.native_tenki_placement_validation import ScopeSpec

        with _temporary_directory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
            spec = ScopeSpec(
                scope="tenki-placement-validation-v1",
                output_root=Path("data/runtime/synthetic-validation-workflow"),
                baseline_root=Path("synthetic-baseline"),
                limit=6, wall_seconds=7_200, old_consumed=26,
                batch_kind="tenki-placement-validation-v1",
                input_seal_kind="tenki_placement_validation_stage_input_seal",
                runner_role="tenki_placement_validation_runner",
                delivery_sha256="d" * 64,
            )
            root = repo / spec.output_root
            output = root / "research"
            output.mkdir(parents=True)
            (root / "native-artifacts").mkdir()
            runner = root / "native-artifacts" / "tenki-placement-probe.exe"
            runner.write_bytes(b"synthetic runner placeholder")
            unsigned = {
                "schema_version": 1,
                "kind": "native_tenki_placement_validation_manifest",
                "scope": spec.scope,
                "started_at": 1_000,
                "limit": spec.limit,
                "planned_calls": spec.limit,
                "wall_seconds": spec.wall_seconds,
                "old_consumed": spec.old_consumed,
                "baseline_delivery_sha256": spec.delivery_sha256,
                "input_sha256": {role: "e" * 64 for role in MANIFEST_INPUT_ROLES},
                "source": {"identity": "synthetic-source", "files": {}},
                "build": {},
                "assets": {"ordinary": copy.deepcopy(ASSET_IDENTITY)},
                "request": copy.deepcopy(STAGE1_REQUEST),
                "stage1_request_sha256": digest(canonical(STAGE1_REQUEST)),
                "request_derivation": "frozen-tenki-activation-only-worker-path-replaced",
                "proof_ready": False,
                "complete_action_coverage": False,
                "global_optimality": False,
                "native_probability_verified": False,
            }
            manifest = {**unsigned, "context": digest(canonical(unsigned))}
            (output / "manifest.json").write_bytes(canonical(manifest))
            (output / "prepared.json").write_bytes(b"{}")
            args = Namespace(
                baseline_dir=repo / spec.baseline_root,
                runner=runner,
                worker=root / "native-artifacts" / "ygo-engine-worker.exe",
                build_record=root / "build-record.json",
                identity=root / "identity.json",
                window_start=root / "window-start.json",
                output=output,
                prepare_only=True,
                verify_only=False,
            )
            with patch("ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                       return_value=({"audit": {}, "audit_sha256": "e" * 64}, {})), \
                 patch("ygo_eval.native_tenki_placement_validation._validate_saved_build_inputs",
                       return_value={}), \
                 patch("ygo_eval.native_tenki_placement_validation._resume_prepared_validation",
                       side_effect=AssertionError("expired preparation must not resume")), \
                 patch("ygo_eval.native_tenki_placement_validation.time.time",
                       return_value=8_200):
                with self.assertRaisesRegex(ValueError, "validation_window_expired"):
                    native_tenki_placement_validation(args, repo=repo, spec=spec)
            self.assertEqual((output / "manifest.json").read_bytes(), canonical(manifest))
            self.assertEqual((output / "prepared.json").read_bytes(), b"{}")
            self.assertFalse(args.window_start.exists())

    def test_verify_only_missing_stage_reports_partial_without_filling_or_rewriting(self):
        with _temporary_directory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            fake = SyntheticRunner()
            spec, root, output, runner, manifest, args = self._public_verify_fixture(repo, fake)
            source = manifest["source"]
            with patch("ygo_eval.native_tenki_placement_validation.stable_source",
                       return_value=source):
                _run_six_stages(
                    root=root, output=output, runner=runner, repo=repo,
                    manifest=manifest, prepared_hash=PREPARED_HASH,
                    stage1_request=copy.deepcopy(STAGE1_REQUEST),
                    expected_identity=copy.deepcopy(ASSET_IDENTITY), source=source,
                    protected={}, frozen_files={}, process_runner=fake,
                    clock=lambda: 2_000,
                )
            summary_bytes = (output / "summary.json").read_bytes()
            missing = [output / f"stage-6-{suffix}.json" for suffix in
                       ("input", "request", "input-seal", "report")]
            missing.append(output / "stage-6.json")
            for path in missing:
                path.unlink()
            # The synthetic stats boundary models five known completed stages;
            # the missing sixth intent/receipt must never be regenerated.
            fake.consumed = fake.completed = 5
            fake.modes.clear()

            with patch("ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                       return_value=({"audit": {}, "audit_sha256": "e" * 64}, {})), \
                 patch("ygo_eval.native_tenki_placement_validation._validate_saved_build_inputs",
                       return_value={}), \
                 patch("ygo_eval.native_tenki_placement_validation._read_validation_prepared",
                       return_value=({}, PREPARED_HASH)), \
                 patch("ygo_eval.native_tenki_placement._capture_identity",
                       side_effect=AssertionError("asset scan must not run")):
                report = native_tenki_placement_validation(args, repo=repo, spec=spec,
                                                          process_runner=fake)

            self.assertFalse(report["valid"])
            self.assertEqual(report["diagnostic"], "incomplete_stage_receipts")
            self.assertEqual([item["stage"] for item in report["stages"]], [1, 2, 3, 4, 5])
            self.assertEqual(report["new_consumed"], 5)
            self.assertEqual(report["cumulative_consumed"], 31)
            self.assertNotIn("normal", [mode for mode, _stage in fake.modes])
            self.assertEqual([mode for mode, _stage in fake.modes].count("verify_recorded"), 5)
            self.assertEqual([mode for mode, _stage in fake.modes].count("stats"), 1)
            self.assertTrue(all(not path.exists() for path in missing))
            self.assertEqual((output / "summary.json").read_bytes(), summary_bytes)


if __name__ == "__main__":
    unittest.main()
