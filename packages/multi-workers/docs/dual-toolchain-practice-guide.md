> **入仓说明**（Multi-Workers 仓库，2026-09-21）：本文由 AssetImportGate 项目 PM 窗口写成，原文快照入仓供所有 dual 模式项目引用；WXWork 缓存原件会失效，以本仓为准。框架已吸收其**通用不变部分**（§9.B）：`mw ue-toolchain run`（§2.2/2.3 执行留证 + 错误签名双判 + --watch 前后哈希）、`mw ue-toolchain targets`（§2.1 目标名现查）、`mw ue-toolchain hash`（§5.5 EOL 归一化哈希）。`mw ue-toolchain` 的定义域是 **dual 模式 UE 游戏开发**（游戏仓 + 引擎源码仓 + `.uproject`，MSVC/UBT）：`targets` 与错误签名正则是 UE/MSVC 专用，`run` 的留证/判定纪律与 `hash` 是工具链无关的通用件。**项目特定部分**（§9.A：UBT 参数形态、模态窗处理、夹具分区、日志契约前缀）仍按本文逐项目替换。

# dual 模式项目 toolchain 指南（跨项目可移植）

> **读者**：另一个 dual 模式项目的 **PM 窗口**（一个前台 PM agent + 后台 worker 队列；典型形态 = **UE 源码引擎挂在游戏项目上做引擎侧改造**，Windows + PowerShell 5.1）。照本文即可开工。
> **证据口径**：本文每条命令、参数、坑都标注出处（文件 + 行号 / §节 / sha256）。出处均为 AssetImportGate 项目（引擎侧改造 UnrealEd 的导入闸门 key）2026-09-17 ~ 2026-09-21 的 `.agenticdoc` 材料；sha256 为 2026-09-21 15:5x 快照（见 §10）。找不到项目出处的条目一律标 **【未验证】**。
> **两个工作区**：控制工作区 `F:\FLSpace\AssetImportGate`（`.agenticdoc` 文档树、worker task 目录在此）；游戏根 `E:\CFBH`；引擎根 `E:\CFBH543`（UE 5.5.1 源码构建）。出处：`target.yml:4-7`（`mode: dual` / `game: 'E:\CFBH'` / `engine: 'E:\CFBH543'` / `uproject: 'E:\CFBH\ProjectH.uproject'`）。

---

## 1. 环境事实与 PowerShell 5.1 纪律

**环境实测**（PM 与 worker 双侧一致）：`bash` 工具底层是 **PowerShell 5.1**（本机 5.1.22621.4249）、`python 3.14.3`、`git 2.45.2.windows.1`、worker cwd = 游戏根。出处：`_pitfalls.md` F 条（P83）、`pm-state.md:155`（worker 侧 shell 实证）。

| # | 纪律 | 出处 |
|---|---|---|
| 1 | **无 `&&`**：用 `;` 分隔命令（PS 5.1 不支持 `&&`） | `_pitfalls.md` P83 |
| 2 | **无 heredoc**；反引号会被吞 | `_pitfalls.md` P83 |
| 3 | **`>` 重定向产出 UTF-16LE**（读起来"字符间空格"）⇒ 写文件一律用 write 工具或 python `io.open(..., encoding='utf-8', newline='\n')` | `_pitfalls.md` P84；实例 `S1-build-verify-20260918.md` S1:31 |
| 4 | **控制台是 GBK** ⇒ 含中文/emoji 的 print 会 `UnicodeEncodeError`。校验脚本用 python、输出 ASCII；或写 UTF-8 文件后用 read 工具看 | `_pitfalls.md` P85 |
| 5 | **多行 `git commit -m` 会被拆坏**（后续行被当 pathspec）⇒ 写消息文件 + `git commit -F <file>` | `_pitfalls.md` P86 |
| 6 | **内联 `python -c "..."` 引号会被吞** ⇒ 写脚本文件再跑；同理：用 python `subprocess` + `cmd /c` 启动 .cmd 也会破坏引号（退出码 1 / 0.1 s 空转），直接调 `.cmd` | `_pitfalls.md` P38（B3）；`T-27b §7 #31` |
| 7 | **PowerShell 变量名大小写不敏感**（`$ProbeReport` 与 `$probeReport` 是同一个变量）。属 PS 语言语义；本项目文档无专门踩坑实例【未验证：项目实例】 | 派发规格口径；PS 5.1 语义 |
| 8 | **rg 用法**：只定向检索单个文件或单层目录；一个模式一次（多模式引号易被吞，必要时写 python 探针）；**禁 `rg -r`**；判"存在/不存在"必须用计数（`rg -c`），不得用被 `-First N` 截断的列表 | `_pitfalls.md` P83、P42-44（B4） |
| 9 | **禁全树扫描**：`Get-ChildItem -Recurse` / 全树 `Select-String` 禁用。真实代价实例：worker `design-evidence-r3-r4-r6` 因 30 分钟重复 PowerShell 递归扫描、零产出被终止，改 PM 直执（rg 秒级完成） | `_pitfalls.md` P83；`pm-state.md:58` |
| 10 | **read 工具按会话计字节数上限**（本指南编写会话实测 65536 B，超限即拒绝读大文件）⇒ 读大文件/批量取证改用 python 抽取脚本，把命中行带行号写 UTF-8 文件或打到 stdout | 本指南会话实测（2026-09-21），非项目既有记载【未验证：非项目文档】 |
| 11 | **中文输出到控制台可行做法**（本指南会话实测）：`[Console]::OutputEncoding=[System.Text.Encoding]::UTF8` + `$env:PYTHONIOENCODING='utf-8'` 后再跑 python/rg，中文不乱码 | 本指南会话实测【未验证：非项目文档】 |
| 12 | **上下文防火墙**：read/ls/find/grep 受 deny globs 限制（二进制/资产/缓存目录全部不可读，源码 `.h/.cpp/.cs/.ini` 可读）——派发规格里逐条列出；自己项目的等价物见 `target.yml:20-61` | `target.yml:24-61` |

---

## 2. UE 源码引擎 + 游戏项目的构建

### 2.1 形态与目标名

