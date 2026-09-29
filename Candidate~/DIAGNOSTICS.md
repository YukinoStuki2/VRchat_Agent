# 独立诊断：Windows实现增量与本地操作者CLI

## 2026-09-29续接提示（优先于下方历史状态）

- Windows第三次真实内核run `36461636092` 在 `512f9a2` 上7/7通过、0skip；artifact digest、输入hash、HANDLE关闭及fixture删除均父级核对。只修自建fixture短路径并给每个负例正常读取对照，生产规则未放宽。见 `evidence/diagnostics-windows-parent-acceptance.json`；旧两次失败仍保留。此测试修正没有独立批准。
- Linux同长度修改漏检已通过30次原始观测定位到stat碰撞（15次）；`snapshot.py`新增原生F_RDLCK租约，已有writer/可写mmap拒绝，读取中写入会中断并拒绝结果。34项回归通过；原6项snapshot+新增6项租约各10轮通过，原断言未改，原失败保留。见 `diagnostics-linux-lease-regression.json`、`diagnostics-linux-lease-repeat.json`。本地增量尚无独立批准；Windows run的snapshot哈希早于此Linux增量，后续冻结仍须全平台复跑。
- Linux租约只允许x86_64/aarch64的主线程同步读取、默认且未屏蔽的SIGIO；不支持的文件系统、信号策略或线程环境会拒绝，绝不退回mtime/重复读取猜测。租约不能冻结目录或跨文件事务；仍保留描述符/祖先身份复核。
- 尚无完整诊断/产品批准，未接入现用Hermes/Codex、未读取真实工程；main、历史发布与VPM索引不动。

## 历史实现状态（不是当前Windows实测或发布批准）

- `windows_handles.py` 实现 stdlib ctypes Win32 路径：从本地固定盘根开始逐层 `CreateFileW`，仅 `FILE_SHARE_READ`，保持所有祖先及最终文件 HANDLE 到读取结束；`FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS`；检查磁盘对象、目录属性、reparse 标志、最终句柄路径、文件单硬链接、大小；用同一个 HANDLE 调用 `ReadFile`，之后复核身份/大小/写入时间/ChangeTime和祖先身份/最终路径。**没有 Path.resolve→按路径重新打开源文件**。
- 拒绝 UNC/设备路径、相对盘符、ADS、点段、重复分隔符、尾点/空格、DOS保留名、reparse/junction/symlink、hardlink及大小写重复选择。忙碌源文件/不兼容共享模式直接拒绝，不放松锁定以读取仍在写的日志。
- Windows 临时外层目录以受保护、可继承的 owner-rights + SYSTEM-only DACL **创建时**建立；内部复用 `TemporaryDirectory` 处理只读文件删除。不把 chmod 当 Windows ACL。此处实现已做替身ABI合同检查，**Windows访问控制实际效果尚待CI/实机验证**。
- `cli.py` 独立于Unity；先做完整UTF-8脱敏快照，再通过真正的本地控制台展示JSON转义全文，操作者输入绑定内容的完整 SHA-256 确认串后才创建MCP服务。无 `--yes`、环境自动批准或 MCP approve 工具；stdin 是MCP流，不能用于批准。预览内容/提示不会写到MCP stdout。无本地控制台时失败关闭。
- 延续原每文件1MiB/64文件/总原文8MiB/300秒lease及敏感名称/文本检查。启发式脱敏不保证无秘密；只选必要合成或明确授权文本。预览未完成就过期时不能交付，**阻塞等待操作者期间没有后台磁盘删除定时器**，关闭/取消控制台才退出上下文。
- 批准digest在服务请求前后复核；内容变化撤销lease并拒绝交付。MCP仍仅暴露原四项只读工具，Roots固定副本；仍是首次数据/目录SDK会话绑定，不是客户端真人身份认证。
- 按需stdio会话EOF、服务异常、期限结束、取消退出时撤销lease、等待SDK关闭后端，再删除自身快照。Linux真实PTY→CLI→FastMCP→固定官方Node链路已验证EOF与SIGTERM清理；预览阶段SIGTERM也清理。无监听、无常驻服务。

## 最小CLI与兼容性

从 `Candidate~` 执行（Windows源root保持原样；选择文件用 `/` 分隔）：

```powershell
py -3.11 -B diagnostics/cli.py preview --root 'C:\DiagFixture' --file 'Editor.log' --file 'Editor/Test.cs' --task 'compile-check'
py -3.11 -B diagnostics/cli.py serve --root 'C:\DiagFixture' --file 'Editor.log' --task 'compile-check'
```

