"""Read-only audit of the frozen Curry failure and its repaired runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import zipfile
from typing import Any, Callable

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source
from ygo_eval.prompt_probe_prepare import require, safe_path, strict_json
from ygo_eval.terminal_regression import immutable_write


BASELINE_RELATIVE = Path("data/runtime/p1-curry-option-validation-native-2026-10-23")
OUTPUT_RELATIVE = Path("data/runtime/p1-curry-asset-binding-offline-2026-10-24")
RUNNER_ROLE = "curry_asset_binding_audit_runner"
PREFLIGHT_TIMEOUT_SECONDS = 900
HISTORICAL_CONSUMED = 32
HISTORICAL_UNKNOWN = 0
HISTORICAL_LEDGER_COUNT = 9
OLD_SCOPE = "curry-option-validation-v1"
ORIGINAL_DIAGNOSTIC = "curry_asset_identity_mismatch"
STORED_SUMMARY_DIAGNOSTIC = "curry_preflight_output_mismatch"
RUST_SOURCE_RELATIVE = Path("crates/ygo-engine-adapter/examples/curry-option-validation.rs")
ALLOWED_ARCHIVE_DIFFS = {
    "TASKS.md",
    "docs/TESTING.md",
    "docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md",
}
HASH_ANCHORS = {
    "final_build_record": "0101d9a46855189b50878e4fef6d4fecf5e0b279a6ad88f6171230fcfbd4ab41",
    "native_build_record": "9bef7b74baac4a502ad94b1296ade61a081c233f027963329dc22b102ad17626",
    "manifest": "b170c35ff48fb4c22892ecffd15324cc7ecc5dfe318a7f1668b0f448756641c3",
    "prepared": "3ba3e920a0721c462e0ec3401a509b8e037a7c65a48b0a67c1dd8fc6aeb5a2b8",
    "summary": "37a1bf1dab01305bed38d35d398594f112e67290c97c92379673002c06b8361a",
}
ARCHIVE_ANCHORS = {
    "native_time": {
        "archive_sha256": "d8b31b838f0b559adc513159a2e8135fd6ecaf2fab0c42897e3f8ebd6fc99582",
        "file_list_sha256": "4c64d44dba562aa9f1ac8d133d63f56b9b0b6e4d02a826e144767477116cf04b",
        "source_identity": "29205c8ef0b98b07b3003a64baa6c7dede5e03391cf7e245b59905e0b2341028",
        "file_count": 494,
    },
    "final": {
        "archive_sha256": "14694d78192a2e8725394aafc3cfca6b260c214f8fd6862fa5cc1249037f5565",
        "file_list_sha256": "ad184ad31fff4a71677c552247dbc8e088625185249cc806b38aca4e1bedcda8",
        "source_identity": "1dd6c895cc013add3b51dd5945d63ce3fa9c3da08b81ce512f569d690e7bc3ea",
        "file_count": 495,
    },
}
FROZEN_FILES = {
    "stage1_request": "f93f938c4fc3d147beb8663405a7457a2ef61ddd8b8bd67697f4cd4918af9c78",
    "stage1_input": "f2e981bf36f7f1ec25aa532943d2ebcb6e4ae60f76c850d198410f66b76acd1b",
    "stage1_seal": "d3b0872139c083211c55ddfaf2ef74f308ad4e42d38a3ea96040605f8d5f1581",
    "identity": "85fedb2b3a964a2fedb535e9120fdb21c79506a89480cbb7e9f4238b104a060c",
    "window_start": "b5bdbf5a3856b42c85b027f7f4dbf5fb09c4ced96d677ff64189f6ec7a6b4419",
}
ORIGINAL_PROCESS_FILES = {
    "metadata": "c27c545e6b7487e4a934ca7dc2a4ed08c598914bd13d1e98b74671920ce38910",
    "stdout": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "stderr": "a3b70cf9e917d6791789e9f3933c92cf6d5ba9bf9c62c02f056bc5c8533f0672",
}
OLD_NATIVE_SOURCE_IDENTITY = ARCHIVE_ANCHORS["native_time"]["source_identity"]
FINAL_SOURCE_IDENTITY = ARCHIVE_ANCHORS["final"]["source_identity"]
RESEARCH_FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
CHECK_NAMES = (
    "static_root_cause",
    "historical_sources",
    "old_curry_material",
    "historical_ledgers",
    "isolated_runner_build",
    "read_only_preflight",
    "trace",
    "input_stability",
    "old_material_protection",
)
TRACE_EVENTS = (
    ("input_validation", "start"),
    ("input_validation", "end"),
    ("shared_preflight", "start"),
    ("shared_preflight", "end"),
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    for name in ("baseline-dir", "runner", "build-record", "output"):
        parser.add_argument("--" + name, type=Path, required=True)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, expected: str | None = None) -> tuple[bytes, str]:
    raw = safe_path(path).read_bytes()
    found = _sha(raw)
    require(expected is None or found == expected, "pinned_input_hash_mismatch")
    return raw, found


def validate_anchor_hashes(value: dict[str, str]) -> bool:
    """Reject any missing, extra, or changed fixed baseline anchor."""
    require(isinstance(value, dict) and value == HASH_ANCHORS, "curry_anchor_set_mismatch")
    return True


def _safe_error(error: BaseException) -> str:
    value = str(error)
    return value if re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value) else "offline_audit_failed"


def _record_input(repo: Path, role: str, path: Path, protected: dict[Path, str], expected: str | None = None) -> dict:
    absolute = _absolute(path)
    try:
        relative = absolute.relative_to(repo).as_posix()
    except ValueError:
        raise ValueError("audit_input_outside_repository") from None
    raw, found = _read(absolute, expected)
    previous = protected.get(absolute)
    require(previous is None or previous == found, "protected_input_binding_conflict")
    protected[absolute] = found
    return {"role": role, "path": relative, "sha256": found, "bytes": len(raw)}


def _asset_scope_sources(sources: Any | None) -> Any | None:
    """Select the immutable descriptor for this audit's own Curry baseline."""
    if sources is None:
        return None
    role = getattr(sources, "role", None)
    if role == "asset_audit_scope":
        return sources
    if role == "asset_audit":
        return sources.child("asset_audit_scope")
    if role == "confirmation":
        return sources.child("asset_audit").child("asset_audit_scope")
    raise ValueError("asset_audit_source_scope_missing")


def _asset_audit_root_sources(sources: Any | None) -> Any | None:
    """Select the immutable source node describing this audit's own inputs."""
    if sources is None:
        return None
    role = getattr(sources, "role", None)
    if role == "asset_audit":
        return sources
    if role == "confirmation":
        return sources.child("asset_audit")
    if role == "asset_audit_scope":
        return None
    raise ValueError("asset_audit_source_root_missing")


def _source_anchor_hashes(sources: Any | None) -> dict[str, str]:
    """Return old Curry material anchors from the supplied immutable source tree."""
    scope_sources = _asset_scope_sources(sources)
    if scope_sources is None:
        return dict(HASH_ANCHORS)
    baseline = Path(scope_sources.baseline_relative)
    paths = {
        "final_build_record": "final-build/build-record.json",
        "native_build_record": "build-record.json",
        "manifest": "research/manifest.json",
        "prepared": "research/prepared.json",
        "summary": "research/summary.json",
    }
    return {
        role: scope_sources.file_sha256((baseline / relative).as_posix())
        for role, relative in paths.items()
    }


def _source_archive_record(scope_sources: Any, report_role: str) -> Any:
    source_role = {
        "native_time": "curry_native_archive",
        "final": "curry_final_archive",
    }.get(report_role)
    if source_role is None:
        raise ValueError("source_archive_role_invalid")
    return scope_sources.archive(source_role)


def _source_archive_report_matches(scope_sources: Any, report_archives: list[dict]) -> bool:
    by_role = {item.get("role"): item for item in report_archives if isinstance(item, dict)}
    if len(by_role) != len(report_archives):
        return False
    for report_role in ("native_time", "final"):
        pin = _source_archive_record(scope_sources, report_role)
        record = by_role.get(report_role)
        if not isinstance(record, dict) or any(
            record.get(report_key) != getattr(pin, pin_key)
            for report_key, pin_key in (
                ("sha256", "archive_sha256"),
                ("file_list_sha256", "file_list_sha256"),
                ("source_identity", "source_identity"),
                ("file_count", "file_count"),
            )
        ):
            return False
    return set(by_role) == {"native_time", "final"}


