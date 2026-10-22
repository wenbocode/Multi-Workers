# D3 设计调研：dp3 三切（执行链）+ dp2 checkpoint 结构化升级

> key: mw-decision-substitution · card: `tasks/D3-dp3-dp2-execution.md` · 2026-10-19 · type: research
> 方法：只读调研，未改任何源码/配置；所有 `path:line` 为 2026-10-19 工作树实测（read 工具逐行核对），卡片锚点漂移处已标注。

## 结论

- **RQ-1**：dp3 唯一插入点 = `worker-mode.ts` `finishSuccess()` 内、`const exitCode: 0 | 2 = …`（:3664）之后、`writeOutputGuarded(…)`（:3671）之前。该点之后才发生全部终态落盘（`## Questions`、no-product 告警、`recordEnd`→run.json `needs-clarification`、`[END] exit=2`），该点之前 evidence/gaps 已算完（dp3 的全部判定输入就绪）且仍在本进程内（可注入后继续跑）。
- **RQ-2**：3a=问题含可在仓内检索定位的指称（路径/符号/命令/报错串）且无意图词；3c=TS 本地匹配 task 卡 > goal.md > pm-state Decisions > 会话历史的既定表述（内容词 Jaccard≥0.6 且共享≥1 个精确指称 token，命中即引用原话）；3b=含意图/偏好词或无法判定。默认 3b 安全：3b 不产生任何自动动作，等价于现状 NC 路径（DS-4 无默认动作）。
- **RQ-3**：推荐 `pi.sendUserMessage(answer, { deliverAs: "followUp" })` steer 注入（AC-003 明文；settle 时无在途工具调用，工具返回值通道不可用；checkpoint steer/self-check 已有同通道先例），配 `[mw dp3-answer]` 机器可归因前缀 + `[DECIDE]` trace 行 + decisions.jsonl 行，防"人已表态"污染；NC 率副作用用 `nc_raw = NC + [DECIDE] dp3 acted=true` 双指标补偿，17.4% 不会"看起来 0%"。
- **RQ-4**：四值降级全部落回**字节不变**的原问人路径（output.md/run.json/告警零改动），只留档案行；`escalated_reason ∈ {disabled, unavailable, low-confidence, input-incomplete}`；防重复问 = 进程级 dp3 预算 1 次 + trigger_id 幂等；原问题永不丢（`## Questions` 首行契约）。
- **RQ-5**：dp2 结构化输入 = `CHECKPOINT_LINE_RE`（heartbeat.ts:95-96）8+4 字段 + 近 3 个 checkpoint 趋势 + 自评计数，全 L0/L1 ≤2KB；mode=auto 只适合**收窄**（四问判据全过），拆/直执必须人；注入点改法 = `pm-orchestrator.ts` 发散升级块（:1658-1690）在 `escalated.add`（:1676）后、`deliverPmAlert`（:1683）前插 `decideFor(dp2)`，acted=收窄 → 写 worker steer 请求文件 + `displaySummary`（不 triggerTurn），其余分支 `deliverPmAlert` 字节不变。
- **RQ-6**：五条不变量（dp3 关闭字节不变 / `## Questions` 首行原文 / checkpoint 每任务至多升级一次 + triggerTurn 语义 / worker 仍能 NC 终态 / goal mtime 记录不受影响）各配可测检查方法（见 Q6）。

---

## Q1 dp3 判定链插入点：从"我需要澄清"到 exit 2 的完整调用链

### 1.1 现状调用链（全部实测）

今天 worker 的"需要澄清"**不是 agent 主动声明**，而是 harness 在 settle 时判定的终态：

1. `pi.on("agent_settled", …)`（`worker/worker-mode.ts:3824`）— 每次 settle 入口（含错误 settle / phase 边界，前置分支先行）。
2. → `settleOrSelfCheck()`（:3734）— 判 recovery 缺段；实质缺段且未自检过 → 补一轮 followUp 自检后返回；否则进 `finishSuccess()`。
3. → `finishSuccess()`（:3610）：
   - :3622-3626 `evidence = isWritelessRole(type) ? hasDeliverableEvidence(taskDir, lastAssistantText) : {delivered:true}`（`shared/deliverable-evidence.ts` 三通道判定；writeless 无产物 → `delivered:false, channel:"none"`）；
   - :3655-3661 `gaps = readTerminalGaps(…)`（recovery 契约 + change ledger）；
   - **:3664 `const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;` ← NC 判定时刻**；
   - :3671-3691 `writeOutputGuarded({ exitCode, questions: … })` → `markOutcome(2)`（:2675-2682，**`:2681` 即卡片所指 NC 终态映射**：run.json status=`needs-clarification`）→ `writeOutput`（`worker/output-writer.ts:527` exit-2 分支写 `## Questions`）；
   - :3702-3706 无产物时 `recordDispatchAlarm(no-product)`；
   - :3717 `recordEnd(2)` → `[END] exit=2` + `finishRun("needs-clarification", 2)`（run.json 终态提交）。
