# D5 设计调研 — decision 关联 + settle 映射 + phase 报告 + 签收 + done 门禁 + dp apply 护栏

任务卡：`tasks/D5-association-report-signoff.md`（key: mw-decision-substitution，worker: ds-d5-association-report-signoff）。
全部结论来自对当前工作树源码的逐行核对；行号以 2026-10-19 工作树为准（任务卡个别锚点有漂移，见各节标注）。未执行任何源码/配置修改，无 git 操作。

## 结论

- **Q1**：`decision:` 行注入唯一正确位置是 `writeDispatchTaskMd`（dispatch_worker 工具与 /worker 命令的唯一落盘点）的 frontmatter merge 链末端，格式 `decision: dp1:<task_key>`（单行、列 0、key-shaped）。TS 侧三个头部读者（`task-frontmatter.ts` 的参数化 scalar 读取、`readTaskType`、`run-store.ts parseSupersedes`）与 Python 镜像（`mw_common.read_task_header_scalar`）全部按键名前缀匹配，未知键被忽略、纯函数永不 throw——证明过程见 Q1。
- **Q2**：settle 唯一追加点 = PM 终态回收循环 `pm/pm-orchestrator.ts:1691-1745` 内、`recordWriteScopeResidualRisks`（:1719）与 `recordModelErrorTerminal`（:1724）旁边；该点是全系统唯一"每 task 每会话恰好消费一次终态迁移"且同时握有 `entry.status` 与 `taskDir` 的位置。6 种终态映射的判定依据：`entry.status` + `run.json.exit` + `model_exhausted`/`## Exit Reason`（exit 0 时契约段齐已被 worker 侧结算判定折叠进退出码，PM 不做第二 oracle）。`needs-clarification` 不落 settle 行（保持 pending，转人）；`lost` 落 `outcome=pending, note=lost` 显式标记行。幂等：**允许多条 settle（最后一条生效）**，因 `ok→rollback`（supersedes 重派）是合法先后序列；写入侧按 `(decision_id, outcome, run_id)` 去重防 PM 重启重放。
- **Q3**：报告全部节数据来自 `decisions.jsonl` 按 `decision_id` 的 fold 视图（唯一例外："无法关联项"来自显式登记行）。生成时机挂在 `advance_phase.py` 推进成功之后（门禁通过 + pm-state 更新完成），判据 = `prev_phase`（推进前读到的 `- Phase:` 行）已推进且 `evidence/review/decision-review-<prev_phase>-*.md` glob 为空。写入白名单：`<key>/evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md`（Python 脚本写，非 agent 写面）。`N<5` → 强制写"数据不足，不结论"。`suggest:` 行格式 `^suggest: (enable|disable) <dp-id>(, <dp-id>)*(, N=<n> override=<n>)?$`。
- **Q4**：`sign-*.md` 头部四行机器字段（`conclusion:` 必填 / `promote:` / `demote:` / `p0-open:`）+ 正文。`dp apply` **先全量校验再单临界区原子写**（沿用 `_decide_write_config` 的 tmp+os.replace+lock 协议），绝不逐条写；缺 `conclusion:`、拼错 dp id、P0 漏列均在写前 exit 2 拒绝。
- **Q5**：现有 done 门禁 5 条规则（advance_phase.py:69-95）。新规则中 `glob_has_files` 可直接沿用；**spec §7.2 的第二规则按字面写法不成立**——`content_match` 在 check_gate 里走 `full_path = key_dir / path_pattern`（:195）+ `.is_file()`（:223），含 `*` 的 glob 路径 stat 永远 False，规则将永久 fail。给出修正代码（固定文件名或新增 `glob_content_match` 检查类型，约 10 行）。与既有 PASS 规则无冲突。
- **Q6**：agent 会话检测用**已存在**的 `PI_CODING_AGENT=true` / `AI_AGENT=pi`（cli.ts:21-22，pi 进程无条件设置，bash 子进程继承）；`PI_WORKER_TASK` 仅标记 worker（launcher.py:693-771）；PM 专属标记不存在，PM = `PI_CODING_AGENT` 在且 `PI_WORKER_TASK` 不在。`pm-orchestrator.ts:666-687` 的过滤器是 worker trace 的残留风险**计数器**，不挡任何写、不覆盖 `evidence/review/**`；PM 写禁止面须按 `xkey-gate-guard` 模式新增 `pi.on("tool_call")` 守卫。两层防护各自的挡/不挡与绕过方式见 Q6。

