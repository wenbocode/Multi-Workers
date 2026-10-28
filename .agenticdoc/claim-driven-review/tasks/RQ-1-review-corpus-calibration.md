# RQ-1: review 类 run 的成本语料标定（research）

- Key: claim-driven-review
- type: research
- 写面：只读仓库与本机数据；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「解决单 Agent 长上下文溢出和无法并行的问题」「文件驱动的去中心化协调」）。
- 本 key 的需求（用户已定，**不要重新讨论**）：把 review 从"读工程"改成"判断言"——成本与断言数量绑定。本卡只做**标定**：用历史语料算出预算常数，不做设计。
- PM 已实测的事实（**不要重复发现**，只在此基础上扩展）：
  - `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/trace.log`：236 次工具调用，`read` 159 次、`grep` 53、`find` 10、`ls` 10、`worker_file` 4；read 覆盖 66 个不同文件；该 run 死于 214k 上下文，三次 attempt 后 `[MODEL_FALLBACK]` 落到 `timi/glm-5.3`。
  - 同行热文件：`packages/multi-workers/mw.py` 401,562 B 被读 4 次；`worker-mode.ts` 213,426 B 读 5 次；`ui-bridge.ts` 184,357 B 读 3 次。
  - `packages/multi-workers/usage.py` 已实现"pi 会话 JSONL → 按 task/key 归因"的解析（mw-usage-monitor key 的沉淀），`packages/coding-agent/src/extensions/agent-team-loop/pm/status-model.ts:88-89` 有读预算字段的展示面。
  - 卡上给的默认读预算：`packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:31-32`（`DEFAULT_READ_FILE_CAP=8`、`DEFAULT_READ_BYTE_CAP=65536`），`packages/multi-workers/autopilot/config.py:95-96`（`l2_read_file_cap=8`、`l2_read_byte_cap=65536`）。

## 要求

1. **全量 review 语料清单**：扫 `.agenticdoc/*/workers/*/trace.log`，识别所有 review 类 run（`type=review` / `reviewer` / `verifier`，判据写清并用一条命令给出计数）。每 run 输出：取数次数（read+find+grep+ls）、distinct 文件数、`[END]` 的 exit 与 elapsed、是否出现 `[MODEL_RETRY]`/`[MODEL_FALLBACK]`/`model unavailable`、是否 `needs-clarification`。给机读表（CSV 或 markdown 表）与汇总分位数（p50/p90/max）。
2. **token 归因**：确认每个 run 的 pi 会话 JSONL 如何定位（session id 从哪来：`run.json`、argv、`argv. 文件`、还是时间+cwd 匹配）。把 `usage.py` 现有的 join 逻辑读透并写清 `文件:行号`；若某类 run 无法可靠 join，明确写出"缺什么信号"，**不要用近似值冒充实测**。给出至少 5 个 run 的"取数次数 → 输入 tokens"对照。
3. **tokens/次取数 常数**：用上一步的对照算出该常数的分布（均值/中位数/离散度），并与 `packages/coding-agent/src/core/compaction/compaction.ts` 的 `estimateTokens`（chars/4 启发式）比较偏差。给出"用 chars/4 估算 read 结果 tokens"的误差量级。
4. **断言供给量**：对每个 review run 找到它的 `card_path`，统计卡里"可枚举的判定单元"数量（发现条目 / AC 行 / VC 行 / 编号要求），与第 1 步的取数次数做相关性。回答：历史上**每次取数对应多少条判定单元**？
5. **预算推荐值**：给定 §1 的窗口事实（200k 窗口、`reserveTokens=16384`、`keepRecentTokens=20000`），给出：单 worker 的取值上限（次）、字节上限、每单元 claim 数 K、以及"何时从 1×N 拆成 4×2"的判定式（用第 3、4 步的常数）。每个推荐值必须说明它是从哪个分位数推出的。
6. **失败普查**：统计 review 类 run 的失败形态分布（超窗降级 / 无产物 / needs-clarification / 超时 / 其它），各给计数与一条实例路径。若能把"超窗降级"与"取数次数"对应上，给出阈值区间。

## 唯一证据文件

`.agenticdoc/claim-driven-review/evidence/research/spec-rq1-review-corpus-20261020.md`

用 `bash` + Python 直接写该路径（写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为回读兜底。**不得写其它任何文件**。

## 交付格式

- `## 0. 结论先行`（≤6 条，可直接被 spec/design 引用）→ `## 1…6` 逐问作答 → `## 数值表`（markdown 表）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每个数字给实测命令与输出摘要；`文件:行号` + 原文片段。未找到写「未找到（命令 + 输出）」，**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`（缺段会被判 needs-clarification）。

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest。只读命令与 Python 只读扫描允许；临时文件放 `%TEMP%`。
