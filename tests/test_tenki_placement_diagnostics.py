import hashlib
import json
import re
import subprocess
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
import uuid


def workspace_temporary_directory():
    """Keep test scratch inside the writable, ignored repository runtime root."""
    repo = Path(__file__).resolve().parents[1]
    root = repo / "data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22"
    path = root / ("test-scratch-" + uuid.uuid4().hex)
    path.mkdir(parents=True, exist_ok=False)
    return path


class TenkiPlacementAnchorRegressionTests(unittest.TestCase):
    def test_input_record_merge_deduplicates_identical_evidence_and_rejects_conflicts(self):
        from ygo_eval.tenki_placement_diagnostics import _deduplicate_input_records

        item = {"role": "delivery", "path": "data/runtime/delivery.json", "sha256": "a" * 64, "bytes": 17}
        self.assertEqual(_deduplicate_input_records([item, dict(item)]), [item])

        conflicting = dict(item, sha256="b" * 64)
        with self.assertRaisesRegex(ValueError, "diagnostic_input_record_conflict"):
            _deduplicate_input_records([item, conflicting])

        for first, second in ((1, True), (1, 1.0)):
            typed_first = dict(item, bytes=first)
            typed_second = dict(item, bytes=second)
            with self.subTest(first_type=type(first).__name__, second_type=type(second).__name__):
                with self.assertRaisesRegex(ValueError, "diagnostic_input_record_conflict"):
                    _deduplicate_input_records([typed_first, typed_second])

    def test_rust_and_python_stage1_anchor_are_the_same_sha256(self):
        from ygo_eval.native_tenki_placement import OLD_STAGE1_SHA256

        source = Path(__file__).resolve().parents[1] / "crates/ygo-engine-adapter/src/tenki_placement_probe.rs"
        rust = source.read_text(encoding="utf-8")
        match = re.search(r'const OLD_STAGE1_SHA256: &str\s*=\s*"([^"]+)";', rust)
        self.assertIsNotNone(match)
        self.assertEqual(OLD_STAGE1_SHA256, "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76")
        self.assertEqual(match.group(1), OLD_STAGE1_SHA256)
        self.assertRegex(OLD_STAGE1_SHA256, r"^[a-f0-9]{64}$")
        historical = Path(__file__).resolve().parents[1] / "data/runtime/p1-tenki-probe-native-2026-10-21/research/stage-1.json"
        if historical.is_file():
            self.assertEqual(hashlib.sha256(historical.read_bytes()).hexdigest(), OLD_STAGE1_SHA256)

    def test_placement_document_parser_treats_ledger_as_pinned_jsonl_bytes(self):
        from ygo_eval.tenki_placement_diagnostics import _parse_placement_documents

        parsed = _parse_placement_documents({
            "manifest": b'{"kind":"manifest"}',
            "ledger": b'{"kind":"header"}\n{"kind":"checkpoint"}\n',
            "native_source_archive": b'\x00\xffnot-json',
            "final_source_archive": b'PK\x03\x04archive-bytes',
        })
        self.assertEqual(parsed["manifest"], {"kind": "manifest"})
        self.assertNotIn("ledger", parsed)
        self.assertNotIn("native_source_archive", parsed)
        self.assertNotIn("final_source_archive", parsed)

    def test_stage_expected_identity_is_the_ordinary_runtime_identity(self):
        from ygo_eval.tenki_placement_diagnostics import _ordinary_runtime_identity

        ordinary = {"consistent": True, "roles": {"worker": {"sha256": "a" * 64}}}
        workspace = {"kind": "workspace_identity", "runtimes": {"ordinary": ordinary, "tournament": {"consistent": True}}}
        self.assertEqual(_ordinary_runtime_identity(workspace), ordinary)
        with self.assertRaisesRegex(ValueError, "placement_ordinary_identity_missing"):
            _ordinary_runtime_identity({"runtimes": {"ordinary": None}})

    def test_historical_placement_build_binds_its_own_runner_not_the_baseline_runner(self):
        from ygo_eval.tenki_placement_diagnostics import (
            HISTORICAL_NATIVE_BUILD,
            HISTORICAL_NATIVE_RUNNER_SHA256,
            HISTORICAL_NATIVE_SOURCE,
            _validate_historical_native_build,
        )
        from ygo_eval.native_tenki_placement import OLD_RUNNER_SHA256

        self.assertNotEqual(HISTORICAL_NATIVE_RUNNER_SHA256, OLD_RUNNER_SHA256)
        worker = "9" * 64
        source = {"identity": HISTORICAL_NATIVE_SOURCE}
        build = {
            "identity": HISTORICAL_NATIVE_BUILD,
            "source_before": source,
            "source_after": dict(source),
            "artifacts": {"runner": HISTORICAL_NATIVE_RUNNER_SHA256, "worker": worker},
        }
        manifest = {
            "build_identity": HISTORICAL_NATIVE_BUILD,
            "runner_sha256": HISTORICAL_NATIVE_RUNNER_SHA256,
            "worker_sha256": worker,
        }
        self.assertTrue(_validate_historical_native_build(manifest, build))
        wrong_runner = dict(build, artifacts={**build["artifacts"], "runner": OLD_RUNNER_SHA256})
        with self.assertRaisesRegex(ValueError, "historical_native_build_binding_mismatch"):
            _validate_historical_native_build(manifest, wrong_runner)

    def test_archive_file_count_accepts_pinned_native_and_final_list_contracts(self):
        from ygo_eval.tenki_placement_diagnostics import _archive_file_count

        files = {"src.py": "a" * 64}
        self.assertEqual(_archive_file_count({"files": files, "file_count": 1}), 1)
        self.assertEqual(_archive_file_count({"files": files, "archived_files": 1}), 1)
        with self.assertRaisesRegex(ValueError, "source_archive_file_list_mismatch"):
            _archive_file_count({"files": files, "file_count": 1, "archived_files": 2})


