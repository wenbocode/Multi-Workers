# Research: autopilot done 事务失败原文回传路径与集成面（design）

> Key: mw-done-closure-repair / RQ-1（design 阶段，只读代码调研，未改任何源码）
> 日期: 2026-09-25
> 姊妹篇: design-marker-mechanics-20260925.md（RQ-2 marker 机制）、design-reprompt-loop-20260925.md（RQ-3 派发/预算/守卫/prompt 面）；本文引用其结论编号，不重复展开。

## 决策问题

支撑 design 对「失败原文回流 L3 回路」（spec §1.1 改动点 1）中**回传通道与调用面**的选型：

1. `_done_transaction`（conductor.py:1319-1409）的返回值语义（advanced/below/gated）与全部调用点：`_verify_loop` 之外是否还有调用方，每个调用点如何消费返回值。
2. advance 失败原文（err）在事务内的当前位置与流向：`advance.advance` 返回 (code, _out, err) 后 err 去了哪里（`_record_advance_result`？timeline config 事件？），返回 "gated" 时 err 是否被丢弃；把 (verdict, err) 带回调用方的可选方案（a 元组 / b 小 dataclass / c 经 ConductorState 字段）的调用点改动数与测试破坏面。
3. 现有测试影响面：test_autopilot_conductor_exec.py / test_autopilot_conductor.py 中断言 `_done_transaction` 返回值或副作用的用例清单，哪些会因返回值形态改变而需要调整。
4. `_verify_loop` 内 gate-blocked reprompt 派发点的插入位置（meets → `_done_transaction` 返回 gated 处）与 used/l3_limit/rounds 计数器的交互；`_advance_failure_streak` 的 streak 语义（dispatch 事件是否打断 streak——walk 逻辑逐行确认）。

## 调研方法与出处（file:line）

- 只读代码核验（本 session，2026-09-25）：
  - `packages/multi-workers/autopilot/conductor.py`（全文 2054 行通读；关键行号经独立 grep 二次锚定）
  - `packages/multi-workers/test_autopilot_conductor_exec.py`（667 行全文）、`packages/multi-workers/test_autopilot_conductor.py`（787 行全文）
  - `packages/multi-workers/autopilot/advance.py`（advance 包装 advance.py:174-192）、`dispatch.py`（dispatch 事件 dispatch.py:585-590、REGISTRY dispatch.py:60-106、DispatchResult dispatch.py:336-352）、`state.py`（used_rounds state.py:224-247）、`timeline.py`（有界尾部 timeline.py:438-442）
  - 标准模板 `.agents/skills/agentic-task/scripts/advance_phase.py`（本仓 .agentic-framework marker 指向，commit d7004d0）：done 门禁表 advance_phase.py:69-92、check_gate 191-289、GATE BLOCKED stderr 输出 584-591
  - 交叉基线测试：`test_autopilot_stall.py`（streak 语义 118-132、stall 基线 166-210、credits 抬升 277-333）、`test_autopilot_e2e.py`（e2e_l2 链路 477-561、stub L3 输出 268-279、真实框架拷贝 42/110-111）
- 唯一性/扫描证据：packages/multi-workers 全量 grep `_done_transaction`（唯一调用点结论）；对 `packages/multi-workers/autopilot/*.py` 的词表字面量扫描（「系统行为变化」0 命中、「遗留」9 命中，见 F-11）
- 未运行任何测试/e2e_l2（只读边界）；F-12 为代码级推断并已标注
- 前置研究：spec-code-facts-20260924.md（F1-F16）、spec-incident-and-alternatives-20260924.md

## 发现（F-1..F-12）

### RQ-1：返回值语义与调用点（F-1/F-2）

- **F-1 返回值域与 9 个 return 点**。签名 `(project_root, st, key, l3_output) -> str`（conductor.py:1319-1324），docstring 声明 advanced | below | gated（conductor.py:1325-1327）。事务步骤序与 return 点：
  - `advanced` ×2：conductor.py:1332（入口幂等——index 已 DONE = crash-after-advance 恢复）；1406（全链成功）
  - `below` ×3：conductor.py:1336（l3_output 读失败 OSError）；1340（缺 `## Quality Gate Report` 或 `## Achieved` 节）；1376（achieved 草稿 <200B 后验，前置 config 留痕事件 1372-1375）
  - `gated` ×4：conductor.py:1379（pm-state PASS 行锁被占，注释 "retry next tick"）；**1389（advance exit≠0——本 key 的目标场景）**；1405（advance exit=0 但 index 失配且 set-phase 重跑仍失配，前置 mark_stalled 1400-1404）；1409（事务内 OSError，前置 config 事件 1408）
  - 步骤序（check-before-write，AC-022）：QG report write-once（1346-1359）→ `_persist_l3_verdict("meets")`（1362）→ achieved.md 转写（≥200B 守卫：仅 absent/short 才写，1363-1369）→ 200B 后验（1371-1376）→ PASS 行（1377-1379，`_append_pass_line` def 1272）→ advance done（1381-1383）→ `_record_advance_result`（1384-1387）→ exit≠0 gated（1388-1389）→ index 后验 + set-phase 重跑（1390-1405）。
