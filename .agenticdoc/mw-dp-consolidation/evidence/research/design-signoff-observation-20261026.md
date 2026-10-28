# RQ17：dp-sign-key 签收硬门 / 适用范围 / 历史只读与安全观测（设计取证，静态）

> key `mw-dp-consolidation`，type research，唯一证据文件。只陈述源码静态事实与候选方案；未运行测试/CLI/服务，未调用模型或裁决服务，未签收、未改源码/框架脚本/配置/活 gate/ledger/历史。
> 证据等级（本文显式定义）：**L0** 可重算的行级静态事实（枚举/正则/哈希/纯净函数）；**L1** 隔离生产路径测试（临时项目 + faux provider，走真实 writer/consumer 代码路径）；**L2** 真实生产链或安装镜像观察 + 独立审查。本文全部为 L0。

## 结论

1. `finalize` 词表错配是**四处**可定位的事实，不是一处：done 硬门（`advance_phase.py:41`）、`mw decide dp apply`（`mw.py:2233/3485`）、archive `by=signoff:*` 闭集（`decide_archive.py:70-81,528-542`）、历史投影闭集（`decision_history.py:925,1021-1030,3571`）。只改门禁会留下三处不一致；只扩词表而不做有效性绑定，等于把 `continue` 合法化为成功。
2. 今天 done 门的语义与 AC-038 相反：真正的成功签收（`conclusion: finalize`）在 `advance_phase.py:339-343` 被拒（缺 `conclusion: continue|narrow|revoke` 机器行 → GATE BLOCKED）；而 `narrow`/`revoke` 只要哈希链完整即放行、`continue` 在 N>=1 且全行真引擎时放行（`decide_signoff.py:452-500`）。即「非成功结论放行、成功结论阻塞」。
3. 门只重算档案（`counted_rows`/`rows_sha256`，`advance_phase.py:361-375`），**从不读 `logical_id`/`snapshot_sha256`，也不查 result record**。所以 AC-039/052 的「这份文件签的是哪次判断」「受影响旧签收不复用」在门禁侧目前无载体：换一份同 key 的旧 finalize（档案未被追加）仍能通过。
4. 推荐**方案 A**：门禁委托 `decision_signoff_result.validate_signoff`（无模型、无凭证的只读面）并以 `conclusion=="finalize"` 为成功判据；无 `logical_id` 的 legacy 文件走现有「历史词表 + 档案重算」窄分支（`advance_phase.py:309-377` 语义不变），历史字节不回写。
5. 强制签收**范围**不需要也不应因迁移改变：仍由 `_key_has_decide_rows`（该 key 有任一 `kind=decide` 行）+ `signoff: disable` 决定（`advance_phase.py:281-307,244-256`）。迁移只把「哪个结论算成功」收窄到 finalize，不把签收扩到更多 key（AC-039）。但 `disable` 是**项目级**开关、且门禁侧返回 `[]` 静默，无法与「无决策行」区分（`advance_phase.py:244-256,867-872`）：建议只增加可观测的跳过原因，不改通过/不通过。
6. 真实链路契约已存在可复用：`consumed`≠完成、`executed` 需动作标签、`settled` 需 outcome、`signoff` 需 path+sha256、`file_verified` 由本次读打开文件并 `validate_signoff` 得出（`decision_lifecycle.py:74-114,647-720`；`decision_history.py:2293-2380`）。设计应在这条链上加 finalize 词表与 success 判据，**不新建第二套 ledger、不回填历史**。
7. 以上为读码结论，**不构成**设计批准、AC/QG/运行/签收通过；本 key 的联合设计与精确写面仍未批准。

## 证据

### A. 现有事实（全文读，行号为当前工作树）

