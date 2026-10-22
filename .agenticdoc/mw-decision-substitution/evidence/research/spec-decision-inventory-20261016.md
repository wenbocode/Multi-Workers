# RQ-1 决策点普查：全仓"现在会停下来等人"的位置清单

- key: mw-decision-substitution · 任务卡 `tasks/RQ1-decision-inventory.md`（SPEC 相位 RQ-1）· 2026-10-16
- 方法：代码锚点核对（grep + 逐点读源）+ 既有产物统计（run.json / trace.log / auto-decisions.jsonl / _project_log.md / gates 目录）
- 基线：决策底座已建成——`packages/multi-workers/decision.py`（8 键契约）、`decision_backends.py`（三传输后端）、`mw.py:953`（`cmd_decide`）、`pm/triage-client.ts`；现仅挂 1 点：`pm/ui-bridge.ts:1257` `planDispatchFrontmatter`（派发前分诊，旁路建议不改写）。conductor 的 13 个自动派发点未接入（`mw-jev-provider-integration/docs/jev-integration-flow-and-usage.md` §2.5，覆盖面 2/15）。
- 行号基线：本仓工作区 2026-10-16 快照。

---

## Q1 主表：决策点 / 位置 / 触发条件 / 等人形式 / 可逆性 / 建议等级 / 现有机器输入

等人形式四类：**A=工具返回文本**（agent 读后自行决定，人可被 PM/worker 代替）· **B=触发新 turn**（deliverPmAlert→triggerTurn 唤醒 PM，PM 仍是 agent）· **C=阻塞进程**（TUI 对话框/CLI 等待，人必须在场）· **D=仅提示**（落账本/面板，等人有空看）。

