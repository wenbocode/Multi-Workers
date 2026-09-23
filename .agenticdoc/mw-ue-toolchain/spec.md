# Spec: mw ue-toolchain（dual 模式 UE 工具链纪律）

> Key: mw-ue-toolchain
> 创建时间: 2026-09-21
> 状态: retroactive（实现已完成于主窗口，本 key 为事后补登记以恢复可追溯性——见 key-decision.md 流程偏差记录）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本项目 goal 是在 pi 之上构建 PM+Worker 协作框架；本 key 服务于 PM 侧直执能力——dual UE 项目的 PM 此前只能把工具链命令模板文本注入 task.md 让 Worker 参考，无执行/取证/判定纪律；吸收前线实践指南（AssetImportGate）后 PM 可直执并留证。
- 继承约束（GC 编号）：
  - GC-1: 不修改 pi 核心——全部改动限 `packages/multi-workers`（mw.py / mw_common.py / docs / tests），通过 mw CLI 扩展实现。
  - GC-2: 文件驱动协调——run 工件（cmd.txt/run.log/exit.txt/errors.txt/meta.json）即文件证据，质检脚本只扫 `*.log`。
- 冲突：无。
- 预期收益：dual UE 项目 PM 直执工具链命令获得机器可判定 verdict（exit ∧ 错误签名 ∧ --watch 漂移），替代"退出码绿即通过"的弱判定；done 时在 achieved.md 对照判定（AC-001~008 全勾 + 指南入仓 + 定义域钉死）。

## §1 功能概述

### 1.1 目标
把前线实践指南（`C:\...\WXWork\..._toolchain-dual-mode-guide.md`，AssetImportGate 项目产出）的通用纪律（§9.B）吸收为 mw CLI 能力：执行留证、错误签名双判、目标名现查、EOL 归一化哈希。指南原文入仓固化（WXWork 缓存路径会失效）。

### 1.2 技术栈 / 语言
Python（mw.py / mw_common.py，stdlib only）+ Markdown 文档 + pytest。

### 1.3 核心用户场景
1. PM 在 dual UE 项目直执 `toolchain.<name>` 模板：渲染 → 控制根执行 → 工件归档 → 机器判定。
2. PM 现查构建目标名（勿猜 `Source\*.Target.cs`）。
3. freeze/drift 检查用 EOL 归一化哈希（引擎仓 autocrlf 翻 EOL 不假漂移）。

### 1.4 范围说明（不做什么）
- 不做 `exclusive_files` 写者唯一性派发检查（harness 工具语义指南里标注【未验证】，需先验证派发层行为，立后续 key）。
- 不做 `/mw toolchain` TS 窗口转发（PM 窗口 bash 直跑 CLI 已可用；TS 转发需窗口重启，立后续 key）。
- 不做非 UE 工具链支持（错误签名集硬编码 MSVC/UE；动词名即定义域）。

## §2 业务约束

### 2.1 平台 / 环境
Windows + PowerShell 5.1 主环境（P-001：验证输出走文件/read 工具）；Python 3.x stdlib only，无新依赖。

### 2.2 性能指标
无特殊要求（CLI 短命令）；subprocess 同步执行。

### 2.3 安全约束
`shell=True` 执行 target.yml 配置的命令——命令源为项目自有配置文件（与既有 render_toolchain_command 注入 task.md 同信任域）；无凭据接触。

### 2.4 集成依赖
target.yml dual 配置（mw-dual-workspace 建立的 `load_target_config`/`render_toolchain_command` 既有面）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-21T21:00:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 dual 项目（target.yml mode=dual 且 toolchain.ping 为 `python -c "print('ok')"`）下，`python mw.py ue-toolchain run ping --project <dir>` 退出码 0，且 `<control>/.mw/toolchain-runs/<stamp>-ping/` 含 cmd.txt / run.log / exit.txt / errors.txt / meta.json 五个文件，meta.json `ok=true` |
| AC-002 | 在命令输出含 `error C2039` 行且自身退出码 2 的配置下，`ue-toolchain run` 退出码 1 且 errors.txt 含该签名行（退出码必要但不充分） |
| AC-003 | 在 `--watch` 文件被所执行命令自身修改（命令 exit 0）的配置下，`ue-toolchain run` 退出码 1 且 meta.json `watched_drift_count=1` |
| AC-004 | 在 game/Source 含 Proj.Target.cs 与 ProjEditor.Target.cs 的 dual 项目下，`ue-toolchain targets` 输出含 `Proj (game)` 与 `ProjEditor (editor)`；无 Source 目录时输出 `no *.Target.cs` 且退出码 0 |
| AC-005 | 对内容相同仅 EOL 不同的两个文件（CRLF/LF），`ue-toolchain hash` 输出相同 sha256；内容不同则不同 |
| AC-006 | 在 toolchain 模板引用 `{engine}` 而配置缺失 engine 的 dual 项目下，`ue-toolchain run` 退出码 1 且 stderr 含 `missing-field`（fail-closed） |
| AC-007 | 在请求未配置的命令名时，`ue-toolchain run` 退出码 1 且 stderr 含 `no toolchain command named` 及已配置名列表 |
| AC-008 | `mw.py ue-toolchain --help` / `run` / `targets` 三个入口退出码 0；旧动词 `mw.py toolchain ...` 退出码 2（argparse 未知子命令，无别名双轨） |

## §4 风险与未决项

- 风险：`shell=True` + 配置命令模板的注入面（同 trust 域内可接受，已记 §2.3）。
- 风险：错误签名正则硬编码 MSVC/UE——非 UE 工具链误用会假 OK（以动词名 `ue-toolchain` + help 文本钉定义域缓解）。
- 待确认：差分验收（基线红项目对比两次 errors.txt 集合）尚未有真实 UE 项目落地用例。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产
- `mw_common.load_target_config` / `render_toolchain_command` / `toolchain_probe_path`（mw-dual-workspace 建立的 target.yml 配置与占位符渲染面，本 key 直接复用）。
- `test_common_target_config.py` 的夹具模式（`<control>/.agenticdoc/target.yml` + `load_target_config(control, env={})`）。
- README dual 节 / CHANGELOG / UPDATE.md 的文档维护面。

### 需规避坑点
- P-001（PowerShell 控制台 mojibake）：验证输出一律 read 工具 / 文件 / UTF-8 落盘，不用控制台直读。
- P-003（`open(p, "w")` 截断陷阱）：本 key 的 run 工件全部一次性 `write_text(..., encoding="utf-8", newline="\n")`（同时规避 PS 5.1 重定向 UTF-16 坑），无读-改-写竞态。
- P-002（跨窗口共享文件）：改动限 `packages/multi-workers` 本 key 自有文件，不碰 `.agenticdoc/_index*`/`_project_log.md` 共享态。
