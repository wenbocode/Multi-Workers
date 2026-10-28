# integrity-review — dc-t08-integrity-review 审查证据（r2 首写基线 → 冻结终态）

审查时间: 2026-10-23（只读审查；工具面 = read/find/grep/ls，无 bash/git/hash 重算）
被审对象: `workers/dc-t08-ts-integration-r2`（TS 冻结终态）+ `workers/dc-t08-python-integration-r2` 的两个间接写（decision_dashboard.js / test_decide_sign_auto.py）。
on-disk 状态前提: `workers/dc-t08-closure-fixes/report.md` 自证 BLOCKED 且终态 hash 与首写前逐字节相同（零源码改动），故本审查读到的工作区文件即 r2 冻结终态。

## 0. 方法与可行性说明（重要）

- baseline-writeface.diff / final-writeface.diff 均为 PowerShell `>` 重定向产物：**UTF-16LE + 内容经 CP936 控制台解码产生确定性乱码**（如 先写问题原文→鍏堝啓闂鍘熸枃、—→鈹€/鈥?）。乱码是底层 UTF-8 字节的确定性函数，且两个 diff 对 decision-tool.ts 记录**同一 HEAD pre-image blob `6fdb5e9b8`**（index 行），因此「两 diff 逐行 verbatim 相同 ⇔ 底层字节相同」。本审查以此做等价基线比对，未做 worktree checkout。
- 已知盲区 A（乱码捕获吞字节）：捕获管线把「CJK 尾字节 + 后随 ASCII」非法 GBK 对吞成一个 `?`，故**被吞字节的具体身份（空格/引号/斜杠/换行）在 diff 中不可分辨**；此 33 字节改由 fix-decision-tool.py 记录 + 语法/结构/registry 交叉验证（见 §2）。
- 已知盲区 B：diff 不可见的文件区域无逐字节锚；但 decision-tool.ts 的**全部含 CJK 行都在两 diff 之一中成对出现**（逐一核对，见 §1），故实际无未锚 CJK 行。
- 恢复性构造（卡面要求的「baseline+HEAD 构造可靠原文」）因工具面无 git/脚本执行不可机械完成；已用上述同 pre-image 逐字配对法替代，覆盖度声明见 report「未覆盖面声明」。

## 1. decision-tool.ts：乱码恢复未改变任何无关原文

### 1.1 非 ASCII 行全量配对（baseline-writeface.diff 45–1426 ↔ final-writeface.diff 45–1663）

配对结果（偏移 +36 起，源自 r2 在 -182/-190 hunk 的 dp25 增量）：
- verbatim 相同（含乱码与 `?` 吞字节位置全部一致）：b78/80/84/92/93/117/121/169/200/247/250/261/271/275/415/416/509/553/556–558/560–562/564–566/569/572/657/690/691/695/880/909/1040–1042/1150/1206/1211/1212/1220/1226/1243/1331/1334/1369/1413/1416 ↔ f78/80/84/92/93/117/121/205/236/283/286/297/307/311/451/452/545/589/592–594/596–598/600–602/605/608/748/781/782/786/982/1011/1276–1278/1442/1447/1448/1456/1462/1478/1568/1571/1606/1650/1653。
- 唯一文本变化对：b635 ↔ f712 — r2 有意扩展 `writeLifecycle` JSDoc（回执解析/`recorded:false`/`duplicate` 语义 + 导出原因），CJK 锚「反馈缺失」两侧一致。属报告改动清单第 2 条，非恢复事故。
- final 新增非 ASCII 行（r2 新增代码）：f670/1077/1079/1106/1568/1571 — 除 f1606（↔b1369 verbatim）外均 ASCII/制表符类；**final 中所有含 CJK 行均有 baseline 锚且 verbatim 匹配**。
- 其他 5 个源文件（index/pm-orchestrator/triage-client/ui-bridge/worker-mode）：非 ASCII 行逐对 verbatim 相同（1427+ ↔ 1664+ 区段全对上），未受事故影响（事故仅 decision-tool.ts）。

### 1.2 hunk 结构对账（`^@@` 清单）

- decision-tool.ts：final hunk 集 = baseline hunk 集 ∪ {合并 -182/-190→-182,14、新增 -493（parseDecisionJson 回溯）、-629 并入 -585,52、-307/-539/-585/-705 新侧增量} — 全部对应报告改动清单（dp25 签收路径、material 入参、--json 回执、parseDecisionJson）。**无来路不明的 hunk 出现或消失。**
- pm-orchestrator：final 新增 -8/-18/-48,17/-2094,459（dp2 seam 完整退役），baseline 已有 -2427,127 部分退役（r1 遗留）→ 与「重派同一写面、r1 已写入」一致。

### 1.3 34 处恢复位点核对（fix-decision-tool.py FIXES = 34 条目）