| # | 决策点 | 位置 path:line | 触发条件 | 等人形式 | 可逆性 | 等级 | 现有机器输入 |
|---|--------|----------------|----------|----------|--------|------|--------------|
| 1 | Worker 澄清（needs-clarification 终态） | `worker/worker-mode.ts:2681`（exit 2→status）、`:3619`（writeless 无产物判 NC）、`packages/multi-workers/launcher.py:593`（`_exit_to_status`）、`pm/pm-orchestrator.ts:1498`（PM 回读指令） | worker 主动 exit 2；writeless 角色收敛但无 deliverable evidence（`shared/deliverable-evidence.ts:92` 机器信号正则） | B+D：run.json 终态 + PM 被 triggerTurn 唤醒，PM 读 `## Questions`（`pm/ui-bridge.ts:685`）后**向用户提问**——这是 PM 把人拉进来的第一站 | 可逆（重派） | P2 | Questions 节、run.json、worker.log tail、no-product alarm（`pm-orchestrator.ts:606`） |
| 2 | Checkpoint 发散升级（PM 判断分拆/收窄/直执） | `pm/pm-orchestrator.ts:1658-1690`；锚点 `worker/worker-mode.ts:243-244`（30m 锚+10m 刷新）、`:3348`（`[CHECKPOINT]` 行）、`shared/heartbeat.ts:96`（解析正则） | running 任务 checkpoint risk=mid/high，每任务每会话至多一次（`escalated` 集 `:1584`） | B：唤醒 **PM（agent）**，不直接找人；PM 决定继续/收窄/终止分拆/直执（`:1687` 文案四选一）。PM 无解时才升级为人 | 可逆 | P2 | 机器判据 computeRisk 全量入行（elapsed/reads/writes/phases/repeat_top/landing）；worker 自评行 |
| 3 | PM 告警处置（13 类 DispatchAlarm） | `pm/pm-orchestrator.ts:505-545`（kind 闭集）、`:553`（NOTICE 6 类）、`:574`（describeDispatchAlarm）、`pm/ui-bridge.ts:188-208`（deliverPmAlert=triggerTurn 通道） | 派发扫描拒绝/越界/orphaned-keys/model-error 连击/write-face-refusal 等 | B+D：唤醒 PM（agent）；PM 处置不了才找用户。本人实测账本（`.agenticdoc/_autopilot/auto-decisions.jsonl` 11 行）里 5 次 no-product、3 次 orphan-repair-skipped 均无人值守恢复 | 可逆 | P2 | 五元组 ledger 行（`pm-orchestrator.ts:645` recordDispatchAlarm） |
| 4 | Autopilot 人工门（6 类 gate：stage-confirm/stage-close/stalled/budget-exhausted/goal-change/xkey-authorize） | `packages/multi-workers/autopilot/gates.py:82-89`（GATE_KINDS）、`:110-183`（40 字段 frontmatter）；创建点 `autopilot/conductor.py:1082,1148,1326,1713,4655,4794,5142,6418`；应答 `mw.py:4595-4603`（`autopilot answer`）；reject 二次确认 `mw.py:7151,7168`；提醒 `pm/pm-orchestrator.ts:1813` | conductor 判定 stage 待确认/停滞/预算耗尽/goal 变更/跨 key 授权 | **C（人不在=流水线停）**：gate 文件 pending + 门提醒唤醒 PM，但应答只有 `/autopilot gate <id> approve|reject`（人在环）；`status-model.ts:1576-1596` BLOCKED_ON_HUMAN 真值表明示"人未应答即阻塞"；`conductor.py:4469` 明文"NEVER closes the stage … the human answers" | 半可逆 | **P0** | gate frontmatter 40 字段：evidence {path,sha256,mtime_ns}、goal_sha256、dossier、blocker_class、default_action、expires_at（48h）——**输入面最全的一个点** |
| 5 | 相位门禁失败 | `.agents/skills/agentic-task/core/scripts/advance_phase.py:191`（check_gate，四类规则 file_min_bytes/dir_has_files/content_match/spec_goal_alignment） | advance 时产物缺失/过小/模式不匹配 | A：脚本非零退出 + failures 列表回显，agent（PM 或 worker）读后自行修复重跑——**已经是机器可判、无需人** | 可逆 | P2 | 规则即代码（GATES 表），失败原因结构化 |
| 6 | 派发参数选择（type/risk/model/role/timeout） | `pm/ui-bridge.ts:1257`（planDispatchFrontmatter，DP-1 唯一挂点）、`pm/triage-client.ts:55-57`（两题 choice）、`:169`（spawnSync）；模型选择：`pm/pm-orchestrator.ts:1498` 重派预算规则、`_project_log.md:18`（覆盖 role 默认值必须带 model_reason） | 每次 dispatch_worker / /worker | A+B：DP-1 现为旁路建议（回执 `ui-bridge.ts:279` + 争议才唤醒 `pm-orchestrator.ts:619`），派发决策本体仍是 PM 自主；timeout 预算重派规则已写入 PM 回读指令（`:1498`） | 可逆 | P2 | state+题面、confidence（自报）、回执、ledger disagreement 行 |
| 7 | 模型降级选择 | `packages/multi-workers/launcher.py:424-512`（fallback chain：exit 3 → 按 `dispatch.yml fallback_models` 换下一个重派）；`worker/worker-mode.ts:2590`（PI_WORKER_TRIED_MODELS） | worker 以 model-unavailable 退出 | **无等人**：launcher 自动换模型（已委派）。连击 2 次才产生 model-error 告警（`pm-orchestrator.ts:769`），仍是 perception only（`:527` 注释） | 可逆 | （Q5 先例） | `[MODEL]` trace 行、tried 链、dispatch.yml 配置 |
| 8 | 破坏性操作确认 | `mw.py:7151,7168`（gate reject 需 `--confirm-destructive`）；pi core：`core/extensions/types.ts:139`（ui.confirm）、headless 恒 false `core/extensions/runner.ts:237`；杀进程树 `worker/worker-mode.ts:2725` 附近 killTrackedDetachedChildren | gate reject、模型卸载等 | C：CLI 必须显式携带标志（人不敲命令就不发生）；headless 下 UI confirm 一律 fail-closed（false） | 半可逆 | P0 | argv 标志（机器可判，但语义是"人亲手确认"） |
| 9 | 用户 override 冲突 | `AGENTS.md:166`（§User Override）；rebase 冲突他方文件 `AGENTS.md:70` | 用户指令与项目规则冲突；rebase 冲突不在自己文件 | A→C：PM 停下向用户求 explicit confirmation；无结构化协议，靠对话 | 半可逆 | P1 | 冲突文件清单、git status 可机器读 |
| 10 | 提交/发布时机 | `AGENTS.md:40`（Never commit unless the user asks）、`:130`（release 第 1 步必须问用户是否跑过 `/cl`）、`:49`（lockfile 提交需 PI_ALLOW_LOCKFILE_CHANGE=1）、`:155-156`（release 命令人手执行） | 每次 commit / release | C+A：commit 需人开口；release 全流程人手驱动（smoke test 步骤 `AGENTS.md` §Releasing 2 也要人跑 tmux 交互验证） | 半可逆 | **P0**（发布）/P1（日常 commit） | git status/diff、check 结果可机器读；`/cl` 是否跑过无机器信号 |
| 11 | 变更范围（扩/删功能、移除表面功能代码） | `AGENTS.md:25`（Always ask before removing functionality）、`:27`（Never remove or downgrade code to fix type errors）、`:28`（models.generated.ts 禁改） | 删代码、降级实现、改生成物 | A→C：PM 问用户 | 半可逆 | P1 | git diff 可机器读 |
| 12 | 依赖升级与安全评审 | `AGENTS.md:44-47`（dep 变更=reviewed code、undici 必须 读 changelog、lifecycle 脚本需 allowlist）、`packages/coding-agent/scripts/generate-coding-agent-shrinkwrap.mjs`（新 dep allowlist） | dep 元数据变化、新增依赖 | C：评审+允许都要人（隐性 changelog 阅读判断无机器输入） | 半可逆 | P1 | package-lock diff、npm metadata（min_release_age 门）可机器读 |
| 13 | 测试失败归类（环境噪声 vs 回归） | `AGENTS.md:35`（Windows 基线 89 失败=13+76，已分类存档，agent 自行对比） | 套件出现失败 | A：agent 对照基线数字自判，无需人——**规则已半自动化**（基线是文本常量，非机器可读清单） | 可逆 | P2 | AGENTS.md 基线数字、per-test 输出 |
| 14 | 凭据/权限/服务配置 | `decision_backends.py:137`（凭据三级解析链）、`pm/ui-bridge.ts:1280`（"mw is not running…ask the user to start it"）、goal.md GC-4（worker 凭据隔离）；doctor 待人工项 `mw.py:6944`（`— 待人工 —`，`[auto]` 项可 `--apply`） | 服务未启、凭据缺失、update-env 非自动项 | C：人启动服务/配 key；doctor 把修复项二分为 `[auto]`（可自动）与待人工——**已是二分委派设计** | 可逆 | P1 | credential_status() 布尔、doctor 报告结构化 |
| 15 | QG（质量门）结论处置 | `.agents/skills/agentic-task/core/workflows/quality-gate.md:172`（全量质检：⚠️ 项"经用户确认接受"）、`:173`（紧急合入：用户显式接受所有未通过项，报告标注 override） | QG 报 ⚠️/❌ 或紧急合入 | C：人拍板接受/返工；`_project_log.md:13`（"质检 PASS（用户确认接入…）"）、`:14`（"质检两轮 FAIL 4 BLOCKER→处置→复核"）为实证 | 半可逆 | P1 | quality-gate-report-*.md（结论结构化，处置在人） |
| 16 | goal.md 确立与目标确认 | `.agents/skills/agentic-task/core/workflows/goal.md:39`（draft→active 需用户确认）、`:60`（目标复述让用户确认/纠正）；机器判据 `advance_phase.py:170`（`_goal_established`） | 项目起步、goal 变更 | C：人确认目标（goal-change gate 是其运行时形态，见 #4） | 半可逆 | P0 | goal_sha256/diff（gate 字段） |
| 17 | spec/需求确认锁定 | `requirements.md:380`（Step 5 用户确认后 AC 锁定）、`:34`（claim 冲突等待用户确认）、`pm-mind.md:429-430`（mini-spec 展示用户确认） | 新 key 立项、trivial-fix 快速路径 | C：人确认需求与 AC；claim 冲突是人裁决 | 可逆 | P1 | spec.md AC 编号结构化 |
| 18 | Key 抢占与 claim 冲突 | `pm/ui-bridge.ts:415-435`（"ask the user before stealing a live claim"；held-conductor 可无 force 接管、活人窗口需 --force） | 目标 key 被其他窗口/worker 持有 | A→C：工具返回拒绝文本并点名 holder，人决定 --force | 半可逆 | P1 | claim 状态五态（claimState）、holder 身份 |
| 19 | write-scope 越面写入（人工预授权逃生舱） | `worker/worker-mode.ts:2986-2994`（`allowForeignWrite===true && rule!=="deny"` 放行+审计，缺省 fail-closed）；写面闸门 `pm/pm-orchestrator.ts:538`（write-face-refusal） | 任务要写声明范围外的外部目标 | A：缺预授权=直接拒绝（无人在场时 worker 停）；授权本身是人给的（task.md 头） | 半可逆（写发生前） | P0 | write_face 载体、审计行 blocked= 、deny 红线清单 |
| 20 | Roadmap 阶段闭环 | `packages/multi-workers/autopilot/roadmap.py:12`（closed-human 状态）、`conductor.py:1330`（stage-close gate：approve=closed 并开下一 stage；reject=halt 等待人工）、`autopilot/status-model.ts:424`（TS 镜像） | stage 全部任务终态 | C：closed-human 字面即"人关的"；gate 未答=halt | 半可逆 | P0 | closure dossier 五判据（`_project_log.md:45` 自动收证） |
| 21 | project-refine 升级 | `core/workflows/project-refine.md:64`（"不自动升级，仅以 report 建议，升级须人工确认后手动执行"） | refinement 报告建议升级 | C：人手动执行 | 可逆 | P2 | report 结构化建议 |
| 22 | debug 方案确认 | `core/workflows/debug.md:113`（引导用户确认） | 根因确认后、修复前 | C：人确认方案 | 可逆 | P2 | 根因证据链 |
| 23 | project-memory 快照 | `core/pm-mind.md:225`（仅用户确认 Y 才执行 /project-memory snapshot） | 快照时机 | C：人敲 Y | 可逆 | P2 | diff 可机器读 |
| 24 | pi core 用户交互入口（Q4 专项） | `core/project-trust.ts:33`（信任选择 ui.select，启动期阻塞）、`core/extensions/types.ts:139-141`（confirm/input/select 对话框 API）、headless no-op `core/extensions/runner.ts:236-238` | 新项目含 .pi 资源、扩展调 UI | C：TUI 阻塞；headless 一律静默默认（confirm=false/input=undefined/select=undefined）= **fail-closed** | 半可逆 | P0 | 信任结果持久化 trust-store |

