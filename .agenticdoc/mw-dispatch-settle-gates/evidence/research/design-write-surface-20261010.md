# DRQ-1：派发期写面校验的落点与判定表

key `mw-dispatch-settle-gates` · AC-005 + AC-003 · 只读调研（本报告是唯一写入产物）

## 0. 读取时刻与锚点声明

- 读取时刻：本报告生成时。工作树 `HEAD=776b82d7fa3af2a36a5a46717be6d5feac8ba0a0`（`git rev-parse HEAD`）。
- **脏树**：`git status --porcelain` = **72** 项（40 modified + 32 untracked）。`git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/` = 9 files changed, **1158 insertions(+), 81 deletions(-)**（含 `ui-bridge.ts`、`worker-mode.ts`、`pm-orchestrator.ts`、`task-dispatcher.ts`、`output-writer.ts`）。⇒ 行号有漂移风险，下文所有行号均为**读取当刻用 `rg` 复核过**的当刻值；实现阶段请 grep 锚名而非直接跳行号。
- 本 worker 目录：`.agenticdoc/mw-dispatch-settle-gates/workers/mds-drq1-write-surface/`；本报告未被 PM 收录前即为 `report.md`，收录名 `evidence/research/design-write-surface-20261010.md`。
- 语料：`.agenticdoc/**/task.md` 中 `type:` ∈ {research, review, verifier, reviewer, rag-research} 的全部任务书 = **97 份**（用 frontmatter 正则统计；`Get-ChildItem` 粗算 99，差 2 为 frontmatter 无 `type:` 行的 `_scratch` 手写卡）。语料分析脚本只读、写 `/tmp`，未改任何仓库文件。

已复核的锚点（读取当刻）：

| 文件 | 锚点行 |
|---|---|
| `worker/worker-mode.ts` | `TOOL_ALLOWLISTS` 63；`toolsForType` 106；`activeToolsForType` 115；`READ_TOOLS` 217；`WRITE_TOOLS` 219；`hasWriteTools` 910；`registerWorkerFileTool(pi,…)` 912 |
| `worker/worker-file-tool.ts` | `WORKER_FILE_TOOL` 30；`WORKER_FILE_MAX_BYTES` 33；`WORKER_FILE_NAME_RE` 41；`isAllowedWorkerFile` 47；`writeWorkerFile` 55；`registerWorkerFileTool` 82 |
| `pm/ui-bridge.ts` | `CROSS_KEY_READ_ONLY` 221；`foreignLiveClaimRefusal` 231；守卫调用点 1333（dispatch_worker）/1698（advance_phase）；`registerWorkerTools` 1237；`planDispatchFrontmatter` 1088；`registerWorkerCommands` 1710；`resolveOwnerKeyWithSync` 1325（dispatch_worker）/1784（/worker）；task.md 写入 1411/1816；`dispatchTask` 调用 1413/1819；`taskDir` 1376/1813 |
| `pm/task-dispatcher.ts` | `PROFILE_MARK` 14；`blockIsFresh` 136；`injectWorkspaceProfile` 237；`dispatchTask` 284 |
| `pm/pm-orchestrator.ts` | `dispatchTask` 调用 691；`DispatchAlarmKind` 387；`recordDispatchAlarm` 439 |
| `autopilot/dispatch.py` | `_CODING_TOOLS` 52；`_REVIEW_TOOLS` 53；`REGISTRY` 71；`tool_set` 146；`registry_snapshot` 152；`render_task_md` 290；`dispatch` 465；`task_md.write_text` 586 |
| `mw_common.py` | `CLI_DEFAULT_PROVIDER` 108；`DISPATCH_ROLES` 142；`TASK_TYPE_TO_ROLE` 143 |

---

## 1. 角色能力单一声明源

### 1.1 TS 侧：`worker-mode.ts:63-97` 的 `TOOL_ALLOWLISTS` + `activeToolsForType`（`:115`）

`activeToolsForType(t)` = `toolsForType(t)`（`:106`，即 `TOOL_ALLOWLISTS[t] ?? fallback`），且当且仅当 **`base.includes("write")`** 为假时追加 `worker_file`（`WORKER_FILE_TOOL`，`worker-file-tool.ts:30`）。注册门 `worker-mode.ts:910-912` 用 `toolsForType(meta.type).includes("write")` 同判据。

| type（行） | tools（顺序即 `activeToolsForType` 顺序） | write/edit | bash | 追加 `worker_file` |
|---|---|---|---|---|
| `coding`（:64） | read, write, edit, bash, find, grep, ls | ✓ | ✓ | 否 |
| `review`（:65） | read, find, grep, ls | ✗ | ✗ | **是** |
| `research`（:66） | read, find, grep, ls, **bash** | ✗ | **✓** | **是** |
| `roadmap-writer`（:72） | read, write, edit, find, grep, ls | ✓ | ✗ | 否 |
| `phase-writer`（:80） | read, write, edit, bash, find, grep, ls | ✓ | ✓ | 否 |
| `verifier`（:74） | read, find, grep, ls | ✗ | ✗ | **是** |
| `reviewer`（:75） | read, find, grep, ls | ✗ | ✗ | **是** |
| `repair`（:76） | read, write, edit, bash, find, grep, ls | ✓ | ✓ | 否 |
| `rag-research`（:79-92） | read, find, grep, ls, rag_search, rag_symbol, rag_graph, rag_impact, rag_sources, rag_feedback, rag_chat | ✗ | ✗ | **是** |
| `vision`（:95） | read, write, edit, bash, find, grep, ls | ✓ | ✓ | 否 |
| `fallback`（:96） | read, write, edit, bash, find, grep, ls | ✓ | ✓ | 否（非可派发 type：`isRegisteredType` :100 显式排除） |

- `roles_without_write`（无 write/edit）= **5**：`review`、`research`、`verifier`、`reviewer`、`rag-research`。
- 其中**真正无法写外部文件**（无 write/edit **且无 bash**）= **4**：`review`、`verifier`、`reviewer`、`rag-research`。
- ⚠ **`research` 有 `bash`（:66），bash 无写面拦截**：`worker-mode.ts:944-967` 的 read-scope `tool_call` 只拦 `read/ls/find/grep`（:946-949），`WRITE_TOOLS = {write, edit}`（:219）不含 `bash`，`worker_file` 也不在 `WRITE_TOOLS`。⇒ `research` 用 bash 重定向写仓库任意路径在**能力上完全可行**。实证：`type: research` 的 `mvr-rq1-role-type-plumbing`（`task.md` 第 1 行 `type: research`）trace.log 有 **111 次 `bash` tool_call**，且其任务书要求的唯一外部交付物 `.agenticdoc/mw-vision-role/evidence/research/spec-role-type-plumbing-20260926.md` **实存 16,575 B**。**这是 AC-005 角色集合的最大风险，见 §1.4。**

### 1.2 Python 侧：`autopilot/dispatch.py` `REGISTRY`（`:71`）+ `mw_common.py` 映射

`DispatchType`（:57-69）：`name / tools / cli / provider / requires_read_scope / conductor_dispatchable`。`_CODING_TOOLS`（:52）、`_REVIEW_TOOLS`（:53）为元组常量。

