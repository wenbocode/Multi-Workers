# Quality Gate Review — mw-decision-substitution（QG-review, 2026-10-20）

- 审查者: worker `ds-qg-review`（type: review，卡 `tasks/QG-review.md`）
- 方法: 静态审计（逐文件精读 + 全仓 grep）+ 既有测试/验证记录复核；本会话未执行任何测试命令（无命令执行通道），测试结论引自 `evidence/runs/verify-mw-decision-substitution-20261020.md` 与各 worker 报告
- 范围: `decision_points.py` / `decide_archive.py` / `mw.py`(_decide_*, _dp_*) / TS 五文件 + `index.ts` / 5 个 Python 测试文件 / 7 个 TS 套件 / `docs/decision-substitution.md` / 三份 `advance_phase.py` 镜像

## 结论

**PASS-WITH-FINDINGS** —— 核心交付（24 项注册表、`decide_for` 11 步、档案 4 类行、`dp` CLI、dp1/dp2/dp3 生产接线、报告/签收/门禁/写守卫）全部落地且有关键测试（含关闭态字节同构、6 终态映射、守卫拒写）；未发现 blocker。但存在 4 项 major：`ask_decision` 工具仍是 D-036 明令禁止的 TS 授权镜像并伪造 `decision_id`/`acted`（T-05 残留在 T-02b 之后无人回收）；`readDp2Authorization`/`readDp3Policy` 同属镜像且与 Python 降级语义有实测分歧；D-015 签收写守卫未覆盖 `worker_file` 通道（worker 可写自己 key 的 `sign-final.md` 满足 done 门禁）；`ask_decision` 对 dp1/2/3 的 state 永远过不了注册表必填门（生产恒上抛，测试因打桩不可见）——其中后两者正是本卡点名要重点打击的「测试绿但生产不可达」形态。

## 证据

### §A AC 覆盖矩阵（spec.md §8，AC-001..AC-015）

> QG 卡片的 AC 引用与 spec rev3 编号有漂移（卡称「AC-011 每次决策一行档案」「AC-012/013 P0 三门槛」，spec 里 P0 门槛是 AC-002、签收是 AC-009、档案是 AC-006）——本矩阵按 spec rev3 内容对号，卡片问句在各行内回答。

