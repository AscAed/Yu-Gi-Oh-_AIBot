import argparse
import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ygo_data.identity import canonical, digest
from ygo_eval.native_tenki_placement_validation import (
    MANIFEST_INPUT_ROLES,
    VALIDATION_SCOPE,
    _normal_runner_timeout,
    _resolve_delivery_path,
    derive_stage_request,
    validate_auto_decisions,
    validate_report,
    validate_stage_receipt,
)
from ygo_eval.native_tenki_placement_confirmation import SCOPE as CONFIRMATION_SCOPE


def _u32(value):
    return list(value.to_bytes(4, "little"))


def _singleton_idle_event(prompt_id=22, command=7):
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
    return {"sequence": prompt_id, "opcode": 11, "supported": True,
            "raw": list(raw), "fields": {"prompt": prompt}}


def _opcode13_event(prompt_id=23):
    prompt = {
        "id": prompt_id,
        "opcode": 13,
        "player": 0,
        "actions": [
            {"choice": {"kind": "yes_no", "yes": False}, "bytes": [0, 0, 0, 0]},
            {"choice": {"kind": "yes_no", "yes": True}, "bytes": [1, 0, 0, 0]},
        ],
    }
    raw = bytes([13, 0]) + (59877851398144).to_bytes(8, "little")
    return {"sequence": prompt_id, "opcode": 13, "supported": True,
            "raw": list(raw), "fields": {"prompt": prompt}}


def _opcode15_result(prompt_id=91):
    records = b""
    for sequence in (7, 8):
        records += (69247929).to_bytes(4, "little") + bytes([0, 1])
        records += sequence.to_bytes(4, "little") + (1).to_bytes(4, "little")
    raw = bytes([15, 0, 0]) + (1).to_bytes(4, "little") + (1).to_bytes(4, "little")
    raw += (2).to_bytes(4, "little") + records
    actions = []
    for index in range(2):
        actions.append({
            "card_ids": [69247929],
            "choice": {"kind": "cards", "indices": [index]},
            "bytes": [0, 0, 0, 0, 1, 0, 0, 0, index, 0, 0, 0],
        })
    prompt = {"id": prompt_id, "opcode": 15, "player": 0, "actions": actions}
    event = {"sequence": prompt_id, "opcode": 15, "supported": True,
             "raw": list(raw), "fields": {"prompt": prompt}}
    return {"status": "decision_required", "error": None, "coverage_gaps": [],
            "resolved_decisions": [], "prompt": prompt, "events": [event]}


def _success_receipt(stage, request=None):
    request = request or {"decisions": []}
    prompt_ops = {1: 18, 2: 13, 3: 11, 4: 11, 5: 15, 6: 15}
    if stage in (5, 6):
        result = _opcode15_result()
        result["resolved_decisions"] = copy.deepcopy(request["decisions"])
    else:
        opcode = prompt_ops[stage]
        prompt_id = 50 + stage
        if opcode == 13:
            event = _opcode13_event(prompt_id)
        elif opcode == 11:
            event = _singleton_idle_event(prompt_id, 7)
        else:
            # Stage 1 is tested by the full Rust oracle; this fixture only
            # needs the envelope shape for report/stage-schema coverage.
            event = {"sequence": prompt_id, "opcode": 18, "supported": True,
                     "raw": [18, 0, 1, 255, 255, 224, 255], "fields": {"prompt": {
                         "id": prompt_id, "opcode": 18, "player": 0, "actions": []}}}
        prompt = event["fields"]["prompt"]
        result = {"status": "decision_required", "error": None, "coverage_gaps": [],
                  "resolved_decisions": request["decisions"], "prompt": prompt, "events": [event]}
    return {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_stage",
        "scope": VALIDATION_SCOPE.scope,
        "context": "a" * 64,
        "stage": stage,
        "request": request,
        "successful": True,
        "diagnostic": None,
        "ledger": {"consumed": stage, "completed": stage, "unknown": 0,
                   "reserved": 0, "abandoned": 0, "limit": 6},
        "assets_unchanged": True,
        "assets_before": {"ordinary": "b" * 64},
        "assets_after": {"ordinary": "b" * 64},
        "window_valid_at_result": True,
        "validation": {"Ok": {"response_oracle_matches": True,
                               "automatic_decisions_single_legal": True}},
        "result": {"Ok": result},
        "independent_replay_matches": True if stage in (4, 6) else None,
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }


