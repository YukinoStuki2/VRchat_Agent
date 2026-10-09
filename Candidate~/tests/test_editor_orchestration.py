"""Shipped Editor coordinator over OS peer; Unity/owner authority are fixtures."""
import asyncio, shutil, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_editor_control import ROOT, detach_fixture_code
from test_editor_owner import environment
import sys
WIRE_DLL=None
DOTNET=None
class EditorOrchestrationTests(unittest.IsolatedAsyncioTestCase):
 async def run_fixture(self,mode="normal",expected="EC001"):
  with tempfile.TemporaryDirectory(prefix='editor-orchestration-fixture-') as td:
   package=Path(td);launcher=package/'Runtime~'/'launcher';launcher.mkdir(parents=True)
   (launcher/'editor_owner.py').write_text('ROOT='+repr(str(ROOT))+'\n'+detach_fixture_code('project-A'),encoding='utf-8')
   shutil.copyfile(ROOT/'launcher/direct_python.py',launcher/'direct_python.py')
   process=await asyncio.create_subprocess_exec(DOTNET,WIRE_DLL,sys.executable,str(package),mode,env=environment(),cwd=package,stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
   try:
    out,err=await asyncio.wait_for(process.communicate(),40)
    self.assertEqual(process.returncode,0,(out+err).decode('utf-8',errors='replace'))
    self.assertEqual([line.split()[1] for line in out.decode().splitlines() if line.startswith('PASS ')],[expected])
    self.assertNotIn(b'ResourceWarning',out+err)
   finally:
    if process.returncode is None:process.kill();await process.communicate();self.fail('orchestration fixture forced cleanup')
 async def test_EC001_local_compile_and_reload_continuity(self):
  await self.run_fixture()
 async def test_EC002_revoke_all_cancels_detached_owner(self):
  await self.run_fixture('revoke-all','EC002')
 async def test_EC003_window_cancel_after_reload_stops_original_owner(self):
  await self.run_fixture('cold-cancel','EC003')
 async def test_EC004_live_read_scopes_revalidate_across_binding(self):
  await self.run_fixture('live-reads','EC004')
 async def test_EC005_capability_revocation_cancels_reload(self):
  await self.run_fixture('capability','EC005')
 async def test_EC006_other_lifecycle_cancellations_do_not_restore(self):
  for mode in ('stop','play','window-close','unplanned','deadline'):
   with self.subTest(mode=mode):await self.run_fixture(mode,'EC006')
 async def test_EC007_changed_candidate_fails_closed_without_rollback(self):
  await self.run_fixture('evidence-change','EC007')
