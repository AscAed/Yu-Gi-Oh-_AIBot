"""Frozen research inputs and sequential, ledger-backed native audit entrypoint."""
import argparse
from collections import Counter
from contextlib import closing
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess


def _object(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f'{label}: expected fields {fields}')


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _cards(value):
    return isinstance(value, list) and all(_integer(n, 1) and n <= 4294967295 for n in value)


def validate_case(case: dict) -> dict:
    """Check complete evaluation/information inputs, never grant proof qualification."""
    _object(case, ('schema_version','case_id','purpose','rules','assets','deck','opening_hand','seed','objective','information','randomness'), 'case')
    if type(case['schema_version']) is not int or case['schema_version'] != 1 or not isinstance(case['case_id'],str) or not re.fullmatch(r'[A-Za-z0-9-]+', case['case_id']):
        raise ValueError('unsupported research case identity')
    if case['purpose'] not in ('protocol_audit', 'proof_input') or not _integer(case['seed']):
        raise ValueError('invalid purpose/seed')
    _object(case['rules'], ('region','version','banlist_sha256'), 'rules')
    if case['rules']['region'] != 'OCG' or not isinstance(case['rules']['version'], str) or not case['rules']['version']:
        raise ValueError('frozen OCG rules required')
    _object(case['assets'], ('engine_sha256','cdb_sha256','scripts_sha256'), 'assets')
    for digest in [*case['assets'].values(), case['rules']['banlist_sha256']]:
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('invalid frozen source hash')
    deck = case['deck']
    _object(deck, ('main','extra','side'), 'deck')
    if not all(_cards(cards) for cards in deck.values()) or not 40 <= len(deck['main']) <= 60 or len(deck['extra']) > 15 or len(deck['side']) > 15:
        raise ValueError('complete deck sizes/card IDs required')
    if any(n > 3 for n in Counter(deck['main']+deck['extra']+deck['side']).values()):
        raise ValueError('three-copy limit exceeded before alias validation')
    hand = case['opening_hand']
    if not _cards(hand) or len(hand) != 5 or Counter(hand) - Counter(deck['main']):
        raise ValueError('five-card opening hand must come from main deck')
    objective = case['objective']
    _object(objective, ('priorities','terminal_utility'), 'objective')
    priorities = objective['priorities']
    if priorities != ['terminal_utility']:
        raise ValueError('ordered distinct objective priorities required')
    _object(objective['terminal_utility'], ('normal','early_win','loss','draw'), 'terminal utility')
    if not all(type(n) is int for n in objective['terminal_utility'].values()):
        raise ValueError('integer utility for every terminal outcome required')
    info = case['information']
    _object(info, ('player_visible','opponent_visible','hidden','opponent_resources'), 'information')
    known = {'own_hand','opponent_hand','own_deck_order','opponent_deck_order','public_board','public_history'}
    for key in ('player_visible','opponent_visible','hidden'):
        values = info[key]
        if not isinstance(values,list) or not values or any(not isinstance(n,str) or n not in known for n in values) or len(set(values)) != len(values):
            raise ValueError('invalid information field set')
    if set(info['player_visible']) & set(info['hidden']) or not {'own_deck_order','opponent_deck_order','opponent_hand'} <= set(info['hidden']):
        raise ValueError('hidden information must not enter player policy')
    if 'own_hand' in info['opponent_visible'] or any('deck_order' in n for n in info['player_visible']+info['opponent_visible']):
        raise ValueError('illegal private information observation')
    resources = info['opponent_resources']
    _object(resources, ('main','hand'), 'opponent resources')
    if not _cards(resources['main']) or not 40 <= len(resources['main']) <= 60 or not _cards(resources['hand']) or len(resources['hand']) > 5 or Counter(resources['hand']) - Counter(resources['main']):
        raise ValueError('fixed opponent main/resources required')
    randomness = case['randomness']
    _object(randomness, ('model','outcomes','seed_role'), 'randomness')
    if randomness['model'] not in ('frozen_scenario','explicit_distribution') or randomness['seed_role'] != 'reproduction_only' or not isinstance(randomness['outcomes'],list) or not randomness['outcomes']:
        raise ValueError('explicit randomness model required; seed is not a strategy')
    total = Fraction(); ids = set()
    for outcome in randomness['outcomes']:
        _object(outcome, ('id','numerator','denominator'), 'probability outcome')
        if not isinstance(outcome['id'],str) or not outcome['id'] or outcome['id'] in ids or not _integer(outcome['numerator'],1) or not _integer(outcome['denominator'],1):
            raise ValueError('invalid probability outcome')
        ids.add(outcome['id']); total += Fraction(outcome['numerator'],outcome['denominator'])
    if total != 1 or (randomness['model'] == 'frozen_scenario' and len(ids) != 1):
        raise ValueError('probabilities must total one')
    return {'schema_version':1,'case_id':case['case_id'],'input_complete':True,'legality_verified':False,'proof_ready':False,'global_optimality':False,'gaps':['declaration_only_until_sources_checked','chance_state_mapping_unverified','legal_information_policy_unverified']}


