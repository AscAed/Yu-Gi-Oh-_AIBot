"""Synthetic artifacts for the current Curry option-verification scope.

All bytes written by this module are inert test data.  It does not start a
runner/worker, read the user's runtime evidence, or create a real journal.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from ygo_data.identity import canonical
from ygo_eval import native_curry_option_validation as curry
from ygo_eval.curry_input_recovery_audit import _PinnedFile, _SourceDescription
from ygo_eval.native_tenki_placement_validation import (
    _diagnostic_hash as _placement_diagnostic_hash,
    _stage_invocation,
)
from tests.support.curry_recovery_e2e import (
    _synthetic_generic_ledger,
    _synthetic_static_preparation,
)
from tests.support.curry_handoff_v2_baseline_synthetic import build_synthetic_native_build
from tests.test_native_curry_option_validation import _receipt as _validation_receipt


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, value: Any) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


@dataclass(frozen=True)
class SyntheticOptionVerificationScope:
    repo: Path
    root: Path
    research: Path
    context: str
    manifest: dict[str, Any]
    prepared: dict[str, Any]
    stage1_receipt: dict[str, Any]
    stage2_request: dict[str, Any]
    stage2_input: dict[str, Any]
    ledger_path: Path
    stage2_receipt_path: Path
    source_node: _SourceDescription
    static_preparation_node: _SourceDescription
    all_sources: _SourceDescription
    native_source: dict[str, Any]


def build_synthetic_option_verification_scope(
    repo: Path,
    *,
    sources: Any | None = None,
    spec: Any | None = None,
    stage1_stdout: bytes | None = None,
) -> SyntheticOptionVerificationScope:
    """Build the scope's inert files in ``repo`` and return their source pins.

    ``repo`` must already contain the synthetic V3 reservation and static
    preparation fixture.  Existing files are reused as read-only source data;
    this helper only writes within ``OPTION_VERIFICATION_SCOPE.output_root``.
    """
    repo = Path(repo).resolve()
    spec = spec or curry.OPTION_VERIFICATION_SCOPE
    fixed = curry.OPTION_VERIFICATION_SCOPE
    fixed_fields = (
        "scope", "output_root", "baseline_root", "limit", "wall_seconds",
        "worker_timeout_seconds", "batch_kind", "input_seal_kind", "runner_role",
        "report_prefix", "candidate_config_root",
        "reservation_policy_id", "certified_historical_consumed", "policy_reserved",
        "planning_base", "reservation_relative", "acceptance_relative",
    )
    if any(getattr(spec, name) != getattr(fixed, name) for name in fixed_fields):
        raise ValueError("synthetic_option_verification_spec_scope_invalid")
    root = repo / spec.output_root
    research = root / "research"
    artifacts = root / "native-artifacts"
    process_dir = root / "process-diagnostics"
    started_at = 1_798_300_000

    inherited_children: tuple[_SourceDescription, ...] = ()
    if sources is not None:
        if not isinstance(sources, _SourceDescription):
            raise TypeError("synthetic_source_description_required")
        inherited_children = (
            sources.children if sources.role == "root" else (sources,)
        )
    inherited_by_role = {child.role: child for child in inherited_children}
    if len(inherited_by_role) != len(inherited_children):
        raise ValueError("synthetic_source_description_child_role_collision")

    # Build the fixed source layer from inert, test-owned bytes.  The helper
    # uses the same frozen case contract as the public audit without reading
    # the user's runtime evidence or local card assets.
    static_node = inherited_by_role.get("static_preparation")
    if static_node is None:
        static_node = _synthetic_static_preparation(repo)
    static_files = {
        "preparation": repo / curry.PREPARATION_PATH,
        "preparation_report": repo / curry.PREPARATION_REPORT_PATH,
        "preparation_acceptance": repo / curry.PREPARATION_ACCEPTANCE_PATH,
        "operations_source": repo / "data/tmp/ocgcore-source/operations.cpp",
        "adapter_codec": repo / curry.HISTORICAL_SOURCE_TRANSITION["path"],
        "frozen_cases": repo / curry.FROZEN_CASES_PATH,
    }
    for path in static_files.values():
        if not path.is_file():
            raise FileNotFoundError(f"synthetic_static_source_missing:{path.name}")
    # Read the prepared objects using the same extractor as production.
    preparation_doc = curry.strict_json(static_files["preparation"].read_bytes())
    cases_doc = curry.strict_json((repo / curry.FROZEN_CASES_PATH).read_bytes())
    candidate_entry = next(
        item for item in preparation_doc.get("candidates", [])
        if item.get("case", {}).get("case_id") == "prompt-14-curry-v1"
    )
    candidate = candidate_entry["case"]
    base = next(
        item for item in cases_doc.get("cases", [])
        if item.get("case", {}).get("case_id") == "rabbit"
    )
    base_request = base["request"]
    # The builder already returned the production-shaped source pins; add no
    # verifier-produced state to that description.
    preparation = curry.verify_curry_preparation(
        repo=repo,
        preparation=static_files["preparation"],
        preparation_report=static_files["preparation_report"],
        preparation_acceptance=static_files["preparation_acceptance"],
        cases_path=repo / curry.FROZEN_CASES_PATH,
        operations_source=static_files["operations_source"],
        _sources=static_node,
    )

    root.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    process_dir.mkdir(parents=True, exist_ok=True)
    # Baseline role files: these must already be generated by the V3 fixture.
    ordinary_cfg = spec.candidate_config_root
    if ordinary_cfg is None:
        raise AssertionError("verification_scope_config_root_missing")
    candidate_config_root = repo / ordinary_cfg
    candidate_configs = (
        candidate_config_root / "ordinary-candidate.toml",
        candidate_config_root / "tournament-candidate.toml",
    )
    if not all(path.is_file() for path in candidate_configs):
        raise FileNotFoundError("synthetic_candidate_configs_missing")

    # Share the exact 544-member native source/build with the enclosing V2
    # baseline fixture; those bytes are inert and never executed.
    native_source = build_synthetic_native_build(repo)
    runner = native_source["artifact_paths"]["runner"]
    worker = native_source["artifact_paths"]["worker"]
    cli = native_source["artifact_paths"]["cli"]
    from ygo_eval.native_tenki_placement import _candidate_configs
    generated_configs = _candidate_configs(
        repo, root, worker, candidate_config_root,
    )
    ordinary_config = generated_configs["ordinary"]
    tournament_config = generated_configs["tournament"]
    identity_path = root / "identity.json"
    window_path = root / "window-start.json"
    _write(window_path, {"started_at": started_at, "synthetic": True})
    archive_path = native_source["archive_path"]
    file_list_path = native_source["file_list_path"]
    source_identity = native_source["source_identity"]
    source = {"head": native_source["head"], "files": native_source["files"],
              "identity": source_identity}
    build_record_path = root / "build-record.json"
    artifacts_info = native_source["artifacts"]
    runtime_roles = {
        "worker": {"sha256": _sha(worker.read_bytes())},
        "dll": {"sha256": preparation["stage1_request_template"]["versions"]["engine_sha256"]},
        "cdb": {"sha256": preparation["stage1_request_template"]["versions"]["cdb_sha256"]},
        "script_manifest": {"sha256": preparation["stage1_request_template"]["versions"]["scripts_sha256"]},
    }
    runtime = {"consistent": True, "roles": runtime_roles}
    runtime["identity"] = _sha(canonical(runtime))
    identity_unsigned = {
        "schema_version": 1,
        "kind": "workspace_identity",
        "consistent": True,
        "source": source,
        "build_provenance": "unverified",
        "reproducible_build_proven": False,
        "cli_sha256": _sha(cli.read_bytes()),
        "runtimes": {"ordinary": runtime, "tournament": runtime},
    }
    identity = {**identity_unsigned,
                "identity": _sha(canonical(identity_unsigned))}
    _write(identity_path, identity)
    build_unsigned = curry.strict_json(build_record_path.read_bytes())

    base_request = preparation["base_request"]
    candidate_case = preparation["candidate_case"]
    # Input path map is obtained from the production role mapper. Candidate
    # request uses the frozen prepared template, with only inert worker path.
    request = dict(preparation["stage1_request_template"])
    request.setdefault("engine", {})["worker_path"] = str(worker.relative_to(repo))
    ordinary_identity = runtime
    tournament_identity = runtime

    paths = {"runner": runner, "worker": worker, "cli": cli,
             "build_record": build_record_path, "identity": identity_path,
             "window_start": window_path, "source_archive": archive_path,
             "source_file_list": file_list_path,
             "ordinary_config": ordinary_config,
             "tournament_config": tournament_config}
    banlist_relative = preparation["base_request_entry"].get("banlist_path", "")
    banlist_candidate = repo / banlist_relative
    if not banlist_candidate.exists():
        _write(banlist_candidate, b"synthetic banlist\n")
    banlist_path = repo / curry._resolve_curry_banlist_path(
        repo, banlist_relative
    )
    paths_map = curry._curry_manifest_files(repo, root, paths, preparation,
                                            banlist_path, spec)
    hashes, raw_protected = curry._capture_manifest_input_state(
        paths_map, {"base_request": base_request, "candidate_case": candidate_case}
    )
    # Source node binds each physical input and the two semantic case objects.
    scope_node = _SourceDescription(
        role="option_verification_scope",
        files=tuple(
            _PinnedFile(role=("baseline_acceptance" if role == "baseline_acceptance"
                              else "consumption_reservation" if role == "consumption_reservation"
                              else f"manifest_input_{role}"),
                        relative_path=path.relative_to(repo).as_posix(),
                        sha256=hashes[role])
            for role, path in paths_map.items()
            if role not in {"base_request", "candidate_case"}
        ),
        semantic_hashes=(
            ("manifest_base_request", hashes["base_request"]),
            ("manifest_candidate_case", hashes["candidate_case"]),
        ),
    )
    child_roles = [child.role for child in inherited_children]
    if len(child_roles) != len(set(child_roles)):
        raise ValueError("synthetic_source_description_child_role_collision")
    if "option_verification_scope" in child_roles:
        raise ValueError(
            "synthetic_source_description_child_already_present:option_verification_scope"
        )
    combined_sources = _SourceDescription(
        role="root", children=(*inherited_children, scope_node,
                                *((static_node,) if "static_preparation" not in child_roles
                                  else ())),
    )
    context_unsigned = {
        "schema_version": 1,
        "kind": curry._report_kind(spec, "manifest"),
        "scope": spec.scope,
        "batch_kind": spec.batch_kind,
        "started_at": started_at,
        "limit": spec.limit,
        "planned_calls": 7,
        "wall_seconds": spec.wall_seconds,
        "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
        "historical_source_transition": curry.HISTORICAL_SOURCE_TRANSITION,
        **curry._verification_manifest_fields(spec),
        "baseline_acceptance_sha256": spec.baseline_acceptance_sha256,
        "source": source,
        "build": {"record_path": str(build_record_path.relative_to(repo)),
                  "record_sha256": _sha(build_record_path.read_bytes()),
                  "identity": build_unsigned["identity"],
                  "artifacts": artifacts_info},
        "source_archive": {"path": str(archive_path.relative_to(repo)),
                           "sha256": _sha(archive_path.read_bytes()),
                           "file_list_path": str(file_list_path.relative_to(repo)),
                           "file_list_sha256": _sha(file_list_path.read_bytes()),
                           "file_count": native_source["file_count"],
                           "source_identity": source_identity},
        "assets": {
            "ordinary": ordinary_identity,
            "tournament": tournament_identity,
            "identity_sha256": identity["identity"],
            "execution_role": "ordinary",
        },
        "request": request,
        "stage1_request_sha256": _sha(canonical(request)),
        "input_sha256": hashes,
        **curry.FLAGS,
    }
    context = _sha(canonical(context_unsigned))
    manifest = {**context_unsigned, "context": context}
    curry.validate_curry_report(manifest, repo=repo, spec=spec,
                                _sources=combined_sources)

    research.mkdir(parents=True, exist_ok=True)
    _write(research / "stage-1-request.json", request)
    request_hash = _sha(canonical(request))
    stage1_input = _stage_invocation(context, research, 1, request,
                                     ordinary_identity, started_at, spec)
    stage1_input_raw = _write(research / "stage-1-input.json", stage1_input)
    stage1_seal = {"schema_version": 1, "kind": spec.input_seal_kind,
                   "context": context, "stage": 1,
                   "input_sha256": _sha(stage1_input_raw)}
    _write(research / "stage-1-input-seal.json", stage1_seal)
    receipt = _validation_receipt(1, request)
    receipt.update({
        "kind": curry._report_kind(spec, "stage"), "scope": spec.scope,
        "context": context, "assets_before": ordinary_identity,
        "assets_after": ordinary_identity,
    })
    receipt_raw = _write(research / "stage-1.json", receipt)
    ledger_path = research / "calls.jsonl"
    _synthetic_generic_ledger(ledger_path, spec.scope, context, 1, spec.limit,
                              "option-verification-stage1")
    ledger_stats = {"consumed": 1, "completed": 1, "unknown": 0,
                    "reserved": 0, "abandoned": 0, "limit": spec.limit}
    diagnostic_record = _write_process_diagnostic(
        repo, root, spec, 1, successful=True,
        ledger=ledger_stats,
        stdout_override=stage1_stdout,
    )
    diag_hash = _placement_diagnostic_hash(root, diagnostic_record, spec)
    stage1_report = {
        "schema_version": 1, "kind": curry._report_kind(spec, "stage_report"),
        "scope": spec.scope, "context": context, "stage": 1,
        "successful": True, "native_calls": 1, "diagnostic": None,
        "receipt_sha256": _sha(receipt_raw), "diagnostic_sha256": diag_hash,
        "independent_replay_matches": None, "ledger": ledger_stats,
        **curry.FLAGS,
    }
    _write(research / "stage-1-report.json", stage1_report)

    stage2_request = curry.derive_curry_stage_request(2, receipt, spec)
    stage2_raw = _write(research / "stage-2-request.json", stage2_request)
    stage2_input = _stage_invocation(context, research, 2, stage2_request,
                                     ordinary_identity, started_at, spec)
    stage2_input_raw = _write(research / "stage-2-input.json", stage2_input)
    stage2_seal = {"schema_version": 1, "kind": spec.input_seal_kind,
                   "context": context, "stage": 2,
                   "input_sha256": _sha(stage2_input_raw)}
    _write(research / "stage-2-input-seal.json", stage2_seal)
    stage2_diagnostic = _write_process_diagnostic(
        repo, root, spec, 2, successful=False,
        ledger=ledger_stats,
    )
    stage2_diag_hash = _placement_diagnostic_hash(root, stage2_diagnostic, spec)
    stage2_report = {
        "schema_version": 1, "kind": curry._report_kind(spec, "stage_report"),
        "scope": spec.scope, "context": context, "stage": 2,
        "successful": False, "native_calls": 0,
        "diagnostic": "runner_output_invalid_or_nonzero",
        "receipt_sha256": None, "diagnostic_sha256": stage2_diag_hash,
        "independent_replay_matches": None, "ledger": ledger_stats,
        **curry.FLAGS,
    }
    _write(research / "stage-2-report.json", stage2_report)
    stage_summaries = [{key: report.get(key) for key in (
        "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
        "diagnostic_sha256", "independent_replay_matches", "ledger",
    )} for report in (stage1_report, stage2_report)]
    summary = curry.summarize_curry_validation(
        context, stage_summaries, ledger_stats, spec=spec,
    )
    _write(research / "summary.json", summary)
    _write(research / "manifest.json", manifest)
    prepared = {
        "schema_version": 1, "kind": curry._report_kind(spec, "prepared"),
        "scope": spec.scope, "batch_kind": spec.batch_kind,
        "context": context,
        "manifest_sha256": _sha((research / "manifest.json").read_bytes()),
        "stage1_request_sha256": request_hash,
        "stage1_input_sha256": _sha(stage1_input_raw),
        "preflight_diagnostic_sha256": "e" * 64,
        "prepared": True, "execution_ready": True, "native_calls": 0,
        "planned_calls": 7, **curry.FLAGS,
    }
    _write(research / "prepared.json", prepared)
    return SyntheticOptionVerificationScope(
        repo=repo, root=root, research=research, context=context,
        manifest=manifest, prepared=prepared, stage1_receipt=receipt,
        stage2_request=stage2_request, stage2_input=stage2_input,
        ledger_path=ledger_path,
        stage2_receipt_path=research / "stage-2.json",
        source_node=scope_node,
        static_preparation_node=static_node,
        all_sources=combined_sources,
        native_source=native_source,
    )


def _write_process_diagnostic(
    repo, root, spec, stage, *, successful, ledger, stdout_override: bytes | None = None,
):
    from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic

    stdout = stdout_override
    if stdout is None:
        stdout = json.dumps({"successful": successful,
                             "native_calls": 1 if successful else 0,
                             "ledger": ledger}, separators=(",", ":")).encode()
    stderr = b"" if successful else b"synthetic nonzero runner output\n"
    completed = subprocess.CompletedProcess(
        ["synthetic-inert-runner"], 0 if successful else 2, stdout, stderr,
    )
    record, _ = capture_process_diagnostic(
        ["synthetic-inert-runner"], cwd=repo, evidence_root=root,
        mode="normal", timeout=1,
        runner=lambda *_args, **_kwargs: completed,
        runner_role=spec.runner_role,
    )
    # capture_process_diagnostic writes the signed-by-hashes metadata and raw
    # stdout/stderr under root/process-diagnostics. The stage sidecar is kept
    # at the production location consumed by saved-stage verification.
    _write(root / f"stage-{stage}-process-diagnostic.json", record)
    return record


def _read_pretty_or_raw(path: Path) -> bytes:
    return path.read_bytes()
