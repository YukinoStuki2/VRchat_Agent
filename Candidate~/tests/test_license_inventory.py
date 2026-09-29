"""Read real hash-locked installed license bytes; no system/environment writes."""
from pathlib import Path
import hashlib
import json
import copy
import importlib.util
import unittest
import tempfile
import base64
from importlib import metadata
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def collector():
    path = ROOT / 'distribution/license_inventory.py'
    if not path.is_file():
        raise AssertionError('license inventory collector missing')
    spec = importlib.util.spec_from_file_location('candidate_licenses', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class LicenseInventoryTests(unittest.TestCase):
    def test_LI001_actual_lock_inventory_cannot_hide_missing_license_text(self):
        report, files = collector().collect(supplements={})
        self.assertGreater(report['active_lock_count'], 0)
        self.assertEqual(len(report['dependencies']), report['active_lock_count'])
        self.assertIn('fastmcp-slim', report['missing_license_text'])
        self.assertFalse(report['complete'])
        for row in report['dependencies']:
            for license in row['license_files']:
                self.assertEqual(hashlib.sha256(files[license['bundle_path']]).hexdigest(), license['sha256'])
                self.assertTrue(license['record_verified'])
                self.assertGreater(len(files[license['bundle_path']]), 20)
        self.assertFalse(any(Path(p).is_absolute() or '..' in Path(p).parts for p in files))


    def test_LI002_pinned_upstream_supplement_completes_license_text_not_product(self):
        report, files = collector().collect()
        self.assertTrue(report['complete'])
        self.assertEqual(report['missing_license_text'], [])
        self.assertFalse(report['selected_wheel_hashes_verified'])
        self.assertFalse(report['cpython_redistribution_verified'])
        slim = next(r for r in report['dependencies'] if r['name'] == 'fastmcp-slim')
        self.assertEqual(slim['version'], '3.4.7')
        self.assertEqual(slim['license_expression'], 'Apache-2.0')
        self.assertEqual(slim['license_files'][0]['source'], 'pinned-upstream-supplement')
        self.assertEqual(slim['license_files'][0]['upstream_commit'], '758397efa66e2cedac95ada540001bc44a95a646')
        self.assertIn(b'Apache License', files[slim['license_files'][0]['bundle_path']])


    def test_LI003_declared_notice_missing_is_not_hidden_by_another_license(self):
        module = collector()
        with tempfile.TemporaryDirectory(prefix='candidate-license-declared-') as td:
            info = Path(td) / 'fixture-1.0.dist-info'; (info / 'licenses').mkdir(parents=True)
            body = b'SYNTHETIC LICENSE TEXT FOR TESTING ONLY'
            (info / 'licenses/LICENSE').write_bytes(body)
            (info / 'METADATA').write_text('Metadata-Version: 2.4\nName: fixture\nVersion: 1.0\nLicense-File: LICENSE\nLicense-File: NOTICE\n')
            digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b'=').decode()
            (info / 'RECORD').write_text('fixture-1.0.dist-info/licenses/LICENSE,sha256=' + digest + ',' + str(len(body)) + '\n')
            fake = metadata.PathDistribution(info)
            installation = {'installed': {'fixture': '1.0'}, 'platform': 'fixture', 'python': 'fixture'}
            with patch.object(module.verify, 'inspect_installation', return_value=installation), patch.object(module.metadata, 'distribution', return_value=fake):
                with self.assertRaisesRegex(ValueError, 'declared_license_missing'):
                    module.collect(supplements={})


    def test_LI004_supplement_wrong_version_hash_or_path_is_refused(self):
        module = collector()
        original = json.loads((ROOT / 'distribution/license-supplements.json').read_text())
        for kind in ('version', 'hash', 'path'):
            mapping = copy.deepcopy(original); entry = mapping['fastmcp-slim']
            if kind == 'version': entry['version'] = '0.0.0'
            elif kind == 'hash': entry['files'] = {next(iter(entry['files'])): '0'*64}
            else: entry['files'] = {'../license-supplements.json': '0'*64}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                module.collect(supplements=mapping)

    def test_LI005_installed_license_record_tamper_refused(self):
        module = collector()
        with tempfile.TemporaryDirectory(prefix='candidate-license-drift-') as td:
            info = Path(td) / 'fixture-1.0.dist-info'; info.mkdir()
            (info / 'LICENSE').write_text('MODIFIED SYNTHETIC LICENSE TEXT')
            (info / 'METADATA').write_text('Metadata-Version: 2.4\nName: fixture\nVersion: 1.0\nLicense-File: LICENSE\n')
            digest = base64.urlsafe_b64encode(hashlib.sha256(b'ORIGINAL').digest()).rstrip(b'=').decode()
            (info / 'RECORD').write_text('fixture-1.0.dist-info/LICENSE,sha256=' + digest + ',8\n')
            fake = metadata.PathDistribution(info)
            installation = {'installed': {'fixture': '1.0'}, 'platform': 'fixture', 'python': 'fixture'}
            with patch.object(module.verify, 'inspect_installation', return_value=installation), patch.object(module.metadata, 'distribution', return_value=fake):
                with self.assertRaisesRegex(ValueError, 'license_record_drift'):
                    module.collect(supplements={})


if __name__ == '__main__':
    unittest.main(verbosity=2)