- **F-2 唯一调用点 + 二值坍缩消费**。packages/multi-workers 全量 grep：`_done_transaction(` 的调用点**仅一处**——`_verify_loop` meets 分支 conductor.py:1229；def 在 conductor.py:1319。无其他模块（mw.py / dispatch.py / state.py / timeline.py…）引用；测试侧无直接调用、无 monkeypatch（test_autopilot_conductor_exec.py:402 仅是用例名 test_meets_done_transaction 含该词）。消费方式（conductor.py:1229-1230）：`if _done_transaction(project_root, st, key, l3_output) != "below": return False`（注释 "advanced (or gated — retried next tick)"）——**advanced 与 gated 坍缩为同一动作**，调用方既无法区分两种结局、也拿不到任何失败信息；below 才落入既有 below/repair 路径（1231 注释，1232 起）。⇒ 返回面改动的机械影响完全局部于这 1 行调用 + 9 个 return 点（F-1），无外部消费者。

### RQ-2：err 流向与回传方案（F-3..F-6）

- **F-3 err 的唯一去向 = `_record_advance_result`，gated 返回时作为值被丢弃**。`code, _out, err = advance.advance(key, "done", project_root, summary="autopilot L3 meets")`（conductor.py:1381-1383；包装层 advance.advance 返回 `(returncode, stdout, stderr)`，advance.py:174-192，子进程 stderr 原样透传）。err 随即传入 `_record_advance_result(project_root, st, key, "verify->done", code, err, cfg)`（conductor.py:1384-1387），函数体（conductor.py:809-847）：
  - exit=0：仅 timeline `advance` 事件 `verify->done exit=0`（826-829）；
  - exit≠0：`_classify_advance_failure(err)`（830）→ `advance` 事件 `verify->done exit=1 class=gate-blocked`（831，**不含 err 原文**）→ `config` 事件 `advance verify->done failed: {_one_line(err, 200)}`（832-834）→ streak 检查（835-836），达 advance_stall_ticks 则 mark_stalled（837-846）。
  之后 `if code != 0: return "gated"`（1388-1389）——**err 不随返回值传出**，其唯一持久化形态是 832-834 的 config 事件，且已经 `_one_line`（conductor.py:710-715：`" ".join(text.split())` 压平全部换行 + 200 字符截断）处理。
