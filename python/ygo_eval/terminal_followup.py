"""Two frozen terminal pairs, with a separate four-request scope."""
import copy
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from ygo_data.identity import canonical, checked_output, digest, regular_file, stable_source
from ygo_eval.terminal_regression import immutable_write, derive_request
from ygo_eval.terminal_smoke import POLICY, sha

CASE_IDS = ['terminal-tournament', 'terminal-shuffle-end']
ACCEPTANCE_SHA = 'fbd371a4f8f10166df2b501b40fc25d35df05ad2b0deffd1055559cfa30bea6a'
SOURCE_SHA = 'c595aece46eda83f7e3412c01c0ea242a6885e117adffd5615ef683c1553d8fc'
LEDGERS = {
 'baseline-2026-10-19/research/calls.jsonl':'b1cde5ab207a1e9ee5033f2b185c5c7de90994021d39c6a1bad9e82b2974bd6a',
 'p1-state-native-2026-10-20/research/native/calls.jsonl':'0e50a03837676b8b19a1409b9ffa06bc7798ff61254109c10025c7733a3c410b',
 'p1-terminal-2026-10-20/research/native/calls.jsonl':'3fd2aa6d1ff18f5eb1fe7100fe8fb4c36e9b73795e0749aa362b0bea9ea93ef2',
 'p1-terminal-smoke-2026-10-20/research/native/calls.jsonl':'624b4843dc9cd09e07588074b2b4ecbd91737316c70e922a183f0dd9a5f137b0'}
FLAGS = dict(proof_ready=False, complete_action_coverage=False, global_optimality=False)


def validate_baseline(baseline, repo):
    acceptance_path = regular_file(baseline/'acceptance.json')
    if sha(acceptance_path) != ACCEPTANCE_SHA:
        raise ValueError('baseline acceptance differs')
    acceptance = json.loads(acceptance_path.read_bytes())
    checkpoint = json.loads(regular_file(baseline/'delivery-checkpoint.json').read_bytes())
    if (acceptance['source_identity'] != SOURCE_SHA or checkpoint['source_identity'] != SOURCE_SHA
            or checkpoint['acceptance_sha256'] != ACCEPTANCE_SHA or acceptance['cumulative_consumed'] != 20
            or acceptance['unknown'] or acceptance['reserved']):
        raise ValueError('baseline identity or consumption differs')
    protected = {acceptance_path:ACCEPTANCE_SHA, baseline/'delivery-checkpoint.json':sha(baseline/'delivery-checkpoint.json')}
    for relative, record in acceptance['evidence'].items():
        if Path(relative).is_absolute() or '..' in Path(relative).parts: raise ValueError('evidence path escapes')
        path = baseline/relative
        if sha(path) != record['sha256'] or path.stat().st_size != record['bytes']:
            raise ValueError('baseline evidence differs')
        protected[path] = record['sha256']
    before = json.loads(regular_file(baseline/'before.json').read_bytes())
    for relative, expected in before['protected_files'].items():
        path = repo/relative
        if sha(path) != expected: raise ValueError('historical protected file differs')
        protected[path] = expected
    for relative, files in before['blob_files'].items():
        root = repo/relative
        actual = {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}
        if actual != files: raise ValueError('historical blobs differ')
        protected.update({root/name:value for name,value in files.items()})
    for relative, expected in LEDGERS.items():
        path = repo/'data/runtime'/relative
        if sha(path) != expected: raise ValueError('historical ledger differs')
        protected[path] = expected
    build = json.loads(regular_file(baseline/'build-native.json').read_bytes())
    runner = baseline/'native-artifacts/terminal-regression.exe'
    if build['identity'] != acceptance['native_build_identity'] or sha(runner) != build['artifacts']['audit']:
        raise ValueError('saved native runner differs')
    protected[runner] = sha(runner)
    invocation = baseline/'research/native/terminal-rabbit-input.json'
    verify_receipt(runner, invocation, protected[invocation], 2)
    failed_root = repo/'data/runtime/p1-terminal-2026-10-20'
    failed_runner = failed_root/'native-artifacts/terminal-regression.exe'
    failed_input = failed_root/'research/native/terminal-rabbit-input.json'
    if protected.get(failed_runner) != sha(failed_runner): raise ValueError('failed native runner differs')
    verify_receipt(failed_runner,failed_input,protected[failed_input],1)
    if any(sha(p) != value for p,value in protected.items()): raise ValueError('baseline changed')
    return protected


