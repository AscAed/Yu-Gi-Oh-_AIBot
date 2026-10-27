import json
import sqlite3
from contextlib import closing
import shutil
from contextlib import contextmanager
from uuid import uuid4
import unittest
from pathlib import Path
from ygo_data.coverage import inventory, tournament_evidence
from ygo_data.language import audit_language


@contextmanager
def temporary_directory():
    base = Path(__file__).resolve().parents[1] / 'data' / 'tmp'
    root = base / ('coverage-' + uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield str(root)
    finally:
        if not root.resolve().is_relative_to(base.resolve()):
            raise ValueError('unsafe cleanup')
        shutil.rmtree(root)


class CoverageInventoryTests(unittest.TestCase):
    def test_classifies_evidence_and_keeps_alias_conflicts(self):
        with temporary_directory() as tmp:
            root = Path(tmp)
            cdb = root / 'cards.cdb'
            with closing(sqlite3.connect(cdb)) as db:
                db.execute('CREATE TABLE datas (id INTEGER, ot INTEGER, alias INTEGER, type INTEGER)')
                db.executemany('INSERT INTO datas VALUES (?, ?, ?, ?)', [
                    (1, 1, 0, 17), (2, 1, 1, 33), (3, 2, 0, 33),
                    (4, 1, 0, 0x4001), (5, 1, 0, 33), (6, 1, 99, 33)])
                db.commit()
            manifest = root / 'scripts.json'
            manifest.write_text(json.dumps({'c2.lua': '0' * 64}), encoding='utf-8')
            records = [{'card_id': 1, 'status': 'released', 'released_by': '2025-01-01',
                        'region': 'OCG', 'evidence': [{'url': 'synthetic', 'sha256': '1' * 64}]}]
            records += [dict(records[0]), {'card_id': 2, 'status': 'prerelease', 'region': 'OCG'}]
            result = inventory(cdb, manifest, {'schema_version': 1, 'records': records})
            rows = {r['card_id']: r for r in result['cards']}
            self.assertEqual(rows[1]['script_status'], 'not_required')
            self.assertEqual(rows[2]['release_status'], 'prerelease')
            self.assertEqual(rows[2]['script_status'], 'unknown')
            self.assertEqual(rows[3]['release_status'], 'region_mismatch')
            self.assertEqual(rows[4]['release_status'], 'rule_generated')
            self.assertEqual(rows[5]['release_status'], 'identity_unconfirmed')
            self.assertIn('alias_target_missing', rows[6]['unresolved'])
            self.assertIn('duplicate_release_record:1', result['unresolved'])
            self.assertFalse(result['complete'])
            self.assertFalse(result['dynamic_dependencies_verified'])

    def test_rejects_invalid_hash_and_prerelease_conflict_and_alias_cycle(self):
        with temporary_directory() as tmp:
            root = Path(tmp)
            cdb = root / 'cards.cdb'
            with closing(sqlite3.connect(cdb)) as db:
                db.execute('CREATE TABLE datas (id INTEGER, ot INTEGER, alias INTEGER, type INTEGER)')
                db.executemany('INSERT INTO datas VALUES (?, ?, ?, ?)', [(1, 257, 2, 33), (2, 1, 1, 33)])
                db.commit()
            scripts = root / 'scripts.json'
            scripts.write_text('{}')
            row = {'card_id': 1, 'status': 'released', 'region': 'OCG', 'released_by': '2025-01-01',
                   'evidence': [{'url': 'synthetic', 'sha256': 'z' * 64}]}
            with self.assertRaises(ValueError):
                inventory(cdb, scripts, {'schema_version': 1, 'records': [row]})
            row['evidence'][0]['sha256'] = 'a' * 64
            result = inventory(cdb, scripts, {'schema_version': 1, 'records': [row]})
            card = result['cards'][0]
            self.assertEqual(card['release_status'], 'prerelease')
            self.assertIn('region_prerelease_evidence_conflict', card['unresolved'])
            self.assertIn('alias_cycle', card['unresolved'])
            with self.assertRaises(ValueError):
                inventory(cdb, scripts, {'schema_version': 1, 'records': [row]}, evidence_root=root)

    def test_actual_script_hash_is_required_for_coverage(self):
        import hashlib
        from unittest.mock import patch
        from ygo_data.coverage import digest
        with temporary_directory() as tmp:
            root = Path(tmp)
            cdb = root / 'cards.cdb'
            with closing(sqlite3.connect(cdb)) as db:
                db.execute('CREATE TABLE datas (id INTEGER, ot INTEGER, alias INTEGER, type INTEGER)')
                db.execute('INSERT INTO datas VALUES (1,1,0,33)')
                db.commit()
            script = root / 'c1.lua'
            script.write_bytes(b'-- synthetic')
            manifest = root / 'scripts.json'
            manifest.write_text(json.dumps({'c1.lua': hashlib.sha256(script.read_bytes()).hexdigest()}))
            evidence = {'schema_version': 1, 'records': []}
            result = inventory(cdb, manifest, evidence, script_root=root)
            self.assertEqual(result['cards'][0]['script_status'], 'covered')
            script.write_bytes(b'-- changed')
            result = inventory(cdb, manifest, evidence, script_root=root)
            self.assertEqual(result['cards'][0]['script_status'], 'missing')
            count = 0
            def unstable(path):
                nonlocal count
                if path == cdb:
                    count += 1
                    if count > 1:
                        return 'f' * 64
                return digest(path)
            with patch('ygo_data.coverage.digest', side_effect=unstable):
                with self.assertRaisesRegex(ValueError, 'changed during'):
                    inventory(cdb, manifest, evidence)

    def test_cli_rejects_outputs_inside_assets_and_language_inputs(self):
        from unittest.mock import patch
        from ygo_data.coverage import main as coverage_main
        from ygo_data.language import main as language_main
        with temporary_directory() as tmp:
            root = Path(tmp)
            script = root / 'c1.lua'
            script.write_bytes(b'-- original')
            args = ['coverage', 'inventory', '--cdb', str(root / 'missing.cdb'),
                    '--scripts', str(root / 'scripts.json'), '--evidence', str(root / 'evidence.json'),
                    '--script-root', str(root), '--output', str(script)]
            with patch('sys.argv', args), self.assertRaises(SystemExit):
                coverage_main()
            self.assertEqual(script.read_bytes(), b'-- original')
            args = ['language', 'audit', '--sources', str(script), '--sample', str(script), '--output', str(script)]
            with patch('sys.argv', args), self.assertRaises(SystemExit):
                language_main()
            self.assertEqual(script.read_bytes(), b'-- original')

    def test_alias_script_presence_does_not_certify_effect_coverage(self):
        with temporary_directory() as tmp:
            root = Path(tmp)
            cdb = root / 'cards.cdb'
            with closing(sqlite3.connect(cdb)) as db:
                db.execute('CREATE TABLE datas (id INTEGER, ot INTEGER, alias INTEGER, type INTEGER)')
                db.executemany('INSERT INTO datas VALUES (?, ?, ?, ?)', [(1, 1, 0, 33), (2, 1, 1, 33)])
                db.commit()
            manifest = root / 'scripts.json'
            manifest.write_text(json.dumps({'c1.lua': 'a' * 64}))
            result = inventory(cdb, manifest, {'schema_version': 1, 'records': []})
            self.assertEqual(result['cards'][1]['script_status'], 'unknown')
            self.assertIn('alias_script_reuse_unverified', result['cards'][1]['unresolved'])

    def test_missing_cdb_is_never_created(self):
        with temporary_directory() as tmp:
            root = Path(tmp)
            (root / 'scripts.json').write_text('{}')
            with self.assertRaises(sqlite3.OperationalError):
                inventory(root / 'missing.cdb', root / 'scripts.json', {'schema_version': 1, 'records': []})
            self.assertFalse((root / 'missing.cdb').exists())

    def test_tournament_upper_bound_is_not_first_release(self):
        result = tournament_evidence(Path('configs/tournament-2026.source.json'))
        self.assertEqual(len(result['records']), 39)
        self.assertTrue(all(r['release_date'] is None for r in result['records']))
        self.assertTrue(all(r['released_by'] for r in result['records']))


class InventorySchemaTests(unittest.TestCase):
    def test_rejects_missing_trust_and_self_signed_verification(self):
        import copy
        import jsonschema
        schema = json.loads(Path('schemas/coverage-inventory.schema.json').read_text())
        report = {'schema_version': 1, 'cutoff': '2026-10-19', 'complete': False,
                  'denominator_status': 'unresolved', 'dynamic_dependencies_verified': False,
                  'region': 'OCG', 'scope': 'synthetic', 'release_evidence_trust': 'declared_provenance_only',
                  'source_verified': False, 'provided_evidence_bytes_checked': False,
                  'inputs': {k: 'a' * 64 for k in ['cdb', 'scripts', 'release_evidence']},
                  'cards': [], 'counts': {}, 'unresolved': []}
        jsonschema.validate(report, schema)
        for key in ('release_evidence_trust', 'source_verified', 'provided_evidence_bytes_checked', 'inputs'):
            changed = copy.deepcopy(report)
            del changed[key]
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(changed, schema)
        report['source_verified'] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)

    def test_rejects_language_fields_without_provenance_and_unknown_top_level(self):
        import jsonschema
        schema = json.loads(Path('schemas/language-audit.schema.json').read_text())
        report = audit_language([1], [], [])
        jsonschema.validate(report, schema)
        report['records'] = [{'card_id': 1, 'language': 'zh-Hans', 'name': {'value': 'synthetic'}}]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)
        report['records'] = []
        report['invented_trust'] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)


