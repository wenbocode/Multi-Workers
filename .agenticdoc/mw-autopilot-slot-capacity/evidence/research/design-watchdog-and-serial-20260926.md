# Design: idle 看门狗与 per-key 串行化的设计面（D7 / msc-d7-watchdog-and-serial）

> key: `mw-autopilot-slot-capacity` · 阶段：DESIGN 期调研（**只读**，未改代码、未改任何账本、未答 gate、未 commit）
> 唯一写面：本文件。行号快照：2026-09-26 工作树（`conductor.py` 174500 B、`launcher.py` 47583 B、`mw_common.py` 144421 B、TS `agent-team-loop/**`）
> 上游输入：`spec.md`（AC-005/AC-008/AC-013/AC-014/AC-021、风险 4/7/8）、`evidence/research/spec-capacity-constraints-20260926.md`（RQ-2）、`evidence/research/spec-worker-serialization-20260926.md`（RQ-5）
> 时间戳按 UTC（`trace.log` 用 `...Z`）。所有实测数字给出复算方式（§调研方法与出处 4）。

## TL;DR

1. **idle 误杀的真因不是"长推理"，是"长 bash 无输出"**：全量复算得 **24 次**机器判死（5 个项目 / 2026-09-19…09-26）；**23/24 的最后一次活动 = `tool_execution_start` 一次 `bash`**，其中 **22 次在判死时刻 `lastActivityAt == lastToolAt`**（即 bash 仍在跑、期间零 `tool_execution_update`）⇒ 判据只认"事件"，而 bash 的 update 是**输出驱动**（无新输出即零事件，`bash.ts:200/371-414`）。阈值余量分布 **601–622s，超出 600s 仅 1–22s**（全是越线后的第一个 30s tick）。
2. **判别信号已在盘上**：`output.md` 的 `## Exit Reason` 已含 `(last delta Xs ago, last tool Ys ago)`；`last tool == idle` 就是"判死时工具在飞"的机器判据。**不需要 LLM 判断**。⇒ 修法首选 **D（结构化 kill 证据）+ B（in-flight tool 分类判定）**，A（抬阈值）单独不推荐，C（二次确认）作为 B 的"无工具在飞"分支兜底。
3. **`worker_timeout_min` 是静默空操作**：`packages/multi-workers/autopilot/**` 内仅 `config.py:18/54/72` 出现（定义/默认/范围），dispatch/conductor/launcher 零命中；真正的墙钟链是 task.md `timeout:` > `PI_WORKER_TIMEOUT_MS`（全仓无写者）> 60m，而 `render_task_md`（`dispatch.py:262-331`）不渲染 `timeout:` ⇒ **conductor 派发的 worker 恒为 60m**。首选 **(i) 接线**（渲染 task.md 头），不动键集合即不动 parity 语料。
4. **per-key 串行是硬顺序，且本 key 不应放开**：三重保证复核成立（`conductor.py:258-264` + `:287-288` + `_advance_key:908-1015` 每分支单派）。放开的硬前置"写面声明→机器可读→重叠拒绝"**机器判定为零**（生产代码 `write_scope|写面` 零命中），三个逃逸口都未修。证据：autopilot 路径每 key 峰值恒 1（RQ-5：429/431），而 PM 手工路径峰值 6。⇒ **本 key 只做可观测与判据（拦截面设计落地为"检测信号 + VC"），不做放开**。
5. **归属缺口（AC-021）实测存在三套口径**：conductor = 前缀 OR path（`conductor.py:2135-2138`）、面板 = 仅前缀（`monitor.ts:509-513`）、`mw.py` = 仅 path（`mw.py:1801-1820`）。实测分歧：**E2 54/491 行、FM 106/236 行**两侧判定不一致；**6 行带 `ap-` 前缀但 task.md 无 `origin: conductor`**（E2 5 + JCodingAss 1）⇒ 前缀归属是假信号。推荐 **行级 `origin` 列（由写者代码路径写，不读 task.md）** + 旧行按 path 兜底读取。

## 决策问题

1. **(AC-005 / c2) idle 看门狗**：现状参数与"无活动"定义在哪（`file:line`）；24 次误杀的**每次活动特征与阈值余量**能否复算；修法有几种、各自 pros/cons；怎样证明"新方案减少误杀且不放过真挂死"。
2. **(AC-005) `worker_timeout_min` 死键**：现状锚点 + "无消费者"的证明；修法选型（接线/删除/标注）；若动键集合的两侧镜像与 parity 语料影响。
3. **(AC-008/AC-014 / d) per-key 串行化**：三重结构保证的锚点复核与"硬顺序 vs 可并行"判定；若未来放开，写面声明→机器可读→重叠拒绝的设计面（字段/写入点/判定算法/锁）；三个逃逸口（PM 手工通道、行提前终态化、xkey 提案通道）逐个的拦截面与可检测信号；**本 key 是否执行放开**。
4. **(AC-021) 归属缺口**：`_workers.parallel` 无 writer 列 ⇒ 归属方案选型 + pros/cons + 两侧镜像面；与面板/conductor 口径收敛的关系。
5. **VC 候选**：≥3 条机器可判 VC。

不做：给出具体阈值取值（属 RQ-4/PM 决策）、实测高并发对照（本卡无新采样权限）、实现代码。

## 调研方法与出处

1. 已读上游笔记：`spec-capacity-constraints-20260926.md`（RQ-2）、`spec-worker-serialization-20260926.md`（RQ-5）、`spec.md` §1.1.1/§4/§5、`H:\git\E2Feature\.agenticdoc\_autopilot\reflect\worker-idle-timeout.md`。
2. 本次走读的源码锚点（read/grep，全部按行段）：`worker/worker-mode.ts` 140-200 / 740-1070、`worker/output-writer.ts` 1-80 / 150-270、`core/tools/bash.ts` 195-420、`extensions/agent-team-loop/rag/budget.ts` 250-285、`agent/src/agent-loop.ts` 660-715、`autopilot/conductor.py` 40-60 / 240-300 / 900-1020 / 1050-1110 / 1570-1620 / 1720-1740 / 2120-2160 / 2860-3045、`autopilot/config.py`（整文件）、`autopilot/dispatch.py` 240-340 / 400-470、`launcher.py` 775-860、`mw_common.py` 1432-1580、`autopilot/status-model.ts` 60-180 / 240-310、`pm/pm-orchestrator.ts` 350-500、`pm/task-dispatcher.ts` 230-310、`shared/worker-store.ts`（整文件）、`autopilot/monitor.ts` 470-560。
3. 只读现场数据（未写入任何文件）：三 + 二项目 `.agenticdoc/*/workers/*/{output.md,trace.log}`（E2Feature / Multi-Workers / JCodingAss / FeatureMigrator / OverCode）、`_workers.parallel`、`_autopilot/config.json`、`_autopilot/reflect/*.md`。
4. **复算方式（唯一口径，脚本在 `%TEMP%\rq7\*.py`，跑完即删）**：
   - 误杀集合：`glob .agenticdoc/*/workers/*/output.md`，正则 `idle timeout: no activity for (\d+)s`；同时抓 `idle timeout: (.*)` 取 `last delta/last tool` 尾串。
   - 每次死亡的最后活动：同目录 `trace.log` 的 `[TOOL] <iso> <name> <target>`（**必须 `re.M` + 容忍行尾 `\r`**，全集用 `findall` 取最后一条）、`[TIMEOUT] <iso>`、`[HEARTBEAT] <iso>`、`[END] … elapsed=<n>s`。
   - 判死时刻并发：解析全部 `trace.log` 的 `[START]`/`[END]` 区间（1143 个 session，5 项目），在死亡时刻做区间计数扫描（排除自身）；口径与 RQ-5 一致（`[END]` 可能与上一行粘连，全文 `re.search`）。
   - 归属对账：按行解析 `_workers.parallel`（7/8 列容忍），比较 `task_key.startswith(f"ap-{key}-")` 与 `task_path` 含 `.agenticdoc/{key}/workers/`，再读对应 `task.md` 的 `^origin:\s*(\S+)`。
   - 重试结果：同 key 下同 base stem 的兄弟目录 `trace.log` 取第一个 `[END] … exit=`。
