"""Frozen shuffle/end route audit using only an independent snapshot evaluator."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess

from ygo_data.identity import canonical, checked_output, regular_file, stable_source
from ygo_eval.information_audit import strict_json, hashed, validate_contract as validate_parent
from ygo_eval.information_projection import check_policy_samples
from ygo_eval.snapshot_eval import run_runner

PINS = {
 'parent-acceptance':'cac76781c455854c8629cd47afed69ef090a8e4b7cd05f75e96afdeddb425a0a',
 'parent-contract':'78d7ea65c136f0c7a33c827b77308af7b900d302f442208ebff4a993bac92dee',
 'terminal-shuffle-end':'3b391ca175f00910570fde0542a95970c028bc85b7c6623fee01d4d71e428dc7',
 'frozen-input':'de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879',
 'source-request':'0831cf62ec6587625543e946658be21c58b2aab30d73aedf1d3249597b2353f7',
 'core-processor':'d051d6a006baa9ad4a590d4bcc185bff112e3ed7df256ff25cd8c0ff7beaf085',
 'core-constants':'191315f0c37bdc2fc086dee457bfc8ebb10b27cb1f063d26d5776465f9dbc4aa'}
ORIGINS = {r:('historical_native','projection') if r == 'terminal-shuffle-end' else ('static_source','static') if r.startswith('core-') else ('parent_audit','parent') if r == 'parent-acceptance' else ('parent_contract','parent') if r == 'parent-contract' else ('frozen_input','source') for r in PINS}
RUNNER_PIN = 'f5d94b180304b2198b1b2e6b1a32bfb0e4d43b3016ae6eb72b3748c529955b13'
CDB_PIN = 'c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225'
FLAGS = ('proof_ready','complete_action_coverage','global_optimality','native_probability_verified')


def validate_contract(value):
    fields = {'schema_version','kind','study_id','observation_profile','seed_role','frozen_input','public','evidence','fixed_actions',*FLAGS}
    if not isinstance(value,dict) or set(value) != fields or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('invalid_route_contract')
    if (value['kind'],value['study_id'],value['observation_profile'],value['seed_role']) != ('information-route-study','rabbit-shuffle-end-information-v1','rabbit-shuffle-end-observation-v1','reproduction_only') or any(value[k] is not False for k in FLAGS):
        raise ValueError('invalid_route_profile')
    if value['fixed_actions'] != [8,7] or any(type(n) is not int for n in value['fixed_actions']):
        raise ValueError('invalid_fixed_actions')
    evidence = value['evidence']
    if not isinstance(evidence,list) or len(evidence) != len(PINS): raise ValueError('invalid_role_set')
    seen = set()
    for item in evidence:
        if not isinstance(item,dict) or set(item) != {'role','sha256','category','scope'}: raise ValueError('invalid_source_fields')
        role = item['role']
        if not isinstance(role,str) or role in seen or role not in PINS or item['sha256'] != PINS[role] or (item['category'],item['scope']) != ORIGINS[role]: raise ValueError('unregistered_route_source')
        seen.add(role)
    return value


def validate_evaluations(core, count):
    if not isinstance(core,dict) or set(core) != {'evaluations'} or not isinstance(core['evaluations'],list) or len(core['evaluations']) != count: raise ValueError('invalid_evaluator_envelope')
    for item in core['evaluations']:
        if not isinstance(item,dict) or set(item) != {'binding_valid','snapshot_count','utility','termination','diagnostics'}: raise ValueError('invalid_evaluator_fields')
        if item['binding_valid'] is not True or item['termination'] != 'terminal_boundary_bound' or type(item['snapshot_count']) is not int or item['snapshot_count'] != 0 or type(item['utility']) is not int or item['utility'] != 0 or item['diagnostics'] != []: raise ValueError('terminal_binding_not_verified')
    return core['evaluations']


def validate_queries(run):
    terminal = run['terminal_observation']
    queries = terminal['queries']
    if type(terminal['capture_query_count']) is not int or terminal['capture_query_count'] != 14 or not isinstance(queries,list) or len(queries) != 14: raise ValueError('fourteen_queries_required')
    expected = {(player,4,slot) for player in (0,1) for slot in range(7)}
    actual = set()
    for query in queries:
        if set(query) != {'controller','location','sequence','flags','raw','sha256','error'} or any(type(query[k]) is not int for k in ('controller','location','sequence','flags')): raise ValueError('invalid_query_fields')
        coordinate = (query['controller'],query['location'],query['sequence'])
        if coordinate in actual or coordinate not in expected or query['flags'] != 11 or query['error'] is not None or query['raw'] != [] or query['sha256'] != hashed(b''): raise ValueError('query_coordinate_or_empty_binding_invalid')
        actual.add(coordinate)
    if actual != expected: raise ValueError('incomplete_query_coordinates')


def audit_information_route(contract_path, samples_path, evidence, cdb, runner, output, repo=None):
    from ygo_eval.information_route_projection import project_route
    repo = Path(repo or Path(__file__).resolve().parents[2])
    output = checked_output(repo,output)
    if output.exists(): raise ValueError('output_exists')
    paths = {'contract':regular_file(contract_path),'samples':regular_file(samples_path),'cdb':regular_file(cdb),'runner':regular_file(runner)}
    for argument in evidence:
        role, separator, path = argument.partition('=')
        if not separator or not role or role in paths: raise ValueError('duplicate_or_invalid_role')
        paths[role] = regular_file(path)
    if output in paths.values(): raise ValueError('output_overlaps_input')
    raw = {role:path.read_bytes() for role,path in paths.items()}
    hashes = {role:hashed(data) for role,data in raw.items()}
    source = stable_source(repo)
    report = {'schema_version':1,'kind':'information-route-audit','successful':False,'native_calls':0,**{key:False for key in FLAGS},'inputs':hashes,'tool_source_identity':source['identity'],'sources':[],'observations':{},'scope_gaps':[],'policy':None,'terminal_evaluations':[],'route_audits':[],'out_of_scope':['rabbit-full','tournament-full'],'historical_reexecution_performed':False,'new_native_replay_verified':False,'layers':{'provenance':False,'route':False,'binding':False,'policy':False},'diagnostics':[]}
    try:
        contract = validate_contract(strict_json(raw['contract']))
        if set(paths) != {'contract','samples','cdb','runner',*PINS}: raise ValueError('evidence_set_mismatch')
        if any(hashes[role] != pin for role,pin in PINS.items()) or hashes['cdb'] != CDB_PIN or hashes['runner'] != RUNNER_PIN: raise ValueError('frozen_hash_mismatch')
        report['sources'] = contract['evidence']
        parent = validate_parent(strict_json(raw['parent-contract']))
        acceptance = strict_json(raw['parent-acceptance'])
        if acceptance.get('tools_verified') is not True or acceptance.get('observation_profile_verified') is not True or acceptance.get('policy_samples_consistent') is not True or acceptance.get('evidence',{}).get('contract.json',{}).get('sha256') != PINS['parent-contract']: raise ValueError('parent_acceptance_not_bound')
        if contract['public'] != parent['public'] or contract['frozen_input'] != parent['frozen_input']: raise ValueError('parent_declaration_mismatch')
        frozen = strict_json(raw['frozen-input'])['cases'][0]
        if hashed(canonical(frozen['case'])) != contract['frozen_input']['case_sha256'] or hashed(canonical(frozen['request'])) != contract['frozen_input']['request_sha256']: raise ValueError('frozen_case_mismatch')
        if frozen['case']['rules'] != contract['frozen_input']['rules'] or frozen['case']['assets'] != contract['frozen_input']['assets']: raise ValueError('frozen_rules_assets_mismatch')
        native = strict_json(raw['terminal-shuffle-end'])
        original = strict_json(raw['source-request'])
        if set(original) != {'input','request_sha256'} or original['input']['request'] != native['request'] or original['request_sha256'] != hashed(canonical(native['request'])): raise ValueError('source_request_mismatch')
        composition = {zone:dict(Counter(map(str,codes))) for zone,codes in frozen['request']['deck'].items()}
        if composition != contract['public']['known_deck_composition']: raise ValueError('declared_composition_mismatch')
        request = native['request']
        for field in ('deck','opening_hand','seed','versions','protocol_version'):
            if request[field] != frozen['request'][field]: raise ValueError('frozen_request_mismatch')
        if any(request['engine'][key] != frozen['request']['engine'][key] for key in ('ocgcore_path','catalog_path','script_manifest_path','timeout_ms')): raise ValueError('frozen_engine_assets_mismatch')
        if request['versions']['cdb_sha256'] != hashes['cdb'] or not isinstance(request['decisions'],list) or len(request['decisions']) != 2 or any(not isinstance(item,dict) or set(item) != {'choice','player','prompt_id'} or type(item['player']) is not int or item['player'] != 0 or type(item['prompt_id']) is not int or item['choice'] != {'command':command,'index':0,'kind':'command'} or any(type(item['choice'][key]) is not int for key in ('command','index')) for item,command in zip(request['decisions'],(8,7))): raise ValueError('request_route_mismatch')
        runs = native['runs']
        if not isinstance(runs,list) or len(runs) != 2 or any(not isinstance(run,dict) or set(run) != {'Ok'} for run in runs): raise ValueError('two_successful_runs_required')
        report['layers']['provenance'] = True
        projected = []
        for index,record in enumerate(runs):
            run = record['Ok']
            if run['protocol_version'] != request['protocol_version'] or type(run['protocol_version']) is not int or run['versions'] != request['versions']: raise ValueError('run_version_mismatch')
            result = project_route(run['events'],contract['public'],request['decisions'],run['resolved_decisions'])
            projected.append(result)
            report['route_audits'].append({'run_index':index,'private_audit':result['private_audit'],'route_complete':result['route_complete'],'terminal_bound':result['terminal_bound']})
            for number,observation in enumerate(result['views']): report['observations'][f'terminal-shuffle-end/run{index}/view{number}'] = dict(observation,provenance={'role':'terminal-shuffle-end','category':'historical_native'})
            report['scope_gaps'].extend(dict(gap,run=index) for gap in result['gaps'])
        report['layers']['route'] = all(item['route_complete'] for item in projected)
        if not report['layers']['route']: raise ValueError('route_projection_incomplete')
        for record in runs: validate_queries(record['Ok'])
        with closing(sqlite3.connect(paths['cdb'].as_uri()+'?mode=ro',uri=True)) as database:
            catalog = {}
            for code,kind in database.execute('SELECT id,type FROM datas'):
                if type(code) is not int or type(kind) is not int or not 0 < code <= 0xffffffff or not 0 <= kind <= 0xffffffff or str(code) in catalog: raise ValueError('invalid_catalog_types')
                catalog[str(code)] = kind
        evaluations = validate_evaluations(run_runner(paths['runner'],{'schema_version':2,'own_player':0,'request':request,'runs':runs,'catalog_types':catalog}),2)
        report['terminal_evaluations'] = evaluations
        report['layers']['binding'] = True
        report['observations'] = {}
        report['scope_gaps'] = [gap for gap in report['scope_gaps'] if gap.get('reason') != 'terminal_evaluation_unbound']
        for index,(record,evaluation) in enumerate(zip(runs,evaluations)):
            result = project_route(record['Ok']['events'],contract['public'],request['decisions'],record['Ok']['resolved_decisions'],terminal_evaluation=dict(evaluation,count=evaluation['snapshot_count']))
            report['route_audits'][index].update(private_audit=result['private_audit'],terminal_bound=result['terminal_bound'])
            if not result['route_complete'] or not result['terminal_bound']: raise ValueError('route_terminal_projection_unbound')
            for number,observation in enumerate(result['views']): report['observations'][f'terminal-shuffle-end/run{index}/view{number}'] = dict(observation,provenance={'role':'terminal-shuffle-end','category':'historical_native'})
        samples = strict_json(raw['samples'])
        if not isinstance(samples,dict) or set(samples) != {'schema_version','kind','samples'} or type(samples['schema_version']) is not int or samples['schema_version'] != 1 or samples['kind'] != 'information-policy-samples' or not isinstance(samples['samples'],list) or not samples['samples']: raise ValueError('invalid_samples_contract')
        for sample in samples['samples']:
            if not isinstance(sample,dict) or set(sample) != {'policy_id','observation_id','distribution'} or not isinstance(sample['distribution'],list): raise ValueError('invalid_policy_sample')
            if report['observations'].get(sample['observation_id'],{}).get('kind') != 'decision': raise ValueError('terminal_policy_sample_forbidden')
            if any(not isinstance(item,dict) or set(item) != {'bytes','numerator','denominator'} for item in sample['distribution']): raise ValueError('invalid_distribution_fields')
        report['policy'] = check_policy_samples(samples['samples'],report['observations'])
        report['layers']['policy'] = report['policy']['valid']
        report['successful'] = all(report['layers'].values()) and len(report['observations']) == 6 and sum(o['kind'] == 'terminal' for o in report['observations'].values()) == 2
    except (ValueError,OSError,KeyError,TypeError,IndexError,AttributeError,OverflowError,subprocess.SubprocessError,sqlite3.Error) as error:
        reason = str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'route_audit_input_or_binding_invalid'
        report['diagnostics'].append({'reason':reason})
    try:
        changed = stable_source(repo) != source or any(hashed(regular_file(path).read_bytes()) != hashes[role] for role,path in paths.items())
    except (ValueError,OSError): changed = True
    if changed:
        report['successful'] = False
        report['layers'] = {key:False for key in report['layers']}
        report['terminal_evaluations'] = []
        for item in report['route_audits']: item.update(route_complete=False,terminal_bound=False)
        for observation in report['observations'].values():
            if observation.get('kind') == 'terminal':
                observation['view'].update(normal_count=None,normal_utility=None,termination='unknown')
                observation['observation_key'] = hashed(canonical(observation['view']))
        report['diagnostics'].append({'reason':'input_or_source_changed_during_capture'})
    output = checked_output(repo,output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output = checked_output(repo,output)
    with output.open('xb') as stream: stream.write(json.dumps(report,ensure_ascii=False,indent=2).encode())
    return report
