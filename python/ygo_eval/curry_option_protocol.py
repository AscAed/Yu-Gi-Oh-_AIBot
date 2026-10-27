"""Independent, pure-data checks for the frozen Mooyan Curry option result.

This module deliberately decodes raw report bytes itself. It does not import
the Rust-facing production decoder or infer expected bytes from its output.
"""

from typing import Any, Iterable


_OPTION_DESCRIPTIONS = (60_895_602_409_472, 60_895_602_409_473)
_OPTION_BYTES = ([0, 0, 0, 0], [1, 0, 0, 0])
_RECOVER_AMOUNT = 200


def _is_integer(value: Any) -> bool:
    return type(value) is int


def _raw_bytes(frame: Any, diagnostic: str) -> bytes:
    if not isinstance(frame, dict):
        raise ValueError(diagnostic)
    raw = frame.get("raw")
    if (not isinstance(raw, list)
            or any(not _is_integer(byte) or byte < 0 or byte > 255 for byte in raw)):
        raise ValueError(diagnostic)
    return bytes(raw)


def _matches_response_bytes(value: Any, expected: list[int]) -> bool:
    return (
        isinstance(value, list)
        and len(value) == len(expected)
        and all(_is_integer(actual) for actual in value)
        and value == expected
    )


def _parse_option14(frame: Any) -> tuple[int, dict, bytes]:
    raw = _raw_bytes(frame, "curry_opcode14_raw_frame_invalid")
    expected_raw = (
        bytes((14, 0, 2))
        + _OPTION_DESCRIPTIONS[0].to_bytes(8, "little")
        + _OPTION_DESCRIPTIONS[1].to_bytes(8, "little")
    )
    if (len(raw) != 19 or raw != expected_raw
            or not _is_integer(frame.get("opcode")) or frame["opcode"] != 14):
        raise ValueError("curry_opcode14_raw_frame_mismatch")

    fields = frame.get("fields")
    prompt = fields.get("prompt") if isinstance(fields, dict) else None
    if (not isinstance(prompt, dict)
            or not _is_integer(prompt.get("id"))
            or not _is_integer(frame.get("sequence"))
            or prompt["id"] != frame["sequence"]
            or prompt.get("opcode") != 14
            or not _is_integer(prompt.get("opcode"))
            or prompt.get("player") != 0
            or not _is_integer(prompt.get("player"))):
        raise ValueError("curry_opcode14_prompt_binding_invalid")

    actions = prompt.get("actions")
    if not isinstance(actions, list) or len(actions) != 2:
        raise ValueError("curry_opcode14_response_set_mismatch")
    for index, action in enumerate(actions):
        choice = action.get("choice") if isinstance(action, dict) else None
        if (not isinstance(choice, dict)
                or choice.get("kind") != "option"
                or not _is_integer(choice.get("index"))
                or choice["index"] != index
                or not _matches_response_bytes(action.get("bytes"), _OPTION_BYTES[index])
                or ("card_ids" in action and action["card_ids"] != [])):
            raise ValueError("curry_opcode14_response_set_mismatch")
    return prompt["id"], prompt, raw


def _parse_recover(frame: dict) -> tuple[int, int, int]:
    raw = _raw_bytes(frame, "curry_recover_raw_frame_invalid")
    if (len(raw) != 6 or raw[0] != 92
            or not _is_integer(frame.get("opcode")) or frame["opcode"] != 92):
        raise ValueError("curry_recover_raw_frame_mismatch")
    player = raw[1]
    amount = int.from_bytes(raw[2:6], "little", signed=False)
    if player not in (0, 1):
        raise ValueError("curry_recover_player_invalid")
    fields = frame.get("fields")
    if (not isinstance(fields, dict)
            or not _is_integer(fields.get("player"))
            or not _is_integer(fields.get("amount"))
            or fields.get("player") != player or fields.get("amount") != amount):
        raise ValueError("curry_recover_fields_disagree_with_raw")
    if amount != _RECOVER_AMOUNT:
        raise ValueError("curry_recover_amount_mismatch")
    sequence = frame.get("sequence")
    if not _is_integer(sequence):
        raise ValueError("curry_recover_sequence_invalid")
    return sequence, player, amount


