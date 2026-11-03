from __future__ import annotations

import copy
import json
import subprocess
import time
from pathlib import Path

import pytest

from ygo_eval.ground_collapse_stage_driver import (
    derive_ground_stage_request,
    replay_results_match,
    run_ground_collapse_stages,
    validate_ground_stage_result,
)
from ygo_eval.ground_collapse_protocol import canonical_zone_pairs, zone_response_bytes
from ygo_data.identity import canonical, digest


TARGET_ZONES = [
    {"player": 1, "location": 4, "sequence": 0},
    {"player": 1, "location": 4, "sequence": 1},
]
TARGET_RESPONSE = [1, 4, 0, 1, 4, 1]
ACTIVATION_CHOICE = {"kind": "command", "command": 5, "index": 0}
ACTIVATION_BYTES = [5, 0, 0, 0]


def action(choice, response, card_ids=()):
    return {"choice": choice, "label": "synthetic", "card_ids": list(card_ids), "bytes": response}


def prompt(opcode, prompt_id, actions, player=0):
    return {"id": prompt_id, "player": player, "opcode": opcode, "actions": actions}


def event_for(value, raw):
    return {
        "sequence": value["id"],
        "opcode": value["opcode"],
        "raw": raw,
        "supported": True,
        "fields": {"prompt": copy.deepcopy(value)},
    }


def idle_result(prompt_id=1, duplicate=False):
    actions = [action(ACTIVATION_CHOICE, ACTIVATION_BYTES, [90502999])]
    if duplicate:
        actions.append(copy.deepcopy(actions[0]))
    value = prompt(11, prompt_id, actions)
    return {"protocol_version": 2, "status": "decision_required", "error": None, "events": [event_for(value, [11, 0])],
            "prompt": value, "resolved_decisions": [], "coverage_gaps": []}


def placement18_result(prompt_id=2, mask=0xFFFFFEFF):
    target = {"player": 0, "location": 8, "sequence": 0}
    value = prompt(18, prompt_id, [action({"kind": "place", "zones": [target]}, [0, 8, 0])])
    raw = [18, 0, 1, *mask.to_bytes(4, "little")]
    return {"protocol_version": 2, "status": "decision_required", "error": None, "events": [event_for(value, raw)],
            "prompt": value, "resolved_decisions": [], "coverage_gaps": []}


def opcode24_result(prompt_id=3, missing_target=False):
    mask = 0xFFE0FFE0
    pairs = canonical_zone_pairs(mask)
    actions = [action({"kind": "place", "zones": pair}, zone_response_bytes(pair)) for pair in pairs]
    if missing_target:
        actions = [item for item in actions if item["choice"]["zones"] != TARGET_ZONES]
    value = prompt(24, prompt_id, actions)
    raw = [24, 0, 2, *mask.to_bytes(4, "little")]
    return {"protocol_version": 2, "status": "decision_required", "error": None, "events": [event_for(value, raw)],
            "prompt": value, "resolved_decisions": [], "coverage_gaps": []}


def accepted_result(request, prompt_id=3):
    raw_prompt = [24, 0, 2, *0xFFE0FFE0.to_bytes(4, "little")]
    actions = [
        action({"kind": "place", "zones": pair}, zone_response_bytes(pair))
        for pair in canonical_zone_pairs(0xFFE0FFE0)
    ]
    value = prompt(24, prompt_id, actions)
    selected_event = event_for(value, raw_prompt)
    after = {"sequence": prompt_id + 1, "opcode": 52, "raw": [52], "supported": True, "fields": {}}
    return {"protocol_version": 2, "status": "engine_verified", "error": None, "events": [selected_event, after],
            "prompt": None, "resolved_decisions": copy.deepcopy(request["decisions"]), "coverage_gaps": []}


def receipt(request, result, stage):
    return {"stage": stage, "request": copy.deepcopy(request), "result": {"Ok": copy.deepcopy(result)}}


def base_request():
    return {"decisions": [], "protocol_version": 2, "seed": 1}


