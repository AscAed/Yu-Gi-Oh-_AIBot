import copy
import unittest
from ygo_eval.native_prompt_probe import derive_stage_request, summarize

class NativePromptProbeTests(unittest.TestCase):
    def test_unknown_consumption_is_never_reported_zero(self):
        report=summarize('ctx',[],None,'stats_unavailable')
        self.assertIsNone(report['new_consumed'])
        self.assertIsNone(report['cumulative_consumed'])
        self.assertFalse(report['successful'])

    def test_activation_uses_actual_menu_and_resolved_prefix(self):
        parent={'request':{'decisions':[]},'result':{'Ok':{'resolved_decisions':[], 'prompt':{'id':7,'player':0,'opcode':11,'actions':[{'choice':{'kind':'command','command':5,'index':3},'card_ids':[57103969],'bytes':[5,0,3,0]}]}}}}
        request=derive_stage_request(2,parent)
        self.assertEqual(request['decisions'],[{'prompt_id':7,'player':0,'choice':{'kind':'command','command':5,'index':3}}])
        self.assertEqual(parent['request']['decisions'],[])

    def test_branches_derive_from_stage2_and_replays_are_exact(self):
        parent={'request':{'decisions':[{'prompt_id':7,'player':0,'choice':{'kind':'command','command':5,'index':3}}]},'result':{'Ok':{'resolved_decisions':[{'prompt_id':7,'player':0,'choice':{'kind':'command','command':5,'index':3}}], 'prompt':{'id':9,'player':0,'opcode':13,'actions':[{'choice':{'kind':'yes_no','yes':False},'bytes':[0,0,0,0]},{'choice':{'kind':'yes_no','yes':True},'bytes':[1,0,0,0]}]}}}}
        no=derive_stage_request(3,parent);yes=derive_stage_request(5,parent)
        self.assertFalse(no['decisions'][-1]['choice']['yes']);self.assertTrue(yes['decisions'][-1]['choice']['yes'])
        self.assertEqual(derive_stage_request(4,{'request':no}),no)
        self.assertEqual(derive_stage_request(6,{'request':yes}),yes)
        forged=copy.deepcopy(parent);forged['result']['Ok']['prompt']['actions'][1]['bytes']=[0,0,0,0]
        with self.assertRaises(ValueError):derive_stage_request(5,forged)

