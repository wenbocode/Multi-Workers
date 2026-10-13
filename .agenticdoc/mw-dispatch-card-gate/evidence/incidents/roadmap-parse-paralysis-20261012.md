# 事故：autopilot conductor 静默停摆（roadmap keys 表解析）

- 日期: 2026-10-12（发现）｜项目: `H:\git\E2Feature`｜关联 key: `mw-dispatch-card-gate`（E8/AC-009、E9/AC-011、AC-012/T-20）
- 性质: **运行期静默失败 2 天**（服务与 conductor 均存活、队列零派发、无任何告警到达操作者）

## 症状（实测）

| 观测 | 值 |
|---|---|
| 队列 `.agenticdoc/_workers.parallel` | 675 done / 33 failed / **0 pending / 0 running**，mtime **10-10 20:45**（**2 天零写入**） |
| 服务与 conductor | **均存活**：`.mw/mw.pid`、`.mw/conductor.pid`、`launcher-beat.*` 持续跳动（mtime 当天 22:06）；`serve.meta.code_dir = H:\git\Multi-Workers\packages\multi-workers` |
| index 状态 | 35 行（**32 个 DONE/idle** + 1 个 DONE/active）⇒ **工作状态正常，坏的是调度器** |
| 全项目 worker | 无任一 key 出现 ≥2 次 `[START]` ⇒ 不是"重启循环"，是**零派发** |

## 根因（已定位到行）

`conductor.log` **每个 tick 重复同一条**：
```
[conductor] gate reminders: roadmap unavailable, stage-terminal suppression disabled this tick:
  line 87 (stage 5): keys table row must have 3 columns (key | role | depends_on), got 4: [...]
```

链路：
1. **生产者**：`packages/multi-workers/autopilot/roadmap.py:283/286-288` `add_key_row` —— `len(cells) != 3` 即抛 `must have 3 columns`。**role 单元格正文里含未转义的 `|`**（如 `view=feature | module`）使 3 列切成 **4 列** ⇒ **整份 roadmap 判为非法**。
2. **降级 A（零派发）**：`autopilot/conductor.py:235-239` `orchestrate` 捕获异常 ⇒ 只写一条 config 事件后 `return`，**每个 tick 重复**。
3. **降级 B（连带失效）**：`autopilot/conductor.py:2575-2596` `_gate_stage_context` 捕获同一异常 ⇒ 打印（`:2591-2592`，即上面那条）+ 返回 `(None, None)` ⇒ **`stage-terminal suppression` 一起被禁用**（单点故障扩散）。
4. **不可观测**：以上只在 `conductor.log` 内自述，**没有任何告警出口到达操作者** ⇒ 2 天无人知晓。

## 处置

- **人工修复（当时）**：`H:\git\E2Feature\.agenticdoc\_autopilot\_roadmap.md` 被修好（复核 `roadmap available: True`、5 stages、0 warnings、sha256 `f3ce0473…`）⇒ conductor **在 17:01–17:12Z 内派出 3 个任务（1 个已 done）** ⇒ 瘫痪解除。
- **框架修复（本 key T-20）**：
  - `roadmap.py`：`RoadmapWarning`/`Roadmap.warnings`；`parse_roadmap(strict=True)` 保 back-compat、`load_roadmap(strict=False)` 为生产默认；**M>N 行级恢复**（首列 key／末列 depends_on／中间片段用 ` | ` 拼回 role）；M<N 生产下跳过+警告、strict 仍抛；空 key/重复 key 局部化；表头缺失/无 stage 段仍结构性 `RoadmapError`；支持 `\|` 转义。
  - `conductor.py`：`_ROADMAP_ALARM_SEEN` session 级去重；`_emit_roadmap_failure`/`_emit_roadmap_warnings`（stderr + timeline `config` 双出口，含**路径+行号+原因+修法**）；`_gate_stage_context` 恢复行**不再禁用 suppression**。
  - 测试：`test_mwds_t20_roadmap_table.py`（11 用例，含 incident 行逐字复原、M<N 跳过、表头缺失 unavailable、**降级局部化对照**、**限频 1/0/0**）。
  - 验证：pre-fix 行（sha256 `f357964a…`，从 conductor.log GBK 逐字复原）在旧解析器下 `available: False / got 4`，新解析器下 `available: True` 且恢复 `('feature-mine-line', <role>, ('feature-planning-cockpit',))` + `recovered-pipe` 警告。
- **生效条件**：Python 侧无构建步骤，各项目服务/conductor 进程**重启即生效**；E2Feature 当前跑旧代码但已由人工修复维持正常。

## 关联事件（同一批收口中登记）

- **C-30**：ORPHANED 修复路径在 `agent-team-loop` / `mw-dispatch-reliability` 两个 idle key 上误触发（3 条队列行、4 秒 done、污染全局队列、触及别的 key 的队列面）⇒ T-24 收窄（无终态产物 + 当前状态引用 + owner 证据时效 + idle/终态只告警）。
- **C-32**：派发写序列**非原子** —— `_workers.parallel` 原子改名 `EPERM` 后留下**半成品 `task.md`**（缺注入段），仍被服务取走 spawn、随后在信封门被拒（`envelope missing: 验收命令`）⇒ 队列多一条 `failed`（3 秒、零 token）。现场复现于 T-26 首次派发。
- **重复 spawn / 假回读**：本 session 累计 **45 条**"exited before output.md"假 `failed` 回读（同一 task_key 出现 7~13 个 run_id）⇒ 队列行存在两个写入方，reconcile 误判未 spawn ⇒ 重复派发；**存在真实双 writer 风险**，`run.json` 定为运行状态唯一权威是后续 key 的输入。
- **假 `needs-clarification` 6 次**（T-18/T-19/T-20/T-21/T-22 等）：回收契约的写入意图判据不健全（否定盲区 / 无按 worker 归属 / 词元残渣）⇒ T-21 修复，运行期复查已不再复现。
- **C-34**：worker 的 ad-hoc 临时产物落在 **cwd（`H:\git`）而非仓库内**，留下 40 个 `t17-*` 文件（250,579 字节，已清理；`mwgf-t17-repair-reanchor` 的 `trace.log` 保留写入事实）⇒ 投递侧应钉死临时目录。

## 未定论 / 需人确认

1. E2Feature 的 conductor 是否会**自然重启**（决定 T-20 何时对其生效）；若不会，需人工重启其 `mw serve`/conductor。
2. E2Feature 的**存量卡形态**（旧形态、无 extras/种子）在其窗口 `/reload` 后是否会被工具层拒绝 —— 本次未对 E2Feature 做任何 reload/派发变更，故未观测；需在下一个 key 做**受控试点**。
3. 队列文件"单写入方 + `run.json` 权威"的改造是否立刻立项（本 key 明确未修）。
