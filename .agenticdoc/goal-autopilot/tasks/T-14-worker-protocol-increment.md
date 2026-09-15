# Task T-14: worker/TS 协议增量（origin 跳过 / fail-closed / [START] / agenticdocRoot 修复）

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t14-protocol
- ac_refs: [AC-021]
- vc_refs: [VC-023]
- pattern_refs: []

## 描述
改 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` + `worker/worker-mode.ts`（D-104 / D-107 / D-115 / D-116）。

**① dispatchNewTasks origin 跳过**（D-104，pm-orchestrator.ts）：
- `dispatchNewTasks` 逐行读 task.md（pickWorkerRoute 已按行解析）→ 识别 `origin: conductor` 行 → 跳过该任务（不入队、不 upsert）
- 手动/旧任务无标记 → 行为不变（AC-012 零回归）；launcher 重启后内存去重丢失场景下 TS 重插 pending 路径对 conductor 任务同样关闭

**② TOOL_ALLOWLISTS 显式条目**（D-107，worker-mode.ts）：
- 增 5 类型条目：`roadmap-writer`（read/write/edit/find/grep/ls）、`phase-writer`（coding 全集）、`verifier`（review 级 read/find/grep/ls）、`reviewer`（review 级）、`repair`（coding 全集）
- 与 Python 侧注册表 per-type 精确相等（T-17 奇偶测试锁定）
- verifier 任务强制 read_scope 存在性校验（缺失 → fail 同未知 type 路径）
- **手动路径 fallback 全集行为保留不变**（GC-8 明文：fallback 仅限手动模式）

**③ origin fail-closed**（D-107）：
- worker 收到 `origin: conductor` 且 type 未注册（TOOL_ALLOWLISTS 无条目）→ **fail-closed exit 1**，output.md 写明原因
- 封闭 stale bundle / 非 conductor 队列路径让未注册 type 落入 fallback 全集的窗口

**④ [START] pid 行**（D-115）：
- worker-mode 启动时（首 agent turn 前）向 trace.log 追加 `[START] pid=<pid>` 纯代码行，每次 spawn 恰一条
- trace.log 追加不重置（区别于 launcher 每 spawn 截断的 worker.log）

**⑤ agenticdocRoot 语义拆分**（D-116，存量 bug 修复）：
- 事实：`parseTaskMd` 现算 `agenticdocRoot = dirname(dirname(taskPath))` = `.agenticdoc/{key}/workers`——对 outputDir 是正确契约，但 goalMtime(root) stat `{key}/workers/goal.md` 恒 miss → [GOAL_CHECK] 记 0
- 修复：拆分语义——输出路径继续用现行 root（outputDir 契约不变），goalMtime/appendGoalCheck 改收真 agenticdoc 根（task.md 向上 4 级）
- 修复后 [GOAL_CHECK] 记录真实 goal.md mtime（goal 约束第 7 条显式继承）

## 输入
- 依赖文件: `pm/pm-orchestrator.ts`（dispatchNewTasks，约 L324/L581）、`worker/worker-mode.ts`（parseTaskMd / TOOL_ALLOWLISTS / trace 追加点）
- 依赖 Task: T-06（frontmatter 协议）、T-13（同文件，先合入避免冲突）
- AC 约束:
  > AC-021: 在 autopilot 派发路径上，roadmap-writer（含 write，需写 `_roadmap.md` 提案）/ L2 verifier（review 级：read/find/grep/ls）/ L3 review（review 级）/ repair（coding 级）各类型均有显式工具白名单条目；对未注册 type 的派发请求，conductor 拒绝派发（行数 0）并记录时间线，不回退全量工具集
- 设计约束:
  > D-104: 竞态按构造消除；D-107: 双保险；D-115: 进程级观测；D-116: 语义拆分（不改 outputDir 契约）

## 预期产出
- `pm/pm-orchestrator.ts` 改 + `worker/worker-mode.ts` 改
- `packages/coding-agent/test/suite/autopilot-protocol.test.ts`（vitest，测试名含 VC 编号）：
  - dispatchNewTasks 跳过 origin: conductor 任务；无标记任务照常入队（VC-023 相关 + AC-012 零回归）
  - 5 类型 allowlist 查表正确；verifier 缺 read_scope → fail
  - origin=conductor + 未注册 type → exit 1 + output.md 原因（VC-023 worker 侧）
  - 手动路径未知 type 仍 fallback 全集（GC-8 保留）
  - [START] 每 spawn 恰一条、追加不重置
  - goalMtime 用真根（fixture 验证 [GOAL_CHECK] 非 0）；outputDir 路径不变
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1（奇偶全量在 T-17）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 12:57 | 实现①D-104（pm-orchestrator.ts）：ORIGIN_LINE_RE（`^origin:[ \t]*(\S+)[ \t\r]*$/m`，行精确、CRLF 容忍）+ isConductorTask；dispatchNewTasks 在 undispatched 收集阶段跳过 origin: conductor 任务——不入队、不 upsert、不计入 docs gate 待派发工作（纯 conductor 任务的 undoc key 不烧 gate 警告）；launcher 重启/行归档后的重插 pending 路径同批关闭（taskKey 不在队列即重扫也不插入） | 代码完成 |
| 1 | 2026-09-10 12:57 | 实现②D-107（worker-mode.ts）：TOOL_ALLOWLISTS 增 5 类型显式条目，与 dispatch.py REGISTRY 逐类型、逐序精确相等（roadmap-writer=read/write/edit/find/grep/ls；phase-writer/repair=coding 全集；verifier/reviewer=review 级）；isRegisteredType 排除内部 fallback 桶（type: fallback + origin: conductor 同样 fail-closed）；手动路径（无 origin 标记）未知 type 仍 fallback 全集（GC-8 保留，含 T-13 手动 verifier 无 read_scope 零拦截契约不变） | 代码完成 |
| 1 | 2026-09-10 12:57 | 实现③D-107 fail-closed：dispatchRefusal 在首 agent turn 前（[START] pid 行之后）拒绝——origin: conductor 且 type 无 TOOL_ALLOWLISTS 条目 → appendError + writeOutput（原因写入 output.md Exit Reason）+ worker.log 状态行 + exit 1；conductor verifier 缺 read_scope（缺失或空列表，对齐 dispatch.py 拒绝空 scope）→ 同路径拒绝；封死 stale bundle/非 conductor 队列路径落入 fallback 全集的窗口 | 代码完成 |
| 1 | 2026-09-10 12:57 | 实现④D-115：appendStartPidLine 在每次 workerModeActivate（每 spawn 恰一次）向 trace.log 追加纯代码行 `[START] pid=<process.pid>`（appendFileSync 追加不重置）；格式与 Python state.py start_pids 的 `^\[START\] pid=(\d+)\s*$` 逐字匹配；与 appendStart 的时间戳 [START] 运行时锚并存（后者不匹配 pid 正则，heartbeat.ts START_LINE_RE 亦不受影响）；拒绝路径同样先记 pid（观测单位是进程本身） | 代码完成 |
| 1 | 2026-09-10 12:57 | 实现⑤D-116：TaskMeta 增 trueAgenticdocRoot（task.md 向上 4 级 = dirname(dirname(agenticdocRoot))，_scratch 布局同归 .agenticdoc）；agenticdocRoot 字段与 outputDir 契约不变；appendGoalCheck 第 4 参改收 goalMtime(trueAgenticdocRoot)——修复后 [GOAL_CHECK] 记真实 goal.md mtime（旧路径 stat {owner}/workers/goal.md 恒 miss 记 0） | 代码完成 |
| 1 | 2026-09-10 12:57 | 验证：test/suite/autopilot-protocol.test.ts 定向 vitest 10/10 绿（VC-023 名义覆盖：origin 跳过 LF+CRLF/无标记照常入队含 route+model 不变/队列擦除重扫 conductor 仍零行/纯 conductor undoc key 零 gate；5 类型查表与 Python REGISTRY 序相等；origin=conductor+未注册 type 与 type: fallback 均 exit 1+output.md 原因；conductor verifier 缺/空 read_scope 拒绝；GC-8 手动未知 type fallback 全集+手动 verifier 照常跑；[START] pid 每 spawn 恰一条追加不重置（预置行存活，pid 可解析）；D-116 真根 [GOAL_CHECK] 非 0 且等于 goal.md mtimeMs + outputDir/progress 落任务目录）；既有 autopilot-read-scope.test.ts + agent-team-loop.test.ts 109/109 绿（无回归）；npm run check：biome 零错误零警告零 info、pinned-deps/ts-imports/shrinkwrap/install-lock/browser-smoke 全过，tsgo 26 错全为 packages/ai 存量噪音（与 T-13 记录一致，非本任务引入，未修） | 验证通过 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | lint | packages/coding-agent/test/suite/autopilot-protocol.test.ts:121 | lint/style/useTemplate: Template literals are preferred over string concatenation（CRLF fixture 的 join()+"\r\n" 拼接） | 已修（改用 conductorTaskMd().replaceAll("\n", "\r\n") 派生 CRLF 变体） |
| E2 | tsgo | packages/ai/*（src/providers/cloudflare-ai-gateway.ts + 12 个 test 文件，共 26 处） | error TS2353/TS2345/TS2741/TS2322/TS2367/TS2339/TS2352/TS1294 等（如 '"openai-completions"' does not exist in type Partial<Record<...>>） | 存量噪音，非本任务引入，未修（任务书明示如实报告；tsgo 失败致 && 链停在 browser-smoke 前，browser-smoke 单独跑通过） |

### PM 验收备注（2026-09-10 15:35）
亲跡三套件 119/119（protocol 10 + read-scope 19 + agent-team-loop 90）；代码走查：TOOL_ALLOWLISTS 5 条目与 dispatch.py REGISTRY 逐类型逐序精确相等（T-17 锁定前提成立）；isConductorTask 读失败返回 false 走原有读错误路径；dispatchRefusal 双拒条件（未注册 type 含 fallback / verifier 缺 scope）+手动豁免 GC-8 保留；[START] pid 行与 state.py start_pids 正则逐字匹配且 append-only；trueAgenticdocRoot 不动 outputDir 契约；git status 仅 5 个预期文件。验收通过。
