"""Pure synthetic probability and ordering audits; no engine evidence is created."""

from fractions import Fraction


def _rational(value: Fraction) -> dict:
    return {'numerator': value.numerator, 'denominator': value.denominator}


def validate_distribution(entries: list[dict]) -> Fraction:
    """Validate unique string-vector outcomes and exact nonnegative mass of one.

    Entries have ``outcome: list[str]`` and ``probability`` containing integer
    numerator and positive integer denominator. No float conversion is allowed.
    """
    seen = set()
    mass = Fraction()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'outcome', 'probability'}:
            raise ValueError('invalid distribution entry')
        outcome = entry['outcome']
        probability = entry['probability']
        if not isinstance(outcome, list) or not all(isinstance(v, str) for v in outcome):
            raise ValueError('invalid outcome')
        key = tuple(outcome)
        if key in seen:
            raise ValueError('duplicate outcome')
        seen.add(key)
        if not isinstance(probability, dict) or set(probability) != {'numerator', 'denominator'}:
            raise ValueError('invalid rational probability')
        numerator, denominator = probability['numerator'], probability['denominator']
        if type(numerator) is not int or type(denominator) is not int:
            raise ValueError('probability must use exact integers')
        if numerator < 0 or denominator <= 0:
            raise ValueError('invalid probability sign or denominator')
        mass += Fraction(numerator, denominator)
    if mass != 1:
        raise ValueError('probability mass is not one')
    return mass


def fisher_yates_distribution(labels: tuple[str, ...]) -> dict[tuple[str, ...], Fraction]:
    """Enumerate forward Fisher–Yates under independent uniform index choices."""
    if not labels or any(not isinstance(x, str) for x in labels) or len(set(labels)) != len(labels):
        raise ValueError('nonempty distinct instance labels required')
    if len(labels) > 8:
        raise ValueError('synthetic enumeration supports at most eight labels')
    frontier = {tuple(labels): Fraction(1)}
    for index in range(len(labels) - 1):
        following = {}
        branch_probability = Fraction(1, len(labels) - index)
        for order, probability in frontier.items():
            for selected in range(index, len(labels)):
                changed = list(order)
                changed[index], changed[selected] = changed[selected], changed[index]
                key = tuple(changed)
                following[key] = following.get(key, Fraction()) + probability * branch_probability
        frontier = following
    return frontier


def _entries(distribution: dict[tuple[str, ...], Fraction]) -> list[dict]:
    return [{'outcome': list(order), 'probability': _rational(probability)}
            for order, probability in sorted(distribution.items())]


def audit_probability() -> dict:
    """Return the exact ideal five-instance model and its code-order marginal."""
    labelled = fisher_yates_distribution(('A0', 'A1', 'A2', 'B0', 'R0'))
    marginal = {}
    for order, probability in labelled.items():
        codes = tuple(label[0] for label in order)
        marginal[codes] = marginal.get(codes, Fraction()) + probability
    labelled_entries, marginal_entries = _entries(labelled), _entries(marginal)
    labelled_mass = validate_distribution(labelled_entries)
    marginal_mass = validate_distribution(marginal_entries)
    valid = (len(labelled) == 120 and len(marginal) == 20
             and all(p == Fraction(1, 120) for p in labelled.values())
             and all(p == Fraction(1, 20) for p in marginal.values()))
    return {'model': 'synthetic-independent-uniform-fisher-yates-v1',
            'origin': 'synthetic', 'valid': valid,
            'labelled_count': len(labelled), 'card_order_count': len(marginal),
            'labelled_distribution': labelled_entries,
            'card_order_distribution': marginal_entries,
            'labelled_mass': _rational(labelled_mass),
            'card_order_mass': _rational(marginal_mass),
            'native_probability_verified': False,
            'instance_merging_verified': False,
            'shuffle_deletion_safe': False,
            'gaps': ['PRNG state distribution', 'conditional random index distribution',
                     'rejection sampling', 'subsequent random behavior']}


