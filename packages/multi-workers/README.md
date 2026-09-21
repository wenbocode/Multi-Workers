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
  # 带 {game}/{engine}/{uproject} 占位符的命令模板
ignore:
  deny_globs: ["**/*.uasset", "**/DerivedDataCache/**"]   # L1 上下文防火墙
contract:
  forbidden_paths: [...]
  conventions: |
    项目约定，注入每个 task.md
  docs: [docs/api.md]
```

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

## 关键环境变量

| 变量 | 说明 |
|------|------|
| `PI_WORKER_TASK` | Worker 的 task.md 路径；设置即进入 Worker 模式 |
| `PI_WORKER_TIMEOUT_MS` | Worker 墙钟兜底（默认 60m；task.md `timeout:` 分钟头优先） |
| `PI_WORKER_IDLE_MS` | 无活动判挂死阈值（默认 10 分钟） |
| `MW_TARGET_GAME` / `MW_TARGET_ENGINE` | 双工作区临时覆盖 |
| `MW_PY` | 扩展找不到 `mw.py` 时手动指定路径 |

## 待实现（Backlog）

- **直连路由泛化**：`launcher._build_env` 的 timi 直连特判泛化为「providers.json 中无 `port` 的路由 = 直连」，新 provider 照 timi 模式注册原生 provider + 无 port 路由条目即可用，无需 proxy。 已落地最小版（mw-provider-routing，zai-coding-cn 走第 5 个直连分支 + zai/ 前缀）；本项保留为完整泛化：pi_providers 数据驱动段取代全部硬编码分支（deepseek 键在 providers 段带 port 7004，朴素「无 port=直连」启发式对其不可行，见 .agenticdoc/mw-provider-routing/design.md D-001）。
- **proxy 定位收敛**：仅服务「外部 CLI + 协议翻译」场景（claude/deepseek CLI）。需要时将 `timi_proxy_cli` 的最小闭包（proxy.py / logging_utils.py / config.py / models.py / constants.py，约 40KB 纯标准库、零 pip 依赖）vendor 进 packages/multi-workers，消除对私有 editable 包的机器级依赖。

## 测试

```bash
cd packages/multi-workers
python -m pytest -q          # 430+ 通过；e2e 默认 deselect
```
