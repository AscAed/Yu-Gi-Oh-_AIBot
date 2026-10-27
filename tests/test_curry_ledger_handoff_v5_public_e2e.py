"""Public CLI success path for the synthetic Curry handoff V5 audit."""
from __future__ import annotations

import ctypes
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from types import SimpleNamespace

import jsonschema
import pytest

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import research
from tests.support.curry_ledger_handoff_v4_e2e import (
    V4_STAGE1_STDOUT,
    stage1_stdout_bytes,
)
from tests.support.curry_ledger_handoff_v5_e2e import (
    build_synthetic_handoff_v5_tree,
    write_synthetic_v5_runner,
)
from tests.support.curry_recovery_e2e import synthetic_source_identity


ROOT = Path(__file__).resolve().parents[1]


def _saved_input_stdout(context: str, identity: str) -> bytes:
    """Return the exact documented saved-input response, not stage-1 output."""
    value = {
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
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _trace() -> bytes:
    rows = []
    for phase, event in handoff.TRACE_EVENTS:
        row = {"phase": phase, "event": event}
        if event == "end":
            row["elapsed_ns"] = 23
        rows.append(json.dumps(row, separators=(",", ":")))
    return ("\n".join(rows) + "\n").encode("utf-8")


def _forbid_process_and_ffi(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args, **_kwargs):
        raise AssertionError("native_process_or_ffi_forbidden_in_synthetic_e2e")

    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, denied)
    for name in ("CDLL", "PyDLL", "WinDLL", "OleDLL"):
        if hasattr(ctypes, name):
            monkeypatch.setattr(ctypes, name, denied)


def _forbid_writable_ledger(monkeypatch: pytest.MonkeyPatch, ledger_path: Path) -> None:
    target = ledger_path.resolve()
    original_open = Path.open

    def guarded_open(self, mode="r", *args, **kwargs):
        if self.resolve() == target and any(flag in mode for flag in ("w", "a", "x", "+")):
            raise AssertionError("writable_journal_forbidden_in_synthetic_audit")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)