def validate_probability_report(report: dict) -> bool:
    """Independently check the frozen outcome sets and exact marginal weights."""
    from itertools import permutations
    labelled_entries = report['labelled_distribution']
    marginal_entries = report['card_order_distribution']
    validate_distribution(labelled_entries)
    validate_distribution(marginal_entries)
    expected_labels = set(permutations(('A0', 'A1', 'A2', 'B0', 'R0')))
    labelled = {tuple(e['outcome']): Fraction(e['probability']['numerator'],
                                            e['probability']['denominator'])
                for e in labelled_entries}
    if set(labelled) != expected_labels or any(p != Fraction(1, 120) for p in labelled.values()):
        raise ValueError('labelled outcomes or probabilities differ from frozen model')
    expected_codes = set(permutations(('A', 'A', 'A', 'B', 'R')))
    marginal = {tuple(e['outcome']): Fraction(e['probability']['numerator'],
                                            e['probability']['denominator'])
                for e in marginal_entries}
    if set(marginal) != expected_codes or any(p != Fraction(1, 20) for p in marginal.values()):
        raise ValueError('card-order aggregate differs from frozen model')
    required_metadata = {
        'model': 'synthetic-independent-uniform-fisher-yates-v1',
        'origin': 'synthetic', 'valid': True,
        'labelled_count': 120, 'card_order_count': 20,
        'labelled_mass': {'numerator': 1, 'denominator': 1},
        'card_order_mass': {'numerator': 1, 'denominator': 1},
        'native_probability_verified': False, 'instance_merging_verified': False,
        'shuffle_deletion_safe': False,
    }
    for key, expected in required_metadata.items():
        if report.get(key) != expected or type(report.get(key)) is not type(expected):
            raise ValueError(f'probability metadata mismatch: {key}')
    return True


def audit_ordering() -> dict:
    """Demonstrate ordered representation/encoding, without claiming legality.

    Synthetic opcode-15 word arrays and opcode-18 zone triples mirror the
    existing Choice format. Reverse orders are not injected into any parser.
    """
    cards = []
    places = []
    for indices in ([0, 1], [1, 0]):
        words = [0, len(indices), *indices]
        cards.append({'choice': {'kind': 'cards', 'indices': indices},
                      'card_codes': ['A', 'A'],
                      'positions': indices,
                      'bytes': list(b''.join(w.to_bytes(4, 'little') for w in words))})
        zones = [{'player': 0, 'location': 4, 'sequence': i} for i in indices]
        places.append({'choice': {'kind': 'place', 'zones': zones},
                       'bytes': [v for zone in zones
                                 for v in (zone['player'], zone['location'], zone['sequence'])]})
    return {'origin': 'synthetic', 'valid': True, 'cards': cards, 'places': places,
            'distinct_position_instances_preserved': True,
            'native_legality': 'unverified', 'order_equivalence_proven': False,
            'production_reverse_responses_added': False}


def validate_ordering_report(report: dict) -> bool:
    """Check fixed synthetic witnesses against independently written byte arrays.

    These vectors follow codec.rs opcode 15's little-endian words and opcode
    18's zone triples. Validation checks representation only, not core legality.
    """
    expected_cards = [
        {'choice': {'kind': 'cards', 'indices': [0, 1]},
         'card_codes': ['A', 'A'], 'positions': [0, 1],
         'bytes': [0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]},
        {'choice': {'kind': 'cards', 'indices': [1, 0]},
         'card_codes': ['A', 'A'], 'positions': [1, 0],
         'bytes': [0, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]},
    ]
    expected_places = [
        {'choice': {'kind': 'place', 'zones': [
            {'player': 0, 'location': 4, 'sequence': 0},
            {'player': 0, 'location': 4, 'sequence': 1}]},
         'bytes': [0, 4, 0, 0, 4, 1]},
        {'choice': {'kind': 'place', 'zones': [
            {'player': 0, 'location': 4, 'sequence': 1},
            {'player': 0, 'location': 4, 'sequence': 0}]},
         'bytes': [0, 4, 1, 0, 4, 0]},
    ]
    if report.get('cards') != expected_cards or report.get('places') != expected_places:
        raise ValueError('ordered Choice, instance position or bytes mismatch')
    required_metadata = {
        'origin': 'synthetic', 'valid': True,
        'distinct_position_instances_preserved': True,
        'native_legality': 'unverified', 'order_equivalence_proven': False,
        'production_reverse_responses_added': False,
    }
    for key, expected in required_metadata.items():
        if report.get(key) != expected or type(report.get(key)) is not type(expected):
            raise ValueError(f'ordering metadata mismatch: {key}')
    return True


run_math_audit = audit_probability
run_order_audit = audit_ordering
