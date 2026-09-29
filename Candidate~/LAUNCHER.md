# Candidate 受限按需启动器

## 已接通的所有者API（2026-09-30）

`create_owned_run`固定完整配置，`supervise_owned`复用既有监督器并验证本轮TLS和门控只读status。SDK会话成功DELETE、探针线程退出、runtime进程清理分开报告；ready在停止/失败时清零。没有CLI参数可将任意JSON转为此权限对象，未接Unity/客户端入口。没有扩展SSH命令allowlist；SSH子进程仍不继承runtime材料。


## 已实现与未验收

`launcher/` 是候选专用、无安装行为的进程管理模块。复用旧 `windows_processes.py` 的原字节（MIT），没有导入旧 supervisor、bridge、raw-upstream 或手写 MCP 探测。只启动自身 Python 解释器下的 bundled `runtime/`，以及可选的固定 OpenSSH 反向转发；不会启动 uv/uvx、下载依赖、扫描/杀掉占用端口的未知进程或访问真实 SSH 配置进行发现。

**当前 CLI 缺可信 runtime binding 时返回 `BINDING_REQUIRED`，不会启动任何进程。** 本模块没有发明认证协议、批准入口或将 loopback/TCP 可连接误当认证。父级需完成下述固定集成接口，才可作为可安装包中的启动路径。当前不是 ALCOM/Unity/真实 SSH 验收完成。

## B1独立反例修复（父级验证）

独立审查发现 `RuntimeBinding.environment=None` 误选无凭据的通用/SSH环境路径。原反例先复跑失败，再在runtime启动前明确要求字典，原环境字段校验继续生效；缺失凭据现在 `BINDING_INVALID` 且零spawn。原反例/红测保留，新增L026含六类缺失/无效环境。父级26项通过、4个Windows用例在Linux明确跳过；证据 `evidence/launcher-b1-result.json`。B1修后独立delta待，不将旧审查改为完整通过。

Windows W002仅验证spawn完成后的supervisor崩溃；CreateProcess suspended到Job分配之间的崩溃窗口未解决。Linux runner超时后代清理存在独立审查标注的未测边界，不以本轮正常退出证明异常路径。

## 文件与路径约定

打包后保持 `launcher/`、`runtime/`、`native/`、`dependencies/` 为同级。`launcher/candidate_launch.py` 固定使用 `Path(__file__).resolve().parents[1]/runtime`；用户配置不能替换 executable、runtime 路径、argv、shell、SSH 选项或环境。

- runtime argv 严格为 `[sys.executable, '-B', bundled_runtime, '--project', project, '--port', str(local_port)]`。
- runtime 自己选择 `dependencies/mcp-1.29.1` overlay；启动器不复制 SDK 选择逻辑。
- Python 3.11+ 及 runtime 依赖须事先存在；不提供自动安装降级。
- SSH 路径：Windows `%SystemRoot%/System32/OpenSSH/ssh.exe`；Linux fixture `/usr/bin/ssh`。PATH 中的任意同名程序不能替换 SSH。Windows 的解释器与系统目录属于本地受信部署边界，并非管理员沙箱。

## 配置与 CLI

Python 模块接受且只接受：

```python
config = {
    'project': 'exact-native-projectHash',
    'parent_pid': 12345,
    'local_port': 34123,
    # 无 ssh 对象则完全本地，不创建隧道
    'ssh': {
        'host': 'explicit-host.example',
        'user': 'restricted-user',  # 可省略，空值使用本机 SSH 用户
        'port': 22,                # 可省略
        'remote_port': 34124,
    },
}
```

`project` 为原样保留的 1..128 ASCII 字符 `[A-Za-z0-9][A-Za-z0-9_.-]*`，不规范化非法值、不接受开关式 token。`parent_pid` 1..4294967295；local/remote port 都是 1024..65535 的 int（拒绝 bool）；SSH 服务端口 1..65535。SSH host/user 沿用旧严格 allowlist，不支持 SSH config alias、IPv6、任意 ProxyJump/ProxyCommand/附加转发。

```text
python -B Candidate~/launcher --project native-project-hash --parent-pid <UnityPID> --local-port 34123
python -B Candidate~/launcher --project native-project-hash --parent-pid <UnityPID> --local-port 34123 --ssh-host explicit-host.example --ssh-user restricted-user --ssh-port 22 --remote-port 34124
```

这些是接口示例，不是让用户现在安装/连接真实工程的命令。当前缺适配器/凭据时 exit 2，stdout 一行 JSON `code=BINDING_REQUIRED`。非法参数 exit 2 `CONFIG_INVALID`，不回显可能含秘密的原始 argv；`--help` 仅打印帮助。进程运行错误 exit 1，正常停止/父退出 exit 0。

