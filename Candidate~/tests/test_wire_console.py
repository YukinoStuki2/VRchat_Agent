"""Actual C# fixture startup under a non-UTF8 console; not Unity acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

class WireConsoleTests(unittest.TestCase):
    def test_WE001_actual_wire_initializes_lossless_utf8_console(self):
        spec=importlib.util.spec_from_file_location('wire_console_driver',ROOT/'tests/verify_editor_wire.py')
        assert spec is not None and spec.loader is not None
        driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
        dotnet=shutil.which('dotnet') or '/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet'
        original=ROOT/'tests/unity-core/WirePeer.csproj'
        source=ROOT/'tests/unity-core/WirePeer.cs';before=hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='wire-encoding-') as td:
            work=Path(td);tree=ET.parse(original)
            for node in tree.iter('Compile'):
                value=node.attrib['Include']
                if '$(' not in value:node.set('Include',str(original.parent/value))
            item=ET.SubElement(tree.getroot(),'ItemGroup')
            ET.SubElement(item,'Compile',{'Include':str(work/'EncodingProbe.cs')})
            (work/'EncodingProbe.cs').write_text('''using System;
using System.Text;
using System.Reflection;
internal static class EncodingProbe {
 public static int Main() {
  Console.InputEncoding=Encoding.ASCII;
  Console.OutputEncoding=Encoding.ASCII;
  typeof(WirePeer).GetMethod("Main",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,null);
  Console.Write("中文");Console.Out.Flush();
  return Console.InputEncoding.CodePage==65001 && Console.OutputEncoding.CodePage==65001 ? 0 : 19;
 }
}
''',encoding='utf-8')
            project=work/'Probe.csproj';tree.write(project,encoding='utf-8')
            response=driver.response_source(work);native=driver.native_source(work)
            args=[dotnet,'build',str(project),'-c','Release','--disable-build-servers','-p:UseSharedCompilation=false',
                '-p:StartupObject=EncodingProbe','-p:CandidateResponseSource='+str(response),
                '-p:CandidateNativeRoot='+str(native),'-p:BaseIntermediateOutputPath='+str(work/'obj')+'/',
                '-p:BaseOutputPath='+str(work/'bin')+'/','-p:RestoreConfigFile='+str(ROOT/'tests/unity-core/ReviewNuGet.Config'),
                '-p:NuGetAudit=false','-p:RestoreSources=']
            build=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',timeout=45)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            self.assertNotIn('warning CS',build.stdout+build.stderr)
            run=subprocess.run([dotnet,str(work/'bin/Release/net8.0/Probe.dll')],input=b'',capture_output=True,timeout=10)
            self.assertEqual(run.returncode,0,'actual WirePeer Main did not override lossy console encoding: '+repr(run.stdout+run.stderr))
            self.assertEqual(run.stdout,'中文'.encode('utf-8'))
            self.assertEqual(run.stderr,b'')
        self.assertFalse(work.exists())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

if __name__=='__main__':unittest.main(verbosity=2)