## 证据

主锚点文件（下文 path 均相对仓库根）：

| 文件 | 用途 |
| --- | --- |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | task.md 头部组装/落盘、dispatch 工具 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts` | TS 头部解析单源 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/run-store.ts` | run.json 终态/`supersedes:` 解析/run marker |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | PM 轮询、终态回收循环、告警通道 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | worker 结算判定、退出码折叠 |
| `packages/multi-workers/mw_common.py` | Python 头部解析镜像、锁、终态集合 |
| `packages/multi-workers/launcher.py` | 退出码→状态映射、`lost` 写入、PI_WORKER_TASK 设置点 |
| `packages/multi-workers/mw.py` | `mw decide` CLI、原子配置写 |
| `.agents/skills/agentic-task/core/scripts/advance_phase.py` | GATES/check_gate/Phase 行读取 |

## Q1 头行注入（decision:）

**现状头部组装链**（两入口共用，注释明言"so the two entries can never drift"，ui-bridge.ts:2274-2281）：

1. `planDispatchFrontmatter`（ui-bridge.ts:1336）拼 `headLines = ["type: <type>"]`，按条件追加 `phase:`（:1378）、`images:`（:1379），随后模型/角色行 → 返回 frontmatter 字符串（ui-bridge.ts:1377-1380 为卡面锚点，实际 `const typeLines` 在 :1380）。
2. `writeDispatchTaskMd`（ui-bridge.ts:2282）依次 merge：`mergeWriteScope`（:1837-1843，尾插一行）→ `mergeAllowForeignWrite`（:1828-1832）→ 有 card 时 `mergeCardHeader`（:2126-2143，尾插 `card_path:`/`card_sha256:`/`envelope_producer:`/`write_face:`）→ 落盘 `` fs.writeFileSync(taskMdPath, `${frontmatter}\n${body}\n`, "utf8") ``（:2315-2327）。

**注入位置与格式（设计）**：在 `writeDispatchTaskMd` 的 merge 链末端（`mergeCardHeader` 之后）加一步同构 merge：

```ts
function mergeDecisionHeader(frontmatter: string, decisionId: string | undefined): string {
	if (!decisionId) return frontmatter;
	return `${frontmatter.replace(/\r?\n$/, "")}\ndecision: ${decisionId}\n`;
}
```

- 值 = `decision_id = "<dp>:<trigger_id>"`，dp1 通道即 `dp1:<task_key>`（spec §6.1）。单行、列 0、键名 `decision` 匹配键语法。
- **注入时机：frontmatter 生成之后**（`writeDispatchTaskMd` 内），不在 `planDispatchFrontmatter` 之内。理由：该函数是模型/分诊职责且被 `/worker` 命令与 `dispatch_worker` 工具共享；`writeDispatchTaskMd` 是唯一写点（T-01 提取注释，ui-bridge.ts:2274-2281），在此注入保证两入口字节一致，且 `card_path`/`write_face` 已就位，`decision:` 成为 frontmatter 块末行（body 前，空行/围栏语义不变）。
- 仅当 dp1 实际产生 `acted=true` 的 decide 行时注入；`mode=suggest`（AC-015）不改行为，不注入（否则 settle 会把结果错记到未生效建议上）。**（设计裁定，非代码事实）**

**解析器安全性证明**（是否会报错）：

