using System;
using Yukino.VRChatAgentLauncher;
static class RecoveryTests
{
    static void Require(bool value,string message){if(!value)throw new Exception("Recovery: "+message);}
    public static void Run()
    {
        var r=new RecoveryState();
        Require(!r.BeginPause(1,"P"),"cold state must not arm");
        r.Remember(false,"P","settings");r.Connected();Require(!r.BeginPause(1,"P"),"default off");
        r.Remember(true,"P","settings");Require(!r.BeginPause(1,"P"),"unconnected manual run not eligible");
        r.Connected();Require(r.BeginPause(1,"P"),"explicit connected run eligible");
        Require(!r.Ready(2,"P",true,true,true),"compiling");
        Require(!r.Ready(3,"P",false,false,true),"no cleanup proof");
        Require(!r.Ready(4,"P",false,true,false),"window absent");
        Require(!r.Ready(5,"P",false,true,true),"quiet timer start");
        Require(!r.Ready(9,"P",false,true,true),"quiet time insufficient");
        Require(r.Ready(10,"P",false,true,true),"ready after 5 quiet seconds");
        Require(r.Consume()=="settings" && !r.Waiting,"one-shot consume");
        Require(r.Consume()==null,"cannot retry same pause");
        Require(!r.BeginPause(11,"P"),"failed recovery cannot rearm without connected proof");
        r.Connected();Require(r.BeginPause(12,"P"),"later import permitted after success");
        r.Ready(13,"OTHER",false,true,true);Require(!r.Allowed && !r.Waiting,"project mismatch cancels");
        r.Remember(true,"P","settings");r.Connected();r.BeginPause(1,"P");
        Require(!r.Ready(182,"P",false,true,true) && !r.Allowed,"expired ticket");
        r.Remember(true,"P","settings");r.Connected();r.BeginPause(1,"P");r.Cancel();
        Require(!r.Ready(10,"P",false,true,true) && r.Consume()==null,"manual close/stop cancels");
        r.Remember(true,"P","settings");r.Connected();r.BeginPause(1,"P");
        var copy=UnityEngine.JsonUtility.FromJson<RecoveryState>(UnityEngine.JsonUtility.ToJson(r));
        Require(copy.Waiting && copy.Project=="P","reload state survives without granting permission");
        Require(!new LauncherSettings().autoRecoverAfterImport,"setting must default off");
        Console.WriteLine("PASS recovery state: default-off/manual intent/same-project/quiet delay/cleanup/window/deadline/one-shot/cancel/reload serialization.");
    }
}