def request_after(request, prompt_value, chosen_action):
    next_request = copy.deepcopy(request)
    next_request["decisions"] = copy.deepcopy(request["decisions"])
    next_request["decisions"].append({
        "prompt_id": prompt_value["id"],
        "player": prompt_value["player"],
        "choice": copy.deepcopy(chosen_action["choice"]),
    })
    return next_request


def test_direct_opcode24_route_builds_response_then_one_exact_replay():
    initial = base_request()
    first = idle_result()
    activation = derive_ground_stage_request(2, receipt(initial, first, 1))
    assert activation["decisions"][-1]["choice"] == ACTIVATION_CHOICE

    second = opcode24_result(prompt_id=2)
    second["resolved_decisions"] = copy.deepcopy(activation["decisions"])
    select_zones = derive_ground_stage_request(3, receipt(activation, second, 2))
    assert select_zones["decisions"][-1] == {
        "prompt_id": 2,
        "player": 0,
        "choice": {"kind": "place", "zones": TARGET_ZONES},
    }
    assert validate_ground_stage_result(3, select_zones, {"Ok": accepted_result(select_zones, 2)})["successful"]

    replay = derive_ground_stage_request(4, receipt(select_zones, accepted_result(select_zones, 2), 3))
    assert replay == select_zones


def test_optional_opcode18_route_uses_one_extra_request_before_opcode24():
    initial = base_request()
    activation = derive_ground_stage_request(2, receipt(initial, idle_result(), 1))
    zone18 = placement18_result()
    zone18["resolved_decisions"] = copy.deepcopy(activation["decisions"])
    one_zone = derive_ground_stage_request(3, receipt(activation, zone18, 2))
    assert one_zone["decisions"][-1]["choice"] == {
        "kind": "place", "zones": [{"player": 0, "location": 8, "sequence": 0}]
    }

    pair24 = opcode24_result(prompt_id=3)
    pair24["resolved_decisions"] = copy.deepcopy(one_zone["decisions"])
    two_zones = derive_ground_stage_request(4, receipt(one_zone, pair24, 3))
    assert two_zones["decisions"][-1]["choice"] == {"kind": "place", "zones": TARGET_ZONES}
    accepted = accepted_result(two_zones, 3)
    assert validate_ground_stage_result(4, two_zones, {"Ok": accepted})["successful"]
    assert derive_ground_stage_request(5, receipt(two_zones, accepted, 4)) == two_zones


def test_duplicate_activation_and_missing_fixed_opcode24_action_stop():
    with pytest.raises(ValueError, match="activation_not_unique"):
        validate_ground_stage_result(1, base_request(), {"Ok": idle_result(duplicate=True)})

    activation = derive_ground_stage_request(2, receipt(base_request(), idle_result(), 1))
    pair24 = opcode24_result(prompt_id=2, missing_target=True)
    pair24["resolved_decisions"] = copy.deepcopy(activation["decisions"])
    with pytest.raises(ValueError, match="prompt_action_count_mismatch"):
        derive_ground_stage_request(3, receipt(activation, pair24, 2))


def test_unexpected_prompt_and_incomplete_acceptance_stop():
    activation = derive_ground_stage_request(2, receipt(base_request(), idle_result(), 1))
    unknown_prompt = prompt(13, 2, [])
    unknown = {"protocol_version": 2, "status": "decision_required", "error": None,
               "events": [event_for(unknown_prompt, [13, 0])], "prompt": unknown_prompt,
               "resolved_decisions": activation["decisions"], "coverage_gaps": []}
    with pytest.raises(ValueError, match="unexpected_activation_followup"):
        validate_ground_stage_result(2, activation, {"Ok": unknown})

    direct = opcode24_result(2)
    direct["resolved_decisions"] = copy.deepcopy(activation["decisions"])
    select_zones = derive_ground_stage_request(3, receipt(activation, direct, 2))
    not_resolved = accepted_result(select_zones, 2)
    not_resolved["resolved_decisions"] = []
    with pytest.raises(ValueError, match="selected_response_not_consumed"):
        validate_ground_stage_result(3, select_zones, {"Ok": not_resolved})


