"""Independent six-stage Tenki placement and opcode 13 experiment."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

from ygo_data.identity import canonical, digest, regular_file, stable_source
from ygo_eval.prompt_probe_prepare import require, safe_path, strict_json
from ygo_eval.terminal_regression import immutable_write

SCOPE = "tenki-placement-probe-v1"
OUTPUT_ROOT_RELATIVE = Path("data/runtime/p1-tenki-placement-native-2026-10-22")
OUTPUT_RELATIVE = OUTPUT_ROOT_RELATIVE / "research"
TRANSITION_RELATIVE_PATH = Path("target/debug/ygo-engine-worker.exe")
TRANSITION_FILE_PATH = OUTPUT_ROOT_RELATIVE / "baseline-transition.json"
TRANSITION_OLD_SHA256 = "a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e"
TRANSITION_V1_NEW_SHA256 = "be6aae6ec2d03ae3293f2954fb84be211483bd9c5b57e4ac3b546b7239db9eba"
TRANSITION_V2_NEW_SHA256 = "4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680"
# This is a separate, source-only continuation for the Curry scope.  It does
# not modify or broaden the historical v2 worker transition above.
CURRY_SCOPE_PROTECTED_SOURCE_CHANGE = {
    "scope": "curry-option-validation-v1",
    "path": "crates/ygo-engine-adapter/src/codec.rs",
    "old_sha256": "224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e",
    "new_sha256": "e8f97eefcf93ef626d2ecbc785661fde2fee47b0525e110ec7aee9a185aad133",
}
# Kept as the v1 alias for callers and tests that consume the original contract.
TRANSITION_NEW_SHA256 = TRANSITION_V1_NEW_SHA256
BASELINE_RELATIVE = Path("data/runtime/p1-tenki-probe-native-2026-10-21")
PREPARATION_RELATIVE = Path("data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json")
PREPARATION_SHA256 = "235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022"
FROZEN_CASES_SHA256 = "de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879"
PAUSE_ACCEPTANCE_SHA256 = "d73bdbdf1cdd9e8202ef7e3f88faf9de6b121e8c0aba2729c79e25e006e286a7"
BEFORE_SHA256 = "e24c17be7e2dd3496ca37ef7b38af4ebc02ca1058a0c237f953cb235acdd3d7e"
PAUSED_DELIVERY_CHECKPOINT_SHA256 = "2944d10e1d13b05e121b6c37c4bc2d4a8e5a64c069c2983772b6a58d2c8a6964"
RECOVERY_ACCEPTANCE_SHA256 = "c2ce85cfd2dcec696a9d5dc94343fa1e6a59985afb5a2300edfe5e05e744d9b1"
RECOVERY_CHECKPOINT_SHA256 = "0a8b0df13e5f71170fbb2afdd258af2452427aca0f12445e05151a4154275ab4"
OLD_STAGE1_SHA256 = "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76"
OLD_STAGE2_REQUEST_SHA256 = "cf2d94a3e5af74156c0bf47a3b380f7b7eab27c9784267fddb2d15a0f685284a"
OLD_STAGE2_SHA256 = "9c32ae3020afcc088b188a9d7770eeb5ec309dc3be86bff5c8e86b4e974429f4"
OLD_RUNNER_SHA256 = "d28c6678f39428552b0301b654f1a1961c2becb5ab794a8005be755abd142e4f"
OLD_LEDGER_MANIFEST = [
    ("baseline-2026-10-19", "b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a", 9),
    ("p1-state-native-2026-10-20", "0e50a03837676b8b19a1409b9ffa06bc7798ff61254109c10025c7733a3c410b", 8),
    ("p1-terminal-2026-10-20", "3fd2aa6d1ff18f5eb1fe7100fe8fb4c36e9b73795e0749aa362b0bea9ea93ef2", 1),
    ("p1-terminal-followup-2026-10-20", "68b134725597f62a888dd182b25bb0fb16cb2dbfcaf5154009b2242dc4bcc473", 4),
    ("p1-terminal-smoke-2026-10-20", "624b4843dc9cd09e07588074b2b4ecbd91737316c70e922a183f0dd9a5f137b0", 2),
    ("p1-tenki-probe-native-2026-10-21", "5337352e249a13eb51a5a6dd124bc2397c4402a68e99cd77c2bffc7da22392b6", 2),
]
OLD_CONSUMED = 26
LIMIT = 6
WINDOW_SECONDS = 7200
PLACEMENT_MASK = 0xFFFFE0FF
YES_NO_DESCRIPTION = 59877851398144
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}


def sha(path):
    return digest(regular_file(path).read_bytes())


def _verify_audit_snapshot(protected_inputs, source, repo):
    for path, expected in protected_inputs.items():
        require(sha(path) == expected, "baseline_input_changed_during_audit")
    require(stable_source(repo) == source, "baseline_source_changed_during_audit")


def expected_place_responses(raw):
    """Hand-written oracle for the frozen 18 frame and own spell/trap zones."""
    raw = bytes(raw)
    if len(raw) != 7 or raw[:3] != bytes([18, 0, 1]):
        raise ValueError("opcode18_frame_header_mismatch")
    if int.from_bytes(raw[3:7], "little") != PLACEMENT_MASK:
        raise ValueError("opcode18_mask_mismatch")
    return [[0, 8, sequence] for sequence in range(5)]


def select_zone_zero(prompt):
    if type(prompt.get("opcode")) is not int or prompt["opcode"] != 18 or prompt.get("player") != 0:
        raise ValueError("own_opcode18_prompt_required")
    expected = {
        "kind": "place",
        "zones": [{"player": 0, "location": 8, "sequence": 0}],
    }
    actions = prompt.get("actions")
    if not isinstance(actions, list) or len(actions) != 5:
        raise ValueError("five_spell_zone_actions_required")
    coordinates = set()
    responses = set()
    for item in actions:
        choice = item.get("choice") if isinstance(item, dict) else None
        zones = choice.get("zones") if isinstance(choice, dict) and choice.get("kind") == "place" else None
        data = item.get("bytes") if isinstance(item, dict) else None
        if not isinstance(zones, list) or len(zones) != 1 or not isinstance(data, list):
            raise ValueError("malformed_spell_zone_action")
        zone = zones[0]
        if zone != {"player": 0, "location": 8, "sequence": data[-1] if data else None}:
            raise ValueError("spell_zone_choice_response_mismatch")
        if type(zone.get("sequence")) is not int or not 0 <= zone["sequence"] <= 4:
            raise ValueError("spell_zone_sequence_invalid")
        if data != [0, 8, zone["sequence"]] or zone["sequence"] in coordinates:
            raise ValueError("duplicate_or_invalid_spell_zone_response")
        coordinates.add(zone["sequence"])
        responses.add(tuple(data))
    if coordinates != set(range(5)) or responses != {tuple([0, 8, i]) for i in range(5)}:
        raise ValueError("incomplete_spell_zone_response_set")
    matches = [item for item in actions if item.get("choice") == expected]
    if len(matches) != 1 or matches[0].get("bytes") != [0, 8, 0]:
        raise ValueError("unique_spell_zone_zero_action_required")
    return matches[0]


def _pending_raw(result, opcode):
    prompt = result.get("prompt")
    if not isinstance(prompt, dict) or prompt.get("opcode") != opcode or prompt.get("player") != 0:
        raise ValueError("expected_own_pending_prompt")
    frames = [
        event for event in result.get("events", [])
        if event.get("sequence") == prompt.get("id") and event.get("opcode") == opcode
    ]
    if len(frames) != 1:
        raise ValueError("pending_raw_frame_not_unique")
    raw = frames[0].get("raw")
    if not isinstance(raw, list) or any(type(byte) is not int or not 0 <= byte <= 255 for byte in raw):
        raise ValueError("pending_raw_frame_invalid")
    frame = frames[0]
    if frame.get("supported") is not True or frame.get("fields", {}).get("prompt") != prompt:
        raise ValueError("pending_raw_normalized_prompt_mismatch")
    return prompt, bytes(raw)


def _check_actions(raw, prompt, expected):
    actions = prompt.get("actions")
    if not isinstance(actions, list):
        raise ValueError("prompt_action_list_required")
    actual = []
    for action in actions:
        data = action.get("bytes") if isinstance(action, dict) else None
        if not isinstance(data, list) or any(type(byte) is not int or not 0 <= byte <= 255 for byte in data):
            raise ValueError("prompt_response_bytes_invalid")
        actual.append(data)
    if len(actual) != len(set(tuple(v) for v in actual)) or sorted(actual) != sorted(expected):
        raise ValueError("prompt_response_set_mismatch")
    if raw[0] == 18:
        expected_place_responses(raw)
    elif raw[0] == 13:
        mapped = {
            (False,): [0, 0, 0, 0],
            (True,): [1, 0, 0, 0],
        }
        seen = set()
        for action in actions:
            choice = action.get("choice", {})
            yes = choice.get("yes") if isinstance(choice, dict) and choice.get("kind") == "yes_no" else None
            if type(yes) is not bool or action.get("bytes") != mapped[(yes,)]:
                raise ValueError("yes_no_choice_response_mismatch")
            if yes in seen:
                raise ValueError("duplicate_yes_no_choice")
            seen.add(yes)
        if seen != {False, True}:
            raise ValueError("incomplete_yes_no_choices")


def _successful_parent(parent, stage):
    if (
        parent.get("schema_version") != 1
        or parent.get("kind") != "native_tenki_placement_stage"
        or parent.get("scope") != SCOPE
        or parent.get("stage") != stage
        or parent.get("successful") is not True
        or parent.get("proof_ready") is not False
        or parent.get("complete_action_coverage") is not False
        or parent.get("global_optimality") is not False
        or parent.get("native_probability_verified") is not False
        or parent.get("validation", {}).get("Ok", {}).get("response_oracle_matches") is not True
        or parent.get("diagnostic") is not None
        or parent.get("assets_unchanged") is not True
        or parent.get("assets_before") != parent.get("assets_after")
    ):
        raise ValueError("successful_parent_receipt_required")
    ledger = parent.get("ledger")
    if not isinstance(ledger, dict) or ledger != {
        "consumed": stage,
        "completed": stage,
        "unknown": 0,
        "reserved": 0,
        "abandoned": 0,
        "limit": LIMIT,
    }:
        raise ValueError("parent_receipt_not_bound_to_stage_prefix")
    result = parent.get("result", {}).get("Ok")
    if not isinstance(result, dict):
        raise ValueError("parent_result_required")
    if result.get("status") != "decision_required" or result.get("error") is not None or result.get("coverage_gaps"):
        raise ValueError("parent_result_not_clean_decision_required")
    resolved = result.get("resolved_decisions")
    request_decisions = parent.get("request", {}).get("decisions")
    if not isinstance(resolved, list) or not isinstance(request_decisions, list) or resolved[:len(request_decisions)] != request_decisions:
        raise ValueError("parent_decisions_not_consumed")
    return result


def derive_stage_request(stage, parent):
    """Derive a child only from a successful receipt and its actual raw menu."""
    parent_stage = {2: 1, 3: 2, 4: 3, 5: 2, 6: 5}.get(stage)
    if parent_stage is None:
        raise ValueError("unsupported_stage_derivation")
    result = _successful_parent(parent, parent_stage)
    request = copy.deepcopy(parent["request"])
    if stage in (4, 6):
        return request
    resolved = result["resolved_decisions"]
    if stage == 2:
        prompt, raw = _pending_raw(result, 18)
        _check_actions(raw, prompt, expected_place_responses(raw))
        action = select_zone_zero(prompt)
    else:
        prompt, raw = _pending_raw(result, 13)
        expected_raw = bytes([13, 0]) + YES_NO_DESCRIPTION.to_bytes(8, "little")
        expected = [[0, 0, 0, 0], [1, 0, 0, 0]]
        if raw != expected_raw:
            raise ValueError("opcode13_raw_prompt_mismatch")
        _check_actions(raw, prompt, expected)
        yes = stage == 5
        choice = {"kind": "yes_no", "yes": yes}
        actions = [a for a in prompt["actions"] if a.get("choice") == choice and a.get("bytes") == expected[int(yes)]]
        if len(actions) != 1:
            raise ValueError("opcode13_choice_not_unique")
        action = actions[0]
    request["decisions"] = copy.deepcopy(resolved) + [{
        "prompt_id": prompt["id"],
        "player": 0,
        "choice": copy.deepcopy(action["choice"]),
    }]
    return request


def summarize(context, stages, stats, diagnostic=None):
    settled = isinstance(stats, dict) and all(
        type(stats.get(key)) is int and stats[key] >= 0
        for key in ("consumed", "completed", "unknown", "reserved", "abandoned", "limit")
    )
    if settled:
        settled = (
            stats["limit"] == LIMIT
            and stats["consumed"] == stats["completed"] + stats["unknown"]
            and stats["abandoned"] <= stats["unknown"]
            and stats["consumed"] + stats["reserved"] <= LIMIT
        )
    if not settled:
        diagnostic = diagnostic or "stats_unavailable_or_inconsistent"
    elif stats["unknown"] or stats["reserved"]:
        diagnostic = diagnostic or "unresolved_consumption"
    ordered = [item.get("stage") for item in stages] == list(range(1, LIMIT + 1))
    replay_qualified = ordered and all(
        item.get("independent_replay_matches") is (True if item.get("stage") in (4, 6) else None)
        for item in stages
    )
    receipts_bound = ordered and all(
        isinstance(item.get("receipt_sha256"), str)
        and len(item["receipt_sha256"]) == 64
        and all(character in "0123456789abcdef" for character in item["receipt_sha256"])
        for item in stages
    )
    successful = (
        diagnostic is None
        and len(stages) == LIMIT
        and ordered
        and all(item.get("successful") is True for item in stages)
        and replay_qualified
        and receipts_bound
        and settled
        and stats["consumed"] == stats["completed"] == LIMIT
        and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0
    )
    if not successful:
        diagnostic = diagnostic or "incomplete_or_failed_stage"
    return {
        "schema_version": 1,
        "kind": "native_tenki_placement_summary",
        "scope": SCOPE,
        "context": context,
        "successful": successful,
        "diagnostic": diagnostic,
        "old_consumed": OLD_CONSUMED,
        "new_consumed": stats["consumed"] if settled else None,
        "cumulative_consumed": OLD_CONSUMED + stats["consumed"] if settled else None,
        "ledger": stats if settled else None,
        "stages": stages,
        **FLAGS,
    }


def add_arguments(parser):
    for name in ("baseline-dir", "runner", "worker", "build-record", "identity", "window-start", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--baseline-transition", type=Path)


def _read(path, expected=None):
    path = safe_path(path)
    raw = path.read_bytes()
    value = digest(raw)
    require(expected is None or value == expected, "pinned_baseline_hash_mismatch")
    return raw, value


def _read_source(path, repo, sources, expected=None):
    """Read a pinned historical file, optionally adding the recursive source pin."""
    if sources is not None:
        relative = Path(path).relative_to(repo).as_posix()
        source_pin = sources.file_sha256(relative)
        require(expected is None or expected == source_pin, "source_description_file_binding_mismatch")
        expected = source_pin
    return _read(path, expected)


def _check_evidence_map(base, entries, expected_count, *, repo=None,
                        _sources=None, dataset_name=None):
    if _sources is not None and dataset_name is not None:
        expected_count = _sources.dataset_count(dataset_name)
    require(isinstance(entries, dict) and len(entries) == expected_count, "baseline_evidence_count_mismatch")
    verified = {}
    for name, item in entries.items():
        require(isinstance(name, str) and isinstance(item, dict), "baseline_evidence_entry_invalid")
        require(set(item) >= {"sha256", "bytes"} and type(item["bytes"]) is int, "baseline_evidence_metadata_invalid")
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "baseline_evidence_path_unsafe")
        path = base / relative
        raw, actual = _read_source(path, repo, _sources, item["sha256"]) if _sources is not None else _read(path, item["sha256"])
        require(len(raw) == item["bytes"], "baseline_evidence_length_mismatch")
        verified[name] = actual
    return verified


def _verify_source_archive(recovery_dir, acceptance, *, repo=None, _sources=None):
    file_list_path = recovery_dir / "source-file-list.json"
    archive_path = recovery_dir / "final-source.zip"
    if _sources is None:
        archive_hash_expected = acceptance["source_archive_sha256"]
        file_list_hash_expected = acceptance["evidence"]["source-file-list.json"]["sha256"]
        source_identity = acceptance.get("source_identity")
        expected_count = 390
    else:
        archive_pin = _sources.archive("baseline_archive")
        require(
            repo is not None
            and archive_pin.archive_path == archive_path.relative_to(repo).as_posix()
            and archive_pin.file_list_path == file_list_path.relative_to(repo).as_posix(),
            "source_description_archive_path_mismatch",
        )
        archive_hash_expected = archive_pin.archive_sha256
        file_list_hash_expected = archive_pin.file_list_sha256
        source_identity = archive_pin.source_identity
        expected_count = archive_pin.file_count
        require(
            acceptance.get("source_archive_sha256") == archive_hash_expected
            and acceptance.get("source_identity") == source_identity
            and acceptance.get("source_file_count") == expected_count,
            "source_description_archive_binding_mismatch",
        )
    file_list_raw, file_list_hash = _read(file_list_path, file_list_hash_expected)
    archive_raw, archive_hash = _read(archive_path, archive_hash_expected)
    listing = strict_json(file_list_raw)
    require(listing.get("source_identity") == source_identity, "archive_source_identity_mismatch")
    files = listing.get("files")
    require(isinstance(files, dict) and len(files) == acceptance.get("source_file_count") == expected_count, "archive_file_list_count_mismatch")
    require(listing.get("file_count") == len(files), "archive_file_list_metadata_mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        require(len(members) == len(set(members)) and set(members) == set(files), "source_archive_membership_mismatch")
        for name, expected in files.items():
            require(digest(archive.read(name)) == expected, "source_archive_member_hash_mismatch")
    return {
        "source_identity": listing["source_identity"],
        "file_count": len(files),
        "file_list_sha256": file_list_hash,
        "archive_sha256": archive_hash,
    }


def _ledger_paths(repo, recovery_acceptance, *, _sources=None):
    expected = [
        ("baseline-2026-10-19", "data/runtime/baseline-2026-10-19/research/calls.jsonl", 9, OLD_LEDGER_MANIFEST[0][1]),
        ("p1-state-native-2026-10-20", "data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl", 8, OLD_LEDGER_MANIFEST[1][1]),
        ("p1-terminal-2026-10-20", "data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl", 1, OLD_LEDGER_MANIFEST[2][1]),
        ("p1-terminal-followup-2026-10-20", "data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl", 4, OLD_LEDGER_MANIFEST[3][1]),
        ("p1-terminal-smoke-2026-10-20", "data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl", 2, OLD_LEDGER_MANIFEST[4][1]),
        ("p1-tenki-probe-native-2026-10-21", "data/runtime/p1-tenki-probe-native-2026-10-21/research/calls.jsonl", 2, OLD_LEDGER_MANIFEST[5][1]),
    ]
    actual = recovery_acceptance.get("old_ledgers")
    expected_count = 5 if _sources is None else _sources.dataset_count("baseline_recovery_old_ledger_entries")
    require(isinstance(actual, list) and len(actual) == expected_count, "prior_five_ledgers_missing")
    declared = actual + [{
        "path": "data/runtime/p1-tenki-probe-native-2026-10-21/research/calls.jsonl",
        "sha256": recovery_acceptance.get("new_ledger_sha256"),
        "consumed": recovery_acceptance.get("new_ledger_consumed"),
        "unknown": recovery_acceptance.get("unknown"),
    }]
    verified = []
    for item, (role, relative_name, consumed, expected_hash) in zip(declared, expected, strict=True):
        if _sources is not None:
            expected_hash = _sources.file_sha256(relative_name)
            consumed = _sources.dataset_count(f"ledger_{role}_consumed")
        require(item.get("path") == relative_name and item.get("sha256") == expected_hash, "historical_ledger_anchor_mismatch")
        require(item.get("consumed") == consumed and item.get("unknown") == 0, "historical_ledger_consumption_mismatch")
        path = repo / relative_name
        raw, actual_hash = _read_source(path, repo, _sources, expected_hash) if _sources is not None else _read(path, expected_hash)
        require(actual_hash == item["sha256"], "historical_ledger_changed")
        verified.append({"role": role, "sha256": actual_hash, "consumed": consumed, "unknown": 0, "path": path})
    expected_total = OLD_CONSUMED if _sources is None else _sources.dataset_count("historical_consumed")
    require(sum(item["consumed"] for item in verified) == expected_total, "historical_total_not_26")
    return verified


def _seal_transition(payload):
    """Bind an offline single-file baseline migration record."""
    record = copy.deepcopy(payload)
    record["identity"] = digest(canonical(record))
    return record


def _transition_old_hash(*, _sources=None):
    value = (
        TRANSITION_OLD_SHA256
        if _sources is None
        else _sources.semantic_sha256("transition_old_worker_sha256")
    )
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None,
            "baseline_transition_hash_invalid")
    return value


def _transition_target_hash(report_version, *, _sources=None):
    if type(report_version) is not int:
        raise ValueError("baseline_transition_version_unsupported")
    if report_version == 1:
        return TRANSITION_V1_NEW_SHA256
    if report_version == 2:
        value = (
            TRANSITION_V2_NEW_SHA256
            if _sources is None
            else _sources.semantic_sha256("transition_new_worker_sha256")
        )
        require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None,
                "baseline_transition_hash_invalid")
        return value
    raise ValueError("baseline_transition_version_unsupported")


def _scope_protected_source_change(protection_scope, *, _sources=None):
    if protection_scope is None:
        return None
    require(
        protection_scope == CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["scope"],
        "protected_source_scope_unsupported",
    )
    source_change = dict(CURRY_SCOPE_PROTECTED_SOURCE_CHANGE)
    if _sources is not None:
        source_change["old_sha256"] = _sources.semantic_sha256("curry_scope_codec_old_sha256")
        source_change["new_sha256"] = _sources.semantic_sha256("curry_scope_codec_sha256")
        require(
            all(re.fullmatch(r"[a-f0-9]{64}", source_change[key]) is not None
                for key in ("old_sha256", "new_sha256")),
                "protected_source_hash_invalid")
    return source_change


def _validate_worker_transition(protected, actual, transition, expected_transition, *, _sources=None):
    require(transition is not None and expected_transition is not None,
            "baseline_transition_input_mismatch")
    require(
        isinstance(transition, dict)
        and isinstance(expected_transition, dict)
        and transition == expected_transition,
        "baseline_transition_input_mismatch",
    )
    version = expected_transition.get("schema_version")
    old_hash = _transition_old_hash(_sources=_sources)
    target_hash = _transition_target_hash(version, _sources=_sources)
    require(
        protected.get(TRANSITION_RELATIVE_PATH.as_posix()) == old_hash
        and actual.get(TRANSITION_RELATIVE_PATH.as_posix()) == target_hash,
        "historical_protected_input_changed",
    )
    require(
        transition.get("scope") == SCOPE
        and transition.get("schema_version") == version
        and transition.get("migration", {}).get("path") == TRANSITION_RELATIVE_PATH.as_posix()
        and transition.get("migration", {}).get("old_sha256") == old_hash
        and transition.get("migration", {}).get("observed_sha256") == target_hash
        and transition.get("identity") == digest(canonical({key: value for key, value in transition.items() if key != "identity"})),
        "baseline_transition_input_mismatch",
    )
    return target_hash


def _effective_protected_map(protected, actual, transition, expected_transition,
                             protection_scope=None, *, _sources=None):
    """Accept one explicitly verified scoped migration and no other drift."""
    require(isinstance(protected, dict) and isinstance(actual, dict) and protected.keys() == actual.keys(),
            "protected_file_count_mismatch")
    source_change = _scope_protected_source_change(protection_scope, _sources=_sources)
    transition_old = _transition_old_hash(_sources=_sources)
    allowed_scope_paths = set()
    if source_change is not None:
        path = source_change["path"]
        require(
            protected.get(path) == source_change["old_sha256"]
            and actual.get(path) == source_change["new_sha256"],
            "protected_source_change_hash_mismatch",
        )
        # The Curry codec exception is additive to, and always accompanies,
        # the already-audited debug-worker migration. Never accept the codec
        # delta on its own, even if the worker hash currently has no drift.
        _validate_worker_transition(protected, actual, transition, expected_transition, _sources=_sources)
        allowed_scope_paths.add(path)
    mismatches = [name for name in protected
                  if protected[name] != actual[name] and name not in allowed_scope_paths]
    if not mismatches:
        if source_change is None:
            require(transition is None and expected_transition is None, "baseline_transition_input_mismatch")
        return dict(actual)
    require(
        len(mismatches) == 1
        and mismatches[0] == TRANSITION_RELATIVE_PATH.as_posix()
        and protected[mismatches[0]] == transition_old,
        "historical_protected_input_changed",
    )
    if source_change is None:
        require(transition is not None and expected_transition is not None,
                "historical_protected_input_changed")
    _validate_worker_transition(protected, actual, transition, expected_transition, _sources=_sources)
    return dict(actual)


def _runtime_protected_map(baseline_protected, historical_ledgers):
    """Use the complete effective audit map; summaries intentionally have no paths."""
    require(isinstance(baseline_protected, dict), "baseline_protected_map_invalid")
    require(isinstance(historical_ledgers, list) and len(historical_ledgers) == 6,
            "historical_ledger_summary_invalid")
    for item in historical_ledgers:
        require(isinstance(item, dict) and set(item) == {"role", "sha256", "consumed", "unknown"},
                "historical_ledger_summary_invalid")
    return dict(baseline_protected)


def _has_sealed_slots(value):
    """The pinned recovery contract stores the sealed slot count, not a boolean."""
    return type(value) is int and value == 4


def _require_new_transition_output(path):
    require(not path.exists() and not path.is_symlink(), "baseline_transition_output_exists")


def _transition_capture_once(baseline, repo, report_version=1,
                             protection_scope=None, *, _sources=None):
    """Capture the exact inputs needed to authorize this scope-only migration."""
    target_hash = _transition_target_hash(report_version, _sources=_sources)
    transition_old = _transition_old_hash(_sources=_sources)
    before_path = baseline / "before.json"
    before_raw, before_hash = _read_source(
        before_path, repo, _sources, None if _sources is not None else BEFORE_SHA256,
    )
    before = strict_json(before_raw)
    protected = before.get("protected")
    protected_count = 366 if _sources is None else _sources.dataset_count("protected_file_count")
    historical_consumed = OLD_CONSUMED if _sources is None else _sources.dataset_count("historical_consumed")
    require(isinstance(protected, dict) and len(protected) == protected_count, "protected_file_count_mismatch")
    actual = {}
    for name, expected in protected.items():
        relative = Path(name)
        require(isinstance(name, str) and not relative.is_absolute() and ".." not in relative.parts,
                "protected_path_unsafe")
        require(isinstance(expected, str) and len(expected) == 64, "protected_hash_invalid")
        protected_path = repo / relative
        actual[name] = _read_source(protected_path, repo, _sources)[1] if _sources is not None else sha(protected_path)
    source_change = _scope_protected_source_change(protection_scope, _sources=_sources)
    allowed_scope_paths = set()
    if source_change is not None:
        path = source_change["path"]
        require(
            protected.get(path) == source_change["old_sha256"]
            and actual.get(path) == source_change["new_sha256"],
            "protected_source_change_hash_mismatch",
        )
        allowed_scope_paths.add(path)
    mismatches = [name for name in protected
                  if protected[name] != actual[name] and name not in allowed_scope_paths]
    require(
        len(mismatches) == 1
        and mismatches[0] == TRANSITION_RELATIVE_PATH.as_posix()
        and protected[mismatches[0]] == transition_old
        and actual[mismatches[0]] == target_hash,
        "historical_protected_input_changed",
    )

    pause_path = baseline / "pause-acceptance.json"
    delivery_path = baseline / "delivery-checkpoint.json"
    pause_raw, pause_hash = _read_source(
        pause_path, repo, _sources, None if _sources is not None else PAUSE_ACCEPTANCE_SHA256,
    )
    delivery_raw, delivery_hash = _read_source(
        delivery_path, repo, _sources,
        None if _sources is not None else PAUSED_DELIVERY_CHECKPOINT_SHA256,
    )
    recovery_dir = baseline / "recovery-2026-10-22"
    recovery_path = recovery_dir / "recovery-acceptance.json"
    checkpoint_path = recovery_dir / "recovery-checkpoint.json"
    recovery_raw, recovery_hash = _read_source(
        recovery_path, repo, _sources,
        None if _sources is not None else RECOVERY_ACCEPTANCE_SHA256,
    )
    checkpoint_raw, checkpoint_hash = _read_source(
        checkpoint_path, repo, _sources,
        None if _sources is not None else RECOVERY_CHECKPOINT_SHA256,
    )
    recovery = strict_json(recovery_raw)
    checkpoint = strict_json(checkpoint_raw)
    require(
        recovery.get("kind") == "tenki_contract_recovery_acceptance"
        and recovery.get("paused_checkpoint_sha256") == delivery_hash
        and recovery.get("cumulative_consumed") == historical_consumed
        and recovery.get("unknown") == 0
        and checkpoint.get("kind") == "tenki_contract_recovery_checkpoint"
        and checkpoint.get("acceptance_sha256") == recovery_hash
        and checkpoint.get("source_identity") == recovery.get("source_identity"),
        "recovery_acceptance_mismatch",
    )
    archive = _verify_source_archive(recovery_dir, recovery, repo=repo, _sources=_sources)
    if source_change is not None:
        with zipfile.ZipFile(recovery_dir / "final-source.zip") as source_archive:
            require(
                digest(source_archive.read(source_change["path"]))
                == source_change["old_sha256"],
                "protected_source_change_historical_archive_mismatch",
            )
    ledgers = _ledger_paths(repo, recovery, _sources=_sources)
    source = stable_source(repo)
    module_hash = sha(Path(__file__))
    ledger_summary = []
    input_hashes = {
        "before": before_hash,
        "pause_acceptance": pause_hash,
        "paused_delivery_checkpoint": delivery_hash,
        "recovery_acceptance": recovery_hash,
        "recovery_checkpoint": checkpoint_hash,
        "protected_map": digest(canonical(protected)),
        "source_archive": archive["archive_sha256"],
        "source_file_list": archive["file_list_sha256"],
        "audit_tool_source": source["identity"],
        "audit_tool_module": module_hash,
    }
    for item in ledgers:
        relative_path = Path(item["path"]).relative_to(repo).as_posix()
        ledger_summary.append({
            "role": item["role"],
            "path": relative_path,
            "sha256": item["sha256"],
            "consumed": item["consumed"],
            "unknown": item["unknown"],
        })
        input_hashes["ledger_" + item["role"]] = item["sha256"]
    return {
        "schema_version": report_version,
        "kind": "tenki_placement_baseline_transition",
        "scope": SCOPE,
        "baseline": {
            "before_sha256": before_hash,
            "pause_acceptance_sha256": pause_hash,
            "paused_delivery_checkpoint_sha256": delivery_hash,
            "recovery_acceptance_sha256": recovery_hash,
            "recovery_checkpoint_sha256": checkpoint_hash,
            "source_archive_sha256": archive["archive_sha256"],
            "source_file_list_sha256": archive["file_list_sha256"],
            "source_identity": recovery["source_identity"],
            "source_file_count": archive["file_count"],
            "historical_ledgers": ledger_summary,
            "protected_file_count": len(protected),
            "matched_protected_count": len(protected) - 1,
        },
        "migration": {
            "path": TRANSITION_RELATIVE_PATH.as_posix(),
            "old_sha256": transition_old,
            "observed_sha256": target_hash,
            "old_protection_check": "failed",
            "current_file_history": "unknown",
            "effective_protection_mapping": "migrated_for_this_scope",
        },
        "audit_tool": {"source_identity": source["identity"], "module_sha256": module_hash},
        "claims": {
            "old_protection_check_passed": False,
            "binary_provenance_verified": False,
            "historical_reexecution_verified": False,
            "future_protection_mapping_migrated": True,
        },
        "input_sha256": input_hashes,
    }


def _transition_payload_from_current(baseline, repo, report_version=1,
                                     protection_scope=None, *, _sources=None):
    """Double-capture migration inputs so drift during collection is rejected."""
    _transition_target_hash(report_version, _sources=_sources)
    first = _transition_capture_once(
        baseline, repo, report_version, protection_scope, _sources=_sources,
    )
    second = _transition_capture_once(
        baseline, repo, report_version, protection_scope, _sources=_sources,
    )
    require(first == second, "baseline_transition_inputs_changed_during_capture")
    return first


def _transition_payload_with_tool_override(current_payload, override_payload):
    """Allow a pinned historical tool identity while binding every other field to current inputs."""
    require(
        isinstance(current_payload, dict)
        and isinstance(override_payload, dict)
        and set(override_payload) == set(current_payload),
        "baseline_transition_override_invalid",
    )
    tool = override_payload.get("audit_tool")
    require(
        isinstance(tool, dict)
        and set(tool) == {"source_identity", "module_sha256"}
        and all(
            isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None
            for value in tool.values()
        ),
        "baseline_transition_override_invalid",
    )
    adjusted = copy.deepcopy(current_payload)
    adjusted["audit_tool"] = copy.deepcopy(tool)
    input_hashes = adjusted.get("input_sha256")
    supplied_hashes = override_payload.get("input_sha256")
    require(
        isinstance(input_hashes, dict)
        and isinstance(supplied_hashes, dict)
        and set(supplied_hashes) == set(input_hashes)
        and tool.get("source_identity") == supplied_hashes.get("audit_tool_source")
        and tool.get("module_sha256") == supplied_hashes.get("audit_tool_module"),
        "baseline_transition_override_invalid",
    )
    input_hashes["audit_tool_source"] = tool["source_identity"]
    input_hashes["audit_tool_module"] = tool["module_sha256"]
    require(override_payload == adjusted, "baseline_transition_override_invalid")
    return adjusted


def _validate_transition_file(path, expected_payload, repo):
    require(Path(os.path.abspath(path)) == repo / TRANSITION_FILE_PATH, "fixed_baseline_transition_path_required")
    raw = safe_path(path).read_bytes()
    report = strict_json(raw)
    expected = _seal_transition(expected_payload)
    require(report == expected, "baseline_transition_input_mismatch")
    require(report.get("identity") == digest(canonical({key: value for key, value in report.items() if key != "identity"})),
            "baseline_transition_identity_mismatch")
    return report, digest(raw)


def prepare_tenki_baseline_transition(args, repo=None):
    """Create a new, offline-only record for the one authorized protected-file change."""
    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    baseline = Path(os.path.abspath(args.baseline_dir))
    output = Path(os.path.abspath(args.output))
    root = repo / OUTPUT_ROOT_RELATIVE
    require(baseline == repo / BASELINE_RELATIVE, "frozen_baseline_directory_required")
    require(output == repo / TRANSITION_FILE_PATH, "fixed_baseline_transition_path_required")
    report_version = getattr(args, "report_version", 1)
    _transition_target_hash(report_version)
    _require_new_transition_output(output)
    safe_path(repo / "data" / "runtime", False)
    if root.exists():
        safe_path(root, False)
    ignored = safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    require(any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime") for line in ignored)
            and not any(line.lstrip().startswith("!") for line in ignored), "ignored_output_contract_missing")
    payload = _transition_payload_from_current(baseline, repo, report_version)
    # Re-run the full historical audit and the saved runner's zero-call receipt checks before sealing.
    audit, _ = audit_baseline(
        baseline, repo, allow_transition_candidate=True, report_version=report_version
    )
    require(audit.get("native_calls") == 0 and audit.get("historical_consumed") == OLD_CONSUMED and audit.get("unknown") == 0,
            "baseline_transition_audit_failed")
    final_payload = _transition_payload_from_current(baseline, repo, report_version)
    require(final_payload == payload, "baseline_transition_inputs_changed_during_capture")
    record = _seal_transition(payload)
    schema_path = repo / "schemas" / f"tenki-placement-baseline-transition{'-v2' if report_version == 2 else ''}.schema.json"
    require(safe_path(schema_path).is_file(), "baseline_transition_schema_missing")
    _require_new_transition_output(output)
    immutable_write(output, record)
    return record


def _collect_baseline_audit(
    baseline,
    repo,
    transition_path=None,
    allow_transition_candidate=False,
    report_version=1,
    verify_legacy_runner=True,
    transition_payload_override=None,
    protection_scope=None,
    *,
    _sources=None,
):
    """Collect sealed history; optionally invoke the authenticated legacy runner."""
    baseline = safe_path(baseline, False)
    require(baseline == repo / BASELINE_RELATIVE, "frozen_baseline_directory_required")
    recovery_dir = baseline / "recovery-2026-10-22"
    protected_inputs = {}
    historical_consumed = OLD_CONSUMED if _sources is None else _sources.dataset_count("historical_consumed")
    source_file = lambda path, expected=None: (
        _read_source(path, repo, _sources, None)
        if _sources is not None else _read(path, expected)
    )
    pause_path = baseline / "pause-acceptance.json"
    pause_raw, pause_hash = source_file(pause_path, PAUSE_ACCEPTANCE_SHA256)
    protected_inputs[pause_path] = pause_hash
    pause = strict_json(pause_raw)
    delivery_path = baseline / "delivery-checkpoint.json"
    delivery_raw, delivery_hash = source_file(delivery_path, PAUSED_DELIVERY_CHECKPOINT_SHA256)
    protected_inputs[delivery_path] = delivery_hash
    delivery_checkpoint = strict_json(delivery_raw)
    require(
        delivery_checkpoint.get("kind") == "tenki_prompt_probe_paused_checkpoint"
        and delivery_checkpoint.get("status") == "paused_incomplete"
        and delivery_checkpoint.get("cumulative_consumed") == historical_consumed
        and delivery_checkpoint.get("unknown") == 0
        and delivery_checkpoint.get("remaining_slots_sealed") == 4,
        "paused_delivery_checkpoint_mismatch",
    )
    recovery_path = recovery_dir / "recovery-acceptance.json"
    recovery_raw, recovery_hash = source_file(recovery_path, RECOVERY_ACCEPTANCE_SHA256)
    protected_inputs[recovery_path] = recovery_hash
    recovery = strict_json(recovery_raw)
    checkpoint_path = recovery_dir / "recovery-checkpoint.json"
    checkpoint_raw, checkpoint_hash = source_file(checkpoint_path, RECOVERY_CHECKPOINT_SHA256)
    protected_inputs[checkpoint_path] = checkpoint_hash
    checkpoint = strict_json(checkpoint_raw)
    require(
        pause.get("kind") == "tenki_prompt_probe_pause_acceptance"
        and pause.get("native_source_identity") == (
            "6a838b72d583eb9c5bd3a5ff13c140c3a1782cfc19dc84562624c4a3c0a3da76"
            if _sources is None else _sources.semantic_sha256("baseline_pause_source_identity")
        )
        and pause.get("cumulative_consumed") == historical_consumed
        and pause.get("unknown") == 0
        and pause.get("native_calls_new") == 2
        and pause.get("remaining_slots_sealed") == 4
        and pause.get("native_stages") == [
            {"stage": 1, "opcode": 11, "prompt_id": 7, "successful": True, "native_replay_verified": False},
            {"stage": 2, "opcode": 18, "prompt_id": 9, "successful": False, "native_replay_verified": False, "diagnostic": "unexpected_intermediate_prompt"},
        ],
        "paused_acceptance_mismatch",
    )
    pause_evidence_count = 61 if _sources is None else _sources.dataset_count("pause_evidence_count")
    require(len(pause.get("evidence", {})) == pause_evidence_count, "paused_evidence_count_mismatch")
    pause_evidence = _check_evidence_map(
        baseline, pause["evidence"], pause_evidence_count, repo=repo,
        _sources=_sources, dataset_name="pause_evidence_count",
    )
    protected_inputs.update({baseline / name: value for name, value in pause_evidence.items()})
    before_path = baseline / "before.json"
    before_raw, before_hash = source_file(before_path, BEFORE_SHA256)
    protected_inputs[before_path] = before_hash
    before = strict_json(before_raw)
    protected = before.get("protected")
    protected_file_count = 366 if _sources is None else _sources.dataset_count("protected_file_count")
    require(isinstance(protected, dict) and len(protected) == protected_file_count, "protected_file_count_mismatch")
    protected_actual = {}
    for name, expected in protected.items():
        path = repo / Path(name)
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "protected_path_unsafe")
        protected_actual[name] = source_file(path)[1] if _sources is not None else sha(path)
    if transition_path is not None:
        require(Path(os.path.abspath(transition_path)) == repo / TRANSITION_FILE_PATH,
                "fixed_baseline_transition_path_required")
    require(not (transition_path is not None and allow_transition_candidate), "invalid_transition_audit_mode")
    if allow_transition_candidate:
        require(transition_path is None, "invalid_transition_audit_mode")
        _transition_target_hash(report_version, _sources=_sources)
        effective_protected = None
    elif transition_path is None:
        # Strict mode checks all 366 paths directly; it never invents a migration record.
        effective_protected = _effective_protected_map(
            protected, protected_actual, None, None, _sources=_sources,
        )
    else:
        effective_protected = None

    require(
        recovery.get("kind") == "tenki_contract_recovery_acceptance"
        and recovery.get("paused_acceptance_sha256") == pause_hash
        and recovery.get("paused_checkpoint_sha256") == delivery_hash
        and recovery.get("source_identity") == (
            "8bcd16e223a69e2053e37e2b380a7b8849bd540292661e79c327585b13496868"
            if _sources is None else _sources.archive("baseline_archive").source_identity
        )
        and recovery.get("source_file_count") == (
            390 if _sources is None else _sources.archive("baseline_archive").file_count
        )
        and recovery.get("evidence_scope") == "recovery directory contents except this acceptance and its linked checkpoint"
        and recovery.get("recovery_native_calls") == 0
        and recovery.get("cumulative_consumed") == historical_consumed
        and recovery.get("old_ledger_consumed") == 24
        and recovery.get("new_ledger_consumed") == 2
        and recovery.get("unknown") == 0
        and recovery.get("stage1_native_success_preserved") is True
        and recovery.get("stage2_native_success") is False
        and recovery.get("stage2_diagnostic") == "unexpected_intermediate_prompt"
        and recovery.get("stage2_opcode") == 18
        and recovery.get("stage2_prompt") == 9
        and _has_sealed_slots(recovery.get("remaining_slots_sealed")),
        "recovery_acceptance_mismatch",
    )
    recovery_evidence_count = 16 if _sources is None else _sources.dataset_count("recovery_evidence_count")
    recovery_evidence = _check_evidence_map(
        recovery_dir, recovery.get("evidence"), recovery_evidence_count, repo=repo,
        _sources=_sources, dataset_name="recovery_evidence_count",
    )
    protected_inputs.update({recovery_dir / name: value for name, value in recovery_evidence.items()})
    archive = _verify_source_archive(recovery_dir, recovery, repo=repo, _sources=_sources)
    prepared_raw, prepared_hash = source_file(repo / PREPARATION_RELATIVE, PREPARATION_SHA256)
    protected_inputs[repo / PREPARATION_RELATIVE] = prepared_hash
    prepared = strict_json(prepared_raw)
    tenki_candidates = [item for item in prepared.get("candidates", []) if item.get("case", {}).get("case_id") == "prompt-13-tenki-v1"]
    require(len(tenki_candidates) == 1 and tenki_candidates[0].get("target") == {"opcode": 13, "card_id": 57103969, "name": "tenki"}, "frozen_tenki_preparation_missing")
    previous_report_path = repo / Path("data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/report.json")
    previous_report_hash = source_file(previous_report_path)[1] if _sources is not None else sha(previous_report_path)
    protected_inputs[previous_report_path] = previous_report_hash
    previous_report = strict_json(safe_path(previous_report_path).read_bytes())
    previous_manifest_path = baseline / "research" / "manifest.json"
    previous_manifest_hash = source_file(previous_manifest_path)[1] if _sources is not None else sha(previous_manifest_path)
    protected_inputs[previous_manifest_path] = previous_manifest_hash
    previous_manifest = strict_json(safe_path(previous_manifest_path).read_bytes())
    frozen_cases_hash = FROZEN_CASES_SHA256 if _sources is None else _sources.semantic_sha256("baseline_frozen_cases")
    require(previous_report.get("input_sha256", {}).get("frozen_cases") == frozen_cases_hash and previous_manifest.get("preparation_sha256") == prepared_hash, "frozen_case_preparation_binding_mismatch")
    require(checkpoint.get("kind") == "tenki_contract_recovery_checkpoint" and checkpoint.get("acceptance_sha256") == recovery_hash and checkpoint.get("source_identity") == recovery["source_identity"], "recovery_checkpoint_mismatch")
    ledger_records = _ledger_paths(repo, recovery, _sources=_sources)
    protected_inputs.update({item["path"]: item["sha256"] for item in ledger_records})

    transition_payload = None
    expected_transition = None
    transition_record = None
    transition_hash = None
    if transition_path is not None:
        transition_document = strict_json(safe_path(transition_path).read_bytes())
        report_version = transition_document.get("schema_version")
        _transition_target_hash(report_version, _sources=_sources)
        if transition_payload_override is not None:
            require(
                isinstance(transition_payload_override, dict)
                and transition_payload_override.get("schema_version") == report_version,
                "baseline_transition_override_invalid",
            )
            current_payload = _transition_payload_from_current(
                baseline, repo, report_version, protection_scope, _sources=_sources,
            )
            transition_payload = _transition_payload_with_tool_override(
                current_payload, transition_payload_override
            )
        else:
            transition_payload = _transition_payload_from_current(
                baseline, repo, report_version, protection_scope, _sources=_sources,
            )
        expected_transition = _seal_transition(transition_payload)
        transition_record, transition_hash = _validate_transition_file(transition_path, transition_payload, repo)
    elif allow_transition_candidate:
        transition_payload = _transition_payload_from_current(
            baseline, repo, report_version, protection_scope, _sources=_sources,
        )
        expected_transition = _seal_transition(transition_payload)
        transition_record = expected_transition
    if transition_record is not None:
        effective_protected = _effective_protected_map(
            protected, protected_actual, transition_record, expected_transition,
            protection_scope, _sources=_sources,
        )
    require(isinstance(effective_protected, dict), "effective_protected_map_missing")
    protected_inputs.update({repo / Path(name): value for name, value in effective_protected.items()})
    if transition_hash is not None:
        protected_inputs[Path(os.path.abspath(transition_path))] = transition_hash
    audit_source = stable_source(repo)

    research = baseline / "research"
    stage1_path = research / "stage-1.json"
    stage1_request_path = research / "stage-1-request.json"
    stage1_input_path = research / "stage-1-input.json"
    stage2_request_path = research / "stage-2-request.json"
    stage2_path = research / "stage-2.json"
    runner = baseline / "native-artifacts" / "prompt-probe.exe"
    fixed = {
        stage1_path: OLD_STAGE1_SHA256,
        stage2_request_path: OLD_STAGE2_REQUEST_SHA256,
        stage2_path: OLD_STAGE2_SHA256,
        runner: OLD_RUNNER_SHA256,
    }
    if _sources is not None:
        fixed = {
            path: _sources.file_sha256(path.relative_to(repo).as_posix())
            for path in fixed
        }
    raw_before = {
        path: (source_file(path, expected)[0] if _sources is not None else _read(path, expected)[0])
        for path, expected in fixed.items()
    }
    protected_inputs.update({path: digest(raw) for path, raw in raw_before.items()})
    stage1_request = strict_json((stage1_request_path).read_bytes())
    stage1_input = strict_json(stage1_input_path.read_bytes())
    stage2_request = strict_json(stage2_request_path.read_bytes())
    old1 = strict_json(raw_before[stage1_path])
    old2 = strict_json(raw_before[stage2_path])
    require(stage1_request == old1.get("request") and stage1_input.get("request") == stage1_request, "old_stage1_request_binding_mismatch")
    require(stage2_request == old2.get("request") and old2.get("successful") is False and old2.get("diagnostic") == "unexpected_intermediate_prompt", "old_stage2_failure_binding_mismatch")
    pending = old2.get("result", {}).get("Ok", {}).get("prompt", {})
    require(pending.get("id") == 9 and pending.get("opcode") == 18 and pending.get("player") == 0, "old_stage2_region_source_mismatch")
    require(old2.get("result", {}).get("Ok", {}).get("events", [])[-1].get("raw") == [18, 0, 1, 255, 224, 255, 255], "old_stage2_raw_region_frame_mismatch")

    verify_results = []
    stats_output = None
    if verify_legacy_runner:
        for stage, input_path, expected_success in ((1, research / "stage-1-input.json", True), (2, research / "stage-2-input.json", False)):
            input_raw, input_hash = source_file(input_path)
            invocation = strict_json(input_raw)
            require(invocation.get("stage") == stage and invocation.get("output") == str(research / f"stage-{stage}.json"), "old_stage_input_binding_mismatch")
            command = [str(runner), str(input_path), "--input-sha", input_hash, "--verify-recorded"]
            completed = subprocess.run(command, cwd=repo, capture_output=True, timeout=60)
            require(completed.returncode in (0, 1), "old_zero_call_receipt_verification_failed")
            output = strict_json(completed.stdout)
            require(output.get("verified_recorded") is True and output.get("native_calls") == 0 and output.get("successful") is expected_success, "old_zero_call_receipt_result_mismatch")
            ledger = output.get("ledger")
            require(isinstance(ledger, dict) and ledger.get("consumed") == 2 and ledger.get("completed") == 2 and ledger.get("unknown") == 0 and ledger.get("reserved") == 0, "old_runner_receipt_stats_mismatch")
            verify_results.append({"stage": stage, "verified_recorded": True, "successful": expected_success, "native_calls": 0, "ledger": ledger})
        stats_input = research / "stage-2-input.json"
        stats_hash = source_file(stats_input)[1] if _sources is not None else sha(stats_input)
        stats_run = subprocess.run([str(runner), str(stats_input), "--input-sha", stats_hash, "--stats"], cwd=repo, capture_output=True, timeout=60)
        require(stats_run.returncode == 0, "old_zero_call_stats_failed")
        stats_value = strict_json(stats_run.stdout)
        require(stats_value.get("native_calls") == 0 and stats_value.get("ledger", {}).get("consumed") == 2 and stats_value.get("ledger", {}).get("unknown") == 0, "old_zero_call_stats_mismatch")
        stats_output = stats_value
    else:
        # This mode is used by offline audit tooling. It hashes and validates the
        # historical runner, but never starts it or opens its journal.
        for stage, input_path in ((1, research / "stage-1-input.json"), (2, research / "stage-2-input.json")):
            invocation = strict_json(source_file(input_path)[0])
            require(invocation.get("stage") == stage and invocation.get("output") == str(research / f"stage-{stage}.json"), "old_stage_input_binding_mismatch")
    for path, old_raw in raw_before.items():
        require(safe_path(path).read_bytes() == old_raw, "historical_receipt_or_runner_changed")
    for item in ledger_records:
        require(safe_path(item["path"]).read_bytes() and sha(item["path"]) == item["sha256"], "historical_ledger_changed_during_verification")

    if transition_payload is not None:
        current_payload = _transition_payload_from_current(
            baseline, repo, report_version, protection_scope, _sources=_sources,
        )
        if transition_payload_override is not None:
            current_payload = _transition_payload_with_tool_override(
                current_payload, transition_payload_override
            )
        require(
            current_payload == transition_payload,
            "baseline_transition_inputs_changed_during_capture",
        )

    _verify_audit_snapshot(protected_inputs, audit_source, repo)

    report = {
        "schema_version": 1,
        "kind": "tenki_placement_baseline_audit",
        "pause_acceptance_sha256": pause_hash,
        "recovery_acceptance_sha256": recovery_hash,
        "recovery_checkpoint_sha256": checkpoint_hash,
        "pause_evidence_count": len(pause_evidence),
        "recovery_evidence_count": len(recovery_evidence),
        "protected_file_count": len(protected),
        "baseline_transition": ({
            "identity": transition_record["identity"],
            "sha256": transition_hash,
            "report_version": report_version,
            "scope": SCOPE,
            "old_protection_check": "failed",
            "current_file_history": "unknown",
        } if transition_record is not None else None),
        "source_archive": archive,
        "preparation_sha256": prepared_hash,
        "frozen_cases_sha256": FROZEN_CASES_SHA256,
        "historical_ledgers": [{key: item[key] for key in ("role", "sha256", "consumed", "unknown")} for item in ledger_records],
        "historical_consumed": OLD_CONSUMED,
        "unknown": 0,
        "old_runner_available": True,
        "old_binary_provenance_verified": False,
        "historical_reexecution_verified": False,
        "old_stage_receipts": verify_results,
        "old_stats": stats_output["ledger"] if stats_output is not None else None,
        "native_calls": 0,
        "audit_source_identity": audit_source["identity"],
        **FLAGS,
    }
    return report, protected_inputs


def audit_baseline(baseline, repo, transition_path=None, allow_transition_candidate=False, report_version=1, *, _sources=None):
    """Verify sealed history and zero-call receipts using the saved legacy runner."""
    return _collect_baseline_audit(
        baseline, repo, transition_path, allow_transition_candidate, report_version, True,
        _sources=_sources,
    )


def collect_baseline_bytes(baseline, repo, transition_path=None, report_version=1,
                           transition_payload_override=None,
                           protection_scope=None, *, _sources=None):
    """Validate sealed historical files and ledgers without starting any runner."""
    return _collect_baseline_audit(
        baseline, repo, transition_path, False, report_version, False,
        transition_payload_override, protection_scope, _sources=_sources,
    )


def _activation_from_history(old_stage1, old_stage2_request):
    result = old_stage1.get("result", {}).get("Ok")
    require(isinstance(result, dict) and result.get("status") == "decision_required" and result.get("error") is None, "old_stage1_clean_idle_required")
    prompt = result.get("prompt")
    require(isinstance(prompt, dict) and prompt.get("opcode") == 11 and prompt.get("player") == 0 and prompt.get("id") == 7, "old_stage1_idle_mismatch")
    matches = [event for event in result.get("events", []) if event.get("sequence") == prompt["id"] and event.get("opcode") == 11]
    require(len(matches) == 1 and matches[0].get("supported") is True and matches[0].get("fields", {}).get("prompt") == prompt, "old_stage1_idle_frame_missing")
    raw = matches[0].get("raw")
    require(isinstance(raw, list) and raw[:2] == [11, 0] and len(raw) >= 29, "old_stage1_idle_raw_frame_invalid")
    actions = prompt.get("actions")
    require(isinstance(actions, list), "old_stage1_action_list_missing")
    activation = {"kind": "command", "command": 5, "index": 0}
    selected = [item for item in actions if item.get("choice") == activation and item.get("card_ids") == [57103969] and item.get("bytes") == [5, 0, 0, 0]]
    require(len(selected) == 1, "old_stage1_unique_tenki_activation_missing")
    old_request = old_stage1.get("request")
    require(isinstance(old_request, dict) and old_request.get("decisions") == [], "old_stage1_request_not_empty")
    derived = copy.deepcopy(old_request)
    derived["decisions"] = copy.deepcopy(result.get("resolved_decisions", [])) + [{"prompt_id": prompt["id"], "player": 0, "choice": activation}]
    require(derived == old_stage2_request, "old_stage2_request_not_exact_activation_derivation")
    return derived


def _validate_signed(value, kind):
    require(isinstance(value, dict) and value.get("kind") == kind, "signed_record_kind_mismatch")
    unsigned = {key: item for key, item in value.items() if key != "identity"}
    require(value.get("identity") == digest(canonical(unsigned)), "signed_record_identity_mismatch")


def _candidate_configs(repo, root, worker, baseline):
    configs = {}
    for role, name in (("ordinary", "ordinary-candidate.toml"), ("tournament", "tournament-candidate.toml")):
        source = safe_path(baseline / name).read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        worker_lines = [index for index, line in enumerate(lines) if line.lstrip().startswith("worker_path")]
        require(len(worker_lines) == 1, "candidate_worker_path_not_unique")
        old_line = lines[worker_lines[0]]
        quote = "'" if "'" in old_line else '"'
        prefix = old_line[:len(old_line) - len(old_line.lstrip())]
        lines[worker_lines[0]] = f"{prefix}worker_path = {quote}{str(worker)}{quote}\n"
        config = root / f"{role}-candidate.toml"
        encoded = "".join(lines).encode("utf-8")
        if config.exists():
            require(safe_path(config).read_bytes() == encoded, "candidate_config_already_differs")
        else:
            config.parent.mkdir(parents=True, exist_ok=True)
            with config.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        configs[role] = config
    return configs


def _window(root, path):
    require(path == root / "window-start.json", "fixed_window_path_required")
    if path.exists():
        value = strict_json(safe_path(path).read_bytes())
        require(value.get("schema_version") == 1 and value.get("kind") == "tenki_placement_window_start" and value.get("scope") == SCOPE and value.get("limit") == LIMIT and value.get("wall_seconds") == WINDOW_SECONDS and type(value.get("started_at")) is int and 0 <= value["started_at"] <= int(time.time()), "existing_window_start_mismatch")
        return value
    value = {"schema_version": 1, "kind": "tenki_placement_window_start", "scope": SCOPE, "limit": LIMIT, "wall_seconds": WINDOW_SECONDS, "started_at": int(time.time())}
    immutable_write(path, value)
    return value


def _capture_identity(repo, cli, configs, identity_path):
    command = [
        sys.executable, "-m", "ygo_data.identity", "capture",
        "--cli", str(cli),
        "--ordinary-config", str(configs["ordinary"]),
        "--tournament-config", str(configs["tournament"]),
        "--repo", str(repo), "--output", str(identity_path),
    ]
    if identity_path.exists():
        return strict_json(safe_path(identity_path).read_bytes())
    completed = subprocess.run(command, cwd=repo, capture_output=True, timeout=900)
    require(completed.returncode == 0 and identity_path.exists(), "candidate_identity_capture_failed")
    return strict_json(safe_path(identity_path).read_bytes())


def _archive_current_source(repo, root, source):
    archive_path = root / "source-native.zip"
    listing_path = root / "source-native-file-list.json"
    file_map = source.get("files")
    require(isinstance(file_map, dict), "source_file_map_missing")
    listing = {"schema_version": 1, "kind": "workspace_source_archive", "head": source.get("head"), "source_identity": source["identity"], "file_count": len(file_map), "files": file_map}
    if listing_path.exists() or archive_path.exists():
        require(listing_path.exists() and archive_path.exists(), "partial_source_archive")
        require(strict_json(safe_path(listing_path).read_bytes()) == listing, "saved_source_file_list_differs")
        with zipfile.ZipFile(archive_path) as archive:
            require(set(archive.namelist()) == set(file_map) and len(archive.namelist()) == len(file_map), "saved_source_archive_membership_differs")
            for name, expected in file_map.items():
                require(digest(archive.read(name)) == expected, "saved_source_archive_hash_differs")
    else:
        with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, expected in sorted(file_map.items()):
                data = safe_path(repo / name).read_bytes()
                require(digest(data) == expected, "source_changed_during_archiving")
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, data)
        immutable_write(listing_path, listing)
    require(stable_source(repo) == source, "source_changed_during_archiving")
    return {"sha256": sha(archive_path), "file_list_sha256": sha(listing_path), "file_count": len(file_map)}


def _assert_runtime_identity(identity, worker, request):
    _validate_signed(identity, "workspace_identity")
    require(identity.get("consistent") is True and identity.get("build_provenance") == "unverified" and identity.get("reproducible_build_proven") is False, "candidate_identity_qualification_mismatch")
    ordinary = identity.get("runtimes", {}).get("ordinary")
    tournament = identity.get("runtimes", {}).get("tournament")
    require(isinstance(ordinary, dict) and ordinary.get("consistent") is True and isinstance(tournament, dict) and tournament.get("consistent") is True, "dual_runtime_identity_required")
    require(ordinary["roles"]["worker"]["sha256"] == sha(worker), "ordinary_worker_identity_mismatch")
    versions = request["versions"]
    for role, version_key in (("dll", "engine_sha256"), ("cdb", "cdb_sha256"), ("script_manifest", "scripts_sha256")):
        require(ordinary["roles"][role]["sha256"] == versions[version_key], "ordinary_asset_identity_mismatch")
    return ordinary, tournament


def validate_schema(value, kind, repo):
    """Small runtime guard; the published JSON Schema remains the full contract."""
    require(isinstance(value, dict) and value.get("schema_version") == 1 and value.get("kind") == kind, "report_contract_kind_mismatch")
    for flag in FLAGS:
        require(value.get(flag) is False, "research_qualification_must_remain_false")
    schema_path = repo / "schemas" / "native-tenki-placement-probe.schema.json"
    # Validate this report with the existing standard-library checks.
    require(safe_path(schema_path).is_file(), "report_schema_missing")


def run_stages(runner, output, manifest, stage1, expected_identity, unchanged, prepare_only=False):
    """Run or zero-call verify the six immutable stages in the fixed order."""
    from ygo_eval.tenki_placement_diagnostics import (
        DiagnosticPersistenceError,
        capture_process_diagnostic,
    )

    context = manifest["context"]
    ledger = output / "calls.jsonl"
    receipts = []
    stats = None
    diagnostic = None
    parent_index = {2: 1, 3: 2, 4: 3, 5: 2, 6: 5}

    def publish_summary(reason):
        summaries = []
        for receipt in receipts:
            receipt_path = output / f"stage-{receipt['stage']}.json"
            summaries.append({
                "stage": receipt["stage"],
                "successful": receipt["successful"],
                "receipt_sha256": sha(receipt_path),
                "independent_replay_matches": receipt.get("independent_replay_matches"),
            })
        report = summarize(context, summaries, stats, reason)
        immutable_write(output / "summary.json", report)
        return report

    deadline = manifest["started_at"] + WINDOW_SECONDS
    if prepare_only and deadline <= int(time.time()):
        raise ValueError("experiment_window_expired")
    last_input = None
    for stage in range(1, 7):
        try:
            unchanged()
        except (ValueError, OSError):
            diagnostic = "frozen_input_changed"
            break
        try:
            request = copy.deepcopy(stage1) if stage == 1 else derive_stage_request(stage, receipts[parent_index[stage] - 1])
        except (ValueError, OSError, KeyError, TypeError, IndexError):
            diagnostic = "stage_derivation_failed"
            break
        invocation = {
            "context": context,
            "ledger": str(ledger),
            "output": str(output / f"stage-{stage}.json"),
            "stage": stage,
            "request": request,
            "expected_identity": expected_identity,
            "started_at": manifest["started_at"],
        }
        request_path = output / f"stage-{stage}-request.json"
        input_path = output / f"stage-{stage}-input.json"
        input_seal_path = output / f"stage-{stage}-input-seal.json"
        last_input = input_path
        try:
            immutable_write(request_path, request)
            immutable_write(input_path, invocation)
            immutable_write(input_seal_path, {
                "schema_version": 1,
                "kind": "tenki_placement_stage_input_seal",
                "context": context,
                "stage": stage,
                "input_sha256": sha(input_path),
            })
        except (ValueError, OSError, TypeError):
            diagnostic = "stage_intent_persistence_failed"
            break
        if prepare_only:
            if stage == 1:
                report = {
                    "schema_version": 1,
                    "kind": "native_tenki_placement_prepared",
                    "scope": SCOPE,
                    "context": context,
                    "prepared": True,
                    "native_calls": 0,
                    "planned_calls": LIMIT,
                    "first_stage_request_sha256": digest(canonical(request)),
                    "old_receipts_verified_zero_call": True,
                    **FLAGS,
                }
                return report
            raise ValueError("prepare_only_must_stop_after_first_request")
        command = [str(runner), str(input_path), "--input-sha", sha(input_path)]
        receipt_path = output / f"stage-{stage}.json"
        has_receipt = receipt_path.exists()
        # Existing receipts are verified with a read-only runner mode even after expiry.
        # The 30-second reserve applies only before a fresh charge.
        if not has_receipt and int(time.time()) + 30 >= deadline:
            diagnostic = "window_exhausted_before_new_call"
            break
        try:
            process_diagnostic, completed = capture_process_diagnostic(
                command + (["--verify-recorded"] if has_receipt else []),
                Path.cwd(),
                output,
                mode="verify_recorded" if has_receipt else "normal",
                timeout=180,
                runner=subprocess.run,
            )
            if process_diagnostic["status"] != "completed" or completed is None:
                diagnostic = "runner_failed"
            elif completed.returncode in (0, 1):
                runner_output = strict_json(completed.stdout)
                require(isinstance(runner_output, dict), "runner_output_object_required")
                stats = runner_output.get("ledger")
            else:
                diagnostic = "runner_failed"
        except DiagnosticPersistenceError:
            diagnostic = "diagnostic_persistence_failed"
            break
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            diagnostic = "runner_failed"

        if receipt_path.exists():
            try:
                receipt = strict_json(safe_path(receipt_path).read_bytes())
                require(
                    receipt.get("schema_version") == 1
                    and receipt.get("kind") == "native_tenki_placement_stage"
                    and receipt.get("scope") == SCOPE
                    and receipt.get("context") == context
                    and type(receipt.get("stage")) is int
                    and receipt["stage"] == stage
                    and receipt.get("request") == request
                    and type(receipt.get("successful")) is bool
                    and receipt.get("proof_ready") is False
                    and receipt.get("complete_action_coverage") is False
                    and receipt.get("global_optimality") is False
                    and receipt.get("native_probability_verified") is False,
                    "stage_receipt_binding_mismatch",
                )
                ledger_prefix = receipt.get("ledger")
                require(isinstance(ledger_prefix, dict) and ledger_prefix == {"consumed": stage, "completed": stage, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": LIMIT}, "stage_receipt_ledger_prefix_mismatch")
                require(isinstance(receipt.get("charged_sequence_id"), str) and len(receipt["charged_sequence_id"]) == 64 and all(character in "0123456789abcdef" for character in receipt["charged_sequence_id"]), "stage_receipt_charge_identity_missing")
                require(receipt.get("window_valid_at_result") is (receipt["successful"] or receipt.get("diagnostic") != "window_exhausted"), "stage_receipt_window_flag_mismatch")
                if receipt["successful"]:
                    require(
                        isinstance(receipt.get("validation"), dict)
                        and isinstance(receipt["validation"].get("Ok"), dict)
                        and receipt.get("assets_before") == expected_identity
                        and receipt.get("assets_after") == expected_identity
                        and receipt.get("assets_unchanged") is True
                        and receipt.get("window_valid_at_result") is True
                        and receipt.get("diagnostic") is None
                        and isinstance(receipt.get("result"), dict)
                        and isinstance(receipt["result"].get("Ok"), dict)
                        and receipt["result"]["Ok"].get("status") == "decision_required"
                        and receipt["result"]["Ok"].get("error") is None
                        and not receipt["result"]["Ok"].get("coverage_gaps"),
                        "successful_stage_validation_missing",
                    )
                if stage in (4, 6):
                    require(receipt.get("independent_replay_matches") is True if receipt["successful"] else receipt.get("independent_replay_matches") in (False, None), "replay_receipt_mismatch")
                else:
                    require(receipt.get("independent_replay_matches") is None, "unexpected_replay_qualification")
                receipts.append(receipt)
            except (ValueError, OSError, KeyError, TypeError, AttributeError):
                diagnostic = "stage_receipt_binding_mismatch"
        else:
            diagnostic = diagnostic or "stage_receipt_unavailable"

        try:
            unchanged()
        except (ValueError, OSError):
            diagnostic = "frozen_input_changed"
        if diagnostic is None and (not receipts[-1].get("successful") or receipts[-1].get("diagnostic") is not None):
            diagnostic = receipts[-1].get("diagnostic") or "stage_validation_failed"
        if diagnostic is not None:
            break

    stats_input = last_input if last_input is not None and last_input.is_file() else None
    if stats_input is None:
        stats_input = next(
            (output / f"stage-{stage}-input.json" for stage in range(6, 0, -1)
             if (output / f"stage-{stage}-input.json").is_file()),
            None,
        )
    if diagnostic is not None:
        # Do not carry forward a prefix observed before a later uncertain call.
        # Only a fresh, authenticated stats read can settle total consumption.
        stats = None
    if diagnostic is not None and diagnostic != "diagnostic_persistence_failed" and ledger.exists() and stats_input is not None:
        try:
            # A frozen-input failure can mean the runner itself was replaced.
            # Never execute even its read-only mode until both runner and saved
            # input match the immutable identities captured before the charge.
            if sha(runner) == manifest.get("runner_sha256"):
                stage = int(stats_input.stem.split("-")[1])
                seal_path = output / f"stage-{stage}-input-seal.json"
                seal = strict_json(safe_path(seal_path).read_bytes())
                invocation = strict_json(safe_path(stats_input).read_bytes())
                request_path = output / f"stage-{stage}-request.json"
                request = strict_json(safe_path(request_path).read_bytes())
                require(
                    seal.get("schema_version") == 1
                    and seal.get("kind") == "tenki_placement_stage_input_seal"
                    and seal.get("context") == context
                    and seal.get("stage") == stage
                    and seal.get("input_sha256") == sha(stats_input)
                    and invocation.get("context") == context
                    and invocation.get("stage") == stage
                    and invocation.get("request") == request
                    and invocation.get("ledger") == str(ledger)
                    and invocation.get("output") == str(output / f"stage-{stage}.json")
                    and invocation.get("expected_identity") == expected_identity
                    and invocation.get("started_at") == manifest["started_at"],
                    "saved_stats_input_binding_mismatch",
                )
                stats_input_hash = sha(stats_input)
                stats_diagnostic, stats_run = capture_process_diagnostic(
                    [str(runner), str(stats_input), "--input-sha", stats_input_hash, "--stats"],
                    Path.cwd(),
                    output,
                    mode="stats",
                    timeout=60,
                    runner=subprocess.run,
                )
                stats_value = (
                    strict_json(stats_run.stdout)
                    if stats_diagnostic["status"] == "completed" and stats_run is not None and stats_run.returncode == 0
                    else None
                )
                stats = stats_value.get("ledger") if isinstance(stats_value, dict) else None
        except DiagnosticPersistenceError:
            stats = None
            diagnostic = "diagnostic_persistence_failed"
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            stats = None
    return publish_summary(diagnostic)


def native_tenki_placement(args, repo=None):
    """Validate sealed history, freeze a new window, then run only approved stages."""
    from ygo_eval.research import validate_sources

    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    baseline = Path(os.path.abspath(args.baseline_dir))
    root = repo / OUTPUT_ROOT_RELATIVE
    output = repo / OUTPUT_RELATIVE
    require(Path(os.path.abspath(args.output)) == output, "dedicated_placement_output_required")
    paths = {
        "runner": Path(os.path.abspath(args.runner)),
        "worker": Path(os.path.abspath(args.worker)),
        "build_record": Path(os.path.abspath(args.build_record)),
        "identity": Path(os.path.abspath(args.identity)),
        "window_start": Path(os.path.abspath(args.window_start)),
    }
    require(paths["build_record"] == root / "build-record.json", "fixed_build_record_path_required")
    require(paths["identity"] == root / "identity.json", "fixed_identity_path_required")
    require(paths["window_start"] == root / "window-start.json", "fixed_window_path_required")
    require(paths["runner"] == root / "native-artifacts" / "tenki-placement-probe.exe", "fixed_runner_artifact_required")
    require(paths["worker"] == root / "native-artifacts" / "ygo-engine-worker.exe", "fixed_worker_artifact_required")
    for path in (paths["runner"], paths["worker"], paths["build_record"], baseline):
        require(path != output and not path.is_relative_to(output) and not output.is_relative_to(path), "output_overlaps_input")
    require(not root.is_symlink() and not output.is_symlink(), "linked_experiment_directory_rejected")
    ignored = safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    require(any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime") for line in ignored) and not any(line.lstrip().startswith("!") for line in ignored), "ignored_output_contract_missing")

    # Re-read and verify all baseline sources before allocating the new window.
    transition_path = getattr(args, "baseline_transition", None)
    if transition_path is not None:
        transition_path = Path(os.path.abspath(transition_path))
        require(transition_path == repo / TRANSITION_FILE_PATH, "fixed_baseline_transition_path_required")
    baseline_audit, baseline_protected = audit_baseline(baseline, repo, transition_path=transition_path)
    source = stable_source(repo)
    build_raw, build_hash = _read(paths["build_record"])
    build = strict_json(build_raw)
    _validate_signed(build, "build_record")
    require(build.get("status") == "recorded" and build.get("source_before") == source and build.get("source_after") == source and build.get("reproducible_build_proven") is False, "build_source_identity_mismatch")
    artifacts = build.get("artifacts", {})
    artifact_hashes = {role: sha(paths[role]) for role in ("runner", "worker")}
    require(all(artifacts.get(role) == artifact_hashes[role] for role in artifact_hashes), "build_artifact_hash_mismatch")

    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
    for path in (root, root / "native-artifacts"):
        if path.exists():
            safe_path(path, False)
    configs = _candidate_configs(repo, root, paths["worker"], baseline)

    # This exclusive start is written before any fresh candidate asset scan.
    if not paths["window_start"].exists() and paths["identity"].exists():
        raise ValueError("identity_exists_without_original_window_start")
    window = _window(root, paths["window_start"])
    if args.prepare_only:
        require(window["started_at"] + WINDOW_SECONDS > int(time.time()), "experiment_window_expired")
    elif window["started_at"] + WINDOW_SECONDS <= int(time.time()):
        require(paths["identity"].is_file(), "experiment_window_expired")
    identity = _capture_identity(repo, paths["build_record"].parent / "native-artifacts" / "ygo-cli.exe", configs, paths["identity"])
    _validate_signed(identity, "workspace_identity")
    require(identity.get("source") == source and identity.get("consistent") is True and identity.get("build_provenance") == "unverified" and identity.get("reproducible_build_proven") is False and identity.get("cli_sha256") == artifacts.get("cli"), "candidate_workspace_identity_mismatch")

    old1 = strict_json((baseline / "research" / "stage-1.json").read_bytes())
    old2_request = strict_json((baseline / "research" / "stage-2-request.json").read_bytes())
    request = _activation_from_history(old1, old2_request)
    request["engine"]["worker_path"] = str(paths["worker"])
    require(request.get("protocol_version") == 2 and request.get("probe_only") is False and request.get("scenario") is None and request.get("interruption") is None and request.get("first_turn") is None, "frozen_protocol2_request_required")
    require(request.get("research_capture") is None, "terminal_capture_must_be_disabled")
    ordinary, tournament = _assert_runtime_identity(identity, paths["worker"], request)
    banlist_path = repo / "data/runtime/banlist.json"
    require(banlist_path.exists(), "ordinary_banlist_missing")
    banlist = strict_json(safe_path(banlist_path).read_bytes())
    prepared = strict_json(safe_path(repo / PREPARATION_RELATIVE).read_bytes())
    tenki_candidates = [item for item in prepared["candidates"] if item.get("case", {}).get("case_id") == "prompt-13-tenki-v1"]
    require(len(tenki_candidates) == 1, "frozen_tenki_case_missing")
    case = tenki_candidates[0]["case"]
    # Validate the frozen source/deck contract using the same source checker used by earlier scopes.
    validate_sources(case, request, banlist_path)
    hashes = {
        "runner": sha(paths["runner"]),
        "worker": sha(paths["worker"]),
        "build_record": build_hash,
        "identity": sha(paths["identity"]),
        "window_start": sha(paths["window_start"]),
        "baseline_audit": digest(canonical(baseline_audit)),
    }
    if transition_path is not None:
        hashes["baseline_transition"] = sha(transition_path)
    archive = _archive_current_source(repo, root, source)
    static_hashes = {
        "worker_source": sha(repo / "crates/ygo-engine-adapter/src/worker.rs"),
        "codec_source": sha(repo / "crates/ygo-engine-adapter/src/codec.rs"),
        "placement_oracle_source": sha(repo / "crates/ygo-engine-adapter/src/tenki_placement_probe.rs"),
        "research_cli_source": sha(repo / "python/ygo_eval/research.py"),
    }
    manifest = {
        "schema_version": 1,
        "kind": "native_tenki_placement_manifest",
        "scope": SCOPE,
        "limit": LIMIT,
        "planned_calls": LIMIT,
        "wall_seconds": WINDOW_SECONDS,
        "started_at": window["started_at"],
        "old_consumed": OLD_CONSUMED,
        "baseline_acceptance_sha256": RECOVERY_ACCEPTANCE_SHA256,
        "source_identity": source["identity"],
        "build_identity": build["identity"],
        "identity_sha256": identity["identity"],
        "runner_sha256": hashes["runner"],
        "worker_sha256": hashes["worker"],
        "old_stage1_sha256": OLD_STAGE1_SHA256,
        "old_stage2_request_sha256": OLD_STAGE2_REQUEST_SHA256,
        "old_stage2_sha256": OLD_STAGE2_SHA256,
        "old_runner_sha256": OLD_RUNNER_SHA256,
        "historical_ledgers": baseline_audit["historical_ledgers"],
        "baseline_audit_sha256": digest(canonical(baseline_audit)),
        "preparation_sha256": baseline_audit["preparation_sha256"],
        "frozen_cases_sha256": baseline_audit["frozen_cases_sha256"],
        "input_sha256": hashes,
        "static_source_sha256": static_hashes,
        "source_archive": archive,
        "stage1_request_sha256": digest(canonical(request)),
        "assets": {
            "ordinary": ordinary["identity"],
            "tournament": tournament["identity"],
            "execution_role": "ordinary",
        },
        "request_derivation": {
            "1": "verified-old-stage1-activation-request-only-worker-path-replaced",
            "2": "stage1-coordinate-player0-location8-sequence0",
            "3": "stage2-opcode13-false",
            "4": "exact-stage3-request-replay",
            "5": "stage2-opcode13-true-stop-at-opcode15",
            "6": "exact-stage5-request-replay",
        },
        **FLAGS,
    }
    unsigned_manifest = dict(manifest)
    manifest["context"] = digest(canonical(unsigned_manifest))
    require(manifest["context"] == digest(canonical({key: value for key, value in manifest.items() if key != "context"})), "manifest_context_calculation_failed")
    immutable_write(output / "baseline-audit.json", baseline_audit)
    immutable_write(output / "manifest.json", manifest)

    # audit_baseline returns the effective map, including the scoped migrated worker
    # hash and all historical ledgers. Do not merge the old protected map back in.
    protected = _runtime_protected_map(baseline_protected, baseline_audit["historical_ledgers"])
    input_hashes = {path: sha(path) for path in (paths["runner"], paths["worker"], paths["build_record"], paths["identity"], paths["window_start"], *configs.values(), banlist_path)}

    def unchanged():
        require(stable_source(repo) == source, "workspace_source_changed")
        for path, expected in input_hashes.items():
            require(sha(path) == expected, "frozen_build_or_identity_input_changed")
        for path, expected in protected.items():
            require(sha(path) == expected, "historical_protected_input_changed")

    prepared = run_stages(paths["runner"], output, manifest, request, ordinary, unchanged, args.prepare_only)
    if args.prepare_only and prepared.get("prepared") is True:
        validate_schema(prepared, "native_tenki_placement_prepared", repo)
        immutable_write(output / "prepared.json", prepared)
        return prepared
    if args.prepare_only:
        validate_schema(prepared, "native_tenki_placement_summary", repo)
        return prepared
    validate_schema(prepared, "native_tenki_placement_summary", repo)
    return prepared
