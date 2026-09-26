# Research: 交接登记机器可读化 — 承载方式的最小侵入设计面（RQ-D1）

> Key: xkey-repair-mechanism / Phase: DESIGN（research RQ-D1，design.md 记录为 D-001 的输入）
> 日期: 2026-09-26
> 产出: 本文件为唯一写入；未改任何 key 文件、未改 FM 树任何文件、未跑写状态命令、未 commit
> 只读范围: 本仓 `packages/multi-workers/**`、`packages/coding-agent/src/extensions/agent-team-loop/**`、`packages/coding-agent/test/**`，以及 `E:\CLI_workspace\FeatureMigrator\.agenticdoc\**`（含 FM 语料）
> 行号口径: 当前工作区 dirty 树实测行号。仓内口径 = 本会话 `read`/`Select-String` 实测；FM 口径 = 本会话直接 `read` 实测。**FM 树是另一份工作区，其行号随其自身版本漂移**（RQ-2 已实证手抄行号漂移）；本文引用均给出被引文件路径 + 行号 + 该行可核验的逐字子串，design 只需信任本文件给出的 `file:line`。

## 决策问题

设计决策 **D-001（交接登记的承载方式）**：如何把"跨 key 交接登记"从散文升级为机器可读，且最小侵入？

- **Q1 写侧改造点**：L3 prompt 在 `conductor.py` 的哪一段构造（已知约 :1113-1124，只要求 `## Quality Gate Report` + `## Achieved` 两节）？若要新增"跨 key 登记"机器块，最小改动在哪里？框架现有 prompt 里是否已有结构化块先例（`[VERIFY] VC-NNN: k=v` 行、`[CHECKPOINT]` 判据、`[COUNT]`）——逐字引用形状与消费侧，给出每种先例的"写侧在哪、读侧在哪、若无读侧则写明"。
- **Q2 读侧改造点**：现有 L3 判定源解析的全部入口（`conductor.py:1076` 两节存在性、`:1155-1185` FAIL 三形态、`:1207-1213`）在哪？新增解析器应挂在哪里、与 `_l3_provenance_record`(:1267, 字段 :1293-1305) 的关系？能否把结构化登记并入 provenance sidecar 而不新增文件？
- **Q3 真实语料形状盘点**：读 FM 语料，逐字收集"跨 key 交接登记"在野外的**全部字形**；对每种字形标注出现位置、字段是**键值对**还是**自然语言**、能可靠抽出哪些字段（file/test_id/owner_key/handoff/冻结块）、抽不出的原因。
- **Q4 兼容解析可行性判定**：基于 Q3 语料，设计"最小解析器"需要哪些规则（键值对优先、自然语言兜底？），明确哪些字段在散文字形下无法可靠取得，以及该情况如何降级（spec AC-011 / §2.3「无登记只升级」）。
- **Q5 双侧测试锁（P-005）**：写侧（L3 输出形状）与读侧（conductor 解析）各自的可测点在哪？现有哪些测试文件覆盖 conductor 的 L3 解析路径（文件名 + 用例名）？新增测试应落在哪（现有 `test_autopilot_*.py` 命名族）？

## 调研方法与出处

### 只读纪律执行情况

- 未写入 FM（`E:\CLI_workspace\FeatureMigrator`）树的任何文件；未执行 `git add/commit/stash`；**未运行 `pytest`**（会写 `.pytest_cache`/`__pycache__`，且在 FM 有 key 处于 EXECUTE 时并行测试会翻转端口/计时类结果，见 FM `_pitfalls` N-3 记录）。
- 只读命令：`read`、`Select-String`、`Get-ChildItem`、`Test-Path`；无写命令、无状态推进命令。
- 本仓代码事实以 src 为准（`packages/multi-workers/**/*.py`、`packages/coding-agent/src/extensions/agent-team-loop/**`）；`dist/**` 只读且仅用于确认镜像存在，不作为行号出处。

### 关键检索（用于区分"未发现"与"存在但未找到"）

| 检索模式 | 范围 | 命中 | 结论 |
|---|---|---|---|
| `cross_key\|crosskey\|handoff` | `packages/multi-workers/**/*.py`（非 test） | 0 | 交接登记在框架 Python 侧无机器字段/解析器 |
| `\[VERIFY\]` | `packages/multi-workers/**/*.py`（非 test） | 3（`:1001`、`:1116`、`:1140`，全为 prompt 文案） | `[VERIFY]` 只有写侧提示、无读侧解析器 |
| `\[VERIFY\]` | `packages/multi-workers/test_*.py`、`packages/coding-agent/test/**` | 大量 | 全是**测试自打印/断言**，非运行时消费 |
| `\[COUNT\]` | 全仓 `*.py`/`*.ts`/`*.md`（排除 node_modules） | 2 个源文件：FM `tests/test_hitl_channel.py:265`（产品测试打印）、本 key 上游 research 文档引用 | 无任何解析器 |
| `CHECKPOINT` | `packages/coding-agent/src/extensions/agent-team-loop/**` | 写侧 `output-writer.ts`、读侧 `shared/heartbeat.ts` | 唯一"写侧 + 读侧都在"的机器块先例 |
| `ttl\|expiry\|expire\|deadline` | `gates.py, config.py, conductor.py` | 4（全为主循环 sleep / advance TimeoutExpired） | gate 无 TTL（RQ-3 已证） |
| `_l3_provenance_record` 调用点 | `conductor.py` | 定义 `:1267`，唯一调用 `:1555` | sidecar 是红来源的唯一现成机读落点 |

### 上游依据（本会话直接读取）

- 本 key：`spec.md`（§1.1 R-1、§2.4、§5、AC-011）、`key-decision.md`（D-001 待记）、`evidence/research/spec-reusable-parts-20260926.md`（RQ-3 §4/§7）、`spec-incident-corpus-20260926.md`（RQ-2）、`spec-problem-framing-20260926.md`（RQ-1）、`evidence/research/spec-code-facts-20260926.md`。
- 仓内代码：`packages/multi-workers/autopilot/conductor.py`（全文读，L3 段 `:1073-1700`）、`autopilot/gates.py`、`autopilot/config.py`、`autopilot/closure.py`；`packages/coding-agent/src/extensions/agent-team-loop/{shared/heartbeat.ts,worker/output-writer.ts,worker/worker-mode.ts,pm/pm-orchestrator.ts,pm/ui-bridge.ts,rag/research-doc.ts}`。
- 测试：`packages/multi-workers/test_autopilot_fail_marker_forms.py`、`test_autopilot_verdict_source_fallback.py`、`test_autopilot_verdict_provenance_guard.py`、`test_autopilot_verdict_freshness.py`、`test_autopilot_conductor_exec.py`、`test_autopilot_closure.py`、`test_autopilot_e2e.py`。
- FM 语料（只读，逐字）：见 §Q3 逐项出处。

---
## 发现

### Q1 — 写侧改造点

#### Q1.1 L3 prompt 的构造位置与逐字形状

`conductor.py:1113-1127`（函数 `_l3_prompt(key, attempt)`）是 VERIFY 阶段唯一构造 L3 reviewer 任务书正文的地方。逐字（`conductor.py:1113-1127`）：