5. **方法学红线（必须随数字一起读）**：所有 `idle_s` 都落在 601–622s，这是**阈值截尾**——任何 >600s 的命令都会被在越线后 ≤22s 处杀掉，所以 `idle_s` 分布**不能**用来估计"bash 运行时长的真实分布"，也不能推出"抬到多少才够"。

## 发现

### 1. idle 看门狗（AC-005）

#### 1.1 现状锚点与"无活动"的定义

| 项 | 值 / 位置 |
|---|---|
| 阈值常量 | `DEFAULT_IDLE_MS = 10 * 60_000`（`worker/worker-mode.ts:148`） |
| 阈值来源（为何是 600s） | 同处注释：`Conservative — above the 7m legit single-generation observed on glm-5.3 (cpr-003)`（`:143-147`）⇒ 600s 的**唯一出处是单次观测的经验值**，不是负载模型 |
| env 覆盖 | `resolveIdleMs(process.env.PI_WORKER_IDLE_MS)`（`:163-167`），读取点 `:895`；`PI_WORKER_IDLE_MS` 在 `packages/multi-workers/**` **零写者**（仅 README/UPDATE 提到），故生产实际生效值恒为 600s（与 `worker-idle-timeout.md` 的实测一致） |
| 判定 | `idleTimer = setInterval(…, 30_000)`（`:1022-1033`）：`idleForMs = Date.now() - lastActivityAt`（`:1024`）；`if (idleForMs < idleMs) return;`（`:1025`）；否则 `timeoutExit("idle", …)`（`:1029-1032`） |
| 死亡留痕 | `timeoutExit`（`:911-937`）→ `appendTimeout`（`:915`）写 `[TIMEOUT] ts idle: <detail>`（`output-writer.ts:170-172`）→ `writeOutputGuarded(exitCode=1, exitReason=…)`（`:920-927`）落 `## Exit Reason`（`output-writer.ts:62-63`）→ `recordEnd(1)`（`:929`）写 `[END] … exit=1 elapsed=… tools=…` → `killTrackedDetachedChildren()` + `process.exit(1)`（`:931-937`） |
| detail 串 | `no activity for ${idleForMs}s (last delta ${d}s ago, last tool ${t}s ago)`（`:1031`）——**这就是机器可判的活动特征** |

**"无活动"= 以下三类信号全部静默**（三类都只做一件事：`touch()` 把 `lastActivityAt = Date.now()`，`:800-802`）：

- **token 增量（唯一能区分"慢生成"与"死连接"的信号）**：`pi.on("message_update", …)`（`:803-806`）——**唯一**同时写 `lastDeltaAt` 的地方（`:805`）。
- **工具事件**：`tool_execution_update`（`:812`）、`tool_execution_end`（`:813`）走 `touch`；`tool_execution_start`（`:825-830`）是**唯一**写 `lastToolAt` 的地方（`:829`）。
- **turn / message / agent 边界**：`message_start`（`:807`）、`message_end`（`:808`）、`turn_start`（`:809`）、`turn_end`（`:810`）、`agent_start`（`:811`）、`agent_end`（`:849-850`）。

⇒ **判据里没有"工具是否仍在执行"这一维**。`tool_execution_start` 之后，是否有事件只取决于**工具自己愿不愿意发 update**。
#### 1.2 误杀复算（24 次，逐次活动特征与阈值余量）

口径：`output.md` 含机器判据 `idle timeout: no activity for <N>s`。**数据可得**（不是推算值），全集 **24 次**、5 个项目、2026-09-19T08:15Z … 2026-09-26T06:11Z。RQ-2 报的 **14 次**是 E2+MW 在 09-20…09-25 窗口的窄口径；本卡扩到 5 项目/全量产物后为 **24 次**（其中 E2 14、FeatureMigrator 5、OverCode 4、Multi-Workers 1）。

| # | key | task（尾段） | idle_s | 余量 (idle−600) | 最后 tool 名 | 工具起→判死 (s) | 判死时并发 |
|---|-----|--------------|-------:|-----:|------|------:|-----:|
| 1 | skill-system-core | skill-system-core-audit | 612 | 12 | bash | 612 | 1 |
| 2 | slicing-algorithm-spec | verify-spec-design-fixes | 607 | 7 | read | 839 | 4 |
| 3 | rag-quality-gate | t003-migration | 607 | 7 | bash | 1235 | 2 |
| 4 | rag-quality-gate | t005-first-run | 612 | 12 | bash | 612 | 0 |
| 5 | slicing-algorithm-spec | t016-t017-e2e-closeout | 606 | 6 | bash | 606 | 1 |
| 6 | mw-rag-integration | mw-rag-t11-verify | 613 | 13 | bash | 613 | 2 |
| 7 | loop-state-single-writer | lsw-002-tool-observability | 601 | 1 | bash | 601 | 1 |
| 8 | feature-tier-a-closeout | 001-tier-engine-skeleton-k7-codes-params-single-source | 622 | 22 | bash | 622 | 1 |
| 9 | chroma-hnsw-poison-fix | chroma-t12-close-owned-heal | 610 | 10 | bash | 610 | 3 |
| 10 | feature-tier-a-closeout | repair-a1 | 611 | 11 | bash | 611 | 3 |
| 11 | feature-inline-marker-patchkit | spec-writer-a1 | 606 | 6 | bash | 606 | 2 |
| 12 | feature-sampling-human-channel | spec-writer-a1 | 607 | 7 | bash | 607 | 2 |
| 13 | feature-cigate-install-kit | design-writer-a1 | 602 | 2 | bash | 602 | 3 |
| 14 | feature-cigate-install-kit | design-writer-a2 | 608 | 8 | bash | 608 | 3 |
| 15 | gui-skeleton-shell | 004-shell-layers-and-frontend | 618 | 18 | bash | 618 | 2 |
| 16 | gui-skeleton-shell | 005-frozen-package-and-thresholds | 619 | 19 | bash | 619 | 6 |
| 17 | gui-skeleton-shell | 005-frozen-package-and-thresholds-a2 | 618 | 18 | bash | 618 | 3 |
| 18 | feature-cigate-install-kit | 012-ci-sandbox-e2e-injections | 614 | 14 | bash | 614 | 1 |
| 19 | feature-inline-marker-patchkit | 014-fm-budgets-evidence-closeout | 617 | 17 | bash | 617 | 7 |
| 20 | feature-gui-time-mvp-board | 001-board-params-config-errors | 613 | 13 | bash | 613 | 1 |
| 21 | feature-gui-time-mvp-board | 001-board-params-config-errors-a2 | 612 | 12 | bash | 612 | 1 |
| 22 | feature-false-meets-remediation | spec-writer-a1 | 605 | 5 | bash | 605 | 3 |
| 23 | feature-gui-time-mvp-board | repair-a2 | 606 | 6 | bash | 606 | 3 |
| 24 | chatbox-monitor-v2 | rq-a-mem-panorama | 603 | 3 | bash | 603 | 10 |

**统计（可复算）**：

- `idle_s`：min **601** / median **611** / max **622**；**余量 = idle_s − 600 ∈ [1, 22]s**，全部落在"越线后的第一个 30s tick"内。
- 最后 tool 名：**bash 23 / read 1**。
- **`工具起→判死` == `idle_s` 的有 22/24** ⇒ 判死时刻 `lastActivityAt == lastToolAt`，即**最后一次 touch 是 `tool_execution_start`，此后该 bash 全程零事件**。
- 余 2 次属于"工具已结束后的静默"，形态不同：
  - #3 `t003-migration`：工具起于 1235s 前、最后一次 touch 在 607s 前（工具已 `tool_execution_end`），随后 607s 无 delta/turn ⇒ 一次 ~628s 的 bash 结束后模型静默。
  - #2 `verify-spec-design-fixes`：最后 tool 是 `read`（839s 前），最后一次 touch 是 607s 前的 token delta ⇒ 纯生成/思考静默。
