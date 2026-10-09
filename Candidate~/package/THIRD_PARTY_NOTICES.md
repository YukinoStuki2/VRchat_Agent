# 第三方代码与未完成的分发边界

- CoplayDev unity-mcp v10.2.0，commit `30d22075093d1d35dfb0091c1c7550e9ad948577`：MIT。候选包含独立命名C#传输增量、受限原生类型元数据增量及Python Server自有副本。正文见 `Editor/OwnedTransport/LICENSE.md`、`Editor/ScopedReflection/LICENSE.md`、`Runtime~/native/LICENSE`；反射增量的精确变换在 `distribution/materialize_reflection.py`，来源/范围在对应 `PROVENANCE.json`。原有版权声明不修改；来源/补丁/文件hash与代码同行。
- Model Context Protocol Python SDK 1.29.1：MIT。候选包含明确记录的流资源关闭修订；正文见 `Runtime~/dependencies/mcp-1.29.1/LICENSE`，来源及差异见 `Runtime~/dependencies/mcp-source.json`、`mcp-candidate.json`、`mcp-sse-cleanup.patch`。
- 候选自己的代码沿用本仓库MIT LICENSE。复用的启动器来源见 `Runtime~/launcher/PROVENANCE.json`。
- Unity、VRChat SDK及项目插件不由此源码组装器分发。Coplay完整Editor包是固定的外部依赖，不在这里复制安装。

**此清单仅覆盖源码载荷，不代表完整Python二进制/依赖发行的许可已完成。** `Runtime~/distribution/requirements.lock`固定第三方wheel版本与哈希，但不替代许可证正文/NOTICE清单。CPython发行及各平台实际wheel的许可、来源与二进制哈希必须另行核验；缺失时不得通过最终打包门槛。