4. → handler 返回；pi print 模式自然退出，launcher 侧 `_reap_status`（`packages/multi-workers/launcher.py:985`起，product-first）按 run.json 终态收行；`:976-982 _exit_to_status` 仅作无 run.json 时的回退映射。
5. PM 侧下一 tick 终态回读：`readTerminalDetail`（`pm/ui-bridge.ts:677-694`）取 `## Questions` **首行** → `deliverWorkerResult`（:213-216，`deliverPmAlert` :199-208 `triggerTurn:true` 唤醒 PM）→ `PM_CONTINUE_HINT`（`pm/pm-orchestrator.ts:1497-1503`）指示"needs-clarification→整理问题向用户澄清"——**这就是 dp3 今天的等人点**。

频次证据：242 个 run.json 中 42 个 `needs-clarification`（17.4%）；42 条中相当部分是 writeless 无产物/问题可自答类（`evidence/research/spec-decision-inventory-20261016.md` Q2/替换优先级 1）。

### 1.2 唯一插入点

**`finishSuccess()` 内、:3664 算出 `exitCode===2` 之后、:3671 `writeOutputGuarded` 之前。**

唯一性论证（四个必要条件只有该点全满足）：
- **判定输入就绪**：`evidence.detail` / `gapsReason` / `lastAssistantText`（真实自然语言问题所在，见 Q2）在 :3664 处全部在手；
- **写 `## Questions` 之前**：`writeOutput` 是唯一 NC 产品写点（output-writer.ts:527），插入点在其前，自动应答时可以**整体跳过**终态落盘；
- **exit/run.json 终态提交之前**：`recordEnd`→`markOutcome`→`finishRun` 与 no-product 告警都在其后，acted 时 run 保持 `running`，看门狗/心跳照常；
- **仍在 worker 进程内**：只有进程内才能用 `sendUserMessage` 让**同一个 run** 继续跑（上下文、写面、watchdog 全保留）；跨进程方案都要重派（见 1.3 候选 6）。

### 1.3 为什么不是其它候选点

| 候选 | 位置 | 否决理由 |
| --- | --- | --- |
| `settleOrSelfCheck` | worker-mode.ts:3734 | 此处只有 `currentRecoveryMissing`（缺段），没有 ledger gaps（:3655 才算）；且自检 followUp 预算（`selfCheckSent`）已占用"补一轮再判"语义，dp3 插这里会和自检轮次叠加、顺序纠缠 |
| `markOutcome` | :2675-2682 | 被**所有** exit 路径共享（refusal/timeout/crash/settle），且由 `writeOutputGuarded`/`recordEnd` 在产品内容已定时调用——此处"不 exit"已不可能，调用方继续走完终态 |
| `agent_settled` handler 顶部 | :3824 | 每次 settle 都触发（错误 settle→exit 3、phase 边界都要先过），evidence/gaps 不在作用域；在此拦截等于重写整个 settle 状态机 |
| output-writer exit-2 分支 | output-writer.ts:527 | 错层：纯产品写函数，被直连调用方/测试共享；拿不到 `pi.sendUserMessage` 与 run 状态机，无法表达"继续跑"；也无法满足"exit 之前"（调用方随后续即 recordEnd） |
| PM 侧（`PM_CONTINUE_HINT` / 回读处） | pm-orchestrator.ts:1497 | worker 已终态（run.json needs-clarification 已提交，launcher 已收行）；只能重派新 run——丢进程内上下文、新 run_id、违反 spec §5.3"worker 侧、判定链之前插入" |
| launcher 侧（reap NC 时重派） | launcher.py:976-1010 | NC 无重试链（只有 exit 3 有）；重派=AC-022 下新 task_key `supersedes:`、全量上下文重建，成本与局部性都不满足 dp 注册表四问判据 |

### 1.4 插入前后伪代码对比

插入前（现状，:3664-3718 摘要）：

```ts
const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;
writeOutputGuarded({ …, exitCode, questions: evidence.delivered ? (gaps.ok ? undefined : `recovery-incomplete: …`) : `no-product: ${evidence.detail}` });
if (!evidence.delivered) recordDispatchAlarm(root, { kind: "no-product", … });
… recordEnd(exitCode); outputWritten = true;
```