| AC | 结论 | 证据（path:line / 说明） |
| --- | --- | --- |
| AC-001 配置表唯一权威；关闭态零扰动 | covered | CLI 路径：`decision_points.py:1393` `decide_for`、`:1448`（disabled 在 `_encode_state`/backend 之前返回）；`test_decide_run_authority.py:224`（dp3 off → `backend.calls==[]`、零档案行、`state_digest is None`）。TS 路径：dp3 `test/suite/dp3-answer.test.ts:247`（两种关闭态归一化后逐字节相同、零 `[DECIDE]`）；dp2 `dp2-narrow.test.ts:226-243`（关闭态告警字节等同）；dp1 `decision-association.test.ts:687`（suggest/关闭态 task.md 与基线逐字节相同）。热生效：`decision_points.py:1085` `(st_mtime_ns,st_size)` 缓存 + `mw.py:1214` `_dp_write_raw` 的 `os.utime(ns=…)` 推格。注：dp1 关闭（表内 off）时仍会 spawn 一次 `python mw.py decide run` 子进程（TS 无表预读，见 MINOR-7）；「零 spawn」按 D-003 定义（backend 零调用）成立 |
| AC-002 默认值/档位/P0 三门槛 | covered | 默认推导 `decision_points.py:240-266`（`__post_init__`：P2 必有 executor）；8 层降级 `:884` `_parse_row`、`:1008`；P0 门槛：`mw.py:1453` `_dp_require_p0_confirmation`（缺 flag → exit 2、`nothing was written`、表 sha 不变——`test_decide_dp_cli.py:303`）；成功后 `authority-change(by=human:p0-confirm)` + `config_sha_after`（`test_decide_dp_cli.py:318`）；`P0-ON` 标记 `mw.py:1281-1315`（test `:215`）；签收侧 p0-open 精确匹配 `mw.py:1800`（test `:590`） |
| AC-003 dp3a/dp3c 自答 + dp3b 预消化 | **partial** | 三切分类器 + 注入落地：`worker-mode.ts:3696` `attemptDp3Clarification`、`:4783` `decideDp3WorkerClarify`（3a 需 `path:line` 引用、3c 本地 Jaccard≥0.75、3b 默认上抛）、`:3897` 唯一插入点；测试 `dp3-answer.test.ts` 13 例。**但验收要求的「真实 run 事件 + 人工轮次计数对比」从未发生**：本仓 `.mw/decide.json`/`.mw/decide-points.json` 不存在、`.agenticdoc/_autopilot/decisions.jsonl` 不存在——启用态零真实运行，全部证据来自 stub harness（T-06 报告残留自认）。另 3b 只做上抛、未做「预消化为结构化问题」（T-06 报告已声明） |
| AC-004 P2 自动生效留痕 | **partial** | dp2：`pm-orchestrator.ts:2244`（narrow）→ `:2588` 写 steer + `:2591` `appendDp2ActedTrace`（`[DECISION] dp2 acted=1 decision_id=…`）；dp3：`worker-mode.ts:3749-3769`（注入点声明 `acted:true` + trace + `[DECISION] dp3 acted=1`）；dp1：`decision:` 头行。**但档案侧 `decide` 行恒 `acted=false`/`actual_action=None`（`intent="answer"`，D-035），消费侧 acted 只进 trace/task.md，`decisions.jsonl` 里永远没有 acted=true**；dp9 无调用点（仅注册）。报告的「自动生效(acted)」计数因此恒 0（见 MINOR-2） |
| AC-005 失效安全四路径 | covered | 7 值词表 `decision_points.py:101-113` + 档案同源校验 `decide_archive.py:60-70`；四路径用例：`test_decide_run_authority.py:373`（unknown dp exit 2）、`:387`（transport 未配置 → disabled）、`test_decision_points.py`（disabled/unavailable/input-incomplete/low-confidence 各分支 + FakeBackend.calls==0）；TS 侧 `dp3-answer.test.ts:287-323`（降级回原问人路径、Questions 首行原文）；D-031（非 api 置信不门控）`decision_points.py` 步 8 + `:1829` |
| AC-006 决策档案 | covered | 4 类行 + 36 字段全写 `decide_archive.py:91/132`；哈希链/半行尾/幂等/并发 `:146/:191/:246/:262/:856`（`test_decide_archive.py` 30 例全绿）；`decision_id` 幂等（重放 `duplicate="existing"` + `note=duplicate-replay`，D-032）。旧 11 字段行（`triage-decisions.jsonl`）仍可读（`mw decide show`，底座面未动）。**卡片问句「legacy 请求路径是否落行」：不落行**——`mw.py:903` `_decide_run` legacy 分支直调 `DecisionClient`，`test_decide_run_authority.py:299` 明确断言 "the frozen legacy path archives nothing"。**已被显式记录**：`mw.py` `_decide_run` docstring + 该测试 + T-02b 报告；但 `docs/decision-substitution.md` §7 边界清单未列此条（MINOR-4） |
| AC-007 结果关联（dp1 通道） | covered | 生产链路真实接通：`ui-bridge.ts:469` `computeDispatchTriage`（结构化 state）→ `triage-client.ts:816` → CLI → `decide_for`；`dispatchDecisionOf`（`ui-bridge.ts:264`）要求 `mode=auto` + `triage_type` + `decision_id` → `mergeDecisionHeader`（`:2158`）写 `decision:` 头行；两个派发入口都传 `decision:`（`ui-bridge.ts:2925` / `:3443`）；settle 六态映射 `pm-orchestrator.ts:852`（NC 不落行、exit3/model_exhausted → inconclusive、lost → pending+note=lost）；`(decision_id,outcome,run_id)` 去重 + rollback 晚于 ok（`:1056` `recordDecisionSettle`/`planDecisionSettle`）；测试 `decision-association.test.ts:245-571`。**「真实样本可查」未验证**：仓库内零真实样本（见 §C） |
| AC-008 phase 末报告 | covered | `advance_phase.py:534` `maybe_write_decision_review`（推进成功后、失败只 WARN）+ 手动 `mw decide report`（`mw.py:2315`）；`N<5` 强制「数据不足，不结论」（`mw.py:2026` `_REPORT_MIN_N=5`）；分歧样例/`suggest:` 行（`:2142`、`:2167`）；`inconclusive` 不进分母（`_REPORT_SETTLED=(ok,rework,rollback)`，`mw.py:2046` 区域）；`test_decide_report.py` 全绿 |
| AC-009 收尾强签收 | covered | 门禁两条（固定名 + `(?m)^conclusion:` 正则）落在**三份镜像**（`.agents/skills/agentic-task/{,core/,claude/}scripts/advance_phase.py:98-110`，T-09b 修复确认无「改镜像不改 canonical」问题）；三种 conclusion 各写 `authority-change`（`mw.py:1858` `_dp_apply_rows` 保证 ≥1 行）；`dp apply` 拒绝 agent 会话（`mw.py:1889` + `_DP_AGENT_ENV_VARS:1150`，test `:580`）；PM 的 write/edit/bash 被守卫拒（`xkey-gate-guard.ts:420` `registerDecisionSignoffGuard`，`decision-signoff.test.ts:223`）。**p0-open 漏列由 `dp apply` 校验而非门禁**（动态集合无法进静态门禁，已在门禁注释与 doc §2.6 显式说明）。**守卫有一个通道缺口（worker_file），见 MAJOR-4** |
| AC-010 机器零写配置 | covered | 表的唯一写者路径是 `mw.py` 人指令（`_dp_set_enabled:1470`/`_dp_set:1539`/`_dp_refresh:1605`/`_dp_apply:1882`，全部经 `_dp_write_raw:1214`）；`refresh` 只增缺失行不动 enabled（test `:444`）；全仓 grep 无第二处写 `.mw/decide-points.json` 的代码；TS 侧零写；bash 层 `mw decide dp on/off/set/refresh/apply` 被文本级拦（`xkey-gate-guard.ts:316` `TABLE_WRITE_CLI_RE`） |
| AC-011 dp 抽象完整性 | covered | 24 项注册 + import 期 fail-loud（`decision_points.py:340` DP_REGISTRY、`:584` `_validate_registry` 强制 24 项、`:600` 未知 id 抛 `DecisionInputError`）；未知 id CLI exit 2（`test_decide_run_authority.py:373`）；TS 常量 ⊆ 注册表有**真跑 Python 的锁**：`triage-client-state.test.ts:520`（spawn 真实 `DP_REGISTRY` 断言 `REQUIRED_FIELDS_BY_DP` 每键都是活 id）、`decision-tool.test.ts:528`（id/tier 24 项 parity）；三个接线点都经 `mw decide run` → `decide_for`。**「TS 只持 id」被 dp2/dp3 的授权/问题集镜像部分突破（MAJOR-3、MINOR-9）** |
| AC-012 dp refresh | covered | `mw.py:1605`：补缺失行、保留已有开关、orphaned 保留并计数、无变化不写文件；幂等（第二次 added=0、mtime 不动）`test_decide_dp_cli.py:478`；orphan 行不删（test `:444` 断言 `dp99-legacy` note 保留） |
| AC-013 结构化输入与脱敏 | covered | ≤2000B 两段式截断双实现一致（`decision_points.py:761` `_fit_state` / `triage-client.ts` `truncateStructuredState`）；L2「构造即无入口」：未知顶层键直接拒（`triage-client.ts:245` "L2 leak guard" 用例 + `STATE_TOP_LEVEL_KEYS` 白名单）、绝对路径入 `task_summary` 前被替换为 `<path>`（`ui-bridge.ts:377` `dispatchTaskSummary`，测试 `decision-association.test.ts:997`）；档案不存 raw state（`decide_archive.py` `append_decide` 只落 `state_digest`）；`state_digest` Python 单点（`decision_points.py:1824`，TS 零哈希、`:801` `applyAuthorityKeys` 纯透传，D-004）；旧字符串输入兼容（`triage-client.ts` legacy 分支 + `decision.py` `isinstance(state,str)`）。遗留：legacy 字符串 state（16KB 截断、不脱敏）仍是 spec 认可的兼容通道 |
| AC-014 不改派发语义 | covered | 关闭/suggest 态字节同构（AC-001/AC-015 各测试）；开启态仅增加 `decision:` 头行与 `[DECISION]` trace（不重写 type/role/model，`ui-bridge.ts:1700` 区段注释 + `computeDispatchTriage` 从不改 `dispatchedType`）；回退可逆且留痕（`dp off` 写 authority-change，test `:352`） |
| AC-015 mode 语义 | covered | `mode=suggest`：dp1 不写头行（`decision-association.test.ts:677` 逐字节对照）、dp2 照常告警不执行（`dp2-narrow.test.ts:396`）、dp3 不注入（`dp3-answer.test.ts:496`）；档案行 `authority=advisory`、`acted=false`（`test_decide_run_authority.py:344`）；`mode` 切换热生效（同一读表路径）；建议只进报告/回执不进 steer |

