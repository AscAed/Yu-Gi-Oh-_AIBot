"""Synthetic V3 source trees for the Curry saved-input audit.

All generated executables are inert.  The fixture reuses the already-authenticated
synthetic baseline and replaces only the prior-attempt source artifacts with the
distinct V1/V2 source shapes required by V3.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ygo_data.identity import canonical
from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval.curry_input_recovery_audit import _PinnedFile, _SourceDescription
from tests.support.curry_ledger_handoff_v2_e2e import build_synthetic_handoff_tree
from tests.support.curry_recovery_e2e import synthetic_source_identity


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pretty(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8") + b"\n"


def _source_identity(files: dict[str, bytes], head: str) -> dict[str, Any]:
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    return {"head": head, "files": hashes,
            "identity": _sha(canonical({"head": head, "files": hashes}))}


def _write_source_bundle(root: Path, files: dict[str, bytes], head: str):
    import io
    import zipfile

    root.mkdir(parents=True, exist_ok=True)
    source = _source_identity(files, head)
    archive_path = root / handoff.SOURCE_ARCHIVE_RELATIVE
    list_path = root / handoff.SOURCE_FILE_LIST_RELATIVE
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    listing = {
        "schema_version": 1, "kind": "workspace_source_archive",
        "head": head, "source_identity": source["identity"],
        "file_count": len(files), "files": source["files"],
    }
    list_path.write_bytes(_pretty(listing))
    return source, archive_path, list_path


def _write_build_record(root: Path, source: dict, runner_path: Path,
                        archive_path: Path, list_path: Path) -> Path:
    unsigned = {
        "kind": "build_record", "status": "recorded",
        "reproducible_build_proven": False,
        "source_before": source, "source_after": source,
        "artifacts": {
            "runner": _sha(runner_path.read_bytes()),
            "source_archive": _sha(archive_path.read_bytes()),
            "source_file_list": _sha(list_path.read_bytes()),
        },
    }
    path = root / handoff.BUILD_RECORD_RELATIVE
    path.write_bytes(_pretty({**unsigned, "identity": _sha(canonical(unsigned))}))
    return path


def _failure_checks(names: tuple[str, ...], checkpoint: str) -> dict[str, str]:
    index = names.index(checkpoint)
    return {name: ("passed" if position < index else
                   "failed" if position == index else "not_run")
            for position, name in enumerate(names)}


def _install_v1_audit_failure(repo: Path) -> _SourceDescription:
    root = repo / handoff.OUTPUT_RELATIVE
    root.mkdir(parents=True, exist_ok=True)
    runner = root / handoff.PREVIOUS_V1_RUNNER_RELATIVE_CORRECT
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_bytes(b"synthetic V1 audit runner; inert\n")
    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    python_path = "python/ygo_eval/curry_ledger_handoff_audit.py"
    repaired_rust = (
        b"fn verify_parent_request(...) -> Result<(), Error> {\n"
        b"    let view = open_readonly()?;\n"
        b"    validate_parent(&view)?;\n"
        b"    drop(view);\n"
        b"    Ok(())\n}\n"
    )
    mismatch_python = (
        b'def _verify_acceptance_delivery():\n'
        b'    expected_accounting = {\n'
        b'        "policy_reserve": 7,\n'
        b'    }\n'
        b'    _require(isinstance(accounting, dict)\n'
        b'             and all(type(accounting.get(key)) is int for key in (\n'
        b'                 "certified_historical_consumed", "policy_reserved",\n'
        b'             )), "curry_handoff_acceptance_accounting_invalid")\n'
    )
    files = {
        lock_path: repaired_rust,
        python_path: mismatch_python,
        **{f"synthetic/v1-member-{i:03d}.bin": b"inert V1 source\n" for i in range(546)},
    }
    source, archive, listing = _write_source_bundle(root, files, "synthetic-v1-audit-head")
    report = handoff._report_template(source, version=1)
    report.update({
        "status": "failed", "failure_checkpoint": "acceptance_delivery",
        "diagnostic": "curry_handoff_acceptance_accounting_invalid",
    })
    report["checks"] = _failure_checks(handoff.CHECK_NAMES, "acceptance_delivery")
    report_path = root / handoff.REPORT_RELATIVE
    report_path.write_bytes(_pretty(report))
    build = _write_build_record(root, source, runner, archive, listing)
    roles = (
        ("previous_v1_report", report_path),
        ("previous_v1_build_record", build),
        ("previous_v1_runner", runner),
        ("previous_v1_source_archive", archive),
        ("previous_v1_source_file_list", listing),
    )
    return _SourceDescription(
        role="previous_failed_attempt",
        files=tuple(_PinnedFile(role, path.relative_to(repo).as_posix(),
                                _sha(path.read_bytes())) for role, path in roles),
        dataset_counts=(("previous_source_file_count", 548),),
    )


def _install_v2_audit_failure(repo: Path) -> tuple[_SourceDescription, dict, bytes]:
    root = repo / handoff.V2_OUTPUT_RELATIVE
    root.mkdir(parents=True, exist_ok=True)
    runner = root / handoff.RUNNER_RELATIVE
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_bytes(b"synthetic V2 audit runner; inert\n")
    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    python_path = "python/ygo_eval/curry_ledger_handoff_audit.py"
    repaired_rust = (
        b"fn verify_parent_request(...) -> Result<(), Error> {\n"
        b"    let view = open_readonly()?;\n"
        b"    drop(view);\n"
        b"    Ok(())\n}\n"
    )
    wrong_v2_python = (
        b'PREVIOUS_V1_RUNNER_RELATIVE = Path("native-artifacts/curry-option-verification.exe")\n'
        b'return previous_root / PREVIOUS_V1_RUNNER_RELATIVE\n'
        b'_parent_view_crosses_exclusive_open(lock_source)\n'
        b'"curry_handoff_archived_parent_lock_cause_missing"\n'
    )
    files = {
        lock_path: repaired_rust, python_path: wrong_v2_python,
        "TASKS.md": b"synthetic base TASKS\n",
        "docs/INDEX.md": b"synthetic base INDEX\n",
        "docs/TESTING.md": b"synthetic base TESTING\n",
        **{f"synthetic/v2-member-{i:03d}.bin": b"inert V2 source\n" for i in range(552)},
    }
    source, archive, listing = _write_source_bundle(root, files, "synthetic-v2-audit-head")
    report = {
        "schema_version": 2, "kind": "curry_ledger_handoff_audit_v2",
        "status": "failed", "failure_checkpoint": "previous_failed_source",
        "diagnostic": "audit_failed",
        "checks": _failure_checks(handoff.V2_CHECK_NAMES, "previous_failed_source"),
        "native_calls": 0, "execution_ready": False,
        "tool_identity": handoff._source_summary(source),
    }
    report_path = root / handoff.REPORT_RELATIVE
    report_path.write_bytes(_pretty(report))
    build = _write_build_record(root, source, runner, archive, listing)
    roles = (
        ("previous_v2_report", report_path),
        ("previous_v2_build_record", build),
        ("previous_v2_runner", runner),
        ("previous_v2_source_archive", archive),
        ("previous_v2_source_file_list", listing),
    )
    node = _SourceDescription(
        role="previous_v2_failed_attempt",
        files=tuple(_PinnedFile(role, path.relative_to(repo).as_posix(),
                                _sha(path.read_bytes())) for role, path in roles),
        semantic_hashes=(("v2_source_identity", source["identity"]),),
        dataset_counts=(("previous_v2_source_file_count", 557),),
    )
    return node, source, report_path.read_bytes()


def _install_v2_final_source(repo: Path, *, v2_source: dict,
                             scope_ledger_path: Path) -> _SourceDescription:
    import zipfile

    root = repo / handoff.PREVIOUS_V2_FINAL_ROOT_RELATIVE
    source_root = repo / handoff.V2_OUTPUT_RELATIVE
    with zipfile.ZipFile(source_root / handoff.SOURCE_ARCHIVE_RELATIVE) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files.update({
        "TASKS.md": b"synthetic final TASKS\n",
        "docs/INDEX.md": b"synthetic final INDEX\n",
        "docs/TESTING.md": b"synthetic final TESTING\n",
    })
    added = handoff.ALLOWED_V2_SOURCE_DELTA["added"][0]
    files[added] = b"synthetic V2 handoff checkpoint\n"
    # Ensure the three changed documentation paths exist in the source tree.
    base_files = {
        name: raw for name, raw in files.items()
        if name not in {"TASKS.md", "docs/INDEX.md", "docs/TESTING.md", added}
    }
    base_files.update({
        "TASKS.md": b"synthetic base TASKS\n",
        "docs/INDEX.md": b"synthetic base INDEX\n",
        "docs/TESTING.md": b"synthetic base TESTING\n",
    })
    # The V2 archive must contain the pre-documentation versions; rewrite its
    # bundle and build binding before producing the final source release.
    v2_source_root = repo / handoff.V2_OUTPUT_RELATIVE
    _source, v2_archive_path, v2_list_path = _write_source_bundle(
        v2_source_root, base_files, v2_source["head"],
    )
    v2_source = _source
    v2_runner = v2_source_root / handoff.RUNNER_RELATIVE
    _write_build_record(v2_source_root, v2_source, v2_runner, v2_archive_path, v2_list_path)
    v2_report_path = v2_source_root / handoff.REPORT_RELATIVE
    v2_report = json.loads(v2_report_path.read_bytes())
    v2_report["tool_identity"] = handoff._source_summary(v2_source)
    v2_report_path.write_bytes(_pretty(v2_report))

    final_files = dict(base_files)
    final_files.update({
        "TASKS.md": b"synthetic final TASKS\n",
        "docs/INDEX.md": b"synthetic final INDEX\n",
        "docs/TESTING.md": b"synthetic final TESTING\n",
        added: b"synthetic V2 handoff checkpoint\n",
    })
    fixed_head = "8a6b2f6762131aebea6d8c0f5f61363d573f1b36"
    final_source, archive_path, list_path = _write_source_bundle(
        root, final_files, fixed_head,
    )
    release_path = root / "release-record.json"
    release = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_v2_final_source_release",
        "head": fixed_head,
        "source_identity": final_source["identity"],
        "file_count": 558,
        "source_archive": {"path": archive_path.name, "sha256": _sha(archive_path.read_bytes())},
        "source_file_list": {"path": list_path.name, "sha256": _sha(list_path.read_bytes())},
        "v2_report_sha256": _sha(v2_report_path.read_bytes()),
        "scope_ledger_sha256": _sha(scope_ledger_path.read_bytes()),
        "stage2_receipt_exists": False,
        "native_calls": 0, "execution_ready": False,
        "qualifications": handoff.QUALIFICATIONS,
    }
    release_path.write_bytes(_pretty(release))
    roles = (
        ("v2_final_release_record", release_path),
        ("v2_final_source_archive", archive_path),
        ("v2_final_source_file_list", list_path),
    )
    return _SourceDescription(
        role="v2_final_source",
        files=tuple(_PinnedFile(role, path.relative_to(repo).as_posix(),
                                _sha(path.read_bytes())) for role, path in roles),
        semantic_hashes=(
            ("v2_final_source_identity", final_source["identity"]),
            ("v2_final_source_head", fixed_head),
            ("scope_ledger_sha256", _sha(scope_ledger_path.read_bytes())),
        ),
    )


def build_synthetic_handoff_v3_tree(
    root: Path, *, stage1_stdout: bytes | Callable[[Any], bytes] | None = None,
):
    root = Path(root).absolute()
    tree = build_synthetic_handoff_tree(
        root / "base", stage1_stdout=stage1_stdout,
    )
    repo = tree.repo
    v1_node = _install_v1_audit_failure(repo)
    _v2_node_initial, v2_source, _v2_report_raw = _install_v2_audit_failure(repo)
    v2_final_node = _install_v2_final_source(
        repo, v2_source=v2_source, scope_ledger_path=tree.ledger_path,
    )
    # The final release builder regenerates the V2 source identity and report
    # bindings. Pin that final synthetic state in a new immutable node.
    v2_report_path = repo / handoff.V2_OUTPUT_RELATIVE / handoff.REPORT_RELATIVE
    v2_archive_path = repo / handoff.V2_OUTPUT_RELATIVE / handoff.SOURCE_ARCHIVE_RELATIVE
    v2_list_path = repo / handoff.V2_OUTPUT_RELATIVE / handoff.SOURCE_FILE_LIST_RELATIVE
    v2_build_path = repo / handoff.V2_OUTPUT_RELATIVE / handoff.BUILD_RECORD_RELATIVE
    v2_runner_path = repo / handoff.V2_OUTPUT_RELATIVE / handoff.RUNNER_RELATIVE
    v2_build = json.loads(v2_build_path.read_bytes())
    v2_source_identity = v2_build["source_before"]["identity"]
    v2_node = _SourceDescription(
        role="previous_v2_failed_attempt",
        files=tuple(_PinnedFile(role, path.relative_to(repo).as_posix(),
                                _sha(path.read_bytes())) for role, path in (
            ("previous_v2_report", v2_report_path),
            ("previous_v2_build_record", v2_build_path),
            ("previous_v2_runner", v2_runner_path),
            ("previous_v2_source_archive", v2_archive_path),
            ("previous_v2_source_file_list", v2_list_path),
        )),
        semantic_hashes=(("v2_source_identity", v2_source_identity),),
        dataset_counts=(("previous_v2_source_file_count", 557),),
    )
    retained = tuple(
        child for child in tree.sources.children
        if child.role not in {
            "previous_failed_attempt", "previous_v2_failed_attempt", "v2_final_source",
        }
    )
    sources = replace(
        tree.sources, children=retained + (v1_node, v2_node, v2_final_node),
    )
    return replace(tree, sources=sources)


def write_synthetic_v3_runner(repo: Path):
    """Write the current V3 audit runner bound to the synthetic repo identity."""
    root = repo / handoff.V3_OUTPUT_RELATIVE
    artifacts = root / "native-artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    runner = artifacts / handoff.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic V3 saved-input runner; inert\n")

    current_source = synthetic_source_identity(repo)
    current_files = {
        name: (repo / Path(name)).read_bytes()
        for name in current_source["files"]
    }
    source, archive_path, list_path = _write_source_bundle(
        root, current_files, current_source["head"],
    )
    if source != current_source:
        raise AssertionError("synthetic_v3_current_source_identity_mismatch")
    _write_build_record(root, source, runner, archive_path, list_path)
    return runner, source


def write_synthetic_previous_v3_source(repo: Path):
    """Write the fixed 563-member historical V3 source used by V4 fixtures."""
    root = repo / handoff.V3_OUTPUT_RELATIVE
    artifacts = root / "native-artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    runner = artifacts / handoff.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic V3 saved-input runner; inert\n")
    rust_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    python_path = "python/ygo_eval/native_curry_option_validation.py"
    source_files = {
        rust_path: (
            b"fn verify_parent_request(...) -> Result<(), Error> {\n"
            b"    let view = open_readonly()?;\n"
            b"    drop(view);\n"
            b"    Ok(())\n}\n"
        ),
        python_path: (
            b'output != {"successful": True, "native_calls": 1,\n'
            b'    "ledger": receipt.get("ledger")}\n'
            b'raise ValueError("curry_saved_stage_process_output_invalid")\n'
        ),
        "TASKS.md": b"synthetic base V3 TASKS\n",
        "docs/INDEX.md": b"synthetic base V3 INDEX\n",
        "docs/TESTING.md": b"synthetic base V3 TESTING\n",
        **{
            f"synthetic/v3-member-{index:03d}.bin": b"inert V3 source member\n"
            for index in range(558)
        },
    }
    if len(source_files) != 563:
        raise AssertionError(f"synthetic_v3_source_count:{len(source_files)}")
    source, archive_path, list_path = _write_source_bundle(
        root, source_files, "synthetic-v3-source-head",
    )
    _write_build_record(root, source, runner, archive_path, list_path)
    return runner, source


def install_synthetic_previous_v3_failure(
    repo: Path, *, baseline_sources: _SourceDescription | None = None,
) -> _SourceDescription:
    """Install a valid inert V3 prelaunch failure for a containing V4 test."""
    import zipfile

    root = Path(repo) / handoff.V3_OUTPUT_RELATIVE
    runner, source = write_synthetic_previous_v3_source(repo)
    report = handoff._report_template(source, version=3)
    if baseline_sources is not None:
        baseline = baseline_sources.child("baseline")
        report["anchors"] = {
            "acceptance_sha256": baseline.file_sha256_role("baseline_acceptance"),
            "delivery_sha256": baseline.file_sha256_role("baseline_delivery"),
        }
        prior = {
            "previous_failed_attempt": (
                baseline_sources.child("previous_failed_attempt"),
                "previous_v1_report", "previous_v1_build_record", "previous_v1_runner",
                "previous_v1_source_archive", "previous_v1_source_file_list",
            ),
            "previous_v2_failed_attempt": (
                baseline_sources.child("previous_v2_failed_attempt"),
                "previous_v2_report", "previous_v2_build_record", "previous_v2_runner",
                "previous_v2_source_archive", "previous_v2_source_file_list",
            ),
        }
        for field, (node, report_role, build_role, runner_role, archive_role, list_role) in prior.items():
            report[field] = {
                "report_sha256": node.file_sha256_role(report_role),
                "status": None,
                "failure_checkpoint": None,
                "diagnostic": None,
                "runner_sha256": None,
                "build_record_sha256": None,
                "source_archive_sha256": None,
                "source_file_list_sha256": None,
            }
        v2_final = baseline_sources.child("v2_final_source")
        report["v2_final_source"] = {
            "release_record_sha256": v2_final.file_sha256_role("v2_final_release_record"),
            "source_archive_sha256": v2_final.file_sha256_role("v2_final_source_archive"),
            "source_file_list_sha256": v2_final.file_sha256_role("v2_final_source_file_list"),
            "source_identity": v2_final.semantic_sha256("v2_final_source_identity"),
            "file_count": 558,
            "source_delta": handoff.ALLOWED_V2_SOURCE_DELTA,
        }
    checkpoint = "stage1_parent_receipt"
    checkpoint_index = handoff.V3_CHECK_NAMES.index(checkpoint)
    report.update({
        "status": "failed",
        "failure_checkpoint": checkpoint,
        "diagnostic": "curry_saved_stage_process_output_invalid",
        "checks": {
            name: ("passed" if index < checkpoint_index else
                   "failed" if index == checkpoint_index else "not_run")
            for index, name in enumerate(handoff.V3_CHECK_NAMES)
        },
    })
    report["stability"]["stage2_receipt_absent_before"] = True
    report["stability"]["stage2_receipt_absent_after"] = True
    report["stability_rechecks"]["stage2_receipt_absent"] = True
    report_raw = _pretty(report)
    report_path = root / handoff.REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(report_raw)
    if not handoff.validate_report(
        report, repo=Path(repo), _sources=baseline_sources,
    ):
        raise AssertionError("synthetic_previous_v3_failure_report_invalid")

    archive_path = root / handoff.SOURCE_ARCHIVE_RELATIVE
    listing_path = root / handoff.SOURCE_FILE_LIST_RELATIVE
    with zipfile.ZipFile(archive_path) as archive:
        source_files = {name: archive.read(name) for name in archive.namelist()}
    if len(source_files) != 563:
        raise AssertionError(f"synthetic_previous_v3_source_count:{len(source_files)}")
    changed_docs = {
        "TASKS.md": b"synthetic final V3 TASKS\n",
        "docs/INDEX.md": b"synthetic final V3 INDEX\n",
        "docs/TESTING.md": b"synthetic final V3 TESTING\n",
    }
    added_path = handoff.V4_ALLOWED_SOURCE_DELTA["added"][0]
    final_files = dict(source_files)
    final_files.update(changed_docs)
    final_files[added_path] = b"synthetic V3 handoff checkpoint\n"
    final_root = root / "final-build"
    final_source, final_archive, final_listing = _write_source_bundle(
        final_root, final_files, source["head"],
    )
    final_delivery = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_v3_final_delivery",
        "status": "failed_before_saved_input_audit",
        "audit_report": {
            "path": "audit-report.json",
            "sha256": _sha(report_raw),
            "bytes": len(report_raw),
        },
        "runner_process_attempted": False,
        "stage2_receipt_absent": True,
        "qualifications": handoff.QUALIFICATIONS,
        "audit_time_source": {
            "identity": source["identity"],
            "file_count": 563,
            "runner_sha256": _sha(runner.read_bytes()),
            "build_record_sha256": _sha(
                (root / handoff.BUILD_RECORD_RELATIVE).read_bytes()
            ),
        },
        "final_document_source": {
            "identity": final_source["identity"],
            "file_count": 564,
            "source_archive": "final-build/source-native.zip",
            "source_archive_sha256": _sha(final_archive.read_bytes()),
            "source_file_list": "final-build/source-native-file-list.json",
            "source_file_list_sha256": _sha(final_listing.read_bytes()),
            "source_delta": handoff.V4_ALLOWED_SOURCE_DELTA,
        },
    }
    delivery_path = final_root / "delivery.json"
    delivery_path.write_bytes(_pretty(final_delivery))

    roles = (
        ("previous_v3_report", report_path),
        ("previous_v3_build_record", root / handoff.BUILD_RECORD_RELATIVE),
        ("previous_v3_runner", runner),
        ("previous_v3_source_archive", archive_path),
        ("previous_v3_source_file_list", listing_path),
        ("previous_v3_final_delivery", delivery_path),
        ("previous_v3_final_source_archive", final_archive),
        ("previous_v3_final_source_file_list", final_listing),
    )
    node = _SourceDescription(
        role="previous_v3_failed_source",
        files=tuple(
            _PinnedFile(role, path.relative_to(repo).as_posix(),
                        _sha(path.read_bytes()))
            for role, path in roles
        ),
        semantic_hashes=(
            ("previous_v3_source_identity", source["identity"]),
            ("previous_v3_final_source_identity", final_source["identity"]),
        ),
        dataset_counts=(("previous_v3_source_file_count", 563),
                        ("previous_v3_final_file_count", 564)),
    )
    return node


def write_synthetic_v4_runner(repo: Path):
    """Write the V4 test runner and its inert build-source artifacts."""
    root = Path(repo) / handoff.V4_OUTPUT_RELATIVE
    artifacts = root / "native-artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    runner = artifacts / handoff.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic V4 saved-input runner; inert\n")
    source = synthetic_source_identity(repo)
    archive_path, list_path = root / handoff.SOURCE_ARCHIVE_RELATIVE, root / handoff.SOURCE_FILE_LIST_RELATIVE
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    import zipfile
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, digest in sorted(source["files"].items()):
            raw = (repo / Path(name)).read_bytes()
            if _sha(raw) != digest:
                raise AssertionError("synthetic_source_changed_during_v4_archive")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    list_path.write_bytes(_pretty({
        "schema_version": 1, "kind": "workspace_source_archive",
        "head": source["head"], "source_identity": source["identity"],
        "file_count": len(source["files"]), "files": source["files"],
    }))
    _write_build_record(root, source, runner, archive_path, list_path)
    return runner, source
