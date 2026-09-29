# 候选开发快照（不是可安装包）

本目录包含进行中的候选源码及父级测试。没有产品批准，不能添加到 ALCOM 或真实 Unity 工程；`package/package.json` 尚未创建。主分支、历史包与 VPM 索引不由本快照更新。完整状态见 `STATUS.md`，原始失败与本机测试证据保留在开发机。

## 可重复的验证范围

本轮先用 `git write-tree` 与 `git archive` 导出暂存源码到新临时目录，然后从该目录运行，不回读原工作树的 Candidate 代码。仍使用以下**明确的外部开发依赖**，并非空白机器的自包含安装测试：

- CPython 3.11 测试环境：`/home/ubuntu/.cache/uv/archive-v0/7z4PORN2YM2xSubx/bin/python`。直接/传递依赖锁在 `distribution/requirements.lock`；运行时显式选择随源码提供的 MCP 1.29.1 修订副本。
- .NET 8 SDK：`/home/ubuntu/.local/share/vrchat-agent-dev/dotnet/dotnet`。Unity API/业务 handler/人审由明确标记的 fixture 替代，.NET 测试不等于 Unity/Mono 导入。
- 固定上游：`/home/ubuntu/.hermes/tmp/coplaydev-unity-mcp-v10.2.0/MCPForUnity`，commit `30d22075093d1d35dfb0091c1c7550e9ad948577`。来源、补丁与输出哈希见 `dependencies/coplay-10.2.0-owned/PROVENANCE.json`。
- Linux 的 `patch`、pidfd、`/proc` 以及受支持的文件租约内核功能。Windows 特有行为由授权候选分支的真实 Windows Actions 验证，不能以 Linux skip 代替。

这些路径是开发验证脚本当前的显式配置，不是最终用户前置要求。便携运行时与通用复现入口仍需完成。

## 在新的开发快照中运行

以下命令已在隔离 Git 树中实际执行。从 `Candidate~` 开始；每次使用新的快照，避免覆盖旧证据。不要在真实 Unity/头像工程运行它们。

```sh
python3 -I -S -B evidence/runtime-editor-pipe-isolated.py

env -i PATH=/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 \
  /home/ubuntu/.cache/uv/archive-v0/7z4PORN2YM2xSubx/bin/python \
  -B -W always::ResourceWarning tests/verify_unity.py staged-source

env -i PATH=/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 \
  /home/ubuntu/.cache/uv/archive-v0/7z4PORN2YM2xSubx/bin/python \
  -B -W always::ResourceWarning tests/verify_owned_transport.py staged-source gates editor
```

- 第一组逐方法新进程，断言实际执行集及唯一计数，拒绝告警、源码漂移和未清理资源。LC006 不算 skip，由第二组新编译 C# gate 实际执行。
- 第二组包含新编译门控、协议及 LC006。第三组是真实 C# 进程私有管道、Python 子进程、TLS、MCP SDK、受控传输与门控；外层另查全部已跟踪后代和监听。
- 测试默认拒绝覆写既有证据。不通过改标签掩盖旧失败；新标签只用于修正后的新轮，原始记录保留。
- 冻结测试通过只是父级有限验证。子代理暂停期间独立复核仍待进行，不得据此生成 `independent_source_reviews_passed=true`。

## Windows 证据

`.github/workflows/candidate-dependencies.yml` 使用干净 venv 按 hash 实装，覆盖身份/TLS/入口/监督器/编辑器私有管道与真实 C# owner。Windows venv redirector 的处理保持精确子 PID/父 PID 校验；实际解释器直接启动并保留已选择 venv。

`.github/workflows/candidate-kernel.yml` 单独覆盖真实 HANDLE/junction 与原子 Job 所有权。Windows CI 不自动证明真实 Unity 包、客户端配置、许可清单、VPM 安装/升级/卸载或完整产品安全。

## 打包门槛

`build_candidate.py` 仍拒绝缺实现、缺独立审查或源码不一致的 proof。`test_packaging.py` 仅证明打包器拒绝和确定性规则；`verify_vpm_fixture.py` 的合成包安装测试不是本 Candidate 的安装证明。没有为本轮源码快照提供安装 ZIP、Release 或 VPM 条目。
