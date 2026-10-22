# dp-inventory-B（2026-10-21）— dp7..dp12 事实采集（只读）

采集人：worker ds-rq-dp-b（card `tasks/RQ-DP-B-inventory.md`，sha256 b816831e…）。
行号取自本工作区实际读到的文件版本（`packages/multi-workers/decision_points.py` 1907 行版、
`packages/multi-workers/mw.py` 8947 行版、`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts` 当前版）。
采集手段：只读文件 + 一次只读 Python import 打印注册表常量（未跑 `mw decide run/ask/probe`，未跑测试，未改代码）。

## 汇总表

| dp | tier | 默认 enabled/mode（注册表；本仓 .mw 表） | 触发点 | questions 类型 | 采纳落点 |
|---|---|---|---|---|---|
| dp7-gate-failure | P2 | true/auto（本仓 on/auto） | 未接线；唯一入口 ask_decision 工具枚举 `decision-tool.ts:117` + `mw decide run` 手工（`mw.py:947`） | 1×choice（无 labels/instructions） | answer 面 advisory 留痕 `decision_points.py:1937-1975`；intent=act 则占位执行器必抛 → over-authority `decision_points.py:2004-2021` |
| dp8-scope-change | P0 | false/auto（本仓 off/auto） | 未接线；同上 `decision-tool.ts:118`；enabled=false 时 step2 先 escalate("disabled") `decision_points.py:1718-1736` | 2×choice（带 instructions+labels） | disabled 优先；人工开启需 `--i-understand-p0`（`mw.py:1805-1819`，`on`:`1827`/`set`:`1919`）；开后 answer 面 advisory；executor=None → over-authority "no executor" `decision_points.py:1978-2002` |
| dp9-model-select | P2 | true/auto（本仓 on/auto） | 未接线；`decision-tool.ts:119` | 1×choice | 同 dp7 |
| dp10-dependency | P1 | false/auto（本仓 off/auto） | 未接线；`decision-tool.ts:120` | 1×choice | 同 dp8（P1 默认关 `decision_points.py:324,399`，但 `dp on` 不需要 `--i-understand-p0`，P0 门 `mw.py:1809` 只拦 P0） |
| dp11-credential | P0 | false/auto（本仓 off/auto） | 未接线；`decision-tool.ts:121` | 1×choice | 同 dp8（`mw decide dp set dp11-credential enabled=true` 无 flag 时 rc=2，`test_decide_dp_cli.py:430-437` 佐证） |
| dp12-destructive | P0 | false/auto（本仓 off/auto） | 未接线；`decision-tool.ts:122`（政策性默认关 `docs/decision-substitution.md:37`） | 1×choice | 同 dp8 |

每行"采纳落点"的共同前提：生产全仓唯一的 `decide_for` 调用点是 `mw.py:947`，固定 `intent="answer"`（`mw.py:909,947-948`），所以经任何现有人机通道 dp7..dp12 的答案都只落 advisory 档案行（acted=false，`authority="advisory"` `decision_points.py:1950`）；`acted=true` 只在 mode=auto + intent=act + 执行器真实返回动作时出现（档案 `authority="binding"` `decision_points.py:2076`，`status="acted"` `:2084`），而 intent=act 在生产代码中零调用点。

## 公共事实（六个 dp 共用，均带行号）

