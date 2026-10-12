# RQ-4: `task.md` `type:` 解析面与 frontmatter-only 影响面（缺口 A8 / 接缝 C3）

只读研究。未修改任何源码/测试/task.md；仓库内唯一写入 = 本文件。

## 结论摘要

1. **A8 成立且可复现**：`parseTaskMd` 逐行扫全文、last-wins（`worker-mode.ts:333-334`），而任务书正文就是派发参数 `description` 的逐字拷贝（`ui-bridge.ts:1791` / `:2248`，无转义）⇒ 任务书正文任意一行 `type: <t>` 会在**运行时**改写 worker 的角色与工具白名单。
2. **派发侧判据不复用 worker 侧解析**：`resolveDispatchType`（`ui-bridge.ts:1065`）校验的是**调用参数**；`judgeWriteIntent`（`:1444`）/`isWritelessRole`（`worker-mode.ts:133`）/`isShellRole`（`:126`）吃的都是同一个参数（`:1451` 等），写入的 `type:` 在 `:1145` 生成。两侧只在「参数串 == 头部那行」时偶然一致；正文可推翻它。
3. **语料计数（305 本任务书，全在 `.agenticdoc/**`）**：`with_frontmatter_type=304`、`with_body_type_line=4`、**`files_where_body_would_flip_role=1`**（`.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md`：头部 `coding`、正文第 3 行 `type: review`，运行时角色 = review）。任务书第 4 条「应为空集」的预期**不成立**；该文件在 frontmatter-only 下会把角色从 review 放宽回 coding（write/edit/bash 回归）。
4. **frontmatter 包裹形态**：现存语料 **0/305 带 `---` 包裹**（全是不带 fence 的裸头部 + 空行 + 正文）；但 Python/conductor 生产者**确实产出 fence**（`autopilot/dispatch.py:347-374`），测试也大量使用 fenced fixture ⇒ 新规则必须同时吃两种形态。
5. **同类 `type:` 解析器当前有 6 份**（见 §3），只有 worker 侧那一份决定工具白名单/写面守卫；且 launcher（Python，first-wins，`launcher.py:155`）与 worker（last-wins）已在语料中**实测分歧 1 例**。
6. **测试影响**：全 TS 测试套件无任何 fixture 含两个 `type:` 值（机器扫描 0 命中）⇒ first-wins 与 last-wins 在现有 fixture 上行为等价。会被「只认 frontmatter」影响的是「`type:` 不在第 1 行」与「fenced」两类 fixture（清单见 §4），用「首个空行之前的连续头部块」规则可全部保持通过。

## 判定规则（用于 §1 计数，必须先声明）

- 读文件时剥离 UTF-8 BOM（`encoding="utf-8-sig"`）。
- **fenced 形态**：第 1 行 `trim() == "---"` ⇒ 头部区 = 第 1 个 `---` 与下一个 `---` 之间（不含两端）；正文 = 闭合 `---` 之后。
- **unfenced 形态**（现存语料全部如此）：头部区 = **首个空行（`trim()==""`）之前的连续行**；正文 = 首个空行及其后。该边界与框架自身的一致：`applyWriteSurfaceContract` 用 `cleaned.search(/\n\s*\n/)`（`ui-bridge.ts:1507`）定位「leading frontmatter block」。
- **正文 `type:` 行** = 位于正文区、且 `trim()` 后以 `type:` 开头的行（与 `parseTaskMd` 的匹配条件完全相同，含缩进行与代码块内行）。
- **last-wins 复刻** = 全文最后一个匹配行的值（无则 `"default"`，`worker-mode.ts:312`）。
- 角色/能力用源码镜像：`TOOL_ALLOWLISTS`（`worker-mode.ts:71-104`）+ `DISPATCH_ROLE_BY_TYPE`（`shared/dispatch-models.ts:59-71`）+ `activeToolsForType`/`isWritelessRole`/`isShellRole`（`worker-mode.ts:114-135`）。
- 边界敏感性：现存语料 **0 个文件没有空行**（`files_without_blank_line=0`），首个空行行号分布 = `{1:249, 2:44, 3:11, 4:1}` ⇒ 规则在整个语料上处处良定义，不存在「整个文件都算头部」的退化。

## 1. 语料计数（命令 + 原始输出）

### 1.1 命令

枚举（PowerShell + ripgrep 交叉核对）：

```powershell
& "C:\Users\wenbozhou\.pi\agent\bin\rg.exe" -uu --no-ignore --files -g "task.md" H:\git\Multi-Workers | Measure-Object -Line
```

计数脚本（**未落盘**：经 stdin 交给 Python，仓库与临时目录均无临时文件）：

```powershell
@'
<scripts/mwgf-rq4 计数脚本全文见下>
'@ | python -
```

其中计数脚本正文（Python 遍历，跳过 `.git`，其余全含）：

