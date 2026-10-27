"""Public CLI success and read-only verification for Curry recovery.

Every artifact here is synthetic and inert. The test exercises the public
``research.main`` dispatch and the real recovery/audit validators, while
blocking OS process, FFI, and writable journal access.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from types import SimpleNamespace

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import curry_ledger_handoff_recovery as recovery
from ygo_eval import native_curry_option_validation as curry
from ygo_eval import research
from tests.support.curry_ledger_handoff_v3_e2e import (
    _write_build_record,
    _write_source_bundle,
)
from tests.support.curry_ledger_handoff_v5_e2e import (
    build_synthetic_handoff_v5_tree,
    write_synthetic_v5_runner,
)
from tests.support.curry_recovery_e2e import synthetic_source_identity
from tests.test_native_curry_option_validation import _idle_event


ROOT = Path(__file__).resolve().parents[1]
REAL_AUDIT_TO_OUTPUT = recovery.audit_to_output
SYNTHETIC_V4_WRONG_ADDED_PATH = (
    "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md"
)
SYNTHETIC_V5_ADDED_PATH = (
    "docs/superpowers/plans/2026-10-26-curry-ledger-handoff-v5-handoff.md"
)
SYNTHETIC_EVENTS = (("input_validation", "start"),
                    ("input_validation", "end"),
                    ("parent_request_check", "start"),
                    ("parent_request_check", "end"),
                    ("saved_input_asset_scan", "start"),
                    ("saved_input_asset_scan", "end"),
                    ("ledger_check", "start"),
                    ("ledger_check", "end"))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pretty(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8") + b"\n"


def _write(path: Path, value) -> bytes:
    raw = value if isinstance(value, bytes) else _pretty(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _write_tool_sources(
    repo: Path, tool_files: tuple[str, ...] = recovery.TOOL_FILES,
) -> None:
    for relative in tool_files:
        source = ROOT / relative
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _complete_protocol_result(receipt: dict, request: dict) -> dict:
    """Make the fixture's authenticated stage result ledger-complete."""
    result = receipt["result"]["Ok"]
    # The shared synthetic prompt fixture uses a historical prompt id greater
    # than one, while providing only the prompt frame itself. The frozen
    # ledger decoder requires a result's event frames to retain their original
    # contiguous 1-based sequence numbers, so supply inert, valid hint frames
    # that precede that prompt in this test-owned stream.
    events = result.get("events", [])
    if (len(events) == 1 and type(events[0].get("sequence")) is int
            and events[0]["sequence"] > 1):
        prompt_sequence = events[0]["sequence"]
        prefix = [
            {
                "sequence": sequence,
                "opcode": 2,
                "raw": [2, 0, 0, *([0] * 8)],
                "supported": True,
                "fields": {"hint_type": 0, "player": 0, "value": 0},
            }
            for sequence in range(1, prompt_sequence)
        ]
        result["events"] = [*prefix, events[0]]
    # The shared synthetic idle event predates the frozen-history format and
    # omits display labels. The ledger codec binds labels too, so add inert
    # deterministic fixture labels to both prompt copies before hashing.
    for event in result.get("events", []):
        prompt = event.get("fields", {}).get("prompt")
        if isinstance(prompt, dict):
            for index, action in enumerate(prompt.get("actions", [])):
                action.setdefault("label", f"synthetic action {index}")
    if isinstance(result.get("prompt"), dict):
        for index, action in enumerate(result["prompt"].get("actions", [])):
            action.setdefault("label", f"synthetic action {index}")
    result.update({
        "protocol_version": request["protocol_version"],
        # The saved request carries only the three asset digests; worker
        # results carry the full frozen engine-version record.
        "versions": {
            "rules": "synthetic-rules-v1",
            "catalog": "synthetic-catalog-v1",
            "banlist": "synthetic-banlist-v1",
            **copy.deepcopy(request["versions"]),
            "core_commit": "synthetic-core",
            "initializer": "synthetic-initializer",
        },
        "loaded_scripts": {},
        "peak_working_set_bytes": 4096,
        "checkpoint": {
            "turn": 1,
            "turn_player": 0,
            "phase": 512,
            "lp": [8000, 8000],
            "cards": [],
        },
    })
    return result


