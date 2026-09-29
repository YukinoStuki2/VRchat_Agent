"""Portable archive checks; tiny tar fixtures are NOT an interpreter test."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module():
    path = ROOT/'distribution/portable_python.py'
    assert path.is_file(), 'portable_python assembly not implemented'
    spec = importlib.util.spec_from_file_location('portable_python',path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

class PortableArchiveTests(unittest.TestCase):
    def test_PP006_every_platform_notice_matches_publisher_hash(self):
        pins=json.loads((ROOT/'distribution/python-standalone.lock.json').read_text())
        for key,pin in pins['platforms'].items():
            for name,digest in {pin['metadata']:pin['metadata_sha256'],**pin['licenses']}.items():
                with self.subTest(platform=key,path=name):
                    self.assertEqual(hashlib.sha256((ROOT/'distribution'/name).read_bytes()).hexdigest(),digest)

    def test_PP001_archive_hash_checked_before_any_extraction(self):
        m = module()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'source.tar.gz'; target=Path(td)/'extracted'
            with tarfile.open(source,'w:gz') as tar:
                info=tarfile.TarInfo('python/bin/python3.11'); info.size=4
                tar.addfile(info,io.BytesIO(b'test'))
            with self.assertRaisesRegex(ValueError,'archive_hash'):
                m.extract(source,target,'0'*64)
            self.assertFalse(target.exists())
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            m.extract(source,target,digest)
            self.assertEqual((target/'python/bin/python3.11').read_bytes(),b'test')
            with self.assertRaises(FileExistsError):m.extract(source,target,digest)

    def test_PP002_traversal_device_alias_and_outbound_links_refused(self):
        m=module()
        for name,link in [('../escape',None),('/escape',None),('python/NUL',None),('python/x:stream',None),('python/x', '/tmp/escape'),('python/x','../../escape')]:
            with self.subTest(name=name,link=link),tempfile.TemporaryDirectory() as td:
                source=Path(td)/'bad.tar.gz'; target=Path(td)/'out'
                with tarfile.open(source,'w:gz') as tar:
                    info=tarfile.TarInfo(name)
                    if link:info.type=tarfile.SYMTYPE;info.linkname=link
                    else:info.size=1
                    tar.addfile(info,None if link else io.BytesIO(b'x'))
                with self.assertRaises((ValueError,tarfile.FilterError)):
                    m.extract(source,target,hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertFalse(target.exists())


    def test_PP003_failed_build_removes_only_owned_target(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'corrupt.tar.gz';source.write_bytes(b'not-python')
            existing=root/'existing';existing.mkdir();(existing/'keep').write_bytes(b'keep')
            with self.assertRaises(FileExistsError):m.build(source,existing)
            self.assertEqual((existing/'keep').read_bytes(),b'keep')
            target=root/'new'
            with self.assertRaisesRegex(ValueError,'archive_hash'):m.build(source,target)
            self.assertFalse(target.exists())

    def test_PP004_environment_does_not_inherit_proxy_or_credentials(self):
        from unittest.mock import patch
        m=module()
        with patch.dict('os.environ', {'GITHUB_TOKEN':'fixture-secret','HTTPS_PROXY':'http://fixture','PYTHONPATH':'/untrusted','__PYVENV_LAUNCHER__':'/untrusted'}, clear=False):
            result=m.clean_environment(Path('/temporary'))
        for key in ('GITHUB_TOKEN','HTTPS_PROXY','PYTHONPATH','__PYVENV_LAUNCHER__'):
            self.assertNotIn(key,result)


    def test_PP005_selected_wheel_hash_must_match_its_exact_lock_entry(self):
        m=module(); self.assertTrue(hasattr(m,'check_wheels'),'selected wheel provenance not integrated')
        import copy
        lock='one==1.0 \\n    --hash=sha256:'+'a'*64+'\n'
        report={'install':[{'metadata':{'name':'one','version':'1.0'},'download_info':{'url':'https://files.pythonhosted.org/one.whl','archive_info':{'hashes':{'sha256':'a'*64}}}}]}
        self.assertEqual(len(m.check_wheels(report,lock,{'one':'1.0'})),1)
        for field,value in [('version','2.0'),('hash','b'*64),('url','https://other.invalid/one.whl')]:
            changed=copy.deepcopy(report);item=changed['install'][0]
            if field=='version':item['metadata']['version']=value
            elif field=='hash':item['download_info']['archive_info']['hashes']['sha256']=value
            else:item['download_info']['url']=value
            with self.assertRaises(ValueError):m.check_wheels(changed,lock,{'one':'1.0'})
        with self.assertRaises(ValueError):m.check_wheels({'install':[]},lock,{'one':'1.0'})

if __name__=='__main__':unittest.main(verbosity=2)
