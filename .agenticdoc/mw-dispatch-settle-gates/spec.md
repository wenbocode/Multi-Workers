# spec — mw-dispatch-settle-gates

- key: `mw-dispatch-settle-gates`
- 依赖：`mw-gate-verdict-hardening`（done，质量门经两次独立复审更正为 22 PASS + 3 ⚠️ PARTIAL）
- 直接动因：两份独立复审报告（`mw-gate-verdict-hardening/evidence/quality-gate-report-review-a-evidence-chain-20261010.md`、`…-review-b-code-adversarial-20261010.md`）确认的 3 个 AC 部分实现 + 1 个 AC 边界 + 本 key 自身执行期暴露的 worker 产物契约缺陷（R22）
- 一句话目标：**让每一道门的判据都由机械事实决定** —— 派发期（可满足性、跨 key、产物终态）、结算期（产物是否真的存在）、观测/提醒期（doctor 面、stage 终态）都不再依赖散文、默认值或人的记忆。

## §0 Goal Alignment

- **对齐**：`goal.md` 的项目目标是"PM 管理多 Worker 并行开发，靠文件驱动的去中心化协调，Worker 进程级隔离"。并行度越高，**判据失准的代价越大**：本 key 修的每一处都是"判据没写全"或"判据写了没人实现"，直接导致 PM 侧要靠人肉兜底（回读不可信、队列被整体重写、报告失准）。
- **GC 继承**：沿用 `mw-gate-verdict-hardening` 的 GC-5（队列完整性）/GC-6（派发隔离与运行身份）的判据风格——**fail-closed、机器可读、带反向用例**；本 key 是它们在四个未闭合点上的收口。
- **冲突**：无。本 key 不引入调度中心、不改 pi 核心、不动 `packages/*` 之外的东西；`mw-gate-verdict-hardening` 已 done，本 key 只新增/收紧判据，不重跑任何已终态 task_key（AC-022）。
- **预期收益**（可判定方式）：① `mw doctor` 能在无面板场景回答"哪个门挂了多久"（AC-001，判据=doctor 输出含 `blocked_on_human` 机器字段与条件后缀）；② 已关闭 stage 的未答门不再产生提醒噪声（AC-002，判据=ledger 零新增行）；③ 无 write 工具的角色拿不到"必须写到别处"的任务书（AC-005，判据=派发期拒绝 + 反向用例放行）；④ 只读角色"跑完了但什么都没产出"不再被记成 `done`（AC-006，判据=该 run 记 `needs-clarification` + 告警）；⑤ `output.md` 的产物/努力度信息不再为空段或常量（AC-007；G-g 更正：`## Changed Files` 段体恒空、实测 0/30 出现 `(none)`）。⑥ 带 shell 的调研角色不能再写仓库任意位置（AC-005b，判据=越界写被 block + trace 审计行）。预计减少 PM 侧每轮约 1 次"人工取证 + 手工补写"。

## 1. 背景与证据（每条缺口都有坐标）

