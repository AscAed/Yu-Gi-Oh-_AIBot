"""Record a conservative, zero-call budget reservation for unknown Curry usage."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import zipfile
from typing import Any, Callable

from ygo_eval.prompt_probe_prepare import safe_path, strict_json


BASELINE_RELATIVE = Path("data/runtime/p1-curry-recovery-synthetic-e2e-offline-2026-10-24")
V2_REPORT_RELATIVE = Path("data/runtime/p1-curry-input-recovery-v2-offline-2026-10-24/audit-report.json")
CONFIRMATION_RELATIVE = Path("data/runtime/p1-curry-option-confirmation-native-2026-10-24")
OUTPUT_RELATIVE = Path("data/runtime/p1-curry-consumption-reservation-offline-2026-10-24")
REPORT_NAME = "reservation.json"
POLICY_ID = "curry-unknown-reserve-seven-v1"
RESERVED_CALLS = 7
HISTORICAL_LEDGER_COUNT = 9
HISTORICAL_CONSUMED = 32
HISTORICAL_UNKNOWN = 0
CONFIRMATION_SCOPE = "curry-option-confirmation-v1"
CONFIRMATION_CONTEXT = "2dfda24aa08bdf1113bac1f831a80e08c113a52f9e0d6e3d813f24e5ff2cc3de"
DELIVERY_SHA256 = "5ede9f0f47742e07961fe7341c70777b134bff43dbeae267890c65a0c906f64e"
V2_REPORT_SHA256 = "67c6332310aed1e77ccc9eb4394b700f4169837b198a50de20d422dc01da757b"
ACCEPTANCE_SHA256 = "f6f5a88664252f9fb0f7d94c7251dba2e8859fbf1d19e9a45396070efce84835"
SYNTHETIC_REPORT_SHA256 = "45d127bed0f27870167c042a23f8f253c88fb4338edc17ca73a9dc6443578812"
REVIEW_SHA256 = "85ed2d0b3cf621005ee2f45cd26cb755cb78eb4ec4b00888aa0db3e24310e43b"
PROTECTION_SHA256 = "1f99ccc594314f9ba92b5a14bfaafbb0d8ba0a35c0f3feaa90feeb7b06fed1ca"
SOURCE_ARCHIVE_SHA256 = "9490176a378cbf0ed6712ac5945f0baa1954d1d24607875f24012c48c05496ff"
SOURCE_FILE_LIST_SHA256 = "089171bd233bccb71e788ad2e0c3259a7cbf0450b468a11cbfdce55669896fe3"
SOURCE_IDENTITY = "fe43200a33bfb36b9d349f0d997360d7450ac1e932bef275815341c942dc9f45"
SOURCE_HEAD = "8a6b2f6762131aebea6d8c0f5f61363d573f1b36"
SOURCE_FILE_COUNT = 529
V2_ACCEPTANCE_SHA256 = "20654b7d09247f5f71acd038c6f72546b50a8bfa85f0a3bb9041fc297b1c69e0"
V2_ACCEPTANCE_RELATIVE = Path("data/runtime/p1-curry-v2-validation-2026-10-24/final-delivery-after-docs-v2/acceptance.json")
PREVIOUS_V1_REPORT_RELATIVE = OUTPUT_RELATIVE / REPORT_NAME
PREVIOUS_V1_REPORT_SHA256 = "17dd4b3f08c4c13c1d440bf6641a3fa4b9c9ae498e652c5d852156c8891ee3e7"
V2_OUTPUT_RELATIVE = Path("data/runtime/p1-curry-consumption-reservation-v2-offline-2026-10-25")
V2_SCHEMA_PATH = "schemas/curry-consumption-reservation-v2.schema.json"
V3_OUTPUT_RELATIVE = Path("data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25")
V3_SCHEMA_PATH = "schemas/curry-consumption-reservation-v3.schema.json"
V2_FAILED_REPORT_RELATIVE = V2_OUTPUT_RELATIVE / REPORT_NAME
V2_FAILED_REPORT_SHA256 = "5fb0cd2e10d3477fd09544e85e02b5234386b60668721ba33bc85ccb1db745da"
V2_FAILED_ACCEPTANCE_RELATIVE = Path("target/curry-consumption-reservation-v2-tests/acceptance-v2.json")
V2_FAILED_ACCEPTANCE_SHA256 = "42513ccd9b4e835540010afc616c7e24183519e8a7316d2629d4792c58506330"
V3_CORRECTED_SOURCE_ARCHIVE = (
    Path("data/runtime/p1-curry-consumption-reservation-offline-2026-10-24/delivery/source-native.zip"),
    "eb34fbe09d05d38b2d84d0e404389c87296bed1795e54c798f7d275c5476431c",
    Path("data/runtime/p1-curry-consumption-reservation-offline-2026-10-24/delivery/source-file-list.json"),
    "ac9eb2071297cd926958620b4d91386bac0b3939b7b7c49dfc41f9c30e3621ec",
    "curry_consumption_reservation_final_source_file_list", 534,
    "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
    "dd287963eb50c461f683aa22149ee341d3d9be03edb34a3d498431924776e6ac", "files",
)
V3_V2_AUDIT_SOURCE_ARCHIVE = (
    Path("target/curry-consumption-reservation-v2-tests/real-audit-source/source-native.zip"),
    "8104ee889d2ae0a686fb5b5a3cba8add1076ad22f29e029f871ee825eea9eb67",
    Path("target/curry-consumption-reservation-v2-tests/real-audit-source/source-file-list.json"),
    "08dd2255a19eea71b1a8d92c03051e1d7b20717265044b91ce7f4005dfb180c9",
    "curry_reservation_v2_audit_source_file_list", 535,
    "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
    "be9414a756ab436ba12221f178ea23bbb55ac00bfa0ff55c170ca69647bafc98", "entries",
)
V3_V2_FINAL_SOURCE_ARCHIVE = (
    Path("target/curry-consumption-reservation-v2-tests/final-doc-source-final/source-native.zip"),
    "071760069b4e551518b57bfb6cae995919d63ea5663423ca9cb50a1a749c3770",
    Path("target/curry-consumption-reservation-v2-tests/final-doc-source-final/source-file-list.json"),
    "e70f335c0ddb31225daccf69916bb5e1f4112827ea1a359b24fb5f81c0a1a9fd",
    "curry_consumption_reservation_v2_final_source_file_list", 536,
    "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
    "1847417cb4136ab446631350208ebd2c44b462d5696427041307747731164374", "entries",
)
V3_TENKI_EVIDENCE_RELATIVE = Path("data/runtime/p1-tenki-placement-validation-native-2026-10-23")
V3_TENKI_EVIDENCE_SHA256 = "e7c0e1069c52f63da047b367bad5e5c9ff49c2d5aaa30c57cf3c16f263c70acb"
V3_TENKI_ACCEPTANCE_RELATIVE = V3_TENKI_EVIDENCE_RELATIVE / "acceptance.json"
V3_TENKI_ACCEPTANCE_SHA256 = "242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9"
V3_TENKI_LEDGER_RELATIVE = V3_TENKI_EVIDENCE_RELATIVE / "research/calls.jsonl"
V3_TENKI_LEDGER_SHA256 = "4244d92bd17413861bc92d4618803bc647dd05cab074189e678be8429f89971c"
V3_V2_AUDIT_SOURCE_ROOT = Path("target/curry-consumption-reservation-v2-tests/real-audit-source")
V3_V2_FINAL_SOURCE_ROOT = Path("target/curry-consumption-reservation-v2-tests/final-doc-source-final")
V3_DOCUMENT_SOURCE_CHANGES = (
    "TASKS.md", "docs/INDEX.md", "docs/TESTING.md",
    "docs/superpowers/plans/2026-10-25-curry-consumption-reservation-v2-handoff.md",
)
ARCHIVED_BAD_ACCEPTANCE_CONSTANT = "f6f5a88664252f9fbf7d94c7251dba2e8859fbf1d19e9a45396070efce84835"
HASH = re.compile(r"^[a-f0-9]{64}$")
_TOOL_FILES = (
    "python/ygo_eval/curry_consumption_reservation.py",
    "python/ygo_eval/research.py",
    "python/ygo_eval/prompt_probe_prepare.py",
    "python/ygo_eval/curry_input_recovery_audit.py",
    "python/ygo_data/identity.py",
    "schemas/curry-consumption-reservation-v1.schema.json",
)
_V2_TOOL_FILES = (*_TOOL_FILES, V2_SCHEMA_PATH)
_V3_TOOL_FILES = (*_V2_TOOL_FILES, V3_SCHEMA_PATH)
_OUTPUT_FILES = {
    REPORT_NAME,
    "tool-source.zip",
    "tool-source-file-list.json",
    "delivery/acceptance.json",
    "delivery/input-protection.json",
    "delivery/independent-review.json",
    "delivery/source-file-list.json",
    "delivery/source-native.zip",
    "delivery/source-identity.json",
    "delivery/evidence-size.json",
    "delivery/pytest-files.txt",
    "delivery/pytest-full.log",
    "delivery/verification.json",
}
_CHECKS = (
    "latest_delivery_chain",
    "real_v2_report",
    "old_confirmation_scope",
    "historical_ledgers",
    "input_stability",
)
_V2_CHECKS = ("previous_failed_attempt", *_CHECKS)
_V3_CHECKS = ("previous_failed_attempts", "recovery_source_archives", *_CHECKS)
_QUALIFICATIONS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}


@dataclass(frozen=True)
class _Profile:
    """Private fixed-source profile; no CLI option can construct one."""

    baseline_relative: Path
    v2_report_relative: Path
    confirmation_relative: Path
    output_relative: Path
    delivery_sha256: str
    v2_report_sha256: str
    acceptance_sha256: str
    review_sha256: str
    protection_sha256: str
    synthetic_report_sha256: str
    archive_sha256: str
    file_list_sha256: str
    source_identity: str
    source_head: str
    source_file_count: int
    confirmation_context: str
    confirmation_input_count: int
    confirmation_evidence_count: int
    confirmation_evidence_bytes: int
    test_log_hashes: tuple[tuple[str, str], ...]
    v2_acceptance_sha256: str
    v2_acceptance_relative: Path
    confirmation_role_input_count: int = 64
    tenki_evidence_relative: Path = V3_TENKI_EVIDENCE_RELATIVE
    tenki_evidence_sha256: str = V3_TENKI_EVIDENCE_SHA256
    tenki_acceptance_relative: Path = V3_TENKI_ACCEPTANCE_RELATIVE
    tenki_acceptance_sha256: str = V3_TENKI_ACCEPTANCE_SHA256
    tenki_ledger_relative: Path = V3_TENKI_LEDGER_RELATIVE
    tenki_ledger_sha256: str = V3_TENKI_LEDGER_SHA256


@dataclass(frozen=True)
class _VersionSpec:
    """Fixed report-version wiring; it cannot be constructed from CLI data."""

    version: int
    kind: str
    schema_path: str
    output_relative: Path
    checks: tuple[str, ...]
    tool_files: tuple[str, ...]
    previous_failure_relative: Path | None = None
    previous_failure_sha256: str | None = None
    previous_v2_failure_relative: Path | None = None
    previous_v2_failure_sha256: str | None = None
    recovery_archives: tuple[tuple[Path, str, Path, str, str, int, str, str, str], ...] = ()
    required_input_roles: tuple[str, ...] = ()
    previous_v2_acceptance_relative: Path | None = None
    previous_v2_acceptance_sha256: str | None = None
    previous_v2_acceptance_bytes: int | None = None


def _production_profile() -> _Profile:
    return _Profile(
        BASELINE_RELATIVE, V2_REPORT_RELATIVE, CONFIRMATION_RELATIVE,
        OUTPUT_RELATIVE, DELIVERY_SHA256, V2_REPORT_SHA256,
        ACCEPTANCE_SHA256, REVIEW_SHA256, PROTECTION_SHA256,
        SYNTHETIC_REPORT_SHA256, SOURCE_ARCHIVE_SHA256,
        SOURCE_FILE_LIST_SHA256, SOURCE_IDENTITY, SOURCE_HEAD,
        SOURCE_FILE_COUNT, CONFIRMATION_CONTEXT, 43, 40, 60_054_498,
        (
            ("pytest-files.txt", "8dd3c844cbe3da37cc0b01713baed01acb49f44b85979af982b4dd9cb8f7817e"),
            ("pytest-full-rerun.log", "39f42e9865a4dbadf3a673b5d99178c28aad359aa8b726644a8ce5eaf449db26"),
            ("pytest-full.log", "2d63562b0b30675f0f50393ba0bea5b806825755814a5a7a6f4dc6219d611028"),
        ),
        V2_ACCEPTANCE_SHA256, V2_ACCEPTANCE_RELATIVE,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-version", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--verify-only", action="store_true")


def _version_spec(version: int) -> _VersionSpec:
    if version == 1:
        return _VersionSpec(
            1, "curry_consumption_reservation",
            "schemas/curry-consumption-reservation-v1.schema.json",
            OUTPUT_RELATIVE, _CHECKS, _TOOL_FILES,
        )
    if version == 2:
        return _VersionSpec(
            2, "curry_consumption_reservation_v2", V2_SCHEMA_PATH,
            V2_OUTPUT_RELATIVE, _V2_CHECKS, _V2_TOOL_FILES,
            PREVIOUS_V1_REPORT_RELATIVE, PREVIOUS_V1_REPORT_SHA256,
        )
    if version == 3:
        return _VersionSpec(
            3, "curry_consumption_reservation_v3", V3_SCHEMA_PATH,
            V3_OUTPUT_RELATIVE, _V3_CHECKS, _V3_TOOL_FILES,
            PREVIOUS_V1_REPORT_RELATIVE, PREVIOUS_V1_REPORT_SHA256,
            V2_FAILED_REPORT_RELATIVE, V2_FAILED_REPORT_SHA256,
            (V3_CORRECTED_SOURCE_ARCHIVE, V3_V2_AUDIT_SOURCE_ARCHIVE, V3_V2_FINAL_SOURCE_ARCHIVE),
            (
                "latest_delivery", "acceptance", "independent_review", "protected_material_check",
                "synthetic_public_report", "authenticated_v2_report", "authenticated_prior_v2_acceptance",
                "previous_v1_failed_reservation_report", "previous_v1_failed_tool_archive",
                "previous_v1_failed_tool_file_list", "previous_v2_failed_reservation_report",
                "previous_v2_failed_tool_archive", "previous_v2_failed_tool_file_list",
                "corrected_534_source_archive", "corrected_534_source_file_list",
                "v2_audit_535_source_archive", "v2_audit_535_source_file_list",
                "v2_final_536_source_archive", "v2_final_536_source_file_list",
                "v2_failure_acceptance", "tenki_validation_directory_evidence",
                "tenki_validation_acceptance", "tenki_validation_ledger",
            ),
            V2_FAILED_ACCEPTANCE_RELATIVE,
            V2_FAILED_ACCEPTANCE_SHA256,
            2_644,
        )
    raise ValueError("reservation_report_version_invalid")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(value: bool, code: str) -> None:
    if not value:
        raise ValueError(code)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _safe_relative(root: Path, name: str) -> Path:
    _require(isinstance(name, str) and name and "\\" not in name and ":" not in name, "unsafe_source_path")
    relative = PurePosixPath(name)
    _require(not relative.is_absolute() and ".." not in relative.parts, "unsafe_source_path")
    candidate = _absolute(root.joinpath(*relative.parts))
    _require(candidate.is_relative_to(_absolute(root)), "unsafe_source_path")
    return safe_path(candidate)


def _read(root: Path, name: str, expected: str | None = None) -> tuple[bytes, str]:
    raw = _safe_relative(root, name).read_bytes()
    found = _sha(raw)
    _require(expected is None or found == expected, "source_hash_mismatch")
    return raw, found


def _record(root: Path, role: str, name: str, expected: str | None = None) -> dict[str, Any]:
    raw, found = _read(root, name, expected)
    return {"role": role, "path": name, "sha256": found, "bytes": len(raw)}


def _parse(raw: bytes, code: str) -> dict[str, Any]:
    value = strict_json(raw)
    _require(isinstance(value, dict), code)
    return value


def _verify_public_source_archive(
    root: Path, archive_name: str, list_name: str, profile: _Profile,
) -> tuple[dict[str, str], dict[str, Any]]:
    archive_raw, archive_hash = _read(root, archive_name, profile.archive_sha256)
    list_raw, list_hash = _read(root, list_name, profile.file_list_sha256)
    listing = _parse(list_raw, "source_file_list_invalid")
    entries = listing.get("entries")
    _require(
        listing.get("schema_version") == 1
        and listing.get("kind") == "curry_synthetic_e2e_final_source_file_list"
        and listing.get("file_count") == profile.source_file_count
        and listing.get("present_file_count") == profile.source_file_count
        and listing.get("source_identity") == profile.source_identity
        and isinstance(entries, list) and len(entries) == profile.source_file_count,
        "source_file_list_invalid",
    )
    files: dict[str, str] = {}
    for item in entries:
        _require(isinstance(item, dict) and set(item) == {"path", "sha256", "state"}, "source_file_list_entry_invalid")
        name, value = item["path"], item["sha256"]
        _require(item["state"] == "present" and isinstance(name, str) and HASH.fullmatch(value or "") is not None, "source_file_list_entry_invalid")
        relative = PurePosixPath(name)
        _require(not relative.is_absolute() and ".." not in relative.parts and "\\" not in name and ":" not in name, "source_archive_member_path_invalid")
        _require(name not in files, "source_file_list_duplicate_path")
        files[name] = value
    identity = _sha(_canonical({"head": profile.source_head, "files": files}))
    _require(identity == profile.source_identity, "source_identity_mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names)) and set(names) == set(files), "source_archive_membership_invalid")
            for name, expected in files.items():
                _require(_sha(archive.read(name)) == expected, "source_archive_member_hash_mismatch")
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("source_archive_invalid") from None
    return files, {"sha256": archive_hash, "file_list_sha256": list_hash, "source_identity": identity, "file_count": len(files), "bytes": len(archive_raw)}


def _verify_v3_recovery_archive(
    repo: Path, pin: tuple[Path, str, Path, str, str, int, str, str, str], role: str,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, Any]]]:
    archive_rel, archive_sha, list_rel, list_sha, list_kind, count, head, identity, row_format = pin
    archive_name, list_name = archive_rel.as_posix(), list_rel.as_posix()
    archive_raw, archive_hash = _read(repo, archive_name, archive_sha)
    list_raw, list_hash = _read(repo, list_name, list_sha)
    listing = _parse(list_raw, "recovery_source_file_list_invalid")
    _require(
        listing.get("schema_version") == 1 and listing.get("kind") == list_kind
        and listing.get("file_count") == count and listing.get("head") == head
        and listing.get("source_identity") == identity,
        "recovery_source_file_list_invalid",
    )
    if row_format == "files":
        _require(set(listing) == {
            "schema_version", "kind", "file_count", "files", "head", "missing_files", "source_identity",
        } and listing.get("missing_files") == [], "corrected_source_file_list_invalid")
        rows = listing.get("files")
    else:
        _require(set(listing) == {"schema_version", "kind", "file_count", "entries", "head", "source_identity"}, "recovery_source_file_list_invalid")
        rows = listing.get("entries")
    _require(isinstance(rows, list) and len(rows) == count, "recovery_source_file_count_invalid")
    files: dict[str, str] = {}
    for row in rows:
        expected_keys = {"path", "sha256"} if row_format == "files" else {"path", "sha256", "state"}
        _require(
            isinstance(row, dict) and set(row) == expected_keys
            and isinstance(row.get("path"), str) and HASH.fullmatch(row.get("sha256", "")) is not None
            and (row_format == "files" or row.get("state") == "present"),
            "recovery_source_file_entry_invalid",
        )
        name = row["path"]
        relative = PurePosixPath(name)
        _require(
            not relative.is_absolute() and ".." not in relative.parts and "\\" not in name
            and ":" not in name and name not in files,
            "recovery_source_archive_member_path_invalid",
        )
        files[name] = row["sha256"]
    _require(len(files) == count, "recovery_source_file_count_invalid")
    _require(_sha(_canonical({"head": head, "files": files})) == identity, "recovery_source_identity_mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names)) and set(names) == set(files), "recovery_source_archive_membership_invalid")
            for name, expected in files.items():
                _require(_sha(archive.read(name)) == expected, "recovery_source_archive_member_hash_mismatch")
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("recovery_source_archive_invalid") from None
    meta = {
        "archive_path": archive_name, "archive_sha256": archive_hash,
        "file_list_path": list_name, "file_list_sha256": list_hash,
        "file_count": count, "head": head, "source_identity": identity,
    }
    records = [
        _record(repo, role + "_source_archive", archive_name, archive_sha),
        _record(repo, role + "_source_file_list", list_name, list_sha),
    ]
    return files, meta, records


def _verify_v3_recovery_sources(
    repo: Path, spec: _VersionSpec, report: dict[str, Any],
) -> None:
    _require(spec.version == 3 and len(spec.recovery_archives) == 3, "v3_recovery_source_spec_invalid")
    _require(
        spec.previous_v2_acceptance_relative is not None
        and spec.previous_v2_acceptance_sha256 is not None,
        "v2_recovery_acceptance_spec_invalid",
    )
    acceptance_raw, acceptance_hash = _read(
        repo, spec.previous_v2_acceptance_relative.as_posix(), spec.previous_v2_acceptance_sha256,
    )
    _require(
        spec.previous_v2_acceptance_bytes is None
        or len(acceptance_raw) == spec.previous_v2_acceptance_bytes,
        "v2_recovery_acceptance_size_invalid",
    )
    acceptance = _parse(acceptance_raw, "v2_recovery_acceptance_invalid")
    _require(
        acceptance.get("schema_version") == 1
        and acceptance.get("kind") == "curry_consumption_reservation_v2_acceptance"
        and acceptance.get("status") == "blocked"
        and acceptance.get("native_calls") == 0
        and acceptance.get("previous_v1_report_sha256") == spec.previous_failure_sha256
        and acceptance.get("audit_source") == {
            "archive_sha256": spec.recovery_archives[1][1],
            "file_count": spec.recovery_archives[1][5],
            "file_list_sha256": spec.recovery_archives[1][3],
            "identity": spec.recovery_archives[1][7],
        }
        and acceptance.get("final_document_source") == {
            "archive_bytes": len(_safe_relative(repo, spec.recovery_archives[2][0].as_posix()).read_bytes()),
            "archive_sha256": spec.recovery_archives[2][1],
            "file_count": spec.recovery_archives[2][5],
            "file_list_sha256": spec.recovery_archives[2][3],
            "head": spec.recovery_archives[2][6],
            "kind": "curry_consumption_reservation_v2_final_source_freeze",
            "present_file_count": spec.recovery_archives[2][5],
            "schema_version": 1,
            "source_identity": spec.recovery_archives[2][7],
        }
        and acceptance.get("real_read_only_audit", {}).get("report_sha256") == spec.previous_v2_failure_sha256
        and acceptance.get("real_read_only_audit", {}).get("failure_checkpoint") == "latest_delivery_chain"
        and acceptance.get("real_read_only_audit", {}).get("diagnostic") == "independent_review_invalid"
        and acceptance.get("reservation") == {"planned_total": None, "recorded": False, "reservation_id": None, "risk_reserve_calls": 7}
        and acceptance.get("qualifications") == _QUALIFICATIONS,
        "v2_recovery_acceptance_binding_invalid",
    )
    report["inputs"].append(_record(
        repo, "v2_failure_acceptance", spec.previous_v2_acceptance_relative.as_posix(), spec.previous_v2_acceptance_sha256,
    ))
    audit_files: dict[str, str] | None = None
    final_files: dict[str, str] | None = None
    labels = ("corrected_534", "v2_audit_535", "v2_final_536")
    for index, (pin, label) in enumerate(zip(spec.recovery_archives, labels, strict=True)):
        files, meta, records = _verify_v3_recovery_archive(repo, pin, label)
        report["recovery_source_archives"][label] = meta
        report["inputs"].extend(records)
        if index == 1:
            audit_files = files
        elif index == 2:
            final_files = files
    _require(audit_files is not None and final_files is not None, "v2_recovery_source_maps_missing")
    shared = set(audit_files) & set(final_files)
    changed = sorted(name for name in shared if audit_files[name] != final_files[name])
    added = sorted(set(final_files) - set(audit_files))
    removed = sorted(set(audit_files) - set(final_files))
    _require(
        changed == sorted(V3_DOCUMENT_SOURCE_CHANGES[:3])
        and added == [V3_DOCUMENT_SOURCE_CHANGES[3]] and removed == [],
        "v2_recovery_source_diff_invalid",
    )
    report["recovery_source_archives"]["allowed_document_changes"] = sorted([*changed, *added])


def _validate_delivery_chain(
    repo: Path, profile: _Profile, report: dict[str, Any], spec: _VersionSpec | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    spec = spec or _version_spec(1)
    baseline = repo / profile.baseline_relative
    delivery_rel = (profile.baseline_relative / "final-build/delivery.json").as_posix()
    delivery_raw, delivery_hash = _read(repo, delivery_rel, profile.delivery_sha256)
    delivery = _parse(delivery_raw, "delivery_invalid")
    _require(
        delivery.get("schema_version") == 1
        and delivery.get("kind") == "curry_recovery_synthetic_e2e_final_delivery"
        and delivery.get("source_identity") == profile.source_identity
        and delivery.get("source_file_count") == profile.source_file_count
        and delivery.get("native_calls") == 0
        and delivery.get("execution_ready") is False
        and delivery.get("qualifications") == _QUALIFICATIONS,
        "delivery_content_invalid",
    )
    required_refs = {
        "acceptance_sha256": profile.acceptance_sha256,
        "independent_review_sha256": profile.review_sha256,
        "protected_material_check_sha256": profile.protection_sha256,
        "synthetic_report_sha256": profile.synthetic_report_sha256,
    }
    _require(all(delivery.get(key) == value for key, value in required_refs.items()), "delivery_anchor_mismatch")
    _require(delivery.get("source_archive") == {
        "file_count": profile.source_file_count,
        "file_list_path": "final-build/source-file-list.json",
        "file_list_sha256": profile.file_list_sha256,
        "path": "final-build/source-native.zip",
        "present_file_count": profile.source_file_count,
        "sha256": profile.archive_sha256,
    }, "delivery_source_archive_binding_invalid")

    inputs: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    records.append(_record(repo, "latest_delivery", delivery_rel, profile.delivery_sha256))
    fixed_files = (
        ("acceptance.json", "acceptance", profile.acceptance_sha256),
        ("independent-review.json", "independent_review", profile.review_sha256),
        ("protected-material-check.json", "protected_material_check", profile.protection_sha256),
        ("synthetic-success-report.json", "synthetic_public_report", profile.synthetic_report_sha256),
    )
    parsed: dict[str, dict[str, Any]] = {}
    for relative, role, expected in fixed_files:
        full = (profile.baseline_relative / relative).as_posix()
        raw, found = _read(repo, full, expected)
        parsed[role] = _parse(raw, role + "_invalid")
        records.append({"role": role, "path": full, "sha256": found, "bytes": len(raw)})

    acceptance = parsed["acceptance"]
    _require(
        acceptance.get("kind") == "curry_recovery_synthetic_e2e_acceptance"
        and acceptance.get("schema_version") == 1
        and acceptance.get("native_calls") == 0
        and acceptance.get("execution_ready") is False
        and acceptance.get("public_audit_report", {}).get("sha256") == profile.synthetic_report_sha256
        and acceptance.get("historical_boundary") == {
            "certified_consumed": HISTORICAL_CONSUMED,
            "certified_ledger_count": HISTORICAL_LEDGER_COUNT,
            "certified_unknown": HISTORICAL_UNKNOWN,
            "curry_confirmation_cumulative_consumed": None,
            "curry_confirmation_new_consumed": None,
            "curry_confirmation_unknown": None,
            "historical_acceptance_sha256": profile.v2_acceptance_sha256,
            "historical_v2_report_sha256": profile.v2_report_sha256,
            "sealed_unconsumed_slots": RESERVED_CALLS,
        },
        "acceptance_content_invalid",
    )
    review = parsed["independent_review"]
    if spec.version == 3:
        review_binding = acceptance.get("review")
        _require(
            review.get("schema_version") == 1
            and review.get("kind") == "curry_recovery_synthetic_e2e_independent_review"
            and review.get("result") == "passed"
            and review.get("mode") == "read_only"
            and review.get("native_calls") == 0
            and review.get("real_audit_run") is False
            and "public_cli_bypass_found" not in review
            and review_binding == {
                "independent_read_only_review": "passed",
                "production_source_pins_unchanged": True,
                "public_cli_bypass_found": False,
            },
            "independent_review_invalid",
        )
        report["compatibility_basis"]["review_field_sources"] = {
            "review_quality_source": "independent-review.json",
            "review_public_cli_bypass_found": None,
            "acceptance_public_cli_bypass_found_source": "acceptance.review.public_cli_bypass_found",
            "acceptance_public_cli_bypass_found": False,
        }
    else:
        _require(
            review.get("kind") == "curry_recovery_synthetic_e2e_independent_review"
            and review.get("result") == "passed"
            and review.get("native_calls") == 0
            and review.get("real_audit_run") is False
            and review.get("public_cli_bypass_found") is False,
            "independent_review_invalid",
        )
    synthetic = parsed["synthetic_public_report"]
    public_checks = synthetic.get("checks")
    _require(
        synthetic.get("kind") == "curry_input_recovery_audit_v2"
        and synthetic.get("status") == "passed"
        and synthetic.get("native_calls") == 0
        and synthetic.get("execution_ready") is False
        and isinstance(public_checks, dict) and len(public_checks) == 7
        and all(value == "passed" for value in public_checks.values())
        and synthetic.get("historical") == {
            "consumed": HISTORICAL_CONSUMED,
            "unknown": HISTORICAL_UNKNOWN,
            "ledger_count": HISTORICAL_LEDGER_COUNT,
            "verified_without_writable_journal": True,
            "input_set_sha256": synthetic.get("historical", {}).get("input_set_sha256"),
        }
        and synthetic.get("confirmation_scope", {}).get("scope") == CONFIRMATION_SCOPE
        and synthetic.get("confirmation_scope", {}).get("new_consumed") is None
        and synthetic.get("confirmation_scope", {}).get("cumulative_consumed") is None
        and synthetic.get("confirmation_scope", {}).get("new_unknown") is None
        and synthetic.get("confirmation_scope", {}).get("unconsumed_slots_sealed") == RESERVED_CALLS,
        "synthetic_report_invalid",
    )
    protected = parsed["protected_material_check"]
    ledger_rows = protected.get("authenticated_historical_ledgers")
    _require(
        protected.get("kind") == "curry_recovery_synthetic_e2e_protected_material_check"
        and protected.get("mode") == "read_only_hash_check_only"
        and protected.get("native_calls") == 0
        and protected.get("historical_ledger_count") == HISTORICAL_LEDGER_COUNT
        and protected.get("historical_consumed") == HISTORICAL_CONSUMED
        and protected.get("historical_unknown") == HISTORICAL_UNKNOWN
        and protected.get("old_curry_confirmation_ledger") == {
            "consumption": None,
            "path": (profile.confirmation_relative / "research/calls.jsonl").as_posix(),
            "state": "still_absent",
        }
        and isinstance(ledger_rows, list) and len(ledger_rows) == HISTORICAL_LEDGER_COUNT,
        "protection_check_invalid",
    )
    ledger_paths: set[str] = set()
    tenki_ledger_pin_count = 0
    for index, item in enumerate(ledger_rows, 1):
        _require(
            isinstance(item, dict) and item.get("passed") is True
            and HASH.fullmatch(item.get("expected_sha256", "")) is not None
            and item.get("actual_sha256") == item.get("expected_sha256")
            and isinstance(item.get("path"), str) and item["path"] not in ledger_paths,
            "historical_ledger_protection_invalid",
        )
        ledger_paths.add(item["path"])
        if spec.version == 3 and item["path"] == profile.tenki_ledger_relative.as_posix():
            _require(
                item["expected_sha256"] == profile.tenki_ledger_sha256,
                "tenki_validation_ledger_pin_invalid",
            )
            tenki_ledger_pin_count += 1
            inputs[item["path"]] = {
                "expected_sha256": item["expected_sha256"], "bytes": None,
                "role": "tenki_validation_ledger",
            }
        else:
            _require(
                not (spec.version == 3 and item["path"] == profile.tenki_evidence_relative.as_posix()),
                "tenki_validation_directory_pin_in_protection_list_unexpected",
            )
            inputs[item["path"]] = {
                "expected_sha256": item["expected_sha256"],
                "bytes": None,
                "role": f"historical_ledger_{index:02d}",
            }
    if spec.version == 3:
        _require(tenki_ledger_pin_count == 1, "tenki_validation_ledger_pin_missing")

    test_logs = delivery.get("test_logs")
    _require(isinstance(test_logs, dict) and test_logs == dict(profile.test_log_hashes), "delivery_test_log_set_invalid")
    for name, expected in sorted(test_logs.items()):
        full = (profile.baseline_relative / name).as_posix()
        records.append(_record(repo, "test_log_" + name.replace(".", "_"), full, expected))
    _require(delivery.get("python_tests") == {"elapsed_seconds": 497.48, "files": 59, "passed": 461, "skipped": 8, "subtests": 130}, "delivery_python_test_summary_invalid")
    _require(delivery.get("rust_cargo") == {"changed_this_batch": False, "previous_certified_file_count": 159, "previous_checks_reused": True}, "delivery_rust_summary_invalid")
    archive_rel = (profile.baseline_relative / "final-build/source-native.zip").as_posix()
    list_rel = (profile.baseline_relative / "final-build/source-file-list.json").as_posix()
    _, archive_info = _verify_public_source_archive(repo, archive_rel, list_rel, profile)
    records.extend([
        _record(repo, "source_archive", archive_rel, profile.archive_sha256),
        _record(repo, "source_file_list", list_rel, profile.file_list_sha256),
    ])
    report["anchors"]["latest_delivery_sha256"] = delivery_hash
    report["anchors"]["source_identity"] = archive_info["source_identity"]
    report["anchors"]["source_file_count"] = archive_info["file_count"]
    return inputs, records


def _input_index(report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_path: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}
    rows = report.get("inputs")
    _require(isinstance(rows, list), "v2_input_list_invalid")
    for row in rows:
        _require(
            isinstance(row, dict) and isinstance(row.get("path"), str)
            and HASH.fullmatch(row.get("sha256", "")) is not None
            and type(row.get("bytes")) is int and row["bytes"] >= 0
            and isinstance(row.get("role"), str),
            "v2_input_record_invalid",
        )
        prior = by_path.get(row["path"])
        if prior is not None:
            _require((prior["sha256"], prior["bytes"]) == (row["sha256"], row["bytes"]), "v2_input_path_hash_conflict")
        else:
            by_path[row["path"]] = row
        _require(row["role"] not in by_role, "v2_input_role_duplicate")
        by_role[row["role"]] = row
    return by_path, by_role


def _confirmation_evidence_roles(
    roles: dict[str, dict[str, Any]], confirmation_prefix: str,
) -> list[dict[str, Any]]:
    """Keep inventory aliases indexed by role even when paths are deduplicated."""
    return [
        item for role, item in roles.items()
        if role.startswith("confirmation_evidence_file_")
        and item.get("path", "").startswith(confirmation_prefix)
    ]


def _validate_v3_ledger_path(value: str, repo: Path, profile: _Profile) -> str:
    """Resolve the frozen Windows path to exactly the old confirmation ledger."""
    from pathlib import PureWindowsPath

    _require(isinstance(value, str) and value, "confirmation_stage_input_ledger_path_invalid")
    windows = PureWindowsPath(value)
    candidate = Path(value)
    _require(windows.is_absolute() and ".." not in windows.parts, "confirmation_stage_input_ledger_path_invalid")
    expected = _absolute(repo / profile.confirmation_relative / "research/calls.jsonl")
    normalized = Path(os.path.normpath(os.path.abspath(candidate)))
    _require(os.path.normcase(str(normalized)) == os.path.normcase(str(expected)), "confirmation_stage_input_ledger_path_invalid")
    # The charge ledger is intentionally absent. Check existing ancestors for
    # links/junctions without requiring the final file to exist.
    for item in reversed(expected.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            _require(
                not item.is_symlink() and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "confirmation_stage_input_ledger_path_linked",
            )
    _require(not expected.is_symlink(), "confirmation_stage_input_ledger_path_linked")
    return (profile.confirmation_relative / "research/calls.jsonl").as_posix()


def _verify_v2_report(
    repo: Path, profile: _Profile, report: dict[str, Any],
    spec: _VersionSpec | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    spec = spec or _version_spec(1)
    relative = profile.v2_report_relative.as_posix()
    raw, found = _read(repo, relative, profile.v2_report_sha256)
    value = _parse(raw, "v2_report_invalid")
    _require(
        value.get("schema_version") == 2
        and value.get("kind") == "curry_input_recovery_audit_v2"
        and value.get("status") == "passed"
        and value.get("failure_checkpoint") is None
        and value.get("native_calls") == 0
        and value.get("execution_ready") is False
        and value.get("checks") == {
            "acceptance_delivery_anchors": "passed", "evidence_inventory": "passed",
            "frozen_input_binding": "passed", "historical_ledgers": "passed",
            "input_stability": "passed", "old_material_protection": "passed",
            "source_archives": "passed",
        }
        and value.get("historical") == {
            "consumed": HISTORICAL_CONSUMED,
            "input_set_sha256": value.get("historical", {}).get("input_set_sha256"),
            "ledger_count": HISTORICAL_LEDGER_COUNT,
            "unknown": HISTORICAL_UNKNOWN,
            "verified_without_writable_journal": True,
        }
        and value.get("confirmation_scope") == {
            "cumulative_consumed": None,
            "execution_ready": False,
            "native_validation_passed": False,
            "new_consumed": None,
            "new_unknown": None,
            "prepared": True,
            "scope": CONFIRMATION_SCOPE,
            "unconsumed_slots_sealed": RESERVED_CALLS,
        }
        and value.get("historical_exit_observation") == {
            "archived_refusal_branch_return_code": 2,
            "historical_exit_code_certified": False,
            "observation_exit_code": 1,
            "raw_normal_stdout_stderr_saved": False,
        }
        and value.get("qualifications") == _QUALIFICATIONS,
        "v2_report_content_invalid",
    )
    paths, roles = _input_index(value)
    acceptance_relative = profile.v2_acceptance_relative.as_posix()
    if spec.version == 3:
        # The V3-anchored V2 acceptance is a separately fixed source, not an
        # input row in the V2 audit report. Bind it directly; V1/V2 retain
        # their historical input-index requirement below.
        acceptance_raw, acceptance_hash = _read(
            repo, acceptance_relative, profile.v2_acceptance_sha256,
        )
    else:
        prior_acceptance = paths.get(acceptance_relative)
        _require(
            isinstance(prior_acceptance, dict)
            and prior_acceptance.get("sha256") == profile.v2_acceptance_sha256,
            "v2_acceptance_anchor_invalid",
        )
        acceptance_raw, acceptance_hash = _read(repo, acceptance_relative, profile.v2_acceptance_sha256)
        _require(len(acceptance_raw) == prior_acceptance["bytes"], "v2_acceptance_size_mismatch")
    report["inputs"].append({"role": "authenticated_prior_v2_acceptance", "path": acceptance_relative, "sha256": acceptance_hash, "bytes": len(acceptance_raw)})
    report["inputs"].append({"role": "authenticated_v2_report", "path": relative, "sha256": found, "bytes": len(raw)})
    report["anchors"]["real_v2_report_sha256"] = found
    report["anchors"]["v2_acceptance_sha256"] = profile.v2_acceptance_sha256
    return paths, roles, value


def _validate_old_scope(
    repo: Path, profile: _Profile, paths: dict[str, dict[str, Any]], roles: dict[str, dict[str, Any]],
    report: dict[str, Any], ledger_pins: dict[str, dict[str, Any]], spec: _VersionSpec | None = None,
) -> list[dict[str, Any]]:
    spec = spec or _version_spec(1)
    confirmation_root = profile.confirmation_relative.as_posix()
    prefix = confirmation_root + "/"
    confirmation_roles = [item for item in roles.values() if item["path"].startswith(prefix)]
    confirmation_rows = [item for item in paths.values() if item["path"].startswith(prefix)]
    role_count = len(confirmation_roles) if spec.version == 3 else len(confirmation_rows)
    expected_role_count = profile.confirmation_role_input_count if spec.version == 3 else profile.confirmation_input_count
    _require(role_count == expected_role_count, "confirmation_input_set_invalid")
    _require(len(confirmation_rows) == profile.confirmation_input_count, "confirmation_physical_file_set_invalid")
    records: list[dict[str, Any]] = []
    for item in sorted(confirmation_rows, key=lambda row: row["path"]):
        raw, found = _read(repo, item["path"], item["sha256"])
        _require(len(raw) == item["bytes"], "confirmation_input_size_mismatch")
    record_rows = confirmation_roles if spec.version == 3 else confirmation_rows
    for item in sorted(record_rows, key=lambda row: (row["role"], row["path"])):
        raw, found = _read(repo, item["path"], item["sha256"])
        _require(len(raw) == item["bytes"], "confirmation_input_size_mismatch")
        records.append({"role": item["role"], "path": item["path"], "sha256": found, "bytes": len(raw)})

    measured_files = {
        path for path, row in _snapshot_tree(repo / profile.confirmation_relative).items()
        if row["kind"] == "file"
    }
    expected_files = {item["path"][len(prefix):] for item in confirmation_rows}
    _require(measured_files == expected_files, "confirmation_unlisted_file_present")

    def load(relative: str) -> tuple[dict[str, Any], str]:
        path = (profile.confirmation_relative / relative).as_posix()
        item = paths.get(path)
        _require(item is not None, "confirmation_required_input_missing")
        raw, found = _read(repo, path, item["sha256"])
        _require(len(raw) == item["bytes"], "confirmation_input_size_mismatch")
        return _parse(raw, "confirmation_json_invalid"), found

    manifest, manifest_hash = load("research/manifest.json")
    window, _ = load("window-start.json")
    prepared, _ = load("research/prepared.json")
    summary, _ = load("research/summary.json")
    inventory, _ = load("evidence-inventory.json")
    observation, _ = load("research/normal-attempt-observation.json")
    seal, _ = load("research/stage-1-input-seal.json")
    stage_input, stage_input_hash = load("research/stage-1-input.json")
    request, request_hash = load("research/stage-1-request.json")

    manifest_path = (profile.confirmation_relative / "research/manifest.json").as_posix()
    manifest_pin = paths.get(manifest_path)
    _require(
        manifest_pin is not None and manifest_hash == manifest_pin["sha256"]
        and manifest.get("kind") == "native_curry_option_confirmation_manifest"
        and manifest.get("scope") == CONFIRMATION_SCOPE
        and manifest.get("context") == profile.confirmation_context
        and manifest.get("planned_calls") == RESERVED_CALLS
        and manifest.get("limit") == RESERVED_CALLS
        and manifest.get("wall_seconds") == 7200
        and type(manifest.get("started_at")) is int,
        "confirmation_manifest_binding_invalid",
    )
    _require(
        window.get("kind") == "curry_option_confirmation_window_start"
        and window.get("scope") == CONFIRMATION_SCOPE
        and window.get("limit") == RESERVED_CALLS
        and window.get("wall_seconds") == 7200
        and window.get("started_at") == manifest["started_at"],
        "confirmation_window_binding_invalid",
    )
    _require(
        prepared.get("kind") == "native_curry_option_confirmation_prepared"
        and prepared.get("scope") == CONFIRMATION_SCOPE
        and prepared.get("context") == profile.confirmation_context
        and prepared.get("prepared") is True
        and prepared.get("execution_ready") is True
        and prepared.get("native_calls") == 0
        and prepared.get("planned_calls") == RESERVED_CALLS
        and prepared.get("manifest_sha256") == manifest_hash,
        "confirmation_prepared_binding_invalid",
    )
    _require(
        summary.get("kind") == "native_curry_option_confirmation_summary"
        and summary.get("scope") == CONFIRMATION_SCOPE
        and summary.get("context") == profile.confirmation_context
        and summary.get("successful") is False
        and summary.get("new_consumed") is None
        and summary.get("cumulative_consumed") is None
        and summary.get("unknown") is None,
        "confirmation_summary_accounting_invalid",
    )
    _require(
        inventory.get("kind") == "curry_option_confirmation_evidence_inventory"
        and inventory.get("scope") == CONFIRMATION_SCOPE
        and inventory.get("complete_for_measured_root") is True
        and inventory.get("entry_count") == profile.confirmation_evidence_count
        and isinstance(inventory.get("entries"), list)
        and len(inventory["entries"]) == profile.confirmation_evidence_count
        and inventory.get("accessible_file_bytes") == profile.confirmation_evidence_bytes
        and inventory.get("access_errors") == [],
        "confirmation_inventory_invalid",
    )
    evidence_source = roles.values() if spec.version == 3 else paths.values()
    evidence_rows = [item for item in evidence_source if item["path"].startswith(prefix) and item["role"].startswith("confirmation_evidence_file_")]
    evidence_by_relative = {
        item["path"][len(prefix):]: item for item in evidence_rows
    }
    _require(
        len(evidence_rows) == profile.confirmation_evidence_count
        and len(evidence_by_relative) == profile.confirmation_evidence_count,
        "confirmation_evidence_record_set_invalid",
    )
    inventory_paths: set[str] = set()
    for entry in inventory["entries"]:
        _require(isinstance(entry, dict) and set(entry) == {"path", "sha256", "bytes"}, "confirmation_inventory_entry_invalid")
        name = entry["path"]
        _require(isinstance(name, str) and name not in inventory_paths, "confirmation_inventory_entry_invalid")
        inventory_paths.add(name)
        item = evidence_by_relative.get(name)
        _require(item is not None and item["sha256"] == entry["sha256"] and item["bytes"] == entry["bytes"], "confirmation_inventory_binding_invalid")
    _require(set(evidence_by_relative) == inventory_paths, "confirmation_inventory_binding_invalid")
    _require(
        set(inventory.get("excluded_from_measurement", [])) == {
            "acceptance.json", "evidence-inventory.json", "final-build/delivery.json",
        },
        "confirmation_inventory_exclusions_invalid",
    )
    _require(
        observation.get("kind") == "curry_option_confirmation_normal_attempt_observation"
        and observation.get("scope") == CONFIRMATION_SCOPE
        and observation.get("exit_code") == 1
        and observation.get("worker_request_consumption") is None
        and observation.get("authenticated_ledger_present") is False
        and observation.get("normal_process_diagnostic_present") is False
        and observation.get("raw_process_output_saved") is False,
        "confirmation_observation_invalid",
    )
    _require(
        stage_input.get("context") == profile.confirmation_context
        and stage_input.get("stage") == 1
        and stage_input.get("request") == request
        and stage_input.get("started_at") == manifest["started_at"]
        and (
            _validate_v3_ledger_path(stage_input.get("ledger"), repo, profile)
            == (profile.confirmation_relative / "research/calls.jsonl").as_posix()
            if spec.version == 3
            else stage_input.get("ledger") == "research/calls.jsonl"
        )
        and stage_input.get("expected_identity") is not None,
        "confirmation_stage_input_binding_invalid",
    )
    _require(
        seal.get("kind") == "curry_option_confirmation_stage_input_seal"
        and seal.get("context") == profile.confirmation_context
        and seal.get("stage") == 1
        and seal.get("input_sha256") == stage_input_hash,
        "confirmation_stage_seal_invalid",
    )
    _require(
        manifest.get("stage1_request_sha256") == request_hash
        and prepared.get("stage1_request_sha256") == request_hash
        and prepared.get("stage1_input_sha256") == stage_input_hash,
        "confirmation_request_prepared_binding_invalid",
    )
    ledger_path = (profile.confirmation_relative / "research/calls.jsonl").as_posix()
    ledger = repo / ledger_path
    _require(not ledger.exists() and not ledger.is_symlink(), "confirmation_charge_ledger_unexpected")
    report["old_scope"] = {
        "scope": CONFIRMATION_SCOPE,
        "manifest_sha256": manifest_hash,
        "context": profile.confirmation_context,
        "request_limit": RESERVED_CALLS,
        "window_seconds": 7200,
        "prepared": True,
        "sealed_unconsumed_slots": RESERVED_CALLS,
        "actual_new_consumed": None,
        "actual_cumulative_consumed": None,
        "actual_unknown": None,
        "charge_ledger_state": "absent",
    }
    report["historical_exit_observation"]["observation_exit_code_claimed"] = observation["exit_code"]
    if spec.version == 3:
        report["compatibility_basis"]["ledger_path_semantics"] = {
            "source_field": "stage-1-input.ledger",
            "stored_as_absolute_windows_path": True,
            "resolved_relative_path": (profile.confirmation_relative / "research/calls.jsonl").as_posix(),
        }
        report["compatibility_basis"]["confirmation_inventory"] = {
            "input_role_rows": len(confirmation_roles),
            "unique_physical_paths": len(confirmation_rows),
            "evidence_role_rows": len(evidence_rows),
        }
    return records


def _verify_historical_ledgers(
    repo: Path, paths: dict[str, dict[str, Any]], ledger_pins: dict[str, dict[str, Any]],
    spec: _VersionSpec | None = None, report: dict[str, Any] | None = None,
    profile: _Profile | None = None,
) -> list[dict[str, Any]]:
    spec = spec or _version_spec(1)
    profile = profile or _production_profile()
    _require(len(ledger_pins) == HISTORICAL_LEDGER_COUNT, "historical_ledger_set_invalid")
    records = []
    for path, pin in sorted(ledger_pins.items()):
        if spec.version == 3 and path == profile.tenki_ledger_relative.as_posix():
            _require(
                pin.get("role") == "tenki_validation_ledger"
                and pin["expected_sha256"] == profile.tenki_ledger_sha256,
                "tenki_validation_ledger_pin_invalid",
            )
            from ygo_eval.native_curry_option_validation import _curry_evidence_hash, _snapshot_curry_evidence
            evidence_root = repo / profile.tenki_evidence_relative
            evidence_snapshot = _snapshot_curry_evidence(evidence_root)
            directory_hash = _curry_evidence_hash(evidence_snapshot)
            _require(directory_hash == profile.tenki_evidence_sha256, "historical_ledger_09_directory_hash_mismatch")
            directory_path = profile.tenki_evidence_relative.as_posix()
            directory_input = paths.get(directory_path)
            ledger_path = profile.tenki_ledger_relative.as_posix()
            _require(
                directory_input is not None
                and directory_input.get("sha256") == profile.tenki_evidence_sha256
                and directory_input.get("bytes") == 0
                and ledger_path not in paths,
                "tenki_validation_directory_input_binding_invalid",
            )
            acceptance_path = profile.tenki_acceptance_relative.as_posix()
            acceptance_pin = paths.get(acceptance_path)
            _require(
                acceptance_pin is not None and acceptance_pin.get("sha256") == profile.tenki_acceptance_sha256
                and type(acceptance_pin.get("bytes")) is int,
                "tenki_validation_acceptance_input_binding_invalid",
            )
            acceptance_raw, acceptance_hash = _read(repo, acceptance_path, profile.tenki_acceptance_sha256)
            _require(len(acceptance_raw) == acceptance_pin["bytes"], "historical_ledger_09_acceptance_size_invalid")
            acceptance = _parse(acceptance_raw, "historical_ledger_09_acceptance_invalid")
            native = acceptance.get("native")
            _require(
                acceptance.get("schema_version") == 1
                and acceptance.get("kind") == "tenki_placement_validation_acceptance"
                and acceptance.get("scope") == "tenki-placement-validation-v1"
                and acceptance.get("status") == "completed_and_paused"
                and isinstance(native, dict)
                and native.get("ledger_path") == "research/calls.jsonl"
                and native.get("ledger_sha256") == profile.tenki_ledger_sha256
                and native.get("successful") is True
                and native.get("new_consumed") == 6
                and native.get("unknown") == 0
                and native.get("cumulative_consumed") == HISTORICAL_CONSUMED
                and native.get("stages_completed") == 6 and native.get("stages_total") == 6
                and native.get("scope_sealed") is True
                and native.get("replay_matches") == {"false_branch_stage4": True, "true_branch_stage6": True},
                "historical_ledger_09_acceptance_semantics_invalid",
            )
            ledger_raw, ledger_hash = _read(repo, ledger_path, profile.tenki_ledger_sha256)
            _require(
                _sha(ledger_raw) == profile.tenki_ledger_sha256
                and evidence_snapshot.get("research/calls.jsonl") == profile.tenki_ledger_sha256,
                "historical_ledger_09_bytes_invalid",
            )
            records.extend((
                {"role": "tenki_validation_directory_evidence", "path": directory_path, "sha256": directory_hash, "bytes": 0},
                {"role": "tenki_validation_acceptance", "path": acceptance_path, "sha256": acceptance_hash, "bytes": len(acceptance_raw)},
                {"role": pin["role"], "path": ledger_path, "sha256": ledger_hash, "bytes": len(ledger_raw)},
            ))
            if report is not None:
                report["compatibility_basis"]["tenki_validation_ledger"]["directory_evidence_sha256"] = directory_hash
            continue
        item = paths.get(path)
        _require(item is not None and item["sha256"] == pin["expected_sha256"], "historical_ledger_v2_binding_invalid")
        _require(item["bytes"] is not None, "historical_ledger_size_missing")
        raw, found = _read(repo, path, pin["expected_sha256"])
        _require(item["bytes"] == len(raw), "historical_ledger_size_mismatch")
        records.append({"role": pin["role"], "path": path, "sha256": found, "bytes": len(raw)})
    ledger_records = [
        row for row in records
        if row["role"].startswith("historical_ledger_") or row["role"] == "tenki_validation_ledger"
    ]
    _require(len({row["path"] for row in ledger_records}) == HISTORICAL_LEDGER_COUNT, "historical_ledger_record_set_invalid")
    if spec.version == 3:
        _require(
            sum(row["role"] == "tenki_validation_directory_evidence" for row in records) == 1
            and sum(row["role"] == "tenki_validation_acceptance" for row in records) == 1,
            "tenki_validation_evidence_record_set_invalid",
        )
    return records


def _snapshot_pinned_files(
    repo: Path, pins: dict[str, dict[str, Any]], profile: _Profile | None = None,
    spec: _VersionSpec | None = None,
) -> dict[str, dict[str, Any]]:
    profile = profile or _production_profile()
    spec = spec or _version_spec(1)
    snapshot: dict[str, dict[str, Any]] = {}
    for path in sorted(pins):
        if spec.version == 3 and path == profile.tenki_evidence_relative.as_posix():
            from ygo_eval.native_curry_option_validation import _curry_evidence_hash, _snapshot_curry_evidence

            evidence = _snapshot_curry_evidence(repo / profile.tenki_evidence_relative)
            snapshot[path] = {"sha256": _curry_evidence_hash(evidence), "bytes": 0, "kind": "evidence_directory", "files": evidence}
        else:
            raw = _safe_relative(repo, path).read_bytes()
            snapshot[path] = {"sha256": _sha(raw), "bytes": len(raw), "kind": "file"}
            if spec.version == 3 and path == profile.tenki_ledger_relative.as_posix():
                from ygo_eval.native_curry_option_validation import _curry_evidence_hash, _snapshot_curry_evidence

                evidence = _snapshot_curry_evidence(repo / profile.tenki_evidence_relative)
                snapshot[profile.tenki_evidence_relative.as_posix()] = {
                    "sha256": _curry_evidence_hash(evidence), "bytes": 0,
                    "kind": "evidence_directory", "files": evidence,
                }
    return snapshot


def _tool_bundle(
    repo: Path, workspace_identity: str, tool_files: tuple[str, ...] = _TOOL_FILES,
) -> tuple[bytes, bytes, dict[str, Any]]:
    files: dict[str, bytes] = {}
    for name in tool_files:
        path = _safe_relative(repo, name)
        files[name] = path.read_bytes()
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    identity = _sha(_canonical({"files": hashes, "workspace_identity": workspace_identity}))
    listing = {
        "schema_version": 1,
        "kind": "curry_consumption_reservation_tool_file_list",
        "tool_identity": identity,
        "workspace_identity": workspace_identity,
        "files": [{"path": name, "sha256": hashes[name]} for name in sorted(hashes)],
    }
    list_raw = _pretty(listing)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, files[name])
    archive_raw = buffer.getvalue()
    metadata = {
        "identity": identity,
        "archive_path": "tool-source.zip",
        "archive_sha256": _sha(archive_raw),
        "file_list_path": "tool-source-file-list.json",
        "file_list_sha256": _sha(list_raw),
        "file_count": len(files),
        "member_sha256": hashes,
        "workspace_identity": workspace_identity,
    }
    return archive_raw, list_raw, metadata


def _verify_tool_bundle(
    root: Path, tool: dict[str, Any], tool_files: tuple[str, ...] = _TOOL_FILES,
) -> bool:
    _validate_tool_metadata(tool, tool_files)
    archive_raw, archive_hash = _read(root, tool["archive_path"], tool["archive_sha256"])
    list_raw, list_hash = _read(root, tool["file_list_path"], tool["file_list_sha256"])
    listing = _parse(list_raw, "tool_bundle_list_invalid")
    _require(
        set(listing) == {"schema_version", "kind", "tool_identity", "workspace_identity", "files"}
        and listing.get("schema_version") == 1
        and listing.get("kind") == "curry_consumption_reservation_tool_file_list",
        "tool_bundle_list_invalid",
    )
    rows = listing.get("files")
    _require(
        list_hash == tool["file_list_sha256"]
        and listing.get("tool_identity") == tool["identity"]
        and listing.get("workspace_identity") == tool["workspace_identity"]
        and isinstance(rows, list) and len(rows) == tool["file_count"],
        "tool_bundle_list_invalid",
    )
    hashes: dict[str, str] = {}
    for row in rows:
        _require(
            isinstance(row, dict) and set(row) == {"path", "sha256"}
            and isinstance(row.get("path"), str) and row["path"] not in hashes
            and isinstance(row.get("sha256"), str) and HASH.fullmatch(row["sha256"]) is not None,
            "tool_bundle_list_entry_invalid",
        )
        hashes[row["path"]] = row["sha256"]
    _require(
        tuple(sorted(hashes)) == tuple(sorted(tool_files))
        and hashes == tool["member_sha256"]
        and _sha(_canonical({"files": hashes, "workspace_identity": tool["workspace_identity"]})) == tool["identity"],
        "tool_bundle_identity_invalid",
    )
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names)) and set(names) == set(hashes), "tool_bundle_membership_invalid")
            for name, expected in hashes.items():
                _require(_sha(archive.read(name)) == expected, "tool_bundle_member_hash_mismatch")
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("tool_bundle_archive_invalid") from None
    return archive_hash == tool["archive_sha256"]


def _reservation_id(scope: str, manifest_sha256: str, context: str) -> str:
    return _sha(_canonical({
        "scope": scope,
        "manifest_sha256": manifest_sha256,
        "context": context,
        "policy_id": POLICY_ID,
        "reserved_calls": RESERVED_CALLS,
    }))


def _new_report(
    tool: dict[str, Any] | None = None, *, version: int = 1, profile: _Profile | None = None,
) -> dict[str, Any]:
    spec = _version_spec(version)
    profile = profile or _production_profile()
    report = {
        "schema_version": spec.version,
        "kind": spec.kind,
        "status": "incomplete",
        "failure_checkpoint": None,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "anchors": {"latest_delivery_sha256": None, "real_v2_report_sha256": None, "v2_acceptance_sha256": None, "source_identity": None, "source_file_count": None},
        "checks": {name: "not_run" for name in spec.checks},
        "historical_ledgers": {"ledger_count": None, "consumed": None, "unknown": None, "verified_by_anchored_read_only_protection": False},
        "old_scope": {"scope": CONFIRMATION_SCOPE, "manifest_sha256": None, "context": None, "request_limit": RESERVED_CALLS, "window_seconds": 7200, "prepared": None, "sealed_unconsumed_slots": RESERVED_CALLS, "actual_new_consumed": None, "actual_cumulative_consumed": None, "actual_unknown": None, "charge_ledger_state": "unknown"},
        "historical_exit_observation": {"observation_exit_code_claimed": None, "archived_static_return_code": None, "historical_actual_exit_code": None, "historical_actual_exit_code_certified": False},
        "reservation": {"policy_id": POLICY_ID, "requested_calls": RESERVED_CALLS, "recorded": False, "reservation_id": None, "duplicate_count": 0},
        "planning_basis": {"certified_historical_consumed": None, "risk_reserve_calls": RESERVED_CALLS, "planned_total": None, "actual_all_history_cumulative": None},
        "inputs": [],
        "stability": {
            "baseline_tree": "not_collected",
            "v2_report_tree": "not_collected",
            "confirmation_tree": "not_collected",
            "historical_ledgers": "not_collected",
            "historical_ledger_count": None,
            "confirmation_charge_ledger_absent_before": None,
            "confirmation_charge_ledger_absent_after": None,
            "status": "not_collected",
        },
        "tool": tool,
        "native_calls": 0,
        "execution_ready": False,
        "qualifications": dict(_QUALIFICATIONS),
        "diagnostics": [],
        "elapsed_seconds": 0.0,
    }
    if version == 2:
        report["previous_failed_attempt"] = {
            "report_path": spec.previous_failure_relative.as_posix(),
            "report_sha256": None,
            "status": None,
            "failure_checkpoint": None,
            "diagnostic": None,
            "reservation_recorded": None,
            "reservation_id": None,
            "planned_total": None,
            "tool_archive_sha256": None,
            "tool_file_list_sha256": None,
            "archived_bad_acceptance_constant": None,
            "historical_actual_exit_code": None,
        }
        report["stability"]["previous_failed_attempt_tree"] = "not_collected"
    elif version == 3:
        report["previous_failed_attempts"] = {
            "v1": None,
            "v2": None,
        }
        report["recovery_source_archives"] = {
            "corrected_534": None,
            "v2_audit_535": None,
            "v2_final_536": None,
            "allowed_document_changes": list(V3_DOCUMENT_SOURCE_CHANGES),
        }
        report["compatibility_basis"] = {
            "review_field_sources": {
                "review_quality_source": "independent-review.json",
                "review_public_cli_bypass_found": None,
                "acceptance_public_cli_bypass_found_source": "acceptance.review.public_cli_bypass_found",
                "acceptance_public_cli_bypass_found": None,
            },
            "ledger_path_semantics": {
                "source_field": "stage-1-input.ledger",
                "stored_as_absolute_windows_path": None,
                "resolved_relative_path": None,
            },
            "confirmation_inventory": {
                "input_role_rows": None,
                "unique_physical_paths": None,
                "evidence_role_rows": None,
            },
            "tenki_validation_ledger": {
                "authentication_method": "evidence_directory_acceptance_and_protection",
                "direct_file_input_present": False,
                "directory_path": profile.tenki_evidence_relative.as_posix(),
                    "directory_evidence_expected_sha256": profile.tenki_evidence_sha256,
                    "directory_evidence_sha256": None,
                "acceptance_path": profile.tenki_acceptance_relative.as_posix(),
                "acceptance_sha256": profile.tenki_acceptance_sha256,
                "ledger_path": profile.tenki_ledger_relative.as_posix(),
                "ledger_sha256": profile.tenki_ledger_sha256,
            },
        }
        report["stability"].update({
            "previous_failed_v1_tree": "not_collected",
            "previous_failed_v2_tree": "not_collected",
            "v2_recovery_sources_tree": "not_collected",
        })
    return report


def _validate_tool_metadata(tool: Any, tool_files: tuple[str, ...] = _TOOL_FILES) -> None:
    expected = {
        "identity", "archive_path", "archive_sha256", "file_list_path",
        "file_list_sha256", "file_count", "member_sha256", "workspace_identity",
    }
    hashes = tool.get("member_sha256") if isinstance(tool, dict) else None
    _require(
        isinstance(tool, dict) and set(tool) == expected
        and tool.get("archive_path") == "tool-source.zip"
        and tool.get("file_list_path") == "tool-source-file-list.json"
        and tool.get("file_count") == len(tool_files)
        and isinstance(hashes, dict) and set(hashes) == set(tool_files)
        and all(isinstance(value, str) and HASH.fullmatch(value) is not None for value in hashes.values())
        and all(
            isinstance(tool.get(name), str) and HASH.fullmatch(tool[name]) is not None
            for name in ("identity", "archive_sha256", "file_list_sha256", "workspace_identity")
        ),
        "tool_bundle_metadata_invalid",
    )
    _require(
        tool["identity"] == _sha(_canonical({"files": hashes, "workspace_identity": tool["workspace_identity"]})),
        "tool_bundle_identity_invalid",
    )


def _validate_report(
    report: dict[str, Any], profile: _Profile | None = None,
    spec: _VersionSpec | None = None,
) -> None:
    version = report.get("schema_version") if isinstance(report, dict) else None
    _require(version in {1, 2, 3}, "reservation_report_contract_invalid")
    spec = spec or _version_spec(version)
    profile = profile or _production_profile()
    expected_top = {
        "schema_version", "kind", "status", "failure_checkpoint", "created_at_utc",
        "anchors", "checks", "historical_ledgers", "old_scope",
        "historical_exit_observation", "reservation", "planning_basis", "inputs",
        "stability", "tool", "native_calls", "execution_ready", "qualifications",
        "diagnostics", "elapsed_seconds",
    }
    if version == 2:
        expected_top.add("previous_failed_attempt")
    if version == 3:
        expected_top.update({"previous_failed_attempts", "recovery_source_archives", "compatibility_basis"})
    _require(isinstance(report, dict) and set(report) == expected_top, "reservation_report_contract_invalid")
    _require(report.get("kind") == spec.kind, "reservation_report_contract_invalid")
    _require(report.get("status") in {"passed", "failed", "incomplete"}, "reservation_report_contract_invalid")
    _require(
        report.get("failure_checkpoint") is None or report["failure_checkpoint"] in spec.checks,
        "reservation_report_contract_invalid",
    )
    _require(report.get("native_calls") == 0 and report.get("execution_ready") is False and report.get("qualifications") == _QUALIFICATIONS, "reservation_qualification_invalid")
    _require(report.get("reservation", {}).get("policy_id") == POLICY_ID and report["reservation"].get("requested_calls") == RESERVED_CALLS, "reservation_policy_invalid")
    _require(set(report.get("checks", {})) == set(spec.checks), "reservation_check_set_invalid")
    _require(all(value in {"not_run", "passed", "failed"} for value in report["checks"].values()), "reservation_check_status_invalid")
    if version == 3 and report["status"] in {"failed", "incomplete"}:
        checkpoint = report["failure_checkpoint"]
        _require(checkpoint in spec.checks, "reservation_failure_checkpoint_missing")
        checkpoint_index = spec.checks.index(checkpoint)
        expected_statuses = {
            name: "passed" if index < checkpoint_index
            else "failed" if index == checkpoint_index
            else "not_run"
            for index, name in enumerate(spec.checks)
        }
        _require(report["checks"] == expected_statuses, "reservation_failure_check_order_invalid")
    _require(report.get("old_scope", {}).get("scope") == CONFIRMATION_SCOPE and report["old_scope"].get("actual_new_consumed") is None and report["old_scope"].get("actual_cumulative_consumed") is None and report["old_scope"].get("actual_unknown") is None, "old_scope_unknown_accounting_invalid")
    _require(report.get("planning_basis", {}).get("actual_all_history_cumulative") is None, "actual_total_must_remain_unknown")
    if report.get("tool") is not None:
        _validate_tool_metadata(report["tool"], spec.tool_files)
    if version == 2:
        previous = report.get("previous_failed_attempt")
        _require(
            isinstance(previous, dict)
            and set(previous) == {
                "report_path", "report_sha256", "status", "failure_checkpoint", "diagnostic",
                "reservation_recorded", "reservation_id", "planned_total", "tool_archive_sha256",
                "tool_file_list_sha256", "archived_bad_acceptance_constant", "historical_actual_exit_code",
            }
            and previous.get("report_path") == spec.previous_failure_relative.as_posix()
            and (previous.get("report_sha256") is None or HASH.fullmatch(previous["report_sha256"]) is not None)
            and (previous.get("tool_archive_sha256") is None or HASH.fullmatch(previous["tool_archive_sha256"]) is not None)
            and (previous.get("tool_file_list_sha256") is None or HASH.fullmatch(previous["tool_file_list_sha256"]) is not None)
            and previous.get("historical_actual_exit_code") is None,
            "previous_failure_report_contract_invalid",
        )
        bad_constant = previous.get("archived_bad_acceptance_constant")
        _require(
            bad_constant is None or (isinstance(bad_constant, str) and re.fullmatch(r"[a-f0-9]{63}", bad_constant) is not None),
            "previous_failure_constant_invalid",
        )
    if version == 3:
        previous = report.get("previous_failed_attempts")
        _require(
            isinstance(previous, dict) and set(previous) == {"v1", "v2"}
            and all(value is None or isinstance(value, dict) for value in previous.values()),
            "previous_failures_contract_invalid",
        )
        previous_v1, previous_v2 = previous["v1"], previous["v2"]
        _require(
            previous_v1 is None or set(previous_v1) == {
                "report_path", "report_sha256", "status", "failure_checkpoint", "diagnostic",
                "reservation_recorded", "reservation_id", "planned_total", "tool_archive_sha256",
                "tool_file_list_sha256", "archived_bad_acceptance_constant", "historical_actual_exit_code",
            },
            "previous_v1_failure_shape_invalid",
        )
        _require(
            previous_v2 is None or set(previous_v2) == {
                "report_path", "report_sha256", "status", "failure_checkpoint", "diagnostic",
                "reservation_recorded", "reservation_id", "planned_total", "tool_archive_sha256",
                "tool_file_list_sha256", "historical_actual_exit_code",
            },
            "previous_v2_failure_shape_invalid",
        )
        sources = report.get("recovery_source_archives")
        _require(
            isinstance(sources, dict) and set(sources) == {
                "corrected_534", "v2_audit_535", "v2_final_536", "allowed_document_changes",
            }
            and sources["allowed_document_changes"] == list(V3_DOCUMENT_SOURCE_CHANGES)
            and all(sources[name] is None or isinstance(sources[name], dict) for name in (
                "corrected_534", "v2_audit_535", "v2_final_536",
            )),
            "recovery_source_archives_contract_invalid",
        )
        compatibility = report.get("compatibility_basis")
        _require(
            isinstance(compatibility, dict) and set(compatibility) == {
                "review_field_sources", "ledger_path_semantics", "confirmation_inventory",
                "tenki_validation_ledger",
            },
            "compatibility_basis_contract_invalid",
        )
    if report["status"] == "passed":
        _require(report.get("tool") is not None, "reservation_success_tool_binding_missing")
        _require(report["failure_checkpoint"] is None and all(value == "passed" for value in report["checks"].values()), "reservation_success_checks_invalid")
        stability = report["stability"]
        _require(
            stability.get("status") == "passed"
            and all(stability.get(name) == "passed" for name in (
                "baseline_tree", "v2_report_tree", "confirmation_tree", "historical_ledgers",
            ))
            and stability.get("historical_ledger_count") == HISTORICAL_LEDGER_COUNT
            and stability.get("confirmation_charge_ledger_absent_before") is True
            and stability.get("confirmation_charge_ledger_absent_after") is True,
            "reservation_success_stability_invalid",
        )
        if version == 2:
            _require(
                stability.get("previous_failed_attempt_tree") == "passed"
                and report["checks"]["previous_failed_attempt"] == "passed",
                "previous_failure_stability_invalid",
            )
            previous = report["previous_failed_attempt"]
            _require(
                previous.get("report_sha256") == spec.previous_failure_sha256
                and previous.get("status") == "failed"
                and previous.get("failure_checkpoint") == "latest_delivery_chain"
                and previous.get("diagnostic") == "delivery_anchor_mismatch"
                and previous.get("reservation_recorded") is False
                and previous.get("reservation_id") is None
                and previous.get("planned_total") is None
                and previous.get("archived_bad_acceptance_constant") == ARCHIVED_BAD_ACCEPTANCE_CONSTANT,
                "previous_failure_binding_invalid",
            )
        if version == 3:
            _require(
                stability.get("previous_failed_v1_tree") == "passed"
                and stability.get("previous_failed_v2_tree") == "passed"
                and stability.get("v2_recovery_sources_tree") == "passed"
                and report["checks"]["previous_failed_attempts"] == "passed"
                and report["checks"]["recovery_source_archives"] == "passed",
                "v3_previous_source_stability_invalid",
            )
            failures = report["previous_failed_attempts"]
            v1, v2 = failures["v1"], failures["v2"]
            _require(
                isinstance(v1, dict) and v1.get("report_sha256") == spec.previous_failure_sha256
                and v1.get("report_path") == spec.previous_failure_relative.as_posix()
                and v1.get("status") == "failed"
                and v1.get("failure_checkpoint") == "latest_delivery_chain"
                and v1.get("diagnostic") == "delivery_anchor_mismatch"
                and v1.get("reservation_recorded") is False and v1.get("reservation_id") is None
                and v1.get("planned_total") is None and v1.get("historical_actual_exit_code") is None
                and v1.get("archived_bad_acceptance_constant") == ARCHIVED_BAD_ACCEPTANCE_CONSTANT
                and isinstance(v2, dict) and v2.get("report_sha256") == spec.previous_v2_failure_sha256
                and v2.get("report_path") == spec.previous_v2_failure_relative.as_posix()
                and v2.get("status") == "failed"
                and v2.get("failure_checkpoint") == "latest_delivery_chain"
                and v2.get("diagnostic") == "independent_review_invalid"
                and v2.get("reservation_recorded") is False and v2.get("reservation_id") is None
                and v2.get("planned_total") is None and v2.get("historical_actual_exit_code") is None,
                "v3_previous_failure_binding_invalid",
            )
            for prior in (v1, v2):
                _require(
                    isinstance(prior.get("tool_archive_sha256"), str)
                    and HASH.fullmatch(prior["tool_archive_sha256"]) is not None
                    and isinstance(prior.get("tool_file_list_sha256"), str)
                    and HASH.fullmatch(prior["tool_file_list_sha256"]) is not None,
                    "v3_previous_failure_tool_binding_invalid",
                )
            source_rows = report["recovery_source_archives"]
            _require(
                all(isinstance(source_rows[name], dict) for name in (
                    "corrected_534", "v2_audit_535", "v2_final_536",
                )),
                "v3_recovery_archives_missing",
            )
            _require(
                report["compatibility_basis"] == {
                    "review_field_sources": {
                        "review_quality_source": "independent-review.json",
                        "review_public_cli_bypass_found": None,
                        "acceptance_public_cli_bypass_found_source": "acceptance.review.public_cli_bypass_found",
                        "acceptance_public_cli_bypass_found": False,
                    },
                    "ledger_path_semantics": {
                        "source_field": "stage-1-input.ledger",
                        "stored_as_absolute_windows_path": True,
                        "resolved_relative_path": (CONFIRMATION_RELATIVE / "research/calls.jsonl").as_posix(),
                    },
                    "confirmation_inventory": {
                        "input_role_rows": 64,
                        "unique_physical_paths": 43,
                        "evidence_role_rows": 40,
                    },
            "tenki_validation_ledger": {
                        "authentication_method": "evidence_directory_acceptance_and_protection",
                        "direct_file_input_present": False,
                        "directory_path": profile.tenki_evidence_relative.as_posix(),
                        "directory_evidence_expected_sha256": profile.tenki_evidence_sha256,
                        "directory_evidence_sha256": profile.tenki_evidence_sha256,
                        "acceptance_path": profile.tenki_acceptance_relative.as_posix(),
                        "acceptance_sha256": profile.tenki_acceptance_sha256,
                        "ledger_path": profile.tenki_ledger_relative.as_posix(),
                        "ledger_sha256": profile.tenki_ledger_sha256,
                    },
                },
                "v3_compatibility_basis_invalid",
            )
        manifest_hash = report["old_scope"].get("manifest_sha256")
        context = report["old_scope"].get("context")
        _require(
            isinstance(manifest_hash, str) and HASH.fullmatch(manifest_hash) is not None
            and isinstance(context, str) and HASH.fullmatch(context) is not None
            and report["reservation"].get("recorded") is True
            and report["reservation"].get("duplicate_count") == 1
            and report["reservation"].get("reservation_id")
            == _reservation_id(CONFIRMATION_SCOPE, manifest_hash, context),
            "reservation_success_binding_invalid",
        )
        _require(report["historical_ledgers"] == {"ledger_count": HISTORICAL_LEDGER_COUNT, "consumed": HISTORICAL_CONSUMED, "unknown": HISTORICAL_UNKNOWN, "verified_by_anchored_read_only_protection": True}, "reservation_history_invalid")
        _require(report["planning_basis"] == {"certified_historical_consumed": HISTORICAL_CONSUMED, "risk_reserve_calls": RESERVED_CALLS, "planned_total": HISTORICAL_CONSUMED + RESERVED_CALLS, "actual_all_history_cumulative": None}, "planning_basis_invalid")
        _require(report["historical_exit_observation"] == {"observation_exit_code_claimed": 1, "archived_static_return_code": 2, "historical_actual_exit_code": None, "historical_actual_exit_code_certified": False}, "historical_exit_provenance_invalid")
    else:
        _require(report["reservation"].get("recorded") is False and report["reservation"].get("reservation_id") is None and report["reservation"].get("duplicate_count") == 0 and report["planning_basis"].get("planned_total") is None, "failed_reservation_must_not_be_recorded")
        _require(
            report["historical_ledgers"] == {
                "ledger_count": None,
                "consumed": None,
                "unknown": None,
                "verified_by_anchored_read_only_protection": False,
            }
            and report["planning_basis"].get("certified_historical_consumed") is None,
            "failed_reservation_history_must_remain_unknown",
        )
    _require(isinstance(report.get("inputs"), list) and isinstance(report.get("diagnostics"), list), "reservation_report_contract_invalid")
    if version in {2, 3} and report["status"] == "passed":
        _require(bool(report["inputs"]), "reservation_success_inputs_missing")
    if version == 3 and report["status"] == "passed":
        roles = {item.get("role") for item in report["inputs"] if isinstance(item, dict)}
        _require(set(spec.required_input_roles) <= roles, "reservation_success_required_sources_missing")
        confirmation_prefix = profile.confirmation_relative.as_posix() + "/"
        confirmation_rows = [
            item for item in report["inputs"]
            if item["path"].startswith(confirmation_prefix)
        ]
        # Keep the independently pinned V2 acceptance role explicit. In the
        # real source tree it lives outside the old confirmation directory;
        # counting it as a confirmation inventory row would conflate two
        # independently authenticated roots.
        prior_acceptance_aliases = [
            item for item in report["inputs"]
            if item["role"] == "authenticated_prior_v2_acceptance"
        ]
        _require(
            len(prior_acceptance_aliases) == 1
            and prior_acceptance_aliases[0]["path"] == profile.v2_acceptance_relative.as_posix(),
            "authenticated_prior_v2_acceptance_input_invalid",
        )
        evidence_rows = [
            item for item in confirmation_rows
            if item["role"].startswith("confirmation_evidence_file_")
        ]
        _require(
            len(confirmation_rows) == 64
            and len({item["path"] for item in confirmation_rows}) == 43
            and len(evidence_rows) == 40
            and report["compatibility_basis"].get("confirmation_inventory") == {
                "input_role_rows": 64,
                "unique_physical_paths": 43,
                "evidence_role_rows": 40,
            },
            "confirmation_input_role_inventory_invalid",
        )
    seen_roles: set[str] = set()
    seen_paths: dict[str, tuple[str, int]] = {}
    for item in report["inputs"]:
        _require(
            isinstance(item, dict) and set(item) == {"role", "path", "sha256", "bytes"}
            and isinstance(item["role"], str) and item["role"] not in seen_roles
            and isinstance(item["path"], str) and HASH.fullmatch(item["sha256"]) is not None
            and type(item["bytes"]) is int and item["bytes"] >= 0,
            "reservation_input_record_invalid",
        )
        name = PurePosixPath(item["path"])
        _require(not name.is_absolute() and ".." not in name.parts and "\\" not in item["path"] and ":" not in item["path"], "reservation_input_path_invalid")
        binding = (item["sha256"], item["bytes"])
        _require(item["path"] not in seen_paths or seen_paths[item["path"]] == binding, "reservation_input_duplicate_conflict")
        seen_roles.add(item["role"])
        seen_paths[item["path"]] = binding


def _write_exclusive(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _snapshot_tree(root: Path) -> dict[str, dict[str, Any]]:
    root = safe_path(root, file=False)
    snapshot: dict[str, dict[str, Any]] = {}
    for item in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        if item.is_dir():
            safe_path(item, file=False)
            snapshot[item.relative_to(root).as_posix()] = {"kind": "directory"}
        else:
            raw = safe_path(item).read_bytes()
            snapshot[item.relative_to(root).as_posix()] = {"kind": "file", "sha256": _sha(raw), "bytes": len(raw)}
    return snapshot


def _verify_output_tree(root: Path) -> dict[str, dict[str, Any]]:
    snapshot = _snapshot_tree(root)
    files = {name for name, row in snapshot.items() if row["kind"] == "file"}
    directories = {name for name, row in snapshot.items() if row["kind"] == "directory"}
    required = {REPORT_NAME, "tool-source.zip", "tool-source-file-list.json"}
    _require(required <= files and files <= _OUTPUT_FILES, "reservation_output_file_set_invalid")
    _require(directories <= {"delivery"} and ("delivery" in directories) == any(name.startswith("delivery/") for name in files), "reservation_output_directory_set_invalid")
    return snapshot


def _verify_previous_failed_attempt(
    repo: Path, spec: _VersionSpec, report: dict[str, Any],
) -> None:
    """Bind the immutable v1 failed attempt and inspect its archived source as data."""
    _require(spec.version in {2, 3} and spec.previous_failure_relative is not None, "previous_failure_spec_invalid")
    relative = spec.previous_failure_relative.as_posix()
    raw, found = _read(repo, relative, spec.previous_failure_sha256)
    old_report = _parse(raw, "previous_failure_report_invalid")
    _validate_report(old_report)
    _require(
        old_report.get("schema_version") == 1
        and old_report.get("kind") == "curry_consumption_reservation"
        and old_report.get("status") == "failed"
        and old_report.get("failure_checkpoint") == "latest_delivery_chain"
        and old_report.get("diagnostics") == ["delivery_anchor_mismatch"]
        and old_report.get("reservation") == {
            "policy_id": POLICY_ID, "requested_calls": RESERVED_CALLS,
            "recorded": False, "reservation_id": None, "duplicate_count": 0,
        }
        and old_report.get("planning_basis", {}).get("planned_total") is None
        and old_report.get("historical_ledgers") == {
            "ledger_count": None, "consumed": None, "unknown": None,
            "verified_by_anchored_read_only_protection": False,
        }
        and old_report.get("old_scope", {}).get("actual_new_consumed") is None
        and old_report.get("old_scope", {}).get("actual_cumulative_consumed") is None
        and old_report.get("old_scope", {}).get("actual_unknown") is None,
        "previous_failure_binding_invalid",
    )

    previous_root = repo / spec.previous_failure_relative.parent
    tool = old_report.get("tool")
    _require(isinstance(tool, dict), "previous_failure_tool_missing")
    archive_hash = _verify_tool_bundle(previous_root, tool, _TOOL_FILES)
    _require(archive_hash, "previous_failure_tool_archive_mismatch")
    archive_raw, _ = _read(previous_root, tool["archive_path"], tool["archive_sha256"])
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
            module_raw = archive.read("python/ygo_eval/curry_consumption_reservation.py")
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("previous_failure_tool_source_invalid") from None
    matches = re.findall(rb'(?m)^ACCEPTANCE_SHA256\s*=\s*"([a-f0-9]+)"\s*$', module_raw)
    _require(matches and matches[0].decode("ascii") == ARCHIVED_BAD_ACCEPTANCE_CONSTANT, "previous_failure_archived_constant_mismatch")

    previous_record = {
        "report_path": relative,
        "report_sha256": found,
        "status": old_report["status"],
        "failure_checkpoint": old_report["failure_checkpoint"],
        "diagnostic": old_report["diagnostics"][0],
        "reservation_recorded": old_report["reservation"]["recorded"],
        "reservation_id": old_report["reservation"]["reservation_id"],
        "planned_total": old_report["planning_basis"]["planned_total"],
        "tool_archive_sha256": tool["archive_sha256"],
        "tool_file_list_sha256": tool["file_list_sha256"],
        "archived_bad_acceptance_constant": matches[0].decode("ascii"),
        "historical_actual_exit_code": None,
    }
    if spec.version == 2:
        report["previous_failed_attempt"] = previous_record
        prefix = "previous_failed_"
    else:
        report["previous_failed_attempts"]["v1"] = previous_record
        prefix = "previous_v1_failed_"
    report["inputs"].extend((
        _record(repo, prefix + "reservation_report", relative, found),
        _record(repo, prefix + "tool_archive", (spec.previous_failure_relative.parent / tool["archive_path"]).as_posix(), tool["archive_sha256"]),
        _record(repo, prefix + "tool_file_list", (spec.previous_failure_relative.parent / tool["file_list_path"]).as_posix(), tool["file_list_sha256"]),
    ))


def _verify_v3_previous_v2_failure(repo: Path, spec: _VersionSpec, report: dict[str, Any]) -> None:
    _require(spec.version == 3 and spec.previous_v2_failure_relative is not None, "v2_previous_failure_spec_invalid")
    relative = spec.previous_v2_failure_relative.as_posix()
    raw, found = _read(repo, relative, spec.previous_v2_failure_sha256)
    old = _parse(raw, "v2_previous_failure_report_invalid")
    _validate_report(old)
    _require(
        old.get("schema_version") == 2
        and old.get("kind") == "curry_consumption_reservation_v2"
        and old.get("status") == "failed"
        and old.get("failure_checkpoint") == "latest_delivery_chain"
        and old.get("diagnostics") == ["independent_review_invalid"]
        and old.get("previous_failed_attempt", {}).get("report_sha256") == spec.previous_failure_sha256
        and old.get("previous_failed_attempt", {}).get("reservation_recorded") is False
        and old.get("reservation") == {
            "policy_id": POLICY_ID, "requested_calls": RESERVED_CALLS,
            "recorded": False, "reservation_id": None, "duplicate_count": 0,
        }
        and old.get("planning_basis", {}).get("planned_total") is None
        and old.get("historical_ledgers") == {
            "ledger_count": None, "consumed": None, "unknown": None,
            "verified_by_anchored_read_only_protection": False,
        }
        and old.get("old_scope", {}).get("actual_new_consumed") is None
        and old.get("old_scope", {}).get("actual_cumulative_consumed") is None
        and old.get("old_scope", {}).get("actual_unknown") is None,
        "v2_previous_failure_binding_invalid",
    )
    tool = old.get("tool")
    _require(isinstance(tool, dict), "v2_previous_failure_tool_missing")
    _verify_tool_bundle(repo / spec.previous_v2_failure_relative.parent, tool, _V2_TOOL_FILES)
    report["previous_failed_attempts"]["v2"] = {
        "report_path": relative,
        "report_sha256": found,
        "status": old["status"],
        "failure_checkpoint": old["failure_checkpoint"],
        "diagnostic": old["diagnostics"][0],
        "reservation_recorded": old["reservation"]["recorded"],
        "reservation_id": old["reservation"]["reservation_id"],
        "planned_total": old["planning_basis"]["planned_total"],
        "tool_archive_sha256": tool["archive_sha256"],
        "tool_file_list_sha256": tool["file_list_sha256"],
        "historical_actual_exit_code": None,
    }
    report["inputs"].extend((
        _record(repo, "previous_v2_failed_reservation_report", relative, found),
        _record(repo, "previous_v2_failed_tool_archive", (spec.previous_v2_failure_relative.parent / tool["archive_path"]).as_posix(), tool["archive_sha256"]),
        _record(repo, "previous_v2_failed_tool_file_list", (spec.previous_v2_failure_relative.parent / tool["file_list_path"]).as_posix(), tool["file_list_sha256"]),
    ))


def _versioned_source_checks(
    repo: Path, profile: _Profile, spec: _VersionSpec, report: dict[str, Any],
) -> None:
    if spec.version == 1:
        _source_checks(repo, profile, report, spec)
        return
    _require(spec.version in {2, 3}, "reservation_report_version_invalid")
    if spec.version == 3:
        _version3_source_checks(repo, profile, spec, report)
        return
    _require(spec.previous_failure_relative is not None, "previous_failure_spec_invalid")
    previous_root = repo / spec.previous_failure_relative.parent
    before: dict[str, dict[str, Any]] | None = None
    report["failure_checkpoint"] = "previous_failed_attempt"
    report["stability"]["previous_failed_attempt_tree"] = "pending"
    try:
        before = _snapshot_tree(previous_root)
        _verify_previous_failed_attempt(repo, spec, report)
        report["checks"]["previous_failed_attempt"] = "passed"
        _source_checks(repo, profile, report, spec)
    finally:
        if before is None:
            status = "not_collected"
        else:
            try:
                status = "passed" if _snapshot_tree(previous_root) == before else "failed"
            except (OSError, ValueError):
                status = "recheck_failed"
        report["stability"]["previous_failed_attempt_tree"] = status
        if status != "passed":
            report["stability"]["status"] = "failed"
            if report["failure_checkpoint"] == "input_stability":
                report["checks"]["input_stability"] = "failed"
                raise ValueError("previous_failure_input_drift")


def _snapshot_v3_recovery_sources(
    repo: Path, spec: _VersionSpec, profile: _Profile | None = None,
) -> dict[str, Any]:
    from ygo_eval import curry_input_recovery_audit as recovery

    profile = profile or _production_profile()
    _require(spec.previous_v2_acceptance_relative is not None, "v2_recovery_acceptance_spec_invalid")
    acceptance = _safe_relative(repo, spec.previous_v2_acceptance_relative.as_posix()).read_bytes()
    v2_acceptance_path = _absolute(repo / profile.v2_acceptance_relative)
    if v2_acceptance_path.exists() or v2_acceptance_path.is_symlink():
        v2_acceptance = safe_path(v2_acceptance_path).read_bytes()
        v2_acceptance_snapshot = {
            "state": "present", "sha256": _sha(v2_acceptance), "bytes": len(v2_acceptance),
        }
    else:
        v2_acceptance_snapshot = {"state": "missing"}
    roots = (spec.recovery_archives[1][0].parent, spec.recovery_archives[2][0].parent)
    return {
        "v2_failure_acceptance": {"sha256": _sha(acceptance), "bytes": len(acceptance)},
        "v2_validation_acceptance": v2_acceptance_snapshot,
        "v2_audit_source": recovery._snapshot_tree(repo / roots[0]),
        "v2_final_source": recovery._snapshot_tree(repo / roots[1]),
    }


def _version3_source_checks(
    repo: Path, profile: _Profile, spec: _VersionSpec, report: dict[str, Any],
) -> None:
    _require(spec.previous_failure_relative is not None, "previous_failure_spec_invalid")
    _require(spec.previous_v2_failure_relative is not None, "v2_previous_failure_spec_invalid")
    v1_root = repo / spec.previous_failure_relative.parent
    v2_root = repo / spec.previous_v2_failure_relative.parent
    before_v1 = before_v2 = before_recovery = None
    report["failure_checkpoint"] = "previous_failed_attempts"
    report["stability"]["previous_failed_v1_tree"] = "pending"
    report["stability"]["previous_failed_v2_tree"] = "pending"
    report["stability"]["v2_recovery_sources_tree"] = "pending"
    try:
        before_v1 = _snapshot_tree(v1_root)
        before_v2 = _snapshot_tree(v2_root)
        before_recovery = _snapshot_v3_recovery_sources(repo, spec, profile)
        _verify_previous_failed_attempt(repo, spec, report)
        _verify_v3_previous_v2_failure(repo, spec, report)
        report["checks"]["previous_failed_attempts"] = "passed"

        report["failure_checkpoint"] = "recovery_source_archives"
        _verify_v3_recovery_sources(repo, spec, report)
        report["checks"]["recovery_source_archives"] = "passed"

        _source_checks(repo, profile, report, spec)
    finally:
        snapshots = (
            ("previous_failed_v1_tree", v1_root, before_v1),
            ("previous_failed_v2_tree", v2_root, before_v2),
        )
        statuses: dict[str, str] = {}
        for role, root, before in snapshots:
            if before is None:
                statuses[role] = "not_collected"
            else:
                try:
                    statuses[role] = "passed" if _snapshot_tree(root) == before else "failed"
                except (OSError, ValueError):
                    statuses[role] = "recheck_failed"
        if before_recovery is None:
            statuses["v2_recovery_sources_tree"] = "not_collected"
        else:
            try:
                statuses["v2_recovery_sources_tree"] = (
                    "passed" if _snapshot_v3_recovery_sources(repo, spec, profile) == before_recovery else "failed"
                )
            except (OSError, ValueError):
                statuses["v2_recovery_sources_tree"] = "recheck_failed"
        report["stability"].update(statuses)
        if any(value != "passed" for value in statuses.values()):
            report["stability"]["status"] = "failed"
            if report["failure_checkpoint"] == "input_stability":
                report["checks"]["input_stability"] = "failed"
                raise ValueError("v3_prior_source_input_drift")


def _source_checks(
    repo: Path, profile: _Profile, report: dict[str, Any], spec: _VersionSpec | None = None,
) -> None:
    from ygo_eval import curry_input_recovery_audit as recovery

    spec = spec or _version_spec(1)
    baseline = repo / profile.baseline_relative
    v2_root = repo / profile.v2_report_relative.parent
    confirmation = repo / profile.confirmation_relative
    root_specs = (
        ("baseline_tree", baseline),
        ("v2_report_tree", v2_root),
        ("confirmation_tree", confirmation),
    )
    before_trees: dict[str, dict[str, dict[str, Any]]] = {}
    historical_before: dict[str, dict[str, Any]] | None = None
    ledger_relative = profile.confirmation_relative / "research/calls.jsonl"
    ledger_path = repo / ledger_relative
    before_absent: bool | None = None
    report["failure_checkpoint"] = "latest_delivery_chain"
    try:
        for role, root in root_specs:
            before_trees[role] = recovery._snapshot_tree(root)
        before_absent = not ledger_path.exists() and not ledger_path.is_symlink()
        report["stability"]["confirmation_charge_ledger_absent_before"] = before_absent
        report["stability"].update({role: "pending" for role, _ in root_specs})
        _require(before_absent, "confirmation_charge_ledger_unexpected")

        ledger_pins, delivery_records = _validate_delivery_chain(repo, profile, report, spec)
        report["checks"]["latest_delivery_chain"] = "passed"
        report["inputs"].extend(delivery_records)

        report["failure_checkpoint"] = "real_v2_report"
        paths, roles, v2 = _verify_v2_report(repo, profile, report, spec)
        report["checks"]["real_v2_report"] = "passed"

        report["failure_checkpoint"] = "old_confirmation_scope"
        old_records = _validate_old_scope(repo, profile, paths, roles, report, ledger_pins, spec)
        report["checks"]["old_confirmation_scope"] = "passed"
        report["inputs"].extend(old_records)

        report["failure_checkpoint"] = "historical_ledgers"
        historical_before = _snapshot_pinned_files(repo, ledger_pins, profile, spec)
        report["stability"]["historical_ledger_count"] = HISTORICAL_LEDGER_COUNT
        report["stability"]["historical_ledgers"] = "pending"
        report["inputs"].extend(_verify_historical_ledgers(repo, paths, ledger_pins, spec, report, profile))
        report["historical_ledgers"] = {
            "ledger_count": HISTORICAL_LEDGER_COUNT,
            "consumed": HISTORICAL_CONSUMED,
            "unknown": HISTORICAL_UNKNOWN,
            "verified_by_anchored_read_only_protection": True,
        }
        report["checks"]["historical_ledgers"] = "passed"
        report["historical_exit_observation"]["archived_static_return_code"] = v2["historical_exit_observation"]["archived_refusal_branch_return_code"]
        report["failure_checkpoint"] = "input_stability"
    finally:
        after_absent: bool | None
        try:
            after_absent = not ledger_path.exists() and not ledger_path.is_symlink()
        except OSError:
            after_absent = None
        report["stability"]["confirmation_charge_ledger_absent_after"] = after_absent
        statuses: dict[str, str] = {}
        for role, root in root_specs:
            before = before_trees.get(role)
            if before is None:
                statuses[role] = "not_collected"
                continue
            try:
                current = recovery._snapshot_tree(root)
                statuses[role] = "passed" if current == before else "failed"
            except (OSError, ValueError):
                statuses[role] = "recheck_failed"
        if historical_before is not None:
            try:
                after_historical = _snapshot_pinned_files(repo, {name: {} for name in historical_before}, profile, spec)
                statuses["historical_ledgers"] = "passed" if after_historical == historical_before else "failed"
            except (OSError, ValueError):
                statuses["historical_ledgers"] = "recheck_failed"
        report["stability"].update(statuses)
        all_stable = (
            all(statuses.get(role) == "passed" for role, _ in root_specs)
            and (historical_before is None or statuses.get("historical_ledgers") == "passed")
            and before_absent is True and after_absent is True
        )
        report["stability"]["status"] = "passed" if all_stable else "failed"
        if not all_stable and report["failure_checkpoint"] == "input_stability":
            report["checks"]["input_stability"] = "failed"

    _require(report["stability"]["status"] == "passed", "reservation_input_drift")
    report["checks"]["input_stability"] = "passed"


def _diagnostic(error: BaseException) -> str:
    text = str(error)
    if re.fullmatch(r"[a-z][a-z0-9_]{1,95}", text):
        return text
    return "reservation_source_check_failed"


def _validate_locations(
    args: argparse.Namespace, repo: Path, profile: _Profile, spec: _VersionSpec | None = None,
) -> tuple[Path, Path, Path]:
    spec = spec or _version_spec(getattr(args, "report_version", 1))
    baseline = _absolute(Path(args.baseline_dir))
    output = _absolute(Path(args.output))
    expected_baseline = _absolute(repo / profile.baseline_relative)
    output_root = _absolute(repo / spec.output_relative)
    output_path = output_root / REPORT_NAME
    _require(baseline == expected_baseline, "fixed_baseline_required")
    _require(output == output_path, "fixed_output_required")
    # Refuse linked runtime ancestors before the exclusive output directory is
    # created, so the fixed lexical path cannot resolve outside this checkout.
    safe_path(output_root.parent, file=False)
    if output_root.exists() or output_root.is_symlink():
        safe_path(output_root, file=False)
    ignored = safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    _require(any(line.strip().strip("/") == "data/runtime" for line in ignored), "ignored_output_contract_missing")
    return baseline, output_root, output_path


def _capture_tool(
    root: Path, repo: Path, report: dict[str, Any], workspace_identity: str,
    spec: _VersionSpec,
) -> None:
    archive_raw, list_raw, metadata = _tool_bundle(repo, workspace_identity, spec.tool_files)
    _write_exclusive(root / metadata["archive_path"], archive_raw)
    _write_exclusive(root / metadata["file_list_path"], list_raw)
    report["tool"] = metadata


def audit_to_output(
    args: argparse.Namespace, *, repo: Path | None = None,
    _profile: _Profile | None = None, _clock: Callable[[], float] = time.monotonic,
    _source_identity: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Record one fixed policy reservation; public callers cannot change policy or pins."""
    repo = _absolute(repo or _repo_root())
    profile = _profile or _production_profile()
    version = getattr(args, "report_version", 1)
    spec = _version_spec(version)
    _, output_root, output_path = _validate_locations(args, repo, profile, spec)
    if args.verify_only:
        return _verify_saved(args, repo, profile, output_root, output_path, spec)
    _require(not output_root.exists() and not output_root.is_symlink(), "reservation_output_exists")
    _require(output_root.parent.is_dir(), "reservation_output_parent_missing")
    output_root.mkdir(exist_ok=False)
    start = _clock()
    report = _new_report(version=spec.version, profile=profile)
    report["failure_checkpoint"] = spec.checks[0]
    try:
        if _source_identity is not None:
            identity_before = _source_identity(repo)
            identity_first_check = _source_identity(repo)
        else:
            from ygo_data.identity import stable_source

            identity_before = stable_source(repo)
            identity_first_check = stable_source(repo)
        _require(identity_before == identity_first_check, "tool_source_changed_during_capture")
        workspace_identity = identity_before.get("identity")
        _require(isinstance(workspace_identity, str) and HASH.fullmatch(workspace_identity) is not None, "tool_workspace_identity_invalid")
        _capture_tool(output_root, repo, report, workspace_identity, spec)
        _versioned_source_checks(repo, profile, spec, report)
        if _source_identity is not None:
            identity_after = _source_identity(repo)
        else:
            identity_after = stable_source(repo)
        _require(identity_before == identity_after, "tool_source_changed_during_capture")
        current_bundle = _tool_bundle(repo, workspace_identity, spec.tool_files)[2]
        _require(
            current_bundle["identity"] == report["tool"]["identity"]
            and current_bundle["member_sha256"] == report["tool"]["member_sha256"]
            and current_bundle["workspace_identity"] == report["tool"]["workspace_identity"],
            "tool_bundle_changed_during_capture",
        )
        manifest_hash = report["old_scope"]["manifest_sha256"]
        context = report["old_scope"]["context"]
        reservation_id = _reservation_id(CONFIRMATION_SCOPE, manifest_hash, context)
        report["reservation"].update({"recorded": True, "reservation_id": reservation_id, "duplicate_count": 1})
        report["planning_basis"] = {
            "certified_historical_consumed": HISTORICAL_CONSUMED,
            "risk_reserve_calls": RESERVED_CALLS,
            "planned_total": HISTORICAL_CONSUMED + RESERVED_CALLS,
            "actual_all_history_cumulative": None,
        }
        report["status"] = "passed"
        report["failure_checkpoint"] = None
    except Exception as error:
        report["status"] = "failed"
        if report["failure_checkpoint"] is None:
            report["failure_checkpoint"] = spec.checks[0]
        checkpoint = report["failure_checkpoint"]
        if checkpoint in report["checks"] and report["checks"][checkpoint] == "not_run":
            report["checks"][checkpoint] = "failed"
        elif checkpoint in report["checks"] and report["checks"][checkpoint] == "passed":
            report["checks"][checkpoint] = "failed"
        report["diagnostics"].append(_diagnostic(error))
        # Any interruption before a fully authenticated source chain leaves all
        # consumption statistics unknown; do not infer zero from absent files.
        report["planning_basis"]["certified_historical_consumed"] = None
        report["planning_basis"]["planned_total"] = None
        report["historical_ledgers"] = {"ledger_count": None, "consumed": None, "unknown": None, "verified_by_anchored_read_only_protection": False}
        if report["old_scope"].get("charge_ledger_state") == "absent":
            report["old_scope"]["charge_ledger_state"] = "unknown_after_failed_check"
    report["elapsed_seconds"] = round(_clock() - start, 6)
    _validate_report(report, profile)
    _write_exclusive(output_path, _pretty(report))
    return report


