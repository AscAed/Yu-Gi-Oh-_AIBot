"""Synthetic V3 reservation source tree for public CLI tests.

The builder composes the existing V1/V2 recovery fixture, then reshapes only
test-owned bytes to match the frozen V3 input layout. It never reads runtime
evidence from the user's checkout and every generated executable is inert.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile
from types import SimpleNamespace
from typing import Any

from ygo_eval import curry_consumption_reservation as reservation
from tests.support.curry_reservation_e2e import (
    _canonical,
    _pretty,
    _sha,
    _write,
    build_synthetic_reservation_tree,
    build_synthetic_v1_failed_attempt,
    _forbid_native_activity,
)


def _source_zip_and_list(
    repo: Path,
    archive_relative: Path,
    list_relative: Path,
    *,
    files: dict[str, bytes],
    pin: tuple[Path, str, Path, str, str, int, str, str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Write a reproducible inert archive/list pair matching one fixed pin shape."""
    archive_rel, _archive_sha, list_rel, _list_sha, list_kind, count, head, _identity, row_format = pin
    if len(files) != count:
        raise AssertionError(f"synthetic_archive_count_mismatch:{len(files)}:{count}")
    hashes = {name: _sha(raw) for name, raw in sorted(files.items())}
    identity = _sha(_canonical({"head": head, "files": hashes}))
    if row_format == "files":
        listing = {
            "schema_version": 1,
            "kind": list_kind,
            "file_count": count,
            "files": [{"path": name, "sha256": hashes[name]} for name in sorted(hashes)],
            "head": head,
            "missing_files": [],
            "source_identity": identity,
        }
    else:
        listing = {
            "schema_version": 1,
            "kind": list_kind,
            "file_count": count,
            "entries": [
                {"path": name, "sha256": hashes[name], "state": "present"}
                for name in sorted(hashes)
            ],
            "head": head,
            "source_identity": identity,
        }
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, raw)
    archive_raw = archive_buffer.getvalue()
    list_raw = _pretty(listing)
    _write(repo, archive_rel, archive_raw)
    _write(repo, list_rel, list_raw)
    return {
        "archive_path": archive_rel.as_posix(),
        "archive_sha256": _sha(archive_raw),
        "file_list_path": list_rel.as_posix(),
        "file_list_sha256": _sha(list_raw),
        "file_count": count,
        "head": head,
        "source_identity": identity,
    }, hashes


def _build_v3_recovery_archives(repo: Path, spec) -> tuple[tuple, dict[str, Any]]:
    corrected_pin, audit_pin, final_pin = spec.recovery_archives
    head = corrected_pin[6]
    corrected_files = {
        "python/ygo_eval/curry_consumption_reservation.py": b'ACCEPTANCE_SHA256 = "corrected-constant-placeholder"\n',
        **{f"synthetic/corrected-{index:04d}.txt": b"inert corrected source\n" for index in range(533)},
    }
    corrected_meta, _ = _source_zip_and_list(
        repo, corrected_pin[0], corrected_pin[2], files=corrected_files, pin=corrected_pin,
    )

    changed_docs = (
        "TASKS.md",
        "docs/INDEX.md",
        "docs/TESTING.md",
    )
    added_doc = "docs/superpowers/plans/2026-10-25-curry-consumption-reservation-v2-handoff.md"
    audit_files = {
        changed_docs[0]: b"audit snapshot tasks\n",
        changed_docs[1]: b"audit snapshot index\n",
        changed_docs[2]: b"audit snapshot testing\n",
        **{f"synthetic/v2-audit-{index:04d}.txt": b"inert v2 audit source\n" for index in range(532)},
    }
    final_files = dict(audit_files)
    final_files.update({
        changed_docs[0]: b"final snapshot tasks\n",
        changed_docs[1]: b"final snapshot index\n",
        changed_docs[2]: b"final snapshot testing\n",
        added_doc: b"synthetic v2 handoff\n",
    })
    audit_meta, audit_hashes = _source_zip_and_list(
        repo, audit_pin[0], audit_pin[2], files=audit_files, pin=audit_pin,
    )
    final_meta, _ = _source_zip_and_list(
        repo, final_pin[0], final_pin[2], files=final_files, pin=final_pin,
    )

    _ = head, audit_hashes

    def synthetic_pin(pin, metadata):
        return (
            pin[0], metadata["archive_sha256"], pin[2], metadata["file_list_sha256"],
            pin[4], pin[5], pin[6], metadata["source_identity"], pin[8],
        )

    synthetic_pins = (
        synthetic_pin(corrected_pin, corrected_meta),
        synthetic_pin(audit_pin, audit_meta),
        synthetic_pin(final_pin, final_meta),
    )
    return synthetic_pins, {
        "corrected_534": corrected_meta,
        "v2_audit_535": audit_meta,
        "v2_final_536": final_meta,
        "allowed_document_changes": sorted([*changed_docs, added_doc]),
    }