### §B 发现清单

#### blocker

无。

#### major

**MAJOR-1：`ask_decision` 工具是 D-036 明令禁止的 TS 镜像，并伪造 `decision_id`/`acted`（T-05 残留在 T-02b 后未回收）**
- 现象：`pm/decision-tool.ts:236` `readDecisionAuthorization` 自行读 `.mw/decide-points.json`（含 `ASK_DECISION_DP_TIERS` 注册表 tier 镜像）推导 `enabled/mode`；`runAskDecision`（`:570`）成功 payload 的 `decision_id` 是 TS 拼的 `` `${dp}:${trigger}` ``（`:660` 区域），`acted = authorization.mode === "auto"`（`:664` 区域）——既不消费子进程 `mw decide run` 早已返回的 `decision_id/mode/acted/escalated_reason`（`mw.py:872` `_decide_run_payload` 四键齐备），又把 `acted` 从 mode 反推（正是 D-041 禁止项）。模块头注释（`:28-40`）的依据「`mw decide run` 直调 `DecisionClient`、不读表、不返回 mode/acted/decision_id」对当前代码为**过时假命题**（结构化路径自 T-02b 起走 `decide_for`）。
- 证据：`decision-tool.ts:236/570` + `mw.py:872-901/903`；`decision-tool.test.ts:210` 用例名自认 "derives mode/acted from the table"；T-05 报告残留 2 原文「工具侧镜像授权表读侧并推导 mode/acted，档案行仍待 Python `dp run` 面（T-02/T-08）」——T-02b 完成了 Python 面，但没有任何卡片回收工具侧（T-04c 写面明确排除 `decision-tool.ts`）。
- 影响面：档案关联链对工具型决策断裂——Python 侧 `decision_id` 由 state 的 `task_key`/`key` 解析（`decision_points.py:150-161` `resolved_id`），工具的 state 只带 owner key，故档案行 id 恒为 `<dp>:<owner-key>`，与工具报给 LLM、写进 trace 的 `<dp>:<trigger>` 不同；同 key 第二次 ask 触发 `duplicate-replay`（档案只留第一行）。`acted:true` 会让模型把「答案已生效/已授权」当成事实（工具 promptGuidelines 明说 mode=suggest→acted=false 不授权，反推 auto→acted=true 即授权）。
- 建议动作：`runAskDecision` 改为消费子进程四键（`decision_id`/`mode`/`acted`/`escalated_reason` 原样透传，删除 `readDecisionAuthorization` 与 tier 镜像）；`acted` 按 D-041 由消费侧（执行门控动作的点）声明，工具 payload 不再自造；同步修模块头注释与 `decision-tool.test.ts` 断言。

