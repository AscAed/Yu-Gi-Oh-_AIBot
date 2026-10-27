"""Fixed V3-reservation-bound Curry option verification scope tests."""
from __future__ import annotations

import copy
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import uuid
from unittest.mock import patch

from jsonschema import Draft202012Validator

import ygo_eval.native_curry_option_validation as curry


REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "schemas" / "native-curry-option-verification.schema.json"
RESERVATION_SHA256 = "14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f"
ACCEPTANCE_SHA256 = "704a72b2ad65ba95874030f199158a673ce18e19901b29d9bfb63f3fb8d78318"
RESERVATION_ID = "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63"
POLICY_ID = "curry-unknown-reserve-seven-v1"
HASH_A = "a" * 64
HASH_B = "b" * 64


def _stats(consumed: int, *, unknown: int = 0) -> dict:
    return {
        "consumed": consumed,
        "completed": consumed - unknown,
        "unknown": unknown,
        "reserved": 0,
        "abandoned": 0,
        "limit": 7,
    }


def _stage(stage: int) -> dict:
    return {
        "stage": stage,
        "successful": True,
        "native_calls": 1,
        "diagnostic": None,
        "receipt_sha256": f"{stage:064x}",
        "diagnostic_sha256": HASH_A,
        "independent_replay_matches": True if stage in (5, 7) else None,
        "ledger": _stats(stage),
    }


