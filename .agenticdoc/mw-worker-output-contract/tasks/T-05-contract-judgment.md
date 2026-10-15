# T-05 · 契约判定（H2 标题档）+ 受判候选集 + 机械段自动补齐（W2）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「项目级目标对齐」）——`exit=2` 是 PM 唯一能看见的产物质量信号；误判等于把合格产物判死。
- 现状（**已确证，不要重复发现**）：
  - 受判文本 = `agentProductText()`（`worker/output-writer.ts:140-147`）：**优先 `report.md`** → `output.md` → settle 回复，**不含 `report-<slug>.md`**。
  - 判定 = `checkRecovery`（`worker/output-sections.ts:87`）：整篇 `toLowerCase()` + `includes`，**标题不参与** ⇒ 框架自己在 `## Recovery Gaps` 里写「缺失段：上下文来源」会让 `上下文来源` 段被判为**已满足**（FW-001 的自证漏洞）。
  - 顺序：判定发生在唯一一次写出**之前** —— `readTerminalGaps`（`worker/worker-mode.ts:2740`）→ `exitCode`（`:2746`）→ `writeOutputGuarded`（`:2761`）。I2 补齐插入点 = `finishSuccess`（`:2713`）；I1 自检回合 = `agent_settled`（`:2811`）；`followUp` 复用点 = `worker/worker-mode.ts:2556`。
  - 候选集缺口：`worker/worker-mode.ts:2734-2738` 的 `reportProduct` 谓词只 `statSync(report.md)` ⇒ 不改则「只写 `report-<slug>.md`」的 write 角色**根本不被判**（本仓 `wjg-qg-evidence-closure` 即此形态）。
  - 语料：judged 433 份，整篇别名通过 145/433 = 33.5%，只认标题 35/433 = 8.1%，110 例 `alias_ok→heading_fail`。**不拿旧产物当验收对象**（R1）。
- 设计落点（`design.md` §4，逐字照办）：
  - **4.1 判定算法（H2 档）**：`haystack` = 每行匹配 ` {0,3}##(?!#)[ \t]+` 的标题文本（围栏代码块内与引用块内的 `#` 不计）；归一化 = 去收尾 `#` + trim + 内部空白折叠 + ASCII lower；命中 = 该标题文本 `includes` 该段任一别名（45 条别名逐字不变）；结论 fail-closed（缺段即缺段），词汇 fail-open（标题可用别名）。**正文彻底不参与**；**不做标点剥离**；**不取 `###`**。
  - **4.2 受判候选集（AC-015）**：顺序 `report.md` → `report-<slug>.md`（同层多文件按 mtime 降序）→ `output.md`；**必须同批改 `reportProduct` 第二入口**。
  - **4.3 机械段补齐（S3）**：I2 落点 = `:2739`（判定前），先把 `## 上下文来源` 追加到**判定将要读的那个文件**（即 4.2 选中的候选），再判定；**拒绝「只补 `output.md`」**；内容由框架已掌握事实生成（`task.md` 的 `card_path`/`card_sha256`、读工具事件汇总、写事件里的产物路径）；纯 append + 幂等标记；三类失败回退（文件不可写/候选不存在/追加后仍缺段）**一律 fail-closed**。
  - **4.4 S2 清单 + 自检**：清单 = `recoverySectionsFor(type)` 渲染成 `## 交付段契约（本角色）`，由生产者注入（Python 侧归 T-06，本卡负责 TS 侧 `pm/ui-bridge.ts::renderCardSeedSections`，门控 `card is not None`）；worker 侧**只审计不改 `task.md`**（改写会推高 mtime 撞 `launcher._envelope_enforced` 分支）。自检回合复用既有 `followUp` 模式，**每进程一次**。
- 风险 R2（**硬约束**）：自动补齐**只允许补机械段**；`## Questions` 与实质判断段一律不自动生成（写成不可越界的白名单）。
- 风险 R8（**预期内改动，不能算回归**）：settle 层**至少 3 处既有用例必须改** —— `test/suite/dispatch-recovery-terminal.test.ts`（单 settle 后变 `exit=0`）、`test/suite/output-recovery-contract.test.ts`（单次 settle 不再落终态）。这 3 处显式登记为「预期内」，其余任何新增红 ⇒ 停手上报。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅** settle 段 + 注册/清单渲染相关段）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（**仅** S2 清单渲染 `renderCardSeedSections`）
- `packages/coding-agent/test/suite/mwoc-w2-contract-judgment.test.ts`（新建）
- `packages/coding-agent/test/suite/output-recovery-contract.test.ts`（预期内改动）
- `packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts`（预期内改动）

## 写入禁止面