CLI 默认在前台。集成方保持重定向 stdin 打开，写入 `stop\n` 或关闭 stdin 即停止；任意首行/EOF 都采取安全停止。SIGINT/SIGTERM 同样置 stop。stdout 是有界字段 JSON 状态，末行是最终状态（可能与先前状态重复）；不得将 stdout 解释成 MCP 协议。无常驻服务、自动重连、导入启动、恢复旧权限或任意外部 stop-PID API。

## 父级准确集成接口（必须补完）

### 程序内

```python
from launcher.candidate_launch import RuntimeBinding, supervise
import threading

binding = RuntimeBinding(
    environment=runtime_defined_credentials,  # 本地受信代码创建；不是远程 JSON
    ready=threading.Event(),                  # 初始必须 unset
)
stop = threading.Event()
result = supervise(config, binding=binding, stop=stop, report=local_status_callback)
```

`RuntimeBinding` 不是认证凭据本身，也不验证其真实性。它是**本地受信集成对象**，不得由远程工具、CLI JSON 或模型自报布尔值构建。缺失/空 credential env、预先 ready、失败或重用的 binding 均 fail closed。

- `environment`: 仅允许 `VRCHAT_AGENT_[A-Z0-9_]{1,64}` 键，1..32 项；值非空、不含 NUL，每项最多 16384 字符，总计最多 65536。这里仅保留安全的传输命名空间，**没有定义 token/文件内容/认证格式**。父级必须让 runtime 明确消费并验证自己定义的字段。秘密不进 argv、状态或 SSH 子进程；账号密码、客户端令牌和签名私钥不落盘。用户在本轮明确批准唯一例外：每次启动的一次性 TLS 私钥可暂存当前用户受限临时目录，加载后立即删除，必须验证 Windows 权限与异常退出清理；未验证前不启用。对象 repr 隐藏 env。
- `started` Event：runtime 已 spawn 后置位。父级此后使用成熟 SDK/自己的可信绑定方案核验**该自有进程、确切工程和所需身份**。不得仅用打开端口或 caller 自报的项目字段置 ready。
- `ready` Event：父级仅在上述核验成功后置位。初始 runtime 等待上限 20s；无 ready 不启动 SSH。
- `failed` Event：身份验证失败/撤销/连接不可信时置位，启动器停止自有 runtime/SSH；ready 不是持续身份检查的替代。
- `cancelled` Event：进入清理时置位，父级取消并 join 自有探测任务、清理已分配的 SDK session。启动器不自行分配 MCP session。
- `used`：单次使用，不用旧 binding 自动重启。父级的探测必须有截止、取消和自己的清理证明。
- `report(dict)`：本地快速回调；不得阻塞、联网等待或输出原始秘密。不是不受信插件执行入口。

`supervise` 返回字典字段：`phase`、`code`、`stage`、`component`、`exit_code`（未观测到则 null）、`process_cleanup_complete`；失败增加 `failure_code`。最终 `code=CLEANUP_FAILED` 不覆盖原始 `failure_code`。`process_cleanup_complete` **只代表自有进程/reader 清理，不代表 Unity 撤权、MCP session 或远端监听清理**。

### CLI 固定适配器

父级只在自身获准目录增加 `runtime/launcher_binding.py`，固定导出：

```python
def create_launch_binding(config: dict):
    # 本地凭据缺失时 return None。
    # 已准备安全凭据与有界 ready/failed 监视时，返回上面的 RuntimeBinding。
    ...

def close_launch_binding(binding) -> bool:
    # 取消/join探测；SDK会话/注册资源有证据清理完毕才返回 True。
    ...
```

以上是合同描述，不是已写入 runtime 的 stub。启动器只从该固定 bundled 路径载入适配器，不接受用户指定模块路径/任意 shell。`create_launch_binding` 不得自己启动 runtime 或 SSH，也不能在 spawn 前置 ready。适配器若需 credential env，应只读取本地授权字段；不要传整个 `os.environ`。加载/创建必须有界且异常前自行清理；`close_launch_binding` 必须有界，`True` 才写 `binding_cleanup_complete=true`，否则 CLI 报 `BINDING_CLEANUP_FAILED`。本子任务没有改 runtime/C#/包，不假称已完成此适配器。

## 生命周期与 SSH 边界

