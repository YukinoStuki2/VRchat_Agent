"""Windows CPython 3.11+ process ownership; import is inert on all platforms.
Children are born in our non-inheritable kill-on-close job, then resumed.
Windows 10 / Server 2016+ JOB_LIST is required; no create-then-assign fallback.
Never find/kill a process by port, executable name or reused PID.
"""
import ctypes as C
import os
import subprocess
import threading
import time

DWORD=C.c_uint32
HANDLE=C.c_void_p
SIZE_T=C.c_size_t
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE=0x2000
CREATE_SUSPENDED=0x4

class BASIC_LIMIT(C.Structure):
    _fields_=[('PerProcessUserTimeLimit',C.c_int64),('PerJobUserTimeLimit',C.c_int64),
              ('LimitFlags',DWORD),('MinimumWorkingSetSize',SIZE_T),('MaximumWorkingSetSize',SIZE_T),
              ('ActiveProcessLimit',DWORD),('Affinity',SIZE_T),('PriorityClass',DWORD),('SchedulingClass',DWORD)]
class IO_COUNTERS(C.Structure):
    _fields_=[(n,C.c_uint64) for n in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
class EXTENDED_LIMIT(C.Structure):
    _fields_=[('BasicLimitInformation',BASIC_LIMIT),('IoInfo',IO_COUNTERS),
              ('ProcessMemoryLimit',SIZE_T),('JobMemoryLimit',SIZE_T),('PeakProcessMemoryUsed',SIZE_T),('PeakJobMemoryUsed',SIZE_T)]
class ACCOUNTING(C.Structure):
    _fields_=[(n,C.c_int64) for n in ('TotalUserTime','TotalKernelTime','ThisPeriodTotalUserTime','ThisPeriodTotalKernelTime')]+[(n,DWORD) for n in ('TotalPageFaultCount','TotalProcesses','ActiveProcesses','TotalTerminatedProcesses')]

class STARTUPINFO(C.Structure):
    _fields_=[('cb',DWORD),('lpReserved',C.c_wchar_p),('lpDesktop',C.c_wchar_p),
              ('lpTitle',C.c_wchar_p)]+[(n,DWORD) for n in
              ('dwX','dwY','dwXSize','dwYSize','dwXCountChars','dwYCountChars','dwFillAttribute','dwFlags')]+[
              ('wShowWindow',C.c_uint16),('cbReserved2',C.c_uint16),('lpReserved2',C.c_void_p),
              ('hStdInput',HANDLE),('hStdOutput',HANDLE),('hStdError',HANDLE)]
class STARTUPINFOEX(C.Structure):
    _fields_=[('StartupInfo',STARTUPINFO),('lpAttributeList',C.c_void_p)]
class PROCESS_INFORMATION(C.Structure):
    _fields_=[('hProcess',HANDLE),('hThread',HANDLE),('dwProcessId',DWORD),('dwThreadId',DWORD)]

class WinAPI:
    def __init__(self):
        if os.name!='nt':raise OSError('Windows CPython required')
        import _winapi
        import msvcrt
        self.w,self.m=_winapi,msvcrt
        self.k=C.WinDLL('kernel32',use_last_error=True)
        signatures={
            'CreateJobObjectW':([C.c_void_p,C.c_wchar_p],HANDLE),
            'SetInformationJobObject':([HANDLE,C.c_int,C.c_void_p,DWORD],C.c_int),
            'QueryInformationJobObject':([HANDLE,C.c_int,C.c_void_p,DWORD,C.c_void_p],C.c_int),
            'IsProcessInJob':([HANDLE,HANDLE,C.POINTER(C.c_int)],C.c_int),
            'InitializeProcThreadAttributeList':([C.c_void_p,DWORD,DWORD,C.POINTER(SIZE_T)],C.c_int),
            'UpdateProcThreadAttribute':([C.c_void_p,DWORD,SIZE_T,C.c_void_p,SIZE_T,C.c_void_p,C.c_void_p],C.c_int),
            'DeleteProcThreadAttributeList':([C.c_void_p],None),
            'CreateProcessW':([C.c_wchar_p,C.c_wchar_p,C.c_void_p,C.c_void_p,C.c_int,DWORD,
                               C.c_void_p,C.c_wchar_p,C.POINTER(STARTUPINFOEX),C.POINTER(PROCESS_INFORMATION)],C.c_int),
            'TerminateJobObject':([HANDLE,C.c_uint],C.c_int),
            'ResumeThread':([HANDLE],DWORD)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.k,name);fn.argtypes=args;fn.restype=result
    def checked(self,result):
        if not result:raise C.WinError(C.get_last_error())
        return result
    def open_parent(self,pid):return self.w.OpenProcess(0x00100000,False,pid)
    def parent_alive(self,handle):
        state=self.w.WaitForSingleObject(handle,0)
        if state==258:return True
        if state==0:return False
        raise OSError('Parent wait failed')
    def close_handle(self,handle):self.w.CloseHandle(handle)
    def create_job(self):
        job=self.checked(self.k.CreateJobObjectW(None,None))
        try:
            limit=EXTENDED_LIMIT();limit.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            self.checked(self.k.SetInformationJobObject(job,9,C.byref(limit),C.sizeof(limit)))
            return job
        except BaseException:self.close_handle(job);raise
    def assign(self,job,process):
        # Legacy caller seam now verifies membership established atomically at birth.
        inside=C.c_int()
        self.checked(self.k.IsProcessInJob(process,job,C.byref(inside)))
        if not inside.value:raise OSError('Child was not created inside owned job')
    def resume(self,thread):
        if self.k.ResumeThread(thread)==0xffffffff:raise C.WinError(C.get_last_error())
    def terminate_job(self,job):self.checked(self.k.TerminateJobObject(job,1))
    def job_empty(self,job):
        info=ACCOUNTING();self.checked(self.k.QueryInformationJobObject(job,1,C.byref(info),C.sizeof(info),None))
        return info.ActiveProcesses==0
    def create_suspended(self,args,env,callback,job):
        # Explicit handle_list prevents leaking parent's unrelated inheritable handles.
        nullfd=os.open(os.devnull,os.O_RDWR);readfd=writefd=None;process=thread=None
        try:
            os.set_inheritable(nullfd,True)
            if callback is not None:
                readfd,writefd=os.pipe();os.set_inheritable(writefd,True)
            null=self.m.get_osfhandle(nullfd)
            err=self.m.get_osfhandle(writefd) if writefd is not None else null
            if not job:raise ValueError('Owned job required')
            if type(env) is not dict or any(type(k) is not str or type(v) is not str or not k or
                    '=' in k or '\0' in k or '\0' in v for k,v in env.items()):
                raise ValueError('Invalid child environment')
            startup=STARTUPINFOEX();startup.StartupInfo.cb=C.sizeof(startup)
            startup.StartupInfo.dwFlags=subprocess.STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput=null;startup.StartupInfo.hStdOutput=null;startup.StartupInfo.hStdError=err
            size=SIZE_T()
            self.k.InitializeProcThreadAttributeList(None,2,0,C.byref(size))
            if C.get_last_error()!=122 or not size.value:raise C.WinError(C.get_last_error())
            attributes=C.create_string_buffer(size.value)
            self.checked(self.k.InitializeProcThreadAttributeList(attributes,2,0,C.byref(size)))
            try:
                startup.lpAttributeList=C.cast(attributes,C.c_void_p)
                allowed=list({null,err});handles=(HANDLE*len(allowed))(*allowed);jobs=(HANDLE*1)(job)
                # Documented HANDLE_LIST (2) and JOB_LIST (13), both input attributes.
                self.checked(self.k.UpdateProcThreadAttribute(attributes,0,0x20002,handles,C.sizeof(handles),None,None))
                self.checked(self.k.UpdateProcThreadAttribute(attributes,0,0x2000D,jobs,C.sizeof(jobs),None,None))
                environment=C.create_unicode_buffer('\0'.join(k+'='+env[k] for k in sorted(env,key=str.upper))+'\0')
                command=C.create_unicode_buffer(subprocess.list2cmdline(args))
                info=PROCESS_INFORMATION()
                flags=CREATE_SUSPENDED|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW|0x00000400|0x00080000
                self.checked(self.k.CreateProcessW(args[0],command,None,None,True,flags,environment,None,C.byref(startup),C.byref(info)))
                process,thread=info.hProcess,info.hThread
            finally:
                self.k.DeleteProcThreadAttributeList(attributes)
            result=NativeProcess(self,process,thread,readfd,callback);readfd=None
            return result
        except BaseException:
            if process is not None:
                try:self.w.TerminateProcess(process,1);self.w.WaitForSingleObject(process,5000)
                finally:self.close_handle(process)
            if thread is not None:self.close_handle(thread)
            raise
        finally:
            for fd in (nullfd,writefd,readfd):
                if fd is not None:os.close(fd)

class NativeProcess:
    def __init__(self,api,handle,thread,readfd,callback):
        self.api,self.handle,self.thread=api,handle,thread
        self.readfd,self.callback=readfd,callback
        self.reader=None
    def poll(self):
        if self.handle is None:return 0
        if self.api.w.WaitForSingleObject(self.handle,0)==258:return None
        return self.api.w.GetExitCodeProcess(self.handle)
    def stop(self):
        if self.poll() is None:self.api.w.TerminateProcess(self.handle,1)
        if self.api.w.WaitForSingleObject(self.handle,5000)!=0:raise OSError('Owned child did not stop')
    def _drain(self):
        pending=b'';discard=False
        try:
            while True:
                data=os.read(self.readfd,4096)
                if not data:
                    if pending and not discard:
                        try:self.callback(pending.decode('utf-8','replace').rstrip('\r\n'))
                        except Exception:pass
                    break
                for part in data.splitlines(keepends=True):
                    end=part.endswith(b'\n')
                    if not discard:
                        pending+=part
                        if len(pending)>4096:pending=b'';discard=True
                    if end:
                        if not discard:
                            try:self.callback(pending.decode('utf-8','replace').rstrip('\r\n'))
                            except Exception:pass
                        pending=b'';discard=False
        except OSError:pass
        finally:
            if self.readfd is not None:os.close(self.readfd);self.readfd=None
    def start_reader(self):
        if self.readfd is not None:
            self.reader=threading.Thread(target=self._drain,name='owned-ssh-output',daemon=True);self.reader.start()
    def close(self):
        for attr in ('thread','handle'):
            value=getattr(self,attr)
            if value is not None:self.api.close_handle(value);setattr(self,attr,None)
        if self.reader is not None:
            self.reader.join(5)
            if self.reader.is_alive():raise OSError('Owned output reader did not stop')
        elif self.readfd is not None:os.close(self.readfd);self.readfd=None

class OwnedProcesses:
    def __init__(self,parent_pid,api=None):
        self.api=api if api is not None else WinAPI()
        self.parent=self.api.open_parent(parent_pid);self.job=None;self.children=[];self.closed=False
        try:self.job=self.api.create_job()
        except BaseException:self.api.close_handle(self.parent);raise
    def alive(self):return not self.closed and self.api.parent_alive(self.parent)
    def spawn(self,args,env,stderr_line_callback=None):
        if self.closed or not self.alive():raise OSError('Parent unavailable')
        child=self.api.create_suspended(args,env,stderr_line_callback,self.job)
        try:
            self.api.assign(self.job,child.handle)
            self.api.resume(child.thread)
            child.start_reader()
            self.children.append(child)
            return child
        except BaseException:
            try:child.stop()
            finally:child.close()
            raise
    def close(self):
        if self.closed:return getattr(self,'clean',False)
        self.closed=True;clean=True
        try:
            self.api.terminate_job(self.job)
            deadline=time.monotonic()+5
            while not self.api.job_empty(self.job):
                if time.monotonic()>=deadline:clean=False;break
                time.sleep(0.05)
        except Exception:clean=False
        finally:
            # Closing noninheritable job is the OS-enforced crash fallback too.
            try:self.api.close_handle(self.job)
            except Exception:clean=False
            for child in self.children:
                try:child.close()
                except Exception:clean=False
            try:self.api.close_handle(self.parent)
            except Exception:clean=False
        self.clean=clean
        return clean
