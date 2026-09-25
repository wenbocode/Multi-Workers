# Research: L3 reprompt 派发机制、预算交互与 prompt 安全面（design）

## 决策问题

支撑 design 阶段 gate-blocked reprompt（spec §1 改动点 1「失败原文回流 L3 回路」）的派发点选型与安全边界：
1. 派发 l3-a{N+1} 的机制前提（dispatch 签名 / task.md frontmatter / reviewer 工具集与 read_scope / task_key 命名）是否全部现成；
2. reprompt 复用 l3-a{N+1} stem 时轮次与预算如何派生、耗尽后走哪条 stalled 路径（AC-005）；
3. in-flight 守卫是否天然覆盖 reprompt、在飞期间事务/advance 是否不重跑（AC-007）；
4. 失败原文的来源链、信任级别与体积上界（prompt 注入素材评估，spec §2.3）；
5. reprompt 分支应补哪些 timeline 事件（测试断言面）；
6. 既有测试夹具可复用什么（AC-001/002/005/006/007/008 的用例基底）。

## 调研方法与出处（file:line）

- 代码核验（本 session，2026-09-25，只读，未改任何源码）：
  - packages/multi-workers/autopilot/dispatch.py（dispatch 事务 / render_task_md / REGISTRY / task_key_for）
  - packages/multi-workers/autopilot/state.py（used_rounds / parse_task_labels / find_orphans）
  - packages/multi-workers/autopilot/conductor.py（_verify_loop / _done_transaction / _record_advance_result / _advance_failure_streak / mark_stalled / _resume_credits / in-flight 守卫）
  - packages/multi-workers/autopilot/advance.py（子进程封装与 stderr 通道）；config.py（round_budget / advance_stall_ticks 默认）；timeline.py（事件词表开放性）
  - packages/multi-workers/mw_common.py（_TERMINAL_STATUSES / 队列解析与锁 / update_status）
  - 标准模板 .agents/skills/agentic-task/scripts/advance_phase.py（GATES['done'] / check_gate 失败行格式 / main stderr 输出；本仓 .agentic-framework marker 的 repo= 行指向该目录）
  - packages/multi-workers/test_autopilot_conductor_exec.py（L3 reprompt / 轮次递增 / 预算耗尽用例族）
- 前置研究：evidence/research/spec-code-facts-20260924.md（F1-F16）、spec-incident-and-alternatives-20260924.md（A3-A5）；本文引用其编号，不重复展开。

## 发现（F-1..F-23）

### RQ-1 dispatch 机制（F-1..F-5）