class ProcessDiagnosticCaptureTests(unittest.TestCase):
    def test_saved_input_audit_mode_is_an_explicit_supported_diagnostic_mode(self):
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        completed = subprocess.CompletedProcess(["runner"], 0, b"{}", b"")
        root = workspace_temporary_directory()
        try:
            record, _ = capture_process_diagnostic(
                ["runner"], root, root / "saved-input", mode="audit_saved_input_only",
                timeout=900, runner_role="curry_ledger_handoff_audit_runner",
                runner=lambda *args, **kwargs: completed,
            )
            self.assertEqual(record["mode"], "audit_saved_input_only")
            self.assertEqual(record["runner_role"], "curry_ledger_handoff_audit_runner")
            with self.assertRaisesRegex(ValueError, "process_diagnostic_mode_invalid"):
                capture_process_diagnostic(
                    ["runner"], root, root / "unknown", mode="audit_anything",
                    timeout=900, runner=lambda *args, **kwargs: completed,
                )
        finally:
            shutil.rmtree(root)

    def test_nonzero_process_preserves_raw_non_utf8_streams_before_returning(self):
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        stdout = b"bad json \xff D:\\private\\source"
        stderr = b"runner rejected input \xfe"
        completed = subprocess.CompletedProcess(["runner"], 2, stdout, stderr)
        root = workspace_temporary_directory()
        try:
            record, result = capture_process_diagnostic(
                ["runner"], root, root / "evidence", mode="preflight_only", timeout=30,
                runner=lambda *args, **kwargs: completed,
            )
            self.assertIs(result, completed)
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["return_code"], 2)
            self.assertEqual((root / "evidence" / record["stdout"]["path"]).read_bytes(), stdout)
            self.assertEqual((root / "evidence" / record["stderr"]["path"]).read_bytes(), stderr)
            self.assertEqual(record["stdout"]["sha256"], hashlib.sha256(stdout).hexdigest())
            metadata = root / "evidence" / record["metadata_path"]
            self.assertTrue(metadata.is_file())
            self.assertNotIn(str(root), metadata.read_text(encoding="utf-8"))
            self.assertNotIn(str(root), json.dumps(record))
        finally:
            shutil.rmtree(root)

    def test_confirmation_runner_role_is_explicit_without_changing_legacy_default(self):
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        completed = subprocess.CompletedProcess(["runner"], 0, b"{}", b"")
        root = workspace_temporary_directory()
        try:
            legacy, _ = capture_process_diagnostic(
                ["runner"], root, root / "legacy", mode="stats", timeout=30,
                runner=lambda *args, **kwargs: completed,
            )
            confirmation, _ = capture_process_diagnostic(
                ["runner"], root, root / "confirmation", mode="stats", timeout=30,
                runner=lambda *args, **kwargs: completed,
                runner_role="tenki_placement_confirmation_runner",
            )
            self.assertEqual(legacy["runner_role"], "tenki_placement_audit_runner")
            self.assertEqual(confirmation["runner_role"], "tenki_placement_confirmation_runner")
        finally:
            shutil.rmtree(root)

    def test_timeout_partial_bytes_and_launch_failure_are_recorded(self):
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        root = workspace_temporary_directory()
        try:
            timed_out = subprocess.TimeoutExpired(["runner"], 30, output=b"partial\xff", stderr=b"partial err")
            record, result = capture_process_diagnostic(
                ["runner"], root, root / "timeout", mode="normal", timeout=30,
                runner=lambda *args, **kwargs: (_ for _ in ()).throw(timed_out),
            )
            self.assertIsNone(result)
            self.assertEqual(record["status"], "timeout")
            self.assertEqual(record["error_code"], "runner_timeout")
            self.assertEqual((root / "timeout" / record["stdout"]["path"]).read_bytes(), b"partial\xff")

            record, result = capture_process_diagnostic(
                ["runner"], root, root / "launch", mode="stats", timeout=30,
                runner=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("D:\\private\\runner missing")),
            )
            self.assertIsNone(result)
            self.assertEqual(record["status"], "launch_failed")
            self.assertEqual(record["error_code"], "runner_start_failed")
            self.assertNotIn(str(root), json.dumps(record))
            record, result = capture_process_diagnostic(
                ["runner"], root, root / "exception", mode="verify_recorded", timeout=30,
                runner=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private path D:\\private\\runner")),
            )
            self.assertIsNone(result)
            self.assertEqual(record["status"], "launch_failed")
            self.assertEqual(record["error_code"], "runner_launch_exception")
            self.assertNotIn("private", json.dumps(record))
        finally:
            shutil.rmtree(root)

    def test_diagnostic_persistence_failure_is_fatal(self):
        from ygo_eval import tenki_placement_diagnostics as diagnostics

        completed = subprocess.CompletedProcess(["runner"], 0, b"{}", b"")
        root = workspace_temporary_directory()
        try:
            with patch.object(diagnostics, "_write_exclusive", side_effect=OSError("disk full")):
                with self.assertRaises(diagnostics.DiagnosticPersistenceError):
                    diagnostics.capture_process_diagnostic(
                        ["runner"], root, root / "evidence",
                        mode="verify_recorded", timeout=30,
                        runner=lambda *args, **kwargs: completed,
                    )
        finally:
            shutil.rmtree(root)


