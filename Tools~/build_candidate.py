#!/usr/bin/env python3
"""Build a reviewed local source candidate, not an installation or release.
No network, git writes, keys, Unity process, or generated runtime binaries.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

TOP = {'package.json','package.json.meta','README.md','README.md.meta','LICENSE','LICENSE.meta',
       'THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md.meta','Editor.meta','START_HERE.md'}
PACKAGE = 'Packages~/com.yukino.vrchat-managed-editing'
# Reviewed filenames, not extension globs. New source files require inventory review.
# Runtime/log/evidence directories and arbitrary JSON/config files are never scanned.
INVENTORY = {
    '': TOP,
    'Editor': {name+suffix for name in (
        'DynamicsStackPerformanceTools.cs', 'MaterialAnimatorExpressionTools.cs',
        'OutfitValidationTools.cs', 'ProjectAvatarTools.cs', 'ReadOnlyCommon.cs',
        'Yukino.VRChatReadonlyMcp.Editor.asmdef') for suffix in ('', '.meta')},
    PACKAGE: {name+suffix for name in (
        'package.json', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
        for suffix in ('', '.meta')} | {'Editor.meta'},
    PACKAGE+'/Editor': {name+suffix for name in (
        'AssemblyInfo.cs', 'FacePreview.cs', 'ManagedSession.cs', 'ManagedTools.cs',
        'ManagedWindow.cs', 'Yukino.VRChatManagedEditing.Editor.asmdef')
        for suffix in ('', '.meta')} | {'Core.meta'},
    PACKAGE+'/Editor/Core': {'GatePolicy.cs', 'GatePolicy.cs.meta'},
    'Tests~': {'UNITY_ACCEPTANCE.md', 'test_distribution.py', 'test_managed_wiring.py',
               'test_preview_ui.py', 'test_reported_regressions.py'},
    'Tests~/Unity': {'ManagedSmokeTests.cs', 'Yukino.VRChatManagedEditing.Tests.asmdef'},
    'Tests~/core': {'.gitignore', 'CoreTests.csproj', 'NuGet.Config', 'Program.cs', 'README.md', 'run.py'},
    'Tests~/core/compatibility': {'CoreCompatibility.csproj'},
    'Tests~/syntax': {'Program.cs', 'SyntaxCheck.csproj'},
    'Tools~': {'build_candidate.py'},
    'Tools~/managed_bridge': {'.gitignore', 'README.zh-CN.md', 'TDD.md', 'bridge.py',
                              'test_bridge.py', 'test_sdk_handshake.py', 'test_reported_regressions.py'},
}

def digest(data): return hashlib.sha256(data).hexdigest()

def source_files(root):
    root = Path(root).resolve()
    result = []
    for directory, filenames in INVENTORY.items():
        folder = root/directory
        for part in (folder, *folder.parents):
            if part == root: break
            if part.is_symlink(): raise ValueError('symlink in candidate scope: '+directory)
        for filename in filenames:
            path = folder/filename
            name = path.relative_to(root).as_posix()
            if path.is_symlink(): raise ValueError('symlink in candidate scope: '+name)
            if not path.exists(): continue
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError('Candidate must be a regular file: '+name)
            result.append(name)
    return sorted(result)

def read_candidate(root, name):
    """Read a contained regular file; not a sandbox for a hostile local writer."""
    root, rel = Path(root).resolve(), Path(name)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Candidate path must be contained: '+str(name))
    path = root/rel
    for part in (path, *path.parents):
        if part == root: break
        if part.is_symlink(): raise ValueError('symlink in candidate scope: '+str(name))
    if not path.resolve().is_relative_to(root):
        raise ValueError('Candidate path must be contained: '+str(name))
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Candidate must be a regular file: '+str(name))
    # NOFOLLOW closes the final-component symlink race where supported (Linux).
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Candidate must be a regular file: '+str(name))
        return stream.read()


def hashes(root,names):
    return {name:digest(read_candidate(root, name)) for name in names}

def build(root, destination):
    root, destination = Path(root),Path(destination)
    evidence_bytes=read_candidate(root, 'VERIFICATION.json')
    evidence=json.loads(evidence_bytes)
    if evidence.get('local_checks_passed') is not True or evidence.get('independent_source_reviews_passed') is not True or evidence.get('unity_verified') is not False:
        raise ValueError('Candidate verification gate not satisfied')
    names=source_files(root)
    if hashes(root,names) != evidence.get('source_sha256'): raise ValueError('Verified source snapshot drift')
    names += ['VERIFICATION.json']
    if (root/'VERIFICATION.md').exists() or (root/'VERIFICATION.md').is_symlink():names.append('VERIFICATION.md')
    payload={name:read_candidate(root, name) for name in names}
    # Validate the frozen payload against the original gate/source snapshot.
    if any(digest(payload[name])!=evidence['source_sha256'][name] for name in evidence['source_sha256']):raise ValueError('Source snapshot changed while packaging')
    if payload['VERIFICATION.json']!=evidence_bytes or read_candidate(root, 'VERIFICATION.json')!=evidence_bytes:raise ValueError('Verification snapshot changed')
    manifest={name:digest(content) for name,content in sorted(payload.items())}
    payload['MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():raise ValueError('Refusing to replace an existing artifact')
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(payload.items()):
            info=zipfile.ZipInfo(name, date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644 << 16
            archive.writestr(info,content)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:raise ValueError('Archive CRC failure')
        if set(archive.namelist())!=set(payload):raise ValueError('Archive member mismatch')
        if any(archive.read(name)!=content for name,content in payload.items()):raise ValueError('Archive bytes mismatch')
    return {'artifact':str(destination.resolve()),'file_count':len(payload),'bytes':destination.stat().st_size,'zip_sha256':digest(destination.read_bytes())}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.root,args.output),ensure_ascii=False,indent=2))
