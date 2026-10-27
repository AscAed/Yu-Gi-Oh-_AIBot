"""Fixed-scope Python orchestration and independent evidence checks for Tenki placement validation."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import copy
from fractions import Fraction
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
from typing import Any, Callable

from ygo_data.identity import canonical, digest, stable_source
from ygo_eval.prompt_probe_prepare import require, safe_path, strict_json
from ygo_eval.native_tenki_workflow import (
    WorkflowSpec,
    capture_runner_process,
    normal_runner_timeout,
    process_diagnostic_sha256,
    run_six_stage_workflow,
)
from ygo_eval.terminal_regression import immutable_write


@dataclass(frozen=True, slots=True)
class ScopeSpec:
    scope: str
    output_root: Path
    baseline_root: Path
    limit: int
    wall_seconds: int
    old_consumed: int
    batch_kind: str
    input_seal_kind: str
    runner_role: str
    delivery_sha256: str


VALIDATION_SCOPE = ScopeSpec(
    scope="tenki-placement-validation-v1",
    output_root=Path("data/runtime/p1-tenki-placement-validation-native-2026-10-23"),
    baseline_root=Path("data/runtime/p1-tenki-runner-repair-offline-2026-10-23"),
    limit=6,
    wall_seconds=7200,
    old_consumed=26,
    batch_kind="tenki-placement-validation-v1",
    input_seal_kind="tenki_placement_validation_stage_input_seal",
    runner_role="tenki_placement_validation_runner",
    delivery_sha256="84a3fc887e967f45c2c807d104450b41fbb31c038e93132b30b6bebadc669e22",
)
WORKFLOW_SPEC = WorkflowSpec(
    scope=VALIDATION_SCOPE.scope,
    limit=VALIDATION_SCOPE.limit,
    wall_seconds=VALIDATION_SCOPE.wall_seconds,
    worker_timeout_seconds=30,
    runner_role=VALIDATION_SCOPE.runner_role,
    stage_kind="native_tenki_placement_validation_stage",
    stage_report_kind="native_tenki_placement_validation_stage_report",
    input_seal_kind=VALIDATION_SCOPE.input_seal_kind,
    trace_stderr=True,
    timeout_error_prefix="validation",
)
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
_HASH = re.compile(r"^[a-f0-9]{64}$")
_YES_NO_DESCRIPTION = 59877851398144
_PLACE_MASK = 0xFFFFE0FF
_PROMPT_BY_STAGE = {1: 18, 2: 13, 3: 11, 4: 11, 5: 15, 6: 15}
_PARENT_BY_STAGE = {2: 1, 3: 2, 4: 3, 5: 2, 6: 5}
MANIFEST_INPUT_ROLES = (
    "runner", "worker", "cli", "build_record", "identity", "window_start",
    "source_archive", "source_file_list", "ordinary_config", "tournament_config",
    "banlist", "preparation", "baseline_delivery", "baseline_audit",
    "prompt_source_stage1", "prompt_source_stage2_request",
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    for name in ("baseline-dir", "runner", "worker", "build-record", "identity", "window-start", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--verify-only", action="store_true")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _need(condition: bool, code: str) -> None:
    require(condition, code)


def _strict_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool-is-int equality shortcut."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_strict_equal(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(_strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def _u32(value: int) -> list[int]:
    return list(struct.pack("<I", value))


class _Reader:
    """Small strict little-endian reader for supported prompt frames."""

    def __init__(self, raw: bytes):
        self.raw = raw
        self.pos = 0

    def take(self, count: int) -> bytes:
        end = self.pos + count
        if count < 0 or end > len(self.raw):
            raise ValueError("automatic_prompt_raw_truncated")
        value = self.raw[self.pos:end]
        self.pos = end
        return value

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def loc(self) -> None:
        self.take(10)

    def count(self) -> int:
        value = self.u32()
        if value > 4096:
            raise ValueError("automatic_prompt_count_limit")
        return value

    def finish(self) -> None:
        if self.pos != len(self.raw):
            raise ValueError("automatic_prompt_raw_trailing_bytes")


def _word_response(*values: int) -> list[int]:
    return list(b"".join(struct.pack("<I", value) for value in values))


def _bounded_binomial(n: int, k: int, limit: int) -> int:
    """Return C(n,k), capped at limit+1 without constructing a large integer."""
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    value = 1
    for step in range(1, k + 1):
        value = value * (n - k + step) // step
        if value > limit:
            return limit + 1
    return value


def _bounded_combination_sum(n: int, minimum: int, maximum: int, limit: int) -> int:
    """Count a selection range with saturation, stopping before enumeration."""
    total = 0
    for size in range(minimum, maximum + 1):
        total += _bounded_binomial(n, size, limit)
        if total > limit:
            return limit + 1
    return total


def _require_bounded_combinations(n: int, minimum: int, maximum: int) -> None:
    if _bounded_combination_sum(n, minimum, maximum, 4096) > 4096:
        raise ValueError("automatic_prompt_combination_limit")


def _enumerate_prompt_actions(raw: bytes) -> tuple[int, int, list[tuple[dict, list[int]]]]:
    """Independently reconstruct response Choice/bytes from the raw prompt."""
    reader = _Reader(raw)
    opcode = reader.u8()
    player = reader.u8()
    if player not in (0, 1):
        raise ValueError("automatic_prompt_player_invalid")
    actions: list[tuple[dict, list[int]]] = []
    if opcode == 11:
        for command in range(6):
            for index in range(reader.count()):
                reader.u32()
                reader.take(2)
                reader.u32()
                if command == 5:
                    reader.u64()
                    reader.u8()
                actions.append((
                    {"kind": "command", "command": command, "index": index},
                    _word_response((index << 16) | command),
                ))
        for command, enabled in ((6, reader.u8()), (7, reader.u8()), (8, reader.u8())):
            if enabled:
                actions.append((
                    {"kind": "command", "command": command, "index": 0},
                    _word_response(command),
                ))
    elif opcode in (12, 13):
        if opcode == 12:
            reader.u32()
            reader.loc()
        reader.u64()
        actions = [
            ({"kind": "yes_no", "yes": False}, _word_response(0)),
            ({"kind": "yes_no", "yes": True}, _word_response(1)),
        ]
    elif opcode == 14:
        count = reader.u8()
        for index in range(count):
            reader.u64()
            actions.append(({"kind": "option", "index": index}, _word_response(index)))
    elif opcode == 15:
        cancel = bool(reader.u8())
        minimum, maximum, count = reader.count(), reader.count(), reader.count()
        if minimum > maximum or maximum > count:
            raise ValueError("automatic_prompt_selection_bounds_invalid")
        for _ in range(count):
            reader.u32()
            reader.loc()
        _require_bounded_combinations(count, minimum, maximum)
        combinations = [
            indices
            for size in range(minimum, maximum + 1)
            for indices in itertools.combinations(range(count), size)
        ]
        for indices in combinations:
            actions.append((
                {"kind": "cards", "indices": list(indices)},
                _word_response(0, len(indices), *indices),
            ))
        if cancel:
            actions.append(({"kind": "finish"}, _word_response(0xFFFFFFFF)))
    elif opcode == 16:
        reader.u8()
        forced = bool(reader.u8())
        reader.u32()
        reader.u32()
        for index in range(reader.count()):
            reader.u32()
            reader.loc()
            reader.u64()
            reader.u8()
            actions.append((
                {"kind": "chain", "index": index},
                _word_response(index),
            ))
        if not forced:
            actions.append(({"kind": "chain", "index": None}, _word_response(0xFFFFFFFF)))
    elif opcode in (18, 24):
        amount = reader.u8()
        mask = reader.u32()
        zones = []
        for relative in range(2):
            for location in (4, 8):
                for sequence in range(7 if location == 4 else 8):
                    bit = sequence + (8 if location == 8 else 0) + relative * 16
                    if mask & (1 << bit) == 0:
                        zones.append({
                            "player": player if relative == 0 else 1 - player,
                            "location": location,
                            "sequence": sequence,
                        })
        if amount > len(zones):
            raise ValueError("automatic_prompt_zone_count_invalid")
        _require_bounded_combinations(len(zones), amount, amount)
        combinations = list(itertools.combinations(range(len(zones)), amount))
        for indices in combinations:
            selected = [zones[index] for index in indices]
            data = [byte for zone in selected for byte in (
                zone["player"], zone["location"], zone["sequence"]
            )]
            actions.append(({"kind": "place", "zones": selected}, data))
    elif opcode == 19:
        reader.u32()
        mask = reader.u8()
        for position in (1, 2, 4, 8):
            if mask & position:
                actions.append((
                    {"kind": "position", "position": position},
                    _word_response(position),
                ))
    elif opcode == 26:
        finish, cancel = bool(reader.u8()), bool(reader.u8())
        reader.u32()
        reader.u32()
        codes = []
        for _ in range(2):
            for _ in range(reader.count()):
                codes.append(reader.u32())
                reader.loc()
        for index, _code in enumerate(codes):
            actions.append((
                {"kind": "toggle", "index": index},
                _word_response(1, index),
            ))
        if finish or cancel:
            actions.append(({"kind": "finish"}, _word_response(0xFFFFFFFF)))
    else:
        raise ValueError("automatic_prompt_opcode_unsupported")
    reader.finish()
    if not actions:
        raise ValueError("automatic_prompt_has_no_actions")
    return opcode, player, actions


def _event_prompt(event: Any, expected_prompt_id: int) -> tuple[dict, bytes, list[tuple[dict, list[int]]]]:
    if not isinstance(event, dict):
        raise ValueError("automatic_prompt_event_invalid")
    prompt_id = event.get("sequence")
    if type(prompt_id) is not int or prompt_id != expected_prompt_id:
        raise ValueError("automatic_prompt_event_sequence_mismatch")
    raw_value = event.get("raw")
    if not isinstance(raw_value, list) or any(type(byte) is not int or not 0 <= byte <= 255 for byte in raw_value):
        raise ValueError("automatic_prompt_raw_invalid")
    raw = bytes(raw_value)
    opcode, player, actions = _enumerate_prompt_actions(raw)
    if (type(event.get("opcode")) is not int or event.get("opcode") != opcode
            or event.get("supported") is not True):
        raise ValueError("automatic_prompt_event_opcode_or_support_mismatch")
    fields = event.get("fields")
    prompt = fields.get("prompt") if isinstance(fields, dict) else None
    if (not isinstance(prompt, dict) or type(prompt.get("id")) is not int
            or type(prompt.get("opcode")) is not int or type(prompt.get("player")) is not int
            or prompt.get("id") != prompt_id or prompt.get("opcode") != opcode
            or prompt.get("player") != player):
        raise ValueError("automatic_prompt_normalized_fields_mismatch")
    actual = prompt.get("actions")
    if not isinstance(actual, list):
        raise ValueError("automatic_prompt_actions_missing")
    actual_pairs = []
    for item in actual:
        if not isinstance(item, dict) or not isinstance(item.get("choice"), dict):
            raise ValueError("automatic_prompt_action_invalid")
        data = item.get("bytes")
        if not isinstance(data, list) or any(type(byte) is not int or not 0 <= byte <= 255 for byte in data):
            raise ValueError("automatic_prompt_response_bytes_invalid")
        actual_pairs.append((item["choice"], data))
    if opcode in (18, 24):
        actual_keyed = sorted(canonical([choice, response]) for choice, response in actual_pairs)
        expected_keyed = sorted(canonical([choice, response]) for choice, response in actions)
        matches = actual_keyed == expected_keyed
    else:
        matches = _strict_equal(actual_pairs, actions)
    if not matches:
        raise ValueError("automatic_prompt_response_mismatch")
    return prompt, raw, actions


def validate_auto_decisions(requested: Any, resolved: Any, events: Any) -> list[dict]:
    """Validate request prefix and independently bind every automatic tail choice to a singleton raw prompt."""
    if (not isinstance(requested, list) or not isinstance(resolved, list)
            or not _strict_equal(resolved[:len(requested)], requested)):
        raise ValueError("request_decisions_not_a_resolved_prefix")
    if not isinstance(events, list):
        raise ValueError("automatic_prompt_events_missing")
    for decision in [*requested, *resolved]:
        if (not isinstance(decision, dict) or type(decision.get("prompt_id")) is not int
                or type(decision.get("player")) is not int or decision.get("player") not in (0, 1)
                or not isinstance(decision.get("choice"), dict)):
            raise ValueError("automatic_decision_shape_invalid")
    tail = resolved[len(requested):]
    previous_id = requested[-1].get("prompt_id", -1) if requested and isinstance(requested[-1], dict) else -1
    for decision in tail:
        prompt_id = decision["prompt_id"]
        if prompt_id <= previous_id:
            raise ValueError("automatic_decision_prompt_order_invalid")
        matches = [event for event in events if isinstance(event, dict) and event.get("sequence") == prompt_id]
        if len(matches) != 1:
            raise ValueError("automatic_prompt_event_not_unique")
        prompt, _raw, actions = _event_prompt(matches[0], prompt_id)
        if prompt.get("player") != decision["player"] or len(actions) != 1:
            raise ValueError("automatic_prompt_not_single_action")
        if not _strict_equal(decision.get("choice"), actions[0][0]):
            raise ValueError("automatic_prompt_choice_mismatch")
        previous_id = prompt_id
    return copy.deepcopy(tail)


def _pending_prompt(result: dict, opcode: int) -> tuple[dict, bytes, dict]:
    prompt = result.get("prompt")
    if (not isinstance(prompt, dict) or type(prompt.get("id")) is not int
            or type(prompt.get("opcode")) is not int or type(prompt.get("player")) is not int
            or prompt.get("opcode") != opcode or prompt.get("player") != 0):
        raise ValueError("stage_pending_prompt_unexpected")
    events = result.get("events")
    if not isinstance(events, list):
        raise ValueError("stage_pending_events_missing")
    matches = [event for event in events if isinstance(event, dict) and event.get("sequence") == prompt.get("id")]
    if len(matches) != 1:
        raise ValueError("stage_pending_prompt_event_not_unique")
    normalized, raw, actions = _event_prompt(matches[0], prompt.get("id"))
    if not _strict_equal(normalized, prompt):
        raise ValueError("stage_pending_prompt_normalization_mismatch")
    if events[-1] != matches[0]:
        raise ValueError("stage_pending_prompt_not_final_event")
    return prompt, raw, matches[0]


def _validate_place_prompt(prompt: dict, raw: bytes) -> None:
    if len(raw) != 7 or raw[:3] != bytes((18, 0, 1)) or int.from_bytes(raw[3:], "little") != _PLACE_MASK:
        raise ValueError("stage_opcode18_raw_frame_mismatch")
    actions = prompt.get("actions")
    if not isinstance(actions, list) or len(actions) != 5:
        raise ValueError("stage_opcode18_responses_mismatch")
    seen: set[int] = set()
    for action in actions:
        choice = action.get("choice") if isinstance(action, dict) else None
        zones = choice.get("zones") if isinstance(choice, dict) else None
        if (not isinstance(choice, dict) or choice.get("kind") != "place"
                or not isinstance(zones, list) or len(zones) != 1):
            raise ValueError("stage_opcode18_responses_mismatch")
        zone = zones[0]
        if (not isinstance(zone, dict) or type(zone.get("player")) is not int
                or type(zone.get("location")) is not int or type(zone.get("sequence")) is not int
                or zone != {"player": 0, "location": 8, "sequence": zone.get("sequence")}
                or zone.get("sequence") not in range(5)
                or zone["sequence"] in seen
                or action.get("bytes") != [0, 8, zone["sequence"]]):
            raise ValueError("stage_opcode18_responses_mismatch")
        seen.add(zone["sequence"])
    if seen != set(range(5)):
        raise ValueError("stage_opcode18_responses_mismatch")


def _validate_yes_no_prompt(prompt: dict, raw: bytes) -> None:
    if raw != bytes((13, 0)) + _YES_NO_DESCRIPTION.to_bytes(8, "little"):
        raise ValueError("stage_opcode13_raw_frame_mismatch")
    expected = [
        ({"kind": "yes_no", "yes": False}, [0, 0, 0, 0]),
        ({"kind": "yes_no", "yes": True}, [1, 0, 0, 0]),
    ]
    if not _strict_equal([(action.get("choice"), action.get("bytes"))
                          for action in prompt.get("actions", [])], expected):
        raise ValueError("stage_opcode13_responses_mismatch")


def _validate_targets_prompt(prompt: dict, raw: bytes) -> None:
    if (len(raw) != 43 or raw[:3] != bytes((15, 0, 0))
            or int.from_bytes(raw[3:7], "little") != 1
            or int.from_bytes(raw[7:11], "little") != 1
            or int.from_bytes(raw[11:15], "little") != 2
            or len(prompt.get("actions", [])) != 2):
        raise ValueError("stage_opcode15_raw_frame_mismatch")
    seen = set()
    for index, action in enumerate(prompt["actions"]):
        card = raw[15 + index * 14:29 + index * 14]
        code = int.from_bytes(card[:4], "little")
        sequence = int.from_bytes(card[6:10], "little")
        position = int.from_bytes(card[10:14], "little")
        if (code != 69_247_929 or card[4:6] != bytes((0, 1)) or sequence >= 35
                or sequence in seen or position not in (0, 1, 2, 4, 8)
                or action.get("card_ids") != [69_247_929]
                or action.get("choice") != {"kind": "cards", "indices": [index]}
                or action.get("bytes") != _word_response(0, 1, index)):
            raise ValueError("stage_opcode15_candidates_or_response_mismatch")
        seen.add(sequence)


def validate_stage_receipt(
    receipt: dict,
    request: dict,
    context: str,
    stage: int,
    expected_identity: dict | None = None,
    spec: ScopeSpec = VALIDATION_SCOPE,
) -> list[dict]:
    """Validate one Rust receipt; return only independently authenticated auto-response tail decisions."""
    if type(stage) is not int or stage not in range(1, spec.limit + 1):
        raise ValueError("stage_number_invalid")
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("kind") != "native_tenki_placement_validation_stage"
            or receipt.get("scope") != spec.scope or receipt.get("context") != context
                or receipt.get("stage") != stage or not _strict_equal(receipt.get("request"), request)
            or receipt.get("successful") is not True
            or any(receipt.get(flag) is not False for flag in FLAGS)):
        raise ValueError("stage_receipt_binding_invalid")
    ledger = receipt.get("ledger")
    if not _strict_equal(ledger, {"consumed": stage, "completed": stage, "unknown": 0,
                                  "reserved": 0, "abandoned": 0, "limit": spec.limit}):
        raise ValueError("stage_ledger_prefix_invalid")
    if (receipt.get("diagnostic") is not None or receipt.get("assets_unchanged") is not True
            or receipt.get("assets_before") != receipt.get("assets_after")
            or (expected_identity is not None and receipt.get("assets_before") != expected_identity)
            or receipt.get("window_valid_at_result") is not True):
        raise ValueError("stage_assets_or_window_invalid")
    validation = receipt.get("validation", {}).get("Ok", {})
    if (validation.get("response_oracle_matches") is not True
            or validation.get("automatic_decisions_single_legal") is not True):
        raise ValueError("stage_response_or_auto_audit_failed")
    result = receipt.get("result", {}).get("Ok", {})
    if (result.get("status") != "decision_required" or result.get("error") is not None
            or result.get("coverage_gaps")):
        raise ValueError("stage_result_not_clean_decision_required")
    requested = request.get("decisions") if isinstance(request, dict) else None
    auto_tail = validate_auto_decisions(requested, result.get("resolved_decisions"), result.get("events"))
    prompt, raw, _event = _pending_prompt(result, _PROMPT_BY_STAGE[stage])
    if stage == 1:
        _validate_place_prompt(prompt, raw)
    elif stage == 2:
        _validate_yes_no_prompt(prompt, raw)
    elif stage in (5, 6):
        _validate_targets_prompt(prompt, raw)
    replay = receipt.get("independent_replay_matches")
    if stage in (4, 6):
        if replay is not True:
            raise ValueError("stage_independent_replay_mismatch")
    elif replay is not None:
        raise ValueError("stage_unexpected_replay_qualification")
    return auto_tail


def _validated_parent(parent: dict, stage: int, spec: ScopeSpec) -> tuple[dict, dict, list[dict]]:
    if not isinstance(parent, dict):
        raise ValueError("stage_parent_receipt_required")
    parent_stage = _PARENT_BY_STAGE.get(stage)
    if parent_stage is None:
        raise ValueError("stage_derivation_invalid")
    request = parent.get("request")
    if not isinstance(request, dict):
        raise ValueError("stage_parent_request_missing")
    context = parent.get("context")
    expected_identity = parent.get("assets_before")
    auto_tail = validate_stage_receipt(parent, request, context, parent_stage, expected_identity, spec)
    return request, parent["result"]["Ok"], auto_tail


def derive_stage_request(stage: int, parent: dict, spec: ScopeSpec = VALIDATION_SCOPE) -> dict:
    """Derive the fixed branch action from the authenticated parent's actual prompt."""
    request, result, _auto_tail = _validated_parent(parent, stage, spec)
    if stage in (4, 6):
        return copy.deepcopy(request)
    decisions = result["resolved_decisions"]
    if stage == 2:
        prompt, _raw, _event = _pending_prompt(result, 18)
        wanted = {"kind": "place", "zones": [{"player": 0, "location": 8, "sequence": 0}]}
        matches = [action for action in prompt["actions"] if action.get("choice") == wanted and action.get("bytes") == [0, 8, 0]]
        if len(matches) != 1:
            raise ValueError("stage_opcode18_zone_zero_not_unique")
    elif stage in (3, 5):
        prompt, _raw, _event = _pending_prompt(result, 13)
        _validate_yes_no_prompt(prompt, bytes([byte for byte in next(
            event["raw"] for event in result["events"] if event.get("sequence") == prompt["id"]
        )]))
        yes = stage == 5
        wanted = {"kind": "yes_no", "yes": yes}
        expected_bytes = [1, 0, 0, 0] if yes else [0, 0, 0, 0]
        matches = [action for action in prompt["actions"]
                   if action.get("choice") == wanted and action.get("bytes") == expected_bytes]
        if len(matches) != 1:
            raise ValueError("stage_opcode13_choice_not_unique")
    else:
        raise ValueError("stage_derivation_invalid")
    child = copy.deepcopy(request)
    child["decisions"] = copy.deepcopy(decisions) + [{
        "prompt_id": prompt["id"],
        "player": 0,
        "choice": copy.deepcopy(matches[0]["choice"]),
    }]
    return child


