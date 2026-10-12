"""Checks real release payloads, with source archives supplied by the operator.
Usage: python3 -I -B test_distribution.py RUNTIME_ZIP UPSTREAM_ZIP PREVIOUS_ZIP
No package code, Unity, model or external publication is executed.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
RUNTIME, UPSTREAM, PREVIOUS = map(lambda p:Path(p).resolve(strict=True),sys.argv[1:4])
sys.argv = sys.argv[:1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Distribution(unittest.TestCase):
    def test_complete_payload_metadata_only_and_pinned_dependency(self):
        plan = json.loads((HERE/'distribution-plan.json').read_bytes())
        provenance = json.loads((HERE/'coplay-provenance.json').read_bytes())
        self.assertEqual(sha(UPSTREAM.read_bytes()), provenance['source_archive_sha256'])
        with tempfile.TemporaryDirectory(prefix='vrc-dist-coplay-test-') as td:
            output = Path(td)/'out'
            proc = subprocess.run([sys.executable,'-I','-B',str(HERE/'assemble.py'),str(RUNTIME),str(output)],
                                  capture_output=True,text=True,timeout=90)
            self.assertEqual(proc.returncode,0,proc.stderr)
            index = json.loads((output/'index.json').read_bytes())
            main = index['packages']['com.yukino.vrchat-agent']['versions']['0.2.0-preview.2']
            coplay = index['packages']['com.coplaydev.unity-mcp']['versions']['10.2.0']
            self.assertEqual(main['vpmDependencies'], {'com.coplaydev.unity-mcp':'=10.2.0'})
            self.assertEqual(main['dependencies']['com.coplaydev.unity-mcp'],'10.2.0')
            old_index = json.loads((HERE/'previous-index.json').read_bytes())
            self.assertEqual(index['packages']['com.yukino.vrchat-agent']['versions']['0.2.0-preview.1'],
                             old_index['packages']['com.yukino.vrchat-agent']['versions']['0.2.0-preview.1'])
            with zipfile.ZipFile(output/plan['candidate_filename']) as new, zipfile.ZipFile(PREVIOUS) as old:
                self.assertEqual(set(new.namelist()),set(old.namelist()))
                self.assertEqual({n for n in new.namelist() if new.read(n)!=old.read(n)},
                                 {'package.json','README.md','CANDIDATE_STATUS.md'})
                self.assertEqual({n:sha(new.read(n)) for n in new.namelist()},plan['members'])
                manifest = json.loads(new.read('package.json'))
                self.assertEqual(dict(manifest,zipSHA256=sha((output/plan['candidate_filename']).read_bytes())),main)
                old_manifest = json.loads(old.read('package.json'))
                self.assertEqual(manifest['vrchatAgentVerification'],old_manifest['vrchatAgentVerification'])
                self.assertFalse(manifest['vrchatAgentVerification']['unity_verified'])
                guids = [re.search(rb'^guid: ([0-9a-f]{32})$',new.read(n),re.M).group(1)
                         for n in new.namelist() if n.endswith('.meta')]
            prefix = 'unity-mcp-'+provenance['upstream_commit']+'/'
            with zipfile.ZipFile(UPSTREAM) as source, zipfile.ZipFile(output/plan['coplay_filename']) as dep:
                originals = {n[len(prefix+'MCPForUnity/'):]:source.read(n) for n in source.namelist()
                             if n.startswith(prefix+'MCPForUnity/') and not n.endswith('/')}
                self.assertEqual({n:sha(b) for n,b in originals.items()},provenance['upstream_files'])
                self.assertEqual(set(dep.namelist())-originals.keys(),set(provenance['added_files']))
                self.assertEqual({n for n,b in originals.items() if dep.read(n)!=b},{'package.json'})
                self.assertEqual(dep.read('LICENSE'),source.read(prefix+'LICENSE'))
                self.assertEqual({n:sha(dep.read(n)) for n in dep.namelist()},provenance['distribution_files'])
                package = json.loads(dep.read('package.json'))
                original_manifest = json.loads(originals['package.json'])
                self.assertEqual({k for k in package.keys()|original_manifest.keys() if package.get(k)!=original_manifest.get(k)},
                                 {'url','vpmDependencies','license','licensesUrl'})
                self.assertEqual(dict(package,zipSHA256=sha((output/plan['coplay_filename']).read_bytes())),coplay)
                self.assertEqual(len(dep.namelist()),len({n.casefold() for n in dep.namelist()}))
                guids += [re.search(rb'^guid: ([0-9a-f]{32})$',dep.read(n),re.M).group(1)
                          for n in dep.namelist() if n.endswith('.meta')]
            self.assertEqual(len(guids),len(set(guids)), 'duplicate Unity GUID across installed packages')
            checks = json.loads((output/'SHA256SUMS.json').read_bytes())
            self.assertEqual(set(checks),{p.name for p in output.iterdir()}-{'SHA256SUMS.json'})
            for name,digest in checks.items():
                self.assertEqual(sha((output/name).read_bytes()),digest)
            self.assertEqual(sha((output/plan['plugin_filename']).read_bytes()),plan['plugin_sha256'])

    def test_corrupt_runtime_refused(self):
        with tempfile.TemporaryDirectory(prefix='vrc-reject-runtime-') as td:
            base = Path(td); (base/'bad.zip').write_bytes(b'not frozen runtime')
            proc = subprocess.run([sys.executable,'-I','-B',str(HERE/'assemble.py'),str(base/'bad.zip'),str(base/'out')],
                                  capture_output=True,text=True,timeout=20)
            self.assertNotEqual(proc.returncode,0)
            self.assertIn('runtime hash mismatch',proc.stderr)
            self.assertFalse((base/'out').exists())

    def test_corrupt_coplay_refused(self):
        with tempfile.TemporaryDirectory(prefix='vrc-reject-coplay-') as td:
            base = Path(td)
            plan = json.loads((HERE/'distribution-plan.json').read_bytes())
            for name in ('assemble.py','zip_layout.py','distribution-plan.json','source-overlay.zip',plan['plugin_filename']):
                shutil.copy2(HERE/name,base/name)
            (base/plan['coplay_filename']).write_bytes(b'not frozen dependency')
            proc = subprocess.run([sys.executable,'-I','-B',str(base/'assemble.py'),str(RUNTIME),str(base/'out')],
                                  capture_output=True,text=True,timeout=90)
            self.assertNotEqual(proc.returncode,0)
            self.assertIn('Coplay archive hash mismatch',proc.stderr)
            self.assertFalse((base/'out').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
