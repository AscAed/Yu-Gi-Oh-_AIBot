"""Independent byte-level oracle for the frozen Ground Collapse prefix.

This module intentionally does not call the production frame or prompt decoder.
Its outputs describe synthetic/static fixtures and never establish native
reachability or response acceptance.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any


def _exact_bytes(raw: bytes | bytearray, width: int, opcode: int) -> bytes:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != width:
        raise ValueError("invalid_frame_width")
    frame = bytes(raw)
    if frame[0] != opcode:
        raise ValueError("unexpected_opcode")
    return frame


def parse_field_disabled(raw: bytes | bytearray) -> int:
    """Parse opcode 56's exact [opcode, u32-le] shape, without player data."""
    frame = _exact_bytes(raw, 5, 56)
    return int.from_bytes(frame[1:5], "little", signed=False)


def parse_opcode24(raw: bytes | bytearray) -> dict[str, int]:
    """Parse a selection prompt with opcode, player, count, and u32 mask."""
    frame = _exact_bytes(raw, 7, 24)
    player, count = frame[1], frame[2]
    if player > 1:
        raise ValueError("invalid_prompt_player")
    return {"player": player, "count": count, "disabled_mask": int.from_bytes(frame[3:7], "little")}


def parse_hint_zone(raw: bytes | bytearray) -> dict[str, int]:
    """Parse only HINT subtype 11 as [2,11,player,u64-le]."""
    frame = _exact_bytes(raw, 11, 2)
    if frame[1] != 11:
        raise ValueError("unexpected_hint_subtype")
    player = frame[2]
    if player > 1:
        raise ValueError("invalid_hint_player")
    return {"player": player, "value": int.from_bytes(frame[3:11], "little")}


def _zone_key(zone: dict[str, Any]) -> tuple[int, int, int]:
    if not isinstance(zone, dict) or set(zone) != {"player", "location", "sequence"}:
        raise ValueError("invalid_zone_shape")
    player, location, sequence = zone["player"], zone["location"], zone["sequence"]
    if type(player) is not int or player not in (0, 1):
        raise ValueError("invalid_zone_player")
    if type(location) is not int or location not in (4, 8):
        raise ValueError("invalid_zone_location")
    maximum = 6 if location == 4 else 7
    if type(sequence) is not int or not 0 <= sequence <= maximum:
        raise ValueError("invalid_zone_sequence")
    return player, location, sequence


def _zone_bit(zone: dict[str, Any]) -> int:
    player, location, sequence = _zone_key(zone)
    return 1 << (sequence + (8 if location == 8 else 0) + player * 16)


