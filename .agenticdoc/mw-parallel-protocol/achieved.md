# 达成报告: mw-parallel-protocol

> Key: mw-parallel-protocol
> 结案时间: 2026-09-22
> 状态: done

## 系统行为变化

PM 模式窗口（`PI_WORKER_TASK` 未设置）的每一次 agent run，系统提示尾部追加一段固定文本「[mw] 并行优先协议」：

- 拆解任何 phase 前先做并行性分析（可并行单元 / 共享资源与文件冲突面 / 必须串行的理由）；
- spec/design 的调研与证据收集默认批量并行：一个研究问题（RQ）一个 `type: research` worker、一个唯一 `evidence/research/<phase>-<rq-slug>-<date>.md`；两个 worker 不得写同一文件；
- 编码按文件/模块边界并行，同一文件同一时刻只允许一个 worker；
- 相位文档（spec.md / design.md）由 PM 串行写，不派 worker；
- 派发前先看 widget 上的 running worker 数，能并行不串行等待。

影响面（明确边界）：

- 只影响 PM 窗口的提示层，**不改任何门禁阈值**（evidence note 仍为 `>= 1`）、不改派发路由、不改 worker 行为；
- worker 窗口结构性不受影响（`index.ts` 按 `PI_WORKER_TASK` 分支，worker 走 `workerModeActivate`）；
- 静态文本、追加式、标记判重：系统提示前缀确定性（prompt cache 友好），不落 session、不累积 token；
- 生效前提：`mw build --install` 重建 bundle + 重启 pi 窗口（旧 bundle 窗口不受影响）。

代码面：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（`PARALLEL_PROTOCOL` / `PARALLEL_PROTOCOL_MARKER` + `pmActivate` 内一个 `before_agent_start` 处理器）；测试 `packages/coding-agent/test/extensions/agent-team-loop.test.ts`；changelog `packages/coding-agent/CHANGELOG.md`。

## 遗留

1. **L2 端到端验证（已关闭）**：2026-09-23 14:49 用全新进程 `pi -p "...第 4 条是什么？"`（PM 模式，加载新 bundle+dist）验证，模型原样复述出「相位文档（spec.md / design.md）由 PM 自己串行写，不派 worker」——证明协议确实进了系统提示。原欠债记录见 `evidence/quality-gate-report-2026-09-22T2152.md`（已同步更新为充分）。
2. **协议文本的框架侧落点未做**：`core/pm-mind.md` Phase 1 的「按依赖顺序排列 stage，不可并行的串行」与 `core/workflows/requirements.md` Step 3.6 / `system-design.md` step 5（当前写法是 PM 自己产出 research note，未提批量派发）仍是并行的反面。去向：立新 key（跨仓库 AgenticTask，需 push/install），本 key 不含。
3. **无动态内容与开关**：不做"空闲并行槽位数"提示、不做注入开关。去向：有真实需求时立新 key。
4. **项目侧零配置**：未改 `AGENTS.md` / `.pi/APPEND_SYSTEM.md`。去向：若希望非 mw 项目或纯文档层面也生效，自行追加一句（不需要 key）。
