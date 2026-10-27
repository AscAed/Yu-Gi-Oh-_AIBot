import copy
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from test_coverage_language import temporary_directory
from ygo_eval.terminal_regression import verified_parent, CASE_IDS


class TerminalRegressionTests(unittest.TestCase):
    def parent_fixture(self, directory):
        prompt = {'id':9,'player':0,'opcode':11,'actions':[{'choice':{'kind':'command','command':7,'index':0},'bytes':[7,0,0,0]}]}
        result = {'prompt':prompt,'events':[{'sequence':9,'opcode':11,'raw':[11,0]+[0]*24+[0,1,0],'fields':{'prompt':copy.deepcopy(prompt)}}]}
        paths = {key:Path(directory)/key for key in ['parent_input','parent_evidence','previous_ledger','parent_runner']}
        invocation = {'output':str(paths['parent_evidence']), 'ledger':str(paths['previous_ledger']),'case_id':'rabbit-shuffle'}
        parent = {'request':{'decisions':[]},'runs':[{'Ok':result},{'Ok':result}], 'independent_replay_matches':True,'assets_unchanged':True}
        paths['parent_input'].write_text(json.dumps(invocation));paths['parent_evidence'].write_text(json.dumps(parent))
        return paths,parent

    def test_verified_public_parent_is_derived_without_worker(self):
        with temporary_directory() as directory:
            paths,parent = self.parent_fixture(directory)
            outcome = subprocess.CompletedProcess([],0,b'{"ledger":{"consumed":8,"unknown":0,"reserved":0}}')
            with patch('ygo_eval.terminal_regression.subprocess.run',return_value=outcome) as called:
                _,derived = verified_parent(paths,{'parent_input':'hash'})
            self.assertEqual(derived['decisions'][0]['prompt_id'],9)
            self.assertIn('--verify-recorded',called.call_args.args[0])
            self.assertEqual(CASE_IDS,['terminal-rabbit','terminal-tournament','terminal-shuffle-end'])
            self.assertEqual(parent['request']['decisions'],[])

    def test_unknown_old_consumption_and_tampered_menu_refuse(self):
        with temporary_directory() as directory:
            paths,parent = self.parent_fixture(directory)
            bad = subprocess.CompletedProcess([],0,b'{"ledger":{"consumed":8,"unknown":1,"reserved":0}}')
            with patch('ygo_eval.terminal_regression.subprocess.run',return_value=bad):
                with self.assertRaises(ValueError):verified_parent(paths,{'parent_input':'hash'})
            parent['runs'][0]['Ok']['prompt']['actions'][0]['bytes']=[8,0,0,0]
            paths['parent_evidence'].write_text(json.dumps(parent))
            good = subprocess.CompletedProcess([],0,b'{"ledger":{"consumed":8,"unknown":0,"reserved":0}}')
            with patch('ygo_eval.terminal_regression.subprocess.run',return_value=good):
                with self.assertRaises(ValueError):verified_parent(paths,{'parent_input':'hash'})


    def test_terminal_pair_contract_never_grants_proof(self):
        from test_schemas import validator
        report = {'schema_version':1,'kind':'terminal_regression_pair','case_id':'terminal-rabbit',
                  'request':{},'runs':[],'terminal_audits':[],'ledger':{},'diagnostic':'not_run',
                  'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        check = validator('terminal-regression.schema.json')
        check.validate(report)
        report['proof_ready'] = True
        self.assertTrue(list(check.iter_errors(report)))

    def test_partial_terminal_summary_contract_and_limits(self):
        from test_schemas import validator
        report = {'schema_version':1,'kind':'terminal_regression_summary','context':'a'*64,
                  'cases':[{'case_id':'terminal-rabbit','evidence_sha256':'b'*64,
                            'diagnostic':'engine_or_journal_error',
                            'ledger':{'consumed':1,'completed':1,'abandoned':0,'unknown':0,'reserved':0,'limit':6}}],
                  'successful':False,'diagnostic':'engine_or_journal_error',
                  'old_consumed':17,'new_consumed':1,'proof_ready':False,
                  'complete_action_coverage':False,'global_optimality':False}
        check=validator('terminal-regression.schema.json')
        check.validate(report)
        for key,value in [('new_consumed',7),('proof_ready',True),('old_consumed',0),('unexpected',1)]:
            changed=copy.deepcopy(report);changed[key]=value
            self.assertTrue(list(check.iter_errors(changed)),key)
        report['new_consumed']=None;report['cases']=[]
        check.validate(report)
        report['new_consumed']=6;report['diagnostic']=None;report['successful']=True
        report['cases']=[{'case_id':case,'evidence_sha256':'b'*64,'diagnostic':None,
                         'ledger':{'consumed':2*(index+1),'completed':2*(index+1),'abandoned':0,'unknown':0,'reserved':0,'limit':6}}
                        for index,case in enumerate(CASE_IDS)]
        check.validate(report)
