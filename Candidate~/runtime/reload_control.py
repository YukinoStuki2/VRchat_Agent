"""One planned handoff over the OS-authenticated LOCAL owner channel only.

Never register as MCP/HTTP/WebSocket commands. Transfer bytes come from the local
C# gates, not SessionState or an agent. This coordinator compares the whole live
cohort; it cannot approve, create, renew, or replay a task. No disk persistence.
"""
import hashlib
import json
import math
import re
import time

MAX_BYTES=4*1024*1024


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate_key')
        result[key]=value
    return result


def decode(raw):
    if type(raw) is not str or not 1<=len(raw.encode('utf-8'))<=MAX_BYTES:
        raise ValueError('invalid_control_bytes')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def keys(value,*expected):
    if type(value) is not dict or set(value)!=set(expected):raise ValueError('invalid_control_shape')


def number(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('invalid_control_time')
    return value


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('invalid_approval_digest')
    return value


class ReloadControl:
    def __init__(self,runtime):
        self.runtime=runtime
        self.phase='idle'
        self.ticket=None
        self.handoff=None
        self.transfers=[]
        self.timer=None

    def abort(self):
        if self.timer is not None:self.timer.cancel();self.timer=None
        if self.ticket is not None:
            barrier=self.runtime._reload_barrier
            if barrier is not None and barrier['ticket'] is self.ticket:self.runtime.cancel_reload_barrier()
        self.ticket=None
        self.transfers.clear()
        if self.phase!='committed':self.phase='closed'

    def validate_transfers(self,request):
        raw=request['transfers']
        if type(raw) is not list or not 1<=len(raw)<=2 or sum(len(s.encode('utf-8')) for s in raw)>MAX_BYTES:
            raise ValueError('invalid_transfer_count')
        now=number(request['editor_now'])
        barrier=self.runtime._reload_barrier
        groups={'read':barrier['reads'],'material':barrier['writes']}
        groups={g:p for g,p in groups.items() if p}
        seen=set();remaining=[]
        for text in raw:
            t=decode(text)
            keys(t,'version','gate','handoff_id','project_id','from_connection_id','deadline','capabilities','plans')
            gate=t['gate']
            if (type(t['version']) is not int or t['version']!=1 or gate not in groups or gate in seen
                or t['handoff_id']!=self.handoff or t['project_id']!=self.runtime.project_id
                or t['from_connection_id']!=barrier['connection']):raise ValueError('transfer_binding_changed')
            seen.add(gate)
            left=number(t['deadline'])-now
            if not 0<left<=60:raise ValueError('transfer_expired')
            remaining.append(left)
            caps=t['capabilities']
            if (type(caps) is not list or not 1<=len(caps)<=32 or any(type(x) is not str for x in caps)
                or len(caps)!=len(set(caps))):raise ValueError('invalid_transfer_capabilities')
            rows=t['plans']
            expected={(p.approval_client,p.task_id,p.plan_id):p for p in groups[gate].values()}
            if type(rows) is not list or len(rows)!=len(expected) or not expected:raise ValueError('cohort_changed')
            matched=set()
            for row in rows:
                extra=('copied','history_digest','records_digest') if gate=='material' else ()
                keys(row,'plan_id','approval_digest','client_id','task_id','approval_connection_id',
                    'previous_binding_digest','expires_at','manifest','evidence',*extra)
                identity=(row['client_id'],row['task_id'],row['plan_id'])
                if identity not in expected or identity in matched:raise ValueError('cohort_changed')
                matched.add(identity);plan=expected[identity]
                if digest(row['approval_digest'])!=digest(plan.approval_digest):raise ValueError('approval_changed')
                digest(row['previous_binding_digest'])
                if type(row['approval_connection_id']) is not str or not row['approval_connection_id']:
                    raise ValueError('approval_connection_missing')
                if number(row['expires_at'])<t['deadline']:raise ValueError('expiry_changed')
                manifest=row['manifest']
                if gate=='material':
                    if manifest!=plan.manifest:raise ValueError('manifest_changed')
                    if type(row['copied']) is not bool:raise ValueError('invalid_material_state')
                    digest(row['history_digest']);digest(row['records_digest'])
                    if any(op not in caps for op in manifest['operations']):raise ValueError('capability_changed')
                else:
                    keys(manifest,'operations','targets','ttl_seconds')
                    ops=manifest['operations'];targets=manifest['targets']
                    if type(ops) is not list or type(targets) is not list:raise ValueError('manifest_changed')
                    for op in ops:keys(op,'command','action')
                    pairs=[(o['command'],o['action']) for o in ops]
                    if (len(pairs)!=len(plan.operations) or frozenset(pairs)!=plan.operations
                        or len(targets)!=len(plan.targets) or frozenset(targets)!=plan.targets
                        or any(a+'/'+b not in caps for a,b in pairs)
                        or not 0<number(manifest['ttl_seconds'])<=900):raise ValueError('manifest_changed')
                if type(row['evidence']) is not dict or not row['evidence']:raise ValueError('missing_evidence')
        if seen!=set(groups):raise ValueError('cohort_changed')
        barrier['deadline']=min(barrier['deadline'],time.monotonic()+min(remaining))
        self.transfers=list(raw)

    async def dispatch(self,request):
        try:
            if type(request) is not dict:raise ValueError()
            kind=request.get('kind')
            if kind=='arm' and self.phase=='idle':
                keys(request,'kind','handoff_id','window','editor_now','transfers')
                handoff=request['handoff_id']
                if type(handoff) is not str or re.fullmatch('[0-9a-f]{32}',handoff) is None:raise ValueError()
                self.handoff=handoff
                self.phase='freezing' # Before the registry await; no concurrent second arm.
                self.ticket=await self.runtime.freeze_for_reload(window=request['window'])
                if self.phase!='freezing':raise ValueError('control_cancelled')
                self.validate_transfers(request)
                if not self.runtime.suspend_reload_handoff(self.ticket):raise ValueError()
                self.phase='armed'
                import asyncio
                deadline=self.runtime._reload_barrier['deadline']
                self.timer=asyncio.get_running_loop().call_later(max(0,deadline-time.monotonic()),self.abort)
                return {'kind':'armed','handoff_id':self.handoff,
                    'digests':[hashlib.sha256(s.encode('utf-8')).hexdigest() for s in self.transfers]}
            if kind=='reattach' and self.phase=='armed':
                keys(request,'kind','handoff_id')
                if request['handoff_id']!=self.handoff or not self.runtime.unity_ingress.allow_reload_reattach(self.ticket):raise ValueError()
                self.phase='reattaching'
                return {'kind':'reattach','handoff_id':self.handoff,'transfers':list(self.transfers)}
            if kind=='commit' and self.phase=='reattaching':
                keys(request,'kind','handoff_id','connection_id','bindings')
                connection=request['connection_id']
                if (request['handoff_id']!=self.handoff or type(connection) is not str
                    or connection!=self.runtime.unity_ingress.session_id):raise ValueError()
                # Exactly Newtonsoft's compact envelope around its ORIGINAL UTF-8
                # transfer. Do not reserialize nested floats or Unicode in Python.
                expected=[hashlib.sha256(('{"transfer":'+raw+',"to_connection_id":'+json.dumps(connection,ensure_ascii=False)+'}').encode('utf-8')).hexdigest() for raw in self.transfers]
                if request['bindings']!=expected:raise ValueError()
                self.phase='committing'
                if not await self.runtime.commit_reload_handoff(self.ticket):raise ValueError()
                self.phase='committed';self.abort()
                return {'kind':'committed','handoff_id':self.handoff}
            raise ValueError()
        except BaseException as error:
            self.abort()
            if not isinstance(error,Exception):raise
            raise PermissionError('local_reload_control_denied') from None


async def joined_worker(stop,operation,*args,**kwargs):
    """Cancel through the native worker's stop event, then join before returning."""
    import asyncio
    task=asyncio.create_task(asyncio.to_thread(operation,*args,**kwargs))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        stop.set()
        while not task.done():
            try:await asyncio.shield(task)
            except asyncio.CancelledError:continue
            except Exception:break
        await asyncio.gather(task,return_exceptions=True)
        raise


async def serve_channel(runtime,channel,*,reusable=False):
    """Three local messages on one already OS-authenticated channel.

    No network listener or peer discovery. Caller holds the original peer until
    this coroutine returns. Every blocking worker is joined before HANDLE close.
    """
    import asyncio
    from launcher.peer_channel import PeerChannel
    if type(channel) is not PeerChannel:raise TypeError('os_peer_channel_required')
    if type(reusable) is not bool:raise TypeError('invalid_control_mode')
    control=ReloadControl(runtime)
    run_deadline=channel.deadline
    seen=set()
    async def io(operation,*args):
        try:return await joined_worker(channel.stop,operation,*args)
        except asyncio.CancelledError:
            control.abort()
            raise
    acknowledged=False
    try:
        for _ in range(384 if reusable else 3):
            raw=await io(channel.receive)
            request=decode(raw.decode('utf-8'))
            if control.phase=='idle':
                handoff=request.get('handoff_id') if type(request) is dict else None
                if type(handoff) is not str or handoff in seen or len(seen)>=128:raise ValueError()
                seen.add(handoff)
            reply=await control.dispatch(request)
            if control.phase=='armed':channel.deadline=min(run_deadline,runtime._reload_barrier['deadline'])
            await io(channel.send,json.dumps(reply,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))
            if control.phase=='committed':
                acknowledged=True
                if not reusable:return True
                control=ReloadControl(runtime)
                # Return to the ORIGINAL transport run deadline, never extend it
                # or any plan/credential. Each next arm rechecks its own <=60s window.
                channel.deadline=run_deadline
                acknowledged=False
        return False
    except Exception:
        return False # Fixed local failure, never log transfer/exception material.
    finally:
        if reusable or (control.phase=='committed' and not acknowledged):
            # Final ACK failed after binding moved: revoke, do not report success.
            ingress=runtime.unity_ingress
            if ingress is not None:ingress.revoke()
        control.abort();channel.stop.set();channel.close()
