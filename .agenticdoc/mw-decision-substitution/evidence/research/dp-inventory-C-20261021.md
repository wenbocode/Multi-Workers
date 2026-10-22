# dp-inventory-C：dp13..dp18 决策点事实采集（2026-10-21）

卡：`tasks/RQ-DP-C-inventory.md`。只读采集，未跑 `mw decide run/ask/probe`、未改代码、未跑测试、无 git 写。
路径约定：`dpts.py` = `packages/multi-workers/decision_points.py`；`decision-tool.ts` = `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`；`triage-client.ts` = `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`；`mw.py` = `packages/multi-workers/mw.py`。行号取自本轮实际读到的文件版本（2026-10-21 工作区）。

## 结论

dp13..dp18 全部**未接线**：注册表只有 id/tier/题面，无任何生产调用点（`decide_for` 的唯一生产调用是 `mw decide run`，mw.py:947，且固定 `intent="answer"`）；TS 侧只有 `ask_decision` 工具的 dp 枚举提到它们（decision-tool.ts:123-128）。六者 executor 均为 None（连 `_unwired_executor` 占位都没挂，那是 dp21/22/23 专属，dpts.py:372），因此答案永远到不了执行器：answer 通道 status="suggested"/acted=false 只留痕（dpts.py:1941-1976），act 通道 over-authority 上抛（dpts.py:1978-1996）。本仓 `.mw/decide-points.json` 六者全部 `enabled=false, mode=auto`。

## 证据

### 6 行汇总表

| dp | tier | 默认 enabled/mode | 触发点 path:line | questions 类型 | 采纳落点 path:line |
| --- | --- | --- | --- | --- | --- |
| dp13-commit-release | P0（spec 复合格 P1/P0 取 P0，dpts.py:411-417） | off / auto（dpts.py:399；本仓表 enabled=false） | 未接线：仅 ask_decision 枚举 decision-tool.ts:123 + 手工 `mw decide run` mw.py:947 | choice×1（release_action，静态 choices） | 只留痕：intent=answer→suggested/acted=false（dpts.py:1941-1976）；无执行器→over-authority（dpts.py:1978-1996） |
| dp14-rule-conflict | P0 | off / auto（同上） | 未接线：decision-tool.ts:124 + mw.py:947 | choice×1（conflict_resolution） | 同上（dpts.py:1941-1976 / :1978-1996） |
| dp15-autopilot-gate | P0 | off / auto（同上） | 未接线：decision-tool.ts:125 + mw.py:947 | choice×1（gate_decision） | 同上（dpts.py:1941-1976 / :1978-1996） |
| dp16-goal | P0 | off / auto（同上） | 未接线：decision-tool.ts:126 + mw.py:947 | choice×1（goal_decision） | 同上（dpts.py:1941-1976 / :1978-1996） |
| dp17-spec-lock | P1 | off / auto（同上） | 未接线：decision-tool.ts:127 + mw.py:947 | choice×1（spec_lock） | 同上（dpts.py:1941-1976 / :1978-1996） |
| dp18-claim | P1 | off / auto（同上） | 未接线：decision-tool.ts:128 + mw.py:947 | choice×1（claim_conflict） | 同上（dpts.py:1941-1976 / :1978-1996） |

### 共用机制（六者相同，各 dp 节只写差异）