**MAJOR-2：`ask_decision` 的 state 对 dp1/dp2/dp3 永远过不了必填门——生产恒上抛且原因误导（测试全绿但生产不可达实例）**
- 现象：`buildDecisionState`（`decision-tool.ts:292` 区域）对**所有** dp 只产 `{v, dp, key, task_key, task_summary}`；`decide_for` 步 5 对 dp1/dp2/dp3 校验 `REQUIRED_STATE_FIELDS`（`decision_points.py:626-677`：dp3 需 `phase/task_type/risk/risk_source/authority_tier/ambiguity.*/questions_version` 等 12 项），缺 7-9 项 → 恒 `input-incomplete`。CLI 把它映射进 legacy reason `bad-response`（`mw.py:846-866` `_DECIDE_RUN_REASON_MAP`），工具只透传 legacy reason、丢弃 `escalated_reason` → 模型看到的是「服务坏响应」，而非「输入契约不满足」。其余 21 个 dp 无必填字段集，可正常走通。
- 证据：`decision-tool.ts` `buildDecisionState`；`decision_points.py:626` `REQUIRED_STATE_FIELDS`（仅 dp1/2/3 有键）；`decision-tool.test.ts:210` 的 stub runner 直接返回 `available:true`——真实 `decide_for` 对该 state 必拒，测试与生产行为分叉。
- 影响面：worker LLM 对 dp1/dp2/dp3 的任何 `ask_decision` 调用都得到「blocked」；对 dp4+ 的调用得到可用答案但带 MAJOR-1 的伪 id/伪 acted。
- 建议动作：工具按 dp 构造必填集（复用 `triage-client.ts` 的 `prepareStructuredState`/`REQUIRED_FIELDS_BY_DP` 机制或要求调用点提供 dp 专属字段）；`unavailable` 分支透传 `escalated_reason`，与 D-021/`_DECIDE_RUN_REASON_MAP` 的语义对齐。

**MAJOR-3：`readDp2Authorization` / `readDp3Policy` 是第二、三处「读表判 enabled/mode」的实现（D-036 字面违反），且与 Python 降级语义有实测分歧**
- 现象：`pm-orchestrator.ts:2044` 与 `worker-mode.ts:4468` 各自 fail-soft 解析 `.mw/decide-points.json` 推导 `enabled/mode`，用于「是否 spawn」和「mode 门控 acted」。Python 的 L2/L3 语义在 TS 侧不对齐：非对象行（L2）Python 强制该 dp off，TS 两处 `recordOf(row) === undefined` → 回落注册表默认（dp2/dp3 均 P2 默认 **on**）；坏 `note`（L3）Python force-off，TS 完全不读 note 仍 enabled。`decideDp2Checkpoint` 的 `acted` 判定用本地 `authorization.mode` 而非子进程回传的 `payload.mode`（`pm-orchestrator.ts:2317`）。
- 证据：`pm-orchestrator.ts:2044-2063`（`if (!row) return fallback`，fallback=on/auto）；`worker-mode.ts:4468-4490`；Python 对照 `decision_points.py:884-968`（L2/L3 force_off）。
- 影响面：当前全部收敛到 fail-closed（TS 放行 → spawn → Python 拒 → unavailable → 回退原告警/原问人路径），无 fail-open；但两处独立实现意味着 Python 侧任何降级语义调整都不会传播到 TS，且 dp2/dp3 在「行损坏」场景白付一次子进程。D-036 的原文（「TS 只消费 mode/acted/decision_id，不得自行镜像配置表推导授权」）被字面违反——若 PM 认为零 spawn 前置检查值得保留，应在 design 显式裁定为例外并注明「TS 预读仅作短路，权威判定在 Python，分歧以 Python 为准」。
- 建议动作：短期在两处镜像注释里声明「非权威、仅短路、分歧以 Python 为准」并把非对象行改为回落 disabled（与 L2 对齐）；中期让 dp2/dp3 消费子进程 `payload.mode`（答案路径上 Python 已回传），本地读仅保留 `enabled` 短路。

