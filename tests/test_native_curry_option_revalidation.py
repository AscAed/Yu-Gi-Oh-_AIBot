"""Fixed-scope tests for the V3-recovery-bound Curry revalidation run."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import ygo_eval.native_curry_option_validation as curry
from ygo_eval.research import main as research_main


class CurryOptionRevalidationTests(unittest.TestCase):
    def test_preflight_zero_call_check_is_strict_only_for_reservation_scopes(self):
        for spec in (curry.OPTION_VERIFICATION_SCOPE, curry.OPTION_REVALIDATION_SCOPE):
            with self.subTest(scope=spec.scope):
                self.assertTrue(curry._zero_call_count_valid(
                    {"native_calls": 0}, spec,
                ))
                for invalid in (False, 0.0, None):
                    self.assertFalse(curry._zero_call_count_valid(
                        {"native_calls": invalid}, spec,
                    ))

        # Preserve the legacy predicate semantics for scopes without reservation accounting.
        self.assertTrue(curry._zero_call_count_valid(
            {"native_calls": False}, curry.CURRY_SCOPE,
        ))

    def test_reservation_reports_reject_boolean_native_calls(self):
        spec = curry.OPTION_REVALIDATION_SCOPE
        prepared = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "prepared"),
            "scope": spec.scope,
            "context": "a" * 64,
            **curry.FLAGS,
            "prepared": False,
            "execution_ready": False,
            "native_calls": False,
            "planned_calls": spec.limit,
            "manifest_sha256": "b" * 64,
            "stage1_request_sha256": "c" * 64,
            "stage1_input_sha256": "d" * 64,
            "preflight_diagnostic_sha256": "e" * 64,
        }
        with self.assertRaisesRegex(ValueError, "curry_prepared_binding_invalid"):
            curry.validate_curry_report(prepared, spec=spec)

        verification = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "verification"),
            "scope": spec.scope,
            "context": "a" * 64,
            **curry.FLAGS,
            "valid": False,
            "native_calls": False,
            "ledger": None,
            "stages": [],
            "prepared_sha256": "f" * 64,
            "verification_diagnostic_sha256": [],
            "diagnostic": "verification_incomplete",
            **curry._verification_manifest_fields(spec),
            "new_consumed": None,
            "certified_consumed_including_new": None,
            "planning_total": None,
            "unknown": None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        }
        with self.assertRaisesRegex(ValueError, "curry_verification_fields_invalid"):
            curry.validate_curry_report(verification, spec=spec)

    def test_revalidation_is_a_fourth_fixed_and_reservation_bound_scope(self):
        spec = curry.OPTION_REVALIDATION_SCOPE
        self.assertEqual(spec.scope, "curry-option-revalidation-v1")
        self.assertEqual(
            spec.output_root,
            Path("data/runtime/p1-curry-option-revalidation-native-2026-10-26"),
        )
        self.assertEqual(spec.limit, 7)
        self.assertEqual(spec.wall_seconds, 7200)
        self.assertEqual(spec.worker_timeout_seconds, 30)
        self.assertEqual(spec.batch_kind, "curry-option-revalidation-v1")
        self.assertEqual(
            spec.input_seal_kind,
            "curry_option_revalidation_stage_input_seal",
        )
        self.assertEqual(spec.runner_role, "curry_option_revalidation_runner")
        self.assertEqual(
            spec.report_prefix, "native_curry_option_revalidation"
        )
        roles = curry._manifest_roles(spec)
        self.assertEqual(len(roles), 22)
        self.assertEqual(len(set(roles)), 22)
        self.assertIn("baseline_delivery", roles)
        self.assertIn("baseline_recovery", roles)
        self.assertIn("consumption_reservation", roles)
        self.assertEqual(curry._window_kind(spec), "curry_option_revalidation_window_start")

    def test_revalidation_source_pins_bind_delivery_recovery_and_reservation(self):
        spec = curry.OPTION_REVALIDATION_SCOPE
        pins = curry._pinned_inputs(spec)
        self.assertEqual(
            pins["baseline_delivery"],
            "dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55",
        )
        self.assertEqual(
            pins["baseline_recovery"],
            "69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468",
        )
        self.assertEqual(
            pins["consumption_reservation"],
            "14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f",
        )
        fields = curry._verification_manifest_fields(spec)
        self.assertEqual(fields["certified_historical_consumed"], 33)
        self.assertEqual(fields["policy_reserved"], 7)
        self.assertEqual(fields["planning_base"], 40)
        self.assertEqual(
            fields["reservation_id"],
            "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63",
        )

    def test_source_manifest_fields_keep_each_fixed_scope_disjoint(self):
        self.assertEqual(
            set(curry._source_manifest_fields(curry.CURRY_SCOPE)),
            {"baseline_acceptance_sha256", "baseline_delivery_sha256"},
        )
        self.assertEqual(
            set(curry._source_manifest_fields(curry.CONFIRMATION_SCOPE)),
            {"baseline_audit_sha256", "baseline_delivery_sha256"},
        )
        self.assertEqual(
            set(curry._source_manifest_fields(curry.OPTION_VERIFICATION_SCOPE)),
            {"baseline_acceptance_sha256"},
        )
        self.assertEqual(
            curry._source_manifest_fields(curry.OPTION_REVALIDATION_SCOPE),
            {
                "baseline_delivery_sha256": curry.OPTION_REVALIDATION_SCOPE.delivery_sha256,
                "baseline_recovery_sha256": curry.OPTION_REVALIDATION_SCOPE.baseline_recovery_sha256,
            },
        )

    def test_revalidation_summary_keeps_certified_and_planning_totals_separate(self):
        spec = curry.OPTION_REVALIDATION_SCOPE
        stats = {"consumed": 7, "completed": 7, "unknown": 0,
                 "reserved": 0, "abandoned": 0, "limit": 7}
        summary = curry.summarize_curry_validation(
            "c" * 64,
            [{"stage": n, "successful": True, "native_calls": 1,
              "independent_replay_matches": True if n in (5, 7) else None}
             for n in range(1, 8)],
            stats,
            spec=spec,
        )
        self.assertEqual(summary["new_consumed"], 7)
        self.assertEqual(summary["certified_historical_consumed"], 33)
        self.assertEqual(summary["policy_reserved"], 7)
        self.assertEqual(summary["planning_base"], 40)
        self.assertEqual(summary["certified_consumed_including_new"], 40)
        self.assertEqual(summary["planning_total"], 47)
        self.assertIsNone(summary["old_confirmation_actual_consumed"])
        self.assertIsNone(summary["actual_all_history_cumulative"])

    def test_unsettled_ledger_preserves_raw_stats_but_leaves_derived_totals_null(self):
        from jsonschema import Draft202012Validator

        spec = curry.OPTION_REVALIDATION_SCOPE
        ledger = {
            "consumed": 1, "completed": 0, "unknown": 1,
            "reserved": 0, "abandoned": 1, "limit": 7,
        }
        summary = curry.summarize_curry_validation(
            "c" * 64, [], ledger, "ledger_has_unresolved_consumption", spec=spec,
        )
        self.assertIsNone(summary["new_consumed"])
        self.assertIsNone(summary["certified_consumed_including_new"])
        self.assertIsNone(summary["planning_total"])
        self.assertEqual(summary["unknown"], 1)
        self.assertEqual(summary["ledger"], ledger)
        self.assertTrue(curry.validate_curry_report(summary, spec=spec))
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "native-curry-option-revalidation.schema.json"
        )
        Draft202012Validator.check_schema(
            json.loads(schema_path.read_text(encoding="utf-8"))
        )
        Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        ).validate(summary)

        verification = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "verification"),
            "scope": spec.scope,
            "context": "c" * 64,
            "valid": False,
            "native_calls": 0,
            "ledger": ledger,
            "stages": [],
            "prepared_sha256": "a" * 64,
            "verification_diagnostic_sha256": [],
            "diagnostic": "ledger_has_unresolved_consumption",
            "certified_historical_consumed": 33,
            "policy_reserved": 7,
            "planning_base": 40,
            "reservation_id": spec.reservation_id,
            "reservation_policy_id": spec.reservation_policy_id,
            "new_consumed": None,
            "certified_consumed_including_new": None,
            "planning_total": None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
            "unknown": 1,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        self.assertTrue(curry.validate_curry_report(verification, spec=spec))
        Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        ).validate(verification)

    def test_revalidation_reports_require_explicit_null_unknown_cumulative_fields(self):
        spec = curry.OPTION_REVALIDATION_SCOPE
        ledger = {
            "consumed": 1, "completed": 0, "unknown": 1,
            "reserved": 0, "abandoned": 1, "limit": 7,
        }
        summary = curry.summarize_curry_validation(
            "c" * 64, [], ledger, "ledger_has_unresolved_consumption", spec=spec,
        )
        verification = {
            "schema_version": 1,
            "kind": curry._report_kind(spec, "verification"),
            "scope": spec.scope,
            "context": "c" * 64,
            "valid": False,
            "native_calls": 0,
            "ledger": ledger,
            "stages": [],
            "prepared_sha256": "a" * 64,
            "verification_diagnostic_sha256": [],
            "diagnostic": "ledger_has_unresolved_consumption",
            "certified_historical_consumed": 33,
            "policy_reserved": 7,
            "planning_base": 40,
            "reservation_id": spec.reservation_id,
            "reservation_policy_id": spec.reservation_policy_id,
            "new_consumed": None,
            "certified_consumed_including_new": None,
            "planning_total": None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
            "unknown": 1,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }

        for report_name, report in (("summary", summary), ("verification", verification)):
            for field in (
                "old_confirmation_actual_consumed",
                "actual_all_history_cumulative",
            ):
                invalid = dict(report)
                del invalid[field]
                with self.subTest(report=report_name, missing=field):
                    with self.assertRaisesRegex(
                        ValueError, "curry_verification_accounting_basis_invalid",
                    ):
                        curry.validate_curry_report(invalid, spec=spec)

    def test_revalidation_cli_command_is_registered(self):
        with self.assertRaises(SystemExit) as raised:
            with patch("sys.argv", ["ygo-research", "native-curry-option-revalidation", "--help"]):
                research_main()
        self.assertEqual(raised.exception.code, 0)

    def test_revalidation_contract_is_a_distinct_schema(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "native-curry-option-revalidation.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], schema_path.name)
        self.assertIn("manifest", schema["$defs"])
        self.assertIn("summary", schema["$defs"])
        self.assertEqual(
            schema["$defs"]["common"]["allOf"][0]["properties"]["scope"]["const"],
            "curry-option-revalidation-v1",
        )

    def test_revalidation_schema_pins_exact_roles_and_accounting_contract(self):
        from jsonschema import Draft202012Validator

        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "native-curry-option-revalidation.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        self.assertEqual(schema["$id"], schema_path.name)
        input_contract = schema["$defs"]["manifest"]["allOf"][1]["properties"]["input_sha256"]
        expected_roles = {
            "preparation", "preparation_report", "preparation_acceptance",
            "candidate_case", "base_request", "operations_source", "adapter_codec",
            "runner", "worker", "cli", "build_record", "identity", "window_start",
            "source_archive", "source_file_list", "ordinary_config",
            "tournament_config", "banlist", "core_source", "baseline_delivery",
            "baseline_recovery", "consumption_reservation",
        }
        self.assertEqual(set(input_contract["required"]), expected_roles)
        self.assertEqual(len(input_contract["properties"]), 22)
        self.assertEqual(input_contract["minProperties"], 22)
        self.assertEqual(input_contract["maxProperties"], 22)
        self.assertEqual(
            input_contract["properties"]["baseline_delivery"]["const"],
            "dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55",
        )
        self.assertEqual(
            input_contract["properties"]["baseline_recovery"]["const"],
            "69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468",
        )

        manifest_contract = schema["$defs"]["manifest"]["allOf"][1]["properties"]
        self.assertEqual(
            manifest_contract["kind"]["const"],
            "native_curry_option_revalidation_manifest",
        )
        self.assertEqual(
            manifest_contract["batch_kind"]["const"],
            "curry-option-revalidation-v1",
        )
        self.assertEqual(
            manifest_contract["certified_historical_consumed"]["const"], 33,
        )
        self.assertEqual(manifest_contract["policy_reserved"]["const"], 7)
        self.assertEqual(manifest_contract["planning_base"]["const"], 40)

        input_hashes = {
            role: role_schema.get("const", "a" * 64)
            for role, role_schema in input_contract["properties"].items()
        }
        manifest = {
            "schema_version": 1,
            "kind": "native_curry_option_revalidation_manifest",
            "scope": "curry-option-revalidation-v1",
            "context": "b" * 64,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "batch_kind": "curry-option-revalidation-v1",
            "started_at": 1_798_300_000,
            "limit": 7,
            "planned_calls": 7,
            "wall_seconds": 7200,
            "input_sha256": input_hashes,
            "source": {},
            "historical_source_transition": manifest_contract[
                "historical_source_transition"
            ]["const"],
            "build": {},
            "assets": {},
            "stage1_request_sha256": "c" * 64,
            "request_derivation": manifest_contract["request_derivation"]["const"],
            "request": {"protocol_version": 2, "seed": 1, "decisions": []},
            "baseline_delivery_sha256": "dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55",
            "baseline_recovery_sha256": "69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468",
            "consumption_reservation_sha256": "14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f",
            "reservation_id": "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63",
            "reservation_policy_id": "curry-unknown-reserve-seven-v1",
            "certified_historical_consumed": 33,
            "policy_reserved": 7,
            "planning_base": 40,
        }
        validator.validate(manifest)
        with_forbidden_legacy_role = dict(manifest)
        with_forbidden_legacy_role["baseline_audit_sha256"] = "e" * 64
        unsigned_bad = {
            key: value for key, value in with_forbidden_legacy_role.items()
            if key != "context"
        }
        with_forbidden_legacy_role["context"] = __import__("hashlib").sha256(
            curry.canonical(unsigned_bad)
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "curry_manifest_binding_invalid"):
            curry.validate_curry_report(
                with_forbidden_legacy_role,
                spec=curry.OPTION_REVALIDATION_SCOPE,
            )

        stats = {
            "consumed": 7, "completed": 7, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 7,
        }
        stages = []
        for stage in range(1, 8):
            stage_stats = dict(stats, consumed=stage, completed=stage)
            stages.append({
                "stage": stage,
                "successful": True,
                "native_calls": 1,
                "diagnostic": None,
                "receipt_sha256": f"{stage:064x}",
                "diagnostic_sha256": "d" * 64,
                "independent_replay_matches": True if stage in (5, 7) else None,
                "ledger": stage_stats,
            })
        summary = {
            "schema_version": 1,
            "kind": "native_curry_option_revalidation_summary",
            "scope": "curry-option-revalidation-v1",
            "context": "b" * 64,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            "successful": True,
            "new_consumed": 7,
            "unknown": 0,
            "ledger": stats,
            "stages": stages,
            "diagnostic": None,
            "certified_historical_consumed": 33,
            "policy_reserved": 7,
            "planning_base": 40,
            "reservation_id": "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63",
            "reservation_policy_id": "curry-unknown-reserve-seven-v1",
            "certified_consumed_including_new": 40,
            "planning_total": 47,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        }
        validator.validate(summary)

        invalid_documents = []
        wrong_scope = dict(summary, scope="curry-option-verification-v1")
        invalid_documents.append(wrong_scope)
        wrong_certified_base = dict(summary, certified_historical_consumed=32)
        invalid_documents.append(wrong_certified_base)
        wrong_policy_reserve = dict(summary, policy_reserved=0)
        invalid_documents.append(wrong_policy_reserve)
        wrong_planning_base = dict(summary, planning_base=39)
        invalid_documents.append(wrong_planning_base)
        wrong_certified_total = dict(summary, certified_consumed_including_new=39)
        invalid_documents.append(wrong_certified_total)
        wrong_planning_total = dict(summary, planning_total=46)
        invalid_documents.append(wrong_planning_total)
        claimed_actual = dict(summary, actual_all_history_cumulative=40)
        invalid_documents.append(claimed_actual)
        for invalid in invalid_documents:
            with self.subTest(document=invalid):
                self.assertTrue(list(validator.iter_errors(invalid)))

        missing_role = dict(manifest)
        missing_role["input_sha256"] = dict(input_hashes)
        del missing_role["input_sha256"]["baseline_recovery"]
        self.assertTrue(list(validator.iter_errors(missing_role)))
        unexpected_role = dict(manifest)
        unexpected_role["input_sha256"] = dict(input_hashes, baseline_acceptance="e" * 64)
        self.assertTrue(list(validator.iter_errors(unexpected_role)))


if __name__ == "__main__":
    unittest.main()
