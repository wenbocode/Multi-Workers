# T-RQ1: 契约判定全貌与历史语料统计入口（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「agent-team-loop 扩展：PM 编排 + Worker 执行」「文件驱动的去中心化协调」）。
- 本 key 的 spec：`.agenticdoc/mw-worker-output-contract/spec.md` —— 相关条目 §1.5 P1/P3、§1.6 S1/S2/S3、§3 AC-001…AC-005、AC-010。
- 已知起点坐标（**只是起点，不得以此为界**）：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:1`（`RECOVERY_SECTIONS` / `RECOVERY_SECTIONS` 型别表 / `RECOVERY_SECTION_ALIASES` / `containsAlias`）、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2745`（`exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2`）、同文件 `:2776`（`questions: recovery-incomplete: …`）。
- 背景事实（已由 PM 复核，不要再重复发现）：`output.md` 的段契约判定是对**整篇文本**做别名子串匹配（词汇 fail-open、结论 fail-closed），判定发生在 settle **之后**；已 6 次把实质完成的 review/research worker 判成 `needs-clarification`（本仓 `wjg-qg-evidence-closure` / `wjg-w12-negative-space-audit`（五段全缺）/ `wjg-w15-delta-adversarial`；另一 key `wfg-rq2-enforcement` / `wfg-rq3-safety` / `wfg-rq-d2-runtime-guard`），单批 3/5，且两个窗口的 PM 都只能靠 byte-pure 补录兜底。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`（本机无墙钟超时，实测挂死 7h14m）。

## 要求

1. **判定链全貌**：从 `output.md` 文本产生到 `exitCode` 决定的完整调用链——谁调用判定、`gaps` 在何处计算、`gaps.ok` / `gapsReason` 如何生成、`exitCode = 2` 之后谁消费。逐条给 `文件:行号` + 原文片段。
2. **契约段与别名表的完整当前值**：`RECOVERY_SECTIONS`、各 type 的额外段（如 review 的 `未覆盖面声明`）、`RECOVERY_SECTION_ALIASES` 全文（逐字），以及匹配算法的确切语义（是否大小写不敏感、是否去空白、是否只看标题、`haystack` 是整篇还是分段）。
3. **历史语料统计入口（AC-010 的关键）**：找出 `_framework-reflect.md` FW-001 提到的语料统计 **99.4% / 87.2%** 的实现位置（脚本 / 测试 / fixture / 注释）、可复跑命令、语料来源与份数。若确实不存在，写「不存在（检索命令 + 输出）」，并列出仓库内**现成可用的 `output.md` 语料**（路径 + 份数 + 各自标题结构），作为 AC-010 降级方案的输入。
4. **澄清模板的来源**：`## TL;DR` / `## Summary` / `## Questions` / `## Recovery Gaps` 这套模板在何处生成、什么条件下走这条路径、它与契约段名是否有映射关系。
5. **`output.md` 的全部消费者**：谁读它、按什么结构读、读到缺段时的行为（PM 回读、widget、结果吸收、其他）。逐条 `文件:行号`。
6. **现有测试清单**：与契约判定 / 段名 / 别名 / settle 出口相关的测试文件与用例名（vitest 的 `packages/coding-agent/test/**` 与 pytest 的 `packages/multi-workers/test_*.py` 都要查），并指出哪些用例会在「判定改按标题结构」后翻转。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq1-contract-corpus-20261014.md`

用 `bash` + Python heredoc 直接写该路径（框架写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md`，作为 PM 回读兜底。

## 交付格式

- `## 0. 结论先行`（≤6 条，直接可引用）→ `## 1…N` 逐问作答 → `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据必须 `文件:行号` + 原文片段；计数与检索给出**实测命令 + 输出**；未找到写「未找到（命令 + 输出）」，**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`（实测计数）。
- 明确写出你使用的工具与**方法边界**（静态检索 / 是否实跑）、以及你**没**覆盖的面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。框架对 `output.md` 的契约判定按整篇别名子串，历史上已有 6 次因缺段被判 needs-clarification；写全可避免本任务被误判（否则只能由 PM 补录，浪费一轮）。