**MAJOR-4：D-015 签收写守卫不覆盖 `worker_file` 通道——worker 可写自己 key 的 `evidence/review/sign-final.md`，done 门禁可被 agent 自满足**
- 现象：`registerDecisionSignoffGuard`（`xkey-gate-guard.ts:420`）只拦 `write`/`edit`/`bash` 三类 tool_call。writeless 角色（research/review）的写通道是 `worker_file`，其写面（`shared/write-surface.ts` `judgeWriteTarget`）显式接受 `<key>/evidence/**`（"no extension restriction"）——`worker_file({file: "evidence/review/sign-final.md", …})` 合法落地。守卫模块自己的注释（`:296-320`）宣称「sign-off is the HUMAN answer channel… an agent cannot do it through its only tool channel」，但 `worker_file` 恰是 writeless worker 的唯一写通道且未被覆盖。
- 证据：`xkey-gate-guard.ts:420`（只匹配 `write|edit|bash`）；`worker-file-tool.ts:101-107`（`inEvidence` 跳过 basename 白名单）；`decision-signoff.test.ts:161-168` 只证 write/edit/bash 面，无 worker_file 用例；done 门禁只验文件存在 + `conclusion:` 行（`advance_phase.py:98-110`），不验作者。
- 影响面：被派发的 worker 可以自写签收满足门禁（`dp apply` 仍拒绝 agent 会话、`.mw/decide-points.json` 不在 evidence 面内不可经 worker_file 写，所以**授权表本身安全**；被伪造的是「人已 review」这个事实与 done 门禁）。这正是 spec §10 风险表「签收被 PM 代签」的变体（PM 不可，worker 可以）。
- 建议动作：把 `evidence/review/sign-final.md`（与 `.mw/decide-points.json`）加进 `judgeWriteTarget` 的拒绝表，或在守卫中增加 `toolName === "worker_file"` 分支拦截 `isDecisionSignoffPath(file)`；补一条 decision-signoff 用例证明 worker_file 被拒。

#### minor

**MINOR-1：dp1 采纳判定不校验一致性** —— `dispatchDecisionOf`（`ui-bridge.ts:264`）只要 `available && mode==="auto" && triage_type && decision_id` 就标 `acted:true` 并写 `decision:`，即使 `triage_type ≠ 实派 type`（disagreement）也照写；T-04c 语义表写的是「派发方**采纳了该类型**」，而派发从不改 type（AC-014），分歧样本会以 `outcome=ok` 进入一致率分子。建议：disagreement 时不采纳（不写头行），或 settle 行/报告里带 `dispatched_type` 供人工判读。证据：`ui-bridge.ts:264-268`；`decision-association.test.ts:667-720`（用例只覆盖 agree/suggest/unavailable，无 disagree-auto 用例）。

**MINOR-2：报告「自动生效(acted)」指标对三个已接线 dp 恒 0，doc §3 言过其实** —— 档案 `decide` 行在 `intent="answer"` 下恒 `acted=false`（`decision_points.py:1690-1712` suggest/answer 分支），消费侧 acted 只存在于 trace.log `[DECISION] … acted=1` 与 `decision:` 头行；`_decide_report_metrics` 数的是 `base.acted`（`mw.py:2067` 区段）→ 恒 0。`docs/decision-substitution.md` §3 mode 表写「`kind=decide`，`acted=true`（执行器成功）」——对现接线永不发生（三点的执行器都是 unwired，`intent=act` 无调用点）。建议：报告补一列「消费侧 acted（trace 反查）」或 doc 明示档案 `acted` 仅指 Python 执行器。

**MINOR-3：dp3 3c 本地复用决策零档案行** —— 3c 零 spawn（`worker-mode.ts:4658` 起，test `dp3-answer.test.ts:440` "never calls the service"），故 `decide_for` 不跑、`decisions.jsonl` 无行；其 `acted=1`、`decision_id` 只在 trace。spec §0 收益 3「每次自动决策可 review：decision_id→输入指纹→答案→是否生效」对 3c 断链。T-06 报告残留已声明；`docs/decision-substitution.md` §7 边界清单未列。建议：doc §7 补一行；或 3c 命中后由 worker 侧补一条 `kind=decide, note=local-reuse` 档案行（需契约裁定，本审不改代码）。

**MINOR-4：legacy `mw decide run` 路径不落档案行，doc §7 未列** —— 已显式记录于 `mw.py` `_decide_run` docstring、`test_decide_run_authority.py:299`、T-02b 报告；`docs/decision-substitution.md` §7（诚实清单）应补。

**MINOR-5：dp3 3a 超限拒发用 `input-incomplete` 而非 D-028 的 `input-oversize`** —— `worker-mode.ts:4847-4848`：`canonical state > 2000B` → `escalate("input-incomplete", "3a", …)`；`Dp3EscalatedReason` 类型（`:4427`）压根没有 `input-oversize` 成员。只影响 trace 措辞（请求未发出、无档案行），不影响行为。建议：类型补 `input-oversize` 并改该分支。

**MINOR-6：design.md 契约表止于 D-036** —— D-037..D-042（含 D-041 acted 语义、D-036 本身、D-028、D-030、D-035）只存在于任务卡/代码注释/本 key 文档，`design.md` §3 未回填；QG 卡与多份代码注释引用「design.md D-001..D-042」名不副实。建议：design.md §3 补齐 7 行（纯文档）。

**MINOR-7：dp1 关闭态仍 spawn CLI 子进程** —— dp2/dp3 有 TS 表预读短路，dp1 没有（`computeDispatchTriage` 只读 `.mw/decide.json`）：dp 在表里 off 但传输 on 时，每次派发付一次 python 启动，由 Python 拒绝。AC-001 的零 spawn 按 D-003（FakeBackend.calls==0）仍成立；建议在 dp1 路径加同型短路或文档说明。

