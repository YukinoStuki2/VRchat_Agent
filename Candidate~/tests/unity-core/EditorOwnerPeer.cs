// Actual C#->Python private pipes/TLS/SDK/gate, explicit Unity API doubles.
using System;
using System.IO;
using System.Threading.Tasks;
using Yukino.VRChatAgent;
using UnityEngine;
internal static class EditorOwnerPeer
{
 static async Task<int> Main(string[] args)
 {
  Directory.SetCurrentDirectory(args[2]);Application.dataPath=Path.Combine(args[2],"Assets");
  using(var owner=new EditorOwnerProcess())
  {
   if(!await owner.StartAsync(args[0],args[1],"fixture-project",CandidateSession.ConnectOwnedAsync,CandidateSession.StopOwnedAsync))return 3;
   if(!owner.Ready || CandidateSession.LiveConnection()=="")return 4;
   // Binding does not enable capabilities or create/approve a plan.
   if(CandidateSession.Gate.Allows("manage_material","get_material_info") || CandidateSession.Gate.LocalPlans().Count!=0)return 5;
   Console.WriteLine("private_editor_ready");Console.Out.Flush();
   await owner.StopAsync();
   if(owner.Ready || !owner.CleanupComplete || CandidateSession.LiveConnection()!="")return 6;
   Console.WriteLine("private_editor_clean");Console.Out.Flush();
  }
  UnityEditor.PackageManager.PackageInfo.TestRoot=args[3];
  if(CandidateSession.HasLocalOwner || CandidateSession.LocalOwnerReady)return 7;
  var window=new CandidateWindow();
  var draw=typeof(CandidateWindow).GetMethod("OnGUI",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic);
  UnityEditor.EditorGUILayout.NextText=args[0];draw.Invoke(window,null);
  if(CandidateSession.HasLocalOwner)return 13;
  GUILayout.NextButton="启动本地受控连接";draw.Invoke(window,null);
  var deadline=System.Diagnostics.Stopwatch.StartNew();
  while(!CandidateSession.LocalOwnerReady && deadline.Elapsed.TotalSeconds<15)await Task.Delay(25);
  if(!CandidateSession.LocalOwnerReady)return 8;
  if(await CandidateSession.StartLocalOwnerAsync(args[0]))return 9;
  GUILayout.NextButton="停止连接并撤权（不回退）";draw.Invoke(window,null);
  deadline.Restart();
  while(CandidateSession.HasLocalOwner && deadline.Elapsed.TotalSeconds<15)await Task.Delay(25);
  if(CandidateSession.HasLocalOwner || CandidateSession.LocalOwnerReady || CandidateSession.LiveConnection()!="")return 10;
  if(!await CandidateSession.StartLocalOwnerAsync(args[0]))return 11;
  UnityEditor.AssemblyReloadEvents.Reload();
  if(CandidateSession.LocalOwnerReady || CandidateSession.LiveConnection()!="")return 12;
  Console.WriteLine("local_controller_explicit_start_stop_reload");return 0;
 }
}