```
def _l3_prompt(key: str, attempt: int) -> str:
    return (
        f"L3 质检复评（key {key}，第 {attempt} 轮）:\n"
        "- 审查 EXECUTE 期 worker 在 output.md 与 evidence/ 中记录的 [VERIFY] 输出"
        "（证据记录制：不重跑命令）\n"
        "- 需要重跑才能确认的验证命令标记 needs-rerun 并计入遗留\n"
        "- 你的 output.md 必含两节：\n"
        "  ## Quality Gate Report（VC 断言表逐条 PASS/FAIL + needs-rerun + 证据引用）\n"
        "  ## Achieved（达成摘要：做了什么 / 目标收益 / 遗留什么）\n"
        "- 两节承载于 output.md（首选）；长报告可置于 report.md 作为**文档化回退源**"
        "（判定按 output.md → report.md 优先级读取，"
        "任一份的任意行出现 FAIL 标记（表格单元格 / 项目符 / 结论行）即 below）\n"
        "- 判定源取证：output.md / report.md 须属于本轮（由同轮 trace.log 锚定）；"
        "事后补写的判定源会被标记 suspect 并按 below 处理"
    )
```

关键事实：
- prompt 只规定**两节**（`## Quality Gate Report` / `## Achieved`），且**没有任何跨 key 登记的机器字段要求**（`cross_key|crosskey|handoff` 全包 0 命中，见上检索表）。
- 该函数是纯字符串函数（无 IO、无参数依赖），是**最小侵入的写侧改动点**：改一处字符串即可新增机器块要求。
- prompt 由 `_verify_loop` 多处派发：`conductor.py:1514`（首轮 `l3-a1`）、`:1548`（no-verdict 再评）、`:1576`（suspect 再评）、`:1614`（closure reprompt，包裹 `closure.compose_reprompt_prompt(_l3_prompt(...), flines)`）；`:1660` 的 repair prompt 不含 `_l3_prompt`。故改 `_l3_prompt` 即覆盖全部 L3 轮次。

#### Q1.2 框架现有结构化块先例（逐字形状 + 写侧/读侧）

| 先例 | 逐字形状 | 写侧（file:line） | 读侧（file:line） | 判定 |
|---|---|---|---|---|
| `[VERIFY] VC-NNN: k=v` | `[VERIFY] VC-006: agg_lines=0 identical_baseline=true`；prompt 模板为 `[VERIFY] VC-NNN: key=value` | prompt 要求：`conductor.py:1001`（EXECUTE）、`:1116`（L3 审查面）、`:1140`（repair 补证据）；实际输出由 agent/test 写入 `output.md`/`evidence/`（FM 例：`cli-run-state-and-events/evidence/runs/repair-r1-out-20260925-r3.txt:220`） | **无读侧**：`packages/multi-workers/**/*.py` 非 test 检索 `[VERIFY]` 仅命中 :1001/:1116/:1140 三处 prompt 文案。TS 侧仅 `rag/research-doc.ts:245` 生成一个 `[VERIFY] VC-018`-**形状**的摘要字符串（`summarizeResearchDoc`，写侧输出，非读侧解析） | 有写侧、无读侧；是"人/agent 约定"而非机器契约 |
| `[CHECKPOINT]`（trace.log） | `[CHECKPOINT] <ISO-8601> elapsed=<n>s reads=<n> writes=<n> phases=<d>/<t> uniq_targets=<n> repeat_top=<k> risk=<low\|mid\|high>`（`output-writer.ts:194-201`） | `worker/output-writer.ts:191`（`appendCheckpoint`，写入 `<taskKey>/trace.log`）；驱动 `worker/worker-mode.ts:941`（`writeCheckpoint`） | `shared/heartbeat.ts:84-85`（`CHECKPOINT_LINE_RE`，**行首行尾锚定** `^...$`），消费于 `readTaskProgress`（`heartbeat.ts:101`、`:162-172`）→ `TaskProgress.checkpoint`；下游消费 `pm/pm-orchestrator.ts:575`、`pm/ui-bridge.ts:583/:680` | **双侧齐备**：唯一的"写侧 + 读侧 + 下游消费"完整先例 |
| `CKPT <n>m [machine] ...`（progress.md） | `CKPT <n>m [machine] ts=<ISO> reads=<n> writes=<n> phases=<d>/<t> repeat_top=<k> risk=<low\|mid\|high>`（`output-writer.ts:221-224`） | `worker/output-writer.ts:220`（`formatMachineCheckpoint`）→ `worker/worker-mode.ts:971` 调 `appendProgressLine` 写 `progress.md` | **无读侧**：`[machine]`/`CKPT` 在 TS src 仅出现在 output-writer 写侧与 worker-mode 的 steer 文案（`:113-131`）；无解析器 | 有写侧、无读侧 |
| `[GOAL_CHECK]` | `[GOAL_CHECK] phase=<n> goal_mtime=<ms>`（`output-writer.ts:272`） | `worker/output-writer.ts:272` | **无读侧**：`heartbeat.ts:100` 的 docstring 仅把它列为 legacy 行类型，`readTaskProgress` 不解析；`test/suite/dual-root-worker.test.ts:198` 只是测试断言 `trace.includes(...)` | 有写侧、无读侧 |
| `[COUNT]` | `[COUNT] cli_groups=13 groups=['agent', ...] agent_subcommands=['answer', 'run']` | **框架外**：FM 产品测试 `tests/test_hitl_channel.py:265` `print(f"[COUNT] cli_groups={len(groups)} groups={groups} agent_subcommands={sorted(subcommands)}")`；表面于 `repair-r1-out-20260925-r3.txt:76`（及 `:78` 复现） | **无任何读侧**（全仓 0 解析器） | 有写侧（被测程序自身）、无读侧 |
| `[REVISED @ YYYY-MM-DD]` | `[REVISED @ 2026-09-25]` | FM L3/修复报告散文（例 `cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md` 表内、登记行） | **无读侧** | 散文标记 |
| `cross_key_conflicts=<n>` | `证据 problems=0 cross_key_conflicts=2`；`唯一天窗：\`cross_key_conflicts=1\`（已登记，未修）` | FM `gui-skeleton-shell/tasks/002-panel-services-and-validation.md:220`（交付证据串）、`gui-skeleton-shell/workers/ap-gui-skeleton-shell-001-gui-deps-and-write-entries/output.md:14` | **无读侧**（仅计数，无聚合器） | 计数型散文字段 |

结论：**框架内唯一"写侧 + 读侧双侧齐备"的结构化块是 `[CHECKPOINT]`**（trace.log，形状 + 锚定正则 + 下游消费都在）；`[VERIFY]` 只有写侧提示、无读侧解析器——这正是 spec R-1 的机制性来源。若要给 `[XKEY]` 找一个可照抄的范式，应照抄 `[CHECKPOINT]` 的"写侧 formatter + 读侧锚定正则 + 类型化字段"三件套，而不是 `[VERIFY]` 的"仅有提示词"。

#### Q1.3 最小写侧改动

最小改动 = 在 `_l3_prompt`（`conductor.py:1113-1127`）的"必含两节"要求中**追加一行机器行要求**（不改节数、不改 `_l3_qualifies` 的判定契约）：

- 位置：`conductor.py:1119-1121`（`- 你的 output.md 必含两节：` 之后的 `## Quality Gate Report` 行附近）。
- 形状建议（键值对、行前缀唯一、不触发任何 FAIL 正则）：`[XKEY] file=<path> test_id=<id> owner_key=<key> handoff=registered frozen_block=<name>=<value>`。
- 为什么放在 `## Quality Gate Report` 之内：机器行随"已合格判定源"（`_l3_qualifies`，`conductor.py:1207-1212`）一起落盘，读侧可复用既有 `sources`（`conductor.py:1254-1258`）与 `_persist_l3_provenance`（`:1359`），**不需要新增文件、不需要改判定链**。
- 为什么不用新增"必含第三节"：`_l3_qualifies` 只认两节（`:1207-1212`）；新增必含节会改动判定契约（旧轮次输出若缺第三节即 below），侵入面更大；机器行内嵌在既有节内对旧轮次天然向后兼容（缺行 = 无登记）。