- TS 键语法：`HEADER_KEY_RE = /^[A-Za-z_][A-Za-z0-9_-]*:/`（task-frontmatter.ts，锚定）。`decision: dp1:x` 是 key-shaped 行。
- 头部区域划分（task-frontmatter.ts `regionFromLines`；Python 镜像 `mw_common._region_from_lines`，mw_common.py:549-566）：`---` 围栏内 → 围栏内多一行；无围栏有空白行 → 空行前多一行（本仓库现实 task.md 即此形态）；既无围栏也无空行的退化形态 → key-shaped 前缀 run 延长一行（`truncated: true` 分支）。三种形态都只是区域边界移动，无报错路径。
- `readTaskType`（task-frontmatter.ts）：只匹配 `type:` 前缀，`decision:` 行被忽略；首行仍是 `type:`，值与 provenance 不变。
- `readTaskHeaderScalar(text, key)`（task-frontmatter.ts；Python `mw_common.read_task_header_scalar` mw_common.py:574-588）：参数化按键读取，现有调用只取 `phase`（mw.py:2256）等，从不请求 `decision`，未知键零影响；值含冒号（`dp1:x`）安全——切片在键前缀首个冒号之后。
- `parseSupersedes`（run-store.ts:170-173）：正则 `/^supersedes:[ \t]*(\S+)[ \t\r]*$/m`，`decision:` 行不匹配，返回值不变。
- 模块级约定：task-frontmatter.ts "Pure functions only: no fs, no cwd, no clock, no throws"；run-store.ts `readRunState` 吞错返回 undefined。Python 侧无第二个严格头部解析器（全仓仅 `mw_common` 一处实现，state.py:179-190 复用同一 region 读取）。
- 边界核验：退化形态下 `scanBodyTypeLines` 的起点后移一行——若原 body 第一行恰是 `type:` 行，它可能被划入头部区；但 `readTaskType` 永远先命中头部首行 `type:`，body 值仍不返回（spec F-10 语义不变）。

## Q2 settle 触发点与 6 种终态映射

**现有终态回收路径**：PM 轮询循环（`POLL_INTERVAL_MS = 4000`，pm-orchestrator.ts:86）每 tick 读队列 entries，其中终态分支 `for (const entry of entries) { if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue; ... }`（pm-orchestrator.ts:1691-1745）依次做：ownership 过滤（:1698-1703，watched key ∪ 本窗口派发）→ `notified.add` + `readbackDelivered.add`（:1710-1711，每 task 每会话恰一次）→ `recordWriteScopeResidualRisks`（:1719）→ `recordModelErrorTerminal`（:1724）→ 终态 readback 投递（:1733-1745）。

**唯一 settle 追加点（设计）**：该循环内、`recordModelErrorTerminal` 之后、readback 之前（约 :1730 处），新增 `recordDecisionSettle(agenticdocRoot, entry, taskDir)`。判定依据排除其余候选：

- worker 侧 `writeRunState`（run-store.ts:231-248）错误层级：settle 是 PM/档案关注点，worker 无 decisions.jsonl 写权。
- Python launcher `_reap_status`（launcher.py:986-1032）：per-run 进程视角，拿不到 PM ownership/去重上下文，且 spec §6.2 明言"PM 回收终态时"。
- ack 路径（ui-bridge.ts:2616-2640）：ack 是 per-window UI 折叠动作，`needs-clarification`/`lost` 可能永不 ack，settle 会丢。
- 该循环是唯一同时满足：(a) 每终态迁移恰消费一次（`notified` 去重）；(b) `entry.status` 与 `taskDir` 同点可得；(c) 已有两个同性质的终态感知出口（write-scope 残留、model-error streak）作先例；(d) 对 conductor 派发的任务同样生效（queue rows 不分派发来源，D-104 只隔离 dispatch 侧，pm-orchestrator.ts:1325-1349）。

**6 种终态映射判定依据**（判定输入全部在追加点作用域内）：

