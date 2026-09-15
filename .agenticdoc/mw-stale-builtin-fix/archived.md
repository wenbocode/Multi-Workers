# Archived: mw-stale-builtin-fix

> status: archived（补记 key）
> 日期：2026-09-09
> 背景：本工作未在独立 AgenticTask key 下执行（发生在 mw-dispatch-flow-fixes 的 VERIFY 烟测排障过程中），应用户要求补 key 留档。无 spec/design/plan，纯修复记录。

## 问题

mw-dispatch-flow-fixes 的 AC-016 烟测（smoke-ac015-ac016）中，src/bundle 侧修复后 worker.log 仍拿不到 pi 最终回复（只有 `[worker]` 状态行），且裸 `pi -p` 实测挂死（180s+ 需强杀）。

## 根因

- 本 fork 将 agent-team-loop 注册为 built-in 扩展（`packages/coding-agent/src/extensions/index.ts`，初始提交 8806e2be），编译进 `packages/coding-agent/dist/`；npm 全局 `pi.cmd` 指向本仓 dist/cli.js。
- dist 最后构建于 **2026-08-14**：旧副本无 ACTIVATION_FLAG 双载防护（防护为 9 月新增）→ 与全局 bundle（`~/.pi/agent/extensions/agent-team-loop.js`，当日新构建）**双激活**。
- 旧副本在 agent_settled 内 `process.exit(0)`（preload `--require` 钩子抓栈定位：`dist/extensions/agent-team-loop/worker/worker-mode.js:125 exitWithSuccess`），抢在 print-mode 写最终回复前杀进程 → worker.log 空；其 PM poll 循环无 session_shutdown 清理 → 裸 `pi -p` 挂死。

## 决策与执行

- 方案 A/B 对比后用户确认 **A：保留 built-in + 重建 dist**。依据加载顺序（resource-loader.ts L563-575：文件扩展先、inline built-in 后），全局 bundle 先激活设 flag，重建后的 built-in 让位为惰性后备（仅全局 bundle 缺失时接管，对 worker spawn 是协议正确的降级）；日常扩展迭代仍只需 `mw build --install`。
- 执行：`npm --prefix packages/coding-agent run build`（2026-09-09 14:43，dist 全量重建，新代码含 finishSuccess/无 exitWithSuccess + 防护）。

## 验证

- smoke-ac016b（task.md → PM 扫描派发 → 项目级队列 → Python spawn → done 全链路）：**worker.log 三段俱全**（`[worker] start` / `[worker] done exit=0 elapsed=12s tools=0` / 最终回复 `SMOKE-OK-AC016B`）—— AC-016 实机通过。
- 裸 `pi -p "Say exactly: ok"`：输出 ok 后 **4.1s 自然退出**（原挂死）。
- 详细证据：`mw-dispatch-flow-fixes/evidence/runs/smoke-ac015-ac016-2026-09-09.md`（含 preload 抓栈、A/B 决策记录、修复后复验）。

## 附带发现（移交后续）

1. 运行中的 mw serve（PID 62804，8-28 启动）携带 **9-5 之前的旧 launcher**：任务体仍整体经 argv 传给 `-p`（worker 会话文件证实 user message = task.md 全文，故 0 工具调用即答）。这是 9-5 "task body never travels through argv"（commit 3d15874c2）修复前的行为，存在 Windows cmd `%*` 重分词执行 shell 片段的隐患。建议择机 `mw stop && mw start`；注意 mw.py/mw_common.py 当时有另一会话未提交改动，重启时机需协调。
2. agent-team-loop 扩展只读写项目级 `.agenticdoc/_workers.parallel`（WorkerStore 恒以项目根构造）；key 级 `_workers.parallel` 无任何读取方。烟测脚本曾误写，已持锁清空。

## 涉及文件

- 无 src 改动（本 key 范围内）；代码修复本体在 mw-dispatch-flow-fixes key（AC-015/016）。
- 变更产物：`packages/coding-agent/dist/**`（gitignored 构建产物，重建）。


---

# 恢复复验（2026-09-09 晚）

**背景**：worktree junction 删除事故将 `packages/coding-agent/dist/**`（本 key 唯一交付物）连同全仓各包 dist 一并删除，npm 全局 `pi` 命令（junction 指向本仓 dist/cli.js）失效。

## 重建与验证（全部复现）

- 全仓 7 包依序重建（tui→ai→agent→sqlite-node→protocol→client→server→coding-agent）；ai 包存在 1 个 HEAD 既有 TS2353（cloudflare-ai-gateway 引用 openai-completions，committed models.generated.ts 无此键——models 工作流未完成态），tsgo 照常 emit，providers/data 40 文件补拷
- `exitWithSuccess` 0 处 / `finishSuccess` 3 处 / ACTIVATION_FLAG 双载防护在 dist index.js（原验证点逐项复现）
- watchdog（CHECKPOINT ×28）与 pm-state 守卫（INTERFACE_LINE ×4）在重建的 built-in dist 内
- 裸 `pi -p "Say exactly: ok"`：exit=0、5s 自然退出、输出 ok（对照原验证 4.1s，挂死修复成立）
- `pi --version`：0.83.0（npm 全局 junction 链路恢复）

## 结论

交付物已恢复且验证点全部复现；本 key 维持 archived。mw serve 旧 launcher 重启建议转记 mw-dispatch-flow-fixes/achieved.md 遗留项。
