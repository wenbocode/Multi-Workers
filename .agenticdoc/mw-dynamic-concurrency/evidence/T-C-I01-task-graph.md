# T-C-I01 · 任务图模块 `task_graph.py` — 证据

> Key：`mw-dynamic-concurrency` · 卡：`tasks/T-C-I01-task-graph.md`（sha256 `303c814910587ee2d076a91e931efb956577acccad2974ebbace21017d2a0004`）
> 角色：coding worker（M-01，B0）· 日期：2026-10-14
> 目标锚点：`.agenticdoc/goal.md` — 让一个 PM Agent 管理多个 Worker Agent **并行**开发；本卡只交付其地基（依赖解析 + 校验 + 前沿），**不放开任何并发、不改任何派发行为**。

## TL;DR

1. 新增纯函数模块 `packages/multi-workers/autopilot/task_graph.py`（612 行，stdlib only：`re` + `dataclasses`），导出 `parse_card_deps` / `deps_declaration_lines` / `numeric_core` / `join_deps` / `find_cycle` / `validate_task_graph` / `frontier` + `DepProblem`/`TaskGraph`。
2. 卡头区域解析覆盖 4 种真实写法（`- deps:` / `- 依赖:` / `deps:` / `- 依赖：`）+ 内嵌 `· 依赖:`；正文里的 `- 依赖:` 被区域规则挡住（真实卡 `timi-gpt-pi-routing/tasks/007-build-verify.md:19` 实测 `[]`）。
3. join 只用**数字核心**：`T-1` 唯一命中 `T-01-*`；同核多命中判**歧义**（`agent-team-loop` 的 `T-01-file-lock` vs `T-01-task-protocol`），绝不任选。
4. V1–V7 全部结构化（`kind` + `card_id` + 1-based 原文行号 + 原文片段）；任一问题/歧义 ⇒ `TaskGraph.plan_is_serializable=False`（整 key 串行回退信号），无部分生效、无默认放大。
5. 真实卡面实测：445 张卡、150 有行 / 295 无行、201 个 dep token（180 绑定 / 10 歧义 / 4 Unsupported / 7 非 id 散文 / 0 悬空 / 0 跨 key）；max 依赖行 = 9（`HEADER_SCAN_LINES=40` 够用）。
6. 验收：`python -m pytest test_task_graph.py -q` → **71 passed**；可选全包回归 `python -m pytest -q` → 2124 passed / 6 failed（6 条与本模块无因果面，详见下文）。

## 交付物

| 文件 | 状态 | 内容 |
|---|---|---|
| `packages/multi-workers/autopilot/task_graph.py` | 新建 | 纯函数任务图模块（无 I/O、无全局状态、不 import `conductor`、不复用 `card_audit._header_value`） |
| `packages/multi-workers/test_task_graph.py` | 新建 | 71 条测试：解析 / V1–V7 / join / 前沿 / 真实卡面扫描 |

- 只读面复核：未改 `conductor.py` / `config.py` / `dispatch.py` / `card_audit.py` / `packages/coding-agent/**`；未写 timeline、未读 `_workers.parallel`。
- 唯一的仓库外临时探测脚本写在 `%TEMP%`，本仓只新增/写入上表 2 个文件 + 本证据文件。

## 验收输出

命令（卡内原文）：

```
cd packages/multi-workers; python -m pytest test_task_graph.py -q
```

原文输出：

```
.......................................................................  [100%]
71 passed in 0.21s
```

可选回归（`python -m pytest -q`，全包 2130 例）：**6 failed, 2124 passed, 10 deselected**（327.9s）。6 条失败与本卡无关：`test_autopilot_readcap_injection` / `test_autopilot_verdict_freshness` / `test_launcher`（BOM）/ `test_mwds_t27_service_envelope`（TS 镜像）/ `test_mwds_t29_producer_signal`（TS 镜像）/ `test_task_type_parity`（BOM）。依据：`git grep task_graph` 除本卡两个新文件外命中 0（本模块未被任何生产代码或测试 import），且当前工作树有其它 session 的并发改动（`packages/coding-agent/src/extensions/agent-team-loop/**` 等），TS 镜像类失败与本模块无因果面。