| 终态（queue `entry.status`，pm-orchestrator.ts:88-90） | 附加判据 | outcome | 依据 |
| --- | --- | --- | --- |
| `done` | `run.json.exit === 0` | `ok` | 契约段齐已被折叠进退出码：worker 结算判定 `const exitCode: 0 \| 2 = evidence.delivered && gaps.ok ? 0 : 2`（worker-mode.ts:3668）先于单次落盘，`markOutcome` 把 0→done / 2→needs-clarification / 其余→failed（worker-mode.ts:2676-2682），output.md marker、`[END] exit=`、run.json、launcher `_exit_to_status`（launcher.py:976-983）与 `_reap_status` 产品优先（launcher.py:986-1032）六处同源。PM 侧不再复读契约段（避免第二 oracle）。 |
| `failed` | `!isModelErrorTerminal(taskDir)` | `rework`（计返工，不进推翻率） | exit 1 路径。 |
| `failed` | `isModelErrorTerminal(taskDir)`（`run.json.model_exhausted===true` 或 `## Exit Reason` 以 `model unavailable:` 开头，pm-orchestrator.ts:731-752） | `inconclusive`（不进分母） | exit 3 / model_exhausted；worker 侧置 flag 于 worker-mode.ts:3805、4028-4031。 |
| `needs-clarification` | — | **不落 settle 行**，保持 `pending`，转人 | 人是下一个 settle 主体；无 settle 行 = 档案自然呈现 pending，避免把人答复前的中间态伪造成结论。 |
| `lost` | — | `pending` + `note=lost` | `lost` 只能由 Python launcher 追加（run-store.ts:16-18 契约；launcher.py:2331-2332 `mw_common.mark_run_lost`；终态集合 mw_common.py:2131 与 run-store.ts:34 双语镜像）。进程消失、结果未知，必须显式落标记行闭合关联回路，否则档案里永远像"仍在跑"。 |
| `rollback` | **非终态**：新任务 task.md 带 `supersedes: <old>` 被接受派发时触发 | `rollback` | `supersedes:` 是替换已完成 run 的唯一途径（run-store.ts:14-19、177-224 `evaluateRunIdentity`；PM 扫描消费点 pm-orchestrator.ts:1338-1349）。追加点 = 派发接受处（ui-bridge.ts:2544-2581 落盘成功后 / `dispatchTask` ok 返回处，task-dispatcher.ts:291-335）：`parseSupersedes` 读新任务内容 → 读旧任务 task.md 头部 `decision:` 行（Q1 注入）→ 对旧 decision_id 追加 `outcome=rollback` settle 行。Python conductor 派发路径（dispatch.py）需镜像同一判定（跨语言契约，dispatch.py:1065 已有 run-terminal 判定先例）。 |

decision_id 反查：终态行只带 taskKey，settle 前读 `<taskDir>/task.md` 头部 `decision:` 标量（Q1 注入）；缺失 ⇒ 非 dp1 任务 ⇒ 不关联（spec §6.2 的显式登记类）。

**重复 settle 幂等（设计裁定）**：**允许多条、最后一条生效，不拒绝第二条**。理由：`done→ok` 之后人工 revert / supersedes 重派产生 `rollback` 是 spec §6.2 表内的合法先后序列，"每 decision_id 只认一条 settle"会直接消灭 rollback 通道（spec §6.1 的"同 trigger_id 仅一条 decide 行"约束只针对 decide 行）。防重放：PM 的 `notified` 是 per-session，PM 重启会对同一条未 ack 终态行重新进入循环（:1691-1692 的过滤不含 ack 状态）⇒ 写入侧按 `(decision_id, outcome, run_id)` 三元组去重（`run_id` 取 run.json 的 `<task_key>@<iso>`，run-store.ts:108-110，天然区分重派），重复触发静默跳过；fold 读侧仍以文件序最后一条 settle 为有效 outcome。

## Q3 报告生成

**数据来源**：全部六节都来自 `decisions.jsonl` 按 `decision_id` 的 fold（decide/override/settle/authority-change 四类行合并读，spec §6.1），不读 `_workers.parallel`、ack 档或 auto-decisions.jsonl：

- 概览计数：fold 后各 decision_id 的有效 settle outcome 计数；`N` = 有效 outcome ∈ {ok, rework, rollback} 的去重 decision_id 数（`inconclusive` 剔除、`pending` 无 outcome 不计）。
- 判据表：decide 行的 `state_digest / questions_version / answer / confidence`（**参考**，不作门控，spec §7.1）。
- 逐决策清单：每 decision_id 的 decide→settle 链。
- 分歧样例：jev 答 X、人做 Y 的行对（override 行、`authority-change(by=human:*)`、settle=rollback）。
- 候选调整：阈值机算（30 条滑窗 `override_rate>0.15` 等，spec §7.3）汇总为 `suggest:` 行。
- 无法关联项：**唯一非 fold 来源**——spec §6.2 的显式登记行（`task_key=null`、`note=composite`、dp10 长时延、worker 内 tool_call、跨 key 外溢）。

**生成时机（准确判据）**：挂在 `advance_phase.py` 推进成功路径——门禁通过（:586-592）且 `update_pm_state` 完成（:594-606）之后。推进前读到的 `- Phase:` 行给出 `prev_phase`（:538-557，注意：任务卡锚点 `:345-351` 已漂移，现文件 Phase 行读取在 main() 内 :538-557）。判据：`target` 推进成功 **且** `not list(key_dir.glob(f"evidence/review/decision-review-{prev_phase}-*.md"))` → 生成 `decision-review-<prev_phase>-<ts>.md`（报告覆盖刚结束的 phase）。`done` 推进同样触发（prev=verify）。生成器为 Python 脚本逻辑（advance_phase.py 内新函数或独立 `mw decide report`），机器生成、无 LLM 参与，避免与 Q6 签收写禁止面冲突。

