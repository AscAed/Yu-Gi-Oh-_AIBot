"""Full synthetic public-CLI E2E for Ground Collapse preparation.

The test composes real synthetic V3 recovery/reservation and Curry delivery
sources, then exercises the unmocked Ground Collapse source validators through
the public research CLI. All generated inputs live under ignored target/ or
data/runtime/ trees; the synthetic binaries are inert and are never launched.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pytest

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval import curry_ledger_handoff_recovery as recovery
from ygo_eval import ground_collapse_preparation as ground
from ygo_eval import research
from ygo_eval import native_curry_option_validation as curry
from tests.support.curry_ground_collapse_full_e2e import (
    build_revalidation_source_bundle,
    compose_ground_collapse_source_components,
)
from tests.support.curry_ledger_handoff_v5_e2e import build_synthetic_handoff_v5_tree
from tests.support import curry_recovery_e2e as recovery_support
from tests.test_curry_ledger_handoff_recovery_public_e2e import (
    _build_synthetic_v5_delivery,
    _forbid_external_execution,
    _forbid_writable_ledger,
    _invoke_recovery_cli,
    _write_tool_sources,
    ROOT,
    SYNTHETIC_V5_ADDED_PATH,
)
from tests.test_curry_ledger_handoff_recovery_v2_public_e2e import _upgrade_stage1_receipt
from tests.test_curry_ledger_handoff_recovery_v3 import (
    _install_synthetic_v2_failed_source,
)
from tests.test_ground_collapse_preparation import _runtime_gate_fixture
from tests.test_curry_ledger_handoff_recovery_public_e2e import _write

_ORIGINAL_SYNTHETIC_SOURCE_IDENTITY = recovery_support.synthetic_source_identity
_ORIGINAL_GROUND_PREPARE = ground.prepare_ground_collapse_probe


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _filtered_synthetic_source_identity(repo: Path) -> dict:
    """Keep the historical workspace count fixed while separately pinning
    the Ground tool members through their real tool-bundle validator.
    """
    from ygo_data.identity import canonical

    value = _ORIGINAL_SYNTHETIC_SOURCE_IDENTITY(repo)
    files = {
        name: digest for name, digest in value["files"].items()
        if name not in set(ground.TOOL_FILES)
    }
    unsigned = {"head": value["head"], "files": files}
    return {**unsigned, "identity": _sha(canonical(unsigned))}


def _make_successful_v3_recovery(monkeypatch, capsys, repo: Path, tree):
    """Run the existing public V3 recovery CLI against a synthetic source tree."""
    v3_profile = replace(
        recovery.V3_PROFILE,
        v5_root=handoff.V5_OUTPUT_RELATIVE,
        output_root=Path("data/runtime/p1-ground-collapse-recovery-e2e") / uuid.uuid4().hex,
        stage2_input_sha256=_sha(tree.stage2_input_path.read_bytes()),
        prepared_sha256=_sha((tree.stage2_input_path.parent / "prepared.json").read_bytes()),
        reservation_id=curry.OPTION_VERIFICATION_SCOPE.reservation_id,
        reservation_policy_id=curry.OPTION_VERIFICATION_SCOPE.reservation_policy_id,
        added=(SYNTHETIC_V5_ADDED_PATH,),
        removed=(),
        changed=("TASKS.md", "docs/INDEX.md", "docs/TESTING.md"),
    )
    _upgrade_stage1_receipt(tree)
    v1_report_sha, v1_delivery_sha, v2_report_sha, v2_delivery_sha = (
        _install_synthetic_v2_failed_source(repo)
    )

    _write_tool_sources(repo, recovery.TOOL_FILES_V3)
    schema_path = repo / "schemas/curry-ledger-handoff-recovery-v3.schema.json"
    schema = json.loads(schema_path.read_bytes())
    v1_props = schema["properties"]["previous_recovery_source"]["properties"]
    v1_props["report_sha256"]["const"] = v1_report_sha
    v1_props["delivery_sha256"]["const"] = v1_delivery_sha
    v2_props = schema["properties"]["previous_recovery_v2_source"]["properties"]
    v2_props["report_sha256"]["const"] = v2_report_sha
    v2_props["delivery_sha256"]["const"] = v2_delivery_sha
    _write(schema_path, schema)

    artifacts = _build_synthetic_v5_delivery(
        tree, v3_profile, added_path=SYNTHETIC_V5_ADDED_PATH,
        tool_files=recovery.TOOL_FILES_V3,
        schema_overrides={"schemas/curry-ledger-handoff-recovery-v3.schema.json": schema},
    )
    v3_profile = replace(
        v3_profile,
        native_identity=artifacts["native_source"]["identity"],
        native_count=len(artifacts["native_source"]["files"]),
        native_archive_sha256=_sha(artifacts["native_archive"].read_bytes()),
        native_list_sha256=_sha(artifacts["native_listing"].read_bytes()),
        final_identity=artifacts["final_source"]["identity"],
        final_count=len(artifacts["final_source"]["files"]),
        delivery_source_after_docs_identity=artifacts["final_source"]["identity"],
        delivery_source_after_docs_file_count=len(artifacts["final_source"]["files"]),
        final_archive_sha256=_sha(artifacts["final_archive"].read_bytes()),
        final_list_sha256=_sha(artifacts["final_list"].read_bytes()),
        delivery_sha256=_sha(artifacts["delivery_raw"]),
        observation_sha256=_sha(artifacts["observation"]),
        command_log_sha256=_sha(artifacts["command_log"]),
        ledger_sha256=_sha(tree.ledger_path.read_bytes()),
    )
    v3_spec = replace(
        recovery.V3_SPEC,
        profile=v3_profile,
        previous_recovery_report_sha256=v1_report_sha,
        previous_recovery_delivery_sha256=v1_delivery_sha,
        previous_recovery_v2_report_sha256=v2_report_sha,
        previous_recovery_v2_delivery_sha256=v2_delivery_sha,
    )
    result = _invoke_recovery_cli(
        monkeypatch, capsys, repo, tree, v3_profile,
        verify_only=False, report_version=3, version_spec=v3_spec,
    )
    assert result["status"] == "passed"
    assert result["valid"] is True
    assert result["native_calls"] == result["runner_process_calls"] == 0
    assert len(result["inputs"]) == 187
    # Curry's fixed V3 source gate consumes the final delivery separately from
    # the recovery report. Mirror that real two-file source shape in this
    # isolated synthetic tree; the report itself remains the output of the
    # public recovery CLI above.
    recovery_raw = (repo / v3_profile.output_root / "recovery-report.json").read_bytes()
    v3_delivery = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_recovery_v3_final_delivery",
        "status": "passed",
        "report": {
            "path": "../recovery-report.json",
            "sha256": _sha(recovery_raw),
        },
        "source_after_docs": {
            "workspace_identity": v3_profile.delivery_source_after_docs_identity,
            "file_count": v3_profile.delivery_source_after_docs_file_count,
        },
    }
    _write(repo / v3_profile.output_root / "final-build/delivery-final.json", v3_delivery)
    return v3_profile, v3_spec, result


def _wire_ground_preparation_fixture(
    repo: Path, candidate_root: Path, revalidation_root: Path,
    revalidation_source, delivery_profile, candidate_profile, candidate, core_root, paths,
):
    frozen = json.loads((candidate_root / "frozen-cases.json").read_bytes())
    base = frozen["cases"][0]

    # The real prompt-preparation gate always resolves its evidence root from
    # the fixed source checkout. Keep this fixture's 37 files in a unique
    # child and bind those exact bytes from the synthetic acceptance.
    old_acceptance_path = candidate_root / "acceptance.json"
    acceptance = json.loads(old_acceptance_path.read_bytes())
    prompt_root_rel = Path("data/runtime/p1-prompt-probes-offline-2026-10-21")
    destination_root = repo / prompt_root_rel / "ground-collapse-e2e" / uuid.uuid4().hex
    remapped = {}
    for old_relative, metadata in acceptance["evidence"].items():
        raw_path = candidate_root / prompt_root_rel / old_relative
        raw = raw_path.read_bytes()
        relative = (Path("ground-collapse-e2e") / destination_root.name / old_relative).as_posix()
        target = repo / prompt_root_rel / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        remapped[relative] = {"bytes": len(raw), "sha256": _sha(raw)}
    assert len(remapped) == 37
    acceptance["evidence"] = remapped
    old_acceptance_path.write_bytes(ground.encode(acceptance))

    # All evidence input files remain in the synthetic repo. The V3 history
    # collector excludes these separately pinned Ground tool members; their
    # content is still read and hashed by the Ground tool-bundle gate itself.
    for name in ground.TOOL_FILES:
        source = ROOT / name
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    ignore = repo / ".gitignore"
    if not ignore.exists():
        ignore.write_text("data/runtime\ntarget/\n", encoding="utf-8")

    profile = replace(
        candidate_profile,
        # The Curry delivery builder owns the pinned historical delivery,
        # source archives, ledger, and build records. Keep the candidate
        # fixture's independent catalog/script/core pins below.
        output_root=ground.OUTPUT_ROOT,
        baseline_root=revalidation_root.relative_to(repo),
        acceptance_path=old_acceptance_path.relative_to(repo),
        preparation_report_path=(candidate_root / "preparation-report.json").relative_to(repo),
        preparation_cases_path=(candidate_root / "prepared-cases.json").relative_to(repo),
        frozen_cases_path=(candidate_root / "frozen-cases.json").relative_to(repo),
        core_source_path=core_root.relative_to(repo),
        acceptance_sha256=_sha(old_acceptance_path.read_bytes()),
        preparation_report_sha256=_sha((candidate_root / "preparation-report.json").read_bytes()),
        preparation_cases_sha256=_sha((candidate_root / "prepared-cases.json").read_bytes()),
        frozen_cases_sha256=_sha((candidate_root / "frozen-cases.json").read_bytes()),
        curry_delivery_sha256=delivery_profile.curry_delivery_sha256,
        native_archive_sha256=delivery_profile.native_archive_sha256,
        native_file_list_sha256=delivery_profile.native_file_list_sha256,
        native_identity=delivery_profile.native_identity,
        final_archive_sha256=delivery_profile.final_archive_sha256,
        final_file_list_sha256=delivery_profile.final_file_list_sha256,
        final_identity=delivery_profile.final_identity,
        ledger_sha256=delivery_profile.ledger_sha256,
        summary_sha256=delivery_profile.summary_sha256,
        native_build_record_sha256=delivery_profile.native_build_record_sha256,
        native_build_record_identity=delivery_profile.native_build_record_identity,
        core_pins=candidate_profile.core_pins,
        script_manifest_pins=candidate_profile.script_manifest_pins,
        target_script_pins=candidate_profile.target_script_pins,
        source_diff=delivery_profile.source_diff,
        tool_files=ground.TOOL_FILES,
        revalidation_source=revalidation_source,
    )
    return profile, candidate, base


def _invoke_ground_public_cli(monkeypatch, capsys, repo: Path, profile, *, verify_only: bool):
    args = [
        "research", "prepare-ground-collapse-probe",
        "--baseline-dir", str(repo / profile.baseline_root),
        "--preparation", str(repo / profile.preparation_cases_path),
        "--cases", str(repo / profile.frozen_cases_path),
        "--core-source", str(repo / profile.core_source_path),
        "--output", str(repo / profile.output_root / ground.OUTPUT_FILE),
    ]
    if verify_only:
        args.append("--verify-only")
    monkeypatch.setattr(sys, "argv", args)

    real_prepare = _ORIGINAL_GROUND_PREPARE
    dispatch_errors: list[str] = []

    def injected_public_prepare(parsed):
        try:
            return real_prepare(
                parsed, repo=repo, source_collector=_filtered_synthetic_source_identity,
                profile=profile,
            )
        except Exception as error:
            dispatch_errors.append(f"{type(error).__name__}:{error}")
            raise

    # Only provide synthetic source bytes/identity at the existing entrypoint
    # boundary; the public parser/dispatch and every production validator run.
    monkeypatch.setattr(ground, "_source_description", lambda: profile)
    monkeypatch.setattr(ground, "stable_source", _filtered_synthetic_source_identity)
    monkeypatch.setattr(ground, "prepare_ground_collapse_probe", injected_public_prepare)
    code = research.main()
    captured = capsys.readouterr()
    assert code == 0, f"ground CLI exit={code}: {captured.out!r} {captured.err!r}; internal={dispatch_errors!r}"
    cli_summary = json.loads(captured.out)
    if verify_only:
        return cli_summary
    saved_report = json.loads((repo / profile.output_root / ground.OUTPUT_FILE).read_bytes())
    assert cli_summary == {
        "status": saved_report["status"],
        "preparation_successful": saved_report["preparation_successful"],
        "execution_ready": False,
        "native_calls": 0,
        "runner_process_calls": 0,
        "worker_calls": 0,
        "ffi_calls": 0,
        "diagnostics": saved_report["diagnostics"],
    }
    return saved_report


def test_public_ground_collapse_prepare_and_verify_with_real_synthetic_source_chain(
    monkeypatch: pytest.MonkeyPatch, capsys,
):
    scratch = ROOT / "target/ground-collapse-preparation-tests" / ("public-e2e-" + uuid.uuid4().hex)
    scratch.mkdir(parents=True, exist_ok=False)
    tree = build_synthetic_handoff_v5_tree(scratch / "synthetic")
    repo = tree.repo

    # Store Ground's pinned tool files before building the recovery identity;
    # the fixture collector omits them from the historical workspace identity,
    # while the dedicated Ground tool bundle independently pins every byte.
    for name in ground.TOOL_FILES:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())

    # Retain the source collector's existing exclusions while excluding only
    # the Ground bundle members that are separately authenticated below.
    monkeypatch.setattr(recovery_support, "synthetic_source_identity", _filtered_synthetic_source_identity)
    import tests.test_curry_ledger_handoff_recovery_public_e2e as recovery_public
    monkeypatch.setattr(recovery_public, "synthetic_source_identity", _filtered_synthetic_source_identity)
    import tests.test_curry_ledger_handoff_recovery_v3 as recovery_v3
    monkeypatch.setattr(recovery_v3, "synthetic_source_identity", _filtered_synthetic_source_identity)

    # The recovered report is built with actual V3 recovery validators and the
    # public CLI. It is a successful synthetic source, never native evidence.
    _forbid_external_execution(monkeypatch)
    v3_profile, v3_spec, recovery_report = _make_successful_v3_recovery(
        monkeypatch, capsys, repo, tree,
    )

    synthetic_scope_spec = replace(
        curry.OPTION_REVALIDATION_SCOPE,
        baseline_root=v3_profile.output_root,
        reservation_sha256=tree.option_spec.reservation_sha256,
        reservation_id=tree.option_spec.reservation_id,
        reservation_policy_id=tree.option_spec.reservation_policy_id,
        baseline_recovery_sha256=_sha(
            (repo / v3_profile.output_root / "recovery-report.json").read_bytes()
        ),
        delivery_sha256=_sha(
            (repo / v3_profile.output_root / "final-build/delivery-final.json").read_bytes()
        ),
    )
    components = compose_ground_collapse_source_components(
        tree, recovery_profile=v3_profile, recovery_version_spec=v3_spec,
        scope_spec=synthetic_scope_spec,
    )
    candidate_root = repo / "target/ground-collapse-preparation-tests" / ("candidate-" + uuid.uuid4().hex)
    candidate_root.mkdir(parents=True, exist_ok=False)
    _candidate_capture, candidate, _core_root, candidate_profile, _paths = _runtime_gate_fixture(candidate_root)
    baseline_root = repo / "data/runtime/baseline-2026-10-19"
    # The Ground fixture has its own compact Rabbit deck for runtime/core
    # gate tests. The upstream Curry revalidation fixture must instead derive
    # from the authenticated Rabbit case in the synthetic baseline tree.
    frozen = json.loads((baseline_root / "research/frozen-cases.json").read_bytes())
    base = frozen["cases"][0]
    revalidation_root = (
        repo / "target/ground-collapse-preparation-tests" / ("synthetic-revalidation-" + uuid.uuid4().hex)
    )
    descriptor, delivery_profile, delivery = build_revalidation_source_bundle(
        repo, revalidation_root,
        source_components=components,
        base_request=base["request"],
        rabbit_case=base["case"],
        candidate_case=curry._derived_curry_case(base["case"]),
    )
    assert len(delivery.receipts) == 7
    assert delivery.ledger_path.is_file()
    # Freeze both synthetic journals only after their fixture builders have
    # populated them. The public Ground prepare and verify paths are strictly
    # read-only and must not mutate either historical journal.
    _forbid_writable_ledger(monkeypatch, tree.ledger_path)
    _forbid_writable_ledger(monkeypatch, delivery.ledger_path)

    profile, _candidate, _base = _wire_ground_preparation_fixture(
        repo, candidate_root, revalidation_root, descriptor, delivery_profile,
        candidate_profile, candidate, _core_root, _paths,
    )

    # Simulate a transient swap after the stage request bytes have been
    # captured, then restore the file before the final stability check. The
    # ledger verifier must bind to the captured bytes, not reopen this path.
    original_ledger_check = ground._verify_option_revalidation_ledger
    swapped = False

    def transient_request_swap(capture, repo_root, ledger_raw, summary):
        nonlocal swapped
        request_path = repo_root / "research/stage-1-request.json"
        original_request = request_path.read_bytes()
        if not swapped:
            changed_request = json.loads(original_request)
            changed_request["transient_test_mutation"] = True
            request_path.write_text(json.dumps(changed_request), encoding="utf-8")
            swapped = True
        try:
            return original_ledger_check(capture, repo_root, ledger_raw, summary)
        finally:
            request_path.write_bytes(original_request)

    monkeypatch.setattr(ground, "_verify_option_revalidation_ledger", transient_request_swap)
    prepared = _invoke_ground_public_cli(monkeypatch, capsys, repo, profile, verify_only=False)
    assert prepared["status"] == "passed"
    assert prepared["preparation_successful"] is True
    assert prepared["native_calls"] == prepared["runner_process_calls"] == 0
    assert prepared["worker_calls"] == prepared["ffi_calls"] == 0
    assert prepared["execution_ready"] is False
    assert prepared["sources"]["historical_certified_consumed"] == 40
    assert prepared["sources"]["historical_policy_reserved"] == 7
    assert prepared["sources"]["historical_planning_base"] == 47
    assert prepared["sources"]["historical_protection"]["entry_count"] > 0
    assert prepared["candidate"]["card_id"] == 90502999
    assert prepared["protocol_vectors"]["opcode24"]["audit"]["canonical_menu_pairs"] == 45

    verified = _invoke_ground_public_cli(monkeypatch, capsys, repo, profile, verify_only=True)
    assert verified["valid"] is True
    assert verified["preparation_successful"] is True
    assert verified["native_calls"] == verified["runner_process_calls"] == 0
    assert verified["worker_calls"] == verified["ffi_calls"] == 0
    assert recovery_report["status"] == "passed"
    assert delivery.summary["successful"] is True