- **判死时并发**（本卡口径：5 项目 / 1143 session）：mean **2.71** / max **10**；分布 `{0:1, 1:7, 2:5, 3:7, 4:1, 6:1, 7:1, 10:1}`。RQ-2 的窄口径（3 项目/窗口）= mean **2.14** / max 3。⇒ 两个口径都支持同一结论：**误杀不依赖高并发**（横跨 0…10），因为根因是"命令无输出"而非"机器忙"。
- **后果**（`worker-idle-timeout.md` 的 12 次清单 + 本卡复核）：24 次中 **12 次的首个兄弟重试 `[END] exit=0`**、6 次重试仍非 0（**含同一 task 连死两次**：`cigate-design-writer a1/a2`、`gui-time-mvp-board-001 a1/a2`、`gui-skeleton-005 / -a2`）、6 次无兄弟目录（未重试）。文档记载的直接成本 ~10min/次，尾部成本 = "无槽位可重试 ⇒ key 延迟 ~1h" 与 "连死两次 ⇒ key stalled + 5–9h 人工等待"。
- **`tool_execution_update` 到底有没有？** #2/#3 之外的 22 次给出了否定答案：如果 bash 在静默窗口里发过 update，`lastActivityAt` 会晚于 `lastToolAt`，`工具起→判死` 会**大于** `idle_s`；实测两者逐秒相等。

#### 1.3 机制判定：为什么 bash 无 update（`file:line`）

- `bash` 工具的 update **不是时间驱动，是输出驱动**：`handleData` 收到子进程数据才 `output.append + scheduleOutputUpdate`（`core/tools/bash.ts:411-414`）；`scheduleOutputUpdate` 只置 `updateDirty = true` 并在 100ms 节流后调 `emitOutputUpdate`（`:392-401`，`BASH_UPDATE_THROTTLE_MS = 100`，`:200`）；`emitOutputUpdate` **首行就是 `if (!onUpdate || !updateDirty) return;`**（`:371-373`）。
- ⇒ **一条 600s 内一行标准输出都没有的命令（pytest 缓冲、长编译、慢计算、PowerShell `[Diagnostics.Stopwatch]` 沙箱、递归目录扫描）在事件流上完全隐形**。逐条复核 24 次里的最后一条命令，全部是这类长命令：`python -m pytest … | Select-Object`、`$sw=[Diagnostics.Stopwatch]::StartNew(); python -X utf8 tools/…`、`cd …; python -X utf8 .agenticdoc/…/worker…/probe*.py`、`& "…/bash.exe" -lc "cd /h/git/…"`、`Get-ChildItem -Recurse …`。
- **反向先例（现成的解法就在仓库里）**：RAG 工具用 `withHeartbeat`（`rag/budget.ts:257-280`）每 30s 主动 `onUpdate`，注释明写 "which refreshes the worker's activity watchdog (`worker-mode.ts` touch()), so a long `rag_chat`/retrieval cannot be mistaken for a hung process"（`:260-265`）。⇒ **bash 缺的正是同一个机制**，而不是阈值不够高。
- **因此 `worker-idle-timeout.md` 的根因表述需要修订**：该文档归因为"长读+长推理 / 单次超长生成"（并据此给出"拆 task / 禁止连续 5 分钟无工具调用"的处置阶梯）；本卡数据表明 **22/24 是"工具在飞"而非"无工具调用"**，"禁止 5 分钟无工具调用"对这类**无效**（worker 恰好正在进行工具调用）。
- 为什么"`slots 2/2`/并发"不是原因（回应 spec 风险 4）：阈值 600s 与余量 1–22s 是常量关系，与在飞 worker 数无关；任何 ≥600s 的静默命令都会在越线后 ≤30s 被杀。

#### 1.4 修法选型（≥2 方案 + pros/cons）

| 方案 | 内容与写入点 | pros | cons / 首个失败模式 |
|---|---|---|---|
| **A. 抬阈值** | `PI_WORKER_IDLE_MS`（env）或新增落盘键（`config.py`/`status-model.ts` 两侧） | 1 行改动；1 分钟见效 | 无判别力（601s 与 1800s 的命令一视同仁）；**阈值截尾 ⇒ 数据无法回答"多高才够"**；真挂死发现更晚；走 env 则 `P-015`（重启丢 env）；走新键则触发两侧镜像 + parity 语料重冻（AC-010/风险 16）。首个失败模式：下一个 20 分钟构建再次被杀 |
| **B. 分类判定（in-flight tool）** | `worker/worker-mode.ts`：在 `tool_execution_start`（`:825`）`toolInFlight++`/记 `inFlightTool`，在 `tool_execution_end`（`:813/841`）清零；`idleTimer` 分支（`:1022-1033`）改为：**有 in-flight tool ⇒ 不用 `idleMs`，用 `toolIdleMs`（新阈值，≥30m）或直接交给 wall**；无 in-flight tool ⇒ 维持 `idleMs`（死连接的判别力完整保留） | 直接命中 22/24 根因；不牺牲"死连接"判别（API 卡死时没有工具在飞）；`tool_execution_end` 在异常路径也保证触发（`agent/src/agent-loop.ts:684-712` 的 `acceptingUpdates=false` + finally），状态不会泄漏 | 需要第 2 个阈值（多一个配置面）；长命令会一直占到 wall ⇒ 占槽更久（2 槽项目被放大）；"idle 看门狗 = 资源护栏"的论点被削弱——**但该论点本就弱**：151 GB 事故的源是 idle kill 之后**存活的 detached 子进程**（`worker-tree-kill` 笔记 + CHANGELOG），真正的护栏是 `killTrackedDetachedChildren()`（`worker-mode.ts:931-937`），不是 idle 判据 |
| **C. 二次确认 + 冷却** | 同文件：第一次越线只 `appendTimeout`-类 `[WATCHDOG] suspect` 记一行（并可选 `sendUserMessage` steer），**继续观察 X 分钟**；第二次仍无活动才杀 | 对"恰好卡在边界的慢模型/慢命令"友好；零阈值语义变更；真挂死的发现时间只延后 X | 真挂死晚 X 分钟被发现；只能救回 X 窗口（本例余量 1–22s，X=30s 即可"救回 24/24"——**这是截尾的必然结果，不能当作收益证明**）；需要每 tick 由内存状态重推（watchdog 本就在 worker 进程内，不违反 GC-1） |
| **D. 只补结构化证据（不改判据）** | `timeoutExit`/`output-writer.ts:170`：把 `tool_in_flight=<name>`、`silence_s`、`last_tool_target`、静默窗内 heartbeat 数写入一条**机器行**（如 `[IDLE_KILL] tool_in_flight=bash silence=612s`） | 零行为风险；把"误杀率"变成可观测指标（现在只能靠字符串解析 `last tool == idle`）；为 B/C 上线提供基线 | 不减少误杀；新事件/新行需两侧（`EVENT_TYPES`/parity）对齐（AC-022 D3 家族） |

**建议组合：D 先落地（拿到机器可判的误杀指标与基线）⇒ B 做分类判定 ⇒ C 作为 B 的"无 in-flight tool"分支兜底。A 不单独采用**（若要 A，必须与 B 同时：A 只放宽"有工具在飞"那一支）。

#### 1.5 判据与反例（如何证明既减少误杀又不放过真挂死）

收益判据（机器可判）：

- **M1**：`count(idle kills where tool_in_flight != none) == 0`（上线后 14 天窗口）。基线可复算：24 次中 **22 次**满足"`工具起→判死` == `idle_s`"，即 `tool_in_flight != none`。
- **M2 历史回放**：用新判据重放 24 个死亡点 ⇒ ≥22 个不再触发 idle 判死；其余 2 个（#2/#3，无工具在飞）属于"慢生成/工具后静默"，只有加 C 才会被豁免。**回放脚本即是 §调研方法与出处 4**（不需要新数据）。
- **M3**：`wall` 击杀占比不因本改动而下降（wall 才是预算护栏）；`idle` 击杀占比下降。两者都从 `[TIMEOUT]` 行统计。
- **M4**：≥1800s 的命令在改动后仍能被 wall 收敛（`[END] elapsed≈budget`），且不留孤儿进程（`killTrackedDetachedChildren` 已被 wall 分支复用，`:1036-1041` → `timeoutExit("wall")`）。

反例（缺一不可，全部可自动化）：

