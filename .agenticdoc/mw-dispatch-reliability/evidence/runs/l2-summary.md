# L2 Summary: mw-dispatch-reliability 执行验证汇总

日期: 2026-08-28 · Key: mw-dispatch-reliability · ClaimId: 20260828-160111-8496

## 1. 测试结果

| 层级 | 命令 | 结果 |
|------|------|------|
| L1 Python 单测 | `python -m pytest`（packages/multi-workers） | 101 passed, 1 deselected (e2e_real) |
| L2 真实链路 | `python -m pytest test_e2e_real.py -m e2e_real` | 1 passed（真实 timi LLM，回复 "ok"） |
| L1 TS 单测 | vitest `test/extensions/agent-team-loop.test.ts` | 18 passed |
| 类型检查 | tsgo --noEmit | agent-team-loop 全部文件 0 错误（仓库其余 580 个错误为并行会话的陈旧模型注册表问题，见 §4） |
| Lint | biome check --error-on-warnings（agent-team-loop + test/extensions） | 通过 |

## 2. 现场修复（本仓库 live 验证）

| 步骤 | 证据 |
|------|------|
| doctor-before | `doctor-before.txt`：ISSUES（历史 FATAL、stale 队列条目、bundle 过期 8/22 vs 8/25、缺 3 组凭证） |
| 启动 mw | PID 存活；mw.log 逐路由记录（timi=file 可用，codex-native=native，claude/claude-cli/deepseek=missing） |
| stale 自动归档 | `review-s1-verification`（task.md 已删的 pending 行）在启动后 ≤6s 移入 `_workers.stale.parallel`，launcher.log 记录 "archived stale entries" |
| 隔离探针 | `mw-dr-live-claude2/3/4`（cli=claude，无 ANTHROPIC_AUTH_TOKEN）→ 三次均单任务 failed + worker.log 写明 `env ANTHROPIC_AUTH_TOKEN unset`（watcher 捕获 pending→failed）；**launcher/service 存活 ≥81s** 且期间其他任务照常 done（原 crash-loop 根因消除）。注：初版 `mw-dr-live-claude` 误经默认 pi 路由派发（队列 cli=pi），其隔离断言作废并已重跑，见 `evidence/runs/l2-claude-isolation-rerun.txt` |
| 全链路探针 | `mw-dr-live-ok`（pi+timi 真实 LLM）→ done，output.md Summary="ok"（多行 prompt 经 _sanitize_prompt 完整送达模型，证明 .cmd 截断修复） |
| bundle 重建 | `mw.py build --install` ×2（第二次含 ui-bridge 类型修复），全局 bundle mtime > 源码 mtime，doctor stale=False |
| doctor-after | `doctor-after.txt`：**healthy，退出码 0**（launcher.log 按 serve 会话轮转，历史 FATAL 不再误报） |
| PM 播报 | 本会话 PM 扩展实时上报两个探针任务终态（failed 带日志指引 / done 带摘要） |

## 3. 交付物清单

- `packages/multi-workers/mw_common.py`：凭证解析（env→file 链）、route_precheck、文件总线、stale 归档、doctor_report/fix
- `packages/multi-workers/launcher.py`：单任务故障隔离（不再 FATAL）、_sanitize_prompt、每轮 stale 扫描
- `packages/multi-workers/mw.py`：serve 预检门（PID 仅在预检后写入）、doctor 子命令、launcher.log 会话轮转
- `packages/multi-workers/providers.json`：声明式凭证 schema（timi 从硬编码迁移）
- TS：`mw-runner.ts`（waitForStart 3s 稳定窗 + doctorMw）、`ui-bridge.ts`（/mw doctor、工具注册补 label/details）、`pm-orchestrator.ts`（中文播报）
- 测试：`test_common.py`、`test_launcher.py`（改）、`test_serve_doctor.py`、`test_integration.py`（真实子进程+fake CLI）、`test_e2e_real.py`、`pytest.ini`、`agent-team-loop.test.ts`、`smoke_test.sh`（T5 假阳性修复）

