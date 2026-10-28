# 调研证据 — 依赖数据源（RQ-C2 / T-C2）

- **key**：mw-dynamic-concurrency
- **任务卡**：`.agenticdoc/mw-dynamic-concurrency/tasks/T-C2-dependency-sources.md`（card_sha256 `05351d7a0a4ae83933261f2e99573066ac65b290978236111a2f393f82665f65`）
- **唯一写面**：本文件。全程只读（read/find/grep/ls/bash + 一次 `roadmap_check.py` / 一次 `python -c` 只读复算；未跑测试、未跑 conductor、未改任何生产文件、未跑 npm）
- **日期**：2026-10-14

## 结论先行

1. **key 级依赖今天完全机器可读**。载体 = `.agenticdoc/_autopilot/_roadmap.md` 每个 stage 的 `### Keys` 表第 3 列 `depends_on`；语法 = `-`/空（无依赖）或逗号分隔 key 名；解析 = `roadmap.py:483 _parse_depends_on`，行装配 `roadmap.py:433`；满足判定 = `conductor.py:3560-3561 _deps_satisfied` + `conductor.py:64 _DEP_SATISFIED = {done, closed-legacy}`。
2. **key 级前沿今天就可算**，不需要新数据：`conductor.py:740` 的 `_deps_satisfied(entry.depends_on, status_of)` 就是前沿谓词，`conductor.py:744` 只是把它按 `max_parallel_keys`（默认 2）截断。TS 侧只读视图也已经算了同一件事（`monitor.ts:915 blockedBy`）。
3. **任务级依赖今天没有机器可读载体**。三种候选载体全部只是散文：(a) `plan.md` 里 `depends_on` 命中数 = 0，代码只读"出现顺序"（`conductor.py:1717 _plan_task_order`）；(b) `tasks/*.md` 卡头有 35 处 `- 依赖:`、26 处 `- 波次: … · 依赖: …`（其中只有 19 条是纯 id 列表）、以及仅 `mw-dual-workspace` 12 个文件的旧式 `- deps: [001]`——**没有任何解析器读它们**；(c) 派发 `task.md` 头是固定字段闭集，没有依赖字段，`card_audit.py` 实际只消费 `card_path:` / `card_sha256:`。
4. **缺的只有"任务级边"一件事**。任务完成态与在飞态今天已经存在（`_workers.parallel` 行 + `conductor.py:1698 _family_rows` / `conductor.py:3539 _is_in_flight`）。最小新增载体 = 卡头一行 `deps:`，解析落 `card_audit.py:129 _header_value` 家族，消费落 `conductor.py:1717 _plan_task_order` 与 `conductor.py:1771`（per-key 串行点）。
5. **环与悬空校验已实现，但只挂在 CLI 与 doctor，conductor 不执行**：`roadmap.py:557-575` 查悬空 / 自依赖 / 前向 / 环，生产调用者是 `roadmap_check.py:50` 与 `mw_common.py:2924`；`mw_common.py:3694-3696` 原文明确写 `"validate_roadmap ran but the conductor does not enforce it yet"`。后果：悬空引用或环对 dispatcher 只表现为"依赖永不满足"，`conductor.py:740` 只 `continue`，**无 timeline 告警、无 gate**——静默死锁。

---

## §1 key 级依赖

### 1.1 语法与 schema

`packages/multi-workers/autopilot/roadmap.py:12-16`（模块 docstring，schema 原文）：

```
    ## Stage 1: <title>
    ...
    ### Keys
    | key | role | depends_on |
    |-----|------|-----------|
    | k1 | <role> | - |
```

`roadmap.py:36-39`（依赖合法性定义原文）：

```
- Stage order = order of appearance in the file. Dependency legality
  (validate_roadmap) is defined against that order: a dependency must point
  to a key in the same stage or an earlier stage.
```

### 1.2 解析函数 `file:line`

| 环节 | 位置 | 原文片段 |
|---|---|---|
| 表头识别 | `roadmap.py:479-480` | `return [c.lower() for c in cells] == ["key", "role", "depends_on"]` |
| 单元格解析 | `roadmap.py:483-496` | `def _parse_depends_on(cell: str) -> tuple[str, ...]:` … `if not cell or cell == "-": return ()` … `for part in cell.split(","):` |
| 行装配 | `roadmap.py:433` | `self.keys.append(RoadmapKey(key=key, role=role, depends_on=_parse_depends_on(dep_cell)))` |
| 数据类 | `roadmap.py:128` | `depends_on: tuple[str, ...]` |
| 全图视图 | `roadmap.py:647-654` | `def dependency_graph(roadmap: Roadmap) -> dict[str, set[str]]:` … `graph.setdefault(k.key, set()).update(k.depends_on)` |