**最小侵入对照**（写侧三选一）：

| 方案 | 改动点 | 侵入面 | 兼容性 |
|---|---|---|---|
| A（推荐）机器行内嵌 QG 节 | `_l3_prompt` 加 1 行 | 1 个字符串函数 | 旧输出缺行 = 无登记，天然兼容 |
| B 新增可选节 `## Cross Key Handoff` | `_l3_prompt` 加节 + 读侧用 `_md_section` 抽取 | 1 个字符串函数 + 读侧新增节抽取（不动 `_l3_qualifies`，节缺失仍合法） | 兼容，但读侧多一个概念 |
| C 新增必含第三节 | `_l3_prompt` + `_l3_qualifies` | 改判定契约（`:1207`） | **不兼容**旧轮次（缺节即 below）——不推荐 |

---
### Q2 — 读侧改造点

#### Q2.1 现有 L3 判定源解析的全部入口（实测行号）

| # | 入口（def / 常量） | file:line | 作用 | 现役/仅测试 |
|---|---|---|---|---|
| 1 | `_md_section(text, header)` | `conductor.py:1076` | 抽取一个 `## ` 节（到下一个 `## ` 为止）；**两节存在性判定的唯一实现** | 现役（被 2/5/8/9 复用） |
| 2 | `_parse_l3_output(project_root, key, attempt)` | `conductor.py:1091`；两节读取 `:1104-1105`；`\|FAIL` 判定 `:1108` | 旧版单一来源解析（只读 `workers/ap-<key>-l3-a<attempt>/output.md`），缺节或 `\| FAIL` → below | **仅测试调用**（`conductor.py` 内无调用者；调用点仅在 `test_autopilot_readcap_injection.py:865/:868/:871`、`test_autopilot_verdict_freshness.py:615/:622/:629/:632`、`test_autopilot_verdict_source_fallback.py:368/:480/:538/:544/:551/:554`） |
| 3 | `_L3_SOURCE_ORDER` | `conductor.py:1152` | `("output.md", "report.md")` 回退优先级 | 现役 |
| 4 | FAIL 三形态常量 | `_L3_FAIL_RE` `:1155`、`_L3_FAIL_BULLET_RE` `:1159`、`_L3_FAIL_PROSE_RE` `:1160`、`_L3_FAIL_ZERO_RE`（token 局部零值豁免）`:1161` | 表格单元格 / 行首项目符 / 结论行三形态 + 零值豁免 | 现役 |
| 5 | `_l3_fail_marker_line(text)` | `conductor.py:1164` | 全文逐行扫描，返回首个 FAIL 行逐字（否则 None） | 现役 |
| 6 | `_l3_source_paths(key_dir, task_key)` | `conductor.py:1192` | 候选源路径（存在性不判） | 现役 |
| 7 | `_l3_read_source(path)` | `conductor.py:1197` | 可读文本；缺失/`OSError` → None | 现役 |
| 8 | `_l3_qualifies(text)` | `conductor.py:1207`；两节判定 `:1210-1211` | 两节都存在才"合格" | 现役 |
| 9 | `_l3_resolve_source(sources)` | `conductor.py:1215` | fail-closed 优先级：任一源带 FAIL → below + 该源 + 首命中行；否则首合格源 → meets；否则 below + None | 现役 |
| 10 | `_l3_round_verdict(project_root, rows, key, attempt)` | `conductor.py:1233`；worker 终态先判 `no-verdict` `:1251-1252`；`sources` 构造 `:1254-1258`；`_l3_resolve_source` 调用 `:1261` | **现役聚合入口**（状态门 → 可读源门 → 优先级解析），返回 `(verdict, worker_status, source, fail_line)` | 现役（唯一调用点 `:1520`） |
| 11 | `_l3_provenance_record(...)` | `conductor.py:1267`；字段字面量 `:1294-1305` | 只读 provenance 记录（同轮 trace.log 锚定、T1/T2 suspect），返回 record dict | 现役（唯一调用点 `:1555`） |
| 12 | `_persist_l3_provenance(key_dir, record, st)` | `conductor.py:1359`；本地 `import json` `:1367` | append-only + 按 `task_key` 去重 + `tmp`+`os.replace` 原子写；corrupt 不覆盖 | 现役（唯一调用点 `:1558`） |
| 13 | `_done_transaction` 内二次读判定源 | `conductor.py:1715`；`_md_section` 读取 `:1735-1736`；`_persist_l3_verdict` `:1760` | meets 后落 QG 报告 + 终态裁决 | 现役（`:1586` 调用） |
| 14 | `_persist_l3_verdict` | `conductor.py:619` | 把终态裁决 + 判定源字节写 `l3-verdict.txt` / `l3-report.md` | 现役 |

`_l3_provenance_record` 字段（逐字，`conductor.py:1294-1305`）：
```
"round", "task_key", "deciding_source", "source_mtime_ns", "anchor_path",
"anchor_mtime_ns", "suspect", "reasons", "raw_verdict", "verdict",
"fail_line", "recorded_at"
```
即：**唯一现成机读入口只有 `fail_line` + `deciding_source` + `round/task_key`**；`(file, test_id)` 与交接登记均无字段（与 RQ-3 §4 一致）。

#### Q2.2 新增解析器的挂载点

推荐挂载：**在 `_l3_round_verdict`（`conductor.py:1233`）内、`sources` 构造之后**（`:1254-1258`），对传入的 `sources: list[(path, text)]` 调用新 helper：

```
_l3_handoff_registrations(sources) -> list[dict]
```

然后把结果作为新可选参数传入 `_l3_provenance_record`（`:1267`，唯一调用点 `:1555`），写入 sidecar 新键（如 `"handoffs": [...]`）。

**为什么必须扫"全部 sources"而不是只扫 deciding source**：FM 语料把同一登记的字段拆在不同载体里——`(file, test_id)` 只在 `report.md:22` 的表行出现，`owner=cli-hitl-channel` 在 `output.md`（deciding source）与 `report.md` 都有，而 `handoff=registered` 只出现在 `report.md:22` 引用的修复行里，`output.md` 的 F-1 行只有中文"挂账交接"（见 §Q3）。`_l3_round_verdict` 已经在 `:1254-1258` 同时构造了两个来源的 `(path, text)`，是天然挂载点。

#### Q2.3 能否并入 provenance sidecar 而不新增文件 —— 可以，附 4 条约束

可以。理由与约束：

1. **同生命周期**：sidecar 文件 `<key>/l3-verdict-provenance.json`（`_PROVENANCE_FILENAME`，`conductor.py:1187`）按轮次 append（去重键 `task_key`，`:1385-1388`），登记是"某一轮的判定源内容"的派生数据，生命周期完全一致。
2. **幂等/原子/抗损坏全部继承**：`_persist_l3_provenance`（`:1359`）已提供 append-only + 去重 + `tmp`+`os.replace` + corrupt 不覆盖；新增键是纯 additive，无需新写路径。
3. **不可刷新（重要约束）**：去重键是 `task_key`（`:1385-1388`），同一轮已有记录即 `return False`（零写）。⇒ 一旦某轮登记被记录，**解析器升级/修 bug 后不能靠重跑 tick 刷新该轮登记**；账本（AC-001）若需回填，必须自建"重扫 sidecar + 重解析"的离线路径，或把登记解析结果同时写进账本行（账本是聚合层）。
4. **只在有裁决的轮次落盘**：`_l3_provenance_record` 仅在 `l3_source is not None` 且 `verdict != "no-verdict"` 时调用（`:1554-1558`）。⇒ worker 崩溃的 `no-verdict` 轮（`:1251-1260`）不会有登记——这类轮次本就无判定源，符合 fail-closed。