## 真实卡面实测

口径：扫 `.agenticdoc/*/tasks/*.md`（排除 `_`/`.` 前缀），按 key 分组，逐卡用本模块解析与校验；命令为 `%TEMP%` 下的 `mw_probe_final.py`（可复算）。

```
[VERIFY] cards_total=445 keys=44
[VERIFY] cards_with_line=150 cards_without_line=295
[VERIFY] forms={'bullet_deps': 12, 'bullet_yilai': 51, 'bare': 6, 'embedded': 81}
[VERIFY] dep_tokens_total=201
[VERIFY] join_bindings=180 ambiguous=10 dangling=0 unknown=7 cross_key=0 unsupported=4
[VERIFY] max_deps_line=9 HEADER_SCAN_LINES=40
```

逐条 **[VERIFY]**（case 原文 + 命令 + 实际数值）：

| # | case 原文 | 命令 / 复算 | 实际数值 |
|---|---|---|---|
| V-01 | `mw-rag-window-parity/tasks/T-4-VERIFY.md:5` `- 依赖: T-1、T-2、T-3 全部完成` | `join_deps(['T-1','T-2','T-3'], <stems>)` | 唯一绑定 `T-1→T-1-SKILL-DIR-PARITY`、`T-2→T-2-MW-RAG-CMD`、`T-3→T-3-DOCTOR-RAG-ROW`（数字核心救回，`_plan_task_file_stems` 对 `T-1` 命中 0） |
| V-02 | `mw-dual-workspace/tasks/002-py-target-config-parity.md:9` `- deps: [001]` | `parse_card_deps` + `join_deps` | `['001']` ⇒ `001→001-ts-target-config`（flow list 剥离 + 数字核心） |
| V-03 | `agent-team-loop/tasks/T-05-launcher.md:5` `deps: T-02, T-03, T-04` | `join_deps(..., <23 stems>)` | 三个 token 全 **ambiguous**（该 key `T-02`/`T-03`/`T-04` 各两份） |
| V-04 | `agent-team-loop/tasks/T-06-smoke-test.md:5` `deps: T-01, T-02, T-03, T-04, T-05` | 同上 | 5 个 token 全 ambiguous；全 key 歧义计数 = **10** |
| V-05 | `timi-gpt-pi-routing/tasks/007-build-verify.md:19`（`## 输入` 正文）`- 依赖: Stage 1 全部完成（TS 检查需要零错误）、Stage 2 全部完成` | `parse_card_deps` | `[]`（区域规则在 `## 输入` 即止，正文依赖不被读） |
| V-06 | `mw-vision-role/tasks/T-14-verification-closeout.md:5` `- 依赖: T-01…T-13 全部 · 预估: 60-90min` | `validate_task_graph` | `deps-unsupported`，`line=5`，`snippet` 保留 `T-01…T-13`（D-110：判 Unsupported，不展开） |
| V-07 | `mw-gate-verdict-hardening/tasks/T-16-docs-dist.md:3` `- 波次: **4** · 依赖: T-01…T-15、T-17…T-23（全部 done）` | 同上 | 2 个 `deps-unsupported`（区间不展开） |
| V-08 | `mw-dual-workspace/tasks/011-regression-baseline.md:9` `- deps: [001, 002, …, 010]` | 同上 | `deps-unsupported`（`…`） |
| V-09 | 全库 | 有行卡数 | **150**（`- deps:` 12 行 / `- 依赖:` 51 行 / 裸 `deps:` 6 行 / 内嵌 `· 依赖:` 81 行）；无行 **295**；合计 445 |
| V-10 | 全库 | dep token | **201** = 绑定 180 + 歧义 10 + Unsupported 4 + 非 id 散文 7；悬空 0、跨 key 0 |
| V-11 | 全库 | 依赖行行号 | max = **9**（远小于 `HEADER_SCAN_LINES=40`） |

