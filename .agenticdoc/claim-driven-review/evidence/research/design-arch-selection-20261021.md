# design-arch: 架构选型依据（claim-driven-review）

> 类型：design 相位证据（架构选型 + 出处）。上游证据：`spec-rq1-review-corpus-20261020.md`、`spec-rq2-seams-20261020.md`、`spec-rq3-claim-taxonomy-20261020.md`。

## 1. 三个候选形态与取舍

| 候选 | 形态 | 结论 | 依据 |
|---|---|---|---|
| A | 新增派发类型 `claim-review`（独立工具集/契约/模型 role） | **否决** | 需改 6+ 文件：TS `TOOL_ALLOWLISTS`（`worker/worker-mode.ts:109-140`）、`DISPATCH_TYPE_VOCABULARY`（`shared/dispatch-card.ts:221-232`）、`DISPATCHABLE_TYPES`（`shared/dispatch-models.ts:75`）、Python `REGISTRY`（`autopilot/dispatch.py:85-127`）、`DISPATCH_ROLES`（`mw_common.py:143`）、恢复契约（`output-sections.ts:52-55` / `dispatch.py:615-619`）；4 条平价测试必红（`test_autopilot_l0.py:233-263`、`test_autopilot_dispatch.py:31-68`、`test_autopilot_l0.py:348-390`、`test_mwoc_s2_sections.py:130-185`）。且 claims 与 `type:` 正交（同一份 review 可能带或不带断言集）。 |
| B | 卡级机器块 `<!-- mw-claims: v1 -->` + 复用 `review` | **采纳** | 上表同一组文件零改动 → 平价锁保持绿；灰度可在块级/环境变量级做，不必新类型 |
| C | 中心化 claims 台账 + 调度器消费 | **否决** | 违反 GC-5（不引入中心化调度器）；且 RQ-1 已证明成本问题是"每次取数的上下文成本"，与调度无关 |

## 2. 四个接缝的选型理由

| 接缝 | 选中点 | 备选与否决理由 | 出处 |
|---|---|---|---|
| 卡 gate | `pm/ui-bridge.ts:2585`（`missing` 聚合处） | 备选：服务层 `launcher.py:2676-2677` —— 那时队列行已写入，拒绝会产生副作用残留，违反 GC-3 | RQ-2 §1.2/§1.4 |
| claims 传递 | 注入 task.md（`mw-dispatch-card: v1` 区） | 备选：结算期按 `card_path:` 回读卡文件 —— 卡可在 run 期间被改写，需 `card_sha256` 校验，成本更高 | RQ-2 §2.3 |
| 结算判据 | 折入 `readTerminalGaps`（`output-writer.ts:357-425`），在 `worker-mode.ts:3872` 之前 | 备选：放在 `taskDone = true`（3906）之后 —— 那时 `writeOutputGuarded` 已定稿，会出现"产物说 done、trace 说缺断言"的分叉 | RQ-2 §2.2 |
| 度量载体 | 独立 `[CLAIMS]` trace 行 + `run.json` 子对象 | 备选：扩展 `[END]` 行 —— 两侧有锚定正则（`heartbeat.ts:93`、`mw_common.py:2768`），改格式即红 | RQ-2 §5.3/§5.4 |

## 3. 预算参数的选型

- 采纳 RQ-1 §5 的实测推导：`fileCap = min(30, Σ预算)`、`byteCap = min(393216, 65536×n)`、每 worker 5 条 claim。
- 否决 spec 初稿的 60 次 / 512 KiB：60 次 × p90 4,854 tokens = 291k，远超可用 177,856。
- 否决 RQ-2 §3.4 的 `min(3n, 60)` / 512 KiB：该段写于 RQ-1 收敛前，沿用初稿占位值；RQ-1 实测 p50 单次取数成本 3,230、p90 4,854，且安全带为累计 <400k chars。
- 依据链：`200000 − 16384(reserve) − 5760(首 prompt) = 177856`；`177856 / 4854 = 36.6 → 30`（留 18% 余量）。

## 4. 分类器不参与拒绝的原因

RQ-3 §2.4 实测：规则分类与人工裁决一致率 66/104（63.5%），危险方向（人工 manual 被判成可机检）1 例、保守方向 29 例。保守方向只多记一条 claim，危险方向会放过"没审却判可机检"。因此设计为**卡自报类 + 前缀一致校验**，规则只用于审查者自查。

## 5. 未覆盖面声明

- 未验证：`[CLAIMS]` 行在 110 列终端下的实际展示（P3 试点时测）。
- 未验证：conductor 的 synthesized 卡（`dispatch.py:777`）带 claims 的路径（本设计按"退化不写 caps 行"处理，收益不覆盖该路径）。
- 未覆盖：per-key 灰度开关（需新配置键，留到 P3）。
