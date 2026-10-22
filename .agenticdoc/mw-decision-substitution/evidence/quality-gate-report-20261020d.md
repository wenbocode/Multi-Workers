## 结论
NOT-CLOSED（静态窄复审，运行验收受工具限制）：MAJOR-3 部分修复、未关闭；MAJOR-4 原漏洞修复但存在误伤、未关闭；MINOR-1 核心三态关闭；AC 矩阵按任务指定基线仍为 12 covered / 3 partial / 0 missing，无本轮功能覆盖等级变化。

## 证据

以下行号来自本轮分段读取的当前文件。测试源码说明“断言覆盖什么”，不代表本轮执行通过；历史运行记录单独标注。源码路径均相对仓库根。

### MAJOR-3：未关闭（解析镜像已对齐；dp3 本地授权回退仍在）

**逐分支对照**：权威 `packages/multi-workers/decision_points.py:884-968`，dp2 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:2060-2091`，dp3 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4486-4522`。

| 分支 | Python 实际逻辑 | TS 实际逻辑 / 判定 |
| --- | --- | --- |
| 非对象行 L2 | `:900-914` 直接返回 enabled=false | dp2 `:2081-2082` 的 recordOf 排除 null/数组/标量；dp3 `:4508-4510` 的 asPlainRecord 排除同类 JSON 值。均关，已对齐。JSON 不会产生 undefined 行值，缺行与 null 行已区分。 |
| mode 非 auto/suggest（含非字符串）L3 | `:916-922` force_off | dp2 `:2061`、dp3 `:4487` 两个严格不等检查。坏字符串及非字符串都关，已对齐。 |
| note 非字符串 L3 | `:923-929` force_off | dp2 `:2062`、dp3 `:4488` typeof 检查。关，已对齐。 |
| tier 非字符串 L3 | `:930-934` force_off | dp2 `:2063`、dp3 `:4489` typeof 检查。关，已对齐。 |
| enabled 非布尔 L5 | `:941-950` force_off；布尔 false 直接关 | dp2 `:2064/:2085`、dp3 `:4490/:4513`。关，已对齐。 |
| tier 字符串值越界 L4 | `:936-938` 只加 issue，不设 force_off，注册表 tier 保留 | 两个 TS helper 不检查 tier 字符串的值；如 `{tier:"P9",enabled:true,mode:"auto"}` 保持开。没有过度拦截。 |
| tier 字符串与注册表不一致 L7 | `:939-940` 只加 issue，不设 force_off，注册表 tier 保留 | 同理 `{tier:"P0",enabled:true,mode:"auto"}` 对 P2 的 dp2/dp3 保持开。没有过度拦截；若 enabled=false 或同时存在 L3/L5，则仍因对应分支关，并非因 L7 关。 |
| 字段缺省 / 缺文件 / 坏顶层 | Python 行字段初始化采用注册表默认；L0/L1 采用默认 | dp2 `:2068-2079`、dp3 `:4502-4509` 保留 P2 默认 on/auto（dp3 另需传输门开启）。与 _parse_row 的缺字段默认不冲突。 |

**已修复的 acted 依据**：dp2 预读类型 `pm-orchestrator.ts:2045-2048` 不再携带 mode，`:2275-2276` 只用 enabled 决定是否 spawn；`:2332` 从子进程 payload.mode 严格提取 auto/suggest，缺失或非法时保持 undefined；`:2349` 仅 `mode===auto && action===narrow` 可执行。`:2341-2344` 闭集映射保证 split/direct/escalate/未知动作均不执行（D-011）；`:2610-2623` 进一步要求活任务且 steer 落盘才记消费 trace。

**反面证据（未关闭原因）**：
1. dp3 `worker-mode.ts:4931-4933` 实际为 `payload.mode` 合法则使用，否则回退 `input.policy.mode`。本地 auto + 可用且带引用的答案 + 子进程 mode 缺失/null/非法，仍得到 answer.mode=auto，经 `:3744-3749` 声明 acted=true 并在 `:3775` 注入 steer。它不是纯“是否 spawn”短路，与 dp2 的缺 mode fail-closed 明显不同。
2. 这不是仅由注释推测：`packages/coding-agent/test/suite/dp3-answer.test.ts:125-143` 的 factAnswer() 默认 payload 没有 mode；`:324-343` 用该 payload 驱动真实 workerModeActivate/settle，断言一个 steer 及 `sub=3a acted=true mode=auto`。现有正向用例把本地 mode 回退钉成了期望行为。
3. dp3 本地 3c `worker-mode.ts:4849-4863` 返回 `mode:input.policy.mode`，仍通过同一 `:3744` 执行门；`dp3-answer.test.ts:453-468` 明确断言零 runner 调用但一个 steer / acted=true。因此 readDp3Policy 的 mode 不只用于诊断或“是否 spawn”。FIX-B 已自认该残留（`workers/ds-fix-b-dp-mirrors/output.md:65-69` 附近）；当前 `design.md:187/:189` 的 D-036/D-041 没有零 spawn 本地执行的授权例外正文。不能凭“非权威”注释宣布该点满足单一权威。