有依赖行的 key（18 个 key，其余 key 无任何声明）：

```
agent-team-loop:23/6(ambiguous=10)  mw-autopilot-slot-capacity:24/24(unsupported=1)
mw-autopilot-stall-feedback:9/9     mw-crosskey-risk-escalation:2/2
mw-dispatch-role-escape:3/3         mw-done-closure-repair:11/11(unknown=1)
mw-dual-workspace:12/12             mw-gate-verdict-hardening:23/23(unsupported=2)
mw-l3-fail-marker-forms:7/2(unknown=3)  mw-rag-config-guide:3/3
mw-rag-integration:14/2             mw-rag-integration-fix:5/5
mw-rag-window-parity:5/5            mw-task-scope-isolation:3/3
mw-vision-role:19/19(unsupported=1) mw-worker-progress-persist:6/6
mw-worker-visibility-gate:6/6       xkey-repair-mechanism:9/9(unknown=3)
```

口径说明（与设计调研 `design-task-deps-20261014.md` 的差异，均已复算）：

- 该调研（2026-10-14）测 434 卡 / 117 有行 / 317 无行；本轮 445 卡 / 150 / 295。差异来源：新增 key（`mw-dynamic-concurrency`、`mw-write-face-guard`、`mw-worker-output-contract` 等）+ 本模块把内嵌 `· 依赖:` 的识别从"仅 `- 波次:` 行"放宽到"任意元信息行的 `· 依赖:` 段"（实测 81 内嵌行 vs 调研 47 行）。放宽方向是 fail-closed（多读依赖只会更晚放行，不会过早并行）。
- 调研测 146 token（唯一 125 + 歧义 10 + 散文 11）；本轮 201 token（绑定 180 + 歧义 10 + Unsupported 4 + 散文 7）。歧义量级一致（10，全部来自 `agent-team-loop`）；悬空一致（0）。
- 7 个散文 token 全部是"非任务 id 的依赖"（如 `冻结契约`、`design §2 契约`、`provenance-guard 会话落地`），按设计判 V1 ⇒ 这些 key 整层串行回退，属预期的 fail-closed。

## V1–V7 与前沿构造

以下为程序实际输出（`%TEMP%/mw_probe_evidence.py`，可复算）。**反例**（每类问题的正例），**正例** = `clean-ok`（`- deps: -` ⇒ `problems=[]`，`plan_is_serializable=True`）。

| # | kind | 输入卡头原文 | 实际输出（kind / line / token / snippet） | 副作用 |
|---|---|---|---|---|
| V1 | `deps-unknown-id` | `- 依赖: 等设计冻结后再说` | `deps-unknown-id / 3 / '等设计冻结后再说' / '- 依赖: 等设计冻结后再说'` | `plan_is_serializable=False` |
| V1b | `deps-unknown-id` | 节点 `T-99-x` 不在卡集 `['T-01-a']` | `deps-unknown-id / card=T-99-x / line=0 / 'node not in the key card set'` | 同上 |
| V2 | `deps-dangling` | `- deps: T-99` | `deps-dangling / 3 / 'T-99' / '- deps: T-99'` | 同上 |
| V3 | `deps-cycle` | `T-01-a: - deps: T-02-b`；`T-02-b: - deps: T-01-a` | `deps-cycle / card=T-01-a / line=3 / snippet='- deps: T-02-b' / detail='dependency cycle: T-01-a -> T-02-b -> T-01-a'` | 同上 |
| V4 | `deps-cross-key` | `- deps: ../other/tasks/T-2` | `deps-cross-key / 3 / '../other/tasks/T-2' / '- deps: ../other/tasks/T-2'` | 同上 |
| V5a | `deps-duplicate` | `- deps: T-2, T-02` | `deps-duplicate / 3 / 'T-02' / '- deps: T-2, T-02'` | 同上 |
| V5b | `deps-duplicate` | `- deps: -` 后接第二行 `- deps: T-01-a` | `deps-duplicate / 4 / '' / '- deps: T-01-a'`（detail=`second deps declaration line`） | 同上 |
| V6 | `deps-self` | 卡 `T-05-mw-rag-cmd` 写 `- deps: T-5` | `deps-self / 3 / 'T-5' / '- deps: T-5'`；`find_cycle({'a':('a',)}) == ['a','a']` | 同上 |
| V7 | `deps-unsupported` | `- 依赖: T-01…T-13 全部 · 预估: 60-90min` | `deps-unsupported / 3 / 'T-01…T-13 全部' / 原文片段` | 同上 |

