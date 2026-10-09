"""Generated product-owned native reader, not a host/upstream patch."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UP = Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity')


def generator():
    path = ROOT / 'distribution/materialize_reflection.py'
    if not path.is_file():
        raise AssertionError('restricted native reflection materializer missing')
    spec = importlib.util.spec_from_file_location('reflection_source', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReflectionSourceTests(unittest.TestCase):
    def test_RFS001_native_bodies_preserved_and_no_global_resolver(self):
        module = generator()
        original = (UP / module.SOURCE).read_bytes()
        before = hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory(prefix='candidate-reflection-source-') as td:
            dest = Path(td) / 'new'
            module.materialize(UP, dest)
            text = (dest / (module.TYPE + '.cs')).read_text(encoding='utf-8')
            self.assertIn('class CandidateScopedUnityReflect', text)
            self.assertNotIn('[McpForUnityTool(', text)
            for forbidden in ('UnityTypeResolver.', 'GetLoadedAssemblies(', 'GetExportedTypes(', 'Assembly.Load', 'Type.GetType('):
                self.assertNotIn(forbidden, text)
            for name in ('GetTypeInfo', 'GetMemberInfo', 'SearchTypes', 'FormatTypeName', 'FormatMethodDetail', 'FormatMethodSignature', 'GetObsoleteMembers'):
                self.assertEqual(module.method(original.decode(), name), module.method(text, name), name)
            self.assertEqual(before, hashlib.sha256((UP / module.SOURCE).read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                module.materialize(UP, dest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
