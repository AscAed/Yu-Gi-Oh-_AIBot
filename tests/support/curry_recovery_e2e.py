"""Synthetic repository tree for the public Curry recovery audit test.

This builder intentionally starts with real byte/ZIP contracts. It does not
reuse local historical reports or production source pins.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import subprocess
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from ygo_eval import curry_input_recovery_audit as audit
from ygo_eval.curry_input_recovery_audit import _PinnedArchive, _PinnedFile, _SourceDescription
from ygo_eval import native_curry_option_validation as curry
from tests.support.curry_recovery_archive import build_synthetic_archive_pair


BASELINE = "data/runtime/p1-curry-option-confirmation-native-2026-10-24"
OUTPUT_V2 = "data/runtime/p1-curry-input-recovery-v2-offline-2026-10-24"
ASSET_AUDIT_ROOT = "data/runtime/p1-curry-asset-binding-offline-2026-10-24"
ASSET_SCOPE_ROOT = "data/runtime/p1-curry-option-validation-native-2026-10-23"
HEAD = "0123456789abcdef0123456789abcdef01234567"
SYNTHETIC_CODEC_CURRENT = b"// synthetic codec source\n"
SYNTHETIC_CODEC_OLD = b"// synthetic historical codec\n"


@dataclass(frozen=True)
class SyntheticRecoveryTree:
    repo: Path
    baseline: Path
    sources: _SourceDescription


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def synthetic_source_identity(repo: Path) -> dict[str, Any]:
    """Rescan the test repo without depending on a temporary Git checkout."""
    repo = Path(repo).absolute()
    files: dict[str, str | None] = {}
    for path in sorted(repo.rglob("*"), key=lambda item: item.relative_to(repo).as_posix()):
        relative = path.relative_to(repo)
        parts = relative.parts
        if parts and (parts[0] == ".git" or "target" in parts):
            continue
        if len(parts) >= 2 and parts[0] == "data" and parts[1] == "runtime":
            continue
        if path.is_symlink():
            raise ValueError("synthetic_source_link_rejected")
        if path.is_file():
            files[relative.as_posix()] = _sha(path.read_bytes())
    value = {"head": HEAD, "files": files}
    value["identity"] = _sha(_canonical(value))
    return value


@contextmanager
def synthetic_source_sampler():
    """Inject a fresh content sampler while retaining production stable_source."""
    with patch("ygo_data.identity.source_identity", side_effect=synthetic_source_identity):
        yield


def _case_encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      indent=2).encode("utf-8") + b"\n"


def _encode_ledger(value: Any) -> bytes:
    """Encode a ledger hash preimage with the frozen Rust wire separators."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _write(repo: Path, relative: str | Path, raw: bytes) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _file_pin(repo: Path, relative: str, role: str | None = None) -> _PinnedFile:
    raw = (repo / relative).read_bytes()
    return _PinnedFile(role or relative.rsplit("/", 1)[-1], relative, _sha(raw))


_SYNTHETIC_LEDGER_CONTRACTS = (
    ("baseline", "data/runtime/baseline-2026-10-19/research/calls.jsonl", 9,
     "research-first-batch-v1", "4ea4d6cb6aa9b1eac4d9ca724ebe451be620ea7fa4d42473fa0f86b9511f17db", 4096),
    ("state", "data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl", 8,
     "native-regression-v1", '["76a86c0ba6a5d4495709d724c5bf1946bbb9c1c887af89430c3e65bfd52cf292",["rabbit-full","tournament-full","rabbit-empty","rabbit-shuffle","rabbit-end"]]', 16),
    ("terminal", "data/runtime/p1-terminal-2026-10-20/research/native/calls.jsonl", 1,
     "terminal-regression-v1", '["db775b4b5ae565de7dcf463e3bcc502ccf72c10397c6266c908090080c750a73",["terminal-rabbit","terminal-tournament","terminal-shuffle-end"]]', 6),
    ("terminal-followup", "data/runtime/p1-terminal-followup-2026-10-20/research/native/calls.jsonl", 4,
     "terminal-followup-v1", '["a9be1d93c90556207c60b9ab17840c512008f971c9c044c49b9930f37bde69e9",["terminal-tournament","terminal-shuffle-end"]]', 4),
    ("terminal-smoke", "data/runtime/p1-terminal-smoke-2026-10-20/research/native/calls.jsonl", 2,
     "terminal-smoke-v1", '["2214263e4122b1ba68871c84b77f880caaf66b0e5bdd7319741b0d9a82dd81d7",["terminal-rabbit"]]', 2),
    ("tenki-probe", "data/runtime/p1-tenki-probe-native-2026-10-21/research/calls.jsonl", 2,
     "tenki-prompt-probe-v1", "7a7258ddacc5b42fe51908a771cff8ed85b58a020c1f0c0e6cd9df5ec01269a1", 6),
    ("tenki-placement", "data/runtime/p1-tenki-placement-native-2026-10-22/research/calls.jsonl", 0,
     "tenki-placement-probe-v1", "773bafe50501dd0e093b7396d24bb2198a94503212a31d6407bdcfad8f7b1d37", 6),
)