| type（行） | tools | cli | provider | requires_read_scope | conductor_dispatchable | 编码类（有 write/edit） |
|---|---|---|---|---|---|---|
| `roadmap-writer`（:73） | read, write, edit, find, grep, ls | pi | timi | False | True | ✓（无 bash） |
| `phase-writer`（:78） | read, write, edit, bash, find, grep, ls | pi | timi | False | True | ✓ |
| `verifier`（:82） | read, find, grep, ls | pi | timi | **True** | True | ✗ |
| `reviewer`（:86） | read, find, grep, ls | pi | timi | False | True | ✗ |
| `repair`（:90） | read, write, edit, bash, find, grep, ls | pi | timi | False | True | ✓ |
| `rag-research`（:98） | read, find, grep, ls, rag_search, rag_symbol, rag_graph, rag_impact, rag_sources, rag_feedback, rag_chat | pi | timi | False | **False** | ✗ |
| `vision`（:111） | read, write, edit, bash, find, grep, ls | pi | timi | False | True | ✓ |

- type→role：`mw_common.py:143` `TASK_TYPE_TO_ROLE`（11 项 → 5 role：coding/review/research/vision；未知 → `"coding"`，:314/:920 兜底），TS 镜像 `shared/dispatch-models.ts` `DISPATCH_ROLE_BY_TYPE`。
- cli/provider 默认：`mw_common.py:108` `CLI_DEFAULT_PROVIDER = {"pi": "claude", "claude": "claude-cli"}`；而 Python 派发走 registry 的显式 `provider="timi"`（:73 等），TS 手工派发也硬编码 `provider = cli === "pi" ? "timi" : ""`（`ui-bridge.ts:1352`/`:1772`）。两者对 pi 一致，非本 DRQ 的缺口。
- Python 侧无 `research`/`coding`/`review` type（那是 TS 手工桶）；`review` 类只有 `verifier`/`reviewer`。⇒ Python 侧 writeless = `verifier`/`reviewer`/`rag-research`（**3**，三者都无 bash，判据安全）。

### 1.3 现有 parity 测试（锁“角色集合 / 工具集”）清单

| # | 测试（文件:行） | 断言摘要 |
|---|---|---|
| P1 | `packages/multi-workers/test_autopilot_l0.py:233` `test_vc023_registry_parity` | Python `REGISTRY` 每个 type 的 `tools` **逐项顺序相等**于 TS `TOOL_ALLOWLISTS`（TS 侧由 `_parse_ts_allowlists` :215 正则解析源码）；`:252` 锁 TS key 集合 == py key 集合 ∪ `{coding, review, research, fallback}`；`:262` 锁 `fallback == coding`；`:245` 逐字钉 `vision` 元组 |
| P2 | `packages/multi-workers/test_autopilot_dispatch.py:31` `test_registry_types_and_tools` | Python 侧**字面**逐 type 工具元组 + `verifier.requires_read_scope is True` + 唯 `verifier` 需要 read_scope + 唯 `rag-research` `conductor_dispatchable=False` + 未注册类型 `tool_set` 返回 `()` |
| P3 | `packages/multi-workers/test_autopilot_dispatch.py:109` `test_registry_snapshot_for_parity` | `registry_snapshot()` 形状（key 集合 == `REGISTRY`） |
| P4 | `packages/multi-workers/test_mwpp_collection_parity.py:66` `test_vc008_allowlist_snapshot_unchanged` | 用 P1 的共享 `_parse_ts_allowlists`（:27）对 `_EXPECTED_ALLOWLISTS`（:39，**11 键冻结快照**）逐键顺序相等 |
| P5 | `packages/multi-workers/test_rag_research.py:71` `test_registry_snapshot_matches_ts_allowlists` | `rag-research` 条目 + “其余 registry 也保持 parity” |
| P6 | `packages/coding-agent/test/suite/autopilot-protocol.test.ts:238`（describe :237） | TS `activeTools()` 对 5 个 autopilot type 逐项相等 = `PY_REGISTRY[t] + (writeless ? worker_file : [])`（`:248/:251` 显式加 `WORKER_FILE_TOOL`）；`:341` 覆盖 manual 桶（coding/review/research/未知） |
| P7 | `packages/coding-agent/test/extensions/agent-team-loop-checkpoint-wiring.test.ts:311`（describe :309） | **已有“规则锁”**：遍历 `ALLOWLIST_SNAPSHOT`（:61，**10 键**冻结快照），断言 `writeless = !expected.includes("write")` ⇒ `activeToolsForType = writeless ? base+worker_file : base`；`:341-343` 再对真实 `before_agent_start` 后的最终集合重述 |

### 1.4 能否扩出“无 write 工具的角色集合两侧相等”？——能，具体扩法与已暴露的缺口

**缺口（必须诚实说）**：P1 的逐项相等**已经蕴含**了 7 个 Python conductor 类型的 write 存在性一致；P7 已经锁了 `+worker_file` 推导规则。真正没锁的是：

- **G-1（覆盖缺口）**：P7 只遍历 `ALLOWLIST_SNAPSHOT` 的 **10 键**（Frozen 2026-09-23），**缺 `vision`**（:95，2026-09-26 加入）。⇒ 今天给 `TOOL_ALLOWLISTS` 新增一个 writeless type，P7 不会红、P1 只在 Python 同步新增时才红。`vision` 就是这条路径上的真实先例（`worker-mode.ts:93-95` 注释 + `test_autopilot_l0.py:245` 事后补字面）。
- **G-2（跨语言缺口）**：TS-only 桶（`coding`/`review`/`research`/`fallback`）的 write 存在性没有任何 Python 侧身份与之相等——`review`/`research` 的 writeless 属性只由 TS 冻结快照自证。
- **G-3（判据口径）**：`activeToolsForType`（:115）与注册门（:910）只看 `includes("write")`，不看 `edit`。当前无 `edit`-without-`write` 的 type，但规则字面应为 `write || edit`，否则未来新增 type 会静默走错分支。

**具体扩法（三处，全部 rule-derived、零硬编码角色名）**：

1. **`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`**：加一个纯增量导出（无行为变化），把 key 集合暴露给测试：
   ```ts
   /** Live allowlist keys, in declaration order (test seam; no runtime use). */
   export function toolAllowlistTypes(): string[] { return Object.keys(TOOL_ALLOWLISTS); }
   ```
   并把 `activeToolsForType`（:115）/`hasWriteTools`（:910）的判据从 `includes("write")` 收紧为 `base.some((t) => t === "write" || t === "edit")`（修 G-3；行为对现表 byte 不变）。
2. **`packages/coding-agent/test/extensions/agent-team-loop-checkpoint-wiring.test.ts`**（扩 P7，不新建文件）：循环体从 `Object.entries(ALLOWLIST_SNAPSHOT)` 改为遍历 `toolAllowlistTypes()`；对**每个 live key**断言
   - `toolsForType(t)` 与快照值相等（快照里没有的 key 跳过，不硬编码 `vision`）；
   - `const writeless = !raw.includes("write") && !raw.includes("edit")`；
   - `activeToolsForType(t)` 等于 `writeless ? [...raw, WORKER_FILE_TOOL] : raw`；
   - 快照 key 集合 ⊆ live key 集合（新增 key 不会被快照静默漏掉）。
   这样 G-1 关闭：任何未来新增 type 都会进循环。
