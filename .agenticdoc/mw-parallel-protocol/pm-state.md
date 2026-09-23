# PM State: mw-parallel-protocol

## 1. Snapshot
- Key: mw-parallel-protocol
- Phase: DONE
- Next Action: 收尾（achieved.md + quality-gate 报告 → done）
- Started: 2026-09-22 21:44
- Updated: 2026-09-22 21:44
- Completed: 2026-09-22 21:44

## 2. Task Status
- T-01 PM 窗口常驻「并行优先协议」注入: done（pm-orchestrator 常量 + before_agent_start 注册；worker 模式不受影响）

## 3. Evidence Ledger
- 2026-09-22 21:42 **PASS** 目标测试（`test/extensions/agent-team-loop.test.ts -t "parallel protocol"`）：2 passed（PM 注入幂等 + worker 不注入）。
- 2026-09-22 21:43 **PASS** 全文件回归：`test/extensions/agent-team-loop.test.ts` 170 passed / 0 failed（基线无新增失败）。
- 2026-09-22 21:45 **PASS** `npm run check` exit 0：biome 1080 files no fixes、pinned-deps、ts-imports、shrinkwrap up to date、install-lock up to date、tsgo --noEmit 无输出（0 error / 0 warning / 0 info）。
- 2026-09-22 21:44 **PASS** key 建立与 claim：写 spec.md 触发自动接管，`_index.parallel` 行为 active/SPEC，claimId 为本窗口 host:pid；随后 `advance_phase` init→execute 同步两处 phase（无 divergence 警告）。
- 2026-09-22 21:50 **PASS** 事实核验（写入 spec 前的代码事实）：`types.ts:1097-1101`（BeforeAgentStartResult）、`index.ts` PM/worker 分支、`worker-mode.ts:48-58`（research/review 只读白名单）、`phase-docs.ts:44`（证据按前缀计数、gate 仅 >= 1）。
- 2026-09-22 21:50 **欠债** → 2026-09-23 14:49 **PASS**（已关闭）L2 端到端：`mw build --install` 重建 bundle + pi dist（两处 grep `rq-slug` 命中），全新进程 `pi -p "只回答一行：你系统提示里 [mw] 并行优先协议 的第 4 条是什么？"` 原样复述出「相位文档（spec.md / design.md）由 PM 自己串行写，不派 worker」。证据：全局 bundle 902459B、pi dist 内建副本 2026-09-23 14:45 重建。

## 4. Hypothesis Queue
- H-1（已证）: 幂等判重成立——把上一轮返回的 `systemPrompt` 回喂处理器返回 `undefined`（用例 1 对应 AC-003）。
- H-2（已证）: 注入文本不改动门禁语义——实施准入门禁测试未受影响，全文件回归 170 passed。
- H-3（未证，非阻塞）: 真实链路里 `before_agent_start` 每 agent run 恰好触发一次（含 worker 终态唤醒的续跑轮）——由 pi runner 契约保证（`extensions.md` 与 `extensions-runner.test.ts:717`），本 key 未新增针对该契约的断言。

## 5. Decisions
- 2026-09-22 选 `before_agent_start` + 追加静态 `systemPrompt`，而非注入持久 `message`：后者每 run 往 session 累积 token；前者每 run 一次、不落盘、确定性文本不破 prompt cache。
- 2026-09-22 保留标记判重（`PARALLEL_PROTOCOL_MARKER`）：双包同进程加载时避免每 run 重复追加（对应 `index.ts` 的 ACTIVATION_FLAG 同族防御）。
- 2026-09-22 协议同时写入调研与编码两类冲突面规则（research/review 只读 → 默认全并行、一 RQ 一文件；coding → 同文件互斥）：混成一句会两端都错。
- 2026-09-22 范围内明确排除 `AGENTS.md` / `.pi/APPEND_SYSTEM.md` / `core/pm-mind.md`：项目侧与框架侧文档另计，保持本 key 单一交付。

## 6. Turn End Records
| # | 问题 | 回答 |
|---|------|------|
| 1 | 顶层目标 | PM 窗口默认从并行度出发拆解（spec/design 调研 + plan/tasks + 编码派发） |
| 2 | 新增证据 | 2 单测 + 170 回归 + `npm run check` exit 0 |
| 3 | 假设变化 | H-1/H-2 证实；H-3 标注未证非阻塞 |
| 4 | 需重开的 done 任务 | 无 |
| 5 | 阻塞点 | 无；L2 已用 `pi -p` 新进程验证通过 |
| 6 | 需新增/拆分 Task | 无；后续若要动态内容/开关另立 key |
| 7 | 下一动作 | achieved.md + quality-gate 报告 → advance done |
| 8 | 是否已写入 pm-state.md | 是 |
| 9 | 可提炼 pattern | 无（单点注入，未形成通用模式） |

## 7. Process Log
- 2026-09-22 21:40 建 key（spec.md 写入触发自动接管）→ 先落代码（pm-orchestrator）→ 补测试 → 跑 check → 补零调研声明与 tasks → `advance_phase execute`。
- 2026-09-22 21:44 实施严格晚于 key 建立（spec.md 先于首行代码），符合实施准入门禁。