```python
import os, re, collections
ROOT = r"H:\git\Multi-Workers"
# TOOL_ALLOWLISTS / DISPATCH_ROLE_BY_TYPE / role_for / active_tools / is_writeless / is_shell 为源码镜像
files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d != ".git"]
    if "task.md" in filenames:
        files.append(os.path.join(dirpath, "task.md"))
files.sort()
for p in files:
    text = open(p, "rb").read().decode("utf-8-sig", errors="replace")
    lines = text.split("\n"); tr = [l.strip() for l in lines]
    tl = [(i, tr[i][5:].strip()) for i in range(len(lines)) if tr[i].startswith("type:")]
    last_wins = tl[-1][1] if tl else None
    is_fenced = bool(tr) and tr[0] == "---"
    if is_fenced:
        close = next((i for i in range(1, len(tr)) if tr[i] == "---"), None)
        fm_range = range(1, close) if close is not None else range(1, len(tr))
        body_range = range(close + 1, len(tr)) if close is not None else range(len(tr), len(tr))
    else:
        blank = next((i for i in range(len(tr)) if tr[i] == ""), None)
        fm_range = range(0, blank) if blank is not None else range(0, len(tr))
        body_range = range(blank, len(tr)) if blank is not None else range(len(tr), len(tr))
    fm_types = [(i, tr[i][5:].strip()) for i in fm_range if tr[i].startswith("type:")]
    body_types = [(i, tr[i][5:].strip()) for i in body_range if tr[i].startswith("type:")]
    front = fm_types[0][1] if fm_types else None
    # ... 逐文件记录 frontmatter/body 值、last-wins 值、角色与能力四元组、isRegisteredType
```

### 1.2 原始输出（关键块，逐字）

```
=== COUNTERS ===
task_md_total=305
fenced_frontmatter_files=0
unfenced_frontmatter_files=305
with_frontmatter_type=304
frontmatter_without_type=1
with_body_type_line=4
body_type_lines_total=4
files_where_body_would_flip_role=1
files_where_body_would_flip_capability=1
files_lastwins_differs_from_frontmatter_type=1
files_lastwins_type_unregistered=0
fence_unclosed=0
near_miss_type_lines=0

=== FRONTMATTER_WITHOUT_TYPE ===
.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md lastwins=None

=== BODY_TYPE_LINES (path:line:value) ===
.agenticdoc/goal-autopilot/workers/ga-spec-design-review-2/task.md:4:coding
.agenticdoc/mw-partition-parent-extended/workers/mwppe-quality-gate/task.md:3:coding
.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md:3:review
.agenticdoc/mw-worker-tree-kill/workers/smoke-tree-kill-1/task.md:3:coding

=== LASTWINS_DIFFERS ===
.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md frontmatter=coding lastwins=review role coding->review writeless False->True shell True->False

=== FLIP_ROLE ===
.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md coding -> review

=== FLIP_CAPABILITY ===
.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md coding -> review

=== UNREGISTERED_LASTWINS ===
(empty)

=== FENCE_UNCLOSED ===
(empty)

=== NEAR_MISS ===
(empty)

=== FM_TYPE_VALUE_HISTOGRAM ===
coding=198
research=78
review=27
vision=1
```

补充计数（同脚本变体，逐字）：

```
task_md_total=305        # 前缀分布：全部 305 个都在 .agenticdoc/** 下，无 test fixture / 无 worktree 漏扫
files_without_blank_line=0
first_blank_line_index_histogram={1: 249, 2: 44, 3: 11, 4: 1}
files_with_multiple_type_in_header=0
files_where_line1_is_not_type=1
  .agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md first='# Smoke: AC-016 re-run after dist rebuild'
match_count_rg_vs_python: 305 == 305
```

### 1.3 交叉验证（用真实 `parseTaskMd` 复算，非镜像）

命令（dist 是编译产物，只读）：

```powershell
@'
import * as fs from "node:fs"; ... 
import { parseTaskMd } from "file:///H:/git/Multi-Workers/packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js";
// 遍历 305 个 task.md，输出 sorted("rel\ttype") 的 md5
'@ | node --input-type=module -
```

原始输出：

```
node_parseTaskMd_files=305
node_hist={"coding":197,"research":78,"review":28,"default":1,"vision":1}
node_md5=01c517abed3a166c0cffcd1ff728b6d1
spot .agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md -> ...	review
spot .agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md -> ...	default
```

Python 镜像给出 `py_md5_actual(last-wins)=01c517abed3a166c0cffcd1ff728b6d1` ⇒ **镜像与真实解析器在 305 个文件上逐字一致**（md5 相等）。
同一脚本算出 frontmatter-only 预测：`py_md5_frontmatter_only=354d11091b61a17ced8230bbf137aaa8`、`delta_count=1`。

直读 3 个代表文件（行号即原始行号，`|` 后为原文）：

```
.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md
  1|type: coding
  2|
  3|type: review
  4|
  5|# Review: mw-worker-tree-kill ...

.agenticdoc/goal-autopilot/workers/ga-spec-design-review-2/task.md
  1|type: coding
  2|model: gpt-5.6-sol
  3|
  4|type: coding

.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md   (116 bytes)
  1|# Smoke: AC-016 re-run after dist rebuild
  2|
  3|Reply with exactly one line: 'SMOKE-OK-AC016B'
```

### 1.4 「frontmatter 结构不规范（无 `---` 包裹）」单列

