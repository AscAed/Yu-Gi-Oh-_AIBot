"""Independent confirmation budget for the frozen Tenki placement prefix."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from typing import Any

from ygo_data.identity import canonical, digest, regular_file, stable_source
from ygo_eval.prompt_probe_prepare import require, safe_path, strict_json
from ygo_eval.terminal_regression import immutable_write
from ygo_eval.native_tenki_workflow import (
    WorkflowSpec,
    capture_runner_process,
    normal_runner_timeout,
    process_diagnostic_sha256,
    run_six_stage_workflow,
)

SCOPE = "tenki-placement-confirmation-v1"
LIMIT = 6
WINDOW_SECONDS = 7200
WORKER_TIMEOUT_MS = 30_000
OLD_CONSUMED = 26
OUTPUT_RELATIVE = Path("data/runtime/p1-tenki-placement-confirmation-native-2026-10-22")
DIAGNOSTICS_RELATIVE = Path("data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22")
OLD_PLACEMENT_RELATIVE = Path("data/runtime/p1-tenki-placement-native-2026-10-22")
PROMPT_BASELINE_RELATIVE = Path("data/runtime/p1-tenki-probe-native-2026-10-21")
ACCEPTANCE_SHA256 = "a134e4229b30b7eda699e5ab394ff3fc03722f17919033b0415521e910a773c0"
DELIVERY_SHA256 = "3c35f9a532d38335fbb1327ff640b077d9d6347d73664bd8299750cd34362df9"
PREFLIGHT_REPORT_SHA256 = "76830d7e34605ecb3bed7d4f3a725b6a18bb4ab2cca95c3314d87592d274e288"
PRECHECK_SOURCE = "7e3471035380cf1043a84b43a5b94f08d3f322c53919cb48814209bb6dac81e6"
FINAL_SOURCE = "2bd1b2c7b130dd25167e2bc28ab5ffa007cc7d9abe6ae4e547f20f10f6092364"
PRECHECK_ARCHIVE_SHA256 = "a4449992b46a9ec2167527c5f59cf988b61c9fdad46466d5721fa88d32a2b59e"
PRECHECK_LIST_SHA256 = "e15709b8bc07d85a2c139f5b13f9e01aa6f7c9d67ca4a70867b6a9d3c3a4bc38"
FINAL_ARCHIVE_SHA256 = "db9f22e75c06b183578c710b4d9ee0a9c97e0c2032bf240197a1795ea9211595"
FINAL_LIST_SHA256 = "93277504373eb87a2b4bdb33ee3b76c418a75ef9d98e1888144ab65b798ee755"
DOC_ONLY_CHANGES = {
    "TASKS.md",
    "docs/INDEX.md",
    "docs/TESTING.md",
    "docs/superpowers/plans/2026-10-22-tenki-placement-diagnostics-handoff.md",
}
FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
WORKFLOW_SPEC = WorkflowSpec(
    scope=SCOPE,
    limit=LIMIT,
    wall_seconds=WINDOW_SECONDS,
    worker_timeout_seconds=WORKER_TIMEOUT_MS // 1000,
    runner_role="tenki_placement_confirmation_runner",
    stage_kind="native_tenki_placement_confirmation_stage",
    stage_report_kind="native_tenki_placement_confirmation_stage",
    input_seal_kind="tenki_placement_confirmation_stage_input_seal",
    timeout_error_prefix="confirmation",
)

# (role, relative ledger path, immutable hash, calls, scope, context, limit)
OLD_LEDGER_CONTRACTS = (
    ("baseline", "data/runtime/baseline-2026-10-19/research/calls.jsonl",
     "b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a", 9,
     "research-first-batch-v1", "4ea4d6cb6aa9b1eac4d9ca724ebe451be620ea7fa4d42473fa0f86b9511f17db", 4096),
    ("state", "data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl",
     "0e50a03837676b8b19a1409b9ffa06bc7798ff61254109c10025c7733a3c410b", 8,
     "native-regression-v1", '["76a86c0ba6a5d4495709d724c5bf1946bbb9c1c887af89430c3e65bfd52cf292",["rabbit-full","tournament-full","rabbit-empty","rabbit-shuffle","rabbit-end"]]', 16),
    ("terminal", "data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl",
     "3fd2aa6d1ff18f5eb1fe7100fe8fb4c36e9b73795e0749aa362b0bea9ea93ef2", 1,
     "terminal-regression-v1", '["db775b4b5ae565de7dcf463e3bcc502ccf72c10397c6266c908090080c750a73",["terminal-rabbit","terminal-tournament","terminal-shuffle-end"]]', 6),
    ("terminal-followup", "data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl",
     "68b134725597f62a888dd182b25bb0fb16cb2dbfcaf5154009b2242dc4bcc473", 4,
     "terminal-followup-v1", '["a9be1d93c90556207c60b9ab17840c512008f971c9c044c49b9930f37bde69e9",["terminal-tournament","terminal-shuffle-end"]]', 4),
    ("terminal-smoke", "data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl",
     "624b4843dc9cd09e07588074b2b4ecbd91737316c70e922a183f0dd9a5f137b0", 2,
     "terminal-smoke-v1", '["2214263e4122b1ba68871c84b77f880caaf66b0e5bdd7319741b0d9a82dd81d7",["terminal-rabbit"]]', 2),
    ("tenki-probe", "data/runtime/p1-tenki-probe-native-2026-10-21/research/calls.jsonl",
     "5337352e249a13eb51a5a6dd124bc2397c4402a68e99cd77c2bffc7da22392b6", 2,
     "tenki-prompt-probe-v1", "7a7258ddacc5b42fe51908a771cff8ed85b58a020c1f0c0e6cd9df5ec01269a1", 6),
    ("tenki-placement", "data/runtime/p1-tenki-placement-native-2026-10-22/research/calls.jsonl",
     "0c274d01a40bb1f225409346b8d2f377fe84246f5bb367672ebcf25d74760767", 0,
     "tenki-placement-probe-v1", "773bafe50501dd0e093b7396d24bb2198a94503212a31d6407bdcfad8f7b1d37", 6),
)


def _old_ledger_expected_hashes(_sources=None) -> tuple[str, ...]:
    """Resolve hashes for this fixed ledger set from its source leaf when supplied."""
    if _sources is None:
        return tuple(contract[2] for contract in OLD_LEDGER_CONTRACTS)
    return tuple(_sources.file_sha256(contract[1]) for contract in OLD_LEDGER_CONTRACTS)


def _old_ledger_hashes_match(ledgers: list[dict], _sources=None) -> bool:
    return [item.get("sha256") for item in ledgers] == list(_old_ledger_expected_hashes(_sources))


def add_arguments(parser: argparse.ArgumentParser) -> None:
    for name in ("baseline-dir", "runner", "worker", "build-record", "identity", "window-start", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--verify-only", action="store_true")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value: Any, *, sort_keys: bool = False) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=sort_keys, allow_nan=False
    ).encode("utf-8")


def _require_sha(value: Any, label: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None, label)
    return value


def summarize_confirmation(context: str, stages: list[dict], stats: dict | None, diagnostic: str | None = None) -> dict:
    """Create a summary whose success follows all six frozen receipts and settled debits."""
    stats_valid = (
        isinstance(stats, dict)
        and all(type(stats.get(key)) is int for key in ("consumed", "completed", "unknown", "reserved", "abandoned", "limit"))
        and stats["consumed"] == LIMIT
        and stats["completed"] == LIMIT
        and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0
        and stats["limit"] == LIMIT
    )
    stage_valid = isinstance(stages, list) and len(stages) == LIMIT
    if stage_valid:
        for number, item in enumerate(stages, 1):
            if (
                not isinstance(item, dict)
                or item.get("stage") != number
                or item.get("successful") is not True
                or not re.fullmatch(r"[a-f0-9]{64}", str(item.get("receipt_sha256", "")))
                or not re.fullmatch(r"[a-f0-9]{64}", str(item.get("diagnostic_sha256", "")))
                or item.get("independent_replay_matches") is not (True if number in (4, 6) else None)
            ):
                stage_valid = False
                break
    known_consumed = stats.get("consumed") if isinstance(stats, dict) and type(stats.get("consumed")) is int else None
    successful = stage_valid and stats_valid and diagnostic is None
    return {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_summary",
        "scope": SCOPE,
        "context": context,
        "old_consumed": OLD_CONSUMED,
        "new_consumed": known_consumed,
        "cumulative_consumed": OLD_CONSUMED + known_consumed if known_consumed is not None else None,
        "unknown": stats.get("unknown") if isinstance(stats, dict) else None,
        "ledger": copy.deepcopy(stats),
        "stages": copy.deepcopy(stages),
        "diagnostic": diagnostic,
        "successful": successful,
        **FLAGS,
    }


def validate_report(value: dict, repo: Path) -> bool:
    """Validate the local v1 contract without requiring jsonschema at runtime."""
    require(isinstance(value, dict) and value.get("schema_version") == 1, "report_schema_version_invalid")
    kind = value.get("kind")
    allowed = {
        "native_tenki_placement_confirmation_manifest",
        "native_tenki_placement_confirmation_prepared",
        "native_tenki_placement_confirmation_stage",
        "native_tenki_placement_confirmation_summary",
        "native_tenki_placement_confirmation_verification",
    }
    require(kind in allowed and value.get("scope") == SCOPE, "report_contract_kind_or_scope_invalid")
    for flag in FLAGS:
        require(value.get(flag) is False, "research_qualification_must_remain_false")
    context = value.get("context")
    require(isinstance(context, str) and re.fullmatch(r"[a-f0-9]{64}", context), "report_context_invalid")
    if kind.endswith("_prepared"):
        require(
            value.get("prepared") is True
            and value.get("native_calls") == 0
            and value.get("planned_calls") == LIMIT
            and re.fullmatch(r"[a-f0-9]{64}", str(value.get("first_stage_request_sha256", "")))
            and re.fullmatch(r"[a-f0-9]{64}", str(value.get("preflight_diagnostic_sha256", ""))),
            "prepared_report_binding_invalid",
        )
    if kind.endswith("_stage"):
        require(
            type(value.get("stage")) is int and 1 <= value["stage"] <= LIMIT
            and type(value.get("successful")) is bool
            and (value.get("native_calls") is None or (type(value.get("native_calls")) is int and 0 <= value["native_calls"] <= 1))
            and (value.get("diagnostic") is None or isinstance(value.get("diagnostic"), str)),
            "stage_report_fields_invalid",
        )
        receipt_hash = value.get("receipt_sha256")
        if receipt_hash is None:
            require(value.get("successful") is False, "successful_stage_receipt_hash_missing")
        else:
            _require_sha(receipt_hash, "stage_receipt_hash_invalid")
        _require_sha(value.get("diagnostic_sha256"), "stage_diagnostic_hash_invalid")
        replay = value.get("independent_replay_matches")
        require(replay is None or type(replay) is bool, "stage_replay_field_invalid")
        if value["stage"] in (4, 6) and value["successful"]:
            require(replay is True, "successful_replay_not_verified")
        elif value["stage"] not in (4, 6):
            require(replay is None, "unexpected_replay_qualification")
        ledger = value.get("ledger")
        require(ledger is None or _valid_stats(ledger), "stage_report_ledger_invalid")
        if value["successful"]:
            require(receipt_hash is not None and _valid_stats(ledger), "successful_stage_evidence_incomplete")
    if kind.endswith("_manifest"):
        _validate_manifest(value)
    if kind.endswith("_summary"):
        require(type(value.get("successful")) is bool, "summary_successful_invalid")
        require(value.get("old_consumed") == OLD_CONSUMED, "summary_old_consumed_invalid")
        require(isinstance(value.get("stages"), list) and len(value["stages"]) <= LIMIT, "summary_stages_invalid")
        for number, stage in enumerate(value["stages"], 1):
            require(
                isinstance(stage, dict)
                and stage.get("stage") == number
                and type(stage.get("successful")) is bool
                and (
                    stage.get("independent_replay_matches") is True
                    if number in (4, 6) and stage.get("successful")
                    else stage.get("independent_replay_matches") in (None, False)
                    if number in (4, 6)
                    else stage.get("independent_replay_matches") is None
                ),
                "summary_stage_order_or_replay_invalid",
            )
            if stage.get("receipt_sha256") is not None:
                _require_sha(stage.get("receipt_sha256"), "summary_stage_receipt_hash_invalid")
            else:
                require(stage.get("successful") is False, "summary_successful_stage_receipt_hash_missing")
            _require_sha(stage.get("diagnostic_sha256"), "summary_stage_diagnostic_hash_invalid")
        ledger = value.get("ledger")
        new_consumed = value.get("new_consumed")
        cumulative = value.get("cumulative_consumed")
        unknown = value.get("unknown")
        if ledger is not None:
            require(
                isinstance(ledger, dict)
                and all(type(ledger.get(name)) is int and ledger[name] >= 0 for name in ("consumed", "completed", "unknown", "reserved", "abandoned", "limit"))
                and ledger.get("limit") == LIMIT
                and new_consumed == ledger.get("consumed")
                and unknown == ledger.get("unknown")
                and cumulative == OLD_CONSUMED + new_consumed,
                "summary_ledger_totals_invalid",
            )
        else:
            require(new_consumed is None and cumulative is None and unknown is None, "summary_unknown_totals_invalid")
        if value["successful"]:
            require(
                ledger is not None
                and ledger.get("consumed") == ledger.get("completed") == LIMIT
                and ledger.get("unknown") == ledger.get("reserved") == ledger.get("abandoned") == 0
                and len(value["stages"]) == LIMIT
                and all(stage.get("successful") is True for stage in value["stages"])
                and value.get("diagnostic") is None,
                "summary_success_claim_invalid",
            )
    if kind.endswith("_verification"):
        require(
            type(value.get("valid")) is bool
            and value.get("native_calls") == 0
            and value.get("old_consumed") == OLD_CONSUMED
            and isinstance(value.get("stages"), list)
            and len(value["stages"]) <= LIMIT,
            "verification_report_fields_invalid",
        )
        for key in ("new_consumed", "cumulative_consumed", "unknown"):
            require(value.get(key) is None or (type(value.get(key)) is int and value[key] >= 0), "verification_stats_invalid")
        if value.get("new_consumed") is not None:
            require(value.get("cumulative_consumed") == OLD_CONSUMED + value["new_consumed"], "verification_total_mismatch")
        for number, stage in enumerate(value["stages"], 1):
            require(isinstance(stage, dict) and stage.get("stage") == number, "verification_stage_order_invalid")
            if stage.get("kind") == "native_tenki_placement_confirmation_stage":
                validate_report(stage, repo)
        if value["valid"]:
            require(
                value.get("new_consumed") == LIMIT
                and value.get("cumulative_consumed") == OLD_CONSUMED + LIMIT
                and value.get("unknown") == 0
                and len(value["stages"]) == LIMIT
                and all(item.get("successful") is True for item in value["stages"]),
                "verification_success_claim_invalid",
            )
    repo_path = Path(repo).resolve()
    schema_path = repo_path / "schemas/native-tenki-placement-confirmation.schema.json"
    if not schema_path.is_file() and repo_path.name == "data":
        schema_path = repo_path.parent / "schemas/native-tenki-placement-confirmation.schema.json"
    require(schema_path.is_file(), "report_schema_missing")
    return True


def _ordered_entry(entry: dict) -> dict:
    """Rebuild the frozen Rust enum/struct field order before hashing a ledger row."""
    kind = entry.get("kind")
    fields = {
        "header": ("kind", "version", "scope", "context", "limit"),
        "checkpoint": ("kind", "name", "blob", "consumed", "charged_sequence"),
        "begin": ("kind", "call_id", "request", "purpose", "reservation"),
        "complete": ("kind", "call_id", "result", "raw_hash", "normalized_hash"),
        "recovery": ("kind", "evidence"),
        "reserve": ("kind", "token", "amount"),
        "release": ("kind", "token"),
        "abandon": ("kind", "call_id", "reason"),
    }
    require(kind in fields and set(entry) == set(fields[kind]), "historical_ledger_entry_unsupported")
    return {key: entry[key] for key in fields[kind]}


def _safe_file(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    safe_path(path)
    return path


def _safe_dir(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    safe_path(path, file=False)
    require(path.is_dir(), "input_directory_required")
    return path


def _walk_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _request_hashes_from_reports(research_dir: Path) -> set[str]:
    found = set()
    for path in sorted(research_dir.rglob("*.json")):
        if any(part.endswith(".blobs") for part in path.parts):
            continue
        raw = _safe_file(path).read_bytes()
        try:
            value = strict_json(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        for item in _walk_values(value):
            required = {"protocol_version", "engine", "deck", "opening_hand", "seed", "decisions", "versions", "probe_only"}
            if required <= set(item):
                request = copy.deepcopy(item)
                request.pop("engine", None)
                found.add(_sha(_encode(request, sort_keys=True)))
    return found


def _folder_blob_reader(blob_root: Path, folder: str, expected: str) -> bytes:
    require(folder in {"results", "events", "checkpoints", "recoveries"}, "historical_blob_folder_invalid")
    _require_sha(expected, "historical_blob_address_invalid")
    path = _safe_file(blob_root / folder / f"{expected}.json")
    raw = path.read_bytes()
    require(_sha(raw) == expected, "historical_blob_hash_mismatch")
    return raw


def _ledger_stats(calls: dict[int, dict], limit: int) -> dict:
    completed = sum(call["normalized_hash"] is not None for call in calls.values())
    abandoned = sum(call["abandoned"] for call in calls.values())
    return {
        "consumed": len(calls),
        "reserved": 0,
        "completed": completed,
        "unknown": len(calls) - completed,
        "abandoned": abandoned,
        "limit": limit,
    }


def _charged_sequence(calls: dict[int, dict], count: int) -> str:
    sequence = [
        [call_id, calls[call_id]["request"], calls[call_id]["purpose"], calls[call_id]["normalized_hash"]]
        for call_id in sorted(calls)[:count]
    ]
    return _sha(_encode(sequence))


def _audit_one_ledger(repo: Path, contract: tuple, *, _sources=None) -> dict:
    role, relative, expected_hash, expected_consumed, expected_scope, expected_context, expected_limit = contract
    if _sources is not None:
        expected_hash = _sources.file_sha256(Path(relative).as_posix())
    path = _safe_file(repo / relative)
    raw = path.read_bytes()
    require(_sha(raw) == expected_hash, "historical_ledger_sha256_mismatch")
    require(raw.endswith(b"\n") and raw and not raw.endswith(b"\n\n"), "historical_ledger_torn_or_blank")
    lines = raw[:-1].split(b"\n")
    require(lines and all(lines), "historical_ledger_blank_record")
    rows = [strict_json(line) for line in lines]
    previous = ""
    calls: dict[int, dict] = {}
    checkpoints = []
    pending: int | None = None
    referenced = {name: set() for name in ("results", "events", "checkpoints", "recoveries")}
    blob_root = path.with_name(path.name + ".blobs")
    research_dir = path.parent
    request_hashes = _request_hashes_from_reports(research_dir)
    for sequence, row in enumerate(rows):
        require(isinstance(row, dict) and set(row) == {"sequence", "previous", "entry", "hash"}, "historical_ledger_record_shape")
        require(type(row["sequence"]) is int and row["sequence"] == sequence and row["previous"] == previous, "historical_ledger_chain_sequence")
        entry = _ordered_entry(row["entry"])
        record_hash = _sha(_encode([sequence, previous, entry]))
        require(row["hash"] == record_hash, "historical_ledger_chain_hash")
        previous = row["hash"]
        kind = entry["kind"]
        if sequence == 0:
            require(kind == "header" and entry == {
                "kind": "header", "version": 1, "scope": expected_scope,
                "context": expected_context, "limit": expected_limit,
            }, "historical_ledger_header_mismatch")
            continue
        require(kind != "header", "historical_ledger_duplicate_header")
        if kind == "begin":
            call_id = entry["call_id"]
            require(type(call_id) is int and call_id == len(calls) + 1 and call_id <= expected_limit, "historical_ledger_call_id")
            require(pending is None and entry["reservation"] is None, "historical_ledger_begin_order")
            require(entry["purpose"] in {"execution", "replay", "probe", "rule_verification", "witness", "audit"}, "historical_ledger_purpose")
            request_hash = _require_sha(entry["request"], "historical_request_identity_invalid")
            require(request_hash in request_hashes, "historical_request_not_bound_to_saved_input")
            require(_ledger_stats(calls, expected_limit)["unknown"] == 0, "historical_ledger_unresolved_before_next_call")
            calls[call_id] = {
                "request": request_hash,
                "purpose": entry["purpose"],
                "normalized_hash": None,
                "abandoned": False,
            }
            pending = call_id
        elif kind == "complete":
            call_id = entry["call_id"]
            require(pending == call_id and calls[call_id]["normalized_hash"] is None, "historical_ledger_completion_order")
            stored_raw = _folder_blob_reader(blob_root, "results", entry["result"])
            referenced["results"].add(entry["result"])
            stored = strict_json(stored_raw)
            require(isinstance(stored, dict) and stored.get("kind") == "duel" and set(stored) == {"kind", "result", "event_chunks"}, "historical_stored_result_kind")
            result = stored["result"]
            chunks = stored["event_chunks"]
            require(isinstance(result, dict) and result.get("events") == [] and isinstance(chunks, list), "historical_stored_result_shape")
            events = []
            for chunk in chunks:
                event_raw = _folder_blob_reader(blob_root, "events", chunk)
                referenced["events"].add(chunk)
                chunk_value = strict_json(event_raw)
                require(isinstance(chunk_value, list) and 0 < len(chunk_value) <= 64, "historical_event_chunk_shape")
                events.extend(chunk_value)
            result["events"] = events
            require(_sha(_encode(result)) == entry["raw_hash"], "historical_raw_result_hash")
            normalized = copy.deepcopy(result)
            require("peak_working_set_bytes" in normalized, "historical_memory_stat_missing")
            normalized["peak_working_set_bytes"] = None
            require(_sha(_encode(normalized)) == entry["normalized_hash"], "historical_normalized_result_hash")
            calls[call_id]["normalized_hash"] = entry["normalized_hash"]
            pending = None
        elif kind == "checkpoint":
            require(pending is None and _ledger_stats(calls, expected_limit)["unknown"] == 0, "historical_checkpoint_unsettled")
            checkpoint_blob = entry["blob"]
            payload = strict_json(_folder_blob_reader(blob_root, "checkpoints", checkpoint_blob))
            referenced["checkpoints"].add(checkpoint_blob)
            require(isinstance(payload, dict) and set(payload) == {"budget", "charged_sequence", "reservations", "search"}, "historical_checkpoint_payload_shape")
            current = _ledger_stats(calls, expected_limit)
            charged = _charged_sequence(calls, len(calls))
            require(type(entry["consumed"]) is int and entry["consumed"] == len(calls), "historical_checkpoint_consumption")
            require(entry["charged_sequence"] == charged and payload["charged_sequence"] == charged, "historical_checkpoint_sequence")
            require(payload["budget"] == current and payload["reservations"] == {}, "historical_checkpoint_budget")
            checkpoints.append({"name": entry["name"], "consumed": len(calls), "charged_sequence": charged})
        else:
            # This fixed historical set contains no reserve/release/recovery/abandon entries.
            raise ValueError("historical_ledger_transition_unsupported")
    require(pending is None, "historical_ledger_unresolved_final_call")
    stats = _ledger_stats(calls, expected_limit)
    require(stats["consumed"] == expected_consumed and stats["completed"] == expected_consumed and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0, "historical_ledger_statistics_mismatch")
    actual_dirs = {child.name for child in safe_path(blob_root, file=False).iterdir() if child.is_dir()}
    require(actual_dirs == {"results", "events", "checkpoints", "recoveries"}, "historical_blob_directory_set")
    for folder, references in referenced.items():
        directory = blob_root / folder
        files = set()
        for child in directory.iterdir():
            safe_path(child)
            require(child.is_file() and child.name.endswith(".json"), "historical_blob_tree_entry")
            files.add(child.name[:-5])
        require(files == references, "historical_blob_inventory_mismatch")
    return {
        "role": role,
        "path": relative,
        "sha256": expected_hash,
        "record_count": len(rows),
        "stats": stats,
        "checkpoints": checkpoints,
    }


def _audit_old_ledgers(repo: Path, *, _sources=None) -> list[dict]:
    contracts = OLD_LEDGER_CONTRACTS
    expected_consumed = OLD_CONSUMED
    expected_count = len(contracts)
    if _sources is not None:
        expected_count = _sources.dataset_count("ledger_count")
        expected_consumed = _sources.dataset_count("consumed")
        require(expected_count == len(contracts), "historical_ledger_count_mismatch")
        contracts = tuple(
            (*contract[:3], _sources.dataset_count(f"ledger_{contract[0]}_consumed"), *contract[4:])
            for contract in contracts
        )
    contracts = tuple(
        (*contract[:2], expected_hash, *contract[3:])
        for contract, expected_hash in zip(contracts, _old_ledger_expected_hashes(_sources))
    )
    results = [
        _audit_one_ledger(repo, contract, _sources=_sources) if _sources is not None
        else _audit_one_ledger(repo, contract)
        for contract in contracts
    ]
    require(len(results) == expected_count, "historical_ledger_count_mismatch")
    require(sum(item["stats"]["consumed"] for item in results) == expected_consumed, "historical_cumulative_consumption_mismatch")
    require(sum(item["stats"]["unknown"] for item in results) == 0, "historical_cumulative_unknown_mismatch")
    return results


def _verify_archives_and_acceptance(
    repo: Path, diagnostics: Path, experiment: Path, *, _sources=None,
) -> tuple[dict, list[dict], dict]:
    from ygo_eval.tenki_placement_diagnostics import _validate_placement_inputs, _verify_experiment_delivery, _verify_archive

    def pinned(path: Path, default: str) -> str:
        return default if _sources is None else _sources.file_sha256(path.relative_to(repo).as_posix())

    def archive_pin(role: str):
        return None if _sources is None else _sources.archive(role)

    acceptance_path = diagnostics / "final-build/acceptance.json"
    acceptance_expected = pinned(acceptance_path, ACCEPTANCE_SHA256)
    acceptance_raw = _safe_file(acceptance_path).read_bytes()
    require(_sha(acceptance_raw) == acceptance_expected, "diagnostics_acceptance_anchor_mismatch")
    acceptance = strict_json(acceptance_raw)
    unsigned = {key: value for key, value in acceptance.items() if key != "identity"}
    require(acceptance.get("identity") == digest(canonical(unsigned)), "diagnostics_acceptance_identity_mismatch")
    # The acceptance is pinned to the diagnostics delivery.  The old placement
    # delivery is a separate, provenance-only input and deliberately has no
    # diagnostics delivery identity.
    diagnostics_delivery_path = diagnostics / "final-build/delivery.json"
    diagnostics_delivery_expected = pinned(diagnostics_delivery_path, DELIVERY_SHA256)
    diagnostics_delivery_raw = _safe_file(diagnostics_delivery_path).read_bytes()
    require(_sha(diagnostics_delivery_raw) == diagnostics_delivery_expected, "diagnostics_delivery_anchor_mismatch")
    diagnostics_delivery = strict_json(diagnostics_delivery_raw)
    from ygo_eval.native_tenki_placement import _validate_signed
    _validate_signed(diagnostics_delivery, "tenki_placement_diagnostics_delivery")
    build_record_path = diagnostics / "final-build/build-record.json"
    build_record_raw = _safe_file(build_record_path).read_bytes()
    require(_sha(build_record_raw) == diagnostics_delivery.get("build_record_sha256"), "diagnostics_build_record_hash_mismatch")
    diagnostics_build = strict_json(build_record_raw)
    _validate_signed(diagnostics_build, "build_record")
    final_archive_path = diagnostics / "final-build/source-native.zip"
    final_list_path = diagnostics / "final-build/source-native-file-list.json"
    final_archive = archive_pin("placement_final_archive")
    if final_archive is None:
        final_archive_values = (FINAL_ARCHIVE_SHA256, FINAL_LIST_SHA256, FINAL_SOURCE, 459)
    else:
        require(
            final_archive.archive_path == final_archive_path.relative_to(repo).as_posix()
            and final_archive.file_list_path == final_list_path.relative_to(repo).as_posix(),
            "source_description_archive_path_mismatch",
        )
        final_archive_values = (
            final_archive.archive_sha256, final_archive.file_list_sha256,
            final_archive.source_identity, final_archive.file_count,
        )
    precheck_archive_path = diagnostics / "verification/source-audit-strict-dedupe/source-native.zip"
    precheck_list_path = diagnostics / "verification/source-audit-strict-dedupe/source-native-file-list.json"
    precheck_archive_pin = archive_pin("placement_native_archive")
    if precheck_archive_pin is None:
        precheck_archive_values = (PRECHECK_ARCHIVE_SHA256, PRECHECK_LIST_SHA256, PRECHECK_SOURCE, 458)
    else:
        require(
            precheck_archive_pin.archive_path == precheck_archive_path.relative_to(repo).as_posix()
            and precheck_archive_pin.file_list_path == precheck_list_path.relative_to(repo).as_posix(),
            "source_description_archive_path_mismatch",
        )
        precheck_archive_values = (
            precheck_archive_pin.archive_sha256, precheck_archive_pin.file_list_sha256,
            precheck_archive_pin.source_identity, precheck_archive_pin.file_count,
        )
    require(
        diagnostics_delivery.get("source_identity") == final_archive_values[2]
        and diagnostics_delivery.get("source_file_count") == final_archive_values[3]
        and diagnostics_delivery.get("source_archive_sha256") == final_archive_values[0]
        and diagnostics_delivery.get("source_file_list_sha256") == final_archive_values[1]
        and diagnostics_delivery.get("build_record_identity") == diagnostics_build.get("identity")
        and diagnostics_build.get("source_before", {}).get("identity") == final_archive_values[2]
        and diagnostics_build.get("source_after") == diagnostics_build.get("source_before")
        and diagnostics_build.get("artifacts", {}).get("runner") == diagnostics_delivery.get("runner_sha256")
        and diagnostics_delivery.get("status") == "offline_preflight_passed_native_target_still_failed"
        and diagnostics_delivery.get("preflight_status") == "passed"
        and diagnostics_delivery.get("native_calls_this_batch") == 0
        and diagnostics_delivery.get("historical_consumed") == (
            OLD_CONSUMED if _sources is None else _sources.dataset_count("historical_consumed")
        )
        and diagnostics_delivery.get("historical_unknown") == 0
        and diagnostics_delivery.get("placement_consumed") == 0
        and diagnostics_delivery.get("placement_unknown") == 0
        and diagnostics_delivery.get("window_reset") is False,
        "diagnostics_delivery_content_mismatch",
    )
    _validate_signed(acceptance, "tenki_placement_diagnostics_acceptance")
    if _sources is None:
        delivery, _addendum, delivery_records = _verify_experiment_delivery(repo, experiment)
    else:
        delivery, _addendum, delivery_records = _verify_experiment_delivery(
            repo, experiment, _sources=_sources,
        )
    preflight = _safe_file(diagnostics / "preflight-report.json").read_bytes()
    require(_sha(preflight) == pinned(diagnostics / "preflight-report.json", PREFLIGHT_REPORT_SHA256), "diagnostics_preflight_anchor_mismatch")
    require(
        acceptance.get("status") == "offline_preflight_accepted_native_trial_not_accepted"
        and acceptance.get("delivery_identity") == diagnostics_delivery.get("identity")
        and acceptance.get("final_source_identity") == final_archive_values[2]
        and acceptance.get("preflight_report_sha256") == _sha(preflight)
        and acceptance.get("preflight_audit_source_identity") == precheck_archive_values[2]
        and acceptance.get("historical_consumed") == (
            OLD_CONSUMED if _sources is None else _sources.dataset_count("historical_consumed")
        )
        and acceptance.get("historical_unknown") == 0
        and acceptance.get("placement_consumed") == 0
        and acceptance.get("placement_unknown") == 0,
        "diagnostics_acceptance_content_mismatch",
    )
    if _sources is None:
        manifest, invocation, input_records = _validate_placement_inputs(repo, experiment, delivery)
    else:
        manifest, invocation, input_records = _validate_placement_inputs(
            repo, experiment, delivery, _sources=_sources,
        )
    precheck_archive = _verify_archive(
        diagnostics,
        "verification/source-audit-strict-dedupe/source-native.zip",
        "verification/source-audit-strict-dedupe/source-native-file-list.json",
        *precheck_archive_values,
    )
    final_archive = _verify_archive(
        diagnostics / "final-build",
        "source-native.zip",
        "source-native-file-list.json",
        *final_archive_values,
    )
    with __import__("zipfile").ZipFile(diagnostics / "verification/source-audit-strict-dedupe/source-native.zip") as left, __import__("zipfile").ZipFile(diagnostics / "final-build/source-native.zip") as right:
        left_files = set(left.namelist())
        right_files = set(right.namelist())
        left_hashes = {name: _sha(left.read(name)) for name in left_files}
        right_hashes = {name: _sha(right.read(name)) for name in right_files}
    changed = {name for name in set(left_hashes) | set(right_hashes) if left_hashes.get(name) != right_hashes.get(name)}
    expected_changes = DOC_ONLY_CHANGES if _sources is None else set(_sources.differences("placement_confirmation"))
    require(changed == expected_changes, "source_archive_change_set_mismatch")
    source_records = [
        {"role": "diagnostics_acceptance", "path": acceptance_path.relative_to(repo).as_posix(), "sha256": _sha(acceptance_raw)},
        {"role": "diagnostics_delivery", "path": diagnostics_delivery_path.relative_to(repo).as_posix(), "sha256": _sha(diagnostics_delivery_raw)},
        {"role": "diagnostics_build_record", "path": build_record_path.relative_to(repo).as_posix(), "sha256": _sha(build_record_raw)},
        {"role": "diagnostics_preflight_report", "path": (diagnostics / "preflight-report.json").relative_to(repo).as_posix(), "sha256": _sha(preflight)},
        *delivery_records,
        *input_records,
    ]
    return manifest, source_records, {"precheck": precheck_archive, "final": final_archive, "document_changes": sorted(changed)}


def _verify_history(repo: Path, baseline_dir: Path,
                    protection_scope: str | None = None, *, _sources=None) -> tuple[dict, dict[Path, str], dict]:
    """Verify the pinned diagnostics handoff and all seven historical ledgers without a process."""
    from ygo_eval.native_tenki_placement import (
        CURRY_SCOPE_PROTECTED_SOURCE_CHANGE,
        OUTPUT_ROOT_RELATIVE as old_experiment_relative,
        _scope_protected_source_change,
        _transition_payload_from_current,
        collect_baseline_bytes,
    )
    from ygo_eval.tenki_placement_diagnostics import (
        HISTORICAL_NATIVE_SOURCE,
        NATIVE_SOURCE_ARCHIVE_SHA256,
        NATIVE_SOURCE_FILE_LIST_SHA256,
        _verify_archive,
    )

    diagnostics = _safe_dir(baseline_dir)
    require(diagnostics == repo / DIAGNOSTICS_RELATIVE, "fixed_confirmation_baseline_required")
    experiment = repo / OLD_PLACEMENT_RELATIVE
    source_before = stable_source(repo)

    if _sources is None:
        placement_manifest, anchored_inputs, archives = _verify_archives_and_acceptance(
            repo, diagnostics, experiment,
        )
    else:
        placement_manifest, anchored_inputs, archives = _verify_archives_and_acceptance(
            repo, diagnostics, experiment, _sources=_sources,
        )
    transition_path = repo / old_experiment_relative / "baseline-transition.json"
    transition_expected = None if _sources is None else _sources.file_sha256(transition_path.relative_to(repo).as_posix())
    transition_new_worker_sha256 = (
        "4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680"
        if _sources is None
        else _sources.child("baseline").semantic_sha256("transition_new_worker_sha256")
    )
    transition_raw = _safe_file(transition_path).read_bytes()
    require(transition_expected is None or _sha(transition_raw) == transition_expected, "source_description_file_binding_mismatch")
    transition = strict_json(transition_raw)
    transition_hash = _sha(transition_raw)
    old_delivery_path = experiment / "final-build/delivery.json"
    old_delivery_raw = _safe_file(old_delivery_path).read_bytes()
    if _sources is not None:
        require(_sha(old_delivery_raw) == _sources.file_sha256(old_delivery_path.relative_to(repo).as_posix()), "source_description_file_binding_mismatch")
    old_delivery = strict_json(old_delivery_raw)
    declared_transition = old_delivery.get("baseline_transition")
    require(
        isinstance(declared_transition, dict)
        and declared_transition.get("sha256") == transition_hash
        and declared_transition.get("version") == "v2"
        and transition.get("schema_version") == 2
        and transition.get("kind") == "tenki_placement_baseline_transition"
        and transition.get("scope") == "tenki-placement-probe-v1"
        and transition.get("migration", {}).get("path") == "target/debug/ygo-engine-worker.exe"
        and transition.get("migration", {}).get("observed_sha256") == transition_new_worker_sha256
        and transition.get("claims", {}).get("binary_provenance_verified") is False
        and transition.get("claims", {}).get("historical_reexecution_verified") is False,
        "prior_transition_provenance_mismatch",
    )

    # This fixed prior collector validates its own old scope and v2 migration, but
    # it is used only to authenticate provenance; no old authorization is inherited.
    # The prior v2 transition binds the audit module archived with that old
    # scope.  Reconstruct that exact provenance binding; never substitute the
    # current module identity or treat the old migration as this scope's grant.
    historical_archive_pin = None if _sources is None else _sources.archive("placement_history_archive")
    if historical_archive_pin is None:
        historical_archive_values = (
            NATIVE_SOURCE_ARCHIVE_SHA256, NATIVE_SOURCE_FILE_LIST_SHA256,
            HISTORICAL_NATIVE_SOURCE, 401,
        )
    else:
        history_archive_path = experiment / "source-native.zip"
        history_list_path = experiment / "source-native-file-list.json"
        require(
            historical_archive_pin.archive_path == history_archive_path.relative_to(repo).as_posix()
            and historical_archive_pin.file_list_path == history_list_path.relative_to(repo).as_posix(),
            "source_description_archive_path_mismatch",
        )
        historical_archive_values = (
            historical_archive_pin.archive_sha256, historical_archive_pin.file_list_sha256,
            historical_archive_pin.source_identity, historical_archive_pin.file_count,
        )
    historical_archive = _verify_archive(
        experiment,
        "source-native.zip",
        "source-native-file-list.json",
        *historical_archive_values,
    )
    baseline_sources = None if _sources is None else _sources.child("baseline")
    if baseline_sources is None:
        transition_payload = _transition_payload_from_current(
            repo / PROMPT_BASELINE_RELATIVE, repo, 2, protection_scope,
        )
    else:
        transition_payload = _transition_payload_from_current(
            repo / PROMPT_BASELINE_RELATIVE, repo, 2, protection_scope,
            _sources=baseline_sources,
        )
    historical_source_identity = (
        HISTORICAL_NATIVE_SOURCE
        if historical_archive_pin is None
        else historical_archive_pin.source_identity
    )
    transition_payload["audit_tool"] = {
        "source_identity": historical_source_identity,
        "module_sha256": historical_archive["archived_audit_tool_sha256"],
    }
    transition_payload["input_sha256"]["audit_tool_source"] = historical_source_identity
    transition_payload["input_sha256"]["audit_tool_module"] = historical_archive["archived_audit_tool_sha256"]
    if baseline_sources is None:
        old_report, protected = collect_baseline_bytes(
            repo / PROMPT_BASELINE_RELATIVE,
            repo,
            transition_path=transition_path,
            report_version=2,
            transition_payload_override=transition_payload,
            protection_scope=protection_scope,
        )
    else:
        old_report, protected = collect_baseline_bytes(
            repo / PROMPT_BASELINE_RELATIVE,
            repo,
            transition_path=transition_path,
            report_version=2,
            transition_payload_override=transition_payload,
            protection_scope=protection_scope,
            _sources=baseline_sources,
        )
    ledger_sources = None if _sources is None else _sources.child("historical_ledgers")
    history_expected_consumed = (
        OLD_CONSUMED if ledger_sources is None else ledger_sources.dataset_count("consumed")
    )
    require(
        old_report.get("historical_consumed") == history_expected_consumed
        and old_report.get("unknown") == 0
        and old_report.get("native_calls") == 0
        and old_report.get("baseline_transition", {}).get("report_version") == 2
        and old_report.get("baseline_transition", {}).get("scope") == "tenki-placement-probe-v1"
        and old_report.get("baseline_transition", {}).get("sha256") == transition_hash,
        "prior_baseline_audit_mismatch",
    )
    ledgers = _audit_old_ledgers(repo, _sources=ledger_sources)
    require(
        _old_ledger_hashes_match(ledgers, ledger_sources)
        and sum(item["stats"]["consumed"] for item in ledgers) == history_expected_consumed
        and sum(item["stats"]["unknown"] for item in ledgers) == 0,
        "seven_ledger_history_mismatch",
    )

    protected_hashes = {}
    for path, expected in protected.items():
        absolute = Path(os.path.abspath(path))
        require(_sha(_safe_file(absolute).read_bytes()) == expected, "historical_protected_input_changed")
        protected_hashes[absolute] = expected
    for item in anchored_inputs:
        path = _safe_file(repo / Path(item["path"]))
        require(_sha(path.read_bytes()) == item["sha256"], "historical_delivery_input_changed")
        protected_hashes[path] = item["sha256"]
    protected_hashes[transition_path] = transition_hash

    # Include the seven ledger bytes explicitly even when they are outside the
    # oldest baseline's six-ledger protected map.
    expected_ledger_hashes = _old_ledger_expected_hashes(ledger_sources)
    for contract, expected_hash in zip(OLD_LEDGER_CONTRACTS, expected_ledger_hashes, strict=True):
        path = _safe_file(repo / contract[1])
        require(_sha(path.read_bytes()) == expected_hash, "historical_ledger_sha256_mismatch")
        protected_hashes[path] = expected_hash

    source_records = [
        {"role": item["role"], "path": item["path"], "sha256": item["sha256"]}
        for item in anchored_inputs
    ]
    source_records.append({
        "role": "prior_baseline_transition",
        "path": transition_path.relative_to(repo).as_posix(),
        "sha256": transition_hash,
    })
    input_digest = digest(canonical([
        {"path": path.relative_to(repo).as_posix(), "sha256": value}
        for path, value in sorted(protected_hashes.items(), key=lambda pair: pair[0].as_posix())
    ]))
    require(stable_source(repo) == source_before, "workspace_source_changed_during_history_audit")
    for path, expected in protected_hashes.items():
        require(_sha(path.read_bytes()) == expected, "history_input_changed_during_audit")

    diagnostics_acceptance_sha256 = next(
        item["sha256"] for item in anchored_inputs
        if item.get("role") == "diagnostics_acceptance"
    )
    diagnostics_delivery_sha256 = next(
        item["sha256"] for item in anchored_inputs
        if item.get("role") == "diagnostics_delivery"
    )
    audit = {
        "schema_version": 1,
        "kind": "tenki_confirmation_historical_audit",
        "diagnostics_acceptance_sha256": diagnostics_acceptance_sha256,
        "diagnostics_delivery_sha256": diagnostics_delivery_sha256,
        "placement_delivery_sha256": _sha(old_delivery_raw),
        "prior_transition_sha256": transition_hash,
        "prior_transition_scope": transition["scope"],
        "prior_transition_is_provenance_only": True,
        "old_scope_authorization_inherited": False,
        "source_archive_audits": archives,
        "ledgers": [
            {
                "role": item["role"],
                "sha256": item["sha256"],
                "records": item["record_count"],
                "stats": item["stats"],
                "checkpoints": item["checkpoints"],
            }
            for item in ledgers
        ],
        "old_consumed": history_expected_consumed,
        "unknown": 0,
        "old_runner_availability_reverified": False,
        "scope_protected_source_change": (
            None if protection_scope is None else {
                "scope": CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["scope"],
                "path": CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["path"],
                "historical_sha256": _scope_protected_source_change(
                    protection_scope, _sources=_sources,
                )["old_sha256"],
                "current_sha256": _scope_protected_source_change(
                    protection_scope, _sources=_sources,
                )["new_sha256"],
                "historical_bytes_verified_from_archive": True,
            }
        ),
        "native_calls": 0,
        "input_set_sha256": input_digest,
    }
    return audit, protected_hashes, {
        "manifest": placement_manifest,
        "records": source_records,
        "input_digest": input_digest,
        "source_identity": source_before["identity"],
    }


def _fixed_paths(args: argparse.Namespace, repo: Path) -> tuple[Path, Path, dict[str, Path]]:
    root = repo / OUTPUT_RELATIVE
    require(Path(os.path.abspath(args.baseline_dir)) == repo / DIAGNOSTICS_RELATIVE, "fixed_confirmation_baseline_required")
    expected = {
        "runner": root / "native-artifacts" / "tenki-placement-probe.exe",
        "worker": root / "native-artifacts" / "ygo-engine-worker.exe",
        "build_record": root / "build-record.json",
        "identity": root / "identity.json",
        "window_start": root / "window-start.json",
    }
    actual = {name: Path(os.path.abspath(getattr(args, name))) for name in expected}
    for name in expected:
        require(actual[name] == expected[name], f"fixed_{name}_path_required")
    output = Path(os.path.abspath(args.output))
    require(output == root / "research", "fixed_confirmation_output_required")
    require(not root.is_symlink() and not output.is_symlink(), "linked_confirmation_output_rejected")
    for path in (*actual.values(), Path(os.path.abspath(args.baseline_dir))):
        require(
            path != output and not path.is_relative_to(output) and not output.is_relative_to(path),
            "confirmation_output_overlaps_input",
        )
    return root, output, actual


def _verify_build_and_identity(args: argparse.Namespace, repo: Path, root: Path, paths: dict[str, Path], source: dict) -> tuple[dict, dict, Path, str]:
    cli = root / "native-artifacts" / "ygo-cli.exe"
    for path in (paths["runner"], paths["worker"], paths["build_record"], cli):
        require(_safe_file(path).is_file(), "frozen_build_artifact_missing")
    build_raw = _safe_file(paths["build_record"]).read_bytes()
    build = strict_json(build_raw)
    from ygo_eval.native_tenki_placement import _validate_signed

    _validate_signed(build, "build_record")
    require(
        build.get("status") == "recorded"
        and build.get("source_before") == source
        and build.get("source_after") == source
        and build.get("reproducible_build_proven") is False,
        "confirmation_build_source_identity_mismatch",
    )
    artifacts = build.get("artifacts")
    require(isinstance(artifacts, dict), "confirmation_build_artifacts_missing")
    artifact_paths = {"runner": paths["runner"], "worker": paths["worker"], "cli": cli}
    for role, path in artifact_paths.items():
        require(artifacts.get(role) == _sha(_safe_file(path).read_bytes()), f"confirmation_{role}_build_hash_mismatch")
    require(artifacts.get("cli") == _sha(_safe_file(cli).read_bytes()), "confirmation_cli_build_hash_mismatch")
    return build, artifacts, cli, _sha(build_raw)


def _verify_workspace_identity(identity: dict, source: dict, artifacts: dict, worker: Path, request: dict) -> tuple[dict, dict]:
    from ygo_eval.native_tenki_placement import _assert_runtime_identity, _validate_signed

    _validate_signed(identity, "workspace_identity")
    require(
        identity.get("source") == source
        and identity.get("consistent") is True
        and identity.get("build_provenance") == "unverified"
        and identity.get("reproducible_build_proven") is False
        and identity.get("cli_sha256") == artifacts.get("cli"),
        "candidate_workspace_identity_mismatch",
    )
    ordinary, tournament = _assert_runtime_identity(identity, worker, request)
    require(
        isinstance(tournament.get("identity"), str)
        and re.fullmatch(r"[a-f0-9]{64}", tournament["identity"]),
        "tournament_runtime_identity_missing",
    )
    return ordinary, tournament


def _window_start(path: Path) -> dict:
    """Create or verify this scope's immutable two-hour window."""
    from ygo_eval.terminal_regression import immutable_write

    require(path.name == "window-start.json", "fixed_confirmation_window_path_required")
    if path.exists():
        value = strict_json(_safe_file(path).read_bytes())
        require(
            value.get("schema_version") == 1
            and value.get("kind") == "tenki_placement_confirmation_window_start"
            and value.get("scope") == SCOPE
            and value.get("limit") == LIMIT
            and value.get("wall_seconds") == WINDOW_SECONDS
            and type(value.get("started_at")) is int
            and 0 <= value["started_at"] <= int(time.time()),
            "confirmation_window_start_mismatch",
        )
        return value
    value = {
        "schema_version": 1,
        "kind": "tenki_placement_confirmation_window_start",
        "scope": SCOPE,
        "limit": LIMIT,
        "wall_seconds": WINDOW_SECONDS,
        "started_at": int(time.time()),
    }
    immutable_write(path, value)
    return value