**Q1 覆盖核对**：任务卡列的 14 个必查点全部入表——worker 澄清(#1)、checkpoint 升级(#2)、PM 告警(#3)、相位门禁(#5)、QG 结论(#15)、派发参数(#6)、破坏性确认(#8/#24)、override(#9)、提交/发布(#10)、变更范围(#11)、依赖安全(#12)、测试归类(#13)、模型降级(#7，已自动)、凭据权限(#14)。另有 10 个自查新增：#4/#18/#19/#20/#16/#17/#21/#22/#23 + doctor 待人工项（并入 #14）。

---

## Q2 频率与成本

**既有产物实测（本仓 `.agenticdoc/`，2026-10-16 扫描，命令输出均 ≤30 行）：**

| 数据源 | 规模 | 反推的频率信号 |
|---|---|---|
| `run.json` 全仓 | 242 个 | **status=needs-clarification 42 个（17.4%）**——每 6 次 worker 运行约 1 次以"要人澄清"终态，是最高频的等人终点 |
| `trace.log` 全仓 | 533 个文件 | `[CHECKPOINT]` 行 142 条，其中 **risk=mid 36 条 + risk=high 24 条（60 条，42%）**——每条 mid/high 理论触发一次 PM 唤醒（`escalated` 去重后每任务至多 1 次） |
| `.agenticdoc/_autopilot/auto-decisions.jsonl` | 11 行 | dispatch-alarm：no-product×5、orphan-repair-skipped×3、orphaned-keys×1、model-error×1、out-of-scope×1——全部无人值守自愈（orphaned-keys 自动 claim-free 修复）或转 PM 处置 |
| `.agenticdoc/_autopilot/gates/` | **不存在（0 个 gate 文件）** | 6 类人工门在本仓历史零触发——gate 频率目前为 0，但每触发一次阻塞的是整条 stage 流水线（阻塞成本最高） |
| `triage-decisions.jsonl` | 不存在 | DP-1 在本仓从未启用（decide.json 缺失=全旁路），决策埋点频率 0 |
| `_project_log.md` | 50 行项目史 | 人出现的实证：`_project_log.md:13`（用户确认接入）、`:14`（质检 FAIL→人处置→复核 PASS）、行18/36/45/48 的质检/QG 结论均为人拍板后落账 |
| `pm-state.md` Process Log | `.agenticdoc/agent-team-loop/pm-state.md:89` 起 | PM 会话快照由人确认写入（`ui-bridge.ts:1216` 要求 PM "写完简短确认"）——半人工通道 |

**结论**：
1. **可零埋点统计的**：needs-clarification 频率（run.json 计数，done）、checkpoint mid/high 频率（trace.log 正则 `shared/heartbeat.ts:96`）、dispatch-alarm 频率（auto-decisions.jsonl 按 kind 分组）——三者已够支撑优先级排序。
2. **无埋点不可统计的**：`/cl` 是否跑过（AGENTS.md:130 无落盘）、QG override 接受（报告文件有结论但无统一 schema 索引）、pi core 信任确认（trust-store 有持久化但未按项目聚合导出）。
3. **成本维度**：单次等人墙钟成本最高的是 #4/#20 gate（整 stage 停摆，`conductor.py:4758` 默认 48h deadline）；频次最高的是 #1 needs-clarification（42/242）与 #2 checkpoint 升级（60 次 mid/high 信号）；单次成本最低的是 #5 相位门禁（机器自判）。

---

## Q3 分类（a 可逆性 / b 风险 / c 机器输入 / d 人不在的后果）

| # | 决策点 | a 可逆性 | b 风险档 | c 现有机器输入充分度 | d 人不在会怎样 |
|---|--------|----------|----------|----------------------|----------------|
| 1 | needs-clarification | 可逆 | P2 | 充分（Questions+产物证据） | PM 重派或自行补做；流水线不停 |
| 2 | checkpoint 升级 | 可逆 | P2 | 充分（7 字段机器判据） | PM 按文案四选一；无 PM 在场则 worker 继续（10m 刷新+看门狗兜底） |
| 3 | PM 告警 | 可逆 | P2 | 充分（ledger 五元组） | 孤儿 key 自动修复、其余留账不阻塞 |
| 4 | 人工门 approve/reject | 半可逆 | **P0** | **最充分**（40 字段含 evidence sha256/default_action/expires_at） | stage halt（`conductor.py:1330`）；有 default_action+48h 字段但按 `conductor.py:4469` 语义默认仍等人 |
| 5 | 相位门禁 | 可逆 | P2 | 充分（规则即代码） | agent 循环修复，不停 |
| 6 | 派发参数 | 可逆 | P2 | 中（DP-1 旁路建议+自报 confidence，`jev` 文档 §2.2 硬规则：非 api 置信不得进门控） | PM 按默认 role/model 派发 |
| 7 | 模型降级 | 可逆 | （已委派） | 充分（tried 链+配置） | 自动换模型，无感 |
| 8 | 破坏性确认 | 半可逆 | **P0** | 充分（标志位显式） | 操作不发生（fail-closed） |
| 9 | override 冲突 | 半可逆 | P1 | 弱（规则全文在 prompt，无结构化冲突单） | agent 停；无 PM 停摆 |
| 10 | 提交/发布 | 半可逆 | **P0（发布）/P1（commit）** | 中（git 状态可读；/cl 状态不可读） | 不提交/不发布（fail-closed），迭代停摆 |
| 11 | 删功能 | 半可逆 | P1 | 弱 | agent 不删（保守绕行） |
| 12 | 依赖升级 | 半可逆 | P1 | 中（lockfile diff） | agent 不升级，可能带病用旧版 |
| 13 | 测试归类 | 可逆 | P2 | 中（基线为文本常量） | agent 对比基线自判 |
| 14 | 凭据/服务 | 可逆 | P1 | 中（doctor 二分 [auto]/人工） | 服务不启，派发全挂 |
| 15 | QG 结论 | 半可逆 | P1 | 中（报告结构化，override 无 schema） | 合入被挡 |
| 16 | goal 确立 | 半可逆 | **P0** | 中（goal_sha256/diff 字段齐） | goal 停 draft，全部 gate 拒绝放行 |
| 17 | spec 锁定 | 可逆 | P1 | 中（AC 编号） | key 不立项 |
| 18 | key 抢占 | 半可逆 | P1 | 充分（holder 身份+五态） | 跨 key 只读，无破坏 |
| 19 | 越面写预授权 | 半可逆 | **P0** | 充分（write_face 载体+审计行） | 拒绝写入（fail-closed），任务失败可重派 |
| 20 | stage 闭环 | 半可逆 | **P0** | 充分（dossier 五判据自动收证） | halt，流水线停 |
| 21-23 | refine/debug/snapshot | 可逆 | P2 | 弱-中 | 建议留档，不阻塞 |
| 24 | pi core 交互 | 半可逆 | **P0** | 充分（trust-store 持久化） | headless 默认拒绝（fail-closed） |

---

## Q4 漏项排查（grep ask/confirm/clarify/approve/permission/waiting 等）

**grep 方法与命中**：对 `packages/coding-agent/src`、`packages/multi-workers`、`.agents/skills/agentic-task` 扫 `ask the user|ask user|向用户|问用户|等用户|等待人工|等待用户|awaiting human|human answer|confirm|clarif|approve|permission|请确认|需要用户|待人工`，命中点全部核对源码后归入 Q1 表；Q1 表之外的实质性新增即 #16-#24（goal 确立、spec 锁定、key 抢占、越面写预授权、stage 闭环、refine/debug/snapshot、doctor 待人工项、pi core 交互入口）。

**pi core（`packages/coding-agent/src/core/**`）用户交互入口的核实结论**：
1. **无逐工具调用确认门**：core 无 toolCallConfirm/needsConfirm/权限弹窗（grep 零命中）；工具面由 session 级 allow/denylist 静态控制（`core/agent-session.ts:213-215`、`core/sdk.ts:55-70`），worker 的工具白名单即此机制（goal.md 约束）。
2. **三个阻塞入口**：项目信任选择 `core/project-trust.ts:33`（ui.select）；扩展 UI 对话框 API `core/extensions/types.ts:139-141`（confirm/input/select）；llama 扩展的模型管理确认（`extensions/llama/index.ts:129`，与本框架无关）。
3. **headless 语义**：print/rpc 模式下 UI 上下文为 noOp——`core/extensions/runner.ts:236-238`（select→undefined、confirm→false、input→undefined）。**这是全仓最重要的一条 Q4 事实：任何试图把"等人"做成 UI 对话框的方案在 worker（headless）里都会静默 fail-closed，决策替换必须走文件/CLI 通道（正如 gate 文件协议所做的那样）。**
4. **无 ask 类工具**：core/tools 目录（bash/edit/find/grep/ls/read/write）无询问工具；worker 的"提问"只能通过 needs-clarification 终态（#1）或 progress.md 自评行表达。

---

## Q5 已委派的先例（机器判断替代人判断，含阈值与失败回退）

| 先例 | 位置 | 阈值/判据 | 失败回退设计 | 对决策替换的价值 |
|---|---|---|---|---|
| **auto_gate_mode（off/shadow/live）**：机器自动应答 gate 的事实平面 | `conductor.py:6520-6580`（注释块+AUTO_GATE_MODES） | `rule_falsifiable` 机器检查：命题主体=gate 自身触发条件即同义反复→拒自动转人工（case 3）；stage-confirm/stage-close 的 fact plane 只作 GUARD，**永不自动放行**（`:6542-6547`）；goal-change/xkey-authorize 永不自动（`:6549`） | off=逐字节旧行为；shadow 先记 `gate-auto-decision` 事件不落效，人工复核后再 live；`gate-auto-revoke` 可撤销（`:6527` 事件集） | **最直接可复制**：决策替换应套用"事实平面可自动、政策平面永不自动 + shadow 先行 + 可撤销事件"三件套 |
| stage-close 五判据自动收证放行 | `_project_log.md:45`（"stage-close 五判据自动收证放行（不可构造绕过，回落点名缺失项）"）；谓词码 `conductor.py:6571-6577`（stage-close-stage-unknown/not-terminal/in-flight/reconciliation/dossier-missing/credentials-missing——每条单独拒因） | 五判据全绿才放行；任何一谓词缺失=永不 pass（"missing record => never a pass"） | 回落=点名缺失项转人工 | 证明"收证自动化、判定半自动"能把 stage-close 的人工墙钟压到只剩一次 approve |
| 看门狗自动判挂死（idle/wall） | `worker/output-writer.ts:647-648`（idle=无 token/工具/turn 活动判真挂死；wall=任务墙钟）；证据行 `worker/worker-mode.ts:2434-2463`（IdleKillEvidence 结构 + `[IDLE_KILL]` 落 trace） | idle 阈值（PI_WORKER_IDLE_MS）+ 墙钟（task.md timeout 头 > env > 默认 60m）；`last_model_error` 字段把"静默+上次模型报错"判为模型嫌疑而非一般挂死 | **"no evidence -> no kill"**（`worker-mode.ts:2461` 注释）：证据行写失败则不杀，wall 看门狗仍是外边界兜底 | 阈值+证据行+回退三层结构可直接移植到"PM 自动处置 no-product"类决策 |
| 模型 fallback 链 | `launcher.py:424-512`（exit 3→按 dispatch.yml 换下一个；consumed fallback 计数从 trace.log 恢复） | 明确的失败码（exit 3）驱动；链耗尽后 exit 3 仍 reaped as failed（旧行为） | 连击 2 次→model-error 告警仅 perception（`pm-orchestrator.ts:527`），不改派发 | "明确失败码→有限次自动重试→仅感知不上报"的分层 |
| 孤儿 key claim-free 自动修复 | `conductor.py` scan（`pm/pm-orchestrator.ts:525` kind=orphaned-keys："claim-free repair dispatch applied"）；修复被跳过时单独 kind=orphan-repair-skipped（T-24/C-30：修复外来 idle key=跨 key 污染） | 无 live claim 且无 live run 才修；有陈旧 owner 证据则**宁可跳过** | 跳过留痕（one neutral notice per key per session） | 保守边界先例：机器只做"零破坏可逆"的自动，其余留痕转人 |
| doctor update-env `[auto]`/待人工二分 | `mw.py:6934-6946`（`[auto]` 标记项可 `--apply` 批量自动执行；非 auto 列入 `— 待人工 —`） | 修复动作注册时即标注 auto 与否 | 只读默认，`--apply` 显式开启 | 低风险修复类决策的现成二分框架 |
| headless UI fail-closed | `core/extensions/runner.ts:236-238` | UI 不可达即默认拒绝 | 无静默放行 | 全部"确认类"决策的底线语义 |
| 写面守卫 deny 红线 + 逃生舱 | `worker/worker-mode.ts:2986-2994` | 硬 deny 清单（其他 key/.git/**/pm-state.md/_workers*）**永不放宽**；外部目标可由 task.md `allowForeignWrite` 预授权 | 缺授权=fail-closed 拒绝+审计行 | "红线不可自动、白名单可预声明"的分层授权模式 |

---

## 替换优先级建议（按"省人墙钟最多且风险最低"排序）

1. **needs-clarification 的机器预消化（#1，P2，42/242≈17% 频率）**：42 次 NC 里相当部分是"writeless 无产物/问题可自答"类。用 jev 对 Questions+产物证据做一次预判：能自答的转自动 steer（复用 checkpoint steer 的 sendUserMessage 通道 `worker-mode.ts:3440` 附近），不能自答的把问题结构化后只在 PM 摘要里保留。风险最低（NC 本就可逆、重派成本低），省的是"PM 整理问题→人回答→重派"整段墙钟。
2. **gate 输入面完备化 + auto_gate_mode shadow 常开（#4/#20，P0 但输入最全）**：gate 频率虽为 0，但单次阻塞整条 stage（最高单次墙钟成本）。`conductor.py:6520` 的 auto 框架已建成，把 shadow 模式设为默认（仍不落效），积累"机器会怎么答 vs 人怎么答"的一致率数据，一致率达标后再对 stalled/budget-exhausted 两类开 live——这两类恰恰是纯事实判断（停滞计数、预算余量），政策面（stage-confirm/goal-change/xkey）保持人工。
3. **checkpoint 升级的 PM 自治（#2，P2，60 次 mid/high 信号）**：升级文案已是"PM 四选一"（`pm-orchestrator.ts:1687`），补一步：low 价值任务（research 卡、无写面）由 PM 按 computeRisk+自评行直接选"收窄并 deadline steer"，只有写面任务或第二次升级才考虑终止重派——完全在 agent 层闭环，零人参与，风险与现状相同。
4. **DP-1 从旁路升为弱输入（#6，P2）**：现在建议 100% 不改写；改为仅当 `confidence_source=api`（`jev` 文档 §2.2 硬规则允许）且与 PM 判断一致时省掉回执呈现、不一致时仍告警——先降信息噪声，再谈 binding。
5. **发布/提交的机器准备度信号（#10，P0 不动决策权）**：`/cl` 是否跑过、check 是否全绿、基线外新失败计数——做成一条机器可读的 release-readiness 摘要，人只做最后一次 yes/no；决策权留给人的前提下把"收集信息等回答"的墙钟压掉。
6. **QG ⚠️ 接受的结构化 override（#15，P1）**：把"用户确认接受 ⚠️"从对话改为 quality-gate 报告内的 override 字段（复用 gate 文件 decision 行协议 `mw_common.py:3473-3488`），人不在时报告保持 ❌ 挡合入（fail-closed 语义不变）。

**不建议替换（P0 红线）**：goal 变更/goal-change gate（#16）、xkey-authorize（#4 子类）、stage-confirm/stage-close 最终 approve（#20，五判据只收证）、破坏性 --confirm-destructive（#8）、越面写预授权（#19 红线部分）、依赖安全评审签字（#12）——与 `conductor.py:6542-6549` 的政策面永不自动原则一致。

---

## 残留与未验证

- 行号为 2026-10-16 工作区快照；`pm/pm-orchestrator.ts` 等高频文件后续提交可能使行号漂移，引用时以符号名（GATE_KINDS/markOutcome/deliverPmAlert）复核。
- #2 的"60 条 mid/high → 实际唤醒次数"未精确统计：`escalated` 集按任务去重（`pm-orchestrator.ts:1584`），唤醒数≤60，无现成落盘计数（PM 会话内未留 wake 记录）。
- gate 频率为 0 仅指本仓：`.agenticdoc/_autopilot/gates/` 不存在；其他项目（goal-autopilot 运行过的仓）的 gate 历史未扫描，频率结论不可外推。
- `_project_log.md` 的"用户确认"事件是叙事行非结构化埋点，#15/#10 的人工介入频率为定性推断。
- QG override 的历史次数未统计（quality-gate-report-*.md 散在 key 目录，无统一索引）。
- jev 决策服务本身在本仓零调用（triage-decisions.jsonl 不存在）；其建议质量（一致率）无本地数据，优先级建议 4 的收益为假设。

## 上下文来源

- 任务卡：`.agenticdoc/mw-decision-substitution/tasks/RQ1-decision-inventory.md`
- 目标：`.agenticdoc/goal.md`（jev 决策模型重定义、Key Constraints、GC-4 凭据隔离）
- 决策底座现状：`.agenticdoc/mw-jev-provider-integration/docs/jev-integration-flow-and-usage.md`（8 键契约、confidence 硬规则、覆盖面 2/15、gate 接入约束）
- 规则：`AGENTS.md`（行 25/28/35/40/44-49/70/130/155-156/166）
- 代码：`packages/multi-workers/{decision.py,decision_backends.py,mw.py,launcher.py,mw_common.py,autopilot/gates.py,autopilot/conductor.py,autopilot/roadmap.py}`、`packages/coding-agent/src/extensions/agent-team-loop/{pm/pm-orchestrator.ts,pm/ui-bridge.ts,pm/triage-client.ts,worker/worker-mode.ts,worker/output-writer.ts,shared/heartbeat.ts,shared/deliverable-evidence.ts,autopilot/status-model.ts}`、`packages/coding-agent/src/core/{project-trust.ts,extensions/runner.ts,extensions/types.ts,agent-session.ts}`
- 流程：`.agents/skills/agentic-task/core/scripts/advance_phase.py`、`core/workflows/{goal,requirements,quality-gate,debug,project-refine}.md`、`core/pm-mind.md`
- 产物统计：`.agenticdoc/*/run.json`（242）、`.agenticdoc/*/trace.log`（533）、`.agenticdoc/_autopilot/{auto-decisions.jsonl,timeline.jsonl}`、`.agenticdoc/_project_log.md`、`.agenticdoc/agent-team-loop/pm-state.md`