| # | 缺口 | 性质 | 坐标（已由复审给出，PM 已独立复现） |
|---|---|---|---|
| G-a | **AC-008 只交付面板半边**：`mw doctor` 的 G2 可见面（`blocked_on_human` 字段 + `_gates_text_alerted` 触发 + `format_doctor_text` 条件后缀）**从未进任何卡** | 功能缺口（掉单） | design `:147`/`:386`/`:432` 要求；`rg 'blocked_on_human\|BLOCKED_ON_HUMAN' packages/multi-workers/mw_common.py` = **0 命中**（`monitor.ts` 侧 10 命中）；plan 把 `mw_common.py` 只分给 T-11/T-18 |
| G-b | **AC-007 缺 stage 终态判据**：人工关闭 stage 后未答门仍会提醒 | 功能缺口 | `gates.pending_gates`（`gates.py:770-772`）只按 `status=="pending"` 过滤整个 gates 目录；`_remind_pending_gates`（`conductor.py:2555`，`:2564` 取数）无 stage 范围；`pending_gate_reminders`（`conductor.py:2522`，条件在 `:2533-2551`）三条件无 stage 终态；RQ-1 复核：终态族常量 `conductor.py:565`（`_STAGE_TERMINAL_RANK = 2`，dict `:557-564`）|
| G-c | **AC-024 有未守卫的同类写面 + 文案与实现不符**：`/worker --key <他人 live key>` 可写 | 功能缺口 | 守卫仅 2 个调用点（`ui-bridge.ts:1333`/`:1698`）；`/worker`（`:1710`，注册 `pm-orchestrator.ts:1059`）经 `:66-67` 直通，写 `:1813-1819`；拒绝文案 `:241-242` 自称 `/worker` 已拒 |
| G-d | **AC-022 边界（D-038）**：Python 派发判据不读产物终态 | 边界 | `autopilot/dispatch.py:621-633` 仅写行；`rg 'run\.json' dispatch.py` = 0 命中 |
| G-e | **R22：派发期不做可满足性校验** → 只读角色收到"写到自身目录之外"的任务书时空转（54s / 8 次调用 / 零产物，仍记 `done`） | 契约缺口 | `worker-file-tool.ts::WORKER_FILE_NAME_RE`（basename 白名单，fail-closed）+ `worker-mode.ts:114-117`（只读角色仅追加 `worker_file`）；实例 `mw-gate-verdict-hardening/workers/mwg-qg-review-20261010/`（RQ-2 独立核对：唯一真空转，`output.md` 1,962 B、零机器行、零引用产物）（R23 亦并入：`research` 的 bash 写面收窄见 AC-005b） |
| G-f | **结算期无产物判据**：只读 run 零产物仍 `done`；`hasProductEvidence()` 语义是"这个目录跑过"（含 `trace.log` / 启动即写的 `run.json`）而非"这次跑出了产物" | 契约缺口 | `pm-orchestrator.ts:487-492`（纯 `existsSync`，注释 `:485-486` 自陈语义=已跑过，唯一调用 `:653`）；`launcher.py:367-373` `_exit_to_status` + `:842-844` reap **只看退出码**；RQ-2 实测：语料 30 目录 `run.json` = **0/30**（运行身份未上线）|
| G-g | **`output.md` 信息量**：`## Changed Files` 段体**恒为空**、`## Exit Reason` 恒为常量（8 次调用与 127 次调用同一句） | 可观测性缺陷 | `changedFiles` 全扩展唯一赋值点 `worker-mode.ts:1359` = `[]` ⇒ `output-writer.ts:65-66` 的 `?? "(none)"` **不可达**（实测 0/30 目录出现 `(none)`，段体为空）；`worker-mode.ts:1361` 常量退出语；`output-writer.ts:95` = 空则覆写/非空则追加；`run.json.artifacts` 唯一赋值 `worker-mode.ts:800`，收集器 `run-store.ts:119-138` **只收任务目录产物、不含源码改动**（worker 无 git/diff 工具）|
| G-h | **文档一致性**：spec AC-021 措辞与反向用例冲突；spec §2.3 与 AC-025⑤ 字面冲突；plan §2.5 值域（1..50 应 1..64）；design §0 `ac_count: 24` 陈旧、§8 映射表止于 AC-018；`evidence-requirement.md`/`evidence/baseline/` 缺失；T-18/19/20 卡头 VC 少报；pm-state D-028 "1406" vs T-18 卡 "1407" | 文档 | QG-A §4 行动项 4/6/7/10、§6.1、§6.3 |
| — | **调研留底（本 key）** | 证据 | `evidence/research/spec-stage-terminality-20261010.md`（RQ-1：stage 终态锚 10 候选穷举 + 调用面 7 处 + 反例 9 条）、`evidence/research/spec-worker-product-contract-20261010.md`（RQ-2：30 目录产物语料 + 28 条回归面）；下列 AC 的判据数字均以其实测为准 |

## 2. 范围 / 非范围

**范围**：G-a…G-h 的收口；每条附非空洞对照与反向用例。

