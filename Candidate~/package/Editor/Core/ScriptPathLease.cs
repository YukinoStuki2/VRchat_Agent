using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Yukino.VRChatAgent
{
    // Same-HANDLE IO with every ancestor held. Not an administrator/plugin sandbox.
    internal sealed class ScriptPathLease : IDisposable
    {
        sealed class Pin
        {internal SafeFileHandle Handle;internal string Path;internal Information Before;}
        readonly List<Pin> pins=new List<Pin>();
        static void Need(bool ok,string reason){if(!ok)throw new CandidateWriteDenied(reason);}
        internal static void ValidatePath(string path)
        {
            Need(path!=null&&path.Length>=3&&((path[0]>='A'&&path[0]<='Z')||(path[0]>='a'&&path[0]<='z'))&&path[1]==':'&&path[2]=='\\',"local_absolute_path_required");
            if(path.Length==3)return;
            foreach(string part in path.Substring(3).Split('\\'))
            {
                Need(part.Length>0&&part==part.Trim()&&part!="."&&part!=".."&&!part.EndsWith(".",StringComparison.Ordinal)&&
                    !part.Any(c=>char.IsControl(c)||"<>:\"/|?*".Contains(c)),"unsafe_path_component");
                string name=part.Split('.')[0].ToUpperInvariant();
                Need(!(new[]{"CON","PRN","AUX","NUL","CONIN$","CONOUT$"}).Contains(name)&&
                    !(name.Length==4&&(name.StartsWith("COM",StringComparison.Ordinal)||name.StartsWith("LPT",StringComparison.Ordinal))&&"123456789¹²³".Contains(name[3])),"reserved_path");
            }
        }
        internal static ScriptPathLease Directory(string path,bool create=false)
        {
            Need(Environment.OSVersion.Platform==PlatformID.Win32NT,"windows_file_contract_required");ValidatePath(path);
            Need(GetDriveTypeW(path.Substring(0,3))==3,"fixed_local_drive_required");
            var lease=new ScriptPathLease();
            try
            {
                string current=path.Substring(0,3);lease.Add(current);
                foreach(string part in path.Substring(3).Split(new[]{'\\'},StringSplitOptions.RemoveEmptyEntries))
                {
                    current=Path.Combine(current,part);
                    // Parent is already held before any directory creation. No
                    // recursive path-only traversal of a substituted ancestor.
                    if(create&&!System.IO.Directory.Exists(current))System.IO.Directory.CreateDirectory(current);
                    lease.Add(current);
                }
                lease.Verify();return lease;
            }
            catch{lease.Dispose();throw;}
        }
        void Add(string path)
        {
            // FILE_LIST_DIRECTORY participates in share-access checks; attributes alone do not.
            var handle=CreateFileW("\\\\?\\"+path,0x81,1,IntPtr.Zero,3,0x02200000,IntPtr.Zero);
            try{var info=Inspect(handle,path,true);pins.Add(new Pin{Handle=handle,Path=path,Before=info});}
            catch{handle.Dispose();throw;}
        }
        internal void Verify()
        {
            foreach(var pin in pins)
            {
                var now=Inspect(pin.Handle,pin.Path,true);var before=pin.Before;
                Need(now.Attributes==before.Attributes&&now.Volume==before.Volume&&now.IndexHigh==before.IndexHigh&&now.IndexLow==before.IndexLow,"ancestor_identity_changed");
            }
        }
        internal static FileStream Open(string path,bool write,bool create=false)
        {
            ValidatePath(path);var parents=Directory(Path.GetDirectoryName(path));SafeFileHandle handle=null;
            try
            {
                handle=CreateFileW("\\\\?\\"+path,write?0xC0000000u:0x80000000u,write?0u:1u,IntPtr.Zero,create?1u:3u,0x02200000,IntPtr.Zero);
                Inspect(handle,path,false);parents.Verify();
                return new HeldStream(handle,write?FileAccess.ReadWrite:FileAccess.Read,parents,path);
            }
            catch{handle?.Dispose();parents.Dispose();throw;}
        }
        sealed class HeldStream : FileStream
        {
            readonly ScriptPathLease parents;
            readonly string path;
            internal HeldStream(SafeFileHandle handle,FileAccess access,ScriptPathLease parents,string path):base(handle,access,4096,false)
            {this.parents=parents;this.path=path;}
            internal string Stamp()
            {
                parents.Verify();var i=Inspect(SafeFileHandle,path,false);
                Need(GetFileInformationByHandleEx(SafeFileHandle,0,out var basic,(uint)Marshal.SizeOf<BasicInfo>()),"file_information_failed");
                return string.Join(":",i.Attributes,i.Volume,i.IndexHigh,i.IndexLow,i.Links,i.SizeHigh,i.SizeLow,i.Written.High,i.Written.Low,basic.ChangeTime);
            }
            protected override void Dispose(bool disposing)
            {try{base.Dispose(disposing);}finally{if(disposing)parents.Dispose();}}
        }
        internal static string Stamp(FileStream stream)=>stream is HeldStream held?held.Stamp():null;
        static Information Inspect(SafeFileHandle handle,string path,bool directory)
        {
            Need(handle!=null&&!handle.IsInvalid&&!handle.IsClosed&&GetFileType(handle)==1,"file_handle_invalid");
            Need(GetFileInformationByHandle(handle,out var info)&&
                (info.Attributes&0x400)==0&&((info.Attributes&0x10)!=0)==directory&&(directory||info.Links==1),"file_identity_unsupported");
            var final=new StringBuilder(32768);uint length=GetFinalPathNameByHandleW(handle,final,(uint)final.Capacity,0);
            Need(length>0&&length<final.Capacity&&final.ToString()=="\\\\?\\"+path,"file_path_alias_or_redirect");
            return info;
        }
        public void Dispose(){for(int i=pins.Count-1;i>=0;i--)pins[i].Handle.Dispose();pins.Clear();}
        [StructLayout(LayoutKind.Sequential)]struct FileTime{internal uint Low,High;}
        [StructLayout(LayoutKind.Sequential)]struct Information
        {internal uint Attributes;internal FileTime Created,Accessed,Written;internal uint Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow;}
        [StructLayout(LayoutKind.Sequential)]struct BasicInfo
        {internal long CreationTime,LastAccessTime,LastWriteTime,ChangeTime;internal uint Attributes;}
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr security,uint disposition,uint flags,IntPtr template);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern uint GetDriveTypeW(string root);
        [DllImport("kernel32.dll",SetLastError=true)]static extern uint GetFileType(SafeFileHandle handle);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetFileInformationByHandle(SafeFileHandle handle,out Information info);
        [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetFileInformationByHandleEx(SafeFileHandle handle,int kind,out BasicInfo info,uint size);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle,StringBuilder path,uint size,uint flags);
    }
}