def _write_seven_record_scope_ledger(
    repo: Path, ledger_path: Path, manifest: dict, receipt: dict,
) -> bytes:
    """Write the actual seven-row recovery ledger shape from test-owned bytes."""
    from ygo_eval import history_audit as history

    blob_root = ledger_path.with_name(ledger_path.name + ".blobs")
    assert blob_root.resolve().is_relative_to(repo.resolve())
    if blob_root.exists():
        shutil.rmtree(blob_root)
    for kind in ("checkpoints", "results", "events", "recoveries"):
        (blob_root / kind).mkdir(parents=True, exist_ok=True)

    def put_blob(kind: str, value) -> str:
        raw = _encode(value)
        address = _sha(raw)
        (blob_root / kind / f"{address}.json").write_bytes(raw)
        return address

    protocol_result = copy.deepcopy(receipt["result"]["Ok"])
    events = copy.deepcopy(protocol_result["events"])
    event_hash = put_blob("events", events)
    stored_result = copy.deepcopy(protocol_result)
    stored_result["events"] = []
    result_hash = put_blob("results", {
        "kind": "duel", "result": stored_result,
        "event_chunks": [event_hash],
    })

    frozen_result = history.frozen_result(protocol_result)
    raw_result_hash = history.digest(history.encode(frozen_result))
    normalized = copy.deepcopy(frozen_result)
    normalized["peak_working_set_bytes"] = None
    normalized_hash = history.digest(history.encode(normalized))
    request_hash = history.request_digest(receipt["request"])
    calls = {
        1: {"request": request_hash, "purpose": "probe",
            "normalized_hash": normalized_hash},
    }
    final_sequence = history.sequence_id(calls)
    receipt["charged_sequence_id"] = final_sequence

    def checkpoint(name: str, consumed: int, search) -> dict:
        charged = history.digest(history.encode([])) if consumed == 0 else final_sequence
        payload = {
            "search": search,
            "budget": {
                "consumed": consumed, "reserved": 0, "completed": consumed,
                "unknown": 0, "abandoned": 0, "limit": 7,
            },
            "reservations": {},
            "charged_sequence": charged,
        }
        return {
            "kind": "checkpoint", "name": name,
            "blob": put_blob("checkpoints", payload),
            "consumed": consumed, "charged_sequence": charged,
        }

    checkpoint_prefix = "immutable/curry-option-verification/"
    entries = [
        {"kind": "header", "version": 1,
         "scope": "curry-option-verification-v1",
         "context": manifest["context"], "limit": 7},
        checkpoint(checkpoint_prefix + "start", 0, manifest["started_at"]),
        checkpoint(checkpoint_prefix + "assets/1", 0, receipt["assets_before"]),
        checkpoint(checkpoint_prefix + "intent/1", 0,
                   {"request": receipt["request"], "stage": 1}),
        {"kind": "begin", "call_id": 1, "request": request_hash,
         "purpose": "probe", "reservation": None},
        {"kind": "complete", "call_id": 1, "result": result_hash,
         "raw_hash": raw_result_hash, "normalized_hash": normalized_hash},
        checkpoint(checkpoint_prefix + "evidence/1", 1,
                   {"receipt": receipt}),
    ]

    rows = []
    previous = ""
    for sequence, entry in enumerate(entries):
        entry_order = {key: entry[key] for key in history.ENTRY_FIELDS[entry["kind"]]}
        row_hash = history.digest(history.encode([sequence, previous, entry_order]))
        rows.append({"sequence": sequence, "previous": previous,
                     "entry": entry_order, "hash": row_hash})
        previous = row_hash
    raw = b"".join(_encode(row) + b"\n" for row in rows)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_bytes(raw)
    return raw