**非范围**：
- **R21 运行时切换**（`mw build --install` + 重启 launcher/9 个窗口）——需用户单独批准，runbook 已就绪。
- **R18**（spawn 竞态下"刚派发的行不得被静默判终态"）——待用户决定是否并入；本 spec 预留 AC 位但不默认纳入。
- **R23 → 已并入本 key**（用户 2026-10-10 批准）：`research` 的 bash 写面收窄 = **AC-005b**（P1 档，已知写模式拦截 + `write_scope` 机器头 + 拒绝清单 + trace 审计）。**P2（OS 级隔离）**不在本 key 范围。
- 任何 `packages/*` 之外的重构；任何 pi 核心改动。

## 3. 验收标准（AC）

> 格式：口径 + 反向用例（反向用例必须可执行、且是"不得误伤"的那一侧）。

| AC | 口径 |
|---|---|
| AC-001 | **doctor 的 G2 可见面**：`mw doctor --json` 的 gates 段含 `blocked_on_human` 机器字段（三轴口径与面板**同轴**：pending 门 > 0 ∧ 非终态行 = 0 ∧ conductor 在 tick） [PM 勘误 2026-10-11]：轴 3 与面板**并非逐字同源** —— 面板遇 `timeline` 缺失按 null 语义（`monitor.ts:704/829`），doctor 侧按「不新鲜」处理（`mw_common.py:3117-3120`，对告警更严、避免假告警），此为有意收窄，已在 T-08 报告登记。，且 `mw doctor` 文本在非零时追加 `BLOCKED_ON_HUMAN` 后缀；**无状态判据**（不新增快照文件、doctor 仍零写盘）。反向用例：门已答、或存在非终态 worker 行、或 conductor 未 tick ⇒ 字段为 false 且文本无后缀。 |
| AC-002 | **已终态 stage 的门不提醒**：终态来源 = **roadmap stage status 终态族**（`_STAGE_TERMINAL_RANK`，`conductor.py:565`；rank 2 = `{closed, closed-human, halted}`，dict `:557-564`，唯一写者 `_set_stage_status` `:605-639` 带单调守卫）：两级解析 `gate.stage` 优先，否则 `roadmap.stage_of_key(gate.key)`（`roadmap.py:477-483`）；**解析不到 / roadmap 缺失 ⇒ 不抑制（fail-open，D-015）**。落点 = `pending_gate_reminders` 纯判据第 4 条件（`conductor.py:2522-2560`），**不放** `gates.pending_gates`（展示/doctor 面须继续显示历史未答门）。反向用例：stage 已终态但门未答 ⇒ 零 ledger 行、零 `gate-reminder`；stage 活动 + 门 pending ⇒ 照旧提醒；roadmap 缺失（现有 12 条 reminder 测试 fixture 均无 `_roadmap.md`）⇒ 行为逐字不变。**`halted` 口径**取 conductor 侧（不提醒），需在 design 显式记 D（面板 `status-model.ts:1393-1399` 口径不同）。 |
| AC-003 | **跨 key 写面闭合**：`/worker`（含显式 `--key`）对他人 live 持有的 key 必须在**任何副作用之前**拒绝，返回固定码 `[cross-key-read-only]` + 正确下一步（`switch_key`）；**拒绝文案与实际守卫集合一致**（防"文案写了但没实现"：design 需给出可测试的单一声明源）。**落点（DRQ-1）**：`ui-bridge.ts:1813`（`workerTaskDir`）**之前**插入守卫，与 `dispatch_worker`（`:1333`）共用同一判定函数；`:1411` 与 `:1816` 的就地写 task.md 应抽成单点 `writeDispatchTaskMd`。反向用例：自有 claim、未认领 key、`_scratch` 一律放行；读面（`list_tasks`/`mw_status`/doctor/面板）不受影响。 |
| AC-004 | **Python 派发读产物终态**：`autopilot/dispatch.py` 的派发/重派判据**首先**读 `run.json` 终态（与 TS 路径同优先级：终态 ⇒ 不派；`running` ⇒ 不派；未知/不存在 ⇒ 零回填放行）。反向用例：无 `run.json` 的历史任务行为与今日逐字一致。 |
| AC-005（= a 半）| **派发期可满足性校验（R22a）**：保护对象 = **无 write/edit 且无 bash** 的角色（判据源自 `activeToolsForType` 单一真相源 `worker-mode.ts:115-118`；TS 侧 4 类 = `review`/`verifier`/`reviewer`/`rag-research`，Python 侧见 `dispatch.py:71` `REGISTRY`）。任务书若要求写到**自身目录之外**（写意图动词 + 路径）、且该路径不是自身目录/`worker_file` 白名单 basename ⇒ 派发期 **fail-closed 拒绝** + 告警，错误文本给出正确写法（`worker_file file="report.md"`）；无论描述是否提写面，都在 `task.md` 头部**注入写面契约段**（成对 marker，幂等）；逃生阀 `allow_foreign_write`（默认关，打开须落 task.md frontmatter 供审计）。判定必须含 **5 类护栏**（否定 / 读标记 / 代码主体 / 引语复述 / PM 归因）+ 路径须在写动词后 <=32 字符。**角色门收窄依据**（PM 量测，替换初版的 97 份口径）：`research` 有 `bash`（`worker-mode.ts:66`）⇒ 不在保护范围；收窄后语料 24 份真实只读任务书上，收紧规则命中 2 份（1 真阳性 = 空转事故卡 `mwg-qg-review-20261010`，1 份写自身 `output.md` 走白名单）⇒ **0 假阳性**；朴素正则假阳性 88%。反向用例：读取 `evidence/runs/` 作为输入不得拒；编码角色不受判据影响；否定/引语复述不得拒。 |
| AC-005b | **bash 写面收窄（原残留 R23；本 key 内实现，档位 P1，用户 2026-10-10 批准）**：对"有 `bash` 但无 `write`/`edit`"的角色（当前仅 `research`），在 `tool_call` 上拦 bash 的**已知写模式**并做路径判据 —— **允许写** = 自身 taskDir（`.agenticdoc/<key>/workers/<taskKey>/`）+ `.agenticdoc/<key>/evidence/**`；**拒绝** = `.agenticdoc/<key>/pm-state.md`、`.agenticdoc/<key>/workers/_workers*`、`.agenticdoc/_index.parallel`、其他 key 的目录、`packages/**`、`.git/**`；拒绝 = `{ block: true }` + `[TOOL_ERR]` + 一条审计行（`trace.log`）。机器头 `write_scope:` 与既有 `read_scope:` 同渲染器、同语法；任务书无论是否提写面都注入写面契约段。有 `write`/`edit` 的角色完全不受影响。**P1 的诚实边界**：只拦已知写模式（重定向 `>`/`>>`、`tee`、`cp`/`mv`/`rm`/`mkdir`/`touch`、`sed -i`、`git checkout|apply|clean`、`curl -o`、PowerShell `Set-Content`/`Out-File`/`New-Item`/`Remove-Item`、`python`/`node` 一行脚本字面量），精心构造的写仍可能漏放（失败模式 = **漏放而非误拦**）；全量 bash 命令入 `trace.log` 供 PM 抽查。**P2（OS 级隔离）明确不在本 key 范围**。反向用例：读类命令（`rg`/`python` 只读脚本/`git status`）不得拦；写自身 taskDir 或 `<key>/evidence/**` 不得拦；写 `pm-state.md`/其他 key ⇒ 必须拦；`coding` 角色零影响。 |
| AC-006 | **结算期产物判据（R22b）**：只读角色（判据同 AC-005/AC-005b）的 run 结束时按**分级通道**判"是否交付"（细则 §3.1），全不命中 ⇒ `needs-clarification` + `dispatch-alarm(kind="no-product")`，**不得静默 `done`**；占位符不计为产物；必须接受 reply/`output.md` 通道。**实现约束（DRQ-2）**：① 判定落点 = `worker-mode.ts::finishSuccess()`（`:1350`）内、`writeOutputGuarded`（`:1354`）之前，折进 `exitCode`（delivered ? 0 : 2），配套 `markOutcome`（`:786`）加 `2 → needs-clarification`、`recordEnd`（`:1075`）放宽 `0|1|2`；② **权责**：队列行终态由 launcher reap 写（`launcher.py:838-844`）⇒ launcher 改 **product-first**（先读 run 状态，退出码仅 fallback），Python 不判产物内容，PM 永不写终态行；③ **`hasProductEvidence()` 必须并存而非被替换**（它是 IN-3 守卫：`pm-orchestrator.ts:487-492`，唯一调用 `:653`）——收窄它会把它从"拒绝扫描"翻成"重跑历史"，须补判别性测试；④ alarm 必须用 `meta.trueAgenticdocRoot`。 |
| AC-007 | **产物信息量**：`## Changed Files` 段体不得为空或误导 —— `run.json.artifacts` **不含源码改动**（`run-store.ts:119-138`），故：**有 artifacts** ⇒ 改名 `## Deliverables` 并排除 `output.md`/`progress.md` 后填充；**无 artifacts**（当前全语料 0/30）⇒ **整段省略**，不得留空段；`## Exit Reason` 必须携带努力度（`toolCallCount` + `writes=<report.md|progress.md|none>`）。**回归面按 DRQ-2 §5 的 28 行重锚表执行**：必须同步改 #4、#10/#11、#19；**#23 必须保持绿**（不得靠放宽断言通过）。 |
| AC-008 | **文档勘误（不改码、不改已冻语义）**：spec AC-021 措辞与反向用例对齐；spec §2.3 与 AC-025⑤ 对齐；plan §2.5 值域改 1..64；design §0 `ac_count` 与 §8 映射表补到 AC-025；补 `evidence-requirement.md`（或显式登记偏离）；T-18/19/20 卡头 VC 补齐；pm-state "1406/1407" 取真值。 |
| AC-009 | **证据标准（本 key 的直接动因）**：每条 AC 的 `[VERIFY]` 数值必须来自实测并带 `文件:行号` 或测试名；**报告中的引用必须对最终工作区重锚**（防"报告写做、锚点漂移"：本 key 的 RQ-1 报告即有 2 处 ±1 漂移、1 处路径写错，已在收录件里更正）；每条机器判据附非空洞对照（摘除/反转 ⇒ 用例转红）。反向用例：故意摘除任一判据 ⇒ 至少一条具名用例转红。 |
| AC-010 | **回读面不遮蔽真报告**：`output.md` 可含多段同名 section（实测 10 目录 >1 段 `## TL;DR`，最多 9 段；主因 = **跨 run 追加**，语料 `blocks == starts`），而 `readOutputSection` 是首匹配（`ui-bridge.ts:339/344`）⇒ 首块占位符遮蔽真报告（实测 3 个目录含占位符）。**实现约束（DRQ-2）**：① 读侧**不改** `readOutputSection`/`readOutputSummary`（首匹配契约被测试钉住），新增 `shared/output-sections.ts` 的 `readOutputSections`/`isPlaceholderSection`/`readLastProductSection`，只把 `readTerminalDetail` 的 4 处读点（`ui-bridge.ts:457/460/464/470`）切到"末个非占位块"；② 写侧幂等守卫加在 `finishSuccess`/`agent_settled` 入口（`if (taskDone) return;`）；③ 占位符全集 15 个按 section 归位（见 `evidence/research/design-settle-read-20261010.md`）。反向用例：首块占位 + 末块真报告 ⇒ 读侧给真报告；单块文件行为不变；`/mw` 命令面零影响。 |