def _hash_tree(paths: dict[Path, str]) -> dict[str, str]:
    return {path.as_posix(): value for path, value in sorted(paths.items(), key=lambda item: item[0].as_posix())}


def _assert_unchanged(repo: Path, source: dict, protected: dict[Path, str]) -> None:
    require(stable_source(repo) == source, "workspace_source_changed")
    for path, expected in protected.items():
        require(_sha(_safe_file(path).read_bytes()) == expected, "historical_protected_input_changed")


def _derive_confirmation_request(stage: int, parent: dict) -> dict:
    from ygo_eval.native_tenki_placement import (
        YES_NO_DESCRIPTION,
        _check_actions,
        _pending_raw,
        expected_place_responses,
        select_zone_zero,
    )

    parent_stage = {2: 1, 3: 2, 4: 3, 5: 2, 6: 5}.get(stage)
    require(parent_stage is not None, "confirmation_stage_derivation_invalid")
    require(
        parent.get("schema_version") == 1
        and parent.get("kind") == "native_tenki_placement_confirmation_stage"
        and parent.get("scope") == SCOPE
        and parent.get("stage") == parent_stage
        and parent.get("successful") is True
        and parent.get("diagnostic") is None
        and parent.get("proof_ready") is False
        and parent.get("complete_action_coverage") is False
        and parent.get("global_optimality") is False
        and parent.get("native_probability_verified") is False
        and parent.get("assets_unchanged") is True
        and parent.get("assets_before") == parent.get("assets_after"),
        "confirmation_parent_receipt_required",
    )
    require(
        parent.get("ledger") == {
            "consumed": parent_stage,
            "completed": parent_stage,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": LIMIT,
        },
        "confirmation_parent_ledger_prefix_invalid",
    )
    result = parent.get("result", {}).get("Ok")
    request = parent.get("request")
    require(
        isinstance(result, dict)
        and result.get("status") == "decision_required"
        and result.get("error") is None
        and not result.get("coverage_gaps")
        and isinstance(request, dict)
        and isinstance(request.get("decisions"), list)
        and result.get("resolved_decisions") == request["decisions"],
        "confirmation_parent_decisions_unconsumed",
    )
    if stage in (4, 6):
        return copy.deepcopy(request)
    if stage == 2:
        prompt, raw = _pending_raw(result, 18)
        _check_actions(raw, prompt, expected_place_responses(raw))
        action = select_zone_zero(prompt)
    else:
        prompt, raw = _pending_raw(result, 13)
        expected_raw = bytes([13, 0]) + YES_NO_DESCRIPTION.to_bytes(8, "little")
        require(raw == expected_raw, "confirmation_opcode13_raw_mismatch")
        expected = [[0, 0, 0, 0], [1, 0, 0, 0]]
        _check_actions(raw, prompt, expected)
        yes = stage == 5
        expected_bytes = [1, 0, 0, 0] if yes else [0, 0, 0, 0]
        matches = [
            item for item in prompt["actions"]
            if item.get("choice") == {"kind": "yes_no", "yes": yes}
            and item.get("bytes") == expected_bytes
        ]
        require(len(matches) == 1, "confirmation_opcode13_choice_not_unique")
        action = matches[0]
    derived = copy.deepcopy(request)
    derived["decisions"] = copy.deepcopy(result["resolved_decisions"]) + [{
        "prompt_id": prompt["id"],
        "player": 0,
        "choice": copy.deepcopy(action["choice"]),
    }]
    return derived