def _upgrade_stage1_receipt(tree) -> bytes:
    research_root = tree.stage2_input_path.parent
    receipt_path = research_root / "stage-1.json"
    receipt = json.loads(receipt_path.read_bytes())
    manifest = json.loads((research_root / "manifest.json").read_bytes())
    request = manifest["request"]
    _complete_protocol_result(receipt, request)
    receipt_raw = _write(receipt_path, receipt)

    stage_report_path = research_root / "stage-1-report.json"
    stage_report = json.loads(stage_report_path.read_bytes())
    stage_report["receipt_sha256"] = _sha(receipt_raw)
    stage_report_raw = _write(stage_report_path, stage_report)
    summary_path = research_root / "summary.json"
    summary = json.loads(summary_path.read_bytes())
    if summary.get("stages"):
        summary["stages"][0]["receipt_sha256"] = _sha(receipt_raw)
        summary["stages"][0]["diagnostic_sha256"] = stage_report["diagnostic_sha256"]
    _write(summary_path, summary)
    ledger_raw = _write_seven_record_scope_ledger(
        tree.repo, tree.ledger_path, manifest, receipt,
    )
    # The ledger's final checkpoint binds the finalized receipt, including its
    # charged sequence. Re-publish those two synthetic stage references now.
    receipt_raw = _write(receipt_path, receipt)
    stage_report = json.loads(stage_report_path.read_bytes())
    stage_report["receipt_sha256"] = _sha(receipt_raw)
    _write(stage_report_path, stage_report)
    summary = json.loads(summary_path.read_bytes())
    if summary.get("stages"):
        summary["stages"][0]["receipt_sha256"] = _sha(receipt_raw)
    _write(summary_path, summary)
    # The final receipt hash is stable after its charged-sequence binding.
    assert json.loads(receipt_path.read_bytes()) == receipt
    assert json.loads(stage_report_path.read_bytes())["receipt_sha256"] == _sha(
        receipt_path.read_bytes()
    )
    return ledger_raw


def _saved_stdout(context: str, identity: str) -> bytes:
    return _encode({
        "saved_input_audit_passed": True,
        "native_calls": 0,
        "execution_ready": False,
        "stage": 2,
        "context": context,
        "identity_sha256": identity,
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": {
            "consumed": 1, "completed": 1, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 7,
        },
    })


def _trace_bytes() -> bytes:
    rows = []
    for phase, event in SYNTHETIC_EVENTS:
        item = {"phase": phase, "event": event}
        if event == "end":
            item["elapsed_ns"] = 23_000_000 if phase == "saved_input_asset_scan" else 17
        rows.append(_encode(item))
    return b"\n".join(rows) + b"\n"