补充：
- 跨 key 聚合仍**必须**新增聚合产物（账本，AC-001）：sidecar 是 per-key、per-round，无法提供跨 key 视图。二者关系 = "sidecar 存原始登记（每 key 每轮）→ 账本聚合去重（跨 key）"。
- 现有测试只检查 `"suspect"` 是否泄漏出 sidecar（`test_autopilot_verdict_provenance_guard.py:437` `test_value_domain_closed_suspect_only_in_sidecar`），**没有 sidecar 字段闭集断言** ⇒ 新增键是安全的 additive 变更；但为稳妥 design 应显式声明"sidecar 允许新增键，消费者按需取键"。

#### Q2.4 读侧不能动的冻结区（设计硬约束）

仓内已有"冻结区域 sha"锁，新增 parser **不得改动**下列区域/文件，否则既有测试会红：

- `_parse_l3_output` 区域（`conductor.py:1091` 起）与 `_md_section` 区域（`:1076` 起）：`test_autopilot_verdict_source_fallback.py:66-67` 的 `_PARSE_L3_SHA` / `_MD_SECTION_SHA` 由 `test_frozen_region_sha_and_criteria_passed`（`:529`）复算比对。
- `test_autopilot_verdict_freshness.py` **整文件字节**：`_FRESHNESS_FILE_SHA`（`test_autopilot_verdict_source_fallback.py:68`）⇒ 新测试**不得写进该文件**。
- `test_autopilot_verdict_provenance_guard.py:637`（`test_frozen_anchors_and_criteria_unchanged`）同样复算 `_parse_l3_output` 区域 sha（`:642`）。
- 结论：新 parser 必须是**新增函数**（新区域），或在 `_l3_round_verdict` 内新增调用行（该区域未被 sha 锁）。`_l3_provenance_record` 增加"新可选参数 + 新键"会改动其函数区域——`test_autopilot_verdict_provenance_guard.py` 的 sha 锁实测只锁 `def _parse_l3_output(` 区域，不锁 `_l3_provenance_record`；但 design 阶段仍应以"新 helper + `_l3_round_verdict` 内调用 + sidecar 新键"为主路径，避免触碰任何已 sha 锁区域。

---
### Q3 — 真实语料形状盘点（逐字，语料驱动解析器设计的输入）

