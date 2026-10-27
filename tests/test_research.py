import copy
import unittest
from ygo_eval.research import validate_case

def sample():
    return {'schema_version': 1, 'case_id': 'synthetic', 'purpose': 'protocol_audit',
            'rules': {'region': 'OCG', 'version': '2026-10-01', 'banlist_sha256': 'a'*64},
            'assets': {name: 'a'*64 for name in ('engine_sha256','cdb_sha256','scripts_sha256')},
            'deck': {'main': list(range(1,41)), 'extra': [], 'side': []},
            'opening_hand': [1,2,3,4,5], 'seed': 1,
            'objective': {'priorities': ['terminal_utility'], 'terminal_utility': {'normal':1,'early_win':2,'loss':-1,'draw':0}},
            'information': {'player_visible':['own_hand','public_board'], 'opponent_visible':['opponent_hand','public_board'], 'hidden':['own_deck_order','opponent_deck_order','opponent_hand'], 'opponent_resources': {'main':list(range(41,81)), 'hand':[41,42,43,44,45]}},
            'randomness': {'model':'frozen_scenario', 'outcomes':[{'id':'fixed','numerator':1,'denominator':1}], 'seed_role':'reproduction_only'}}

class ResearchTests(unittest.TestCase):
    def test_valid_frozen_case_has_no_optimality_claim(self):
        self.assertFalse(validate_case(sample())['global_optimality'])
    def test_incomplete_or_ill_formed_information_and_evaluation_are_rejected(self):
        for section in ('objective','information','randomness'):
            value=sample(); del value[section]
            with self.assertRaises(ValueError): validate_case(value)
        for modify in (lambda v: v['objective']['terminal_utility'].pop('draw'),
                       lambda v: v['randomness']['outcomes'][0].update(numerator=2),
                       lambda v: v['information']['player_visible'].append('opponent_hand'),
                       lambda v: v.update(opening_hand=[1,2,3,4,99]),
                       lambda v: v.update(seed=True)):
            value=sample(); modify(value)
            with self.assertRaises(ValueError): validate_case(value)

    def test_sources_validate_real_cdb_alias_zones_and_banlist(self):
        import hashlib
        import json
        from pathlib import Path
        import sqlite3
        from test_coverage_language import temporary_directory
        from contextlib import closing
        from ygo_eval.research import validate_sources
        with temporary_directory() as temporary:
            root=Path(temporary)
            db=root/'cards.cdb'
            with closing(sqlite3.connect(db)) as conn:
                conn.execute('CREATE TABLE datas (id INTEGER, alias INTEGER, type INTEGER, ot INTEGER)')
                conn.executemany('INSERT INTO datas VALUES (?,0,17,1)',[(n,) for n in range(1,41)])
                conn.commit()
            dll=root/'core.dll'; dll.write_bytes(b'synthetic')
            scripts=root/'scripts.json'; scripts.write_text('{}')
            ban=root/'ban.json'; ban.write_text(json.dumps({'data':{'region':'OCG','version':'2026-10-01','limits':{'1':'Limited'}}}))
            case=sample(); case['information']['opponent_resources']={'main':case['deck']['main'],'hand':[]}
            case['rules']['banlist_sha256']=hashlib.sha256(ban.read_bytes()).hexdigest()
            case['assets']={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in [('engine_sha256',dll),('cdb_sha256',db),('scripts_sha256',scripts)]}
            request={'deck':case['deck'],'opening_hand':case['opening_hand'],'seed':case['seed'],'engine':{'timeout_ms':30000,'ocgcore_path':str(dll),'catalog_path':str(db),'script_manifest_path':str(scripts)},'versions':{'rules':'ocg-mr5',**case['assets']}}
            validate_sources(case,request,ban)
            for mutation in ('alias=1','type=16384','ot=2','type=64'):
                with closing(sqlite3.connect(db)) as conn:
                    conn.execute('UPDATE datas SET '+mutation+' WHERE id=2'); conn.commit()
                case['assets']['cdb_sha256']=hashlib.sha256(db.read_bytes()).hexdigest(); request['versions']['cdb_sha256']=case['assets']['cdb_sha256']
                with self.assertRaises(ValueError): validate_sources(case,request,ban)
                with closing(sqlite3.connect(db)) as conn:
                    conn.execute('UPDATE datas SET alias=0,type=17,ot=1 WHERE id=2'); conn.commit()
            case['assets']['cdb_sha256']=hashlib.sha256(db.read_bytes()).hexdigest(); request['versions']['cdb_sha256']=case['assets']['cdb_sha256']
            ban.write_text('{}')
            with self.assertRaises(ValueError): validate_sources(case,request,ban)

    def test_run_refuses_tracked_ledger_before_spawning_worker(self):
        from pathlib import Path
        from unittest.mock import patch
        import sys
        from ygo_eval.research import main
        root=Path(__file__).resolve().parents[1]
        with patch('sys.argv',['research','run','--cases',str(root/'tests/fixtures/rabbit.request.json'),'--runner',sys.executable,'--ledger',str(root/'TASKS.md'),'--output',str(root/'data/runtime/research')]):
            with self.assertRaises(ValueError): main()