def _validate_stage_receipt(
    receipt: dict,
    request: dict,
    context: str,
    stage: int,
    expected_identity: dict | None = None,
) -> None:
    from ygo_eval.native_tenki_placement import (
        YES_NO_DESCRIPTION,
        _check_actions,
        _pending_raw,
        expected_place_responses,
    )

    require(
        receipt.get("schema_version") == 1
        and receipt.get("kind") == "native_tenki_placement_confirmation_stage"
        and receipt.get("scope") == SCOPE
        and receipt.get("context") == context
        and receipt.get("stage") == stage
        and receipt.get("request") == request
        and type(receipt.get("successful")) is bool
        and all(receipt.get(flag) is False for flag in FLAGS),
        "confirmation_stage_receipt_binding_invalid",
    )
    require(
        receipt.get("ledger") == {
            "consumed": stage,
            "completed": stage,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": LIMIT,
        },
        "confirmation_stage_ledger_prefix_invalid",
    )
    require(
        receipt.get("diagnostic") is None
        and receipt.get("assets_unchanged") is True
        and receipt.get("assets_before") == receipt.get("assets_after")
        and (expected_identity is None or receipt.get("assets_before") == expected_identity)
        and receipt.get("window_valid_at_result") is True,
        "confirmation_stage_assets_or_window_invalid",
    )
    validation = receipt.get("validation", {}).get("Ok", {})
    require(validation.get("response_oracle_matches") is True, "confirmation_stage_response_oracle_failed")
    result = receipt.get("result", {}).get("Ok", {})
    require(
        result.get("status") == "decision_required"
        and result.get("error") is None
        and not result.get("coverage_gaps")
        and result.get("resolved_decisions") == request.get("decisions"),
        "confirmation_stage_result_or_decisions_invalid",
    )
    prompts = {1: 18, 2: 13, 3: 11, 4: 11, 5: 15, 6: 15}
    prompt = result.get("prompt")
    require(
        isinstance(prompt, dict)
        and prompt.get("opcode") == prompts[stage]
        and prompt.get("player") == 0,
        "confirmation_stage_unexpected_prompt",
    )
    if stage in (1, 4, 6):
        # Stage 1's response set is the fixed coordinate oracle. Replays are
        # checked by the independent Rust comparator and are not re-enumerated here.
        if stage == 1:
            pending, raw = _pending_raw(result, 18)
            _check_actions(raw, pending, expected_place_responses(raw))
    if stage == 2:
        pending, raw = _pending_raw(result, 13)
        require(raw == bytes([13, 0]) + YES_NO_DESCRIPTION.to_bytes(8, "little"), "confirmation_stage_opcode13_frame_invalid")
        _check_actions(raw, pending, [[0, 0, 0, 0], [1, 0, 0, 0]])
    if stage in (5, 6):
        pending, raw = _pending_raw(result, 15)
        require(
            len(raw) == 43
            and raw[:3] == bytes([15, 0, 0])
            and int.from_bytes(raw[3:7], "little") == 1
            and int.from_bytes(raw[7:11], "little") == 1
            and int.from_bytes(raw[11:15], "little") == 2
            and len(pending.get("actions", [])) == 2,
            "confirmation_stage_opcode15_frame_invalid",
        )
        sequences = set()
        for index, (record_bytes, action) in enumerate(zip(
            (raw[15:29], raw[29:43]), pending["actions"]
        )):
            code = int.from_bytes(record_bytes[:4], "little")
            sequence = int.from_bytes(record_bytes[6:10], "little")
            position = int.from_bytes(record_bytes[10:14], "little")
            expected_bytes = list((0).to_bytes(4, "little") + (1).to_bytes(4, "little") + index.to_bytes(4, "little"))
            require(
                code == 69_247_929
                and record_bytes[4:6] == bytes([0, 1])
                and sequence < 35
                and sequence not in sequences
                and position in {0, 1, 2, 4, 8}
                and action.get("card_ids") == [69_247_929]
                and action.get("choice") == {"kind": "cards", "indices": [index]}
                and action.get("bytes") == expected_bytes,
                "confirmation_stage_opcode15_candidate_or_response_mismatch",
            )
            sequences.add(sequence)
    replay = receipt.get("independent_replay_matches")
    if stage in (4, 6):
        require(receipt.get("successful") is True and replay is True, "confirmation_stage_replay_mismatch")
    else:
        require(replay is None, "confirmation_unexpected_replay_qualification")


