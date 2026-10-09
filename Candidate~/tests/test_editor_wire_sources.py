"""Pinned build-input boundaries; not Windows kernel or Unity acceptance."""
import ast
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity/Editor')
PREFIX = 'https://raw.githubusercontent.com/CoplayDev/unity-mcp/30d22075093d1d35dfb0091c1c7550e9ad948577/MCPForUnity/Editor/'
spec = importlib.util.spec_from_file_location('editor_wire_sources', ROOT/'tests/verify_editor_wire.py')
assert spec is not None and spec.loader is not None
wire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)
from source_native_source import PINS
EXPECTED = {name: PINS[name] for name in (
    'Helpers/Response.cs', 'Helpers/ToolParams.cs',
    'Helpers/ParamCoercion.cs', 'Helpers/StringCaseUtility.cs')}
EXPECTED['Tools/ReadConsole.cs'] = '80950f3ff610b845d34644aa0426775c7e1bfc20483c912c004067d43dfb119f'


def build_arguments(suite, work):
    """Execute the runner's real input/argv preparation, without subprocesses."""
    tree = ast.parse((ROOT/'tests/verify_editor_wire.py').read_bytes())
    body = next(n.body for n in ast.walk(tree) if isinstance(n, ast.With)
                and 'TemporaryDirectory' in ast.unparse(n.items[0].context_expr))
    end = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'build_code' for t in n.targets))
    namespace = dict(vars(wire), SUITE=suite, PROJECT=wire.SUITES[suite][1],
                     DOTNET=Path('unused-dotnet'), td=str(work))
    exec(compile(ast.Module(body=body[:end], type_ignores=[]), 'wire-build-inputs', 'exec'), namespace)
    return namespace['argv']


class EditorWireSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        snapshot = Path(os.environ.get('CANDIDATE_PINNED_EDITOR_ROOT', str(LOCAL)))
        cls.payloads = {}
        for name, digest in EXPECTED.items():
            if snapshot.is_dir():
                raw = (snapshot/name).read_bytes()
            elif sys.platform == 'win32':
                with urllib.request.urlopen(PREFIX+name, timeout=30) as response:
                    raw = response.read()
            else:
                raise FileNotFoundError('local pinned snapshot required for offline tests')
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('fixture_source_drift: '+name)
            cls.payloads[name] = raw

    def fetch(self, url, timeout):
        self.assertTrue(url.startswith(PREFIX))
        self.assertEqual(timeout, 30)
        name = url[len(PREFIX):]
        self.assertNotIn(name, self.requested, 'duplicate source fetch')
        self.requested.append(name)
        return io.BytesIO(self.payloads[name])

    def test_EWS001_rw_er_pass_owned_verified_sources_to_actual_project(self):
        real_is_file, real_is_dir = Path.is_file, Path.is_dir
        for suite in ('rw', 'er'):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory(prefix='wire-source-') as td:
                work = Path(td)
                self.requested = []
                # Simulate no Linux source tree, as on a clean Windows runner.
                with patch.object(Path, 'is_file', lambda p: False if p.is_relative_to(LOCAL) else real_is_file(p)), \
                     patch.object(Path, 'is_dir', lambda p: False if p.is_relative_to(LOCAL) else real_is_dir(p)), \
                     patch.object(urllib.request, 'urlopen', self.fetch):
                    argv = build_arguments(suite, work)
                props = dict(arg[3:].split('=', 1) for arg in argv if arg.startswith('-p:'))
                self.assertIn('CandidateResponseSource', props, 'WirePeer must override Linux Response default')
                self.assertIn('CandidateNativeRoot', props, 'WirePeer must override Linux native default')
                response = Path(props['CandidateResponseSource'])
                native = Path(props['CandidateNativeRoot'])
                self.assertTrue(response.is_relative_to(work))
                self.assertTrue(native.is_relative_to(work))
                self.assertEqual(set(self.requested), set(EXPECTED))
                self.assertEqual(len(self.requested), len(EXPECTED))
                actual = {'Helpers/Response.cs': hashlib.sha256(response.read_bytes()).hexdigest()}
                actual.update({p.relative_to(native).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in native.rglob('*.cs')})
                self.assertEqual(actual, EXPECTED)
                includes = [n.attrib['Include'] for n in ET.parse(ROOT/'tests/unity-core/WirePeer.csproj').iter('Compile')
                            if '$(Candidate' in n.attrib['Include']]
                resolved = []
                for name in includes:
                    for key in ('CandidateResponseSource', 'CandidateNativeRoot'):
                        name = name.replace('$('+key+')', props[key])
                    resolved.append(Path(name))
                self.assertEqual(len(resolved), len(EXPECTED))
                self.assertTrue(all(p.is_file() and p.is_relative_to(work) for p in resolved))
            self.assertFalse(work.exists())

    def test_EWS002_local_missing_or_corrupt_source_fails_without_network_fallback(self):
        for name in EXPECTED:
            for fault in ('missing', 'corrupt'):
                with self.subTest(name=name, fault=fault), tempfile.TemporaryDirectory(prefix='wire-local-') as td:
                    work = Path(td)
                    snapshot = work/'snapshot'
                    for key, raw in self.payloads.items():
                        path = snapshot/key
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if key != name or fault != 'missing':
                            path.write_bytes(raw+(b'changed' if key == name and fault == 'corrupt' else b''))
                    expected_error = FileNotFoundError if fault == 'missing' else ValueError
                    with patch.object(wire, 'NATIVE_LOCAL', snapshot), \
                         patch.object(urllib.request, 'urlopen', side_effect=AssertionError('no network fallback')) as fetch:
                        with self.assertRaises(expected_error):
                            build_arguments('rw', work)
                        fetch.assert_not_called()
                self.assertFalse(work.exists())

    def test_EWS003_download_missing_empty_or_corrupt_source_fails_closed(self):
        for name in EXPECTED:
            for fault in ('missing', 'empty', 'corrupt'):
                with self.subTest(name=name, fault=fault), tempfile.TemporaryDirectory(prefix='wire-download-') as td:
                    work = Path(td)
                    def damaged(url, timeout):
                        self.assertTrue(url.startswith(PREFIX))
                        self.assertEqual(timeout, 30)
                        key = url[len(PREFIX):]
                        if key == name and fault == 'missing':
                            raise FileNotFoundError(key)
                        raw = self.payloads[key]
                        if key == name:
                            raw = b'' if fault == 'empty' else raw+b'changed'
                        return io.BytesIO(raw)
                    with patch.object(wire, 'NATIVE_LOCAL', work/'absent-snapshot'), \
                         patch.object(urllib.request, 'urlopen', damaged):
                        with self.assertRaises(FileNotFoundError if fault == 'missing' else ValueError):
                            build_arguments('er', work)
                self.assertFalse(work.exists())

    def test_EWS004_other_suite_source_overrides_are_unchanged(self):
        for suite in ('ec', 'ep', 'ce'):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory(prefix='wire-other-') as td:
                work = Path(td)
                self.requested = []
                with patch.object(wire, 'NATIVE_LOCAL', work/'absent-snapshot'), \
                     patch.object(urllib.request, 'urlopen', self.fetch):
                    argv = build_arguments(suite, work)
                props = dict(arg[3:].split('=', 1) for arg in argv if arg.startswith('-p:'))
                self.assertEqual('CandidateResponseSource' in props, suite == 'ec')
                self.assertNotIn('CandidateNativeRoot', props)
                self.assertEqual(self.requested, ['Helpers/Response.cs'] if suite == 'ec' else [])
            self.assertFalse(work.exists())

    def test_EWS005_build_gate_still_rejects_warnings_exit_and_cleanup_failures(self):
        tree = ast.parse((ROOT/'tests/verify_editor_wire.py').read_bytes())
        gate = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(ast.unparse(t) == "report['build_passed']" for t in n.targets))
        code = compile(ast.Module(body=[gate], type_ignores=[]), 'actual-wire-build-gate', 'exec')
        good = dict(exit_code=0, timed_out=False, natural_tree_exit=True,
                    cleanup_complete=True, temporary_home_absent=True, stdout='', stderr='')
        with tempfile.TemporaryDirectory(prefix='wire-gate-') as td:
            dll = Path(td)/'fixture.dll'
            dll.write_bytes(b'gate-only fixture; not compiled output')
            faults = [dict(exit_code=1), dict(timed_out=True), dict(natural_tree_exit=False),
                      dict(cleanup_complete=False), dict(temporary_home_absent=False)]
            faults.extend({stream: text} for stream in ('stdout', 'stderr')
                          for text in ('ResourceWarning: leak', 'warning CS0649: fixture'))
            for fault in [{}, *faults]:
                with self.subTest(fault=fault):
                    env = dict(vars(wire), report={}, dll=dll, build={**good, **fault})
                    exec(code, env)
                    self.assertEqual(env['report']['build_passed'], not fault)
            dll.unlink()
            env = dict(vars(wire), report={}, dll=dll, build=good)
            exec(code, env)
            self.assertFalse(env['report']['build_passed'])
        self.assertFalse(Path(td).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