def _prepare_v3_business_sources(repo: Path, profile, spec):
    """Adapt the reusable V2 tree into the exact V3 source-role layout."""
    baseline = repo / profile.baseline_relative
    confirmation_prefix = profile.confirmation_relative.as_posix() + "/"

    # V3 keeps the independent review quality fields in the review artifact,
    # while the public-CLI bypass result is sourced from acceptance.review.
    review_path = baseline / "independent-review.json"
    review = json.loads(review_path.read_bytes())
    review.pop("public_cli_bypass_found", None)
    review["mode"] = "read_only"
    review_raw = _pretty(review)
    review_path.write_bytes(review_raw)

    acceptance_path = baseline / "acceptance.json"
    acceptance = json.loads(acceptance_path.read_bytes())
    acceptance["review"] = {
        "independent_read_only_review": "passed",
        "production_source_pins_unchanged": True,
        "public_cli_bypass_found": False,
    }

    # The validation fixture already creates the genuine directory shape and
    # inert six-call journal. Rewrite only the top-level acceptance summary;
    # the directory digest intentionally covers research and process sidecars.
    tenki_root = repo / profile.tenki_evidence_relative
    tenki_acceptance_path = repo / profile.tenki_acceptance_relative
    tenki_ledger_path = repo / profile.tenki_ledger_relative
    tenki_ledger_raw = tenki_ledger_path.read_bytes()
    tenki_acceptance = {
        "schema_version": 1,
        "kind": "tenki_placement_validation_acceptance",
        "scope": "tenki-placement-validation-v1",
        "status": "completed_and_paused",
        "native": {
            "ledger_path": "research/calls.jsonl",
            "ledger_sha256": _sha(tenki_ledger_raw),
            "successful": True,
            "new_consumed": 6,
            "unknown": 0,
            "cumulative_consumed": 32,
            "stages_completed": 6,
            "stages_total": 6,
            "scope_sealed": True,
            "replay_matches": {"false_branch_stage4": True, "true_branch_stage6": True},
        },
    }
    tenki_acceptance_raw = _pretty(tenki_acceptance)
    tenki_acceptance_path.write_bytes(tenki_acceptance_raw)
    from ygo_eval.native_curry_option_validation import _curry_evidence_hash, _snapshot_curry_evidence
    tenki_directory_hash = _curry_evidence_hash(_snapshot_curry_evidence(tenki_root))

    # Build the frozen 43-path / 64-role inventory shape. The lower-level
    # recovery fixture has only one measured evidence file, so add inert files
    # and bind every one through the real V2 report input index and inventory.
    # The authenticated V3 source uses workspace_identity at identity.json;
    # the earlier V2 fixture's confirmation_summary is not part of that shape.
    v2_path = repo / profile.v2_report_relative
    v2_report = json.loads(v2_path.read_bytes())
    v2_inputs = list(v2_report["inputs"])
    summary_rows = [
        row["path"] for row in v2_inputs
        if row["path"].startswith(confirmation_prefix)
        and row["role"] == "confirmation_summary"
    ]
    if len(summary_rows) != 1:
        raise AssertionError(f"synthetic_confirmation_summary_role:{len(summary_rows)}")
    v2_inputs = [
        row for row in v2_inputs
        if not (
            row["path"].startswith(confirmation_prefix)
            and row["role"] == "confirmation_summary"
        )
    ]
    # The real V3 inventory pins summary.json as an ordinary evidence role;
    # keep that physical file and role-bound hash while omitting the obsolete
    # confirmation_summary alias from the V3 source shape.
    summary_relative = summary_rows[0]
    summary_raw = (repo / summary_relative).read_bytes()
    v2_inputs.append({
        "role": "confirmation_evidence_file_000",
        "path": summary_relative,
        "sha256": _sha(summary_raw),
        "bytes": len(summary_raw),
    })
    confirmation_rows = [row for row in v2_inputs if row["path"].startswith(confirmation_prefix)]
    unique_by_path = {row["path"]: row for row in confirmation_rows}
    if len(unique_by_path) != 23 or len(confirmation_rows) != 26:
        raise AssertionError(
            f"synthetic_confirmation_base_shape:{len(unique_by_path)}:{len(confirmation_rows)}"
        )

    excluded = {
        (profile.confirmation_relative / "acceptance.json").as_posix(),
        (profile.confirmation_relative / "evidence-inventory.json").as_posix(),
        (profile.confirmation_relative / "final-build/delivery.json").as_posix(),
    }
    evidence_paths = sorted(set(unique_by_path) - excluded)
    if len(evidence_paths) != 20:
        raise AssertionError(f"synthetic_confirmation_base_evidence_shape:{len(evidence_paths)}")
    confirmation_root = repo / profile.confirmation_relative
    for index in range(20):
        relative = f"research/evidence-v3/synthetic-{index:02d}.bin"
        path = confirmation_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"inert synthetic evidence {index:02d}\n".encode("ascii"))
        evidence_paths.append((profile.confirmation_relative / relative).as_posix())
    evidence_paths.sort()
    if len(evidence_paths) != 40:
        raise AssertionError(f"synthetic_confirmation_evidence_shape:{len(evidence_paths)}")

    inventory_path = confirmation_root / "evidence-inventory.json"
    inventory = json.loads(inventory_path.read_bytes())
    inventory["entries"] = []
    for name in evidence_paths:
        full_path = repo / name
        raw = full_path.read_bytes()
        inventory["entries"].append({
            "path": name[len(confirmation_prefix):],
            "sha256": _sha(raw),
            "bytes": len(raw),
        })
    inventory["entry_count"] = len(evidence_paths)
    inventory["accessible_file_bytes"] = sum(row["bytes"] for row in inventory["entries"])
    inventory["complete_for_measured_root"] = True
    inventory["access_errors"] = []
    inventory_raw = _pretty(inventory)
    inventory_path.write_bytes(inventory_raw)
    inventory_report_rows = [
        row for row in v2_inputs
        if row["path"] == (profile.confirmation_relative / "evidence-inventory.json").as_posix()
    ]
    if len(inventory_report_rows) != 1:
        raise AssertionError(f"synthetic_inventory_report_pin:{len(inventory_report_rows)}")
    inventory_report_rows[0].update({"sha256": _sha(inventory_raw), "bytes": len(inventory_raw)})

    prior_evidence_rows = [
        row for row in confirmation_rows
        if row["role"].startswith("confirmation_evidence_file_")
    ]
    prior_evidence_by_path = {row["path"]: row for row in prior_evidence_rows}
    if len(prior_evidence_by_path) != len(prior_evidence_rows) or not prior_evidence_rows:
        raise AssertionError(f"synthetic_prior_evidence_role_count:{len(prior_evidence_rows)}")
    evidence_role_rows = []
    for index, name in enumerate(evidence_paths, 1):
        raw = (repo / name).read_bytes()
        evidence_row = {
            "role": f"confirmation_evidence_file_{index:03d}",
            "path": name,
            "sha256": _sha(raw),
            "bytes": len(raw),
        }
        if name in prior_evidence_by_path:
            prior_evidence_by_path[name].update(evidence_row)
        else:
            evidence_role_rows.append(evidence_row)
    v2_inputs.extend(evidence_role_rows)

    # Remove the V2 fixture's ninth direct ledger role; V3 binds only the
    # validation evidence directory, then follows its acceptance and ledger.
    v2_inputs = [
        row for row in v2_inputs
        if row["path"] != "data/runtime/synthetic-reservation-history/research/calls.jsonl"
    ]
    # Match the authenticated V2 report's distinct directory and child pins:
    # the directory is a zero-byte evidence-digest row, acceptance is direct,
    # and the ledger itself is represented only inside that directory tree.
    tenki_directory_path = profile.tenki_evidence_relative.as_posix()
    tenki_acceptance_rel = profile.tenki_acceptance_relative.as_posix()
    ledger_path = profile.tenki_ledger_relative.as_posix()
    v2_inputs = [
        row for row in v2_inputs
        if row["path"] not in {tenki_directory_path, tenki_acceptance_rel, ledger_path}
    ]
    v2_inputs.extend((
        {
            "role": "historical_ledger_09_directory_evidence",
            "path": tenki_directory_path,
            "sha256": tenki_directory_hash,
            "bytes": 0,
        },
        {
            "role": "historical_tenki_acceptance",
            "path": tenki_acceptance_rel,
            "sha256": _sha(tenki_acceptance_raw),
            "bytes": len(tenki_acceptance_raw),
        },
    ))
    v2_report["inputs"] = v2_inputs
    confirmation_rows = [row for row in v2_inputs if row["path"].startswith(confirmation_prefix)]
    unique_confirmation_paths = {row["path"] for row in confirmation_rows}
    if len(confirmation_rows) != 64 or len(unique_confirmation_paths) != 43:
        raise AssertionError(
            f"synthetic_confirmation_v3_shape:{len(confirmation_rows)}:{len(unique_confirmation_paths)}"
        )
    if sum(row["role"].startswith("confirmation_evidence_file_") for row in confirmation_rows) != 40:
        raise AssertionError("synthetic_confirmation_v3_evidence_role_count")

    # The authenticated historical V2 acceptance is a separate source root in
    # production. Keep the confirmation acceptance above as one of the 64
    # confirmation-role rows, then add an independently pinned external file
    # at the fixed V2 acceptance path.
    external_v2_acceptance_relative = reservation.V2_ACCEPTANCE_RELATIVE
    external_v2_acceptance_raw = _pretty({
        "schema_version": 1,
        "kind": "synthetic_historical_v2_acceptance",
        "status": "passed",
        "native_calls": 0,
        "execution_ready": False,
    })
    _write(repo, external_v2_acceptance_relative, external_v2_acceptance_raw)
    profile = replace(
        profile,
        v2_acceptance_relative=external_v2_acceptance_relative,
        v2_acceptance_sha256=_sha(external_v2_acceptance_raw),
    )
    v2_raw = _canonical(v2_report)
    v2_path.write_bytes(v2_raw)
    _write(repo, profile.baseline_relative / "synthetic-success-report.json", v2_raw)

    # Keep the protection manifest's ninth row bound to the ledger file. The
    # V2 report separately authenticates the containing evidence-directory
    # digest and the acceptance file, which lets the verifier prove all three
    # bindings without treating the directory as a ledger file.
    protection_path = baseline / "protected-material-check.json"
    protection = json.loads(protection_path.read_bytes())
    ledgers = protection["authenticated_historical_ledgers"]
    if len(ledgers) != 9:
        raise AssertionError(f"synthetic_historical_ledger_count:{len(ledgers)}")
    tenki_ledger_pin = {
        "path": profile.tenki_ledger_relative.as_posix(),
        "expected_sha256": _sha(tenki_ledger_raw),
        "actual_sha256": _sha(tenki_ledger_raw),
        "passed": True,
    }
    # The production V3 contract reserves ledger slot 05 for the Tenki
    # validation ledger, whose bytes are authenticated through its containing
    # evidence-directory digest. Keep the other eight direct ledger pins and
    # place the special pin at the same ordinal so their role names remain
    # historical_ledger_01..04 and historical_ledger_06..09.
    direct_ledgers = ledgers[:-1]
    ledgers[:] = direct_ledgers[:4] + [tenki_ledger_pin] + direct_ledgers[4:]
    protection_raw = _pretty(protection)
    protection_path.write_bytes(protection_raw)

    v2_sha = _sha(v2_raw)
    acceptance["public_audit_report"] = {"sha256": v2_sha}
    acceptance["historical_boundary"]["historical_v2_report_sha256"] = v2_sha
    acceptance["historical_boundary"]["historical_acceptance_sha256"] = profile.v2_acceptance_sha256
    acceptance["historical_boundary"]["certified_consumed"] = 32
    acceptance["historical_boundary"]["certified_ledger_count"] = 9
    acceptance["historical_boundary"]["certified_unknown"] = 0
    acceptance_raw = _pretty(acceptance)
    acceptance_path.write_bytes(acceptance_raw)

    synthetic_sha = _sha(v2_raw)
    acceptance_hash = _sha(acceptance_raw)
    protection_hash = _sha(protection_raw)
    review_hash = _sha(review_raw)
    delivery_path = baseline / "final-build/delivery.json"
    delivery = json.loads(delivery_path.read_bytes())
    delivery.update({
        "acceptance_sha256": acceptance_hash,
        "independent_review_sha256": review_hash,
        "protected_material_check_sha256": protection_hash,
        "synthetic_report_sha256": synthetic_sha,
    })
    delivery_raw = _pretty(delivery)
    delivery_path.write_bytes(delivery_raw)

    profile = replace(
        profile,
        delivery_sha256=_sha(delivery_raw),
        v2_report_sha256=v2_sha,
        acceptance_sha256=acceptance_hash,
        review_sha256=review_hash,
        protection_sha256=protection_hash,
        synthetic_report_sha256=synthetic_sha,
        confirmation_input_count=43,
        confirmation_role_input_count=64,
        confirmation_evidence_count=len(inventory["entries"]),
        confirmation_evidence_bytes=inventory["accessible_file_bytes"],
        tenki_evidence_sha256=tenki_directory_hash,
        tenki_acceptance_sha256=_sha(tenki_acceptance_raw),
        tenki_ledger_sha256=_sha(tenki_ledger_raw),
    )

    # The V3 acceptance's authenticated V2 report must itself contain the
    # same physical input index used above; its prior acceptance remains the
    # lower-level audit acceptance already pinned by the V2 report.
    return profile, v2_report, tenki_directory_hash