插入后：

```ts
const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;
if (exitCode === 2 && dp3Attempted < 1 /* 进程级预算，防循环 */) {
  const v = decideDp3WorkerClarify({          // 永不 throw（镜像 triageDispatch 契约）
    taskKey, projectDir: process.cwd(),
    questionText: lastAssistantText,           // 真实问题（Q2）
    harnessDetail: evidence.delivered ? gapsReason : evidence.detail,
    taskDir, trueRoot: meta.trueAgenticdocRoot,
  });
  if (v.kind === "answer") {                   // 3a/3c 且 mode=auto
    dp3Attempted++;
    appendTrace(taskKey, root, `[DECIDE] ${iso} dp=dp3-worker-clarify sub=${v.sub} acted=true decision_id=${v.id}`);
    pi.sendUserMessage(dp3AnswerSteerText(v), { deliverAs: "followUp" });  // Q3
    return;                                    // 不写 output / 不告警 / 不 recordEnd；run 继续，watchdog 继续计时
  }
  if (v.kind === "escalate") {
    appendTrace(taskKey, root, `[DECIDE] ${iso} dp=dp3-worker-clarify acted=false escalated_reason=${v.reason}`);
    // 档案行由 Python 单写者落 decisions.jsonl；此处不改动任何产品字节 → 落回原问人路径
  }
  // v.kind === "off"（disabled）：零 spawn 零 trace，逐字节现状
}
writeOutputGuarded({ … });                     // 原路径字节不变
```

关键语义保持：`taskDone` 仍为 false → AC-010② 的二次 settle 防护不误伤；下一轮 settle 重新走 `settleOrSelfCheck → finishSuccess`（自检/NC 判定用**同一证据谓词**重判，不存在"答完即 done"的旁路）；followUp 载体与 recovery self-check（:3776-3783，同为 settle 时刻发 followUp）先例一致。

---

## Q2 3a/3b/3c 判定规则（机器可判定信号）

### 2.0 分类输入的来源

真实问题文本在 `lastAssistantText`（settle 前最后一条 assistant 消息，:3195-3206 采集），**不在** `## Questions`——后者是 harness 生成的机器句（`no-product: <detail>` / `recovery-incomplete: <gaps>`，:3686-3688）。分类器输入 = `lastAssistantText`（L2 敏感：含代码/绝对路径 → 只在本地用，外发 jev 前必须按 spec §5.4 三级脱敏，≤2KB canonical JSON）+ harnessDetail（L0）。

### 2.1 信号提取（TS 侧纯函数，可单测）

- `R_CONT`（事实指称）：反引号标识符 `` `x` ``、路径形 token（`[\w.-]+[/\][\w.-]+`，仓内相对）、命令/测试名（`npm run …`、`*_test*`、`make …`）、引号报错串。
- `R_INT`（意图/口径词）：`应该|建议|更(好|倾向)|偏好|优先|取舍|是否可以|要不要|请确认|需要你|approve|prefer|should|trade-?off`。
- `R_ALR`（已表态指示）：`之前|上面|已经说过|按你(的)?推荐|按推荐|as mentioned|你(已|之前)(说|确认)`。

### 2.2 三切判定顺序（先 3c → 3a → 默认 3b）

**3c 已表态复用**（本地匹配，确定性优先，能不问 jev 就不问）：
- 来源优先级（由具体到一般，逐级回退）：
  1. **本任务 task.md 卡**（dispatch card 正文——问题最可能是把卡里已写的答案又问了一遍）；
  2. 同 key 兄弟任务卡 `<key>/workers/*/task.md`；
  3. **goal.md**（项目级口径/目标类问题，`meta.trueAgenticdocRoot/goal.md`）；
  4. **pm-state.md `## 5. Decisions` 段**（本 key 既定裁定，DS-1..13 形态，实测存在于 `.agenticdoc/mw-decision-substitution/pm-state.md:54`）；
  5. **会话历史**（本 key pi 会话 JSONL 中 human 消息）——注意 L2：用户原话永不外发，故第 5 级**只在本地引用**：命中后 steer 引用原话+出处，发给 jev 的只有 L0 元数据（来源类型/得分/去敏关键词）。
- 命中阈值：内容词 Jaccard ≥ 0.6 **且** 共享 ≥1 个精确指称 token（路径/标识符/命令/报错串，取自 R_CONT）。得分 ≥0.75 → 确定性命中，零 jev 调用；0.6–0.75 → 发 L0 元数据给 jev 仅做消歧（是否真答了这个问题）。
- 输出：`{sub: "3c", quote: 原话, source: "path:line", score}`。

