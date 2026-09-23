# Multi-Workers — pi 之上的 Agent Team 协作框架

一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目，解决单 Agent 长上下文溢出和无法并行的问题。基于 [pi](https://pi.dev) 扩展系统构建，不 fork pi 核心。

```
PM 窗口 (pi + agent-team-loop, PM 模式)
  ├─ /mw-watch 看板 · /pm-key 认领 key · dispatch 派发
  ▼
mw serve 后台服务 (Python)
  ├─ LLM 代理 (本地隔离端口) · 任务调度 · worker launcher · watchdog
  ▼
Worker 1 (独立 pi 进程)   Worker 2 ...   Worker N
  ├─ agent-team-loop, Worker 模式 (PI_WORKER_TASK 切换)
  └─ .agenticdoc/ 文件协调: task.md → trace.log → output.md → _index.parallel
```

核心性质：

- **进程级隔离**：每个 Worker 是独立 pi 进程，崩溃不影响其他 Worker
- **文件驱动去中心化协调**：无中心调度器，Worker 之间不直接通信，通过 `.agenticdoc/` 下的文件 + 文件锁并发控制
- **Phase 门禁**：沿用 AgenticTask 语义（spec / design / plan / tasks / evidence）
- **凭证隔离**：每个 Worker 只拿到它需要的 API key，其他 provider 凭证从 env 中删除

## 组成

| 组件 | 位置 | 说明 |
|------|------|------|
| mw 服务 | `mw.py` + `launcher.py` + `proxy_multi.py` | 后台常驻：调度器、launcher、看门狗、LLM 代理（可选，见 CLI 参考） |
| agent-team-loop 扩展 | `../coding-agent/src/extensions/agent-team-loop/` | PM 模式（编排）+ Worker 模式（执行），构建后装到 `~/.pi/agent/extensions/` |
| AgenticTask 工作流 | `.agenticdoc/` | spec / design / plan / tasks / trace / evidence 与 `_index.parallel` 索引 |

## 快速开始（新机器一条命令）

```bash
git clone https://github.com/wenbocode/Multi-Workers.git
cd Multi-Workers
python packages/multi-workers/mw.py bootstrap --project .
```

`bootstrap` 按序执行 8 步，全部幂等，可反复重跑：

| 步骤 | 内容 |
|------|------|
| 1 | 前置检查：Python/Node 版本、git，以及**凭据预检**。无可路由凭据不阻断全新安装（此时 `~/.pi/agent/auth.json` 尚不存在）：警告后继续，步骤 2-6 本就无需凭据，**跳过步骤 7**（服务启动），提示配好凭据后用 `bootstrap --fast` 补启 |
| 2 | `npm ci` / `npm install --ignore-scripts` |
| 3 | `npm run build`（根；ai 构建需网络拉取 models.dev） |
| 4 | 全局 link `pi`：已存在则校验链接目标确为本仓库（防 registry 版顶替），失败时提示 `npm uninstall -g` 修复 |
| 5 | `setup`：克隆 AgenticTask 框架 + 全局安装扩展；Windows 上检测并填充 pi 的 `shellPath`（`~/.pi/agent/settings.json`，只在缺失/失效时写入，已有有效值不覆盖） |
| 6 | `init`：创建 `.agenticdoc/` `.mw/` `.pi/extensions/` 脚手架 |
| 7 | `start`：后台启动服务（无凭据路径下跳过，见步骤 1） |
| 8 | `doctor`：全链路诊断，期望 `summary: healthy` |

常用参数：

```bash
--project DIR     控制工作区（默认仓库根）
--from SOURCE     AgenticTask 框架来源（默认远端）
--branch BR       框架分支
--fast            跳过 npm install + 构建（凭据配好后的补启重跑；要求此前完成过一次完整 bootstrap）
--no-start        不启动服务（步骤 1-6 + doctor）
```

## CLI 参考

更新方式总览（版本锚点自检 + 指令矩阵 + 场景最小动作）：见 [UPDATE.md](./UPDATE.md)。

```bash
python mw.py <子命令>
```

| 命令 | 说明 |
|------|------|
| `serve` / `start` | 前台 / 后台运行服务。参数：`--project`（必填）、`--pi-port`（默认 7001）、`--claude-port`（7003）、`--deepseek-port`、`--poll-interval`（2s）、`--max-workers`、`--providers`。LLM 代理按需启动：仅当 claude/claude-cli/deepseek 代理路由有凭证时才拉起（需私有包 `timi-proxy-cli`）；纯 timi/codex 直连路由不起代理、无该包也能正常服务 |
| `stop` / `status` | 停止 / 查看服务 |
| `doctor [--json] [--fix]` | 全链路诊断：服务、代理端口、日志、队列、凭据、bundle、target、pi shellPath |
| `bootstrap` | 新机器一键安装（见上） |
| `init [--no-framework]` | 初始化项目脚手架；`--no-framework` 跳过 AgenticTask 框架安装 |
| `build [--install]` | esbuild 重建扩展 bundle（无 bash 依赖、cwd 无关）；`--install` 同时装到全局扩展目录并重建 pi dist |
| `setup` | 一次性机器初始化：克隆框架 + 全局装扩展 + 自动填充 pi `shellPath`（Windows；幂等，不覆盖已配置值） |
| `pull-agentictask` / `push-agentictask` | 更新 / 推送 AgenticTask 框架 |
| `update-env [--apply] [--json] [--fetch]` | 增量自检（UPDATE.md 锚点：bundle/dist/serve/框架传播）；`--apply` 执行安全修复后复查 |
| `target set/show/clear` | 双工作区配置（见下） |
| `ue-toolchain run/targets/hash` | dual 模式 UE 工具链纪律（见下）：执行模板并留证（错误签名双判 + --watch 前后哈希）、发现 UE 构建目标名、EOL 归一化哈希 |
| `model set/show/clear` | 派发模型默认值（见下） |

## 派发模型默认值

`mw model set <role> <provider/model>` 配置各角色的默认模型，未显式指定 `model:` 的任务在派发时逐层回退：

```
task.md model:  >  dispatch.yml [role]  >  当前窗口模型  >  每路由硬编码默认
（显式指定）        （前缀需匹配路由）     （.mw/window-model）  （pi+timi→glm-5.3、codex→gpt-5.6-sol）
```

角色：`main`（PM 主窗口，无显式选择时 session_start 套用）、`coding`（coding/phase-writer/repair/roadmap-writer/无类型）、`review`（review/verifier/reviewer）、`research`。配置存于项目级 `.mw/dispatch.yml`（gitignore，随机器本地）。

模型值用 `前缀/模型 id` 命名空间，前缀选择供应渠道：

| 前缀 | 渠道 | 说明 |
|------|------|------|
| `timi/` | pi + timi 直连 | 默认路由 |
| `claude/` | pi + anthropic 直连 | 不走 mw 代理，ANTHROPIC_API_KEY 直连 |
| `codex/` | pi + openai-codex | 用 codex 自身配置，无需代理凭证 |
| `deepseek/` | pi + deepseek 直连 | 不走 mw 代理 |
| `codex_cli/` / `claude_cli/` | CLI 执行器 | 仅匹配对应 cli 的任务 |
| 裸 id（无前缀） | 任务原路由 | 兼容现有行为 |

前缀生效时覆盖任务的 provider 但**不换 cli**（工具白名单/watchdog/模型徽标是 pi worker-mode 功能）；不兼容或未知前缀的默认值跳过落到下一层，显式 task.md `model:` 值不兼容则报错进 worker.log。未配置时 worker 默认与主窗口模型一致（`.mw/window-model` 由主窗口扩展在 session_start/model_select 时记录）。

```bash
python mw.py model set --project . coding timi/glm-5.3
python mw.py model set --project . review timi/glm-5.3-air
python mw.py model show --project .      # 配置 + 窗口模型 + 各角色实际生效值
python mw.py model clear --project . review
```

PM 窗口里也可用 `/mw model`（转发到同一 CLI）：`/mw model show` · `/mw model set <role> <prefix/model>` · `/mw model clear <role|all>`。worker 角色下次 spawn 生效（无需重启 serve）；`main` 角色在窗口下次启动时套用。

`mw doctor` 的 `dispatch` 段展示配置状态；配置文件损坏仅降级为建议（不阻断派发，回退窗口模型/硬编码默认）。

### 派工类型与模型覆盖门禁（mw-dispatch-role-escape）

`dispatch_worker` 工具与 `/worker` 命令都可显式声明任务类型，直接选择对应的 dispatch.yml role 与 worker 工具白名单：

- `type: coding | review | research`（工具参数 `type`，命令 `--type`；省略时按 cli 推导：pi→coding、claude→review、codex→codex）。此前 pi 任务恒为 `coding`，`review`/`research` 档对 pi 不可达——只能靠手填 `model:` 绕过策略。
- 覆盖 role 默认值必须给出理由：`model_reason`（工具）/ `--reason`（命令），记录为 task.md 的 `model-reason:` 单行；缺理由直接拒绝派发（不建目录、不写队列行）。请求值与 role 默认值相同时不写 `model:` 行（配置保持唯一事实来源，改配置即生效）。
- pi 路由的模型值（显式值或本次生效的 role 默认值）在派发时对照 pi 模型表校验：不在表内（如 `timi/gpt-5.6.sol`）直接拒绝，避免 pi 把它静默当作 custom model id 使用。`codex_cli/`/`claude_cli/` 前缀与 cli ≠ pi 的任务跳过校验；模型表缺少该 provider 时不判错；逃生口是显式 `model` + 理由。
- launcher 在 task.md 显式值偏离 role 默认值时，于原有 `source=task` 行后追加 `[launcher] <key>: model-override task=<X> config:<role>=<Y>` 到 launcher.log（仅证据，解析顺序与派发行为不变）。

## 双工作区：代码目录与工作目录分离

默认 **single 模式**：控制工作区与目标项目是同一个目录。配置 `target.yml` 后进入 **dual 模式**：

```
控制工作区 (control root)                  目标项目 (game root)
├─ .agenticdoc/          ← 所有协调文件    ├── Source/ ...
├─ target.yml            ← 配置本体        └── ProjectX.uproject
├─ _index.parallel                          引擎根 (engine root, 可选)
└─ {key}/workers/{task}/task.md
   └─ trace.log / output.md ← 写回这里
```

- Worker 进程 **cwd = game root**（相对路径、工具链锚定目标项目）
- 一切**协调写入**（trace.log / output.md / phase docs / goal check）通过 `PI_WORKER_TASK` 反推 control root，写回控制工作区——**目标树零框架文件**
- `read_scope` 相对条目按 game root 展开，`ignore.deny_globs` 作为上下文防火墙（deny 优先于 allow）
- 派发时把 toolchain / 防火墙清单 / contract 注入 task.md，Worker 无需感知 target.yml 的存在
- 配置坏时 fail-closed：拒绝派发，不静默下发未注入的 task.md

### 配置方式

CLI（优先级：env > target.yml > single 默认）：

```bash
python mw.py target set --project <控制工作区> \
    --game <UE项目根> \
    [--engine <引擎根>] [--vcs git|p4|none] [--uproject <.uproject>]
python mw.py target show --project <控制工作区>   # 查看解析后的生效视图
python mw.py target clear --project <控制工作区>  # 删除 target.yml，回到 single
```

pi 窗口内（新窗口生效）：

```
/mw target show
/mw target set --game "D:\My Game" --engine D:\UE5 [--vcs git|p4|none] [--uproject <file>]
/mw target clear
```

`set`/`clear` 自**下一次 worker 派发**生效，无需重启 serve（launcher 每次 spawn 重新解析）。带空格的路径用双引号。
环境变量临时覆盖（不落盘）：`MW_TARGET_GAME` / `MW_TARGET_ENGINE`。
`target.yml` 三个手工维护段（`mw target set` 只管理 bootstrap 字段，不碰这些）：

```yaml
toolchain:
  # 带 {game}/{engine}/{uproject} 占位符的命令模板（PM 直执走 mw ue-toolchain run，见下）
ignore:
  deny_globs: ["**/*.uasset", "**/DerivedDataCache/**"]   # L1 上下文防火墙
contract:
  forbidden_paths: [...]
  conventions: |
    项目约定，注入每个 task.md
  docs: [docs/api.md]
```

### 工具链执行纪律（mw ue-toolchain）

**定义域**：dual 模式的 UE 游戏开发项目（游戏仓 + 引擎源码仓 + `.uproject`，MSVC/UBT 工具链）。`run` 的留证/判定纪律和 `hash` 是工具链无关的通用件；`targets` 目标发现（`Source\*.Target.cs`）和 `errors.txt` 错误签名（`error C` / `LNK` / `error :`）是 UE/MSVC 专用。

toolchain 模板不只是注入 task.md 的文档——PM 直执时用 `mw ue-toolchain` 落地[dual 实践指南](./docs/dual-toolchain-practice-guide.md)的通用纪律：

- `python mw.py ue-toolchain run <name> --project <dir> [--args="-MaxParallelActions=16"]`（`--args` 值以 `-` 开头时必须用等号形式）—— 控制工作区根执行渲染后的命令，工件落 `<control>/.mw/toolchain-runs/<时间戳>-<name>/`：`cmd.txt`（逐字命令留档）、`run.log`（UTF-8 合并输出，`.log` 扩展名——质检脚本只扫 `*.log`）、`exit.txt`（退出码）、`errors.txt` + `meta.json`（错误签名扫描 `error C` / `LNK` / `error :`——退出码必要但不充分）；`--watch <file>` 前后 EOL 归一化 sha256，证明命令执行期间无人改被编译源码；`--out` 可把 run 目录指到 key evidence 归档。mw 退出码 0 = exit 0 ∧ 错误行 0 ∧ 无漂移；差分验收（基线本来就红的项目）对比两次 run 的 `errors.txt` 集合。
- `python mw.py ue-toolchain targets --project <dir>` —— 从 `<game>/Source/*.Target.cs` 现查构建目标名（`*Editor` = editor target），勿猜。
- `python mw.py ue-toolchain hash <file>...` —— EOL 归一化 sha256（引擎仓 `core.autocrlf=input` 会在 checkout/rebase 时把 CRLF 翻成 LF，字节级哈希会假漂移）。

## pi 窗口命令

| 命令 | 说明 |
|------|------|
| `/pm-key <key>` | 认领并 watch 一个 AgenticTask key |
| `/pm-save` | 会话快照写入 `pm-state.md` |
| `/mw-watch` | 切换 Worker 进度看板 widget |
| `/worker <claude\|codex\|pi> [--model <id>] <任务描述>` | 派发一个 worker |
| `/mw build \| init \| start \| stop \| status \| doctor [fix] \| update [--apply]` | 服务与 bundle 管理（update = 锚点自检，见 [UPDATE.md](./UPDATE.md)） |
| `/mw target show \| set \| clear` | 双工作区配置（见上） |
| `/mw ack <task-key> \| all` | 确认终态 worker 结果 |

### 实施准入门禁（mw-implementation-gate）

非 trivial 实施（新功能、多文件改动、超出一行修的东西）必须先有 active key——这条纪律现在由 agent-team-loop 扩展的 `tool_call` 硬门机械化执行：write/edit（以及 bash 写目标收窄判定）命中仓库代码路径（`packages/**` 代码扩展名，排除 node_modules/dist/.tmp）且窗口无 active key claim 时拒绝执行，reason 内给出两条合规路径。放行条件（任一）：

1. `_index.parallel` 中存在本窗口 host:pid 的 active claim（写 `.agenticdoc/<key>/spec.md` 即自动 claim）；
2. `PI_WORKER_TASK` 存在（被派发的 worker 预授权）；
3. 新鲜（≤24h）的 `.agenticdoc/<key>/mini-spec.md`（trivial 修复快路径，放行留审计行）。

每次 block 与 mini 放行追加一行到 `.agenticdoc/_impl_gate.log`（best-effort，不影响判定）。bash 侧只判写结构的目标参数、声明非沙箱（`python -c` 内联写等已知漏过，见模块头注释）。生效条件：`mw setup --build` 重建 dist 并重启窗口；旧 bundle 进程重启前不受门禁。

## Autopilot 配置与停滞处置（mw-autopilot-stall-feedback）

`.agenticdoc/_autopilot/config.json`（缺失即默认；存在但非法会 fail-closed 报错）：

| 键 | 默认 | 说明 |
|----|------|------|
| `enabled` / `paused` | false / false | 总开关；`mw serve` 据此启停 conductor |
| `poll_interval_sec` | 4 | tick 周期（1..5，受 AC-019 心跳预算限制） |
| `max_parallel_keys` | 2 | 同时推进的 key 上限 |
| `round_budget` | 2 | L1↔L2 / L3 复评 / 任务重试共用的轮数上限 |
| `advance_stall_ticks` | 5 | 同一 `(key, edge)` 的 phase 推进连续失败次数阀值（1..50）；达阼值即把 key 标 `stalled` 并建门禁 |
| `worker_timeout_min` | 30 | worker 墙钟兜底超时 |

停滞处置：

- 每次失败的 `advance` 事件带分类（`class=interface-drift|gate-blocked|timeout-env|other`），连击从 timeline 尾部重派生（无私有状态），因此 conductor 重启不丢。
- `approve` 一个 `stalled` 门禁 = 该 key 回到 `running`，且 L2 / EXECUTE / L3 / repair 四个预算点**各放宽一轮**（额度 = 该 key 已批准的 stalled 门禁数）；该额度**不可复用**——每个回路自己的轮次计数是单调的，用掉那一轮后同一回路会再次到顶、需要新的人工决定；`reject` = 既有 `closed-legacy` 语义。
- `L3 无裁决`：reviewer worker 崩溃（`output.md` 缺失）不再被当成 `below`，而是重派下一轮 L3，停滞原因也写明 worker 状态与 task_key。
- 新增 timeline 事件类型：`resume`（人工 approve 后恢复）、`l3-no-verdict`（reviewer 未交裁决）。
- PM 窗口底部监控面板会展示 tick 新鲜度 / 槽位 / 每 key 相位与状态 / 停滞连击与最近错误，并在 `stalled` 行给出 `/autopilot gate <id> approve|reject` 处置命令；面板的连击派生与 conductor 守卫同口径（只有**同一 edge** 的成功才清除，相邻边界的成功既不打断也不计入），唯一差异是面板会保留 `stalled`/`gate-created` 之后的那一轮连击以便展示。

## 关键环境变量

| 变量 | 说明 |
|------|------|
| `PI_WORKER_TASK` | Worker 的 task.md 路径；设置即进入 Worker 模式 |
| `PI_WORKER_TIMEOUT_MS` | Worker 墙钟兜底（默认 60m；task.md `timeout:` 分钟头优先） |
| `PI_WORKER_IDLE_MS` | 无活动判挂死阈值（默认 10 分钟） |
| `MW_TARGET_GAME` / `MW_TARGET_ENGINE` | 双工作区临时覆盖 |
| `MW_PY` | 扩展找不到 `mw.py` 时手动指定路径 |
| `MW_IMPL_GATE_ROOT` | 门禁项目根覆盖（测试钩子，默认 cwd） |
| `MW_RAG_SERVERS_FILE` | 机器级 RAG 配置的硬覆盖路径（设定但缺失 = 机器层为空，**不回落到 HOME**，用于测试隔离） |
| `MW_RAG_SERVERS_HOME` | 机器级 RAG 配置的 HOME 覆盖（其后依次尝试 `HOME`、`USERPROFILE`） |
| `MW_RAG_PYTHON` | `skill` 形态 RAG 的解释器覆盖（缺省 Windows `python` / 其它 `python3`） |

## RAG 接入（可配置）

RAG 是**可选**能力：只有项目显式启用时才注册工具、才往 task.md 注入块；未启用项目零影响
（工具不注册、不写任何文件、不发探活请求）。完整的逐字段配置手册（四类可直接复制粘贴的示例、命令参考、
退出码、失败 signature 与排查）：[`docs/rag-config-guide.md`](docs/rag-config-guide.md)。

### 两层配置与逐字段合并

| 层 | 路径 | 用途 |
|----|------|------|
| 机器级 | `~/.agents/rag-servers.yml` | 本机所有 RAG 服务的连接信息 |
| 项目级 | `<control>/.mw/rag-servers.yml` | 项目覆盖（同名 server 逐字段覆盖机器级） |

两层文件形态都是 `{servers: {<name>: {...}}}`（只有 `servers` 是合法顶层键）。合并是**逐字段**的：
同名 server 的项目级字段覆盖机器级，`null` 删除该字段，数组（`sources`）整体替换；每个字段的来源
记在 `origin` 里（`rag list --json` 可查）。`target.yml` 的 `rag:` 段决定启用集与角色/阶段要求：

```yaml
rag:
  enabled: [overcode]              # 启用集（空或缺省 = 全关）
  default_server: overcode
  roles:
    coding: { server: overcode, require: false, rewrite: true }
    review: { server: overcode, source: docs, require: true }
  phases:
    design: { server: overcode, require: true }   # required = role.require OR phase.require
  budgets:
    time_budget_s: 900
```

`required = role.require OR phase.require`（并集，无例外）。`phase` 取**派发时** key 的阶段，由派发器
写进 task.md 的 `phase:` 头（阶段未知或 `_scratch` 不写该行；`target.yml` 的 `phases:` 键必须与
`pm-state.md` 的阶段值同大小写）。"必需"的判定标准是**产物里有可核对的引用**（`citation` + 本地路径
存在），不是"调用过工具"。

服务形态 `transport`：`mcp`（streamable-http，默认）/ `skill`（本地 CLI）/ `both`（mcp 为主，**连接层**
失败且只读工具时才回落 CLI；`rag_feedback`、`rag_chat`、超时永不自动回落）。凭证只以 `token_env` 名
出现在配置里，值由 `mw serve` 进程环境注入（task.md / trace / evidence 里不会出现值）。

### 命令

`--project <dir>` 是四个子命令的共同必填参数（argparse `required=True`）。

```bash
python mw.py rag list  --project <dir> [--json]                             # 合并后的 server 表与逐字段来源
python mw.py rag probe --project <dir> [--json]                             # 探活（诊断；不可达仍退 0）
python mw.py rag audit --project <dir> [--key <KEY>] [--json] [--out FILE]  # 只读审计：rag_call / 引用 / required-but-unused（无 --out 只写 stdout）
python mw.py rag sync  --project <dir>                                      # 把 skill 形态的说明文件同步到 .pi/skills
```

退出码（以 `mw.py` 实现为准）：

| 命令 | 退出码 |
|---|---|
| `list` / `probe` | 0 = 成功；1 = 配置错误（`probe` 不因服务不可达而失败） |
| `sync` | 0 = 成功；1 = 配置错误或框架 skill 源文件缺失 |
| `audit` | 0 = 无 `missing` / `unverified` / `required_missing`；1 = 有任一；2 = 用法或配置错误 |

### 工具面

启用后 worker 多出 6 个工具：`rag_search`、`rag_symbol`、`rag_graph`、`rag_impact`、`rag_sources`、
`rag_feedback`；`rag_chat` 只在 `rag-research` 类型下可见。引用格式为
`server:source:file_path:line` —— 左侧两段是 server/source，最右侧数字段是行号，中间全部内容
（允许含 `::`）都是 file_path。

逻辑名与参考服务（overcode）真实工具名的映射（AC-018）：

| 逻辑工具 | 线上工具名 | 说明 |
|---|---|---|
| `rag_search` | `rag_search` | 重写开关为真时改走 `rag_search_multi_rounds`（服务端多轮改写） |
| `rag_symbol` | `rag_symbol` | |
| `rag_graph` | `graph_query` | |
| `rag_impact` | `rag_impact` | |
| `rag_sources` | `list_sources` + `list_collections` | 两次调用合并为一个信封 |
| `rag_feedback` | `rag_feedback` | |

映射在适配器（`overcode-v1`）里以数据表维护：换服务族 = 加一个适配器，不改配置 schema。表中 6 行是
**六个基工具**的映射；`RAG_TOOL_MAP` 里还有第 7 条 `rag_chat`（`mcp: ["rag_chat"]`），它只在 `rag-research`
任务注册，故不列在此表。

`rag-rewrite-degraded` 与上面「开了多轮」是相反的语义：只有服务端响应信封的
`meta.rewrite_degraded === true`（服务端**改写失败**、降级为普通检索）时才追加该 trace 行
（`rag/adapter.ts` 的 meta 白名单 + `rag/tools.ts` 的判定）；它**不是**「启用了多轮改写」的标记。

### 降级与证据

五层降级：未启用 = 工具不可见；探活失败 = 注册但标注 `[unreachable at session start]`；运行时失败 =
熔断（连续 3 次连接/超时/协议错误，能力错误不计）；必需但服务不可用 = 告警；必需但没用 = 告警。
worker trace 里会出现 `rag_call`（含 `mcp_tool` 真实线上名）、`rag_fallback`、`rag-required-missing`、
`rag-rewrite-degraded` 等行；`mw rag audit` 只读地对这些行做独立判定。

## 待实现（Backlog）

- **直连路由泛化**：`launcher._build_env` 的 timi 直连特判泛化为「providers.json 中无 `port` 的路由 = 直连」，新 provider 照 timi 模式注册原生 provider + 无 port 路由条目即可用，无需 proxy。 已落地最小版（mw-provider-routing，zai-coding-cn 走第 5 个直连分支 + zai/ 前缀）；本项保留为完整泛化：pi_providers 数据驱动段取代全部硬编码分支（deepseek 键在 providers 段带 port 7004，朴素「无 port=直连」启发式对其不可行，见 .agenticdoc/mw-provider-routing/design.md D-001）。
- **proxy 定位收敛**：仅服务「外部 CLI + 协议翻译」场景（claude/deepseek CLI）。需要时将 `timi_proxy_cli` 的最小闭包（proxy.py / logging_utils.py / config.py / models.py / constants.py，约 40KB 纯标准库、零 pip 依赖）vendor 进 packages/multi-workers，消除对私有 editable 包的机器级依赖。

## 测试

```bash
cd packages/multi-workers
python -m pytest -q          # 430+ 通过；e2e 默认 deselect
```
