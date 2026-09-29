"""Assemble reviewed-by-hash source bytes IN MEMORY; no ZIP/install/approval.

The source inventory is a developer build input, not an independent approval.
Portable Python, wheel licenses and product gates remain separate requirements.
"""
from pathlib import Path, PurePosixPath
import hashlib
import importlib.util
import json
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('candidate_packer', ROOT / 'build_candidate.py')
assert _spec is not None and _spec.loader is not None
packer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(packer)


def collect(root=ROOT):
    root = Path(root)
    inventory = json.loads(packer.base.read_regular(root, 'distribution/source-inputs.json'))
    if type(inventory.get('schema')) is not int or inventory['schema'] != 1 or not isinstance(inventory.get('files'), dict):
        raise ValueError('source_inventory_required')
    result = {}
    destinations = {}
    for name in inventory['files']:
        path = PurePosixPath(name)
        if (str(path) != name or path.is_absolute() or '..' in path.parts or
                re.search(r'[\\:\x00-\x1f]', name) or
                path.parts[0] not in {'package', 'runtime', 'launcher', 'diagnostics',
                                      'native', 'dependencies', 'distribution', 'catalog'} or
                any(p in {'tests', 'evidence', '__pycache__'} or p.startswith('.') for p in path.parts)):
            raise ValueError('source_path_invalid')
        destinations[name] = name[len('package/'):] if name.startswith('package/') else 'Runtime~/' + name
    if len({d.casefold() for d in destinations.values()}) != len(destinations):
        raise ValueError('source_destination_alias')
    for name, destination in destinations.items():
        data = packer.base.read_regular(root, name)
        if hashlib.sha256(data).hexdigest() != inventory['files'][name]:
            raise ValueError('source_drift: ' + name)
        result[destination] = data
    required = {'package.json', 'LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md',
                'Editor/Yukino.VRChatAgent.Editor.asmdef', 'Editor/CandidateSession.cs',
                'Runtime~/launcher/editor_owner.py', 'Runtime~/runtime/__main__.py',
                'Runtime~/native/LICENSE', 'Runtime~/dependencies/mcp-1.29.1/LICENSE'}
    if not required <= result.keys():
        raise ValueError('incomplete_source_payload')
    # Stable namespace; preserve all supplied upstream/additive GUIDs unchanged.
    for name in tuple(result):
        if name.endswith('.meta'):
            continue
        entries = {name: False, **{str(p): True for p in PurePosixPath(name).parents if str(p) != '.'}}
        for entry, folder in entries.items():
            meta = entry + '.meta'
            if meta not in result:
                guid = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/YukinoStuki2/VRchat_Agent/candidate/' + entry)
                result[meta] = ('fileFormatVersion: 2\nguid: ' + guid.hex + '\n' +
                                ('folderAsset: yes\n' if folder else '')).encode()
    packer.validate_sources(result)
    return result