- **F-4 timeline 通道不满足 AC-002（逐字原文）**。done 门禁失败 stderr 是多行块（advance_phase.py:584-591）：`GATE BLOCKED: {key} cannot advance to 'done'` + `   Current phase: {current}` + 逐条 `   - {failure}`；check_gate 产出 `MISSING:` / `TOO SMALL:` / `NO MATCH:` 前缀行（advance_phase.py:203, 205-207, 227）。压平 + 200 字符截断后逐行结构不可恢复（首行 + Current phase + 第一条 NO MATCH 即超 200 字符），且 timeline 尾部有界（timeline.py:438-442：400 事件/512KiB）已被 spec §5 明令排除为判定依据。⇒ **原文必须走函数返回通道（本 RQ）或 marker 落盘通道（RQ-2 姊妹篇 F-8/结论 4 已定：marker `failures` 字段承载逐行原文）**；两通道互补——返回通道供同 tick 分支决策，marker 供跨 tick 持久与哈希绑定。
- **F-5 分类稳定性（gate-blocked 判定现成可靠）**。stderr 含 "GATE BLOCKED" → 小写命中 `_GATE_BLOCKED_MARKERS`（conductor.py:700-703）的 "gate blocked"（匹配逻辑 717-733 先序探针：interface-drift markers 696-699 与 done 门禁输出无词面交集——"Current phase: verify" 不含 "unknown phase"/"phase-line"/"phase field" 等；timeout-env markers 704-707 亦无交集）→ class 恒 gate-blocked。done 门禁 achieved.md 规则的 path_pattern 字面量即 "achieved.md"（advance_phase.py:71-86）→ 涉稿失败行天然含 "achieved.md"（spec §4「已决」判定的来源）。注意该输出契约属模板可演进（spec §4 风险）：分类失败时退化为现状不 reprompt，不劣于现状。
- **F-6 (verdict, err) 回传三方案对比**（调用点改动数 = 修改 conductor.py:1229-1231 一处；return 点改动数 = F-1 的 9 处）：

  | 方案 | 调用点改动 | return 点改动 | 新增定义 | 测试破坏（两文件） | 评注 |
  |---|---|---|---|---|---|
  | a) 元组 `-> tuple[str, str]` | 1（1229-1230 改 unpack + 三分支展开） | 9（below/advanced 路第二元 err=""） | 0 | **0** | 代码库同型先例：`_l3_round_verdict`（conductor.py:1131）、`_advance_failure_streak`（744）、`_set_index_phase`（1304）。调用方用现成 `_classify_advance_failure(err)`（717-734）重导 cls，零冗余 |
  | b) 小 frozen dataclass（如 `DoneOutcome(verdict, err)`） | 1（属性访问） | 9（构造） | +1 类（先例 dispatch.DispatchResult，dispatch.py:336-352） | **0** | 命名自文档、可扩展第三字段（cls/失败行筛选）；比 a 多一个模块级名字 |
  | c) ConductorState 字段（如 `st.done_gate_err: dict[str, str]`） | 1（调后读 st 字段） | 0（各 gated 点写 st） | +1 字段（ConductorState conductor.py:138-148） | **0** | 隐藏数据流（签名不可见契约）；须事务入口清空防跨 tick/跨 key 残留；违背 D-102「zero private state, every decision re-derives from files」（orchestrate docstring conductor.py:169-171）；崩溃重启丢字段。可审查性最差，不推荐 |

  三案对两个指定测试文件均为 0 破坏（F-7/F-8：无直接调用/monkeypatch，断言全为副作用）。a/b 之差只在是否需要携带第三字段——按 spec §1.1 改动点 1 只需 (verdict, err)，cls 可由调用方从 err 重导（单一来源），**a 为最小充分方案**；b 在 design 预见字段扩张时可选。

### RQ-3：测试影响面（F-7/F-8）

- **F-7 test_autopilot_conductor_exec.py：done 事务族 6 用例逐条（断言面全为副作用，无返回值断言，返回值形态改变 0 破坏）**：
  1. `test_meets_done_transaction`（402-464）：l3-a1 task.md 形状（type/loop/attempt/read_scope）、QG report ×1、achieved 含 `## Achieved` 且 ≥200B、pm-state PASS、`calls == [("k1", "done")]`、index DONE、timeline `verify->done exit=0`、幂等重 tick（QG 不重复）、l3-verdict.txt=meets、l3-report.md、closure dossier 行。advanced 侧语义锚。
  2. `test_below_repair_reeval_then_stalled`（466-499）：below→repair-a1→l3-a2→2 轮 below→stalled、无 repair-a2。不触碰 meets 分支。
  3. `test_l3_budget_one_escalates_after_one_round`（501-533）：round_budget=1 下一轮 below 即 stalled + verdict 持久化 below。锁定 below 路径 l3_limit 语义（reprompt 预算封顶用例的直接模板，姊妹篇 F-23）。
  4. `test_missing_sections_and_short_achieved_are_below`（535-572）：缺节→below；meets+短稿→below（QG 先写、无 advance、phase VERIFY、stalled、config "200B" 留痕）。锁定 step-3 below（conductor.py:1371-1376）；**meets-but-degraded 场景的最近测试模板**。
  5. `test_advance_index_mismatch_set_phase_retry`（574-598）：monkeypatch `conductor._set_index_phase`；advance exit=0 + index 未写 → set-phase 重跑修复 → DONE + config "mismatch"。锁定 step-6 前半（1390-1397 → 1406 advanced）。
  6. `test_advance_index_mismatch_persists_human_gate`（600-626）：set-phase 重跑失败 → stalled + stalled gate + config "mismatch"。锁定 step-6 gated（1397-1405：mark_stalled 先于 gated return）。
  - **关键覆盖缺口：verify→done advance exit≠0（conductor.py:1388-1389）在全测试套件 0 覆盖**。`_fake_advance_factory` 的 done 失败分支（test_autopilot_conductor_exec.py:206-214 `return 1, "", "done gate failed (三件套)"`）在现有全部用例中**不可达**——事务总在 advance 前写齐三件套（1346-1379），mismatch 两用例的三件套也齐（仅 update_index=False）；`verify->done` 事件断言仅 exit=0 形态（本文件 434；e2e 侧 test_autopilot_e2e.py:556）。⇒ gate-blocked reprompt 分支是全新测试面；该 fake 失败分支是现成注入点（错误文本换成含 "achieved.md" 的真实 GATE BLOCKED 块即可驱动，姊妹篇 F-22 同结论）。行为面：只要 reprompt 仅在 cls=gate-blocked ∧ 失败行含 achieved.md 时触发，上述 6 用例行为均不变（mismatch 用例 err=""，不触发新分支）。
