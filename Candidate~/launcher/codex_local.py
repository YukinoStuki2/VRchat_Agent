"""Explicit local native Codex invocation. No existing client config is modified.

Bearer stays in the new process environment, never argv or disk. The public
leaf certificate is additional native Codex trust, not exclusive TLS pinning.
MCP gates do not sandbox the client's own terminal. No model prompt is supplied.
"""
from contextlib import contextmanager
import tempfile
from uuid import uuid4
import json
import os
from pathlib import Path
import time
import tomllib

from .candidate_launch import child_environment

TOKEN_ENV = 'VRCHAT_AGENT_CODEX_TOKEN'
TOOLS = ('agent_status','agent_catalog','agent_prepare','agent_stop','manage_material','manage_animation','read_console','manage_scene','find_gameobjects','get_gameobject','get_gameobject_components','get_project_info','get_tags','get_layers','get_selection','get_windows','get_active_tool','get_prefab_stage','get_menu_items','manage_packages','manage_script','get_sha','manage_shader','unity_reflect','get_test_job','manage_asset','manage_prefabs','get_tests',
         'material_prepare','material_execute','material_stop')


@contextmanager
def profile(local_run, executable, project):
    outer=None
    if os.name=='nt':
        from diagnostics.windows_handles import create_private_directory
        outer=Path(tempfile.gettempdir())/('vrchat-codex-'+uuid4().hex)
        create_private_directory(outer)
    try:
        with tempfile.TemporaryDirectory(prefix='vrchat-codex-',dir=outer) as folder:
            home=Path(folder)
            argv,env,config=configuration(local_run,executable,project,home)
            (home/'config.toml').write_text(config,encoding='utf-8')
            (home/'public-ca.pem').write_bytes(local_run.tls.certificate)
            yield argv,env
    finally:
        if outer is not None:outer.rmdir()


def configuration(local_run, executable, project, home):
    if ('codex' not in local_run.identity.clients or
            time.time() >= local_run.identity.expires_at):
        raise ValueError('codex_not_admitted')
    executable,project,home=map(Path,(executable,project,home))
    if executable.suffix.lower() in ('.cmd','.bat','.ps1','.py','.sh') or (os.name=='nt' and executable.suffix.lower()!='.exe'):
        raise ValueError('codex_native_executable_required')
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError('codex_executable_required')
    if not project.is_absolute() or not project.is_dir() or not home.is_absolute() or not home.is_dir():
        raise ValueError('codex_local_paths_required')
    q=json.dumps
    config='\n'.join((
        'cli_auth_credentials_store = "ephemeral"',
        'check_for_update_on_startup = false',
        '[history]', 'persistence = "none"',
        '[features]', 'plugins = false',
        '[analytics]', 'enabled = false',
        '[feedback]', 'enabled = false',
        '[shell_environment_policy]', 'exclude = '+q([TOKEN_ENV]),
        '[mcp_servers.candidate]',
        'url = '+q(f'https://127.0.0.1:{local_run.port}/mcp'),
        'bearer_token_env_var = '+q(TOKEN_ENV),
        'startup_timeout_sec = 8', 'tool_timeout_sec = 8', 'required = true',
        'enabled_tools = '+q(TOOLS), ''))
    env={**child_environment(),'CODEX_HOME':str(home),
         'CODEX_CA_CERTIFICATE':str(home/'public-ca.pem'),
         TOKEN_ENV:local_run.identity.credentials['codex'].token}
    argv=[str(executable),'--no-daemon','--cd',str(project)]
    def override(table,prefix=''):
        for key,value in table.items():
            name=prefix+key
            if isinstance(value,dict):override(value,name+'.')
            else:argv.extend(('-c',name+'='+q(value)))
    override(tomllib.loads(config))
    return argv,env,config


def _owner():
    if os.name != 'nt':raise RuntimeError('codex_visible_console_requires_windows')
    from .candidate_launch import make_owner
    return make_owner(os.getpid())


async def verify_native(owner, executable, environment):
    import asyncio
    import threading
    from .editor_owner import read_control
    readin,writein=os.pipe();readout,writeout=os.pipe()
    safe_env={k:v for k,v in environment.items() if k!=TOKEN_ENV}
    try:
        child=owner.spawn([str(executable),'--version'],safe_env,stdio=(readin,writeout))
        os.close(readin);readin=None;os.close(writeout);writeout=None
        os.close(writein);writein=None
        reply=await read_control(threading.Event(),4,fd=readout,limit=80)
        if reply.rstrip(b'\r\n')!=b'codex-cli 0.159.2':raise ValueError('codex_version_unsupported')
        async with asyncio.timeout(2):
            while child.poll() is None:await asyncio.sleep(.02)
        if child.poll()!=0:raise ValueError('codex_version_unsupported')
    finally:
        for fd in (readin,writein,readout,writeout):
            if fd is not None:os.close(fd)


async def serve(local_run, executable, project, *, stop, started):
    import asyncio
    owner=_owner();clean=False;code='CODEX_LAUNCH_FAILED'
    try:
        with profile(local_run,executable,project) as (argv,env):
            try:
                await verify_native(owner,executable,env)
                child=owner.spawn(argv,env,new_console=True)
                started.set()
                while child.poll() is None:
                    if stop.is_set():code='STOPPED';break
                    if not owner.alive():code='CODEX_OWNER_LOST';break
                    if time.time()>=local_run.identity.expires_at:code='CODEX_EXPIRED';break
                    await asyncio.sleep(.02)
                else:
                    code='CODEX_CLOSED' if child.poll()==0 else 'CODEX_EXIT_FAILED'
            finally:
                clean=owner.close()
    finally:
        if not getattr(owner,'closed',True):owner.close()
    return {'code':code,'process_cleanup_complete':clean,'profile_cleanup_complete':True}
