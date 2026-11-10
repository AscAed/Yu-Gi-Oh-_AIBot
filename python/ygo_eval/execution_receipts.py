"""Offline verifier for the synthetic W1-C execution receipt contract v1.

This module verifies a supplied record. It does not observe or launch workers,
call ocgcore, create receipts, or authenticate the identity of a producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ygo_data.identity import regular_file


_HEX_32 = re.compile(r"^[a-f0-9]{32}$")
_HEX_64 = re.compile(r"^[a-f0-9]{64}$")
_ZERO_HASH = "0" * 64
_MAX_RECORD_BYTES = 64 * 1024 * 1024
_EVENT_TYPES = {
    "adapter_attempt",
    "worker_spawn",
    "protocol_request",
    "protocol_response",
    "ffi_entered",
    "ffi_returned",
    "report_persisted",
}


class ReceiptValidationError(ValueError):
    """Raised when the receipt cannot be verified against contract v1."""


def canonical(value: Any) -> bytes:
    """Return the contract's canonical UTF-8 JSON representation."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReceiptValidationError("non_canonical_json_value") from exc


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def context_digest(context: Dict[str, Any]) -> str:
    """Hash receipt context for event binding; this is not a signature."""
    return sha256(canonical(context))


def event_digest(context_sha256: str, event: Dict[str, Any]) -> str:
    """Hash one event without its event_sha256 field."""
    body = {key: value for key, value in event.items() if key != "event_sha256"}
    body["context_sha256"] = context_sha256
    return sha256(canonical(body))


def _require(condition: bool, diagnostic: str) -> None:
    if not condition:
        raise ReceiptValidationError(diagnostic)


def _enum(value: Any, allowed: set[str], diagnostic: str) -> str:
    _require(isinstance(value, str) and value in allowed, diagnostic)
    return value


def _exact_object(value: Any, keys: set[str], diagnostic: str) -> Dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == keys, diagnostic)
    return value


def _hash(value: Any, diagnostic: str) -> str:
    _require(isinstance(value, str) and _HEX_64.fullmatch(value) is not None, diagnostic)
    return value


def _id(value: Any, diagnostic: str) -> str:
    _require(isinstance(value, str) and _HEX_32.fullmatch(value) is not None, diagnostic)
    return value


def _json_integer(value: Any, diagnostic: str) -> int:
    is_json_integer = type(value) is int or (
        type(value) is float and math.isfinite(value) and value.is_integer()
    )
    _require(is_json_integer, diagnostic)
    return int(value)


def _integer(value: Any, diagnostic: str, minimum: int = 0) -> int:
    integer = _json_integer(value, diagnostic)
    _require(integer >= minimum, diagnostic)
    return integer


def _signed_integer(value: Any, diagnostic: str) -> int:
    return _json_integer(value, diagnostic)


