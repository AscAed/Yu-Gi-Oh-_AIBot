"""Fixed-scope seven-stage Mooyan Curry opcode 14 validation workflow.

The module owns the Curry branch policy and its report checks.  It reuses only
the generic journaled stage driver; it does not invoke or infer native results
outside the caller-provided runner.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ygo_data.identity import canonical
from ygo_eval.curry_option_protocol import (
    _parse_option14,
    validate_curry_option_result,
)
from ygo_eval.native_tenki_workflow import (
    WorkflowSpec,
    run_six_stage_workflow,
)
from ygo_eval.prompt_probe_prepare import safe_path, strict_json
from ygo_eval.terminal_regression import immutable_write


@dataclass(frozen=True, slots=True)
class CurryScopeSpec:
    scope: str
    output_root: Path
    baseline_root: Path
    limit: int
    wall_seconds: int
    worker_timeout_seconds: int
    old_consumed: int
    batch_kind: str
    input_seal_kind: str
    runner_role: str
    delivery_acceptance_sha256: str
    delivery_sha256: str
    baseline_acceptance_sha256: str | None = None
    report_prefix: str = "native_curry_option_validation"
    baseline_audit_sha256: str | None = None
    baseline_recovery_sha256: str | None = None
    candidate_config_root: Path | None = None
    reservation_sha256: str | None = None
    reservation_id: str | None = None
    reservation_policy_id: str | None = None
    certified_historical_consumed: int | None = None
    policy_reserved: int | None = None
    planning_base: int | None = None
    reservation_relative: Path | None = None
    acceptance_relative: Path | None = None


class CurryFrozenInputMismatch(ValueError):
    """Stable role-level failure for a frozen input whose bound hash changed."""

    def __init__(self, role: str, expected_sha256: str | None,
                 found_sha256: str | None) -> None:
        self.role = role
        self.expected_sha256 = expected_sha256
        self.found_sha256 = found_sha256
        self.diagnostic = f"curry_saved_{role}_hash_mismatch"
        super().__init__(self.diagnostic)


CURRY_SCOPE = CurryScopeSpec(
    scope="curry-option-validation-v1",
    output_root=Path("data/runtime/p1-curry-option-validation-native-2026-10-23"),
    baseline_root=Path("data/runtime/p1-tenki-placement-validation-native-2026-10-23"),
    limit=7,
    wall_seconds=7200,
    worker_timeout_seconds=30,
    old_consumed=32,
    batch_kind="curry-option-validation-v1",
    input_seal_kind="curry_option_validation_stage_input_seal",
    runner_role="curry_option_validation_runner",
    delivery_acceptance_sha256=(
        "242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9"
    ),
    delivery_sha256=(
        "7c46a4a790c56dea2daf77478c5a33654ee20bb3bd3179bdfb57ebf74cc21061"
    ),
)

PREPARATION_PATH = Path(
    "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/prepared-cases.json"
)
PREPARATION_REPORT_PATH = Path(
    "data/runtime/p1-prompt-probes-offline-2026-10-21/research-final/report.json"
)
PREPARATION_ACCEPTANCE_PATH = Path(
    "data/runtime/p1-prompt-probes-offline-2026-10-21/acceptance.json"
)
OPERATIONS_SOURCE_SHA256 = (
    "b46cf0d53825cb662af319a7382015b555422aa11903067445c994c4b0c8a990"
)
HISTORICAL_SOURCE_TRANSITION = {
    "scope": "curry-option-validation-v1",
    "path": "crates/ygo-engine-adapter/src/codec.rs",
    "historical_sha256": "224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e",
    "current_sha256": "68cf8de986c331060f72d95a56acc68ecec34d916230f5302d33210b254ca42d",
    "reason": "RECOVER-92-decoder-added-for-this-fixed-scope",
    "historical_bytes_verified_from_archive": True,
}
PINNED_INPUT_SHA256 = {
    "preparation": "235d218426e9a14fdc000ca2e81a64b00cac394f247d0c53029dc1c2e4c2b022",
    "preparation_report": "22536f6031adc88eae4bb7e2ada4f9ff374a2d227e66927e084180552e12b073",
    "preparation_acceptance": "0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7",
    "candidate_case": "71aa1e51edf74b3b4b572d61cbdaf7b25414ebc6fba745c72b1e82fe18e5a23c",
    "base_request": "d25d2e79a58728221111d9007f5890b3e99be2bdcf4a8aee1a17554d59da91bb",
    "operations_source": OPERATIONS_SOURCE_SHA256,
    "adapter_codec": HISTORICAL_SOURCE_TRANSITION["current_sha256"],
}
BASELINE_ACCEPTANCE_SHA256 = CURRY_SCOPE.delivery_acceptance_sha256
BASELINE_DELIVERY_SHA256 = CURRY_SCOPE.delivery_sha256
BASELINE_NATIVE_FILE_LIST_SHA256 = (
    "fd02e8e722a38b0edfdfc0058c9d4007f1059edfe3c641c8b4a2774a00939653"
)
BASE_REQUEST_SHA256 = PINNED_INPUT_SHA256["base_request"]
CANDIDATE_CASE_SHA256 = PINNED_INPUT_SHA256["candidate_case"]
FROZEN_CASES_PATH = Path("data/runtime/baseline-2026-10-19/research/frozen-cases.json")

FLAGS = {
    "proof_ready": False,
    "complete_action_coverage": False,
    "global_optimality": False,
    "native_probability_verified": False,
}
RECOVERY_REFUSAL_DIAGNOSTICS_ROOT = Path(
    "data/runtime/p1-curry-input-recovery-diagnostics-2026-10-24"
)
PARENT_STAGE = {2: 1, 3: 2, 4: 3, 5: 4, 6: 3, 7: 6}
PENDING_OPCODE = {1: 11, 2: 18, 3: 14, 4: 11, 5: 11, 6: 11, 7: 11}
PROMPT_OPCODES = frozenset((11, 12, 13, 14, 15, 16, 18, 19, 24, 26))
OPTION_DESCRIPTIONS = (60_895_602_409_472, 60_895_602_409_473)
CURRY_CARD_ID = 58_074_572
RECOVER_AMOUNT = 200
HASH = re.compile(r"^[a-f0-9]{64}$")
MANIFEST_INPUT_ROLES = (
    "preparation", "preparation_report", "preparation_acceptance",
    "candidate_case", "base_request", "operations_source", "runner",
    "adapter_codec", "worker", "cli", "build_record", "identity", "window_start",
    "source_archive", "source_file_list", "ordinary_config",
    "tournament_config", "banlist", "core_source", "baseline_delivery",
)

CONFIRMATION_AUDIT_SHA256 = (
    "f31e019affc99d3cf8cfc81921f72a424c904fcc4750b67a0a443ae3fc5a74b5"
)
CONFIRMATION_DELIVERY_SHA256 = (
    "58f9d28bcf5ac20cd3ee517aa70a6cc9fec294973a295a51d1dc415b4212eee0"
)
CONFIRMATION_INPUT_ROLES = (*MANIFEST_INPUT_ROLES, "baseline_audit")
CONFIRMATION_SCOPE = CurryScopeSpec(
    scope="curry-option-confirmation-v1",
    output_root=Path("data/runtime/p1-curry-option-confirmation-native-2026-10-24"),
    baseline_root=Path("data/runtime/p1-curry-asset-binding-offline-2026-10-24"),
    limit=7,
    wall_seconds=7200,
    worker_timeout_seconds=30,
    old_consumed=32,
    batch_kind="curry-option-confirmation-v1",
    input_seal_kind="curry_option_confirmation_stage_input_seal",
    runner_role="curry_option_confirmation_runner",
    delivery_acceptance_sha256="",
    delivery_sha256=CONFIRMATION_DELIVERY_SHA256,
    report_prefix="native_curry_option_confirmation",
    baseline_audit_sha256=CONFIRMATION_AUDIT_SHA256,
    candidate_config_root=CURRY_SCOPE.output_root,
)

V3_RESERVATION_SHA256 = (
    "14c13e4992673115c0211259dd7d035d968b9c36518c28b4a4ea159ff06ad43f"
)
V3_ACCEPTANCE_SHA256 = (
    "704a72b2ad65ba95874030f199158a673ce18e19901b29d9bfb63f3fb8d78318"
)
V3_RESERVATION_ID = (
    "09de07440402fcd12996dcbe0ed67741973b2cd095cd60b43e77b764331d3b63"
)
V3_RESERVATION_POLICY_ID = "curry-unknown-reserve-seven-v1"
OLD_VALIDATION_MANIFEST_SHA256 = (
    "b170c35ff48fb4c22892ecffd15324cc7ecc5dfe318a7f1668b0f448756641c3"
)
OLD_VALIDATION_ORDINARY_CONFIG_SHA256 = (
    "d89c207ddc0370aa508067c5b86430504251034294b19caf16cc978355edfbce"
)
OLD_VALIDATION_TOURNAMENT_CONFIG_SHA256 = (
    "e481fa97a036e64687ce54c108ef979811601d11ee5f4b2c66c543f50b681822"
)
ABSENT_PROTECTION_SENTINEL = "absent-v1"
VERIFICATION_INPUT_ROLES = tuple(
    role for role in MANIFEST_INPUT_ROLES if role != "baseline_delivery"
) + ("baseline_acceptance", "consumption_reservation")
OPTION_REVALIDATION_INPUT_ROLES = tuple(
    role for role in MANIFEST_INPUT_ROLES if role != "baseline_delivery"
) + ("baseline_delivery", "baseline_recovery", "consumption_reservation")
OPTION_VERIFICATION_SCOPE = CurryScopeSpec(
    scope="curry-option-verification-v1",
    output_root=Path("data/runtime/p1-curry-option-verification-native-2026-10-25"),
    baseline_root=Path("data/runtime/p1-curry-consumption-reservation-v3-offline-2026-10-25"),
    limit=7,
    wall_seconds=7200,
    worker_timeout_seconds=30,
    old_consumed=32,
    batch_kind="curry-option-verification-v1",
    input_seal_kind="curry_option_verification_stage_input_seal",
    runner_role="curry_option_verification_runner",
    delivery_acceptance_sha256=V3_ACCEPTANCE_SHA256,
    baseline_acceptance_sha256=V3_ACCEPTANCE_SHA256,
    delivery_sha256="",
    report_prefix="native_curry_option_verification",
    candidate_config_root=CURRY_SCOPE.output_root,
    reservation_sha256=V3_RESERVATION_SHA256,
    reservation_id=V3_RESERVATION_ID,
    reservation_policy_id=V3_RESERVATION_POLICY_ID,
    certified_historical_consumed=32,
    policy_reserved=7,
    planning_base=39,
    reservation_relative=Path("reservation.json"),
    acceptance_relative=Path("delivery/acceptance.json"),
)
OPTION_REVALIDATION_SCOPE = CurryScopeSpec(
    scope="curry-option-revalidation-v1",
    output_root=Path("data/runtime/p1-curry-option-revalidation-native-2026-10-26"),
    baseline_root=Path("data/runtime/p1-curry-ledger-handoff-recovery-v3-offline-2026-10-26"),
    limit=7,
    wall_seconds=7200,
    worker_timeout_seconds=30,
    old_consumed=33,
    batch_kind="curry-option-revalidation-v1",
    input_seal_kind="curry_option_revalidation_stage_input_seal",
    runner_role="curry_option_revalidation_runner",
    delivery_acceptance_sha256="",
    delivery_sha256="dbc0db354846fdc772305970c90f7dbcee0d10804aded678845dd7bdaffd7a55",
    report_prefix="native_curry_option_revalidation",
    baseline_recovery_sha256="69d2af394169d5773394e775718840ef9a3df22eac12167d2e7ba3c79484c468",
    candidate_config_root=CURRY_SCOPE.output_root,
    reservation_sha256=V3_RESERVATION_SHA256,
    reservation_id=V3_RESERVATION_ID,
    reservation_policy_id=V3_RESERVATION_POLICY_ID,
    certified_historical_consumed=33,
    policy_reserved=7,
    planning_base=40,
    reservation_relative=Path("reservation.json"),
    acceptance_relative=Path("final-build/delivery-final.json"),
)


def _report_kind(spec: CurryScopeSpec, suffix: str) -> str:
    return f"{spec.report_prefix}_{suffix}"


def _uses_reservation_accounting(spec: CurryScopeSpec) -> bool:
    return spec.scope in (
        OPTION_VERIFICATION_SCOPE.scope,
        OPTION_REVALIDATION_SCOPE.scope,
    )


def _zero_call_count_valid(record: Any, spec: CurryScopeSpec) -> bool:
    """Validate zero-call accounting without changing legacy scope semantics."""
    native_calls = record.get("native_calls") if isinstance(record, dict) else None
    if _uses_reservation_accounting(spec):
        return type(native_calls) is int and native_calls == 0
    return native_calls == 0


def _reservation_stats_settled(stats: dict | None, spec: CurryScopeSpec) -> bool:
    """Return true only when a reservation ledger proves settled consumption."""
    return bool(
        _valid_stats(stats, spec)
        and stats["unknown"] == 0
        and stats["reserved"] == 0
        and stats["abandoned"] == 0
        and stats["consumed"] == stats["completed"]
    )


def _is_revalidation_scope(spec: CurryScopeSpec) -> bool:
    return spec.scope == OPTION_REVALIDATION_SCOPE.scope


def _verification_manifest_fields(spec: CurryScopeSpec) -> dict[str, Any]:
    """Return the fixed accounting and source fields for the verification manifest."""
    if spec.scope not in (
            OPTION_VERIFICATION_SCOPE.scope,
            OPTION_REVALIDATION_SCOPE.scope):
        raise ValueError("curry_verification_manifest_fields_scope_invalid")
    return {
        "certified_historical_consumed": spec.certified_historical_consumed,
        "policy_reserved": spec.policy_reserved,
        "planning_base": spec.planning_base,
        "reservation_id": spec.reservation_id,
        "reservation_policy_id": spec.reservation_policy_id,
        "consumption_reservation_sha256": spec.reservation_sha256,
    }


def _source_manifest_fields(spec: CurryScopeSpec) -> dict[str, str | None]:
    """Select exactly the source anchors belonging to one fixed Curry scope."""
    if spec.scope == CURRY_SCOPE.scope:
        return {
            "baseline_acceptance_sha256": BASELINE_ACCEPTANCE_SHA256,
            "baseline_delivery_sha256": spec.delivery_sha256,
        }
    if spec.scope == CONFIRMATION_SCOPE.scope:
        return {
            "baseline_audit_sha256": spec.baseline_audit_sha256,
            "baseline_delivery_sha256": spec.delivery_sha256,
        }
    if spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        return {"baseline_acceptance_sha256": spec.baseline_acceptance_sha256}
    if _is_revalidation_scope(spec):
        return {
            "baseline_delivery_sha256": spec.delivery_sha256,
            "baseline_recovery_sha256": spec.baseline_recovery_sha256,
        }
    raise ValueError("curry_scope_not_fixed")


def _manifest_roles(spec: CurryScopeSpec) -> tuple[str, ...]:
    if spec.scope == CURRY_SCOPE.scope:
        return MANIFEST_INPUT_ROLES
    if spec.scope == CONFIRMATION_SCOPE.scope:
        return CONFIRMATION_INPUT_ROLES
    if spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        return VERIFICATION_INPUT_ROLES
    if spec.scope == OPTION_REVALIDATION_SCOPE.scope:
        return OPTION_REVALIDATION_INPUT_ROLES
    raise ValueError("curry_scope_not_fixed")


def _pinned_inputs(spec: CurryScopeSpec) -> dict[str, str]:
    if spec.scope == CURRY_SCOPE.scope:
        return PINNED_INPUT_SHA256
    if spec.scope == CONFIRMATION_SCOPE.scope:
        if not spec.baseline_audit_sha256:
            raise ValueError("curry_confirmation_audit_anchor_missing")
        return {
            **PINNED_INPUT_SHA256,
            "baseline_delivery": spec.delivery_sha256,
            "baseline_audit": spec.baseline_audit_sha256,
        }
    if spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        if not spec.reservation_sha256 or not spec.delivery_acceptance_sha256:
            raise ValueError("curry_option_verification_reservation_anchor_missing")
        return {
            **PINNED_INPUT_SHA256,
            "baseline_acceptance": spec.delivery_acceptance_sha256,
            "consumption_reservation": spec.reservation_sha256,
        }
    if spec.scope == OPTION_REVALIDATION_SCOPE.scope:
        if (not spec.reservation_sha256 or not spec.delivery_sha256
                or not spec.baseline_recovery_sha256):
            raise ValueError("curry_option_revalidation_source_anchor_missing")
        return {
            **PINNED_INPUT_SHA256,
            "baseline_delivery": spec.delivery_sha256,
            "baseline_recovery": spec.baseline_recovery_sha256,
            "consumption_reservation": spec.reservation_sha256,
        }
    raise ValueError("curry_scope_not_fixed")


def _window_kind(spec: CurryScopeSpec) -> str:
    """Return the fixed serialized window kind without changing legacy bytes."""
    if spec.scope == CURRY_SCOPE.scope:
        return "curry_option_validation_window_start"
    if spec.scope == CONFIRMATION_SCOPE.scope:
        return "curry_option_confirmation_window_start"
    if spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        return "curry_option_verification_window_start"
    if spec.scope == OPTION_REVALIDATION_SCOPE.scope:
        return "curry_option_revalidation_window_start"
    raise ValueError("curry_scope_not_fixed")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Install the fixed Curry validation CLI arguments."""
    for name in (
        "baseline-dir", "preparation", "cases", "core-source", "runner",
        "worker", "build-record", "identity", "window-start", "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--verify-only", action="store_true")


def add_confirmation_arguments(parser: argparse.ArgumentParser) -> None:
    """Install the confirmation command using the same fixed path shape."""
    add_arguments(parser)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _case_encode(value: Any) -> bytes:
    import json

    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, indent=2).encode("utf-8") + b"\n"


def _replace_unique_card(values: Any, diagnostic: str) -> list[int]:
    if (not isinstance(values, list)
            or any(type(card) is not int for card in values)
            or values.count(85_138_716) != 1):
        raise ValueError(diagnostic)
    return [CURRY_CARD_ID if card == 85_138_716 else card for card in values]


def _derived_curry_case(rabbit_case: dict) -> dict:
    if not isinstance(rabbit_case, dict) or rabbit_case.get("case_id") != "rabbit":
        raise ValueError("curry_base_rabbit_case_invalid")
    result = copy.deepcopy(rabbit_case)
    result["case_id"] = "prompt-14-curry-v1"
    deck = result.get("deck")
    if not isinstance(deck, dict):
        raise ValueError("curry_base_request_deck_binding_invalid")
    deck["main"] = _replace_unique_card(
        deck.get("main"), "curry_base_request_deck_binding_invalid"
    )
    result["opening_hand"] = _replace_unique_card(
        result.get("opening_hand"), "curry_base_request_hand_binding_invalid"
    )
    information = result.get("information")
    opponent = information.get("opponent_resources") if isinstance(information, dict) else None
    if not isinstance(opponent, dict) or opponent.get("hand") != []:
        raise ValueError("curry_base_opponent_resources_invalid")
    opponent["main"] = _replace_unique_card(
        opponent.get("main"), "curry_base_opponent_deck_binding_invalid"
    )
    if result.get("seed") != 1:
        raise ValueError("curry_base_seed_mismatch")
    return result


def derive_curry_stage1_request(
    base_request: dict,
    rabbit_case: dict,
    candidate_case: dict,
    worker_path: str | Path,
) -> dict:
    """Derive the empty-decision Curry request from the frozen Rabbit request.

    Only the unique 85138716 in the deck/opening hand, decisions, and worker
    path may differ from the verified base request. The candidate case must
    independently equal the same card-substitution transform.
    """
    if not isinstance(base_request, dict) or not isinstance(rabbit_case, dict):
        raise ValueError("curry_base_request_invalid")
    if (not _strict_equal(base_request.get("deck"), rabbit_case.get("deck"))
            or not _strict_equal(base_request.get("opening_hand"), rabbit_case.get("opening_hand"))
            or base_request.get("seed") != rabbit_case.get("seed")
            or base_request.get("protocol_version") != 2
            or not isinstance(base_request.get("engine"), dict)
            or not isinstance(base_request.get("decisions"), list)):
        raise ValueError("curry_base_request_deck_binding_invalid")
    expected_case = _derived_curry_case(rabbit_case)
    if not _strict_equal(candidate_case, expected_case):
        raise ValueError("curry_candidate_case_not_rabbit_derivation")
    worker = str(worker_path)
    if not worker or "\x00" in worker:
        raise ValueError("curry_candidate_worker_path_invalid")
    derived = copy.deepcopy(base_request)
    derived["deck"] = copy.deepcopy(candidate_case["deck"])
    derived["opening_hand"] = copy.deepcopy(candidate_case["opening_hand"])
    derived["seed"] = candidate_case["seed"]
    derived["decisions"] = []
    derived["engine"]["worker_path"] = worker
    if (derived.get("deck") != candidate_case["deck"]
            or derived.get("opening_hand") != candidate_case["opening_hand"]):
        raise ValueError("curry_candidate_request_mismatch")
    return derived


def _source_file_sha256(sources: Any | None, path: Path, fallback: str) -> str:
    """Return an injected immutable source pin or the unchanged production pin."""
    return sources.file_sha256(path.as_posix()) if sources is not None else fallback


def _source_semantic_sha256(sources: Any | None, role: str, fallback: str) -> str:
    """Return the fixed semantic-object pin for tests or production defaults."""
    return sources.semantic_sha256(role) if sources is not None else fallback


def _source_dataset_count(sources: Any | None, name: str, fallback: int) -> int:
    """Resolve a pinned source count without changing the fixed scope contract."""
    return sources.dataset_count(name) if sources is not None else fallback


def _source_child(sources: Any | None, role: str) -> Any | None:
    return sources.child(role) if sources is not None else None