- **T1 真挂死仍被杀**：合成任务无任何事件、无工具在飞，阈值 60s ⇒ 必须仍产出 `idle timeout: no activity for 60s`（现有测试 `coding-agent/test/extensions/agent-team-loop.test.ts:4218-4230`，改动后必须保持绿）。
- **T2 长 bash 不被 idle 杀、但被 wall 杀**：合成 `bash` 命令运行超过 idle 阈值 ⇒ 新判据下**不得**产生 idle 击杀；把 wall 调小 ⇒ 必须产生 `wall timeout: budget 120s exceeded`（对应 `agent-team-loop-worker-tree-kill.test.ts:149-160`）。
- **T3 token 流必须续命（含工具在飞期间）**：现有 `t-stream`（`agent-team-loop.test.ts:4246`）保持；**新增**：in-flight bash 期间每 30s 到达的 `tool_execution_update` 也续命（`rag/budget.ts:257-280` 已证明该路径可跑通）。
- **T4 阈值必须可落盘**：若引入 `toolIdleMs`，必须走 `_autopilot/config.json` 两侧镜像（AC-010/P-021），不得只用 env（P-015）。
- **T5 状态不泄漏**：in-flight 计数必须在 `tool_execution_end`（含异常）与进程退出路径上归零；反例 = 构造一个 `tool_execution_start` 后立刻 `agent_end` 的场景，断言计数为 0。

### 2. `worker_timeout_min` 死键（AC-005）

#### 2.1 现状锚点 + "无消费者"的证明

| 项 | 位置 |
|---|---|
| 键定义（文档串） | `autopilot/config.py:18`（`worker_timeout_min int 30`） |
| 默认值 | `config.py:54`（`"worker_timeout_min": 30`） |
| 取值域校验 | `config.py:72`（`(1, None)`，即 ≥1 无上界） |
| TS 镜像 | `status-model.ts:81`（接口字段）、`:108`（默认）、`:138`（`INT_RANGES`）、`:257`（`EFFECTIVE_KEYS` union）、`:273`（`intOf`）、`:298`（`readConfig` 组装） |
| 文档 | `multi-workers/README.md:228`（`worker_timeout_min \| 30 \| worker 墙钟兜底超时`） |

**无消费者的证明（grep 全仓源码）**：

```
grep -rn "worker_timeout_min" packages/**/*.{py,ts}   # 排除 dist/ test/ fixtures/
→ multi-workers/autopilot/config.py:18,54,72            # 仅定义 + 默认 + 范围
→ coding-agent/.../autopilot/status-model.ts:81,108,138,257,273,298   # 仅 schema/镜像/组装
→ （无第三方消费者）
grep -rn "worker_timeout_min" packages/multi-workers/autopilot/   → 仅 config.py 三处
```

- **Python 侧**：`dispatch.py` / `conductor.py` / `launcher.py` / `mw_common.py` **零命中**；`render_task_md`（`dispatch.py:262-331`）不渲染 `timeout:` 头；`launcher._build_env`（`launcher.py:223-323`）不注入 `PI_WORKER_TIMEOUT_MS`。
- **TS 侧**：`status-model.ts` 把它并进 `AutopilotConfig` 对象后**没有下游 read**——`worker-mode.ts` 的 `resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS)`（`:894`）只认 task.md 头与 env。
- **真正的墙钟链**（`worker-mode.ts:154-160`）：task.md `timeout:`（分钟，解析于 `:275-277`）> `PI_WORKER_TIMEOUT_MS`（`:155-159`）> `DEFAULT_BUDGET_MS = 60m`（`:143`）。而 `PI_WORKER_TIMEOUT_MS` 在 `packages/multi-workers/**` **零写者**（仅 README 描述）⇒ **conductor 派发的 worker 恒为 60m 墙钟**，与 `config.json` 里写的任何 `worker_timeout_min` 无关。RQ-2 的实测佐证：E2 `config.json` 写 30 而 4 个 worker 的 `[END] elapsed=3600s` 恰好命中 60m。

#### 2.2 修法选型

| 方案 | 改动面 | pros | cons |
|---|---|---|---|
| **(i) 接线（推荐）** | `dispatch.render_task_md` 新增可选参数并渲染 `timeout: <min>`（`dispatch.py:262-331`，取值 `cfg["worker_timeout_min"]`，注意 effective_config 的"空值即未决定"）；TS 侧 `dispatchTask`（`task-dispatcher.ts:284-300`）在写 task.md 时写同一头 | 与既有优先级一致（task.md 头最高）；**逐任务可见、可复算**；**不动键集合 ⇒ 不动 parity 语料**；消灭静默空操作 | 改动 `render_task_md` 会改既有 task.md 渲染语料（幂等重渲染会覆盖旧 task.md）⇒ 需要 `[推断]` 核对是否有测试断言 byte-identical 渲染；两侧必须同头，否则 PM 派发与 conductor 派发墙钟口径不同 |
| **(ii) 删除键** | `config.py`（docstring/default/_INT_RANGES）+ `status-model.ts`（接口/默认/范围/union/readConfig）+ README + `test_autopilot_config.py:55` + `autopilot-config-corpus.json`（`:390`/`:542`） | 彻底消灭死键 | **fail-closed 会炸现存项目**：`validate_config` 对 unknown field 直接 `ConfigError`（`config.py:73-76`），而 FM/E2 的 `config.json` 已材料化 13 键（含 `worker_timeout_min`）⇒ 删键后 autopilot 直接停摆，需要一次性迁移所有项目文件 + 重冻 parity 语料 |
| **(iii) 保持现状 + 显式标注无效** | README 一行 + `config.py:18` docstring 标 `RESERVED (no consumer as of vX)` | 零代码风险 | 保留一个"看起来改了其实没改"的静默空操作（spec 风险 5 家族），且没有机器判据能发现它 |

**建议：本 key 选 (i)**；(ii) 只在同时做项目文件迁移时才有意义；(iii) 是可接受的降级但必须有机器可判的标注（见 VC-3）。

#### 2.3 两侧镜像与 parity 语料影响

- **若只做 (i)（读现有键 + 渲染 task.md 头）**：**键集合不变** ⇒ `DEFAULT_CONFIG`/`INT_RANGES`/`EFFECTIVE_KEYS` 两侧无需改；`autopilot-config-corpus.json` 的 53 例冻结 sha **不动**；`mw autopilot verify set/show/clear` 的 CLI 面不动。需要两侧同改的只有"渲染 task.md 的 `timeout:` 头"这一条（Python `render_task_md` + TS `dispatchTask` 的 task.md 写入路径）——P-021 要求两侧都跑 verify。
- **若做 (ii) 删键**：`config.py` 与 `status-model.ts` 逐字段一致地删；`autopilot-config-corpus.json:390`（`{"enabled": true, "worker_timeout_min": 45}`）与 `:542`（`partial-key-worker_timeout_min`）两例必须移除/改造并**重冻**；FM/E2/JCodingAss 的 `config.json` 需一次性迁移（`EFFECTIVE_KEYS` 判定 + 机器层覆盖）；`EFFECTIVE_KEYS` 是编译期 union（`status-model.ts:257`），漏改即 TS 编译错（好事）。
- **若做 (iii)**：改 README + docstring 即可，但应在 `config.py` 加一条测试断言"该键无消费者或已被标注"（VC-3），否则标注会再次漂移。
- **共性约束**：`worker_timeout_min` 与 `PI_WORKER_IDLE_MS`/`PI_WORKER_TIMEOUT_MS` 是三个不同层（键 / env / task.md 头）。P-015：env 参数不落盘，重启路径不同即丢；若最终要让阈值可控，**只有落盘键或 task.md 头是可信的**。

### 3. per-key 串行化（AC-008/AC-014）

#### 3.1 三重结构保证的锚点复核与"硬顺序 vs 可并行"判定

**结论：A. 硬顺序**（复核 RQ-5，本卡逐条读原文确认）：

| # | 保证 | 锚点 | 判定 |
|---|------|------|------|
| 1 | `in_flight_keys` = 「该 key 名下存在任意非终态行」，**`pending` 也算** | `conductor.py:258-264`（集合推导）；`_is_in_flight` = `status not in mw_common._TERMINAL_STATUSES`（`:2131-2132`，终态集 `{done, failed, needs-clarification}` `mw_common.py:158`）；`_row_belongs_to` = 前缀 OR task_path（`:2135-2138`） | 硬 |
| 2 | 派发循环对该 key 直接跳过 | `if key in in_flight_keys: continue  # wait for the in-flight worker`（`:287-288`） | 硬 |
| 3 | `_advance_key`（`:908-1015`）**每个分支只派 1 个后立刻 return** | phase-writer `:935-941`、L2 fix-writer `:970-979`、L2 verifier `:1006-1011`；loop 层再各自确认：`execute_loop` 的 `if any(_is_in_flight(r) for r in fam): return False  # per-key serial: wait for the in-flight task`（`:1095-1096`）、`_verify_loop` 的 `for prefix in (f"ap-{key}-l3-", f"ap-{key}-repair-"):` + `return False`（`:1600-1602`）、repair family 判定 `:1730-1734` | 硬 |

