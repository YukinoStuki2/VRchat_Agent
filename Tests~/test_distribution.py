"""Candidate packaging tests; no Unity execution or live service changes."""
import errno
import importlib.util
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'Tools~' / 'build_candidate.py'

class DistributionTests(unittest.TestCase):
    def module(self):
        self.assertTrue(SCRIPT.is_file(), 'Missing deterministic candidate packager')
        spec = importlib.util.spec_from_file_location('candidate_packager', SCRIPT)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def fixture(self, tmp):
        root = Path(tmp)/'work'; root.mkdir()
        (root/'package.json').write_text('{}')
        mod = self.module()
        (root/'VERIFICATION.json').write_text(json.dumps({
            'local_checks_passed': True, 'independent_source_reviews_passed': True,
            'unity_verified': False, 'source_sha256': mod.hashes(root, mod.source_files(root))}))
        return mod, root

    def test_verification_attachments_reject_symlinks(self):
        for name in ('VERIFICATION.json', 'VERIFICATION.md'):
            for target_kind in ('outside', 'inside', 'dangling'):
                with self.subTest(name=name, target=target_kind), tempfile.TemporaryDirectory() as tmp:
                    mod, root = self.fixture(tmp)
                    target = (root if target_kind == 'inside' else Path(tmp))/'private.txt'
                    if target_kind != 'dangling':
                        target.write_bytes((root/'VERIFICATION.json').read_bytes())
                    attachment = root/name
                    if attachment.exists(): attachment.unlink()
                    attachment.symlink_to(target)
                    destination = Path(tmp)/'candidate.zip'
                    with self.assertRaisesRegex(ValueError, 'symlink|contain'):
                        mod.build(root, destination)
                    self.assertFalse(destination.exists())

    def test_verification_attachments_must_be_regular_files(self):
        for name in ('VERIFICATION.json', 'VERIFICATION.md'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                mod, root = self.fixture(tmp)
                attachment = root/name
                if attachment.exists(): attachment.unlink()
                attachment.mkdir()
                destination = Path(tmp)/'candidate.zip'
                with self.assertRaisesRegex(ValueError, 'regular file'):
                    mod.build(root, destination)
                self.assertFalse(destination.exists())

    def test_verification_replaced_after_gate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod, root = self.fixture(tmp)
            original_hashes = mod.hashes
            def replace_after_hashes(source, names):
                result = original_hashes(source, names)
                evidence = json.loads((root/'VERIFICATION.json').read_bytes())
                evidence['independent_source_reviews_passed'] = False
                (root/'VERIFICATION.json').write_text(json.dumps(evidence))
                return result
            destination = Path(tmp)/'candidate.zip'
            with patch.object(mod, 'hashes', side_effect=replace_after_hashes):
                with self.assertRaisesRegex(ValueError, 'Verification snapshot'):
                    mod.build(root, destination)
            self.assertFalse(destination.exists())

    def test_all_verification_gates_require_exact_booleans(self):
        for field, values in (
            ('local_checks_passed', (False, None, 1, 'true')),
            ('independent_source_reviews_passed', (False, None, 1, 'true')),
            ('unity_verified', (True, None, 0, 'false')),
        ):
            for value in values:
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                    mod, root = self.fixture(tmp)
                    evidence = json.loads((root/'VERIFICATION.json').read_bytes())
                    evidence[field] = value
                    (root/'VERIFICATION.json').write_text(json.dumps(evidence))
                    destination = Path(tmp)/'candidate.zip'
                    with self.assertRaisesRegex(ValueError, 'verification gate'):
                        mod.build(root, destination)
                    self.assertFalse(destination.exists())

    def test_explicit_inventory_excludes_unreviewed_artifacts(self):
        mod = self.module()
        package = 'Packages~/com.yukino.vrchat-managed-editing'
        allowed = {
            'package.json', 'package.json.meta', 'START_HERE.md',
            'Editor/ReadOnlyCommon.cs', 'Editor/ReadOnlyCommon.cs.meta',
            package+'/package.json', package+'/Editor.meta',
            package+'/Editor/FacePreview.cs', package+'/Editor/Core/GatePolicy.cs',
            'Tests~/UNITY_ACCEPTANCE.md', 'Tests~/test_distribution.py',
            'Tests~/test_reported_regressions.py', 'Tests~/Unity/ManagedSmokeTests.cs',
            'Tests~/Unity/Yukino.VRChatManagedEditing.Tests.asmdef',
            'Tests~/core/Program.cs', 'Tests~/core/CoreTests.csproj', 'Tests~/core/NuGet.Config',
            'Tests~/core/.gitignore', 'Tests~/core/README.md', 'Tests~/core/run.py',
            'Tests~/core/compatibility/CoreCompatibility.csproj',
            'Tests~/syntax/Program.cs', 'Tests~/syntax/SyntaxCheck.csproj',
            'Tools~/build_candidate.py', 'Tools~/managed_bridge/bridge.py',
            'Tools~/managed_bridge/test_bridge.py', 'Tools~/managed_bridge/test_sdk_handshake.py',
            'Tools~/managed_bridge/README.zh-CN.md', 'Tools~/managed_bridge/TDD.md',
        }
        directories = {str(Path(name).parent) for name in allowed}
        excluded = {str(Path(directory)/name) for directory in directories for name in (
            'credentials.json', 'runtime.config', '.env.json', 'private.md',
            'credentials.json.meta', 'unreviewed.cs', 'test_private.py',
            'runtime/bridge.py', 'logs/debug.json', 'evidence/README.md',
        )}
        with tempfile.TemporaryDirectory() as tmp:
            mod, root = self.fixture(tmp)
            for name in allowed | excluded:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            self.assertEqual(set(mod.source_files(root)), allowed)
            evidence = json.loads((root/'VERIFICATION.json').read_bytes())
            evidence['source_sha256'] = mod.hashes(root, mod.source_files(root))
            (root/'VERIFICATION.json').write_text(json.dumps(evidence))
            (root/'VERIFICATION.md').write_bytes(b'Reviewed local candidate\n')
            destination = Path(tmp)/'candidate.zip'
            mod.build(root, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(set(archive.namelist()), allowed | {
                    'VERIFICATION.json', 'VERIFICATION.md', 'MANIFEST.json'})
                self.assertEqual(archive.read('VERIFICATION.json'), (root/'VERIFICATION.json').read_bytes())
                self.assertEqual(archive.read('VERIFICATION.md'), b'Reviewed local candidate\n')

    def test_hashes_enforce_containment_and_reject_parent_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod, root = self.fixture(tmp)
            outside = Path(tmp)/'private'; outside.mkdir()
            (outside/'bridge.py').write_bytes(b'private')
            for name in ('../private/bridge.py', str(outside/'bridge.py')):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'contained'):
                    mod.hashes(root, [name])
            (root/'Tools~').mkdir()
            (root/'Tools~/managed_bridge').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                mod.hashes(root, ['Tools~/managed_bridge/bridge.py'])
            with self.assertRaisesRegex(ValueError, 'symlink'):
                mod.source_files(root)

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW'), 'O_NOFOLLOW unavailable')
    def test_verification_symlink_swap_at_open_is_not_followed(self):
        for name in ('VERIFICATION.json', 'VERIFICATION.md'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                mod, root = self.fixture(tmp)
                if name.endswith('.md'): (root/name).write_bytes(b'reviewed')
                target = Path(tmp)/'private'; target.write_bytes(b'private')
                original_open = os.open
                def swap_at_open(path, flags, *args, **kwargs):
                    if Path(path) == root/name:
                        (root/name).unlink()
                        (root/name).symlink_to(target)
                    return original_open(path, flags, *args, **kwargs)
                destination = Path(tmp)/'candidate.zip'
                with patch.object(os, 'open', side_effect=swap_at_open):
                    with self.assertRaises(OSError) as raised:
                        mod.build(root, destination)
                self.assertEqual(raised.exception.errno, errno.ELOOP)
                self.assertFalse(destination.exists())

    def test_source_changed_during_collection_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod, root = self.fixture(tmp)
            original_hashes = mod.hashes
            def replace_after_hashes(source, names):
                result = original_hashes(source, names)
                (root/'package.json').write_bytes(b'changed during collection')
                return result
            destination = Path(tmp)/'candidate.zip'
            with patch.object(mod, 'hashes', side_effect=replace_after_hashes):
                with self.assertRaisesRegex(ValueError, 'Source snapshot'):
                    mod.build(root, destination)
            self.assertFalse(destination.exists())

    def test_verified_scope_packaging_excludes_runtime_and_hashes_zip(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'work'; root.mkdir()
            for name in ['package.json','Packages~/com.yukino.vrchat-managed-editing/package.json','Tools~/managed_bridge/bridge.py','Tests~/core/Program.cs','START_HERE.md']:
                p=root/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{}' if name.endswith('.json') else 'candidate\n')
            for name in ['.env','secret.key','Tools~/managed_bridge/__pycache__/bridge.pyc','Tests~/core/bin/artifact.dll','Tests~/core/obj/cache.json','Tools~/managed_bridge/test-results.json']:
                p=root/name; p.parent.mkdir(parents=True,exist_ok=True);p.write_text('DO NOT DISTRIBUTE')
            names=mod.source_files(root)
            self.assertIn('Tools~/managed_bridge/bridge.py',names)
            self.assertFalse(any('bin/' in n or '__pycache__' in n or n.endswith('.env') or n.endswith('test-results.json') for n in names))
            state=mod.hashes(root,names)
            (root/'VERIFICATION.json').write_text(json.dumps({'local_checks_passed':True,'independent_source_reviews_passed':True,'unity_verified':False,'source_sha256':state}))
            path=Path(tmp)/'candidate.zip'
            result=mod.build(root,path)
            self.assertEqual(result['zip_sha256'],mod.digest(path.read_bytes()))
            with zipfile.ZipFile(path) as archive:
                manifest=json.loads(archive.read('MANIFEST.json'))
                self.assertEqual(set(manifest),set(archive.namelist())-{'MANIFEST.json'})
                for name,sha in manifest.items(): self.assertEqual(mod.digest(archive.read(name)),sha)
            # Source drift since verification refuses publication.
            (root/'Tools~/managed_bridge/bridge.py').write_text('changed\n')
            with self.assertRaisesRegex(ValueError,'snapshot'): mod.build(root,Path(tmp)/'bad.zip')

    def test_unity_metadata_and_original_package_identity(self):
        import re
        import subprocess
        root = ROOT / 'Packages~' / 'com.yukino.vrchat-managed-editing'
        guids = []
        for path in root.rglob('*'):
            if path.suffix == '.meta':
                matches=re.findall(r'^guid: ([0-9a-f]{32})$',path.read_text(),re.M)
                self.assertEqual(len(matches),1,str(path))
                guids.extend(matches)
            else:
                self.assertTrue(Path(str(path)+'.meta').is_file(),str(path))
        self.assertEqual(len(guids),len(set(guids)))
        original=subprocess.check_output(['git','ls-tree','-r','--name-only','v0.1.1'],cwd=ROOT,text=True).splitlines()
        for name in original:
            self.assertEqual((ROOT/name).read_bytes(),subprocess.check_output(['git','show','v0.1.1:'+name],cwd=ROOT),name)
        manifest=json.loads((root/'package.json').read_text())
        self.assertEqual(manifest['unity'],'2022.3')
        self.assertEqual(manifest['dependencies']['com.coplaydev.unity-mcp'],'10.2.0')

    def test_failed_review_and_symlinks_never_produce_package(self):
        mod=self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'work';root.mkdir()
            (root/'VERIFICATION.json').write_text(json.dumps({'local_checks_passed':True,'independent_source_reviews_passed':False,'unity_verified':False,'source_sha256':{}}))
            with self.assertRaisesRegex(ValueError,'verification'):mod.build(root,Path(tmp)/'out.zip')
            p=root/'Tools~/managed_bridge';p.mkdir(parents=True)
            (p/'bridge.py').symlink_to(root/'VERIFICATION.json')
            with self.assertRaisesRegex(ValueError,'symlink'):mod.source_files(root)

if __name__=='__main__': unittest.main()
