"""Read-only, installed-source operation inventory; never imported by a gate."""
import json
import hashlib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def page(offset=0, limit=12):
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 20:
        raise ValueError('invalid_catalog_page')
    try:
        inventory = json.loads((ROOT/'catalog/native-inventory.json').read_text(encoding='utf-8'))
        tools = inventory['tools']
        if (inventory['schema_version'] != 1 or inventory['permission_grant'] is not False
                or inventory['product_ready'] is not False or type(tools) is not list
                or inventory['count'] != len(tools) or not 1 <= len(tools) <= 256
                or len({row['name'] for row in tools}) != len(tools)
                or [row['name'] for row in tools] != sorted(row['name'] for row in tools)):
            raise ValueError('catalog_invalid')
        sources = {}
        for row in tools:
            if row['enabled_by_catalog'] is not False or row['default_decision'] != 'deny':
                raise ValueError('catalog_invalid')
            anchor = row['source']
            path = PurePosixPath(anchor['path'])
            if (not anchor['path'].startswith('Server/src/services/tools/')
                    or str(path) != anchor['path'] or '..' in path.parts
                    or '\\' in anchor['path'] or ':' in anchor['path'] or path.suffix != '.py'):
                raise ValueError('catalog_invalid')
            prior = sources.setdefault(anchor['path'], anchor['sha256'])
            if prior != anchor['sha256']:
                raise ValueError('catalog_invalid')
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('catalog_invalid') from exc
    for path, expected in sources.items():
        try:
            source = ROOT/'native'/PurePosixPath(path).relative_to('Server')
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError('catalog_source_mismatch') from exc
        if actual != expected:
            raise ValueError('catalog_source_mismatch')
    if offset > len(tools):
        raise ValueError('invalid_catalog_page')
    rows = [{k: row[k] for k in ('name','name_zh','unity_target','group','declared_actions',
             'has_action_parameter','source','default_decision','enabled_by_catalog',
             'implemented_candidate_read_actions','audit_note_zh')} for row in tools[offset:offset+limit]]
    next_offset = offset + len(rows)
    return {'schema_version': 1, 'permission_grant': False, 'product_ready': False,
            'scope_zh': inventory['scope_zh'], 'total': len(tools), 'offset': offset,
            'returned': len(rows), 'next_offset': next_offset if next_offset < len(tools) else None,
            'tools': rows}
