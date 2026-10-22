# Quality Gate Review 2 — mw-decision-substitution（QG-review-2, 2026-10-20）

- 审查者: worker `ds-qg-review-2`（type: review，卡 `tasks/QG-review-2.md`，本轮为修复批次关闭判定的总卡复审；窄卡 `ds-qg-review-2c`/`ds-qg-review-2d` 的 c/d 报告已并行落盘，本报告独立取证并吸收其结论）
- 方法: 静态审计（逐文件精读 + 全仓 grep + 与 Python 权威逐分支对照）。本会话工具面无命令执行通道，**未执行任何测试**；所有"测试绿"证据引自 FIX-A..E 各 worker 的运行记录（下文逐处标注），行号为本轮实际读取位置。

## 结论

**PASS** —— 第一轮 6 条发现（4 major + 2 minor）**全部关闭**：MAJOR-1/2（FIX-A）、MAJOR-3（FIX-B + FIX-E 改动 1）、MAJOR-4（FIX-C + FIX-E 改动 2）、MINOR-1/5（FIX-D）均以「反面用例能红」的方式落地；修复未引入新的 D-036 违约、fail-open 或跨层漂移；AC-001..015 覆盖等级无翻转（partial 项与第一轮同因）。发现两个新 minor 口子（均非本批次引入的缺陷回归，已记录）：§3 文档对 dp1 采纳条件描述不完整；`evidence/sign-final.md` 根落位只在 `worker_file` 通道设防（write/edit/bash 仍只认 review 落位，不构成门禁绕过）。

## 证据

### MAJOR-1：`ask_decision` 镜像与伪 id/acted —— **关闭**

- 改了什么：`readDecisionAuthorization`、`ASK_DECISION_DP_TIERS`、`AskDecisionAuthorization`、`defaultAuthorization`、`isMode`、`ASK_DECISION_DEFAULT_MODE` 全部删除；工具不再读 `.mw/decide-points.json`。
- path:line：`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:643-651`——`decision_id`/`mode`/`acted` 三个键只从子进程 `response` 取值（`const acted = response.acted`，`:645`），缺/错任一键 → `unavailable("bad-response")`，不本地补；`:620-629` `escalated_reason` 原样透传、与冻结 8 值 legacy `unavailable` 键并存不折叠；`:579-596` 缺必填字段的 state 在**零 spawn** 下以 `input-incomplete` + `missing_fields` 拒绝（MAJOR-2 修复面）。
- grep 级证据：全仓 `grep readDecisionAuthorization|ASK_DECISION_DP_TIERS` 零命中；`decision-tool.ts` 内 `decide-points` 仅存于 `:34` 头注释（描述 Python 是权威）。`acted` 全文件 15 处命中均为注释/接口/透传/trace，无任何 `mode==="auto" &&` 反推表达式。
- 反面证据（能红）：`decision-tool.test.ts:234`（替换掉原 "derives mode/acted from the table" 的用例）——同一子进程答案分别在**无表 / 表与子进程结论相反（enabled:false,mode:suggest）/ 表是坏 JSON** 三种目录下断言 payload 完全一致且等于子进程四键。变异：恢复读表推导 → tableDir 的 payload 变 `unavailable:disabled`，全等断言即红；恢复 `` `${dp}:${trigger}` `` 本地拼 id → `decision_id` 断言（`:278` `not.toContain("ds-t05-ask-tool")`）即红。`:492` "does not pre-gate on the authorization table"：表说 dp12 off 仍 spawn（`calls` 长度 1）并报告子进程的 disabled 判定——恢复表预门控即红。`:323` "refuses to fabricate the authority keys"：子进程缺 id/mode → bad-response，本地推导会绿掉此用例。

### MAJOR-2：state 恒 `input-incomplete` 且原因误导 —— **关闭**（行为面）

