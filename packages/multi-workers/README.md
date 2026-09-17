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
| 5 | `setup`：克隆 AgenticTask 框架 + 全局安装扩展 |
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

```bash
python mw.py <子命令>
```

| 命令 | 说明 |
|------|------|
| `serve` / `start` | 前台 / 后台运行服务。参数：`--project`（必填）、`--pi-port`（默认 7001）、`--claude-port`（7003）、`--deepseek-port`、`--poll-interval`（2s）、`--max-workers`、`--providers`。LLM 代理按需启动：仅当 claude/claude-cli/deepseek 代理路由有凭证时才拉起（需私有包 `timi-proxy-cli`）；纯 timi/codex 直连路由不起代理、无该包也能正常服务 |
| `stop` / `status` | 停止 / 查看服务 |
| `doctor [--json] [--fix]` | 全链路诊断：服务、代理端口、日志、队列、凭据、bundle、target |
| `bootstrap` | 新机器一键安装（见上） |
| `init [--no-framework]` | 初始化项目脚手架；`--no-framework` 跳过 AgenticTask 框架安装 |
| `build [--install]` | esbuild 重建扩展 bundle（无 bash 依赖、cwd 无关）；`--install` 同时装到全局扩展目录并重建 pi dist |
| `setup` | 一次性机器初始化：克隆框架 + 全局装扩展 |
| `pull-agentictask` / `push-agentictask` | 更新 / 推送 AgenticTask 框架 |
| `target set/show/clear` | 双工作区配置（见下） |

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
| `/mw build \| init \| start \| stop \| status \| doctor [fix]` | 服务与 bundle 管理 |
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

## 测试

```bash
cd packages/multi-workers
python -m pytest -q          # 430+ 通过；e2e 默认 deselect
```
