import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ygo_eval.history_audit import strict_json, verify_ledger, audit_history


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def hashed(value):
    return hashlib.sha256(value).hexdigest()


def records(entries):
    out=[]; previous=''
    for index,entry in enumerate(entries):
        current=hashed(wire([index,previous,entry]))
        out.append({'sequence':index,'previous':previous,'entry':entry,'hash':current})
        previous=current
    return b''.join(wire(row)+b'\n' for row in out)


class HistoryAuditTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_keys_and_nonfinite(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}']:
            with self.assertRaises(ValueError):strict_json(raw)

    def test_header_chain_uses_literal_frozen_wire(self):
        entry={'kind':'header','version':1,'scope':'research-first-batch-v1','context':'ctx','limit':4096}
        raw=b'{"sequence":0,"previous":"","entry":{"kind":"header","version":1,"scope":"research-first-batch-v1","context":"ctx","limit":4096},"hash":"12c7fb1aaf973d2887250b0dfe04bbe96563db8a2ad26a880ad8e19743ff46f9"}\n'
        # This literal fixture is independent of the test's record builder.
        self.assertEqual(verify_ledger(raw,lambda *_:b'',{},expected_calls=0)['stats']['consumed'],0)
        bad=bytearray(raw);bad[bad.index(b'4096')]=ord('3')
        with self.assertRaises(ValueError):verify_ledger(bytes(bad),lambda *_:b'',{},expected_calls=0)

    def test_unsupported_or_torn_ledger_is_not_repaired(self):
        header={'kind':'header','version':1,'scope':'research-first-batch-v1','context':'ctx','limit':4096}
        for raw in [records([header])[:-1],records([header,{'kind':'reserve','token':'x','amount':1}]),records([header,header])]:
            with self.assertRaises(ValueError):verify_ledger(raw,lambda *_:b'',{},expected_calls=0)

    def test_live_audit_starts_no_process_and_does_not_change_inputs(self):
        repo=Path(__file__).resolve().parents[1]
        baseline=repo/'data/runtime/p1-terminal-followup-2026-10-20'
        if not baseline.exists():self.skipTest('local pinned history unavailable')
        ledger=repo/'data/runtime/baseline-2026-10-19/research/calls.jsonl'
        before=ledger.read_bytes()
        with patch('subprocess.run',side_effect=AssertionError('process must not start')):
            report=audit_history(baseline,repo)
        self.assertTrue(report['valid'],report['diagnostics'])
        self.assertEqual(report['stats']['consumed'],9)
        self.assertEqual(report['stats']['completed'],9)
        self.assertEqual(report['native_calls'],0)
        self.assertEqual(report['unpaired_call_ids'],[7])
        self.assertFalse(report['original_runner_available'])
        self.assertEqual(ledger.read_bytes(),before)

    def fixture(self):
        # Test-owned frozen structs and codec; no production enumeration or hash helpers.
        request={'protocol_version':2,'engine':{'worker_path':'w','ocgcore_path':'d','catalog_path':'c','scripts_path':'s','script_manifest_path':'sm','engine_manifest_path':'em','timeout_ms':30000},'deck':{'main':[],'extra':[],'side':[]},'opening_hand':[],'seed':1,'decisions':[],'versions':{'rules':'r','catalog':'c','banlist':'b','engine_sha256':'a','cdb_sha256':'b','scripts_sha256':'c','core_commit':'d','initializer':'i'},'probe_only':False}
        result={'protocol_version':2,'status':'engine_verified','events':[],'prompt':None,'checkpoint':{'turn':1,'turn_player':0,'phase':512,'lp':[8000,8000],'cards':[]},'error':None,'versions':request['versions'],'loaded_scripts':{},'steps':[],'resolved_decisions':[],'coverage_gaps':[],'peak_working_set_bytes':None}
        blobs={}
        def blob(folder,value):
            raw=wire(value);h=hashed(raw);blobs[(folder,h)]=raw;return h
        empty=hashed(b'[]')
        budget={'consumed':0,'completed':0,'unknown':0,'reserved':0,'abandoned':0,'limit':4096}
        def cp(name,search):
            return {'kind':'checkpoint','name':name,'blob':blob('checkpoints',{'budget':budget,'charged_sequence':empty,'reservations':{},'search':search}),'consumed':0,'charged_sequence':empty}
        request_hash=hashed(json.dumps({k:v for k,v in request.items() if k!='engine'},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
        entries=[{'kind':'header','version':1,'scope':'research-first-batch-v1','context':'ctx','limit':4096},cp('research/case/rabbit',hashed(wire(request))),cp('research/debit/0','rabbit'),{'kind':'begin','call_id':1,'request':request_hash,'purpose':'execution','reservation':None}]
        stored=blob('results',{'kind':'duel','result':result,'event_chunks':[]})
        entries.append({'kind':'complete','call_id':1,'result':stored,'raw_hash':hashed(wire(result)),'normalized_hash':hashed(wire(result))})
        return entries,blobs,{'rabbit':request}

    def check_fixture(self,entries,blobs,requests):
        return verify_ledger(records(entries),lambda folder,h:blobs[(folder,h)],requests,expected_calls=1)

    def test_synthetic_frozen_result_and_failures(self):
        entries,blobs,requests=self.fixture()
        self.assertEqual(self.check_fixture(entries,blobs,requests)['stats']['completed'],1)
        for mutation in ['request','purpose','duplicate','missing','raw','normal','blob','checkpoint','debit','sequence']:
            e=copy.deepcopy(entries);b=copy.deepcopy(blobs);r=copy.deepcopy(requests)
            if mutation=='request':e[3]['request']='0'*64
            if mutation=='purpose':e[3]['purpose']='probe'
            if mutation=='duplicate':e.append(copy.deepcopy(e[-1]))
            if mutation=='missing':e.pop()
            if mutation=='raw':e[-1]['raw_hash']='0'*64
            if mutation=='normal':e[-1]['normalized_hash']='0'*64
            if mutation=='blob':b[('results',e[-1]['result'])]+=b' '
            if mutation=='checkpoint':e[1]['consumed']=1
            if mutation=='debit':e[2]['name']='research/debit/1'
            if mutation=='sequence':e[3]['call_id']=2
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.check_fixture(e,b,r)

    def test_begin_without_case_binding_is_rejected(self):
        e,b,r=self.fixture();e.pop(1)
        with self.assertRaises(ValueError):self.check_fixture(e,b,r)

    def test_non_first_previous_pointer_mismatch_is_rejected_by_ledger_parser(self):
        entries, blobs, requests = self.fixture()
        raw_rows = [json.loads(line) for line in records(entries).splitlines()]
        # Keep the record's original hash so this specifically exercises the
        # parser's sequence-link check before it reaches the hash check.
        raw_rows[4]['previous'] = 'f' * 64
        malformed = b''.join(wire(row) + b'\n' for row in raw_rows)

        with self.assertRaisesRegex(ValueError, '^ledger_sequence_mismatch$'):
            verify_ledger(malformed, lambda folder, digest: blobs[(folder, digest)], requests, expected_calls=1)

    def test_live_report_schema_and_qualifications(self):
        from test_schemas import validator
        repo=Path(__file__).resolve().parents[1]
        baseline=repo/'data/runtime/p1-terminal-followup-2026-10-20'
        if not baseline.exists():self.skipTest('local pinned history unavailable')
        report=audit_history(baseline,repo)
        validator('history-audit.schema.json').validate(report)
        forged=copy.deepcopy(report);forged['original_runner_available']=True
        with self.assertRaises(Exception):validator('history-audit.schema.json').validate(forged)

    def test_frozen_result_nested_field_order_is_not_trusted(self):
        e,b,r=self.fixture()
        old=e[-1]['result'];stored=json.loads(b[('results',old)])
        stored['result']['checkpoint']=dict(reversed(list(stored['result']['checkpoint'].items())))
        raw=wire(stored);new=hashed(raw);b[('results',new)]=raw;e[-1]['result']=new
        self.assertEqual(self.check_fixture(e,b,r)['stats']['completed'],1)

    def test_all_nine_report_bindings_keep_singleton_and_metadata_limit(self):
        repo=Path(__file__).resolve().parents[1]
        baseline=repo/'data/runtime/p1-terminal-followup-2026-10-20'
        if not baseline.exists():self.skipTest('local pinned history unavailable')
        report=audit_history(baseline,repo)
        self.assertEqual([r['call_ids'] for r in report['report_bindings']],[[1,2],[3,4],[5,6],[7],[8,9]])
        singleton=report['report_bindings'][3]
        self.assertEqual(singleton['provenance'],'ledger_fields_recomputed')
        self.assertFalse(singleton['metadata_origin_verified'])

    def test_checkpoint_budget_boolean_is_not_an_integer(self):
        e,b,r=self.fixture()
        entry=e[1];payload=json.loads(b[('checkpoints',entry['blob'])]);payload['budget']['consumed']=False
        raw=wire(payload);entry['blob']=hashed(raw);b[('checkpoints',entry['blob'])]=raw
        with self.assertRaises(ValueError):self.check_fixture(e,b,r)

    def test_event_chunks_and_rehashed_event_order(self):
        e,b,r=self.fixture();stored=json.loads(b[('results',e[-1]['result'])])
        frame={'sequence':1,'opcode':40,'raw':[40,0],'supported':True,'fields':{'player':0}}
        raw=wire([frame]);h=hashed(raw);b[('events',h)]=raw;stored['event_chunks']=[h]
        restored=copy.deepcopy(stored['result']);restored['events']=[frame]
        raw=wire(stored);e[-1]['result']=hashed(raw);b[('results',hashed(raw))]=raw
        e[-1]['raw_hash']=e[-1]['normalized_hash']=hashed(wire(restored))
        self.assertEqual(self.check_fixture(e,b,r)['calls'][0]['event_count'],1)
        for altered in [b[('events',h)]+b' ',wire([{**frame,'sequence':2}])]:
            ee=copy.deepcopy(e);bb=copy.deepcopy(b)
            if altered.endswith(b' '):bb[('events',h)]=altered
            else:
                nh=hashed(altered);bb[('events',nh)]=altered
                change=copy.deepcopy(stored);change['event_chunks']=[nh];raw=wire(change);ee[-1]['result']=hashed(raw);bb[('results',hashed(raw))]=raw
            with self.assertRaises(ValueError):self.check_fixture(ee,bb,r)

    def test_directory_addition_during_audit_is_rejected(self):
        import ygo_eval.history_audit as module
        repo=Path(__file__).resolve().parents[1];baseline=repo/'data/runtime/p1-terminal-followup-2026-10-20'
        if not baseline.exists():self.skipTest('local pinned history unavailable')
        original=module.blob_layout;calls=[]
        def changed(directory):
            files,dirs=original(directory);calls.append(1)
            return (files,dirs+['extra']) if len(calls)>1 else (files,dirs)
        with patch.object(module,'blob_layout',side_effect=changed):report=module.audit_history(baseline,repo)
        self.assertFalse(report['valid']);self.assertIn('blob_directory_changed_during_audit',report['diagnostics'])

    def test_writer_is_exclusive_and_does_not_start_processes(self):
        from uuid import uuid4
        from types import SimpleNamespace
        from ygo_eval.history_audit import audit_to_output
        repo=Path(__file__).resolve().parents[1]
        recovery=repo/'data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21'
        if not recovery.exists():self.skipTest('local pinned history unavailable')
        output=recovery/('test-audit-'+uuid4().hex+'.json')
        try:
            args=SimpleNamespace(baseline_dir=recovery.parent,output=output)
            with patch('subprocess.run',side_effect=AssertionError('no process')):
                report=audit_to_output(args)
                self.assertTrue(report['valid'])
                with self.assertRaisesRegex(ValueError,'output_already_exists'):audit_to_output(args)
        finally:
            if output.exists():output.unlink()

    def test_input_change_during_capture_is_rejected_without_writing(self):
        import ygo_eval.history_audit as module
        repo=Path(__file__).resolve().parents[1];baseline=repo/'data/runtime/p1-terminal-followup-2026-10-20'
        if not baseline.exists():self.skipTest('local pinned history unavailable')
        original=Path.read_bytes;target=Path(module.__file__).resolve();seen=[]
        def changed(path):
            raw=original(path)
            if path==target:
                seen.append(1)
                if len(seen)>1:return raw+b'\n'
            return raw
        with patch.object(Path,'read_bytes',changed):report=module.audit_history(baseline,repo)
        self.assertFalse(report['valid']);self.assertIn('input_changed_during_audit',report['diagnostics'])

    def test_report_contains_no_personal_absolute_paths(self):
        repo=Path(__file__).resolve().parents[1];baseline=repo/'data/runtime/p1-terminal-followup-2026-10-20'
        if not baseline.exists():self.skipTest('local pinned history unavailable')
        report=audit_history(baseline,repo)
        self.assertTrue(report['valid'])
        raw=json.dumps(report)
        self.assertNotIn(str(repo),raw)
        self.assertNotIn('D:',raw)
        self.assertNotIn('C:',raw)

    def test_frozen_profile_requires_start_binding_mode_and_authorized_window(self):
        repo=Path(__file__).resolve().parents[1];base=repo/'data/runtime/baseline-2026-10-19/research'
        if not base.exists():self.skipTest('local pinned history unavailable')
        rows=[json.loads(line) for line in (base/'calls.jsonl').read_text().splitlines()]
        original=[row['entry'] for row in rows]
        frozen=json.loads((base/'frozen-cases.json').read_bytes())
        requests={item['case']['case_id']:item['request'] for item in frozen['cases']}
        originals={(folder,p.stem):p.read_bytes() for folder in ['checkpoints','events','results'] for p in (base/('calls.jsonl.blobs/'+folder)).iterdir()}
        for mutation in ['start','immutable','window']:
            entries=copy.deepcopy(original);blobs=copy.deepcopy(originals)
            for index,entry in enumerate(entries):
                if mutation=='start' and entry.get('name')=='research/start':
                    entries[index]=copy.deepcopy(entries[index+1]);break
                if mutation=='immutable' and entry.get('name')=='immutable/research/case/tournament':
                    entry['name']='research/case/tournament';break
                if mutation=='window' and entry.get('name')=='immutable/research/authorized-window/user-resume-20261019':
                    payload=json.loads(blobs[('checkpoints',entry['blob'])])
                    earlier=next(e for e in entries if e.get('name')=='immutable/research/case/tournament')
                    payload['search']=json.loads(blobs[('checkpoints',earlier['blob'])])['search']
                    raw=wire(payload);entry['blob']=hashed(raw);blobs[('checkpoints',entry['blob'])]=raw;entry['name']='research/case/tournament';break
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                verify_ledger(records(entries),lambda folder,h:blobs[(folder,h)],requests)