- 同一 OS 用户、同一 exact project：跨进程文件锁，只允许一组 cooperating launcher；不同工程互不抢锁。默认锁目录 Windows `%LOCALAPPDATA%/VRChatAgent/launcher-locks`（无 LOCALAPPDATA 回落 TEMP），Linux `/tmp/vrchat-agent-launcher-<uid>`。锁文件只含 `0`，无秘密；停止释放 OS 锁，**不 unlink 锁文件**，避免 inode 替换允许双启动。fixtures 使用临时根并在测试后删除；不是清理用户资产。
- Windows 原生所有权增量：保留父 HANDLE；STARTUPINFOEX 的 JOB_LIST 在 CreateProcessW 时原子关联非继承 kill-on-close Job，suspended 出生后再 resume，禁止先创建再分配的回退；显式 HANDLE_LIST；job accounting 清零确认。W005已复现并关闭创建后/分配前监督进程崩溃窗口，W001–006真实Windows通过。不是完整binding/bootstrap验收。
- Linux 只作本地合同/合成进程测试：pidfd 持有父身份；每个 child 新 session/process group；退出 poll 使用 WNOWAIT 保留 leader PID，最后 group signal 前不 reap，避免 PID/PGID 复用误杀。正常/超时清理后等待并验证组不存在。**不提供 Linux supervisor SIGKILL/crash 的 Job 等价保证，也不保证阻止恶意后代 setsid 逃逸**；不要当 Linux 生产部署验收。
- 占用本地端口仅拒绝；不接管、不扫描 owner、不杀未知监听。检查/真正 bind 间存在竞争，因此 TCP 检查不能替代父级可信 readiness。
- SSH 使用 `-F` 空设备抑制用户/系统 config，固定 `-N -T -v`，BatchMode、StrictHostKeyChecking、ExitOnForwardFailure、连接/保活超时，禁 ProxyCommand/ProxyJump/LocalCommand/agent forwarding/X11/control multiplexing。
- 唯一转发是 `-R 127.0.0.1:<remote_port>:127.0.0.1:<local_port>`；账号密钥/known_hosts 由 OpenSSH 本地管理，启动器不读写密码/密钥/真实 SSH 配置，不自动接受 host key。
- 完全匹配 OpenSSH 的动态端口成功行才记 `FORWARD_ESTABLISHED`。这只是转发 ACK，不是 MCP/Unity/实际远端 bind 范围已核验；真实部署还需服务端 `GatewayPorts no` 与远端回读，否则不得宣称远端仅 loopback。
- 停止先切自有 SSH，再清理进程组/Job；不碰用户预存的旧隧道和服务。错误不自动重试。

## 有界诊断与证据

stderr 按块读取，每行最多 4096 bytes，超长整行丢弃，合规 EOF 尾行仍分类；只保存 allowlisted category，不保存完整行/路径/命令/环境。SSH auth/hostkey/forward/refused/timeout；runtime dependency/arguments/port busy；未知退出 `PROCESS_EXITED`。保留原 stage/component/已观测 exit code。reader 在 close 时交付 EOF 尾因由，只丰富先前已观测的 `PROCESS_EXITED`；不在 closed HANDLE 上 repoll、不将人为停止变成错误。

执行：

```text
python -B tests/test_launcher_candidate_runner.py <一个未用过的证据标签>
```

runner 使用临时 HOME/USERPROFILE/TMP，`-B -W error::ResourceWarning`，固定 launcher-only unittest discovery；旧失败证据绝不覆写。`evidence/launcher-completion-01..16-*` 保留真实 RED/GREEN 与中间回归；最终准确统计及 hash 见 `evidence/launcher-completion-result.json`。首轮就通过的继承行为/补充检查明确是 characterization，不把它们冒称 RED。Windows-only 四项在 Linux 跳过，不能计通过；在真实 Windows 手动运行：

```text
python -B tests/test_launcher_candidate_windows.py
```

涵盖 Job 后代清理、supervisor crash、父 HANDLE 退出、显式 stop。代码来自旧 Windows live suite，改固定候选路径、用例 ID、-B；本轮**没有 Windows 内核执行**。来源 commit/hash、片段和 MIT 许可见 `launcher/PROVENANCE.json`、`launcher/LICENSE`。

最终证据记录真实 Linux 合成 child/parent/descendant 的清理断言，以及 runner 20ms 采样捕获的 PID/starttime 退出复核。采样不保证看见每个极短子进程，因此不将 observed 数字当所有创建总数。没有真实 runtime、SSH、Unity、客户端连接或 VPM 安装测试，也没有网络安装、提交、推送、发布或现用配置修改。父级仍需做可信 binding、包布局/入口、Windows与真实 SSH、Unity/ALCOM 的独立验收。