所有出处均在 `E:\CLI_workspace\FeatureMigrator\.agenticdoc\`。共识别 **10 种字形**（S-A..S-J），其中 S-A..S-G 是同一处红（或同族跨 key 红）在不同载体上的字形。

#### S-A：修复轮 `[VERIFY]` 机器行（键值对最全的形态）

出处：
- `cli-run-state-and-events/evidence/runs/repair-r1-out-20260925-r3.txt:220`
- 同载荷 `…-r2.txt:239`、`…repair-r1-out-20260925.txt:209`（r1）

逐字（r3:220）：
```
[VERIFY] REPAIR-R1-F1: cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True
```
r1 变体（`repair-r1-out-20260925.txt:209`，注意 `cli_groups=-1` 是采集脚本派生字段缺陷，L3 已如实披露）：
```
[VERIFY] REPAIR-R1-F1: cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged rc=1 cli_groups=-1 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True
```
r2 变体（`repair-r1-out-20260925-r2.txt:239`）：`cli_groups=13`，其余同 r3。

- 字段类型：**纯键值对**（空格分隔的 `k=v`）。
- 可抽出：`file`（`cross_key_test` 按 `::` 左半 = `tests/test_hitl_channel.py`）、`test_id`（右半 = `test_top_level_command_groups_unchanged`）、`owner_key`（`owner=cli-hitl-channel`）、`handoff=registered`、`rc=1`、`frozen_groups=12`、`not_fixed_by_this_key=True`。
- 冻结块：无显式名，仅有 `frozen_groups=12`（计数），**抽不出块名**（真实块名 `TOP_LEVEL_GROUPS` 在 S-D 才有）。
- **关键缺陷：此载体不被 conductor 读取**——`_l3_source_paths`（`conductor.py:1192`）只取 `workers/<task_key>/{output.md,report.md}`，不扫 `evidence/runs/**`。该行只在被 L3 报告"引用"时才进入判定源。

#### S-B：L3-a2 §B 表行（B 侧判定源，散文 + 内嵌键值对）

出处：`cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:22`

逐字：
```
| F-1 跨 key 红 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged` | **未闭合（按设计）**：当前树复跑仍红（rc=1，`cli_groups=13` vs 该用例冻结 12），owner=`cli-hitl-channel`，挂账交接、本 key 不修（写面纪律正确） | `repair-r1-out-20260925-r3.txt:220`（`REPAIR-R1-F1: rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True`）+ §F-1 原始 pytest 输出 |
```

- 字段类型：**自然语言表格行**，内嵌反引号键值对与 `path::test` token。
- 可抽出：`file`+`test_id`（反引号 `path::test` token）、`owner_key`（`owner=` 后的反引号 token）、`handoff=registered`（内嵌的引用串里仍有 `handoff=registered`）、`rc=1`、`frozen_groups=12`。
- 冻结块：无（仅计数）。
- 这是 **B 侧 report.md**（conductor 读得到的回退源）。

#### S-C：L3-a2 output.md 的 F-1 散文行（B 侧 **deciding source**）

出处：`cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/output.md`（QG 节内 F-1 行；同文件 Summary 行）

逐字（QG 节）：
```
- **F-1（跨 key 红）未闭合（按设计）**：r3 实测仍红（`cli_groups=13` vs 冻结 12，r3:220）；owner=`cli-hitl-channel`，挂账交接、本 key 写面外不修，纪律正确。
```
逐字（Summary/TL;DR 节）：
```
F-1 跨 key 红挂账 owner=`cli-hitl-channel`
```

- 字段类型：**自然语言**（`owner=` 近似 KV，但 `file/test_id` 缺失）。
- 可抽出：`owner_key`（`owner=` 后反引号 token）；`handoff`（中文"挂账交接"，启发式）；`file`/`test_id` **抽不出**（只有 `r3:220` 引用与 `cli_groups=13`，没有 `path::test`）。
- 关键含义：**只扫 deciding source 会丢 `(file, test_id)`** ⇒ 解析器必须同时扫 `report.md`（S-B）。

#### S-D：L3-a2 §F needs-rerun N-1 行（冻结块名唯一出现处）

出处：
- `cli-run-state-and-events/workers/ap-cli-run-state-and-events-l3-a2/report.md:83`
- key 级 `cli-run-state-and-events/l3-report.md:54`

逐字（report.md:83）：
```
| N-1 | 跨 key 红 `tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（第 1 轮 F-1 承接） | r3（10:49Z）实测仍红（`cli_groups=13` vs 冻结 12）；owner key 的修复是否已落地，本 key 记录无法证明 | `python -X utf8 -m pytest tests/test_hitl_channel.py -k top_level_command_groups -s -q`（期望 owner 修复后绿） | **`cli-hitl-channel`**（一行修复 = `TOP_LEVEL_GROUPS` 插入 `"runs"`）；conductor done 事务前确认收口或显式挂账 |
```
逐字（`l3-report.md:54`）：
```
- **N-1**（=F-1）跨 key 红：`pytest tests/test_hitl_channel.py -k top_level_command_groups`——owner `cli-hitl-channel`（一行修复：`TOP_LEVEL_GROUPS` 加 `"runs"`），conductor done 前确认收口或挂账。
```

- 字段类型：自然语言表格/项目行 + 内嵌反引号。
- 可抽出：`file`+`test_id`（`path::test`）、`owner_key`（末列反引号 key 或 "owner `key`"）、`frozen_block`（`TOP_LEVEL_GROUPS`）、`frozen_block_insert`（`"runs"`）。
- `handoff`：**无** `handoff=` token（靠"挂账/确认收口"启发式）。

#### S-E：cli-hitl-channel L3-a1 §遗留 K-1 行（A 侧，纯散文，字段最少）

出处：`cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md:68`

逐字（该行完整，含 K-1..K-4）：
```
- **K-1..K-4**（4 条已知红）：K-1 兄弟 key 新增顶层组 `runs` 致本 key PG-2 断言（12 组）红；K-2 本 key P1 的 `conftest.py` 子 env 改名（`env`→`child_env`）触发 `tests/gui_contract/paths_encoding.py` 静态匹配器 0 命中；K-3/K-4 本 key P4 的 `gate_service.write_acceptance`（design D-007.2/D-008/PG-3 明文要求）与两条既有只读源码守卫（token 扫描，连 docstring 提及 `write_text` 都判红）冲突。owner 与一行级修法均已登记（P7 §9.5 / P4 L-2/L-3/L-4；P4 明确拒绝以改名/别名绕过守卫——避免假绿，处置正确）。
```

- 字段类型：**纯自然语言**（把 K-1..K-4 四条压在一行）。
- 可抽出：`handoff`（"已登记"启发式）；`owner_key` **抽不出**（只有"owner 与一行级修法均已登记"，没有 key 名；"兄弟 key"是关系而非 key）；`file`/`test_id` **抽不出**（只有 `PG-2 断言（12 组）`、`runs`、`conftest.py`/`paths_encoding.py` 等其它文件）；`frozen_block` 抽不出（"PG-2 断言"是判据号，不是常量块名，且与 `TOP_LEVEL_GROUPS` 无显式映射）。
- 这是 A 侧 report.md（conductor 读得到的回退源）。

#### S-F：cli-hitl-channel L3-a1 摘要行（§遗留 摘要）

出处：`cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/report.md:96`

逐字：
```
- **已登记遗留**：4 条已知红 K-1..K-4（owner 在案，修复面均在本 key 白名单外）、A-1 上游 17 处格式违规（解析面 0 失效）、R-1/R-2/R-3 重冻结申请（契约 owner）、N6 一行既有形状（另立 AC）、`push` 归 Stage 3 key、口径登记类（N1/N7/N9/DEFAULT_TIMEOUT_SEC）。
```

- 字段类型：自然语言。
- 可抽出：`handoff`（"已登记遗留"启发式）；其余字段无。

---

#### S-G：cli-hitl-channel L3-a2 NR-B 行（A 侧，path::test 有、owner key 无）

出处：
- `cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a2/report.md:65`
- key 级 `cli-hitl-channel/l3-report.md:58`

逐字（report.md:65）：
```
| **NR-B** | `python -X utf8 -m pytest tests/test_hitl_channel.py::test_top_level_command_groups_unchanged`（+ 守卫网 G4 复跑） | K-1 仍红（`known_red_rc` 第 1 位 = 1，`repair-a1-evidence.txt:408` 完整失败输出在案）：第 13 个顶层组 `runs` 由兄弟 key 的未跟踪 `migrator/commands/cmd_runs.py` 引入，本 key PG-2 字面量（12 组）需 owner 更新 | 兄弟 key / PM 更新 PG-2 的 12 项字面量（或兄弟 key 撤 `runs` 组）后 |
```
逐字（`l3-report.md:58`）：
```
| **NR-B** | `pytest tests/test_hitl_channel.py::test_top_level_command_groups_unchanged` | K-1 仍红：第 13 顶层组 `runs` 来自兄弟 key 未跟踪 `cmd_runs.py`（`repair-a1-evidence.txt:408` 完整失败输出在案） | 兄弟 key/PM 更新 PG-2 字面量后 |
```

- 字段类型：自然语言表格行 + 内嵌 `path::test`。
- 可抽出：`file`+`test_id`（`path::test`）。
- `owner_key` **抽不出**（只有"兄弟 key / PM"——**角色不是 key 名**；这正是最易被启发式误抽的地方：设计必须禁止把"兄弟 key"/"PM"当成 owner_key）。
- `frozen_block` 抽不出（"PG-2 字面量（12 组）"）。
- `handoff`：无 token（"需 owner 更新"）。

#### S-H：gui-contract-mock-tests 的 `[FINDING]` / `[VERIFY] LEFTOVER-CROSSKEY`（另一处跨 key 登记，`Owner:` 形态）

出处：
- `gui-contract-mock-tests/evidence/runs/repair-r1-needs-rerun-20260924.txt:270`
- 同文件 `:729`（verdict 摘要）、`:730`（LEFTOVER-CROSSKEY 行）

逐字（:270）：
```
[FINDING] REPAIR-R1-03A: cross_key_missing_file_in_assertion=True -- the only 03A failure is the AC-014 behaviour-coverage assertion, which names AG-8 = tests/test_cli_json_snapshot.py (still untracked, sibling key cli-readonly-snapshot); the AC-016 drift case *skips by design* (contract source plane absent). Registered as a cross-key leftover (commit ordering), see the repair report.
```
逐字（:730）：
```
[VERIFY] REPAIR-R1-LEFTOVER-CROSSKEY: the frozen AC-014 behaviour table entry AG-8 = tests/test_cli_json_snapshot.py is still untracked (sibling key cli-readonly-snapshot) -> a clean checkout of THIS key's face alone is red on test_gcm_forbidden_rules_and_agreement_anchors_all_resolve. Owner: conductor (commit both keys' tests/** together) or the anchor declaration (re-point AG-8, which would be a declared-face change, not a repair). Not fixable by weakening the assertion.
```
其 L3 报告转述：`gui-contract-mock-tests/workers/ap-gui-contract-mock-tests-repair-a1/report.md:57`（"跨 key 冻结锚点（新遗留 L-1）"）。

- 字段类型：**英文键值对 + 英文散文**；注意 `Owner:`（大写 O + 冒号 + 空格）**不是** `owner=`。
- 可抽出：`file`（`tests/test_cli_json_snapshot.py`，但**无 test_id**）、`owner`（`Owner: conductor` —— 值是**角色**不是 key 名）、`handoff`（`Registered as a cross-key leftover`）。
- `owner_key` **抽不出**（`conductor` 不是 key 名；sibling key 名 `cli-readonly-snapshot` 在括号里但那是"红之来源"不是 owner）。
- 证明：`owner=` 这一约定**在野外观测到至少 3 种拼写**：`owner=`（S-A/S-B/S-C）、`Owner:`（S-H）、"owner 在案"（S-E/S-F）。解析器必须容错，且必须区分"role vs key"。

#### S-I：gui-skeleton-shell 的 `cross_key_conflicts=<n>`（计数型，无逐红登记）

出处：
- `gui-skeleton-shell/tasks/002-panel-services-and-validation.md:220`（交付证据串 `证据 problems=0 cross_key_conflicts=2`）
- `gui-skeleton-shell/workers/ap-gui-skeleton-shell-001-gui-deps-and-write-entries/output.md:14`（`**唯一天窗：\`cross_key_conflicts=1\`（已登记，未修）**`）

- 字段类型：**计数**（`cross_key_conflicts=<n>`）。
- 可抽出：冲突**数量**；`file`/`test_id`/`owner_key`/`frozen_block` 全部抽不出（无逐红条目）。
- 证明：野外还存在"只记数、不记 owner"的登记形态 ⇒ 若解析器只在计数上取数，会得到"有 N 处红但无 owner"的信息；这类必须**降级为仅升级**（AC-002 场景 C）。

#### S-J：A-06 / 重冻结申请（治理字段有、逐红 owner 无）

出处：
- `_autopilot/reflect/plan-writeface-gap.md`（A-06；逐字关键行：`:7` `first_seen     : 2026-09-24T19:33 前（6 个红在 P1–P5 窗口内引入）/ 确证于 2026-09-25T02:42Z`；`:22` `⇒ 没有任何 task 有权修这 6 个红，key 在原 plan 下**结构性不可收敛**（不是执行失败）。`；`:37` `1. **白名单没有覆盖"本阶段可能出现的全部失败面"**：P5 的判据把"全量套件"纳进来，写面却没有覆盖"套件红了要改哪里"。`；`:38` `2. **红没有 owner**：plan 依赖"下一阶段会修"这一默认假设，而没有把红**显式指派**给任何 task；`；`:57-:59` 三条教训）
- `gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md`（逐字关键行：`:8` `status    : ratified-by-human（2026-09-25T03:09:28+00:00 追认；见 §6）`；`:72` `**decision: approved by user-via-pm-window at 2026-09-25T03:09:28+00:00**`；`:86` `**decision-2: approved by user-via-pm-window at 2026-09-25T06:48:31+00:00（D-2：三处越表改动追认）**`；`:104` `**decision-3: accepted-as-known-leftover by user-via-pm-window at 2026-09-25T06:48:31+00:00（D-3 / W-1）**`）

- 字段类型：散文 + 治理级 KV（`old sha256 → new sha256` + `reason` + "是否放宽断言=否" + `decision:`）。
- 可抽出：治理字段（sha256/reason/decision）；逐红的 `file` 部分可见（`tests/test_gui_cli_entries.py` 等，`plan-writeface-gap.md:26-:33`），但 **`test_id` 无、`owner_key` 无、`frozen_block` 无**。
- 证明：同一族治理动作在野外出现了**两种文件形状**（`refreeze-request-*.md` / `cross-key-repair-request-*.md`）与两种登记形状；机制要把这些要素收敛成一套机器字段。

#### Q3 小结矩阵（语料驱动解析器的输入）

| 字形 | 出处（file:line） | 载体 | file | test_id | owner_key | handoff | 冻结块 |
|---|---|---|---|---|---|---|---|
| S-A 修复 `[VERIFY]` KV | `repair-r1-out-…-r3.txt:220`（/r2:239/r1:209） | evidence（**conductor 不读**） | ✅ | ✅ | ✅ `owner=` | ✅ `handoff=` | ❌（仅 `frozen_groups=12`） |
| S-B L3 报告 §B 表行 | `…l3-a2/report.md:22` | **判定源** report.md | ✅ | ✅ | ✅ `owner=` | ✅（内嵌引用串） | ❌ |
| S-C L3 output F-1 行 | `…l3-a2/output.md`（QG 节 / Summary） | **判定源** output.md（deciding） | ❌ | ❌ | ✅ `owner=` | ⚠️ 自然语言"挂账交接" | ❌ |
| S-D needs-rerun N-1 | `…l3-a2/report.md:83`；`…/l3-report.md:54` | 判定源 report.md | ✅ | ✅ | ✅（末列反引号） | ⚠️ | ✅ `TOP_LEVEL_GROUPS` |
| S-E K-1 散文 | `cli-hitl-channel/…l3-a1/report.md:68` | **判定源** report.md | ❌ | ❌ | ❌ | ⚠️ "已登记" | ❌（只有 `PG-2`） |
| S-F 摘要行 | `cli-hitl-channel/…l3-a1/report.md:96` | 判定源 report.md | ❌ | ❌ | ❌ | ⚠️ "已登记遗留" | ❌ |
| S-G NR-B 行 | `cli-hitl-channel/…l3-a2/report.md:65`；`…/l3-report.md:58` | 判定源 report.md | ✅ | ✅ | ❌（"兄弟 key / PM"） | ⚠️ | ❌ |
| S-H gui-contract `[FINDING]`/`LEFTOVER` | `gui-contract-mock-tests/evidence/runs/repair-r1-needs-rerun-20260924.txt:270/:730` | evidence（conductor 不读） | ✅ | ❌ | ❌（`Owner: conductor` 是角色） | ✅ 英文 `Registered as a cross-key leftover` | ❌ |
| S-I `cross_key_conflicts=<n>` | `gui-skeleton-shell/tasks/002-….md:220`；`…001-…/output.md:14` | 交付证据/输出 | ❌ | ❌ | ❌ | ❌ | ❌ |
| S-J A-06 / 重冻结 | `_autopilot/reflect/plan-writeface-gap.md:7/:22/:37/:38/:57-:59`；`gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md:8/:72/:86/:104` | reflect/evidence | 部分 | ❌ | ❌ | ❌ | ❌ |

补充：另一处"跨 key 登记"在 A 侧 deciding source（`cli-hitl-channel/workers/ap-cli-hitl-channel-l3-a1/output.md`）中仅有 `K-1..K-4` 概念词（无 `path::test`、无 key 名），再次证明"只扫 output.md 不够"。

---

### Q4 — 兼容解析的可行性判定

#### Q4.1 最小解析器规则（按优先级）

规则 1（**键值对优先**，覆盖 S-A/S-B/S-C 与 S-H 的 KV 部分）：
- 逐行扫描；对每个"跨 key 标记行"（含 `cross_key_test=`、`handoff=`、`cross_key_missing_file_in_assertion=`、`crosskey`、`cross_key_conflicts=` 之一的行）做空格分隔的 `k=v` 拆分。
- 字段映射：
  - `cross_key_test=<path>::<test>` → `file`、`test_id`（按第一个 `::` 拆分；无 `::` 则只有 `file`）。
  - `file=<path>` / `path=<path>` → `file`。
  - `test_id=<id>` / `test=<id>` → `test_id`。
  - `owner=<key>` / `owner_key=<key>` → `owner_key`（**仅当值匹配 key 名形态**；拒绝 `conductor`/`PM`/`兄弟 key` 等角色词）。
  - `handoff=<registered|...>` → `handoff`。
  - `frozen_block=<name>` / `frozen=<name>` / `frozen_groups=<n>` → `frozen_block`（或计数）。
  - `not_fixed_by_this_key=True` → `handoff` 的佐证（registered 的充分条件之一）。
- 注意同一行可能有多个 `=`（如 S-B 内嵌引用串）；解析器应按**字段名白名单**取值，而不是 `split("=")` 全量。

规则 2（**自然语言兜底**，覆盖 S-B/S-D/S-G 的 `path::test` 与 owner）：
- `path::test` token 正则：反引号内或裸的 `[\w./-]+\.py::[\w:]+` → `file`/`test_id`。
- `owner` 形态白名单：`` owner=`<key>` ``、`` owner `<key>` ``、`owner=<key>`、`` **`<key>`** ``（末列反引号，仅当该行同时含 `跨 key` 或 `path::test`）→ `owner_key`。
- `handoff` 关键词集：`registered`、`挂账`、`交接`、`已登记`、`owner 在案` → `handoff=registered`（**启发式，必须标注 confidence**）。
- **禁止**把 `兄弟 key`、`PM`、`conductor`、`兄弟 key/PM` 当 `owner_key`（S-G/S-H 实测污染源）。

规则 3（**合并与去重**）：
- 同一 key 的同一红（`(file, test_id)`）在 `output.md` 与 `report.md` 可能各出现一次；解析器对 `sources` 全部文本解析后按 `(file, test_id)` 合并，取并集字段（S-B 补 `file/test_id`，S-C 补 `owner_key`）。
- 去重键 = `(file, test_id, frozen_block_fingerprint)`（对齐 spec Q8 的账本去重键）。

规则 4（**降级**，spec AC-011 / §2.3）：
- 若候选登记缺 `(file, test_id)` 或 `owner_key` 不可解析到具体 key → **不生成工单/提案**；只生成升级记录（AC-002 场景 C），并在记录中写明 `unresolvable_fields`。
- 若某轮判定源中**完全没有**跨 key 标记 → 无登记，不产生任何登记行（fail-closed 默认）。
- 若只有计数（S-I）→ 升级记录，不提案。

#### Q4.2 散文字形下"无法可靠取得"的字段

| 字段 | 散文字形下的可得性 | 具体不可得的语料 | 降级 |
|---|---|---|---|
| `file` | 多数可得（`path::test` / `*.py` token）；S-E/S-I/S-J 不可得 | S-E 只说 `PG-2 断言`；S-I 只有计数；S-J 无 test_id | 缺则 unresolvable → 仅升级 |
| `test_id` | 只有显式 `path::test` 时可得；S-C/S-E/S-F/S-H/S-I/S-J 不可得 | S-C deciding source 只有 `r3:220`；S-E 无 test id | 缺则 unresolvable → 仅升级 |
| `owner_key` | 只有 `owner=<key>` 或明确反引号 key 时可得；S-E/S-G/S-H/S-I/S-J 不可得 | S-G 是"兄弟 key / PM"（角色）；S-H 是 `Owner: conductor`（角色）；S-E 是"owner 在案" | 缺则 unresolvable → 仅升级（**绝不猜 key**） |
| `handoff` | 只有 `handoff=registered` 是可靠 KV；其余全是启发式中文/英文关键词 | S-B/S-C/S-D/S-E/S-F/S-G 均无 `handoff=` | 启发式命中则标 confidence，未命中则视为"未登记"→ 仅升级 |
| `冻结块`（名或指纹） | 只有 S-D 显式给出 `TOP_LEVEL_GROUPS`；S-A/S-B 只有计数 `frozen_groups=12`；其余无 | S-A/S-B/S-C/S-E/S-F/S-G/S-H | 缺则提案不可含精确边界 → 降级为"仅提案不可执行"（对齐 spec R-2） |

**结论**：兼容解析可以覆盖 `file/test_id/owner_key/handoff` 的"KV 优先"部分；但**K-1 式散文（S-E/S-F）与 `cross_key_conflicts` 计数（S-I）无法可靠抽出 `test_id`/`owner_key`**——这类必须按 spec §2.3/AC-002「无登记只升级」处理，机制不得为了凑字段而猜 owner（否则会重演"红有 owner 但 owner 是错的"这种比无 owner 更坏的假绿）。

---

### Q5 — 双侧测试锁（P-005）

#### Q5.1 写侧（L3 输出形状）现有可测点

| 可测点 | 测试文件:用例 | file:line | 断言内容 |
|---|---|---|---|
| L3 prompt 文档化回退契约 | `test_autopilot_verdict_source_fallback.py::test_reviewer_prompt_documents_fallback` | 用例 `:919` | prompt 含 `## Quality Gate Report`/`## Achieved`、`output.md` 首选、`report.md` 回退、`FAIL`→`below`；并检查 `task.md` 也含 `report.md` |
| L3 prompt 文档化 provenance 契约 | `test_autopilot_verdict_provenance_guard.py::test_reviewer_prompt_documents_provenance` | 用例 `:556`（`:563` 取 `conductor._l3_prompt("k1", 1)`） | prompt 含 suspect/事后补写语义 |
| reprompt prompt 字节精确 = `_l3_prompt` + 固定指示 + 失败行 | `test_autopilot_conductor_exec.py::test_dcr_reprompt_prompt_byte_exact` | 用例 `:939`（`:952/:959` 断言 `body.startswith(conductor._l3_prompt("k1", 2))`） | 写侧 prompt 片段字节锁 |

#### Q5.2 读侧（conductor 解析）现有可测点

| 可测点 | 测试文件:用例 | file:line | 覆盖的 conductor 符号 |
|---|---|---|---|
| FAIL 三形态 + 豁免（正/负/构造/正则单元） | `test_autopilot_fail_marker_forms.py`：`TestPositiveAnchors:77`、`TestWholeFileSurface:106`、`TestConstructedVariants:136`、`TestNegativeAnchors:155`、`TestInlineNegation:240`、`TestRegexUnits:252`（用例如 `test_naive_pipe_cell:80`、`test_first_failing_line_wins_over_later_qg_table:122`） | `:77-:285` | `_l3_fail_marker_line` + `_L3_FAIL_*` 常量 |
| 回退优先级 / fail-closed / 只读约束 | `test_autopilot_verdict_source_fallback.py`：`test_report_fallback_meets_and_pointer:229`、`test_output_priority_when_both_qualify:262`、`test_report_fail_not_whitewashed_by_output_pass:297`、`test_both_unqualified_is_below_without_fabricated_artifacts:390`、`test_slug_report_is_not_a_fallback_source:835`、`test_worker_status_priority_and_availability_gate:784`、`test_zero_write_with_report_source:868` | — | `_l3_qualifies`、`_l3_resolve_source`、`_l3_round_verdict`、`_L3_SOURCE_ORDER` |
| 冻结原语 region sha + criteria | 同文件 `test_frozen_region_sha_and_criteria_passed:529`（sha 常量 `_PARSE_L3_SHA:66`、`_MD_SECTION_SHA:67`、`_FRESHNESS_FILE_SHA:68`） | — | `_parse_l3_output`、`_md_section` 区域 sha 锁 |
| provenance sidecar 字段/值域/幂等 | `test_autopilot_verdict_provenance_guard.py`：`test_normal_round_not_suspect:236`、`test_time_overrun_marks_suspect_and_fails_closed:265`、`test_copy_signature_marks_suspect:300`、`test_value_domain_closed_suspect_only_in_sidecar:437`、`test_idempotent_zero_write_and_io_bound:722`、`test_frozen_anchors_and_criteria_unchanged:637`、`test_only_tighten_no_below_to_meets:670` | — | `_l3_provenance_record`、`_persist_l3_provenance`、`_PROVENANCE_FILENAME` |
| L3 判定新鲜度 / 两节缺失 → below | `test_autopilot_verdict_freshness.py::test_l3_criteria_behavior_unchanged:605`（`:613/:618/:625` 构造缺节用例）；`test_transient_meets_degrades_to_below:450` | — | `_parse_l3_output`、`_persist_l3_verdict` |
| conductor 端 L3 链（缺节 / FAIL 行穿线） | `test_autopilot_conductor_exec.py`：`test_missing_sections_and_short_achieved_are_below:537`、`test_fmr_bullet_fail_only_source_below:1384`、`test_fmr_nonqualifying_output_fail_vetoes_clean_report:1416`、`test_fmr_fail_line_threading:1446`、`test_fmr_meets_preserved_with_zero_fail_texts:1507`、`test_fmr_inline_negation_still_fires:1541` | — | `_md_section`、`_l3_fail_marker_line`、`_l3_round_verdict` |
| e2e provenance fail_line 落盘 | `test_autopilot_e2e.py`（`:679-684` 断言 `by_round["l3-a1"]["fail_line"]` 含逐字 bullet 行） | — | `_l3_provenance_record` end-to-end |

#### Q5.3 新增测试应落在哪

- **命名族**：`packages/multi-workers/test_autopilot_*.py`（flat，与现有 L3 测试同目录）。
- **推荐新文件**：`packages/multi-workers/test_autopilot_xkey_registration.py`（**新文件**，不改任何现有测试文件）。理由：(a) `test_autopilot_verdict_source_fallback.py` 的 `_FRESHNESS_FILE_SHA`(:68) 把 freshness 文件整文件字节锁死，任何修改现有文件都可能撞上"新文件 only"惯例（provenance guard 的 docstring 明写 "New file only (D-013 / AC-017): no existing test file is modified"，`test_autopilot_verdict_provenance_guard.py:6`）；(b) `_parse_l3_output`/`_md_section` 区域 sha 锁禁止改动其所在区域。
- **用例分层（写侧 + 读侧双侧锁，P-005）**：
  - 写侧：调用 `conductor._l3_prompt("k1", 1)`，断言机器行模板存在且形状可被读侧规则解析（含字段名白名单）；再断言该模板**不含**能触发 `_l3_fail_marker_line` 的 token（防止把登记行误判成 FAIL）。
  - 读侧（语料驱动，直接引用 §Q3 逐字字形）：S-A KV 行、S-B 表行、S-C output 行、S-D N-1 行、S-E K-1 散步行、S-G NR-B 行、S-I 计数行；断言抽取结果与人工判读逐字段一致（含"K-1 散步行 `owner_key`/`test_id` 必须为 None"这一负例）。
  - 降级：断言缺 `(file,test_id)` 或 owner 不可解析时不产提案（AC-002），只产升级记录。
  - 自审：照现有 `test_autopilot_verdict_source_fallback.py::test_ac013_self_coverage_audit:953` 的 AC→test 覆盖自审模式（`# AC-0NN -> test_name` + 覆盖集合 + 无真实树依赖）。
- **不要**：把新用例塞进 `test_autopilot_verdict_freshness.py`（整文件 sha 锁）、不要改 `_parse_l3_output`/`_md_section` 区域（sha 锁）、不要依赖 FM 真实树路径（现有测试均用 `tmp_path`，`test_ac013_self_coverage_audit` 还显式断言 `real_tree_deps == 0`，`:953` 起）。

---

## 结论 → 决策映射

| # | 结论（对应上文） | 对 design D-001（承载方式）的决策输入 |
|---|---|---|
| 1 | L3 prompt 的唯一构造点是 `conductor.py:1113-1127`（纯字符串函数），只规定两节；写侧最小改动 = 在 `:1119-1121` 追加**一行机器行要求**（方案 A），不改节数、不改 `_l3_qualifies`（`:1207`）判定契约 | **D-001 写侧载体**：机器行内嵌 `## Quality Gate Report`，形状 `[XKEY] file=… test_id=… owner_key=… handoff=… frozen_block=…`；不新增必含节 |
| 2 | 框架内唯一"写+读双侧齐备"的机器块先例是 `[CHECKPOINT]`（写 `output-writer.ts:191`，读 `heartbeat.ts:84-85`+`:101`）；`[VERIFY]`（`:1001/:1116/:1140`）只有写侧提示、**无读侧** | **D-001 读侧范式**：照抄 `[CHECKPOINT]` 的"formatter + 行锚定正则 + 类型化字段"；不要照抄 `[VERIFY]` 的"仅提示词" |
| 3 | L3 判定源解析现役入口链：`_md_section:1076` → `_l3_qualifies:1207` / `_l3_resolve_source:1215` / `_l3_round_verdict:1233`（`sources` 构造 `:1254-1258`）→ `_l3_provenance_record:1267`（字段 `:1294-1305`）→ `_persist_l3_provenance:1359`；`_parse_l3_output:1091` 仅测试调用 | **D-001 读侧挂载点**：新 helper `_l3_handoff_registrations(sources)` 在 `_l3_round_verdict`（`:1254-1261` 之间）调用，结果作为新可选参数进 `_l3_provenance_record` |
| 4 | 结构化登记可并入 provenance sidecar（`<key>/l3-verdict-provenance.json`，`_PROVENANCE_FILENAME:1187`）**而不新增文件**：生命周期一致、原子写/去重/抗损坏继承；但有 3 条约束——(a) 去重键 `task_key` 意味着**不可刷新**（`:1385-1388`），(b) 只在有裁决的轮次落盘（`:1554-1558`），(c) 跨 key 聚合仍**必须**新增账本（AC-001） | **D-001 落盘载体**：登记写入 sidecar 新键；账本（新文件）作为聚合层，从各 key sidecar 增量读取 |
| 5 | FM 语料有 10 种字形（S-A..S-J）；**同一登记的字段被拆在不同载体**：`(file,test_id)` 只在 `report.md`（`:22`/`:83`），`owner=` 在 `output.md`/`report.md`，`handoff=registered` 只在被引用串里 | **D-001 解析范围**：必须扫**全部** `sources`（`output.md` + `report.md`）并按 `(file,test_id)` 合并，不能只扫 deciding source |
| 6 | `owner` 在野外至少 3 种拼写（`owner=` / `Owner:` / "owner 在案"），且 `Owner: conductor`、"兄弟 key / PM" 是**角色不是 key**；`Owner:` 出现在 S-H（`repair-r1-needs-rerun-20260924.txt:730`） | **D-001 解析规则**：owner 必须做"key 名形态"校验；role 词白名单拒绝（`conductor\|PM\|兄弟 key`）；否则 `owner_key=None` |
| 7 | K-1 式散文（`cli-hitl-channel/…l3-a1/report.md:68`）只有 `PG-2 断言`，无 `path::test`、无 key 名；`cross_key_conflicts=<n>`（`gui-skeleton-shell/…:220`）只有计数 | **D-001 降级**：缺 `(file,test_id)` 或 `owner_key` → 不产提案，只产升级记录（AC-002/§2.3）；绝不猜 owner |
| 8 | 冻结区 sha 锁：`_parse_l3_output`/`_md_section` 区域（`test_autopilot_verdict_source_fallback.py:66-67` + `:529`）、`test_autopilot_verdict_freshness.py` 整文件（`:68`）不可动 | **D-001 实现约束**：新 parser 必须是新函数/新文件；新测试落 `test_autopilot_xkey_registration.py` |
| 9 | 双侧测试锁现成范式：写侧 `test_reviewer_prompt_documents_fallback`（`:919`）/`test_dcr_reprompt_prompt_byte_exact`（`:939`）；读侧 `test_autopilot_fail_marker_forms.py`（`:77-:285`）+ `test_frozen_region_sha_and_criteria_passed`（`:529`）+ provenance guard（`:437/:722/:637`）；自审 `test_ac013_self_coverage_audit`（`:953`） | **D-001 测试锁（P-005）**：写侧锁 prompt 模板形状；读侧锁 §Q3 逐一字形抽取结果（含 K-1 负例）；降级路径锁 AC-002 |

### 设计阶段需拍板的两个点（本文不替 design 决定）

1. **机器行的精确语法**：`[XKEY] file=… test_id=… owner_key=… handoff=… frozen_block=…` vs 复用 `[VERIFY]` 前缀（如 `[VERIFY] XKEY: …`）。前者与现有 `[VERIFY]` 语义分离、更便于唯一前缀识别；后者可复用现有"验证行"心智。二者都不触发 FAIL 正则，均可行——建议 `[XKEY]` 独立前缀（S-A 已证明 `[VERIFY]` 前缀下多种 `REPAIR-R1-*` 行混杂）。
2. **sidecar 新键的字段名与形状**：`"handoffs": [ {file, test_id, owner_key, handoff, frozen_block, confidence} ]` 逐轮并列，还是每轮只存一个聚合对象。建议逐轮数组（一次 L3 轮可有多个跨 key 登记），与 `reasons` 的既有"逐轮数组"形状同族（`conductor.py:1301`）。