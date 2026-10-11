using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Yukino.VRChatAgent;

// Pure lexical cases run everywhere; all locking/link cases require a real Windows kernel.
static class ScriptPathCases
{
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Denied(Action action,string why){bool denied=false;try{action();}catch{denied=true;}Check(denied,why);}
    static void Rules()
    {
        var type=typeof(ScriptFileStore).Assembly.GetType("Yukino.VRChatAgent.ScriptPathLease");
        Check(type!=null,"missing pinned Windows path lease");
        var validate=type.GetMethod("ValidatePath",BindingFlags.NonPublic|BindingFlags.Static);
        Check(validate!=null,"missing exact Windows path validation");
        Action<string> run=path=>validate.Invoke(null,new object[]{path});
        run(@"C:\Project\Assets\A.cs");run(@"D:\项目\Assets\源.shader");
        foreach(var path in new[]{@"C:relative",@"\\server\share\a",@"\\?\C:\a",@"C:\a\..\b",@"C:\a\.\b",@"C:\a\\b",@"C:\a\b.",@"C:\a\b ",@"C:\a\NUL.cs",@"C:\a\COM¹.cs",@"C:\a\a.cs:data",@"C:/a/b",@"C:\a\a\",@"C:\a\bad\n".Replace("\\n","\n")})
            Denied(()=>run(path),"accepted alias/device: "+path);
    }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateHardLinkW(string link,string existing,IntPtr unused);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateSymbolicLinkW(string link,string target,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern uint GetLongPathNameW(string path,System.Text.StringBuilder result,uint size);
    static void Fixture(Action<ScriptFileStore,string,string> action)
    {
        string root=Path.Combine(Path.GetTempPath(),"vragent-script-path-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var buffer=new System.Text.StringBuilder(32768);Check(GetLongPathNameW(root,buffer,(uint)buffer.Capacity)>0,"fixture canonicalization failed");root=buffer.ToString();
        try
        {
            Directory.CreateDirectory(Path.Combine(root,"Assets"));var file=Path.Combine(root,"Assets","A.cs");
            File.WriteAllText(file,"class A {}\n");File.WriteAllText(file+".meta","guid: fixture\n");
            var store=new ScriptFileStore(root);store.Capture("Assets/A.cs"); // positive control before every negative case
            action(store,root,file);
        }
        finally{Directory.Delete(root,true);}
        Check(!Directory.Exists(root),"fixture not cleaned");
    }
    static void RoundTrip()=>Fixture((store,root,file)=>{
        var row=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class New {}\n",()=>true);
        Check((string)row["outcome"]=="changed"&&row["error"].Type==Newtonsoft.Json.Linq.JTokenType.Null,row.ToString());
        Check((string)new ScriptFileStore(root).Restore((string)row["transaction_id"],()=>true)["outcome"]=="restored","durable restore failed");
        Check(File.ReadAllText(file)=="class A {}\n","wrong restore bytes");
    });
    static void RenameDenied(string source,string destination,string why)
    {
        bool moved=false;
        try{Denied(()=>{Directory.Move(source,destination);moved=true;},why);}
        finally{if(moved)Directory.Move(destination,source);}
    }
    static void HeldAncestors()=>Fixture((store,root,file)=>{
        var snapshot=store.Capture("Assets/A.cs");int entered=0;
        var row=store.Write("Assets/A.cs",snapshot,"class New {}\n",()=>{
            entered++;
            RenameDenied(Path.Combine(root,"Assets"),Path.Combine(root,"Moved"),"ancestor renamed during authorization");
            RenameDenied(root,root+"-moved","project root renamed during authorization");
            Denied(()=>{using(var s=new FileStream(file,FileMode.Open,FileAccess.Write,FileShare.ReadWrite|FileShare.Delete)){}},"writer entered held leaf");
            return true;
        });
        Check(entered==2&&(string)row["outcome"]=="changed",row.ToString());
        Directory.Move(Path.Combine(root,"Assets"),Path.Combine(root,"Moved"));Directory.Move(Path.Combine(root,"Moved"),Path.Combine(root,"Assets"));
    });
    static void BusyWriter()=>Fixture((store,root,file)=>{
        var expected=store.Capture("Assets/A.cs");
        using(var writer=new FileStream(file,FileMode.Open,FileAccess.Write,FileShare.ReadWrite|FileShare.Delete))
        {Denied(()=>store.Capture("Assets/A.cs"),"busy capture admitted");Denied(()=>store.Write("Assets/A.cs",expected,"class Bad {}",()=>true),"busy writer admitted");}
        Check(File.ReadAllText(file)=="class A {}\n","busy source changed");
    });
    static void Hardlinks()=>Fixture((store,root,file)=>{
        string link=Path.Combine(root,"alias.cs");Check(CreateHardLinkW(link,file,IntPtr.Zero),"hardlink fixture creation failed");
        Denied(()=>store.Capture("Assets/A.cs"),"hardlink admitted");File.Delete(link);store.Capture("Assets/A.cs");
    });
    static void Reparse()=>Fixture((store,root,file)=>{
        string assets=Path.Combine(root,"Assets"),real=Path.Combine(root,"RealAssets");Directory.Move(assets,real);
        Check(CreateSymbolicLinkW(assets,real,1|2)||CreateSymbolicLinkW(assets,real,1),"directory symlink unavailable; not a passing kernel check");
        try{Denied(()=>store.Capture("Assets/A.cs"),"reparse ancestor admitted");}
        finally{Directory.Delete(assets);Directory.Move(real,assets);}
        string other=Path.Combine(root,"Other.cs");File.Move(file,other);
        Check(CreateSymbolicLinkW(file,other,2)||CreateSymbolicLinkW(file,other,0),"leaf symlink unavailable; not a passing kernel check");
        try{Denied(()=>store.Capture("Assets/A.cs"),"reparse leaf admitted");}
        finally{File.Delete(file);File.Move(other,file);}
    });
    static void Aliases()=>Fixture((store,root,file)=>{
        Denied(()=>store.Capture("Assets/a.cs"),"case alias admitted");
        Denied(()=>new ScriptFileStore(root+"\\.").Capture("Assets/A.cs"),"root dot alias admitted");
    });
    public static int Main()
    {
        try
        {
            Rules();Console.WriteLine("PASS WP001 exact_windows_path_rules");
            if(Environment.OSVersion.Platform!=PlatformID.Win32NT){Console.WriteLine("WINDOWS_KERNEL_NOT_EXECUTED");return 0;}
            RoundTrip();Console.WriteLine("PASS WP002 actual_windows_write_restore");
            HeldAncestors();Console.WriteLine("PASS WP003 ancestor_leaf_locks_and_release");
            BusyWriter();Console.WriteLine("PASS WP004 preexisting_writer_denied");
            Hardlinks();Console.WriteLine("PASS WP005 hardlinks_denied");
            Reparse();Console.WriteLine("PASS WP006 directory_and_leaf_reparse_denied");
            Aliases();Console.WriteLine("PASS WP007_aliases_denied".Replace("WP007_","WP007 "));
            return 0;
        }
        catch(Exception ex){Console.WriteLine("FAIL "+ex);return 1;}
    }
}
