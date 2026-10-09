using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace Yukino.VRChatAgent
{
 // Local bytes only. Caller supplies the originally captured owner identity;
 // a PID/locator from discovery or a message is NOT an authorization source.
 internal sealed class EditorPeerChannel : IDisposable
 {
  internal sealed class HeldPeer : IDisposable
  {
   readonly object sync=new object();
   readonly int pid;
   readonly bool windows;
   SafeHandle handle;
   internal long Created { get; private set; }
   internal HeldPeer(int expectedPid,long expectedCreated)
   {
    if(expectedPid<=1||expectedCreated<=0||RuntimeInformation.ProcessArchitecture!=Architecture.X64)
     throw new ArgumentException("owner_identity_required");
    pid=expectedPid;windows=RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
    try {
     if(windows){
      handle=OpenProcess(0x00101000,false,pid);
      if(handle.IsInvalid||!GetProcessTimes(handle,out long created,out _,out _,out _))throw new IOException("owner_handle_refused");
      Created=created;
     }else if(RuntimeInformation.IsOSPlatform(OSPlatform.Linux)){
      long fd=Syscall(434,pid,0); // pidfd_open on the explicitly supported Linux x64 ABI.
      if(fd<0||fd>int.MaxValue)throw new IOException("owner_pidfd_refused");
      handle=new SafeFileHandle(new IntPtr(fd),true);
      using(var input=new FileStream("/proc/"+pid+"/stat",FileMode.Open,FileAccess.Read,FileShare.ReadWrite)){
       byte[] buffer=new byte[4097];int count=0,n;
       while(count<buffer.Length&&(n=input.Read(buffer,count,buffer.Length-count))>0)count+=n;
       if(count==buffer.Length)throw new IOException("owner_stat_oversize");
       string stat=Encoding.UTF8.GetString(buffer,0,count);int end=stat.LastIndexOf(") ",StringComparison.Ordinal);
       if(end<0)throw new IOException("owner_stat_invalid");
       Created=long.Parse(stat.Substring(end+2).Split(new[]{' '},StringSplitOptions.RemoveEmptyEntries)[19]);
      }
     }else throw new PlatformNotSupportedException("owner_platform_unsupported");
     if(Created!=expectedCreated||!Alive)throw new IOException("owner_identity_changed");
    }catch{Dispose();throw;}
   }
   internal bool Alive {
    get {lock(sync){
     if(handle==null||handle.IsClosed||handle.IsInvalid)return false;
     if(windows)return WaitForSingleObject(handle,0)==258;
     var fds=new[]{new PollFd{fd=handle.DangerousGetHandle().ToInt32(),events=1}};
     return Poll(fds,new UIntPtr(1),0)==0;
    }}
   }
   internal bool Matches(SafeHandle channel)
   {
    lock(sync){
     if(!Alive||channel==null||channel.IsClosed||channel.IsInvalid)return false;
     if(windows)return GetNamedPipeServerProcessId(channel,out uint peer)&&peer==(uint)pid&&Alive;
     uint length=12;
     return GetSocketOption(channel,1,17,out Credentials credentials,ref length)==0&&length==12
      &&credentials.pid==pid&&credentials.uid==GetUid()&&Alive;
    }
   }
   public void Dispose(){lock(sync){handle?.Dispose();handle=null;}}
  }
  [StructLayout(LayoutKind.Sequential)]struct PollFd {internal int fd;internal short events,revents;}
  [StructLayout(LayoutKind.Sequential)]struct Credentials {internal int pid;internal uint uid,gid;}
  [DllImport("libc",EntryPoint="syscall",SetLastError=true)]static extern long Syscall(long number,int pid,uint flags);
  [DllImport("libc",EntryPoint="poll",SetLastError=true)]static extern int Poll([In,Out]PollFd[] descriptors,UIntPtr count,int timeout);
  [DllImport("libc",EntryPoint="getsockopt",SetLastError=true)]static extern int GetSocketOption(SafeHandle socket,int level,int option,out Credentials value,ref uint size);
  [DllImport("libc",EntryPoint="getuid")]static extern uint GetUid();
  [DllImport("libc",EntryPoint="fcntl",SetLastError=true)]static extern int DuplicateCloseOnExec(int fd,int command,int minimum);
  [DllImport("kernel32.dll",SetLastError=true)]static extern SafeWaitHandle OpenProcess(uint access,bool inherit,int pid);
  [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetProcessTimes(SafeHandle process,out long created,out long exited,out long kernel,out long user);
  [DllImport("kernel32.dll",SetLastError=true)]static extern uint WaitForSingleObject(SafeHandle handle,uint milliseconds);
  [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetNamedPipeServerProcessId(SafeHandle pipe,out uint pid);

  const int MaxFrame=4*1024*1024;
  readonly HeldPeer peer;
  readonly double runDeadline;
  readonly CancellationTokenSource stop=new CancellationTokenSource();
  readonly SemaphoreSlim serial=new SemaphoreSlim(1,1);
  Stream stream;
  Socket socket;
  SafeFileHandle socketProof;
  NamedPipeClientStream pipe;
  int closed;
  static double Now=>Stopwatch.GetTimestamp()/(double)Stopwatch.Frequency;
  static bool Finite(double n)=>!double.IsNaN(n)&&!double.IsInfinity(n);
  EditorPeerChannel(HeldPeer owner,double seconds){peer=owner;runDeadline=Now+seconds;}
  void Check(double deadline,CancellationToken cancel,bool verify=true)
  {
   cancel.ThrowIfCancellationRequested();
   if(closed!=0||Now>=deadline||!peer.Alive)throw new IOException("owner_channel_expired");
   if(verify&&!peer.Matches(pipe!=null?(SafeHandle)pipe.SafePipeHandle:socketProof))
    throw new IOException("owner_channel_foreign");
  }
  async Task<T> Finish<T>(Task<T> operation,double deadline,CancellationToken cancel,bool verify=true)
  {
   try {
    while(!operation.IsCompleted){Check(deadline,cancel,verify);await Task.WhenAny(operation,Task.Delay(10));}
    T value=await operation;Check(deadline,cancel,verify);return value;
   }catch{
    Dispose(); // Framework-owned async buffers remain retained until the operation finishes.
    try{await operation;}catch{}
    throw;
   }
  }
  static async Task<int> AsValue(Task task){await task;return 0;}
  internal static async Task<EditorPeerChannel> ConnectAsync(string locator,HeldPeer owner,double runSeconds,CancellationToken cancel)
  {
   if(owner==null||!Finite(runSeconds)||runSeconds<=0||runSeconds>3600||locator==null||
    !Regex.IsMatch(locator,@"\Avrchat-local-[0-9a-f]{48}\z"))throw new ArgumentException("owner_channel_arguments");
   var channel=new EditorPeerChannel(owner,runSeconds);
   try {
    double deadline=Math.Min(channel.runDeadline,Now+5);
    using(var linked=CancellationTokenSource.CreateLinkedTokenSource(cancel,channel.stop.Token)){
     channel.Check(deadline,linked.Token,false);
     if(RuntimeInformation.IsOSPlatform(OSPlatform.Windows)){
      channel.pipe=new NamedPipeClientStream(".",locator,PipeDirection.InOut,PipeOptions.Asynchronous,
       TokenImpersonationLevel.None,HandleInheritability.None);
      channel.stream=channel.pipe;
      await channel.Finish(AsValue(channel.pipe.ConnectAsync(5000,linked.Token)),deadline,linked.Token,false);
     }else if(RuntimeInformation.IsOSPlatform(OSPlatform.Linux)){
      channel.socket=new Socket(AddressFamily.Unix,SocketType.Stream,ProtocolType.Unspecified);
      // netstandard2.1 has no Socket.SafeHandle. Duplicate the NEW, unshared fd
      // before any async I/O; held CLOEXEC proof cannot race descriptor reuse.
      int proof=DuplicateCloseOnExec(channel.socket.Handle.ToInt32(),1030,0);
      if(proof<0)throw new IOException("owner_socket_proof_refused");
      channel.socketProof=new SafeFileHandle(new IntPtr(proof),true);
      await channel.Finish(AsValue(channel.socket.ConnectAsync(new UnixDomainSocketEndPoint("\0"+locator))),deadline,linked.Token,false);
      channel.stream=new NetworkStream(channel.socket,true);
     }else throw new PlatformNotSupportedException();
     channel.Check(deadline,linked.Token); // Kernel peer BEFORE any authority bytes.
    }
    return channel;
   }catch{channel.Dispose();throw;}
  }
  internal async Task<byte[]> ExchangeAsync(byte[] request,double seconds,CancellationToken cancel)
  {
   if(request==null||request.Length<1||request.Length>MaxFrame||!Finite(seconds)||seconds<=0||seconds>60)
    throw new ArgumentException("owner_frame_invalid");
   byte[] payload=(byte[])request.Clone(); // Caller aliases cannot change queued bytes.
   double deadline=Math.Min(runDeadline,Now+seconds);
   try {
    using(var queued=CancellationTokenSource.CreateLinkedTokenSource(cancel,stop.Token)){
     queued.CancelAfter(TimeSpan.FromSeconds(Math.Max(0,deadline-Now)));
     await serial.WaitAsync(queued.Token);
    }
   }catch{Dispose();throw;}
   try {
    using(var linked=CancellationTokenSource.CreateLinkedTokenSource(cancel,stop.Token)){
     Check(deadline,linked.Token);
     int size=payload.Length;byte[] prefix={(byte)(size>>24),(byte)(size>>16),(byte)(size>>8),(byte)size};
     await Finish(AsValue(stream.WriteAsync(prefix,0,4,linked.Token)),deadline,linked.Token);
     for(int offset=0;offset<payload.Length;offset+=65536)
      await Finish(AsValue(stream.WriteAsync(payload,offset,Math.Min(65536,payload.Length-offset),linked.Token)),deadline,linked.Token);
     async Task ReadExact(byte[] bytes){
      for(int offset=0;offset<bytes.Length;){
       int n=await Finish(stream.ReadAsync(bytes,offset,Math.Min(65536,bytes.Length-offset),linked.Token),deadline,linked.Token);
       if(n==0)throw new EndOfStreamException("owner_channel_closed");offset+=n;
      }
     }
     await ReadExact(prefix);
     uint count=((uint)prefix[0]<<24)|((uint)prefix[1]<<16)|((uint)prefix[2]<<8)|prefix[3];
     if(count<1||count>MaxFrame)throw new IOException("owner_frame_invalid");
     byte[] result=new byte[(int)count];await ReadExact(result);return result;
    }
   }catch{Dispose();throw;}
   finally{serial.Release();}
  }
  public void Dispose()
  {
   if(Interlocked.Exchange(ref closed,1)!=0)return;
   try{socketProof?.Dispose();}finally{try{stop.Cancel();}finally{try{stream?.Dispose();}finally{socket?.Dispose();stop.Dispose();}}}
  }
 }
}
