"""Candidate packaging contract tests; fixtures are NOT implementation evidence."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / 'build_candidate.py'


class CandidatePackagingTests(unittest.TestCase):
    def builder(self):
        self.assertTrue(SCRIPT.is_file(), 'candidate verification-gated packer is missing')
        spec = importlib.util.spec_from_file_location('candidate_builder', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, root):
        package = root / 'package'
        (package / 'Editor').mkdir(parents=True)
        for name, text in {
            'package.json': json.dumps({'name': 'com.yukino.vrchat-agent',
                'version': '0.2.0-preview.1', 'unity': '2022.3',
                'dependencies': {'com.coplaydev.unity-mcp': '10.2.0',
                    'com.unity.nuget.newtonsoft-json': '3.0.2'}, 'vpmDependencies': {}}),
            'README.md': 'Packaging fixture, not a Unity implementation.',
            'LICENSE': 'Packaging fixture license.',
            'THIRD_PARTY_NOTICES.md': 'Packaging fixture notices.',
            'Editor/Fixture.cs': '// TEST FIXTURE ONLY',
        }.items():
            p = package / name
            p.write_text(text, encoding='utf-8')
            (package / (name + '.meta')).write_text('fileFormatVersion: 2\nguid: ' + hashlib.md5(name.encode()).hexdigest() + '\n')
        (package / 'Editor.meta').write_text('fileFormatVersion: 2\nguid: ' + '1' * 32 + '\nfolderAsset: yes\n')
        return package

    def proof(self, package, **changes):
        data = {'implementation_complete': True, 'local_checks_passed': True,
                'independent_source_reviews_passed': True, 'windows_kernel_checks_passed': True,
                'unity_verified': False, 'remaining_implementation_gaps': [],
                'source_sha256': {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in package.rglob('*') if p.is_file()}}
        data.update(changes)
        return data

    def test_incomplete_candidate_cannot_be_built_as_installable(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory(prefix='candidate-package-test-') as td:
            package = self.fixture(Path(td))
            proof = self.proof(package, implementation_complete=False,
                               remaining_implementation_gaps=['missing actual runtime'])
            with self.assertRaisesRegex(ValueError, 'verification|incomplete'):
                builder.build(package, proof, 'http://127.0.0.1:9000/packages/')


    def test_package_requires_stable_meta_for_files_and_folders(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory(prefix='candidate-package-meta-') as td:
            package = self.fixture(Path(td))
            for missing in ('Editor/Fixture.cs.meta', 'Editor.meta'):
                proof = self.proof(package)
                del proof['source_sha256'][missing]
                with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'meta'):
                    builder.build(package, proof, 'http://127.0.0.1:9000/packages/')


    def test_unity_ignored_runtime_contents_need_no_meta(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory(prefix='candidate-runtime-meta-') as td:
            package = self.fixture(Path(td))
            (package/'Runtime~/python').mkdir(parents=True)
            (package/'Runtime~/python/python.exe').write_bytes(b'fixture, not executable')
            (package/'Runtime~.meta').write_text('fileFormatVersion: 2\nguid: ' + '2'*32 + '\nfolderAsset: yes\n')
            files = {p.relative_to(package).as_posix(): p.read_bytes()
                     for p in package.rglob('*') if p.is_file()}
            manifest = builder.validate_sources(files)
            self.assertEqual(manifest['name'], 'com.yukino.vrchat-agent')
            # Visible Runtime is different; the exception must stay exact.
            files['Runtime/python.exe'] = b'visible fixture'
            with self.assertRaisesRegex(ValueError, 'meta'):
                builder.validate_sources(files)

    def test_invalid_or_duplicate_guid_is_rejected(self):
        builder = self.builder()
        for content in ('fileFormatVersion: 2\nguid: not-a-guid\n',
                        'fileFormatVersion: 2\nguid: ' + '1' * 32 + '\n'):
            with tempfile.TemporaryDirectory(prefix='candidate-package-guid-') as td:
                package = self.fixture(Path(td))
                (package / 'Editor/Fixture.cs.meta').write_text(content)
                with self.subTest(content=content), self.assertRaisesRegex(ValueError, 'GUID'):
                    builder.build(package, self.proof(package), 'http://127.0.0.1:9000/packages/')

    def test_fixture_zip_deterministic_and_reviewed_source_drift_rejected(self):
        import io
        import zipfile
        builder = self.builder()
        with tempfile.TemporaryDirectory(prefix='candidate-package-zip-') as td:
            package = self.fixture(Path(td))
            proof = self.proof(package)
            first = builder.build(package, proof, 'http://127.0.0.1:9000/packages/')
            self.assertEqual(first, builder.build(package, proof, 'http://127.0.0.1:9000/packages/'))
            name, data, manifest = first
            self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['zipSHA256'])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), set(proof['source_sha256']))
                for path in proof['source_sha256']:
                    if path != 'package.json':
                        self.assertEqual(archive.read(path), (package / path).read_bytes())
            (package / 'Editor/Fixture.cs').write_text('// changed after review')
            with self.assertRaisesRegex(ValueError, 'drift'):
                builder.build(package, proof, 'http://127.0.0.1:9000/packages/')


if __name__ == '__main__':
    unittest.main()