语法边界（实测）：`-` → 空元组；空 cell → 空元组；逗号分隔且容忍尾逗号/空格（`roadmap.py:492-495` 逐段 strip，空段与 `-` 段被过滤）。**未见任何解析器把依赖写成 `|` 分隔或 brace 列表**（`rg -u -n "depends_on" --glob "!**/dist/**" packages/multi-workers` 的命中全部落在 roadmap 相关点与两处 `_deps_satisfied` 调用）。

### 1.3 验证规则（`validate_roadmap`，`roadmap.py:528`）

四条依赖相关判据原文（`roadmap.py:557-575`）：

```python
            for dep in k.depends_on:
                if dep not in key_stage:
                    problems.append(
                        f"stage {stage.number} key {k.key!r}: dependency {dep!r} not found"
                    )
                elif key_stage[dep] > idx:
                    later = roadmap.stages[key_stage[dep]].number
                    problems.append(
                        f"stage {stage.number} key {k.key!r}: dependency {dep!r} "
                        f"points to later stage {later}"
                    )
                elif dep == k.key:
                    problems.append(
                        f"stage {stage.number} key {k.key!r}: depends on itself"
                    )

    cycle = _find_cycle(roadmap)
    if cycle:
        problems.append("dependency cycle: " + " -> ".join(cycle))
```

- **同 stage / 更早 stage**：合法（`key_stage[dep] > idx` 才报错）。
- 另有重复 key 检查 `roadmap.py:548-553`、空 Keys 表 `roadmap.py:541`、goal 空 `roadmap.py:576-578`、key-status 集合双向一致 `roadmap.py:581-593`。

### 1.4 依赖满足判定（conductor）

`packages/multi-workers/autopilot/conductor.py:60-64`（终态集合原文）：

```python
# Dependency-satisfaction set (design D-005 red line). `pending-review` is
# deliberately absent: a deferred review is NOT a verdict, so it must never
# unlock its dependents (`_deps_satisfied` -> dependent dispatch, and
# `_xkey_aggregate`'s owner-terminal check). Adding it here is the red line
# VC-D2-01/02/12 lock.
_DEP_SATISFIED = frozenset({"done", "closed-legacy"})
```

`conductor.py:3560-3561`：

```python
def _deps_satisfied(deps: tuple[str, ...], status_of: dict[str, str]) -> bool:
    return all(status_of.get(dep) in _DEP_SATISFIED for dep in deps)
```

数据来源：`status_of` 来自 roadmap 的 `> key-status:` 行（`conductor.py:650-658`）：

```python
    # Cross-stage views: key -> deps, key -> status, key -> stage number.
    deps_of: dict[str, tuple[str, ...]] = {}
    status_of: dict[str, str] = {}
    stage_of: dict[str, int] = {}
    for stage in rm.stages:
        for entry in stage.keys:
            deps_of[entry.key] = entry.depends_on
            stage_of[entry.key] = stage.number
        for k, s in stage.key_status.items():
            status_of[k] = s
```

消费点（key 层闸门本体，`conductor.py:736-746`）：

```python
            if not _deps_satisfied(entry.depends_on, status_of):
                continue
            if key in in_flight_keys:
                continue  # wait for the in-flight worker
            if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):
                continue  # parallel cap — key starts on a later tick
```

（种子给的行号 `conductor.py:744` 命中"cap"那一行；依赖谓词在 `:740`。两条一起才是完整闸门。）
`_DISPATCH_SKIP_STATUSES`（`conductor.py:71`）= `("done", "stalled", "closed-legacy", "pending-review")`；`in_flight_keys` 由 `_workers.parallel` 行算出（`conductor.py:698-702`）。
fail-closed 副作用：`status_of` 缺该 dep（悬空）或 key-status 行缺失时 `status_of.get(dep)` 为 `None` → `_deps_satisfied` False → 该 key 永不被派发。

### 1.5 两个真实 `_roadmap.md` 实例片段（其它项目，只读）

本仓库 `.agenticdoc/_autopilot/_roadmap.md` **不存在**（实测见 §6「未找到」）。下面两个是 `H:` 盘按文件名扫到的真实实例。

**实例 A**：`H:/git/JCodingAss/.agenticdoc/_autopilot/_roadmap.md`（Stage 1，2 stage / 5 key，`roadmap_check.py` exit 0）

```
### Keys
| key | role | depends_on |
|-----|------|-----------|
| llm-router | LLM 多 provider 失败自动切换（A→B→C→D）… | - |
| crash-analysis | Crash Parser 项目问题分析真实现… | llm-router |
| plugin-ui | 插件 UI：工具窗滚动容器 + IM 式问答气泡 + 引用跳转… | - |
| rag-context | RAG 问答细化①+③… | plugin-ui |
```
（`crash-analysis` 依赖同 stage 的 `llm-router`；`rag-context` 依赖同 stage 的 `plugin-ui`——同 stage 依赖合法，见 §1.3。）

Stage 2 单 key 跨 stage 依赖：

```
| e2e-validation | E2E 集中验证… | llm-router,crash-analysis,plugin-ui,rag-context |
```