**3a 事实可查**：
- 条件（全过才判 3a）：① `R_INT` 为空；② R_CONT 指称在仓内**有界检索全部可解析**（grep ≤5 个 pattern、read ≤3 个文件、证据片段总预算 ≤2KB、只收 L0/L1：仓相对路径/短代码行，绝不收绝对路径与凭据）；③ 问题形态为定位/定义类（在哪/哪个文件/怎么运行/字段名/签名/为何报错<X>）。
- 执行：证据包（问题 + 片段）交 jev（B2 `llm-transitional`，`decision_backends.py:4`，模型 `jev-latest` :96）自答，答案必须带 `path:line` 引用；无引用的答案视为坏响应（→ Q4 `unavailable`）。

**3b 意图需人**（默认）：`R_INT` 非空，或指称不可解析，或 3c 低于阈值且 3a 条件不全 → jev 只做预消化（散乱问题 → 一个带选项的结构化问题），**不产生答案**。

### 2.3 默认 3b 为什么安全（证明）

- 3b 的行为 = 现状 NC 路径 + 一段附加的预消化问题：**零自动动作**（DS-4"禁止默认动作"的平凡满足）；人不在线时与今天完全同态（launcher 照常收 NC 行，PM 照常上抛）。
- 误分类代价不对称：错把 3b 判成 3a/3c → worker 可能沿错误答案跑偏（有界损失：本 run 墙钟预算 + PM 复核可回退，重派成本=NC 本身的重派成本）；错把 3a/3c 判成 3b → 只损失一次自动化机会（= 现状等待）。因此把不确定样本推向 3b 使最坏情况单调不劣于现状——默认方向安全。
- 形式化：设动作空间 {answer, escalate}，`escalate` 恒为现状；只要 3a/3c 的触发条件是"正向证据充分"（检索命中/阈值命中）而非"未见反证"，则 false-negative 只损失收益、false-positive 被 Q4 的置信门（low-confidence 阈值）二次拦截。

---

## Q3 答案注入形态（mode=auto 时如何交回 worker）

### 3.1 四种形态比较

| 形态 | 机制 | 优点 | 缺点 | 判定 |
| --- | --- | --- | --- | --- |
| A. steer 消息（followUp） | `pi.sendUserMessage(text, {deliverAs:"followUp"})`，settle 后排队新一轮 | **AC-003 明文规定**（"dp3a/dp3c 由 jev 自答并注入 steer"）；同进程续跑、上下文全保留；三处现成先例：checkpoint steer :3430-3444、deadline steer :3455-3467、recovery self-check :3776-3783（同为 settle 时刻发 followUp） | 属系统注入 user 角色——DS-7 排除"伪造 user 消息"因会污染"人已表态"检测 | **推荐（带归因护栏）** |
| B. 追加 progress.md | `appendProgressLine`（output-writer.ts:708-715） | 纯 append、留档 | 已 settle 的进程不会重读文件——**单独使用无法唤醒任何一轮**；只能作 A 的留档补充 | 否（单独），可并作审计面 |
| C. 修改 task.md 头部 | 改卡再重派 | 与"卡为真相"一致 | `parseTaskMd` 只在启动读一次（worker-mode.ts:2637 附近）；task.md 属 PM/派发写面，worker 无权写；重派=新 run_id+上下文重建+AC-022 约束；跨写者竞争 | 否 |
| D. 工具返回值回灌 | `tool_call` 钩子返回值（DS-7 首选通道） | 最安全、全审计、headless 生效 | **dp3 处 settle 时刻，没有在途 tool call 可回灌**；改造为先让 agent 调 `ask_decision` 工具再停 = 依赖模型自觉的 prompt 契约，而 writeless 无产物 NC 恰恰是 harness 判定的（agent 往往不知道自己将 NC），不可确定触发 | 否（保留给 dp5/dp7 类"运行中"决策点） |

### 3.2 推荐方案：A + 机器归因护栏（化解 DS-7 张力）

DS-7 排除的是**伪装成人的** user 消息；AC-003（spec rev3 绑定验收）已为 dp3 选定 steer。两者用"可归因"调和——注入文本固定形如：

```
[mw dp3-answer] 你的澄清问题已由自动决策解答（decision_id=<dp3-worker-clarify:<task>#nc1>，3a 事实检索 / 3c 已表态引用，非人工输入）。
问题：<原问摘引>
答案：<事实/原话引用 + path:line 出处>
请基于该答案继续完成任务并正常收尾。
```

