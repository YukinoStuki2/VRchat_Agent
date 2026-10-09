"""Exercise the real strict verifier's source resolver without executing its historical aggregate."""
import ast,hashlib,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence/verify-plugin-live-20261009-strict.py'
def resolver():
    tree=ast.parse(SOURCE.read_text())
    nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))]
    ns={'__file__':str(SOURCE),'ROOT':ROOT}
    exec(compile(ast.Module(nodes,type_ignores=[]),str(SOURCE),'exec'),ns)
    return ns['current'],ns.get('reader_origins')
class EvidenceSourceTests(unittest.TestCase):
    def test_ES001_upstream_and_semantic_aliases_use_declared_origins(self):
        current,origins=resolver()
        self.assertIsNotNone(origins,'reader namespace resolver missing')
        for kind,name in [('assets','native-asset-effects'),('prefabs','prefab-reader')]:
            report=json.loads((ROOT/'evidence'/f'{name}-plugin-live-20261009-strict.json').read_text())
            paths=origins(kind)
            selected={n:h for n,h in report['after'].items() if n in paths}
            self.assertEqual(len(selected),2 if kind=='assets' else 6)
            self.assertTrue(current(ROOT,selected,origins=paths))
    def test_ES002_real_drift_and_unknown_or_escaping_keys_are_rejected(self):
        current,origins=resolver()
        self.assertIsNotNone(origins)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'actual').write_bytes(b'current')
            good=hashlib.sha256(b'current').hexdigest()
            self.assertTrue(current(root,{'fixture':good},origins={'fixture':root/'actual'}))
            self.assertFalse(current(root,{'fixture':'0'*64},origins={'fixture':root/'actual'}))
            for key in ('fixture','runner','native/Tools/unknown.cs','Tools/unknown.cs','../actual','/actual','a/../actual'):
                with self.subTest(key=key),self.assertRaises(ValueError):current(root,{key:good})
            self.assertFalse(current(root,{'missing':good}))
            with self.assertRaises(ValueError):origins('unknown')
if __name__=='__main__':unittest.main(verbosity=2)