def _source_archive(sources: Any | None, role: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """Resolve archive provenance while preserving the default fixed anchor."""
    if sources is None:
        return fallback
    pin = sources.archive(role)
    return {
        "archive_sha256": pin.archive_sha256,
        "file_list_sha256": pin.file_list_sha256,
        "source_identity": pin.source_identity,
        "file_count": pin.file_count,
        "head": pin.head,
        "archive_path": pin.archive_path,
        "file_list_path": pin.file_list_path,
    }


def _confirmation_archive_source_scope(sources: Any | None) -> Any | None:
    """Resolve old Curry archive pins only from their dedicated source subtree."""
    return _source_child(sources, "asset_audit_scope") if sources is not None else None


def verify_curry_preparation(
    *, repo: Path,
    preparation: Path = PREPARATION_PATH,
    preparation_report: Path = PREPARATION_REPORT_PATH,
    preparation_acceptance: Path = PREPARATION_ACCEPTANCE_PATH,
    cases_path: Path = FROZEN_CASES_PATH,
    operations_source: Path | None = None,
    _sources: Any | None = None,
) -> dict:
    """Read-only recheck of the saved static Curry preparation and core pin."""
    repo = Path(repo).resolve()
    fixed_paths = {
        "preparation": repo / PREPARATION_PATH,
        "preparation_report": repo / PREPARATION_REPORT_PATH,
        "preparation_acceptance": repo / PREPARATION_ACCEPTANCE_PATH,
    }
    provided = {
        "preparation": Path(preparation).resolve(),
        "preparation_report": Path(preparation_report).resolve(),
        "preparation_acceptance": Path(preparation_acceptance).resolve(),
    }
    if provided != fixed_paths:
        raise ValueError("curry_fixed_preparation_paths_required")
    frozen_cases_path = Path(cases_path).resolve()
    if frozen_cases_path != (repo / FROZEN_CASES_PATH).resolve():
        raise ValueError("curry_fixed_frozen_cases_path_required")
    operations_path = Path(operations_source or repo / "data/tmp/ocgcore-source/operations.cpp").resolve()
    if operations_path != (repo / "data/tmp/ocgcore-source/operations.cpp").resolve():
        raise ValueError("curry_fixed_operations_source_required")

    before: dict[str, bytes] = {}
    for role, path in fixed_paths.items():
        before[role] = safe_path(path).read_bytes()
    before["operations_source"] = safe_path(operations_path).read_bytes()
    before["frozen_cases"] = safe_path(frozen_cases_path).read_bytes()
    _verify_frozen_cases_raw_binding(before["frozen_cases"], _sources=_sources)
    file_hashes = {role: _sha(before[role]) for role in (
        "preparation", "preparation_report", "preparation_acceptance", "operations_source"
    )}
    fixed_file_paths = {
        "preparation": PREPARATION_PATH,
        "preparation_report": PREPARATION_REPORT_PATH,
        "preparation_acceptance": PREPARATION_ACCEPTANCE_PATH,
        "operations_source": Path("data/tmp/ocgcore-source/operations.cpp"),
    }
    pinned_file_hashes = {
        role: _source_file_sha256(_sources, fixed_file_paths[role], PINNED_INPUT_SHA256[role])
        for role in file_hashes
    }
    if file_hashes != pinned_file_hashes:
        raise ValueError("curry_preparation_source_hash_mismatch")
    preparation_doc = strict_json(before["preparation"])
    report_doc = strict_json(before["preparation_report"])
    acceptance_doc = strict_json(before["preparation_acceptance"])
    candidates = [item for item in preparation_doc.get("candidates", [])
                  if isinstance(item, dict)
                  and isinstance(item.get("case"), dict)
                  and item["case"].get("case_id") == "prompt-14-curry-v1"]
    if len(candidates) != 1:
        raise ValueError("curry_preparation_candidate_not_unique")
    candidate = candidates[0]
    case = candidate["case"]
    derivation = candidate.get("request_derivation")
    if (not isinstance(derivation, dict)
            or derivation.get("base_request_sha256") != _source_semantic_sha256(
                _sources, "base_request", BASE_REQUEST_SHA256,
            )
            or derivation.get("case_sha256") != _source_semantic_sha256(
                _sources, "candidate_case", CANDIDATE_CASE_SHA256,
            )
            or derivation.get("hash_encoding") != "sorted-utf8-indent2-newline-v1"
            or derivation.get("replace_card") != {"from": 85_138_716, "to": CURRY_CARD_ID}
            or derivation.get("fixed_changes") != {"seed": 1}):
        raise ValueError("curry_preparation_derivation_mismatch")
    candidate_case_sha256 = _source_semantic_sha256(
        _sources, "candidate_case", CANDIDATE_CASE_SHA256,
    )
    base_request_sha256 = _source_semantic_sha256(
        _sources, "base_request", BASE_REQUEST_SHA256,
    )
    if _sha(_case_encode(case)) != candidate_case_sha256:
        raise ValueError("curry_preparation_case_hash_mismatch")
    frozen_cases = strict_json(before["frozen_cases"])
    rabbit_entries = [
        item for item in frozen_cases.get("cases", [])
        if isinstance(item, dict)
        and isinstance(item.get("case"), dict)
        and item["case"].get("case_id") == "rabbit"
    ]
    if len(rabbit_entries) != 1:
        raise ValueError("curry_frozen_rabbit_case_not_unique")
    rabbit_case = rabbit_entries[0]["case"]
    base_request = rabbit_entries[0].get("request")
    base_request_sha = _sha(_case_encode(base_request))
    if base_request_sha != base_request_sha256:
        raise ValueError("curry_frozen_base_request_hash_mismatch")
    if not isinstance(base_request, dict) or not isinstance(base_request.get("engine"), dict):
        raise ValueError("curry_frozen_base_request_invalid")
    derived_source_request = derive_curry_stage1_request(
        base_request, rabbit_case, case, base_request["engine"].get("worker_path", "")
    )
    deck = case.get("deck")
    if (not isinstance(deck, dict) or len(deck.get("main", [])) != 40
            or len(deck.get("extra", [])) != 3 or deck.get("side") != []
            or deck["main"].count(CURRY_CARD_ID) != 1
            or 85_138_716 in deck["main"]
            or case.get("opening_hand") != [CURRY_CARD_ID, 2_964_201,
                                             2_964_201, 2_964_201, 2_971_090]
            or case.get("seed") != 1):
        raise ValueError("curry_preparation_deck_or_hand_mismatch")
    information = case.get("information")
    opponent = information.get("opponent_resources") if isinstance(information, dict) else None
    if (not isinstance(opponent, dict) or opponent.get("hand") != []
            or opponent.get("main") != deck["main"]):
        raise ValueError("curry_opponent_resource_binding_mismatch")
    expected_target = {
        "opcode": 14,
        "descriptions": list(OPTION_DESCRIPTIONS),
        "player": 0,
        "responses": [
            {"choice": {"kind": "option", "index": 0}, "bytes": [0, 0, 0, 0]},
            {"choice": {"kind": "option", "index": 1}, "bytes": [1, 0, 0, 0]},
        ],
    }
    if (candidate.get("target") != {"card_id": CURRY_CARD_ID, "name": "curry", "opcode": 14}
            or candidate.get("expected_target") != expected_target
            or candidate.get("selector") != {"card_id": CURRY_CARD_ID,
                                               "command": 5, "opcode": 11,
                                               "player": 0, "unique": True}
            or candidate.get("execution_ready") is not False):
        raise ValueError("curry_preparation_target_or_qualification_mismatch")
    report_candidates = [item for item in report_doc.get("candidates", [])
                         if isinstance(item, dict)
                         and item.get("case_id") == "prompt-14-curry-v1"]
    accepted_candidates = [item for item in acceptance_doc.get("static_candidates", [])
                           if isinstance(item, dict)
                           and item.get("case_id") == "prompt-14-curry-v1"]
    if (len(report_candidates) != 1 or len(accepted_candidates) != 1
            or report_candidates[0].get("status") != "static_prepared"
            or report_candidates[0].get("execution_ready") is not False
            or accepted_candidates[0].get("case_sha256") != candidate_case_sha256
            or accepted_candidates[0].get("execution_ready") is not False
            or accepted_candidates[0].get("formal_release_status") != "unknown"):
        raise ValueError("curry_preparation_acceptance_mismatch")
    for role, path in {**fixed_paths, "operations_source": operations_path,
                        "frozen_cases": frozen_cases_path}.items():
        if safe_path(path).read_bytes() != before[role]:
            raise ValueError("curry_preparation_input_changed_during_capture")
    actual_hashes = {
        **file_hashes,
        "candidate_case": _sha(_case_encode(case)),
        "base_request": base_request_sha,
    }
    return {
        "candidate": copy.deepcopy(candidate),
        "candidate_case": copy.deepcopy(case),
        "rabbit_case": copy.deepcopy(rabbit_case),
        "base_request": copy.deepcopy(base_request),
        "base_request_entry": copy.deepcopy(rabbit_entries[0]),
        "stage1_request_template": derived_source_request,
        "frozen_cases_sha256": _sha(before["frozen_cases"]),
        "input_sha256": actual_hashes,
    }


def _verify_frozen_cases_raw_binding(raw: bytes, *, _sources: Any | None = None) -> str:
    """Bind the whole case-container file without changing manifest role hashes."""
    found = _sha(raw)
    if _sources is None:
        from ygo_eval.native_tenki_placement import FROZEN_CASES_SHA256

        expected = FROZEN_CASES_SHA256
    else:
        expected = _source_file_sha256(_sources, FROZEN_CASES_PATH, "")
    if found != expected:
        raise ValueError("curry_frozen_cases_file_hash_mismatch")
    return found


def _strict_equal(left: Any, right: Any) -> bool:
    """Compare JSON data while keeping bool distinct from integer values."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _bytes(value: Any, diagnostic: str) -> bytes:
    if (not isinstance(value, list)
            or any(type(byte) is not int or not 0 <= byte <= 255 for byte in value)):
        raise ValueError(diagnostic)
    return bytes(value)


def _event_prompt(event: Any, expected_opcode: int | None = None) -> tuple[dict, bytes]:
    """Bind a normalized prompt to the actual raw event frame."""
    from ygo_eval.native_tenki_placement_validation import _event_prompt as parse_event

    if not isinstance(event, dict):
        raise ValueError("curry_prompt_event_invalid")
    sequence = event.get("sequence")
    if type(sequence) is not int:
        raise ValueError("curry_prompt_sequence_invalid")
    prompt, raw, _actions = parse_event(event, sequence)
    if expected_opcode is not None and prompt.get("opcode") != expected_opcode:
        raise ValueError("curry_pending_opcode_unexpected")
    return prompt, raw


def _pending_prompt(result: dict, expected_opcode: int, *, curry_activation: bool = False) -> tuple[dict, bytes, dict]:
    from ygo_eval.native_tenki_placement_validation import _pending_prompt as pending

    prompt, raw, event = pending(result, expected_opcode)
    if curry_activation:
        _validate_curry_idle_event(event, prompt, require_candidate=True)
    return prompt, raw, event


def _decode_idle(raw: bytes) -> tuple[int, list[list[int]]]:
    """Decode opcode 11 command groups and retain command-5 card codes by slot."""
    if len(raw) < 2 or raw[0] != 11 or raw[1] not in (0, 1):
        raise ValueError("curry_idle_raw_header_invalid")
    pos = 2
    command_cards: list[list[int]] = []
    for command in range(6):
        if pos + 4 > len(raw):
            raise ValueError("curry_idle_raw_truncated")
        count = int.from_bytes(raw[pos:pos + 4], "little")
        pos += 4
        if count > 4096:
            raise ValueError("curry_idle_count_limit")
        cards: list[int] = []
        for _ in range(count):
            width = 10 + (9 if command == 5 else 0)
            if pos + width > len(raw):
                raise ValueError("curry_idle_raw_truncated")
            card_id = int.from_bytes(raw[pos:pos + 4], "little")
            pos += 10
            if command == 5:
                pos += 9
                cards.append(card_id)
        command_cards.append(cards)
    if pos + 3 != len(raw):
        raise ValueError("curry_idle_raw_length_invalid")
    if any(byte not in (0, 1) for byte in raw[pos:]):
        raise ValueError("curry_idle_flags_invalid")
    return raw[1], command_cards


def _validate_curry_idle_event(event: dict, prompt: dict, *, require_candidate: bool) -> None:
    raw = _bytes(event.get("raw"), "curry_idle_raw_invalid")
    if event.get("opcode") != 11:
        raise ValueError("curry_idle_event_opcode_mismatch")
    player, command_cards = _decode_idle(raw)
    if prompt.get("player") != player or player != 0:
        raise ValueError("curry_idle_player_mismatch")
    actions = prompt.get("actions")
    if not isinstance(actions, list):
        raise ValueError("curry_idle_actions_invalid")
    candidate_actions = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("curry_idle_action_invalid")
        choice = action.get("choice")
        if not isinstance(choice, dict) or choice.get("kind") != "command" or choice.get("command") != 5:
            continue
        index = choice.get("index")
        if (type(index) is not int or not 0 <= index < len(command_cards[5])
                or action.get("card_ids") != [command_cards[5][index]]
                or action.get("bytes") != [5, 0, index & 0xFF, (index >> 8) & 0xFF]):
            raise ValueError("curry_idle_command5_action_mismatch")
        if command_cards[5][index] == CURRY_CARD_ID:
            candidate_actions.append(action)
    if require_candidate and len(candidate_actions) != 1:
        raise ValueError("curry_activation_card_not_unique")


def _validate_all_event_support(events: Any) -> None:
    if not isinstance(events, list):
        raise ValueError("curry_result_events_missing")
    for event in events:
        if not isinstance(event, dict) or event.get("supported") is not True:
            raise ValueError("curry_result_contains_unsupported_event")
        raw = _bytes(event.get("raw"), "curry_event_raw_invalid")
        if not raw or type(event.get("opcode")) is not int or event["opcode"] != raw[0]:
            raise ValueError("curry_event_opcode_disagrees_with_raw")


def _validate_empty_protocol2_opponent_chain(event: dict, prompt: dict,
                                              raw: bytes) -> dict:
    """Return the sole fixed protocol-2 opponent pass action for an empty chain."""
    if (len(raw) != 16 or raw[:4] != bytes((16, 1, 0, 0))
            or raw[12:16] != bytes(4)
            or prompt.get("opcode") != 16 or prompt.get("player") != 1):
        raise ValueError("curry_protocol2_opponent_chain_not_empty_optional")
    actions = prompt.get("actions")
    expected_choice = {"kind": "chain", "index": None}
    expected_bytes = [255, 255, 255, 255]
    if (not isinstance(actions, list) or len(actions) != 1
            or actions[0].get("choice") != expected_choice
            or actions[0].get("bytes") != expected_bytes):
        raise ValueError("curry_protocol2_opponent_chain_response_invalid")
    return actions[0]


def _validate_decision_binding(requested: Any, resolved: Any, events: Any,
                               steps: Any) -> tuple[list[dict], list[int]]:
    """Bind decisions and protocol-2 opponent responses to ordered result steps.

    The worker records protocol-2 opponent policy choices in ``steps`` but
    intentionally omits them from ``resolved_decisions``. Only the fixed empty
    optional chain response is accepted as such an opponent step.
    """
    from ygo_eval.native_tenki_placement_validation import validate_auto_decisions

    if not isinstance(requested, list) or not isinstance(resolved, list):
        raise ValueError("curry_decisions_invalid")
    if not isinstance(events, list):
        raise ValueError("curry_result_events_missing")
    if not isinstance(steps, list):
        raise ValueError("curry_result_steps_missing")
    for decision in (*requested, *resolved):
        if (not isinstance(decision, dict) or type(decision.get("prompt_id")) is not int
                or type(decision.get("player")) is not int or decision.get("player") not in (0, 1)
                or not isinstance(decision.get("choice"), dict)):
            raise ValueError("curry_requested_decision_invalid")
    ids = [decision["prompt_id"] for decision in resolved]
    if len(ids) != len(set(ids)):
        raise ValueError("curry_resolved_decisions_duplicate")
    prompt_events = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("curry_prompt_event_invalid")
        raw = _bytes(event.get("raw"), "curry_event_raw_invalid")
        if raw and raw[0] in PROMPT_OPCODES:
            prompt, parsed_raw = _event_prompt(event)
            if parsed_raw != raw:
                raise ValueError("curry_prompt_event_raw_mismatch")
            prompt_events.append((event, prompt, raw))
    if (not prompt_events or len(steps) != len(prompt_events) - 1
            or [entry[1]["id"] for entry in prompt_events]
            != sorted(entry[1]["id"] for entry in prompt_events)):
        raise ValueError("curry_prompt_steps_order_mismatch")

    decision_by_id = {item["prompt_id"]: item for item in resolved}
    opponent_chain_ids: list[int] = []
    for index, (event, prompt, raw) in enumerate(prompt_events):
        prompt_id = prompt.get("id")
        if type(prompt_id) is not int or event.get("sequence") != prompt_id:
            raise ValueError("curry_prompt_event_sequence_invalid")
        decision = decision_by_id.get(prompt_id)
        is_pending = index == len(prompt_events) - 1
        if prompt.get("player") == 1:
            if decision is not None or is_pending:
                raise ValueError("curry_protocol2_opponent_decision_must_not_be_resolved")
            action = _validate_empty_protocol2_opponent_chain(event, prompt, raw)
            opponent_chain_ids.append(prompt_id)
        elif decision is None:
            if is_pending:
                if prompt.get("player") != 0:
                    raise ValueError("curry_pending_prompt_must_be_owned")
                continue
            raise ValueError("curry_resolved_own_prompt_missing_decision")
        else:
            if is_pending or decision.get("player") != prompt.get("player"):
                raise ValueError("curry_decision_prompt_binding_invalid")
            actions = prompt.get("actions")
            matches = [action for action in actions if isinstance(action, dict)
                       and _strict_equal(action.get("choice"), decision["choice"])]
            if len(matches) != 1:
                raise ValueError("curry_decision_choice_not_unique")
            action = matches[0]
        if not is_pending and not _strict_equal(steps[index], action):
            raise ValueError("curry_result_step_does_not_match_prompt")

    accounted_ids = set(ids) | set(opponent_chain_ids)
    actual_ids = [prompt["id"] for _event, prompt, _raw in prompt_events]
    if (len(actual_ids) != len(set(actual_ids))
            or any(prompt_id not in accounted_ids for prompt_id in actual_ids[:-1])
            or actual_ids[-1] in accounted_ids):
        raise ValueError("curry_prompt_event_accounting_mismatch")
    return validate_auto_decisions(requested, resolved, events), opponent_chain_ids


def _validate_prompt_event_accounting(
    requested: list[dict],
    auto_tail: list[dict],
    events: list[dict],
    pending_prompt_id: int,
    opponent_chain_ids: list[int] | None = None,
) -> None:
    """Require every supported prompt frame to have one protocol-2 trace role."""
    expected_ids = [item["prompt_id"] for item in (*requested, *auto_tail)]
    expected_ids.extend(opponent_chain_ids or [])
    expected_ids.append(pending_prompt_id)
    if (any(type(prompt_id) is not int for prompt_id in expected_ids)
            or len(expected_ids) != len(set(expected_ids))):
        raise ValueError("curry_prompt_event_accounting_mismatch")
    actual: list[int] = []
    for event in events:
        raw = _bytes(event.get("raw"), "curry_event_raw_invalid")
        if raw and raw[0] in PROMPT_OPCODES:
            sequence = event.get("sequence")
            if type(sequence) is not int:
                raise ValueError("curry_prompt_event_accounting_mismatch")
            actual.append(sequence)
    if actual != sorted(expected_ids):
        raise ValueError("curry_prompt_event_accounting_mismatch")


def _find_event(events: list, opcode: int) -> dict:
    matches = [event for event in events if isinstance(event, dict)
               and isinstance(event.get("raw"), list)
               and event["raw"] and event["raw"][0] == opcode]
    if not matches:
        raise ValueError("curry_required_event_missing")
    return matches[-1]


def _validate_option_prompt(event: dict, prompt: dict) -> None:
    prompt_id, normalized, _raw = _parse_option14(event)
    if prompt_id != prompt.get("id") or not _strict_equal(normalized, prompt):
        raise ValueError("curry_option_prompt_binding_mismatch")


def _validate_place_prompt(prompt: dict, raw: bytes) -> None:
    from ygo_eval.native_tenki_placement_validation import _validate_place_prompt as place_oracle

    place_oracle(prompt, raw)
    wanted = {"kind": "place", "zones": [{"player": 0, "location": 8, "sequence": 0}]}
    matches = [action for action in prompt["actions"]
               if _strict_equal(action.get("choice"), wanted)
               and action.get("bytes") == [0, 8, 0]]
    if len(matches) != 1:
        raise ValueError("curry_zone_zero_not_unique")


def _requested_option_decision(request: dict, option_frame: dict) -> dict:
    decisions = request.get("decisions") if isinstance(request, dict) else None
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("curry_option_decision_missing")
    matches = [item for item in decisions if isinstance(item, dict)
               and item.get("prompt_id") == option_frame.get("sequence")
               and isinstance(item.get("choice"), dict)
               and item["choice"].get("kind") == "option"]
    if len(matches) != 1:
        raise ValueError("curry_option_decision_not_unique")
    return matches[0]


def validate_curry_stage_receipt(
    receipt: dict,
    request: dict,
    context: str,
    stage: int,
    expected_identity: dict | None = None,
    spec: CurryScopeSpec = CURRY_SCOPE,
) -> list[dict]:
    """Validate one complete stage receipt and return its proven automatic tail."""
    if type(stage) is not int or stage not in range(1, spec.limit + 1):
        raise ValueError("curry_stage_number_invalid")
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("kind") != _report_kind(spec, "stage")
            or receipt.get("scope") != spec.scope or receipt.get("context") != context
            or receipt.get("stage") != stage or not _strict_equal(receipt.get("request"), request)
            or receipt.get("successful") is not True
            or any(receipt.get(flag) is not False for flag in FLAGS)):
        raise ValueError("curry_stage_receipt_binding_invalid")
    ledger = receipt.get("ledger")
    if not _strict_equal(ledger, {"consumed": stage, "completed": stage,
                                  "unknown": 0, "reserved": 0,
                                  "abandoned": 0, "limit": spec.limit}):
        raise ValueError("curry_stage_ledger_prefix_invalid")
    if (receipt.get("diagnostic") is not None
            or receipt.get("assets_unchanged") is not True
            or not isinstance(receipt.get("assets_before"), dict)
            or not isinstance(receipt.get("assets_after"), dict)
            or not _strict_equal(receipt.get("assets_before"), receipt.get("assets_after"))
            or (expected_identity is not None
                and not _strict_equal(receipt.get("assets_before"), expected_identity))
            or receipt.get("window_valid_at_result") is not True):
        raise ValueError("curry_stage_assets_or_window_invalid")
    validation = receipt.get("validation", {}).get("Ok", {})
    if (validation.get("response_oracle_matches") is not True
            or validation.get("automatic_decisions_single_legal") is not True):
        raise ValueError("curry_stage_response_or_auto_audit_failed")

    result = receipt.get("result", {}).get("Ok", {})
    if (result.get("status") != "decision_required" or result.get("error") is not None
            or result.get("coverage_gaps")):
        raise ValueError("curry_stage_result_not_clean_decision_required")
    events = result.get("events")
    _validate_all_event_support(events)
    requested = request.get("decisions") if isinstance(request, dict) else None
    resolved = result.get("resolved_decisions")
    auto_tail, opponent_chain_ids = _validate_decision_binding(
        requested, resolved, events, result.get("steps")
    )
    prompt, raw, pending_event = _pending_prompt(
        result, PENDING_OPCODE[stage], curry_activation=(stage == 1)
    )
    _validate_prompt_event_accounting(
        requested, auto_tail, events, prompt["id"], opponent_chain_ids
    )

    if stage == 1:
        if requested != []:
            raise ValueError("curry_stage1_must_be_empty_prefix")
        _validate_curry_idle_event(pending_event, prompt, require_candidate=True)
    elif stage == 2:
        _validate_place_prompt(prompt, raw)
    elif stage == 3:
        _validate_option_prompt(pending_event, prompt)
    else:
        option_frame = _find_event(events, 14)
        option_decision = _requested_option_decision(request, option_frame)
        checkpoint = result.get("checkpoint")
        validate_curry_option_result(
            option_frame, option_decision, events, checkpoint, pending_event=pending_event,
        )
        if stage in (4, 6):
            if prompt.get("opcode") != 11:
                raise ValueError("curry_post_option_idle_required")
            _validate_curry_idle_event(pending_event, prompt, require_candidate=False)

    replay = receipt.get("independent_replay_matches")
    if stage in (5, 7):
        if replay is not True:
            raise ValueError("curry_independent_replay_mismatch")
    elif replay is not None:
        raise ValueError("curry_unexpected_replay_qualification")
    return auto_tail


def _validated_parent(parent: dict, stage: int, spec: CurryScopeSpec) -> tuple[dict, dict]:
    parent_stage = PARENT_STAGE.get(stage)
    if parent_stage is None or not isinstance(parent, dict):
        raise ValueError("curry_stage_derivation_invalid")
    request = parent.get("request")
    context = parent.get("context")
    if not isinstance(request, dict) or not isinstance(context, str):
        raise ValueError("curry_stage_parent_binding_missing")
    validate_curry_stage_receipt(parent, request, context, parent_stage,
                                 parent.get("assets_before"), spec)
    return request, parent["result"]["Ok"]


def derive_curry_stage_request(stage: int, parent: dict,
                               spec: CurryScopeSpec = CURRY_SCOPE) -> dict:
    """Derive one immutable child request from its fixed, authenticated parent."""
    request, result = _validated_parent(parent, stage, spec)
    if stage in (5, 7):
        return copy.deepcopy(request)
    resolved = result.get("resolved_decisions")
    if not isinstance(resolved, list):
        raise ValueError("curry_parent_resolved_decisions_missing")
    if stage == 2:
        prompt, raw, _event = _pending_prompt(
            result, 11, curry_activation=True
        )
        _validate_curry_idle_event(
            {"raw": list(raw), "opcode": 11}, prompt, require_candidate=True
        )
        matches = []
        for action in prompt["actions"]:
            choice = action.get("choice") if isinstance(action, dict) else None
            if (isinstance(choice, dict) and choice.get("kind") == "command"
                    and choice.get("command") == 5 and action.get("card_ids") == [CURRY_CARD_ID]):
                expected_bytes = [5, 0, choice.get("index", -1) & 0xFF,
                                  (choice.get("index", -1) >> 8) & 0xFF]
                if action.get("bytes") == expected_bytes:
                    matches.append(action)
        if len(matches) != 1:
            raise ValueError("curry_activation_card_not_unique")
    elif stage == 3:
        prompt, raw, _event = _pending_prompt(result, 18)
        _validate_place_prompt(prompt, raw)
        wanted = {"kind": "place", "zones": [{"player": 0,
                  "location": 8, "sequence": 0}]}
        matches = [action for action in prompt["actions"]
                   if _strict_equal(action.get("choice"), wanted)
                   and action.get("bytes") == [0, 8, 0]]
        if len(matches) != 1:
            raise ValueError("curry_zone_zero_not_unique")
    elif stage in (4, 6):
        prompt, _raw, option_frame = _pending_prompt(result, 14)
        _validate_option_prompt(option_frame, prompt)
        index = 0 if stage == 4 else 1
        wanted = {"kind": "option", "index": index}
        expected_bytes = [index, 0, 0, 0]
        matches = [action for action in prompt["actions"]
                   if _strict_equal(action.get("choice"), wanted)
                   and action.get("bytes") == expected_bytes]
        if len(matches) != 1:
            raise ValueError("curry_option_choice_not_unique")
    else:
        raise ValueError("curry_stage_derivation_invalid")
    child = copy.deepcopy(request)
    child["decisions"] = copy.deepcopy(resolved) + [{
        "prompt_id": prompt["id"],
        "player": 0,
        "choice": copy.deepcopy(matches[0]["choice"]),
    }]
    return child


def _valid_stats(stats: Any, spec: CurryScopeSpec = CURRY_SCOPE) -> bool:
    return (
        isinstance(stats, dict)
        and all(type(stats.get(key)) is int and stats[key] >= 0 for key in (
            "consumed", "completed", "unknown", "reserved", "abandoned", "limit"
        ))
        and stats["limit"] == spec.limit
        and stats["consumed"] == stats["completed"] + stats["unknown"]
        and stats["abandoned"] <= stats["unknown"]
        and stats["consumed"] + stats["reserved"] <= spec.limit
    )


def _valid_stage_summary(item: Any, stage: int, spec: CurryScopeSpec) -> bool:
    if (not isinstance(item, dict) or item.get("stage") != stage
            or type(item.get("successful")) is not bool
            or (item["successful"] and item.get("native_calls") != 1)
            or (item.get("native_calls") is not None
                and (type(item["native_calls"]) is not int or item["native_calls"] not in (0, 1)))
            or not isinstance(item.get("diagnostic_sha256"), str)
            or not HASH.fullmatch(item["diagnostic_sha256"])
            or (item.get("receipt_sha256") is not None
                and (not isinstance(item.get("receipt_sha256"), str)
                     or not HASH.fullmatch(item["receipt_sha256"])) )):
        return False
    replay = item.get("independent_replay_matches")
    if stage in (5, 7):
        if item["successful"] is True and replay is not True:
            return False
        if (item["successful"] is not True
                and replay is not None and type(replay) is not bool):
            return False
    elif replay is not None:
        return False
    ledger = item.get("ledger")
    if item["successful"]:
        if (item.get("native_calls") != 1 or item.get("diagnostic") is not None
                or item.get("receipt_sha256") is None or not _valid_stats(ledger, spec)
                or ledger["consumed"] != stage or ledger["completed"] != stage):
            return False
    elif ledger is not None and (not _valid_stats(ledger, spec)
                                 or ledger.get("consumed", spec.limit + 1) > stage):
        return False
    return True


def summarize_curry_validation(context: str, stages: list[dict], stats: dict | None,
                               diagnostic: str | None = None,
                               spec: CurryScopeSpec = CURRY_SCOPE) -> dict:
    stats_valid = _valid_stats(stats, spec)
    ordered = isinstance(stages, list) and [item.get("stage") for item in stages] == list(
        range(1, len(stages) + 1)
    )
    stage_success = bool(ordered and len(stages) == spec.limit
                        and all(_valid_stage_summary(item, number, spec)
                                for number, item in enumerate(stages, 1))
                        and all(item.get("successful") is True for item in stages))
    if not stats_valid:
        diagnostic = diagnostic or "ledger_statistics_unknown_or_invalid"
    elif stats["unknown"] or stats["reserved"] or stats["abandoned"]:
        diagnostic = diagnostic or "ledger_has_unresolved_consumption"
    successful = bool(stage_success and stats_valid and diagnostic is None
                      and stats["consumed"] == stats["completed"] == spec.limit
                      and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0)
    if _uses_reservation_accounting(spec):
        certified = spec.certified_historical_consumed
        reserved = spec.policy_reserved
        planning = spec.planning_base
        if certified is None or reserved is None or planning is None:
            raise ValueError("curry_option_verification_accounting_spec_missing")
        known_consumed = (
            stats["consumed"] if _reservation_stats_settled(stats, spec) else None
        )
        return {
            "schema_version": 1,
            "kind": _report_kind(spec, "summary"),
            "scope": spec.scope,
            "context": context,
            "certified_historical_consumed": certified,
            "policy_reserved": reserved,
            "planning_base": planning,
            "reservation_id": spec.reservation_id,
            "reservation_policy_id": spec.reservation_policy_id,
            "new_consumed": known_consumed,
            "certified_consumed_including_new": (
                certified + known_consumed if known_consumed is not None else None
            ),
            "planning_total": planning + known_consumed if known_consumed is not None else None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
            "unknown": stats["unknown"] if stats_valid else None,
            "ledger": copy.deepcopy(stats) if stats_valid else None,
            "stages": copy.deepcopy(stages),
            "diagnostic": diagnostic,
            "successful": successful,
            **FLAGS,
        }
    known_consumed = stats["consumed"] if stats_valid else None
    return {
        "schema_version": 1,
        "kind": _report_kind(spec, "summary"),
        "scope": spec.scope,
        "context": context,
        "old_consumed": spec.old_consumed,
        "new_consumed": known_consumed,
        "cumulative_consumed": (spec.old_consumed + known_consumed
                                 if known_consumed is not None else None),
        "unknown": stats["unknown"] if stats_valid else None,
        "ledger": copy.deepcopy(stats) if stats_valid else None,
        "stages": copy.deepcopy(stages),
        "diagnostic": diagnostic,
        "successful": successful,
        **FLAGS,
    }


def validate_curry_report(value: dict, repo: Path | None = None,
                          spec: CurryScopeSpec = CURRY_SCOPE,
                          *, _sources: Any | None = None) -> bool:
    """Apply strict Curry-local invariants; published JSON Schema is separate."""
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1 or value.get("scope") != spec.scope):
        raise ValueError("curry_report_scope_or_version_invalid")
    if any(value.get(flag) is not False for flag in FLAGS):
        raise ValueError("curry_qualification_must_remain_false")
    context = value.get("context")
    if not isinstance(context, str) or not HASH.fullmatch(context):
        raise ValueError("curry_report_context_invalid")
    kind = value.get("kind")
    allowed = {_report_kind(spec, suffix) for suffix in (
        "manifest", "prepared", "stage", "stage_report", "summary", "verification",
    )}
    if kind not in allowed:
        raise ValueError("curry_report_kind_invalid")
    if kind.endswith("_manifest"):
        unsigned = {key: item for key, item in value.items() if key != "context"}
        source_baseline_delivery = spec.delivery_sha256
        source_baseline_audit = spec.baseline_audit_sha256
        source_baseline_recovery = spec.baseline_recovery_sha256
        source_baseline_acceptance = (
            spec.baseline_acceptance_sha256
            if spec.baseline_acceptance_sha256 is not None
            else spec.delivery_acceptance_sha256
        )
        if _sources is not None:
            if spec.scope == CONFIRMATION_SCOPE.scope:
                asset_sources = _sources.child("asset_audit")
                source_baseline_delivery = asset_sources.file_sha256_role("asset_audit_delivery")
                source_baseline_audit = asset_sources.file_sha256_role("asset_audit_audit")
            elif spec.scope == OPTION_VERIFICATION_SCOPE.scope:
                source_node = _sources.child("option_verification_scope")
                source_baseline_acceptance = source_node.file_sha256_role(
                    "baseline_acceptance",
                )
            elif _is_revalidation_scope(spec):
                source_node = _sources.child("option_revalidation_scope")
                source_baseline_delivery = source_node.file_sha256_role("baseline_delivery")
                source_baseline_recovery = source_node.file_sha256_role("baseline_recovery")
            elif spec.scope == CURRY_SCOPE.scope:
                source_node = _sources.child("validation_candidate_scope")
                source_baseline_acceptance = source_node.file_sha256_role(
                    "baseline_acceptance",
                )
                source_baseline_delivery = source_node.file_sha256_role(
                    "baseline_delivery",
                )
                source_baseline_audit = source_node.file_sha256_role("baseline_audit")
            else:
                raise ValueError("source_description_curry_scope_unsupported")
        verification_source_fields_match = (
            value.get("baseline_acceptance_sha256") == source_baseline_acceptance
            and "baseline_delivery_sha256" not in value
            and "baseline_audit_sha256" not in value
                and "baseline_recovery_sha256" not in value
            and value.get("certified_historical_consumed") == spec.certified_historical_consumed
            and value.get("policy_reserved") == spec.policy_reserved
            and value.get("planning_base") == spec.planning_base
            and value.get("reservation_id") == spec.reservation_id
            and value.get("reservation_policy_id") == spec.reservation_policy_id
            and value.get("consumption_reservation_sha256") == spec.reservation_sha256
            and "old_consumed" not in value
        )
        revalidation_source_fields_match = (
            value.get("baseline_delivery_sha256") == source_baseline_delivery
            and value.get("baseline_recovery_sha256") == (
                source_baseline_recovery if _sources is not None
                else spec.baseline_recovery_sha256
            )
            and value.get("consumption_reservation_sha256") == spec.reservation_sha256
            and value.get("certified_historical_consumed") == spec.certified_historical_consumed
            and value.get("policy_reserved") == spec.policy_reserved
            and value.get("planning_base") == spec.planning_base
            and value.get("reservation_id") == spec.reservation_id
            and value.get("reservation_policy_id") == spec.reservation_policy_id
            and "baseline_acceptance_sha256" not in value
                and "baseline_audit_sha256" not in value
            and "old_consumed" not in value
        )
        if (value.get("batch_kind") != spec.batch_kind
                or type(value.get("started_at")) is not int or value["started_at"] < 0
                or value.get("limit") != spec.limit or value.get("planned_calls") != spec.limit
                or value.get("wall_seconds") != spec.wall_seconds
                or (not _uses_reservation_accounting(spec)
                    and value.get("old_consumed") != spec.old_consumed)
                or (spec.scope == CURRY_SCOPE.scope
                    and value.get("baseline_acceptance_sha256") != source_baseline_acceptance)
                or (spec.scope == CONFIRMATION_SCOPE.scope
                    and ("baseline_acceptance_sha256" in value
                         or value.get("baseline_audit_sha256") != source_baseline_audit))
                or (spec.scope not in (OPTION_VERIFICATION_SCOPE.scope,
                                       OPTION_REVALIDATION_SCOPE.scope)
                    and value.get("baseline_delivery_sha256") != source_baseline_delivery)
                or (spec.scope == OPTION_VERIFICATION_SCOPE.scope
                    and not verification_source_fields_match)
                or (_is_revalidation_scope(spec)
                    and not revalidation_source_fields_match)
                or value.get("request_derivation") != (
                    "frozen-prompt-14-curry-v1-worker-path-replaced"
                )
                or value.get("historical_source_transition") != HISTORICAL_SOURCE_TRANSITION
                or value.get("context") != hashlib.sha256(canonical(unsigned)).hexdigest()
                or not isinstance(value.get("request"), dict)
                or value["request"].get("protocol_version") != 2
                or value["request"].get("seed") != 1
                or value["request"].get("decisions") != []
                or not isinstance(value["request"].get("engine"), dict)
                or not isinstance(value.get("source"), dict)
                or not isinstance(value.get("build"), dict)
                or not isinstance(value.get("assets"), dict)
                or value.get("stage1_request_sha256") != hashlib.sha256(
                    canonical(value["request"])
                ).hexdigest()):
            raise ValueError("curry_manifest_binding_invalid")
        input_hashes = value.get("input_sha256")
        roles = _manifest_roles(spec)
        pinned = _pinned_inputs(spec)
        if _sources is not None:
            if spec.scope == OPTION_VERIFICATION_SCOPE.scope:
                source_node = _sources.child("option_verification_scope")
                pinned = {
                    role: (
                        source_node.semantic_sha256(f"manifest_{role}")
                        if role in {"base_request", "candidate_case"}
                        else source_node.file_sha256_role(f"manifest_input_{role}")
                    )
                    for role in _manifest_roles(spec)
                    if role not in {"baseline_acceptance", "consumption_reservation"}
                }
                pinned["baseline_acceptance"] = source_node.file_sha256_role(
                    "baseline_acceptance",
                )
                pinned["consumption_reservation"] = source_node.file_sha256_role(
                    "consumption_reservation",
                )
            elif _is_revalidation_scope(spec):
                source_node = _sources.child("option_revalidation_scope")
                pinned = {
                    role: (
                        source_node.semantic_sha256(f"manifest_{role}")
                        if role in {"base_request", "candidate_case"}
                        else source_node.file_sha256_role(f"manifest_input_{role}")
                    )
                    for role in _manifest_roles(spec)
                    if role not in {
                        "baseline_delivery", "baseline_recovery",
                        "consumption_reservation",
                    }
                }
                pinned["baseline_delivery"] = source_node.file_sha256_role(
                    "baseline_delivery",
                )
                pinned["baseline_recovery"] = source_node.file_sha256_role(
                    "baseline_recovery",
                )
                pinned["consumption_reservation"] = source_node.file_sha256_role(
                    "consumption_reservation",
                )
            elif spec.scope == CURRY_SCOPE.scope:
                source_node = _sources.child("validation_candidate_scope")
                pinned = {
                    role: (
                        source_node.semantic_sha256(f"manifest_{role}")
                        if role in {"base_request", "candidate_case"}
                        else source_node.file_sha256_role(f"manifest_input_{role}")
                    )
                    for role in _manifest_roles(spec)
                }
                pinned["baseline_delivery"] = source_baseline_delivery
            else:
                static_sources = _sources.child("static_preparation")
                pinned = {
                    "preparation": static_sources.file_sha256_role("preparation"),
                    "preparation_report": static_sources.file_sha256_role("preparation_report"),
                    "preparation_acceptance": static_sources.file_sha256_role("preparation_acceptance"),
                    "candidate_case": static_sources.semantic_sha256("candidate_case"),
                    "base_request": static_sources.semantic_sha256("base_request"),
                    "operations_source": static_sources.file_sha256_role("operations_source"),
                    "adapter_codec": static_sources.file_sha256_role("adapter_codec"),
                    "baseline_delivery": source_baseline_delivery,
                    "baseline_audit": source_baseline_audit,
                }
        if (not isinstance(input_hashes, dict)
                or set(input_hashes) != set(roles)
                or any(not isinstance(item, str) or not HASH.fullmatch(item)
                       for item in input_hashes.values())
                or any(input_hashes.get(role) != expected
                       for role, expected in pinned.items())
                or (spec.scope not in (OPTION_VERIFICATION_SCOPE.scope,
                                       OPTION_REVALIDATION_SCOPE.scope)
                    and input_hashes.get("baseline_delivery") != source_baseline_delivery)
                or (spec.scope == CONFIRMATION_SCOPE.scope
                    and input_hashes.get("baseline_audit") != source_baseline_audit)
                or (spec.scope == OPTION_VERIFICATION_SCOPE.scope
                    and (input_hashes.get("baseline_acceptance") != source_baseline_acceptance
                         or input_hashes.get("consumption_reservation") != spec.reservation_sha256))
                or (_is_revalidation_scope(spec)
                    and (input_hashes.get("baseline_delivery") != spec.delivery_sha256
                         or input_hashes.get("baseline_recovery") != spec.baseline_recovery_sha256
                         or input_hashes.get("consumption_reservation") != spec.reservation_sha256))):
            raise ValueError("curry_manifest_input_hashes_invalid")
    elif kind.endswith("_prepared"):
        if (type(value.get("prepared")) is not bool
                or type(value.get("execution_ready")) is not bool
                or (value["execution_ready"] and not value["prepared"])
                or not _zero_call_count_valid(value, spec)
                or value.get("planned_calls") != spec.limit
                or not HASH.fullmatch(str(value.get("manifest_sha256", "")))
                or not HASH.fullmatch(str(value.get("stage1_request_sha256", "")))
                or not HASH.fullmatch(str(value.get("stage1_input_sha256", "")))
                or not HASH.fullmatch(str(value.get("preflight_diagnostic_sha256", "")))
                or ("diagnostics" in value
                    and (not isinstance(value["diagnostics"], list)
                         or any(not isinstance(item, str) for item in value["diagnostics"])))):
            raise ValueError("curry_prepared_binding_invalid")
    elif kind.endswith("_stage") and not kind.endswith("_stage_report"):
        stage = value.get("stage")
        if (type(stage) is not int or stage not in range(1, spec.limit + 1)
                or type(value.get("successful")) is not bool
                or not isinstance(value.get("request"), dict)
                or not _valid_stats(value.get("ledger"), spec)
                or not isinstance(value.get("assets_before"), dict)
                or (value.get("assets_after") is not None
                    and not isinstance(value.get("assets_after"), dict))
                or (value.get("successful") is True
                    and not isinstance(value.get("assets_after"), dict))
                or type(value.get("assets_unchanged")) is not bool
                or type(value.get("window_valid_at_result")) is not bool
                or not isinstance(value.get("validation"), dict)
                or not isinstance(value.get("result"), dict)):
            raise ValueError("curry_stage_report_fields_invalid")
        if value["successful"]:
            validate_curry_stage_receipt(
                value, value["request"], context, stage,
                value.get("assets_before"), spec,
            )
    elif kind.endswith("_stage_report"):
        stage = value.get("stage")
        if (type(stage) is not int or stage not in range(1, spec.limit + 1)
                or type(value.get("successful")) is not bool
                or (value.get("native_calls") is not None
                    and (type(value["native_calls"]) is not int
                         or value["native_calls"] not in (0, 1)))
                or not HASH.fullmatch(str(value.get("diagnostic_sha256", "")))
                or (value.get("receipt_sha256") is not None
                    and not HASH.fullmatch(str(value["receipt_sha256"])))
                or ("diagnostic" in value
                    and value["diagnostic"] is not None
                    and not isinstance(value["diagnostic"], str))
                or (value.get("ledger") is not None
                    and not _valid_stats(value.get("ledger"), spec))):
            raise ValueError("curry_stage_report_fields_invalid")
        if value["successful"] and (
            value.get("native_calls") != 1 or value.get("diagnostic") is not None
            or not isinstance(value.get("receipt_sha256"), str)
            or value.get("ledger") is None
        ):
            raise ValueError("curry_successful_stage_report_invalid")
        replay = value.get("independent_replay_matches")
        if stage in (5, 7):
            if value["successful"] and replay is not True:
                raise ValueError("curry_replay_report_invalid")
            if (not value["successful"]
                    and replay is not None and type(replay) is not bool):
                raise ValueError("curry_replay_report_invalid")
        elif replay is not None:
            raise ValueError("curry_unexpected_replay_report")
    elif kind.endswith("_summary"):
        if (type(value.get("successful")) is not bool
                or not isinstance(value.get("stages"), list)
                or len(value["stages"]) > spec.limit):
            raise ValueError("curry_summary_fields_invalid")
        if _uses_reservation_accounting(spec):
            if (value.get("certified_historical_consumed") != spec.certified_historical_consumed
                    or value.get("policy_reserved") != spec.policy_reserved
                    or value.get("planning_base") != spec.planning_base
                    or value.get("reservation_id") != spec.reservation_id
                    or value.get("reservation_policy_id") != spec.reservation_policy_id
                    or "old_confirmation_actual_consumed" not in value
                    or value["old_confirmation_actual_consumed"] is not None
                    or "actual_all_history_cumulative" not in value
                    or value["actual_all_history_cumulative"] is not None
                    or "old_consumed" in value or "cumulative_consumed" in value):
                raise ValueError("curry_verification_accounting_basis_invalid")
        elif value.get("old_consumed") != spec.old_consumed:
            raise ValueError("curry_summary_fields_invalid")
        for index, stage in enumerate(value["stages"], 1):
            if not _valid_stage_summary(stage, index, spec):
                raise ValueError("curry_summary_stage_invalid")
        ledger = value.get("ledger")
        if ledger is not None and not _valid_stats(ledger, spec):
            raise ValueError("curry_summary_ledger_invalid")
        if _uses_reservation_accounting(spec):
            if ledger is None:
                if any(value.get(key) is not None for key in (
                        "new_consumed", "certified_consumed_including_new",
                        "planning_total", "unknown")):
                    raise ValueError("curry_summary_unknown_ledger_must_not_claim_stats")
            elif _reservation_stats_settled(ledger, spec):
                if (type(value.get("new_consumed")) is not int
                        or value.get("new_consumed") != ledger["consumed"]
                        or type(value.get("certified_consumed_including_new")) is not int
                        or value.get("certified_consumed_including_new") != (
                            spec.certified_historical_consumed + ledger["consumed"]
                        )
                        or type(value.get("planning_total")) is not int
                        or value.get("planning_total") != spec.planning_base + ledger["consumed"]
                        or type(value.get("unknown")) is not int
                        or value.get("unknown") != ledger["unknown"]):
                    raise ValueError("curry_summary_consumption_binding_invalid")
            elif (any(value.get(key) is not None for key in (
                          "new_consumed", "certified_consumed_including_new", "planning_total"))
                  or type(value.get("unknown")) is not int
                  or value.get("unknown") != ledger["unknown"]):
                raise ValueError("curry_summary_unsettled_ledger_must_not_claim_totals")
        elif ledger is None:
            if any(value.get(key) is not None for key in (
                    "new_consumed", "cumulative_consumed", "unknown")):
                raise ValueError("curry_summary_unknown_ledger_must_not_claim_stats")
        elif (value.get("new_consumed") != ledger["consumed"]
              or value.get("cumulative_consumed") != spec.old_consumed + ledger["consumed"]
              or value.get("unknown") != ledger["unknown"]):
            raise ValueError("curry_summary_consumption_binding_invalid")
        if value["successful"]:
            recomputed = summarize_curry_validation(
                context, value["stages"], ledger, spec=spec,
            )
            if not _strict_equal(recomputed, value):
                raise ValueError("curry_summary_success_not_proven")
    elif kind.endswith("_verification"):
        if (type(value.get("valid")) is not bool
                or not _zero_call_count_valid(value, spec)
                or not isinstance(value.get("stages"), list)
                or len(value["stages"]) > spec.limit
                or not isinstance(value.get("prepared_sha256"), str)
                or not HASH.fullmatch(value["prepared_sha256"])):
            raise ValueError("curry_verification_fields_invalid")
        for index, stage in enumerate(value["stages"], 1):
            if not _valid_stage_summary(stage, index, spec):
                raise ValueError("curry_verification_stage_invalid")
        ledger = value.get("ledger")
        hashes = value.get("verification_diagnostic_sha256")
        if (not isinstance(hashes, list)
                or len(hashes) != len(value["stages"])
                or any(not isinstance(item, str) or not HASH.fullmatch(item)
                       for item in hashes)):
            raise ValueError("curry_verification_diagnostic_binding_invalid")
        if _uses_reservation_accounting(spec):
            if (value.get("certified_historical_consumed") != spec.certified_historical_consumed
                    or value.get("policy_reserved") != spec.policy_reserved
                    or value.get("planning_base") != spec.planning_base
                    or value.get("reservation_id") != spec.reservation_id
                    or value.get("reservation_policy_id") != spec.reservation_policy_id
                    or "old_confirmation_actual_consumed" not in value
                    or value["old_confirmation_actual_consumed"] is not None
                    or "actual_all_history_cumulative" not in value
                    or value["actual_all_history_cumulative"] is not None
                    or "old_consumed" in value or "cumulative_consumed" in value):
                raise ValueError("curry_verification_accounting_basis_invalid")
            if ledger is None:
                if any(value.get(key) is not None for key in (
                        "new_consumed", "certified_consumed_including_new",
                        "planning_total", "unknown")):
                    raise ValueError("curry_verification_unknown_ledger_must_not_claim_stats")
            elif not _valid_stats(ledger, spec):
                raise ValueError("curry_verification_consumption_binding_invalid")
            elif _reservation_stats_settled(ledger, spec):
                if (type(value.get("new_consumed")) is not int
                        or value.get("new_consumed") != ledger["consumed"]
                        or type(value.get("certified_consumed_including_new")) is not int
                        or value.get("certified_consumed_including_new") != (
                            spec.certified_historical_consumed + ledger["consumed"]
                        )
                        or type(value.get("planning_total")) is not int
                        or value.get("planning_total") != spec.planning_base + ledger["consumed"]
                        or type(value.get("unknown")) is not int
                        or value.get("unknown") != ledger["unknown"]):
                    raise ValueError("curry_verification_consumption_binding_invalid")
            elif (any(value.get(key) is not None for key in (
                          "new_consumed", "certified_consumed_including_new", "planning_total"))
                  or type(value.get("unknown")) is not int
                  or value.get("unknown") != ledger["unknown"]):
                raise ValueError("curry_verification_unsettled_ledger_must_not_claim_totals")
        elif ledger is None:
            if any(value.get(key) is not None for key in (
                    "new_consumed", "cumulative_consumed", "unknown")):
                raise ValueError("curry_verification_unknown_ledger_must_not_claim_stats")
        elif (not _valid_stats(ledger, spec)
              or value.get("new_consumed") != ledger["consumed"]
              or value.get("cumulative_consumed") != spec.old_consumed + ledger["consumed"]
              or value.get("unknown") != ledger["unknown"]):
            raise ValueError("curry_verification_consumption_binding_invalid")
        if value["valid"]:
            if (ledger is None or ledger["consumed"] != spec.limit
                    or ledger["completed"] != spec.limit
                    or any(ledger[key] != 0 for key in ("unknown", "reserved", "abandoned"))
                    or len(value["stages"]) != spec.limit
                    or not all(stage.get("successful") is True
                               for stage in value["stages"])
                    or value.get("diagnostic") is not None):
                raise ValueError("curry_verification_success_not_proven")
        elif (not isinstance(value.get("diagnostic"), str)
              or not value["diagnostic"]):
            raise ValueError("curry_verification_failure_diagnostic_missing")
    return True


def _stage_report(context: str, stage: int, receipt: dict | None,
                  receipt_path: Path, diagnostic_sha: str,
                  native_calls: int | None, reason: str | None,
                  fallback_ledger: dict | None = None,
                  spec: CurryScopeSpec = CURRY_SCOPE) -> dict:
    receipt_sha = (_sha(safe_path(receipt_path).read_bytes())
                   if receipt_path.is_file() else None)
    replay = receipt.get("independent_replay_matches") if isinstance(receipt, dict) else None
    report = {
        "schema_version": 1,
        "kind": _report_kind(spec, "stage_report"),
        "scope": spec.scope,
        "context": context,
        "stage": stage,
        "successful": bool(receipt and receipt.get("successful") is True and reason is None),
        "native_calls": native_calls,
        "diagnostic": reason,
        "receipt_sha256": receipt_sha,
        "diagnostic_sha256": diagnostic_sha,
        "independent_replay_matches": replay if type(replay) is bool else None,
        "ledger": receipt.get("ledger") if isinstance(receipt, dict) else fallback_ledger,
        **FLAGS,
    }
    validate_curry_report(report, spec=spec)
    return report


def _stage_report_matches_receipt(
    report: dict, receipt: dict, *, stage: int, previous_consumed: int,
    process_record: dict, orchestration_diagnostic: str | None,
    runner_output_matches_receipt: bool | None,
) -> bool:
    """Cross-bind derived stage outcome fields to their immutable receipt."""
    ledger = receipt.get("ledger") if isinstance(receipt, dict) else None
    report_ledger = report.get("ledger") if isinstance(report, dict) else None
    if (not isinstance(ledger, dict) or not isinstance(report_ledger, dict)
            or not _strict_equal(report_ledger, ledger)):
        return False
    consumed = ledger.get("consumed")
    if type(consumed) is not int or consumed < previous_consumed:
        return False
    native_calls = consumed - previous_consumed
    if native_calls not in (0, 1) or report.get("native_calls") != native_calls:
        return False

    receipt_success = receipt.get("successful")
    report_success = report.get("successful")
    if type(receipt_success) is not bool or type(report_success) is not bool:
        return False
    if report_success and not receipt_success:
        return False
    if stage in (5, 7):
        receipt_replay = receipt.get("independent_replay_matches")
        expected_replay = receipt_replay if type(receipt_replay) is bool else None
        if report.get("independent_replay_matches") is not expected_replay:
            return False
    elif report.get("independent_replay_matches") is not None:
        return False

    report_diagnostic = report.get("diagnostic")
    if report_success:
        return (
            receipt_success is True and report_diagnostic is None
            and runner_output_matches_receipt is True
            and native_calls == 1
            and process_record.get("status") == "completed"
            and process_record.get("return_code") == 0
            and process_record.get("error_code") is None
        )
    if not isinstance(report_diagnostic, str) or not report_diagnostic:
        return False
    if (runner_output_matches_receipt is False
            and report_diagnostic != "runner_output_invalid_or_nonzero"):
        return False
    possible: set[str] = set()
    for value in (
        receipt.get("diagnostic"), process_record.get("error_code"),
        orchestration_diagnostic,
    ):
        if isinstance(value, str) and value:
            possible.add(value)
    if process_record.get("status") != "completed":
        possible.add("runner_process_incomplete")
    else:
        return_code = process_record.get("return_code")
        if type(return_code) is int and return_code != 0:
            possible.add("runner_output_invalid_or_nonzero")
        elif (type(return_code) is int and return_code == 0
              and receipt_success is True
              and process_record.get("error_code") is None):
            # A clean process can still emit malformed JSON after the runner
            # has durably written a successful receipt. The report records
            # that output failure without rewriting the receipt outcome.
            possible.add("runner_output_invalid_or_nonzero")
        if receipt_success is False:
            possible.update(("stage_unsuccessful", "stage_receipt_unsuccessful"))
    return report_diagnostic in possible


def _expected_normal_runner_output(receipt: dict, previous_consumed: int,
                                   spec: CurryScopeSpec) -> dict | None:
    """Derive the one expected normal-result JSON object from its receipt."""
    ledger = receipt.get("ledger") if isinstance(receipt, dict) else None
    successful = receipt.get("successful") if isinstance(receipt, dict) else None
    if (not isinstance(ledger, dict) or type(successful) is not bool
            or type(ledger.get("consumed")) is not int
            or ledger["consumed"] < previous_consumed):
        return None
    delta = ledger["consumed"] - previous_consumed
    if delta not in (0, 1):
        return None
    expected = {
        "successful": successful,
        "native_calls": delta,
        "ledger": copy.deepcopy(ledger),
    }
    if _uses_reservation_accounting(spec):
        certified = spec.certified_historical_consumed
        reserved = spec.policy_reserved
        planning = spec.planning_base
        if certified is None or reserved is None or planning is None:
            return None
        known = (
            type(ledger.get("unknown")) is int and ledger["unknown"] == 0
            and type(ledger.get("reserved")) is int and ledger["reserved"] == 0
            and type(ledger.get("abandoned")) is int and ledger["abandoned"] == 0
            and ledger.get("consumed") == ledger.get("completed")
        )
        new_consumed = ledger["consumed"] if known else None
        expected.update({
            "certified_historical_consumed": certified,
            "policy_reserved": reserved,
            "planning_base": planning,
            "reservation_id": spec.reservation_id,
            "reservation_policy_id": spec.reservation_policy_id,
            "new_consumed": new_consumed,
            "certified_consumed_including_new": (
                certified + new_consumed if new_consumed is not None else None
            ),
            "planning_total": planning + new_consumed if new_consumed is not None else None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
            "unknown": ledger.get("unknown"),
        })
    return expected


def _saved_normal_output_matches_receipt(
    root: Path, process_record: dict, receipt: dict,
    previous_consumed: int, spec: CurryScopeSpec,
) -> bool | None:
    """Parse authenticated saved stdout and bind its full result to the receipt.

    ``None`` means the process did not complete, so its partial stdout cannot be
    treated as a runner result. ``False`` means completed stdout is malformed
    or does not equal the receipt-derived normal result.
    """
    if process_record.get("status") != "completed":
        return None
    try:
        stdout_meta = process_record.get("stdout")
        if not isinstance(stdout_meta, dict) or not isinstance(stdout_meta.get("path"), str):
            return False
        raw = safe_path(root / stdout_meta["path"]).read_bytes()
        value = strict_json(raw)
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return False
    expected = _expected_normal_runner_output(receipt, previous_consumed, spec)
    return expected is not None and _strict_equal(value, expected)


def _saved_orchestration_diagnostic(output: Path, stage: int,
                                    spec: CurryScopeSpec) -> str | None:
    path = output / f"stage-{stage}-orchestration-diagnostic.json"
    if not path.exists():
        return None
    value = strict_json(safe_path(path).read_bytes())
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "kind", "scope", "stage", "diagnostic"}
            or value.get("schema_version") != 1
            or value.get("kind") != _report_kind(spec, "orchestration_diagnostic")
            or value.get("scope") != spec.scope or value.get("stage") != stage
            or not isinstance(value.get("diagnostic"), str)
            or re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value["diagnostic"]) is None):
        raise ValueError("curry_saved_orchestration_diagnostic_invalid")
    return value["diagnostic"]


def _save_orchestration_diagnostic(output: Path, stage: int, reason: str,
                                   spec: CurryScopeSpec = CURRY_SCOPE) -> str:
    path = output / f"stage-{stage}-orchestration-diagnostic.json"
    immutable_write(path, {
        "schema_version": 1,
        "kind": _report_kind(spec, "orchestration_diagnostic"),
        "scope": spec.scope,
        "stage": stage,
        "diagnostic": reason,
    })
    return _sha(safe_path(path).read_bytes())


def run_curry_stages(
    *, root: Path, output: Path, runner: Path, repo: Path, manifest: dict,
    prepared_hash: str, stage1_request: dict, expected_identity: dict,
    source: dict, protected: dict[Path, str], frozen_files: dict[Path, str],
    process_runner: Callable[..., Any] | None = None,
    spec: CurryScopeSpec = CURRY_SCOPE,
    clock: Callable[[], float] = time.time,
) -> dict:
    """Run/resume only the fixed seven-stage Curry request chain."""
    from ygo_eval.native_tenki_placement_validation import (
        _diagnostic_hash,
        _process_exit_succeeded,
        _read_runner_stats,
        _run_process,
        _save_stage_files,
        _stage_invocation,
        _stats_for_missing_ledger,
        _valid_stats as tenki_valid_stats,
        _verify_basic_receipt,
        _verify_stage_intent,
    )
    from ygo_data.identity import stable_source

    def protected_hash(path: Path) -> str:
        if spec.scope == CONFIRMATION_SCOPE.scope:
            return _confirmation_protected_hash(path, repo)
        if _is_revalidation_scope(spec):
            return _option_revalidation_protected_hash(path, repo)
        if _uses_reservation_accounting(spec):
            return _option_verification_protected_hash(path, repo)
        return _protected_curry_hash(path, repo / spec.baseline_root)

    def unchanged(repo_path, captured_source, protected_files):
        if stable_source(repo_path) != captured_source:
            raise ValueError("curry_workspace_source_changed")
        for path, expected in protected_files.items():
            found = protected_hash(path)
            if found != expected:
                raise ValueError("curry_frozen_input_changed")

    def verify_intent(input_path, stage, request, identity, started_at):
        _verify_stage_intent(input_path, output, manifest["context"], stage,
                             request, identity, started_at, spec)

    def run_process(runner_path, input_path, repo_path, root_path, mode,
                    *, prepared_hash=None, timeout=None):
        return _run_process(
            runner_path, input_path, repo_path, root_path, mode,
            prepared_hash=prepared_hash, timeout=timeout,
            process_runner=process_runner, spec=spec,
        )

    def read_stats(input_path):
        return _read_runner_stats(runner, input_path, repo, root,
                                  process_runner=process_runner, spec=spec)

    def valid_stats(value):
        return tenki_valid_stats(value, spec)

    return run_six_stage_workflow(
        spec=WorkflowSpec(
            scope=spec.scope,
            limit=spec.limit,
            wall_seconds=spec.wall_seconds,
            worker_timeout_seconds=spec.worker_timeout_seconds,
            runner_role=spec.runner_role,
            stage_kind=_report_kind(spec, "stage"),
            stage_report_kind=_report_kind(spec, "stage_report"),
            input_seal_kind=spec.input_seal_kind,
            trace_stderr=True,
            timeout_error_prefix="curry",
        ),
        root=root, output=output, runner=runner, repo=repo,
        manifest=manifest, prepared_hash=prepared_hash,
        stage1_request=stage1_request, expected_identity=expected_identity,
        source=source, protected=protected, frozen_files=frozen_files,
        parent_stage=PARENT_STAGE,
        derive_request=lambda stage, parent: derive_curry_stage_request(stage, parent, spec),
        save_stage_files=lambda *args: _save_stage_files(*args, spec=spec),
        invocation_for_stage=lambda context, out, stage, request, identity, started:
            _stage_invocation(context, out, stage, request, identity, started, spec),
        verify_stage_intent=verify_intent,
        read_receipt=lambda path: strict_json(safe_path(path).read_bytes()) if path.exists() else None,
        run_process=run_process,
        read_stats=read_stats,
        valid_stats=valid_stats,
        missing_ledger_stats=lambda *, normal_attempted:
            _stats_for_missing_ledger(normal_attempted=normal_attempted, spec=spec),
        verify_basic_receipt=lambda receipt, request, context, stage:
            _verify_curry_basic_receipt(receipt, request, context, stage, spec),
        validate_stage_receipt=lambda receipt, request, context, stage, identity:
            validate_curry_stage_receipt(receipt, request, context, stage, identity, spec),
        stage_report=lambda *args: _stage_report(*args, spec=spec),
        validate_report=lambda value, _repo: validate_curry_report(value, spec=spec),
        summarize=lambda context, stages, stats, diagnostic:
            summarize_curry_validation(context, stages, stats, diagnostic, spec),
        diagnostic_hash=lambda root_path, record:
            _diagnostic_hash(root_path, record, spec),
        save_orchestration_diagnostic=lambda out, stage, reason:
            _save_orchestration_diagnostic(out, stage, reason, spec),
        assert_unchanged=unchanged,
        safe_file=safe_path,
        immutable_write=immutable_write,
        sha256=_sha,
        process_exit_succeeded=_process_exit_succeeded,
        strict_json=strict_json,
        clock=clock,
    )


def verify_curry_only(
    *, root: Path, output: Path, runner: Path, repo: Path,
    manifest: dict, prepared_hash: str,
    verify_recorded: Callable[[Path], dict],
    read_stats: Callable[[Path], dict | None],
    verification_output: Path | None = None,
    spec: CurryScopeSpec = CURRY_SCOPE,
) -> dict:
    """Read-only verification of already saved stage receipts.

    Callbacks are deliberately limited to the runner's `--verify-recorded`
    and `--stats` modes. This function never creates a stage intent or invokes
    normal execution. It only creates the separate verification report.
    """
    from ygo_eval.native_tenki_placement_validation import (
        _diagnostic_hash,
        _stage_invocation,
        _verify_stage_intent,
    )

    context = manifest.get("context")
    if (not isinstance(context, str) or not HASH.fullmatch(context)
            or manifest.get("scope") != spec.scope):
        raise ValueError("curry_verify_manifest_binding_invalid")
    stage_summaries: list[dict] = []
    verification_hashes: list[str] = []
    parent_receipts: dict[int, dict] = {}
    diagnostic = None
    last_input: Path | None = None
    previous_consumed = 0
    for stage in range(1, spec.limit + 1):
        input_path = output / f"stage-{stage}-input.json"
        request_path = output / f"stage-{stage}-request.json"
        seal_path = output / f"stage-{stage}-input-seal.json"
        receipt_path = output / f"stage-{stage}.json"
        report_path = output / f"stage-{stage}-report.json"
        required = (input_path, request_path, seal_path, receipt_path, report_path)
        if not all(path.is_file() for path in required):
            diagnostic = ("incomplete_saved_stage_files" if any(path.exists() for path in required)
                          else "incomplete_stage_receipts")
            break
        try:
            invocation = strict_json(safe_path(input_path).read_bytes())
            request = strict_json(safe_path(request_path).read_bytes())
            seal = strict_json(safe_path(seal_path).read_bytes())
            receipt = strict_json(safe_path(receipt_path).read_bytes())
            report = strict_json(safe_path(report_path).read_bytes())
            if stage == 1:
                expected_request = manifest.get("request")
            else:
                parent = parent_receipts.get(PARENT_STAGE[stage])
                if parent is None:
                    diagnostic = "saved_parent_receipt_missing_or_invalid"
                    break
                expected_request = derive_curry_stage_request(stage, parent, spec)
            if not _strict_equal(request, expected_request):
                raise ValueError("curry_saved_parent_request_derivation_mismatch")
            _verify_stage_intent(
                input_path, output, context, stage, request,
                manifest["assets"]["ordinary"], manifest["started_at"], spec,
            )
            if (invocation.get("request") != request
                    or invocation.get("batch_kind") != spec.batch_kind
                    or seal.get("context") != context
                    or invocation != _stage_invocation(
                        context, output, stage, request, manifest["assets"]["ordinary"],
                        manifest["started_at"], spec,
                    )):
                raise ValueError("curry_saved_stage_intent_invalid")
            _verify_curry_basic_receipt(receipt, request, context, stage, spec)
            if report.get("kind") != _report_kind(spec, "stage_report"):
                raise ValueError("curry_saved_stage_report_kind_invalid")
            validate_curry_report(report, spec=spec)
            if (report.get("stage") != stage or report.get("context") != context
                    or report.get("receipt_sha256") != _sha(safe_path(receipt_path).read_bytes())):
                raise ValueError("curry_saved_stage_report_binding_invalid")
            process_sidecar = root / f"stage-{stage}-process-diagnostic.json"
            process_record = strict_json(safe_path(process_sidecar).read_bytes())
            if _diagnostic_hash(root, process_record, spec) != report.get("diagnostic_sha256"):
                raise ValueError("curry_saved_stage_diagnostic_mismatch")
            orchestration_diagnostic = _saved_orchestration_diagnostic(
                output, stage, spec,
            )
            runner_output_matches = (
                _saved_normal_output_matches_receipt(
                    root, process_record, receipt, previous_consumed, spec,
                )
                if _uses_reservation_accounting(spec) else True
            )
            if not _stage_report_matches_receipt(
                    report, receipt, stage=stage,
                    previous_consumed=previous_consumed,
                    process_record=process_record,
                    orchestration_diagnostic=orchestration_diagnostic,
                    runner_output_matches_receipt=runner_output_matches):
                raise ValueError("curry_saved_stage_report_receipt_mismatch")
            if receipt.get("successful") is True:
                validate_curry_stage_receipt(receipt, request, context, stage,
                                             manifest["assets"]["ordinary"], spec)
                parent_receipts[stage] = receipt
            previous_consumed = receipt["ledger"]["consumed"]
            runner_result = verify_recorded(input_path)
            if (not isinstance(runner_result, dict)
                    or runner_result.get("verified_recorded") is not True
                    or runner_result.get("native_calls") != 0):
                raise ValueError("curry_recorded_receipt_verification_failed")
            verification_hashes.append(runner_result.get("diagnostic_sha256", _sha(b"")))
            if (not isinstance(verification_hashes[-1], str)
                    or not HASH.fullmatch(verification_hashes[-1])):
                raise ValueError("curry_verify_diagnostic_hash_invalid")
            stage_summaries.append({key: report.get(key) for key in (
                "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
                "diagnostic_sha256", "independent_replay_matches", "ledger",
            )})
            last_input = input_path
            if report.get("successful") is not True:
                diagnostic = report.get("diagnostic") or "saved_stage_unsuccessful"
                break
        except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
            diagnostic = str(error) if str(error).isidentifier() else "saved_stage_invalid"
            break

    stats = None
    ledger_path = output / "calls.jsonl"
    if ledger_path.exists():
        stats_input = last_input or (output / "stage-1-input.json")
        if stats_input.is_file():
            try:
                stats = read_stats(stats_input)
            except (OSError, ValueError, TypeError, UnicodeDecodeError):
                stats = None
        if not _valid_stats(stats, spec):
            stats = None
            diagnostic = diagnostic or "ledger_statistics_unknown_or_invalid"
    if stats is None:
        new_consumed = cumulative = unknown = None
    else:
        new_consumed = (
            stats["consumed"]
            if not _uses_reservation_accounting(spec)
            or _reservation_stats_settled(stats, spec)
            else None
        )
        cumulative = spec.old_consumed + stats["consumed"]
        unknown = stats["unknown"]
    valid = bool(
        diagnostic is None and len(stage_summaries) == spec.limit
        and stats is not None and stats["consumed"] == stats["completed"] == spec.limit
        and stats["unknown"] == stats["reserved"] == stats["abandoned"] == 0
        and all(_valid_stage_summary(item, index, spec)
                and item["successful"] is True
                for index, item in enumerate(stage_summaries, 1))
        and len(verification_hashes) == spec.limit
    )
    if not valid and diagnostic is None:
        diagnostic = "saved_curry_validation_incomplete_or_invalid"
    report = {
        "schema_version": 1,
        "kind": _report_kind(spec, "verification"),
        "scope": spec.scope,
        "context": context,
        "valid": valid,
        "native_calls": 0,
        "ledger": stats,
        "stages": stage_summaries,
        "prepared_sha256": prepared_hash,
        "verification_diagnostic_sha256": verification_hashes,
        "diagnostic": diagnostic,
        **FLAGS,
    }
    if _uses_reservation_accounting(spec):
        certified = spec.certified_historical_consumed
        reserved = spec.policy_reserved
        planning = spec.planning_base
        if certified is None or reserved is None or planning is None:
            raise ValueError("curry_option_verification_accounting_spec_missing")
        report.update({
            "certified_historical_consumed": certified,
            "policy_reserved": reserved,
            "planning_base": planning,
            "reservation_id": spec.reservation_id,
            "reservation_policy_id": spec.reservation_policy_id,
            "new_consumed": new_consumed,
            "certified_consumed_including_new": (
                certified + new_consumed if new_consumed is not None else None
            ),
            "planning_total": planning + new_consumed if new_consumed is not None else None,
            "old_confirmation_actual_consumed": None,
            "actual_all_history_cumulative": None,
            "unknown": unknown,
        })
    else:
        report.update({
            "old_consumed": spec.old_consumed,
            "new_consumed": new_consumed,
            "cumulative_consumed": cumulative,
            "unknown": unknown,
        })
    validate_curry_report(report, spec=spec)
    report_path = (verification_output or output) / "verification.json"
    immutable_write(report_path, report)
    return report


def _verify_saved_confirmation_build_and_archive(
    root: Path, manifest: dict, paths: dict[str, Path],
) -> dict:
    """Revalidate saved source/build artifacts without consulting live assets."""
    import zipfile

    from ygo_eval.native_tenki_placement import _validate_signed
    from ygo_eval.native_tenki_placement_confirmation import _verify_workspace_identity

    source = manifest.get("source")
    input_hashes = manifest.get("input_sha256")
    build_binding = manifest.get("build")
    archive_binding = manifest.get("source_archive")
    if not all(isinstance(value, dict) for value in (
            source, input_hashes, build_binding, archive_binding)):
        raise ValueError("curry_saved_build_manifest_invalid")

    build_raw = safe_path(paths["build_record"]).read_bytes()
    if _sha(build_raw) != input_hashes.get("build_record"):
        raise ValueError("curry_saved_build_record_hash_mismatch")
    build = strict_json(build_raw)
    _validate_signed(build, "build_record")
    if (build.get("status") != "recorded"
            or build.get("source_before") != source
            or build.get("source_after") != source
            or build.get("reproducible_build_proven") is not False
            or build.get("identity") != build_binding.get("identity")
            or _sha(build_raw) != build_binding.get("record_sha256")):
        raise ValueError("curry_saved_build_binding_invalid")

    artifact_hashes = build.get("artifacts")
    if (not isinstance(artifact_hashes, dict)
            or build_binding.get("artifacts") != artifact_hashes):
        raise ValueError("curry_saved_build_artifact_map_invalid")
    for role in ("runner", "worker", "cli"):
        path = safe_path(paths[role])
        expected = input_hashes.get(role)
        if (not isinstance(expected, str) or not HASH.fullmatch(expected)
                or artifact_hashes.get(role) != expected
                or _sha(path.read_bytes()) != expected):
            raise ValueError(f"curry_saved_{role}_artifact_hash_mismatch")

    identity_raw = safe_path(paths["identity"]).read_bytes()
    if _sha(identity_raw) != input_hashes.get("identity"):
        raise ValueError("curry_saved_identity_hash_mismatch")
    identity = strict_json(identity_raw)
    _validate_signed(identity, "workspace_identity")
    if identity.get("source") != source:
        raise ValueError("curry_saved_identity_source_mismatch")
    _verify_workspace_identity(identity, source, artifact_hashes,
                               paths["worker"], manifest.get("request"))

    archive_raw = safe_path(paths["source_archive"]).read_bytes()
    file_list_raw = safe_path(paths["source_file_list"]).read_bytes()
    if archive_binding.get("sha256") != input_hashes.get("source_archive"):
        raise ValueError("curry_saved_source_archive_role_hash_mismatch")
    if archive_binding.get("file_list_sha256") != input_hashes.get("source_file_list"):
        raise ValueError("curry_saved_source_file_list_role_hash_mismatch")
    if (_sha(archive_raw) != archive_binding.get("sha256")
            or _sha(file_list_raw) != archive_binding.get("file_list_sha256")):
        raise ValueError("curry_saved_source_archive_binding_invalid")
    listing = strict_json(file_list_raw)
    files = listing.get("files") if isinstance(listing, dict) else None
    head = listing.get("head") if isinstance(listing, dict) else None
    if (listing.get("schema_version") != 1
            or listing.get("kind") != "workspace_source_archive"
            or not isinstance(files, dict)
            or listing.get("file_count") != len(files)
            or listing.get("file_count") != archive_binding.get("file_count")
            or listing.get("source_identity") != source.get("identity")
            or listing.get("head") != source.get("head")
            or files != source.get("files")
            or _sha(canonical({"head": head, "files": files})) != source.get("identity")):
        raise ValueError("curry_saved_source_list_binding_invalid")
    for name, expected in files.items():
        path_name = Path(name)
        if (not isinstance(name, str) or not name or path_name.is_absolute()
                or "\\" in name or ":" in name or ".." in path_name.parts
                or not isinstance(expected, str) or not HASH.fullmatch(expected)):
            raise ValueError("curry_saved_source_list_entry_invalid")
    try:
        with zipfile.ZipFile(paths["source_archive"]) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(files):
                raise ValueError("curry_saved_source_archive_membership_invalid")
            for name, expected in files.items():
                if _sha(archive.read(name)) != expected:
                    raise ValueError("curry_saved_source_archive_member_hash_mismatch")
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("curry_saved_source_archive_invalid") from None
    return {
        "build_identity": build["identity"],
        "source_identity": source["identity"],
        "artifact_sha256": {role: artifact_hashes[role] for role in ("runner", "worker", "cli")},
        "source_archive_sha256": archive_binding["sha256"],
        "source_file_list_sha256": archive_binding["file_list_sha256"],
        "source_file_count": len(files),
        "source_file_hashes": dict(files),
    }


def _verify_curry_basic_receipt(receipt: dict, request: dict, context: str,
                               stage: int, spec: CurryScopeSpec) -> None:
    from ygo_eval.native_tenki_placement_validation import _valid_stats

    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
            or receipt.get("kind") != _report_kind(spec, "stage")
            or receipt.get("scope") != spec.scope or receipt.get("context") != context
            or type(receipt.get("stage")) is not int or receipt.get("stage") != stage
            or not _strict_equal(receipt.get("request"), request)
            or type(receipt.get("successful")) is not bool
            or not isinstance(receipt.get("assets_before"), dict)
            or (receipt.get("assets_after") is not None
                and not isinstance(receipt.get("assets_after"), dict))
            or (receipt.get("successful") is True
                and not isinstance(receipt.get("assets_after"), dict))
            or any(receipt.get(flag) is not False for flag in FLAGS)):
        raise ValueError("curry_stage_receipt_binding_invalid")
    if not _valid_stats(receipt.get("ledger"), spec):
        raise ValueError("curry_stage_receipt_ledger_invalid")


def _fixed_curry_paths(args: argparse.Namespace, repo: Path,
                       spec: CurryScopeSpec) -> tuple[Path, Path, dict[str, Path]]:
    """Resolve only the predeclared Curry scope paths; the CLI cannot redirect it."""
    root = repo / spec.output_root
    if Path(os.path.abspath(args.baseline_dir)) != repo / spec.baseline_root:
        raise ValueError("curry_fixed_baseline_required")
    expected = {
        "runner": root / "native-artifacts" / (
            "curry-option-confirmation.exe"
            if spec.scope == CONFIRMATION_SCOPE.scope else
            "curry-option-revalidation.exe"
            if _is_revalidation_scope(spec) else
            "curry-option-verification.exe"
            if spec.scope == OPTION_VERIFICATION_SCOPE.scope else
            "curry-option-validation.exe"
        ),
        "worker": root / "native-artifacts" / "ygo-engine-worker.exe",
        "build_record": root / "build-record.json",
        "identity": root / "identity.json",
        "window_start": root / "window-start.json",
        "cli": root / "native-artifacts" / "ygo-cli.exe",
        "source_archive": root / "source-native.zip",
        "source_file_list": root / "source-native-file-list.json",
        "ordinary_config": root / "ordinary-candidate.toml",
        "tournament_config": root / "tournament-candidate.toml",
        "output": root / "research",
    }
    supplied_roles = ("runner", "worker", "build_record", "identity", "window_start", "output")
    for arg_name in supplied_roles:
        expected_path = expected[arg_name]
        supplied = Path(os.path.abspath(getattr(args, arg_name)))
        if supplied != expected_path:
            raise ValueError(f"curry_fixed_{arg_name}_path_required")
    fixed_inputs = {
        "preparation": repo / PREPARATION_PATH,
        "cases": repo / FROZEN_CASES_PATH,
        "core_source": repo / "data/tmp/ocgcore-source/operations.cpp",
    }
    for role, path in fixed_inputs.items():
        supplied = Path(os.path.abspath(getattr(args, role)))
        if supplied != path:
            raise ValueError(f"curry_fixed_{role}_path_required")
    output = expected["output"]
    candidate_root = repo / (spec.candidate_config_root or spec.baseline_root)
    for path in (root, output, candidate_root, *expected.values()):
        if path.is_symlink():
            raise ValueError("curry_linked_scope_path_rejected")
    if output == root or not output.is_relative_to(root):
        raise ValueError("curry_output_outside_scope")
    return root, output, {key: expected[key] for key in (
        "runner", "worker", "build_record", "identity", "window_start",
        "cli", "source_archive", "source_file_list", "ordinary_config",
        "tournament_config",
    )}


def _curry_window_start(path: Path, spec: CurryScopeSpec,
                        *, now: int | None = None) -> dict:
    """Create or reuse the fixed window, without ever resetting its start."""
    from ygo_eval.terminal_regression import immutable_write as write_once

    current = int(time.time()) if now is None else now
    if path.name != "window-start.json":
        raise ValueError("curry_fixed_window_path_required")
    if path.exists():
        value = strict_json(safe_path(path).read_bytes())
        if (value.get("schema_version") != 1
                or value.get("kind") != _window_kind(spec)
                or value.get("scope") != spec.scope
                or value.get("limit") != spec.limit
                or value.get("wall_seconds") != spec.wall_seconds
                or type(value.get("started_at")) is not int
                or value["started_at"] < 0):
            raise ValueError("curry_window_start_mismatch")
        return value
    value = {
        "schema_version": 1,
        "kind": _window_kind(spec),
        "scope": spec.scope,
        "limit": spec.limit,
        "wall_seconds": spec.wall_seconds,
        "started_at": current,
    }
    write_once(path, value)
    return value


def _curry_manifest_files(repo: Path, root: Path, paths: dict[str, Path],
                          preparation: dict, banlist_path: Path,
                          spec: CurryScopeSpec = CURRY_SCOPE) -> dict[str, Path]:
    files = {
        "preparation": repo / PREPARATION_PATH,
        "preparation_report": repo / PREPARATION_REPORT_PATH,
        "preparation_acceptance": repo / PREPARATION_ACCEPTANCE_PATH,
        "operations_source": repo / "data/tmp/ocgcore-source/operations.cpp",
        "base_request": repo / FROZEN_CASES_PATH,
        "candidate_case": repo / PREPARATION_PATH,
        "adapter_codec": repo / HISTORICAL_SOURCE_TRANSITION["path"],
        "runner": paths["runner"],
        "worker": paths["worker"],
        "cli": paths["cli"],
        "build_record": paths["build_record"],
        "identity": paths["identity"],
        "window_start": paths["window_start"],
        "source_archive": paths["source_archive"],
        "source_file_list": paths["source_file_list"],
        "ordinary_config": paths["ordinary_config"],
        "tournament_config": paths["tournament_config"],
        "banlist": banlist_path,
        "core_source": repo / "data/tmp/ocgcore-source/operations.cpp",
    }
    if spec.scope == CONFIRMATION_SCOPE.scope:
        files["baseline_audit"] = repo / spec.baseline_root / "audit-report.json"
        files["baseline_delivery"] = repo / spec.baseline_root / "final-build/delivery.json"
    elif spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        if spec.acceptance_relative is None or spec.reservation_relative is None:
            raise ValueError("curry_option_verification_baseline_roles_missing")
        files["baseline_acceptance"] = repo / spec.baseline_root / spec.acceptance_relative
        files["consumption_reservation"] = repo / spec.baseline_root / spec.reservation_relative
    elif _is_revalidation_scope(spec):
        files["baseline_delivery"] = (
            repo / spec.baseline_root / "final-build/delivery-final.json"
        )
        files["baseline_recovery"] = repo / spec.baseline_root / "recovery-report.json"
        files["consumption_reservation"] = (
            repo / OPTION_VERIFICATION_SCOPE.baseline_root / "reservation.json"
        )
    else:
        files["baseline_delivery"] = repo / spec.baseline_root / "final-build/delivery.json"
    if set(files) != set(_manifest_roles(spec)):
        raise ValueError("curry_manifest_role_set_invalid")
    return files


def _hash_manifest_files(files: dict[str, Path], repo: Path,
                         preparation: dict,
                         spec: CurryScopeSpec = CURRY_SCOPE) -> dict[str, str]:
    del repo
    hashes, _raw_snapshot = _capture_manifest_input_state(files, preparation)
    if any(hashes.get(role) != digest for role, digest in _pinned_inputs(spec).items()
           if role in hashes):
        raise ValueError("curry_base_request_hash_binding_invalid")
    return hashes


def _capture_manifest_input_state(
    files: dict[str, Path], preparation: dict,
) -> tuple[dict[str, str], dict[Path, str]]:
    """Capture semantic manifest hashes and separate raw file protections.

    ``base_request`` and ``candidate_case`` are extracted objects in their
    container files. Their manifest roles intentionally retain the historical
    canonical-object hash; the returned path map always holds raw file hashes.
    """
    hashes: dict[str, str] = {}
    raw_snapshot: dict[Path, str] = {}
    for role, path in files.items():
        absolute = Path(os.path.abspath(path))
        safe = safe_path(absolute)
        if not safe.is_file():
            raise ValueError(f"curry_manifest_{role}_missing")
        raw = safe.read_bytes()
        raw_hash = _sha(raw)
        hashes[role] = raw_hash
        raw_snapshot[absolute] = raw_hash
    for role in ("base_request", "candidate_case"):
        if role in files:
            if role not in preparation:
                raise ValueError(f"curry_manifest_{role}_object_missing")
            hashes[role] = _sha(_case_encode(preparation[role]))
    return hashes, raw_snapshot


def _verify_manifest_input_state(
    files: dict[str, Path], preparation: dict,
    expected_hashes: dict[str, str],
    *, archived_source_hashes: dict[str, str] | None = None,
) -> dict[Path, str]:
    """Compare the unchanged manifest contract and return raw protections."""
    hashes, raw_snapshot = _capture_manifest_input_state(files, preparation)
    if archived_source_hashes is not None:
        if (set(archived_source_hashes) != {"adapter_codec"}
                or "adapter_codec" not in files
                or any(not isinstance(value, str) or not HASH.fullmatch(value)
                       for value in archived_source_hashes.values())):
            raise ValueError("curry_saved_historical_source_archive_role_invalid")
        # A saved Curry manifest binds adapter_codec to the source used by its
        # authenticated build archive. The live path can legitimately contain
        # a later protocol decoder, so compare the frozen role to the archive
        # while retaining the live file's raw hash in raw_snapshot for drift
        # protection during this read-only audit.
        hashes.update(archived_source_hashes)
    if set(hashes) != set(expected_hashes):
        missing = sorted(set(expected_hashes) - set(hashes))
        extra = sorted(set(hashes) - set(expected_hashes))
        role = missing[0] if missing else extra[0]
        raise CurryFrozenInputMismatch(role, expected_hashes.get(role), hashes.get(role))
    for role, found in hashes.items():
        expected = expected_hashes.get(role)
        if expected != found:
            raise CurryFrozenInputMismatch(role, expected, found)
    return raw_snapshot


def _resolve_curry_banlist_path(repo: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(repo) or not safe_path(path).is_file():
        raise ValueError("curry_fixed_banlist_path_invalid")
    return path


def _save_pre_stage_refusal_diagnostic(
    repo: Path, error: BaseException, spec: CurryScopeSpec,
) -> tuple[Path, str]:
    """Persist a path-free refusal record before a normal stage can start."""
    repo = Path(os.path.abspath(repo))
    root = repo / RECOVERY_REFUSAL_DIAGNOSTICS_ROOT
    try:
        ignored = safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        if not any(line.strip().strip("/") == "data/runtime" for line in ignored):
            raise ValueError("curry_refusal_diagnostic_output_must_be_ignored")
        if root.exists() or root.is_symlink():
            root = safe_path(root, file=False)
            if not root.is_dir():
                raise ValueError("curry_refusal_diagnostic_root_invalid")
        else:
            root.mkdir(parents=True, exist_ok=False)
            root = safe_path(root, file=False)
        role = error.role if isinstance(error, CurryFrozenInputMismatch) else None
        expected = error.expected_sha256 if isinstance(error, CurryFrozenInputMismatch) else None
        found = error.found_sha256 if isinstance(error, CurryFrozenInputMismatch) else None
        code = getattr(error, "diagnostic", str(error))
        if not isinstance(code, str) or re.fullmatch(r"[a-z][a-z0-9_]{1,90}", code) is None:
            code = "curry_pre_stage_gate_rejected"
        if role is not None and (not isinstance(role, str)
                                 or re.fullmatch(r"[a-z][a-z0-9_]{1,100}", role) is None):
            raise ValueError("curry_refusal_diagnostic_role_invalid")
        record = {
            "schema_version": 1,
            "kind": "curry_input_recovery_pre_stage_refusal",
            "scope": spec.scope,
            "checkpoint": "normal_resume_pre_stage_gate",
            "error_code": code,
            "role": role,
            "expected_sha256": expected,
            "found_sha256": found,
            **FLAGS,
        }
        _validate_pre_stage_refusal_diagnostic(record)
        path = root / f"pre-stage-refusal-{uuid.uuid4().hex}.json"
        raw = canonical(record)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return path, _sha(raw)
    except Exception:
        raise ValueError("curry_refusal_diagnostic_save_failed") from None


def _validate_pre_stage_refusal_diagnostic(value: dict) -> bool:
    if (not isinstance(value, dict) or set(value) != {
            "schema_version", "kind", "scope", "checkpoint", "error_code", "role",
            "expected_sha256", "found_sha256", *FLAGS.keys(),
        }
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("kind") != "curry_input_recovery_pre_stage_refusal"
            or value.get("scope") not in {
                CURRY_SCOPE.scope, CONFIRMATION_SCOPE.scope,
                OPTION_VERIFICATION_SCOPE.scope, OPTION_REVALIDATION_SCOPE.scope,
            }
            or value.get("checkpoint") != "normal_resume_pre_stage_gate"
            or not isinstance(value.get("error_code"), str)
            or re.fullmatch(r"[a-z][a-z0-9_]{1,90}", value["error_code"]) is None
            or any(value.get(flag) is not False for flag in FLAGS)):
        raise ValueError("curry_refusal_diagnostic_invalid")
    role = value.get("role")
    if role is None:
        if value.get("expected_sha256") is not None or value.get("found_sha256") is not None:
            raise ValueError("curry_refusal_diagnostic_hash_without_role")
    elif (not isinstance(role, str)
          or re.fullmatch(r"[a-z][a-z0-9_]{1,100}", role) is None
          or any(item is not None and (not isinstance(item, str) or not HASH.fullmatch(item))
                 for item in (value.get("expected_sha256"), value.get("found_sha256")))):
        raise ValueError("curry_refusal_diagnostic_role_hash_invalid")
    return True


def _snapshot_curry_evidence(root: Path) -> dict[str, str]:
    """Hash the fixed evidence trees and stage diagnostic aliases without mutation."""
    root = Path(os.path.abspath(root))
    snapshot: dict[str, str] = {}
    for relative_root in (Path("research"), Path("process-diagnostics")):
        directory = safe_path(root / relative_root, file=False)
        for item in directory.rglob("*"):
            safe = safe_path(item, file=item.is_file())
            if safe.is_file():
                snapshot[safe.relative_to(root).as_posix()] = _sha(safe.read_bytes())
    for item in root.glob("*-process-diagnostic.json"):
        safe = safe_path(item)
        snapshot[safe.relative_to(root).as_posix()] = _sha(safe.read_bytes())
    return snapshot


def _curry_evidence_hash(snapshot: dict[str, str]) -> str:
    return _sha(canonical(snapshot))


def _option_verification_protected_hash(path: Path, repo: Path) -> str:
    """Hash the fixed V3 source tree, its evidence directory, or an absent ledger."""
    from ygo_eval.curry_consumption_reservation import (
        V3_TENKI_EVIDENCE_RELATIVE, _snapshot_tree,
    )

    path = Path(os.path.abspath(path))
    repo = Path(os.path.abspath(repo))
    if not path.is_relative_to(repo):
        raise ValueError("curry_option_verification_protected_path_outside_repo")
    if path.is_symlink():
        raise ValueError("curry_option_verification_protected_symlink_rejected")
    if path == repo / OPTION_VERIFICATION_SCOPE.baseline_root:
        return _sha(canonical(_snapshot_tree(path)))
    if path == repo / V3_TENKI_EVIDENCE_RELATIVE:
        return _curry_evidence_hash(_snapshot_curry_evidence(path))
    absent_ledger = repo / CONFIRMATION_SCOPE.output_root / "research" / "calls.jsonl"
    if path == absent_ledger:
        parent = safe_path(path.parent, file=False)
        if path.exists() or path.is_symlink():
            raise ValueError("curry_confirmation_charge_ledger_unexpected")
        # Inspect every parent component through safe_path before certifying absence.
        del parent
        return ABSENT_PROTECTION_SENTINEL
    if path.is_dir():
        raise ValueError("curry_option_verification_unrecognized_protected_directory")
    return _sha(safe_path(path).read_bytes())


def _assert_option_verification_protected(
    protected: dict[Path, str], repo: Path,
) -> None:
    for path, expected in protected.items():
        found = _option_verification_protected_hash(path, repo)
        if found != expected:
            raise ValueError("curry_option_verification_protected_input_changed")


def _assert_option_revalidation_protected(
    protected: dict[Path, str], repo: Path,
) -> None:
    for path, expected in protected.items():
        if _option_revalidation_protected_hash(path, repo) != expected:
            raise ValueError("curry_option_revalidation_protected_input_changed")


def _merge_protected_pin(protected: dict[Path, str], path: Path,
                         expected: str) -> None:
    absolute = Path(os.path.abspath(path))
    existing = protected.get(absolute)
    if existing is not None and existing != expected:
        raise ValueError("curry_option_verification_protected_pin_conflict")
    protected[absolute] = expected


def _add_v3_reservation_input_protections(
    protected: dict[Path, str], repo: Path, reservation: dict,
) -> None:
    """Carry the already authenticated V3 file and directory input pins forward."""
    from ygo_eval.curry_consumption_reservation import V3_TENKI_EVIDENCE_RELATIVE

    rows = reservation.get("inputs")
    if not isinstance(rows, list) or not rows:
        raise ValueError("curry_option_verification_reservation_inputs_missing")
    seen_roles: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("curry_option_verification_reservation_input_invalid")
        relative = item.get("path")
        role = item.get("role")
        expected = item.get("sha256")
        byte_count = item.get("bytes")
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or ":" in relative or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or not isinstance(role, str) or role in seen_roles
                or not isinstance(expected, str) or not HASH.fullmatch(expected)
                or type(byte_count) is not int or byte_count < 0):
            raise ValueError("curry_option_verification_reservation_input_invalid")
        seen_roles.add(role)
        candidate = repo / Path(relative)
        if relative == V3_TENKI_EVIDENCE_RELATIVE.as_posix():
            if byte_count != 0:
                raise ValueError("curry_option_verification_directory_length_invalid")
            directory = safe_path(candidate, file=False)
            found = _curry_evidence_hash(_snapshot_curry_evidence(directory))
        else:
            file_path = safe_path(candidate)
            raw = file_path.read_bytes()
            if len(raw) != byte_count:
                raise ValueError("curry_option_verification_input_length_mismatch")
            found = _sha(raw)
        if found != expected:
            raise ValueError("curry_option_verification_reservation_input_hash_mismatch")
        _merge_protected_pin(protected, candidate, expected)


def _verify_saved_option_verification_inputs(
    args: argparse.Namespace, repo: Path, root: Path, paths: dict[str, Path],
    manifest: dict, baseline_protected: dict[Path, str],
    spec: CurryScopeSpec = OPTION_VERIFICATION_SCOPE,
    *, _sources: Any | None = None,
    archived_source_hashes: dict[str, str] | None = None,
) -> dict[Path, str]:
    """Revalidate 21 verification or 22 revalidation roles without asset scans."""
    if spec.scope not in (OPTION_VERIFICATION_SCOPE.scope,
                          OPTION_REVALIDATION_SCOPE.scope):
        raise ValueError("curry_saved_input_gate_scope_invalid")
    preparation = verify_curry_preparation(
        repo=repo,
        preparation=repo / PREPARATION_PATH,
        preparation_report=repo / PREPARATION_REPORT_PATH,
        preparation_acceptance=repo / PREPARATION_ACCEPTANCE_PATH,
        cases_path=repo / FROZEN_CASES_PATH,
        operations_source=repo / "data/tmp/ocgcore-source/operations.cpp",
        _sources=(
            _sources.child("static_preparation") if _sources is not None else None
        ),
    )
    banlist_path = _resolve_curry_banlist_path(
        repo, preparation["base_request_entry"].get("banlist_path", ""),
    )
    files = _curry_manifest_files(repo, root, paths, preparation, banlist_path, spec)
    if archived_source_hashes is not None:
        archived_codec = archived_source_hashes.get(HISTORICAL_SOURCE_TRANSITION["path"])
        if (spec.scope != OPTION_VERIFICATION_SCOPE.scope
                or not isinstance(archived_codec, str)
                or not HASH.fullmatch(archived_codec)
                or manifest.get("input_sha256", {}).get("adapter_codec") != archived_codec):
            raise ValueError("curry_saved_adapter_codec_archive_binding_mismatch")
        archived_source_hashes = {"adapter_codec": archived_codec}
    frozen = _verify_manifest_input_state(
        files, preparation, manifest.get("input_sha256", {}),
        archived_source_hashes=archived_source_hashes,
    )
    protected = dict(baseline_protected)
    for path, expected in frozen.items():
        _merge_protected_pin(protected, path, expected)
    return protected


def _protected_curry_hash(path: Path, evidence_root: Path) -> str:
    """Hash ordinary protected files or the fixed Curry evidence inventory."""
    path = Path(os.path.abspath(path))
    evidence_root = Path(os.path.abspath(evidence_root))
    if path == evidence_root:
        return _curry_evidence_hash(_snapshot_curry_evidence(evidence_root))
    return _sha(safe_path(path).read_bytes())


def _confirmation_protected_hash(path: Path, repo: Path) -> str:
    """Recheck each confirmation input with the directory semantics it was frozen under."""
    from ygo_eval.curry_asset_binding_audit import _snapshot_tree

    path = Path(os.path.abspath(path))
    repo = Path(os.path.abspath(repo))
    if path.is_symlink():
        raise ValueError("curry_confirmation_protected_symlink_rejected")
    if path.is_dir():
        if path == repo / CONFIRMATION_SCOPE.baseline_root:
            return _sha(canonical(_snapshot_tree(path)))
        return _protected_curry_hash(path, path)
    return _sha(safe_path(path).read_bytes())


def _verify_curry_baseline(repo: Path, baseline_dir: Path,
                           spec: CurryScopeSpec = CURRY_SCOPE, *,
                           _sources: Any | None = None) -> tuple[dict, dict[Path, str]]:
    """Verify the placement-validation delivery and the separate eight-ledger base.

    The Curry baseline is the placement-validation *output*. Its predecessor
    verifier expects the older runner-repair *input*, so those two roots must
    be checked independently.
    """
    from ygo_data.identity import stable_source
    from ygo_eval.native_tenki_placement_validation import (
        VALIDATION_SCOPE, _verify_validation_baseline,
    )

    repo = Path(os.path.abspath(repo))
    baseline = Path(os.path.abspath(baseline_dir))
    if baseline != repo / spec.baseline_root or baseline.is_symlink():
        raise ValueError("curry_fixed_baseline_required")
    evidence_snapshot = _snapshot_curry_evidence(baseline)
    source_before = stable_source(repo)
    validation_kwargs = {"protection_scope": spec.scope}
    if _sources is not None:
        validation_kwargs["_sources"] = _source_child(_sources, "validation_baseline")
    prior, protected = _verify_validation_baseline(
        repo,
        repo / VALIDATION_SCOPE.baseline_root,
        VALIDATION_SCOPE,
        **validation_kwargs,
    )

    acceptance_path = baseline / "acceptance.json"
    acceptance_raw = safe_path(acceptance_path).read_bytes()
    expected_acceptance_sha256 = _source_file_sha256(
        _sources,
        spec.baseline_root / "acceptance.json",
        spec.delivery_acceptance_sha256,
    )
    if _sha(acceptance_raw) != expected_acceptance_sha256:
        raise ValueError("curry_baseline_acceptance_hash_mismatch")
    acceptance = strict_json(acceptance_raw)
    delivery_path = baseline / "final-build" / "delivery.json"
    delivery_raw = safe_path(delivery_path).read_bytes()
    expected_delivery_sha256 = _source_file_sha256(
        _sources,
        spec.baseline_root / "final-build" / "delivery.json",
        spec.delivery_sha256,
    )
    if _sha(delivery_raw) != expected_delivery_sha256:
        raise ValueError("curry_baseline_delivery_hash_mismatch")
    delivery = strict_json(delivery_raw)
    delivery_audit, protected_delivery = _verify_curry_delivery(
        repo, baseline, acceptance, delivery, spec, _sources=_sources,
    )
    protected.update(protected_delivery)
    protected[Path(os.path.abspath(acceptance_path))] = _sha(acceptance_raw)
    protected[Path(os.path.abspath(delivery_path))] = _sha(delivery_raw)

    if stable_source(repo) != source_before:
        raise ValueError("curry_workspace_changed_during_baseline_audit")
    if _snapshot_curry_evidence(baseline) != evidence_snapshot:
        raise ValueError("curry_baseline_evidence_changed_during_audit")
    protected[baseline] = _curry_evidence_hash(evidence_snapshot)
    for path, expected in protected.items():
        if _protected_curry_hash(path, baseline) != expected:
            raise ValueError("curry_protected_history_changed")
    return {
        "prior": prior,
        "acceptance_sha256": _sha(acceptance_raw),
        "delivery_sha256": _sha(delivery_raw),
        "delivery": delivery_audit,
    }, protected


def _verify_option_verification_baseline(
    repo: Path, baseline_dir: Path,
    *, _profile: Any | None = None, _reservation_spec: Any | None = None,
    _sources: Any | None = None, _option_spec: Any | None = None,
    _candidate_spec: Any | None = None,
    source_collector: Callable[[Path], dict] | None = None,
) -> tuple[dict, dict[Path, str]]:
    """Re-run the saved V3 reservation verifier and bind its accepted output.

    This is a read-only source gate. It neither opens the new scope journal nor
    scans current engine assets. The reservation itself remains a planning
    policy record, never a native debit.
    """
    from ygo_data.identity import stable_source
    from ygo_eval.curry_consumption_reservation import (
        _production_profile, _snapshot_tree, _verify_saved, _version_spec,
    )

    repo = Path(os.path.abspath(repo))
    baseline = Path(os.path.abspath(baseline_dir))
    option_spec = _option_spec or OPTION_VERIFICATION_SCOPE
    collector = source_collector or stable_source
    if baseline != repo / option_spec.baseline_root or baseline.is_symlink():
        raise ValueError("curry_option_verification_fixed_reservation_required")

    source_before = collector(repo)
    tree_before = _snapshot_tree(baseline)
    reservation_path = baseline / "reservation.json"
    acceptance_path = baseline / "delivery" / "acceptance.json"
    reservation_raw = safe_path(reservation_path).read_bytes()
    acceptance_raw = safe_path(acceptance_path).read_bytes()
    reservation_hash = _sha(reservation_raw)
    acceptance_hash = _sha(acceptance_raw)
    reservation_sources = _sources.child("reservation") if _sources is not None else None
    expected_reservation_hash = (
        reservation_sources.file_sha256_role("v3_reservation_report")
        if reservation_sources is not None else option_spec.reservation_sha256
    )
    expected_acceptance_hash = (
        reservation_sources.file_sha256_role("v3_reservation_acceptance")
        if reservation_sources is not None else option_spec.baseline_acceptance_sha256
    )
    if reservation_hash != expected_reservation_hash:
        raise ValueError("curry_option_verification_reservation_anchor_mismatch")
    if acceptance_hash != expected_acceptance_hash:
        raise ValueError("curry_option_verification_acceptance_anchor_mismatch")

    reservation = strict_json(reservation_raw)
    acceptance = strict_json(acceptance_raw)
    verification = _verify_saved(
        argparse.Namespace(report_version=3), repo,
        _profile or _production_profile(), baseline,
        reservation_path, _reservation_spec or _version_spec(3),
    )
    # `_verify_saved` has just revalidated this object against its authenticated
    # source tree. Preserve the report's pinned manifest/context identity while
    # independently enforcing the fixed confirmation-scope semantics here.
    old_scope = reservation.get("old_scope")
    old_scope_valid = (
        isinstance(old_scope, dict)
        and set(old_scope) == {
            "scope", "context", "manifest_sha256", "request_limit",
            "window_seconds", "prepared", "charge_ledger_state",
            "sealed_unconsumed_slots", "actual_new_consumed",
            "actual_cumulative_consumed", "actual_unknown",
        }
        and old_scope.get("scope") == "curry-option-confirmation-v1"
        and HASH.fullmatch(str(old_scope.get("context", ""))) is not None
        and HASH.fullmatch(str(old_scope.get("manifest_sha256", ""))) is not None
        and type(old_scope.get("request_limit")) is int
        and old_scope["request_limit"] == 7
        and type(old_scope.get("window_seconds")) is int
        and old_scope["window_seconds"] == 7200
        and old_scope.get("prepared") is True
        and old_scope.get("charge_ledger_state") == "absent"
        and type(old_scope.get("sealed_unconsumed_slots")) is int
        and old_scope["sealed_unconsumed_slots"] == 7
        and all(old_scope.get(name) is None for name in (
            "actual_new_consumed", "actual_cumulative_consumed", "actual_unknown",
        ))
    )
    qualifications = {
        "proof_ready": False,
        "complete_action_coverage": False,
        "global_optimality": False,
        "native_probability_verified": False,
    }
    expected_reservation = {
        "duplicate_count": 1,
        "policy_id": option_spec.reservation_policy_id,
        "recorded": True,
        "requested_calls": 7,
        "reservation_id": option_spec.reservation_id,
    }
    expected_history = {
        "consumed": 32,
        "ledger_count": 9,
        "unknown": 0,
        "verified_by_anchored_read_only_protection": True,
    }
    expected_planning = {
        "actual_all_history_cumulative": None,
        "certified_historical_consumed": 32,
        "planned_total": 39,
        "risk_reserve_calls": 7,
    }
    if (not old_scope_valid
            or verification.get("valid") is not True
            or verification.get("reservation_id") != option_spec.reservation_id
            or reservation.get("status") != "passed"
            or reservation.get("native_calls") != 0
            or reservation.get("execution_ready") is not False
            or reservation.get("historical_ledgers") != expected_history
            or reservation.get("reservation") != expected_reservation
            or reservation.get("planning_basis") != expected_planning
            or reservation.get("qualifications") != qualifications
            or acceptance.get("schema_version") != 1
            or acceptance.get("kind") != "curry_consumption_reservation_v3_delivery_acceptance"
            or acceptance.get("status") != "passed"
            or acceptance.get("native_calls") != 0
            or acceptance.get("execution_ready") is not False
            or acceptance.get("reservation_report_sha256") != reservation_hash
            or acceptance.get("reservation") != expected_reservation
            or acceptance.get("old_scope") != old_scope
            or acceptance.get("historical_ledgers") != expected_history
            or acceptance.get("planning_basis") != expected_planning
            or acceptance.get("qualifications") != qualifications
            or acceptance.get("verification", {}).get("valid") is not True
            or acceptance.get("verification", {}).get("native_calls") != 0):
        raise ValueError("curry_option_verification_reservation_content_mismatch")

    # The candidate files come from the frozen validation run, whose manifest
    # binds their raw bytes. They are not taken from the V3 reservation output.
    candidate_spec = _candidate_spec or CURRY_SCOPE
    candidate_root = repo / candidate_spec.output_root
    candidate_manifest_path = candidate_root / "research" / "manifest.json"
    candidate_manifest_raw = safe_path(candidate_manifest_path).read_bytes()
    candidate_sources = (
        _sources.child("validation_candidate_scope") if _sources is not None else None
    )
    expected_manifest_hash = (
        candidate_sources.file_sha256_role("validation_manifest")
        if candidate_sources is not None else OLD_VALIDATION_MANIFEST_SHA256
    )
    if _sha(candidate_manifest_raw) != expected_manifest_hash:
        raise ValueError("curry_option_verification_old_manifest_anchor_mismatch")
    candidate_manifest = strict_json(candidate_manifest_raw)
    validate_curry_report(
        candidate_manifest, repo=repo, spec=candidate_spec, _sources=_sources,
    )
    candidate_input_hashes = candidate_manifest.get("input_sha256", {})
    candidate_paths = {
        "ordinary_config": candidate_root / "ordinary-candidate.toml",
        "tournament_config": candidate_root / "tournament-candidate.toml",
    }
    expected_candidate_hashes = (
        {
            "ordinary_config": candidate_sources.file_sha256_role(
                "validation_ordinary_config",
            ),
            "tournament_config": candidate_sources.file_sha256_role(
                "validation_tournament_config",
            ),
        }
        if candidate_sources is not None else {
            "ordinary_config": OLD_VALIDATION_ORDINARY_CONFIG_SHA256,
            "tournament_config": OLD_VALIDATION_TOURNAMENT_CONFIG_SHA256,
        }
    )
    for role, path in candidate_paths.items():
        if (candidate_input_hashes.get(role) != expected_candidate_hashes[role]
                or _sha(safe_path(path).read_bytes()) != expected_candidate_hashes[role]):
            raise ValueError(f"curry_option_verification_{role}_mismatch")

    if (collector(repo) != source_before or _snapshot_tree(baseline) != tree_before):
        raise ValueError("curry_option_verification_baseline_changed_during_audit")
    protected: dict[Path, str] = {
        baseline: _sha(canonical(tree_before)),
        reservation_path: reservation_hash,
        acceptance_path: acceptance_hash,
        candidate_manifest_path: _sha(candidate_manifest_raw),
    }
    protected.update({path: expected_candidate_hashes[role]
                      for role, path in candidate_paths.items()})
    _add_v3_reservation_input_protections(protected, repo, reservation)
    absent_confirmation_ledger = (
        repo / CONFIRMATION_SCOPE.output_root / "research" / "calls.jsonl"
    )
    if absent_confirmation_ledger.exists() or absent_confirmation_ledger.is_symlink():
        raise ValueError("curry_confirmation_charge_ledger_unexpected")
    _merge_protected_pin(protected, absent_confirmation_ledger,
                         ABSENT_PROTECTION_SENTINEL)
    for path, expected in protected.items():
        if _option_verification_protected_hash(path, repo) != expected:
            raise ValueError("curry_option_verification_protected_input_changed")
    return {
        "reservation_sha256": reservation_hash,
        "acceptance_sha256": acceptance_hash,
        "reservation_id": option_spec.reservation_id,
        "policy_id": option_spec.reservation_policy_id,
        "certified_historical_consumed": 32,
        "policy_reserved": 7,
        "planning_base": 39,
        "reservation_verification": verification,
    }, protected


def _option_revalidation_protected_hash(
    path: Path, repo: Path, *, _source_description: Any | None = None,
) -> str:
    """Hash the fixed V3 recovery and reservation roots with their tree semantics."""
    source = _source_description or _production_option_revalidation_source()
    return _option_revalidation_protected_hash_for_source(path, repo, source)


def _verify_option_revalidation_baseline(
    repo: Path, baseline_dir: Path,
    *, source_collector: Callable[[Path], dict] | None = None,
    _source_description: Any | None = None,
) -> tuple[dict, dict[Path, str]]:
    """Reverify the saved V3 recovery and reservation evidence without a runner."""
    from ygo_data.identity import stable_source
    from ygo_eval.curry_consumption_reservation import _snapshot_tree
    from ygo_eval.curry_ledger_handoff_recovery import (
        V3_PROFILE, V3_SPEC, _verify_only, _tree_snapshot,
    )

    if _source_description is None:
        _source_description = _production_option_revalidation_source()
    scope_spec = _source_description.scope_spec
    recovery_profile = _source_description.recovery_profile
    recovery_spec = _source_description.recovery_version_spec
    option_spec = _source_description.option_verification_spec
    candidate_spec = _source_description.candidate_spec

    repo = Path(os.path.abspath(repo))
    baseline = Path(os.path.abspath(baseline_dir))
    expected_root = repo / scope_spec.baseline_root
    if baseline != expected_root or baseline.is_symlink():
        raise ValueError("curry_option_revalidation_fixed_baseline_required")
    collector = source_collector or stable_source
    source_before = collector(repo)
    recovery_tree_before = _tree_snapshot(baseline)
    recovery_path = baseline / "recovery-report.json"
    delivery_path = baseline / "final-build" / "delivery-final.json"
    recovery_raw = safe_path(recovery_path).read_bytes()
    delivery_raw = safe_path(delivery_path).read_bytes()
    if _sha(recovery_raw) != scope_spec.baseline_recovery_sha256:
        raise ValueError("curry_option_revalidation_recovery_anchor_mismatch")
    if _sha(delivery_raw) != scope_spec.delivery_sha256:
        raise ValueError("curry_option_revalidation_delivery_anchor_mismatch")
    recovery = strict_json(recovery_raw)
    delivery = strict_json(delivery_raw)
    verification = _verify_only(
        repo, baseline, recovery_path, source_collector=collector,
        _sources=_source_description.recovery_sources,
        _reservation_profile=_source_description.reservation_profile,
        _reservation_spec=_source_description.reservation_spec,
        _option_spec=option_spec, _candidate_spec=candidate_spec,
        _profile=recovery_profile, version_spec=recovery_spec,
    )
    if (verification.get("valid") is not True
            or verification.get("native_calls") != 0
            or verification.get("runner_process_calls") != 0
            or recovery.get("status") != "passed"
            or recovery.get("valid") is not True
            or recovery.get("native_calls") != 0
            or recovery.get("runner_process_calls") != 0
            or recovery.get("accounting", {}).get(
                "certified_historical_consumed_including_scope"
            ) != 33
            or recovery.get("accounting", {}).get("planning_total") != 40
            or delivery.get("kind") != "curry_ledger_handoff_recovery_v3_final_delivery"
            or delivery.get("status") != "passed"
            or delivery.get("report", {}).get("sha256") != _sha(recovery_raw)
            or delivery.get("report", {}).get("path") != "../recovery-report.json"
            or delivery.get("source_after_docs", {}).get("workspace_identity") !=
                _source_description.recovery_delivery_workspace_identity
            or delivery.get("source_after_docs", {}).get("file_count") !=
                _source_description.recovery_delivery_workspace_file_count):
        raise ValueError("curry_option_revalidation_recovery_content_mismatch")

    # Re-run the existing immutable V3 reservation verifier at its own fixed root.
    reservation_info, reservation_protected = _verify_option_verification_baseline(
        repo, repo / option_spec.baseline_root,
        _profile=_source_description.reservation_profile,
        _reservation_spec=_source_description.reservation_spec,
        _sources=_source_description.reservation_sources,
        _option_spec=option_spec,
        _candidate_spec=candidate_spec,
        source_collector=collector,
    )
    if (reservation_info.get("reservation_id") != scope_spec.reservation_id
            or reservation_info.get("policy_id") != scope_spec.reservation_policy_id
            or reservation_info.get("certified_historical_consumed") != 32
            or reservation_info.get("planning_base") != 39):
        raise ValueError("curry_option_revalidation_reservation_content_mismatch")
    if collector(repo) != source_before or _tree_snapshot(baseline) != recovery_tree_before:
        raise ValueError("curry_option_revalidation_baseline_changed_during_audit")
    protected = dict(reservation_protected)
    protected[baseline] = _sha(canonical(recovery_tree_before))
    protected[recovery_path] = _sha(recovery_raw)
    protected[delivery_path] = _sha(delivery_raw)
    # The old reserve report remains separately rooted and is protected by the verifier above.
    for path, expected in protected.items():
        if _option_revalidation_protected_hash_for_source(path, repo, _source_description) != expected:
            raise ValueError("curry_option_revalidation_protected_input_changed")
    return {
        "recovery_sha256": _sha(recovery_raw),
        "delivery_sha256": _sha(delivery_raw),
        "reservation_id": scope_spec.reservation_id,
        "reservation_policy_id": scope_spec.reservation_policy_id,
        "certified_historical_consumed": 33,
        "policy_reserved": 7,
        "planning_base": 40,
        "recovery_verification": verification,
        "reservation_verification": reservation_info.get("reservation_verification"),
    }, protected


def _production_option_revalidation_source() -> Any:
    """Return the immutable, fixed V3/V3-reservation source description."""
    from ygo_eval.curry_ledger_handoff_recovery import V3_PROFILE, V3_SPEC
    from ygo_eval.native_curry_option_validation import CURRY_SCOPE as candidate_spec

    # Local import avoids a top-level cycle while keeping all production source
    # pins in their existing constants and fixed version configurations.
    from ygo_eval.ground_collapse_preparation import (
        GroundCollapseRevalidationSource,
    )

    return GroundCollapseRevalidationSource(
        scope_spec=OPTION_REVALIDATION_SCOPE,
        recovery_profile=V3_PROFILE,
        recovery_version_spec=V3_SPEC,
        recovery_sources=None,
        reservation_profile=None,
        reservation_spec=None,
        reservation_sources=None,
        option_verification_spec=OPTION_VERIFICATION_SCOPE,
        candidate_spec=candidate_spec,
        recovery_delivery_workspace_identity=(
            V3_PROFILE.delivery_source_after_docs_identity
        ),
        recovery_delivery_workspace_file_count=(
            V3_PROFILE.delivery_source_after_docs_file_count
        ),
    )


def _option_revalidation_protected_hash_for_source(path: Path, repo: Path, source: Any) -> str:
    """Use the same fixed directory semantics for the selected immutable source tree."""
    from ygo_eval.curry_consumption_reservation import _snapshot_tree
    from ygo_eval.curry_ledger_handoff_recovery import _tree_snapshot

    path = Path(os.path.abspath(path))
    repo = Path(os.path.abspath(repo))
    if not path.is_relative_to(repo) or path.is_symlink():
        raise ValueError("curry_option_revalidation_protected_path_invalid")
    if path == repo / source.scope_spec.baseline_root:
        return _sha(canonical(_tree_snapshot(path)))
    if path == repo / source.option_verification_spec.baseline_root:
        return _sha(canonical(_snapshot_tree(path)))
    return _option_verification_protected_hash(path, repo)


def _verify_confirmation_baseline(
    repo: Path, baseline_dir: Path,
    *, _sources: Any | None = None,
) -> tuple[dict, dict[Path, str]]:
    """Verify the latest Curry audit without inventing a missing acceptance file."""
    from ygo_data.identity import stable_source
    from ygo_eval.curry_asset_binding_audit import (
        ALLOWED_ARCHIVE_DIFFS,
        ARCHIVE_ANCHORS,
        _snapshot_tree,
        _verify_archive,
        _verify_curry_scope,
        _verify_historical_chain,
        validate_report as validate_asset_audit,
    )

    repo = Path(os.path.abspath(repo))
    baseline = Path(os.path.abspath(baseline_dir))
    if baseline != repo / CONFIRMATION_SCOPE.baseline_root or baseline.is_symlink():
        raise ValueError("curry_fixed_confirmation_baseline_required")
    source_before = stable_source(repo)
    tree_before = _snapshot_tree(baseline)
    audit_path = baseline / "audit-report.json"
    delivery_path = baseline / "final-build" / "delivery.json"
    audit_raw = safe_path(audit_path).read_bytes()
    delivery_raw = safe_path(delivery_path).read_bytes()
    audit_sha256 = _source_file_sha256(
        _sources,
        CONFIRMATION_SCOPE.baseline_root / "audit-report.json",
        CONFIRMATION_AUDIT_SHA256,
    )
    delivery_sha256 = _source_file_sha256(
        _sources,
        CONFIRMATION_SCOPE.baseline_root / "final-build" / "delivery.json",
        CONFIRMATION_DELIVERY_SHA256,
    )
    if _sha(audit_raw) != audit_sha256:
        raise ValueError("curry_confirmation_audit_anchor_mismatch")
    if _sha(delivery_raw) != delivery_sha256:
        raise ValueError("curry_confirmation_delivery_anchor_mismatch")
    audit = strict_json(audit_raw)
    delivery = strict_json(delivery_raw)
    validate_asset_audit(
        audit, repo=repo, artifact_root=baseline,
        **({"_sources": _source_child(_sources, "asset_audit_scope")}
           if _sources is not None else {}),
    )
    expected_document_diffs = (
        list(_sources.differences("asset_audit")) if _sources is not None else sorted({
            "TASKS.md", "docs/TESTING.md",
            "docs/superpowers/plans/2026-10-24-curry-asset-binding-audit-handoff.md",
        })
    )
    historical_consumed = _source_dataset_count(_sources, "historical_consumed", 32)
    historical_unknown = _source_dataset_count(_sources, "historical_unknown", 0)
    historical_ledger_count = _source_dataset_count(_sources, "historical_ledgers", 9)
    audit_input_count = _source_dataset_count(_sources, "asset_audit_inputs", 548)
    historical_material_count = _source_dataset_count(
        _sources, "historical_material_inputs", 518,
    )
    audit_protected_file_count = _source_dataset_count(
        _sources, "asset_audit_protected_files", 24,
    )
    audit_source_file_count = _source_dataset_count(
        _sources, "asset_audit_source_files", 498,
    )
    audit_archive_records = {
        item.get("role"): item for item in audit.get("source_archives", [])
        if isinstance(item, dict)
    }
    native_audit_archive = audit_archive_records.get("native_time", {})
    final_audit_archive = audit_archive_records.get("final", {})
    asset_native_archive = _source_archive(
        _sources, "asset_audit_native_archive", {
            "archive_sha256": native_audit_archive.get("sha256", ""),
            "file_list_sha256": native_audit_archive.get("file_list_sha256", ""),
            "source_identity": "43f4518145e6fa0157896c96f6d48dcd9df89c80f24d64bfc6a116b6be7e62f2",
            "file_count": audit_source_file_count, "head": "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
            "archive_path": "data/runtime/p1-curry-asset-binding-offline-2026-10-24/source-native.zip",
            "file_list_path": "data/runtime/p1-curry-asset-binding-offline-2026-10-24/source-native-file-list.json",
        },
    )
    asset_final_archive = _source_archive(
        _sources, "asset_audit_final_archive", {
            "archive_sha256": final_audit_archive.get("sha256", ""),
            "file_list_sha256": final_audit_archive.get("file_list_sha256", ""),
            "source_identity": "2a9f15766a3da34016e1b9b790f7f530809fceb4a6a761f37ce16451334a271b",
            "file_count": 499, "head": "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
            "archive_path": "data/runtime/p1-curry-asset-binding-offline-2026-10-24/final-build/source-native.zip",
            "file_list_path": "data/runtime/p1-curry-asset-binding-offline-2026-10-24/final-build/source-native-file-list.json",
        },
    )
    if (asset_native_archive["file_count"] != audit_source_file_count
            or asset_final_archive["file_count"] != 499):
        raise ValueError("curry_confirmation_source_archive_count_mismatch")
    history = audit.get("history")
    if (audit.get("status") != "passed" or audit.get("native_calls") != 0
            or audit.get("execution_ready") is not False
            or not isinstance(history, dict)
            or (history.get("consumed"), history.get("unknown"), history.get("ledger_count"),
                history.get("verified_without_writable_journal")) != (
                    historical_consumed, historical_unknown, historical_ledger_count, True,
                )
            or historical_consumed != 32 or historical_unknown != 0
            or historical_ledger_count != 9
            or len(audit.get("inputs", [])) != audit_input_count
            or sum(item.get("role", "").startswith("historical_material_")
                   for item in audit.get("inputs", [])) != historical_material_count
            or audit.get("protection", {}).get("file_count") != audit_protected_file_count
            or audit.get("source", {}).get("workspace_identity") !=
                asset_native_archive["source_identity"]
            or audit.get("source", {}).get("workspace_file_count") != audit_source_file_count
            or audit.get("source", {}).get("source_archive_differences") != expected_document_diffs):
        raise ValueError("curry_confirmation_audit_content_mismatch")
    if (delivery.get("schema_version") != 1
            or delivery.get("kind") != "curry_asset_binding_final_delivery"
            or delivery.get("status") != "recorded"
            or delivery.get("native_calls") != 0
            or delivery.get("execution_ready") is not False
            or delivery.get("reproducible_build_proven") is not False
            or delivery.get("source_identity") !=
                asset_final_archive["source_identity"]
            or delivery.get("source_file_count") != asset_final_archive["file_count"]
            or delivery.get("source_archive_sha256") != asset_final_archive["archive_sha256"]
            or delivery.get("source_file_list_sha256") != asset_final_archive["file_list_sha256"]
            or delivery.get("qualifications") != FLAGS):
        raise ValueError("curry_confirmation_delivery_content_mismatch")

    # Re-hash all 548 inputs with the audit's established file/directory rules.
    for item in audit["inputs"]:
        relative = item["path"]
        if (not isinstance(relative, str) or Path(relative).is_absolute()
                or "\\" in relative or ":" in relative
                or ".." in Path(relative).parts):
            raise ValueError("curry_confirmation_audit_input_path_invalid")
        candidate = repo / Path(relative)
        path = safe_path(candidate, file=not candidate.is_dir())
        if path.is_dir():
            found = _protected_curry_hash(path, path)
            if item.get("bytes") != 0:
                raise ValueError("curry_confirmation_audit_directory_length_invalid")
        else:
            raw = path.read_bytes()
            found = _sha(raw)
            if len(raw) != item.get("bytes"):
                raise ValueError("curry_confirmation_audit_input_length_mismatch")
        if found != item.get("sha256"):
            raise ValueError("curry_confirmation_audit_input_hash_mismatch")

    # Verify the audit's archived old-build sources against fixed anchors.
    old_curry_root = repo / CURRY_SCOPE.output_root
    curry_source_node = _confirmation_archive_source_scope(_sources)
    curry_native_archive = _source_archive(
        curry_source_node, "curry_native_archive", {
            **ARCHIVE_ANCHORS["native_time"],
            "head": "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
            "archive_path": (
                CURRY_SCOPE.output_root / "source-native.zip"
            ).as_posix(),
            "file_list_path": (
                CURRY_SCOPE.output_root / "source-native-file-list.json"
            ).as_posix(),
        },
    )
    curry_final_archive = _source_archive(
        curry_source_node, "curry_final_archive", {
            **ARCHIVE_ANCHORS["final"],
            "head": "8a6b2f6762131aebea6d8c0f5f61363d573f1b36",
            "archive_path": (
                CURRY_SCOPE.output_root / "final-build/source-native.zip"
            ).as_posix(),
            "file_list_path": (
                CURRY_SCOPE.output_root / "final-build/source-native-file-list.json"
            ).as_posix(),
        },
    )
    expected_native_root = CURRY_SCOPE.output_root.as_posix().rstrip("/") + "/"
    if (not curry_native_archive["archive_path"].startswith(expected_native_root)
            or not curry_native_archive["file_list_path"].startswith(expected_native_root)
            or not curry_final_archive["archive_path"].startswith(expected_native_root)
            or not curry_final_archive["file_list_path"].startswith(expected_native_root)):
        raise ValueError("curry_confirmation_old_archive_path_mismatch")
    archive_native_files, archive_native = _verify_archive(
        old_curry_root,
        Path(curry_native_archive["archive_path"]).relative_to(CURRY_SCOPE.output_root).as_posix(),
        Path(curry_native_archive["file_list_path"]).relative_to(CURRY_SCOPE.output_root).as_posix(),
        curry_native_archive,
    )
    archive_final_files, archive_final = _verify_archive(
        old_curry_root,
        Path(curry_final_archive["archive_path"]).relative_to(CURRY_SCOPE.output_root).as_posix(),
        Path(curry_final_archive["file_list_path"]).relative_to(CURRY_SCOPE.output_root).as_posix(),
        curry_final_archive,
    )
    archive_diffs = sorted(
        name for name in archive_native_files.keys() | archive_final_files.keys()
        if archive_native_files.get(name) != archive_final_files.get(name)
    )
    expected_curry_diffs = (
        list(curry_source_node.differences("curry_baseline"))
        if _sources is not None else sorted(ALLOWED_ARCHIVE_DIFFS)
    )
    if (archive_diffs != sorted(expected_curry_diffs)
            or {item.get("role"): item for item in audit.get("source_archives", [])}
            != {"native_time": archive_native, "final": archive_final}):
        raise ValueError("curry_confirmation_audit_archive_binding_invalid")

    # Compare the audit-time and final-delivery workspace snapshots. The only
    # permitted changes are the two status documents and the new handoff.
    if _sources is None:
        source_specs = (
            ("source-native-file-list.json", "source-native.zip", asset_native_archive),
            ("final-build/source-native-file-list.json", "final-build/source-native.zip",
             asset_final_archive),
        )
    else:
        def archive_relative(pin: dict[str, Any], key: str) -> str:
            pin_path = Path(pin[key])
            try:
                return pin_path.relative_to(CONFIRMATION_SCOPE.baseline_root).as_posix()
            except ValueError:
                raise ValueError("curry_confirmation_source_archive_path_mismatch") from None

        source_specs = (
            (archive_relative(asset_native_archive, "file_list_path"),
             archive_relative(asset_native_archive, "archive_path"), asset_native_archive),
            (archive_relative(asset_final_archive, "file_list_path"),
             archive_relative(asset_final_archive, "archive_path"), asset_final_archive),
        )
    source_maps = []
    for list_rel, archive_rel, archive_pin in source_specs:
        list_path = safe_path(baseline / list_rel)
        archive_path = safe_path(baseline / archive_rel)
        listing_raw = list_path.read_bytes()
        listing = strict_json(listing_raw)
        files = listing.get("files") if isinstance(listing, dict) else None
        identity = archive_pin["source_identity"]
        if (not isinstance(files, dict) or listing.get("source_identity") != identity
                or listing.get("file_count") != len(files)
                or listing.get("file_count") != archive_pin["file_count"]
                or listing.get("head") != archive_pin["head"]
                or hashlib.sha256(canonical({"head": listing["head"], "files": files})).hexdigest() != identity):
            raise ValueError("curry_confirmation_workspace_source_list_invalid")
        identity = archive_pin["source_identity"]
        if _sha(listing_raw) != archive_pin["file_list_sha256"]:
            raise ValueError("curry_confirmation_delivery_source_list_hash_mismatch")
        archive_raw = archive_path.read_bytes()
        if _sha(archive_raw) != archive_pin["archive_sha256"]:
            raise ValueError("curry_confirmation_delivery_source_archive_hash_mismatch")
        import zipfile
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(files):
                raise ValueError("curry_confirmation_workspace_archive_membership_invalid")
            for name, digest_value in files.items():
                if (not isinstance(digest_value, str) or not HASH.fullmatch(digest_value)
                        or _sha(archive.read(name)) != digest_value):
                    raise ValueError("curry_confirmation_workspace_archive_hash_invalid")
        source_maps.append(files)
    diffs = sorted(
        name for name in source_maps[0].keys() | source_maps[1].keys()
        if source_maps[0].get(name) != source_maps[1].get(name)
    )
    if diffs != expected_document_diffs:
        raise ValueError("curry_confirmation_workspace_archive_diff_invalid")

    build_path = safe_path(baseline / "final-build" / "build-record.json")
    build_raw = build_path.read_bytes()
    if _sha(build_raw) != delivery.get("build_record_sha256"):
        raise ValueError("curry_confirmation_build_record_hash_mismatch")
    build = strict_json(build_raw)
    build_unsigned = {key: value for key, value in build.items() if key != "identity"}
    if (build.get("kind") != "build_record"
            or build.get("identity") != hashlib.sha256(canonical(build_unsigned)).hexdigest()
            or build.get("identity") != delivery.get("build_record_identity")
            or build.get("artifacts", {}).get("runner") != delivery.get("runner_sha256")):
        raise ValueError("curry_confirmation_build_record_binding_invalid")
    delivered_runner = safe_path(
        baseline / "final-build" / "native-artifacts" / "curry-option-validation.exe"
    )
    if _sha(delivered_runner.read_bytes()) != delivery.get("runner_sha256"):
        raise ValueError("curry_confirmation_delivered_runner_hash_mismatch")
    identity_path = safe_path(baseline / "final-build" / "source-identity.json")
    identity_raw = identity_path.read_bytes()
    identity_doc = strict_json(identity_raw)
    identity_unsigned = {key: value for key, value in identity_doc.items() if key != "identity"}
    if (_sha(identity_raw) != delivery.get("source_identity_file_sha256")
            or identity_doc.get("identity") != delivery.get("source_identity")
            or hashlib.sha256(canonical(identity_unsigned)).hexdigest() != identity_doc.get("identity")):
        raise ValueError("curry_confirmation_delivery_identity_invalid")

    # Validate the old Curry static candidate/config sources separately.
    old_curry = _verify_curry_scope(
        repo, old_curry_root,
        **({"_sources": _source_child(_sources, "asset_audit_scope")}
           if _sources is not None else {}),
    )
    old_manifest = strict_json(safe_path(old_curry_root / "research/manifest.json").read_bytes())
    for role, filename in (("ordinary_config", "ordinary-candidate.toml"),
                           ("tournament_config", "tournament-candidate.toml")):
        candidate_path = safe_path(old_curry_root / filename)
        if _sha(candidate_path.read_bytes()) != old_manifest.get("input_sha256", {}).get(role):
            raise ValueError("curry_confirmation_candidate_config_source_mismatch")

    historical, protected = _verify_historical_chain(
        repo,
        **({"_sources": _source_child(_sources, "historical_chain")}
           if _sources is not None else {}),
    )
    if (historical.get("consumed"), historical.get("unknown"), historical.get("ledger_count")) != (
            historical_consumed, historical_unknown, historical_ledger_count):
        raise ValueError("curry_confirmation_historical_totals_mismatch")
    protected.update(old_curry.get("protected", {}))
    protected[Path(os.path.abspath(audit_path))] = audit_sha256
    protected[Path(os.path.abspath(delivery_path))] = delivery_sha256
    protected[Path(os.path.abspath(baseline))] = _sha(canonical(_snapshot_tree(baseline)))
    if stable_source(repo) != source_before or _snapshot_tree(baseline) != tree_before:
        raise ValueError("curry_confirmation_inputs_changed_during_baseline_check")
    for path, expected in protected.items():
        found = _confirmation_protected_hash(path, repo)
        if found != expected:
            raise ValueError("curry_confirmation_protected_input_changed")
    return {
        "audit_sha256": CONFIRMATION_AUDIT_SHA256,
        "delivery_sha256": CONFIRMATION_DELIVERY_SHA256,
        "audit": audit,
        "delivery": delivery,
        "history": historical,
        "old_curry": old_curry,
    }, protected


def _process_diagnostics_with_hash(root: Path, wanted_sha256: str, mode: str,
                                   spec: CurryScopeSpec, *,
                                   diagnostic_hash: Callable[[Path, dict], str]) -> list[dict]:
    """Return only diagnostics whose metadata and raw streams match the pinned digest."""
    directory = safe_path(root / "process-diagnostics", file=False)
    if not directory.is_dir():
        raise ValueError("curry_saved_process_diagnostics_missing")
    matches: list[dict] = []
    for metadata_path in directory.glob("*.json"):
        try:
            record = strict_json(safe_path(metadata_path).read_bytes())
            relative = metadata_path.relative_to(root).as_posix()
            if (record.get("metadata_path") != relative
                    or record.get("mode") != mode
                    or record.get("runner_role") != spec.runner_role):
                continue
            found = diagnostic_hash(root, record)
        except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError):
            continue
        if found == wanted_sha256:
            matches.append(record)
    return matches


def _verify_curry_stage_artifacts(
    *, root: Path, research: Path, manifest: dict, stage: int,
    expected_request: dict, stage_summary: dict, spec: CurryScopeSpec,
    report_kind: str = "native_tenki_placement_validation_stage_report",
    stdout_contract: str = "legacy-v1",
    stdout_contract_spec: CurryScopeSpec | None = None,
    validate_report: Callable[[dict], Any],
    diagnostic_hash: Callable[[Path, dict], str],
) -> dict:
    """Cross-bind a saved stage request, sealed invocation, receipt, report and raw process output."""
    from ygo_eval.native_tenki_placement_validation import _verify_stage_intent

    context = manifest.get("context")
    if (type(stage) is not int or stage not in range(1, spec.limit + 1)
            or not isinstance(context, str) or not HASH.fullmatch(context)):
        raise ValueError("curry_saved_stage_manifest_binding_invalid")
    request_path = safe_path(research / f"stage-{stage}-request.json")
    input_path = safe_path(research / f"stage-{stage}-input.json")
    seal_path = safe_path(research / f"stage-{stage}-input-seal.json")
    receipt_path = safe_path(research / f"stage-{stage}.json")
    report_path = safe_path(research / f"stage-{stage}-report.json")
    request = strict_json(request_path.read_bytes())
    invocation = strict_json(input_path.read_bytes())
    seal = strict_json(seal_path.read_bytes())
    receipt_raw = receipt_path.read_bytes()
    receipt = strict_json(receipt_raw)
    report = strict_json(report_path.read_bytes())
    if not _strict_equal(request, expected_request):
        raise ValueError("curry_saved_parent_request_derivation_mismatch")
    try:
        _verify_stage_intent(
            input_path, research, context, stage, expected_request,
            manifest["assets"]["ordinary"], manifest["started_at"], spec,
        )
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
        raise ValueError("curry_saved_stage_intent_invalid") from error
    if (not _strict_equal(invocation.get("request"), expected_request)
            or invocation.get("context") != context
            or invocation.get("stage") != stage
            or invocation.get("batch_kind") != spec.batch_kind
            or seal.get("context") != context
            or seal.get("stage") != stage):
        raise ValueError("curry_saved_stage_intent_invalid")
    if (receipt.get("context") != context or receipt.get("stage") != stage
            or not _strict_equal(receipt.get("request"), expected_request)):
        raise ValueError("curry_saved_stage_receipt_binding_invalid")
    if report.get("kind") != report_kind:
        raise ValueError("curry_saved_stage_report_kind_invalid")
    if report.get("context") != context or report.get("stage") != stage:
        raise ValueError("curry_saved_stage_report_identity_invalid")
    if report.get("successful") is not True:
        raise ValueError("curry_saved_stage_report_unsuccessful")
    if report.get("receipt_sha256") != _sha(receipt_raw):
        raise ValueError("curry_saved_stage_report_receipt_hash_invalid")
    if not _strict_equal(report.get("ledger"), receipt.get("ledger")):
        raise ValueError("curry_saved_stage_report_ledger_invalid")
    validate_report(report)
    expected_summary = {key: report.get(key) for key in (
        "stage", "successful", "native_calls", "diagnostic", "receipt_sha256",
        "diagnostic_sha256", "independent_replay_matches", "ledger",
    )}
    if not _strict_equal(stage_summary, expected_summary):
        raise ValueError("curry_saved_stage_summary_binding_invalid")
    diagnostic_sha256 = report.get("diagnostic_sha256")
    matches = _process_diagnostics_with_hash(
        root, diagnostic_sha256, "normal", spec,
        diagnostic_hash=diagnostic_hash,
    )
    if len(matches) != 1:
        raise ValueError("curry_saved_stage_diagnostic_missing")
    process_record = matches[0]
    output = strict_json(safe_path(root / process_record["stdout"]["path"]).read_bytes())
    process_sidecar = strict_json(
        safe_path(root / f"stage-{stage}-process-diagnostic.json").read_bytes()
    )
    if not _strict_equal(process_sidecar, process_record):
        raise ValueError("curry_saved_stage_diagnostic_sidecar_mismatch")
    if diagnostic_hash(root, process_sidecar) != diagnostic_sha256:
        raise ValueError("curry_saved_stage_diagnostic_sidecar_hash_invalid")
    from ygo_eval.curry_ledger_handoff_audit import _expected_curry_stage_process_output
    expected_process_output = _expected_curry_stage_process_output(
        manifest, receipt, stdout_contract=stdout_contract,
        option_spec=stdout_contract_spec,
    )
    if (process_record.get("status") != "completed"
            or process_record.get("return_code") != 0
            or process_record.get("error_code") is not None
            or not _strict_equal(output, expected_process_output)):
        raise ValueError("curry_saved_stage_process_output_invalid")
    return {"receipt": receipt, "report": report,
            "diagnostic_record": process_record}


def _verify_curry_auxiliary_diagnostics(
    *, root: Path, manifest: dict, prepared: dict, prepared_raw: bytes,
    manifest_raw: bytes, summary: dict, verification: dict,
    stage1_input_raw: bytes, spec: CurryScopeSpec,
    diagnostic_hash: Callable[[Path, dict], str],
) -> None:
    """Bind preflight and zero-call verification outputs to their saved reports."""
    from collections import Counter

    stage1_request_sha256 = hashlib.sha256(canonical(manifest["request"])).hexdigest()
    if (prepared.get("manifest_sha256") != _sha(manifest_raw)
            or prepared.get("stage1_input_sha256") != _sha(stage1_input_raw)
            or prepared.get("stage1_request_sha256") != stage1_request_sha256
            or prepared.get("preflight_diagnostic_sha256") is None
            or verification.get("prepared_sha256") != _sha(prepared_raw)
            or summary.get("stages") != verification.get("stages")):
        raise ValueError("curry_prepared_or_verification_binding_invalid")

    preflight_hash = prepared["preflight_diagnostic_sha256"]
    preflight_records = _process_diagnostics_with_hash(
        root, preflight_hash, "preflight_only", spec,
        diagnostic_hash=diagnostic_hash,
    )
    if len(preflight_records) != 1:
        raise ValueError("curry_preflight_diagnostic_missing")
    preflight = preflight_records[0]
    preflight_output = strict_json(
        safe_path(root / preflight["stdout"]["path"]).read_bytes()
    )
    if (preflight.get("status") != "completed" or preflight.get("return_code") != 0
            or preflight.get("error_code") is not None
            or preflight_output != {
                "context": manifest["context"],
                "identity_sha256": manifest["assets"]["ordinary"]["identity"],
                "native_calls": 0, "preflight_passed": True, "stage": 1,
            }):
        raise ValueError("curry_preflight_process_output_invalid")

    verification_hashes = verification.get("verification_diagnostic_sha256")
    if (not isinstance(verification_hashes, list)
            or len(verification_hashes) != spec.limit):
        raise ValueError("curry_verification_diagnostic_list_invalid")
    verification_records = []
    for expected_hash in verification_hashes:
        records = _process_diagnostics_with_hash(
            root, expected_hash, "verify_recorded", spec,
            diagnostic_hash=diagnostic_hash,
        )
        if len(records) != 1:
            raise ValueError("curry_verification_diagnostic_missing")
        record = records[0]
        output = strict_json(safe_path(root / record["stdout"]["path"]).read_bytes())
        expected_ledger = {
            "abandoned": 0, "completed": spec.limit, "consumed": spec.limit,
            "limit": spec.limit, "reserved": 0, "unknown": 0,
        }
        if (record.get("status") != "completed" or record.get("return_code") != 0
                or record.get("error_code") is not None
                or output != {"ledger": expected_ledger, "native_calls": 0,
                              "successful": True, "verified_recorded": True}):
            raise ValueError("curry_verification_process_output_invalid")
        verification_records.append(record)
    observed_hashes = []
    directory = safe_path(root / "process-diagnostics", file=False)
    for metadata_path in directory.glob("*.json"):
        try:
            record = strict_json(safe_path(metadata_path).read_bytes())
            if record.get("mode") != "verify_recorded":
                continue
            if record.get("metadata_path") != metadata_path.relative_to(root).as_posix():
                raise ValueError("process_diagnostic_metadata_path_invalid")
            observed_hashes.append(diagnostic_hash(root, record))
        except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError):
            continue
    if Counter(observed_hashes) != Counter(verification_hashes):
        raise ValueError("curry_verification_diagnostic_set_mismatch")


def _verify_curry_delivery(repo: Path, baseline: Path, acceptance: dict,
                           delivery: dict, spec: CurryScopeSpec, *,
                           _sources: Any | None = None) -> tuple[dict, dict[Path, str]]:
    """Recompute all anchors for the latest placement-validation delivery."""
    import zipfile

    from ygo_eval.native_tenki_placement import _validate_signed
    from ygo_eval.native_tenki_placement_confirmation import _audit_one_ledger
    from ygo_eval.native_tenki_placement_validation import (
        VALIDATION_SCOPE, _PARENT_BY_STAGE, _diagnostic_hash,
        _verify_basic_receipt, _verify_frozen_stage1_request,
        derive_stage_request, validate_report, validate_stage_receipt,
    )
    from ygo_eval.tenki_placement_diagnostics import _verify_archive

    evidence_snapshot = _snapshot_curry_evidence(baseline)
    if (acceptance.get("schema_version") != 1
            or acceptance.get("kind") != "tenki_placement_validation_acceptance"
            or acceptance.get("scope") != VALIDATION_SCOPE.scope
            or acceptance.get("status") != "completed_and_paused"
            or acceptance.get("qualifications") != FLAGS):
        raise ValueError("curry_baseline_acceptance_invalid")
    native = acceptance.get("native")
    accepted_delivery = acceptance.get("final_delivery")
    expected_delivery_sha256 = _source_file_sha256(
        _sources,
        spec.baseline_root / "final-build/delivery.json",
        spec.delivery_sha256,
    )
    if (not isinstance(native, dict)
            or native.get("old_consumed") != VALIDATION_SCOPE.old_consumed
            or native.get("new_consumed") != VALIDATION_SCOPE.limit
            or native.get("cumulative_consumed") != spec.old_consumed
            or native.get("unknown") != 0
            or native.get("stages_completed") != VALIDATION_SCOPE.limit
            or native.get("stages_total") != VALIDATION_SCOPE.limit
            or native.get("successful") is not True
            or native.get("scope_sealed") is not True
            or native.get("verify_only_native_calls") != 0
            or native.get("replay_matches") != {
                "false_branch_stage4": True, "true_branch_stage6": True,
            }
            or not isinstance(accepted_delivery, dict)
            or accepted_delivery.get("path") != "final-build/delivery.json"
            or accepted_delivery.get("sha256") != expected_delivery_sha256):
        raise ValueError("curry_baseline_acceptance_content_mismatch")
    if (delivery.get("schema_version") != 1
            or delivery.get("kind") != "tenki_placement_validation_final_delivery"
            or delivery.get("scope") != VALIDATION_SCOPE.scope
            or delivery.get("qualifications") != FLAGS):
        raise ValueError("curry_baseline_delivery_content_mismatch")

    evidence = delivery.get("native_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("curry_baseline_native_evidence_missing")
    for field in ("old_consumed", "new_consumed", "cumulative_consumed", "unknown"):
        if evidence.get(field) != native.get(field):
            raise ValueError("curry_baseline_native_totals_mismatch")
    if (evidence.get("verification_native_calls") != 0
            or evidence.get("ledger_path") != "../research/calls.jsonl"
            or evidence.get("summary_path") != "../research/summary.json"
            or evidence.get("verification_path") != "../research/verification.json"
            or native.get("ledger_path") != "research/calls.jsonl"
            or native.get("summary_path") != "research/summary.json"
            or native.get("verification_path") != "research/verification.json"):
        raise ValueError("curry_baseline_native_evidence_paths_invalid")

    research = baseline / "research"
    manifest_raw = safe_path(research / "manifest.json").read_bytes()
    manifest = strict_json(manifest_raw)
    summary_raw = safe_path(research / "summary.json").read_bytes()
    summary = strict_json(summary_raw)
    verification_raw = safe_path(research / "verification.json").read_bytes()
    verification = strict_json(verification_raw)
    if (_sha(summary_raw) != native.get("summary_sha256")
            or _sha(summary_raw) != evidence.get("summary_sha256")
            or _sha(verification_raw) != native.get("verification_sha256")
            or _sha(verification_raw) != evidence.get("verification_sha256")
            or _sha(safe_path(research / "calls.jsonl").read_bytes()) != native.get("ledger_sha256")
            or native.get("ledger_sha256") != evidence.get("ledger_sha256")):
        raise ValueError("curry_baseline_native_file_hash_mismatch")
    validate_report(manifest, repo=repo, spec=VALIDATION_SCOPE)
    validate_report(summary, repo=repo, spec=VALIDATION_SCOPE)
    validate_report(verification, repo=repo, spec=VALIDATION_SCOPE)
    if (manifest.get("context") != summary.get("context")
            or manifest.get("context") != verification.get("context")
            or summary.get("successful") is not True
            or summary.get("new_consumed") != VALIDATION_SCOPE.limit
            or summary.get("cumulative_consumed") != spec.old_consumed
            or summary.get("unknown") != 0
            or verification.get("valid") is not True
            or verification.get("native_calls") != 0
            or verification.get("new_consumed") != VALIDATION_SCOPE.limit
            or verification.get("cumulative_consumed") != spec.old_consumed
            or verification.get("unknown") != 0
            or summary.get("stages") != verification.get("stages")):
        raise ValueError("curry_baseline_validation_reports_invalid")
    _verify_frozen_stage1_request(
        repo, baseline, manifest, VALIDATION_SCOPE, _sources=_sources,
    )

    prepared_raw = safe_path(research / "prepared.json").read_bytes()
    prepared = strict_json(prepared_raw)
    validate_report(prepared, repo=repo, spec=VALIDATION_SCOPE)
    if (prepared.get("prepared") is not True
            or prepared.get("execution_ready") is not True
            or prepared.get("context") != manifest.get("context")
            or verification.get("prepared_sha256") != _sha(prepared_raw)):
        raise ValueError("curry_baseline_prepared_binding_invalid")

    stage_reports = verification.get("stages")
    if (not isinstance(stage_reports, list)
            or len(stage_reports) != VALIDATION_SCOPE.limit
            or [item.get("stage") if isinstance(item, dict) else None for item in stage_reports]
               != list(range(1, VALIDATION_SCOPE.limit + 1))):
        raise ValueError("curry_baseline_stage_summary_invalid")
    parent_receipts: dict[int, dict] = {}
    for stage, item in enumerate(stage_reports, 1):
        if stage == 1:
            expected_request = manifest["request"]
        else:
            parent = parent_receipts.get(_PARENT_BY_STAGE[stage])
            if parent is None:
                raise ValueError("curry_baseline_parent_receipt_missing")
            expected_request = derive_stage_request(stage, parent, VALIDATION_SCOPE)
        artifacts = _verify_curry_stage_artifacts(
            root=baseline, research=research, manifest=manifest, stage=stage,
            expected_request=expected_request, stage_summary=item,
            spec=VALIDATION_SCOPE, validate_report=lambda value: validate_report(
                value, repo=repo, spec=VALIDATION_SCOPE,
            ), diagnostic_hash=lambda root_path, record: _diagnostic_hash(
                root_path, record, VALIDATION_SCOPE,
            ),
        )
        receipt = artifacts["receipt"]
        _verify_basic_receipt(receipt, expected_request, manifest["context"],
                              stage, VALIDATION_SCOPE)
        if receipt.get("successful") is not True:
            raise ValueError("curry_baseline_stage_receipt_unsuccessful")
        validate_stage_receipt(
            receipt, expected_request, manifest["context"], stage,
            manifest["assets"]["ordinary"], VALIDATION_SCOPE,
        )
        parent_receipts[stage] = receipt
    stage1_input_raw = safe_path(research / "stage-1-input.json").read_bytes()
    _verify_curry_auxiliary_diagnostics(
        root=baseline, manifest=manifest, prepared=prepared,
        prepared_raw=prepared_raw, manifest_raw=manifest_raw,
        summary=summary, verification=verification,
        stage1_input_raw=stage1_input_raw, spec=VALIDATION_SCOPE,
        diagnostic_hash=lambda root_path, record: _diagnostic_hash(
            root_path, record, VALIDATION_SCOPE,
        ),
    )

    native_source = acceptance.get("native_source")
    final_source = delivery.get("final_source")
    final_archive_meta = delivery.get("source_archive")
    if (not isinstance(native_source, dict) or not isinstance(final_source, dict)
            or not isinstance(final_archive_meta, dict)
            or delivery.get("native_source_identity") != native_source.get("identity")
            or delivery.get("scope") != VALIDATION_SCOPE.scope):
        raise ValueError("curry_baseline_source_binding_missing")

    native_pin = _source_archive(_sources, "curry_native_archive", {
        "archive_sha256": native_source.get("archive_sha256", ""),
        "file_list_sha256": BASELINE_NATIVE_FILE_LIST_SHA256,
        "source_identity": native_source.get("identity", ""),
        "file_count": native_source.get("file_count", 0),
        "head": native_source.get("head", ""),
        "archive_path": (spec.baseline_root / "source-native.zip").as_posix(),
        "file_list_path": (spec.baseline_root / "source-native-file-list.json").as_posix(),
    })
    final_pin = _source_archive(_sources, "curry_final_archive", {
        "archive_sha256": final_archive_meta.get("sha256", ""),
        "file_list_sha256": final_archive_meta.get("file_list_sha256", ""),
        "source_identity": final_source.get("source_identity", ""),
        "file_count": final_source.get("file_count", 0),
        "head": final_source.get("head", ""),
        "archive_path": (spec.baseline_root / "final-build" / final_archive_meta.get("path", "")).as_posix(),
        "file_list_path": (spec.baseline_root / "final-build" / final_archive_meta.get("file_list_path", "")).as_posix(),
    })

    def archive_relative(pin: dict[str, Any], key: str, prefix: Path) -> str:
        pin_path = Path(pin[key])
        try:
            return pin_path.relative_to(prefix).as_posix()
        except ValueError:
            raise ValueError("curry_baseline_source_archive_path_mismatch") from None

    native_archive_relative = archive_relative(
        native_pin, "archive_path", spec.baseline_root,
    )
    native_list_relative = archive_relative(
        native_pin, "file_list_path", spec.baseline_root,
    )
    final_archive_relative = archive_relative(
        final_pin, "archive_path", spec.baseline_root / "final-build",
    )
    final_list_relative = archive_relative(
        final_pin, "file_list_path", spec.baseline_root / "final-build",
    )
    native_list_path = baseline / native_list_relative
    native_list_raw = safe_path(native_list_path).read_bytes()
    if _sha(native_list_raw) != native_pin["file_list_sha256"]:
        raise ValueError("curry_baseline_native_file_list_hash_mismatch")
    if (native_source.get("archive_sha256") != native_pin["archive_sha256"]
            or native_source.get("identity") != native_pin["source_identity"]
            or native_source.get("file_count") != native_pin["file_count"]
            or final_archive_meta.get("sha256") != final_pin["archive_sha256"]
            or final_archive_meta.get("file_list_sha256") != final_pin["file_list_sha256"]
            or final_source.get("source_identity") != final_pin["source_identity"]
            or final_source.get("file_count") != final_pin["file_count"]
            or final_archive_meta.get("path") != final_archive_relative
            or final_archive_meta.get("file_list_path") != final_list_relative):
        raise ValueError("curry_baseline_source_archive_binding_mismatch")
    native_archive = _verify_archive(
        baseline,
        native_archive_relative, native_list_relative,
        native_pin["archive_sha256"], native_pin["file_list_sha256"],
        native_pin["source_identity"], native_pin["file_count"],
    )
    final_archive = _verify_archive(
        baseline / "final-build",
        final_archive_relative, final_list_relative,
        final_pin["archive_sha256"], final_pin["file_list_sha256"],
        final_pin["source_identity"], final_pin["file_count"],
    )
    historical_codec_sha256 = _source_semantic_sha256(
        _sources, "historical_codec", HISTORICAL_SOURCE_TRANSITION["historical_sha256"],
    )
    current_codec_sha256 = _source_semantic_sha256(
        _sources, "current_codec", HISTORICAL_SOURCE_TRANSITION["current_sha256"],
    )
    for archive_path in (
        baseline / native_archive_relative,
        baseline / "final-build" / final_archive_relative,
    ):
        archive_path = safe_path(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            codec_raw = archive.read(HISTORICAL_SOURCE_TRANSITION["path"])
        if _sha(codec_raw) != historical_codec_sha256:
            raise ValueError("curry_historical_codec_archive_mismatch")
    current_codec = safe_path(repo / HISTORICAL_SOURCE_TRANSITION["path"]).read_bytes()
    if _sha(current_codec) != current_codec_sha256:
        raise ValueError("curry_current_codec_hash_mismatch")

    build_record_meta = delivery.get("build_record")
    if not isinstance(build_record_meta, dict):
        raise ValueError("curry_baseline_build_record_missing")
    build_path = baseline / "final-build" / build_record_meta.get("path", "")
    build_raw = safe_path(build_path).read_bytes()
    build = strict_json(build_raw)
    _validate_signed(build, "build_record")
    final_artifacts = delivery.get("final_artifacts")
    if not isinstance(final_artifacts, dict) or set(final_artifacts) != {"cli", "runner", "worker"}:
        raise ValueError("curry_baseline_final_artifacts_invalid")
    if (_sha(build_raw) != build_record_meta.get("sha256")
            or build.get("identity") != build_record_meta.get("identity")
            or build.get("status") != "recorded"
            or build.get("reproducible_build_proven") is not False
            or build.get("source_before") != build.get("source_after")
            or build.get("source_before", {}).get("identity") != final_source.get("source_identity")
            or build.get("artifacts") != {role: value.get("sha256")
                                            for role, value in final_artifacts.items()}):
        raise ValueError("curry_baseline_build_record_binding_invalid")
    for role, artifact in final_artifacts.items():
        path = safe_path(baseline / "final-build" / artifact.get("path", ""))
        raw = path.read_bytes()
        if _sha(raw) != artifact.get("sha256") or len(raw) != artifact.get("bytes"):
            raise ValueError("curry_baseline_final_artifact_hash_mismatch")

    native_build_path = baseline / "build-record.json"
    native_build_raw = safe_path(native_build_path).read_bytes()
    native_build = strict_json(native_build_raw)
    _validate_signed(native_build, "build_record")
    if (native_build.get("identity") != native_source.get("build_record_identity")
            or native_build.get("source_before", {}).get("identity") != native_source.get("identity")
            or native_build.get("source_after") != native_build.get("source_before")):
        raise ValueError("curry_baseline_native_build_record_binding_invalid")
    native_artifacts = native_build.get("artifacts")
    native_artifact_paths = {
        "cli": baseline / "native-artifacts" / "ygo-cli.exe",
        "runner": baseline / "native-artifacts" / "tenki-placement-probe.exe",
        "worker": baseline / "native-artifacts" / "ygo-engine-worker.exe",
    }
    for role, path in native_artifact_paths.items():
        raw = safe_path(path).read_bytes()
        if _sha(raw) != native_artifacts.get(role):
            raise ValueError("curry_baseline_native_artifact_hash_mismatch")

    ledger_relative = "data/runtime/p1-tenki-placement-validation-native-2026-10-23/research/calls.jsonl"
    contract = (
        "tenki-placement-validation",
        ledger_relative,
        native.get("ledger_sha256"),
        VALIDATION_SCOPE.limit,
        VALIDATION_SCOPE.scope,
        manifest.get("context"),
        VALIDATION_SCOPE.limit,
    )
    ledger_audit = _audit_one_ledger(repo, contract)
    if (ledger_audit.get("stats") != {
            "consumed": VALIDATION_SCOPE.limit,
            "reserved": 0,
            "completed": VALIDATION_SCOPE.limit,
            "unknown": 0,
            "abandoned": 0,
            "limit": VALIDATION_SCOPE.limit,
        }):
        raise ValueError("curry_baseline_ledger_statistics_invalid")

    protected: dict[Path, str] = {}

    def protect(path: Path) -> None:
        safe = safe_path(path)
        protected[Path(os.path.abspath(safe))] = _sha(safe.read_bytes())

    # Bind the pre-validation inventory so later stage checks also notice added
    # or removed sidecars, not only changes to files already in the snapshot.
    if _snapshot_curry_evidence(baseline) != evidence_snapshot:
        raise ValueError("curry_baseline_evidence_changed_during_audit")
    protected[Path(os.path.abspath(baseline))] = _curry_evidence_hash(evidence_snapshot)
    for path in (
        baseline / "source-native.zip",
        native_list_path,
        native_build_path,
        *native_artifact_paths.values(),
        baseline / "final-build" / final_archive_meta["path"],
        baseline / "final-build" / final_archive_meta["file_list_path"],
        build_path,
        *(baseline / "final-build" / item["path"] for item in final_artifacts.values()),
    ):
        protect(path)
    for path in (baseline / "acceptance.json", baseline / "final-build" / "delivery.json"):
        protected[Path(os.path.abspath(path))] = _sha(safe_path(path).read_bytes())
    codec_transition = copy.deepcopy(HISTORICAL_SOURCE_TRANSITION)
    codec_transition["historical_sha256"] = historical_codec_sha256
    codec_transition["current_sha256"] = current_codec_sha256
    return {
        "ledger": ledger_audit,
        "native_archive": native_archive,
        "final_archive": final_archive,
        "codec_transition": codec_transition,
        "summary_sha256": _sha(summary_raw),
        "verification_sha256": _sha(verification_raw),
    }, protected


def _load_curry_resume_state(
    *, repo: Path, root: Path, output: Path, paths: dict[str, Path],
    preparation: dict, spec: CurryScopeSpec,
    manifest_path: Path, prepared_path: Path,
) -> tuple[dict, bytes, dict, dict[Path, str]]:
    """Validate the complete immutable resume intent before entering stages."""
    from ygo_data.identity import stable_source

    if not (output.is_dir() and manifest_path.is_file() and prepared_path.is_file()):
        raise ValueError("curry_existing_output_not_recoverable")
    manifest_raw = safe_path(manifest_path).read_bytes()
    manifest = strict_json(manifest_raw)
    validate_curry_report(manifest, spec=spec)
    prepared_raw = safe_path(prepared_path).read_bytes()
    prepared = strict_json(prepared_raw)
    validate_curry_report(prepared, spec=spec)
    if (prepared.get("prepared") is not True or prepared.get("execution_ready") is not True
            or prepared.get("manifest_sha256") != _sha(manifest_raw)):
        raise ValueError("curry_prepared_execution_gate_failed")
    source = manifest.get("source")
    if stable_source(repo) != source:
        raise ValueError("curry_workspace_source_changed")
    frozen_paths = _curry_manifest_files(
        repo, root, paths, preparation,
        _resolve_curry_banlist_path(
            repo, preparation["base_request_entry"].get("banlist_path", ""),
        ),
        spec,
    )
    frozen_files = _verify_manifest_input_state(
        frozen_paths, preparation, manifest.get("input_sha256", {}),
    )
    input_hashes = manifest.get("input_sha256", {})
    if _is_revalidation_scope(spec):
        if (input_hashes.get("baseline_delivery") != spec.delivery_sha256
                or input_hashes.get("baseline_recovery") != spec.baseline_recovery_sha256
                or input_hashes.get("consumption_reservation") != spec.reservation_sha256):
            raise ValueError("curry_saved_revalidation_input_mismatch")
    elif spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        if (input_hashes.get("baseline_acceptance") != spec.baseline_acceptance_sha256
                or input_hashes.get("consumption_reservation") != spec.reservation_sha256):
            raise ValueError("curry_saved_reservation_input_mismatch")
    elif input_hashes.get("baseline_delivery") != spec.delivery_sha256:
        raise ValueError("curry_saved_baseline_delivery_mismatch")
    for path in (
        manifest_path, prepared_path, output / "stage-1-request.json",
        output / "stage-1-input.json", output / "stage-1-input-seal.json",
    ):
        if not path.is_file():
            raise ValueError("curry_saved_stage1_intent_missing")
        frozen_files[Path(os.path.abspath(path))] = _sha(safe_path(path).read_bytes())
    return manifest, prepared_raw, source, frozen_files


def native_curry_option_validation(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    process_runner: Callable[..., Any] | None = None,
    spec: CurryScopeSpec = CURRY_SCOPE,
) -> dict:
    """Prepare, zero-call verify, or resume the fixed seven-stage Curry scope.

    The caller controls no scope, budget, expected card, or action encoding.
    Fresh preparation is gated by the signed historical baseline and isolated
    build before a window or asset scan is created.
    """
    from ygo_data.identity import stable_source
    from ygo_eval.native_tenki_placement import (
        _archive_current_source, _candidate_configs, _capture_identity,
    )
    from ygo_eval.native_tenki_placement_confirmation import (
        _verify_build_and_identity, _verify_workspace_identity,
    )
    from ygo_eval.native_tenki_placement_validation import (
        VALIDATION_SCOPE, _read_runner_stats, _run_process,
    )

    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    root, output, paths = _fixed_curry_paths(args, repo, spec)
    if not any(line.strip() in ("/data/runtime/", "data/runtime/", "/data/runtime", "data/runtime")
               for line in safe_path(repo / ".gitignore").read_text(encoding="utf-8").splitlines()):
        raise ValueError("curry_output_must_be_ignored")

    output = Path(os.path.abspath(output))
    manifest_path = output / "manifest.json"
    prepared_path = output / "prepared.json"

    # The new scope's verify-only path is deliberately read-only and does not
    # consult the live workspace, candidate configs, or current asset scans.
    if _uses_reservation_accounting(spec) and args.verify_only:
        if not output.is_dir() or not manifest_path.is_file() or not prepared_path.is_file():
            raise ValueError("curry_verify_requires_saved_prepared_output")
        if _is_revalidation_scope(spec):
            baseline, baseline_protected = _verify_option_revalidation_baseline(
                repo, Path(args.baseline_dir),
            )
        else:
            baseline, baseline_protected = _verify_option_verification_baseline(
                repo, Path(args.baseline_dir),
            )
        manifest_raw = safe_path(manifest_path).read_bytes()
        manifest = strict_json(manifest_raw)
        validate_curry_report(manifest, spec=spec)
        prepared_raw = safe_path(prepared_path).read_bytes()
        prepared = strict_json(prepared_raw)
        validate_curry_report(prepared, spec=spec)
        if (prepared.get("prepared") is not True
                or prepared.get("execution_ready") is not True
                or prepared.get("manifest_sha256") != _sha(manifest_raw)
                or prepared.get("stage1_request_sha256") != manifest.get("stage1_request_sha256")):
            raise ValueError("curry_saved_prepared_binding_invalid")
        protected = _verify_saved_option_verification_inputs(
            args, repo, root, paths, manifest, baseline_protected, spec,
        )
        _verify_saved_confirmation_build_and_archive(root, manifest, paths)
        if _is_revalidation_scope(spec):
            _assert_option_revalidation_protected(protected, repo)
        else:
            _assert_option_verification_protected(protected, repo)
        scope_evidence_before = _snapshot_curry_evidence(root)

        checks_root = repo / "target" / (
            "curry-option-revalidation-checks"
            if _is_revalidation_scope(spec) else "curry-option-verification-checks"
        )
        if checks_root.is_symlink():
            raise ValueError("curry_verification_checks_root_symlink_rejected")
        checks_root.mkdir(parents=True, exist_ok=True)
        checks_dir = checks_root / uuid.uuid4().hex
        checks_dir.mkdir(exist_ok=False)

        def verify_recorded_verification(input_path: Path) -> dict:
            process, completed, diagnostic_sha = _run_process(
                paths["runner"], input_path, repo, checks_dir, "verify_recorded",
                process_runner=process_runner, spec=spec,
            )
            result = None
            if process.get("status") == "completed" and completed is not None:
                try:
                    result = strict_json(completed.stdout)
                except (ValueError, UnicodeDecodeError, TypeError):
                    result = None
            if (not isinstance(result, dict) or result.get("verified_recorded") is not True
                    or not _zero_call_count_valid(result, spec)
                    or getattr(completed, "returncode", None) not in (0, 1)):
                raise ValueError("curry_recorded_receipt_verification_failed")
            return {**result, "diagnostic_sha256": diagnostic_sha}

        def read_verification_stats(input_path: Path) -> dict | None:
            stats, _process, _diagnostic = _read_runner_stats(
                paths["runner"], input_path, repo, checks_dir,
                process_runner=process_runner, spec=spec,
            )
            return stats

        report = verify_curry_only(
            root=root, output=output, runner=paths["runner"], repo=repo,
            manifest=manifest, prepared_hash=_sha(prepared_raw),
            verify_recorded=verify_recorded_verification,
            read_stats=read_verification_stats,
            verification_output=checks_dir, spec=spec,
        )
        if _is_revalidation_scope(spec):
            _assert_option_revalidation_protected(protected, repo)
        else:
            _assert_option_verification_protected(protected, repo)
        if _snapshot_curry_evidence(root) != scope_evidence_before:
            raise ValueError("curry_option_verification_scope_evidence_changed")
        return report

    if spec.scope == CONFIRMATION_SCOPE.scope and args.verify_only:
        if not output.is_dir() or not manifest_path.is_file() or not prepared_path.is_file():
            raise ValueError("curry_verify_requires_saved_prepared_output")
        manifest_raw = safe_path(manifest_path).read_bytes()
        manifest = strict_json(manifest_raw)
        validate_curry_report(manifest, spec=spec)
        prepared_raw = safe_path(prepared_path).read_bytes()
        prepared = strict_json(prepared_raw)
        validate_curry_report(prepared, spec=spec)
        if (prepared.get("prepared") is not True
                or prepared.get("execution_ready") is not True):
            raise ValueError("curry_confirmation_prepared_execution_gate_failed")
        if (prepared.get("manifest_sha256") != _sha(manifest_raw)
                or prepared.get("stage1_request_sha256") != manifest.get("stage1_request_sha256")):
            raise ValueError("curry_saved_prepared_binding_invalid")
        _verify_saved_confirmation_build_and_archive(root, manifest, paths)

        def verify_recorded_saved(input_path: Path) -> dict:
            process, completed, diagnostic_sha = _run_process(
                paths["runner"], input_path, repo, root, "verify_recorded",
                process_runner=process_runner, spec=spec,
            )
            result = None
            if process.get("status") == "completed" and completed is not None:
                try:
                    result = strict_json(completed.stdout)
                except (ValueError, UnicodeDecodeError, TypeError):
                    result = None
            if (not isinstance(result, dict) or result.get("verified_recorded") is not True
                    or result.get("native_calls") != 0
                    or getattr(completed, "returncode", None) not in (0, 1)):
                raise ValueError("curry_recorded_receipt_verification_failed")
            return {**result, "diagnostic_sha256": diagnostic_sha}

        def read_saved_stats(input_path: Path) -> dict | None:
            stats, _process, _diagnostic = _read_runner_stats(
                paths["runner"], input_path, repo, root,
                process_runner=process_runner, spec=spec,
            )
            return stats

        return verify_curry_only(
            root=root, output=output, runner=paths["runner"], repo=repo,
            manifest=manifest, prepared_hash=_sha(prepared_raw),
            verify_recorded=verify_recorded_saved, read_stats=read_saved_stats,
            spec=spec,
        )

    # For a normal resume, all provenance and input gates belong to the
    # pre-stage refusal path. Persist a stable diagnostic before returning and
    # before the stage driver can inspect a writable journal or start a runner.
    if output.exists() and not args.verify_only:
        if args.prepare_only:
            raise ValueError("curry_prepare_output_already_exists")
        try:
            if not root.is_dir() or not (root / "native-artifacts").is_dir():
                raise ValueError("curry_isolated_build_required")
            if spec.scope == CONFIRMATION_SCOPE.scope:
                baseline_audit, protected = _verify_confirmation_baseline(
                    repo, Path(args.baseline_dir),
                )
            elif spec.scope == OPTION_VERIFICATION_SCOPE.scope:
                baseline_audit, protected = _verify_option_verification_baseline(
                    repo, Path(args.baseline_dir),
                )
            elif _is_revalidation_scope(spec):
                baseline_audit, protected = _verify_option_revalidation_baseline(
                    repo, Path(args.baseline_dir),
                )
            else:
                baseline_audit, protected = _verify_curry_baseline(
                    repo, Path(args.baseline_dir), spec,
                )
            preparation = verify_curry_preparation(
                repo=repo,
                preparation=Path(args.preparation),
                cases_path=Path(args.cases),
                operations_source=Path(args.core_source),
            )
            manifest, prepared_raw, source, frozen_files = _load_curry_resume_state(
                repo=repo, root=root, output=output, paths=paths,
                preparation=preparation, spec=spec,
                manifest_path=manifest_path, prepared_path=prepared_path,
            )
        except Exception as error:
            _save_pre_stage_refusal_diagnostic(repo, error, spec)
            raise
        return run_curry_stages(
            root=root, output=output, runner=paths["runner"], repo=repo,
            manifest=manifest, prepared_hash=_sha(prepared_raw),
            stage1_request=manifest["request"],
            expected_identity=manifest["assets"]["ordinary"],
            source=source, protected=protected, frozen_files=frozen_files,
            process_runner=process_runner, spec=spec,
        )

    if spec.scope == CONFIRMATION_SCOPE.scope:
        baseline_audit, protected = _verify_confirmation_baseline(
            repo, Path(args.baseline_dir),
        )
    elif spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        baseline_audit, protected = _verify_option_verification_baseline(
            repo, Path(args.baseline_dir),
        )
    elif _is_revalidation_scope(spec):
        baseline_audit, protected = _verify_option_revalidation_baseline(
            repo, Path(args.baseline_dir),
        )
    else:
        baseline_audit, protected = _verify_curry_baseline(
            repo, Path(args.baseline_dir), spec,
        )
    preparation = verify_curry_preparation(
        repo=repo,
        preparation=Path(args.preparation),
        cases_path=Path(args.cases),
        operations_source=Path(args.core_source),
    )

    if args.verify_only:
        if not output.is_dir() or not manifest_path.is_file() or not prepared_path.is_file():
            raise ValueError("curry_verify_requires_saved_prepared_output")
        manifest_raw = safe_path(manifest_path).read_bytes()
        manifest = strict_json(manifest_raw)
        validate_curry_report(manifest, spec=spec)
        prepared_raw = safe_path(prepared_path).read_bytes()
        prepared = strict_json(prepared_raw)
        validate_curry_report(prepared, spec=spec)
        if (prepared.get("prepared") is not True
                or prepared.get("manifest_sha256") != _sha(manifest_raw)
                or prepared.get("stage1_request_sha256") != manifest.get("stage1_request_sha256")):
            raise ValueError("curry_saved_prepared_binding_invalid")
        def verify_recorded(input_path: Path) -> dict:
            process, completed, diagnostic_sha = _run_process(
                paths["runner"], input_path, repo, root, "verify_recorded",
                process_runner=process_runner, spec=spec,
            )
            result = None
            if process.get("status") == "completed" and completed is not None:
                try:
                    result = strict_json(completed.stdout)
                except (ValueError, UnicodeDecodeError, TypeError):
                    result = None
            if (not isinstance(result, dict) or result.get("verified_recorded") is not True
                    or result.get("native_calls") != 0
                    or getattr(completed, "returncode", None) not in (0, 1)):
                raise ValueError("curry_recorded_receipt_verification_failed")
            return {**result, "diagnostic_sha256": diagnostic_sha}
        def read_stats(input_path: Path) -> dict | None:
            stats, _process, _diagnostic = _read_runner_stats(
                paths["runner"], input_path, repo, root,
                process_runner=process_runner, spec=spec,
            )
            return stats
        report = verify_curry_only(
            root=root, output=output, runner=paths["runner"], repo=repo,
            manifest=manifest, prepared_hash=_sha(prepared_raw),
            verify_recorded=verify_recorded, read_stats=read_stats, spec=spec,
        )
        return report

    if not args.prepare_only:
        raise ValueError("curry_prepare_required_before_execution")
    if not root.is_dir() or not (root / "native-artifacts").is_dir():
        raise ValueError("curry_isolated_build_required")
    if any(not path.is_file() for path in (
            paths["runner"], paths["worker"], paths["cli"], paths["build_record"])):
        raise ValueError("curry_isolated_build_artifact_missing")

    source = stable_source(repo)
    build, artifacts, cli, build_hash = _verify_build_and_identity(
        args, repo, root, paths, source,
    )
    source_archive = _archive_current_source(repo, root, source)
    configs = _candidate_configs(
        repo, root, paths["worker"],
        repo / (spec.candidate_config_root or spec.baseline_root),
    )
    if paths["identity"].exists() and not paths["window_start"].exists():
        raise ValueError("curry_identity_exists_without_window")
    # This immutable timestamp precedes the first candidate identity scan.
    window = _curry_window_start(paths["window_start"], spec)
    started_at = window["started_at"]
    if started_at + spec.wall_seconds <= int(time.time()):
        raise ValueError("curry_window_expired")
    request = derive_curry_stage1_request(
        preparation["base_request"], preparation["rabbit_case"],
        preparation["candidate_case"], paths["worker"],
    )
    identity = _capture_identity(repo, cli, configs, paths["identity"])
    ordinary, tournament = _verify_workspace_identity(
        identity, source, artifacts, paths["worker"], request,
    )
    if stable_source(repo) != source:
        raise ValueError("curry_workspace_changed_during_identity_capture")
    if _is_revalidation_scope(spec):
        _assert_option_revalidation_protected(protected, repo)

    banlist_path = _resolve_curry_banlist_path(
        repo, preparation["base_request_entry"].get("banlist_path", ""),
    )
    files = _curry_manifest_files(repo, root, paths, preparation, banlist_path, spec)
    input_hashes, input_raw_snapshot = _capture_manifest_input_state(files, preparation)
    if any(input_hashes.get(role) != digest
           for role, digest in _pinned_inputs(spec).items() if role in input_hashes):
        raise ValueError("curry_base_request_hash_binding_invalid")
    expected_input_hashes = {
        **preparation["input_sha256"],
        "runner": input_hashes["runner"], "worker": input_hashes["worker"],
        "cli": input_hashes["cli"], "build_record": build_hash,
        "identity": input_hashes["identity"],
        "window_start": input_hashes["window_start"],
        "source_archive": source_archive["sha256"],
        "source_file_list": source_archive["file_list_sha256"],
        "ordinary_config": input_hashes["ordinary_config"],
        "tournament_config": input_hashes["tournament_config"],
        "banlist": input_hashes["banlist"],
        "core_source": input_hashes["core_source"],
        "adapter_codec": input_hashes["adapter_codec"],
    }
    if spec.scope == CONFIRMATION_SCOPE.scope:
        expected_input_hashes["baseline_delivery"] = spec.delivery_sha256
        expected_input_hashes["baseline_audit"] = spec.baseline_audit_sha256
    elif spec.scope == OPTION_VERIFICATION_SCOPE.scope:
        expected_input_hashes["baseline_acceptance"] = spec.baseline_acceptance_sha256
        expected_input_hashes["consumption_reservation"] = spec.reservation_sha256
    elif _is_revalidation_scope(spec):
        expected_input_hashes["baseline_delivery"] = spec.delivery_sha256
        expected_input_hashes["baseline_recovery"] = spec.baseline_recovery_sha256
        expected_input_hashes["consumption_reservation"] = spec.reservation_sha256
    else:
        expected_input_hashes["baseline_delivery"] = spec.delivery_sha256
    if set(expected_input_hashes) != set(_manifest_roles(spec)):
        raise ValueError("curry_manifest_input_roles_mismatch")
    if any(expected_input_hashes.get(role) != digest
           for role, digest in _pinned_inputs(spec).items()):
        raise ValueError("curry_frozen_preparation_inputs_changed")
    input_sha256 = expected_input_hashes
    unsigned = {
        "schema_version": 1,
        "kind": _report_kind(spec, "manifest"),
        "scope": spec.scope,
        "batch_kind": spec.batch_kind,
        "limit": spec.limit,
        "planned_calls": spec.limit,
        "wall_seconds": spec.wall_seconds,
        "started_at": started_at,
        **(_verification_manifest_fields(spec)
           if _uses_reservation_accounting(spec) else {
            "old_consumed": spec.old_consumed,
        }),
        **_source_manifest_fields(spec),
        "source": source,
        "historical_source_transition": copy.deepcopy(HISTORICAL_SOURCE_TRANSITION),
        "build": {"identity": build.get("identity"),
                  "artifacts": artifacts, "record_sha256": build_hash},
        "assets": {"ordinary": ordinary, "tournament": tournament,
                   "identity_sha256": identity.get("identity"),
                   "execution_role": "ordinary"},
        "input_sha256": input_sha256,
        "source_archive": source_archive,
        "request": request,
        "stage1_request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
        "request_derivation": "frozen-prompt-14-curry-v1-worker-path-replaced",
        **FLAGS,
    }
    manifest = {**unsigned, "context": hashlib.sha256(canonical(unsigned)).hexdigest()}
    validate_curry_report(manifest, spec=spec)
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = output / "manifest.json"
    immutable_write(manifest_path, manifest)
    stage1_input, _request_path = _save_curry_stage_files(
        output, manifest["context"], 1, request, ordinary, started_at, spec,
    )
    if (output / "calls.jsonl").exists():
        raise ValueError("curry_prepare_created_charge_ledger")
    timeout = min(900.0, started_at + spec.wall_seconds - time.time())
    if timeout <= 30:
        raise ValueError("curry_window_insufficient_for_preflight")
    process_record, completed, process_sha = _run_process(
        paths["runner"], stage1_input, repo, root, "preflight_only",
        timeout=timeout, process_runner=process_runner, spec=spec,
    )
    preparation_after = verify_curry_preparation(
        repo=repo, preparation=Path(args.preparation),
        cases_path=Path(args.cases), operations_source=Path(args.core_source),
    )
    after_hashes, after_raw_snapshot = _capture_manifest_input_state(files, preparation_after)
    if (preparation_after["input_sha256"] != preparation["input_sha256"]
            or preparation_after["frozen_cases_sha256"] != preparation["frozen_cases_sha256"]
            or after_hashes != input_sha256
            or after_raw_snapshot != input_raw_snapshot):
        raise ValueError("curry_frozen_input_changed_during_prepare")
    if _is_revalidation_scope(spec):
        _assert_option_revalidation_protected(protected, repo)
    output_value = None
    if process_record.get("status") == "completed" and completed is not None:
        try:
            output_value = strict_json(completed.stdout)
        except (ValueError, UnicodeDecodeError, TypeError):
            output_value = None
    preflight_ok = bool(
        completed is not None and completed.returncode == 0
        and isinstance(output_value, dict)
        and output_value.get("preflight_passed") is True
        and _zero_call_count_valid(output_value, spec)
        and output_value.get("context") == manifest["context"]
        and output_value.get("identity_sha256") == ordinary.get("identity")
    )
    if (output / "calls.jsonl").exists():
        raise ValueError("curry_preflight_created_charge_ledger")
    prepared = {
        "schema_version": 1,
        "kind": _report_kind(spec, "prepared"),
        "scope": spec.scope,
        "context": manifest["context"],
        "prepared": preflight_ok,
        "execution_ready": preflight_ok,
        "native_calls": 0,
        "planned_calls": spec.limit,
        "stage1_request_sha256": manifest["stage1_request_sha256"],
        "preflight_diagnostic_sha256": process_sha,
        "manifest_sha256": _sha(safe_path(manifest_path).read_bytes()),
        "stage1_input_sha256": _sha(safe_path(stage1_input).read_bytes()),
        "diagnostics": [] if preflight_ok else ["curry_preflight_output_mismatch"],
        **FLAGS,
    }
    validate_curry_report(prepared, spec=spec)
    immutable_write(prepared_path, prepared)
    if not preflight_ok:
        summary = summarize_curry_validation(
            manifest["context"], [], None, "curry_preflight_output_mismatch", spec,
        )
        immutable_write(output / "summary.json", summary)
    return prepared


def native_curry_option_confirmation(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    process_runner: Callable[..., Any] | None = None,
) -> dict:
    """Run the independent fixed confirmation scope, sharing only workflow code."""
    return native_curry_option_validation(
        args, repo, process_runner=process_runner, spec=CONFIRMATION_SCOPE,
    )


def native_curry_option_verification(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    process_runner: Callable[..., Any] | None = None,
) -> dict:
    """Run the new fixed scope bound to the certified V3 risk reservation."""
    return native_curry_option_validation(
        args, repo, process_runner=process_runner, spec=OPTION_VERIFICATION_SCOPE,
    )


def native_curry_option_revalidation(
    args: argparse.Namespace,
    repo: Path | None = None,
    *,
    process_runner: Callable[..., Any] | None = None,
) -> dict:
    """Run the fixed Curry scope bound to the V3 recovery evidence."""
    return native_curry_option_validation(
        args, repo, process_runner=process_runner, spec=OPTION_REVALIDATION_SCOPE,
    )


def _save_curry_stage_files(output: Path, context: str, stage: int,
                            request: dict, expected_identity: dict,
                            started_at: int, spec: CurryScopeSpec) -> tuple[Path, Path]:
    from ygo_eval.native_tenki_placement_validation import _stage_invocation

    invocation = _stage_invocation(context, output, stage, request,
                                   expected_identity, started_at, spec)
    request_path = output / f"stage-{stage}-request.json"
    input_path = output / f"stage-{stage}-input.json"
    input_bytes = canonical(invocation)
    immutable_write(request_path, request)
    immutable_write(input_path, invocation)
    immutable_write(output / f"stage-{stage}-input-seal.json", {
        "schema_version": 1, "kind": spec.input_seal_kind,
        "context": context, "stage": stage, "input_sha256": _sha(input_bytes),
    })
    return input_path, request_path
