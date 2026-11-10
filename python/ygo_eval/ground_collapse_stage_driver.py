"""Fixed-action Ground Collapse stage derivation and receipt validation.

This module is an orchestration helper only. Importing it creates no scope and
does not start a runner, worker, engine, or FFI call.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from ygo_data.identity import canonical, digest, regular_file, stable_source
from ygo_eval.ground_collapse_protocol import (
    audit_ground_collapse_fixed_selection,
    audit_opcode18_fixed_zone_selection,
)
from ygo_eval.prompt_probe_prepare import strict_json
from ygo_eval.terminal_regression import immutable_write


GROUND_COLLAPSE_SCOPE = "p1-ground-collapse-opcode24-reachability-v1"
MAX_REQUESTS = 5
WINDOW_SECONDS = 1800
RUNNER_TIMEOUT_SECONDS = 60
REQUEST_TIMEOUT_MS = 30000
TARGET_CARD_ID = 90502999
TARGET_ZONES = [
    {"player": 1, "location": 4, "sequence": 0},
    {"player": 1, "location": 4, "sequence": 1},
]
TARGET_RESPONSE = [1, 4, 0, 1, 4, 1]
OPCODE18_ZONE = {"player": 0, "location": 8, "sequence": 0}
OPCODE18_RESPONSE = [0, 8, 0]
PROMPT_OPCODES = {11, 12, 13, 14, 15, 16, 18, 19, 24, 26}
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}


def _require(condition: bool, diagnostic: str) -> None:
    if not condition:
        raise ValueError(diagnostic)


def _strict_equal(left: Any, right: Any) -> bool:
    """Compare JSON-shaped values without treating bool as int."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _result_from_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(receipt, dict), "stage_receipt_object_required")
    result = receipt.get("result")
    _require(isinstance(result, dict) and set(result) == {"Ok"}, "successful_parent_result_required")
    value = result["Ok"]
    _require(isinstance(value, dict), "duel_result_object_required")
    return value