def _ordered_test_ledger_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Handwritten frozen ledger entry ordering; deliberately not imported."""
    names = {
        "header": ("kind", "version", "scope", "context", "limit"),
        "checkpoint": ("kind", "name", "blob", "consumed", "charged_sequence"),
        "begin": ("kind", "call_id", "request", "purpose", "reservation"),
        "complete": ("kind", "call_id", "result", "raw_hash", "normalized_hash"),
    }
    return {key: entry[key] for key in names[entry["kind"]]}


def _rewrite_first_ledger_context(path: Path, context: str) -> None:
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    rows[0]["entry"]["context"] = context
    previous = ""
    for sequence, row in enumerate(rows):
        payload = _encode_ledger([
            sequence, previous, _ordered_test_ledger_entry(row["entry"]),
        ])
        row["hash"] = _sha(payload)
        row["sequence"] = sequence
        row["previous"] = previous
        previous = row["hash"]
    path.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))


def _synthetic_request(case_id: str, seed: int) -> dict[str, Any]:
    return {
        "protocol_version": 2,
        "engine": {
            "worker_path": f"synthetic/{case_id}/worker.exe",
            "ocgcore_path": f"synthetic/{case_id}/core.dll",
            "catalog_path": f"synthetic/{case_id}/cards.cdb",
            "scripts_path": f"synthetic/{case_id}/scripts",
            "script_manifest_path": f"synthetic/{case_id}/scripts.json",
            "engine_manifest_path": f"synthetic/{case_id}/engine.json",
            "timeout_ms": 30_000,
        },
        "deck": {"main": [], "extra": [], "side": []},
        "opening_hand": [], "seed": seed, "decisions": [],
        "versions": {
            "rules": "synthetic-rules-v1", "catalog": "synthetic-catalog-v1",
            "banlist": "synthetic-banlist-v1", "engine_sha256": "a" * 64,
            "cdb_sha256": "b" * 64, "scripts_sha256": "c" * 64,
            "core_commit": "synthetic-core", "initializer": "synthetic-initializer",
        },
        "probe_only": False,
    }


def _synthetic_generic_ledger(path: Path, scope: str, context: str, count: int,
                              limit: int, role: str) -> tuple[str, ...]:
    """Write a self-contained content-addressed ledger using only test code."""
    path.parent.mkdir(parents=True, exist_ok=True)
    blob_root = path.with_name(path.name + ".blobs")
    for folder in ("checkpoints", "events", "recoveries", "results"):
        (blob_root / folder).mkdir(parents=True, exist_ok=True)
    request = _synthetic_request(role, seed=1)
    request_hash = _sha(json.dumps(
        {key: value for key, value in request.items() if key != "engine"},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        allow_nan=False,
    ).encode("utf-8"))
    (path.parent / "synthetic-request.json").write_bytes(_canonical({"request": request}))

    def put(folder: str, raw: bytes) -> str:
        address = _sha(raw)
        (blob_root / folder / f"{address}.json").write_bytes(raw)
        return address

    entries: list[dict[str, Any]] = [{
        "kind": "header", "version": 1, "scope": scope,
        "context": context, "limit": limit,
    }]
    for call_id in range(1, count + 1):
        event = [{
            "sequence": 1, "opcode": 40, "raw": [40, 0],
            "supported": True, "fields": {"player": 0},
        }]
        event_hash = put("events", _encode_ledger(event))
        result = {
            "protocol_version": 2, "status": "engine_verified", "events": event,
            "prompt": None,
            "checkpoint": {"turn": 1, "turn_player": 0, "phase": 512,
                            "lp": [8000, 8000], "cards": []},
            "error": None,
            "versions": request["versions"], "loaded_scripts": {}, "steps": [],
            "resolved_decisions": [], "coverage_gaps": [],
            "peak_working_set_bytes": 1024,
        }
        stored_result = dict(result)
        stored_result["events"] = []
        result_blob = put("results", _encode_ledger({
            "kind": "duel", "result": stored_result, "event_chunks": [event_hash],
        }))
        normalized = dict(result)
        normalized["peak_working_set_bytes"] = None
        entries.extend((
            {"kind": "begin", "call_id": call_id, "request": request_hash,
             "purpose": "execution", "reservation": None},
            {"kind": "complete", "call_id": call_id, "result": result_blob,
             "raw_hash": _sha(_encode_ledger(result)),
             "normalized_hash": _sha(_encode_ledger(normalized))},
        ))

    previous = ""
    rows = []
    for sequence, entry in enumerate(entries):
        current = _sha(_encode_ledger([
            sequence, previous, _ordered_test_ledger_entry(entry),
        ]))
        rows.append({"sequence": sequence, "previous": previous,
                     "entry": entry, "hash": current})
        previous = current
    path.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))
    return (request_hash,)


def _synthetic_history_ledgers(repo: Path) -> tuple[_PinnedFile, ...]:
    """Generate the seven fixed historical ledger bytes and bind every request."""
    from tests.support.curry_recovery_ledger import build_synthetic_first_batch_ledger
    from ygo_eval.history_audit import verify_ledger

    pins: list[_PinnedFile] = []
    for index, contract in enumerate(_SYNTHETIC_LEDGER_CONTRACTS):
        role, relative, count, scope, context, limit = contract
        ledger_path = repo / relative
        if index == 0:
            first = build_synthetic_first_batch_ledger(ledger_path.parent)
            _rewrite_first_ledger_context(ledger_path, context)
            frozen_cases = {
                "cases": [
                    {"case_id": case_id, "request": request}
                    for case_id, request in first.requests.items()
                ]
            }
            (ledger_path.parent / "synthetic-cases.json").write_bytes(_canonical(frozen_cases))
            parsed = verify_ledger(ledger_path.read_bytes(), first.read_blob, first.requests)
            if parsed["stats"]["consumed"] != 9 or parsed["ledger_records"] != 37:
                raise AssertionError("synthetic_first_ledger_invariant_failed")
        else:
            request_hashes = _synthetic_generic_ledger(
                ledger_path, scope, context, count, limit, role,
            )
            # The first builder's case file is an independent request source;
            # generic ledgers use one synthetic request document per ledger.
        pins.append(_file_pin(repo, relative, role=f"historical_{role}_ledger"))
    return tuple(pins)


def _synthetic_old_curry_scope(repo: Path) -> _SourceDescription:
    """Create the old Curry static scope consumed by the asset-audit layer."""
    root = repo / ASSET_SCOPE_ROOT
    final = root / "final-build"
    research = root / "research"
    final.mkdir(parents=True)
    research.mkdir(parents=True)

    worker = b"synthetic old worker\n"
    runner = b"synthetic old runner\n"
    cli = b"synthetic old cli\n"
    dll = b"synthetic old dll\n"
    cdb = b"synthetic old cdb\n"
    scripts = b"synthetic old scripts\n"
    roles = {
        "worker": {"sha256": _sha(worker)},
        "dll": {"sha256": _sha(dll)},
        "cdb": {"sha256": _sha(cdb)},
        "script_manifest": {"sha256": _sha(scripts)},
    }
    ordinary = {"consistent": True, "roles": roles}
    ordinary["identity"] = _sha(_canonical(ordinary))
    versions = {"engine_sha256": _sha(dll), "cdb_sha256": _sha(cdb), "scripts_sha256": _sha(scripts)}
    request = {
        "protocol_version": 2, "seed": 1, "probe_only": False, "decisions": [],
        "versions": versions,
    }
    context = "538053247dabdba0d0eb424f67ce41c1b0a55eb7ee803685ad8d9a95c8a6e332"
    source_code = b'found["roles"]["worker"]["sha256"] != input.request.versions.engine_sha256\n'
    current_code = (
        b'found["roles"]["dll"]["sha256"] != input.request.versions.engine_sha256\n'
        b'manifest["input_sha256"]["worker"]\n'
    )
    _write(repo, "crates/ygo-engine-adapter/examples/curry-option-validation.rs", current_code)
    native_files = {
        "crates/ygo-engine-adapter/examples/curry-option-validation.rs": source_code,
        "TASKS.md": b"old task snapshot\n",
        "docs/TESTING.md": b"old testing snapshot\n",
        "docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md": b"old handoff\n",
    }
    differences = {
        "TASKS.md": b"new task snapshot\n",
        "docs/TESTING.md": b"new testing snapshot\n",
        "docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md": b"new handoff\n",
    }
    pair = build_synthetic_archive_pair(
        root,
        archive_filenames=("source-native.zip", "source-native-final.zip"),
        file_list_filenames=("source-native-file-list.json", "source-native-final-list.json"),
        native_files=native_files,
        differences=differences,
        source_head=HEAD,
        native_file_count=4,
        final_file_count=4,
    )
    # The verifier's final archive paths are fixed beneath final-build.
    (final / "source-native.zip").write_bytes(pair.final_archive.read_bytes())
    (final / "source-native-file-list.json").write_bytes(pair.final_file_list.read_bytes())

    artifact_hashes = {"cli": _sha(cli), "runner": _sha(runner), "worker": _sha(worker)}
    native_source = {"head": HEAD, "files": {name: _sha(raw) for name, raw in pair.native_files.items()},
                     "identity": pair.native_source_identity}
    final_source = {"head": HEAD, "files": {name: _sha(raw) for name, raw in pair.final_files.items()},
                    "identity": pair.final_source_identity}
    for relative, content in (
        ("native-artifacts/ygo-cli.exe", cli),
        ("native-artifacts/curry-option-validation.exe", runner),
        ("native-artifacts/ygo-engine-worker.exe", worker),
        ("final-build/native-artifacts/ygo-cli.exe", cli),
        ("final-build/native-artifacts/curry-option-validation.exe", runner),
        ("final-build/native-artifacts/ygo-engine-worker.exe", worker),
    ):
        _write(repo, ASSET_SCOPE_ROOT + "/" + relative, content)

    def build_record(source: dict) -> bytes:
        unsigned = {
            "schema_version": 1, "kind": "build_record", "status": "recorded",
            "source_before": source, "source_after": source,
            "reproducible_build_proven": False, "artifacts": artifact_hashes,
        }
        return _canonical({**unsigned, "identity": _sha(_canonical(unsigned))})

    _write(repo, f"{ASSET_SCOPE_ROOT}/build-record.json", build_record(native_source))
    _write(repo, f"{ASSET_SCOPE_ROOT}/final-build/build-record.json", build_record(final_source))

    manifest = {
        "schema_version": 1, "kind": "native_curry_option_validation_manifest",
        "scope": "curry-option-validation-v1", "batch_kind": "curry-option-validation-v1",
        "context": context, "old_consumed": 32, "limit": 7, "wall_seconds": 7200,
        "request": request, "stage1_request_sha256": _sha(_canonical(request)),
        "assets": {"ordinary": ordinary}, "started_at": 1_800_000_000,
        "input_sha256": {
            "worker": roles["worker"]["sha256"],
            "ordinary_config": _sha(b'worker_path = "synthetic/native-artifacts/ygo-engine-worker.exe"\n'),
            "tournament_config": _sha(b'worker_path = "synthetic/native-artifacts/ygo-engine-worker.exe"\n'),
        },
    }
    _write(repo, f"{ASSET_SCOPE_ROOT}/research/manifest.json", _canonical(manifest))
    request_raw = _canonical(request)
    input_doc = {
        "context": context, "stage": 1, "batch_kind": "curry-option-validation-v1",
        "request": request, "expected_identity": ordinary,
        "ledger": str(root / "research/calls.jsonl"),
        "output": str(root / "research/stage-1.json"),
    }
    input_raw = _canonical(input_doc)
    seal = {"schema_version": 1, "kind": "curry_option_validation_stage_input_seal",
            "context": context, "stage": 1, "input_sha256": _sha(input_raw)}
    _write(repo, f"{ASSET_SCOPE_ROOT}/research/stage-1-request.json", request_raw)
    _write(repo, f"{ASSET_SCOPE_ROOT}/research/stage-1-input.json", input_raw)
    _write(repo, f"{ASSET_SCOPE_ROOT}/research/stage-1-input-seal.json", _canonical(seal))
    identity_unsigned = {"schema_version": 1, "kind": "workspace_identity", "consistent": True,
                         "runtimes": {"ordinary": ordinary}}
    identity = {**identity_unsigned, "identity": _sha(_canonical(identity_unsigned))}
    identity_raw = _canonical(identity)
    _write(repo, f"{ASSET_SCOPE_ROOT}/identity.json", identity_raw)
    window = {"schema_version": 1, "kind": "curry_option_validation_window_start",
              "scope": "curry-option-validation-v1", "limit": 7, "wall_seconds": 7200,
              "started_at": manifest["started_at"]}
    window_raw = _canonical(window)
    _write(repo, f"{ASSET_SCOPE_ROOT}/window-start.json", window_raw)
    manifest["input_sha256"].update({"identity": _sha(identity_raw), "window_start": _sha(window_raw)})
    _write(repo, f"{ASSET_SCOPE_ROOT}/research/manifest.json", _canonical(manifest))

    _write(repo, f"{ASSET_SCOPE_ROOT}/research/prepared.json", _canonical({
        "context": context, "prepared": False, "native_calls": 0,
        "execution_ready": False, "stage1_input_sha256": _sha(input_raw),
    }))
    _write(repo, f"{ASSET_SCOPE_ROOT}/research/summary.json", _canonical({
        "context": context, "successful": False, "old_consumed": 32,
        "diagnostic": "curry_preflight_output_mismatch", "new_consumed": None,
        "new_unknown": None,
    }))
    _write(repo, f"{ASSET_SCOPE_ROOT}/ordinary-candidate.toml", b'worker_path = "synthetic/native-artifacts/ygo-engine-worker.exe"\n')
    _write(repo, f"{ASSET_SCOPE_ROOT}/tournament-candidate.toml", b'worker_path = "synthetic/native-artifacts/ygo-engine-worker.exe"\n')
    diagnostics = root / "process-diagnostics"
    stdout = b""
    stderr = b"Curry asset identity differs from frozen request\n"
    _write(repo, f"{ASSET_SCOPE_ROOT}/process-diagnostics/stdout.bin", stdout)
    _write(repo, f"{ASSET_SCOPE_ROOT}/process-diagnostics/stderr.bin", stderr)
    metadata = {
        "runner_role": "curry_option_validation_runner", "mode": "preflight_only",
        "status": "completed", "return_code": 2, "error_code": None,
        "stdout": {"path": "process-diagnostics/stdout.bin", "sha256": _sha(stdout), "bytes": len(stdout)},
        "stderr": {"path": "process-diagnostics/stderr.bin", "sha256": _sha(stderr), "bytes": len(stderr)},
    }
    _write(repo, f"{ASSET_SCOPE_ROOT}/process-diagnostics/preflight.json", _canonical(metadata))

    pin_paths = [
        "build-record.json", "final-build/build-record.json", "research/manifest.json",
        "research/prepared.json", "research/summary.json", "research/stage-1-request.json",
        "research/stage-1-input.json", "research/stage-1-input-seal.json", "identity.json",
        "window-start.json", "process-diagnostics/preflight.json", "process-diagnostics/stdout.bin",
        "process-diagnostics/stderr.bin", "ordinary-candidate.toml", "tournament-candidate.toml",
        "native-artifacts/ygo-cli.exe", "native-artifacts/curry-option-validation.exe",
        "native-artifacts/ygo-engine-worker.exe", "final-build/native-artifacts/ygo-cli.exe",
        "final-build/native-artifacts/curry-option-validation.exe", "final-build/native-artifacts/ygo-engine-worker.exe",
        "source-native.zip", "source-native-file-list.json", "final-build/source-native.zip",
        "final-build/source-native-file-list.json",
    ]
    pins = tuple(_file_pin(repo, f"{ASSET_SCOPE_ROOT}/{path}") for path in pin_paths)
    archives = (
        _PinnedArchive("curry_native_archive", f"{ASSET_SCOPE_ROOT}/source-native.zip",
                       f"{ASSET_SCOPE_ROOT}/source-native-file-list.json", pair.native_archive_sha256,
                       pair.native_file_list_sha256, pair.native_source_identity, 4, HEAD),
        _PinnedArchive("curry_final_archive", f"{ASSET_SCOPE_ROOT}/final-build/source-native.zip",
                       f"{ASSET_SCOPE_ROOT}/final-build/source-native-file-list.json",
                       _sha((final / "source-native.zip").read_bytes()),
                       _sha((final / "source-native-file-list.json").read_bytes()),
                       pair.final_source_identity, 4, HEAD),
    )
    return _SourceDescription(
        role="asset_audit_scope", files=pins, archives=archives,
        archive_differences=(("curry_baseline", tuple(sorted(differences))),),
        dataset_counts=(
            ("historical_consumed", 32), ("historical_unknown", 0),
            ("historical_ledgers", 9),
        ),
        baseline_relative=ASSET_SCOPE_ROOT,
    )


def _synthetic_asset_audit(repo: Path) -> _SourceDescription:
    """Create the independently pinned asset-audit report and source tree."""
    from ygo_eval import curry_asset_binding_audit as asset_audit

    root = repo / ASSET_AUDIT_ROOT
    final = root / "final-build"
    final.mkdir(parents=True)
    old_scope = _synthetic_old_curry_scope(repo)
    historical_ledger_pins = _synthetic_history_ledgers(repo)

    docs = (
        "TASKS.md",
        "docs/TESTING.md",
        "docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md",
    )
    native_files = {
        f"synthetic/source-{index:03d}.txt": f"synthetic member {index}\n".encode()
        for index in range(496)
    }
    native_files[docs[0]] = b"old synthetic task\n"
    native_files[docs[1]] = b"old synthetic testing\n"
    differences = {
        docs[0]: b"new synthetic task\n",
        docs[1]: b"new synthetic testing\n",
        docs[2]: b"new synthetic handoff\n",
    }
    pair = build_synthetic_archive_pair(
        root,
        archive_filenames=("source-native.zip", "source-native-final.zip"),
        file_list_filenames=("source-native-file-list.json", "source-native-final-list.json"),
        native_files=native_files,
        differences=differences,
        source_head=HEAD,
        native_file_count=498,
        final_file_count=499,
    )
    (final / "source-native.zip").write_bytes(pair.final_archive.read_bytes())
    (final / "source-native-file-list.json").write_bytes(pair.final_file_list.read_bytes())

    native_record = {
        "role": "native_time", "sha256": pair.native_archive_sha256,
        "file_list_sha256": pair.native_file_list_sha256,
        "source_identity": pair.native_source_identity, "file_count": 498,
        "bytes": pair.native_archive.stat().st_size,
    }
    final_record = {
        "role": "final", "sha256": _sha((final / "source-native.zip").read_bytes()),
        "file_list_sha256": _sha((final / "source-native-file-list.json").read_bytes()),
        "source_identity": pair.final_source_identity, "file_count": 499,
        "bytes": (final / "source-native.zip").stat().st_size,
    }

    # The fake process is intentionally a validated sidecar set rather than a
    # stubbed result object. audit.validate_report will parse it end to end.
    context = "a" * 64
    engine_identity = "b" * 64
    stage1_input = {
        "schema_version": 1, "kind": "tenki_placement_preflight_input",
        "stage": 1, "context": context,
        "expected_identity": {"identity": engine_identity},
        "request": {"protocol_version": 2, "decisions": []},
    }
    input_path = "data/runtime/synthetic-audit/stage1-input.json"
    _write(repo, input_path, _canonical(stage1_input))
    output_raw = _canonical({
        "preflight_passed": True, "native_calls": 0, "stage": 1,
        "context": context, "identity_sha256": engine_identity,
    })
    trace = b"\n".join((
        _canonical({"phase": "input_validation", "event": "start"}),
        _canonical({"phase": "input_validation", "event": "end", "elapsed_ns": 1}),
        _canonical({"phase": "shared_preflight", "event": "start"}),
        _canonical({"phase": "shared_preflight", "event": "end", "elapsed_ns": 1}),
    )) + b"\n"
    _write(repo, f"{ASSET_AUDIT_ROOT}/process-diagnostics/stdout.bin", output_raw)
    _write(repo, f"{ASSET_AUDIT_ROOT}/process-diagnostics/stderr.bin", trace)
    stdout_record = {"path": "process-diagnostics/stdout.bin", "sha256": _sha(output_raw), "bytes": len(output_raw)}
    stderr_record = {"path": "process-diagnostics/stderr.bin", "sha256": _sha(trace), "bytes": len(trace)}
    metadata_path = "process-diagnostics/metadata.json"
    metadata_unsigned = {
        "mode": "preflight_only", "runner_role": "curry_asset_binding_audit_runner",
        "status": "completed", "return_code": 0, "error_code": None,
        "stdout": stdout_record, "stderr": stderr_record,
        "metadata_path": metadata_path,
    }
    metadata_raw = _canonical(metadata_unsigned)
    _write(repo, f"{ASSET_AUDIT_ROOT}/{metadata_path}", metadata_raw)
    process = {
        **metadata_unsigned,
        "metadata_sha256": _sha(metadata_raw), "metadata_bytes": len(metadata_raw),
        "timeout_seconds": 900,
        "trace": [
            {"phase": "input_validation", "event": "start"},
            {"phase": "input_validation", "event": "end", "elapsed_ns": 1},
            {"phase": "shared_preflight", "event": "start"},
            {"phase": "shared_preflight", "event": "end", "elapsed_ns": 1},
        ],
        "parsed_result": {
            "preflight_passed": True, "native_calls": 0, "stage": 1,
            "context": context, "identity_sha256": engine_identity,
            "matches_expected": True,
        },
    }

    # These synthetic input records exercise the public report validator and
    # the later audit's fixed cardinality checks. Every path resolves to real,
    # generated bytes; the 518 history labels deliberately remain synthetic.
    shared_input = b"synthetic audit evidence input\n"
    shared_path = "data/runtime/synthetic-audit/evidence.bin"
    _write(repo, shared_path, shared_input)
    input_records = [{
        "role": f"historical_material_{index:04d}", "path": shared_path,
        "sha256": _sha(shared_input), "bytes": len(shared_input),
    } for index in range(1, 519)]
    input_records.extend({
        "role": f"audit_input_{index:04d}", "path": shared_path,
        "sha256": _sha(shared_input), "bytes": len(shared_input),
    } for index in range(1, 30))
    input_records.append({
        "role": "stage1_input", "path": input_path,
        "sha256": _sha(_canonical(stage1_input)), "bytes": len(_canonical(stage1_input)),
    })
    history = {
        "consumed": 32, "unknown": 0, "ledger_count": 9,
        "verified_without_writable_journal": True,
        "input_set_sha256": _sha(b"synthetic historical input set"),
    }
    static_root_cause = {
        "historical_comparison_role": "worker", "engine_version_role": "dll",
        "repair_target_role": "dll",
        "root_cause": "engine_sha256_was_compared_to_worker_sha256",
        "repair": "compare_engine_sha256_to_dll_and_bind_manifest_worker",
        "historical_scan_identity_persisted": False,
    }
    scope_files = {item.relative_path: item.sha256 for item in old_scope.files}
    scope_root = Path(old_scope.baseline_relative)
    anchors = {
        "native_build_record": scope_files[(scope_root / "build-record.json").as_posix()],
        "final_build_record": scope_files[(scope_root / "final-build/build-record.json").as_posix()],
        "manifest": scope_files[(scope_root / "research/manifest.json").as_posix()],
        "prepared": scope_files[(scope_root / "research/prepared.json").as_posix()],
        "summary": scope_files[(scope_root / "research/summary.json").as_posix()],
    }
    old_builds = []
    for role, record_path, artifact_prefix, archive_role in (
        ("native_time", "build-record.json", "native-artifacts", "curry_native_archive"),
        ("final", "final-build/build-record.json", "final-build/native-artifacts", "curry_final_archive"),
    ):
        archive = next(item for item in old_scope.archives if item.role == archive_role)
        old_builds.append({
            "role": role,
            "source_identity": archive.source_identity,
            "build_record_sha256": scope_files[(scope_root / record_path).as_posix()],
            "artifact_sha256": {
                key: scope_files[(scope_root / artifact_prefix / filename).as_posix()]
                for key, filename in (
                    ("cli", "ygo-cli.exe"),
                    ("runner", "curry-option-validation.exe"),
                    ("worker", "ygo-engine-worker.exe"),
                )
            },
        })
    scope_source_archives = []
    for role, archive_role in (("native_time", "curry_native_archive"), ("final", "curry_final_archive")):
        archive = next(item for item in old_scope.archives if item.role == archive_role)
        scope_source_archives.append({
            "role": role,
            "sha256": archive.archive_sha256,
            "file_list_sha256": archive.file_list_sha256,
            "source_identity": archive.source_identity,
            "file_count": archive.file_count,
            "bytes": (repo / archive.archive_path).stat().st_size,
        })
    source = {
        "runner_role": "curry_asset_binding_audit_runner",
        "workspace_identity": pair.native_source_identity,
        "workspace_file_count": 498,
        "historical_consumed": 32,
        "historical_unknown": 0,
        "ledger_count": 9,
        "source_archive_differences": sorted(docs),
        "old_builds": old_builds,
    }
    report = {
        "schema_version": 1, "kind": "curry_asset_binding_audit", "status": "passed",
        "anchors": anchors, "native_calls": 0,
        "execution_ready": False, "original_native_diagnostic": "curry_asset_identity_mismatch",
        "checks": {name: "passed" for name in asset_audit.CHECK_NAMES},
        "inputs": input_records, "source_archives": scope_source_archives,
        "history": history,
        "old_scope": {
            "scope": asset_audit.OLD_SCOPE, "prepared": False, "ledger_exists": False,
            "consumed": None, "unknown": None,
            "stored_summary_diagnostic": asset_audit.STORED_SUMMARY_DIAGNOSTIC,
            "observed_process_diagnostic": asset_audit.ORIGINAL_DIAGNOSTIC,
        },
        "static_root_cause": static_root_cause, "source": source,
        "protection": {"file_count": 24}, "process": process,
        "diagnostic": None, "elapsed_seconds": 0.0, "input_set_sha256": history["input_set_sha256"],
        "proof_ready": False, "complete_action_coverage": False,
        "global_optimality": False, "native_probability_verified": False,
    }
    audit_raw = _canonical(report)
    _write(repo, f"{ASSET_AUDIT_ROOT}/audit-report.json", audit_raw)

    # This delivery binds to the exact generated final source archive and list.
    audit_runner = b"synthetic asset-audit runner\n"
    audit_runner_hash = _sha(audit_runner)
    audit_source = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in pair.final_files.items()},
        "identity": pair.final_source_identity,
    }
    audit_build_unsigned = {
        "schema_version": 1,
        "kind": "build_record",
        "status": "recorded",
        "source_before": audit_source,
        "source_after": audit_source,
        "reproducible_build_proven": False,
        "artifacts": {"runner": audit_runner_hash},
    }
    audit_build_raw = _canonical({
        **audit_build_unsigned,
        "identity": _sha(_canonical(audit_build_unsigned)),
    })
    audit_identity_raw = _canonical(audit_source)
    _write(repo, f"{ASSET_AUDIT_ROOT}/final-build/build-record.json", audit_build_raw)
    _write(repo, f"{ASSET_AUDIT_ROOT}/final-build/source-identity.json", audit_identity_raw)
    _write(repo, f"{ASSET_AUDIT_ROOT}/final-build/native-artifacts/curry-option-validation.exe", audit_runner)

    delivery = {
        "schema_version": 1, "kind": "curry_asset_binding_final_delivery",
        "status": "recorded", "native_calls": 0, "execution_ready": False,
        "reproducible_build_proven": False,
        "source_identity": pair.final_source_identity, "source_file_count": 499,
        "source_archive_sha256": final_record["sha256"],
        "source_file_list_sha256": final_record["file_list_sha256"],
        "runner_sha256": audit_runner_hash,
        "build_record_sha256": _sha(audit_build_raw),
        "build_record_identity": json.loads(audit_build_raw)["identity"],
        "source_identity_file_sha256": _sha(audit_identity_raw),
        "qualifications": dict(asset_audit.RESEARCH_FLAGS),
    }
    delivery_raw = _canonical(delivery)
    _write(repo, f"{ASSET_AUDIT_ROOT}/final-build/delivery.json", delivery_raw)

    # The tree's own report must be accompanied by the schema file because the
    # real validator checks for its presence. The public test validates the
    # semantic contract in Python; the file is inert synthetic material.
    _write(repo, "schemas/curry-asset-binding-audit-v1.schema.json", b'{"type":"object"}\n')

    validation_predecessor = _synthetic_validation_baseline(repo, historical_ledger_pins)
    validation_output = _synthetic_validation_output(
        repo, validation_predecessor, historical_ledger_pins,
    )
    historical_chain = _SourceDescription(
        role="historical_chain",
        dataset_counts=(
            ("previous_consumed", 26), ("previous_unknown", 0),
            ("previous_ledger_count", 7), ("confirmation_consumed", 0),
            ("confirmation_unknown", 0), ("current_consumed", 6),
            ("current_unknown", 0), ("historical_consumed", 32),
            ("historical_unknown", 0), ("historical_ledgers", 9),
        ),
        children=(
            validation_output,
            _SourceDescription(
                role="historical_ledgers",
                files=historical_ledger_pins,
                dataset_counts=(("ledger_count", 7), ("consumed", 26)),
                baseline_relative="data/runtime",
            ),
        ),
    )
    return _SourceDescription(
        role="asset_audit",
        files=(
            _PinnedFile("asset_audit_audit", f"{ASSET_AUDIT_ROOT}/audit-report.json", _sha(audit_raw)),
            _PinnedFile("asset_audit_delivery", f"{ASSET_AUDIT_ROOT}/final-build/delivery.json", _sha(delivery_raw)),
        ),
        archives=(
            _PinnedArchive(
                "asset_audit_native_archive", f"{ASSET_AUDIT_ROOT}/source-native.zip",
                f"{ASSET_AUDIT_ROOT}/source-native-file-list.json", pair.native_archive_sha256,
                pair.native_file_list_sha256, pair.native_source_identity, 498, HEAD,
            ),
            _PinnedArchive(
                "asset_audit_final_archive", f"{ASSET_AUDIT_ROOT}/final-build/source-native.zip",
                f"{ASSET_AUDIT_ROOT}/final-build/source-native-file-list.json",
                final_record["sha256"], final_record["file_list_sha256"],
                pair.final_source_identity, 499, HEAD,
            ),
        ),
        archive_differences=(("asset_audit", tuple(sorted(docs))),),
        dataset_counts=(
            ("historical_consumed", 32), ("historical_unknown", 0),
            ("historical_ledgers", 9), ("asset_audit_inputs", 548),
            ("historical_material_inputs", 518), ("asset_audit_protected_files", 24),
            ("asset_audit_source_files", 498),
        ),
        children=(old_scope, historical_chain),
        baseline_relative=ASSET_AUDIT_ROOT,
    )


def _synthetic_validation_baseline(
    repo: Path, ledger_pins: tuple[_PinnedFile, ...],
) -> _SourceDescription:
    """Materialize a complete inert runner-repair delivery and nested history.

    This is synthetic evidence for exercising the real validation path. The
    archive members and process sidecars are generated locally; no saved
    executable is started.
    """
    from ygo_eval.tenki_confirmation_runner_audit import RUNNER_ROLE
    from ygo_eval.native_tenki_placement_validation import VALIDATION_SCOPE
    from ygo_eval.tenki_placement_diagnostics import WRONG_ARCHIVED_STAGE1_LITERAL

    baseline_rel = VALIDATION_SCOPE.baseline_root.as_posix()
    root = repo / baseline_rel
    final = root / "final-build"
    final.mkdir(parents=True, exist_ok=True)

    # Produce a small, fully checked source archive with a fixed final-build
    # location. Its contents are inert text and its identity is generated by
    # the test-owned ZIP writer.
    archive_pair = build_synthetic_archive_pair(
        final,
        archive_filenames=("source-native.zip", "source-native-final.zip"),
        file_list_filenames=("source-native-file-list.json", "source-native-final-list.json"),
        native_files={
            "crates/ygo-engine-adapter/src/tenki_placement_probe.rs": (
                b'const OLD_STAGE1_SHA256: &str = "'
                + WRONG_ARCHIVED_STAGE1_LITERAL.encode("ascii") + b'";\n'
            ),
            "python/ygo_eval/native_tenki_placement.py": b"# inert synthetic validation module\n",
            "synthetic/metadata.txt": b"not an executable\n",
        },
        differences={},
        source_head=HEAD,
        native_file_count=3,
        final_file_count=3,
    )
    runner_raw = b"synthetic runner artifact; never execute\n"
    runner_path = final / "native-artifacts/tenki-placement-probe.exe"
    runner_path.parent.mkdir(parents=True, exist_ok=True)
    runner_path.write_bytes(runner_raw)

    source_description = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in archive_pair.final_files.items()},
        "identity": archive_pair.final_source_identity,
    }
    identity_raw = _canonical({"identity": archive_pair.final_source_identity})
    (final / "source-identity.json").write_bytes(identity_raw)
    build_unsigned = {
        "schema_version": 1,
        "kind": "build_record",
        "status": "recorded",
        "source_before": source_description,
        "source_after": source_description,
        "reproducible_build_proven": False,
        "artifacts": {"runner": _sha(runner_raw)},
    }
    build_raw = _canonical({**build_unsigned, "identity": _sha(_canonical(build_unsigned))})
    (final / "build-record.json").write_bytes(build_raw)

    # The passed audit report is validated through its normal schema-sidecar
    # and process-artifact path. Construct its stdout, stderr, and metadata
    # bytes first, then bind every byte in the report.
    context = _sha(b"synthetic validation audit context")
    expected_identity = _sha(b"synthetic validation runtime identity")
    stage1_input = {
        "schema_version": 1,
        "kind": "tenki_placement_preflight_input",
        "context": context,
        "stage": 1,
        "expected_identity": {"identity": expected_identity},
    }
    stage1_input_raw = _canonical(stage1_input)
    stage1_input_path = root / "audit-stage1-input.json"
    stage1_input_path.write_bytes(stage1_input_raw)
    input_record = {
        "role": "stage1_input",
        "path": (Path(baseline_rel) / "audit-stage1-input.json").as_posix(),
        "sha256": _sha(stage1_input_raw),
        "bytes": len(stage1_input_raw),
    }
    parsed = {
        "preflight_passed": True,
        "native_calls": 0,
        "stage": 1,
        "context": context,
        "identity_sha256": expected_identity,
    }
    stdout_raw = _canonical(parsed)
    trace_items = [
        {"phase": "input_validation", "event": "start"},
        {"phase": "input_validation", "event": "end", "elapsed_ns": 1},
        {"phase": "shared_preflight", "event": "start"},
        {"phase": "shared_preflight", "event": "end", "elapsed_ns": 1},
    ]
    stderr_raw = b"".join(_canonical(item) + b"\n" for item in trace_items)
    diagnostics = root / "process-diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    (diagnostics / "stdout.bin").write_bytes(stdout_raw)
    (diagnostics / "stderr.bin").write_bytes(stderr_raw)
    stdout_record = {
        "path": "process-diagnostics/stdout.bin",
        "sha256": _sha(stdout_raw),
        "bytes": len(stdout_raw),
    }
    stderr_record = {
        "path": "process-diagnostics/stderr.bin",
        "sha256": _sha(stderr_raw),
        "bytes": len(stderr_raw),
    }
    metadata_path = "process-diagnostics/metadata.json"
    metadata = {
        "mode": "preflight_only",
        "runner_role": RUNNER_ROLE,
        "status": "completed",
        "return_code": 0,
        "error_code": None,
        "stdout": stdout_record,
        "stderr": stderr_record,
        "metadata_path": metadata_path,
    }
    metadata_raw = _canonical(metadata)
    (root / metadata_path).write_bytes(metadata_raw)
    process = {
        **metadata,
        "metadata_sha256": _sha(metadata_raw),
        "metadata_bytes": len(metadata_raw),
        "timeout_seconds": 900,
        "trace": trace_items,
        "parsed_result": {
            **parsed,
            "matches_expected": True,
        },
    }
    checks = {
        name: "passed"
        for name in (
            "delivery_and_history", "source_archives", "frozen_request_and_seal",
            "eight_ledgers", "isolated_runner_build", "read_only_preflight",
            "input_stability", "trace",
        )
    }
    audit_report = {
        "schema_version": 1,
        "kind": "tenki_runner_offline_audit",
        "status": "passed",
        "baseline_anchor_sha256": _sha(b"synthetic baseline delivery"),
        "native_calls": 0,
        "execution_ready": False,
        "original_native_diagnostic": "runner_timeout",
        "checks": checks,
        "inputs": [input_record],
        "source_archives": [
            {
                "role": "native_time",
                "sha256": archive_pair.native_archive_sha256,
                "file_list_sha256": archive_pair.native_file_list_sha256,
                "source_identity": archive_pair.native_source_identity,
                "file_count": 3,
                "bytes": archive_pair.native_archive.stat().st_size,
            },
            {
                "role": "final",
                "sha256": archive_pair.final_archive_sha256,
                "file_list_sha256": archive_pair.final_file_list_sha256,
                "source_identity": archive_pair.final_source_identity,
                "file_count": 3,
                "bytes": archive_pair.final_archive.stat().st_size,
            },
        ],
        "source": {
            "runner_role": RUNNER_ROLE,
            "baseline_source_identity": archive_pair.final_source_identity,
            "historical_consumed": 26,
            "historical_unknown": 0,
            "ledger_count": 8,
            "confirmation_consumed": 0,
        },
        "process": process,
        "diagnostic": None,
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    audit_raw = _canonical(audit_report)
    (root / "audit-report.json").write_bytes(audit_raw)
    _write(repo, "schemas/tenki-runner-offline-audit-v1.schema.json", b'{"type":"object"}\n')

    archive_relative = f"{baseline_rel}/final-build/source-native-final.zip"
    list_relative = f"{baseline_rel}/final-build/source-native-final-list.json"
    source = {
        "archive": Path(archive_relative).name,
        "file_list": Path(list_relative).name,
        "archive_sha256": archive_pair.final_archive_sha256,
        "file_list_sha256": archive_pair.final_file_list_sha256,
        "identity": archive_pair.final_source_identity,
        "file_count": 3,
        "identity_file": "source-identity.json",
        "identity_file_sha256": _sha(identity_raw),
    }
    final_build = {
        "record": "build-record.json",
        "record_sha256": _sha(build_raw),
        "identity": json.loads(build_raw)["identity"],
        "runner": {
            "path": "native-artifacts/tenki-placement-probe.exe",
            "sha256": _sha(runner_raw),
            "bytes": len(runner_raw),
        },
    }
    delivery_unsigned = {
        "schema_version": 1,
        "kind": "tenki_runner_repair_final_delivery",
        "status": "completed_offline_audit",
        "historical_consumed": 26,
        "historical_unknown": 0,
        "native_calls": 0,
        "original_confirmation_result": "runner_timeout",
        "confirmation_scope_consumed": 0,
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
        "source": source,
        "final_build": final_build,
        "audit_report": {"path": "../audit-report.json", "sha256": _sha(audit_raw)},
    }
    delivery_raw = _canonical({
        **delivery_unsigned,
        "identity": _sha(_canonical(delivery_unsigned)),
    })
    (final / "delivery.json").write_bytes(delivery_raw)

    files = tuple(
        _file_pin(repo, path)
        for path in (
            f"{baseline_rel}/final-build/delivery.json",
            f"{baseline_rel}/final-build/source-identity.json",
            f"{baseline_rel}/final-build/build-record.json",
            f"{baseline_rel}/final-build/native-artifacts/tenki-placement-probe.exe",
            f"{baseline_rel}/audit-report.json",
            archive_relative,
            list_relative,
        )
    )
    validation_archive = _PinnedArchive(
        "validation_final_archive",
        archive_relative,
        list_relative,
        archive_pair.final_archive_sha256,
        archive_pair.final_file_list_sha256,
        archive_pair.final_source_identity,
        3,
        HEAD,
    )
    runner_sources = _synthetic_runner_confirmation(repo, ledger_pins)
    return _SourceDescription(
        role="validation_baseline",
        files=files,
        archives=(validation_archive,),
        baseline_relative=VALIDATION_SCOPE.baseline_root.as_posix(),
        dataset_counts=(
            ("validation_historical_consumed", 26),
            ("validation_historical_unknown", 0),
            ("validation_historical_ledgers", 7),
        ),
        children=(runner_sources,),
    )


def _synthetic_validation_output(
    repo: Path,
    validation_predecessor: _SourceDescription,
    historical_ledger_pins: tuple[_PinnedFile, ...],
) -> _SourceDescription:
    """Build an inert, complete six-stage validation delivery for the public audit.

    The actual stage scheduler and saved-evidence verifier run against the
    test-owned ``SyntheticRunner`` process boundary. No binary, engine worker,
    FFI, or real historical material is opened.
    """
    from ygo_eval import native_tenki_placement as placement
    from ygo_eval import native_tenki_placement_confirmation as confirmation
    from ygo_eval import native_tenki_placement_validation as validation
    from ygo_eval.tenki_placement_diagnostics import WRONG_ARCHIVED_STAGE1_LITERAL
    from tests.test_native_tenki_validation_workflow import SyntheticRunner

    del historical_ledger_pins  # The immutable tree carries these as a sibling child.
    spec = validation.VALIDATION_SCOPE
    relative = spec.output_root.as_posix()
    root = repo / relative
    research = root / "research"
    final = root / "final-build"
    artifacts_root = root / "native-artifacts"
    root.mkdir(parents=True, exist_ok=False)
    research.mkdir()
    final.mkdir()
    artifacts_root.mkdir()

    # Reuse the already-generated and pinned Tenki history. Reconstructing or
    # rewriting these two inputs here would invalidate their child source pins.
    prompt_root = repo / confirmation.PROMPT_BASELINE_RELATIVE
    old_stage1 = json.loads(
        (prompt_root / "research/stage-1.json").read_bytes()
    )
    old_stage2_request = json.loads(
        (prompt_root / "research/stage-2-request.json").read_bytes()
    )
    activation = placement._activation_from_history(old_stage1, old_stage2_request)
    worker_path = artifacts_root / "ygo-engine-worker.exe"
    request = json.loads(json.dumps(activation))
    request["engine"]["worker_path"] = str(worker_path)

    # The source snapshots are intentionally inert but retain the pinned
    # historical RECOVER source in both archives. Remaining members are
    # repeated synthetic placeholders to exercise the real file-count checks.
    source_members = {
        "crates/ygo-engine-adapter/src/codec.rs": SYNTHETIC_CODEC_OLD,
        "crates/ygo-engine-adapter/src/tenki_placement_probe.rs": (
            b'const OLD_STAGE1_SHA256: &str = "'
            + WRONG_ARCHIVED_STAGE1_LITERAL.encode("ascii") + b'";\n'
        ),
        "python/ygo_eval/native_tenki_placement.py": b"# synthetic archived placement source\n",
        "TASKS.md": b"synthetic validation native-time tasks\n",
        "docs/TESTING.md": b"synthetic validation native-time docs\n",
    }
    source_members.update({
        f"synthetic/archive-member-{index:04d}.txt": b"synthetic\n"
        for index in range(678)
    })
    archive_pair = build_synthetic_archive_pair(
        root,
        archive_filenames=("source-native.zip", "source-final.tmp.zip"),
        file_list_filenames=("source-native-file-list.json", "source-final.tmp-list.json"),
        native_files=source_members,
        differences={
            "TASKS.md": b"synthetic validation final tasks\n",
            "docs/TESTING.md": b"synthetic validation final docs\n",
            "docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md": b"synthetic final handoff\n",
        },
        source_head=HEAD,
        native_file_count=683,
        final_file_count=684,
    )
    final_archive = final / "source-native.zip"
    final_list = final / "source-native-file-list.json"
    final_archive.write_bytes(archive_pair.final_archive.read_bytes())
    final_list.write_bytes(archive_pair.final_file_list.read_bytes())

    # Three artifact roles are represented by distinct inert bytes. The runtime
    # identity keeps worker and DLL hashes independent as required by the
    # receipt verifier.
    artifact_bytes = {
        "runner": b"synthetic validation runner; inert\n",
        "worker": b"synthetic validation worker; inert\n",
        "cli": b"synthetic validation cli; inert\n",
    }
    native_artifact_paths = {
        "runner": artifacts_root / "tenki-placement-probe.exe",
        "worker": worker_path,
        "cli": artifacts_root / "ygo-cli.exe",
    }
    final_artifact_paths = {
        role: final / "native-artifacts" / path.name
        for role, path in native_artifact_paths.items()
    }
    (final / "native-artifacts").mkdir()
    for role, raw in artifact_bytes.items():
        native_artifact_paths[role].write_bytes(raw)
        final_artifact_paths[role].write_bytes(raw)
    dll = b"synthetic validation dll; inert\n"
    cdb = b"synthetic validation cdb; inert\n"
    scripts = b"synthetic validation script manifest; inert\n"
    # The immutable public request carries the DLL/CDB/script identities. Keep
    # those role hashes separate from the synthetic worker artifact digest.
    ordinary = {
        "consistent": True,
        "roles": {
            "worker": {"sha256": _sha(artifact_bytes["worker"])},
            "dll": {"sha256": request["versions"]["engine_sha256"]},
            "cdb": {"sha256": request["versions"]["cdb_sha256"]},
            "script_manifest": {"sha256": request["versions"]["scripts_sha256"]},
        },
    }
    if len({role["sha256"] for role in ordinary["roles"].values()}) != 4:
        raise AssertionError("synthetic_asset_roles_must_have_distinct_hashes")
    ordinary["identity"] = _sha(_canonical(ordinary))
    tournament = json.loads(json.dumps(ordinary))

    # Small source/build records bind the inert snapshots and artifacts. The
    # current codec in the synthetic repository is distinct from the archived
    # historical codec, as it is in the real transition.
    _write(repo, curry.HISTORICAL_SOURCE_TRANSITION["path"], SYNTHETIC_CODEC_CURRENT)
    native_source = {
        "identity": archive_pair.native_source_identity,
        "file_count": 683, "head": HEAD,
        "archive_sha256": archive_pair.native_archive_sha256,
        "build_record_identity": None,
    }
    final_source = {
        "source_identity": archive_pair.final_source_identity,
        "file_count": 684, "head": HEAD,
    }
    native_build_unsigned = {
        "schema_version": 1, "kind": "build_record", "status": "recorded",
        "source_before": {
            "head": HEAD,
            "files": {name: _sha(raw) for name, raw in archive_pair.native_files.items()},
            "identity": archive_pair.native_source_identity,
        },
        "source_after": {
            "head": HEAD,
            "files": {name: _sha(raw) for name, raw in archive_pair.native_files.items()},
            "identity": archive_pair.native_source_identity,
        },
        "reproducible_build_proven": False,
        "artifacts": {role: _sha(raw) for role, raw in artifact_bytes.items()},
    }
    native_build = {
        **native_build_unsigned,
        "identity": _sha(_canonical(native_build_unsigned)),
    }
    native_build_raw = _canonical(native_build)
    native_source["build_record_identity"] = native_build["identity"]
    _write(repo, f"{relative}/build-record.json", native_build_raw)

    final_build_unsigned = {
        "schema_version": 1, "kind": "build_record", "status": "recorded",
        "source_before": {
            "head": HEAD,
            "files": {name: _sha(raw) for name, raw in archive_pair.final_files.items()},
            "identity": archive_pair.final_source_identity,
        },
        "source_after": {
            "head": HEAD,
            "files": {name: _sha(raw) for name, raw in archive_pair.final_files.items()},
            "identity": archive_pair.final_source_identity,
        },
        "reproducible_build_proven": False,
        "artifacts": {role: _sha(raw) for role, raw in artifact_bytes.items()},
    }
    final_build_record = {
        **final_build_unsigned,
        "identity": _sha(_canonical(final_build_unsigned)),
    }
    final_build_raw = _canonical(final_build_record)
    (final / "build-record.json").write_bytes(final_build_raw)

    # Static input pins and candidate metadata are test-local and only support
    # the fixed manifest schema. The frozen helper validates the four inputs
    # whose derivation is security relevant.
    preparation_path = repo / curry.PREPARATION_PATH
    stage1_source_path = prompt_root / "research/stage-1.json"
    stage2_source_path = prompt_root / "research/stage-2-request.json"
    banlist_path = repo / "data/runtime/banlist.json"
    ordinary_config = _write(repo, f"{relative}/ordinary-candidate.toml",
                             b'worker_path = "synthetic/ordinary-worker.exe"\n')
    tournament_config = _write(repo, f"{relative}/tournament-candidate.toml",
                               b'worker_path = "synthetic/tournament-worker.exe"\n')
    window = {
        "schema_version": 1, "kind": "tenki_placement_validation_window_start",
        "scope": spec.scope, "limit": spec.limit,
        "wall_seconds": spec.wall_seconds, "started_at": 1_000,
    }
    _write(repo, f"{relative}/window-start.json", _canonical(window))

    # Manifest context is the canonical digest of the remaining fields. The
    # baseline-delivery role deliberately retains its fixed contract anchor.
    input_paths = {
        "runner": native_artifact_paths["runner"],
        "worker": native_artifact_paths["worker"],
        "cli": native_artifact_paths["cli"],
        "build_record": repo / relative / "build-record.json",
        "identity": _write(repo, f"{relative}/identity.json", _canonical({
            "runtimes": {"ordinary": ordinary, "tournament": tournament},
            "identity": _sha(_canonical({"ordinary": ordinary, "tournament": tournament})),
        })),
        "window_start": repo / relative / "window-start.json",
        "source_archive": repo / relative / "source-native.zip",
        "source_file_list": repo / relative / "source-native-file-list.json",
        "ordinary_config": ordinary_config,
        "tournament_config": tournament_config,
        "banlist": banlist_path,
        "preparation": preparation_path,
        "baseline_delivery": repo / spec.baseline_root / "final-build/delivery.json",
        "baseline_audit": repo / spec.baseline_root / "audit-report.json",
        "prompt_source_stage1": stage1_source_path,
        "prompt_source_stage2_request": stage2_source_path,
    }
    input_sha256 = {
        role: _sha(path.read_bytes()) for role, path in input_paths.items()
    }
    input_sha256["baseline_delivery"] = spec.delivery_sha256
    source = synthetic_source_identity(repo)
    unsigned_manifest = {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_manifest",
        "scope": spec.scope, "limit": spec.limit, "planned_calls": spec.limit,
        "wall_seconds": spec.wall_seconds, "started_at": 1_000,
        "old_consumed": spec.old_consumed,
        "baseline_delivery_sha256": spec.delivery_sha256,
        "source": source,
        "build": {
            "identity": native_build["identity"],
            "artifacts": native_build_unsigned["artifacts"],
            "record_sha256": _sha(native_build_raw),
        },
        "assets": {
            "ordinary": ordinary, "tournament": tournament,
            "identity_sha256": _sha(_canonical({"ordinary": ordinary, "tournament": tournament})),
            "execution_role": "ordinary",
        },
        "input_sha256": input_sha256,
        "source_archive": {
            "sha256": archive_pair.native_archive_sha256,
            "file_list_sha256": archive_pair.native_file_list_sha256,
            "file_count": 683,
        },
        "request": request,
        "stage1_request_sha256": _sha(_canonical(request)),
        "request_derivation": "frozen-tenki-activation-only-worker-path-replaced",
        "proof_ready": False, "complete_action_coverage": False,
        "global_optimality": False, "native_probability_verified": False,
    }
    manifest = {
        **unsigned_manifest,
        "context": _sha(_canonical(unsigned_manifest)),
    }
    validation.validate_report(manifest, spec=spec)
    manifest_raw = _canonical(manifest)
    (research / "manifest.json").write_bytes(manifest_raw)

    # Build a captured preflight process record with a fake process runner.
    stage1_input = {
        "context": manifest["context"],
        "ledger": str(research / "calls.jsonl"),
        "output": str(research / "stage-1.json"), "stage": 1,
        "request": request, "expected_identity": ordinary,
        "started_at": manifest["started_at"],
        "batch_kind": spec.batch_kind,
    }
    stage1_input_raw = _canonical(stage1_input)
    (research / "stage-1-input.json").write_bytes(stage1_input_raw)
    (research / "stage-1-request.json").write_bytes(_canonical(request))
    (research / "stage-1-input-seal.json").write_bytes(_canonical({
        "schema_version": 1, "kind": spec.input_seal_kind,
        "context": manifest["context"], "stage": 1,
        "input_sha256": _sha(stage1_input_raw),
    }))
    preflight_output = {
        "context": manifest["context"],
        "identity_sha256": ordinary["identity"],
        "native_calls": 0, "preflight_passed": True, "stage": 1,
    }

    def preflight_process(command, *, cwd, capture_output, timeout, check):
        del cwd, capture_output, timeout, check
        return subprocess.CompletedProcess(
            command, 0, _canonical(preflight_output),
            b'{"phase":"input_validation","event":"end","elapsed_ns":1}\n',
        )

    _process, completed, preflight_hash = validation._run_process(
        native_artifact_paths["runner"], research / "stage-1-input.json",
        repo, root, "preflight_only", timeout=900,
        process_runner=preflight_process, spec=spec,
    )
    if completed is None or completed.returncode != 0:
        raise AssertionError(
            f"synthetic_validation_preflight_failed:{_process!r}:{completed!r}"
        )
    prepared = {
        "schema_version": 1,
        "kind": "native_tenki_placement_validation_prepared",
        "scope": spec.scope, "context": manifest["context"],
        "prepared": True, "execution_ready": True, "native_calls": 0,
        "planned_calls": spec.limit,
        "stage1_request_sha256": manifest["stage1_request_sha256"],
        "preflight_diagnostic_sha256": preflight_hash,
        "manifest_sha256": _sha(manifest_raw),
        "stage1_input_sha256": _sha(stage1_input_raw),
        "diagnostics": [],
        "proof_ready": False, "complete_action_coverage": False,
        "global_optimality": False, "native_probability_verified": False,
    }
    validation.validate_report(prepared, spec=spec)
    prepared_raw = _canonical(prepared)
    (research / "prepared.json").write_bytes(prepared_raw)
    (research / "preflight-process-diagnostic.json").write_bytes(_canonical(_process))

    # All six stages and their exact parent derivations pass through the real
    # production workflow; only subprocess interaction is synthesized.
    fake_runner = SyntheticRunner()
    protected: dict[Path, str] = {}
    frozen_files = {
        Path(path): _sha(path.read_bytes())
        for path in (
            preparation_path, stage1_source_path, stage2_source_path,
            banlist_path, ordinary_config, tournament_config,
        )
    }
    with synthetic_source_sampler():
        stage_summary = validation._run_six_stages(
            root=root, output=research, runner=native_artifact_paths["runner"],
            repo=repo, manifest=manifest, prepared_hash=_sha(prepared_raw),
            stage1_request=request, expected_identity=ordinary, source=source,
            protected=protected, frozen_files=frozen_files,
            process_runner=fake_runner, spec=spec, clock=lambda: 2_000,
        )
    if stage_summary.get("successful") is not True:
        raise AssertionError(f"synthetic_validation_stages_failed:{stage_summary.get('diagnostic')}")

    # Replace SyntheticRunner's deliberately non-ledger placeholder with the
    # real test-owned authenticated journal format, then run production's
    # verify-only checker over the completed six-stage evidence.
    ledger_path = research / "calls.jsonl"
    _synthetic_generic_ledger(
        ledger_path, "tenki-placement-validation-v1", manifest["context"],
        spec.limit, spec.limit, "validation-output",
    )
    verification = validation._verify_only(
        root, research, native_artifact_paths["runner"], repo, manifest,
        _sha(prepared_raw), fake_runner, spec,
    )
    if verification.get("valid") is not True:
        raise AssertionError(f"synthetic_validation_verify_failed:{verification.get('diagnostic')}")

    # Complete archive/build metadata after stage generation (the archive is
    # independent of the ignored research tree).
    native_archive_meta = _PinnedArchive(
        "curry_native_archive", f"{relative}/source-native.zip",
        f"{relative}/source-native-file-list.json",
        archive_pair.native_archive_sha256, archive_pair.native_file_list_sha256,
        archive_pair.native_source_identity, 683, HEAD,
    )
    final_archive_meta = _PinnedArchive(
        "curry_final_archive", f"{relative}/final-build/source-native.zip",
        f"{relative}/final-build/source-native-file-list.json",
        _sha(final_archive.read_bytes()), _sha(final_list.read_bytes()),
        archive_pair.final_source_identity, 684, HEAD,
    )
    acceptance = {
        "schema_version": 1,
        "kind": "tenki_placement_validation_acceptance",
        "scope": spec.scope, "status": "completed_and_paused",
        "qualifications": dict(curry.FLAGS),
        "native": {
            "old_consumed": spec.old_consumed, "new_consumed": spec.limit,
            "cumulative_consumed": spec.old_consumed + spec.limit,
            "unknown": 0, "stages_completed": spec.limit,
            "stages_total": spec.limit, "successful": True,
            "scope_sealed": True, "verify_only_native_calls": 0,
            "replay_matches": {"false_branch_stage4": True, "true_branch_stage6": True},
            "ledger_path": "research/calls.jsonl",
            "ledger_sha256": _sha(ledger_path.read_bytes()),
            "summary_path": "research/summary.json",
            "summary_sha256": _sha((research / "summary.json").read_bytes()),
            "verification_path": "research/verification.json",
            "verification_sha256": _sha((research / "verification.json").read_bytes()),
        },
        "native_source": {
            "identity": archive_pair.native_source_identity, "head": HEAD,
            "file_count": 683, "archive_sha256": archive_pair.native_archive_sha256,
            "build_record_identity": native_build["identity"],
        },
        "final_delivery": {
            "path": "final-build/delivery.json",
            "sha256": _sha(b"filled after delivery"),
        },
    }
    # Fill the source and acceptance/delivery cross-reference in a single
    # deterministic pass.
    delivery = {
        "schema_version": 1,
        "kind": "tenki_placement_validation_final_delivery",
        "scope": spec.scope, "qualifications": dict(curry.FLAGS),
        "native_source_identity": archive_pair.native_source_identity,
        "native_evidence": {
            "old_consumed": spec.old_consumed, "new_consumed": spec.limit,
            "cumulative_consumed": spec.old_consumed + spec.limit, "unknown": 0,
            "verification_native_calls": 0,
            "ledger_path": "../research/calls.jsonl",
            "ledger_sha256": acceptance["native"]["ledger_sha256"],
            "summary_path": "../research/summary.json",
            "summary_sha256": acceptance["native"]["summary_sha256"],
            "verification_path": "../research/verification.json",
            "verification_sha256": acceptance["native"]["verification_sha256"],
        },
        "final_source": final_source,
        "source_archive": {
            "path": "source-native.zip",
            "file_list_path": "source-native-file-list.json",
            "sha256": final_archive_meta.archive_sha256,
            "file_list_sha256": final_archive_meta.file_list_sha256,
        },
        "build_record": {
            "path": "build-record.json", "sha256": _sha(final_build_raw),
            "identity": final_build_record["identity"],
        },
        "final_artifacts": {
            role: {
                "path": f"native-artifacts/{final_artifact_paths[role].name}",
                "sha256": _sha(raw), "bytes": len(raw),
            } for role, raw in artifact_bytes.items()
        },
    }
    delivery["schema_version"] = 1
    delivery_raw = _canonical(delivery)
    (final / "delivery.json").write_bytes(delivery_raw)
    acceptance["final_delivery"]["sha256"] = _sha(delivery_raw)
    acceptance_raw = _canonical(acceptance)
    (root / "acceptance.json").write_bytes(acceptance_raw)

    files = [
        _file_pin(repo, f"{relative}/acceptance.json", "curry_acceptance"),
        _file_pin(repo, f"{relative}/final-build/delivery.json", "curry_delivery"),
        _file_pin(repo, f"{relative}/research/manifest.json", "curry_manifest"),
        _file_pin(repo, f"{relative}/research/prepared.json", "curry_prepared"),
        _file_pin(repo, f"{relative}/research/summary.json", "curry_summary"),
        _file_pin(repo, f"{relative}/research/verification.json", "curry_verification"),
        _file_pin(repo, f"{relative}/research/calls.jsonl", "curry_ledger"),
        _file_pin(repo, f"{relative}/build-record.json", "curry_native_build_record"),
        _file_pin(repo, f"{relative}/final-build/build-record.json", "curry_final_build_record"),
        _file_pin(repo, f"{relative}/source-native.zip", "curry_native_archive_file"),
        _file_pin(repo, f"{relative}/source-native-file-list.json", "curry_native_file_list"),
        _file_pin(repo, f"{relative}/final-build/source-native.zip", "curry_final_archive_file"),
        _file_pin(repo, f"{relative}/final-build/source-native-file-list.json", "curry_final_file_list"),
    ]
    for role, path in native_artifact_paths.items():
        files.append(_file_pin(repo, path.relative_to(repo).as_posix(), f"curry_native_{role}"))
    for role, path in final_artifact_paths.items():
        files.append(_file_pin(repo, path.relative_to(repo).as_posix(), f"curry_final_{role}"))
    files.extend((
        _file_pin(repo, stage1_source_path.relative_to(repo).as_posix(), "validation_prompt_stage1"),
        _file_pin(repo, stage2_source_path.relative_to(repo).as_posix(), "validation_prompt_stage2_request"),
        _file_pin(repo, preparation_path.relative_to(repo).as_posix(), "validation_preparation"),
        _file_pin(repo, banlist_path.relative_to(repo).as_posix(), "validation_banlist"),
    ))
    return _SourceDescription(
        role="curry_baseline",
        files=tuple(files),
        archives=(native_archive_meta, final_archive_meta),
        semantic_hashes=(
            ("historical_codec", _sha(SYNTHETIC_CODEC_OLD)),
            ("current_codec", _sha(SYNTHETIC_CODEC_CURRENT)),
        ),
        archive_differences=(("curry_baseline", (
            "TASKS.md",
            "docs/TESTING.md",
            "docs/superpowers/plans/2026-10-24-curry-option-validation-handoff.md",
        )),),
        dataset_counts=(
            ("historical_consumed", 32), ("historical_unknown", 0),
            ("historical_ledgers", 9),
        ),
        children=(validation_predecessor,),
        baseline_relative=relative,
    )


def _synthetic_runner_confirmation(
    repo: Path, ledger_pins: tuple[_PinnedFile, ...],
) -> _SourceDescription:
    """Create the first byte-authenticated artifacts for runner-repair history."""
    from ygo_eval.tenki_confirmation_runner_audit import EXPERIMENT_RELATIVE

    root = repo / EXPERIMENT_RELATIVE
    final = root / "final-build"
    final.mkdir(parents=True, exist_ok=True)
    native_files = {
        "crates/ygo-engine-adapter/src/tenki_placement_probe.rs": (
            b'const OLD_STAGE1_SHA256: &str = "' + b"a" * 64 + b'";\n'
        ),
        "python/ygo_eval/native_tenki_placement.py": b"# synthetic history module\n",
        "synthetic/source.txt": b"synthetic runner-repair archive\n",
    }
    pair = build_synthetic_archive_pair(
        root,
        archive_filenames=("source-native.zip", "source-native-final.zip"),
        file_list_filenames=("source-native-file-list.json", "source-native-final-list.json"),
        native_files=native_files,
        differences={},
        source_head=HEAD,
        native_file_count=3,
        final_file_count=3,
    )
    final_archive = final / "source-native.zip"
    final_list = final / "source-native-file-list.json"
    final_archive.write_bytes(pair.final_archive.read_bytes())
    final_list.write_bytes(pair.final_file_list.read_bytes())
    artifact_bytes = {
        "runner": b"synthetic tenki runner\n",
        "worker": b"synthetic engine worker\n",
        "cli": b"synthetic cli\n",
    }
    artifact_names = {
        "runner": "tenki-placement-probe.exe",
        "worker": "ygo-engine-worker.exe",
        "cli": "ygo-cli.exe",
    }
    for folder in (root / "native-artifacts", final / "native-artifacts"):
        folder.mkdir(parents=True, exist_ok=True)
        for role, raw in artifact_bytes.items():
            (folder / artifact_names[role]).write_bytes(raw)

    native_source = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in pair.native_files.items()},
        "identity": pair.native_source_identity,
    }
    final_source = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in pair.final_files.items()},
        "identity": pair.final_source_identity,
    }

    def signed_build(source: dict[str, Any]) -> bytes:
        unsigned = {
            "schema_version": 1,
            "kind": "build_record",
            "status": "recorded",
            "source_before": source,
            "source_after": source,
            "reproducible_build_proven": False,
            "artifacts": {role: _sha(raw) for role, raw in artifact_bytes.items()},
        }
        return _canonical({**unsigned, "identity": _sha(_canonical(unsigned))})

    native_build_raw = signed_build(native_source)
    final_build_raw = signed_build(final_source)
    (root / "build-record.json").write_bytes(native_build_raw)
    (final / "build-record.json").write_bytes(final_build_raw)
    flags = {
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    # Build a self-consistent manifest context from independently generated
    # test bytes. The source description below authenticates this value; it is
    # deliberately not copied from the production report.
    ordinary_roles = {
        "worker": {"sha256": _sha(artifact_bytes["worker"])},
        "dll": {"sha256": _sha(b"synthetic confirmation dll\n")},
        "cdb": {"sha256": _sha(b"synthetic confirmation cdb\n")},
        "script_manifest": {"sha256": _sha(b"synthetic confirmation scripts\n")},
    }
    ordinary = {"consistent": True, "roles": ordinary_roles}
    ordinary["identity"] = _sha(_canonical(ordinary))
    tournament = {
        "consistent": True,
        "roles": {
            "worker": {"sha256": _sha(artifact_bytes["worker"])},
            "dll": {"sha256": _sha(b"synthetic tournament dll\n")},
            "cdb": {"sha256": _sha(b"synthetic tournament cdb\n")},
            "script_manifest": {"sha256": _sha(b"synthetic tournament scripts\n")},
        },
    }
    tournament["identity"] = _sha(_canonical(tournament))
    request = {
        "protocol_version": 2,
        "seed": 1,
        "probe_only": False,
        "decisions": [],
        "versions": {
            "engine_sha256": ordinary_roles["dll"]["sha256"],
            "cdb_sha256": ordinary_roles["cdb"]["sha256"],
            "scripts_sha256": ordinary_roles["script_manifest"]["sha256"],
        },
        "engine": {"worker_path": "synthetic/tenki-worker.exe"},
    }
    request_raw = _canonical(request)
    request_hash = _sha(request_raw)
    started_at = 1_798_000_000
    identity_unsigned = {
        "schema_version": 1,
        "kind": "workspace_identity",
        "consistent": True,
        "build_provenance": "unverified",
        "reproducible_build_proven": False,
        "runtimes": {"ordinary": ordinary, "tournament": tournament},
    }
    runtime_identity_raw = _canonical({
        **identity_unsigned,
        "identity": _sha(_canonical(identity_unsigned)),
    })
    identity_hash = _sha(runtime_identity_raw)
    window_raw = _canonical({
        "schema_version": 1,
        "kind": "tenki_placement_confirmation_window_start",
        "scope": "tenki-placement-confirmation-v1",
        "limit": 6,
        "wall_seconds": 7200,
        "started_at": started_at,
    })
    manifest_unsigned = {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_manifest",
        "scope": "tenki-placement-confirmation-v1",
        "limit": 6,
        "wall_seconds": 7200,
        "old_consumed": 26,
        "started_at": started_at,
        "input_sha256": {
            "prompt_source_stage1": _sha(b"synthetic prompt stage 1"),
            "prompt_source_stage2_request": _sha(b"synthetic prompt stage 2 request"),
            "runner": _sha(artifact_bytes["runner"]),
            "identity": identity_hash,
            "window_start": _sha(window_raw),
        },
        "source": {"identity": pair.native_source_identity},
        "build": {"artifacts": {role: _sha(raw) for role, raw in artifact_bytes.items()}},
        "assets": {
            "ordinary": ordinary,
            "tournament": tournament,
            "identity_sha256": identity_unsigned["identity"] if "identity" in identity_unsigned else _sha(_canonical(identity_unsigned)),
            "execution_role": "ordinary",
        },
        "request": request,
        "stage1_request_sha256": request_hash,
        **flags,
    }
    context = _sha(_canonical(manifest_unsigned))
    manifest = {**manifest_unsigned, "context": context}
    manifest_raw = _canonical(manifest)
    stage1_input = {
        "schema_version": 1,
        "kind": "tenki_placement_confirmation_stage_input",
        "context": context,
        "stage": 1,
        "batch_kind": "tenki-placement-confirmation-v1",
        "request": request,
        "expected_identity": ordinary,
        "ledger": str(root / "research/calls.jsonl"),
        "output": str(root / "research/stage-1.json"),
        "started_at": started_at,
    }
    stage1_input_raw = _canonical(stage1_input)
    stage1_seal_raw = _canonical({
        "schema_version": 1,
        "kind": "tenki_placement_confirmation_stage_input_seal",
        "context": context,
        "stage": 1,
        "input_sha256": _sha(stage1_input_raw),
    })
    stdout = b""
    stderr = b"synthetic timed out before output\n"
    stdout_raw = _sha(stdout)
    stderr_hash = _sha(stderr)
    diagnostic = {
        "runner_role": "tenki_placement_confirmation_runner",
        "mode": "normal",
        "status": "timeout",
        "return_code": None,
        "error_code": "runner_timeout",
        "input_sha256": _sha(stage1_input_raw),
        "prepared_sha256": None,
        "metadata_path": "stage-1-process-diagnostic.json",
        "stdout": {
            "path": "process-diagnostics/stage-1.stdout.bin",
            "sha256": stdout_raw,
            "bytes": len(stdout),
        },
        "stderr": {
            "path": "process-diagnostics/stage-1.stderr.bin",
            "sha256": stderr_hash,
            "bytes": len(stderr),
        },
    }
    diagnostic_hash = _sha(_canonical(diagnostic))
    prepared_raw = _canonical({
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_prepared",
        "scope": "tenki-placement-confirmation-v1",
        "context": context,
        "prepared": True,
        "execution_ready": True,
        "native_calls": 0,
        "planned_calls": 6,
        "stage1_input_sha256": _sha(stage1_input_raw),
    })
    stage_report_raw = _canonical({
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_stage",
        "scope": "tenki-placement-confirmation-v1",
        "context": context,
        "stage": 1,
        "successful": False,
        "native_calls": 0,
        "diagnostic": "runner_timeout",
        "receipt_sha256": None,
        "diagnostic_sha256": diagnostic_hash,
        "independent_replay_matches": None,
        "ledger": None,
    })
    summary_raw = _canonical({
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_summary",
        "scope": "tenki-placement-confirmation-v1",
        "context": context,
        "successful": False,
        "old_consumed": 26,
        "new_consumed": None,
        "cumulative_consumed": None,
        "unknown": None,
        "ledger": None,
        "stages": [],
        "diagnostic": "runner_timeout",
        **flags,
    })
    verification_raw = _canonical({
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_verification",
        "scope": "tenki-placement-confirmation-v1",
        "context": context,
        "valid": False,
        "native_calls": 0,
        "old_consumed": 26,
        "new_consumed": None,
        "cumulative_consumed": None,
        "unknown": None,
        "stages": [],
        "diagnostic": "incomplete_stage_receipts",
        **flags,
    })
    delivery = {
        "schema_version": 1,
        "kind": "native_tenki_placement_confirmation_delivery",
        "scope": "tenki-placement-confirmation-v1",
        "context": context,
        "history_totals": {
            "consumed": 26,
            "old_runner_availability_reverified": False,
            "unknown": 0,
        },
        "native_outcome": {
            "first_stage_diagnostic": "runner_timeout",
            "charged_calls": 0,
            "unknown_consumption": 0,
            "stdout_sha256": stdout_raw,
            "stderr_sha256": stderr_hash,
        },
        "window": {"remaining_slots_authorized": 0},
        "qualifications": flags,
        "final_source": {
            "identity": pair.final_source_identity,
            "file_count": 3,
            "archive": "source-native.zip",
            "file_list": "source-native-file-list.json",
            "archive_sha256": _sha(final_archive.read_bytes()),
            "file_list_sha256": _sha(final_list.read_bytes()),
            "identity_file_sha256": _sha(_canonical({"identity": pair.final_source_identity})),
            "identity_file": "source-identity.json",
        },
        "native_time": {
            "source_archive_sha256": pair.native_archive_sha256,
            "source_file_list_sha256": pair.native_file_list_sha256,
            "source_identity": pair.native_source_identity,
            "source_file_count": 3,
            "ordinary_asset_identity": ordinary["identity"],
            "build_record_sha256": _sha(native_build_raw),
            "build_record_identity": json.loads(native_build_raw)["identity"],
            "artifact_sha256": {role: _sha(raw) for role, raw in artifact_bytes.items()},
        },
        "final_build": {
            "record": "build-record.json",
            "record_sha256": _sha(final_build_raw),
            "identity": json.loads(final_build_raw)["identity"],
            "artifacts": {
                role: {
                    "relative_path": f"native-artifacts/{artifact_names[role]}",
                    "sha256": _sha(raw),
                }
                for role, raw in artifact_bytes.items()
            },
        },
        "reports": {
            "prepared_sha256": _sha(prepared_raw),
            "stage1_report_sha256": _sha(stage_report_raw),
            "summary_sha256": _sha(summary_raw),
            "verification_sha256": _sha(verification_raw),
        },
    }
    delivery_raw = _canonical(delivery)
    (final / "delivery.json").write_bytes(delivery_raw)
    final_source_identity_raw = _canonical({"identity": pair.final_source_identity})
    (final / "source-identity.json").write_bytes(final_source_identity_raw)
    _write(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/source-identity.json",
           _canonical({"identity": pair.native_source_identity}))
    final_identity_raw = _canonical({"identity": pair.final_source_identity})
    # The final identity was written above before the native build metadata was
    # assembled. Re-write identical bytes with the bound final source identity.
    (final / "source-identity.json").write_bytes(final_identity_raw)
    research = root / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "manifest.json").write_bytes(manifest_raw)
    (research / "stage-1-request.json").write_bytes(request_raw)
    (research / "stage-1-input.json").write_bytes(stage1_input_raw)
    (research / "stage-1-input-seal.json").write_bytes(stage1_seal_raw)
    (research / "prepared.json").write_bytes(prepared_raw)
    (research / "stage-1-report.json").write_bytes(stage_report_raw)
    (research / "summary.json").write_bytes(summary_raw)
    (research / "verification.json").write_bytes(verification_raw)
    # ``identity.json`` is the frozen runtime workspace identity bound by the
    # manifest and stage-1 invocation. Keep the source-archive identity in its
    # separate ``source-identity.json`` artifact above.
    (root / "identity.json").write_bytes(runtime_identity_raw)
    (root / "window-start.json").write_bytes(window_raw)
    (root / "process-diagnostics").mkdir(parents=True, exist_ok=True)
    (root / diagnostic["stdout"]["path"]).write_bytes(stdout)
    (root / diagnostic["stderr"]["path"]).write_bytes(stderr)
    (root / diagnostic["metadata_path"]).write_bytes(_canonical(diagnostic))
    # The current confirmation ledger is intentionally empty of native calls.
    # It contains only its frozen header and initial checkpoint.
    checkpoint_blob = {
        "budget": {
            "consumed": 0, "completed": 0, "unknown": 0,
            "reserved": 0, "abandoned": 0,
        },
        "charged_sequence": _sha(_canonical([])),
    }
    checkpoint_raw = _canonical(checkpoint_blob)
    checkpoint_hash = _sha(checkpoint_raw)
    checkpoint_path = research / "calls.jsonl.blobs/checkpoints" / f"{checkpoint_hash}.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(checkpoint_raw)
    entries = [
        {"kind": "header", "version": 1, "scope": "tenki-placement-confirmation-v1",
         "context": context, "limit": 6},
        {"kind": "checkpoint", "name": "immutable/tenki-placement-confirmation/start",
         "blob": checkpoint_hash, "consumed": 0, "charged_sequence": _sha(_canonical([]))},
    ]
    rows = []
    previous = ""
    for sequence, entry in enumerate(entries):
        canonical_entry = {
            key: entry[key]
            for key in ("kind", "version", "scope", "context", "limit")
        } if entry["kind"] == "header" else {
            key: entry[key]
            for key in ("kind", "name", "blob", "consumed", "charged_sequence")
        }
        row_hash = _sha(_encode_ledger([sequence, previous, canonical_entry]))
        rows.append(_canonical({"sequence": sequence, "previous": previous,
                                "entry": entry, "hash": row_hash}))
        previous = row_hash
    (research / "calls.jsonl").write_bytes(b"\n".join(rows) + b"\n")
    # The delivery binds the empty current-scope ledger and its record count;
    # prior ledger entries remain a separate authenticated set.
    current_ledger_raw = (research / "calls.jsonl").read_bytes()
    delivery["historical_ledgers"] = [
        {"role": pin.role, "sha256": pin.sha256}
        for pin in ledger_pins
    ]
    delivery["new_ledger"] = {
        "sha256": _sha(current_ledger_raw),
        "record_count": 2,
        "consumed": 0,
        "unknown": 0,
    }
    delivery_raw = _canonical(delivery)
    (final / "delivery.json").write_bytes(delivery_raw)
    files = (
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/delivery.json"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/source-identity.json"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/build-record.json"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/build-record.json"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/source-native.zip"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/source-native-file-list.json"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/source-native.zip"),
        _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/source-native-file-list.json"),
        *(
            _file_pin(
                repo,
                (EXPERIMENT_RELATIVE / folder / "native-artifacts" / artifact_names[role]).as_posix(),
            )
            for folder in ("", "final-build")
            for role in artifact_bytes
        ),
        *(
            _file_pin(repo, f"{EXPERIMENT_RELATIVE.as_posix()}/{path}")
            for path in (
                "research/manifest.json", "research/stage-1-request.json",
                "research/stage-1-input.json", "research/stage-1-input-seal.json",
                "research/prepared.json", "research/stage-1-report.json",
                "research/summary.json", "research/verification.json",
                "identity.json", "window-start.json", "stage-1-process-diagnostic.json",
                "process-diagnostics/stage-1.stdout.bin", "process-diagnostics/stage-1.stderr.bin",
                "research/calls.jsonl",
                f"research/calls.jsonl.blobs/checkpoints/{checkpoint_hash}.json",
            )
        ),
    )
    archives = (
        _PinnedArchive(
            "runner_native_archive",
            f"{EXPERIMENT_RELATIVE.as_posix()}/source-native.zip",
            f"{EXPERIMENT_RELATIVE.as_posix()}/source-native-file-list.json",
            pair.native_archive_sha256, pair.native_file_list_sha256,
            pair.native_source_identity, 3, HEAD,
        ),
        _PinnedArchive(
            "runner_final_archive",
            f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/source-native.zip",
            f"{EXPERIMENT_RELATIVE.as_posix()}/final-build/source-native-file-list.json",
            _sha(final_archive.read_bytes()), _sha(final_list.read_bytes()),
            pair.final_source_identity, 3, HEAD,
        ),
    )
    placement_sources = _synthetic_placement_diagnostics(repo, ledger_pins)
    return _SourceDescription(
        role="runner_confirmation",
        files=files,
        archives=archives,
        dataset_counts=(
            ("historical_consumed", 26),
            ("historical_unknown", 0),
            ("historical_ledgers", 8),
        ),
        semantic_hashes=(
            ("runner_confirmation_context", context),
            ("runner_stage1_request", request_hash),
        ),
        children=(
            _SourceDescription(
                role="historical_ledgers", files=ledger_pins,
                dataset_counts=(("ledger_count", 7), ("consumed", 26)),
            ),
            _SourceDescription(
                role="placement_confirmation",
                files=placement_sources.files,
                archives=placement_sources.archives,
                semantic_hashes=placement_sources.semantic_hashes,
                archive_differences=placement_sources.archive_differences,
                dataset_counts=placement_sources.dataset_counts,
                baseline_relative=placement_sources.baseline_relative,
                children=placement_sources.children,
            ),
        ),
    )


def _synthetic_prompt_probe_baseline(
    repo: Path, ledger_pins: tuple[_PinnedFile, ...],
) -> tuple[_SourceDescription, dict[str, Any]]:
    """Materialize an inert, fully pinned Tenki pause/recovery baseline.

    This source tree exists only to drive the public audit's historical byte
    parsers. All identities and archives are generated from synthetic bytes;
    no saved runner or engine artifact is executed.
    """
    from ygo_eval.native_tenki_placement import PREPARATION_RELATIVE
    from ygo_eval.native_tenki_placement_confirmation import PROMPT_BASELINE_RELATIVE

    baseline_rel = PROMPT_BASELINE_RELATIVE.as_posix()
    baseline = repo / baseline_rel
    recovery_rel = f"{baseline_rel}/recovery-2026-10-22"
    recovery = repo / recovery_rel
    (baseline / "research").mkdir(parents=True, exist_ok=True)
    (baseline / "native-artifacts").mkdir(parents=True, exist_ok=True)
    recovery.mkdir(parents=True, exist_ok=True)

    old_worker = b"synthetic historical protected worker\n"
    new_worker = b"synthetic current protected worker\n"
    worker_path = "target/debug/ygo-engine-worker.exe"
    worker_file = repo / worker_path
    worker_file.parent.mkdir(parents=True, exist_ok=True)
    worker_file.write_bytes(new_worker)
    worker_old_hash = _sha(old_worker)
    worker_new_hash = _sha(new_worker)
    codec_path = "crates/ygo-engine-adapter/src/codec.rs"
    codec_file = repo / codec_path
    codec_file.parent.mkdir(parents=True, exist_ok=True)
    codec_file.write_bytes(SYNTHETIC_CODEC_CURRENT)
    codec_old_hash = _sha(SYNTHETIC_CODEC_OLD)
    codec_new_hash = _sha(SYNTHETIC_CODEC_CURRENT)

    # Build the fixed-cardinality protected map from real generated bytes.
    protected: dict[str, str] = {
        worker_path: worker_old_hash,
        codec_path: codec_old_hash,
    }
    for index in range(364):
        relative = f"data/runtime/synthetic-protected/prompt-{index:03d}.bin"
        raw = f"synthetic protected file {index}\n".encode("ascii")
        _write(repo, relative, raw)
        protected[relative] = _sha(raw)
    if len(protected) != 366:
        raise AssertionError("synthetic_prompt_protected_count_invalid")
    before_raw = _canonical({"schema_version": 1, "kind": "baseline_before", "protected": protected})
    _write(repo, f"{baseline_rel}/before.json", before_raw)

    pause_evidence: dict[str, dict[str, Any]] = {}
    for index in range(61):
        relative = f"evidence/pause-{index:02d}.bin"
        raw = f"synthetic pause evidence {index}\n".encode("ascii")
        _write(repo, f"{baseline_rel}/{relative}", raw)
        pause_evidence[relative] = {"sha256": _sha(raw), "bytes": len(raw)}
    pause_source_identity = _sha(b"synthetic historical prompt source identity\n")
    pause = {
        "schema_version": 1,
        "kind": "tenki_prompt_probe_pause_acceptance",
        "native_source_identity": pause_source_identity,
        "cumulative_consumed": 26,
        "unknown": 0,
        "native_calls_new": 2,
        "remaining_slots_sealed": 4,
        "native_stages": [
            {"stage": 1, "opcode": 11, "prompt_id": 7, "successful": True,
             "native_replay_verified": False},
            {"stage": 2, "opcode": 18, "prompt_id": 9, "successful": False,
             "native_replay_verified": False,
             "diagnostic": "unexpected_intermediate_prompt"},
        ],
        "evidence": pause_evidence,
    }
    pause_raw = _canonical(pause)
    _write(repo, f"{baseline_rel}/pause-acceptance.json", pause_raw)

    delivery_checkpoint = {
        "schema_version": 1,
        "kind": "tenki_prompt_probe_paused_checkpoint",
        "status": "paused_incomplete",
        "cumulative_consumed": 26,
        "unknown": 0,
        "remaining_slots_sealed": 4,
    }
    delivery_raw = _canonical(delivery_checkpoint)
    _write(repo, f"{baseline_rel}/delivery-checkpoint.json", delivery_raw)

    # The archived snapshot has 390 inert members and binds the pre-migration
    # codec bytes used by the scope-local protected-file transition.
    recovery_evidence: dict[str, dict[str, Any]] = {}
    archive_members: dict[str, bytes] = {codec_path: SYNTHETIC_CODEC_OLD}
    for index in range(16):
        relative = f"evidence/recovery-{index:02d}.bin"
        raw = f"synthetic recovery evidence {index}\n".encode("ascii")
        _write(repo, f"{recovery_rel}/{relative}", raw)
        recovery_evidence[relative] = {"sha256": _sha(raw), "bytes": len(raw)}
        archive_members[relative] = raw
    for index in range(390 - len(archive_members)):
        archive_members[f"synthetic/member-{index:03d}.txt"] = (
            f"synthetic archived member {index}\n".encode("ascii")
        )
    archive_pair = build_synthetic_archive_pair(
        recovery,
        archive_filenames=("native-source.zip", "final-source.zip"),
        file_list_filenames=("native-source-file-list.json", "source-file-list.json"),
        native_files=archive_members,
        differences={},
        source_head=HEAD,
        native_file_count=390,
        final_file_count=390,
    )
    source_identity = archive_pair.final_source_identity
    source_archive_hash = _sha(archive_pair.final_archive.read_bytes())
    source_list_hash = _sha(archive_pair.final_file_list.read_bytes())

    first_five = []
    for pin, contract in zip(ledger_pins[:5], _SYNTHETIC_LEDGER_CONTRACTS[:5], strict=True):
        _role, relative, consumed, _scope, _context, _limit = contract
        first_five.append({
            "path": relative,
            "sha256": pin.sha256,
            "consumed": consumed,
            "unknown": 0,
        })
    new_ledger = ledger_pins[5]
    recovery_acceptance = {
        "schema_version": 1,
        "kind": "tenki_contract_recovery_acceptance",
        "paused_acceptance_sha256": _sha(pause_raw),
        "paused_checkpoint_sha256": _sha(delivery_raw),
        "source_identity": source_identity,
        "source_file_count": 390,
        "source_archive_sha256": source_archive_hash,
        "evidence": recovery_evidence,
        "evidence_scope": "recovery directory contents except this acceptance and its linked checkpoint",
        "old_ledgers": first_five,
        "new_ledger_sha256": new_ledger.sha256,
        "new_ledger_consumed": 2,
        "recovery_native_calls": 0,
        "cumulative_consumed": 26,
        "old_ledger_consumed": 24,
        "unknown": 0,
        "stage1_native_success_preserved": True,
        "stage2_native_success": False,
        "stage2_diagnostic": "unexpected_intermediate_prompt",
        "stage2_opcode": 18,
        "stage2_prompt": 9,
        "remaining_slots_sealed": 4,
    }
    recovery_acceptance_raw = _canonical(recovery_acceptance)
    _write(repo, f"{recovery_rel}/recovery-acceptance.json", recovery_acceptance_raw)
    recovery_checkpoint_raw = _canonical({
        "schema_version": 1,
        "kind": "tenki_contract_recovery_checkpoint",
        "acceptance_sha256": _sha(recovery_acceptance_raw),
        "source_identity": source_identity,
    })
    _write(repo, f"{recovery_rel}/recovery-checkpoint.json", recovery_checkpoint_raw)

    # Bind the previous preparation and Rabbit source without reusing any
    # external or production evidence bytes.
    preparation_raw = (repo / PREPARATION_RELATIVE).read_bytes()
    frozen_cases_raw = (repo / curry.FROZEN_CASES_PATH).read_bytes()
    previous_report_relative = curry.PREPARATION_REPORT_PATH.as_posix()
    previous_report_raw = (repo / previous_report_relative).read_bytes()
    previous_manifest_raw = _canonical({"preparation_sha256": _sha(preparation_raw)})
    _write(repo, f"{baseline_rel}/research/manifest.json", previous_manifest_raw)

    candidate = next(
        item for item in json.loads(preparation_raw)["candidates"]
        if item.get("case", {}).get("case_id") == "prompt-13-tenki-v1"
    )
    frozen_entry = json.loads(frozen_cases_raw)["cases"][0]
    request = json.loads(json.dumps(frozen_entry["request"]))
    request["deck"] = candidate["case"]["deck"]
    request["opening_hand"] = candidate["case"]["opening_hand"]
    request["seed"] = candidate["case"]["seed"]
    request["decisions"] = []
    activation = {"kind": "command", "command": 5, "index": 0}
    actions = [{
        "choice": activation,
        "card_ids": [57_103_969],
        "bytes": [5, 0, 0, 0],
    }]
    prompt = {"id": 7, "opcode": 11, "player": 0, "actions": actions}
    event = {
        "sequence": 7,
        "opcode": 11,
        "raw": [11, 0, *([0] * 27)],
        "supported": True,
        "fields": {"prompt": prompt},
    }
    stage1 = {
        "request": request,
        "successful": True,
        "result": {"Ok": {
            "status": "decision_required", "error": None,
            "events": [event], "prompt": prompt, "resolved_decisions": [],
        }},
    }
    stage2_request = json.loads(json.dumps(request))
    stage2_request["decisions"] = [{
        "prompt_id": 7, "player": 0, "choice": activation,
    }]
    pending = {
        "id": 9, "opcode": 18, "player": 0,
        "actions": [{
            "choice": {"kind": "place", "zones": [{"player": 0, "location": 8, "sequence": 0}]},
            "bytes": [0, 8, 0],
        }],
    }
    stage2 = {
        "request": stage2_request,
        "successful": False,
        "diagnostic": "unexpected_intermediate_prompt",
        "result": {"Ok": {
            "status": "decision_required", "error": None,
            "events": [{
                "sequence": 9, "opcode": 18,
                "raw": [18, 0, 1, 255, 224, 255, 255],
                "supported": True, "fields": {"prompt": pending},
            }],
            "prompt": pending,
            "resolved_decisions": [{
                "prompt_id": 7, "player": 0, "choice": activation,
            }],
        }},
    }
    research = baseline / "research"
    old_paths = {
        "stage1": f"{baseline_rel}/research/stage-1.json",
        "stage1_request": f"{baseline_rel}/research/stage-1-request.json",
        "stage1_input": f"{baseline_rel}/research/stage-1-input.json",
        "stage2": f"{baseline_rel}/research/stage-2.json",
        "stage2_request": f"{baseline_rel}/research/stage-2-request.json",
        "stage2_input": f"{baseline_rel}/research/stage-2-input.json",
    }
    _write(repo, old_paths["stage1"], _canonical(stage1))
    _write(repo, old_paths["stage1_request"], _canonical(request))
    _write(repo, old_paths["stage1_input"], _canonical({
        "stage": 1, "request": request,
        "output": str(research / "stage-1.json"),
    }))
    _write(repo, old_paths["stage2"], _canonical(stage2))
    _write(repo, old_paths["stage2_request"], _canonical(stage2_request))
    _write(repo, old_paths["stage2_input"], _canonical({
        "stage": 2, "request": stage2_request,
        "output": str(research / "stage-2.json"),
    }))
    old_runner = b"synthetic inert saved prompt runner\n"
    _write(repo, f"{baseline_rel}/native-artifacts/prompt-probe.exe", old_runner)

    paths_to_pin = {
        f"{baseline_rel}/before.json",
        f"{baseline_rel}/pause-acceptance.json",
        f"{baseline_rel}/delivery-checkpoint.json",
        f"{recovery_rel}/recovery-acceptance.json",
        f"{recovery_rel}/recovery-checkpoint.json",
        f"{baseline_rel}/research/manifest.json",
        old_paths["stage1"], old_paths["stage1_request"], old_paths["stage1_input"],
        old_paths["stage2"], old_paths["stage2_request"], old_paths["stage2_input"],
        f"{baseline_rel}/native-artifacts/prompt-probe.exe",
        PREPARATION_RELATIVE.as_posix(), previous_report_relative,
        curry.FROZEN_CASES_PATH.as_posix(),
        *[f"{baseline_rel}/{name}" for name in pause_evidence],
        *[f"{recovery_rel}/{name}" for name in recovery_evidence],
        *[pin.relative_path for pin in ledger_pins],
        *protected.keys(),
    }
    files = tuple(
        _file_pin(repo, relative, role=f"baseline_{relative.rsplit('/', 1)[-1]}")
        for relative in sorted(paths_to_pin)
    )
    source = _SourceDescription(
        role="baseline",
        files=files,
        archives=(
            _PinnedArchive(
                "baseline_archive",
                f"{recovery_rel}/final-source.zip",
                f"{recovery_rel}/source-file-list.json",
                source_archive_hash, source_list_hash, source_identity, 390, HEAD,
            ),
        ),
        semantic_hashes=(
            ("baseline_pause_source_identity", pause_source_identity),
            ("baseline_frozen_cases", _sha(frozen_cases_raw)),
            ("transition_old_worker_sha256", worker_old_hash),
            ("transition_new_worker_sha256", worker_new_hash),
            ("curry_scope_codec_old_sha256", codec_old_hash),
            ("curry_scope_codec_sha256", codec_new_hash),
        ),
        dataset_counts=(
            ("baseline_recovery_old_ledger_entries", 5),
            ("pause_evidence_count", 61), ("recovery_evidence_count", 16),
            ("protected_file_count", 366), ("historical_consumed", 26),
            *(
                (name, contract[2])
                for contract in _SYNTHETIC_LEDGER_CONTRACTS[:7]
                for name in (
                    f"ledger_{contract[0]}_consumed",
                    f"ledger_{Path(contract[1]).parts[2]}_consumed",
                )
            ),
        ),
        baseline_relative=baseline_rel,
    )
    return source, {
        "baseline": baseline, "recovery": recovery,
        "source_identity": source_identity,
        "source_archive_sha256": source_archive_hash,
        "source_file_list_sha256": source_list_hash,
        "before_sha256": _sha(before_raw),
        "pause_sha256": _sha(pause_raw),
        "delivery_sha256": _sha(delivery_raw),
        "recovery_acceptance_sha256": _sha(recovery_acceptance_raw),
        "recovery_checkpoint_sha256": _sha(recovery_checkpoint_raw),
        "protected": protected,
        "pause_source_identity": pause_source_identity,
        "frozen_cases_sha256": _sha(frozen_cases_raw),
        "worker_old_sha256": worker_old_hash,
        "worker_new_sha256": worker_new_hash,
        "codec_old_sha256": codec_old_hash,
        "codec_new_sha256": codec_new_hash,
        "archive_pair": archive_pair,
        "stage1_request": request,
        "stage2_request": stage2_request,
        "ledger_pins": ledger_pins,
        "preparation_sha256": _sha(preparation_raw),
        "previous_manifest_sha256": _sha(previous_manifest_raw),
        "previous_report_sha256": _sha(previous_report_raw),
    }


def _synthetic_transition_record(
    repo: Path, baseline_sources: _SourceDescription, baseline_data: dict[str, Any],
    history_pair: Any,
) -> bytes:
    """Seal a v2 transition from generated bytes and an inert archive identity."""
    source_change_module = history_pair.native_files[
        "python/ygo_eval/native_tenki_placement.py"
    ]
    ledgers = []
    ledger_hashes: dict[str, str] = {}
    for pin, contract in zip(
        baseline_data["ledger_pins"][:6], _SYNTHETIC_LEDGER_CONTRACTS[:6], strict=True,
    ):
        role, relative, consumed, _scope, _context, _limit = contract
        historical_role = Path(relative).parts[2]
        ledger_hashes["ledger_" + historical_role] = pin.sha256
        ledgers.append({
            "role": historical_role, "path": relative, "sha256": pin.sha256,
            "consumed": consumed, "unknown": 0,
        })
    before_raw = (repo / f"{baseline_sources.baseline_relative}/before.json").read_bytes()
    recovery = baseline_data["recovery"]
    payload = {
        "schema_version": 2,
        "kind": "tenki_placement_baseline_transition",
        "scope": "tenki-placement-probe-v1",
        "baseline": {
            "before_sha256": baseline_data["before_sha256"],
            "pause_acceptance_sha256": baseline_data["pause_sha256"],
            "paused_delivery_checkpoint_sha256": baseline_data["delivery_sha256"],
            "recovery_acceptance_sha256": baseline_data["recovery_acceptance_sha256"],
            "recovery_checkpoint_sha256": baseline_data["recovery_checkpoint_sha256"],
            "source_archive_sha256": baseline_data["source_archive_sha256"],
            "source_file_list_sha256": baseline_data["source_file_list_sha256"],
            "source_identity": baseline_data["source_identity"],
            "source_file_count": 390,
            "historical_ledgers": ledgers,
            "protected_file_count": 366,
            "matched_protected_count": 365,
        },
        "migration": {
            "path": "target/debug/ygo-engine-worker.exe",
            "old_sha256": baseline_data["worker_old_sha256"],
            "observed_sha256": baseline_data["worker_new_sha256"],
            "old_protection_check": "failed",
            "current_file_history": "unknown",
            "effective_protection_mapping": "migrated_for_this_scope",
        },
        "audit_tool": {
            "source_identity": history_pair.native_source_identity,
            "module_sha256": _sha(source_change_module),
        },
        "claims": {
            "old_protection_check_passed": False,
            "binary_provenance_verified": False,
            "historical_reexecution_verified": False,
            "future_protection_mapping_migrated": True,
        },
        "input_sha256": {
            "before": baseline_data["before_sha256"],
            "pause_acceptance": baseline_data["pause_sha256"],
            "paused_delivery_checkpoint": baseline_data["delivery_sha256"],
            "recovery_acceptance": baseline_data["recovery_acceptance_sha256"],
            "recovery_checkpoint": baseline_data["recovery_checkpoint_sha256"],
            "protected_map": _sha(_canonical(baseline_data["protected"])),
            "source_archive": baseline_data["source_archive_sha256"],
            "source_file_list": baseline_data["source_file_list_sha256"],
            "audit_tool_source": history_pair.native_source_identity,
            "audit_tool_module": _sha(source_change_module),
            **ledger_hashes,
        },
    }
    return _canonical({**payload, "identity": _sha(_canonical(payload))})


def _synthetic_placement_diagnostics(
    repo: Path, ledger_pins: tuple[_PinnedFile, ...],
) -> _SourceDescription:
    """Create the first source-pinned layer below the runner-repair history.

    The fixture is intentionally assembled from generated bytes. It provides
    the diagnostics delivery and archive records needed to enter the older
    placement verifier; deeper experiment and prompt-baseline artifacts are
    added as each real verifier gate is reached.
    """
    from ygo_eval.native_tenki_placement_confirmation import (
        DIAGNOSTICS_RELATIVE,
        DOC_ONLY_CHANGES,
    )

    diagnostics_rel = DIAGNOSTICS_RELATIVE.as_posix()
    diagnostics = repo / diagnostics_rel
    final = diagnostics / "final-build"
    precheck = diagnostics / "verification/source-audit-strict-dedupe"
    final.mkdir(parents=True, exist_ok=True)
    precheck.mkdir(parents=True, exist_ok=True)

    # The archived code files are inert synthetic bytes. The old Rust member
    # retains the malformed historical literal because that is what the
    # verifier is intended to authenticate; nothing here is executable.
    native_members = {
        "crates/ygo-engine-adapter/src/tenki_placement_probe.rs": (
            b'const OLD_STAGE1_SHA256: &str = "'
            b'c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7601bbedce5ceaf76";\n'
        ),
        "python/ygo_eval/native_tenki_placement.py": b"# synthetic archived module\n",
        "TASKS.md": b"old generated tasks\n",
        "docs/TESTING.md": b"old generated testing\n",
        "docs/superpowers/plans/2026-10-22-tenki-placement-diagnostics-handoff.md": b"old generated handoff\n",
        "synthetic/member.txt": b"generated source member\n",
    }
    changes = {
        "TASKS.md": b"new generated tasks\n",
        "docs/TESTING.md": b"new generated testing\n",
        "docs/superpowers/plans/2026-10-22-tenki-placement-diagnostics-handoff.md": b"new generated handoff\n",
    }
    pair = build_synthetic_archive_pair(
        diagnostics,
        archive_filenames=("precheck-source.zip", "final-source.zip"),
        file_list_filenames=("precheck-source-list.json", "final-source-list.json"),
        native_files=native_members,
        differences=changes,
        source_head=HEAD,
        native_file_count=len(native_members),
        final_file_count=len(native_members),
    )
    precheck_archive = precheck / "source-native.zip"
    precheck_list = precheck / "source-native-file-list.json"
    final_archive = final / "source-native.zip"
    final_list = final / "source-native-file-list.json"
    precheck_archive.write_bytes(pair.native_archive.read_bytes())
    precheck_list.write_bytes(pair.native_file_list.read_bytes())
    final_archive.write_bytes(pair.final_archive.read_bytes())
    final_list.write_bytes(pair.final_file_list.read_bytes())

    runner = b"synthetic diagnostics runner\n"
    artifacts = {"runner": _sha(runner)}
    source_before = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in pair.final_files.items()},
        "identity": pair.final_source_identity,
    }
    build_unsigned = {
        "schema_version": 1,
        "kind": "build_record",
        "status": "recorded",
        "source_before": source_before,
        "source_after": source_before,
        "reproducible_build_proven": False,
        "artifacts": artifacts,
    }
    build_raw = _canonical({**build_unsigned, "identity": _sha(_canonical(build_unsigned))})
    _write(repo, f"{diagnostics_rel}/final-build/build-record.json", build_raw)
    preflight_raw = _canonical({"kind": "synthetic_tenki_preflight", "native_calls": 0})
    _write(repo, f"{diagnostics_rel}/preflight-report.json", preflight_raw)
    delivery_unsigned = {
        "schema_version": 1,
        "kind": "tenki_placement_diagnostics_delivery",
        "source_identity": pair.final_source_identity,
        "source_file_count": len(pair.final_files),
        "source_archive_sha256": _sha(final_archive.read_bytes()),
        "source_file_list_sha256": _sha(final_list.read_bytes()),
        "build_record_sha256": _sha(build_raw),
        "build_record_identity": json.loads(build_raw)["identity"],
        "runner_sha256": artifacts["runner"],
        "status": "offline_preflight_passed_native_target_still_failed",
        "preflight_status": "passed",
        "native_calls_this_batch": 0,
        "historical_consumed": 26,
        "historical_unknown": 0,
        "placement_consumed": 0,
        "placement_unknown": 0,
        "window_reset": False,
    }
    delivery_raw = _canonical({
        **delivery_unsigned, "identity": _sha(_canonical(delivery_unsigned)),
    })
    _write(repo, f"{diagnostics_rel}/final-build/delivery.json", delivery_raw)
    acceptance_unsigned = {
        "schema_version": 1,
        "kind": "tenki_placement_diagnostics_acceptance",
        "status": "offline_preflight_accepted_native_trial_not_accepted",
        "delivery_identity": json.loads(delivery_raw)["identity"],
        "final_source_identity": pair.final_source_identity,
        "preflight_report_sha256": _sha(preflight_raw),
        "preflight_audit_source_identity": pair.native_source_identity,
        "historical_consumed": 26,
        "historical_unknown": 0,
        "placement_consumed": 0,
        "placement_unknown": 0,
    }
    acceptance_raw = _canonical({
        **acceptance_unsigned, "identity": _sha(_canonical(acceptance_unsigned)),
    })
    _write(repo, f"{diagnostics_rel}/final-build/acceptance.json", acceptance_raw)
    (final / "runner.exe").write_bytes(runner)

    # Create the frozen (failed-before-charge) placement experiment that the
    # diagnostics verifier binds as provenance. All binaries are inert bytes;
    # the public audit only hashes and parses the evidence.
    from ygo_eval.native_tenki_placement_confirmation import OLD_PLACEMENT_RELATIVE
    from ygo_eval.native_tenki_placement import (
        OLD_STAGE2_REQUEST_SHA256,
        OLD_STAGE2_SHA256,
        TRANSITION_V2_NEW_SHA256,
    )
    from ygo_eval.tenki_placement_diagnostics import CORRECT_STAGE1_LITERAL

    experiment_rel = OLD_PLACEMENT_RELATIVE.as_posix()
    experiment = repo / experiment_rel
    research = experiment / "research"
    experiment_final = experiment / "final-build"
    verification = experiment / "verification"
    research.mkdir(parents=True, exist_ok=True)
    experiment_final.mkdir(parents=True, exist_ok=True)
    verification.mkdir(parents=True, exist_ok=True)

    history_members = {
        "crates/ygo-engine-adapter/src/tenki_placement_probe.rs": (
            b'const OLD_STAGE1_SHA256: &str = "'
            b'c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7601bbedce5ceaf76";\n'
        ),
        "python/ygo_eval/native_tenki_placement.py": b"# synthetic historical placement module\n",
    }
    history_pair = build_synthetic_archive_pair(
        experiment,
        archive_filenames=("source-native.zip", "unused-final.zip"),
        file_list_filenames=("source-native-file-list.json", "unused-final-list.json"),
        native_files=history_members,
        differences={},
        source_head=HEAD,
        native_file_count=2,
        final_file_count=2,
    )
    (experiment_final / "source-final.zip").write_bytes(history_pair.final_archive.read_bytes())
    (experiment_final / "source-final-file-list.json").write_bytes(history_pair.final_file_list.read_bytes())
    prompt_baseline_sources, prompt_baseline_data = _synthetic_prompt_probe_baseline(
        repo, ledger_pins,
    )

    hist_runner = b"synthetic old placement runner\n"
    hist_worker = b"synthetic old placement worker\n"
    hist_cli = b"synthetic old placement cli\n"
    hist_artifacts = {
        "runner": _sha(hist_runner), "worker": _sha(hist_worker), "cli": _sha(hist_cli),
    }
    for relative, raw in (
        ("native-artifacts/tenki-placement-probe.exe", hist_runner),
        ("native-artifacts/ygo-engine-worker.exe", hist_worker),
        ("native-artifacts/ygo-cli.exe", hist_cli),
    ):
        _write(repo, f"{experiment_rel}/{relative}", raw)

    hist_source = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in history_pair.native_files.items()},
        "identity": history_pair.native_source_identity,
    }
    hist_build_unsigned = {
        "schema_version": 1, "kind": "build_record", "status": "recorded",
        "source_before": hist_source, "source_after": hist_source,
        "reproducible_build_proven": False, "artifacts": hist_artifacts,
    }
    hist_build_raw = _canonical({
        **hist_build_unsigned, "identity": _sha(_canonical(hist_build_unsigned)),
    })
    hist_build = json.loads(hist_build_raw)
    _write(repo, f"{experiment_rel}/build-record.json", hist_build_raw)

    ordinary_roles = {
        "worker": {"sha256": _sha(b"synthetic ordinary worker\n")},
        "dll": {"sha256": _sha(b"synthetic ordinary dll\n")},
        "cdb": {"sha256": _sha(b"synthetic ordinary cdb\n")},
        "script_manifest": {"sha256": _sha(b"synthetic ordinary scripts\n")},
    }
    ordinary = {"consistent": True, "roles": ordinary_roles}
    ordinary["identity"] = _sha(_canonical(ordinary))
    identity_unsigned = {
        "schema_version": 1, "kind": "workspace_identity", "source": hist_source,
        "consistent": True, "build_provenance": "unverified",
        "reproducible_build_proven": False,
        "runtimes": {"ordinary": ordinary},
    }
    identity_raw = _canonical({
        **identity_unsigned, "identity": _sha(_canonical(identity_unsigned)),
    })
    _write(repo, f"{experiment_rel}/identity.json", identity_raw)
    started_at = 1_798_000_000
    window_raw = _canonical({
        "schema_version": 1, "kind": "tenki_placement_probe_window_start",
        "scope": "tenki-placement-probe-v1", "limit": 6,
        "wall_seconds": 7200, "started_at": started_at,
    })
    _write(repo, f"{experiment_rel}/window-start.json", window_raw)

    request = {
        "protocol_version": 2,
        "engine": {"worker_path": str((experiment / "native-artifacts/ygo-engine-worker.exe").absolute())},
        "decisions": [{"prompt_id": 7, "player": 0, "choice": {"kind": "command", "command": 5, "index": 0}}],
    }
    request_raw = _canonical(request)
    request_hash = _sha(request_raw)
    transition_raw = _synthetic_transition_record(
        repo, prompt_baseline_sources, prompt_baseline_data, history_pair,
    )
    _write(repo, f"{experiment_rel}/baseline-transition.json", transition_raw)
    prompt_baseline_sources = replace(
        prompt_baseline_sources,
        files=(
            *prompt_baseline_sources.files,
            _file_pin(repo, f"{experiment_rel}/baseline-transition.json", "baseline_transition"),
        ),
    )
    input_sha256 = {
        "baseline_transition": _sha(transition_raw),
        "build_record": _sha(hist_build_raw),
        "identity": _sha(identity_raw),
        "window_start": _sha(window_raw),
    }
    manifest_unsigned = {
        "schema_version": 1,
        "kind": "native_tenki_placement_manifest",
        "scope": "tenki-placement-probe-v1",
        "source_identity": history_pair.native_source_identity,
        "build_identity": hist_build["identity"],
        "runner_sha256": hist_artifacts["runner"],
        "worker_sha256": hist_artifacts["worker"],
        "old_consumed": 26,
        "old_stage1_sha256": CORRECT_STAGE1_LITERAL,
        "old_stage2_request_sha256": OLD_STAGE2_REQUEST_SHA256,
        "old_stage2_sha256": OLD_STAGE2_SHA256,
        "stage1_request_sha256": request_hash,
        "started_at": started_at,
        "input_sha256": input_sha256,
    }
    from ygo_data.identity import canonical as _identity_canonical, digest as _identity_digest
    context = _identity_digest(_identity_canonical(manifest_unsigned))
    manifest_raw = _canonical({**manifest_unsigned, "context": context})
    invocation = {
        "context": context, "stage": 1, "started_at": started_at,
        "request": request, "expected_identity": ordinary,
        "ledger": str((research / "calls.jsonl").absolute()),
        "output": str((research / "stage-1.json").absolute()),
    }
    invocation_raw = _canonical(invocation)
    seal_raw = _canonical({
        "schema_version": 1, "kind": "tenki_placement_stage_input_seal",
        "context": context, "stage": 1, "input_sha256": _sha(invocation_raw),
    })
    prepared_raw = _canonical({
        "kind": "native_tenki_placement_prepared", "context": context,
        "native_calls": 0, "first_stage_request_sha256": request_hash,
    })
    summary_raw = _canonical({
        "kind": "native_tenki_placement_summary", "diagnostic": "runner_failed",
        "stages": [], "new_consumed": 0, "ledger": {"unknown": 0},
    })
    for name, raw in (
        ("manifest.json", manifest_raw), ("stage-1-request.json", request_raw),
        ("stage-1-input.json", invocation_raw), ("stage-1-input-seal.json", seal_raw),
        ("prepared.json", prepared_raw), ("summary.json", summary_raw),
    ):
        (research / name).write_bytes(raw)

    details = {
        "kind": "test_exclusion_details",
        "python": {"skipped": 7, "items": [f"synthetic skipped {i}" for i in range(7)]},
        "rust_workspace_serial": {"ignored": 36, "items": [f"synthetic ignored {i}" for i in range(36)]},
        "adapter_examples": {"ignored": 0, "items": []},
        "native_asset_opt_in": "not_run", "doctor": "not_run", "48_hand_evaluation": "not_run",
    }
    details_raw = _canonical(details)
    _write(repo, f"{experiment_rel}/verification/test-exclusion-details.json", details_raw)
    ledger_raw = (repo / ledger_pins[-1].relative_path).read_bytes()
    delivery_experiment = {
        "kind": "tenki_placement_final_delivery",
        "status": "offline_delivery_complete_native_probe_failed_before_charge",
        "baseline_transition": {"version": "v2", "sha256": _sha(transition_raw)},
        "native_result": {
            "new_consumed": 0, "unknown_consumption": 0, "cumulative_consumed": 26,
            "ledger_sha256": _sha(ledger_raw), "summary_sha256": _sha(summary_raw),
        },
        "final_source": {
            "identity": history_pair.final_source_identity,
            "file_count": len(history_pair.final_files),
        },
    }
    delivery_exp_raw = _canonical(delivery_experiment)
    _write(repo, f"{experiment_rel}/final-build/delivery.json", delivery_exp_raw)
    addendum = {
        "kind": "tenki_placement_delivery_addendum",
        "base_delivery": "delivery.json",
        "base_delivery_sha256": _sha(delivery_exp_raw),
        "supplement": {
            "sha256": _sha(details_raw), "python_skipped": 7,
            "rust_ignored": 36, "examples_ignored": 0,
        },
    }
    addendum_raw = _canonical(addendum)
    _write(repo, f"{experiment_rel}/final-build/delivery-addendum.json", addendum_raw)

    final_source = {
        "head": HEAD,
        "files": {name: _sha(raw) for name, raw in history_pair.final_files.items()},
        "identity": history_pair.final_source_identity,
    }
    final_build_unsigned = {
        "schema_version": 1, "kind": "build_record", "status": "recorded",
        "source_before": final_source, "source_after": final_source,
        "reproducible_build_proven": False, "artifacts": hist_artifacts,
    }
    final_build_raw = _canonical({
        **final_build_unsigned, "identity": _sha(_canonical(final_build_unsigned)),
    })
    _write(repo, f"{experiment_rel}/final-build/final-build-record.json", final_build_raw)
    _write(repo, f"{experiment_rel}/final-build/native-artifacts/tenki-placement-probe.exe", hist_runner)
    _write(repo, f"{experiment_rel}/final-build/native-artifacts/ygo-engine-worker.exe", hist_worker)
    _write(repo, f"{experiment_rel}/final-build/native-artifacts/ygo-cli.exe", hist_cli)
    delivery_experiment["final_build"] = {
        "record_identity": json.loads(final_build_raw)["identity"],
        "source_before_identity": history_pair.final_source_identity,
        "source_after_identity": history_pair.final_source_identity,
    }
    delivery_experiment["native_result"]["ledger_sha256"] = _sha(ledger_raw)
    delivery_exp_raw = _canonical(delivery_experiment)
    _write(repo, f"{experiment_rel}/final-build/delivery.json", delivery_exp_raw)
    addendum["base_delivery_sha256"] = _sha(delivery_exp_raw)
    addendum_raw = _canonical(addendum)
    _write(repo, f"{experiment_rel}/final-build/delivery-addendum.json", addendum_raw)

    # Rewrite signed diagnostics documents with an explicit binding to the
    # complete synthetic placement delivery; this remains generated evidence.
    acceptance_unsigned["preflight_audit_source_identity"] = pair.native_source_identity
    acceptance_unsigned["identity"] = _sha(_canonical({k: v for k, v in acceptance_unsigned.items() if k != "identity"}))
    acceptance_raw = _canonical(acceptance_unsigned)
    _write(repo, f"{diagnostics_rel}/final-build/acceptance.json", acceptance_raw)

    # All source pins are derived only after their generated bytes are final.
    # Include each old placement document that the actual verifier reads.
    placement_files = (
        _file_pin(repo, f"{diagnostics_rel}/final-build/acceptance.json", "diagnostics_acceptance"),
        _file_pin(repo, f"{diagnostics_rel}/final-build/delivery.json", "diagnostics_delivery"),
        _file_pin(repo, f"{diagnostics_rel}/final-build/build-record.json", "diagnostics_build"),
        _file_pin(repo, f"{diagnostics_rel}/preflight-report.json", "diagnostics_preflight"),
        *(
            _file_pin(repo, f"{experiment_rel}/{relative}", role)
            for role, relative in (
                ("placement_experiment_delivery", "final-build/delivery.json"),
                ("placement_addendum", "final-build/delivery-addendum.json"),
                ("placement_details", "verification/test-exclusion-details.json"),
                ("placement_manifest", "research/manifest.json"),
                ("placement_prepared", "research/prepared.json"),
                ("placement_request", "research/stage-1-request.json"),
                ("placement_input", "research/stage-1-input.json"),
                ("placement_seal", "research/stage-1-input-seal.json"),
                ("placement_summary", "research/summary.json"),
                ("placement_ledger", "research/calls.jsonl"),
                ("placement_identity", "identity.json"),
                ("placement_native_build", "build-record.json"),
                ("placement_native_archive_file", "source-native.zip"),
                ("placement_native_list_file", "source-native-file-list.json"),
                ("placement_final_archive_file", "final-build/source-final.zip"),
                ("placement_final_list_file", "final-build/source-final-file-list.json"),
                ("placement_final_build", "final-build/final-build-record.json"),
                ("placement_transition", "baseline-transition.json"),
            )
        ),
        *ledger_pins,
    )
    placement_archives = (
        _PinnedArchive(
            "placement_native_archive",
            f"{diagnostics_rel}/verification/source-audit-strict-dedupe/source-native.zip",
            f"{diagnostics_rel}/verification/source-audit-strict-dedupe/source-native-file-list.json",
            _sha(precheck_archive.read_bytes()), _sha(precheck_list.read_bytes()),
            pair.native_source_identity, len(pair.native_files), HEAD,
        ),
        _PinnedArchive(
            "placement_final_archive",
            f"{diagnostics_rel}/final-build/source-native.zip",
            f"{diagnostics_rel}/final-build/source-native-file-list.json",
            _sha(final_archive.read_bytes()), _sha(final_list.read_bytes()),
            pair.final_source_identity, len(pair.final_files), HEAD,
        ),
        _PinnedArchive(
            "placement_history_archive",
            f"{experiment_rel}/source-native.zip",
            f"{experiment_rel}/source-native-file-list.json",
            history_pair.native_archive_sha256, history_pair.native_file_list_sha256,
            history_pair.native_source_identity, len(history_pair.native_files), HEAD,
        ),
    )
    placement_children = (
        _SourceDescription(
            role="historical_ledgers", files=ledger_pins,
            dataset_counts=(
                ("ledger_count", 7), ("consumed", 26),
                *(
                    (f"ledger_{contract[0]}_consumed", contract[2])
                    for contract in _SYNTHETIC_LEDGER_CONTRACTS[:7]
                ),
            ),
            baseline_relative="data/runtime",
        ),
        prompt_baseline_sources,
    )
    return _SourceDescription(
        role="placement_confirmation",
        files=placement_files,
        archives=placement_archives,
        semantic_hashes=(
            ("placement_context", context),
            ("placement_historical_build", hist_build["identity"]),
            ("placement_historical_runner", hist_artifacts["runner"]),
        ),
        archive_differences=(
            ("placement_confirmation", tuple(sorted(changes))),
        ),
        dataset_counts=(
            ("historical_consumed", 26), ("ledger_count", 7),
            ("placement_python_skipped", 7),
            ("placement_rust_ignored", 36),
            ("placement_examples_ignored", 0),
        ),
        baseline_relative=diagnostics_rel,
        children=placement_children,
    )


def _synthetic_static_preparation(repo: Path) -> _SourceDescription:
    """Create a generated, self-consistent static Curry preparation source."""
    prep_root = repo / "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final"
    prep_root.mkdir(parents=True)
    cases_path = repo / curry.FROZEN_CASES_PATH
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    operations_path = repo / "data/tmp/ocgcore-source/operations.cpp"
    operations_path.parent.mkdir(parents=True, exist_ok=True)

    main = [85_138_716, *range(10_001, 10_040)]
    extra = [20_001, 20_002, 20_003]
    hand = [85_138_716, 2_964_201, 2_964_201, 2_964_201, 2_971_090]
    rabbit_case = {
        "case_id": "rabbit", "deck": {"main": main, "extra": extra, "side": []},
        "opening_hand": hand, "seed": 1,
        "information": {"opponent_resources": {"hand": [], "main": list(main)}},
    }
    base_request = {
        "protocol_version": 2,
        "probe_only": False,
        "engine": {"worker_path": "synthetic/native-artifacts/ygo-engine-worker.exe"},
        "deck": rabbit_case["deck"], "opening_hand": hand, "seed": 1,
        "decisions": [], "banlist_path": "data/banlist.conf",
        "versions": {
            "engine_sha256": hashlib.sha256(b"synthetic dll").hexdigest(),
            "cdb_sha256": hashlib.sha256(b"synthetic cdb").hexdigest(),
            "scripts_sha256": hashlib.sha256(b"synthetic script manifest").hexdigest(),
        },
    }
    # Test-owned substitution: do not use the production derivation function to
    # generate the expected candidate.
    candidate_case = json.loads(json.dumps(rabbit_case))
    candidate_case["case_id"] = "prompt-14-curry-v1"
    candidate_case["deck"]["main"] = [
        58_074_572 if card == 85_138_716 else card for card in main
    ]
    candidate_case["opening_hand"] = [
        58_074_572 if card == 85_138_716 else card for card in hand
    ]
    candidate_case["information"]["opponent_resources"]["main"] = list(
        candidate_case["deck"]["main"]
    )
    base_hash = _sha(_case_encode(base_request))
    candidate_hash = _sha(_case_encode(candidate_case))
    expected_target = {
        "opcode": 14,
        "descriptions": [60_895_602_409_472, 60_895_602_409_473],
        "player": 0,
        "responses": [
            {"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]},
            {"choice": {"kind": "option", "index": 1}, "bytes": [1, 0, 0, 0]},
        ],
    }
    candidate = {
        "case": candidate_case,
        "request_derivation": {
            "base_request_sha256": base_hash, "case_sha256": candidate_hash,
            "hash_encoding": "sorted-utf8-indent2-newline-v1",
            "replace_card": {"from": 85_138_716, "to": 58_074_572},
            "fixed_changes": {"seed": 1},
        },
        "target": {"card_id": 58_074_572, "name": "curry", "opcode": 14},
        "expected_target": expected_target,
        "selector": {"card_id": 58_074_572, "command": 5, "opcode": 11,
                     "player": 0, "unique": True},
        "execution_ready": False,
    }
    tenki_case = json.loads(json.dumps(rabbit_case))
    tenki_case["case_id"] = "prompt-13-tenki-v1"
    tenki_case["deck"]["main"] = [
        57_103_969 if card == 85_138_716 else card for card in main
    ]
    tenki_case["opening_hand"] = [
        57_103_969 if card == 85_138_716 else card for card in hand
    ]
    tenki_case["information"]["opponent_resources"]["main"] = list(
        tenki_case["deck"]["main"]
    )
    synthetic_banlist = _canonical({"schema_version": 1, "kind": "synthetic_banlist"})
    _write(repo, "data/runtime/banlist.json", synthetic_banlist)
    tenki_case["rules"] = {
        "region": "OCG",
        "banlist_version": "synthetic-banlist-v1",
        "banlist_sha256": _sha(synthetic_banlist),
    }
    tenki_hash = _sha(_case_encode(tenki_case))
    tenki_candidate = {
        "case": tenki_case,
        "request_derivation": {
            "base_request_sha256": base_hash, "case_sha256": tenki_hash,
            "hash_encoding": "sorted-utf8-indent2-newline-v1",
            "replace_card": {"from": 85_138_716, "to": 57_103_969},
            "fixed_changes": {"seed": 1},
        },
        "target": {"opcode": 13, "card_id": 57_103_969, "name": "tenki"},
        "expected_target": {
            "opcode": 13, "player": 0, "description": 59_877_851_398_144,
            "responses": [
                {"choice": {"kind": "yes_no", "yes": False}, "bytes": [0, 0, 0, 0]},
                {"choice": {"kind": "yes_no", "yes": True}, "bytes": [1, 0, 0, 0]},
            ],
        },
        "selector": {"card_id": 57_103_969, "command": 5, "opcode": 11,
                     "player": 0, "unique": True},
        "execution_ready": False,
    }
    frozen_raw = _canonical({"cases": [
        {"case": rabbit_case, "request": base_request, "banlist_path": "data/banlist.conf"},
    ]})
    frozen_hash = _sha(frozen_raw)
    preparation_raw = _canonical({"candidates": [candidate, tenki_candidate]})
    raw_by_role = {
        "preparation": (curry.PREPARATION_PATH, preparation_raw),
        "preparation_report": (curry.PREPARATION_REPORT_PATH, _canonical({"candidates": [
            {"case_id": "prompt-14-curry-v1", "status": "static_prepared", "execution_ready": False},
            {"case_id": "prompt-13-tenki-v1", "status": "static_prepared", "execution_ready": False},
        ], "input_sha256": {"frozen_cases": frozen_hash}})),
        "preparation_acceptance": (curry.PREPARATION_ACCEPTANCE_PATH, _canonical({"static_candidates": [
            {"case_id": "prompt-14-curry-v1", "case_sha256": candidate_hash,
             "execution_ready": False, "formal_release_status": "unknown"},
            {"case_id": "prompt-13-tenki-v1", "case_sha256": tenki_hash,
             "execution_ready": False, "formal_release_status": "unknown"},
        ]})),
        "operations_source": (Path("data/tmp/ocgcore-source/operations.cpp"),
                              b"// synthetic static-only operations source\n"),
        "adapter_codec": (Path("crates/ygo-engine-adapter/src/codec.rs"),
                          SYNTHETIC_CODEC_CURRENT),
        "frozen_cases": (curry.FROZEN_CASES_PATH, frozen_raw),
    }
    files = []
    for role, (relative, raw) in raw_by_role.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        files.append(_PinnedFile(role, relative.as_posix(), _sha(raw)))
    return _SourceDescription(
        role="static_preparation", files=tuple(files),
        semantic_hashes=(("base_request", base_hash), ("candidate_case", candidate_hash)),
        baseline_relative="data/runtime/p1-prompt-probes-offline-2026-10-21",
    )


def _populate_confirmation_inputs(
    repo: Path, baseline: Path, archive_pair: Any,
) -> None:
    """Write the synthetic confirmation manifest and all twenty-one inputs."""
    preparation = json.loads((repo / curry.PREPARATION_PATH).read_bytes())
    candidate_case = preparation["candidates"][0]["case"]
    frozen_cases = json.loads((repo / curry.FROZEN_CASES_PATH).read_bytes())
    rabbit_entry = frozen_cases["cases"][0]
    base_request = rabbit_entry["request"]
    request = json.loads(json.dumps(base_request))
    request["deck"] = candidate_case["deck"]
    request["opening_hand"] = candidate_case["opening_hand"]
    request["seed"] = candidate_case["seed"]
    request["decisions"] = []

    worker = b"synthetic worker binary\n"
    dll = b"synthetic core dll\n"
    cdb = b"synthetic catalog\n"
    script_manifest = b"synthetic script manifest\n"
    cli = b"synthetic cli binary\n"
    artifacts = {"runner": b"synthetic runner binary\n", "worker": worker, "cli": cli}
    raw_files: dict[str, bytes] = {
        "native-artifacts/curry-option-confirmation.exe": artifacts["runner"],
        "native-artifacts/ygo-engine-worker.exe": worker,
        "native-artifacts/ygo-cli.exe": cli,
        "data/banlist.conf": b"# synthetic banlist\n",
        "crates/ygo-engine-adapter/src/codec.rs": SYNTHETIC_CODEC_CURRENT,
        "data/runtime/p1-curry-option-validation-native-2026-10-23/ordinary-candidate.toml": b'worker_path = "synthetic/native-artifacts/ygo-engine-worker.exe"\n',
        "data/runtime/p1-curry-option-validation-native-2026-10-23/tournament-candidate.toml": b'worker_path = "synthetic/native-artifacts/ygo-engine-worker.exe"\n',
    }
    for relative, raw in raw_files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        if relative.endswith("ordinary-candidate.toml") or relative.endswith("tournament-candidate.toml"):
            (baseline / Path(relative).name).write_bytes(raw)
    (baseline / "native-artifacts").mkdir(parents=True, exist_ok=True)
    for name, raw in artifacts.items():
        (baseline / "native-artifacts" / {
            "runner": "curry-option-confirmation.exe",
            "worker": "ygo-engine-worker.exe",
            "cli": "ygo-cli.exe",
        }[name]).write_bytes(raw)

    ordinary = {
        "consistent": True,
        "roles": {
            "worker": {"sha256": _sha(worker)},
            "dll": {"sha256": _sha(dll)},
            "cdb": {"sha256": _sha(cdb)},
            "script_manifest": {"sha256": _sha(script_manifest)},
        },
    }
    ordinary["identity"] = _sha(_canonical(ordinary))
    tournament = json.loads(json.dumps(ordinary))
    asset_sha = {
        "engine_sha256": _sha(dll),
        "cdb_sha256": _sha(cdb),
        "scripts_sha256": _sha(script_manifest),
    }
    request["versions"] = asset_sha
    source_files = {name: _sha(content) for name, content in archive_pair.native_files.items()}
    source = {"head": HEAD, "files": source_files, "identity": archive_pair.native_source_identity}

    build_unsigned = {
        "schema_version": 1,
        "kind": "build_record",
        "status": "recorded",
        "source_before": source,
        "source_after": source,
        "reproducible_build_proven": False,
        "artifacts": {role: _sha(raw) for role, raw in artifacts.items()},
    }
    build_record = {**build_unsigned, "identity": _sha(_canonical(build_unsigned))}
    build_raw = _canonical(build_record)
    (baseline / "build-record.json").write_bytes(build_raw)
    (baseline / "final-build" / "build-record.json").write_bytes(build_raw)

    identity_unsigned = {
        "schema_version": 1,
        "kind": "workspace_identity",
        "source": source,
        "consistent": True,
        "build_provenance": "unverified",
        "reproducible_build_proven": False,
        "cli_sha256": _sha(cli),
        "runtimes": {"ordinary": ordinary, "tournament": tournament},
    }
    identity = {**identity_unsigned, "identity": _sha(_canonical(identity_unsigned))}
    (baseline / "identity.json").write_bytes(_canonical(identity))
    started_at = 1_800_000_000
    window = {
        "schema_version": 1,
        "kind": "curry_option_confirmation_window_start",
        "scope": curry.CONFIRMATION_SCOPE.scope,
        "limit": 7,
        "wall_seconds": 7200,
        "started_at": started_at,
    }
    (baseline / "window-start.json").write_bytes(_canonical(window))

    # Files used by the 21-role input map already exist in their fixed roots.
    input_paths = {
        "runner": baseline / "native-artifacts/curry-option-confirmation.exe",
        "worker": baseline / "native-artifacts/ygo-engine-worker.exe",
        "build_record": baseline / "build-record.json",
        "identity": baseline / "identity.json",
        "window_start": baseline / "window-start.json",
        "cli": baseline / "native-artifacts/ygo-cli.exe",
        "source_archive": baseline / "source-native.zip",
        "source_file_list": baseline / "source-native-file-list.json",
        "ordinary_config": repo / "data/runtime/p1-curry-option-validation-native-2026-10-23/ordinary-candidate.toml",
        "tournament_config": repo / "data/runtime/p1-curry-option-validation-native-2026-10-23/tournament-candidate.toml",
    }
    # The baseline audit/delivery sources are fixed-role files. Their fixture
    # hashes are generated and later pinned by the nested description.
    from ygo_eval.native_curry_option_validation import _curry_manifest_files

    banlist = repo / "data/banlist.conf"
    preparation_result = {
        "base_request": base_request,
        "candidate_case": candidate_case,
    }
    manifest_files = _curry_manifest_files(
        repo, baseline, input_paths, preparation_result, banlist,
        curry.CONFIRMATION_SCOPE,
    )
    input_hashes = {}
    for role, path in manifest_files.items():
        raw = path.read_bytes()
        input_hashes[role] = _sha(raw)
    input_hashes["base_request"] = _sha(_case_encode(base_request))
    input_hashes["candidate_case"] = _sha(_case_encode(candidate_case))
    # The two role-specific asset paths are represented by hashes in runtime
    # metadata; binary bytes are synthetic inert evidence only.
    manifest = {
        "schema_version": 1,
        "kind": "native_curry_option_confirmation_manifest",
        "scope": curry.CONFIRMATION_SCOPE.scope,
        "batch_kind": curry.CONFIRMATION_SCOPE.batch_kind,
        "started_at": started_at,
        "limit": 7,
        "planned_calls": 7,
        "wall_seconds": 7200,
        "old_consumed": 32,
        "baseline_delivery_sha256": curry.CONFIRMATION_SCOPE.delivery_sha256,
        "baseline_audit_sha256": curry.CONFIRMATION_SCOPE.baseline_audit_sha256,
        "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
        "historical_source_transition": curry.HISTORICAL_SOURCE_TRANSITION,
        "request": request,
        "stage1_request_sha256": _sha(_canonical(request)),
        "input_sha256": input_hashes,
        "source": source,
        "build": {
            "identity": build_record["identity"],
            "record_sha256": _sha(build_raw),
            "artifacts": build_unsigned["artifacts"],
        },
        "source_archive": {
            "sha256": archive_pair.native_archive_sha256,
            "file_list_sha256": archive_pair.native_file_list_sha256,
            "file_count": len(source_files),
        },
        "assets": {"ordinary": ordinary, "tournament": tournament},
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    manifest["context"] = _sha(_canonical(manifest))
    manifest_raw = _canonical(manifest)
    research = baseline / "research"
    (research / "manifest.json").write_bytes(manifest_raw)
    request_raw = _canonical(request)
    (research / "stage-1-request.json").write_bytes(request_raw)
    input_doc = {
        "schema_version": 1,
        "kind": "native_curry_option_confirmation_stage_input",
        "scope": curry.CONFIRMATION_SCOPE.scope,
        "context": manifest["context"],
        "stage": 1,
        "batch_kind": curry.CONFIRMATION_SCOPE.batch_kind,
        "request": request,
        "expected_identity": ordinary,
        "started_at": started_at,
        "ledger": "research/calls.jsonl",
    }
    input_raw = _canonical(input_doc)
    (research / "stage-1-input.json").write_bytes(input_raw)
    seal = {
        "schema_version": 1,
        "kind": curry.CONFIRMATION_SCOPE.input_seal_kind,
        "context": manifest["context"],
        "stage": 1,
        "input_sha256": _sha(input_raw),
    }
    (research / "stage-1-input-seal.json").write_bytes(_canonical(seal))
    prepared = {
        "schema_version": 1,
        "kind": "native_curry_option_confirmation_prepared",
        "scope": curry.CONFIRMATION_SCOPE.scope,
        "context": manifest["context"],
        "prepared": True,
        "execution_ready": True,
        "native_calls": 0,
        "planned_calls": 7,
        "manifest_sha256": _sha(manifest_raw),
        "stage1_request_sha256": _sha(request_raw),
        "stage1_input_sha256": _sha(input_raw),
        "preflight_diagnostic_sha256": _sha(b"synthetic preflight"),
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    (research / "prepared.json").write_bytes(_canonical(prepared))


def build_synthetic_recovery_tree(root: Path) -> SyntheticRecoveryTree:
    """Build a minimal synthetic root and reach the first deep verifier gate.

    The public test intentionally does not mock the verifier chain. This first
    version supplies the acceptance/inventory/archive layer; follow-up work can
    add subsequent authenticated layers based on the first observed gate.
    """
    repo = Path(root) / "repo"
    repo.mkdir(parents=True, exist_ok=False)
    (repo / ".gitignore").write_text("data/runtime\ntarget/\n", encoding="utf-8")
    baseline = repo / BASELINE
    research = baseline / "research"
    final_build = baseline / "final-build"
    research.mkdir(parents=True)
    final_build.mkdir(parents=True)
    static_preparation_sources = _synthetic_static_preparation(repo)
    asset_audit_sources = _synthetic_asset_audit(repo)

    # Source checks look for historical text, not for executable material.
    # These files are inert synthetic UTF-8 members.
    old_code = "\n".join((
        "for role, path in frozen_paths.items():",
        "if _sha(safe_path(path).read_bytes()) != manifest[\"input_sha256\"].get(role):",
        'hashes["base_request"] = _sha(_case_encode(preparation["base_request"]))',
        'hashes["candidate_case"] = _sha(_case_encode(preparation["candidate_case"]))',
    )).encode("utf-8")
    old_research = "\n".join((
        "if args.command == 'native-curry-option-confirmation':",
        "native-curry-option-confirmation refused: frozen input, build, ledger, or output check failed",
        "return 2",
        "if args.command == 'audit-tenki-placement-preflight':",
    )).encode("utf-8")
    native_files = {
        audit.NATIVE_SOURCE_PATH: old_code,
        audit.RESEARCH_SOURCE_PATH: old_research,
        "crates/ygo-engine-adapter/src/codec.rs": SYNTHETIC_CODEC_CURRENT,
        "synthetic/placeholder.txt": b"synthetic placeholder\n",
        "TASKS.md": b"old synthetic task state\n",
        "docs/TESTING.md": b"old synthetic test state\n",
        "docs/superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md": b"old handoff\n",
    }
    archive_differences = {
        "TASKS.md": b"new synthetic task state\n",
        "docs/TESTING.md": b"new synthetic test state\n",
        "docs/superpowers/plans/2026-10-24-curry-option-confirmation-handoff.md": b"new handoff\n",
    }
    archive_pair = build_synthetic_archive_pair(
        baseline,
        archive_filenames=("source-native.zip", "unused-final.zip"),
        file_list_filenames=("source-native-file-list.json", "unused-final-list.json"),
        native_files=native_files,
        differences=archive_differences,
        source_head=HEAD,
        native_file_count=7,
        final_file_count=7,
    )
    # Move the second archive into the final-build path without altering bytes.
    (final_build / "source-native.zip").write_bytes(archive_pair.final_archive.read_bytes())
    (final_build / "source-native-file-list.json").write_bytes(archive_pair.final_file_list.read_bytes())
    _populate_confirmation_inputs(repo, baseline, archive_pair)

    (research / "normal-attempt-observation.json").write_bytes(_canonical({
        "kind": "curry_option_confirmation_normal_attempt_observation",
        "scope": "curry-option-confirmation-v1",
        "exit_code": 1,
        "worker_request_consumption": None,
        "authenticated_ledger_present": False,
        "normal_process_diagnostic_present": False,
        "raw_process_output_saved": False,
    }))
    # A one-byte inventory is sufficient to exercise the verifier's exact
    # accounting logic while keeping the synthetic tree small.
    payload = b"x"
    evidence = baseline / "research" / "synthetic-evidence.bin"
    evidence.write_bytes(payload)
    inventory = {
        "schema_version": 1,
        "kind": "curry_option_confirmation_evidence_inventory",
        "scope": "curry-option-confirmation-v1",
        "measured_root": BASELINE,
        "entry_count": 1,
        "entries": [{"path": "research/synthetic-evidence.bin", "sha256": _sha(payload), "bytes": 1}],
        "accessible_file_bytes": 1,
        "complete_for_measured_root": True,
        "access_errors": [],
        "excluded_from_measurement": ["acceptance.json", "evidence-inventory.json", "final-build/delivery.json"],
    }
    inventory_raw = _canonical(inventory)
    (baseline / "evidence-inventory.json").write_bytes(inventory_raw)
    inventory_hash = _sha(inventory_raw)
    qualification = {
        "complete_action_coverage": False,
        "global_optimality": False,
        "issuance_evidence": "unknown",
        "native_probability_verified": False,
        "proof_ready": False,
        "successful": False,
    }
    accounting = {
        "cumulative_consumed": None,
        "historical_consumed": 32,
        "historical_unknown": 0,
        "new_consumed": None,
        "new_unknown": None,
        "status": "unknown_without_authenticated_ledger",
    }
    acceptance = {
        "schema_version": 1,
        "kind": "native_curry_option_confirmation_acceptance",
        "scope": "curry-option-confirmation-v1",
        "status": "partial",
        "accounting": accounting,
        "qualification": qualification,
        "evidence_inventory": {
            "path": "evidence-inventory.json", "sha256": inventory_hash,
            "covered_entries": 1, "covered_bytes": 1,
        },
    }
    (baseline / "acceptance.json").write_bytes(_canonical(acceptance))
    delivery = {
        "schema_version": 1,
        "kind": "native_curry_option_confirmation_delivery",
        "status": "partial_stopped_before_authenticated_stage",
        "accounting": accounting,
        "qualification": qualification,
        "scope": {"id": "curry-option-confirmation-v1", "request_limit": 7, "wall_seconds_limit": 7200},
        "prepared": {"prepared": True, "execution_ready": True, "native_calls": 0},
        "verification": {"valid": False},
        "normal_attempt": {
            "exit_code": 1, "worker_request_consumption": None,
            "authenticated_ledger_present": False,
        },
        "evidence_inventory": {"sha256": inventory_hash},
        "source": {
            "identity": archive_pair.final_source_identity,
            "file_count": 7,
            "archive": {"sha256": archive_pair.final_archive_sha256},
            "file_list": {"sha256": archive_pair.final_file_list_sha256},
        },
    }
    delivery_raw = _canonical(delivery)
    (final_build / "delivery.json").write_bytes(delivery_raw)

    base_rel = BASELINE
    source_files = (
        _PinnedFile("acceptance", f"{base_rel}/acceptance.json", _sha((baseline / "acceptance.json").read_bytes())),
        _PinnedFile("delivery", f"{base_rel}/final-build/delivery.json", _sha(delivery_raw)),
        _PinnedFile("evidence_inventory", f"{base_rel}/evidence-inventory.json", inventory_hash),
        _PinnedFile("native_source_archive", f"{base_rel}/source-native.zip", archive_pair.native_archive_sha256),
        _PinnedFile("native_source_file_list", f"{base_rel}/source-native-file-list.json", archive_pair.native_file_list_sha256),
        _PinnedFile("final_source_archive", f"{base_rel}/final-build/source-native.zip", _sha((final_build / "source-native.zip").read_bytes())),
        _PinnedFile("final_source_file_list", f"{base_rel}/final-build/source-native-file-list.json", _sha((final_build / "source-native-file-list.json").read_bytes())),
    )
    sources = _SourceDescription(
        role="confirmation",
        files=source_files,
        archives=(
            _PinnedArchive(
                "confirmation_native_archive", f"{base_rel}/source-native.zip",
                f"{base_rel}/source-native-file-list.json", archive_pair.native_archive_sha256,
                archive_pair.native_file_list_sha256, archive_pair.native_source_identity, 7, HEAD,
            ),
            _PinnedArchive(
                "confirmation_final_archive", f"{base_rel}/final-build/source-native.zip",
                f"{base_rel}/final-build/source-native-file-list.json",
                _sha((final_build / "source-native.zip").read_bytes()),
                _sha((final_build / "source-native-file-list.json").read_bytes()),
                archive_pair.final_source_identity, 7, HEAD,
            ),
        ),
        archive_differences=(("confirmation", tuple(sorted(archive_differences))),),
        dataset_counts=(("evidence_inventory_entries", 1), ("evidence_inventory_bytes", 1)),
        children=(
            static_preparation_sources,
            asset_audit_sources,
        ),
        baseline_relative=BASELINE,
        output_relative_v1="data/runtime/p1-curry-recovery-e2e-v1",
        output_relative_v2=OUTPUT_V2,
    )
    return SyntheticRecoveryTree(repo, baseline, sources)
