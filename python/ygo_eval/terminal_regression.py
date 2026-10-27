"""Frozen three-pair terminal regression; preparation never starts a worker."""
import copy
import json
import subprocess
from pathlib import Path

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source

CASE_IDS = ['terminal-rabbit', 'terminal-tournament', 'terminal-shuffle-end']
PREVIOUS_LEDGER_SHA = '0e50a03837676b8b19a1409b9ffa06bc7798ff61254109c10025c7733a3c410b'
OLD_LEDGER_SHA = 'b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a'


def immutable_write(path, value):
    """An identical durable intent may be resumed; different bytes never replace it."""
    encoded = canonical(value)
    if path.exists():
        if regular_file(path).read_bytes() != encoded:
            raise ValueError('immutable intent already differs')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        import os
        os.fsync(stream.fileno())


def derive_request(request, result, command):
    """Use only the actual recorded own-player public idle menu."""
    prompt = result.get('prompt')
    if not isinstance(prompt, dict) or prompt.get('opcode') != 11 or prompt.get('player') != 0:
        raise ValueError('own public idle prompt required')
    matching = [f for f in result.get('events', []) if f.get('sequence') == prompt.get('id')
                and f.get('opcode') == 11 and f.get('fields', {}).get('prompt') == prompt]
    if len(matching) != 1 or matching[0].get('raw', [])[:2] != [11,0] or command not in (6,7,8) or len(matching[0]['raw']) < 29 or not matching[0]['raw'][-3 + command - 6]:
        raise ValueError('prompt not bound to actual enabled raw idle menu')
    choice = {'kind': 'command', 'command': command, 'index': 0}
    matches = [a for a in prompt.get('actions', []) if a.get('choice') == choice]
    if len(matches) != 1 or matches[0].get('bytes') != [command, 0, 0, 0]:
        raise ValueError('requested command absent or response corrupted')
    derived = copy.deepcopy(request)
    derived['decisions'].append({'prompt_id': prompt['id'], 'player': 0, 'choice': choice})
    return derived