- `preview` 仅做本地预览/确认校验并删除副本；不会交付或启动Node。`serve` 批准后在stdin/stdout运行标准MCP，控制台保留给本地人审。退出码：0正常/预览完成，2失败关闭，3操作者拒绝，130中断。
- `serve` 的宿主必须保留本地控制台同时连接stdio管道。无控制台的桌面MCP自动启动当前会拒绝；**尚未提供Tkinter窗口、桌面客户端配置或Hermes/Codex已接入声明**。用户自己的终端/管理员控制台操作不属于MCP沙箱。
- `capture(root, files, task_id=..., temp_parent=...)` 原签名保留；新增Windows分派。`create_server(snapshot, *, approved_digest=None)` 是向后兼容的本地嵌入接口，旧调用者仍负责可信本地批准；唯一CLI交付路径强制传入批准digest。这个参数不是远程工具。
- preview、Windows内核CI检查仅需Python 3.11标准库。serve复用现有隔离 **FastMCP 3.4.7 / MCP 1.29.1** 和现存 `@modelcontextprotocol/server-filesystem` 0.6.3 fs01-candidate；没有重写文件MCP、安装新依赖或修改SDK。
- 固定Node入口仍为 `Experiments~/p0.2/filesystem/fs01-candidate/src/filesystem/dist/index.js`，需相应完整已固定依赖树，不是只复制单个JS。Windows通过本机PATH找到 `node.exe`，Linux保持已有 `/usr/bin/env -i /usr/bin/node`。**这仍是开发布局，Windows打包/Node依赖搬运归父级，当前没有可分发的filesystem包**。

## Windows CI入口（父级执行；当前机器没有Windows）

```powershell
py -3.11 -B diagnostics/verify_windows.py --output evidence/diagnostics-completion-windows-ci.json
```

该入口**不需要npm/Node/FastMCP**，不会安装依赖。运行本地合成fixture，临时HOME/USERPROFILE/APPDATA/TEMP，保留必要Windows系统环境；JSON目标必须不存在，不覆盖旧证据。输出完整测试ID、每项状态、原始unittest输出、输入hash、fixture删除和未关闭HANDLE数量。exit0要求真实Windows且所有用例通过、没有skip、cleanup与源码hash核验通过；失败exit1，不可用/skip exit2。

`tests.test_diagnostics_windows_kernel.WindowsKernelTests`：

- WK001：真实HANDLE→UTF-8脱敏快照→原文变化不影响副本→删除。
- WK002：实际硬链接和 `cmd.exe /d /c mklink /J` junction拒绝（含作为root的junction），finally只清自有fixture。
- WK003：读期间真实文件/目录改名与写入失败，结束后可写/改名，验证锁定及释放。
- WK004：真实文件symlink拒绝；缺少Windows symlink权限会明确skip并使该CI门不通过，不能冒称成功。
- WK005：通过 `GetNamedSecurityInfoW` 回读外层和叶文件DACL，验证受保护外层、只含OW/SY的ACE；不等于跨用户攻击/管理员隔离实测。
- WK006：已有写句柄导致导出拒绝。
- WK007：跨根、ADS、DOS设备名、根别名、UNC/设备路径拒绝。

本机 `diagnostics-completion-windows-ci-unavailable-final.json` 是 **exit2 / windows_kernel_executed:false / passed:false / 7 skipped**。早期 `windows-kernel-unavailable` 只覆盖当时6项，原样保留，不替代最终7项清单。

## 本轮证据口径与尚缺边界

- 新增DW001–DW010为Linux运行的Windows策略/ABI替身与CI拒伪绿检查，**不能计为Windows内核通过**。DC001–DC004为预览/批准digest/期限与异常清理/无控制台拒绝；DC005真实PTY及Node链路是first-green characterization，不伪造RED；DC006/007先分别真实复现SIGTERM导致-15退出，再修复。
- 逐片原始RED/GREEN、最终回归、准确完整ID及文件hash见 `evidence/diagnostics-completion-*`；旧DW003正则转义错误、DW006初版替身错误、旧审查429及旧失败全部保留。旧11项测试及其断言未放松。
- Windows内核、ACL/junction/共享锁实际行为和Win32 ABI实测；Windows控制台预览、Node/SDK stdio退出、Job Object/后代清理；Hermes/Codex真实连接；Windows/Unity/ALCOM安装均**尚未在本轮执行**。SDK Windows Job Object是原生best-effort实现，可能因缺pywin32或分配失败回退，当前不宣称Windows进程树强保证。
- SIGKILL、TerminateProcess、解释器崩溃/断电不能依赖finally，可能留下私有脱敏副本；**尚无崩溃监护/跨次启动清扫器，不自动删除未知目录**。未把有界正常退出等同于任何异常退出都无残留。
- 当前是开发增量，不是独立安全批准。历史审查429不被替换。未提交/推送；用户新增批准的候选分支/Actions由父级统一处理，不改main/历史发布/VPM索引。