3. **`packages/multi-workers/test_autopilot_l0.py`** 新增 `test_vc023_writeless_parity`（扩 P1，不重复解析）：
   ```python
   ts_reg = _parse_ts_allowlists()
   py_reg = {n: list(e.tools) for n, e in dispatch.REGISTRY.items()}
   ts_only = set(ts_reg) - set(py_reg)
   py_writeless = {n for n, t in py_reg.items() if "write" not in t}
   ts_writeless = {n for n, t in ts_reg.items() if "write" not in t}
   # G-2: TS-only 桶的 writeless 贡献由集合差身份决定，不写角色名
   assert ts_writeless == py_writeless | {n for n in ts_only if "write" not in ts_reg[n]}
   for n, t in py_reg.items():
       assert ("write" in ts_reg[n]) == ("write" in t), n
   ```
   该断言在“把 `research` 改成 coding 集”“给 TS 加一个 writeless 桶而没在 Python 声明”两种情况都会红。**注意**：单纯 `assert ts_writeless == py_writeless | {...}` 在 `research` 被正确排除后仍然成立——若要锁 §1.4 的**纠正后的判据**（no write/edit/bash），应把 `"write" not in t` 换成 `not ({"write","edit","bash"} & set(t))` 并在 `_EXPECTED_ALLOWLISTS`/`REGISTRY` 两侧同改；这是 design 决策，见 §2.5/§3.5。

---

## 2. 写意图判定表（AC-005 核心）

### 2.1 语料实测：朴素正则不可用，规则必须“窄 + 带护栏”

在 97 份只读任务书上跑了两版候选判据（只读脚本，落在 `/tmp`）：

| 版本 | 规则 | 命中 | 人工复核 |
|---|---|---|---|
| v1 朴素 | 行内出现任一写动词 + 行内任一路径 token（仅排 negation + whitelisted basename） | **16/97 文件、18 处** | 真阳性约 3 处；**假阳性约 15 处（≈83%）**：`(write/edit/bash)` 工具名枚举、`Do NOT modify` 禁令、`process.stdout.write`、`output.md` 里的 `output`、`output-writer.ts` 文件名、讨论“代码在哪里写盘” |
| v2 收窄 | 先按句读（`。；！？`）切 clause；写动词前后夹住路径；叠加 negation/read-marker/代码主体/引语/归因护栏；whitelisted basename、自身目录、框架自有文件直接放行 | **39 处 / 37 文件** | 其中 **35 个文件是 `type: research`**（有 bash，历史可满足且**确实交付成功**）、仅 **2 个 `type: review`**（真 writeless）；另 5 处残余假阳性全部是“路径在动词之前 / 在讨论代码写盘” |

**结论（给 design 的硬约束）**：任何“写动词 + 路径”的裸正则都会把“**分析某段代码往哪里写**”“**禁止写到某处**”“**引用上游交付物**”误判。判定表必须显式声明 5 类护栏，且**拒绝面只认“对 worker 的显式外部写指令”**。

### 2.2 判定规则（可执行口径）

输入：`type`（task.md frontmatter 的 `type:`）、`description`（TS `dispatch_worker` 的 `description` / Python `render_task_md` 的 `prompt`）、`taskDir`（自身目录）。

1. **角色门（§1.4）**：仅当角色 writeless 才判。推荐谓词 = `!has(write) && !has(edit) && !has(bash)`（TS 侧得到 `{review, reviewer, verifier, rag-research}`；Python 侧得到 `{verifier, reviewer, rag-research}`）。**不要**用 AC 字面的 `{review, reviewer, verifier, research, rag-research}`（理由见 §2.5）。
2. **预处理**：丢弃 fenced code block（```…```）；其余行按 `。；！？` 切 clause；对每个 clause 先做“路径 token 掩码”（把路径换成空格）再找写动词，避免 `output.md`/`output-writer.ts`/`process.stdout.write` 触发 `output`/`write`。
3. **路径 token 识别**：`(盘符:/UNC/./../)…+扩展名`，或 `name.(md|py|ts|tsx|js|json|yml|yaml|log|txt|ps1|sh)`。排除 `Q1..Q5`、`i.e`、`l3-verdict.txt` 之类误报。
4. **写意图**：clause（掩码后）含写动词，且**路径出现在动词之后 ≤32 字符窗口内**（中文“写到 X”“输出到 X”，英文“write … to X”“Output: … X”）。路径在动词之前的（“X 的写入时机”“X 是怎么写的”）一律不算。
5. **放行护栏（任一命中即放行，且记一条非阻塞说明）**：
   - N: clause 含否定/禁令（`不要/不得/禁止/勿/无需/不准/do not/don't/never/must not`）；
   - R: clause 含读/参考标记（`读取/参考/作为输入/输入/引用/依据/来源/现有/已有/读/看/核对/查/扫描/read/rg/grep/current/existing`）；
   - C: clause 的主体是代码/实现（`代码/函数/语句/调用链/调用/生成处/写者/写入点/分支/由谁写/谁写/实现/路径/行号/code/function/writer/path/line`）；
   - Q: clause 处于引语/复述（`事故/例如/声称/误/「」""` 或路径被反引号引在 `要求…写到` 之后）；
   - A: 路径被归因给第三方（路径前 14 字符含 `PM/收录/由/代理/collect`）——**这是新惯例“PM 会收录为 `<external>`”的放行点**。
6. **目标分类**（写意图成立且无护栏）：
   - `basename`（无分隔符）命中 `WORKER_FILE_NAME_RE`（`worker-file-tool.ts:41`，等价 `progress.md | report.md | report-<slug>.md`，slug 1..41）⇒ **放行**；
   - 有分隔符但 `resolve(dir) == taskDir` 且 basename 命中白名单（如 `…/workers/<key>/report.md` 绝对/相对写法）⇒ **放行**；
   - basename ∈ `{output.md, task.md, trace.log, worker.log, run.json}`（框架自有）⇒ **放行** + 提示“reply 会被框架写进 output.md；要落文件请用 `worker_file file=\"report.md\"`”；
   - 其余 ⇒ **拒绝**（fail-closed）。
7. **`allowForeignWrite`**（默认关）：显式开启时跳过第 6 步的拒绝，但**仍注入契约段并在 task.md 记 `allow_foreign_write: true`**（审计）。

### 2.3 判定表（17 例；**粗体**为语料实录）