def add_arguments(parser):
    for name in ('cases', 'runner', 'worker', 'build-record', 'identity', 'old-ledger', 'previous-ledger', 'parent-input', 'parent-evidence', 'parent-runner', 'window-start', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')


def _sha(path): return digest(regular_file(path).read_bytes())


def verified_parent(paths, hashes):
    """Verify the immutable prior receipt without invoking a worker."""
    parent_input = json.loads(paths['parent_input'].read_bytes())
    parent = json.loads(paths['parent_evidence'].read_bytes())
    if Path(parent_input['output']).absolute() != paths['parent_evidence'] or Path(parent_input['ledger']).absolute() != paths['previous_ledger'] or parent_input['case_id'] != 'rabbit-shuffle':
        raise ValueError('parent evidence/ledger binding differs')
    verified = subprocess.run([str(paths['parent_runner']), str(paths['parent_input']), '--input-sha', hashes['parent_input'], '--verify-recorded'], capture_output=True, timeout=60)
    if verified.returncode != 0: raise ValueError('parent receipt verification failed')
    old_stats = json.loads(verified.stdout)['ledger']
    if old_stats['consumed'] != 8 or old_stats['unknown'] or old_stats['reserved']: raise ValueError('prior eight-call ledger inconsistent')
    if parent.get('independent_replay_matches') is not True or parent.get('assets_unchanged') is not True or len(parent['runs']) != 2:
        raise ValueError('parent replay or assets unverified')
    derived = derive_request(parent['request'], parent['runs'][0]['Ok'], 7)
    if derived['decisions'][-1]['prompt_id'] != 9: raise ValueError('frozen parent prompt differs')
    return parent, derived


def terminal_regression(args):
    """Prepare or resume exactly the three approved pairs, stopping at first failure."""
    from ygo_eval.research import validate_sources
    repo = Path(__file__).resolve().parents[2]
    output = checked_output(repo, args.output)
    if 'research' not in output.relative_to(repo / 'data' / 'runtime').parts:
        raise ValueError('dedicated research output required')
    paths = {name: regular_file(getattr(args,name).absolute()) for name in
             ('cases','runner','worker','build_record','identity','old_ledger','previous_ledger','parent_input','parent_evidence','parent_runner','window_start')}
    if any(p == output or p.is_relative_to(output) or output.is_relative_to(p) for p in paths.values()):
        raise ValueError('output overlaps frozen input')
    hashes = {name:_sha(path) for name,path in paths.items()}
    if hashes['old_ledger'] != OLD_LEDGER_SHA or hashes['previous_ledger'] != PREVIOUS_LEDGER_SHA: raise ValueError('historical ledger changed')
    source = stable_source(repo)
    build = json.loads(paths['build_record'].read_bytes())
    identities = json.loads(paths['identity'].read_bytes())
    window = json.loads(paths['window_start'].read_bytes())
    import time
    if window.get('schema_version') != 1 or window.get('kind') != 'terminal_regression_window_start' or type(window.get('started_at')) is not int or not 0 <= window['started_at'] <= int(time.time()):
        raise ValueError('invalid immutable experiment window start')
    if build.get('status') != 'recorded' or build.get('source_before') != source or build.get('source_after') != source:
        raise ValueError('build is not bound to frozen current source')
    if not all(hashes[role] in build.get('artifacts', {}).values() for role in ('runner','worker')):
        raise ValueError('runner or worker not in build record')
    if identities.get('source') != source or identities.get('consistent') is not True:
        raise ValueError('candidate identity source differs')
    frozen = json.loads(paths['cases'].read_bytes())
    templates = {}
    for item in frozen['cases']:
        case_id = item['case']['case_id']
        if case_id not in ('rabbit','tournament'): continue
        validate_sources(item['case'], item['request'], Path(item['banlist_path']))
        request = copy.deepcopy(item['request']); request['engine']['worker_path'] = str(paths['worker'])
        role = 'ordinary' if case_id == 'rabbit' else 'tournament'
        runtime = identities['runtimes'][role]
        if runtime['roles']['worker']['sha256'] != hashes['worker']: raise ValueError('candidate worker differs')
        for asset, version in [('dll','engine_sha256'),('cdb','cdb_sha256'),('script_manifest','scripts_sha256')]:
            if runtime['roles'][asset]['sha256'] != request['versions'][version]: raise ValueError('candidate asset versions differ')
        templates[case_id] = request
    if set(templates) != {'rabbit','tournament'}: raise ValueError('Rabbit and tournament templates required')
    parent, derived = verified_parent(paths, hashes)
    original = copy.deepcopy(templates['rabbit'])
    recorded = copy.deepcopy(parent['request'])
    original['engine']['worker_path'] = recorded['engine']['worker_path']
    original['decisions'] = recorded['decisions']
    if original != recorded or len(recorded['decisions']) != 1 or recorded['decisions'][0]['choice'] != {'kind':'command','command':8,'index':0}:
        raise ValueError('parent is not the frozen Rabbit shuffle prefix')
    derived['engine']['worker_path'] = str(paths['worker'])
    templates['shuffle'] = derived
    for request in templates.values(): request['research_capture'] = {'schema_version':1,'objective':'rabbit-own-face-up-xyz-v1','boundary':'first-next-turn-process-return-v1'}
    manifest = {'schema_version':1,'kind':'terminal_regression_manifest', 'source_identity':source['identity'],
        'output_relative':output.relative_to(repo).as_posix(), 'input_sha256':hashes,
        'old_consumed':17,'limit':6,'planned_calls':6,'window_seconds':7200,'started_at':window['started_at'],
        'case_ids':CASE_IDS, 'templates':templates,'runtimes':identities['runtimes'],
        'parent':{'evidence_sha256':hashes['parent_evidence'],'input_sha256':hashes['parent_input'],
                  'public_prompt_sha256':digest(canonical(parent['runs'][0]['Ok']['prompt'])), 'prompt_id':9,
                  'choice':derived['decisions'][-1]['choice']},
        'allowed_derivations':['terminal-shuffle-end:verified_parent_public_command7'],
        'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
    manifest['context'] = digest(canonical(manifest))
    # One approved time-window file binds one output scope, including reopen.
    window_binding = checked_output(repo, paths['window_start'].with_suffix('.binding.json'))
    immutable_write(window_binding, {'context':manifest['context'],'output_relative':manifest['output_relative']})
    output.mkdir(parents=True, exist_ok=True)
    immutable_write(checked_output(repo, output/'manifest.json'),manifest)
    if args.prepare_only: return {'prepared':True,'planned_calls':6,'native_calls':0}
    ledger = checked_output(repo, output/'calls.jsonl')
    summaries = []; stopped = None; current_stats = None
    def frozen_inputs():
        if stable_source(repo) != source or any(_sha(p) != hashes[n] for n,p in paths.items()):
            raise ValueError('frozen source, build, or input changed')
    for case_id in CASE_IDS:
        frozen_inputs()
        role = 'tournament' if case_id == 'terminal-tournament' else 'ordinary'
        key = {'terminal-rabbit':'rabbit','terminal-tournament':'tournament','terminal-shuffle-end':'shuffle'}[case_id]
        request = templates[key]
        derivation = manifest['parent'] if key == 'shuffle' else None
        import sqlite3
        cdb = regular_file(Path(request['engine']['catalog_path']).absolute())
        with sqlite3.connect(cdb.as_uri()+'?mode=ro', uri=True) as conn:
            catalog_types = {str(code):kind for code,kind in conn.execute('select id,type from datas')}
        intent = {'context':manifest['context'],'ledger':str(ledger),'output':str(output/(case_id+'.json')),
                  'case_id':case_id,'request':request,'expected_identity':identities['runtimes'][role],
                  'started_at':window['started_at'],'catalog_types':catalog_types,
                  'expected_count':1 if case_id == 'terminal-rabbit' else 0}
        immutable_write(checked_output(repo, output/(case_id+'-request.json')), {'request_sha256':digest(canonical(request)), 'derivation':derivation,'input':intent})
        invocation = checked_output(repo, output/(case_id+'-input.json')); immutable_write(invocation,intent)
        invocation_hash = _sha(invocation)
        pair_path = checked_output(repo, output/(case_id+'.json'))
        if pair_path.exists():
            verified = subprocess.run([str(paths['runner']),str(invocation),'--input-sha',invocation_hash,'--verify-recorded'],capture_output=True,timeout=60)
            if verified.returncode != 0: raise ValueError('recorded evidence differs from journal or recomputed audit')
            current_stats = json.loads(verified.stdout)['ledger']
        else:
            completed = subprocess.run([str(paths['runner']),str(invocation),'--input-sha',invocation_hash],capture_output=True,timeout=7200)
            if completed.returncode not in (0,1) or not pair_path.exists():
                stats_result = subprocess.run([str(paths['runner']),str(invocation),'--input-sha',invocation_hash,'--stats'],capture_output=True,timeout=60)
                current_stats = json.loads(stats_result.stdout)['ledger'] if stats_result.returncode == 0 else None
                stopped = 'runner_failed_or_outcome_unavailable'; break
            current_stats = json.loads(completed.stdout)['ledger']
        if _sha(invocation) != invocation_hash: raise ValueError('invocation changed during execution')
        pair = json.loads(regular_file(pair_path).read_bytes())
        if pair.get('context') != manifest['context'] or pair.get('request') != request or pair.get('case_id') != case_id:
            raise ValueError('recorded pair binding differs')
        status = pair.get('diagnostic')
        if current_stats['unknown'] or current_stats['reserved']: status = 'unresolved_consumption'
        if not status:
            if pair.get('assets_unchanged') is not True or pair.get('independent_replay_matches') is not True:
                status = 'pair_verification_failed'
            else:
                try:
                    for run in pair['runs']:
                        if set(run) != {'Ok'} or run['Ok'].get('error') is not None: raise ValueError('failed outcome')
                        if run['Ok'].get('resolved_decisions') != request['decisions']: raise ValueError('frozen decisions not fully consumed')
                    for audit in pair['terminal_audits']:
                        if audit.get('binding_valid') is not True or audit.get('utility') != intent['expected_count']:
                            raise ValueError('terminal binding or utility differs')
                except (ValueError,KeyError,TypeError): status = 'group_observation_failed'
        summaries.append({'case_id':case_id,'evidence_sha256':_sha(pair_path),'diagnostic':status,'ledger':pair['ledger']})
        frozen_inputs()
        if status: stopped = status; break
    final = {'schema_version':1,'kind':'terminal_regression_summary','context':manifest['context'],'cases':summaries,
             'successful':len(summaries)==3 and stopped is None,'diagnostic':stopped,
             'old_consumed':17,'new_consumed':current_stats['consumed'] if current_stats else None,
             'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
    # Revisioned immutable summaries allow recovery after an interrupted pair.
    immutable_write(checked_output(repo, output/('summary-'+digest(canonical(final))+'.json')),final)
    return final
