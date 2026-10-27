"""Six-stage Tenki native probe; each charged call belongs to the Rust ledger runner."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import time

from ygo_data.identity import canonical, digest, regular_file, stable_source
from ygo_eval.prompt_probe_prepare import strict_json, require, safe_path, relative
from ygo_eval.prompt_probe_logic import select_unique_activation
from ygo_eval.terminal_regression import immutable_write

ACCEPTANCE_SHA='0e88c82501c4bbc229d6326b6b789411a93426f9474a02cd0e83e2c6cacbfcf7'
OLD_SOURCE='56524e906812a1313991b375f27d82f150787407b7c178aa86f43b6f0c7b993b'
CASES_SHA='de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879'
SCOPE='tenki-prompt-probe-v1'
FLAGS={'proof_ready':False,'complete_action_coverage':False,'global_optimality':False,'native_probability_verified':False}


def sha(path):
    return digest(regular_file(path).read_bytes())


def add_arguments(parser):
    for name in ('preparation','cases','baseline-dir','runner','worker','build-record','identity','window-start','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')


def derive_stage_request(stage,parent):
    """Append only a matching recorded legal action to the resolved actual prefix."""
    request=copy.deepcopy(parent['request'])
    if stage in (4,6):
        return request
    require(stage in (2,3,5),'unsupported_derived_stage')
    result=parent['result']['Ok'];prompt=result['prompt']
    require(type(prompt.get('id')) is int and prompt['id']>=0 and prompt.get('player')==0 and type(prompt.get('player')) is int,'actual_own_prompt_required')
    resolved=result.get('resolved_decisions')
    require(isinstance(resolved,list) and resolved[:len(request['decisions'])]==request['decisions'],'parent_resolved_decisions_mismatch')
    if stage==2:
        action=select_unique_activation(prompt,57103969)
    else:
        require(type(prompt.get('opcode')) is int and prompt['opcode']==13,'actual_yes_no_prompt_required')
        choice={'kind':'yes_no','yes':stage==5}
        actions=[a for a in prompt.get('actions',[]) if a.get('choice')==choice]
        require(len(actions)==1 and actions[0].get('bytes')==[int(stage==5),0,0,0],'actual_yes_no_action_required')
        action=actions[0]
    request['decisions']=copy.deepcopy(resolved)+[{'prompt_id':prompt['id'],'player':0,'choice':copy.deepcopy(action['choice'])}]
    return request


def summarize(context,stages,stats,diagnostic=None):
    """Unavailable stats stay unknown, including cumulative consumption."""
    settled=isinstance(stats,dict) and all(type(stats.get(key)) is int and stats[key]>=0 for key in ('consumed','completed','unknown','reserved','abandoned','limit'))
    if settled:
        settled=stats['limit']==6 and stats['consumed']==stats['completed']+stats['unknown'] and stats['abandoned']<=stats['unknown'] and stats['consumed']+stats['reserved']<=6
    if not settled:
        diagnostic=diagnostic or 'stats_unavailable'
    elif stats['unknown'] or stats['reserved']:
        diagnostic=diagnostic or 'unresolved_consumption'
    successful=diagnostic is None and len(stages)==6 and all(item.get('successful') is True for item in stages) and settled and stats['limit']==6 and stats['consumed']==6 and stats['completed']==6 and stats['unknown']==0 and stats['reserved']==0 and stats['abandoned']==0
    if not successful:
        diagnostic=diagnostic or 'incomplete_or_failed_stage'
    return {'schema_version':1,'kind':'native_prompt_probe_summary','scope':SCOPE,'context':context,'successful':successful,'diagnostic':diagnostic,'old_consumed':24,'new_consumed':stats['consumed'] if settled else None,'cumulative_consumed':24+stats['consumed'] if settled else None,'ledger':stats if settled else None,'stages':stages,**FLAGS}


def validate_static_sources(report,repo,protected):
    """Check pinned static executor sources without rebinding older tool source hashes."""
    hashes=report.get('input_sha256')
    require(isinstance(hashes,dict) and 'core/libduel.cpp' in hashes,'static_core_binding_missing')
    for role,expected in hashes.items():
        if role.startswith('core/'):
            path=relative(repo/'data/tmp/ocgcore-source',role.removeprefix('core/'))
        elif role.startswith('repository/'):
            path=relative(repo,role.removeprefix('repository/'))
        else:
            continue
        path=regular_file(path)
        require(sha(path)==expected,'static_source_hash_mismatch')
        protected[path]=expected


def validate_baseline(baseline,preparation,repo):
    """Bind the previous immutable acceptance, 37 evidence members and 327 files."""
    protected={}
    def read(path,expected=None):
        path=regular_file(path);raw=path.read_bytes();value=digest(raw)
        require(expected is None or value==expected,'baseline_file_mismatch')
        protected[path]=value
        return strict_json(raw)
    acceptance=read(baseline/'acceptance.json',ACCEPTANCE_SHA)
    require(acceptance.get('kind')=='prompt_probe_offline_delivery_acceptance' and acceptance.get('source_identity')==OLD_SOURCE and acceptance.get('cumulative_consumed')==24 and acceptance.get('unknown')==0 and len(acceptance.get('evidence',{}))==37,'baseline_acceptance_mismatch')
    for flag in (*FLAGS,'execution_ready','native_reachability_verified','response_acceptance_verified'):
        require(acceptance.get(flag) is False,'baseline_qualification_mismatch')
    for name,item in acceptance['evidence'].items():
        path=regular_file(relative(baseline,name));require(sha(path)==item['sha256'] and path.stat().st_size==item['bytes'],'baseline_evidence_mismatch');protected[path]=item['sha256']
    before=read(baseline/'before.json')
    require(len(before['protected'])==327,'baseline_protected_membership_mismatch')
    for name,expected in before['protected'].items():
        path=regular_file(relative(repo,name));require(sha(path)==expected,'historical_protected_file_changed');protected[path]=expected
    require(sum(item['consumed'] for item in acceptance['ledgers'])==24 and all(item['unknown']==0 for item in acceptance['ledgers']) and len(acceptance['ledgers'])==5,'historical_ledger_totals_mismatch')
    for item in acceptance['ledgers']:
        path=repo/'data/runtime'/item['role']/'research'
        candidates=[p for p in path.rglob('calls.jsonl') if sha(p)==item['sha256']]
        require(len(candidates)==1,'historical_ledger_hash_mismatch');protected[candidates[0]]=item['sha256']
    require(preparation==baseline/'research-final','frozen_preparation_path_required')
    report=read(preparation/'report.json');prepared=read(preparation/'prepared-cases.json')
    validate_static_sources(report,repo,protected)
    require(report.get('preparation_successful') is True and report.get('source_unchanged') is True,'preparation_not_successful')
    candidates=[c for c in prepared['candidates'] if c['case']['case_id']=='prompt-13-tenki-v1']
    require(len(candidates)==1 and candidates[0]['target']=={'opcode':13,'card_id':57103969,'name':'tenki'},'unique_tenki_preparation_required')
    return candidates[0],protected


def output_path(repo,output):
    output=Path(os.path.abspath(output));allowed=repo/'data/runtime/p1-tenki-probe-native-2026-10-21'
    require(output==allowed/'research','dedicated_native_probe_output_required')
    ignored=regular_file(repo/'.gitignore').read_text(encoding='utf8').splitlines()
    require('/data/runtime/' in ignored and not any(s.lstrip().startswith('!') for s in ignored),'unsupported_ignore_policy')
    for path in [*reversed(output.parents),output]:
        if path.exists() or path.is_symlink():
            safe_path(path,False)
        if path!=repo and path.is_relative_to(repo):
            require(not (path/'.gitignore').exists(),'unsupported_nested_ignore')
    return output


def validate_signed(value,kind):
    require(value.get('kind')==kind,'identity_kind_mismatch')
    unsigned={key:item for key,item in value.items() if key!='identity'}
    require(value.get('identity')==digest(canonical(unsigned)),'identity_content_hash_mismatch')


def run_stages(runner,output,manifest,stage1,expected_identity,unchanged,prepare_only=False):
    """Freeze each intent before invocation and stop after the first unsuccessful stage."""
    context=manifest['context'];ledger=output/'calls.jsonl';receipts=[];stats=None;diagnostic=None
    parents={2:1,3:2,4:3,5:2,6:5}
    for stage in range(1,7):
        unchanged()
        request=copy.deepcopy(stage1) if stage==1 else derive_stage_request(stage,receipts[parents[stage]-1])
        invocation={'context':context,'ledger':str(ledger),'output':str(output/f'stage-{stage}.json'),'stage':stage,'request':request,'expected_identity':expected_identity,'started_at':manifest['started_at']}
        path=output/f'stage-{stage}-input.json';immutable_write(output/f'stage-{stage}-request.json',request);immutable_write(path,invocation)
        if prepare_only:
            return {'schema_version':1,'kind':'native_prompt_probe_prepared','context':context,'scope':SCOPE,'prepared':True,'native_calls':0,'planned_calls':6,**FLAGS}
        command=[str(runner),str(path),'--input-sha',sha(path)]
        recorded=(output/f'stage-{stage}.json').exists()
        if not recorded and int(time.time())+30>=manifest['started_at']+7200:
            recovered_stats=None
            if ledger.exists():
                try:
                    recovered=subprocess.run(command+['--stats'],capture_output=True,timeout=60)
                    value=strict_json(recovered.stdout) if recovered.returncode==0 else None
                    recovered_stats=value.get('ledger') if isinstance(value,dict) else None
                except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):
                    pass
            else:
                recovered_stats={'limit':6,'consumed':0,'completed':0,'unknown':0,'reserved':0,'abandoned':0}
            paid_complete=isinstance(recovered_stats,dict) and type(recovered_stats.get('completed')) is int and recovered_stats['completed']>=stage and recovered_stats.get('unknown')==0
            if not paid_complete:
                stats=recovered_stats;diagnostic='window_exhausted_before_new_call'
                break
        try:
            completed=subprocess.run(command+(['--verify-recorded'] if recorded else []),capture_output=True,timeout=180)
            if completed.returncode in (0,1):
                value=strict_json(completed.stdout)
                require(isinstance(value,dict),'runner_stdout_object_required')
                stats=value.get('ledger')
            else: diagnostic='runner_failed'
        except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):
            diagnostic='runner_failed'
        receipt_path=output/f'stage-{stage}.json'
        if receipt_path.exists():
            try:
                receipt=strict_json(regular_file(receipt_path).read_bytes())
                require(isinstance(receipt,dict) and receipt.get('context')==context and type(receipt.get('stage')) is int and receipt['stage']==stage and receipt.get('request')==request and type(receipt.get('successful')) is bool,'stage_receipt_binding_mismatch')
                receipts.append(receipt)
            except (ValueError,OSError,KeyError,TypeError):
                diagnostic='stage_receipt_binding_mismatch'
        else: diagnostic=diagnostic or 'stage_receipt_unavailable'
        if diagnostic is None and (not receipts[-1].get('successful') or any(receipts[-1].get(flag) is not False for flag in ('proof_ready','complete_action_coverage','global_optimality'))):
            diagnostic=receipts[-1].get('diagnostic') or 'stage_validation_failed'
        try: unchanged()
        except (ValueError,OSError):diagnostic='frozen_input_changed'
        if diagnostic is not None:
            try:
                response=subprocess.run(command+['--stats'],capture_output=True,timeout=60)
                value=strict_json(response.stdout) if response.returncode==0 else None
                stats=value.get('ledger') if isinstance(value,dict) else None
            except (OSError,subprocess.TimeoutExpired,ValueError,TypeError):stats=None
            break
    report=summarize(context,[{'stage':r['stage'],'successful':r['successful'],'receipt_sha256':sha(output/f"stage-{r['stage']}.json")} for r in receipts],stats,diagnostic)
    immutable_write(output/('summary-'+digest(canonical(report))+'.json'),report)
    return report


def native_prompt_probe(args,repo=None):
    """Validate current source/build separately from the previous delivery source identity."""
    from ygo_eval.research import validate_sources
    repo=Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]));output=output_path(repo,args.output)
    paths={key:regular_file(Path(getattr(args,key)).absolute()) for key in ('cases','runner','worker','build_record','identity','window_start')}
    baseline=safe_path(args.baseline_dir,False);preparation=safe_path(args.preparation,False)
    require(not output.is_relative_to(baseline) and not output.is_relative_to(preparation),'output_overlaps_input')
    hashes={key:sha(path) for key,path in paths.items()}
    require(hashes['cases']==CASES_SHA,'frozen_cases_hash_mismatch')
    candidate,protected=validate_baseline(baseline,preparation,repo)
    source=stable_source(repo);build=strict_json(paths['build_record'].read_bytes());identity=strict_json(paths['identity'].read_bytes());window=strict_json(paths['window_start'].read_bytes())
    validate_signed(build,'build_record');validate_signed(identity,'workspace_identity')
    require(build.get('status')=='recorded' and build.get('source_before')==source and build.get('source_after')==source,'build_source_mismatch')
    require(all(build.get('artifacts',{}).get(role)==hashes[role] for role in ('runner','worker')),'build_artifact_mismatch')
    require(identity.get('source')==source and identity.get('consistent') is True and identity.get('cli_sha256')==build['artifacts'].get('cli'),'candidate_identity_mismatch')
    require(window.get('schema_version')==1 and window.get('scope')==SCOPE and window.get('limit')==6 and window.get('wall_seconds')==7200 and type(window.get('started_at')) is int and 0<=window['started_at']<=int(time.time()),'invalid_window')
    frozen=strict_json(paths['cases'].read_bytes());base=[item for item in frozen['cases'] if item['case']['case_id']=='rabbit'];require(len(base)==1,'unique_rabbit_required')
    request=copy.deepcopy(base[0]['request']);case=candidate['case']
    for key in ('deck','opening_hand','seed'):request[key]=copy.deepcopy(case[key])
    request['decisions']=[];request['engine']['worker_path']=str(paths['worker'])
    request.pop('research_capture',None)
    request['probe_only']=False
    require(request.get('protocol_version')==2 and request.get('scenario') is None and request.get('interruption') is None and request.get('first_turn') is None,'standard_protocol_v2_required')
    banlist=regular_file(base[0]['banlist_path']);strict_json(banlist.read_bytes());protected[banlist]=sha(banlist)
    validate_sources(case,request,banlist)
    runtime=identity['runtimes']['ordinary'];require(runtime['roles']['worker']['sha256']==hashes['worker'],'worker_identity_mismatch')
    for role,key in (('dll','engine_sha256'),('cdb','cdb_sha256'),('script_manifest','scripts_sha256')):
        require(runtime['roles'][role]['sha256']==case['assets'][key],'runtime_asset_mismatch')
    static_hashes={path.relative_to(repo).as_posix():value for path,value in protected.items() if path.is_relative_to(repo/'data/tmp/ocgcore-source') or path.relative_to(repo).as_posix() in ('crates/ygo-engine-adapter/src/worker.rs','crates/ygo-engine-adapter/src/codec.rs')}
    manifest={'static_source_sha256':static_hashes,'schema_version':1,'kind':'native_prompt_probe_manifest','scope':SCOPE,'limit':6,'planned_calls':6,'old_consumed':24,'window_seconds':7200,'started_at':window['started_at'],'source_identity':source['identity'],'input_sha256':hashes,'baseline_acceptance_sha256':ACCEPTANCE_SHA,'preparation_sha256':sha(preparation/'prepared-cases.json'),'stage1_request_sha256':digest(canonical(request)),'derivation_rules':{'2':'stage1_unique_tenki_activation','3':'stage2_yes_no_false','4':'exact_stage3_replay','5':'stage2_yes_no_true_stop_pending15','6':'exact_stage5_replay'},**FLAGS}
    manifest['context']=digest(canonical(manifest));output.mkdir(parents=True,exist_ok=True);immutable_write(output/'manifest.json',manifest)
    def unchanged():
        require(stable_source(repo)==source and all(sha(path)==hashes[key] for key,path in paths.items()) and all(sha(path)==value for path,value in protected.items()),'frozen_input_changed')
    unchanged()
    return run_stages(paths['runner'],output,manifest,request,runtime,unchanged,args.prepare_only)
