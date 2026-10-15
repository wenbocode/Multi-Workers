# DR2 design 研究：输出契约判定、`report-<slug>.md` 候选集、机械段补齐与自检

- key: `mw-worker-output-contract` ／ 阶段: DESIGN ／ worker: `woc-dr2-contract-judgment`
- 卡: `.agenticdoc/mw-worker-output-contract/tasks/T-DR2-contract-judgment.md`（card_sha256 `3964acdf131939a0c0fc422eed5accf8d184103bb03aeafaa1f64f82461b6d59`）
- 上游已锁定前提（本报告不重新发现，只做增量）：受判文本 = `agentProductText()`（`worker/output-writer.ts:140-147`）；判定 = `checkRecovery`（`worker/output-sections.ts:87`）；调用点 `worker/worker-mode.ts:2740` 与 `output-writer.ts:257-259`；`exitCode` = `worker-mode.ts:2746`；判定早于唯一一次 `writeOutputGuarded`（`:2761`）。
- 方法边界: **全静态只读 + 只读 Python 统计脚本**。未跑 vitest / pytest / `npm run check` / `npm run build` / `./test.sh` / `npm install`；未修改仓库任何文件（写面只有本任务目录与唯一证据文件）。所有行号为本机 HEAD 工作区实测。
- 语料口径: 受判 target = `.agenticdoc/**/workers/<task>/` 有 `task.md` header `type:` 且候选文件非空者。本轮实测窗口 `2026-10-14T03:47:40Z`，**437** 份（并行 worker 会持续新建目录，同一脚本重跑可见 ±1–2 份漂移，RQ-1 口径为 433；差异全部来自 `manual-*`/`_scratch`/在途新目录，不改变任何结论方向）。

## 0. 结论与判定表

### 0.1 逐条结论

| # | 结论 | 依据坐标 |
|---|---|---|
| C1 | **判定改动最小化**：`checkRecovery` 的 haystack 由「整篇 `toLowerCase()` 文本」换成「H2 标题行集合」，别名表 45 条**逐字不变**，正文彻底不参与满足判定 | `output-sections.ts:87-91`（现状）/ `:63-64`（`includes`）/ `:89`（`text.toLowerCase()`） |
| C2 | **标题层级取 `##`（恰二层）**：允许 0–3 前导空格（CommonMark），fenced code / 引用块内的 `##` 不计。**不取 `###`、不取 `#`** | 读侧 `shared/output-sections.ts:71`（`SECTION_SPLIT_RE = /##\s+(.+?)\s*\n+…/`）与 `pm/ui-bridge.ts:478-488`（`readOutputSection` 亦 `##` 锚定）——判据口径超过读侧口径即重造 FW-005「两套结构」 |
| C3 | **归一化只做三件事**：去行尾 `#` 收尾串、`trim()`、内部空白折叠为一个空格；ASCII 大小写不敏感。**不做标点剥离**（`csv` 实测 0 收益） | §1.3 + `mw_norm.py` 输出（trailing-punct 增益 `{}`） |
| C4 | 判定表 16 例（AC-001 的 8 例 + 8 例边界），「仅正文含别名而无标题」判缺，且 `## Recovery Gaps` 正文里框架自己写的「缺失段：X」**不再自证满足** | §1.5 |
| C5 | **AC-015 取「纳入候选集」**，顺序 `report.md` → `report-<slug>.md`（mtime 降序，同名 tie-break 名称升序）→ `output.md` → settle 摘要；**单文件单挑，不拼接** | §2.1/§2.2 |
| C6 | **AC-015 有第二个入口必须同批改**：`worker-mode.ts:2733-2738` 的 `reportProduct` 只 `statSync(report.md)` ⇒ coding 型只写 `report-<slug>.md` 时 `judgeRecovery=false`，**根本不判** | §2.3（建议直接改用已存在的 `findNonEmptyReport`，`deliverable-evidence.ts:105-119`） |
| C7 | **S3 机械段白名单 v1 = `{上下文来源}`**，唯一。coding 型额外段不纳入（账本未可信 + spec R2 禁止用机械段掩盖真实缺口） | §3.1；spec §1.6 S3 / R2 |
| C8 | **S3 的顺序矛盾解法：在判定之前，把段追加到「判定将要读的那个文件」**（I2 = `worker-mode.ts:2739`）。「只补 `output.md`」被否决——受判文本是 `report.md` 时二者必然不一致，正是 AC-005 明令禁止的形态 | §3.1/§3.2 |
| C9 | 内容生成来源：`task.md` 头 `card_path`/`card_sha256`（`readTaskHeaderScalar`，`shared/task-frontmatter.ts:117`）+ trace `[TOOL] … read <path>` 去重前 10 + `[WRITE_FILE]`/`collectArtifacts`；带 `<!-- mw-mechanical: 上下文来源 v1 -->` 幂等标记，纯 append，≤2 KiB | §3.3 |
| C10 | 失败回退：无可判产物文件 / 目标 basename 不在允许集 / append 抛异常 ⇒ **no-op + `[FLOW]` trace，判定照旧 fail-closed**，绝不判内存补丁文本 | §3.4 |
| C11 | **前置清单 = `recoverySectionsFor(type)` 渲染成 `## 交付段契约（本角色）`，由生产者注入**（Python `dispatch.py` + TS `ui-bridge.ts`）；worker 侧**只审计、不改 `task.md`** | §4.2（worker 侧改写会推高 `task.md` mtime，触发 `launcher.py:870-895` 的「mtime 晚于 dispatched_at ⇒ 无条件判」分支） |
| C12 | 自检 I1 落在 `agent_settled` 的两个 `finishSuccess()` 调用点（`worker-mode.ts:2827`/`:2859`）之前，用 `sendUserMessage(..., { deliverAs: "followUp" })`（复用 `:2556-2564` 的既有模式），每进程一次，只在「非机械段缺口非空且预算有余」时触发 | §4.3 |
| C13 | **修正 RQ-1 的「0 个既有用例翻转」**：纯谓词级 0 翻转成立，**settle 级至少 2 例翻转**（`dispatch-recovery-terminal.test.ts:162` 由 exit=2 变 exit=0；`output-recovery-contract.test.ts:282` 单次 settle 不再落终态） | §6.1 |
| C14 | **量化 S1/S2/S3 的分工**（H2-only，437 受判 target）：相对旧整篇别名判据 **116 例翻转**；其中 **84 例缺 `上下文来源`**（S3 可介入），**S3 单独救回仅 6 例**；**32 例与 `上下文来源` 无关（S3 完全无效，只能靠 S2）** ⇒ **S2 是承载机制，S3 是减噪** | §6.4；`mw_auth.py` |
| C15 | AC-005 的 3 例：在 `##`-only 下「唯一缺机械段」的池子有 10 例，其中**只有 1 例**（`mdc-rq1-dispatch-chain`）task.md 带字面 `card_path`+`card_sha256`。⇒ 若坚持字面 card 前提，`##`-only 历史语料**供不出 3 例**；须把「任务事实齐备」读作「至少一类真实事实可用（card / trace 读取 / 产物）」 | §5.1/§5.2 |

### 0.2 契约判定表（新算法）

`required = 结论 / 证据 / 残留与未验证 / 上下文来源`（+ coding `改动清单` / review `未覆盖面声明`）。下表 `type=research`。