**实例 B**：`H:/git/E2Feature/.agenticdoc/_autopilot/_roadmap.md`（Stage 4，5 stage / 42 key，`roadmap_check.py` exit 0）

```
| key | role | depends_on |
|-----|------|-----------|
| feature-build-baseline | **本机构建基座与基线（不是缺机器）**：… | - |
| feature-dual-switch-compile | **成功判据 (b)：`FEATURE_X=0/1` 双开关编译对拍…** | feature-build-baseline |
| feature-upgrade-cost-actual | **成功判据 (c)：真实升级成本回归**… | feature-build-baseline |
```

Stage 5 有一个长依赖行（同 stage 多依赖，演示逗号语法）：

```
| feature-switch-readiness-closeout | **切换就绪对账 + 本 stage 唯一 doc 写者**… | feature-cigate-install-kit, feature-inline-marker-patchkit, feature-sampling-human-channel, feature-gui-time-mvp-board, feature-l3-verdict-freshness, feature-l3-verdict-source-fallback, feature-verdict-provenance-guard, feature-false-meets-remediation, feature-gui-contract-respec, feature-gui-contract-respec-apply |
```

其余 key 级依赖消费者（只读展示面，不构成新载体）：
- TS 解析镜像：`status-model.ts:444` `dependsOn: string[];`、`status-model.ts:485 parseDependsOn`、`status-model.ts:591` 推入 `keys`。
- 只读前沿视图：`monitor.ts:915` `blockedBy: (depsByKey.get(key) ?? []).filter((dep) => !["done", "closed-legacy"].includes(statusByKey.get(dep) ?? ""))`。
- 门下游推导：`mw.py:3730 _gate_downstream_keys`、`console.ts:329 downstreamKeys`。

---

## §2 任务级依赖现状（三态逐一 grep）

### 2.1 `plan.md` —— 只有顺序，没有依赖

- 机器读取点只有两处，都在 `conductor.py`：

| 位置 | 原文 |
|---|---|
| `conductor.py:1707-1715` | `def _plan_text(key_dir: pathlib.Path) -> str:` … `plan = key_dir / "plan.md"` |
| `conductor.py:1717-1724` | `def _plan_task_order(stems: list[str], plan: str) -> list[str]:` / `"""Execution order: plan appearance order when parseable, else stem lexicographic; plan-unmentioned (orphan) tasks go last (D-111)."""` / `mentioned = [(plan.find(s), s) for s in stems if s in plan]` |
| `conductor.py:1764-1765` | `plan = _plan_text(key_dir)` / `for stem in _plan_task_order([f.stem for f in files], plan):` |
| `conductor.py:2848-2866` | `def _missing_plan_tasks(...)`：`referenced = sorted(set(re.findall(r"\bT-\d{2,3}-[A-Za-z0-9][A-Za-z0-9-]*", plan)))`（只用于"plan 提到的 id 是否缺 tasks/ 文件"，不是依赖） |

- **`plan.md` 里没有任何 `depends_on` 字段**。实测：

```
PS> rg -n "depends_on" --glob "**/plan.md" .agenticdoc | Measure-Object | Select-Object -ExpandProperty Count
0
```

- 依赖信息存在于 `plan.md` 的**散文与 markdown 表格**里，且格式因 key 而异，例如：
  - `mw-worktree-junction-guard/plan.md:6`：`## 0. 批次与依赖（落地顺序）`，`:10` `| 批次 | 任务 | 语言/写面 | 依赖 | 覆盖 AC |`，`:14` `| **B2** | W-05 G1 guard ‖ W-07 AC-013 脚本 ‖ W-03 doctor 段 | … | W-05 依赖 W-01；W-03 依赖 W-02 的注册表模块（接口已在卡内冻结，不并行以避免双实现）；W-07 只依赖摘链原语语义 | … |`
  - `mw-rag-window-parity/plan.md:22`：`约束：T-2 与 T-3 都改 pm/ui-bridge.ts ⇒ **串行**（T-3 在 T-2 之后）；T-2 可与 T-1 并行（文件不相交）。`
  - `mw-dispatch-settle-gates/plan.md:26-29`：`| 波次 | … | 并行理由（无文件交叠） |` 表。
  这些表没有被任何代码读取（`rg -n "plan\.md" packages/multi-workers/autopilot/conductor.py` 只有 §2.1 表中 4 行）。

### 2.2 `tasks/*.md`（任务卡）—— 有依赖文字，无解析器

本工作区 `tasks/` 下的卡 = 428 个 `.md`。

