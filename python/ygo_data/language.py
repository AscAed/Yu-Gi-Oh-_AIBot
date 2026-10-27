"""Separate language-source audit; never infers card IDs or translation truth."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import re
from pathlib import Path

from .identity import checked_output

FIELDS = ('name', 'text', 'alias', 'archetypes')
LANGUAGES = ('zh-Hans', 'zh-Hant')
RECORD_FIELDS = frozenset(('card_id', 'language', *FIELDS))
VALUE_FIELDS = frozenset(('value', 'source', 'status'))


def audit_language(card_ids: list[int], sources: list[dict], records: list[dict]) -> dict:
    """Audit provenance per field; source/license gaps block formal qualification."""
    if (not isinstance(card_ids, list) or any(type(code) is not int or code <= 0 for code in card_ids)
            or len(card_ids) != len(set(card_ids))):
        raise ValueError('sample requires unique positive integer card IDs')
    if not isinstance(sources, list) or not isinstance(records, list):
        raise ValueError('sources and records must be arrays')
    for source in sources:
        if not isinstance(source, dict) or any(not isinstance(source.get(key), str) or not source[key] for key in ('id', 'language', 'version')):
            raise ValueError('source ID, language and precise version required')
        if not isinstance(source.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', source['sha256']):
            raise ValueError('source SHA256 must be lowercase hexadecimal')
        license_info = source.get('license')
        if not isinstance(license_info, dict) or license_info.get('redistribution') not in ('permitted', 'prohibited', 'unknown'):
            raise ValueError('source redistribution status required')
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('language record must be an object')
        if set(row) - RECORD_FIELDS:
            raise ValueError('language record contains unknown fields')
        if type(row.get('card_id')) is not int or row['card_id'] <= 0:
            raise ValueError('language record requires positive integer card ID')
        if not isinstance(row.get('language'), str) or row['language'] not in LANGUAGES:
            raise ValueError('language record requires a supported language')
        for field in FIELDS:
            if field not in row:
                continue
            entry = row[field]
            if not isinstance(entry, dict):
                raise ValueError('language field must be an object')
            if set(entry) - VALUE_FIELDS:
                raise ValueError('language field contains unknown fields')
            if (entry.get('status') not in ('verified', 'unverified', 'missing', 'ambiguous')
                    or not isinstance(entry.get('source'), str) or not entry['source']):
                raise ValueError('language field requires source and recognized status')
            value = entry.get('value')
            if field in ('name', 'text'):
                valid = isinstance(value, str)
            else:
                valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
            if not valid:
                raise ValueError('invalid language field value type')
    issues = []
    source_ids = {source['id']: source for source in sources}
    if len(source_ids) != len(sources):
        issues.append('duplicate_source_id')
    for source in sources:
        for field in ('version', 'sha256', 'language'):
            if not source.get(field):
                issues.append(f"source_metadata_missing:{source['id']}:{field}")
        if source.get('license', {}).get('redistribution') != 'permitted':
            issues.append(f"redistribution_unresolved:{source['id']}")
    seen = set()
    names = defaultdict(set)
    present = set()
    for row in records:
        card_id = row['card_id']
        language = row.get('language')
        key = (card_id, language)
        if key in seen:
            issues.append(f'duplicate_mapping:{card_id}:{language}')
        seen.add(key)
        if card_id not in card_ids:
            issues.append(f'unexpected_card_id:{card_id}')
        present.add(card_id)
        for field in FIELDS:
            entry = row.get(field)
            if not isinstance(entry, dict) or entry.get('status') != 'verified' or not entry.get('value'):
                issues.append(f'field_unverified:{card_id}:{language}:{field}')
            if isinstance(entry, dict):
                source = source_ids.get(entry.get('source'))
                if source is None:
                    issues.append(f'unknown_source:{card_id}:{language}:{field}')
                elif source.get('language') != language:
                    issues.append(f'source_language_mismatch:{card_id}:{language}:{field}')
        name = row.get('name', {}).get('value')
        if name:
            names[(language, name)].add(card_id)
    missing = sorted(set(card_ids) - present)
    for card_id in card_ids:
        for language in LANGUAGES:
            if (card_id, language) not in seen:
                issues.append(f'language_mapping_missing:{card_id}:{language}')
    ambiguous = [{'language': language, 'name': name, 'card_ids': sorted(ids)}
                 for (language, name), ids in sorted(names.items()) if len(ids) > 1]
    # Names shared by IDs are disclosed and must not resolve a query to a guessed ID.
    return {'schema_version': 1, 'scope': 'explicit-card-id-sample',
            'qualified': False, 'qualification_gate': 'independent_semantic_review_not_implemented',
            'provenance_checks_passed': not issues and not missing, 'sources': sources,
            'sample_card_ids': sorted(set(card_ids)), 'record_count': len(records),
            'missing_card_ids': missing, 'ambiguous_names': ambiguous,
            'unresolved': sorted(set(issues)), 'records': records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['audit'])
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--sample', type=Path, required=True, help='release evidence records define sample IDs')
    parser.add_argument('--records', type=Path, help='local independent language records; no guessing if absent')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = checked_output(Path.cwd(), args.output)
    if args.output.resolve() in {path.resolve() for path in (args.sources, args.sample, args.records) if path is not None}:
        parser.error('output must not overwrite input sources or records')
    try:
        sources = json.loads(args.sources.read_text(encoding='utf-8'))['sources']
        ids = [row['card_id'] for row in json.loads(args.sample.read_text(encoding='utf-8'))['records']]
        records = json.loads(args.records.read_text(encoding='utf-8')) if args.records else []
        report = audit_language(ids, sources, records)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(f'invalid language audit input: {error}')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