- 注册工厂 `_point`：`decision_points.py:385-412`。`executor` 默认 None `:392`；`default_mode="auto"` `:393`；`default_enabled=(tier=="P2")` `:399`；`build_state=_state_builder(dp_id)` `:402`；`questions_version=_questions_version(questions)` `:404`。
- `DecisionPoint` 十字段冻结形状 `decision_points.py:300-313`；`__post_init__` 导入期规则：`default_enabled must follow tier (P2 on, P1/P0 off)` `:324`；P0 必须带 `p0_consequences` `:342`；P2 必须带 executor（auto 必须能 act）`:344`——这就是 dp7/dp9 这类 P2 未接线点挂"必抛占位执行器"而非 None 的原因。
- `_unwired_executor`：`decision_points.py:372-380`。占位执行器调用即 `raise NotImplementedError(f"{dp_id}: executor not wired yet (call site card pending)")` `:380`（DS-4：不许默认动作）。
- 泛型 state 组装 `_state_builder`：`decision_points.py:349-370`。字段：`v`=1（恒有）、`dp`=dp_id（恒有）、`trigger.data` 逐键 setdefault（可选，`Trigger` 四字段 `:123-129`：trigger_id/key/task_key/data）、`key`（trigger.key 兜底）、`task_key`（trigger.task_key 兜底）、`questions_version`（注册表自动补）。
- 必需字段表 `REQUIRED_STATE_FIELDS`：`decision_points.py:872-922`，**只含 dp1/dp2/dp3** → dp7..dp12 无任何注册表必需字段，`_missing_required` `:956-958` 对它们恒返回空，step5（`decide_for` `:1760` 起）不会因缺字段拒答。
- 动态键：`dynamic_choices` 全注册表只有 dp3 的 `candidate` 题用（`decision_points.py:499`，state 键 `local_candidates`）；渲染枚举 `resolve_dynamic_choices` `:850-861` / `dynamic_choice_labels` `:826-847`。**dp7..dp12 全部是静态 choices，state 不带 `local_candidates`/`rendered` 这类动态键**。
- state 预算：canonical ≤ `MAX_STATE_BYTES`=2000B `:87`；两段截断后仍超 → escalate("input-oversize")（`decide_for` step6 `:1806-1821`）。TS 侧同额墙 `ASK_DECISION_MAX_STATE_BYTES`（`decision-tool.ts:34-36`）。
- `decide_for` 11 步（`decision_points.py:1666-2110`）：step2 disabled 先于一切 `:1718-1736`；step5 input-incomplete `:1760-1805`；step7 transport unavailable `:1822-1861`；step8 输入侧答案不可用 → low-confidence `:1862-1897`、输出侧仅 `confidence_source=="api"` 且低于阈值才门（`:1900-1934`）；阈值 `MIN_CONFIDENCE=0.7` `:90`，优先级 显式参数 > `.mw/decide.json` extras.min_confidence > 0.7（`_confidence_threshold` `:2102-2110`）；step9 suggest/answer 面 `:1937-1975`；step10/11 executor None → over-authority note="no executor" `:1978-2002`，执行器抛异常/空返回 → over-authority `:2004-2061`。
- TS worker 通道（`ask_decision` 工具）：仅在 worker 分支注册（`index.ts:84-90`，`PI_WORKER_TASK` 存在时）；工具注册 `decision-tool.ts:790-870`（`registerTool` `:797`）；dp 白名单 `ASK_DECISION_DP_IDS` `:110-135`（dp7..dp12 在 `:117-122`）；客户端组装 state `buildDecisionState` `:264-277`（只发 v/dp/key/task_key/task_summary，≤600B note→task_summary）；缺字段预检只对 dp1/dp2/dp3（`ASK_DECISION_ENFORCED_STATE_DP_IDS` `:146-150`，`missingDecisionStateFields` `:296-301`）——dp7..dp12 客户端永不预拒；子进程 argv `buildDecideArgv` `:422-434` = `python -X utf8 mw.py decide run --project=<dir> --dp <id> --request-file <f> --json`；runner `runDecideMw` `:450-477`；总入口 `runAskDecision` `:579+`；20s 硬墙 `ASK_DECISION_TIMEOUT_MS` `:87`；同 dp 一轮 2 次阻断即终止本轮（`ASK_DECISION_MAX_BLOCKED_PER_TURN` `:90`，执行于 `:843-867`）。
- 人用通道：`mw decide run`（结构化路径 → `decide_for(intent="answer")`，`mw.py:905-960`；legacy 自带 questions 路径不走注册表授权 `:931-941`）；`mw decide ask`（人类自由问答，`_decide_ask` `mw.py:1413-1462`，`_ASK_DP="dp-human-ask"` `:1128`，**完全不经过 dp 注册表/授权表**，打字即视为人类 opt-in `:1424-1428`）；`mw decide dp on/off/set`（人工写面，P0 开门 `_dp_require_p0_confirmation` `mw.py:1805-1819`，`on` 在 `:1827`、`set` 在 `:1919` 应用；P0 开启写档案 `by="human:p0-confirm"` `:1842`/`:1936`，合法值表 `decide_archive.py:73`）。
- questions_version 实测（只读 import，2026-10-21，与 `test_decision_points.py:341-346` 的 pin 一致）：版本只哈希题目形状 id/type/choices/dynamic_choices（`VERSIONED_QUESTION_KEYS` `decision_points.py:193`，`_questions_version` `:229-247`），改 instructions/labels/criteria 文案不变版本。
- 本仓授权表实况（`.mw/decide-points.json`，updated_at 2026-10-21T03:39:33Z by refresh，与种子一致）：dp7 on/auto、dp9 on/auto、dp8/dp10/dp11/dp12 off/auto。`.mw/decide.json`：transport=timi-decisions，model=jev-latest，enabled=true。

