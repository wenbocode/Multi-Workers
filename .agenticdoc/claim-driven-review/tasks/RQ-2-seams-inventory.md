# RQ-2: 四个接缝的最小改动点盘点（research）

- Key: claim-driven-review
- type: research
- 写面：只读仓库；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「不修改 pi 核心：所有功能通过 Extension API」「文件驱动的去中心化协调」）。
- 本 key 的需求（用户已定，**不要重新讨论**）：review 卡的断言集 → 派发期校验 → 结算期覆盖判据 → 预算承载 → 度量。本卡只做**接缝盘点**（改哪里、被什么测试锁住），不写实现。
- PM 已确认的落点（作为起点，需你逐处核实行号并补细节）：
  - 派发卡校验：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:150-270`（envelope hints / `TYPE_EXTRA_SECTIONS` / `TYPE_EXTRA_PATTERNS` / `typeExtrasMissing`）。
  - 结算恢复契约：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:48-210`（`RECOVERY_SECTIONS`、`RECOVERY_TYPE_SECTIONS`、`checkRecovery`）。
  - 读面预算：`packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:31-210`、`:254-275`（`readScopeConfigFromMeta`：`read_scope` 与 `deny_globs` 都缺 → 拦截整体关闭）。
  - Python 侧渲染：`packages/multi-workers/autopilot/dispatch.py:224-270`（`_read_scope_caps`）、`:1436-1450`（`requires_read_scope` 强制）、`:977-987`（`read_scope`/`deny_globs` 渲染）。
  - 平价锁：`packages/multi-workers/test_autopilot_l0.py:234-263`、`packages/multi-workers/test_autopilot_dispatch.py:31-68`。
- 已知缺口（需你确认并给出精确行号）：PM 手工派发 `dispatch_worker` **没有** `read_scope`/`deny_globs`/caps 参数。

## 要求

1. **卡校验链**：`dispatch_worker` 从参数到落盘 `task.md` 的完整调用链（函数名 + `文件:行号`），以及卡 gate 在哪一层触发（工具层 / 服务层）。指出"新增一个 claims 块校验"的最小插入点，并说明在该点能否 stat 目标文件尺寸（AC-001 第③条判据需要）。给出拒绝形态的既有实现（拒绝码 + 文案 + 零副作用断言在哪个测试里）。
2. **结算链**：`finishSuccess()` 的判定顺序（`hasDeliverableEvidence`、`judgeRecoveryHere`、`checkRecovery`、`recovery-gap` steer、exit 2 映射），每步 `文件:行号`。指出"新增断言覆盖判据"应放在哪一步之前/之后，以及一次性 self-check 的状态变量是什么（避免无限补写）。
3. **预算承载**：`checkReadScopeCall` 的计费口径（`allowedCalls` 数的是调用次数还是去重文件数；哪些工具计字节），`readScopeConfigFromMeta` 的激活条件，以及 conductor 与 PM 两条通道各自怎么设置 caps。给出"由 claim 数量推导 caps"需要改的具体函数与调用点（两侧）。**明确回答：给 PM 手工派发加 `read_scope` 参数要动哪几个文件、会不会破 T-17 平价锁。**
4. **类型与词汇表**：若要新增一个 `claim-review` 类型，需要同时改哪些文件（TS `TOOL_ALLOWLISTS`、Python `REGISTRY`、`DISPATCH_TYPE_VOCABULARY`、`REGISTERED_WORKER_TYPES` 断言、平价测试），逐项给 `文件:行号` 与"漏改会红哪条测试"。若判断**不需要**新类型（复用 `review`），给出理由与替代落点。
5. **度量接缝**：`status-model.ts` 的面板字段来源、`usage.py` 的聚合入口、`pm status` 输出构造点，各自 `文件:行号`；指出新增 `claims/closed/partial/unverified/fetches/tokens_per_closed_claim` 应落在哪个结构体、是否要动 dist/bundle（本仓 `dist/` 是否为 tracked 产物）。
6. **破坏面清单**：对第 1–5 步每个改动，列出会被影响的既有测试文件与断言（点名 `文件:行号`），并标注"必红需更新"与"不应红（红了说明设计错）"两类。

## 写入允许面

- `.agenticdoc/claim-driven-review/evidence/research/spec-rq2-seams-20261020.md`

## 唯一证据文件

`.agenticdoc/claim-driven-review/evidence/research/spec-rq2-seams-20261020.md`

用 `bash` + Python 直接写该路径（写面允许 `<key>/evidence/**`）；同时在本任务目录用 `worker_file` 写同内容 `report.md`。**不得写其它任何文件**。

## 交付格式

- `## 0. 结论先行`（≤6 条：每层一个"最小插入点 + 破坏面"）→ `## 1…6` 逐问作答 → `## 接缝表`（层 / 文件:行号 / 函数 / 改动形态 / 锁定测试）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段。未找到写「未找到（命令 + 输出）」，禁止推测补齐。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest。临时文件放 `%TEMP%`。
