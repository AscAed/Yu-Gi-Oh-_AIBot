"""Read-only workspace/runtime identities and observed build records (Python 3.10+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import stat
import subprocess
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union
import uuid
import zipfile

PathLike = Union[str, Path]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(repo: PathLike, *args: str, optional: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env)
    if result.returncode and not optional:
        raise ValueError("local git inspection failed")
    return result


def regular_file(path: PathLike) -> Path:
    """Reject symlinks/junctions, including links in parent directories."""
    path = Path(os.path.abspath(path))
    _reject_linked_path(path, "linked source or artifact rejected")
    if not path.is_file():
        raise ValueError("regular file required")
    return path


def _reject_linked_path(path: Path, message: str) -> None:
    for item in [*reversed(path.parents), path]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(message)


def source_identity(repo: PathLike) -> Dict[str, Any]:
    """Hash all tracked and nonignored untracked files; preserve deletions."""
    repo = Path(repo).absolute()
    result = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    head = git(repo, "rev-parse", "--verify", "HEAD", optional=True)
    names = set(result.stdout.split(b"\0")) - {b""}
    if head.returncode == 0:
        committed = git(repo, "ls-tree", "-r", "-z", "--name-only", "--full-tree", head.stdout.decode().strip())
        names.update(set(committed.stdout.split(b"\0")) - {b""})
    files = {}
    for raw in sorted(names):
        name = raw.decode("utf-8")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe git path")
        path = repo / relative
        files[name] = digest(regular_file(path).read_bytes()) if path.exists() or path.is_symlink() else None
    value = {"head": head.stdout.decode().strip() if head.returncode == 0 else None, "files": files}
    value["identity"] = digest(canonical(value))
    return value


def stable_source(repo: PathLike) -> Dict[str, Any]:
    first = source_identity(repo)
    if first != source_identity(repo):
        raise ValueError("source changed during capture")
    return first


def _safe_bundle_name(name: str) -> None:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError("unsafe source bundle path")
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe source bundle path")
    if any(any(char in '<>"|?*' for char in part) for part in path.parts):
        raise ValueError("unsafe source bundle path")


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        return len(bytes.fromhex(value)) == 32 and value == value.lower()
    except ValueError:
        return False


def _source_bundle_identity(source: Any) -> Dict[str, Any]:
    if not isinstance(source, dict) or set(source) != {"head", "files", "identity"}:
        raise ValueError("source identity shape invalid")
    if source["head"] is not None and not isinstance(source["head"], str):
        raise ValueError("source identity head invalid")
    files = source["files"]
    if not isinstance(files, dict):
        raise ValueError("source identity files invalid")
    for name, value in files.items():
        _safe_bundle_name(name)
        if value is not None and not _valid_sha256(value):
            raise ValueError("source identity file digest invalid")
    unsigned = {"head": source["head"], "files": files}
    if not _valid_sha256(source["identity"]) or digest(canonical(unsigned)) != source["identity"]:
        raise ValueError("source identity digest invalid")
    return source


def _unique_json_object(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate source bundle manifest key")
        result[key] = value
    return result


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def create_source_bundle(repo: PathLike, output_dir: PathLike) -> Dict[str, Any]:
    """Atomically archive current tracked and nonignored source bytes."""
    repo, output = Path(repo).absolute(), Path(output_dir).absolute()
    checked_output(repo, output)
    if output.exists():
        raise ValueError("source bundle destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    checked_output(repo, output)

    staging: Optional[Path] = None
    try:
        staging = output.parent / ("." + output.name + ".stage-" + uuid.uuid4().hex)
        staging.mkdir()
        try:
            checked_output(repo, staging)
        except ValueError as error:
            raise ValueError("source bundle staging path must also be ignored") from error

        source = _source_bundle_identity(stable_source(repo))
        present_files = {name: value for name, value in source["files"].items() if value is not None}
        archive_path = staging / "source.zip"
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
            for name in sorted(present_files):
                data = regular_file(repo / Path(name)).read_bytes()
                if digest(data) != present_files[name]:
                    raise ValueError("source changed during bundle capture")
                archive.writestr(_zip_info(name), data)

        if stable_source(repo) != source:
            raise ValueError("source changed during bundle capture")
        archive_bytes = archive_path.read_bytes()
        unsigned = {
            "schema_version": 1,
            "kind": "workspace_source_bundle",
            "source": source,
            "archive": {"name": "source.zip", "bytes": len(archive_bytes), "sha256": digest(archive_bytes)},
            "archived_file_count": len(present_files),
            "deleted_tracked_file_count": len(source["files"]) - len(present_files),
        }
        manifest = dict(unsigned, identity=digest(canonical(unsigned)))
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if stable_source(repo) != source:
            raise ValueError("source changed during bundle capture")
        if output.exists():
            raise ValueError("source bundle destination already exists")
        os.rename(staging, output)
        staging = None
        return manifest
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def verify_source_bundle(bundle_dir: PathLike) -> Dict[str, Any]:
    """Verify the bundle manifest and every archived source byte."""
    bundle = Path(os.path.abspath(bundle_dir))
    _reject_linked_path(bundle, "linked source bundle rejected")
    if not bundle.is_dir():
        raise ValueError("source bundle directory required")
    entries = {item.name for item in bundle.iterdir()}
    if entries != {"manifest.json", "source.zip"}:
        raise ValueError("source bundle contents invalid")
    manifest_path = regular_file(bundle / "manifest.json")
    archive_path = regular_file(bundle / "source.zip")
    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("source bundle manifest invalid") from error
    expected_fields = {"schema_version", "kind", "source", "archive", "archived_file_count", "deleted_tracked_file_count", "identity"}
    if not isinstance(manifest, dict) or set(manifest) != expected_fields or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["kind"] != "workspace_source_bundle":
        raise ValueError("source bundle manifest shape invalid")
    unsigned = {key: value for key, value in manifest.items() if key != "identity"}
    if not _valid_sha256(manifest["identity"]) or digest(canonical(unsigned)) != manifest["identity"]:
        raise ValueError("source bundle manifest digest invalid")

    source = _source_bundle_identity(manifest["source"])
    archive_record = manifest["archive"]
    if not isinstance(archive_record, dict) or set(archive_record) != {"name", "bytes", "sha256"}:
        raise ValueError("source bundle archive record invalid")
    if archive_record["name"] != "source.zip" or type(archive_record["bytes"]) is not int or archive_record["bytes"] < 0 or not _valid_sha256(archive_record["sha256"]):
        raise ValueError("source bundle archive record invalid")
    archive_bytes = archive_path.read_bytes()
    if len(archive_bytes) != archive_record["bytes"] or digest(archive_bytes) != archive_record["sha256"]:
        raise ValueError("source bundle archive digest invalid")

    files = source["files"]
    present_files = {name: value for name, value in files.items() if value is not None}
    deleted_count = len(files) - len(present_files)
    if type(manifest["archived_file_count"]) is not int or manifest["archived_file_count"] != len(present_files):
        raise ValueError("source bundle file count invalid")
    if type(manifest["deleted_tracked_file_count"]) is not int or manifest["deleted_tracked_file_count"] != deleted_count:
        raise ValueError("source bundle deletion count invalid")

    try:
        with zipfile.ZipFile(archive_path, mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != set(present_files):
                raise ValueError("source bundle member set invalid")
            for info in infos:
                _safe_bundle_name(info.filename)
                if info.is_dir() or info.compress_type != zipfile.ZIP_STORED or info.file_size != info.compress_size or info.flag_bits & 0x1:
                    raise ValueError("source bundle member encoding invalid")
                if digest(archive.read(info)) != present_files[info.filename]:
                    raise ValueError("source bundle member digest mismatch")
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, KeyError) as error:
        raise ValueError("source bundle archive invalid") from error
    return manifest


_WORKSPACE_STATE_MEMBERS = {
    "git-index.bin", "staged.patch", "unstaged.patch",
    "index-entries.bin", "status.porcelain-v2", "file-modes.json",
}


def _git_path(repo: Path, name: str) -> Path:
    result = git(repo, "rev-parse", "--git-path", name)
    value = result.stdout.decode("utf-8").strip()
    path = Path(value)
    return path.absolute() if path.is_absolute() else (repo / path).absolute()


def _workspace_state_snapshot(repo: Path, source_manifest: Mapping[str, Any]) -> tuple[Dict[str, Any], Dict[str, bytes]]:
    source = source_manifest["source"]
    if stable_source(repo) != source:
        raise ValueError("source bundle does not match current workspace")

    index_path = _git_path(repo, "index")
    lock_path = _git_path(repo, "index.lock")
    if lock_path.exists() or lock_path.is_symlink():
        raise ValueError("git index update is in progress")
    if index_path.exists() or index_path.is_symlink():
        index_data = regular_file(index_path).read_bytes()
    else:
        index_data = b""
    head_result = git(repo, "rev-parse", "--verify", "HEAD", optional=True)
    if head_result.returncode not in (0, 1):
        raise ValueError("local git inspection failed")
    head = head_result.stdout.decode("utf-8").strip() if head_result.returncode == 0 else None
    if head != source["head"]:
        raise ValueError("source bundle HEAD does not match workspace")

    staged = git(repo, "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv", "--no-renames", "--full-index", "--")
    unstaged = git(repo, "diff", "--binary", "--no-ext-diff", "--no-textconv", "--no-renames", "--full-index", "--")
    index_entries = git(repo, "ls-files", "--stage", "-z")
    status = git(repo, "status", "--porcelain=v2", "-z", "--untracked-files=all")
    version = git(repo, "--version").stdout.decode("utf-8").strip()
    filemode_result = git(repo, "config", "--bool", "--get", "core.filemode", optional=True)
    if filemode_result.returncode not in (0, 1):
        raise ValueError("local git inspection failed")
    core_filemode = None if filemode_result.returncode == 1 else filemode_result.stdout.decode("ascii").strip() == "true"

    present_files = {name: value for name, value in source["files"].items() if value is not None}
    modes: Dict[str, int] = {}
    for name in sorted(present_files):
        path = regular_file(repo / Path(name))
        modes[name] = stat.S_IMODE(path.stat().st_mode)

    payloads = {
        "git-index.bin": index_data,
        "staged.patch": staged.stdout,
        "unstaged.patch": unstaged.stdout,
        "index-entries.bin": index_entries.stdout,
        "status.porcelain-v2": status.stdout,
        "file-modes.json": canonical(modes) + b"\n",
    }
    git_record = {
        "head": head,
        "version": version,
        "core_filemode": core_filemode,
        "index_sha256": digest(index_data),
        "index_bytes": len(index_data),
        "index_entry_count": len([entry for entry in index_entries.stdout.split(b"\0") if entry]),
    }
    return git_record, payloads


def _workspace_state_snapshot_stable(repo: Path, source_manifest: Mapping[str, Any]) -> tuple[Dict[str, Any], Dict[str, bytes]]:
    first = _workspace_state_snapshot(repo, source_manifest)
    if first != _workspace_state_snapshot(repo, source_manifest):
        raise ValueError("workspace state changed during capture")
    return first


def create_workspace_state_bundle(repo: PathLike, source_bundle_dir: PathLike, output_dir: PathLike) -> Dict[str, Any]:
    """Capture the exact Git index, patches, status, and file modes bound to a source bundle."""
    repo, source_bundle_dir, output = Path(repo).absolute(), Path(source_bundle_dir).absolute(), Path(output_dir).absolute()
    checked_output(repo, output)
    if output.exists():
        raise ValueError("workspace state bundle destination already exists")
    source_manifest = verify_source_bundle(source_bundle_dir)
    if source_manifest["source"] != stable_source(repo):
        raise ValueError("source bundle does not match current workspace")
    output.parent.mkdir(parents=True, exist_ok=True)
    checked_output(repo, output)

    staging: Optional[Path] = None
    try:
        staging = output.parent / ("." + output.name + ".stage-" + uuid.uuid4().hex)
        staging.mkdir()
        try:
            checked_output(repo, staging)
        except ValueError as error:
            raise ValueError("workspace state staging path must also be ignored") from error

        git_record, payloads = _workspace_state_snapshot_stable(repo, source_manifest)
        archive_path = staging / "workspace-state.zip"
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
            for name in sorted(payloads):
                archive.writestr(_zip_info(name), payloads[name])
        with regular_file(archive_path).open("rb+") as handle:
            os.fsync(handle.fileno())
        archive_bytes = regular_file(archive_path).read_bytes()
        payload_records = {
            name: {"bytes": len(data), "sha256": digest(data)}
            for name, data in sorted(payloads.items())
        }
        unsigned = {
            "schema_version": 1,
            "kind": "workspace_state_bundle",
            "source_bundle_identity": source_manifest["identity"],
            "source_identity": source_manifest["source"]["identity"],
            "git": git_record,
            "payloads": payload_records,
            "archive": {"name": "workspace-state.zip", "bytes": len(archive_bytes), "sha256": digest(archive_bytes)},
        }
        manifest = dict(unsigned, identity=digest(canonical(unsigned)))
        manifest_path = staging / "manifest.json"
        with manifest_path.open("xb") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if _workspace_state_snapshot_stable(repo, source_manifest) != (git_record, payloads):
            raise ValueError("workspace state changed during capture")
        if verify_source_bundle(source_bundle_dir)["identity"] != source_manifest["identity"]:
            raise ValueError("source bundle changed during capture")
        if output.exists():
            raise ValueError("workspace state bundle destination already exists")
        os.rename(staging, output)
        staging = None
        return manifest
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def verify_workspace_state_bundle(bundle_dir: PathLike, source_bundle_dir: PathLike) -> Dict[str, Any]:
    """Verify workspace state payloads and their exact source-bundle binding."""
    bundle = Path(os.path.abspath(bundle_dir))
    _reject_linked_path(bundle, "linked workspace state bundle rejected")
    if not bundle.is_dir() or {item.name for item in bundle.iterdir()} != {"manifest.json", "workspace-state.zip"}:
        raise ValueError("workspace state bundle contents invalid")
    manifest_path = regular_file(bundle / "manifest.json")
    archive_path = regular_file(bundle / "workspace-state.zip")
    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("workspace state manifest invalid") from error
    expected_fields = {"schema_version", "kind", "source_bundle_identity", "source_identity", "git", "payloads", "archive", "identity"}
    if not isinstance(manifest, dict) or set(manifest) != expected_fields or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["kind"] != "workspace_state_bundle":
        raise ValueError("workspace state manifest shape invalid")
    unsigned = {key: value for key, value in manifest.items() if key != "identity"}
    if not _valid_sha256(manifest["identity"]) or digest(canonical(unsigned)) != manifest["identity"]:
        raise ValueError("workspace state manifest digest invalid")

    source_manifest = verify_source_bundle(source_bundle_dir)
    if manifest["source_bundle_identity"] != source_manifest["identity"] or manifest["source_identity"] != source_manifest["source"]["identity"]:
        raise ValueError("workspace state source binding invalid")
    git_record = manifest["git"]
    git_fields = {"head", "version", "core_filemode", "index_sha256", "index_bytes", "index_entry_count"}
    if not isinstance(git_record, dict) or set(git_record) != git_fields:
        raise ValueError("workspace state Git record invalid")
    if (
        git_record["head"] != source_manifest["source"]["head"]
        or not isinstance(git_record["version"], str) or not git_record["version"]
        or (git_record["core_filemode"] is not None and type(git_record["core_filemode"]) is not bool)
        or not _valid_sha256(git_record["index_sha256"])
        or type(git_record["index_bytes"]) is not int or git_record["index_bytes"] < 0
        or type(git_record["index_entry_count"]) is not int or git_record["index_entry_count"] < 0
    ):
        raise ValueError("workspace state Git record invalid")
    payload_records = manifest["payloads"]
    if not isinstance(payload_records, dict) or set(payload_records) != _WORKSPACE_STATE_MEMBERS:
        raise ValueError("workspace state payload record invalid")
    for name, record in payload_records.items():
        if not isinstance(record, dict) or set(record) != {"bytes", "sha256"} or type(record["bytes"]) is not int or record["bytes"] < 0 or not _valid_sha256(record["sha256"]):
            raise ValueError("workspace state payload record invalid")
    archive_record = manifest["archive"]
    if not isinstance(archive_record, dict) or set(archive_record) != {"name", "bytes", "sha256"} or archive_record["name"] != "workspace-state.zip" or type(archive_record["bytes"]) is not int or archive_record["bytes"] < 0 or not _valid_sha256(archive_record["sha256"]):
        raise ValueError("workspace state archive record invalid")
    archive_bytes = archive_path.read_bytes()
    if len(archive_bytes) != archive_record["bytes"] or digest(archive_bytes) != archive_record["sha256"]:
        raise ValueError("workspace state archive digest invalid")

    try:
        with zipfile.ZipFile(archive_path, mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != _WORKSPACE_STATE_MEMBERS:
                raise ValueError("workspace state archive member set invalid")
            payloads = {}
            for info in infos:
                _safe_bundle_name(info.filename)
                if info.is_dir() or info.compress_type != zipfile.ZIP_STORED or info.file_size != info.compress_size or info.flag_bits & 0x1:
                    raise ValueError("workspace state archive member encoding invalid")
                payloads[info.filename] = archive.read(info)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError, KeyError) as error:
        raise ValueError("workspace state archive invalid") from error
    for name, data in payloads.items():
        record = payload_records[name]
        if len(data) != record["bytes"] or digest(data) != record["sha256"]:
            raise ValueError("workspace state payload digest mismatch")
    index_data = payloads["git-index.bin"]
    if len(index_data) != git_record["index_bytes"] or digest(index_data) != git_record["index_sha256"]:
        raise ValueError("workspace state index digest mismatch")
    entries = payloads["index-entries.bin"].split(b"\0")
    if len([entry for entry in entries if entry]) != git_record["index_entry_count"]:
        raise ValueError("workspace state index entry count mismatch")
    try:
        modes = json.loads(payloads["file-modes.json"].decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("workspace state file modes invalid") from error
    present_files = {name for name, value in source_manifest["source"]["files"].items() if value is not None}
    if not isinstance(modes, dict) or set(modes) != present_files or any(type(mode) is not int or not 0 <= mode <= 0o7777 for mode in modes.values()):
        raise ValueError("workspace state file modes invalid")
    return {"valid": True, "identity": manifest["identity"], "source_bundle_identity": manifest["source_bundle_identity"], "index_sha256": git_record["index_sha256"], "payloads_verified": True}


def checked_output(repo: PathLike, output: PathLike) -> Path:
    repo, output = Path(repo).absolute(), Path(output).absolute()
    try:
        relative = output.relative_to(repo)
    except ValueError:
        raise ValueError("output must be inside repository and ignored") from None
    ignored = git(repo, "check-ignore", "--no-index", "-q", "--", str(relative), optional=True).returncode
    if ignored == 1:
        raise ValueError("output must be ignored to prevent self reference")
    if ignored != 0:
        raise ValueError("local git inspection failed")
    tracked = git(repo, "ls-files", "--error-unmatch", "--", str(relative), optional=True).returncode
    if tracked == 0:
        raise ValueError("output must not be tracked")
    if tracked != 1:
        raise ValueError("local git inspection failed")
    for item in [*reversed(output.parents), output]:
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("linked output rejected")
    return output


def toolchain() -> Dict[str, str]:
    result = {"python": sys.version.split()[0]}
    for tool in ["rustc", "cargo", "git"]:
        try:
            item = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=30)
            result[tool] = item.stdout.strip() if item.returncode == 0 else "unavailable"
        except (OSError, subprocess.TimeoutExpired):
            result[tool] = "unavailable"
    return result


def runtime_identity(repo: PathLike, cli: PathLike, config: PathLike) -> Dict[str, Any]:
    result = subprocess.run([str(cli), "engine", "identity", "--config", str(config)], cwd=repo, capture_output=True, timeout=300)
    if result.returncode:
        raise ValueError("runtime identity collection failed")
    value = json.loads(result.stdout)
    identity = value.pop("identity", None)
    if value.get("schema_version") != 1 or value.get("kind") != "engine_identity" or digest(canonical(value)) != identity:
        raise ValueError("runtime identity digest invalid")
    value["identity"] = identity
    return value


def capture(repo: PathLike, cli: PathLike, ordinary_config: PathLike, tournament_config: PathLike) -> Dict[str, Any]:
    repo, cli = Path(repo).absolute(), regular_file(Path(cli).absolute())
    before = stable_source(repo)
    cli_hash = digest(cli.read_bytes())
    versions = toolchain()
    configs = {"ordinary": Path(ordinary_config).absolute(), "tournament": Path(tournament_config).absolute()}
    config_hashes = {role: digest(regular_file(path).read_bytes()) for role, path in configs.items()}
    runtimes = {role: runtime_identity(repo, cli, path) for role, path in configs.items()}
    # Recollect rather than trusting a report's self-declared consistent field.
    repeated = {role: runtime_identity(repo, cli, path) for role, path in configs.items()}
    if before != stable_source(repo) or digest(cli.read_bytes()) != cli_hash or runtimes != repeated or versions != toolchain() or config_hashes != {role: digest(regular_file(path).read_bytes()) for role, path in configs.items()}:
        raise ValueError("inputs changed during capture")
    value = {"schema_version": 1, "kind": "workspace_identity", "source": before, "toolchain": versions, "cli_sha256": cli_hash, "runtimes": runtimes, "consistent": all(runtime["consistent"] for runtime in runtimes.values()), "build_provenance": "unverified", "reproducible_build_proven": False}
    value["identity"] = digest(canonical(value))
    return value


def run_build(command: Sequence[str], repo: PathLike) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=repo, check=False)


def record_build(
    repo: PathLike,
    command: List[str],
    artifacts: Mapping[str, PathLike],
    source_bundle: Optional[PathLike] = None,
    asset_inputs: Optional[Mapping[str, PathLike]] = None,
    expected_asset_snapshot: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not command:
        raise ValueError("build command required")
    # Apply repository-required proxy in the same subprocess environment.
    os.environ.update(http_proxy="http://127.0.0.1:7897", https_proxy="http://127.0.0.1:7897", all_proxy="socks5://127.0.0.1:7897")
    repo = Path(repo).absolute()
    before = stable_source(repo)
    bundle_before = verify_source_bundle(source_bundle) if source_bundle is not None else None
    if bundle_before is not None and bundle_before["source"] != before:
        raise ValueError("source bundle does not match current workspace")
    versions = toolchain()
    if stable_source(repo) != before:
        raise ValueError("source changed before build")
    if source_bundle is not None and verify_source_bundle(source_bundle)["identity"] != bundle_before["identity"]:
        raise ValueError("source bundle changed before build")
    if asset_inputs is not None and _asset_snapshot(asset_inputs) != expected_asset_snapshot:
        raise ValueError("asset inputs changed before build")
    result = run_build(command, repo)
    after = stable_source(repo)
    def artifact_hashes() -> Dict[str, Optional[str]]:
        return {role: digest(regular_file(path).read_bytes()) if Path(path).exists() else None for role, path in sorted(artifacts.items())}
    hashes = artifact_hashes()
    if after != stable_source(repo) or hashes != artifact_hashes():
        raise ValueError("build outputs changed during capture")
    status = "recorded" if result.returncode == 0 and before == after and versions == toolchain() and hashes and all(hashes.values()) else "source_changed" if before != after else "failed"
    # Keep a content binding to exact argv, while the human-readable command
    # stores only known build switches; arbitrary arguments may contain secrets.
    allowed = {
        "cargo", "build", "check", "test", "--offline", "--locked", "--release",
        "--bins", "--bin", "--profile", "--target-dir", "-p", "--workspace", "--all-targets",
        "dev", "ygo-cli", "ygo-engine-adapter", "ygo-engine-worker",
    }
    logical = [arg if arg in allowed else "<argument>" for arg in command]
    value = {"schema_version": 1, "kind": "build_record", "source_before": before, "source_after": after, "command": logical, "command_sha256": digest(canonical(command)), "toolchain": versions, "exit_code": result.returncode, "artifacts": hashes, "status": status, "provenance": "observed_command_only", "reproducible_build_proven": False}
    value["identity"] = digest(canonical(value))
    return value


def _source_bundle_reference(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "identity": manifest["identity"],
        "source_identity": manifest["source"]["identity"],
        "archive_sha256": manifest["archive"]["sha256"],
        "archive_bytes": manifest["archive"]["bytes"],
    }


def _asset_snapshot(assets: Mapping[str, PathLike], missing_ok: bool = False) -> Dict[str, Optional[Dict[str, Any]]]:
    result: Dict[str, Optional[Dict[str, Any]]] = {}
    for role, path in sorted(assets.items()):
        if not role or not all(char.isalnum() or char == "_" for char in role):
            raise ValueError("unique logical asset role required")
        try:
            data = regular_file(path).read_bytes()
            result[role] = {"sha256": digest(data), "bytes": len(data)}
        except (OSError, ValueError) as error:
            if not missing_ok:
                raise ValueError("asset input unavailable before build") from error
            result[role] = None
    return result


def source_bound_build_record(
    repo: PathLike,
    command: List[str],
    artifacts: Mapping[str, PathLike],
    bundle_dir: PathLike,
    assets: Optional[Mapping[str, PathLike]] = None,
) -> Dict[str, Any]:
    """Run and record a build tied to a verified source bundle and asset hashes."""
    repo, bundle_dir = Path(repo).absolute(), Path(bundle_dir).absolute()
    assets = assets or {}
    artifact_paths: Dict[str, Path] = {}
    for role, path in sorted(artifacts.items()):
        if not role or not all(char.isalnum() or char == "_" for char in role):
            raise ValueError("unique logical artifact role required")
        artifact_path = Path(path).absolute()
        checked_output(repo, artifact_path)
        if artifact_path.exists() or artifact_path.is_symlink():
            raise ValueError("candidate artifact output already exists")
        artifact_paths[role] = artifact_path
    bundle_manifest = verify_source_bundle(bundle_dir)
    current_source = stable_source(repo)
    if bundle_manifest["source"] != current_source:
        raise ValueError("source bundle does not match current workspace")
    assets_before = _asset_snapshot(assets)

    build = record_build(
        repo, command, artifact_paths, source_bundle=bundle_dir,
        asset_inputs=assets, expected_asset_snapshot=assets_before,
    )
    try:
        bundle_after_manifest = verify_source_bundle(bundle_dir)
        bundle_after = _source_bundle_reference(bundle_after_manifest)
    except (OSError, ValueError):
        bundle_after = None
    assets_after = _asset_snapshot(assets, missing_ok=True)
    bundle_before = _source_bundle_reference(bundle_manifest)

    if build["status"] == "source_changed":
        status = "source_changed"
    elif bundle_after != bundle_before:
        status = "source_bundle_changed"
    elif assets_after != assets_before:
        status = "asset_changed"
    else:
        status = "recorded" if build["status"] == "recorded" else "failed"

    value = {
        "schema_version": 1,
        "kind": "source_bound_build_record",
        "source_bundle_before": bundle_before,
        "source_bundle_after": bundle_after,
        "asset_inputs_before": assets_before,
        "asset_inputs_after": assets_after,
        "artifact_outputs_before": {role: None for role in artifact_paths},
        "build_record": build,
        "status": status,
        "provenance": "observed_command_only",
        "reproducible_build_proven": False,
    }
    value["identity"] = digest(canonical(value))
    return value


def verify_source_bound_build_record(
    value: Mapping[str, Any],
    bundle_dir: PathLike,
    artifacts: Mapping[str, PathLike],
    assets: Mapping[str, PathLike],
) -> Dict[str, Any]:
    """Verify the record, source bundle, and the current candidate/asset bytes."""
    expected_fields = {
        "schema_version", "kind", "source_bundle_before", "source_bundle_after",
        "asset_inputs_before", "asset_inputs_after", "artifact_outputs_before", "build_record", "status",
        "provenance", "reproducible_build_proven", "identity",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("source-bound build record shape invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != "source_bound_build_record":
        raise ValueError("source-bound build record version invalid")
    unsigned = {key: item for key, item in value.items() if key != "identity"}
    if not _valid_sha256(value["identity"]) or digest(canonical(unsigned)) != value["identity"]:
        raise ValueError("source-bound build record identity invalid")
    if value["provenance"] != "observed_command_only" or value["reproducible_build_proven"] is not False:
        raise ValueError("source-bound build provenance claim invalid")

    manifest = verify_source_bundle(bundle_dir)
    bundle_reference = _source_bundle_reference(manifest)
    if value["source_bundle_before"] != bundle_reference:
        raise ValueError("source bundle identity binding invalid")
    bundle_after = value["source_bundle_after"]
    if bundle_after is not None and (
        not isinstance(bundle_after, dict)
        or set(bundle_after) != {"identity", "source_identity", "archive_sha256", "archive_bytes"}
        or any(not _valid_sha256(bundle_after[key]) for key in ("identity", "source_identity", "archive_sha256"))
        or type(bundle_after["archive_bytes"]) is not int
        or bundle_after["archive_bytes"] < 0
    ):
        raise ValueError("source bundle after observation invalid")

    build = value["build_record"]
    build_fields = {
        "schema_version", "kind", "identity", "source_before", "source_after", "command",
        "command_sha256", "toolchain", "exit_code", "artifacts", "status", "provenance",
        "reproducible_build_proven",
    }
    if not isinstance(build, dict) or set(build) != build_fields:
        raise ValueError("nested build record shape invalid")
    build_unsigned = {key: item for key, item in build.items() if key != "identity"}
    if type(build["schema_version"]) is not int or build["schema_version"] != 1 or build["kind"] != "build_record":
        raise ValueError("nested build record version invalid")
    if not _valid_sha256(build["identity"]) or digest(canonical(build_unsigned)) != build["identity"]:
        raise ValueError("nested build record identity invalid")
    if not isinstance(build["status"], str) or build["status"] not in {"recorded", "source_changed", "failed"}:
        raise ValueError("nested build status invalid")
    if (
        not isinstance(build["command"], list) or not build["command"]
        or any(not isinstance(arg, str) for arg in build["command"])
        or not _valid_sha256(build["command_sha256"])
        or type(build["exit_code"]) is not int
    ):
        raise ValueError("nested build command record invalid")
    expected_toolchain = {"python", "rustc", "cargo", "git"}
    if not isinstance(build["toolchain"], dict) or set(build["toolchain"]) != expected_toolchain or any(not isinstance(item, str) for item in build["toolchain"].values()):
        raise ValueError("nested build toolchain record invalid")
    if not isinstance(build["artifacts"], dict):
        raise ValueError("nested build artifacts invalid")
    for role, artifact_hash in build["artifacts"].items():
        if not role or not all(char.isalnum() or char == "_" for char in role):
            raise ValueError("nested build artifact role invalid")
        if artifact_hash is not None and not _valid_sha256(artifact_hash):
            raise ValueError("nested build artifact digest invalid")
    if build["status"] == "recorded" and (
        build["exit_code"] != 0 or not build["artifacts"]
        or not all(_valid_sha256(item) for item in build["artifacts"].values())
        or build["source_before"] != build["source_after"]
    ):
        raise ValueError("nested recorded build evidence incomplete")
    source_before = _source_bundle_identity(build["source_before"])
    source_after = _source_bundle_identity(build["source_after"])
    if source_before != manifest["source"]:
        raise ValueError("build source identity binding invalid")
    if (source_before != source_after) != (build["status"] == "source_changed"):
        raise ValueError("nested build source status inconsistent")
    if build["provenance"] != "observed_command_only" or build["reproducible_build_proven"] is not False:
        raise ValueError("nested build provenance claim invalid")

    before_assets, after_assets = value["asset_inputs_before"], value["asset_inputs_after"]
    if not isinstance(before_assets, dict) or not isinstance(after_assets, dict) or set(before_assets) != set(after_assets):
        raise ValueError("asset input snapshot shape invalid")
    for role, snapshot in before_assets.items():
        if not role or not all(char.isalnum() or char == "_" for char in role):
            raise ValueError("asset input role invalid")
        if not isinstance(snapshot, dict) or set(snapshot) != {"sha256", "bytes"}:
            raise ValueError("asset input snapshot invalid")
        if not _valid_sha256(snapshot["sha256"]) or type(snapshot["bytes"]) is not int or snapshot["bytes"] < 0:
            raise ValueError("asset input snapshot invalid")
        after = after_assets[role]
        if after is not None and (
            not isinstance(after, dict) or set(after) != {"sha256", "bytes"}
            or not _valid_sha256(after["sha256"]) or type(after["bytes"]) is not int or after["bytes"] < 0
        ):
            raise ValueError("asset after snapshot invalid")

    artifact_outputs = value["artifact_outputs_before"]
    if not isinstance(artifact_outputs, dict) or set(artifact_outputs) != set(build["artifacts"]) or any(item is not None for item in artifact_outputs.values()):
        raise ValueError("candidate artifact output precondition invalid")
    if build["status"] == "recorded" and (not build["artifacts"] or not all(_valid_sha256(item) for item in build["artifacts"].values())):
        raise ValueError("recorded build artifact digest missing")

    expected_status = (
        "source_changed" if build["status"] == "source_changed"
        else "source_bundle_changed" if bundle_after != value["source_bundle_before"]
        else "asset_changed" if before_assets != after_assets
        else "recorded" if build["status"] == "recorded"
        else "failed"
    )
    if value["status"] != expected_status:
        raise ValueError("source-bound build status inconsistent")
    recorded_artifacts = build["artifacts"]
    if set(artifacts) != set(recorded_artifacts):
        raise ValueError("candidate artifact roles do not match build record")
    for role, path in artifacts.items():
        expected = recorded_artifacts[role]
        candidate = Path(path)
        if expected is None:
            if candidate.exists() or candidate.is_symlink():
                raise ValueError("unexpected candidate artifact present")
        elif digest(regular_file(candidate).read_bytes()) != expected:
            raise ValueError("candidate artifact digest mismatch")
    if set(assets) != set(after_assets):
        raise ValueError("asset roles do not match build record")
    for role, path in assets.items():
        expected = after_assets[role]
        candidate = Path(path)
        if expected is None:
            if candidate.exists() or candidate.is_symlink():
                raise ValueError("asset state differs from build record")
        else:
            data = regular_file(candidate).read_bytes()
            if digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
                raise ValueError("asset digest differs from build record")
    return {
        "valid": True,
        "identity": value["identity"],
        "status": value["status"],
        "source_bundle_identity": bundle_reference["identity"],
        "build_record_identity": build["identity"],
        "artifacts_verified": True,
        "assets_verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    capture_parser = sub.add_parser("capture")
    for flag in ["cli", "ordinary-config", "tournament-config"]:
        capture_parser.add_argument("--" + flag, required=True)
    build = sub.add_parser("build-record")
    build.add_argument("--artifact", action="append", default=[], metavar="ROLE=PATH")
    build.add_argument("command", nargs=argparse.REMAINDER)
    bound_build = sub.add_parser("build-provenance-record")
    bound_build.add_argument("--source-bundle", required=True)
    bound_build.add_argument("--artifact", action="append", default=[], metavar="ROLE=PATH")
    bound_build.add_argument("--asset", action="append", default=[], metavar="ROLE=PATH")
    bound_build.add_argument("command", nargs=argparse.REMAINDER)
    source_bundle = sub.add_parser("source-bundle")
    source_bundle.add_argument("--repo", default=".")
    source_bundle.add_argument("--output-dir", required=True)
    verify_bundle = sub.add_parser("verify-source-bundle")
    verify_bundle.add_argument("--bundle-dir", required=True)
    verify_bound_build = sub.add_parser("verify-source-bound-build-record")
    verify_bound_build.add_argument("--record", required=True)
    verify_bound_build.add_argument("--bundle-dir", required=True)
    verify_bound_build.add_argument("--artifact", action="append", default=[], metavar="ROLE=PATH")
    verify_bound_build.add_argument("--asset", action="append", default=[], metavar="ROLE=PATH")
    state_bundle = sub.add_parser("workspace-state-bundle")
    state_bundle.add_argument("--repo", default=".")
    state_bundle.add_argument("--source-bundle-dir", required=True)
    state_bundle.add_argument("--output-dir", required=True)
    verify_state_bundle = sub.add_parser("verify-workspace-state-bundle")
    verify_state_bundle.add_argument("--bundle-dir", required=True)
    verify_state_bundle.add_argument("--source-bundle-dir", required=True)
    for child in [capture_parser, build, bound_build]:
        child.add_argument("--repo", default=".")
        child.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.operation == "source-bundle":
            manifest = create_source_bundle(args.repo, args.output_dir)
            print(json.dumps({"status": "created", "identity": manifest["identity"], "source_identity": manifest["source"]["identity"], "archived_file_count": manifest["archived_file_count"], "deleted_tracked_file_count": manifest["deleted_tracked_file_count"]}, ensure_ascii=False))
            return 0
        if args.operation == "workspace-state-bundle":
            manifest = create_workspace_state_bundle(args.repo, args.source_bundle_dir, args.output_dir)
            print(json.dumps({"status": "created", "identity": manifest["identity"], "source_bundle_identity": manifest["source_bundle_identity"], "index_sha256": manifest["git"]["index_sha256"], "payload_count": len(manifest["payloads"])}, ensure_ascii=False))
            return 0
        if args.operation == "verify-workspace-state-bundle":
            result = verify_workspace_state_bundle(args.bundle_dir, args.source_bundle_dir)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.operation == "verify-source-bundle":
            manifest = verify_source_bundle(args.bundle_dir)
            print(json.dumps({"status": "verified", "identity": manifest["identity"], "source_identity": manifest["source"]["identity"], "archived_file_count": manifest["archived_file_count"], "deleted_tracked_file_count": manifest["deleted_tracked_file_count"]}, ensure_ascii=False))
            return 0
        if args.operation == "verify-source-bound-build-record":
            record = json.loads(regular_file(args.record).read_bytes().decode("utf-8"), object_pairs_hook=_unique_json_object)
            artifacts = _parse_role_paths(args.artifact, "artifact")
            assets = _parse_role_paths(args.asset, "asset")
            result = verify_source_bound_build_record(record, args.bundle_dir, artifacts, assets)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        repo = Path(args.repo).absolute()
        output = checked_output(repo, args.output)
        if args.operation == "capture":
            value = capture(repo, args.cli, args.ordinary_config, args.tournament_config)
        elif args.operation == "build-record":
            artifacts = _parse_role_paths(args.artifact, "artifact")
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            value = record_build(repo, command, artifacts)
        else:
            artifacts = _parse_role_paths(args.artifact, "artifact")
            assets = _parse_role_paths(args.asset, "asset")
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            value = source_bound_build_record(repo, command, artifacts, args.source_bundle, assets)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return 0 if args.operation == "capture" or value["status"] == "recorded" else 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print("identity operation failed; check inputs, ignored output and stable assets", file=sys.stderr)
        return 1


def _parse_role_paths(items: Sequence[str], label: str) -> Dict[str, Path]:
    result: Dict[str, Path] = {}
    for item in items:
        role, separator, path = item.partition("=")
        if not separator or not role or role in result or not all(char.isalnum() or char == "_" for char in role):
            raise ValueError(f"unique logical {label} role required")
        result[role] = Path(path).absolute()
    return result


if __name__ == "__main__":
    sys.exit(main())