**MINOR-8：QG 卡 AC 编号与 spec rev3 漂移** —— 卡片「AC-011 每次决策一行档案」「AC-012/013 P0 三门槛」在 spec 里分别是 AC-006 与 AC-002/AC-009；本报告按 spec 编号作答并在对应行内回答卡片问句。后续卡片引用 AC 时应回 spec §8 对表。

**MINOR-9：questions_version 镜像无跨层执行校验** —— dp2 的 `DP2_QUESTIONS_VERSION` 由 TS 手写 canonical 串推导、测试只对注册表**源码文本**做 regex + 断言固定哈希（`dp2-narrow.test.ts:546-556`），不执行 Python `_questions_version`；dp3 的 `DP3_QUESTIONS_VERSION = "q-b71e824c"` 是裸常量，**无任何测试**引用。`decide_for` 只做存在性校验（非相等），漂移不炸但会静默。建议：两处改为像 `triage-client-state.test.ts:520` 那样 spawn Python 取真值。

#### nit

- **NIT-1**：`_DECIDE_RUN_REASON_MAP` 把 `input-incomplete/low-confidence/over-authority` 全折进 legacy `bad-response`（`mw.py:846-866`）。`escalated_reason` 附加键在，但消费它的只有 triage-client；ask_decision 不透传（并入 MAJOR-2）。
- **NIT-2**：`dp apply` 先写 `authority-change` 行再换表（`mw.py:1955-2000`）：表写失败时审计行已落（代码打印警告并注明）。顺序是 Q4 裁定的防丢审计选择，接受；仅提示读档时 `change` 可能早于真实生效。
- **NIT-3**：`decision-tool.ts` 头注释引用行号如 `packages/agent/src/types.ts:355-368` 带杂字符（`:355-368`，同文件多处），属注释排版噪声。

### 单一权威排查（D-036，卡片审计项 2）

全仓 grep `decide-points`：读表的实现共 **4 处**——
1. `decision_points.py:1085` `load_points_config`（**权威**，`decide_for` 与 `dp` CLI 共用，8 层降级 + 缓存）；
2. `pm/decision-tool.ts:236` `readDecisionAuthorization`（镜像，MAJOR-1）；
3. `pm/pm-orchestrator.ts:2044` `readDp2Authorization`（镜像，MAJOR-3）；
4. `worker/worker-mode.ts:4468` `readDp3Policy`（镜像，MAJOR-3）。
`pm/triage-client.ts` **不读授权表**（只读 `.mw/decide.json` 传输门 + 透传四键，`:801`）——dp1 的授权判断完全交给 Python，是三面里唯一干净的一面。`ui-bridge.ts` 不读（`dispatchDecisionOf` 只消费回传键）。结论：**存在第二/三/四处实现，D-036 字面不满足**；其中 triage-client 路径（dp1）已收敛，dp2/dp3/ask_decision 未收敛。

### 测试有效性抽样（≥3，卡片审计项 3）

1. **`triage-client-state.test.ts`（证生产行为，强）**：被测函数是真实的 `triageDispatch`/`prepareStructuredState`；子进程在声明的 `DecideRunner` seam 打桩（合法：外部进程）；且 `:520-583` **spawn 真实 Python** dump `DP_REGISTRY` 做 id/`v`/dp 专属行三重锁——这是跨层漂移的正向防御。缺口：TS 消费的响应键与 Python 产出的响应键分别由两侧测试固定（`test_decide_run_authority.py` 跑真实 `cmd_decide`+FakeBackend），**没有任何单测一次跑通 TS client → 真实 CLI** 的端到端（见 §C）。
2. **`decision-association.test.ts`（证生产行为，强）**：驱动真实 `planDispatchFrontmatter` + `writeDispatchTaskMd`，对 `decision:` 头行做**逐字节**断言（`:667-720` suggest 与关闭基线全等，非「不含某子串」式负断言）；`:1010` 走真实 `dispatch_worker` 工具入口证明接线，防止「plan 层测试绿、入口没接」。
3. **`dp2-narrow.test.ts`（证生产行为，强，含变异自证）**：驱动真实 `startWorkerPollLoop` + 真实 Worker/Ack/Index 文件 store；T-07b 报告记录了变异验证——删掉 steer 消费者 → 4 用例红、删掉 liveness 回退 → 1 用例红（`workers/ds-t07b-dp2-consumer/output.md:25-30`），证明测试咬的是消费行为不是自造输入。
4. **`dp3-answer.test.ts`（证生产行为，强）**：真实 `workerModeActivate` 全 settle 链 + 双 fixture 归一化字节对比；3c 用「零 runner 调用」区分本地复用与真问服务。
5. **`decision-tool.test.ts:210`（把错误契约钉成绿灯，弱）**：断言「mode/acted derives from the table」——测试绿恰是 D-036 违约的固化（MAJOR-1/2）；这是本轮最典型的「测试绿但生产漂移」样本。

### 契约-实现一致性抽查（卡片审计项 4）

