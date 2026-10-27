"""Frozen five-pair native regression; preparation never starts a worker."""
import copy
import json
import subprocess
from collections import Counter
from pathlib import Path

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source

CASE_IDS = ['rabbit-full', 'tournament-full', 'rabbit-empty', 'rabbit-shuffle', 'rabbit-end']
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


def _hand(result):
    cards = result.get('checkpoint', {}).get('cards')
    if not isinstance(cards, list): raise ValueError('hand checkpoint missing')
    return Counter(c['code'] for c in cards if c['player'] == 0 and c['location'] == 2)


def check_observations(case_id, result, parent):
    """Additional group-specific checks; these confer no terminal or proof status."""
    if case_id == 'rabbit-empty':
        derive_request({'decisions': []}, result, 8)
    elif case_id == 'rabbit-shuffle':
        parent_events = parent.get('events') if isinstance(parent,dict) else None
        child_events = result.get('events')
        if not isinstance(parent_events,list) or not isinstance(child_events,list) or child_events[:len(parent_events)] != parent_events:
            raise ValueError('child event prefix differs from parent history')
        # Every run starts from the duel beginning; initialization can shuffle too.
        raw = [f.get('raw', []) for f in child_events[len(parent_events):]]
        messages = [f for f in raw if f[:2] == [33, 0]]
        if len(messages) != 1 or len(messages[0]) < 6: raise ValueError('own shuffle message missing')
        frame = bytes(messages[0]); count = int.from_bytes(frame[2:6], 'little')
        if len(frame) != 6 + 4 * count: raise ValueError('shuffle message malformed')
        codes = Counter(int.from_bytes(frame[n:n+4], 'little') for n in range(6, len(frame), 4))
        if _hand(result) != _hand(parent) or codes != _hand(parent): raise ValueError('hand multiset changed')
        prompt = result.get('prompt')
        if not prompt or prompt.get('player') != 0 or prompt.get('opcode') != 11: raise ValueError('post-shuffle idle missing')
        if any(a.get('choice') == {'kind':'command', 'command':8, 'index':0} for a in prompt['actions']):
            raise ValueError('shuffle option not closed')
    elif case_id in ('rabbit-end','rabbit-full','tournament-full'):
        raw = [f.get('raw', []) for f in result.get('events', [])]
        ends = [i for i, f in enumerate(raw) if f == [41, 0, 2]]
        if not ends or not any(f == [40, 1] for f in raw[ends[-1]+1:]):
            raise ValueError('end phase followed by next turn not observed')
    return True


def add_arguments(parser):
    for name in ('cases', 'runner', 'worker', 'build-record', 'identity', 'old-ledger', 'window-start', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')


def _sha(path): return digest(regular_file(path).read_bytes())


def native_regression(args):
    """Prepare or resume exactly the five approved pairs, stopping at first failure."""
    from ygo_eval.research import validate_sources
    repo = Path(__file__).resolve().parents[2]
    output = checked_output(repo, args.output)
    if 'research' not in output.relative_to(repo / 'data' / 'runtime').parts:
        raise ValueError('dedicated research output required')
    paths = {name: regular_file(getattr(args,name).absolute()) for name in
             ('cases','runner','worker','build_record','identity','old_ledger','window_start')}
    if any(p == output or p.is_relative_to(output) or output.is_relative_to(p) for p in paths.values()):
        raise ValueError('output overlaps frozen input')
    hashes = {name:_sha(path) for name,path in paths.items()}
    if hashes['old_ledger'] != OLD_LEDGER_SHA: raise ValueError('original nine-call ledger changed')
    source = stable_source(repo)
    build = json.loads(paths['build_record'].read_bytes())
    identities = json.loads(paths['identity'].read_bytes())
    window = json.loads(paths['window_start'].read_bytes())
    import time
    if window.get('schema_version') != 1 or window.get('kind') != 'native_regression_window_start' or type(window.get('started_at')) is not int or not 0 <= window['started_at'] <= int(time.time()):
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
    manifest = {'schema_version':1,'kind':'native_regression_manifest', 'source_identity':source['identity'],
        'output_relative':output.relative_to(repo).as_posix(),
        'input_sha256':hashes,'old_consumed':9,'limit':16,'planned_calls':10,'window_seconds':7200,'started_at':window['started_at'],
        'case_ids':CASE_IDS, 'templates':templates,'runtimes':identities['runtimes'],
        'allowed_derivations':['rabbit-empty:remove_all_decisions','rabbit-shuffle:parent_public_command8','rabbit-end:parent_public_command7'],
        'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
    manifest['context'] = digest(canonical(manifest))
    # One approved time-window file binds one output scope, including reopen.
    window_binding = checked_output(repo, paths['window_start'].with_suffix('.binding.json'))
    immutable_write(window_binding, {'context':manifest['context'],'output_relative':manifest['output_relative']})
    output.mkdir(parents=True, exist_ok=True)
    immutable_write(checked_output(repo, output/'manifest.json'),manifest)
    if args.prepare_only: return {'prepared':True,'planned_calls':10,'native_calls':0}
    ledger = checked_output(repo, output/'calls.jsonl')
    summaries = []; parents = {}; stopped = None; current_stats = None
    def frozen_inputs():
        if stable_source(repo) != source or any(_sha(p) != hashes[n] for n,p in paths.items()):
            raise ValueError('frozen source, build, or input changed')
    for case_id in CASE_IDS:
        frozen_inputs()
        parent = None; derivation = None
        if case_id == 'tournament-full': request = templates['tournament']; role = 'tournament'
        else:
            role = 'ordinary'; request = copy.deepcopy(templates['rabbit'])
            if case_id == 'rabbit-empty': request['decisions'] = []
            if case_id in ('rabbit-shuffle','rabbit-end'):
                parent_id = 'rabbit-empty' if case_id == 'rabbit-shuffle' else 'rabbit-shuffle'
                parent_pair = parents[parent_id]; parent = parent_pair['runs'][0]['Ok']
                request = derive_request(parent_pair['request'], parent, 8 if case_id == 'rabbit-shuffle' else 7)
                derivation = {'parent_case':parent_id,'parent_evidence_sha256':_sha(output/(parent_id+'.json')),
                              'prompt_id':parent['prompt']['id'],'choice':request['decisions'][-1]['choice']}
        intent = {'context':manifest['context'],'ledger':str(ledger),'output':str(output/(case_id+'.json')),
                  'case_id':case_id,'request':request,'expected_identity':identities['runtimes'][role],'started_at':window['started_at']}
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
        parents[case_id] = pair
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
                        check_observations(case_id,run['Ok'],parent)
                except (ValueError,KeyError,TypeError): status = 'group_observation_failed'
        summaries.append({'case_id':case_id,'evidence_sha256':_sha(pair_path),'diagnostic':status,'ledger':pair['ledger']})
        frozen_inputs()
        if status: stopped = status; break
    final = {'schema_version':1,'kind':'native_regression_summary','context':manifest['context'],'cases':summaries,
             'successful':len(summaries)==5 and stopped is None,'diagnostic':stopped,
             'old_consumed':9,'new_consumed':current_stats['consumed'] if current_stats else None,
             'proof_ready':False,'complete_action_coverage':False,'global_optimality':False}
    # Revisioned immutable summaries allow recovery after an interrupted pair.
    immutable_write(checked_output(repo, output/('summary-'+digest(canonical(final))+'.json')),final)
    return final
