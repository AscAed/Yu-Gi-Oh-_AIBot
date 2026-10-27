"""Independent synthetic writer for the frozen nine-call history ledger.

This module deliberately uses only the standard library. It is test support,
not a production ledger implementation, and writes its bytes only to the
caller-provided ignored test directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


_CALL_PROFILE = (
    ("rabbit", "execution"),
    ("rabbit", "replay"),
    ("phantom", "execution"),
    ("phantom", "replay"),
    ("tournament", "execution"),
    ("tournament", "replay"),
    ("tournament", "execution"),
    ("tournament", "execution"),
    ("tournament", "replay"),
)


@dataclass(frozen=True)
class SyntheticFirstBatchLedger:
    ledger_path: Path
    blob_root: Path
    requests: dict[str, dict[str, Any]]
    call_requests: tuple[dict[str, Any], ...]
    unpaired_followup_error: dict[str, str]
    authorized_window: dict[str, Any]

    def read_blob(self, folder: str, address: str) -> bytes:
        if folder not in {"results", "events", "checkpoints"}:
            raise ValueError("unsupported_blob_folder")
        if len(address) != 64 or any(char not in "0123456789abcdef" for char in address):
            raise ValueError("invalid_blob_address")
        return (self.blob_root / folder / f"{address}.json").read_bytes()


def _wire(value: Any, *, sort_keys: bool = False) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _request(case_id: str) -> dict[str, Any]:
    # The shape and field order below are handwritten to match the sealed
    # request contract; no production request encoder is imported.
    return {
        "protocol_version": 2,
        "engine": {
            "worker_path": f"synthetic/{case_id}/worker.exe",
            "ocgcore_path": f"synthetic/{case_id}/core.dll",
            "catalog_path": f"synthetic/{case_id}/cards.cdb",
            "scripts_path": f"synthetic/{case_id}/scripts",
            "script_manifest_path": f"synthetic/{case_id}/scripts.json",
            "engine_manifest_path": f"synthetic/{case_id}/engine.json",
            "timeout_ms": 30_000,
        },
        "deck": {"main": [], "extra": [], "side": []},
        "opening_hand": [],
        "seed": {"rabbit": 1, "phantom": 2, "tournament": 3}[case_id],
        "decisions": [],
        "versions": {
            "rules": "synthetic-rules-v1",
            "catalog": "synthetic-catalog-v1",
            "banlist": "synthetic-banlist-v1",
            "engine_sha256": "a" * 64,
            "cdb_sha256": "b" * 64,
            "scripts_sha256": "c" * 64,
            "core_commit": "synthetic-core",
            "initializer": "synthetic-initializer",
        },
        "probe_only": False,
    }


def _ordered_request(value: dict[str, Any]) -> dict[str, Any]:
    # Explicit projection rather than importing history_audit.ordered_request.
    return {
        "protocol_version": value["protocol_version"],
        "engine": {
            "worker_path": value["engine"]["worker_path"],
            "ocgcore_path": value["engine"]["ocgcore_path"],
            "catalog_path": value["engine"]["catalog_path"],
            "scripts_path": value["engine"]["scripts_path"],
            "script_manifest_path": value["engine"]["script_manifest_path"],
            "engine_manifest_path": value["engine"]["engine_manifest_path"],
            "timeout_ms": value["engine"]["timeout_ms"],
        },
        "deck": {
            "main": list(value["deck"]["main"]),
            "extra": list(value["deck"]["extra"]),
            "side": list(value["deck"]["side"]),
        },
        "opening_hand": list(value["opening_hand"]),
        "seed": value["seed"],
        "decisions": [],
        "versions": {
            "rules": value["versions"]["rules"],
            "catalog": value["versions"]["catalog"],
            "banlist": value["versions"]["banlist"],
            "engine_sha256": value["versions"]["engine_sha256"],
            "cdb_sha256": value["versions"]["cdb_sha256"],
            "scripts_sha256": value["versions"]["scripts_sha256"],
            "core_commit": value["versions"]["core_commit"],
            "initializer": value["versions"]["initializer"],
        },
        "probe_only": value["probe_only"],
    }


def _request_address(value: dict[str, Any]) -> str:
    identity = copy.deepcopy(value)
    identity.pop("engine")
    return _sha(_wire(identity, sort_keys=True))


def _result(request: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": 2,
        "status": "engine_verified",
        "events": [event],
        "prompt": None,
        "checkpoint": {
            "turn": 1,
            "turn_player": 0,
            "phase": 512,
            "lp": [8000, 8000],
            "cards": [],
        },
        "error": None,
        "versions": {
            "rules": request["versions"]["rules"],
            "catalog": request["versions"]["catalog"],
            "banlist": request["versions"]["banlist"],
            "engine_sha256": request["versions"]["engine_sha256"],
            "cdb_sha256": request["versions"]["cdb_sha256"],
            "scripts_sha256": request["versions"]["scripts_sha256"],
            "core_commit": request["versions"]["core_commit"],
            "initializer": request["versions"]["initializer"],
        },
        "loaded_scripts": {},
        "steps": [],
        "resolved_decisions": [],
        "coverage_gaps": [],
        "peak_working_set_bytes": 1024,
    }


def _stats(call_state: dict[int, dict[str, Any]]) -> dict[str, int]:
    complete = sum(item["completed"] for item in call_state.values())
    count = len(call_state)
    return {
        "consumed": count,
        "completed": complete,
        "unknown": count - complete,
        "reserved": 0,
        "abandoned": 0,
        "limit": 4096,
    }


def _charged_sequence(call_state: dict[int, dict[str, Any]]) -> str:
    prefix = [
        [number, item["request"], item["purpose"], item.get("normalized_hash")]
        for number, item in call_state.items()
    ]
    return _sha(_wire(prefix))


def build_synthetic_first_batch_ledger(root: Path) -> SyntheticFirstBatchLedger:
    """Write a frozen nine-call, 37-record ledger under ``root``."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    blob_root = root / "calls.jsonl.blobs"
    for folder in ("checkpoints", "events", "recoveries", "results"):
        (blob_root / folder).mkdir(parents=True, exist_ok=True)

    requests = {case_id: _request(case_id) for case_id in ("rabbit", "phantom", "tournament")}
    blobs: dict[tuple[str, str], bytes] = {}

    def put_blob(folder: str, raw: bytes) -> str:
        address = _sha(raw)
        blobs[(folder, address)] = raw
        path = blob_root / folder / f"{address}.json"
        path.write_bytes(raw)
        return address

    entries: list[dict[str, Any]] = [
        {
            "kind": "header",
            "version": 1,
            "scope": "research-first-batch-v1",
            "context": "synthetic-research-context-v1",
            "limit": 4096,
        }
    ]
    calls: dict[int, dict[str, Any]] = {}
    debits: list[str] = []
    event = {
        "sequence": 1,
        "opcode": 40,
        "raw": [40, 0],
        "supported": True,
        "fields": {"player": 0},
    }
    event_address = put_blob("events", _wire([event]))

    def checkpoint(name: str, search: Any) -> None:
        prefix = _charged_sequence(calls)
        payload = {
            "budget": _stats(calls),
            "charged_sequence": prefix,
            "reservations": {},
            "search": search,
        }
        address = put_blob("checkpoints", _wire(payload))
        entries.append(
            {
                "kind": "checkpoint",
                "name": name,
                "blob": address,
                "consumed": len(calls),
                "charged_sequence": prefix,
            }
        )

    checkpoint("research/start", 1)
    for case_id in ("rabbit", "phantom", "tournament"):
        checkpoint(
            f"research/case/{case_id}",
            _sha(_wire(_ordered_request(requests[case_id]))),
        )
    checkpoint(
        "immutable/research/case/tournament",
        _sha(_wire(_ordered_request(requests["tournament"]))),
    )

    for call_id, (case_id, purpose) in enumerate(_CALL_PROFILE, start=1):
        # The seventh call's uncharged error is represented as test companion
        # metadata, not a fabricated charged begin/complete pair.
        if call_id == 8:
            checkpoint(
                "immutable/research/authorized-window/user-resume-20261019",
                {
                    "additional_calls": 2,
                    "base_consumed": 7,
                    "case_id": "tournament",
                    "id": "user-resume-20261019",
                    "started": 1_792_403_041,
                },
            )

        checkpoint(f"research/debit/{call_id - 1}", case_id)
        request = requests[case_id]
        request_hash = _request_address(request)
        entries.append(
            {
                "kind": "begin",
                "call_id": call_id,
                "request": request_hash,
                "purpose": purpose,
                "reservation": None,
            }
        )
        result = _result(request, event)
        stored_result = copy.deepcopy(result)
        stored_result["events"] = []
        result_address = put_blob(
            "results",
            _wire(
                {
                    "kind": "duel",
                    "result": stored_result,
                    "event_chunks": [event_address],
                }
            ),
        )
        raw_hash = _sha(_wire(result))
        normalized_result = copy.deepcopy(result)
        normalized_result["peak_working_set_bytes"] = None
        normalized_hash = _sha(_wire(normalized_result))
        entries.append(
            {
                "kind": "complete",
                "call_id": call_id,
                "result": result_address,
                "raw_hash": raw_hash,
                "normalized_hash": normalized_hash,
            }
        )
        calls[call_id] = {
            "request": request_hash,
            "purpose": purpose,
            "completed": True,
            "normalized_hash": normalized_hash,
        }

        # These three repeated bindings preserve the frozen record count while
        # exercising latest-checkpoint semantics after prior calls.
        if call_id in {1, 3, 5}:
            checkpoint(
                f"research/case/{case_id}",
                _sha(_wire(_ordered_request(request))),
            )

    raw_ledger = bytearray()
    previous = ""
    for index, entry in enumerate(entries):
        chain_hash = _sha(_wire([index, previous, entry]))
        row = {
            "sequence": index,
            "previous": previous,
            "entry": entry,
            "hash": chain_hash,
        }
        raw_ledger.extend(_wire(row))
        raw_ledger.extend(b"\n")
        previous = chain_hash

    ledger_path = root / "calls.jsonl"
    ledger_path.write_bytes(bytes(raw_ledger))
    return SyntheticFirstBatchLedger(
        ledger_path=ledger_path,
        blob_root=blob_root,
        requests=requests,
        call_requests=tuple(requests[case_id] for case_id, _ in _CALL_PROFILE),
        unpaired_followup_error={"code": "journal_checkpoint", "stage": "call_journal"},
        authorized_window={
            "base_consumed": 7,
            "additional_calls": 2,
            "request_slot": 8,
        },
    )
