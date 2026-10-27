"""Pure, unqualified prompt candidates and explicitly synthetic response vectors."""
from collections import Counter
from copy import deepcopy

from ygo_eval.research import validate_case


_TARGETS = ((13, 57103969, 'tenki'), (14, 58074572, 'curry'), (24, 90502999, 'collapse'))


def _expected_target(opcode, card_id):
    expected = {'opcode': opcode, 'player': 0}
    if opcode == 13:
        expected.update(description=(0 & 0xfffff) | (card_id << 20),
                        responses=[{'choice': {'kind': 'yes_no', 'yes': yes},
                                    'bytes': list(int(yes).to_bytes(4, 'little'))}
                                   for yes in (False, True)])
    elif opcode == 14:
        expected.update(descriptions=[(index & 0xfffff) | (card_id << 20) for index in (0, 1)],
                        responses=[{'choice': {'kind': 'option', 'index': index},
                                    'bytes': list(index.to_bytes(4, 'little'))}
                                   for index in (0, 1)])
    else:
        expected.update(count=2, mask_source='future_raw_prompt')
    return expected


def derive_candidates(base_case: dict) -> list[dict]:
    """Replace one fixed opening card, preserving the research objective verbatim."""
    validate_case(base_case)
    deck = base_case['deck']
    if (base_case['seed'] != 1 or [len(deck[k]) for k in ('main', 'extra', 'side')] != [40, 3, 0]
            or deck['main'].count(85138716) != 1 or base_case['opening_hand'].count(85138716) != 1):
        raise ValueError('fixed seed and 40/3/0 single replacement base required')
    remaining = Counter(deck['main']) - Counter(base_case['opening_hand'])
    if remaining[69247929] != 2:
        raise ValueError('Tenki requires exactly two declared targets remaining in deck')
    result = []
    for opcode, card_id, name in _TARGETS:
        case = deepcopy(base_case)
        case['case_id'] = f'prompt-{opcode}-{name}-v1'
        for cards in (case['deck']['main'], case['opening_hand']):
            cards[cards.index(85138716)] = card_id
        case['information']['opponent_resources'] = {'main': deepcopy(case['deck']['main']), 'hand': []}
        validate_case(case)
        result.append({'case': case, 'target': {'opcode': opcode, 'card_id': card_id, 'name': name},
                       'request_derivation': {'replace_card': {'from': 85138716, 'to': card_id}, 'fixed_changes': {'seed': 1}},
                       'selector': {'player': 0, 'opcode': 11, 'command': 5, 'card_id': card_id, 'unique': True},
                       'expected_target': _expected_target(opcode, card_id), 'execution_ready': False,
                       'native_reachability_verified': False, 'response_acceptance_verified': False,
                       'formal_release_status': 'unknown'})
    return result


def select_unique_activation(prompt: dict, card_id: int) -> dict:
    """Copy one exact command-5 action; ambiguity and invalid encodings fail closed."""
    if (type(card_id) is not int or not 0 < card_id <= 0xffffffff or not isinstance(prompt, dict)
            or type(prompt.get('player')) is not int or prompt['player'] != 0
            or type(prompt.get('opcode')) is not int or prompt['opcode'] != 11
            or not isinstance(prompt.get('actions'), list)):
        raise ValueError('expected player-0 opcode-11 activation prompt')
    matches = []
    for action in prompt['actions']:
        if not isinstance(action, dict) or not isinstance(action.get('choice'), dict):
            raise ValueError('malformed action')
        choice = action['choice']
        if choice.get('kind') != 'command' or choice.get('command') != 5 or action.get('card_ids') != [card_id]:
            continue
        index = choice.get('index')
        raw = action.get('bytes')
        cards = action['card_ids']
        if (set(choice) != {'kind', 'command', 'index'}
                or not isinstance(cards, list) or len(cards) != 1 or type(cards[0]) is not int
                or not 0 < cards[0] <= 0xffffffff
                or type(choice.get('command')) is not int or type(index) is not int or not 0 <= index <= 65535
                or not isinstance(raw, list) or any(type(b) is not int or not 0 <= b <= 255 for b in raw)
                or raw != list(((index << 16) | 5).to_bytes(4, 'little'))):
            raise ValueError('invalid activation index or response bytes')
        matches.append(action)
    if len(matches) != 1:
        raise ValueError('activation must have exactly one matching action')
    return deepcopy(matches[0])


def response_fixtures() -> dict:
    """Return synthetic vectors only; no actual native prompt or legality evidence."""
    def word_action(choice, value):
        return {'choice': choice, 'card_ids': [], 'bytes': list(value.to_bytes(4, 'little'))}

    zones = [{'player': 0, 'location': 4, 'sequence': 0},
             {'player': 0, 'location': 4, 'sequence': 1},
             {'player': 1, 'location': 4, 'sequence': 0}]

    def place_action(indices):
        selected = [deepcopy(zones[i]) for i in indices]
        return {'choice': {'kind': 'place', 'zones': selected}, 'card_ids': [],
                'bytes': [number for zone in selected for number in (zone['player'], zone['location'], zone['sequence'])]}

    return {'synthetic': True, 'native_frames': [], 'native_reachability_verified': False,
            'response_acceptance_verified': False, 'formal_release_status': 'unknown',
            'prompts': [
                {'opcode': 13, 'player': 0, 'actions': [word_action({'kind': 'yes_no', 'yes': yes}, int(yes)) for yes in (False, True)]},
                {'opcode': 14, 'player': 0, 'actions': [word_action({'kind': 'option', 'index': i}, i) for i in (0, 1)]},
                {'opcode': 24, 'player': 0, 'mask': 0xfffefffc, 'count': 2,
                 'actions': [place_action(pair) for pair in ((0, 1), (0, 2), (1, 2))]}],
            'reverse_order_example': place_action((1, 0))}