- 引擎根 = 源码构建的 UE 5.5.1（`E:\CFBH543`），游戏 = `E:\CFBH\ProjectH.uproject`；本类项目改的是**引擎侧模块**（例：`E:\CFBH543\Engine\Source\Editor\UnrealEd\`）。出处：`target.yml:5-6,12-13`。
- **增量构建目标 = `ProjectHEditor`**；Game 目标 = `ProjectH`。目标名**从 `E:\CFBH\Source\*.Target.cs` 确认**（`ProjectHEditor` = Editor / `ProjectH` = Game），不要猜。出处：`target.yml:12,15`。
- Game Target 基线可能本来就红（本例 exit 8：缺 `FAMILY_CN=1` ⇒ `Could not find definition for module 'INTLCore'`，工程侧既有问题）⇒ 验收口径改为**差分**（改动前后错误集合恒等）。出处：`target.yml:16-17`、`pm-state.md:59`（CR-5）。

### 2.2 逐字命令（勿改写）

**PM 增量构建（S8 定案形态，控制工作区根执行）**——出处 `pm-state.md:793`（表中 `**` 为 markdown 强调符，实际命令无）：

```
research\_run_build_pm.cmd <log> ProjectHEditor Win64 Development -project=E:\CFBH\ProjectH.uproject -WaitMutex
```

**基线/S1 形态（同源勿改写）**——出处 `pm-state.md:491`：

```
cmd /c .agenticdoc\research\_run_build.cmd .agenticdoc\research\build-editor-s234.log ProjectHEditor Win64 Development -project=E:\CFBH\ProjectH.uproject -waitmutex
```

**直接调 Build.bat（模板，占位符形态）**——出处 `target.yml:14`：

```
"{engine}/Engine/Build/BatchFiles/Build.bat" ProjectHEditor Win64 Development -project="{uproject}" -waitmutex
```

**渲染后的逐字形态**——出处 `pm-state.md:153`（`{engine}` 展开为反斜杠路径）：

```
"E:\CFBH543\Engine\Build\BatchFiles\Build.bat" ProjectHEditor Win64 Development -project="E:\CFBH\ProjectH.uproject" -waitmutex
```

**参数顺序与 wrapper 语义**（`_run_build_pm.cmd:3,35-37`；arg1 恒为日志路径，args 2..n 为 UBT 参数）：

```
rem Usage: _run_build_pm.cmd <logfile> <target> <platform> <config> [extra UBT args...]
set LOG=%~1
call "E:\CFBH543\Engine\Build\BatchFiles\Build.bat" %2 %3 %4 %5 %6 %7 %8 %9 -MaxParallelActions=16 -Log="%~dp1%~n1.ubt.txt" > "%LOG%" 2>&1
echo %ERRORLEVEL% > "%LOG%.exit"
```

- `-waitmutex`（小写，pm-state:491 / target.yml:14 / S1:12）与 `-WaitMutex`（大写，pm-state:793）**两种写法均有实测运行记录**；语义 = 让并发调用串行等 UBT 互斥锁而不是直接失败（`target.yml:13`）。
- **wrapper 陷阱**：不得用 `%*`/`shift` 转发参数——本机实测 `cmd` 的 `%*` 不受 SHIFT 影响，会把日志路径当 target 名传给 UBT 报 `Couldn't find target`；正确做法是转发 `%2..%9`。出处：`_run_build.cmd:5-9`。
- **应急本地构建**（Horde/UBA 池不可用时）：`_run_build_local.cmd`，同参数序，内部加 `-NoUBA -MaxParallelActions=16`（`_run_build_local.cmd:16`）。

### 2.3 构建前/中/后纪律

1. **构建前查孤儿进程**（否则 `-waitmutex` 只会在排队上烧预算）：`Get-Process cl,dotnet`。出处：`pm-state.md:40②`。
2. **退出码必要但不充分**：退出码落 `<log>.exit`（wrapper 行 37）；实测值：exit 0（S8，`pm-state.md:794`）、exit 6（基线/S1，`S1:14`）、exit 8（Game Target 既有问题）。**必须扫日志找 `error C` / `LNK` / `error :`**——S8 验收把 `exit 0` 与 "`error C/LNK/error:` 命中 0" 并列记录（`pm-state.md:793-794`）；差分验收用**签名集合 + 定位集合三重比对**（新增/消失/计数，`pm-state.md:40③`、`S1-build-verify §2`）。理由：600+ 条静态断言全绿仍被真编译暴露 5 个真缺陷（`C2039`×3、UHT include-order、`LNK2001` 跨模块导出，`_pitfalls.md` P26-29 B1）；**只有真实编译+链接能证伪**。
3. **错误行按"触及文件"过滤**：日志里既有错误（别的模块 `C3668` 等）与你无关，过滤后才是你的缺陷清单（`T-13-merged-build-20260918.md:45`：过滤后恰为 4 条）。远端重试噪声行（`Force local retry`）与 C-error 签名无关（`S1:30`）。
4. **UBA 日志必须 `-Log=<file>` 另存**：默认 `Engine\Programs\UnrealBuildTool\Log.txt` 会被下次构建覆盖（`_pitfalls.md` P68 D2）；stdout 捕获日志丢 `RemoteExecutor` 标签，不能做主机归因（wrapper:20-24、P69 D3）。
5. **构建前后各取被编译源码 sha256**，证明"构建期间没人在改被编译文件"——实测记录（`pm-state.md:795`：前后 `.h A7FC3CCE…` / `.cpp D5E34C33…` 不变 ⇒ 构建期无写入）；管线脚本 `t27_freeze_build_verify.py:2,111,130`（verify sources → freeze hashes → build → re-hash → scan errors）。
6. **构建中不要重启机器**；中断后恢复 = 直接重跑同一条命令（UBT 按时间戳缓存，已完成 `.obj` 保留）。出处：`pm-state.md:435`。

### 2.4 UBA 与耗时预期

- UBA（公司 Horde 池）**保持开启**：池健康时 ~420 actions/min（Rider 同链实测 `[1396/5493]→[1816/5493]` 60 s）；池退化时（节点反复掉线）本地回退只有 2 宽 ⇒ 3.9 actions/min。修复 = wrapper 内 `-MaxParallelActions=16` 抬高本地回退宽度（24 逻辑核留余量）。出处：`_run_build_pm.cmd:10-18`。
- 用户级 `%APPDATA%\...\BuildConfiguration.xml` 的 `MaxParallelActions` 会钉死本地回退宽度（本例 =2），命令行 `-MaxParallelActions=16` 可覆盖且不反向限制 UBA 远端宽度。出处：`_pitfalls.md` P70 D4。
- **典型耗时**（预算排程用）：全量 86.5 min（`build-baseline-ue551-20260917.md:33`）；S1 大增量 4811.53 s ≈ 80.2 min（`S1:15`）；小增量（改动少量文件、UBA 命中）**32~47.4 s**（`T-27b §5`、`pm-state.md:794`）。**UnrealEd 增量重编一次 ≈ 80 min ⇒ 代码类 worker 1h 预算内必然 wall 超时，绝不让 worker 等构建**（`pm-state.md:40①`）。
- 判"在干活 vs 卡住"：日志 mtime / `[N/M]` 推进、`[WorkerNN] Connected/Exception`、lease 是否反复重建；本机可能没有 cl.exe/link.exe（编译在远端），**不得**据此判卡住。出处：`_pitfalls.md` P72 D6、`pm-state.md:489`。
- 中止判据：已确证 ≥1 个硬 FAIL 缺陷 **且** 远端反复异常/日志长时间停滞 ⇒ 可中止先修复。出处：`_pitfalls.md` P71 D5。

### 2.5 产物落地位置与"哪只 DLL 被重链接"

- 引擎侧模块改动 ⇒ 重链接 `E:\CFBH543\Engine\Binaries\Win64\UnrealEditor-UnrealEd.dll`（本 key 全部代码在 UnrealEd 模块）。出处：`check_dll_v5.py:10`、`S1:44`。
- UHT 反射产物：`E:\CFBH543\Engine\Intermediate\Build\Win64\UnrealEditor\Inc\UnrealEd\UHT\<类>.generated.h` / `.gen.cpp`。出处：`S1:37-38`。
- 编辑器主程序/游戏侧产物更新于 `E:\CFBH\Binaries\Win64` 下（基线记录：Editor 构建真实产出/更新了该目录下的产物）。出处：`build-baseline-ue551-20260917.md:100`。
- **防"陈旧 DLL 假绿"**：构建后对 DLL 做**字面量核验**（`check_dll_v5.py` 12/12、`check_dll_v4.py` 13/13），证明新代码真的进了二进制（`pm-state.md:796`、`T-27b §5`）。字面量编码坑见 §5.4。

