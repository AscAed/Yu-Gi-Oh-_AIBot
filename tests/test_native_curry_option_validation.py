import copy
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid
from dataclasses import replace
from unittest.mock import patch

import ygo_eval.native_curry_option_validation as curry_module

from jsonschema import Draft202012Validator
from ygo_data.identity import canonical
from ygo_eval.native_curry_option_validation import (
    BASELINE_ACCEPTANCE_SHA256,
    BASELINE_DELIVERY_SHA256,
    CURRY_SCOPE,
    HISTORICAL_SOURCE_TRANSITION,
    MANIFEST_INPUT_ROLES,
    PINNED_INPUT_SHA256,
    _stage_report,
    derive_curry_stage1_request,
    derive_curry_stage_request,
    run_curry_stages,
    summarize_curry_validation,
    validate_curry_report,
    validate_curry_stage_receipt,
    _verify_curry_basic_receipt,
    verify_curry_only,
)
from ygo_eval.native_tenki_placement_validation import _save_stage_files


_TEST_TMP_BASE = (
    Path(__file__).resolve().parents[1]
    / "target/curry-option-validation-tests/python-synthetic"
)


class _TemporaryDirectory:
    def __enter__(self) -> str:
        _TEST_TMP_BASE.mkdir(parents=True, exist_ok=True)
        self.path = _TEST_TMP_BASE / f"run-{uuid.uuid4().hex}"
        self.path.mkdir(exist_ok=False)
        return str(self.path)

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self.path.parent != _TEST_TMP_BASE:
            raise AssertionError("synthetic test cleanup escaped its fixed temp base")
        shutil.rmtree(self.path)


OPTION_DESCRIPTIONS = (60_895_602_409_472, 60_895_602_409_473)
CURRY_FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
IDENTITY = {"ordinary": "b" * 64}


def _event(sequence, raw, prompt=None, fields=None):
    body = {"sequence": sequence, "opcode": raw[0], "supported": True,
            "raw": list(raw)}
    event_fields = dict(fields or {})
    if prompt is not None:
        event_fields["prompt"] = prompt
    body["fields"] = event_fields
    return body


def _idle_event(sequence=10, *, candidate_count=1, shuffle=False):
    # Opcode 11 with exactly one Curry activation at command 5 / index 0.
    raw = bytearray((11, 0))
    for command in range(6):
        count = candidate_count if command == 5 else 0
        raw.extend(count.to_bytes(4, "little"))
        for index in range(count):
            raw.extend((58_074_572).to_bytes(4, "little"))
            raw.extend((0, 1))
            raw.extend(index.to_bytes(4, "little"))
            raw.extend((60_895_602_409_472).to_bytes(8, "little"))
            raw.append(0)
    raw.extend((0, 0, int(shuffle)))
    actions = []
    for index in range(candidate_count):
        actions.append({"choice": {"kind": "command", "command": 5, "index": index},
                        "card_ids": [58_074_572],
                        "bytes": [5, 0, index & 0xFF, (index >> 8) & 0xFF]})
    if shuffle:
        actions.append({"choice": {"kind": "command", "command": 8, "index": 0},
                        "bytes": [8, 0, 0, 0]})
    prompt = {"id": sequence, "opcode": 11, "player": 0, "actions": actions}
    return _event(sequence, raw, prompt)


def _place_event(sequence=11):
    raw = bytes((18, 0, 1)) + (0xFFFFE0FF).to_bytes(4, "little")
    actions = []
    for index in range(5):
        actions.append({
            "choice": {"kind": "place", "zones": [{"player": 0, "location": 8,
                                                          "sequence": index}]},
            "bytes": [0, 8, index],
        })
    return _event(sequence, raw, {"id": sequence, "opcode": 18, "player": 0,
                                  "actions": actions})


def _option_event(sequence=12):
    raw = bytes((14, 0, 2)) + b"".join(value.to_bytes(8, "little")
                                         for value in OPTION_DESCRIPTIONS)
    return _event(sequence, raw, {"id": sequence, "opcode": 14, "player": 0,
                                  "actions": [
                                      {"choice": {"kind": "option", "index": 0},
                                       "bytes": [0, 0, 0, 0]},
                                      {"choice": {"kind": "option", "index": 1},
                                       "bytes": [1, 0, 0, 0]},
                                  ]})


def _recover_event(sequence=13, player=0):
    raw = bytes((92, player)) + (200).to_bytes(4, "little")
    return _event(sequence, raw, fields={"player": player, "amount": 200})


def _chain_event(sequence=14):
    # Empty, non-forced MSG_SELECT_CHAIN.
    prompt = {
        "id": sequence,
        "opcode": 16,
        "player": 1,
        "actions": [{
            "choice": {"kind": "chain", "index": None},
            "bytes": [255, 255, 255, 255],
        }],
    }
    return _event(sequence, bytes((16, 1, 0, 0)) + bytes(8) + bytes(4), prompt)


def _decision(prompt_id, choice):
    return {"prompt_id": prompt_id, "player": 0, "choice": choice}


def _resolution_events(selected, *, idle_sequence=15):
    return [_idle_event(), _place_event(), _option_event(),
            _recover_event(13, selected), _chain_event(),
            _idle_event(idle_sequence, candidate_count=0, shuffle=True)]


def _receipt(stage, request=None, *, events=None, pending=None, lp=None,
             resolved=None, successful=True):
    request = request or {"decisions": []}
    if events is None:
        if stage == 1:
            events = [_idle_event()]
            pending = events[-1]["fields"]["prompt"]
        elif stage == 2:
            events = [_place_event()]
            pending = events[-1]["fields"]["prompt"]
        elif stage == 3:
            events = [_option_event()]
            pending = events[-1]["fields"]["prompt"]
        else:
            selected = request["decisions"][-1]["choice"]["index"]
            idle = _idle_event(15, candidate_count=0, shuffle=True)
            events = _resolution_events(selected)
            pending = idle["fields"]["prompt"]
            lp = [8200, 8000] if selected == 0 else [8000, 8200]
    if resolved is None:
        resolved = copy.deepcopy(request["decisions"])
    else:
        resolved = copy.deepcopy(resolved)
    steps = []
    for event in events:
        raw = bytes(event.get("raw", []))
        if not raw or raw[0] not in (11, 12, 13, 14, 15, 16, 18, 19, 24, 26):
            continue
        prompt = event.get("fields", {}).get("prompt", {})
        if pending is not None and prompt.get("id") == pending.get("id"):
            break
        if prompt.get("player") == 1:
            choice = {"kind": "chain", "index": None}
        else:
            decision = next(item for item in resolved
                            if item["prompt_id"] == event["sequence"])
            choice = decision["choice"]
        action = next(item for item in prompt.get("actions", [])
                      if item.get("choice") == choice)
        steps.append(copy.deepcopy(action))
    return {
        "schema_version": 1,
        "kind": "native_curry_option_validation_stage",
        "scope": CURRY_SCOPE.scope,
        "context": "a" * 64,
        "stage": stage,
        "request": copy.deepcopy(request),
        "successful": successful,
        "diagnostic": None if successful else "synthetic_failure",
        "ledger": {"consumed": stage, "completed": stage, "unknown": 0,
                   "reserved": 0, "abandoned": 0, "limit": 7},
        "assets_unchanged": True,
        "assets_before": IDENTITY,
        "assets_after": IDENTITY,
        "window_valid_at_result": True,
        "validation": {"Ok": {"response_oracle_matches": True,
                               "automatic_decisions_single_legal": True}},
        "result": {"Ok": {"status": "decision_required", "error": None,
                            "coverage_gaps": [], "resolved_decisions": resolved,
                            "steps": steps, "prompt": pending, "events": events,
                            "checkpoint": {"lp": lp} if lp is not None else {}}},
        "independent_replay_matches": True if stage in (5, 7) else None,
        **CURRY_FLAGS,
    }


