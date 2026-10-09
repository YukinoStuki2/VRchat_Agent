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
        self.assertEqual(implemented['unity_reflect'], ['get_type','get_member','search'])
        reflection=next(row for row in inventory['tools'] if row['name']=='unity_reflect')
        self.assertIn('程序集解析', reflection['audit_note_zh'])
        self.assertIn('受限核心类型', reflection['audit_note_zh'])
        self.assertEqual(implemented['manage_script'], ['read'])
        self.assertEqual(implemented['get_sha'], ['get_sha'])
        self.assertEqual(implemented['manage_shader'], ['read'])
        self.assertEqual(implemented['manage_scene'], ['get_active','get_build_settings','get_loaded_scenes','get_hierarchy','validate'])
        self.assertEqual(implemented['find_gameobjects'], ['find'])
        self.assertEqual(implemented['manage_animation'], ['controller_get_info','clip_get_info','animator_get_info','animator_get_parameter'])
        self.assertEqual({row['name'] for row in inventory.get('resource_facades',[])}, {'get_gameobject','get_gameobject_components','get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items','get_tests'})
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
            import importlib.util
            spec=importlib.util.spec_from_file_location('candidate_catalog_builder', ROOT/'catalog/catalog.py')
            builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
            source_view=root/'upstream';shutil.copytree(root/'native',source_view/'Server')
            self.assertEqual(builder.build_candidate_inventory(source_view), inventory)
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

    def test_OC002_job_effect_is_explicit_not_pure_read_or_grant(self):
        inventory=json.loads((ROOT/'catalog/native-inventory.json').read_text(encoding='utf-8'))
        job=next(row for row in inventory['tools'] if row['name']=='get_test_job')
        self.assertEqual(job['implemented_candidate_read_actions'], [])
        self.assertEqual(job.get('implemented_candidate_effect_actions'), ['observe'])
        self.assertEqual(job.get('required_effect'), {'kind':'project_test_job_maintenance','version':1})
        self.assertIn('工程', job['audit_note_zh'])
        self.assertFalse(job['enabled_by_catalog'])
        rows=[]
        for offset in range(0, len(inventory['tools']), 20): rows.extend(catalog.page(offset,20)['tools'])
        delivered=next(row for row in rows if row['name']=='get_test_job')
        self.assertEqual(delivered,{k:v for k,v in job.items() if k != 'parameters'})

    def test_OC003_live_effect_catalog_is_not_pure_read_or_permission(self):
        doc=json.loads((ROOT/'catalog/native-inventory.json').read_text())
        rows={r['name']:r for r in doc['tools']+doc['resource_facades']}
        for name,actions in [('manage_asset',['search','get_info']),('manage_prefabs',['get_info','get_hierarchy']),('get_tests',['discover'])]:
            self.assertIn(name,rows)
            self.assertEqual(rows[name].get('implemented_candidate_effect_actions'),actions)
            self.assertEqual(rows[name]['implemented_candidate_read_actions'],[])
            self.assertIn('不是插件沙箱',rows[name]['audit_note_zh'])
            self.assertFalse(rows[name]['enabled_by_catalog'])
        self.assertIn('get_tests',{r['name'] for r in catalog.page()['resource_facades']})

if __name__=='__main__':unittest.main()
