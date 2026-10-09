using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Services;
using MCPForUnity.Editor.Services.Transport;
using WebSocketTransportClient = MCPForUnity.Editor.Services.Transport.Transports.CandidateOwnedWebSocketTransportClient;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgent
{
    [InitializeOnLoad]
    internal static class CandidateSession
    {
        // Explicit local trust premise, not a claim to attest executed code.
        internal static readonly ProjectPluginTrust Plugins = new ProjectPluginTrust(
            PluginContext, () => Gate?.StopAll("工程插件信任已失效；重新本地核对，不回退作用"));
        static string PluginContext()
        {
            if(localStop!=null||ownedRevoked)return null;
            string connection=LiveConnection();
            if(string.IsNullOrEmpty(connection))return null;
            string directory=Directory.GetParent(Application.dataPath).FullName;
            var context=new StringBuilder();
            Action<string> add=value=>context.Append(value.Length).Append(':').Append(value);
            add(CoplayProjectIdentity.GetProjectHash());add(connection);add(Application.unityVersion);
            add(HashFile(Path.Combine(directory,"Packages/manifest.json"),1048576));
            add(HashFile(Path.Combine(directory,"Packages/packages-lock.json"),1048576));
            var assemblies=AppDomain.CurrentDomain.GetAssemblies();
            if(assemblies.Length>4096)return null;
            foreach(var identity in assemblies.Select(a=>a.FullName+"|"+a.ManifestModule.ModuleVersionId.ToString("D")).OrderBy(x=>x,StringComparer.Ordinal))add(identity);
            // Inventory/hash changes revoke; this is NOT exhaustive callback or
            // in-memory code integrity detection. Approved plugins are trusted.
            return ProjectPluginTrust.Digest(context.ToString());
        }
        // No process startup, EditorPrefs writes, or persistent approval on import.
        internal static readonly CandidateGate Gate = new CandidateGate(
            () => EditorApplication.timeSinceStartup, CoplayProjectIdentity.GetProjectHash,
            LiveConnection, Evidence, NativeRead,
            target => Plugins.Evidence("asset_load_callbacks",target), ReadAsset,
            (action,target) => Plugins.Evidence(action=="get_hierarchy"?"prefab_contents_callbacks":"asset_load_callbacks",target),
            MCPForUnity.Editor.Tools.Prefabs.CandidateScopedPrefabs.Read,
            target => Plugins.Evidence("test_discovery_callbacks",target), ReadDiscovery,
            new EffectCleanupLedger(
                kind => SessionState.GetString("Yukino.VRChatAgent.EffectCleanup.v1."+kind,""),
                (kind,value) => SessionState.SetString("Yukino.VRChatAgent.EffectCleanup.v1."+kind,value)));
        static CandidateSession()
        {
            EditorApplication.update += Plugins.Observe;
            EditorApplication.update += Gate.Observe;
            EditorApplication.quitting += Revoke;
            AssemblyReloadEvents.beforeAssemblyReload += () => {
#if UNITY_EDITOR
                if (CandidateReload.BeforeReload()) return;
#endif
                Revoke();
            };
            EditorApplication.playModeStateChanged += _ => Revoke();
        }
        static EditorOwnerProcess localOwner;
        static Task localStop;
        internal static bool HasLocalOwner => localOwner != null;
#if UNITY_EDITOR
        internal static EditorOwnerProcess LocalOwner => localOwner;
        internal static bool AdoptReloadOwner(EditorOwnerProcess owner)
        {
            if (localOwner != null || ownedClient != null || owner == null) return false;
            localOwner = owner; localStop = null;
            LocalOwnerStatus = "核验原owner中；任务权限尚未恢复";
            return true;
        }
        internal static void ReloadStatus(string value) { LocalOwnerStatus = value; }
#endif
        internal static bool LocalOwnerReady => localOwner != null && localOwner.Ready && LiveConnection() != "";
        internal static string LocalOwnerStatus { get; private set; } = "未启动";
        internal static async Task<bool> StartLocalOwnerAsync(string python = null, bool allowHermes = false, bool allowCodex = false, JObject hermesSsh = null, string codexExecutable = null, bool enableReloadControl = false)
        {
            if (localOwner != null || ownedClient != null || EditorApplication.isCompiling ||
                EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode) return false;
            var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(CandidateSession).Assembly);
            string entry = package == null ? "" : Path.Combine(package.resolvedPath, "Runtime~", "launcher", "editor_owner.py");
            if (python == null)
            {
                try { python = EditorOwnerProcess.ResolvePortablePython(package?.resolvedPath); }
                catch { LocalOwnerStatus = "随包运行时缺失、不匹配或入口校验失败；未启动且不回退本机Python"; return false; }
            }
            if (!Path.IsPathRooted(python) || !File.Exists(python) || !File.Exists(entry))
            { LocalOwnerStatus = "固定运行时或Python缺失，未启动"; return false; }
            var owner = new EditorOwnerProcess(); localOwner = owner; localStop = null;
            LocalOwnerStatus = "正在通过私有管道绑定；没有授予任务权限";
            bool ready = await owner.StartAsync(python, entry, CoplayProjectIdentity.GetProjectHash(), ConnectOwnedAsync, StopOwnedAsync, allowHermes, allowCodex, hermesSsh, codexExecutable, codexExecutable == null ? null : Path.GetDirectoryName(Application.dataPath), enableReloadControl);
            if (!ReferenceEquals(localOwner, owner) || !owner.Ready) ready = false;
            LocalOwnerStatus = ready ? "本地门控已连接；客户端尚需单独绑定" : "启动失败或已撤权；清理未确认时禁止重连";
            return ready;
        }
        internal static Task StopLocalOwnerAsync()
        {
            Plugins.Revoke();
#if UNITY_EDITOR
            CandidateReload.Cancel();
#endif
            if (localOwner == null) return StopOwnedAsync();
            Gate.StopAll("本地停止，不回退文件");
#if UNITY_EDITOR
            MaterialCandidateSession.Gate.StopAll("本地停止，不回退文件");
#endif
            LocalOwnerStatus = "正在关闭本轮会话及进程";
            return localStop ?? (localStop = CloseLocalOwnerAsync(localOwner));
        }
        static async Task CloseLocalOwnerAsync(EditorOwnerProcess owner)
        {
            try
            {
                await owner.StopAsync(); await StopOwnedAsync();
                if (owner.CleanupComplete && ReferenceEquals(localOwner, owner))
                { owner.Dispose(); localOwner = null; LocalOwnerStatus = "已停止，清理已确认；权限不恢复"; }
                else LocalOwnerStatus = "清理未确认，禁止重连";
            }
            catch { LocalOwnerStatus = "清理失败，禁止重连"; }
        }
        static async void Revoke()
        {
            Plugins.Revoke();
#if UNITY_EDITOR
            if (CandidateReload.Pending) { CandidateReload.Cancel(); return; }
#endif
            // Another lifecycle subscriber may already have started normal stop.
            // Do not Dispose its channel while the original owner's receipt is pending.
            if (localStop != null) { try { await localStop; } catch { } return; }
            ownedRevoked = true;
            Gate.StopAll("编辑器生命周期变化，需重新批准");
#if UNITY_EDITOR
            MaterialCandidateSession.Gate.StopAll("编辑器生命周期变化，需重新批准");
#endif
            ownedClient?.ForceStop(); // Revoke before any bounded process cleanup wait.
            localOwner?.Dispose();
            if (localOwner != null) LocalOwnerStatus = "生命周期已撤权；不自动重连或恢复批准";
            try { await StopOwnedAsync(); }
            catch { Gate.StopAll("连接清理未确认，禁止重新连接"); }
        }
        static WebSocketTransportClient ownedClient;
        static Uri ownedEndpoint;
        static string ownedSession;
        static bool ownedRevoked;
        static Task ownedCleanup;
        static Task<bool> ownedStart;
        // Local bootstrap caller only; never exposed as an MCP command. Values must
        // come from the owner-launched sidecar, not a discovered port or model input.
        internal static async Task<bool> ConnectOwnedAsync(Uri endpoint, string bearer, byte[] certificatePin)
        {
            if (ownedClient != null || EditorApplication.isCompiling || EditorApplication.isUpdating ||
                EditorApplication.isPlayingOrWillChangePlaymode) return false;
            WebSocketTransportClient client = null;
            client = new WebSocketTransportClient(endpoint, bearer, certificatePin,
                (command, args) => DispatchOwned(client, command, args));
            ownedClient = client; ownedEndpoint = endpoint; ownedRevoked = false; ownedCleanup = null; ownedSession = null;
            try
            {
                ownedStart = client.StartAsync();
                if (await ownedStart)
                {
                    var deadline = System.Diagnostics.Stopwatch.StartNew();
                    while (ReferenceEquals(ownedClient, client) && !ownedRevoked && client.IsConnected && deadline.Elapsed.TotalSeconds < 5)
                    {
                        if (LiveConnection() != "") return true;
                        await Task.Delay(20);
                    }
                }
            }
            catch { }
            if (ReferenceEquals(ownedClient, client)) await StopOwnedAsync();
            return false;
        }
        internal static Task StopOwnedAsync()
        {
            Plugins.Revoke();
            ownedRevoked = true;
            Gate.StopAll("连接已撤权，不回退");
#if UNITY_EDITOR
            MaterialCandidateSession.Gate.StopAll("连接已撤权，不回退");
#endif
            if (ownedClient == null) return Task.CompletedTask;
            return ownedCleanup ?? (ownedCleanup = CloseOwnedAsync(ownedClient));
        }
        static async Task CloseOwnedAsync(WebSocketTransportClient client)
        {
            var starting = ownedStart;
            bool pendingStart = starting != null && !starting.IsCompleted;
            await client.StopAsync(); // Cancel before waiting for a late connect.
            if (pendingStart)
            {
                try { await starting; } catch { }
                await client.StopAsync();
            }
            client.Dispose();
            if (ReferenceEquals(ownedClient, client)) { ownedClient = null; ownedEndpoint = null; }
        }
        internal static string LiveConnection()
        {
            if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode) return "";
            var client = ownedClient; var state = client?.State;
            if (ownedRevoked || client == null || !client.IsConnected || state == null || !state.IsConnected ||
                string.IsNullOrEmpty(state.SessionId) || state.SessionId == "pending" ||
                ownedEndpoint == null || state.Details != ownedEndpoint.AbsoluteUri)
            { if (ownedSession != null) ownedRevoked = true; return ""; }
            if (ownedSession != null && ownedSession != state.SessionId) { ownedRevoked = true; return ""; }
            ownedSession = state.SessionId;
            return ownedSession;
        }
        static object DispatchOwned(WebSocketTransportClient source, string command, JObject args)
        {
            if (!ReferenceEquals(source, ownedClient) || LiveConnection() == "")
                return new ErrorResponse("owned_connection_required");
            if(command=="vrchat_agent_dispatch" && (string)args?["kind"]=="execute" && (string)args?["body"]?["command"]=="get_tests")
                return DispatchDiscoveryAsync(args);
            JObject result;
            if (command == "vrchat_agent_dispatch") result = Gate.Dispatch(args);
#if UNITY_EDITOR
            else if (command == "vrchat_agent_material_dispatch") result = MaterialCandidateSession.Gate.Dispatch(args);
#endif
            else return new ErrorResponse("candidate_command_required");
            if ((bool?)result["success"] == true) return new SuccessResponse("受控候选操作", result["data"]);
            return new ErrorResponse((string)result["error"] ?? "candidate_denied", result["data"]);
        }
        static async Task<object> DispatchDiscoveryAsync(JObject request)
        {
            var result=await Gate.DispatchAsync(request);
            if((bool?)result["success"]==true)return new SuccessResponse("受控实时发现",result["data"]);
            return new ErrorResponse((string)result["error"]??"candidate_denied",result["data"]);
        }
        static async Task<JObject> ReadDiscovery(JObject args,Func<bool> authorized)
        {
            var job=UnityEditor.TestTools.TestRunner.CandidateDiscoveryJob.Begin((string)args["mode"],authorized);
            var result=await job.Completion;
            return new JObject{["success"]=result.Success,["error"]=result.Error,["data"]=new JObject{
                ["tests"]=result.Rows==null?new JArray():JArray.FromObject(result.Rows),
                ["candidate_effects"]=new JObject{["kind"]="test_discovery_callbacks",["version"]=1,
                    ["read_only"]=false,["all_mutations_observed"]=false,["callback_effects_path_bounded"]=false,["cleanup_confirmed"]=result.CleanupConfirmed}}};
        }
        static bool LiveSceneObject(int id)
        {
            // Native ID lookup is global; reject assets/components/other scenes without loading.
            var go = GameObjectLookup.ResolveInstanceID(id) as GameObject;
            var stage = UnityEditor.SceneManagement.PrefabStageUtility.GetCurrentPrefabStage();
            var scene = stage != null ? stage.scene : UnityEditor.SceneManagement.EditorSceneManager.GetActiveScene();
            return go != null && !EditorUtility.IsPersistent(go) && scene.IsValid() && scene.isLoaded &&
                go.scene.IsValid() && go.scene.isLoaded && go.scene == scene;
        }
        static AnimationClip LoadedClip(string target)
        {
            if(!CandidateGate.ClipPath(target) || AssetDatabase.GetMainAssetTypeAtPath(target)!=typeof(AnimationClip))throw new IOException("clip_not_loaded_main_asset");
            var clip=Resources.FindObjectsOfTypeAll<AnimationClip>().SingleOrDefault(x=>x!=null && x.GetType()==typeof(AnimationClip) && AssetDatabase.IsMainAsset(x) && AssetDatabase.GetAssetPath(x)==target);
            if(clip==null)throw new IOException("clip_not_loaded_main_asset");
            if(AnimationUtility.GetCurveBindings(clip).Length>512 || AnimationUtility.GetAnimationEvents(clip).Length>1024)throw new IOException("clip_budget");
            return clip;
        }
        static FileStream SourceLease(string command,JObject args)
        {
            string target=command=="manage_animation"?(string)args["clipPath"]:CandidateGate.SourceParams(command,args);Evidence(target);
            string full=Path.Combine(Directory.GetParent(Application.dataPath).FullName,target);
            var lease=new FileStream(full,FileMode.Open,FileAccess.Read,FileShare.Read);
            try{if(lease.Length>131072)throw new IOException("source_budget");Evidence(target);return lease;}
            catch{lease.Dispose();throw;}
        }
        static JObject ReadAsset(JObject args,Func<bool> authorized)
        {
            return AssetObservation.Read(args,authorized,(request,ticket)=> {
                if((string)request["action"]=="get_info")return CandidateScopedAssets.Info((string)request["path"],ticket);
                request.Remove("action");return CandidateScopedAssets.Query(request,ticket);
            });
        }
        static JObject NativeRead(string command, JObject args)
        {
            // Effectful operation: separately validated and receipted by the pinned
            // native adapter, never routed through the overridable read registry.
            if (command == "get_test_job") return JobObservation.Read(args);
            // Keep a read-sharing handle while native code reopens the same file.
            // This is not an adversarial filesystem sandbox; evidence is rechecked.
            using var sourceLease=command=="manage_script" || command=="manage_shader" || (command=="manage_animation" && (string)args["action"]=="clip_get_info")?SourceLease(command,args):null;
            // This registry API rejects asynchronous handlers before executing them.
            // CandidateGate restricts command/action/targets; no arbitrary command route.
            if ((command == "manage_scene" && (string)args["action"] == "get_hierarchy" && args.ContainsKey("parent") &&
                 !LiveSceneObject((int)args["parent"])) ||
                (command == "find_gameobjects" && (string)args["searchMethod"] == "by_id" &&
                 !LiveSceneObject(int.Parse((string)args["searchTerm"], System.Globalization.CultureInfo.InvariantCulture))))
                return new JObject { ["success"] = false };
            bool animatorRead = command == "manage_animation" && CandidateGate.AnimatorAction((string)args["action"]);
            int animatorId = 0; GameObject animatorObject = null;
            if (animatorRead)
            {
                animatorId = int.Parse((string)args["target"], System.Globalization.CultureInfo.InvariantCulture);
                if (!LiveSceneObject(animatorId)) return new JObject { ["success"] = false };
                animatorObject = (GameObject)GameObjectLookup.ResolveInstanceID(animatorId);
                var animator = animatorObject.GetComponents<Animator>().SingleOrDefault();
                if (animator == null || animator.parameterCount < 0 || animator.parameterCount > 256 ||
                    animator.layerCount < 0 || animator.layerCount > 64 ||
                    ((string)args["action"] == "animator_get_info" && animator.runtimeAnimatorController != null &&
                     animator.runtimeAnimatorController.animationClips.Length > 1024))
                    return new JObject { ["success"] = false };
            }
            bool objectRead = command == "get_gameobject" || command == "get_gameobject_components";
            if (objectRead)
            {
                int id = (int)args["instanceID"];
                if (!LiveSceneObject(id)) return new JObject { ["success"] = false };
                var go = (GameObject)GameObjectLookup.ResolveInstanceID(id);
                if (command == "get_gameobject" && (go.transform.childCount > 1024 || go.GetComponents<Component>().Length > 256))
                    return new JObject { ["success"] = false };
            }
            // Bind these new resource facades directly to pinned native classes:
            // the global registry permits later same-name overrides by other plugins.
            object response = command == "unity_reflect" ? MCPForUnity.Editor.Tools.CandidateScopedUnityReflect.HandleCommand(args) :
                command == "manage_shader" ? MCPForUnity.Editor.Tools.ManageShader.HandleCommand(args) :
                command == "manage_script" ? MCPForUnity.Editor.Tools.ManageScript.HandleCommand(args) :
                (animatorRead || (command=="manage_animation" && (string)args["action"]=="clip_get_info")) ? MCPForUnity.Editor.Tools.Animation.ManageAnimation.HandleCommand(args) :
                command == "manage_packages" ? MCPForUnity.Editor.Tools.ManagePackages.HandleCommand(args) :
                command == "get_menu_items" ? MCPForUnity.Editor.Resources.MenuItems.GetMenuItems.HandleCommand(args) :
                command == "get_selection" ? MCPForUnity.Editor.Resources.Editor.Selection.HandleCommand(args) :
                command == "get_windows" ? MCPForUnity.Editor.Resources.Editor.Windows.HandleCommand(args) :
                command == "get_active_tool" ? MCPForUnity.Editor.Resources.Editor.ActiveTool.HandleCommand(args) :
                command == "get_prefab_stage" ? MCPForUnity.Editor.Resources.Editor.GetPrefabStage.HandleCommand(args) :
                command == "get_project_info" ? MCPForUnity.Editor.Resources.Project.ProjectInfo.HandleCommand(args) :
                command == "get_tags" ? MCPForUnity.Editor.Resources.Project.Tags.HandleCommand(args) :
                command == "get_layers" ? MCPForUnity.Editor.Resources.Project.Layers.HandleCommand(args) :
                command == "get_gameobject" ? MCPForUnity.Editor.Resources.Scene.GameObjectResource.HandleCommand(args) :
                command == "get_gameobject_components" ? MCPForUnity.Editor.Resources.Scene.GameObjectComponentsResource.HandleCommand(args) :
                CommandRegistry.GetHandler(command)(args);
            JObject result = response as JObject ?? JObject.FromObject(response);
            // Validate only native success data here; the core sanitizes every
            // failure and revokes. Unknown/partial output is never a success.
            if (result["success"]?.Type == JTokenType.Boolean && (bool)result["success"] &&
                (!NativeReadContract.Valid(command, result, args) ||
                 (objectRead && !LiveSceneObject((int)args["instanceID"])) ||
                 (animatorRead && (!LiveSceneObject(animatorId) ||
                    ((string)args["action"] == "animator_get_info" && (string)result["data"]["gameObject"] != animatorObject.name))) ||
                 (command == "get_gameobject" &&
                    (!((JArray)result["data"]["children"]).All(id => LiveSceneObject((int)id)) ||
                     (result["data"]["parent"].Type != JTokenType.Null && !LiveSceneObject((int)result["data"]["parent"])))) ||
                 (command == "find_gameobjects" && !((JArray)result["data"]["instanceIDs"]).All(id => LiveSceneObject((int)id)))))
                return new JObject { ["success"] = false };
            if(command=="unity_reflect" && (bool?)result["success"]==true)
                result["data"]["candidate_scope"]=new JObject{["type_set"]="unity-engine-core-v1",["all_loaded_types"]=false,["extension_methods_included"]=false};
            return result;
        }
        static string Evidence(string assetPath)
        {
            // Explicit live Console capability: not a file, not a frozen log snapshot.
            // Project/session identity is rechecked by the gate; log appends are expected.
            // Live scopes are not content snapshots. Connection is a separate grant
            // binding, not evidence bytes; authenticated reload creates a new binding.
            if (CandidateGate.JobTarget(assetPath)) return "live-test-job:" + CoplayProjectIdentity.GetProjectHash() + ":" + assetPath;
            if (assetPath == "ApiMetadata") return "core-api-metadata-v1:" + Application.unityVersion + ":" + CoplayProjectIdentity.GetProjectHash();
            if (assetPath == "Console") return "live-console:" + CoplayProjectIdentity.GetProjectHash();
            // Scene metadata is a live project-scoped read, never a file grant.
            if (assetPath == "Scenes") return "live-scenes:" + CoplayProjectIdentity.GetProjectHash();
            if (assetPath == "EditorMetadata") return "live-editor-metadata:" + CoplayProjectIdentity.GetProjectHash();
            if (assetPath == "ProjectMetadata") return "live-project-metadata:" + CoplayProjectIdentity.GetProjectHash();
            string project = Directory.GetParent(Application.dataPath).FullName;
            string full = Path.GetFullPath(Path.Combine(project, assetPath));
            if (!full.StartsWith(Path.GetFullPath(Application.dataPath) + Path.DirectorySeparatorChar, StringComparison.Ordinal)) throw new IOException("target_outside_assets");
            string current = full;
            while (current != project)
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new IOException("reparse_target_unsupported");
                current = Path.GetDirectoryName(current);
            }
            // Evidence, not an OS sandbox. Bounded target + .meta raw disk hashes catch
            // external edits even before Unity import. Dependency hash is Unity's own
            // imported-dependency view; full unimported dependency evidence is still pending.
            var state = new StringBuilder();
            if(CandidateGate.ClipPath(assetPath))
            {
                string raw=HashFile(full,131072),meta=HashFile(full+".meta",131072);
                var clip=LoadedClip(assetPath);string memory=EditorJsonUtility.ToJson(clip);
                if(Encoding.UTF8.GetByteCount(memory)>1024*1024)throw new IOException("clip_memory_budget");
                return assetPath+"|"+raw+"|"+meta+"|"+AssetDatabase.GetAssetDependencyHash(assetPath)+"|"+clip.GetInstanceID()+"|"+memory;
            }
            if(CandidateGate.SourcePath(assetPath))
                return assetPath+"|"+HashFile(full,131072)+"|"+HashFile(full+".meta",131072);
            state.Append(assetPath).Append('|').Append(HashFile(full)).Append('|').Append(HashFile(full + ".meta"));
            state.Append('|').Append(AssetDatabase.AssetPathToGUID(assetPath));
            state.Append('|').Append(AssetDatabase.GetAssetDependencyHash(assetPath).ToString());
            var objects = AssetDatabase.LoadAllAssetsAtPath(assetPath);
            if (objects == null || objects.Length == 0 || objects.Length > 4096) throw new IOException("asset_evidence_unavailable");
            foreach (var obj in objects.OrderBy(o => o.GetInstanceID()))
            {
                if (obj == null) throw new IOException("null_asset_evidence");
                string memory = EditorJsonUtility.ToJson(obj);
                if (memory.Length > 4 * 1024 * 1024 || state.Length + memory.Length > 16 * 1024 * 1024) throw new IOException("evidence_too_large");
                state.Append('|').Append(obj.GetInstanceID()).Append(':').Append(memory);
            }
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(state.ToString())));
        }
        static string HashFile(string path,long budget=16*1024*1024)
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("reparse_target_unsupported");
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (input.Length > budget) throw new IOException("evidence_too_large");
                using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(input));
            }
        }
    }

    // Compatibility tombstone: deliberately absent from global tool discovery.
    public static class VrchatAgentDispatch
    {
        public static object HandleCommand(JObject parameters)
        {
            return new ErrorResponse("owned_connection_required");
        }
    }
}