def _prompt_frame(result: dict[str, Any], prompt: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    _require(isinstance(prompt, dict), "pending_prompt_object_required")
    prompt_id = prompt.get("id")
    opcode = prompt.get("opcode")
    player = prompt.get("player")
    _require(type(prompt_id) is int and prompt_id >= 0, "prompt_id_invalid")
    _require(type(opcode) is int and opcode in PROMPT_OPCODES, "unexpected_prompt_opcode")
    _require(type(player) is int and player in (0, 1), "prompt_player_invalid")
    events = result.get("events")
    _require(isinstance(events, list), "event_list_required")
    matches = [
        event for event in events
        if isinstance(event, dict)
        and type(event.get("sequence")) is int
        and event["sequence"] == prompt_id
        and type(event.get("opcode")) is int
        and event["opcode"] == opcode
    ]
    _require(len(matches) == 1, "pending_raw_prompt_not_unique")
    frame = matches[0]
    raw_value = frame.get("raw")
    _require(
        isinstance(raw_value, list)
        and all(type(byte) is int and 0 <= byte <= 255 for byte in raw_value),
        "raw_prompt_bytes_invalid",
    )
    raw = bytes(raw_value)
    _require(bool(raw) and raw[0] == opcode, "raw_prompt_opcode_mismatch")
    recorded = frame.get("fields", {}).get("prompt") if isinstance(frame.get("fields"), dict) else None
    _require(_strict_equal(recorded, prompt), "raw_recorded_prompt_mismatch")
    return frame, raw


def _unique_activation(prompt: dict[str, Any]) -> dict[str, Any]:
    _require(prompt.get("opcode") == 11 and prompt.get("player") == 0,
             "ground_activation_requires_own_idle")
    actions = prompt.get("actions")
    _require(isinstance(actions, list), "activation_action_menu_missing")
    matches = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        choice = action.get("choice")
        if (isinstance(choice, dict) and choice.get("kind") == "command"
                and type(choice.get("command")) is int and choice["command"] == 5
                and action.get("card_ids") == [TARGET_CARD_ID]):
            matches.append(action)
    _require(len(matches) == 1, "activation_not_unique")
    action = matches[0]
    choice = action["choice"]
    index = choice.get("index")
    _require(type(index) is int and 0 <= index <= 65535, "activation_index_invalid")
    expected = ((index << 16) | 5).to_bytes(4, "little")
    _require(action.get("bytes") == list(expected), "activation_response_bytes_mismatch")
    return action


def _unique_fixed_place(prompt: dict[str, Any], raw: bytes, opcode: int) -> dict[str, Any]:
    actions = prompt.get("actions")
    _require(isinstance(actions, list), f"opcode{opcode}_actions_missing")
    # The independent oracle's contract intentionally covers only the fields
    # that bind a menu action to its response. Rust's public Action also has a
    # display label, which is not part of that wire-level binding.
    oracle_prompt = dict(prompt)
    oracle_prompt["actions"] = [
        {key: copy.deepcopy(action[key]) for key in ("choice", "card_ids", "bytes")}
        for action in actions
        if isinstance(action, dict)
        and all(key in action for key in ("choice", "card_ids", "bytes"))
    ]
    if opcode == 18:
        audit_opcode18_fixed_zone_selection(
            raw, oracle_prompt, OPCODE18_ZONE, OPCODE18_RESPONSE
        )
        expected_choice = {"kind": "place", "zones": [OPCODE18_ZONE]}
        expected_bytes = OPCODE18_RESPONSE
    else:
        audit_ground_collapse_fixed_selection(
            raw, oracle_prompt, TARGET_ZONES, TARGET_RESPONSE
        )
        expected_choice = {"kind": "place", "zones": TARGET_ZONES}
        expected_bytes = TARGET_RESPONSE
    actions = prompt.get("actions")
    matches = [
        action for action in actions
        if isinstance(action, dict)
        and _strict_equal(action.get("choice"), expected_choice)
        and _strict_equal(action.get("bytes"), expected_bytes)
    ]
    _require(len(matches) == 1, f"opcode{opcode}_fixed_selection_not_unique")
    return matches[0]


def _append_decision(request: dict[str, Any], parent_result: dict[str, Any],
                     prompt: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    decisions = request.get("decisions")
    resolved = parent_result.get("resolved_decisions")
    _require(isinstance(decisions, list), "request_decisions_missing")
    _require(isinstance(resolved, list), "parent_resolved_decisions_missing")
    _require(len(resolved) >= len(decisions)
             and _strict_equal(resolved[:len(decisions)], decisions),
             "parent_resolved_decisions_mismatch")
    next_request = copy.deepcopy(request)
    next_request["decisions"] = copy.deepcopy(resolved)
    next_request["decisions"].append({
        "prompt_id": prompt["id"],
        "player": prompt["player"],
        "choice": copy.deepcopy(action["choice"]),
    })
    return next_request


def derive_ground_stage_request(stage: int, parent: dict[str, Any]) -> dict[str, Any]:
    """Derive the next frozen request from the authenticated prior receipt.

    Stages are 1-based. Stage 1 is supplied as the frozen base request. The
    optional opcode18 branch occupies one additional request; the final request
    is an exact replay of the request that submitted the opcode24 response.
    """
    _require(type(stage) is int and 2 <= stage <= MAX_REQUESTS, "stage_outside_ground_window")
    request = parent.get("request") if isinstance(parent, dict) else None
    _require(isinstance(request, dict), "parent_request_missing")
    parent_result = _result_from_receipt(parent)
    validated = validate_ground_stage_result(parent.get("stage"), request, parent.get("result"))
    _require(validated["successful"] is True, "parent_stage_unsuccessful")

    if stage == 2:
        _require(parent.get("stage") == 1 and request.get("decisions") == [],
                 "initial_ground_request_required")
        prompt = parent_result.get("prompt")
        _require(isinstance(prompt, dict), "initial_activation_prompt_missing")
        frame, _ = _prompt_frame(parent_result, prompt)
        _require(frame.get("opcode") == 11, "ground_activation_requires_own_idle")
        return _append_decision(request, parent_result, prompt, _unique_activation(prompt))

    decisions = request.get("decisions")
    _require(isinstance(decisions, list) and decisions, "parent_decision_prefix_missing")
    last_choice = decisions[-1].get("choice") if isinstance(decisions[-1], dict) else None
    zones = last_choice.get("zones") if isinstance(last_choice, dict) else None

    if stage == 3:
        _require(parent.get("stage") == 2, "activation_stage_required")
        prompt = parent_result.get("prompt")
        _require(isinstance(prompt, dict), "activation_followup_prompt_missing")
        frame, raw = _prompt_frame(parent_result, prompt)
        opcode = frame["opcode"]
        _require(opcode in (18, 24) and prompt.get("player") == 0,
                 "unexpected_activation_followup")
        return _append_decision(
            request, parent_result, prompt, _unique_fixed_place(prompt, raw, opcode)
        )

    if stage == 4 and isinstance(zones, list) and len(zones) == 1:
        _require(parent.get("stage") == 3, "opcode18_response_stage_required")
        prompt = parent_result.get("prompt")
        _require(isinstance(prompt, dict), "opcode24_prompt_after_opcode18_missing")
        frame, raw = _prompt_frame(parent_result, prompt)
        _require(frame.get("opcode") == 24 and prompt.get("player") == 0,
                 "unexpected_opcode18_followup")
        return _append_decision(
            request, parent_result, prompt, _unique_fixed_place(prompt, raw, 24)
        )

    if stage in (4, 5) and isinstance(zones, list) and _strict_equal(zones, TARGET_ZONES):
        _require(parent.get("stage") == stage - 1, "opcode24_response_parent_required")
        _require(validated.get("phase") == "opcode24_response_accepted",
                 "opcode24_response_not_accepted")
        return copy.deepcopy(request)

    raise ValueError("ground_stage_transition_invalid")


def validate_ground_stage_result(stage: int, request: dict[str, Any],
                                 outcome: dict[str, Any]) -> dict[str, Any]:
    """Validate one runner result against the fixed Ground Collapse route."""
    _require(type(stage) is int and 1 <= stage <= MAX_REQUESTS, "stage_outside_ground_window")
    _require(isinstance(request, dict), "request_object_required")
    _require(isinstance(outcome, dict) and set(outcome) in ({"Ok"}, {"Err"}),
             "runner_result_variant_required")
    if "Err" in outcome:
        raise ValueError("engine_request_failed")
    result = outcome["Ok"]
    _require(isinstance(result, dict), "duel_result_object_required")
    _require(result.get("protocol_version") == 2, "protocol_version_mismatch")
    _require(result.get("error") is None, "engine_result_error")
    _require(result.get("coverage_gaps") == [], "engine_coverage_gap")
    _require(result.get("status") in ("decision_required", "engine_verified", "probe_passed"),
             "engine_result_status_invalid")
    _require(isinstance(result.get("events"), list), "event_list_required")
    if result.get("status") == "decision_required":
        pending_prompt = result.get("prompt")
        _require(isinstance(pending_prompt, dict), "pending_prompt_missing")
        _prompt_frame(result, pending_prompt)
    else:
        _require(result.get("prompt") is None, "terminal_result_has_prompt")

    decisions = request.get("decisions")
    _require(isinstance(decisions, list), "request_decisions_missing")
    resolved = result.get("resolved_decisions")
    _require(isinstance(resolved, list), "resolved_decisions_missing")
    prefix_matches = len(resolved) >= len(decisions) and _strict_equal(
        resolved[:len(decisions)], decisions
    )
    final_choice = decisions[-1].get("choice") if decisions and isinstance(decisions[-1], dict) else None
    if not prefix_matches:
        if (isinstance(final_choice, dict) and final_choice.get("kind") == "place"
                and _strict_equal(final_choice.get("zones"), TARGET_ZONES)):
            raise ValueError("selected_response_not_consumed")
        raise ValueError("resolved_decisions_prefix_mismatch")

    if stage == 1:
        _require(decisions == [], "initial_request_has_decisions")
        prompt = result.get("prompt")
        _require(isinstance(prompt, dict), "initial_activation_prompt_missing")
        _prompt_frame(result, prompt)
        _unique_activation(prompt)
        return {"successful": True, "phase": "activation_available", **FLAGS}

    _require(decisions, "decision_request_required")
    selected = decisions[-1]
    _require(isinstance(selected, dict), "last_decision_invalid")
    selected_choice = selected.get("choice")
    _require(isinstance(selected_choice, dict), "last_choice_invalid")
    kind = selected_choice.get("kind")

    if kind == "command":
        _require(selected_choice.get("command") == 5, "ground_activation_choice_invalid")
        prompt = result.get("prompt")
        _require(isinstance(prompt, dict), "activation_followup_prompt_missing")
        _require(prompt.get("opcode") in (18, 24) and prompt.get("player") == 0,
                 "unexpected_activation_followup")
        frame, raw = _prompt_frame(result, prompt)
        opcode = frame["opcode"]
        _require(opcode in (18, 24) and prompt.get("player") == 0,
                 "unexpected_activation_followup")
        phase = "opcode18_available" if opcode == 18 else "opcode24_available"
        _unique_fixed_place(prompt, raw, opcode)
        return {"successful": True, "phase": phase, **FLAGS}

    zones = selected_choice.get("zones")
    _require(kind == "place" and isinstance(zones, list), "ground_place_choice_required")
    if len(zones) == 1:
        _require(_strict_equal(zones, [OPCODE18_ZONE]), "opcode18_fixed_zone_mismatch")
        prompt = result.get("prompt")
        _require(isinstance(prompt, dict), "opcode24_prompt_after_opcode18_missing")
        frame, raw = _prompt_frame(result, prompt)
        _require(frame.get("opcode") == 24 and prompt.get("player") == 0,
                 "unexpected_opcode18_followup")
        _unique_fixed_place(prompt, raw, 24)
        return {"successful": True, "phase": "opcode24_available", **FLAGS}

    _require(_strict_equal(zones, TARGET_ZONES), "opcode24_fixed_zone_mismatch")
    _require(selected.get("player") == 0, "opcode24_selected_player_mismatch")
    _require(type(selected.get("prompt_id")) is int, "opcode24_selected_prompt_id_invalid")
    matching_frames = []
    for event in result["events"]:
        if isinstance(event, dict) and event.get("opcode") == 24:
            prompt_value = event.get("fields", {}).get("prompt") if isinstance(event.get("fields"), dict) else None
            if isinstance(prompt_value, dict) and prompt_value.get("id") == selected["prompt_id"]:
                matching_frames.append((event, prompt_value))
    _require(len(matching_frames) == 1, "selected_opcode24_prompt_not_unique")
    event, prompt_value = matching_frames[0]
    _, raw = _prompt_frame({"events": [event]}, prompt_value)
    _unique_fixed_place(prompt_value, raw, 24)
    expected_decision = {
        "prompt_id": selected["prompt_id"],
        "player": 0,
        "choice": {"kind": "place", "zones": TARGET_ZONES},
    }
    consumed = [item for item in resolved if isinstance(item, dict) and item.get("prompt_id") == selected["prompt_id"]]
    _require(len(consumed) == 1 and _strict_equal(consumed[0], expected_decision),
             "selected_response_not_consumed")
    prompt_sequence = event.get("sequence")
    later_events = [item for item in result["events"]
                    if isinstance(item, dict) and type(item.get("sequence")) is int
                    and item["sequence"] > prompt_sequence]
    _require(result.get("status") in ("engine_verified", "probe_passed") or bool(later_events),
             "post_response_event_or_terminal_state_missing")
    later_prompts = [item for item in later_events if item.get("opcode") in PROMPT_OPCODES]
    _require(not later_prompts and result.get("prompt") is None,
             "unexpected_post_response_prompt")
    return {"successful": True, "phase": "opcode24_response_accepted", **FLAGS}


def replay_results_match(first: dict[str, Any], replay: dict[str, Any]) -> bool:
    """Compare complete results, ignoring only the volatile memory counter."""
    if not isinstance(first, dict) or not isinstance(replay, dict):
        return False
    left = copy.deepcopy(first)
    right = copy.deepcopy(replay)
    left["peak_working_set_bytes"] = None
    right["peak_working_set_bytes"] = None
    return _strict_equal(left, right)


def _sha256(path: Path) -> str:
    return digest(regular_file(path).read_bytes())


def _verify_run_manifest(manifest: dict[str, Any], runner: Path, output: Path,
                         initial_request: dict[str, Any], expected_identity: dict[str, Any],
                         repo: Path) -> None:
    _require(manifest.get("schema_version") == 1
             and manifest.get("kind") == "ground_collapse_probe_manifest",
             "ground_scope_manifest_required")
    _require(manifest.get("scope") == GROUND_COLLAPSE_SCOPE
             and manifest.get("request_limit") == MAX_REQUESTS
             and manifest.get("window_seconds") == WINDOW_SECONDS
             and manifest.get("request_timeout_ms") == REQUEST_TIMEOUT_MS,
             "ground_scope_budget_mismatch")
    _require(manifest.get("scope_authorized") is True
             and manifest.get("preparation_execution_ready") is True,
             "separate_scope_authorization_and_execution_ready_required")
    started_at = manifest.get("started_at")
    _require(type(started_at) is int and started_at <= int(time.time())
             and int(time.time()) - started_at < WINDOW_SECONDS,
             "ground_scope_window_start_invalid")
    _require(Path(os.path.abspath(manifest.get("output_path", ""))) == output,
             "ground_scope_output_binding_mismatch")
    _require(manifest.get("expected_identity") == expected_identity,
             "ground_expected_identity_binding_mismatch")
    _require(manifest.get("stage1_request_sha256") == digest(canonical(initial_request)),
             "ground_initial_request_binding_mismatch")
    _require(manifest.get("source_identity") == stable_source(repo),
             "ground_workspace_source_identity_changed")
    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, dict), "ground_scope_artifact_bindings_missing")
    for role, path in (("runner", runner),):
        binding = artifacts.get(role)
        _require(isinstance(binding, dict)
                 and Path(os.path.abspath(binding.get("path", ""))) == path
                 and binding.get("sha256") == _sha256(path),
                 f"ground_{role}_identity_mismatch")
    for role in ("worker", "build_record"):
        binding = artifacts.get(role)
        _require(isinstance(binding, dict) and isinstance(binding.get("path"), str),
                 f"ground_{role}_binding_missing")
        path = regular_file(Path(binding["path"]))
        _require(path.is_absolute(), f"ground_{role}_absolute_path_required")
        _require(binding.get("sha256") == _sha256(path), f"ground_{role}_identity_mismatch")
        if role == "worker":
            configured = initial_request.get("engine", {}).get("worker_path")
            _require(isinstance(configured, str)
                     and Path(os.path.abspath(configured)) == path,
                     "ground_worker_request_binding_mismatch")
    protected = manifest.get("protected_files")
    _require(isinstance(protected, dict) and protected, "ground_protected_inputs_missing")
    for path_text, expected_sha in protected.items():
        path = regular_file(Path(path_text))
        _require(path.is_absolute(), "ground_protected_input_absolute_path_required")
        _require(isinstance(expected_sha, str) and _sha256(path) == expected_sha,
                 "ground_protected_input_changed")
    unsigned = {key: value for key, value in manifest.items() if key != "context"}
    _require(manifest.get("context") == digest(canonical(unsigned)),
             "ground_scope_manifest_context_mismatch")
    for flag in ("proof_ready", "complete_action_coverage", "global_optimality",
                 "native_probability_verified"):
        _require(manifest.get(flag) is False, "ground_scope_qualification_must_remain_false")