def _validate_report_source_pins(report: dict, sources: Any) -> None:
    scope_sources = _asset_scope_sources(sources)
    root_sources = _asset_audit_root_sources(sources)
    require(report.get("anchors") == _source_anchor_hashes(sources), "audit_anchor_set_invalid")

    source = report.get("source")
    require(isinstance(source, dict), "audit_source_invalid")
    if root_sources is not None:
        if report.get("status") == "passed":
            require(
                all(key in source for key in (
                    "workspace_identity", "workspace_file_count", "historical_consumed",
                    "historical_unknown", "ledger_count", "source_archive_differences", "old_builds",
                )),
                "audit_source_pins_missing",
            )
        if "workspace_identity" in source:
            require(
                source["workspace_identity"]
                == root_sources.archive("asset_audit_native_archive").source_identity,
                "audit_workspace_identity_mismatch",
            )
        if "workspace_file_count" in source:
            require(
                source["workspace_file_count"]
                == root_sources.dataset_count("asset_audit_source_files"),
                "audit_workspace_file_count_mismatch",
            )
        for report_key, count_key in (
            ("historical_consumed", "historical_consumed"),
            ("historical_unknown", "historical_unknown"),
            ("ledger_count", "historical_ledgers"),
        ):
            if report_key in source:
                require(
                    source[report_key] == root_sources.dataset_count(count_key),
                    "audit_source_history_count_mismatch",
                )
        if report.get("history") is not None:
            expected_history = {
                "consumed": root_sources.dataset_count("historical_consumed"),
                "unknown": root_sources.dataset_count("historical_unknown"),
                "ledger_count": root_sources.dataset_count("historical_ledgers"),
            }
            require(
                all(report["history"].get(key) == value for key, value in expected_history.items()),
                "historical_totals_claim_invalid",
            )
        if report.get("protection") is not None:
            require(
                report["protection"].get("file_count")
                == root_sources.dataset_count("asset_audit_protected_files"),
                "audit_protection_count_mismatch",
            )
        checks = report.get("checks", {})
        if report.get("status") == "passed":
            require(
                len(report.get("inputs", [])) == root_sources.dataset_count("asset_audit_inputs"),
                "audit_input_count_mismatch",
            )
            historical_inputs = [
                item for item in report.get("inputs", [])
                if isinstance(item, dict) and item.get("role", "").startswith("historical_material_")
            ]
            require(
                len(historical_inputs) == root_sources.dataset_count("historical_material_inputs"),
                "audit_historical_material_input_count_mismatch",
            )

    if source.get("source_archive_differences") is not None:
        require(
            source["source_archive_differences"]
            == list(scope_sources.differences("curry_baseline")),
            "audit_source_archive_differences_mismatch",
        )
    if report.get("source_archives"):
        require(
            _source_archive_report_matches(scope_sources, report["source_archives"]),
            "audit_source_archive_pins_mismatch",
        )
    old_builds = source.get("old_builds")
    if old_builds or report.get("status") == "passed":
        require(isinstance(old_builds, list), "audit_old_builds_invalid")
        expected_roles = {"native_time", "final"}
        by_role = {item.get("role"): item for item in old_builds if isinstance(item, dict)}
        require(len(by_role) == len(old_builds) and set(by_role) == expected_roles, "audit_old_builds_invalid")
        for role, build_path, artifact_prefix, archive_role in (
            ("native_time", "build-record.json", "native-artifacts", "curry_native_archive"),
            ("final", "final-build/build-record.json", "final-build/native-artifacts", "curry_final_archive"),
        ):
            record = by_role[role]
            archive = _source_archive_record(scope_sources, role)
            expected_artifacts = {
                "cli": scope_sources.file_sha256((Path(scope_sources.baseline_relative) / artifact_prefix / "ygo-cli.exe").as_posix()),
                "runner": scope_sources.file_sha256((Path(scope_sources.baseline_relative) / artifact_prefix / "curry-option-validation.exe").as_posix()),
                "worker": scope_sources.file_sha256((Path(scope_sources.baseline_relative) / artifact_prefix / "ygo-engine-worker.exe").as_posix()),
            }
            require(
                record.get("source_identity") == archive.source_identity
                and record.get("build_record_sha256")
                == scope_sources.file_sha256((Path(scope_sources.baseline_relative) / build_path).as_posix())
                and record.get("artifact_sha256") == expected_artifacts,
                "audit_old_build_source_pin_mismatch",
            )


def _source_file_sha256(sources: Any | None, relative_path: str, fallback: str) -> str:
    return sources.file_sha256(relative_path) if sources is not None else fallback


def _source_dataset_count(sources: Any | None, name: str, fallback: int) -> int:
    return sources.dataset_count(name) if sources is not None else fallback


def _source_relative_path(repo: Path, relative: str, *, file: bool = True) -> Path:
    value = Path(relative)
    require(
        isinstance(relative, str) and relative and not value.is_absolute()
        and "\\" not in relative and ":" not in relative and ".." not in value.parts,
        "asset_audit_source_path_invalid",
    )
    return safe_path(repo / value, file=file)


def _source_optional_file_path(repo: Path, relative: str) -> Path:
    """Resolve an optional file only beneath an existing safe parent directory."""
    require(
        isinstance(relative, str) and relative and "\\" not in relative
        and ":" not in relative and ".." not in Path(relative).parts
        and not Path(relative).is_absolute() and Path(relative).name not in ("", ".", ".."),
        "asset_audit_source_path_invalid",
    )
    value = Path(relative)
    parent = _source_relative_path(repo, value.parent.as_posix(), file=False)
    candidate = parent / value.name
    require(not candidate.is_symlink(), "asset_audit_source_path_invalid")
    return candidate


def _verify_signed_build(value: Any) -> None:
    require(isinstance(value, dict) and value.get("kind") == "build_record", "build_record_kind_mismatch")
    unsigned = {key: item for key, item in value.items() if key != "identity"}
    require(value.get("identity") == digest(canonical(unsigned)), "build_record_signature_invalid")