def _diagnostic_hash(repo: Path, record: dict) -> str:
    return process_diagnostic_sha256(
        Path(repo), record,
        runner_role=WORKFLOW_SPEC.runner_role,
        safe_file=_safe_file,
        strict_json=strict_json,
    )


def _run_process(
    runner: Path,
    input_path: Path,
    repo: Path,
    root: Path,
    mode: str,
    *,
    prepared_hash: str | None = None,
    timeout: float | None = None,
):
    require(mode != "normal" or prepared_hash is not None,
            "confirmation_prepared_report_hash_required")
    if mode == "normal":
        require(
            isinstance(timeout, (int, float))
            and type(timeout) is not bool
            and math.isfinite(timeout)
            and timeout > 0,
            "confirmation_runner_window_timeout_required",
        )
    record, completed = capture_runner_process(
        runner=runner,
        input_path=input_path,
        repo=repo,
        root=root,
        mode=mode,
        input_sha256=_sha(_safe_file(input_path).read_bytes()),
        prepared_hash=prepared_hash,
        timeout=timeout if timeout is not None else WORKER_TIMEOUT_MS / 1000 + 30,
        runner_role=WORKFLOW_SPEC.runner_role,
        trace_stderr=WORKFLOW_SPEC.trace_stderr,
        process_runner=subprocess.run,
    )
    return record, completed, _diagnostic_hash(root, record)