### 3.1 AC-006 谓词细则（RQ-2 实测校准；语料 = `mw-gate-verdict-hardening/workers/` 30 个目录）

**语料事实**（PM 独立复现）：30 目录；有 `report.md` 24（2,517–57,337 B）；无 `report.md` 6；其中 **4 个合规**（`mgh-rq1-l3-abort` 7,604 B 内联 `[VERIFY]`×4、`mgh-rq2-gate-alert` 6,455 B 内联 `[VERIFY]`×4、`mgh-rq4-monitor-freeze` 7,078 B 引实存 `evidence/**`、`mwg-t03-event-names` 1 次机器行）；**1 个真空转**（`mwg-qg-review-20261010`，1,962 B / 零机器行 / 零引用产物）；**1 个硬杀**（`mwg-t08b-g2-surfaces`，无 `output.md`）。行首机器行（`^[VERIFY]`/`^VERDICT=`/`^TASKS=`）全语料仅 **1 次** ⇒ spec 初版"机器行"单通道等于空集。

**参数化谓词**（`isReadOnly(type)` 时；判定表见 `evidence/research/spec-worker-product-contract-20261010.md`）：

1. 自身目录内 `report.md` / `report-<slug>.md` **非空** ⇒ delivered；
2. 否则 `output.md` 非空且**存在至少一个非占位块**（占位块 = `(worker exited without writing output)` 一类空交付桩；**不要求所有块都非占位** —— 首块常为桩块而真报告在后，见 §3.2 与 D-022 现场证据。[REVISED @ 2026-10-11：原写「全部块均非占位符」，与本节 28/2 语料数字自相矛盾（`mgh-rq2-gate-alert` 首块占位、末块真报告 ⇒ 会翻成 27/3）；由 T-04 实测校准，PM 裁定采纳]），且满足任一：(a) 机器行（**行首或内联**）`[VERIFY]`/`VERDICT=`/`TASKS=`；(b) `run.json.artifacts` 含 `output.md` 以外的产物（**仅运行身份上线后可用**，语料 0/30，不得作唯一通道）；(c) 正文引用的 `evidence/**.md` 相对路径**实存**；
3. 否则 ⇒ `needs-clarification` + `dispatch-alarm`。