def _verify_archive(
    root: Path,
    archive_relative: str,
    file_list_relative: str,
    expected: dict[str, Any],
) -> tuple[dict[str, str], dict]:
    """Verify every archive member against its independently hashed source list."""
    archive_path = safe_path(root / archive_relative)
    list_path = safe_path(root / file_list_relative)
    list_raw, list_hash = _read(list_path, expected["file_list_sha256"])
    archive_raw, archive_hash = _read(archive_path, expected["archive_sha256"])
    listing = strict_json(list_raw)
    files = listing.get("files") if isinstance(listing, dict) else None
    require(
        isinstance(files, dict)
        and listing.get("kind") == "workspace_source_archive"
        and listing.get("schema_version") == 1
        and listing.get("head") == expected.get("head", "8a6b2f6762131aebea6d8c0f5f61363d573f1b36")
        and listing.get("file_count") == expected["file_count"]
        and len(files) == expected["file_count"]
        and listing.get("source_identity") == expected["source_identity"],
        "source_archive_file_list_mismatch",
    )
    source_unsigned = {"head": listing["head"], "files": files}
    require(digest(canonical(source_unsigned)) == expected["source_identity"], "source_archive_identity_mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        require(len(members) == len(set(members)) and set(members) == set(files), "source_archive_membership_mismatch")
        for name, member_hash in files.items():
            member_path = Path(name)
            require(not member_path.is_absolute() and ".." not in member_path.parts and "\\" not in name, "source_archive_member_path_invalid")
            require(isinstance(member_hash, str) and re.fullmatch(r"[a-f0-9]{64}", member_hash) is not None, "source_archive_member_hash_invalid")
            require(_sha(archive.read(name)) == member_hash, "source_archive_member_hash_mismatch")
    record = {
        "role": expected.get(
            "report_role",
            "final" if "final-build" in Path(archive_relative).parts else "native_time",
        ),
        "sha256": archive_hash,
        "file_list_sha256": list_hash,
        "source_identity": expected["source_identity"],
        "file_count": expected["file_count"],
        "bytes": len(archive_raw),
    }
    return files, record


def _snapshot_tree(root: Path) -> dict[str, dict[str, Any]]:
    root = safe_path(root, file=False)
    snapshot: dict[str, dict[str, Any]] = {}
    for item in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        if item.is_dir():
            safe_path(item, file=False)
            snapshot[item.relative_to(root).as_posix()] = {"kind": "directory"}
        else:
            raw, found = _read(item)
            snapshot[item.relative_to(root).as_posix()] = {"kind": "file", "sha256": found, "bytes": len(raw)}
    return snapshot


def _verify_historical_chain(
    repo: Path, *, _sources: Any | None = None,
) -> tuple[dict, dict[Path, str]]:
    """Use the existing pure byte verifier; never open a writable call journal."""
    from ygo_eval.native_curry_option_validation import CURRY_SCOPE, _verify_curry_baseline

    if _sources is None:
        audit, protected = _verify_curry_baseline(repo, repo / CURRY_SCOPE.baseline_root)
        expected = {
            "previous_consumed": 26,
            "previous_unknown": 0,
            "previous_ledger_count": 7,
            "confirmation_consumed": 0,
            "confirmation_unknown": 0,
            "current_consumed": 6,
            "current_unknown": 0,
            "historical_consumed": HISTORICAL_CONSUMED,
            "historical_unknown": HISTORICAL_UNKNOWN,
            "historical_ledgers": HISTORICAL_LEDGER_COUNT,
        }
    else:
        source_role = getattr(_sources, "role", None)
        if source_role == "confirmation":
            historical_sources = _sources.child("asset_audit").child("historical_chain")
        elif source_role == "asset_audit":
            historical_sources = _sources.child("historical_chain")
        elif source_role == "historical_chain":
            historical_sources = _sources
        else:
            raise ValueError("historical_chain_source_scope_missing")
        curry_sources = historical_sources.child("curry_baseline")
        baseline_relative = getattr(curry_sources, "baseline_relative", None)
        require(
            isinstance(baseline_relative, str)
            and baseline_relative == CURRY_SCOPE.baseline_root.as_posix(),
            "historical_curry_source_path_invalid",
        )
        audit, protected = _verify_curry_baseline(
            repo, repo / baseline_relative, _sources=curry_sources,
        )
        ledger_sources = historical_sources
        # dataset_count recursively finds the unique pin in the immutable
        # source description's historical_ledgers leaf.
        expected = {
            name: ledger_sources.dataset_count(name)
            for name in (
                "previous_consumed", "previous_unknown", "previous_ledger_count",
                "confirmation_consumed", "confirmation_unknown",
                "current_consumed", "current_unknown", "historical_consumed",
                "historical_unknown", "historical_ledgers",
            )
        }
    prior = audit.get("prior")
    require(isinstance(prior, dict), "historical_audit_shape_invalid")
    previous_delivery = prior.get("delivery")
    confirmation = prior.get("prior")
    require(isinstance(confirmation, dict), "historical_confirmation_shape_invalid")
    previous_ledgers = confirmation.get("historical_ledgers")
    confirmation_ledger = confirmation.get("current_ledger")
    current_ledger = audit.get("delivery", {}).get("ledger")
    require(
        isinstance(previous_delivery, dict)
        and previous_delivery.get("historical_consumed") == expected["previous_consumed"]
        and previous_delivery.get("historical_unknown") == expected["previous_unknown"]
        and previous_ledgers == expected["previous_ledger_count"]
        and isinstance(confirmation_ledger, dict)
        and confirmation_ledger.get("consumed") == expected["confirmation_consumed"]
        and confirmation_ledger.get("unknown") == expected["confirmation_unknown"]
        and isinstance(current_ledger, dict)
        and current_ledger.get("stats", {}).get("consumed") == expected["current_consumed"]
        and current_ledger.get("stats", {}).get("unknown") == expected["current_unknown"]
        and expected["historical_consumed"]
        == expected["previous_consumed"] + expected["confirmation_consumed"] + expected["current_consumed"]
        and expected["historical_unknown"]
        == expected["previous_unknown"] + expected["confirmation_unknown"] + expected["current_unknown"]
        and expected["historical_ledgers"] == expected["previous_ledger_count"] + 2,
        "historical_ledger_totals_mismatch",
    )
    summary = {
        "consumed": expected["historical_consumed"],
        "unknown": expected["historical_unknown"],
        "ledger_count": expected["historical_ledgers"],
        "verified_without_writable_journal": True,
        "input_set_sha256": confirmation.get("historical_audit_sha256"),
    }
    return summary, protected


def _verify_curry_scope(
    repo: Path, baseline_root: Path, *, _sources: Any | None = None,
) -> dict:
    from ygo_eval.native_curry_option_validation import (
        _curry_evidence_hash,
        _snapshot_curry_evidence,
    )

    scope_sources = _asset_scope_sources(_sources)
    baseline_relative = Path(scope_sources.baseline_relative) if scope_sources is not None else BASELINE_RELATIVE
    require(scope_sources is None or baseline_relative == BASELINE_RELATIVE, "fixed_curry_baseline_required")
    require(_absolute(baseline_root) == _absolute(repo / baseline_relative), "fixed_curry_baseline_required")
    baseline_root = safe_path(baseline_root, file=False)
    if scope_sources is None:
        validate_anchor_hashes(HASH_ANCHORS)
    protected: dict[Path, str] = {}
    input_records: list[dict] = []

    def baseline_file(relative: str, *, file: bool = True, must_exist: bool = True) -> Path:
        if scope_sources is None:
            candidate = baseline_root / relative
            if not must_exist:
                safe_path(candidate.parent, file=False)
                require(not candidate.is_symlink(), "asset_audit_source_path_invalid")
                return candidate
            return safe_path(baseline_root / relative, file=file)
        if not must_exist:
            relative_path = (baseline_relative / relative).as_posix()
            return _source_optional_file_path(repo, relative_path)
        return _source_relative_path(repo, (baseline_relative / relative).as_posix(), file=file)

    def source_hash(relative: str, fallback: str) -> str:
        return _source_file_sha256(
            scope_sources, (baseline_relative / relative).as_posix(), fallback,
        )

    historical_consumed = _source_dataset_count(
        scope_sources, "historical_consumed", HISTORICAL_CONSUMED,
    )
    historical_unknown = _source_dataset_count(
        scope_sources, "historical_unknown", HISTORICAL_UNKNOWN,
    )

    pinned_paths = {
        "native_build_record": ("build-record.json", HASH_ANCHORS["native_build_record"]),
        "final_build_record": ("final-build/build-record.json", HASH_ANCHORS["final_build_record"]),
        "manifest": ("research/manifest.json", HASH_ANCHORS["manifest"]),
        "prepared": ("research/prepared.json", HASH_ANCHORS["prepared"]),
        "summary": ("research/summary.json", HASH_ANCHORS["summary"]),
    }
    for role, (relative, fixed_hash) in pinned_paths.items():
        path = baseline_file(relative)
        expected = source_hash(relative, fixed_hash)
        input_records.append(_record_input(repo, "old_" + role, path, protected, expected))

    if scope_sources is None:
        archive_specs = (
            ("native_time", baseline_root, "source-native.zip", "source-native-file-list.json", ARCHIVE_ANCHORS["native_time"]),
            ("final", baseline_root, "final-build/source-native.zip", "final-build/source-native-file-list.json", ARCHIVE_ANCHORS["final"]),
        )
    else:
        archive_specs = []
        for report_role, source_role in (
            ("native_time", "curry_native_archive"),
            ("final", "curry_final_archive"),
        ):
            pin = scope_sources.archive(source_role)
            expected_archive_path = (baseline_relative / ("source-native.zip" if report_role == "native_time" else "final-build/source-native.zip")).as_posix()
            expected_list_path = (baseline_relative / ("source-native-file-list.json" if report_role == "native_time" else "final-build/source-native-file-list.json")).as_posix()
            require(
                pin.archive_path == expected_archive_path
                and pin.file_list_path == expected_list_path,
                "curry_source_archive_path_mismatch",
            )
            archive_specs.append((
                report_role, repo, pin.archive_path, pin.file_list_path,
                {
                    "archive_sha256": pin.archive_sha256,
                    "file_list_sha256": pin.file_list_sha256,
                    "source_identity": pin.source_identity,
                    "file_count": pin.file_count,
                    "head": pin.head,
                    "report_role": report_role,
                },
            ))

    (native_role, native_root, native_archive_rel, native_list_rel, native_expected), \
        (final_role, final_root, final_archive_rel, final_list_rel, final_expected) = archive_specs
    native_source, native_archive = _verify_archive(
        native_root, native_archive_rel, native_list_rel, native_expected,
    )
    final_source, final_archive = _verify_archive(
        final_root, final_archive_rel, final_list_rel, final_expected,
    )
    for role, root, relative, expected_hash in (
        ("native_source_archive", native_root, native_archive_rel, native_expected["archive_sha256"]),
        ("native_source_file_list", native_root, native_list_rel, native_expected["file_list_sha256"]),
        ("final_source_archive", final_root, final_archive_rel, final_expected["archive_sha256"]),
        ("final_source_file_list", final_root, final_list_rel, final_expected["file_list_sha256"]),
    ):
        input_records.append(_record_input(repo, role, root / relative, protected, expected_hash))
    source_diffs = sorted(
        name for name in native_source.keys() | final_source.keys()
        if native_source.get(name) != final_source.get(name)
    )
    expected_diffs = (
        set(scope_sources.differences("curry_baseline"))
        if scope_sources is not None else ALLOWED_ARCHIVE_DIFFS
    )
    require(set(source_diffs) == expected_diffs, "curry_source_archive_diff_unexpected")

    source_records = []
    for record_relative, build_role, source_map, artifact_relative, archive_role, archive_record in (
        ("build-record.json", "native_build_record", native_source, "native-artifacts", "native_time", native_archive),
        ("final-build/build-record.json", "final_build_record", final_source, "final-build/native-artifacts", "final", final_archive),
    ):
        record_path = baseline_file(record_relative)
        expected_hash = source_hash(record_relative, HASH_ANCHORS[build_role])
        build_raw, build_hash = _read(record_path, expected_hash)
        build = strict_json(build_raw)
        _verify_signed_build(build)
        expected_head = (
            native_expected.get("head", "8a6b2f6762131aebea6d8c0f5f61363d573f1b36")
            if archive_role == "native_time"
            else final_expected.get("head", "8a6b2f6762131aebea6d8c0f5f61363d573f1b36")
        )
        source_identity = {"head": expected_head, "files": source_map}
        source_identity["identity"] = archive_record["source_identity"]
        require(
            build.get("status") == "recorded"
            and build.get("source_before") == source_identity
            and build.get("source_after") == source_identity
            and build.get("reproducible_build_proven") is False,
            "curry_old_build_source_binding_invalid",
        )
        expected_artifacts = {
            "cli": source_hash(f"{artifact_relative}/ygo-cli.exe", "00395cd2e209746ba7295d07782fd64ce635a960273c511469e0b0a89959e089" if archive_role == "native_time" else "00395cd2e209746ba7295d07782fd64ce635a960273c511469e0b0a89959e089"),
            "runner": source_hash(f"{artifact_relative}/curry-option-validation.exe", "57e119a1232b91dd57d13a5803475398589d2a801cc95ea27790a813326ed85f"),
            "worker": source_hash(f"{artifact_relative}/ygo-engine-worker.exe", "087fe574ac8d21a10befdbdad9ccfbc871805e643b6669e3fab520c8eb7fcb6d"),
        }
        require(build.get("artifacts") == expected_artifacts, "curry_old_artifact_build_hash_mismatch")
        for role, name in (
            ("runner", "curry-option-validation.exe"),
            ("cli", "ygo-cli.exe"),
            ("worker", "ygo-engine-worker.exe"),
        ):
            artifact = baseline_file(f"{artifact_relative}/{name}")
            record = _record_input(repo, f"{archive_role}_{role}", artifact, protected, expected_artifacts[role])
            input_records.append(record)
        input_records.append(_record_input(repo, f"{archive_role}_build_record", record_path, protected, expected_hash))
        source_records.append({
            "role": archive_role,
            "source_identity": archive_record["source_identity"],
            "build_record_sha256": build_hash,
            "build_record_identity": build["identity"],
            "artifact_sha256": expected_artifacts,
        })

    historical_code_path = RUST_SOURCE_RELATIVE.as_posix()
    require(historical_code_path in native_source and historical_code_path in final_source, "curry_archived_root_source_missing")
    with zipfile.ZipFile(native_root / native_archive_rel) as archive:
        historical_code = archive.read(historical_code_path).decode("utf-8")
    compact_code = re.sub(r"\s+", "", historical_code)
    require(
        'found["roles"]["worker"]["sha256"]!=input.request.versions.engine_sha256' in compact_code,
        "curry_historical_wrong_role_comparison_missing",
    )
    current_code_path = safe_path(repo / RUST_SOURCE_RELATIVE)
    current_code_raw, current_code_hash = _read(current_code_path)
    current_compact = re.sub(r"\s+", "", current_code_raw.decode("utf-8"))
    require(native_source[historical_code_path] == final_source[historical_code_path], "curry_archived_root_source_changed_between_builds")
    require(_sha(current_code_raw) == stable_source(repo)["files"].get(historical_code_path), "curry_current_root_source_not_bound_to_workspace")
    require(
        'found["roles"]["dll"]["sha256"]!=input.request.versions.engine_sha256' in current_compact
        and 'manifest["input_sha256"]["worker"]' in current_compact,
        "curry_current_asset_role_repair_missing",
    )
    historical_code_hash = native_source[historical_code_path]
    protected[_absolute(baseline_root)] = _curry_evidence_hash(_snapshot_curry_evidence(baseline_root))

    manifest_path = baseline_file("research/manifest.json")
    manifest = strict_json(safe_path(manifest_path).read_bytes())
    prepared_path = baseline_file("research/prepared.json")
    prepared = strict_json(safe_path(prepared_path).read_bytes())
    summary_path = baseline_file("research/summary.json")
    summary = strict_json(safe_path(summary_path).read_bytes())
    request_relative = "research/stage-1-request.json"
    input_relative = "research/stage-1-input.json"
    seal_relative = "research/stage-1-input-seal.json"
    request_path = baseline_file(request_relative)
    input_path = baseline_file(input_relative)
    seal_path = baseline_file(seal_relative)
    request_raw, request_hash = _read(request_path, source_hash(request_relative, FROZEN_FILES["stage1_request"]))
    request = strict_json(request_raw)
    input_raw, input_hash = _read(input_path, source_hash(input_relative, FROZEN_FILES["stage1_input"]))
    invocation = strict_json(input_raw)
    seal_raw, seal_hash = _read(seal_path, source_hash(seal_relative, FROZEN_FILES["stage1_seal"]))
    seal = strict_json(seal_raw)
    identity_relative = "identity.json"
    identity_path = baseline_file(identity_relative)
    identity_raw, identity_hash = _read(identity_path, source_hash(identity_relative, FROZEN_FILES["identity"]))
    identity_file = strict_json(identity_raw)
    window_relative = "window-start.json"
    window_path = baseline_file(window_relative)
    window_raw, window_hash = _read(window_path, source_hash(window_relative, FROZEN_FILES["window_start"]))
    window = strict_json(window_raw)

    require(
        manifest.get("schema_version") == 1
        and manifest.get("kind") == "native_curry_option_validation_manifest"
        and manifest.get("scope") == OLD_SCOPE
        and manifest.get("batch_kind") == OLD_SCOPE
        and manifest.get("context") == "538053247dabdba0d0eb424f67ce41c1b0a55eb7ee803685ad8d9a95c8a6e332"
        and manifest.get("old_consumed") == historical_consumed
        and manifest.get("limit") == 7
        and manifest.get("wall_seconds") == 7200,
        "curry_manifest_content_mismatch",
    )
    require(
        request == manifest.get("request")
        and digest(canonical(request)) == manifest.get("stage1_request_sha256")
        and request.get("protocol_version") == 2
        and request.get("seed") == 1
        and request.get("probe_only") is False
        and request.get("decisions") == [],
        "curry_stage1_request_binding_invalid",
    )
    expected_identity = manifest.get("assets", {}).get("ordinary")
    require(
        invocation.get("context") == manifest.get("context")
        and invocation.get("stage") == 1
        and invocation.get("batch_kind") == OLD_SCOPE
        and invocation.get("request") == request
        and invocation.get("expected_identity") == expected_identity
        and invocation.get("ledger") == str(baseline_root / "research/calls.jsonl")
        and invocation.get("output") == str(baseline_root / "research/stage-1.json")
        and manifest.get("input_sha256", {}).get("worker") == expected_identity.get("roles", {}).get("worker", {}).get("sha256")
        and expected_identity.get("roles", {}).get("dll", {}).get("sha256") == request.get("versions", {}).get("engine_sha256"),
        "curry_stage1_input_binding_invalid",
    )
    require(
        seal == {
            "schema_version": 1,
            "kind": "curry_option_validation_stage_input_seal",
            "context": manifest["context"],
            "stage": 1,
            "input_sha256": input_hash,
        },
        "curry_stage1_input_seal_invalid",
    )
    unsigned_identity = {key: value for key, value in identity_file.items() if key != "identity"}
    require(
        identity_file.get("kind") == "workspace_identity"
        and identity_file.get("schema_version") == 1
        and identity_file.get("consistent") is True
        and digest(canonical(unsigned_identity)) == identity_file.get("identity")
        and identity_file.get("runtimes", {}).get("ordinary") == expected_identity
        and manifest.get("input_sha256", {}).get("identity") == identity_hash,
        "curry_identity_file_binding_invalid",
    )
    require(
        window.get("schema_version") == 1
        and window.get("kind") == "curry_option_validation_window_start"
        and window.get("scope") == OLD_SCOPE
        and window.get("limit") == 7
        and window.get("wall_seconds") == 7200
        and window.get("started_at") == manifest.get("started_at")
        and manifest.get("input_sha256", {}).get("window_start") == window_hash,
        "curry_window_start_binding_invalid",
    )
    require(
        prepared.get("context") == manifest.get("context")
        and prepared.get("prepared") is False
        and prepared.get("native_calls") == 0
        and prepared.get("execution_ready") is False
        and prepared.get("stage1_input_sha256") == input_hash,
        "curry_prepared_report_mismatch",
    )
    require(
        summary.get("context") == manifest.get("context")
        and summary.get("successful") is False
        and summary.get("old_consumed") == historical_consumed
        and summary.get("diagnostic") == STORED_SUMMARY_DIAGNOSTIC
        and summary.get("new_consumed") is None
        and summary.get("new_unknown") is None,
        "curry_original_failure_summary_mismatch",
    )
    input_records.extend([
        _record_input(repo, "stage1_request", request_path, protected, request_hash),
        _record_input(repo, "stage1_input", input_path, protected, input_hash),
        _record_input(repo, "stage1_input_seal", seal_path, protected, seal_hash),
        _record_input(repo, "identity", identity_path, protected, identity_hash),
        _record_input(repo, "window_start", window_path, protected, window_hash),
    ])

    ledger_path = baseline_file("research/calls.jsonl", must_exist=False)
    require(not ledger_path.exists() and not ledger_path.is_symlink(), "curry_failed_scope_ledger_should_be_absent")
    diagnostic_records = []
    diagnostics_dir = safe_path(baseline_file("process-diagnostics", file=False), file=False)
    metadata_matches = []
    for metadata_path in diagnostics_dir.glob("*.json"):
        raw, found = _read(metadata_path)
        metadata = strict_json(raw)
        if (
            metadata.get("runner_role") == "curry_option_validation_runner"
            and metadata.get("mode") == "preflight_only"
            and metadata.get("status") == "completed"
            and metadata.get("return_code") == 2
        ):
            metadata_matches.append((metadata_path, metadata, raw, found))
    require(len(metadata_matches) == 1, "curry_original_preflight_diagnostic_ambiguous")
    metadata_path, metadata, metadata_raw, metadata_hash = metadata_matches[0]
    metadata_relative = metadata_path.relative_to(baseline_root).as_posix()
    require(
        metadata_hash == source_hash(metadata_relative, ORIGINAL_PROCESS_FILES["metadata"])
        and metadata.get("error_code") is None,
        "curry_original_preflight_diagnostic_mismatch",
    )
    for role in ("stdout", "stderr"):
        output = metadata.get(role)
        require(isinstance(output, dict), "curry_original_diagnostic_stream_missing")
        relative = output.get("path")
        require(
            isinstance(relative, str)
            and not Path(relative).is_absolute()
            and "\\" not in relative
            and ":" not in relative
            and ".." not in Path(relative).parts
            and relative.startswith("process-diagnostics/"),
            "curry_original_diagnostic_path_invalid",
        )
        stream_path = baseline_file(relative)
        stream_raw, stream_hash = _read(stream_path, source_hash(relative, ORIGINAL_PROCESS_FILES[role]))
        require(output.get("sha256") == stream_hash and output.get("bytes") == len(stream_raw), "curry_original_diagnostic_stream_mismatch")
        if role == "stderr":
            stderr_lines = stream_raw.decode("utf-8", errors="strict").splitlines()
            require(
                stderr_lines
                and stderr_lines[-1] == "Curry asset identity differs from frozen request",
                "curry_original_stderr_root_cause_mismatch",
            )
        diagnostic_records.append(_record_input(repo, "original_preflight_" + role, stream_path, protected, stream_hash))
    diagnostic_records.append(_record_input(repo, "original_preflight_metadata", metadata_path, protected, metadata_hash))
    input_records.extend(diagnostic_records)
    protected[baseline_root] = _curry_evidence_hash(_snapshot_curry_evidence(baseline_root))

    static_cause = {
        "historical_source_path": historical_code_path,
        "historical_source_sha256": historical_code_hash,
        "historical_comparison_role": "worker",
        "engine_version_role": "dll",
        "repair_target_role": "dll",
        "root_cause": "engine_sha256_was_compared_to_worker_sha256",
        "repair": "compare_engine_sha256_to_dll_and_bind_manifest_worker",
        "current_source_sha256": current_code_hash,
        "historical_scan_identity_persisted": False,
    }
    return {
        "context": manifest["context"],
        "request": request,
        "expected_identity": invocation["expected_identity"],
        "input_path": input_path,
        "input_sha256": input_hash,
        "input_records": input_records,
        "protected": protected,
        "source_archives": [native_archive, final_archive],
        "old_builds": source_records,
        "source_archive_differences": source_diffs,
        "historical": None,
        "old_scope": {
            "scope": OLD_SCOPE,
            "prepared": False,
            "ledger_exists": False,
            "consumed": None,
            "unknown": None,
            "stored_summary_diagnostic": STORED_SUMMARY_DIAGNOSTIC,
            "observed_process_diagnostic": ORIGINAL_DIAGNOSTIC,
            "original_process_return_code": 2,
            "original_stdout_sha256": ORIGINAL_PROCESS_FILES["stdout"],
            "original_stderr_sha256": ORIGINAL_PROCESS_FILES["stderr"],
            "original_process_metadata_sha256": ORIGINAL_PROCESS_FILES["metadata"],
        },
        "static_root_cause": static_cause,
        "protected_summary": {
            "file_count": len(protected),
            "tree_sha256": digest(canonical({path.as_posix(): value for path, value in sorted(protected.items(), key=lambda item: item[0].as_posix())})),
        },
    }


def _verify_historical_material(protected: dict[Path, str]) -> bool:
    from ygo_eval.native_curry_option_validation import _protected_curry_hash

    for path, expected in protected.items():
        absolute = _absolute(path)
        if absolute.is_dir():
            found = _protected_curry_hash(absolute, absolute)
        else:
            found = _sha(safe_path(absolute).read_bytes())
        require(found == expected, "protected_historical_material_changed")
    return True


def _protected_input_records(repo: Path, protected: dict[Path, str]) -> list[dict]:
    """Expose historical read-only inputs by logical role and repository-relative path."""
    records = []
    root = _absolute(repo)
    for index, (path, expected) in enumerate(sorted(protected.items(), key=lambda item: _absolute(item[0]).as_posix()), 1):
        absolute = _absolute(path)
        try:
            relative = absolute.relative_to(root).as_posix()
        except ValueError:
            raise ValueError("historical_input_outside_repository") from None
        if absolute.is_dir():
            from ygo_eval.native_curry_option_validation import _protected_curry_hash

            found = _protected_curry_hash(absolute, absolute)
            size = 0
        else:
            raw, found = _read(absolute)
            size = len(raw)
        require(found == expected, "historical_input_changed")
        records.append({
            "role": f"historical_material_{index:04d}",
            "path": relative,
            "sha256": found,
            "bytes": size,
        })
    return records


def _verify_new_runner(runner: Path, build_record: Path, repo: Path) -> dict:
    runner = _absolute(runner)
    build_path = _absolute(build_record)
    runner_raw, runner_hash = _read(runner)
    build_raw, build_hash = _read(build_path)
    build = strict_json(build_raw)
    _verify_signed_build(build)
    source = stable_source(repo)
    require(
        build.get("status") == "recorded"
        and build.get("source_before") == source
        and build.get("source_after") == source
        and build.get("reproducible_build_proven") is False
        and build.get("artifacts", {}).get("runner") == runner_hash,
        "audit_runner_build_binding_mismatch",
    )
    return {
        "runner_sha256": runner_hash,
        "runner_bytes": len(runner_raw),
        "build_record_sha256": build_hash,
        "build_record_identity": build["identity"],
        "source_identity": source["identity"],
        "source_file_count": len(source["files"]),
    }


def _trace_summary(stderr: bytes) -> tuple[list[dict], str | None]:
    try:
        lines = stderr.decode("utf-8").splitlines()
        require(len(lines) == len(TRACE_EVENTS), "runner_trace_incomplete")
        result = []
        for line, expected in zip(lines, TRACE_EVENTS):
            item = strict_json(line.encode("utf-8"))
            require(isinstance(item, dict), "runner_trace_event_invalid")
            require((item.get("phase"), item.get("event")) == expected, "runner_trace_order_invalid")
            if expected[1] == "start":
                require(set(item) == {"phase", "event"}, "runner_trace_event_invalid")
                result.append({"phase": expected[0], "event": expected[1]})
            else:
                elapsed = item.get("elapsed_ns")
                require(set(item) == {"phase", "event", "elapsed_ns"} and type(elapsed) is int and elapsed >= 0, "runner_trace_duration_invalid")
                result.append({"phase": expected[0], "event": expected[1], "elapsed_ns": elapsed})
        return result, None
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        return [], "runner_trace_invalid"


def _parsed_result(value: Any, context: str, identity_sha256: str) -> dict:
    return {
        "preflight_passed": value.get("preflight_passed") is True if isinstance(value, dict) else False,
        "native_calls": value.get("native_calls") if isinstance(value, dict) else None,
        "stage": value.get("stage") if isinstance(value, dict) else None,
        "context": value.get("context") if isinstance(value, dict) else None,
        "identity_sha256": value.get("identity_sha256") if isinstance(value, dict) else None,
        "matches_expected": (
            isinstance(value, dict)
            and value.get("preflight_passed") is True
            and type(value.get("native_calls")) is int
            and value.get("native_calls") == 0
            and type(value.get("stage")) is int
            and value.get("stage") == 1
            and value.get("context") == context
            and value.get("identity_sha256") == identity_sha256
        ),
    }


def _capture_process_sidecars(output_root: Path, repo: Path, process: dict, protected: dict[Path, str]) -> list[dict]:
    records = []
    for role, item in (
        ("runner_process_metadata", {"path": process["metadata_path"]}),
        ("runner_stdout", process["stdout"]),
        ("runner_stderr", process["stderr"]),
    ):
        relative = item.get("path")
        require(
            isinstance(relative, str)
            and not Path(relative).is_absolute()
            and "\\" not in relative
            and ":" not in relative
            and ".." not in Path(relative).parts
            and relative.startswith("process-diagnostics/"),
            "audit_process_path_invalid",
        )
        path = safe_path(output_root / relative)
        raw, found = _read(path, item.get("sha256"))
        if role != "runner_process_metadata":
            require(len(raw) == item.get("bytes"), "audit_process_length_mismatch")
        else:
            require(strict_json(raw) == process, "audit_process_metadata_mismatch")
        protected[_absolute(path)] = found
        records.append({"role": role, "path": path.relative_to(repo).as_posix(), "sha256": found, "bytes": len(raw)})
    return records


def _verify_report_sidecars(report: dict, repo: Path, artifact_root: Path) -> dict[str, bytes]:
    process = report.get("process")
    require(isinstance(process, dict), "audit_process_missing")
    require(process.get("mode") == "preflight_only" and process.get("runner_role") == RUNNER_ROLE, "audit_process_invalid")
    sidecars = {}
    for role, item in (
        ("metadata", {"path": process.get("metadata_path"), "sha256": process.get("metadata_sha256"), "bytes": process.get("metadata_bytes")}),
        ("stdout", process.get("stdout")),
        ("stderr", process.get("stderr")),
    ):
        require(isinstance(item, dict), "audit_process_sidecar_missing")
        relative = item.get("path")
        require(
            isinstance(relative, str)
            and not Path(relative).is_absolute()
            and "\\" not in relative
            and ":" not in relative
            and ".." not in Path(relative).parts
            and relative.startswith("process-diagnostics/"),
            "audit_process_path_invalid",
        )
        raw, found = _read(safe_path(artifact_root / relative), item.get("sha256"))
        require(len(raw) == item.get("bytes"), "audit_process_length_mismatch")
        sidecars[role] = raw
    require(strict_json(sidecars["metadata"]) == {
        "mode": process["mode"], "runner_role": process["runner_role"],
        "status": process.get("status"), "return_code": process.get("return_code"),
        "error_code": process.get("error_code"), "stdout": process.get("stdout"),
        "stderr": process.get("stderr"), "metadata_path": process.get("metadata_path"),
    }, "audit_process_metadata_binding_invalid")
    return sidecars


def _verify_report_process(report: dict, repo: Path, artifact_root: Path) -> None:
    process = report.get("process")
    sidecars = _verify_report_sidecars(report, repo, artifact_root)
    require(
        process.get("status") == "completed"
        and process.get("return_code") == 0
        and process.get("error_code") is None
        and process.get("timeout_seconds") == PREFLIGHT_TIMEOUT_SECONDS,
        "passed_audit_process_invalid",
    )
    trace, error = _trace_summary(sidecars["stderr"])
    require(error is None and trace == process.get("trace"), "audit_process_trace_mismatch")
    output = strict_json(sidecars["stdout"])
    input_item = next((item for item in report["inputs"] if item.get("role") == "stage1_input"), None)
    require(isinstance(input_item, dict), "audit_stage1_input_missing")
    input_path = safe_path(repo / input_item["path"])
    invocation = strict_json(_read(input_path, input_item.get("sha256"))[0])
    parsed = _parsed_result(output, invocation.get("context"), invocation.get("expected_identity", {}).get("identity"))
    require(parsed == process.get("parsed_result") and parsed["matches_expected"], "audit_preflight_output_mismatch")


def validate_report(
    report: dict,
    repo: Path | None = None,
    artifact_root: Path | None = None,
    *,
    _sources: Any | None = None,
) -> bool:
    require(isinstance(report, dict) and report.get("schema_version") == 1, "audit_schema_version_invalid")
    require(report.get("kind") == "curry_asset_binding_audit", "audit_kind_invalid")
    require(report.get("status") in {"passed", "failed", "incomplete"}, "audit_status_invalid")
    require(report.get("native_calls") == 0 and report.get("execution_ready") is False, "audit_scope_invalid")
    require(all(report.get(key) is False for key in RESEARCH_FLAGS), "research_qualification_must_remain_false")
    require(report.get("original_native_diagnostic") == ORIGINAL_DIAGNOSTIC, "original_diagnostic_changed")
    expected_anchors = _source_anchor_hashes(_sources)
    require(report.get("anchors") == expected_anchors, "audit_anchor_set_invalid")
    if _sources is not None:
        _validate_report_source_pins(report, _sources)
    require(
        isinstance(report.get("checks"), dict)
        and set(report["checks"]) == set(CHECK_NAMES)
        and all(state in {"not_run", "passed", "failed"} for state in report["checks"].values()),
        "audit_checks_invalid",
    )
    require(isinstance(report.get("inputs"), list) and isinstance(report.get("source_archives"), list), "audit_records_invalid")
    require(report.get("source", {}).get("runner_role") == RUNNER_ROLE, "audit_runner_role_invalid")
    require(report.get("process") is None or isinstance(report.get("process"), dict), "audit_process_invalid")
    require(report.get("diagnostic") is None or re.fullmatch(r"[a-z][a-z0-9_]{1,90}", report["diagnostic"]) is not None, "audit_diagnostic_invalid")
    old_scope = report.get("old_scope")
    require(
        isinstance(old_scope, dict)
        and old_scope.get("scope") == OLD_SCOPE
        and old_scope.get("prepared") is False
        and old_scope.get("ledger_exists") is False
        and old_scope.get("stored_summary_diagnostic") == STORED_SUMMARY_DIAGNOSTIC
        and old_scope.get("observed_process_diagnostic") == ORIGINAL_DIAGNOSTIC,
        "old_curry_scope_claim_invalid",
    )
    history = report.get("history")
    if _sources is None:
        historical_consumed = HISTORICAL_CONSUMED
        historical_unknown = HISTORICAL_UNKNOWN
        historical_ledgers = HISTORICAL_LEDGER_COUNT
    else:
        historical_consumed = _source_dataset_count(_sources, "historical_consumed", HISTORICAL_CONSUMED)
        historical_unknown = _source_dataset_count(_sources, "historical_unknown", HISTORICAL_UNKNOWN)
        historical_ledgers = _source_dataset_count(_sources, "historical_ledgers", HISTORICAL_LEDGER_COUNT)
    require(
        history is None
        or (
            isinstance(history, dict)
            and history.get("consumed") == historical_consumed
            and history.get("unknown") == historical_unknown
            and history.get("ledger_count") == historical_ledgers
            and history.get("verified_without_writable_journal") is True
            and isinstance(history.get("input_set_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", history["input_set_sha256"]) is not None
        ),
        "historical_totals_claim_invalid",
    )
    for item in report["inputs"]:
        path = item.get("path") if isinstance(item, dict) else None
        require(
            isinstance(path, str)
            and not Path(path).is_absolute()
            and "\\" not in path
            and ":" not in path
            and ".." not in Path(path).parts
            and isinstance(item.get("role"), str)
            and re.fullmatch(r"[a-z][a-z0-9_-]{1,80}", item["role"]) is not None
            and re.fullmatch(r"[a-f0-9]{64}", item.get("sha256", "")) is not None
            and type(item.get("bytes")) is int
            and item["bytes"] >= 0,
            "audit_input_path_invalid",
        )
    if report.get("static_root_cause") is not None:
        cause = report["static_root_cause"]
        require(
            isinstance(cause, dict)
            and cause.get("historical_comparison_role") == "worker"
            and cause.get("engine_version_role") == "dll"
            and cause.get("repair_target_role") == "dll"
            and cause.get("root_cause") == "engine_sha256_was_compared_to_worker_sha256"
            and cause.get("repair") == "compare_engine_sha256_to_dll_and_bind_manifest_worker"
            and cause.get("historical_scan_identity_persisted") is False,
            "static_root_cause_claim_invalid",
        )
    for archive in report["source_archives"]:
        require(
            isinstance(archive, dict)
            and archive.get("role") in {"native_time", "final"}
            and all(re.fullmatch(r"[a-f0-9]{64}", archive.get(key, "")) for key in ("sha256", "file_list_sha256", "source_identity"))
            and type(archive.get("file_count")) is int
            and archive["file_count"] > 0,
            "source_archive_record_invalid",
        )
    if report.get("process") is not None and repo is not None:
        _verify_report_sidecars(
            report,
            Path(repo).absolute(),
            _absolute(artifact_root or Path(repo).absolute() / OUTPUT_RELATIVE),
        )
    if report["status"] == "passed":
        require(
            report.get("diagnostic") is None
            and all(value == "passed" for value in report["checks"].values())
            and len(report["inputs"]) > 0
            and {item.get("role") for item in report["source_archives"]} == {"native_time", "final"}
            and report.get("history") == {
                "consumed": historical_consumed,
                "unknown": historical_unknown,
                "ledger_count": historical_ledgers,
                "verified_without_writable_journal": True,
                "input_set_sha256": report["history"].get("input_set_sha256"),
            }
            and report["old_scope"].get("ledger_exists") is False
            and report["static_root_cause"].get("historical_scan_identity_persisted") is False
            and isinstance(report.get("process"), dict),
            "audit_success_claim_invalid",
        )
        require(repo is not None, "passed_audit_requires_process_validation")
        _verify_report_process(report, Path(repo).absolute(), _absolute(artifact_root or Path(repo).absolute() / OUTPUT_RELATIVE))
    if repo is not None:
        schema_path = Path(repo).absolute() / "schemas/curry-asset-binding-audit-v1.schema.json"
        require(schema_path.is_file(), "audit_schema_missing")
    return True


def _new_report() -> dict:
    return {
        "schema_version": 1,
        "kind": "curry_asset_binding_audit",
        "status": "incomplete",
        "anchors": dict(HASH_ANCHORS),
        "native_calls": 0,
        "execution_ready": False,
        "original_native_diagnostic": ORIGINAL_DIAGNOSTIC,
        "checks": {name: "not_run" for name in CHECK_NAMES},
        "inputs": [],
        "source_archives": [],
        "history": None,
        "old_scope": {
            "scope": OLD_SCOPE,
            "prepared": False,
            "ledger_exists": False,
            "consumed": None,
            "unknown": None,
            "stored_summary_diagnostic": STORED_SUMMARY_DIAGNOSTIC,
            "observed_process_diagnostic": ORIGINAL_DIAGNOSTIC,
        },
        "static_root_cause": None,
        "source": {"runner_role": RUNNER_ROLE},
        "protection": None,
        "process": None,
        "diagnostic": None,
        "elapsed_seconds": 0.0,
        "input_set_sha256": None,
        **RESEARCH_FLAGS,
    }


def _run_audit(
    *,
    repo: Path,
    baseline_dir: Path,
    runner: Path,
    build_record: Path,
    output_root: Path,
    output_path: Path,
    process_runner: Callable[..., Any] | None = None,
    baseline_verifier: Callable[[Path, Path], dict] | None = None,
    _sources: Any | None = None,
) -> dict:
    from ygo_eval.tenki_placement_diagnostics import capture_process_diagnostic, DiagnosticPersistenceError

    start = time.monotonic()
    repo = _absolute(repo)
    output_root = _absolute(output_root)
    report = _new_report()
    protected: dict[Path, str] = {}
    current_check = "historical_sources"
    source_before = None
    curry_before = None
    historical_protected: dict[Path, str] = {}
    process_record = None
    try:
        report["anchors"] = _source_anchor_hashes(_sources)
        source_before = stable_source(repo)
        root_sources = _asset_audit_root_sources(_sources)
        if root_sources is not None:
            expected_source_identity = root_sources.archive("asset_audit_native_archive").source_identity
            expected_source_file_count = root_sources.dataset_count("asset_audit_source_files")
            require(
                source_before.get("identity") == expected_source_identity
                and len(source_before.get("files", {})) == expected_source_file_count,
                "audit_workspace_source_pin_mismatch",
            )
        curry_before = _snapshot_tree(_absolute(baseline_dir))
        verify = baseline_verifier
        if verify is None:
            full = _verify_curry_scope(repo, baseline_dir, _sources=_sources)
            history, historical_protected = _verify_historical_chain(repo, _sources=_sources)
            full["historical"] = history
            verify = lambda _repo, _baseline: full
        baseline = verify(repo, baseline_dir)
        protected.update(baseline.get("protected", {}))
        protected.update(historical_protected)
        report["inputs"] = baseline.get("input_records", [])
        report["inputs"].extend(_protected_input_records(repo, historical_protected))
        report["source_archives"] = baseline.get("source_archives", [])
        report["history"] = baseline.get("historical")
        report["old_scope"] = baseline.get("old_scope") or report["old_scope"]
        report["static_root_cause"] = baseline.get("static_root_cause")
        report["protection"] = baseline.get("protected_summary")
        report["source"].update({
            "workspace_identity": source_before["identity"],
            "workspace_file_count": len(source_before["files"]),
            "historical_consumed": _source_dataset_count(_sources, "historical_consumed", HISTORICAL_CONSUMED),
            "historical_unknown": _source_dataset_count(_sources, "historical_unknown", HISTORICAL_UNKNOWN),
            "ledger_count": _source_dataset_count(_sources, "historical_ledgers", HISTORICAL_LEDGER_COUNT),
            "runner_role": RUNNER_ROLE,
            "source_archive_differences": baseline.get("source_archive_differences", []),
            "old_builds": baseline.get("old_builds", []),
        })
        report["checks"]["historical_sources"] = "passed"
        report["checks"]["old_curry_material"] = "passed"
        report["checks"]["historical_ledgers"] = "passed"
        report["checks"]["static_root_cause"] = "passed"

        current_check = "isolated_runner_build"
        new_build = _verify_new_runner(runner, build_record, repo)
        report["source"].update(new_build)
        report["inputs"].extend([
            _record_input(repo, "new_isolated_runner", runner, protected, new_build["runner_sha256"]),
            _record_input(repo, "new_build_record", build_record, protected, new_build["build_record_sha256"]),
        ])
        report["checks"]["isolated_runner_build"] = "passed"

        _verify_historical_material(protected)
        protected_before = dict(protected)
        current_check = "read_only_preflight"
        report["checks"]["read_only_preflight"] = "failed"
        input_path = baseline["input_path"]
        input_raw, input_hash = _read(input_path, baseline["input_sha256"])
        invocation = strict_json(input_raw)
        require(invocation.get("request") == baseline.get("request"), "curry_request_not_bound_to_input")
        command = [
            str(_absolute(runner)), str(_absolute(input_path)),
            "--input-sha", input_hash,
            "--preflight-only", "--trace-stderr",
        ]
        process_record, completed = capture_process_diagnostic(
            command,
            repo,
            output_root,
            mode="preflight_only",
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
            runner=process_runner,
            runner_role=RUNNER_ROLE,
        )
        sidecar_records = _capture_process_sidecars(output_root, repo, process_record, protected)
        report["inputs"].extend(sidecar_records)
        report["process"] = {
            "mode": "preflight_only",
            "runner_role": RUNNER_ROLE,
            "status": process_record["status"],
            "return_code": process_record["return_code"],
            "error_code": process_record["error_code"],
            "metadata_path": process_record["metadata_path"],
            "metadata_sha256": next(item["sha256"] for item in sidecar_records if item["role"] == "runner_process_metadata"),
            "metadata_bytes": next(item["bytes"] for item in sidecar_records if item["role"] == "runner_process_metadata"),
            "stdout": process_record["stdout"],
            "stderr": process_record["stderr"],
            "timeout_seconds": PREFLIGHT_TIMEOUT_SECONDS,
        }
        stdout = safe_path(output_root / process_record["stdout"]["path"]).read_bytes()
        stderr = safe_path(output_root / process_record["stderr"]["path"]).read_bytes()
        trace, trace_error = _trace_summary(stderr)
        report["process"]["trace"] = trace
        report["checks"]["trace"] = "passed" if trace_error is None else "failed"
        if process_record["status"] != "completed":
            report["diagnostic"] = process_record.get("error_code") or "runner_process_failed"
        elif completed is None or completed.returncode != 0:
            report["diagnostic"] = "runner_nonzero_exit"
        else:
            try:
                parsed = strict_json(stdout)
            except (ValueError, TypeError, UnicodeDecodeError):
                parsed = None
                report["diagnostic"] = "runner_invalid_json"
            if parsed is not None:
                result = _parsed_result(parsed, baseline["context"], baseline["expected_identity"].get("identity"))
                report["process"]["parsed_result"] = result
                if not result["matches_expected"]:
                    report["diagnostic"] = "runner_preflight_result_mismatch"
                elif trace_error is not None:
                    report["diagnostic"] = trace_error
                else:
                    report["checks"]["read_only_preflight"] = "passed"
        current_check = "input_stability"
        _verify_historical_material(protected_before)
        _verify_historical_material(protected)
        require(_read(input_path)[1] == input_hash, "stage1_input_changed_during_preflight")
        require(stable_source(repo) == source_before, "workspace_source_changed_during_preflight")
        require(_snapshot_tree(_absolute(baseline_dir)) == curry_before, "old_curry_material_changed_during_preflight")
        require(not (baseline_dir / "research/calls.jsonl").exists(), "audit_must_not_create_charge_ledger")
        report["checks"]["input_stability"] = "passed"
        report["checks"]["old_material_protection"] = "passed"
        if report["diagnostic"] is None and all(value == "passed" for value in report["checks"].values()):
            report["status"] = "passed"
        else:
            report["status"] = "failed"
            if report["diagnostic"] is None:
                report["diagnostic"] = "offline_audit_checks_incomplete"
    except DiagnosticPersistenceError:
        report["status"] = "failed"
        report["diagnostic"] = "diagnostic_persistence_failed"
        report["checks"][current_check] = "failed"
    except (ValueError, OSError, KeyError, TypeError, UnicodeDecodeError, zipfile.BadZipFile) as error:
        report["status"] = "failed"
        report["diagnostic"] = _safe_error(error)
        report["checks"][current_check] = "failed"
    except Exception:
        report["status"] = "failed"
        report["diagnostic"] = "offline_audit_unexpected_failure"
        report["checks"][current_check] = "failed"

    report["elapsed_seconds"] = round(time.monotonic() - start, 6)
    report["input_set_sha256"] = digest(canonical([
        {"path": path.relative_to(repo).as_posix(), "sha256": value}
        for path, value in sorted(protected.items(), key=lambda pair: pair[0].as_posix())
        if path.is_relative_to(repo)
    ])) if protected else None
    validate_report(report, repo=repo, artifact_root=output_root, _sources=_sources)
    immutable_write(output_path, report)
    return report


def _load_baseline_request(baseline_root: Path) -> dict:
    request_path = safe_path(baseline_root / "research/stage-1-request.json")
    request_raw, found = _read(request_path, FROZEN_FILES["stage1_request"])
    request = strict_json(request_raw)
    require(digest(canonical(request)) == found, "curry_request_content_hash_mismatch")
    return request


def run_audit(
    args: argparse.Namespace,
    repo: Path | None = None,
    process_runner: Callable[..., Any] | None = None,
    *,
    _sources: Any | None = None,
) -> dict:
    """Audit fixed Curry evidence and one zero-call preflight into an ignored directory."""
    repo = _absolute(repo or Path(__file__).resolve().parents[2])
    baseline = _absolute(args.baseline_dir)
    output_root = _absolute(repo / OUTPUT_RELATIVE)
    runner = _absolute(args.runner)
    build_record = _absolute(args.build_record)
    output_path = _absolute(args.output)
    require(baseline == _absolute(repo / BASELINE_RELATIVE), "fixed_curry_baseline_required")
    require(runner == output_root / "native-artifacts/curry-option-validation.exe", "fixed_audit_runner_path_required")
    require(build_record == output_root / "build-record.json", "fixed_audit_build_record_path_required")
    require(output_path == output_root / "audit-report.json", "fixed_audit_output_path_required")
    checked_output(repo, output_path)
    require(not output_path.exists() and not output_path.is_symlink(), "audit_output_already_exists")
    diagnostics = output_root / "process-diagnostics"
    require(not diagnostics.exists() or not any(diagnostics.rglob("*")), "audit_preflight_already_started")
    return _run_audit(
        repo=repo,
        baseline_dir=baseline,
        runner=runner,
        build_record=build_record,
        output_root=output_root,
        output_path=output_path,
        process_runner=process_runner,
        _sources=_sources,
    )
