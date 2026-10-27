"""Restricted, pure raw-message observation projection; no engine or journal access."""
import hashlib
import json
from fractions import Fraction


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _public_model(public):
    keys = {'rules', 'objective', 'known_deck_composition', 'initial_public_state'}
    if not isinstance(public, dict) or set(public) != keys:
        raise ValueError('unsupported_public_declaration')
    rules = public['rules']
    if not isinstance(rules, dict) or set(rules) != {'region', 'version'} or any(not isinstance(x, str) or not x for x in rules.values()):
        raise ValueError('unsupported_public_rules')
    objective = {'id': 'rabbit-own-face-up-xyz-v1', 'normal_min': 0, 'normal_max': 7,
                 'early_win': 8, 'loss': -2, 'draw': -1, 'boundary': 'first-next-turn-process-return-v1'}
    initial = {'own_player': 0, 'lp': [8000, 8000], 'turn': 1, 'turn_player': 0,
               'own_hand_count': 5, 'opponent_hand_count': 0, 'empty_field': True,
               'opponent_deck_model': 'copy-own-main'}
    if _digest(public['objective']) != _digest(objective) or _digest(public['initial_public_state']) != _digest(initial):
        raise ValueError('unsupported_public_objective_or_initial_state')
    composition = public['known_deck_composition']
    if not isinstance(composition, dict) or set(composition) != {'main', 'extra', 'side'}:
        raise ValueError('unsupported_known_composition')
    for entries in composition.values():
        if not isinstance(entries, dict) or any(not isinstance(code, str) or not code.isascii() or not code.isdecimal() or int(code) <= 0 or str(int(code)) != code or not _integer(count) or count <= 0 for code, count in entries.items()):
            raise ValueError('unsupported_known_composition')
    return json.loads(json.dumps(public))


class _Reader:
    def __init__(self, raw):
        if not isinstance(raw, list) or any(not _integer(x) or not 0 <= x <= 255 for x in raw):
            raise ValueError('invalid_raw_bytes')
        self.raw, self.offset = bytes(raw), 0

    def take(self, size):
        if self.offset + size > len(self.raw):
            raise ValueError('truncated_frame')
        value = self.raw[self.offset:self.offset + size]
        self.offset += size
        return value

    def number(self, size=1):
        return int.from_bytes(self.take(size), 'little')

    def finish(self):
        if self.offset != len(self.raw):
            raise ValueError('trailing_frame_bytes')


def _idle(reader, hand):
    if reader.number() != 0:
        raise ValueError('opponent_idle_outside_profile')
    menu = []
    for command in range(6):
        count = reader.number(4)
        if count > 4096:
            raise ValueError('idle_group_limit')
        for index in range(count):
            code, player, location, position = reader.number(4), reader.number(), reader.number(), reader.number(4)
            if player != 0 or location != 2 or position >= len(hand) or hand[position] != code:
                raise ValueError('idle_card_coordinate_mismatch')
            if command == 5:
                raise ValueError('activation_outside_empty_idle_profile')
            if command not in (0, 3):
                raise ValueError('scene_change_outside_empty_idle_profile')
            menu.append({'choice': {'kind': 'command', 'command': command, 'index': index},
                         'bytes': list(((index << 16) | command).to_bytes(4, 'little')),
                         'cards': [{'code': code, 'player': player, 'location': location, 'sequence': position}]})
    for command in (6, 7, 8):
        flag = reader.number()
        if flag not in (0, 1):
            raise ValueError('invalid_idle_flag')
        if flag:
            if command == 6:
                raise ValueError('battle_outside_first_turn_profile')
            menu.append({'choice': {'kind': 'command', 'command': command, 'index': 0},
                         'bytes': list(command.to_bytes(4, 'little')), 'cards': []})
    return menu