def summarize_validation(context: str, stages: list[dict], stats: dict | None, diagnostic: str | None = None,
                         spec: ScopeSpec = VALIDATION_SCOPE) -> dict:
    stats_valid = (
        isinstance(stats, dict)
        and all(type(stats.get(key)) is int and stats[key] >= 0
                for key in ("consumed", "completed", "unknown", "reserved", "abandoned", "limit"))
        and stats["limit"] == spec.limit
        and stats["consumed"] == stats["completed"] + stats["unknown"]
        and stats["abandoned"] <= stats["unknown"]
        and stats["consumed"] + stats["reserved"] <= spec.limit
    )
    ordered = isinstance(stages, list) and [item.get("stage") for item in stages] == list(range(1, len(stages) + 1))
    successful_stages = ordered and len(stages) == spec.limit and all(
        _is_successful_stage_summary(item, expected_stage, spec)
        for expected_stage, item in enumerate(stages, 1)
    )
    if not stats_valid:
        diagnostic = diagnostic or "ledger_statistics_unknown_or_invalid"
    elif stats["unknown"] or stats["reserved"] or stats["abandoned"]:
        diagnostic = diagnostic or "ledger_has_unresolved_consumption"
    success = bool(
        successful_stages and stats_valid and diagnostic is None
        and stats["consumed"] == stats["completed"] == spec.limit
        and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0
    )
    return {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_summary",
        "scope": spec.scope,
        "context": context,
        "successful": success,
        "old_consumed": spec.old_consumed,
        "new_consumed": stats.get("consumed") if isinstance(stats, dict) and type(stats.get("consumed")) is int else None,
        "cumulative_consumed": spec.old_consumed + stats["consumed"] if stats_valid else None,
        "unknown": stats.get("unknown") if isinstance(stats, dict) and type(stats.get("unknown")) is int else None,
        "ledger": copy.deepcopy(stats) if stats_valid else None,
        "stages": copy.deepcopy(stages),
        "diagnostic": diagnostic,
        **FLAGS,
    }