- 当前 on-disk decision-tool.ts 全文件扫描：**0 个乱码残留**（鈥/锛/銆/鍏 等均无）、**0 个 CJK 邻接 `?` 损伤标记**。
- CJK 字符逐字验证（乱码反演 vs on-disk）：b78↔ts183「不要自行猜测」；b556–566↔ts744–754 三组固定材料提示词逐字一致（含 全角标点/`；"`/`。"` 收尾）；b80/84/200/271/572 等注释行一致。
- 33 个被吞 ASCII 字节分类：5 个引号（语法强制：字符串字面量收尾，tsgo 0 + 214/214 绿证明）、3 个换行（JSDoc 结构，on-disk ts24–25、ts230–231、ts398–399 确认两行形态）、24 空格 + 1 斜杠（fix-decision-tool.py 逐条记录、上下文唯一匹配）。dp2 词「判断继续/拆小/直执/上抛人」的斜杠恢复由 `packages/multi-workers/decide_registry.json:118`（继续、拆小、直接执行、上抛人 四动作）佐证。
- 测试锚点：`test/suite/decision-tool.test.ts:424`（`blocked on decision ${dp}`）与 `:491`（`disabled ≠ approval`）在 green-decision-tool.log（23/23，vitest v4.1.9）下真实通过。
- 计数澄清：报告称「34 处后续字节」；脚本实为 34 个修复位点，其中 1 条为 no-op（identical replace），实际恢复 33 字节 + 2 个 stage-2 字符选择（。↔、）。

### 1.4 残余（明确覆盖不足，不猜）

- 24 空格 + 1 斜杠位点的「字节身份」无法由 diff 本身证明（盲区 A）；证据链 = 修复脚本记录 + 语法/结构/registry 佐证，非字节级。
- 三组材料提示词全文**未被任何 TS 测试断言**（仅 unavailableDirective 与 `disabled ≠ approval` 被钉）；提示词文本完整性靠 §1.1 的 diff 配对（强）而非测试（弱）。

## 2. Python 两间接写

### 2.1 decision_dashboard.js（patch_dashboard_js.py，单 hunk）

| 项 | 值 |
|---|---|
| snapshot 原文 | `evidence/snapshot/files/decision_dashboard.js`（sha256 bd8a374f…，99997 B，2294 行；snapshot/sha256.txt 2026-10-23T02:51:52Z） |
| 脚本 | 单 hunk：renderFacetOptions 内 `old`（13 行，assert-once）→ `new`（23 行，+10 行净增，+638 B 与 sha256_final 100635 B 一致） |
| on-disk 终态 | 2304 行（=2294+10 精确）；508–527 行与脚本 `new` 逐字一致；`applied`/`withheld` 仅出现在该 hunk 与既有 480 行（两文件同位，非本次改动） |
| 契约/安全 | AC-019 对齐：被输出策略 withheld 的筛选名不再从本地 state 回插 `<option>`（识别出的 secret 不回显 DOM）— **强化**，无断言删除，无测试删除 |
| ledger | 该写为脚本间接写，无台账登记（见 §3 建议） |

### 2.2 test_decide_sign_auto.py（rewrite_sign_auto_tests.py）

- 量账：snapshot 29402 B/749 行 → 终态 24890 B/633 行（−4512 B/−116 行）；用例数 27（12F/15P）→ 22（22P）= −15 defs + 10 defs，**精确守恒**；head 12 个用例与全部 helper（`_project/_backend/_append_true_engine_row/_assert_legacy_refusal` 等，L24–200）保留，`dataclasses` import 在位。
- 删除的 15 个 def 中 5 个以同名强化版重写，10 个名字真删（snapshot 294–619 区段）；逐个安全断言去向：