## 4. 范围外既有失败（非本工作引入，已归因）

归因方法：`git worktree add` HEAD 干净树 + 补齐 gitignored 生成数据后重跑。

- `packages/tui` imageFallback 2 例 + `footer-width` 等：Windows 路径分隔符（`~\` vs `~/`），HEAD 即失败
- `agent-session-*`/`tools`/`extensions-runner` 等 93 例：本机环境既有失败，HEAD 干净树复现 21 例（agent-session-retry/tools/extensions-runner），与本地未提交改动无关
- tsgo 580 错误：并行会话修改 `packages/ai/scripts/generate-models.ts` 后模型注册表陈旧（ModelId 变 never），涉及文件与本工作零交集
- 上述均已留档，REVIEW 阶段可复核

## 5. 发现并修复的额外生产 Bug

Windows npm `.cmd` shim 逐行展开 `%*`：多行 `-p` 参数在首个换行处截断 → 真实 worker 会静默丢失整个任务正文。修复：launcher `_sanitize_prompt()` 折叠空白；集成测试以折叠后形态断言，e2e 断言完整语义送达。

## 6. 用户指令追加项（REVIEW 前变更，2026-08-28 20:30）

| 指令 | 实现 | 验证 |
|------|------|------|
| 凭证用 pi 自己的配置，不依赖 ~/.timi-anthropic-proxy/config.toml | providers.json + default_config 的 timi 链改为 env TIMI_API_KEY → ~/.pi/agent/auth.json（field 	imi.key）；修复 mw.py serve/doctor 未显式传 --providers 时误用内存默认而不读包内 providers.json 的 bug | doctor: 	imi available (file ~/.pi/agent/auth.json)；e2e_real 重跑通过（真实 glm-5.3 回复 ok）；101 例单测全绿 |
| 默认模型改 glm5.3 | launcher pi+timi 默认 --model glm-5.3（codex 默认不变） | 单测断言更新；现场探针 mw-dr-glm53 → done，output.md "ok" |
| pi 启动时连带启动 mw | session_start 已有 auto-start（T-08 产物）：未运行 → startMw + 3s 稳定窗确认 | 现场：停 mw → 新 pi 进程启动 → mw 自动拉起（PID 63568） |

## 7. worker 任务目录改挂 key 下（用户指令，2026-08-28 21:15）

| 项 | 实现 | 验证 |
|----|------|------|
| 布局 | worker 任务从 .agenticdoc 根级迁至 {key}/workers/<task-key>/；无 key 归属用 _scratch/workers/ 兜底 | 根目录只剩 3 个 key + _scratch |
| 扫描 | dispatchNewTasks 改扫 .agenticdoc/*/workers/*/task.md；根级 task.md 不再派发（消除 key 命名空间污染 + 旧 bundle 重复派发隐患） | 单测 3 例 + 现场：_scratch/workers/mw-dr-autodispatch 仅放 task.md，新 bundle pi 进程 agent_settled 自动派发 → done |
| 派发入口 | dispatch_worker 工具与 /worker 命令新增 key 参数，默认 active key → _scratch | tsgo/biome/vitest 全绿 |
| 播报路径 | 轮询循环改从队列行 taskPath 推导任务目录（旧代码按根级拼路径，keyed 布局下误报"无 output.md 摘要"） | 新 bundle 下修复；旧会话残留误报为预期 |
| 迁移 | 7 个根级 mw-dr-* 目录迁入 mw-dispatch-reliability/workers/，队列行 task_path 同步改写 | 队列 7 行全部指向新路径且终态保留 |
| 现场探针 | A: keyed 队列行 → done 4s；B: _scratch 纯 task.md 自动扫描 → done（13:13:22 派发→13:13:34 完成） | 两探针 output.md 均为 "ok" |

注：迁移期间旧 bundle 曾对根级 task.md 重复派发一轮（时间戳 13:00:50 重置）——恰是本变更要消除的行为；新布局下已不可能复发。
