# Arch Snapshot — 架构快照 + 可复用资产清单

> 项目级记忆文档之一（pm-mind Hook 1 维护，key done 后经用户确认刷新；Hook 2 spec 生成前必读，spec §「可复用资产」取源于本清单）。
> 最近全量刷新：2026-09-20（mw-provider-routing done 后）。来源：goal.md + _project_log.md 全部 done key + 各 key achieved.md。

## 1. 系统架构现状

### 1.1 mw 后台服务（Python，`packages/multi-workers/`）
- `mw.py`：CLI 入口（serve / model / partition / doctor / build --install 等）。
- `mw_common.py`：共享层——providers.json + `_DEFAULT_CONFIG` 加载、凭证链（`resolve_credential` env→auth.json 双源、`describe_missing`、`route_precheck`）、queue/index 文件并发原语、watchdog、doctor、target.yml v2 partition 配置、模型选择链（`resolve_dispatch_model`：task.md `model:` > dispatch.yml role > window-model > per-cli 默认）。
- `launcher.py`：worker 进程派发——`_resolve_entry_model`/`_effective_entry`（prefix 重映射）、`_build_env`（凭证注入/剥离）、`_build_command`（CLI 命令构造）、`_spawn`（全路径解析 + 派发日志）、queue poll / 孤儿 reconcile。
- `providers.json`：`credentials`（多源凭证链）+ `providers`（路由表：带 `port` = 走 mw proxy；无 `port` = 直连）。
- on-demand proxy（mw-proxy-on-demand 交付）：仅带 port 路由有凭证时 spawn `proxy_multi.py`。

### 1.2 agent-team-loop 扩展（TS，`packages/coding-agent/src/extensions/agent-team-loop/`，dist bundle 随构建同步）
- PM 模式：task-dispatcher、watch widget（三区渲染 + ack 通道）、advance_phase 集成、`/worker` 派发命令。
- Worker 模式：worker-mode（PI_WORKER_TASK 切换）、read-scope（read_scope/deny_globs 防火墙 + parent union）、protected-config（auth.json 等硬拦截）、退出树杀。
- shared：dispatch-models（PROVIDER_ID_TO_PREFIX 与 py 侧 parity 锁）。

### 1.3 文件驱动去中心化协调（GC-1）
- `_workers.parallel`（队列，O_CREAT|O_EXCL 锁）+ `_index.parallel`（key/phase 表）+ `goal.md`（项目目标锚点，低频变更）+ 每 worker 目录 trace.log/output.md/task.md。
- 无中心调度器，Worker 间不直接通信；PM 主窗口不经 mw（天然保底路径）。

### 1.4 Worker 生命周期（mw-worker-timeout-convergence / mw-worker-tree-kill）
- activity watchdog（无 token/工具/turn 活动 10 分钟判真挂死，`PI_WORKER_IDLE_MS` 可调）+ 墙钟兜底（默认 60m，task.md `timeout:` > `PI_WORKER_TIMEOUT_MS` > 默认）+ 30 分钟收敛检查点（[CHECKPOINT] 机器判据，mid/high risk 升级 PM）+ deadline steer。
- 退出树杀：worker-mode 4 退出位点 + exit 安全网 `killTrackedDetachedChildren`（taskkill /T / kill(-pgid)），防 bash 子树孤儿化。

### 1.5 工作区形态（mw-target-partition + mw-partition-parent-extended）
- dual：control workspace + game root 双根。
- partition（target.yml v2）：`active` 键 + 模式块；partition 模式 = parent root（**扩展可写工作区**，被切出的功能块所在地）+ partition root（worker cwd）+ 命名 roots；read_scope 默认并入 parent（空 scope/deny-only 保持 fail-closed，deny 优先）；profile v2 注入 + launcher 撕裂校验 fail-closed。

### 1.6 Provider / 模型路由（2026-09-20 现，mw-provider-routing）
- prefix 命名空间：`timi/claude/codex/deepseek/zai`（pi provider 前缀）+ `codex_cli/claude_cli`（CLI 传输前缀，须匹配 entry cli）；裸模型 ID 不动路由；未知 prefix → RuntimeError。
- 直连 pi providers：`timi`（默认路由，默认模型 glm-5.3）、`anthropic`、`openai-codex`、`deepseek`、`zai-coding-cn`（glm-5.3 系列，直连 open.bigmodel.cn；**无默认模型，必须显式 `--model`**；zai 家族固定 zai-coding-cn，无裸 `zai`）。
- 凭证隔离：`_stripped_env` 剥离一切其他 provider 凭证；worker env 仅注入所选路由 key + PI_WORKER_TASK；直连无 localhost base_url。
- 默认不变量：不指定 provider/model → timi；zai 不进默认/回退链。

## 2. 可复用资产清单

| 资产 | 位置 | 说明 |
|------|------|------|
| 凭证链 + 路由表机制 | providers.json / mw_common | 加新 provider 零代码：credentials 多源链 + providers 条目（直连则无 port） |
| 直连 provider 接入五步式 | achieved(mw-provider-routing) 沉淀 | providers.json → prefix 双侧 map → `_build_env` 照 timi 模式分支 → `_build_command` 直连元组 → e2e_real 冒烟；第 6 个分支时触发 pi_providers 泛化 key |
| prefix 双侧 parity 锁 | test_dispatch_models.py `_TS_MIRROR` + agent-team-loop.test.ts | 命名空间变更双侧强制同步，改一侧必红另一侧 |
| `_stripped_env` 凭证隔离 | launcher.py | 已覆盖任意声明的凭证链，新路由自动隔离 |
| 直连分支模板 | launcher.py timi/zai 分支 | resolve_credential → 注入 api_key_env + PI_WORKER_TASK，缺凭证 RuntimeError（含 describe_missing） |
| hermetic serve 测试模式 | test_serve_doctor.py TestServeSupervision | fake Popen + TEST_* 凭证，不依赖真机 env/auth.json |
| e2e_real 标记模式 | test_e2e_real.py | 默认 deselect，显式 `-m e2e_real` 真实派发冒烟；thinking 模型预算 ≥1024 |
| watchdog / 树杀 / 孤儿 reconcile | mw_common / worker-mode.ts | 超时三段式 + 子树清理 + 队列孤儿收敛 |
| partition profile v2 + golden parity | mw_common / fixtures | 注入块 golden 逐字节基线，dual/single 语义回归锁 |
| advance_phase / audit_phase 门禁脚本 | .agents/skills/agentic-task/scripts | phase 门禁 + evidence 校验，pm-state 接口行脚本专管 |

## 3. 已知边界 / 后续指针

- pi_providers 数据驱动泛化（消灭 launcher 硬编码直连分支）：README Backlog，独立 key，届时带 timi 专属回归矩阵。
- proxy 内化（timi-proxy-cli 进 mw 包）：README Backlog。
- `mw serve` 重启生效语义：Py 侧改动需重启常驻进程；JS bundle 对新 spawn worker 即时生效。
- `docs/zai_guider.md` 脱敏（untracked，含明文 key）：后续清理。
- 坑点台账见 `_pitfalls.md`（P-001 PowerShell UTF-8 管道损坏、P-002 会话内改共享配置）。
