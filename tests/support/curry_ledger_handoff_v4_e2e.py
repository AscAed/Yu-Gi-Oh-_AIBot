"""Synthetic V4 source tree for the Curry saved-input audit."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from dataclasses import replace

from ygo_eval import curry_ledger_handoff_audit as handoff
from tests.support.curry_ledger_handoff_v3_e2e import (
    build_synthetic_handoff_v3_tree,
    install_synthetic_previous_v3_failure,
)


V4_STAGE1_STDOUT = {
    "successful": True,
    "native_calls": 1,
    "ledger": {
        "abandoned": 0,
        "completed": 1,
        "consumed": 1,
        "limit": 7,
        "reserved": 0,
        "unknown": 0,
    },
    "certified_historical_consumed": 32,
    "policy_reserved": 7,
    "planning_base": 39,
    "reservation_id": "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63",
    "reservation_policy_id": "curry-unknown-reserve-seven-v1",
    "new_consumed": 1,
    "certified_consumed_including_new": 33,
    "planning_total": 40,
    "unknown": 0,
    "old_confirmation_actual_consumed": None,
    "actual_all_history_cumulative": None,
}


def stage1_stdout_bytes(
    option_spec: Any | None = None, *, overrides: Mapping[str, Any] | None = None,
) -> bytes:
    """Encode a test-owned golden output; do not call the production oracle."""
    value = dict(V4_STAGE1_STDOUT)
    if option_spec is not None:
        value["reservation_id"] = option_spec.reservation_id
    if overrides:
        value.update(overrides)
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def build_synthetic_handoff_v4_tree(
    root: Path, *, stage1_stdout: bytes | Callable[[Any], bytes] | None = None,
):
    """Extend the complete V3 tree with V4's prior failed V3 release."""
    stdout_factory = stage1_stdout if stage1_stdout is not None else (
        lambda option_spec: stage1_stdout_bytes(option_spec)
    )
    tree = build_synthetic_handoff_v3_tree(
        Path(root) / "v3-base",
        stage1_stdout=stdout_factory,
    )
    previous_v3 = install_synthetic_previous_v3_failure(
        tree.repo, baseline_sources=tree.sources,
    )
    if any(child.role == previous_v3.role for child in tree.sources.children):
        raise AssertionError("synthetic_v4_previous_v3_role_already_present")
    return replace(
        tree,
        sources=replace(
            tree.sources,
            children=(*tree.sources.children, previous_v3),
        ),
    )