- **F-8 test_autopilot_conductor.py：0 影响**。该文件覆盖 tick/beat/goal/锁/CLI/status/serve + SPEC/TASKS 相位机（L1/L2），不触达 done 事务；advance 事件断言仅 `test_l1_clean_direct_advance`（444-479，exit=0）与 `test_transfer_events_all_carry_key_and_ts`（760-787，key/ts 非空），均非 verify→done。`test_conductor_source_never_writes_goal_or_phase`（221-237）为静态扫描（goal/Phase 写点），与返回值形态无关。交叉基线（非指定文件但语义直接锁定）：`test_autopilot_stall.py:118-132` `test_streak_broken_by_success_or_other_activity` 直接断言「dispatch 事件打断 streak」（128 插入 dispatch 事件后 count 归零重计）；`test_autopilot_stall.py:166-210` 锁定 advance_stall_ticks 连败→stalled 四件套 + 冻结（AC-006 依赖的现状基线）；`test_autopilot_stall.py:277-333` 锁定 resume credits 对 l3/repair 限的抬升。

### RQ-4：reprompt 插点与计数器/streak 交互（F-9/F-10）

- **F-9 插入点 = conductor.py:1229-1230 坍缩判定处展开为四分支**（唯一调用点，F-2）：
  - `advanced` → `return False`（不变；下 tick `_advance_key` 对 DONE key 走 `_mark_key_done`，conductor.py:865-866）；
  - `gated` ∧ `_classify_advance_failure(err) == "gate-blocked"` ∧ 失败行含 "achieved.md" → 派发 l3-a{used+1} reprompt（loop=l3:{key}、attempt=used+1、reviewer 类型、prompt 携带 err 原文行——词表零硬编码，F-11），`return result.ok`；
  - `gated` 其他（PASS 锁 1379 / OSError 1409 / index 失配 1405 / gate-blocked 但无 achieved.md 行）→ `return False` 维持现状重试（AC-006：无 reprompt，advance_stall_ticks 收敛）；
  - `below` → 落入既有 1232+ below/repair 路径（不变）。
  预算交互（AC-005）：reprompt 派发 l3-a{used+1} 前必须自持 `used < l3_limit` 检查——**meets 分支现状无任何预算检查**（1232 的 l3_limit 检查只对 below 路径可达；no-verdict 路径的同类检查在 1210-1215），即 P-009 无界形状；耗尽时 mark_stalled（镜像 1232-1238）。l3_limit = round_budget + `_resume_credits`（conductor.py:1181-1182；credits 语义 conductor.py:1711-1731：每个已批 stalled gate 对全部封顶回路各 +1 轮，不可复用）。rounds 派生：`rounds` 在 tick 起点由 orchestrate 从 worker task.md loop/attempt 标签派生（conductor.py:193；state.py:224-247 按 distinct attempt 计数，in-flight 即消耗）→ reprompt 的 attempt=used+1 计入**下一** tick 的 used；派发成功当 tick `return result.ok` → orchestrate:249-250 将 key 计入 in_flight。in-flight 守卫（AC-007 结构性满足，姊妹篇 F-13 同结论）：守卫在 meets 分支之前（conductor.py:1188-1190，前缀 `ap-{key}-l3-` / `ap-{key}-repair-`；`_is_in_flight` 1590-1592 = status 非 terminal）→ reprompt pending 期间后续 tick 直接 return False，`_done_transaction`/advance 不重跑。repair 家族互斥：repair:{key}（1239-1259，预算 1245）只属 below 路径；meets+gate-blocked 走 l3 家族（spec 场景 A 明确 l3-a{N+1}）。verdict 持久化警示：meets 时 step-1b 已 `_persist_l3_verdict("meets")`（1362）；若耗尽 stall 照抄 1233/1211/1246 的 `_persist_l3_verdict(key_dir, "below", ...)`，会经 631-637 的双向刷新把 meets 改写为 below → closure dossier 行（`_closure_dossier_md` conductor.py:699-708 读 l3-verdict.txt）随之翻转。design 必须显式决策耗尽时持久化什么（below 对齐 AC-012 no-verdict stall 先例 1211，或保留 meets）；l3_report_src（1184-1187，函数入口按 used 计算）可复用为报告源。prompt 载体：`_l3_prompt(key, attempt)`（1110-1120）现成，reprompt 需新入口携带失败行（AC-002 逐字要求 = 失败行不经改写进 prompt）。