def validate_report(value: dict, repo: Path | None = None, spec: ScopeSpec = VALIDATION_SCOPE) -> bool:
    """Enforce local invariants in addition to the separately published JSON Schema."""
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1 or value.get("scope") != spec.scope):
        raise ValueError("validation_report_scope_or_version_invalid")
    if any(value.get(flag) is not False for flag in FLAGS):
        raise ValueError("research_qualification_must_remain_false")
    kind = value.get("kind")
    if kind not in {
        "native_tenki_placement_validation_manifest",
        "native_tenki_placement_validation_prepared",
        "native_tenki_placement_validation_preflight_failure",
        "native_tenki_placement_validation_stage",
        "native_tenki_placement_validation_stage_report",
        "native_tenki_placement_validation_summary",
        "native_tenki_placement_validation_verification",
    }:
        raise ValueError("validation_report_kind_invalid")
    if not isinstance(value.get("context"), str) or not _HASH.fullmatch(value["context"]):
        raise ValueError("validation_report_context_invalid")
    if kind.endswith("_manifest"):
        unsigned = {key: item for key, item in value.items() if key != "context"}
        request = value.get("request")
        input_sha256 = value.get("input_sha256")
        if (not isinstance(request, dict)
                or value.get("stage1_request_sha256") != digest(canonical(request))
                or value.get("request_derivation") != "frozen-tenki-activation-only-worker-path-replaced"):
            raise ValueError("validation_manifest_request_binding_invalid")
        if (not isinstance(input_sha256, dict)
                or set(input_sha256) != set(MANIFEST_INPUT_ROLES)):
            raise ValueError("validation_manifest_input_roles_invalid")
        if (type(value.get("started_at")) is not int or value["started_at"] < 0
                or type(value.get("limit")) is not int or value.get("limit") != spec.limit
                or type(value.get("planned_calls")) is not int or value.get("planned_calls") != spec.limit
                or type(value.get("wall_seconds")) is not int or value.get("wall_seconds") != spec.wall_seconds
                or type(value.get("old_consumed")) is not int or value.get("old_consumed") != spec.old_consumed
                or value.get("baseline_delivery_sha256") != spec.delivery_sha256
                or value.get("context") != digest(canonical(unsigned))
                or any(not isinstance(item, str) or not _HASH.fullmatch(item)
                       for item in input_sha256.values())):
            raise ValueError("validation_manifest_binding_invalid")
    elif kind.endswith("_prepared"):
        if (value.get("prepared") is not True or type(value.get("execution_ready")) is not bool
                or type(value.get("native_calls")) is not int or value.get("native_calls") != 0
                or type(value.get("planned_calls")) is not int or value.get("planned_calls") != spec.limit
                or any(not isinstance(value.get(key), str) or not _HASH.fullmatch(value[key])
                       for key in ("stage1_request_sha256", "preflight_diagnostic_sha256", "manifest_sha256", "stage1_input_sha256"))):
            raise ValueError("validation_prepared_binding_invalid")
    elif kind.endswith("_preflight_failure"):
        if (value.get("prepared") is not False or value.get("execution_ready") is not False
                or type(value.get("native_calls")) is not int or value.get("native_calls") != 0
                or type(value.get("stage")) is not int or value.get("stage") != 1
                or value.get("no_charged_ledger") is not True
                or not isinstance(value.get("diagnostic"), str) or not value["diagnostic"]
                or not isinstance(value.get("process_diagnostic_saved"), bool)
                or any(not isinstance(value.get(key), str) or not _HASH.fullmatch(value[key])
                       for key in ("manifest_sha256", "stage1_request_sha256",
                                   "stage1_input_sha256", "process_diagnostic_sha256"))):
            raise ValueError("validation_preflight_failure_invalid")
    elif kind == "native_tenki_placement_validation_stage":
        stage = value.get("stage")
        request = value.get("request")
        if type(stage) is not int:
            raise ValueError("validation_runner_receipt_stage_invalid")
        _verify_basic_receipt(value, request, value["context"], stage, spec)
        if value.get("successful") is True:
            validate_stage_receipt(value, request, value["context"], stage,
                                   value.get("assets_before"), spec)
    elif kind == "native_tenki_placement_validation_stage_report":
        if (type(value.get("stage")) is not int or value["stage"] not in range(1, spec.limit + 1)
                or type(value.get("successful")) is not bool
                or (value.get("native_calls") is not None
                    and (type(value.get("native_calls")) is not int or value.get("native_calls") not in (0, 1)))
                or not isinstance(value.get("diagnostic_sha256"), str) or not _HASH.fullmatch(value["diagnostic_sha256"])
                or (value.get("receipt_sha256") is not None and (not isinstance(value["receipt_sha256"], str) or not _HASH.fullmatch(value["receipt_sha256"])))):
            raise ValueError("validation_stage_report_invalid")
        if value.get("successful") is True:
            if (value.get("receipt_sha256") is None or value.get("native_calls") != 1
                    or value.get("ledger") is None or value.get("diagnostic") is not None):
                raise ValueError("validation_successful_stage_incomplete")
            _validate_success_ledger_prefix(value["ledger"], value["stage"], spec)
        replay = value.get("independent_replay_matches")
        if value["stage"] in (4, 6):
            if value.get("successful") is True and replay is not True:
                raise ValueError("validation_stage_replay_flag_invalid")
            if value.get("successful") is not True and replay not in (None, False):
                raise ValueError("validation_stage_replay_flag_invalid")
        elif replay is not None:
            raise ValueError("validation_stage_replay_flag_invalid")
    elif kind.endswith("_summary"):
        stages = value.get("stages")
        expected_fields = {
            "schema_version", "kind", "scope", "context", *FLAGS,
            "successful", "old_consumed", "new_consumed", "cumulative_consumed",
            "unknown", "ledger", "stages", "diagnostic",
        }
        if set(value) != expected_fields:
            raise ValueError("validation_summary_fields_invalid")
        if (type(value.get("successful")) is not bool or not isinstance(stages, list)
                or len(stages) > spec.limit
                or [item.get("stage") if isinstance(item, dict) else None for item in stages]
                   != list(range(1, len(stages) + 1))):
            raise ValueError("validation_summary_stage_prefix_invalid")
        if type(value.get("old_consumed")) is not int or value.get("old_consumed") != spec.old_consumed:
            raise ValueError("validation_summary_historical_count_invalid")
        if value.get("diagnostic") is not None and not isinstance(value.get("diagnostic"), str):
            raise ValueError("validation_summary_diagnostic_invalid")
        for stage_summary in stages:
            _validate_stage_summary(stage_summary, spec)
        ledger = value.get("ledger")
        if ledger is None:
            if any(value.get(key) is not None for key in ("new_consumed", "cumulative_consumed", "unknown")):
                raise ValueError("validation_summary_unknown_statistics_mismatch")
        elif (not _valid_stats(ledger, spec)
              or type(value.get("new_consumed")) is not int
              or value.get("new_consumed") != ledger["consumed"]
              or type(value.get("cumulative_consumed")) is not int
              or value.get("cumulative_consumed") != spec.old_consumed + ledger["consumed"]
              or type(value.get("unknown")) is not int
              or value.get("unknown") != ledger["unknown"]):
            raise ValueError("validation_summary_statistics_incoherent")
        if value.get("successful") is True:
            expected_stats = {"consumed": spec.limit, "completed": spec.limit,
                              "unknown": 0, "reserved": 0, "abandoned": 0,
                              "limit": spec.limit}
            if (len(stages) != spec.limit
                    or type(value.get("new_consumed")) is not int or value.get("new_consumed") != spec.limit
                    or type(value.get("cumulative_consumed")) is not int or value.get("cumulative_consumed") != spec.old_consumed + spec.limit
                    or type(value.get("unknown")) is not int or value.get("unknown") != 0
                    or value.get("ledger") != expected_stats
                    or value.get("diagnostic") is not None
                    or not all(_is_successful_stage_summary(item, expected_stage, spec)
                               for expected_stage, item in enumerate(stages, 1))):
                raise ValueError("validation_summary_success_not_proven")
    elif kind.endswith("_verification"):
        expected_fields = {
            "schema_version", "kind", "scope", "context", *FLAGS,
            "valid", "native_calls", "old_consumed", "new_consumed",
            "cumulative_consumed", "unknown", "ledger", "stages",
            "prepared_sha256", "verification_diagnostic_sha256", "diagnostic",
        }
        if (set(value) != expected_fields
                or type(value.get("native_calls")) is not int or value.get("native_calls") != 0
                or type(value.get("valid")) is not bool
                or type(value.get("old_consumed")) is not int or value.get("old_consumed") != spec.old_consumed
                or not isinstance(value.get("prepared_sha256"), str)
                or not _HASH.fullmatch(value["prepared_sha256"])
                or not isinstance(value.get("verification_diagnostic_sha256"), list)
                or len(value["verification_diagnostic_sha256"]) > spec.limit
                or any(not isinstance(item, str) or not _HASH.fullmatch(item)
                       for item in value["verification_diagnostic_sha256"])
                or not isinstance(value.get("stages"), list)
                or len(value["stages"]) > spec.limit
                or [item.get("stage") if isinstance(item, dict) else None for item in value["stages"]]
                   != list(range(1, len(value["stages"]) + 1))):
            raise ValueError("validation_verification_invalid")
        if value.get("diagnostic") is not None and not isinstance(value.get("diagnostic"), str):
            raise ValueError("validation_verification_diagnostic_invalid")
        for stage_summary in value["stages"]:
            _validate_stage_summary(stage_summary, spec)
        ledger = value.get("ledger")
        if ledger is None:
            if any(value.get(key) is not None for key in ("new_consumed", "cumulative_consumed", "unknown")):
                raise ValueError("validation_verification_unknown_statistics_mismatch")
        elif (not _valid_stats(ledger, spec)
              or type(value.get("new_consumed")) is not int
              or value.get("new_consumed") != ledger["consumed"]
              or type(value.get("cumulative_consumed")) is not int
              or value.get("cumulative_consumed") != spec.old_consumed + ledger["consumed"]
              or type(value.get("unknown")) is not int
              or value.get("unknown") != ledger["unknown"]
              or any(item.get("ledger") is not None
                     and item["ledger"]["consumed"] > ledger["consumed"]
                     for item in value["stages"])):
            raise ValueError("validation_verification_statistics_incoherent")
        if value.get("valid") is True:
            expected_ledger = {"consumed": spec.limit, "completed": spec.limit,
                               "unknown": 0, "reserved": 0, "abandoned": 0,
                               "limit": spec.limit}
            if (len(value["stages"]) != spec.limit
                    or not all(_is_successful_stage_summary(item, number, spec)
                               for number, item in enumerate(value["stages"], 1))
                    or not _strict_equal(ledger, expected_ledger)
                    or value.get("new_consumed") != spec.limit
                    or value.get("cumulative_consumed") != spec.old_consumed + spec.limit
                    or value.get("unknown") != 0
                    or value.get("diagnostic") is not None
                    or len(value["verification_diagnostic_sha256"]) != spec.limit):
                raise ValueError("validation_verification_success_not_proven")
        elif not isinstance(value.get("diagnostic"), str) or not value["diagnostic"]:
            raise ValueError("validation_invalid_verification_requires_diagnostic")
    return True


