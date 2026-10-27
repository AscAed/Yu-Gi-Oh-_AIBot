import argparse
import uuid
import shutil
from contextlib import contextmanager

@contextmanager
def temporary_directory():
    root = Path(__file__).resolve().parents[1]/"data/runtime"/str(uuid.uuid4())
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)
from pathlib import Path
import unittest
from unittest.mock import patch

from ygo_eval.prompt_probe_prepare import prepare_prompt_probes, strict_json


class PromptPreparationTests(unittest.TestCase):
    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError):
            strict_json('{"x":1,"x":2}')

    def test_failure_report_is_saved_without_processes(self):
        with temporary_directory() as temporary:
            repo = Path(temporary)
            (repo/'.gitignore').write_text('/data/runtime/\n')
            args = argparse.Namespace(cases=repo/'missing.json', baseline_dir=repo/'baseline', core_source=repo/'core', output=repo/'data/runtime/p1-prompt-probes-offline-2026-10-21/research')
            with patch('subprocess.Popen', side_effect=AssertionError('process forbidden')):
                report = prepare_prompt_probes(args, repo=repo)
            self.assertFalse(report['preparation_successful'])
            self.assertEqual(report['native_calls'], 0)
            self.assertTrue((args.output/'report.json').is_file())
            with self.assertRaises(ValueError):
                prepare_prompt_probes(args, repo=repo)

    def test_outside_output_refused(self):
        with temporary_directory() as temporary:
            repo = Path(temporary)
            args = argparse.Namespace(output=repo/'outside')
            with self.assertRaises(ValueError):
                prepare_prompt_probes(args, repo=repo)