- `[mw dp3-answer]` 前缀 + `decision_id` + "非人工输入"使会话 JSONL 里的这条 user 角色消息可被离线度量（spec §7.2 会话统计）按前缀剔除，"人已表态"检测不受污染；
- 注入同时落 `[DECIDE]` trace 行 + decisions.jsonl `kind=decide, acted=true`（Python 单写者），三面互证。

### 3.3 对 `needs-clarification` 计数的副作用与补偿

自动应答后 run 终态变为 `done`（若答后真完成）→ run.json 口径的 NC 率会从 17.4% 下降——这是**收益本身**，但必须可区分"少等人"与"没发生"：
- 定义双指标：`nc_human = run.json NC 计数`（真实转人）；`nc_raw = nc_human + [DECIDE] dp3 acted=true 行数`（假如没有 dp3 会等人的量）。两者均可零/低埋点统计：前者现成，后者一条 trace 正则 + decisions.jsonl 对账。
- `mode=suggest`（DS-13/AC-015）：jev 照跑、档案落 `acted=false`，**不注入、不改执行** → run 照样 NC，`nc_human` 不变；建议只进报告/回执（AC-015"不注入 steer"）。这保证灰度期 17.4% 口径完全不失真。
- 禁止把被答 run 在 run.json 里标成 NC 类变体（会破坏 `_exit_to_status`/`_reap_status` 契约与 launcher.py:976-1010 的终态语义）；可观测性由 [DECIDE] 行与档案承担。

---

## Q4 失败与降级（jev 不可用 / 低置信 / 输入不足）

### 4.1 总原则

任何非 `answer` 结果都**逐字节落回原问人路径**：不写 output.md、不改 run.json、不发告警、不注入——DP-1 的 fail-soft 先例（`triage-client.ts` 头部硬规则 + `unavailable()` 归一化 :254-259）直接复制；`decideDp3WorkerClarify` 本身 never-throw（内部全 catch，防异常落进 `agent_settled` 的兜底 exit-1 catch :3994-4013）。降级痕迹只有两处：档案行 + `[DECIDE]` trace 行，人类看到的问题与今天完全相同。

### 4.2 `escalated_reason` 四值触发条件（AC-005）

| 值 | 触发条件（可测） | 行为 |
| --- | --- | --- |
| `disabled`（未开启） | `.mw/decide-points.json` 缺失/不可读（→注册表默认，dp3=P2 默认 on 时此项不触发）、dp3 行 `enabled=false`、`mode` 非法值 | **零 spawn 零写**（复制 triage-client D-007"complete bypass"：连 trace 行都不留，保证 disable 逐字节零扰动）；`mode=suggest` 不是 disabled：jev 照跑、档案 `acted=false`，然后走原 NC 路径（不计 escalated_reason——它不是自动尝试失败，是配置选择的观察态） |
| `unavailable`（不可用） | `findMwPy()` 空；spawn ENOENT/异常；超时（默认 20s 硬墙，`DEFAULT_TRIAGE_TIMEOUT_MS` triage-client.ts:38）；子进程 exit≠0（含 Python 侧 `DecisionInputError` exit 2，decision.py:138）；stdout 非 JSON；`available!==true`；答案形状坏（3a 答案无 `path:line` 引用 / 3b 预消化无选项） | 归一化为 `available=false, reason=…`（:254-259 同款），走原 NC 路径 |
| `low-confidence`（低置信） | `confidence_source !== "api"` → 置信**不参与门控直接上抛**（spec §7.2 硬规则 + `confidenceSourceLabel` triage-client.ts:318-322"不用于门控"）；或 `confidence_source=api` 但 `confidence < min_confidence`（建议默认 0.7，放 `.mw/decide.json` 传输配置，非授权表字段）；3c 本地匹配得分 <0.6 → 不调 jev 直接按此值上抛 | 走原 NC 路径 |
| `input-incomplete`（输入缺失） | `lastAssistantText` 为空（NC 来自纯 placeholder 产物，没有可分类的问题）；taskKey/taskDir 解析失败；脱敏+bound 后仍超 `max_state_bytes`（Python 上限 16384，decision.py:244；spec §5.4 目标 ≤2000）；必需字段（问题文本/出处）缺失 | **TS 侧拒发**（spec §5.4"必需字段缺失 → TS 侧拒发 + 上抛人"），零 spawn |

### 4.3 不重复问、不丢失原问题