## dp7-gate-failure（相位门禁失败）

1. **注册身份**：`decision_points.py:535` `dp_id="dp7-gate-failure"`；`:536` tier="P2"；`:537` description="相位门禁失败"；default_enabled=true（P2，`:399`）、default_mode="auto"（`:393`）；executor=`_unwired_executor("dp7-gate-failure")` `:545`。
2. **触发点**：未接线。没有任何调度/编排代码在特定条件下调用它（已查关键词见文末清单）。可达通道只有两个手工面：worker 的 `ask_decision` 工具枚举（`decision-tool.ts:117`）与 `mw decide run --dp dp7-gate-failure`（`mw.py:947`）。`docs/decision-substitution.md:60` 标注"仅注册（缺结构化输出）"、`:511` "注册表有占位执行器，无调用点｜真正接线的卡未开"。
3. **state 形状**：泛型 `_state_builder`（`:349-370`）组装：`v`(1, 必需)、`dp`(必需)、`key`/`task_key`/调用方 data 键(可选)、`questions_version`(注册表补)。无注册表必需字段（`REQUIRED_STATE_FIELDS` `:872-922` 无此条目）。TS ask_decision 面实际只发 v/dp/key/task_key/task_summary（`decision-tool.ts:264-277`）。无动态键（不涉及 `local_candidates`/`rendered`）。
4. **questions**：1 题 `gate_cause`（`:539-543`）：type=choice，choices=[missing-evidence, stale-verdict, config, unknown]（`:542`）；无 instructions、无 labels、无 criteria。`questions_version="q-c8e23cc7"`（`:341` pin + 实测一致）。
5. **答案采纳**：现网只会走 answer 面：`intent="answer"` → step9 status="suggested"、档案 acted=false、authority="advisory"（`:1937-1975`，`authority="advisory"` `:1950`）；ask_decision 工具把 answers 单行 JSON 返给 worker，落点=worker 自己照答案行事，工具层不执行任何动作（promptGuidelines `decision-tool.ts:811-820`；trace 记录 `:816-822`）。若有人以 `intent="act"` 直调（生产无此调用点）：mode=auto 时占位执行器抛 NotImplementedError → step11 escalate("over-authority")，note="executor raised NotImplementedError"（`:2004-2021`）。置信门仅 api 来源生效，0.7（`:90`,`:1900-1934`,`:2102-2110`）。**结论：注册但无真实执行器（占位执行器必抛），只有 `mw decide run` / ask_decision 可手工问，答案仅留痕+供 agent 参考。**
6. **风险语义**：P2 → 注册表默认开+auto；`--i-understand-p0` 与它无关（P0 专用，`mw.py:1809`）。

## dp8-scope-change（变更范围）