---

## 3. 真机驱动编辑器

### 3.1 完整逐字命令行

启动器注释里的完整形态（出处：`pm_v5_probe_launch.ps1:4-5`）：

```
UnrealEditor.exe "E:\CFBH\ProjectH.uproject" -EnablePlugins=PythonScriptPlugin -skipcompile
  -ExecCmds="PY <pm_v5_probe.py>" -abslog="<run_dir>\editor_v5probe.log" -NoSplash
```

PowerShell 实际发射代码（出处：`pm_v5_probe_launch.ps1:203-212,220,259,262`；`pm_v5_cdo_launch.ps1:158-173` 同构）：

```powershell
$ArgList = @(
    ('"' + $Project + '"'),
    '-EnablePlugins=PythonScriptPlugin',
    '-skipcompile',
    ('-ExecCmds="PY ' + $Driver + '"'),
    ('-abslog="' + $EditorLog + '"'),
    ('-V5ProbeRunDir="' + $RunDir + '"'),
    ('-V5MigrateScript="' + $Migrate + '"'),
    '-NoSplash'
)
$editor = Start-Process -FilePath $EditorExe -ArgumentList $ArgList -WorkingDirectory $Fixtures -PassThru
$editor.WaitForExit(30000) | Out-Null
try { if ($editor.HasExited) { $exitCode = $editor.ExitCode } } catch {}
```

- 编辑器 exe：`E:\CFBH543\Engine\Binaries\Win64\UnrealEditor.exe`（启动器 `$EditorExe`，`pm_v5_probe_launch.ps1:46`）。
- 项目自定义参数（如 `-V5ProbeRunDir`）可随命令行传给 python 驱动（`:209-210`）；完整命令行**原样落盘** `editor_launch_cmd.txt`（`:214-215`）备核。
- python 侧发射（argv 列表 ⇒ 无需内嵌引号）：`'-ExecCmds=PY %s' % DRIVER, "-abslog=%s" % LOG, "-NoSplash",`（`pm_sweep_launch.py:119`）。

### 3.2 两条禁忌

1. **禁 `-ExecutePythonScript`**：引擎 `EditorPythonExecuter.cpp:92` 会主动置 `Unattended` 标志 ⇒ `GIsRunningUnattendedScript=true` ⇒ 所有 `IsInteractive()` 判定恒假——"交互式"取证永远走旁路（本例 22 行 `VC-014/VC-017 gate_action=not_evaluated` 假象）。需要真交互必须用 `-ExecCmds="PY <script>"`（`PythonScriptPlugin.cpp:886` 控制台命令，flags 默认）。出处：`_pitfalls.md` P7-11 A1。
2. **禁改引号形态**：`-ExecCmds` 必须是**单个**参数（PS 数组里的单元素 `('-ExecCmds="PY ' + $Driver + '"')`；python argv 里的单个 `'-ExecCmds=PY <script>'`）。拆开/重排引号 = 驱动脚本根本不执行。收窄重派的 t29b 验收清单里"启动引号形式"是第一项静态验收。出处：`pm_v5_probe_launch.ps1:207`、`pm_sweep_launch.py:119`、`_superseded\README.md`。

### 3.3 每次运行必须自证（否则全部结论无效）

驱动脚本真的执行了没有？**自证数字**（出处：`verify_t31.py:74-79`，PM 复验脚本逐字断言）：

```python
_, cmdpy = clip("Cmd: PY")
check("self-proof Cmd: PY == 1 (driver really executed)", cmdpy == 1, "count=%d" % cmdpy)
_, vc14 = clip("VC-014")
check("self-proof VC-014 == 0 (no synthetic input)", vc14 == 0, "count=%d" % vc14)
_, vc17 = clip("VC-017")
check("self-proof VC-017 == 0", vc17 == 0, "count=%d" % vc17)
```

- `Cmd: PY` 全日志恰 1 条 = 脚本执行（`T-31 §1` 原文：`[2026.09.20-17.15.01:406][  0]Cmd: PY F:\FLSpace\AssetImportGate\.agenticdoc\...\editor\pm_v5_cdo_probe.py`）；**`Cmd: PY != 1` ⇒ 一切结论无效**。
- `VC-014`/`VC-017` = 0 ⇒ 无合成输入/旁路（交互性自证）。派发任务书就把自证写进要求（`pm-state.md:533`：t14c 派发含 "`VC-014` 计数=0 自证 + 外部关窗 + 串行化"）。

### 3.4 串行化（同一时刻只允许一个编辑器会话）

```powershell
$running = @(Get-Process UnrealEditor -ErrorAction SilentlyContinue)
```

- 有编辑器进程 ⇒ **拒绝发射**：`SKIP: UnrealEditor already running pids=...`（`pm_v5_probe_launch.ps1:135,144-149`，注释 `:19` "refuses to launch if any UnrealEditor is running"）。
- 用户会话在跑 ⇒ PM 期间不得开自己的编辑器（`pm-state.md:698`）；"PM 不能并发开第二个 UnrealEditor"（`T-32 §2.2`）。
- python 发射器同款：先等已有 `UnrealEditor` 进程退出（`pm_sweep_launch.py:5,65,70`）。

### 3.5 模态窗：只能 `WM_CLOSE`，禁合成鼠标/键盘

- 交互式弹窗会阻塞游戏线程（`ReportBlocked → GEditor->EditorAddModalWindow` 嵌套 Slate 循环）⇒ 无人值守脚本死锁。**必须由外部进程关窗**：Win32 `WM_CLOSE` 优先、标题精确匹配（实测延迟 ≈0.22 s），并留 `WINDOW_SEEN`/`WINDOW_GONE` 原文。`closed=0` 只在"旁路场景无模态"时才合理。出处：`_pitfalls.md` P13-17 A2。
- 匹配键（窗口标题）**必须从源码行号取**：`AssetImportGate.cpp:2656` → `Asset Import Gate - Blocked Files`（v5 冻结源码：`AssetImportGate.cpp:2656` = `.Title(FText::FromString(TEXT("Asset Import Gate - Blocked Files")))`；`_pitfalls.md` P79 E4。注：`t14c_interactive_block.py:33-35` 里写的是 T-14 时代的 `:1920-1938`/`:1892`——代码增长后行号已漂移，**引用行号必须现场重取**）。
- 驱动内部再加**看门狗**：`never let a stuck modal run past DEADLINE_SECONDS`（`t14c_interactive_block.py:634`），同时计数 `reentrant ticks during call > 0` 证明游戏线程停在模态循环（`:503,570`）。
- **禁合成鼠标/键盘输入**（D-T14-1）：Slate 交互只能归人工手势卡（`T-31 §6`：设置页按钮真实点击"自动化会被迫伪造输入（D-T14-1 禁止）⇒ 归人工手势卡"）。