- 改了什么：新增 `missingDecisionStateFields`（`decision-tool.ts:279-299`）复用 `triage-client.ts` 的 `validateStructuredState`/`REQUIRED_FIELDS_BY_DP`（只复用不复制），过滤 Python `_state_builder` 自填的 `questions_version`（`decision_points.py:278-289`），对 dp1/dp2/dp3 零 spawn 返回 `input-incomplete` + `missing_fields`（字段名 L0）；`unavailable` 分支透传 `escalated_reason`。
- 字段清单与 Python 逐项对照（本轮独立核对，非信注释）：`REQUIRED_STATE_FIELDS`（`decision_points.py:624-672`）dp1=13 项 / dp2=14 项 / dp3=12 项；TS `UNIVERSAL_REQUIRED_FIELDS`（`triage-client.ts:344-354`，9 项）∪ `REQUIRED_FIELDS_BY_DP[dp]`（`:363-372`）与 Python 三个集合**逐项相等**：dp1 差 `requested_type/task_summary/scope.write_scope/scope.ext`、dp2 差 5 个 `progress.*`、dp3 差 `task_summary/ambiguity.kind/ambiguity.question`，并集后与 Python 全集无遗漏、无多余。`buildDecisionState`（`decision-tool.ts:264-274`）只产 `{v,dp,key,task_key,task_summary}`，故报出的缺字段集 = Python `_missing_required` 对同 state 的结果（dp1 8 / dp2 10 / dp3 7 项，`questions_version` 除外）。
- 反面证据：`decision-tool.test.ts:364` 断言三个 dp 的 `missing_fields` **精确数组** + `outcome.spawned===false` + `calls` 为 0——stub runner 备好了 `available:true` 也不可绕过预拒。若字段清单与 Python 漂移（增/删/改名），精确数组断言即红。`:451`/`:492` 用例钉住 `escalated_reason` 与 legacy reason 并存透传（7 值词表回环）。
- 残余（不阻塞关闭）：**字段清单的持续锁不跑 Python**——`decision-tool.test.ts:710` 是对 `REQUIRED_STATE_FIELDS` 源码文本的正则锁（仅 dp id 集）；`triage-client-state.test.ts:520` 真跑 Python 但只锁 `REQUIRED_FIELDS_BY_DP` 的**键**是活注册表 id，不锁字段名清单。FIX-A worker 修复时以真实 `python _missing_required` 探针核对过一次（8/10/7），但无提交内的执行锁。漂移后果是 fail-closed（TS 少报 → Python 拒 → `escalated_reason=input-incomplete` 透传；TS 多报 → 过度预拒），不会 fail-open。另按 FIX-A 要求 4 的设计，`ask_decision` 对 dp1/dp2/dp3 从此恒为结构化拒答（这三 dp 的生产答案走 triage-client / pm-orchestrator / `worker-mode.buildDp3State` 专用链路，不丢功能；`decision-tool.test.ts` 旧「恒绿成功」stub 已删除）。

### MAJOR-3：dp2/dp3 镜像与 Python 降级语义分歧 —— **关闭**（FIX-B 主体 + FIX-E 改动 1 收尾）

