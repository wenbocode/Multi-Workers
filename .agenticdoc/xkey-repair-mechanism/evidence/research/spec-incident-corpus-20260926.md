# Research: 事故语料与 A-06 前例（spec RQ-2）

> RQ-2 唯一产出文件；只读调研，未改动 FM（`E:\CLI_workspace\FeatureMigrator`）任何文件。
> 上游基础语料：`spec-problem-framing-20260926.md`（本文件只做深化与补全，不重复其结论）。

## 决策问题

回答 spec 的 §1.1（问题背景与根因）/§1.4（范围取舍）/§2.3（边界与解冻权）/AC-003·AC-005（取证形状）：

1. **Q1（A-06 前例，最重要）**：`红无 owner` 同族第一次出现的原始记录在哪里？逐字现象、处置、是否闭合、留下什么教训？"写面缺口"同族（A-01..A-07 全表）是什么？
2. **Q2（逐字证据补全）**：(a) `cli-run-state-and-events` L3 报告里 `REPAIR-R1-F1` 段落的完整上下文（含 L3 轮次号与 verdict 结论句）；(b) `cli-hitl-channel` L3 报告 §遗留 `K-1` 行的完整上下文；(c) `tests/test_hitl_channel.py` 的 `TOP_LEVEL_GROUPS` 定义处与 `:268` 附近断言的原文。
3. **Q3（时间线）**：`cli-hitl-channel` 何时 DONE、`runs` 顶层命令何时落地、两侧 L3 何时跑、申请文件何时写。
4. **Q4（"跨 key 修复轮"概念）**：`_index.parallel` / `_project_log.md` / `reflect` / roadmap 里是否已有"跨 key 修复轮（cross-key repair round）"这一既有承诺或阶段定义？若有，承诺载体是什么？
5. **Q5（该测试文件的改动史）**：`tests/test_hitl_channel.py` 此前是否被改过？改它的 key 是谁、走什么流程、有无 sha256/reason 留档？
6. **Q6（当前状态核对）**：该红今天是否仍存在（静态比对 12 vs 13，不跑会写缓存的命令）？申请文件是否已有 decision 行？

## 调研方法与出处

**只读纪律执行情况**

- 未写入 FM 树的任何文件；未执行 `git add/commit/stash`；未运行 `pytest`（会写 `.pytest_cache` / `__pycache__`，且在 `gui-live-monitor`、`gui-run-control-hitl` 处于 EXECUTE 时跑测试会翻转端口/计时类结果，与既有 N-3 记录一致）。
- Q6 的"红是否仍存在"用**静态比对**（读 `migrator/cli.py` 的注册表 + 读测试常量），未跑测试；Q6 明确标注"静态结论，非实测"。
- 只读命令：`git status --porcelain`（不改状态）、`Get-Item`（mtime）、`Get-FileHash`、`Select-String`、`Get-Content`、`python -X utf8`（仅读文件与打印行号，不写盘）。

**出处清单（本会话直接读取；路径均相对 FM 仓库根）**

| 类别 | 文件 |
|---|---|
| 申请/执行证据 | `.agenticdoc/_autopilot/evidence/cross-key-repair-request-20260925-n1.md`（84 行）· `.agenticdoc/_autopilot/evidence/xkey-n1-repair-20260926.txt`（150 行）· `.agenticdoc/_scratch/workers/xkey-n1-hitl-groups-repair/task.md` |
| A-06 记录 | `.agenticdoc/_autopilot/reflect/plan-writeface-gap.md`（66 行）· `.agenticdoc/_autopilot/reflect/_index.md`（49 行）· `.agenticdoc/_pitfalls.md` §43.2（742-754 行）· `.agenticdoc/gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md`（110 行） |
| 两侧 L3 | `cli-run-state-and-events/l3-report.md` · `cli-run-state-and-events/workers/ap-cli-run-state-and-events-{l3-a1,l3-a2,repair-a1}/report.md` · `cli-run-state-and-events/evidence/runs/repair-r1-out-20260925-r3.txt` · `cli-hitl-channel/l3-report.md` · `cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a{1,2}/report.md` |
| 时间线 | `.agenticdoc/_index.parallel` · `.agenticdoc/_project_log.md` · `cli-hitl-channel/pm-state.md` · `cli-run-state-and-events/pm-state.md` · `.agenticdoc/_autopilot/_roadmap.md`（40 行） |
| 代码/测试 | `tests/test_hitl_channel.py` · `migrator/cli.py` · `migrator/commands/cmd_*.py` |
## 发现

### Q1 — A-06 前例（"红无 owner"同族的第一次出现）

**定位**：A-06 的原始记录 = `.agenticdoc/_autopilot/reflect/plan-writeface-gap.md`（66 行）；台账索引行 = `.agenticdoc/_autopilot/reflect/_index.md:16`。

**身份 / 状态（逐字，`_autopilot/reflect/plan-writeface-gap.md`）**

- `:1` `# 归因 A-06：plan 级缺口 —— **新引入的红没有任何 task 有权修** ⇒ key 结构性不可收敛`
- `:4` `attribution_id : A-06`
- `:6` `status         : fixed-in-project（重冻结例外已于 2026-09-25T03:09:28+00:00 经人工**追认**）`
- `:7` `first_seen     : 2026-09-24T19:33 前（6 个红在 P1–P5 窗口内引入）/ 确证于 2026-09-25T02:42Z`
- `:8` `hit_keys       : gui-skeleton-shell（P5 两次耗尽 → gate-0006 的**根本**原因）`
- `:10` `evidence       : .agenticdoc/gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md`

**现象（逐字）**