### 3.6 退出码语义

| 退出码 | 含义 | 判据与出处 |
|---|---|---|
| `0` | 会话正常结束 | `v5cdo_3`: `timeout=0 stale_kill=0 exit_code=0 seconds=117.1 pid=9708`（`T-31 §1`）；复验断言 `editor exit_code == 0`（`verify_t31.py:86`） |
| `-1073741502`（= `0xC0000142` `STATUS_DLL_INIT_FAILED`） | **死在引擎初始化之前**（Windows 加载器失败码，不是引擎断言/崩溃栈） | `v5probe_2`: `exit_code=-1073741502 seconds=25.4 pid=50284`（`T-27b §1`、`pm-state.md:950`） |
| 日志文件**根本不会生成** | `-abslog` 指定文件不存在 + `gate_log_extract.txt` = 0 B + `E:\CFBH\Saved\Logs\ProjectH.log` mtime 未变 ⇒ 进程死在静态初始化/加载阶段，**不是闸门逻辑崩溃** | `T-27b §2` |
| `-1073741819` 等 | 【未验证】本项目证据树中无任何 `-1073741819` 记录（rg 全树零命中，2026-09-21 查） | —— |

### 3.7 启动即死的根因范例（静态初始化禁忌）

**禁止在文件作用域静态初始化里加载模块**（Windows 加载器锁下调 `FModuleManager::LoadModuleChecked` 属非法操作 ⇒ `0xC0000142`）。反面教材（T-27 原版，出处 `T-27b §3`）：

```cpp
// Editor.cpp 文件作用域
namespace {
  struct FAssetImportGateSettingsCustomizationRegistrar {
    FAssetImportGateSettingsCustomizationRegistrar() {
      FAssetImportGate::RegisterSettingsCustomization();   // ← 静态初始化期调用
    }
  };
  static FAssetImportGateSettingsCustomizationRegistrar GAssetImportGateSettingsCustomizationRegistrar;
}
```

正确做法 = 注册点迁到模块 `StartupModule`（出处 `T-27b §4`，改 `UnrealEdGlobals.cpp`）：

```cpp
#include "AssetImportGate.h"          // 新增
...
class FUnrealEdModuleImpl : public FDefaultModuleImpl
{
public:
    virtual void StartupModule() override
    {
        FDefaultModuleImpl::StartupModule();
        FAssetImportGate::RegisterSettingsCustomization();
    }
};

IMPLEMENT_MODULE( FUnrealEdModuleImpl, UnrealEd );
```

- 该风险**只有真机跑一次才能证实**（worker 自己在 result.md 里列为"不确定点 #2"，它是对的）——这正是"Stage 出口必须真编译+真链接+真运行"的价值（`T-27b §3`）。
- 配套环境事实：**ini 只在启动时读进 CDO**，会话内每批读的是 CDO 对象 ⇒ ① Project Settings UI 改 ⇒ 下一批生效（无需重启）；② 直接改 `Config\DefaultEditor.ini` ⇒ **必须重启编辑器**才生效（`T-27b §6`、`T-31 §3.1`——旧说法"改 ini 无需重启"被真机证伪）。
- 编辑器内 Python API 可用性**必须实测**（`unreal.AssetTools.import_assets` 等，先落 `api_probes.json` 逐 API `hasattr` 探测；`UDeveloperSettings` 走项目 `Config/DefaultEditor.ini`，用户层 ini 无效）。出处：`_pitfalls.md` P19-22 A3、`T-14b-report.md:47`。

---

## 4. 运行期证据纪律

### 4.1 日志契约固定可 grep

- 引擎侧行契约：`[VERIFY] VC-nnn: k=v k=v ...`（例，出处 `gate_log_extract.log:7,11`）：

```
[2026.09.20-19.47.25:064][700]LogAssetImportGate: [VERIFY] VC-024: gate_action=allow_all table_state=missing warning_count=1
[2026.09.20-19.47.25:064][700]LogAssetImportGate: [VERIFY] VC-042: default_gate_asset_types=2
```

- 质检侧按字面量反解：`re.findall(r"\[VERIFY\]\s*(VC-\d{3})", txt)`（`quality_gate.py:89`）；PM 复验脚本的段正则**直接对着真机日志的精确行形状**写（`t31_preflight.py:82`）。
- 覆盖统计契约：`quality_gate.py:82`（`if not fn.lower().endswith(".log"):`）⇒ **日志抽取文件扩展名必须是 `.log`**；用 `.txt` 会静默不进覆盖统计（`runs\20260920\manual_user_session\README.md:9`："PM 的 `_scratch/quality_gate.py` 的 `runtime_verify()` 只扫 `evidence/**/*.log`"）。

### 4.2 证据目录结构：`runs/<日期>/<会话>/`

每会话一个目录，至少含（出处：`T-27b §2` 产物清单、`T-31 §5` 产物表、`manual_user_session\README.md`）：