def _strict_equal(left: Any, right: Any) -> bool:
    """Compare JSON-shaped values without Python's bool/int equivalence."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_strict_equal(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _available_zones(disabled_mask: int) -> list[dict[str, int]]:
    if type(disabled_mask) is not int or not 0 <= disabled_mask <= 0xFFFFFFFF:
        raise ValueError("invalid_disabled_mask")
    return [
        {"player": player, "location": location, "sequence": sequence}
        for player in range(2)
        for location in (4, 8)
        for sequence in range(7 if location == 4 else 8)
        if not disabled_mask & (
            1 << (sequence + (8 if location == 8 else 0) + player * 16)
        )
    ]


def canonical_zone_pairs(disabled_mask: int) -> list[list[dict[str, int]]]:
    """Return menu's canonical unordered two-zone combinations.

    This is the canonical production-menu order only. The frozen core accepts
    distinct zones in either response order; this helper does not claim the
    parser's emitted menu is exhaustive over core-accepted byte sequences.
    """
    zones = _available_zones(disabled_mask)
    return [[dict(first), dict(second)] for first, second in combinations(zones, 2)]


def zone_response_bytes(zones: list[dict[str, int]]) -> list[int]:
    if not isinstance(zones, list) or not zones:
        raise ValueError("zones_required")
    keys = [_zone_key(zone) for zone in zones]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_zone")
    return [part for player, location, sequence in keys for part in (player, location, sequence)]


def audit_opcode18_fixed_zone_selection(
    raw_prompt: bytes | bytearray,
    prompt: dict[str, Any],
    selected_zone: dict[str, int],
    response: list[int],
) -> dict[str, Any]:
    """Validate the frozen public opcode18 choice at player 0, SZONE 0.

    The actual opcode18 menu and prompt id are not frozen here. This function
    only accepts one unique menu action whose coordinate is (0, 8, 0), and
    binds its response bytes to the three coordinate bytes.
    """
    frame = _exact_bytes(raw_prompt, 7, 18)
    player, count = frame[1], frame[2]
    mask = int.from_bytes(frame[3:7], "little")
    if player != 0:
        raise ValueError("opcode18_player_mismatch")
    if count != 1:
        raise ValueError("opcode18_fixed_route_requires_one_zone")
    if not isinstance(prompt, dict) or type(prompt.get("opcode")) is not int or prompt["opcode"] != 18:
        raise ValueError("opcode18_prompt_binding_missing")
    if type(prompt.get("player")) is not int or prompt["player"] != player:
        raise ValueError("opcode18_prompt_player_mismatch")
    target = {"player": 0, "location": 8, "sequence": 0}
    if not _strict_equal(selected_zone, target):
        raise ValueError("opcode18_fixed_zone_mismatch")
    expected_bytes = [0, 8, 0]
    if not _strict_equal(response, expected_bytes):
        raise ValueError("opcode18_response_mismatch")
    actions = prompt.get("actions")
    if not isinstance(actions, list):
        raise ValueError("opcode18_actions_missing")
    expected_actions = [
        {
            "choice": {"kind": "place", "zones": [zone]},
            "card_ids": [],
            "bytes": zone_response_bytes([zone]),
        }
        for zone in _available_zones(mask)
    ]
    # Menu order is not part of the public coordinate rule. Bind the complete
    # set exactly once while allowing the engine/parser to enumerate it in a
    # different order.
    if (len(actions) != len(expected_actions)
            or any(
                sum(_strict_equal(action, expected) for action in actions) != 1
                for expected in expected_actions
            )):
        raise ValueError("opcode18_action_menu_binding_mismatch")
    expected_choice = {"kind": "place", "zones": [target]}
    matches = [
        action for action in actions
        if isinstance(action, dict)
        and _strict_equal(action.get("choice"), expected_choice)
        and _strict_equal(action.get("bytes"), expected_bytes)
    ]
    if len(matches) != 1:
        raise ValueError("opcode18_fixed_zone_not_unique")
    return {
        "classification": "public_fixed_choice_rule_only",
        "prompt_opcode": 18,
        "prompt_player": 0,
        "selected_zone": dict(target),
        "response_bytes": list(expected_bytes),
        "matching_menu_actions": 1,
        "native_reachability_verified": False,
        "response_acceptance_verified": False,
    }


def _mask_from_hint_value(value: int) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("invalid_hint_value")
    # Core zone bits: player 0 at bit sequence, player 1 at bit sequence+16.
    # HINT_ZONE describes the 32-bit field mask. High bits are not silently lost.
    if value > 0xFFFFFFFF:
        raise ValueError("hint_value_outside_field_mask")
    return value


def audit_ground_collapse_selection(
    raw_prompt: bytes | bytearray,
    prompt: dict[str, Any],
    selected_zones: list[dict[str, int]],
    response: list[int],
    raw_hint_zone: bytes | bytearray | None = None,
    raw_field_disabled: bytes | bytearray | None = None,
) -> dict[str, Any]:
    """Cross-bind opcode24 menu, selected coordinates, response, and messages."""
    parsed = parse_opcode24(raw_prompt)
    if parsed["count"] != 2:
        raise ValueError("frozen_route_requires_two_zones")
    if (not isinstance(prompt, dict) or type(prompt.get("opcode")) is not int
            or prompt["opcode"] != 24 or type(prompt.get("player")) is not int):
        raise ValueError("prompt_binding_missing")
    if prompt["player"] != parsed["player"] or prompt["player"] != 0:
        raise ValueError("prompt_player_mismatch")
    actions = prompt.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("prompt_actions_missing")

    available = _available_zones(parsed["disabled_mask"])
    expected_pairs = canonical_zone_pairs(parsed["disabled_mask"])
    expected_actions = []
    for pair in expected_pairs:
        expected_actions.append({
            "choice": {"kind": "place", "zones": pair},
            "card_ids": [],
            "bytes": zone_response_bytes(pair),
        })
    if len(actions) != len(expected_actions):
        raise ValueError("prompt_action_count_mismatch")
    if any(
        sum(_strict_equal(actual, expected) for actual in actions) != 1
        for expected in expected_actions
    ):
        raise ValueError("prompt_action_binding_mismatch")

    selected_keys = [_zone_key(zone) for zone in selected_zones]
    if len(selected_keys) != parsed["count"] or len(set(selected_keys)) != len(selected_keys):
        raise ValueError("selected_zone_count_or_uniqueness_mismatch")
    if any(zone not in available for zone in selected_zones):
        raise ValueError("selected_zone_unavailable")
    expected_response = zone_response_bytes(selected_zones)
    if not _strict_equal(response, expected_response):
        raise ValueError("response_bytes_mismatch")
    selected_action = {
        "choice": {"kind": "place", "zones": selected_zones},
        "card_ids": [],
        "bytes": expected_response,
    }
    if sum(_strict_equal(action, selected_action) for action in actions) != 1:
        raise ValueError("selected_action_not_unique")

    selected_mask = 0
    for zone in selected_zones:
        selected_mask |= _zone_bit(zone)

    hint = None
    disabled = None
    if raw_hint_zone is not None:
        hint = parse_hint_zone(raw_hint_zone)
        if hint["player"] != parsed["player"]:
            raise ValueError("hint_player_mismatch")
        hinted_mask = _mask_from_hint_value(hint["value"])
        if hinted_mask != selected_mask:
            raise ValueError("hint_selection_mismatch")
    if raw_field_disabled is not None:
        disabled = parse_field_disabled(raw_field_disabled)
        if disabled != selected_mask:
            raise ValueError("field_disabled_selection_mismatch")
    if hint is not None and disabled is not None and hint["value"] != disabled:
        raise ValueError("selection_message_mismatch")

    # A real HINT_ZONE event may be followed by other events. When absent, the
    # fixed synthetic vectors remain unavailable and no native sequence is inferred.
    synthetic_empty_mask = 0xFFE0FFE0
    return {
        "classification": "synthetic_or_static_only",
        "opcode24_player": parsed["player"],
        "opcode24_count": parsed["count"],
        "disabled_mask": parsed["disabled_mask"],
        "available_zones": len(available),
        "canonical_menu_pairs": len(expected_pairs),
        "static_ordered_encodings": len(expected_pairs) * 2,
        "reverse_encoding_is_distinct": True,
        "reverse_acceptance_by_engine_verified": False,
        "selected_zones": [dict(zone) for zone in selected_zones],
        "response_bytes": list(response),
        "selected_mask": selected_mask,
        "hint_zone": hint,
        "field_disabled_mask": disabled,
        "synthetic_empty_field_canonical_pairs": len(canonical_zone_pairs(synthetic_empty_mask)),
        "synthetic_empty_field_ordered_encodings": 90,
        "native_order_acceptance_verified": False,
        "native_reachability_verified": False,
        "response_acceptance_verified": False,
    }


def audit_ground_collapse_fixed_selection(
    raw_prompt: bytes | bytearray,
    prompt: dict[str, Any],
    selected_zones: list[dict[str, int]],
    response: list[int],
    raw_hint_zone: bytes | bytearray | None = None,
    raw_field_disabled: bytes | bytearray | None = None,
) -> dict[str, Any]:
    """Bind the fixed public 1/4/0 then 1/4/1 preparation route.

    This only verifies that a supplied prompt/menu and response encode the
    frozen public choice. It makes no claim about native reachability or core
    acceptance of alternative response orderings.
    """
    expected_zones = [
        {"player": 1, "location": 4, "sequence": 0},
        {"player": 1, "location": 4, "sequence": 1},
    ]
    expected_response = [1, 4, 0, 1, 4, 1]
    if not _strict_equal(selected_zones, expected_zones):
        raise ValueError("fixed_ground_collapse_zone_order_mismatch")
    if not _strict_equal(response, expected_response):
        raise ValueError("fixed_ground_collapse_response_mismatch")
    result = audit_ground_collapse_selection(
        raw_prompt,
        prompt,
        selected_zones,
        response,
        raw_hint_zone,
        raw_field_disabled,
    )
    if result["selected_mask"] != 0x00030000:
        raise ValueError("fixed_ground_collapse_selected_mask_mismatch")
    result["fixed_public_choice_rule"] = {
        "zones": expected_zones,
        "response_bytes": expected_response,
        "classification": "synthetic_or_static_only",
    }
    return result