- dp2：`Dp2Authorization` 收窄为 `{enabled, source}`（`pm-orchestrator.ts:2045-2048`，`mode` 字段删除——收窄式 API 变更后全仓无残留调用点，仅 `dp2-narrow.test.ts` 同步重写）；`readDp2Authorization`（`:2067-2086`）+ `dp2RowForceOff`（`:2060-2065`）。`decideDp2Checkpoint` 的 `acted` 改由子进程 `payload.mode` 判定（`:2332-2334` 提取，缺/非法 → `undefined` → `acted=false` fail-closed；`:2349` `mode === "auto" && action === "narrow"`）。本地读仅保留 `enabled` 零 spawn 短路（`:2275-2276`），两处注释显式声明「NON-AUTHORITATIVE、分歧以 Python 为准」（`:2033-2043`/`:2270-2274`）。
- dp3：`dp3RowForceOff`（`worker-mode.ts:4486-4489`）与 dp2 同型；`readDp3Policy`（`:4501-4522`）非对象行 → off、L3 → off。**FIX-E 改动 1**：spawn 路径的 `childMode` 只认子进程自报值——`worker-mode.ts:4937-4939` `payload.mode` 非 `auto|suggest` → `escalate("unavailable","3a","decision mode missing")`，原「回退 `input.policy.mode`」已删（该回退曾使本地 auto 在子进程哑默时注入 steer，违反 D-036/D-041）。3c 零 spawn 路径保留 `policy.mode`（`:4863`）：该路径 Python 从不参与（无子进程可问），`Dp3Policy.mode` 注释（`:4744-4746`）与 doc §3（`docs/decision-substitution.md:215-218`）均已写明此例外。
- 与 Python `_parse_row` 逐分支对照（本轮独立核对 `decision_points.py:884-968`）：L2 非对象行 → off（TS `recordOf/asPlainRecord===undefined` → `enabled:false, source:"invalid"`）✓；L3 mode 非 auto|suggest → off ✓；L3 note 非字符串 → off ✓；L3 tier 非字符串 → off ✓；L5 enabled 非布尔 → off ✓；**L4 tier 值越界 → 不关**（TS 不检查 tier 值）✓；**L7 tier ≠ 注册表 → 不关** ✓；L0/L1 缺文件/坏 JSON → 注册表默认（dp2/dp3 均 P2 → on/auto）✓；可用行 `enabled !== false` 取表值 ✓。第一轮点名的两处实测分歧（非对象行回落默认、坏 note 不读）全部消除。
- 反面证据：`dp2-narrow.test.ts:270`（非对象行 `"yes"` → `readDp2Authorization()==={enabled:false,source:"invalid"}`、零 spawn、告警与 off 基线逐字节相同）；`:293`（L1/L2/L3×4/L5/L4 全矩阵 + 显式 off）；`:468`（本地 auto + 子进程 suggest → 不 act；子进程无 mode → fail-closed 无 acted=1）。`dp3-answer.test.ts:496`（L2/坏 note/坏 tier → off）、`:521`（坏 note → 零 spawn、无 trace 行、回人工 NC）、`:556`（子进程 suggest 胜过本地 auto 行，无 steer）、`:571`（**FIX-E 用例**：`{mode:undefined}` 与 `{mode:"bogus"}` 两变体 → escalate、`escalated_reason=unavailable`、零 steer、无 `decision:` 头行——把本地回退路径钉成会红）。变异自证：恢复 L2 回落注册表默认 → `:270`/`:293` 红；恢复 mode 本地回退 → `:571` 红。
- 说明：第一轮 MAJOR-3 的字面违反（TS 读表）按 QG 报告给出的收口方式处理——保留为零 spawn 短路 + 逐分支对齐 + 「分歧以 Python 为准」注释，且 spawn 路径的 mode/acted 全部来自子进程。3c 的 `policy.mode` 是零 spawn 本地判定的固有例外（有注释、有文档、FIX-E 后 spawn 路径无任何 mode 本地来源）。

### MAJOR-4：签收守卫不覆盖 `worker_file` —— **关闭**（FIX-C 主体 + FIX-E 改动 2 收尾）

