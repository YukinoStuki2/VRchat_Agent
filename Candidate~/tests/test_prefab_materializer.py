"""Offline deterministic source and provenance; no Unity or installed package edits."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from distribution.materialize_prefabs import materialize, READERS, HELPERS, PINS
NATIVE=Path('/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity')

class PrefabMaterializerTests(unittest.TestCase):
    def test_PM001_provenance_hashes_original_method_bytes(self):
        with tempfile.TemporaryDirectory(prefix='prefab-provenance-') as td:
            proof=materialize(NATIVE,Path(td)/'reader')
            for name,path in [(n,'Editor/Tools/Prefabs/ManagePrefabs.cs') for n in READERS]+[(n,'Editor/Helpers/PrefabUtilityHelper.cs') for n in HELPERS]:
                text=(NATIVE/path).read_text(encoding='utf-8')
                parts=re.findall(r'^        (?:private|public) static [^\n]+\b'+re.escape(name)+r'\([^\n]*\)\n        \{\n.*?^        \}',text,re.M|re.S)
                self.assertEqual(len(parts),1)
                self.assertEqual(proof['method_hashes_before_adaptation'][name],hashlib.sha256(parts[0].encode()).hexdigest(),name)

    def test_PM002_reproducible_shipped_source_and_existing_destination_refused(self):
        with tempfile.TemporaryDirectory(prefix='prefab-provenance-') as td:
            output=Path(td)/'reader';materialize(NATIVE,output)
            def data(root):return {p.name:p.read_bytes() for p in root.iterdir()}
            expected=data(ROOT/'package/Editor/ScopedPrefabs')
            self.assertEqual(data(output),expected)
            with self.assertRaises(FileExistsError):materialize(NATIVE,output)
            self.assertEqual(data(output),expected)

    def test_PM003_native_pin_drift_fails_before_output(self):
        with tempfile.TemporaryDirectory(prefix='prefab-provenance-') as td:
            upstream=Path(td)/'upstream';out=Path(td)/'reader'
            for name in PINS:
                dest=upstream/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(NATIVE/name,dest)
            source=upstream/next(iter(PINS));source.write_bytes(source.read_bytes()+b'\n// drift\n')
            with self.assertRaisesRegex(ValueError,'native_prefab_source_drift'):materialize(upstream,out)
            self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