class TenkiPlacementValidationTests(unittest.TestCase):
    def _synthetic_repo(self):
        root = Path(__file__).resolve().parents[1] / "target" / ("tenki-validation-" + uuid.uuid4().hex)
        root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, root)
        return root

    def test_delivery_relative_path_resolves_from_delivery_directory_inside_baseline(self):
        baseline = Path.cwd() / "data/runtime/frozen-baseline"
        delivery = baseline / "final-build" / "delivery.json"
        self.assertEqual(
            _resolve_delivery_path(delivery, "../audit-report.json", baseline),
            baseline / "audit-report.json",
        )
        with self.assertRaisesRegex(ValueError, "validation_delivery_reference_outside_root"):
            _resolve_delivery_path(delivery, "../../outside.json", baseline)
        with self.assertRaisesRegex(ValueError, "validation_delivery_reference_absolute"):
            _resolve_delivery_path(delivery, "C:/outside.json", baseline)

    def test_new_scope_is_immutable_and_separate_from_sealed_confirmation(self):
        self.assertEqual(VALIDATION_SCOPE.scope, "tenki-placement-validation-v1")
        self.assertEqual(VALIDATION_SCOPE.limit, 6)
        self.assertEqual(VALIDATION_SCOPE.wall_seconds, 7200)
        self.assertNotEqual(VALIDATION_SCOPE.scope, CONFIRMATION_SCOPE)
        with self.assertRaises(FrozenInstanceError):
            VALIDATION_SCOPE.scope = CONFIRMATION_SCOPE

    def test_auto_decision_requires_the_raw_singleton_response_not_only_runner_flag(self):
        requested = [{"prompt_id": 10, "player": 0,
                      "choice": {"kind": "command", "command": 8, "index": 0}}]
        automatic = {"prompt_id": 22, "player": 0,
                     "choice": {"kind": "command", "command": 7, "index": 0}}
        accepted = validate_auto_decisions(requested, requested + [automatic],
                                           [_singleton_idle_event()])
        self.assertEqual(accepted, [automatic])

        raw = bytes([14, 0, 2]) + (101).to_bytes(8, "little") + (202).to_bytes(8, "little")
        prompt = {"id": 22, "opcode": 14, "player": 0, "actions": [
            {"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]},
            {"choice": {"kind": "option", "index": 1}, "bytes": [1, 0, 0, 0]},
        ]}
        multi = {"sequence": 22, "opcode": 14, "supported": True,
                 "raw": list(raw), "fields": {"prompt": prompt}}
        with self.assertRaisesRegex(ValueError, "automatic_prompt_not_single_action"):
            validate_auto_decisions(requested, requested + [
                {"prompt_id": 22, "player": 0,
                 "choice": {"kind": "option", "index": 0}}
            ], [multi])

    def test_auto_decision_rejects_missing_raw_event_and_response_byte_mismatch(self):
        decision = {"prompt_id": 22, "player": 0,
                    "choice": {"kind": "command", "command": 7, "index": 0}}
        with self.assertRaisesRegex(ValueError, "automatic_prompt_event_not_unique"):
            validate_auto_decisions([], [decision], [])
        forged = _singleton_idle_event()
        forged["fields"]["prompt"]["actions"][0]["bytes"] = [8, 0, 0, 0]
        with self.assertRaisesRegex(ValueError, "automatic_prompt_response_mismatch"):
            validate_auto_decisions([], [decision], [forged])

    def test_prompt_numeric_fields_reject_boolean_values(self):
        decision = {"prompt_id": True, "player": 0,
                    "choice": {"kind": "command", "command": 7, "index": 0}}
        with self.assertRaisesRegex(ValueError, "automatic_decision_shape_invalid"):
            validate_auto_decisions([], [decision], [_singleton_idle_event()])

        event = _singleton_idle_event(prompt_id=1)
        event["fields"]["prompt"]["player"] = True
        event["raw"][1] = 1
        with self.assertRaisesRegex(ValueError, "automatic_prompt_normalized_fields_mismatch"):
            validate_auto_decisions([], [{"prompt_id": 1, "player": 1,
                                          "choice": {"kind": "command", "command": 7, "index": 0}}],
                                    [event])

    def test_opcode18_oracle_accepts_permuted_menu_but_rejects_duplicate_coordinates(self):
        from ygo_eval.native_tenki_placement_validation import _event_prompt, _validate_place_prompt

        raw = bytes([18, 0, 1]) + (0xFFFFE0FF).to_bytes(4, "little")
        actions = []
        for sequence in (4, 1, 3, 0, 2):
            actions.append({
                "choice": {"kind": "place", "zones": [{"player": 0, "location": 8,
                                                             "sequence": sequence}]},
                "bytes": [0, 8, sequence],
            })
        prompt = {"id": 1, "opcode": 18, "player": 0, "actions": actions}
        _validate_place_prompt(prompt, raw)
        event = {"sequence": 1, "opcode": 18, "supported": True,
                 "raw": list(raw), "fields": {"prompt": prompt}}
        _event_prompt(event, 1)
        prompt["actions"][0] = prompt["actions"][1]
        with self.assertRaisesRegex(ValueError, "stage_opcode18_responses_mismatch"):
            _validate_place_prompt(prompt, raw)

    def test_child_request_inherits_authenticated_parent_automatic_tail(self):
        requested_auto = {"prompt_id": 21, "player": 0,
                          "choice": {"kind": "command", "command": 8, "index": 0}}
        automatic_tail = {"prompt_id": 22, "player": 0,
                          "choice": {"kind": "command", "command": 7, "index": 0}}
        pending = _opcode13_event(23)
        parent_result = {"status": "decision_required", "error": None,
                         "coverage_gaps": [],
                         "resolved_decisions": [requested_auto, automatic_tail],
                         "prompt": pending["fields"]["prompt"],
                         "events": [_singleton_idle_event(21, 8), _singleton_idle_event(), pending]}
        parent = _success_receipt(2, {"decisions": [requested_auto]})
        parent["result"] = {"Ok": parent_result}
        child = derive_stage_request(3, parent)
        self.assertEqual(child["decisions"], [
            requested_auto,
            automatic_tail,
            {"prompt_id": 23, "player": 0,
             "choice": {"kind": "yes_no", "yes": False}},
        ])
        self.assertEqual(parent["request"]["decisions"], [requested_auto])

    def test_replay_request_is_exact_copy_of_execution_request(self):
        request = {"decisions": [{"prompt_id": 5, "player": 0,
                                  "choice": {"kind": "yes_no", "yes": False}}],
                   "opaque": {"kept": [1, 2]}}
        parent = _success_receipt(3, request)
        self.assertEqual(derive_stage_request(4, parent), request)

    def test_true_branch_and_replay_derive_from_their_authenticated_parents(self):
        region = {"prompt_id": 61, "player": 0,
                  "choice": {"kind": "place", "zones": [
                      {"player": 0, "location": 8, "sequence": 0}]}}
        stage2 = _success_receipt(2, {"decisions": [region]})
        stage5_request = derive_stage_request(5, stage2)
        self.assertEqual(stage5_request["decisions"], [
            region,
            {"prompt_id": 52, "player": 0,
             "choice": {"kind": "yes_no", "yes": True}},
        ])
        stage5 = _success_receipt(5, stage5_request)
        self.assertEqual(derive_stage_request(6, stage5), stage5_request)

    def test_normal_mode_requires_saved_prepare_before_any_build_or_asset_work(self):
        from ygo_eval.native_tenki_placement_validation import (
            ScopeSpec, native_tenki_placement_validation,
        )

        repo = self._synthetic_repo()
        (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
        spec = ScopeSpec(
            scope="tenki-placement-validation-test-v1",
            output_root=Path("data/runtime/p1-tenki-runner-repair-offline-2026-10-23"),
            baseline_root=Path("baseline"),
            limit=6, wall_seconds=7200, old_consumed=26,
            batch_kind="tenki-placement-validation-v1",
            input_seal_kind="tenki_placement_validation_stage_input_seal",
            runner_role="tenki_placement_validation_runner",
            delivery_sha256="d" * 64,
        )
        root = repo / spec.output_root
        (root / "native-artifacts").mkdir(parents=True)
        research = root / "research"
        args = argparse.Namespace(
            baseline_dir=repo / spec.baseline_root,
            runner=root / "native-artifacts/tenki-placement-probe.exe",
            worker=root / "native-artifacts/ygo-engine-worker.exe",
            build_record=root / "build-record.json",
            identity=root / "identity.json",
            window_start=root / "window-start.json",
            output=research, prepare_only=False, verify_only=False,
        )
        with patch("ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                   return_value=({"audit": {}, "audit_sha256": "a" * 64}, {})), \
             patch("ygo_eval.native_tenki_placement_confirmation._verify_build_and_identity",
                   side_effect=AssertionError("build must not run")), \
             patch("ygo_eval.native_tenki_placement._capture_identity",
                   side_effect=AssertionError("asset scan must not run")):
            with self.assertRaisesRegex(ValueError, "validation_prepare_required_before_execution"):
                native_tenki_placement_validation(args, repo=repo, spec=spec)
        self.assertFalse(research.exists())
        self.assertFalse(args.window_start.exists())

    def test_stage_five_and_six_validate_duplicate_card_positions(self):
        for stage in (5, 6):
            with self.subTest(stage=stage):
                receipt = _success_receipt(stage)
                validate_stage_receipt(receipt, receipt["request"], "a" * 64,
                                       stage, {"ordinary": "b" * 64})
                receipt["result"]["Ok"]["events"][0]["fields"]["prompt"]["actions"].reverse()
                with self.assertRaises(ValueError):
                    validate_stage_receipt(receipt, receipt["request"], "a" * 64,
                                           stage, {"ordinary": "b" * 64})

    def test_summary_never_reports_success_for_partial_or_unknown_consumption(self):
        from ygo_eval.native_tenki_placement_validation import summarize_validation

        success = [
            {"stage": n, "successful": True, "native_calls": 1, "diagnostic": None,
             "receipt_sha256": f"{n:064x}",
             "diagnostic_sha256": "a" * 64,
             "independent_replay_matches": True if n in (4, 6) else None,
             "ledger": {"consumed": n, "completed": n, "unknown": 0,
                        "reserved": 0, "abandoned": 0, "limit": 6}}
            for n in range(1, 7)
        ]
        stats = {"consumed": 6, "completed": 6, "unknown": 0,
                 "reserved": 0, "abandoned": 0, "limit": 6}
        good = summarize_validation("a" * 64, success, stats)
        self.assertTrue(good["successful"])
        validate_report(good)
        self.assertFalse(summarize_validation("a" * 64, success[:5], stats)["successful"])
        unknown = dict(stats, unknown=1, completed=5)
        self.assertFalse(summarize_validation("a" * 64, success, unknown)["successful"])
        forged = copy.deepcopy(good)
        forged["stages"][2]["successful"] = False
        with self.assertRaisesRegex(ValueError, "validation_summary_success_not_proven"):
            validate_report(forged)
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-validation.schema.json")
                            .read_text(encoding="utf-8"))
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate(forged)
        Draft202012Validator(schema).validate(good)

    def test_summary_rejects_wrong_kind_unknown_fields_and_incoherent_counts(self):
        from ygo_eval.native_tenki_placement_validation import summarize_validation

        partial = summarize_validation("a" * 64, [], None, "ledger_statistics_unknown_or_invalid")
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-validation.schema.json")
                            .read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        validator.validate(partial)

        wrong_kind = copy.deepcopy(partial)
        wrong_kind["kind"] = "native_tenki_placement_validation_manifest"
        with self.assertRaises(ValueError):
            validate_report(wrong_kind)
        with self.assertRaises(Exception):
            validator.validate(wrong_kind)

        extra_field = copy.deepcopy(partial)
        extra_field["unreviewed"] = True
        with self.assertRaises(ValueError):
            validate_report(extra_field)
        with self.assertRaises(Exception):
            validator.validate(extra_field)

        forged_counts = copy.deepcopy(partial)
        forged_counts.update({"new_consumed": 2, "cumulative_consumed": 28,
                              "unknown": 0,
                              "ledger": {"consumed": 0, "completed": 0,
                                         "unknown": 0, "reserved": 0,
                                         "abandoned": 0, "limit": 6}})
        with self.assertRaises(ValueError):
            validate_report(forged_counts)
        with self.assertRaises(Exception):
            validator.validate(forged_counts)

    def test_failed_replay_stage_can_be_reported_without_claiming_a_match(self):
        from ygo_eval.native_tenki_placement_validation import _stage_report

        report = _stage_report("a" * 64, 4, None, Path("missing.json"),
                               "b" * 64, 1, "replay_mismatch")
        self.assertFalse(report["successful"])
        self.assertIsNone(report["independent_replay_matches"])
        validate_report(report)
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/native-tenki-placement-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(report)

    def test_verification_success_requires_six_verified_stages_and_full_ledger(self):
        from ygo_eval.native_tenki_placement_validation import _is_successful_stage_summary

        stages = [
            {"stage": n, "successful": True, "native_calls": 1,
             "diagnostic": None, "receipt_sha256": f"{n:064x}",
             "diagnostic_sha256": "a" * 64,
             "independent_replay_matches": True if n in (4, 6) else None,
             "ledger": {"consumed": n, "completed": n, "unknown": 0,
                        "reserved": 0, "abandoned": 0, "limit": 6}}
            for n in range(1, 7)
        ]
        valid = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_verification",
            "scope": VALIDATION_SCOPE.scope,
            "context": "a" * 64,
            "valid": True,
            "native_calls": 0,
            "old_consumed": 26,
            "new_consumed": 6,
            "cumulative_consumed": 32,
            "unknown": 0,
            "ledger": {"consumed": 6, "completed": 6, "unknown": 0,
                       "reserved": 0, "abandoned": 0, "limit": 6},
            "stages": stages,
            "prepared_sha256": "b" * 64,
            "verification_diagnostic_sha256": ["c" * 64] * 6,
            "diagnostic": None,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        self.assertTrue(validate_report(valid))
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(valid)

        for mutation in (
            lambda item: item.update(stages=[]),
            lambda item: item.update(new_consumed=None, cumulative_consumed=None,
                                     unknown=None, ledger=None),
            lambda item: item["stages"][3].update(independent_replay_matches=False),
            lambda item: item.update(diagnostic="incomplete"),
            lambda item: item.update(ledger={"consumed": 6, "completed": 5,
                                             "unknown": 1, "reserved": 0,
                                             "abandoned": 0, "limit": 6}),
        ):
            forged = copy.deepcopy(valid)
            mutation(forged)
            with self.assertRaises(ValueError):
                validate_report(forged)
            with self.assertRaises(Exception):
                Draft202012Validator(schema).validate(forged)

    def test_invalid_verification_reconciles_partial_stage_prefix_and_ledger(self):
        partial = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_verification",
            "scope": VALIDATION_SCOPE.scope,
            "context": "a" * 64,
            "valid": False,
            "native_calls": 0,
            "old_consumed": 26,
            "new_consumed": 2,
            "cumulative_consumed": 28,
            "unknown": 0,
            "ledger": {"consumed": 2, "completed": 2, "unknown": 0,
                       "reserved": 0, "abandoned": 0, "limit": 6},
            "stages": [
                {"stage": 1, "successful": True, "native_calls": 1,
                 "diagnostic": None, "receipt_sha256": "1" * 64,
                 "diagnostic_sha256": "a" * 64,
                 "independent_replay_matches": None,
                 "ledger": {"consumed": 1, "completed": 1, "unknown": 0,
                            "reserved": 0, "abandoned": 0, "limit": 6}},
                {"stage": 2, "successful": False, "native_calls": 1,
                 "diagnostic": "unexpected_prompt", "receipt_sha256": "2" * 64,
                 "diagnostic_sha256": "b" * 64,
                 "independent_replay_matches": None,
                 "ledger": {"consumed": 2, "completed": 2, "unknown": 0,
                            "reserved": 0, "abandoned": 0, "limit": 6}},
            ],
            "prepared_sha256": "c" * 64,
            "verification_diagnostic_sha256": ["d" * 64],
            "diagnostic": "saved_validation_incomplete_or_invalid",
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }
        self.assertTrue(validate_report(partial))
        forged = copy.deepcopy(partial)
        forged["new_consumed"] = 3
        forged["cumulative_consumed"] = 29
        with self.assertRaises(ValueError):
            validate_report(forged)
        forged = copy.deepcopy(partial)
        forged["stages"].reverse()
        with self.assertRaises(ValueError):
            validate_report(forged)

    def test_schema_and_python_validator_reject_forged_qualification(self):
        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-validation.schema.json")
                            .read_text(encoding="utf-8"))
        manifest_unsigned = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_manifest",
            "scope": VALIDATION_SCOPE.scope,
            "started_at": 1000,
            "limit": 6,
            "planned_calls": 6,
            "wall_seconds": 7200,
            "old_consumed": 26,
            "baseline_delivery_sha256": "84a3fc887e967f45c2c807d104450b41fbb31c038e93132b30b6bebadc669e22",
            "input_sha256": {role: "b" * 64 for role in MANIFEST_INPUT_ROLES},
            "source": {}, "build": {}, "assets": {},
            "stage1_request_sha256": digest(canonical({"decisions": []})),
            "request_derivation": "frozen-tenki-activation-only-worker-path-replaced",
            "request": {"decisions": []},
            "proof_ready": False, "complete_action_coverage": False,
            "global_optimality": False, "native_probability_verified": False,
        }
        manifest = {**manifest_unsigned, "context": digest(canonical(manifest_unsigned))}
        validate_report(manifest, repo)
        Draft202012Validator(schema).validate(manifest)
        receipt = _success_receipt(3)
        validate_report(receipt, repo)
        Draft202012Validator(schema).validate(receipt)
        stage_report = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_stage_report",
            "scope": VALIDATION_SCOPE.scope,
            "context": "a" * 64,
            "stage": 3,
            "successful": True,
            "native_calls": 1,
            "diagnostic": None,
            "receipt_sha256": "b" * 64,
            "diagnostic_sha256": "c" * 64,
            "independent_replay_matches": None,
            "ledger": {"consumed": 3, "completed": 3, "unknown": 0,
                       "reserved": 0, "abandoned": 0, "limit": 6},
            "proof_ready": False, "complete_action_coverage": False,
            "global_optimality": False, "native_probability_verified": False,
        }
        validate_report(stage_report, repo)
        Draft202012Validator(schema).validate(stage_report)
        forged = dict(manifest, proof_ready=True)
        with self.assertRaises(ValueError):
            validate_report(forged, repo)
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate(forged)

    def test_manifest_binds_request_digest_and_exact_fixed_input_roles(self):
        from ygo_eval.native_tenki_placement_validation import MANIFEST_INPUT_ROLES

        request = {"decisions": [], "protocol_version": 2, "seed": 1}
        unsigned = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_manifest",
            "scope": VALIDATION_SCOPE.scope,
            "started_at": 1000,
            "limit": 6,
            "planned_calls": 6,
            "wall_seconds": 7200,
            "old_consumed": 26,
            "baseline_delivery_sha256": VALIDATION_SCOPE.delivery_sha256,
            "input_sha256": {role: "b" * 64 for role in MANIFEST_INPUT_ROLES},
            "source": {"identity": "source"},
            "build": {},
            "assets": {},
            "request": request,
            "stage1_request_sha256": digest(canonical(request)),
            "request_derivation": "frozen-tenki-activation-only-worker-path-replaced",
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
        }

        def reseal(value):
            unsigned_value = {key: item for key, item in value.items() if key != "context"}
            value["context"] = digest(canonical(unsigned_value))
            return value

        valid = reseal(copy.deepcopy(unsigned))
        validate_report(valid)

        changed_request = copy.deepcopy(valid)
        changed_request["request"]["seed"] = 2
        reseal(changed_request)
        with self.assertRaisesRegex(ValueError, "validation_manifest_request_binding_invalid"):
            validate_report(changed_request)

        missing_request = copy.deepcopy(valid)
        del missing_request["request"]
        reseal(missing_request)
        with self.assertRaises(ValueError):
            validate_report(missing_request)

        missing_role = copy.deepcopy(valid)
        del missing_role["input_sha256"][MANIFEST_INPUT_ROLES[0]]
        reseal(missing_role)
        with self.assertRaisesRegex(ValueError, "validation_manifest_input_roles_invalid"):
            validate_report(missing_role)

        extra_role = copy.deepcopy(valid)
        extra_role["input_sha256"]["unreviewed"] = "c" * 64
        reseal(extra_role)
        with self.assertRaisesRegex(ValueError, "validation_manifest_input_roles_invalid"):
            validate_report(extra_role)

        repo = Path(__file__).resolve().parents[1]
        schema = json.loads((repo / "schemas/native-tenki-placement-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(valid)
        for forged in (missing_request, missing_role, extra_role):
            with self.assertRaises(Exception):
                Draft202012Validator(schema).validate(forged)

    def test_resume_rederives_stage1_from_frozen_prompts_without_scanning_live_assets(self):
        from ygo_eval.native_tenki_placement_validation import (
            _verify_frozen_stage1_request,
        )
        from ygo_data.identity import digest
        import json

        repo = self._synthetic_repo()
        banlist = repo / "data/runtime/banlist.json"
        banlist.parent.mkdir(parents=True)
        banlist.write_bytes(b'{"synthetic":true}')
        root = repo / VALIDATION_SCOPE.output_root
        worker = root / "native-artifacts" / "ygo-engine-worker.exe"
        prompt = {
            "opcode": 11, "player": 0, "id": 7,
            "actions": [{"choice": {"kind": "command", "command": 5, "index": 0},
                         "card_ids": [57103969], "bytes": [5, 0, 0, 0]}],
        }
        old_request = {"protocol_version": 2, "seed": 1, "probe_only": False,
                       "scenario": None, "interruption": None, "first_turn": None,
                       "research_capture": None,
                       "engine": {"worker_path": "old-worker.exe"}, "decisions": []}
        old_stage1 = {"request": old_request,
                      "result": {"Ok": {"status": "decision_required", "error": None,
                                         "prompt": prompt, "resolved_decisions": [],
                                         "events": [{"sequence": 7, "opcode": 11,
                                                     "supported": True,
                                                     "fields": {"prompt": prompt},
                                                     "raw": [11, 0] + [0] * 27}]}}}
        activation = {"kind": "command", "command": 5, "index": 0}
        old_stage2_request = copy.deepcopy(old_request)
        old_stage2_request["decisions"] = [{"prompt_id": 7, "player": 0, "choice": activation}]
        banlist_hash = digest((repo / "data/runtime/banlist.json").read_bytes())
        preparation = {"candidates": [{"case": {
            "case_id": "prompt-13-tenki-v1",
            "rules": {"banlist_sha256": banlist_hash},
        }}]}
        encoded = {
            "stage1": json.dumps(old_stage1, separators=(",", ":")).encode(),
            "stage2": json.dumps(old_stage2_request, separators=(",", ":")).encode(),
            "preparation": json.dumps(preparation, separators=(",", ":")).encode(),
        }
        hashes = {role: digest(raw) for role, raw in encoded.items()}
        prompt_root = repo / "data/runtime/p1-tenki-probe-native-2026-10-21"

        def pinned_read(path, expected=None):
            path = Path(path)
            if path == prompt_root / "research/stage-1.json":
                role = "stage1"
            elif path == prompt_root / "research/stage-2-request.json":
                role = "stage2"
            elif path == repo / "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json":
                role = "preparation"
            else:
                raise AssertionError(f"unexpected source read: {path}")
            if expected != hashes[role]:
                raise AssertionError("source must be pinned by its exact hash")
            return encoded[role], hashes[role]

        expected = copy.deepcopy(old_request)
        expected["decisions"] = copy.deepcopy(old_stage2_request["decisions"])
        expected["engine"]["worker_path"] = str(worker)
        manifest = {
            "request": copy.deepcopy(expected),
            "input_sha256": {
                "banlist": banlist_hash,
                "preparation": hashes["preparation"],
                "prompt_source_stage1": hashes["stage1"],
                "prompt_source_stage2_request": hashes["stage2"],
                "baseline_delivery": VALIDATION_SCOPE.delivery_sha256,
            },
        }
        with patch("ygo_eval.native_tenki_placement._read", side_effect=pinned_read), \
             patch("ygo_eval.native_tenki_placement.OLD_STAGE1_SHA256", hashes["stage1"]), \
             patch("ygo_eval.native_tenki_placement.OLD_STAGE2_REQUEST_SHA256", hashes["stage2"]), \
             patch("ygo_eval.native_tenki_placement.PREPARATION_SHA256", hashes["preparation"]), \
             patch("ygo_eval.research.validate_sources",
                   side_effect=AssertionError("verify-only must not scan live assets")), \
             patch("ygo_eval.native_tenki_placement_confirmation._candidate_request",
                   side_effect=AssertionError("verify-only must use pure prompt derivation")):
            _verify_frozen_stage1_request(repo, root, manifest, VALIDATION_SCOPE)

        forged = copy.deepcopy(manifest)
        forged["request"]["seed"] = 2
        with patch("ygo_eval.native_tenki_placement._read", side_effect=pinned_read), \
             patch("ygo_eval.native_tenki_placement.OLD_STAGE1_SHA256", hashes["stage1"]), \
             patch("ygo_eval.native_tenki_placement.OLD_STAGE2_REQUEST_SHA256", hashes["stage2"]), \
             patch("ygo_eval.native_tenki_placement.PREPARATION_SHA256", hashes["preparation"]), \
             patch("ygo_eval.research.validate_sources",
                   side_effect=AssertionError("verify-only must not scan live assets")):
            with self.assertRaisesRegex(ValueError, "validation_frozen_stage1_request_mismatch"):
                _verify_frozen_stage1_request(repo, root, forged, VALIDATION_SCOPE)

        forged_banlist = copy.deepcopy(manifest)
        forged_banlist["input_sha256"]["banlist"] = "f" * 64
        with patch("ygo_eval.native_tenki_placement._read", side_effect=pinned_read), \
             patch("ygo_eval.native_tenki_placement.OLD_STAGE1_SHA256", hashes["stage1"]), \
             patch("ygo_eval.native_tenki_placement.OLD_STAGE2_REQUEST_SHA256", hashes["stage2"]), \
             patch("ygo_eval.native_tenki_placement.PREPARATION_SHA256", hashes["preparation"]), \
             patch("ygo_eval.research.validate_sources",
                   side_effect=AssertionError("verify-only must not scan live assets")):
            with self.assertRaisesRegex(ValueError, "validation_frozen_banlist_source_mismatch"):
                _verify_frozen_stage1_request(repo, root, forged_banlist, VALIDATION_SCOPE)

    def test_timeout_uses_remaining_window_not_a_sixty_second_default(self):
        self.assertAlmostEqual(_normal_runner_timeout({"started_at": 1000}, now=1061.25),
                               7138.75)

    def test_over_limit_card_combinations_are_rejected_before_materializing(self):
        from ygo_eval.native_tenki_placement_validation import _enumerate_prompt_actions

        count = 30
        raw = (bytes([15, 0, 0]) + (15).to_bytes(4, "little")
               + (15).to_bytes(4, "little") + count.to_bytes(4, "little")
               + bytes(count * 14))
        with patch("ygo_eval.native_tenki_placement_validation.itertools.combinations",
                   side_effect=AssertionError("must preflight before enumeration")):
            with self.assertRaisesRegex(ValueError, "automatic_prompt_combination_limit"):
                _enumerate_prompt_actions(raw)

    def test_over_limit_zone_combinations_are_rejected_before_materializing(self):
        from ygo_eval.native_tenki_placement_validation import _enumerate_prompt_actions

        # With an empty mask the protocol exposes 30 zones; selecting 12 exceeds
        # the 4096-choice contract by a wide margin.
        raw = bytes([24, 0, 12]) + bytes(4)
        with patch("ygo_eval.native_tenki_placement_validation.itertools.combinations",
                   side_effect=AssertionError("must preflight before enumeration")):
            with self.assertRaisesRegex(ValueError, "automatic_prompt_combination_limit"):
                _enumerate_prompt_actions(raw)


if __name__ == "__main__":
    unittest.main()
