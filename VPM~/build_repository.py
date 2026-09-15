#!/usr/bin/env python3
"""Build deterministic VPM ZIPs from the already-reviewed source snapshot.
No network, credentials, Unity execution, Git writes or automatic installation.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

REPO = 'https://raw.githubusercontent.com/YukinoStuki2/VRchat_Agent/'
RELEASE_TAG = 'vpm-0.1.0'
INDEX_URL = REPO + 'vpm/index.json'
ASSET_BASE = REPO + RELEASE_TAG + '/VPM~/packages/'
REPO_IDENTITY = {'name': 'Yukino VRChat Agent — ALCOM / VPM',
                 'author': 'Yukino / Hermes Agent', 'id': 'com.yukino.vrchat-agent.vpm',
                 'url': INDEX_URL}
PACKAGES = (
    ('com.yukino.vrchat-readonly-mcp', '0.1.2', '', {}),
    ('com.yukino.vrchat-managed-editing', '0.1.0-preview.2',
     'Packages~/com.yukino.vrchat-managed-editing/', {'com.yukino.vrchat-readonly-mcp': '0.1.2'}),
)


def read_regular(root, name):
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Unsafe source path')
    path = root / rel
    for item in (path, *path.parents):
        if item == root: break
        if item.is_symlink(): raise ValueError('Symlink is not a package source')
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Missing regular source file: ' + name)
    return path.read_bytes()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def build(root):
    root = Path(root).resolve()
    proof = json.loads(read_regular(root, 'VERIFICATION.json'))
    if (proof.get('local_checks_passed') is not True or
            proof.get('independent_source_reviews_passed') is not True or
            proof.get('unity_verified') is not False):
        raise ValueError('Missing candidate verification gates')
    source = proof.get('source_sha256', {})
    artifacts = {}
    index = {**REPO_IDENTITY, 'packages': {}}
    for package_id, version, prefix, dependencies in PACKAGES:
        files = {}
        for name, expected in source.items():
            if prefix:
                if not name.startswith(prefix): continue
                relative = name[len(prefix):]
            else:
                relative = name
                if '/' in relative and not relative.startswith('Editor/'): continue
            if not (relative.startswith('Editor/') or relative in {
                    'package.json', 'package.json.meta', 'Editor.meta', 'README.md', 'README.md.meta',
                    'LICENSE', 'LICENSE.meta', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md.meta'}):
                continue
            data = read_regular(root, name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Reviewed source drift: ' + name)
            files[relative] = data
        required = {'package.json', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'}
        if not required <= files.keys() or not any(n.endswith('.cs') for n in files):
            raise ValueError('Incomplete package source')
        manifest = json.loads(files['package.json'])
        if manifest['name'] != package_id:
            raise ValueError('Wrong package identity')
        filename = package_id + '-' + version + '.zip'
        manifest.update(version=version, url=ASSET_BASE + filename,
                        documentationUrl='https://github.com/YukinoStuki2/VRchat_Agent/blob/vpm/ALCOM.md',
                        changelogUrl=REPO + RELEASE_TAG + '/ALCOM.md', license='MIT')
        # Project-level Coplay Git install remains required; it is NOT in our VPM repo.
        # Unity registry dependencies remain normal UPM dependencies.
        manifest['vpmDependencies'] = dependencies
        if not manifest.get('author', {}).get('name'):
            raise ValueError('Missing author')
        manifest['author']['url'] = 'https://github.com/YukinoStuki2'
        if any(k.startswith('legacy') for k in manifest):
            raise ValueError('Implicit migration/removal is forbidden')
        files['package.json'] = json_bytes(manifest)
        header = ('# ALCOM / VPM 分发说明\n\n'
                  + '本包版本：`' + version + '`。仅分发元数据/说明更新，C#及.meta沿用已审查源码。\n\n'
                  + '**必须先**在Unity Package Manager安装官方固定依赖：\n\n'
                  + '`https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0`\n\n'
                  + '本VPM仓库不分发或自动安装Coplay，不升级Unity/SDK，不启动受限入口或SSH。\n'
                  + '已有同名Git/磁盘包，先备份并移除旧引用，再由ALCOM安装；不要删除模型。\n'
                  + '受控编辑为预览版本，必须先临时工程验收；更新后修改权限仍关闭。\n'
                  + '安装/更新完整说明：https://github.com/YukinoStuki2/VRchat_Agent/blob/vpm/ALCOM.md\n\n'
                  + '---\n以下为原始源码快照说明；其中版本及Git分发记录描述先前阶段。\n\n')
        files['README.md'] = header.encode() + files['README.md']
        data = zip_bytes(files)
        artifacts[filename] = data
        entry = dict(manifest, zipSHA256=hashlib.sha256(data).hexdigest())
        index['packages'][package_id] = {'versions': {version: entry}}
    return artifacts, index


def merge_index(existing, new):
    """Append package versions without removing any previous releases."""
    for candidate in (existing, new):
        if any(candidate.get(key) != value for key, value in REPO_IDENTITY.items()):
            raise ValueError('Wrong repository identity')
    merged = copy.deepcopy(existing)
    for package_id, package in new['packages'].items():
        target = merged['packages'].setdefault(package_id, copy.deepcopy(package))
        for version, record in package['versions'].items():
            if version in target['versions']:
                if (json.dumps(target['versions'][version], sort_keys=True, allow_nan=False) !=
                        json.dumps(record, sort_keys=True, allow_nan=False)):
                    raise ValueError('Refusing changed existing version: ' + package_id + '@' + version)
            else:
                target['versions'][version] = copy.deepcopy(record)
    return merged


def check_output_path(path):
    """Reject traversal and symlinks, including ancestors of the output root."""
    if '..' in path.parts or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Unsafe output path: ' + str(path))


def emit(root, output):
    root, output = Path(root), Path(output).absolute()
    check_output_path(output)
    artifacts, index = build(root)
    index_path = output / 'index.json'
    check_output_path(index_path)
    previous = index_path.read_bytes() if index_path.exists() else None
    existing = json.loads(previous) if previous is not None else dict(REPO_IDENTITY, packages={})
    index = merge_index(existing, index)
    index_data = previous if previous is not None and index == existing else json_bytes(index)
    assets = {output / 'VPM~/packages' / name: data for name, data in artifacts.items()}
    for path, data in assets.items():
        # Preflight all immutable ZIPs before writing anything.
        check_output_path(path)
        if path.exists() and path.read_bytes() != data:
            raise ValueError('Refusing changed existing artifact: ' + str(path))
    for path, data in assets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open('xb') as handle: handle.write(data)
    if index_data != previous:
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output, prefix='.index-', suffix='.tmp', delete=False) as handle:
            staged = Path(handle.name)
            try:
                handle.write(index_data)
                handle.flush()
                os.fsync(handle.fileno())
            except BaseException:
                staged.unlink()
                raise
        try:
            os.replace(staged, index_path)
        finally:
            staged.unlink(missing_ok=True)
    planned = {index_path: index_data, **assets}
    return {str(p): hashlib.sha256(data).hexdigest() for p, data in planned.items()}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(emit(args.root, args.output), indent=2))
