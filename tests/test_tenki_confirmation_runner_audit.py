"""Synthetic, zero-worker tests for the confirmation runner offline audit."""
from __future__ import annotations

import json
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_data.identity import canonical, digest
from ygo_eval import tenki_confirmation_runner_audit as audit


class TenkiConfirmationRunnerAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.scratch_root = (
            cls.repo_root
            / "data/runtime/p1-tenki-runner-repair-offline-2026-10-23/test-fixtures"
        )
        cls.scratch_root.mkdir(parents=True, exist_ok=True)
        cls.schema = json.loads(
            (cls.repo_root / "schemas/tenki-runner-offline-audit-v1.schema.json").read_bytes()
        )

    def _fixture(self):
        # Keep synthetic evidence in the ignored batch directory. Do not use
        # TemporaryDirectory here: its Windows ACL cleanup is restricted on
        # this host, so fixtures remain as uniquely named audit evidence.
        root = self.scratch_root / f"audit-fixture-{uuid.uuid4().hex}"
        root.mkdir()
        temp = type("TempTree", (), {"cleanup": lambda _self: None})()
        schema_dir = root / "schemas"
        schema_dir.mkdir()
        (schema_dir / "tenki-runner-offline-audit-v1.schema.json").write_bytes(
            (self.repo_root / "schemas/tenki-runner-offline-audit-v1.schema.json").read_bytes()
        )
        baseline_dir = root / "baseline"
        baseline_dir.mkdir()
        input_path = baseline_dir / "stage-1-input.json"
        expected_identity = {"identity": "c" * 64, "kind": "engine_identity"}
        input_raw = json.dumps(
            {"context": "a" * 64, "stage": 1, "expected_identity": expected_identity},
            separators=(",", ":"),
        ).encode("utf-8")
        input_path.write_bytes(input_raw)
        output_root = root / "audit"
        artifact_dir = output_root / "native-artifacts"
        artifact_dir.mkdir(parents=True)
        runner = artifact_dir / "tenki-placement-probe.exe"
        runner.write_bytes(b"synthetic runner bytes")
        source = {"head": "synthetic", "files": {"marker": "1" * 64}, "identity": "2" * 64}
        unsigned = {
            "schema_version": 1,
            "kind": "build_record",
            "source_before": source,
            "source_after": source,
            "status": "recorded",
            "reproducible_build_proven": False,
            "artifacts": {"runner": digest(runner.read_bytes())},
        }
        build_value = {**unsigned, "identity": digest(canonical(unsigned))}
        build_path = output_root / "build-record.json"
        build_path.write_bytes(canonical(build_value))
        protected = {input_path: digest(input_raw)}
        baseline = {
            "context": "a" * 64,
            "source_identity": "f" * 64,
            "protected": protected,
            "input_records": [{
                "role": "stage1_input",
                "path": input_path.relative_to(root).as_posix(),
                "sha256": digest(input_raw),
                "bytes": len(input_raw),
            }],
            "source_archives": [
                {"role": "native_time", "sha256": "3" * 64, "file_list_sha256": "4" * 64, "file_count": 10},
                {"role": "final", "sha256": "5" * 64, "file_list_sha256": "6" * 64, "file_count": 11},
            ],
            "input_path": input_path,
            "input_sha256": digest(input_raw),
            "expected_identity": expected_identity,
        }
        return temp, root, baseline_dir, output_root, runner, build_path, input_path, baseline, source

    @staticmethod
    def _trace_bytes():
        rows = []
        for phase in ("input_validation", "shared_preflight"):
            rows.append({"phase": phase, "event": "start"})
            rows.append({"phase": phase, "event": "end", "elapsed_ns": 8})
        return b"\n".join(json.dumps(row, separators=(",", ":")).encode("utf-8") for row in rows)

    def _run(self, fixture, process_runner, baseline_verifier=None):
        temp, root, baseline_dir, output_root, runner, build_path, _input_path, baseline, _source = fixture
        output_path = output_root / "audit-report.json"
        with (
            patch.object(audit, "OUTPUT_RELATIVE", Path("audit")),
            patch.object(audit, "stable_source", return_value={
                "head": "synthetic", "files": {"marker": "1" * 64}, "identity": "2" * 64
            }),
        ):
            report = audit._run_audit(
                repo=root,
                baseline_dir=baseline_dir,
                runner=runner,
                build_record=build_path,
                output_root=output_root,
                output_path=output_path,
                process_runner=process_runner,
                baseline_verifier=baseline_verifier or (lambda _repo, _path: baseline),
            )
        self.assertTrue(output_path.is_file())
        saved = json.loads(output_path.read_bytes())
        self.assertEqual(saved, report)
        return report, output_root

    def test_success_saves_raw_io_before_parsing_and_accepts_only_preflight(self):
        fixture = self._fixture()
        temp, root, _baseline_dir, _output_root, _runner, _build, _input_path, _baseline, _source = fixture
        observed = {}

        def process_runner(command, *, cwd, capture_output, timeout, check):
            observed.update(command=command, cwd=cwd, capture_output=capture_output, timeout=timeout, check=check)
            output = {
                "preflight_passed": True,
                "native_calls": 0,
                "stage": 1,
                "context": "a" * 64,
                "identity_sha256": "c" * 64,
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), self._trace_bytes())

        try:
            report, output_root = self._run(fixture, process_runner)
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["native_calls"], 0)
            self.assertFalse(report["execution_ready"])
            self.assertEqual(report["original_native_diagnostic"], "runner_timeout")
            self.assertEqual(report["source"]["baseline_source_identity"], "f" * 64)
            self.assertEqual(report["source"]["workspace_identity"], "2" * 64)
            self.assertEqual(report["source"]["source_identity"], "2" * 64)
            self.assertEqual(observed["timeout"], audit.PREFLIGHT_TIMEOUT_SECONDS)
            self.assertEqual(observed["command"][-2:], ["--preflight-only", "--trace-stderr"])
            self.assertNotIn("--stats", observed["command"])
            self.assertNotIn("--verify-recorded", observed["command"])
            process = report["process"]
            raw_stdout = (output_root / process["stdout"]["path"]).read_bytes()
            raw_stderr = (output_root / process["stderr"]["path"]).read_bytes()
            self.assertEqual(raw_stdout, json.dumps({
                "preflight_passed": True, "native_calls": 0, "stage": 1,
                "context": "a" * 64, "identity_sha256": "c" * 64,
            }).encode())
            self.assertEqual(raw_stderr, self._trace_bytes())
            Draft202012Validator(self.schema).validate(report)
            self.assertTrue(audit.validate_report(report, repo=root, artifact_root=output_root))
        finally:
            temp.cleanup()

    def test_two_json_documents_are_saved_then_rejected(self):
        fixture = self._fixture()
        temp = fixture[0]
        def process_runner(command, **kwargs):
            output = json.dumps({"preflight_passed": True}).encode() + b"\n{}"
            return subprocess.CompletedProcess(command, 0, output, self._trace_bytes())
        try:
            report, output_root = self._run(fixture, process_runner)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["diagnostic"], "runner_invalid_json")
            stdout_path = output_root / report["process"]["stdout"]["path"]
            self.assertEqual(stdout_path.read_bytes(), json.dumps({"preflight_passed": True}).encode() + b"\n{}")
            Draft202012Validator(self.schema).validate(report)
        finally:
            temp.cleanup()

    def test_invalid_utf8_stdout_is_saved_and_reported(self):
        fixture = self._fixture()
        temp = fixture[0]
        def process_runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, b"\xff", self._trace_bytes())
        try:
            report, output_root = self._run(fixture, process_runner)
            self.assertEqual(report["diagnostic"], "runner_invalid_json")
            self.assertEqual((output_root / report["process"]["stdout"]["path"]).read_bytes(), b"\xff")
            Draft202012Validator(self.schema).validate(report)
        finally:
            temp.cleanup()

    def test_timeout_partial_output_is_preserved_and_consumption_is_not_inferred(self):
        fixture = self._fixture()
        temp = fixture[0]
        def process_runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial", stderr=b"partial trace")
        try:
            report, output_root = self._run(fixture, process_runner)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["diagnostic"], "runner_timeout")
            self.assertEqual(report["native_calls"], 0)
            self.assertEqual((output_root / report["process"]["stdout"]["path"]).read_bytes(), b"partial")
            self.assertEqual((output_root / report["process"]["stderr"]["path"]).read_bytes(), b"partial trace")
            Draft202012Validator(self.schema).validate(report)
        finally:
            temp.cleanup()

    def test_baseline_failure_stops_before_process_but_still_saves_report(self):
        fixture = self._fixture()
        temp = fixture[0]
        calls = []
        def process_runner(*args, **kwargs):
            calls.append(args)
            raise AssertionError("preflight must not run when baseline verification fails")
        def broken_baseline(_repo, _path):
            raise ValueError("pinned_input_hash_mismatch")
        try:
            report, _output_root = self._run(fixture, process_runner, baseline_verifier=broken_baseline)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["diagnostic"], "pinned_input_hash_mismatch")
            self.assertEqual(calls, [])
            self.assertIsNone(report["process"])
            Draft202012Validator(self.schema).validate(report)
        finally:
            temp.cleanup()

    def test_input_drift_after_preflight_fails_after_raw_capture(self):
        fixture = self._fixture()
        temp, _root, _baseline_dir, _output_root, _runner, _build, input_path, _baseline, _source = fixture
        def process_runner(command, **kwargs):
            input_path.write_bytes(input_path.read_bytes() + b" ")
            output = {
                "preflight_passed": True, "native_calls": 0, "stage": 1,
                "context": "a" * 64, "identity_sha256": "c" * 64,
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), self._trace_bytes())
        try:
            report, output_root = self._run(fixture, process_runner)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["diagnostic"], "pinned_input_hash_mismatch")
            self.assertEqual(report["checks"]["input_stability"], "failed")
            self.assertTrue((output_root / report["process"]["stdout"]["path"]).is_file())
            Draft202012Validator(self.schema).validate(report)
        finally:
            temp.cleanup()

    def test_qualification_flags_and_absolute_input_path_are_rejected(self):
        fixture = self._fixture()
        temp = fixture[0]
        def process_runner(command, **kwargs):
            output = {
                "preflight_passed": True, "native_calls": 0, "stage": 1,
                "context": "a" * 64, "identity_sha256": "c" * 64,
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), self._trace_bytes())
        try:
            report, _ = self._run(fixture, process_runner)
            forged = dict(report)
            forged["proof_ready"] = True
            with self.assertRaises(Exception):
                Draft202012Validator(self.schema).validate(forged)
            forged = json.loads(json.dumps(report))
            forged["inputs"][0]["path"] = "D:/private/input.json"
            with self.assertRaises(Exception):
                Draft202012Validator(self.schema).validate(forged)
            forged = json.loads(json.dumps(report))
            forged["process"]["parsed_result"]["identity_sha256"] = "d" * 64
            with self.assertRaises(ValueError):
                audit.validate_report(forged, repo=fixture[1], artifact_root=fixture[3])
        finally:
            temp.cleanup()

    def test_pinned_delivery_shape_has_no_status_and_identity_bytes_are_distinct(self):
        delivery = {
            "schema_version": 1,
            "kind": "native_tenki_placement_confirmation_delivery",
            "scope": "tenki-placement-confirmation-v1",
            "context": "0f55ccf433f7d0e90421cf40850e64de8c02614404ec8d6028e767dfbbbbb138",
            "history_totals": {"consumed": 26, "old_runner_availability_reverified": False, "unknown": 0},
            "native_outcome": {"first_stage_diagnostic": "runner_timeout", "charged_calls": 0, "unknown_consumption": 0},
            "window": {"remaining_slots_authorized": 0},
            "qualifications": dict(audit.FLAGS),
        }
        self.assertNotIn("status", delivery)
        audit._validate_delivery_header(delivery)

        expected = {"kind": "engine_identity", "identity": "c" * 64}
        identity_file = {
            "kind": "workspace_identity",
            "schema_version": 1,
            "consistent": True,
            "runtimes": {"ordinary": expected},
        }
        identity_raw = canonical(identity_file)
        manifest = {"input_sha256": {"identity": digest(identity_raw)}}
        invocation = {"expected_identity": expected}
        audit._validate_identity_binding(manifest, invocation, identity_file, digest(identity_raw))
        manifest["input_sha256"]["identity"] = digest(canonical(expected))
        with self.assertRaises(ValueError):
            audit._validate_identity_binding(manifest, invocation, identity_file, digest(identity_raw))

    def test_delivery_context_can_only_be_overridden_by_fixed_source_pin(self):
        delivery = {
            "schema_version": 1,
            "kind": "native_tenki_placement_confirmation_delivery",
            "scope": "tenki-placement-confirmation-v1",
            "context": "a" * 64,
            "history_totals": {"consumed": 26, "old_runner_availability_reverified": False, "unknown": 0},
            "native_outcome": {"first_stage_diagnostic": "runner_timeout", "charged_calls": 0, "unknown_consumption": 0},
            "window": {"remaining_slots_authorized": 0},
            "qualifications": dict(audit.FLAGS),
        }
        with self.assertRaises(ValueError):
            audit._validate_delivery_header(delivery)

        audit._validate_delivery_header(delivery, expected_context="a" * 64)
        delivery["scope"] = "other-scope"
        with self.assertRaises(ValueError):
            audit._validate_delivery_header(delivery, expected_context="a" * 64)

    def test_input_role_accepts_historical_scope_name_hyphens(self):
        Draft202012Validator(
            self.schema["$defs"]["input"]["properties"]["role"]
        ).validate("historical_ledger_terminal-followup")

    def test_trace_requires_only_ordered_preflight_prefix(self):
        exact = self._trace_bytes()
        self.assertIsNone(audit._trace_summary(exact)[1])
        extra = exact + b"\n" + json.dumps({
            "phase": "ledger_check", "event": "start"
        }).encode()
        self.assertEqual(audit._trace_summary(extra)[1], "runner_trace_invalid")
        wrong_order = b"\n".join([
            json.dumps({"phase": "shared_preflight", "event": "start"}).encode(),
            json.dumps({"phase": "shared_preflight", "event": "end", "elapsed_ns": 1}).encode(),
            json.dumps({"phase": "input_validation", "event": "start"}).encode(),
            json.dumps({"phase": "input_validation", "event": "end", "elapsed_ns": 1}).encode(),
        ])
        self.assertIsNotNone(audit._trace_summary(wrong_order)[1])

    def test_runner_and_build_are_rechecked_after_the_stubbed_process(self):
        for selected in ("runner", "build"):
            with self.subTest(selected=selected):
                fixture = self._fixture()
                temp, _root, _baseline, _output, runner, build, _input, _binding, _source = fixture

                def process_runner(command, **kwargs):
                    target = runner if selected == "runner" else build
                    target.write_bytes(target.read_bytes() + b"drift")
                    output = {
                        "preflight_passed": True,
                        "native_calls": 0,
                        "stage": 1,
                        "context": "a" * 64,
                        "identity_sha256": "c" * 64,
                    }
                    return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), self._trace_bytes())

                try:
                    report, _ = self._run(fixture, process_runner)
                    self.assertEqual(report["status"], "failed")
                    self.assertEqual(report["checks"]["input_stability"], "failed")
                    self.assertEqual(report["diagnostic"], "pinned_input_hash_mismatch")
                finally:
                    temp.cleanup()

    def test_all_raw_process_sidecars_are_rechecked_after_parsing(self):
        for suffix in (".json", ".stdout.bin", ".stderr.bin"):
            with self.subTest(suffix=suffix):
                fixture = self._fixture()
                temp, _root, _baseline, output_root, _runner, _build, _input, _binding, _source = fixture

                def process_runner(command, **kwargs):
                    output = {
                        "preflight_passed": True,
                        "native_calls": 0,
                        "stage": 1,
                        "context": "a" * 64,
                        "identity_sha256": "c" * 64,
                    }
                    return subprocess.CompletedProcess(command, 0, json.dumps(output).encode(), self._trace_bytes())

                original_trace = audit._trace_summary

                def mutate_sidecar(stderr):
                    candidate = next(output_root.glob(f"process-diagnostics/*{suffix}"))
                    candidate.write_bytes(candidate.read_bytes() + b"drift")
                    return original_trace(stderr)

                try:
                    with patch.object(audit, "_trace_summary", side_effect=mutate_sidecar):
                        report, _ = self._run(fixture, process_runner)
                    self.assertEqual(report["status"], "failed")
                    self.assertEqual(report["checks"]["input_stability"], "failed")
                    self.assertEqual(report["diagnostic"], "pinned_input_hash_mismatch")
                finally:
                    temp.cleanup()


if __name__ == "__main__":
    unittest.main()