其余一切路径。特别地：`worker/worker-mode.ts` 的**抽取器/记账段**（T-02）与**检查点段**（T-04）只读；`shared/write-surface.ts`、`worker/worker-file-tool.ts`、`pm/ui-bridge.ts` 的 `judgeWriteTarget` 与 `applyWatchWidget`（T-01/T-03 写面）只读——**本卡只改 `ui-bridge.ts` 的 S2 清单渲染一处**，开工前若发现该文件正被第三方编辑，先停手上报；`shared/output-sections.ts`（`shared/` 版本）只读（判定实现是 `worker/output-sections.ts`）；`packages/multi-workers/**` 只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **判定算法**：严格按 §4.1；用 AC-001 的 **8 例单测矩阵**逐例断言（全 5 段标题 / 缺 1 / 缺 2 / 缺 5 / 仅正文含别名而无标题 / 标题用别名 / 标题重复 / 标题在引用块内），其中「仅正文含别名无标题」**判为缺失**。
2. **AC-002**：缺段时 settle 回读文本包含**全部**缺失段的**准确**名称；`exit=2` 例数等于期望表。
3. **AC-015 候选集**：按 §4.2 顺序实现；**同批改 `reportProduct` 第二入口**（两条路径必须一致，用测试锁住）；既有 `report.md`/`output.md` 优先级的 3 个用例不得回归。
4. **AC-005 自动补齐**：I2 位置正确（判定**之前**）、写进**判定将要读的文件**、纯 append、幂等、fail-closed；补齐内容含 card 路径与至少 1 条产物/读取来源；**重放池**取 `evidence/recovery-contract-flip-disposition-20261014.txt` 的 `class=mechanical-only` 8 例中的 **3 例**（`mdc-rq1-dispatch-chain`、`mwgf-drq2-target-axis-design`、`mwgf-drq3-role-key-design`、`mwgf-qga3-final-adversarial`、`mw-rag-t11-verify`、`mw-rag-t14-phase-axis`、`mwtp-final-fixes-3`、`mvr-rq5-awareness-surface` 里任取 3），断言 `exit=2 → exit=0`（3/3），输入 = 盘上现存文本（**从未被 PM 补录**，PM 已逐例复核）。
5. **AC-004**：settle 前 worker 收到一次结构化缺口（缺失段名列表或 `ok`）并在 `trace.log` 落一行**可解析**记录；「首轮缺 1 段、补齐后再 settle」的模拟用例最终 `exit=0`。
6. **I1 自检回合**：复用 `followUp` 模式，**每进程一次**；用测试证明只发一次。
7. **AC-003（TS 侧半边）**：`renderCardSeedSections` 注入 `## 交付段契约（本角色）`，门控 `card is not None`；与 T-06 的 Python 注入不重复（同节幂等）。**worker 侧不改 `task.md`**。
8. **AC-014**：`worker/output-sections.ts:19-20` 的误引注释改为引用真实出处（`mw-dispatch-card-gate` 的派发输入/卡片统计，含 `file:line`），或改述为「宽档的真实理由 = 旧契约不要求标题、历史产物不可作为判据」。`_framework-reflect.md` FW-001 的修法 5 已由 PM 更正，**核对两处一致**即可（该文件归 T-09 写面，本卡只读核对并在证据里写结论）。
9. **AC-010(a) 语料对照**：改动前后各统计「整篇别名通过率」与「标题别名通过率」（基线 145/433 = 33.5% 与 35/433 = 8.1%，n 已漂到 437），命令用 `evidence/scripts/recovery-contract-corpus-stats.py`，两数与命令落 `evidence/`。
10. **禁止拿旧产物当验收对象**；历史数字只作背景记录（R1）。
11. `git diff --stat` 收尾只应含允许面文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：8 例矩阵逐例判定表、3 例重放的 `exit=2 → 0` 原始输出、候选集优先级测试输出、幂等/fail-closed 输出、`followUp` 一次性的原始输出、语料前后对照两数与命令、预期内 3 处的原始结果与「非预期红 = 0」的声明。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w2-contract-judgment.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/output-recovery-contract.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-recovery-terminal.test.ts
node ../../node_modules/vitest/dist/cli.js --run <既有 output 判定相关套件，逐文件参数>
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

（HEAD 基线：`output-recovery` + `dispatch-terminal` **30/30 全绿**、`agent-team-loop` 196/197（`:6381` 既存红）。预期内改动 3 处单独登记，不能混进回归失败。）

## 改动历史

- 2026-10-14 spec 阶段 RQ-1：受判文本 = `agentProductText()`（优先 `report.md`）而非 `output.md`；AC-010 前提被推翻（99.4%/87.2% 属另一 key）；语料 433 份实测 33.5%/8.1%。新增 AC-014，重写 AC-010。
- design 阶段 DR2：给出 H2 档判定规格、候选集顺序与 `reportProduct` 第二入口、I2/I1 落点、S2 承载 32/116 例的量化依据、6 个历史实例在新判定下**仍 `exit=2`** 的诚实声明。
- 依赖：T-04（检查点）已落地 —— 本卡的 settle 段改动必须避开 T-04 刚改的检查点段。