**为什么这是"硬"而不是"策略保守"**：#1+#2 意味着**即使把 `max_parallel_keys` 调到 100、把 deps/相位/budget 全部放开**，只要该 key 有 1 个非终态行，`_advance_key` 就不会被调用。⇒ 单 key 并发不是"没配"，而是队列表驱动的布尔互斥。

**"可并行"的一层**：launcher 消费侧**完全没有** per-key 限制——`_poll_once`（`launcher.py:775-841`）遍历**全部** `status == "pending"` 行、不按 key 分组、`_spawn` 非阻塞（`:966-967`），一轮 poll 把当轮所有 pending 全拉起；`--max-workers` 是唯一 opt-in 上限且默认为 `None`（`:837`，`launcher.py:1021`）且**不落盘**。⇒ **闸在 conductor，不在 worker 层**（AC-008 的直接结论）。

**AC-008 的两侧对比**（实测量，RQ-5 复算，本卡未重跑 trace 重叠统计——同一口径）：同一项目 E2Feature：autopilot/conductor（`ap-*`，431 session/100h）单 key 峰值 **1**（唯二例外是逃逸口 E2 的重试重叠 89.2s / 6.4s），项目峰值 2（另有一次 150s 的 4 = 2 conductor + 2 PM 手工 `ap-` 名）；PM 手工路径（non-`ap-`，54 session）项目峰值 **3**；MW 项目 PM 通道 166 session 峰值 **6**（`design-rqd1..6` 同批 306.3s 全重叠）。

#### 3.2 若未来放开：写面声明 → 机器可读 → 重叠拒绝 的设计面

现状反证（AC-014 的"机器判定为零"，复核）：写面纪律只存在于 **11/248** 个任务书的散文 `- 写面：…` 行；生产代码 grep `write_scope|writeScope|写面` **零命中**；`read_scope`/`deny_globs` 只拦 `read/ls/find/grep`（`worker-mode.ts:763-787`），`write/edit/bash` 不受约束；`implementation-gate` 对 worker 一律放行（`basis: "worker-env"`）。

设计面（**本 key 不实施，仅作 design 输入**）：

| 环节 | 字段/写入点 | 判定算法 | 锁 |
|---|---|---|---|
| 写面声明 | task.md frontmatter 新增 `writes:`（YAML 列表，与既有 `read_scope:`/`deny_globs:` 同形，`worker-mode.ts:253-290` 的解析器扩展；conductor 侧 `render_task_md`（`dispatch.py:262-331`）与 TS 侧 task.md 写入路径同渲染） | — | — |
| 机器可读 | 行/任务元数据：`writes` 归一化为 **normcase + 绝对路径前缀**（Windows 大小写不敏感，`mw.py` 已用 `os.path.normcase` 先例） | — | — |
| 重叠拒绝 | 两个派发入口：`dispatch.dispatch`（`dispatch.py:409`，写 task.md 之前）与 `dispatchTask`（`task-dispatcher.ts:284`，`upsert` 之前）；读同 key 的**在飞行**（`_is_in_flight`）的 `writes` 集合，做前缀交集 | 交集非空 ⇒ **拒绝派发**（conductor：返回 `DispatchResult(ok=False, reason="write-surface-conflict")` + timeline `type-rejected`；PM：抛错/不 upsert 并告警） | 复用 `.mw/workers.lock` 的 RMW 读；判定本身是只读，故不需要新锁；写面索引若缓存则必须落盘 + 每 tick 重推（GC-1/风险 12） |
| 行终态化时机 | 现状：判据是**行状态**而非**进程存活**（`_is_in_flight`），所以"提前置 failed"会打开并发窗口（见 3.3 E2） | 修法：派发前校验前驱行的进程已退出（launcher 已有 `running_procs`；conductor 只能用"行 `updated_at` + task 目录 `[END]`/进程探活"的近似，属**新面**） | — |
| 锁一致性 | **锁路径相同（RQ-5 该条为误报，RQ-9 已更正）**：`conductor.lock_file(root,"workers")` → `.mw/workers.lock`（`conductor.py:116-118`）== `mw_common.lock_path`（`mw_common.py:1440`），且 `reconcile_orphans` 确实在锁内（`conductor.py:4030-4032`）。**真正的差异是协议**：(a) 用 `acquire_conductor_lock`（仓内唯一有 age-based steal 的实现，`:143-154`）而非 `mw_common.acquire_lock`（无 steal）⇒ steal 到 launcher/TS 的持锁者时会失去互斥；(b) 写协议是 `open("a")` 追加（`:4038-4052`）而非 parse→改→tmp+rename RMW ⇒ 与 W1/W3/W4/W5 的全量重写混用时，行可见性依赖"读先于写"的时序假设 | 统一到 `mw_common.lock_path` + `mw_common.acquire_lock`（无 steal）+ `parse→改→_write_workers_file`；最低限度是去掉 steal 并让 append 走 RMW | `.mw/workers.lock` |

缺位时的首个失败模式（逐项）：无 `writes:` ⇒ 同 key 两卡写同一文件（P-018/P-019 家族，本仓库已发生）；无重叠拒绝 ⇒ 拒绝不会发生，冲突静默发生；行终态化不看进程存活 ⇒ 重试与旧进程并发写（**已实测 2 例：89.2s / 6.4s**）；锁旁路 ⇒ 行丢失/回滚（GC-3）。

#### 3.3 三个逃逸口的拦截面设计与可检测信号

| 逃逸口 | 锚点 | 现状 | 拦截面设计（**本 key 只落检测信号，不落闸**） | 可检测信号（机器可判） |
|---|---|---|---|---|
| **E1. PM 手工通道无判定** | `dispatch_worker` 工具只查 taskDir 去重（`pm/ui-bridge.ts:1113` 注册、`:1222-1232`），**不查该 key 有几个在飞**；`/worker` 命令 task_key = `manual-<ts>`（`:1555`/`:1611`）；后台扫描对某 key 的**所有**未入队 task.md 逐个 `dispatchTask`（`pm-orchestrator.ts:464`，无计数） | 完全可并行；CM 峰值实测 6（MW）/3（E2） | 在 `dispatchTask` 之前加"同 key 在飞计数 + 写面交集"判定（与 3.2 同一函数）；PM 通道需要**同一条**判定，否则修了 conductor 也堵不住 | **同 key 非终态行数 > 1 且其中至少 1 行 `origin != conductor`**；或 `slotsUsed`（conductor 口径）与"全行在飞数"出现差值。**当前可直接测量** |
| **E2. 行提前终态化** | 判据是行状态（`_is_in_flight`，`conductor.py:2131-2132`），而"谁把行置 failed"不可判定（RQ-5 数据缺口 1）。实测 2 例：`feature-gui-time-mvp-board-repair-a3-a3` 行 `updated_at=02:59:24Z` 终态 `failed`，`-a4` 于 `02:59:25Z` 派发，而 a3 的 `[END]` 在 `03:01:00Z` ⇒ **同 key 同 family 2 个 pi 进程重叠 89.2s**；`feature-params-service-002-probe` → `-a2` 重叠 **6.4s** | 现存双写源（非本 key 引入） | 拦截面 = "派发前校验前驱家族行的进程已退出"：conductor 侧可用 `[END]` 缺失 + task 目录 mtime 新鲜度做近似；launcher 侧可用 `running_procs`（精确）。**本 key 只落"能否判定 writer"的可验证方法**（RQ-5 已给：临时项目复现 + `.agenticdoc/_workers.parallel` 轮询审计记录 status/updated_at 变化 + 写者 pid；或给 `mw_common.update_status` 加调用方标记后重放） | **同 key 家族内两行的存活区间重叠 > 0**（trace.log `[START]`/`[END]` 区间扫描即可算出，RQ-5 已验证）；或"某行 `updated_at` 早于同 key 另一进程的 `[END]` 且后缀为 `-aN` 重试" |
| **E3. xkey 提案通道** | `_xkey_proposal_stage` 在计算 `in_flight_keys` **之前**执行（`conductor.py:243-254` 顺序）；对每个 `approved && 无 proposal.md` 的 ticket 各派 1 个（`_xkey_proposal_one` `:2983`，`dispatch` `:3031`），只受 `_XKEY_PROPOSAL_MAX_ATTEMPTS = 2`（`:2872`）与 ticket 条数约束 ⇒ 同一 tick 可派 N 个，既越过 key cap 也越过"每 key 1"（有独立 stem-family in-flight 判定 `_xkey_proposal_in_flight`） | 默认关闭（`xkey_repair: false`，`config.py:56`），生产 0 样本 | 拦截面 = 把 `_xkey_proposal_stage` **移到 `in_flight_keys` 计算之后**，并对其派发做与常规派发同一套 cap/写面判定（或显式声明"该通道豁免，但必须在面板上单列计数"） | **同一 tick 内 xkey 派发数 > 1**（timeline `xkey-proposal-dispatched` 事件计数 `conductor.py:3040-3043`）；或"该 key 的非终态行数 > `max(1, max_parallel_keys)`" 且其中含 `xkey-*-proposal` stem |