def test_opcode18_menu_and_prompt_are_bound_to_exact_fixed_coordinate():
    activation = derive_ground_stage_request(2, receipt(base_request(), idle_result(), 1))
    bad = placement18_result()
    bad["resolved_decisions"] = copy.deepcopy(activation["decisions"])
    bad["prompt"]["actions"][0]["bytes"] = [0, 4, 0]
    bad["events"][0]["fields"]["prompt"]["actions"][0]["bytes"] = [0, 4, 0]
    with pytest.raises(ValueError, match="opcode18_action_menu_binding_mismatch"):
        derive_ground_stage_request(3, receipt(activation, bad, 2))


def test_replay_comparison_ignores_only_volatile_memory_counter():
    first = {"events": [{"sequence": 1, "raw": [24, 0]}], "resolved_decisions": [1],
             "peak_working_set_bytes": 1024}
    replay = copy.deepcopy(first)
    replay["peak_working_set_bytes"] = 2048
    assert replay_results_match(first, replay)
    replay["events"][0]["raw"] = [24, 1]
    assert not replay_results_match(first, replay)


def run_manifest(tmp_path, monkeypatch, initial):
    import ygo_eval.ground_collapse_stage_driver as module

    repo = tmp_path
    (repo / ".gitignore").write_text("/data/runtime/\n", encoding="utf8")
    runner = repo / "ground-collapse-probe.exe"
    worker = repo / "worker.exe"
    build = repo / "build-record.json"
    prep = repo / "preparation.json"
    identity_file = repo / "identity.json"
    for path, raw in ((runner, b"runner"), (worker, b"worker"), (build, b"build"),
                      (prep, b"prep"), (identity_file, b"identity")):
        path.write_bytes(raw)
    identity = {"consistent": True, "roles": {"worker": {"sha256": digest(b"worker")}}}
    output = repo / "data/runtime/p1-ground-collapse-opcode24-native-2026-11-03/research"
    source_identity = {"identity": "synthetic-source"}
    monkeypatch.setattr(module, "stable_source", lambda _repo: source_identity)
    manifest = {
        "schema_version": 1,
        "kind": "ground_collapse_probe_manifest",
        "scope": module.GROUND_COLLAPSE_SCOPE,
        "request_limit": 5,
        "window_seconds": 1800,
        "request_timeout_ms": 30000,
        "started_at": int(time.time()),
        "output_path": str(output),
        "stage1_request_sha256": digest(canonical(initial)),
        "expected_identity": identity,
        "source_identity": source_identity,
        "scope_authorized": True,
        "preparation_execution_ready": True,
        "artifacts": {
            "runner": {"path": str(runner), "sha256": digest(b"runner")},
            "worker": {"path": str(worker), "sha256": digest(b"worker")},
            "build_record": {"path": str(build), "sha256": digest(b"build")},
        },
        "protected_files": {str(prep): digest(b"prep"), str(identity_file): digest(b"identity")},
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    manifest["context"] = digest(canonical(manifest))
    initial["engine"] = {"worker_path": str(worker), "timeout_ms": 30000}
    manifest["stage1_request_sha256"] = digest(canonical(initial))
    unsigned = {key: value for key, value in manifest.items() if key != "context"}
    manifest["context"] = digest(canonical(unsigned))
    return module, repo, runner, output, manifest, initial, identity


def test_coordinator_uses_synthetic_runner_and_completes_direct_route(monkeypatch):
    from test_prompt_probe_prepare import temporary_directory
    with temporary_directory() as temporary:
        initial = base_request()
        module, repo, runner, output, manifest, initial, identity = run_manifest(
            temporary, monkeypatch, initial
        )
        first_request = copy.deepcopy(initial)

        def fake_runner(command, **_kwargs):
            invocation = json.loads(Path(command[1]).read_bytes())
            stage = invocation["stage"]
            request = invocation["request"]
            if stage == 1:
                result = idle_result()
            elif stage == 2:
                result = opcode24_result(2)
                result["resolved_decisions"] = copy.deepcopy(request["decisions"])
            else:
                result = accepted_result(request, 2)
            outcome = {"Ok": result}
            validation = module.validate_ground_stage_result(stage, request, outcome)
            replay = True if stage == 4 else None
            receipt_value = {
            "schema_version": 1,
            "kind": "ground_collapse_probe_stage",
            "scope": module.GROUND_COLLAPSE_SCOPE,
            "context": manifest["context"],
            "stage": stage,
            "request": request,
            "result": outcome,
            "validation": {"Ok": validation},
            "assets_before": identity,
            "assets_after": identity,
            "assets_unchanged": True,
            "independent_replay_matches": replay,
            "successful": True,
            "diagnostic": None,
            "ledger": {"limit": 5, "consumed": stage, "completed": stage,
                       "unknown": 0, "reserved": 0, "abandoned": 0},
            "started_at": manifest["started_at"],
            "native_calls": 1,
            "runner_process_calls": 1,
            "worker_process_calls": 1,
            "ffi_calls": None,
            "proof_ready": False,
            "complete_action_coverage": False,
            "global_optimality": False,
            "native_probability_verified": False,
            }
            Path(invocation["output"]).write_text(json.dumps(receipt_value), encoding="utf8")
            stdout = canonical({"successful": True, "native_calls": 1, "runner_process_calls": 1,
                                "worker_process_calls": 1, "ffi_calls": None,
                                "ledger": receipt_value["ledger"]})
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

        report = run_ground_collapse_stages(
            runner, output, manifest, first_request, identity, lambda: None,
            repo=repo, process_runner=fake_runner,
        )
        assert report["successful"] is True
        assert report["native_calls"] == 4
        assert report["runner_process_calls"] == 4
        assert report["worker_process_calls"] == 4
        assert report["actual_unknown"] == 0
        assert report["proof_ready"] is False


def test_coordinator_does_not_retry_uncertain_runner_timeout(monkeypatch):
    from test_prompt_probe_prepare import temporary_directory
    with temporary_directory() as temporary:
        module, repo, runner, output, manifest, initial, identity = run_manifest(
            temporary, monkeypatch, base_request()
        )
        calls = []

        def timed_out(command, **_kwargs):
            calls.append(command)
            raise subprocess.TimeoutExpired(command, 60)

        report = run_ground_collapse_stages(
            runner, output, manifest, initial, identity, lambda: None,
            repo=repo, process_runner=timed_out,
        )
        assert len(calls) == 1
        assert report["successful"] is False
        assert report["native_calls"] is None
        assert report["actual_unknown"] is None
        assert report["diagnostic"] == "runner_or_frozen_input_failure"


def test_later_uncertain_runner_timeout_does_not_reuse_previous_actual_unknown(monkeypatch):
    from test_prompt_probe_prepare import temporary_directory
    with temporary_directory() as temporary:
        module, repo, runner, output, manifest, initial, identity = run_manifest(
            temporary, monkeypatch, base_request()
        )
        calls = []

        def first_stage_then_timeout(command, **_kwargs):
            calls.append(command)
            if len(calls) == 2:
                raise subprocess.TimeoutExpired(command, 60)

            invocation = json.loads(Path(command[1]).read_bytes())
            request = invocation["request"]
            result = idle_result()
            outcome = {"Ok": result}
            stats = {"limit": 5, "consumed": 1, "completed": 1,
                     "unknown": 0, "reserved": 0, "abandoned": 0}
            receipt_value = {
                "schema_version": 1,
                "kind": "ground_collapse_probe_stage",
                "scope": module.GROUND_COLLAPSE_SCOPE,
                "context": manifest["context"],
                "stage": 1,
                "request": request,
                "result": outcome,
                "validation": {"Ok": module.validate_ground_stage_result(1, request, outcome)},
                "assets_before": identity,
                "assets_after": identity,
                "assets_unchanged": True,
                "independent_replay_matches": None,
                "successful": True,
                "diagnostic": None,
                "ledger": stats,
                "started_at": manifest["started_at"],
                "native_calls": 1,
                "runner_process_calls": 1,
                "worker_process_calls": 1,
                "ffi_calls": None,
                "proof_ready": False,
                "complete_action_coverage": False,
                "global_optimality": False,
                "native_probability_verified": False,
            }
            Path(invocation["output"]).write_text(json.dumps(receipt_value), encoding="utf8")
            stdout = canonical({"successful": True, "native_calls": 1,
                                "runner_process_calls": 1, "worker_process_calls": 1,
                                "ffi_calls": None, "ledger": stats})
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

        report = run_ground_collapse_stages(
            runner, output, manifest, initial, identity, lambda: None,
            repo=repo, process_runner=first_stage_then_timeout,
        )

        assert len(calls) == 2
        assert report["successful"] is False
        assert report["native_calls"] is None
        assert report["actual_unknown"] is None
        assert report["ledger"] is None
        assert report["last_authenticated_ledger"] == {
            "stage": 1,
            "stats": {"limit": 5, "consumed": 1, "completed": 1,
                      "unknown": 0, "reserved": 0, "abandoned": 0},
        }
        assert report["diagnostic"] == "runner_or_frozen_input_failure"


def test_coordinator_keeps_complete_ledger_when_protocol_validation_disagrees(monkeypatch):
    from test_prompt_probe_prepare import temporary_directory
    with temporary_directory() as temporary:
        module, repo, runner, output, manifest, initial, identity = run_manifest(
            temporary, monkeypatch, base_request()
        )

        def mismatched_validation(command, **_kwargs):
            invocation = json.loads(Path(command[1]).read_bytes())
            receipt = {
                "schema_version": 1,
                "kind": "ground_collapse_probe_stage",
                "scope": module.GROUND_COLLAPSE_SCOPE,
                "context": manifest["context"],
                "stage": 1,
                "request": invocation["request"],
                "result": {"Ok": idle_result()},
                "validation": {"Ok": {"phase": "incorrect"}},
                "assets_before": identity,
                "assets_after": identity,
                "assets_unchanged": True,
                "independent_replay_matches": None,
                "successful": True,
                "diagnostic": None,
                "ledger": {"limit": 5, "consumed": 1, "completed": 1,
                           "unknown": 0, "reserved": 0, "abandoned": 0},
                "started_at": manifest["started_at"],
                "native_calls": 1,
                "runner_process_calls": 1,
                "worker_process_calls": 1,
                "ffi_calls": None,
                "proof_ready": False,
                "complete_action_coverage": False,
                "global_optimality": False,
                "native_probability_verified": False,
            }
            Path(invocation["output"]).write_text(json.dumps(receipt), encoding="utf8")
            stdout = canonical({"successful": True, "native_calls": 1,
                                "runner_process_calls": 1, "worker_process_calls": 1,
                                "ffi_calls": None, "ledger": receipt["ledger"]})
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

        report = run_ground_collapse_stages(
            runner, output, manifest, initial, identity, lambda: None,
            repo=repo, process_runner=mismatched_validation,
        )
        assert report["successful"] is False
        assert report["diagnostic"] == "stage_receipt_validation_failed"
        assert report["native_calls"] == 1
        assert report["worker_process_calls"] == 1
        assert report["actual_unknown"] == 0
        assert report["ledger"]["consumed"] == 1
        assert report["stage_count"] == 1


def test_prepare_only_creates_no_scope_or_runner_call(monkeypatch):
    from test_prompt_probe_prepare import temporary_directory
    with temporary_directory() as temporary:
        module, repo, runner, output, manifest, initial, identity = run_manifest(
            temporary, monkeypatch, base_request()
        )
        report = run_ground_collapse_stages(
            runner, output, manifest, initial, identity, lambda: None,
            repo=repo, prepare_only=True,
            process_runner=lambda *_args, **_kwargs: pytest.fail("runner must remain inert"),
        )
        assert report["prepared"] is True
        assert report["native_calls"] == 0
        assert not output.exists()