| grep | 命中 | 原文示例 |
|---|---|---|
| `rg -u -n "^\s*-\s*依赖\s*[:：]" --glob "**/tasks/*.md" .agenticdoc` | **35 行** | `mw-dispatch-role-escape/tasks/T-03-docs-dist-smoke.md:3`：`- 依赖: T-01、T-02` |
| 其中"纯 id 列表或 `无`"（无解释文字） | **5 行** | `mw-crosskey-risk-escalation/tasks/T-1-CROSSKEY-ESCALATION.md:5`：`- 依赖: 无` |
| 其余 30 行为散文 | 30 行 | `mw-rag-window-parity/tasks/T-3-DOCTOR-RAG-ROW.md:5`：`- 依赖: **T-2 必须先完成**（同一文件 `pm/ui-bridge.ts`，且 `shared/mw-runner.ts` 也会被两者触碰）` |
| `rg -u -n "^\s*-\s*波次\s*[:：].*依赖\s*[:：]"` | **26 行** | `mw-autopilot-slot-capacity/tasks/T-05-consumption-carrier.md:3`：`- 波次: **1** · 依赖: T-01, T-03` |
| 其中纯 id 列表或 `无` | **19 行** | 同上 |
| 其余 7 行含解释 | 7 行 | `mw-autopilot-slot-capacity/tasks/T-21-defer-ledger.md:3`：`- 波次: **3** · 依赖: T-07（台账）、T-19（case 2 生产者）` |
| `- deps: [...]`（旧式，仅一个 key） | **12 个文件，全在 `mw-dual-workspace/tasks/`** | `mw-dual-workspace/tasks/006-dispatch-injection.md:9`：`- deps: [002, 004]`；`011-regression-baseline.md:9`：`- deps: [001, 002, 003, 004, 005, 006, 007, 008, 009, 010]` |

**没有任何代码解析这些字段**。实测：

```
PS> rg -n "deps" packages/multi-workers/autopilot/card_audit.py packages/multi-workers/autopilot/dispatch.py packages/multi-workers/autopilot/conductor.py
packages/multi-workers/autopilot/conductor.py:61:# unlock its dependents (`_deps_satisfied` -> dependent dispatch, and
packages/multi-workers/autopilot/conductor.py:650:    # Cross-stage views: key -> deps, key -> status, key -> stage number.
packages/multi-workers/autopilot/conductor.py:651:    deps_of: dict[str, tuple[str, ...]] = {}
packages/multi-workers/autopilot/conductor.py:656:            deps_of[entry.key] = entry.depends_on
packages/multi-workers/autopilot/conductor.py:700:        for key in deps_of
packages/multi-workers/autopilot/conductor.py:740:            if not _deps_satisfied(entry.depends_on, status_of):
packages/multi-workers/autopilot/conductor.py:3560:def _deps_satisfied(deps: tuple[str, ...], status_of: dict[str, str]) -> bool:
packages/multi-workers/autopilot/conductor.py:3561:    return all(status_of.get(dep) in _DEP_SATISFIED for dep in deps)
```

（`card_audit.py` 零命中；全部 8 处都是 key 级 `deps_of`。）

`- deps:` 甚至**不会传播到派发面**：卡片解析 `dispatch.py:480-524 _extract_card_parts` 只认 `^#{2,6}` 标题（`dispatch.py:385 _CARD_HEADING_RE = re.compile(r"^#{2,6}\s+(.*)$")`），卡头顶部 `- deps: [...]` 在第一个 H2 之前，既不是标题也不在"首个标题之后的 fallback 文本"里（fallback 从 `headings[0][0] + 1` 开始，`dispatch.py:521-523`），因此被整体丢弃。实测：

```
PS> rg -u -n "^\s*-?\s*deps\s*:" --glob "**/workers/*/task.md" .agenticdoc | Measure-Object | Select-Object -ExpandProperty Count
0
```

（`rg -u -n "deps" --glob "**/workers/*/task.md" .agenticdoc` 的非零命中全是散文里出现 `deps` 字样，例如 `mw-worktree-junction-guard/workers/wjg-w02-worktree-cli/task.md` 里的 CLI 参数 `--link-deps`。）

### 2.3 派发 `task.md` 头 —— 固定字段闭集，无依赖字段

生产者 1（conductor）：`dispatch.py:826-866` 渲染的 header 字段闭集：

| 行号 | 字段 |
|---|---|
| `dispatch.py:828` | `f"type: {task_type}"` |
| `dispatch.py:835` | `f"card_path: {card_path}"` |
| `dispatch.py:837` | `f"card_sha256: {card_sha256}"` |
| `dispatch.py:839` | `f"phase: {phase}"` |
| `dispatch.py:841` | `f"images: {images}"` |
| `dispatch.py:843` | `f"model: {model}"` |
| `dispatch.py:849` | `f"{PRODUCER_IDENTITY_KEY}: {producer_identity()}"`（= `envelope_producer`，`dispatch.py:276`） |
| `dispatch.py:851-853` | `origin: conductor` / `loop: {loop}` / `attempt: {attempt}` |
| `dispatch.py:856` | `timeout: {int(worker_timeout_min)}` |
| `dispatch.py:858-859` | `read_scope:`（列表） |
| `dispatch.py:861` / `:863` | `l2_read_file_cap:` / `l2_read_byte_cap:` |
| `dispatch.py:865-866` | `deny_globs:`（列表） |

