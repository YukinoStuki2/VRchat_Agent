# 分发验证状态（非可安装 Candidate）

## 实际源码载荷与许可收集（2026-09-30，当前）

- `assemble_source.py`在内存中校验并组装源码载荷，不创建ZIP、不批准或安装；`source-inputs.json`是明确的309输入清单。658份输出含稳定meta、Editor程序集/manifest、Runtime~固定入口与源码许可。真实复制后的载荷已运行跨语言私有管道/门控联调，不依赖指回开发树的软链接。
- `license_inventory.py`收集当前平台锁定安装中的LICENSE/NOTICE原文，验证RECORD哈希、缺失声明及补充来源。Linux74依赖、85份记录已实际核验。Windows Actions `36624382991`已在全新hash-lock安装后独立收集：74依赖、99份正文全部核对，实际74个wheel的pip报告hash与各自锁条目匹配。没有直接复用Linux清单。
- `fastmcp-slim 3.4.7`的缺正文采用固定上游LICENSE补充；源码pyproject与sdist字节一致，具体来源、版本和hash在`license-supplements.json`。`selected_wheel_hashes_verified=false`与`cpython_redistribution_verified=false`明确保留：当前收集器不把RECORD校验冒称便携Python/完整wheel供应链验收。Windows pip额外保存原生install-report供精确wheel来源核对。
- 仍然没有完整Candidate ZIP或真实Candidate VPM安装/ALCOM验收。下面缺项列表是旧阶段记录：Windows依赖实装、私有引导等已完成有限验证；真实客户端/完整发行/最终独立批准尚缺。

## Windows实装与启动测试（2026-09-30，历史）

固定哈希锁已在Windows2022 CPython3.11全新venv实际安装74个适用包并读回；身份4、内存TLS5、真实CLI6、受限监督器4测试有Actions产物。venv删除和源hash前后/本地比对见最新接受记录。此处取代下文“Windows尚仅解析”历史状态；不证明便携Python发行/完整许可或真实Unity产品安装。


## 2026-09-30新增：候选私有传输源布局

`materialize_owned_transport.py`产物是候选包内独立C#类型，不是重写/覆盖安装的上游包。固定commit、补丁hash、asmdef GUID均核验；重复构建字节一致，源漂移与非空目标拒绝，LICENSE/meta/provenance随源保留。当前4项布局测试通过，OD001先缺失失败后通过；其余是既有校验的characterization。跨程序集门控OD002/003先失败后通过。实际TLS tests已直接编译包内生成源，并核对重建一致。

这只完成可复现源码布局，尚非完整manifest/许可清单/可安装Candidate，未运行真实Candidate安装或ALCOM。不要将此前合成vrc-get五项结果升级成该产品包验收。正式私有引导、Windows依赖及全产品打包门槛仍缺。


目前仅完成依赖与包管理验证基座。**没有完整 Candidate ZIP、没有产品批准、没有更新 VPM 索引，也没有执行用户工程的 ALCOM 安装。**

## Python 依赖

- `distribution/requirements.in` 固定当前测试所用的直接依赖。
- `distribution/tested-constraints.txt` 记录测试环境的已安装版本约束；不是便携运行时。
- `distribution/requirements.lock` 由已有 `uv pip compile --universal --python-version 3.11 --generate-hashes` 生成，包含平台条件与分发哈希。
- `evidence/distribution-parent-clean-install.json`：使用独立临时 venv，`uv pip sync --require-hashes --only-binary :all:` 实际安装 74 个 Linux 包；复跑 AU001、AU003、AU005，通过后删除临时环境。
- `evidence/distribution-parent-windows-resolution.json`：Windows x64 的依赖解析 dry-run 成功，**不是 Windows 实装或执行**。
- `evidence/distribution-resume-lock-rebuild.json`：离线重建后，逐行比较非注释依赖条目、环境标记与所有哈希，一致；仅忽略生成命令注释和缩进，不修改原锁。

复现解析（在 `Candidate~` 目录中，输出到新的临时文件，不覆盖历史锁）：

```sh
uv pip compile --offline --universal --python-version 3.11 --generate-hashes \
  --constraint distribution/tested-constraints.txt distribution/requirements.in \
  --output-file /tmp/candidate-rebuilt-requirements.lock
```

这仅是开发/构建命令，不能放进运行启动器。产品必须使用预先配置、审核并带来源证据的运行时，启动时不得自行安装依赖。已隔离的原生代码与 MCP SDK 补丁仍需单独打包和逐文件校验，锁文件不能代替它们的来源记录。

## 真实 vrc-get，合成包测试

- `evidence/distribution-vrc-get-provenance.json`：核验缓存的官方 vrc-get v1.9.2 Linux 二进制，与官方 GitHub Release asset 的 SHA-256 一致。
- `distribution/verify_vpm_fixture.py`：复用原有隔离 smoke workflow，使用 Python 标准库建立短时 loopback 服务、独立 HOME/XDG 状态和合成 Unity 工程；包内只有测试说明与 manifest，不含 Candidate 实现。
- `evidence/distribution-parent-vpm-fixture-final.json`：新装、升级、明确 `downgrade`、卸载保留无关文件、错误哈希拒绝，五项通过。各操作执行真实 vrc-get，而非模拟返回。
- 该报告核验服务线程结束、监听关闭、子进程与临时目录消失。
- 首次脚本把降级误用为 `install`，vrc-get 返回 `nothing to do`；原失败日志 `distribution-parent-vpm-fixture-run.json` 保留。改为官方 `downgrade` 后重新完整执行，未更改 vrc-get 或测试判据。

**不得用合成包测试通过替代真实 Candidate 的新装、升级、降级和卸载测试。** 没有绕过 `build_candidate.py` 的完整性门槛。

## 仍未完成

1. Windows 运行时及依赖真实安装/执行，便携 Python 的固定来源、许可证与分发验证。
2. 每个实际交付包的许可证正文、NOTICE/来源与 wheel/文件哈希。当前报告只记录元数据；其中五项 License 字段缺失，不能当作许可交付完成或没有许可证。
3. Unity 可信入口、sidecar 服务身份验证、分客户端授权与生命周期闭环。
4. 完整代码冻结后的独立复核、真实 Candidate 包管理验证与 ALCOM/Unity 验收。
5. 正式发布和现用升级须另行批准；候选 CI 分支不等于发布通道。
