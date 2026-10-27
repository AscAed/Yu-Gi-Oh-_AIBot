"""Synthetic source helpers for Curry ledger-handoff V2 integration tests.

All files created by this module are inert synthetic bytes under the caller's
ignored test root.  The helpers intentionally call production read-only
validators; they do not start a runner, worker, FFI, or doctor.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import json
from pathlib import Path
import zipfile
from types import SimpleNamespace
from typing import Any, Callable

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval.curry_input_recovery_audit import (
    _PinnedArchive,
    _PinnedFile,
    _SourceDescription,
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False,
    ).encode("utf-8") + b"\n"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(repo: Path, relative: str | Path, raw: bytes) -> Path:
    path = Path(repo) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _source_identity(files: dict[str, bytes], head: str) -> dict[str, Any]:
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    return {
        "head": head,
        "files": hashes,
        "identity": _sha(_canonical({"head": head, "files": hashes})),
    }


def _zip_source(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    return stream.getvalue()


@dataclass(frozen=True)
class SyntheticPreviousFailure:
    """V1 failed-attempt files and the pins needed by the real V2 reader."""

    repo: Path
    sources: _SourceDescription
    runner_path: Path
    decoy_runner_path: Path
    source_archive_path: Path
    source_file_list_path: Path
    report_path: Path
    build_record_path: Path
    source_identity: dict[str, Any]


def build_synthetic_previous_v1_failure(repo: Path) -> SyntheticPreviousFailure:
    """Build and authenticate a complete inert V1 failure source tree.

    The prior V1 runner is deliberately named ``curry-option-verification.exe``;
    a decoy ``curry-option-validation.exe`` is also written with different
    bytes.  The production reader must select the former.
    """
    repo = Path(repo).absolute()
    previous_root = repo / handoff.OUTPUT_RELATIVE
    artifact_dir = previous_root / "native-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    runner_path = artifact_dir / "curry-option-verification.exe"
    decoy_path = artifact_dir / "curry-option-validation.exe"
    runner_raw = b"synthetic prior verification runner; inert\n"
    decoy_raw = b"synthetic newer validation runner decoy; inert\n"
    runner_path.write_bytes(runner_raw)
    decoy_path.write_bytes(decoy_raw)

    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    archived_lock = (
        b"fn normal() {\n"
        b"    let _parent_view = verify_parent_request(&input, root)?;\n"
        b"    CurryOptionBatch::open_verification(root)?;\n"
        b"}\n"
    )
    archived_main = (
        b"fn main() {\n"
        b"    if let Err(error) = execute(&args) {\n"
        b"        eprintln!(\"{error}\");\n"
        b"        std::process::exit(2);\n"
        b"    }\n"
        b"}\n"
    )
    source_files = {
        lock_path: archived_lock,
        "crates/ygo-engine-adapter/examples/curry-option-verification.rs": archived_main,
        **{
            f"synthetic/archive-member-{index:03d}.bin":
            f"inert V1 archived source {index:03d}\n".encode("ascii")
            for index in range(546)
        },
    }
    if len(source_files) != 548:
        raise AssertionError(f"previous_source_count:{len(source_files)}")
    identity = _source_identity(source_files, "synthetic-handoff-v1-head")
    archive_raw = _zip_source(source_files)
    list_value = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": identity["head"],
        "source_identity": identity["identity"],
        "file_count": 548,
        "files": identity["files"],
    }
    list_raw = _canonical(list_value)
    archive_path = previous_root / handoff.SOURCE_ARCHIVE_RELATIVE
    list_path = previous_root / handoff.SOURCE_FILE_LIST_RELATIVE
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_raw)
    list_path.write_bytes(list_raw)

    report = handoff._report_template(identity, version=1)
    report["status"] = "failed"
    report["failure_checkpoint"] = "acceptance_delivery"
    report["diagnostic"] = "curry_handoff_acceptance_accounting_invalid"
    checkpoint_index = handoff.CHECK_NAMES.index("acceptance_delivery")
    report["checks"] = {
        name: ("passed" if index < checkpoint_index else
               "failed" if index == checkpoint_index else "not_run")
        for index, name in enumerate(handoff.CHECK_NAMES)
    }
    report_raw = _canonical(report)
    report_path = previous_root / handoff.REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(report_raw)

    build = {
        "kind": "build_record",
        "status": "recorded",
        "reproducible_build_proven": False,
        "source_before": identity,
        "source_after": identity,
        "artifacts": {
            "runner": _sha(runner_raw),
            "source_archive": _sha(archive_raw),
            "source_file_list": _sha(list_raw),
        },
    }
    build["identity"] = _sha(_canonical(build))
    build_raw = _canonical(build)
    build_path = previous_root / handoff.BUILD_RECORD_RELATIVE
    build_path.write_bytes(build_raw)

    child = _SourceDescription(
        role="previous_failed_attempt",
        files=(
            _PinnedFile("previous_v1_report", handoff.REPORT_RELATIVE.as_posix(), _sha(report_raw)),
            _PinnedFile("previous_v1_build_record", handoff.BUILD_RECORD_RELATIVE.as_posix(), _sha(build_raw)),
            _PinnedFile("previous_v1_runner", handoff.PREVIOUS_V1_RUNNER_RELATIVE.as_posix(), _sha(runner_raw)),
            _PinnedFile("previous_v1_source_archive", handoff.SOURCE_ARCHIVE_RELATIVE.as_posix(), _sha(archive_raw)),
            _PinnedFile("previous_v1_source_file_list", handoff.SOURCE_FILE_LIST_RELATIVE.as_posix(), _sha(list_raw)),
        ),
        dataset_counts=(("previous_source_file_count", 548),),
    )
    sources = _SourceDescription(role="root", children=(child,))

    # This is a direct read-only production-validator smoke.  It proves the
    # prior runner lookup resolves the verification binary and its source pin.
    verified = handoff._verify_previous_failed_attempt(repo, _sources=sources)
    selected = next(item for item in verified["inputs"] if item["role"] == "previous_v1_runner")
    if not selected["path"].endswith("/native-artifacts/curry-option-verification.exe"):
        raise AssertionError(f"wrong_previous_runner_selected:{selected['path']}")
    if selected["sha256"] != _sha(runner_raw) or selected["sha256"] == _sha(decoy_raw):
        raise AssertionError("previous_runner_pin_mismatch")

    return SyntheticPreviousFailure(
        repo, sources, runner_path, decoy_path, archive_path, list_path,
        report_path, build_path, identity,
    )


@dataclass(frozen=True)
class SyntheticLedgerHandoffTree:
    """Fixture namespace used by the complete public V2 audit test."""

    repo: Path
    sources: _SourceDescription
    previous: SyntheticPreviousFailure
    reservation_profile: Any
    reservation_spec: Any
    option_spec: Any
    candidate_spec: Any
    stage2_request_path: Path
    stage2_input_path: Path
    stage2_seal_path: Path
    ledger_path: Path
    stage2_receipt_path: Path
    construction_gaps: tuple[str, ...] = ()


def _build_validation_candidate_scope(repo: Path, *, baseline, asset_sources, static_sources):
    """Create an inert old validation manifest in a separate test-only root."""
    from ygo_eval import native_curry_option_validation as curry

    candidate_root_rel = Path("data/runtime/synthetic-curry-option-validation-candidate")
    candidate_root = repo / candidate_root_rel
    candidate_root.mkdir(parents=True, exist_ok=True)
    old_config_root = repo / curry.CURRY_SCOPE.output_root
    ordinary_config = candidate_root / "ordinary-candidate.toml"
    tournament_config = candidate_root / "tournament-candidate.toml"
    ordinary_config.write_bytes((old_config_root / ordinary_config.name).read_bytes())
    tournament_config.write_bytes((old_config_root / tournament_config.name).read_bytes())

    artifacts = candidate_root / "native-artifacts"
    artifacts.mkdir(exist_ok=True)
    runner, worker, cli = (
        artifacts / "curry-option-validation.exe",
        artifacts / "ygo-engine-worker.exe",
        artifacts / "ygo-cli.exe",
    )
    runner.write_bytes(b"synthetic old validation runner; inert\n")
    worker.write_bytes(b"synthetic old validation worker; inert\n")
    cli.write_bytes(b"synthetic old validation cli; inert\n")
    source_files = {
        "synthetic/candidate-validation-source.txt": b"synthetic candidate source\n",
    }
    source = _source_identity(source_files, "synthetic-curry-validation-head")
    source_archive = candidate_root / "source-native.zip"
    source_archive.write_bytes(_zip_source(source_files))
    source_file_list = candidate_root / "source-native-file-list.json"
    source_file_list.write_bytes(_canonical({
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": source["head"],
        "source_identity": source["identity"],
        "file_count": len(source_files),
        "files": source["files"],
    }))
    identity_path = candidate_root / "identity.json"
    identity_path.write_bytes(_canonical({"source": source, "consistent": True}))
    window_path = candidate_root / "window-start.json"
    window_path.write_bytes(_canonical({"started_at": 1_798_300_000}))
    build_unsigned = {
        "kind": "build_record",
        "status": "recorded",
        "reproducible_build_proven": False,
        "source_before": source,
        "source_after": source,
        "artifacts": {
            "runner": _sha(runner.read_bytes()),
            "worker": _sha(worker.read_bytes()),
            "cli": _sha(cli.read_bytes()),
        },
    }
    build_record = candidate_root / "build-record.json"
    build_record.write_bytes(_canonical({
        **build_unsigned, "identity": _sha(_canonical(build_unsigned)),
    }))

    candidate_spec = replace(
        curry.CURRY_SCOPE,
        output_root=candidate_root_rel,
        baseline_root=curry.OPTION_VERIFICATION_SCOPE.output_root,
        delivery_acceptance_sha256=_sha(baseline.acceptance_path.read_bytes()),
        delivery_sha256=_sha(baseline.delivery_path.read_bytes()),
        baseline_audit_sha256=asset_sources.file_sha256_role("asset_audit_audit"),
        candidate_config_root=candidate_root_rel,
    )
    paths = {
        "runner": runner,
        "worker": worker,
        "cli": cli,
        "build_record": build_record,
        "identity": identity_path,
        "window_start": window_path,
        "source_archive": source_archive,
        "source_file_list": source_file_list,
        "ordinary_config": ordinary_config,
        "tournament_config": tournament_config,
    }
    # The V3 source tree already contains the authentic static preparation
    # node; this verifier call extracts the objects from those pinned bytes.
    preparation = curry.verify_curry_preparation(
        repo=repo,
        preparation=repo / curry.PREPARATION_PATH,
        preparation_report=repo / curry.PREPARATION_REPORT_PATH,
        preparation_acceptance=repo / curry.PREPARATION_ACCEPTANCE_PATH,
        cases_path=repo / curry.FROZEN_CASES_PATH,
        operations_source=repo / "data/tmp/ocgcore-source/operations.cpp",
        _sources=static_sources,
    )
    banlist_relative = preparation["base_request_entry"].get("banlist_path", "")
    banlist_candidate = repo / banlist_relative
    if not banlist_candidate.exists():
        banlist_candidate.parent.mkdir(parents=True, exist_ok=True)
        banlist_candidate.write_bytes(b"synthetic banlist\n")
    banlist = repo / curry._resolve_curry_banlist_path(repo, banlist_relative)
    manifest_files = curry._curry_manifest_files(
        repo, candidate_root, paths, preparation, banlist, candidate_spec,
    )
    hashes, _raw_files = curry._capture_manifest_input_state(
        manifest_files,
        {"base_request": preparation["base_request"],
         "candidate_case": preparation["candidate_case"]},
    )
    acceptance_hash = _sha(baseline.acceptance_path.read_bytes())
    delivery_hash = _sha(baseline.delivery_path.read_bytes())
    audit_path = repo / "data/runtime/p1-curry-asset-binding-offline-2026-10-24/audit-report.json"
    candidate_input_pins = tuple(
            _PinnedFile(f"manifest_input_{role}", path.relative_to(repo).as_posix(), hashes[role])
            for role, path in manifest_files.items()
            if role not in {"base_request", "candidate_case"}
        ) + (
            _PinnedFile("validation_ordinary_config", ordinary_config.relative_to(repo).as_posix(), hashes["ordinary_config"]),
            _PinnedFile("validation_tournament_config", tournament_config.relative_to(repo).as_posix(), hashes["tournament_config"]),
            _PinnedFile("baseline_acceptance", baseline.acceptance_path.relative_to(repo).as_posix(), acceptance_hash),
            _PinnedFile("baseline_delivery", baseline.delivery_path.relative_to(repo).as_posix(), delivery_hash),
            _PinnedFile("baseline_audit", audit_path.relative_to(repo).as_posix(), asset_sources.file_sha256_role("asset_audit_audit")),
    )
    request = dict(preparation["stage1_request_template"])
    request.setdefault("engine", {})["worker_path"] = worker.relative_to(repo).as_posix()
    manifest = {
        "schema_version": 1,
        "kind": "native_curry_option_validation_manifest",
        "scope": candidate_spec.scope,
        "batch_kind": candidate_spec.batch_kind,
        "context": "0" * 64,
        "started_at": 1_798_300_000,
        "limit": candidate_spec.limit,
        "planned_calls": candidate_spec.limit,
        "wall_seconds": candidate_spec.wall_seconds,
        "old_consumed": candidate_spec.old_consumed,
        "baseline_acceptance_sha256": acceptance_hash,
        "baseline_delivery_sha256": delivery_hash,
        "input_sha256": hashes,
        "source": source,
        "historical_source_transition": curry.HISTORICAL_SOURCE_TRANSITION,
        "build": {"identity": json.loads(build_record.read_bytes())["identity"]},
        "assets": {"ordinary": {"consistent": True, "identity": "synthetic"}},
        "stage1_request_sha256": _sha(_canonical(request)),
        "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
        "request": request,
        **curry.FLAGS,
    }
    unsigned = {key: value for key, value in manifest.items() if key != "context"}
    manifest["context"] = _sha(_canonical(unsigned))
    manifest_raw = _pretty(manifest)
    manifest_path = _write(repo, candidate_root_rel / "research/manifest.json", manifest_raw)
    candidate_source_node = _SourceDescription(
        role="validation_candidate_scope",
        files=candidate_input_pins + (
            _PinnedFile("validation_manifest", manifest_path.relative_to(repo).as_posix(), _sha(manifest_raw)),
        ),
        semantic_hashes=(
            ("manifest_base_request", hashes["base_request"]),
            ("manifest_candidate_case", hashes["candidate_case"]),
        ),
    )
    sources = _SourceDescription(
        role="root", children=(candidate_source_node, asset_sources),
    )
    curry.validate_curry_report(
        manifest, repo=repo, spec=candidate_spec, _sources=sources,
    )
    return candidate_spec, candidate_source_node


def build_synthetic_handoff_tree(
    root: Path, *, stage1_stdout: bytes | Callable[[Any], bytes] | None = None,
) -> SyntheticLedgerHandoffTree:
    """Build all authenticated synthetic source nodes for the public V2 audit."""
    from tests.support import curry_reservation_v3_e2e as v3_e2e
    from ygo_eval import curry_ledger_handoff_audit as handoff

    root = Path(root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    v3 = v3_e2e.build_synthetic_v3_reservation_tree(root / "v3-reservation")
    # Reuse the V3 fixture's repo so every independently pinned source tree is
    # rooted in the same synthetic checkout used by the public V2 auditor.
    repo = v3.repo
    previous = build_synthetic_previous_v1_failure(repo)

    # A V3 real success report is needed for the option verification baseline.
    code, stdout, reservation_report_path = v3_e2e.invoke_v3_public_cli(v3)
    if code != 0:
        raise AssertionError(f"synthetic_v3_reservation_not_passed:{code}:{stdout}")
    v3_report = json.loads(reservation_report_path.read_bytes())
    if (v3_report.get("status") != "passed"
            or v3_report.get("planning_basis", {}).get("planned_total") != 39):
        raise AssertionError("synthetic_v3_reservation_contract_invalid")

    from tests.support.curry_handoff_v2_baseline_synthetic import (
        build_synthetic_dual_timepoint_baseline,
    )
    from tests.support.curry_option_verification_scope_synthetic import (
        build_synthetic_option_verification_scope,
    )
    from ygo_eval.curry_input_recovery_audit import _PinnedFile, _SourceDescription
    from ygo_eval.native_curry_option_validation import OPTION_VERIFICATION_SCOPE

    v3_acceptance_path = reservation_report_path.parent / "delivery/acceptance.json"
    v3_acceptance_path.parent.mkdir(parents=True, exist_ok=True)
    v3_acceptance = {
        "schema_version": 1,
        "kind": "curry_consumption_reservation_v3_delivery_acceptance",
        "status": "passed",
        "native_calls": 0,
        "execution_ready": False,
        "reservation_report_sha256": _sha(reservation_report_path.read_bytes()),
        "reservation": dict(v3_report["reservation"]),
        "old_scope": dict(v3_report["old_scope"]),
        "historical_ledgers": dict(v3_report["historical_ledgers"]),
        "planning_basis": dict(v3_report["planning_basis"]),
        "qualifications": dict(v3_report["qualifications"]),
        "verification": {"valid": True, "native_calls": 0},
    }
    v3_acceptance_path.write_bytes(_pretty(v3_acceptance))
    option_spec = replace(
        OPTION_VERIFICATION_SCOPE,
        reservation_sha256=_sha(reservation_report_path.read_bytes()),
        baseline_acceptance_sha256=_sha(v3_acceptance_path.read_bytes()),
        reservation_id=v3_report["reservation"]["reservation_id"],
    )
    reservation_node = _SourceDescription(
        role="reservation",
        files=(
            _PinnedFile("v3_reservation_report", reservation_report_path.relative_to(repo).as_posix(), _sha(reservation_report_path.read_bytes())),
            _PinnedFile("v3_reservation_acceptance", v3_acceptance_path.relative_to(repo).as_posix(), _sha(v3_acceptance_path.read_bytes())),
        ),
    )
    baseline = build_synthetic_dual_timepoint_baseline(repo)
    asset_sources = v3.base.fixture.sources.child("asset_audit")
    static_sources = v3.base.fixture.sources.child("static_preparation")
    candidate_spec, candidate_sources = _build_validation_candidate_scope(
        repo, baseline=baseline, asset_sources=asset_sources,
        static_sources=static_sources,
    )
    prior_sources = _SourceDescription(
        role="root", children=(reservation_node, candidate_sources, static_sources,
                               asset_sources),
    )
    resolved_stage1_stdout = (
        stage1_stdout(option_spec) if callable(stage1_stdout) else stage1_stdout
    )
    option = build_synthetic_option_verification_scope(
        repo, sources=prior_sources, spec=option_spec,
        stage1_stdout=resolved_stage1_stdout,
    )

    # The baseline's final acceptance is downstream of the frozen manifest.
    # Bind its preflight to the real synthetic manifest/prepared bytes, then
    # refresh the candidate manifest because it authenticates these baseline
    # acceptance and delivery files as inputs.
    option_manifest_raw = (option.research / "manifest.json").read_bytes()
    option_prepared_raw = (option.research / "prepared.json").read_bytes()
    final_acceptance = json.loads(baseline.acceptance_path.read_bytes())
    final_acceptance["preflight"] = {
        "context": option.manifest["context"],
        "manifest_sha256": _sha(option_manifest_raw),
        "prepared_sha256": _sha(option_prepared_raw),
        "prepared": True,
        "execution_ready_at_prepare": True,
        "passed": True,
        "native_calls": 0,
        "input_roles": 21,
    }
    baseline.acceptance_path.write_bytes(_pretty(final_acceptance))
    final_delivery = json.loads(baseline.delivery_path.read_bytes())
    final_delivery["acceptance"] = {
        "path": (handoff.BASELINE_RELATIVE / handoff.ACCEPTANCE_RELATIVE).as_posix(),
        "sha256": _sha(baseline.acceptance_path.read_bytes()),
        "bytes": baseline.acceptance_path.stat().st_size,
    }
    baseline.delivery_path.write_bytes(_pretty(final_delivery))
    candidate_spec, candidate_sources = _build_validation_candidate_scope(
        repo, baseline=baseline, asset_sources=asset_sources,
        static_sources=static_sources,
    )
    baseline_node = _SourceDescription(
        role="baseline",
        files=(
            _PinnedFile(
                "baseline_acceptance",
                baseline.acceptance_path.relative_to(repo).as_posix(),
                _sha(baseline.acceptance_path.read_bytes()),
            ),
            _PinnedFile(
                "baseline_delivery",
                baseline.delivery_path.relative_to(repo).as_posix(),
                _sha(baseline.delivery_path.read_bytes()),
            ),
        ),
        baseline_relative=OPTION_VERIFICATION_SCOPE.output_root.as_posix(),
    )
    baseline = replace(baseline, source_node=baseline_node)
    sources = _SourceDescription(
        role="root",
        children=(
            previous.sources.child("previous_failed_attempt"),
            baseline.source_node,
            reservation_node,
            candidate_sources,
            option.source_node,
            static_sources,
            asset_sources,
        ),
    )
    from ygo_eval.native_curry_option_validation import _verify_option_verification_baseline

    synthetic_collector = lambda _path: {
        "head": "synthetic-test-head",
        "files": {"synthetic": "0" * 64},
        "identity": "1" * 64,
    }
    _verify_option_verification_baseline(
        repo, repo / OPTION_VERIFICATION_SCOPE.baseline_root,
        _profile=v3.profile, _reservation_spec=v3.spec, _sources=sources,
        _option_spec=option_spec, _candidate_spec=candidate_spec,
        source_collector=synthetic_collector,
    )
    handoff._verify_previous_failed_attempt(repo, _sources=sources)
    acceptance, delivery, _, _ = handoff._verify_acceptance_delivery(
        repo / handoff.BASELINE_RELATIVE, _sources=sources,
    )
    handoff._verify_final_build_chain(
        repo, repo / handoff.BASELINE_RELATIVE, acceptance, delivery,
        _sources=sources,
    )
    research = option.research
    return SyntheticLedgerHandoffTree(
        repo=repo,
        sources=sources,
        previous=previous,
        reservation_profile=v3.profile,
        reservation_spec=v3.spec,
        option_spec=option_spec,
        candidate_spec=candidate_spec,
        stage2_request_path=research / "stage-2-request.json",
        stage2_input_path=research / "stage-2-input.json",
        stage2_seal_path=research / "stage-2-input-seal.json",
        ledger_path=option.ledger_path,
        stage2_receipt_path=option.stage2_receipt_path,
        construction_gaps=(),
    )