class CurryOptionVerificationTests(unittest.TestCase):
    def test_verification_scope_is_a_third_fixed_and_reservation_bound_scope(self):
        spec = curry.OPTION_VERIFICATION_SCOPE
        self.assertEqual(spec.scope, "curry-option-verification-v1")
        self.assertEqual(spec.output_root, Path(
            "data/runtime/p1-curry-option-verification-native-2026-10-25"
        ))
        self.assertEqual(spec.baseline_root, Path(
            "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"
        ))
        self.assertEqual(spec.batch_kind, "curry-option-verification-v1")
        self.assertEqual(spec.input_seal_kind, "curry_option_verification_stage_input_seal")
        self.assertEqual(spec.runner_role, "curry_option_verification_runner")
        self.assertEqual(spec.report_prefix, "native_curry_option_verification")
        self.assertEqual(spec.baseline_acceptance_sha256, ACCEPTANCE_SHA256)
        self.assertEqual(spec.reservation_sha256, RESERVATION_SHA256)
        self.assertEqual(spec.reservation_id, RESERVATION_ID)
        self.assertEqual(len(curry._manifest_roles(spec)), 21)
        self.assertNotIn("baseline_delivery", curry._manifest_roles(spec))
        self.assertIn("baseline_acceptance", curry._manifest_roles(spec))
        self.assertIn("consumption_reservation", curry._manifest_roles(spec))
        self.assertEqual(curry._window_kind(spec), "curry_option_verification_window_start")

    def test_old_validation_manifest_and_candidate_hashes_are_independently_fixed(self):
        self.assertEqual(curry.OLD_VALIDATION_MANIFEST_SHA256,
                         "b170c35ff48fb4c22892ecffd15324cc7ecc5dfe318a7f1668b0f448756641c3")
        self.assertEqual(curry.OLD_VALIDATION_ORDINARY_CONFIG_SHA256,
                         "d89c207ddc0370aa508067c5b86430504251034294b19caf16cc978355edfbce")
        self.assertEqual(curry.OLD_VALIDATION_TOURNAMENT_CONFIG_SHA256,
                         "e481fa97a036e64687ce54c108ef979811601d11ee5f4b2c66c543f50b681822")

    def test_verification_manifest_source_uses_only_dedicated_baseline_role_pins(self):
        from ygo_eval.curry_input_recovery_audit import (
            _PinnedFile, _SourceDescription,
        )

        spec = curry.OPTION_VERIFICATION_SCOPE
        semantic = {
            "manifest_base_request": "a" * 64,
            "manifest_candidate_case": "b" * 64,
        }
        file_roles = [role for role in curry._manifest_roles(spec)
                      if role not in {
                          "base_request", "candidate_case",
                          "baseline_acceptance", "consumption_reservation",
                      }]
        generic_pins = tuple(
            _PinnedFile(f"manifest_input_{role}", f"synthetic/{role}.bin", "c" * 64)
            for role in file_roles
        )
        acceptance_pin = spec.baseline_acceptance_sha256
        reservation_pin = spec.reservation_sha256
        dedicated_pins = (
            _PinnedFile("baseline_acceptance", "synthetic/acceptance.json", acceptance_pin),
            _PinnedFile("consumption_reservation", "synthetic/reservation.json", reservation_pin),
        )
        option_scope = _SourceDescription(
            role="option_verification_scope",
            files=generic_pins + dedicated_pins,
            semantic_hashes=tuple(semantic.items()),
        )
        sources = _SourceDescription(role="root", children=(option_scope,))
        hashes = {
            role: (
                semantic[f"manifest_{role}"] if role in {"base_request", "candidate_case"}
                else acceptance_pin if role == "baseline_acceptance"
                else reservation_pin if role == "consumption_reservation"
                else "c" * 64
            )
            for role in curry._manifest_roles(spec)
        }
        request = {
            "protocol_version": 2, "seed": 1, "decisions": [],
            "engine": {"worker_path": "synthetic-worker.exe"},
        }
        manifest = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "manifest"),
            "scope": spec.scope,
            "batch_kind": spec.batch_kind,
            "context": "0" * 64,
            "started_at": 1,
            "limit": spec.limit,
            "planned_calls": spec.limit,
            "wall_seconds": spec.wall_seconds,
            "baseline_acceptance_sha256": acceptance_pin,
            **curry._verification_manifest_fields(spec),
            "input_sha256": hashes,
            "source": {"identity": "synthetic"},
            "historical_source_transition": copy.deepcopy(curry.HISTORICAL_SOURCE_TRANSITION),
            "build": {"runner": "synthetic"},
            "assets": {"ordinary": "synthetic"},
            "stage1_request_sha256": hashlib.sha256(curry.canonical(request)).hexdigest(),
            "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
            "request": request,
            **curry.FLAGS,
        }
        unsigned = {key: value for key, value in manifest.items() if key != "context"}
        manifest["context"] = hashlib.sha256(curry.canonical(unsigned)).hexdigest()

        self.assertTrue(curry.validate_curry_report(manifest, spec=spec, _sources=sources))

        changed_source = _SourceDescription(
            role="option_verification_scope",
            files=generic_pins + (
                _PinnedFile("baseline_acceptance", "synthetic/acceptance.json", "f" * 64),
                dedicated_pins[1],
            ),
            semantic_hashes=tuple(semantic.items()),
        )
        changed_sources = _SourceDescription(role="root", children=(changed_source,))
        with self.assertRaisesRegex(ValueError, "curry_manifest_binding_invalid|curry_manifest_input_hashes_invalid"):
            curry.validate_curry_report(manifest, spec=spec, _sources=changed_sources)

    def test_summary_uses_separate_certified_and_planning_accounting(self):
        spec = curry.OPTION_VERIFICATION_SCOPE
        summary = curry.summarize_curry_validation(
            "c" * 64, [_stage(stage) for stage in range(1, 8)], _stats(7), spec=spec,
        )
        self.assertEqual(summary["new_consumed"], 7)
        self.assertEqual(summary["certified_historical_consumed"], 32)
        self.assertEqual(summary["policy_reserved"], 7)
        self.assertEqual(summary["planning_base"], 39)
        self.assertEqual(summary["certified_consumed_including_new"], 39)
        self.assertEqual(summary["planning_total"], 46)
        self.assertIsNone(summary["old_confirmation_actual_consumed"])
        self.assertIsNone(summary["actual_all_history_cumulative"])
        self.assertNotIn("cumulative_consumed", summary)
        self.assertTrue(summary["successful"])
        self.assertTrue(curry.validate_curry_report(summary, spec=spec))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(summary)

    def test_summary_keeps_new_consumption_unknown_when_ledger_is_unavailable(self):
        spec = curry.OPTION_VERIFICATION_SCOPE
        summary = curry.summarize_curry_validation(
            "c" * 64, [], None, "ledger_missing_after_normal_attempt", spec,
        )
        self.assertIsNone(summary["new_consumed"])
        self.assertIsNone(summary["certified_consumed_including_new"])
        self.assertIsNone(summary["planning_total"])
        self.assertIsNone(summary["old_confirmation_actual_consumed"])
        self.assertIsNone(summary["actual_all_history_cumulative"])
        self.assertFalse(summary["successful"])
        self.assertTrue(curry.validate_curry_report(summary, spec=spec))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(summary)

    def test_new_schema_accepts_exact_accounting_and_rejects_claimed_actual_total(self):
        document = {
            "schema_version": 1,
            "kind": "native_curry_option_verification_summary",
            "scope": "curry-option-verification-v1",
            "context": HASH_A,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "certified_historical_consumed": 32,
            "policy_reserved": 7,
            "planning_base": 39,
            "reservation_id": RESERVATION_ID,
            "reservation_policy_id": POLICY_ID,
            "successful": True,
            "new_consumed": 7,
            "certified_consumed_including_new": 39,
            "planning_total": 46,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
            "unknown": 0,
            "ledger": _stats(7),
            "stages": [_stage(stage) for stage in range(1, 8)],
            "diagnostic": None,
        }
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        validator.check_schema(schema)
        validator.validate(document)
        forged = copy.deepcopy(document)
        forged["actual_all_history_cumulative"] = 39
        self.assertTrue(list(validator.iter_errors(forged)))

    def test_python_contract_rejects_reservation_or_actual_accounting_drift(self):
        spec = curry.OPTION_VERIFICATION_SCOPE
        summary = curry.summarize_curry_validation(
            "c" * 64, [_stage(stage) for stage in range(1, 8)], _stats(7), spec=spec,
        )
        for key, value in (
            ("reservation_id", "0" * 64),
            ("reservation_policy_id", "invented-policy"),
            ("planning_total", 39),
            ("certified_consumed_including_new", 32),
            ("old_confirmation_actual_consumed", 0),
        ):
            forged = copy.deepcopy(summary)
            forged[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                curry.validate_curry_report(forged, spec=spec)

    def test_verify_only_dispatch_precedes_preparation_window_and_live_asset_scan(self):
        spec = curry.OPTION_VERIFICATION_SCOPE
        test_root = REPO / "target" / "curry-option-verification-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        repo = test_root / uuid.uuid4().hex
        repo.mkdir()
        (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
        root = repo / spec.output_root
        output = root / "research"
        output.mkdir(parents=True)
        manifest_raw = b'{"stage1_request_sha256":"' + b"a" * 64 + b'"}'
        (output / "manifest.json").write_bytes(manifest_raw)
        prepared = {
            "prepared": True,
            "execution_ready": True,
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "stage1_request_sha256": "a" * 64,
        }
        (output / "prepared.json").write_text(json.dumps(prepared), encoding="utf-8")
        args = argparse.Namespace(
            baseline_dir=repo / spec.baseline_root,
            preparation=repo / curry.PREPARATION_PATH,
            cases=repo / curry.FROZEN_CASES_PATH,
            core_source=repo / "data/tmp/ocgcore-source/operations.cpp",
            runner=root / "native-artifacts/curry-option-verification.exe",
            worker=root / "native-artifacts/ygo-engine-worker.exe",
            build_record=root / "build-record.json",
            identity=root / "identity.json",
            window_start=root / "window-start.json",
            output=output,
            prepare_only=False,
            verify_only=True,
        )
        with (
            patch.object(curry, "_verify_option_verification_baseline", return_value=({}, {})),
            patch.object(curry, "validate_curry_report", return_value=True),
            patch.object(curry, "_verify_saved_confirmation_build_and_archive", return_value={}),
            patch.object(curry, "_verify_saved_option_verification_inputs", return_value={}) as frozen_gate,
            patch.object(curry, "verify_curry_only", return_value={"valid": False, "native_calls": 0}) as verify,
            patch("ygo_eval.native_tenki_placement._capture_identity", side_effect=AssertionError),
            patch("ygo_eval.native_tenki_placement._candidate_configs", side_effect=AssertionError),
            patch.object(curry, "_assert_option_verification_protected"),
            patch.object(curry, "_snapshot_curry_evidence", return_value={}),
        ):
            result = curry.native_curry_option_validation(args, repo, spec=spec)
        self.assertEqual(result, {"valid": False, "native_calls": 0})
        verify.assert_called_once()
        frozen_gate.assert_called_once()
        self.assertTrue(verify.call_args.kwargs["verification_output"].is_dir())

    def test_verification_manifest_generator_binds_reservation_at_top_level(self):
        fields = curry._verification_manifest_fields(curry.OPTION_VERIFICATION_SCOPE)
        self.assertEqual(fields["consumption_reservation_sha256"], RESERVATION_SHA256)
        self.assertEqual(fields["reservation_id"], RESERVATION_ID)
        self.assertEqual(fields["reservation_policy_id"], POLICY_ID)

    def test_saved_verification_input_gate_rechecks_every_role_and_raw_file(self):
        spec = curry.OPTION_VERIFICATION_SCOPE
        test_root = REPO / "target" / "curry-option-verification-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        repo = test_root / uuid.uuid4().hex
        repo.mkdir()
        (repo / "banlist.conf").write_bytes(b"banlist")
        root = repo / spec.output_root
        root.mkdir(parents=True)
        roles = curry._manifest_roles(spec)
        preparation = {
            "base_request": {"request": "base"},
            "candidate_case": {"case": "candidate"},
            "base_request_entry": {"banlist_path": "banlist.conf"},
        }
        role_files = {}
        expected = {}
        for index, role in enumerate(roles):
            path = repo / "frozen" / f"{role}.bin"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(f"raw-{role}".encode())
            role_files[role] = path
            expected[role] = curry._sha(curry._case_encode(preparation[role])) if role in (
                "base_request", "candidate_case"
            ) else curry._sha(path.read_bytes())
        manifest = {"input_sha256": expected}
        baseline = repo / spec.baseline_root
        baseline.mkdir(parents=True)
        baseline_protected = {baseline: "baseline-tree-hash"}
        args = argparse.Namespace(
            preparation=repo / curry.PREPARATION_PATH,
            cases=repo / curry.FROZEN_CASES_PATH,
            core_source=repo / "data/tmp/ocgcore-source/operations.cpp",
        )
        with (
            patch.object(curry, "verify_curry_preparation", return_value=preparation),
            patch.object(curry, "_curry_manifest_files", return_value=role_files),
        ):
            protected = curry._verify_saved_option_verification_inputs(
                args, repo, root, {}, manifest, baseline_protected, spec,
            )
            self.assertEqual(set(protected), set(baseline_protected) | set(role_files.values()))
            role_files["worker"].write_bytes(b"changed-worker")
            with self.assertRaisesRegex(curry.CurryFrozenInputMismatch, "worker"):
                curry._verify_saved_option_verification_inputs(
                    args, repo, root, {}, manifest, baseline_protected, spec,
                )

    def test_v3_reservation_directory_pin_and_absent_confirmation_ledger_are_protected(self):
        from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE

        test_root = REPO / "target" / "curry-option-verification-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        repo = test_root / uuid.uuid4().hex
        repo.mkdir()
        evidence = repo / V3_TENKI_EVIDENCE_RELATIVE
        (evidence / "research").mkdir(parents=True)
        (evidence / "process-diagnostics").mkdir()
        (evidence / "research" / "calls.jsonl").write_bytes(b"frozen-ledger")
        evidence_pin = curry._curry_evidence_hash(curry._snapshot_curry_evidence(evidence))
        file_path = repo / "frozen.bin"
        file_path.write_bytes(b"frozen-file")
        rows = [
            {"path": V3_TENKI_EVIDENCE_RELATIVE.as_posix(), "role": "directory",
             "sha256": evidence_pin, "bytes": 0},
            {"path": "frozen.bin", "role": "file", "sha256": curry._sha(b"frozen-file"),
             "bytes": len(b"frozen-file")},
        ]
        protected = {}
        curry._add_v3_reservation_input_protections(
            protected, repo, {"inputs": rows},
        )
        self.assertEqual(protected[Path(str(evidence.resolve()))], evidence_pin)
        self.assertEqual(protected[Path(str(file_path.resolve()))], curry._sha(b"frozen-file"))
        self.assertEqual(curry._option_verification_protected_hash(
            evidence, repo,
        ), evidence_pin)
        (evidence / "research" / "calls.jsonl").write_bytes(b"changed")
        self.assertNotEqual(curry._option_verification_protected_hash(
            evidence, repo,
        ), evidence_pin)

        confirmation_ledger = (
            repo / curry.CONFIRMATION_SCOPE.output_root / "research" / "calls.jsonl"
        )
        confirmation_ledger.parent.mkdir(parents=True)
        self.assertEqual(curry._option_verification_protected_hash(
            confirmation_ledger, repo,
        ), curry.ABSENT_PROTECTION_SENTINEL)
        confirmation_ledger.write_bytes(b"unexpected-charge")
        with self.assertRaisesRegex(ValueError, "charge_ledger_unexpected"):
            curry._option_verification_protected_hash(confirmation_ledger, repo)

    def test_stage_report_cannot_disagree_with_its_receipt(self):
        receipt = {
            "successful": True,
            "ledger": _stats(5),
            "independent_replay_matches": True,
            "diagnostic": None,
        }
        report = {
            "stage": 5,
            "successful": True,
            "ledger": _stats(5),
            "independent_replay_matches": True,
            "native_calls": 1,
            "diagnostic": None,
        }
        process_record = {"status": "completed", "return_code": 0, "error_code": None}
        self.assertTrue(curry._stage_report_matches_receipt(
            report, receipt, stage=5, previous_consumed=4,
            process_record=process_record, orchestration_diagnostic=None,
            runner_output_matches_receipt=True,
        ))
        malformed_output_report = copy.deepcopy(report)
        malformed_output_report["successful"] = False
        malformed_output_report["diagnostic"] = "runner_output_invalid_or_nonzero"
        self.assertTrue(curry._stage_report_matches_receipt(
            malformed_output_report, receipt, stage=5, previous_consumed=4,
            process_record=process_record, orchestration_diagnostic=None,
            runner_output_matches_receipt=False,
        ))
        for invalid_process in (
            {"status": "started", "return_code": 0, "error_code": None},
            {"status": "completed", "return_code": None, "error_code": None},
            {"status": "completed", "return_code": 0, "error_code": "unexpected"},
        ):
            with self.subTest(process=invalid_process):
                self.assertFalse(curry._stage_report_matches_receipt(
                    malformed_output_report, receipt, stage=5, previous_consumed=4,
                    process_record=invalid_process, orchestration_diagnostic=None,
                    runner_output_matches_receipt=None,
                ))
        failed_receipt = {**receipt, "successful": False, "diagnostic": "engine_error"}
        self.assertFalse(curry._stage_report_matches_receipt(
            malformed_output_report, failed_receipt, stage=5, previous_consumed=4,
            process_record=process_record, orchestration_diagnostic=None,
            runner_output_matches_receipt=False,
        ))
        variants = []
        changed = copy.deepcopy(report)
        changed["successful"] = False
        changed["diagnostic"] = "forged_failure"
        variants.append(("success", changed, receipt))
        changed = copy.deepcopy(report)
        changed["ledger"] = _stats(4)
        variants.append(("ledger", changed, receipt))
        changed = copy.deepcopy(report)
        changed["independent_replay_matches"] = False
        variants.append(("replay", changed, receipt))
        changed = copy.deepcopy(report)
        changed["native_calls"] = 0
        variants.append(("native_calls", changed, receipt))
        changed = copy.deepcopy(report)
        changed["successful"] = False
        changed["diagnostic"] = "forged_failure"
        variants.append(("diagnostic", changed, receipt))
        failed_receipt = {**receipt, "successful": False, "diagnostic": "engine_error"}
        changed = copy.deepcopy(report)
        variants.append(("forged_success", changed, failed_receipt))
        for name, forged_report, bound_receipt in variants:
            with self.subTest(field=name):
                self.assertFalse(curry._stage_report_matches_receipt(
                    forged_report, bound_receipt, stage=5, previous_consumed=4,
                    process_record=process_record,
                    orchestration_diagnostic=None,
                    runner_output_matches_receipt=True,
                ))

    def test_verify_only_does_not_upgrade_malformed_saved_stdout_to_success(self):
        from ygo_eval.native_tenki_placement_validation import _diagnostic_hash
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        spec = curry.OPTION_VERIFICATION_SCOPE
        test_root = REPO / "target" / "curry-option-verification-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        repo = test_root / uuid.uuid4().hex
        root = repo / spec.output_root
        output = root / "research"
        output.mkdir(parents=True)
        context = HASH_A
        started_at = 1
        request = {"case_id": "synthetic-stage-1", "decisions": []}
        expected_identity = {"worker": HASH_B}
        curry._save_curry_stage_files(
            output, context, 1, request, expected_identity, started_at, spec,
        )
        receipt = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "stage"),
            "scope": spec.scope,
            "context": context,
            "stage": 1,
            "request": request,
            "successful": True,
            "assets_before": expected_identity,
            "assets_after": expected_identity,
            "ledger": _stats(1),
            "diagnostic": None,
            **curry.FLAGS,
        }
        receipt_path = output / "stage-1.json"
        curry.immutable_write(receipt_path, receipt)

        def malformed_stdout_runner(command, cwd=None, **_kwargs):
            return subprocess.CompletedProcess(command, 0, b"{broken", b"")

        process_record, _completed = capture_process_diagnostic(
            ["synthetic-runner"], repo, root,
            mode="normal", timeout=30, runner=malformed_stdout_runner,
            runner_role=spec.runner_role,
        )
        curry.immutable_write(root / "stage-1-process-diagnostic.json", process_record)
        process_sha = _diagnostic_hash(root, process_record, spec)
        failure_report = curry._stage_report(
                context, 1, receipt, receipt_path, process_sha, 1,
                "runner_output_invalid_or_nonzero", _stats(1), spec,
            )
        self.assertTrue(curry._stage_report_matches_receipt(
            failure_report,
            receipt, stage=1, previous_consumed=0,
            process_record=process_record, orchestration_diagnostic=None,
            runner_output_matches_receipt=False,
        ), f"report={failure_report!r}; process={process_record!r}; receipt={receipt!r}")
        report = curry._stage_report(
            context, 1, receipt, receipt_path, process_sha, 1,
            "runner_output_invalid_or_nonzero", _stats(1), spec,
        )
        report_path = output / "stage-1-report.json"
        curry.immutable_write(report_path, report)
        manifest = {
            "scope": spec.scope,
            "context": context,
            "started_at": started_at,
            "request": request,
            "assets": {"ordinary": expected_identity},
        }
        runner_verify = unittest.mock.Mock(return_value={
            "verified_recorded": True,
            "native_calls": 0,
            "diagnostic_sha256": HASH_B,
        })

        with patch.object(curry, "validate_curry_stage_receipt", return_value=[]):
            failure = curry.verify_curry_only(
                root=root, output=output, runner=root / "runner.exe", repo=repo,
                manifest=manifest, prepared_hash=HASH_B,
                verify_recorded=runner_verify, read_stats=lambda _path: None,
                verification_output=root / "checks" / "failure",
                spec=spec,
            )
        self.assertFalse(failure["valid"])
        self.assertEqual(failure["diagnostic"], "runner_output_invalid_or_nonzero")
        runner_verify.assert_called_once()

        forged_success = copy.deepcopy(report)
        forged_success["successful"] = True
        forged_success["diagnostic"] = None
        (output / "stage-1-report.json").write_text(
            json.dumps(forged_success), encoding="utf-8",
        )
        forged_verify = unittest.mock.Mock(return_value={
            "verified_recorded": True,
            "native_calls": 0,
            "diagnostic_sha256": HASH_B,
        })
        with patch.object(curry, "validate_curry_stage_receipt", return_value=[]):
            rejected = curry.verify_curry_only(
                root=root, output=output, runner=root / "runner.exe", repo=repo,
                manifest=manifest, prepared_hash=HASH_B,
                verify_recorded=forged_verify, read_stats=lambda _path: None,
                verification_output=root / "checks" / "forged-success",
                spec=spec,
            )
        self.assertFalse(rejected["valid"])
        self.assertEqual(
            rejected["diagnostic"], "curry_saved_stage_report_receipt_mismatch",
        )
        forged_verify.assert_not_called()

    def test_verify_only_preserves_legitimate_incomplete_runner_timeout_failure(self):
        from ygo_eval.native_tenki_placement_validation import _diagnostic_hash
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        spec = curry.OPTION_VERIFICATION_SCOPE
        test_root = REPO / "target" / "curry-option-verification-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        repo = test_root / uuid.uuid4().hex
        root = repo / spec.output_root
        output = root / "research"
        output.mkdir(parents=True)
        context = HASH_A
        started_at = 1
        request = {"case_id": "synthetic-timeout-stage-1", "decisions": []}
        expected_identity = {"worker": HASH_B}
        curry._save_curry_stage_files(
            output, context, 1, request, expected_identity, started_at, spec,
        )
        receipt = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "stage"),
            "scope": spec.scope,
            "context": context,
            "stage": 1,
            "request": request,
            "successful": False,
            "assets_before": expected_identity,
            "assets_after": None,
            "ledger": _stats(1, unknown=1),
            "diagnostic": "runner_timeout",
            **curry.FLAGS,
        }
        receipt_path = output / "stage-1.json"
        curry.immutable_write(receipt_path, receipt)

        def timeout_runner(command, cwd=None, **_kwargs):
            raise subprocess.TimeoutExpired(
                command, 30, output=b"partial stdout", stderr=b"timed out",
            )

        process_record, completed = capture_process_diagnostic(
            ["synthetic-runner"], repo, root,
            mode="normal", timeout=30, runner=timeout_runner,
            runner_role=spec.runner_role,
        )
        self.assertIsNone(completed)
        self.assertEqual(process_record["status"], "timeout")
        curry.immutable_write(
            root / "stage-1-process-diagnostic.json", process_record,
        )
        process_sha = _diagnostic_hash(root, process_record, spec)
        report = curry._stage_report(
            context, 1, receipt, receipt_path, process_sha, 1,
            "runner_timeout", _stats(1, unknown=1), spec,
        )
        curry.immutable_write(output / "stage-1-report.json", report)
        manifest = {
            "scope": spec.scope,
            "context": context,
            "started_at": started_at,
            "request": request,
            "assets": {"ordinary": expected_identity},
        }
        runner_verify = unittest.mock.Mock(return_value={
            "verified_recorded": True,
            "native_calls": 0,
            "diagnostic_sha256": HASH_B,
        })

        with patch.object(curry, "validate_curry_stage_receipt", return_value=[]):
            verified = curry.verify_curry_only(
                root=root, output=output, runner=root / "runner.exe", repo=repo,
                manifest=manifest, prepared_hash=HASH_B,
                verify_recorded=runner_verify, read_stats=lambda _path: None,
                verification_output=root / "checks" / "timeout",
                spec=spec,
            )

        self.assertFalse(verified["valid"])
        self.assertEqual(verified["diagnostic"], "runner_timeout")
        self.assertEqual(len(verified["stages"]), 1)
        self.assertEqual(verified["stages"][0]["diagnostic"], "runner_timeout")
        runner_verify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
