# RQ-3: 断言分类与反例集（review 卡的负样本）（research）

- Key: claim-driven-review
- type: research
- 写面：只读仓库；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」；本卡服务于"审查结论可判定、可回读"）。
- 本 key 的需求（用户已定，**不要重新讨论**）：review 卡声明可证伪断言（`id/陈述/反证条件/定位/判据/预算`），结算期强制"每条断言一行裁决 + 证据引用"。本卡产出**分类法与负样本**，用于防止新判据误拒和防止被绕过。
- PM 已确认的语料（作为起点）：
  - `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/task.md`：一张真实 review 卡，含 4 major + 2 minor 的关闭判定要求，且"要求"里已有 grep 级/逐条对照形态的判据。
  - review 卡的强制 extras：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:189-190`（`审计目标`、`未覆盖面声明`）+ `TYPE_EXTRA_PATTERNS.review`。
  - 产出段的恢复契约：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:48-63`（`结论/证据/残留与未验证/上下文来源`）。
  - 历史坑：`.agenticdoc/_pitfalls.md` P-007（长报告无落盘）、P-048（`worker_file` schema 误拒）。
  - 预算饥饿史：`packages/multi-workers/autopilot/dispatch.py:224-250`（FeatureMigrator 两个 L3 reviewer 花光 8 次配额，0/23 与 0/31 VC 无法断言）。

## 要求

1. **语料盘点**：列出 `.agenticdoc/*/tasks/*.md` 与 `.agenticdoc/*/workers/*/task.md` 中所有 review/reviewer/verifier 任务（给计数与命令）。抽 8–12 张真实的，逐条把它们的"要求/验收"拆成**判定单元**，标注类型：`命令可判`（有命令+期望）、`grep 可判`（存在性/计数）、`结构可判`（表格/矩阵完整性）、`仅人工`。
2. **分类法**：给出四类的判定边界与每类的最小 `判据` 写法模板（含 3 个真实例句）。判定"一条要求属于哪类"的**可执行规则**（不是主观描述），至少能处理：含具体命令、含 `path:line`、含"逐条/全部/是否"、含"评审意见/建议"等形态。
3. **误拒反例集（重点）**：从语料里找出 **≥6 条**"看起来像断言但无法按 AC-001 四要素填"的真实要求（例如"整体是否自洽""是否引入新的 fail-open""回归审计"）。对每条说明：为什么四要素校验会误拒、应归入 `manual` 还是应改写为可机检、以及改写后的样子。这是本卡最重要的产出——design 要靠它定 validator 的宽容边界。
4. **被绕过反例集**：给出 ≥5 种 worker 可以"表面合规但实际没审"的写法（例如复制 claim id 空跑、全部标 `unverified`、引用不存在的行号、证据只写 `report.md`、把断言改写成同义反复），并给出**廉价的机器判据**（不调用 LLM）逐条拦住它。每条判据要能落到具体校验点（卡 gate / 结算 gate）并说明误伤风险。
5. **schema 建议**：给出 `## 断言裁决` 表的列定义、裁决 token 闭集、证据引用语法（`path:line`、`path:a-b`、`命令 => 结果` 的精确形式）、`unverified` 原因词表（建议 5–8 个受控词），并用真实语料写 10 行示例表。
6. **`manual` 档位**：定义 manual claim 的计入预算方式、允许的裁决值、以及在覆盖表里的呈现（避免它变成"写完就 PASS"的后门）。

## 写入允许面

- `.agenticdoc/claim-driven-review/evidence/research/spec-rq3-claim-taxonomy-20261020.md`

## 唯一证据文件

`.agenticdoc/claim-driven-review/evidence/research/spec-rq3-claim-taxonomy-20261020.md`

用 `bash` + Python 直接写该路径（写面允许 `<key>/evidence/**`）；同时在本任务目录用 `worker_file` 写同内容 `report.md`。**不得写其它任何文件**。

## 交付格式

- `## 0. 结论先行`（≤6 条）→ `## 1…6` 逐问作答 → `## 反例集`（表格：反例 / 为什么会误拒或被绕过 / 拦住它的判据 / 误伤风险）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每条结论给语料出处（`文件:行号` 或卡片路径 + 行号）。未找到写「未找到（命令 + 输出）」，禁止编造。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest。临时文件放 `%TEMP%`。
