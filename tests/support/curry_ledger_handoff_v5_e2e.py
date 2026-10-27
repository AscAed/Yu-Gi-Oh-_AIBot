"""Synthetic source tree for the fixed Curry ledger handoff V5 audit."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval.curry_input_recovery_audit import _PinnedFile, _SourceDescription
from tests.support.curry_ledger_handoff_v3_e2e import (
    _pretty,
    _source_identity,
    _write_build_record,
    _write_source_bundle,
)
from tests.support.curry_ledger_handoff_v4_e2e import build_synthetic_handoff_v4_tree


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def install_synthetic_previous_v4_failure(repo: Path, sources: _SourceDescription):
    """Create the authentic failed-report shape with inert 568/569 source pins."""
    repo = Path(repo)
    root = repo / handoff.V4_OUTPUT_RELATIVE
    root.mkdir(parents=True, exist_ok=False)
    runner = root / "native-artifacts/curry-option-validation.exe"
    runner.parent.mkdir(parents=True, exist_ok=False)
    runner_raw = b"synthetic V4 audit runner; inert\n"
    runner.write_bytes(runner_raw)

    base_files = {
        "crates/ygo-engine-adapter/examples/curry-option-validation.rs": (
            b"fn verify_parent_request(...) -> Result<(), Error> { drop(view); Ok(()) }\n"
        ),
        "TASKS.md": b"V4 source TASKS\n",
        "docs/INDEX.md": b"V4 source INDEX\n",
        "docs/TESTING.md": b"V4 source TESTING\n",
        **{
            f"synthetic/v4-member-{index:03d}.bin": b"inert V4 source member\n"
            for index in range(564)
        },
    }
    if len(base_files) != 568:
        raise AssertionError(f"synthetic_v4_native_count:{len(base_files)}")
    native, archive, listing = _write_source_bundle(
        root, base_files, "synthetic-v4-native-head",
    )
    _write_build_record(root, native, runner, archive, listing)

    report = handoff._report_template(native, version=4, _sources=sources)
    checkpoint = "previous_v3_failed_source"
    index = handoff.V4_CHECK_NAMES.index(checkpoint)
    report.update({
        "status": "failed",
        "failure_checkpoint": checkpoint,
        "diagnostic": "curry_handoff_build_root_contents_invalid",
        "tool_identity": None,
        "checks": {
            name: ("passed" if i < index else "failed" if i == index else "not_run")
            for i, name in enumerate(handoff.V4_CHECK_NAMES)
        },
        "inputs": [],
    })
    report_path = root / handoff.REPORT_RELATIVE
    report_path.write_bytes(_pretty(report))
    (root / "build-target").mkdir()
    (root / "build-command.json").write_text("{}\n", encoding="utf-8")
    (root / "final-build").mkdir()

    final_files = dict(base_files)
    final_files.update({
        "TASKS.md": b"V4 final TASKS\n",
        "docs/INDEX.md": b"V4 final INDEX\n",
        "docs/TESTING.md": b"V4 final TESTING\n",
        handoff.V5_ALLOWED_SOURCE_DELTA["added"][0]: b"V4 handoff checkpoint\n",
    })
    final_identity, final_archive, final_listing = _write_source_bundle(
        root / "final-build", final_files, "synthetic-v4-final-head",
    )
    final_archive_path = final_archive.with_name("source-final.zip")
    final_listing_path = final_listing.with_name("source-final-file-list.json")
    final_archive.replace(final_archive_path)
    final_listing.replace(final_listing_path)
    final_archive = final_archive_path
    final_listing = final_listing_path
    delivery = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_v4_final_delivery",
        "audit_time": {
            "report_path": "../audit-report.json",
            "report_sha256": _sha(report_path.read_bytes()),
            "status": "failed",
            "failure_checkpoint": "previous_v3_failed_source",
            "diagnostic": "curry_handoff_build_root_contents_invalid",
            "native_calls": 0,
            "runner_process_attempted": False,
            "runner_started": False,
        },
        "source_after_docs": {
            "identity": final_identity["identity"],
            "head": final_identity["head"],
            "file_count": 569,
        },
        "source_archive": {
            "archive_path": "source-final.zip",
            "archive_sha256": _sha(final_archive.read_bytes()),
            "file_list_path": "source-final-file-list.json",
            "file_list_sha256": _sha(final_listing.read_bytes()),
            "file_count": 569,
        },
        "audit_build": {
            "build_record_path": "../build-record.json",
            "build_record_sha256": _sha((root / handoff.BUILD_RECORD_RELATIVE).read_bytes()),
            "runner_path": "../native-artifacts/curry-option-validation.exe",
            "runner_sha256": _sha(runner.read_bytes()),
            "runner_executed": False,
        },
    }
    delivery_path = root / "final-build/delivery-final.json"
    delivery_path.write_bytes(_pretty(delivery))

    roles = (
        ("previous_v4_report", report_path),
        ("previous_v4_build_record", root / handoff.BUILD_RECORD_RELATIVE),
        ("previous_v4_runner", runner),
        ("previous_v4_source_archive", archive),
        ("previous_v4_source_file_list", listing),
        ("previous_v4_final_delivery", delivery_path),
        ("previous_v4_final_source_archive", final_archive),
        ("previous_v4_final_source_file_list", final_listing),
    )
    node = _SourceDescription(
        role="previous_v4_failed_source",
        files=tuple(
            _PinnedFile(role, path.relative_to(repo).as_posix(), _sha(path.read_bytes()))
            for role, path in roles
        ),
        semantic_hashes=(
            ("previous_v4_final_source_identity", final_identity["identity"]),
            ("previous_v4_final_source_head", final_identity["head"]),
        ),
    )
    return node


def build_synthetic_handoff_v5_tree(root: Path):
    tree = build_synthetic_handoff_v4_tree(Path(root) / "v4-base")
    node = install_synthetic_previous_v4_failure(tree.repo, tree.sources)
    sources = replace(tree.sources, children=(*tree.sources.children, node))
    return replace(tree, sources=sources)


def write_synthetic_v5_runner(repo: Path):
    """Write an inert runner and build bundle satisfying the fixed source gate."""
    from tests.support.curry_ledger_handoff_v3_e2e import (
        _source_identity as source_identity,
        _write_source_bundle as write_source_bundle,
        _write_build_record as write_build_record,
    )
    from tests.support.curry_recovery_e2e import synthetic_source_identity

    root = repo / handoff.V5_OUTPUT_RELATIVE
    artifacts = root / "native-artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    runner = artifacts / handoff.RUNNER_RELATIVE.name
    runner.write_bytes(b"synthetic V5 saved-input runner; inert\n")
    current = synthetic_source_identity(repo)
    files = {name: (repo / name).read_bytes() for name in current["files"]}
    source, archive, listing = write_source_bundle(root, files, current["head"])
    if source != current:
        raise AssertionError("synthetic_v5_source_identity_mismatch")
    write_build_record(root, source, runner, archive, listing)
    return runner, source