def _freeze_absolute_ledger_input(repo: Path, profile) -> None:
    """Rebind the synthetic stage-1 input and all existing content pins.

    V3 accepts the historically saved absolute Windows ledger path. This
    helper changes only generated test bytes and updates the real evidence
    inventory and authenticated V2 input index that bind those bytes.
    """
    confirmation = repo / profile.confirmation_relative
    input_relative = Path("research/stage-1-input.json")
    input_path = confirmation / input_relative
    stage_input = json.loads(input_path.read_bytes())
    stage_input["ledger"] = str(
        (confirmation / "research/calls.jsonl").absolute()
    )
    input_raw = _pretty(stage_input)
    input_path.write_bytes(input_raw)
    input_sha = _sha(input_raw)

    seal_path = confirmation / "research/stage-1-input-seal.json"
    seal = json.loads(seal_path.read_bytes())
    seal["input_sha256"] = input_sha
    seal_raw = _pretty(seal)
    seal_path.write_bytes(seal_raw)

    prepared_path = confirmation / "research/prepared.json"
    prepared = json.loads(prepared_path.read_bytes())
    prepared["stage1_input_sha256"] = input_sha
    prepared_raw = _pretty(prepared)
    prepared_path.write_bytes(prepared_raw)

    inventory_path = confirmation / "evidence-inventory.json"
    inventory = json.loads(inventory_path.read_bytes())
    relative_text = input_relative.as_posix()
    matched = [row for row in inventory["entries"] if row["path"] == relative_text]
    inventory_raw = inventory_path.read_bytes()
    if matched:
        if len(matched) != 1:
            raise AssertionError(f"synthetic_stage_input_inventory_binding:{len(matched)}")
        matched[0].update({"sha256": input_sha, "bytes": len(input_raw)})
        inventory["accessible_file_bytes"] = sum(row["bytes"] for row in inventory["entries"])
        inventory_raw = _pretty(inventory)
        inventory_path.write_bytes(inventory_raw)

    v2_path = repo / profile.v2_report_relative
    v2_report = json.loads(v2_path.read_bytes())
    changes = {
        (profile.confirmation_relative / input_relative).as_posix(): input_raw,
        (profile.confirmation_relative / "research/stage-1-input-seal.json").as_posix(): seal_raw,
        (profile.confirmation_relative / "research/prepared.json").as_posix(): prepared_raw,
    }
    if matched:
        changes[(profile.confirmation_relative / "evidence-inventory.json").as_posix()] = inventory_raw
    for name, raw in changes.items():
        rows = [row for row in v2_report["inputs"] if row["path"] == name]
        if len(rows) != 1:
            raise AssertionError(f"synthetic_v2_input_pin_binding:{name}:{len(rows)}")
        rows[0].update({"sha256": _sha(raw), "bytes": len(raw)})
    v2_path.write_bytes(_canonical(v2_report))