- **全部 305 个现存任务书都不带 `---` 包裹**（`fenced_frontmatter_files=0`），即 §1.2 的 249 个「首个空行在第 2 行」= `type:`（+若干头部键）+ 空行 + 正文；44/11/1 个分别是 3/4/5 行头部。判定规则见文首。
- 不规范但有意义的 2 例：
  - `.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md`：**完全没有 `type:`**（首行是 markdown 标题）⇒ `parseTaskMd` 得 `default`（未注册类型），且无 `origin:` ⇒ `dispatchRefusal` 直接放行（`worker-mode.ts:545` 只拦 `origin: conductor`），工具集落到 `fallback`（含 write/edit/bash）。
  - `.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md`：头部 1 行 + 空行 + **再一行 `type: review`**，是本次唯一角色翻转样本（手工书写的「头部 type + 正文 type」形态）。
- fenced 形态虽然语料里是 0，但**生产者会产出**：`autopilot/dispatch.py:347-374`（`lines = ["---", f"type: {task_type}", ...]` … `lines += ["---", "", prompt.strip(), ""]`），测试里也有（`test/suite/autopilot-console.test.ts:278-286` 的 `fencedTask`、`test/suite/mwds-t03-bash-write-scope.test.ts:289`、`test/suite/autopilot-read-scope.test.ts:446/746/803`）⇒ frontmatter-only 必须保留 fenced 分支。

## 2. 派发侧写入面（唯一写入函数 + `type:` 落点）

前 key 记的 `pm/ui-bridge.ts:1266` 在当前工作树已过时；实际行号如下。

**TS/PM 侧（本扩展内的唯一 task.md 创建者）**

| 环节 | 位置 | 说明 |
| --- | --- | --- |
| 头部渲染 | `pm/ui-bridge.ts:1145` | `const headLines = [\`type: ${input.taskType}\`];`，其后追加 `phase:`（`:1146`）、`images:`（`:1147`）；`model:`/`model-reason:` 在 `:1203`/`:1240` |
| 头部组装 | `pm/ui-bridge.ts:1148` `typeLines = headLines.join("\n") + "\n"`；`modelPlan.frontmatter` 即「头部字节」 | 前端不写 `---`（裸头部） |
| 唯一写函数 | `pm/ui-bridge.ts:1539` `export function writeDispatchTaskMd(...)`；内容 = `${frontmatter}\n${body}\n`（`:1563`）；落盘 `:1565` `fs.writeFileSync(taskMdPath, content, "utf8")` | 另经 `mergeWriteScope`（`:1524`）/`mergeAllowForeignWrite`（`:1515`）/`applyWriteSurfaceContract`（`:1504`）顺序改写 |
| 工具入口 body | `pm/ui-bridge.ts:1791` `body: description`（`dispatch_worker`） | 逐字 |
| 命令入口 body | `pm/ui-bridge.ts:2248` `body: description`（`/worker`） | 逐字；description 由 `parts.slice(idx).join(" ")`（`:2161`）拼回，命令行里的 `\n` 早已被 split 掉 |

**结论（`type:` 是否可能落到正文）**：
- `type:` 只在头部生成（`:1145`），并且是本轮 `input.taskType` 的**唯一**写入点；写入函数不再二次解析任务书。
- **但正文 = `description` 无任何转义/白名单**（`:1791`、`:2248`，`writeDispatchTaskMd` 只做字符串拼接 `:1563`）⇒ 描述里出现一行（**任意位置、允许前导空白**）`type: coding` / `  type: coding` / 代码块内的 `type: coding`，都会成为正文 `type:` 行；`parseTaskMd` last-wins 读到的是**最后**一个，而正文永远在头部之后 ⇒ **正文必然压过头部**。
- 注入的写面契约段（`renderWriteSurfaceContract`，`:1481`）不含 `type:` 行，不会额外干扰。

**另有 2 个 task.md 写入者（不是创建者，改动面需知）**
- `pm/task-dispatcher.ts:281` `if (out !== original) fs.writeFileSync(taskPath, out, "utf8")`（`injectWorkspaceProfile`，`:237`）：向**已存在**的 task.md 追加/替换 v2 profile 块与 RAG 块；`type:` 不动，但它渲染 RAG 块时用**自己的**类型解析（`:115-118` `parseRagTaskMeta`，`/^type:[ \t]*(.+?)[ \t]*$/m` = **first-wins、全文**）决定 RAG 要求（`:279` role via `rag/block.ts:67-68`）。
- Python/conductor 生产者：`autopilot/dispatch.py:290 render_task_md`（fenced 头部，`:347-374`）+ `:625 task_md.write_text(...)`。一个 `type:` 由 `task_type` 参数写入头部；conductor 的 prompt 同样逐字进正文。

## 3. 消费者清单与「事实源」现状图

### 3.1 `type:` 解析器（6 份）

