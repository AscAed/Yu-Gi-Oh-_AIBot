"""Reusable inert fixtures for Ground Collapse source-chain tests.

This module builds the successful seven-stage Curry revalidation delivery
consumed by ``ground_collapse_preparation``.  It does not create or certify the
upstream V3 recovery/reservation tree: callers must supply those already-built
synthetic source descriptions.  No artifact produced here is executable.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import copy
import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

from ygo_data.identity import canonical
from ygo_eval import ground_collapse_preparation as ground
from ygo_eval import native_curry_option_validation as curry
from ygo_eval.native_tenki_placement_validation import _stage_invocation
from tests.test_native_curry_option_validation import (
    _idle_event,
    _option_event,
    _place_event,
    _receipt,
)


_SOURCE_HEAD = "8a6b2f6762131aebea6d8c0f5f61363d573f1b36"
_PROMPTS = (10, 11, 12)
_PURPOSES = {
    1: "probe", 2: "probe", 3: "probe", 4: "execution",
    5: "replay", 6: "execution", 7: "replay",
}
_DOC_PATHS = ("TASKS.md", "docs/INDEX.md", "docs/TESTING.md")
_INERT_ARTIFACTS = {
    "runner": ("curry-option-revalidation.exe", b"synthetic Curry runner; inert\n"),
    "cli": ("ygo-cli.exe", b"synthetic CLI; inert\n"),
    "worker": ("ygo-engine-worker.exe", b"synthetic worker; inert\n"),
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _wire(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8") + b"\n"


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _write_json(path: Path, value: Any) -> bytes:
    raw = canonical(value)
    _write(path, raw)
    return raw


def _signed_build(source: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
    unsigned = {
        "kind": "build_record",
        "status": "recorded",
        "reproducible_build_proven": False,
        "source_before": copy.deepcopy(source),
        "source_after": copy.deepcopy(source),
        "artifacts": dict(artifacts),
    }
    return {**unsigned, "identity": _sha(canonical(unsigned))}


def _source_bundle(root: Path, files: dict[str, bytes]) -> tuple[dict[str, Any], bytes, bytes]:
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    source = {"head": _SOURCE_HEAD, "files": hashes,
              "identity": _sha(canonical({"head": _SOURCE_HEAD, "files": hashes}))}
    listing = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": _SOURCE_HEAD,
        "source_identity": source["identity"],
        "file_count": len(files),
        "files": hashes,
    }
    list_raw = _pretty(listing)
    archive_path = root / "source-native.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    _write(root / "source-native-file-list.json", list_raw)
    return source, archive_path.read_bytes(), list_raw


def _stage_event_bundle(stage: int) -> tuple[dict[str, Any], ...]:
    """Use a compact inert engine result for the journal; receipts hold prompts."""
    return ({
        "sequence": 1,
        "opcode": 40,
        "raw": [40, 0],
        "supported": True,
        "fields": {"player": 0, "synthetic_stage": stage},
    },)


def _result_bytes(stage: int, request: dict[str, Any], events: tuple[dict[str, Any], ...]) -> tuple[bytes, str, str]:
    versions = copy.deepcopy(request.get("versions", {}))
    if not versions:
        versions = {
            "rules": "synthetic-rules-v1", "catalog": "synthetic-catalog-v1",
            "banlist": "synthetic-banlist-v1", "engine_sha256": "a" * 64,
            "cdb_sha256": "b" * 64, "scripts_sha256": "c" * 64,
            "core_commit": "synthetic-core", "initializer": "synthetic-initializer",
        }
    # Typed result field order mirrors the frozen Rust serde contract used by
    # the research journal. The stored blob chunks events separately.
    restored = {
        "protocol_version": 2,
        "status": "engine_verified",
        "events": [copy.deepcopy(item) for item in events],
        "prompt": None,
        "checkpoint": {"turn": 1, "turn_player": 0, "phase": 512,
                        "lp": [8000, 8000], "cards": []},
        "error": None,
        "versions": versions,
        "loaded_scripts": {},
        "steps": [],
        "resolved_decisions": [],
        "coverage_gaps": [],
        "peak_working_set_bytes": 4096,
    }
    event_raw = _wire(list(events))
    # Hash the full restored result. Only its in-memory metric changes in the
    # journal's normalized comparison copy.
    raw_hash = _sha(_wire(restored))
    normalized = copy.deepcopy(restored)
    normalized["peak_working_set_bytes"] = None
    normalized_hash = _sha(_wire(normalized))
    stored = copy.deepcopy(restored)
    stored["events"] = []
    return event_raw, raw_hash, normalized_hash


def _stats(consumed: int) -> dict[str, int]:
    return {"consumed": consumed, "completed": consumed, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 7}


def _sequence_id(calls: dict[int, dict[str, Any]]) -> str:
    return _sha(_wire([
        [call_id, item["request"], item["purpose"], item["normalized_hash"]]
        for call_id, item in calls.items()
    ]))


def _put_blob(root: Path, folder: str, raw: bytes) -> str:
    digest = _sha(raw)
    _write(root / "research" / "calls.jsonl.blobs" / folder / f"{digest}.json", raw)
    return digest


def _append_record(records: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    sequence = len(records)
    previous = records[-1]["hash"] if records else ""
    raw = _wire([sequence, previous, entry])
    records.append({"sequence": sequence, "previous": previous,
                    "entry": entry, "hash": _sha(raw)})


def _append_checkpoint(root: Path, records: list[dict[str, Any]], calls: dict[int, dict[str, Any]],
                       name: str, search: Any) -> None:
    consumed = len(calls)
    charged = _sequence_id(calls)
    payload = {"budget": _stats(consumed), "charged_sequence": charged,
               "reservations": {}, "search": search}
    blob = _put_blob(root, "checkpoints", _wire(payload))
    _append_record(records, {"kind": "checkpoint", "name": name,
                             "blob": blob, "consumed": consumed,
                             "charged_sequence": charged})


@dataclass(frozen=True, slots=True)
class SyntheticRevalidationDelivery:
    """Paths and authenticated fixture values written by the delivery builder."""

    repo: Path
    root: Path
    output: Path
    context: str
    spec: Any
    profile: Any
    requests: tuple[dict[str, Any], ...]
    receipts: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    ledger_path: Path
    ledger_sha256: str
    delivery_sha256: str
    native_identity: str
    final_identity: str


def build_synthetic_revalidation_delivery(
    repo: Path,
    root: Path,
    *,
    base_request: dict[str, Any],
    rabbit_case: dict[str, Any],
    candidate_case: dict[str, Any],
    worker_path: str = "synthetic/native-artifacts/ygo-engine-worker.exe",
    expected_identity: dict[str, Any] | None = None,
    context: str = "d" * 64,
    spec: Any | None = None,
    started_at: int = 1_798_300_000,
) -> SyntheticRevalidationDelivery:
    """Write a full inert successful seven-stage delivery under ``root``.

    All paths must be inside the caller's synthetic repository. The builder
    verifies every stage receipt with the real Python scope validator before
    publishing the summary. It intentionally does not certify any upstream
    recovery/reservation source chain.
    """
    repo = Path(repo).resolve()
    root = Path(root).resolve()
    if not root.is_relative_to(repo) or root == repo:
        raise ValueError("synthetic_revalidation_root_must_be_under_repo")
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("synthetic_revalidation_root_not_empty")
    spec = spec or curry.OPTION_REVALIDATION_SCOPE
    if spec.scope != curry.OPTION_REVALIDATION_SCOPE.scope:
        raise ValueError("synthetic_revalidation_fixed_scope_required")
    expected_identity = copy.deepcopy(expected_identity or {"identity": "b" * 64})
    context = context or ("d" * 64)
    if len(context) != 64 or any(ch not in "0123456789abcdef" for ch in context):
        raise ValueError("synthetic_revalidation_context_invalid")

    output = root / "research"
    output.mkdir(parents=True, exist_ok=True)
    (root / "native-artifacts").mkdir(parents=True, exist_ok=True)
    (root / "final-build" / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "final-build" / "source-final").mkdir(parents=True, exist_ok=True)
    for folder in ("events", "results", "checkpoints"):
        (output / "calls.jsonl.blobs" / folder).mkdir(parents=True, exist_ok=True)

    requests: dict[int, dict[str, Any]] = {
        1: curry.derive_curry_stage1_request(
            base_request, rabbit_case, candidate_case, worker_path,
        ),
    }
    receipts: dict[int, dict[str, Any]] = {}
    for stage in range(1, 8):
        if stage > 1:
            parent_stage = curry.PARENT_STAGE[stage]
            requests[stage] = curry.derive_curry_stage_request(
                stage, receipts[parent_stage], spec,
            )
        if stage == 2:
            events = [_idle_event(10), _place_event(11)]
            receipt = _receipt(stage, requests[stage], events=events,
                               pending=events[-1]["fields"]["prompt"])
        elif stage == 3:
            events = [_idle_event(10), _place_event(11), _option_event(12)]
            receipt = _receipt(stage, requests[stage], events=events,
                               pending=events[-1]["fields"]["prompt"])
        else:
            receipt = _receipt(stage, requests[stage])
        receipt.update({
            "kind": curry._report_kind(spec, "stage"),
            "scope": spec.scope,
            "context": context,
            "ledger": _stats(stage),
            "assets_before": expected_identity,
            "assets_after": copy.deepcopy(expected_identity),
            "assets_unchanged": True,
            "window_valid_at_result": True,
            "started_at": started_at,
            "result_at": started_at + stage,
        })
        curry.validate_curry_stage_receipt(
            receipt, requests[stage], context, stage, expected_identity, spec,
        )
        receipts[stage] = receipt

    # Build the authentic 37-row record layout: header + immutable start, then
    # three checkpoints and one begin/complete pair per stage.
    records: list[dict[str, Any]] = []
    _append_record(records, {"kind": "header", "version": 1,
                            "scope": spec.scope, "context": context, "limit": 7})
    calls: dict[int, dict[str, Any]] = {}
    _append_checkpoint(root, records, calls,
                       "immutable/curry-option-revalidation/start", started_at)
    stage_reports: list[dict[str, Any]] = []
    delivery_receipts: list[dict[str, Any]] = []
    for stage in range(1, 8):
        request = requests[stage]
        request_path = output / f"stage-{stage}-request.json"
        input_path = output / f"stage-{stage}-input.json"
        receipt_path = output / f"stage-{stage}.json"
        report_path = output / f"stage-{stage}-report.json"
        _write_json(request_path, request)
        invocation = _stage_invocation(
            context, output, stage, request, expected_identity, started_at, spec,
        )
        input_raw = canonical(invocation)
        _write(input_path, input_raw)
        _write_json(output / f"stage-{stage}-input-seal.json", {
            "schema_version": 1, "kind": spec.input_seal_kind,
            "context": context, "stage": stage,
            "input_sha256": _sha(input_raw),
        })

        _append_checkpoint(root, records, calls,
                           f"immutable/curry-option-revalidation/assets/{stage}",
                           expected_identity)
        _append_checkpoint(root, records, calls,
                           f"immutable/curry-option-revalidation/intent/{stage}",
                           {"stage": stage, "request": request})
        request_identity = copy.deepcopy(request)
        request_identity.pop("engine", None)
        request_sha = _sha(canonical(request_identity))
        _append_record(records, {"kind": "begin", "call_id": stage,
                                 "request": request_sha,
                                 "purpose": _PURPOSES[stage], "reservation": None})

        events = _stage_event_bundle(stage)
        event_sha = _put_blob(root, "events", _wire(list(events)))
        event_raw, raw_result_sha, normalized_sha = _result_bytes(
            stage, request, events,
        )
        # Use the same event bytes in the content-addressed event blob.
        if _sha(event_raw) != event_sha:
            raise AssertionError("synthetic_event_blob_identity_changed")
        stored_result = {
            "kind": "duel",
            "result": {
                "protocol_version": 2, "status": "engine_verified", "events": [],
                "prompt": None,
                "checkpoint": {"turn": 1, "turn_player": 0, "phase": 512,
                               "lp": [8000, 8000], "cards": []},
                "error": None,
                "versions": copy.deepcopy(request.get("versions", {})),
                "loaded_scripts": {}, "steps": [], "resolved_decisions": [],
                "coverage_gaps": [], "peak_working_set_bytes": 4096,
            },
            "event_chunks": [event_sha],
        }
        result_sha = _put_blob(root, "results", _wire(stored_result))
        _append_record(records, {
            "kind": "complete", "call_id": stage, "result": result_sha,
            "raw_hash": raw_result_sha, "normalized_hash": normalized_sha,
        })
        calls[stage] = {"request": request_sha, "purpose": _PURPOSES[stage],
                        "normalized_hash": normalized_sha}

        sequence_id = _sequence_id(calls)
        receipt = receipts[stage]
        receipt["charged_sequence_id"] = sequence_id
        receipt["consumed_prefix"] = stage
        _write_json(receipt_path, receipt)
        diag_sha = _sha(f"synthetic revalidation stage {stage} process diagnostic\n".encode())
        report = curry._stage_report(
            context, stage, receipt, receipt_path, diag_sha, 1, None,
            spec=spec,
        )
        _write_json(report_path, report)
        stage_reports.append({key: report.get(key) for key in (
            "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
            "diagnostic_sha256", "independent_replay_matches", "ledger",
        )})
        delivery_receipts.append({"stage": stage, "successful": True,
                                  "receipt_sha256": _sha(receipt_path.read_bytes())})
        _append_checkpoint(root, records, calls,
                           f"immutable/curry-option-revalidation/evidence/{stage}",
                           {"receipt": receipt})

    ledger_path = output / "calls.jsonl"
    ledger_raw = b"".join(_wire(record) + b"\n" for record in records)
    _write(ledger_path, ledger_raw)
    stats = _stats(7)
    summary = curry.summarize_curry_validation(
        context, stage_reports, stats, spec=spec,
    )
    curry.validate_curry_report(summary, repo=repo, spec=spec)
    summary_raw = _write_json(output / "summary.json", summary)

    native_files = {
        **{name: f"native snapshot {name}\n".encode("utf-8") for name in _DOC_PATHS},
        **{f"synthetic/revalidation-{index:04d}.bin": b"inert native source member\n"
           for index in range(590)},
    }
    final_files = dict(native_files)
    for name in _DOC_PATHS:
        final_files[name] = f"final snapshot {name}\n".encode("utf-8")
    additions = sorted(set(ground.ALLOWED_SOURCE_DIFFS) - set(_DOC_PATHS))
    if len(additions) != 1:
        raise ValueError("synthetic_revalidation_expected_one_handoff_source_path")
    final_files[additions[0]] = b"synthetic revalidation handoff\n"
    if len(native_files) != 593 or len(final_files) != 594:
        raise AssertionError("synthetic_revalidation_source_count_invalid")
    native_source, native_archive, native_list = _source_bundle(root, native_files)
    final_source, final_archive, final_list = _source_bundle(
        root / "final-build" / "source-final", final_files,
    )
    # _source_bundle writes generic names; place the final pair at its pinned path.
    final_archive_path = root / "final-build" / "source-final" / "source-native.zip"
    final_list_path = root / "final-build" / "source-final" / "source-native-file-list.json"
    if final_archive_path.read_bytes() != final_archive or final_list_path.read_bytes() != final_list:
        raise AssertionError("synthetic_revalidation_final_archive_write_mismatch")

    native_artifacts: dict[str, str] = {}
    final_artifacts: dict[str, dict[str, Any]] = {}
    final_build_artifact_hashes: dict[str, str] = {}
    for role, (filename, contents) in _INERT_ARTIFACTS.items():
        native_path = root / "native-artifacts" / filename
        final_path = root / "final-build" / "artifacts" / filename
        _write(native_path, contents)
        _write(final_path, contents)
        digest = _sha(contents)
        native_artifacts[role] = digest
        final_artifacts[role] = {
            "path": f"artifacts/{filename}", "sha256": digest, "bytes": len(contents),
        }
        final_build_artifact_hashes[role] = digest

    native_record = _signed_build(native_source, native_artifacts)
    native_record_raw = _pretty(native_record)
    _write(root / "build-record.json", native_record_raw)
    cli_worker_record = _signed_build(
        final_source, {"cli": final_build_artifact_hashes["cli"],
                       "worker": final_build_artifact_hashes["worker"]},
    )
    cli_worker_raw = _pretty(cli_worker_record)
    _write(root / "final-build" / "build-record-cli-worker.json", cli_worker_raw)
    runner_record = _signed_build(final_source, {"runner": final_build_artifact_hashes["runner"]})
    runner_record_raw = _pretty(runner_record)
    _write(root / "final-build" / "build-record-runner.json", runner_record_raw)

    delivery = {
        "schema_version": 1,
        "kind": "native_curry_option_revalidation_final_delivery",
        "status": "passed",
        "scope": spec.scope,
        "accounting": {
            "actual_all_history_cumulative": None,
            "certified_consumed_including_new": 40,
            "certified_historical_consumed_before_scope": 33,
            "new_scope_consumed": 7,
            "old_confirmation_actual_consumed": None,
            "planning_base": 40,
            "planning_total": 47,
            "policy_reserved": 7,
            "reservation_id": spec.reservation_id,
            "reservation_policy_id": spec.reservation_policy_id,
        },
        "native_execution": {
            "native_calls": 7, "consumed": 7, "completed": 7,
            "unknown": 0,
        },
        "stage_receipts": delivery_receipts,
        "final_source": {
            "workspace_identity": final_source["identity"],
            "file_count": 594,
            "changed_paths_vs_native_source": list(ground.ALLOWED_SOURCE_DIFFS),
            "source_archive_sha256": _sha(final_archive),
            "source_file_list_sha256": _sha(final_list),
        },
        "final_build": {
            "build_record_cli_worker": {
                "path": "build-record-cli-worker.json",
                "sha256": _sha(cli_worker_raw),
                "identity": cli_worker_record["identity"],
            },
            "build_record_runner": {
                "path": "build-record-runner.json",
                "sha256": _sha(runner_record_raw),
                "identity": runner_record["identity"],
            },
            "artifacts": final_artifacts,
        },
        "original_call_journal": {
            "path": "../research/calls.jsonl",
            "sha256": _sha(ledger_raw),
            "records": 37,
            "bytes": len(ledger_raw),
            "record_kinds": {"begin": 7, "checkpoint": 22,
                             "complete": 7, "header": 1},
        },
    }
    delivery_raw = _write_json(root / "final-build" / "delivery-final.json", delivery)

    from ygo_eval.ground_collapse_preparation import PRODUCTION_PROFILE
    from dataclasses import replace as dataclass_replace

    profile = dataclass_replace(
        PRODUCTION_PROFILE,
        baseline_root=root.relative_to(repo),
        curry_delivery_sha256=_sha(delivery_raw),
        native_archive_sha256=_sha(native_archive),
        native_file_list_sha256=_sha(native_list),
        native_identity=native_source["identity"],
        final_archive_sha256=_sha(final_archive),
        final_file_list_sha256=_sha(final_list),
        final_identity=final_source["identity"],
        ledger_sha256=_sha(ledger_raw),
        summary_sha256=_sha(summary_raw),
        native_build_record_sha256=_sha(native_record_raw),
        native_build_record_identity=native_record["identity"],
        source_diff=tuple(ground.ALLOWED_SOURCE_DIFFS),
    )
    return SyntheticRevalidationDelivery(
        repo=repo, root=root, output=output, context=context, spec=spec,
        profile=profile, requests=tuple(requests[i] for i in range(1, 8)),
        receipts=tuple(receipts[i] for i in range(1, 8)),
        summary=summary, ledger_path=ledger_path,
        ledger_sha256=_sha(ledger_raw), delivery_sha256=_sha(delivery_raw),
        native_identity=native_source["identity"],
        final_identity=final_source["identity"],
    )


def make_ground_collapse_revalidation_source(
    *,
    scope_spec: Any,
    recovery_profile: Any,
    recovery_version_spec: Any,
    recovery_sources: Any,
    reservation_profile: Any,
    reservation_spec: Any,
    reservation_sources: Any,
    option_verification_spec: Any,
    candidate_spec: Any,
    recovery_delivery_workspace_identity: str,
    recovery_delivery_workspace_file_count: int,
):
    """Create the immutable descriptor from caller-authenticated source nodes.

    The helper intentionally requires the V3 source nodes rather than copying
    or substituting their validators. This keeps generated bytes and source
    policy separate.
    """
    if recovery_sources is None or reservation_sources is None:
        raise ValueError("synthetic_authenticated_v3_source_nodes_required")
    if (type(recovery_delivery_workspace_file_count) is not int
            or recovery_delivery_workspace_file_count < 1):
        raise ValueError("synthetic_recovery_workspace_count_invalid")
    from ygo_eval.ground_collapse_preparation import GroundCollapseRevalidationSource

    return GroundCollapseRevalidationSource(
        scope_spec=scope_spec,
        recovery_profile=recovery_profile,
        recovery_version_spec=recovery_version_spec,
        recovery_sources=recovery_sources,
        reservation_profile=reservation_profile,
        reservation_spec=reservation_spec,
        reservation_sources=reservation_sources,
        option_verification_spec=option_verification_spec,
        candidate_spec=candidate_spec,
        recovery_delivery_workspace_identity=recovery_delivery_workspace_identity,
        recovery_delivery_workspace_file_count=recovery_delivery_workspace_file_count,
    )


def compose_ground_collapse_source_components(
    handoff_tree: Any,
    *,
    recovery_profile: Any,
    recovery_version_spec: Any | None = None,
    scope_spec: Any | None = None,
) -> dict[str, Any]:
    """Compose the descriptor inputs from the existing synthetic V3 tree.

    ``handoff_tree`` is the ``SyntheticLedgerHandoffTree`` produced by
    ``build_synthetic_handoff_tree`` (or its V5-wrapped variant).  Its source
    node already contains the independent reservation and recovery children;
    this helper routes those authenticated nodes without replacing any
    verifier.  The saved-input recovery profile remains an explicit input
    because its V5 archive and source identity are created by the separate
    recovery fixture.
    """
    from dataclasses import replace as dataclass_replace
    from ygo_eval import curry_ledger_handoff_recovery as recovery

    from ygo_eval.native_curry_option_validation import (
        OPTION_REVALIDATION_SCOPE,
    )

    if not hasattr(handoff_tree, "sources") or not hasattr(handoff_tree, "repo"):
        raise TypeError("synthetic_curry_handoff_tree_required")
    try:
        # Resolve both fixed child nodes now. This fails early on an incomplete
        # fixture instead of silently passing a root with missing ancestry.
        handoff_tree.sources.child("reservation")
        handoff_tree.sources.child("baseline")
    except (AttributeError, KeyError, ValueError):
        raise ValueError("synthetic_curry_v3_source_nodes_incomplete") from None

    recovery_spec = recovery_version_spec or dataclass_replace(
        recovery.V3_SPEC, profile=recovery_profile,
    )
    if recovery_spec.profile != recovery_profile:
        raise ValueError("synthetic_recovery_profile_spec_mismatch")
    if getattr(handoff_tree, "reservation_profile", None) is None or getattr(
        handoff_tree, "reservation_spec", None
    ) is None:
        raise ValueError("synthetic_reservation_profile_missing")
    if getattr(handoff_tree, "option_spec", None) is None or getattr(
        handoff_tree, "candidate_spec", None
    ) is None:
        raise ValueError("synthetic_option_candidate_profile_missing")

    return {
        "scope_spec": scope_spec or OPTION_REVALIDATION_SCOPE,
        "recovery_profile": recovery_profile,
        "recovery_version_spec": recovery_spec,
        "recovery_sources": handoff_tree.sources,
        "reservation_profile": handoff_tree.reservation_profile,
        "reservation_spec": handoff_tree.reservation_spec,
        "reservation_sources": handoff_tree.sources,
        "option_verification_spec": handoff_tree.option_spec,
        "candidate_spec": handoff_tree.candidate_spec,
        "recovery_delivery_workspace_identity": (
            recovery_profile.delivery_source_after_docs_identity
        ),
        "recovery_delivery_workspace_file_count": (
            recovery_profile.delivery_source_after_docs_file_count
        ),
    }


def build_revalidation_source_bundle(
    repo: Path,
    baseline_root: Path,
    *,
    source_components: dict[str, Any],
    base_request: dict[str, Any],
    rabbit_case: dict[str, Any],
    candidate_case: dict[str, Any],
    worker_path: str = "synthetic/native-artifacts/ygo-engine-worker.exe",
    expected_identity: dict[str, Any] | None = None,
    context: str = "d" * 64,
):
    """Build delivery/profile and return a data-only Ground Collapse source.

    ``source_components`` must contain the frozen upstream V3 recovery,
    reservation, and candidate profile/spec/source nodes. No validator is
    accepted or replaced here.
    """
    needed = {
        "scope_spec", "recovery_profile", "recovery_version_spec", "recovery_sources",
        "reservation_profile", "reservation_spec", "reservation_sources",
        "option_verification_spec", "candidate_spec",
        "recovery_delivery_workspace_identity",
        "recovery_delivery_workspace_file_count",
    }
    if set(source_components) != needed:
        missing = sorted(needed - set(source_components))
        extra = sorted(set(source_components) - needed)
        raise ValueError(f"synthetic_revalidation_source_components_invalid:{missing}:{extra}")
    delivery = build_synthetic_revalidation_delivery(
        repo, baseline_root, base_request=base_request, rabbit_case=rabbit_case,
        candidate_case=candidate_case, worker_path=worker_path,
        expected_identity=expected_identity, context=context,
        spec=source_components["scope_spec"],
    )
    descriptor = make_ground_collapse_revalidation_source(**source_components)
    return descriptor, delivery.profile, delivery