def _make_v2_failed_attempt(repo: Path, profile, v1_report: Path) -> tuple[Path, str]:
    """Run the public V2 CLI against the V3 review shape and retain its failure."""
    import contextlib
    import sys
    from unittest.mock import patch

    from ygo_eval.research import main

    raw_v1 = v1_report.read_bytes()
    original_version_spec = reservation._version_spec
    spec = replace(
        original_version_spec(2),
        previous_failure_sha256=_sha(raw_v1),
    )
    output = repo / spec.output_relative / reservation.REPORT_NAME
    argv = [
        "research", "prepare-curry-consumption-reservation",
        "--report-version", "2",
        "--baseline-dir", str(repo / profile.baseline_relative),
        "--output", str(output),
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(reservation, "_repo_root", return_value=repo),
        patch.object(reservation, "_production_profile", return_value=profile),
        patch.object(
            reservation,
            "_version_spec",
            side_effect=lambda version: spec if version == 2 else original_version_spec(version),
        ),
        patch("ygo_data.identity.stable_source", side_effect=__import__(
            "tests.support.curry_recovery_e2e", fromlist=["synthetic_source_identity"],
        ).synthetic_source_identity),
        contextlib.redirect_stdout(io.StringIO()) as stdout,
        _forbid_native_activity(),
    ):
        code = main()
    if code != 1:
        raise AssertionError(f"synthetic_v2_failed_attempt_not_created:{code}:{stdout.getvalue()}")
    report = json.loads(stdout.getvalue())
    if report.get("failure_checkpoint") != "latest_delivery_chain" or report.get("diagnostics") != ["independent_review_invalid"]:
        raise AssertionError(f"synthetic_v2_failure_contract_mismatch:{stdout.getvalue()}")
    return output, _sha(output.read_bytes())