def _validate_success_ledger_prefix(ledger: Any, stage: int,
                                    spec: ScopeSpec) -> None:
    expected = {"consumed": stage, "completed": stage, "unknown": 0,
                "reserved": 0, "abandoned": 0, "limit": spec.limit}
    if not _strict_equal(ledger, expected):
        raise ValueError("validation_successful_stage_ledger_invalid")


def _is_successful_stage_summary(value: Any, stage: int,
                                 spec: ScopeSpec) -> bool:
    return (
        isinstance(value, dict)
        and type(value.get("stage")) is int and value.get("stage") == stage
        and value.get("successful") is True
        and type(value.get("native_calls")) is int and value.get("native_calls") == 1
        and isinstance(value.get("receipt_sha256"), str) and _HASH.fullmatch(value["receipt_sha256"])
        and isinstance(value.get("diagnostic_sha256"), str) and _HASH.fullmatch(value["diagnostic_sha256"])
        and value.get("diagnostic") is None
        and value.get("independent_replay_matches") is (True if stage in (4, 6) else None)
        and _strict_equal(value.get("ledger"), {
            "consumed": stage, "completed": stage, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": spec.limit,
        })
    )


def _validate_stage_summary(value: Any, spec: ScopeSpec) -> None:
    expected_fields = {
        "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
        "diagnostic_sha256", "independent_replay_matches", "ledger",
    }
    if (not isinstance(value, dict) or set(value) != expected_fields
            or type(value.get("stage")) is not int
            or value["stage"] not in range(1, spec.limit + 1)
            or type(value.get("successful")) is not bool
            or (value.get("native_calls") is not None
                and (type(value["native_calls"]) is not int or value["native_calls"] not in (0, 1)))
            or (value.get("diagnostic") is not None and not isinstance(value.get("diagnostic"), str))
            or not isinstance(value.get("diagnostic_sha256"), str)
            or not _HASH.fullmatch(value["diagnostic_sha256"])
            or (value.get("receipt_sha256") is not None
                and (not isinstance(value["receipt_sha256"], str)
                     or not _HASH.fullmatch(value["receipt_sha256"])) )):
        raise ValueError("validation_stage_summary_invalid")
    stage = value["stage"]
    replay = value.get("independent_replay_matches")
    if stage in (4, 6):
        if value["successful"] is True and replay is not True:
            raise ValueError("validation_stage_summary_replay_invalid")
        if value["successful"] is not True and replay not in (None, False):
            raise ValueError("validation_stage_summary_replay_invalid")
    elif replay is not None:
        raise ValueError("validation_stage_summary_replay_invalid")
    ledger = value.get("ledger")
    if value["successful"] is True:
        if (value.get("native_calls") != 1 or value.get("diagnostic") is not None
                or value.get("receipt_sha256") is None or ledger is None):
            raise ValueError("validation_successful_stage_incomplete")
        _validate_success_ledger_prefix(ledger, stage, spec)
    elif ledger is not None:
        if not _valid_stats(ledger, spec) or ledger.get("consumed", spec.limit + 1) > stage:
            raise ValueError("validation_stage_summary_ledger_invalid")


def _stage_invocation(context: str, output: Path, stage: int, request: dict,
                      expected_identity: dict, started_at: int,
                      spec: ScopeSpec = VALIDATION_SCOPE) -> dict:
    receipt = output / f"stage-{stage}.json"
    return {
        "context": context,
        "ledger": str(output / "calls.jsonl"),
        "output": str(receipt),
        "stage": stage,
        "request": copy.deepcopy(request),
        "expected_identity": copy.deepcopy(expected_identity),
        "started_at": started_at,
        "batch_kind": spec.batch_kind,
    }


def _save_stage_files(output: Path, context: str, stage: int, request: dict,
                      expected_identity: dict, started_at: int,
                      spec: ScopeSpec = VALIDATION_SCOPE) -> tuple[Path, Path]:
    invocation = _stage_invocation(context, output, stage, request,
                                   expected_identity, started_at, spec)
    request_path = output / f"stage-{stage}-request.json"
    input_path = output / f"stage-{stage}-input.json"
    input_bytes = canonical(invocation)
    immutable_write(request_path, request)
    immutable_write(input_path, invocation)
    immutable_write(output / f"stage-{stage}-input-seal.json", {
        "schema_version": 1,
        "kind": spec.input_seal_kind,
        "context": context,
        "stage": stage,
        "input_sha256": _sha(input_bytes),
    })
    return input_path, request_path


def _verify_stage_intent(input_path: Path, output: Path, context: str,
                         stage: int, request: dict, expected_identity: dict,
                         started_at: int, spec: ScopeSpec = VALIDATION_SCOPE) -> None:
    input_bytes = input_path.read_bytes()
    seal = strict_json((output / f"stage-{stage}-input-seal.json").read_bytes())
    if (strict_json(input_bytes) != _stage_invocation(context, output, stage,
                                                      request, expected_identity,
                                                      started_at, spec)
            or seal != {
                "schema_version": 1,
                "kind": spec.input_seal_kind,
                "context": context,
                "stage": stage,
                "input_sha256": _sha(input_bytes),
            }):
        raise ValueError("validation_stage_intent_binding_invalid")


def _diagnostic_hash(root: Path, record: dict,
                     spec: ScopeSpec = VALIDATION_SCOPE) -> str:
    return process_diagnostic_sha256(
        root, record,
        runner_role=spec.runner_role,
        safe_file=safe_path,
        strict_json=strict_json,
    )


def _run_process(runner: Path, input_path: Path, repo: Path, root: Path,
                 mode: str, *, prepared_hash: str | None = None,
                 timeout: float | None = None,
                 process_runner: Callable[..., Any] | None = None,
                 spec: ScopeSpec = VALIDATION_SCOPE):
    record, completed = capture_runner_process(
        runner=runner,
        input_path=input_path,
        repo=repo,
        root=root,
        mode=mode,
        runner_role=spec.runner_role,
        input_sha256=_sha(safe_path(input_path).read_bytes()),
        prepared_hash=prepared_hash,
        timeout=timeout if timeout is not None else 75,
        trace_stderr=True,
        process_runner=process_runner,
    )
    return record, completed, _diagnostic_hash(root, record, spec)


def _process_exit_succeeded(completed: Any) -> bool:
    return completed is not None and getattr(completed, "returncode", None) == 0


def _valid_stats(value: Any, spec: ScopeSpec = VALIDATION_SCOPE) -> bool:
    return (
        isinstance(value, dict)
        and all(type(value.get(key)) is int and value[key] >= 0 for key in (
            "consumed", "completed", "unknown", "reserved", "abandoned", "limit"
        ))
        and value.get("limit") == spec.limit
        and value["consumed"] == value["completed"] + value["unknown"]
        and value["abandoned"] <= value["unknown"]
        and value["consumed"] + value["reserved"] <= spec.limit
    )


def _stats_for_missing_ledger(*, normal_attempted: bool,
                              spec: ScopeSpec = VALIDATION_SCOPE) -> dict | None:
    if normal_attempted:
        return None
    return {"consumed": 0, "completed": 0, "unknown": 0, "reserved": 0,
            "abandoned": 0, "limit": spec.limit}


def _read_runner_stats(runner: Path, input_path: Path, repo: Path,
                       root: Path, *, process_runner: Callable[..., Any] | None = None,
                       spec: ScopeSpec = VALIDATION_SCOPE) -> tuple[dict | None, dict, str]:
    process, completed, diagnostic_sha = _run_process(
        runner, input_path, repo, root, "stats", process_runner=process_runner,
        spec=spec,
    )
    stats = None
    if process.get("status") == "completed" and _process_exit_succeeded(completed):
        try:
            value = strict_json(completed.stdout)
            if (isinstance(value, dict) and value.get("native_calls") == 0
                    and isinstance(value.get("ledger"), dict)):
                stats = value["ledger"]
        except (ValueError, UnicodeDecodeError, TypeError):
            stats = None
    return stats, process, diagnostic_sha


def _verify_basic_receipt(receipt: dict, request: dict, context: str,
                          stage: int, spec: ScopeSpec = VALIDATION_SCOPE) -> None:
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("kind") != "native_tenki_placement_validation_stage"
            or receipt.get("scope") != spec.scope
            or receipt.get("context") != context
            or type(receipt.get("stage")) is not int or receipt.get("stage") != stage
            or not _strict_equal(receipt.get("request"), request)
            or type(receipt.get("successful")) is not bool
            or any(receipt.get(flag) is not False for flag in FLAGS)):
        raise ValueError("validation_stage_receipt_binding_invalid")
    if not _valid_stats(receipt.get("ledger"), spec) or receipt["ledger"].get("consumed", 0) > stage:
        raise ValueError("validation_stage_receipt_ledger_invalid")


def _stage_report(context: str, stage: int, receipt: dict | None,
                  receipt_path: Path, diagnostic_sha: str,
                  native_calls: int | None, reason: str | None,
                  fallback_ledger: dict | None = None,
                  spec: ScopeSpec = VALIDATION_SCOPE) -> dict:
    receipt_sha = _sha(safe_path(receipt_path).read_bytes()) if receipt_path.is_file() else None
    replay = None
    if stage in (4, 6) and isinstance(receipt, dict):
        replay = receipt.get("independent_replay_matches")
    return {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_stage_report",
        "scope": spec.scope,
        "context": context,
        "stage": stage,
        "successful": bool(receipt and receipt.get("successful") is True and reason is None),
        "native_calls": native_calls,
        "diagnostic": reason,
        "receipt_sha256": receipt_sha,
        "diagnostic_sha256": diagnostic_sha,
        "independent_replay_matches": replay if type(replay) is bool else None,
        "ledger": receipt.get("ledger") if isinstance(receipt, dict) else fallback_ledger,
        **FLAGS,
    }


def _save_orchestration_diagnostic(output: Path, stage: int,
                                   reason: str,
                                   spec: ScopeSpec = VALIDATION_SCOPE) -> str:
    path = output / f"stage-{stage}-orchestration-diagnostic.json"
    immutable_write(path, {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_orchestration_diagnostic",
        "scope": spec.scope,
        "stage": stage,
        "diagnostic": reason,
    })
    return _sha(safe_path(path).read_bytes())