| # | 输入特征 | 期望 | 理由 |
|---|---|---|---|
| 1 | 4 个 `## <段名>` 齐全 | 通过 | 标题齐全 |
| 2 | 缺 1（`## 上下文来源` 无） | 不通过，`missing=[上下文来源]` | 结构 fail-closed |
| 3 | 缺 2 | 不通过，`missing=[两个]` | 同上 |
| 4 | 缺 4 | 不通过，`missing=[全部]` | 空文本等价 |
| 5 | **仅正文含别名、无标题** | 不通过 | 正文不参与（AC-001 明列） |
| 6 | 标题用别名（`## TL;DR` / `## Evidence` / `## Remaining` / `## Sources`） | 通过 | 词汇 fail-open 保留 |
| 7 | `## 证据` 重复两次 | 通过 | 存在性判定，与重复无关 |
| 8 | 标题在引用块内（`> ## 证据`） | 不通过 | `>` 破坏 ` {0,3}##` 前缀（AC-001 明列） |
| 9 | 标题在 fenced code 内 | 不通过 | 围栏状态机；fail-closed |
| 10 | `### 证据`（仅三层） | 不通过 | C2：恰二层 |
| 11 | `   ## 证据`（≤3 空格缩进） | 通过 | CommonMark 允许 0–3 |
| 12 | `    ## 证据`（4 空格） | 不通过 | CommonMark 视为缩进代码块 |
| 13 | `## 证据 ##`（收尾串） | 通过 | 去收尾 `#` |
| 14 | `## 抽样复核机器证据`（标题内含别名） | 通过 | 标题内子串 fail-open（与旧档同精神） |
| 15 | 仅 `## Recovery Gaps` 里写「缺失段：证据」 | 不通过 | 框架自述不再自证（旧档最大假阳源） |
| 16 | CRLF 全文 | 与 LF 等价 | 既有断言 `output-recovery-contract.test.ts:136` |

### 0.3 6 个历史实例在新算法下的预期结论

受判文件列 = **AC-015 新候选集**（`report.md` → `report-<slug>.md` → `output.md`）下的选择；「新缺失」= H2-only；「旧」= 现行整篇别名（对同一份盘上文本）。**重要限定**：settle 当时的受判文本可能是 settle 摘要（review 型无 write 工具、不能写 `output.md`，`report.md` 当时不存在），盘上文本是**事后**产物；本表是 AC-010 语料口径（重放「受判对象」），不是逐字节的「判前文本」。

| task | type | 受判文件（新候选集） | 新缺失 | 旧（整篇别名） | 结论 |
|---|---|---|---|---|---|
| `wjg-qg-evidence-closure` | review | `report-quality-gate-report-20261013.md`（23,252 B） | `残留与未验证`、`上下文来源`、`未覆盖面声明` | 通过（虚高） | **AC-015 修好「判错文件」**：内容全在 `report-<slug>.md`，旧判据读的是空模板 `output.md`；S1 下仍 exit=2，需 S2 一回合 |
| `wjg-w12-negative-space-audit` | review | `report-negative-space-audit-20261013.md`（37,149 B） | `结论`、`证据`、`残留与未验证` | 通过（虚高） | 同上；FM 报告的 `### N-0x` 全是三层，不吃 |
| `wjg-w15-delta-adversarial` | review | `report-delta-adversarial-audit-20261013.md`（30,257 B） | `残留与未验证` | 通过（虚高） | 只差 1 段（真实段，非机械），S2 单回合可救 |
| `wfg-rq2-enforcement` | research | `output.md`（2,658 B，settle 当时 `report.md` 尚不存在——其 mtime 晚于 `run.json`，内容是 PM 补录） | `证据`、`残留与未验证`、`上下文来源` | 通过（虚高） | 机械段只占 1/3，S3 不够 |
| `wfg-rq3-safety` | research | 同上 | 同上 | 同上 | 同上 |
| `wfg-rq-d2-runtime-guard` | research | 同上 | 同上 | 同上 | 同上 |

⇒ 6 例在新算法下**全部仍 exit=2**（差别是「判错文件」被 AC-015 修掉、缺失集合变准），**没有一例是「唯一缺机械段」**。这与 spec §1.7 第 1 条「其中 3 次唯一缺项是机械段」不符，见 §5.1。

## 1. 新判定算法的精确规格

### 1.1 接口与签名（保持符号稳定）

`worker/output-sections.ts` 内 `checkRecovery(text, type) → RecoveryVerdict` 签名不变（`ok` / `missing` / `required` 三字段语义不变，既有 17 例测试只读这三者，编译层零迁移）。改动只在函数体与新增一个**诊断字段**：

```ts
export interface RecoveryVerdict {
  ok: boolean;
  missing: string[];
  required: string[];
  /** 诊断用（不参与 ok）：旧宽档下会满足、标题档下不满足的段。
   *  供 S2 自检回读与 AC-010(c) 的 110 例逐条归因，不进 exitCode。 */
  bodyOnly?: string[];
}
```

成本：`O(required × H2 标题行数)`（spec §2.2 约束），单次线性扫描，无新增轮询/线程。

### 1.2 标题识别规则（逐条）

1. 先按 `\n` 分行，行尾 `\r` 剥除（CRLF 等价）。
2. 维护围栏状态机：`line.trimStart()` 以 ``` 或 ~~~ 开头即翻转；围栏内任何行都不是标题。
3. 标题行正则（恰二层、0–3 前导空格、`##` 后必须跟空白）：
   `^ {0,3}##(?!#)[ \t]+(.*)$`
   - `# 结论` / `### 结论` / `#### 结论` 均**不**命中（`(?!#)` 与固定两个 `#`）；
   - `> ## 结论` 不命中（`>` 破坏前缀）→ 引用块例判缺（AC-001 第 8 例）；
   - `    ## 结论`（4 空格）不命中 → 与 CommonMark 缩进代码块一致。
4. **不做**集合式扫描：`## ` 出现在 HTML 注释、表格单元格、行内代码里都不算（前缀规则天然排除）。

### 1.3 归一化规则

对每个命中的标题文本依次：

1. 去**收尾**闭合串：`title.replace(/#+\s*$/, "")`（CommonMark 的 closing sequence）；
2. `trim()`；
3. 内部空白折叠：`replace(/[ \t]+/g, " ")`（使 `context  sources` 与 `context sources` 等价）；
4. `toLowerCase()` 后与同样 lower 的别名做 `includes`。

**明确不做**（均有实测支撑）：
- 不剥标点：全语料 H1–H6 标题行尾标点分布 `{. 23, 。3, ：3, : 3, ，2, , 1}`，对必需段命中增益 **0**（`mw_norm.py`）。规则越少越可预测。
- 不做全角/半角互转、不做简繁、不做拼音：无需求证据，且会引入不可枚举的等价类。
- 不去前导 `#` 以外的装饰符（`**`、`-`）：靠标题内子串 fail-open 已足够。

### 1.4 别名集合

**逐字沿用现表 45 条**（`output-sections.ts:46-53`），不增不减。理由：

- 别名表不是本 key 的缺陷面（spec §1.7 第 7 条已定：宽档的理由被误引）；收窄会额外制造翻转面，扩大会削弱「哪些段」的可预测性。
- 现表已含 `summary`/`tldr` 等，使 harness 模板 `## TL;DR`/`## Summary` 仍满足 `结论`——这是**保留**的（读侧同一事实；且不改则 `## TL;DR` 本来就出现在 `output.md`）。
- `## Recovery Gaps` / `## Questions` 不在任何别名表内（RQ-1 已确证），因此框架自述段不会自证满足。唯一残留风险是**正文**里的段名，已被 S1 关掉。

### 1.5 语料统计（用于支撑「不做标点剥离」「不做 `###`」）

`mw_norm.py`（只读，H2 与 H2+H3 对照）：

- 前导空格缩进的 ATX 标题行：**88** 行 → 所以归一化必须允许 0–3 空格（否则误收）。
- 行尾 `#` 收尾串：**0** 行（保留该规则无害，为 CommonMark 兼容性）。
- fenced code 内的 `## ` 行：**13** 行 → 围栏状态机把「做样例会写 `## 证据`」的报告从不通过改成不通过（fail-closed，方向正确）。实测对 437 个 target 的 pass 数无影响（`mw_matrix.py` 的 D 变体 = A 变体）。
- 接受 `###` 的增益：**38 个 target** 会多满足至少一个必需段；但 pass 仅从 36 升到 41（`mw_auth.py`）。⇒ 收益存在但小，且与读侧 `##` 口径冲突，故取 `##`-only（C2）。
- 收尾标点归一：增益 **0**。