def build_synthetic_v3_reservation_tree(root: Path):
    """Create a complete inert V3 tree and return fixed injected test bindings."""
    from unittest.mock import patch

    from tests.support.curry_recovery_e2e import synthetic_source_identity

    base = build_synthetic_reservation_tree(root / "base")
    repo = base.repo
    profile = base.profile
    _freeze_absolute_ledger_input(repo, profile)
    v1_report = build_synthetic_v1_failed_attempt(repo, profile)
    profile, _v2_report, tenki_directory_hash = _prepare_v3_business_sources(
        repo, profile, reservation._version_spec(3),
    )
    v2_report, v2_hash = _make_v2_failed_attempt(repo, profile, v1_report)

    # The V3 acceptance binds a synthetic failed V2 attempt to the two
    # synthetic source archives; these are static bytes, not executable code.
    spec0 = reservation._version_spec(3)
    archive_pins = []
    for pin in spec0.recovery_archives:
        archive_pins.append(pin)
    recovery_meta = {}
    recovery_pins, recovery_meta = _build_v3_recovery_archives(repo, spec0)
    corrected_pin, audit_pin, final_pin = recovery_pins
    acceptance = {
        "schema_version": 1,
        "kind": "curry_consumption_reservation_v2_acceptance",
        "status": "blocked",
        "native_calls": 0,
        "previous_v1_report_sha256": _sha(v1_report.read_bytes()),
        "audit_source": {
            "archive_sha256": recovery_meta["v2_audit_535"]["archive_sha256"],
            "file_count": recovery_meta["v2_audit_535"]["file_count"],
            "file_list_sha256": recovery_meta["v2_audit_535"]["file_list_sha256"],
            "identity": recovery_meta["v2_audit_535"]["source_identity"],
        },
        "final_document_source": {
            "archive_bytes": (repo / final_pin[0]).stat().st_size,
            "archive_sha256": recovery_meta["v2_final_536"]["archive_sha256"],
            "file_count": recovery_meta["v2_final_536"]["file_count"],
            "file_list_sha256": recovery_meta["v2_final_536"]["file_list_sha256"],
            "head": final_pin[6],
            "kind": "curry_consumption_reservation_v2_final_source_freeze",
            "present_file_count": recovery_meta["v2_final_536"]["file_count"],
            "schema_version": 1,
            "source_identity": recovery_meta["v2_final_536"]["source_identity"],
        },
        "real_read_only_audit": {
            "report_sha256": v2_hash,
            "failure_checkpoint": "latest_delivery_chain",
            "diagnostic": "independent_review_invalid",
        },
        "reservation": {
            "planned_total": None,
            "recorded": False,
            "reservation_id": None,
            "risk_reserve_calls": 7,
        },
        "qualifications": dict(reservation._QUALIFICATIONS),
    }
    acceptance_raw = _pretty(acceptance)
    v2_acceptance_path = _write(repo, spec0.previous_v2_acceptance_relative, acceptance_raw)

    v3_spec = replace(
        spec0,
        previous_failure_sha256=_sha(v1_report.read_bytes()),
        previous_v2_failure_sha256=v2_hash,
        recovery_archives=(corrected_pin, audit_pin, final_pin),
        previous_v2_acceptance_sha256=_sha(acceptance_raw),
        previous_v2_acceptance_bytes=len(acceptance_raw),
    )
    # Source factory only writes the V3 tool-member source bytes into the
    # synthetic checkout; no external runtime material is copied.
    workspace = Path(__file__).resolve().parents[2]
    for name in v3_spec.tool_files:
        _write(repo, name, (workspace / name).read_bytes())

    fixture = SimpleNamespace(
        base=base,
        repo=repo,
        profile=profile,
        spec=v3_spec,
        v1_report=v1_report,
        v2_report=v2_report,
        v2_failure_report=v2_report,
        v2_acceptance=v2_acceptance_path,
        tenki_directory_hash=tenki_directory_hash,
        recovery_meta=recovery_meta,
    )
    return fixture