**A1 唯一签收写入面（同次判断，不二次批准）**
- `mw.py:4531 _decide_sign_finalize`：一次 `decide_for(intent="answer")` → `decision_signoff_result.build_result` → `write_result` → `_decide_sign_finish`；`finalize` 才写文件（`mw.py:4927-5005`），`continue`/`user-confirm` 写 **0** 个签收文件、只记 `executed(action=<conclusion>, result="pm-handoff")`（`mw.py:5009-5035`，动作词表见 `decision_lifecycle.py:100-112`）。
- payload 固定 `second_approval: 0`（`mw.py:_decide_sign_payload_base`）；拒绝信息 `["dp25 answer is not in the finalize|continue|user-confirm set"]`（`mw.py:4799`）。
- 结论闭集：`decision_signoff_result.py:71 CONCLUSIONS=("finalize","continue","user-confirm")`；`dp25` 定义与三选项标签见 `decision_points.py:854-885`；执行器只回显、不写入（同处注释）。
- 写文件：`decide_signoff.py:516-660 render` 生成列 0 机器行（`conclusion`/`counted_rows`/`rows_sha256`/`engine`/`allow_empty`/`key`/`claims`/`ts`/`promote`/`demote`/`p0-open`，有 result 时追加 `record_version`/`dp`/`logical_id`/`decision_id`/`material_sha256`/`evidence_sha256`/`snapshot_sha256`/`initiator_role`/`retry_of`/`transport`/`model`/`confidence_source`），`render` 内 `result.rows_sha256 != facts.sha256` 直接 `SignoffError`；落盘走 `decision_signoff_result.py:275 _atomic_write_text`（temp+fsync+replace，父链 symlink/包含检查 `:199-260`）。
- 无 agent-session 门禁：`decide_signoff.py:698-716` 明示「authority 是决策模型，不是跑命令的进程」；对照 `mw decide dp apply` 仍有 agent-session 拒绝（`mw.py:3618-3625`）。两者对同一文件的写/用权限**不对称**（事实，非缺陷判定）。

**A2 done 硬门（现状）**
- `advance_phase.py:41 DECISION_CONCLUSION_RE = ^conclusion:\s*(continue|narrow|revoke)$`；`:339-343` 不匹配即返回 `SIGNOFF: ... 缺机器行 conclusion: continue|narrow|revoke` 并 return（**不再往下校验**）。
- `:361-375` 仅做 `decide_signoff.collect(...)` → 比 `rows_sha256`/`counted_rows`，`continue` 才跑 `verdict`；`:463-466` 规则无条件执行；`:244-256` disable 读 `.mw/decide.json`（项目级，读失败=没关）；`:281-307` `_key_has_decide_rows` 不排除 dp25 行（注释明示单调增长理由）。
- 门禁脚本有 **3 份字节镜像**（`.agents/skills/agentic-task/{scripts,core/scripts,claude/scripts}/advance_phase.py`），一致性由 `test_decide_sign_auto.py:298-317` 锁定。

**A3 同一文件的其它消费者（旧词表）**
- `mw.py:2233 _DP_SIGN_CONCLUSIONS=("continue","narrow","revoke")`、`:3485` 非法结论即拒、`:3611 _dp_apply` 用 `by=f"signoff:{conclusion}"` 写 authority-change。
- `decide_archive.py:70-81`（`_CHANGE_BY` 含 `signoff:continue|narrow|revoke`；`_CONCLUSIONS` 同三词）、`:528-542`（`by` 与 `conclusion` 联合校验）→ 若将来为 finalize 记 authority-change，**当前 schema 会拒绝**（潜在第三处阻塞）。
- 结论：finalize 文件今天在 `dp apply` 上恒拒（由 `mw.py:3485` 推断，未运行）。

**A4 历史只读投影**
- `decision_history.py:916-930 _CLOSED_SETS`（`conclusion` 三旧词、`change_by` 含三旧 signoff 值）、`:1021-1030 _SIGNOFF_STRUCT`：`finalize` 属「结构字段值不在闭集」→ `:1359-1395 _sanitize_carrier` 置 `None` 并计入 `invalid_fields`/`structural-fields-invalid`；`:3532-3571 _read_signoff` 追加 `unknown conclusion` 警告。**即：历史面也会把正确的 finalize 显示为未记录结论。**
- 但 workbench 的签收事实走新面：`:2293-2380 _signoff_fact` 用 `decision_signoff_result.validate_signoff(key_dir, key, expected_logical_id=<本记录>, expected_snapshot=<记录值>)`，`file_verified` 才是「本次读证明」；`:3226-3268` 只有 `signoff_verified` 才 `processing_state="completed"`，`:284 _NO_SIGNOFF_COMPLETION_ACTIONS={"continue","user-confirm"}` 使 dp25 的 continue/user-confirm 不要求文件。
- 只读性：`load_history`（`:3715`）无锁无写；签名/gate 读取前做 realpath 包含检查（`_inside`/`_rel_label`）；`consumed` 只算 receipt；`workbench-association-ambiguous` 对两 logical_id 抢同 decision_id 不做归属。