def validate_sources(case: dict, request: dict, banlist_path: Path) -> None:
    """Bind deck legality and frozen sources to actual read-only local inputs."""
    validate_case(case)
    if request.get('scenario') is not None or request.get('probe_only',False):
        raise ValueError('only standard runtime scenario admitted')
    if case['information']['opponent_resources'] != {'main':case['deck']['main'],'hand':[]}:
        raise ValueError('resources differ from worker fixed-opponent-v1 default')
    if request['versions'].get('rules') != 'ocg-mr5':
        raise ValueError('unsupported master rule')
    if request['deck'] != case['deck'] or request['opening_hand'] != case['opening_hand'] or request['seed'] != case['seed']:
        raise ValueError('request differs from frozen case')
    if request.get('interruption') is not None or request.get('first_turn') is not None:
        raise ValueError('first-batch protocol audit does not admit implicit opponent policies')
    if request['engine']['timeout_ms'] != 30000:
        raise ValueError('30 second worker timeout required')
    banlist_bytes = banlist_path.read_bytes()
    if hashlib.sha256(banlist_bytes).hexdigest() != case['rules']['banlist_sha256']:
        raise ValueError('banlist hash mismatch')
    banlist = json.loads(banlist_bytes)
    limits = banlist.get('data',banlist)
    if limits['region'] != case['rules']['region'] or limits['version'] != case['rules']['version']:
        raise ValueError('banlist rules mismatch')
    for role, key in [('ocgcore_path','engine_sha256'),('catalog_path','cdb_sha256'),('script_manifest_path','scripts_sha256')]:
        if hashlib.sha256(Path(request['engine'][role]).read_bytes()).hexdigest() != case['assets'][key]:
            raise ValueError(f'{role} changed')
    for key, digest in case['assets'].items():
        if request['versions'][key] != digest:
            raise ValueError('request asset version mismatch')
    path = Path(request['engine']['catalog_path']).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(path, uri=True)) as db:
        cards = {row[0]: row[1:] for row in db.execute('SELECT id,alias,type,ot FROM datas')}
    counts = Counter()
    extra_mask = 0x40 | 0x2000 | 0x800000 | 0x4000000
    for zone, values in case['deck'].items():
        for code in values:
            if code not in cards: raise ValueError('unknown card')
            alias, card_type, region = cards[code]
            if not region & 1 or card_type & 0x4000: raise ValueError('non-OCG card or token')
            if zone != 'side' and bool(card_type & extra_mask) != (zone == 'extra'): raise ValueError('incorrect deck zone')
            counts[alias or code] += 1
    for code, count in counts.items():
        cap = {'Forbidden':0,'Limited':1,'SemiLimited':2,'Unlimited':3}[limits['limits'].get(str(code),'Unlimited')]
        if count > cap: raise ValueError('banlist or alias limit exceeded')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('validate'); check.add_argument('--case', type=Path, required=True)
    problem = sub.add_parser('validate-problem'); problem.add_argument('--problem', type=Path, required=True)
    route = sub.add_parser('audit-information-route')
    for name in ('contract','samples','cdb','runner','output'):
        route.add_argument('--'+name,type=Path,required=True)
    route.add_argument('--evidence',action='append',required=True,metavar='ROLE=PATH')
    information = sub.add_parser('audit-information')
    for name in ('contract','samples','output'):
        information.add_argument('--'+name,type=Path,required=True)
    information.add_argument('--evidence',action='append',required=True,metavar='ROLE=PATH')
    native_probe = sub.add_parser('native-prompt-probe')
    from ygo_eval.native_prompt_probe import add_arguments as add_native_probe_arguments
    add_native_probe_arguments(native_probe)
    placement = sub.add_parser('native-tenki-placement-probe')
    from ygo_eval.native_tenki_placement import add_arguments as add_placement_arguments
    add_placement_arguments(placement)
    placement_confirmation = sub.add_parser('native-tenki-placement-confirmation')
    from ygo_eval.native_tenki_placement_confirmation import add_arguments as add_confirmation_arguments
    add_confirmation_arguments(placement_confirmation)
    placement_validation = sub.add_parser('native-tenki-placement-validation')
    from ygo_eval.native_tenki_placement_validation import add_arguments as add_validation_arguments
    add_validation_arguments(placement_validation)
    curry_validation = sub.add_parser('native-curry-option-validation')
    from ygo_eval.native_curry_option_validation import add_arguments as add_curry_validation_arguments
    add_curry_validation_arguments(curry_validation)
    curry_confirmation = sub.add_parser('native-curry-option-confirmation')
    from ygo_eval.native_curry_option_validation import add_confirmation_arguments
    add_confirmation_arguments(curry_confirmation)
    curry_verification = sub.add_parser('native-curry-option-verification')
    from ygo_eval.native_curry_option_validation import add_arguments as add_curry_verification_arguments
    add_curry_verification_arguments(curry_verification)
    curry_revalidation = sub.add_parser('native-curry-option-revalidation')
    from ygo_eval.native_curry_option_validation import add_arguments as add_curry_revalidation_arguments
    add_curry_revalidation_arguments(curry_revalidation)
    placement_preflight = sub.add_parser('audit-tenki-placement-preflight')
    for name in ('baseline-dir', 'experiment-dir', 'runner', 'build-record', 'output'):
        placement_preflight.add_argument('--' + name, type=Path, required=True)
    confirmation_runner_audit = sub.add_parser('audit-tenki-confirmation-runner')
    for name in ('baseline-dir', 'runner', 'build-record', 'output'):
        confirmation_runner_audit.add_argument('--' + name, type=Path, required=True)
    transition = sub.add_parser('prepare-tenki-baseline-transition')
    transition.add_argument('--baseline-dir', type=Path, required=True)
    transition.add_argument('--report-version', type=int, choices=(1, 2), default=1)
    transition.add_argument('--output', type=Path, required=True)
    preparation = sub.add_parser('prepare-prompt-probes')
    for name in ('cases','baseline-dir','core-source','output'):
        preparation.add_argument('--'+name,type=Path,required=True)
    ground_collapse = sub.add_parser('prepare-ground-collapse-probe')
    from ygo_eval.ground_collapse_preparation import add_arguments as add_ground_collapse_arguments
    add_ground_collapse_arguments(ground_collapse)
    history = sub.add_parser('audit-history')
    history.add_argument('--baseline-dir', type=Path, required=True)
    history.add_argument('--output', type=Path, required=True)
    curry_asset_audit = sub.add_parser('audit-curry-asset-binding')
    from ygo_eval.curry_asset_binding_audit import add_arguments as add_curry_asset_audit_arguments
    add_curry_asset_audit_arguments(curry_asset_audit)
    curry_input_recovery = sub.add_parser('audit-curry-input-recovery')
    from ygo_eval.curry_input_recovery_audit import add_arguments as add_curry_input_recovery_arguments
    add_curry_input_recovery_arguments(curry_input_recovery)
    curry_reservation = sub.add_parser('prepare-curry-consumption-reservation')
    from ygo_eval.curry_consumption_reservation import add_arguments as add_curry_reservation_arguments
    add_curry_reservation_arguments(curry_reservation)
    curry_ledger_handoff = sub.add_parser('audit-curry-ledger-handoff')
    from ygo_eval.curry_ledger_handoff_audit import add_arguments as add_curry_ledger_handoff_arguments
    add_curry_ledger_handoff_arguments(curry_ledger_handoff)
    curry_ledger_handoff_recovery = sub.add_parser('recover-curry-ledger-handoff')
    from ygo_eval.curry_ledger_handoff_recovery import add_arguments as add_curry_ledger_handoff_recovery_arguments
    add_curry_ledger_handoff_recovery_arguments(curry_ledger_handoff_recovery)
    audit = sub.add_parser('audit-corpus')
    audit.add_argument('--evidence', action='append', required=True, metavar='ROLE=PATH')
    audit.add_argument('--runner', type=Path, required=True)
    audit.add_argument('--output', type=Path, required=True)
    snapshot = sub.add_parser('evaluate-snapshot')
    for name in ('evidence','cdb','runner','output'):
        snapshot.add_argument('--'+name, type=Path, required=True)
    snapshot.add_argument('--report-version', type=int, choices=(1,2), default=1)
    followup = sub.add_parser('terminal-followup')
    from ygo_eval.terminal_followup import add_arguments as add_followup_arguments
    add_followup_arguments(followup)
    smoke = sub.add_parser('terminal-smoke')
    from ygo_eval.terminal_smoke import add_arguments as add_smoke_arguments
    add_smoke_arguments(smoke)
    terminal = sub.add_parser('terminal-regression')
    from ygo_eval.terminal_regression import add_arguments
    add_arguments(terminal)
    native = sub.add_parser('native-regression')
    for name in ('cases','runner','worker','build-record','old-ledger','output','identity','window-start'):
        native.add_argument('--'+name, type=Path, required=True)
    native.add_argument('--prepare-only', action='store_true')
    run = sub.add_parser('run')
    for name in ('cases','runner','ledger','output'):
        run.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    if args.command == 'native-prompt-probe':
        from ygo_eval.native_prompt_probe import native_prompt_probe
        try:
            report = native_prompt_probe(args)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error,subprocess.SubprocessError):
            print('native-prompt-probe refused: invalid or changed frozen input or output')
            return 2
        print(json.dumps(report,ensure_ascii=False))
        return 0 if report.get('successful') is True or report.get('prepared') is True else 1
    if args.command == 'native-tenki-placement-probe':
        from ygo_eval.native_tenki_placement import native_tenki_placement
        try:
            report = native_tenki_placement(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
            reason = str(error)
            if reason not in (
                'frozen_baseline_directory_required',
                'pinned_baseline_hash_mismatch',
                'historical_protected_input_changed',
                'old_zero_call_receipt_verification_failed',
                'candidate_identity_capture_failed',
                'build_source_identity_mismatch',
                'build_artifact_hash_mismatch',
                'workspace_source_changed',
                'experiment_window_expired',
            ):
                reason = 'invalid or changed frozen input, identity, ledger, or output'
            print('native-tenki-placement-probe refused: ' + reason)
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('prepared') is True or report.get('successful') is True else 1
    if args.command == 'native-tenki-placement-confirmation':
        from ygo_eval.native_tenki_placement_confirmation import native_tenki_placement_confirmation
        try:
            report = native_tenki_placement_confirmation(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-tenki-placement-confirmation refused: frozen input, build, ledger, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('prepared') is True or report.get('successful') is True else 1
    if args.command == 'native-tenki-placement-validation':
        from ygo_eval.native_tenki_placement_validation import native_tenki_placement_validation
        try:
            report = native_tenki_placement_validation(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-tenki-placement-validation refused: frozen input, build, ledger, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if (report.get('prepared') is True or report.get('successful') is True
                     or report.get('valid') is True) else 1
    if args.command == 'native-curry-option-validation':
        from ygo_eval.native_curry_option_validation import native_curry_option_validation
        try:
            report = native_curry_option_validation(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-curry-option-validation refused: frozen input, build, ledger, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if (report.get('prepared') is True or report.get('successful') is True
                     or report.get('valid') is True) else 1
    if args.command == 'native-curry-option-confirmation':
        from ygo_eval.native_curry_option_validation import native_curry_option_confirmation
        try:
            report = native_curry_option_confirmation(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-curry-option-confirmation refused: frozen input, build, ledger, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if (report.get('prepared') is True or report.get('successful') is True
                     or report.get('valid') is True) else 1
    if args.command == 'native-curry-option-verification':
        from ygo_eval.native_curry_option_validation import native_curry_option_verification
        try:
            report = native_curry_option_verification(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-curry-option-verification refused: frozen reservation, input, build, ledger, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if (report.get('prepared') is True or report.get('successful') is True
                     or report.get('valid') is True) else 1
    if args.command == 'native-curry-option-revalidation':
        from ygo_eval.native_curry_option_validation import native_curry_option_revalidation
        try:
            report = native_curry_option_revalidation(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-curry-option-revalidation refused: frozen recovery, reservation, input, build, ledger, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if (report.get('prepared') is True or report.get('successful') is True
                     or report.get('valid') is True) else 1
    if args.command == 'audit-tenki-placement-preflight':
        from ygo_eval.tenki_placement_diagnostics import audit_tenki_placement_preflight
        try:
            report = audit_tenki_placement_preflight(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('audit-tenki-placement-preflight refused: invalid frozen input, runner, or output')
            return 2
        print(json.dumps({
            'status': report['status'],
            'native_calls': 0,
            'execution_ready': False,
            'diagnostic': report.get('diagnostic'),
        }, ensure_ascii=False))
        return 0 if report.get('status') == 'passed' else 1
    if args.command == 'audit-tenki-confirmation-runner':
        from ygo_eval.tenki_confirmation_runner_audit import run_audit
        try:
            report = run_audit(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('audit-tenki-confirmation-runner refused: invalid frozen input, runner, or output')
            return 2
        print(json.dumps({
            'status': report['status'],
            'native_calls': 0,
            'execution_ready': False,
            'diagnostic': report.get('diagnostic'),
        }, ensure_ascii=False))
        return 0 if report.get('status') == 'passed' else 1
    if args.command == 'prepare-tenki-baseline-transition':
        from ygo_eval.native_tenki_placement import prepare_tenki_baseline_transition
        try:
            report = prepare_tenki_baseline_transition(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
            reason = str(error)
            if reason not in (
                'frozen_baseline_directory_required',
                'historical_protected_input_changed',
                'old_zero_call_receipt_verification_failed',
                'baseline_transition_inputs_changed_during_capture',
                'baseline_transition_output_exists',
            ):
                reason = 'invalid or changed frozen baseline transition input or output'
            print('prepare-tenki-baseline-transition refused: ' + reason)
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0
    if args.command == 'prepare-prompt-probes':
        from ygo_eval.prompt_probe_prepare import prepare_prompt_probes
        try:
            report = prepare_prompt_probes(args)
        except (ValueError,OSError,KeyError,TypeError):
            print('prepare-prompt-probes refused: invalid input or output')
            return 2
        print(json.dumps({'preparation_successful':report['preparation_successful'],'native_calls':0,'diagnostics':report['diagnostics']},ensure_ascii=False))
        return 0 if report['preparation_successful'] else 1
    if args.command == 'prepare-ground-collapse-probe':
        from ygo_eval.ground_collapse_preparation import prepare_ground_collapse_probe
        try:
            report = prepare_ground_collapse_probe(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
            print('prepare-ground-collapse-probe refused: fixed source or output check failed')
            return 2
        if args.verify_only:
            print(json.dumps({
                'valid': report['valid'],
                'preparation_successful': report['preparation_successful'],
                'native_calls': 0,
                'runner_process_calls': 0,
                'worker_calls': 0,
                'ffi_calls': 0,
            }, ensure_ascii=False))
            return 0 if report.get('valid') is True else 1
        print(json.dumps({
            'status': report.get('status'),
            'preparation_successful': report['preparation_successful'],
            'execution_ready': report['execution_ready'],
            'native_calls': 0,
            'runner_process_calls': 0,
            'worker_calls': 0,
            'ffi_calls': 0,
            'diagnostics': report['diagnostics'],
        }, ensure_ascii=False))
        return 0 if report.get('preparation_successful') is True else 1
    if args.command == 'audit-information-route':
        from ygo_eval.information_route import audit_information_route
        try:
            report = audit_information_route(args.contract,args.samples,args.evidence,args.cdb,args.runner,args.output)
        except (ValueError,OSError,KeyError,TypeError):
            print('audit-information-route refused: invalid input or output')
            return 2
        print(json.dumps({'successful':report['successful'],'native_calls':0,'diagnostics':report['diagnostics']},ensure_ascii=False))
        return 0 if report['successful'] else 1
    if args.command == 'audit-information':
        from ygo_eval.information_audit import audit_information
        try:
            report = audit_information(args.contract,args.samples,args.evidence,args.output)
        except (ValueError,OSError,KeyError,TypeError):
            print('audit-information refused: invalid input or output')
            return 2
        print(json.dumps({'successful':report['successful'],'native_calls':0,'diagnostics':report['diagnostics']},ensure_ascii=False))
        return 0 if report['successful'] else 1
    if args.command == 'audit-history':
        from ygo_eval.history_audit import audit_to_output
        try:
            report = audit_to_output(args)
        except (ValueError, OSError, KeyError, TypeError):
            print('audit-history refused: invalid or changed historical input or output')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('valid') is True else 1
    if args.command == 'audit-curry-asset-binding':
        from ygo_eval.curry_asset_binding_audit import run_audit
        try:
            report = run_audit(args)
        except Exception:
            print('audit-curry-asset-binding refused: invalid frozen input, isolated runner, or output')
            return 2
        print(json.dumps({
            'status': report['status'],
            'native_calls': 0,
            'execution_ready': False,
            'diagnostic': report.get('diagnostic'),
        }, ensure_ascii=False))
        return 0 if report.get('status') == 'passed' else 1
    if args.command == 'audit-curry-input-recovery':
        from ygo_eval.curry_input_recovery_audit import audit_to_output
        try:
            report = audit_to_output(args)
        except Exception:
            print('audit-curry-input-recovery refused: fixed frozen input or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('status') == 'passed' else 1
    if args.command == 'prepare-curry-consumption-reservation':
        from ygo_eval.curry_consumption_reservation import audit_to_output
        try:
            report = audit_to_output(args)
        except Exception:
            print('prepare-curry-consumption-reservation refused: fixed source or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('status') == 'passed' or report.get('valid') is True else 1
    if args.command == 'audit-curry-ledger-handoff':
        from ygo_eval.curry_ledger_handoff_audit import run_audit, AuditPublicationError
        try:
            report = run_audit(args)
        except AuditPublicationError as error:
            print(
                'audit-curry-ledger-handoff publication failed: '
                f'phase={error.phase} code={error.code} diagnostic={error.diagnostic_id}'
            )
            return 2
        except Exception:
            print('audit-curry-ledger-handoff refused: fixed source, runner, or output check failed')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('status') == 'passed' else 1
    if args.command == 'recover-curry-ledger-handoff':
        from ygo_eval.curry_ledger_handoff_recovery import (
            RecoveryPublicationError, audit_to_output,
        )
        try:
            report = audit_to_output(args)
        except RecoveryPublicationError as error:
            print(
                'recover-curry-ledger-handoff publication failed: '
                f'phase={error.phase} code={error.code} diagnostic={error.diagnostic_id}'
            )
            return 2
        except Exception as error:
            reason = str(error)
            if not re.fullmatch(r'[a-z][a-z0-9_]{1,100}', reason):
                reason = 'fixed_source_or_output_check_failed'
            print(f'recover-curry-ledger-handoff refused: {reason}')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('valid') is True else 1
    if args.command == 'validate-problem':
        from ygo_eval.research_problem import validate_problem
        try:
            report = validate_problem(json.loads(args.problem.read_bytes()))
        except (ValueError, OSError, KeyError, TypeError):
            print('validate-problem refused: invalid frozen research problem')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0
    if args.command == 'terminal-followup':
        from ygo_eval.terminal_followup import terminal_followup
        try:
            report = terminal_followup(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
            reason = str(error)
            if reason not in ('old9_runner_unavailable','old9_build_provenance_differs','old9_zero_call_receipt_verifier_unavailable'):
                reason = 'invalid or changed frozen input, ledger, or output'
            print('terminal-followup refused: '+reason)
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('prepared') or report.get('successful') else 1
    if args.command == 'terminal-smoke':
        from ygo_eval.terminal_smoke import terminal_smoke
        try:
            report = terminal_smoke(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('terminal-smoke refused: invalid or changed frozen input, ledger, or output')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('prepared') or report.get('successful') else 1
    if args.command == 'terminal-regression':
        from ygo_eval.terminal_regression import terminal_regression
        try:
            report = terminal_regression(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('terminal-regression refused: invalid or changed frozen input, ledger, or output')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('prepared') or report.get('successful') else 1
    if args.command == 'native-regression':
        from ygo_eval.native_regression import native_regression
        try:
            report = native_regression(args)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
            print('native-regression refused: invalid or changed frozen input, ledger, or output')
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get('prepared') or report.get('successful') else 1
    if args.command == 'evaluate-snapshot':
        from ygo_eval.snapshot_eval import evaluate_snapshot
        try:
            report = evaluate_snapshot(args.evidence,args.cdb,args.runner,args.output,args.report_version)
        except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError):
            print('evaluate-snapshot refused: invalid or changed evidence, CDB, auditor, or output')
            return 2
        print(json.dumps({'evaluations':report['evaluations'],'native_calls':0}))
        return 0
    if args.command == 'audit-corpus':
        from ygo_eval.prompt_audit import audit_corpus
        try:
            report = audit_corpus(args.evidence, args.runner, args.output)
        except (ValueError, OSError, subprocess.SubprocessError):
            print('audit-corpus refused: invalid or changed input, auditor, or output')
            return 2
        print(json.dumps({'successful':report['successful'], 'summary':report['summary'], 'native_calls':0}))
        return int(not report['successful'])
    if args.command == 'validate':
        print(json.dumps(validate_case(json.loads(args.case.read_text(encoding='utf-8'))),ensure_ascii=False)); return
    from ygo_data.identity import checked_output, regular_file
    repo = Path(__file__).resolve().parents[2]
    args.output = checked_output(repo,args.output)
    args.ledger = checked_output(repo,args.ledger)
    for path in (args.output,args.ledger):
        relative = path.relative_to(repo / 'data' / 'runtime')
        if 'research' not in relative.parts:
            raise ValueError('dedicated ignored research directory required')
    inputs = [regular_file(args.cases), regular_file(args.runner)]
    source = json.loads(args.cases.read_text(encoding='utf-8'))
    _object(source, ('context','cases'), 'batch input')
    if not isinstance(source['cases'],list) or not 1 <= len(source['cases']) <= 8: raise ValueError('one to eight cases required')
    ids = set(); cases = []
    for item in source['cases']:
        _object(item, ('case','request','banlist_path'), 'batch case')
        inputs.append(regular_file(item['banlist_path']))
        inputs.extend(Path(value).absolute() for key,value in item['request']['engine'].items() if key.endswith('_path'))
        case = item['case']; validate_sources(case,item['request'],Path(item['banlist_path']))
        if case['purpose'] != 'protocol_audit' or case['randomness']['model'] != 'frozen_scenario' or case['case_id'] in ids: raise ValueError('only unique protocol audit cases supported')
        ids.add(case['case_id']); cases.append({'case_id':case['case_id'],'request':item['request']})
    for source_path in inputs:
        if args.ledger == source_path or args.output == source_path or source_path.is_relative_to(args.output) or args.output.is_relative_to(source_path) or args.ledger.is_relative_to(source_path):
            raise ValueError('research output overlaps input or runtime assets')
    # Bind all user-frozen contracts, including information/probability, into journal context.
    context = hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    args.output.mkdir(parents=True,exist_ok=True)
    batch = {'context':context,'ledger':str(args.ledger.resolve()),'output':str(args.output.resolve()),'cases':cases}
    batch_path = args.output / ('batch-'+context+'.json')
    encoded = json.dumps(batch,ensure_ascii=False,indent=2).encode()
    if batch_path.exists() and batch_path.read_bytes() != encoded: raise ValueError('batch intent already differs')
    if not batch_path.exists():
        with batch_path.open('xb') as stream:
            stream.write(encoded)
    subprocess.run([str(args.runner.resolve()),str(batch_path.resolve())],check=True)

if __name__ == '__main__':
    raise SystemExit(main())