| 已删用例 | 替代定位 / 判定 |
|---|---|
| test_sign_auto_persists_the_mode_and_exits_zero | 同名重写（模式持久化 + 尾随 legacy 拒绝断言） |
| test_auto_decide_writes_signed_via_auto_decide | 旧自动签写面按批准设计退役；反向不变量由 `_assert_legacy_refusal`（无 sign 文件、无 authority-change 行）+ 新写面 `test_decision_context_signoff_cli.py`（47P）+ integration `test_valid_signoff_file_is_the_completion_authority` 覆盖 |
| test_auto_decide_is_allowed_inside_an_agent_session（旧 AC-026） | **有意反转**：`test_legacy_face_is_refused_inside_an_agent_session`（同 env，exit 2 + 零写）— 安全增强，符合新 AC-020 |
| test_auto_decide_narrow_with_no_rows_is_written | 退役（dp25 结论集无 narrow）；零写由 refusal 矩阵覆盖 |
| test_unavailable_transport_writes_nothing_and_names_the_reason | `test_legacy_face_is_refused_for_every_configuration`：**backend.calls==[]（零模型调用）**+ 零写，强于旧断言 |
| test_dp25_disabled_says_not_required_and_writes_nothing | 同上第二块（disabled dp25 仍拒绝）；disable 正面语义由 head 保留用例（disable_prints/dry_run/done_gate）覆盖 |
| test_dp25_not_registered_says_not_required_and_writes_nothing | 同上第三块（unknown dp 抛错仍拒绝、零写） |
| test_sign_without_jev_says_not_required_and_writes_nothing | `test_sign_without_jev_is_refused_not_a_silent_success`（同项目形态；exit 0→2 为批准的行为变更，零写不变） |
| test_auto_decide_continue_still_runs_the_verdict（模型答案不绕过本地判据） | `test_decide_signoff.py` verdict 块（N=0/seq/hash-chain/invalid conclusion/allow_empty 界定）+ `test_module_verdicts_still_gate_the_framework_face`（585–591）保留门禁内容判定 |
| test_dp25_rows_never_enter_the_signed_counts（D-067） | 同名重写，直接对 `collect()` 断言 rows/sha 不变 — 保留 |
| test_dp25_is_registered_with_the_contracted_shape | 同名重写，新增钉死四部分 REQUIRED_STATE_FIELDS 与 finalize\|continue\|user-confirm |
| test_dp25_is_on_by_default_and_the_default_signoff_path_asks_jev（W11） | 拆分：`test_dp25_is_on_by_default`（默认开）+ refusal 矩阵断言默认路径**不**问 jev（calls==[]，按设计反转） |
| test_dp25_signs_any_key_not_just_the_fixture_key（per-key） | `test_collect_counts_only_the_requested_key`（key 隔离）+ `test_decision_context_signoff_cli.py::test_sign_stdin_requires_the_envelope_key_to_match_the_command_key`（meta.key≠--key → rc 2） |
| test_dp25_executor_is_not_called_on_the_answer_path | 同名重写（executor probe 断言零调用） |
| test_intent_act_returns_the_echo_and_never_writes_the_sign_file | 同名重写（+config 字节不变断言，增强） |

- AC-020 对齐：所有新拒绝用例断言 exit 2 + `nothing was written` + 无 sign 文件 + 无 authority-change 行 + 模型调用 0 — 无伪造成功、拒绝路径零发送。
- 重写后 registry-shape 用例钉的结论集（finalize|continue|user-confirm）与 r2-Python 报告的框架门禁阻塞（advance_phase.py 只认 continue|narrow|revoke）互相印证 — 一致，非本次审查新增阻塞。

## 3. 台账（ledger）缺口与登记建议（只建议，不执行）

两处脚本间接写均未产生任何台账/authority-change/trace 登记（PM 卡面「间接脚本写漏 ledger」属实）。建议 PM 补两条追溯登记（内容要点，非本角色执行）：

1. decision_dashboard.js：actor=`evidence/patch_dashboard_js.py`（单 hunk，assert-once）；变更 = snapshot bd8a374f…99997B → final 359117cf…100635B（+638B/+10 行）；性质 = AC-019 强化（withheld 不回显）；补偿控制 = 本审查 §2.1 逐字核验。
2. test_decide_sign_auto.py：actor=`evidence/rewrite_sign_auto_tests.py`（REMOVE 15 + NEW 10）；变更 = ec4f5eda…29402B → 047684d4…24890B（−4512B）；性质 = 批准的旧计数面退役 + 拒绝契约迁移，安全断言映射见 §2.2 表；补偿控制 = 本审查 §2.2。
3. 流程建议：后续凡以脚本整文件重写源码/测试，写后即时向本任务 trace.log 追加一行机器可读登记（path/actor-script/sha-before/sha-after），避免依赖事后审查补账。

## 4. 其他观察（不展开）

- `evidence/restore-decision-tool.py`（r2-TS）对已归档的 baseline-writeface.diff **不可能成功**：该 diff 为 UTF-16+CP936 乱码（其 assert `先写问题原文` 必败）且含捕获期合并行/合并 hunk 头（如 b200「…state 鈥?- * field…」、b1758 内容行吞并 `@@ -50,9 +56,10 @@`，hunk 计数校验必败）。应为被放弃的替代方案，建议标注「superseded/unused」，防误导后续审计。
- `final-diff-stat.txt` 覆盖 19 文件（宽于 6 文件写面 diff：含他会话并发改动如 claim-bypass/claim-coverage/dispatch-claims-render、decide-registry.generated.ts 等）；冻结完整性的权威记录是 `final-hashes.txt`（15 路径，r2 自核 mismatches=0）。decide-registry.generated.ts 等不在本卡固定审查面，未审。
- 两 diff 中 `index.ts` 的 post-image blob 相同（9b50fa8e9），与「index.ts 无改动」声明一致。
