import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_coverage_language import temporary_directory
from ygo_eval.prompt_audit import audit_corpus
from ygo_data.identity import digest
from test_schemas import validator


class PromptAudit(unittest.TestCase):
    def test_report_is_exclusive_schema_bound_and_cannot_grant_qualification(self):
        with temporary_directory() as directory:
            root=Path(directory); source=root/'source.json';runner=root/'runner.exe'
            source.write_text(json.dumps({'kind':'synthetic_prompt_fixture','request':{},'prompt_audits':[{'sequence':1,'raw':[19,0,1,0,0,0,1],'actual_response_bytes':{'Ok':[[1,0,0,0]]}}]}))
            runner.write_bytes(b'synthetic auditor')
            output=Path(__file__).resolve().parents[1]/'data/runtime/research'/root.name/'audit.json'
            def core(_runner,envelope):
                receipt=envelope['sources'][0].copy()
                audit={'opcode':19,'matches':True,'missing':[],'unexpected':[],'duplicate_count':0,'global_optimality':False,'qualification':'canonical_response_comparison','complete_action_coverage':False,'coverage_gaps':['ordering_equivalence_unproven','protocol_oracle_is_not_engine_semantic_proof']}
                comparison={'status':'matched','audit':audit,'diagnostic':None}
                receipt['frames']=[{'sequence':1,'opcode':19,'raw_sha256':digest(bytes([19,0,1,0,0,0,1])),'current':comparison,'historical':comparison}]
                return {'sources':[receipt],'summary':{'frames':1,'current_mismatches':0,'historical_mismatches':0,'errors':0,'historical_unavailable':0},'successful':True}
            try:
                with patch('ygo_eval.prompt_audit.run_runner',side_effect=core):
                    report=audit_corpus([f'synthetic={source}'],runner,output)
                    check=validator('prompt-corpus-audit.schema.json');check.validate(report)
                    self.assertNotIn(str(root),json.dumps(report))
                    self.assertEqual(report['native_calls'],0)
                    for field in ('global_optimality','complete_action_coverage'):
                        self.assertTrue(list(check.iter_errors({**report,field:True})))
                    self.assertTrue(list(check.iter_errors({**report,'native_calls':1})))
                    original=output.read_bytes()
                    with self.assertRaises(ValueError):audit_corpus([f'synthetic={source}'],runner,output)
                    self.assertEqual(output.read_bytes(),original)
            finally:
                if output.exists():output.unlink()
                if output.parent.exists():output.parent.rmdir()

    def test_source_is_bound_and_changed_input_prevents_publication(self):
        with temporary_directory() as directory:
            root=Path(directory)
            evidence=root/'source.json'; runner=root/'runner.exe'
            original=json.dumps({'kind':'synthetic_prompt_fixture','request':{},'prompt_audits':[{'sequence':1,'opcode':19,'raw':[19,0,1,0,0,0,1],'actual_response_bytes':{'Ok':[[1,0,0,0]]}}]})
            output=Path(__file__).resolve().parents[1]/'data/runtime/research'/root.name/'audit.json'
            for target in (evidence,runner):
                evidence.write_text(original)
                runner.write_bytes(b'synthetic runner')
                def changed(*args):
                    target.write_bytes(b'changed')
                    return {'sources':[], 'summary':{}, 'successful':True}
                with patch('ygo_eval.prompt_audit.run_runner',side_effect=changed):
                    with self.assertRaisesRegex(ValueError,'changed'):
                        audit_corpus([f'synthetic={evidence}'],runner,output)
            self.assertFalse(output.exists())

    def test_bad_sources_and_duplicate_roles_are_rejected_before_runner(self):
        with temporary_directory() as directory:
            root=Path(directory); source=root/'source.json';runner=root/'runner.exe'
            source.write_text('{}');runner.write_bytes(b'x')
            output=Path(__file__).resolve().parents[1]/'data/runtime/research'/root.name/'audit.json'
            with patch('ygo_eval.prompt_audit.run_runner') as call:
                with self.assertRaises(ValueError):audit_corpus([f'a={source}'],runner,output)
                source.write_text(json.dumps({'prompt_audits':[{'sequence':1,'raw':[19,0,1]}]}))
                for entries in [[f'a={source}',f'a={source}'],[f'../bad={source}']]:
                    with self.assertRaises(ValueError):audit_corpus(entries,runner,output)
                call.assert_not_called()