**A5 生命周期 / 任务快照**
- `decision_lifecycle.py:74 RECORD_VERSION=2`、`:77-88 META_KEYS`（identity/association 只在 meta，不进 material）、`:90 INITIATOR_ROLES`、`:96 OUTCOMES`、`:100 EXECUTED_ACTIONS`、`:114 STAGES`；`record_start` 在 transport 前落版本+关联（`:587`），`record_lifecycle` 按 stage 强制 schema（`:647-720`：settled 需 outcome、executed 需 action、signoff 需 path+sha256），`:928 versioned_logical_ids` 明确「缺 wire 行/失败捕获不使 v2 变 legacy」。
- `decision_task_state.py:16-45`：`None`=未记录、`[]`=明确无项（`:39`），`validate_observation_order` 拒 after\<before（`:43-49`）；history `_task_state_fact`（`:2279-2291`）区分 `recorded/unrecorded/withheld/invalid`。
- dp25 材料闭集：`decision_points.py:1695-1701` 五个必需路径；`:1804-1832` 三数组 `empty_is_value: True`；`:3007-3011 _is_blank` 只把 `None`/缺失当空（`[]` 是值）→ **AC-051 的「[]≠缺项」在材料侧已有机器判据**；缺项升级见 `:5263`。

**A6 result record（重试面，非成功权威）**
- `decision_signoff_result.py:67-73`（v2、dp25、三结论、`evidence/review/decide-results`）、`:384 build_result`（快照=key+dp+material/evidence/rows 摘要）、`:475 write_result`（同 logical_id 异内容拒绝、存 redact 后审计副本）、`:561 read_result`（仅缺失返回 None，坏记录抛错）、`:632-742 validate_signoff`（路径/symlink/包含 + record_version=2 + dp + 闭集 + snapshot 自重算 + 可选 expected logical_id/snapshot + 与 result record 交叉比对）。
- 事实边界：`validate_signoff` **不复算** result record 里 material 的摘要（存的是 redact 副本），文件本身也不含材料正文 → 材料正文不可由签收文件重建，只能由 result record 的审计副本读；「摘要存在」不等于「材料安全或正确」。

### B. 目标要求（本 RQ 只做观测/取证，不替协议定约）

| AC | 与本 RQ 相关的已确认要求 | 现状（A 节） |
|---|---|---|
| AC-038 | 仅有效 finalize 满足签收；continue/user-confirm 不冒充成功；文件≠phase done≠stage close；不二次 PM 批准 | 写入面已按此实现（A1）；门禁反了（A2） |
| AC-039 | 正确识别 finalize；不伪造旧标签/disable 绕门；不扩强制范围；受影响旧签收不无条件复用 | 四处词表不一（A2/A3/A4）；门禁无 logical_id/snapshot 绑定（A2） |
| AC-013 | 历史只读、原始字节 0 变化、不按当前注册补造 | `load_history` 无写（A4） |
| AC-014 | producer→writer→consumer→projection 可被隔离生产路径核验；秘密明文/注入执行 0 | 链路存在，cross-language（TS UI）未读 |
| AC-043 | 非法/缺项/服务不可用/无有效结论 → 阻塞且 0 放行，可有真实失败审计 | 拒绝分支齐（A1/A6），未测 |
| AC-050/051 | 动作证据与 round 结算可关联、时间不倒退；`null`≠`[]`；签收三数组仍为数组 | A5 已具备；签收文件不带三数组（在 result record） |
| AC-052 | 同事项重放/并发不重复；实质变化后旧批准不放行 | result record 幂等有；文件覆盖与「哪次判断」无门禁绑定 |
| AC-005/006/053 | QG 三选项与证据/缺口/未覆盖面；QG 不代签收、缺失不产生放行 | QG 侧未在本 RQ 取证；只确认「签收门不读 QG 结论」 |

### C. 候选方案（识别「同次判断 + 证据/适用范围」）