def validate_history_report(path, repo):
    """Recompute the accepted read-only audit; a saved success flag is insufficient."""
    from ygo_eval.history_audit import audit_history
    path = regular_file(path)
    before = sha(path)
    def unique_fields(pairs):
        value = {}
        for name,item in pairs:
            if name in value:
                raise ValueError('historical audit duplicate key')
            value[name] = item
        return value
    supplied = json.loads(path.read_bytes(), object_pairs_hook=unique_fields)
    fresh = audit_history(repo/'data/runtime/p1-terminal-followup-2026-10-20', repo=repo)
    if sha(path) != before or fresh.get('valid') is not True or fresh.get('native_calls') != 0 or canonical(supplied) != canonical(fresh):
        raise ValueError('historical audit differs or failed')
    protected = {path:before}
    for relative, expected in fresh.get('input_sha256', {}).items():
        name = Path(relative)
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('historical audit input escapes')
        source = repo/name
        if sha(source) != expected:
            raise ValueError('historical audit source changed')
        protected[source] = expected
    return protected


def verify_frozen_inputs(repo, source, paths, hashes, protected, historical_audit):
    """Guard intent publication and every pair with the same immutable inputs."""
    if (stable_source(repo) != source
            or any(sha(path) != hashes[name] for name,path in paths.items())
            or any(sha(path) != expected for path,expected in protected.items())):
        raise ValueError('frozen input changed')
    validate_history_report(historical_audit, repo)


def verify_receipt(runner, invocation, expected, consumed):
    if sha(invocation) != expected: raise ValueError('historical invocation differs')
    result = subprocess.run([str(runner),str(invocation),'--input-sha',expected,'--verify-recorded'],capture_output=True,timeout=60)
    if result.returncode != 0: raise ValueError('historical receipt failed')
    stats = json.loads(result.stdout)['ledger']
    if stats['consumed'] != consumed or stats['completed'] != consumed or stats['unknown'] or stats['reserved']:
        raise ValueError('historical receipt consumption differs')


def pair_diagnostic(pair, decisions):
    if pair is None: return 'runner_failed_or_outcome_unavailable'
    if pair.get('diagnostic'): return pair['diagnostic']
    if any(pair.get(k) is not False for k in FLAGS): return 'qualification_flags_invalid'
    if pair.get('assets_unchanged') is not True or pair.get('independent_replay_matches') is not True:
        return 'pair_verification_failed'
    groups = pair.get('prompt_audits_by_run')
    if not isinstance(groups,list) or len(groups) != 2 or any(not isinstance(g,list) or any(a.get('audit',{}).get('Ok',{}).get('matches') is not True for a in g) for g in groups):
        return 'prompt_response_audit_failed'
    if len(pair.get('runs',[])) != 2 or len(pair.get('terminal_audits',[])) != 2:
        return 'incomplete_pair'
    for run in pair['runs']:
        if set(run) != {'Ok'}: return 'execution_failed'
        value = run['Ok']
        if value.get('status') != 'engine_verified' or 'error' not in value or value['error'] is not None or 'prompt' not in value or value['prompt'] is not None or value.get('resolved_decisions') != decisions:
            return 'execution_or_decisions_failed'
    for audit in pair['terminal_audits']:
        if audit.get('binding_valid') is not True or type(audit.get('snapshot_count')) is not int or audit['snapshot_count'] != 0 or type(audit.get('utility')) is not int or audit['utility'] != 0:
            return 'terminal_binding_or_utility_failed'
    return None


def summarize(context, pairs, stats, diagnostic):
    if stats is None or stats.get('unknown') or stats.get('reserved'): diagnostic = 'unresolved_consumption'
    if not diagnostic and ([p['case_id'] for p in pairs] != CASE_IDS or not all(p['successful'] for p in pairs)):
        diagnostic = 'incomplete_pairs'
    if not diagnostic and any(stats.get(k) != v for k,v in dict(consumed=4,completed=4,limit=4,unknown=0,reserved=0,abandoned=0).items()):
        diagnostic = 'incomplete_consumption'
    return dict(schema_version=1,kind='terminal_followup_summary',context=context,pairs=pairs,ledger=stats,
                successful=diagnostic is None,diagnostic=diagnostic,old_consumed=20,
                new_consumed=stats['consumed'] if stats else None,**FLAGS)