def _unique_object(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptValidationError("duplicate_json_object_key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ReceiptValidationError("non_finite_json_number")


def _parse_json(raw: bytes, diagnostic: str) -> Any:
    _require(len(raw) <= _MAX_RECORD_BYTES, "record_too_large")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ReceiptValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptValidationError(diagnostic) from exc


def _validate_context(value: Any) -> Dict[str, Any]:
    context = _exact_object(
        value,
        {
            "operation_id",
            "job_id",
            "input_sha256",
            "source_bundle_identity",
            "build_record_identity",
            "assets",
        },
        "context_shape_invalid",
    )
    _id(context["operation_id"], "operation_id_invalid")
    _id(context["job_id"], "job_id_invalid")
    for key in ("input_sha256", "source_bundle_identity", "build_record_identity"):
        _hash(context[key], f"{key}_invalid")
    assets = context["assets"]
    _require(isinstance(assets, dict) and {"cli", "worker", "engine"}.issubset(assets), "asset_roles_missing")
    for role, value in assets.items():
        _require(
            isinstance(role, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", role) is not None,
            "asset_role_invalid",
        )
        _hash(value, "asset_hash_invalid")
    return context


def _validate_payload(event_type: str, payload: Any) -> Dict[str, Any]:
    shapes = {
        "adapter_attempt": {"command_sha256", "status"},
        "worker_spawn": {"status", "pid", "executable_sha256"},
        "protocol_request": {"status", "request_sha256", "bytes", "input_sha256"},
        "protocol_response": {"status", "response_sha256", "bytes", "exit_code", "observation", "ffi_receipt_status"},
        "ffi_entered": {"call_id", "direction", "name", "ordinal"},
        "ffi_returned": {"call_id", "status", "result_sha256"},
        "report_persisted": {"status", "report_sha256", "report_bytes", "readback_sha256"},
    }
    payload = _exact_object(payload, shapes[event_type], f"{event_type}_payload_invalid")

    if event_type == "adapter_attempt":
        _hash(payload["command_sha256"], "command_sha256_invalid")
        _require(payload["status"] == "started", "adapter_attempt_status_invalid")
    elif event_type == "worker_spawn":
        _enum(payload["status"], {"spawned", "failed"}, "worker_spawn_status_invalid")
        if payload["status"] == "spawned":
            _integer(payload["pid"], "worker_pid_invalid", 1)
            _hash(payload["executable_sha256"], "worker_executable_hash_invalid")
        else:
            _require(payload["pid"] is None and payload["executable_sha256"] is None, "failed_spawn_has_process")
    elif event_type == "protocol_request":
        _enum(payload["status"], {"written", "failed", "unknown"}, "protocol_request_status_invalid")
        if payload["status"] == "written":
            _hash(payload["request_sha256"], "request_sha256_invalid")
            _integer(payload["bytes"], "request_bytes_invalid", 1)
        else:
            _require(payload["request_sha256"] is None and payload["bytes"] is None, "unwritten_request_has_digest")
    elif event_type == "protocol_response":
        _enum(payload["status"], {"received", "missing", "invalid", "unknown"}, "protocol_response_status_invalid")
        _enum(
            payload["observation"],
            {"complete", "worker_exit", "timeout", "read_error", "parse_error", "unknown"},
            "protocol_response_observation_invalid",
        )
        _enum(payload["ffi_receipt_status"], {"complete", "partial", "unknown"}, "ffi_receipt_status_invalid")
        if payload["status"] in {"received", "invalid"}:
            _hash(payload["response_sha256"], "response_sha256_invalid")
            _integer(payload["bytes"], "response_bytes_invalid", 1)
            if payload["exit_code"] is not None:
                _signed_integer(payload["exit_code"], "worker_exit_code_invalid")
        elif payload["status"] == "missing":
            _require(payload["response_sha256"] is None and payload["bytes"] is None, "missing_response_has_digest")
            if payload["exit_code"] is not None:
                _signed_integer(payload["exit_code"], "worker_exit_code_invalid")
        else:
            _require(
                payload["response_sha256"] is None and payload["bytes"] is None and payload["exit_code"] is None,
                "unknown_response_has_observation",
            )
        expected_observations = {
            "received": {"complete"},
            "missing": {"worker_exit", "timeout", "read_error", "unknown"},
            "invalid": {"parse_error"},
            "unknown": {"unknown"},
        }
        _require(payload["observation"] in expected_observations[payload["status"]], "protocol_response_observation_mismatch")
    elif event_type == "ffi_entered":
        _id(payload["call_id"], "ffi_call_id_invalid")
        _enum(payload["direction"], {"host_to_ocgcore", "ocgcore_callback_to_host"}, "ffi_direction_invalid")
        _require(isinstance(payload["name"], str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", payload["name"]) is not None, "ffi_name_invalid")
        _integer(payload["ordinal"], "ffi_ordinal_invalid", 1)
    elif event_type == "ffi_returned":
        _id(payload["call_id"], "ffi_call_id_invalid")
        _enum(payload["status"], {"returned", "error"}, "ffi_return_status_invalid")
        if payload["result_sha256"] is not None:
            _hash(payload["result_sha256"], "ffi_result_sha256_invalid")
    elif event_type == "report_persisted":
        _enum(payload["status"], {"committed", "failed", "unknown"}, "report_persistence_status_invalid")
        if payload["status"] == "committed":
            _hash(payload["report_sha256"], "report_sha256_invalid")
            _integer(payload["report_bytes"], "report_bytes_invalid", 1)
            _require(payload["readback_sha256"] == payload["report_sha256"], "report_readback_hash_mismatch")
        elif payload["status"] == "failed":
            _require(
                payload["report_sha256"] is None and payload["report_bytes"] is None and payload["readback_sha256"] is None,
                "failed_report_has_material",
            )
        else:
            if payload["report_sha256"] is not None:
                _hash(payload["report_sha256"], "report_sha256_invalid")
            if payload["report_bytes"] is not None:
                _integer(payload["report_bytes"], "report_bytes_invalid", 1)
            _require(payload["readback_sha256"] is None, "uncertain_report_has_readback")
    return payload


def verify_receipt_chain(
    receipt: Any,
    report_bytes: Optional[bytes] = None,
    expected_head_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify schema-level invariants and the event hash chain.

    The result distinguishes an internally consistent record from producer
    authentication. This v1 verifier always reports
    ``report_origin_authenticated=False``.
    """
    receipt = _exact_object(
        receipt,
        {"schema_version", "kind", "context", "context_sha256", "events", "consumption"},
        "receipt_shape_invalid",
    )
    _require(_integer(receipt["schema_version"], "schema_version_unsupported") == 1, "schema_version_unsupported")
    _require(receipt["kind"] == "w1c_execution_receipt_chain", "receipt_kind_invalid")
    _require(report_bytes is None or len(report_bytes) <= _MAX_RECORD_BYTES, "report_record_too_large")
    context = _validate_context(receipt["context"])
    context_hash = _hash(receipt["context_sha256"], "context_sha256_invalid")
    _require(context_hash == context_digest(context), "context_digest_mismatch")

    consumption = _exact_object(receipt["consumption"], {"status", "unit", "count", "evidence_sha256"}, "consumption_shape_invalid")
    _require(
        consumption == {"status": "unknown", "unit": None, "count": None, "evidence_sha256": None},
        "consumption_must_remain_unknown",
    )

    if expected_head_sha256 is not None:
        _hash(expected_head_sha256, "expected_head_sha256_invalid")

    events = receipt["events"]
    _require(isinstance(events, list) and 1 <= len(events) <= 10000, "events_invalid")
    previous = _ZERO_HASH
    attempts: List[Dict[str, Any]] = []
    attempts_by_id: Dict[str, Dict[str, Any]] = {}
    active_attempt_id: Optional[str] = None
    seen_call_ids: set[str] = set()
    report_event: Optional[Dict[str, Any]] = None
    saw_report_event = False
    counts = {
        "adapter_attempts": 0,
        "worker_processes_observed": 0,
        "worker_spawn_failures": 0,
        "protocol_requests_written": 0,
        "protocol_responses_received": 0,
        "ffi_entries_observed": 0,
        "ffi_returns_observed": 0,
    }

    for index, raw_event in enumerate(events, start=1):
        event = _exact_object(
            raw_event,
            {"sequence", "attempt_id", "event_type", "previous_sha256", "payload", "event_sha256"},
            "event_shape_invalid",
        )
        _require(_integer(event["sequence"], "event_sequence_invalid", 1) == index, "event_sequence_not_contiguous")
        current_attempt = _id(event["attempt_id"], "attempt_id_invalid")
        event_type = _enum(event["event_type"], _EVENT_TYPES, "event_type_invalid")
        _require(_hash(event["previous_sha256"], "event_previous_sha256_invalid") == previous, "event_chain_predecessor_mismatch")
        observed_hash = _hash(event["event_sha256"], "event_sha256_invalid")
        _require(observed_hash == event_digest(context_hash, event), "event_sha256_mismatch")
        payload = _validate_payload(event_type, event["payload"])

        if event_type == "adapter_attempt":
            _require(not saw_report_event, "event_after_report")
            if index == 1:
                _require(event_type == "adapter_attempt", "adapter_attempt_must_start_chain")
            if active_attempt_id is not None:
                previous_attempt = attempts_by_id[active_attempt_id]
                _require(
                    previous_attempt["spawn_status"] == "spawned"
                    and previous_attempt["request_status"] == "written"
                    and previous_attempt["response_status"] == "received",
                    "attempt_after_incomplete_outcome",
                )
            _require(current_attempt not in attempts_by_id, "attempt_id_reused")
            state: Dict[str, Any] = {
                "attempt_id": current_attempt,
                "spawn_status": None,
                "request_status": None,
                "response_status": None,
                "ffi_receipt_status": None,
                "ffi_calls": {},
                "ffi_ordinals": [],
                "ffi_stack": [],
                "saw_protocol_request": False,
                "saw_protocol_response": False,
            }
            attempts.append(state)
            attempts_by_id[current_attempt] = state
            active_attempt_id = current_attempt
            counts["adapter_attempts"] += 1
        else:
            _require(not saw_report_event, "event_after_report")
            _require(
                current_attempt == active_attempt_id and current_attempt in attempts_by_id,
                "event_attempt_mismatch",
            )

        state = attempts_by_id[current_attempt]
        if event_type == "worker_spawn":
            _require(state["spawn_status"] is None, "worker_spawn_order_invalid")
            state["spawn_status"] = payload["status"]
            if state["spawn_status"] == "spawned":
                _require(payload["executable_sha256"] == context["assets"]["worker"], "spawned_worker_identity_mismatch")
                counts["worker_processes_observed"] += 1
            else:
                counts["worker_spawn_failures"] += 1
        elif event_type == "protocol_request":
            _require(
                state["spawn_status"] == "spawned" and not state["saw_protocol_request"],
                "protocol_request_order_invalid",
            )
            _require(payload["input_sha256"] == context["input_sha256"], "protocol_request_input_binding_mismatch")
            state["saw_protocol_request"] = True
            state["request_status"] = payload["status"]
            if state["request_status"] == "written":
                counts["protocol_requests_written"] += 1
        elif event_type == "protocol_response":
            _require(
                state["spawn_status"] == "spawned"
                and state["saw_protocol_request"]
                and not state["saw_protocol_response"],
                "protocol_response_order_invalid",
            )
            state["saw_protocol_response"] = True
            state["response_status"] = payload["status"]
            state["ffi_receipt_status"] = payload["ffi_receipt_status"]
            if state["response_status"] == "received":
                _require(state["request_status"] == "written", "response_without_written_request")
                counts["protocol_responses_received"] += 1
        elif event_type == "ffi_entered":
            _require(
                state["spawn_status"] == "spawned"
                and state["request_status"] == "written"
                and not state["saw_protocol_response"],
                "ffi_entry_order_invalid",
            )
            call_id = payload["call_id"]
            _require(call_id not in seen_call_ids, "duplicate_ffi_call_id")
            seen_call_ids.add(call_id)
            state["ffi_calls"][call_id] = {"returned": False}
            state["ffi_ordinals"].append(payload["ordinal"])
            state["ffi_stack"].append(call_id)
            counts["ffi_entries_observed"] += 1
        elif event_type == "ffi_returned":
            _require(not state["saw_protocol_response"], "ffi_return_after_protocol_response")
            call_id = payload["call_id"]
            _require(
                call_id in state["ffi_calls"] and not state["ffi_calls"][call_id]["returned"],
                "ffi_return_without_unique_entry",
            )
            _require(
                state["ffi_stack"] and state["ffi_stack"][-1] == call_id,
                "ffi_return_order_invalid",
            )
            state["ffi_calls"][call_id]["returned"] = True
            state["ffi_stack"].pop()
            counts["ffi_returns_observed"] += 1
        elif event_type == "report_persisted":
            _require(
                state["saw_protocol_response"] and not saw_report_event,
                "report_persistence_order_invalid",
            )
            saw_report_event = True
            report_event = payload
            _require(index == len(events), "report_event_must_be_terminal")

        previous = observed_hash

    _require(attempts, "adapter_attempt_missing")
    summaries: List[Dict[str, Any]] = []
    outstanding_ffi = 0
    all_ffi_receipts_complete = True
    any_ffi_receipt_observed = False
    all_attempts_complete = True
    total_ffi_calls = 0
    for state in attempts:
        ffi_ordinals = state["ffi_ordinals"]
        _require(ffi_ordinals == list(range(1, len(ffi_ordinals) + 1)), "ffi_ordinals_not_contiguous")
        attempt_outstanding = sum(not call["returned"] for call in state["ffi_calls"].values())
        outstanding_ffi += attempt_outstanding
        if state["saw_protocol_response"] and state["ffi_receipt_status"] == "complete":
            _require(attempt_outstanding == 0, "complete_ffi_stream_has_unreturned_call")
        ffi_complete = state["ffi_receipt_status"] == "complete" and attempt_outstanding == 0
        all_ffi_receipts_complete = all_ffi_receipts_complete and ffi_complete
        any_ffi_receipt_observed = any_ffi_receipt_observed or state["ffi_receipt_status"] in {"complete", "partial"}
        all_attempts_complete = all_attempts_complete and bool(
            state["spawn_status"] == "spawned"
            and state["request_status"] == "written"
            and state["response_status"] == "received"
            and ffi_complete
        )
        if ffi_complete:
            total_ffi_calls += len(state["ffi_calls"])
        summaries.append(
            {
                "attempt_id": state["attempt_id"],
                "worker_spawn_status": state["spawn_status"] or "unknown",
                "protocol_request_status": state["request_status"] or "unknown",
                "protocol_response_status": state["response_status"] or "unknown",
                "ffi_receipt_status": state["ffi_receipt_status"] or "unknown",
                "ffi_total_count": len(state["ffi_calls"]) if ffi_complete else None,
                "observed_ffi_entries_without_return": attempt_outstanding,
            }
        )

    head_hash = previous
    head_anchor_verified = expected_head_sha256 is not None and head_hash == expected_head_sha256
    if expected_head_sha256 is not None:
        _require(head_anchor_verified, "expected_head_sha256_mismatch")

    report_bytes_verified: Optional[bool] = None
    report_binding_verified: Optional[bool] = None
    if report_event and report_event["status"] == "committed" and report_bytes is not None:
        _require(len(report_bytes) == report_event["report_bytes"], "report_material_size_mismatch")
        _require(sha256(report_bytes) == report_event["report_sha256"], "report_material_sha256_mismatch")
        report = _parse_json(report_bytes, "report_json_invalid")
        _require(isinstance(report, dict), "report_json_object_required")
        for key, context_key in (("operation_id", "operation_id"), ("job_id", "job_id"), ("input_sha256", "input_sha256")):
            _require(report.get(key) == context[context_key], f"report_{key}_binding_mismatch")
        report_bytes_verified = True
        report_binding_verified = True

    complete = bool(
        all_attempts_complete
        and report_event is not None
        and report_event["status"] == "committed"
        and report_bytes_verified is True
        and report_binding_verified is True
    )
    return {
        "valid": True,
        "status": "complete" if complete else "incomplete",
        "context_sha256": context_hash,
        "head_sha256": head_hash,
        "head_anchor_verified": head_anchor_verified,
        "counts": counts,
        "attempts": summaries,
        "ffi_total_count": total_ffi_calls if all_ffi_receipts_complete else None,
        "observed_ffi_entries_without_return": outstanding_ffi,
        "ffi_receipt_status": (
            "complete"
            if all_ffi_receipts_complete
            else "partial"
            if any_ffi_receipt_observed
            else "unknown"
        ),
        "report_persistence_status": report_event["status"] if report_event else "unknown",
        "report_bytes_verified": report_bytes_verified,
        "report_binding_verified": report_binding_verified,
        "report_origin_authenticated": False,
        "consumption": {"status": "unknown", "unit": None, "count": None},
    }


def verify_files(
    receipt_path: str | Path,
    report_path: Optional[str | Path] = None,
    expected_head_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    receipt_file = regular_file(receipt_path)
    with receipt_file.open("rb") as stream:
        receipt_raw = stream.read(_MAX_RECORD_BYTES + 1)
    receipt = _parse_json(receipt_raw, "receipt_json_invalid")
    report_raw = None
    if report_path is not None:
        report_file = regular_file(report_path)
        with report_file.open("rb") as stream:
            report_raw = stream.read(_MAX_RECORD_BYTES + 1)
        _require(len(report_raw) <= _MAX_RECORD_BYTES, "record_too_large")
    return verify_receipt_chain(receipt, report_raw, expected_head_sha256)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="verify a W1-C receipt chain offline")
    verify.add_argument("--input", required=True, help="receipt JSON path")
    verify.add_argument("--report", help="persisted report bytes to bind, when available")
    verify.add_argument("--expected-head-sha256", help="externally pinned event-chain head digest")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            raw = sys.stdin.buffer.read(_MAX_RECORD_BYTES + 1)
            receipt = _parse_json(raw, "receipt_json_invalid")
            report_raw = None
            if args.report is not None:
                report_file = regular_file(args.report)
                with report_file.open("rb") as stream:
                    report_raw = stream.read(_MAX_RECORD_BYTES + 1)
                _require(len(report_raw) <= _MAX_RECORD_BYTES, "record_too_large")
            result = verify_receipt_chain(receipt, report_raw, args.expected_head_sha256)
        else:
            result = verify_files(args.input, args.report, args.expected_head_sha256)
    except (OSError, ReceiptValidationError, ValueError) as exc:
        print(json.dumps({"valid": False, "diagnostic": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