- 注册工厂：`_point()` dpts.py:385-411 —— `default_enabled=(tier=="P2")` :399（P0/P1 一律 off）、`default_mode="auto"` :393、`executor=None` :392（六者均未传 executor）、`build_state=_state_builder(dp_id)` :402、`questions_version=_questions_version(questions)` :404。
- state 形状（泛型 `_state_builder` dpts.py:349-369）：恒有 `v=1, dp=<id>` :357；`trigger.data` 原样 setdefault 并入 :358-359（不给默认值，docstring :352-353）；`key` :360-361、`task_key` :362-363（trigger 有才写）；`questions_version` 由注册表自动补 :364-366。必需字段表 `REQUIRED_STATE_FIELDS` dpts.py:872-923 只含 dp1/dp2/dp3 → 这 6 个 dp **零必需字段**，step 5（decide_for :1782-1796，`_missing_required` :956-958）不可能因缺字段 escalate。无动态键：六题全部静态 `choices`，`resolve_dynamic_choices`（dpts.py:850）无事可做；`local_candidates` 是 dp3 专用（dpts.py:920）；`closure`/`rendered` 类键不出现在这 6 个 dp 的 state 里（dp13 的 TS 侧 `closure` required_if 见 dp13 节，今天不被强制）。
- 两条人用通道：
  - `mw decide run --dp <id> --request-file <json>`：`_decide_run` mw.py:905-960，结构化路径走 `decide_for(..., intent="answer")` mw.py:947-948；请求 JSON 由 `_decide_read_request` mw.py:698 解析，dp/题面由 `_decide_resolve_dp_questions` mw.py:812 从注册表解析。TS `ask_decision` 工具 spawn 的就是这条 CLI（`buildDecideArgv` decision-tool.ts:422-436），state 由 `buildDecisionState`（decision-tool.ts:264-277）组装 = `{v:1, dp, key?, task_key?, task_summary(=note, ≤600B)}`。
  - `mw decide ask`：`_decide_ask` mw.py:1413-1470，用 `_ASK_DP="dp-human-ask"`（mw.py:1128）直接问模型，**不过注册表、不过 decide_for、不归档**——与 dp13..dp18 无接线关系。
- 答案采纳（六者相同）：answer 通道（今天唯一通道）命中 decide_for step 9 `if mode == "suggest" or intent == "answer":` dpts.py:1941 → status="suggested" :1959、acted=false、authority="advisory"、note="intent=answer"，一行归档到 `.agenticdoc/_autopilot/decisions.jsonl`（`DECISIONS_RELATIVE_PATH` dpts.py:75，`_maybe_archive` :1525）。答案本身只回显给调用方，**没有任何 steer/narrow/escalate 消费者**（对比 dp2=PM narrow、dp3=worker steer，那两个有 TS 消费点）。若将来以 intent=act 调用（注册表语义允许、现无调用方）：executor=None → step 10 `escalated_reason="over-authority"`、note="no executor"、acted=false（dpts.py:1978-1996）。置信门：仅 `confidence_source=="api"` 生效（dpts.py:1905-1907），阈值优先级 显式参数 > `.mw/decide.json` extras.min_confidence > `MIN_CONFIDENCE=0.7`（dpts.py:2102-2111，:90）；不可用答案/低置信 → escalated_reason="low-confidence"（dpts.py:1881/:1917）。
- 风险语义：tier 决定 enabled 默认——校验 `default_enabled must follow tier (P2 on, P1/P0 off)` dpts.py:324，赋值 dpts.py:399；P0 必须声明 `p0_consequences` dpts.py:340-343。把 P0 从 off 打开需显式 `--i-understand-p0`（`_dp_require_p0_confirmation` mw.py:1806-1818，不带则 stderr + exit 2 不落盘；`mw decide dp on` mw.py:9780-9784、`dp set` mw.py:9789-9794）。`escalated_reason="p0"` 在冻结词表预留（dpts.py:105-114，:113 注释指未来 P0 confirmation path）但**无生产者**。dp13/dp14/dp15/dp16=P0 → 默认关 + `--i-understand-p0` 才能开；dp17/dp18=P1 → 默认关，开启无 P0 门。

### dp13-commit-release

