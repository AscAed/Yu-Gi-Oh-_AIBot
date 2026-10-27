"""Build the fixed, offline-only Curry ledger handoff V5 audit bundle."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile
from typing import Any

from ygo_data import identity as identity_tool
from ygo_eval import curry_ledger_handoff_audit as handoff_audit


REPO_ROOT = Path(__file__).resolve().parents[1]
STAGING_RELATIVE = Path("target/curry-ledger-handoff-v5-build")
OUTPUT_RELATIVE = Path("data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26")
RUNNER_NAME = "curry-option-validation.exe"
EXAMPLE_NAME = "curry-option-validation"
PACKAGE_ENTRIES = frozenset({
    "native-artifacts",
    "build-record.json",
    "source-native.zip",
    "source-native-file-list.json",
})


class PackageFailure(ValueError):
    """A stable packaging failure safe to write to evidence."""

    def __init__(self, phase: str, code: str):
        super().__init__(code)
        self.phase = phase
        self.code = code


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _regular_file(path: Path) -> Path:
    """Require a regular, unlinked file, including each parent component."""
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PackageFailure("input_validation", "linked_package_input_rejected")
    if not path.is_file():
        raise PackageFailure("input_validation", "regular_package_input_required")
    return path


def create_staging_root(path: Path) -> Path:
    """Create a fresh staging directory; never reuse prior build evidence."""
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise PackageFailure("staging", "staging_root_already_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(exist_ok=False)
    return path


def validate_bundle_layout(root: Path) -> None:
    """Use the same strict four-entry gate as the public V5 audit."""
    runner = root / "native-artifacts" / RUNNER_NAME
    record = root / "build-record.json"
    try:
        handoff_audit.validate_fixed_build_bundle(root, runner, record)
    except (OSError, ValueError) as exc:
        code = str(exc) if str(exc).startswith("curry_handoff_") else "bundle_layout_invalid"
        raise PackageFailure("bundle_layout", code) from None


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _write_json_exclusive(path: Path, value: Any) -> None:
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write_exclusive(path, raw)


def _write_source_snapshot(repo: Path, staging: Path) -> dict[str, Any]:
    """Write a source ZIP and its identity list from one stable snapshot."""
    source = identity_tool.stable_source(repo)
    files = source.get("files")
    if not isinstance(files, dict) or not files or any(value is None for value in files.values()):
        raise PackageFailure("source_snapshot", "source_identity_incomplete")

    archive_path = staging / "source-native.zip"
    list_path = staging / "source-native-file-list.json"
    listing = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": source.get("head"),
        "source_identity": source["identity"],
        "file_count": len(files),
        "files": files,
    }
    _write_json_exclusive(list_path, listing)

    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, expected_hash in sorted(files.items()):
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise PackageFailure("source_snapshot", "unsafe_source_path")
            source_path = _regular_file(repo / relative)
            raw = source_path.read_bytes()
            if _sha(raw) != expected_hash:
                raise PackageFailure("source_snapshot", "source_changed_during_archive")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, raw, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    if source != identity_tool.stable_source(repo):
        raise PackageFailure("source_snapshot", "source_changed_during_archive")
    return source


def install_bundle(staging: Path, destination: Path) -> Path:
    """Copy only the four allowed package entries to a new formal root."""
    staging, destination = Path(staging), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PackageFailure("bundle_layout", "package_root_already_exists")

    staged_runner = _regular_file(staging / "native-artifacts" / RUNNER_NAME)
    staged_record = _regular_file(staging / "build-record.json")
    staged_archive = _regular_file(staging / "source-native.zip")
    staged_list = _regular_file(staging / "source-native-file-list.json")

    destination.mkdir(parents=True, exist_ok=False)
    (destination / "native-artifacts").mkdir(exist_ok=False)
    for source, target in (
        (staged_runner, destination / "native-artifacts" / RUNNER_NAME),
        (staged_record, destination / "build-record.json"),
        (staged_archive, destination / "source-native.zip"),
        (staged_list, destination / "source-native-file-list.json"),
    ):
        _write_exclusive(target, source.read_bytes())

    validate_bundle_layout(destination)
    return destination


def _save_failure(staging: Path, failure: PackageFailure) -> None:
    status_path = staging / "packaging-status.json"
    if status_path.exists() or status_path.is_symlink():
        return
    try:
        _write_json_exclusive(status_path, {
            "schema_version": 1,
            "kind": "curry_ledger_handoff_v5_package_status",
            "status": "failed",
            "phase": failure.phase,
            "error_code": failure.code,
            "native_calls": 0,
            "audit_runner_started": False,
        })
    except OSError:
        # Do not replace a primary failure with a best-effort diagnostic error.
        return


def _run_build_record(repo: Path, staging: Path) -> None:
    cargo_target = staging / "cargo-target"
    runner_build = cargo_target / "debug" / "examples" / f"{EXAMPLE_NAME}.exe"
    archive = staging / "source-native.zip"
    listing = staging / "source-native-file-list.json"
    build_record = staging / "build-record.json"
    command = [
        sys.executable, "-m", "ygo_data.identity", "build-record",
        "--repo", str(repo), "--output", str(build_record),
        "--artifact", f"runner={runner_build}",
        "--artifact", f"source_archive={archive}",
        "--artifact", f"source_file_list={listing}",
        "--", "cargo", "build", "--offline", "--locked",
        "-p", "ygo-engine-adapter", "--example", EXAMPLE_NAME,
        "--target-dir", str(cargo_target),
    ]
    command_record = {
        "schema_version": 1,
        "kind": "curry_ledger_handoff_v5_build_command",
        "argv": command,
        "cargo_target_dir": str(cargo_target),
        "cargo_target_dir_env_matches_argument": True,
    }
    _write_json_exclusive(staging / "build-command.json", command_record)

    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(cargo_target)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    python_path = str(repo / "python")
    env["PYTHONPATH"] = python_path + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True, check=False)
    except OSError:
        raise PackageFailure("build", "build_record_tool_start_failed") from None
    _write_exclusive(staging / "build.stdout", result.stdout)
    _write_exclusive(staging / "build.stderr", result.stderr)
    if result.returncode != 0:
        raise PackageFailure("build", "offline_runner_build_failed")

    record_path = _regular_file(build_record)
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise PackageFailure("build", "build_record_invalid") from None
    if (not isinstance(record, dict) or record.get("status") != "recorded"
            or record.get("kind") != "build_record"):
        raise PackageFailure("build", "build_record_not_recorded")
    if record.get("source_before") != record.get("source_after"):
        raise PackageFailure("build", "source_changed_during_build")

    built_runner = _regular_file(runner_build)
    packaged_runner = staging / "native-artifacts" / RUNNER_NAME
    packaged_runner.parent.mkdir(exist_ok=True)
    _write_exclusive(packaged_runner, built_runner.read_bytes())


def _verify_staging_bundle(repo: Path, staging: Path, source: dict[str, Any]) -> None:
    runner = staging / "native-artifacts" / RUNNER_NAME
    build_record = staging / "build-record.json"
    try:
        # Staging also contains the build target, command and raw build logs.
        # Apply the strict four-entry contract only after copying into the
        # formal root, never to this intentionally richer working directory.
        _regular_file(runner)
        _regular_file(build_record)
        _regular_file(staging / "source-native.zip")
        _regular_file(staging / "source-native-file-list.json")
        artifact_dir = staging / "native-artifacts"
        if not artifact_dir.is_dir() or artifact_dir.is_symlink() or {
            item.name for item in artifact_dir.iterdir()
        } != {RUNNER_NAME}:
            raise PackageFailure("staged_build_validation", "staged_runner_layout_invalid")
        handoff_audit._verify_runner_build(runner, build_record, repo, source)
    except PackageFailure:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc) if str(exc).startswith("curry_handoff_") else "staged_build_binding_invalid"
        raise PackageFailure("staged_build_validation", code) from None


def prepare_package(repo: Path = REPO_ROOT) -> Path:
    """Build and install the fixed V5 bundle; never invoke its audit runner."""
    repo = Path(repo).resolve()
    staging = repo / STAGING_RELATIVE
    destination = repo / OUTPUT_RELATIVE
    try:
        identity_tool.checked_output(repo, staging)
        identity_tool.checked_output(repo, destination)
        create_staging_root(staging)
    except PackageFailure:
        raise
    except (OSError, ValueError):
        raise PackageFailure("fixed_paths", "fixed_package_path_check_failed") from None
    phase = "bundle_layout"
    try:
        if destination.exists() or destination.is_symlink():
            raise PackageFailure("bundle_layout", "package_root_already_exists")

        phase = "source_snapshot"
        source = _write_source_snapshot(repo, staging)
        (staging / "native-artifacts").mkdir(exist_ok=False)

        phase = "build"
        _run_build_record(repo, staging)

        phase = "staged_build_validation"
        _verify_staging_bundle(repo, staging, source)
        if source != identity_tool.stable_source(repo):
            raise PackageFailure("stability", "source_changed_before_install")

        phase = "bundle_install"
        installed = install_bundle(staging, destination)
        _write_json_exclusive(staging / "packaging-status.json", {
            "schema_version": 1,
            "kind": "curry_ledger_handoff_v5_package_status",
            "status": "prepared",
            "phase": "bundle_layout",
            "formal_root_entries": sorted(PACKAGE_ENTRIES),
            "native_calls": 0,
            "audit_runner_started": False,
        })
        return installed
    except PackageFailure as failure:
        _save_failure(staging, failure)
        raise
    except (OSError, ValueError, subprocess.SubprocessError):
        failure = PackageFailure(phase, "package_operation_failed")
        _save_failure(staging, failure)
        raise failure from None


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        print("this packaging command accepts no overrides", file=sys.stderr)
        return 2
    try:
        output = prepare_package()
    except PackageFailure as failure:
        print(f"V5 offline package stopped: {failure.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("V5 offline package stopped: fixed_package_path_check_failed", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "prepared",
        "package": OUTPUT_RELATIVE.as_posix(),
        "formal_root_entries": sorted(PACKAGE_ENTRIES),
        "native_calls": 0,
        "audit_runner_started": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