def add_arguments(parser):
    for name in ('cases','baseline-dir','historical-audit','parent-input','parent-evidence','parent-runner','runner','worker','build-record','identity','window-start','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')


def terminal_followup(args):
    from ygo_eval.research import validate_sources
    repo = Path(__file__).resolve().parents[2]
    output = checked_output(repo,args.output)
    if 'research' not in output.relative_to(repo/'data/runtime').parts: raise ValueError('research output required')
    paths = {key:regular_file(getattr(args,key).absolute()) for key in ('cases','historical_audit','parent_input','parent_evidence','parent_runner','runner','worker','build_record','identity','window_start')}
    if any(p == output or p.is_relative_to(output) or output.is_relative_to(p) for p in paths.values()): raise ValueError('output overlaps input')
    hashes = {k:sha(p) for k,p in paths.items()}
    history_protected = validate_history_report(paths['historical_audit'], repo)
    protected = validate_baseline(args.baseline_dir.absolute(),repo)
    protected.update(history_protected)
    for key in ('cases','parent_input','parent_evidence','parent_runner'):
        if protected.get(paths[key]) != hashes[key]: raise ValueError('historical source not pinned')
    verify_receipt(paths['parent_runner'],paths['parent_input'],hashes['parent_input'],8)
    parent_input = json.loads(paths['parent_input'].read_bytes())
    parent = json.loads(paths['parent_evidence'].read_bytes())
    if parent_input['case_id'] != 'rabbit-shuffle' or Path(parent_input['output']).absolute() != paths['parent_evidence'] or Path(parent_input['ledger']).absolute() != repo/'data/runtime/p1-state-native-2026-10-20/research/native/calls.jsonl': raise ValueError('parent binding differs')
    if parent.get('assets_unchanged') is not True or parent.get('independent_replay_matches') is not True: raise ValueError('parent unverified')
    derived = derive_request(parent['request'],parent['runs'][0]['Ok'],7)
    expected_decisions = [{'prompt_id':7,'player':0,'choice':{'kind':'command','command':8,'index':0}}, {'prompt_id':9,'player':0,'choice':{'kind':'command','command':7,'index':0}}]
    if derived['decisions'] != expected_decisions: raise ValueError('parent public decisions differ')
    source = stable_source(repo)
    build = json.loads(paths['build_record'].read_bytes()); identity = json.loads(paths['identity'].read_bytes()); window = json.loads(paths['window_start'].read_bytes())
    if window.get('schema_version') != 1 or window.get('kind') != 'terminal_followup_window_start' or type(window.get('started_at')) is not int or not 0 <= window['started_at'] <= int(time.time()): raise ValueError('invalid immutable window')
    if build.get('status') != 'recorded' or build.get('source_before') != source or build.get('source_after') != source or any(hashes[k] not in build.get('artifacts',{}).values() for k in ('runner','worker')): raise ValueError('build differs')
    if identity.get('source') != source or identity.get('consistent') is not True: raise ValueError('identity differs')
    frozen = json.loads(paths['cases'].read_bytes()); items = {}
    for item in frozen['cases']:
        key = item['case']['case_id']
        if key not in ('rabbit','tournament'): continue
        if key in items: raise ValueError('duplicate case')
        validate_sources(item['case'],item['request'],Path(item['banlist_path'])); items[key] = item
    if set(items) != {'rabbit','tournament'}: raise ValueError('frozen cases missing')
    original = copy.deepcopy(items['rabbit']['request']); original['engine']['worker_path'] = parent['request']['engine']['worker_path']; original['decisions'] = parent['request']['decisions']
    if original != parent['request']: raise ValueError('shuffle parent not frozen Rabbit')
    templates = {'terminal-tournament':copy.deepcopy(items['tournament']['request']),'terminal-shuffle-end':derived}
    old_root = repo/'data/runtime/p1-terminal-2026-10-20'
    old_acceptance_path = old_root/'acceptance.json'
    if protected.get(old_acceptance_path) != sha(old_acceptance_path): raise ValueError('old acceptance differs')
    old_acceptance = json.loads(old_acceptance_path.read_bytes())
    old_manifest_path = old_root/'research/native/manifest.json'
    protected[old_manifest_path] = old_acceptance['evidence']['research/native/manifest.json']['sha256']
    if protected.get(old_manifest_path) != sha(old_manifest_path): raise ValueError('old template not protected')
    old_template = json.loads(old_manifest_path.read_bytes())['templates']['shuffle']
    check = copy.deepcopy(derived); check['research_capture'] = POLICY; check['engine']['worker_path'] = old_template['engine']['worker_path']
    if check != old_template: raise ValueError('derived frozen template differs')
    catalogs = {}; cdbs = {}; bindings = {}
    for case_id, request in templates.items():
        request['research_capture'] = POLICY; request['engine']['worker_path'] = str(paths['worker'])
        role = 'tournament' if case_id == 'terminal-tournament' else 'ordinary'; runtime = identity['runtimes'][role]
        validate_runtime(runtime,request,hashes['worker'])
        cdb = regular_file(Path(request['engine']['catalog_path']).absolute()); cdb_hash = sha(cdb)
        with sqlite3.connect(cdb.as_uri()+'?mode=ro',uri=True) as conn: rows = list(conn.execute('select id,type from datas'))
        if len({c for c,_ in rows}) != len(rows) or any(type(c) is not int or not 0 < c <= 0xffffffff or type(t) is not int or not 0 <= t <= 0xffffffff for c,t in rows): raise ValueError('invalid CDB types')
        catalog = {str(c):t for c,t in rows}
        if sha(cdb) != cdb_hash or cdb_hash != request['versions']['cdb_sha256']: raise ValueError('CDB changed')
        catalogs[case_id] = catalog; cdbs[cdb] = cdb_hash
        bindings[case_id] = {'request_sha256':digest(canonical(request)),'cdb_sha256':cdb_hash,'catalog_types_sha256':digest(canonical(catalog))}
    verify_frozen_inputs(repo,source,paths,hashes,{**protected,**cdbs},paths['historical_audit'])
    manifest = dict(schema_version=1,kind='terminal_followup_manifest',source_identity=source['identity'],output_relative=output.relative_to(repo).as_posix(),input_sha256=hashes,baseline_acceptance_sha256=ACCEPTANCE_SHA,old_consumed=20,limit=4,planned_calls=4,window_seconds=7200,started_at=window['started_at'],case_ids=CASE_IDS,bindings=bindings,runtimes=identity['runtimes'],parent={'evidence_sha256':hashes['parent_evidence'],'public_prompt_sha256':digest(canonical(parent['runs'][0]['Ok']['prompt']))},**FLAGS)
    manifest['context'] = digest(canonical(manifest))
    immutable_write(checked_output(repo,paths['window_start'].with_suffix('.binding.json')),{'context':manifest['context'],'output_relative':manifest['output_relative']})
    immutable_write(checked_output(repo,output/'manifest.json'),manifest)
    invocations = {}
    for case_id,request in templates.items():
        role = 'tournament' if case_id == 'terminal-tournament' else 'ordinary'
        intent = dict(batch_kind='terminal-followup-v1',context=manifest['context'],ledger=str(output/'calls.jsonl'),output=str(output/(case_id+'.json')),case_id=case_id,request=request,expected_identity=identity['runtimes'][role],started_at=window['started_at'],catalog_types=catalogs[case_id],expected_count=0)
        path = checked_output(repo,output/(case_id+'-input.json')); immutable_write(path,intent)
        immutable_write(checked_output(repo,output/(case_id+'-request.json')),{'request_sha256':bindings[case_id]['request_sha256'],'input':intent})
        invocations[case_id] = (path,digest(canonical(intent)))
    def unchanged():
        verify_frozen_inputs(repo,source,paths,hashes,{**protected,**cdbs},paths['historical_audit'])
        if any(sha(p) != h for p,h in invocations.values()): raise ValueError('frozen input changed')
    unchanged()
    if args.prepare_only: return dict(prepared=True,planned_calls=4,native_calls=0,context=manifest['context'])
    pairs, stats, stopped = execute_pairs(invocations,templates,paths['runner'],output,manifest['context'],unchanged)
    report = summarize(manifest['context'],pairs,stats,stopped)
    immutable_write(checked_output(repo,output/('summary-'+digest(canonical(report))+'.json')),report)
    return report