def _normal_runner_timeout(invocation: dict, *, now: float | None = None) -> float:
    """Return only the remaining frozen window after enforcing the worker margin."""
    started_at = invocation.get("started_at") if isinstance(invocation, dict) else None
    require(type(started_at) is int and started_at >= 0, "confirmation_window_start_invalid")
    try:
        return normal_runner_timeout(
            started_at,
            wall_seconds=WINDOW_SECONDS,
            worker_timeout_seconds=WORKER_TIMEOUT_MS / 1000,
            now=now,
            error_prefix="confirmation",
        )
    except ValueError as error:
        # Preserve the long-standing confirmation error vocabulary.
        message = str(error)
        if message == "confirmation_window_clock_invalid":
            raise
        raise


def _process_exit_succeeded(completed: subprocess.CompletedProcess | None) -> bool:
    return completed is not None and completed.returncode == 0


def _stats_for_missing_ledger(*, normal_attempted: bool) -> dict | None:
    """Only a confirmed pre-charge absence is zero; afterwards it is unknown."""
    if normal_attempted:
        return None
    return {"consumed": 0, "completed": 0, "unknown": 0, "reserved": 0, "abandoned": 0, "limit": LIMIT}


def _preflight_output_matches(preflight: object, manifest: dict, expected_identity: dict, *, calls_present: bool) -> bool:
    """Bind the runner's preflight to the ordinary asset identity, not wrapper identity."""
    return (
        isinstance(preflight, dict)
        and preflight.get("preflight_passed") is True
        and preflight.get("native_calls") == 0
        and preflight.get("stage") == 1
        and preflight.get("context") == manifest.get("context")
        and preflight.get("identity_sha256") == expected_identity.get("identity")
        and not calls_present
    )