**写入路径白名单**：仅 `<key>/evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md`；时间戳 `datetime.now().strftime("%Y%m%d-%H%M")`（compact 化自 advance_phase.py:32 `TS_FMT = "%Y-%m-%d %H:%M"`，文件名不得含冒号）。由脚本写、不经 agent 工具，故不触碰 sign-*.md 写禁止面（Q6）。

**`N<5` 判定与文案**：`N` 如上定义（去重 settle、剔 inconclusive、pending 不计）；`N < 5` 时报告概览节强制逐字包含 `数据不足，不结论`（spec §7.1 / AC-008），且跳过判据表与候选调整两节（或标注"仅供参考"）——防止小样本上机器给调整建议。

**`suggest:` 机器可读格式**：单行、行首锚定：
`suggest: (enable|disable) <dp-id>(, <dp-id>)*(, N=<int> override=<int>)?`
spec 示例：`suggest: enable dp4`、`suggest: disable dp5, N=12 override=3`（§7.1）。消费者（doctor 高亮 / 人执行 `mw decide dp off dpX`，§7.3）只认 `^suggest: ` 前缀；一行一方向，多建议拆多行。

## Q4 签收文件格式与解析

**`sign-*.md` 完整格式（设计，落在 `<key>/evidence/review/sign-<yyyymmdd>-<hhmm>.md`）**：

```markdown
# Decision Signoff — <key> <phase>

conclusion: continue        # 必填，∈ {continue|narrow|revoke}
promote: dp4, dp9           # 可选；缺省/`-` = 无
demote: dp5                 # 可选；缺省/`-` = 无
p0-open: dp2                # 当前仍开启的 P0 项全集（AC-009；无则写 `-`）

（正文：人写理由，机器不解析）
```

三种 conclusion 各自产生 `authority-change` 行（AC-009）：continue=维持现配置、narrow=按 demote 收、revoke=全收（等价逐 dp off，仍走 dp 命令语义而非直接改 JSON）。`p0-open:` 与 `decide-points.json` 的当前开启 P0 集做**集合相等**校验。

**解析容错（`mw decide dp apply <file>`，命令尚不存在——mw.py:7504-7534 现仅 run/probe/show/set 四子命令，`grep` 证实；此为新增设计）**：

- 缺 `conclusion:` 或值不在三枚举内 → 整体拒绝，exit 2，输出 `signoff: missing/invalid 'conclusion:' (continue|narrow|revoke)`。
- `promote:`/`demote:` 拼错 dp id（不在 24 项注册表，decision.py DecisionConfig :231 起的表）→ 拒绝并逐个点名，**绝不静默跳过**（AC-011"未知 dp id 被拒"）；`promote` 与 `demote` 同一 dp → 冲突拒绝。
- P0 漏列 / 列了未开项 → 拒绝并输出 diff（"signoff p0-open 与 decide-points.json 不一致：缺 dpX / 多 dpY"）；签收文件**不得开启 P0**——promote 目标 tier=P0 → 拒绝并提示改走 `mw decide dp on <dp> --i-understand-p0`（AC-002 的人类确认语义不被签收旁路）。门禁层对 P0 清单无法用现成 check_type 校验（动态集合），done 门禁只在失败提示文案里提醒（Q5）；权威校验在 dp apply。
- 多行/正文干扰：解析只认列 0 的四个键前缀（与 task.md 头部同一套锚定习惯），正文任意内容不影响。

**处理顺序：先全量校验，再单临界区原子写；绝不逐条写**。理由与既有原语：

1. 全量校验（上列全部规则，纯读）任一失败 → exit 2，磁盘零扰动。
2. 校验通过后进入**一个** `mw_common.acquire_lock` 临界区（mw_common.py:2369）：(a) 重读 decide-points.json（防 TOCTOU）并复核；(b) 追加 authority-change 行到 decisions.jsonl（append-only、prev_sha 链、spec §6.1）；(c) 配置落盘复用 `_decide_write_config` 的 tmp + `os.replace` 协议（mw.py:773-793，注释明言 P-003 atomic write 且锁护全程）。
3. (b)(c) 顺序为先档案后配置，均在锁内；若 (c) 失败（os.replace 同目录失败属病态），打印"配置未变但档案已记 apply"差异行并不掩盖（档案 append-only，无回滚行语义，spec §6.1 撤销用负行）。
4. 逐条写的坏处（被否）：promote 两条、第二条失败时配置与档案半更新，违背 AC-009"三种 conclusion 各产生 authority-change 行"的原子审计要求。

