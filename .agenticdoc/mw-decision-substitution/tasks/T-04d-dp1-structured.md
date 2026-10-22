# T-04d dp1 结构化 state 上线 + dp2 acted trace

- key: mw-decision-substitution · type: coding
- 依据：T-04c 残留 1（dp2 缺 PM 侧 trace）+ 残留 2（生产 dp1 仍走 legacy，关联链在生产链路不可达）

## 上下文

T-04c 把字段链路打通了，但它自己发现并报了关键一条：

> 生产 dp1 仍走 legacy 字符串 state → `mw.py:927-939` 走 `questions` 分支 → 响应无 `decision_id/mode/acted` → `decision:` 头行在生产链路**永不可达**。测试里能过，是因为测试注入了结构化形状的响应。

即：**AC-007（决策→结果关联）目前只在单测里成立**。这是本 key 的核心价值之一，必须在上线前闭合。

## 要求

1. **dp1 结构化 state**（`pm/ui-bridge.ts:computeDispatchTriage`）：
   - 从派发计划构造 dp1 的结构化 state：`v: 1`、`dp: "dp1-dispatch-type"`、`key`、`phase`、`task_type`、`risk`、`risk_source`、`authority_tier`、`requested_type`、`task_summary`、`scope.write_scope`、`scope.ext`（注册表 `REQUIRED_STATE_FIELDS["dp1-dispatch-type"]` 全量，见 `decision_points.py`）；
   - **构造不出完整必填集时回退 legacy 字符串**（保持 T-04 的冻结字节路径，逐字节不变）。回退必须写 trace `[DECISION] dp1 state=legacy reason=<missing|oversize>`，不许静默；
   - 结构化路径的 state 必须 ≤2000B（复用 `prepareStructuredState`），超限按 T-04 的两段式截断，截断后仍超 → 回退 legacy（而不是拒发，因为 legacy 有 16KB 预算）。
2. **dp2 acted trace**（`pm/pm-orchestrator.ts`，narrow 分支约 `:2557-2585`）：narrow 真正执行（写完 steer、跳过告警）后追加一行
   `[DECISION] dp2 acted=1 decision_id=<id> trigger=<task>#ckpt<N>`；未执行（回退告警 / suggest / disabled）不得写该行。
3. 测试：
   - `decision-association.test.ts`：dp1 结构化路径下，用**真实形状**的 CLI 响应（含 4 个新键）走 `computeDispatchTriage → writeDispatchTaskMd`，断言 `decision:` 行写出；必填缺失时回退 legacy 且 task.md 与基线逐字节相同 + trace 有 `state=legacy`；
   - `dp2-narrow.test.ts`：narrow 执行 → trace 含 `dp2 acted=1`；回退告警 → 不含。
4. 不改 `spec.md:162` 的 legacy 兼容条款本身（legacy 仍保留），只改"何时用哪条路径"。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
- `packages/coding-agent/test/suite/decision-association.test.ts`
- `packages/coding-agent/test/suite/dp2-narrow.test.ts`

## 写入禁止面

- 其它任何文件（含 `worker-mode.ts`、`index.ts`、Python 侧、skill 脚本、其它 key 目录）
- 禁止 `git add/commit/checkout/stash/clean`；禁止 `npm run build`、`npm run check`

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/decision-association.test.ts test/suite/dp2-narrow.test.ts \
  test/suite/triage-client-state.test.ts test/suite/triage-dispatch.test.ts
```

期望：全绿（30 + 30 + 31 + 21 + 新增）。

## 种子

- goal 锚点：`.agenticdoc/goal.md`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:236`（`computeDispatchTriage`，legacy 字符串产地）
- `packages/multi-workers/mw.py:927`（CLI 的 legacy / 结构化分支分叉点）
- `packages/multi-workers/decision_points.py` `REQUIRED_STATE_FIELDS["dp1-dispatch-type"]`（必填集权威）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:2557`（dp2 narrow 执行点）

## 交付格式

- 四段：结论 / 证据（四套件尾行 + 生产路径对照：结构化时 `decision:` 写出、回退时 task.md 与基线 sha 相同）/ 残留与未验证 / 改动清单。
- 必须给出「生产路径真的走了结构化」的证据（trace 行或 runner 收到的 argv/payload 形状），不接受只有单测注入。
- 契约冲突停手写残留。

## 改动历史

- 2026-10-20 创建（T-04c 残留 1+2）