---

# 以下为先前Linux候选历史记录（原文保留，不代表本轮最新实现状态）

仅由本地可信操作者选择root/明确文件列表和task；`capture`导出一个私有短寿命文本副本，`create_server(snapshot)`复用固定官方filesystem候选和FastMCP ProxyProvider。不是实时工程文件服务，不启动监听，不注册到Hermes，不构成可安装产品。无修改原工程功能。

## 已实现与父级测试

- Linux descriptor逐层O_NOFOLLOW/O_DIRECTORY打开；文件必须regular、nlink=1，验证的是实际读取FD；完成后复核文件身份/大小/mtime/ctime及祖先目录身份。路径必须明确绝对root+相对文件选择，拒绝别名、越界、symlink、FIFO和hardlink。
- 每文件最多1MiB，最多64文件，总原文最多8MiB；UTF-8文本、批准扩展名、拒绝控制字符/已知敏感名称/私钥内容；常见secret赋值及URL脱敏。**启发式脱敏不保证消除所有秘密**，不能因此批量读取真实凭据。
- 快照容器0700、目录0500、文件0400；与源工程分离，源后改不影响副本。context关闭撤销lease并删除自有临时目录。固定300秒lease，不支持远程续期。
- 本地initialize/ping不启动上游文件服务。数据和目录请求在前后校验lease，首次数据/目录请求绑定一个真实SDK会话，其他新会话不能继承。此为私有连接中的会话约束，不是可信真人认证；未做真正操作者UI/客户端交付绑定。
- 只暴露read_text_file/list_directory/get_file_info及诊断status；不转发下游Roots，后端Roots固定副本。写工具、资源、提示不开放。
- `tests/test_diagnostics_snapshot.py` 6个测试；`test_diagnostics_mcp.py` DM001–003为真实SDK内存前端+真实官方Node stdio后端，3个测试。撤权发生在原生读取完成、响应交付前时结果被拒绝。

## 修复证据与限制

旧`diagnostics-mcp-green-attempt.json`是失败，不是通过。原FastMCPProxy会在initialize先于lease检查启动后端、关闭snapshot后以原始目录错误失败，并出现stdio子进程-9结束。DM002-parent-red真实复现初始化创建后端。

改用原生FastMCP+ProxyProvider，无需复制协议或文件读取器。第一次green命令因构造参数不匹配报错，保留记录；随后测试把首个允许的SDK调用触发的catalog探测误归因到第二次initialize，修正计数归属（未删除无权会话零后端启动断言）。`diagnostics-DM001-003-process-cleanup.json`为最终父级3项通过、每个真实后端returncode=0且PID/进程组消失证据，`diagnostics-snapshot-final-parent.json`为6项通过。

- Windows目前明确拒绝；没有Windows句柄/reparse/ACL实测。
- Linux FD边界不是同UID/管理员/挂载命名空间攻击的OS沙箱。文件权限不是防管理员的不可变存储，跨文件采集也不是原子全工程snapshot。
- 本地确认/显示脱敏预览、只选必要证据、宿主异常退出生命周期、独立审查、日志输出与打包整合尚缺。
- backend路径暂指向冻结P0.2 fs01-candidate；未把历史实验目录依赖伪装成可分发包。新版依赖清单/许可/封装须在打包时核验。

## 审查中断后的父级核验

审查`deleg_fbd8c142`生成了`diagnostics-review.json`与11项最终运行记录，但最终HTTP429中断。磁盘报告写有passed:true/未遇429只代表它写入时的状态，**不作为已完成独立批准**；外部失败通知与历史原始记录并存，不改旧报告。

父级核对报告全部输入hash一致，并执行`diagnostics/record_test.py parent-takeover-final tests.test_diagnostics_snapshot tests.test_diagnostics_mcp tests.test_diagnostics_review`，11个唯一测试通过，见`evidence/diagnostics-parent-takeover-final.json`。DR001通过原始SDK直接调用4个隐藏writer，全拒且未到后端；这些是一个测试的子例，不按4项计数。DR002验证真实时钟下缩短fixture lease过期前后的在途结果拒绝，不宣称已做300秒浸泡。

最终24个真实Node后端全部正常exit=0且PID/进程组消失。早期review instrumentation参数名错误导致-9强退的失败仍保留，不当成功清理。**期限过后只拒绝服务；磁盘副本仍要到capture上下文退出才删除**，崩溃清理/本地操作者流程继续缺失。

所有测试仅synthetic本机fixture。不得据此用于真实工程/凭据或宣称完整取证完成。