class StageOrchestrationTests(unittest.TestCase):
    def test_prepare_does_not_invoke_runner_or_create_ledger(self):
        from unittest.mock import patch
        from test_prompt_probe_prepare import temporary_directory
        from ygo_eval.native_prompt_probe import run_stages
        with temporary_directory() as output,patch('subprocess.run',side_effect=AssertionError('no process')):
            result=run_stages(output/'never.exe',output,{'context':'ctx','started_at':int(__import__('time').time())},{'decisions':[]},{},lambda:None,True)
            self.assertTrue(result['prepared'])
            self.assertEqual(result['native_calls'],0)
            self.assertTrue((output/'stage-1-input.json').exists())
            self.assertFalse((output/'stage-2-input.json').exists())
            self.assertFalse((output/'calls.jsonl').exists())

    def test_failed_stage_stops_and_unavailable_stats_remain_unknown(self):
        import json
        import subprocess
        from unittest.mock import patch
        from test_prompt_probe_prepare import temporary_directory
        from ygo_eval.native_prompt_probe import run_stages
        calls=[]
        def run(command,**kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command,2,b'bad',b'')
        with temporary_directory() as output,patch('subprocess.run',side_effect=run):
            result=run_stages(output/'stub.exe',output,{'context':'ctx','started_at':int(__import__('time').time())},{'decisions':[]},{},lambda:None)
            self.assertFalse(result['successful'])
            self.assertIsNone(result['new_consumed'])
            self.assertEqual(len(calls),2)
            self.assertEqual(calls[-1][-1],'--stats')
            self.assertFalse((output/'stage-2-input.json').exists())

    def test_six_stage_order_replays_and_recovery_are_exact(self):
        import json
        import subprocess
        from pathlib import Path
        from unittest.mock import patch
        from test_prompt_probe_prepare import temporary_directory
        from ygo_data.identity import canonical
        from ygo_eval.native_prompt_probe import run_stages
        requests={};calls=[]; frozen_start=int(__import__('time').time())
        def run(command,**kwargs):
            invocation=json.loads(Path(command[1]).read_bytes());stage=invocation['stage'];calls.append((stage,command[-1]))
            request=invocation['request'];requests[stage]=request
            if '--verify-recorded' not in command:
                if stage==1:
                    prompt={'id':17,'player':0,'opcode':11,'actions':[{'choice':{'kind':'command','command':5,'index':2},'card_ids':[57103969],'bytes':[5,0,2,0]}]}
                elif stage==2:
                    prompt={'id':29,'player':0,'opcode':13,'actions':[{'choice':{'kind':'yes_no','yes':yes},'bytes':[int(yes),0,0,0]} for yes in (False,True)]}
                else:prompt={'id':40,'player':0,'opcode':15 if stage in (5,6) else 11,'actions':[]}
                receipt={'stage':stage,'context':invocation['context'],'request':request,'successful':True,'proof_ready':False,'complete_action_coverage':False,'global_optimality':False,'result':{'Ok':{'resolved_decisions':request['decisions'],'prompt':prompt}}}
                Path(invocation['output']).write_bytes(canonical(receipt))
            return subprocess.CompletedProcess(command,0,canonical({'ledger':{'limit':6,'consumed':stage,'completed':stage,'unknown':0,'reserved':0,'abandoned':0}}),b'')
        with temporary_directory() as output,patch('subprocess.run',side_effect=run):
            report=run_stages(output/'stub',output,{'context':'ctx','started_at':frozen_start},{'decisions':[]},{},lambda:None)
            self.assertTrue(report['successful'])
            self.assertEqual([c[0] for c in calls],[1,2,3,4,5,6])
            self.assertEqual(requests[3],requests[4]);self.assertEqual(requests[5],requests[6])
            self.assertFalse(requests[3]['decisions'][-1]['choice']['yes']);self.assertTrue(requests[5]['decisions'][-1]['choice']['yes'])
            calls.clear();recovered=run_stages(output/'stub',output,{'context':'ctx','started_at':frozen_start},{'decisions':[]},{},lambda:None)
            self.assertTrue(recovered['successful'])
            self.assertTrue(all(flag=='--verify-recorded' for _,flag in calls))

    def test_failure_receipt_stops_before_next_stage_and_preserves_diagnostic(self):
        import json
        import subprocess
        from pathlib import Path
        from unittest.mock import patch
        from test_prompt_probe_prepare import temporary_directory
        from ygo_data.identity import canonical
        from ygo_eval.native_prompt_probe import run_stages
        calls=[]
        def run(command,**kwargs):
            calls.append(command)
            invocation=json.loads(Path(command[1]).read_bytes())
            stats={'limit':6,'consumed':1,'completed':1,'unknown':0,'reserved':0,'abandoned':0}
            if '--stats' not in command:
                receipt={'stage':1,'context':'ctx','request':invocation['request'],'successful':False,'diagnostic':'unexpected_pending18','proof_ready':False,'complete_action_coverage':False,'global_optimality':False,'result':{'Ok':{'prompt':{'opcode':18}}}}
                Path(invocation['output']).write_bytes(canonical(receipt))
            return subprocess.CompletedProcess(command,1 if '--stats' not in command else 0,canonical({'ledger':stats}),b'')
        with temporary_directory() as output,patch('subprocess.run',side_effect=run):
            report=run_stages(output/'stub',output,{'context':'ctx','started_at':int(__import__('time').time())},{'decisions':[]},{},lambda:None)
            self.assertFalse(report['successful']);self.assertEqual(report['diagnostic'],'unexpected_pending18');self.assertEqual(report['new_consumed'],1)
            self.assertFalse((output/'stage-2-input.json').exists());self.assertEqual(len(calls),2)

    def test_full_prepare_pipeline_binds_current_build_and_starts_no_runner(self):
        import argparse
        import json
        import time
        from unittest.mock import patch
        from test_prompt_probe_prepare import temporary_directory,SyntheticPipelineTests
        from ygo_data.identity import canonical,digest
        from ygo_eval.prompt_probe_logic import derive_candidates
        import ygo_eval.native_prompt_probe as module
        with temporary_directory() as repo:
            source_args,pins=SyntheticPipelineTests().fixture(repo)
            frozen=json.loads(source_args.cases.read_bytes());base=frozen['cases'][0]
            base['request']['protocol_version']=2;base['request']['probe_only']=False
            source_args.cases.write_bytes(canonical(frozen))
            candidate=derive_candidates(base['case'])[0]
            preparation=source_args.baseline_dir/'research-final';preparation.mkdir()
            (preparation/'prepared-cases.json').write_text('{}')
            runner=repo/'stub.exe';runner.write_bytes(b'not executable')
            worker=repo/'worker.exe';worker.write_bytes(b'not executable either')
            source={'identity':'a'*64,'files':{}}
            build={'kind':'build_record','status':'recorded','source_before':source,'source_after':source,'artifacts':{'runner':module.sha(runner),'worker':module.sha(worker),'cli':'c'*64}}
            build['identity']=digest(canonical(build));build_path=repo/'build.json';build_path.write_bytes(canonical(build))
            runtime={'roles':{'worker':{'sha256':module.sha(worker)},'dll':{'sha256':base['case']['assets']['engine_sha256']},'cdb':{'sha256':base['case']['assets']['cdb_sha256']},'script_manifest':{'sha256':base['case']['assets']['scripts_sha256']}}}
            identity={'kind':'workspace_identity','source':source,'consistent':True,'cli_sha256':'c'*64,'runtimes':{'ordinary':runtime}}
            identity['identity']=digest(canonical(identity));identity_path=repo/'identity.json';identity_path.write_bytes(canonical(identity))
            window=repo/'window.json';window.write_bytes(canonical({'schema_version':1,'scope':module.SCOPE,'started_at':int(time.time()),'limit':6,'wall_seconds':7200}))
            args=argparse.Namespace(preparation=preparation,cases=source_args.cases,baseline_dir=source_args.baseline_dir,runner=runner,worker=worker,build_record=build_path,identity=identity_path,window_start=window,output=repo/'data/runtime/p1-tenki-probe-native-2026-10-21/research',prepare_only=True)
            static=repo/'data/tmp/ocgcore-source/libduel.cpp';static.parent.mkdir(parents=True);static.write_bytes(b'frozen core')
            with patch.object(module,'CASES_SHA',module.sha(args.cases)),patch.object(module,'validate_baseline',return_value=(candidate,{static:module.sha(static)})),patch.object(module,'stable_source',return_value=source),patch('subprocess.run',side_effect=AssertionError('no runner')):
                report=module.native_prompt_probe(args,repo)
            self.assertTrue(report['prepared']);self.assertFalse((args.output/'calls.jsonl').exists())
            invocation=json.loads((args.output/'stage-1-input.json').read_bytes())
            self.assertEqual(invocation['expected_identity'],runtime)
            self.assertEqual(invocation['request']['deck']['main'][0],57103969)
            self.assertEqual(invocation['request']['decisions'],[])
            self.assertNotIn('research_capture',invocation['request'])
            self.assertFalse(invocation['request']['probe_only'])
            import jsonschema
            from pathlib import Path
            schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/native-prompt-probe.schema.json').read_bytes())
            validator=jsonschema.Draft202012Validator(schema)
            validator.validate(report)
            validator.validate(json.loads((args.output/'manifest.json').read_bytes()))

    def test_schema_rejects_success_without_six_settled_calls(self):
        import copy
        import json
        from pathlib import Path
        import jsonschema
        from ygo_eval.native_prompt_probe import summarize
        stages=[{'stage':n,'successful':True,'receipt_sha256':'a'*64} for n in range(1,7)]
        report=summarize('a'*64,stages,{'limit':6,'consumed':6,'completed':6,'unknown':0,'reserved':0,'abandoned':0})
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/native-prompt-probe.schema.json').read_bytes())
        validator=jsonschema.Draft202012Validator(schema);validator.validate(report)
        for mutate in (lambda r:r.update(new_consumed=None),lambda r:r['ledger'].update(unknown=1),lambda r:r['stages'].pop(),lambda r:r.update(proof_ready=True),lambda r:r['stages'][0].update(stage=2),lambda r:r.update(ledger={})):
            forged=copy.deepcopy(report);mutate(forged)
            with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)

    def test_stage_schema_preserves_failed_raw_result_and_rejects_forged_success(self):
        import copy
        import json
        from pathlib import Path
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/native-prompt-probe.schema.json').read_bytes());validator=jsonschema.Draft202012Validator(schema)
        stage={'schema_version':1,'kind':'tenki_prompt_probe_stage','scope':'tenki-prompt-probe-v1','stage':2,'context':'a'*64,'request':{},'result':{'Ok':{'events':[{'opcode':18,'raw':[18,0,1,0]}]}},'validation':{'Err':'unexpected opcode18'},'assets_before':{},'assets_after':{},'assets_unchanged':True,'independent_replay_matches':None,'successful':False,'diagnostic':'unexpected_intermediate_prompt','ledger':{'limit':6,'consumed':2,'completed':2,'unknown':0,'reserved':0,'abandoned':0},'started_at':1,'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        validator.validate(stage)
        for mutate in (lambda r:r.update(successful=True),lambda r:r.update(ledger={}),lambda r:r['ledger'].update(completed=1),lambda r:r.update(proof_ready=True)):
            forged=copy.deepcopy(stage);mutate(forged)
            with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)

    def test_expired_new_call_stops_before_runner_and_reports_known_empty_ledger(self):
        from unittest.mock import patch
        from test_prompt_probe_prepare import temporary_directory
        from ygo_eval.native_prompt_probe import run_stages
        with temporary_directory() as output,patch('subprocess.run',side_effect=AssertionError('expired new call forbidden')):
            report=run_stages(output/'stub',output,{'context':'ctx','started_at':1},{'decisions':[]},{},lambda:None)
            self.assertFalse(report['successful']);self.assertEqual(report['new_consumed'],0)
            self.assertEqual(report['diagnostic'],'window_exhausted_before_new_call')
            self.assertFalse((output/'calls.jsonl').exists())