真实样例（conductor 产物，`H:/git/E2Feature/.agenticdoc/feature-domain-skeleton/workers/ap-feature-domain-skeleton-012-reverse-cases-contract-discipline-closeout/task.md:1-11`）：

```
---
type: phase-writer
card_path: tasks/012-reverse-cases-contract-discipline-closeout.md
card_sha256: 6fc0c76e8907bca243d4a8934cab7123732b56740f0e99d1fca5011858b2399b
phase: EXECUTE
origin: conductor
loop: exec:feature-domain-skeleton:012-reverse-cases-contract-discipline-closeout
attempt: 1
timeout: 240
l2_read_file_cap: 128
l2_read_byte_cap: 4194304
---
```

生产者 2（PM，`ui-bridge.ts`）：真实样例 `.agenticdoc/mw-dynamic-concurrency/workers/mdc-rq1-dispatch-chain/task.md:1-5`（本 key 自己的派发面）：

```
type: research
write_scope: .agenticdoc/mw-dynamic-concurrency/workers/mdc-rq1-dispatch-chain, .agenticdoc/mw-dynamic-concurrency/evidence
card_path: tasks/T-C1-dispatch-chain.md
card_sha256: d3977a6a26e8b3b70e690f1f050e5c8f37780ea38810e885a9cd4dfb032c7419
envelope_producer: agent-team-loop-pm@0.83.0
```

两套生产者都没有依赖字段。header 解析器 `card_audit.py` 只消费两个 key：

- `card_audit.py:78`：`HEADER_SCAN_LINES = 40`
- `card_audit.py:82`：`_HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*)$")`
- `card_audit.py:80-81`：`_CARD_PATH_RE = re.compile(r"^card_path\s*:\s*(?P<value>.*)$")` / `_CARD_SHA_RE = re.compile(r"^card_sha256\s*:\s*(?P<value>.*)$")`
- `card_audit.py:129` / `:171` / `:181`：`_header_value` / `parse_card_path` / `parse_card_sha256`——**只有这两个 `parse_*`**。

### 2.4 wave / 批次字段 —— 只存在于人读文本

- `tasks/*.md` 卡头有 `- 波次:`（与 `依赖` 同行），共 26 行（§2.2）。
- `plan.md` 有 `| 波次 | … |` / `## 0. 批次与依赖` 表格（§2.1）。
- **代码零处解析**：

```
PS> rg -n "波次|批次|wave" packages/multi-workers/autopilot/conductor.py packages/multi-workers/autopilot/dispatch.py packages/multi-workers/autopilot/roadmap.py packages/multi-workers/mw_common.py packages/multi-workers/launcher.py
packages/multi-workers/autopilot/conductor.py:4469:# never imports it — the parallel wave that lands xkey.py cannot change the
```

（唯一命中是注释。）

### 2.5 三态回答

**今天不存在机器可读的任务级依赖。** 存在的只有：(1) `plan.md` 的**出现顺序**（唯一被机器消费的排序信号）；(2) `plan.md` 表格 / 卡头 bullet / plan 散文里的依赖**文本**，且同义字段有三种拼写（`依赖` / `deps` / `波次+依赖`）、30/35 与 7/26 带解释性括号，无法直接当 id 列表用；(3) 一个 plan→tasks 的 id 存在性检查（`_missing_plan_tasks`），与依赖无关。

---

## §3 前沿计算所需数据与缺口

### 3.1 key 层前沿：只需要三样，今天全有

| 需要 | 今天在哪 | 状态 |
|---|---|---|
| 依赖边 | roadmap `Keys.depends_on`（`roadmap.py:433/483`） | 有 |
| 每个 key 的终态 | roadmap `> key-status:` 行 → `status_of`（`conductor.py:657-658`）+ 终态集 `_DEP_SATISFIED`（`conductor.py:64`） | 有 |
| 在飞 key | `_workers.parallel` 行 → `in_flight_keys`（`conductor.py:698-702`），in-flight 判定 `conductor.py:3539 _is_in_flight` | 有 |

即：`frontier = {k | _deps_satisfied(deps_of[k], status_of) and status_of[k] not in _DISPATCH_SKIP_STATUSES}`，今天就能算，且 `conductor.py:740` 已在算。**key 层没有数据缺口**；唯一"缺"的是配置语义（cap 从硬上限降为上界），属 RQ-C3。

实测（真实 roadmap 复算，只读）：

```
project=H:/git/E2Feature keys=42 frontier(deps satisfied & non-terminal)=
  ['feature-identity-layer-reslice', 'feature-planning-cockpit', 'feature-rbac-fixture-repair']
  → 今日 effective started = min(max_parallel_keys=2, 3) = 2
project=H:/git/JCodingAss keys=5 frontier=[]  （5 个 key 全 done，前沿空）
```

### 3.2 任务级前沿：只缺"任务依赖边"

