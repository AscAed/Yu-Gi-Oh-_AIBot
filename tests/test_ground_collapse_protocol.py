from itertools import combinations

import pytest

from ygo_eval.ground_collapse_protocol import (
    audit_ground_collapse_fixed_selection,
    audit_opcode18_fixed_zone_selection,
    audit_ground_collapse_selection,
    canonical_zone_pairs,
    parse_field_disabled,
    parse_hint_zone,
    parse_opcode24,
    zone_response_bytes,
)


def _zone(player, sequence):
    return {"player": player, "location": 4, "sequence": sequence}


def _synthetic_prompt(raw):
    parsed = parse_opcode24(raw)
    zones = [
        {"player": player, "location": location, "sequence": sequence}
        for player in range(2)
        for location in (4, 8)
        for sequence in range(7 if location == 4 else 8)
        if not parsed["disabled_mask"] & (
            1 << (sequence + (8 if location == 8 else 0) + player * 16)
        )
    ]
    actions = []
    for first, second in combinations(zones, 2):
        selected = [first, second]
        actions.append({
            "choice": {"kind": "place", "zones": selected},
            "card_ids": [],
            "bytes": zone_response_bytes(selected),
        })
    return {"opcode": 24, "player": parsed["player"], "actions": actions}


def test_field_disabled_uses_exact_five_byte_little_endian_frame():
    assert parse_field_disabled(bytes([56, 0, 0, 0, 0])) == 0
    assert parse_field_disabled(bytes([56, 0xFF, 0xFF, 0xFF, 0xFF])) == 0xFFFFFFFF
    for raw in (bytes([56]), bytes([56, 0, 0, 0]), bytes([56, 0, 0, 0, 0, 0]), bytes([55, 0, 0, 0, 0])):
        with pytest.raises(ValueError):
            parse_field_disabled(raw)


def test_opcode24_and_hint_zone_preserve_raw_fields():
    prompt = parse_opcode24(bytes([24, 0, 2, 224, 255, 224, 255]))
    assert prompt == {"player": 0, "count": 2, "disabled_mask": 0xFFE0FFE0}
    assert parse_hint_zone(bytes([2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0])) == {
        "player": 0, "value": 0x30000,
    }
    with pytest.raises(ValueError):
        parse_opcode24(bytes([24, 2, 2, 0, 0, 0, 0]))
    with pytest.raises(ValueError):
        parse_opcode24(bytes([24, 0, 2, 0, 0, 0]))
    with pytest.raises(ValueError):
        parse_hint_zone(bytes([2, 10, 0, 0, 0, 3, 0, 0, 0, 0, 0]))
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(
            bytes([24, 0, 2, 224, 255, 224, 255]),
            _synthetic_prompt(bytes([24, 0, 2, 224, 255, 224, 255])),
            [_zone(1, 0), _zone(1, 1)],
            [1, 4, 0, 1, 4, 1],
            bytes([2, 11, 1, 0, 0, 3, 0, 0, 0, 0, 0]),
        )
    with pytest.raises(ValueError):
        parse_hint_zone(bytes([2, 11, 0, 0, 0, 3, 0, 0, 0, 0]))
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(
            bytes([24, 0, 2, 224, 255, 224, 255]),
            {"opcode": True, "player": 0, "actions": []},
            [_zone(1, 0), _zone(1, 1)],
            [1, 4, 0, 1, 4, 1],
        )


def test_opcode24_parser_preserves_zero_count_as_raw_u8():
    # The byte parser models the frame, while this case-specific route rejects
    # it later because the frozen action requires two placements.
    assert parse_opcode24(bytes([24, 0, 0, 0, 0, 0, 0])) == {
        "player": 0,
        "count": 0,
        "disabled_mask": 0,
    }


def test_empty_field_has_45_canonical_pairs_and_fixed_public_choice():
    raw = bytes([24, 0, 2, 224, 255, 224, 255])
    pairs = canonical_zone_pairs(parse_opcode24(raw)["disabled_mask"])
    assert len(pairs) == 45
    selected = [_zone(1, 0), _zone(1, 1)]
    response = [1, 4, 0, 1, 4, 1]
    audit = audit_ground_collapse_selection(
        raw,
        _synthetic_prompt(raw),
        selected,
        response,
        bytes([2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0]),
        bytes([56, 0, 0, 3, 0]),
    )
    assert audit["selected_mask"] == 0x30000
    assert audit["canonical_menu_pairs"] == 45
    assert audit["static_ordered_encodings"] == 90
    assert audit["available_zones"] == 10
    assert audit["reverse_encoding_is_distinct"] is True
    assert audit["reverse_acceptance_by_engine_verified"] is False
    assert audit["native_order_acceptance_verified"] is False
    reversed_response = zone_response_bytes(list(reversed(selected)))
    assert reversed_response == [1, 4, 1, 1, 4, 0]
    assert reversed_response != response

    reordered_prompt = _synthetic_prompt(raw)
    reordered_prompt["actions"] = list(reversed(reordered_prompt["actions"]))
    reordered_audit = audit_ground_collapse_selection(
        raw,
        reordered_prompt,
        selected,
        response,
        bytes([2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0]),
        bytes([56, 0, 0, 3, 0]),
    )
    assert reordered_audit["selected_mask"] == audit["selected_mask"]
    assert reordered_audit["response_bytes"] == response


