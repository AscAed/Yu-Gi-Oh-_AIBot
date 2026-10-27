"""Filesystem-only static prompt preparation; deliberately has no execution entry."""
import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

ACCEPTANCE_SHA = '5fda5ef58e8b45813af0a79dbc0459354a533eb08aa6ade03f5288db6bc00833'
CASES_SHA = 'de1e0157db84c9c12249798f895e359479ea092c92c593ce0f84e35e5b253879'
SCRIPT_PINS = {
    'official/c57103969.lua': 'f616f84335cdc031435b491d078cb6b49660959075d6e95307f143f354bd2f65',
    'official/c58074572.lua': 'df0569217bb3659ed774d21a158c86bb9aec65bca7f5725f03df97b479c5f9ac',
    'official/c90502999.lua': '67d95d32e1b6023c41516b0f15657af60121aa5b072dc85bb273fc1280912497',
    'utility.lua': 'ace5e7811d8e9863ba0604cf7d90747e4ee010e11d30c4e1ebca29e82a5cb13c',
}
CORE_PINS = {
    'libduel.cpp': '4b31e3247555b6548bcd2588e944a971d6f3032da0ed12f963235275aeef3e5a',
    'processor.cpp': 'd051d6a006baa9ad4a590d4bcc185bff112e3ed7df256ff25cd8c0ff7beaf085',
    'ocgapi_constants.h': '191315f0c37bdc2fc086dee457bfc8ebb10b27cb1f063d26d5776465f9dbc4aa',
    'effect_constants.h': '6d14bc8ba1a1aa955815266fcb3db8b49ebf8174385bfd885a881f899c7041c6',
    'playerop.cpp': 'a9ff2c499476f70afb4afa9d3880a0070bcd54f4baf9f116cd9e79f7107c9e97',
    'field.cpp': '9b6aa4916a8e2f7e95cab570be886e22751c197b320f15acdf1fa7de3c5dadfd',
}
REPO_PINS = {
    'crates/ygo-engine-adapter/src/worker.rs': 'adfad90c5a62944e2d669fad81dece7ec4e70a338a03362a30ffb2453a29c4d7',
    'crates/ygo-engine-adapter/src/codec.rs': '224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e',
}
TOOL_FILES = ('.gitignore', 'python/ygo_eval/prompt_probe_prepare.py', 'python/ygo_eval/prompt_probe_logic.py', 'python/ygo_eval/research.py', 'schemas/prompt-probe-preparation.schema.json', 'schemas/prepared-prompt-cases.schema.json', 'schemas/research-case.schema.json')
FLAGS = dict(execution_ready=False, native_reachability_verified=False, response_acceptance_verified=False, proof_ready=False, complete_action_coverage=False, global_optimality=False, native_probability_verified=False)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite_json_number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2).encode('utf8') + b'\n'


def safe_path(path, file=True):
    path = Path(os.path.abspath(path))
    for parent in [*reversed(path.parents), path]:
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, 'linked_path_rejected')
    require(stat.S_ISREG(path.stat().st_mode) if file else path.is_dir(), 'regular_file_or_directory_required')
    return path


def relative(root, name):
    name = Path(name)
    require(not name.is_absolute() and '..' not in name.parts, 'unsafe_relative_path')
    return root/name