| # | 类别 | 输入（节选，来源） | 判定 | 理由 / 为什么这条规则不误伤 |
|---|---|---|---|---|
| A1 | 读用法 | **`1. **读取**。`evidence/runs/verify-20260926-190335-analysis-evidence-index.md` = PM-provided LOCATORS ONLY`**（`msc-qg-quality-gate/task.md:16`） | 放行 | 读动词 `读取` 直接前置于路径（护栏 R）；路径在动词之后但读标记同 clause ⇒ 不构写意图 |
| A2 | 读用法 | `- 输入：`evidence/research/spec-problem-framing-20260926.md`（上游已产出）` | 放行 | 护栏 R（`输入`）；无写动词 |
| A3 | 读用法 | `- 参考 `…/worker/worker-mode.ts:63-117` 的 TOOL_ALLOWLISTS` | 放行 | 护栏 C+R（`参考` + 代码路径）；`write` 只出现在“是否有 write/edit”这种工具名枚举里，被掩码 |
| A4 | 读用法 | **`- 上游交付物：`H:\…\spec-problem-framing-20260926.md`（PM 已产出，按需覆盖/深化）`**（`xkey-rm-rq2-incident-corpus/task.md:11`） | 放行 | 无写动词；`覆盖/深化` 是调研动作，路径是输入；护栏 A（`PM`）也在 |
| A5 | 读用法 | `- 见 [evidence/runs/x.md](../evidence/runs/x.md)` | 放行 | Markdown 链接 `](path)` 是引用语法；无写动词 |
| W1 | 可写 target | `- **唯一允许写入**：`worker_file file="report.md"`（只写你自己目录）`（本 key 所有任务书） | 放行 | basename `report.md` 命中 `WORKER_FILE_NAME_RE`；这是可满足的唯一正确写法 |
| W2 | 可写 target | **`Output: write your report to H:\…\workers\fmr-review-spec-design\report.md`**（`fmr-review-spec-design/task.md:21`） | 放行 | 路径解析后 `== taskDir` 且 basename 白名单 ⇒ 满足（`worker_file file="report.md"`） |
| W3 | 框架通道 | `写到 output.md`（假设式） | 放行 + 提示 | 框架自有文件（§2.2 第 6 步最后一档）；reply 会自动进 output.md，指向 `report.md` 更稳 |
| R1 | 写到外部 | **`- 唯一允许写入的文件：`.agenticdoc/mw-gate-verdict-hardening/evidence/quality-gate-report-review-20261010.md`（**新建**）`**（`mwg-qg-review-20261010/task.md:15`）**= 本 key 的事故卡** | **拒绝** | 外部目录 + 非白名单 basename；`review` 无 write/edit/bash ⇒ 不可满足（R22 复发形态） |
| R2 | 写到外部 | **`输出（唯一写面）：`.agenticdoc/mw-autopilot-verify-cli/evidence/research/design-write-lock-20260926.md``**（`design-rqd4-write-lock/task.md:5`） | 拒绝 | 同上；此卡为 `type: research`，在**纠正后的角色门**下取决于 design 决策（§2.5） |
| R3 | 写到外部 | **`**唯一允许写入**：`H:\…\evidence\research\spec-role-type-plumbing-20260926.md`。不得修改任何其他文件`**（`mvr-rq1-role-type-plumbing/task.md:7`） | 拒绝 | 绝对路径外部；`research` 有 bash ⇒ 历史可满足，纠正后的角色门会**放行**（见 §2.5） |
| R4 | 写到外部（英文） | **`Output: write findings to H:\…\mw-implementation-gate\evidence\research\w1-pi-extension-interception.md with structure: …`**（`_scratch/workers/w1-pi-extension-interception/task.md:19`） | 拒绝 | 英文 arm：`Output:` + `write … to <path>`；同样 `type: research` |
| R5 | 写到外部（bash） | **`- 你的报告用 bash（python heredoc / `>` 重定向）写到 `.agenticdoc/mw-vision-role/evidence/reviews/qg-review-mw-vision-role-20260926.md`；`**（`mvr-t16-quality-gate-review/task.md:6`） | 拒绝（**前提：**角色无 bash） | `mvr-t16` 实测 `type: research` ⇒ 有 bash ⇒ 纠正后**放行**。若同文案出现在 `review` ⇒ 拒绝。这正是把 bash 纳入角色门的必要性 |
| B1 | 边界（禁令+归因） | **`- 不要尝试 `evidence/...`、`../`、绝对路径；PM 会收录为 `evidence/research/design-write-surface-20261010.md`。`**（`mds-drq1/task.md:9`，本卡） | 放行 | 护栏 N（`不要尝试`）+ A（`PM 会收录为`）；路径 `evidence/...` 无扩展名不成 token |
| B2 | 边界（mode 值） | **`先 `mode="write"` 落骨架，再 `mode="append"` 补节`**（`mds-drq1/task.md:10`） | 放行 | `write`/`append` 是 mode 字面量，clause 内无路径 token；掩码后也没有目标 |
| B3 | 边界（复述事故） | **`真事故：任务书要求把报告写到 `<key>/evidence/xxx.md` ⇒ worker 卡在矛盾上`**（`mds-drq1/task.md:15`） | 放行 | 护栏 Q（`事故` + 引号内 `要求…写到` 的复述）；路径 `<key>/evidence/xxx.md` 无扩展名 token。**这是唯一需要引语识别才不会误伤的类别** |
| B4 | 边界（分析代码写盘） | **`- TS 侧：`worker-mode.ts:63-117`（`TOOL_ALLOWLISTS` / `activeToolsForType`）逐个角色列出工具集（表：role | tools | 是否有 write/edit）`**（`mds-drq1/task.md:20`） | 放行 | 护栏 C（`逐个角色列出工具集` 是分析语）+ 路径在动词 `write` **之前**（第 4 步“路径必须在动词之后”）；v1 朴素规则会误伤此例 |
| B5 | 边界（讨论写路径） | **`到把条目写入 `_workers.parallel` 的调用链`**（`mvr-rq2-capability-gate-hooks/task.md:10`） | 放行 | 护栏 C（`调用链`）；主语是代码不是 worker |

### 2.4 假阳性面清单（必须写进 design 的“不得误伤”清单）

| FP 面 | 真实反例 | 护栏 |
|---|---|---|
| 工具名枚举里的 `write/edit/bash` | `(write/edit/bash) BEFORE execution`（`w1-pi-extension-interception/task.md:5`） | 掩码 + 无路径后接 |
| 禁令 | `Do NOT modify any file except…`（`fmr-rq1-code-facts/task.md:16`）、`不要尝试 evidence/...` | 护栏 N |
| 分析某段代码的写盘行为 | “把条目写入 `_workers.parallel` 的调用链”“`gates.py` 里的生成处”“`run.json` 的写入时机” | 护栏 C + “路径须在动词之后” |
| 英文 `output` 当名词 | `output.md`、`…/report.md`、`process.stdout.write` | clause 掩码路径后再找动词 |
| 含 `write` 的文件名 | `output-writer.ts`、`-writer.ts` | 同上 + 路径 token 分类 |
| 复述事故原文 | “要求把报告写到 `<key>/evidence/xxx.md`” | 护栏 Q |
| 上游交付物当输入 | “上游交付物：`H:\…\spec-problem-framing-…md`” | 无写动词 + 护栏 A/R |
| 新惯例的 PM 归因 | “PM 会收录为 `evidence/research/design-…md`” | 护栏 A |
| `mode="write"` / `--write` | “先 `mode="write"` 落骨架” | 无路径目标 |
| `.md` 绝对路径就是自身 `report.md` | `workers/fmr-review-spec-design/report.md` | 自身目录 + 白名单 basename 放行 |

