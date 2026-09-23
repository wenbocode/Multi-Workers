# Research: 派发门禁 / 面板可见性 / claim 身份的改造前基线（spec）

> 日期：2026-09-23
> Key: mw-worker-visibility-gate
> 方式：只读代码勘察（本仓 + 框架 clone），无外部网络调研

## 决策问题

支撑 spec 的三个范围决策：
- §1.1-1（派发门禁与相位脱钩）：现状到底在哪一层脱钩、能否复用既有相位读取口？
- §1.1-2（面板他键任务不可见）：工具与面板的所有权判定分别在哪、分叉点是函数签名还是谓词？
- §1.1-3（claim 身份双写）：谁是权威、谁在写、分叉的具体 pid 语义差在哪？
- §2 约束（能否在当前仓库内完成）：框架脚本属于哪个仓库、能否随本 key 一起改？

## 调研方法与出处

全部为仓库内文件的直接阅读（文件:行号），无外部来源。

## 发现

### F1 派发门禁与相位脱钩（三处调用点，一处判定）

- 判定函数 `dispatchDocGaps(agenticdocRoot, key)`：`packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts:127`；`_scratch` 直接放行（`:128`），其余走 `phaseDocGaps(readPhaseDocs(...))`。
- 缺项判定 `phaseDocGaps(status)`：`phase-docs.ts:96`；六项硬要求、与相位无关：`spec.md`≥500B、`evidence/research/spec-*.md`≥1、§0 含"预期收益"、≥1 条 `AC-NNN`、`design.md`≥500B、`evidence/research/design-*.md`≥1。阈值常量 `MIN_PHASE_DOC_BYTES = 500`（`phase-docs.ts:7`）。
- 状态采集 `readPhaseDocs()`：`phase-docs.ts:81-94`（`spec`/`design` 为文件字节数判定，`specEvidence`/`designEvidence` 按 `evidence/research/` 前缀计数）。
- **相位本来就是可读的**：`dispatchPhase(agenticdocRoot, ownerKey)`（`pm/ui-bridge.ts:902`）通过 `StateManager.read().phase`（`pm/state-manager.ts`）读取；且该值已在同一调用链里算过（`ui-bridge.ts:1093` 附近取 `docGaps`，随后用它填 task.md frontmatter 的 `phase:`）。
- 门禁调用点有 **两处**：`ui-bridge.ts:1093`（`dispatch_worker` 工具）与 `ui-bridge.ts:1498`（另一个入口，改门禁时必须同步，否则两条入口行为分叉）。
- `DOC_GATE_HINT`（`phase-docs.ts:117-124`）当前明确把 `_scratch` 作为兜底建议 → 这是"关键工作被引出 key"的直接引导源。

### F2 面板与工具的所有权判定分叉

- 工具侧（`list_tasks` / `ack_worker_result`）：`ownedByThisWindow(entry, watch, agenticdocRoot)`（`ui-bridge.ts:278`）= `ownerKeyOf(e) === watch.key || watch.dispatchedTaskKeys?.has(e.taskKey)`；派发时登记：`ui-bridge.ts:1153-1154`。
- **面板侧**：`renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key)`（`ui-bridge.ts:480`），第 495 行 `const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === key)` —— **只有 key 一个维度，且函数签名里没有 `watch`**，构造上拿不到 `dispatchedTaskKeys`。
- 另有 `ui-bridge.ts:771` 一处同谓词（另一个列表入口）。
- monitor 的跨 key 过滤：`pm/pm-orchestrator.ts:546`（risk 升级）与 `:565`（终态回读），均为 `ownerKeyOf(entry, agenticdocRoot) !== watch.key` → 跨 key 任务既不升级也不回读。
- 行宽上限 `WATCH_LINE_MAX = 110`（`ui-bridge.ts:249`）。
- 结论：分叉点是**函数签名辖域**（面板拿不到 `watch`），不是谓词语义本身 → 修法是给面板传入"本窗口派发的键集合"并在其中排除已属于 watched key 的行。

### F3 claim 身份的两个写入者与权威