### 1.6 判定表（16 例）

见 §0.2。AC-001 的 8 例逐例落位：全 5 段(1) / 缺 1(2) / 缺 2(3) / 缺 5(4) / 仅正文(5) / 标题用别名(6) / 标题重复(7) / 标题在引用块内(8)。新增 8 例（9–16）为围栏、三层、缩进 3/4、收尾串、标题内子串、框架自述、CRLF。

## 2. `report-<slug>.md` 候选集（AC-015）

### 2.1 对齐方式：**纳入候选集**（否决「从白名单移除」）

四条硬证据表明 `report-<slug>.md` 已经是框架的**一等产物名**，只有受判文本选择器没跟上：

1. **交付 oracle 已认**：`shared/deliverable-evidence.ts:105-119 findNonEmptyReport()` 用 `WORKER_FILE_NAME_RE` 遍历，`report.md` 与 `report-<slug>.md` 都算 `channel=report`（文件头注释 `:15` 明写）。⇒ 现状可同时 `delivered=true` 且「按空模板被判缺段」，即 FW-001/QG 的形态。
2. **派发期写意图判据已认**：`pm/ui-bridge.ts:1707 judgeWriteTarget` → `:1717` 用同一个 `WORKER_FILE_NAME_RE`。
3. **结算标签已认**：`worker-mode.ts:2695-2701 writesLabel()` 的 `/^report-.+\.md$/` 会把 `report-<slug>.md` 报成 `report.md`。
4. **角色通道已认**：`worker/worker-file-tool.ts:42 WORKER_FILE_NAME_RE`，且是 `worker_file` 的 `parameters.pattern` 单一来源。

从白名单移除会：把 research/review 唯一写通道的命名自由度砍掉（现有 33 个 target 携带 `report-<slug>.md`）；与上述三处判据矛盾（P-08 单一来源失守）；并让 `mwds-t02-write-intent.test.ts:573`、`agent-team-loop-worker-file-tool.test.ts:276-278` 的既有断言失去锚点。**故取「纳入候选集」。**

### 2.2 优先级与多文件选择

**规则（固定优先级 + 仅 slug 兄弟间用 mtime）**：

```
1. report.md                        （存在且 trim() 非空）
2. report-<slug>.md 中最新的        （mtime 降序；mtime 相等时名称升序，保证确定性）
3. output.md                        （存在且 trim() 非空）
4. settle 摘要                      （都空时的既有回退，不变）
```

选择理由：

- `report.md` 置顶：保留现有行为（下面 §6.1 的 3 个既有优先级用例不翻转），且 design §3.1 把 coding 的变更段放在它。
- slug 文件排在 `output.md` **之前**：`output.md` 是框架**跨 run 追加**的产物（`output-writer.ts:370-371` 的 D-117 合并 + 每轮一个 harness block），其 `## TL;DR`/`## Summary`/`## Questions`/`## Recovery Gaps` **不是 agent 的产出**；把 harness 模板当作受判文本正是 FW-001 的根因（QG/W-12/W-15 三例）。
- **不做全局 mtime 排序**：`output.md`/`report.md` 都是跨 run 追加/覆写，mtime 不能作为全局优先级键；且会引入测试抖动。仅在「同名前缀、语义等价、数量不定」的 slug 兄弟间用 mtime 作 tie-break。
- **不做拼接**：拼接会同时改 `diffLedger` 的声明抽取面（`change-ledger.ts:352 extractLedgerBody` 只取首个声明段），可能引入新的 `unrecordedFiles` exit=2，收益（防「碎片化报告」）在语料上无证据（22 个 target 有 2+ report 文件，但都是一「主」+「附录/复验」）。
- **`report.md` 与 `report-<slug>.md` 并存时只取 `report.md`**（单挑），且该行为被既有用例锁定（§6.1）。

### 2.3 必须同批改的第二个入口（实现清单）

| # | 位置 | 现状 | 改法 |
|---|---|---|---|
| 1 | `worker/output-writer.ts:140-147 agentProductText` | 硬编码 `["report.md","output.md"]` | 换成候选解析器（顺序见 §2.2），返回 text |
| 2 | `worker/worker-mode.ts:2733-2738 reportProduct` | `statSync(join(taskDir,"report.md")).size > 0` | 换成 `findNonEmptyReport(taskDir) !== undefined`（**已存在的导出**，`deliverable-evidence.ts:105`）；这样交付 oracle 与「是否判」同源 |
| 3 | 新增 `agentProductSource(dir)`（导出，仅内部使用） | 无 | 供 S3 追加目标与 trace 行使用（§3.3） |
| 4 | `shared/` 侧归一 | `writesLabel` 有 `/^report-.+\.md$/` 正则、`findNonEmptyReport` 有 `WORKER_FILE_NAME_RE` | 抽 `isReportProductName(name)` 单一谓词，三处共用 + 一条 parity 测试（P-08 风格） |

第 2 条是关键、且容易漏：漏掉它则 **coding 型「只写 `report-<slug>.md`」的 run 直接不进判定**（`judgeRecovery=false`），AC-015 只修好一半。

### 2.4 语料影响

`mw_cand2.py`（只读，437 受判 target）：

- 携带至少一个 `report-<slug>.md` 的 target：**33**；
- 受判文件选择发生变化的 target：**13**（全部是 `output.md` → `report-<slug>.md`），其中包含 FW-001 的 `wjg-qg-evidence-closure` / `wjg-w12` / `wjg-w15` 三例，以及 `wip-qg-review`、`xkey-rm-rq1-code-facts` 等。
- `report.md` 存在的 243 个 target 选择不变（优先级用例不回归）。

## 3. 机械段自动补齐（S3 / I2）与顺序矛盾

### 3.1 顺序矛盾的三种解法与裁决

矛盾原文：判定在 `readTerminalGaps`（`worker-mode.ts:2740`）发生，而唯一一次写出是 `writeOutputGuarded`（`:2761`）；受判文件可能是 **agent 写的 `report.md`**，框架的 harness block 只写 `output.md`。

| 解法 | 做法 | 裁决 |
|---|---|---|
| A. 只补 `output.md` | 在 `writeOutput` 里插 `## 上下文来源` | **否决**。受判文本是 `report.md` 时，判定读的文件与产物文件不同 ⇒ 直接违反 AC-005「判定与产物一致，不允许只对内存文本判定」；且 S3 对 13 个 AC-015 变化 target 中的 3 个 FW-001 例完全无效 |
| B. 判内存补丁文本 | 判 `text + block`，不落盘 | **否决**。AC-005 明文禁止；且 PM 回读/后续重判看到的是另一份文件 |
| C. **在判定之前把段追加到「判定将要读的那个文件」** | I2 处解析 `agentProductSource(dir)`，对该文件纯 append；随后判据自然读到它 | **采纳** |

C 的政策面论证（为什么框架**可以**追加到 agent 的文件）：
- 追加发生在 `finishSuccess` 内、`agent_settled` 回调里，即模型最后一个回合**之后**、进程仍存活时，不存在并发写者（GC-3 同进程内，无跨进程协调）。
- 追加是**纯 append**（不截断、不重排 agent 内容），带机器标记与 `[FLOW]` trace，可审计、可幂等。
- 不改 `worker_file` 白名单、不改工具集（GC-5）；不新增可写共享文件（GC-4）。
- 目标 basename 必须在「允许产物集」内（`report.md` | `report-<slug>.md` | `output.md`）且路径必须 resolve 在 `taskDir` 内——即**只碰受判文件本身**，不做泛化写。

### 3.2 插入点与调用序列