def invoke_v3_public_cli(
    fixture, *, verify_only: bool = False,
    output_relative: Path | None = None,
    mutate_output_tree_during_verify: bool = False,
    mutate_external_v2_acceptance_after_validation: bool = False,
):
    """Invoke the public research CLI with only its private test bindings fixed."""
    import contextlib
    import sys
    from unittest.mock import patch

    from tests.support.curry_recovery_e2e import synthetic_source_identity
    from ygo_eval.research import main

    from dataclasses import replace

    spec = (
        replace(fixture.spec, output_relative=output_relative)
        if output_relative is not None else fixture.spec
    )
    output_root = fixture.repo / spec.output_relative
    output = output_root / reservation.REPORT_NAME
    argv = [
        "research", "prepare-curry-consumption-reservation",
        "--report-version", "3",
        "--baseline-dir", str(fixture.repo / fixture.profile.baseline_relative),
        "--output", str(output),
    ]
    if verify_only:
        argv.append("--verify-only")
    spec_map = {1: reservation._version_spec(1), 2: reservation._version_spec(2), 3: spec}
    original_audit = reservation.audit_to_output
    original_output_tree = reservation._verify_output_tree
    original_historical_ledgers = reservation._verify_historical_ledgers
    tree_mutated = False
    external_acceptance_mutated = False

    def observe_audit_exception(*args, **kwargs):
        try:
            return original_audit(*args, **kwargs)
        except Exception as exc:
            fixture.last_audit_exception = f"{type(exc).__name__}:{exc}"
            traceback = exc.__traceback__
            while traceback is not None:
                frame = traceback.tb_frame
                if frame.f_code.co_name == "audit_to_output":
                    report = frame.f_locals.get("report")
                    if isinstance(report, dict):
                        prefix = fixture.profile.confirmation_relative.as_posix() + "/"
                        rows = [
                            row for row in report.get("inputs", [])
                            if row.get("path", "").startswith(prefix)
                        ]
                        fixture.last_confirmation_shape = {
                            "compatibility_inventory": report.get("compatibility_basis", {}).get("confirmation_inventory"),
                            "rows": len(rows),
                            "unique_paths": len({row["path"] for row in rows}),
                            "evidence_roles": sum(
                                row.get("role", "").startswith("confirmation_evidence_file_")
                                for row in rows
                            ),
                            "samples": rows[:3],
                        }
                traceback = traceback.tb_next
            raise

    def observe_output_tree(path):
        nonlocal tree_mutated
        snapshot = original_output_tree(path)
        if (
            verify_only and mutate_output_tree_during_verify and not tree_mutated
            and Path(path) == output_root
        ):
            (output_root / "verify-drift.bin").write_bytes(b"synthetic concurrent output drift\n")
            tree_mutated = True
        return snapshot

    def observe_historical_ledgers(*args, **kwargs):
        nonlocal external_acceptance_mutated
        result = original_historical_ledgers(*args, **kwargs)
        if mutate_external_v2_acceptance_after_validation and not external_acceptance_mutated:
            acceptance_path = fixture.repo / fixture.profile.v2_acceptance_relative
            acceptance_path.write_bytes(acceptance_path.read_bytes() + b"\n")
            external_acceptance_mutated = True
        return result

    with (
        patch.object(sys, "argv", argv),
        patch.object(reservation, "_repo_root", return_value=fixture.repo),
        patch.object(reservation, "_production_profile", return_value=fixture.profile),
        patch.object(reservation, "_version_spec", side_effect=lambda version: spec_map[version]),
        patch.object(reservation, "audit_to_output", side_effect=observe_audit_exception),
        patch.object(reservation, "_verify_output_tree", side_effect=observe_output_tree),
        patch.object(reservation, "_verify_historical_ledgers", side_effect=observe_historical_ledgers),
        patch("ygo_data.identity.stable_source", side_effect=synthetic_source_identity),
        contextlib.redirect_stdout(io.StringIO()) as stdout,
        _forbid_native_activity(),
    ):
        code = main()
    return code, stdout.getvalue(), output