| # | 位置 | 算法 | 输入范围 | 谁消费 |
| --- | --- | --- | --- | --- |
| P1 | `worker/worker-mode.ts:308`（`parseTaskMd`，匹配在 `:333-334`，缺省 `:312`，回填 `:454`） | 逐行 `trim().startsWith("type:")`，**last-wins** | **全文**（含正文/代码块/缩进行） | worker 角色与全部运行期守卫 |
| P2 | `pm/task-dispatcher.ts:115`（`parseRagTaskMeta`，正则 `:117`） | `^type:[ \t]*(.+?)[ \t]*$` /m，**first-wins**，行首锚定（允许 0 缩进） | 全文（`base`，去掉 profile/RAG 块后） | RAG 块渲染资格（`:279` → `rag/block.ts:67-68`） |
| P3 | `autopilot/status-model.ts:1243`（`parseTaskLabels`，正则 `:1236`，fence 判定 `:1250`） | 仅当 `lines[0].trim() === "---"`，只读 fence 内，重复键 last-wins | 仅 fenced 头部 | autopilot 控制台 loop/attempt/type 标签（`:1284`） |
| P4 | `packages/multi-workers/launcher.py:143`（`_read_task_md_fields`，正则 `:155`） | `^type:[ \t]*(\S+)[ \t\r]*$` /m，**first-wins**，行首锚定 | 全文 | **spawn 期模型/角色解析**（`:133-137` → `mw_common.py:296 resolve_dispatch_model`）；`:171` 再读一次做 override 日志 |
| P5 | `packages/multi-workers/mw.py:1788`（`_rag_task_meta`，匹配 `:1794`） | 逐行 `line.strip().startswith("type:")`，**first-wins**（`if not task_type`） | 全文 | RAG 审计/报告（`:1879` role 映射） |
| P6 | `test/suite/mwds-t02-write-intent.test.ts:94`（`corpusType`） | `^type:\s*(\S+)\s*$` /m，**first-wins** | 全文 | VC-015 语料回放筛选（`:228`） |

角色映射表另有两份互锁副本：TS `shared/dispatch-models.ts:59-71`（`DISPATCH_ROLE_BY_TYPE`）与 Python `mw_common.py:144-157`（`TASK_TYPE_TO_ROLE`），由 `test_dispatch_models.py:158` 差分锁定。

### 3.2 `parseTaskMd(` 调用点

源码仅 1 处生产调用：

- `worker/worker-mode.ts:1184` `const meta = parseTaskMd(taskPath)`（worker 启动）。

测试调用（只读证据，不修改）：`test/extensions/agent-team-loop.test.ts:3986,3992`；`agent-team-loop-profile-injection.test.ts:125,362`；`test/suite/autopilot-read-scope.test.ts:353,362,367,378,385`；`autopilot-protocol.test.ts:429,439`；`mwds-t03-bash-write-scope.test.ts:290,325`；`mwds-t12-regression.test.ts:132,143,158,171`；`rag-tools.test.ts:393`；`rag-required.test.ts:144-149`；`rag-e2e-slow.test.ts:224`。

### 3.3 `TaskMeta.type` 的下游消费者（全部来自 P1 这一次解析）

- `worker-mode.ts:546` `isRegisteredType(meta.type)`（唯一调用点，函数 `:107`）——**仅当** `meta.origin === "conductor"`（`:545`）才 fail-closed；`verifier` + 空 `read_scope` 也在此拦（`:557`）。调用总入口 `:1222`。
- `worker-mode.ts:1209` `kind: meta.type`（run.json）、`:1292` `appendStart(... meta.type ...)`、`:1335` 启动日志。
- `worker-mode.ts:1386` `role: roleForTaskType(meta.type)`（run 状态）、`:1396` `hasWriteTools = toolsForType(meta.type).includes("write")`（checkpoint 文案分派）、`:1420` `applyRagTools(pi, ragRuntime, meta.type)`（RAG 工具准入）。
- `worker-mode.ts:1468` `isShellRole(meta.type) && isWritelessRole(meta.type)`（bash 写面守卫启用条件）、`:1904` `isWritelessRole(meta.type)`（deliverable/证据分支）、`:1939` `taskType: meta.type`。
- 工具白名单本身：`toolsForType`（`:110`）/ `activeToolsForType`（`:114`）/ `isShellRole`（`:126`）/ `isWritelessRole`（`:133`）。

### 3.4 `roleForTaskType` / `isWritelessRole` / `isShellRole` / `isRegisteredType` 调用点

- `roleForTaskType`（定义 `shared/dispatch-models.ts:78`）：`worker-mode.ts:1154`（dispatch-refusal 文案上下文）、`:1386`；`rag/block.ts:68`；`pm/ui-bridge.ts:1127`（`planDispatchFrontmatter` 里按**入参 type** 选 dispatch.yml role）、`:1816`、`:2262`（回执文案）；测试 `test/extensions/agent-team-loop.test.ts:5568-5603`、`test/suite/rag-research-doc.test.ts:110`。
- `isWritelessRole`（定义 `worker-mode.ts:133`）：`worker-mode.ts:1468`、`:1904`；`pm/ui-bridge.ts:1451`、`:1741`、`:2197`；测试 `test/suite/mwds-t02-write-intent.test.ts:229,466`、`mwds-t03-bash-write-scope.test.ts:164,167`。
- `isShellRole`（定义 `worker-mode.ts:126`）：`worker-mode.ts:1468`；`pm/ui-bridge.ts:1451`、`:1488`（契约段「越界后果」文案）、`:1794`、`:2251`（shell 角色的默认 `write_scope`）；测试 `mwds-t02:229,467`、`mwds-t03:163,170`。
- `isRegisteredType`（定义 `worker-mode.ts:107`）：仅 `worker-mode.ts:546`。**除 conductor 外无任何 fail-closed 入口。**

