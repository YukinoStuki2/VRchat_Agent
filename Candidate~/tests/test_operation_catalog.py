"""Installed package catalog, not Unity execution or permission approval."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
import operation_catalog as catalog

class CatalogDeliveryTests(unittest.TestCase):
    def test_OC001_changed_sources_or_permission_claims_fail_closed(self):
        inventory=json.loads((ROOT/'catalog/native-inventory.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory(prefix='catalog-fixture-') as td:
            root=Path(td); (root/'catalog').mkdir()
            dest=root/'catalog/native-inventory.json'
            dest.write_text(json.dumps(inventory),encoding='utf-8')
            for row in inventory['tools']:
                relative=Path('native')/Path(row['source']['path']).relative_to('Server')
                (root/relative).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,root/relative)
            with patch.object(catalog,'ROOT',root):
                self.assertEqual(catalog.page()['total'],len(inventory['tools']))
                source=root/'native/src/services/tools/manage_material.py'
                original=source.read_bytes();source.write_bytes(original+b'\n# changed\n')
                with self.assertRaisesRegex(ValueError,'catalog_source_mismatch'):catalog.page()
                source.write_bytes(original)
                for field,value in (('permission_grant',True),('count',1),('product_ready',True)):
                    broken=copy.deepcopy(inventory);broken[field]=value
                    dest.write_text(json.dumps(broken),encoding='utf-8')
                    with self.assertRaisesRegex(ValueError,'catalog_invalid'):catalog.page()
                broken=copy.deepcopy(inventory);broken['tools'][0]['enabled_by_catalog']=True
                dest.write_text(json.dumps(broken),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'catalog_invalid'):catalog.page()

if __name__=='__main__':unittest.main()