1. **注册身份**：`dp_id="dp13-commit-release"` dpts.py:619，`tier="P0"` :620，description「提交(P1) / 发布+版本号(P0)」:621，p0_consequences「发布与版本号推进对外可见且不可撤回（tag 已推送即不可重发同一版本）」:622。复合 tier 说明注释 dpts.py:411-417（spec §4 格子 P1/P0，fail-closed 取 P0；design D-029 见 `.agenticdoc/mw-decision-substitution/design.md:180`；P0 计数=10 断言 test_decision_points.py:257）。
2. **触发点**：未接线。spec 期望节奏「每次收尾」（spec.md:82，锚 AGENTS.md:40,130），代码无调用点。唯一引用面：TS 枚举 decision-tool.ts:123；手工 `mw decide run` mw.py:947。
3. **state 形状**：泛型 builder（见共用机制），零必需字段。TS 侧 `REQUIRED_FIELDS_BY_DP["dp13-commit-release"]=["closure"]`（triage-client.ts:376，block 校验器 closure.* triage-client.ts:485-489），但 (a) `ASK_DECISION_ENFORCED_STATE_DP_IDS` 只含 dp1/dp2/dp3（decision-tool.ts:146-150），(b) Python `REQUIRED_STATE_FIELDS` 无 dp13 条目（dpts.py:872-923）→ `closure` 今天**不被任何一层强制**；spec 设想的输入（`phase`/`checklist_done`/`user_mandated` + closure 块，`spec-structured-input-contract-20261016.md:69,186`）未实现。
4. **questions**：单题 `release_action`、type=choice、choices `[commit, version-bump, publish, hold]`（dpts.py:624-628）；无 labels/criteria/instructions（FIX-O 文案只给了 dp1/2/3/8，`WIRED_DP_IDS` test_decision_points.py:323-329）；questions_version `q-6d26173d`（钉死表 test_decision_points.py:347，:411-416 断言不漂移；hash 只覆盖 shape 键 `VERSIONED_QUESTION_KEYS` dpts.py:193）。
5. **答案采纳**：与共用机制相同——只留痕（suggested/acted=false，dpts.py:1941-1976）；intent=act 则 over-authority/no executor（dpts.py:1978-1996）。无执行器（executor=None，非 `_unwired_executor`）。
6. **风险语义**：P0 → 注册默认 off；开启必须 `mw decide dp on dp13-commit-release --i-understand-p0`（mw.py:1806-1818, :9780-9784），否则不写表 exit 2。

### dp14-rule-conflict

1. **注册身份**：dpts.py:632 `dp_id="dp14-rule-conflict"`，:633 `tier="P0"`，:634 description「用户指令 vs 规则」，:635 p0_consequences「越过项目硬规则会改变授权边界，影响后续所有会话」。
2. **触发点**：未接线。spec 节奏「偶发」（spec.md:83，锚 AGENTS.md:166）；引用面仅 decision-tool.ts:124 + mw.py:947。
3. **state 形状**：泛型 builder，零必需字段，无动态键（见共用机制）。
4. **questions**：单题 `conflict_resolution`、choice、`[follow-rule, follow-instruction, ask-human]`（dpts.py:637-641）；无 labels/criteria/instructions；questions_version `q-b667b8d3`（test_decision_points.py:348）。
5. **答案采纳**：同共用机制：只留痕（dpts.py:1941-1976）/ over-authority（:1978-1996）；executor=None。
6. **风险语义**：P0 → 默认 off，开启需 `--i-understand-p0`（mw.py:1806-1818）。

### dp15-autopilot-gate

1. **注册身份**：dpts.py:645 `dp_id="dp15-autopilot-gate"`，:646 `tier="P0"`，:647 description「6 类人工门」，:648 p0_consequences「自动越过 autopilot 人工门会让无人监管的推进落地，单次最贵的不可逆面」。
2. **触发点**：未接线。spec 节奏「本仓 0 次（常关闭）」（spec.md:84，锚 autopilot/gates.py:82）；引用面仅 decision-tool.ts:125 + mw.py:947。
3. **state 形状**：泛型 builder，零必需字段，无动态键。
4. **questions**：单题 `gate_decision`、choice、`[continue, narrow, revoke]`（dpts.py:650）；无 labels/criteria/instructions；questions_version `q-09e25bec`（test_decision_points.py:349）。
5. **答案采纳**：同共用机制：只留痕 / over-authority；executor=None。
6. **风险语义**：P0 → 默认 off，开启需 `--i-understand-p0`（mw.py:1806-1818）。