def test_fixed_ground_collapse_rule_binds_ordered_opposing_monster_zones():
    raw = bytes([24, 0, 2, 224, 255, 224, 255])
    selected = [
        {"player": 1, "location": 4, "sequence": 0},
        {"player": 1, "location": 4, "sequence": 1},
    ]
    response = [1, 4, 0, 1, 4, 1]
    result = audit_ground_collapse_fixed_selection(
        raw,
        _synthetic_prompt(raw),
        selected,
        response,
        bytes([2, 11, 0, 0, 0, 3, 0, 0, 0, 0, 0]),
        bytes([56, 0, 0, 3, 0]),
    )
    assert result["selected_mask"] == 0x00030000
    assert result["fixed_public_choice_rule"]["response_bytes"] == response
    assert result["native_order_acceptance_verified"] is False

    with pytest.raises(ValueError, match="fixed_ground_collapse_zone_order_mismatch"):
        audit_ground_collapse_fixed_selection(
            raw, _synthetic_prompt(raw), list(reversed(selected)),
            [1, 4, 1, 1, 4, 0],
        )


def test_opcode18_fixed_choice_is_publicly_bound_but_not_native_verified():
    raw = bytes([18, 0, 1, 0xFF, 0xE0, 0xFF, 0xFF])
    zones = [
        {"player": player, "location": location, "sequence": sequence}
        for player in range(2)
        for location in (4, 8)
        for sequence in range(7 if location == 4 else 8)
        if not int.from_bytes(raw[3:7], "little") & (
            1 << (sequence + (8 if location == 8 else 0) + player * 16)
        )
    ]
    actions = [
        {
            "choice": {"kind": "place", "zones": [zone]},
            "card_ids": [],
            "bytes": [zone["player"], zone["location"], zone["sequence"]],
        }
        for zone in zones
    ]
    prompt = {"opcode": 18, "player": 0, "actions": actions}
    target = {"player": 0, "location": 8, "sequence": 0}
    result = audit_opcode18_fixed_zone_selection(raw, prompt, target, [0, 8, 0])
    assert result["matching_menu_actions"] == 1
    assert result["native_reachability_verified"] is False
    assert result["response_acceptance_verified"] is False

    # The fixed selection is resolved by its coordinate, not menu position.
    reordered = dict(prompt, actions=list(reversed(actions)))
    assert audit_opcode18_fixed_zone_selection(
        raw, reordered, target, [0, 8, 0],
    )["matching_menu_actions"] == 1

    duplicate = dict(prompt, actions=actions + [actions[0]])
    with pytest.raises(ValueError, match="opcode18_action_menu_binding_mismatch"):
        audit_opcode18_fixed_zone_selection(raw, duplicate, target, [0, 8, 0])
    with pytest.raises(ValueError, match="opcode18_response_mismatch"):
        audit_opcode18_fixed_zone_selection(raw, prompt, target, [0, 8, True])
    with pytest.raises(ValueError, match="opcode18_fixed_zone_mismatch"):
        audit_opcode18_fixed_zone_selection(
            raw, prompt, {"player": 0, "location": 8, "sequence": False}, [0, 8, 0],
        )


def test_ground_collapse_selection_rejects_ambiguous_or_mismatched_actions():
    raw = bytes([24, 0, 2, 224, 255, 224, 255])
    prompt = _synthetic_prompt(raw)
    selected = [_zone(1, 0), _zone(1, 1)]
    response = [1, 4, 0, 1, 4, 1]
    broken = dict(prompt, actions=prompt["actions"][:-1])
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(raw, broken, selected, response)
    duplicate = dict(prompt, actions=prompt["actions"] + [prompt["actions"][-1]])
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(raw, duplicate, selected, response)
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(raw, prompt, list(reversed(selected)), response)
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(raw, prompt, selected, response[:-1])
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(raw, prompt, [selected[0], selected[0]], response)
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(raw, prompt, selected, [1, 4, 0, True, 4, 1])
    one_zone_raw = bytes([24, 0, 1, 224, 255, 224, 255])
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(
            one_zone_raw,
            _synthetic_prompt(one_zone_raw),
            [selected[0]],
            [1, 4, 0],
        )


def test_opcode24_menu_includes_every_enabled_monster_and_spell_trap_zone():
    raw = bytes([24, 0, 2, 0, 0, 0, 0])
    full_prompt = _synthetic_prompt(raw)
    assert len(full_prompt["actions"]) == 435
    assert any(
        zone["location"] == 8
        for action in full_prompt["actions"]
        for zone in action["choice"]["zones"]
    )
    incomplete = dict(full_prompt, actions=full_prompt["actions"][:-1])
    with pytest.raises(ValueError):
        audit_ground_collapse_selection(
            raw,
            incomplete,
            [_zone(1, 0), _zone(1, 1)],
            [1, 4, 0, 1, 4, 1],
        )
