"""Actual candidate source layout, not an approved package or Unity test."""
from pathlib import Path, PureWindowsPath
from unittest.mock import patch
import importlib.util
import json
import hashlib
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def assembler():
    path = ROOT / 'distribution/assemble_source.py'
    if not path.is_file():
        raise AssertionError('source payload assembler missing')
    spec = importlib.util.spec_from_file_location('source_payload', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourcePayloadTests(unittest.TestCase):
    def test_SP009_relocated_payload_has_executable_catalog(self):
        files=assembler().collect(ROOT)
        self.assertTrue('Runtime~/runtime/operation_catalog.py' in files, 'catalog runtime missing from copied payload')
        with tempfile.TemporaryDirectory(prefix='candidate-catalog-layout-') as td:
            for name, data in files.items():
                if name.startswith('Runtime~/') and not name.endswith('.meta'):
                    output=Path(td)/name;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
            spec=importlib.util.spec_from_file_location('relocated_catalog',Path(td)/'Runtime~/runtime/operation_catalog.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.assertEqual(module.page()['total'],json.loads(files['Runtime~/catalog/native-inventory.json'])['count'])

    def test_SP008_local_codex_is_in_actual_runtime_payload(self):
        files=assembler().collect(ROOT)
        self.assertTrue('Runtime~/launcher/codex_local.py' in files,'local Codex absent from payload')
        self.assertEqual(files['Runtime~/launcher/codex_local.py'],(ROOT/'launcher/codex_local.py').read_bytes())

    def test_SP007_delivery_runtime_dependency_is_in_the_actual_payload(self):
        files=assembler().collect(ROOT)
        name='launcher/hermes_delivery.py'
        self.assertTrue('Runtime~/'+name in files,'missing required SSH delivery module')
        self.assertEqual(files['Runtime~/'+name],(ROOT/name).read_bytes())

    def test_SP006_package_member_names_stay_posix_on_windows(self):
        module = assembler(); files = module.collect(ROOT)
        with patch.object(module.packer, 'Path', PureWindowsPath):
            self.assertEqual(module.packer.validate_sources(files)['name'], 'com.yukino.vrchat-agent')

    def test_SP001_actual_editor_and_fixed_runtime_are_in_one_source_payload(self):
        files = assembler().collect(ROOT)
        manifest = json.loads(files['package.json'])
        self.assertEqual(manifest['name'], 'com.yukino.vrchat-agent')
        self.assertEqual(manifest['version'], '0.2.0-preview.1')
        self.assertEqual(manifest['dependencies']['com.coplaydev.unity-mcp'], '10.2.0')
        self.assertFalse(any(k.startswith('legacy') for k in manifest))
        asm = json.loads(files['Editor/Yukino.VRChatAgent.Editor.asmdef'])
        self.assertEqual(asm['includePlatforms'], ['Editor'])
        self.assertIn('MCPForUnity.Editor', asm['references'])
        for relative in ('launcher/editor_owner.py', 'launcher/direct_python.py',
                         'runtime/__main__.py', 'native/src/main.py',
                         'dependencies/mcp-1.29.1/mcp/client/streamable_http.py',
                         'diagnostics/server.py', 'diagnostics/lifetime.py', 'distribution/requirements.lock'):
            self.assertEqual(files['Runtime~/' + relative], (ROOT / relative).read_bytes())
        for relative in ('Editor/CandidateSession.cs', 'Editor/CandidateWindow.cs',
                         'Editor/OwnedTransport/CandidateOwnedTransport.asmref'):
            self.assertEqual(files[relative], (ROOT / 'package' / relative).read_bytes())
        self.assertFalse(any('/tests/' in f or '/evidence/' in f or '__pycache__' in f for f in files))
        for f in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'Runtime~/native/LICENSE',
                  'Runtime~/dependencies/mcp-1.29.1/LICENSE'):
            self.assertGreater(len(files[f]), 100)


    def test_SP002_duplicate_meta_guid_is_rejected_in_actual_payload(self):
        module = assembler()
        with tempfile.TemporaryDirectory(prefix='candidate-source-bad-meta-') as td:
            target = Path(td)
            index = json.loads((ROOT / 'distribution/source-inputs.json').read_text())
            for name in index['files']:
                output = target / name; output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, output)
            first = 'package/Editor/OwnedTransport/CandidateOwnedTransport.asmref.meta'
            second = 'package/Editor/OwnedTransport/CandidateOwnedWebSocketTransportClient.cs.meta'
            (target / second).write_bytes((target / first).read_bytes())
            index['files'][second] = hashlib.sha256((target / second).read_bytes()).hexdigest()
            (target / 'distribution/source-inputs.json').write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, 'GUID'):
                module.collect(target)


    def test_SP003_empty_source_and_case_aliased_destinations_refused(self):
        module = assembler()
        with tempfile.TemporaryDirectory(prefix='candidate-source-alias-') as td:
            target = Path(td)
            (target / 'distribution').mkdir()
            for mapping in ({'': '0'*64}, {'package/README.md': '0'*64, 'package/readme.md': '0'*64}):
                (target / 'distribution/source-inputs.json').write_text(json.dumps({'schema': 1, 'files': mapping}))
                # Alias detection must happen before file reads and source-drift failures.
                with self.subTest(keys=list(mapping)), self.assertRaisesRegex(ValueError, 'source_path|alias'):
                    module.collect(target)


    def test_SP004_deterministic_metas_preserve_upstream_and_product_gate_closed(self):
        module = assembler(); files = module.collect(ROOT)
        self.assertEqual(files, module.collect(ROOT))
        guids = [value.decode().split('guid: ')[1].splitlines()[0]
                 for name, value in files.items() if name.endswith('.meta')]
        self.assertEqual(len(guids), len(set(guids)))
        for original in (ROOT / 'package').rglob('*.meta'):
            self.assertEqual(files[original.relative_to(ROOT / 'package').as_posix()], original.read_bytes())
        with tempfile.TemporaryDirectory(prefix='candidate-source-gate-') as td:
            target = Path(td)
            for name, data in files.items():
                path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            proof = {'implementation_complete': False, 'independent_source_reviews_passed': False,
                     'local_checks_passed': True, 'windows_kernel_checks_passed': True,
                     'unity_verified': False, 'remaining_implementation_gaps': ['client integration'],
                     'source_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
            with self.assertRaisesRegex(ValueError, 'incomplete candidate'):
                module.packer.build(target, proof, 'https://invalid.example/')

    def test_SP005_source_drift_and_symlink_rejected(self):
        module = assembler()
        with tempfile.TemporaryDirectory(prefix='candidate-source-drift-') as td:
            target = Path(td); (target / 'distribution').mkdir(); (target / 'runtime').mkdir()
            (target / 'runtime/example.py').write_text('changed')
            index = {'schema': 1, 'files': {'runtime/example.py': hashlib.sha256(b'original').hexdigest()}}
            (target / 'distribution/source-inputs.json').write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, 'source_drift'):
                module.collect(target)
            (target / 'runtime/example.py').unlink()
            (target / 'runtime/example.py').symlink_to(ROOT / 'runtime/__main__.py')
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                module.collect(target)


if __name__ == '__main__':
    unittest.main(verbosity=2)
