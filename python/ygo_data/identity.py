"""Read-only workspace/runtime identities and observed build records (Python 3.10+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

PathLike = Union[str, Path]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(repo: PathLike, *args: str, optional: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode and not optional:
        raise ValueError("local git inspection failed")
    return result


def regular_file(path: PathLike) -> Path:
    """Reject symlinks/junctions, including links in parent directories."""
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked source or artifact rejected")
    if not path.is_file():
        raise ValueError("regular file required")
    return path


def source_identity(repo: PathLike) -> Dict[str, Any]:
    """Hash all tracked and nonignored untracked files; preserve deletions."""
    repo = Path(repo).absolute()
    result = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    files = {}
    for raw in sorted(set(result.stdout.split(b"\0")) - {b""}):
        name = raw.decode("utf-8")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe git path")
        path = repo / relative
        files[name] = digest(regular_file(path).read_bytes()) if path.exists() or path.is_symlink() else None
    head = git(repo, "rev-parse", "--verify", "HEAD", optional=True)
    value = {"head": head.stdout.decode().strip() if head.returncode == 0 else None, "files": files}
    value["identity"] = digest(canonical(value))
    return value


def stable_source(repo: PathLike) -> Dict[str, Any]:
    first = source_identity(repo)
    if first != source_identity(repo):
        raise ValueError("source changed during capture")
    return first


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


def record_build(repo: PathLike, command: List[str], artifacts: Mapping[str, PathLike]) -> Dict[str, Any]:
    if not command:
        raise ValueError("build command required")
    # Apply repository-required proxy in the same subprocess environment.
    os.environ.update(http_proxy="http://127.0.0.1:7897", https_proxy="http://127.0.0.1:7897", all_proxy="socks5://127.0.0.1:7897")
    before, versions = stable_source(repo), toolchain()
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
    allowed = {"cargo", "build", "check", "test", "--offline", "--locked", "--release", "--bins", "-p", "--workspace", "--all-targets", "ygo-cli", "ygo-engine-adapter"}
    logical = [arg if arg in allowed else "<argument>" for arg in command]
    value = {"schema_version": 1, "kind": "build_record", "source_before": before, "source_after": after, "command": logical, "command_sha256": digest(canonical(command)), "toolchain": versions, "exit_code": result.returncode, "artifacts": hashes, "status": status, "provenance": "observed_command_only", "reproducible_build_proven": False}
    value["identity"] = digest(canonical(value))
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    capture_parser = sub.add_parser("capture")
    for flag in ["cli", "ordinary-config", "tournament-config"]:
        capture_parser.add_argument("--" + flag, required=True)
    build = sub.add_parser("build-record")
    build.add_argument("--artifact", action="append", default=[], metavar="ROLE=PATH")
    build.add_argument("command", nargs=argparse.REMAINDER)
    for child in [capture_parser, build]:
        child.add_argument("--repo", default=".")
        child.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        repo = Path(args.repo).absolute()
        output = checked_output(repo, args.output)
        if args.operation == "capture":
            value = capture(repo, args.cli, args.ordinary_config, args.tournament_config)
        else:
            artifacts = {}
            for item in args.artifact:
                role, path = item.split("=", 1)
                if not role or role in artifacts or not all(c.isalnum() or c == "_" for c in role):
                    raise ValueError("unique logical artifact role required")
                artifacts[role] = Path(path).absolute()
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            value = record_build(repo, command, artifacts)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return 0 if args.operation == "capture" or value["status"] == "recorded" else 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print("identity operation failed; check inputs, ignored output and stable assets", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
