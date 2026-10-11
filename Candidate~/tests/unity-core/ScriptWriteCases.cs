using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Newtonsoft.Json.Linq;

// Real temporary file IO. On Linux the Windows handle-identity probe is an
// explicit double: these checks cannot establish Windows sharing/link semantics.
static class ScriptWriteCases
{
    static void Check(bool value,string why){if(!value)throw new Exception(why);}
    static object Call(object obj,string name,params object[] args)
    {
        try{return obj.GetType().GetMethod(name,BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance).Invoke(obj,args);}
        catch(TargetInvocationException ex){throw ex.InnerException;}
    }
    static void BackupWriteRestore()
    {
        var type=typeof(ScriptWriteCases).Assembly.GetType("Yukino.VRChatAgent.ScriptFileStore");
        Check(type!=null,"missing non-compiling durable single-file backup/write/restore store");
        string root=Path.Combine(Path.GetTempPath(),"vragent-script-"+Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root,"Assets"));
            string target=Path.Combine(root,"Assets/A.cs");
            byte[] before=new byte[]{239,187,191}.Concat(Encoding.UTF8.GetBytes("class A {}\r\n")).ToArray();
            File.WriteAllBytes(target,before);File.WriteAllText(target+".meta","guid: fixture-guid\n");
            var store=Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,
                new object[]{root,(Action<FileStream>)(_=>{})},null);
            var observed=(JObject)Call(store,"Capture","Assets/A.cs");
            Check(!Directory.Exists(Path.Combine(root,"UserSettings")),"read-only capture created backup folders");
            var report=(JObject)Call(store,"Write","Assets/A.cs",observed,"class A { int n; }\r\n",(Func<bool>)(()=>true));
            Check((string)report["outcome"]=="changed",report.ToString());
            Check(File.ReadAllBytes(target).Take(3).SequenceEqual(before.Take(3)),"BOM was lost");
            Check(File.ReadAllText(target)=="class A { int n; }\r\n","new text missing");
            string id=(string)report["transaction_id"];
            string backup=Path.Combine(root,"UserSettings/VRChatAgent/ScriptBackups",id,"before.bytes");
            Check(File.ReadAllBytes(backup).SequenceEqual(before),"exact backup missing");
            Check(!Directory.EnumerateFiles(Path.Combine(root,"Assets")).Any(p=>p.EndsWith(".bak")||p.EndsWith(".tmp")),"compiled-tree backup/staging created");
            // Fresh object: recovery is durable, not a live grant or an in-memory undo.
            store=Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,
                new object[]{root,(Action<FileStream>)(_=>{})},null);
            var restored=(JObject)Call(store,"Restore",id,(Func<bool>)(()=>true));
            Check((string)restored["outcome"]=="restored",restored.ToString());
            Check(File.ReadAllBytes(target).SequenceEqual(before),"exact bytes not restored");
            Check(File.Exists(backup),"restore deleted recovery backup");
        }
        finally{if(Directory.Exists(root))Directory.Delete(root,true);}
        Check(!Directory.Exists(root),"fixture residue");
    }
    static void InterruptedJournalRecovery()
    {
        string root=Path.Combine(Path.GetTempPath(),"vragent-script-"+Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root,"Assets"));
            string target=Path.Combine(root,"Assets/A.shader");
            File.WriteAllText(target,"Shader \"Old\" {}\n");File.WriteAllText(target+".meta","guid: fixture-guid\n");
            var store=new Yukino.VRChatAgent.ScriptFileStore(root,_=>{});
            var receipt=store.Write("Assets/A.shader",store.Capture("Assets/A.shader"),"Shader \"New\" {}\n",()=>true);
            string id=(string)receipt["transaction_id"];
            string journal=Path.Combine(root,"UserSettings/VRChatAgent/ScriptBackups",id,"record.json");
            // Emulate interruption AFTER source flush, BEFORE final journal update.
            Check((string)JObject.Parse(File.ReadAllText(journal))["state"]=="prepared","prepared journal was updated");
            File.Delete(Path.Combine(Path.GetDirectoryName(journal),"write-result.json"));
            store=new Yukino.VRChatAgent.ScriptFileStore(root,_=>{});
            Check((string)store.Restore(id,()=>true)["outcome"]=="restored","durable prepared postimage cannot recover");
            Check(File.ReadAllText(target)=="Shader \"Old\" {}\n","interrupted transaction was not restored");
        }
        finally{if(Directory.Exists(root))Directory.Delete(root,true);}
        Check(!Directory.Exists(root),"fixture residue");
    }
    static void Reject(Action action,string why)
    {bool denied=false;try{action();}catch{denied=true;}Check(denied,why);}
    static void WithFixture(Action<Yukino.VRChatAgent.ScriptFileStore,string,string> action)
    {
        string root=Path.Combine(Path.GetTempPath(),"vragent-script-"+Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root,"Assets"));string file=Path.Combine(root,"Assets/A.cs");
            File.WriteAllText(file,"class A {}\n");File.WriteAllText(file+".meta","guid: fixture-guid\n");
            action(new Yukino.VRChatAgent.ScriptFileStore(root,_=>{}),root,file);
        }
        finally{if(Directory.Exists(root))Directory.Delete(root,true);}
        Check(!Directory.Exists(root),"fixture residue");
    }
    static void ScopeAndEncoding()=>WithFixture((store,root,file)=>
    {
        var observed=store.Capture("Assets/A.cs");
        foreach(var target in new[]{"../A.cs","Assets/../A.cs","Assets/A.txt","Assets/CON.cs","Assets/COM1.cs","Assets/A.cs:stream","Assets//A.cs"})
            Reject(()=>store.Capture(target),"unsafe target admitted: "+target);
        foreach(var text in new[]{"\0bad","\ud800","\ufeffclass A {}",new string('字',50000)})
            Reject(()=>store.Write("Assets/A.cs",observed,text,()=>true),"invalid source admitted");
        Check(File.ReadAllText(file)=="class A {}\n" && !Directory.Exists(Path.Combine(root,"UserSettings")),"invalid write had effects");
        File.WriteAllBytes(file,new byte[]{0xff,0xfe,0x61,0});observed=store.Capture("Assets/A.cs");
        Reject(()=>store.Write("Assets/A.cs",observed,"class A {}",()=>true),"legacy encoding guessed");
        Check(File.ReadAllBytes(file).SequenceEqual(new byte[]{0xff,0xfe,0x61,0}),"legacy source changed");
    });
    static void EvidenceAndStop()=>WithFixture((store,root,file)=>
    {
        var observed=store.Capture("Assets/A.cs");File.WriteAllText(file,"class UserEdit {}\n");
        Reject(()=>store.Write("Assets/A.cs",observed,"class AgentEdit {}\n",()=>true),"concurrent source overwritten");
        observed=store.Capture("Assets/A.cs");File.WriteAllText(file+".meta","guid: replaced\n");
        Reject(()=>store.Write("Assets/A.cs",observed,"class AgentEdit {}\n",()=>true),"concurrent meta ignored");
        observed=store.Capture("Assets/A.cs");int calls=0;
        var receipt=store.Write("Assets/A.cs",observed,"class AgentEdit {}\n",()=>++calls==1);
        Check((string)receipt["outcome"]=="unchanged" && (string)receipt["error"]=="plan_revoked","late stop did not prevent source write");
        Check(File.ReadAllText(file)=="class UserEdit {}\n","stop rolled back or changed user source");
        Check((bool)receipt["backup_retained"],"recovery evidence discarded");
    });
    static void RecoveryConflicts()=>WithFixture((store,root,file)=>
    {
        var receipt=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class AgentEdit {}\n",()=>true);
        string id=(string)receipt["transaction_id"];
        Reject(()=>store.Restore(id,()=>false),"recovery without local consent");
        File.WriteAllText(file,"class UserEdit {}\n");Reject(()=>store.Restore(id,()=>true),"user post-edit overwritten");
        Check(File.ReadAllText(file)=="class UserEdit {}\n","conflict recovery mutated source");
        File.WriteAllText(file,"class AgentEdit {}\n");File.WriteAllText(file+".meta","guid: replaced\n");
        Reject(()=>store.Restore(id,()=>true),"replaced meta ignored");
        File.WriteAllText(file+".meta","guid: fixture-guid\n");
        File.WriteAllText(Path.Combine(root,"UserSettings/VRChatAgent/ScriptBackups",id,"before.bytes"),"tampered");
        Reject(()=>store.Restore(id,()=>true),"corrupted backup written to source");
        Check(File.ReadAllText(file)=="class AgentEdit {}\n","bad backup mutated source");
    });
    static void ApprovedGateWrite()
    {
        var type=typeof(ScriptWriteCases).Assembly.GetType("Yukino.VRChatAgent.ScriptWriteGate");
        Check(type!=null,"missing final authority for single-file script exception");
        WithFixture((store,root,file)=>
        {
            object gate=Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,
                new object[]{(Func<double>)(()=>10),(Func<string>)(()=>"project"),(Func<string>)(()=>"connection"),
                    (Func<string>)(()=>new string('a',64)),store},null);
            Func<string,string,JObject,JObject> request=(kind,id,body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project",
                ["client_id"]="client",["connection_id"]="connection",["task_id"]="task",["plan_id"]=id,["body"]=body};
            Func<JObject> manifest=()=>new JObject{["target"]="Assets/A.cs",["ttl_seconds"]=60,
                ["effects"]=new JArray("source_import_compile_callbacks")};
            Check((bool) ((JObject)Call(gate,"Dispatch",request("prepare","",manifest())))["success"]==false,"default enabled");
            Call(gate,"SetCapability",true);Call(gate,"SetCompileCapability",true);
            var pending=(JObject)Call(gate,"Dispatch",request("prepare","",manifest()));Check((bool)pending["success"],pending.ToString());
            string id=(string)pending["data"]["plan_id"],digest=(string)pending["data"]["digest"];
            Check((bool)Call(gate,"Approve",id,digest),"exact local approval failed");
            var changed=(JObject)Call(gate,"Dispatch",request("execute",id,new JObject{["content"]="class Changed {}\n"}));
            Check((bool)changed["success"],changed.ToString());
            Check(File.ReadAllText(file)=="class Changed {}\n","approved gate did not write");
            var receipt=(JObject)changed["data"]["transaction"];
            Check((string)receipt["outcome"]=="changed" && (bool)receipt["backup_retained"],"gate lost real transaction");
            Call(gate,"StopAll","local stop");Check(File.ReadAllText(file)=="class Changed {}\n","stop rolled back");
            var denied=(JObject)Call(gate,"Dispatch",request("execute",id,new JObject{["content"]="class Denied {}\n"}));
            Check(!(bool)denied["success"] && File.ReadAllText(file)=="class Changed {}\n","stopped plan wrote");
            var restored=(JObject)Call(gate,"Withdraw",(string)receipt["transaction_id"]);
            Check((bool)restored["success"] && File.ReadAllText(file)=="class A {}\n","local exact-postimage recovery failed");
        });
    }
    static void ReentrantRevocation()=>WithFixture((store,root,file)=>
    {
        Yukino.VRChatAgent.ScriptWriteGate gate=null;int reads=0;
        gate=new Yukino.VRChatAgent.ScriptWriteGate(()=>10,()=>"project",()=>"connection",()=>
        {if(++reads==2)gate.StopAll("fixture revocation during prepare");return new string('a',64);},store);
        gate.SetCapability(true);gate.SetCompileCapability(true);
        var request=new JObject{["protocol"]=1,["kind"]="prepare",["project_id"]="project",["connection_id"]="connection",
            ["client_id"]="client",["task_id"]="task",["plan_id"]="",["body"]=new JObject{["target"]="Assets/A.cs",
                ["ttl_seconds"]=60,["effects"]=new JArray("source_import_compile_callbacks")}};
        var result=gate.Dispatch(request);
        Check(!(bool)result["success"]&&gate.LocalPlans().Count==0,"prepare resurrected a reentrantly revoked plan");
        Check(File.ReadAllText(file)=="class A {}\n","rejected prepare mutated source");
    });
    static void RecoveryRevocation()=>WithFixture((store,root,file)=>
    {
        var receipt=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class Changed {}\n",()=>true);
        Yukino.VRChatAgent.ScriptWriteGate gate=null;int reads=0;
        gate=new Yukino.VRChatAgent.ScriptWriteGate(()=>10,()=>"project",()=>"connection",()=>
        {if(++reads==2)gate.StopAll("fixture revocation during recovery");return new string('a',64);},store);
        gate.SetCapability(true);gate.SetCompileCapability(true);
        var result=gate.Withdraw((string)receipt["transaction_id"]);
        Check(!(bool)result["success"]&&File.ReadAllText(file)=="class Changed {}\n","recovery ignored reentrant revocation");
    });
    static void GateRejections()
    {
        foreach(string scenario in new[]{"unapproved","expired","clock_backwards","connection_changed","plugin_changed","source_changed","compile_revoked","extra_field","foreign_client","stale_stop"})
        WithFixture((store,root,file)=>
        {
            double now=10;string connection="connection",plugin=new string('a',64);
            var gate=new Yukino.VRChatAgent.ScriptWriteGate(()=>now,()=>"project",()=>connection,()=>plugin,store);
            gate.SetCapability(true);gate.SetCompileCapability(true);
            Func<string,string,JObject,JObject> request=(kind,id,body)=>new JObject{["protocol"]=1,["kind"]=kind,["project_id"]="project",
                ["client_id"]="client",["connection_id"]="connection",["task_id"]="task",["plan_id"]=id,["body"]=body};
            Func<JObject> prepare=()=>request("prepare","",new JObject{["target"]="Assets/A.cs",["ttl_seconds"]=60,["effects"]=new JArray("source_import_compile_callbacks")});
            var pending=gate.Dispatch(prepare());Check((bool)pending["success"],pending.ToString());
            string id=(string)pending["data"]["plan_id"],digest=(string)pending["data"]["digest"];
            Check(!gate.Approve(id,new string('0',64)),"wrong approval digest accepted");
            if(scenario!="unapproved")Check(gate.Approve(id,digest),"fixture approval failed");
            var execute=request("execute",id,new JObject{["content"]="class Changed {}\n"});
            if(scenario=="expired")now=70;
            if(scenario=="clock_backwards")now=9;
            if(scenario=="connection_changed")connection="new-connection";
            if(scenario=="plugin_changed")plugin=new string('b',64);
            if(scenario=="source_changed")File.WriteAllText(file,"class UserEdit {}\n");
            if(scenario=="compile_revoked")gate.SetCompileCapability(false);
            if(scenario=="extra_field")execute["body"]["target"]="Assets/Other.cs";
            if(scenario=="foreign_client")execute["client_id"]="other-client";
            if(scenario=="stale_stop")
            {
                var next=gate.Dispatch(prepare());string nextId=(string)next["data"]["plan_id"];
                Check((bool)next["success"]&&gate.Approve(nextId,(string)next["data"]["digest"]),"replacement fixture approval failed");
                Check(!(bool)gate.Dispatch(request("stop",id,new JObject()))["success"],"stale stop accepted");
                Check(gate.LocalPlans().Count==1&&(string)gate.LocalPlans()[0]["plan_id"]==nextId,"stale stop revoked replacement");
            }
            string before=File.ReadAllText(file);var result=gate.Dispatch(execute);
            Check(!(bool)result["success"]&&File.ReadAllText(file)==before,"rejection failed: "+scenario);
            Check(!Directory.Exists(Path.Combine(root,"UserSettings")),"denied operation created backup: "+scenario);
            if(scenario=="foreign_client")Check(gate.LocalPlans().Count==1,"foreign client revoked another plan");
            if(scenario=="stale_stop")Check(gate.LocalPlans().Count==1,"stale execute revoked the replacement plan");
        });
    }
    static void DurableHistory()=>WithFixture((store,root,file)=>
    {
        var method=store.GetType().GetMethod("History",BindingFlags.NonPublic|BindingFlags.Instance);
        Check(method!=null,"missing durable local recovery inventory");
        Check(((JArray)Call(store,"History")).Count==0&&!Directory.Exists(Path.Combine(root,"UserSettings")),"empty history created storage");
        var receipt=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class Changed {}\n",()=>true);
        store=new Yukino.VRChatAgent.ScriptFileStore(root,_=>{});
        var rows=(JArray)Call(store,"History");
        Check(rows.Count==1&&(string)rows[0]["transaction_id"]==(string)receipt["transaction_id"]&&
            (string)rows[0]["outcome"]=="changed"&&(string)rows[0]["target"]=="Assets/A.cs","reload history mismatch");
        Check(File.ReadAllText(file)=="class Changed {}\n","listing performed recovery");
        store.Restore((string)receipt["transaction_id"],()=>true);
        Check((string)((JArray)Call(store,"History"))[0]["outcome"]=="restored","history did not reflect actual recovery");
    });
    static void IncompleteHistory()=>WithFixture((store,root,file)=>
    {
        var receipt=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class Changed {}\n",()=>true);
        string backup=Path.Combine(root,"UserSettings/VRChatAgent/ScriptBackups");
        string missing=Guid.NewGuid().ToString("N"),truncated=Guid.NewGuid().ToString("N");
        Directory.CreateDirectory(Path.Combine(backup,missing));
        Directory.CreateDirectory(Path.Combine(backup,truncated));
        File.WriteAllText(Path.Combine(backup,truncated,"record.json"),"{\"version\":");
        store=new Yukino.VRChatAgent.ScriptFileStore(root,_=>{});
        var rows=store.History();
        Check(rows.Count==3,"incomplete entries hid intact history");
        Check(rows.Single(r=>(string)r["transaction_id"]==(string)receipt["transaction_id"])["outcome"].Value<string>()=="changed","intact history lost");
        foreach(string id in new[]{missing,truncated})
        {
            var row=rows.Single(r=>(string)r["transaction_id"]==id);
            Check((string)row["outcome"]=="unavailable"&&(bool)row["recovery_available"]==false&&row["target"].Type==JTokenType.Null,"damaged entry looked recoverable");
            Reject(()=>store.Restore(id,()=>true),"damaged transaction restored");
        }
        Check(File.ReadAllText(file)=="class Changed {}\n","listing damaged history mutated source");
        Check((string)store.Restore((string)receipt["transaction_id"],()=>true)["outcome"]=="restored","intact transaction inaccessible");
    });
    static void ImmutablePreparedJournal()=>WithFixture((store,root,file)=>
    {
        byte[] prepared=null;string journal=null;int calls=0;
        var receipt=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class Changed {}\n",()=>{
            if(++calls==2)
            {
                journal=Directory.GetFiles(Path.Combine(root,"UserSettings/VRChatAgent/ScriptBackups"),"record.json",SearchOption.AllDirectories).Single();
                prepared=File.ReadAllBytes(journal);
            }
            return true;
        });
        Check(prepared!=null&&File.ReadAllBytes(journal).SequenceEqual(prepared),"write outcome overwrote sole prepared recovery record");
        Check((string)store.History()[0]["outcome"]=="changed","separate write outcome missing");
        store.Restore((string)receipt["transaction_id"],()=>true);
        Check(File.ReadAllBytes(journal).SequenceEqual(prepared),"restore outcome overwrote prepared recovery record");
        Check((string)store.History()[0]["outcome"]=="restored","separate restore outcome missing");
    });
    static void TornOutcomeRecovery()=>WithFixture((store,root,file)=>
    {
        var receipt=store.Write("Assets/A.cs",store.Capture("Assets/A.cs"),"class Changed {}\n",()=>true);
        string id=(string)receipt["transaction_id"],directory=Path.Combine(root,"UserSettings/VRChatAgent/ScriptBackups",id);
        byte[] prepared=File.ReadAllBytes(Path.Combine(directory,"record.json"));
        File.WriteAllText(Path.Combine(directory,"write-result.json"),"{\"version\":");
        store=new Yukino.VRChatAgent.ScriptFileStore(root,_=>{});
        var row=store.History().Single();
        Check((string)row["outcome"]=="unknown"&&(string)row["error"]=="journal_state_unavailable"&&(string)row["target"]=="Assets/A.cs","torn outcome lost prepared evidence or claimed success");
        Reject(()=>store.Restore(id,()=>false),"torn state granted recovery");
        File.WriteAllText(file,"class UserEdit {}\n");Reject(()=>store.Restore(id,()=>true),"torn state bypassed postimage conflict");
        File.WriteAllText(file,"class Changed {}\n");
        Check((string)store.Restore(id,()=>true)["outcome"]=="restored","torn outcome destroyed exact-postimage recovery");
        Check(File.ReadAllText(file)=="class A {}\n"&&File.ReadAllBytes(Path.Combine(directory,"record.json")).SequenceEqual(prepared),"recovery corrupted immutable evidence");
    });
    public static int Main()
    {
        try
        {
            BackupWriteRestore();Console.WriteLine("PASS SW001 durable_backup_write_restore");
            InterruptedJournalRecovery();Console.WriteLine("PASS SW002 interrupted_journal_postimage_recovery");
            ScopeAndEncoding();Console.WriteLine("PASS SW003 scope_encoding_budget");
            EvidenceAndStop();Console.WriteLine("PASS SW004 evidence_and_late_stop");
            RecoveryConflicts();Console.WriteLine("PASS SW005 recovery_conflict_backup_integrity");
            ApprovedGateWrite();Console.WriteLine("PASS SW006 approved_gate_write_stop_withdraw");
            ReentrantRevocation();Console.WriteLine("PASS SW007 prepare_reentrant_stop_no_resurrection");
            RecoveryRevocation();Console.WriteLine("PASS SW008 recovery_reentrant_stop");
            GateRejections();Console.WriteLine("PASS SW009 gate_rejection_matrix");
            DurableHistory();Console.WriteLine("PASS SW010 durable_local_history_no_automatic_restore");
            IncompleteHistory();Console.WriteLine("PASS SW011 incomplete_history_isolated");
            ImmutablePreparedJournal();Console.WriteLine("PASS SW012 prepared_journal_immutable");
            TornOutcomeRecovery();Console.WriteLine("PASS SW013 torn_outcome_preserves_guarded_recovery");
            return 0;
        }
        catch(Exception ex){Console.WriteLine("FAIL "+ex);return 1;}
    }
}
