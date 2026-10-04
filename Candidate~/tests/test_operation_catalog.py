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
        implemented={row['name']:row['implemented_candidate_read_actions'] for row in inventory['tools']}
        self.assertEqual(implemented['read_console'], ['get'])
        self.assertEqual(implemented['manage_packages'], ['get_package_info'])
        self.assertEqual(implemented['manage_scene'], ['get_active','get_build_settings','get_loaded_scenes','get_hierarchy','validate'])
        self.assertEqual(implemented['find_gameobjects'], ['find'])
        self.assertEqual(implemented['manage_animation'], ['controller_get_info','animator_get_info','animator_get_parameter'])
        self.assertEqual({row['name'] for row in inventory.get('resource_facades',[])}, {'get_gameobject','get_gameobject_components','get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items'})
        find=next(row for row in inventory['tools'] if row['name']=='find_gameobjects')
        self.assertFalse(find['has_action_parameter'])
        self.assertEqual(find['declared_actions'],[])
        with tempfile.TemporaryDirectory(prefix='catalog-fixture-') as td:
            root=Path(td); (root/'catalog').mkdir()
            dest=root/'catalog/native-inventory.json'
            dest.write_text(json.dumps(inventory),encoding='utf-8')
            for row in inventory['tools'] + inventory['resource_facades']:
                relative=Path('native')/Path(row['source']['path']).relative_to('Server')
                (root/relative).parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/relative,root/relative)
            with patch.object(catalog,'ROOT',root):
                self.assertEqual(catalog.page()['total'],len(inventory['tools']))
                self.assertEqual(catalog.page()['resource_facades'], inventory['resource_facades'])
                resource=root/'native/src/services/resources/gameobject.py'
                original_resource=resource.read_bytes();resource.write_bytes(original_resource+b'\n# changed\n')
                with self.assertRaisesRegex(ValueError,'catalog_source_mismatch'):catalog.page()
                resource.write_bytes(original_resource)
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
