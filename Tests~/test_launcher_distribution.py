"""Launcher VPM regression tests; fixture-only, never touches installed packages."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import io
ROOT = Path(__file__).resolve().parents[1]

def load():
    spec = importlib.util.spec_from_file_location('launcher_dist', ROOT/'VPM~/build_launcher.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Distribution(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.m=load();self.p=self.root/self.m.PREFIX
        self.files={'package.json':json.dumps({'name':self.m.ID,'version':self.m.VERSION,'vpmDependencies':{'com.yukino.vrchat-readonly-mcp':'0.1.2','com.yukino.vrchat-managed-editing':'0.1.0-preview.2'}}).encode(),'README.md':b'preview','LICENSE':b'MIT','THIRD_PARTY_NOTICES.md':b'notices','Editor/Test.cs':b'// fixture','Editor/Runtime~/launcher_supervisor.py':b'# fixture','Editor/Runtime~/bridge.py':b'# fixture','Editor/Runtime~/windows_processes.py':b'# fixture','Editor/Runtime~/admission_gate.py':b'# fixture'}
        self.proof={'local_checks_passed':True,'independent_source_reviews_passed':True,'unity_verified':False,'source_sha256':{}}
        for n,data in self.files.items():
            f=self.p/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
            self.proof['source_sha256'][n]=hashlib.sha256(data).hexdigest()
        self.old=json.loads((ROOT/'index.json').read_text())
        # A fixture baseline always excludes this new package even after local emit.
        if self.m.ID in self.old['packages']:
            self.old['packages'][self.m.ID]['versions'].pop(self.m.VERSION,None)
        (self.root/'index.json').write_text(json.dumps(self.old))
        self.proof_write()
    def proof_write(self):
        (self.root/'RESILIENCE_VERIFICATION.json').write_text(json.dumps(self.proof))
    def test_package_and_index_preserve_history(self):
        artifacts,index=self.m.build(self.root)
        for pid,record in self.old['packages'].items():
            for version,entry in record['versions'].items():self.assertEqual(entry,index['packages'][pid]['versions'][version])
        self.assertEqual(artifacts,self.m.build(self.root)[0])
        data=next(iter(artifacts.values()))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIn('package.json',z.namelist());self.assertIn('Editor/Runtime~/bridge.py',z.namelist())
            man=json.loads(z.read('package.json'))
            record=index['packages'][self.m.ID]['versions'][self.m.VERSION]
            self.assertEqual(record,dict(man,zipSHA256=hashlib.sha256(data).hexdigest()))
            self.assertIn('/'+self.m.TAG+'/',record['url'])
    def test_verified_source_drift_refused(self):
        (self.p/'Editor/Test.cs').write_text('// changed')
        with self.assertRaisesRegex(ValueError,'source drift'):self.m.build(self.root)
    def test_unreviewed_fails(self):
        self.proof['independent_source_reviews_passed']=False;self.proof_write()
        with self.assertRaisesRegex(ValueError,'verification gates'):self.m.build(self.root)
    def test_symlink_refused_before_hash(self):
        f=self.p/'Editor/Test.cs';data=f.read_bytes();f.unlink();outside=self.root/'outside.cs';outside.write_bytes(data);f.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'Symlink'):self.m.build(self.root)
    def test_unsafe_source_refused(self):
        self.proof['source_sha256']['../credential']=hashlib.sha256(b'').hexdigest();self.proof_write()
        with self.assertRaisesRegex(ValueError,'Unsafe'):self.m.build(self.root)
    def test_emit_identical_and_historic_zip_untouched(self):
        folder=self.root/'VPM~/packages';folder.mkdir(parents=True)
        oldzip=folder/'historical.zip';oldzip.write_bytes(b'never-replace')
        self.m.emit(self.root);before=(self.root/'index.json').read_bytes()
        self.assertEqual(self.m.emit(self.root),self.m.emit(self.root))
        self.assertEqual(before,(self.root/'index.json').read_bytes());self.assertEqual(oldzip.read_bytes(),b'never-replace')
    def test_conflicting_zip_does_not_publish_index(self):
        artifacts,_=self.m.build(self.root);folder=self.root/'VPM~/packages';folder.mkdir(parents=True)
        for name in artifacts:(folder/name).write_bytes(b'conflict')
        before=(self.root/'index.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'Immutable ZIP conflict'):self.m.emit(self.root)
        self.assertEqual(before,(self.root/'index.json').read_bytes())
    def test_existing_sameversion_hash_change_fails(self):
        _,index=self.m.build(self.root)
        index['packages'][self.m.ID]['versions'][self.m.VERSION]['zipSHA256']='0'*64
        (self.root/'index.json').write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError,'changed existing version'):self.m.build(self.root)

if __name__=='__main__':unittest.main()