任务级前沿 = `{task | 其所有 deps 任务已完成}`，所需四类数据：

| 需要 | 今天在哪 | 状态 |
|---|---|---|
| 任务依赖边（任务→任务） | **无**（§2 全部证据） | **缺** |
| 任务完成态 | `_workers.parallel` 行按 `task_key = ap-<key>-<stem>[-aN]` 家族聚合：`conductor.py:1698 _family_rows`；完成判定 `conductor.py:1766-1768`（`if any(r["status"] == "done" for r in fam): continue`） | 有 |
| 任务在飞态 | `conductor.py:3539 _is_in_flight` + `conductor.py:1770-1771`（`if any(_is_in_flight(r) for r in fam): return False  # per-key serial`） | 有 |
| 任务 id ↔ 卡文件 stem 的 join | `conductor.py:2832 _plan_task_file_stems`（`T-NN-slug` ↔ `NN-slug`） | 有（弱：靠正则候选，不是显式 `id:` 字段） |
| 任务写面（并行安全第二条件） | **无**——属前置件 mw-write-face-guard，本 RQ 不覆盖 | 缺（相邻） |

### 3.3 最小新增载体候选（字段名 + 落点）

按"改动最小、复用既有解析惯例、fail-closed"排序：

| # | 载体 | 字段名 | 落点 `file:line` | 说明 |
|---|---|---|---|---|
| C1（推荐） | 任务卡头部一行 | `deps: T-01, T-02`（`-`/空 = 无） | 写入位置 = `.agenticdoc/<key>/tasks/<stem>.md` 头部区；解析落点 = `packages/multi-workers/autopilot/card_audit.py:129 _header_value`（新增 `_DEPS_RE` + `parse_card_deps`，与 `:171 parse_card_path` / `:181 parse_card_sha256` 并列） | 语法与 `roadmap._parse_depends_on`（`roadmap.py:483`）逐字同构，两语言可共享测试向量；不动 `plan.md` schema |
| C2 | 同上，但元组进 envelope | `deps` → `dispatch.dispatch_card()` 返回值 | `packages/multi-workers/autopilot/dispatch.py:556-584`（`dispatch_card` 的返回 dict 加 `"deps"`），渲染点 `dispatch.py:826-866`（加一行 `deps: …`） | 需要 C1 先做；让依赖边随派发面可审计（`card_sha256` 已覆盖字节完整性） |
| C3 | 任务图消费点 | `deps_by_stem: dict[str, tuple[str, ...]]` | `packages/multi-workers/autopilot/conductor.py:1717 _plan_task_order`（签名加第二参数）/ `conductor.py:1771`（per-key 串行点改为依赖判定） | 只需一处改动即可把"出现顺序"换成"依赖拓扑序"，`_plan_task_order` 的 orphan-last 语义可保留为 fail-closed 回退 |
| C4（备选，零新增字段） | 复用 `plan.md` 的 `| 批次 |` 表 | `批次` → 整数 | 需在 `plan.md` 新增表格解析器（今天不存在），且 `批次` 只能表达"同批可并行"，无法表达任意 DAG；不推荐 |

fail-closed 约定应与 key 层一致：不可解析/悬空/环 → 该任务视为依赖未满足（退化为串行），并在 `st.timeline` 留事件（key 层今天连事件都没有，见 §4.3）。

---

## §4 环与悬空引用

### 4.1 现有验证确实检测环与悬空（判定原文）

`roadmap.py:557-575`（已在 §1.3 引全）：

- 悬空：`f"stage {stage.number} key {k.key!r}: dependency {dep!r} not found"`
- 自依赖：`f"stage {stage.number} key {k.key!r}: depends on itself"`
- 前向（跨 stage 反向）：`f"stage {stage.number} key {k.key!r}: dependency {dep!r} points to later stage {later}"`
- 环：`"dependency cycle: " + " -> ".join(cycle)`，由 `roadmap.py:596-621 _find_cycle`（DFS 三色，显式跳过悬空节点：`if dep not in color: continue  # dangling dependency: reported by validate_roadmap`）产出。

端到端判据有测试锁：`test_autopilot_roadmap.py:136`（`"not found"`）、`:202`（`"points to later stage 2"`）、`:220`（`"depends on itself"`）、`:235`（`"dependency cycle"`）。

### 4.2 但 conductor 不执行（关键判据原文）

`mw_common.py:3694-3696`（doctor 建议文案，原文）：

```python
            f"roadmap invalid: {problem} - validate_roadmap ran but the conductor does "
            "not enforce it yet"
```

生产调用者只有两个：
- `roadmap_check.py:50`：`problems = roadmap.validate_roadmap(parsed)`（独立 CLI）
- `mw_common.py:2924`：`section["problems"] = [str(problem) for problem in roadmap_protocol.validate_roadmap(parsed)]`（doctor 读数）