#### 3.4 本 key 是否应该"只做可观测与判据、不做放开"

**建议：本 key 只做可观测与判据，不做放开。** 理由（都要有证据）：

1. **放开的硬前置不存在**：写面声明→机器可读→重叠拒绝链条**机器判定为零**（3.2 现状反证），而 per-key 并发是**净新增**写冲突面（不是已有风险的放大）。
2. **地基不可靠**：互斥判据是行状态而非进程存活，且**已在生产发生** 2 次同 key 重叠（89.2s / 6.4s）⇒ 新加的同 key 并发判定会建在同一个不可靠地基上。
3. **收益面不对**：autopilot 路径每 key 峰值恒 1（RQ-5：429/431），而夜跑吞吐的主因是 **gate 阻塞**（RQ-6：stalled 占墙钟 46.6%/54.6%）与"死连接/长命令误杀"，不是 per-key 串行化；放开 per-key 并发对"卡在 gate 上的 key"零收益。
4. **成本面明确**：放开 = 写面判定 + 行终态化时机 + 锁一致性 + 三处 family 判定同步放宽（`conductor.py:1095`、`:1600`、`:1730`） + 面板口径；每一处都是 AC-010 的两侧镜像面。
5. 与之对照，PM 手工路径峰值 6 而**不受任何并发判定约束**——真正"需要收口"的是 PM 通道（E1），而不是放开 conductor。⇒ 本 key 的合理动作是把 **E1 的检测信号**做出来（AC-021），放开留给后续 key。

若 PM 仍要放开：**必须显式声明"本 key 不执行"**，并把 3.2 的四条前置与 3.3 的三个逃逸口写成后续 key 的入口条件（spec §3 范围内 AC-014 已要求这份清单）。

### 4. 归属缺口（AC-021）

#### 4.1 现状锚点：`_workers.parallel` 无 writer 列，且存在三套归属口径

- **行结构（8 列，无 writer/origin）**：`TaskKey | status | cli | provider | taskPath | dispatchedAt | updatedAt | model`——TS `WorkerEntry`/`WORKER_COLS = 8`（`shared/worker-store.ts:22-37`、`:38-55`），Python `parse_workers_file`（`mw_common.py:1444-1470`，容忍 7/8 列）+ `serialize_entry`（`:1472-1483`）。实测行样（E2）：`review-slicing-algorithm-spec | done | pi | timi | H:\\git\\E2Feature\\.agenticdoc\\slicing-algorithm-spec\\workers\\review-slicing-algorithm-spec\\task.md | 2026-09-20T08:04:21.926Z | 2026-09-20T08:11:42+00:00 | gpt-5.6-sol`。
- **五个 writer**（RQ-5 F1）：W1 `dispatch.dispatch`（`dispatch.py:528` task.md → `:534-570` 锁内 upsert，`.mw/workers.lock`）；W2 `conductor.reconcile_orphans`（`conductor.py:4030-4052`，`open("a")` 追加，锁是 `.mw/conductor-workers.lock`）；W3 `mw_common.update_status`（`:1512-1524`，`.mw/workers.lock`）；W4 `mw_common.archive_stale_entries`（`:1529-1559`，同锁）；W5 `WorkerStore.upsert`（`worker-store.ts:67-84`，同锁 + tmp/rename）。
- **三套归属口径**：
  | 消费者 | 判据 | 锚点 |
  |---|---|---|
  | conductor（槽位与派发） | **前缀 `ap-{key}-` OR task_path 含 `.agenticdoc/{key}/workers/`** | `_row_belongs_to` `conductor.py:2135-2138`（调用 `:261`） |
  | 面板（`slots ${used}/${max}` 与每 key `inFlight`） | **仅前缀 `ap-{key}-`**；不匹配时 `busyKeys.add(w.taskKey)`（该行自成一"key"） | `monitor.ts:503-513`（`inFlight` `:499`，`busyKeys` `:509-513`，`slotsUsed` `:521`） |
  | `mw.py`（RAG 审计分组） | **仅 task_path**（`rel.parts[0]`） | `mw.py:1801-1820` |

#### 4.2 实测分歧（可复算）

- **两侧判定不一致**：`前缀` vs `path` 的归属结果相差——**E2Feature 54/491 行、FeatureMigrator 106/236 行**（全部是"path 认、前缀不认"：PM 手工 task_key 不带 `ap-` 但目录在 `.agenticdoc/<key>/workers/` 下）。JCodingAss 72/72 一致。
- **前缀是假信号**：**6 行带 `ap-<key>-` 前缀但 task.md 无 `origin:` 行**（E2 5 行：`feature-inline-marker-patchkit-repair-a4-achieved-terminal`、`feature-sampling-human-channel-repair-a2-achieved-terminal`、`feature-cigate-install-kit-repair-a3-achieved-terminal`、`feature-l3-readcap-injection-repair-a2-achieved-honest`、`feature-gui-time-mvp-board-unratified-disclosure`；JCodingAss 1 行：`ap-plugin-ui-006-toolwindow-scroll-a2`）。⇒ 这些行**被 conductor 计入 `in_flight_keys`（前缀分支）、被面板计入 key 的 `inFlight`/`slotsUsed`**，但它们不是 conductor 派发的（`origin:` 缺行 = 非 conductor 通道的签名；conductor 渲染器恒写 `origin: conductor`，`dispatch.py:298-301`）。
- 反向：`origin: conductor` 但前缀不匹配的行 **0**（E2/FM/JC 均为 0）⇒ 现有 conductor 派发恒满足 `ap-{key}-` 前缀，`origin` 与前缀在**conductor 侧**自洽。
- ⇒ 结论：**归属无法只靠格式取证**（时间戳精度/`origin:`/task.md mtime 都是近似），需要行级 writer/origin 列。

#### 4.3 方案选型（writer 列 / 前缀命名空间 / 行携带 origin）