残余风险（诚实登记）：护栏 Q 依赖 `事故/例如/声称/引号` 关键词；若某任务书**平铺直叙**地复述一个外部写路径而不带引号/事故词，会被误拒。缓解：拒绝文案必须给出 `allow_foreign_write` 逃生阀与 `report.md` 正确写法（§3.4），且 AC-005 的告警要同时落 `dispatch-alarm` 供 PM 复核；此外建议在 design 里显式接受“误拒时 PM 用逃生阀重派”这一代价，而不是把判据放宽到重新引入 83% 假阳性。

### 2.5 ⚠ 角色集合纠正（本报告最重要的风险项，需 design 显式决策）

- AC-005 字面把 `research` 与 `rag-research` 一并当 writeless，但 `research` 的 allowlist **含 `bash`**（`worker-mode.ts:66`），而 bash 无写面拦截（`:944-967`，`WRITE_TOOLS` :219 不含 bash）。
- 语料实测：v2 判据拒绝的 37 个文件里 **35 个是 `type: research`**（全部有 bash、且历史上确实交付了外部 evidence 文件，如 `mvr-rq1` 的 16,575 B 交付物、`mvr-t16` 的 reviews 交付物）；只有 **2 个 `type: review`** 是真不可满足（含 `mwg-qg-review-20261010` 事故卡）。
- ⇒ 照字面落地 AC-005，会在真实只读语料上产生 **35/37 ≈ 95% 的误拒**，并把已稳定运行数月的 research 工作流整体打停。
- **建议判据（D-candidate）**：`isWriteless(type) = !has("write") && !has("edit") && !has("bash")`。TS 侧 = `{review, reviewer, verifier, rag-research}`（4 个）；Python 侧 = `{verifier, reviewer, rag-research}`（3 个，与字面一致，无冲突）。
- **代价**：`research` 走 bash 写外部文件的行为不再被 AC-005 拦（它是能力可行的）；若产品上仍要禁止，应作为独立 AC（例如“research 的 bash 写面审计/deny_glob 落点”）而不是塞进 AC-005。
- 需 design 回答：AC-005 的括号清单是否改成“`review`/`reviewer`/`verifier`/`rag-research`（真无 write/edit/bash），`research` 单列并说明 bash 通道”。本报告把它作为**待裁决策 D-write-1** 记录；未决策前，实现应按“角色门 = no write/edit/bash”落地，避免误拒历史工作流。

---

## 3. 落点与最小改动

### 3.1 `dispatch_worker` 与 `/worker` 是否共用一个“写 task.md + 入队”函数？

**部分共用，但关键路径不共用**：

| 环节 | `dispatch_worker`（tool） | `/worker`（command） | 共享？ |
|---|---|---|---|
| 注册 | `registerWorkerTools` `ui-bridge.ts:1237` | `registerWorkerCommands` `ui-bridge.ts:1710`（由 `pm-orchestrator.ts:1059` 注册） | 否 |
| owner key | `resolveOwnerKeyWithSync` `:1325` | `:1784` | 是（同函数） |
| 类型解析 | `resolveDispatchType` `:1046`，调用 `:1356` | 同函数，调用 `:1776` 附近 | 是 |
| 模型/phase/images frontmatter | `planDispatchFrontmatter` `:1088`，调用 `:1394` | 同函数，调用 `:1792` | **是** |
| **task.md 正文写入** | `fs.writeFileSync(taskMdPath, frontmatter+description)` **`:1411`** | 同式 **`:1816`** | **否（就地重复）** |
| 入队 + profile/RAG 注入 | `dispatchTask(...)` `:1413` → `task-dispatcher.ts:284` → `injectWorkspaceProfile` `:237` → `store.upsert` | `:1819` → 同一 `dispatchTask` | **是** |

- `dispatchTask`（`task-dispatcher.ts:284`）只接收 `{taskKey,status,cli,provider,model,taskPath}`（Omit<WorkerEntry,…>），**拿不到 ownerKey，也拿不到 description/type**；它先 `injectWorkspaceProfile(entry.taskPath)`（:237）再 `upsert`。它还被 `pm-orchestrator.ts:691`（`dispatchNewTasks` 对已存在目录）复用。
- ⇒ **AC-003 与 AC-005 今天不能靠“一处守卫”同时覆盖两条路径**：AC-003 需要 ownerKey（`foreignLiveClaimRefusal` 第二个参数）且必须在 `:1411`/`:1816` 写盘之前；AC-005 需要 description/type 且同样必须在写盘之前。可行的单点化只有一个办法：把“正文拼装 + 写 task.md”从 `:1411`/`:1816` 抽成**一个共享函数**（例如 `writeDispatchTaskMd({taskDir, frontmatter, description, taskType, ownerKey, allowForeignWrite})`，放 `ui-bridge.ts` 或新 `write-surface.ts`），把 AC-003 守卫、AC-005 判定、契约段注入全部放进去；`dispatchTask` 保持“注入 profile/RAG + 入队”。建议这么做（消除 1411/1816 的漂移面），但若要求最小 diff，则两条路径各加一次调用（本报告给两套）。

### 3.2 AC-003 最小改动（`/worker` 扩守卫）

- 守卫签名/返回形态（`ui-bridge.ts:231`）：
  ```ts
  export function foreignLiveClaimRefusal(indexStore: IndexStore, key: string): string | null
  ```
  返回 `null` = 放行；否则返回一段多行中文/英文混合文本，首行以 **`[cross-key-read-only]`**（常量 `CROSS_KEY_READ_ONLY` `:221`）开头，包含 Allowed / Refused 清单与下一步 `switch_key { key: "<k>" }` + “ask the user before stealing a live claim”（`:241-245`）。
- 现有调用点：`:1333`（`dispatch_worker`，条件 `(key ?? "").trim()`，`:1332`；**返回**为 tool 文本 `:1334`）、`:1698`（`advance_phase`，条件同款，返回 tool 文本 `:1699`）。**`/worker` 无守卫**（全文仅 2 个调用点），而拒绝文案 `:242` 已自称 “Refused: dispatch_worker, /worker, advance_phase, acking its rows.” ⇒ 文案与实现不符（G-c）。
- **最小改动（4 行）**：在 `ui-bridge.ts:1784`（`const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, keyArg, agenticdocRoot);`）之后、docs gate 之前插入：
  ```ts
  if (keyArg.trim()) {
      const refusal = foreignLiveClaimRefusal(indexStore, ownerKey);
      if (refusal) { ctx.ui.notify(refusal, "warning"); return; }
  }
  ```
  - 位置正确性：`:1813` 才建 taskDir、`:1816` 才写 task.md、`:1819` 才入队；docs gate（`:1788` 附近）与 `validateRagEnabled`（`:1779` 附近）只读。⇒ 拒绝时零副作用。
  - 只对显式 `--key` 生效：隐式路径在 `resolveOwnerKeyWithSync`（`:65-78`）已把“他人 live claim”降级到 `_scratch` 并告警，无需再判（与 `dispatch_worker` 完全同构）。
- 测试：`packages/coding-agent/test/suite/worker-crosskey-readonly.test.ts`（**untracked 新文件，已存在**）覆盖 `dispatch_worker`（:108 起）与 `advance_phase`（:180 起），**未覆盖 `/worker`**。扩一条：fake pi 捕获 `registerCommand("worker", {handler})`，调 handler，断言 notify 文本含 `[cross-key-read-only]` 且 `fs.existsSync(root/foreign/workers/...)` 为 false、`store.readAll()` 为空。

