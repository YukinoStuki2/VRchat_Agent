// Receipt validation is real; context collection/reviewer/UI are explicit doubles.
using System;
using System.Reflection;
using Newtonsoft.Json.Linq;
using Yukino.VRChatAgent;
internal static class AssetReviewCases
{
 static void Check(bool v,string reason){if(!v)throw new Exception(reason);}
 static DateTimeOffset now=DateTimeOffset.Parse("2026-10-08T00:00:00Z");static double monotonic=1;static int invalidations;static Action DuringCapture;
 static JObject context=JObject.Parse("{project_id:'fixture-project',editor:'fixture-editor',candidate_sha256:'"+new string('a',64)+"',code:{'Assets/Editor/Reviewed.cs':'"+new string('b',64)+"'},dependencies:{'Assets/Scope/a.asset':'"+new string('c',64)+"'},callbacks:['fixture.Callback'],complete:true}");
 static object review;
 static object Call(string name,params object[] args)=>review.GetType().GetMethod(name,BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance).Invoke(review,args);
 static JObject Record()=>new JObject{["schema"]=1,["purpose"]="asset_load_callbacks",["target"]="AssetReads/Assets/Scope",["reviewer"]="fixture reviewer, not real review",["reviewed_at_utc"]=now.AddMinutes(-1).ToString("O"),["expires_at_utc"]=now.AddMinutes(10).ToString("O"),["conclusion"]="reviewed",["unassessed_callbacks"]=new JArray(),["context"]=context.DeepClone()};
 static int PipeCase(string mode)
 {
  if(mode=="emit-fixture"){Console.Write(Record().ToString(Newtonsoft.Json.Formatting.None));return 0;}
  Check(mode=="accept-pipe-fixture","unknown fixture mode");
  var local=new AssetCallbackReview(()=>context,()=>now,()=>monotonic,()=>invalidations++);
  var previous=local.StageLocal(Record().ToString());Check(local.ConfirmLocal(previous),"baseline fixture not accepted");
  string digest=local.StageCapturedLocal(()=>{
   Check(local.Evidence("AssetReads/Assets/Scope")==null,"old review not revoked before reading");
   using(var input=Console.OpenStandardInput())using(var memory=new System.IO.MemoryStream())
   {var buffer=new byte[8192];int count;while((count=input.Read(buffer,0,Math.Min(buffer.Length,262145-(int)memory.Length)))>0){memory.Write(buffer,0,count);if(memory.Length>262144)break;}return memory.ToArray();}
  });
  if(digest==null){Check(local.Evidence("AssetReads/Assets/Scope")==null,"invalid import retained authority");Console.Write("REFUSED");return 2;}
  Check(local.Evidence("AssetReads/Assets/Scope")==null,"pipe implicitly approved review");
  Check(local.ConfirmLocal(digest) && local.Evidence("AssetReads/Assets/Scope")==digest,"separate fixture confirmation failed");
  Console.Write("STAGED_THEN_SEPARATELY_CONFIRMED");return 0;
 }
 static int Main(string[] args){try{
  if(args.Length==1)return PipeCase(args[0]);
  var type=typeof(CandidateGate).Assembly.GetType("Yukino.VRChatAgent.AssetCallbackReview");
  Check(type!=null,"local_review_record_validator_missing");
  review=Activator.CreateInstance(type,BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic,null,new object[]{(Func<JObject>)(()=>{DuringCapture?.Invoke();return context;}),(Func<DateTimeOffset>)(()=>now),(Func<double>)(()=>monotonic),(Action)(()=>invalidations++)},null);
  Check(Call("Evidence","AssetReads/Assets/Scope")==null,"empty review grants evidence");
  string digest=(string)Call("StageLocal",Record().ToString());Check(!string.IsNullOrEmpty(digest),"valid record not staged");
  Check(Call("Evidence","AssetReads/Assets/Scope")==null,"staging granted authority");
  Check(!(bool)Call("ConfirmLocal",new string('f',64)),"wrong local digest confirmed");
  digest=(string)Call("StageLocal",Record().ToString());
  Check((bool)Call("ConfirmLocal",digest),"exact local record not confirmed");
  Check((string)Call("Evidence","AssetReads/Assets/Scope")==digest,"confirmed record did not bind evidence");
  Check(Call("Evidence","AssetReads/Assets/Other")==null,"record escaped exact target");
  Console.WriteLine("PASS AR001 stage_is_inert_confirmation_binds_exact_record_and_target");
  var originalContext=(JObject)context.DeepClone();
  foreach(var bad in new[]{"unknown-key","schema-bool","invalid-hash","missing-reviewer","blank-reviewer","unknown-callback","incomplete","target-traversal","duplicate-json","empty-code","duplicate-callback","context-mismatch","expired","future"})
  {
   context=(JObject)originalContext.DeepClone();
   if(bad=="invalid-hash")context["code"]["Assets/Editor/Reviewed.cs"]="not-a-sha256";
   if(bad=="incomplete")context["complete"]=false;
   if(bad=="empty-code")context["code"]=new JObject();
   if(bad=="duplicate-callback")((JArray)context["callbacks"]).Add("fixture.Callback");
   var record=Record();
   if(bad=="unknown-key")record["allow_any_callback"]=true;
   if(bad=="schema-bool")record["schema"]=true;
   if(bad=="missing-reviewer")record.Remove("reviewer");if(bad=="blank-reviewer")record["reviewer"]="";
   if(bad=="unknown-callback")((JArray)record["unassessed_callbacks"]).Add("unreviewed.Callback");
   if(bad=="target-traversal")record["target"]="AssetReads/Assets/Scope/../Other";
   if(bad=="context-mismatch")record["context"]["project_id"]="another-project";
   if(bad=="expired")record["expires_at_utc"]=now.AddMinutes(-2).ToString("O");
   if(bad=="future")record["reviewed_at_utc"]=now.AddMinutes(1).ToString("O");
   string json=record.ToString(Newtonsoft.Json.Formatting.None);
   if(bad=="duplicate-json")json="{\"conclusion\":\"unreviewed\","+json.Substring(1);
   Check(Call("StageLocal",json)==null && Call("Evidence","AssetReads/Assets/Scope")==null,"invalid record accepted: "+bad);
  }
  context=originalContext;
  Console.WriteLine("PASS AR002 malformed_incomplete_unassessed_and_mismatched_records_denied");
  foreach(var changed in new[]{"code","dependencies","project_id","editor","candidate_sha256","callbacks","complete"})
  {
   context=(JObject)originalContext.DeepClone();digest=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",digest),"context fixture approval failed");
   if(changed=="code")context["code"]["Assets/Editor/Reviewed.cs"]=new string('d',64);
   else if(changed=="dependencies")context["dependencies"]["Assets/Scope/a.asset"]=new string('d',64);
   else if(changed=="callbacks")((JArray)context["callbacks"]).Add("unknown.Callback");
   else if(changed=="complete")context["complete"]=false;
   else context[changed]=changed=="candidate_sha256"?new string('e',64):"changed";
   Check(Call("Evidence","AssetReads/Assets/Scope")==null,"changed context trusted: "+changed);
   context=(JObject)originalContext.DeepClone();Check(Call("Evidence","AssetReads/Assets/Scope")==null,"restoring old context revived record");
  }
  foreach(var clockFailure in new[]{"mono-back","utc-back","expired","nonfinite"})
  {
   monotonic+=10;double savedMono=monotonic;digest=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",digest),"clock fixture approval failed");
   var savedNow=now;
   if(clockFailure=="mono-back")monotonic=savedMono-1;if(clockFailure=="utc-back")now=now.AddSeconds(-10);if(clockFailure=="expired")monotonic=savedMono+10000;if(clockFailure=="nonfinite")monotonic=double.NaN;
   Check(Call("Evidence","AssetReads/Assets/Scope")==null,"unsafe clock accepted: "+clockFailure);
   monotonic=savedMono+20000;now=savedNow.AddMinutes(1);Check(Call("Evidence","AssetReads/Assets/Scope")==null,"restored clock revived record");
  }
  Console.WriteLine("PASS AR003 context_and_clock_changes_revoke_without_revival");
  context=(JObject)originalContext.DeepClone();
  foreach(var phase in new[]{"stage","confirm","evidence"})
  foreach(var reentry in new[]{"revoke","replacement"})
  {
   DuringCapture=null;digest=(string)Call("StageLocal",Record().ToString());
   if(phase=="evidence")Check((bool)Call("ConfirmLocal",digest),"reentry fixture approval failed");
   DuringCapture=()=>{DuringCapture=null;if(reentry=="revoke")Call("Revoke");else{string nested=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",nested),"nested replacement fixture failed");}};
   if(phase=="stage")Check(Call("StageLocal",Record().ToString())==null,"stage restored record after callback revocation");
   if(phase=="confirm")Check(!(bool)Call("ConfirmLocal",digest),"confirm ignored callback revocation");
   if(phase=="evidence")Check(Call("Evidence","AssetReads/Assets/Scope")==null,"evidence ignored callback revocation");
   DuringCapture=null;Check(Call("Evidence","AssetReads/Assets/Scope")==null,"record revived after callback revocation");
  }
  Console.WriteLine("PASS AR004 reentrant_revocation_cannot_restore_review");
  var holder=(AssetCallbackReview)review;string connection="c";int assetCalls=0;
  var gate=new CandidateGate(()=>monotonic,()=>"p",()=>connection,t=>{throw new Exception("generic evidence called");},(c,a)=>{throw new Exception("generic native called");},holder.Evidence,(a,ticket)=>{Check(ticket(),"gate ticket invalid");assetCalls++;return JObject.Parse("{success:true,data:{}} ");});
  JObject PrepareWire()=>new JObject{["protocol"]=1,["kind"]="prepare",["project_id"]="p",["connection_id"]=connection,["client_id"]="client",["task_id"]="task",["plan_id"]="",["body"]=JObject.Parse("{operations:[{command:'manage_asset',action:'search'}],targets:['AssetReads/Assets/Scope'],ttl_seconds:60,effects:[{kind:'asset_load_callbacks',version:1}]}")};
  JObject ExecuteWire(JObject plan){var req=PrepareWire();req["kind"]="execute";req["plan_id"]=plan["data"]["plan_id"].DeepClone();req["body"]=JObject.Parse("{command:'manage_asset',params:{action:'search',path:'Assets/Scope',pageSize:1,pageNumber:1,generatePreview:false}}");return req;}
  digest=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",digest),"review-only fixture failed");
  Check(!gate.AssetCallbacksAllowed && !(bool)gate.Dispatch(PrepareWire())["success"] && assetCalls==0,"review auto-enabled capabilities");
  gate.SetAssetCallbacks(true);gate.SetCapability("manage_asset","search",true);
  var plan=gate.Dispatch(PrepareWire());Check((bool)plan["success"] && !(bool)gate.Dispatch(ExecuteWire(plan))["success"] && assetCalls==0,"review auto-approved task");
  plan=gate.Dispatch(PrepareWire());Check(gate.Approve((string)plan["data"]["plan_id"],(string)plan["data"]["digest"]),"task approval failed");
  Check((bool)gate.Dispatch(ExecuteWire(plan))["success"] && assetCalls==1,"separate task approval failed");
  Call("Revoke");Check(!(bool)gate.Dispatch(ExecuteWire(plan))["success"] && assetCalls==1,"revoked review still authorized loads");
  digest=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",digest),"replacement review failed");
  Check(!(bool)gate.Dispatch(ExecuteWire(plan))["success"] && assetCalls==1,"replacement review revived stopped plan");
  Console.WriteLine("PASS AR005 confirmed_review_never_enables_or_approves_task");
  Check(type.GetMethod("StageCapturedLocal",BindingFlags.NonPublic|BindingFlags.Instance)!=null,"bounded_local_capture_handoff_missing");
  var validBytes=System.Text.Encoding.UTF8.GetBytes(Record().ToString());
  foreach(var failure in new[]{"null","empty","oversize","encoding","bom","throw","revoked","bad-json","replaced-review"})
  {
   digest=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",digest),"import fixture approval failed");
   int reads=0;Func<byte[]> capture=()=>{reads++;Check(Call("Evidence","AssetReads/Assets/Scope")==null,"old record remained live during import");
    if(failure=="null")return null;if(failure=="empty")return new byte[0];if(failure=="oversize")return new byte[262145];
    if(failure=="encoding")return new byte[]{0xff};if(failure=="bom")return new byte[]{0xef,0xbb,0xbf,0x7b,0x7d};
    if(failure=="throw")throw new Exception("fixture private path, must not escape");if(failure=="revoked")Call("Revoke");
    if(failure=="replaced-review"){string nested=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",nested),"replacement fixture failed");}
    if(failure=="bad-json")return System.Text.Encoding.UTF8.GetBytes("{bad-json");return validBytes;};
   Check(Call("StageCapturedLocal",capture)==null,"unsafe local capture accepted: "+failure);
   Check(reads==1 && Call("Evidence","AssetReads/Assets/Scope")==null,"failed import retained review");
   Check(!(bool)Call("ConfirmLocal",digest),"old pending digest survived failed import");
  }
  digest=(string)Call("StageCapturedLocal",(Func<byte[]>)(()=>validBytes));
  Check(!string.IsNullOrEmpty(digest) && Call("Evidence","AssetReads/Assets/Scope")==null,"capture granted authority or failed");
  Check((bool)Call("ConfirmLocal",digest),"valid captured record not confirmable");
  Console.WriteLine("PASS AR006 bounded_capture_revokes_before_read_and_never_auto_confirms");
  Check(type.GetMethod("StageCapturedLocalAsync",BindingFlags.NonPublic|BindingFlags.Instance)!=null,"async_local_capture_handoff_missing");
  foreach(var interrupted in new[]{"none","revoke","replacement","fault","cancel"})
  {
   digest=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",digest),"async fixture approval failed");
   var completion=new System.Threading.Tasks.TaskCompletionSource<byte[]>();
   int reads=0;
   Func<System.Threading.Tasks.Task<byte[]>> capture=()=>{reads++;Check(Call("Evidence","AssetReads/Assets/Scope")==null,"old review survived async capture start");return completion.Task;};
   var pending=(System.Threading.Tasks.Task<string>)Call("StageCapturedLocalAsync",capture);
   Check(reads==1 && !pending.IsCompleted,"capture was not awaited");
   if(interrupted=="revoke")Call("Revoke");
   if(interrupted=="replacement"){string nested=(string)Call("StageLocal",Record().ToString());Check((bool)Call("ConfirmLocal",nested),"async replacement fixture failed");}
   if(interrupted=="fault")completion.SetException(new Exception("private content must not escape"));
   else if(interrupted=="cancel")completion.SetCanceled();
   else completion.SetResult(validBytes);
   string staged=pending.GetAwaiter().GetResult();
   Check(Call("Evidence","AssetReads/Assets/Scope")==null,"async capture granted or retained authority");
   if(interrupted=="none")Check(staged!=null && (bool)Call("ConfirmLocal",staged),"async valid record not confirmable");
   else Check(staged==null,"async interruption restored record: "+interrupted);
  }
  Console.WriteLine("PASS AR008 async_capture_revokes_before_await_and_rejects_stale_completion");
  return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