| 方案 | 设计 | pros | cons | 两侧镜像面 |
|---|---|---|---|---|
| **A. writer 列**（推荐变体：列名 `origin`） | 第 9 列 `origin ∈ {conductor, pm, xkey, legacy}`，由**写者代码路径**填入（W1 conductor、W2 conductor、W3 保留、W4 保留、W5 pm），**不读 task.md**（task.md 派发后可被 agent 改写） | 归属直读、无格式取证；旧行 `origin=""`/缺列 ⇒ 按 path 兜底（向后兼容读取判据）；同时把"谁写的"变成机器可判（AC-013 的"无法判定 writer"也一并解决） | 9 列 ⇒ 触碰两侧 parser/serializer + 直接追加路径 + 所有读者；`_workers.stale.parallel` 的归档行格式（`serialize_entry + " | " + now + " | " + reason`，`mw_common.py:1553-1559`）同步；W2 的 `open("a")` 追加必须补列 | `worker-store.ts`（`WORKER_COLS`/`parseWorkerLine`/`serializeWorkerLine`/`WorkerEntry`）+ `mw_common.py`（`parse_workers_file`/`serialize_entry`）+ `conductor.py:4038-4052` + 读者（`monitor.ts`、`mw.py`、`conductor.py:200`）。7/8 列容忍必须保留 |
| **B. 前缀命名空间隔离** | 规定"conductor 独占 `ap-`，PM 手工一律 `pm-`/`manual-`" | 不动行格式 | **治不了 AC-021(a)(i)**：conductor 的 `_row_belongs_to` 有 OR 的 path 分支，PM 行只要落在 key 的 `workers/` 下就仍占 key 槽位；也治不了面板（面板本来就只看前缀，改了前缀反而让 PM 行从 `slotsUsed` 消失⇒口径更分叉）。且需改 PM 任务命名约定（人工面） | 只需改 `dispatch_worker`/`/worker` 的命名 + 文档；**但不足以收敛** |
| **C. 行携带 origin（语义同 A，但由 task.md 派生）** | 行 origin 由派发时读 task.md 的 `origin:` 得到 | 复用既有 `origin:` 单一来源（`pm-orchestrator.ts:358-379` `ORIGIN_LINE_RE`/`readTaskOrigin`） | task.md 在派发后可被改写（worker 有 write 工具）⇒ 行的归属会与"当时的事实"漂移；且 PM 手工行的 task.md **无 origin 行** ⇒ 仍需"缺行 = pm"的隐式约定（可判，但弱） | 同 A 的列面 |
| **D. 只做读取侧收敛（不新增列）** | 定义唯一的 `owner_key(row)` + `origin(row)` 纯函数，两侧各实现一份，判据统一为：`origin = row 有 origin 列 ? 列值 : (task_path 在 .agenticdoc/<key>/workers/ ? "pm" : "unknown")`；`owner_key = 从 task_path 解析 key（兜底：从前缀解析）` | 零行格式改动、零迁移；立刻消除"面板只看前缀"和"mw.py 只看 path"的分裂 | 仍无法机器区分"PM 手工 `ap-` 名"（4.2 的 6 行）——只能标 `origin=pm-by-path` | `monitor.ts` + `mw.py` + `conductor.py` 三处纯函数 |

**建议：A（列名 `origin`，由写者路径填）+ D 的 `owner_key` 判据作为旧行兜底**。B 单独不可用（治不了 slot 口径）；C 有漂移风险，可作为 A 的交叉校验（conductor 派发行断言 `origin 列 == "conductor" == task.md origin`）。

**向后兼容读取判据（AC-021 要求）**：

1. 7/8 列行（无 `origin`）：`origin = ` task_path 落在 `.agenticdoc/<key>/workers/` 且 task_key 以 `ap-<key>-` 开头 ⇒ `"conductor"`，否则 `"pm"`；此为**旧行启发式**，必须在面板上标注 `~` 前缀（不造假精度）。
2. 9 列行：`origin` 列即权威；`origin==""`（PM 未填）时退回 1。
3. `owner_key`：优先 task_path 的 `.agenticdoc/<key>/workers/` 解析；不可得时用 `ap-<key>-` 前缀；两者都不可得 ⇒ `unknown`（面板单列，不计入 `slotsUsed`）。

#### 4.4 与面板/conductor 口径收敛的关系

- **收敛目标**：`slotsUsed` 与 conductor 的 `len(in_flight_keys)` 必须是**同一个集合基数**（同一份 `owner_key` + `origin` 判据、同样只算非终态行、同样只算 conductor 归属）。现状差值来自两处：(a) 前缀 vs 前缀 OR path（4.2：E2 54 行/FM 106 行结构分歧）；(b) 面板把"不匹配任何已知 key"的行算作一个独立 key（`monitor.ts:512` 的 `busyKeys.add(owner ?? w.taskKey)`）⇒ 面板可能显示 `slotsUsed > slotsMax`（RQ-5 数据缺口 6 已记录）。
- **收敛后的建议口径**：`slotsUsed` = `count(distinct owner_key of non-terminal rows with origin == "conductor")`；新增 `manualRunning` = 同式但 `origin != "conductor"`（**PM 并发必须可见，但不占 conductor 的槽计数**，这是 AC-021(a)(i) 的直接修复：PM 手工行不再消耗 conductor 的 key 层配额）。`mw doctor` 用同一函数。
- **conductor 侧同步**：`_row_belongs_to` 改为"`origin == conductor` 时按前缀/path 归属；否则**不计入** `in_flight_keys`"，`_is_in_flight` 不变。⇒ PM 手工行不再占 conductor 槽（现状 4.2 的 6 行问题消失），但 PM 行的在飞数出现在 `manualRunning`。
- **风险**：改 `_row_belongs_to` 会改变"是否存在同 key 并发"的判定 ⇒ 与 3.1 的硬互斥耦合。必须与 3.4 的"不放开"建议一致：只改**归属**（谁算在飞），不改**并发许可**（仍不允许同 key 并行派发）；PM 行的并发仍由 PM 通道自己负责。

### 5. VC 候选（≥3 条机器可判）

| ID | 命题（可判、可为假） | 机器判据 | 现状基线（反例已在盘上） |
|---|---|---|---|
| **VC-1** | **PM 手工派发的行必须能机器区分于 conductor 派发行** | 对 `_workers.parallel` 全部非终态行：`assert row.origin in {"conductor","pm","xkey","manual"}`（9 列后）；且 `count(task_key.startswith("ap-<key>-") and origin != "conductor")` 可报出 | **基线 = 6 行**（E2 5 + JC 1）当前无法机器区分（无列）⇒ 命题可为假（已假） |
| **VC-2** | **判死时刻"有工具在飞"的 idle 击杀必须为 0** | 每次 idle 击杀写机器行 `[IDLE_KILL] tool_in_flight=<name|none> silence=<N>s`；断言 `count(tool_in_flight != none) == 0`（窗口内） | **基线 = 22/24**（由 `工具起→判死 == idle_s` 复算得到，本卡 §1.2）⇒ 命题可为假（已假） |
| **VC-3** | **`_autopilot/config.json` 的每个键都必须有消费者，或显式标注为 schema-only** | 静态测试：对 `DEFAULT_CONFIG` 的每个键，在 `packages/multi-workers/autopilot/**` + `agent-team-loop/**`（排除 config/status-model 自身与 test）grep 命中数 > 0；否则必须出现在显式的 `SCHEMA_ONLY_KEYS` 集合里（含注释理由） | 当前 `worker_timeout_min` 命中数 = **0**（§2.1）且不在任何标注集合里 ⇒ 命题可为假（已假） |
| **VC-4** | **面板与 conductor 的归属口径必须一致** | 合成 8 行（①`ap-<k>-x` 无 origin；②`<pm>-y` 在 `.agenticdoc/<k>/workers/` 下；③`ap-<k>-z` 有 `origin: pm`），断言 `deriveAutopilotPanel().slotsUsed` == `len(in_flight_keys)` 且两者都把 ③ 归为 pm、② 归为 k | 当前两侧判据不同（前缀 vs 前缀 OR path）⇒ 命题可为假（E2 54 / FM 106 行结构分歧） |
| **VC-5** | **同 key 并发必须可被机器检出（无论是否允许）** | 扫全部 trace.log 的 `[START]`/`[END]` 区间，按 key 分组求峰值；断言"conductor 派发（`origin: conductor`）的 key 峰值 ≤ `max_parallel_keys`"且例外（逃逸口）必须列出 | 现状 2 个正例外（89.2s / 6.4s，均为重试与旧进程重叠）⇒ 命题可为假（已假） |
| **VC-6** | **`ap-` 前缀不得作为唯一归属依据** | 断言：`origin` 列存在时，归属只读该列 + task_path；`ap-` 前缀仅作为旧行兜底且必须带"低置信"标记（面板渲染 `~`） | 当前面板**只**看前缀（`monitor.ts:509-513`）⇒ 命题可为假（已假） |

## 数据缺口

