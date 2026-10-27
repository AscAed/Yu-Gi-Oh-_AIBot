from __future__ import annotations

import hashlib
import json
import copy
from dataclasses import replace
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from ygo_eval import curry_consumption_reservation as reservation
from tests.support.curry_reservation_v3_e2e import (
    build_synthetic_v3_reservation_tree,
    invoke_v3_public_cli,
)


def assert_v3_contract(testcase, report, fixture, workspace: Path) -> None:
    original_version_spec = reservation._version_spec
    with patch.object(
        reservation, "_version_spec",
        side_effect=lambda version: fixture.spec if version == 3 else original_version_spec(version),
    ):
        reservation._validate_report(report, fixture.profile)
    schema = json.loads((workspace / "schemas/curry-consumption-reservation-v3.schema.json").read_bytes())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        testcase.fail("V3 schema mismatch: " + repr([
            (list(error.path), list(error.schema_path), error.validator, error.message[:160])
            for error in errors[:8]
        ]))


class CurryConsumptionReservationV3PublicCliTests(unittest.TestCase):
    def test_shared_path_aliases_require_identical_hash_and_length(self):
        first = {"role": "confirmation_evidence_file_0001", "path": "evidence/shared.bin", "sha256": "a" * 64, "bytes": 7}
        conflicting_hash = {"role": "confirmation_evidence_file_0002", "path": "evidence/shared.bin", "sha256": "b" * 64, "bytes": 7}
        conflicting_size = {"role": "confirmation_evidence_file_0002", "path": "evidence/shared.bin", "sha256": "a" * 64, "bytes": 8}
        for second in (conflicting_hash, conflicting_size):
            with self.subTest(second=second):
                with self.assertRaisesRegex(ValueError, "v2_input_path_hash_conflict"):
                    reservation._input_index({"inputs": [first, second]})

    def test_synthetic_v3_success_verify_and_rejects_changed_prior_failure(self):
        workspace = Path(__file__).resolve().parents[1]
        scratch_root = workspace / "target/curry-consumption-reservation-v3-tests"
        scratch_root.mkdir(parents=True, exist_ok=True)
        scratch = scratch_root / uuid.uuid4().hex
        scratch.mkdir(exist_ok=False)
        try:
            fixture = build_synthetic_v3_reservation_tree(scratch)
            stage_input_path = (
                fixture.repo / fixture.profile.confirmation_relative
                / "research/stage-1-input.json"
            )
            stage_input = json.loads(stage_input_path.read_bytes())
            self.assertEqual(
                reservation._validate_v3_ledger_path(
                    stage_input["ledger"], fixture.repo, fixture.profile,
                ),
                (fixture.profile.confirmation_relative / "research/calls.jsonl").as_posix(),
                repr(stage_input.get("ledger")),
            )
            self.assertEqual(stage_input.get("request"), json.loads(
                (fixture.repo / fixture.profile.confirmation_relative
                 / "research/stage-1-request.json").read_bytes()
            ))
            code, stdout, output_path = invoke_v3_public_cli(fixture)
            self.assertEqual(
                code, 0,
                f"{stdout}\nunderlying={getattr(fixture, 'last_audit_exception', None)}"
                f"\nshape={getattr(fixture, 'last_confirmation_shape', None)}",
            )
            report = json.loads(stdout)
            assert_v3_contract(self, report, fixture, workspace)
            original_version_spec = reservation._version_spec
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["native_calls"], 0)
            self.assertIs(report["execution_ready"], False)
            self.assertEqual(report["historical_ledgers"], {
                "ledger_count": 9,
                "consumed": 32,
                "unknown": 0,
                "verified_by_anchored_read_only_protection": True,
            })
            self.assertEqual(report["planning_basis"], {
                "certified_historical_consumed": 32,
                "risk_reserve_calls": 7,
                "planned_total": 39,
                "actual_all_history_cumulative": None,
            })
            self.assertEqual(report["old_scope"]["actual_new_consumed"], None)
            self.assertEqual(report["old_scope"]["actual_cumulative_consumed"], None)
            self.assertEqual(report["old_scope"]["actual_unknown"], None)
            self.assertIsNone(report["historical_exit_observation"]["historical_actual_exit_code"])
            self.assertEqual(report["compatibility_basis"]["confirmation_inventory"], {
                "input_role_rows": 64,
                "unique_physical_paths": 43,
                "evidence_role_rows": 40,
            })
            self.assertEqual(report["compatibility_basis"]["ledger_path_semantics"]["stored_as_absolute_windows_path"], True)
            self.assertEqual(report["checks"], {name: "passed" for name in reservation._version_spec(3).checks})
            self.assertEqual(output_path.read_bytes(), (fixture.repo / fixture.spec.output_relative / reservation.REPORT_NAME).read_bytes())

            # Exercise the actual historical-ledger verifier with the real
            # synthetic V2 input index. It must be insensitive to protection
            # array ordering while binding the Tenki ledger by its exact path.
            v2_value = json.loads((fixture.repo / fixture.profile.v2_report_relative).read_bytes())
            paths, _ = reservation._input_index(v2_value)
            ledger_pins, _ = reservation._validate_delivery_chain(
                fixture.repo, fixture.profile, copy.deepcopy(report), fixture.spec,
            )
            reordered_pins = dict(reversed(list(ledger_pins.items())))
            authenticated = reservation._verify_historical_ledgers(
                fixture.repo, paths, reordered_pins, fixture.spec,
                copy.deepcopy(report), fixture.profile,
            )
            self.assertEqual(sum(row["role"].startswith("historical_ledger_") for row in authenticated), 8)
            self.assertEqual(sum(row["role"] == "tenki_validation_ledger" for row in authenticated), 1)

            wrong_path_pins = dict(ledger_pins)
            tenki_path = fixture.profile.tenki_ledger_relative.as_posix()
            tenki_pin = wrong_path_pins.pop(tenki_path)
            wrong_path_pins[tenki_path + ".misbound"] = tenki_pin
            with self.assertRaisesRegex(ValueError, "historical_ledger_v2_binding_invalid"):
                reservation._verify_historical_ledgers(
                    fixture.repo, paths, wrong_path_pins, fixture.spec,
                    copy.deepcopy(report), fixture.profile,
                )

            wrong_acceptance_paths = copy.deepcopy(paths)
            wrong_acceptance_paths[fixture.profile.tenki_acceptance_relative.as_posix()]["sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "tenki_validation_acceptance_input_binding_invalid"):
                reservation._verify_historical_ledgers(
                    fixture.repo, wrong_acceptance_paths, ledger_pins, fixture.spec,
                    copy.deepcopy(report), fixture.profile,
                )

            wrong_directory_profile = replace(
                fixture.profile, tenki_evidence_sha256="e" * 64,
            )
            with self.assertRaisesRegex(ValueError, "historical_ledger_09_directory_hash_mismatch"):
                reservation._verify_historical_ledgers(
                    fixture.repo, paths, ledger_pins, fixture.spec,
                    copy.deepcopy(report), wrong_directory_profile,
                )

            wrong_ledger_pins = copy.deepcopy(ledger_pins)
            wrong_ledger_pins[tenki_path]["expected_sha256"] = "d" * 64
            with self.assertRaisesRegex(ValueError, "tenki_validation_ledger_pin_invalid"):
                reservation._verify_historical_ledgers(
                    fixture.repo, paths, wrong_ledger_pins, fixture.spec,
                    copy.deepcopy(report), fixture.profile,
                )

            # Mutating the authenticated directory produces a durable public
            # failure report that still satisfies both runtime and schema.
            tenki_root = fixture.repo / fixture.profile.tenki_evidence_relative
            directory_drift = tenki_root / "research/synthetic-directory-drift.bin"
            directory_drift.write_bytes(b"synthetic evidence drift\n")
            try:
                drift_code, drift_stdout, drift_path = invoke_v3_public_cli(
                    fixture,
                    output_relative=Path("data/runtime/v3-tenki-directory-drift"),
                )
                self.assertEqual(drift_code, 1, drift_stdout)
                drift_report = json.loads(drift_stdout)
                self.assertEqual(drift_report["failure_checkpoint"], "historical_ledgers")
                self.assertIn("historical_ledger_09_directory_hash_mismatch", drift_report["diagnostics"])
                assert_v3_contract(self, drift_report, fixture, workspace)
                self.assertTrue(drift_path.exists())
            finally:
                directory_drift.unlink()

            saved_output = output_path.read_bytes()
            saved_output_hash = hashlib.sha256(saved_output).hexdigest()
            verify_code, verify_stdout, _ = invoke_v3_public_cli(fixture, verify_only=True)
            self.assertEqual(verify_code, 0, verify_stdout)
            verification = json.loads(verify_stdout)
            self.assertEqual(verification["kind"], "curry_consumption_reservation_v3_verification")
            self.assertIs(verification["valid"], True)
            self.assertEqual(verification["reservation_id"], report["reservation"]["reservation_id"])
            self.assertEqual(verification["native_calls"], 0)
            self.assertEqual(hashlib.sha256(output_path.read_bytes()).hexdigest(), saved_output_hash)

            # A malformed saved report with no provenance inputs must be
            # rejected by both public verify-only and the runtime/schema
            # contracts; the original report remains recoverable.
            empty_inputs = dict(report)
            empty_inputs["inputs"] = []
            with patch.object(
                reservation, "_version_spec",
                side_effect=lambda version: fixture.spec if version == 3 else original_version_spec(version),
            ):
                with self.assertRaises(ValueError):
                    reservation._validate_report(empty_inputs, fixture.profile)
            schema = json.loads((workspace / "schemas/curry-consumption-reservation-v3.schema.json").read_bytes())
            self.assertTrue(list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(empty_inputs)))
            output_path.write_bytes(json.dumps(empty_inputs, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            empty_code, empty_stdout, _ = invoke_v3_public_cli(fixture, verify_only=True)
            self.assertEqual(empty_code, 2, empty_stdout)
            output_path.write_bytes(saved_output)

            # Verification compares the complete output tree before and after
            # reading the saved report. A concurrent synthetic write is caught.
            tree_code, tree_stdout, _ = invoke_v3_public_cli(
                fixture, verify_only=True, mutate_output_tree_during_verify=True,
            )
            self.assertEqual(tree_code, 2, tree_stdout)
            drift_file = output_path.parent / "verify-drift.bin"
            self.assertTrue(drift_file.exists())
            drift_file.unlink()
            self.assertEqual(output_path.read_bytes(), saved_output)

            # Reproduce the external V2 acceptance TOCTOU: mutate it only
            # after its hash has been read and recorded by historical audit.
            external_acceptance = fixture.repo / fixture.profile.v2_acceptance_relative
            acceptance_before = external_acceptance.read_bytes()
            try:
                changed_code, changed_stdout, changed_path = invoke_v3_public_cli(
                    fixture,
                    output_relative=Path("data/runtime/v3-external-acceptance-toctou"),
                    mutate_external_v2_acceptance_after_validation=True,
                )
                self.assertEqual(changed_code, 1, changed_stdout)
                changed_report = json.loads(changed_stdout)
                self.assertEqual(changed_report["failure_checkpoint"], "input_stability")
                self.assertEqual(changed_report["stability"]["v2_recovery_sources_tree"], "failed")
                assert_v3_contract(self, changed_report, fixture, workspace)
                self.assertTrue(changed_path.exists())
            finally:
                external_acceptance.write_bytes(acceptance_before)

            prior_raw = fixture.v1_report.read_bytes()
            try:
                fixture.v1_report.write_bytes(prior_raw + b"\n")
                rejected_code, _, _ = invoke_v3_public_cli(fixture, verify_only=True)
                self.assertEqual(rejected_code, 2)
                self.assertEqual(output_path.read_bytes(), saved_output)
            finally:
                fixture.v1_report.write_bytes(prior_raw)

            restored_code, restored_stdout, _ = invoke_v3_public_cli(fixture, verify_only=True)
            self.assertEqual(restored_code, 0, restored_stdout)
            self.assertEqual(output_path.read_bytes(), saved_output)
        finally:
            shutil.rmtree(scratch, ignore_errors=False)


if __name__ == "__main__":
    unittest.main()
