from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_cards(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict) or payload.get('schema_version') != '2' or not isinstance(payload.get('source'), str) or not payload['source'].strip():
        return ['requires catalog schema_version 2 and source']
    if set(payload) != {'schema_version', 'source', 'cards'}:
        return ['catalog root fields must be schema_version, source, cards']
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return ["root must contain a cards array"]
    if not cards:
        return ['cards must not be empty']
    seen: set[int] = set()
    unsigned = ['id', 'alias', 'type_flags', 'level', 'attribute', 'race', 'lscale', 'rscale', 'link_marker']
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append(f"cards[{index}] must be an object")
            continue
        code = card.get("id")
        if type(code) is not int or not 0 < code <= 2**32-1:
            errors.append(f"cards[{index}].id must be a positive integer")
        elif code in seen:
            errors.append(f"cards[{index}].id duplicates {code}")
        else:
            seen.add(code)
        if not isinstance(card.get("name"), str) or not card["name"].strip():
            errors.append(f"cards[{index}].name must be a non-empty string")
        for key in unsigned + ['attack', 'defense']:
            value = card.get(key)
            lower = -2**31 if key in ['attack', 'defense'] else 0
            upper = 2**31-1 if key in ['attack', 'defense'] else 2**64-1 if key == 'race' else 2**32-1
            if type(value) is not int or not lower <= value <= upper:
                errors.append(f'cards[{index}].{key} out of range or missing')
        kind = card.get('kind')
        flags = card.get('type_flags')
        bit = {'monster': 1, 'spell': 2, 'trap': 4}.get(kind)
        if bit is None or type(flags) is not int or flags & 7 != bit:
            errors.append(f'cards[{index}] kind/type_flags mismatch')
        sets = card.get('setcodes')
        if not isinstance(sets, list) or any(type(v) is not int or not 0 < v < 2**16 for v in sets):
            errors.append(f'cards[{index}].setcodes requires u16 array')
        archetypes = card.get('archetypes')
        if not isinstance(archetypes, list) or any(not isinstance(v, str) for v in archetypes):
            errors.append(f'cards[{index}].archetypes requires string array')
        allowed = set(unsigned + ['attack', 'defense', 'name', 'kind', 'setcodes', 'archetypes'])
        if set(card) - allowed:
            errors.append(f'cards[{index}] has unknown fields')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ygo-data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--input", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        errors = validate_cards(payload)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        cards = payload.get("cards", payload) if isinstance(payload, dict) else payload
        print(f"OK: validated {len(cards)} cards")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
