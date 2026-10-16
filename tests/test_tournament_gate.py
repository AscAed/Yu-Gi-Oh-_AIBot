"""Source, release and coverage checks independent of the planner."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import unittest

from ygo_data.tournament import validate_gate


ROOT = Path(__file__).resolve().parents[1]


class TournamentGate(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((ROOT / 'configs/tournament-2026.source.json')
                                 .read_text(encoding='utf-8'))
        self.deck = (ROOT / 'tests/fixtures/tournament-2026.deck.json').read_bytes()
        self.coverage = json.loads((ROOT / 'knowledge/tournament-2026.coverage.json')
                                   .read_text(encoding='utf-8'))

    def check(self):
        return validate_gate(self.source, self.deck, self.coverage)

    def test_original_counts_and_unpublished_side_are_explicit(self):
        result = self.check()
        self.assertEqual(result['counts'], {'main': 41, 'extra': 15})
        self.assertEqual(result['inside_rules'], 85)
        self.assertFalse(result['semantics_verified'])

    def test_changed_deck_or_unclassified_rule_is_rejected(self):
        original = self.deck
        self.deck = self.deck.replace(b'83566725', b'24224830', 1)
        with self.assertRaisesRegex(ValueError, 'deck hash'):
            self.check()
        self.deck = original
        self.coverage['cards'][0]['entries'][0]['applicability'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'unclassified'):
            self.check()

    def test_release_after_cutoff_and_rule_mapping_difference_are_rejected(self):
        self.source['releases'][0]['ocg_released_by'] = '2026-12-01'
        with self.assertRaisesRegex(ValueError, 'release'):
            self.check()
        self.setUp()
        self.source['rules']['differences'] = [{'card_id': 1}]
        with self.assertRaisesRegex(ValueError, 'rule comparison'):
            self.check()

    def test_effect_omission_and_unexplained_exclusion_are_rejected(self):
        self.coverage['cards'].pop()
        with self.assertRaisesRegex(ValueError, 'coverage card set'):
            self.check()
        self.setUp()
        entry = next(e for c in self.coverage['cards'] for e in c['entries']
                     if e['applicability'] == 'outside_scenario')
        entry['exclusion_basis'] = ''
        with self.assertRaisesRegex(ValueError, 'exclusion'):
            self.check()

    def test_unpublished_side_cannot_claim_full_legality(self):
        self.source['side']['legality_verified'] = True
        with self.assertRaisesRegex(ValueError, 'unpublished side'):
            self.check()

    def test_selected_source_requires_independent_full_transcription(self):
        self.source['transcription']['independent_check'] = False
        with self.assertRaisesRegex(ValueError, 'transcription'):
            self.check()
        self.setUp()
        self.source['selected']['event_date'] = '2025-12-31'
        with self.assertRaisesRegex(ValueError, 'event date'):
            self.check()


@unittest.skipUnless(os.environ.get('YGO_TOURNAMENT_ENGINE'),
                     'opt-in: independent 2026 asset config required')
class TournamentEngineCompatibility(unittest.TestCase):
    def test_manual_new_card_route_and_independent_replay(self):
        import tomllib
        from ygo_data.assets import verify_group

        config = Path(os.environ['YGO_TOURNAMENT_ENGINE'])
        engine = tomllib.loads(config.read_text(encoding='utf-8'))
        group = verify_group(Path(engine['catalog_path']).parent)
        case = json.loads((ROOT / 'tests/fixtures/tournament-2026.asset-probe.json')
                          .read_text(encoding='utf-8'))
        deck_bytes = (ROOT / 'tests/fixtures/tournament-2026.deck.json').read_bytes()
        self.assertEqual(hashlib.sha256(deck_bytes).hexdigest(), case['deck_sha256'])
        recipe = group['recipe']
        request = {
            'protocol_version': 2, 'engine': engine, 'deck': json.loads(deck_bytes),
            'opening_hand': case['opening_hand'], 'seed': case['seed'],
            'decisions': case['decisions'], 'probe_only': False,
            'versions': {'rules': 'ocg-mr5', 'catalog': '',
                         'banlist': recipe['banlist_id'],
                         'core_commit': recipe['core']['core_commit'],
                         'initializer': 'fixed-hand-shuffle-v1',
                         'engine_sha256': recipe['core']['sha256'],
                         'cdb_sha256': recipe['catalog']['sha256'],
                         'scripts_sha256': recipe['scripts']['manifest_sha256']}}
        results = []
        # This deployment audit has its own ledger, outside all sample metrics.
        journal = config.parent / 'asset-probe-audit.jsonl'
        for attempt in range(2):
            with journal.open('a', encoding='utf-8') as log:
                log.write(json.dumps({'case_id': case['case_id'],
                                      'attempt': attempt, 'status': 'debited'}) + '\n')
                log.flush()
                os.fsync(log.fileno())
            proc = subprocess.run([engine['worker_path']], input=json.dumps(request) + '\n',
                                  text=True, capture_output=True, timeout=40, check=True)
            result = json.loads(proc.stdout)
            self.assertEqual(result['status'], 'engine_verified', result['error'])
            events = result['events']
            cards = result['checkpoint']['cards']
            expected = case['expected']
            self.assertEqual([c['code'] for c in cards if c['player'] == 0 and
                              c['location'] == 4 and c['position'] & 5],
                             expected['faceup_monsters'])
            self.assertEqual([c['code'] for c in cards if c['player'] == 0 and
                              c['location'] == 8 and c['position'] & 10],
                             expected['set_traps'])
            moves = [e['fields'] for e in events if e['opcode'] == 50]
            self.assertTrue(any(m['code'] == expected['deck_to_grave_effect'] and
                                m['from']['location'] == 1 and m['to']['location'] == 16
                                and m['reason'] & 64 for m in moves))
            self.assertTrue(any(m['code'] == expected['detached_material'] and
                                m['from']['location'] & 128 and m['to']['location'] == 16
                                and m['reason'] & 128 for m in moves))
            for code in expected['new_resolved_effects']:
                starts = [i for i, e in enumerate(events) if e['opcode'] == 70 and
                          e['fields']['code'] == code]
                self.assertTrue(starts, code)
                start = starts[0]
                chain = events[start]['fields']['chain']
                end = next(i for i in range(start + 1, len(events))
                           if events[i]['opcode'] == 74)
                segment = events[start + 1:end]
                self.assertTrue(any(e['opcode'] == 73 and e['fields']['chain'] == chain
                                    for e in segment), code)
                self.assertFalse(any(e['opcode'] in (75, 76) and
                                     e['fields']['chain'] == chain for e in segment), code)
            results.append({k: result[k] for k in
                            ('status', 'events', 'checkpoint', 'resolved_decisions')})
        self.assertEqual(results[0], results[1])


if __name__ == '__main__':
    unittest.main()