### 3.5 「谁是事实源、谁在复制判定」

事实源（唯一真正决定运行期权限的）是 **P1 + `TOOL_ALLOWLISTS`/`DISPATCH_ROLE_BY_TYPE`**，在 `worker-mode.ts:1184` 一次性解析后向下分发（§3.3）。其余是**复制判定**：

- **派发期判据（PM，TS）** 与 **运行期判据（worker）分离**，两者之间只有「写头部字符串」这一条隐式契约：
  - PM 判据的输入是**调用参数**：`resolveDispatchType(cli, requested)`（`ui-bridge.ts:1065-1086`，白名单 `DISPATCHABLE_TYPES`，`shared/dispatch-models.ts:73`）→ `typeField`（工具 `:1733`、命令 `:2167`）；随后 `isWritelessRole(typeField)`（`:1741`/`:2197`）→ `judgeWriteIntent({ type: typeField, ... })`（`:1451` 起，`judgeWriteIntent` 定义 `:1444`）→ `planDispatchFrontmatter({ taskType: typeField, ... })`（`:1770`/`:2227`，定义 `:1107`）→ 头部 `type:`（`:1145`）。
  - worker 侧**重新解析写出的文件**（`:1184`），用 last-wins。两侧没有共享的解析函数、没有共享的 `TaskMeta`：`ui-bridge.ts:45` 只 import 了 `isShellRole/isWritelessRole`（能力判定），**没有** import `parseTaskMd`。
  - 因此**「派发期判据是否复用 worker 侧角色解析」= 否**。PM 只在「头部那行 == 当前参数」时与运行期一致；正文多一个 `type:` 立刻分叉（A8 即此）。
- **Python 侧（launcher）又一份独立判定**：`launcher.py:133-137` 用 P4（first-wins）解析 `type:` 去选 dispatch.yml 的 model role。它在语料里已与 worker 分歧 **1 例**：`review-mw-worker-tree-kill`，launcher/角色 = `coding`（取第 1 行），worker 运行期 = `review`（取最后一行）。
- **RAG 判定是第三份**：P2（first-wins）在 `task-dispatcher.ts:279` 决定是否注入/要求 RAG 工具，而 worker 用 P1 的 last-wins 决定 `applyRagTools`（`:1420`）——同一文件两种答案（当前语料 0 例分歧，因为 4 个正文 `type:` 文件里只有 1 个值与头部不同，而该文件未被 RAG 覆盖；属未验证的潜在面，未构造反例）。
- **autopilot 控制台**（P3）只认 fenced 头部，对 PM 产出的裸头部文件恒返回空 Map（`status-model.ts:1250`）——即控制台标签面对 PM 任务书本就失效，与本次改动同向（都往「结构化头部」收敛）。

## 4. frontmatter-only 的影响面

### 4.1 会改变角色的现有任务书：**1 个（不是空集）**

| 任务书 | 头部 | 正文 | 现状（last-wins） | frontmatter-only | 方向 |
| --- | --- | --- | --- | --- | --- |
| `.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md` | `coding`（行 1） | `review`（行 3） | role=review，writeless=true，shell=false，工具 `read/find/grep/ls/worker_file` | role=coding，writeless=false，shell=true，工具 `read/write/edit/bash/find/grep/ls` | **放宽**（write/edit/bash 回归） |

- 证据：`node_md5`/`py_md5` 交叉验证 + `py_hist` 对比（`review 28 → 27`、`coding 197 → 198`），`delta_count=1` 且唯一 delta 即上表文件。
- 另 3 个 `with_body_type_line` 文件（`ga-spec-design-review-2`、`mwppe-quality-gate`、`smoke-tree-kill-1`）正文值与头部/缺省一致 ⇒ 角色不变。
- `smoke-ac016b`（无 `type:`）：last-wins 与 frontmatter-only 都得 `default`（未注册）⇒ 不变（但见 §5 的 fail-closed 建议会**改变它的行为**，需单独决策）。
- 兼容风险要点：这唯一一例的**任务书标题写的是 "Review:"**，但头部 `type:` 是 `coding`（大概率是 `/worker --type` 默认或手抄遗留）。也就是说 frontmatter-only 会让「按标题意图本该只读」的一次 dispatch 变成有写权限——「前端裁剪」修掉了自我提权的 A8，却在存量手工书里放大了权限。历史任务（已终态）无现实风险，但**同型手工书将来仍会出现**，建议同时加「正文出现 `type:` 行 ⇒ trace 告警/拒绝」的可见性（§5）。

### 4.2 会被影响的测试

机器扫描结论（`packages/coding-agent/test/**/*.ts`，匹配 `type:` + 12 个注册类型值）：**157 处命中，全部 fixture 只含一个 `type:` 值**（`lines_with_two_or_more_known_type_values=0`）⇒ first-wins 与 last-wins 在现有 fixture 上**行为等价**，没有测试依赖 last-wins。

