# T-DR2: 输出契约判定与机械段自动补齐设计（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」「phase 门禁」）。
- 本 key 的 spec（**已锁定**）：`.agenticdoc/mw-worker-output-contract/spec.md` —— §1.5 P1、§1.6 S1/S2/S3、§3 **AC-001…AC-005 / AC-010 / AC-014 / AC-015**、§4 R1。
- 已确证的现状（**设计前提，不要重复发现**）：受判文本 = `agentProductText()`（`packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:140`：**优先 `report.md`** → `output.md` → settle 回复，**不含 `report-<slug>.md`**）；判定 = `checkRecovery`（`worker/output-sections.ts:87`，整篇 `toLowerCase()` + `includes`，标题不参与）；调用点 `worker/worker-mode.ts:2740` 与 `output-writer.ts:257`；`exitCode` 在 `worker-mode.ts:2746`，**判定早于唯一一次写出** `writeOutputGuarded`（`:2761`）；机械段补齐插入点 **I2 = `finishSuccess:2713`**、自检回合 **I1 = `agent_settled:2811`**。语料实测：judged 433 份，整篇别名通过 145/433 = 33.5%，只认标题 35/433 = 8.1%，110 例 `alias_ok→heading_fail`。
- spec 阶段研究证据（**必读**）：`evidence/research/spec-rq1-contract-corpus-20261014.md`（契约段/别名表全文、澄清模板来源、消费者、测试翻转面=0）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`。

## 要求

1. **新判定算法的精确规格**：标题识别的层级（`##` only 还是 `##`/`###`）、去空白/大小写/标点规则、别名集合是否沿用现表、正文别名是否彻底不参与；给出「通过/不通过」的判定表与 6 个历史实例（QG / W-12 / W-15 / wfg-rq2 / wfg-rq3 / wfg-rq-d2）在新算法下的预期结论。
2. **`report-<slug>.md` 候选集**（AC-015）：纳入方式与优先级（与 `report.md`/`output.md` 的相对顺序、多文件并存时的选择规则、mtime 还是固定优先级），并说明与 `worker_file` 白名单的**对齐方式**（纳入候选 vs 从白名单移除，二者取一并给理由）。
3. **机械段自动补齐（S3）**：`## 上下文来源` 的内容生成规则（可用事实：`task.md` 的 `card_path`/`card_sha256`、读写工具事件、产物路径）；**必须解决一个顺序矛盾**——判定在 `writeOutputGuarded` 之前，而补齐要出现在**最终落盘的受判文件**里（`report.md` 是 agent 写的文件，框架能否追加？只补 `output.md` 时如何满足「判定与产物一致」？）给出明确方案与失败回退。
4. **前置清单 + 收尾自检（S2）**：清单从哪来、何时注入（`before_agent_start`？）、自检在 I1 的形态（`followUp` 模式复用点）。
5. **AC-005 的 3 例重放方法**：如何用「补录前前缀」构造重放输入、断言 `exit=2 → 0`；以及 AC-001/AC-002/AC-003 的测试落点（哪个文件、什么夹具）。
6. **影响面**：现有 fixture 是否需要改（RQ-1 结论是「0 个既有用例翻转」）；新增矩阵用例的最小集合。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq2-contract-judgment-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写同内容 `report.md`。

## 交付格式

- `## 0. 结论与判定表` → `## 1…N` 逐问 → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；命令 + 输出；禁止推测补齐。
- 末尾一行 `[VERIFY] …`；写出方法边界与未覆盖面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
