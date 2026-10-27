"""Synthetic dual-timepoint Curry handoff baseline material.

This module writes only inert test-owned bytes.  It is intended to be composed
with the V3 reservation and option-verification fixtures by tests exercising
the real handoff acceptance and source-bundle validators.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import zipfile
from typing import Any

from ygo_data.identity import canonical
from ygo_eval import curry_ledger_handoff_audit as handoff
from ygo_eval.curry_input_recovery_audit import _PinnedFile, _SourceDescription
from ygo_eval.native_curry_option_validation import (
    OPTION_VERIFICATION_SCOPE,
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any, *, canonical_form: bool = False) -> bytes:
    if canonical_form:
        return canonical(value)
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2,
    ).encode("utf-8") + b"\n"


def _write(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _source_identity(files: dict[str, bytes], head: str) -> tuple[str, dict[str, str]]:
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    return _sha(canonical({"head": head, "files": hashes})), hashes


def _write_source_pair(
    archive_path: Path,
    list_path: Path,
    files: dict[str, bytes],
    *,
    head: str,
) -> dict[str, Any]:
    identity, hashes = _source_identity(files, head)
    listing = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "file_count": len(files),
        "head": head,
        "files": hashes,
        "source_identity": identity,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    archive_raw = buffer.getvalue()
    list_raw = _json_bytes(listing)
    _write(archive_path, archive_raw)
    _write(list_path, list_raw)
    return {
        "source_identity": identity,
        "file_count": len(files),
        "head": head,
        "files": hashes,
        "archive_path": archive_path,
        "archive_sha256": _sha(archive_raw),
        "archive_bytes": len(archive_raw),
        "file_list_path": list_path,
        "file_list_sha256": _sha(list_raw),
        "file_list_bytes": len(list_raw),
    }


def _build_record(source: dict[str, Any], artifacts: dict[str, str]) -> bytes:
    unsigned = {
        "schema_version": 1,
        "kind": "build_record",
        "status": "recorded",
        "reproducible_build_proven": False,
        "command": ["synthetic-inert-build-record"],
        "toolchain": {"name": "synthetic", "version": "0"},
        "source_before": {
            "head": source["head"],
            "identity": source["source_identity"],
            "files": source["files"],
        },
        "source_after": {
            "head": source["head"],
            "identity": source["source_identity"],
            "files": source["files"],
        },
        "artifacts": artifacts,
    }
    return _json_bytes({**unsigned, "identity": _sha(canonical(unsigned))})


def _parent_lock_source() -> bytes:
    # Static inert Rust text that exercises the verifier's ordering predicate.
    return (
        b"fn run_normal(input: &Input, root: &Path) -> Result<()> {\n"
        b"    let _parent_view = verify_parent_request(&input, root)?;\n"
        b"    let batch = CurryOptionBatch::open_verification(root)?;\n"
        b"    Ok(())\n"
        b"}\n"
        b"fn main() {\n"
        b"    if let Err(error) = execute(&args) {\n"
        b"        eprintln!(\"{error}\");\n"
        b"        std::process::exit(2);\n"
        b"    }\n"
        b"}\n"
    )


def _synthetic_native_source_files() -> dict[str, bytes]:
    lock_path = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
    native_files: dict[str, bytes] = {
        lock_path: _parent_lock_source(),
        "crates/ygo-engine-adapter/src/codec.rs": b"// synthetic codec source\n",
        "TASKS.md": b"synthetic native tasks snapshot\n",
        "docs/INDEX.md": b"synthetic native index snapshot\n",
        "docs/TESTING.md": b"synthetic native testing snapshot\n",
    }
    native_files.update({
        f"synthetic/native-{index:04d}.bin": b"inert synthetic native source member\n"
        for index in range(539)
    })
    if len(native_files) != 544:
        raise AssertionError(f"synthetic_native_source_count:{len(native_files)}")
    return native_files


def build_synthetic_native_build(repo: Path) -> dict[str, Any]:
    """Create the 544-member frozen native bundle before manifest creation."""
    repo = Path(repo).resolve()
    native_root = repo / OPTION_VERIFICATION_SCOPE.output_root
    native_files = _synthetic_native_source_files()
    native_source = _write_source_pair(
        native_root / "source-native.zip",
        native_root / "source-native-file-list.json",
        native_files,
        head="synthetic-native-head",
    )
    artifact_bytes = {
        "cli": ("ygo-cli.exe", b"synthetic inert native cli\n"),
        "runner": ("curry-option-verification.exe", b"synthetic inert native runner\n"),
        "worker": ("ygo-engine-worker.exe", b"synthetic inert native worker\n"),
    }
    artifacts: dict[str, str] = {}
    artifact_paths: dict[str, Path] = {}
    for role, (name, raw) in artifact_bytes.items():
        path = native_root / "native-artifacts" / name
        _write(path, raw)
        artifacts[role] = _sha(raw)
        artifact_paths[role] = path
    build_path = native_root / "build-record.json"
    build_raw = _build_record(native_source, artifacts)
    _write(build_path, build_raw)
    return {
        **native_source,
        "root": native_root,
        "build_record_path": build_path,
        "build_record_sha256": _sha(build_raw),
        "build_record_bytes": len(build_raw),
        "artifacts": artifacts,
        "artifact_paths": artifact_paths,
    }


@dataclass(frozen=True)
class SyntheticDualTimepointBaseline:
    repo: Path
    baseline_root: Path
    native_root: Path
    acceptance_path: Path
    delivery_path: Path
    native_build_record_path: Path
    native_archive_path: Path
    native_file_list_path: Path
    final_build_root: Path
    source_node: _SourceDescription
    native_source: dict[str, Any]
    final_source: dict[str, Any]


def build_synthetic_dual_timepoint_baseline(
    repo: Path,
    *,
    native_source: dict[str, Any] | None = None,
) -> SyntheticDualTimepointBaseline:
    """Build the 544/545 native/final source bundles and their pinned contract.

    The resulting acceptance and delivery are intentionally synthetic but use
    the field names and invariant values consumed by the production
    ``_verify_acceptance_delivery`` and ``_verify_final_build_chain`` routines.
    The caller should place this in a fresh synthetic repository, then call
    those validators with ``source_node`` in a parent source description.
    """
    repo = Path(repo).resolve()
    baseline_root = repo / OPTION_VERIFICATION_SCOPE.output_root
    final_build_root = baseline_root / "final-build"
    native_root = repo / OPTION_VERIFICATION_SCOPE.output_root
    final_artifacts_root = final_build_root / "native-artifacts"
    native_source = native_source or build_synthetic_native_build(repo)
    native_files = _synthetic_native_source_files()
    expected_native_hashes = {
        name: _sha(raw) for name, raw in sorted(native_files.items())
    }
    if (native_source.get("root") != native_root
            or native_source.get("file_count") != 544
            or native_source.get("files") != expected_native_hashes):
        raise ValueError("synthetic_native_build_metadata_invalid")

    final_files = dict(native_files)
    final_files.update({
        "TASKS.md": b"synthetic final tasks snapshot\n",
        "docs/INDEX.md": b"synthetic final index snapshot\n",
        "docs/TESTING.md": b"synthetic final testing snapshot\n",
        "docs/superpowers/plans/2026-10-25-curry-option-verification-handoff.md": (
            b"synthetic handoff plan\n"
        ),
    })
    if len(final_files) != 545:
        raise AssertionError(f"synthetic_final_source_count:{len(final_files)}")

    native_archive_path = native_source["archive_path"]
    native_file_list_path = native_source["file_list_path"]
    native_build_record_path = native_source["build_record_path"]

    final_archive_path = final_build_root / "source-native.zip"
    final_file_list_path = final_build_root / "source-native-file-list.json"
    final_source = _write_source_pair(
        final_archive_path, final_file_list_path, final_files,
        head="synthetic-final-head",
    )
    final_artifact_bytes = {
        "cli": ("ygo-cli.exe", b"synthetic inert final cli\n"),
        "runner": ("curry-option-validation.exe", b"synthetic inert final runner\n"),
        "worker": ("ygo-engine-worker.exe", b"synthetic inert final worker\n"),
    }
    final_artifacts: dict[str, str] = {}
    artifact_rows: list[dict[str, Any]] = []
    for role, (name, raw) in final_artifact_bytes.items():
        path = final_artifacts_root / name
        _write(path, raw)
        digest = _sha(raw)
        final_artifacts[role] = digest
        artifact_rows.append({
            "path": f"native-artifacts/{name}",
            "sha256": digest,
            "bytes": len(raw),
        })
    final_build_record_path = final_build_root / "build-record.json"
    final_build_raw = _build_record(final_source, final_artifacts)
    _write(final_build_record_path, final_build_raw)

    delta = {
        "added": ["docs/superpowers/plans/2026-10-25-curry-option-verification-handoff.md"],
        "removed": [],
        "changed": ["TASKS.md", "docs/INDEX.md", "docs/TESTING.md"],
    }
    acceptance = {
        "schema_version": 1,
        "kind": "curry_option_verification_final_acceptance",
        "status": "partial_failed",
        "scope": {
            "id": OPTION_VERIFICATION_SCOPE.scope,
            "limit": 7,
            "wall_seconds": 7200,
            "worker_timeout_ms": 30000,
            "execution_order": "serial",
        },
        "accounting": {
            "certified_historical_consumed": 32,
            "policy_reserve": 7,
            "planning_base": 39,
            "new_consumed": 1,
            "certified_consumed_including_new": 33,
            "planning_total": 40,
            "unknown": 0,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
        },
        "native_result": {
            "stage_1": {"passed": True, "charged": True},
            "stage_2": {
                "passed": False, "charged": False, "runner_return_code": 2,
                "diagnostic": "runner_output_invalid_or_nonzero",
            },
            "native_calls_total": 1,
            "unknown_consumption": 0,
        },
        "source_and_build": {
            "native_time": {
                "build_record_sha256": native_source["build_record_sha256"],
                "source_identity": native_source["source_identity"],
                "file_count": 544,
                "source_archive_sha256": native_source["archive_sha256"],
                "source_file_list_sha256": native_source["file_list_sha256"],
            },
            "final_after_docs": {
                "build_record_identity": json.loads(final_build_raw)["identity"],
                "build_record_sha256": _sha(final_build_raw),
                "source_identity": final_source["source_identity"],
                "file_count": 545,
                "source_archive_sha256": final_source["archive_sha256"],
                "source_file_list_sha256": final_source["file_list_sha256"],
                "source_delta_vs_native": delta,
            },
        },
        "preflight": {
            "manifest_sha256": "0" * 64,
            "prepared_sha256": "0" * 64,
            "prepared": True,
            "execution_ready_at_prepare": True,
            "passed": True,
            "native_calls": 0,
            "input_roles": 21,
            "context": "0" * 64,
        },
        "qualifications": dict(handoff.QUALIFICATIONS),
    }
    acceptance_raw = _json_bytes(acceptance)
    acceptance_path = _write(final_build_root / "acceptance.json", acceptance_raw)
    delivery = {
        "schema_version": 1,
        "kind": "curry_option_verification_delivery",
        "scope": OPTION_VERIFICATION_SCOPE.scope,
        "status": "partial_failed",
        "acceptance": {
            "path": (OPTION_VERIFICATION_SCOPE.output_root / "final-build/acceptance.json").as_posix(),
            "sha256": _sha(acceptance_raw),
            "bytes": len(acceptance_raw),
        },
        "final_build": {
            "record": {
                "path": "build-record.json",
                "sha256": _sha(final_build_raw),
                "bytes": len(final_build_raw),
            },
            "source_archive": {
                "path": "source-native.zip",
                "sha256": final_source["archive_sha256"],
                "bytes": final_source["archive_bytes"],
            },
            "source_file_list": {
                "path": "source-native-file-list.json",
                "sha256": final_source["file_list_sha256"],
                "bytes": final_source["file_list_bytes"],
            },
            "artifacts": artifact_rows,
        },
        "qualifications": dict(handoff.QUALIFICATIONS),
    }
    delivery_raw = _json_bytes(delivery)
    delivery_path = _write(final_build_root / "delivery.json", delivery_raw)

    baseline_source = _SourceDescription(
        role="baseline",
        files=(
            _PinnedFile("baseline_acceptance", acceptance_path.relative_to(repo).as_posix(), _sha(acceptance_raw)),
            _PinnedFile("baseline_delivery", delivery_path.relative_to(repo).as_posix(), _sha(delivery_raw)),
        ),
        baseline_relative=OPTION_VERIFICATION_SCOPE.output_root.as_posix(),
    )
    return SyntheticDualTimepointBaseline(
        repo=repo,
        baseline_root=baseline_root,
        native_root=native_root,
        acceptance_path=acceptance_path,
        delivery_path=delivery_path,
        native_build_record_path=native_build_record_path,
        native_archive_path=native_archive_path,
        native_file_list_path=native_file_list_path,
        final_build_root=final_build_root,
        source_node=baseline_source,
        native_source=native_source,
        final_source=final_source,
    )


def verify_synthetic_dual_timepoint_baseline(
    fixture: SyntheticDualTimepointBaseline,
) -> dict[str, Any]:
    """Exercise the production acceptance and dual-timepoint validators."""
    acceptance, delivery, acceptance_raw, delivery_raw = handoff._verify_acceptance_delivery(
        fixture.baseline_root,
        _sources=_SourceDescription(
            role="root",
            children=(fixture.source_node,),
        ),
    )
    dual = handoff._verify_final_build_chain(
        fixture.repo,
        fixture.baseline_root,
        acceptance,
        delivery,
    )
    return {
        "acceptance": acceptance,
        "delivery": delivery,
        "acceptance_sha256": _sha(acceptance_raw),
        "delivery_sha256": _sha(delivery_raw),
        "dual_timepoint": dual,
    }
