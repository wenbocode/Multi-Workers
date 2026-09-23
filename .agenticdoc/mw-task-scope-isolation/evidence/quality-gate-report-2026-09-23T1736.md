# Quality Gate Report: mw-task-scope-isolation

**时间**: 2026-09-23T17:36+08:00
**触发**: T-01..T-03 完成（PM 直执）
**范围**: 全量（单 key，3 个 Task）

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | `list_tasks` 默认只列本窗口 + owner 前缀 | 充分 | 新用例「AC-001..AC-004」：`key-a :: t-mine \| running \| pi` 命中、`t-theirs` 不出现 | L1 |
| Q-AC-002 | `scope:"all"` 保持全项目视图 | 充分 | 同用例：两 owner 行同时命中 | L1 |
| Q-AC-003 | `scope:"key"` 过滤；缺参/未知 scope 报文本错误 | 充分 | 同用例：`key-b` 单列、`scope "key" requires key`、`Unknown scope` | L1 |
| Q-AC-004 | 无 claim 且无派发 → 指引文案，不列他人任务 | 充分 | 同用例：`No tasks found for this window` + `switch_key` + `scope: "all"`，且两组行均不出现 | L1 |
| Q-AC-005 | `all` 只 ack 本窗口（侧车不误清） | 充分 | 新用例「AC-005/AC-006」：`Acked 1 task(s): a-done`，`b-failed` 未写入 | L1 |
| Q-AC-006 | 显式指名他人行 → 拒绝 + 指引 + 不写盘 | 充分 | 同用例：`NOT acked: b-failed` + `owned by key 'key-b'` + `/pm-key switch key-b`，侧车无新增 | L1 |
| Q-AC-007 | 显式跨 key 派发仍属本窗口 | 充分 | 新用例「AC-007」：`dispatch_worker(key:"key-b")` 后 `mine` 含 `key-b :: x-task \| pending` | L1 |
| Q-AC-008 | 回归无新增失败 | 充分 | `agent-team-loop.test.ts` 173 passed / 0 failed（基线 170 + 3） | L1；4 处既有断言按有意变更适配（VC-004/005/011 + `/mw` 路由用例） |
| Q-CHK-001 | 静态检查零 error/warning/info | 充分 | `npm run check` exit 0：biome 1087 files no fixes、tsgo `--noEmit` 无输出、shrinkwrap/install-lock up to date、browser-smoke 通过 | L0 |
| Q-DES-001 | 归属判定与 widget 同口径（不出现工具/面板不一致） | 充分 | 复用 `ownerKeyOf`（widget 同函数）；`mine` 是它的超集（多派生发记账） | 代码审阅 |
| Q-SCOPE-001 | 未越界（无 Python / 文件格式 / 路由改动） | 充分 | `git status` 仅扩展 TS + 测试 + CHANGELOG + 本 key 状态文件 | 代码审阅 |
| Q-VC-L2 | 真实窗口目视（新 bundle 下的 `list_tasks`/ack 行为） | 充分（17:19/17:20 补充） | `pi -p` 默认 scope → 隔离指引文案，未泄露任何其它 key 任务；`pi -p` `scope:"all"` → `mw-dispatch-reliability :: mw-dr-glm53 \| done \| pi \| acked` | L2；bundle 17:18 重建，grep 确认新旧两处加载点均含新代码 |
| Q-CONC | 双窗口同时 ack 的真实并发 | 不足 | — | 未实测；沿用既有 `.mw/workers.lock`，收窄不引入新竞争面（记欠债 1 项） |

## 汇总

- **总问题数**: 12
- **通过（充分）**: 11（92%）
- **有条件通过（不足）**: 1（验证欠债 1 项：Q-CONC；Q-VC-L2 已于 17:19/17:20 补足）
- **未通过（无证据）**: 0

**质检结论**: 有条件通过（欠债 1 项，属并发实测类，已记入 achieved.md 遗留，用户知情）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|------|------|---------|---------|
| Q-VC-L2 | ~~无头环境 + bundle 未重建~~ 已闭环 | 17:18 `mw build --install`（exit 0）+ 17:19/17:20 两次 `pi -p` 实机验证 | 无需后续动作 |
| Q-CONC | 需两个真实窗口 + 时序编排 | 双窗口各自 ack 同一批，确认侧车/待处理清单互不影响 | 有意留待后续 key（如需） |

## 二次印证结论

无遗漏。二次核查确认三点：(1) 拒绝路径确实在 `ackStore.ack()` 之前返回（仅 `acked` 数组进写入）；(2) 未传 scope 时 `ackTasks` 保持旧行为，既有单测无需改动；(3) `dispatchedTaskKeys` 可选，`PmWatchState` 的字面量构造点全部无需修改。