## Q5 门禁规则

**现有 `GATES["done"]` 全部 5 条**（advance_phase.py:69-95，逐条列出）：

1. `("achieved.md", "file_min_bytes", 200, ...)`（:70-74）
2. `("achieved.md", "content_match", r"系统行为变化", ...)`（:75-80）
3. `("achieved.md", "content_match", r"遗留", ...)`（:81-86）
4. `("pm-state.md", "content_match", r"PASS", "pm-state.md 必须包含至少一个 PASS 证据")`（:87-88）
5. `("evidence/quality-gate-report-*.md", "glob_has_files", 1, "必须先执行 /quality-gate 生成 evidence/quality-gate-report-*.md")`（:89-94）

**新规则具体代码**——先纠正 spec §7.2 的一个字面陷阱：`content_match` 分支用 `full_path = key_dir / path_pattern`（check_gate :195）+ `full_path.is_file()`（:223）；pathlib/stat **不展开 glob**，`Path("…/sign-*.md").is_file()` 恒 False，故对 `evidence/review/sign-*.md` 直接套 `content_match` 会让 done 门禁永久 fail（这就是与既有规则的"冲突"——不是语义冲突，是模式不兼容）。两条规则只能这样落：

规则 1（直接沿用，现成 check_type，`glob_has_files` 分支走 `key_dir.glob`，:259-263）：

```python
(
    "evidence/review/sign-*.md",
    "glob_has_files",
    1,
    "收尾强制签收：必须存在人工签收文件 evidence/review/sign-*.md（由人在 agent 会话外写入，PM/agent 无权写）",
),
```

规则 2（conclusion 正则；二选一）：

- 方案 A（零脚本改动，推荐首选）：约束签收文件用**稳定名** `sign-final.md`（glob 规则同时保留兜底存在性检查）：
  ```python
  (
      "evidence/review/sign-final.md",
      "content_match",
      r"^conclusion:\s*(continue|narrow|revoke)\s*$",
      "签收文件必须含机器行 conclusion: continue|narrow|revoke（列 0、单行）",
  ),
  ```
- 方案 B（保留任意时间戳文件名）：给 check_gate 增加约 10 行的 `glob_content_match` 检查类型（与 `glob_has_files` 同构，取 glob 首个匹配做 `re.search`，多匹配取最新 mtime），再挂同上正则。这超出"纯沿用现成 check_type"，需同步 `test_advance_phase.py` 与框架分发副本（`.agents/skills/agentic-task/core/scripts/` 为运行源，`packages/multi-workers/.tmp/agentic-task/**` 为测试 staging，`sync_framework.py` 负责项目侧安装同步——三处 parity）。

**与既有 PASS 规则的冲突**：无。规则 4 只查 `pm-state.md` 含 `PASS` 子串；新规则对象是不同文件、不同 check_type，互不影响。`glob_has_files` 只判数量 ≥1，读任意同名命中——它**无法**校验文件出自人手（防伪靠 Q6 两层防护 + dp apply 的 P0 集合校验，门禁自身不做作者鉴定）。

**门禁失败人读提示**：check_gate 失败输出走既有通道（advance_phase.py:587-592）：`GATE BLOCKED: <key> cannot advance to 'done'` + `Current phase: <p>` + 每条 `MISSING: <pattern> (0 matches) — <描述>`。提示文案写在规则第 4 元组（见上），需说清三点：缺什么、找谁补（人，不是 PM）、补完重跑 `/agentic advance done`。AC-009 的"漏列 P0 则门禁提示"落在规则 1 的描述尾句：`（dp apply 会校验 p0-open 行与 decide-points.json 一致）`——门禁只提示，权威校验在 dp apply。

## Q6 dp apply 护栏

**"当前在 agent 会话内"的检测——代码里已存在的变量名与设置点（逐一核实）**：