def _validate_chain_frame(frame: dict, raw: bytes) -> None:
    # MSG_SELECT_CHAIN has a 16-byte header followed by 23 bytes per candidate:
    # player:u8, forced:u8, two u32 values, count:u32, then card/location/effect.
    if len(raw) < 15:
        raise ValueError("curry_chain_frame_truncated")
    if not _is_integer(frame.get("opcode")) or frame["opcode"] != 16:
        raise ValueError("curry_chain_opcode_disagrees_with_raw")
    # The production decoder consumes an intervening protocol byte before the
    # forced flag, then two u32 timing values and a u32 candidate count.
    player, special_count, forced = raw[1], raw[2], raw[3]
    count = int.from_bytes(raw[12:16], "little", signed=False)
    if player not in (0, 1) or special_count != 0 or forced not in (0, 1):
        raise ValueError("curry_chain_header_invalid")
    if len(raw) != 16 + 23 * count:
        raise ValueError("curry_chain_frame_length_mismatch")
    if count != 0 or forced != 0:
        raise ValueError("curry_nonempty_or_forced_chain")

    fields = frame.get("fields")
    prompt = fields.get("prompt") if isinstance(fields, dict) else None
    if prompt is not None:
        actions = prompt.get("actions") if isinstance(prompt, dict) else None
        choice = actions[0].get("choice") if isinstance(actions, list) and len(actions) == 1 and isinstance(actions[0], dict) else None
        response = actions[0].get("bytes") if isinstance(actions, list) and len(actions) == 1 and isinstance(actions[0], dict) else None
        if (not isinstance(prompt, dict)
                or not _is_integer(prompt.get("id"))
                or prompt.get("id") != frame.get("sequence")
                or prompt.get("opcode") != 16
                or not _is_integer(prompt.get("opcode"))
                or prompt.get("player") != player
                or not _is_integer(prompt.get("player"))
                or not isinstance(choice, dict)
                or choice.get("kind") != "chain"
                or choice.get("index", object()) is not None
                or not _matches_response_bytes(response, [255, 255, 255, 255])):
            raise ValueError("curry_empty_chain_response_mismatch")


def validate_curry_option_result(
    option_frame: dict,
    decision: dict,
    events: Iterable[dict],
    checkpoint: dict,
    pending_event: dict | None = None,
) -> dict:
    """Validate the selected Curry option, its sole RECOVER event, and LP result.

    ``option_frame`` and ``events`` use the raw-frame dictionaries emitted in a
    duel report (``sequence``, ``opcode``, ``raw`` and ``fields``). ``decision``
    is the resolved option decision from the request/result pair. The returned
    mapping contains only independently decoded values for this fixed case.
    """
    prompt_id, _prompt, option_raw = _parse_option14(option_frame)
    if not isinstance(decision, dict):
        raise ValueError("curry_option_decision_invalid")
    choice = decision.get("choice")
    if (not _is_integer(decision.get("prompt_id"))
            or decision["prompt_id"] != prompt_id
            or not _is_integer(decision.get("player"))
            or decision["player"] != 0
            or not isinstance(choice, dict)
            or choice.get("kind") != "option"
            or not _is_integer(choice.get("index"))
            or choice["index"] not in (0, 1)):
        raise ValueError("curry_option_decision_invalid")
    selected = choice["index"]

    if not isinstance(events, (list, tuple)):
        raise ValueError("curry_event_frames_invalid")
    option_matches = []
    recover_frames = []
    previous_sequence = None
    for frame in events:
        if not isinstance(frame, dict):
            raise ValueError("curry_event_frame_invalid")
        sequence = frame.get("sequence")
        if (not _is_integer(sequence)
                or (previous_sequence is not None and sequence <= previous_sequence)):
            raise ValueError("curry_event_sequence_order_invalid")
        previous_sequence = sequence
        raw = _raw_bytes(frame, "curry_event_frame_invalid")
        opcode = raw[0] if raw else None
        reported_opcode = frame.get("opcode")
        if reported_opcode is not None and (
            not _is_integer(reported_opcode) or reported_opcode != opcode
        ):
            raise ValueError("curry_event_opcode_disagrees_with_raw")
        if opcode == 14 and frame.get("sequence") == prompt_id:
            if raw != option_raw or frame != option_frame:
                raise ValueError("curry_option_event_binding_mismatch")
            option_matches.append(frame)
        if opcode == 92 or reported_opcode == 92:
            recover_frames.append(frame)
        if opcode == 16 or reported_opcode == 16:
            _validate_chain_frame(frame, raw)

    if len(option_matches) != 1:
        raise ValueError("curry_option_event_not_unique")
    if len(recover_frames) != 1:
        raise ValueError("curry_recover_event_count_mismatch")
    recover_sequence, recover_player, recover_amount = _parse_recover(recover_frames[0])
    if recover_sequence <= prompt_id:
        raise ValueError("curry_recover_precedes_option")
    if pending_event is not None:
        pending_sequence = pending_event.get("sequence") if isinstance(pending_event, dict) else None
        if (not _is_integer(pending_sequence)
                or not events or events[-1] != pending_event
                or recover_sequence >= pending_sequence):
            raise ValueError("curry_recover_after_pending_prompt")
    if recover_player != selected:
        raise ValueError("curry_recover_player_mismatch")

    expected_lp = [8200, 8000] if selected == 0 else [8000, 8200]
    lp = checkpoint.get("lp") if isinstance(checkpoint, dict) else None
    if (not isinstance(lp, list) or len(lp) != 2
            or any(not _is_integer(value) for value in lp)
            or lp != expected_lp):
        raise ValueError("curry_checkpoint_lp_mismatch")

    return {
        "selected_option": selected,
        "response_bytes": list(_OPTION_BYTES[selected]),
        "recover_player": recover_player,
        "recover_amount": recover_amount,
        "checkpoint_lp": expected_lp,
        "option_frame_sha256": _sha256(option_raw),
        "recover_frame_sha256": _sha256(_raw_bytes(recover_frames[0], "curry_recover_raw_frame_invalid")),
    }


def _sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()