`conductor.py` 全文没有 `validate_roadmap` 调用（`rg -n "validate_roadmap" packages/multi-workers/autopilot/conductor.py` 零命中）。conductor 只调 `roadmap.load_roadmap`（`conductor.py:633`）与 `_emit_roadmap_warnings`（`conductor.py:639`，只报**解析** warning，不报语义 problems）。

### 4.3 后果（静态推演）

- **悬空 / 环 = 静默永锁**：`conductor.py:740` 的 `continue` 没有任何 `st.timeline.append`，也没有 gate。key 永远不进 frontier，stage 永远 `running`，`key-status` 永远非终态 → `_stage_closure`（`conductor.py:1288+`）不放行。只有 `python autopilot/roadmap_check.py` / `mw doctor` 会说出来。
- 这是 fail-closed 的**正确方向**（不放大并发），但缺**可见性**：与 spec §2.3「依赖数据不可解析时回退串行并写审计行」相比，今天连审计行都没有。
- 自依赖 / 环在**任务级**若照 C1/C3 落地，必须补校验；否则同样静默。

### 4.4 任务级新增依赖所需的校验清单（附反例）

反例按现有真实数据形状构造（标注为构造，不是仓库既有事实）：

| # | 校验 | 反例（构造） | 若缺失的后果 |
|---|---|---|---|
| V1 | 悬空 id | `tasks/T-2-x.md` 写 `deps: T-9`，而 `tasks/T-9-*.md` 不存在（plan 也未提） | 依赖永不满足；参照 key 层同型判据 `roadmap.py:558-561` |
| V2 | 自依赖 | `tasks/T-3-x.md` 写 `deps: T-3` | 同 V1；判据形如 `roadmap.py:567-571` |
| V3 | 环 | `T-2` deps `[T-3]` + `T-3` deps `[T-2]` | 两个任务都永不派发；需要一个任务版 `_find_cycle`（key 版 `roadmap.py:596` 可直接泛化，输入换成 `dependency_graph` 同型 `dict[str, set[str]]`） |
| V4 | 引用了"不在 `tasks/` 的 plan-only id" | plan 写 `T-14`，卡文件却叫 `T-14-VERIFY.md`（真实形状） | 必须走 `conductor.py:2832 _plan_task_file_stems` 的候选映射，否则合法依赖被判悬空（假红） |
| V5 | 引用了"非 worker 执行"的任务 | 卡头标 `- 负责 Agent: PM`（真实存在，428 张卡里 74 处 `负责 Agent`） | 依赖一个永不被 dispatcher 完成的 id → 死锁；需显式排除或声明"PM 直执也计完成" |
| V6 | 依赖指向重试代数不匹配 | `deps: T-2-a2`（家族行是 `ap-<key>-<stem>-aN`，`conductor.py:1698`） | 应按 base stem 归一（`_family_rows` 的 anchor 正则 `^<anchor>(-a\d+)?$` 已给出判据），否则同一任务的不同代数被当成不同节点 |
| V7 | 跨 key 依赖 | `mw-a/tasks/T-1` deps `mw-b/tasks/T-2` | 越出 roadmap key 级依赖语义（key 级已有 `depends_on`）；必须显式拒绝，否则形成跨 key 隐式序，与 `_deps_satisfied` 双层判定冲突 |

两语言镜像注意：TS 侧 `status-model.ts` 只解析 `dependsOn` 用于展示（`status-model.ts:444/485/591`），**没有任何校验**（`rg -n "cycle" packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` 零命中，唯一命中是 `:1193` 的 import cycle 注释）；若任务级依赖要呈现，需两侧同波冻结（P-021）。

---

## §5 缺口表（汇总）

| # | 缺口 | 影响 | 最小新增载体 | 落点 |
|---|---|---|---|---|
| G1 | 任务级依赖边无机器可读载体 | 任务级前沿不可算（AC-002 的前置） | 卡头 `deps:` + `parse_card_deps` | 写：`.agenticdoc/<key>/tasks/<stem>.md` 头部；解析：`packages/multi-workers/autopilot/card_audit.py:129/171` |
| G2 | 任务图无消费者（顺序即全部） | 即使有边也不会被用 | `deps_by_stem` 参数 | `packages/multi-workers/autopilot/conductor.py:1717`、`:1771` |
| G3 | 依赖边不随派发面传播 | 派发产物无法审计"为什么现在跑这个" | `dispatch_card` 返回 `deps` + header 一行 | `packages/multi-workers/autopilot/dispatch.py:556-584`、`:826-866` |
| G4 | key 层语义校验不被 dispatcher 执行 | 悬空/环 = 静默永锁（无事件、无 gate） | 在 tick 内调用 `validate_roadmap` 并对 problems 写 timeline/config 事件（不阻断派发） | `packages/multi-workers/autopilot/conductor.py:633-641`（`load_roadmap` 之后、`_stage_activation` 之前） |
| G5 | 任务级校验缺位 | 新增依赖后同型静默死锁 | 任务版悬空/自依赖/环（V1–V7） | 建议 `packages/multi-workers/autopilot/roadmap.py:596 _find_cycle` 泛化 or 新 `task_graph.py` |
| G6 | 任务 id join 靠正则候选 | 合法依赖被判悬空（假红） | 显式 `id:` 头 or 复用候选映射 | `packages/multi-workers/autopilot/conductor.py:2832 _plan_task_file_stems` |
| G7（相邻，非本 RQ） | 任务写面不可判定 → 并行不安全 | AC-002 第二条件 | 由 mw-write-face-guard 提供 | 本 key 外 |