def project_prefix(events: list, public: dict) -> dict:
    """Project only the first two supported idle prefixes, decoding raw bytes independently.

    Metadata is routing only. Unknown or unexpected messages stop projection permanently.
    Callers must authenticate the evidence and the declared public model separately.
    """
    result = {'views': [], 'gaps': []}
    try:
        base = _public_model(public)
    except (ValueError, TypeError) as exc:
        result['gaps'].append({'event_index': None, 'reason': str(exc)})
        return result
    history, hand, phase = [], None, None
    # Exact initialization grammar, then optional own hand shuffle and next idle.
    expected = [40, 33, 41, 2, 41, 41, 11, 33, 11]
    for ordinal, event in enumerate(events):
        if ordinal >= len(expected):
            result['gaps'].append({'event_index': ordinal, 'reason': 'beyond_supported_second_idle'})
            break
        try:
            if not isinstance(event, dict):
                raise ValueError('invalid_event_record')
            fields = event.get('fields', {})
            if not isinstance(fields, dict):
                raise ValueError('invalid_event_fields')
            if 'prompt' in fields:
                recorded_prompt = fields['prompt']
                if not isinstance(recorded_prompt, dict) or not isinstance(recorded_prompt.get('actions'), list) or any(not isinstance(action, dict) for action in recorded_prompt['actions']):
                    raise ValueError('invalid_recorded_prompt')
            reader = _Reader(event.get('raw'))
            opcode = reader.number()
            if event.get('opcode') != opcode:
                raise ValueError('raw_opcode_mismatch')
            if opcode != expected[ordinal]:
                raise ValueError('unexpected_or_unsupported_message')
            if opcode == 40:
                if reader.number() != 0:
                    raise ValueError('first_turn_not_own')
                visible = {'kind': 'new_turn', 'player': 0}
            elif opcode == 33:
                if reader.number() != 0:
                    raise ValueError('hidden_opponent_shuffle_outside_profile')
                count = reader.number(4)
                if count != 5:
                    raise ValueError('hand_size_outside_profile')
                cards = [reader.number(4) for _ in range(count)]
                if any(code == 0 for code in cards):
                    raise ValueError('unknown_own_hand_identity')
                if hand is not None and sorted(hand) != sorted(cards):
                    raise ValueError('shuffle_hand_multiset_changed')
                hand = cards
                visible = {'kind': 'shuffle_hand', 'player': 0, 'cards': cards[:]}
            elif opcode == 41:
                phase = reader.number(2)
                if phase != {2: 1, 4: 2, 5: 4}[ordinal]:
                    raise ValueError('unexpected_initial_phase')
                visible = {'kind': 'new_phase', 'phase': phase}
            elif opcode == 2:
                if (reader.number(), reader.number(), reader.number(8)) != (1, 0, 27):
                    raise ValueError('unverified_initial_hint')
                visible = {'kind': 'initial_hint', 'hint_type': 1, 'player': 0, 'value': 27}
            else:
                menu = _idle(reader, hand)
                shuffle = any(x['choice']['command'] == 8 for x in menu)
                if shuffle != (ordinal == 6):
                    raise ValueError('unexpected_shuffle_availability')
                existing = fields.get('prompt')
                if existing is not None:
                    actual = [(a['choice'], a['bytes']) for a in menu]
                    recorded = [(a.get('choice'), a.get('bytes')) for a in existing.get('actions', [])]
                    if actual != recorded or existing.get('player') != 0 or existing.get('opcode') != 11:
                        raise ValueError('recorded_prompt_mismatch')
                visible = {'kind': 'idle', 'player': 0, 'menu': menu}
            reader.finish()
            history.append(visible)
            if opcode == 11:
                view = dict(json.loads(json.dumps(base)), profile='rabbit-idle-observation-v1', phase=phase,
                            own_hand=[{'code': code, 'position': i} for i, code in enumerate(hand)],
                            visible_history=json.loads(json.dumps(history)), legal_menu=menu)
                result['views'].append({'view': view, 'observation_key': _digest(view),
                                        'routing': {'event_index': ordinal, 'prompt_id': fields.get('prompt', {}).get('id', event.get('sequence'))}})
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            result['gaps'].append({'event_index': ordinal, 'reason': str(exc)})
            break
    if not result['gaps'] and len(events) not in (7, 9):
        result['gaps'].append({'event_index': len(events), 'reason': 'incomplete_supported_prefix'})
    return result


def check_policy_samples(samples: list, observations: dict) -> dict:
    """Check finite data samples, never execute strategy code or claim implementation safety."""
    groups, diagnostics = {}, []
    for index, sample in enumerate(samples):
        try:
            policy = sample['policy_id']
            if not isinstance(policy, str) or not policy:
                raise ValueError('invalid_policy_id')
            observation = observations[sample['observation_id']]
            view = observation['view']
            if observation['observation_key'] != _digest(view):
                raise ValueError('forged_observation_key')
            legal = {tuple(action['bytes']) for action in view['legal_menu']}
            distribution = {}
            for item in sample['distribution']:
                raw = item['bytes']
                if not isinstance(raw, list) or any(not _integer(x) or not 0 <= x <= 255 for x in raw):
                    raise ValueError('invalid_response_bytes')
                response = tuple(raw)
                if response not in legal or response in distribution:
                    raise ValueError('illegal_or_duplicate_response')
                numerator, denominator = item['numerator'], item['denominator']
                if not _integer(numerator) or not _integer(denominator) or numerator < 0 or denominator <= 0:
                    raise ValueError('invalid_probability')
                distribution[response] = Fraction(numerator, denominator)
            if sum(distribution.values(), Fraction()) != 1:
                raise ValueError('probability_mass_not_one')
            # Zero-probability entries do not change the mathematical distribution.
            normalized = tuple(sorted((key, value) for key, value in distribution.items() if value))
            key = (policy, observation['observation_key'])
            if key in groups and groups[key] != normalized:
                raise ValueError('same_policy_observation_distribution_differs')
            groups[key] = normalized
        except (ValueError, KeyError, TypeError) as exc:
            diagnostics.append({'sample_index': index, 'reason': str(exc)})
    return {'valid': not diagnostics, 'groups': [{'policy_id': key[0], 'observation_key': key[1]} for key in sorted(groups)],
            'diagnostics': diagnostics, 'finite_samples_only': True, 'arbitrary_policy_leak_freedom_proven': False}
