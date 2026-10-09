"""Offline fixed-baseline reconstruction; patch only a disposable copy."""
import hashlib,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NativePatchTests(unittest.TestCase):
    def test_NP001_patch_rebuilds_all_declared_native_bytes(self):
        provenance=json.loads((ROOT/'native/PROVENANCE.json').read_text())
        upstream=Path(provenance['source'])
        self.assertEqual(subprocess.check_output(['git','rev-parse','HEAD'],cwd=upstream,text=True).strip(),provenance['upstream_commit'])
        with tempfile.TemporaryDirectory(prefix='native-patch-contract-') as td:
            work=Path(td)
            for name,digest in provenance['baseline_sha256'].items():
                source=upstream/name if name=='LICENSE' else upstream/'Server'/name
                data=source.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),digest,name)
                path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            result=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(ROOT/'native/candidate-runtime.patch')],cwd=work,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            expected={p.relative_to(ROOT/'native/src').as_posix():p.read_bytes() for p in (ROOT/'native/src').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
            actual={p.relative_to(work/'src').as_posix():p.read_bytes() for p in (work/'src').rglob('*') if p.is_file()}
            self.assertEqual(set(actual),set(expected))
            self.assertEqual([n for n in expected if expected[n]!=actual[n]],[],'declared patch does not reconstruct actual source')
            for name in ('LICENSE','pyproject.toml'):self.assertEqual((work/name).read_bytes(),(ROOT/'native'/name).read_bytes())
        self.assertFalse(work.exists())
if __name__=='__main__':unittest.main(verbosity=2)
