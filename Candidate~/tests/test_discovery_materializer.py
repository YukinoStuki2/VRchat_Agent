"""Pinned offline generation; no install, register, test execution or native edits."""
from pathlib import Path
import hashlib,json,re,shutil,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from distribution.materialize_discovery import materialize,PINS,COPLAY_SHA
NATIVE=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity')
FRAMEWORK=ROOT/'evidence/test-framework-1.1.31'

class DiscoveryMaterializerTests(unittest.TestCase):
    def test_DM001_original_source_and_method_provenance(self):
        with tempfile.TemporaryDirectory(prefix='discovery-provenance-') as td:
            proof=materialize(FRAMEWORK,NATIVE,Path(td)/'out')
            self.assertEqual(proof['framework_inputs'],{n:hashlib.sha256((FRAMEWORK/n).read_bytes()).hexdigest() for n in PINS})
            raw=(NATIVE/'Editor/Services/TestRunnerService.cs').read_bytes()
            parts=re.findall(r'^        private static void CollectFromNode\([^)]*\)\n        \{\n.*?^        \}',raw.decode(),re.M|re.S)
            self.assertEqual(len(parts),1)
            self.assertEqual(proof['collector_before_sha256'],hashlib.sha256(parts[0].encode()).hexdigest())
            self.assertEqual(hashlib.sha256(raw).hexdigest(),COPLAY_SHA)
            for name,sha in proof['outputs'].items():self.assertEqual(hashlib.sha256((Path(td)/'out'/name).read_bytes()).hexdigest(),sha)
            self.assertFalse(proof['registered_tool']);self.assertFalse(proof['installed_upstream_files_modified'])

    def test_DM002_reproducible_generated_bytes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='discovery-provenance-') as td:
            dest=Path(td)/'out';materialize(FRAMEWORK,NATIVE,dest)
            generated={p.name:p.read_bytes() for p in dest.iterdir()}
            checked={p.name:p.read_bytes() for p in (ROOT/'package/Editor/ScopedTests').iterdir() if not p.name.startswith('CandidateDiscoveryJob.cs')}
            self.assertEqual(generated,checked)
            with self.assertRaises(FileExistsError):materialize(FRAMEWORK,NATIVE,dest)
            self.assertEqual({p.name:p.read_bytes() for p in dest.iterdir()},generated)

    def test_DM003_source_drift_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix='discovery-provenance-') as td:
            tmp=Path(td);framework=tmp/'framework'
            for name in PINS:
                dest=framework/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(FRAMEWORK/name,dest)
            first=framework/next(iter(PINS));original=first.read_bytes();first.write_bytes(original+b'\n// drift\n')
            with self.assertRaisesRegex(ValueError,'test_framework_source_drift'):materialize(framework,NATIVE,tmp/'out')
            self.assertFalse((tmp/'out').exists());first.write_bytes(original)
            native=tmp/'native';source=native/'Editor/Services/TestRunnerService.cs';source.parent.mkdir(parents=True)
            source.write_bytes((NATIVE/'Editor/Services/TestRunnerService.cs').read_bytes()+b'\n// drift\n')
            with self.assertRaisesRegex(ValueError,'coplay_test_source_drift'):materialize(framework,native,tmp/'out')
            self.assertFalse((tmp/'out').exists())

if __name__=='__main__':unittest.main()