```
finishSuccess()                                    # worker-mode.ts:2707
  ├─ taskDone = true; clear timers …               # :2711-2716
  ├─ evidence = hasDeliverableEvidence(...)        # :2720
  ├─ reportProduct = ...                           # :2733-2738（改法见 §2.3）
  ├─ [I2] backfillMechanicalSections({dir,type,…}) # ← 新，:2739，紧邻下一条
  ├─ gaps = readTerminalGaps({...})                 # :2740（判据读到刚落盘的段）
  ├─ exitCode = ...                                 # :2746
  └─ writeOutputGuarded({... terminalGaps: gaps})    # :2761（output.md 走 D-117 合并）
```

配套（一致性）：`writeOutput` 在 `opts.terminalGaps === undefined` 时（即 writer 直调/失败路径 `:2093`/`:2490`/`:2862` 未传 verdict 的形态）也先调用**同一个** `backfillMechanicalSections`，再走 `:257-259` 的默认 `readTerminalGaps`。否则 settle 路径与 writer 直调路径对同一份文本会给出不同 missing 集合（现状 `output-recovery-contract.test.ts:186` 就断言 writer 直调会写出 `## Recovery Gaps`——它必须随此改动更新，见 §6.1）。

### 3.3 `## 上下文来源` 内容生成规则

可用事实（I2 时点全部已在盘上或内存里）：

| 事实 | 来源 | 用法 |
|---|---|---|
| `card_path` / `card_sha256` | `task.md` 头部，`readTaskHeaderScalar(text, key)`（`shared/task-frontmatter.ts:117`） | 首行「派发卡」项；缺则不写该项 |
| 读取来源 | `<taskDir>/trace.log` 的 `[TOOL] <iso> <tool> <target>` 行（写入点 `worker-mode.ts:2363 appendTool`） | 过滤 `tool ∈ {read, grep, find, ls, glob}`，按 target 去重保序，取前 10 |
| 产物 | trace 的 `[WRITE_FILE] <path>`（`change-ledger.ts:123`）+ `collectArtifacts(taskDir)`（`run-store.ts:119`），去掉 `output.md`/`progress.md` | 「产物」项，≤10 条 |
| 任务书自身 | `task.md`（字节数/路径） | 兜底项，保证内容非空 |

模板（逐字节固定，便于测试断言）：

```
## 上下文来源

<!-- mw-mechanical: 上下文来源 v1 -->
- 派发卡：`<card_path>`（card_sha256 `<前 12 位>`）
- 任务书：`task.md`（<bytes> B）
- 读取来源：`a`、`b`、…（trace.log，前 10）
- 产物：`p1`、`p2`、…
```

边界：

- 无 `card_path` 时省略首项（**不做占位**）；全空时至少留「任务书」一项 ⇒ 段体非空。
- 每块 ≤ 2 KiB；路径按 `repoRelativePath` 归一（与账本同源）。
- 机械段白名单 v1 = `{上下文来源}`（C7）。`改动清单` 需要「账本可信」这个前置（AC-017），且用它填段会把「账本该报的缺口」机械抹平，属 spec R2 禁止的「把真实未决项掩盖成机械段」。**故不纳入 v1**；`未覆盖面声明`/`限制`/`Questions` 一律不自动生成。

### 3.4 幂等、原子性与失败回退

- **幂等**：追加前检查目标文件是否已含 `<!-- mw-mechanical: 上下文来源` ⇒ 有则 no-op。这挡住「同进程二次 settle」与「重派后 `output.md` 追加第二块」两条路径。
- **原子性**：`fs.appendFileSync(target, "\n\n" + block, "utf8")`——纯 append，天然满足 P-003（不 read-modify-write）。
- **失败回退（逐条件）**：
  1. 无法解析受判产物文件（只有 settle 摘要）⇒ no-op + `[FLOW] mechanical-backfill skipped=no-product-file`；判定照旧（AC-005 不覆盖该形态，见「未覆盖面声明」）。
  2. 受判文件 basename 不在允许产物集 ⇒ no-op + trace（防御性）。
  3. `appendFileSync` 抛错（EACCES/EPERM/ENOSPC）⇒ catch + `[FLOW] mechanical-backfill failed target=<rel> err=<msg>`，**不做内存补丁**，缺失照报 ⇒ `exit=2`（fail-closed）。
  4. 任务事实表全空 ⇒ 仍写「任务书」兜底项（段标题落盘即满足契约）。
- **成功 trace**：`[FLOW] mechanical-backfill section=上下文来源 target=<rel> sources=<n> products=<n> card=yes|no`。

### 3.5 「判定与产物一致」的可断言形式

AC-005 的第三句由此变成一条机械断言：settle 之后读 `<taskDir>/report.md`（或判定时选中的那个文件），断言其中存在 `## 上下文来源` 标题，且该文件在判定前后的字节差**只有**那一块追加（前缀逐字节不变）。

## 4. 前置清单 + 收尾自检（S2 / I1）

### 4.1 清单来源与渲染

来源**唯一** = `recoverySectionsFor(type)`（`worker/output-sections.ts:56-61`，即 base 4 + 类型额外段），渲染为：

```
## 交付段契约（本角色）

受判产物（`report.md` / `report-<slug>.md` / `output.md`）必须带以下段标题，逐字可复制：
- `## 结论`
- `## 证据`
- `## 残留与未验证`
- `## 上下文来源`
```

要求：**必须是 `## ` 标题体**（P-026：type 专属项必须在 `## ` 标题体内，否则派发卡门禁 / 服务层 extras 判据判不合格）。

### 4.2 注入点：生产者侧（两处），worker 侧不改 `task.md`

`launcher.py:1315-1334 _starter_prompt` 明写「task 正文永不走 argv」，worker 自己 `read` `task.md`（`PI_WORKER_TASK`）。因此清单必须在**worker 启动前**进 `task.md`：

| 生产者 | 落点 | 方式 |
|---|---|---|
| Python（conductor 自动派发） | `autopilot/dispatch.py:602-650 _envelope_card_body` | 在三段信封之后追加 `## 交付段契约（本角色）`；以 `card is not None` 为门（`card=None` 的遗留/单测渲染保持字节不变，`test_autopilot_readcap_injection.py:940-975` 的 frozen-copy 对比不破） |
| TS（`/worker` 手动派发） | `pm/ui-bridge.ts:1961 renderCardSeedSections` / `:2150 writeDispatchTaskMd` | 同形注入；与 Python 侧由一条 parity 测试锁同一份段表 |

**为什么不在 worker 侧补写 `task.md`**：`launcher.py:870-895 _envelope_enforced()` 有一条「`task.md` mtime 晚于行 `dispatched_at` ⇒ 无条件判此行的信封门禁」的分支；worker 启动后改 `task.md` 会**主动**把历史行推进门禁判定面（失败即 refuse dispatch）。→ worker 侧只做**审计**：`before_agent_start`（`worker-mode.ts:2154`）里若 `task.md` 缺该标题体，`appendTrace(... "contract-checklist missing type=<t> (producer drift)")`，fail-open 不影响 exitCode。

### 4.3 自检回合（I1）形态

- **位置**：`agent_settled`（`worker-mode.ts:2806`）内两个 `finishSuccess()` 调用点（`:2827` 无 phase 分支、`:2859` 全部 phase 完成分支）之前加一次性 wrapper `maybeSelfCheckOrFinish()`。不能放在 `finishSuccess` 内部——它第一行就 `taskDone = true`（`:2712`），之后无法再回到 pi 的回合循环。
- **触发条件**（全部满足）：
  1. `selfChecked === false`（每进程一次，防死循环）；
  2. 「缺口 − S3 机械白名单」非空（即真有非机械段缺）；
  3. 预算有余：`budgetMs - (now - startedAt) >= SELF_CHECK_MIN_MS`，建议 `min(5m, budget/4)`（与 `steerAtMs` 同算术风格，`worker-mode.ts:253`）；
  4. 不在 timeout/cancel 路径上（那些路径直接走 `:2490`/`:2862`）。