- 改了什么：`registerDecisionSignoffGuard` 新增 `toolName === "worker_file"` 分支（`xkey-gate-guard.ts:492-499`）+ 单一判定函数 `isDecisionSignoffEvidenceTarget`（`:373-389`）；固定名 `DECISION_SIGNOFF_BASENAME` 只写一次（`:333-335`）。方案选守卫分支而非 `judgeWriteTarget` 拒绝表：后者是派发判定/shell 守卫/worker_file 三处共用谓词，改它会波及判据矩阵，而 `dp apply`（Python CLI）不经该谓词。
- 判定语义（对照 done 门禁 `advance_phase.py:98-110` 只认 `evidence/review/sign-final.md`）：worker_file 写 `evidence/review/sign-final.md`（tail=[review]）→ 拒；`evidence/sign-final.md`（tail=[]）→ 拒；`.agenticdoc/<key>/evidence/…` 两种落位同拒；win32 大小写折叠除外无其它命中。**FIX-E 改动 2**：`lastIndexOf("evidence")` → `indexOf("evidence")`（`:385`）——深路径 `evidence/research/evidence/sign-final.md` 从误拒变放行（首个 evidence 段才是落位面，深层 evidence 是产物名的一部分，注释 `:382-384` 写明）。
- 反面证据（真实 tool_call dispatch，faux provider → Agent loop → 守卫 → block，非单元调用）：`decision-signoff.test.ts:305` 两落位拒绝用例（`isError=true`、人写文件字节不变、无新文件落地、`[DECISION_SIGNOFF]` trace 原文两行）；`:347` 不过度拦截用例（`evidence/review/review-notes.md`、`evidence/research/notes.md` 真落盘、零拒绝 trace）；既有 write/edit/bash 三通道用例（`:223` 区段）零改动继续绿；`xkey-gate-guard-coverage.test.ts:361` **FIX-E** 深路径放行用例（`evidence/research/evidence/sign-final.md` 经真实 worker_file 落盘）。变异自证：删掉 worker_file 分支 → `:305` 两条结果变成功 + 文件落地 → 红；把 `indexOf` 改回 `lastIndexOf` → `:361` 红。纯判定断言 `:182-196` 覆盖两落位/两基/反斜杠/`.bak`/`sign-final2.md`/`progress.md` 负例。
- 生产接线：`index.ts:60` 于双载入 flag 之后、PM/Worker 分支之前在**每个模式**注册守卫；`activate()` 级测试（`decision-signoff.test.ts` "production wiring" 用例）证明真实注册面生效。

### MINOR-1：dp1 分歧样本被计为采纳 —— **关闭**

- 改了什么：`dispatchDecisionOf`（`ui-bridge.ts:280-287`）新增分歧闸：`available && mode==="auto" && triage_type!==undefined` 后追加 `if (result.triage_type !== dispatchedType) return undefined`——分歧 → 不采纳（acted 无、不写 `decision:` 头行），与 suggest 同型；空/缺实派 type 同样 fail-closed（`triage_type !== ""` 恒真 → undefined，无「未知即采纳」）。调用点 `computeDispatchTriage`（`:523`）传入**计划点真实实派 type**（`planDispatchFrontmatter` 的 `dispatchedType: input.taskType`，`:1737`），两个派发入口（`dispatch_worker`/`/worker`）都经同一计划点。`mergeDecisionHeader`（`:2176-2181`）`!decision?.acted` 即原字节。settle 侧无头行即跳过关联 → 分歧不再以 `outcome=ok` 进一致率分子。
- 反面证据：`decision-association.test.ts:687`（disagree + auto：advice=coding、实派=research → `disagreement=true`、`decision===undefined`、`result.decision_id` 保留可观察、task.md 与**关闭态基线逐字节相同**——非「不含某子串」式弱断言）；agree+auto 写头行（`:667-684`，消费点声明 acted=true 而子进程 acted=false 也被如实透传）；suggest 三态（`:718` 逐字节对照）。
- 说明：FIX-D 卡里「trace 仍带 decision_id」在磁盘 trace 上未单列（`[DECISION] dp1 state=…` 行与 ledger detail 均不含 id）——与 suggest 同型（分歧答案的 id 留在 Python 档案行 `decisions.jsonl` 与内存 `TriageResult`），不构成采纳误计复发；2d 报告同判。

### MINOR-5：3a 超限措辞 —— **关闭**

