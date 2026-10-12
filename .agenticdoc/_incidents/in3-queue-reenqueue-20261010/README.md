# IN-3 事故档案：队列整表重建导致全项目 250+ 任务重派

- **事故 ID**：IN-3（本项目第 3 起；IN-1/IN-2 见 `.agenticdoc/mw-workspace-incident-probe/`）
- **建档**：2026-10-10 11:50（本地 UTC+8）　**建档人**：`mw-gate-verdict-hardening` 窗口（PM 直执，只读审计）
- **目录性质**：**跨 key 事故档案**。用途＝后续一旦再出现类似症状，先来这里对照指纹与判据拿线索，不必重新取证
- **归因负责人**：`mw-gate-verdict-hardening`（该 key 的 G5 即本事故的修复项）

---

## 1. 30 秒版根因

`.agenticdoc/_workers.parallel` 被**整表重建**（252 行、全部非终态、同一秒内），launcher 据"有 252 个 pending"**全量重派**，峰值 66 个 node worker 并发。

机制：派发判据是"队列里**有没有**该 task_key 的行"，**不是**"任务是否已终态"；而队列行格局在 `b8bc115ff`（10-09 16:27）从 **8 列漂移到 9 列**（新增 `origin`），**长驻 pi 窗口内存里仍跑 7~8 列解析器**（安装副本 `~/.pi/agent/extensions/agent-team-loop.js` 直到 10-10 10:53:02 才刷新）⇒ 9 列行被**静默丢弃**（`worker-store.ts:81` `return undefined`）⇒ `upsert` 回写时**永久删除**这些行 ⇒ `readAll()` 归零 ⇒ 全部任务被当成"从未派发"重新入列。

⇒ 一句话：**读侧的静默降级 + 写侧的无条件回写，把"解析不了"变成了"删掉重派"。**

---

## 2. 代码判据（复发时按这些位置核对）