class CurryStagePolicyTests(unittest.TestCase):
    def test_scope_is_independent_fixed_seven_request_budget(self):
        self.assertEqual(CURRY_SCOPE.scope, "curry-option-validation-v1")
        self.assertEqual(CURRY_SCOPE.limit, 7)
        self.assertEqual(CURRY_SCOPE.wall_seconds, 7200)
        self.assertEqual(CURRY_SCOPE.old_consumed, 32)

    def test_stage1_request_replaces_only_the_fixed_rabbit_card_and_clears_decisions(self):
        rabbit_main = [85_138_716, 2, 3, 4]
        rabbit_case = {
            "case_id": "rabbit",
            "deck": {"main": rabbit_main, "extra": [9, 10, 11], "side": []},
            "opening_hand": [85_138_716, 2, 3, 4, 5],
            "seed": 1,
            "rules": {"version": "2026-10-01", "region": "OCG"},
            "information": {"opponent_resources": {
                "main": list(rabbit_main), "hand": [],
            }},
        }
        curry_case = copy.deepcopy(rabbit_case)
        curry_case["case_id"] = "prompt-14-curry-v1"
        curry_case["deck"]["main"][0] = 58_074_572
        curry_case["opening_hand"][0] = 58_074_572
        curry_case["information"]["opponent_resources"]["main"][0] = 58_074_572
        base_request = {
            "protocol_version": 2,
            "engine": {"worker_path": "old-worker.exe", "timeout_ms": 30_000,
                       "catalog_path": "cards.cdb"},
            "deck": copy.deepcopy(rabbit_case["deck"]),
            "opening_hand": list(rabbit_case["opening_hand"]),
            "seed": 1,
            "decisions": [{"prompt_id": 7, "player": 0,
                           "choice": {"kind": "command", "command": 0, "index": 0}}],
            "versions": {"rules": "ocg-mr5", "catalog": "", "banlist": ""},
            "probe_only": False,
        }

        request = derive_curry_stage1_request(
            base_request, rabbit_case, curry_case, "candidate-worker.exe"
        )

        expected = copy.deepcopy(base_request)
        expected["deck"] = copy.deepcopy(curry_case["deck"])
        expected["opening_hand"] = list(curry_case["opening_hand"])
        expected["decisions"] = []
        expected["engine"]["worker_path"] = "candidate-worker.exe"
        self.assertEqual(request, expected)

    def test_stage1_request_rejects_ambiguous_card_replacement_or_case_drift(self):
        rabbit_main = [85_138_716, 2, 3]
        rabbit_case = {
            "case_id": "rabbit",
            "deck": {"main": rabbit_main, "extra": [9, 10, 11], "side": []},
            "opening_hand": [85_138_716, 2, 3, 4, 5],
            "seed": 1,
            "rules": {"version": "2026-10-01", "region": "OCG"},
            "information": {"opponent_resources": {"main": list(rabbit_main), "hand": []}},
        }
        curry_case = copy.deepcopy(rabbit_case)
        curry_case.update(case_id="prompt-14-curry-v1")
        curry_case["deck"]["main"][0] = 58_074_572
        curry_case["opening_hand"][0] = 58_074_572
        curry_case["information"]["opponent_resources"]["main"][0] = 58_074_572
        base_request = {
            "protocol_version": 2,
            "engine": {"worker_path": "old-worker.exe"},
            "deck": copy.deepcopy(rabbit_case["deck"]),
            "opening_hand": list(rabbit_case["opening_hand"]),
            "seed": 1,
            "decisions": [],
            "versions": {},
        }
        duplicate = copy.deepcopy(base_request)
        duplicate["deck"]["main"].append(85_138_716)
        with self.assertRaisesRegex(ValueError, "curry_base_request_deck_binding_invalid"):
            derive_curry_stage1_request(duplicate, rabbit_case, curry_case,
                                        "candidate-worker.exe")
        drifted_case = copy.deepcopy(curry_case)
        drifted_case["deck"]["main"][1] = 44
        with self.assertRaisesRegex(ValueError, "curry_candidate_case_not_rabbit_derivation"):
            derive_curry_stage1_request(base_request, rabbit_case, drifted_case,
                                        "candidate-worker.exe")

    def test_fixed_parent_chain_derives_both_option_branches_and_replays(self):
        activation = _decision(10, {"kind": "command", "command": 5, "index": 0})
        stage1 = _receipt(1, {"decisions": []}, resolved=[])
        stage2_request = derive_curry_stage_request(2, stage1)
        self.assertEqual(stage2_request["decisions"], [activation])

        region = _decision(11, {"kind": "place", "zones": [
            {"player": 0, "location": 8, "sequence": 0}]})
        stage2 = _receipt(2, stage2_request, events=[_idle_event(), _place_event()],
                          pending=_place_event()["fields"]["prompt"],
                          resolved=[activation])
        stage3_request = derive_curry_stage_request(3, stage2)
        self.assertEqual(stage3_request["decisions"], [activation, region])

        stage3 = _receipt(3, stage3_request,
                          events=[_idle_event(), _place_event(), _option_event()],
                          pending=_option_event()["fields"]["prompt"],
                          resolved=[activation, region])
        zero_request = derive_curry_stage_request(4, stage3)
        one_request = derive_curry_stage_request(6, stage3)
        self.assertEqual(zero_request["decisions"][-1], _decision(
            12, {"kind": "option", "index": 0}))
        self.assertEqual(one_request["decisions"][-1], _decision(
            12, {"kind": "option", "index": 1}))

        stage4 = _receipt(4, zero_request)
        stage6 = _receipt(6, one_request)
        self.assertEqual(derive_curry_stage_request(5, stage4), zero_request)
        self.assertEqual(derive_curry_stage_request(7, stage6), one_request)

    def test_activation_must_be_unique_and_bind_card_id_and_response(self):
        stage1 = _receipt(1)
        action = stage1["result"]["Ok"]["prompt"]["actions"][0]
        action["card_ids"] = [85138716]
        with self.assertRaisesRegex(ValueError, "curry_idle_command5_action_mismatch"):
            derive_curry_stage_request(2, stage1)

        stage1 = _receipt(1, events=[_idle_event(candidate_count=2)],
                          pending=_idle_event(candidate_count=2)["fields"]["prompt"])
        with self.assertRaisesRegex(ValueError, "curry_activation_card_not_unique"):
            derive_curry_stage_request(2, stage1)

    def test_stage_receipt_binds_recover_player_and_life_point_outcome(self):
        activation = _decision(10, {"kind": "command", "command": 5, "index": 0})
        region = _decision(11, {"kind": "place", "zones": [
            {"player": 0, "location": 8, "sequence": 0}]})
        option = _decision(12, {"kind": "option", "index": 0})
        request = {"decisions": [activation, region, option]}
        receipt = _receipt(
            4, request,
            events=_resolution_events(0),
            pending=_idle_event(15, candidate_count=0, shuffle=True)["fields"]["prompt"],
            lp=[8200, 8000],
        )
        validate_curry_stage_receipt(receipt, request, "a" * 64, 4, IDENTITY)
        receipt["result"]["Ok"]["events"][1] = _recover_event(player=1)
        with self.assertRaises(ValueError):
            validate_curry_stage_receipt(receipt, request, "a" * 64, 4, IDENTITY)

    def test_protocol2_empty_opponent_chain_is_bound_through_ordered_steps_only(self):
        activation = _decision(10, {"kind": "command", "command": 5, "index": 0})
        region = _decision(11, {"kind": "place", "zones": [
            {"player": 0, "location": 8, "sequence": 0}]})
        option = _decision(12, {"kind": "option", "index": 0})
        request = {"protocol_version": 2,
                   "decisions": [activation, region, option]}
        receipt = _receipt(4, request)
        result = receipt["result"]["Ok"]
        self.assertEqual(result["resolved_decisions"], request["decisions"])
        self.assertNotIn(14, [decision["prompt_id"]
                              for decision in result["resolved_decisions"]])
        self.assertEqual(len(result["steps"]), 4)
        self.assertEqual(result["steps"][3]["choice"],
                         {"kind": "chain", "index": None})
        validate_curry_stage_receipt(receipt, request, "a" * 64, 4, IDENTITY)

        result["steps"][3]["bytes"] = [0, 0, 0, 0]
        with self.assertRaises(ValueError):
            validate_curry_stage_receipt(receipt, request, "a" * 64, 4, IDENTITY)

        receipt = _receipt(4, request)
        receipt["result"]["Ok"]["resolved_decisions"].append({
            "prompt_id": 14, "player": 1,
            "choice": {"kind": "chain", "index": None},
        })
        with self.assertRaises(ValueError):
            validate_curry_stage_receipt(receipt, request, "a" * 64, 4, IDENTITY)

    def test_stage_receipt_rejects_an_extra_supported_prompt_outside_the_decision_trace(self):
        receipt = _receipt(1)
        result = receipt["result"]["Ok"]
        extra = _option_event(sequence=9)
        result["events"].insert(0, extra)
        with self.assertRaises(ValueError):
            validate_curry_stage_receipt(
                receipt, receipt["request"], "a" * 64, 1, IDENTITY
            )

    def test_summary_requires_all_seven_slots_and_clean_consumption(self):
        stages = [
            {"stage": index, "successful": True, "native_calls": 1,
             "diagnostic": None, "receipt_sha256": f"{index:064x}",
             "diagnostic_sha256": "b" * 64,
             "independent_replay_matches": True if index in (5, 7) else None,
             "ledger": {"consumed": index, "completed": index, "unknown": 0,
                        "reserved": 0, "abandoned": 0, "limit": 7}}
            for index in range(1, 8)
        ]
        stats = {"consumed": 7, "completed": 7, "unknown": 0,
                 "reserved": 0, "abandoned": 0, "limit": 7}
        complete = summarize_curry_validation("a" * 64, stages, stats)
        self.assertTrue(complete["successful"])
        self.assertEqual(complete["cumulative_consumed"], 39)
        validate_curry_report(complete)

        partial = summarize_curry_validation("a" * 64, stages[:-1], stats)
        self.assertFalse(partial["successful"])
        validate_curry_report(partial)

        unknown = dict(stats, consumed=7, completed=6, unknown=1)
        self.assertFalse(summarize_curry_validation("a" * 64, stages, unknown)["successful"])

    def test_successful_new_scope_summary_recomputes_with_its_own_scope(self):
        confirmation = replace(
            CURRY_SCOPE,
            scope="curry-option-confirmation-v1",
            output_root=Path("data/runtime/p1-curry-option-confirmation-native-2026-10-24"),
            baseline_root=Path("data/runtime/p1-curry-asset-binding-offline-2026-10-24"),
            batch_kind="curry-option-confirmation-v1",
            input_seal_kind="curry_option_confirmation_stage_input_seal",
            runner_role="curry_option_confirmation_runner",
            delivery_acceptance_sha256="f" * 64,
            delivery_sha256="e" * 64,
        )
        stages = [
            {"stage": index, "successful": True, "native_calls": 1,
             "diagnostic": None, "receipt_sha256": f"{index:064x}",
             "diagnostic_sha256": "b" * 64,
             "independent_replay_matches": True if index in (5, 7) else None,
             "ledger": {"consumed": index, "completed": index, "unknown": 0,
                        "reserved": 0, "abandoned": 0, "limit": 7}}
            for index in range(1, 8)
        ]
        stats = {"consumed": 7, "completed": 7, "unknown": 0,
                 "reserved": 0, "abandoned": 0, "limit": 7}
        summary = summarize_curry_validation("a" * 64, stages, stats, spec=confirmation)
        self.assertTrue(summary["successful"])
        self.assertEqual(summary["scope"], confirmation.scope)
        validate_curry_report(summary, spec=confirmation)

    def test_failed_summary_still_binds_known_consumption_and_unknown(self):
        stages = []
        ledger = {"consumed": 2, "completed": 1, "unknown": 1,
                  "reserved": 0, "abandoned": 0, "limit": 7}
        report = summarize_curry_validation("a" * 64, stages, ledger,
                                             "synthetic_partial_run")
        self.assertFalse(report["successful"])
        self.assertEqual((report["new_consumed"], report["cumulative_consumed"],
                          report["unknown"]), (2, 34, 1))
        validate_curry_report(report)
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/native-curry-option-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(report)
        forged = copy.deepcopy(report)
        forged["new_consumed"] = 1
        with self.assertRaises(ValueError):
            validate_curry_report(forged)
        self.assertFalse(Draft202012Validator(schema).is_valid(forged))

        unknown = summarize_curry_validation(
            "a" * 64,
            [],
            {"consumed": 2, "completed": 1, "unknown": 0,
             "reserved": 0, "abandoned": 0, "limit": 7},
            "synthetic_invalid_stats",
        )
        self.assertIsNone(unknown["ledger"])
        self.assertIsNone(unknown["new_consumed"])
        validate_curry_report(unknown)

    def test_report_rejects_forged_success_or_qualification(self):
        report = summarize_curry_validation("a" * 64, [], None,
                                             "ledger_statistics_unknown_or_invalid")
        validate_curry_report(report)
        forged = copy.deepcopy(report)
        forged["proof_ready"] = True
        with self.assertRaises(ValueError):
            validate_curry_report(forged)

    def test_manifest_matches_fixed_schema_and_binds_the_empty_stage1_request(self):
        request = {
            "protocol_version": 2, "seed": 1, "decisions": [],
            "engine": {"worker_path": "candidate-worker.exe"},
        }
        hashes = {
            role: PINNED_INPUT_SHA256.get(role, "c" * 64)
            for role in MANIFEST_INPUT_ROLES
        }
        hashes["baseline_delivery"] = BASELINE_DELIVERY_SHA256
        manifest = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_manifest",
            "scope": CURRY_SCOPE.scope,
            "batch_kind": CURRY_SCOPE.batch_kind,
            "context": "0" * 64,
            "started_at": 1,
            "limit": 7,
            "planned_calls": 7,
            "wall_seconds": 7200,
            "old_consumed": 32,
            "baseline_acceptance_sha256": BASELINE_ACCEPTANCE_SHA256,
            "baseline_delivery_sha256": BASELINE_DELIVERY_SHA256,
            "input_sha256": hashes,
            "source": {"identity": "synthetic"},
            "historical_source_transition": copy.deepcopy(HISTORICAL_SOURCE_TRANSITION),
            "build": {"runner": "synthetic"},
            "assets": {"ordinary": "synthetic"},
            "stage1_request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
            "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
            "request": request,
            **CURRY_FLAGS,
        }
        unsigned = {key: value for key, value in manifest.items() if key != "context"}
        manifest["context"] = hashlib.sha256(canonical(unsigned)).hexdigest()

        validate_curry_report(manifest)
        missing_batch_kind = copy.deepcopy(manifest)
        missing_batch_kind.pop("batch_kind")
        missing_batch_unsigned = {
            key: value for key, value in missing_batch_kind.items() if key != "context"
        }
        missing_batch_kind["context"] = hashlib.sha256(
            canonical(missing_batch_unsigned)
        ).hexdigest()
        with self.assertRaises(ValueError):
            validate_curry_report(missing_batch_kind)
        forged_transition = copy.deepcopy(manifest)
        forged_transition["historical_source_transition"]["current_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_curry_report(forged_transition)
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/native-curry-option-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(manifest)

    def test_validation_manifest_source_description_does_not_add_non_manifest_audit_role(self):
        from ygo_eval.curry_input_recovery_audit import (
            _PinnedFile, _SourceDescription,
        )

        semantic = {
            "manifest_base_request": "a" * 64,
            "manifest_candidate_case": "b" * 64,
        }
        files = [
            _PinnedFile(f"manifest_input_{role}", f"synthetic/{role}.json", "c" * 64)
            for role in MANIFEST_INPUT_ROLES
            if role not in {"base_request", "candidate_case"}
        ]
        files.extend((
            _PinnedFile("baseline_acceptance", "synthetic/acceptance.json",
                        BASELINE_ACCEPTANCE_SHA256),
            _PinnedFile("baseline_delivery", "synthetic/delivery.json",
                        BASELINE_DELIVERY_SHA256),
            _PinnedFile("baseline_audit", "synthetic/audit.json", "d" * 64),
        ))
        candidate = _SourceDescription(
            role="validation_candidate_scope",
            files=tuple(files),
            semantic_hashes=tuple(semantic.items()),
        )
        sources = _SourceDescription(role="root", children=(candidate,))

        request = {
            "protocol_version": 2, "seed": 1, "decisions": [],
            "engine": {"worker_path": "candidate-worker.exe"},
        }
        hashes = {
            role: semantic[f"manifest_{role}"]
            if role in {"base_request", "candidate_case"}
            else (BASELINE_DELIVERY_SHA256 if role == "baseline_delivery" else "c" * 64)
            for role in MANIFEST_INPUT_ROLES
        }
        manifest = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_manifest",
            "scope": CURRY_SCOPE.scope,
            "batch_kind": CURRY_SCOPE.batch_kind,
            "context": "0" * 64,
            "started_at": 1,
            "limit": 7,
            "planned_calls": 7,
            "wall_seconds": 7200,
            "old_consumed": 32,
            "baseline_acceptance_sha256": BASELINE_ACCEPTANCE_SHA256,
            "baseline_delivery_sha256": BASELINE_DELIVERY_SHA256,
            "input_sha256": hashes,
            "source": {"identity": "synthetic"},
            "historical_source_transition": copy.deepcopy(HISTORICAL_SOURCE_TRANSITION),
            "build": {"runner": "synthetic"},
            "assets": {"ordinary": "synthetic"},
            "stage1_request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
            "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
            "request": request,
            **CURRY_FLAGS,
        }
        unsigned = {key: item for key, item in manifest.items() if key != "context"}
        manifest["context"] = hashlib.sha256(canonical(unsigned)).hexdigest()

        validate_curry_report(manifest, spec=CURRY_SCOPE, _sources=sources)

    def test_prepared_and_stage_report_use_published_kind_names_and_fields(self):
        prepared = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_prepared",
            "scope": CURRY_SCOPE.scope,
            "context": "a" * 64,
            "prepared": True,
            "execution_ready": True,
            "native_calls": 0,
            "planned_calls": 7,
            "stage1_request_sha256": "b" * 64,
            "preflight_diagnostic_sha256": "c" * 64,
            "manifest_sha256": "d" * 64,
            "stage1_input_sha256": "e" * 64,
            "diagnostics": [],
            **CURRY_FLAGS,
        }
        report = _stage_report(
            "a" * 64, 1, None, Path("not-written-receipt.json"),
            "f" * 64, 0, "synthetic_stage_failure",
            {"consumed": 0, "completed": 0, "unknown": 0, "reserved": 0,
             "abandoned": 0, "limit": 7},
        )
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/native-curry-option-validation.schema.json")
                            .read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        validate_curry_report(prepared)
        validate_curry_report(report)
        validator.validate(prepared)
        validator.validate(report)