1. **注册身份**：`:548` dp_id；`:549` tier="P0"；`:550` description="变更范围"；`:551` p0_consequences="扩面会改动他人写面外的文件，跨会话冲突不可在一次重派内撤回"；default_enabled=false（P0）、mode=auto；**executor=None**（未传，`:392` 默认）。
2. **触发点**：未接线（同 dp7 判据；`docs/decision-substitution.md:61` "仅注册；p0_consequences 已写"）。且 enabled=false 时 `decide_for` step2 在 build_state/网络之前直接 escalate("disabled")（`:1718-1736`）——即默认状态下连 transport 都不碰。
3. **state 形状**：同 dp7 泛型 shape；无必需字段；无动态键。
4. **questions**：2 题。`scope_decision`（`:553-563`）：type=choice，choices=[keep, narrow, expand] `:556`，instructions="这次变更应该保持、收窄还是扩大范围？" `:557`，labels：keep=按原范围/narrow=缩小到原范围内的一子集/expand=扩大到原范围之外 `:558-562`。`scope_reason`（`:564-580`）：type=choice，choices=[outside-write-face, cross-key-conflict, scope-creep, unclear-boundary] `:567-572`，instructions="为什么需要或不需要改范围？" `:573`，labels：目标文件在授权写面之外/会与他人写面重叠/需求本身扩大了/边界不清需要先界定 `:574-579`。`questions_version="q-e5d928e8"`。
5. **答案采纳**：默认 disabled（无答案）。人工 `mw decide dp on dp8-scope-change --i-understand-p0`（`mw.py:164` 示例；`:1805-1819` 门）打开后：answer 面 advisory 留痕；intent=act 面 executor=None → step10 escalate("over-authority")，note="no executor"（`:1978-2002`）。开启动作本身写档案 `by="human:p0-confirm"`（`mw.py:1842`）。`p0` 这个 escalated_reason 是保留值（`ESCALATED_REASONS` `:105-115`，注释 `:117-121`），现版 `decide_for` 不产出。**结论：注册但无执行器（executor=None），仅人工开启后可问，答案只留痕。**
6. **风险语义**：P0 → 默认关；开必须显式 `--i-understand-p0`，否则 rc=2 且不写表（`mw.py:1805-1819`）；`dp set ... enabled=true` 同样被拦（`mw.py:1919`）。

## dp9-model-select（模型/降级选择）

1. **注册身份**：`:584` dp_id；`:585` tier="P2"；`:586` description="模型/降级选择"；default_enabled=true、mode=auto；executor=`_unwired_executor("dp9-model-select")` `:590`。
2. **触发点**：未接线（同 dp7 判据；`docs/decision-substitution.md:62` "仅注册"）。通道：`decision-tool.ts:119` 枚举 / `mw decide run`。
3. **state 形状**：同泛型；无必需字段；无动态键。
4. **questions**：1 题 `model_class`（`:588`）：type=choice，choices=[primary, fallback, degrade]；无 instructions/labels/criteria。`questions_version="q-bc7918b9"`。
5. **答案采纳**：同 dp7（answer 面 advisory `:1937-1975`；act 面占位执行器抛 → over-authority `:2004-2021`；阈值 0.7 `:90`）。**注册但无真实执行器。**
6. **风险语义**：P2 → 默认开/自动，本仓 on/auto；与 `--i-understand-p0` 无关。

## dp10-dependency（依赖升级）

1. **注册身份**：`:593` dp_id；`:594` tier="P1"；`:595` description="依赖升级"；default_enabled=false（P1）、mode=auto；executor=None（未传）。
2. **触发点**：未接线（同 dp7 判据；`docs/decision-substitution.md:63` "仅注册"）。enabled=false → step2 disabled。
3. **state 形状**：同泛型；无必需字段；无动态键。
4. **questions**：1 题 `dependency_decision`（`:597`）：type=choice，choices=[upgrade, hold, pin]；无 instructions/labels/criteria。`questions_version="q-3bbd9e44"`。
5. **答案采纳**：disabled 优先；人工 `mw decide dp on`（无需 P0 flag，`:1809` 只拦 P0）打开后 answer 面 advisory；act 面 executor=None → over-authority "no executor"（`:1978-2002`）。**注册但无执行器。**
6. **风险语义**：P1 → 注册表默认关（tier 规则 `:324`/`:399`：P2 on，P1/P0 off）；打开不需要 `--i-understand-p0`。

## dp11-credential（凭据/权限）

1. **注册身份**：`:601` dp_id；`:602` tier="P0"；`:603` description="凭据/权限"；`:604` p0_consequences="凭据隔离一旦放宽会外溢到其他 provider，泄露不可撤销"；default_enabled=false；executor=None。
2. **触发点**：未接线（同 dp7 判据；`docs/decision-substitution.md:64` "仅注册"）。
3. **state 形状**：同泛型；无必需字段；无动态键。
4. **questions**：1 题 `credential_action`（`:606`）：type=choice，choices=[isolate, rotate, deny]；无 instructions/labels/criteria。`questions_version="q-080722b1"`。
5. **答案采纳**：同 dp8（disabled / 开启后 advisory / act 面 over-authority "no executor" `:1978-2002`；P0 开门 `mw.py:1805-1819`）。**注册但无执行器。**
6. **风险语义**：P0 → 默认关；`dp on`/`dp set enabled=true` 都必须带 `--i-understand-p0`，否则 rc=2（`test_decide_dp_cli.py:430-437` 断言佐证）。