- `editor_<会话>.log`（`-abslog` 全量日志，2.4 MB 级）
- `editor_exit_code.txt`（`timeout=.. stale_kill=.. exit_code=.. seconds=.. pid=..` 原文）
- `editor_launch_cmd.txt`（完整命令行留档）、`editor_launch_ini.txt`（ini 注入内容）
- `inventory_*.json`（before/after 落盘清单 diff 的清点）
- `<会话>_modal_watcher.log`（外部关窗看门狗原文，含 `WINDOW_SEEN/GONE`）
- `<会话>_summary.json` / `*_report.json`（机器可读 verdict）
- 人工会话证据落 `runs\<日期>\manual\` 或 `manual_user_session\`（`README.md:24`），并在 README 记**源日志路径 + 其 sha256 前 16 + 抽取方式**（`README.md:7-9`：源 `E:\CFBH\Saved\Logs\ProjectH.log` sha `09e18873cf540156`，`rg -N 'LogAssetImportGate'` 全量抽出未改写）。

### 4.3 真机原文双向核验

- **文档里引用的每一行必须能在运行日志里逐字找到；反之日志里的关键行要回写文档**。实例：`T-30c §3`（PM 独立抽取 vs 文档照录，语料 = `evidence/fixtures/runs/20260920/**` **19,256,389 字符**；8 行照录逐条"文档含 ✅ / 日志含 ✅"）。
- **交叉互证**：同一 settings 状态的指纹（`VC-039 settings_signature=9def6e0d`）在**两个独立会话**一致 ⇒ 跨会话稳定（`T-30c §3`、`T-31 §4⑤`）。
- 失败的对照也要留档（`interactive_attempt1/`，`_pitfalls.md` P22）。

### 4.4 fail-open 必须可观测

- 失败方向（表缺失/非法正则等）要打出**显式日志行**：`VC-024: gate_action=allow_all table_state=missing warning_count=1` + 中文警告行（`gate_log_extract.log:6-7`）；非法正则行 fail-open + 警告原文两轮一致（`quality_gate.py:188` Q-COV-004）。
- 该事件在用户真机上实际触发过（`T-32 §2.3`：19:47:25 用户会话 `table_state=missing` ⇒ fail-open 生效直接导入）——不是纸上推断。

---

## 5. 冻结与快照

### 5.1 三类哈希

| 类 | 做法 | 出处 |
|---|---|---|
| 源码 | 任务收口即冻结：`snapshots/<任务>/` 存 4 件源文件 + 哈希表 | `snapshots\README_v5.md:5-15`（T-27/ = T-31/ 逐字节相同；`AssetImportGate.h` 26,366 B LF `9A5D8FC74B69C881…`、`.cpp` 112,230 B LF `F904096734CF4732…`、`UnrealEdGlobals.cpp` 10,058 B CRLF `EC8CB69B…`、`Editor.cpp` 82,098 B CRLF `4C2B1ED6…`） |
| ini | 临时改配置必须 sha 三连（before_run / after_run / restored）+ PM 逐位核收 | `_pitfalls.md` P77 E2；启动器实测 `$backupSha`/`$injectedSha`/`$afterRunSha`/`$restoredSha`/`$backupFileSha`（`pm_v5_probe_launch.ps1:162-164,194,282-285`）；`T-31 §1`（ini 全程零写入，会后 sha `9F1A61D4569DBA8A…` 与基线一致） |
| DLL | 构建后对二进制做字面量核验 | `check_dll_v5.py:10`（DLL 路径）、`pm-state.md:796`（13/13 ⇒ 非陈旧 DLL 假绿） |

### 5.2 冻结与校验分离

- 快照脚本**默认只校验，`--freeze` 才写**：`pm-state.md:814`（"脚本改为**默认只校验**（`--freeze` 才写）"，起因 = `verify_t18.py` 冻结段同义反复且覆盖快照的事故）。
- 独立管线：`t27_freeze_build_verify.py:2`（"verify sources -> freeze hashes -> build -> re-hash -> scan errors"），`PRE = {p: sha(p) ...}`（:111）/ `POST`（:130）前后对拍。
- **快照/证据目录的写者是 PM**：用哈希证明 worker 未写引擎文件（`T-30c §2` 零漂移表）；废弃产物由 PM 原样封存（`_superseded\README.md`）；worker 产物一律落在自己的 `workers/<task_key>/` 目录（`_workers.parallel` 各行的 task.md 路径）。
- **教训**：每个写代码的任务收口时应**立即**冻结快照，不要等整条链结束——T-25/T-26 中间态被 T-27 覆盖，只剩哈希（`snapshots\README_v5.md:19-21`）。

### 5.3 快照复算命令（PM 侧逐字）

```powershell
foreach ($f in @("AssetImportGate.h","AssetImportGate.cpp","UnrealEdGlobals.cpp","Editor.cpp")) {
  (Get-FileHash ".agenticdoc\drag-drop-import-gate\snapshots\T-27\$f" -Algorithm SHA256).Hash
}
```

出处：`snapshots\README_v5.md:26-28`（与哈希表逐行一致即为"未漂移"）。

### 5.4 DLL 字面量核验必须同时处理 ASCII 与 UTF-16LE

- `TEXT()` / `UE_LOG` 字面量在二进制里是 **UTF-16LE**——只按 ASCII 搜会漏（本类字面量首次按 ASCII 搜得 0，差点误判 CVar/Log 类别未进 DLL；按 UTF-16LE 搜各得 1）。出处：`S1-build-verify §4`（S1:57-60 假信号纠偏表）、`check_dll_v5.py:40`：

```python
    """UTF-16LE image of an ASCII literal: TEXT() strings live in the binary this way."""
```

- `T-27b §7 #32`：`check_dll_v5.py` 首跑 3/12，加宽字符双编码计数后 12/12。

### 5.5 哈希比对必须先做行尾归一化（EOL 陷阱）

- 引擎仓 `core.autocrlf=input`：**checkout/rebase 会把 CRLF 工作区文件翻成 LF**（不是内容改动）。实例：2026-09-20 20:56 用户 rebase 后 `Editor.cpp` 82,098 B(CRLF) → 80,058 B(LF)、`UnrealEdGlobals.cpp` 10,058 → 9,760 B，**内容逐字节相同（已验）**。出处：`_pitfalls.md` P89-91（§G，2026-09-21）。
- 因此**按字节比对源码哈希的验收必须先归一化**（本指南编写时实测：`Editor.cpp` 当前 sha256 前 16 = `01D2BB7080C2B841`（LF 形态），与 T-30c 记录的 `4C2B1ED6F3A1B61A`（CRLF 形态）不同，但 EOL 归一化后与 `snapshots\T-27\Editor.cpp` 相同 ⇒ 内容未变）。
- 归一化哈希逐字实现（`t27_freeze_build_verify.py:31-32`）：

```python
def sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()  # EOL-insensitive
```

- 禁止为"恢复 CRLF"而改工作区；需要时对单文件 `git checkout -- <path>`（`_pitfalls.md` P92）。

---

## 6. dual 模式协作流程（PM + worker）

### 6.1 队列文件与角色

- `_workers.parallel`：每行 = `task_key | status | pi | timi | task.md 绝对路径 | 启动时间 | 结束时间 | model`（列值照录实测；末列模型**显式指定才有值**，如 `glm-5.3`、`deepseek-v4.1-flash`；空 = 未显式指定）。出处：`_workers.parallel` WP1-WP51。
- `_workers.acked`：`task_key | ack 时间戳`（ISO）。**ack 时机 = worker 终态之后**（间隔从秒级到半小时不等：t30c 结束 09:59:26 → ack 10:00:06；t31 结束 09:24:39 → ack 09:24:48；失败个例 T-01 结束 05:39:22 → ack 06:06:01）；**失败任务也 ack**（design-evidence、t14 系列、t29、t31 都在列）⇒ ack 只是"结果已接收/入账登记"，**不等于采信**，成败由 PM 独立复验决定。出处：`_workers.acked` vs `_workers.parallel` 时间戳对照。

### 6.2 派发规格的必要要素（task.md 必须钉死）

1. **task_key**（队列主键，`_workers.parallel` 第一列）。
2. **产物绝对路径**（"只允许写这一个文件"式硬边界；例：本指南任务书直接给出 `F:\FLSpace\AssetImportGate\.agenticdoc\_toolchain-dual-mode-guide.md`）。
3. **硬约束**（禁跑构建 / 禁开编辑器 / 既有文件只读 / 禁编造——每条命令要能指到出处）。
4. **预算**（工具调用次数上限 + wall 分钟数；例：本任务 ≤60 次 / ≤45 min；收窄版 t29b = 硬预算 25 次工具调用、只许读 3 个文件、禁止读引擎源码）。
5. **证据要求**（自证数字、日志契约、冻结哈希、"交付自检"清单）。
6. 附：workspace profile 注入（game/engine 根、已解析的构建命令模板、deny globs）。

出处：`_scratch\workers\toolchain-dual-mode-guide\task.md`（派发实例）、`_superseded\README.md`（收窄版实例）。

### 6.3 worker 侧纪律

- **不跑构建**：UnrealEd 增量 ≈ 80 min > 1h 预算，必 wall 超时；worker 只交付代码 + 静态自查 + "待编译验证项"清单，构建由 PM 触发并按 Stage 批量（`pm-state.md:40①②`；`pm-state.md:735`："T-22 合并构建 PM 直执（禁止 worker 跑构建）"）。
- **不碰共享环境**：引擎/项目源码与 `.agenticdoc` 既有文件只读；产物落自己的 `workers/<task_key>/`。
- **产物自证**：交付物要过 PM 的静态验收清单——`py_compile`、启动引号形式、ini sha 四连、`WM_CLOSE`、`Cmd: PY` 与 `VC-014/VC-017` 自证（`_superseded\README.md`，t29b 验收实录）。
- **哈希/数字自报不可信**：PM 用冻结快照字节比对 + 自己的命令复算（`_pitfalls.md` P46-48 B5）。

### 6.4 PM 侧纪律

- **不采信 worker 自述**："下表每项均为 PM 用不同方法重跑一遍的结果"（`S1-build-verify:6`）；"不采信 worker 自述，全部由 PM 重新读取文档与运行日志原文得出"（`T-30c` 头部）；**验收脚本不得外包**（`pm-state.md:734`）。
- **自写脚本独立复验**：`verify_t31.py`（12 项断言 + 自证四条，`VERIFY_T31: PASS` exit 0）、`verify_t30c.py`、`t31_preflight.py`、`t27_freeze_build_verify.py`。
- **首跑 FAIL 先怀疑自己的脚本**（本项目 45 次首跑 FAIL 全是脚本自身缺陷）：范围过宽、引号被吞、未闭合引号崩在断言前、正则折叠失败等（`_pitfalls.md` P36-40 B3；`T-30c §6 #45`："本轮第 45 次首跑 FAIL 先自查脚本"——B5 断言写错字 2 项假 FAIL）。做法：① 首跑 FAIL 先自查并给出反证；② 回归 runner 逐套件校验退出码；③ 负向断言限定归属域。
- **观测计数一律累计字典（禁 delta）**；**超时被杀的 worker 先核查其已落盘证据再取舍**（曾救回 22 行 AC-014 证据，`_pitfalls.md` P48）。

### 6.5 模型策略

- 项目实际策略（2026-09-18 用户指定）：**执行类 worker（coding/构建/夹具/文档同步）→ `deepseek-v4.1-flash`；review 评审类 → `glm-5.3`**（`launcher.py:265` 对 pi CLI 强制 `--provider timi`；两个 id 均在 timi 路由实测可用；T-04 之前的 glm-5.3 派发不中断）。出处：`pm-state.md:40④`。
- 派发记录佐证：`_workers.parallel` 末列——早期任务显式 `glm-5.3`（WP8-WP17）、T-05 起显式 `deepseek-v4.1-flash`（WP19-WP40）、其余行为空（未显式指定）。
- **通用口径**：worker 默认与 PM 窗口同模型（本项目 PM 窗口 = `deepseek-v4.1-flash`），只有显式指定才覆盖。【未验证：harness 层默认行为的文档出处；上述为该项目实测口径】

### 6.6 文件级写者唯一性

- **同一对文件禁止并行两个 coding worker**：并行编排表里 `AssetImportGate.h/.cpp`（**独占**）给 t17；T-18（同文件）**必须等 T-17 通过 PM 验收**才派；t20/t21 因"不碰引擎源码、不与 T-20 同文件"才并行。出处：`pm-state.md:726-735`（§14.3 并行编排，遵守同文件串行纪律）。
- 底层原因（harness 工具语义）：`write` 是整文件覆盖（会 clobber 他人改动）、`edit` 是精确文本匹配（撞车即失败、fail-safe）。【未验证：该工具语义未在本项目文档中记载，属派发规格口径】

---

## 7. 失败处置 playbook

| 终态 | 判据 | 处置 | 出处 |
|---|---|---|---|
| **wall 超时**（预算耗尽被杀） | worker 终止时间 = 派发后整 1h；`last activity 57 s ago`、checkpoint `risk=low` | ① **产物不直丢**：先核查已落盘证据再取舍（曾救回 22 行 AC-014 + 一套可复用机械）；② 值得保留的产物**采纳**（t31 wall 超时产物被采纳：三个会话均 exit 0 无残留）；③ 剩余未写部分**PM 直执补全**；④ 已被取代的产物移 `_superseded/` **原样封存 + 登记哈希 + 标记禁运行** | `_pitfalls.md` P48；`T-31 §5`；`_superseded\README.md` |
| **idle/停滞** | 30 分钟重复同一批慢扫描、零产出；mw checkpoint `risk=high` | **终止** + **PM 直执**（用 rg 秒级完成）。教训：大目录取证任务应在任务书里指定 `rg`，否则 worker 陷入慢扫描循环 | `pm-state.md:58`（design-evidence-r3-r4-r6 实录） |
| **发散/范围漂移** | 30 min / 35 次读取 / 0 次写入、progress.md 无自评行（只有机器行）、在研读范围外源码 | 30 min 检查点裁决"范围漂移" ⇒ **收窄重派**：硬预算（25 次工具调用）、只许读白名单文件（3 个）、**禁读（引擎）源码**、**产物改名防撞车**；重派版 15 min/14 次交付并通过 PM 静态验收。首派产物照 `_superseded/` 封存规则处理 | `_superseded\README.md`（t29 → t29b 全实录） |

- **只读角色的发散口径**（mw-worker-progress-persist，2026-09-23）：review/research/verifier 这类无写工具角色，检查点机器行改由框架写入 `progress.md`（`CKPT <n>m [machine] …`），窄工具 `worker_file` 的落盘**不计入** `writes` —— 因此这类任务出现 `writes=0` 属正常，发散判据只看「机器行在推进但始终无自评行 / `repeat_top` 不下降」。
- **重试一次仍失败 ⇒ 转 PM 直执**（派发规格口径）：实例一 = t29 失败 → 收窄重派 t29b 成功；实例二 = design-evidence 失败后未重试、直接 PM 直执；实例三 = t31 wall 超时 → 采纳产物 + PM 直执补终版汇总（`T-31 §5`）。三种路径都出现过，未见成文的"最多重试一次"硬规则【未验证：成文规则】。
- 构建中止判据与恢复：见 §2.3-6（`_pitfalls.md` P71 D5、`pm-state.md:435`）。
- `_superseded/` 封存记录格式（文件名字节数 + sha256 前缀 + 处置）：`v5_probe.py` 32,100 B `A7500366342397CE` / `v5_probe_launch.ps1` 64,888 B `D319309999111320`，处置 = "废弃，不运行"（`_superseded\README.md` 产物清册表）。

---

## 8. 一页速查（命令卡片）

> 全部逐字摘自出处；`<...>` 为占位符。构建类命令在**控制工作区根**执行；引擎/游戏路径按对方项目替换（见 §9）。

**构建（增量，UBA 开）**
```
research\_run_build_pm.cmd <log> ProjectHEditor Win64 Development -project=E:\CFBH\ProjectH.uproject -WaitMutex
```
（`pm-state.md:793`；wrapper 用法 `_run_build_pm.cmd:3`：arg1 = 日志路径）　构建前孤儿检查：`Get-Process cl,dotnet`（`pm-state.md:40`）。

**构建（应急，纯本地）**
```
call "E:\CFBH543\Engine\Build\BatchFiles\Build.bat" %2 %3 %4 %5 %6 %7 %8 %9 -NoUBA -MaxParallelActions=16 -Log="%~dp1%~n1.ubt.txt" > "%LOG%" 2>&1
```
（`_run_build_local.cmd:16` 内部形态；外层用法同 §2.2）

**驱动编辑器（PS 发射器核心）**
```powershell
$ArgList = @(
    ('"' + $Project + '"'),
    '-EnablePlugins=PythonScriptPlugin',
    '-skipcompile',
    ('-ExecCmds="PY ' + $Driver + '"'),
    ('-abslog="' + $EditorLog + '"'),
    '-NoSplash'
)
$editor = Start-Process -FilePath $EditorExe -ArgumentList $ArgList -WorkingDirectory $Fixtures -PassThru
$editor.WaitForExit(30000) | Out-Null
try { if ($editor.HasExited) { $exitCode = $editor.ExitCode } } catch {}
```
（`pm_v5_probe_launch.ps1:203-212,220,259,262`；发射前串行化检查 `$running = @(Get-Process UnrealEditor -ErrorAction SilentlyContinue)`（`:135`），有进程即 SKIP（`:144-149`））

**日志抽取（扩展名必须 .log）**
```
rg -N 'LogAssetImportGate' <源日志>   →  输出写 <run>\gate_log_extract.log
```
（`runs\20260920\manual_user_session\README.md:9`；写文件用 write 工具/python UTF-8，**不得**用 `>` 重定向——UTF-16LE 陷阱，`_pitfalls.md` P84）

**质检（PM 侧脚本）**
```
python _scratch\verify_t31.py    # T-31 §0 记录形态：VERIFY_T31: PASS（12 断言 + 自证四条）
```
质检脚本 `_scratch\quality_gate.py`（证据中的记录形态为 `_scratch/quality_gate.py`，`runs\...\README.md:9`）：入口 `main()`（:102）、`if __name__`（:239）、只扫 `*.log`（:82）、VC 正则（:89）；**其命令行用法未在证据留档【未验证】，运行前先读脚本头**。

**哈希（三连/快照/EOL 归一）**
```powershell
$backupSha   = (Get-FileHash -LiteralPath $EditorIni -Algorithm SHA256).Hash
foreach ($f in @("AssetImportGate.h","AssetImportGate.cpp","UnrealEdGlobals.cpp","Editor.cpp")) {
  (Get-FileHash ".agenticdoc\drag-drop-import-gate\snapshots\T-27\$f" -Algorithm SHA256).Hash
}
```
（`pm_v5_probe_launch.ps1:164`；`snapshots\README_v5.md:26-28`）　EOL 归一化哈希（python）：`hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()`（`t27_freeze_build_verify.py:32`）

**驱动脚本自证（逐字断言）**
```python
_, cmdpy = clip("Cmd: PY")
check("self-proof Cmd: PY == 1 (driver really executed)", cmdpy == 1, "count=%d" % cmdpy)
_, vc14 = clip("VC-014")
check("self-proof VC-014 == 0 (no synthetic input)", vc14 == 0, "count=%d" % vc14)
```
（`verify_t31.py:74-77`）

**提交（多行消息）**：写消息文件 + `git commit -F <file>`（`_pitfalls.md` P86）。

---

## 9. 移植到其它 dual 项目的 checklist

**A. 必须换成对方项目自己的参数：**

| 项 | 本项目值 | 换法 | 出处 |
|---|---|---|---|
| uproject | `E:\CFBH\ProjectH.uproject` | 对方 uproject 绝对路径 | `target.yml:7` |
| 引擎根 / 游戏根 | `E:\CFBH543` / `E:\CFBH` | 对方源码引擎根 / 游戏根 | `target.yml:5-6` |
| 构建目标名 | `ProjectHEditor` / `ProjectH` | **从 `<游戏>\Source\*.Target.cs` 现查**，勿猜 | `target.yml:12,15` |
| 日志类别前缀 | `LogAssetImportGate` | 对方引擎侧日志 Category（抽取/质检的 grep 键） | `README.md:9`、`S1:58` |
| 证据契约前缀 | `[VERIFY] VC-nnn: k=v` | 对方验收行契约（编号体系 + 键值形状） | `quality_gate.py:89` |
| 证据根目录 | `evidence\fixtures\runs\<日期>\<会话>\`、`snapshots\` | 对方 key 的对应目录树 | `T-31 §5`、`snapshots\README_v5.md` |
| 角色文件名 | `pm-state.md`、`_workers.parallel`、`_workers.acked`、`target.yml` | 对方框架等价物（队列/ack/状态文件） | `_workers.parallel`、`_workers.acked` |
| 夹具分区 | `/Game/__GateFixture*`（新用例用新目录名；项目收尾时统一清理并**同步清掉配置里的引用** —— 本项目 2026-09-21 已删三个夹具目录 + 去掉 ini 的 `RuleTable=` 行） | 对方夹具命名分区 | `_pitfalls.md` P78 E3 |
| 模态窗标题 | `Asset Import Gate - Blocked Files`（源码 `AssetImportGate.cpp:2656`） | 从对方源码行号现查 | `_pitfalls.md` P79 E4 |

**B. 通用不变（直接照抄本指南）：**

1. PowerShell 5.1 全部纪律（§1：`;`、无 heredoc、UTF-16LE 重定向、GBK、`-F` 提交、引号坑、rg 纪律、禁全树扫描）。
2. 构建 = wrapper + `-waitmutex` + `-Log=` 另存 + 退出码与 `error C`/`LNK` 双判 + 前后 sha + 差分三重比对（§2）。
3. 编辑器驱动 = `-ExecCmds="PY <script>"` 单参数 + `-abslog` + `Cmd: PY == 1` 自证 + 串行化 + `WM_CLOSE` 外部关窗（§3）。
4. 证据 = 固定可 grep 契约 + `runs/<日期>/<会话>/` + 双向核验 + fail-open 可观测 + `.log` 扩展名（§4）。
5. 冻结/快照 = 三类哈希 + 冻结与校验分离 + ini sha 三连 + DLL 双编码字面量 + EOL 归一化（§5）。
6. 协作 = 派发五要素 + worker 不跑构建 + PM 不采信自述 + 首跑 FAIL 先自查 + ack 即时登记 + 写者唯一性（§6）。
7. 失败处置三终态 playbook + `_superseded/` 封存（§7）。

**C. 开工 checklist（照序执行）：**

1. 确认 dual 工作区三根路径 + deny globs（`target.yml` 等价物）。
2. 从 `Source\*.Target.cs` 现查目标名；先跑一次**基线构建**拿退出码与错误签名集合（`S1 §2` 差分基线）。
3. 定日志契约前缀 + 写质检脚本（只扫 `*.log`）。
4. 建 `runs/<日期>/<会话>/` 证据骨架 + 启动器模板（抄 §3.1/§8，只换路径）。
5. 建 `_superseded/` 与快照目录约定（PM 唯一写者）。
6. 首次驱动会话先跑**能力探针**（`api_probes.json`）再写真用例（`_pitfalls.md` P21）。
7. 派 worker 前写死五要素 + 同文件串行表（§6.2/§6.6）。
8. 验收前自问：自证数字齐了吗？首跑 FAIL 查过自己脚本了吗？

---

## 10. 证据出处表

> sha256 前 16 位，快照时间 2026-09-21 15:50（`Get-FileHash` 实测）。`_scratch\pm_sweep_launch.py` 的 sha 未取（行号引用）。

| 出处文件 | sha256 前 16 | 本指南主要引用 |
|---|---|---|
| `.agenticdoc\_pitfalls.md` | `E1BFCB4A692EFAA6` | §1 全部（P83-86 F 组）、A1/A2/B1-B5/D 组/E2-E4/G 组（P7-93） |
| `.agenticdoc\research\_run_build_pm.cmd` | `B974887F8D15D7CA` | §2.2 逐字命令（:3,35-37）、UBA 数据（:10-18）、-Log=（:20-24）、开关出处（:26-31） |
| `.agenticdoc\research\_run_build_local.cmd` | `C948A42438A7227C` | §2.2 应急本地构建（:16）、-NoUBA 论证（:5-14） |
| `.agenticdoc\research\_run_build.cmd` | `27FBEA1D4F5D2A83` | §2.2 wrapper 陷阱（:5-9 `%*`/shift） |
| `.agenticdoc\research\build-baseline-ue551-20260917.md` | `C590E5238090A50E` | §2.4 耗时（:33,62,75）、§2.5 产物（:100）、UBA 轮询（:21-29） |
| `drag-drop-import-gate\pm-state.md` | `014A3AB4D945B716` | §2.2（:491,793-796,153）、§2.3（:40,435,489）、§3.3（:533）、§3.4（:698）、§3.6（:950）、§5.2（:814）、§6（:40④,58,726-735）、§7（:58） |
| `evidence\execute\T-27b-static-init-crash-20260920.md` | `2496DF4E99FACD48` | §3.6 退出码/无日志判据（§1-2）、§3.7 两段 cpp 原文（§3-4）、§5.1 哈希表（§5）、#31/#32（§7） |
| `evidence\execute\T-31-v5-live-verification-20260920.md` | `51C529C7595BE799` | §3.3（§1 自证原文）、§3.6（exit 0 原文）、§4.3（§4 交叉互证）、§6.4（§0）、§7（§5 wall 超时处置）、§3.7 ini/CDO（§3.1） |
| `evidence\execute\T-30c-v5-docs-verification-20260920.md` | `226040C44528D8AB` | §4.3 双向核验（§3）、§5.2 零漂移（§2）、§6.4 首跑 FAIL #45（§6） |
| `evidence\execute\T-32-user-session-and-feedback-20260920.md` | `F9E6345CD0EDFF6B` | §3.4（§2.2 不可并发）、§4.4 fail-open 实触发（§2.3） |
| `evidence\execute\T-13-merged-build-20260918.md` | `6B57845F7AF949C5` | §2.3 错误行过滤（:16-18,45） |
| `evidence\execute\S1-build-verify-20260918.md` | `89CC20792E8C0DB6` | §2.3 差分（§2）、§2.5 产物（§3-4）、§5.4 UTF-16LE（§4）、§6.4 不采信自述（:6） |
| `evidence\fixtures\editor\pm_v5_probe_launch.ps1` | `4D46574286A38E3B` | §3.1 命令行/PS 代码（:4-5,203-216,220,259,262）、§3.4（:135-149）、§5.1 ini sha（:162-164,282-285） |
| `evidence\fixtures\editor\pm_v5_cdo_launch.ps1` | `035EC8133FC915BA` | §3.1 同构发射器（:4-5,158-173）、§5.1（:500,502 脚本 sha 自报） |
| `evidence\fixtures\editor\migrate_rules_v5.py` | `B2D7D015EABDE267` | §6.3 worker 产物自证（:19-33 fail-loud、delete→create→fill→verify→save） |
| `evidence\fixtures\editor\t14c_interactive_block.py` | `6082ABF708EFCC4E` | §3.5 模态窗（:27-35,503,570,634） |
| `evidence\fixtures\editor\pm_sweep.py` | `55125EDE5C95D3B7` | §3.1 python 发射形态（:9）、§4.1 用例契约（:105-128） |
| `_scratch\pm_sweep_launch.py` | —（行号引用） | §3.1（:119 ExecCmds 单参数）、§3.4（:5,65,70 串行化） |
| `evidence\fixtures\editor\_superseded\README.md` | `57B1B9D83BB8AE66` | §7 全部（wall 超时封存、发散收窄重派、t29→t29b、哈希登记） |
| `evidence\fixtures\runs\20260920\manual_user_session\README.md` | `ED719AC0DA114ABC` | §4.1（:9 .log 扩展名）、§4.2（:7-9 源日志 sha）、§8 抽取命令 |
| `...\manual_user_session\gate_log_extract.log` | `DD38AAB54381EC62` | §4.1 契约行原文（:7,11）、§4.4（:6-7） |
| `drag-drop-import-gate\snapshots\README_v5.md` | `C3D19BD14A954D31` | §5.1 哈希表（:10-15）、§5.2 教训（:19-21）、§5.3 复算命令（:26-28） |
| `_scratch\quality_gate.py` | `783AFAE174E1E9BC` | §4.1（:82 .log 过滤、:89 VC 正则）、§8（:102,239 入口） |
| `_scratch\verify_t31.py` | `65A22992190D559D` | §3.3 自证断言（:74-79）、§3.6（:86） |
| `_scratch\check_dll_v5.py` | `BEF4E360F7201F8A` | §2.5（:10 DLL 路径）、§5.4（:40 UTF-16LE） |
| `_scratch\fix_v5_gate_debts.py` | `742AA89E2AB0E85F` | §6.4 指纹配方（:39-41,51,74 sha1 指纹） |
| `_scratch\t27_freeze_build_verify.py` | `D9677FD3097DC713` | §2.3-5（:2,111,130 冻结-构建-复哈希）、§5.5（:31-32 EOL 归一） |
| `.agenticdoc\target.yml` | `732F579CB48EBA07` | §0（:4-7）、§2.1（:12-17）、§1.12（:24-61）、§9.A |
| `.agenticdoc\_workers.acked` | `A57C5F9F32D519C8` | §6.1 ack 时机（时间戳对照） |
| `.agenticdoc\_workers.parallel` | `53A8DCAFAF0D6930` | §6.1 队列列格式、§6.5 模型记录（WP1-51） |

**未验证条目汇总（诚实边界）：**

1. `-1073741819`（0xC0000005）退出码：证据树 rg 零命中，无任何实例记录。
2. PowerShell 变量大小写不敏感：PS 语言语义成立，但本项目无踩坑实例记载。
3. `write` clobber / `edit` fail-safe 的工具语义：harness 层行为，项目文档未记载（项目证据只到"同文件串行纪律"）。
4. worker 默认与 PM 窗口同模型的 harness 默认行为：项目实测口径见 §6.5，无框架文档出处。
5. `rg --no-messages` 禁令：仅见于本任务派发规格（task.md 检索纪律），`_pitfalls.md` 未载。
6. `quality_gate.py` 带参 CLI 用法：入口 `main()`（:102）与 `if __name__`（:239）已证实，参数形态未留档。
7. §1 表第 10/11 条（read 字节上限、控制台 UTF-8 输出做法）：本指南编写会话实测，非项目既有记载。