def _run_six_stages(*, root: Path, output: Path, runner: Path, repo: Path,
                    manifest: dict, prepared_hash: str, stage1_request: dict,
                    expected_identity: dict, source: dict,
                    protected: dict[Path, str], frozen_files: dict[Path, str],
                    process_runner: Callable[..., Any] | None = None,
                    spec: ScopeSpec = VALIDATION_SCOPE,
                    clock: Callable[[], float] = time.time) -> dict:
    def verify_intent(input_path, stage, request, identity, started_at):
        _verify_stage_intent(input_path, output, manifest["context"],
                              stage, request, identity, started_at, spec)

    def run_process(runner_path, input_path, repo_path, root_path, mode,
                    *, prepared_hash=None, timeout=None):
        return _run_process(
            runner_path, input_path, repo_path, root_path, mode,
            prepared_hash=prepared_hash, timeout=timeout,
            process_runner=process_runner, spec=spec,
        )

    def read_stats(input_path):
        return _read_runner_stats(runner, input_path, repo, root,
                                  process_runner=process_runner, spec=spec)

    def assert_unchanged(repo_path, captured_source, protected_files):
        if stable_source(repo_path) != captured_source:
            raise ValueError("workspace_source_changed")
        for path, expected in protected_files.items():
            if _sha(safe_path(path).read_bytes()) != expected:
                raise ValueError("historical_protected_input_changed")

    return run_six_stage_workflow(
        spec=WORKFLOW_SPEC if spec == VALIDATION_SCOPE else WorkflowSpec(
            scope=spec.scope, limit=spec.limit, wall_seconds=spec.wall_seconds,
            worker_timeout_seconds=30, runner_role=spec.runner_role,
            stage_kind="native_tenki_placement_validation_stage",
            stage_report_kind="native_tenki_placement_validation_stage_report",
            input_seal_kind=spec.input_seal_kind, trace_stderr=True,
            timeout_error_prefix="validation",
        ),
        root=root, output=output, runner=runner, repo=repo,
        manifest=manifest, prepared_hash=prepared_hash,
        stage1_request=stage1_request, expected_identity=expected_identity,
        source=source, protected=protected, frozen_files=frozen_files,
        parent_stage=_PARENT_BY_STAGE,
        derive_request=lambda stage, parent: derive_stage_request(stage, parent, spec),
        save_stage_files=lambda *args: _save_stage_files(*args, spec=spec),
        invocation_for_stage=lambda context, out, stage, request, identity, started:
            _stage_invocation(context, out, stage, request, identity, started, spec),
        verify_stage_intent=verify_intent,
        read_receipt=lambda path: strict_json(safe_path(path).read_bytes()) if path.exists() else None,
        run_process=run_process,
        read_stats=read_stats,
        valid_stats=lambda value: _valid_stats(value, spec),
        missing_ledger_stats=lambda *, normal_attempted:
            _stats_for_missing_ledger(normal_attempted=normal_attempted, spec=spec),
        verify_basic_receipt=lambda receipt, request, context, stage:
            _verify_basic_receipt(receipt, request, context, stage, spec),
        validate_stage_receipt=lambda receipt, request, context, stage, identity:
            validate_stage_receipt(receipt, request, context, stage, identity, spec),
        stage_report=lambda *args: _stage_report(*args, spec=spec),
        validate_report=lambda value, _repo: validate_report(value, spec=spec),
        summarize=lambda context, stages, stats, diagnostic:
            summarize_validation(context, stages, stats, diagnostic, spec),
        diagnostic_hash=lambda root_path, record: _diagnostic_hash(root_path, record, spec),
        save_orchestration_diagnostic=lambda out, stage, reason:
            _save_orchestration_diagnostic(out, stage, reason, spec),
        assert_unchanged=assert_unchanged,
        safe_file=safe_path,
        immutable_write=immutable_write,
        sha256=_sha,
        process_exit_succeeded=_process_exit_succeeded,
        strict_json=strict_json,
        clock=clock,
    )


def _normal_runner_timeout(manifest: dict, *, now: float | None = None, spec: ScopeSpec = VALIDATION_SCOPE) -> float:
    started = manifest.get("started_at") if isinstance(manifest, dict) else None
    return normal_runner_timeout(
        started,
        wall_seconds=spec.wall_seconds,
        worker_timeout_seconds=30,
        now=now,
        error_prefix="validation",
    )


def _resolve_delivery_path(delivery_path: Path, reference: str,
                           boundary_root: Path) -> Path:
    """Resolve a delivery-relative file reference without escaping its baseline."""
    if not isinstance(reference, str) or not reference:
        raise ValueError("validation_delivery_reference_invalid")
    relative = Path(reference)
    if relative.is_absolute():
        raise ValueError("validation_delivery_reference_absolute")
    boundary = Path(os.path.abspath(boundary_root))
    resolved = Path(os.path.abspath(delivery_path.parent / relative))
    if resolved == boundary or not resolved.is_relative_to(boundary):
        raise ValueError("validation_delivery_reference_outside_root")
    return resolved


def _fixed_validation_paths(args: argparse.Namespace, repo: Path,
                            spec: ScopeSpec) -> tuple[Path, Path, dict[str, Path]]:
    root = repo / spec.output_root
    baseline = Path(os.path.abspath(args.baseline_dir))
    if baseline != repo / spec.baseline_root:
        raise ValueError("validation_fixed_baseline_required")
    expected = {
        "runner": root / "native-artifacts" / "tenki-placement-probe.exe",
        "worker": root / "native-artifacts" / "ygo-engine-worker.exe",
        "build_record": root / "build-record.json",
        "identity": root / "identity.json",
        "window_start": root / "window-start.json",
    }
    actual = {key: Path(os.path.abspath(getattr(args, key))) for key in expected}
    for key, path in expected.items():
        if actual[key] != path:
            raise ValueError(f"validation_fixed_{key}_path_required")
    output = Path(os.path.abspath(args.output))
    if output != root / "research":
        raise ValueError("validation_fixed_output_path_required")
    for path in (root, output):
        if path.is_symlink():
            raise ValueError("validation_linked_output_rejected")
    if output.is_relative_to(root) is False:
        raise ValueError("validation_output_outside_scope")
    return root, output, actual


def _verify_validation_baseline(repo: Path, baseline_dir: Path,
                                spec: ScopeSpec,
                                protection_scope: str | None = None, *,
                                _sources: Any | None = None) -> tuple[dict, dict[Path, str]]:
    """Recompute the pinned repair delivery and the complete eight-ledger history."""
    from ygo_eval.tenki_confirmation_runner_audit import (
        EXPERIMENT_RELATIVE as confirmation_relative,
        _verify_confirmation_baseline,
        validate_report as validate_runner_audit,
    )
    from ygo_eval.tenki_placement_diagnostics import _verify_archive
    from ygo_eval.native_tenki_placement import _validate_signed

    def source_file_pin(path: Path, fallback: str) -> str:
        return _sources.file_sha256(path.as_posix()) if _sources is not None else fallback

    def source_count_pin(name: str, fallback: int) -> int:
        return _sources.dataset_count(name) if _sources is not None else fallback

    baseline = Path(os.path.abspath(baseline_dir))
    if baseline != repo / spec.baseline_root or baseline.is_symlink():
        raise ValueError("validation_fixed_baseline_required")
    before = stable_source(repo)
    # This verifier rechecks the earlier confirmation delivery, all seven prior
    # ledgers plus the eighth zero-consumption confirmation ledger, and their
    # immutable inputs without running a worker or opening a writable journal.
    prior = _verify_confirmation_baseline(
        repo, repo / confirmation_relative, protection_scope,
        _sources=(
            _sources.child("runner_confirmation") if _sources is not None else None
        ),
    )
    protected = dict(prior["protected"])
    delivery_path = baseline / "final-build" / "delivery.json"
    delivery_raw = safe_path(delivery_path).read_bytes()
    delivery_sha256 = source_file_pin(
        spec.baseline_root / "final-build" / "delivery.json", spec.delivery_sha256,
    )
    if _sha(delivery_raw) != delivery_sha256:
        raise ValueError("validation_baseline_delivery_anchor_mismatch")
    delivery = strict_json(delivery_raw)
    unsigned = {key: item for key, item in delivery.items() if key != "identity"}
    historical_consumed = source_count_pin("validation_historical_consumed", spec.old_consumed)
    historical_unknown = source_count_pin("validation_historical_unknown", 0)
    historical_ledgers = source_count_pin("validation_historical_ledgers", 7)
    if (historical_consumed != spec.old_consumed or historical_unknown != 0
            or historical_ledgers != 7):
        raise ValueError("validation_historical_source_count_mismatch")
    if (delivery.get("schema_version") != 1
            or delivery.get("kind") != "tenki_runner_repair_final_delivery"
            or delivery.get("status") != "completed_offline_audit"
            or delivery.get("identity") != digest(canonical(unsigned))
            or delivery.get("historical_consumed") != historical_consumed
            or delivery.get("historical_unknown") != historical_unknown
            or delivery.get("native_calls") != 0
            or delivery.get("original_confirmation_result") != "runner_timeout"
            or delivery.get("confirmation_scope_consumed") != 0
            or delivery.get("proof_ready") is not False
            or delivery.get("complete_action_coverage") is not False
            or delivery.get("global_optimality") is not False
            or delivery.get("native_probability_verified") is not False):
        raise ValueError("validation_baseline_delivery_content_mismatch")
    source = delivery.get("source")
    final_build = delivery.get("final_build")
    if not isinstance(source, dict) or not isinstance(final_build, dict):
        raise ValueError("validation_baseline_build_binding_missing")
    if _sources is None:
        archive_expected = {
            "archive": source.get("archive"),
            "file_list": source.get("file_list"),
            "archive_sha256": source.get("archive_sha256"),
            "file_list_sha256": source.get("file_list_sha256"),
            "source_identity": source.get("identity"),
            "file_count": source.get("file_count"),
        }
    else:
        archive_pin = _sources.archive("validation_final_archive")
        archive_prefix = (spec.baseline_root / "final-build").as_posix().rstrip("/") + "/"
        if (not archive_pin.archive_path.startswith(archive_prefix)
                or not archive_pin.file_list_path.startswith(archive_prefix)):
            raise ValueError("validation_source_archive_path_mismatch")
        archive_expected = {
            "archive": archive_pin.archive_path[len(archive_prefix):],
            "file_list": archive_pin.file_list_path[len(archive_prefix):],
            "archive_sha256": archive_pin.archive_sha256,
            "file_list_sha256": archive_pin.file_list_sha256,
            "source_identity": archive_pin.source_identity,
            "file_count": archive_pin.file_count,
        }
        source_archive_binding = {
            "archive": source.get("archive"),
            "file_list": source.get("file_list"),
            "archive_sha256": source.get("archive_sha256"),
            "file_list_sha256": source.get("file_list_sha256"),
            "source_identity": source.get("identity"),
            "file_count": source.get("file_count"),
        }
        if source_archive_binding != archive_expected:
            raise ValueError("validation_source_archive_binding_mismatch")
    archive_audit = _verify_archive(
        baseline / "final-build", archive_expected["archive"], archive_expected["file_list"],
        archive_expected["archive_sha256"], archive_expected["file_list_sha256"],
        archive_expected["source_identity"], archive_expected["file_count"],
    )
    identity_path = baseline / "final-build" / source.get("identity_file", "source-identity.json")
    identity_raw = safe_path(identity_path).read_bytes()
    identity_file_sha256 = source_file_pin(
        spec.baseline_root / "final-build" / source.get("identity_file", "source-identity.json"),
        source.get("identity_file_sha256"),
    )
    if (_sha(identity_raw) != identity_file_sha256
            or strict_json(identity_raw).get("identity") != source.get("identity")):
        raise ValueError("validation_baseline_source_identity_mismatch")
    build_path = baseline / "final-build" / final_build.get("record", "build-record.json")
    build_raw = safe_path(build_path).read_bytes()
    build_record_sha256 = source_file_pin(
        spec.baseline_root / "final-build" / final_build.get("record", "build-record.json"),
        final_build.get("record_sha256"),
    )
    build = strict_json(build_raw)
    _validate_signed(build, "build_record")
    source_before = build.get("source_before")
    source_after = build.get("source_after")
    if (_sha(build_raw) != build_record_sha256
            or build.get("identity") != final_build.get("identity")
            or build.get("status") != "recorded"
            or build.get("reproducible_build_proven") is not False
            or not isinstance(source_before, dict)
            or not isinstance(source_after, dict)
            or source_before != source_after
            or source_before.get("identity") != source.get("identity")
            or source_after.get("identity") != source.get("identity")
            or not isinstance(source_before.get("files"), dict)
            or len(source_before["files"]) != source.get("file_count")):
        raise ValueError("validation_baseline_build_record_mismatch")
    runner = baseline / "final-build" / final_build.get("runner", {}).get("path", "")
    runner_raw = safe_path(runner).read_bytes()
    runner_info = final_build.get("runner", {})
    runner_sha256 = source_file_pin(
        spec.baseline_root / "final-build" / final_build.get("runner", {}).get("path", ""),
        runner_info.get("sha256"),
    )
    if (_sha(runner_raw) != runner_sha256
            or len(runner_raw) != runner_info.get("bytes")
            or build.get("artifacts", {}).get("runner") != runner_info.get("sha256")):
        raise ValueError("validation_baseline_runner_hash_mismatch")
    audit_path = _resolve_delivery_path(
        delivery_path, delivery.get("audit_report", {}).get("path"), baseline,
    )
    audit_raw = safe_path(audit_path).read_bytes()
    audit_hash = source_file_pin(
        audit_path.relative_to(repo), delivery.get("audit_report", {}).get("sha256"),
    )
    if _sha(audit_raw) != audit_hash:
        raise ValueError("validation_baseline_audit_report_hash_mismatch")
    audit = strict_json(audit_raw)
    validate_runner_audit(audit, repo, baseline)
    if (audit.get("status") != "passed"
            or audit.get("native_calls") != 0
            or audit.get("execution_ready") is not False
            or audit.get("source", {}).get("historical_consumed") != historical_consumed
            or audit.get("source", {}).get("historical_unknown") != historical_unknown):
        raise ValueError("validation_baseline_audit_report_not_passed")
    for path, raw in ((delivery_path, delivery_raw), (identity_path, identity_raw),
                      (build_path, build_raw), (runner, runner_raw),
                      (audit_path, audit_raw),
                      (baseline / "final-build" / source["archive"], None),
                      (baseline / "final-build" / source["file_list"], None)):
        protected[Path(os.path.abspath(path))] = _sha(raw) if raw is not None else _sha(safe_path(path).read_bytes())
    protected.update({
        Path(os.path.abspath(baseline / "final-build" / source["archive"])): archive_audit["archive_sha256"],
        Path(os.path.abspath(baseline / "final-build" / source["file_list"])): archive_audit["file_list_sha256"],
    })
    if stable_source(repo) != before:
        raise ValueError("validation_workspace_changed_during_baseline_audit")
    for path, expected in protected.items():
        if _sha(safe_path(path).read_bytes()) != expected:
            raise ValueError("validation_protected_history_changed")
    return {"delivery": delivery, "audit": audit, "audit_sha256": audit_hash, "prior": prior,
            "archive": archive_audit}, protected


