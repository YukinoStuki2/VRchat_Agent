"""Local Codex launch policy. No model, account login or existing config access."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'runtime')]
from owner_bootstrap import new_local_run

class CodexLocal(unittest.TestCase):
    def module(self):
        self.assertTrue((ROOT/'launcher/codex_local.py').is_file(),'local Codex entry missing')
        from launcher import codex_local
        return codex_local

    def test_CX001_isolated_config_contains_no_secrets_or_automatic_prompt(self):
        m=self.module()
        owner=new_local_run('fixture-local-codex',32198,clients=('codex',))
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);binary=home/('codex.exe' if os.name=='nt' else 'codex');binary.write_bytes(b'fixture-native-binary')
            project=home/'project';project.mkdir();profile=home/'profile';profile.mkdir()
            argv,env,config=m.configuration(owner,binary,project,profile)
            doc=tomllib.loads(config)
            self.assertEqual(argv[:4],[str(binary),'--no-daemon','--cd',str(project)])
            overrides={}
            for i in range(4,len(argv),2):
                self.assertEqual(argv[i],'-c');key,value=argv[i+1].split('=',1)
                overrides[key]=tomllib.loads('value='+value)['value']
            self.assertEqual(overrides.get('cli_auth_credentials_store'),'ephemeral','project config must not persist login')
            self.assertEqual(overrides.get('mcp_servers.candidate.url'),doc['mcp_servers']['candidate']['url'])
            self.assertEqual(overrides.get('shell_environment_policy.exclude'),[m.TOKEN_ENV])
            self.assertEqual(env['CODEX_HOME'],str(profile))
            self.assertEqual(env[m.TOKEN_ENV],owner.identity.credentials['codex'].token)
            self.assertNotIn(owner.identity.credentials['codex'].token,config+' '.join(argv))
            self.assertNotIn('PRIVATE KEY',config+' '.join(argv))
            self.assertEqual(doc['cli_auth_credentials_store'],'ephemeral')
            self.assertEqual(doc['history']['persistence'],'none')
            self.assertFalse(doc['features']['plugins'])
            self.assertIn(m.TOKEN_ENV,doc['shell_environment_policy']['exclude'])
            self.assertEqual(set(doc['mcp_servers']),{'candidate'})
            self.assertIn('manage_animation',doc['mcp_servers']['candidate']['enabled_tools'])
            self.assertIn('agent_catalog',doc['mcp_servers']['candidate']['enabled_tools'])
            self.assertIn('read_console',doc['mcp_servers']['candidate']['enabled_tools'])
            self.assertIn('manage_scene',doc['mcp_servers']['candidate']['enabled_tools'])
            self.assertIn('find_gameobjects',doc['mcp_servers']['candidate']['enabled_tools'])
            self.assertEqual(overrides['mcp_servers.candidate.enabled_tools'],doc['mcp_servers']['candidate']['enabled_tools'])
            inventory=json.loads((ROOT/'catalog/native-inventory.json').read_text(encoding='utf-8'))
            expected={row['name'] for row in inventory['tools'] if row.get('implemented_candidate_read_actions')}
            expected.update(row['name'] for row in inventory['resource_facades'])
            expected.update(('agent_status','agent_catalog','agent_prepare','agent_stop','material_prepare','material_execute','material_stop'))
            self.assertEqual(set(doc['mcp_servers']['candidate']['enabled_tools']),expected)
            self.assertEqual(len(doc['mcp_servers']['candidate']['enabled_tools']),len(expected))
            self.assertEqual(doc['mcp_servers']['candidate']['url'],'https://127.0.0.1:32198/mcp')
            self.assertEqual(doc['mcp_servers']['candidate']['bearer_token_env_var'],m.TOKEN_ENV)
            self.assertFalse((profile/'auth.json').exists())
            self.assertEqual(list(profile.iterdir()),[],'configuration builder must not write')

    def test_CX002_unselected_expired_or_script_launcher_refused(self):
        m=self.module()
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);exe=home/'codex.cmd';exe.write_text('@echo fixture')
            owner=new_local_run('fixture',32001,clients=('codex',))
            with self.assertRaisesRegex(ValueError,'native_executable'):
                m.configuration(owner,exe,home,home)
            exe=home/('codex.exe' if os.name=='nt' else 'codex');exe.write_bytes(b'fixture')
            closed=new_local_run('fixture',32001,clients=())
            with self.assertRaisesRegex(ValueError,'not_admitted'):m.configuration(closed,exe,home,home)
            with patch.object(m.time,'time',return_value=owner.identity.expires_at):
                with self.assertRaisesRegex(ValueError,'not_admitted'):m.configuration(owner,exe,home,home)

    def test_CX003_profile_is_private_and_removed_without_secret_files(self):
        m=self.module()
        self.assertTrue(hasattr(m,'profile'),'owned profile lifecycle missing')
        owner=new_local_run('fixture-profile',32002,clients=('codex',))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);exe=root/('codex.exe' if os.name=='nt' else 'codex');exe.write_bytes(b'fixture')
            with m.profile(owner,exe,root) as (argv,env):
                profile=Path(env['CODEX_HOME'])
                self.assertEqual((profile/'public-ca.pem').read_bytes(),owner.tls.certificate)
                self.assertEqual(set(p.name for p in profile.iterdir()),{'config.toml','public-ca.pem'})
                for p in profile.iterdir():
                    self.assertNotIn(owner.identity.credentials['codex'].token.encode(),p.read_bytes())
                    self.assertNotIn(b'PRIVATE KEY',p.read_bytes())
                if os.name!='nt':self.assertEqual(profile.stat().st_mode & 0o077,0)
            self.assertFalse(profile.exists())


class CodexLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_CX004_stop_closes_owned_console_before_profile_removal(self):
        from launcher import codex_local as m
        from unittest.mock import patch
        import asyncio,threading
        self.assertTrue(hasattr(m,'serve'),'local Codex lifecycle missing')
        run=new_local_run('fixture-console',32003,clients=('codex',))
        stop=threading.Event();started=threading.Event();events=[]
        class Child:
            def poll(self):return None
        class Owner:
            def alive(self):return True
            def spawn(self,argv,env,**options):
                self.home=Path(env['CODEX_HOME'])
                self_test.assertTrue(self.home.exists())
                self_test.assertEqual(options,{'new_console':True})
                events.append('spawn');return Child()
            def close(self):
                self_test.assertTrue(self.home.exists(),'profile removed before owned children exit')
                events.append('close');return True
        self_test=self;owner=Owner()
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'codex.exe';exe.write_bytes(b'fixture')
            with patch.object(m,'_owner',return_value=owner), patch.object(m,'verify_native') as verify:
                task=asyncio.create_task(m.serve(run,exe,Path(td),stop=stop,started=started))
                async with asyncio.timeout(3):
                    while not started.is_set():await asyncio.sleep(.01)
                    stop.set();result=await task
        verify.assert_awaited_once()
        self.assertEqual(verify.await_args.args[:2],(owner,exe))
        self.assertEqual(events,['spawn','close']);self.assertFalse(owner.home.exists())
        self.assertEqual(result,{'code':'STOPPED','process_cleanup_complete':True,'profile_cleanup_complete':True})

    async def test_CX005_failed_spawn_and_cancel_close_owned_profile(self):
        from launcher import codex_local as m
        from unittest.mock import patch
        import asyncio,threading
        class Owner:
            closed=False
            def alive(self):return True
            def spawn(self,argv,env,**kw):
                self.home=Path(env['CODEX_HOME'])
                if failing:raise OSError('fixture-start-failure')
                return type('Child',(),{'poll':lambda _:None})()
            def close(self):self.closed=True;return True
        run=new_local_run('fixture-failure',32004,clients=('codex',))
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'codex.exe';exe.write_bytes(b'fixture')
            for failing in (True,False):
                owner=Owner();started=threading.Event()
                with patch.object(m,'_owner',return_value=owner), patch.object(m,'verify_native') as verify:
                    task=asyncio.create_task(m.serve(run,exe,Path(td),stop=threading.Event(),started=started))
                    if failing:
                        with self.assertRaises(OSError):await task
                    else:
                        async with asyncio.timeout(2):
                            while not started.is_set():await asyncio.sleep(.01)
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):await task
                self.assertTrue(owner.closed);self.assertFalse(owner.home.exists())

    async def test_CX006_native_version_is_checked_without_candidate_credentials(self):
        from launcher import codex_local as m
        import asyncio,threading
        self.assertTrue(hasattr(m,'verify_native'),'bounded native version preflight missing')
        class Child:
            def poll(self):return 0
        class Owner:
            def spawn(self,argv,env,**kw):
                self_test.assertEqual(argv,[sys.executable,'--version'])
                self_test.assertNotIn(m.TOKEN_ENV,env)
                os.write(kw['stdio'][1],reply)
                return Child()
        self_test=self
        for reply in (b'codex-cli 0.159.2\n',b'codex-cli 0.1.0\n',b'unknown\n'):
            if reply==b'codex-cli 0.159.2\n':await m.verify_native(Owner(),sys.executable,{m.TOKEN_ENV:'must-not-inherit'})
            else:
                with self.assertRaisesRegex(ValueError,'codex_version_unsupported'):
                    await m.verify_native(Owner(),sys.executable,{m.TOKEN_ENV:'must-not-inherit'})

    async def test_CX007_script_path_is_rejected_before_version_execution(self):
        from launcher import codex_local as m
        from unittest.mock import patch
        import threading
        owner=type('Owner',(),{'closed':False,'close':lambda self:setattr(self,'closed',True)})()
        run=new_local_run('fixture-invalid-exe',32005,clients=('codex',))
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'fake.cmd';exe.write_bytes(b'fixture')
            with patch.object(m,'_owner',return_value=owner), patch.object(m,'verify_native') as verify:
                with self.assertRaisesRegex(ValueError,'native_executable'):
                    await m.serve(run,exe,Path(td),stop=threading.Event(),started=threading.Event())
                verify.assert_not_awaited()
        self.assertTrue(owner.closed)

if __name__=='__main__':unittest.main(verbosity=2)
