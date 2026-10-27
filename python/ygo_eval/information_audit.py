"""Read-only, bounded information-study orchestration; never opens an engine or journal."""
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from ygo_data.identity import canonical, checked_output, regular_file, stable_source

STATIC_PINS = {'core-field':'9b6aa4916a8e2f7e95cab570be886e22751c197b320f15acdf1fa7de3c5dadfd','core-random':'5c40deecee0047b5d2ba51031dd545eb89374ff5194c10a893bbc9c07fe257c1','core-menu':'a9ff2c499476f70afb4afa9d3880a0070bcd54f4baf9f116cd9e79f7107c9e97'}
PINS = {
 'rabbit-empty':'3d05204902a41a6cf6e1c285dcfcda829eed46fc998a6a34307eabc7cdc86362',
 'rabbit-shuffle':'37b4027a6e670cf9a01e2462899a42acaa1fceabbda9dea04facb78e845a530a',
 'terminal-shuffle-end':'3b391ca175f00910570fde0542a95970c028bc85b7c6623fee01d4d71e428dc7',
 'rabbit-full':'1f40071c55e16a346d26e0aa51fc829e8c75a5eefede064b7cfe76e76310be97',
 'tournament-full':'6eb9199124e344356af387c31f83e2955187b0dff1919a4847923258cd9ea059',
}


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    def bad(value):
        raise ValueError('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def validate_origin(item):
    category = item.get('category')
    if item.get('role') in PINS and category != 'historical_native':
        raise ValueError('historical_role_category_mismatch')
    if item.get('role') in STATIC_PINS and category != 'static_source':
        raise ValueError('static_role_category_mismatch')
    if item.get('role') == 'frozen-input' and category != 'frozen_input':
        raise ValueError('frozen_role_category_mismatch')
    if category == 'historical_native':
        if PINS.get(item['role']) != item['sha256']:
            raise ValueError('unregistered_historical_source')
    elif category == 'frozen_input':
        if item['role'] != 'frozen-input' or item['sha256'] != 'de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879':
            raise ValueError('unregistered_frozen_source')
    elif category == 'static_source':
        if STATIC_PINS.get(item['role']) != item['sha256']: raise ValueError('unregistered_static_source')
    elif category != 'synthetic':
        raise ValueError('unsupported_source_category')
    if item.get('scope') not in ('projection', 'inventory', 'source', 'static'):
        raise ValueError('unsupported_evidence_scope')


def validate_contract(value):
    required = {'schema_version','kind','study_id','observation_profile','frozen_input','public','evidence','static_sources','seed_role','proof_ready','complete_action_coverage','global_optimality'}
    if set(value) != required or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['study_id'] != 'rabbit-idle-information-v1' or value['kind'] != 'information-study' or value['observation_profile'] != 'rabbit-idle-observation-v1':
        raise ValueError('unsupported_information_contract')
    if value['seed_role'] != 'reproduction_only' or any(value[k] is not False for k in ('proof_ready','complete_action_coverage','global_optimality')):
        raise ValueError('unsupported_qualification')
    public = value['public']
    if set(public) != {'rules','objective','known_deck_composition','initial_public_state'}:
        raise ValueError('unsupported_public_declaration')
    # The contract is a declaration, never a vehicle for private routing/state.
    def inspect(obj):
        if isinstance(obj,dict):
            for key, item in obj.items():
                if any(word in key.lower() for word in ('seed','hash','checkpoint','instance','buffer','prompt_id','deck_order','source')):
                    raise ValueError('private_public_declaration')
                inspect(item)
        elif isinstance(obj,list):
            for item in obj: inspect(item)
    inspect(public)
    if not value['evidence'] or len({x['role'] for x in value['evidence']}) != len(value['evidence']):
        raise ValueError('missing_or_duplicate_sources')
    for item in value['evidence']: validate_origin(item)
    if not any(x['category'] == 'frozen_input' and x['scope'] == 'source' for x in value['evidence']):
        raise ValueError('missing_frozen_source')
    for key in ('case_sha256','request_sha256','frozen_source_sha256','rules','assets'):
        if key not in value['frozen_input']: raise ValueError('missing_frozen_input')
    if public['rules'] != {k:value['frozen_input']['rules'][k] for k in ('region','version')}:
        raise ValueError('rules_binding_mismatch')
    if public['objective'] != {'id':'rabbit-own-face-up-xyz-v1','normal_min':0,'normal_max':7,'early_win':8,'loss':-2,'draw':-1,'boundary':'first-next-turn-process-return-v1'}:
        raise ValueError('objective_binding_mismatch')
    if public['initial_public_state'] != {'own_player':0,'lp':[8000,8000],'turn':1,'turn_player':0,'own_hand_count':5,'opponent_hand_count':0,'empty_field':True,'opponent_deck_model':'copy-own-main'}:
        raise ValueError('unsupported_initial_public_state')
    for item in value['evidence']:
        expected = ('source' if item['role'] == 'frozen-input' else 'static' if item['role'] in STATIC_PINS else 'inventory' if item['role'] in ('rabbit-full','tournament-full') else 'projection')
        if item['scope'] != expected: raise ValueError('source_scope_mismatch')
    if not set(STATIC_PINS).issubset({x['role'] for x in value['evidence']}):
        raise ValueError('missing_static_sources')
    if not set(PINS).issubset({x['role'] for x in value['evidence']}):
        raise ValueError('missing_historical_corpus')
    if value['static_sources'] != [{'role':r,'sha256':h,'commit':'38d04c9feb1a26617407091380634c87262fe3f8'} for r,h in STATIC_PINS.items()]:
        raise ValueError('static_registry_mismatch')
    return value


def _runs(report):
    runs = report.get('runs')
    if not isinstance(runs,list): raise ValueError('missing_runs')
    return runs


def audit_information(contract_path, samples_path, evidence, output, repo=None):
    from ygo_eval.information_projection import project_prefix, check_policy_samples
    from ygo_eval.information_math import audit_probability, audit_ordering, validate_probability_report, validate_ordering_report
    repo = Path(repo or Path(__file__).resolve().parents[2])
    output = checked_output(repo,output)
    if output.exists(): raise ValueError('output_exists')
    paths = {'contract':regular_file(contract_path),'samples':regular_file(samples_path)}
    for arg in evidence:
        role, separator, name = arg.partition('=')
        if not separator or not role or role in paths: raise ValueError('duplicate_or_invalid_role')
        paths[role] = regular_file(name)
    if output in paths.values(): raise ValueError('output_overlaps_source')
    started = time.monotonic()
    source = stable_source(repo)
    raw = {role:path.read_bytes() for role,path in paths.items()}
    hashes = {role:hashed(data) for role,data in raw.items()}
    report = {'schema_version':1,'kind':'information-audit','successful':False,'native_calls':0,
              'proof_ready':False,'complete_action_coverage':False,'global_optimality':False,
              'native_probability_verified':False,'inputs':hashes,'tool_source_identity':source['identity'],
              'observations':{},'scope_gaps':[],'policy':None,'probability':None,'ordering':None,
              'layers':{'tool':False,'observation_profile':False,'policy_samples':False,'ideal_probability':False,'history_range_complete':False},'sources':[],'diagnostics':[],'elapsed_seconds':0,'input_bytes':sum(map(len,raw.values()))}
    try:
        contract = validate_contract(strict_json(raw['contract']))
        samples = strict_json(raw['samples'])
        if set(samples) != {'schema_version','kind','samples'} or type(samples['schema_version']) is not int or samples['schema_version'] != 1 or samples['kind'] != 'information-policy-samples':
            raise ValueError('invalid_samples_contract')
        if not samples['samples']: raise ValueError('empty_policy_samples')
        if any(set(x) != {'policy_id','observation_id','distribution'} for x in samples['samples']):
            raise ValueError('unsupported_policy_sample_fields')
        declared = {x['role']:x for x in contract['evidence']}
        report['sources'] = contract['evidence']
        profile_valid = True
        frozen = strict_json(raw['frozen-input'])['cases'][0]
        if set(paths) - {'contract','samples'} != set(declared): raise ValueError('evidence_set_mismatch')
        for role,item in declared.items():
            if hashes[role] != item['sha256']: raise ValueError('evidence_hash_mismatch')
            if item['scope'] == 'static': continue
            value = strict_json(raw[role])
            if item['scope'] == 'source':
                frozen = value['cases'][0]
                if hashed(raw[role]) != contract['frozen_input']['frozen_source_sha256'] or hashed(canonical(frozen['case'])) != contract['frozen_input']['case_sha256'] or hashed(canonical(frozen['request'])) != contract['frozen_input']['request_sha256']:
                    raise ValueError('frozen_source_binding_mismatch')
                composition = {zone:dict(Counter(map(str,codes))) for zone,codes in frozen['request']['deck'].items()}
                if composition != contract['public']['known_deck_composition']:
                    raise ValueError('declared_composition_mismatch')
                if frozen['case']['rules'] != contract['frozen_input']['rules'] or frozen['case']['assets'] != contract['frozen_input']['assets']:
                    raise ValueError('frozen_rules_assets_mismatch')
                continue
            if item['scope'] == 'inventory':
                report['scope_gaps'].append({'role':role,'reason':'full_route_outside_observation_profile'})
                continue
            for index,run in enumerate(_runs(value)):
                if set(run) != {'Ok'}: raise ValueError('failed_execution_not_observation')
                if role in ('rabbit-empty','rabbit-shuffle'):
                    checkpoint = run['Ok']['checkpoint']
                    cards = checkpoint['cards']
                    if checkpoint['lp'] != [8000,8000] or any(c['location'] in (4,8) or (c['player'] == 1 and c['location'] == 2) for c in cards):
                        raise ValueError('initial_public_state_contradicted')
                result = project_prefix(run['Ok']['events'],contract['public'])
                if any(len(x['view']['own_hand']) != 5 for x in result['views']):
                    raise ValueError('own_hand_count_mismatch')
                expected_views = 1 if role == 'rabbit-empty' else 2
                if len(result['views']) != expected_views: profile_valid = False
                if result['views'] and Counter(x['code'] for x in result['views'][0]['view']['own_hand']) != Counter(frozen['request']['opening_hand']):
                    raise ValueError('opening_hand_mismatch')
                for number,observation in enumerate(result['views']):
                    name = f'{role}/run{index}/view{number}'
                    report['observations'][name] = dict(observation, provenance={'role':role,'category':item['category']})
                report['scope_gaps'].extend(dict(gap,role=role,run=index) for gap in result['gaps'])
        report['policy'] = check_policy_samples(samples['samples'],report['observations'])
        report['probability'] = audit_probability()
        report['ordering'] = audit_ordering()
        validate_probability_report(report['probability'])
        validate_ordering_report(report['ordering'])
        report['layers'] = {'tool':True,'observation_profile':profile_valid,'policy_samples':report['policy']['valid'],'ideal_probability':True,'history_range_complete':False}
        report['successful'] = bool(report['observations']) and profile_valid and report['policy']['valid']
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,OverflowError) as error:
        report['diagnostics'].append({'reason':str(error) if str(error).replace('_','').isalnum() else 'invalid_input_structure'})
    try:
        changed = any(not path.exists() or hashed(regular_file(path).read_bytes()) != hashes[role] for role,path in paths.items()) or stable_source(repo) != source
    except (ValueError,OSError):
        changed = True
    if changed:
        report['layers'] = {key:False for key in report['layers']}
        report['successful'] = False
        report['diagnostics'].append({'reason':'input_or_source_changed_during_capture'})
    report['elapsed_seconds'] = round(time.monotonic()-started,6)
    with output.open('xb') as stream:
        stream.write(json.dumps(report,ensure_ascii=False,indent=2).encode())
    return report