def test_public_research_cli_runs_complete_synthetic_v5_audit(monkeypatch, capsys):
    scratch = ROOT / "target/curry-ledger-handoff-v5-tests" / (
        "public-cli-" + uuid.uuid4().hex
    )
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v5_tree(scratch / "synthetic")
    repo = tree.repo
    runner, _source = write_synthetic_v5_runner(repo)
    output_root = repo / handoff.V5_OUTPUT_RELATIVE
    assert {item.name for item in output_root.iterdir()} == {
        "native-artifacts", "build-record.json", "source-native.zip",
        "source-native-file-list.json",
    }
    ledger_before = tree.ledger_path.read_bytes()
    baseline_root = repo / handoff.BASELINE_RELATIVE

    # This is a separately hand-written 14-field stage-1 golden. It is not
    # generated from the production stdout oracle or from the mocked response.
    stage1_sidecar = json.loads(
        (baseline_root / "stage-1-process-diagnostic.json").read_bytes()
    )
    stage1_stdout_path = baseline_root / stage1_sidecar["stdout"]["path"]
    expected_stage1 = stage1_stdout_bytes(tree.option_spec)
    assert stage1_stdout_path.read_bytes() == expected_stage1
    assert json.loads(expected_stage1) == {
        **V4_STAGE1_STDOUT,
        "reservation_id": tree.option_spec.reservation_id,
    }
    assert len(json.loads(expected_stage1)) == 14

    monkeypatch.setattr(sys, "argv", [
        "research", "audit-curry-ledger-handoff", "--report-version", "5",
        "--baseline-dir", str(repo / handoff.BASELINE_RELATIVE),
        "--runner", str(runner),
        "--build-record", str(output_root / handoff.BUILD_RECORD_RELATIVE),
        "--output", str(output_root / handoff.REPORT_RELATIVE),
    ])

    process_calls: list[tuple[list[str], dict]] = []
    audit_exceptions: list[str] = []
    clock_values = iter((100.0, 100.5))

    def fake_process(command, **kwargs):
        process_calls.append((list(command), dict(kwargs)))
        manifest = json.loads(
            (baseline_root / "research/manifest.json").read_bytes()
        )
        return SimpleNamespace(
            returncode=0,
            stdout=_saved_input_stdout(
                manifest["context"], manifest["assets"]["ordinary"]["identity"],
            ),
            stderr=_trace(),
        )

    real_run_audit = handoff.run_audit
    def injected_run_audit(args):
        try:
            return real_run_audit(
                args, repo=repo, process_runner=fake_process,
                source_collector=synthetic_source_identity,
                clock=lambda: next(clock_values), _sources=tree.sources,
                _reservation_profile=tree.reservation_profile,
                _reservation_spec=tree.reservation_spec,
                _option_spec=tree.option_spec,
                _candidate_spec=tree.candidate_spec,
            )
        except Exception as error:
            audit_exceptions.append(f"{type(error).__name__}:{error}")
            raise

    monkeypatch.setattr(handoff, "run_audit", injected_run_audit)
    _forbid_process_and_ffi(monkeypatch)
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)

    exit_code = research.main()
    captured = capsys.readouterr()
    if exit_code != 0:
        saved_path = output_root / handoff.REPORT_RELATIVE
        saved = saved_path.read_text(encoding="utf-8") if saved_path.is_file() else "<no report>"
        pytest.fail(
            f"public_cli_exit={exit_code}; stdout={captured.out!r}; "
            f"stderr={captured.err!r}; exceptions={audit_exceptions!r}; saved={saved}"
        )

    report = json.loads(captured.out)
    assert report["status"] == "passed"
    assert report["checks"] == {name: "passed" for name in handoff.V5_CHECK_NAMES}
    assert report["native_calls"] == 0
    assert report["execution_ready"] is False
    assert report["proof_ready"] is False
    assert report["complete_action_coverage"] is False
    assert report["global_optimality"] is False
    assert report["native_probability_verified"] is False
    assert report["accounting"] == {
        "scope": "curry-option-verification-v1",
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

    roles = [item["role"] for item in report["inputs"]]
    assert len(roles) == 164
    assert len(roles) == len(set(roles))
    assert len([role for role in roles if role.startswith("v3_source_")]) == 100
    assert handoff.V4_PREVIOUS_V3_INPUT_ROLES <= set(roles)
    assert handoff.V4_STAGE1_DIAGNOSTIC_INPUT_ROLES <= set(roles)
    assert handoff.V5_PREVIOUS_V4_INPUT_ROLES <= set(roles)
    previous_v4 = report["previous_v4_failed_source"]
    assert previous_v4["status"] == "failed"
    assert previous_v4["failure_checkpoint"] == "previous_v3_failed_source"
    assert previous_v4["diagnostic"] == "curry_handoff_build_root_contents_invalid"
    assert previous_v4["file_count"] == 568
    assert previous_v4["final_file_count"] == 569
    assert previous_v4["source_delta"] == handoff.V5_ALLOWED_SOURCE_DELTA
    assert len(process_calls) == 1
    command, kwargs = process_calls[0]
    assert command[0] == str(runner)
    assert command[command.index("--input-sha") + 1] == hashlib.sha256(
        tree.stage2_input_path.read_bytes()
    ).hexdigest()
    assert command[command.index("--prepared-sha256") + 1] == hashlib.sha256(
        (tree.stage2_input_path.parent / "prepared.json").read_bytes()
    ).hexdigest()
    assert "--audit-saved-input-only" in command and "--trace-stderr" in command
    assert kwargs["timeout"] == 900 and kwargs["check"] is False
    assert report["runner"]["saved_input_result"] == {
        "saved_input_audit_passed": True,
        "stage": 2,
        "context": json.loads(
            (baseline_root / "research/manifest.json").read_bytes()
        )["context"],
        "identity_sha256": json.loads(
            (baseline_root / "research/manifest.json").read_bytes()
        )["assets"]["ordinary"]["identity"],
        "parent_receipt_valid": True,
        "request_derivation_valid": True,
        "stage_receipt_absent": True,
        "ledger": {
            "consumed": 1, "completed": 1, "unknown": 0,
            "reserved": 0, "abandoned": 0, "limit": 7,
        },
    }
    assert report["runner"]["process_status"] == "completed"
    assert report["runner"]["trace"] == [
        {"phase": phase, "event": event,
         **({"elapsed_ns": 23} if event == "end" else {})}
        for phase, event in handoff.TRACE_EVENTS
    ]
    assert report["runner"]["stdout_sha256"] == hashlib.sha256(
        _saved_input_stdout(
            json.loads((baseline_root / "research/manifest.json").read_bytes())["context"],
            json.loads((baseline_root / "research/manifest.json").read_bytes())
            ["assets"]["ordinary"]["identity"],
        )
    ).hexdigest()

    schema_path = ROOT / handoff.AUDIT_VERSIONS[5].schema_path
    schema = json.loads(schema_path.read_bytes())
    jsonschema.Draft202012Validator(schema).validate(report)
    structurally_valid_but_unpinned = copy.deepcopy(report)
    structurally_valid_but_unpinned["previous_v4_failed_source"]["report_sha256"] = "a" * 64
    jsonschema.Draft202012Validator(schema).validate(structurally_valid_but_unpinned)
    with pytest.raises(ValueError, match="curry_handoff_previous_v4_source_fields_invalid"):
        handoff.validate_report(
            structurally_valid_but_unpinned, _sources=tree.sources, repo=repo,
            source_collector=synthetic_source_identity,
            _reservation_profile=tree.reservation_profile,
            _reservation_spec=tree.reservation_spec,
            _option_spec=tree.option_spec,
            _candidate_spec=tree.candidate_spec,
        )
    assert handoff.validate_report(
        report, _sources=tree.sources, repo=repo,
        source_collector=synthetic_source_identity,
        _reservation_profile=tree.reservation_profile,
        _reservation_spec=tree.reservation_spec,
        _option_spec=tree.option_spec,
        _candidate_spec=tree.candidate_spec,
    )
    saved_path = output_root / handoff.REPORT_RELATIVE
    assert json.loads(saved_path.read_bytes()) == report
    assert tree.ledger_path.read_bytes() == ledger_before
    assert not tree.stage2_receipt_path.exists()