- **文本**：

```
[mw self-check] 收尾前契约自检：受判产物 <rel> 缺以下段标题：<名称列表>
请在本回合内补齐（追加 `## <名称>` 段，内容必须真实，不得空话）；
`## 上下文来源` 由框架自动补齐，无需处理。补齐后立即结束回合，不要展开新工作。
```

- **投递方式**：`pi.sendUserMessage(text, { deliverAs: "followUp" })`——复用既有 checkpoint steer 的结论（`worker-mode.ts:2550-2564`：裸调 `sendUserMessage` 在 agent 处理中会抛 "Agent is already processing"，`followUp` 才是安全档）。
- **trace**：首次 `[FLOW] recovery-selfcheck missing=<a,b> product=<rel> turn=1`；第二次 settle 后 `[FLOW] recovery-selfcheck resolved=yes|no`。
- **与三段式超时的关系**：只发一条 followUp，不动 idle（`lastActivityAt`）/墙钟（`budgetMs`）两段的输入（spec §1.6 S5 硬约束；`computeRisk` 与这两段无耦合，`worker-mode.ts:2591-2624`/`:2650-2654`）。额外一个回合会让 `lastActivityAt` 自然前移，不会造成误杀。
- **与 S3 的次序**：自检**先于** finishSuccess（因此先于 S3），但它只看「非机械缺口」；机械缺口留给 S3 ⇒ 只缺 `上下文来源` 的 run 不会白白多一个回合（AC-005 的 3 例即此类）。
- **提示不回读**：AC-004 要求 trace 可解析，不要求 agent 回读；避免把「agent 是否照做」变成第二个判据。

## 5. AC-005 重放方法与测试落点

### 5.1 「补录前前缀」的两种读法与实测

| 读法 | 定义 | 实测结果 |
|---|---|---|
| **R-a（框架机械补录前）** | 把「S3 尚未插入 `## 上下文来源` 的受判文本」当输入：即盘上产物文件本身（该例本就缺该标题） | `##`-only 下「唯一缺该段」的池子 = **10 例**；其中带字面 `card_path`+`card_sha256` 的只有 **1 例**（`mdc-rq1-dispatch-chain`） |
| **R-b（PM 人工补录前）** | 把带「（PM-补录，…）」标题的文件切掉补录段后的前缀当输入 | `mw_scan_bf2.py` 只找到 **7** 个带「补录标题」的文件；**没有一例**前缀缺失集恰为 `[上下文来源]`（最少也缺 2 段）⇒ **3/3 不可能达成** |

⇒ AC-005 必须按 **R-a** 读。且 R-a 下若坚持 AC-005 括号里的字面 card 前提，`##`-only 历史语料**只能供出 1 例**。两条出路（须 PM 定，§7）：
- (i) 把「任务事实齐备」定义为「至少一类真实事实可用（card 头 / trace 读取 / 产物）」——池子 10 例，取 3 例绰绰有余；
- (ii) 坚持字面 card 前提 ⇒ 需放宽标题层级到 H1（池子 16 例、3 例带 card：`mdc-rq1`、`mdc-rq2`、`wfg-rq-d1`），但那与读侧 `##` 口径冲突（C2）。

另外必须写明：**6 个 FW-001 实例没有一例是「唯一缺机械段」**（§0.3），所以 AC-005 的 3 例不可能从这 6 例里挑；它们的价值在 §5.3 的 AC-015 重放（判错文件）与 S2 覆盖。

### 5.2 3 例重放配方（R-a + 出路 (i)）

推荐 3 例（H2-only 池中 trace 事实最厚者，均可复跑）：

| # | task | type | 受判文件 | card 头 | trace `[TOOL] read` |
|---|---|---|---|---|---|
| 1 | `mw-dynamic-concurrency/workers/mdc-rq1-dispatch-chain` | research | `report.md` | 有（`card_path`+`card_sha256`） | 46 |
| 2 | `mw-guard-form-hardening/workers/mwgf-rq3-path-resolution` | research | `report.md` | 无 | 9 |
| 3 | `mw-dispatch-settle-gates/workers/mds-qg-b-code-adversarial` | review | `report.md` | 无 | 43 |

步骤（每例一份夹具，**只读源目录、不得原地跑**——S3 会 append，原地跑等于改仓库语料）：

1. `mkdtemp` → 复制**字节原样** `<hist>/task.md`、`<hist>/trace.log`、`<hist>/report.md` 到 `workerDir/`（夹具构造后断言 `report.md` 字节 == 源字节）。
2. 前置断言（S1 单档）：`checkRecovery(reportText, type).missing` 恰为 `["上下文来源"]`（`missing.length === 1`）；等价地断言 `exit=2` 期望值存在。
3. 走真实 settle 路径：`workerModeActivate(fakeWorkerPi)` + `agent_end` + `agent_settled`（复用 `dispatch-recovery-terminal.test.ts:143-155` 的 harness）。
4. 后置断言：
   - `run.json`：`exit === 0` ∧ `status === "done"`（**这就是 `exit=2 → 0` 的机械形式**）；
   - `output.md` 无 `## Recovery Gaps`（`missingSections` 空）；
   - **判定与产物一致**：`<workerDir>/report.md` 现含 `## 上下文来源` H2 标题，且其前缀（插入点之前）与源字节逐字节相同；
   - 生成内容含源 `task.md` 的 `card_path` 值（例 1）或 ≥1 条 trace 读取路径（例 2/3），且含 `<!-- mw-mechanical: 上下文来源 v1 -->`；
   - trace 含 `[FLOW] mechanical-backfill section=上下文来源`。
5. 失败回退用例（3 条，各 1 例）：无可判产物文件 / basename 越界 / `appendFileSync` 抛错（mock `fs`）⇒ 断言 `exit=2` + trace 行。

夹具落点建议：与 `mwds-t04-deliverable.test.ts:42` 的既有做法一致——测试**从 `.agenticdoc/...` 读源字节**、写进临时目录执行；不复制进 `test/fixtures/`（避免大文件入库）。

### 5.3 AC-001 / AC-002 / AC-003 / AC-004 / AC-015 的测试落点

| AC | 文件 | 夹具/形态 |
|---|---|---|
| AC-001 | `test/suite/output-recovery-contract.test.ts`（扩 `checkRecovery (AC-003)` describe，`:92-143`） | §0.2 的 16 例内联字符串；保留 `:99`/`:103`/`:110`/`:116`/`:126`/`:132`/`:136` 既有 7 例 |
| AC-002 | 同文件 `writeOutput recovery enforcement`（`:145-222`）+ settle describe（`:224-300`）；`dispatch-recovery-terminal.test.ts`（`:160-180`） | 对每个失败矩阵例，断言 `readOutputSection(taskDir,"Questions")` 首行**恰好** `缺失段：<missing.join("、")>`（不多不少）；settle 级断言 `exit=2` 例数 == 期望表例数 |
| AC-003 | `packages/multi-workers/test_autopilot_dispatch.py` / `test_mwds_t13_producer_paralysis.py`（Python 生产者）；`packages/coding-agent/test/suite/dispatch-card-injection.test.ts`（TS 生产者） | 渲染后断言含 `## 交付段契约（本角色）` 且逐字含 `- \`## <name>\`` 列表（coding/research/review 各 1）；再加 1 例「card=None 渲染字节不变」 |
| AC-004 | `output-recovery-contract.test.ts` 新 describe（复用 `:230-256` 的 `startWorker/settle`） | 需扩 harness：`fakeWorkerPi().sendUserMessage` 目前是 no-op（`:236`），改为**记录调用**以断言自检文本与 `deliverAs`；首轮 settle → 断言 trace 行 + `run.json` 不存在（未落终态）；把缺段标题写进产物 → 二次 settle → `exit=0` |
| AC-005 | `dispatch-recovery-terminal.test.ts` 新 describe（或新文件 `test/suite/woc-t0x-output-contract-replay.test.ts`） | §5.2 配方；源字节锚 `.agenticdoc`（同 `mwds-t04-deliverable.test.ts:42` 模式） |
| AC-015 | `dispatch-recovery-terminal.test.ts` 新 describe | 3 例：(a) 只有 `report-<slug>.md` 非空（模板 `output.md` + 真报告）⇒ 受判文本是该 slug 文件；(b) `report.md` 与 `report-<slug>.md` 并存 ⇒ `report.md` 胜（锁定既有优先级）；(c) 只写 `report-<slug>.md` 的 **coding** 型仍被判（覆盖 §2.3 第 2 条 `reportProduct`） |
| AC-014 | `worker/output-sections.ts:19-20` 注释 + `.agenticdoc/_framework-reflect.md` FW-001 修法 5 | 逐字核对（本报告不执行） |