**反面测试覆盖**：`dp2-narrow.test.ts:270-290` 钉非对象行零 spawn/原告警，`:304-319` 钉坏 note/tier/enabled/mode 与 P9 不关，`:468-515` 钉本地 auto/子进程 suggest 与子进程无 mode 的不执行；`dp3-answer.test.ts:496-532` 钉坏行/坏 note 与 P9 不关，`:550-564` 钉子进程 suggest 覆盖本地 auto。两套只有 P9 的直接 L4 测试，没有 P0/P1 与注册表不一致的独立 L7 断言；L7 不关的本轮依据是已逐分支读过的源码，而不是测试名中的“L4/L7”。

历史 FIX-B 自报 `dp2-narrow 33 passed / dp3-answer 19 passed / tsgo rc=0`，见 `workers/ds-fix-b-dp-mirrors/worker.log:42-45`；FIX-D 后续自报 dp3-answer 20 passed。均非本轮执行结果，不能反证上述残留。

### MAJOR-4：未关闭（worker_file 原漏洞修复；research 任意证据的放行不成立）

**正面实现**：`packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:373-386` 提供 worker_file 专用固定名 matcher，`:489-499` 读取 event.input.file，命中则 trace + block=true；`:465-487` 保留 write/edit/bash 分支。`packages/coding-agent/src/extensions/agent-team-loop/index.ts:60` 在 PM/worker 分支之前注册守卫。正常证据仍走 `worker/worker-file-tool.ts:96-107/:114-118` 的 evidence 面与写入链，不因扩展名被拒。

**要求四组逐项核对**（本轮为静态路径推演 + 现有 harness 用例核查，未执行工具攻击或测试）：

| 通道 / 输入 | 当前判定 | 证据与反面断言 |
| --- | --- | --- |
| worker_file `evidence/review/sign-final.md` | 拒 | matcher tail=[review]；`decision-signoff.test.ts:305-345` 真 tool_call harness 断言 error、既有人文件字节不变、两次拒绝 trace。 |
| worker_file `evidence/sign-final.md` | 拒 | matcher tail=[]；同用例第二个调用用 `.agenticdoc/k-signoff/evidence/sign-final.md`，断言文件不存在；`:182-187` matcher 另覆盖两种落位与相对/项目基路径。 |
| worker_file `evidence/review/review-notes.md`、其它非固定名文件 | 放行 | matcher `:380-381` basename 不等即 false；`:347-381` harness 断言 review-notes 真落盘、isError=false、零拒绝 trace。 |
| worker_file `evidence/research/notes.md` | 放行 | matcher tail=[research]，false；同 `:347-381` harness 断言 research/notes 真落盘。 |
| worker_file `evidence/research/sign-final.md` | 放行（静态） | basename 命中但 tail=[research]，`:386` 为 false。无直接 harness 用例。 |
| write / edit / bash 指向门禁签收 `evidence/review/sign-final.md` | 仍拒 | write/edit 共用 `:467-475` path 分支；bash `:406-430/:478-485`。`decision-signoff.test.ts:249-281` 用 write(signoff)、write(table)、edit(table) 断言字节不变与三拒；`:384-407` bash(signoff) 与 dp 写 CLI 断言 backend 未执行。edit(signoff) 源码同分支，但现有 harness 并未单独调用该输入。 |