- **F-10 streak 语义确认：dispatch 事件打断 streak（walk 逻辑逐行）**。`_advance_failure_streak`（conductor.py:744-807）walk 规则（docstring 750-756 + 代码 783-806）：最新→最旧、仅看同 key 事件——`beat` 跳过（783-784）；`config` 事件跳过且首个含 "advance" 的捕获为 error_text/snippet（785-790）；同 edge 失败 `advance` 计数（791-802）；同 edge exit=0 break（797-798）；**任何其他事件 → break（803，docstring 753-754 明列 dispatch / stalled / gate / stage）**。`dispatch.dispatch` 成功必写 `dispatch` 事件（dispatch.py:585-590，key=owner）。⇒ **gate-blocked 失败后派发 reprompt 会使 verify->done 失败 streak 归零**，下一条失败重新从 1 计。含义：(1) achieved.md 类失败（每次失败后必有 reprompt dispatch）的 advance_stall_ticks 停机守卫**失效**，收敛完全移交 l3 预算（AC-005）——与 spec §5 已记语义一致，本调研从 walk 代码 + `test_autopilot_stall.py:118-132` 测试锁定双确认；(2) 非 achieved.md 类失败无 dispatch，streak 正常累积至 stall（AC-006，基线 test_autopilot_stall.py:166-210）。时序交互：`_record_advance_result` 的 mark_stalled（837-846）在事务内、gated return（1389）**之前**执行——若某次失败恰达阈值会先 stall 再返回 gated；对 achieved.md 类首次失败 count=1 < 默认 5（conductor.py:735-742），reprompt 分支无同 tick stall+dispatch 双写风险；stalled key 下一 tick 被 orchestrate:232 跳过，reprompt 不与 stall 状态竞争。

### 集成面补充发现（F-11/F-12）

- **F-11 AC-002 的 rg 扫描判据字面不可满足（design 需收窄）**。AC-002 要求 `rg` 扫描 `packages/multi-workers/autopilot/*.py` 对「系统行为变化」「遗留」命中 0 次。现状扫描（本 session）：「系统行为变化」= 0 命中（合规）；「遗留」= **9 处既有命中**（conductor.py:1115 `_l3_prompt`「计入遗留」、1118 `_l3_prompt`「遗留什么」、1126 `_repair_prompt`「needs-rerun 遗留」、1807 closed-legacy docstring、1864 closed-legacy gate 文案、1873/1875 stalled 草稿模板「## 遗留问题」、1894/1898 stall-lesson 模板文案）——均为既有 prompt/模板文案，与门禁规则句式无关，reprompt 改动未发生即已违反字面判据。design 需明确扫描目标，可选：(i) 门禁规则句式（如「必含「## 系统行为变化」」「必含「## 遗留」」的 rule 描述文本，当前 0 命中）；(ii) 非自然词项字面量（「系统行为变化」+ AC-008 合成词表的 "Impact"/"Follow-ups"，当前均 0 命中）；(iii) 豁免既有文案清单并锁定 diff 零新增。本文只呈事实，判据选择归 design/PM。
- **F-12 e2e_l2 链路用例是词表缺口的仓内复现（代码级推断，未运行）**。`test_autopilot_e2e.py::test_full_chain_single_key`（477-561）把**真实**框架拷进 fixture（:42 `_FW_SRC = _REPO/.agents/skills/agentic-task`，:110-111 copytree）→ done 门禁真实执行；stub reviewer 的 `## Achieved`（:268-279）含「遗留」（"无遗留阻塞项"）但**不含「系统行为变化」**。推断链：事务转写该节为 achieved.md（conductor.py:1363-1369）≥200B → advance done 被 content_match r"系统行为变化" 拒（advance_phase.py:76-81，NO MATCH 行含 achieved.md）→ gated 每 tick 同因重放（坏稿 ≥200B 永不重写，1366-1368 守卫）→ 5 tick 后 mark_stalled（conductor.py:837-846）→ stalled pending gate 阻塞 stage-close（`_stage_closure` conductor.py:571-573：terminal 仅 done/closed-legacy，AC-024）→ 120s `_wait_until(stage-close)`（test_autopilot_e2e.py:537）超时 → 用例失败。该模块 `pytestmark = pytest.mark.e2e_l2`（:54）被 pytest.ini addopts 默认排除（`-m "not e2e_real and not e2e_l2"`）→ 默认套件不受影响，但 **opt-in e2e_l2 的 full-chain 用例在词表缺口下已不可绿**；修复后它是 AC-001 场景 A 最近的回归面（stub 需产出合规词表或经 reprompt 轮修正）。此为推断（未运行多进程链路，超出只读边界）；plan 阶段执行一次 `-m e2e_l2` 可低成本证实/证伪。