## 6. 影响面

### 6.1 现有 fixture：**至少 3 处需要改**（修正 RQ-1 的「0 翻转」）

RQ-1 的「0 个既有用例翻转」对**纯谓词**成立（`checkRecovery` 的 7 例 fixture 全是真标题），但**settle 级与 writer 级**有翻转：

| # | 用例 | 现状断言 | 改动后 |
|---|---|---|---|
| 1 | `test/suite/dispatch-recovery-terminal.test.ts:162` `a delivered but incomplete report flips done → needs-clarification` | reply = `MISSING_CONTEXT_SOURCES`（只缺 `上下文来源`），2 次 `expect` 于 `:173-176` | **翻转**：S3 自动补齐 ⇒ `exit=0` / `status="done"`。用例必须改指「非机械缺段」（如删 `残留与未验证`），或改写为 AC-005 的正例 |
| 2 | `test/suite/output-recovery-contract.test.ts:282` `missing section => needs-clarification…` | `INCOMPLETE_REPORT`（缺 `证据`+`残留与未验证`），单次 `settle()` 后读 `run.json` | **破坏**：S2 自检会先发一回合，`taskDone` 仍 false ⇒ `run.json` 不存在（`readRun` 抛错）。必须改成两次 settle |
| 3 | `test/suite/output-recovery-contract.test.ts:186` `done path with gaps: …` | `writeOutput` 直调 + `MISSING_CONTEXT_SOURCES` ⇒ 期望 `## Recovery Gaps` 含 `缺失段：上下文来源` | **翻转**：若 `writeOutput` 直调路径也接 S3（§3.2 要求的同源），该用例改为断言「无 Recovery Gaps + 文件含 `## 上下文来源`」；若只做 settle 路径则此例保持——但会出现两条路径判定不一致 |
| 4 | `test/extensions/agent-team-loop.test.ts:494` `exit 2 writes Questions` | 走 harness 模板，缺 base 4 全部 | 不翻转（该例不经过真实 `checkRecovery` 的完整链） |
| 5 | `mwgal-t17*` / `mwds-t23` / `mwds-t21` / `mwds-t04` | 全部 `judgeRecovery:false` 或走交付 oracle | 不翻转 |

另外**夹具层面**的新约束：AC-005 的 3 个重放测试必须复制到临时目录再跑（S3 会 append，原地跑等于改仓库语料）。

### 6.2 新增矩阵用例的最小集合

1. **AC-001 判定矩阵**：16 例（§0.2），单 describe、纯函数、零 I/O。
2. **AC-002 回读准确性**：4 例（缺 1 / 缺 2 / 缺 4 / 只正文）断言 `## Questions` 首行段名集合恰好等于 `missing`。
3. **AC-015 候选集**：3 例（§5.3）。
4. **AC-004 自检**：2 例（触发一次并补齐→0；忽略自检→按缺段 2，且自检不重复触发）。
5. **AC-005 重放 + 回退**：3 + 3 例。
6. **归一化边界**：6 例（围栏 / 三层 / 缩进 3 / 缩进 4 / 收尾串 / 标题内子串）——可与 1 合并。
7. **S3 幂等**：2 例（同文件二次调用只留一块；`output.md` 已有 harness block 时仍正确追加）。
8. **parity**：1 例（`isReportProductName` 三处一致 + `WORKER_FILE_NAME_RE` 同源），1 例（Python/TS 清单段表一致）。

合计最小 ≈ **38 例**，全部落在 `packages/coding-agent/test/suite/` 与 `packages/multi-workers/test_*.py`。

### 6.3 生产者侧 byte-golden 风险（AC-003 的连带面）

`_envelope_card_body` 加段会改真实 dispatch 的 `task.md` 字节。风险面：

- **安全**（保持字节行为）：`test_autopilot_readcap_injection.py:940-975` 的 frozen-copy 对比用 `BASE_KWARGS`（无 `card`）⇒ 门控在 `card is not None` 即不破。
- **需检查/更新的断言**：`test_mwds_t13_producer_paralysis.py:259/317/400/421`（遍历 `PRODUCER_EXTRA_ITEMS` 断言 in-text）、`test_mwds_t29_producer_signal.py:155/586`、`test_autopilot_dispatch.py:118/141`、`test_write_face_dispatch.py:173`、`test_rag_phase.py:33-70`、`test_autopilot_attribution.py:289`。这些多为 `in text` / 参数形状断言，加段通常不破；但**实现期必须跑 `test_autopilot_*` 定向套件**确认（本卡只读，未跑）。
- 另需 1 条新金标：`card` 存在时渲染结果含清单段（正向），`card=None` 字节不变（反向）。

### 6.4 语料处置口径（AC-010(c) 可执行化）

`mw_auth.py`（H2-only，437 target，相对旧整篇别名判据 116 例翻转）逐类归因：

| 缺失集形态 | 例数 | 处置 |
|---|---|---|
| `[上下文来源]`（仅机械段） | 6 | **S3 直接救回** |
| 含 `上下文来源` 且另有真实段 | 78 | S3 + S2 一回合（agent 自补真实段） |
| 不含 `上下文来源` | 32 | **S3 无效**，只能 S2；若 agent 不补 ⇒ 真 exit=2（这是契约想要的结果） |

⇒ AC-010(b)「新产物全通过」在机理上等价于「S2 自检在被采纳时总能补齐真实段」，因此 **AC-010(b) 的分母必须写明「自检被采纳并被 agent 补齐」**，不能把它当成判据自动成立的推论。同时（H2+H3 变体：116 → 112 例、S3-alone 6 → 8 例）不改变上述结构。

### 6.5 其他连带面

- `writeOutputGuarded` 的失败路径（`:2093`/`:2490`/`:2862`）未传 `terminalGaps` ⇒ 会走 `output-writer.ts:257-259` 的默认判据。若在那里也接 S3，失败 run 的 `output.md` 会多一块机械段（exit=1 口径不变）。建议一并接入以消除双路径语义差，代价是 §6.1 第 3 条要改。
- `pm/ui-bridge.ts:585-611 readTerminalDetail` 读的是 harness 段名（`TL;DR`/`Summary`/`Questions`/`Exit Reason`），与契约段名不同源 ⇒ S1/S3 不触碰读侧，零回归（RQ-1 §5/#9、§6.1 已确证）。

## 7. 需 PM 决策项（实现前必须定）