class CurryReplayReportTests(unittest.TestCase):
    def test_failed_receipt_accepts_missing_after_scan_but_success_does_not(self):
        receipt = _receipt(1)
        receipt["successful"] = False
        receipt["assets_unchanged"] = False
        receipt["assets_after"] = None
        _verify_curry_basic_receipt(
            receipt, receipt["request"], "a" * 64, 1, CURRY_SCOPE
        )
        validate_curry_report(receipt)
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/native-curry-option-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(receipt)

        receipt["successful"] = True
        with self.assertRaises(ValueError):
            _verify_curry_basic_receipt(
                receipt, receipt["request"], "a" * 64, 1, CURRY_SCOPE
            )
        self.assertFalse(Draft202012Validator(schema).is_valid(receipt))

    def test_failed_replay_stage_can_retain_the_replay_comparison_result(self):
        """A later gate can fail after a real replay comparison was recorded."""
        with _TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "stage-5.json"
            receipt_path.write_text('{"independent_replay_matches":true}',
                                    encoding="utf-8")
            receipt = {
                "successful": True,
                "independent_replay_matches": True,
                "ledger": {"consumed": 5, "completed": 5, "unknown": 0,
                           "reserved": 0, "abandoned": 0, "limit": 7},
            }
            failed = _stage_report(
                "a" * 64, 5, receipt, receipt_path, "f" * 64, 1,
                "asset_identity_changed",
            )
            self.assertFalse(failed["successful"])
            self.assertTrue(failed["independent_replay_matches"])
            validate_curry_report(failed)

            failed["independent_replay_matches"] = False
            validate_curry_report(failed)

            receipt["independent_replay_matches"] = False
            with self.assertRaises(ValueError):
                _stage_report(
                    "a" * 64, 5, receipt, receipt_path, "f" * 64, 1, None,
                )