class SyntheticPipelineTests(unittest.TestCase):
    def fixture(self, repo):
        import copy
        import json
        import sqlite3
        from contextlib import closing
        from test_prompt_probe_logic import base
        from ygo_eval.prompt_probe_prepare import digest, encode, FLAGS, TOOL_FILES
        case = base(); case["case_id"] = "rabbit"
        for name in TOOL_FILES:
            path=repo/name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('/data/runtime/\n' if name == '.gitignore' else '{}')
        runtime=repo/'runtime';runtime.mkdir()
        scripts=runtime/'scripts';scripts.mkdir()
        scriptpins={}
        for name in ('utility.lua','official/c57103969.lua','official/c58074572.lua','official/c90502999.lua'):
            path=scripts/name;path.parent.mkdir(exist_ok=True);path.write_bytes(b'-- synthetic\n')
            scriptpins[name]=digest(path.read_bytes())
        manifest=runtime/'scripts.json';manifest.write_bytes(encode(scriptpins))
        engine=runtime/'core.dll';engine.write_bytes(b'not executable')
        engine_manifest=runtime/'engine.json';engine_manifest.write_text('{}')
        banlist=runtime/'banlist.json';banlist.write_bytes(encode({'region':'OCG','version':case['rules']['version'],'limits':{}}))
        catalog=runtime/'cards.cdb'
        with closing(sqlite3.connect(catalog)) as db:
            db.execute('CREATE TABLE datas (id INTEGER,alias INTEGER,type INTEGER,ot INTEGER,race INTEGER,level INTEGER)')
            codes=set(case['deck']['main']+case['deck']['extra']+[57103969,58074572,90502999])
            for code in codes:
                db.execute('INSERT INTO datas VALUES (?,?,?,?,?,?)',(code,0,0x2000 if code in case['deck']['extra'] else 1,1,32768,4))
            db.commit()
        case['assets']={'engine_sha256':digest(engine.read_bytes()),'cdb_sha256':digest(catalog.read_bytes()),'scripts_sha256':digest(manifest.read_bytes())}
        case['rules']['banlist_sha256']=digest(banlist.read_bytes())
        request={'engine':{'worker_path':str(runtime/'never-run.exe'),'ocgcore_path':str(engine),'catalog_path':str(catalog),'scripts_path':str(scripts),'script_manifest_path':str(manifest),'engine_manifest_path':str(engine_manifest),'timeout_ms':30000},'versions':{'rules':'ocg-mr5',**case['assets']},'deck':copy.deepcopy(case['deck']),'opening_hand':copy.deepcopy(case['opening_hand']),'seed':1,'decisions':[]}
        cases=repo/'cases.json';cases.write_bytes(encode({'cases':[{'case':case,'request':request,'banlist_path':str(banlist)}]}))
        baseline=repo/'baseline';baseline.mkdir()
        acceptance={'kind':'shuffle_route_offline_delivery_acceptance','source_identity':'42372235b2ab0453db078a5d06ee0fdd5c979271ba60663d2327b0bd04ec9598','source_files':374,'paused':True,'tools_verified':True,'route_observation_verified':True,'cumulative_consumed':24,'unknown':0,'evidence':{},**FLAGS}
        (baseline/'acceptance.json').write_bytes(encode(acceptance))
        core=repo/'core';core.mkdir()
        return argparse.Namespace(cases=cases,baseline_dir=baseline,core_source=core,output=repo/'data/runtime/p1-prompt-probes-offline-2026-10-21/research'),dict(ACCEPTANCE_SHA=digest((baseline/'acceptance.json').read_bytes()),CASES_SHA=digest(cases.read_bytes()),SCRIPT_PINS=scriptpins,CORE_PINS={},REPO_PINS={})

    def test_complete_pipeline_never_starts_process_and_saves_no_request(self):
        import json
        from unittest.mock import patch
        import ygo_eval.prompt_probe_prepare as module
        with temporary_directory() as repo:
            args,pins=self.fixture(repo)
            with patch.multiple(module,**pins), patch('subprocess.Popen',side_effect=AssertionError('process forbidden')):
                report=module.prepare_prompt_probes(args,repo)
            self.assertTrue(report['preparation_successful'],report['diagnostics'])
            self.assertEqual(len(report['candidates']),3)
            prepared=json.loads((args.output/'prepared-cases.json').read_bytes())
            self.assertFalse(prepared['execution_ready'])
            raw=(args.output/'report.json').read_text()
            self.assertNotIn(str(repo),raw)
            self.assertNotIn('worker_path',(args.output/'prepared-cases.json').read_text())
            self.assertEqual(report['command6']['direct_symbol_scan']['hits'],[])
            self.assertFalse((args.output/'journal.jsonl').exists())

    def test_input_drift_revokes_all_prepared_candidates(self):
        import ygo_eval.prompt_probe_prepare as module
        from ygo_eval.research import validate_sources
        with temporary_directory() as repo:
            args,pins=self.fixture(repo)
            calls=[]
            def mutate(case,request,banlist):
                validate_sources(case,request,banlist)
                calls.append(case)
                if len(calls)==4:
                    args.cases.write_bytes(args.cases.read_bytes()+b' ')
            with patch.multiple(module,**pins), patch('ygo_eval.research.validate_sources',side_effect=mutate), patch('subprocess.Popen',side_effect=AssertionError('process forbidden')):
                report=module.prepare_prompt_probes(args,repo)
            self.assertFalse(report['preparation_successful'])
            self.assertFalse(report['source_unchanged'])
            self.assertEqual(report['candidates'],[])
            self.assertEqual(report['diagnostics'],['input_changed_during_preparation'])


    def test_ordinary_failure_preserves_validated_prefix(self):
        import ygo_eval.prompt_probe_prepare as module
        from ygo_eval.research import validate_sources
        with temporary_directory() as repo:
            args,pins=self.fixture(repo); calls=[]
            def fail_third(case,request,banlist):
                calls.append(case)
                if len(calls)==3:
                    raise ValueError('synthetic_second_candidate_failure')
                validate_sources(case,request,banlist)
            with patch.multiple(module,**pins), patch('ygo_eval.research.validate_sources',side_effect=fail_third):
                report=module.prepare_prompt_probes(args,repo)
            self.assertFalse(report['preparation_successful'])
            self.assertEqual(len(report['candidates']),1)

    def test_directory_addition_during_scan_revokes_preparation(self):
        import ygo_eval.prompt_probe_prepare as module
        from ygo_eval.research import validate_sources
        with temporary_directory() as repo:
            args,pins=self.fixture(repo); calls=[]
            def add(case,request,banlist):
                validate_sources(case,request,banlist);calls.append(case)
                if len(calls)==2:
                    (Path(request['engine']['scripts_path'])/'added.lua').write_text('-- late')
            with patch.multiple(module,**pins), patch('ygo_eval.research.validate_sources',side_effect=add):
                report=module.prepare_prompt_probes(args,repo)
            self.assertFalse(report['preparation_successful'])
            self.assertEqual(report['candidates'],[])
            self.assertEqual(report['diagnostics'],['source_directory_changed'])

    def test_report_schema_rejects_qualified_candidate_and_missing_bindings(self):
        import copy
        import json
        import jsonschema
        import ygo_eval.prompt_probe_prepare as module
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/prompt-probe-preparation.schema.json').read_bytes())
        with temporary_directory() as repo:
            args,pins=self.fixture(repo)
            with patch.multiple(module,**pins):
                report=module.prepare_prompt_probes(args,repo)
            jsonschema.Draft202012Validator(schema).validate(report)
            prepared_schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/prepared-prompt-cases.schema.json').read_bytes())
            prepared=json.loads((args.output/'prepared-cases.json').read_bytes())
            jsonschema.Draft202012Validator(prepared_schema).validate(prepared)
            forged=copy.deepcopy(prepared); forged['candidates'][0]['case']['seed']=True
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(prepared_schema).validate(forged)
            for key in module.FLAGS:
                forged=copy.deepcopy(report);forged['candidates'][0][key]=True
                with self.subTest(key=key),self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(schema).validate(forged)
            for key in ('tenki_target','static_api_mapping','followup_dependencies'):
                forged=copy.deepcopy(report);del forged[key]
                with self.subTest(key=key),self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(schema).validate(forged)

    def test_ignore_negation_and_nested_ignore_refused_before_output(self):
        import ygo_eval.prompt_probe_prepare as module
        for nested in (False,True):
            with self.subTest(nested=nested),temporary_directory() as repo:
                args,pins=self.fixture(repo)
                if nested:
                    (repo/'data').mkdir()
                    (repo/'data/.gitignore').write_text('!runtime/\n')
                else:
                    (repo/'.gitignore').write_text('/data/runtime/\n!data/runtime/**\n')
                with patch.multiple(module,**pins),self.assertRaises(ValueError):
                    module.prepare_prompt_probes(args,repo)
                self.assertFalse(args.output.exists())