### dp16-goal

1. **注册身份**：dpts.py:654 `dp_id="dp16-goal"`，:655 `tier="P0"`，:656 description「goal 确立/变更」，:657 p0_consequences「改项目级目标会让所有 worker 的方向对齐失效，历史上不可追溯」。
2. **触发点**：未接线。spec 节奏「每项目/变更」（spec.md:85，锚 goal.md:39）；引用面仅 decision-tool.ts:126 + mw.py:947。
3. **state 形状**：泛型 builder，零必需字段，无动态键。
4. **questions**：单题 `goal_decision`、choice、`[keep, amend, defer]`（dpts.py:659）；无 labels/criteria/instructions；questions_version `q-ba34304c`（test_decision_points.py:350）。
5. **答案采纳**：同共用机制：只留痕 / over-authority；executor=None。
6. **风险语义**：P0 → 默认 off，开启需 `--i-understand-p0`（mw.py:1806-1818）。

### dp17-spec-lock

1. **注册身份**：dpts.py:663 `dp_id="dp17-spec-lock"`，:664 `tier="P1"`，:665 description「spec/AC 锁定」；无 p0_consequences（P1 不要求，dpts.py:340-343 只约束 P0）。
2. **触发点**：未接线。spec 节奏「每 key」（spec.md:86，锚 requirements.md:380）；引用面仅 decision-tool.ts:127 + mw.py:947。
3. **state 形状**：泛型 builder，零必需字段，无动态键。
4. **questions**：单题 `spec_lock`、choice、`[lock, reopen, amend]`（dpts.py:667）；无 labels/criteria/instructions；questions_version `q-f81bd06d`（test_decision_points.py:351）。
5. **答案采纳**：同共用机制：只留痕 / over-authority；executor=None。
6. **风险语义**：P1 → 注册默认 off；开启走普通 `mw decide dp on dp17-spec-lock`，**不需要** `--i-understand-p0`（P0 门只看 tier，mw.py:1807-1808）。

### dp18-claim

1. **注册身份**：dpts.py:671 `dp_id="dp18-claim"`，:672 `tier="P1"`，:673 description「key 抢占冲突」；无 p0_consequences。
2. **触发点**：未接线。spec 节奏「偶发」（spec.md:87，锚 pm/ui-bridge.ts:415）；引用面仅 decision-tool.ts:128 + mw.py:947。
3. **state 形状**：泛型 builder，零必需字段，无动态键。
4. **questions**：单题 `claim_conflict`、choice、`[wait, steal, new-key]`（dpts.py:675）；无 labels/criteria/instructions；questions_version `q-094db8cc`（test_decision_points.py:352）。
5. **答案采纳**：同共用机制：只留痕 / over-authority；executor=None。
6. **风险语义**：P1 → 注册默认 off；开启无 `--i-understand-p0` 门。

### 未接线清单（六个全部命中）

逐 dp 写明：**未接线（已查下列关键词，生产代码零调用点）**。

