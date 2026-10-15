# T-DR6: 验证策略与测试矩阵设计（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「Worker 执行过程中追踪 goal 一致性」）与 `.agents/skills/agentic-task/references/workflow-quality-gate.md`。
- 本 key 的 spec（**已锁定**）：`.agenticdoc/mw-worker-output-contract/spec.md` —— 全部 **AC-001…AC-017**（尤其 AC-010 的 (a)(b)(c) 三条与 AC-017 的四段判据）、§4 R8（HEAD 既存红基线）。
- 已确证的现状（**设计前提**）：HEAD 既存红 —— `worker-file-tool` 7/9、`mwds-t02` 38/39（`git diff --quiet HEAD` = 0，非本次引入）；`change-ledger` + checkpoint 22/22、`mwds-t03` 63/63 全绿；相关 vitest 文件 12 个；pytest 侧无账本相关用例；本机**不能**跑全量 `./test.sh`（实测挂死 7h14m，无墙钟超时）；仓库有多窗口并行未提交改动（`pm/ui-bridge.ts` 等行号可能漂移）。
- spec 阶段研究证据（**必读**）：`evidence/research/spec-rq1-contract-corpus-20261014.md`、`spec-rq2-write-face-20261014.md`、`spec-rq3-ledger-20261014.md`、`spec-rq4-checkpoint-settle-20261014.md`、`spec-rq5-readback-push-20261014.md`。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`。你**可以**跑单个测试文件（`node ../../node_modules/vitest/dist/cli.js --run <file>`，从包根）来确认基线，但必须记录命令与输出。

## 要求

1. **AC → 测试矩阵**：把 AC-001…AC-017 逐条映射到「测试文件 / 夹具 / 断言要点 / 是否需要实跑」（可以合并到同一用例的明确标注）。
2. **基线红处理**：给出验收命令序列，使「HEAD 既存红」与「本次引入红」可区分（例如先 stash 不可用时的替代：记录用例名白名单 + `git stash` 禁用 ⇒ 说明用什么替代手段定位）。
3. **AC-010(b) 的可执行方案**：「本 key 交付后新跑的 ≥6 个 worker（覆盖 research/review/coding）受判产物全 `exit=0`」——怎么跑、怎么取产物、怎么避免自评偏差（不能用本 key 自己的结论当证据）。给出步骤与判据。
4. **AC-010(a) 的复跑脚本设计**：整篇别名 / 标题两档通过率统计（PM 已实测 145/433 = 33.5%、35/433 = 8.1%）应固化在何处（`evidence/` 下的脚本 + 输出），给可复跑命令。
5. **部署与生效验收序列**：从 bundle 重建（`mw build --install --allow-dirty`）到 serve 重启（**仅当无 running worker**）到 `mw doctor` 的验收命令，以及「每个已打开的 pi 窗口需要 `/reload`」这一人工步骤如何记录。
6. **回归锁清单**：列出改动**必须**保持通过的既有用例（含 `agent-team-loop.test.ts:2077`、`report.md` 优先级 3 例、worker-file-tool 既有 7 例），以及它们的验证命令。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq6-verification-matrix-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写同内容 `report.md`。

## 交付格式

- `## 0. 结论与矩阵` → `## 1…N` 逐问 → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；命令 + 输出；禁止推测补齐。
- 末尾一行 `[VERIFY] …`；写出方法边界（哪些实跑、哪些只静态读）与未覆盖面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
