import unittest
from ygo_eval.terminal_followup import pair_diagnostic, summarize

class TerminalFollowupTests(unittest.TestCase):
    def pair(self):
        return {'diagnostic':None,'assets_unchanged':True,'independent_replay_matches':True,'runs':[{'Ok':{'status':'engine_verified','error':None,'prompt':None,'resolved_decisions':[]}}]*2,'terminal_audits':[{'binding_valid':True,'snapshot_count':0,'utility':0}]*2,'prompt_audits_by_run':[[],[]],'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
    def test_zero_requires_complete_pair(self):
        p=self.pair();self.assertIsNone(pair_diagnostic(p,[]))
        p['terminal_audits'][0]={'binding_valid':False,'snapshot_count':None,'utility':None}
        self.assertIsNotNone(pair_diagnostic(p,[]))
    def test_prefix_receipt_not_compared_with_latest_aggregate(self):
        p=self.pair();p['ledger']={'consumed':2}
        stats={'consumed':4,'completed':4,'unknown':0,'reserved':0,'abandoned':0,'limit':4}
        rows=[{'case_id':'terminal-tournament','successful':True,'evidence_sha256':'a'*64},{'case_id':'terminal-shuffle-end','successful':True,'evidence_sha256':'b'*64}]
        self.assertTrue(summarize('a'*64,rows,stats,None)['successful'])
        self.assertEqual(p['ledger']['consumed'],2)
    def test_unknown_consumption_is_not_zero(self):
        r=summarize('a'*64,[],None,'runner_failed');self.assertIsNone(r['new_consumed']);self.assertFalse(r['successful'])

    def test_contract_success_failure_partial_unknown_and_tamper(self):
        import copy
        from test_schemas import validator
        check=validator('terminal-followup.schema.json')
        flags={'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        stats={'consumed':4,'completed':4,'unknown':0,'reserved':0,'abandoned':0,'limit':4}
        rows=[{'case_id':k,'successful':True,'diagnostic':None,'evidence_sha256':'a'*64} for k in ['terminal-tournament','terminal-shuffle-end']]
        good=summarize('b'*64,rows,stats,None);check.validate(good)
        for n in [0,1,2,3]:
            current={**stats,'consumed':n,'completed':n}
            check.validate(summarize('b'*64,rows[:1],current,'incomplete'))
        check.validate(summarize('b'*64,[],None,'unavailable'))
        for key,value in [('new_consumed',3),('proof_ready',True),('old_consumed',18)]:
            bad=copy.deepcopy(good);bad[key]=value;self.assertTrue(list(check.iter_errors(bad)))
        manifest={'schema_version':1,'kind':'terminal_followup_manifest','case_ids':['terminal-tournament','terminal-shuffle-end'],'source_identity':'a'*64,'output_relative':'data/runtime/example/research','input_sha256':{'worker':'a'*64},'baseline_acceptance_sha256':'a'*64,'old_consumed':20,'limit':4,'planned_calls':4,'window_seconds':7200,'started_at':1,'runtimes':{},'context':'b'*64,'bindings':{k:{n:'a'*64 for n in ['request_sha256','cdb_sha256','catalog_types_sha256']} for k in ['terminal-tournament','terminal-shuffle-end']},'parent':{'evidence_sha256':'a'*64,'public_prompt_sha256':'b'*64},**flags}
        check.validate(manifest)
        pair={'schema_version':1,'kind':'terminal_followup_pair','case_id':'terminal-tournament','request':{},'runs':[],'terminal_audits':[],'ledger':{**stats,'consumed':2,'completed':2},'diagnostic':'failed','context':'b'*64,'prompt_audits_by_run':[],'assets_before':None,'assets_after':None,'assets_unchanged':False,'independent_replay_matches':False,'started_at':1,'ledger_sequence':'a'*64,**flags}
        check.validate(pair)

    def test_mutated_or_missing_actual_audit_refuses_pair(self):
        import copy
        for field,value in [('runs',[]),('prompt_audits_by_run',[[{'audit':{'Ok':{'matches':False}}}],[]]),('assets_unchanged',False),('proof_ready',True)]:
            p=copy.deepcopy(self.pair());p[field]=value;self.assertIsNotNone(pair_diagnostic(p,[]))

    def test_wrong_case_order_is_not_successful(self):
        rows=[{'case_id':'terminal-shuffle-end','successful':True},{'case_id':'terminal-tournament','successful':True}]
        stats={'consumed':4,'completed':4,'unknown':0,'reserved':0,'abandoned':0,'limit':4}
        self.assertFalse(summarize('a'*64,rows,stats,None)['successful'])

    def test_first_pair_failure_blocks_second_runner_and_preserves_stats(self):
        import json
        import subprocess
        from pathlib import Path
        from unittest.mock import patch
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_followup import execute_pairs, CASE_IDS
        with temporary_directory() as directory:
            output=Path(directory);calls=[]
            templates={k:{'decisions':[]} for k in CASE_IDS}
            inputs={k:(output/(k+'-input.json'),'a'*64) for k in CASE_IDS}
            stats={'consumed':1,'completed':1,'unknown':0,'reserved':0,'abandoned':0,'limit':4}
            pair={**self.pair(),'case_id':CASE_IDS[0],'context':'a'*64,'request':templates[CASE_IDS[0]],'diagnostic':'query_failed'}
            def run(command,**kwargs):
                calls.append(command)
                (output/(CASE_IDS[0]+'.json')).write_text(json.dumps(pair))
                return subprocess.CompletedProcess(command,1,json.dumps({'ledger':stats}).encode(),b'')
            with patch('ygo_eval.terminal_followup.subprocess.run',side_effect=run):
                pairs,current,diagnostic=execute_pairs(inputs,templates,Path('runner'),output,'a'*64,lambda:None)
            self.assertEqual(len(calls),1);self.assertEqual(len(pairs),1)
            self.assertEqual(current['consumed'],1);self.assertEqual(diagnostic,'query_failed')

    def test_wrong_order_refused_before_runner(self):
        from unittest.mock import patch
        from pathlib import Path
        from ygo_eval.terminal_followup import execute_pairs, CASE_IDS
        wrong={k:(Path(k),'a'*64) for k in reversed(CASE_IDS)}
        with patch('ygo_eval.terminal_followup.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'order'):
                execute_pairs(wrong,{},Path('runner'),Path('.'),'a'*64,lambda:None)
            run.assert_not_called()

    def test_runtime_asset_swap_refused(self):
        from ygo_eval.terminal_followup import validate_runtime
        runtime={'roles':{'worker':{'sha256':'worker'},'dll':{'sha256':'engine'},'cdb':{'sha256':'ordinary'},'script_manifest':{'sha256':'scripts'}}}
        request={'versions':{'engine_sha256':'engine','cdb_sha256':'tournament','scripts_sha256':'scripts'}}
        with self.assertRaisesRegex(ValueError,'asset'):
            validate_runtime(runtime,request,'worker')

    def test_parent_public_menu_tampering_is_rejected(self):
        import copy
        from ygo_eval.terminal_regression import derive_request
        prompt={'id':9,'player':0,'opcode':11,'actions':[{'choice':{'kind':'command','command':7,'index':0},'bytes':[7,0,0,0]}]}
        original={'prompt':prompt,'events':[{'sequence':9,'opcode':11,'raw':[11,0]+[0]*24+[0,1,0],'fields':{'prompt':copy.deepcopy(prompt)}}]}
        self.assertEqual(derive_request({'decisions':[]},original,7)['decisions'][0]['prompt_id'],9)
        for mutation in ['prompt','choice','bytes','raw']:
            value=copy.deepcopy(original)
            if mutation=='prompt': value['prompt']['id']=10
            if mutation=='choice': value['prompt']['actions'][0]['choice']['index']=1
            if mutation=='bytes': value['prompt']['actions'][0]['bytes']=[8,0,0,0]
            if mutation=='raw': value['events'][0]['raw'][-2]=0
            with self.assertRaises(ValueError):derive_request({'decisions':[]},value,7)

    def test_old9_missing_original_runner_fails_closed_before_subprocess(self):
        from pathlib import Path
        from unittest.mock import patch
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_followup import verify_original_runner
        with temporary_directory() as directory:
            with patch('ygo_eval.terminal_followup.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,'old9_runner_unavailable'):
                    verify_original_runner({'status':'recorded','artifacts':{'audit':'a'*64}},[Path(directory)/'missing.exe'],'a'*64)
                run.assert_not_called()

    def test_partial_status_never_passes_replay_gate(self):
        p=self.pair();p['runs'][0]['Ok']['status']='partial'
        self.assertIsNotNone(pair_diagnostic(p,[]))

    def test_historical_audit_argument_is_required(self):
        import argparse
        from ygo_eval.terminal_followup import add_arguments
        parser=argparse.ArgumentParser()
        add_arguments(parser)
        supplied=[]
        for name in ['cases','baseline-dir','parent-input','parent-evidence','parent-runner','runner','worker','build-record','identity','window-start','output']:
            supplied += ['--'+name, 'unused']
        with self.assertRaises(SystemExit):parser.parse_args(supplied)

    def test_historical_audit_recomputed_before_acceptance(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_followup import validate_history_report
        report={'valid':True,'native_calls':0,'input_sha256':{},'anchor':{'acceptance_sha256':'a'*64}}
        with temporary_directory() as directory:
            repo=Path(directory);path=repo/'audit.json';path.write_text(json.dumps(report))
            with patch('ygo_eval.history_audit.audit_history',return_value=report) as audit:
                protected=validate_history_report(path,repo)
                audit.assert_called_once_with(repo/'data/runtime/p1-terminal-followup-2026-10-20',repo=repo)
                self.assertIn(path,protected)

    def test_forged_success_cannot_replace_fresh_audit(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_followup import validate_history_report
        with temporary_directory() as directory:
            repo=Path(directory);path=repo/'audit.json';path.write_text(json.dumps({'valid':True,'native_calls':0}))
            with patch('ygo_eval.history_audit.audit_history',return_value={'valid':False,'native_calls':0}),patch('ygo_eval.terminal_followup.subprocess.run') as runner:
                with self.assertRaisesRegex(ValueError,'historical audit'):
                    validate_history_report(path,repo)
                runner.assert_not_called()

    def test_history_input_changed_during_recomputation_is_rejected(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_followup import validate_history_report
        report={'valid':True,'native_calls':0,'input_sha256':{}}
        with temporary_directory() as directory:
            repo=Path(directory);path=repo/'audit.json';path.write_text(json.dumps(report))
            def changed(*args,**kwargs):
                path.write_text(json.dumps({**report,'tampered':True}));return report
            with patch('ygo_eval.history_audit.audit_history',side_effect=changed),patch('ygo_eval.terminal_followup.subprocess.run') as runner:
                with self.assertRaisesRegex(ValueError,'historical audit'):
                    validate_history_report(path,repo)
                runner.assert_not_called()

    def test_frozen_source_change_refuses_before_writer_or_runner(self):
        from pathlib import Path
        from unittest.mock import patch
        from ygo_eval.terminal_followup import verify_frozen_inputs
        with patch('ygo_eval.terminal_followup.stable_source',return_value={'identity':'changed'}),patch('ygo_eval.terminal_followup.immutable_write') as writer,patch('ygo_eval.terminal_followup.subprocess.run') as runner:
            with self.assertRaisesRegex(ValueError,'frozen input'):
                verify_frozen_inputs(Path('.'),{'identity':'frozen'},{},{},{},Path('audit'))
            writer.assert_not_called();runner.assert_not_called()

    def test_duplicate_keys_in_saved_history_audit_are_rejected(self):
        import sys
        from types import SimpleNamespace
        from pathlib import Path
        from unittest.mock import patch
        from test_coverage_language import temporary_directory
        from ygo_eval.terminal_followup import validate_history_report
        with temporary_directory() as directory:
            repo=Path(directory);path=repo/'audit.json'
            path.write_text('{"valid":false,"valid":true,"native_calls":0,"input_sha256":{}}')
            auditor=SimpleNamespace(audit_history=lambda *a,**kw:{'valid':True,'native_calls':0,'input_sha256':{}})
            with patch.dict(sys.modules,{'ygo_eval.history_audit':auditor}):
                with self.assertRaisesRegex(ValueError,'historical audit'):
                    validate_history_report(path,repo)