**方案 A（推荐）门禁委托已验证的只读面**
`advance_phase._decision_signoff_problems` 改为两分支：①文件**有** `logical_id` → `decision_signoff_result.validate_signoff(key_dir, key)`，成功判据 = `valid ∧ conclusion=="finalize" ∧ dp=="dp25-signoff-conclusion"`（后两者 validate 内已强制），失败原样返回 `validation.reason`；②文件**无** `logical_id`（legacy）→ 保留 `:339-375` 现行为（旧词表 + 档案重算），并明示「legacy 按历史词表受理」。
- pros：闭集与校验只有一份实现（`decision_signoff_result.py:71,632`）；天然带 logical_id/snapshot/result-record/父链安全检查；无模型无凭证；legacy 字节不动、可解释。
- cons：门禁是安装镜像脚本（3 份，A2），跨包 import 需沿用 `_load_decide_signoff`（`:218-242`）的 fail-loud 方式；必须写清「哪种文件适用哪条判据」，否则回到「用词表猜结论」。
- 风险：`validate_signoff` 需要 result record 一致；若 sign 路径的 `write_result` 失败（重试面缺）但文件已写，validate 仍判 valid（`record is None` 时跳过交叉比对，`:735-742`）——这是「文件是权威」的既定语义，不是漏洞，但**设计要明确记录该分支**。

**方案 B 门禁自持扩展词表**
正则扩为 `finalize|continue|user-confirm|continue|narrow|revoke`，并要求 `record_version=2`/`logical_id`/`snapshot_sha256` 行存在且自查 snapshot 一致性。
- pros：最小 diff，零跨包依赖。
- cons：**第二份 validator**（正是本次事故根因）；不查 result record；snapshot 重算逻辑复制会漂移；无法区分「文件被换过」；三处旧闭集仍是另一份事实源。

**方案 C 由 sign 写一行成功标记供门禁读**（如 `signoff_ok: true`）：拒绝。自述字段不是判断证据（AC-039 明确不以文本声明代真实证据），等于把门禁降级为一个布尔。
**方案 D 用 `signoff: disable` 绕门 / 关掉门**：拒绝。AC-039 明令禁止；且 disable 是项目级（A2），会同时豁免所有 key。

**适用范围建议**：不改 `_key_has_decide_rows` 判据；只为跳过原因（`disable` vs `no decide rows` vs `legacy`）产出可观测文本/审计，仍不改通过结论。
**幂等/并发建议**：同一 logical_id 重签走 `--retry-write`（0 次模型调用，`mw.py:4585-4660`）；不同 logical_id 的 finalize 覆盖同一路径时，旧 result record 必须仍可读、并在 history 里表现为两次 signoff 事实（不删旧），门禁判据绑定「文件当前 logical_id + 其 recorded snapshot」。

### D. 精确候选文件与接口 + 证据建议

| 目标 | 文件/接口（候选，未授权修改） | AC | 证据等级 |
|---|---|---|---|
| 门禁分支化 | `.agents/skills/agentic-task/scripts/advance_phase.py:41,309-377,463-466`（+2 份字节镜像） | 038/039 | L0 三份字节一致+调用链；L1 临时项目写一份 finalize 文件跑 `check_gate(key_dir,"done")` |
| success 常量单一来源 | `decision_signoff_result.py:71`（如 `SIGNOFF_SUCCESS=("finalize",)`），门禁与 history 共用 | 038/039 | L0 枚举点唯一 |
| 历史投影接受 finalize | `decision_history.py:925,1021-1030,3571`（legacy 词表限定到无 logical_id 文件） | 013/014/038 | L1 `load_history` fold 新 finalize 文件，断言 `workbench.processing_state=="completed"` 且 `signoff.conclusion=="finalize"` |
| dp apply 与 archive 闭集一致 | `mw.py:2233,3485,3611`；`decide_archive.py:70-81,528-542` | 039 | L0 闭集交叉；L1 apply 对 finalize 文件的最大可支持结果（拒绝或成功，二选一并写明） |
| 范围/disable 可观测 | `advance_phase.py:244-256,281-307,867-872` | 039 | L0 判定顺序；L1 三态（disable/无行/legacy）各自可见 |
| 材料不变量 | `decision_points.py:1695-1701,1804-1832,3007-3011` | 051 | L1 dp25 材料：`[]` 通过、`null`/缺项被拒 |
| 关联/时间 | `decision_lifecycle.py:587,647-720,928`；`decision_task_state.py:16-49`；`decision_history.py:2279-2380` | 050/051 | L1 start→executed→settled→signoff 链路 + before/after 时间倒退被拒 |