## 结论 → 决策映射

1. **（RQ-1→改动面）** 返回面改动完全局部：唯一调用点 conductor.py:1229 + 9 个 return 点（F-1/F-2），无外部消费者、无测试直接断言返回值。任何返回形态方案的机械改动面 = O(1) 调用点 + O(9) return 点。
2. **（RQ-2→通道选型）** err 在 conductor.py:1388-1389 被丢弃；唯一持久形态是 `_one_line(err, 200)` 压平 config 事件（832-834），不满足 AC-002 逐字要求，timeline 尾部又被 spec §5 排除 → **原文必须走返回通道**（同 tick 分支决策）+ marker 落盘通道（跨 tick 持久，姊妹篇 RQ-2 已定）。方案 a（元组）最小充分且合代码库惯例（1131/744/1304 先例）；b（dataclass）仅在预见字段扩张时值得；c（ConductorState 字段）隐藏契约、违背 D-102、有跨 tick 残留风险，不推荐。cls 不必随返——调用方用现成 `_classify_advance_failure`（717-734）从 err 重导。
3. **（RQ-3→测试面）** 两个指定文件 0 直接破坏（全部用例经 conductor.tick 驱动、断言副作用）；真实影响面是**新增**用例：verify→done exit≠0 路径现存 0 覆盖（F-7 缺口），`_fake_advance_factory` 的 done 失败分支（206-214）是现成注入点；`test_meets_done_transaction` / `test_missing_sections_and_short_achieved_are_below` 分别是 advanced / below 侧语义锚，reprompt 新用例并列扩展。
4. **（RQ-4→插点与预算）** gate-blocked 分支插在 1229-1230 展开处（advanced / gated-reprompt / gated-现状 / below 四分，F-9）；预算检查必须内嵌（used < l3_limit 才派发 l3-a{used+1}，镜像 1210/1232 先例）——meets 分支现状零预算检查即 P-009 无界形状；AC-007 由既有 in-flight 守卫（1188-1190）结构性满足；streak 被 dispatch 打断（750-756/803 + dispatch.py:585-590 + test_autopilot_stall.py:118-132）⇒ achieved.md 类失败收敛移交 l3 预算（AC-005），advance_stall_ticks 保留给非 achieved.md 类（AC-006）。耗尽 stall 的 verdict 持久化（meets 已写 1362 vs below 先例 1233，dossier 行随之翻转）是 design 待决点。
5. **（集成面→AC 判据）** AC-002 的 rg 判据字面不可满足（「遗留」既有 9 命中，F-11），design 需收窄扫描目标并写入 design 文档；e2e_l2 full-chain 用例是词表缺口的仓内复现（F-12，推断），修复后为 AC-001 场景 A 的最近回归面，建议 plan 阶段跑一次 `-m e2e_l2` 证实。

## 勘误（2026-09-25，dcr-review-spec-design 发现 2）

以下行号锚点经评审实测修正，实质内容均复核为真，下游消费以修正行号为准：
- F-7 引"_fake_advance_factory 的 done 失败分支（test_autopilot_conductor_exec.py:206-214）"——实际 def 在 ：158-185、失败 return 在 :175（姊妹篇 design-reprompt-loop F-21 正确引用 ：175）
- F-6 表格引"先例 dispatch.DispatchResult，dispatch.py:336-352"——实际 `class DispatchResult` 在 dispatch.py:371
- F-12 引 e2e `_wait_until(stage-close)` test_autopilot_e2e.py:537——实际 :541
