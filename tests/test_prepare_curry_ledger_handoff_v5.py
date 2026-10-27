from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from contextlib import contextmanager
from unittest.mock import patch
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare-curry-ledger-handoff-v5.py"
SPEC = importlib.util.spec_from_file_location("prepare_curry_ledger_handoff_v5", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


@contextmanager
def _package_test_root():
    parent = ROOT / "target" / "curry-ledger-handoff-v5-tests"
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / ("packager-" + uuid.uuid4().hex)
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("package test workspace already exists")
    temporary.mkdir()
    resolved_parent = parent.resolve()
    resolved_temporary = temporary.resolve()
    if resolved_temporary.parent != resolved_parent:
        raise RuntimeError("unexpected package test workspace")
    try:
        yield temporary
    finally:
        if temporary.exists() and temporary.resolve() == resolved_temporary:
            shutil.rmtree(resolved_temporary)


def _staging_bundle(root: Path) -> Path:
    stage = root / "stage"
    (stage / "native-artifacts").mkdir(parents=True)
    (stage / "native-artifacts" / PACKAGER.RUNNER_NAME).write_bytes(b"synthetic runner bytes")
    (stage / "build-record.json").write_text("{}", encoding="utf-8")
    (stage / "source-native.zip").write_bytes(b"synthetic archive bytes")
    (stage / "source-native-file-list.json").write_text("{}", encoding="utf-8")
    (stage / "build-command.json").write_text("{}", encoding="utf-8")
    return stage


def test_package_copies_exactly_four_root_entries_and_passes_shared_layout_gate():
    with _package_test_root() as root:
        stage = _staging_bundle(root)
        destination = root / "package"

        installed = PACKAGER.install_bundle(stage, destination)

        assert installed == destination
        assert {item.name for item in destination.iterdir()} == {
            "native-artifacts",
            "build-record.json",
            "source-native.zip",
            "source-native-file-list.json",
        }
        PACKAGER.validate_bundle_layout(destination)


def test_package_refuses_existing_root_without_overwriting_it():
    with _package_test_root() as root:
        stage = _staging_bundle(root)
        destination = root / "existing-package"
        destination.mkdir()
        sentinel = destination / "preserve.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with pytest.raises(ValueError, match="package_root_already_exists"):
            PACKAGER.install_bundle(stage, destination)

        assert sentinel.read_text(encoding="utf-8") == "keep"
        assert {item.name for item in destination.iterdir()} == {"preserve.txt"}


def test_shared_layout_gate_rejects_build_command_or_extra_root_entry():
    with _package_test_root() as root:
        stage = _staging_bundle(root)
        destination = root / "package"
        PACKAGER.install_bundle(stage, destination)

        (destination / "build-command.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="curry_handoff_build_root_contents_invalid"):
            PACKAGER.validate_bundle_layout(destination)


def test_staging_validation_allows_build_material_but_final_root_remains_exact():
    with _package_test_root() as root:
        stage = _staging_bundle(root)
        (stage / "cargo-target").mkdir()
        (stage / "build.stdout").write_bytes(b"offline cargo output")
        (stage / "build.stderr").write_bytes(b"")
        source = {"identity": "0" * 64}
        with patch.object(
            PACKAGER.handoff_audit,
            "_verify_runner_build",
            return_value={"runner_sha256": "a" * 64},
        ) as verify_build:
            PACKAGER._verify_staging_bundle(root, stage, source)
        verify_build.assert_called_once()

        destination = root / "final-package"
        PACKAGER.install_bundle(stage, destination)
        assert {item.name for item in destination.iterdir()} == PACKAGER.PACKAGE_ENTRIES
        PACKAGER.validate_bundle_layout(destination)


def test_staging_root_is_never_reused():
    with _package_test_root() as root:
        stage = root / "stage"
        stage.mkdir()

        with pytest.raises(ValueError, match="staging_root_already_exists"):
            PACKAGER.create_staging_root(stage)
