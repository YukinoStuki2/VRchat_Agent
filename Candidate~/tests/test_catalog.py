"""Offline checks against the pinned, real native source tree; no Unity simulation."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0')


class CatalogTests(unittest.TestCase):
    def test_catalog_classification_never_grants_permission_from_tool_names(self):
        spec = importlib.util.spec_from_file_location('candidate_catalog', ROOT / 'catalog/catalog.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, 'build_candidate_inventory'), 'Chinese deny-default inventory missing')
        result = module.build_candidate_inventory(UPSTREAM)
        self.assertFalse(result['product_ready'])
        self.assertFalse(result['permission_grant'])
        self.assertEqual(len(result['tools']), 48)
        for row in result['tools']:
            self.assertTrue(row['name_zh'])
            self.assertEqual(row['default_decision'], 'deny')
            self.assertFalse(row['enabled_by_catalog'])
        surface = {(row['name'], action) for row in result['tools']
                   for action in row['implemented_candidate_read_actions']}
        self.assertEqual(surface, {('manage_material', 'get_material_info'),
                                   ('manage_animation', 'controller_get_info')})
        # Read-looking names remain denied; unknown tools must not inherit a label grant.
        fake = {'name': 'read_fake_safely', 'declared_actions': ['read'], 'source': {}}
        from unittest.mock import patch
        with patch.object(module, 'discover_python_tools', return_value=[fake]):
            unknown = module.build_candidate_inventory(UPSTREAM)['tools'][0]
        self.assertEqual(unknown['default_decision'], 'deny')
        self.assertEqual(unknown['implemented_candidate_read_actions'], [])
        self.assertEqual(unknown['name_zh'], '未分类原生能力')

    def test_registered_inventory_is_complete_sorted_and_exact(self):
        module_path = ROOT / 'catalog' / 'catalog.py'
        self.assertTrue(module_path.is_file(), 'catalog parser is not implemented')
        spec = importlib.util.spec_from_file_location('candidate_catalog', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = module.discover_python_tools(UPSTREAM)
        names = [r['name'] for r in rows]
        self.assertEqual(48, len(names))
        self.assertEqual(sorted(set(names)), names)
        self.assertTrue({'apply_text_edits', 'get_sha', 'get_test_job', 'manage_tools'} <= set(names))
        self.assertEqual('manage_script', next(r for r in rows if r['name'] == 'get_sha')['unity_target'])
        self.assertEqual(['get', 'clear'], next(r for r in rows if r['name'] == 'read_console')['declared_actions'])


if __name__ == '__main__':
    unittest.main()