| 变量 | 设置点 | 覆盖面 |
| --- | --- | --- |
| `PI_CODING_AGENT=true`、`AI_AGENT=pi` | `packages/coding-agent/src/cli.ts:21-22`，pi 进程启动无条件设置 | **一切 pi 会话**（PM 与 worker）；bash 工具子进程继承父 env（core/tools/bash.ts:158-181 `getShellEnv()` 拷贝，仅删除 `PI_SESSION_ID/PI_SESSION_FILE/PI_PROVIDER/PI_MODEL/PI_REASONING_LEVEL`，bash.ts:166-171） |
| `PI_WORKER_TASK=<abs task.md>` | `packages/multi-workers/launcher.py:693,711,720,743,768-771`，仅 worker 派发路径设置 | 仅 worker 进程 |
| `PI_SESSION_ID/PI_SESSION_FILE/…` | bash.ts:167-175，`exposeSessionEnvironment`（默认 true，BashToolOptions 注释 :186-187） | 条件存在（设置关闭时被删除），**不宜作护栏输入** |
| PM 专属标记 | **不存在**（全扩展 grep `PI_[A-Z_]+` 仅上表各值） | PM 判定 = `PI_CODING_AGENT` 在且 `PI_WORKER_TASK` 不在 |

**`dp apply` 进程层护栏（新子命令内，第一层）**：

```python
def _decide_dp_apply(args, project_dir):
    in_worker = "PI_WORKER_TASK" in os.environ
    in_agent = os.environ.get("PI_CODING_AGENT") == "true" or os.environ.get("AI_AGENT") == "pi"
    if in_worker or in_agent:
        who = "worker 会话 (PI_WORKER_TASK)" if in_worker else "agent 会话 (PI_CODING_AGENT)"
        print(f"[mw decide dp apply] refused: {who}; 签收 apply 仅限人在自己的终端执行", file=sys.stderr)
        return 2
    ...
```

- exit 2 与 D-003 既有退出码语义一致（mw.py:973 注释）；提示语点名环境变量，人能看懂为何被拒。

**PM 写禁止面接线（第二层）**：`pm-orchestrator.ts:666-687`（实际 :666-693）的 `countWriteScopeResidualRisks` 是**审计计数器**——读 worker `trace.log` 里 `[WRITE_SCOPE]` 且 `blocked=false`+`risk=deny-basename` 的行并落账（pm-orchestrator.ts:674-687），它**不拦截任何写、也不覆盖 `evidence/review/**`**；worker 的写面约束来自 task.md 契约（mw-write-surface），对 PM 会话无约束。因此签收文件写禁止面必须按 `xkey-gate-guard` 既有模式新增注册（该 guard 注册于**所有模式**，index.ts:50；机制 = `pi.on("tool_call")` 对 write/edit 路径解析匹配 + bash 文本级 fail-closed 扫描，xkey-gate-guard.ts:239-282）：