### E. 观测建议（正向 / 异常 / 重放 / 并发 / 秘密与注入 / 只读）

- **正向**：finalize → 文件机器行齐全 + 门禁通过 + `signoff` 生命周期行（path+sha256）；continue/user-confirm → 0 文件、`executed(action)`、`handoff`，门禁仍阻塞（AC-038/039/050）。
- **异常**：结论越界/缺 logical_id/snapshot 与 material 不一致/result record 不可读/父链含 symlink/`key:` 与目录不符 → 各自具体 reason，放行 0（AC-043）。注意门禁**现在**对 finalize 走的是「缺机器行」这条错误文案，会误导整改方向。
- **重放**：同 logical_id 二次 sign = 0 次模型调用、0 次新决策；两 logical_id 对同 decision_id → `workbench-association-ambiguous`，不归属（AC-052）。
- **并发**：同 logical_id 并发 → `record-start` duplicate 拒绝；文件写为 temp+fsync+replace；**不同** logical_id 并发 finalize 会互相覆盖同一路径 → 断言「旧 result record 仍可读 + history 两条 signoff 事实」（AC-052）。
- **秘密/注入**：签名材料含 `sk-`/Bearer 时，result record 存 redact 副本，但 `material_sha256` 是**发送原文**摘要（A6）→ 门禁不得以「摘要存在」推断材料安全；历史读侧 free-text 走 redact→clip→boundary-scrub、结构化值命中即省略（`decision_history.py:1050+`）；`gate.question/note`、签收 `claim` 只经 sanitizer 输出、不做 HTML 转义 → UI 必须按文本渲染，禁止 `innerHTML` 拼接（AC-014/051，跨语言部分未核）。
- **只读**：一次 `load_history` 前后对 archive/`sign-final.md`/ledger 取 sha256 应不变（AC-013）。

## 残留与未验证

- 全部结论为读码，**未运行**任何测试/CLI/服务；下列为明确未验证项。
- 未跟踪 `_missing_required`（`decision_points.py:3013`）在 sign 路径的完整调用栈：`[]`/非数组类型在运行期的实际行为只到 L0 读码（`:3007-3011` + `:5263`），未实测。
- 未运行 `mw decide dp apply`，finalize 文件被拒为静态推断（`mw.py:3485`）。
- 未读测试全文（仅定位 `test_decide_signoff.py:607-730`、`test_decide_sign_auto.py:298-317`），未核现有测试是否已锁新词表、也未判断哪些需同步更新。
- 未核安装/部署：3 份镜像是否已同步到真实项目、`install.py` 的 scripts→mirrors 同步行为未读。
- 未读 TS 侧/UI 消费者（`decision_dashboard.js`、`decision_monitor.py`）如何呈现 `signoff.conclusion` 与警告通道，AC-014 的跨语言段只到 Python 边界。
- 未读 `mw.py` 全文（570KB，定点读 sign/apply 区），未核其它 sign-final 读取点是否还有第四处词表。
- 设计/写面未批准：以上文件与行号只是候选定位，不含任何修改授权；本文件不宣称设计、运行、AC、QG 或签收通过。

## 上下文来源

- 全文读：`spec.md`（53AC 锁稿）、`evidence/h13-signoff-gate-link-confirmation.md`、`evidence/graduation-pm-review-20261025.md`、`goal.md`。
- 全文读（主源码）：`.agents/skills/agentic-task/scripts/advance_phase.py`；`packages/multi-workers/decide_signoff.py`；`decision_signoff_result.py`；`decision_lifecycle.py`；`decision_task_state.py`；`decision_history.py`（4211 行全读）。
- 定点读：`mw.py:4525-5175`（sign/finish/apply 入口与词表）、`mw.py:3611-3700`（dp apply）、`decision_points.py:840-900,1685-1835,3000-3075,4230-4300`、`decide_archive.py:60-100,525-545`、`decision.py:110-125,380-440`、`test_decide_sign_auto.py:296-330`、`test_decide_signoff.py`（grep 定位）。
- 未读：活配置 `.mw/decide.json`/`.mw/decide-points.json`、任何 gate/ledger/签收文件、其他 key 运行材料、凭证、`decide_registry.json` 导出件全文、UI/TS 全链、`mw.py` 全文。