**反面证据（过度拦截）**：`xkey-gate-guard.ts:383` 用 `dir.lastIndexOf("evidence")`，不是认 own-key evidence 根。合法研究产物 **`evidence/research/evidence/sign-final.md`** 的 dir=[evidence,research,evidence]，evidenceIdx=2，tail=[]，`:386` 返回 true；**`evidence/research/evidence/review/sign-final.md`** 同理 tail=[review] 被拒。它们均位于 evidence/research/**，不是人类签收落位。

这两个输入被 worker_file schema 允许：`shared/write-surface.ts:68-72` 接受任意多层合法 segment，evidence/research/evidence/sign-final.md 没有 `.`/`..` 或越界；`:405-406/:439-445` 按 own-key evidence 根解析，`:367-379` 在未被 write_scope 收窄的任务可放行。因此不能归因于通用写面拒绝；误拒根因就是签收 matcher 误把内部同名目录当根。现有 `decision-signoff.test.ts:190-194/:347-381` 只有浅层 notes，未覆盖该反例。任务明确要求 research 下“任意证据”放行，故不予完全关闭。

**既有边界不扩大**：write/edit/bash 的 isDecisionSignoffPath `:353-360` 仍只认 review/sign-final.md 和配置表；`decision-signoff.test.ts:176` 明确把 evidence/sign-final.md 标为 false。done 门禁的真正路径是 `.agents/skills/agentic-task/scripts/advance_phase.py:98-110` 的 review/sign-final.md，所以原三通道防线没有退化；但不声称它们也覆盖新增的 evidence 根落位。守卫为应用层 hook，不是进程沙箱。

历史 FIX-C 自报 decision-signoff 11 passed、xkey 11 passed，见 `workers/ds-fix-c-signoff-file/worker.log:14-15`；`:20-21` 的两条历史 trace 为：

```text
[DECISION_SIGNOFF] 2026-10-20T11:40:44.072Z blocked tool=worker_file target=evidence/review/sign-final.md
[DECISION_SIGNOFF] 2026-10-20T11:40:44.073Z blocked tool=worker_file target=.agenticdoc/k-signoff/evidence/sign-final.md
```

这些是 FIX-C 交付记录中的原文，不是本轮产生的 trace，也不覆盖上述深层 research 误伤。

### MINOR-1：核心关闭（静态；不等同 FIX-D 全卡验收通过）

`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:280-287` 实际要求 available、mode=auto、triage_type 与实派 dispatchedType 严格相等且 decision_id 非空，才返回 `{decisionId,acted:true}`；`:523` 明确传入实派 type。`:2176-2181` 的 mergeDecisionHeader 只对 acted 决策写头行，`:2663` 为共享写点。不是只修注释。

| 三态 | 当前采纳 / 头行 | 反面证据 |
| --- | --- | --- |
| agree + auto | acted=true / 写 decision: | `decision-association.test.ts:667-684` 子进程 acted=false 仍由消费点声明 true，对 task.md 完整字符串及头行顺序断言。 |
| disagree + auto | decision=undefined（未采纳）/ 不写 | `:687-715` advice=coding、实派=research，断言 disagreement=true、decision undefined、result.decision_id 保留，无头行且字节等同关闭基线。 |
| suggest（任意 type） | decision=undefined / 不写 | `:718-749` 断言 suggest 与关闭态 frontmatter 和完整 task.md 全等；源码 `ui-bridge.ts:281` 在比较 type 前返回，因此任意 type 都不执行。 |

关联消费者 `pm-orchestrator.ts:1071-1075` 对无 decision 头行直接跳过 settle，分歧不再被该路径作为“采纳成功”落成 ok 样本。以上足以关闭第一轮 MINOR-1 的采纳误计问题。

**保留的反面证据**：FIX-D 要求的“trace 仍带 decision_id”没有落实成磁盘 trace：`ui-bridge.ts:511-514` stateTrace 只带 state/bytes 或 legacy reason；`:537` 的 ledger 使用 `triage-client.ts:922-932` formatter，只带 triage/dispatched/disagreement/confidence_source，不含 id。新增 disagree 用例只检查内存 TriageResult.decision_id，没有 trace/ledger id 断言。故关闭的是本窄卡三态，不宣布 FIX-D 全卡无残留；这不构成采纳误计复发。

历史 FIX-D 自报 `decision-association 36 passed / dp3-answer 20 passed / triage-dispatch 21 passed / tsgo rc=0`，见 `workers/ds-fix-d-dp1-disagree/worker.log:18-22`。本轮未复跑。

### AC 矩阵复核

**按任务指定基线仍为 12 covered / 3 partial / 0 missing，不变。** 本轮只检查三条发现的关闭，不把补丁与新增 stub/harness 断言当成真实启用/人工轮次对比的证据，也不将原已记录的镜像/关联残留再次计成新的覆盖等级变化。AC-001/009/011/014/015 的证据得到补强但仍有上述授权回退/误伤，AC-003/004 等既有真实运行与作用链欠债未由这些修复补齐。

原报告自身有口径不一致：§A `quality-gate-report-20261020.md:25` 把 AC-007 标 covered，残留 `:148` 又称 AC-007 的真实样本只能 partial；本卡明确给定 12/3/0，本报告沿用该汇总口径，不将这项原文标注差异伪称本轮功能变化，也未重新全量评分。

## 残留与未验证

1. 本会话实际工具只有 read/find/grep/ls/worker_file，无 bash/命令执行通道。**没有运行任何 vitest，没有实际提交签收攻击调用，也没有运行 npm run check/全量 pytest/test.sh/build/git。** 四组签收输入与 dp1 三态只做源码推演及既有相关 describe 核查；不能声称满足本轮“都要试”的动态验收。需有执行通道的 PM 分别运行 `node ../../node_modules/vitest/dist/cli.js --run test/suite/dp2-narrow.test.ts`、`dp3-answer.test.ts`、`decision-signoff.test.ts`、`decision-association.test.ts`（每次单文件、cwd=packages/coding-agent）。
2. MAJOR-3 尚需收口 dp3 子进程 mode 缺失/非法时的本地授权回退，以及 3c 本地执行与 D-036 的关系；本审仅定位不实施，未改任何源码/测试。缺 mode 的现有正向用例应作为回收关注点，而非通过数证明正确性。
3. MAJOR-4 尚需区分 own-key evidence 根与 research 内部同名目录；应验证上述两条深层合法 research 路径。当前浅层 notes 测试不足以证明“research 任意证据放行”。
4. L7 直接单测、edit(signoff) 独立 harness、research/sign-final.md 独立 harness 均未见，本轮依据为明确源码分支。正常 evidence 放行始终受声明 write_scope、合法路径/64KiB 等通用约束，不能理解为绕过这些限制。
5. MINOR-1 的磁盘 decision_id 可见性欠债单独保留；只确认核心三态静态关闭，不把历史 passed 数当本轮运行成功。FIX-D 自报 dp3 测试曾经历编码修复，本审未做历史字节恢复对比，也不重复判 MINOR-5。
6. 无执行工具也无法查询 PI_* 运行环境或执行 AgenticTask detect_root/audit_phase；本轮以提供的绝对任务路径、_index.parallel active 行与 pm-state Snapshot 恢复状态，不变更 phase/index/PM 状态。所有单文件 read 均显式 offset/limit 且每次不超过 200 行；大型源码先 grep 定位后局部读取。

## 上下文来源

- 任务：`.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2d/task.md`；`tasks/QG-review-2D.md`（先写五段骨架、窄范围关闭判定、写入允许面）。
- 目标/状态：`.agenticdoc/goal.md`；`.agenticdoc/_index.parallel` 的 mw-decision-substitution active/EXECUTE 行；本 key `pm-state.md:1-66` Snapshot/证据账本。对齐文件驱动协作、单一授权源与失效安全，不引入新执行路径。
- 基准：本 key `spec.md:224-238`、`design.md:150-191`、`evidence/quality-gate-report-20261020.md:13-33/:55-69/:145-150`；修复卡 `tasks/FIX-B-dp-mirror-convergence.md`、`FIX-C-signoff-worker-file.md`、`FIX-D-dp1-disagree-oversize.md`。
- 当前实现：`packages/multi-workers/decision_points.py:884-968`、`mw.py:872-917`；`packages/coding-agent/src/extensions/agent-team-loop/{pm/pm-orchestrator.ts,pm/ui-bridge.ts,pm/triage-client.ts,worker/worker-mode.ts,worker/worker-file-tool.ts,shared/xkey-gate-guard.ts,shared/write-surface.ts,index.ts}` 的上述局部；canonical `advance_phase.py:98-110`。
- 相关测试段：`packages/coding-agent/test/suite/{dp2-narrow,dp3-answer,decision-signoff,decision-association}.test.ts`，仅相关 describe、fixture/seam 与 payload 构造。
- 历史辅助记录：本 key `workers/ds-fix-{b-dp-mirrors,c-signoff-file,d-dp1-disagree}/{output.md,worker.log,run.json}`。run.json 的 done/exit=0 仅表示 worker 结束，不等于本轮测试结果；worker.log 所读计数是交付摘要，不是独立保存的完整命令 stdout。
- 工作流：agentic-task SKILL / workflow-quality-gate；verification-before-completion；systematic-debugging（只做根因取证，无修复）。

## 未覆盖面声明

- 不评估 MAJOR-1 / MAJOR-2 / MINOR-5（并行卡 ds-qg-review-2c 负责），不以本报告替代 2C 判定。
- 不评估真实启用端到端、真实模型答案质量/凭据/付费请求、mw build --install 后的 L5 派发路径。
- 不评估本仓既有 Windows 环境失败基线；不重做全量 AC 审计或第一轮其余 8 条 minor / 3 条 nit 的关闭判定。
- 不评估同 uid 进程外写者、符号链接/文件系统沙箱、所有 shell 文本绕过；签收审核仅为所列工具 hook 与合法 evidence 路径。
- 本轮只写 `.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020d.md`；未修改 packages/**、docs/**、CHANGELOG、spec/design/pm-state/index 或任何 git 状态。最终回复由框架写 output.md，不额外写 report.md。
