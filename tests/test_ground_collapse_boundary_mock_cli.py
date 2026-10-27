"""Boundary-mocked public CLI check; this is not a full source-chain E2E.

The fixed historical delivery and option-revalidation validators are replaced
by synthetic providers, so this only exercises candidate/runtime validation,
report publication, and verify reconstruction through the public dispatcher.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import uuid
from argparse import Namespace
from dataclasses import replace
from unittest.mock import patch

from ygo_data.identity import source_identity
from ygo_eval import ground_collapse_preparation as preparation
from ygo_eval import native_curry_option_validation as curry_validation
from ygo_eval import research
from ygo_eval.ground_collapse_preparation import PRODUCTION_PROFILE, sha256

# Reuse the established fully synthetic candidate/runtime fixture. It writes no
# real asset or historical evidence and uses a read-only SQLite catalog.
from test_ground_collapse_preparation import _runtime_gate_fixture


def _synthetic_repo() -> tuple[Path, object, dict[str, Path]]:
    workspace = Path(__file__).resolve().parents[1]
    root = workspace / "target/ground-collapse-preparation-tests" / f"public-e2e-{uuid.uuid4().hex}"
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=False)

    # The tool archive is built from fixed project code, while all evaluated
    # scenario inputs and assets below are synthetic and confined to this repo.
    for relative in PRODUCTION_PROFILE.tool_files:
        source = workspace / relative
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    _capture, _candidate, _core, profile, paths = _runtime_gate_fixture(repo)
    baseline = repo / "data/runtime/synthetic-baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    delivery = baseline / "delivery.json"
    delivery.write_bytes(b"synthetic pinned delivery\n")

    profile = replace(
        profile,
        output_root=Path("data/runtime/p1-ground-collapse-public-e2e"),
        baseline_root=Path("data/runtime/synthetic-baseline"),
        core_source_path=Path("core"),
        curry_delivery_sha256=sha256(delivery.read_bytes()),
    )
    # This synthetic baseline intentionally avoids any runner/worker. The two
    # external historical-source validators are mocked; this test therefore
    # does not claim to exercise their fixed source-chain gates. Frozen
    # candidate, SQLite, script, core, hashing, publication, report validation,
    # and verify reconstruction remain production code.
    return repo, profile, paths


def _invoke(repo: Path, profile, *, verify_only: bool) -> tuple[int, dict]:
    args = [
        "research", "prepare-ground-collapse-probe",
        "--baseline-dir", str((repo / profile.baseline_root).resolve()),
        "--preparation", str((repo / profile.preparation_cases_path).resolve()),
        "--cases", str((repo / profile.frozen_cases_path).resolve()),
        "--core-source", str((repo / profile.core_source_path).resolve()),
        "--output", str((repo / profile.output_root).resolve()),
    ]
    if verify_only:
        args.append("--verify-only")
    from io import StringIO
    import contextlib

    stdout = StringIO()
    with patch.object(sys, "argv", args), contextlib.redirect_stdout(stdout):
        code = research.main()
    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError:
        payload = {"raw": stdout.getvalue()}
    return code, payload


def test_boundary_mocked_public_prepare_refuses_missing_source_chain_roles():
    repo, profile, paths = _synthetic_repo()
    output = repo / profile.output_root
    delivery_calls: list[str] = []
    history_calls: list[str] = []
    dispatch_errors: list[str] = []
    real_prepare = preparation.prepare_ground_collapse_probe
    def synthetic_delivery(capture, source_repo: Path, selected_profile):
        delivery_calls.append("called")
        baseline_root = source_repo / selected_profile.baseline_root
        capture.directory("latest_curry_delivery_tree", baseline_root)
        capture.read("latest_curry_delivery", baseline_root / "delivery.json",
                     selected_profile.curry_delivery_sha256)
        return {"delivery_sha256": selected_profile.curry_delivery_sha256,
                "synthetic_fixture": True,
                "certified_consumed": selected_profile.prior_certified_consumed,
                "policy_reserved": selected_profile.policy_reserved,
                "planning_total": selected_profile.planning_total}

    def synthetic_history(_source_repo, _baseline_root, *, source_collector, **_kwargs):
        history_calls.append("called")
        # This preserves the fixed public accounting basis from the selected
        # baseline shape without reading any local historical ledger.
        return ({"certified_historical_consumed": 40,
                 "policy_reserved": 7,
                 "planning_base": 47}, {})

    def invoke_with_synthetic_repo(args: Namespace):
        try:
            return real_prepare(
                args, repo=repo, source_collector=source_identity, profile=profile,
            )
        except Exception as error:
            dispatch_errors.append(f"{type(error).__name__}:{error}")
            raise

    with (
        patch.object(preparation, "_source_description", return_value=profile),
        patch.object(preparation, "_verify_curry_scope_delivery", side_effect=synthetic_delivery),
        patch.object(curry_validation, "_verify_option_revalidation_baseline", side_effect=synthetic_history),
        patch.object(preparation, "prepare_ground_collapse_probe", side_effect=invoke_with_synthetic_repo),
    ):
        prepare_code, prepare_stdout = _invoke(repo, profile, verify_only=False)
        assert prepare_code == 2, (dispatch_errors, prepare_stdout)
        assert dispatch_errors == ["PreparationError:report_success_inputs_invalid"]
        assert prepare_stdout["raw"].startswith("prepare-ground-collapse-probe refused:")
        diagnostic = json.loads((output / "publication-diagnostic.json").read_bytes())
        assert diagnostic["checkpoint"] == "report_publication"
        assert diagnostic["code"] == "report_success_inputs_invalid"
        assert not (output / "preparation.json").exists()

    assert delivery_calls == ["called"]
    assert history_calls == ["called"]
    assert not list(repo.rglob("calls.jsonl"))
    assert paths["target_script"].is_file()
