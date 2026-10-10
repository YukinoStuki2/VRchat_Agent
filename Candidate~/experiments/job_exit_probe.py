"""Bounded investigation, not acceptance or a fix. Original verdict is immutable."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


def observer(check,snapshot,rows,*,sleep=time.sleep):
    def observe(owner,child):
        result=check(owner,child)  # Original check always happens first.
        row={'pid':child.pid,'original_natural_tree_exit':result,'snapshots':[]}
        rows.append(row)
        if not result:
            start=time.monotonic()
            for attempt in range(11):
                if attempt:sleep(.02)
                state=snapshot(owner)
                row['snapshots'].append({'elapsed':time.monotonic()-start,'state':state})
                if state.get('accounting',{}).get('ActiveProcesses')==0:break
        return result  # Later empty accounting NEVER replaces the initial failure.
    return observe


def snapshot_images(owner,snapshot):
    import ctypes as c
    import ntpath
    state=snapshot(owner)
    for row in state.get('members',[]):
        if not row.get('member_verified'):continue
        handle=None
        try:
            handle=owner.api.w.OpenProcess(0x101000,False,row['pid'])
            owner.api.assign(owner.job,handle)
            query=owner.api.k.QueryFullProcessImageNameW
            query.argtypes=[c.c_void_p,c.c_uint32,c.c_wchar_p,c.POINTER(c.c_uint32)]
            query.restype=c.c_int
            size=c.c_uint32(32768);buffer=c.create_unicode_buffer(size.value)
            owner.api.checked(query(handle,0,buffer,c.byref(size)))
            row['image_basename']=ntpath.basename(buffer.value)
        except Exception as error:
            row['image_error_type']=type(error).__name__
        finally:
            if handle is not None:owner.api.close_handle(handle)
    return state


def birth_observer(make_owner,snapshot,rows,*,settle=0,sleep=time.sleep):
    def create(parent_pid):
        owner=make_owner(parent_pid);original=owner.spawn
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs)
            if settle:sleep(settle)
            rows.append({'pid':child.pid,'state':snapshot(owner)})
            return child
        owner.spawn=spawn
        return owner
    return create


def probe_plan(mode):
    if mode=='baseline':return 64,20,.02
    if mode=='signal-race':return 512,0,0
    raise ValueError('unknown_probe_mode')


def main():
    if os.name!='nt' or len(sys.argv) not in (2,3):
        raise SystemExit('Windows, new output directory and optional fixed mode required')
    mode=sys.argv[2] if len(sys.argv)==3 else 'baseline'
    simple_limit,build_limit,poll_sleep=probe_plan(mode)
    out=Path(sys.argv[1]);out.mkdir(exist_ok=False)
    sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
    import verify_peer
    import verify_editor_wire
    from launcher.direct_python import current
    import launcher.candidate_launch as launches
    files=subprocess.check_output(['git','ls-files','-z','Candidate~','.github/workflows'],cwd=ROOT.parent).decode().split('\0')
    def hashes():return {name:hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest() for name in files if name}
    report={'scope':'bounded original Windows Job verdict investigation, not product acceptance',
        'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent,text=True).strip(),
        'platform':sys.platform,'mode':mode,'simple_limit':simple_limit,'build_limit':build_limit,'poll_sleep':poll_sleep,'source_before':hashes(),'controls':[],'simple':[],'builds':[],'observations':[],'birth_observations':[],
        'historical_root_cause_proven':False}
    def save():
        (out/'probe.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    check=verify_peer.natural_tree_exit
    snapshot=lambda owner:snapshot_images(owner,verify_peer.failed_job_snapshot)
    try:
        # Stress changes only this test driver's poll interval, not owner cleanup,
        # deadlines, native predicates or any production module's time object.
        with patch.object(verify_peer,'time',SimpleNamespace(monotonic=time.monotonic,sleep=lambda _:time.sleep(poll_sleep))), \
                patch.object(verify_peer,'natural_tree_exit',observer(check,snapshot,report['observations'])), \
                patch.object(launches,'make_owner',birth_observer(launches.make_owner,snapshot,report['birth_observations'],settle=.02)):
            # One live descendant lasts beyond the existing 40s parent deadline.
            # Avoid a short sleep-based control that can itself race the observer.
            for label,seconds in [('live-descendant',60)]:
                code='import os,subprocess;child=subprocess.Popen('+repr([current()['executable'],'-I','-B','-c',f'import time;time.sleep({seconds})'])+');os._exit(0)'
                row=verify_peer.run_case(Path(__file__),code)
                report['controls'].append({'label':label,'row':row});save()
                assert row['exit_code']==0 and not row['natural_tree_exit'] and row['cleanup_complete'] and row['temporary_home_absent']
                assert not row['timed_out'] and 'ResourceWarning' not in row['stdout']+row['stderr']
            for number in range(simple_limit):
                row=verify_peer.run_case(Path(__file__),'import time;time.sleep(.1);raise SystemExit(0)')
                report['simple'].append(row);save()
                assert row['exit_code']==0 and row['cleanup_complete'] and row['temporary_home_absent'] and not row['timed_out']
                if not row['natural_tree_exit']:break
            for number in range(build_limit):
                label=f'job-probe-{number:02}'
                with patch.object(sys,'argv',['verify_editor_wire.py',label,'rw','RW001']):
                    result=verify_editor_wire.main()
                payload=(ROOT/'evidence'/('editor-wire-'+label+'.json')).read_bytes()
                (out/f'build-{number:02}.json').write_bytes(payload)
                doc=json.loads(payload)
                report['builds'].append({'number':number,'returncode':result,'passed':doc['passed'],'build':doc.get('build'),
                    'build_root_absent':doc.get('build_root_absent'),'source_unchanged':doc['source_unchanged']});save()
                if result!=0:break
    except Exception as error:
        report['error_type']=type(error).__name__
    finally:
        report['source_after']=hashes()
        report['source_unchanged']=report['source_before']==report['source_after']
        report['collection_complete']='error_type' not in report and len(report['controls'])==1 and bool(report['simple']) and (not build_limit or bool(report['builds'])) and report['source_unchanged']
        report['unexpected_failure']=any(not row['natural_tree_exit'] for row in report['simple']) or any(not row['passed'] for row in report['builds'])
        save()
    print(json.dumps({k:report[k] for k in ('collection_complete','unexpected_failure','historical_root_cause_proven')}))
    return 0 if report['collection_complete'] and not report['unexpected_failure'] else 1


if __name__=='__main__':raise SystemExit(main())