## dp12-destructive（破坏性操作）

1. **注册身份**：`:610` dp_id；`:611` tier="P0"；`:612` description="破坏性操作"；`:613` p0_consequences="删除/覆盖他人工作区文件或历史不可恢复，属外部副作用"；default_enabled=false；executor=None。
2. **触发点**：未接线（同 dp7 判据；`docs/decision-substitution.md:65` "仅注册"；`:37` DS-3 政策推迟："不替代 pi 核心的破坏性确认，dp12/dp13 保持 P0 默认关"）。
3. **state 形状**：同泛型；无必需字段；无动态键。
4. **questions**：1 题 `destructive_action`（`:615`）：type=choice，choices=[proceed, block, ask-human]；无 instructions/labels/criteria。`questions_version="q-02f737ab"`。
5. **答案采纳**：同 dp8。**注册但无执行器。**
6. **风险语义**：P0 → 默认关；开需 `--i-understand-p0`；破坏性确认目前仍由 pi 核心兜着，dp12 只留痕注册。

## 未接线清单（六个 dp 全部未接线）

判定口径：没有"谁在什么条件/阈值下自动调用"的代码；唯一存在形态是注册表条目 + 两个手工问答通道。实际搜过的关键词与结果：

- 六个字面 dp id（`dp7-gate-failure`…`dp12-destructive`）：`packages/coding-agent/src` 全量 → 仅 `decision-tool.ts:117-122`（ask_decision 工具的 dp 枚举，注释明言"copied verbatim from DP_REGISTRY"）；`packages/multi-workers/*.py` 非测试代码 → 仅 `decision_points.py:535/548/584/593/601/610` 注册行与 dp7/dp9 占位执行器行（`:545`/`:590`）；其余命中全在 `test_*.py` 与构建产物 `dist/`。
- 六个题目 id（`gate_cause`/`scope_decision`/`scope_reason`/`model_class`/`dependency_decision`/`credential_action`/`destructive_action`）：`packages/**` → 仅注册表（`:540`,`:554`,`:565`,`:588`,`:597`,`:606`,`:615`）。
- 接线常量对照：dp1/dp2/dp3 有专用接线常量与调用点（`DP1_ID` `triage-client.ts:75`、`DP2_CHECKPOINT_ID` `pm-orchestrator.ts:1958`、`DP3_ID` `worker-mode.ts:4425`），dp7..dp12 无任何对应物。
- `decide_for` 调用点全仓盘点：生产唯一 `mw.py:947`（`intent="answer"`）；无任何 `intent="act"` 生产调用（其余命中全为测试）。
- 佐证文档：`docs/decision-substitution.md:54-65` 接线表（dp7"仅注册（缺结构化输出）"、dp8/10/11/12"仅注册"、dp9"仅注册"）、`:511`（dp5/dp7 缺结构化输入，无调用点）、`:37`（dp12/dp13 政策性 P0 默认关）。

## 残留与未验证

- 按卡禁令未跑 `mw decide run/ask/probe`，传输层实际行为以代码路径 + `test_decide_*.py` 断言佐证，未做线上复现。
- `questions_version` 为只读 import 实测（2026-10-21 本工作区文件版本）；若 id/type/choices/dynamic_choices 任一形状键改动会重算（`VERSIONED_QUESTION_KEYS` `:193`）。
- `p0` escalated_reason 为保留词汇，现版 `decide_for` 代码路径不产出（`:117-121` 注释自述"lands with the P0 confirmation path"）。
- 行号基于当前工作区未提交状态，非 git 提交 pin；`dist/extensions/agent-team-loop.js:13134-13139` 为构建产物镜像，未逐行核对与 src 的新鲜度。
- 本仓 `.mw/decide-points.json` 是 refresh 产物（2026-10-21T03:39:33Z），反映的是当前人工/refresh 状态，不是注册表默认值；两者在本仓恰好一致（P2 开、P1/P0 关）。