def _build_synthetic_v5_delivery(
    tree, profile: recovery.RecoveryProfile, *,
    added_path: str = SYNTHETIC_V4_WRONG_ADDED_PATH,
    tool_files: tuple[str, ...] = recovery.TOOL_FILES,
    schema_overrides: dict[str, object] | None = None,
) -> dict:
    repo = tree.repo
    _write_tool_sources(repo, tool_files)
    for relative, schema in (schema_overrides or {}).items():
        _write(repo / relative, schema)
    (repo / "TASKS.md").write_bytes(b"synthetic native TASKS\n")
    (repo / "docs/INDEX.md").parent.mkdir(parents=True, exist_ok=True)
    (repo / "docs/INDEX.md").write_bytes(b"synthetic native INDEX\n")
    (repo / "docs/TESTING.md").write_bytes(b"synthetic native TESTING\n")

    v5_root = repo / profile.v5_root
    v5_root.mkdir(parents=True, exist_ok=False)
    runner, native_source = write_synthetic_v5_runner(repo)
    build_path = v5_root / "build-record.json"
    build = json.loads(build_path.read_bytes())
    native_archive = v5_root / "source-native.zip"
    native_listing = v5_root / "source-native-file-list.json"

    # Reproduce V5's final documentation snapshot without executing its runner.
    native_files = {
        name: (repo / name).read_bytes()
        for name in native_source["files"]
    }
    final_files = dict(native_files)
    final_files.update({
        "TASKS.md": b"synthetic final TASKS\n",
        "docs/INDEX.md": b"synthetic final INDEX\n",
        "docs/TESTING.md": b"synthetic final TESTING\n",
        added_path: b"synthetic V5 recovery checkpoint\n",
    })
    final_root = v5_root / "final-build"
    final_source, final_archive, final_list = _write_source_bundle(
        final_root, final_files, "synthetic-v5-final-head",
    )
    final_archive.rename(final_root / "source-final.zip")
    final_list.rename(final_root / "source-final-file-list.json")
    final_archive = final_root / "source-final.zip"
    final_list = final_root / "source-final-file-list.json"

    observation = _write(repo / profile.observation_path,
                        b'{"kind":"synthetic_v5_observation"}\n')
    command_log = _write(repo / profile.command_log_path,
                         b"synthetic saved-input audit attempt\n")

    baseline_root = repo / profile.baseline_root
    manifest = json.loads((baseline_root / "research/manifest.json").read_bytes())
    stdout = _saved_stdout(
        manifest["context"], manifest["assets"]["ordinary"]["identity"],
    )
    stderr = _trace_bytes()
    metadata_path = profile.metadata_relative
    stdout_path = profile.stdout_relative
    stderr_path = profile.stderr_relative
    metadata = {
        "mode": "audit_saved_input_only",
        "runner_role": "curry_ledger_handoff_audit_runner",
        "status": "completed",
        "return_code": 0,
        "error_code": None,
        "stdout": {"path": stdout_path.as_posix(), "sha256": _sha(stdout),
                   "bytes": len(stdout)},
        "stderr": {"path": stderr_path.as_posix(), "sha256": _sha(stderr),
                   "bytes": len(stderr)},
        "metadata_path": metadata_path.as_posix(),
    }
    metadata_raw = _pretty(metadata)
    _write(v5_root / metadata_path, metadata_raw)
    _write(v5_root / stdout_path, stdout)
    _write(v5_root / stderr_path, stderr)

    delivery = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_v5_final_delivery",
        "status": "incomplete_outer_audit_cli_failed",
        "native_calls": 0,
        "native_bundle": {
            "source_identity": native_source["identity"],
            "source_file_count": len(native_source["files"]),
            "source_archive_path": (profile.v5_root / "source-native.zip").as_posix(),
            "source_archive_sha256": _sha(native_archive.read_bytes()),
            "source_file_list_path": (profile.v5_root / "source-native-file-list.json").as_posix(),
            "source_file_list_sha256": _sha(native_listing.read_bytes()),
            "build_record_sha256": _sha(build_path.read_bytes()),
            "runner_sha256": _sha(runner.read_bytes()),
            "build_record_identity": build["identity"],
        },
        "source_after_docs": {
            "identity": final_source["identity"],
            "file_count": len(final_source["files"]),
            "archive_path": "source-final.zip",
            "archive_sha256": _sha(final_archive.read_bytes()),
            "file_list_path": "source-final-file-list.json",
            "file_list_sha256": _sha(final_list.read_bytes()),
        },
        "audit_attempt": {
            "cli_exit_code": 2,
            "cli_diagnostic": "audit-curry-ledger-handoff refused: fixed source, runner, or output check failed",
            "failure_checkpoint": None,
            "failure_checkpoint_certified": False,
            "runner_process_calls": 1,
            "runner_mode": "audit_saved_input_only",
            "runner_exit_code": 0,
            "runner_read_only_audit_passed": True,
            "official_report_path": (profile.v5_root / "audit-report.json").as_posix(),
            "official_report_exists": False,
            "rerun_performed": False,
        },
        "process_diagnostics": {
            "role": "curry_ledger_handoff_audit_runner",
            "mode": "audit_saved_input_only",
            "trace_event_count": 8,
            "asset_scan_elapsed_ns": 23_000_000,
            "raw_output_preserved_before_interpretation": True,
            "metadata_path": (profile.v5_root / metadata_path).as_posix(),
            "metadata_sha256": _sha(metadata_raw),
            "stdout_path": (profile.v5_root / stdout_path).as_posix(),
            "stdout_sha256": _sha(stdout),
            "stdout_bytes": len(stdout),
            "stderr_path": (profile.v5_root / stderr_path).as_posix(),
            "stderr_sha256": _sha(stderr),
            "stderr_bytes": len(stderr),
        },
    }
    delivery_raw = _pretty(delivery)
    _write(v5_root / "final-build/delivery.json", delivery_raw)
    assert not (v5_root / handoff.REPORT_RELATIVE).exists()
    return {
        "delivery": delivery,
        "delivery_raw": delivery_raw,
        "native_source": native_source,
        "final_source": final_source,
        "native_archive": native_archive,
        "native_listing": native_listing,
        "final_archive": final_archive,
        "final_list": final_list,
        "observation": observation,
        "command_log": command_log,
        "runner": runner,
    }


