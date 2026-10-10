"""Export boundaries only; fixtures are not an installable candidate."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def driver():
    spec = importlib.util.spec_from_file_location('portable_export', ROOT/'tests/verify_portable.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PayloadExportTests(unittest.TestCase):
    def test_PE001_export_requires_verified_payload_and_copies_exact_bytes(self):
        module = driver()
        self.assertTrue(callable(getattr(module, 'export_payload', None)),
                        'missing verified development payload export')
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            root = Path(td)
            package = root/'package'; package.mkdir()
            (package/'file.bin').write_bytes(b'fixture, not product')
            expected = {'file.bin': hashlib.sha256((package/'file.bin').read_bytes()).hexdigest()}
            report = {'passed': True, 'source_unchanged': True, 'payload_unchanged': True}
            result = module.export_payload(package, expected, root/'export', report)
            self.assertEqual((root/'export/file.bin').read_bytes(), b'fixture, not product')
            self.assertEqual(result['inventory'], expected)
            self.assertIs(result['product_approved'], False)
            self.assertEqual(result['scope'], 'verified development payload; not installable approval')


    def test_PE002_failed_or_incomplete_verification_cannot_export(self):
        module = driver()
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            root = Path(td); package = root/'package'; package.mkdir()
            (package/'file').write_bytes(b'fixture')
            expected = {'file': hashlib.sha256(b'fixture').hexdigest()}
            for field in ('passed', 'source_unchanged', 'payload_unchanged'):
                for bad in (False, None, 1):
                    report: dict[str, object] = dict(passed=True, source_unchanged=True, payload_unchanged=True)
                    report[field] = bad
                    destination = root/(field + '-' + str(bad))
                    with self.subTest(field=field, bad=bad), self.assertRaisesRegex(ValueError, 'unverified'):
                        module.export_payload(package, expected, destination, report)
                    self.assertFalse(destination.exists())


    def test_PE003_drift_never_leaves_a_partial_export(self):
        module = driver()
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            root = Path(td); package = root/'package'; package.mkdir()
            (package/'file').write_bytes(b'fixture')
            report = dict(passed=True, source_unchanged=True, payload_unchanged=True)
            for expected in ({'file': '0'*64}, {}, {'file': hashlib.sha256(b'fixture').hexdigest(), 'missing': '0'*64}):
                destination = root/'export'
                with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, 'drift'):
                    module.export_payload(package, expected, destination, report)
                self.assertFalse(destination.exists())

    def test_PE004_existing_destination_is_never_modified(self):
        module = driver()
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            root = Path(td); package = root/'package'; package.mkdir()
            (package/'file').write_bytes(b'fixture')
            destination = root/'existing'; destination.mkdir()
            (destination/'kept').write_bytes(b'user')
            with self.assertRaises(FileExistsError):
                module.export_payload(package, {'file': hashlib.sha256(b'fixture').hexdigest()},
                                      destination, dict(passed=True, source_unchanged=True, payload_unchanged=True))
            self.assertEqual([p.name for p in destination.iterdir()], ['kept'])
            self.assertEqual((destination/'kept').read_bytes(), b'user')


    def test_PE005_source_links_and_unsafe_destinations_are_refused(self):
        from unittest.mock import patch
        module = driver()
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            root = Path(td); package = root/'package'; package.mkdir()
            target = package/'file'; target.write_bytes(b'fixture')
            report = dict(passed=True, source_unchanged=True, payload_unchanged=True)
            expected = {'file': hashlib.sha256(b'fixture').hexdigest()}
            # Inject link identity portably; this is an export-policy test, not a kernel claim.
            original = Path.is_symlink
            with patch.object(Path, 'is_symlink', lambda p: p == target or original(p)):
                with self.assertRaisesRegex(ValueError, 'link'):
                    module.export_payload(package, expected, root/'export', report)
            self.assertFalse((root/'export').exists())
            for destination in (package/'nested', root/'uncreated'/'..'/'export'):
                with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, 'destination'):
                    module.export_payload(package, expected, destination, report)
                self.assertFalse(destination.exists())

    def test_PE006_copy_failure_removes_only_owned_output(self):
        from unittest.mock import patch
        module = driver()
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            root = Path(td); package = root/'package'; package.mkdir()
            (package/'file').write_bytes(b'fixture')
            expected = {'file': hashlib.sha256(b'fixture').hexdigest()}
            with patch.object(module.shutil, 'copytree', side_effect=OSError('fixture copy failed')):
                with self.assertRaises(OSError):
                    module.export_payload(package, expected, root/'export',
                                          dict(passed=True, source_unchanged=True, payload_unchanged=True))
            self.assertFalse((root/'export').exists())
            self.assertEqual((package/'file').read_bytes(), b'fixture')


    def test_PE007_cli_and_ci_export_are_opt_in_and_after_validation(self):
        import ast
        from types import SimpleNamespace
        from unittest.mock import Mock
        source = (ROOT/'tests/verify_portable.py').read_text(encoding='utf-8')
        self.assertIn("parser.add_argument('--retain-payload'", source, 'missing opt-in export CLI')
        tree = ast.parse(source)
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        block = next(n for n in main.body if isinstance(n, ast.With))
        gate = next(i for i, n in enumerate(block.body) if isinstance(n, ast.Assign)
                    and any(ast.unparse(t) == "report['passed']" for t in n.targets))
        call = next(n for n in block.body[gate+1:] if isinstance(n, ast.If)
                    and ast.unparse(n.test) == 'args.retain_payload')
        code = compile(ast.Module(body=[call], type_ignores=[]), 'export-cli-tail', 'exec')
        for destination in (None, Path('output')):
            exporter = Mock(return_value={'product_approved': False})
            report = {'passed': True}
            exec(code, {'args': SimpleNamespace(retain_payload=destination), 'report': report,
                        'export_payload': exporter, 'relocated': Path('fixture'), 'before': {}})
            self.assertEqual(exporter.call_count, int(destination is not None))
        flow = (ROOT.parent/'.github/workflows/candidate-portable.yml').read_text(encoding='utf-8')
        for marker in ('retain_payload:', 'default: false', 'test_payload_export.py',
                       '--retain-payload', 'include-hidden-files: true', 'development-payload-unapproved-'):
            self.assertIn(marker, flow)


    def test_PE008_exception_after_validation_is_recorded_as_failure(self):
        import json
        module = driver()
        with tempfile.TemporaryDirectory(prefix='candidate-export-') as td:
            report = {'passed': False}
            output = Path(td)/'report.json'
            with self.assertRaisesRegex(OSError, 'late export failure'):
                with module.recorded_directory(report, output):
                    report['passed'] = True
                    raise OSError('late export failure')
            observed = json.loads(output.read_text())
            self.assertIs(observed['passed'], False)
            self.assertIs(observed['temporary_root_absent'], True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
