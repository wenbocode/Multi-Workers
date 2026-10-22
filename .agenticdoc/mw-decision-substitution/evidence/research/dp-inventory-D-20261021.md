# dp-inventory-D — dp19..dp24 决策点事实采集（2026-10-21）

- 卡：`.agenticdoc/mw-decision-substitution/tasks/RQ-DP-D-inventory.md`（sha256 1d3b0fe0…f207e）
- 所有 `path:line` 取自 2026-10-21 工作区实际读到的文件版本；只读采集，未运行 `mw decide run/ask/probe`，未改代码，无 git 写操作。
- 主读文件：`packages/multi-workers/decision_points.py`（2111 行）、`packages/multi-workers/mw.py`（读段 720-970 / 1413-1482 / 2182-2197 / 9780-9793）、`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（约 890 行）、`worker/worker-mode.ts`（读段 530-680 / 2400-2420 / 2970-3075）、`pm/ui-bridge.ts`（读段 2740-2790 / 3283-3380）、`.mw/decide-points.json`（149 行）、`packages/multi-workers/autopilot/conductor.py`（读段 1300-1330 / 6680-6920）、`packages/multi-workers/test_decision_points.py`（读段 40-60 / 345-360）。

## 0. 一句话结论

dp19..dp24 六个点全部**仅注册、未接线**：全仓没有任何生产代码路径调用它们。Python 侧唯一生产 `decide_for` 调用点是 `mw decide run` 的结构化路径（`mw.py:947`，且固定 `intent="answer"`）；TS 侧唯一引用是 `ask_decision` 工具的 dp 枚举（`decision-tool.ts:129-134`）。即使被询问，也只走咨询分支（`acted=false`，`decision_points.py:1943-1978`），执行器永远不触发；dp21/22/23 的执行器本身也是故意抛错的 `_unwired_executor`。

## 1. 六行汇总表

| dp | tier | 默认 enabled/mode（注册表=本仓 .mw） | 触发点 | questions 类型 | 采纳落点 |
|---|---|---|---|---|---|
| dp19-foreign-write | P0 | off/auto（`.mw/decide-points.json:114-119`） | 未接线（§9）；越面写实际由 write-face 守卫 + AC-007 escape hatch 承担 `worker-mode.ts:3060-3070` | 1×choice `write_decision` | 无执行器；人工通道 ask_decision/`mw decide run` 仅咨询（acted=false）；实际放行机制 = `--allow-foreign-write`→task.md frontmatter（`ui-bridge.ts:3301-3307,2748-2753`）+ worker 侧校验留痕（`worker-mode.ts:668-669,3060-3070,2406-2417`） |
| dp20-stage-close | P0 | off/auto（`:120-125`） | 未接线（§9）；stage 闭环实际走 autopilot 人工门 `conductor.py:1308,1327` | 1×choice `stage_action` | 无执行器；人工门 = autopilot gate 文件 + T-12 自动放行规则 `stage-close-credentials`（`conductor.py:6711,6891,6911-6918`），与 dp20 无关 |
| dp21-refine | P2 | on/auto（`:126-131`） | 未接线（§9）；语义替代 = workflow 文档人工确认条款 `.agents/skills/agentic-task/core/workflows/project-refine.md:64` | 1×choice `refine_decision` | 注册但无执行器（`_unwired_executor` `decision_points.py:703`），只有 `mw decide run` 可手工调用，`intent="answer"` 只留痕不执行 |
| dp22-debug-plan | P2 | on/auto（`:132-137`） | 未接线（§9）；语义替代 = debug workflow 人工确认 `.agents/skills/agentic-task/core/workflows/debug.md:113` | 1×choice `debug_plan` | 同 dp21（executor `decision_points.py:716`） |
| dp23-snapshot | P2 | on/auto（`:138-143`） | 未接线（§9）；语义替代 = pm-mind Hook 人工确认 `.agents/skills/agentic-task/core/pm-mind.md:225` | 1×choice `snapshot_decision` | 同 dp21（executor `decision_points.py:725`） |
| dp24-pi-trust | P0 | off/auto（`:144-149`） | 未接线（§9）；pi core 信任实际由 pi 自身 project-trust 机制承担 `packages/coding-agent/src/core/project-trust.ts:33` | 1×choice `trust_decision` | 无执行器；人工通道同上（仅咨询） |

## 2. 共通机制（六点共用，行号均 `decision_points.py` 除非另注）

- 注册工厂 `_point`：`:385-407`。`default_enabled=(tier=="P2")` `:399`；`default_mode="auto"` `:393`；`questions_version=_questions_version(questions)` `:404`（内容哈希 `q-<8hex>` `:285-301`，只哈希 `id/type/choices/dynamic_choices`，`:193`，labels/instructions 改动不动版本）。
- 注册校验（import 期 fail-loud）：`DecisionPoint.__post_init__` `:296-347` —— `default_enabled` 必须跟随 tier（P2 on / P0/P1 off）`:316`；P0 必须带 `p0_consequences` `:331-333`；P2 必须带 executor `:334-336`。总数 `EXPECTED_DP_COUNT=24` `:92`，`_validate_registry` `:746-759`。
- 泛型 state 组装 `_state_builder` `:349-365`：`{v:1, dp:<id>}` + `trigger.data` 逐键透传（setdefault，调用方可覆盖）+ `key`/`task_key`（trigger 有才加）+ `questions_version`（自动补）。
- 必需字段表 `REQUIRED_STATE_FIELDS` `:872-904` **只有 dp1/dp2/dp3**；dp19..24 无条目 → `_missing_required` `:956-958` 恒返回空 → 这六点不会因缺字段升级 `input-incomplete`（唯一例外是 build_state 自身抛异常，`:1787-1798`）。
- 无动态键：dp19..24 的 state 不含 `local_candidates`/`rendered` 类动态键。全注册表唯一 `dynamic_choices` 是 dp3 的 `"local_candidates"`（`:499`），渲染逻辑 `resolve_dynamic_choices` `:850-865` / `:830-848`。
- 控制流 `decide_for` `:1666-2089`（11 步，docstring `:1679-1702`）：step2 disabled 提前返回（不 build_state、不碰网络）`:1712-1727`；step5 缺字段 `:1780-1801`；step6 超 2000B（`MAX_STATE_BYTES=2000` `:91`）`:1806-1824`；step7 传输不可用 `:1826-1858`；step8 低置信/无可用答案 `:1860-1941`；step9 `mode=suggest` 或 `intent="answer"` → `status="suggested"`、`acted=false`，只归档不执行 `:1943-1978`；step10/11 executor None/抛错/空返回 → `over-authority` `:1980-2063`（executor 调用 `:2008`），成功才 `authority="binding"`、`status="acted"` `:2072-2089`。
- 置信门：`MIN_CONFIDENCE=0.7` `:90`；仅 `confidence_source=="api"` 才参与门控（自报/未知源完全忽略）`:1900-1941`；阈值优先级 显式参数 > `.mw/decide.json` extras `min_confidence` > 0.7（`_confidence_threshold` `:2102-2110`）。
- 留痕：每次到达传输层的决策写一行 `decide` 归档（`.agenticdoc/_autopilot/decisions.jsonl` `:38`），写入器 `decide_archive.append_decide`（`decide_archive.py:917`），经 `_maybe_archive` `:1525` 在各出口调用 `:1828/1872/1908/1942/1979/2010/2039/2068`。`escalated_reason` 冻结词表 `:107-118`（disabled/unavailable/input-incomplete/input-oversize/low-confidence/over-authority/p0）。
- P0 开关与 `--i-understand-p0`：`mw decide dp on/set` 对 P0 点必须带 `--i-understand-p0`，否则 exit 2 且不写文件（`mw.py:1808-1813`；argparse `:9780-9793`）；`dp refresh` 只补缺行，拒绝开 P0，提示人工 `mw decide dp on <id> --i-understand-p0`（`mw.py:2182-2197`）。`.mw/decide-points.json` 是唯一授权源（设计 D-001），机器永不写它。
- 人用通道：`mw decide run`（`_decide_run` `mw.py:928-970`）结构化路径 `decide_for(dp, trigger, …, intent="answer")` `mw.py:947-951`；`mw decide ask`（`_decide_ask` `mw.py:1413-1467`）根本不走注册表（`_ASK_DP="dp-human-ask"` `mw.py:1128`），人敲命令即视为 opt-in（`mw.py:1430-1433`）。TS 的 `ask_decision` 工具 spawn 的就是前者（`decision-tool.ts:19,419-452`）。

## 3. dp19-foreign-write（越面写预授权）

1. **注册身份**：`decision_points.py:679-685`。`tier="P0"` `:680`；`default_enabled=False`（P0→off，工厂 `:399`）；`default_mode="auto"`；description「越面写预授权」`:681`。
2. **触发点**：未接线（已查 `dp19`、`dp19-foreign-write`、`foreign-write`、`write_decision`、`decide_for\(`，见 §9）。实际承担越面写裁决的是 write-face 守卫 + AC-007/T-07 escape hatch：`worker-mode.ts:3060-3070`（判定条件原文：`if (meta.allowForeignWrite === true && verdict.rule !== "deny")` → 放行并写 `[ESCAPE_HATCH]` 审计行 `:2406-2417`；missing/false 保持 fail-closed `:3066` 附近注释）。frontmatter 来源：`worker-mode.ts:668-669`，dispatch flag `--allow-foreign-write` → task.md frontmatter `allow_foreign_write: true`（`ui-bridge.ts:3301-3307, 2748-2753, 2138-2139`）。
3. **state 形状**：泛型 `_state_builder`（若真被调用）；字段 = `v`(恒 1)、`dp`("dp19-foreign-write")、`key`/`task_key`（可选）、`questions_version`（自动）；其余字段全靠调用方 `trigger.data`，当前无调用方。**无必需字段**（§2），无 `local_candidates`/`rendered`。
4. **questions**：1 题 `{"id":"write_decision","type":"choice","choices":["allow","deny","redirect"]}` `:684`。无 labels、无 criteria（criteria 仅 noul 可带 `:278-282`）、无 instructions；`questions_version="q-df9c727d"`（`test_decision_points.py:353`，与 ds-fix-o2 采集一致）。
5. **答案采纳**：P0 默认 disabled → step2 `escalate("disabled")`；若经 ask_decision/`mw decide run` 询问，`intent="answer"` → `status="suggested"`、`acted=false`、只写归档行，**无任何 steer/narrow/escalate 落点**——答案以 JSON 返回给调用方，采不采纳纯属人工。无执行器（executor=None `:685` 后未传）。
6. **风险语义**：P0 + 默认 off；本仓 `.mw/decide-points.json:114-119` 维持 off；人工开启必须 `--i-understand-p0`（`mw.py:1808-1813`）。`p0_consequences`「越面写会覆盖其他会话/其他 key 的文件，写坏即他人工作丢失」`:682`。

## 4. dp20-stage-close（stage 闭环）

1. **注册身份**：`decision_points.py:688-694`。`tier="P0"` `:689`；off/auto；description「stage 闭环」`:690`。
2. **触发点**：未接线（已查 `dp20`、`dp20-stage-close`、`stage_action`、`decide_for\(`，见 §9）。spec §4 预期锚 `conductor.py:1330` 实为 autopilot **gate 机制**：`conductor.py:1308`（`_gate_open(project_root, "stage-close", stage=stage.number)` 判重）与 `:1327`（`_create_gate(project_root, st, "stage-close", …)` 建 gate 文件）——这是 autopilot 的人工门子系统（`autopilot/gates.py:84` kind 枚举），不是 dp20 的 decide 调用。
3. **state 形状**：同 dp19（泛型 builder、无必需字段、无动态键）。
4. **questions**：1 题 `stage_action`，choice `[close, hold, rework]` `:693`；无 labels/criteria/instructions；`questions_version="q-30afd59f"`（`test_decision_points.py:354`）。
5. **答案采纳**：同 dp19（disabled / answer-only / 无落点）。stage 闭环的实际自动裁决在 T-12 规则 `stage-close-credentials`：proposition `proposition_stage_close_credentials` `conductor.py:6711`，规则 id `:6891`，注册 `AutoRule(gate_kind="stage-close", …)` `:6911-6918`——五条事实子句（`_stage_close_facts` `:7269`）全过才自动 approve，任何一条不过回落人工。与 dp20 注册表条目零代码关联。
6. **风险语义**：P0 + off + `--i-understand-p0` 才能开；本仓 `:120-125` off。`p0_consequences`「stage 闭环会推进不可回退的门禁与产物状态，错误闭环需要人工重建」`:691`。

## 5. dp21-refine（project-refine 升级）

1. **注册身份**：`decision_points.py:697-703`。`tier="P2"` `:698`；`default_enabled=True`（P2→on，`:399`）；auto；description「project-refine 升级」`:699`。
2. **触发点**：未接线（已查 `dp21`、`dp21-refine`、`refine_decision`、`decide_for\(`，见 §9）。语义替代：refine workflow 的人工硬门槛「self-refinement 硬门槛 | **须人工确认**（须报给用户确认后人工执行）」`.agents/skills/agentic-task/core/workflows/project-refine.md:64` —— 是流程文档条款，无代码调用。
3. **state 形状**：泛型 builder；无必需字段；无动态键。
4. **questions**：1 题 `refine_decision`，choice `[accept, defer, reject]` `:701`；无 labels/criteria/instructions；`questions_version="q-ddd23fe2"`（`test_decision_points.py:355`）。
5. **答案采纳**：executor=`_unwired_executor("dp21-refine")` `:703`（定义 `:372-380`，**故意** `raise NotImplementedError` `:380`，DS-4 禁止默认动作）。若将来有 `intent="act"` 调用点 → step11 `escalate("over-authority")` `:2035-2063`。当前生产里唯一入口 `mw decide run` 固定 `intent="answer"`（`mw.py:947-951`），**注册但无执行器，只有 `mw decide run` 可手工调用，只留痕不执行**。
6. **风险语义**：P2 → 默认 on/auto（`P2 必须有 executor` 的校验 `:334-336` 由占位器满足）；无需 `--i-understand-p0`；本仓 `:126-131` on。

## 6. dp22-debug-plan（debug 方案确认）

1. **注册身份**：`decision_points.py:706-716`。`tier="P2"` `:707`；on/auto；description「debug 方案确认」`:708`。
2. **触发点**：未接线（已查 `dp22`、`dp22-debug-plan`、`debug_plan`，见 §9）。语义替代：debug workflow Step 6 修法「先与用户确认」`.agents/skills/agentic-task/core/workflows/debug.md:113` —— 流程条款，无代码调用。
3. **state 形状**：泛型 builder；无必需字段；无动态键。
4. **questions**：1 题 `debug_plan`，choice `[hypothesis-first, repro-first, rollback]` `:710-713`；无 labels/criteria/instructions；`questions_version="q-a1ed6dbc"`（`test_decision_points.py:356`）。
5. **答案采纳**：executor=`_unwired_executor("dp22-debug-plan")` `:716` → 同 dp21：注册但无执行器，只有 `mw decide run` 手工可调，`intent="answer"` 只留痕。
6. **风险语义**：P2 → 默认 on/auto；本仓 `:132-137` on。

## 7. dp23-snapshot（memory 快照）

1. **注册身份**：`decision_points.py:719-725`。`tier="P2"` `:720`；on/auto；description「memory 快照」`:721`。
2. **触发点**：未接线（已查 `dp23`、`dp23-snapshot`、`snapshot_decision`，见 §9）。语义替代：pm-mind Hook「需要用户确认 Y 后再执行 `/project-memory snapshot`；未确认 → **不得**动 `_arch_snapshot.md`」`.agents/skills/agentic-task/core/pm-mind.md:225` —— 流程条款，无代码调用。
3. **state 形状**：泛型 builder；无必需字段；无动态键。
4. **questions**：1 题 `snapshot_decision`，choice `[write, defer, skip]` `:723`；无 labels/criteria/instructions；`questions_version="q-f5cecffb"`（`test_decision_points.py:357`）。
5. **答案采纳**：executor=`_unwired_executor("dp23-snapshot")` `:725` → 同 dp21/22。
6. **风险语义**：P2 → 默认 on/auto；本仓 `:138-143` on。

## 8. dp24-pi-trust（pi core 交互）

1. **注册身份**：`decision_points.py:728-734`。`tier="P0"` `:729`；off/auto；description「pi core 交互」`:730`。
2. **触发点**：未接线（已查 `dp24`、`dp24-pi-trust`、`trust_decision`、`pi-trust`、`project-trust`，见 §9）。pi 的项目信任实际由 pi core 自身机制承担：`packages/coding-agent/src/core/project-trust.ts:33`（`ctx.ui.select(formatProjectTrustPrompt(cwd), …)` 的信任对话框）+ 扩展可挂的 `project_trust` 事件（`packages/coding-agent/test/extensions-runner.test.ts:122-142`）——都不是 dp24 调用。
3. **state 形状**：泛型 builder；无必需字段；无动态键。
4. **questions**：1 题 `trust_decision`，choice `[trust-once, trust-always, deny]` `:733`；无 labels/criteria/instructions；`questions_version="q-20850ffa"`（`test_decision_points.py:358`）。
5. **答案采纳**：同 dp19/20（disabled / answer-only / 无落点）。无执行器。
6. **风险语义**：P0 + off + `--i-understand-p0` 才能开；本仓 `:144-149` off。`p0_consequences`「影响 pi 核心信任边界，误判后会话权限升级不可在一次重派内撤回」`:731`。

## 9. 未接线清单（六个 dp 全部命中，检索记录）

全仓扫描（`.py/.ts/.mts/.js/.mjs/.json/.md/.sh/.ps1/.yaml/.yml/.toml`，跳过 `.git/node_modules/__pycache__/.venv`），实际搜过的关键词：

- `dp19`、`dp20`、`dp21`、`dp22`、`dp23`、`dp24`（短前缀，含完整 id 变体 `dp19-foreign-write` 等）→ 命中仅：注册表 `decision_points.py:679-734`、TS 枚举 `decision-tool.ts:129-134`（+ dist 构建产物）、`.mw/decide-points.json:114-149`、测试断言 `test_decision_points.py:48-53,353-358`、文档（`docs/decision-substitution.md:72-77`、`.agenticdoc/mw-decision-substitution/spec.md:88-93`、evidence/*.md）。**没有任何一处是调用点。**
- `decide_for\(`（`packages/**`）→ 生产调用点仅 `mw.py:947`（`mw decide run` 结构化路径，`intent="answer"`）；`decision_points.py:1666` 是定义；其余全是测试。
- `foreign-write|stage-close|pi-trust|project-trust|write_decision|stage_action|refine_decision|debug_plan|snapshot_decision|trust_decision`（`packages/**`）→ 命中均为各 dp 的「语义替代机制」（§3-§8 第 2 条）或无关同名（autopilot gate kind、测试 fixture），无 dp 调用。

佐证：`docs/decision-substitution.md:72-77` 对这六点逐行标注「仅注册」；`decision-tool.ts:139-151` 的 `ASK_DECISION_ENFORCED_STATE_DP_IDS` 也只含 dp1/dp2/dp3（TS 侧对 dp19..24 不做字段预门禁）。

## 10. 残留与未验证

- `questions_version` 值取自测试钉死的期望表 `test_decision_points.py:353-358`（未重算哈希；同一值在 `workers/ds-fix-o2-registry-instructions/report.md:80` 独立采集过，两处一致）。
- spec §4 的行号锚（如 `conductor.py:1330`、`worker-mode.ts:2986`）与当前工作区有 ±几行的漂移；本文件一律引用实测行号。
- 未运行任何 decide 命令验证端到端行为（按卡禁令）；step9/10/11 的行为描述来自 `decide_for` 源码与 `test_decision_points.py` 用例（`:635-1090` 多处）。
