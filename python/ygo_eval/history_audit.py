"""Independent read-only verifier for the sealed nine-call research ledger."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat

ANCHOR_SHA = '7bf14e90c46e2a6c610f47433cfbe63b6eb377c147f2646186daf75081a05cf7'
LEDGER_SHA = 'b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a'
OLD_ROOT = 'data/runtime/baseline-2026-10-19/research'
FLAGS = dict(proof_ready=False, complete_action_coverage=False, global_optimality=False)
ENTRY_FIELDS = {
 'header': ('kind','version','scope','context','limit'),
 'checkpoint': ('kind','name','blob','consumed','charged_sequence'),
 'begin': ('kind','call_id','request','purpose','reservation'),
 'complete': ('kind','call_id','result','raw_hash','normalized_hash')}
CALL_PROFILE = [('rabbit','execution'),('rabbit','replay'),('phantom','execution'),('phantom','replay'),
                ('tournament','execution'),('tournament','replay'),('tournament','execution'),
                ('tournament','execution'),('tournament','replay')]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value, sorted_keys=False):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=sorted_keys,allow_nan=False).encode('utf8')


def strict_json(raw):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out: raise ValueError('duplicate_json_key')
            out[key]=value
        return out
    def invalid(_): raise ValueError('nonfinite_json_number')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def require(condition, reason):
    if not condition: raise ValueError(reason)


def ordered(value, keys):
    require(isinstance(value,dict) and set(value)==set(keys),'unsupported_frozen_shape')
    return {key:value[key] for key in keys}


def ordered_request(value):
    result=ordered(value,('protocol_version','engine','deck','opening_hand','seed','decisions','versions','probe_only'))
    result['engine']=ordered(value['engine'],('worker_path','ocgcore_path','catalog_path','scripts_path','script_manifest_path','engine_manifest_path','timeout_ms'))
    result['deck']=ordered(value['deck'],('main','extra','side'))
    result['versions']=ordered(value['versions'],('rules','catalog','banlist','engine_sha256','cdb_sha256','scripts_sha256','core_commit','initializer'))
    choices={'command':('kind','command','index'),'cards':('kind','indices'),'toggle':('kind','index'),
             'finish':('kind',),'yes_no':('kind','yes'),'option':('kind','index'),'place':('kind','zones'),
             'position':('kind','position'),'chain':('kind','index')}
    result['decisions']=[]
    for item in value['decisions']:
        decision=ordered(item,('prompt_id','player','choice'))
        choice=item['choice']; require(choice.get('kind') in choices,'unsupported_frozen_choice')
        decision['choice']=ordered(choice,choices[choice['kind']])
        if choice['kind']=='place': decision['choice']['zones']=[ordered(z,('player','location','sequence')) for z in choice['zones']]
        result['decisions'].append(decision)
    return result



def sorted_value(value):
    if isinstance(value,dict):return {k:sorted_value(value[k]) for k in sorted(value)}
    if isinstance(value,list):return [sorted_value(v) for v in value]
    return value


def frozen_choice(value):
    fields={'command':('kind','command','index'),'cards':('kind','indices'),'toggle':('kind','index'),
            'finish':('kind',),'yes_no':('kind','yes'),'option':('kind','index'),'place':('kind','zones'),
            'position':('kind','position'),'chain':('kind','index')}
    require(isinstance(value,dict) and value.get('kind') in fields,'unsupported_frozen_choice')
    result=ordered(value,fields[value['kind']])
    if value['kind']=='place':result['zones']=[ordered(z,('player','location','sequence')) for z in value['zones']]
    return result


def frozen_decision(value):
    result=ordered(value,('prompt_id','player','choice'));result['choice']=frozen_choice(value['choice']);return result


def frozen_action(value):
    result=ordered(value,('choice','label','card_ids','bytes'));result['choice']=frozen_choice(value['choice']);return result


def frozen_result(value):
    required=('protocol_version','status','events','prompt','checkpoint','error','versions','loaded_scripts','steps','resolved_decisions','coverage_gaps','peak_working_set_bytes')
    result=ordered(value,required)
    result['events']=[]
    for frame in value['events']:
        frame=ordered(frame,('sequence','opcode','raw','supported','fields'));frame['fields']=sorted_value(frame['fields']);result['events'].append(frame)
    if value['prompt'] is not None:
        prompt=ordered(value['prompt'],('id','player','opcode','actions'));prompt['actions']=[frozen_action(a) for a in prompt['actions']];result['prompt']=prompt
    checkpoint=ordered(value['checkpoint'],('turn','turn_player','phase','lp','cards'))
    cards=[]
    required_card=('code','player','location','sequence','position','type_flags','attack','defense','overlay')
    optional=('level','rank','attribute','race','base_attack','base_defense','owner','status','link','link_marker','is_public')
    for card in checkpoint['cards']:
        require(set(required_card).issubset(card) and set(card).issubset(set(required_card+optional)),'unsupported_card_fields')
        cards.append({k:card[k] for k in required_card+optional if k in card})
    checkpoint['cards']=cards;result['checkpoint']=checkpoint
    if value['error'] is not None:result['error']=ordered(value['error'],('code','stage','message'))
    result['versions']=ordered(value['versions'],('rules','catalog','banlist','engine_sha256','cdb_sha256','scripts_sha256','core_commit','initializer'))
    result['loaded_scripts']=sorted_value(value['loaded_scripts'])
    result['steps']=[frozen_action(a) for a in value['steps']]
    result['resolved_decisions']=[frozen_decision(d) for d in value['resolved_decisions']]
    return result

def request_digest(request):
    value=copy.deepcopy(request);value.pop('engine',None)
    return digest(encode(value,True))


def stats(calls):
    completed=sum(c['completed'] for c in calls.values())
    return dict(consumed=len(calls),completed=completed,unknown=len(calls)-completed,reserved=0,abandoned=0,limit=4096)


def sequence_id(calls):
    return digest(encode([[i,c['request'],c['purpose'],c.get('normalized_hash')] for i,c in calls.items()]))


def verify_ledger(raw, blob_reader, requests, expected_calls=9):
    """Verify frozen v1 bytes without opening any journal or process."""
    require(raw and raw.endswith(b'\n'),'torn_or_empty_ledger')
    lines=raw.splitlines();require(all(lines),'blank_ledger_record')
    calls={}; checkpoints=[]; latest={}; previous=''; restored={}; debits={}
    identities={request_digest(r):case for case,r in requests.items()}
    for index,line in enumerate(lines):
        row=ordered(strict_json(line),('sequence','previous','entry','hash'))
        require(type(row['sequence']) is int and row['sequence']==index and row['previous']==previous,'ledger_sequence_mismatch')
        entry=row['entry'];kind=entry.get('kind') if isinstance(entry,dict) else None
        require(kind in ENTRY_FIELDS,'unsupported_ledger_record')
        entry=ordered(entry,ENTRY_FIELDS[kind])
        require(digest(encode([index,previous,entry]))==row['hash'],'ledger_chain_mismatch')
        previous=row['hash']
        if index==0:
            require(kind=='header' and entry['version']==1 and type(entry['version']) is int
                    and entry['scope']=='research-first-batch-v1' and entry['limit']==4096
                    and type(entry['limit']) is int and isinstance(entry['context'],str) and entry['context'],'header_mismatch')
            continue
        require(kind!='header','duplicate_header')
        if kind=='begin':
            call=entry['call_id'];require(type(call) is int and call==len(calls)+1 and call<=4096,'invalid_call_id')
            require(entry['reservation'] is None and entry['purpose'] in ('execution','replay'),'invalid_purpose_or_reservation')
            case=identities.get(entry['request']);require(case is not None,'request_identity_mismatch')
            require(stats(calls)['unknown']==0,'unresolved_prior_call')
            require(debits.get(call-1)==case,'case_debit_mismatch')
            require('research/case/'+case in latest or 'immutable/research/case/'+case in latest,'missing_case_binding')
            if expected_calls==9:
                require(call<=9 and (case,entry['purpose'])==CALL_PROFILE[call-1],'call_profile_mismatch')
                require('research/start' in latest,'missing_start_checkpoint')
                binding=('research/case/'+case) if call<=6 else 'immutable/research/case/tournament'
                require(binding in latest,'missing_frozen_binding_mode')
                if call>=8:require('immutable/research/authorized-window/user-resume-20261019' in latest,'missing_authorized_window')
            calls[call]=dict(request=entry['request'],purpose=entry['purpose'],case_id=case,completed=False)
        elif kind=='complete':
            call=entry['call_id'];require(type(call) is int and call in calls and not calls[call]['completed'],'invalid_completion')
            raw_result=blob_reader('results',entry['result'])
            require(digest(raw_result)==entry['result'],'result_blob_mismatch')
            stored=ordered(strict_json(raw_result),('kind','result','event_chunks'))
            require(stored['kind']=='duel' and isinstance(stored['event_chunks'],list),'unsupported_result_record')
            result=stored['result'];require(isinstance(result,dict) and result.get('events')==[],'events_not_chunked')
            # Stored typed field order is part of the frozen byte contract; the
            # sealed result blob authenticates these exact bytes before restore.
            required=('protocol_version','status','events','prompt','checkpoint','error','versions','loaded_scripts','steps','resolved_decisions','coverage_gaps','peak_working_set_bytes')
            result=ordered(result,required);events=[]
            for chunk in stored['event_chunks']:
                raw_events=blob_reader('events',chunk);require(digest(raw_events)==chunk,'event_blob_mismatch')
                frames=strict_json(raw_events);require(isinstance(frames,list) and 0<len(frames)<=64,'invalid_event_chunk')
                for frame in frames:
                    ordered(frame,('sequence','opcode','raw','supported','fields'))
                    require(type(frame['sequence']) is int and frame['sequence']==len(events)+1,'event_sequence_mismatch')
                    events.append(frame)
            result['events']=events
            result=frozen_result(result)
            require(digest(encode(result))==entry['raw_hash'],'raw_result_hash_mismatch')
            normal=copy.deepcopy(result);normal['peak_working_set_bytes']=None
            require(digest(encode(normal))==entry['normalized_hash'],'normalized_result_hash_mismatch')
            calls[call].update(completed=True,result_sha256=entry['result'],raw_hash=entry['raw_hash'],normalized_hash=entry['normalized_hash'],event_count=len(events))
            restored[call]=result
        elif kind=='checkpoint':
            require(stats(calls)['unknown']==0,'checkpoint_with_unresolved_call')
            name=entry['name'];require(isinstance(name,str) and name,'invalid_checkpoint_name')
            require(not name.startswith('immutable/') or name not in latest,'duplicate_immutable_checkpoint')
            current=stats(calls);prefix=sequence_id(calls)
            require(type(entry['consumed']) is int and entry['consumed']==current['consumed'] and entry['charged_sequence']==prefix,'checkpoint_prefix_mismatch')
            payload_raw=blob_reader('checkpoints',entry['blob']);require(digest(payload_raw)==entry['blob'],'checkpoint_blob_mismatch')
            payload=ordered(strict_json(payload_raw),('budget','charged_sequence','reservations','search'))
            require(isinstance(payload['budget'],dict) and all(type(v) is int and v>=0 for v in payload['budget'].values()),'checkpoint_budget_type_mismatch')
            require(payload['budget']==current and payload['reservations']=={} and payload['charged_sequence']==prefix,'checkpoint_budget_mismatch')
            search=payload['search']
            if name=='research/start': require(type(search) is int and search>=0 and name not in latest,'invalid_start_checkpoint')
            elif name.startswith('research/debit/'):
                number=name[len('research/debit/'):];require(number.isdecimal() and str(int(number))==number,'invalid_debit_name')
                number=int(number);require(number==len(calls) and number not in debits and search in requests,'invalid_case_debit')
                debits[number]=search
            elif name.startswith('research/case/') or name.startswith('immutable/research/case/'):
                case=name.rsplit('/',1)[1];require(case in requests,'unknown_checkpoint_case')
                require(search==digest(encode(ordered_request(requests[case]))),'full_request_binding_mismatch')
            elif name=='immutable/research/authorized-window/user-resume-20261019':
                expected=dict(additional_calls=2,base_consumed=7,case_id='tournament',id='user-resume-20261019',started=search.get('started') if isinstance(search,dict) else None)
                require(search==expected and all(type(search[k]) is int and search[k]>=0 for k in ('additional_calls','base_consumed','started')) and len(calls)==7,'authorized_window_mismatch')
            else:raise ValueError('unsupported_checkpoint')
            latest[name]=search
            checkpoints.append(dict(name=name,consumed=len(calls),charged_sequence=prefix,blob_sha256=entry['blob']))
    require(len(calls)==expected_calls and stats(calls)['unknown']==0,'incomplete_consumption')
    require(set(debits)==set(range(expected_calls)),'unfinished_or_missing_debit')
    if expected_calls==9:require(len(lines)==37,'frozen_record_count_mismatch')
    return dict(stats=stats(calls),calls=[dict(call_id=i,**c) for i,c in calls.items()],checkpoints=checkpoints,
                ledger_records=len(lines),charged_sequence=sequence_id(calls),restored=restored)


def safe_file(path):
    path=Path(os.path.abspath(path))
    for item in [*reversed(path.parents),path]:
        info=item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'linked_path_rejected')
    require(path.is_file(),'regular_file_required')
    return path


def within(repo, name):
    name=Path(name)
    require(not name.is_absolute() and '..' not in name.parts,'unsafe_relative_path')
    path=(repo/name).absolute();require(path.is_relative_to(repo),'unsafe_relative_path')
    return path



def blob_layout(directory):
    files=[];dirs=[]
    for path in directory.rglob('*'):
        info=path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'linked_blob_tree_rejected')
        if path.is_dir():dirs.append(path.relative_to(directory).as_posix())
        elif path.is_file():files.append(path.relative_to(directory).as_posix())
        else:raise ValueError('unsupported_blob_tree_entry')
    return sorted(files),sorted(dirs)

def audit_history(baseline_dir, repo=None):
    """Recompute an anchored report. Every source is read-only, without subprocess."""
    repo=Path(repo or Path(__file__).resolve().parents[2]).absolute()
    baseline=Path(baseline_dir).absolute()
    report=dict(schema_version=1,kind='history_audit',valid=False,anchor_sha256=ANCHOR_SHA,input_sha256={},
                auditor_source_identity=None,auditor_source_files={},stats=None,ledger_records=0,calls=[],checkpoints=[],
                report_bindings=[],unpaired_call_ids=[7],diagnostics=[],native_calls=0,original_runner_available=False,
                original_binary_provenance_verified=False,historical_reexecution_verified=False,native_replay_verified=False,**FLAGS)
    inputs={};blob_lists={}
    def read(path, expected=None):
        path=safe_file(path);require(path.is_relative_to(repo),'source_outside_repository')
        raw=path.read_bytes();hashed=digest(raw)
        require(expected is None or hashed==expected,'anchored_input_hash_mismatch')
        name=path.relative_to(repo).as_posix()
        require(name not in inputs or inputs[name]==hashed,'input_changed_during_read')
        inputs[name]=hashed
        return raw
    try:
        require(baseline==repo/'data/runtime/p1-terminal-followup-2026-10-20','baseline_directory_mismatch')
        anchor=strict_json(read(baseline/'acceptance.json',ANCHOR_SHA))
        require(anchor.get('source_identity')=='9cc721041044fd018e7ae466cd631b916470e41927c74c60e2778343a544ad85'
                and anchor.get('cumulative_consumed')==20 and anchor.get('unknown')==anchor.get('reserved')==0,'anchor_identity_mismatch')
        before_path=baseline/'before.json';before=strict_json(read(before_path,anchor['evidence']['before.json']['sha256']))
        protected=before['protected_files']
        old=repo/OLD_ROOT
        for name,expected in protected.items():
            path=within(repo,name)
            if path.is_relative_to(old):read(path,expected)
        ledger_name=(old/'calls.jsonl').relative_to(repo).as_posix()
        raw=read(old/'calls.jsonl',LEDGER_SHA)
        blobroot=old/'calls.jsonl.blobs'
        expected_blobs=next(value for name,value in before['blob_files'].items() if within(repo,name)==blobroot)
        names,dirs=blob_layout(blobroot)
        require(dirs==['checkpoints','events','recoveries','results'],'blob_directory_manifest_mismatch')
        actual={name:digest(read(blobroot/name)) for name in names}
        require(actual==expected_blobs,'blob_directory_manifest_mismatch');blob_lists[blobroot]=(actual,dirs)
        frozen=strict_json(read(old/'frozen-cases.json',protected[(old/'frozen-cases.json').relative_to(repo).as_posix()]))
        requests={}
        for item in frozen['cases']:
            case=item['case']['case_id'];require(case not in requests,'duplicate_frozen_case');requests[case]=item['request']
        require(set(requests)=={'rabbit','phantom','tournament'},'frozen_case_set_mismatch')
        def blob(folder, hashed):
            require(isinstance(hashed,str) and len(hashed)==64 and all(c in '0123456789abcdef' for c in hashed),'invalid_blob_address')
            require(folder in ('results','events','checkpoints'),'unsupported_blob_folder')
            return read(blobroot/folder/(hashed+'.json'),hashed)
        result=verify_ledger(raw,blob,requests)
        restored=result.pop('restored');report.update(result)
        bindings=[('rabbit-2.json',[1,2]),('phantom-4.json',[3,4]),('tournament-6-1792382565073757500-0.json',[5,6]),('tournament-7-1792383041824358400-0.json',[7]),('tournament-9-1792409563968375300-0.json',[8,9])]
        for filename,ids in bindings:
            path=old/'evidence'/filename;relative=path.relative_to(repo).as_posix()
            value=strict_json(read(path,protected.get(relative)));case=CALL_PROFILE[ids[0]-1][0]
            require(value['case_id']==case and value['request']==requests[case],'report_request_mismatch')
            extra_error=None
            if ids==[7]:
                require(len(value['runs'])==2 and set(value['runs'][1])=={'Err'},'single_call_report_shape_mismatch')
                extra_error=value['runs'][1]['Err']
                require(extra_error.get('code')=='journal_checkpoint' and extra_error.get('stage')=='call_journal','single_call_followup_error_mismatch')
            else:require(len(value['runs'])==len(ids),'report_run_count_mismatch')
            prefix_calls={c['call_id']:c for c in result['calls'] if c['call_id']<=ids[-1]}
            require(value['ledger_sequence']==sequence_id(prefix_calls),'report_ledger_prefix_mismatch')
            for call,run in zip(ids,value['runs']):require(run=={'Ok':restored[call]},'report_result_mismatch')
            # Compare stored outcomes; this is not a fresh native replay.
            if len(ids)==2:
                left=copy.deepcopy(restored[ids[0]]);right=copy.deepcopy(restored[ids[1]])
                left['peak_working_set_bytes']=right['peak_working_set_bytes']=None
                require(left==right,'recorded_pair_difference')
            report['report_bindings'].append(dict(case_id=case,call_ids=ids,source_sha256=inputs[relative],
                provenance='anchored_report' if relative in protected else 'ledger_fields_recomputed',
                metadata_origin_verified=False,
                observed_uncharged_followup_error_sha256=digest(encode(extra_error,True)) if extra_error is not None else None,
                observed_asset_capture_diagnostic_sha256=digest(encode(value['asset_capture_diagnostic'],True)) if value.get('asset_capture_diagnostic') is not None else None,
                observed_independent_replay_matches=value.get('independent_replay_matches') if type(value.get('independent_replay_matches')) is bool else None))
        # Original build records remain metadata, never a claim that the absent
        # original executable has been authenticated or rerun.
        for filename,expected in [('build-before-native.json','01c2b52451ebcdb6837d5d5e29ffdae7c1aa3be36e9c2b88545db2e4e923bb0f'),('build-resumed-native.json','7090a52dbb95443ab22a27598ac20d372e3fd084c0bd54aafe5cadfa533e02ec')]:
            build=strict_json(read(old.parent/filename,expected));require(build.get('status')=='recorded','build_metadata_invalid')
        module=Path(__file__).resolve();schema=repo/'schemas/history-audit.schema.json'
        source_files={p.relative_to(repo).as_posix():digest(read(p)) for p in (module,schema)}
        report['auditor_source_files']=source_files;report['auditor_source_identity']=digest(encode(source_files,True))
        for name,expected in inputs.items():require(digest(safe_file(repo/name).read_bytes())==expected,'input_changed_during_audit')
        for directory,(expected,expected_dirs) in blob_lists.items():
            names,dirs=blob_layout(directory)
            require(dirs==expected_dirs and names==sorted(expected),'blob_directory_changed_during_audit')
            current={name:digest(safe_file(directory/name).read_bytes()) for name in names}
            require(current==expected,'blob_directory_changed_during_audit')
        report['valid']=True
    except (OSError,ValueError,KeyError,TypeError,StopIteration,OverflowError):
        import sys
        reason=str(sys.exc_info()[1])
        allowed={'anchored_input_hash_mismatch','blob_directory_manifest_mismatch','input_changed_during_read','input_changed_during_audit','blob_directory_changed_during_audit'}
        report['diagnostics']=[reason if reason in allowed or reason and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in reason) else 'history_audit_rejected']
        report['valid']=False
    report['input_sha256']=dict(sorted(inputs.items()))
    return report


def audit_to_output(args):
    """Publish exclusively beneath the fixed ignored recovery directory."""
    repo=Path(__file__).resolve().parents[2]
    output=Path(os.path.abspath(args.output))
    allowed=repo/'data/runtime/p1-terminal-followup-2026-10-20/recovery-2026-10-21'
    require(output.is_relative_to(allowed) and output.suffix=='.json','dedicated_recovery_output_required')
    ignored=(repo/'.gitignore').read_text(encoding='utf8').splitlines()
    require(any(line.strip().strip('/')=='data/runtime' for line in ignored),'ignored_output_contract_missing')
    for parent in [*reversed(output.parents),output]:
        if parent.exists() or parent.is_symlink():
            info=parent.lstat();require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'linked_output_rejected')
    require(not output.exists(),'output_already_exists')
    report=audit_history(args.baseline_dir,repo)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:
        stream.write(encode(report,True));stream.flush();os.fsync(stream.fileno())
    return report