def output_directory(repo, output):
    output = Path(os.path.abspath(output))
    allowed = repo/'data/runtime/p1-prompt-probes-offline-2026-10-21'
    require(output.is_relative_to(allowed), 'dedicated_preparation_output_required')
    ignored = safe_path(repo/'.gitignore').read_text(encoding='utf8').splitlines()
    require(not any(line.lstrip().startswith('!') for line in ignored), 'unsupported_ignore_negation')
    for parent in [*reversed(output.parents), output]:
        if parent != repo and parent.is_relative_to(repo):
            require(not (parent/'.gitignore').exists() and not (parent/'.gitignore').is_symlink(), 'unsupported_nested_ignore')
    require(any(line.strip() in ('/data/runtime/', 'data/runtime/', '/data/runtime', 'data/runtime') for line in ignored), 'ignored_output_contract_missing')
    for parent in [*reversed(output.parents), output]:
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, 'linked_output_rejected')
    require(not output.exists(), 'output_already_exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    return output


def prepare_prompt_probes(args, repo=None):
    """Prepare immutable static evidence using file reads and SQLite read-only only."""
    from ygo_eval.research import validate_sources
    repo = Path(os.path.abspath(repo or Path(__file__).resolve().parents[2]))
    proposed = Path(os.path.abspath(args.output))
    for source in (getattr(args,'core_source',None), getattr(args,'baseline_dir',None)):
        if source is not None:
            require(not proposed.is_relative_to(Path(os.path.abspath(source))), 'output_inside_source_rejected')
    if getattr(args,'cases',None) is not None and Path(args.cases).is_file():
        try:
            preflight = strict_json(safe_path(args.cases).read_bytes())
        except (ValueError,OSError):
            preflight = {}
        items = preflight.get('cases',[]) if isinstance(preflight,dict) else []
        for item in items if isinstance(items,list) else []:
            if not isinstance(item,dict) or not isinstance(item.get('request'),dict):
                continue
            engine_input = item['request'].get('engine')
            scripts_input = engine_input.get('scripts_path') if isinstance(engine_input,dict) else None
            if isinstance(scripts_input,str) and scripts_input:
                require(not proposed.is_relative_to(Path(os.path.abspath(scripts_input))), 'output_inside_source_rejected')
    output = output_directory(repo, args.output)
    report = dict(schema_version=1, kind='prompt_probe_preparation', preparation_successful=False, source_unchanged=False,
                  native_calls=0, cumulative_consumed=24, unknown_consumption=0, candidates=[], command6={'status':'blocked','reason':'turn_one_battle_phase_not_available_under_current_configuration'},
                  input_sha256={}, tool_identity={'algorithm':'prompt-preparation-fixed-files-v1','files':{}}, diagnostics=[], **FLAGS)
    prepared = dict(schema_version=1, kind='static_prompt_probe_candidates', candidates=[], **FLAGS)
    inputs = {}; directories = {}
    def read(path, role, expected=None):
        path = safe_path(path)
        raw = path.read_bytes()
        sha = digest(raw)
        require(expected is None or sha == expected, 'anchored_input_hash_mismatch')
        require(path not in inputs or inputs[path][1] == sha, 'input_changed_during_read')
        inputs[path] = (role, sha)
        return raw
    try:
        for name in TOOL_FILES:
            report['tool_identity']['files'][name] = digest(read(repo/name, 'tool/'+name))
        report['tool_identity']['sha256'] = digest(encode(report['tool_identity']['files']))
        baseline = safe_path(args.baseline_dir, False)
        acceptance = strict_json(read(baseline/'acceptance.json', 'baseline/acceptance.json', ACCEPTANCE_SHA))
        require(acceptance['cumulative_consumed'] == 24 and acceptance['unknown'] == 0, 'baseline_consumption_mismatch')
        require(acceptance.get('kind') == 'shuffle_route_offline_delivery_acceptance' and acceptance.get('source_identity') == '42372235b2ab0453db078a5d06ee0fdd5c979271ba60663d2327b0bd04ec9598' and acceptance.get('source_files') == 374 and acceptance.get('paused') is True and acceptance.get('tools_verified') is True and acceptance.get('route_observation_verified') is True, 'baseline_identity_mismatch')
        for flag in ('proof_ready','complete_action_coverage','global_optimality','native_probability_verified'):
            require(acceptance.get(flag) is False, 'baseline_qualification_mismatch')
        for name, evidence in acceptance['evidence'].items():
            read(relative(baseline, name), 'baseline/'+name, evidence['sha256'])
        frozen = strict_json(read(args.cases, 'frozen_cases', CASES_SHA))
        rabbits = [item for item in frozen['cases'] if item['case']['case_id'] == 'rabbit']
        require(len(rabbits) == 1, 'unique_rabbit_case_required')
        base = rabbits[0]
        request = base['request']
        for key in ('ocgcore_path','catalog_path','script_manifest_path','engine_manifest_path'):
            raw = read(Path(request['engine'][key]), 'runtime/'+key)
            if key.endswith('manifest_path'):
                strict_json(raw)
        banlist = Path(base['banlist_path'])
        strict_json(read(banlist, 'runtime/banlist'))
        strict_json(read(banlist, 'runtime/banlist'))
        validate_sources(base['case'], request, banlist)
        scripts = safe_path(request['engine']['scripts_path'], False)
        manifest = strict_json(read(Path(request['engine']['script_manifest_path']), 'runtime/script_manifest_path'))
        require(isinstance(manifest, dict), 'script_manifest_shape')
        directories[scripts] = sorted(path.relative_to(scripts).as_posix() for path in scripts.rglob('*'))
        for name, expected in SCRIPT_PINS.items():
            require(manifest.get(name) == expected, 'script_manifest_pin_mismatch')
            read(relative(scripts, name), 'scripts/'+name, expected)
        listed = sorted(name for name in manifest if name.startswith('official/') and name.endswith('.lua'))
        require(bool(listed), 'official_script_scope_empty')
        hits = []
        for name in listed:
            raw = read(relative(scripts, name), 'scripts/'+name, manifest[name])
            if b'EFFECT_BP_FIRST_TURN' in raw:
                hits.append(name)
        report['command6'].update(worker_flags='0x2e800', attack_first_turn_flag='0x02', worker_stops_after_turn=1,
            direct_symbol_scan={'scope':'manifest-listed official Lua files only','files_scanned':len(listed),'hits':hits,'dynamic_or_universal_absence_proven':False})
        core = safe_path(args.core_source, False)
        directories[core] = sorted(path.relative_to(core).as_posix() for path in core.rglob('*'))
        for name, expected in CORE_PINS.items():
            read(relative(core, name), 'core/'+name, expected)
        for name, expected in REPO_PINS.items():
            read(repo/name, 'repository/'+name, expected)
        from ygo_eval.prompt_probe_logic import derive_candidates, response_fixtures
        candidates = derive_candidates(base['case'])
        with closing(sqlite3.connect(safe_path(request['engine']['catalog_path']).as_uri()+'?mode=ro', uri=True)) as db:
            row = db.execute('SELECT alias,ot,race,level FROM datas WHERE id=69247929').fetchone()
            require(row is not None and row[2] == 32768 and row[3] & 0xff == 4, 'tenki_target_filter_mismatch')
            report['tenki_target'] = {'card_id':69247929,'copies':base['case']['deck']['main'].count(69247929),'alias':row[0],'ot':row[1],'race':row[2],'level':row[3] & 0xff,'formal_release_status':'unknown'}
        require(report['tenki_target']['copies'] == 2, 'tenki_target_copies_mismatch')
        with closing(sqlite3.connect(safe_path(request['engine']['catalog_path']).as_uri()+'?mode=ro', uri=True)) as db:
            candidate_metadata = {c['target']['card_id']:db.execute('SELECT alias,ot FROM datas WHERE id=?',(c['target']['card_id'],)).fetchone() for c in candidates}
        for candidate in candidates:
            derived = copy.deepcopy(request)
            for key in ('deck','opening_hand','seed'):
                derived[key] = copy.deepcopy(candidate['case'][key])
            derived['decisions'] = []
            strict_json(read(banlist, 'runtime/banlist'))
            validate_sources(candidate['case'], derived, banlist)
            candidate['request_derivation'].update(base_request_sha256=digest(encode(request)),case_sha256=digest(encode(candidate['case'])),hash_encoding='sorted-utf8-indent2-newline-v1',pending_conditions=['bind_future_worker','bind_actual_native_prompt','freeze_full_future_request_hash','authorize_new_budget_and_window'])
            candidate.update(FLAGS)
            candidate['status'] = 'static_prepared'
            candidate['source_legality_validated'] = True
            metadata = candidate_metadata[candidate['target']['card_id']]
            require(metadata is not None, 'candidate_catalog_metadata_missing')
            candidate['catalog_legality'] = {'alias':metadata[0],'ot':metadata[1],'ocg_bit_present':bool(metadata[1] & 1),'banlist_and_alias_limits_validated':True,'formal_release_status':'unknown'}
            prepared['candidates'].append(candidate)
            report['candidates'].append({'case_id':candidate['case']['case_id'],'status':'static_prepared','formal_release_status':'unknown', **FLAGS})
        prepared['response_fixtures'] = response_fixtures()
        report['static_api_mapping'] = [{'card_id':57103969,'api':'Duel.SelectYesNo','core_processor':'Processors::SelectYesNo','opcode':13}, {'card_id':58074572,'api':'Duel.SelectOption','core_processor':'Processors::SelectOption','opcode':14}, {'card_id':90502999,'api':'Duel.SelectDisableField','core_processor':'Processors::SelectDisField','opcode':24}]
        report['stringid'] = {'implementation':'utility.lua Auxiliary.Stringid','formula':'(id & 0xfffff) | (code << 20)','runtime_description_match_verified':False}
        report['followup_dependencies'] = [{'message':'RECOVER','opcode':92,'decoder_supported':False},{'message':'FIELD_DISABLED','opcode':56,'decoder_supported':False}]
        require(len(candidates) == 3, 'three_candidates_required')
        for path, (_, expected) in inputs.items():
            require(digest(safe_path(path).read_bytes()) == expected, 'input_changed_during_preparation')
        for path, names in directories.items():
            require(sorted(item.relative_to(path).as_posix() for item in path.rglob('*')) == names, 'source_directory_changed')
        for parent in [*reversed(output.parents),output]:
            if parent != repo and parent.is_relative_to(repo):
                require(not (parent/'.gitignore').exists() and not (parent/'.gitignore').is_symlink(), 'source_directory_changed')
        report['source_unchanged'] = True
        report['preparation_successful'] = True
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        reason = str(error)
        try:
            for path, (_, expected) in inputs.items():
                require(digest(safe_path(path).read_bytes()) == expected, 'input_changed_during_preparation')
            for path, names in directories.items():
                require(sorted(item.relative_to(path).as_posix() for item in path.rglob('*')) == names, 'source_directory_changed')
        except (ValueError,OSError) as drift:
            reason = str(drift) if str(drift) in ('source_directory_changed','input_changed_during_preparation') else 'input_changed_during_preparation'
        report['diagnostics'] = [reason if reason and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in reason) else 'preparation_rejected']
        if reason in ('input_changed_during_preparation','source_directory_changed','input_changed_during_read'):
            report['candidates'] = []
            prepared['candidates'] = []
    report['input_sha256'] = dict(sorted((role, sha) for role, sha in inputs.values()))
    for name, value in (('prepared-cases.json', prepared), ('report.json', report)):
        with (output/name).open('xb') as stream:
            stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
    return report