- **不重复问（对人）**：升级路径写出的 `## Questions` 与现状逐字节相同——人只会被问一次、问的 就是原问题；3b 的预消化问题只**追加在原文之后**（原文仍是首行，保住 `readTerminalDetail` 首行契约 :688）。
- **不重复问（对 jev）**：① 进程级 `dp3Attempted` 预算 =1：一次 run 内至多一次自动应答；答后再次 NC 说明答案没解决问题（多半是意图层问题），第二次**不再问 jev**、直接原路径转人（这也把"循环澄清"的爆炸半径钉死为 1 轮 followUp）；② trigger_id 幂等（spec §6.1：同一 trigger_id 只允许一行 decide，`decision_id = "dp3-worker-clarify:<task_key>#nc<N>"`）兜底双 PM 窗口/重放场景。
- **不丢失**：原问题在 `## Summary`（lastAssistantText 全文）与 `## Questions` 首行双处保留；降级时档案行冗余携带 `questions_digest`（hash）即可对账，绝不用预消化文本替换原文。

---

## Q5 dp2 checkpoint：结构化输入与注入点

### 5.1 文本行 → 结构化输入（解析哪些字段）

生产格式两处：`appendCheckpoint`（output-writer.ts:655-681，write 角色）与 `appendLandingCheckpoint`（worker-mode.ts:3335-3359，writeless 角色，多 4 个 landing 后缀）；解析器**已存在**：`CHECKPOINT_LINE_RE`（shared/heartbeat.ts:95-96）→ `CheckpointInfo`（:30-60：ts/elapsedS/reads/writes/phases/uniqTargets/repeatTop/risk + 可选 land/lastLandingS/artifactPresent/progressDone），`readTaskProgress(taskDir).checkpoint` 取**最后一条**。dp2 输入构造（TS 侧组装，全 L0/L1，≤2KB canonical JSON）：

```
dp=dp2-checkpoint-split, trigger=<task_key>#ckpt
task_key, task_type/role            （task.md 头，L0）
risk, elapsed_s, budget_s           （budget=task.md timeout 头 / PI_WORKER_TIMEOUT_MS / 60m 默认，worker-mode.ts:232-239）
reads, writes, uniq_targets, repeat_top, phases   （CheckpointInfo 直取）
trend: 最近 ≤3 条 [CHECKPOINT] 的 (elapsed_s, reads, writes)   （trace.log 再扫，判断是否还在爬）
self assessments: progress.md 中 CKPT converging=yes|no 计数（[machine] 行剔除，PROGRESS_DONE_RE 同源 :383-384）
last_action: 最后一条 [TOOL] 行（截断、仓相对，L1）
question: action ∈ {wait, narrow, split, direct}
```

60 条 mid/high 的语料事实：142 条 `[CHECKPOINT]` 中 risk=mid 36 + high 24（inventory Q2）；实际 PM 唤醒数 ≤60（`escalated` 按任务去重 :1582-1584，inventory 残留项已注明"无落盘唤醒计数"——dp2 档案行正好补上这个盲区）。

### 5.2 升级动作候选与 auto/人 边界（按 spec 四问判据：①可逆 ②机器可判 ③局部 ④无代价承诺）

| 动作 | ① | ② | ③ | ④ | 归属 |
| --- | --- | --- | --- | --- | --- |
| **收窄 narrow**（对 running worker 注入收窄 steer，模板复用 `checkpointSteerText` :206-224 的收窄段） | ✔ 一次重派内可撤回 | ✔ risk/trend/自评即判据 | ✔ 只影响本任务方向 | ✔ 零新成本 | **mode=auto 可执行**（含弱形式"继续等待到 deadline steer"——deadline steer 本就自动 :3455-3467） |
| 拆 split（终止并分拆重派） | 半 | 弱（拆几份、按什么边界= PM 的 key 级上下文） | ✘ 外溢到任务账本/新派发 | ✘ 新 run=token 成本 + 队列写 | **必须人**（PM 权威） |
| 直执 direct（PM 亲自做） | — | — | ✘ 绕过 worker 进程/写面隔离 | ✘ | **必须人** |
| （候选）wait | ✔ | ✔ | ✔ | ✔ | auto 可选（等价于"本次不升级"，与低风险分支同效） |

### 5.3 注入点精确改法（`pm/pm-orchestrator.ts:1658-1690`）

现状：`:1674 const ck = readTaskProgress(...)?.checkpoint` → `:1675 if (!ck || ck.risk === "low") continue` → `:1676 escalated.add(entry.taskKey)` → `:1683 deliverPmAlert(pi, "[mw] 发散风险：…继续等待 / steer 收窄范围 / 终止并分拆重派 / PM 直执…")`（`triggerTurn:true` 唤醒 PM 主窗，:199-208）。改法（插在 :1676 与 :1683 之间，`escalated.add` 保持"全分支先记账"→ 每任务每会话至多一次的界不变）：