def execute_pairs(invocations, templates, runner, output, context, unchanged):
    """Only the fixed first passing pair can unlock the second runner call."""
    if list(invocations) != CASE_IDS or list(templates) != CASE_IDS:
        raise ValueError("fixed case order required")
    pairs = []; stats = None; stopped = None
    for case_id in CASE_IDS:
        unchanged()
        path,input_sha = invocations[case_id]; pair_path = output/(case_id+'.json')
        command = [str(runner),str(path),'--input-sha',input_sha]
        recorded = pair_path.exists()
        try: result = subprocess.run(command+(['--verify-recorded'] if recorded else []),capture_output=True,timeout=7200)
        except subprocess.TimeoutExpired: result = subprocess.CompletedProcess(command,2,b'',b'runner_timeout')
        if recorded and result.returncode != 0: raise ValueError('recorded receipt differs')
        if result.returncode in (0,1) and pair_path.exists(): stats = json.loads(result.stdout)['ledger']
        else:
            queried = subprocess.run(command+['--stats'],capture_output=True,timeout=60)
            stats = json.loads(queried.stdout)['ledger'] if queried.returncode == 0 else None
        pair = json.loads(regular_file(pair_path).read_bytes()) if pair_path.exists() else None
        if pair and (pair.get('context') != context or pair.get('case_id') != case_id or pair.get('request') != templates[case_id]): raise ValueError('pair binding differs')
        stopped = pair_diagnostic(pair,templates[case_id]['decisions'])
        if stats is None or stats.get('unknown') or stats.get('reserved'): stopped = 'unresolved_consumption'
        elif stats.get('limit') != 4 or stats.get('abandoned') or stats.get('completed') != stats.get('consumed'):
            stopped = 'unsettled_or_wrong_scope_consumption'
        pairs.append({'case_id':case_id,'successful':stopped is None,'diagnostic':stopped,'evidence_sha256':sha(pair_path) if pair else None})
        unchanged()
        if stopped: break
    return pairs, stats, stopped


