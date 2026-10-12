# T-15: G5-A 读侧不得静默丢行（队列完整性）

- 波次: **3** · 依赖: 无（本卡是 G5/G6 的起点）
- 写面（独占）: `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts`
- 只读参考（不得改）: `packages/multi-workers/mw_common.py`（`:1567-1596` 解析 / `:1599-1615` 序列化 / `:1704-1710` 原子写）
- AC: **AC-023** · VC: **VC-024 / VC-025 / VC-026**
- 基线: `10446aefb`

## 问题（IN-3 根因，实测）

`parseWorkerLine` 在列数不在容忍区间时 **`return undefined`**（事故前为 `WORKER_COLS = 8; if (parts.length !== 8 && parts.length !== 7) return undefined;`），`readAll()`（`:117-121`）默默过滤掉这些行，`upsert()`（`:123-140`）随后**读全表 → 改一行 → tmp+rename 整文件回写** ⇒ "解析不了"被固化为"**永久删除**"。

触发序列（`evidence/incident-in3-queue-reenqueue-20261010.md`）：行格局 8→9 列（`b8bc115ff`，新增 `origin`）→ 长驻窗口仍跑旧解析器 → 252 行被丢弃 → `readAll()` 归零 → 全项目任务被当成"从未派发"而全量重派。

**注**：事故后 HEAD 已把常量放宽为 `WORKER_COLS_MIN = 7 / WORKER_COLS_MAX = 9`，但这只是"把某一列数塞进容忍区间"，**没有改变"不可解析即静默丢弃"这一危险语义**，也没有版本化契约。

## 交付

1. `parseWorkerLine(line)` → `{ ok: true, entry } | { ok: false, reason: "cols" | "sep" | "empty" | "encoding" }`；**不再返回 `undefined`**。
2. 新增 `readQueue()` → `{ rows, unparsable: Array<{ index: number; line: string; reason: string }>, version: 1 | 2 }`；`readAll()` 保留为兼容包装（`readQueue().rows`），既有调用点零改动。
3. `upsert()` 回写：**按 index 槽位回插**原行；不可解析行**原文保留**（不改、不删、不重排）。
4. 版本头：首行 `# mw-queue:v{2}` 可识别；读时 `#` 行不计入数据行；**已有文件无头 ⇒ 不补头**（P-018），仅新建队列写头。
5. 不新增 timeline 事件（告警面 = doctor + 面板 + 派发抑制，见 T-18 / T-17 / T-13）。

## 契约（冻结）

- **不得**把 `unparsable` 行写进 `rows`（否则下游把坏行当有效行）。
- **不得**在 `upsert` 里做任何"清理/归一化"动作。
- `WORKER_COLS_MAX` 保持 9；扩张容忍区间必须在**有版本头 + 有测试**的前提下做。
- 解析失败必须**可归因**（`reason` 区分列数/分隔符/空行/编码），不许只给布尔。

## [VERIFY]

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts   # 本卡新建
```

并给出：9 列样本（含 `origin`）读入行数、插入 1 行 10 列后的 `unparsable.length`、以及回写后文件行数（应等于插入后行数）。

## 非空洞对照

1. 把 `upsert` 回写改回"过滤后重写" ⇒ `preserves-unparsable` 用例必红（行数变少）。
2. 把 `WORKER_COLS_MAX` 改回 8 ⇒ `reads-nine-column-rows` 用例必红（IN-3 样本读入行数 < 总数）。
3. 去掉版本头识别（把 `#` 行当数据行）⇒ `version-header-not-a-row` 用例必红。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-15-worker-store/report.md`，写完立即复制到 `evidence/runs/`（R7：IN-3 曾覆写产物）。