```ts
escalated.add(entry.taskKey);
const dp2 = decideDp2CheckpointSplit({ projectDir, taskKey: entry.taskKey, ck, trend, taskDir, budgetS }); // never-throw
if (dp2.acted && dp2.action === "narrow") {
  writeWorkerSteerRequest(taskDir, dp2);   // 新传输面：<taskDir>/steer-dp2.md（单写者=PM 进程；worker 消费后改名/删除）
  displaySummary(pi, `[mw] dp2 已自动收窄 ${entry.taskKey}（decision_id=${dp2.id}，risk=${ck.risk}）；` +
    `worker 将在下一个检查点 tick 注入收窄 steer。如需改判：手动处置或 mw decide dp off dp2。`);
  continue;                                 // 不花 PM agent turn（displaySummary 无 triggerTurn，:190-197）
}
// split / direct / wait-不适用 / 四类降级 → 原告警字节不变
deliverPmAlert(pi, `[mw] 发散风险：…`);      // :1683 原文
```

worker 侧消费（唯一新增 worker 代码）：checkpoint tick（`writeCheckpoint` :3363 / `scheduleCheckpoint` :3446，≤10m 一次）检查 `steer-dp2.md` 存在 → `sendUserMessage(收窄 steer, {deliverAs:"followUp"})` → 原子消费（rename），`[mw dp2-narrow]` 前缀归因。文件传输符合 goal.md"文件驱动的去中心化协调"约束；备选方案（在 worker `writeCheckpoint` 内直接 decideFor(dp2)）省掉 ≤10m 延迟与新传输面，但把决策点移出了卡片钉住的 pm-orchestrator 锚点、且 PM 失去集中审计点——不推荐。

时延注记：自动收窄最迟在下一个 checkpoint tick（≤10m，`CHECKPOINT_REFRESH_MS` worker-mode.ts:244）生效；若需要更快，可把轮询加密到 60s（独立可调，不影响语义）。

### 5.4 "不破坏现有 triggerTurn 语义"的验证办法

`triggerTurn` 语义 = 终态回读/升级告警必须能唤醒 idle PM（ui-bridge.ts:193-208 注释）。验证四条（stub `pi.sendMessage` 捕获调用的单测 + 一条真会话 smoke）：
1. **旁路不变**：policy off / `unavailable` / `low-confidence` / 答案=split|direct 时，`sendMessage` 恰好一次且 `{triggerTurn:true}`、文本与现告警逐字节一致（快照断言）——"降级=现状"由此锁定；
2. **acted 路径**：answer=narrow 时 `sendMessage` 一次且无 `triggerTurn`（displaySummary 形态）+ steer 文件落盘含 decision_id；transcript 仍有记录（PM 下一 turn 可见，不丢知情权）；
3. **一次界**：同一任务连续两个 mid/high checkpoint tick → 恰好一次 decide、一次投递（`escalated` 集在 acted 分支同样先 add）；
4. **所有权**：非本窗 watched/owned 的 running worker → decideFor 不被调用（所有权检查 :1666-1673 先于 dp2）。

---

## Q6 不可破坏的现有不变量（5 条，各配可测检查方法）

| # | 不变量 | 依据 | 可测检查方法 |
| --- | --- | --- | --- |
| 1 | **dp3 关闭 / `mode=suggest` 逐字节零行为差异**（AC-001/AC-015）：`decide-points.json` 无文件、行坏、`enabled=false`、`mode=suggest` 时，NC 产品的 output.md/run.json/`[END]`/告警与改动前完全一致 | spec §5.1、AC-015；triage-client D-007 complete-bypass 先例 | 黄金文件测试：stub `pi` + writeless 无产物任务驱动 `finishSuccess`，四组配置（无文件 / off / suggest / auto-unavailable）与改动前基线 fixture 逐字节 diff；另断言 off/suggest 分支 `runDecideMw` spawn 计数（off=0、suggest=1） |
| 2 | **PM 仍读到 `## Questions` 原文首行**（readback 契约） | ui-bridge.ts:677-694（needs-clarification → `## Questions` first line）、output-writer.ts:527 | 升级路径测试：`readTerminalDetail(taskDir,"needs-clarification")` === 原问题首句；3b 预消化文本只出现在首行之后（对全文做行序断言）；no-product 告警行 detail 不变 |
| 3 | **checkpoint 每任务（每 PM 会话）至多升级一次，且 triggerTurn 语义不破坏** | `escalated` Set（pm-orchestrator.ts:1582-1584, 1665, 1676）；Q5.4 | Q5.4 四条单测（旁路字节一致 / acted 无 triggerTurn / 双 tick 单 decide / 非所属不调用）+ 现有 diverge-escalation 测试全部保持绿 |
| 4 | **worker 仍能正常以 needs-clarification 终态结束**（AC-006/C5）：jev 四类降级、dp3 预算耗尽、答后仍未交付等路径下 exit 2 可达且四面一致（OS 退出/run.json/`[END]`/output.md 标记） | markOutcome :2675-2682、recordEnd :3717、launcher.py:976-1010 | 注入 `DecideRunner` stub 返回各降级类 → 断言 `run.json.status=="needs-clarification"`、`[END] exit=2`、`## Questions` 存在、no-product 告警照发；答后二次 NC → 不再调 jev 且终态四面一致 |
| 5 | **goal mtime 记录不受影响**（phase 机制与 dp3/dp2 正交） | `appendGoalCheck`（output-writer.ts:758-766）+ `goalMtime(meta.trueAgenticdocRoot)`（worker-mode.ts:3901-3904 附近 D-116 注释） | phased 任务 + dp3 auto-answer fixture：trace 中每个 phase 仍各有一条 `[GOAL_CHECK] phase=n goal_mtime=<真实 mtime>`（`goalMtime` 返回值非 0），`[PHASE] start/done` 序列与基线一致；dp2 narrow steer（followUp）不改变 `completedPhaseIdx` 推进 |