def _validate_manifest(manifest: dict) -> None:
    require(
        isinstance(manifest, dict)
        and manifest.get("schema_version") == 1
        and manifest.get("kind") == "native_tenki_placement_confirmation_manifest"
        and manifest.get("scope") == SCOPE
        and manifest.get("limit") == LIMIT
        and manifest.get("wall_seconds") == WINDOW_SECONDS
        and manifest.get("old_consumed") == OLD_CONSUMED
        and type(manifest.get("started_at")) is int
        and _require_sha(manifest.get("context"), "confirmation_manifest_context_invalid")
        and manifest.get("context") == digest(canonical({key: item for key, item in manifest.items() if key != "context"})),
        "confirmation_manifest_binding_invalid",
    )
    require(all(manifest.get(flag) is False for flag in FLAGS), "research_qualification_must_remain_false")
    input_hashes = manifest.get("input_sha256")
    require(
        isinstance(input_hashes, dict)
        and _require_sha(input_hashes.get("prompt_source_stage1"), "confirmation_prompt_source_stage1_hash_invalid")
        and _require_sha(input_hashes.get("prompt_source_stage2_request"), "confirmation_prompt_source_stage2_request_hash_invalid"),
        "confirmation_prompt_source_hashes_missing",
    )


def _read_prepared(output: Path, manifest: dict, repo: Path) -> tuple[dict, str]:
    raw = _safe_file(output / "prepared.json").read_bytes()
    prepared = strict_json(raw)
    validate_report(prepared, repo)
    require(
        prepared.get("context") == manifest["context"]
        and prepared.get("execution_ready") is True
        and prepared.get("manifest_sha256") == _sha(_safe_file(output / "manifest.json").read_bytes())
        and prepared.get("stage1_input_sha256") == _sha(_safe_file(output / "stage-1-input.json").read_bytes()),
        "confirmation_prepared_binding_invalid",
    )
    preflight_record = strict_json(_safe_file(output / "preflight-process-diagnostic.json").read_bytes())
    require(_diagnostic_hash(output.parents[0], preflight_record) == prepared.get("preflight_diagnostic_sha256"), "confirmation_preflight_diagnostic_binding_invalid")
    preflight_path = output.parents[0] / preflight_record["stdout"]["path"]
    preflight = strict_json(_safe_file(preflight_path).read_bytes())
    require(
        preflight.get("preflight_passed") is True
        and preflight.get("native_calls") == 0
        and preflight.get("context") == manifest["context"]
        and preflight.get("stage") == 1,
        "confirmation_saved_preflight_invalid",
    )
    return prepared, _sha(raw)


def _verify_saved_build_inputs(root: Path, manifest: dict, runner: Path) -> None:
    require(_sha(_safe_file(runner).read_bytes()) == manifest.get("input_sha256", {}).get("runner"), "saved_confirmation_runner_mismatch")
    for name in ("build-record.json", "identity.json", "source-native.zip", "source-native-file-list.json"):
        key = {
            "build-record.json": "build_record",
            "identity.json": "identity",
            "source-native.zip": "source_archive",
            "source-native-file-list.json": "source_file_list",
        }[name]
        path = _safe_file(root / name)
        require(_sha(path.read_bytes()) == manifest.get("input_sha256", {}).get(key), f"saved_confirmation_{key}_mismatch")
    identity = strict_json(_safe_file(root / "identity.json").read_bytes())
    from ygo_eval.native_tenki_placement import _assert_runtime_identity, _validate_signed
    _validate_signed(identity, "workspace_identity")
    request = manifest.get("request")
    require(isinstance(request, dict), "saved_confirmation_request_missing")
    ordinary, tournament = _assert_runtime_identity(identity, root / "native-artifacts/ygo-engine-worker.exe", request)
    require(
        ordinary == manifest.get("assets", {}).get("ordinary")
        and tournament == manifest.get("assets", {}).get("tournament"),
        "saved_confirmation_dual_asset_identity_mismatch",
    )
    artifacts = manifest.get("build", {}).get("artifacts", {})
    require(
        _sha(_safe_file(runner).read_bytes()) == artifacts.get("runner")
        and _sha(_safe_file(root / "native-artifacts/ygo-engine-worker.exe").read_bytes()) == artifacts.get("worker")
        and _sha(_safe_file(root / "native-artifacts/ygo-cli.exe").read_bytes()) == artifacts.get("cli"),
        "saved_confirmation_build_artifacts_mismatch",
    )


