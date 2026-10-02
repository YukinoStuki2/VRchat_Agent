"""Portable diagnostic backend boundary; no Unity/user files or approval bypass."""
import importlib.util
import sys
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'diagnostics'))

class DiagnosticDistributionTests(unittest.TestCase):
    def test_DD001_backend_is_candidate_local_and_never_experiment_fallback(self):
        import server
        self.assertTrue(server.ENTRY.is_relative_to(ROOT), 'backend still depends on experimental workspace')
        self.assertNotIn('Experiments~',str(server.ENTRY))

    def test_DD002_builder_rejects_wrong_archive_before_creating_output(self):
        path=ROOT/'distribution/diagnostic_backend.py'
        self.assertTrue(path.is_file(), 'pinned diagnostic builder missing')
        spec=importlib.util.spec_from_file_location('diagnostic_builder',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='diag-build-contract-') as td:
            archive=Path(td)/'wrong.tar.xz';archive.write_bytes(b'not a Node archive')
            output=Path(td)/'payload'
            with self.assertRaisesRegex(ValueError,'node_archive_hash'):
                module.build(archive,output)
            self.assertFalse(output.exists())

    def test_DD004_missing_bundled_backend_does_not_use_system_node(self):
        from unittest.mock import patch
        import server
        with tempfile.TemporaryDirectory(prefix='diag-no-backend-') as td:
            root=Path(td)/'snapshot';root.mkdir()
            with patch.object(server,'ENTRY',Path(td)/'missing/filesystem/dist/index.js'):
                with self.assertRaisesRegex(ValueError,'bundled_diagnostic_backend_invalid'):
                    server.backend_transport(root)

    def test_DD005_changed_missing_extra_files_and_inventory_are_rejected(self):
        from unittest.mock import patch
        import hashlib,json
        import server
        pins=json.loads((ROOT/'distribution/diagnostics-backend.lock.json').read_bytes())
        key='windows-x86_64' if sys.platform=='win32' else 'linux-x86_64'
        node='node/node.exe' if sys.platform=='win32' else 'node/node'
        with tempfile.TemporaryDirectory(prefix='diag-payload-integrity-') as td:
            base=Path(td);entry=base/'filesystem/dist/index.js';entry.parent.mkdir(parents=True)
            entry.write_bytes(b'fixture-not-executable');binary=base/node;binary.parent.mkdir();binary.write_bytes(b'fixture-node')
            doc={'schema':1,'platform':key,'node_archive_sha256':pins['platforms'][key]['sha256'],
                'node_version':pins['node_version'],'source_inputs':pins['inputs'],'upstream_commit':pins['upstream_commit'],
                'node_executable':node,'entry':'filesystem/dist/index.js','missing_notice_packages':[],
                'files':{p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (entry,binary)}}
            inventory=base/'inventory.json';inventory.write_text(json.dumps(doc))
            with patch.object(server,'ENTRY',entry):
                self.assertEqual(server.bundled_node(),binary)
                entry.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'bundled_diagnostic_backend_invalid'):server.bundled_node()
                entry.write_bytes(b'fixture-not-executable')
                extra=base/'unlisted';extra.write_bytes(b'x')
                with self.assertRaisesRegex(ValueError,'bundled_diagnostic_backend_invalid'):server.bundled_node()
                extra.unlink();binary.unlink()
                with self.assertRaisesRegex(ValueError,'bundled_diagnostic_backend_invalid'):server.bundled_node()
                binary.write_bytes(b'fixture-node');doc['node_executable']='node/foreign.exe';inventory.write_text(json.dumps(doc))
                with self.assertRaisesRegex(ValueError,'bundled_diagnostic_backend_invalid'):server.bundled_node()

if __name__=='__main__':unittest.main(verbosity=2)