def _safe_output_root(repo: Path, output: Path) -> None:
    ignore = regular_file(repo / ".gitignore").read_text(encoding="utf8").splitlines()
    _require(any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime")
                 for line in ignore), "runtime_output_ignore_contract_missing")
    for parent in [*reversed(output.parents), output]:
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            _require(not parent.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                     "linked_ground_output_path_rejected")
        if parent != repo and parent.is_relative_to(repo):
            _require(not (parent / ".gitignore").exists(), "nested_runtime_ignore_unsupported")


def _verify_frozen_manifest_inputs(manifest: dict[str, Any], runner: Path, repo: Path) -> None:
    _require(manifest.get("source_identity") == stable_source(repo),
             "ground_workspace_source_identity_changed")
    artifacts = manifest["artifacts"]
    for role, path in (("runner", runner),):
        _require(artifacts[role]["sha256"] == _sha256(path),
                 f"ground_{role}_identity_changed")
    for role in ("worker", "build_record"):
        binding = artifacts[role]
        _require(binding["sha256"] == _sha256(regular_file(Path(binding["path"]))),
                 f"ground_{role}_identity_changed")
    for path_text, expected_sha in manifest["protected_files"].items():
        _require(_sha256(regular_file(Path(path_text))) == expected_sha,
                 "ground_protected_input_changed")