- 关键词 1：`dp13|dp14|dp15|dp16|dp17|dp18`（regex）扫 `packages/**`、`docs/**`、`.agenticdoc/mw-decision-substitution/**`（*.py/*.ts/*.md/*.json，排除 node_modules/dist/__pycache__/.mw runs）。命中仅：注册块 dpts.py:619/632/645/654/663/671；TS id 枚举 decision-tool.ts:123-128；`REQUIRED_FIELDS_BY_DP` 的 dp13 行 triage-client.ts:376；tier 钉死表 test_decision_points.py:42-47、questions_version 钉死表 :347-352、TS drift 锁 triage-client-state.test.ts:496；文档 docs/decision-substitution.md:66-71。
- 关键词 2：`decide_for\(` 扫 `packages/multi-workers/*.py` → 生产调用点唯一：mw.py:947（`mw decide run`，`intent="answer"`）；其余全是 test_decision_points.py。
- 关键词 3：`dp1-dispatch-type|dp2-checkpoint-split|dp3-worker-clarify|decide run|decide ask|decide_for` 扫 `packages/coding-agent/src/extensions/agent-team-loop/**/*.ts` → 专用调用常量只有 dp1（triage-client.ts:75 `DP1_ID`）、dp2（pm/pm-orchestrator.ts:1958 `DP2_CHECKPOINT_ID`）、dp3（worker/worker-mode.ts:4425 `DP3_ID`）；dp13..dp18 无对应物。
- 关键词 4：`closure` 扫 agent-team-loop/**/*.ts → 只有 triage-client.ts 校验表（:338/:376/:485-489/:664-668），无 dp13 生产组装点。
- 关键词 5：`_decide_run|_decide_ask|_ASK_DP|i-understand-p0` 扫 mw.py → `_decide_run` :905（唯一过 decide_for 的通道）、`_decide_ask` :1413 + `_ASK_DP` :1128（绕开注册表）、P0 门 :1806-1818/:9780-9784。

### 本仓配置表现值（只读直读，未跑 CLI）

`.mw/decide-points.json`（version=1，updated_at=2026-10-21T03:39:33Z，updated_by=refresh）：dp13/dp14/dp15/dp16 = `tier P0, enabled=false, mode=auto`；dp17/dp18 = `tier P1, enabled=false, mode=auto`。与注册默认一致，无人为开启记录。

## 残留与未验证

- 未跑 `mw decide dp list`（卡禁）；enabled/mode 现值改由直读 `.mw/decide-points.json` 取得，与注册默认一致，风险低。
- questions_version 六个值取自 test_decision_points.py:347-352 的钉死表（:411-416 与活注册表断言绑定）；未本地重算 hash（避免无必要地执行注册表导入；语义上等价）。
- `escalated_reason="p0"`（dpts.py:113）预留无生产者：若未来 P0 confirmation path 落地，本文「答案采纳」段对 P0 四者的描述需要更新。
- dp13 的 TS `closure` required_if（triage-client.ts:376）与 Python `REQUIRED_STATE_FIELDS` 无 dp13 条目之间的不对齐是既有事实（ds-fix-a-ask-authority 报告已记录其对齐决策）；本文只记录现状，不判对错。
- 汇总表「触发点」列的 decision-tool.ts:123-128 行号是该 dp id 在 `ASK_DECISION_DP_IDS`（:110-137）内的位置，不是调用点——六个 dp 的真实答案获取通道仍是手工/工具化 `mw decide run`。

## 上下文来源

- `packages/multi-workers/decision_points.py`（:58-59, :73-75, :83, :90, :105-114, :124, :185-199, :280-296, :300-348, :349-369, :372-382, :385-411, :411-417, :418, :618-677, :765, :827-860, :872-923, :956-958, :1525, :1532, :1574, :1666-2095, :2097-2111）
- `packages/multi-workers/mw.py`（:698, :812, :852-903, :905-960, :1128, :1413-1470, :1806-1822, :1937-1938, :9780-9794）
- `packages/multi-workers/decision.py`（:98, :112-118）
- `packages/multi-workers/decide_signoff.py`（:240-254）
- `packages/multi-workers/test_decision_points.py`（:26-47, :257, :309-318, :323-359, :411-416）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`（:19-56, :86-89, :110-137, :146-150, :264-277, :283-309, :422-436, :512-527, :579-676, :744-781, :838-866）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`（:58, :75, :341-377, :485-489, :530）
- `packages/coding-agent/test/suite/triage-client-state.test.ts`（:479-496）
- `packages/multi-workers/decision_points.py` 注册邻居对照：dp21/22/23 的 `_unwired_executor`（dpts.py:703/:716/:725 + :372-382）
- `docs/decision-substitution.md`（:46-49, :57-80）
- `.agenticdoc/mw-decision-substitution/spec.md`（§4 :82-87）、`design.md`（:180 D-029）
- `.agenticdoc/mw-decision-substitution/evidence/research/spec-structured-input-contract-20261016.md`（:69, :146, :186）
- `.mw/decide-points.json`（全量直读，2026-10-21）