**通道分级理由**：初版只认 ①②(a) 会把 3/4 历史合规 run 判异常（75% 假阳性）——正是上一 key 的复发形态；把 (c) 纳入后语料 = **28 delivered / 2 正确 NC / 0 假阳性**（2 = 真空转 + 硬杀）。

### 3.2 AC-010 依据（RQ-2 副发现，PM 复现）

多段成因：`output-writer.ts:95`（空则覆写、非空则 `---` 追加，D-117 有意设计，用于保护 worker 自写的机器行）+ `worker-mode.ts:1392`/`:1423` 无同进程二次 settle 幂等守卫；读侧 `ui-bridge.ts:344` 首匹配 ⇒ T-11 的 9 段、T-16 的 3 段都出现过"占位块在前、真报告在后"。修 AC-010 时不废除 D-117（追加语义保留），只补"读侧取末个非占位块"+"写侧幂等"。

## 4. 待裁决策（PM 提议默认值，用户可否决）

| # | 决策 | 我的提议 |
|---|---|---|
| D1 | AC-008（本 key 的 G-a）：落地 `mw doctor` 面 **还是** 正式 descope 并改 AC 文字 | **落地**（AC 字面含"与 `mw doctor`"，descope 需改已冻 AC，成本更高） |
| D2 | AC-024（G-c）：扩守卫到 `/worker` **还是** 只改文案 | **扩守卫**（同族隔离不变式；文案已承诺） |
| D3 | AC-006 的第三态：`needs-clarification` **还是** `lost` | **`needs-clarification`**（"跑完没产物"需要人判断，不是进程丢失）+ `dispatch-alarm` |
| D4 | AC-007 的 `changedFiles`：填充 **还是** 删段 | **填充（有 `run.json.artifacts` 时）+ 无则省略**（worker 无 git，只有自报权威） |
| D5 | R18 是否并入本 key | 不并入（保持本 key 单一主题"判据机械化"），单独立卡待你决定 |
| D6 | AC-006 谓词：初版（仅 `report.md` + 行首机器行）vs RQ-2 校准版（三级通道） | **校准版**——初版在真实语料上 75% 假阳性；证据 `evidence/research/spec-worker-product-contract-20261010.md` |
| D7 | AC-010（多段/首匹配遮蔽）是否纳入本 key | **纳入**——与 AC-006 同族（产物可读性），且实测已两次致误（T-11 九段、T-16 三段） |
| D8 | AC-005 角色门：初版（无 write/edit，含 `research`）vs 收窄（无 write/edit/bash） | **收窄**——`research` 有 `bash` 能自己写，保护它是假保护；收窄后语料 0 假阳性（24 份 review 任务书，1 真阳性 = 事故卡） |
| D9 | `hasProductEvidence` 收窄 vs 并存 | **并存**——收窄会削弱 IN-3 守卫（"拒绝扫描"翻成"重跑历史"），须补判别性测试，不改语义 |
| D10 | 队列行终态权责 | **launcher product-first**（先读 ``run.json`` 状态，退出码仅 fallback）；worker 只写 `run.json` 终态 + `pending` 行；PM 永不写终态行 |
| D11 | 读侧改 `readOutputSection` 本体 vs 新增模块 | **新增 `shared/output-sections.ts`**，只切 `readTerminalDetail` 的 4 处读点 |
| D12 | R23（bash 写面）：单开 key / 并入本 key；档位 P1 vs P2；允许写目录 | **并入本 key，P1**；允许写 = 自身 taskDir + `<key>/evidence/**`；拒 `pm-state.md`/`_workers*`/`_index.parallel`/其他 key/`packages/**`/`.git/**`（用户 2026-10-10 批准） |

