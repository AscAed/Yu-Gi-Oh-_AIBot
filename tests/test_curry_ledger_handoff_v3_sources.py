from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

import pytest

from ygo_eval import curry_ledger_handoff_audit as audit


ROOT = Path(__file__).resolve().parents[1]
LOCK_MEMBER = "crates/ygo-engine-adapter/examples/curry-option-validation.rs"
AUDIT_MEMBER = "python/ygo_eval/curry_ledger_handoff_audit.py"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _scratch() -> Path:
    path = ROOT / "target/curry-ledger-handoff-v3-tests" / ("source-" + uuid.uuid4().hex)
    path.mkdir(parents=True, exist_ok=False)
    return path


def _source_bundle(path: Path, files: dict[str, bytes]) -> tuple[Path, Path, dict]:
    listing = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": "synthetic-v1-head",
        "source_identity": None,
        "file_count": len(files),
        "files": {name: _sha(raw) for name, raw in sorted(files.items())},
    }
    listing["source_identity"] = _sha(audit.canonical({
        "head": listing["head"], "files": listing["files"],
    }))
    archive_path = path / "source-native.zip"
    list_path = path / "source-native-file-list.json"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    list_path.write_text(json.dumps(listing), encoding="utf-8")
    return archive_path, list_path, listing


def _v1_sources(*, fixed: bool) -> dict[str, bytes]:
    repaired_rust = (
        b"fn verify_parent_request(...) -> Result<(), Error> {\n"
        b"    let view = open_readonly()?;\n"
        b"    validate_parent(&view)?;\n"
        b"    drop(view);\n"
        b"    Ok(())\n"
        b"}\n"
    )
    broken_rust = (
        b"fn normal() {\n"
        b"    let _parent_view = verify_parent_request(&input, root)?;\n"
        b"    CurryOptionBatch::open_verification(root)?;\n"
        b"}\n"
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
    matched_python = (
        b'def _verify_acceptance_delivery():\n'
        b'    expected_accounting = {\n'
        b'        "policy_reserve": 7,\n'
        b'    }\n'
        b'    _require(isinstance(accounting, dict)\n'
        b'             and all(type(accounting.get(key)) is int for key in (\n'
        b'                 "certified_historical_consumed", "policy_reserve",\n'
        b'             )), "curry_handoff_acceptance_accounting_invalid")\n'
    )
    return {
        LOCK_MEMBER: repaired_rust if fixed else broken_rust,
        AUDIT_MEMBER: mismatch_python if fixed else matched_python,
        "crates/ygo-engine-adapter/examples/curry-option-verification.rs": b"fn main() {}\n",
    }


def test_v3_v1_audit_runner_uses_validation_binary_in_its_own_root():
    root = _scratch() / "v1-audit"

    selected = audit._previous_v1_audit_runner_path(root)

    assert selected == root / "native-artifacts/curry-option-validation.exe"


def test_v3_static_v2_failure_shape_requires_each_historical_defect_marker():
    source = (
        b'PREVIOUS_V1_RUNNER_RELATIVE = Path("native-artifacts/curry-option-verification.exe")\n'
        b"return previous_root / PREVIOUS_V1_RUNNER_RELATIVE\n"
        b"_parent_view_crosses_exclusive_open(lock_source)\n"
        b'"curry_handoff_archived_parent_lock_cause_missing"\n'
    )
    assert audit._v2_archive_semantics(source)
    for marker in (
        b"PREVIOUS_V1_RUNNER_RELATIVE",
        b"_parent_view_crosses_exclusive_open",
        b"curry_handoff_archived_parent_lock_cause_missing",
    ):
        assert not audit._v2_archive_semantics(source.replace(marker, b"removed"))
    assert not audit._v2_archive_semantics(source + b"_repaired_parent_view_source")


def test_v3_v1_archive_authenticates_repaired_rust_and_actual_python_typo():
    tmp_path = _scratch()
    files = _v1_sources(fixed=True)
    files.update({f"synthetic/member-{index:03d}.bin": b"inert" for index in range(545)})
    archive_path, list_path, listing = _source_bundle(tmp_path, files)

    facts = audit._verify_v1_audit_archive_semantics(
        archive_path, list_path, expected_identity=listing["source_identity"],
        expected_count=548,
    )

    assert facts == {
        "rust_repaired": True,
        "python_accounting_mismatch": True,
        "rust_member_sha256": listing["files"][LOCK_MEMBER],
        "python_member_sha256": listing["files"][AUDIT_MEMBER],
    }


@pytest.mark.parametrize("fixed", [False, True])
def test_v3_v1_archive_rejects_missing_either_expected_source_state(fixed: bool):
    tmp_path = _scratch()
    files = _v1_sources(fixed=fixed)
    files.update({f"synthetic/member-{index:03d}.bin": b"inert" for index in range(545)})
    archive_path, list_path, listing = _source_bundle(tmp_path, files)

    if fixed:
        files[AUDIT_MEMBER] = files[AUDIT_MEMBER].replace(b"policy_reserved", b"policy_reserve")
        archive_path.unlink()
        list_path.unlink()
        archive_path, list_path, listing = _source_bundle(tmp_path, files)
        expected = "curry_handoff_v1_accounting_failure_cause_missing"
    else:
        expected = "curry_handoff_v1_repaired_rust_missing"

    with pytest.raises(ValueError, match=expected):
        audit._verify_v1_audit_archive_semantics(
            archive_path, list_path, expected_identity=listing["source_identity"],
            expected_count=548,
        )