`…` / `...` / `~` / `～` / `*` 全部走同一个可逆点 `_RANGE_RE`（`task_graph.py:97`），判 Unsupported、不展开（D-110）。

**join 结果**（`deps: T-1` 与 `T-01-*`）：

```
join T-1 -> T-01-*    : bindings={'T-1': 'T-01-skill-dir-parity'}
join T-01 ambiguous   : bindings={} ; ambiguous={'T-01': ('T-01-file-lock', 'T-01-task-protocol')}
join real T-4 deps    : bindings={'T-1': 'T-1-SKILL-DIR-PARITY', 'T-2': 'T-2-MW-RAG-CMD', 'T-3': 'T-3-DOCTOR-RAG-ROW'}
join 001 flow list    : bindings={'001': '001-ts-target-config'}
```

`numeric_core` 保留原写法（`T-01-x → "01"`、`T-1 → "1"`），join 用 `int()` 归一 ⇒ `1 == 01`。

**前沿构造（3 组）**：

```
chain  A→B→C  F={}    -> ['A']            # 恒 1（入口未完成时只有入口就绪）
chain  A→B→C  F={A}   -> ['B']            # 恒 1
chain  A→B→C  F={A,B} -> ['C']            # 恒 1
fanout R→X,Y,Z F={}   -> ['R']
fanout R→X,Y,Z F={R}  -> ['X','Y','Z']    # = 可并行数 3
mixed  F={A}          -> ['B','C','E']    # 混合：B/C 依赖 A，E 独立
mixed  F={A,B}        -> ['C','D','E']    # 混合：D 在 B 之后
```

顺序恒等于传入的 `deps_by_id` 卡序（保持 M-02 要用的 `_plan_task_order` 稳定性）；不存在的依赖不阻塞（`frontier({'A':('ghost',)}, set()) == ['A']`），但该情形已在校验层判 `deps-dangling` 并触发整层串行回退。

## 残留与未验证

