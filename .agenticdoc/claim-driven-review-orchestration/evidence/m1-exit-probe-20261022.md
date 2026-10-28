# M1 出口实测：`plan` 档在真实 review 卡上跑

- 日期：2026-10-22
- 口径：`planReviewSplit`（纯组合器）+ `planReviewSplitGate`（写 manifest、零派发）
- 探针：`packages/coding-agent/test/suite/probe-m1-real-cards.test.ts`（临时，跑完即删）
- 原始输出：`.mw/runs/m1-probe-out.txt`、`.mw/runs/probe-entries-out.txt`

## 1. 四个真实 review 卡的 `plan` 回执行

| 卡 | 回执行 | claims | units |
|---|---|---|---|
| `mw-worktree-junction-guard/tasks/T-QG-evidence-closure.md` | `mode=plan units=0 claims=0 cap=0 capSum=0 inflation=0.00 l0=0/12 l1=ok gap=no-source` | 0 | 0 |
| `mw-decision-substitution/tasks/QG-review-2.md` | `mode=plan units=0 claims=0 … l0=0/11 l1=ok gap=no-source` | 0 | 0 |
| `mw-signoff-per-key/tasks/QG-review.md` | `mode=plan units=0 claims=0 … l0=0/5 l1=ok gap=no-source` | 0 | 0 |
| `claim-driven-review/tasks/T-07a-e2e-review-a.md`（带 claims 块） | `mode=plan units=1 claims=5 cap=30 capSum=30 inflation=1.00 l0=5/5 l1=ok` | 5 | 1 |

结论：**claims 块路径成立**（T-07a 复算无误，`inflation=1.00`），**散文路径在真实 QG 卡上产出 0 条**。

## 2. 为什么是 0（条目分布实测）

`T-QG-evidence-closure.md`：

```
[上下文]      asks=9  withLocator=4     ← 定位在这里，但它们是"被审对象"指针，不是断言
[审计目标]    asks=5  withLocator=0
[要求]        asks=12 withLocator=0     ← 真正的"要做什么"
[未覆盖面声明] asks=3 withLocator=0
AC refs: AC-001, AC-003, AC-008, AC-009, AC-012, AC-013
```

`QG-review-2.md`：

```
[审计目标]              asks=5  withLocator=0
[要求（这是本轮的核心）] asks=11 withLocator=0
[种子]                  asks=5  withLocator=1
```

**真实 QG 卡的写作习惯**：定位写在「上下文/被审对象」（哪份文件要被审），要求写在「要求/审计目标」（要判什么），两者**不在同一行**。T-10 的降级规则要求"条目自带 `path:line`"，因此一条也匹配不上。

## 3. 这暴露的两个缺陷

1. **降级规则不覆盖目标人群**（设计缺口，不是实现 bug）：散文卡需要"要求条目 × 被审坐标"的**跨条目解析**，而不是同行自带。
   可用的确定性桥：
   - 条目里引用 `AC-<n>` → 用该 key 的 `spec.md` 里 `AC-<n>` 的行号当定位（A 类，可机检）；
   - 条目里写 `AC-001 到 AC-013` 这样的**区间** → 按区间展开成逐条断言（评审"每条都给判定"正是要核的东西）；
   - `## 审计目标` 必须与 `## 要求` 平级视为 ask 段（实测它有 5 条目标）。
2. **`l0` 算术在 no-source 分支破了**：`asks=12 mapped=0` 但 `unmapped=[]`，
   违反卡里"`asks - mapped === unmapped.length`"的不变式。`unmapped` 必须装那 12 条摘要。

## 4. 门禁（`planReviewSplitGate`）实测

临时项目 + `.mw/review-split.json = {"v":1,"mode":"plan"}`：

```
[review-split] mode=plan units=0 claims=0 … gap=no-source
[review-split] manifest=.agenticdoc/probe/evidence/split/review-probe-qg-manifest.json
[gate] writing: .agenticdoc, .mw          ← 只多了 evidence/split/ 一个文件
```

断言全过：`workers/` 不存在、`.mw/workers.parallel` 不存在、`.mw/workers.serial` 不存在。
**零副作用成立**（GC-3）。

## 5. 判定

- M1 的**管道**通了：开关 → 提取 → 装箱 → manifest → 回执行，`off` 路径不变，`plan` 零副作用。
- M1 的**降级规则**没达成目标：真实 QG 卡 0 条 claim。按 D-019 的口径这不能算"拆分成立"，只能算"管道可用"。
- 下一步（T-12）：补 AC 引用解析 + 区间展开 + `## 审计目标` 段 + `l0` 算术修正；然后**重跑本文件的四张卡**，
  要求至少两张真实 QG 卡产出 `claims ≥ 5` 且 `l0` 覆盖可解释，否则 `plan` 保持 `off` 默认。

## 6. T-12 之后重跑（同一批真实卡）

| 卡 | 回执行 | claims | units |
|---|---|---|---|
| `T-QG-evidence-closure` | `units=8 claims=23 cap=30 capSum=126 inflation=4.20 l0=6/17 l1=gaps:9` | 23 | 8 |
| `QG-review-2` | `units=1 claims=2 cap=12 capSum=12 inflation=1.00 l0=2/16 l1=gaps:1` | 2 | 1 |
| `QG-review`（signoff） | `units=0 claims=0 … l0=0/6 gap=no-source` | 0 | 0 |
| `T-18-adversarial-qg` | `units=0 claims=0 … l0=0/0 gap=no-source` | 0 | 0 |
| `T-07a`（claims 块） | `units=1 claims=5 … l0=5/5 l1=ok` | 5 | 1 |

进展：AC 桥让最大的 QG 卡从 0 → 23 条 claim（`l0=6/17`，11 条要求诚实记入 `unmapped`）。

### 6.1 又抓到三个缺陷

1. **同一张卡、同一批 claims，`units` 却不同**：直接调组合器得 `units=8 capSum=126`，
   走门禁（`acIndex` 路径拼成 `.agenticdoc/probe/spec.md`）得 `units=12 capSum=138`。
   `packClaims` 按定位 token 聚簇 → 路径拼法不同 → 聚簇不同。**拆分数依赖路径写法**，不可接受。
2. **两张真实卡仍为 0**：`signoff/QG-review` 的 asks 是 6 条列表项但只写“逐条给 PASS/FAIL”，
   AC 范围写在**段标题**里（`## 要求（…对应 AC-001..005）`）；`T-18` 的 `## 要求` 是**散文段落**（无列表项），
   且真要求落在 `## 必须覆盖的 10 项对抗探针` 这类**标题不含“要求”**的段。
3. **`l1` 被打成 `gaps:9`/`gaps:1`**：AC 派生 claim 全为 manual，falsifier 必缺 → `l1` 永远不是 `ok`，
   这个字段失去判别力（该单列 `fals=<n>`）。