真正会被「只认 frontmatter」实现方式影响的是**形态**敏感的 fixture，清单（按风险排序）：

1. `test/suite/worker-run-identity.test.ts:149` — `"origin: conductor\ntype: fallback\n\nwork\n"`：**`type:` 不在第 1 行**。任何「要求第 1 行是 `type:`」的实现会把它读成缺省 `default`（未注册 + conductor ⇒ fail-closed 拒绝），该用例会红。用「首个空行前的头部块」规则则不破。
2. fenced fixture（必须保留 fenced 分支）：`test/suite/autopilot-console.test.ts:278-286`（`fencedTask`）、`:558`（`---\norigin: conductor\nloop: ...\n---`，**fence 内无 type**）、`test/suite/mwds-t03-bash-write-scope.test.ts:289`、`test/suite/autopilot-read-scope.test.ts:446,746,803`、`test/suite/dual-root-worker.test.ts:75`、`cross-drive-worker.test.ts:154`、`autopilot-protocol.test.ts:467`。
3. 裸头部里含裸 `---` 行的 fixture：`test/suite/autopilot-read-scope.test.ts:378` `"type: verifier\nread_scope:\n---\n\nwork\n"`（unfenced 且头部有 `---`）——「只要出现 `---` 就当 fence」的错误实现会误判边界；本报告规则（首行才判 fence）不受影响，`type` 仍为 `verifier`。
4. 语料回放测试：`test/suite/mwds-t02-write-intent.test.ts:224-263`（VC-015）用**P6 first-wins** 筛 `.agenticdoc` 真语料。当前语料下 frontmatter-only 与 P6 结果**完全一致**（唯一 delta 文件 `review-mw-worker-tree-kill`：P6=coding=frontmatter-only），所以 `books.length >= 24` / `truePositive=1` 断言不会变；但该测试的 `corpusType` 是第 6 份独立解析器，若本次改造引入共享函数，理应让它改用共享函数（否则留下另一处漂移）。
5. 明确**不受影响**（首行 `type:`、无重复值）：`test/extensions/agent-team-loop.test.ts:3985-3992`（重复 `timeout:` 用例，非 type）、`test/suite/rag-required.test.ts:143-149`、`rag-tools.test.ts:391`、`mwds-t12-regression.test.ts:111,170`、`agent-team-loop-image-cap.test.ts:123/161/175/189`、`agent-team-loop-output.test.ts:139`、`run-store.test.ts:168-216`、`worker-dispatch-guard.test.ts:61/415`、`worker-idle-heartbeat.test.ts:84`、`rag-e2e-slow.test.ts:171` 等。
6. Python 侧无 `parseTaskMd` 依赖；`test_rag_audit.py:150`、`test_autopilot_attribution.py:271` 构造的是 fenced/单行 `type:`，与新规则无冲突（未逐条运行验证 —— 依纪律未跑测试）。

## 5. 兜底建议（fail-closed 规则）与存量兼容风险

### 5.1 统一事实源（前置条件）

1. 抽一个共享的「头部区提取器」（建议放 `shared/`，worker 与 PM、task-dispatcher 共用），算法固定为：
   1. 剥 BOM；按 `\r?\n` 切行。
   2. 若 `lines[0].trim() === "---"`：头部区 = 第 1 个闭合 `---` 之前的行；**找不到闭合 `---` 时按 unfenced 分支处理**（不要静默返回空）。
   3. 否则头部区 = **首个空行之前的连续行**（与 `ui-bridge.ts:1507` 的 `\n\s*\n` 锚点同义）。
   4. 若**没有空行**（今日 0 例）：头部区终止于第一个不匹配「头部键文法」的行，文法 = `^[A-Za-z_][A-Za-z0-9_-]*:`（可复用 `status-model.ts:1236` 的 `TASK_FM_LINE_RE`）或缩进块项 `^\s+- `；绝不把整个文件当头部。
2. 单一 `type:` 解析器：只在头部区内找，**首个命中胜出**（写侧保证只写一行：`ui-bridge.ts:1145`、`dispatch.py:347`）；命中值做 `trim()`（顺带吃掉 `\r`），**不**做大小写归一。`parseTaskMd`（P1）改用它；`task-dispatcher.ts:117`（P2）、`launcher.py:155`（P4）、`mw.py:1794`（P5）、`status-model.ts:1243`（P3，fenced-only 保持）、测试 `corpusType`（P6）全部改为调用它或显式声明为「有意不同的 legacy reader」。
3. 建议**同一提取器也复用到其余头部键**（`phase/timeout/origin/images/read_scope/deny_globs/write_scope/l2_*`，`:336-421`）——它们与 `type:` 是同一种漏洞（正文可注入 `origin: conductor`、`write_scope:`、`timeout:`）。**注意**：这一步会额外改变 1 个存量文件的 `timeout`（见 §5.4）。若本轮只想堵 `type:`，就把提取器**只**用于 `type:`，并把差异写进 change note。

### 5.2 fail-closed 判定矩阵（建议）