- 改了什么：`Dp3EscalatedReason`（`worker-mode.ts:4452`）增加 `input-oversize`；3a 超限分支（`:4892`）`escalate("input-oversize", "3a", "canonical state > 2000B")`，先于 runner 调用。
- 词表判定（FIX-D 卡要求显式回答）：`input-oversize` **本来就是** Python `ESCALATED_REASONS` 7 值成员（`decision_points.py:101-111`：disabled/unavailable/input-incomplete/input-oversize/low-confidence/over-authority/p0），与档案层同源集（`decide_archive.py`）一致；TS 侧 `Dp3EscalatedReason` 加该值后仍是 7 值的**子集**（4/7→5/7 对齐），`triage-client.ts`/`decision-tool.ts` 对该字段类型均为 `string`、无共享 union——**是对齐，不是加宽**；Python/档案/CLI 侧零改动；legacy 8 值 `reason` 映射（`mw.py:855-856` → `budget-exhausted`）不变。
- 反面证据：`dp3-answer.test.ts:626` 用例（2100 字节 phase 推高 canonical state 越过 2000B）驱动真实 worker settle 链：`stub.calls===0`、trace 单行含 `escalated_reason=input-oversize`、`sub=3a acted=false`、`nc_raw=1 nc_human=1`、无 steer 注入。变异：改回 `input-incomplete` → trace 断言红；去掉预算检查改为强发 → `calls===0` 红。

### AC 矩阵复核（AC-001..015）

**结论：无翻转——修复批次没有把任何 AC 从 covered 变 partial，也没有把 partial 变 covered。**

- 口径说明：第一轮报告 §A 表按行数是 **13 covered / 2 partial**（partial = AC-003、AC-004），但其「残留与未验证」第 2 条又把 AC-007（真实样本可查）并入只能判 partial，得出 12 covered / 3 partial。本卡给定的基线 12/3 与残留节的口径一致；两口径都是第一轮报告自身的簿记差异，不是本轮功能变化。本轮按 12 covered（AC-001/002/005/006/008/009/010/011/012/013/014/015）/ 3 partial（AC-003、AC-004、AC-007）/ 0 missing 复核。
- 逐条状态不变的原因：AC-003 partial（启用态零真实运行，全 stub harness 证据）、AC-004 partial（档案 `decide` 行 `intent="answer"` 下恒 `acted=false`，报告 acted 计数恒 0——D-035 设计如此，且 MINOR-2 已把该事实写进 doc §3）、AC-007 partial（仓库内零真实 settle 样本）。三者依赖真实启用端到端，修复批次不触及。
- 修复带来的**增强**（不改变等级）：AC-009 的 worker_file 通道缺口（MAJOR-4）关闭，守卫四通道齐；AC-011 的「TS 只持 id」例外从三处镜像缩到两处已注释非权威预读 + 3c 零 spawn 例外，ask_decision 镜像删除；AC-014/AC-015 的 disagree 分支现与 suggest 同型（task.md 字节与关闭基线全等，`decision-association.test.ts:715` 逐字节断言）；AC-001 的关闭态等价在 dp2/dp3 坏行场景补齐（L2/L3 → 零 spawn 字节同构，dp2-narrow:270 / dp3-answer:521）。

### 测试有效性抽样（≥3，均为行为级非镜子级）