1. **写面维度不在本模块**：`frontier` 只算依赖前沿，不含 `mw-write-face-guard` 的"写面可判 + 与在飞不交"。M-02 必须把该谓词与 `frontier` 结果取交；未声明写面 ⇒ serial-only（WFG D-003），本卡不复制该判定。
2. **无副作用**：不写 timeline、不发事件、不读 `_workers.parallel`、不改任何上界（M-02/M-03/M-04 的写面）。
3. **内嵌 `· 依赖:` 的放宽**：本模块对任意元信息行的 `· 依赖:` 段都解析（不止 `- 波次:`）。实测 81 内嵌行、其中 7 个 token 是非 id 散文（`冻结契约` 等）⇒ 该 key 整层串行。若 M-02 希望只在 `- 波次:`/`- 依赖:` 行解析，改动点集中在 `_deps_value`。
4. **V1/V2 的切分口径**：卡内把两者都描述为"id 不可用"。本模块按**是否具备 id 语法**切分：无 id 形状（散文）⇒ V1 `deps-unknown-id`；有 id 形状但无对应卡 ⇒ V2 `deps-dangling`；另补 V1 的第二子情形"节点不在卡集"。两 kind 都触发回退，切分只为可独立断言。
5. **V3/V6 的切分口径**：`find_cycle` 是 V3 检测器且把自环算作长度 1 的环（`['a','a']`）；`validate_task_graph` 把自环归到 V6，避免与 V3 重复上报；长度 ≥2 的环报 V3，且 `line`/`snippet` 指向该环的第一条真实依赖行（非 0）。
6. **`*` 通配的识别**：先剥离 `**`（加粗）再查 `_RANGE_RE`，因此 `**T-15 必须先完成**` 解析成 `T-15`，而真正的 `T-*` 判 V7。deps 值里孤立的 `*` 会判 V7。
7. **区间不展开**：D-110 明确不展开；扩展点只有 `_RANGE_RE` 一处 + 语料。
8. **语料漂移**：445/150/295/201 会随新 key 增长；测试断言用下界（`cards≥400`、`with_line≥100`、`without_line≥250`、`bindings≥120`、`ambiguous≥8`、`unsupported≥2`）+ 恒等式 `with_line+without_line==cards`，不硬编码调研数字。
9. **全量 `python -m pytest -q` 不是本卡验收门**（卡内标注"可选"）：实测 6 条失败全部与本模块无因果面（`git grep task_graph` 命中 0、另有其它 session 并发改 `coding-agent` TS 面 / Windows GBK BOM 环境噪声）；本卡验收只用 `test_task_graph.py`。
10. **未验证**：M-02 把 `frontier` 结果接入 `execute_loop` 后的真实 tick 行为、`write_face_ok` 与前沿取交后的实起数、以及 `plan_is_serializable=False` 时的 timeline 事件（均属 M-02）。

## 上下文来源

- 卡：`.agenticdoc/mw-dynamic-concurrency/tasks/T-C-I01-task-graph.md`
- 决策：`.agenticdoc/mw-dynamic-concurrency/design.md` D-103（载体与算法）、D-104（V1–V7；任一问题 ⇒ 整 key 串行回退 + timeline，事件由 M-02 写）、D-110（区间判 Unsupported，可逆点 `_RANGE_RE`）
- 计划：`.agenticdoc/mw-dynamic-concurrency/plan.md` §0/§1/§2 M-01（写面唯一性：`task_graph.py` + `test_task_graph.py`）
- 设计证据：`.agenticdoc/mw-dynamic-concurrency/evidence/research/design-task-deps-20261014.md`（载体形态、`_header_value` 不可复用 5/5、数字核心 125/10、`deps: T-1` 真实存在于 `mw-rag-window-parity`）
- 源码依据：`packages/multi-workers/autopilot/card_audit.py:82/160-162`（不可复用）、`roadmap.py:596-626`（`_find_cycle` 泛化来源）、`conductor.py:1717 _plan_task_order`（前沿顺序要喂给它的稳定性）、`conductor.py:64 _DEP_SATISFIED`
- 目标：`.agenticdoc/goal.md`（并行开发 + 文件驱动协调；本卡为其依赖地基）

## 改动历史

| 文件 | before → after | 说明 |
|---|---|---|
| `packages/multi-workers/autopilot/task_graph.py` | 新建（0 → 612 行） | `DepProblem:141`、`TaskGraph:164`、`_iter_header_lines:208`、`_deps_value:251`、`_classify_tokens:282`、`parse_card_deps:317`、`deps_declaration_lines:328`、`numeric_core:340`、`join_deps:361`、`find_cycle:443`、`validate_task_graph:489`、`frontier:595`；`_RANGE_RE:97`（D-110 可逆点） |
| `packages/multi-workers/test_task_graph.py` | 新建（0 → 678 行） | 71 测试；解析 `:57-262`、join `:285-333`、cycle/frontier `:337-385`、V1–V7 `:388-506`、纯度守卫 `:509`、真实卡面 `:530-677` |
| `.agenticdoc/mw-dynamic-concurrency/evidence/T-C-I01-task-graph.md` | 新建 | 本证据文件 |