class DiagnosticsSchemaTests(unittest.TestCase):
    def test_preflight_result_rejects_boolean_numbers(self):
        from ygo_eval.tenki_placement_diagnostics import _preflight_output_matches

        valid = {
            "preflight_passed": True,
            "native_calls": 0,
            "stage": 1,
            "context": "c" * 64,
            "identity_sha256": "d" * 64,
        }
        self.assertTrue(_preflight_output_matches(valid, "c" * 64, "d" * 64))
        self.assertFalse(_preflight_output_matches(dict(valid, native_calls=False), "c" * 64, "d" * 64))
        self.assertFalse(_preflight_output_matches(dict(valid, stage=True), "c" * 64, "d" * 64))

    def test_contract_allows_failed_zero_call_audit_and_rejects_qualification(self):
        import jsonschema

        schema_path = Path(__file__).resolve().parents[1] / "schemas/tenki-placement-diagnostics-v1.schema.json"
        schema = json.loads(schema_path.read_bytes())
        report = {
            "schema_version": 1,
            "kind": "tenki_placement_diagnostics",
            "operation": "stage1_preflight_audit",
            "status": "failed",
            "native_calls": 0,
            "execution_ready": False,
            "source_identity": {
                "historical_native": "a" * 64,
                "native_build": "b" * 64,
                "historical_runner_sha256": "f" * 64,
                "audit_source": "c" * 64,
                "audit_build": "d" * 64,
                "audit_runner_sha256": "e" * 64,
            },
            "historical_anchor": {
                "archived_rust_literal": "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7601bbedce5ceaf76",
                "actual_stage1_sha256": "f" * 64,
                "python_anchor_sha256": "f" * 64,
                "repaired_rust_anchor_sha256": "f" * 64,
                "historical_stderr": "not_saved",
            },
            "historical_claims": {
                "old_binary_provenance_verified": False,
                "historical_reexecution_verified": False,
                "historical_stderr_recovered": False,
            },
            "inputs": [{"role": "frozen_input", "path": "data/runtime/evidence.json", "sha256": "0" * 64, "bytes": 1}],
            "asset_scan": {"time_utc": None, "expected_identity_sha256": "0" * 64, "identity_match": None},
            "input_drift": {
                "workspace_source_unchanged": None,
                "baseline_tree_unchanged": None,
                "experiment_tree_unchanged": None,
                "protected_inputs_unchanged": None,
            },
            "checks": {key: "passed" for key in (
                "baseline_acceptance", "historical_archive", "manifest", "request", "input", "seal", "ledger", "identity", "preflight_process"
            )},
            "process_diagnostic": None,
            "diagnostic": "runner_nonzero_exit",
            "input_snapshot_sha256": "0" * 64,
            "input_count": 1,
            "evidence_bytes": 0,
            "elapsed_seconds": 0,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        report["checks"]["preflight_process"] = "not_run"
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(report)
        changed = dict(report, execution_ready=True)
        self.assertTrue(list(validator.iter_errors(changed)))

        passed = dict(report)
        passed.update(status="passed", diagnostic=None)
        passed["checks"] = dict(report["checks"], preflight_process="passed")
        passed["asset_scan"] = dict(report["asset_scan"], identity_match=True)
        passed["process_diagnostic"] = {
            "mode": "preflight_only",
            "runner_role": "tenki_placement_audit_runner",
            "status": "completed",
            "return_code": 0,
            "error_code": None,
            "stdout": {"path": "process-diagnostics/run.stdout.bin", "sha256": "1" * 64, "bytes": 0},
            "stderr": {"path": "process-diagnostics/run.stderr.bin", "sha256": "2" * 64, "bytes": 0},
            "metadata_path": "process-diagnostics/run.json",
            "metadata_bytes": 0,
        }
        validator.validate(passed)

        contradictory = dict(passed)
        contradictory["asset_scan"] = dict(passed["asset_scan"], identity_match=False)
        self.assertTrue(list(validator.iter_errors(contradictory)))
        contradictory = dict(passed, diagnostic="runner_failed")
        self.assertTrue(list(validator.iter_errors(contradictory)))
        contradictory = dict(
            report,
            diagnostic=None,
            checks={key: "passed" for key in report["checks"]},
        )
        self.assertTrue(list(validator.iter_errors(contradictory)))
        bad_role = dict(report)
        bad_role["inputs"] = [dict(report["inputs"][0], role="D:\\private\\evidence")]
        self.assertTrue(list(validator.iter_errors(bad_role)))

    def test_runtime_report_validator_recomputes_input_hash_and_rejects_bool_as_integer(self):
        from ygo_data.identity import canonical, digest
        from ygo_eval import tenki_placement_diagnostics as diagnostics

        root = Path(__file__).resolve().parents[1]
        report = {
            "schema_version": 1,
            "kind": "tenki_placement_diagnostics",
            "operation": "stage1_preflight_audit",
            "status": "failed",
            "native_calls": 0,
            "execution_ready": False,
            "source_identity": {
                "historical_native": "a" * 64,
                "native_build": "b" * 64,
                "historical_runner_sha256": "c" * 64,
                "audit_source": "d" * 64,
                "audit_build": "e" * 64,
                "audit_runner_sha256": "f" * 64,
            },
            "historical_anchor": {
                "archived_rust_literal": diagnostics.WRONG_ARCHIVED_STAGE1_LITERAL,
                "actual_stage1_sha256": diagnostics.CORRECT_STAGE1_LITERAL,
                "python_anchor_sha256": diagnostics.OLD_STAGE1_SHA256,
                "repaired_rust_anchor_sha256": diagnostics.CORRECT_STAGE1_LITERAL,
                "historical_stderr": "not_saved",
            },
            "historical_claims": {
                "old_binary_provenance_verified": False,
                "historical_reexecution_verified": False,
                "historical_stderr_recovered": False,
            },
            "inputs": [{"role": "fixture", "path": "tests/fixtures/frozen.json", "sha256": "1" * 64, "bytes": 12}],
            "asset_scan": {"time_utc": None, "expected_identity_sha256": "2" * 64, "identity_match": None},
            "input_drift": {
                "workspace_source_unchanged": None,
                "baseline_tree_unchanged": None,
                "experiment_tree_unchanged": None,
                "protected_inputs_unchanged": None,
            },
            "checks": {key: "not_run" for key in (
                "baseline_acceptance", "historical_archive", "manifest", "request", "input", "seal", "ledger", "identity", "preflight_process"
            )},
            "process_diagnostic": None,
            "diagnostic": "offline_preflight_failed",
            "input_snapshot_sha256": digest(canonical([{"path": "tests/fixtures/frozen.json", "sha256": "1" * 64}])),
            "input_count": 1,
            "evidence_bytes": 12,
            "elapsed_seconds": 0.0,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        diagnostics._validate_report(report, root)

        wrong_digest = dict(report, input_snapshot_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "diagnostic_report_hash_invalid"):
            diagnostics._validate_report(wrong_digest, root)

        bool_count = dict(report, input_count=True)
        with self.assertRaisesRegex(ValueError, "diagnostic_report_input_count_invalid"):
            diagnostics._validate_report(bool_count, root)

        integer_boolean = dict(report)
        integer_boolean["asset_scan"] = dict(report["asset_scan"], identity_match=1)
        with self.assertRaisesRegex(ValueError, "diagnostic_report_asset_scan_invalid"):
            diagnostics._validate_report(integer_boolean, root)

        private_field = dict(report, local_path="D:\\private\\evidence")
        with self.assertRaisesRegex(ValueError, "diagnostic_report_fields_invalid"):
            diagnostics._validate_report(private_field, root)

        private_role = dict(report)
        private_role["inputs"] = [dict(report["inputs"][0], role="D:\\private\\evidence")]
        with self.assertRaisesRegex(ValueError, "diagnostic_report_input_entry_invalid"):
            diagnostics._validate_report(private_role, root)

        path_diagnostic = dict(report, diagnostic="D:\\private\\failure")
        with self.assertRaisesRegex(ValueError, "diagnostic_report_diagnostic_invalid"):
            diagnostics._validate_report(path_diagnostic, root)


if __name__ == "__main__":
    unittest.main()
