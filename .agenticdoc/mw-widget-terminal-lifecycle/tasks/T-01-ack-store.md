# Task T-01: AckStore（ack sidecar 读写）

## 基本信息
- Stage: 1
- 代码状态: 已完成（代码+测试就绪，见执行记录）
- 验证状态: 验证通过（VC-004 存储半：agent-team-loop-ack.test.ts 5/5 + 埋点；T-09 全量回归复验 121/121）
- 负责 Agent: 待定
- ac_refs: [AC-004]
- vc_refs: [VC-004]
- pattern_refs: []

## 描述
新文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts`。

**AckStore**（D-001 纯存储，状态校验在通道层 T-07）：
- 构造：`new AckStore(agenticdocRoot: string)`；文件 = `<root>/_workers.acked`，锁 = `<root>/../.mw/workers.lock`（与 WorkerStore 同锁）
- `readAll(): Map<string, string>`——taskKey → ackedAt（ISO）；文件缺失/坏行跳过返回已解析部分；`#` 开头行忽略
- `ack(taskKeys: string[]): Promise<{ acked: string[]; rejected: string[] }>`——持锁读-合-写（tmp + rename 原子替换，模式照抄 WorkerStore.upsert）；幂等（重复 ack 覆盖时间戳）；`acked` 为实际写入 keys，`rejected` 为空集校验（非法 taskKey：空串/含 `|`）
- 行格式：`taskKey | ackedAtIso`（与队列文件同族管道格式）

**测试**（新文件 `packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts`，独立 describe，不碰 agent-team-loop.test.ts）：
- 写读往返：ack 2 keys → readAll 返回 2 条且值为合法 ISO
- 幂等：重复 ack 同 key → 条数不变、时间戳更新
- 持久化：新 AckStore 实例（同 root）读出相同 keys（VC-004 persisted 半）
- 坏行容忍：手写坏行/注释行 → readAll 跳过
- 空/非法 key 拒绝：rejected 收录且文件无记录
- 输出 `[VERIFY] VC-004: acked=<k>, persisted=yes` 埋点行

## 输入
- 依赖文件: `shared/worker-store.ts`（upsert 原子写模式参照）、`shared/file-lock.ts`（acquireLock）
- 依赖 Task: 无
- AC 约束:
  > AC-004: 执行 `/mw ack <task-key>` 后，`.agenticdoc/_workers.acked` 中存在该 task_key 的 ack 记录（含 ISO 时间戳，workers lock 保护写入），重启 pi 后 widget 分区仍按 ack 状态渲染；`/mw ack all` 覆盖当前全部未 ack 终态行；对 running/pending 行 ack 返回错误提示且不写记录（本 Task 只做存储半：写入/持久化/幂等；通道与状态校验在 T-07）
- 设计约束:
  > D-001: sidecar `.agenticdoc/_workers.acked`，workers lock + tmp/rename，项目级多窗口共享
  > GC-4: 不改 `_workers.parallel` 行/列格式

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts`
- `packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts`
- 验证方式: `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-ack.test.ts`（从 packages/coding-agent 起）全绿 + 埋点行
- 验证等级: Level 1

## 约束（worker 派发适用）
- 只碰上述两个新文件；禁改 agent-team-loop.test.ts / ui-bridge.ts / worker-store.ts
- 显式路径参数；禁 import 未完成模块
- 完成后更新本文件执行记录（验证状态留 PM 验收）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T07:24:35Z | 新建 shared/ack-store.ts（AckStore：readAll/ack，workers lock + tmp/rename 原子写，UTC ISO 时间戳）+ test/extensions/agent-team-loop-ack.test.ts（5 用例：往返/幂等/持久化/坏行容忍/非法 key 拒绝） | 测试 5/5 绿，输出 `[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes`；biome/tsgo 对两新文件无告警（tsgo 仅报 packages/ai 既有错误，与本案无关）；未改 worker-store.ts / ui-bridge.ts / agent-team-loop.test.ts；未 commit |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
