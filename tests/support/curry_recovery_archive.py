"""Independent synthetic ZIP and source-list writer for audit tests.

All archive content is supplied by the test. This helper has no production
identity, ZIP, or report-writing dependencies and is intended only for ignored
test scratch directories.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Mapping
import zipfile


@dataclass(frozen=True)
class SyntheticArchivePair:
    native_archive: Path
    native_file_list: Path
    final_archive: Path
    final_file_list: Path
    native_files: dict[str, bytes]
    final_files: dict[str, bytes]
    native_archive_sha256: str
    native_file_list_sha256: str
    native_source_identity: str
    final_archive_sha256: str
    final_file_list_sha256: str
    final_source_identity: str


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _member_path(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not isinstance(name, str)
        or not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
    ):
        raise ValueError("synthetic_archive_member_path_invalid")


def _artifact_filename(name: str) -> None:
    if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("synthetic_archive_filename_invalid")


def _identity(head: str, files: Mapping[str, bytes]) -> tuple[dict, str]:
    file_hashes = {name: _sha(files[name]) for name in sorted(files)}
    listing = {
        "schema_version": 1,
        "kind": "workspace_source_archive",
        "head": head,
        "file_count": len(file_hashes),
        "source_identity": _sha(_canonical({"head": head, "files": file_hashes})),
        "files": file_hashes,
    }
    return listing, listing["source_identity"]


def _write_archive(path: Path, files: Mapping[str, bytes]) -> None:
    with zipfile.ZipFile(
        path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits = 0
            archive.writestr(info, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _write_snapshot(root: Path, archive_name: str, list_name: str, head: str, files: Mapping[str, bytes]):
    listing, identity = _identity(head, files)
    archive_path = root / archive_name
    list_path = root / list_name
    _write_archive(archive_path, files)
    list_path.write_bytes(_canonical(listing))
    return archive_path, list_path, _sha(archive_path.read_bytes()), _sha(list_path.read_bytes()), identity


def build_synthetic_archive_pair(
    root: Path,
    *,
    archive_filenames: tuple[str, str],
    file_list_filenames: tuple[str, str],
    native_files: Mapping[str, bytes],
    differences: Mapping[str, bytes | None],
    source_head: str,
    native_file_count: int,
    final_file_count: int,
) -> SyntheticArchivePair:
    """Write two authenticated snapshots and apply explicit member changes.

    ``differences`` maps a source member to its final bytes. ``None`` removes
    a member; a key absent from ``native_files`` adds one. The declared counts
    are checked independently before either archive is written.
    """
    if not isinstance(source_head, str) or not source_head:
        raise ValueError("synthetic_archive_head_invalid")
    if len(archive_filenames) != 2 or len(file_list_filenames) != 2:
        raise ValueError("synthetic_archive_pair_names_invalid")
    for filename in (*archive_filenames, *file_list_filenames):
        _artifact_filename(filename)

    base = dict(native_files)
    if any(not isinstance(content, bytes) for content in base.values()):
        raise ValueError("synthetic_archive_member_bytes_required")
    for name in base:
        _member_path(name)

    final = dict(base)
    for name, content in differences.items():
        _member_path(name)
        if content is None:
            if name not in final:
                raise ValueError("synthetic_archive_removed_member_missing")
            del final[name]
        elif isinstance(content, bytes):
            final[name] = content
        else:
            raise ValueError("synthetic_archive_member_bytes_required")

    if len(base) != native_file_count or len(final) != final_file_count:
        raise ValueError("synthetic_archive_declared_count_mismatch")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    native = _write_snapshot(
        root, archive_filenames[0], file_list_filenames[0], source_head, base,
    )
    final_artifact = _write_snapshot(
        root, archive_filenames[1], file_list_filenames[1], source_head, final,
    )
    return SyntheticArchivePair(
        native_archive=native[0],
        native_file_list=native[1],
        final_archive=final_artifact[0],
        final_file_list=final_artifact[1],
        native_files=base,
        final_files=final,
        native_archive_sha256=native[2],
        native_file_list_sha256=native[3],
        native_source_identity=native[4],
        final_archive_sha256=final_artifact[2],
        final_file_list_sha256=final_artifact[3],
        final_source_identity=final_artifact[4],
    )
