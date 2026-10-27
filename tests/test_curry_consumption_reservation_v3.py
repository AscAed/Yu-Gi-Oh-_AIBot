from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from ygo_eval import curry_consumption_reservation as reservation


class CurryConsumptionReservationV3ContractTests(unittest.TestCase):
    def test_v3_has_a_fixed_seven_checkpoint_eight_member_spec(self):
        spec = reservation._version_spec(3)

        self.assertEqual(spec.version, 3)
        self.assertEqual(spec.kind, "curry_consumption_reservation_v3")
        self.assertEqual(len(spec.checks), 7)
        self.assertEqual(len(spec.tool_files), 8)
        self.assertIn("previous_failed_attempts", spec.checks)
        self.assertIn("recovery_source_archives", spec.checks)
        self.assertEqual(spec.output_relative.as_posix(), "data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25")

    def test_v3_schema_and_cli_version_are_registered_without_changing_default(self):
        workspace = Path(__file__).resolve().parents[1]
        schema_path = workspace / "schemas/curry-consumption-reservation-v3.schema.json"
        self.assertTrue(schema_path.is_file())
        schema = json.loads(schema_path.read_bytes())
        self.assertEqual(schema["properties"]["schema_version"]["const"], 3)
        self.assertEqual(schema["properties"]["kind"]["const"], "curry_consumption_reservation_v3")
        self.assertEqual(reservation._version_spec(1).version, 1)
        self.assertEqual(reservation._version_spec(2).version, 2)

    def test_v3_ledger_path_accepts_only_the_pinned_old_scope_absolute_path(self):
        repo = Path("D:/synthetic/repo")
        allowed = repo / reservation.CONFIRMATION_RELATIVE / "research/calls.jsonl"

        self.assertEqual(
            reservation._validate_v3_ledger_path(str(allowed), repo, reservation._production_profile()),
            (reservation.CONFIRMATION_RELATIVE / "research/calls.jsonl").as_posix(),
        )
        for rejected in (
            str(repo / "data/runtime/other-scope/research/calls.jsonl"),
            str(repo / reservation.CONFIRMATION_RELATIVE / "research/../calls.jsonl"),
            "research/calls.jsonl",
        ):
            with self.subTest(path=rejected), self.assertRaises(ValueError):
                reservation._validate_v3_ledger_path(rejected, repo, reservation._production_profile())

    def test_v3_evidence_roles_are_not_lost_when_physical_paths_are_deduplicated(self):
        path = "data/runtime/confirmation/research/process-diagnostics/shared.json"
        base = {"path": path, "sha256": "a" * 64, "bytes": 10, "role": "canonical_process_diagnostic"}
        alias = {**base, "role": "confirmation_evidence_file_001"}
        paths, roles = reservation._input_index({"inputs": [base, alias]})

        self.assertEqual(len(paths), 1)
        evidence = reservation._confirmation_evidence_roles(roles, "data/runtime/confirmation/")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["role"], "confirmation_evidence_file_001")

    def test_v3_contract_rejects_success_without_the_complete_required_role_set(self):
        report = reservation._new_report(version=3)
        report["status"] = "passed"
        report["failure_checkpoint"] = None
        report["checks"] = {name: "passed" for name in reservation._version_spec(3).checks}
        with self.assertRaises(ValueError):
            reservation._validate_report(report)

    def test_v3_failed_report_checkpoints_must_match_the_execution_prefix(self):
        workspace = Path(__file__).resolve().parents[1]
        schema = json.loads((workspace / "schemas/curry-consumption-reservation-v3.schema.json").read_bytes())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        checks = reservation._version_spec(3).checks
        report = reservation._new_report(version=3)
        report["status"] = "failed"
        report["failure_checkpoint"] = "recovery_source_archives"
        report["checks"] = {
            name: "passed" if index == 0 else "failed" if index == 1 else "not_run"
            for index, name in enumerate(checks)
        }
        reservation._validate_report(report)
        validator.validate(report)

        report["checks"]["latest_delivery_chain"] = "passed"
        with self.assertRaisesRegex(ValueError, "reservation_failure_check_order_invalid"):
            reservation._validate_report(report)
        self.assertTrue(list(validator.iter_errors(report)))

        report["checks"]["latest_delivery_chain"] = "not_run"
        report["failure_checkpoint"] = None
        with self.assertRaisesRegex(ValueError, "reservation_failure_checkpoint_missing"):
            reservation._validate_report(report)
        self.assertTrue(list(validator.iter_errors(report)))


if __name__ == "__main__":
    unittest.main()