| # | 决策 | 推荐 | 备选与代价 |
|---|---|---|---|
| D1 | 标题层级：`##` only，还是 `##`+`###` | **`##` only**（与读侧一致） | 放宽到 `###`：pass 36→41、S3-alone 6→8，但判据口径超过读侧口径（FD-005 第二形态） |
| D2 | S3 白名单是否含 coding 型额外段 | **否（v1 只 `上下文来源`）** | 含则须等 AC-017 后，且要用「账本可信」证明，否则掩盖真实缺口（R2） |
| D3 | AC-005 的「3 例」用哪种读法 | **R-a（机械补录前）+ 事实前提放宽为「≥1 类事实」** | 坚持字面 card 前提 ⇒ `##`-only 只有 1 例；要 3 例需放宽到 H1（与 D1 冲突） |
| D4 | S2 自检是否也覆盖「账本缺口」 | **否**（只覆盖恢复段缺口） | 覆盖会让 `dispatch-recovery-terminal.test.ts:247/290` 等账本用例多一个回合 |
| D5 | `writeOutput` 直调路径是否接 S3 | **是**（消双路径语义差） | 否则 `output-recovery-contract.test.ts:186` 保持但两条路径判定不一致 |
| D6 | AC-003 注入到 `task.md` 是否要重冻结 golden | **只门控在 `card is not None`** | 若无条件注入，`test_autopilot_readcap_injection.py` 的 frozen-copy 对比全线变红 |

## 残留与未验证

1. **未跑任何测试**。§6.1 的翻转清单是**静态判据**（fixture 文本 + 代码路径 + 期望断言逐行读出来），不是运行结果；真正的确认要在实现期跑 `output-recovery-contract.test.ts`、`dispatch-recovery-terminal.test.ts` 与 `packages/multi-workers` 的 `test_autopilot_*` 定向套件（P-032：禁全量 `./test.sh`）。
2. **未验证 §6.3 的生产者 golden 面**：`test_autopilot_*` 里哪些是 `in text`、哪些是字节相等**未逐条核**（只核到 frozen-copy 对比用的是 `BASE_KWARGS` 无 `card`）。
3. **未验证 `###`/`##`/`#` 三种层级在「新产物」上的真实分布**：语料统计全部来自「旧契约不要求标题」年代，按 spec §4 R1 不得当判据；本报告只用它做**方向性**论证（不做/做某规则的增益量级）。
4. **未验证 AC-015 的 mtime tie-break 在测试中的稳定性**：同毫秒内写入多个 slug 文件时靠名称升序，理论上确定；未做实测。
5. **未做 AC-005 重放的实跑**：§5.2 的 3 例是本轮只读统计筛出的**候选**，其 `card_path` / trace 读取条目数已实测，但「S3 生成内容含 card 路径」这一步未运行验证（那需要实现后的代码）。
6. **`report.md` 之外的第二部入口未穷举**：本报告核到 `agentProductText` 与 `reportProduct` 两处；`collectArtifacts`（`run-store.ts:119`）不列 `report-<slug>.md`（`deliverable-evidence.ts:104` 注释明写 design R3），是否要在 `## Deliverables` 里体现 slug 报告**未提案**（超出本卡范围）。
7. **并发影响**：本轮测量期间有并行 worker 在写 `.agenticdoc`，受判 target 从 433（RQ-1 口径）漂到 437；所有比例结论对该漂移不敏感，但精确计数不可复现到个位。

## 证据

**实跑命令与脚本**（全部只读；脚本落在 `%TEMP%`，未写入仓库）：

| 脚本 | 作用 | 关键输出 |
|---|---|---|
| `%TEMP%\mw_inst.py` | 6 个历史实例盘上复核（文件清单/大小/mtime、`run.json`、H1–H6 标题、补录标记） | QG/W-12/W-15 的真实报告是 `report-<slug>.md`（23,252 / 37,149 / 30,257 B）；`wfg-rq2/rq3/d2` 的 `report.md` mtime 晚于 `run.json`（PM 补录） |
| `%TEMP%\mw_judge.py` | 从 TS 源解析别名表（45 条）后对 6 例算「整篇别名 / 只认标题 × 补录前/后」 | `wjg-w15` 报告文件新缺失仅 `[残留与未验证]`；`wfg-rq*` 判前 `report.md` 不存在 |
| `%TEMP%\mw_scan_bf.py` / `mw_scan_bf2.py` | 全语料「补录标题」扫描（前缀重放可行性） | 带补录标题的文件 7 个；**前缀缺失集 == `[上下文来源]` 的 0 个** |
| `%TEMP%\mw_judged.py` | 受判 target 清点 + 新旧判据对照 | 433 target；旧 150 通过、新 37 通过 |
| `%TEMP%\mw_auth.py` | **权威一次跑**（H2 / H2+H3，含 3 个 S3 相关数） | `H2: pass=37/437 flips=116 (含 ctx 84 / 不含 ctx 32 / S3 单独救回 6) pool=10`；`H2+H3: pass=41/437 flips=112 (80/32/8) pool=13`；pool 中带 card 事实者仅 `mdc-rq1`（H2） |
| `%TEMP%\mw_norm.py` | 归一化收益度量 | 缩进标题 88 行、收尾 `#` 0 行、围栏内 `## ` 13 行；`###` 增益 38 target；**标点增益 0** |
| `%TEMP%\mw_cand2.py` | AC-015 候选集影响 | 携带 `report-<slug>.md` 的 target **33**；受判文件变化 **13**（含 QG/W-12/W-15） |
| `%TEMP%\mw_pool.py` / `mw_pool2.py` | AC-005 池的逐例细节（`run.json`、card 头、trace 读取数、标题层级） | 3 例字面 card 事实出现在「接受 H1」的池中（`mdc-rq1`/`mdc-rq2`/`wfg-rq-d1`）；H2-only 下只剩 `mdc-rq1` |
| `%TEMP%\mw_facts.py` | `task.md` 事实齐备率 | 449 个 worker 目录中 `card_path:` **98**、`card_path`+`card_sha256` **97**、`envelope_producer:` **98** |

**源码判据（`文件:行` + 原文片段）**：