def _forbid_external_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    original_run = subprocess.run
    original_popen = subprocess.Popen

    def allowed_read_only_git(args) -> bool:
        return (
            isinstance(args, (list, tuple)) and len(args) >= 4
            and Path(str(args[0])).name.lower() == "git"
            and args[1] == "-C"
            and args[3] in {"check-ignore", "ls-files", "rev-parse"}
        )

    def guarded_run(args, *positional, **kwargs):
        # checked_output uses these local, read-only git queries to establish
        # that the synthetic destination is ignored and untracked. No other
        # subprocess is permitted (in particular, never a runner or worker).
        if allowed_read_only_git(args):
            return original_run(args, *positional, **kwargs)
        raise AssertionError("forbidden_subprocess_run")

    def guarded_popen(args, *positional, **kwargs):
        # subprocess.run delegates to Popen; permit only its checked local-Git
        # identity queries, keeping every other child process blocked.
        if allowed_read_only_git(args):
            return original_popen(args, *positional, **kwargs)
        raise AssertionError("forbidden_subprocess_Popen")

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    for name in ("call", "check_call", "check_output"):
        def denied_process(*_args, _name=name, **_kwargs):
            raise AssertionError(f"forbidden_subprocess_{_name}")
        monkeypatch.setattr(subprocess, name, denied_process)
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        if hasattr(ctypes, name):
            def denied_ffi(*_args, _name=name, **_kwargs):
                raise AssertionError(f"forbidden_ffi_{_name}")
            monkeypatch.setattr(ctypes, name, denied_ffi)


def _forbid_writable_ledger(monkeypatch: pytest.MonkeyPatch,
                            ledger_path: Path) -> None:
    target = ledger_path.resolve()
    original_open = Path.open
    original_write_bytes = Path.write_bytes

    def guarded_open(self, mode="r", *args, **kwargs):
        if (self.resolve() == target
                and any(flag in mode for flag in ("w", "a", "x", "+"))):
            raise AssertionError("writable_journal_forbidden_in_recovery_e2e")
        return original_open(self, mode, *args, **kwargs)

    def guarded_write_bytes(self, data):
        if self.resolve() == target:
            raise AssertionError("writable_journal_forbidden_in_recovery_e2e")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)


def _invoke_recovery_cli(
    monkeypatch, capsys, repo, tree, profile, *, verify_only,
    report_version: int = 1, version_spec=None,
):
    baseline = repo / profile.v5_root
    output = repo / profile.output_root / recovery.OUTPUT_NAME
    argv = [
        "research", "recover-curry-ledger-handoff",
        "--report-version", str(report_version),
        "--baseline-dir", str(baseline), "--output", str(output),
    ]
    if verify_only:
        argv.append("--verify-only")
    monkeypatch.setattr(sys, "argv", argv)

    observed_errors = []
    def injected(args):
        try:
            return REAL_AUDIT_TO_OUTPUT(
                args, repo=repo, source_collector=synthetic_source_identity,
                clock=lambda: 900.0,
                _sources=tree.sources,
                _reservation_profile=tree.reservation_profile,
                _reservation_spec=tree.reservation_spec,
                _option_spec=tree.option_spec,
                _candidate_spec=tree.candidate_spec,
                _profile=profile,
                _version_spec_override=version_spec,
            )
        except Exception as error:
            report_roles = None
            input_set_diagnostic = None
            traceback = error.__traceback__
            while traceback is not None:
                if traceback.tb_frame.f_code.co_name == "audit_to_output":
                    candidate = traceback.tb_frame.f_locals.get("report")
                    if isinstance(candidate, dict):
                        report_roles = sorted(
                            row.get("role") for row in candidate.get("inputs", [])
                            if isinstance(row, dict)
                            and str(row.get("role", "")).startswith("v3_source_")
                        )
                if traceback.tb_frame.f_code.co_name == "_validate_input_rows":
                    frame = traceback.tb_frame
                    actual = frame.f_locals.get("roles")
                    expected = frame.f_locals.get("expected")
                    if isinstance(actual, set) and isinstance(expected, set):
                        input_set_diagnostic = {
                            "missing": sorted(expected - actual),
                            "unexpected": sorted(actual - expected),
                            "actual_count": len(frame.f_locals.get("rows", [])),
                            "expected_count": frame.f_locals.get("expected_count"),
                        }
                traceback = traceback.tb_next
            observed_errors.append(
                f"{type(error).__name__}: {error}; v3_roles={report_roles}; "
                f"input_set={input_set_diagnostic}"
            )
            raise
    monkeypatch.setattr(recovery, "audit_to_output", injected)

    exit_code = research.main()
    captured = capsys.readouterr()
    assert exit_code == 0, (
        f"CLI exit={exit_code}: {captured.out!r} {captured.err!r}; "
        f"observed={observed_errors!r}"
    )
    result = json.loads(captured.out)
    return result