| 情况 | 现状 | 建议 | 理由 |
| --- | --- | --- | --- |
| 头部区有 `type:`，值**非法**（不在 `TOOL_ALLOWLISTS`，含 `fallback`/`default`/空串） | 仅 `origin: conductor` 拒绝（`worker-mode.ts:545-556`，`isRegisteredType` `:107` 排除 `fallback`）；无 origin 时落 `fallback` = 全工具集 | **所有 origin 一律拒绝**（把 `isRegisteredType` 检查从 `origin` 门后移到门内全局），拒绝文案复用 `:552` 的已注册类型清单 | 与 D-107 的既有语义一致，只是拆掉 `origin` 这个可被正文 `origin: conductor` 反向利用的前置条件；无 origin 时「未知类型 = 全权限」是当前的隐藏升权面 |
| 头部区**没有** `type:`（含 `smoke-ac016b` 这种整篇无 `type:`） | 默认 `"default"`（`:312`）→ 未注册 → 无 origin 时放行、`fallback` 全工具集 | 两选一：(a) 严格：一律拒绝（写侧两处生产者都恒写 `type:`，能走到这里的只有手工书）；(b) 保守：保留 `fallback`，但在 `trace.log`/`worker.log` 写一条 `[HEADER] type missing -> fallback` 强制审计行。**建议 (a) + 显式迁移提示**，因为它与上一条合并后规则单值化 | 上一条把「未注册一律拒绝」立起来后，(b) 会留下「缺失 ≠ 非法」的第二种放行路径，等于把同一个洞换个形状留着 |
| **无 `---`**（unfenced） | 305/305 都是这个形态 | **不是错误**，按 §5.1 的首个空行规则接受；仅当「无空行」时才退化到头部键文法 | 存量全靠它，且 `applyWriteSurfaceContract`（`:1504-1512`）本来就用首个空行当锚点 |
| 头部区出现**多个** `type:` | last-wins（现状，可被正文利用）；语料 0 例 | first-wins + 拒绝（或至少强制 trace 告警）；写侧恒写一行，出现重复只可能是手工编辑 | 消除歧义；重复值是「守卫可自我失效」的检测信号，值得直接拦 |
| 头部区无 `type:`、但**正文**有 `type:` 行 | 正文静默胜出（A8） | 建议**显式拒绝**（正文值 != 头部值时），或至少每次启动写一条 `[HEADER] body type: ignored` 审计行；配合 §4.1 那 1 个存量文件的历史事实 | 这是 A8 的唯一触发路径；拒绝能让「护栏被审文本改写」从静默变成可观测，且今日语料中该拒绝只会命中 1 个已终态的历史书 |
| `type:` 值带大小写/空白差异 | `trim()` 后精确匹配（`:334`） | 保持精确匹配，不做 case-fold | 与 Python 侧 `TASK_TYPE_TO_ROLE` 精确键、`isRegisteredType` 精确键一致；case-fold 会造出第二套键空间 |

### 5.3 与 `isRegisteredType` / `DISPATCHABLE_TYPES` 的关系

- 运行期：`isRegisteredType`（`worker-mode.ts:107`）已经把 `fallback` 从「已注册」里排除，这是正确的 fail-closed 锚点；本建议只是把它的门从 `origin === "conductor"`（`:545`）扩大到全体。
- 派发期：`resolveDispatchType`（`ui-bridge.ts:1065-1086`）已经对**参数**做白名单拒绝（`DISPATCHABLE_TYPES`，`shared/dispatch-models.ts:73`）；改动后派发期与运行期共用同一个「已注册类型」集合（`TOOL_ALLOWLISTS` 键集 ⊇ `DISPATCHABLE_TYPES`，`:71-104` vs `dispatch-models.ts:73`），需要把 `rag-research`/`vision`/`verifier` 等非 `DISPATCHABLE_TYPES` 但已注册的键区分清楚：**建议运行期白名单 = `TOOL_ALLOWLISTS` 的键（排除 `fallback`），而不是 `DISPATCHABLE_TYPES`**，否则 conductor 的 `phase-writer`/`repair`/`verifier` 会被误杀（`test/suite/autopilot-protocol.test.ts:346-350` 的 `PY_*_TOOLS` 对照已锁定这组类型必须可运行）。

### 5.4 存量兼容风险（量化）