def run_ground_collapse_stages(
    runner: Path,
    output: Path,
    manifest: dict[str, Any],
    initial_request: dict[str, Any],
    expected_identity: dict[str, Any],
    unchanged,
    *,
    repo: Path | None = None,
    prepare_only: bool = False,
    process_runner=None,
) -> dict[str, Any]:
    """Coordinate at most five one-request Rust runner invocations.

    `prepare_only` is inert: it creates no output directory or scope. Running
    requires a preflight-authenticated manifest carrying separate scope
    authorization and execution readiness. A failed or uncertain process is
    recorded as unknown and is never retried.
    """
    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    runner = Path(os.path.abspath(runner))
    output = Path(os.path.abspath(output))
    expected_output = repo / "data/runtime/p1-ground-collapse-opcode24-native-2026-11-03/research"
    _require(output == expected_output, "dedicated_ground_research_output_required")
    _safe_output_root(repo, output)
    if prepare_only:
        return {
            "schema_version": 1,
            "kind": "ground_collapse_probe_prepared",
            "scope": GROUND_COLLAPSE_SCOPE,
            "prepared": True,
            "planned_requests": "4-5",
            "native_calls": 0,
            "runner_process_calls": 0,
            "worker_process_calls": 0,
            "ffi_calls": None,
            **FLAGS,
        }

    _verify_run_manifest(manifest, runner, output, initial_request, expected_identity, repo)
    _require(callable(unchanged), "ground_frozen_input_guard_required")
    _require(not output.exists(), "existing_ground_scope_evidence_requires_audit")
    output.mkdir(parents=True, exist_ok=False)
    immutable_write(output / "manifest.json", manifest)
    immutable_write(output / "window-start.json", {
        "scope": GROUND_COLLAPSE_SCOPE,
        "context": manifest["context"],
        "started_at": manifest["started_at"],
        "request_limit": MAX_REQUESTS,
        "window_seconds": WINDOW_SECONDS,
    })

    process_runner = process_runner or subprocess.run
    ledger = output / "calls.jsonl"
    receipts: list[dict[str, Any]] = []
    runner_process_calls = 0
    attempted_stage: int | None = None
    uncertain = False
    diagnostic = None
    request = copy.deepcopy(initial_request)
    started_at = manifest["started_at"]

    for stage in range(1, MAX_REQUESTS + 1):
        if stage > 1:
            try:
                request = derive_ground_stage_request(stage, receipts[-1])
            except (ValueError, TypeError, KeyError):
                diagnostic = "stage_derivation_failed"
                break
        if int(time.time()) + RUNNER_TIMEOUT_SECONDS >= started_at + WINDOW_SECONDS:
            diagnostic = "scope_window_exhausted_before_request"
            break
        try:
            unchanged()
            _verify_frozen_manifest_inputs(manifest, runner, repo)
            input_value = {
                "context": manifest["context"],
                "ledger": str(ledger),
                "output": str(output / f"stage-{stage}.json"),
                "stage": stage,
                "request": request,
                "expected_identity": expected_identity,
                "started_at": started_at,
            }
            input_path = output / f"stage-{stage}-input.json"
            immutable_write(input_path, input_value)
            attempted_stage = stage
            runner_process_calls += 1
            completed = process_runner(
                [str(runner), str(input_path), "--input-sha", digest(canonical(input_value))],
                capture_output=True,
                timeout=RUNNER_TIMEOUT_SECONDS,
                cwd=str(repo),
            )
            unchanged()
            _verify_frozen_manifest_inputs(manifest, runner, repo)
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            diagnostic = "runner_or_frozen_input_failure"
            uncertain = True
            break

        receipt_path = output / f"stage-{stage}.json"
        if not receipt_path.exists():
            diagnostic = "stage_receipt_unavailable"
            uncertain = True
            break
        accounting_trusted = False
        previous_receipt = receipts[-1] if receipts else None
        try:
            receipt = strict_json(regular_file(receipt_path).read_bytes())
            _require(isinstance(receipt, dict)
                     and receipt.get("scope") == GROUND_COLLAPSE_SCOPE
                     and receipt.get("context") == manifest["context"]
                     and receipt.get("stage") == stage
                     and receipt.get("request") == request
                     and receipt.get("started_at") == started_at,
                     "stage_receipt_input_binding_mismatch")
            runner_summary = strict_json(completed.stdout)
            _require(isinstance(runner_summary, dict)
                     and runner_summary.get("successful") == receipt.get("successful")
                     and runner_summary.get("native_calls") == receipt.get("native_calls")
                     and runner_summary.get("runner_process_calls") == 1
                     and runner_summary.get("worker_process_calls") == receipt.get("worker_process_calls")
                     and runner_summary.get("ffi_calls") is None
                     and runner_summary.get("ledger") == receipt.get("ledger"),
                     "runner_stdout_receipt_disagreement")

            stats = receipt.get("ledger")
            _require(type(receipt.get("successful")) is bool
                     and receipt.get("native_calls") == 1
                     and receipt.get("runner_process_calls") == 1
                     and receipt.get("worker_process_calls") == 1
                     and receipt.get("ffi_calls") is None,
                     "charged_stage_unaccounted")
            _require(isinstance(stats, dict)
                     and stats.get("limit") == MAX_REQUESTS
                     and stats.get("consumed") == stage
                     and stats.get("completed") == stage
                     and stats.get("unknown") == 0
                     and stats.get("reserved") == 0
                     and stats.get("abandoned") == 0,
                     "scope_ledger_inconsistent")
            accounting_trusted = True
            receipts.append(receipt)

            outcome = receipt.get("result")
            if isinstance(outcome, dict) and set(outcome) == {"Ok"}:
                validation = validate_ground_stage_result(stage, request, outcome)
                _require(receipt.get("validation") == {"Ok": validation},
                         "python_rust_validation_disagreement")
            else:
                validation = None
                validation_value = receipt.get("validation")
                error_value = outcome.get("Err") if isinstance(outcome, dict) else None
                _require(isinstance(outcome, dict) and set(outcome) == {"Err"}
                         and isinstance(validation_value, dict)
                         and isinstance(error_value, dict)
                         and validation_value.get("Err") == error_value.get("message"),
                         "failed_stage_result_binding_mismatch")
            if receipt.get("successful") is True:
                _require(receipt.get("assets_unchanged") is True
                         and receipt.get("assets_before") == expected_identity
                         and receipt.get("assets_after") == expected_identity
                         and validation is not None,
                         "successful_stage_asset_or_validation_mismatch")
            else:
                _require(receipt.get("successful") is False
                         and isinstance(receipt.get("diagnostic"), str)
                         and type(receipt.get("assets_unchanged")) is bool,
                         "failed_stage_has_no_failure_evidence")
            if previous_receipt and request == previous_receipt["request"] and receipt.get("successful") is True:
                _require(replay_results_match(previous_receipt["result"]["Ok"], receipt["result"]["Ok"])
                         and receipt.get("independent_replay_matches") is True,
                         "independent_replay_mismatch")
            else:
                _require(receipt.get("independent_replay_matches") in (None, False),
                         "unexpected_replay_claim")
        except (OSError, ValueError, TypeError, KeyError):
            diagnostic = "stage_receipt_validation_failed"
            uncertain = not accounting_trusted
            break

        if getattr(completed, "returncode", 2) != 0 or receipts[-1].get("successful") is not True:
            diagnostic = receipts[-1].get("diagnostic") or "runner_reported_failed_stage"
            break
        if receipts[-1]["validation"]["Ok"]["phase"] == "opcode24_response_accepted":
            replayed = receipts[-1].get("independent_replay_matches") is True
            if replayed:
                diagnostic = None
                break
            continue

    if diagnostic is None and (not receipts or receipts[-1].get("independent_replay_matches") is not True):
        diagnostic = "request_limit_exhausted_before_replay_acceptance"

    stats = receipts[-1].get("ledger") if receipts else None
    last_authenticated_ledger = (
        {"stage": receipts[-1]["stage"], "stats": stats}
        if uncertain and receipts and isinstance(stats, dict)
        else None
    )
    report = {
        "schema_version": 1,
        "kind": "ground_collapse_probe_summary",
        "scope": GROUND_COLLAPSE_SCOPE,
        "context": manifest["context"],
        "successful": diagnostic is None and bool(receipts)
                     and receipts[-1].get("independent_replay_matches") is True,
        "diagnostic": diagnostic,
        "attempted_stage": attempted_stage,
        "stage_count": len(receipts),
        "native_calls": sum(item["native_calls"] for item in receipts) if not uncertain else None,
        "runner_process_calls": runner_process_calls,
        "worker_process_calls": sum(item["worker_process_calls"] for item in receipts) if not uncertain else None,
        "ffi_calls": None,
        "ledger": stats if not uncertain else None,
        "last_authenticated_ledger": last_authenticated_ledger,
        "actual_unknown": stats.get("unknown") if not uncertain and isinstance(stats, dict) else None,
        "stages": [
            {"stage": item["stage"], "successful": item["successful"],
             "receipt_sha256": digest(canonical(item))}
            for item in receipts
        ],
        **FLAGS,
    }
    immutable_write(output / f"summary-{digest(canonical(report))}.json", report)
    return report
