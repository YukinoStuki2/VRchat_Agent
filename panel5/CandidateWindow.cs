using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace Yukino.VRChatAgent
{
    public sealed class CandidateWindow : EditorWindow
    {
        static readonly string[] Pages = { "连接", "权限", "任务" };
        int page;
        Vector2[] pageScroll = new Vector2[3];
        bool advancedConnection, showProject, showEffects, showReload, showMaterial, showVisual, showScript;
        JArray catalog;
        string catalogQuery = "";
        string catalogTool = "", catalogError = "";
        string pluginTrustToken;
        bool allowPlannedReload; // Per-run opt-in; opening the window never enables it.
        bool allowHermes, allowCodex; // Local per-run selection; default closed, no persistence.
        bool externalPython; // Explicit development opt-in; default never searches host Python.
        string codexExecutable = "";
        string hermesHost = "", hermesUser = "";
        int hermesPort = 22, hermesForwardPort = 18088;
        string python = ""; // Local window only; never persists credentials or client configuration.
        [MenuItem("Tools/VRChat Agent/候选权限与清单")]
        static void Open() { GetWindow<CandidateWindow>("VRChat Agent"); }
#if UNITY_EDITOR
        void OnEnable() { CandidateReload.WindowVisible(true); }
        // OnDisable also runs during reload; only destruction is local cancellation.
        void OnDestroy() { VisualCaptureSession.Stop("权限窗口关闭；未发送图片不外发"); CandidateReload.WindowVisible(false); }
#endif
        void OnInspectorUpdate() { Repaint(); }
        void OnGUI()
        {
            GUILayout.Space(6);
            EditorGUILayout.LabelField("VRChat Agent", EditorStyles.boldLabel);
            EditorGUILayout.LabelField(CandidateSession.LocalOwnerReady ? "本地连接已就绪 · 客户端需另行绑定" : "本地连接：" + CandidateSession.LocalOwnerStatus, EditorStyles.wordWrappedLabel);
            GUILayout.Space(4);
            int next = GUILayout.Toolbar(page, Pages);
            if (next != page) { GUI.FocusControl(null); page = next; }
            pageScroll[page] = EditorGUILayout.BeginScrollView(pageScroll[page]);
            if (page == 0) DrawConnection();
            else if (page == 1) DrawPermissions();
            else DrawTasks();
            EditorGUILayout.EndScrollView();
            DrawQuickActions();
        }

        static void Section(string title, string note)
        {
            GUILayout.Space(8);
            EditorGUILayout.LabelField(title, EditorStyles.boldLabel);
            EditorGUILayout.LabelField(note, EditorStyles.wordWrappedLabel);
            GUILayout.Space(3);
        }

        void DrawConnection()
        {
            Section("连接到哪里？", "选一个对话入口，再启动连接。连接不会授予读写权限。");
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            EditorGUI.BeginDisabledGroup(CandidateSession.HasLocalOwner);
            allowHermes = EditorGUILayout.ToggleLeft("Hermes · 在指定聊天里使用", allowHermes);
            allowCodex = EditorGUILayout.ToggleLeft("Codex · 在本机终端使用", allowCodex);
            if (allowCodex)
            {
                codexExecutable = EditorGUILayout.TextField("Codex原生.exe绝对路径", codexExecutable);
                EditorGUILayout.HelpBox("仅Windows原生Codex，不接受.cmd/.bat包装器。不自动发送提示或消耗模型额度；首次在独立控制台登录。凭据仅内存，关闭后需重新登录；MCP授权不限制原生终端，修改仍应遵循项目规则。", MessageType.Info);
            }
            if (allowHermes)
            {
                hermesHost = EditorGUILayout.TextField("Hermes管理机SSH主机", hermesHost);
                hermesUser = EditorGUILayout.TextField("受限SSH用户名", hermesUser);
                hermesPort = EditorGUILayout.IntField("SSH端口", hermesPort);
                hermesForwardPort = EditorGUILayout.IntField("管理机回环转发端口", hermesForwardPort);
                EditorGUILayout.HelpBox("需预先安装远端接收器及vrchat-agent-handoff子系统、核对主机指纹并配置SSH密钥。不保存密码；本面板不修改SSH账号或信任配置。", MessageType.Info);
            }
            GUILayout.Space(4);
            advancedConnection = EditorGUILayout.Foldout(advancedConnection, "高级连接选项", true);
            if (advancedConnection)
            {
                allowPlannedReload = EditorGUILayout.ToggleLeft("允许本轮本地批准一次编译续接（默认关闭）", allowPlannedReload);
                externalPython = EditorGUILayout.ToggleLeft("开发测试：改用本机Python（不属于便携交付）", externalPython);
                if (externalPython) python = EditorGUILayout.TextField("本机Python 3.11绝对路径", python);
                else EditorGUILayout.LabelField("运行时", "随包固定Python；缺失或校验失败不自动回退");
            }
            GUILayout.Space(6);
            if (GUILayout.Button("启动本地受控连接")) StartLocal();
            EditorGUI.EndDisabledGroup();
            EditorGUILayout.EndVertical();
            Section("第一次可以试什么？", "先问：当前打开的是哪个场景？只需要读取，不用允许修改或截图。");
            EditorGUILayout.LabelField("客户端绑定后，在「权限」选择所需读取；它提交请求后，到「任务」核对目标并批准。", EditorStyles.wordWrappedLabel);
            GUILayout.Space(8);
            showProject = EditorGUILayout.Foldout(showProject, "工程标识与使用范围", true);
            if (showProject)
            {
                EditorGUILayout.LabelField(CoplayProjectIdentity.GetProjectHash(), EditorStyles.wordWrappedLabel);
                EditorGUILayout.HelpBox("预览版，仅约束本项目的受控 MCP 操作，不限制本地终端。打开窗口不会启动服务或批准任务。", MessageType.Info);
            }
        }

        void DrawQuickActions()
        {
            var gate = CandidateSession.Gate;
            GUILayout.Space(3);
            EditorGUI.BeginDisabledGroup(!CandidateSession.HasLocalOwner);
            if (GUILayout.Button("停止连接并撤权（不回退）")) StopLocal();
            EditorGUI.EndDisabledGroup();
            if (GUILayout.Button("撤销全部任务权限（不回退文件）"))
            {
#if UNITY_EDITOR
                CandidateReload.Cancel();
#endif
                CandidateSession.Plugins.Revoke();pluginTrustToken=null;
                gate.StopAll("本地已撤销全部任务；不回退文件");
#if UNITY_EDITOR
                MaterialCandidateSession.Gate.StopAll("本地全部撤权；不回退文件");
#endif
            }
        }

        void DrawPermissions()
        {
            var gate = CandidateSession.Gate;
            if (gate.PrefabCleanupUnconfirmed || gate.TestDiscoveryCleanupUnconfirmed)
                EditorGUILayout.HelpBox("清理尚未确认：相关读取仍被阻止，重连不会解除。", MessageType.Warning);
            Section("常用读取", "勾选只表示允许申请；具体读取哪些对象，要在「任务」另行批准。");
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            Capability("当前场景", "manage_scene", "get_active");
            Capability("场景层级", "manage_scene", "get_hierarchy");
            Capability("材质信息读取", "manage_material", "get_material_info");
            Capability("控制器信息读取", "manage_animation", "controller_get_info");
            Capability("已加载独立动画片段信息读取", "manage_animation", "clip_get_info");
            EditorGUILayout.EndVertical();
            EditorGUILayout.LabelField("场景层级只列对象摘要，不读取全部组件属性。场景检查不修复、不加载、不保存。", EditorStyles.wordWrappedLabel);
            Section("更多操作", "在目录中按中文名或英文工具名搜索。未接通的操作不能勾选。");
            DrawCatalog();
            GUILayout.Space(8);
            showEffects = EditorGUILayout.Foldout(showEffects, "插件信任与有副作用的读取", true);
            if (showEffects)
            {
                EditorGUILayout.HelpBox("工程插件信任前提：本地明确认可此工程已安装插件及其内部回调。不是插件沙箱，不保证阻止未知回调、文件写入、联网或启动进程；路径限制只约束Agent入口。此认可不批准任务、不开启效果权限，连接/代码库存或包清单变化后须重新核对。", MessageType.Warning);
                EditorGUILayout.LabelField("工程插件信任", CandidateSession.Plugins.Confirmed ? "本轮已本地认可；不是代码安全证明" : "未认可；效果读取不可用");
                if (GUILayout.Button("核对本轮工程插件信任")) pluginTrustToken=CandidateSession.Plugins.StageLocal();
                if(pluginTrustToken!=null)
                {
                    EditorGUILayout.LabelField("本轮确认标识",pluginTrustToken);
                    if(GUILayout.Button("确认信任此工程插件（不批准任务）"))
                    {CandidateSession.Plugins.ConfirmLocal(pluginTrustToken);pluginTrustToken=null;}
                }
                if(GUILayout.Button("撤销工程插件信任（不回退）"))
                {CandidateSession.Plugins.Revoke();pluginTrustToken=null;}
                bool assets=EditorGUILayout.ToggleLeft("允许资产加载回调（独立副作用）",gate.AssetCallbacksAllowed);
                if(assets!=gate.AssetCallbacksAllowed)gate.SetAssetCallbacks(assets);
                bool prefabs=EditorGUILayout.ToggleLeft("允许Prefab临时内容回调（独立副作用）",gate.PrefabContentsCallbacksAllowed);
                if(prefabs!=gate.PrefabContentsCallbacksAllowed)gate.SetPrefabContentsCallbacks(prefabs);
                bool discovery=EditorGUILayout.ToggleLeft("允许实时测试发现回调（独立副作用）",gate.TestDiscoveryCallbacksAllowed);
                if(discovery!=gate.TestDiscoveryCallbacksAllowed)gate.SetTestDiscoveryCallbacks(discovery);
                bool maintenance = EditorGUILayout.ToggleLeft("允许本工程测试作业状态维护（独立副作用）", gate.ProjectJobMaintenanceAllowed);
                if (maintenance != gate.ProjectJobMaintenanceAllowed)
                {
#if UNITY_EDITOR
                    CandidateReload.Cancel();
#endif
                    gate.SetProjectJobMaintenance(maintenance);
                }
                EditorGUILayout.HelpBox("作业观测不是纯读取：可恢复并改变本工程其他过期作业、写SessionState及裁剪历史。结果仅返回清单指定作业；此开关不批准任务，不启动测试、不抢焦点。停止不回退维护结果。", MessageType.Warning);
            }
            EditorGUILayout.HelpBox("材质副本、脚本修改及截图各自独立审批，入口在「任务」。", MessageType.Info);
        }

        void DrawTasks()
        {
            var gate = CandidateSession.Gate;
            Section("读取请求", "核对操作、目标和有效期后再批准。停止只撤权，不会撤销已经发生的修改。");
            EditorGUILayout.LabelField("最近状态：" + gate.LastReason, EditorStyles.wordWrappedLabel);
            JArray displayed = gate.LocalPlans();
            if (displayed.Count == 0) EditorGUILayout.HelpBox("暂无读取请求。请先在已绑定的客户端提出任务。", MessageType.Info);
            foreach (JObject plan in displayed)
            {
                EditorGUILayout.Space();
                EditorGUILayout.LabelField("认证主体 / MCP会话：" + (string)plan["client_id"], EditorStyles.wordWrappedLabel);
                EditorGUILayout.LabelField("连接", (string)plan["connection_id"]);
                EditorGUILayout.LabelField("任务", (string)plan["task_id"]);
                EditorGUILayout.LabelField("清单ID", (string)plan["plan_id"]);
                EditorGUILayout.LabelField("清单摘要：" + (string)plan["digest"], EditorStyles.wordWrappedLabel);
                EditorGUILayout.LabelField("剩余秒数", ((double)plan["seconds_left"]).ToString("F0"));
                foreach (JObject op in (JArray)plan["manifest"]["operations"])
                    EditorGUILayout.LabelField("操作", (string)op["command"] + " / " + (string)op["action"]);
                foreach (JToken target in (JArray)plan["manifest"]["targets"])
                    EditorGUILayout.LabelField("精确目标：" + (string)target, EditorStyles.wordWrappedLabel);
                if (plan["manifest"]["effect_policy"] is JObject effect)
                {
                    EditorGUILayout.LabelField("独立副作用", (string)effect["kind"] + " / v" + (string)effect["version"]);
                    EditorGUILayout.HelpBox((string)effect["notice_zh"], MessageType.Warning);
                    EditorGUILayout.LabelField("结果范围（不限制维护范围）", (string)effect["result_target"]);
                }
                bool approved = (bool)plan["approved"];
                EditorGUILayout.LabelField("批准状态", approved ? "已批准" : "等待主人在本地核对");
                EditorGUI.BeginDisabledGroup(approved);
                if (GUILayout.Button("批准此清单"))
                    gate.Approve((string)plan["plan_id"], (string)plan["digest"]);
                EditorGUI.EndDisabledGroup();
                EditorGUILayout.LabelField("暂停状态", (bool)plan["paused"] ? "已暂停；期限不延长" : "未暂停");
                EditorGUI.BeginDisabledGroup(!(bool)plan["approved"]);
                if ((bool)plan["paused"])
                {
                    if (GUILayout.Button("核验后继续原清单")) gate.Resume((string)plan["plan_id"], (string)plan["digest"]);
                }
                else if (GUILayout.Button("暂停此清单（不回退）")) gate.Pause((string)plan["plan_id"], (string)plan["digest"]);
                EditorGUI.EndDisabledGroup();
            }
#if UNITY_EDITOR
            Section("专项任务", "展开对应类型，可设置单项权限、处理请求或查看历史。");
            showMaterial = EditorGUILayout.Foldout(showMaterial, "材质副本与引用", true);
            if (showMaterial) MaterialCandidateSession.Draw();
            showScript = EditorGUILayout.Foldout(showScript, "单文件修改与恢复", true);
            if (showScript) ScriptCandidateSession.Draw();
            showVisual = EditorGUILayout.Foldout(showVisual, "截图预览与发送确认", true);
            if (showVisual) VisualCaptureSession.Draw();
            showReload = EditorGUILayout.Foldout(showReload, "编译后续接", true);
            if (showReload)
            {
                EditorGUILayout.LabelField("一次计划内编译续接", CandidateReload.Status);
                EditorGUI.BeginDisabledGroup(!CandidateSession.LocalOwnerReady || CandidateReload.Pending);
                if (GUILayout.Button("批准一次编译并核验续接原清单")) BeginReload();
                EditorGUI.EndDisabledGroup();
            }
#endif
        }
        void DrawCatalog()
        {
            if (GUILayout.Button(catalog == null ? "展开原生操作目录" : "收起原生操作目录"))
            {
                if (catalog != null) catalog = null;
                else
                {
                    try
                    {
                        var package = UnityEditor.PackageManager.PackageInfo.FindForAssembly(typeof(CandidateSession).Assembly);
                        string path = Path.Combine(package.resolvedPath, "Runtime~", "catalog", "native-inventory.json");
                        if (new FileInfo(path).Length > 1024 * 1024) throw new InvalidDataException();
                        var doc = JObject.Parse(File.ReadAllText(path));
                        var rows = doc["tools"] as JArray;
                        if ((int?)doc["schema_version"] != 1 || (bool?)doc["permission_grant"] != false ||
                            (bool?)doc["product_ready"] != false || rows == null || rows.Count == 0 ||
                            rows.Count > 256 || (int?)doc["count"] != rows.Count) throw new InvalidDataException();
                        foreach (JObject row in rows)
                            if ((bool?)row["enabled_by_catalog"] != false || (string)row["default_decision"] != "deny" ||
                                row["declared_actions"] is not JArray) throw new InvalidDataException();
                        var facades = doc["resource_facades"] as JArray;
                        if (facades == null || facades.Count != 11) throw new InvalidDataException();
                        foreach (JObject row in facades)
                        {
                            if ((string)row["provenance_kind"] != "native_resource_tool_facade" ||
                                !new[] { "get_gameobject", "get_gameobject_components", "get_project_info", "get_tags", "get_layers", "get_selection", "get_windows", "get_active_tool", "get_prefab_stage", "get_menu_items", "get_tests" }.Contains((string)row["name"]) ||
                                (bool?)row["enabled_by_catalog"] != false || (string)row["default_decision"] != "deny" ||
                                row["declared_actions"] is not JArray) throw new InvalidDataException();
                            rows.Add(row.DeepClone());
                        }
                        catalog = rows; catalogError = "";
                    }
                    catch { catalog = null; catalogError = "随包能力目录缺失或无效，未更改任何权限。"; }
                }
            }
            if (catalogError != "") EditorGUILayout.HelpBox(catalogError, MessageType.Warning);
            if (catalog == null) return;
            EditorGUILayout.HelpBox("固定候选版本的能力目录，不是工程资产扫描，也不代表全部已接通。未知操作保持禁用；勾选仅改变本地能力上限，具体任务仍需核对清单批准。运行时另校验目录对应源码。", MessageType.Info);
            catalogQuery = EditorGUILayout.TextField("搜索工具", catalogQuery);
            string query = catalogQuery.Trim();
            int matches = 0;
            foreach (JObject row in catalog)
            {
                string command = (string)row["name"];
                if (query.Length > 0 && (command + " " + (string)row["name_zh"]).IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0) continue;
                matches++;
                string category = (string)row["group"];
                string chinese = category switch {
                    "core" => "核心", "animation" => "动画", "asset_gen" => "外部资产生成",
                    "docs" => "文档", "probuilder" => "几何建模", "profiling" => "性能分析",
                    "scripting_ext" => "脚本", "testing" => "测试", "ui" => "用户界面",
                    "vfx" => "特效", _ => "其他"
                };
                EditorGUILayout.LabelField((string)row["provenance_kind"] == "native_resource_tool_facade" ? "原生资源的候选工具入口" : "原生工具", chinese + " / " + (string)row["name_zh"] + "  " + command);
                if (GUILayout.Button("展开操作：" + command)) catalogTool = catalogTool == command ? "" : command;
                if (catalogTool != command) continue;
                var actions = (JArray)row["declared_actions"];
                if (actions.Count == 0 && (bool?)row["has_action_parameter"] == false &&
                    row["implemented_candidate_read_actions"] is JArray labels && labels.Count > 0)
                { actions = labels; EditorGUILayout.LabelField("权限名", "仅用于候选清单；原生工具没有action参数"); }
                if (actions.Count == 0 && (bool?)row["has_action_parameter"] == false &&
                    row["implemented_candidate_effect_actions"] is JArray effects && effects.Count > 0)
                { actions = effects; EditorGUILayout.LabelField("独立副作用权限名", "不是只读能力；仍需工程级维护开关和本地清单批准"); }
                if (actions.Count == 0) EditorGUILayout.LabelField("操作", "无封闭动作清单；尚未接通，拒绝");
                foreach (JToken item in actions)
                {
                    string action = (string)item;
                    string operationCommand=command=="get_sha" && action=="get_sha"?"manage_script":command;
                    bool supported = true;
                    try { CandidateSession.Gate.Allows(operationCommand, action); } catch { supported = false; }
                    if (supported)
                    {
                        if (CandidateGate.EditorCommand(command)) EditorGUILayout.HelpBox("EditorMetadata会披露全编辑器的选择名称/类型/ID、窗口标题坐标、工具设置或已打开Prefab路径。不是资产正文读取/修改授权；不聚焦窗口、不打开Prefab。", MessageType.Info);
                        if (command == "unity_reflect") EditorGUILayout.HelpBox("ApiMetadata独立批准：仅13种UnityEngine核心类型，不是全工程API；不查用户/插件类型、不发现扩展方法、不执行getter/方法、不扫描程序集。具体类型集合见随包说明。get_type/get_member/search分别授权。", MessageType.Info);
                        if (command == "manage_packages") EditorGUILayout.HelpBox("仅get_package_info；ProjectMetadata独立批准，披露包作者/描述/来源/绝对路径/依赖。仅读本地已注册元数据，不查询远端、不调用UPM任务；不是包内容或安装权限。", MessageType.Info);
                        if (command == "get_menu_items") EditorGUILayout.HelpBox("菜单名称仅为TypeCache元数据；内部refresh不刷新资产、不执行菜单。最多4096项，原生扫描失败可返回旧缓存/空列表，不保证穷尽。", MessageType.Info);
                        if (operationCommand=="manage_script" || operationCommand=="manage_shader") EditorGUILayout.HelpBox("仅规范Assets精确文件，绑定原始文件与.meta证据；不加载Unity资产、导入或编译。原始及解码UTF8文本限128KiB。get_sha是原生解码后文本摘要，不是磁盘字节哈希，也不授予正文读取。", MessageType.Info);
                        Capability((string)row["name_zh"], operationCommand, action);
                    }
                    else
                    {
                        EditorGUI.BeginDisabledGroup(true);
                        EditorGUILayout.ToggleLeft(command + "/" + action + "  尚未接通，拒绝", false);
                        EditorGUI.EndDisabledGroup();
                        EditorGUILayout.LabelField("未支持操作", command + "/" + action + "  尚未接通，拒绝");
                    }
                }
            }
            if (matches == 0) EditorGUILayout.HelpBox("没有匹配的工具。试试中文名称或英文工具名。", MessageType.Info);
        }
#if UNITY_EDITOR
        async void BeginReload() { await CandidateReload.BeginAsync(); Repaint(); }
#endif
        async void StartLocal()
        {
            try
            {
                JObject hermesSsh = allowHermes ? new JObject { ["host"]=hermesHost, ["user"]=hermesUser,
                    ["port"]=hermesPort, ["remote_port"]=hermesForwardPort } : null;
                await CandidateSession.StartLocalOwnerAsync(externalPython ? python : null, allowHermes, allowCodex, hermesSsh, allowCodex ? codexExecutable : null, allowPlannedReload);
            }
            catch { CandidateSession.Gate.StopAll("本地连接启动失败，未批准任务"); }
            Repaint();
        }
        async void StopLocal()
        {
            try { await CandidateSession.StopLocalOwnerAsync(); }
            catch { CandidateSession.Gate.StopAll("连接清理未确认"); }
            Repaint();
        }
        static void Capability(string chinese, string command, string action)
        {
            var gate = CandidateSession.Gate;
            bool current = gate.Allows(command, action);
            bool selected = EditorGUILayout.ToggleLeft(chinese + "  " + command + "/" + action, current);
            if (current != selected)
            {
#if UNITY_EDITOR
                CandidateReload.Cancel();
#endif
                gate.SetCapability(command, action, selected);
            }
        }
    }
}
