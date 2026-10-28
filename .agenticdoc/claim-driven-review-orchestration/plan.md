# Plan: claim-driven-review-orchestration

原则：**先交付只读规划器，再碰派发链**。每个里程碑独立可验证，任一里程碑失败可停在 `off` 不影响现状。

## M1 开关与只读规划器（无派发、无队列写入）

| 交付 | 写入面 | 验证 |
|---|---|---|
| `shared/review-split.ts`：`REVIEW_SPLIT_DEFAULT="off"`、`resolveReviewSplit()`（env > `.mw/review-split.json` > 默认，回 `{mode, source}`） | 新文件 | 单测：三档 × 三来源（env/config/default）+ 非法值降级 |
| `mw review-split status/set`（`packages/multi-workers/mw.py`） | `mw.py`、`.mw/review-split.json`（set 时原子写） | `status --json` 回显值+来源；`status` 前后 `.mw` 全树 sha 不变；`set` 后 mtime/sha 变 |
| `shared/claim-extract.ts`（E1：findings 行 / AC 行 / diff hunk / 反模式命中 → `Claim[]`） | 新文件 | 幂等（同输入两次 sha 相同）；源侧双向对账（`extract:lost-source-row` / `foreign-locator`） |
| `shared/claim-pack.ts`（簇原子性 + `Σ预算≤8` + 每单元 ≥1 机检 claim） | 新文件 | 三个约束各一条负例；struct N≥5 不拆散父子 |
| `shared/split-manifest.ts`（序列化 + sha 链 + 校验） | 新文件 | 改一个 id / 一个 sha → 校验失败 |
| plan 回执行 `[review-split] mode=plan ...` | `pm/ui-bridge.ts` | 真实卡跑 plan：出 manifest、**无** `workers/<task>-u*` 目录、无队列行 |
| Python 平价 | `autopilot/review_split.py` + `dispatch.py` 读取点 | 平价锁：TS/Python 对同一 config 解析结果一致 |

**M1 出口**：`mw review-split set plan` 后派一张真实 review 卡，能看到"如果拆会拆成什么样"，且工程上与今天无差异（`off` 时逐字节相同）。


## 判决（2026-10-22）：M1 未过门禁，M2/M3/M4 撤销

`evidence/m1-verdict-20261022.md`：两张路径都不成立 ——

- E1 散文降级：真实 QG 卡 12/12 单元 `manual-only`，`inflation=6.20`；
- E2 LLM 提取：判定层机检 0/39，且 `CLAIM_MANUAL_CAP=4` 使忠实编码不可能。

因此**本 plan 的后三个里程碑不再执行**：没有 `on` 档就没有 merge 门禁与度量的适用对象。
M1 本身交付完成并通过质量门（scope=narrow），代码保留、开关默认 `off`。

## M2 merge 门禁（不依赖子卡真的跑起来）

| 交付 | 验证 |
|---|---|
| manifest 完整性校验 + `merge-blocked:<原因>` | 构造"缺一个单元 / 少一条 id / sha 不匹配"三种残缺 manifest，全部拒绝派 merge |
| `[review-split]` 汇总行与 `[SPLIT]` 级别区分 | 行格式逐字断言 |

## M3 `on` 档：子卡派发 + merge 单元

| 交付 | 验证 |
|---|---|
| k 张子卡（各自 `read_scope` + 逐单元 `write_face`） | 5 张子卡真并行（墙钟 < 2× 最长单元），无 `write-face-undeclared` 拒绝 |
| merge 卡（`read_scope` 只放子报告 + 自己 task.md，`fileCap ≥ k+2`） | 越界读被拒；merge 表 = 母卡 claim 数 |
| L1/L2 判据落地（12 `split:*` + 4 `merge:*`，复用 11 token、豁免 2） | 每条判据一条负例 + T-07 三份真实 report 回放零误报 |

## M4 度量与判决

| 交付 | 验证 |
|---|---|
| `launcher.py` `end` 补 `claims` 标量 | `mw stats --key <k>` claims 列非 0；`tokens_per_closed_claim` 出真值 |
| arm 级聚合（`Σtokens / Σclosed_dedup`，merge 单列） | 1×n 与 k 单元两臂并排一行 |
| 四项判决（保真/成本/墙钟/上下文）成报表行 | 用 §5.2 门槛自动判 `ok|fail` |

## 依赖与并行

- M1 内部：`review-split.ts` / `mw.py` CLI / `claim-extract.ts` / `claim-pack.ts` / `split-manifest.ts` 互不冲突，可并行。
- M2 依赖 M1 的 manifest 类型；M3 依赖 M2；M4 独立（只碰 `launcher.py`/`usage.py`/`status-model.ts`），可与 M1 并行开工。
- **同一文件同一时刻一个 worker**：`pm/ui-bridge.ts` 与 `autopilot/dispatch.py` 是热点，M1 与 M3 的改动必须串行。

## 风险闸

每完成一个里程碑，跑一次 `off` 逐字节回归 + 既有 159 TS / 27 Python。任何红 → 停在当前里程碑，不开下一个。

## 撤销记录

| 里程碑 | 状态 | 依据 |
|---|---|---|
| M1 开关与只读规划器 | ✅ 完成（含 T-06/T-09/T-12/T-13 修正） | 116 TS + 58 Python 全绿 |
| M2 merge 门禁 | ⛔ 撤销 | 无 `on` 档 → 无 merge 卡 |
| M3 `on` 档 | ⛔ 撤销 | M1 判决不成立 |
| M4 度量与判决 | ⛔ 撤销 | 同上；`tokens_per_closed_claim` 仍 `n/a`（Phase 1 遗留，未在本 key 修） |