- `:18` `  （`pyproject.toml` 更明确写"偏离只能走重冻结申请"）⇒ 按原口径 **P5 不可通过**；`
- `:20` `  「`migrator/**`（含 P1–P5 全部产物：本 task **零产品改动**）」⇒ **P6 不可修绿**。`
- `:22` `⇒ 没有任何 task 有权修这 6 个红，key 在原 plan 下**结构性不可收敛**（不是执行失败）。`

**根因（逐字）**

- `:35` `## 3. 根因（两条 plan 设计错误）`
- `:37` `1. **白名单没有覆盖"本阶段可能出现的全部失败面"**：P5 的判据把"全量套件"纳进来，写面却没有覆盖"套件红了要改哪里"。`
- `:38` `2. **红没有 owner**：plan 依赖"下一阶段会修"这一默认假设，而没有把红**显式指派**给任何 task；`

**当时如何处置（逐字）**

- `:41` `## 4. 处置（走重冻结，不降门槛）`
- `:45`-`:47` `1. **P6 白名单收窄例外**：仅 4 条路径可动（`cmd_gui.py` 注释措辞 / `tests/fixtures/gui_contract/v1/case-registry.json` 仅加第 15 个模块登记项 / `migrator/gui/logging_setup.py` 走既有写入者或登记该出口 / `pyproject.toml` 仅修 gui 声明，**P1 的 4 项版本锁字面量不得动**），每条要 `old sha256 → new sha256` + `reason` + **禁止放宽断言**。`
- `:48`-`:49` `2. **P5 判据 #8 口径澄清**（写入 task 005 正文）：不新增用例 + 全量结果**原文落盘**并交 P6；`
- `:50` `3. task 005/006 正文补入**已知红名单 + 交接说明**（worker 必读任务书，不必重新发现）。`
- `:52`-`:53` `**验证**：P5 attempt 3 于 `10:59:59` `STATUS: PASS`（7 条 `[VERIFY]` 实测齐备、`PROBLEMS=0`、全量结果原文含 6 红）；`

**是否闭合**：**闭合**。`plan-writeface-gap.md:6` 记 `fixed-in-project` 且例外已人工追认；追认载体 `.agenticdoc/gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md`（110 行）：

- `:8` `status    : ratified-by-human（2026-09-25T03:09:28+00:00 追认；见 §6）`
- `:72` `**decision: approved by user-via-pm-window at 2026-09-25T03:09:28+00:00**`
- `:86` `**decision-2: approved by user-via-pm-window at 2026-09-25T06:48:31+00:00（D-2：三处越表改动追认）**`
- `:104` `**decision-3: accepted-as-known-leftover by user-via-pm-window at 2026-09-25T06:48:31+00:00（D-3 / W-1）**`
- 终态位：`.agenticdoc/_index.parallel:41` `| gui-skeleton-shell | idle | DONE | — | — | — | 2026-09-25 14:48 |`

**教训（逐字）**

- `plan-writeface-gap.md:57` `1. **每条 task 的白名单必须覆盖"本阶段可能出现的全部失败面"**，否则 plan 写下来那一刻就不可收敛。`
- `plan-writeface-gap.md:58` `2. **"某个 key 引入的红"必须显式指派 owner**（写进某条 task 的判据或白名单），**不能默认"下一阶段会修"**。`
- `plan-writeface-gap.md:59` `3. 判据里出现"全量套件仍 `failed=0`"这类**跨阶段门槛**时，必须同时写明"**若红且不在本阶段写面内**怎么办"。`
- `_pitfalls.md:742` `### 43.2 plan 级缺口：新引入的红没有任何 task 有权修（比 idle 更根本）`；其 `:748`-`:751` 记"处置（PM 窗口）= 走重冻结申请"，`:752`-`:754` 记与上文同义的三条规则。

**"写面缺口"同族（A-01..A-07 全表，逐字）**：台账在 `.agenticdoc/_autopilot/reflect/_index.md`；表头 `:9` = `| 编号 | 归因 | 类别 | 影响面 | status |`，行 `:11`-`:17`：

- `:11` `| A-01 | [`read-cap-dead-config.md`](read-cap-dead-config.md) | framework（配置生效面） | L3 验证器被 8 次读上限饿死 → 2 key stalled，L3 全绿不可达 | **fixed-in-worktree**（已由人工提交 `6254783b6`） |`
- `:12` `| A-02 | [`done-vocabulary-mismatch.md`](done-vocabulary-mismatch.md) | framework + 工程契约 | `verify->done` 恒 blocked → **Stage 1 的 4 个 key 全部命中** | `workaround`（PM 手工收口；已 handoff R1/R2） |`
- `:13` `| A-03 | [`verdict-surface-vs-archive-surface.md`](verdict-surface-vs-archive-surface.md) | framework（worker 产出面） | L3 实质 PASS 被判 `below`（读错文件） | `workaround`（PM 逐字转写 + 来源标记） |`
- `:14` `| A-04 | [`stalled-gate-replay.md`](stalled-gate-replay.md) | framework（conductor 幂等） | 12 小时生成 **6684** 个门禁文件洪泛 | **fixed-in-worktree**（未提交；已 handoff） |`
- `:15` `| A-05 | [`idle-watchdog-vs-long-command.md`](idle-watchdog-vs-long-command.md) | framework（worker 看门狗） | exec task 两次被杀，**内容零错** | **fixed-in-project**（env 注入，已实测）+ handoff 附 C |`
- `:16` `| A-06 | [`plan-writeface-gap.md`](plan-writeface-gap.md) | 工程 plan | P5 不可过 / P6 不可修 → key 结构性不收敛 | **fixed-in-project**（重冻结例外，待人工追认） |`
- `:17` `| A-07 | [`powershell-bom-kills-serve.md`](powershell-bom-kills-serve.md) | human（PM 自伤） | mw serve / conductor / launcher **全栈退出** | **fixed-in-project** |`

A-06 所属分类行：`_autopilot/reflect/_index.md:30` `| ⑤ 写面与 owner | A-06 | plan 的白名单必须覆盖本阶段**可能出现的全部失败面**；每个红必须有 owner |`

**本 RQ 新发现的两点留痕缺陷（供机制取值）**

1. `_autopilot/reflect/_index.md:16` 的 status 仍写"**待人工追认**"，而 `plan-writeface-gap.md:6` 已写"已于 2026-09-25T03:09:28+00:00 经人工**追认**"——**台账行是陈旧快照**（与 A-10 同类：判定面未随最终轮刷新）。
2. A-06 的红清单只有散文计数（"6 个红在 P1–P5 窗口内引入"，`plan-writeface-gap.md:7`），`§2 证据锚点`（`:26`-`:33`）逐红给了现象与测量值，但**没有机器可读的"红 → owner"台账**（与 `plan-writeface-gap.md:58` 自己立的规则相反）。
### Q2 — 逐字证据补全（附两处引用可核性缺陷）

#### (a) `cli-run-state-and-events` 的 L3 / `REPAIR-R1-F1`

- **L3 轮次号**：`cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:1` = `# L3 质检复评（第 2 轮）— key `cli-run-state-and-events`（VERIFY · loop l3 · attempt 2）` ⇒ 第 2 轮 / attempt 2。
- **机器行原文（唯一权威）**：`cli-run-state-and-events/evidence/runs/repair-r1-out-20260925-r3.txt:220` =
  `[VERIFY] REPAIR-R1-F1: cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True`
  （同载荷另见 `…-r2.txt:239`；`…-r1.txt:209` 的 `cli_groups=-1` 是采集脚本派生字段缺陷，L3 已如实披露。）
- **L3-a2 §B 表行完整上下文**：`cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:22` =
  `| F-1 跨 key 红 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged` | **未闭合（按设计）**：当前树复跑仍红（rc=1，`cli_groups=13` vs 该用例冻结 12），owner=`cli-hitl-channel`，挂账交接、本 key 不修（写面纪律正确） | `repair-r1-out-20260925-r3.txt:220`（`REPAIR-R1-F1: rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True`）+ §F-1 原始 pytest 输出 |`
- **同级 needs-rerun 行**：同文件 `:83` =
  `| N-1 | 跨 key 红 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（第 1 轮 F-1 承接） | r3（10:49Z）实测仍红（`cli_groups=13` vs 冻结 12）；owner key 的修复是否已落地，本 key 记录无法证明 | `python -X utf8 -m pytest tests/test_hitl_channel.py -k top_level_command_groups -s -q`（期望 owner 修复后绿） | **`cli-hitl-channel`**（一行修复 = `TOP_LEVEL_GROUPS` 插入 `"runs"`）；conductor done 事务前确认收口或显式挂账 |`
- **verdict 结论句**（key 级）：`cli-run-state-and-events/l3-report.md:17` =
  `- **F-1（跨 key 红）未闭合（按设计）**：r3 实测仍红（`cli_groups=13` vs 冻结 12，r3:220）；owner=`cli-hitl-channel`，挂账交接、本 key 写面外不修，纪律正确。`
- **key 级裁定句**：`cli-run-state-and-events/l3-report.md:58` =
  `**裁定：QUALITY GATE = PASS（第 2 轮维持；遗留可归因、无悬空）**——建议 conductor 完成 N-1/N-2/N-3 确认后落 done 三件套。`

#### (b) `cli-hitl-channel` 的 L3 §遗留 `K-1`

- **实际路径**：报告在 `cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md`（第 1 轮，102 行）与 `cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a2/report.md`（第 2 轮，71 行）；key 级摘要 `cli-hitl-channel/l3-report.md`（73 行）。
- **K-1 逐字完整上下文** = `cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md:68`（§"已登记遗留（去向均已在案，不悬空）"）=
  `- **K-1..K-4**（4 条已知红）：K-1 兄弟 key 新增顶层组 `runs` 致本 key PG-2 断言（12 组）红；K-2 本 key P1 的 `conftest.py` 子 env 改名（`env`→`child_env`）触发 `tests/gui_contract/paths_encoding.py` 静态匹配器 0 命中；K-3/K-4 本 key P4 的 `gate_service.write_acceptance`（design D-007.2/D-008/PG-3 明文要求）与两条既有只读源码守卫（token 扫描，连 docstring 提及 `write_text` 都判红）冲突。owner 与一行级修法均已登记（P7 §9.5 / P4 L-2/L-3/L-4；P4 明确拒绝以改名/别名绕过守卫——避免假绿，处置正确）。`
- **同报告"遗留什么"摘要行** `:96` =
  `- **已登记遗留**：4 条已知红 K-1..K-4（owner 在案，修复面均在本 key 白名单外）、A-1 上游 17 处格式违规（解析面 0 失效）、R-1/R-2/R-3 重冻结申请（契约 owner）、N6 一行既有形状（另立 AC）、`push` 归 Stage 3 key、口径登记类（N1/N7/N9/DEFAULT_TIMEOUT_SEC）。`
- **第 2 轮把 K-1 转成 NR-B**：`cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a2/report.md:65` =
  `| **NR-B** | `python -X utf8 -m pytest tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（+ 守卫网 G4 复跑） | K-1 仍红（`known_red_rc` 第 1 位 = 1，`repair-a1-evidence.txt:408` 完整失败输出在案）：第 13 个顶层组 `runs` 由兄弟 key 的未跟踪 `migrator/commands/cmd_runs.py` 引入，本 key PG-2 字面量（12 组）需 owner 更新 | 兄弟 key / PM 更新 PG-2 的 12 项字面量（或兄弟 key 撤 `runs` 组）后 |`
  （key 级 `cli-hitl-channel/l3-report.md:58` 同内容。）
- **引用可核性缺陷（本 RQ 新发现）**：申请文件 `_autopilot/evidence/cross-key-repair-request-20260925-n1.md:30` 写：
  `- `cli-hitl-channel` L3 报告 §遗留第 96 行：`K-1 兄弟 key 新增顶层命令 runs 下本 key PG-2 断言（12 组）红，owner 在跨 key 修复轮（不在本 key 写面内）`。`
  **核对结果**：`l3-a1/report.md:96` 是上方那条"已登记遗留"摘要，**不含** "owner 在跨 key 修复轮"；`:68` 的 K-1 详细行也不含。l3-a2（71 行）与 key 级 `l3-report.md`（73 行）**根本没有第 96 行**。
  搜索过的模式：`跨 key 修复轮`、`owner 在跨 key`、`兄弟 key 新增顶层命令 runs`、`新增顶层命令 runs 下`；范围 = 整个 `E:\CLI_workspace\FeatureMigrator`（`.agenticdoc/**` + 源码 + 文档）。全库命中 `跨 key 修复轮` 仅 2 处：申请文件 `:30` 与该申请的执行证据 `_autopilot/evidence/xkey-n1-repair-20260926.txt:144`（后者逐字转引前者）。
  ⇒ **该引文是"带引号但非逐字"的转述**，且"§遗留第 96 行"的定位与内容都不成立。这是本机制要消灭的取证形状（人写散文引文不可核）。

#### (c) `tests/test_hitl_channel.py`

- **实际路径**：`tests/test_hitl_channel.py`（repo 根 `E:\CLI_workspace\FeatureMigrator`，未跟踪文件）。
- **`TOP_LEVEL_GROUPS` 定义处** = `tests/test_hitl_channel.py:241`-`:244`：
  - `:241` `#: PG-2 counting口径: the top-level command groups of `migrator --help` (a new group,`
  - `:242` `#: e.g. `hitl`, would make the comparison below fail).`
  - `:243` `TOP_LEVEL_GROUPS = ("agent", "analyze", "branch", "config", "gate", "gui", "init",`
  - `:244` `                     "install-hooks", "mcp", "mr", "project", "runs", "validate")`
- **`:268` 附近断言原文** = `tests/test_hitl_channel.py:261`-`:271`：
  - `:261` `def test_top_level_command_groups_unchanged(run_cli):`
  - `:262` `    """PG-2: `migrator agent answer` is a **sub-command**; the top level keeps its groups."""`
  - `:263` `    groups = _help_groups(run_cli)`
  - `:264` `    subcommands = _help_groups(run_cli, "agent")`
  - `:265` `    print(f"[COUNT] cli_groups={len(groups)} groups={groups} "`
  - `:266` `           f"agent_subcommands={sorted(subcommands)}")`
  - `:268` `    assert tuple(groups) == TOP_LEVEL_GROUPS, f"top-level groups changed: {groups}"`
  - `:269` `    assert "agent" in groups`
  - `:271` `    assert "answer" in subcommands and "run" in subcommands`
- **引用缺陷（本 RQ 新发现）**：申请文件 `:19` 写"断言 tests/test_hitl_channel.py:268 期望 12 组（TOP_LEVEL_GROUPS，定义见该文件 :1 附近）"——"`:1 附近`"**不成立**，定义在 `:243`-`:244`。旁证：`cli-run-state-and-events/workers/ap-cli-run-state-and-events-004-cancel-channel-and-tree-kill/trace.log:313` 在同一时段用 `rg -n "TOP_LEVEL_GROUPS"` 得到的正是 `243:TOP_LEVEL_GROUPS = ("agent", "analyze", "branch", "config", "gate", "gui", "init",`。
### Q3 — 时间线（还原）

| 事件 | 时间（记录原样） | 出处（file:line / 命令） |
|---|---|---|
| `cli-hitl-channel` 开工 | `2026-09-25 15:00`（本地） | `cli-hitl-channel/pm-state.md:7` |
| `cli-run-state-and-events` 开工 | `2026-09-25 15:03`（本地） | `cli-run-state-and-events/pm-state.md:7` |
| `runs` 顶层命令落地（产品面） | `migrator/commands/cmd_runs.py` mtime `2026-09-25 16:46:07`；注册点 `migrator/cli.py:60` `cli.add_command(cmd_runs)`；组名 `migrator/commands/cmd_runs.py:43` `@click.group("runs")` | 本会话 `Get-Item` / `read` |
| 首次记录的跨 key 红（B 侧，= CK-1） | P4 证据 `cli-run-state-and-events/evidence/runs/plan-p4-cancel-20260925.txt:203`-`:206`（`:205` `exit_code=1 elapsed_s=1.89 summary=1 failed in 1.31s`）；登记行 `cli-run-state-and-events/tasks/004-cancel-channel-and-tree-kill.md:231`；该证据 `:216` 记 CK-1 归因（"owner = key `cli-hitl-channel`"）。P4 运行 id 前缀 `20260925T092356Z` | 见左 |
| B 侧 L3 第 1 轮 | report mtime `2026-09-25 18:25:27`（本地） | `Get-Item cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a1/report.md` |
| A 侧 L3 第 1 轮 | report mtime `2026-09-25 18:26:32`（首次登记 K-1..K-4，`:68`） | `Get-Item cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md` |
| B 侧 EXECUTE 收口绿证 | `2026-09-25T10:14:54Z`（=18:14:54 本地，21 passed） | `cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:8` |
| B 侧修复轮 r1/r2/r3 | `10:31Z / 10:40Z / 10:49:13Z`（=18:31/18:40/18:49 本地）；r3 = `46 passed` | 同上 `:8`；`cli-run-state-and-events/evidence/runs/repair-r1-out-20260925-r3.txt:221` |
| A 侧修复轮 repair-a1 的 AFTER | 启动 `19:03:12` / 完成 `19:05:56`（本地） | `cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a2/report.md:20` |
| B 侧 L3 第 2 轮 | report mtime `2026-09-25 19:00:14`；`quality-gate-report-20260925-190050.md`；pm-state PASS `autopilot 2026-09-25T11:00:50Z` | `Get-Item`；`cli-run-state-and-events/pm-state.md:28` |
| A 侧 L3 第 2 轮 | report mtime `2026-09-25 19:20:08`；`quality-gate-report-20260925-192054.md`；pm-state PASS `autopilot 2026-09-25T11:20:54Z` | `Get-Item`；`cli-hitl-channel/pm-state.md:28` |
| **`cli-hitl-channel` DONE** | `2026-09-25 19:20`（本地） | `cli-hitl-channel/pm-state.md:5`/`:9`；`_index.parallel:42`；`_project_log.md:192` |
| **`cli-run-state-and-events` DONE** | `2026-09-26 10:12`（本地；其 L3 PASS 在 09-25 19:00，晚了约 15h） | `cli-run-state-and-events/pm-state.md:5`/`:9`；`_index.parallel:43`；`_project_log.md:193` |
| 申请文件创建 | 字段 `created_at : 2026-09-25T02:20Z` | `_autopilot/evidence/cross-key-repair-request-20260925-n1.md:6` |
| 人工追认 | `2026-09-26T03:04:05+00:00` | 同上 `:57` `**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**` |
| 修复执行收口 | `2026-09-26T03:05:59Z`（§6 执行结果） | 同上 `:65` |
| 修复落盘 | 测试文件 mtime `2026-09-26 11:04:39`；证据 `_autopilot/evidence/xkey-n1-repair-20260926.txt` mtime `2026-09-26 11:05:51`；申请文件 mtime `2026-09-26 11:07:03`（均本地） | 本会话 `Get-Item` |
| 修复 worker | `_scratch/workers/xkey-n1-hitl-groups-repair`（`type: coding`，`exit=0 / 1m / 26 tools`） | `_scratch/workers/xkey-n1-hitl-groups-repair/task.md:1`；申请文件 `:67` |

**时间线异常/新发现（供机制取值）**

1. **申请文件 `created_at` 与内容自相矛盾**：`created_at : 2026-09-25T02:20Z`（`:6`）写成 09-25，但它引用的 A 侧 L3-a2 report 直到 `2026-09-25 19:20 本地` 才落盘、B 侧 L3-a2 到 `19:00 本地` 才落盘。按 `decision (2026-09-26T03:04:05Z) − created_at (02:20Z) ≈ 44min` 的一致性推断，`created_at` 的日期应为 **2026-09-26**（`02:20Z` = `10:20 本地`）。即该字段有一日之差的手写错误。
2. **B 侧 key 是"带着未闭合的跨 key 红 DONE"的**：`cli-run-state-and-events` 于 `2026-09-26 10:12` 本地落 DONE（`pm-state.md:9`），而其 N-1（=REPAIR-R1-F1）仍在 needs-rerun 清单里挂账（`l3-report.md:54` / `workers/…-l3-a2/report.md:83`）。申请文件在 DONE 之后 8 分钟（`10:20 本地`）起草。⇒ 现有状态机允许"挂账即 DONE"，跨 key 红**不阻塞** key 关账，只留一条口头-ish 的挂账。
3. A 侧 `K-1` 首次登记（`l3-a1` mtime 18:26:32）只比 B 侧 `l3-a1`（18:25:27）晚 ~1 分钟 ⇒ 两侧是各自独立登记的（不是互读后确认），与申请文件 `:32` 的归纳一致。

### Q4 — "跨 key 修复轮"这一概念

**结论：未发现它作为框架既有承诺或阶段定义存在；它是 A 侧 L3 报告写下的一个"预期中的通道"，没有任何已存在的载体。**

搜索范围与结果：

- `.agenticdoc/_autopilot/_roadmap.md`（40 行，全文已读）：只有 Stage 1/2/3。Stage 2 标题 `:18` `## Stage 2: 运行态 · 事件流 · 运行控制与人在环`；其 `Keys` 表 `:24`-`:29` = `cli-run-state-and-events`(`:25`)、`cli-hitl-channel`(`:26`)、`gui-live-monitor`、`gui-run-control-hitl`、`gui-monitor-hitl-e2e`(`:29`)。**没有**任何 repair / 修复轮 / cross-key 阶段或 key。
- `.agenticdoc/_index.parallel`（43 行）：只有 key 状态表，两 key 行 `:42`/`:43`；无阶段/通道定义。
- `.agenticdoc/_project_log.md`：两 key 行 `:192`/`:193`；无"跨 key 修复轮"条目。
- `.agenticdoc/_autopilot/reflect/**`（`_index.md` + 10 个归因文件）：无该概念。
- `.agenticdoc/_arch_snapshot.md`（`:17`/`:19` 只提"跨 key refine"）、`goal.md`：无。
- `.agenticdoc/_workers.parallel` / `_workers.acked`：无。
- 搜索模式：`跨 key 修复轮`、`cross-key repair`、`跨key修复`、`修复轮`；范围 = 整个 `E:\CLI_workspace\FeatureMigrator`。
- **唯一命中 `跨 key 修复轮` 的是申请文件 `:30` 与其执行证据 `_autopilot/evidence/xkey-n1-repair-20260926.txt:144`（后者逐字转引前者）。**

**既有的相邻概念（但不是"跨 key"通道）**：框架内已存在的是**单元 key 内的"修复轮"**（VERIFY 阶段承接 L3 needs-rerun 的修复 worker）：

- `cli-run-state-and-events/workers/ap-cli-run-state-and-events-repair-a1/report.md:1` `# 修复轮 1 报告 — key `cli-run-state-and-events``
- `cli-hitl-channel/evidence/runs/repair-a1-evidence.txt` + `cli-hitl-channel/workers/ap-cli-hitl-channel-repair-a1/`（同 key 修复轮）
- `cli-readonly-snapshot/workers/ap-cli-readonly-snapshot-repair-a1/report.md:1` `# 修复轮 1 报告 — key `cli-readonly-snapshot``
- `gui-contract-mock-tests/workers/ap-gui-contract-mock-tests-l3-a2/report.md:7` 亦有 "repair round" 表述。

该"修复轮"始终**受本 key 写面白名单约束**：B 侧修复轮对 F-1 的处置就是"不修、挂账交接"（`cli-run-state-and-events/workers/ap-cli-run-state-and-events-repair-a1/output.md:16` `**F-1** 跨 key 红 … | 当前树复跑复核 `rc=1`（`cli_groups=13` vs 冻结 12）；该文件属 `cli-hitl-channel` 写面（mtime 未变）→ **不修、挂账交接**（一行修复建议：`TOP_LEVEL_GROUPS` 加入 `"runs"`）`）。因此它**在结构上不可能**承接跨 key 红。

**它承诺的载体是什么**：A 侧 L3 原文里的"跨 key 修复轮"**没有**指向任何已存在的 key 或 roadmap 阶段。申请文件 §3 候选处置表（`:34` 起）把候选载体写成 Stage 2 的 `gui-monitor-hitl-e2e`：`:39` `| R2 | 把红挂账到 Stage 2 的 E2E key（`gui-monitor-hitl-e2e`）的关账前置清单，由其后一轮修复 | 该 key 是否具备 `tests/**` 写面未知，可能重演 A-06（红继续无 owner） |`（roadmap 里该 key 在 `:29`）。但 R2 **未被采纳**（最终采纳 R1 = 人工授权的最小修复，`:38` + `:57`）。
**⇒ 框架当时预期存在一条跨 key 修复通道（L3 用它解释"为什么红可以不在本 key 修"），但该通道在 roadmap / `_index.parallel` / `_project_log.md` / reflect 台账中均不存在。**（这正是本 key 要补的缺口。）
### Q5 — `tests/test_hitl_channel.py` 的解冻/改动史

事实（按时间）：

1. **git 侧无历史**：该文件当前是**未跟踪**文件 —— 本会话实测 `git status --porcelain -- tests/test_hitl_channel.py` = `?? tests/test_hitl_channel.py`；`git log -- tests/test_hitl_channel.py` 无输出。⇒ 无 commit 级历史可查。
2. **创建（P1，`cli-hitl-channel` 自己）**：`cli-hitl-channel/tasks/001-hitl-contract-input-and-red-baseline.md:191` = `| `tests/test_hitl_channel.py` | 11,027 B | `440ec74a21851f51` | AC-001/AC-003/AC-008：真值表 4 组合、4 个 `input(` 站点 + `KIND_SPECS`、4 条 legacy 分支互异、通道端到端 12 键请求 |`（同值见 `cli-hitl-channel/workers/ap-cli-hitl-channel-001-hitl-contract-input-and-red-baseline/output.md:29`）。
3. **第一次修改（P3，仍是 `cli-hitl-channel` 自己）**：`cli-hitl-channel/tasks/003-stdin-sites-and-answer-surface.md:177` = `- `tests/test_hitl_channel.py` 39,468 B `43847db068b3d20b`：P1 红骨架转绿（4 条端到端链路 / 真值表 / 逐点策略 / 出口形态，共 22 用例，未删用例、未放宽断言）`（同值见 `cli-hitl-channel/evidence/runs/plan-p3-sites-and-answer.txt:334`、`cli-hitl-channel/workers/ap-cli-hitl-channel-003-stdin-sites-and-answer-surface/output.md:17`）。
4. **第二次修改（跨 key 授权修复 XKEY-2026-09-25-01）**：
   - `_autopilot/evidence/xkey-n1-repair-20260926.txt:15` `old sha256      : 43847DB068B3D20B056FD8AD5C2E841BF907847C222B3636AD76AD95BD5146DE`
   - 同 `:17` `new sha256      : 90A52D9B8774D262DDAA6B2556949B2913EC73495D8F14C8253086B58D4D19F8`
   - 同 `:20` `是否放宽断言=否    （断言主体 `assert tuple(groups) == TOP_LEVEL_GROUPS` 逐字节未动；改的只是期望常量本身的成员集合，…`
   - 同 `:41` `唯一改动 = 第 244 行在 `"project", ` 与 `"validate"` 之间插入 `"runs", `（字母序位置，符合该元组既有排序约定与格式）。`
   - 同 `:23` `git 状态（该文件为未跟踪新文件，故无 `git diff` 可给；按任务 §5 以 `git status --porcelain` + 前后 sha 说明）:`
   - 申请侧同记：`cross-key-repair-request-20260925-n1.md:71`-`:74`（唯一改动 / old sha256 / new sha256 / 是否放宽断言）。
5. **当前（本会话实测）**：sha256 = `90A52D9B8774D262DDAA6B2556949B2913EC73495D8F14C8253086B58D4D19F8`（与修复记录一致），mtime `2026-09-26 11:04:39`。

结论：

- 搜索模式 = 全库检索 `test_hitl_channel.py` 的 sha16/指纹记录；**全部命中只有三个指纹**：`440ec74a21851f51`（P1）、`43847db068b3d20b`（P3）、`90a52d9b8774d262`（XKEY 修复）。⇒ **未发现**除 `cli-hitl-channel` 自身与本次 XKEY 授权修复之外的任何 key 改过该文件。
- P1/P3 两次改动是**所属 key 写面内的正常写入**，留痕形状 = "task 交付物表 + 证据文件里的 sha16"，**没有** `old→new sha256 + reason + 是否放宽断言 + decision` 的治理级形状（当时不需要授权）。
- 只有 XKEY 修复带**完整治理级留痕**：`old/new sha256` + `reason` + `是否放宽断言=否` + 新文件名证据（A-09）+ 人工 `decision` 行 + 执行结果 §6 + 双侧登记闭合声明。
- ⇒ **本机制要复刻的证据形状 = XKEY 这一份**（`xkey-n1-repair-20260926.txt` §1-§7 + 申请文件 §4/§5/§6），而不是 P1/P3 的"task 表 + sha16"形状。
- 另注意该文件**从未 commit**（工作树 untracked）⇒ 它的"冻结"只存在于文件系统 + `.agenticdoc` 记录中，git 不能提供解冻/回收/审计能力；机制须自建解冻审计（不能依赖 VCS）。

### Q6 — 当前状态核对（静态，未跑测试）

**该红今天是否仍存在 —— 静态比对结论：已对齐，静态层面不再存在。**

| 侧 | 静态读数 | 出处 |
|---|---|---|
| migrator CLI 注册表 | `migrator/cli.py` 共 13 次 `add_command`：`cmd_init / cmd_config / cmd_branch / cmd_analyze / cmd_validate / cmd_hooks / cmd_mr / cmd_project / cmd_agent / cmd_mcp / cmd_gate / cmd_gui / cmd_runs`（`migrator/cli.py:48`-`:60`；`cmd_runs` 在 `:60`） | `read migrator/cli.py` |
| 各组真实组名 | `init`(`migrator/commands/cmd_init.py:38`) · `config`(`cmd_config.py:15`) · `branch`(`cmd_branch.py:8`) · `analyze`(`cmd_analyze.py:32`) · `validate`(`cmd_validate.py:48`) · `install-hooks`(`cmd_hooks.py:7`) · `mr`(`cmd_mr.py:9`) · `project`(`cmd_project.py:14`) · `agent`(`cmd_agent.py:313`) · `mcp`(`cmd_mcp.py:65`) · `gate`(`cmd_gate.py:38`) · `gui`(`cmd_gui.py:32`) · `runs`(`cmd_runs.py:43`) = **13 组** | `grep -n "@click\.(group\|command)" migrator/commands/*.py` |
| 测试冻结期望 | `tests/test_hitl_channel.py:243`-`:244` `TOP_LEVEL_GROUPS` = `("agent", "analyze", "branch", "config", "gate", "gui", "init", "install-hooks", "mcp", "mr", "project", "runs", "validate")` = **13 项**（字母序与 CLI 组名集合一致） | `read tests/test_hitl_channel.py` |

⇒ 静态 `13 == 13`；`tests/test_hitl_channel.py:268` 的 `assert tuple(groups) == TOP_LEVEL_GROUPS` 在静态层面不再有分歧。

**未实测声明**：本 RQ **没有运行** `pytest`（会写 `.pytest_cache` / `__pycache__`，且当前 `gui-live-monitor`、`gui-run-control-hitl` 处于 EXECUTE，按既有 N-3 记录并行活动会翻转端口/计时类结果）。"红消失"的**实测确认仍是推迟项**：申请文件 `:63` 与证据 `:133`-`:137` 明写"全量套件红数 1→0 … 留待下一个安静窗口执行并落新文件名证据"（`VC-058` 类判据）。本次修复只做了**定向复跑**：证据 `:98` `22 passed in 48.22s`（修复 worker）+ 申请文件 `:75` 记 PM 窗口独立复跑 `22 passed in 48.80s`。

**申请文件是否已有 decision 行 —— 有，且已执行收口**：

- `cross-key-repair-request-20260925-n1.md:7` `status         : authorized-R1（2026-09-26T03:04:05+00:00 经人工批准）`
- `:57` `**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**`
- `:58`-`:63` 批准范围（唯一可写路径 `tests/test_hitl_channel.py` + 仅 `TOP_LEVEL_GROUPS` 成员增减 + 一组禁止项 + `_scratch` 隔离 + 定向复跑为验收 + 全量确认推迟）
- `:65` `## 6. 执行结果（收口，2026-09-26T03:05:59Z）`；`:67` 修复 worker 行；`:71`-`:78` 结果表；`:80`-`:81` 双侧登记闭合声明；`:84` "仍未闭合（故意）"项。

### 附加发现 — 引文漂移（对机制的取证形状有直接影响）

- 申请文件自身的行号引用有两处不成立（Q2(b) 的"§遗留第 96 行"与内容不符；Q2(c) 的"定义见该文件 :1 附近"实际为 `:243`-`:244`）。
- 本 key 的上游基础语料 `spec-problem-framing-20260926.md` 对申请文件的行号引用也**与当前文件不符**（例：它引 `:6 request_id`，当前申请文件 `:4` 才是 `request_id`；它称申请文件"76 行"，当前为 84 行）。⇒ 同一份证据在不同时点被不同人按不同版本的手抄行号引用，**行号引用本身在漂移**。
- 这三点共同说明：靠"人写散文 + 手抄 file:line"互证的红/授权链路，**不可机器校验**。机制必须把"引用"变成可复算的机器字段（文件名 + 行号 + 该行的 sha256，或至少"写入时即校验存在"）。

## 结论 → 决策映射

| 结论（本 RQ 证据） | 支撑的 spec 决策 |
|---|---|
| A-06 是"红无 owner"同族的第一次出现，2026-09-24/25 发生，**已闭合**，闭合方式是"人工追认的重冻结例外"（`plan-writeface-gap.md:6/:41-:53`；`refreeze-request-…:72/:86/:104`）。 | §1.1 "为什么机制化" = 同族复发第二次；机制应把 A-06 的闭合方式（人工追认 + 精确例外表 + old→new sha256 + 禁止放宽）**从人写流程变成机器通道**。 |
| A-06 的三条教训（`plan-writeface-gap.md:57-:59`）= 写面覆盖失败面 / 红必须显式指派 owner / 跨阶段门槛必须写明"若红不在本阶段写面内怎么办"。 | §1.1 根因第 2 层；AC-001 账本（每个红必须有 owner 字段）+ R-1 机器可读化交接登记。 |
| A-06 台账行本身是陈旧快照（`_index.md:16` vs `plan-writeface-gap.md:6`），且无机器可读的"红→owner"台账。 | §2.2/§2.3：账本需"聚合 + 最终轮一致性"；AC-001 幂等去重 + AC-002 陈旧检测（同 A-10 家族）。 |
| 跨 key 红的两侧登记**都是纪律正确的拒修**（`REPAIR-R1-F1` / `K-1`），owner 字段都指向对方 key（`…l3-a2/report.md:22`、`…l3-a1/report.md:68`）。 | §1.1 根因第 3 层"检测/授权都在、缺传导通道"；§1.4 不改写面模型（不把 B 的文件划给 A）。 |
| **"跨 key 修复轮"不是既有机制**（Q4）：roadmap/index/log/reflect 全无此概念，唯一出现处是 L3 散文与其转引。 | §1.1 "本 key 做什么" = **新建**通道（而不是接入既有通道）；机制文档里必须显式定义这条通道，避免再次出现"只存在于散文里的通道"。 |
| 该红在 B 侧 key **带着开着的 N-1 挂账 DONE**（`pm-state.md:9` @09-26 10:12 vs 申请文件 `:6` @10:20）。 | §2.1/§2.3：done 门禁与挂账的关系要写清——机制要么禁止"跨 key 红 + DONE 长期并存"，要么把挂账做成机器可查且强制在合并点前收敛。 |
| 申请文件只授权"唯一可写路径 + 只改冻结常量的字面成员 + 禁止改断言/探针/migrator/**"，并且**实际执行完全落在该边界内**（Q5 的 XKEY 记录）。 | §2.3 边界机械强制；AC-005 "精确到冻结常量块行集合"（对应 `tests/test_hitl_channel.py:244` 一处插入）。 |
| XKEY 修复已把该红静态消除（Q6：13==13），但**语料级全量确认仍是推迟项**（`:63`/`:133-:137`）。 | §2.4/AC-004：机制必须有"已闭合（定向）/待安静窗口全量确认"这一显式中间态，不能把定向绿证当全量绿证。 |
| 解冻证据形状 = `old→new sha256` + `reason` + `是否放宽断言=否` + 新文件名证据（A-09）+ `decision` 行（Q5）。该文件**从未 commit**，冻结只靠文件系统 + `.agenticdoc` 记录。 | §2.3 解冻权只给人 + 证据包字段；AC-005/AC-006 取证形状；机制不得依赖 VCS 提供冻结/解冻审计。 |
| 引文漂移（申请文件 2 处行号错 + 上游基础语料行号错）：散文 + 手抄 file:line 不可核。 | §4 R-1：交接登记必须机器可读；AC-002/AC-003 工单须带"写入时即校验"的精确位置。 |
| A-06 的红清单无机器台账（`plan-writeface-gap.md:7` 仅散文计数）。 | §1.1 二阶根因（聚合缺失）；AC-001 账本聚合。 |

## 未发现项与开放问题（供 next research 承接）

- **未发现**任何把"跨 key 修复轮"写成阶段/key/承诺的文档（搜索模式与命中见 Q4）。
- **未发现**该测试文件被 `cli-hitl-channel` 之外的 key 改动的记录（Q5）。
- **未发现**机器可读的"红 → owner → 修复轮"台账（A-06 与 XKEY 两案都只有散文）。开放问题：XKEY 账本应以什么为单一真源（新文件？`reflect/_index`？`.agenticdoc/_autopilot/evidence/` 索引？）——本 RQ 只出证据，不做设计。
- **未实测**该红当前的 pytest 结果（Q6 为静态结论；定向绿证来自 `2026-09-26` 的两次 `22 passed`）。全量"红数 1→0"的实测是推迟项，需在安静窗口落新文件名证据。