| 位置 | 作用 | 事故中的角色 |
|---|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:402` | `const dispatched = new Set(workerStore.readAll().map(e => e.taskKey))` | 派发判据的输入＝**行是否可读** |
| `…/pm-orchestrator.ts:428` | `if (dispatched.has(taskKey)) continue;` | 判据命中即跳过；行丢了 ⇒ 不跳过 ⇒ 重派 |
| `…/pm-orchestrator.ts:435` | `isConductorTask` 跳过 | 为什么 252 行里 **0 个 `ap-*`** |
| `…/pm-orchestrator.ts:737-744` | `pi.on("agent_settled", …)` 触发扫描 | 触发时机：任何 agent 收尾（含 PM 自己） |
| `…/shared/worker-store.ts:81-104` | `parseWorkerLine`：事故前 `parts.length !== 8 && !== 7 ⇒ return undefined` | **静默丢行**的唯一入口 |
| `…/shared/worker-store.ts:123-140` | `upsert` 读全表 → 改一行 → 整文件 tmp+rename 回写 | 丢行被**固化**（把丢弃当成删除） |
| `packages/multi-workers/launcher.py:822` | 只 spawn `status == "pending"` 的行 | 252 行全 pending ⇒ 全 spawn |
| `packages/multi-workers/launcher.py:837/847` | `if max_workers and …`；默认 `max_workers=None` | **无上限**（峰值 66 并发） |
| `packages/multi-workers/launcher.py:555-621` | `_reconcile_orphans` 只把 `running` 收敛到终态，**从不写 pending** | 已排除为成因 |
| `packages/multi-workers/mw_common.py:1567-1615` | Python 侧 parse 容忍 7/8/9；`serialize_entry` 仅在 `origin` 真值时追加 | Python 侧不会丢行（丢行只在 TS 侧） |

---

## 3. 时间线（实测锚点）

| 时刻（本地） | 事件 |
|---|---|
| 10-09 16:27:22 | `b8bc115ff` 引入 `origin`（7..9 列容忍）；16:27:30 `27e3c927e` 重建 dist（中间态 dist 仍是 8 列） |
| **10-09 20:01:47** | **第 1 次整表重建**：随后本 key 7 个已 acked 调研任务被重跑，证据被覆写（pm-state D-008） |
| 10-09 20:07:43 | 重跑出来的 `mvr-t16-quality-gate-review` 启动（兄弟 key IN-1 的元凶进程） |
| 10-09 20:32:18 | 该重跑 worker 执行 `git worktree remove --force` ⇒ 穿透 junction ⇒ 3,448 个 tracked 文件消失（IN-1/IN-2） |
| 10-10 10:50:02 | 本 key 写 T-07 任务卡（时间相关，非因果） |
| **10-10 10:50:05.220–.637Z / 本地 10:50:05** | **第 2 次整表重建**：252 行、28 个 owner key、单秒内、行序＝纯字母扫描序、全部 8 域、0 个 `ap-*` |
| 10-10 10:50–11:07 | launcher 全量 spawn（峰值 66 并发）；`.mw/launcher.log` 出现 `[WinError 5] '_workers.parallel.tmp' -> '_workers.parallel'` |
| 10-10 10:53:02 | 安装副本 `~/.pi/agent/extensions/agent-team-loop.js` 刷新（此后新启动的窗口才拿到 7..9 列解析器） |
| 10-10 11:07:28 | 用户授权"轻刹"：kill launcher（PID 96968）⇒ **11:07:31 `mw serve` 级联退出**（轻刹 ≈ 停服务，意外副作用） |
| 10-10 11:07–11:10 | 手工 kill 6 个仍在跑的重跑 worker；RQ-5（本 key）被连带 kill，报 `failed (0s)` |
| 10-10 11:20:32 | 他方重启服务（serve 37452 / launcher 132268）；当时队列 0 pending ⇒ 未再爆发 |
| 10-10 11:26 | 队列 252 行 = 243 done / 8 failed / 1 running / **0 pending**；2 行由新 key 正常派发 |
| 10-10 11:45 | 残留排查：**3 个重跑 worker 仍存活并在写仓库**（见 `04-residue-scan-20261010.md`） |

---

## 4. 复发条件（满足任一条即可能再发）

1. **队列行格局再次变化**（加列/改列序），而**任何长驻 pi 窗口**仍跑旧解析器 ⇒ 丢行 ⇒ 重派。当前安装副本已是 7..9，但**行格局仍是硬编码容差**，不是版本化契约。
2. **任一行不可解析**（不只是列数：分隔符、编码、空行、半写行）⇒ 静默丢行。
3. **`.agenticdoc/_workers.parallel` 被外部清空/截断/替换**（如 `.tmp` 脚本直写、非原子覆盖、Windows `os.replace` 争用）⇒ `readAll()` 归零 ⇒ 全量重派。
4. **`max_workers` 未设置**（默认 None）⇒ 一旦重派无上限。
5. 任何一次 `agent_settled` 都可能触发扫描 ⇒ 触发面 = 全部活跃窗口。

---

## 5. 复发识别指纹（拿来对照，一眼判定是不是 IN-3 复发）

- [ ] `_workers.parallel` 行数突然接近"历史任务总数"（本次 252），且**几乎全部非终态**
- [ ] 这些行的 `dispatched_at` 落在**同一秒**内（本次 `…02:50:05.220–.637Z`）
- [ ] 行序 = 按 owner key 的**纯字母序**、owner 之间**零交错**（＝一次扫描顺序 append，非多次独立写入）
- [ ] 所有新行**列数一致且偏少**（本次全部 8 域；当前写入器应为 9 域带 `origin`）
- [ ] **0 个 `ap-*` 行**（conductor 过滤仍在生效 ⇒ 问题在"已终态任务"而非"conductor 任务"）
- [ ] 同时段 `node … --provider timi --model … -p "Read your task file at …"` 进程数**暴涨**（本次峰值 66）
- [ ] `.mw/launcher.log` 出现 `[WinError 5] '_workers.parallel.tmp' -> '_workers.parallel'`
- [ ] `.agenticdoc/*/workers/*/trace.log` 出现"同一任务二次开工"（`trace.log` 被截断/重写，或 `output.md` 被新内容覆盖）
- [ ] 长驻窗口的 bundle mtime **早于** `packages/multi-workers/dist/extensions/agent-team-loop.js` 的 mtime（⇒ 该窗口跑旧解析器）

---

## 6. 影响面摘要（详见 `02-impact-assessment.md`）

- `.agenticdoc` 产品面：窗口内被写 **504 份产品文件**；当前 **82 份 tracked 改动（L1 18 / L2 ≈37 / L3 13）**；**无截断**；结论＝**中高但可恢复**（受影响文档绝大多数在 git 里；新 key 目录 untracked ⇒ 无 git 备份）
- `packages/` 源码面：窗口内 1,308 文件 mtime 变化，但仅 **12 份内容 diff**（且都很小）；**无证据**表明历史改动被重放，但**无法排除**
- 台账面：`_workers.acked` 261 行 / `_index.parallel` +5−2
- **下游因果**：IN-3 是兄弟事故 IN-1/IN-2 的**上游**（第 1 次重建重派了 `mvr-t16`，它随后删掉了 3,448 个文件）

---

## 7. 与修复项的对应

| 事故成因 | 修复项（key `mw-gate-verdict-hardening`） |
|---|---|
| 判据不看终态 | G5 + AC-022（产物自带终态优先，done 永不重派） |
| 行缺失即全量重派 | AC-020（fail-closed）+ AC-023（丢行计数/告警/不回删 + 版本头） |
| 单次派发副作用面 = 全项目 | AC-019（PM 侧自动派发收窄到本 key + `_scratch`；**`mw` 指令仍全局扫描**） |
| 无派发配额 | AC-021（单轮配额 N，超限拒绝 + 告警） |
| 无上限 spawn | G5 附项：launcher 默认 `max_workers` 必须有限 |
| 事故发生时无人察觉 | G2/G4 观测项 + `mw doctor` 队列规模突变检查 |
| 隔离要求（用户） | G6：本 key 执行不得影响历史 worker |

---

## 8. 本档案文件清单

| 文件 | 内容 |
|---|---|
| `01-rootcause-and-attribution.md` | 完整复盘（11 节：机制、codec 漂移、F1–F8 放大因子、与 IN-1/IN-2 的因果、影响实测、复发条件、分层建议 A/B/C/D、未坐实 7 条、可复现命令） |
| `02-impact-assessment.md` | 影响评估（面 A `.agenticdoc` / 面 B `packages` / 面 C 台账；结论与处置建议） |
| `03-products-to-review.md` | 受损产品清单（L1 18 / L2 / L3，含路径 + 窗口内 mtime + diffstat） |
| `04-residue-scan-20261010.md` | 残留排查（存活进程、孤儿 worker、其正在写入的共享产物） |
| `05-sol-collateral-trace-20261010.md` | 派生调用实证（2026-10-11 建档）：10-10 的 **12 次 `gpt-5.6-sol` 调用 100% 由第 2 次整表重建产生**（队列快照 + `_workers.acked` 终态 + 逐任务三波重派时间线 + 与 sol 流中断缺陷的边界划分） |
| `scripts/in3-impact-audit.py` | 只读：窗口内 `.agenticdoc` 改动分类 |
| `scripts/in3-source-attrib.py` | 只读：源码写入归因尝试 |

## 9. 未坐实项（复发取证时先看这里，别重复劳动）

1. 究竟是**哪个进程**执行了那次"9 列整表重写"（候选：长驻窗口的 upsert；无法从文件本身定位 PID）。
2. **02:50:05 的触发窗口**：只有时间相关性（他 key 写 spec 10:50:01、本 key 写任务卡 10:50:02），无因果证据。
3. 第 1 次（20:01:47）事件的**文件形态已不可得**（被第 2 次覆盖）。
4. 11:16–11:21 期间 `packages/**` 的 20+ 处写入的**归属**（20+ 活跃 key 并发编码，trace.log 提到文件名 ≠ 写入）。
5. 更早的 bundle 是否只接受 7 列（未取证）。
6. 队列文件当时是否**短暂不存在**（Windows tmp+replace 使 CreationTime 无参考价值）。
7. 仓库内 `.pi/agent/sessions` 不存在（会话在 `~/.pi/agent/sessions`）⇒ 会话级取证需换路径。
8. **第 0 波（10-09 15:08）全项目重派的触发者**：12 个 sol 钉死任务的 `trace.log` 均显示该时刻另有一波开工（早于 `b8bc115ff` 列漂移 16:27），本档案只记录了 20:01:47 与 10:50:05 两次；见 `05-sol-collateral-trace-20261010.md` §3.1/§6。
9. **`exit=0` 却记 `failed` 的写入方**（10-10 共 4/12 例）：队列 `updated_at` 为批量扫描值，无法据此定位；见 `05-sol-collateral-trace-20261010.md` §4/§6。