def _validation_window(path: Path, spec: ScopeSpec) -> dict:
    if path.name != "window-start.json":
        raise ValueError("validation_fixed_window_path_required")
    now = int(time.time())
    if path.exists():
        value = strict_json(safe_path(path).read_bytes())
        if (value.get("schema_version") != 1
                or value.get("kind") != "tenki_placement_validation_window_start"
                or value.get("scope") != spec.scope
                or value.get("limit") != spec.limit
                or value.get("wall_seconds") != spec.wall_seconds
                or type(value.get("started_at")) is not int
                or value["started_at"] < 0 or value["started_at"] > now):
            raise ValueError("validation_window_start_mismatch")
        return value
    value = {"schema_version": 1,
             "kind": "tenki_placement_validation_window_start",
             "scope": spec.scope, "limit": spec.limit,
             "wall_seconds": spec.wall_seconds, "started_at": now}
    immutable_write(path, value)
    return value


def _verify_frozen_stage1_request(repo: Path, root: Path, manifest: dict,
                                 spec: ScopeSpec, *, _sources: Any | None = None) -> None:
    """Re-derive stage 1 from pinned public history without scanning live assets."""
    from ygo_eval.native_tenki_placement import (
        OLD_STAGE1_SHA256,
        OLD_STAGE2_REQUEST_SHA256,
        PREPARATION_RELATIVE,
        PREPARATION_SHA256,
        _activation_from_history,
        _read,
    )
    from ygo_eval.native_tenki_placement_confirmation import (
        PROMPT_BASELINE_RELATIVE,
    )

    prompt_root = repo / PROMPT_BASELINE_RELATIVE
    stage1_path = prompt_root / "research" / "stage-1.json"
    stage2_path = prompt_root / "research" / "stage-2-request.json"
    preparation_path = repo / PREPARATION_RELATIVE
    if _sources is None:
        stage1_pin = OLD_STAGE1_SHA256
        stage2_pin = OLD_STAGE2_REQUEST_SHA256
        preparation_pin = PREPARATION_SHA256
    else:
        # The private immutable source description may supply synthetic pins
        # for the E2E verifier. The public production path never accepts a
        # caller-provided profile and continues to use the literal anchors.
        stage1_pin = _sources.file_sha256(stage1_path.relative_to(repo).as_posix())
        stage2_pin = _sources.file_sha256(stage2_path.relative_to(repo).as_posix())
        preparation_pin = _sources.file_sha256(preparation_path.relative_to(repo).as_posix())
    stage1_raw, stage1_hash = _read(stage1_path, stage1_pin)
    stage2_raw, stage2_hash = _read(stage2_path, stage2_pin)
    preparation_raw, preparation_hash = _read(preparation_path, preparation_pin)
    preparation = strict_json(preparation_raw)
    candidates = [
        item for item in preparation.get("candidates", [])
        if isinstance(item, dict)
        and isinstance(item.get("case"), dict)
        and item["case"].get("case_id") == "prompt-13-tenki-v1"
    ]
    if len(candidates) != 1:
        raise ValueError("validation_frozen_tenki_case_missing")
    # Bind the small frozen rules file by bytes only. Do not parse the CDB,
    # validate card sources, or rescan the runtime assets from verify-only.
    banlist_raw = safe_path(repo / "data" / "runtime" / "banlist.json").read_bytes()
    banlist_hash = _sha(banlist_raw)
    case_banlist_hash = candidates[0]["case"].get("rules", {}).get("banlist_sha256")
    if (case_banlist_hash != banlist_hash
            or manifest.get("input_sha256", {}).get("banlist") != banlist_hash):
        raise ValueError("validation_frozen_banlist_source_mismatch")
    expected_request = _activation_from_history(
        strict_json(stage1_raw), strict_json(stage2_raw),
    )
    worker = root / "native-artifacts" / "ygo-engine-worker.exe"
    expected_request["engine"]["worker_path"] = str(worker)
    if (expected_request.get("protocol_version") != 2
            or expected_request.get("probe_only") is not False
            or expected_request.get("scenario") is not None
            or expected_request.get("interruption") is not None
            or expected_request.get("first_turn") is not None
            or expected_request.get("research_capture") is not None):
        raise ValueError("validation_frozen_protocol2_request_required")
    if not _strict_equal(manifest.get("request"), expected_request):
        raise ValueError("validation_frozen_stage1_request_mismatch")
    expected_input_hashes = {
        "preparation": preparation_hash,
        "prompt_source_stage1": stage1_hash,
        "prompt_source_stage2_request": stage2_hash,
        "baseline_delivery": spec.delivery_sha256,
    }
    if any(manifest.get("input_sha256", {}).get(role) != value
           for role, value in expected_input_hashes.items()):
        raise ValueError("validation_frozen_stage1_sources_mismatch")


def _read_validation_prepared(output: Path, root: Path, manifest: dict,
                              repo: Path, spec: ScopeSpec) -> tuple[dict, str]:
    prepared_path = safe_path(output / "prepared.json")
    raw = prepared_path.read_bytes()
    prepared = strict_json(raw)
    validate_report(prepared, spec=spec)
    _verify_frozen_stage1_request(repo, root, manifest, spec)
    manifest_raw = safe_path(output / "manifest.json").read_bytes()
    stage1_raw = safe_path(output / "stage-1-input.json").read_bytes()
    request_raw = safe_path(output / "stage-1-request.json").read_bytes()
    saved_request = strict_json(request_raw)
    stage1_invocation = strict_json(stage1_raw)
    if (not _strict_equal(saved_request, manifest.get("request"))
            or not _strict_equal(stage1_invocation.get("request"), manifest.get("request"))):
        raise ValueError("validation_saved_stage1_request_mismatch")
    _verify_stage_intent(
        output / "stage-1-input.json", output, manifest["context"], 1,
        manifest["request"], manifest["assets"]["ordinary"],
        manifest["started_at"], spec,
    )
    if (prepared.get("context") != manifest.get("context")
            or prepared.get("execution_ready") is not True
            or prepared.get("manifest_sha256") != _sha(manifest_raw)
            or prepared.get("stage1_input_sha256") != _sha(stage1_raw)
            or prepared.get("stage1_request_sha256") != manifest.get("stage1_request_sha256")):
        raise ValueError("validation_prepared_binding_invalid")
    process = strict_json(safe_path(output / "preflight-process-diagnostic.json").read_bytes())
    if _diagnostic_hash(root, process, spec) != prepared.get("preflight_diagnostic_sha256"):
        raise ValueError("validation_preflight_diagnostic_binding_invalid")
    stdout = strict_json(safe_path(root / process["stdout"]["path"]).read_bytes())
    if (process.get("status") != "completed" or process.get("return_code") != 0
            or stdout.get("preflight_passed") is not True
            or stdout.get("native_calls") != 0
            or stdout.get("stage") != 1
            or stdout.get("context") != manifest.get("context")
            or stdout.get("identity_sha256") != manifest.get("assets", {}).get("ordinary", {}).get("identity")):
        raise ValueError("validation_saved_preflight_invalid")
    return prepared, _sha(raw)


def _save_preflight_failure(output: Path, root: Path, manifest: dict,
                            stage1_input: Path, process_record: dict | None,
                            process_hash: str, diagnostic: str,
                            spec: ScopeSpec) -> dict:
    """Persist an immutable, non-executable preflight failure for read-only recovery."""
    manifest_raw = safe_path(output / "manifest.json").read_bytes()
    stage1_raw = safe_path(stage1_input).read_bytes()
    request = strict_json(safe_path(output / "stage-1-request.json").read_bytes())
    failure = {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_preflight_failure",
        "scope": spec.scope,
        "context": manifest["context"],
        "prepared": False,
        "execution_ready": False,
        "native_calls": 0,
        "stage": 1,
        "no_charged_ledger": True,
        "manifest_sha256": _sha(manifest_raw),
        "stage1_request_sha256": digest(canonical(request)),
        "stage1_input_sha256": _sha(stage1_raw),
        "process_diagnostic_sha256": process_hash,
        "process_diagnostic_saved": process_record is not None,
        "diagnostic": diagnostic,
        **FLAGS,
    }
    validate_report(failure, spec=spec)
    immutable_write(output / "preflight-failure.json", failure)
    return failure