- **D-011（dp2 auto 只允许 narrow）**：✅ `decideDp2Checkpoint` 闭集映射，`split/direct/escalate` 全部落回人告警；`acted = mode==="auto" && action==="narrow"`；liveness 探测失败回退告警（T-07b）。偏离：`acted` 用的是**本地镜像 mode**（MAJOR-3），非子进程回传。
- **D-012（decision: 仅 acted=true）**：✅ `mergeDecisionHeader`（`ui-bridge.ts:2158`）`!decision?.acted` 即原字节；suggest/无 id/畸形 id 全不动。
- **D-014（签收固定名 sign-final.md）**：✅ 门禁固定名 + `(?m)` 锚定正则（三镜像 `advance_phase.py:98-110`）；`dp apply` 拒 `key : value` 空格拼写（`_dp_apply_parse`），与门禁正则一致。
- **D-021/D-028（input-incomplete vs input-oversize）**：✅ TS `TRIAGE_REASON_INPUT_OVERSIZE` 独立（`triage-client.ts:63`）、Python 7 值词表含 `input-oversize`（`decision_points.py:101`）、`_decide_run_reason` 映射为 `budget-exhausted` 不与 `input-incomplete` 混同。❌ 偏离一处：dp3 3a 超限用 `input-incomplete`（MINOR-5）。
- **D-030（七值词表单一）**：✅ `ESCALATED_REASONS`（`decision_points.py:101-113`）与 `decide_archive._ESCALATED_REASONS`（`:60-70`）同源同集，`input-invalid` 仅读侧兼容；`_decide_run_reason` 的映射表只作用于**legacy reason 键**，`escalated_reason` 键原样并存——不存在「disabled 伪装成 unavailable」的路径。
- **D-041（acted 由消费侧给出）**：✅ dp1（dispatchDecisionOf）、dp2（steer 落地后 `appendDp2ActedTrace`）、dp3（注入点声明）都是消费点显式给出。❌ `ask_decision` 由 mode 反推（MAJOR-1）。

### 安全与隔离（卡片审计项 5）

- **L2 进 state**：结构化路径构造即无入口——字段白名单 + 逐字段 cap + 未知顶层键拒绝（`triage-client.ts:245` 用例）、绝对路径在 `task_summary` 内被替换 `<path>`（`ui-bridge.ts:377`，测试 `:997`）、dp3 复用语料全程本地、`buildDecisionState` note 截断 600B；档案不落 raw state 只落 digest。遗留面：**legacy 字符串 state（≤16KB 自由文本）不脱敏直接上 wire**——spec §5.4 明文保留的兼容分支，属已接受残留；dp2/dp3 state 全为机器枚举/计数。
- **state 构造**：`_state_builder` 只合入 caller data + v/dp/questions_version，绝不编造默认（缺失保持缺失以便 step 5 拒绝）。
- **写守卫威胁边界**：覆盖 agent 的 `write`/`edit`/`bash` 三通道（含重定向/PowerShell/sed/find/内联代码写 + `mw decide dp` 写动词族），每拒绝落一条 `[DECISION_SIGNOFF]` trace；读操作与 `decision-review-*.md` 明确放行。**不覆盖**：`worker_file` 通道（MAJOR-4）、同 uid 进程外写者（守卫注释自认「application-layer guard, not a sandbox」）。`.mw/decide-points.json` 不在 evidence 写面内，worker_file 打不到。
- **`dp apply` 环境变量绕过**：`_DP_AGENT_ENV_VARS`（`mw.py:1150`）检测 `PI_CODING_AGENT/AI_AGENT/PI_WORKER_TASK`。**可被 `env -u` 类前缀绕过**（子进程 env 由调用者构造）；但 bash 层守卫与 env 检查独立成层——`mw decide dp apply/on/off/set/refresh` 文本形态无论 env 如何都会被 `TABLE_WRITE_CLI_RE` 拦（`decision-signoff.test.ts` 有 `env -u` 场景吗？无——建议补一条：`env -u PI_WORKER_TASK python mw.py decide dp apply …` 必须仍被 bash 守卫拦）。真·进程外（人在普通终端）执行本来就是设计允许的人通道。

### 文档声明 vs 代码（抽查 3 条，卡片审计项 6）

1. **热生效**（doc §2.4）：✅ `load_points_config` 按 `(st_mtime_ns, st_size)` 重读（`decision_points.py:1085-1132`），`_dp_write_raw` 同签名重写后 `os.utime(ns=)` 推格（`mw.py:1214-1237`）；且 CLI 每次决策本就是新进程，热重载对 TS 侧直读（无缓存）同样成立。
2. **`dp refresh` 幂等**（doc §2.5）：✅ 只增缺失、不动已有、无变化不写文件（mtime 不动）、`by=refresh` 逐行审计；`test_decide_dp_cli.py:478` 断言第二次 `added=0` 且 `_signature` 不变。
3. **`revoke` 语义**（doc §5.2）：✅ `_dp_apply_plan`（`mw.py:1822`）对 revoke 把所有 enabled 的 dp 置 off；签收不能开 P0（promote 命中 P0 即 exit 2）；`narrow` 带 promote 即拒；三种结论都保证 ≥1 条 authority-change（`_dp_apply_rows`）。与 doc §5.2 的每一条一致。

三份 `advance_phase.py` 镜像（`scripts/`、`core/scripts/`、`claude/scripts/`）的 done 门禁与 review 钩子逐段一致（T-09b 收口确认；本审逐份 grep `sign-final` 命中同一组规则行）。