1. **误杀集合的完整性**：本卡只统计 `output.md` 带 `no activity for Ns` 机器行的死亡（24 次）。**旧格式/被覆盖/被 repair 改写的 `output.md` 可能漏计**（RQ-2 曾报"另有 3 个含 idle timeout 无机器行"，本卡复核其中 2 个是散文提及、非 Exit Reason）。**可验证方法**：改用 timeline/`[TIMEOUT]` 事件（若存在）或给 kill 增加结构化事件（即方案 D）作为权威源。
2. **"真挂死"与"合法长静默"的分界不可从现有数据估出**：`idle_s` 被阈值截尾在 601–622s，无法回答"命令运行时长的真实分布"或"阈值抬到多少才够"。**可验证方法**：受控实验——记录 bash 工具实际的 `handleData` 时间戳分布（需要新埋点），或对 24 次里被杀的同一命令做无看门狗的复跑并测墙钟。
3. **#3/#2 两次"无工具在飞"静默的性质不明**：无法判断是死连接、慢生成还是模型侧排队。**可验证方法**：在 `message_update` 缺失窗口内加入 API 层探测（如 provider 侧 latency/连接状态），或对同一 provider 做受控静默计时。
4. **`t003-migration` 的最后一次 touch 是 `tool_execution_end` 还是 turn 事件，无法从 trace 判定**（trace 只记 `[TOOL]` 起点与 heartbeat）。**可验证方法**：同 2 的埋点。
5. **行提前终态化的 writer 不可判定**（RQ-5 数据缺口 1 仍未解）：`02:59:24Z` 把 `ap-feature-gui-time-mvp-board-repair-a3-a3` 置 `failed` 的写者无法从产物定位。**可验证方法**：临时项目复现 + `_workers.parallel` 轮询审计（记录 status/updated_at 每次变化 + 写者 pid），或给 `mw_common.update_status` 加调用方标记后重放。
6. **PM 手工通道的并发上限**：实测峰值 6（MW）/3（E2），但**样本只有这些**，且 `--max-workers` 不落盘 ⇒ 无法回答"PM 通道在 8/12 并发时会先坏在哪"。**可验证方法**：受控派发实验（本卡无权限）。
7. **xkey 通道生产 0 样本** ⇒ E3 的拦截面无法用生产数据验证，只能用合成测试（`test_autopilot_*` 已有 e2e 脚手架）。
8. **写面重叠概率不可量化**：无机器可读写面数据（3.2 现状反证）⇒ "若放开 per-key 并发会冲突多少次"目前不可答。

## 结论 → 决策映射

| 决策问题 | 结论 | 证据锚点 | 建议 PM/design 动作 |
|---|---|---|---|
| **idle 看门狗（AC-005 / c2）** | 根因 = 判据缺"工具是否在飞"这一维；`bash` 的 update 是输出驱动 ⇒ **长命令无输出即隐形**。修法 **D→B→C**，A 不单独用 | §1.1（锚点）、§1.2（24 次复算，22 次 `工具起→判死 == idle_s`）、§1.3（`bash.ts:200/371-414`、`rag/budget.ts:257-280` 先例）、§1.5（T1–T5） | design 写 3 件事：① `[IDLE_KILL]` 结构化机器行（含 `tool_in_flight`）；② `toolInFlight` 计数 + 新阈值 `toolIdleMs`（两侧落盘 + 镜像）；③ 无工具在飞分支的二次确认。**本 key 不实现，只作为 design 输入** |
| **`worker_timeout_min`（AC-005）** | **静默空操作**：可判据 = 生产 grep 零消费者；`render_task_md` 不渲染 `timeout:` ⇒ conductor worker 恒 60m | §2.1（`config.py:18/54/72`、`status-model.ts:81/108/138/273/298`、`dispatch.py:262-331`）、§2.3 | 选 (i) 接线：两侧同渲染 task.md `timeout:` 头；**不动键集合 ⇒ parity 语料不用重冻**；若选 (ii) 必须先做项目文件迁移 |
| **per-key 串行化（AC-008/AC-014 / d）** | 三重保证复核成立（硬顺序）；**本 key 只做可观测与判据，不做放开** | §3.1（`conductor.py:258-264/287-288/908-1015/1095-1096/1600-1602/1730-1734`）、§3.3（三逃逸口）、§3.4（4 条理由 + RQ-5 的 429/431 vs PM 峰值 6） | design 落"检测信号 + 入口条件"，明确写"**本 key 不执行放开**"；把 3.2 的四条前置列为后续 key 的入口条件 |
| **归属缺口（AC-021）** | 无 writer 列 + **三套口径**（conductor 前缀 OR path / 面板仅前缀 / `mw.py` 仅 path）；前缀是假信号（实测 6 行 `ap-` 但非 conductor） | §4.1（`worker-store.ts:22-37`、`mw_common.py:1444-1483`、`conductor.py:2135-2138`、`monitor.ts:509-513`、`mw.py:1801-1820`）、§4.2（E2 54 / FM 106 行分歧） | design 选 **行级 `origin` 列（写者路径填）+ `owner_key` 统一判据**；面板拆 `slotsUsed`（conductor）与 `manualRunning`（PM）；`_row_belongs_to` 改按 origin，旧行按 path 兜底 |
| **VC** | 6 条候选（VC-1..VC-6），全部可用现有产物或合成行集复算，且**现状均为假**（有反例） | §5 | design 从中挑入选 VC 并绑定实现面 |

**一句话给 design**：本卡的全部结论都指向"**先把机器判据补上**"——误杀的判据、死键的判据、归属的判据、同 key 并发的判据；四者都不需要放开任何并发或阈值，全部是只读/可复算的增量。

## [VERIFY]

```
[VERIFY] D7: idle_kills=24 (5 projects, 2026-09-19..09-26; idle_s 601-622, margin 1-22s) last_tool=bash 23/24 toolrun==idle 22/24 => in-flight bash, zero tool_execution_update
  anchors idle: worker-mode.ts:148 DEFAULT_IDLE_MS=600000, :163-167 resolveIdleMs(PI_WORKER_IDLE_MS), :895 read, :1022-1033 judge(30s tick), :1031 detail(last delta/last tool), :911-937 timeoutExit
  anchors activity: message_update :803-806 (lastDeltaAt), tool_execution_start :825-830 (lastToolAt), tool_execution_update :812, tool_execution_end :813/:841, turn/message :807-811, agent_end :849-850
  anchors bash update: core/tools/bash.ts:200 throttle=100ms, :371-373 emit only if updateDirty, :392-401 schedule, :411-414 handleData(output-driven) ; precedent rag/budget.ts:257-280 withHeartbeat 30s
  conc_at_death: mean 2.71 max 10 (5 projects/1143 sessions); RQ-2 narrow scope mean 2.14 max 3
  retry: 12/24 first sibling retry exit=0, 6 non-zero (3 tasks died twice), 6 no sibling
[VERIFY] worker_timeout_min: consumers=0 (config.py:18/54/72 only in autopilot/**; status-model.ts:81/108/138/257/273/298 schema-only) wall_chain=task.md timeout: > PI_WORKER_TIMEOUT_MS(no writer) > 60m; render_task_md dispatch.py:262-331 writes no timeout header => conductor workers always 60m
[VERIFY] per-key serial: hard (conductor.py:258-264 in_flight_keys + :287-288 skip + :908-1015 one-dispatch-per-branch + :1095-1096/:1600-1602/:1730-1734 loop guards) launcher unlimited (launcher.py:819-841, :966, --max-workers default None :1021) autopilot per-key peak 1 (429/431) vs pm-manual peak 6
[VERIFY] write-surface machine check = 0 (write_scope|写面 grep 0 in production; read_scope/deny_globs intercept read only worker-mode.ts:763-787) => recommendation: this key does observability+criterion only, NO per-key concurrency opening
[VERIFY] escapes: E1 pm path no concurrency check (ui-bridge.ts:1222-1232, pm-orchestrator.ts:464) E2 row pre-terminalization overlap 89.2s/6.4s (writer undecidable) E3 xkey proposal before in_flight_keys (conductor.py:243-254, :2872 cap=2, :3010 stem-family guard)
[VERIFY] attribution: row=8 cols no writer (worker-store.ts:22-37; mw_common.py:1444-1483) 3 rules disagree = prefix-OR-path (conductor.py:2135-2138) vs prefix-only (monitor.ts:509-513) vs path-only (mw.py:1801-1820); E2 54/491 and FM 106/236 rows structurally disagree; 6 rows have ap- prefix but no origin:conductor (E2 5 + JC 1)
[VERIFY] VC: VC-1 origin distinguishability (baseline 6 rows fail) VC-2 idle-kill-with-tool-in-flight==0 (baseline 22/24 fail) VC-3 config key consumers>0 or schema-only list (baseline worker_timeout_min=0) VC-4 panel/conductor slots parity VC-5 per-key peak<=cap with listed escapes VC-6 ap- prefix not sole attribution
```