"""Offline, non-qualifying review of the frozen 39-card language candidates."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
SOURCE_PATH = REPO / 'configs/language-sources-2026-10-19.json'
BASELINE = REPO / 'data/runtime/baseline-2026-10-19/data'
SAMPLE_PATH = BASELINE / 'releases.json'
RECORDS_PATH = BASELINE / 'language-records.json'
FIELD_NAMES = ('name', 'text', 'alias', 'archetypes')
DB_NAMES = {
    'mycard-zh-CN-217ae165': BASELINE / 'ygopro-database-locales-zh-CN-cards.cdb',
    'mycard-zh-SC-217ae165': BASELINE / 'ygopro-database-locales-zh-SC-cards.cdb',
}
STATUSES = {'candidate', 'missing', 'conflict', 'unknown'}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate_json_key:{key}')
            result[key] = value
        return result

    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs)


def _canonical_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _source_language(source: dict) -> str:
    language = source.get('language')
    return language if language in ('zh-Hans', 'zh-Hant') else 'und'


def _field(status: str, source: str, reason: str, candidate_hash: str | None = None) -> dict:
    value = {'status': status, 'source': source, 'reason': reason}
    if candidate_hash is not None:
        value['candidate_sha256'] = candidate_hash
    return value


def audit_language_fields(card_ids: list[int], sources: list[dict], records: list[dict], catalogs: dict[str, dict[int, dict]]) -> dict:
    """Compare candidate bytes without returning candidate text or granting language trust."""
    if (not isinstance(card_ids, list) or not card_ids
            or any(type(code) is not int or not 0 < code <= 0xFFFFFFFF for code in card_ids)
            or len(card_ids) != len(set(card_ids))):
        raise ValueError('sample_requires_unique_u32_card_ids')
    if not isinstance(sources, list) or not isinstance(records, list) or not isinstance(catalogs, dict):
        raise ValueError('language_review_inputs_invalid')
    source_by_id = {}
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get('id'), str) or not source['id']:
            raise ValueError('language_source_id_required')
        if source['id'] in source_by_id:
            raise ValueError('duplicate_language_source_id')
        if not re.fullmatch(r'[0-9a-f]{64}', str(source.get('sha256', ''))):
            raise ValueError('language_source_sha256_invalid')
        source_by_id[source['id']] = source
    if set(catalogs) != set(source_by_id):
        raise ValueError('language_catalog_source_set_mismatch')

    record_map = {}
    names: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in records:
        if not isinstance(row, dict) or type(row.get('card_id')) is not int or row['card_id'] not in card_ids:
            raise ValueError('language_record_card_id_invalid')
        source_id = row.get('name', {}).get('source') if isinstance(row.get('name'), dict) else None
        source_id = source_id or (row.get('text', {}).get('source') if isinstance(row.get('text'), dict) else None)
        if source_id not in source_by_id:
            raise ValueError('language_record_source_unknown')
        if row.get('language') != source_by_id[source_id].get('language'):
            raise ValueError('language_record_category_mismatch')
        key = (source_id, row['card_id'])
        if key in record_map:
            raise ValueError('duplicate_language_record')
        record_map[key] = row

    output_cards = []
    for card_id in sorted(card_ids):
        output_sources = {}
        for source_id, source in source_by_id.items():
            db_row = catalogs[source_id].get(card_id)
            if db_row is not None and not isinstance(db_row, dict):
                raise ValueError('catalog_row_invalid')
            record = record_map.get((source_id, card_id), {})
            fields = {}
            for field_name, db_key in (('name', 'name'), ('text', 'text')):
                candidate = db_row.get(db_key) if db_row else None
                record_entry = record.get(field_name)
                record_value = record_entry.get('value') if isinstance(record_entry, dict) else None
                values = [value for value in (candidate, record_value) if isinstance(value, str) and value.strip()]
                hashes = {_canonical_hash(value) for value in values}
                if not values:
                    fields[field_name] = _field('missing', source_id, 'candidate_value_absent')
                elif len(hashes) > 1:
                    fields[field_name] = _field('conflict', source_id, 'candidate_sources_disagree')
                else:
                    fields[field_name] = _field('candidate', source_id, 'candidate_not_semantically_reviewed', next(iter(hashes)))
                if field_name == 'name' and values:
                    names[(source_id, values[0].casefold())].add(card_id)
            fields['alias'] = _field('unknown', source_id, 'localized_alias_mapping_not_defined')
            fields['archetypes'] = _field('unknown', source_id, 'localized_archetype_mapping_not_defined')
            output_sources[source_id] = {
                'language_category': _source_language(source),
                'language_category_status': 'candidate' if _source_language(source) != 'und' else 'unknown',
                'semantic_review': 'not_reviewed',
                'usage_basis': {'status': 'unknown', 'reason': 'redistribution_or_official_usage_basis_not_established'},
                'redistribution': source.get('license', {}).get('redistribution', 'unknown'),
                'fields': fields,
                'engine_metadata': {
                    'alias_id': db_row.get('engine_alias', 0) if db_row else None,
                    'setcode': db_row.get('setcode', 0) if db_row else None,
                    'note': 'engine alias and setcode are not Chinese-name aliases or localized archetypes',
                },
            }
        output_cards.append({'card_id': card_id, 'sources': output_sources})
    ambiguous = []
    for (source_id, name), ids in sorted(names.items()):
        if len(ids) > 1:
            ambiguous.append({'source': source_id, 'candidate_sha256': _canonical_hash(name), 'card_ids': sorted(ids)})
    return {
        'schema_version': 1,
        'kind': 'language_field_review',
        'scope': 'explicit-39-card-candidates',
        'qualified': False,
        'qualification_gate': 'independent_semantic_and_usage_review_required',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_manifest_checked_date': None,
        'sample_card_ids': sorted(card_ids),
        'source_count': len(sources),
        'record_count': len(records),
        'language_categories': {source['id']: _source_language(source) for source in sources},
        'sources': sources,
        'ambiguous_names': ambiguous,
        'cards': output_cards,
    }


def _load_catalog(path: Path) -> dict[int, dict]:
    before = _sha256(path)
    uri = f'file:{quote(path.resolve().as_posix(), safe="/:\\")}\u003fmode=ro'
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            'SELECT d.id, t.name, t.desc, d.alias, d.setcode FROM datas d LEFT JOIN texts t ON t.id=d.id'
        ).fetchall()
    finally:
        connection.close()
    after = _sha256(path)
    if before != after:
        raise ValueError('catalog_changed_during_read')
    return {row[0]: {'name': row[1], 'text': row[2], 'engine_alias': row[3], 'setcode': row[4]} for row in rows}


def build_frozen_report() -> tuple[dict, dict[str, str]]:
    paths = [SOURCE_PATH, SAMPLE_PATH, RECORDS_PATH, *DB_NAMES.values()]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError('frozen_language_input_missing_or_linked')
    initial_hashes = {str(path.relative_to(REPO)).replace('\\', '/'): _sha256(path) for path in paths}
    sources_payload = _strict_json(SOURCE_PATH)
    sample = _strict_json(SAMPLE_PATH)
    records = _strict_json(RECORDS_PATH)
    if not isinstance(sources_payload, dict) or not isinstance(sample, dict) or not isinstance(records, list):
        raise ValueError('frozen_language_json_shape_invalid')
    sources = sources_payload.get('sources')
    release_rows = sample.get('records')
    if not isinstance(sources, list) or not isinstance(release_rows, list):
        raise ValueError('frozen_language_json_shape_invalid')
    ids = [row.get('card_id') for row in release_rows if isinstance(row, dict) and row.get('status') == 'released' and row.get('region') == 'OCG']
    if len(ids) != 39 or len(set(ids)) != 39:
        raise ValueError('frozen_release_sample_must_have_39_unique_released_ocg_cards')
    catalogs = {source['id']: _load_catalog(DB_NAMES[source['id']]) for source in sources if source.get('id') in DB_NAMES}
    if len(catalogs) != len(sources):
        raise ValueError('frozen_language_source_unmapped')
    for source in sources:
        expected = source.get('sha256')
        path = DB_NAMES[source['id']]
        if expected != initial_hashes[str(path.relative_to(REPO)).replace('\\', '/')]:
            raise ValueError('frozen_catalog_hash_does_not_match_source_pin')
    report = audit_language_fields(ids, sources, records, catalogs)
    from .language import audit_language
    legacy_audit = audit_language(ids, sources, records)
    final_hashes = {str(path.relative_to(REPO)).replace('\\', '/'): _sha256(path) for path in paths}
    if initial_hashes != final_hashes:
        raise ValueError('frozen_language_inputs_changed_during_audit')
    report['inputs'] = initial_hashes
    report['source_manifest_checked_date'] = sources_payload.get('checked_date')
    report['legacy_audit_unresolved'] = legacy_audit['unresolved']
    return report, final_hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='ygo-language-review')
    sub = parser.add_subparsers(dest='command', required=True)
    audit = sub.add_parser('audit')
    audit.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command != 'audit':
        return 2
    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    try:
        if output.exists():
            raise ValueError('output_already_exists')
        report, _ = build_frozen_report()
        if any(output == path.resolve() for path in [SOURCE_PATH, SAMPLE_PATH, RECORDS_PATH, *DB_NAMES.values()]):
            raise ValueError('output_must_not_overwrite_input')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f'ERROR: language_review_failed:{type(error).__name__}')
        return 1
    print(f'OK: reviewed {len(report["cards"])} cards; qualified=false')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