1. **`decision-tool.test.ts:234`（替换 MAJOR-1 旧用例的那条）**：驱动真实 `runAskDecision`（子进程只在 `DecideRunner` seam 打桩——外部进程是合法 seam），在无表/相反表/坏表三目录断言 payload 全等 + `spawned===true` + 请求信封逐字节。回退路径：恢复读表推导 → payload 不全等即红；恢复本地拼 id → id 断言红；恢复表预门控 → `:492` 的 `calls` 长度断言红。旧行为（镜像推导）会被这组用例直接判死。
2. **`decision-signoff.test.ts:305`（真实 dispatch，非纯函数断言）**：faux provider → 真实 Agent loop → `registerDecisionSignoffGuard` 注册面 → `{block,reason}` → 工具结果 isError、文件不落地、trace 行原文。回退路径：删 worker_file 分支 → 两条工具调用成功、文件落地、trace 计数 0 → 红。配对的 `:347` 防过度拦截用例反向咬合（守卫误伤 evidence/** 也会红）。
3. **`decision-association.test.ts:687`（卡点名的 disagree 用例）**：驱动真实 `planDispatchFrontmatter` + `writeDispatchTaskMd`，对 disagree+auto 断言 `decision===undefined` 且 task.md 与关闭态基线**逐字节相同**。回退路径：删分歧闸 → `decision` 有值 → 头行写入 → 字节比较红（不是「不含子串」可以蒙混的弱断言）。
4. （补充抽样）**`dp3-answer.test.ts:571`（FIX-E）**：`{mode:undefined}`/`{mode:"bogus"}` → escalate、零 steer、`escalated_reason=unavailable`——恢复本地 mode 回退即红；**`dp2-narrow.test.ts:270`**：L2 非对象行零 spawn + 告警字节同构——恢复回落默认即红；**`dp3-answer.test.ts:626`**：超限 → `input-oversize` 零 spawn——改回旧措辞即红。

### 文档-代码一致性（docs/decision-substitution.md §3/§7 新增内容）

- §3 新增「档案 `acted` ≠ 消费侧生效」要点（MINOR-2）：与代码一致——Python `intent="answer"` 恒 `acted=false`（`decide_for` D-035 分支），消费侧 acted 在 trace `[DECISION] acted=1` 与 `decision:` 头行，报告指标数档案 acted（恒 0）。✓
- §7 新增两行（MINOR-3/4）：dp3 3c 本地复用零档案行——与 `worker-mode.ts` 3c 零 spawn 一致；legacy `mw decide run` 不落档案行——与 `mw.py` `_decide_run` legacy 分支一致。✓
- FIX-E 补充：§3 dp3 子进程未报 mode 即上抛、不回退本地（`:215-218`）；§5.2 worker_file 签收守卫只认两落位、深路径可写（`:385-387`）。✓ CHANGELOG `### Fixed` 首行有对应条目。✓
- design.md §3 补 D-036/D-038/D-041 行 + D-037/039/040/042 编号说明（MINOR-6 doc 侧关闭）。✓
- 遗留小口子（非本轮修复引入）：§3:213 描述头行条件仍是「`mode=auto` 且带 `decision_id`」——FIX-D 后实为必要不充分（还要求 `triage_type===实派 type`），分歧闸未写入正文；§6.2 引用「pm/decision-tool 套件 mode=suggest never acts」的用例定位已过时（suggest 用例实际在 decision-association/dp2-narrow/dp3-answer）。均为措辞级，见残留。

### 修复批次回归审计（审计目标 2）

- **新 D-036 违约**：无。全仓读 `.mw/decide-points.json` 的实现现为 Python 权威 + 两处带「NON-AUTHORITATIVE / 仅零 spawn 短路 / 分歧以 Python 为准」注释的 TS 预读（`pm-orchestrator.ts:2071`、`worker-mode.ts:4505`）；decision-tool/triage-client/ui-bridge 均不读表。
- **新 fail-open**：无。dp2 子进程缺 mode → `acted=false`（fail-closed）；dp3 spawn 路径缺/坏 mode → escalate（FIX-E，fail-closed）；3c 本地 mode 是零 spawn 判定的必要例外且有注释/文档/用例三重钉住。第一轮 MAJOR-3 唯一的真实 fail-open（3c 在 Python 会 force-off 的坏行上仍可执行）已由 `dp3RowForceOff` → `enabled=false` → 完全旁路关闭。
- **跨层漂移**：`dp2RowForceOff`/`dp3RowForceOff` 是 `_parse_row` force_off 半边的文本镜像，无执行级锁（Python 改降级层需手工同步两处，注释已钉「改这里」）；`REQUIRED_FIELDS_BY_DP` 字段清单同前述仅源码/硬编码锁。与第一轮 MINOR-9 同类，风险方向 fail-closed。
- **收窄式 API 变更**：`Dp2Authorization.mode` 删除后全仓无残留引用（grep 仅剩接口定义与 `readDp2Authorization` 本体，消费点只取 `enabled`）；FIX-B 报告记录的并行在飞 tsgo rc=2（decision-tool.test.ts 对 FIX-A 改名的 missing export）在 FIX-A 落盘后复跑 rc=0。
- **FIX-D 的 cp936 事故**：FIX-D worker 自报曾因 `Set-Content` 误用让 `dp3-answer.test.ts` 经 cp936 往返丢字节并已逐字节还原；本轮 grep 该文件无 U+FFFD/乱码残留，FIX-E 复跑该套件 21 例绿。无 git 基线可做独立字节 diff，见残留。

### 测试运行记录（引自各 fix worker，本轮未复跑）

| 套件 | 计数 | 来源 |
| --- | --- | --- |
| decision-tool | 23 passed | FIX-A |
| triage-client-state | 31 passed | FIX-A（内含真跑 Python 的注册表 id 锁） |
| decision-association | 35（FIX-A）→ 36（FIX-D）passed | A/D |
| dp2-narrow | 33 passed | FIX-B |
| dp3-answer | 19（FIX-B）→ 20（FIX-D）→ 21（FIX-E）passed | B/D/E |
| decision-signoff | 11 passed | FIX-C（FIX-E 回归复跑仍 11） |
| xkey-gate-guard-coverage | 11（FIX-C）→ 12（FIX-E）passed | C/E |
| triage-dispatch | 21 passed | FIX-D |
| `npx tsgo --noEmit` | rc=0 | A/B/C/D/E 各自最终态 |

## 残留与未验证

1. **本轮未执行任何命令/测试**：本 review 角色会话无命令执行通道（仅 read/grep/find/ls/worker_file）；卡片允许的单文件 `vitest --run` 无法执行。上表全部计数引自 FIX-A..E worker 的 output/worker.log，未独立复跑。修复批次是并行落盘的（A/B/C/D 各自验证自己的终态 + 并行交错期的 tsgo rc=2 记录），**五张卡合并后的最终 union 状态没有一份单次全绿记录**（FIX-E 最后落盘，只复跑了 dp3-answer/xkey-coverage/decision-signoff/tsgo）。建议收尾前在 `packages/coding-agent` 下对上表 8 个套件做一次单遍 `vitest --run` 复核（每文件一条命令，非全量 test.sh）。
2. **MAJOR-2 的跨层锁不完整**：dp1/dp2/dp3 字段清单靠硬编码期望数组 + `REQUIRED_STATE_FIELDS` 源码正则锁，无「真跑 Python dump 字段集」的执行锁（id 集有：`triage-client-state.test.ts:520`）。Python 侧字段集演进不会红测试，只会在运行期退化为子进程拒答（escalated_reason 可见，fail-closed）。
3. **`ask_decision` 对 dp1/dp2/dp3 恒结构化拒答**（零 spawn + missing_fields）：这是 FIX-A 要求 4 的诚实行为（字段在工具入参无来源），非缺陷；但这三 dp 的 LLM 工具通道答案能力未交付，生产答案只走 triage-client / decideDp2Checkpoint / dp3 专用链路。若要工具可答，需另开卡加结构化 state 入参。
4. **doc §3 的 dp1 采纳条件描述不完整**：分歧闸（`triage_type===实派 type`）未写入 §3 正文（`mode=auto 且带 decision_id` 是必要不充分描述）。措辞级，一轮卡可收。
5. **`evidence/sign-final.md` 根落位的防护不对称**：`isDecisionSignoffPath`（write/edit/bash）仍只认 `evidence/review/sign-final.md`，evidence 根落位只在 worker_file 判定函数覆盖。done 门禁只读 review 落位，故无门禁绕过；属纵深防御不对称，可一轮卡对齐。
6. **第一轮 minor 未清项维持原状**（均不属本修复批次范围）：MINOR-2/3/4 已由文档收口；MINOR-7（dp1 关闭态仍 spawn）未加短路；MINOR-8（QG 卡 AC 编号漂移）未回填卡片；MINOR-9（questions_version 镜像无执行锁）未改。3c 零档案行（MINOR-3）在 §7 已声明，功能未变。
7. **FIX-D cp936 事故**：`dp3-answer.test.ts` 曾经编码事故并自修复；本轮 grep 无乱码残留、FIX-E 复跑绿，但无 git 干净基线做独立字节比对（本会话无命令通道）。

## 上下文来源

- 本卡：`.agenticdoc/mw-decision-substitution/tasks/QG-review-2.md`（含 mw-dispatch-card 全文）
- 第一轮报告：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md`（§A/§B 全文精读）
- 修复卡：`tasks/FIX-A-ask-decision-authority.md`、`FIX-B-dp-mirror-convergence.md`、`FIX-C-signoff-worker-file.md`、`FIX-D-dp1-disagree-oversize.md`、`FIX-E-mode-fallback-deeppath.md`
- 修复 worker 报告：`workers/ds-fix-a-ask-authority/output.md`、`ds-fix-b-dp-mirrors/output.md`、`ds-fix-c-signoff-file/output.md`、`ds-fix-d-dp1-disagree/output.md`、`ds-fix-e-mode-deeppath/output.md`
- 并行复审：`evidence/quality-gate-report-20261020c.md`（MAJOR-1/2、MINOR-5）、`quality-gate-report-20261020d.md`（MAJOR-3/4、MINOR-1、AC 矩阵；其两条 NOT-CLOSED 残留即 FIX-E 的来源，本轮已验证 FIX-E 关闭）
- Python 权威：`packages/multi-workers/decision_points.py`（`REQUIRED_STATE_FIELDS:624`、`_parse_row:884-968`、`ESCALATED_REASONS:101`、`_state_builder:278`）、`mw.py`（`_DECIDE_RUN_REASON_MAP:846`、`_decide_run_payload:872`、`_decide_run:903`）
- TS 实现（按点名锚点 + 周边精读）：`agent-team-loop/pm/decision-tool.ts`（整读）、`pm/pm-orchestrator.ts:1946-2360`、`pm/ui-bridge.ts:260-570/1627-1748/2160-2182/2623-2673/2915-2960/3430-3480`、`pm/triage-client.ts:58-560/814-932`、`worker/worker-mode.ts:3696-3800/4440-4560/4570-4977`、`shared/xkey-gate-guard.ts:296-510`、`shared/write-surface.ts`（整读）、`worker/worker-file-tool.ts`（整读）、`index.ts:40-95`
- 测试：`test/suite/decision-tool.test.ts`（整读）、`decision-association.test.ts:219-241/560-750`、`decision-signoff.test.ts`（整读）、`dp2-narrow.test.ts:231-323`、`dp3-answer.test.ts:124-143/456-596/626-680`、`triage-client-state.test.ts:490-575`、`xkey-gate-guard-coverage.test.ts:356-400`
- 门禁：`.agents/skills/agentic-task/scripts/advance_phase.py:88-127`
- 文档：`docs/decision-substitution.md`（整读）、`design.md:179-191`、`packages/coding-agent/CHANGELOG.md:107-112`

## 未覆盖面声明

- 未执行任何测试命令（无命令执行通道）：`vitest --run`、`tsgo`、`pytest`、`npm run check`、全量 `test.sh` 均未运行；所有测试结论引自修复 worker 的运行记录，非本轮独立复跑。
- 不评估真实启用端到端（`.mw/decide.json`/`.mw/decide-points.json`/真实 decisions.jsonl 在本仓均不存在）：AC-003「真实 run + 人工轮次对比」、AC-007「真实样本可查」的启用态验证、真实 LLM 答案质量、凭据链均不在本卡范围。
- 不评估 `mw build --install` 之后的 L5 真派发路径。
- 不评估本仓既有 Windows 环境失败基线（第一轮 T-10 记录的 Python 9 / TS 19 基线）。
- 不重做第一轮 9 条 minor / 3 条 nit 中除 MINOR-1/2/3/4/5/6 之外的关闭判定（MINOR-7/8/9 已在残留里注明维持原状）。
- 不评估同 uid 进程外写者、symlink/文件系统级沙箱（守卫是应用层 hook，非沙箱；`dp apply` 的 env 检测可被 `env -u` 前缀绕过的既有限制未变，bash 层 TABLE_WRITE_CLI_RE 文本级拦截仍独立成层）。
- 未做任何 git 操作；未修改 packages/**、docs/**、.agenticdoc/** 下除本报告外的任何文件。
