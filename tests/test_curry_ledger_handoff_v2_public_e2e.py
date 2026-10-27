"""Public research CLI E2E for the synthetic Curry handoff V2 success path."""
from __future__ import annotations

import ctypes
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile
from types import SimpleNamespace

import jsonschema
import pytest

from ygo_data.identity import canonical
from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import research
from tests.support.curry_ledger_handoff_v2_e2e import build_synthetic_handoff_tree
from tests.support.curry_recovery_e2e import synthetic_source_identity


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_synthetic_audit_runner(repo: Path) -> tuple[Path, dict]:
    """Install an inert runner and a real source/archive/build binding."""
    output_root = repo / handoff.V2_OUTPUT_RELATIVE
    artifacts_root = output_root / "native-artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    runner = artifacts_root / handoff.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic inert handoff audit runner; never executed\n")

    source = synthetic_source_identity(repo)
    archive_path = output_root / handoff.SOURCE_ARCHIVE_RELATIVE
    list_path = output_root / handoff.SOURCE_FILE_LIST_RELATIVE
    files: dict[str, bytes] = {}
    for relative in source["files"]:
        path = repo / Path(relative)
        files[relative] = path.read_bytes()
    source_list = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": source["head"],
        "source_identity": source["identity"],
        "file_count": len(source["files"]),
        "files": source["files"],
    }
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    archive_path.write_bytes(archive_buffer.getvalue())
    list_path.write_text(
        json.dumps(source_list, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    archive_hash = _sha(archive_path.read_bytes())
    list_hash = _sha(list_path.read_bytes())
    runner_hash = _sha(runner.read_bytes())
    unsigned = {
        "kind": "build_record",
        "status": "recorded",
        "reproducible_build_proven": False,
        "source_before": source,
        "source_after": source,
        "artifacts": {
            "runner": runner_hash,
            "source_archive": archive_hash,
            "source_file_list": list_hash,
        },
    }
    build = {**unsigned, "identity": _sha(canonical(unsigned))}
    (output_root / handoff.BUILD_RECORD_RELATIVE).write_bytes(
        json.dumps(build, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    return runner, source


def _saved_result(context: str, identity: str) -> dict:
    return {
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
            "consumed": 1,
            "completed": 1,
            "unknown": 0,
            "reserved": 0,
            "abandoned": 0,
            "limit": 7,
        },
    }


def _trace() -> bytes:
    rows = []
    for phase, event in handoff.TRACE_EVENTS:
        value = {"phase": phase, "event": event}
        if event == "end":
            value["elapsed_ns"] = 23
        rows.append(json.dumps(value, separators=(",", ":")))
    return ("\n".join(rows) + "\n").encode("utf-8")


def _forbid_process_and_ffi(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args, **_kwargs):
        raise AssertionError("native_process_or_ffi_forbidden_in_synthetic_e2e")

    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "call", denied)
    monkeypatch.setattr(subprocess, "check_call", denied)
    monkeypatch.setattr(subprocess, "check_output", denied)
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        if hasattr(ctypes, name):
            monkeypatch.setattr(ctypes, name, denied)


def _forbid_writable_ledger(monkeypatch: pytest.MonkeyPatch, ledger_path: Path) -> None:
    ledger_path = ledger_path.resolve()
    original_open = Path.open

    def guarded_open(self, mode="r", *args, **kwargs):
        if self.resolve() == ledger_path and any(flag in mode for flag in ("w", "a", "x", "+")):
            raise AssertionError("writable_journal_forbidden_in_synthetic_audit")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_public_research_cli_runs_complete_synthetic_v2_audit(monkeypatch, capsys):
    scratch = (
        Path(__file__).resolve().parents[1]
        / "target/curry-ledger-handoff-v2-tests"
        / ("public-cli-" + uuid.uuid4().hex)
    )
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_tree(scratch / "sources")
    assert tree.construction_gaps == (), (
        "synthetic_handoff_tree_incomplete:" + ",".join(tree.construction_gaps)
    )
    assert (tree.ledger_path.parent / "manifest.json").is_file()
    assert (tree.ledger_path.parent / "prepared.json").is_file()
    assert not (tree.ledger_path.parent.parent / "manifest.json").exists()
    repo = tree.repo
    frozen_manifest_raw = (tree.ledger_path.parent / "manifest.json").read_bytes()
    frozen_prepared_raw = (tree.ledger_path.parent / "prepared.json").read_bytes()
    final_acceptance = json.loads(
        (repo / handoff.BASELINE_RELATIVE / handoff.ACCEPTANCE_RELATIVE).read_bytes()
    )
    assert final_acceptance["preflight"] == {
        "context": json.loads(frozen_manifest_raw)["context"],
        "manifest_sha256": _sha(frozen_manifest_raw),
        "prepared_sha256": _sha(frozen_prepared_raw),
        "prepared": True,
        "execution_ready_at_prepare": True,
        "passed": True,
        "native_calls": 0,
        "input_roles": 21,
    }
    output_root = repo / handoff.V2_OUTPUT_RELATIVE
    output_root.mkdir(parents=True, exist_ok=True)
    (repo / ".gitignore").write_text("data/runtime/\n", encoding="utf-8")
    runner, source = _write_synthetic_audit_runner(repo)
    ledger_before = tree.ledger_path.read_bytes()
    ledger_hash_before = _sha(ledger_before)
    assert not tree.stage2_receipt_path.exists()

    argv = [
        "research", "audit-curry-ledger-handoff", "--report-version", "2",
        "--baseline-dir", str(repo / handoff.BASELINE_RELATIVE),
        "--runner", str(runner),
        "--build-record", str(output_root / handoff.BUILD_RECORD_RELATIVE),
        "--output", str(output_root / handoff.REPORT_RELATIVE),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    real_run_audit = handoff.run_audit
    process_calls: list[tuple[list[str], dict]] = []
    clock_values = iter((100.0, 100.25))

    def fake_process(command, **kwargs):
        process_calls.append((list(command), dict(kwargs)))
        manifest = json.loads(
            (repo / "data/runtime/p1-curry-option-verification-native-2026-10-25"
             / "research/manifest.json").read_bytes()
        )
        stdout = json.dumps(
            _saved_result(manifest["context"], manifest["assets"]["ordinary"]["identity"]),
            separators=(",", ":"),
        ).encode("utf-8")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=_trace())

    def runner_build_verifier(runner_path, build_record_path, run_repo):
        assert run_repo == repo
        return handoff._verify_runner_build(
            runner_path, build_record_path, run_repo, source,
        )

    def stability_verifier(**kwargs):
        return handoff._verify_stability(
            **kwargs, source_collector=synthetic_source_identity,
        )

    def injected_run_audit(args):
        return real_run_audit(
            args,
            repo=repo,
            process_runner=fake_process,
            runner_build_verifier=runner_build_verifier,
            stability_verifier=stability_verifier,
            source_collector=synthetic_source_identity,
            clock=lambda: next(clock_values),
            _sources=tree.sources,
            _reservation_profile=tree.reservation_profile,
            _reservation_spec=tree.reservation_spec,
            _option_spec=tree.option_spec,
            _candidate_spec=tree.candidate_spec,
        )

    monkeypatch.setattr(handoff, "run_audit", injected_run_audit)
    _forbid_process_and_ffi(monkeypatch)
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)

    exit_code = research.main()
    captured = capsys.readouterr()
    printed = captured.out
    if exit_code != 0:
        saved = output_root / handoff.REPORT_RELATIVE
        saved_text = saved.read_text(encoding="utf-8") if saved.is_file() else "<no report saved>"
        pytest.fail(
            f"public_cli_exit={exit_code}; stdout={printed!r}; stderr={captured.err!r}; saved_report={saved_text}"
        )
    report = json.loads(printed)
    assert report["status"] == "passed"
    assert report["checks"] == {name: "passed" for name in handoff.V2_CHECK_NAMES}
    assert report["native_calls"] == 0
    assert report["execution_ready"] is False
    assert report["accounting"] == {
        "certified_historical_consumed": 32,
        "policy_reserved": 7,
        "planning_base": 39,
        "new_consumed": 1,
        "certified_consumed_including_new": 33,
        "planning_total": 40,
        "unknown": 0,
        "old_confirmation_actual_consumed": None,
        "actual_all_history_cumulative": None,
    }
    assert report["runner"]["saved_input_result"]["ledger"] == {
        "consumed": 1, "completed": 1, "unknown": 0,
        "reserved": 0, "abandoned": 0, "limit": 7,
    }
    assert len(process_calls) == 1
    command, process_kwargs = process_calls[0]
    assert command[0] == str(runner)
    assert command[command.index("--input-sha") + 1] == report["baseline"]["stage2_input_sha256"]
    assert "--audit-saved-input-only" in command and "--trace-stderr" in command
    assert process_kwargs["timeout"] == 900
    assert process_kwargs["check"] is False
    assert handoff.validate_report(
        report, _sources=tree.sources, repo=repo,
        source_collector=synthetic_source_identity,
        _reservation_profile=tree.reservation_profile,
        _reservation_spec=tree.reservation_spec,
        _option_spec=tree.option_spec,
        _candidate_spec=tree.candidate_spec,
    )
    schema = json.loads(
        (Path(__file__).resolve().parents[1]
         / handoff.AUDIT_VERSIONS[2].schema_path).read_bytes()
    )
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(report)
    v3_rows = [row for row in report["inputs"] if row["role"].startswith("v3_source_")]
    assert len(v3_rows) == handoff.V3_SOURCE_INPUT_COUNT
    schema_pinned_v3_roles = set()

    def collect_pinned_roles(node):
        if isinstance(node, dict):
            role = (
                node.get("properties", {})
                .get("inputs", {})
                .get("contains", {})
                .get("properties", {})
                .get("role", {})
            )
            if isinstance(role, dict) and "const" in role:
                schema_pinned_v3_roles.add(role["const"])
            for child in node.values():
                collect_pinned_roles(child)
        elif isinstance(node, list):
            for child in node:
                collect_pinned_roles(child)

    collect_pinned_roles(schema)
    unpinned_v3_row = next(
        row for row in v3_rows
        if row["role"] not in handoff.V3_SOURCE_REQUIRED_ROLES
        and row["role"] not in schema_pinned_v3_roles
    )
    truncated = json.loads(json.dumps(report))
    truncated["inputs"].remove(unpinned_v3_row)
    with pytest.raises(ValueError, match="curry_handoff_success_inputs_incomplete"):
        handoff.validate_report(
            truncated, _sources=tree.sources, repo=repo,
            source_collector=synthetic_source_identity,
            _reservation_profile=tree.reservation_profile,
            _reservation_spec=tree.reservation_spec,
            _option_spec=tree.option_spec,
            _candidate_spec=tree.candidate_spec,
        )
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(truncated)
    saved_report = output_root / handoff.REPORT_RELATIVE
    assert json.loads(saved_report.read_bytes()) == report
    assert tree.ledger_path.read_bytes() == ledger_before
    assert _sha(tree.ledger_path.read_bytes()) == ledger_hash_before
    assert not tree.stage2_receipt_path.exists()
    assert len(list((output_root / "process-diagnostics").iterdir())) == 3
