"""Real bundled Node/filesystem relocation and MCP test, not Unity/production approval.
No account credentials, real project, model request, listening port or user config.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def verify_payload(moved, work, report):
    # Canonicalize only this driver-owned build output (CI TEMP may be 8.3).
    moved=moved.resolve(strict=True)
    processes=[]
    sys.path.insert(0,str(moved/'diagnostics'))
    import server,snapshot
    assert server.ENTRY.is_relative_to(moved)
    node=server.bundled_node()
    assert node.is_relative_to(moved) and node.is_file()
    async def exercise():
        from fastmcp import Client
        import mcp.client.stdio as stdio
        create=stdio._create_platform_compatible_process
        async def record(*args,**kwargs):
            command=kwargs.get('command',args[0] if args else None)
            assert command==str(node),'host_node_fallback'
            process=await create(*args,**kwargs);processes.append(process);return process
        source=work/'source';source.mkdir();(source/'Editor.log').write_text('fixture diagnostic marker',encoding='utf-8')
        (source/'private.txt').write_text('unselected fixture',encoding='utf-8')
        with patch.object(stdio,'_create_platform_compatible_process',side_effect=record):
            with snapshot.capture(str(source),['Editor.log'],task_id='portable-diagnostic',temp_parent=str(work)) as snap:
                factory=server.create_server(snap)
                async with Client(factory,roots=[source.as_uri()]) as client:
                    names={t.name for t in await client.list_tools()}
                    assert names=={'read_text_file','list_directory','get_file_info','agent_diagnostics_status'}
                    before_hidden=len(processes)
                    assert await client.list_resources()==[] and await client.list_prompts()==[]
                    assert await client.list_resource_templates()==[]
                    assert len(processes)==before_hidden,'hidden_catalog_forwarded_to_backend'
                    read=await client.call_tool('read_text_file',{'path':str(snap.root/'Editor.log')})
                    assert not read.is_error and 'fixture diagnostic marker' in str(read.content)
                    for name,arguments in [('write_file',{'path':str(snap.root/'new.txt'),'content':'x'}),
                        ('read_text_file',{'path':str(source/'private.txt')})]:
                        value=await client.call_tool(name,arguments,raise_on_error=False);assert value.is_error
                    before_denied=len(processes)
                    async with Client(factory) as foreign:
                        for query in (foreign.list_resources, foreign.list_resource_templates, foreign.list_prompts):
                            try: await query()
                            except Exception as exc: assert 'snapshot_bound_to_other_session' in str(exc)
                            else: raise AssertionError('foreign_hidden_catalog_inherited_lease')
                    snap._active.clear()
                    value=await client.call_tool('agent_diagnostics_status',{},raise_on_error=False);assert value.is_error
                    for query in (client.list_resources, client.list_resource_templates, client.list_prompts):
                        try: await query()
                        except Exception as exc: assert 'local_snapshot_expired_or_closed' in str(exc)
                        else: raise AssertionError('closed_hidden_catalog_bypassed_lease')
                    assert len(processes)==before_denied,'denied_catalog_spawned_backend'
                    report['hidden_catalog_local_only_and_bound']=True
            assert not snap.root.parent.exists()
        report['children']=[{'pid':p.pid,'returncode':p.returncode} for p in processes]
        report['child_pids']=[p.pid for p in processes]
        report['all_children_exit_zero']=bool(processes) and all(p.returncode==0 for p in processes)
        print(json.dumps({'diagnostic_child_exits':report['children']}),flush=True)
        assert report['all_children_exit_zero']
        if sys.platform!='win32':
            assert all(not Path(f'/proc/{p.pid}').exists() for p in processes)
            report['all_child_pids_absent']=True
    asyncio.run(exercise())
    report['native_read_write_denial_revoke_passed']=True
    target=server.ENTRY;original=target.read_bytes();target.write_bytes(original+b'\n// changed fixture\n')
    try:
        server.bundled_node();raise AssertionError('modified_bundle_accepted')
    except ValueError as exc:
        assert str(exc)=='bundled_diagnostic_backend_invalid'
    finally:target.write_bytes(original)
    report['tamper_rejected']=True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('node_archive');parser.add_argument('output')
    args=parser.parse_args();output=Path(args.output)
    if output.exists():raise FileExistsError(output)
    report={'passed':False,'scope':'real bundled Node and filesystem MCP; fixture source; not real Editor or human approval',
        'process_cleanup_scope':'graceful SDK child exit; no crash/power-loss claim'}
    tracked=[*(ROOT/'diagnostics').glob('*.py'),*(ROOT/'dependencies/filesystem-0.6.3').rglob('*'),
        ROOT/'distribution/diagnostic_backend.py',ROOT/'distribution/diagnostics-backend.lock.json',Path(__file__)]
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked if p.is_file()}
    processes=[]
    try:
        with tempfile.TemporaryDirectory(prefix='candidate-diag-portable-') as temporary:
            work=Path(temporary).resolve();report['temporary_root']=str(work)
            first=work/'candidate';first.mkdir()
            spec=importlib.util.spec_from_file_location('diagnostic_builder',ROOT/'distribution/diagnostic_backend.py')
            assert spec is not None and spec.loader is not None
            builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
            build=builder.build(args.node_archive,first/'diagnostics-backend')
            assert not build['missing_notice_packages']
            report['build']={k:build[k] for k in ('platform','node_version','npm_package_count','node_archive_sha256','upstream_commit')}
            shutil.copytree(ROOT/'diagnostics',first/'diagnostics',ignore=shutil.ignore_patterns('__pycache__'))
            (first/'distribution').mkdir()
            shutil.copyfile(ROOT/'distribution/diagnostics-backend.lock.json',first/'distribution/diagnostics-backend.lock.json')
            moved=work/'relocated';first.rename(moved);assert not first.exists()
            report['bundled_file_count']=len(build['files'])
            verify_payload(moved,work,report)
            report['passed']=True
    except BaseException as exc:
        report['error_type']=type(exc).__name__
        import traceback
        report['error_frames']=[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-8:]]
    finally:
        report['temporary_root_absent']='temporary' in locals() and not Path(temporary).exists()
        report['source_unchanged']=before=={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked if p.is_file()}
        report['source_hashes']=before
        report['passed']=bool(report['passed'] and report['temporary_root_absent'] and report['source_unchanged'])
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_hashes'}))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