def _candidate_request(repo: Path, prompt_baseline: Path, worker: Path) -> tuple[dict, dict]:
    from ygo_eval.native_tenki_placement import (
        PREPARATION_RELATIVE,
        PREPARATION_SHA256,
        _activation_from_history,
        _read,
    )
    from ygo_eval.research import validate_sources

    stage_one = strict_json(_safe_file(prompt_baseline / "research/stage-1.json").read_bytes())
    stage_two = strict_json(_safe_file(prompt_baseline / "research/stage-2-request.json").read_bytes())
    request = _activation_from_history(stage_one, stage_two)
    request["engine"]["worker_path"] = str(worker)
    require(
        request.get("protocol_version") == 2
        and request.get("probe_only") is False
        and request.get("scenario") is None
        and request.get("interruption") is None
        and request.get("first_turn") is None
        and request.get("research_capture") is None,
        "frozen_protocol2_request_required",
    )
    preparation_raw, preparation_hash = _read(repo / PREPARATION_RELATIVE, PREPARATION_SHA256)
    preparation = strict_json(preparation_raw)
    candidates = [
        item for item in preparation.get("candidates", [])
        if item.get("case", {}).get("case_id") == "prompt-13-tenki-v1"
    ]
    require(len(candidates) == 1, "frozen_tenki_case_missing")
    banlist = _safe_file(repo / "data/runtime/banlist.json")
    validate_sources(candidates[0]["case"], request, banlist)
    return request, {
        "preparation_sha256": preparation_hash,
        "old_stage1_sha256": _sha(_safe_file(prompt_baseline / "research/stage-1.json").read_bytes()),
        "old_stage2_request_sha256": _sha(_safe_file(prompt_baseline / "research/stage-2-request.json").read_bytes()),
        "banlist_sha256": _sha(banlist.read_bytes()),
        "case_id": "prompt-13-tenki-v1",
    }


def _stage_invocation(context: str, output: Path, stage: int, request: dict, expected_identity: dict, started_at: int) -> dict:
    return {
        "batch_kind": SCOPE,
        "context": context,
        "ledger": str(output / "calls.jsonl"),
        "output": str(output / f"stage-{stage}.json"),
        "stage": stage,
        "request": copy.deepcopy(request),
        "expected_identity": copy.deepcopy(expected_identity),
        "started_at": started_at,
    }


def _save_stage_files(output: Path, context: str, stage: int, request: dict, expected_identity: dict, started_at: int) -> tuple[Path, Path]:
    invocation = _stage_invocation(context, output, stage, request, expected_identity, started_at)
    request_path = output / f"stage-{stage}-request.json"
    input_path = output / f"stage-{stage}-input.json"
    immutable_write(request_path, request)
    immutable_write(input_path, invocation)
    immutable_write(output / f"stage-{stage}-input-seal.json", {
        "schema_version": 1,
        "kind": "tenki_placement_confirmation_stage_input_seal",
        "context": context,
        "stage": stage,
        "input_sha256": _sha(_safe_file(input_path).read_bytes()),
    })
    return input_path, request_path


def _read_runner_stats(runner: Path, input_path: Path, repo: Path, root: Path) -> tuple[dict | None, dict, Any]:
    process, completed, diagnostic_sha = _run_process(runner, input_path, repo, root, "stats", timeout=75)
    stats = None
    if process.get("status") == "completed" and completed is not None and completed.returncode == 0:
        try:
            value = strict_json(completed.stdout)
            if isinstance(value, dict) and value.get("native_calls") == 0 and isinstance(value.get("ledger"), dict):
                stats = value["ledger"]
        except (ValueError, UnicodeDecodeError, TypeError):
            stats = None
    return stats, process, diagnostic_sha


def _valid_stats(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and all(type(value.get(key)) is int and value[key] >= 0 for key in ("consumed", "completed", "unknown", "reserved", "abandoned", "limit"))
        and value.get("limit") == LIMIT
    )


def _receipt_digest(path: Path) -> str:
    return _sha(_safe_file(path).read_bytes()) if path.is_file() else None


def _record_process_sidecar(path: Path, record: dict) -> None:
    immutable_write(path, record)


def _save_orchestration_diagnostic(output: Path, stage: int, reason: str) -> str:
    value = {
        "schema_version": 1,
        "kind": "tenki_placement_confirmation_orchestration_diagnostic",
        "scope": SCOPE,
        "stage": stage,
        "diagnostic": reason,
    }
    path = output / f"stage-{stage}-orchestration-diagnostic.json"
    immutable_write(path, value)
    return _sha(_safe_file(path).read_bytes())


def _read_receipt_if_present(path: Path) -> dict | None:
    if not path.exists():
        return None
    return strict_json(_safe_file(path).read_bytes())


def _stage_report(context: str, stage: int, receipt: dict | None, receipt_path: Path, diagnostic_sha: str, native_calls: int | None, reason: str | None, fallback_ledger: dict | None = None) -> dict:
    successful = bool(receipt and receipt.get("successful") is True and reason is None)
    replay = None
    if stage in (4, 6):
        replay = receipt.get("independent_replay_matches") if receipt and type(receipt.get("independent_replay_matches")) is bool else False
    ledger = receipt.get("ledger") if isinstance(receipt, dict) else fallback_ledger
    report = {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_stage",
        "scope": SCOPE,
        "context": context,
        "stage": stage,
        "successful": successful,
        "native_calls": native_calls,
        "diagnostic": reason,
        "receipt_sha256": _receipt_digest(receipt_path),
        "diagnostic_sha256": diagnostic_sha,
        "independent_replay_matches": replay,
        "ledger": ledger,
        **FLAGS,
    }
    return report


def _verify_only(root: Path, output: Path, runner: Path, repo: Path) -> dict:
    manifest_raw = _safe_file(output / "manifest.json").read_bytes()
    manifest = strict_json(manifest_raw)
    _validate_manifest(manifest)
    _verify_saved_build_inputs(root, manifest, runner)
    prepared, prepared_hash = _read_prepared(output, manifest, repo)
    stages = []
    diagnostic = None
    stage_numbers = []
    verification_sidecar_hashes = []
    for stage in range(1, LIMIT + 1):
        input_path = output / f"stage-{stage}-input.json"
        request_path = output / f"stage-{stage}-request.json"
        seal_path = output / f"stage-{stage}-input-seal.json"
        receipt_path = output / f"stage-{stage}.json"
        report_path = output / f"stage-{stage}-report.json"
        if not all(path.is_file() for path in (input_path, request_path, seal_path, receipt_path, report_path)):
            diagnostic = "incomplete_stage_receipts"
            break
        invocation = strict_json(_safe_file(input_path).read_bytes())
        request = strict_json(_safe_file(request_path).read_bytes())
        seal = strict_json(_safe_file(seal_path).read_bytes())
        saved_report = strict_json(_safe_file(report_path).read_bytes())
        receipt = strict_json(_safe_file(receipt_path).read_bytes())
        require(
            invocation.get("context") == manifest["context"]
            and invocation.get("stage") == stage
            and invocation.get("batch_kind") == SCOPE
            and invocation.get("request") == request
            and invocation.get("ledger") == str(output / "calls.jsonl")
            and invocation.get("output") == str(receipt_path)
            and seal == {
                "schema_version": 1,
                "kind": "tenki_placement_confirmation_stage_input_seal",
                "context": manifest["context"],
                "stage": stage,
                "input_sha256": _sha(_safe_file(input_path).read_bytes()),
            },
            "saved_confirmation_stage_input_binding_invalid",
        )
        _verify_basic_receipt(receipt, request, manifest["context"], stage)
        validate_report(saved_report, repo)
        require(
            saved_report.get("receipt_sha256") == _sha(_safe_file(receipt_path).read_bytes())
            and saved_report.get("context") == manifest["context"],
            "saved_confirmation_stage_report_mismatch",
        )
        diag_path = root / f"stage-{stage}-process-diagnostic.json"
        diag_record = strict_json(_safe_file(diag_path).read_bytes())
        require(_diagnostic_hash(root, diag_record) == saved_report["diagnostic_sha256"], "saved_confirmation_stage_diagnostic_mismatch")
        process, completed, _diag_sha = _run_process(runner, input_path, repo, root, "verify_recorded")
        verify_diag_path = output / "verification-diagnostics" / f"stage-{stage}-{uuid.uuid4().hex}.json"
        verify_diag_raw = _encode(process)
        immutable_write(verify_diag_path, process)
        verification_sidecar_hashes.append(_sha(verify_diag_raw))
        require(_diag_sha == _diagnostic_hash(root, process), "verification_diagnostic_invalid")
        require(
            process.get("status") == "completed"
            and completed is not None
            and _process_exit_succeeded(completed)
            and isinstance(strict_json(completed.stdout), dict)
            and strict_json(completed.stdout).get("verified_recorded") is True
            and strict_json(completed.stdout).get("native_calls") == 0,
            "confirmation_read_only_receipt_verification_failed",
        )
        stages.append(saved_report)
        stage_numbers.append(stage)

    stats = None
    stats_input = output / "stage-1-input.json"
    ledger = output / "calls.jsonl"
    if ledger.exists() and stats_input.exists():
        process, completed, _diag_sha = _run_process(runner, stats_input, repo, root, "stats")
        if process.get("status") == "completed" and completed is not None and completed.returncode == 0:
            value = strict_json(completed.stdout)
            if isinstance(value, dict) and value.get("native_calls") == 0 and isinstance(value.get("ledger"), dict):
                stats = value["ledger"]
    new_consumed = stats.get("consumed") if isinstance(stats, dict) and type(stats.get("consumed")) is int else None
    unknown = stats.get("unknown") if isinstance(stats, dict) and type(stats.get("unknown")) is int else None
    complete = stage_numbers == list(range(1, LIMIT + 1))
    valid = complete and new_consumed == LIMIT and unknown == 0 and all(item.get("successful") is True for item in stages)
    if not valid and diagnostic is None:
        diagnostic = "saved_confirmation_incomplete_or_invalid"
    report = {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_verification",
        "scope": SCOPE,
        "context": manifest["context"],
        "valid": valid,
        "native_calls": 0,
        "old_consumed": OLD_CONSUMED,
        "new_consumed": new_consumed,
        "cumulative_consumed": OLD_CONSUMED + new_consumed if new_consumed is not None else None,
        "unknown": unknown,
        "stages": stages,
        "prepared_sha256": prepared_hash,
        "verification_diagnostic_sha256": verification_sidecar_hashes,
        "diagnostic": diagnostic,
        **FLAGS,
    }
    validate_report(report, repo)
    verification_path = output / "verification.json"
    if verification_path.exists():
        existing = strict_json(_safe_file(verification_path).read_bytes())
        # Per-run verification diagnostics are unique. Reuse the first sealed
        # verification result on later invocations while still checking every
        # saved receipt and the read-only ledger afresh.
        comparable = {key: value for key, value in report.items() if key != "verification_diagnostic_sha256"}
        prior_comparable = {key: value for key, value in existing.items() if key != "verification_diagnostic_sha256"}
        require(prior_comparable == comparable, "existing_confirmation_verification_differs")
        report = existing
    else:
        immutable_write(verification_path, report)
    return report


def _verify_basic_receipt(receipt: dict, request: dict, context: str, stage: int) -> None:
    require(
        isinstance(receipt, dict)
        and receipt.get("schema_version") == 1
        and receipt.get("kind") == "native_tenki_placement_confirmation_stage"
        and receipt.get("scope") == SCOPE
        and receipt.get("context") == context
        and receipt.get("stage") == stage
        and receipt.get("request") == request
        and type(receipt.get("successful")) is bool
        and all(receipt.get(flag) is False for flag in FLAGS),
        "confirmation_stage_receipt_binding_invalid",
    )
    ledger = receipt.get("ledger")
    require(_valid_stats(ledger) and ledger.get("consumed") <= stage, "confirmation_stage_receipt_ledger_invalid")
    if receipt["successful"]:
        require(ledger == {
            "consumed": stage, "completed": stage, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": LIMIT,
        }, "confirmation_stage_ledger_prefix_invalid")
        _validate_stage_receipt(receipt, request, context, stage)


