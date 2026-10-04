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
        Vector2 scroll;
        JArray catalog;
        string catalogTool = "", catalogError = "";
        bool allowHermes, allowCodex; // Local per-run selection; default closed, no persistence.
        bool externalPython; // Explicit development opt-in; default never searches host Python.
        string codexExecutable = "";
        string hermesHost = "", hermesUser = "";
        int hermesPort = 22, hermesForwardPort = 18088;
        string python = ""; // Local window only; never persists credentials or client configuration.
        [MenuItem("Tools/VRChat Agent/候选权限与清单")]
        static void Open() { GetWindow<CandidateWindow>("候选权限与清单"); }
        void OnInspectorUpdate() { Repaint(); }
        void OnGUI()
        {
            var gate = CandidateSession.Gate;
            EditorGUILayout.HelpBox("开发候选，尚未完成实机验收。这里只控制本项目受控MCP入口，不限制本地终端。导入/打开窗口不会启动服务或批准任务。", MessageType.Warning);
            EditorGUILayout.LabelField("当前工程", CoplayProjectIdentity.GetProjectHash());
            EditorGUILayout.LabelField("本地连接", CandidateSession.LocalOwnerReady ? "门控已就绪，客户端另行绑定" : CandidateSession.LocalOwnerStatus);
            EditorGUI.BeginDisabledGroup(CandidateSession.HasLocalOwner);
            EditorGUILayout.HelpBox("本轮客户端准入（不是绑定完成或任务批准）；默认全关，变更需先停止连接。远程Hermes使用受限SSH子系统，远端仍须在指定聊天中认领；本地Codex在新控制台单独登录，不复用或修改现用配置。", MessageType.Info);
            allowHermes = EditorGUILayout.ToggleLeft("允许本轮 Hermes 角色", allowHermes);
            allowCodex = EditorGUILayout.ToggleLeft("允许本轮 Codex 角色", allowCodex);
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
            externalPython = EditorGUILayout.ToggleLeft("开发测试：改用本机Python（不属于便携交付）", externalPython);
            if (externalPython) python = EditorGUILayout.TextField("本机Python 3.11绝对路径", python);
            else EditorGUILayout.LabelField("运行时", "随包固定Python；缺失或校验失败不自动回退");
            if (GUILayout.Button("启动本地受控连接")) StartLocal();
            EditorGUI.EndDisabledGroup();
            EditorGUI.BeginDisabledGroup(!CandidateSession.HasLocalOwner);
            if (GUILayout.Button("停止连接并撤权（不回退）")) StopLocal();
            EditorGUI.EndDisabledGroup();
            Capability("材质信息读取", "manage_material", "get_material_info");
            Capability("控制器信息读取", "manage_animation", "controller_get_info");
            EditorGUILayout.HelpBox("旧v1入口保持只读。Scenes范围允许本工程场景元数据与当前场景/Prefab Stage的单层分页摘要；父对象仅精确ID。结果实时变化，组件类型摘要并非完整属性；不加载或保存。validate只在显式auto_repair=false时检查活动场景的缺失脚本/损坏Prefab引用，不修复；最多200条记录，问题总数不等于对象条数，遍历可能耗时。候选材质写走下方独立入口；删除、全量刷新/导入、场景保存、包操作、任意执行仍拒绝。", MessageType.Info);
            if (GUILayout.Button("撤销全部任务权限（不回退文件）"))
            {
                gate.StopAll("本地已撤销全部任务；不回退文件");
#if UNITY_EDITOR
                MaterialCandidateSession.Gate.StopAll("本地全部撤权；不回退文件");
#endif
            }
            EditorGUILayout.LabelField("状态", gate.LastReason);
            scroll = EditorGUILayout.BeginScrollView(scroll);
            DrawCatalog();
            JArray displayed = gate.LocalPlans();
            foreach (JObject plan in displayed)
            {
                EditorGUILayout.Space();
                EditorGUILayout.LabelField("认证主体 / MCP会话", (string)plan["client_id"]);
                EditorGUILayout.LabelField("连接", (string)plan["connection_id"]);
                EditorGUILayout.LabelField("任务", (string)plan["task_id"]);
                EditorGUILayout.LabelField("清单ID", (string)plan["plan_id"]);
                EditorGUILayout.LabelField("清单摘要", (string)plan["digest"]);
                EditorGUILayout.LabelField("剩余秒数", ((double)plan["seconds_left"]).ToString("F0"));
                foreach (JObject op in (JArray)plan["manifest"]["operations"])
                    EditorGUILayout.LabelField("操作", (string)op["command"] + " / " + (string)op["action"]);
                foreach (JToken target in (JArray)plan["manifest"]["targets"])
                    EditorGUILayout.LabelField("精确目标", (string)target);
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
            MaterialCandidateSession.Draw();
#endif
            EditorGUILayout.EndScrollView();
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
                        if (facades == null || facades.Count != 10) throw new InvalidDataException();
                        foreach (JObject row in facades)
                        {
                            if ((string)row["provenance_kind"] != "native_resource_tool_facade" ||
                                !new[] { "get_gameobject", "get_gameobject_components", "get_project_info", "get_tags", "get_layers", "get_selection", "get_windows", "get_active_tool", "get_prefab_stage", "get_menu_items" }.Contains((string)row["name"]) ||
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
            foreach (JObject row in catalog)
            {
                string command = (string)row["name"];
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
                if (actions.Count == 0) EditorGUILayout.LabelField("操作", "无封闭动作清单；尚未接通，拒绝");
                foreach (JToken item in actions)
                {
                    string action = (string)item;
                    bool supported = true;
                    try { CandidateSession.Gate.Allows(command, action); } catch { supported = false; }
                    if (supported)
                    {
                        if (CandidateGate.EditorCommand(command)) EditorGUILayout.HelpBox("EditorMetadata会披露全编辑器的选择名称/类型/ID、窗口标题坐标、工具设置或已打开Prefab路径。不是资产正文读取/修改授权；不聚焦窗口、不打开Prefab。", MessageType.Info);
                        if (command == "manage_packages") EditorGUILayout.HelpBox("仅get_package_info；ProjectMetadata独立批准，披露包作者/描述/来源/绝对路径/依赖。仅读本地已注册元数据，不查询远端、不调用UPM任务；不是包内容或安装权限。", MessageType.Info);
                        if (command == "get_menu_items") EditorGUILayout.HelpBox("菜单名称仅为TypeCache元数据；内部refresh不刷新资产、不执行菜单。最多4096项，原生扫描失败可返回旧缓存/空列表，不保证穷尽。", MessageType.Info);
                        Capability((string)row["name_zh"], command, action);
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
        }
        async void StartLocal()
        {
            try
            {
                JObject hermesSsh = allowHermes ? new JObject { ["host"]=hermesHost, ["user"]=hermesUser,
                    ["port"]=hermesPort, ["remote_port"]=hermesForwardPort } : null;
                await CandidateSession.StartLocalOwnerAsync(externalPython ? python : null, allowHermes, allowCodex, hermesSsh, allowCodex ? codexExecutable : null);
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
            if (current != selected) gate.SetCapability(command, action, selected);
        }
    }
}
