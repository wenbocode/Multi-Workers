# Quality Gate Report — mw-crosskey-risk-escalation

- Key: `mw-crosskey-risk-escalation`
- 日期: 2026-09-24
- 门禁执行: PM（基于 T-3 独立验证的原始产物 + PM 自身复跑；独立验证角色由 T-3 worker 承担）
- 输入: `spec.md`（AC-001~004）、`design.md`（D-101~D-104、§7 VC-001~004）、`evidence/research/*-2026-09-23.md`、`evidence/verify-independent-2026-09-23.md`、两个 worker 的 `output.md`/`trace.log`

## 0. 证据充分性总览

- **总核查项**: 4 条 AC / 4 条 VC + 4 条交叉项（Q-X）= 12
- **充分（有可机械判定证据）**: 11
- **有条件通过（已记录去向）**: 1（Q-X-004）
- **未通过（无证据）**: 0

**门禁结论：✅ 通过**

## 1. AC → VC 逐条证据核查

| AC | VC | 判定 | 证据（原始输出） | 复核方式 |
|----|----|------|------------------|----------|
| AC-001 | VC-001 | ✅ 充分 | `[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0`（T-1 用例与 T-3 自建探针各自实测同一数值；T-3 断言文本含 `'t-xkey'（owner key=key-b）`、`risk=high`、`reads=`/`writes=`、`trace.log`、`progress.md`） | PM 复跑两文件 183/183；读 T-3 报告 §1 原始输出 |
| AC-002 | VC-002 | ✅ 充分 | `[VERIFY] VC-002: undefined_alerts=0 empty_set_alerts=0`；既有反例用例 `never wake this window` 在 T-3 中独立重跑通过；M-2 变异时该用例变红（证明它真在守卫） | 同上；PM 检查既有用例零改动（测试文件 159+/0-） |
| AC-003 | VC-003 | ✅ 充分 | `[VERIFY] VC-003: low_alerts=0 high_alerts=1 dup=0`（T-1 红阶段实测 `expected [] to have a length of 1`） | 同上 |
| AC-004 | VC-004 | ✅ 充分 | `[VERIFY] VC-004: watched_key_alerts=1 trigger_turn=true dup=0` + **机械字节证据** `head_alerts=1 current_alerts=1 text_byte_identical=true head_sha256=f2da612a…= current_sha256=f2da612a…`（用 `git show HEAD:` 取改造前模块，同夹具求值两侧 alert 均 533 bytes 全等） | PM 独立确认改造前/后文本模板：watched key 路径渲染为 `worker 'x' 检查点`，与原模板逐字一致（diff 显示仅 `workerLabel` 变量化） |

## 2. 变异反例（对抗性证据充分性）

| 变异 | 目标 | 红 | 复原 |
|------|------|----|------|
| M-1 | 过滤改回只看 `ownerKey`（去掉 `owned` 支） | VC-001 `alerts=0`（EXIT=1，4 项断言失败） | H1 == H0（`C261B903…ECCC3`） |
| M-2 | 去掉 owner + owned 过滤（全局广播） | VC-002 `1/1` + 既有反例用例 `expected 0 got 1` | H1 == H0，复绿（0/0 + 用例通过） |
| M-3 | `?? false` → `?? true` | VC-002 `undefined=1 empty=0`（仅未定义形态误投递，与设计边界一致） | H1 == H0，复绿 |

PM 独立复核：终态 `pm-orchestrator.ts` sha256 = `C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3`，与 T-3 记录的 H0 逐字节相同（变异确实已复原）。

## 3. 回归与影响面

| 命令 | 结果 | 判定 |
|------|------|------|
| `agent-team-loop.test.ts` + `agent-team-loop-watch-aggregate.test.ts` | **183 passed / 0 failed**（T-1、T-3、PM 三方各自复跑） | ✅ |
| `npm run check` | **EXIT=0**（biome 1092 files / pinned-deps / ts-imports / shrinkwrap / install-lock / tsgo --noEmit / browser-smoke） | ✅ |
| 测试文件改动面 | `159 insertions / 0 deletions`（纯追加 3 用例；既有 2 个 AC-004 用例零改动） | ✅ |
| 源码改动面 | `pm/pm-orchestrator.ts`：条件 + 文案两处（+19 行含注释）；`ui-bridge.ts` / `shared/**` / `dist/**` / Python diff 为空 | ✅ |
| `git status --short` 起止 | T-3 起止 10 行逐行相同；PM 终态仅本 key 改动 | ✅ |

## 4. 交叉检查（Q-X）

| 编号 | 问题 | 判定 | 说明 |
|------|------|------|------|
| Q-X-001 | 放宽过滤是否破坏"别窗口静默"？ | ✅ 充分 | AC-002 覆盖（未定义 / 空 Set 两形态）+ 既有反例用例独立重跑 + M-2 变异证明该用例真在守卫 |
| Q-X-002 | `!watch.key` 短路是否保留？ | ✅ 充分 | diff 逐字含 `if (!watch.key \|\| (ownerKey !== watch.key && !owned)) continue;`；T-3 探针在 `watch.key` 存在的前提下驱动，未发现历史记录触发的投递路径 |
| Q-X-003 | watched key 路径文本是否真的不变？ | ✅ 充分 | 机械字节比对（同夹具 sha256 全等，非"用例全绿"式推断） |
| Q-X-004 | 窗口重启后异地 worker 的升级面 | ⚠️ 有条件通过 | `dispatchedTaskKeys` 是进程内状态（GC-5），重启后本会话派发的异地高风险 worker 不再投递、只被动可见于面板聚合行（`mw-worker-visibility-gate`）。**去向**：spec §4 R-1 / 未决 Q-1（是否持久化另案评估），已在 achieved.md 遗留登记 |

## 5. 与 spec/design 的偏差登记（透明性）

1. **注释修正**：升级循环上方既有块注释末句 "(scoped to the watched key)" 在 D-101 后失真，改写为 "(scoped to the watched key ∪ this window's dispatched tasks — mw-crosskey-risk-escalation D-101)"；代码语义改动仍限于条件 + 文案两处。
2. **T-3 的 VC-004 实现方式**：T-3 用真实定时器 + 自建 fake pi 探针（任务书允许"fake timers 或自建 pi 桩"），而非 fake timers；驱动的是真实 `startWorkerPollLoop`。
3. 无其他偏差：未改判据、未新增导出/集合、未做全局广播、未改 Python/dist/框架仓库。

## 6. 结论

4/4 AC 与 VC 均具备可机械判定的证据，3 个变异反例双向成立（改坏即红 + sha256 逐字节复原），回归面无本 key 引入的失败。**质量门禁通过**，可进入 `done`。

遗留项：
- R-1 / Q-X-004（见 §4）：`dispatchedTaskKeys` 进程内语义 → 重启后异地升级面收窄为"面板可见"。接受不处理（spec 已登记，未决 Q-1 保留持久化议题）。
- R-2：更早会话派发（非本次进程）的异地高风险 worker 仍只被动可见（面板聚合行含 `risk=high:K`）。
- R-3（非本 key 引入）：`packages/multi-workers/autopilot/conductor.py` 有另一窗口的未提交改动，本 key 不触碰、不提交。
