# T-DR1: 写面通道设计（worker_file 放宽 + 派发期同源）（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「agent-team-loop 扩展：PM 编排 + Worker 执行」「文件驱动的去中心化协调」「工具白名单按任务类型」）。
- 本 key 的 spec（**已锁定**）：`.agenticdoc/mw-worker-output-contract/spec.md` —— 相关条目 §1.5 P2、§1.6 S4、§3 **AC-006 / AC-007 / AC-016**、§4 R7。
- 已确证的现状（**不要再重复发现**，直接作为设计前提）：`TOOL_ALLOWLISTS`（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:73`）11 键、其中 review/research/verifier/reviewer/rag-research 无 `write`/`edit`；`activeToolsForType`（同文件 `:145`）只为这些角色追加 `worker_file`；`worker-file-tool.ts:42` 的 `WORKER_FILE_NAME_RE` 只认 `progress.md|report.md|report-<slug>.md` 且强制落任务目录；运行期写面 `worker-mode.ts:1625`–`:1646` 允许 `taskDir + <key>/evidence`；**派发期** `pm/ui-bridge.ts:1707` 的 `judgeWriteTarget` 允许面只有「taskDir」+「无目录成分的白名单 basename」，**没有 evidence 面** ⇒ 同一路径两处判定相反（review 卡声明写 `evidence/*.md` 实测被判不可满足）。
- spec 阶段研究证据（**必读，含 34 项改动点清单 A1-A16 / B1-B6 / C1-C11 / D1**）：`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq2-write-face-20261014.md`。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`（本机实测挂死 7h14m，无墙钟超时）。

## 要求

1. 对 A1-A16 逐条给出**设计决策**（保留 / 改写 / 删除 / 合并），每条写：改哪个符号、什么语义、影响面（调用点）、风险。
2. **路径域语义定死**：`<key>` 是相对 project-root 还是相对 key 目录；`evidence/**` 的深度/扩展名限制；`../..`、其他 key、仓库源码的 fail-closed 判据；`write_scope:` 是否同时约束 `worker_file`（spec 列为 design 待定 A15）。
3. **`WORKER_FILE_NAME_RE` 的处置**：放宽 basename 白名单 vs 改为「路径域判定」；它被 `worker-file-tool.ts` 与 `pm/ui-bridge.ts` 两处共用，给出**单一真源**（同一常量/谓词）的具体接口设计。
4. **派发期与运行期同源**（AC-016）：`judgeWriteTarget` 与运行期写面共用谓词的最小改法；越界面仍 fail-closed；指出 `pm/ui-bridge.ts` 当前工作树相对 HEAD 有另一并行 session 的改动（行号可能漂移）⇒ 设计必须以**符号名**锚定而非行号。
5. **AC-006 / AC-007 / AC-016 的测试形态**：每个 AC 给出「用例文件 + 夹具 + 断言」草案；AC-007 需先判定「文案层级」（扩展可改面 vs pi 核心 `packages/agent/src/agent-loop.ts:611` 不可改面）。
6. 指出你认为**不应做**的改动（例如改 `TOOL_ALLOWLISTS` 会碰 parity 锁）并给理由。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq1-write-face-channel-20261014.md`

用 `bash` + Python heredoc 直接写该路径（框架写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。

## 交付格式

- `## 0. 结论与决策表` → `## 1…N` 逐问 → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；计数与检索给**实测命令 + 输出**；禁止推测补齐。
- 末尾一行 `[VERIFY] <数值> …`；写出方法边界（静态 / 是否实跑）与未覆盖面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`（历史上 6 次因缺段被判 needs-clarification）。
