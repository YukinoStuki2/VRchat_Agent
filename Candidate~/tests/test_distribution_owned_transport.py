"""Additive transport layout only; no Unity importer or whole-package acceptance."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity')


class OwnedDistributionTests(unittest.TestCase):
    def test_OD001_materializes_additive_owned_type_without_upstream_edits(self):
        module = ROOT / 'distribution/materialize_owned_transport.py'
        self.assertTrue(module.is_file(), 'OD001 additive transport materializer missing')
        spec = importlib.util.spec_from_file_location('materializer', module)
        assert spec is not None and spec.loader is not None
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        source = UPSTREAM / 'Editor/Services/Transport/Transports/WebSocketTransportClient.cs'
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='candidate-additive-transport-') as td:
            target = Path(td) / 'OwnedTransport'
            m.materialize(UPSTREAM, target)
            generated = (target / 'CandidateOwnedWebSocketTransportClient.cs').read_text()
            self.assertIn('public sealed class CandidateOwnedWebSocketTransportClient', generated)
            self.assertNotIn('public class WebSocketTransportClient', generated)
            self.assertIn('public CandidateOwnedWebSocketTransportClient(Uri endpoint', generated)
            self.assertNotIn('public CandidateOwnedWebSocketTransportClient(IToolDiscoveryService', generated)
            self.assertEqual(json.loads((target / 'CandidateOwnedTransport.asmref').read_text()),
                             {'reference': 'GUID:98f702da6ca044be59a864a9419c4eab'})
            self.assertTrue((target / 'LICENSE.md').is_file())
            for f in list(target.iterdir()):
                if not f.name.endswith('.meta'):
                    self.assertTrue(f.with_name(f.name + '.meta').is_file(), f.name)
            other = Path(td) / 'second'
            m.materialize(UPSTREAM, other)
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()},
                             {p.name: p.read_bytes() for p in other.iterdir()})
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_OD004_shipped_additive_source_matches_reconstruction(self):
        spec = importlib.util.spec_from_file_location('materializer', ROOT / 'distribution/materialize_owned_transport.py')
        assert spec is not None and spec.loader is not None
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(prefix='candidate-shipped-source-') as td:
            target = Path(td) / 'rebuilt'; m.materialize(UPSTREAM, target)
            shipped = ROOT / 'package/Editor/OwnedTransport'
            self.assertEqual({p.name: p.read_bytes() for p in target.iterdir()},
                             {p.name: p.read_bytes() for p in shipped.iterdir()})

    def test_OD005_existing_destination_never_overwritten(self):
        spec = importlib.util.spec_from_file_location('materializer', ROOT / 'distribution/materialize_owned_transport.py')
        assert spec is not None and spec.loader is not None
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(prefix='candidate-no-overwrite-') as td:
            target = Path(td) / 'occupied'; target.mkdir(); keep = target / 'user'; keep.write_bytes(b'unchanged')
            with self.assertRaises(FileExistsError): m.materialize(UPSTREAM, target)
            self.assertEqual(keep.read_bytes(), b'unchanged')
            self.assertEqual(len(list(target.iterdir())), 1)

    def test_OD006_drifted_upstream_rejected_before_destination_created(self):
        spec = importlib.util.spec_from_file_location('materializer', ROOT / 'distribution/materialize_owned_transport.py')
        assert spec is not None and spec.loader is not None
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory(prefix='candidate-upstream-drift-') as td:
            altered = Path(td) / 'input'; target = Path(td) / 'output'
            source = altered / m.SOURCE; source.parent.mkdir(parents=True)
            source.write_bytes((UPSTREAM / m.SOURCE).read_bytes() + b'\n// altered\n')
            with self.assertRaisesRegex(ValueError, 'owned_transport_input_drift'):
                m.materialize(altered, target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