class StaticSourceGuardTests(unittest.TestCase):
    def test_libduel_is_bound_and_old_tool_sources_are_not_rebound(self):
        from test_prompt_probe_prepare import temporary_directory
        from ygo_eval.native_prompt_probe import validate_static_sources,sha
        with temporary_directory() as repo:
            path=repo/'data/tmp/ocgcore-source/libduel.cpp';path.parent.mkdir(parents=True);path.write_text('frozen core')
            protected={};report={'input_sha256':{'core/libduel.cpp':sha(path),'tool/python/ygo_eval/research.py':'0'*64}}
            validate_static_sources(report,repo,protected)
            self.assertEqual(protected[path],sha(path))
            path.write_text('tampered')
            with self.assertRaises(ValueError):validate_static_sources(report,repo,{})

    def test_empty_success_stage_rejected(self):
        import json
        from pathlib import Path
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/native-prompt-probe.schema.json').read_bytes())
        stage={'schema_version':1,'kind':'tenki_prompt_probe_stage','scope':'tenki-prompt-probe-v1','stage':2,'context':'a'*64,'request':{},'result':{'Ok':{}},'validation':{'Ok':{}},'assets_before':{},'assets_after':{},'assets_unchanged':True,'independent_replay_matches':None,'successful':True,'diagnostic':None,'ledger':{'limit':6,'consumed':2,'completed':2,'unknown':0,'reserved':0,'abandoned':0},'started_at':1,'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
        with self.assertRaises(jsonschema.ValidationError):jsonschema.Draft202012Validator(schema).validate(stage)

    def test_complete_success_stage_schema_accepts_then_rejects_missing_details(self):
        import copy
        import json
        from pathlib import Path
        import jsonschema
        from test_prompt_probe_prepare import temporary_directory,SyntheticPipelineTests
        validator=jsonschema.Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'schemas/native-prompt-probe.schema.json').read_bytes()))
        with temporary_directory() as repo:
            args,_=SyntheticPipelineTests().fixture(repo)
            request=json.loads(args.cases.read_bytes())['cases'][0]['request'];request.update(protocol_version=2,probe_only=False)
            # Keep the legacy empty labels from the frozen request: content
            # identity is carried by the bound hashes, not these labels.
            request['versions'].update(catalog='',banlist='',core_commit='synthetic',initializer='synthetic')
            identity={'schema_version':1,'kind':'engine_identity','identity':'a'*64,'consistent':True,'timeout_ms':30000,'roles':{role:{'status':'present','sha256':'a'*64} for role in ('worker','dll','cdb','script_manifest','engine_manifest')},'scripts':{'root_present':True,'actual':{},'missing':[],'extra':[],'mismatch':[]}}
            result={'protocol_version':2,'status':'decision_required','events':[{'sequence':1,'opcode':13,'raw':[13,0],'supported':True,'fields':{}}],'prompt':{'id':1,'player':0,'opcode':13,'actions':[{}]},'checkpoint':{'turn':1,'turn_player':0,'phase':4,'lp':[8000,8000],'cards':[]},'error':None,'versions':request['versions'],'loaded_scripts':{},'steps':[],'resolved_decisions':[],'coverage_gaps':[],'peak_working_set_bytes':None}
            stage={'schema_version':1,'kind':'tenki_prompt_probe_stage','scope':'tenki-prompt-probe-v1','stage':2,'context':'a'*64,'request':request,'result':{'Ok':result},'validation':{'Ok':{'pending_opcode':13,'raw_prompt_count':1,'response_oracle_matches':True,'expected_target_matches':True,'automatic_decisions_single_legal':True}},'assets_before':identity,'assets_after':identity,'assets_unchanged':True,'independent_replay_matches':None,'successful':True,'diagnostic':None,'ledger':{'limit':6,'consumed':2,'completed':2,'unknown':0,'reserved':0,'abandoned':0},'started_at':1,'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
            validator.validate(stage)
            for catalog, banlist in (('', ''), ('catalog-v1', ''), ('', 'banlist-v1'), ('catalog-v1', 'banlist-v1')):
                compatible = copy.deepcopy(stage)
                compatible['request']['versions'].update(catalog=catalog, banlist=banlist)
                compatible['result']['Ok']['versions'].update(catalog=catalog, banlist=banlist)
                validator.validate(compatible)
            for mutate in (lambda r:r['result']['Ok'].pop('checkpoint'),lambda r:r['result']['Ok']['prompt'].update(opcode=18),lambda r:r['validation']['Ok'].update(response_oracle_matches=False),lambda r:r['assets_before'].update(consistent=False),lambda r:r.update(request={})):
                forged=copy.deepcopy(stage);mutate(forged)
                with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)

            for field in ('catalog', 'banlist'):
                for invalid in (None, 3, []):
                    forged=copy.deepcopy(stage)
                    forged['request']['versions'][field]=invalid
                    with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)
                forged=copy.deepcopy(stage)
                forged['request']['versions'].pop(field)
                with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)
            for location in ('request', 'result'):
                forged=copy.deepcopy(stage)
                versions=forged[location]['versions'] if location == 'request' else forged['result']['Ok']['versions']
                versions['engine_sha256']='not-a-hash'
                with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)
            for forged_stage in (1, 6):
                forged=copy.deepcopy(stage)
                forged['stage']=forged_stage
                with self.assertRaises(jsonschema.ValidationError):validator.validate(forged)