## 5. 调研计划（spec/design 阶段默认并行；每个 RQ 只写唯一的 evidence 文件）

- **RQ-1**（research）：`evidence/research/spec-stage-terminality-20261010.md` —— "stage 终态"在本项目的机器可读锚到底是什么？（roadmap/closure 模型、`[END]`/`[DONE]` 用法、`advance` 的 phase 记录、`_stall_family`/conductor 现有判定），给出候选锚 + 每种锚的反例风险（AC-002 的判据来源）。
- **RQ-2**（research）：`evidence/research/spec-worker-product-contract-20261010.md` —— 只读角色的交付通道实况（同 key 27 个已结束 worker 的 `report.md`/`output.md` 统计、5 个无 `report.md` 的合规先例）、`hasProductEvidence()` 在 dispatch vs settle 两种语义下的差异、`run.json` 字段（`artifacts`）可承载哪些"产物事实"（AC-006/AC-007 的判据来源）。

（G-c/G-d/G-g 的坐标已由两份复审给出并经 PM 复现，不再重复调研。）

## 6. 需规避坑点

- **不得把"缺失"当作"失败"**：本 key 的判据都是 fail-closed，但 `mw-gate-verdict-hardening` 的教训是"缺失 ⇒ 放行"（D-015 修订）——凡"无记录/无 sidecar/无 run.json"一律走零回填放行，只有"有记录且冲突"才拒绝。
- **不得用 `trace.log`/启动即写的 `run.json` 当产物证据**（G-f）。
- **不得引入第二真相源**：角色能力判据必须复用 `activeToolsForType`，两侧镜像（Python `dispatch.py` REGISTRY ↔ TS allowlist）必须保持既有 parity 测试可锁。
- **同文件串行**：`ui-bridge.ts`（AC-003 + AC-005）、`worker-mode.ts`/`output-writer.ts`（AC-006 + AC-007）、`conductor.py`（AC-002）、`mw_common.py`（AC-001）、`dispatch.py`（AC-004）——同一文件同一时刻只允许一个 worker。
- **报告必须先落骨架**：本文档的两份复审报告均为"第一次 write 骨架 + 逐节 append"，中途 settle 也不至于空交付。

## 7. 可复用资产

- `mw-gate-verdict-hardening` 的 25 AC / 47 VC 判据体系、`evidence/runs/verify-g5g6-tests.md`（47 行 VC→用例映射）、6 份 `*-controls.ps1` 非空洞对照脚本、`pm-g3-live-check.py`（真活端到端）、`t23-normalize-whole-queue.py`（锁下一次性队列归一化）、`t23-queue-inspect.py`（队列只读检视）。
- 两份独立复审报告（可复用的"对抗清单"与"证据链核查"问题集）。
- `worker-file-tool.ts` 的 basename 白名单与 fail-closed 形态（AC-005 的判据直接复用其声明源）。
- `hasProductEvidence()`（语义需修正后复用，见 G-f）。