- F-1 dispatch 完整签名：dispatch(project_root, owner, stem, task_type, prompt, *, loop: str, attempt: int, read_scope=(), deny_globs=None, model="", timeline=None) 返回 DispatchResult(ok, reason, task_key, task_md, row_verified)（dispatch.py:399-412, 370-389）。loop/attempt 为必填 keyword-only。拒绝路径零队列行并各带事件：unknown-type / not-conductor-dispatchable / verifier-read-scope-required（type-rejected，dispatch.py:415-435）、target-config-unusable（target-config-rejected，dispatch.py:460-470, 495-503）。
- F-2 task.md frontmatter 渲染（render_task_md，dispatch.py:243-313）：type（:287）→ 可选 phase/model（:289-292）→ origin: conductor（:294）→ loop: {loop}（:295）→ attempt: {attempt}（:296）→ read_scope YAML 块列表（:298-300）→ config 存在时 l2_read_file_cap / l2_read_byte_cap（:301-304，值来自 _read_scope_caps dispatch.py:203-235；缺 config 不渲染，TS harness 默认 8 文件/65536B）→ deny_globs 单引号（:305-308）→ --- + prompt 正文 strip（:309-313）。写入 encoding="utf-8"、newline="\n"（dispatch.py:515-518）。
- F-3 reviewer 类型：REGISTRY（dispatch.py:70-105）中 reviewer = DispatchType("reviewer", _REVIEW_TOOLS, "pi", "timi", False)（dispatch.py:86-88）——工具集 _REVIEW_TOOLS = (read, find, grep, ls)（dispatch.py:52；无 write/edit/bash，GC-3）；requires_read_scope=False（registry 层不强制，唯一强制的是 verifier，dispatch.py:82-84）。conductor 的全部 l3 dispatch 仍显式传 read_scope=[.agenticdoc/{key}, .agenticdoc/goal.md]（conductor.py:1196, 1221, 1266）。角色映射 reviewer → review（mw_common.py:137-148）。因 task.md 带 read_scope，TS harness 读取限额对该 worker 生效（dispatch.py:203-235 记录的历史事故：caps 未渲染时 reviewer 把 8 次读全耗在上下文加载）——reprompt 把失败原文直接嵌入 prompt 正文，不消耗读取配额，恰好规避该坑。
- F-4 task_key 命名：task_key_for(owner, stem) = "ap-{owner}-{stem}"（dispatch.py:387-391）；ap- 前缀全局唯一于 conductor 派发（D-111），手工 task key 永不冲突。
- F-5 dispatch 事务三步（dispatch.py:515-583）：(1) 先写 task.md（:515-518）——崩溃间隙 = orphan 形态（origin: conductor 且无队列行），由 reconcile_orphans 下 tick 以同 loop/attempt 重插 pending、不耗新轮（conductor.py:1912-1953；state.find_orphans state.py:287-316；dispatch.py:13-21 模块 docstring）；(2) workers.lock（O_CREAT|O_EXCL，mw_common.py:1480-1493）下按 task_key upsert 队列行——同 stem 重派替换既有行、永不重复（dispatch.py:520-560），写经 _write_workers_file（tmp + os.replace，mw_common.py:1502-1507）；(3) 读回验证：恰好一行且 task_path/cli/status=pending 匹配 → row_verified（dispatch.py:572-583）。成功后（读回之后）追加 timeline dispatch 事件，detail = "{task_key} type={task_type} loop={loop} attempt={attempt}"（dispatch.py:585-590）。

### RQ-2 rounds 与预算派生（F-6..F-11）