def _read_preflight_failure(output: Path, root: Path, manifest: dict,
                            repo: Path, spec: ScopeSpec) -> dict:
    """Validate a saved failed preflight without retrying or opening a ledger."""
    failure_raw = safe_path(output / "preflight-failure.json").read_bytes()
    failure = strict_json(failure_raw)
    validate_report(failure, spec=spec)
    manifest_raw = safe_path(output / "manifest.json").read_bytes()
    stage1_input_path = output / "stage-1-input.json"
    stage1_input_raw = safe_path(stage1_input_path).read_bytes()
    request_raw = safe_path(output / "stage-1-request.json").read_bytes()
    request = strict_json(request_raw)
    stage1_invocation = strict_json(stage1_input_raw)
    if (failure.get("context") != manifest.get("context")
            or failure.get("manifest_sha256") != _sha(manifest_raw)
            or failure.get("stage1_input_sha256") != _sha(stage1_input_raw)
            or failure.get("stage1_request_sha256") != digest(canonical(request))
            or not _strict_equal(request, manifest.get("request"))
            or not _strict_equal(stage1_invocation.get("request"), request)
            or (output / "prepared.json").exists()
            or (output / "calls.jsonl").exists()):
        raise ValueError("validation_saved_preflight_failure_binding_invalid")
    _verify_frozen_stage1_request(repo, root, manifest, spec)
    _verify_stage_intent(
        stage1_input_path, output, manifest["context"], 1, request,
        manifest["assets"]["ordinary"], manifest["started_at"], spec,
    )
    process_path = output / "preflight-process-diagnostic.json"
    if failure.get("process_diagnostic_saved") is True:
        process_record = strict_json(safe_path(process_path).read_bytes())
        if _diagnostic_hash(root, process_record, spec) != failure.get("process_diagnostic_sha256"):
            raise ValueError("validation_saved_preflight_diagnostic_mismatch")
    elif process_path.exists() or failure.get("process_diagnostic_sha256") != _sha(b""):
        raise ValueError("validation_saved_preflight_diagnostic_mismatch")
    return failure


def _validate_saved_build_inputs(root: Path, manifest: dict,
                                 spec: ScopeSpec) -> dict[str, Path]:
    input_hashes = manifest.get("input_sha256")
    names = {"runner": root / "native-artifacts/tenki-placement-probe.exe",
             "worker": root / "native-artifacts/ygo-engine-worker.exe",
             "cli": root / "native-artifacts/ygo-cli.exe",
             "build_record": root / "build-record.json",
             "identity": root / "identity.json",
             "window_start": root / "window-start.json",
             "source_archive": root / "source-native.zip",
             "source_file_list": root / "source-native-file-list.json",
             "ordinary_config": root / "ordinary-candidate.toml",
             "tournament_config": root / "tournament-candidate.toml"}
    for role, path in names.items():
        if _sha(safe_path(path).read_bytes()) != input_hashes.get(role):
            raise ValueError(f"validation_saved_{role}_hash_mismatch")
    identity = strict_json(safe_path(names["identity"]).read_bytes())
    from ygo_eval.native_tenki_placement import _assert_runtime_identity, _validate_signed
    _validate_signed(identity, "workspace_identity")
    ordinary, tournament = _assert_runtime_identity(identity, names["worker"], manifest["request"])
    if (ordinary != manifest.get("assets", {}).get("ordinary")
            or tournament != manifest.get("assets", {}).get("tournament")):
        raise ValueError("validation_saved_dual_asset_identity_mismatch")
    build = strict_json(safe_path(names["build_record"]).read_bytes())
    from ygo_eval.native_tenki_placement import _validate_signed as validate_signed
    validate_signed(build, "build_record")
    if (build.get("source_before") != manifest.get("source")
            or build.get("source_after") != manifest.get("source")
            or build.get("artifacts", {}).get("runner") != input_hashes.get("runner")
            or build.get("artifacts", {}).get("worker") != input_hashes.get("worker")
            or build.get("artifacts", {}).get("cli") != input_hashes.get("cli")):
        raise ValueError("validation_saved_build_binding_mismatch")
    from ygo_eval.tenki_placement_diagnostics import _verify_archive
    source = manifest.get("source")
    archive = manifest.get("source_archive")
    if (not isinstance(source, dict) or not isinstance(archive, dict)
            or not isinstance(source.get("files"), dict)
            or type(archive.get("file_count")) is not int
            or archive["file_count"] != len(source["files"])):
        raise ValueError("validation_saved_source_archive_binding_invalid")
    archive_check = _verify_archive(
        root, "source-native.zip", "source-native-file-list.json",
        input_hashes["source_archive"], input_hashes["source_file_list"],
        source.get("identity"), archive["file_count"],
    )
    if (archive_check.get("archive_sha256") != archive.get("sha256")
            or archive_check.get("file_list_sha256") != archive.get("file_list_sha256")
            or archive_check.get("source_identity") != source.get("identity")):
        raise ValueError("validation_saved_source_archive_mismatch")
    return names


def _resume_prepared_validation(root: Path, output: Path, runner: Path,
                                repo: Path, baseline: dict,
                                protected: dict[Path, str],
                                process_runner: Callable[..., Any] | None,
                                spec: ScopeSpec, *, execute: bool) -> dict:
    manifest_path = output / "manifest.json"
    manifest_raw = safe_path(manifest_path).read_bytes()
    manifest = strict_json(manifest_raw)
    validate_report(manifest, spec=spec)
    if (manifest.get("baseline_delivery_sha256") != spec.delivery_sha256
            or manifest.get("input_sha256", {}).get("baseline_audit") != baseline["audit_sha256"]):
        raise ValueError("validation_manifest_baseline_mismatch")
    names = _validate_saved_build_inputs(root, manifest, spec)
    prepared, prepared_hash = _read_validation_prepared(output, root, manifest, repo, spec)
    if prepared.get("execution_ready") is not True:
        raise ValueError("validation_prepared_not_execution_ready")
    if stable_source(repo) != manifest.get("source"):
        raise ValueError("validation_workspace_source_changed")
    if execute:
        if not all((output / name).is_file() for name in (
                "stage-1-request.json", "stage-1-input.json", "stage-1-input-seal.json")):
            raise ValueError("validation_saved_stage1_intent_missing")
        frozen_files = {Path(os.path.abspath(path)): _sha(safe_path(path).read_bytes())
                        for path in names.values()}
        for path in (manifest_path, output / "prepared.json",
                     output / "stage-1-request.json", output / "stage-1-input.json",
                     output / "stage-1-input-seal.json"):
            frozen_files[Path(os.path.abspath(path))] = _sha(safe_path(path).read_bytes())
        return _run_six_stages(
            root=root, output=output, runner=runner, repo=repo,
            manifest=manifest, prepared_hash=prepared_hash,
            stage1_request=manifest["request"],
            expected_identity=manifest["assets"]["ordinary"],
            source=manifest["source"], protected=protected,
            frozen_files=frozen_files, process_runner=process_runner, spec=spec,
        )
    return prepared


def _verify_only(root: Path, output: Path, runner: Path, repo: Path,
                 manifest: dict, prepared_hash: str,
                 process_runner: Callable[..., Any] | None,
                 spec: ScopeSpec) -> dict:
    """Verify only existing evidence; never fill a missing stage or rewrite its report."""
    stage_summaries: list[dict] = []
    verify_diagnostics: list[str] = []
    diagnostic = None
    last_input = None
    parent_receipts: dict[int, dict] = {}
    for stage in range(1, spec.limit + 1):
        input_path = output / f"stage-{stage}-input.json"
        request_path = output / f"stage-{stage}-request.json"
        seal_path = output / f"stage-{stage}-input-seal.json"
        receipt_path = output / f"stage-{stage}.json"
        report_path = output / f"stage-{stage}-report.json"
        paths = (input_path, request_path, seal_path, receipt_path, report_path)
        if not all(path.is_file() for path in paths):
            if any(path.exists() for path in paths):
                diagnostic = "incomplete_saved_stage_files"
            else:
                diagnostic = "incomplete_stage_receipts"
            break
        invocation = strict_json(safe_path(input_path).read_bytes())
        request = strict_json(safe_path(request_path).read_bytes())
        seal = strict_json(safe_path(seal_path).read_bytes())
        receipt = strict_json(safe_path(receipt_path).read_bytes())
        report = strict_json(safe_path(report_path).read_bytes())
        if stage == 1:
            expected_request = manifest["request"]
        else:
            parent = parent_receipts.get(_PARENT_BY_STAGE[stage])
            if parent is None:
                diagnostic = "saved_parent_receipt_missing_or_invalid"
                break
            expected_request = derive_stage_request(stage, parent, spec)
        if not _strict_equal(request, expected_request):
            raise ValueError("validation_saved_parent_request_derivation_mismatch")
        _verify_stage_intent(input_path, output, manifest["context"], stage,
                             request, manifest["assets"]["ordinary"],
                             manifest["started_at"], spec)
        if (invocation.get("request") != request
                or invocation.get("batch_kind") != spec.batch_kind
                or seal.get("context") != manifest["context"]):
            raise ValueError("validation_saved_stage_intent_invalid")
        _verify_basic_receipt(receipt, request, manifest["context"], stage, spec)
        if receipt.get("successful") is True:
            validate_stage_receipt(receipt, request, manifest["context"], stage,
                                   manifest["assets"]["ordinary"], spec)
            parent_receipts[stage] = receipt
        validate_report(report, spec=spec)
        if (report.get("kind") != "native_tenki_placement_validation_stage_report"
                or report.get("stage") != stage
                or report.get("context") != manifest["context"]
                or report.get("receipt_sha256") != _sha(safe_path(receipt_path).read_bytes())):
            raise ValueError("validation_saved_stage_report_binding_invalid")
        native_diag = safe_path(root / f"stage-{stage}-process-diagnostic.json")
        process_record = strict_json(native_diag.read_bytes())
        if _diagnostic_hash(root, process_record, spec) != report.get("diagnostic_sha256"):
            raise ValueError("validation_saved_stage_diagnostic_mismatch")
        process, completed, diagnostic_hash = _run_process(
            runner, input_path, repo, root, "verify_recorded",
            process_runner=process_runner, spec=spec,
        )
        verify_diagnostics.append(diagnostic_hash)
        if (process.get("status") != "completed" or completed is None
                or completed.returncode not in (0, 1)):
            diagnostic = "recorded_receipt_verification_failed"
            break
        runner_output = strict_json(completed.stdout)
        if (runner_output.get("verified_recorded") is not True
                or runner_output.get("native_calls") != 0):
            diagnostic = "recorded_receipt_verification_failed"
            break
        stage_summaries.append({key: report.get(key) for key in (
            "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
            "diagnostic_sha256", "independent_replay_matches", "ledger")})
        last_input = input_path
        if report.get("successful") is not True:
            diagnostic = report.get("diagnostic") or "saved_stage_unsuccessful"
            break
    stats = None
    ledger_path = output / "calls.jsonl"
    if ledger_path.exists() and (last_input is not None or (output / "stage-1-input.json").is_file()):
        stats, _stats_record, _stats_hash = _read_runner_stats(
            runner, last_input or output / "stage-1-input.json", repo, root,
            process_runner=process_runner, spec=spec,
        )
        if not _valid_stats(stats, spec):
            stats = None
    if stats is None:
        new_consumed = cumulative = unknown = None
    else:
        new_consumed = stats["consumed"]
        cumulative = spec.old_consumed + stats["consumed"]
        unknown = stats["unknown"]
    successful = bool(
        diagnostic is None and len(stage_summaries) == spec.limit
        and stats is not None and stats["consumed"] == stats["completed"] == spec.limit
        and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0
        and all(_is_successful_stage_summary(item, i, spec)
                for i, item in enumerate(stage_summaries, 1))
        and len(verify_diagnostics) == spec.limit
    )
    if not successful and diagnostic is None:
        diagnostic = "saved_validation_incomplete_or_invalid"
    report = {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_verification",
        "scope": spec.scope,
        "context": manifest["context"],
        "valid": successful,
        "native_calls": 0,
        "old_consumed": spec.old_consumed,
        "new_consumed": new_consumed,
        "cumulative_consumed": cumulative,
        "unknown": unknown,
        "ledger": stats,
        "stages": stage_summaries,
        "prepared_sha256": prepared_hash,
        "verification_diagnostic_sha256": verify_diagnostics,
        "diagnostic": diagnostic,
        **FLAGS,
    }
    validate_report(report, spec=spec)
    verification_path = output / "verification.json"
    if verification_path.exists():
        previous = strict_json(safe_path(verification_path).read_bytes())
        comparable = {key: value for key, value in report.items()
                      if key != "verification_diagnostic_sha256"}
        old_comparable = {key: value for key, value in previous.items()
                          if key != "verification_diagnostic_sha256"}
        if old_comparable != comparable:
            raise ValueError("validation_existing_verification_differs")
        return previous
    immutable_write(verification_path, report)
    return report