- `worker/output-sections.ts:30` `export const RECOVERY_SECTIONS = ["结论", "证据", "残留与未验证", "上下文来源"] as const;`
- `worker/output-sections.ts:46-53` 别名表 6 组 45 条（`结论: ["结论","tldr",…]` …）
- `worker/output-sections.ts:63-64` `function containsAlias(haystack, aliases) { return aliases.some((alias) => haystack.includes(alias.toLowerCase())); }`
- `worker/output-sections.ts:89-90` `const haystack = text.toLowerCase();` / `const missing = required.filter((name) => !containsAlias(haystack, …));`
- `worker/output-writer.ts:140-147` `function agentProductText(dir, summary) { for (const name of ["report.md", "output.md"]) { … } return summary; }`
- `worker/output-writer.ts:203` `const missingSections = opts.judgeRecovery === false ? [] : checkRecovery(productText, type).missing;`
- `worker/output-writer.ts:257-259` `opts.terminalGaps ?? readTerminalGaps({ taskKey: opts.taskKey, agenticdocRoot: opts.agenticdocRoot, summary: opts.summary });`
- `worker/output-writer.ts:320` / `:351` `sections.push(\`## TL;DR\n\n…\`)` / `if (gapNote) sections.push(\`## Recovery Gaps\n\n${gapNote}\`);`
- `worker/output-writer.ts:370-371` `const existing = readFileSafe(outputPath); fs.writeFileSync(outputPath, existing.trim() === "" ? body : \`${existing.trimEnd()}\n\n---\n\n${body}\`, "utf8");`
- `worker/worker-mode.ts:2707` `function finishSuccess(): void {`；`:2712` `taskDone = true;`；`:2720-2722` `hasDeliverableEvidence(...)`；`:2733-2738` `let reportProduct = false; try { reportProduct = fs.statSync(path.join(taskDir, "report.md")).size > 0; } catch { … }`；`:2740` `const gaps = readTerminalGaps({`；`:2746` `const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;`；`:2761` `writeOutputGuarded({`
- `worker/worker-mode.ts:2806` `pi.on("agent_settled", () => {`；`:2827` `finishSuccess();`（无 phase 分支）；`:2859` `finishSuccess();`（全部 phase 完成）
- `worker/worker-mode.ts:2550-2564` `pi.sendUserMessage(checkpointSteerText({…}), { deliverAs: "followUp" });`（自检复用的模式）
- `worker/worker-mode.ts:2695-2701` `function writesLabel() … /^report-.+\.md$/.test(b)`（框架已把 `report-<slug>` 当 report）
- `worker/worker-mode.ts:2363` `appendTool(meta.taskKey, meta.agenticdocRoot, event.toolName, target);`（`[TOOL] read <path>` 来源）
- `shared/deliverable-evidence.ts:15` `*   1. \`report.md\` / \`report-<slug>.md\` non-empty ⇒ delivered (\`channel=report\`);`；`:105-119` `findNonEmptyReport()` 用 `WORKER_FILE_NAME_RE`
- `worker/worker-file-tool.ts:42` `export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;`
- `pm/ui-bridge.ts:1707-1718` `judgeWriteTarget` 用 `WORKER_FILE_NAME_RE`；`:1961-1975` `renderCardSeedSections`；`:2150-2180` `writeDispatchTaskMd`
- `shared/output-sections.ts:71` `const SECTION_SPLIT_RE = /##\s+(.+?)\s*\n+([\s\S]*?)(?=\n##\s|$)/g;`
- `shared/change-ledger.ts:190-207` `LEDGER_SECTION_ALIASES`（宽档，含 `改动`/`变更`）；`:208-217` `WRITELESS_LEDGER_ALIASES`（窄档）；`:352-366` `extractLedgerBody`；`:493-521` `collectWritelessDeclarations`（deliverable 目录新鲜度）
- `shared/task-frontmatter.ts:117` `export function readTaskHeaderScalar(text, key)`
- `shared/run-store.ts:119` `export function collectArtifacts(taskDir)`
- `packages/multi-workers/autopilot/dispatch.py:371-377` `_DEFAULT_DELIVERABLES`；`:418-422` `PRODUCER_EXTRA_ITEMS`；`:602-650` `_envelope_card_body`；`:755+` `render_task_md`
- `packages/multi-workers/launcher.py:1315-1334` `_starter_prompt`（正文不走 argv）；`:796-816` `has_canonical_envelope`；`:870-895` `_envelope_enforced`（mtime 分支）
- `packages/coding-agent/test/suite/output-recovery-contract.test.ts:136-139` CRLF 等价断言；`:186-200` 「done path with gaps」；`:270-300` settle 两例
- `packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts:160-180` 「incomplete flips」；`:204-216` migration 不判；`:391-407` `readTerminalGaps is the single verdict`
- `packages/coding-agent/test/suite/mwds-t04-deliverable.test.ts:42` 语料锚 `.agenticdoc/.../workers/`；`:153-166` channel order
- `packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts:573-583` `WORKER_FILE_NAME_RE.test("report-adversarial.md")`

## 未覆盖面声明

1. **未跑测试**（vitest / pytest / `npm run check` / `./test.sh` / `npm run build` / `npm install` 全部未跑），§6.1 的翻转清单是静态判据。
2. **未覆盖 settle 当时的逐字节受判文本**：对 `wfg-rq2/rq3/d2` 等 review/research 型，settle 时受判文本是 settle 摘要（`output.md` 当时不存在、`report.md` 由 PM 事后补录），盘上无从复原；本报告用「受判对象语料口径」（AC-010 口径）代替，并已逐处标注。
3. **未覆盖 `dist/` 分发产物**：所有坐标均为 `src/`；`dist` 与 `src` 是否同版本未核。
4. **未覆盖 `mw doctor` / `mw serve` / RAG 审计 CLI 对 `output.md` 契约段的读取**（RQ-1 已指出这些面与恢复契约无关，本报告沿用其结论、未独立复核）。
5. **未覆盖「自检回合被 agent 忽略/prompt 无效」的实际发生率**：AC-010(b) 的「新产物全通过」依赖这一点，本报告只给出机理与分母定义，未做样本。
6. **未覆盖 Python 侧 `PRODUCER_EXTRA_ITEMS` 与 TS `renderCardSeedSections` 的既有 parity 测试**具体断言内容（只读到存在 parity 锁，未逐行读该测试）。
7. **未覆盖 `before_agent_start` 里 `sendUserMessage` 的时序可行性**：本设计刻意不走这条（清单走生产者、只审计），但未实测「worker 侧早期注入提示」是否可行（§4.2 只用它做审计 + trace）。

## 上下文来源

- 卡：`.agenticdoc/mw-worker-output-contract/tasks/T-DR2-contract-judgment.md`（card_sha256 `3964acdf131939a0c0fc422eed5accf8d184103bb03aeafaa1f64f82461b6d59`）
- 规格：`.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P1、§1.6 S1/S2/S3、§3 AC-001…AC-005 / AC-010 / AC-014 / AC-015、§4 R1/R2、§5 P-001/P-026/P-028/P-030/P-031/P-032）
- SPEC 阶段证据（必读并已核）：`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq1-contract-corpus-20261014.md`
- 台账：`.agenticdoc/_framework-reflect.md` FW-001（6 次实例）
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/{worker/output-sections.ts, worker/output-writer.ts, worker/worker-mode.ts, worker/worker-file-tool.ts, shared/output-sections.ts, shared/deliverable-evidence.ts, shared/change-ledger.ts, shared/task-frontmatter.ts, shared/run-store.ts, pm/ui-bridge.ts}`；`packages/multi-workers/{launcher.py, autopilot/dispatch.py}`
- 测试：`packages/coding-agent/test/suite/{output-recovery-contract, dispatch-recovery-terminal, mwds-t02-write-intent, mwds-t04-deliverable, mwds-t05-output-sections, mwds-t12-regression}.test.ts`、`packages/coding-agent/test/extensions/{agent-team-loop, agent-team-loop-worker-file-tool}.test.ts`、`packages/multi-workers/{test_autopilot_readcap_injection, test_mwds_t13_producer_paralysis, test_mwds_t29_producer_signal, test_autopilot_dispatch, test_write_face_dispatch, test_rag_phase}.py`
- 历史实例（只读复核）：`mw-worktree-junction-guard/workers/{wjg-qg-evidence-closure, wjg-w12-negative-space-audit, wjg-w15-delta-adversarial}`、`mw-write-face-guard/workers/{wfg-rq2-enforcement, wfg-rq3-safety, wfg-rq-d2-runtime-guard, wfg-rq-d1-glob-intersection}`、`mw-dynamic-concurrency/workers/{mdc-rq1-dispatch-chain, mdc-rq2-dependency-sources}`、`mw-guard-form-hardening/workers/{mwgf-rq3-path-resolution, mwgf-drq3-role-key-design, mwgf-drq2-target-axis-design, mwgf-qga3-final-adversarial}`、`mw-dispatch-settle-gates/workers/mds-qg-b-code-adversarial`
- 本轮只读脚本（**不在仓库内**，位于 `%TEMP%`）：`mw_inst.py`、`mw_judge.py`、`mw_scan_bf.py`、`mw_scan_bf2.py`、`mw_judged.py`、`mw_auth.py`、`mw_norm.py`、`mw_cand2.py`、`mw_pool.py`、`mw_pool2.py`、`mw_facts.py`

[VERIFY] counts: judged_targets=437 report_slug_targets=33 ac015_product_changes=13 h2_pass=37 h2_h3_pass=41 flips_vs_old_alias_h2=116 flips_with_ctx=84 flips_without_ctx=32 s3_alone_rescue_h2=6 s3_alone_rescue_h23=8 ac005_pool_h2=10 ac005_pool_h2_with_card_facts=1 ac005_pool_h1h2_with_card_facts=3 backfill_heading_files=7 backfill_prefix_missing_only_ctx=0 indented_heading_lines=88 fenced_h2_lines=13 trailing_hash_closers=0 h3_gain_targets=38 punct_gain_targets=0 worker_dirs=449 card_path_dirs=98 envelope_producer_dirs=98 spec_fixture_flips=0 settle_fixture_flips=3 aliases=45 sections=6
