import argparse
import hashlib
import json
import shutil
import subprocess
import unittest
import uuid
from jsonschema.exceptions import ValidationError
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_data.identity import canonical, digest

from ygo_eval.native_tenki_placement_confirmation import (
    LIMIT,
    OLD_CONSUMED,
    OLD_LEDGER_CONTRACTS,
    SCOPE,
    DIAGNOSTICS_RELATIVE,
    OUTPUT_RELATIVE,
    PROMPT_BASELINE_RELATIVE,
    _candidate_request,
    _verify_history,
    _preflight_output_matches,
    _validate_stage_receipt,
    _stats_for_missing_ledger,
    add_arguments,
    _process_exit_succeeded,
    summarize_confirmation,
    validate_report,
)


def _successful_opcode15_receipt(stage: int) -> tuple[dict, dict]:
    request = {"decisions": []}
    actions = []
    records = []
    for index, sequence in enumerate((3, 7)):
        record = (
            (69_247_929).to_bytes(4, "little")
            + bytes([0, 1])
            + sequence.to_bytes(4, "little")
            + bytes([1 << index, 0, 0, 0])
        )
        records.extend(record)
        actions.append({
            "card_ids": [69_247_929],
            "choice": {"kind": "cards", "indices": [index]},
            "bytes": list(bytes(4) + (1).to_bytes(4, "little") + index.to_bytes(4, "little")),
        })
    raw = bytes([15, 0, 0]) + (1).to_bytes(4, "little") + (1).to_bytes(4, "little") + (2).to_bytes(4, "little") + bytes(records)
    prompt = {"id": 91, "opcode": 15, "player": 0, "actions": actions}
    receipt = {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_stage",
        "scope": SCOPE,
        "context": "a" * 64,
        "stage": stage,
        "request": request,
        "successful": True,
        "diagnostic": None,
        "ledger": {"consumed": stage, "completed": stage, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": LIMIT},
        "assets_unchanged": True,
        "assets_before": {},
        "assets_after": {},
        "window_valid_at_result": True,
        "validation": {"Ok": {"response_oracle_matches": True}},
        "result": {"Ok": {
            "status": "decision_required",
            "error": None,
            "coverage_gaps": [],
            "resolved_decisions": [],
            "prompt": prompt,
            "events": [{"sequence": 91, "opcode": 15, "raw": list(raw), "supported": True, "fields": {"prompt": prompt}}],
        }},
        "independent_replay_matches": True if stage == 6 else None,
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    return receipt, request


class TenkiPlacementConfirmationTests(unittest.TestCase):
    def _synthetic_repo(self):
        root = Path(__file__).resolve().parents[1] / "target" / ("tenki-confirmation-" + uuid.uuid4().hex)
        root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, root)
        return root

    def test_stage_five_and_six_validate_complete_opcode15_receipts(self):
        for stage in (5, 6):
            with self.subTest(stage=stage):
                receipt, request = _successful_opcode15_receipt(stage)
                _validate_stage_receipt(receipt, request, "a" * 64, stage, {})

    def test_missing_ledger_is_unknown_after_a_runner_attempt(self):
        before_first_attempt = _stats_for_missing_ledger(normal_attempted=False)
        self.assertEqual(before_first_attempt["consumed"], 0)
        self.assertEqual(before_first_attempt["unknown"], 0)

        after_runner_attempt = _stats_for_missing_ledger(normal_attempted=True)
        self.assertIsNone(after_runner_attempt)

    def test_preflight_binds_the_expected_ordinary_runtime_identity(self):
        manifest = {"context": "a" * 64}
        ordinary = {"identity": "b" * 64}
        workspace = {"identity": "c" * 64}
        result = {
            "context": "a" * 64,
            "identity_sha256": "b" * 64,
            "native_calls": 0,
            "preflight_passed": True,
            "stage": 1,
        }
        self.assertTrue(_preflight_output_matches(result, manifest, ordinary, calls_present=False))
        self.assertFalse(_preflight_output_matches(result, manifest, workspace, calls_present=False))
        self.assertFalse(_preflight_output_matches(result, manifest, ordinary, calls_present=True))

    def test_new_scope_is_fixed_and_not_the_sealed_placement_scope(self):
        self.assertEqual(SCOPE, "tenki-placement-confirmation-v1")
        self.assertEqual(LIMIT, 6)
        self.assertEqual(OLD_CONSUMED, 26)
        self.assertNotEqual(SCOPE, "tenki-placement-probe-v1")

    def test_manifest_requires_hashes_for_the_public_activation_source(self):
        unsigned = {
            "schema_version": 1,
            "kind": "native_tenki_placement_confirmation_manifest",
            "scope": SCOPE,
            "limit": LIMIT,
            "wall_seconds": 7200,
            "started_at": 1,
            "old_consumed": OLD_CONSUMED,
            "input_sha256": {
                "prompt_source_stage1": "a" * 64,
                "prompt_source_stage2_request": "b" * 64,
            },
            "source": {},
            "build": {},
            "assets": {},
            "stage1_request_sha256": "c" * 64,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        manifest = {**unsigned, "context": digest(canonical(unsigned))}
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-confirmation.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(manifest)
        self.assertTrue(validate_report(manifest, repo))

        missing = dict(unsigned)
        missing_hashes = dict(unsigned["input_sha256"])
        del missing_hashes["prompt_source_stage1"]
        missing["input_sha256"] = missing_hashes
        missing_manifest = {**missing, "context": digest(canonical(missing))}
        with self.assertRaises(ValueError):
            validate_report(missing_manifest, repo)
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(missing_manifest)

    def test_candidate_request_derives_activation_from_prompt_probe_history(self):
        repo = self._synthetic_repo()
        banlist = repo / "data/runtime/banlist.json"
        banlist.parent.mkdir(parents=True)
        banlist.write_bytes(b'{"synthetic":true}')
        temp_root = repo / OUTPUT_RELATIVE / "test-data"
        temp_root.mkdir(parents=True, exist_ok=True)
        expected_source = {
            "schema_version": 1,
            "kind": "tenki_prompt_probe_stage_1",
            "prompt": {"id": 101},
        }
        expected_parent = {"kind": "tenki_prompt_probe_stage_2_request", "decisions": []}
        seen = {}

        def derive(stage_one, stage_two):
            seen["stage_one"] = stage_one
            seen["stage_two"] = stage_two
            return {
                "protocol_version": 2,
                "probe_only": False,
                "scenario": None,
                "interruption": None,
                "first_turn": None,
                "research_capture": None,
                "engine": {"worker_path": "historical-worker"},
                "decisions": [],
            }

        preparation = {
            "candidates": [{"case": {"case_id": "prompt-13-tenki-v1"}}],
        }
        preparation_bytes = json.dumps(preparation).encode("utf-8")
        worker = temp_root / "frozen-worker.exe"
        prompt_baseline = temp_root / "candidate-source"
        evidence = prompt_baseline / "research"
        evidence.mkdir(parents=True, exist_ok=True)
        for filename, value in (
            ("stage-1.json", expected_source),
            ("stage-2-request.json", expected_parent),
        ):
            path = evidence / filename
            encoded = json.dumps(value).encode("utf-8")
            if path.exists():
                self.assertEqual(path.read_bytes(), encoded)
            else:
                path.write_bytes(encoded)
        with (
            patch("ygo_eval.native_tenki_placement._activation_from_history", side_effect=derive),
            patch("ygo_eval.native_tenki_placement._read", return_value=(preparation_bytes, "a" * 64)),
            patch("ygo_eval.research.validate_sources"),
        ):
            request, frozen_case = _candidate_request(repo, prompt_baseline, worker)

        self.assertEqual(seen, {"stage_one": expected_source, "stage_two": expected_parent})
        self.assertEqual(request["engine"]["worker_path"], str(worker))
        self.assertEqual(frozen_case["case_id"], "prompt-13-tenki-v1")
        self.assertEqual(
            frozen_case["old_stage1_sha256"],
            hashlib.sha256(json.dumps(expected_source).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            frozen_case["old_stage2_request_sha256"],
            hashlib.sha256(json.dumps(expected_parent).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(PROMPT_BASELINE_RELATIVE.as_posix(), "data/runtime/p1-tenki-probe-native-2026-10-21")

    def test_cli_modes_are_mutually_exclusive_and_keep_fixed_paths(self):
        parser = argparse.ArgumentParser()
        add_arguments(parser)
        base = [
            "--baseline-dir", "baseline",
            "--runner", "runner",
            "--worker", "worker",
            "--build-record", "build",
            "--identity", "identity",
            "--window-start", "window",
            "--output", "output",
        ]
        args = parser.parse_args(base + ["--prepare-only"])
        self.assertTrue(args.prepare_only)
        self.assertFalse(args.verify_only)
        args = parser.parse_args(base + ["--verify-only"])
        self.assertTrue(args.verify_only)
        with self.assertRaises(SystemExit):
            parser.parse_args(base + ["--prepare-only", "--verify-only"])

    def test_success_requires_all_six_bound_receipts_and_settled_budget(self):
        stages = [
            {
                "stage": stage,
                "successful": True,
                "receipt_sha256": f"{stage:064x}",
                "diagnostic_sha256": f"{stage + 10:064x}",
                "independent_replay_matches": True if stage in (4, 6) else None,
            }
            for stage in range(1, 7)
        ]
        stats = {
            "consumed": 6,
            "completed": 6,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": 6,
        }
        report = summarize_confirmation("a" * 64, stages, stats)
        self.assertTrue(report["successful"])
        self.assertEqual(report["cumulative_consumed"], 32)
        self.assertFalse(report["proof_ready"])

        incomplete = summarize_confirmation("a" * 64, stages[:-1], stats)
        self.assertFalse(incomplete["successful"])
        self.assertEqual(incomplete["old_consumed"], 26)

    def test_runner_success_requires_zero_exit_even_if_stdout_claims_success(self):
        success = subprocess.CompletedProcess(["runner"], 0, b'{"successful":true}', b"")
        failed = subprocess.CompletedProcess(["runner"], 1, b'{"successful":true}', b"")
        self.assertTrue(_process_exit_succeeded(success))
        self.assertFalse(_process_exit_succeeded(failed))
        self.assertFalse(_process_exit_succeeded(None))

    def test_report_validator_rejects_qualification_and_wrong_scope(self):
        report = {
            "schema_version": 1,
            "kind": "native_tenki_placement_confirmation_prepared",
            "scope": SCOPE,
            "context": "a" * 64,
            "prepared": True,
            "native_calls": 0,
            "planned_calls": 6,
            "first_stage_request_sha256": "b" * 64,
            "preflight_diagnostic_sha256": "c" * 64,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        repo = Path(__file__).resolve().parents[1]
        self.assertTrue(validate_report(report, repo))
        changed = dict(report, proof_ready=True)
        with self.assertRaises(ValueError):
            validate_report(changed, repo)

    def test_schema_accepts_explicit_unknown_stage_evidence_without_guessing_zero(self):
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-confirmation.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        stage = {
            "schema_version": 1,
            "kind": "native_tenki_placement_confirmation_stage",
            "scope": SCOPE,
            "context": "a" * 64,
            "stage": 1,
            "successful": False,
            "native_calls": None,
            "diagnostic": "runner_start_failed",
            "receipt_sha256": None,
            "diagnostic_sha256": "b" * 64,
            "independent_replay_matches": None,
            "ledger": None,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        Draft202012Validator(schema).validate(stage)
        summary = summarize_confirmation(
            "a" * 64,
            [{key: stage[key] for key in (
                "stage", "successful", "receipt_sha256", "diagnostic_sha256", "independent_replay_matches"
            )}],
            None,
            "ledger_consumption_unknown",
        )
        Draft202012Validator(schema).validate(summary)

    def test_seven_historical_ledgers_reaudit_read_only_without_runner(self):
        repo = Path(__file__).resolve().parents[1]
        try:
            (repo / DIAGNOSTICS_RELATIVE).lstat()
        except FileNotFoundError:
            self.skipTest("historical diagnostics baseline is not present")
        ledger_paths = [repo / item[1] for item in OLD_LEDGER_CONTRACTS]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in ledger_paths}
        experiment_root = repo / OUTPUT_RELATIVE

        def runtime_snapshot():
            if not experiment_root.exists():
                return None
            entries = sorted(path.name for path in experiment_root.iterdir())
            research_root = experiment_root / "research"
            research = {
                path.relative_to(research_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in research_root.rglob("*")
                if path.is_file()
            } if research_root.exists() else {}
            protected_names = (
                "window-start.json",
                "identity.json",
                "build-record.json",
                "source-native.zip",
                "source-native-file-list.json",
                "research/calls.jsonl",
                "research/manifest.json",
                "research/prepared.json",
            )
            protected = {}
            for name in protected_names:
                path = experiment_root / name
                protected[name] = (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file()
                    else None
                )
            return entries, research, protected

        before_root = runtime_snapshot()
        original_popen = subprocess.Popen

        def allow_git_only(command, *args, **kwargs):
            executable = command[0] if isinstance(command, (list, tuple)) else command
            self.assertIn(Path(str(executable)).name.lower(), {"git", "git.exe"})
            return original_popen(command, *args, **kwargs)

        with patch.object(subprocess, "Popen", side_effect=allow_git_only):
            with self.assertRaisesRegex(ValueError, "historical_protected_input_changed"):
                _verify_history(repo, repo / DIAGNOSTICS_RELATIVE)
            report, _protected, _history = _verify_history(
                repo, repo / DIAGNOSTICS_RELATIVE,
                "curry-option-validation-v1",
            )
        self.assertEqual(report["old_consumed"], 26)
        self.assertEqual(report["unknown"], 0)
        self.assertEqual(report["scope_protected_source_change"], {
            "scope": "curry-option-validation-v1",
            "path": "crates/ygo-engine-adapter/src/codec.rs",
            "historical_sha256": "224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e",
            "current_sha256": "e8f97eefcf93ef626d2ecbc785661fde2fee47b0525e110ec7aee9a185aad133",
            "historical_bytes_verified_from_archive": True,
        })
        self.assertEqual(len(report["ledgers"]), 7)
        self.assertEqual(before_root, runtime_snapshot())
        self.assertEqual(
            before_root[2]["research/calls.jsonl"],
            "5daf512e4381803663df466575f4706f083843629ae660caf8c557ebecc8bc21",
        )
        self.assertEqual(
            before,
            {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in ledger_paths},
        )
        changed = dict(report, scope="tenki-placement-probe-v1")
        with self.assertRaises(ValueError):
            validate_report(changed, repo)


if __name__ == "__main__":
    unittest.main()
