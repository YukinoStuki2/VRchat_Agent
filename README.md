# VRChat Read-Only MCP Diagnostics

A project-scoped Unity package for CoplayDev MCP for Unity v10.2.0. It exposes
only bounded query, analysis, validation, and authoring decision-support tools.
It does not create, edit, save, import, delete, build, upload, enter Play Mode,
change Selection, access credentials, run arbitrary code, or perform network
requests.

## 从 GitHub 安装（Unity Package Manager）

先安装基础依赖：在 Package Manager → Add package from git URL 中添加
`https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0`。

然后添加本工具包（公开仓库）：
`https://github.com/YukinoStuki2/VRchat_Agent.git#v0.1.1`

私有仓库使用 SSH 地址，且 Windows 必须具有该仓库的读取权限：
`ssh://git@github.com/YukinoStuki2/VRchat_Agent.git#v0.1.1`

本包位于仓库根目录，无需 `?path=`。不要同时保留 Assets 中或本地路径安装的重复副本。
等待编译完成，在 MCP 面板 Rescan，保持 Project Scoped Tools 开启。
这只安装项目级只读诊断扩展，不会自动启动 MCP 服务端、SSH 隧道或配置 AI 客户端。

## Install from a local ZIP

1. Back up or commit `Assets/`, `Packages/`, and `ProjectSettings/`.
2. Extract this package outside the Unity project.
3. In Unity Package Manager choose **Add package from disk...** and select this
   package's `package.json`.
4. Wait for compilation. Do not continue if Console reports a compile error.
5. In **Window > MCP for Unity > Tools**, click **Rescan**.
6. Confirm exactly twelve `vrchat_ro_*` tools are present.
7. Keep Project Scoped Tools enabled. Reconnect/reload the MCP client.
8. Add only the exact `vrchat_ro_*` names to the Hermes allowlist.

## Target parameters

Tools resolve targets in this order:

- `instance_id`: exact Unity object instance ID;
- `hierarchy_path`: exact `Scene/Root/Child` or `Root/Child` path;
- `target`: exact path first, then unique object name.

Ambiguous names fail closed and return at most twenty candidate paths. Results include
`read_only=true` and `mutated=false`.

## Response bounds

Every successful tool applies `max_items` as a global JSON node budget in addition
to its section-specific row limits. String values are capped at 512 characters.
The top-level `response_budget` reports emitted nodes and whether the response was
truncated. A truncated response is not a complete negative finding; rerun with a
larger bounded budget or a narrower target/query.

## Tools

- `vrchat_ro_project_inventory`
- `vrchat_ro_avatar_inspect`
- `vrchat_ro_renderer_mesh`
- `vrchat_ro_blendshapes`
- `vrchat_ro_materials`
- `vrchat_ro_animator`
- `vrchat_ro_expressions`
- `vrchat_ro_dynamics`
- `vrchat_ro_modular_stack`
- `vrchat_ro_performance`
- `vrchat_ro_outfit_compatibility`
- `vrchat_ro_validate`

Performance metrics are static, advisory snapshots. The tool exposes
`analysis_complete` and `unavailable_categories`; when exact SDK parity is not
available, the formal rank/readiness verdict is withheld rather than reported as
clean. `measured_metrics_worst_rank` is only the worst result among the
categories this tool measured or estimated; it is not a bound on the official rank,
and the SDK result may be worse because unavailable categories are omitted. An
unreadable rendered mesh is separately reported under VRChat's forced Very Poor
rule. Verify current limits and the SDK Builder before acting. Outfit and
face/body classifications are heuristics with evidence and confidence, not
permission to modify assets.