- F-6 used_rounds（state.py:224-249）：per-loop used = 该 loop 下所有 */workers/*/task.md frontmatter 的去重 attempt 值个数（unit = attempt 标签，缺失时退化为 "@{task_dir}" 目录键，state.py:247-248）；同 attempt 的重派 / orphan 重插不加轮；in-flight 派发即计为已消耗（task.md 从 dispatch 事务起存在，state.py:233-235 docstring）。frontmatter 解析 parse_task_labels 宽容（state.py:150-177）。
- F-7 l3 预算派生（conductor.py:1176-1183）：l3_loop = "l3:{key}"（:1177）；l3_budget = max(1, cfg["round_budget"])（:1181；默认 2，config.py:43，合法域 >=1，config.py:55）；l3_limit = l3_budget + _resume_credits(project_root, key)（:1182）；used = rounds.get(l3_loop, 0)（:1183）。_resume_credits = 该 key 的 approved stalled gate 计数（conductor.py:1711-1731；每个被批门对每个封顶 loop 家族各 +1 轮，轮次单调、credit 不可复用）。
- F-8 reprompt 复用 l3-a{N+1} 时轮次自然递增：dispatch(stem="l3-a{used+1}", loop=l3:{key}, attempt=used+1) 写出新的 ap-{key}-l3-a{N+1}/task.md（F-5 步骤 1），其 attempt 标签成为 l3:{key} 的新去重 unit → 下一 tick used_rounds 递增为 N+1（F-6 机制）。同形先例两处：no-verdict 复评（conductor.py:1218-1222）与 repair 完成后的下一轮（conductor.py:1263-1267）。
- F-9 预算耗尽的 mark_stalled 路径（全部经 mark_stalled conductor.py:1835-1909：key-status stalled + stalled gate（:1862-1866）+ achieved.md 遗留草稿 + pattern 文件 + stalled 事件（:1907））：
  - below 轮耗尽：_persist_l3_verdict(below) + mark_stalled("L3 below {l3_limit} rounds (budget {l3_budget}, credits ...)")（conductor.py:1232-1238）；
  - no-verdict 耗尽：mark_stalled("L3 无裁决（worker {status}: {round_key}）达 {used}/{l3_limit} 轮")（conductor.py:1210-1216）；
  - repair 预算（round_budget + credits）耗尽：mark_stalled("repair exhausted {repair_used} attempts at L3 round {used}")（conductor.py:1245-1251）；
  - advance 连败：_record_advance_result 在同 edge 连续 advance_stall_ticks（默认 5，config.py:47,59）次失败后 mark_stalled（conductor.py:841-846）。
- F-10（缺口，design 必须处理）meets-but-gated 路径今天不受 l3 预算封顶：verdict == meets → _done_transaction 返回 "gated" → 立即 return False（conductor.py:1229-1230），控制流到不了 :1232 的 used >= l3_limit 检查——该检查只对 below（及 meets-but-short 落入的 below 路径）可达。现状 meets+gated 的唯一界是 advance streak（F-9 第 4 条）。新 gate-blocked reprompt 分支必须自带 used >= l3_limit 封顶 + mark_stalled（AC-005 的「l3 家族 dispatch 总数 <= 预算上限 + 首轮」）。
- F-11 streak 交互：reprompt 派发会打断 advance 失败 streak——_advance_failure_streak 的 timeline 回溯把该 key 的任何其他事件（dispatch / stalled / gate / stage...）视为进展并终止计数（conductor.py:744-807）。即 reprompt 一旦派发，5-tick stalled 兜底即复位；reprompt 回路的唯一界是 l3 预算（F-10 的封顶）——设计不可依赖 streak 界。

### RQ-3 in-flight 守卫（F-12..F-14）

- F-12 _is_in_flight(row) = status 不在 _TERMINAL_STATUSES（conductor.py:1590-1591）；_TERMINAL_STATUSES = {"done", "failed", "needs-clarification"}（mw_common.py:156）。
- F-13 双层守卫，reprompt（同 l3 前缀）天然被覆盖：
  - orchestrate 层：in_flight_keys 收集所有 _is_in_flight 且 _row_belongs_to 的 key（conductor.py:216-221；_row_belongs_to = task_key 前缀 ap-{key}- 或 task_path 含 .agenticdoc/{key}/workers/，conductor.py:1594-1598），命中即 continue（conductor.py:245-246）——_advance_key 根本不被调用；
  - _verify_loop 层：开头 for prefix in ("ap-{key}-l3-", "ap-{key}-repair-") 任一 in-flight 行 → 立即 return False（conductor.py:1188-1190），位于 meets 分支（:1225）与 _done_transaction 调用（:1229）之前。
  reprompt 的 task_key = ap-{key}-l3-a{N+1} 以前缀 ap-{key}-l3- 开头 → 在飞期间不重跑事务 / advance / 派发（AC-007 的机制基础），无需扩守卫（前置研究 F7 在此逐行确认）。
- F-14 worker 完成的观察协议：状态翻转走 _workers.parallel 行（launcher 侧 update_status，mw_common.py:1513-1527）；_l3_round_verdict 先查行状态再读 output.md——failed/needs-clarification 恒 no-verdict（conductor.py:1131-1160）。崩溃间隙（task.md 有、队列行无）由 orphan 愈合，同 loop/attempt、不耗轮（F-5）。

### RQ-4 prompt 安全面（F-15..F-18）

- F-15 失败原文的产出（标准模板）：check_gate（advance_phase.py:191-290）按 GATES 表（:41-92）逐规则产出一行 failure；GATES['done']（:69-89）共 5 条规则：achieved.md >=200B（file_min_bytes）、achieved.md 含「系统行为变化」（content_match）、achieved.md 含「遗留」（content_match）、pm-state.md 含 PASS（content_match）、evidence/quality-gate-report-*.md >=1（glob_has_files）。行格式（前缀 + 路径 + 数值/模式 + 规则描述）：
  - MISSING: {path} — {desc}（advance_phase.py:203, 223, 250, 267）
  - TOO SMALL: {path} ({size}B < {min}B) — {desc}（:205-207）
  - MISSING DIR: {path}/ — {desc}（:212）
  - TOO FEW: {path}/ has {n} .md files (need >= {m}) — {desc}（:215-218）
  - NO MATCH: {path} missing pattern '{pattern}' — {desc}（:227）
  - glob 变体 MISSING: {path} (0 matches) — {desc}（:263）
  main() 在 gate 失败时向 stderr 输出 "GATE BLOCKED: {key} cannot advance to '{target}'" + "   Current phase: {phase}" + 每失败一行 "   - {failure}"，exit 1（advance_phase.py:585-591）。失败行以 "   - "（3 空格 + 连字符）为稳定可解析前缀。
- F-16 传输链与捕获点：advance.advance()（advance.py:164-192）以子进程 capture_output + text + encoding="utf-8" + errors="replace" 运行，timeout 120s（advance.py:36），child 强制 -X utf8（:41，防 Windows cp936 把中文诊断毁成 '?'）；返回 (code, stdout, stderr) 原样透传。conductor 侧 err 只在 _done_transaction step 5 调用点的作用域内可见（conductor.py:1381-1383）；今天它唯一去向是 _record_advance_result 的 timeline config 事件，且被 _one_line(err, 200) 截断（conductor.py:833-835）——全文不落盘。_done_transaction 的返回契约是裸字符串 "advanced"|"below"|"gated"（conductor.py:1319-1326），err 不随返回值传出：reprompt 分支要拿逐行失败原文，捕获点必须在 conductor.py:1381-1383 处（或扩展返回契约），不能从 timeline 回读（200 字符截断 + 尾部 400 事件/512KiB 有界，前置研究已否决 timeline 作为判定数据源）。
- F-17 信任级别评估：
  - 失败行 = 框架模板常量（GATES 规则元组的路径 / 模式 / 描述字符串）+ 数值（文件字节数、.md 计数）。文件内容从不进入失败行——content_match 引用的是规则里的 pattern 字面量而非文档文本（advance_phase.py:227）；file_min_bytes 只放字节数（:205-207）。即失败原文不是任意用户输入，是模板代码产出。
  - 但安装的框架是 per-project 的（.agentic-framework marker repo= 指向、或 .agents/skills/agentic-task 目录副本，advance.py:46-63 探测序）——被驱动工程可改自己的 GATES 描述字符串。故信任级别 = 工程自身配置级（与 conductor 已经当子进程执行的 advance_phase.py 同级），不是第三方任意输入。reprompt 的消费者（reviewer）本就运行在该工程内、只读工具集（F-3），把该文本嵌入其 prompt 不授予任何新能力；残余风险 = 对 reviewer 自身 output.md 的 prompt 影响力，由「判定不代写」机制兜底：achieved.md = ## Achieved 节逐字转写（conductor.py:1365-1370）、QG/PASS 转写路径不动（前置研究 F13）、reviewer 无 write 工具（F-3）。「工程词表字面量不进框架源码」（spec §2.3 / AC-002 后半）由该产出机制天然满足：词表唯一来源 = 失败原文。
  - 体积上界：失败行数 <= GATES['done'] 规则数 = 5（每规则 <=1 行；唯一可多行的是 mermaid 规则 :245-249，done 无此规则）；单行长度上界 = 规则描述常量（最长 ~90 CJK 字符 ~270B）→ reprompt prompt 增量 <= 5 行（~1.5KB）。失败原文 per-attempt（每次 advance 的 err 独立），跨轮不累积、无放大回路。
- F-18 _l3_prompt 现有文案结构（conductor.py:1110-1120）：两节强制（output.md 必含 ## Quality Gate Report（VC 断言表逐条 PASS/FAIL + needs-rerun + 证据引用）与 ## Achieved（达成摘要：做了什么 / 目标收益 / 遗留什么））+ 证据记录制（审查 EXECUTE 期 [VERIFY] 输出、不重跑命令、needs-rerun 计入遗留）。reprompt prompt = 该基底（~300B）+ 失败原文逐行 + 合规子节指示（## Achieved 内组织子节；_md_section 以 "## " 为节边界、### 子节完整保留并随事务逐字转写，conductor.py:1073-1086，前置研究 F11）。编码与注入面：task.md 写入 encoding="utf-8"、newline="\n"（dispatch.py:518）；prompt 正文位于已闭合 frontmatter 之后（dispatch.py:309-313），parse_task_labels 在第二个 --- 停止（state.py:160-166）——prompt 内含 --- / # 不破坏标签解析，无 YAML 转义问题；失败原文经 -X utf8 + errors="replace" 通道（F-16）保持 CJK 字面量完整。

### RQ-5 时间线事件（F-19..F-20）

- F-19 reprompt 派发产生的事件（单 tick 内顺序）：
  - advance 事件，detail="verify->done exit=1 class=gate-blocked"（conductor.py:831；分类 _classify_advance_failure / _GATE_BLOCKED_MARKERS，conductor.py:700-706, 717-733——"GATE BLOCKED" 小写含 "gate blocked" 即命中）；
  - config 事件，detail="advance verify->done failed: {_one_line(err, 200)}"（conductor.py:833-835）；
  - dispatch 事件，detail="ap-{key}-l3-a{N+1} type=reviewer loop=l3:{key} attempt={N+1}"（dispatch.py:585-590）。
  队列读回验证无专用事件（row_verified 只在 DispatchResult 上，dispatch.py:572-583）；测试断言队列走 mw_common.parse_workers_file（test_autopilot_conductor_exec.py:83-88 的 _rows helper）。mark_stalled 附带 gate-created（_create_gate，conductor.py:1618-1644，事件行 :1642）+ stalled（conductor.py:1907）事件。
- F-20 事件词表开放 + 建议补充：EVENT_TYPES 仅用于 console 过滤，未知 ev 值照常 append（timeline.py:66-72）——新增专用事件（如 l3-reprompt）无需改 timeline.py（若要进 console 默认过滤视图则同步加词表）。同分支先例：l3-no-verdict（conductor.py:1206-1208）。建议 gate-blocked reprompt 分支补：一条 config（或专用）事件携带失败原文的 _one_line 限长摘要（参考 conductor.py:833-835 的 200 字符界；_one_line 定义 conductor.py:710-715，gates.create 拒绝多行 question，故 stall reason 也须单行）——全文只进 prompt，不进 timeline detail；轮次断言用现成 dispatch 事件的 loop/attempt detail（F-19）；AC-006 的「无 reprompt」断言用 l3 家族 dispatch 计数 + 既有 stalled 路径事件。

### RQ-6 测试先例（F-21..F-23）

- F-21 夹具栈（test_autopilot_conductor_exec.py）：_project（:32-40，goal.md + enabled config）→ _key_project（:42-72，running roadmap + _index.parallel phase 行）→ _verify_key_project（:387-401，VERIFY key + 超尺寸 spec/design/plan + achieved.md 临时稿 + tasks/）；helpers：_state（:74）、_events（:79）、_rows（:83-88）、_set_row（:90-99，状态翻转注入 worker 行为）、_worker_output（:101-105，写 worker output.md）；产物常量 _L3_MEETS（:129-143）、_L3_BELOW（:144-156）；_fake_advance_factory（:158-185）——gate 校验 fake，done 分支检查 achieved>=200B + pm-state PASS + QG report 存在，但失败时返回泛化串 "done gate failed (三件套)"（:175），无真实失败行格式。
- F-22 reprompt 用例（AC-001/AC-002/AC-008）需要 fake 产出真实 stderr 形状：早期调用返回 (1, "", "GATE BLOCKED: k1 cannot advance to 'done'\\n   Current phase: VERIFY\\n   - NO MATCH: achieved.md missing pattern '系统行为变化' — ...\\n   - NO MATCH: achieved.md missing pattern '遗留' — ...")（F-15 格式；AC-008 的第二套合成词表 fixture 换 'Impact'/'Follow-ups'），marker 授权改稿后返回 (0, "advanced", "")。断言复用：读 .agenticdoc/k1/workers/ap-k1-l3-a2/task.md 的 prompt 正文含失败原文逐字行（先例：test_meets_done_transaction 读 l3 task.md 断言 frontmatter，:411-417）；_rows(project, "ap-k1-l3-") 家族计数（:488 先例）；roadmap key_status stalled（:495-497, :521-524）；l3-verdict.txt / l3-report.md（:526-529）；timeline _events 过滤断言（:572-573 先例：config 事件 detail 子串）。
- F-23 预算/收敛用例先例：test_l3_budget_one_escalates_after_one_round（:501-533）用 config.save_config 置 round_budget=1（:509-510）——AC-005 的 reprompt 耗尽用例直接复用该模式；test_missing_sections_and_short_achieved_are_below（:535-573）展示 meets-but-short → below → 2 轮耗尽 stalled 的完整形状与 config 事件断言（:572-573）；test_meets_done_transaction（:402-464）锁定事务产物全集 + 幂等（:443-445，QG report 不重复）+ closure dossier 行（:455-460）；test_below_repair_reeval_then_stalled（:466-499）锁定 repair → l3-a2 的轮次递增断言写法（:485-490）；AC-007（在飞不重跑 advance）断言可仿 test_kill_restart_invariants（:628-678）的「事件计数不变 + trace mtime 不变」模式。

## 结论 → 决策映射

- F-1/F-4/F-5 → 改动点 1 的派发原语零新增：reprompt = 一次标准 reviewer dispatch（dispatch(project_root, key, "l3-a{used+1}", "reviewer", prompt, loop="l3:{key}", attempt=used+1, read_scope=[.agenticdoc/{key}, .agenticdoc/goal.md], timeline=st.timeline)，同 conductor.py:1263-1267 形制）；事务幂等（同 stem upsert）、崩溃愈合（orphan 重插不耗轮）、frontmatter 标签自动就位。
- F-6/F-7/F-8 → 轮次递增与预算公式全部现成：新 stem 的 attempt=N+1 使下一 tick used 自然 +1；封顶判定复用 l3_budget/l3_limit（conductor.py:1181-1182）。
- F-10/F-11 → design 必须在 gate-blocked 分支自带 used >= l3_limit 封顶 + mark_stalled（AC-005）：既有 :1232 检查对 meets+gated 不可达，且 dispatch 事件打断 advance streak、5-tick 兜底对 reprompt 回路失效——这是本分支唯一必须新写的预算逻辑。
- F-12/F-13/F-14 → AC-007 机制基础现成：双层 in-flight 守卫覆盖 ap-{key}-l3- 前缀，reprompt 在飞期间不重跑事务 / advance / 派发；无需扩守卫。
- F-15/F-16/F-17/F-18 → 失败原文捕获点 = _done_transaction step 5 调用点（conductor.py:1381-1383，err 在作用域内、今天被丢弃）；解析 stderr 的 "   - " 前缀行；信任级别 = 工程配置级模板文本（文件内容不进失败行、非任意用户输入），体积 <=5 行；嵌入 prompt 正文 UTF-8 全链路安全；reviewer 只读 + 判定不代写兜底 prompt 影响力风险。
- F-19/F-20 → 事件面：dispatch 事件自带 loop/attempt 供轮次断言；读回验证无事件（断言走队列文件）；新分支建议补一条 _one_line 限长摘要事件，全文只进 prompt 不进 timeline；stall reason 保持单行（gates.create 拒多行）。
- F-21/F-22/F-23 → 测试面：夹具栈（_verify_key_project + _set_row/_worker_output/_rows + round_budget 覆写）全部可复用；唯一新增夹具 = stderr 格式忠实的 advance fake（真实 "GATE BLOCKED:" / "   - " 行形状）+ AC-008 的第二套词表 fixture；AC-002 断言读 ap-k1-l3-a{N+1}/task.md prompt 原文，AC-005/AC-006 断言 l3 家族 dispatch 计数与 stalled 事件。