### 「测试绿但生产不可达」三类重点打击结论

- **T-05 类（TS 镜像）**：仍存活于 `decision-tool.ts`（MAJOR-1）与 dp2/dp3 预读（MAJOR-3）——triage-client/dp1 一线已按 D-036 修正，其余未收敛。
- **T-09 类（守卫放错位置/未注册）**：未复发——`registerDecisionSignoffGuard` 在 `index.ts:60` 于**每个模式**注册（worker 分支之前），`registerAskDecisionTool` 在 worker 分支内 `workerModeActivate` 之后注册且用 `before_agent_start` 幂等追加 active 集（`index.ts:82-90`）。但守卫**覆盖面**有缺口（MAJOR-4）。
- **T-04c 类（生产 dp1 走 legacy 断链）**：已修复——两个派发入口都传 `dp1` facts，结构化 state 优先，legacy 回退被强制写 `[DECISION] dp1 state=legacy reason=…` trace（`ui-bridge.ts:469-506`）；`decision:` 头行在结构化分支可达（`decision-association.test.ts:835` "the decision: line becomes reachable" + `:1010` 入口级测试）。

### 关键测试/验证记录引用

- T-10 全量：`evidence/runs/verify-mw-decision-substitution-20261020.md` —— Python `9 failed, 2728 passed`（8 条既有基线 + 1 条测试间污染，单文件 11 passed）；TS `19 failed, 1837 passed`（Windows shell/path + 另 key 在途 + bundle sha 未重建）；**本 key 8 套件 169/169 全绿**；`tsgo --noEmit` rc=0；度量基线 93.222/13.600 min 复算一致。
- T-07b 变异自证（消费者删除 → 4 红）与 T-08b/T-08c 补测记录在各自 `workers/*/output.md`。

## 残留与未验证

1. **本会话未执行任何命令/测试**（本 review 角色无命令执行通道）；所有测试结论引自 T-10 验证记录与 worker 报告的既有输出，未独立复跑。
2. **启用态从未真实运行**：本仓无 `.mw/decide.json`、无 `.mw/decide-points.json`、无 `.agenticdoc/_autopilot/decisions.jsonl`——dp1/2/3 的启用路径全部只有 stub-harness 证据；AC-003 的「真实 run + 人工轮次对比」与 AC-007 的「真实样本可查」因此只能判 partial。需要一次真实启用 + 真实派发 + 真实 settle 的端到端（依赖凭据与 `mw build --install`，均在用户放行流程内）。
3. **TS client ↔ 真实 CLI 无单条端到端测试**：两侧契约各自被钉（TS 侧 `triage-client-state.test.ts:585`、Python 侧 `test_decide_run_authority.py`），但没有一个测试把 `triageDispatch` 接到真实 `mw decide run` stdout。
4. **`npm run check` / `./test.sh` 未在本审运行**（前者按 T-10 记录会带 `--write`、后者本机无 WSL）；静态检查以 T-10 的 `tsgo rc=0` 为准。
5. MAJOR-1..4 与 MINOR-1..9 均为**记录不修**（本卡禁止改代码）；修复建议已给出最小范围。
6. design.md D-037..D-042 未回填（MINOR-6）——契约正文的单一来源仍是任务卡 + 代码注释。

## 上下文来源

- `.agenticdoc/mw-decision-substitution/{spec.md, design.md, plan.md, pm-state.md, tasks/*.md}`；`workers/ds-*/output.md`（T-01..T-10 报告与残留）；`evidence/research/*.md`（6 束设计调研）；`evidence/runs/verify-mw-decision-substitution-20261020.md`
- `packages/multi-workers/{decision_points.py, decide_archive.py, mw.py, README.md}`；`packages/multi-workers/test_{decision_points, decide_archive, decide_dp_cli, decide_run_authority, decide_report}.py`
- `packages/coding-agent/src/extensions/agent-team-loop/{index.ts, pm/{triage-client, decision-tool, ui-bridge, pm-orchestrator}.ts, worker/worker-mode.ts, shared/{xkey-gate-guard, write-surface, worker-file-tool}.ts}`
- `packages/coding-agent/test/suite/{triage-client-state, triage-dispatch, decision-tool, decision-association, decision-signoff, dp2-narrow, dp3-answer}.test.ts`
- `.agents/skills/agentic-task/{,core/,claude/}scripts/advance_phase.py`（done 门禁 + review 钩子三镜像）；`docs/decision-substitution.md`；`packages/{multi-workers, coding-agent}/CHANGELOG.md`
- `goal.md`（目标锚点：文件驱动去中心化协调 / 唯配置论 / 失效安全）

## 未覆盖面声明

- 不评估真实 LLM 答案质量（无凭据；jev 底座 key 已另行验收）。
- 不评估 `mw build --install` 之后的 L5 真派发路径（本 key 未执行该步骤；`mwds-t23-cutover-recheck` 的 bundle sha 失败项即其后果）。
- 不评估其它 key 的并行改动、Windows 环境类既有失败（T-10 记录的 Python 9 / TS 19 基线）。
- 不重写实现；发现问题只记录，未改任何代码；未做任何 git 写操作。