### 3.3 AC-005 落点与 `allowForeignWrite` 逃生阀

**建议的共享单元（新增，最小面）**：
- `isWritelessType(taskType)`：唯一真相源 = `activeToolsForType(taskType)`（`worker-mode.ts:115`），判据 `!has(write) && !has(edit) && !has(bash)`（§2.5）。
- `judgeWriteSurface({taskType, description, taskDir, allowForeignWrite})`：§2.2 规则，返回 `{ok:true} | {ok:false, code:"worker-write-surface", path, message}`。
- `renderWriteSurfaceContract(taskType)`：§4 的契约段。

**调用点**：
| 面 | 判定位置 | 注入位置 |
|---|---|---|
| `dispatch_worker` | `ui-bridge.ts` 类型解析后（`:1356`）～taskDir 前（`:1376`） | `:1411` 的 task.md 内容（或抽出的共享写函数） |
| `/worker` | 类型解析后（`:1776` 附近）～taskDir 前（`:1813`） | `:1816` 的 task.md 内容 |
| Python conductor | `dispatch.py:465` `dispatch()`，复用现有 `reject()`（`:486-497`），新 reason `write-surface-unsatisfiable` / ev `write-surface-rejected`，**在 `:586 task_md.write_text` 之前** | `render_task_md`（`:290`）新增参数 |

**`allowForeignWrite`（默认关）**：
- `dispatch_worker` 参数：`ui-bridge.ts` 的 `parameters: Type.Object({...})`（`:1250` 起）新增 `allow_foreign_write: Type.Optional(Type.Boolean({description: …}))`；execute 的解构（`:1300` 附近）取值，传入 `judgeWriteSurface` 与 frontmatter。
- `/worker`：flag 循环（`:1719-1752` 的 `while (["--model","--type","--reason","--key","--images"]…)`）新增 `"--allow-foreign-write"`（布尔 flag，与其它取值 flag 不同的是它不消费下一个 token；`keyArg` 分支旁需单独处理）。
- **记入 task.md 供审计**：`planDispatchFrontmatter`（`:1088`）新增 input `allowForeignWrite?: boolean`，在 `headLines`（约 `:1130`）里 `headLines.push("allow_foreign_write: true")`（可选 `write-surface-reason: <one-line>`）。Python 侧在 `render_task_md`（`:290`）同一位置加同名字段。审计值 = task.md frontmatter 行本身；契约段再渲染一行 `write-surface: override (allow_foreign_write=true)` 便于人读。
- 语义：开启时 `judgeWriteSurface` 跳过“拒绝”分支，但**仍注入契约段并记 frontmatter**（AC-005 字面要求）。

### 3.4 拒绝错误文本里“下一步”应给人什么

模板（TS tool 文本 / `ctx.ui.notify`、Python `DispatchResult.reason_detail`）：

```
[worker-write-surface] task '<task_key>' has type '<type>' (no write/edit/bash tool);
its task book requires writing to '<path>', which this role cannot reach.

Fix (pick one):
1. Put the deliverable in your own task dir: worker_file file="report.md"
   (progress.md / report-<slug>.md also work). The PM collects it afterwards.
2. Re-dispatch with allow_foreign_write: true -- recorded in task.md frontmatter
   (allow_foreign_write: true) for audit; use it only when a human accepted the external path.
3. Use a role with write tools: type: coding | repair | vision.

Your writable set: task dir only, basenames progress.md | report.md | report-<slug>.md (<=64 KiB per call).
Reply text is captured to output.md automatically -- you do not need a file for a short answer.
```

要点：给**可执行**的三种改法（`worker_file file="report.md"` / `allow_foreign_write: true` / 换 type），说明逃生阀会留审计痕迹，并列出可写 basename 全集（来源 `WORKER_FILE_NAME_RE`）。与 AC-002/AC-003 的“下一步”风格一致（`switch_key` 先例，`:244-245`）。

---

## 4. 契约段注入点与幂等

### 4.1 task.md 生成位置

- **TS 无模板函数**：内容 = `planDispatchFrontmatter(...).frontmatter` + `"\n" + description + "\n"`，直接 `fs.writeFileSync`（`ui-bridge.ts:1411` 与 `:1816`）。frontmatter 拼装在 `planDispatchFrontmatter`（`:1088`，`headLines` 起始约 `:1130`）。后续 `dispatchTask` → `injectWorkspaceProfile`（`task-dispatcher.ts:237`）再追加 profile 块（marker `PROFILE_MARK` `:14`）与 RAG 块（`<!-- mw-rag: v1 -->`，`RAG_MARKER_V1`）到 EOF。
- **Python**：`render_task_md`（`dispatch.py:290`）拼 frontmatter + `prompt.strip()`；`dispatch()`（`:465`）在 `:568-577` 调它，`:586 task_md.write_text` 落地；profile 块以参数 `profile_block`（`:549-562`）传入，RAG 块由 `_inject_rag_block`（`:160`）追加。

### 4.2 建议位置与形态

- AC-005 要求“在 `task.md` 头部自动注入写面契约段”。建议：**紧跟在 frontmatter 结束的 `---` 之后、正文之前**，标题 `## 写面契约（dispatch-injected）`，整段用**成对 marker** 包住：
  ```
  <!-- mw-write-surface: v1 -->
  ## 写面契约（dispatch-injected）
  - role: <type>（writeless: yes/no）
  - 可写：本任务目录下的 progress.md | report.md | report-<slug>.md（每次 <=64 KiB，UTF-8）
  - 工具：worker_file file="report.md"（mode="write" 落骨架 / mode="append" 补节）
  - 只读角色没有 write/edit[、bash]；不得写到本任务目录之外
  - reply 文本会被框架写入 output.md（无需为短答写文件）
  - write-surface: <normal|override (allow_foreign_write=true)>
  <!-- /mw-write-surface -->
  ```
- **不要**用“marker → EOF”替换：TS 侧 profile/RAG 块是 marker→EOF 语义（`injectWorkspaceProfile` `:237`，`blockIsFresh` `:136`），契约段若也 marker→EOF 会互相吞。用**成对 marker** 或把契约段放最后——但放最后就不再是“头部”。故推荐成对 marker，替换区间 = 两 marker 之间。

### 4.3 幂等判据（重派同一 task_key 不得重复注入）

- **TS 路径本身已有两道防重**：
  - `dispatch_worker`：`if (fs.existsSync(taskDir)) return …already exists…`（`ui-bridge.ts:1377`）⇒ 同 task_key 重派直接被拒，根本到不了注入。
  - `/worker`：taskKey = `manual-${Date.now()}`（`:1781`）⇒ 每次新 key，不会重派同一 key。