def native_tenki_placement_validation(args: argparse.Namespace,
                                      repo: Path | None = None,
                                      *, spec: ScopeSpec = VALIDATION_SCOPE,
                                      process_runner: Callable[..., Any] | None = None) -> dict:
    """Prepare, verify, or run this immutable six-call scope."""
    from ygo_eval.native_tenki_placement import (
        _archive_current_source, _candidate_configs, _capture_identity,
    )
    from ygo_eval.native_tenki_placement_confirmation import (
        OLD_PLACEMENT_RELATIVE, PROMPT_BASELINE_RELATIVE, _candidate_request,
        _verify_build_and_identity, _verify_workspace_identity,
    )

    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    root, output, paths = _fixed_validation_paths(args, repo, spec)
    if not root.is_dir() or not (root / "native-artifacts").is_dir():
        raise ValueError("validation_isolated_build_required")
    if not any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime")
               for line in safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()):
        raise ValueError("validation_output_must_be_ignored")
    baseline, protected = _verify_validation_baseline(repo, Path(args.baseline_dir), spec)
    if not args.verify_only and output.exists() and output.is_symlink():
        raise ValueError("validation_linked_research_directory_rejected")
    if args.verify_only:
        if not output.is_dir():
            raise ValueError("validation_output_missing")
        manifest = strict_json(safe_path(output / "manifest.json").read_bytes())
        validate_report(manifest, spec=spec)
        if (manifest.get("baseline_delivery_sha256") != spec.delivery_sha256
                or manifest.get("input_sha256", {}).get("baseline_audit") != baseline["audit_sha256"]):
            raise ValueError("validation_manifest_baseline_mismatch")
        _validate_saved_build_inputs(root, manifest, spec)
        if (output / "preflight-failure.json").is_file():
            return _read_preflight_failure(output, root, manifest, repo, spec)
        prepared, prepared_hash = _read_validation_prepared(output, root, manifest, repo, spec)
        return _verify_only(root, output, paths["runner"], repo, manifest,
                            prepared_hash, process_runner, spec)

    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            # A frozen, complete prepare can be recovered below. Any partial or
            # foreign directory remains evidence and is never overwritten.
            if (output.is_dir() and (output / "manifest.json").is_file()
                    and (output / "preflight-failure.json").is_file()):
                manifest = strict_json(safe_path(output / "manifest.json").read_bytes())
                validate_report(manifest, spec=spec)
                if (manifest.get("baseline_delivery_sha256") != spec.delivery_sha256
                        or manifest.get("input_sha256", {}).get("baseline_audit") != baseline["audit_sha256"]):
                    raise ValueError("validation_manifest_baseline_mismatch")
                _validate_saved_build_inputs(root, manifest, spec)
                failure = _read_preflight_failure(output, root, manifest, repo, spec)
                if args.prepare_only:
                    return failure
                raise ValueError("validation_preflight_failed_requires_verify_only")
            if not (output.is_dir() and (output / "manifest.json").is_file()
                    and (output / "prepared.json").is_file()):
                raise ValueError("validation_existing_research_directory_not_recoverable")
            if args.prepare_only:
                if (output / "calls.jsonl").exists():
                    raise ValueError("validation_prepare_requires_absent_ledger")
                manifest = strict_json(safe_path(output / "manifest.json").read_bytes())
                validate_report(manifest, spec=spec)
                if (manifest.get("baseline_delivery_sha256") != spec.delivery_sha256
                        or manifest.get("input_sha256", {}).get("baseline_audit")
                        != baseline["audit_sha256"]):
                    raise ValueError("validation_manifest_baseline_mismatch")
                _validate_saved_build_inputs(root, manifest, spec)
                now = int(time.time())
                require(now >= manifest["started_at"], "validation_clock_before_window")
                require(now < manifest["started_at"] + spec.wall_seconds,
                        "validation_window_expired")
                return _resume_prepared_validation(
                    root, output, paths["runner"], repo, baseline, protected,
                    process_runner, spec, execute=False,
                )
            return _resume_prepared_validation(
                root, output, paths["runner"], repo, baseline, protected,
                process_runner, spec, execute=True,
            )
        raise ValueError("validation_existing_research_directory_not_recoverable")
    if not args.prepare_only:
        raise ValueError("validation_prepare_required_before_execution")

    source_before = stable_source(repo)
    _validate_build, artifacts, cli, build_hash = _verify_build_and_identity(
        args, repo, root, paths, source_before,
    )
    source_archive = _archive_current_source(repo, root, source_before)
    ordinary_config_root = repo / OLD_PLACEMENT_RELATIVE
    configs = _candidate_configs(repo, root, paths["worker"], ordinary_config_root)
    if paths["identity"].exists() and not paths["window_start"].exists():
        raise ValueError("validation_identity_exists_without_window")
    # Candidate validation opens the frozen CDB. Persist the immutable wall
    # clock before that first asset scan so preflight time is charged to scope.
    window = _validation_window(paths["window_start"], spec)
    started_at = window["started_at"]
    if args.prepare_only:
        require(started_at + spec.wall_seconds > int(time.time()), "validation_window_expired")
    request, frozen_case = _candidate_request(
        repo, repo / PROMPT_BASELINE_RELATIVE, paths["worker"],
    )
    identity = _capture_identity(repo, cli, configs, paths["identity"])
    ordinary, tournament = _verify_workspace_identity(
        identity, source_before, artifacts, paths["worker"], request,
    )
    if stable_source(repo) != source_before:
        raise ValueError("validation_workspace_changed_during_identity_capture")
    preparation_sha = frozen_case["preparation_sha256"]
    input_sha256 = {
        "runner": _sha(safe_path(paths["runner"]).read_bytes()),
        "worker": _sha(safe_path(paths["worker"]).read_bytes()),
        "cli": _sha(safe_path(cli).read_bytes()),
        "build_record": build_hash,
        "identity": _sha(safe_path(paths["identity"]).read_bytes()),
        "window_start": _sha(safe_path(paths["window_start"]).read_bytes()),
        "source_archive": source_archive["sha256"],
        "source_file_list": source_archive["file_list_sha256"],
        "ordinary_config": _sha(safe_path(configs["ordinary"]).read_bytes()),
        "tournament_config": _sha(safe_path(configs["tournament"]).read_bytes()),
        "banlist": frozen_case["banlist_sha256"],
        "preparation": preparation_sha,
        "baseline_delivery": spec.delivery_sha256,
        "baseline_audit": baseline["audit_sha256"],
        "prompt_source_stage1": frozen_case["old_stage1_sha256"],
        "prompt_source_stage2_request": frozen_case["old_stage2_request_sha256"],
    }
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
    if not output.is_dir():
        raise ValueError("validation_research_directory_required")
    expected_identity = ordinary
    unsigned = {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_manifest",
        "scope": spec.scope,
        "limit": spec.limit,
        "planned_calls": spec.limit,
        "wall_seconds": spec.wall_seconds,
        "started_at": started_at,
        "old_consumed": spec.old_consumed,
        "baseline_delivery_sha256": spec.delivery_sha256,
        "source": source_before,
        "build": {"identity": _validate_build.get("identity"),
                  "artifacts": artifacts, "record_sha256": build_hash},
        "assets": {"ordinary": ordinary, "tournament": tournament,
                   "identity_sha256": identity.get("identity"),
                   "execution_role": "ordinary"},
        "input_sha256": input_sha256,
        "source_archive": source_archive,
        "request": request,
        "stage1_request_sha256": digest(canonical(request)),
        "request_derivation": "frozen-tenki-activation-only-worker-path-replaced",
        **FLAGS,
    }
    manifest = {**unsigned, "context": digest(canonical(unsigned))}
    validate_report(manifest, spec=spec)
    manifest_path = output / "manifest.json"
    immutable_write(manifest_path, manifest)
    stage1_input, _request_path = _save_stage_files(
        output, manifest["context"], 1, request, expected_identity,
        started_at, spec,
    )
    if args.prepare_only:
        if (output / "calls.jsonl").exists():
            raise ValueError("validation_prepare_requires_absent_ledger")
        try:
            timeout = min(900.0, _normal_runner_timeout(manifest, now=time.time(), spec=spec))
            process_record, completed, process_hash = _run_process(
                paths["runner"], stage1_input, repo, root, "preflight_only",
                timeout=timeout, process_runner=process_runner, spec=spec,
            )
        except Exception as error:
            process_record, completed, process_hash = None, None, _sha(b"")
            diagnostic = str(error) if str(error).isidentifier() else "validation_preflight_failed"
        else:
            diagnostic = None
        if process_record is not None:
            immutable_write(output / "preflight-process-diagnostic.json", process_record)
        output_value = None
        if completed is not None and process_record and process_record.get("status") == "completed":
            try:
                output_value = strict_json(completed.stdout)
            except (ValueError, UnicodeDecodeError, TypeError):
                diagnostic = "validation_preflight_json_invalid"
        if (completed is None or completed.returncode != 0 or not isinstance(output_value, dict)
                or output_value.get("preflight_passed") is not True
                or type(output_value.get("native_calls")) is not int
                or output_value.get("native_calls") != 0
                or output_value.get("stage") != 1
                or output_value.get("context") != manifest["context"]
                or output_value.get("identity_sha256") != expected_identity.get("identity")):
            diagnostic = diagnostic or "validation_preflight_output_mismatch"
        if (output / "calls.jsonl").exists():
            raise ValueError("validation_preflight_created_ledger")
        if diagnostic is not None or process_record is None:
            return _save_preflight_failure(
                output, root, manifest, stage1_input, process_record,
                process_hash, diagnostic or "validation_preflight_failed", spec,
            )
        prepared = {
            "schema_version": 1,
            "kind": "native_tenki_placement_validation_prepared",
            "scope": spec.scope,
            "context": manifest["context"],
            "prepared": True,
            "execution_ready": True,
            "native_calls": 0,
            "planned_calls": spec.limit,
            "stage1_request_sha256": manifest["stage1_request_sha256"],
            "preflight_diagnostic_sha256": process_hash,
            "manifest_sha256": _sha(safe_path(manifest_path).read_bytes()),
            "stage1_input_sha256": _sha(safe_path(stage1_input).read_bytes()),
            "diagnostics": ["historical_eight_ledgers_verified", "dual_asset_identity_bound",
                            "preflight_passed"],
            **FLAGS,
        }
        validate_report(prepared, spec=spec)
        immutable_write(output / "prepared.json", prepared)
        return prepared
    raise ValueError("validation_prepare_flow_unreachable")