def test_public_research_cli_recovers_and_verifies_synthetic_v5_evidence(
    monkeypatch: pytest.MonkeyPatch, capsys,
):
    scratch = ROOT / "target/curry-ledger-handoff-recovery-tests" / (
        "public-cli-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v5_tree(scratch / "synthetic")
    repo = tree.repo

    # The source profiles and ancestry remain the existing production-shaped
    # synthetic fixtures. Only this test's pins and V5 root are private.
    v5_root = handoff.V5_OUTPUT_RELATIVE
    output_root = Path("data/runtime/p1-curry-ledger-handoff-recovery-tests") / uuid.uuid4().hex
    profile = replace(
        recovery.PRODUCTION_PROFILE,
        v5_root=v5_root,
        output_root=output_root,
        baseline_root=recovery.PRODUCTION_PROFILE.baseline_root,
        reservation_root=recovery.PRODUCTION_PROFILE.reservation_root,
        stage2_input_sha256=_sha(tree.stage2_input_path.read_bytes()),
        prepared_sha256=_sha((tree.stage2_input_path.parent / "prepared.json").read_bytes()),
        reservation_id=curry.OPTION_VERIFICATION_SCOPE.reservation_id,
        reservation_policy_id=curry.OPTION_VERIFICATION_SCOPE.reservation_policy_id,
    )

    ledger_raw = _upgrade_stage1_receipt(tree)
    artifacts = _build_synthetic_v5_delivery(
        tree, profile, added_path=SYNTHETIC_V4_WRONG_ADDED_PATH,
    )
    profile = replace(
        profile,
        native_identity=artifacts["native_source"]["identity"],
        native_count=len(artifacts["native_source"]["files"]),
        native_archive_sha256=_sha(artifacts["native_archive"].read_bytes()),
        native_list_sha256=_sha(artifacts["native_listing"].read_bytes()),
        final_identity=artifacts["final_source"]["identity"],
        final_count=len(artifacts["final_source"]["files"]),
        final_archive_sha256=_sha(artifacts["final_archive"].read_bytes()),
        final_list_sha256=_sha(artifacts["final_list"].read_bytes()),
        delivery_sha256=_sha(artifacts["delivery_raw"]),
        observation_path=profile.observation_path,
        observation_sha256=_sha(artifacts["observation"]),
        command_log_path=profile.command_log_path,
        command_log_sha256=_sha(artifacts["command_log"]),
        ledger_sha256=_sha(ledger_raw),
    )

    process_calls = 0
    _forbid_external_execution(monkeypatch)
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)

    result = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, profile, verify_only=False,
    )
    assert result["status"] == "passed"
    assert result["valid"] is True
    assert result["native_calls"] == 0
    assert result["runner_process_calls"] == 0
    assert result["execution_ready"] is False
    assert all(value is False for value in result["qualifications"].values())
    assert result["checks"] == {name: "passed" for name in recovery.CHECKS}
    assert result["accounting"]["original_scope_consumed"] == 1
    assert result["accounting"]["original_scope_completed"] == 1
    assert result["accounting"]["original_scope_unknown"] == 0
    assert result["accounting"]["certified_historical_consumed_before_scope"] == 32
    assert result["accounting"]["certified_historical_consumed_including_scope"] == 33
    assert result["accounting"]["planning_total"] == 40
    assert result["accounting"]["old_confirmation_actual_consumed"] is None
    assert result["accounting"]["actual_all_history_cumulative"] is None
    assert result["source_groups"] == {
        "v5_original_audit_roles": 164,
        "v5_recovery_anchors": 5,
        "curry_scope_blob_roles": 6,
        "v3_reservation_roles": 100,
    }
    assert len(result["inputs"]) == 175
    assert result["saved_process_evidence"]["trace_event_count"] == 8
    assert result["saved_process_evidence"]["historical_scan_time_certified"] is False
    schema_path = ROOT / "schemas/curry-ledger-handoff-recovery-v1.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema_path.read_bytes())).validate(result)

    report_path = repo / profile.output_root / recovery.OUTPUT_NAME
    saved_report = json.loads(report_path.read_bytes())
    assert saved_report == result
    ledger_before_verify = tree.ledger_path.read_bytes()
    report_tree_before_verify = recovery._tree_snapshot(report_path.parent)

    verified = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, profile, verify_only=True,
    )
    assert verified["valid"] is True
    assert verified["native_calls"] == 0
    assert verified["runner_process_calls"] == 0
    assert verified["execution_ready"] is False
    assert tree.ledger_path.read_bytes() == ledger_before_verify
    assert recovery._tree_snapshot(report_path.parent) == report_tree_before_verify
    assert not tree.stage2_receipt_path.exists()
    assert process_calls == 0
