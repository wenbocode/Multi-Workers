# RQ2 — `decision_signoff` 门禁结构：从"标记文件触发"改为"无条件执行"

- type: research
- owner key: mw-signoff-decide-only
- 唯一证据文件：`.agenticdoc/mw-signoff-decide-only/evidence/research/spec-gate-structure-20261022.md`

## 上下文

项目目标见 `.agenticdoc/goal.md`。本 key 要让收尾签收只在"决策模型真的参与过"时成立，并**彻底忽略** `decision-scope.md` 标记（该标记是历史遗留，本身无语义）。

现状锚点：

- `.agents/skills/agentic-task/scripts/advance_phase.py:37` `DECISION_SCOPE_MARKER = "decision-scope.md"`
- 同文件 `:123-131` `GATES["done"]` 里的 `(DECISION_SCOPE_MARKER, "decision_signoff", None, ...)` 规则
- 同文件 `:420-427` `check_gate` 对 `decision_signoff` 的分支（只有标记文件存在才调用）
- 同文件 `:233` `_load_decide_signoff` 的延迟导入注释
- 同文件 `:271` `_decision_signoff_problems`

## 要求（只读）

1. 逐行说明 `check_gate` 的规则循环：`path_pattern`、`full_path`、各 `check_type` 分支如何决定"是否执行"。给出能让 `decision_signoff` **无条件执行**的最小规则写法（例如把 path_pattern 改成别的哨兵、或加新 check_type），并指出哪种写法不会影响其他规则。
2. 说明 `_decision_signoff_problems` 当前的控制流：`signoff: disable` 跳过 → 文件存在性 → 机器行 → `_load_decide_signoff` → `collect` → sha → `verdict`。标出**在哪一行插入"该 key 无决策行则返回 []"最安全**（必须在导入之前）。
3. 给出一个**不依赖 `decide_signoff` 导入**的廉价判据方案：如何在本文件内用 `json` 读 `<key_dir>/../_autopilot/decisions.jsonl`，判断是否存在 `kind=decide` 且 `key` 列等于该 key（或 `decision_id` 以 `:<key>` 结尾）的行。逐条指出与 `decide_signoff._row_matches_key` 对齐需要注意的边界（缺列、非字符串、空 key）。
4. 列出 `advance_phase.py` 的**副本**：`.agents/skills/agentic-task/{claude,core}/scripts/advance_phase.py`、`.claude/scripts/advance_phase.py`、`packages/multi-workers/.tmp/agentic-task/...`。判断哪些是仓库内需要同步的镜像、哪些是临时产物（给依据：git 是否跟踪、install.py 的同步方向）。
5. 找出 `decision_signoff` 相关的测试：`packages/multi-workers/test_decide_signoff.py:617` 起用 `decision-scope.md` 夹具的用例，逐条说明改条件后哪条会失效、应改成什么断言。

## 写入允许面

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-gate-structure-20261022.md`
- `.agenticdoc/mw-signoff-decide-only/workers/sdo-rq2-gate/**`

其它文件一律只读。

## 交付格式

Markdown，五节对应上面 5 条；第 1、3 条必须给出可粘贴的代码片段草案（标明插入位置的行号）。最后一段 `## 风险` 列出最容易被忽略的一处（≤5 行）。