- Python 侧（框架仓库）：`now_claim_id()` = `f"{socket.gethostname()}:{os.getpid()}"`（`.agents/skills/agentic-task/core/scripts/update_index.py:58-61`）——**短命进程的 pid**；`cmd_claim` 把它写进索引行（新行同时写 `phase: "—"`，`:374-398`）并同时写 pm-state（`_update_pm_state_claim`，`:262-305`；新文件时创建三行 stub：`Key`/`Claim-Id`/`Phase: init`，`:269-280`）。
- 存活判定 `claim_is_stale_local()`（`update_index.py:97-107`）按 `host:pid` 查进程是否还在，Windows 走 `GetExitCodeProcess`；即**按 pid 判活**。
- TS 侧：`IndexStore.claim()`（`shared/index-store.ts:91`）把索引行 `claimId` 写成 `self`（本窗口 id，`:117`）；新 key 时建行 `phase: "SPEC"`（`:121`）。
- pm-state 的读取者：`pm/state-manager.ts:32`（`read()`）；写入者只有 `write()`（`:56`），而 `StateManager` 的实际调用点仅 `ui-bridge.ts:904`（读相位）与测试 → **TS 侧当前没有人写 pm-state 的 Claim-Id**。
- 权威使用点（都读索引行，不读 pm-state）：`shared/implementation-gate.ts:229`（`active && claimId === wanted` 决定实施门禁）、`pm/ui-bridge.ts claimState()`/`resolveOwnerKeyWithSync`（liveness/所有权）。
- 结论：索引行是权威、pm-state 是**无读者的镜像**；分叉不会报错（无消费者），但一旦未来有代码按 pm-state 判活，短命 pid 天然已死 → 误判 stale 并允许无 `--force` 抢占。
- 另有一致性缺口：`advance_phase.py:305-334` 只有在"缺 `- Updated:` 且缺 `- Next Action:` 且带 `- Claim-Id:`"三条件同时成立时才升级 stub 模板（保留 Claim-Id），否则 fail-closed；这解释了首次 advance 的 template drift 报错是设计行为。

### F4 框架脚本属于另一个 git 仓库

- `.agents/skills/agentic-task` 本身是框架仓库的 clone（`git -C .agents/skills/agentic-task log` HEAD = `d7004d0`，工作区干净）；三份镜像 `scripts/`、`core/scripts/`、`claude/scripts/update_index.py` 的 sha256 相同（`0b8f7128…`）。
- `packages/multi-workers/.tmp/agentic-task` 是同一远端的一个**落后** clone（HEAD `fa97ed6`，其 `update_index.py` 缺 `find_root` 的 cwd 优先逻辑）。
- SKILL.md「Lightweight Framework Maintenance」：`scripts/` 为规范源，`claude/`+`core/` 是镜像；框架改动需在 clone 内提交并 push（`mw.py push-agentictask` 走 `.tmp` 那个 clone，与 SKILL.md 建议的"就地改安装 clone 并 push"并存）。
- 结论：任何 Python 侧改动（claim stub 模板、`phase: —` 占位符）都要跨仓库提交+推送，**不应混进本仓 key**；本 key 只做 TS 侧可自洽部分与记忆登记。

### F5 事故现场（用户报告，本次改造的触发源）

- key `h0h1-decision-baseline`（另一台机器 PC3 的窗口）：`dispatch_worker` 被 `Worker dispatch blocked: key 'h0h1-decision-baseline' is missing phase documentation` 拒绝 → 4 个 worker 按 hint 落到 `_scratch`；`list_tasks` 可见（4 running），面板 0 行。
- 首次 `advance_phase` 撞 template drift（缺 `- Updated:`）→ 跑脚本后 pm-state 被升级为标准 7 段模板，`Phase: SPEC`，索引同步 SPEC，`audit_phase` PASS。
- 同 key 的 `Claim-Id` 与索引行 Claim 列不一致（`WENBOZHOU-PC3:67152` vs `WENBOZHOU-PC3:22428`），audit 未报 drift —— 与 F3 的结论一致（无消费者）。

## 结论 → 决策映射

| 结论 | 支撑的决策 |
|------|-----------|
| F1（相位已可读、门禁与相位脱钩、两处调用点） | spec §1.1-1 的根因表述；design 采用"按相位分层缺项 + 两处调用点同改"，且阈值/文案复用 `phase-docs.ts` 现有常量与 `DOC_GATE_HINT`（AC-001~AC-005、AC-012） |
| F2（分叉在函数签名辖域） | design 选择"面板只列本 key 行 + 1 行跨 key 聚合提示"，而非把面板改成 `ownedByThisWindow` 全混列（AC-006~AC-009） |
| F3（索引行权威、pm-state 无人写/无读者、pid 语义差） | spec §1.1-3 与 D-c 决策：双写 + 同值 + 索引权威；TS takeover 增同步写（AC-010/AC-011），并把规则登记进 `_pitfalls.md`（AC-013） |
| F4（框架脚本在另一仓库） | spec §1.4 范围排除 + §4 R-2/R-3 残留（不在本 key 改 Python） |
| F5（真实事故） | spec §1.3 场景 A/B/C 与 §0 预期收益的可观察判定项 |