- **注入函数自身幂等**：复用 `blockIsFresh` 的“渲染结果字节相等则不动”模式（`task-dispatcher.ts:136`）：把两 marker 之间的现有文本与 `renderWriteSurfaceContract(type)` 比较，相等 ⇒ 零写入；不等 ⇒ 整段替换（手改过的半块也能被收敛成唯一一块）。
- **Python**：`task_md.write_text(content)`（`dispatch.py:586`）是**整文件覆写**，重派天然幂等；契约段由 `render_task_md` 纯函数渲染（与 `_strip_rag_block` `:127` / `_inject_rag_block` `:160` 同款 marker 替换先例）。
- **PM 手改 task.md 的判据**：AC-022 一 key 一跑，但手改后：① 若手改保留了 marker ⇒ 契约段被替换回规范文本（不会出现两块）；② 若手改删了 marker ⇒ 注入函数按“无块”插入**一次**；③ 若手改在正文里手写了一段“写面契约”而无 marker ⇒ 不视为契约段（规范段仍注入一次），但不要在正文里重复渲染同一标题（设计上标题唯一化：只在 marker 段用该标题）。⇒ 断言：任意重派/手改组合后 `grep -c '<!-- mw-write-surface: v1 -->' task.md == 1`。
- `allow_foreign_write: true` 同理：它是 frontmatter 行，由渲染函数写一次，不存在 append 路径；重派覆写时若已撤掉 flag 会随之消失（可接受，审计痕迹在 PM 侧提交历史/告警里）。

---

## 5. 反向用例设计（输入 → 期望）

1. **读用法不误伤**：`type: review`，描述 `"读取 evidence/runs/x.md 作为输入，报告写到 report.md"` → 期望：**放行**（读标记 + 白名单 basename），task.md 含 1 个契约段，无告警。
2. **编码角色完全不受影响**：`type: coding`，描述 `"把结论写到 packages/foo/bar.ts 并改 tests"` → 期望：**放行**（`activeToolsForType("coding")` 含 write/edit/bash），无判定、无告警；契约段可注入（策略允许）但必须与“writable”一致。
3. **research 走 bash（角色门纠正）**：`type: research`，描述 `"输出到 .agenticdoc/<key>/evidence/research/x.md"` → 期望（纠正后判据）：**放行**；期望（AC 字面）：拒绝。此用例是 D-write-1 的回归锚：实现按纠正后判据时断言放行，并在测试名里写明 `research_has_bash_allowed`。
4. **真不可满足**：`type: reviewer`（或 `review`/`verifier`/`rag-research`），描述 `"唯一允许写入的文件：.agenticdoc/<key>/evidence/qg.md"` → 期望：**拒绝**，错误文本含 `worker-write-surface`、外部路径、`worker_file file="report.md"`；taskDir 不存在、`_workers.parallel` 无新行、`dispatch-alarm` 记一条。
5. **跨 key（AC-003）**：`/worker --key mw-foreign <cli> <desc>`，`mw-foreign` 被他人 live 持有 → 期望：notify 含 `[cross-key-read-only]` 与 `switch_key`；无 taskDir、无队列行、无写入；与 `dispatch_worker` 行为一致（同一 `foreignLiveClaimRefusal`）。
6. **自有/未认领/_scratch 放行**：`/worker --key mw-mine`（本窗口 claim）、未认领 key、`--key _scratch` → 期望：不触发 `[cross-key-read-only]`；正常建 taskDir + 入队。
7. **完全不提写面**：`type: verifier`，描述 `"分析 X 的失败原因，给出判定"` → 期望：**放行** + 契约段注入（AC-005 的“无论是否提写面都注入”）。
8. **逃生阀**：`type: review`，描述 `"写到 .agenticdoc/<key>/evidence/x.md"`，`allow_foreign_write: true` → 期望：**放行**；task.md frontmatter 含 `allow_foreign_write: true`，契约段含 `write-surface: override`；审计可 grep 到。
9. **自身目录绝对路径**：`type: review`，描述 `"Output: write your report to H:\…\workers\<task_key>\report.md"` → 期望：**放行**（§2.2 第 6 步自身目录档）；不得因“绝对路径”字样拒绝。
10. **契约段幂等**：先派发一次，手改 task.md 在正文里追加一段 `## 写面契约`（无 marker）后再跑注入 → 期望：marker 段恰好 1 处；`grep -c '<!-- mw-write-surface: v1 -->' == 1`；正文手改段保留。
11. **mode 值不误判**：描述 `"先 mode=\"write\" 落骨架，再 mode=\"append\" 补节"`，`type: review` → 期望：放行（无目标路径）。
12. **复述事故不误判**：描述 `"真事故：任务书要求把报告写到 <key>/evidence/xxx.md"`，`type: review` → 期望：放行（护栏 Q），且因为 `review` 不可满足，设计上应接受“可被逃生阀救回”。

（用例 1/4/5/6/7 是可执行的 vitest（`test/suite/` + faux provider / fake pi），3/8/9/10/11/12 是 `judgeWriteSurface` 纯函数单测 + 一次 task.md 字符串断言；Python 侧 4/7 镜像到 `packages/multi-workers/test_autopilot_dispatch.py` 的 `dispatch()` 拒绝路径。）

---

## 6. 结论摘要（给 design 的 7 条）

1. **单一声明源**：TS `worker-mode.ts:63-97` + `activeToolsForType:115`；Python `dispatch.py:71 REGISTRY` + `registry_snapshot:152`；两侧由 P1（`test_autopilot_l0.py:233`）逐项锁、P7（`checkpoint-wiring.test.ts:311`）锁推导规则。扩锁 3 处：导出的 `toolAllowlistTypes()`、P7 改遍历 live key、新增 `test_vc023_writeless_parity`。
2. **角色门纠偏（D-write-1）**：`isWriteless = no write/edit/bash`；字面含 `research` 会在真实语料产生 35/37 ≈ 95% 误拒（`research` 有 bash，历史可满足）。
3. **判定规则**：clause 切分 + 路径掩码 + “路径须在写动词之后” + 5 类护栏（否定/读标记/代码主体/引语/PM 归因）+ 目标分类（白名单 basename、自身目录、框架自有文件放行）。裸正则在语料上 83% 假阳性。
4. **落点不共用**：`dispatchTask`（`task-dispatcher.ts:284`）只共享“profile/RAG 注入 + 入队”；task.md 正文写盘在 `ui-bridge.ts:1411`/`:1816` 就地重复。建议抽出共享 `writeDispatchTaskMd` 单点化；最小 diff 则两处各加一次调用。
5. **AC-003 最小改动**：`ui-bridge.ts:1784` 后插 4 行 `foreignLiveClaimRefusal` 守卫（`ctx.ui.notify` + return），复用 `:231` 的 `string|null` 返回与 `:241-245` 的 `switch_key` 下一步；补 `/worker` 回归用例（现有 untracked 测试未覆盖）。
6. **契约段**：成对 marker `<!-- mw-write-surface: v1 -->`；放 frontmatter 之后、正文之前；幂等 = marker 段字节相等则不动 / 否则整段替换（TS）+ 整文件覆写（Python）；断言“任意重派后 marker 计数 == 1”。
7. **逃生阀**：`allow_foreign_write`（tool 参数 / `--allow-foreign-write` / `planDispatchFrontmatter` 输入）→ task.md frontmatter `allow_foreign_write: true` 作审计。

[VERIFY] DRQ1: roles_without_write=5 parity_tests=7 judge_cases=17 must_allow=8 must_refuse=4 boundary=5 call_sites=3

---

## 7. 锚点勘误（读取当刻最终复核；覆盖 §0/§3 中的三个行号）

