import unittest
from ygo_eval.terminal_smoke import summarize, validate_baseline

class TerminalSmokeTests(unittest.TestCase):
    def test_success_requires_exact_pair_and_settled_two_calls(self):
        pair={'diagnostic':None,'assets_unchanged':True,'independent_replay_matches':True,'runs':[{'Ok':{'status':'engine_verified','prompt':None,'error':None,'resolved_decisions':[]}}, {'Ok':{'status':'engine_verified','prompt':None,'error':None,'resolved_decisions':[]}}], 'terminal_audits':[{'binding_valid':True,'snapshot_count':1,'utility':1}]*2,'prompt_audits_by_run':[[],[]],'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        stats={'consumed':2,'completed':2,'unknown':0,'reserved':0,'abandoned':0,'limit':2}
        good=summarize('a'*64,pair,stats,[],'b'*64)
        self.assertTrue(good['successful'])
        stats['unknown']=1
        self.assertFalse(summarize('a'*64,pair,stats,[],'b'*64)['successful'])
        pair['runs']=pair['runs'][:1]
        self.assertFalse(summarize('a'*64,pair,stats,[],'b'*64)['successful'])

    def test_unknown_and_failed_summary_contract(self):
        from test_schemas import validator
        check=validator('terminal-smoke.schema.json')
        for stats in [None,{'consumed':1,'completed':1,'unknown':0,'reserved':0,'abandoned':0,'limit':2}]:
            report=summarize('a'*64,None,stats,[] ,None)
            check.validate(report)
            report['proof_ready']=True
            self.assertTrue(list(check.iter_errors(report)))

    def test_wrong_baseline_hash_fails_before_receipt(self):
        from test_coverage_language import temporary_directory
        from pathlib import Path
        with temporary_directory() as name:
            path=Path(name);(path/'acceptance.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'acceptance'):
                validate_baseline(path,path)

    def test_all_three_contract_shapes_and_tamper(self):
        import copy
        from test_schemas import validator
        check=validator('terminal-smoke.schema.json')
        flags={'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        manifest={'schema_version':1,'kind':'terminal_smoke_manifest','case_ids':['terminal-rabbit'],
                  'input_sha256':{'worker':'a'*64},'old_consumed':18,'limit':2,'planned_calls':2,
                  'started_at':1,'runtimes':{},'context':'a'*64,'source_identity':'b'*64,
                  'output_relative':'data/runtime/example/research','baseline_acceptance_sha256':'c'*64,
                  'request_sha256':'d'*64,'catalog_types_sha256':'e'*64,'cdb_sha256':'f'*64,
                  'window_seconds':7200,**flags}
        ledger={'consumed':2,'completed':2,'unknown':0,'reserved':0,'abandoned':0,'limit':2}
        pair={'schema_version':1,'kind':'terminal_smoke_pair','case_id':'terminal-rabbit','request':{},
              'runs':[],'terminal_audits':[],'ledger':ledger,'diagnostic':None,'context':'a'*64,'prompt_audits_by_run':[],'assets_before':None,'assets_after':None,'assets_unchanged':False,'independent_replay_matches':False,'started_at':1,'ledger_sequence':'b'*64,**flags}
        success=summarize('a'*64,{'diagnostic':None,'assets_unchanged':True,
                         'independent_replay_matches':True,'runs':[{'Ok':{'status':'engine_verified','prompt':None,'error':None,'resolved_decisions':[]}}]*2,
                         'terminal_audits':[{'binding_valid':True,'snapshot_count':1,'utility':1}]*2,'prompt_audits_by_run':[[],[]],**flags},ledger,[],'b'*64)
        for report in [manifest,pair,success]:check.validate(report)
        for field,value in [('old_consumed',0),('new_consumed',3),('proof_ready',True),('ledger',{**ledger,'limit':6})]:
            tampered=copy.deepcopy(success);tampered[field]=value
            self.assertTrue(list(check.iter_errors(tampered)),field)
        success['new_consumed']=1
        self.assertTrue(list(check.iter_errors(success)))

    def test_immutable_intent_rejects_changed_request(self):
        from test_coverage_language import temporary_directory
        from pathlib import Path
        from ygo_eval.terminal_regression import immutable_write
        with temporary_directory() as name:
            path=Path(name)/'request.json'
            immutable_write(path,{'request_sha256':'a'*64})
            immutable_write(path,{'request_sha256':'a'*64})
            with self.assertRaises(ValueError):immutable_write(path,{'request_sha256':'b'*64})
    def test_baseline_protected_file_tamper_is_rejected(self):
        import json
        import subprocess
        from unittest.mock import patch
        from pathlib import Path
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_smoke import sha
        with temporary_directory() as name:
            repo=Path(name).absolute();base=repo/'baseline';native=base/'research/native';native.mkdir(parents=True)
            protected=repo/'old-ledger';protected.write_text('old')
            (native/'calls.jsonl').write_text('latest')
            (native/'terminal-rabbit-input.json').write_text('{"request":{}}')
            (base/'before.json').write_text(json.dumps({'protected_files':{'old-ledger':sha(protected)},'blob_files':{}}))
            runner=base/'native-artifacts/terminal-regression.exe';runner.parent.mkdir();runner.write_text('runner')
            (base/'build-native.json').write_text(json.dumps({'identity':'build','artifacts':{'audit':sha(runner)}}))
            a={'native_build_identity':'build','source_identity':'s','cumulative_consumed':18,'unknown':0,'reserved':0,'evidence':{'research/native/terminal-rabbit-input.json':{'sha256':sha(native/'terminal-rabbit-input.json'),'bytes':(native/'terminal-rabbit-input.json').stat().st_size}}}
            (base/'acceptance.json').write_text(json.dumps(a));accepted=sha(base/'acceptance.json')
            (base/'delivery-checkpoint.json').write_text(json.dumps({'acceptance_sha256':accepted,'source_identity':'s'}))
            response=subprocess.CompletedProcess([],0,b'{"ledger":{"consumed":1,"completed":1,"unknown":0,"reserved":0}}')
            with patch('ygo_eval.terminal_smoke.ACCEPTANCE_SHA',accepted),patch('ygo_eval.terminal_smoke.SOURCE_SHA','s'),patch('ygo_eval.terminal_smoke.LEDGER_SHA',sha(native/'calls.jsonl')),patch('ygo_eval.terminal_smoke.subprocess.run',return_value=response) as call:
                validate_baseline(base,repo)
                self.assertIn('--verify-recorded',call.call_args.args[0])
                protected.write_text('changed')
                with self.assertRaisesRegex(ValueError,'protected'):validate_baseline(base,repo)
    def test_forged_pair_qualification_or_prompt_audit_never_succeeds(self):
        import copy
        pair={'diagnostic':None,'assets_unchanged':True,'independent_replay_matches':True,
              'runs':[{'Ok':{'status':'engine_verified','error':None,'prompt':None,'resolved_decisions':[]}}]*2,
              'terminal_audits':[{'binding_valid':True,'snapshot_count':1,'utility':1}]*2,
              'prompt_audits_by_run':[[],[]],'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        stats={'consumed':2,'completed':2,'unknown':0,'reserved':0,'abandoned':0,'limit':2}
        for key,value in [('prompt_audits_by_run',[[{'audit':{'Err':'bad'}}],[]]),('proof_ready',True)]:
            changed=copy.deepcopy(pair);changed[key]=value
            self.assertFalse(summarize('a'*64,changed,stats,[],'b'*64)['successful'])