补充（度量面不变量，配合 Q3.3）：`nc_raw` 可复原——`[DECIDE] dp3 acted=true` trace 行 + decisions.jsonl `kind=decide` 行数一致（对账测试）；`mode=suggest` 样本计入 `nc_human`。

---

## 残留与未验证

- **卡片锚点 `worker/launcher.py:593` 失效**：该文件不存在；实际 launcher 为 `packages/multi-workers/launcher.py`，其 :593 是 `_read_task_md_fields` docstring（本报告按符号定位到 `_exit_to_status`:976-982 / `_reap_status`:985+）。其余卡片锚点全部实测吻合（worker-mode.ts:2681/:3619/:3824/:243-244/:3348、heartbeat.ts:96、output-writer.ts:666-680/:505-528、pm-orchestrator.ts:1498/:1658-1690、triage-client.ts:132/:169）。
- **3c 会话历史级的实测命中率未统计**：本仓 42 条 NC 的原问文本与四个来源的匹配得分分布未回放（需实现 matcher 后跑离线语料）；"相当部分可自答"是 inventory 的定性结论，量化比例未验证。
- **dp2 自动收窄的收益未量化**：60 条 mid/high 的实际 PM 唤醒数无落盘计数（`escalated` 为进程内存）；`steer-dp2.md` 文件传输面为新机制，跨平台原子消费（Windows rename 语义）未做原型验证。
- **jev 对 3a 事实题的真实答对率无本地数据**：triage-decisions.jsonl 不存在（DP-1 本仓零调用），`min_confidence=0.7` 阈值是建议默认，需 mode=suggest 灰度期校准。
- **pi 会话 JSONL 的 `[mw dp3-answer]` 前缀过滤**：spec §7.2 引用的 `session-manager.ts:29-35,474-480` 未逐行复核（本任务未读该文件）；度量脚本侧实现时需确认 user 消息条目可按内容前缀区分。
- 行号为 2026-10-19 快照，后续提交会漂移；引用时按符号名复核（spec 坑点表同款警告）。

## 上下文来源

- 源码（全部整读或逐行核对）：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（全文 4094 行）、`worker/output-writer.ts`（全文）、`shared/heartbeat.ts`（全文）、`shared/deliverable-evidence.ts`（全文）、`pm/pm-orchestrator.ts`（全文 2026 行）、`pm/triage-client.ts`（全文）、`pm/ui-bridge.ts`（:150-250、:655-735 区段）、`worker/output-sections.ts`（:48-67 契约段表）
- Python 侧：`packages/multi-workers/launcher.py`（:960-1010）、`mw_common.py`（终态集合 :168/:2131/:2597）、`decision.py`（:15-244）、`decision_backends.py`（:4-124）
- 本 key 文档：`.agenticdoc/mw-decision-substitution/spec.md`（全文，§4.1 三切 / §5.3 执行面 / §5.4 输入契约 / AC-003/004/005/015）、`pm-state.md`（§5 Decisions DS-1..13）、`evidence/research/spec-decision-inventory-20261016.md`（Q2/Q3/Q5/替换优先级：42/242、142 条 CHECKPOINT、mid36+high24、escalated 去重）
- 任务卡：`tasks/D3-dp3-dp2-execution.md`（sha256 `8afaea1b…`，envelope producer agent-team-loop-pm@0.83.0）

Q-answered: 6/6