---

## §6 残留与未验证

1. **未跑任何测试、未跑 conductor tick**。`_deps_satisfied` 的悬空行为（§4.3）是静态阅读 + fail-closed 推演，不是实跑观测；标注为**推断**。
2. **本仓库没有 `_roadmap.md`**。实测：
   ```
   PS> Get-ChildItem .agenticdoc/_autopilot | Select-Object Name, Length
   Name                 Length
   ----                 ------
   auto-decisions.jsonl   1523
   timeline.jsonl          505
   PS> python autopilot/roadmap_check.py --project H:/git/Multi-Workers
   roadmap parse error: roadmap file not found: H:\git\Multi-Workers\.agenticdoc\_autopilot\_roadmap.md
   exit=1
   PS> git log --all --oneline -- "*_roadmap.md"   # 无输出
   ```
   因此 §1.5 用的是 H: 盘其它项目的实例（`H:\git\JCodingAss`、`H:\git\E2Feature`），不是"同仓其它 key"的实例——本仓没有同仓实例可引。
3. **`.mw/dispatch-table.md` 不存在**（任务卡鼓励的取证面之一）。实测：`Get-ChildItem .mw` 仅列出 `conductor.log / dispatch.yml / launcher-beat.* / launcher.log / mw.log / mw.pid / proxy.log / serve-console.log / serve.meta / window-model`，无 `dispatch-table.md`。
4. **`- 依赖:` / `波次` 的计数只覆盖 `.agenticdoc/**/tasks/*.md`**。未扫 `.agenticdoc/**/_scratch/**`、`evidence/**` 下的复制件；未扫其它工作区（`E:\CLI_workspace\FeatureMigrator` 等）的卡，故"35 / 26 / 19 / 12"是本工作区实测值，不是全局值。
5. **未核对 `dist/` 是否有任务级依赖解析**。源码侧（`packages/multi-workers/**` + `packages/coding-agent/src/**`）零命中已实测；`dist/` 是构建产物，未逐文件核对。
6. **种子锚点漂移 1 处**：种子给 `packages/multi-workers/launcher.py:819（唯一 spawn 点）`，该行当前是 `_envelope_declaring` 的 docstring 内容（`launcher.py:818-826`）；唯一 `Popen` 调用在 `launcher.py:2008`（`proc = subprocess.Popen(cmd, **spawn_kwargs)`）。种子给 `conductor.py:744` 落在 cap 行（依赖谓词在 `:740`），`dispatch.py:964`（`def dispatch`）核对无误。
7. **未验证 `_plan_task_order` 在 plan 未提全部任务时的真实分布**（有多少 key 存在 orphan task）；只读了实现与 orphan 分支 `conductor.py:1783-1787`。

## §7 未覆盖面声明

- 未覆盖：任务级依赖的**运行时**行为（任何 dispatcher 改造都未实现、未实跑）。
- 未覆盖：跨项目统一配额 / 多工作区（`dual`、`partition` 模式）下 frontier 与 `_workers.parallel` 的关系。
- 未覆盖：`_index.parallel` claim 语义与 frontier 的交互（属 RQ-C1/C3 面）。
- 未覆盖：TS 侧 `monitor.ts` 的 `blockedBy` 与 Python 侧 `_deps_satisfied` 的逐条 parity（只各引一处判定原文，未做语料对拍）。
- 未覆盖：`stalled` 恢复路径对 frontier 的时序影响（只引了终态集合常量的定义与注释）。

[VERIFY] RQ-C2: roadmap_instances=2(JCodingAss 2stage/5key exit=0 | E2Feature 5stage/42key exit=0) | repo_roadmap=absent | frontier_E2Feature=3 keys | frontier_JCodingAss=0 keys | cap_default_max_parallel_keys=2 | plan_md_depends_on_hits=0 | plan_md_files=38 | tasks_cards=428 | card_dependency_lines=35 (pure-idlist-or-none=5) | card_wave+dependency_lines=26 (pure=19) | card_deps_field_files=12 (all mw-dual-workspace) | dispatch_taskmd_deps_hits=0 | task_dep_parsers_in_src=0 | validate_roadmap_production_callers=2 (roadmap_check.py:50, mw_common.py:2924) | validate_roadmap_in_conductor=0 | wave_in_src=1 (comment) | mw_dispatch_table_md=absent