def _run_six_stages(
    *, root: Path, output: Path, runner: Path, repo: Path, manifest: dict,
    prepared_hash: str, stage1_request: dict, expected_identity: dict,
    source: dict, protected: dict[Path, str], frozen_files: dict[Path, str],
) -> dict:
    def verify_stage_intent(input_path, stage, request, expected_identity, started_at):
        invocation = strict_json(_safe_file(input_path).read_bytes())
        seal = strict_json(_safe_file(output / f"stage-{stage}-input-seal.json").read_bytes())
        require(
            invocation == _stage_invocation(manifest["context"], output, stage,
                                            request, expected_identity, started_at)
            and seal.get("input_sha256") == _sha(_safe_file(input_path).read_bytes()),
            "confirmation_stage_intent_binding_invalid",
        )

    return run_six_stage_workflow(
        spec=WORKFLOW_SPEC,
        root=root,
        output=output,
        runner=runner,
        repo=repo,
        manifest=manifest,
        prepared_hash=prepared_hash,
        stage1_request=stage1_request,
        expected_identity=expected_identity,
        source=source,
        protected=protected,
        frozen_files=frozen_files,
        parent_stage={2: 1, 3: 2, 4: 3, 5: 2, 6: 5},
        derive_request=_derive_confirmation_request,
        save_stage_files=_save_stage_files,
        invocation_for_stage=_stage_invocation,
        verify_stage_intent=verify_stage_intent,
        read_receipt=_read_receipt_if_present,
        run_process=_run_process,
        read_stats=_read_runner_stats,
        valid_stats=_valid_stats,
        missing_ledger_stats=_stats_for_missing_ledger,
        verify_basic_receipt=_verify_basic_receipt,
        validate_stage_receipt=_validate_stage_receipt,
        stage_report=_stage_report,
        validate_report=validate_report,
        summarize=summarize_confirmation,
        diagnostic_hash=_diagnostic_hash,
        save_orchestration_diagnostic=_save_orchestration_diagnostic,
        assert_unchanged=_assert_unchanged,
        safe_file=_safe_file,
        immutable_write=immutable_write,
        sha256=_sha,
        process_exit_succeeded=_process_exit_succeeded,
        strict_json=strict_json,
    )



def _require_ignored_runtime(repo: Path) -> None:
    lines = _safe_file(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    require(
        any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime") for line in lines)
        and not any(line.lstrip().startswith("!") for line in lines),
        "ignored_confirmation_output_contract_missing",
    )


def native_tenki_placement_confirmation(args: argparse.Namespace, repo: Path | None = None) -> dict:
    """Prepare the frozen confirmation input or execute its six fixed stages."""
    from ygo_eval.native_tenki_placement import (
        _archive_current_source,
        _candidate_configs,
        _capture_identity,
    )

    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    root, output, paths = _fixed_paths(args, repo)
    _require_ignored_runtime(repo)
    require(not root.is_symlink() and not output.is_symlink(), "linked_confirmation_directory_rejected")
    require(root.is_dir() and (root / "native-artifacts").is_dir(), "isolated_confirmation_build_required")
    require(output == root / "research", "fixed_confirmation_output_required")
    if args.verify_only:
        require(output.is_dir(), "confirmation_output_missing")
        return _verify_only(root, output, paths["runner"], repo)

    if not args.prepare_only:
        require(output.is_dir() and (output / "manifest.json").is_file() and (output / "prepared.json").is_file(), "confirmation_prepared_input_required")

    require(not args.prepare_only or not (output / "summary.json").exists(), "confirmation_already_executed")
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
    require(output.is_dir(), "confirmation_output_directory_required")

    source_before = stable_source(repo)
    build, artifacts, cli, build_hash = _verify_build_and_identity(args, repo, root, paths, source_before)
    audit, protected, history = _verify_history(repo, Path(args.baseline_dir))
    history_path = output / "historical-audit.json"
    immutable_write(history_path, audit)
    old_placement = repo / OLD_PLACEMENT_RELATIVE
    request, frozen_case = _candidate_request(repo, repo / PROMPT_BASELINE_RELATIVE, paths["worker"])
    source_archive = _archive_current_source(repo, root, source_before)
    configs = _candidate_configs(repo, root, paths["worker"], old_placement)

    if paths["identity"].exists() and not paths["window_start"].exists():
        raise ValueError("identity_exists_without_original_window_start")
    window = _window_start(paths["window_start"])
    started_at = window["started_at"]
    if args.prepare_only:
        require(started_at + WINDOW_SECONDS > int(time.time()), "experiment_window_expired")
    # Identity capture includes the candidate asset scans and therefore happens
    # only after the immutable window start has been durably written.
    identity = _capture_identity(repo, cli, configs, paths["identity"])
    ordinary, tournament = _verify_workspace_identity(identity, source_before, artifacts, paths["worker"], request)

    preparation_hash = frozen_case["preparation_sha256"]
    banlist_path = repo / "data/runtime/banlist.json"
    input_sha256 = {
        "runner": _sha(_safe_file(paths["runner"]).read_bytes()),
        "worker": _sha(_safe_file(paths["worker"]).read_bytes()),
        "cli": _sha(_safe_file(cli).read_bytes()),
        "build_record": build_hash,
        "identity": _sha(_safe_file(paths["identity"]).read_bytes()),
        "window_start": _sha(_safe_file(paths["window_start"]).read_bytes()),
        "source_archive": source_archive["sha256"],
        "source_file_list": source_archive["file_list_sha256"],
        "ordinary_config": _sha(_safe_file(configs["ordinary"]).read_bytes()),
        "tournament_config": _sha(_safe_file(configs["tournament"]).read_bytes()),
        "banlist": _sha(_safe_file(banlist_path).read_bytes()),
        "preparation": preparation_hash,
        "history_audit": _sha(_safe_file(history_path).read_bytes()),
        "prior_transition": history["records"][-1]["sha256"],
        "prompt_source_stage1": frozen_case["old_stage1_sha256"],
        "prompt_source_stage2_request": frozen_case["old_stage2_request_sha256"],
    }
    expected_identity = ordinary
    unsigned = {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_manifest",
        "scope": SCOPE,
        "limit": LIMIT,
        "planned_calls": LIMIT,
        "wall_seconds": WINDOW_SECONDS,
        "started_at": started_at,
        "old_consumed": OLD_CONSUMED,
        "source": source_before,
        "build": {"identity": build.get("identity"), "artifacts": artifacts, "record_sha256": build_hash},
        "assets": {
            "ordinary": ordinary,
            "tournament": tournament,
            "identity_sha256": identity.get("identity"),
            "execution_role": "ordinary",
        },
        "input_sha256": input_sha256,
        "source_archive": source_archive,
        "historical_audit_sha256": input_sha256["history_audit"],
        "historical_input_set_sha256": history["input_digest"],
        "prior_transition_provenance_only": True,
        "request": request,
        "stage1_request_sha256": digest(canonical(request)),
        "request_derivation": "old-public-tenki-activation-only-worker-path-replaced",
        **FLAGS,
    }
    manifest = {**unsigned, "context": digest(canonical(unsigned))}
    _validate_manifest(manifest)
    manifest_path = output / "manifest.json"
    immutable_write(manifest_path, manifest)
    stage1_input, _ = _save_stage_files(output, manifest["context"], 1, request, expected_identity, started_at)

    if args.prepare_only:
        require(not (output / "calls.jsonl").exists(), "preflight_requires_absent_charge_ledger")
        previous = output / "prepared.json"
        if previous.exists():
            prepared, _ = _read_prepared(output, manifest, repo)
            return prepared
        process_record, completed, preflight_sha = _run_process(paths["runner"], stage1_input, repo, root, "preflight_only", timeout=900)
        immutable_write(output / "preflight-process-diagnostic.json", process_record)
        require(
            process_record.get("status") == "completed"
            and completed is not None
            and completed.returncode == 0,
            "confirmation_preflight_process_failed",
        )
        preflight = strict_json(completed.stdout)
        require(
            _preflight_output_matches(
                preflight,
                manifest,
                expected_identity,
                calls_present=(output / "calls.jsonl").exists(),
            ),
            "confirmation_preflight_output_mismatch",
        )
        prepared = {
            "schema_version": 1,
            "kind": "native_tenki_placement_confirmation_prepared",
            "scope": SCOPE,
            "context": manifest["context"],
            "prepared": True,
            "execution_ready": True,
            "native_calls": 0,
            "planned_calls": LIMIT,
            "first_stage_request_sha256": manifest["stage1_request_sha256"],
            "preflight_diagnostic_sha256": preflight_sha,
            "manifest_sha256": _sha(_safe_file(manifest_path).read_bytes()),
            "stage1_input_sha256": _sha(_safe_file(stage1_input).read_bytes()),
            "diagnostics": ["historical_ledgers_read_only_verified", "dual_asset_identity_bound", "preflight_passed"],
            **FLAGS,
        }
        validate_report(prepared, repo)
        immutable_write(previous, prepared)
        require(stable_source(repo) == source_before, "workspace_changed_after_confirmation_prepare")
        return prepared

    prepared, prepared_hash = _read_prepared(output, manifest, repo)
    require(prepared.get("execution_ready") is True, "confirmation_prepared_not_execution_ready")
    require(stable_source(repo) == source_before, "workspace_changed_before_confirmation_run")
    _verify_saved_build_inputs(root, manifest, paths["runner"])
    frozen_files = {
        paths["runner"]: input_sha256["runner"],
        paths["worker"]: input_sha256["worker"],
        cli: input_sha256["cli"],
        paths["build_record"]: input_sha256["build_record"],
        paths["identity"]: input_sha256["identity"],
        paths["window_start"]: input_sha256["window_start"],
        root / "source-native.zip": input_sha256["source_archive"],
        root / "source-native-file-list.json": input_sha256["source_file_list"],
        configs["ordinary"]: input_sha256["ordinary_config"],
        configs["tournament"]: input_sha256["tournament_config"],
        banlist_path: input_sha256["banlist"],
        repo / PROMPT_BASELINE_RELATIVE / "research/stage-1.json": input_sha256["prompt_source_stage1"],
        repo / PROMPT_BASELINE_RELATIVE / "research/stage-2-request.json": input_sha256["prompt_source_stage2_request"],
        repo / "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json": preparation_hash,
        history_path: input_sha256["history_audit"],
    }
    return _run_six_stages(
        root=root, output=output, runner=paths["runner"], repo=repo, manifest=manifest,
        prepared_hash=prepared_hash, stage1_request=request, expected_identity=expected_identity,
        source=source_before, protected=protected, frozen_files=frozen_files,
    )