def validate_runtime(runtime, request, worker_sha):
    """Bind each case to its own frozen asset role before creating paid inputs."""
    if runtime["roles"]["worker"]["sha256"] != worker_sha:
        raise ValueError("worker differs")
    for asset,version in [("dll","engine_sha256"),("cdb","cdb_sha256"),("script_manifest","scripts_sha256")]:
        if runtime["roles"][asset]["sha256"] != request["versions"][version]:
            raise ValueError("asset role differs")


def verify_original_runner(build, candidates, expected_sha):
    """A current replacement executable cannot certify a historical receipt."""
    if build.get('status') != 'recorded' or build.get('artifacts',{}).get('audit') != expected_sha:
        raise ValueError('old9_build_provenance_differs')
    for candidate in candidates:
        if candidate.is_file() and sha(candidate) == expected_sha:
            return candidate
    raise ValueError('old9_runner_unavailable')


def require_old9_original_runners(repo, protected):
    """Fail closed until the original nine-call receipt verifiers are recoverable."""
    root = repo/'data/runtime/baseline-2026-10-19'
    originals = [
        ('build-before-native.json','01c2b52451ebcdb6837d5d5e29ffdae7c1aa3be36e9c2b88545db2e4e923bb0f','b6c68c92414e1fed0b46ef4d2e5c2be3a6b5aa797e0f8261481bfa90034bc4c3','research-audit-before.exe'),
        ('build-resumed-native.json','7090a52dbb95443ab22a27598ac20d372e3fd084c0bd54aafe5cadfa533e02ec','b111cf5f5f015299517f80295a22c002b19efbb0c8cc685298f8d46794c3b7c7','research-audit-resumed.exe')]
    for name,build_sha,artifact_sha,saved_name in originals:
        path = root/name
        if sha(path) != build_sha: raise ValueError('old9_build_provenance_differs')
        build = json.loads(path.read_bytes())
        runner = verify_original_runner(build,[root/'native-artifacts'/saved_name,root/'native-artifacts/research-audit.exe',repo/'target/debug/examples/research-audit.exe'],artifact_sha)
        protected[path] = build_sha; protected[runner] = artifact_sha
    # The old research-audit only exposes recovery, not the required pure receipt
    # verifier. Finding binaries alone must not silently satisfy that extra gate.
    raise ValueError('old9_zero_call_receipt_verifier_unavailable')