在报告收尾时用 `rg` 对 `/worker` 路径的调用链做了一次终检，以下三个行号以本节为准（前文括号里的旧值作废，均为同一文件 `pm/ui-bridge.ts`）：

| 锚点 | 报告中旧值 | **当刻真值** |
|---|---|---|
| `dispatch_worker` 的 `typeResolution = resolveDispatchType(cli, type ?? "")` | ：1356 | **：1348** |
| `/worker` 的 `typeResolution = resolveDispatchType(cli, typeArg)` | ：1776 | **：1766** |
| `/worker` 的 `const ragCheck = validateRagEnabled(projectDir)` | ：1779 | **：1775** |
| `/worker` 的 `const modelPlan = planDispatchFrontmatter(...)` | ：1792 | **：1797** |
| `/worker` 的 `const docGaps = dispatchDocGaps(...)` | ：1788 | **：1788（一致）** |
| `dispatch_worker` 的 `const modelPlan = planDispatchFrontmatter(...)` | ：1394 | **：1393** |

其余锚点（`foreignLiveClaimRefusal` 231、调用点 1333/1698、`resolveOwnerKeyWithSync` 1325/1784、taskDir 1376/1813、写盘 1411/1816、`dispatchTask` 1413/1819、`worker-mode.ts` 63/106/115/217/219/910/912、`worker-file-tool.ts` 30/33/41/47/55/82、`task-dispatcher.ts` 14/136/237/284、`dispatch.py` 52/53/71/146/152/290/465/586、`mw_common.py` 108/142/143）均与 `rg` 当刻输出一致。此勘误即 AC-009 所要求的“引用对最终工作区重锚”的实例（本 key 的 RQ-1 报告曾出现 ±1 漂移）。

## 8. 数字复核

- `judge_cases`：§2.3 判定表共 **18** 行（A1-A5 读用法放行 5；W1-W3 可写/框架 target 放行 3；R1-R5 拒绝 5；B1-B5 边界放行 5）。⇒ `must_allow=8`、`must_refuse=5`、`boundary=5`。
- `parity_tests=7`：P1-P7（§1.3）。
- `roles_without_write=5`；纠正后真不可满足角色 `=4`（§1.1/§2.5）。
- 语料：97 份只读任务书；v1 朴素判据 16 文件/18 处（≈83% FP）；v2 收窄判据 39 处/37 文件，其中 `type: research` 35、`type: review` 2。
- `call_sites=3`：`dispatch_worker`（`ui-bridge.ts:1411`）、`/worker`（`:1816`）、Python `dispatch()`（`dispatch.py:586`）——三处 task.md 落盘前都必须过判定；AC-003 的守卫点另计 2 处（`:1333` 已有、`/worker` 待补于 `:1784` 后）。

[VERIFY] DRQ1: roles_without_write=5 parity_tests=7 judge_cases=18 must_allow=8 must_refuse=5 call_sites=3


---

## PM 现场复核（2026-10-10 22:05，`mw-dispatch-settle-gates` PM）

正文逐字收录；以下为 PM 独立复核与**口径收窄**（AC-009）。

### 确认

| worker 结论 | 复核 | 证据（PM 读到的行） |
|---|---|---|
| `research` 角色**有 `bash`** | **成立（决定项）** | `worker-mode.ts:66` `research: ["read","find","grep","ls","bash"]`；`review`/`verifier`/`reviewer` = `:65`/`:74`/`:75`（无 bash 无 write）；`rag-research` `:80-92` |
| `read_scope` 只拦 read/ls/find/grep | **成立** | `worker-mode.ts:944-950`（`event.toolName !== "read" && !== "ls" && !== "find" && !== "grep"` 直接 return）⇒ **bash 不受 read_scope 约束** |
| writeless ⇒ 追加 `worker_file` | **成立** | `activeToolsForType:115-118`（`base.includes("write") ? base : [...base, WORKER_FILE_TOOL]`） |
| Python 侧 writeless 集 | **成立** | `dispatch.py:71` `REGISTRY`：`verifier` `:83`/`reviewer` `:87`/`rag-research` `:98` 用 `_REVIEW_TOOLS`/rag 工具；`roadmap-writer`/`phase-writer`/`repair` 是 `_CODING_TOOLS` |
| `/worker` 写路径在 `:1813`/`:1816` | **成立** | `ui-bridge.ts:1784`（`resolveOwnerKeyWithSync`）→ `:1789-1794`（docs 门）→ `:1797`（`planDispatchFrontmatter`，注释 `:1796` 明说"refusal must leave no task dir"）→ `:1813` `workerTaskDir` → `:1814` `mkdirSync` → `:1816` `writeFileSync` → `:1819` `dispatchTask` ⇒ AC-003 守卫必须插在 `:1813` 之前 |
| `dispatch_worker` 与 `/worker` 就地重复写 task.md | **成立** | `:1411` 与 `:1816` 两处同样的 `fs.writeFileSync(taskMdPath, ...)` ⇒ DRQ-1 的"抽出单点 `writeDispatchTaskMd`"是正确最小改法 |

### 口径收窄（PM 量测，替换 worker 的 97 份口径）

Worker 用"无 write/edit"（97 份：research 73 + review 24）算误拒率；但 `research` **有 bash** ⇒ 它能自己写外部路径，**不在 AC-005 的保护对象内**（保护它是假保护）。
PM 重新量测（脚本 `.tmp/t24-ac005-corpus.py`，全仓 286 份 task.md）：

| 口径 | 份数 | 朴素 v1 命中 | 收紧 v2 命中（写动词 + 带后缀路径） |
|---|---|---|---|
| `!write && !edit && !bash`（**采纳**：review 24 + verifier/reviewer/rag-research 0） | **24** | 8（真阳性 **1**）⇒ 假阳性 88% | **2**（`mwg-qg-review-20261010` 真阳性 + `mw-rag-integration-design-review` 命中 `output.md`） |
| 含 `research`（spec 初版） | 97 | 53 ⇒ 约 98% 假阳性 | 6 |

⇒ **加"自身目录/basename 白名单放行"后，24 份真实只读任务书上 0 假阳性、1 真阳性（正是那次空转事故卡）**。
另注：PM 自己写的 DRQ 任务书（`mds-drq1`/`mds-rq2`）也被 v2 命中 `<key>/evidence/xxx.md`——那是**背景段的否定引语**（"不要尝试 evidence/…"）⇒ DRQ-1 列的"否定/引语复述"护栏是**必需项**，PM 的任务书本身就是它的测试素材。

### 采纳

- AC-005 角色门 = **`!write && !edit && !bash`**（4 类：`review`/`verifier`/`reviewer`/`rag-research`）；判定必须含 5 类护栏（否定 / 读标记 / 代码主体 / 引语复述 / PM 归因）+ 白名单与自身目录放行 + `allow_foreign_write` 逃生阀。
- AC-003 落点 = `ui-bridge.ts:1813` 之前（与 `:1333` 的 `dispatch_worker` 共用判定函数）。
- 残余风险（登记）：`research` 的 **bash 完全不受 write 面约束**（read_scope 只覆盖 read/ls/find/grep `:944-950`）⇒ 记为残留 **R23**（是否单开 key 由用户定）。
