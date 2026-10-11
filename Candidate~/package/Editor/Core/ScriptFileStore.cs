using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Yukino.VRChatAgent
{
    // Existing single-file exception only. No Unity APIs, imports, compilation,
    // arbitrary execution, source creation, remote recovery or automatic rollback.
    // The Windows sharing contract is intentional; other hosts fail closed unless
    // an internal test supplies an explicitly labelled handle-identity double.
    internal sealed class ScriptFileStore
    {
        internal const int Budget=131072;
        readonly string root;
        readonly Action<FileStream> inspectHandle;
        static readonly UTF8Encoding Utf8=new UTF8Encoding(false,true);
        internal ScriptFileStore(string root,Action<FileStream> inspectHandle=null)
        {if(inspectHandle==null)ScriptPathLease.ValidatePath(root);this.root=Path.GetFullPath(root);this.inspectHandle=inspectHandle;}
        static void Need(bool ok,string code){if(!ok)throw new CandidateWriteDenied(code);}
        internal static string Hash(byte[] value)
        {using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(value)).Replace("-","").ToLowerInvariant();}
        static bool IsHash(JToken value)=>value?.Type==JTokenType.String && ((string)value).Length==64 && ((string)value).All(c=>"0123456789abcdef".Contains(c));
        internal static string Target(string target)
        {
            MaterialCandidateGate.AssetPath(target);
            Need(target.EndsWith(".cs",StringComparison.Ordinal)||target.EndsWith(".shader",StringComparison.Ordinal),"script_extension_required");
            foreach(string part in target.Split('/'))
            {
                string name=part.Split('.')[0].ToUpperInvariant();
                Need(!(new[]{"CON","PRN","AUX","NUL","CONIN$","CONOUT$"}).Contains(name) &&
                    !(name.Length==4 && (name.StartsWith("COM",StringComparison.Ordinal)||name.StartsWith("LPT",StringComparison.Ordinal)) && "123456789¹²³".Contains(name[3])),"reserved_path");
            }
            return target;
        }
        void Chain(string full)
        {
            // Attribute errors deny. Root ancestors are checked too; no catch-and-proceed.
            Need(full==root||full.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.Ordinal),"outside_project");
            for(string p=full;!string.IsNullOrEmpty(p);p=Path.GetDirectoryName(p))
                Need((File.GetAttributes(p)&FileAttributes.ReparsePoint)==0,"reparse_unsupported");
        }
        string Full(string target){Target(target);string full=Path.GetFullPath(Path.Combine(root,target));Chain(full);return full;}
        FileStream Open(string full,bool write,int budget)
        {
            Chain(full);
            var stream=inspectHandle==null?ScriptPathLease.Open(full,write):
                new FileStream(full,FileMode.Open,write?FileAccess.ReadWrite:FileAccess.Read,write?FileShare.None:FileShare.Read);
            try{inspectHandle?.Invoke(stream);Need(stream.Length<=budget,"source_budget");Chain(full);return stream;}
            catch{stream.Dispose();throw;}
        }
        static byte[] Read(FileStream stream,int budget)
        {
            string stamp=ScriptPathLease.Stamp(stream);Need(stream.Length<=budget,"source_budget");stream.Position=0;
            byte[] bytes=new byte[(int)stream.Length];int offset=0,count;
            while(offset<bytes.Length && (count=stream.Read(bytes,offset,bytes.Length-offset))>0)offset+=count;
            Need(offset==bytes.Length && stream.ReadByte()==-1 && stamp==ScriptPathLease.Stamp(stream),"source_changed");return bytes;
        }
        static JObject Snapshot(byte[] source,byte[] meta)=>new JObject{["sha256"]=Hash(source),["meta_sha256"]=Hash(meta)};
        internal JObject Capture(string target)
        {
            string full=Full(target);
            using(var source=Open(full,false,Budget))using(var meta=Open(full+".meta",false,1048576))
                return Snapshot(Read(source,Budget),Read(meta,1048576));
        }
        string BackupRoot=>Path.Combine(root,"UserSettings","VRChatAgent","ScriptBackups");
        IDisposable HoldDirectory(string path,bool create=false)
        {if(inspectHandle==null)return ScriptPathLease.Directory(path,create);if(create)Directory.CreateDirectory(path);Chain(path);return null;}
        void CreateBackupRoot()
        {
            string p=root;Chain(p);
            foreach(string part in new[]{"UserSettings","VRChatAgent","ScriptBackups"})
            {p=Path.Combine(p,part);if(!Directory.Exists(p))Directory.CreateDirectory(p);Chain(p);}
            Need(Directory.EnumerateFileSystemEntries(p).Take(129).Count()<128,"backup_capacity");
        }
        static string Transaction(string id)
        {Need(Guid.TryParseExact(id,"N",out _),"invalid_transaction");return id;}
        void SaveNew(string path,byte[] bytes)
        {
            Chain(Path.GetDirectoryName(path));
            using(var s=inspectHandle==null?ScriptPathLease.Open(path,true,true):new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None))
            {inspectHandle?.Invoke(s);s.Write(bytes,0,bytes.Length);s.Flush(true);ScriptPathLease.Stamp(s);}
            Chain(path);
        }
        void SaveRecord(string path,JObject record)
        {
            var persisted=(JObject)record.DeepClone();persisted.Remove("journal_error");
            byte[] bytes=Utf8.GetBytes(persisted.ToString(Formatting.None));Need(bytes.Length<=8192,"record_budget");
            SaveNew(path,bytes); // Immutable: outcome writes never destroy prepared recovery data.
        }
        static byte[] Replacement(byte[] before,string content)
        {
            Need(content!=null && content.Length<=Budget && content.IndexOf('\0')<0,"invalid_source_text");
            // Decode the old bytes strictly; never guess a legacy encoding.
            bool bom=before.Length>=3 && before[0]==239 && before[1]==187 && before[2]==191;
            Utf8.GetString(before,bom?3:0,before.Length-(bom?3:0));
            byte[] encoded=Utf8.GetBytes(content);
            Need(!(encoded.Length>=3 && encoded[0]==239 && encoded[1]==187 && encoded[2]==191),"content_bom_not_allowed");
            byte[] result=bom?new byte[]{239,187,191}.Concat(encoded).ToArray():encoded;
            Need(result.Length<=Budget,"source_budget");return result;
        }
        static void WriteHeld(FileStream source,byte[] bytes)
        {ScriptPathLease.Stamp(source);source.Position=0;source.Write(bytes,0,bytes.Length);source.SetLength(bytes.Length);source.Flush(true);ScriptPathLease.Stamp(source);}
        JObject Result(JObject record,string outcome,string error=null)=>new JObject{
            ["transaction_id"]=record["id"],["target"]=record["target"],["outcome"]=outcome,["error"]=(error??(string)record["journal_error"])==null?JValue.CreateNull():new JValue(error??(string)record["journal_error"]),
            ["before_sha256"]=record["before"],["expected_after_sha256"]=record["after"],
            ["meta_sha256"]=record["meta"],["backup_retained"]=true,["import_requested"]=false};
        internal JObject Write(string target,JObject expected,string content,Func<bool> authorized)
        {
            string full=Full(target);
            using(var source=Open(full,true,Budget))using(var meta=Open(full+".meta",false,1048576))
            {
                byte[] before=Read(source,Budget),metaBytes=Read(meta,1048576);
                Need(JToken.DeepEquals(expected,Snapshot(before,metaBytes)),"relevant_evidence_changed");
                byte[] after=Replacement(before,content);Need(!before.SequenceEqual(after),"no_change");
                Need(authorized!=null && authorized(),"plan_revoked");
                using var backupRoot=HoldDirectory(BackupRoot,true);CreateBackupRoot();
                string id=Guid.NewGuid().ToString("N"),directory=Path.Combine(BackupRoot,id);
                using var backupDirectory=HoldDirectory(directory,true);
                SaveNew(Path.Combine(directory,"before.bytes"),before);
                var record=new JObject{["version"]=1,["id"]=id,["project"]=Hash(Utf8.GetBytes(root)),["target"]=target,
                    ["before"]=Hash(before),["after"]=Hash(after),["meta"]=Hash(metaBytes),["state"]="prepared"};
                string receipt=Path.Combine(directory,"record.json");SaveRecord(receipt,record);
                bool entered=false;string outcome="unchanged",error=null;
                try
                {
                    Chain(full);Need(JToken.DeepEquals(expected,Snapshot(Read(source,Budget),Read(meta,1048576))),"relevant_evidence_changed");
                    Need(authorized(),"plan_revoked");entered=true;WriteHeld(source,after);
                    Need(Read(source,Budget).SequenceEqual(after),"write_readback_mismatch");outcome="changed";
                }
                catch(Exception ex){outcome=entered?"unknown":"unchanged";error=ex is CandidateWriteDenied?ex.Message:"write_state_unknown";}
                record["state"]=outcome;
                try{SaveRecord(Path.Combine(directory,"write-result.json"),record);}catch{error="journal_update_failed";}
                return Result(record,outcome,error);
            }
        }
        JObject ReadRecord(string id,string name)
        {
            string path=Path.Combine(BackupRoot,Transaction(id),name);JObject record;
            using(var s=Open(path,false,8192))
            using(var reader=new JsonTextReader(new StringReader(Utf8.GetString(Read(s,8192)))){MaxDepth=4})
            {record=JObject.Load(reader,new JsonLoadSettings{DuplicatePropertyNameHandling=DuplicatePropertyNameHandling.Error});Need(!reader.Read(),"invalid_record");}
            string[] keys={"version","id","project","target","before","after","meta","state"};
            Need(record.Count==keys.Length && record.Properties().All(p=>keys.Contains(p.Name)) && record["version"]?.Type==JTokenType.Integer && (int)record["version"]==1 &&
                (string)record["id"]==id && (string)record["project"]==Hash(Utf8.GetBytes(root)) && IsHash(record["before"]) && IsHash(record["after"]) && IsHash(record["meta"]) &&
                record["target"]?.Type==JTokenType.String && record["state"]?.Type==JTokenType.String,"invalid_record");
            Target((string)record["target"]);return record;
        }
        JObject Record(string id)
        {
            var record=ReadRecord(id,"record.json");
            foreach(string name in new[]{"write-result.json","restore-result.json"})
            {
                try
                {
                    JObject next;
                    try{next=ReadRecord(id,name);}
                    catch(FileNotFoundException){continue;}
                    string state=(string)next["state"];
                    Need((name=="write-result.json"?new[]{"changed","unknown","unchanged"}:new[]{"restored"}).Contains(state),"invalid_record");
                    var original=(JObject)record.DeepClone();original["state"]=state;
                    Need(JToken.DeepEquals(original,next),"outcome_record_mismatch");record=next;
                }
                catch(Exception)
                {
                    // Only optional outcome state is uncertain. The validated
                    // immutable record and exact-postimage recovery checks remain.
                    record["state"]="unknown";record["journal_error"]="journal_state_unavailable";return record;
                }
            }
            return record;
        }
        internal JArray History()
        {
            // Local UI inventory only; listing never restores grants or bytes.
            if(!Directory.Exists(BackupRoot))return new JArray();
            using var directory=HoldDirectory(BackupRoot);
            var paths=Directory.EnumerateFileSystemEntries(BackupRoot).Take(129).ToArray();
            Need(paths.Length<=128,"backup_capacity");var rows=new JArray();
            foreach(string path in paths.OrderBy(p=>p,StringComparer.Ordinal))
            {
                string id=Transaction(Path.GetFileName(path));
                try
                {
                    using var transaction=HoldDirectory(path);
                    var record=Record(id);string state=(string)record["state"];
                    Need(new[]{"prepared","changed","unknown","unchanged","restored"}.Contains(state),"invalid_record");
                    rows.Add(Result(record,state));
                }
                catch(Exception)
                {
                    // An interrupted preparation must not hide other transactions.
                    // No inferred target, backup integrity, or recovery authority.
                    rows.Add(new JObject{["transaction_id"]=id,["target"]=JValue.CreateNull(),
                        ["outcome"]="unavailable",["error"]="transaction_record_unavailable",
                        ["recovery_available"]=false,["backup_retained"]=JValue.CreateNull(),["import_requested"]=false});
                }
            }
            return rows;
        }
        internal JObject Restore(string id,Func<bool> authorized)
        {
            // Local operator only. A fresh caller may recover after reload, but this
            // never restores an editing grant. A damaged journal fails closed.
            // A crash can leave "prepared" after the source was flushed. Recovery
            // still requires the exact intended postimage and an explicit local act.
            using var directory=HoldDirectory(Path.Combine(BackupRoot,Transaction(id)));
            var record=Record(id);Need(new[]{"prepared","changed","unknown"}.Contains((string)record["state"]),"transaction_not_restorable");
            byte[] before;
            using(var s=Open(Path.Combine(BackupRoot,id,"before.bytes"),false,Budget))before=Read(s,Budget);
            Need(Hash(before)==(string)record["before"],"backup_changed");
            string full=Full((string)record["target"]);
            using(var source=Open(full,true,Budget))using(var meta=Open(full+".meta",false,1048576))
            {
                Need(Hash(Read(source,Budget))==(string)record["after"] && Hash(Read(meta,1048576))==(string)record["meta"],"postimage_conflict");
                Need(authorized!=null && authorized(),"local_recovery_required");
                string outcome="unknown",error=null;
                try{WriteHeld(source,before);Need(Read(source,Budget).SequenceEqual(before),"restore_readback_mismatch");outcome="restored";}
                catch(Exception ex){error=ex is CandidateWriteDenied?ex.Message:"restore_state_unknown";}
                if(outcome=="restored")record["state"]="restored";
                try{if(outcome=="restored")SaveRecord(Path.Combine(BackupRoot,id,"restore-result.json"),record);}catch{error="journal_update_failed";}
                return Result(record,outcome,error);
            }
        }
    }
}
