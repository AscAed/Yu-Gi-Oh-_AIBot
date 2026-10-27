"""Synthetic, zero-worker tests for the Curry asset-binding audit."""
from __future__ import annotations

import json
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_data.identity import canonical, digest
from ygo_eval import curry_asset_binding_audit as audit


class CurryAssetBindingAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.scratch_root = (
            cls.repo_root
            / "target/curry-asset-binding-tests"
        )
        cls.scratch_root.mkdir(parents=True, exist_ok=True)
        cls.schema = json.loads(
            (cls.repo_root / "schemas/curry-asset-binding-audit-v1.schema.json").read_bytes()
        )

    def _fixture(self):
        root = self.scratch_root / f"fixture-{uuid.uuid4().hex}"
        root.mkdir()
        (root / "audit/native-artifacts").mkdir(parents=True)
        (root / "baseline/research").mkdir(parents=True)
        schema_dir = root / "schemas"
        schema_dir.mkdir()
        (schema_dir / "curry-asset-binding-audit-v1.schema.json").write_bytes(
            (self.repo_root / "schemas/curry-asset-binding-audit-v1.schema.json").read_bytes()
        )
        input_path = root / "baseline/research/stage-1-input.json"
        expected_identity = {"kind": "engine_identity", "identity": "c" * 64}
        request = {"id": "synthetic"}
        input_raw = canonical({
            "context": "a" * 64,
            "stage": 1,
            "request": request,
            "expected_identity": expected_identity,
        })
        input_path.write_bytes(input_raw)
        source = {"head": "synthetic", "files": {"marker": "1" * 64}}
        source["identity"] = digest(canonical(source))
        runner = root / "audit/native-artifacts/curry-option-validation.exe"
        runner.write_bytes(b"synthetic isolated runner")
        unsigned_build = {
            "schema_version": 1,
            "kind": "build_record",
            "status": "recorded",
            "source_before": source,
            "source_after": source,
            "reproducible_build_proven": False,
            "artifacts": {"runner": digest(runner.read_bytes())},
        }
        build = {**unsigned_build, "identity": digest(canonical(unsigned_build))}
        build_path = root / "audit/build-record.json"
        build_path.write_bytes(canonical(build))
        baseline = {
            "context": "a" * 64,
            "request": request,
            "expected_identity": expected_identity,
            "input_path": input_path,
            "input_sha256": digest(input_raw),
            "input_records": [{
                "role": "stage1_input",
                "path": input_path.relative_to(root).as_posix(),
                "sha256": digest(input_raw),
                "bytes": len(input_raw),
            }],
            "protected": {input_path: digest(input_raw)},
            "source_archives": [
                {"role": "native_time", "sha256": "2" * 64,
                 "file_list_sha256": "3" * 64, "source_identity": "4" * 64,
                 "file_count": 494, "bytes": 100},
                {"role": "final", "sha256": "4" * 64,
                 "file_list_sha256": "5" * 64, "source_identity": "6" * 64,
                 "file_count": 495, "bytes": 101},
            ],
            "historical": {
                "consumed": 32, "unknown": 0, "ledger_count": 9,
                "verified_without_writable_journal": True, "input_set_sha256": "9" * 64,
            },
            "old_scope": {
                "scope": "curry-option-validation-v1", "prepared": False,
                "ledger_exists": False, "consumed": None, "unknown": None,
                "stored_summary_diagnostic": "curry_preflight_output_mismatch",
                "observed_process_diagnostic": "curry_asset_identity_mismatch",
            },
            "static_root_cause": {
                "historical_source_path": "crates/ygo-engine-adapter/examples/curry-option-validation.rs",
                "historical_comparison_role": "worker",
                "engine_version_role": "dll",
                "repair_target_role": "dll",
                "root_cause": "engine_sha256_was_compared_to_worker_sha256",
                "repair": "compare_engine_sha256_to_dll_and_bind_manifest_worker",
                "historical_source_sha256": "6" * 64,
                "current_source_sha256": "7" * 64,
                "historical_scan_identity_persisted": False,
            },
            "protected_summary": {"file_count": 1, "tree_sha256": "8" * 64},
        }
        return root, baseline, runner, build_path, source

    @staticmethod
    def _trace_bytes():
        rows = []
        for phase in ("input_validation", "shared_preflight"):
            rows.append({"phase": phase, "event": "start"})
            rows.append({"phase": phase, "event": "end", "elapsed_ns": 61_000_000_000})
        return b"\n".join(json.dumps(row, separators=(",", ":")).encode() for row in rows)

    def _run(self, fixture, process_runner):
        root, baseline, runner, build_path, _source = fixture
        output_root = root / "audit"
        output_path = output_root / "audit-report.json"
        source = {"head": "synthetic", "files": {"marker": "1" * 64}}
        source["identity"] = digest(canonical(source))
        with patch.object(audit, "stable_source", return_value=source):
            report = audit._run_audit(
                repo=root,
                baseline_dir=root / "baseline",
                runner=runner,
                build_record=build_path,
                output_root=output_root,
                output_path=output_path,
                process_runner=process_runner,
                baseline_verifier=lambda _repo, _path: baseline,
            )
        self.assertEqual(json.loads(output_path.read_bytes()), report)
        return report, output_root

    def test_preflight_only_saves_raw_output_before_parsing_and_never_charges(self):
        fixture = self._fixture()
        observed = {}

        def runner(command, *, cwd, capture_output, timeout, check):
            observed.update(command=command, cwd=cwd, capture_output=capture_output,
                            timeout=timeout, check=check)
            result = {
                "preflight_passed": True,
                "native_calls": 0,
                "stage": 1,
                "context": "a" * 64,
                "identity_sha256": "c" * 64,
            }
            return subprocess.CompletedProcess(
                command, 0, json.dumps(result).encode(), self._trace_bytes()
            )

        report, output_root = self._run(fixture, runner)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["native_calls"], 0)
        self.assertFalse(report["execution_ready"])
        self.assertEqual(report["original_native_diagnostic"], "curry_asset_identity_mismatch")
        self.assertEqual(report["old_scope"]["stored_summary_diagnostic"], "curry_preflight_output_mismatch")
        self.assertEqual(report["source"]["runner_role"], audit.RUNNER_ROLE)
        self.assertEqual(observed["timeout"], 900)
        self.assertEqual(observed["command"][-2:], ["--preflight-only", "--trace-stderr"])
        self.assertNotIn("--stats", observed["command"])
        self.assertNotIn("--verify-recorded", observed["command"])
        process = report["process"]
        self.assertEqual((output_root / process["stdout"]["path"]).read_bytes(),
                         json.dumps({
                             "preflight_passed": True, "native_calls": 0, "stage": 1,
                             "context": "a" * 64, "identity_sha256": "c" * 64,
                         }).encode())
        self.assertEqual((output_root / process["stderr"]["path"]).read_bytes(), self._trace_bytes())
        Draft202012Validator(self.schema).validate(report)
        self.assertTrue(audit.validate_report(report, repo=fixture[0], artifact_root=output_root))
        self.assertFalse((fixture[0] / "baseline/research/calls.jsonl").exists())

    def test_historical_audit_hash_uses_the_actual_three_level_return_shape(self):
        fixture = self._fixture()
        nested_hash = "a" * 64
        confirmation_audit = {
            "historical_ledgers": 7,
            "current_ledger": {"consumed": 0, "unknown": 0},
            "historical_audit_sha256": nested_hash,
        }
        validation_audit = {
            "delivery": {"historical_consumed": 26, "historical_unknown": 0},
            "prior": confirmation_audit,
        }
        curry_audit = {
            "prior": validation_audit,
            "delivery": {"ledger": {"stats": {"consumed": 6, "unknown": 0}}},
        }
        with patch(
            "ygo_eval.native_curry_option_validation._verify_curry_baseline",
            return_value=(curry_audit, {fixture[0] / "protected.bin": "b" * 64}),
        ):
            summary, protected = audit._verify_historical_chain(fixture[0])
        self.assertEqual(summary["input_set_sha256"], nested_hash)
        self.assertEqual(summary["ledger_count"], 9)
        self.assertIn(fixture[0] / "protected.bin", protected)

    def test_nonzero_process_is_saved_and_does_not_become_a_preflight_pass(self):
        fixture = self._fixture()

        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 2, b"", b"fixed error")

        report, output_root = self._run(fixture, runner)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["native_calls"], 0)
        self.assertFalse(report["execution_ready"])
        self.assertEqual(report["process"]["return_code"], 2)
        self.assertEqual(report["checks"]["read_only_preflight"], "failed")
        self.assertEqual((output_root / report["process"]["stderr"]["path"]).read_bytes(), b"fixed error")
        Draft202012Validator(self.schema).validate(report)

    def test_timeout_and_launch_failure_mark_preflight_failed(self):
        for failure, expected_status in (
            (subprocess.TimeoutExpired(["synthetic-runner"], 900, output=b"partial", stderr=b"trace"), "timeout"),
            (OSError("synthetic launch failure"), "launch_failed"),
        ):
            with self.subTest(status=expected_status):
                fixture = self._fixture()

                def runner(command, **kwargs):
                    raise failure

                report, _output_root = self._run(fixture, runner)
                self.assertEqual(report["process"]["status"], expected_status)
                self.assertEqual(report["checks"]["read_only_preflight"], "failed")
                self.assertEqual(report["status"], "failed")
                Draft202012Validator(self.schema).validate(report)

    def test_report_cannot_grant_qualification_or_change_the_anchor_set(self):
        fixture = self._fixture()
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, b"not-json", self._trace_bytes())
        report, _ = self._run(fixture, runner)
        forged = dict(report)
        forged["proof_ready"] = True
        with self.assertRaises(ValueError):
            audit.validate_report(forged)
        valid_anchors = dict(audit.HASH_ANCHORS)
        self.assertTrue(audit.validate_anchor_hashes(valid_anchors))
        valid_anchors["manifest"] = "0" * 64
        with self.assertRaises(ValueError):
            audit.validate_anchor_hashes(valid_anchors)

    def test_invalid_or_multiple_stdout_documents_are_preserved_before_rejection(self):
        for stdout in (b"\xffnot-utf8", b"{}\n{}\n"):
            with self.subTest(stdout=stdout):
                fixture = self._fixture()

                def runner(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, stdout, self._trace_bytes())

                report, output_root = self._run(fixture, runner)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["diagnostic"], "runner_invalid_json")
                self.assertEqual(report["checks"]["read_only_preflight"], "failed")
                saved_stdout = output_root / report["process"]["stdout"]["path"]
                self.assertEqual(saved_stdout.read_bytes(), stdout)
                Draft202012Validator(self.schema).validate(report)

    def test_input_drift_after_preflight_is_reported_and_never_creates_a_ledger(self):
        fixture = self._fixture()
        baseline = fixture[1]
        original = baseline["input_path"].read_bytes()

        def runner(command, **kwargs):
            baseline["input_path"].write_bytes(original + b" ")
            result = {
                "preflight_passed": True,
                "native_calls": 0,
                "stage": 1,
                "context": "a" * 64,
                "identity_sha256": "c" * 64,
            }
            return subprocess.CompletedProcess(
                command, 0, json.dumps(result).encode(), self._trace_bytes()
            )

        report, output_root = self._run(fixture, runner)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["diagnostic"], "protected_historical_material_changed")
        self.assertFalse((fixture[0] / "baseline/research/calls.jsonl").exists())
        self.assertTrue((output_root / "audit-report.json").is_file())
        Draft202012Validator(self.schema).validate(report)


if __name__ == "__main__":
    unittest.main()