def _verify_saved(
    args: argparse.Namespace, repo: Path, profile: _Profile, output_root: Path,
    output_path: Path, spec: _VersionSpec | None = None,
) -> dict[str, Any]:
    spec = spec or _version_spec(getattr(args, "report_version", 1))
    _require(output_root.is_dir() and not output_root.is_symlink(), "reservation_report_missing")
    output_before = _verify_output_tree(output_root)
    prior_output_before = None
    if spec.version == 3:
        prior_output_before = {
            "v1": _snapshot_tree(repo / OUTPUT_RELATIVE),
            "v2": _snapshot_tree(repo / V2_OUTPUT_RELATIVE),
        }
    report_raw = safe_path(output_path).read_bytes()
    saved = _parse(report_raw, "reservation_report_invalid")
    _validate_report(saved, profile, spec)
    _require(saved.get("schema_version") == spec.version, "saved_reservation_version_mismatch")
    _require(saved["status"] == "passed", "saved_reservation_not_successful")
    _verify_tool_bundle(output_root, saved["tool"], spec.tool_files)
    # Recheck every pinned source and byte binding without requiring the current
    # checkout to have the same identity as the saved archive.
    scratch = _new_report(saved["tool"], version=spec.version, profile=profile)
    _versioned_source_checks(repo, profile, spec, scratch)
    _require(scratch["checks"] == saved["checks"], "saved_reservation_check_set_changed")
    _require(scratch["stability"] == saved["stability"], "saved_reservation_stability_changed")
    _require(scratch["inputs"] == saved["inputs"], "saved_reservation_inputs_changed")
    _require(scratch["old_scope"] == saved["old_scope"], "saved_reservation_scope_changed")
    _require(scratch["historical_ledgers"] == saved["historical_ledgers"], "saved_reservation_history_changed")
    _require(scratch["anchors"] == saved["anchors"], "saved_reservation_anchors_changed")
    _require(scratch["historical_exit_observation"] == saved["historical_exit_observation"], "saved_exit_provenance_changed")
    if spec.version == 2:
        _require(scratch["previous_failed_attempt"] == saved["previous_failed_attempt"], "saved_previous_failure_changed")
    if spec.version == 3:
        _require(scratch["previous_failed_attempts"] == saved["previous_failed_attempts"], "saved_previous_failures_changed")
        _require(scratch["recovery_source_archives"] == saved["recovery_source_archives"], "saved_recovery_sources_changed")
        _require(scratch["compatibility_basis"] == saved["compatibility_basis"], "saved_compatibility_basis_changed")
    _require(
        saved["reservation"]["reservation_id"] == _reservation_id(
            saved["old_scope"]["scope"], saved["old_scope"]["manifest_sha256"], saved["old_scope"]["context"],
        ),
        "reservation_id_mismatch",
    )
    output_after = _verify_output_tree(output_root)
    _require(output_after == output_before, "reservation_output_changed_during_verify")
    if spec.version == 3:
        prior_output_after = {
            "v1": _snapshot_tree(repo / OUTPUT_RELATIVE),
            "v2": _snapshot_tree(repo / V2_OUTPUT_RELATIVE),
        }
        _require(prior_output_after == prior_output_before, "reservation_prior_output_changed_during_verify")
    return {
        "schema_version": spec.version,
        "kind": (
            "curry_consumption_reservation_verification" if spec.version == 1
            else "curry_consumption_reservation_v2_verification" if spec.version == 2
            else "curry_consumption_reservation_v3_verification"
        ),
        "valid": True,
        "reservation_id": saved["reservation"]["reservation_id"],
        "native_calls": 0,
        "execution_ready": False,
        "diagnostics": [],
    }


def verify_report_bytes(raw: bytes) -> dict[str, Any]:
    """Small public-to-tests contract gate; parsing still rejects duplicate keys."""
    value = _parse(raw, "reservation_report_invalid")
    _validate_report(value)
    return value
