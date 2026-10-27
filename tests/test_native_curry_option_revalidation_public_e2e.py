"""Public CLI integration for the fixed Curry revalidation scope.

The V3 source and reservation verifiers, preparation checker, stage scheduler,
receipt validators, report validators, and verify-only path are production
code. Only the source collector used for the synthetic workspace, build and
asset capture, candidate-config materialization, clock-independent process
edge, and runner process are supplied by this test.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid
import zipfile
from unittest.mock import patch

import ygo_data.identity as identity_module
import ygo_eval.native_curry_option_validation as curry
import ygo_eval.native_tenki_placement_confirmation as confirmation_build
import ygo_eval.native_tenki_placement_validation as validation_runner
from ygo_eval import research
from ygo_data.identity import canonical
from tests.test_native_curry_option_validation import (
    _idle_event,
    _option_event,
    _place_event,
    _receipt,
)


class CurryOptionRevalidationPublicE2ETests(unittest.TestCase):
    def test_public_prepare_normal_seven_stage_verify_uses_real_v3_gate(self):
        repo = Path(__file__).resolve().parents[1]
        baseline = repo / curry.OPTION_REVALIDATION_SCOPE.baseline_root
        try:
            baseline.lstat()
        except FileNotFoundError:
            self.skipTest("historical V3 recovery baseline is not present")
        test_root = repo / "target" / "curry-option-revalidation-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        run_root = test_root / f"public-e2e-{uuid.uuid4().hex}"
        run_root.mkdir(exist_ok=False)
        spec = replace(
            curry.OPTION_REVALIDATION_SCOPE,
            output_root=Path("target/curry-option-revalidation-tests")
            / run_root.name / "scope",
        )
        root = repo / spec.output_root
        artifact_dir = root / "native-artifacts"
        artifact_dir.mkdir(parents=True)
        runner = artifact_dir / "curry-option-revalidation.exe"
        worker = artifact_dir / "ygo-engine-worker.exe"
        cli = artifact_dir / "ygo-cli.exe"
        for path, contents in (
            (runner, b"synthetic revalidation runner"),
            (worker, b"synthetic worker artifact"),
            (cli, b"synthetic cli artifact"),
        ):
            path.write_bytes(contents)
        # The production prepare path checks the fixed build-record path before
        # invoking its build verification boundary; seed only a synthetic
        # placeholder here, then let `synthetic_build` replace it with the
        # authenticated fixture record.
        (root / "build-record.json").write_bytes(b"synthetic build placeholder")

        source_files = {"synthetic/source.py": hashlib.sha256(b"source bytes").hexdigest()}
        source_head = "synthetic-source-head"
        source = {
            "head": source_head,
            "files": source_files,
            "identity": hashlib.sha256(
                canonical({"head": source_head, "files": source_files})
            ).hexdigest(),
        }
        ordinary = {"identity": "b" * 64, "asset_role": "ordinary"}
        tournament = {"identity": "c" * 64, "asset_role": "tournament"}
        artifacts = {
            role: hashlib.sha256(path.read_bytes()).hexdigest()
            for role, path in (("runner", runner), ("worker", worker), ("cli", cli))
        }
        artifact_hashes = {"runner": artifacts["runner"],
                           "worker": artifacts["worker"], "cli": artifacts["cli"]}

        def signed(kind: str, fields: dict) -> dict:
            unsigned = {"kind": kind, **fields}
            return {**unsigned, "identity": hashlib.sha256(canonical(unsigned)).hexdigest()}

        def synthetic_build(_args, _repo, _root, paths, observed_source):
            self.assertEqual(observed_source, source)
            build = signed("build_record", {
                "status": "recorded",
                "reproducible_build_proven": False,
                "source_before": source,
                "source_after": source,
                "artifacts": artifact_hashes,
            })
            paths["build_record"].write_bytes(canonical(build))
            return (
                build,
                artifact_hashes,
                paths["cli"],
                hashlib.sha256(paths["build_record"].read_bytes()).hexdigest(),
            )

        def synthetic_archive(_repo, _root, observed_source):
            archive_path = root / "source-native.zip"
            listing_path = root / "source-native-file-list.json"
            listing = {
                "schema_version": 1,
                "kind": "workspace_source_archive",
                "head": observed_source["head"],
                "source_identity": observed_source["identity"],
                "file_count": len(observed_source["files"]),
                "files": observed_source["files"],
            }
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("synthetic/source.py", b"source bytes")
            listing_path.write_bytes(canonical(listing))
            return {
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "file_list_sha256": hashlib.sha256(listing_path.read_bytes()).hexdigest(),
                "file_count": len(observed_source["files"]),
            }

        def synthetic_configs(_repo, destination_root, _worker, _candidate_root):
            result = {}
            for role in ("ordinary", "tournament"):
                path = destination_root / f"{role}-candidate.toml"
                path.write_text(f"role = '{role}'\n", encoding="utf-8")
                result[role] = path
            return result

        def synthetic_identity(_repo, _cli, _configs, output_path):
            self.assertTrue((root / "window-start.json").is_file(),
                            "window must be persisted before the asset scan boundary")
            value = signed("workspace_identity", {
                "source": source,
                "consistent": True,
                "build_provenance": "unverified",
                "reproducible_build_proven": False,
                "cli_sha256": artifact_hashes["cli"],
                "runtimes": {"ordinary": {}, "tournament": {}},
            })
            output_path.write_bytes(canonical(value))
            return value

        class SyntheticRunner:
            def __init__(self):
                self.completed = 0
                self.normal_stages: list[int] = []
                self.verified_stages: list[int] = []
                self.modes: list[str] = []

            def stats(self):
                return {
                    "consumed": self.completed,
                    "completed": self.completed,
                    "unknown": 0,
                    "reserved": 0,
                    "abandoned": 0,
                    "limit": spec.limit,
                }

            def __call__(self, command, *, cwd, capture_output, timeout, check):
                del cwd, capture_output, timeout, check
                command = list(command)
                input_path = Path(command[1])
                invocation = json.loads(input_path.read_bytes())
                if "--preflight-only" in command:
                    self.modes.append("preflight")
                    result = {
                        "preflight_passed": True,
                        "native_calls": 0,
                        "context": invocation["context"],
                        "identity_sha256": invocation["expected_identity"]["identity"],
                    }
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(result).encode(), b"synthetic preflight trace\n",
                    )
                if "--stats" in command:
                    self.modes.append("stats")
                    return subprocess.CompletedProcess(
                        command, 0,
                        json.dumps({"native_calls": 0, "ledger": self.stats()}).encode(),
                        b"synthetic stats trace\n",
                    )
                if "--verify-recorded" in command:
                    self.modes.append("verify-recorded")
                    receipt = json.loads(Path(invocation["output"]).read_bytes())
                    self.verified_stages.append(receipt["stage"])
                    result = {"native_calls": 0, "verified_recorded": True}
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(result).encode(), b"synthetic verify trace\n",
                    )
                if "--prepared-sha256" not in command:
                    raise AssertionError("unexpected runner command at synthetic process edge")

                stage = invocation["stage"]
                request = invocation["request"]
                if invocation.get("batch_kind") != spec.batch_kind:
                    raise AssertionError("normal input lost the fixed revalidation batch kind")
                if stage == 2:
                    events = [_idle_event(10), _place_event(11)]
                    receipt = _receipt(stage, request, events=events,
                                       pending=events[-1]["fields"]["prompt"])
                elif stage == 3:
                    events = [_idle_event(10), _place_event(11), _option_event(12)]
                    receipt = _receipt(stage, request, events=events,
                                       pending=events[-1]["fields"]["prompt"])
                else:
                    receipt = _receipt(stage, request)
                ledger = {
                    "consumed": stage,
                    "completed": stage,
                    "unknown": 0,
                    "reserved": 0,
                    "abandoned": 0,
                    "limit": spec.limit,
                }
                receipt.update({
                    "kind": curry._report_kind(spec, "stage"),
                    "scope": spec.scope,
                    "context": invocation["context"],
                    "ledger": ledger,
                    "assets_before": copy.deepcopy(invocation["expected_identity"]),
                    "assets_after": copy.deepcopy(invocation["expected_identity"]),
                })
                receipt_path = Path(invocation["output"])
                with receipt_path.open("xb") as stream:
                    stream.write(canonical(receipt))
                ledger_path = Path(invocation["ledger"])
                ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with ledger_path.open("ab") as stream:
                    stream.write(f"synthetic complete stage {stage}\n".encode())
                self.completed = stage
                self.normal_stages.append(stage)
                output = {
                    "successful": True,
                    "native_calls": 1,
                    "ledger": ledger,
                    "certified_historical_consumed": 33,
                    "policy_reserved": 7,
                    "planning_base": 40,
                    "reservation_id": spec.reservation_id,
                    "reservation_policy_id": spec.reservation_policy_id,
                    "new_consumed": stage,
                    "certified_consumed_including_new": 33 + stage,
                    "planning_total": 40 + stage,
                    "old_confirmation_actual_consumed": None,
                    "actual_all_history_cumulative": None,
                    "unknown": 0,
                }
                return subprocess.CompletedProcess(
                    command, 0, json.dumps(output).encode(), b"synthetic normal trace\n",
                )

        synthetic_runner = SyntheticRunner()
        baseline = repo / spec.baseline_root
        original_baseline_gate = curry._verify_option_revalidation_baseline
        real_source_collector = identity_module.stable_source
        baseline_gate_calls: list[Path] = []
        handler_errors: list[Exception] = []
        gate_diagnostics: list[dict] = []

        original_public_handler = curry.native_curry_option_revalidation

        def record_handler_error(args):
            try:
                return original_public_handler(args)
            except Exception as exc:
                handler_errors.append(exc)
                raise

        def real_v3_gate(repo_path, baseline_path, **kwargs):
            # Keep the production V3 recovery and reservation verification intact.
            # The real source collector is a test boundary so it remains bound to
            # the already-authenticated historical tree while the new run uses a
            # separate synthetic workspace identity.
            baseline_gate_calls.append(Path(baseline_path))
            from ygo_eval.curry_ledger_handoff_recovery import _tree_snapshot

            baseline_before = _tree_snapshot(Path(baseline_path))
            source_observations: list[dict] = []

            def tracked_source(source_root):
                observed = real_source_collector(source_root)
                source_observations.append(observed)
                return observed

            try:
                return original_baseline_gate(
                    repo_path, baseline_path, source_collector=tracked_source,
                )
            except Exception as exc:
                baseline_after = _tree_snapshot(Path(baseline_path))
                changed = sorted(
                    key for key in set(baseline_before) | set(baseline_after)
                    if baseline_before.get(key) != baseline_after.get(key)
                )
                gate_diagnostics.append({
                    "error": f"{type(exc).__name__}: {exc}",
                    "source_observation_count": len(source_observations),
                    "source_observations_equal": (
                        not source_observations
                        or all(value == source_observations[0]
                               for value in source_observations[1:])
                    ),
                    "changed_baseline_paths": changed,
                })
                raise

        synthetic_source = lambda _repo: source
        original_run_process = validation_runner._run_process

        def process_boundary(runner_path, input_path, repo_path, process_root, mode, **kwargs):
            kwargs.pop("process_runner", None)
            return original_run_process(
                runner_path, input_path, repo_path, process_root, mode,
                process_runner=synthetic_runner, **kwargs,
            )

        original_pinned_inputs = curry._pinned_inputs

        def synthetic_pinned_inputs(scope):
            pinned = original_pinned_inputs(scope)
            if scope.scope == curry.CURRY_SCOPE.scope:
                # The frozen validation candidate keeps its historical codec
                # identity, while this test's newer worktree includes opcode 56.
                pinned["adapter_codec"] = curry.HISTORICAL_SOURCE_TRANSITION[
                    "current_sha256"
                ]
            elif scope.scope == curry.OPTION_REVALIDATION_SCOPE.scope:
                pinned["adapter_codec"] = hashlib.sha256(
                    (repo / "crates/ygo-engine-adapter/src/codec.rs").read_bytes()
                ).hexdigest()
            return pinned

        arguments = [
            "ygo-research", "native-curry-option-revalidation",
            "--baseline-dir", str(baseline),
            "--preparation", str(repo / curry.PREPARATION_PATH),
            "--cases", str(repo / curry.FROZEN_CASES_PATH),
            "--core-source", str(repo / "data/tmp/ocgcore-source/operations.cpp"),
            "--runner", str(runner), "--worker", str(worker),
            "--build-record", str(root / "build-record.json"),
            "--identity", str(root / "identity.json"),
            "--window-start", str(root / "window-start.json"),
            "--output", str(root / "research"),
        ]

        def invoke(extra: list[str]) -> tuple[int, dict]:
            stdout = io.StringIO()
            with patch("sys.argv", [*arguments, *extra]), contextlib.redirect_stdout(stdout):
                exit_code = research.main()
            try:
                document = json.loads(stdout.getvalue())
            except json.JSONDecodeError as exc:
                cause = handler_errors[-1] if handler_errors else None
                raise AssertionError(
                    f"public CLI emitted no JSON (exit={exit_code}, stdout={stdout.getvalue()!r}, "
                    f"handler_error={type(cause).__name__ if cause else None}: {cause}, "
                    f"gate_diagnostics={gate_diagnostics})"
                ) from exc
            return exit_code, document

        try:
            with (
                # The current codec includes Ground's opcode56 parser. Keep
                # this new byte identity local to the synthetic exercise; the
                # production historical Curry pin remains unchanged.
                patch.dict(curry.PINNED_INPUT_SHA256, {
                    "adapter_codec": hashlib.sha256(
                        (repo / "crates/ygo-engine-adapter/src/codec.rs").read_bytes()
                    ).hexdigest(),
                }),
                patch.object(curry, "_pinned_inputs", side_effect=synthetic_pinned_inputs),
                patch.object(curry, "OPTION_REVALIDATION_SCOPE", spec),
                patch.object(curry, "native_curry_option_revalidation",
                             side_effect=record_handler_error),
                patch.object(curry, "_verify_option_revalidation_baseline", side_effect=real_v3_gate),
                patch.object(identity_module, "stable_source", side_effect=synthetic_source),
                patch("ygo_eval.native_tenki_placement._candidate_configs",
                      side_effect=synthetic_configs),
                patch("ygo_eval.native_tenki_placement._archive_current_source",
                      side_effect=synthetic_archive),
                patch("ygo_eval.native_tenki_placement._capture_identity",
                      side_effect=synthetic_identity),
                patch.object(confirmation_build, "_verify_build_and_identity",
                             side_effect=synthetic_build),
                patch.object(confirmation_build, "_verify_workspace_identity",
                             return_value=(ordinary, tournament)),
                patch.object(validation_runner, "_run_process", side_effect=process_boundary),
            ):
                prep_exit, prepared = invoke(["--prepare-only"])
                self.assertEqual(prep_exit, 0, prepared)
                self.assertTrue(prepared["prepared"])
                self.assertEqual(prepared["native_calls"], 0)
                self.assertEqual(synthetic_runner.normal_stages, [])
                self.assertFalse((root / "research" / "calls.jsonl").exists())

                manifest = json.loads((root / "research" / "manifest.json").read_bytes())
                self.assertEqual(manifest["scope"], "curry-option-revalidation-v1")
                self.assertEqual(manifest["kind"], "native_curry_option_revalidation_manifest")
                self.assertEqual(len(manifest["input_sha256"]), 22)
                self.assertEqual(set(manifest["input_sha256"]),
                                 set(curry.OPTION_REVALIDATION_INPUT_ROLES))
                self.assertEqual(manifest["input_sha256"]["baseline_recovery"],
                                 spec.baseline_recovery_sha256)
                self.assertEqual(manifest["input_sha256"]["baseline_delivery"],
                                 spec.delivery_sha256)
                self.assertEqual(manifest["input_sha256"]["consumption_reservation"],
                                 spec.reservation_sha256)
                self.assertEqual(manifest["certified_historical_consumed"], 33)
                self.assertEqual(manifest["policy_reserved"], 7)
                self.assertEqual(manifest["planning_base"], 40)
                self.assertEqual(manifest["reservation_id"], spec.reservation_id)

                normal_exit, summary = invoke([])
                self.assertEqual(normal_exit, 0, summary)
                self.assertTrue(summary["successful"])
                self.assertEqual(synthetic_runner.normal_stages, list(range(1, 8)))
                self.assertEqual(summary["new_consumed"], 7)
                self.assertEqual(summary["certified_consumed_including_new"], 40)
                self.assertEqual(summary["planning_total"], 47)
                self.assertIsNone(summary["old_confirmation_actual_consumed"])
                self.assertIsNone(summary["actual_all_history_cumulative"])
                self.assertTrue(summary["stages"][4]["independent_replay_matches"])
                self.assertTrue(summary["stages"][6]["independent_replay_matches"])

                verify_exit, verification = invoke(["--verify-only"])
                self.assertEqual(verify_exit, 0, verification)
                self.assertTrue(verification["valid"])
                self.assertEqual(verification["native_calls"], 0)
                self.assertEqual(synthetic_runner.verified_stages, list(range(1, 8)))
                self.assertEqual(baseline_gate_calls, [baseline, baseline, baseline])
                self.assertEqual(synthetic_runner.normal_stages, list(range(1, 8)))
        finally:
            if run_root.parent == test_root and run_root.exists():
                shutil.rmtree(run_root)


if __name__ == "__main__":
    unittest.main()