class CurryVerifyOnlyTests(unittest.TestCase):
    def test_failure_verification_binds_ledger_totals_and_verified_stage_hashes(self):
        stats = {"consumed": 1, "completed": 0, "unknown": 1,
                 "reserved": 0, "abandoned": 0, "limit": 7}
        stage = {
            "stage": 1, "successful": False, "native_calls": 1,
            "diagnostic": "synthetic_failure", "receipt_sha256": "a" * 64,
            "diagnostic_sha256": "b" * 64,
            "independent_replay_matches": None, "ledger": stats,
        }
        report = {
            "schema_version": 1,
            "kind": "native_curry_option_validation_verification",
            "scope": CURRY_SCOPE.scope,
            "context": "c" * 64,
            "valid": False,
            "native_calls": 0,
            "old_consumed": 32,
            "new_consumed": 1,
            "cumulative_consumed": 33,
            "unknown": 1,
            "ledger": stats,
            "stages": [stage],
            "prepared_sha256": "d" * 64,
            "verification_diagnostic_sha256": ["e" * 64],
            "diagnostic": "saved_stage_unsuccessful",
            **CURRY_FLAGS,
        }
        validate_curry_report(report)
        schema = json.loads((Path(__file__).resolve().parents[1]
                             / "schemas/native-curry-option-validation.schema.json")
                            .read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(report)

        for key, value in (("new_consumed", 0), ("cumulative_consumed", 32),
                           ("unknown", 0), ("verification_diagnostic_sha256", []),
                           ("prepared_sha256", "not-a-sha256"),
                           ("diagnostic", None)):
            forged = copy.deepcopy(report)
            forged[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_curry_report(forged)
                self.assertFalse(Draft202012Validator(schema).is_valid(forged))

    def test_verify_only_checks_all_saved_stages_without_a_normal_execution_callback(self):
        from unittest.mock import patch
        from ygo_eval import native_tenki_placement_validation as tenki_module

        with _TemporaryDirectory() as temporary:
            root = Path(temporary) / "experiment"
            output = root / "research"
            repo = Path(temporary) / "repo"
            output.mkdir(parents=True)
            repo.mkdir()
            context = "a" * 64
            manifest = {
                "context": context,
                "scope": CURRY_SCOPE.scope,
                "started_at": 1_000,
                "request": {"decisions": []},
                "assets": {"ordinary": copy.deepcopy(IDENTITY)},
            }
            receipts: dict[int, dict] = {}
            requests: dict[int, dict] = {1: manifest["request"]}
            receipts[1] = _receipt(1, requests[1])
            activation = _decision(10, {"kind": "command", "command": 5, "index": 0})
            requests[2] = derive_curry_stage_request(2, receipts[1])
            receipts[2] = _receipt(
                2, requests[2], events=[_idle_event(), _place_event()],
                pending=_place_event()["fields"]["prompt"],
                resolved=[activation],
            )
            region = _decision(11, {"kind": "place", "zones": [
                {"player": 0, "location": 8, "sequence": 0},
            ]})
            requests[3] = derive_curry_stage_request(3, receipts[2])
            receipts[3] = _receipt(
                3, requests[3],
                events=[_idle_event(), _place_event(), _option_event()],
                pending=_option_event()["fields"]["prompt"],
                resolved=[activation, region],
            )
            requests[4] = derive_curry_stage_request(4, receipts[3])
            receipts[4] = _receipt(4, requests[4])
            requests[5] = derive_curry_stage_request(5, receipts[4])
            receipts[5] = _receipt(5, requests[5])
            requests[6] = derive_curry_stage_request(6, receipts[3])
            receipts[6] = _receipt(6, requests[6])
            requests[7] = derive_curry_stage_request(7, receipts[6])
            receipts[7] = _receipt(7, requests[7])

            for stage in range(1, 8):
                request = requests[stage]
                receipt = receipts[stage]
                _save_stage_files(output, context, stage, request, IDENTITY,
                                  manifest["started_at"], CURRY_SCOPE)
                receipt_path = output / f"stage-{stage}.json"
                receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
                sidecar = root / f"stage-{stage}-process-diagnostic.json"
                sidecar.write_text(json.dumps({
                    "stage": stage, "status": "completed", "return_code": 0,
                    "error_code": None,
                }), encoding="utf-8")
                report = _stage_report(
                    context, stage, receipt, receipt_path, "f" * 64, 1,
                    None, receipt["ledger"],
                )
                (output / f"stage-{stage}-report.json").write_text(
                    json.dumps(report, sort_keys=True), encoding="utf-8"
                )
            (output / "calls.jsonl").write_text("synthetic ledger placeholder\n",
                                                encoding="utf-8")

            calls = {"verify": 0, "stats": 0}

            def verify_recorded(_input_path):
                calls["verify"] += 1
                return {"verified_recorded": True, "native_calls": 0,
                        "diagnostic_sha256": "1" * 64}

            def read_stats(_input_path):
                calls["stats"] += 1
                return {"consumed": 7, "completed": 7, "unknown": 0,
                        "reserved": 0, "abandoned": 0, "limit": 7}

            with patch.object(tenki_module, "_diagnostic_hash",
                              return_value="f" * 64):
                verification = verify_curry_only(
                    root=root, output=output, runner=root / "runner.exe", repo=repo,
                    manifest=manifest, prepared_hash="b" * 64,
                    verify_recorded=verify_recorded, read_stats=read_stats,
                )

            self.assertTrue(verification["valid"])
            self.assertEqual(verification["native_calls"], 0)
            self.assertEqual(calls, {"verify": 7, "stats": 1})
            self.assertTrue((output / "verification.json").is_file())

            # A structurally valid report cannot promote a failed immutable
            # receipt to success, even when its receipt hash is refreshed.
            failed_receipt = copy.deepcopy(receipts[7])
            failed_receipt["successful"] = False
            failed_receipt["diagnostic"] = "engine_error"
            receipt_path = output / "stage-7.json"
            receipt_path.write_text(json.dumps(failed_receipt, sort_keys=True),
                                    encoding="utf-8")
            report_path = output / "stage-7-report.json"
            forged_report = json.loads(report_path.read_text(encoding="utf-8"))
            forged_report["receipt_sha256"] = hashlib.sha256(
                receipt_path.read_bytes()
            ).hexdigest()
            report_path.write_text(json.dumps(forged_report, sort_keys=True),
                                   encoding="utf-8")
            calls.update(verify=0, stats=0)
            checks = root / "verify-checks"
            checks.mkdir()
            with patch.object(tenki_module, "_diagnostic_hash",
                              return_value="f" * 64):
                forged_verification = verify_curry_only(
                    root=root, output=output, runner=root / "runner.exe", repo=repo,
                    manifest=manifest, prepared_hash="b" * 64,
                    verify_recorded=verify_recorded, read_stats=read_stats,
                    verification_output=checks,
                )
            self.assertFalse(forged_verification["valid"])
            self.assertEqual(forged_verification["diagnostic"],
                             "curry_saved_stage_report_receipt_mismatch")
            self.assertEqual(calls, {"verify": 6, "stats": 1})


class CurryWorkflowIntegrationTests(unittest.TestCase):
    def test_shared_scheduler_runs_all_seven_stages_with_parent_bound_branches(self):
        for spec in (
            CURRY_SCOPE,
            curry_module.CONFIRMATION_SCOPE,
            curry_module.OPTION_VERIFICATION_SCOPE,
            curry_module.OPTION_REVALIDATION_SCOPE,
        ):
            with self.subTest(scope=spec.scope):
                self._assert_shared_scheduler_runs_all_seven_stages(spec)

    def _assert_shared_scheduler_runs_all_seven_stages(self, spec):
        from unittest.mock import patch
        from ygo_eval import native_tenki_placement_validation as tenki_module

        with _TemporaryDirectory() as temporary:
            temp = Path(temporary)
            root = temp / "experiment"
            output = root / "research"
            repo = temp / "repo"
            output.mkdir(parents=True)
            repo.mkdir()
            runner = root / "native-artifacts" / "runner.exe"
            runner.parent.mkdir()
            runner.write_bytes(b"synthetic runner placeholder")
            context = "a" * 64
            stage1_request = {
                "protocol_version": 2,
                "engine": {"worker_path": "synthetic-worker.exe"},
                "decisions": [],
            }
            manifest = {
                "context": context,
                "started_at": 1_000,
                "request": copy.deepcopy(stage1_request),
                "assets": {"ordinary": copy.deepcopy(IDENTITY)},
            }
            source = {"identity": "synthetic-source", "files": {}}

            class SyntheticProcess:
                def __init__(self):
                    self.consumed = 0
                    self.completed = 0
                    self.modes = []
                    self.normal_stages = []

                def stats(self):
                    return {
                        "consumed": self.consumed,
                        "completed": self.completed,
                        "unknown": 0,
                        "reserved": 0,
                        "abandoned": 0,
                        "limit": spec.limit,
                    }

                def __call__(self, command, *, cwd, capture_output, timeout, check):
                    del cwd, capture_output, timeout, check
                    if "--stats" in command:
                        self.modes.append(("stats", None))
                        result = {"native_calls": 0, "ledger": self.stats()}
                        return subprocess.CompletedProcess(
                            command, 0, json.dumps(result).encode("utf-8"), b"",
                        )
                    if "--verify-recorded" in command:
                        self.modes.append(("verify_recorded", None))
                        result = {"native_calls": 0, "verified_recorded": True}
                        return subprocess.CompletedProcess(
                            command, 0, json.dumps(result).encode("utf-8"), b"",
                        )
                    if "--prepared-sha256" not in command:
                        raise AssertionError(f"unexpected runner mode: {command}")

                    invocation = json.loads(Path(command[1]).read_text(encoding="utf-8"))
                    stage = invocation["stage"]
                    self.modes.append(("normal", stage))
                    self.normal_stages.append(stage)
                    request = invocation["request"]
                    if stage == 2:
                        events = [_idle_event(10), _place_event(11)]
                        receipt = _receipt(
                            stage, request, events=events,
                            pending=events[-1]["fields"]["prompt"],
                            resolved=request["decisions"],
                        )
                    elif stage == 3:
                        events = [_idle_event(10), _place_event(11), _option_event(12)]
                        receipt = _receipt(
                            stage, request, events=events,
                            pending=events[-1]["fields"]["prompt"],
                            resolved=request["decisions"],
                        )
                    else:
                        receipt = _receipt(stage, request)
                    receipt["kind"] = curry_module._report_kind(spec, "stage")
                    receipt["scope"] = spec.scope
                    receipt["context"] = invocation["context"]
                    receipt["assets_before"] = copy.deepcopy(invocation["expected_identity"])
                    receipt["assets_after"] = copy.deepcopy(invocation["expected_identity"])
                    receipt_path = Path(invocation["output"])
                    with receipt_path.open("xb") as stream:
                        stream.write(json.dumps(receipt, sort_keys=True).encode("utf-8"))
                    ledger_path = Path(invocation["ledger"])
                    ledger_path.parent.mkdir(parents=True, exist_ok=True)
                    with ledger_path.open("ab") as stream:
                        stream.write(f"synthetic-stage-{stage}\n".encode("utf-8"))
                    self.consumed = stage
                    self.completed = stage
                    result = {
                        "successful": True,
                        "native_calls": 1,
                        "ledger": self.stats(),
                    }
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(result).encode("utf-8"),
                        b"synthetic trace\n",
                    )

            fake = SyntheticProcess()
            with patch("ygo_data.identity.stable_source", return_value=source):
                summary = run_curry_stages(
                    root=root,
                    output=output,
                    runner=runner,
                    repo=repo,
                    manifest=manifest,
                    prepared_hash="b" * 64,
                    stage1_request=stage1_request,
                    expected_identity=copy.deepcopy(IDENTITY),
                    source=source,
                    protected={},
                    frozen_files={},
                    process_runner=fake,
                    spec=spec,
                    clock=lambda: 2_000,
                )

            self.assertTrue(summary["successful"])
            self.assertEqual(fake.normal_stages, list(range(1, 8)))
            self.assertEqual(summary["new_consumed"], 7)
            if spec in (curry_module.OPTION_VERIFICATION_SCOPE,
                        curry_module.OPTION_REVALIDATION_SCOPE):
                expected_certified = spec.certified_historical_consumed
                expected_planning = spec.planning_base
                self.assertEqual(summary["certified_historical_consumed"], expected_certified)
                self.assertEqual(summary["policy_reserved"], 7)
                self.assertEqual(summary["planning_base"], expected_planning)
                self.assertEqual(summary["certified_consumed_including_new"],
                                 expected_certified + 7)
                self.assertEqual(summary["planning_total"], expected_planning + 7)
                self.assertIsNone(summary["old_confirmation_actual_consumed"])
                self.assertIsNone(summary["actual_all_history_cumulative"])
            else:
                self.assertEqual(
                    summary["cumulative_consumed"], spec.old_consumed + 7,
                )
            self.assertEqual(summary["unknown"], 0)
            self.assertEqual(summary["stages"][-1]["stage"], 7)
            self.assertEqual(summary["stages"][4]["independent_replay_matches"], True)
            self.assertEqual(summary["stages"][6]["independent_replay_matches"], True)

            requests = {
                stage: json.loads((output / f"stage-{stage}-request.json").read_text(
                    encoding="utf-8"))
                for stage in range(1, 8)
            }
            self.assertEqual(requests[1]["decisions"], [])
            self.assertEqual(requests[3]["decisions"][:-1], requests[2]["decisions"])
            self.assertEqual(requests[4]["decisions"][-1]["choice"],
                             {"kind": "option", "index": 0})
            self.assertEqual(requests[4]["decisions"][:-1], requests[3]["decisions"])
            self.assertEqual(requests[5], requests[4])
            self.assertEqual(requests[6]["decisions"][-1]["choice"],
                             {"kind": "option", "index": 1})
            self.assertEqual(requests[6]["decisions"][:-1], requests[3]["decisions"])
            self.assertEqual(requests[7], requests[6])
            self.assertTrue((root / "process-diagnostics").is_dir())
            self.assertEqual(len(list(output.glob("stage-*-report.json"))), 7)

            audited = curry_module._verify_curry_stage_artifacts(
                root=root,
                research=output,
                manifest=manifest,
                stage=1,
                expected_request=requests[1],
                stage_summary=summary["stages"][0],
                spec=spec,
                report_kind=curry_module._report_kind(spec, "stage_report"),
                validate_report=lambda value: validate_curry_report(value, spec=spec),
                diagnostic_hash=lambda path, record:
                    tenki_module._diagnostic_hash(path, record, spec),
            )
            self.assertEqual(audited["receipt"], json.loads(
                (output / "stage-1.json").read_text(encoding="utf-8")))
            self.assertTrue(audited["report"]["successful"])

            input_path = output / "stage-1-input.json"
            original_input = input_path.read_bytes()
            changed_input = json.loads(original_input)
            changed_input["context"] = "c" * 64
            input_path.write_text(json.dumps(changed_input), encoding="utf-8")
            try:
                with self.assertRaisesRegex(ValueError, "curry_saved_stage_intent_invalid"):
                    curry_module._verify_curry_stage_artifacts(
                        root=root, research=output, manifest=manifest, stage=1,
                        expected_request=requests[1], stage_summary=summary["stages"][0],
                        spec=spec,
                        report_kind=curry_module._report_kind(spec, "stage_report"),
                        validate_report=lambda value: validate_curry_report(value, spec=spec),
                        diagnostic_hash=lambda path, record:
                            tenki_module._diagnostic_hash(path, record, spec),
                    )
            finally:
                input_path.write_bytes(original_input)

            process_record = audited["diagnostic_record"]
            process_sidecar = root / f"stage-1-process-diagnostic.json"
            original_sidecar = process_sidecar.read_bytes()
            process_sidecar.write_text('{"tampered":true}\n', encoding="utf-8")
            try:
                with self.assertRaisesRegex(
                    ValueError, "curry_saved_stage_diagnostic_sidecar_mismatch"
                ):
                    curry_module._verify_curry_stage_artifacts(
                        root=root, research=output, manifest=manifest, stage=1,
                        expected_request=requests[1], stage_summary=summary["stages"][0],
                        spec=spec,
                        report_kind=curry_module._report_kind(spec, "stage_report"),
                        validate_report=lambda value: validate_curry_report(value, spec=spec),
                        diagnostic_hash=lambda path, record:
                            tenki_module._diagnostic_hash(path, record, spec),
                    )
            finally:
                process_sidecar.write_bytes(original_sidecar)

            stdout_path = root / process_record["stdout"]["path"]
            original_stdout = stdout_path.read_bytes()
            stdout_path.write_bytes(b"tampered stdout\n")
            try:
                with self.assertRaisesRegex(ValueError, "curry_saved_stage_diagnostic_missing"):
                    curry_module._verify_curry_stage_artifacts(
                        root=root, research=output, manifest=manifest, stage=1,
                        expected_request=requests[1], stage_summary=summary["stages"][0],
                        spec=spec,
                        report_kind=curry_module._report_kind(spec, "stage_report"),
                        validate_report=lambda value: validate_curry_report(value, spec=spec),
                        diagnostic_hash=lambda path, record:
                            tenki_module._diagnostic_hash(path, record, spec),
                    )
            finally:
                stdout_path.write_bytes(original_stdout)


class CurryBaselineRoutingTests(unittest.TestCase):
    def test_baseline_audit_uses_curry_root_and_separate_legacy_root(self):
        from ygo_eval.native_tenki_placement_validation import VALIDATION_SCOPE

        with _TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            baseline = repo / CURRY_SCOPE.baseline_root
            (baseline / "final-build").mkdir(parents=True)
            (baseline / "research").mkdir()
            (baseline / "process-diagnostics").mkdir()
            acceptance_raw = b'{"kind":"synthetic_acceptance"}'
            delivery_raw = b'{"kind":"synthetic_delivery"}'
            (baseline / "acceptance.json").write_bytes(acceptance_raw)
            (baseline / "final-build" / "delivery.json").write_bytes(delivery_raw)
            spec = replace(
                CURRY_SCOPE,
                delivery_acceptance_sha256=hashlib.sha256(acceptance_raw).hexdigest(),
                delivery_sha256=hashlib.sha256(delivery_raw).hexdigest(),
            )
            with patch("ygo_data.identity.stable_source", return_value={"identity": "synthetic"}), \
                    patch(
                        "ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                        return_value=({"history": "verified"}, {}),
                    ) as legacy_verify, \
                    patch.object(
                        curry_module, "_verify_curry_delivery",
                        return_value=({"delivery": "verified"}, {}),
                    ) as curry_verify:
                audited, protected = curry_module._verify_curry_baseline(repo, baseline, spec)

            legacy_verify.assert_called_once_with(
                repo,
                repo / VALIDATION_SCOPE.baseline_root,
                VALIDATION_SCOPE,
                protection_scope=spec.scope,
            )
            curry_verify.assert_called_once()
            self.assertEqual(audited["prior"], {"history": "verified"})
            self.assertEqual(audited["delivery"], {"delivery": "verified"})
            self.assertEqual(len(protected), 3)

    def test_baseline_audit_rejects_evidence_changed_during_validation(self):
        with _TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            baseline = repo / CURRY_SCOPE.baseline_root
            (baseline / "final-build").mkdir(parents=True)
            (baseline / "research").mkdir()
            (baseline / "process-diagnostics").mkdir()
            sidecar = baseline / "stage-1-process-diagnostic.json"
            sidecar.write_bytes(b'{"stage":1}\n')
            acceptance_raw = b'{"kind":"synthetic_acceptance"}'
            delivery_raw = b'{"kind":"synthetic_delivery"}'
            (baseline / "acceptance.json").write_bytes(acceptance_raw)
            (baseline / "final-build" / "delivery.json").write_bytes(delivery_raw)
            spec = replace(
                CURRY_SCOPE,
                delivery_acceptance_sha256=hashlib.sha256(acceptance_raw).hexdigest(),
                delivery_sha256=hashlib.sha256(delivery_raw).hexdigest(),
            )

            def mutate_after_validation(*_args, **_kwargs):
                sidecar.write_bytes(b'{"stage":1,"changed":true}\n')
                return ({"delivery": "verified"}, {})

            with patch("ygo_data.identity.stable_source",
                       return_value={"identity": "synthetic"}), \
                    patch(
                        "ygo_eval.native_tenki_placement_validation._verify_validation_baseline",
                        return_value=({"history": "verified"}, {}),
                    ), patch.object(
                        curry_module, "_verify_curry_delivery",
                        side_effect=mutate_after_validation,
                    ):
                with self.assertRaisesRegex(
                    ValueError, "curry_baseline_evidence_changed_during_audit"
                ):
                    curry_module._verify_curry_baseline(repo, baseline, spec)

    def test_baseline_audit_rejects_the_legacy_root_as_curry_delivery(self):
        with _TemporaryDirectory() as temporary:
            repo = Path(temporary)
            with patch(
                "ygo_eval.native_tenki_placement_validation._verify_validation_baseline"
            ) as legacy_verify:
                with self.assertRaisesRegex(ValueError, "curry_fixed_baseline_required"):
                    curry_module._verify_curry_baseline(
                        repo, repo / "data/runtime/p1-tenki-runner-repair-offline-2026-10-23",
                    )
            legacy_verify.assert_not_called()


class CurryAuxiliaryDiagnosticsTests(unittest.TestCase):
    def test_preflight_and_verify_sidecars_are_recomputed_from_raw_streams(self):
        from ygo_data.identity import digest
        from ygo_eval.native_tenki_placement_validation import _diagnostic_hash
        from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

        with _TemporaryDirectory() as temporary:
            root = Path(temporary) / "experiment"
            root.mkdir()
            context = "a" * 64
            identity_sha256 = "d" * 64
            manifest = {
                "context": context,
                "request": {"decisions": []},
                "assets": {"ordinary": {"identity": identity_sha256}},
            }
            manifest_raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
            stage1_input_raw = b"synthetic immutable stage-one input"
            spec = CURRY_SCOPE

            def save_process(mode, output):
                stdout = json.dumps(output, sort_keys=True).encode("utf-8") + b"\n"
                completed = subprocess.CompletedProcess(
                    ["synthetic-runner"], 0, stdout, b"",
                )
                record, _ = capture_process_diagnostic(
                    ["synthetic-runner"], root, root, mode=mode, timeout=1,
                    runner=lambda *_args, **_kwargs: completed,
                    runner_role=spec.runner_role,
                )
                return record, _diagnostic_hash(root, record, spec)

            _preflight_record, preflight_hash = save_process("preflight_only", {
                "context": context, "identity_sha256": identity_sha256,
                "native_calls": 0, "preflight_passed": True, "stage": 1,
            })
            stats = {"abandoned": 0, "completed": spec.limit,
                     "consumed": spec.limit, "limit": spec.limit,
                     "reserved": 0, "unknown": 0}
            verification_hashes = [
                save_process("verify_recorded", {
                    "ledger": stats, "native_calls": 0,
                    "successful": True, "verified_recorded": True,
                })[1]
                for _ in range(spec.limit)
            ]
            prepared = {
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "stage1_input_sha256": hashlib.sha256(stage1_input_raw).hexdigest(),
                "stage1_request_sha256": digest(canonical(manifest["request"])),
                "preflight_diagnostic_sha256": preflight_hash,
            }
            prepared_raw = json.dumps(prepared, sort_keys=True).encode("utf-8")
            stages = [{"stage": 1}]
            summary = {"stages": stages}
            verification = {
                "context": context,
                "prepared_sha256": hashlib.sha256(prepared_raw).hexdigest(),
                "verification_diagnostic_sha256": verification_hashes,
                "stages": stages,
            }

            curry_module._verify_curry_auxiliary_diagnostics(
                root=root, manifest=manifest, prepared=prepared,
                prepared_raw=prepared_raw, manifest_raw=manifest_raw,
                summary=summary, verification=verification,
                stage1_input_raw=stage1_input_raw, spec=spec,
                diagnostic_hash=lambda path, record:
                    _diagnostic_hash(path, record, spec),
            )

            verify_records = list((root / "process-diagnostics").glob(
                "verify_recorded-*.json"
            ))
            record = json.loads(verify_records[0].read_text(encoding="utf-8"))
            stdout_path = root / record["stdout"]["path"]
            original = stdout_path.read_bytes()
            stdout_path.write_bytes(b"tampered\n")
            try:
                with self.assertRaisesRegex(
                    ValueError, "curry_verification_diagnostic_missing"
                ):
                    curry_module._verify_curry_auxiliary_diagnostics(
                        root=root, manifest=manifest, prepared=prepared,
                        prepared_raw=prepared_raw, manifest_raw=manifest_raw,
                        summary=summary, verification=verification,
                        stage1_input_raw=stage1_input_raw, spec=spec,
                        diagnostic_hash=lambda path, item:
                            _diagnostic_hash(path, item, spec),
                    )
            finally:
                stdout_path.write_bytes(original)


class CurryPrepareOnlyIntegrationTests(unittest.TestCase):
    def test_prepare_only_runs_real_freeze_path_and_only_preflight_process(self):
        with _TemporaryDirectory() as temporary:
            temp = Path(temporary)
            repo = temp / "repo"
            repo.mkdir()
            (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf-8")
            spec = replace(
                CURRY_SCOPE,
                output_root=Path("data/runtime/curry-synthetic-e2e"),
                baseline_root=Path("data/runtime/curry-synthetic-baseline"),
                delivery_acceptance_sha256="",
                delivery_sha256="",
            )
            root = repo / spec.output_root
            artifact_dir = root / "native-artifacts"
            artifact_dir.mkdir(parents=True)
            for name in ("curry-option-validation.exe", "ygo-engine-worker.exe", "ygo-cli.exe"):
                (artifact_dir / name).write_bytes(("synthetic-" + name).encode())
            (root / "build-record.json").write_bytes(b"synthetic-build-record")

            baseline = repo / spec.baseline_root / "final-build"
            baseline.mkdir(parents=True)
            (baseline / "delivery.json").write_bytes(b"synthetic-baseline-delivery")
            acceptance_path = repo / spec.baseline_root / "acceptance.json"
            acceptance_path.write_bytes(b"synthetic-baseline-acceptance")
            spec = replace(
                spec,
                delivery_acceptance_sha256=hashlib.sha256(acceptance_path.read_bytes()).hexdigest(),
                delivery_sha256=hashlib.sha256((baseline / "delivery.json").read_bytes()).hexdigest(),
            )

            fixed_files = {
                "preparation": curry_module.PREPARATION_PATH,
                "preparation_report": curry_module.PREPARATION_REPORT_PATH,
                "preparation_acceptance": curry_module.PREPARATION_ACCEPTANCE_PATH,
                "operations_source": Path("data/tmp/ocgcore-source/operations.cpp"),
                "base_request": curry_module.FROZEN_CASES_PATH,
                "adapter_codec": Path(curry_module.HISTORICAL_SOURCE_TRANSITION["path"]),
                "banlist": Path("data/runtime/banlist.json"),
            }
            file_hashes = {}
            for index, (role, relative) in enumerate(fixed_files.items()):
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"synthetic-{role}-{index}".encode())
                file_hashes[role] = hashlib.sha256(path.read_bytes()).hexdigest()

            main = [85_138_716, *range(1_000, 1_039)]
            rabbit_case = {
                "case_id": "rabbit",
                "deck": {"main": main, "extra": [20_001, 20_002, 20_003], "side": []},
                "opening_hand": [85_138_716, 2_964_201, 2_964_201, 2_964_201, 2_971_090],
                "seed": 1,
                "information": {"opponent_resources": {"hand": [], "main": main}},
            }
            candidate_case = curry_module._derived_curry_case(rabbit_case)
            base_request = {
                "protocol_version": 2,
                "seed": 1,
                "deck": copy.deepcopy(rabbit_case["deck"]),
                "opening_hand": copy.deepcopy(rabbit_case["opening_hand"]),
                "decisions": [{"old": "decision"}],
                "engine": {"worker_path": "frozen-worker.exe"},
            }
            base_request_sha = hashlib.sha256(curry_module._case_encode(base_request)).hexdigest()
            candidate_sha = hashlib.sha256(curry_module._case_encode(candidate_case)).hexdigest()
            input_sha = {
                "preparation": file_hashes["preparation"],
                "preparation_report": file_hashes["preparation_report"],
                "preparation_acceptance": file_hashes["preparation_acceptance"],
                "operations_source": file_hashes["operations_source"],
                "candidate_case": candidate_sha,
                "base_request": base_request_sha,
            }
            preparation = {
                "candidate": {"case": copy.deepcopy(candidate_case)},
                "candidate_case": candidate_case,
                "rabbit_case": rabbit_case,
                "base_request": base_request,
                "base_request_entry": {"banlist_path": "data/runtime/banlist.json"},
                "stage1_request_template": base_request,
                "frozen_cases_sha256": "1" * 64,
                "input_sha256": input_sha,
            }
            pinned = {
                "preparation": file_hashes["preparation"],
                "preparation_report": file_hashes["preparation_report"],
                "preparation_acceptance": file_hashes["preparation_acceptance"],
                "candidate_case": candidate_sha,
                "base_request": base_request_sha,
                "operations_source": file_hashes["operations_source"],
                "adapter_codec": file_hashes["adapter_codec"],
            }
            spec = replace(spec, baseline_root=spec.baseline_root)
            with patch.object(curry_module, "PINNED_INPUT_SHA256", pinned), \
                    patch.object(curry_module, "BASE_REQUEST_SHA256", base_request_sha), \
                    patch.object(curry_module, "CANDIDATE_CASE_SHA256", candidate_sha), \
                    patch.object(curry_module, "BASELINE_ACCEPTANCE_SHA256",
                                 spec.delivery_acceptance_sha256), \
                    patch.object(curry_module, "BASELINE_DELIVERY_SHA256", spec.delivery_sha256), \
                    patch.object(curry_module, "_verify_curry_baseline",
                                 return_value=({"verified": True}, {})), \
                    patch.object(curry_module, "verify_curry_preparation",
                                 return_value=preparation), \
                    patch("ygo_data.identity.stable_source",
                          return_value={"identity": "synthetic-source", "files": {}}), \
                    patch("ygo_eval.native_tenki_placement._candidate_configs") as configs_mock, \
                    patch("ygo_eval.native_tenki_placement._archive_current_source") as archive_mock, \
                    patch("ygo_eval.native_tenki_placement._capture_identity") as capture_mock, \
                    patch("ygo_eval.native_tenki_placement_confirmation._verify_build_and_identity") as build_mock, \
                    patch("ygo_eval.native_tenki_placement_confirmation._verify_workspace_identity") as workspace_mock, \
                    patch.object(curry_module.time, "time", return_value=1_000):
                config_paths = {
                    "ordinary": root / "ordinary-candidate.toml",
                    "tournament": root / "tournament-candidate.toml",
                }
                def write_configs(_repo, _root, _worker, _baseline):
                    for role, path in config_paths.items():
                        path.write_text(f"{role}=synthetic\n", encoding="utf-8")
                    return config_paths
                configs_mock.side_effect = write_configs

                archive_path = root / "source-native.zip"
                file_list_path = root / "source-native-file-list.json"
                def write_archive(_repo, _root, source):
                    archive_path.write_bytes(b"synthetic-source-archive")
                    file_list_path.write_text("{}", encoding="utf-8")
                    return {
                        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                        "file_list_sha256": hashlib.sha256(file_list_path.read_bytes()).hexdigest(),
                    }
                archive_mock.side_effect = write_archive

                identity_path = root / "identity.json"
                identity = {"identity": "d" * 64}
                def capture_identity(_repo, _cli, _configs, output_path):
                    self.assertTrue((root / "window-start.json").is_file())
                    output_path.write_text(json.dumps(identity), encoding="utf-8")
                    return identity
                capture_mock.side_effect = capture_identity
                ordinary = {"identity": "b" * 64}
                tournament = {"identity": "c" * 64}
                workspace_mock.return_value = (ordinary, tournament)

                build_record_hash = hashlib.sha256((root / "build-record.json").read_bytes()).hexdigest()
                build_mock.return_value = (
                    {"identity": "synthetic-build"},
                    {"runner": "r" * 64, "worker": "w" * 64, "cli": "c" * 64},
                    artifact_dir / "ygo-cli.exe",
                    build_record_hash,
                )

                class PreflightRunner:
                    def __init__(self):
                        self.commands = []

                    def __call__(self, command, *, cwd, capture_output, timeout, check):
                        del cwd, capture_output, check
                        self.commands.append((list(command), timeout))
                        self.assert_command = command
                        self_test = self
                        input_path = Path(command[1])
                        invocation = json.loads(input_path.read_text(encoding="utf-8"))
                        self_test.invocation = invocation
                        if ("--preflight-only" not in command
                                or "--trace-stderr" not in command
                                or "--prepared-sha256" in command
                                or timeout > 900):
                            raise AssertionError("prepare-only called a non-preflight runner mode")
                        result = {
                            "preflight_passed": True,
                            "native_calls": 0,
                            "context": invocation["context"],
                            "identity_sha256": ordinary["identity"],
                        }
                        return subprocess.CompletedProcess(
                            command, 0, json.dumps(result).encode("utf-8"), b"synthetic trace\n",
                        )

                fake_runner = PreflightRunner()
                args = argparse.Namespace(
                    baseline_dir=repo / spec.baseline_root,
                    preparation=repo / curry_module.PREPARATION_PATH,
                    cases=repo / curry_module.FROZEN_CASES_PATH,
                    core_source=repo / "data/tmp/ocgcore-source/operations.cpp",
                    runner=artifact_dir / "curry-option-validation.exe",
                    worker=artifact_dir / "ygo-engine-worker.exe",
                    build_record=root / "build-record.json",
                    identity=root / "identity.json",
                    window_start=root / "window-start.json",
                    output=root / "research",
                    prepare_only=True,
                    verify_only=False,
                )
                prepared = curry_module.native_curry_option_validation(
                    args, repo, process_runner=fake_runner, spec=spec,
                )

            self.assertTrue(prepared["prepared"])
            self.assertTrue(prepared["execution_ready"])
            self.assertEqual(prepared["native_calls"], 0)
            self.assertFalse((root / "research" / "calls.jsonl").exists())
            self.assertEqual(len(fake_runner.commands), 1)
            self.assertTrue((root / "research" / "manifest.json").is_file())
            self.assertTrue((root / "research" / "stage-1-input-seal.json").is_file())


if __name__ == "__main__":
    unittest.main()