class LanguageAuditTests(unittest.TestCase):
    def test_language_cli_rejects_invalid_records_before_creating_report(self):
        from contextlib import redirect_stderr
        from io import StringIO
        from unittest.mock import patch
        from ygo_data.language import main

        with temporary_directory() as temporary:
            root = Path(temporary)
            sources = root / 'sources.json'
            sample = root / 'sample.json'
            records = root / 'records.json'
            output = root / 'report.json'
            sources.write_text(json.dumps({'sources': []}), encoding='utf-8')
            sample.write_text(json.dumps({'records': [{'card_id': 1}]}), encoding='utf-8')
            records.write_text(json.dumps([{
                'card_id': 1,
                'language': 'zh-Hans',
                'unexpected': True,
            }]), encoding='utf-8')
            args = [
                'ygo-data', 'audit', '--sources', str(sources), '--sample', str(sample),
                '--records', str(records), '--output', str(output),
            ]
            stderr = StringIO()
            with patch('sys.argv', args), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn('invalid language audit input', stderr.getvalue())
            self.assertIn('unknown fields', stderr.getvalue())
            self.assertFalse(output.exists())

    def test_rejects_language_records_that_cannot_fit_the_report_schema(self):
        import jsonschema

        schema = json.loads(Path('schemas/language-audit.schema.json').read_text())
        valid_partial = {
            'card_id': 1,
            'language': 'zh-Hans',
            'name': {'value': '候选名', 'source': 'synthetic', 'status': 'unverified'},
        }
        jsonschema.validate(audit_language([1], [], [valid_partial]), schema)

        invalid_records = [
            {'card_id': 1, 'language': 'zh-Hans', 'note': 'unknown record field'},
            {'card_id': 1},
            {'card_id': 1, 'language': 'en'},
            {
                'card_id': 1,
                'language': 'zh-Hans',
                'name': {
                    'value': '候选名',
                    'source': 'synthetic',
                    'status': 'unverified',
                    'note': 'unknown value field',
                },
            },
        ]
        for record in invalid_records:
            with self.subTest(record=record), self.assertRaises(ValueError):
                audit_language([1], [], [record])

    def test_rejects_malformed_source_hash_and_self_reported_field_types(self):
        source = {'id': 'synthetic', 'language': 'zh-Hans', 'version': 'fixture',
                  'sha256': 'NOT-A-HASH', 'license': {'redistribution': 'permitted'}}
        with self.assertRaises(ValueError):
            audit_language([1], [source], [])
        source['sha256'] = 'a' * 64
        with self.assertRaises(ValueError):
            audit_language([1, 1], [source], [])
        with self.assertRaises(ValueError):
            audit_language([1], [source], [{'card_id': 1, 'language': 'zh-Hans',
                                          'name': {'value': 42, 'source': 'synthetic', 'status': 'verified'}}])
        with self.assertRaises(ValueError):
            audit_language([1], [source], [{'card_id': 1, 'language': 'zh-Hans',
                                          'name': {'value': 'synthetic', 'source': 'synthetic', 'status': 'invented'}}])

    def test_independent_fields_no_guessing_and_ambiguous_names(self):
        source = {'id': 'synthetic', 'language': 'zh-Hans', 'version': 'fixture-1',
                  'sha256': '1' * 64, 'license': {'redistribution': 'unknown'}}
        records = [
            {'card_id': 1, 'language': 'zh-Hans', 'name': {'value': '同名', 'source': 'synthetic', 'status': 'verified'}},
            {'card_id': 2, 'language': 'zh-Hans', 'name': {'value': '同名', 'source': 'synthetic', 'status': 'verified'}},
            {'card_id': 1, 'language': 'zh-Hant', 'name': {'value': '同名繁', 'source': 'synthetic', 'status': 'unverified'}},
            {'card_id': 3, 'language': 'zh-Hans', 'alias': {'value': ['别称'], 'source': 'absent', 'status': 'verified'}}]
        result = audit_language([1, 2, 3, 4], [source], records)
        self.assertFalse(result['qualified'])
        self.assertEqual(result['ambiguous_names'][0]['card_ids'], [1, 2])
        self.assertIn(4, result['missing_card_ids'])
        self.assertTrue(any('unknown_source' in issue for issue in result['unresolved']))
        self.assertTrue(any('redistribution' in issue for issue in result['unresolved']))


if __name__ == '__main__':
    unittest.main()
