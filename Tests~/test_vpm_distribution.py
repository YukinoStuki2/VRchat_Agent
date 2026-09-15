"""VPM packaging tests against audited source; no Unity execution."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'VPM~/build_repository.py'

class VpmDistributionTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('vpm_builder', SCRIPT)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_two_separate_reproducible_packages_preserve_editor_bytes(self):
        mod = self.module()
        artifacts, index = mod.build(ROOT)
        self.assertEqual(set(index['packages']), {'com.yukino.vrchat-readonly-mcp', 'com.yukino.vrchat-managed-editing'})
        self.assertEqual(index['url'], 'https://raw.githubusercontent.com/YukinoStuki2/VRchat_Agent/vpm/index.json')
        self.assertEqual(len(artifacts), 2)
        self.assertEqual((artifacts, index), mod.build(ROOT))
        for package_id, row in index['packages'].items():
            versions = row['versions']
            self.assertEqual(len(versions), 1)
            version, manifest = next(iter(versions.items()))
            self.assertEqual(version, '0.1.2' if 'readonly' in package_id else '0.1.0-preview.2')
            name = package_id + '-' + version + '.zip'
            data = artifacts[name]
            self.assertEqual(manifest['zipSHA256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(manifest['url'], mod.ASSET_BASE + name)
            self.assertNotIn('/vpm/', manifest['url'])
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                self.assertIsNone(z.testzip())
                files = z.namelist()
                self.assertEqual(len(files), len(set(files)))
                self.assertIn('package.json', files)
                self.assertTrue(all(not n.startswith('/') and '..' not in Path(n).parts for n in files))
                self.assertTrue(all('Tools~' not in n and 'Tests~' not in n and not n.endswith('.dll') for n in files))
                package = json.loads(z.read('package.json'))
                self.assertEqual({k: v for k, v in manifest.items() if k != 'zipSHA256'}, package)
                self.assertFalse(any(k.startswith('legacy') for k in package))
                self.assertEqual(package['dependencies']['com.coplaydev.unity-mcp'], '10.2.0')
                self.assertEqual(package['dependencies']['com.unity.nuget.newtonsoft-json'], '3.0.2')
                expected = {} if 'readonly' in package_id else {'com.yukino.vrchat-readonly-mcp': '0.1.2'}
                self.assertEqual(package.get('vpmDependencies', {}), expected)
                src = ROOT if 'readonly' in package_id else ROOT / 'Packages~/com.yukino.vrchat-managed-editing'
                for f in src.rglob('*.cs'):
                    # Root source has additional packages; only its own Editor belongs in read-only ZIP.
                    if not f.is_relative_to(src / 'Editor'): continue
                    rel = f.relative_to(src).as_posix()
                    self.assertEqual(z.read(rel), f.read_bytes())
                    self.assertEqual(z.read(rel+'.meta'), f.with_name(f.name+'.meta').read_bytes())
                self.assertIn('必须先', z.read('README.md').decode())
                self.assertIn('LICENSE', files)
                self.assertIn('THIRD_PARTY_NOTICES.md', files)

    def test_merge_retains_older_versions_and_unmentioned_packages(self):
        mod = self.module()
        self.assertTrue(callable(getattr(mod, 'merge_index', None)), 'merge_index is required')
        _, new = mod.build(ROOT)
        existing = copy.deepcopy(new)
        package_id = 'com.yukino.vrchat-readonly-mcp'
        versions = existing['packages'][package_id]['versions']
        older = versions.pop('0.1.2')
        older.update(version='0.1.1', url=older['url'].replace('0.1.2', '0.1.1'), zipSHA256='a'*64)
        versions['0.1.1'] = older
        del new['packages']['com.yukino.vrchat-managed-editing']
        before = copy.deepcopy((existing, new))
        merged = mod.merge_index(existing, new)
        self.assertEqual(merged['packages'][package_id]['versions'], {
            '0.1.1': older, '0.1.2': new['packages'][package_id]['versions']['0.1.2']})
        self.assertEqual(merged['packages']['com.yukino.vrchat-managed-editing'],
                         existing['packages']['com.yukino.vrchat-managed-editing'])
        self.assertEqual((existing, new), before)

    def test_merge_same_version_requires_canonical_identical_record(self):
        mod = self.module()
        _, existing = mod.build(ROOT)
        package_id = 'com.yukino.vrchat-readonly-mcp'
        for field, value in [('zipSHA256', '0'*64), ('url', 'https://example.invalid/changed.zip'),
                             ('version', '0.1.3')]:
            with self.subTest(field=field):
                changed = copy.deepcopy(existing)
                changed['packages'][package_id]['versions']['0.1.2'][field] = value
                with self.assertRaisesRegex(ValueError, 'existing version'):
                    mod.merge_index(existing, changed)
        # Object key ordering is irrelevant, but JSON types must not compare equal.
        reordered = json.loads(json.dumps(existing, sort_keys=True))
        self.assertEqual(mod.merge_index(existing, reordered), existing)
        existing['packages'][package_id]['versions']['0.1.2']['testFlag'] = True
        changed = copy.deepcopy(existing)
        changed['packages'][package_id]['versions']['0.1.2']['testFlag'] = 1
        with self.assertRaisesRegex(ValueError, 'existing version'):
            mod.merge_index(existing, changed)

    def test_merge_rejects_repository_identity_changes(self):
        mod = self.module()
        _, index = mod.build(ROOT)
        for field in ('id', 'url', 'name', 'author'):
            for side in ('existing', 'new', 'both'):
                for missing in (False, True):
                    with self.subTest(field=field, side=side, missing=missing):
                        existing, new = copy.deepcopy(index), copy.deepcopy(index)
                        for candidate in ([existing] if side == 'existing' else
                                          [new] if side == 'new' else [existing, new]):
                            if missing:
                                del candidate[field]
                            else:
                                candidate[field] = 'different'
                        with self.assertRaisesRegex(ValueError, 'repository identity'):
                            mod.merge_index(existing, new)

    def test_emit_appends_versions_with_atomic_index_after_assets(self):
        mod = self.module()
        artifacts, new = mod.build(ROOT)
        existing = copy.deepcopy(new)
        package_id = 'com.yukino.vrchat-readonly-mcp'
        versions = existing['packages'][package_id]['versions']
        older = versions.pop('0.1.2')
        older.update(version='0.1.1', url=older['url'].replace('0.1.2', '0.1.1'), zipSHA256='a'*64)
        versions['0.1.1'] = older
        for initial in (None, mod.json_bytes(existing)):
            with self.subTest(existing=initial is not None), tempfile.TemporaryDirectory() as td:
                output = Path(td)
                index_path = output / 'index.json'
                if initial is not None:
                    index_path.write_bytes(initial)
                replace = os.replace
                def publish(source, destination):
                    self.assertEqual(Path(destination), index_path)
                    self.assertEqual(Path(source).parent, output)
                    self.assertEqual(index_path.read_bytes() if index_path.exists() else None, initial)
                    for name, data in artifacts.items():
                        self.assertEqual((output / 'VPM~/packages' / name).read_bytes(), data)
                    expected = new if initial is None else mod.merge_index(existing, new)
                    self.assertEqual(Path(source).read_bytes(), mod.json_bytes(expected))
                    return replace(source, destination)
                with patch('os.replace', side_effect=publish) as commit:
                    result = mod.emit(ROOT, output)
                commit.assert_called_once()
                for name, digest in result.items():
                    self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(), digest)
                if initial is not None:
                    self.assertEqual(json.loads(index_path.read_bytes())['packages'][package_id]
                                     ['versions']['0.1.1'], older)

    def test_repeated_emit_is_byte_and_metadata_idempotent(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)
            first = mod.emit(ROOT, output)
            before = {name: (Path(name).read_bytes(), Path(name).stat().st_ino,
                             Path(name).stat().st_mtime_ns) for name in first}
            with patch('os.replace', side_effect=AssertionError('unexpected index replacement')):
                self.assertEqual(mod.emit(ROOT, output), first)
            self.assertEqual({name: (Path(name).read_bytes(), Path(name).stat().st_ino,
                                    Path(name).stat().st_mtime_ns) for name in first}, before)

    def test_conflicting_existing_zip_fails_before_index_change(self):
        mod = self.module()
        artifacts, index = mod.build(ROOT)
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)
            existing = copy.deepcopy(index)
            existing['packages'] = {}
            initial = mod.json_bytes(existing)
            (output / 'index.json').write_bytes(initial)
            names = list(artifacts)
            conflict = output / 'VPM~/packages' / names[-1]
            conflict.parent.mkdir(parents=True)
            conflict.write_bytes(b'conflicting immutable ZIP')
            with self.assertRaisesRegex(ValueError, 'existing artifact'):
                mod.emit(ROOT, output)
            self.assertEqual((output / 'index.json').read_bytes(), initial)
            self.assertEqual(conflict.read_bytes(), b'conflicting immutable ZIP')
            self.assertFalse((conflict.parent / names[0]).exists())

    def test_failed_index_replace_preserves_old_bytes(self):
        mod = self.module()
        _, index = mod.build(ROOT)
        index['packages'] = {}
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)
            initial = mod.json_bytes(index)
            (output / 'index.json').write_bytes(initial)
            with patch('os.replace', side_effect=OSError('injected commit failure')):
                with self.assertRaisesRegex(OSError, 'injected commit failure'):
                    mod.emit(ROOT, output)
            self.assertEqual((output / 'index.json').read_bytes(), initial)
            self.assertEqual(list(output.glob('.index-*.tmp')), [])

    def test_emit_rejects_symlinks_and_parent_components_in_output(self):
        mod = self.module()
        artifacts, _ = mod.build(ROOT)
        for location in ('ancestor', 'root', 'VPM~', 'VPM~/packages', 'index.json',
                         'VPM~/packages/' + next(iter(artifacts)), '..'):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as td:
                base = Path(td)
                outside = base / 'outside'
                outside.mkdir()
                output = base / 'output'
                if location == 'ancestor':
                    (base / 'link').symlink_to(outside, target_is_directory=True)
                    output = base / 'link' / 'nested'
                elif location == '..':
                    output.mkdir()
                    output = output / '..' / 'outside'
                else:
                    link = output if location == 'root' else output / location
                    link.parent.mkdir(parents=True, exist_ok=True)
                    is_dir = location in ('root', 'VPM~', 'VPM~/packages')
                    target = outside if is_dir else outside / 'missing'
                    link.symlink_to(target, target_is_directory=is_dir)
                with self.assertRaisesRegex(ValueError, 'output path'):
                    mod.emit(ROOT, output)
                self.assertEqual(list(outside.iterdir()), [])
                self.assertFalse((output / 'index.json').is_file())

    def test_unreviewed_or_symlinked_sources_are_rejected(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'VERIFICATION.json').write_text(json.dumps({'source_sha256': {'Editor/unsafe.cs': '0'*64}}))
            (root/'Editor').mkdir()
            (root/'Editor/unsafe.cs').symlink_to(SCRIPT)
            with self.assertRaises(ValueError): mod.build(root)

if __name__ == '__main__':
    unittest.main()
