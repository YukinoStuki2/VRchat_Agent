"""Reproducibly add a unique owned transport; never patch an installed package.

Build-time Linux tool. Unity's asmref groups ONLY this folder into the pinned
upstream editor assembly so existing internal helpers can be reused unchanged.
Actual Unity import / Mono validation is a separate required acceptance layer.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
DELTA = ROOT / 'dependencies/coplay-10.2.0-owned'
SOURCE = 'Editor/Services/Transport/Transports/WebSocketTransportClient.cs'
TYPE = 'CandidateOwnedWebSocketTransportClient'
ASM_GUID = '98f702da6ca044be59a864a9419c4eab'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def materialize(upstream, destination):
    upstream, destination = Path(upstream), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('additive_destination_must_be_new')
    provenance = json.loads((DELTA / 'PROVENANCE.json').read_text())
    original = (upstream / SOURCE).read_bytes()
    delta = DELTA / 'transport.patch'
    if (digest(original) != provenance['upstream_sha256'] or
            digest(delta.read_bytes()) != provenance['patch_sha256']):
        raise ValueError('owned_transport_input_drift')
    asm = json.loads((upstream / 'Editor/MCPForUnity.Editor.asmdef').read_text())
    meta = (upstream / 'Editor/MCPForUnity.Editor.asmdef.meta').read_text()
    guid = re.findall(r'^guid: ([0-9a-f]{32})$', meta, re.M)
    if guid != [ASM_GUID] or asm.get('name') != 'MCPForUnity.Editor':
        raise ValueError('pinned_editor_assembly_required')
    license_bytes = (upstream.parent / 'LICENSE').read_bytes()
    with tempfile.TemporaryDirectory(prefix='candidate-transport-source-') as td:
        work = Path(td)
        source = work / (TYPE + '.cs')
        source.write_bytes(original)
        result = subprocess.run(['patch', '--batch', '--fuzz=0', str(source), str(delta)],
                                capture_output=True, text=True, timeout=10)
        if result.returncode or digest(source.read_bytes()) != provenance['patched_sha256']:
            raise ValueError('owned_transport_patch_mismatch')
        # Only public ownership entrypoint; no discovery constructor is exposed.
        text = re.sub(r'\bWebSocketTransportClient\b', TYPE, source.read_text())
        text = text.replace('public class ' + TYPE, 'public sealed class ' + TYPE)
        text = text.replace('public ' + TYPE + '(IToolDiscoveryService',
                            'private ' + TYPE + '(IToolDiscoveryService')
        source.write_text(text, encoding='utf-8', newline='\n')
        (work / 'CandidateOwnedTransport.asmref').write_text(
            json.dumps({'reference': 'GUID:' + ASM_GUID}, indent=2) + '\n')
        (work / 'LICENSE.md').write_bytes(license_bytes)
        record = {'upstream_commit': provenance['upstream_commit'], 'upstream_path': SOURCE,
                  'upstream_sha256': provenance['upstream_sha256'],
                  'patch_sha256': provenance['patch_sha256'],
                  'additive_type': TYPE, 'source_sha256': digest(source.read_bytes()),
                  'assembly_reference_guid': ASM_GUID,
                  'installed_upstream_files_modified': False,
                  'unity_import_verified': False}
        (work / 'PROVENANCE.json').write_text(json.dumps(record, indent=2) + '\n')
        for file in list(work.iterdir()):
            # A patch backup is not distributable content.
            if file.name.endswith(('.orig', '.rej')):
                raise ValueError('unexpected_patch_artifact')
            stable = uuid.uuid5(uuid.NAMESPACE_URL,
                               'https://github.com/YukinoStuki2/VRchat_Agent/owned/' + file.name)
            file.with_name(file.name + '.meta').write_text(
                'fileFormatVersion: 2\nguid: ' + stable.hex + '\n')
        shutil.copytree(work, destination)  # refuses existing targets; no installed edits