1. **角色翻转 1 例**（§4.1）：`review-mw-worker-tree-kill` 由 review → coding = **权限放宽**；该 key 已是历史任务（`review-mw-worker-tree-kill` 与同 key 其它书均已终态），现实风险低，但必须在 change note 里点名，并靠 §5.2 的「正文 `type:` 审计/拒绝」让新书可见。
2. **`type:` 缺失 1 例**（`smoke-ac016b`）：严格 fail-closed 后该任务书会被拒绝执行（当前会以 `fallback` 全工具集运行）。它是 smoke 书且已终态，代价可接受。
3. **若提取器同时覆盖所有头部键：`timeout` 变 1 例**。机器计数（同规则）：正文区出现 `timeout:` 的文件 = 1，即 `.agenticdoc/mw-worker-tree-kill/workers/smoke-tree-kill-1/task.md:4:timeout: 2`（该书形态为 `type: coding` / 空行 / `type: coding` / `timeout: 2`）。按「首个空行前 = 头部」规则该行会从头部掉出，墙钟预算由 2m 变回默认（60m）。其余头部键（`phase`/`origin`/`images`/`write_scope`/`l2_*`/`rag_*`/`supersedes`/`allow_foreign_write`）在语料正文区出现次数 = **0**。→ 建议：要么接受这 1 例（并把该 smoke 书视为过期），要么本轮只把提取器用于 `type:`。
4. **跨侧分歧归零（收益）**：改造后 worker（P1）与 launcher（P4，first-wins）在现存 305 本上的 `type:` 完全一致（md5 层面：`py_md5_frontmatter_only=354d11091b61a17ced8230bbf137aaa8` 对应 launcher 视角），实测分歧的 1 例消失。RAG 判定（P2）同理对齐。
5. **测试兼容**：无 fixture 含两个 `type:` 值（0/157 命中），所以 first-wins 本身零测试回归；风险集中在形态判断（见 §4.2 第 1/3 条），用「首个空行 + 首行才判 fence」的规则可全部保持。未运行任何测试（遵守纪律），以上为静态推断。

## 附：证据与复现方式（全部只读）

- 枚举：`rg -uu --no-ignore --files -g "task.md" H:\git\Multi-Workers`（=305）与 `os.walk`（=305）一致；全部落在 `.agenticdoc/**`。
- 计数：Python 经 stdin 执行（无临时文件），镜像 `TOOL_ALLOWLISTS`/`DISPATCH_ROLE_BY_TYPE`/`activeToolsForType`；输出见 §1.2。
- 交叉验证：`node --input-type=module -` 直接 import `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` 的真实 `parseTaskMd`，对 305 个文件算出 `node_md5=01c517abed3a166c0cffcd1ff728b6d1`，与 Python 镜像 `py_md5_actual=01c517abed3a166c0cffcd1ff728b6d1` **相等** ⇒ §1 的数字不是「我以为的解析」，而是真实解析器的行为。
- 测试扫描：正则 `type:[ \t]*(coding|review|research|verifier|reviewer|vision|rag-research|phase-writer|roadmap-writer|repair|fallback|default)\b` 扫 `packages/coding-agent/test/**/*.ts`，157 处命中，`lines_with_two_or_more_known_type_values=0`。
- 未验证项（明确标注）：(a) §3.5 中「P2 与 P1 在 RAG 判定上存在潜在分歧」未构造反例，仅指出现状（同一文件两套解析）；(b) §4.2 第 6 条的 Python 测试影响未逐条运行；(c) 未运行 vitest / `npm run check` / build（按纪律由 PM 执行）。

## 勘误（行号复核）

交付前对全文行号做了二次 grep 复核。以下 7 处引用行号需以本表为准（其余引用已复核一致）：

| 出现位置（本报告行） | 原文写的 | 正确 |
| --- | --- | --- |
| §1 判定规则「角色/能力用源码镜像」 | `worker-mode.ts:71-104`（`TOOL_ALLOWLISTS`） | `worker-mode.ts:68-102` |
| 同上 | `shared/dispatch-models.ts:59-71`（`DISPATCH_ROLE_BY_TYPE`） | `shared/dispatch-models.ts:58-69` |
| 同上 | `worker-mode.ts:114-135`（`activeToolsForType`/`isShellRole`/`isWritelessRole`） | `worker-mode.ts:120-135`（`isShellRole`=126、`isWritelessRole`=133 不变） |
| §3.1 表后「角色映射表另有两份互锁副本」 | `shared/dispatch-models.ts:59-71` | `:58-69` |
| §3.3 末行「工具白名单本身」 | `toolsForType`（`:110`）/ `activeToolsForType`（`:114`） | `toolsForType` = `:111`；`activeToolsForType` = `:120` |
| §3.5 / §5.3 `DISPATCHABLE_TYPES` | `shared/dispatch-models.ts:73` | `:75` |
| §5.1 第 3 点 头部键行号范围 | `:336-421` | `:336-428`（含 `RAG_CHAT_BUDGET_HEADER` `:422`、`RAG_TIME_BUDGET_HEADER` `:426`） |
| §5.3 「`TOOL_ALLOWLISTS` 键集 … `:71-104`」 | `:71-104` | `:68-102` |
| §2 命令入口 body 说明 | `parts.slice(idx).join(" ")`（`:2161`） | `:2149` |

其余关键行号已逐一 grep 复核一致：`worker-mode.ts:107/126/133/312/333-334/336/340/344/347/352/366/386/414/418/454/544-557/1184/1209/1222/1292/1335/1386/1396/1420/1468/1154/1904/1939`；`ui-bridge.ts:1065/1107/1127/1145-1148/1203/1240/1444/1451/1463/1476/1481/1488/1504/1507/1515/1524/1539/1563/1565/1733/1741/1791/1794/1816/2167/2197/2248/2251/2262`；`task-dispatcher.ts:115/117/237/279/281/284`；`status-model.ts:1236/1243/1250/1284`；`dispatch.py:290/347-374/625`；`launcher.py:133/143/155/171`；`mw.py:1788/1794/1879`；`mw_common.py:144-157/296/315`；`dispatch-models.ts:58-69/75/78`。
