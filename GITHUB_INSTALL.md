# GitHub 安装与版本更新

## 状态和边界

- 这是 `com.yukino.vrchat-managed-editing@0.1.0-preview.1` **临时工程验收候选版**。
- 独立分支：`managed-editing`；固定 Git 标签：`managed-v0.1.0-preview.1`。
- 原只读包位于根目录，仍为 `com.yukino.vrchat-readonly-mcp@0.1.1`。其21个发布文件保持原字节，原标签 `v0.1.1` 和 `main` 不变。
- Linux本地检查及独立源码复审已完成，**不代表 Windows/Unity 编译、渲染、Undo、Prefab 或实机调用通过**。
- 已审查的源码文件保留原字节。其README中的“本地候选/此前未发布”描述记录的是先前阶段；Git分发说明以本文件为准，Unity未验收状态不变。
- 不上传模型、场景、纹理、实际工程、凭据、本机原始诊断日志或编译缓存。

## Unity 通过 Git URL 安装

先在可丢弃的 Unity 2022.3 工程验收。原工程必须另做备份，且预存未保存修改由本人处理。

Package Manager → `+` → **Add package from git URL**，按顺序安装：

### 1. 固定基础依赖

```text
https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#v10.2.0
```

### 2. 原只读诊断扩展

```text
https://github.com/YukinoStuki2/VRchat_Agent.git#v0.1.1
```

已安装同版本时不要重复添加。

### 3. 可选受控编辑扩展

```text
https://github.com/YukinoStuki2/VRchat_Agent.git?path=/Packages~/com.yukino.vrchat-managed-editing#managed-v0.1.0-preview.1
```

必须保留 `?path=/Packages~/com.yukino.vrchat-managed-editing`，否则会选择根目录只读包。

若此前从磁盘安装的是同名编辑扩展，先移除旧包引用，再添加Git版本；不要同时留Assets脚本副本或重复包。这里移除的是插件引用，不是删除模型。出现编译错误就停止，不开放任意脚本/通用写工具绕过。

通过Git安装只会更换项目插件源码，不会替你开启授权、保存场景、启动桥接入口、修改Hermes配置或建立SSH隧道。

## Windows受限入口必须单独取得

UPM安装可选子包不会把仓库的 `Tools~` 安装成Windows服务。下载同一标签的完整源码ZIP并解压到固定目录：

https://github.com/YukinoStuki2/VRchat_Agent/archive/refs/tags/managed-v0.1.0-preview.1.zip

进入 `Tools~/managed_bridge/`，按其中的 `README.zh-CN.md` 操作。需要Python3.11或更新版本；只使用标准库。首次启动命令：

```powershell
py -3 bridge.py --upstream http://127.0.0.1:18081/mcp --listen 127.0.0.1 --port 18082
```

**先人工关闭所有原始18081直通通路（包括旧28080→18081隧道），再切换受限入口。** 仅安装编辑扩展并不能约束原始MCP通用写工具。

初次验收先保持权限关闭；核对唯一期望Unity工程、工具注册和拒绝路径后，仅开Preview，再进行单独授权的应用与恢复验收。

## 未来怎么更新

1. 新改动先在开发分支完成测试和独立复审，再发布**新标签**；不移动或覆盖已经发布的标签。
2. 阅读新版本说明并备份工程，关闭授权窗口、停止本次专用桥接/隧道。
3. 将编辑包Git URL的 `#managed-v...` 改为目标新标签，重新等待Unity导入/编译。不要使用移动的 `#managed-editing` 或 `#main` 自动追更。
4. 若入口也有更新，下载该标签完整ZIP，单独更新Windows桥接文件；UPM不会代替这一动作。
5. 重新验证编译、工具名单、默认关闭、预览/应用/恢复。确认后由本人重新授予小范围权限。
6. 回退代码可恢复原固定标签，并匹配同版桥接文件；**代码回退不等于模型权重恢复**，权重仍需Undo/精确恢复或工程备份。

完整流程见 `START_HERE.md` 和 `Tests~/UNITY_ACCEPTANCE.md`。当前没有建立自动更新、定时任务或后台常驻部署。