- 守卫目标：`<project>/**/.agenticdoc/*/evidence/review/sign-*.md`（含绝对/反斜杠/相对拼写的 fragment 匹配，沿用 `guardedFragmentPresent` + `isUnder` 手法，xkey-gate-guard.ts:133-155；写动词与重定向正则直接复用 :170-186 的 `WRITE_VERB_RE`/`POWERSHELL_WRITE_RE`/`REDIRECT_RE` 族）。
- 刻意**不**守卫 `decision-review-*.md`（Q3 报告可由脚本/人写，是建议通道不是答案通道）——签收文件是"人类答案通道"，与 gates/** 同性质（xkey-gate-guard.ts:8-14 的设计动机原文）。
- worker 侧拒绝同时落 `[XKEY_GATE]` 式 trace 行（`recordXkeyGateBlockTrace`，xkey-gate-guard.ts:213-236）。

**两层防护各自能挡/不能挡（含绕过）**：

| | 能挡 | 不能挡 / 绕过 |
| --- | --- | --- |
| 第一层（dp apply 进程检测） | PM/worker 通过 bash 工具的**诚实调用**（env 完整继承）；RPC/print 模式子进程同样继承 | (1) agent 先 `env -u PI_CODING_AGENT` / PowerShell `$env:PI_CODING_AGENT=$null` 再执行——文本级命令扫描不查 env 洗涤；(2) agent 说服/诱导人在其终端执行；(3) 直接用 python -c 调 decision 库函数（绕过 CLI 入口，需第二层+审计补位） |
| 第二层（sign-*.md 工具守卫） | write/edit 工具直写、bash 明文引用 + 写动词/重定向/PowerShell cmdlet/sed -i/inline code（fail-closed），拒绝可观测（trace/refusal） | (1) **同 uid 进程外写入**（编辑器、独立 Python、脚本）——两层都不是沙箱，xkey-gate-guard.ts:28-33 残余风险原文承认；(2) 路径混淆绕过文本匹配（变量拼接、编码后解码写、`cd` 后相对名）——fragment 匹配只认明文；(3) 不经工具通道的 IPC |
| 兜底 | dp apply 的 P0 集合校验 + authority-change 档案行 + `decide-points.json` 变动必留 `kind=authority-change` 行，事后可审计"谁以何身份改了配置" | 伪造完整证据链的合谋场景（超出应用层守卫目标，与 xkey-gate-guard 同一威胁模型边界） |

补充：`decide-points.json` 本身目前**无** agent 写守卫（protected-config 只护 `.pi` 配置，protected-config.ts；xkey-gate-guard 只护 `_autopilot/**`）；AC-010 的"机器零写配置"靠 grep 审计 + dp apply 第一层护栏。若要闭环，可把 `.mw/decide-points.json` 一并纳入 Q6 新守卫的 fragment 清单（人走 `mw decide dp on/off` 在 agent 外执行，不受影响）——列为设计建议。

## 残留与未验证

- 未验证：`decisions.jsonl` 的写者实现（spec §6.1 的 prev_sha 链、四层 append-only）在本工作树尚不存在（全仓 grep `decisions.jsonl` 仅命中 spec 与 auto-decisions/triage-decisions 两个既有文件），Q2/Q3 的 ledger 侧行为是按 spec 的设计推导，非代码事实。
- 未验证：Python conductor 派发路径（`packages/multi-workers/autopilot/dispatch.py`）对 `supersedes:` 的具体消费点行号——已确认 `evaluateRunIdentity` 的 TS 侧语义与 dispatch.py:1065 存在 run-terminal 判定，但 rollback 追加在 conductor 侧的对称挂点需要实现期再核（Q2 已标注"需镜像"）。
- 未验证：`advance_phase.py` 任务卡锚点漂移的第三方佐证——卡面 `:345-351`、`:69-95`（后者吻合）、`:191-289`（吻合）、`:220-227`（吻合）；Phase 行读取实测在 :538-557。
- 未验证：`xkey-gate-guard` 若扩到 `sign-*.md` 后对 review 类 worker 的影响面——review worker 的写面（read/find/grep/ls）本就不含 write/edit/bash，理论无冲突，但未跑套件验证。
- 设计裁定（非代码事实，需 PM/人确认）：Q1 的"仅 acted=true 才注入 decision: 行"；Q2 的"needs-clarification 不落 settle 行"；Q3 的报告按"刚结束的 phase"命名；Q4 的"签收不得开启 P0"；Q5 的方案 A/B 取舍。

## 上下文来源

- 任务卡：`.agenticdoc/mw-decision-substitution/workers/ds-d5-association-report-signoff/task.md`
- Spec：`.agenticdoc/mw-decision-substitution/spec.md`（§6.1/§6.2 :164-190、§7.1/§7.2 :194-203、§7.3 :204-211、AC-006~AC-015 :212-229）
- 源码（全部通读或定点核对）：ui-bridge.ts（1336-1440、1824-1843、2126-2143、2274-2359、2540-2640 段）、task-frontmatter.ts（全文）、run-store.ts（全文）、pm-orchestrator.ts（84-109、495-776、1320-1349、1620-1795 段）、worker-mode.ts（2557-2700、3596-3720、3800-3840 段）、worker/output-sections.ts（全文）、shared/ack-store.ts（全文）、shared/xkey-gate-guard.ts（全文）、task-dispatcher.ts（286-335 段）、extensions/agent-team-loop/index.ts（头部注册段）
- Python：mw_common.py（506-588、2131-2200、2369 段）、launcher.py（693-771、976-1032、2331 段）、mw.py（668-993、7504-7572 段）、decision.py（函数索引）
- 脚本：`.agents/skills/agentic-task/core/scripts/advance_phase.py`（全文）
- 环境变量盘点：cli.ts、core/tools/bash.ts、全扩展 `PI_[A-Z_]+` grep

Q-answered: 6/6
