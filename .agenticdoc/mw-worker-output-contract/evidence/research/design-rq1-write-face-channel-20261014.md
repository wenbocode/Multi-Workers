# T-DR1 设计研究：worker_file 写面放宽 + 派发期/运行期写面同源

- Key: `mw-worker-output-contract`；任务卡 `.agenticdoc/mw-worker-output-contract/tasks/T-DR1-write-face-channel.md`；worker `woc-dr1-write-face-channel`（type: research，只读）
- 唯一证据文件：`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq1-write-face-channel-20261014.md`（本文件；任务目录 `report.md` 同字节）
- 上游清单（已确证，直接作设计前提）：`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq2-write-face-20261014.md` §4（A1-A16 / B1-B6 / C1-C11 / D1）
- 方法边界：**纯静态**。读源码/测试全文 + `git grep`/`Select-String` 计数 + 只读 fs 遍历；**未实现任何改动、未跑任何测试套件、未重建 dist、未跑真实 provider**。所有 `文件:行号` 为**当前工作树**（`git grep -n` 口径）。
- 交付格式：本卡点名的三段（`## 0. 结论与决策表` / `## 1…N` 逐问 / `## 未覆盖面声明`）与本 key 强制的 4 段标题合并如下：`## 结论` 内含 `### 0. 决策表`；`## 证据` 内含 `### §1 … §11` 与 `### 未覆盖面声明`；另两段为 `## 残留与未验证` / `## 上下文来源`。

## 结论

1. **可以放宽，但只能靠「一个纯谓词 + 一个纯模块」放宽，绝不能靠放宽 `WORKER_FILE_NAME_RE`**：该正则今天被 `shared/deliverable-evidence.ts` 的 **basename** 判定（`readdirSync` 结果）与 `pm/ui-bridge.ts` 的 **basename 通道**（`!hasDirComponent` 前置）共用（`grep` 实测 3 个 importer，见 §1.3）；让它接受路径会同时打掉这两处的目录盲区防线。设计：新增纯模块 `shared/write-surface.ts`，把「deny 表 + 路径域判定 + basename 白名单」收成一份，`worker-file-tool.ts`（运行期通道）、`worker-mode.ts::checkBashWriteScopeTarget`（bash 守卫）、`pm/ui-bridge.ts::judgeWriteTarget`（派发期判定）全部退化为它的薄适配层。A1-A16 结果为 **12 项采纳/改写、2 项保留（A1 迁址、A7）、1 项否决（A13）、1 项改写取最小支（A16）**。
2. **路径域语义定死为「两个基准、一个物理面、先归一化再判定」**：`evidence/**`（key 相对）与 `.agenticdoc/<key>/evidence/**`（project-root 相对）是**同一物理目标的别名**，基准只有这两个且顺序固定；判定顺序 = 形状前置 → 归一化 → deny 表（6 条，绝对优先）→ taskDir 面（basename 白名单**只在 token 无目录成分时**开）→ evidence 面 → `write_scope` 收窄 → 拒。evidence 面限 `.md`、段字符集 `[A-Za-z0-9._-]+`、**深度不限**（实测 `.agenticdoc/**/evidence/**` 共 547 文件、非字符集名称 0、最深 9 段，见 §2.4）。fail-closed **只用一条规则**：归一化后不在面内即拒（与壳层逐字同构），不另立「含 `..` 即拒」的第二套规则（§10-8 说明为什么否决 RQ-2 A2 的该条建议）。
3. **AC-007 的「文案」层级判定为：模型可见文本不可改**，因此验收走 AC 的 (a) 支「该错误不再产生」，配套扩展可改面的三处**事前指引**（卡面契约段 / `worker_file` description+promptGuidelines / `writeIntentRefusal` 的 Fix 清单）；PM 可见的 `[TOOL_ERR]` 行只做「可判读」（带 `rule=`），不声称改了模型可见文本。

### 0. 结论与决策表

| 项 | 符号（当前工作树坐标） | 决策 | 一句话语义 |
|---|---|---|---|
| A1 | `worker-file-tool.ts:42` `WORKER_FILE_NAME_RE` | 保留（迁址 + 再导出） | basename-only 语义逐字不变；定义移到 `shared/write-surface.ts`，原文件再导出 |
| A2 | `worker-file-tool.ts:48` `isAllowedWorkerFile` | 改写 | 保留 basename 判定；新增**唯一谓词** `judgeWorkerWriteTarget(ctx, token, {bareBase})` |
| A3 | `worker-file-tool.ts:56` `writeWorkerFile` | 改写 | 签名 `(ctx: WorkerFileWriteCtx, file, content, mode)`；ctx 必需（缺 keyDir 即 fail-closed） |
| A4 | `worker-file-tool.ts:62-64` 拒绝原因 | 改写 | 两类原因可辨：`file name not allowed:` 保留；越界用 `outside the worker write surface: <json> [rule=<deny|scope|write-scope>]` |
| A5 | `worker-file-tool.ts:72` `mkdirSync` | 改写 | mkdir 目标改为 `path.dirname(target)`（evidence 子目录才能创建） |
| A6 | `worker-file-tool.ts:73` `path.join(taskDir, file)` | 改写 | 用解析器给出的绝对 `target` |
| A7 | `worker-file-tool.ts:82` `appendWriteFileEvent` | 保留 | trace 仍写 `<taskDir>/trace.log`，事件路径为 repo 相对（evidence 写即 `.agenticdoc/<key>/evidence/...`） |
| A8 | `worker-file-tool.ts:87` `registerWorkerFileTool` | 改写 | 第二参从 `taskDir: string` 改为 `ctx: WorkerFileWriteCtx`；调用点 `worker-mode.ts:2133` 同步 |
| A9 | `worker-file-tool.ts:91-95` description | 改写 | 同时说明任务目录 basename 与 `<key>/evidence/**` 两个域 |
| A10 | `worker-file-tool.ts:96-100` promptGuidelines | 改写 | 去掉「basename only」的写死表述，给出 evidence 形式示例 |
| A11 | `worker-file-tool.ts:103-106` schema `pattern` | 改写 | 改为合并前置过滤 `WORKER_FILE_PATH_RE.source`；导出 `WORKER_FILE_BASENAME_ALT` 供单源断言 |
| A12 | `worker-mode.ts:2131-2134` 注册处 | 改写 | 现场拼 `ctx`：`projectRoot=process.cwd()`、`taskDir=workerTaskDir`、`keyDir=path.dirname(meta.agenticdocRoot)`、`trueRoot=meta.trueAgenticdocRoot`、`writeScope=meta.writeScope` |
| A13 | `worker-mode.ts:260-262` `READ_TOOLS`/`WRITE_TOOLS` | **否决**（不改） | 不把 `worker_file` 放进 `WRITE_TOOLS`；writeless 收敛判据（AC-009）改读账本事件，见 §5-A13 |
| A14 | `worker-mode.ts:1568` + `ui-bridge.ts:1673` 两份 deny 表 | 采纳（合并） | 抽 `writeDenyReason(ctx, absTarget)` 到 `shared/write-surface.ts`，两处变一行委托 |
| A15 | `worker-mode.ts:1648-1661` + `:1584-1599` | 采纳（**是**） | `write_scope:` 同样约束 `worker_file`（复用 `matchesWriteScopeEntry`） |
| A16 | `worker-mode.ts:2390` + `output-writer.ts:440-446` | 改写（取最小支） | 只落既有 `[TOOL_ERR] worker_file <reason>`，reason 带 `rule=`；**不新增** `[WRITE_SCOPE]` 风格行 |
| B1 | `ui-bridge.ts::judgeWriteTarget` | 采纳 | 在 taskDir 分支后加 evidence 分支，实现为共享谓词的一次调用 |
| B2 | `ui-bridge.ts:1564` `PmWriteSurfaceCtx` | 采纳（无需改字段） | `keyDir` 已在；确认两处派发调用已传 `keyDir`/`trueRoot`（§4.2 实测） |
| B3 | `ui-bridge.ts::writeIntentRefusal` | 采纳 | Fix 第 1 条加入 evidence 形式 |
| B4 | `ui-bridge.ts:2432` / `:2926` scope 渲染条件 | **否决**（不改） | 非 shell 的 writeless 角色不渲染 `write_scope:`（理由 §6-B4） |
| B5 | `ui-bridge.ts::renderWriteSurfaceContract` | 采纳 | 「允许写」加入 evidence 面；「不得写」明确「其他 key 的 evidence 仍禁」 |
| B6 | `ui-bridge.ts::judgeWriteTarget` 头部顺序注释 | 采纳 | 顺序文档随 B1 同步；**不得写行号** |
| C1-C11 | 测试 11 处 | 10 采纳 / C3 C6 改写 | 见 §6-C 与 §7-§9 |
| D1 | `packages/multi-workers/dist/extensions/agent-team-loop.js` | 采纳（实现期） | 改源后必须重建 dist（本任务不做） |

## 证据

### §1 现状坐标与漂移（符号锚定）

**1.1 行号漂移与锚定口径（要求 4 的前置）**

- `git diff --quiet HEAD` 实测：`worker/worker-file-tool.ts` clean、`worker/worker-mode.ts` clean、`worker/read-scope.ts` clean、`shared/deliverable-evidence.ts` clean；**`pm/ui-bridge.ts` 不 clean**（`git diff --stat` = `3 insertions(+), 1 deletion(-)`，改动点 `setWatchWidget` 的 `ctx.ui.setWidget(..., { placement: "belowEditor", order: 10 })`，净 +2 行，位于 `judgeWriteTarget` **之前**）⇒ B1-B6 的一切引用必须以**符号名**定位，行号只能作参考。
- 顺带实测（本 key 之外，但会咬到 design 阶段）：`test/extensions/agent-team-loop.test.ts:6253` 的锚表测试只扫 `[".agenticdoc/mw-guard-form-hardening/spec.md", ".agenticdoc/mw-guard-form-hardening/design.md"]`，其 `EXPECTED` 表用**行号**锁 ui-bridge（`:6297 "pm/ui-bridge.ts:1645": /export function judgeWriteTarget/`、`:6298 "…:1664": /export function isWhitelistedWriteTarget/`）；当前工作树 `ui-bridge.ts:1645` = `if (t === "" || !/[A-Za-z0-9]/.test(t)) return "punct";`、`:1664` = deny 表注释、`:1726` = `export function isWhitelistedWriteTarget` ⇒ **相对当前工作树已失配**（与并行的 `setWatchWidget` 改动叠加）。`design.md` L10/L11 确实引用了 `:1664`/`:1679`，故该锚表测试的 `content_mismatch` 面在今天的树上非空（**静态断定，未实跑**）。结论：本 key 的 design.md 若要写 `文件:行号`，必须在实现完成当刻重取，且优先写成 `文件::符号名`。

**1.2 判定链的三处入口（唯一真源要覆盖的面）**

```
运行期通道  worker-file-tool.ts::writeWorkerFile        (worker-file-tool.ts:56-84)
运行期壳层  worker-mode.ts::checkBashWriteScopeTarget     (worker-mode.ts:1606-1664)
派发期      pm/ui-bridge.ts::judgeWriteTarget             (ui-bridge.ts:1707-1722)
```

三处的共同输入是「一个 token + 一组基准目录」，输出是「allowed / rule」。差异只在两处：(i) 壳层有 `verbatim=false → allow-unknown` 这一档（`worker-mode.ts:1613-1621`），派发期与 worker_file 没有；(ii) **裸 token（无目录成分）的基准不同**：worker_file 落 `<taskDir>/<token>`，壳层落 `cwd/<token>`＝`<projectRoot>/<token>`，派发期把裸 token 交给自己的 basename 通道（`ui-bridge.ts:1715`）。这正是今天「同一路径两处判定相反」的结构原因，也是共享谓词必须显式参数化的地方。

**1.3 `WORKER_FILE_NAME_RE` 的三个 importer（要求 3 的事实面）**

```
$ git grep -n "WORKER_FILE_NAME_RE" -- packages/coding-agent/src packages/multi-workers
pm/ui-bridge.ts:65                import { WORKER_FILE_NAME_RE } from "../worker/worker-file-tool.ts";
pm/ui-bridge.ts:1715              if (!hasDirComponent && (WORKER_FILE_NAME_RE.test(pathToken) || FRAMEWORK_TASK_BASENAMES.includes(pathToken))) {
shared/deliverable-evidence.ts:43 import { WORKER_FILE_NAME_RE } from "../worker/worker-file-tool.ts";
shared/deliverable-evidence.ts:113 if (name === "progress.md" || !WORKER_FILE_NAME_RE.test(name)) continue;
worker/worker-file-tool.ts:42     export const WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;
worker/worker-file-tool.ts:49     return WORKER_FILE_NAME_RE.test(name);
worker/worker-file-tool.ts:104    pattern: WORKER_FILE_NAME_RE.source,
packages/multi-workers/dist/extensions/agent-team-loop.js: {16823,16825,16860,16922,22795}  (打包副本 5 处)
```

外加测试侧 2 处 import（`test/extensions/agent-team-loop-worker-file-tool.test.ts`、`test/suite/mwds-t02-write-intent.test.ts:55`）。`deliverable-evidence.ts:113` 的入参来自 `fs.readdirSync(taskDir)` ⇒ 是**纯 basename**；`ui-bridge.ts:1715` 的 `!hasDirComponent` 前置是 load-bearing（注释原文：``The `!hasDirComponent` precondition (not `shape === "bare"`) is load-bearing: `output.md`/`report.md` are `ext`-shaped and must still use the channel.``）⇒ **放宽这个正则 = 同时给这两处开目录盲区**，这是 A1「保留」的硬理由。

**1.4 运行期注册与 ctx 的可得性**

```
worker-mode.ts:2131  const hasWriteTools = toolsForType(meta.type).includes("write");
worker-mode.ts:2133  registerWorkerFileTool(pi, workerTaskDir);
worker-mode.ts:2327  const pendingWriteTargets = new Map<string, string>();
worker-mode.ts:2390  appendToolError(meta.taskKey, meta.agenticdocRoot, event.toolName, toolErrorText(event.result));
```
`meta`（`TaskMeta`）在 :2131 处可用，含 `agenticdocRoot`（= owner 的 `workers/` dir）与 `trueAgenticdocRoot`（= `.agenticdoc`）、`writeScope`；`keyDir = path.dirname(meta.agenticdocRoot)` 与壳层 config 的 `:2207 keyDir: path.dirname(meta.agenticdocRoot)` 同式 ⇒ A12 的 ctx 拼装**零新派生**。

### §2 路径域语义（要求 2）

**2.1 `<key>` 是相对 project-root 还是相对 key 目录 —— 裁决：两个基准都接受，但「物理面」只有一个**

- 物理面恒为 `<keyDir>/evidence/**`（`keyDir = <projectRoot>/.agenticdoc/<key>`），与壳层 `evidenceDir = path.join(config.keyDir, "evidence")`（`worker-mode.ts:1623`）逐字相同。
- 两个**基准**（token → 绝对目标的解析起点）：
  - (a) `projectRoot` 基准：`.agenticdoc/<key>/evidence/research/x.md`。这是 `renderDefaultWriteScope` 的输出形状（`ui-bridge.ts::renderDefaultWriteScope` = `write_scope: .agenticdoc/${ownerKey}/workers/${taskKey}, .agenticdoc/${ownerKey}/evidence`），也是壳层 bash 的唯一基准（shell cwd = project root）。
  - (b) `keyDir` 基准：`evidence/research/x.md`。这是历史 review 卡在 `## 唯一证据文件` 里的写法（P2 证实的 `mwg-qg-review-20261010` / `wjg-qg-evidence-closure` 形态），也是 AC-016 点名的 `evidence/**` 形式。
- 顺序固定：先 (a) 后 (b)；两者只在 token 首段是 `evidence` 时才可能给出不同命中，且 (b) 只在 (a) 未命中时尝试 ⇒ 不产生影子写面（不会出现「同一个字符串能写到两个地方」）。
- **为什么必须收 (b)**：AC-016 要求「review 卡声明 `evidence/**` 时派发期判定为可满足」，而派发期可满足必须意味着运行期**真的能写**（否则就是把不可满足的订单放行）。若只收 (a)，卡里的 `evidence/x.md` 依然写不成 ⇒ AC-006 的端到端（worker 照卡调用 `worker_file`）失败。两个 AC 只有在收 (b) 时才自洽。
- **已知例外（必须显式记进用例，不许后来「顺手修」）**：壳层的 bash 通道**不**收 (b)。shell 的 `evidence/x.md` 由 shell 按 cwd 解析为 `<projectRoot>/evidence/x.md`，若把它也解释成 key 相对，就是**对 shell 撒谎**。其后果是 fail-closed（bash 拒、worker_file 收），唯一受影响角色是 `research`（唯一的 shell+writeless），且它仍有可用通道。

**2.2 evidence 面的形状限制**

- 深度：**不限**（`evidence/<a>/<b>/…/x.md`）。实测依据见 §2.4。
- 段字符集：`[A-Za-z0-9._-]+`，且每段不得等于 `.` 或 `..`。
- 扩展名：必须以 `.md` 结尾（大小写不敏感）。
- 目录本体拒：`evidence`、`evidence/`、`evidence/research`（无文件段）一律拒。
- 理由（不是「推测」）：(a) `deliverable-evidence.ts` 的 `EVIDENCE_REF_RE = /evidence[\\/]([A-Za-z0-9._\-\\/]+?\.md)/g` 只认 `.md` ⇒ 非 `.md` 写进 evidence 对 PM 的产物判定不可见，等于制造「写了但看不见」的假象；(b) spec §4 R3 明写「`evidence/` 只放产物」；(c) 段字符集收窄把 `..` 在 **schema 层**就挡住（纵深），而权威判定仍在谓词层。
- 非 `.md` 产物的出路（写进文档，避免制造假不可满足）：`research` 等 shell 角色继续用 bash 通道写 `.txt/.py/.log`（壳层允许面已含 `<key>/evidence/**`，t03 已锁）。

**2.3 `../..`、其他 key、仓库源码的 fail-closed 判据（唯一规则）**

```
judge(token):
  abs = normalizeForCompare(projectRoot, token)          // read-scope.ts:100：path.resolve + 最深存在祖先 realpath
  if denyReason(ctx, abs) !== null               -> {allowed:false, rule:"deny"}
  if bareBase==="task-dir" && token 无目录成分   -> target = join(taskDir, token);
                                                    如果 !WORKER_FILE_NAME_RE.test(token) -> {allowed:false, rule:"scope"}
                                                    否则 -> {allowed:true, domain:"task-dir", target}
  if token 有目录成分:
        if isSameOrUnder(taskDir, abs)             -> 拒（rule:"scope"）      // 目录盲区防线不因放宽而消失
        else 对 base ∈ [projectRoot, keyDir] 依次：absBase = normalizeForCompare(base, token);
              if isSameOrUnder(evidenceDir, absBase) && endsWithMd(absBase) && 段合法 -> {allowed:true, domain:"evidence", target:absBase}
  if ctx.writeScope !== undefined && !some(matchesWriteScopeEntry(ctx, e, target)) -> {allowed:false, rule:"write-scope"}
  否则 -> {allowed:false, rule:"scope"}
```

- 绝对/UNC/盘符（`/etc/x.md`、`C:\abs\x.md`、`\\unc\share\x.md`）：`normalizeForCompare(projectRoot, token)` 不会落在 `<keyDir>/evidence` 内（盘符/UNC 解析到别的卷）⇒ `rule=scope` 拒。
- 其他 key：`.agenticdoc/other-key/evidence/x.md` ⇒ deny 表第 5 条（`isSameOrUnder(trueRoot, target) && !isSameOrUnder(keyDir, target)` → `other key dir / .agenticdoc root`）。注意顺序：deny 先于 evidence 面，故 (b) 基准不会救它。
- 仓库源码：`packages/**`（deny 第 5 条）、`.git/**`（deny 第 6 条）。
- 框架禁写：`pm-state.md`（第 1 条）、`workers/_workers*`（第 2 条）、`_index.parallel`（第 3 条）。
- key 内 evidence 之外：`.agenticdoc/<key>/design.md`、`.agenticdoc/<key>/workers/<other>/report.md` ⇒ 非 evidence、非 taskDir ⇒ `rule=scope`。
- `evidence/..` ⇒ 归一为 `<keyDir>` ⇒ `rule=scope`；`evidence/../../x.md` ⇒ 归一后落在 `.agenticdoc/` 或更外 ⇒ 非 evidence（若落到其他 key 则先被 deny 第 5 条吃）⇒ 拒。
- **不再另立「token 含 `..` 一律先拒」规则**（RQ-2 A2 的建议，本设计否决）：`normalizeForCompare` 已做词法 collapse + 最深存在祖先 realpath，凡归一后落在面内的都是同一物理文件，另立规则只会让同一字符串在两通道得到不同结论，直接违背 AC-016 的「同源」目标。反向对照仍覆盖：「越界型的 `..`」全部拒（§11 矩阵 5/6 行）。

**2.4 `write_scope:` 是否约束 `worker_file`（AC-006 开放项 2 / A15）—— 裁决：约束**

- 理由 1（spec 意图）：§2.3 安全约束是「写面放宽**只到** `<key>/evidence/`」；若 `write_scope:` 只约束 bash，则宽松通道成为收窄声明的旁路，声明形同虚设。
- 理由 2（同源）：AC-016 要的是「两处判定共用同一谓词」，谓词里带不加 `write_scope` 等于两套语义。
- 后果（必须写进文档，避免实现期当成 bug）：`write_scope:` 收窄对 **taskDir 面同样生效**（与壳层一致）。今天框架渲染的唯一声明 `renderDefaultWriteScope` 恰好 = 默认面（`taskDir + <key>/evidence`），所以**今天零行为变化**；只有当 PM 手写更窄的 `write_scope:` 时才可能连 `progress.md` 一起挡掉——这是 fail-closed 的正确方向。

**2.5 实测（计数）**

```
$ (Get-ChildItem -Recurse -Path .agenticdoc -File | Where-Object { $_.FullName -match '\\evidence\\' }).Count
547
$ <同上> | Where-Object { $_.Name -notmatch '^[A-Za-z0-9._-]+$' } | Measure
0                              # 547/547 basename 落在建议字符集内 ⇒ 字符集收窄不会误伤仓内既有命名
扩展名分布: .md=397 .txt=63 .py=41 .log=23 .ps1=7 .json=4 .parallel=3 .cmd=3 .mts=2 (+3 个纯数字后缀) 
深度分布(evidence/ 之后段数): 1→124  2→373  3→19  4→5  5→7  6→6  8→1  9→12   ⇒ 深度不限是实测结论
```

（`Get-Content` 的数组下标与文件行号会错位约 5 行，本文件所有行号一律以 `git grep -n`/`Select-String` 为准。）

### §3 `WORKER_FILE_NAME_RE` 的处置与单一真源（要求 3）

**3.1 处置：不放宽，改为「正则只做 syntax 前置 + 谓词做 domain 判定」**

- basename 白名单语义**逐字保留**（`progress.md|report.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md`）。
- 新增 `WORKER_FILE_PATH_RE`（**只为 schema `pattern` 前置过滤**），来源是两条 fragment，避免第二份白名单字面量：

```ts
// shared/write-surface.ts（新文件；纯模块：只 import node:path + ../../worker/read-scope.ts）
export const WORKER_FILE_BASENAME_ALT = "(?:progress\\.md|report\\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\\.md)";
const SEG = "(?!\\.{1,2}(?:/|$))[A-Za-z0-9._-]+";
export const WORKER_FILE_EVIDENCE_ALT =
  `(?:\\.agenticdoc/[A-Za-z0-9._-]+/)?evidence/${SEG}(?:/${SEG})*\\.md`;
export const WORKER_FILE_PATH_RE = new RegExp(`^(?:${WORKER_FILE_BASENAME_ALT}|${WORKER_FILE_EVIDENCE_ALT})$`);
export const WORKER_FILE_NAME_RE = new RegExp(`^(?:${WORKER_FILE_BASENAME_ALT})$`);
```

- schema 换用 `WORKER_FILE_PATH_RE.source`（替换 `worker-file-tool.ts:104`）；`.md` 大小写：schema 侧按现状大小写敏感（避免引入 `i` 标志改变既有 12 例拒绝集的行为），谓词侧 `endsWithMd` 用大小写不敏感（Windows 上 `X.MD` 是同一文件，拒它是无价值的 false block）。
- **单源断言从「相等」改为「包含」**：`expect(WORKER_FILE_PATH_RE.source).toContain(WORKER_FILE_BASENAME_ALT)` 且 `expect(WORKER_FILE_NAME_RE.source).toContain(WORKER_FILE_BASENAME_ALT)` ⇒ 打不到「两份 basename 白名单字面量」的漂移，同时保留「12 例非法名在 schema 层仍被拒」的行为断言（12 例里 `a/b.md`/`../x.md`/`C:\abs\x.md`/`\\unc\share\x.md` 均不匹配 `WORKER_FILE_EVIDENCE_ALT`）。

**3.2 单一真源的接口（具体签名）**

```ts
// shared/write-surface.ts
export interface WriteSurfaceCtx {          // 派发期用（keyDir/trueRoot 可选，保持 ui-bridge 今天的「缺省即不评估 deny」语义）
  projectRoot: string; taskDir: string; keyDir?: string; trueRoot?: string; writeScope?: string[];
}
export interface WorkerFileWriteCtx extends WriteSurfaceCtx { keyDir: string; trueRoot: string; }  // 运行期必需
export type BareBase = "task-dir" | "cwd" | "none";
export type WriteSurfaceRule = "deny" | "scope" | "write-scope";
export interface WriteTargetVerdict {
  allowed: boolean; domain?: "task-dir" | "evidence"; target: string;
  rule?: WriteSurfaceRule; detail?: string;
}
export function writeDenyReason(ctx: WriteSurfaceCtx, absoluteTarget: string): string | null;   // 6 条，唯一
export function judgeWorkerWriteTarget(ctx: WriteSurfaceCtx, token: string, opts: { bareBase: BareBase }): WriteTargetVerdict;
export function evidenceDirOf(keyDir: string): string;
export function workerFileCtxFromTaskMeta(meta: { agenticdocRoot: string; trueAgenticdocRoot: string; writeScope?: string[] },
                                          taskDir: string, projectRoot: string): WorkerFileWriteCtx;
```

**依赖方向（硬约束）**：`shared/write-surface.ts` 只 import `node:path` 与 `worker/read-scope.ts`（`:isSameOrUnder`/`:normalizeForCompare`，都是纯函数）；**不得** import `worker-file-tool.ts` / `worker-mode.ts` / `pm/ui-bridge.ts` / `shared/deliverable-evidence.ts`（否则成环：`worker-file-tool → change-ledger`，`ui-bridge → worker-file-tool`）。`worker-file-tool.ts` 用 `export { WORKER_FILE_NAME_RE, isAllowedWorkerFileBasename as isAllowedWorkerFile } from "../shared/write-surface.ts";` 再导出 ⇒ **§1.3 的 3 个 importer + 2 个测试 import 零改动**。

**3.3 适配层最小改法**

- 运行期：`writeWorkerFile(ctx, file, content, mode)` = `judgeWorkerWriteTarget(ctx, file, {bareBase:"task-dir"})` → byte cap → `mkdirSync(path.dirname(target))` → write → `appendWriteFileEvent(<taskDir>/trace.log, repoRelativePath(target))`。注意保持现有失败顺序不变式：**拒绝路径不建目录、不建/不改文件**（现有测试 `rejects fail-closed: no taskDir is created ...` 依赖它）。
- 壳层：`checkBashWriteScopeTarget` 的 `verbatim=false` 分支原样保留（`allow-unknown`）；verbatim 分支改为 `judgeWorkerWriteTarget(config, rawTarget, {bareBase:"cwd"})` 后把 `rule` 映射回原有四个 token（`deny`/`scope`/`write-scope`），**error message 文案逐字保留**（t03 的 63 例断言含 `[rule=deny]`/`[rule=scope]` 与 `[WRITE_SCOPE]` 行格式）。
- 派发期：见 §4.3。

### §4 派发期与运行期同源（要求 4 / AC-016）

**4.1 今天为什么相反（已确证，不重复发现）**：`judgeWriteTarget`（`ui-bridge.ts:1707`）的允许面 = deny → `isSameOrUnder(task, target)` → `!hasDirComponent && (WORKER_FILE_NAME_RE.test || FRAMEWORK_TASK_BASENAMES.includes)` → shape 拒。缺 evidence 一步 ⇒ `.agenticdoc/k/evidence/x.md`（有目录成分、ext 形状）落到 `rule=scope`。反向证据在 `test/suite/mwds-t02-write-intent.test.ts:580-582`（断言 false）与 §5.1-(5) 的语料 replay。

**4.2 ctx 已齐（B2 无需改字段）**

```
ui-bridge.ts:2366-2372  judgeWriteIntent({ type, description, taskDir, projectRoot: projectDir, keyDir: path.join(agenticdocRoot, ownerKey), trueRoot: agenticdocRoot, allowForeignWrite })
ui-bridge.ts:2860-2866  同上（/worker 入口）
```
`keyDir = path.join(agenticdocRoot, ownerKey)` 与运行期 `path.dirname(meta.agenticdocRoot)` 等价（`agenticdocRoot` 在 PM 侧即 `.agenticdoc`）。注意 `judgeWriteIntent` 对 **shell 角色提前 return ok**（`ui-bridge.ts:1741-1745`）⇒ AC-016 里「research 卡」今天**已经**不会被拒；新增工作实际只在 review 形态，这一条要写进 AC-016 用例注释，避免把「早就通过」当成新证据。

**4.3 最小改法（B1）**：在 `judgeWriteTarget` 的 deny 之后插入共享谓词的调用，其余 PM 专属通道保持原位：

```ts
export function judgeWriteTarget(pathToken: string, ctx: PmWriteSurfaceCtx): WriteTargetJudge {
  const shape = classifyWriteTargetShape(pathToken, ctx);
  const verdict = judgeWorkerWriteTarget(ctx, pathToken, { bareBase: "none" });
  if (verdict.allowed) return { allowed: true, shape };
  if (verdict.rule === "deny") return { allowed: false, shape, rule: "deny", detail: `denied:${verdict.detail}` };
  const hasDirComponent = /[\\/]/.test(pathToken);
  if (!hasDirComponent && (WORKER_FILE_NAME_RE.test(pathToken) || FRAMEWORK_TASK_BASENAMES.includes(pathToken))) {
    return { allowed: true, shape };                       // 逐字保留 ui-bridge.ts:1715
  }
  if (WRITE_TARGET_PATH_SHAPES.has(shape)) return { allowed: false, shape, rule: "scope", detail: "outside-write-surface" };
  return { allowed: true, shape };
}
```

要点：(i) `bareBase:"none"` ⇒ 派发期的裸 token 行为**逐字不变**（仍由 :1715 的 basename 通道决定），共享谓词只贡献 deny 表 + evidence 面 + write_scope（PM ctx 无 writeScope ⇒ 不生效）；(ii) deny 优先级不变；(iii) 越界面仍 fail-closed（shape 分支只可能更严）；(iv) 不再有第二份「evidence 路径」正则（唯一字面量在 `shared/write-surface.ts`）。

**4.4 锚定纪律**：B1-B6 的所有引用写成 `文件::符号`（`ui-bridge.ts::judgeWriteTarget`、`ui-bridge.ts::PmWriteSurfaceCtx`、`ui-bridge.ts::writeIntentRefusal`、`ui-bridge.ts::renderWriteSurfaceContract`、`ui-bridge.ts:2432`→写成「`dispatch_worker` 工具里紧邻 `judgeWriteIntent` 调用的 `writeScope` 渲染条件」）。并发的 `setWatchWidget` 改动使行号 +2，实现时用 `grep -n` 重定位。

### §5 A1-A16 逐条决策（要求 1）

> 格式：符号 · 决策 · 语义 · 影响面（调用点） · 风险。

- **A1 `worker-file-tool.ts:42 WORKER_FILE_NAME_RE` · 保留（迁址 + 再导出）** · 语义逐字不变，定义搬到 `shared/write-surface.ts`，原文件 `export { … } from` 再导出 · 影响面：`ui-bridge.ts:65`、`deliverable-evidence.ts:43`、`worker-file-tool.ts:49/104`、2 个测试 import（**路径不变**）、dist bundle（D1） · 风险：低。唯一实际风险是有人「顺手」把路径分支塞进这个正则（§3.1 已明令禁止，并用「包含式」单源断言兜住）。
- **A2 `worker-file-tool.ts:48 isAllowedWorkerFile` · 改写** · 保留 basename 判定（改名 `isAllowedWorkerFileBasename` + 旧名再导出）；新增唯一谓词 `judgeWorkerWriteTarget(ctx, token, {bareBase})`，判定顺序见 §2.3 · 影响面：3 个 importer + 2 个测试 + 新增 `shared/write-surface.ts` · 风险：**中**。风险集中在 `bareBase` 三态：`task-dir`（worker_file）、`cwd`（bash）、`none`（派发期）如果实现时写错，会把裸 token 的基准挪位（如把 bash 的裸 token 当 taskDir 相对 ⇒ 引入真实的越界写）。缓解：§11 矩阵把三种 bareBase 的裸 token 行全部锁进用例。
- **A3 `worker-file-tool.ts:56 writeWorkerFile` · 改写** · 签名 `(ctx: WorkerFileWriteCtx, file, content, mode)`；`keyDir`/`trueRoot` 必需（类型层 fail-closed：没有它们就构造不出 ctx） · 影响面：`registerWorkerFileTool` 的 execute 闭包（唯一生产调用点）+ `agent-team-loop-worker-file-tool.test.ts` 的 8 处 `writeWorkerFile(taskDir, …)` 调用（需加 `makeCtx(taskDir)` 夹具） · 风险：低-中（测试改动面大但机械）。
- **A4 `worker-file-tool.ts:62-64` 拒绝原因 · 改写** · 两类文案：`file name not allowed: <json>`（basename 域，**原文保留**——`agent-team-loop-worker-file-tool.test.ts:223` 断言 `/^worker_file rejected: /`）+ 新增 `outside the worker write surface: <json> [rule=<deny|scope|write-scope>]` · 影响面：`worker-mode.ts:2390` 的 `[TOOL_ERR]`（`toolErrorText` 取首行、截断 120 字符 ⇒ **`rule=` 必须前置**） · 风险：低。注意别把原因串写长到 120 字符以外，否则 `rule=` 被截掉，AC-006 的「可辨 trace」失效。
- **A5 `worker-file-tool.ts:72 mkdirSync` · 改写** · `fs.mkdirSync(path.dirname(target), {recursive:true})` · 影响面：taskDir 域行为逐字相同（`dirname(join(taskDir, base)) === taskDir`）；evidence 域才能建 `evidence/research/` · 风险：低。保持「先判定后建目录」的顺序（越界不得产生空目录，AC-006 用例断言之）。
- **A6 `worker-file-tool.ts:73` · 改写** · 用谓词返回的 `target` · 影响面：同 A5；`repoRelativePath(target)` 落到事件里 · 风险：低。「project 根之外」的相对路径不需要处理：谓词已保证 target 在 taskDir/evidence 内。
- **A7 `worker-file-tool.ts:82 appendWriteFileEvent` · 保留** · trace 仍写 `<taskDir>/trace.log`（不是 evidence 下），事件 path = repo 相对（evidence 写产出 `.agenticdoc/<key>/evidence/…`，与 `diffLedger` 的声明面同基准） · 影响面：`shared/change-ledger.ts::parseWriteFileEvents` 消费者 6 处（RQ-3 已清点，全 TS） · 风险：低。
- **A8 `worker-file-tool.ts:87 registerWorkerFileTool` · 改写** · 第二参 `ctx: WorkerFileWriteCtx` · 影响面：`worker-mode.ts:2133`、`agent-team-loop-worker-file-tool.test.ts:93`、dist · 风险：低。
- **A9 `worker-file-tool.ts:91-95` description · 改写** · 两个域都写清：「任务目录 basename（progress.md | report.md | report-<slug>.md）」+「`<key>/evidence/**/*.md`（可写 `.agenticdoc/<key>/evidence/…` 或 `evidence/…`），其它路径拒绝」 · 影响面：模型可见文本（AC-007 的扩展可改面之一） · 风险：低。description 里**不要**再出现「(no directories, no separators)」这类与 schema 冲突的绝对化措辞。
- **A10 `worker-file-tool.ts:96-100` promptGuidelines · 改写** · 同上，给出两条可复制示例 · 影响面：模型可见文本 · 风险：低。
- **A11 `worker-file-tool.ts:103-106` schema pattern · 改写** · 换 `WORKER_FILE_PATH_RE.source`；`file.description` 同步 · 影响面：`Compile(tool.parameters)` 的 12 例拒绝断言（`agent-team-loop-worker-file-tool.test.ts:310-330`）与 `:327` 单源断言（改「包含式」） · 风险：中。合并正则若把 `..` 段吃掉，schema 层会先放行、再由谓词拒——行为仍正确但「纵深」变浅；因此 `SEG` 的负向前瞻 `(?!\.{1,2}(?:/|$))` 是设计的一部分，不是可选优化。
- **A12 `worker-mode.ts:2131-2134` 注册处 · 改写** · `registerWorkerFileTool(pi, workerFileCtxFromTaskMeta(meta, workerTaskDir, process.cwd()))` · 影响面：注册门（`hasWriteTools === false` 的 5 个角色）/ dist / `agent-team-loop-checkpoint-wiring.test.ts:340`（只断言工具名被注册，不受 ctx 影响） · 风险：低。**注意 `meta.writeScope` 的 `[]`（present-but-blank ⇒ fail-closed）要原样传下去**，不要 `?? undefined`（那会把「声明为空」翻成「未声明」，打开 5 个角色的写面）。
- **A13 `worker-mode.ts:260-262 READ_TOOLS/WRITE_TOOLS` · 否决（不改）** · 语义：`READ_TOOLS`/`WRITE_TOOLS` 表达的是「pi 内建工具族」，`[CHECKPOINT] writes=` 的含义随之是「agent 用了写工具」；把 `worker_file`/`bash` 塞进去会把该字段的含义偷换成「框架记了账」，而 P4 已证明账本双向失真 ⇒ 用不可信的输入当判据 · 语义替代（属 AC-009/S5，本 key 另一任务）：writeless 判据改读「最近落盘信号（`[WRITE_FILE]` 行，含 `worker_file` 与成功 bash 写的行）」+ 产物存在性 + `progress.md` 完成记录 · 影响面：`ComputeRisk` 入参（`ConvergenceSignals.writes`）与 `formatMachineCheckpoint` 的 `writes=` 字段 · 风险：**高（若真改）**——这正是「修入参 vs 改判据」的岔口，本设计选「改判据」并把工具面常量保持语义纯净。注意 `worker_file` **今天已经**通过 `worker-file-tool.ts:82` 落 `[WRITE_FILE]` 行 ⇒ 改判据**零新增管线**。
- **A14 两份 deny 表（`worker-mode.ts:1568 bashWriteDenyReason` / `ui-bridge.ts:1673 pmWriteDenyReason`）· 采纳（合并）** · 抽 `writeDenyReason(ctx, absTarget)`，两处变一行委托；参数化的 `keyDir`/`trueRoot` 可选性保持不变（PM 侧缺省即跳过前 4 条，与今天 `ui-bridge.ts:1561-1563` 的注释语义一致） · 影响面：壳层 5+1 条 deny 断言（t03 63 例）、PM `rule=deny` 断言（t02 :694-715）、`test/extensions/agent-team-loop.test.ts:6297` 的 `must: /export function judgeWriteTarget/` 不受影响 · 风险：中。**六条规则的字符串必须逐字保留**（`pm-state.md`/`workers/_workers*`/`_index.parallel`/`other key dir / .agenticdoc root`/`packages/**`/`.git/**`），因为它们在测试与 trace 里是机器判据。
- **A15 `worker-mode.ts:1648-1661` + `:1584-1599` · 采纳（约束 worker_file）** · 复用 `matchesWriteScopeEntry`（含 glob 与尾部 `/**` 剥离） · 影响面：`worker_file` 的 5 个角色；今天 `renderDefaultWriteScope` 只对 `research` 渲染且等于默认面 ⇒ **今天零行为变化** · 风险：中。若将来 PM 手写更窄的 `write_scope:`，`progress.md` 也会被挡（fail-closed，可接受但必须写进文档）；反之若忘记传 `writeScope`，收窄声明被宽松通道旁路（选 A15 就是为了堵这个）。
- **A16 `worker-mode.ts:2390` / `output-writer.ts:440-446` · 改写（取最小支）** · 只落既有 `[TOOL_ERR] worker_file <reason>`，reason 自带 `rule=`；**不新增** `[WRITE_SCOPE]` 风格审计行 · 理由：tool 的失败形态是 throw → `tool_execution_end.isError` → `worker-mode.ts:2390` 已经写出这一行；再加一条 `[WRITE_SCOPE]` 需要 tool 知道 `taskKey`/`agenticdocRoot`，并会与壳层守卫的审计通道重复（且 `[WRITE_SCOPE_SUMMARY]` 的计数不等式会被第三来源污染） · 影响面：`agent-team-loop-checkpoint-wiring.test.ts:414-470`（已断言 `[TOOL_ERR] worker_file` 出现；文案含 `rule=` 不破坏 `includes` 断言） · 风险：低。

### §6 B1-B6 / C1-C11 / D1 决策

**B**

- **B1 采纳**（§4.3 的最小改法）。
- **B2 采纳（无需改字段）**：`PmWriteSurfaceCtx`（`ui-bridge.ts:1564`）已有 `keyDir`/`trueRoot`；两处调用点（`dispatch_worker` 与 `/worker`）实测都已传（§4.2）。
- **B3 采纳**：`writeIntentRefusal` 的 Fix 第 1 条今天只写 `worker_file file="report.md"`，改为「`worker_file file="report.md"`（或 `file=".agenticdoc/<key>/evidence/<name>.md"`）」。受影响断言：`test/suite/mwds-t02-write-intent.test.ts:830`「names the code, the path and the three ways forward」——用 `toContain` 写法，加一条 evidence 形式即可。
- **B4 否决（不做）**：`writeScope` 渲染条件（`ui-bridge.ts:2432` / `:2926` 的 `writelessRole && isShellRole(typeField)`）保持不变。理由：(i) A15 让 `write_scope` 也约束 worker_file，但**默认面 = 渲染出来的面**，非 shell 角色拿到 `undefined` 时走的就是默认面，功能等价；(ii) 给 review/verifier/reviewer/rag-research 的 `task.md` 新增一行会改变其字节（派发卡的 idempotent 套用/契约段测试与 golden 快照都在那附近），收益为零；(iii) 真正需要的是「告诉这些角色它们**能**写 `<key>/evidence/**`」——那是 B5（契约段）的事。
- **B5 采纳**：`renderWriteSurfaceContract`（`ui-bridge.ts:1779`）的 `allowed` 行加入 evidence 面（含两种写法），`denied` 行补一句「其他 key 的 `evidence/**` 仍禁」。受影响的既有断言：`test/suite/mwds-t02-write-intent.test.ts:365/516` 与 `test/suite/autopilot-protocol.test.ts` 附近的契约段字节断言（须核对是否逐字比对）。
- **B6 采纳**：`judgeWriteTarget` 上方的顺序注释（`ui-bridge.ts:1698-1706` 区域，符号锚定）加入「3b. own-key evidence surface」一步；注释里**不写行号**（§1.1）。

**C（11 项）**

- **C1 采纳**：`agent-team-loop-worker-file-tool.test.ts` 的目录快照计入 `trace.log`（HEAD 既存 2 例红：`:177`/`:285`）。修完后该文件应 9/9。
- **C2 采纳（保持）**：12 例 `REJECTED_FILES` 全拒不变（schema 前置 + 谓词双层断言）。
- **C3 改写**：`:327` 的单源断言从 `pattern === WORKER_FILE_NAME_RE.source` 改为「`WORKER_FILE_PATH_RE.source` 含 `WORKER_FILE_BASENAME_ALT`」+「12 例在两层都被拒」+ 新增「evidence 路径在 schema 层被接受」。
- **C4 采纳**：`change-ledger.test.ts:195-230` 加「成功写 evidence ⇒ 恰好 1 条 `[WRITE_FILE] path=.agenticdoc/<key>/evidence/…`」；越界 0 条的事件断言保持不变。
- **C5 采纳（重基线）**：`mwds-t02-write-intent.test.ts:346` 的 `expect(truePositive).toHaveLength(1)` 在 B1 后必翻。目标态：`violations.length === 0`，`falsePositives.length === 0`；`truePositive` 断言删除或改为 `0`（并把 `[VERIFY] VC-015` 行改口径：`violations=0`）。**不得**保留「已知真阳性 1 例」的旧白名单来掩盖修复。
- **C6 改写（关键）**：`:580-582` 的 `.agenticdoc/k/evidence/x.md === false` **必须带着 keyDir 的 ctx 重写**：无 `keyDir` 的 ctx 仍应判 false（fail-closed，是正确行为，要保留一个反向用例），带 `keyDir` 的 ctx 判 true。`:653 axisCtx()` 已是现成的带 keyDir 夹具，直接复用。
- **C7 采纳（不变）**：`mwds-t03-bash-write-scope.test.ts` 63 例整体保持（通道两侧语义对齐的反向对照）。
- **C8 / C9 采纳（不变）**：active set / 注册门 / Python REGISTRY parity 断言保持（本设计不新增工具名、不动 `TOOL_ALLOWLISTS`）。
- **C10 采纳（保持）**：`test_autopilot_l0.py:233-260`（7 键 order-exact）与 `test_mwpp_collection_parity.py:66-90`（11 键快照）解析 TS 源码文本 ⇒ 不动表即保持绿。
- **C11 采纳（改名）**：新增回归套件。仓库既有命名是任务/key 前缀（`test/suite/mwds-t02-…`、`mwgal-t10-…`），建议 `packages/coding-agent/test/suite/woc-t24-write-face-evidence.test.ts`（`woc` = key 缩写；若 PM 统一走 issue 编号则用 `<issue>-write-face-evidence.test.ts`）。内容见 §7-§9。

**D**

- **D1 采纳（实现期）**：`packages/multi-workers/dist/extensions/agent-team-loop.js` 内嵌 `worker-file-tool.ts`（实测含 `file name not allowed` 字节、5 处 `WORKER_FILE_NAME_RE`）⇒ 改源后必须重建 dist（`mw update-env`/`npm run build` 由实现任务执行），否则分发副本与源码判定不一致，AC-006 端到端会在分发路径上复现旧行为。

### §7 AC-006 测试形态（要求 5）

**用例文件**：新增 `packages/coding-agent/test/suite/woc-t24-write-face-evidence.test.ts`（C11）；不新增到 `test/extensions/` 下以免与既有 unit 文件语义重叠，但 C1/C2/C3 的 unit 断言留在 `test/extensions/agent-team-loop-worker-file-tool.test.ts`。

**夹具**：

```ts
const root = fs.mkdtempSync(path.join(os.tmpdir(), "woc-"));
// <root>/.agenticdoc/k/workers/t/  (taskDir)  ; <root>/.agenticdoc/k/evidence/  ; <root>/.agenticdoc/goal.md
const ctx: WorkerFileWriteCtx = {
  projectRoot: root, taskDir, keyDir: path.join(root, ".agenticdoc", "k"), trueRoot: path.join(root, ".agenticdoc"),
  writeScope: [`.agenticdoc/k/workers/t`, `.agenticdoc/k/evidence`],
};
const tool = registerTool(ctx);   // capturePi() 风格，同 agent-team-loop-worker-file-tool.test.ts
```

**断言（成功面，逐条）**：

1. `execute({file: ".agenticdoc/k/evidence/research/r1.md", content, mode:"write"})` → 解析结果 `path === <keyDir>/evidence/research/r1.md`、字节相等、`trace.log` 含 `[WRITE_FILE] path=.agenticdoc/k/evidence/research/r1.md`；`mkdirSync` 建出 `evidence/research/`。
2. `file: "evidence/research/r2.md"`（key 相对别名）→ 落到同一 `evidenceDir`，事件为 `.agenticdoc/k/evidence/research/r2.md`。
3. 既有 basename 3 例（`progress.md`/`report.md`/`report-x.md`）仍落在 `taskDir`（AC-006 明文「3/3 仍通过」）。
4. `Compile(tool.parameters).Check({file: …evidence…, content:"x"})` → true（schema 层不早退）。

**断言（fail-closed 面，逐条：`ok=false` + 目录/文件集合零变化 + 原因含 `rule=`）**：`"../.."`、`"../../x.md"`、`"evidence/../../x.md"`、`"/etc/x.md"`、`"C:\\abs\\x.md"`、`"\\\\unc\\share\\x.md"`、`".agenticdoc/other-key/evidence/x.md"`、`"packages/coding-agent/src/x.ts"`、`".git/config"`、`".agenticdoc/k/pm-state.md"`、`".agenticdoc/k/workers/_workers.parallel"`、`".agenticdoc/_index.parallel"`、`".agenticdoc/k/design.md"`、`".agenticdoc/k/workers/other/report.md"`、`"evidence/"`、`"evidence"`、`"evidence/x.txt"`、`".agenticdoc/k/evidence/../x.md"`。其中「目录/文件零变化」用 `snapshot(root)`（递归、相对路径有序集）在调用前后逐例比较。

**断言（两通道一致性，AC-006 §5.2 的对齐要求）**：对同一 token 列表跑 `judgeWorkerWriteTarget(ctxWF, t, {bareBase:"task-dir"})` 与 `checkBashWriteScopeTarget(bashCtx, t, true)`，断言 `allowed` 相等，**仅** `evidence/x.md` 一行登记为已知例外（§11）。

### §8 AC-007 测试形态（要求 5，先钉死文案层级）

**8.1 层级判定（结论）**：

```
packages/agent/src/agent-loop.ts:611  result: createErrorToolResult(`Tool ${toolCall.name} not found`)
packages/agent/src/agent-loop.ts:454-461 / :508-518   kind==="immediate" 直接 emitToolExecutionEnd（串行/并行两支）
packages/agent/src/agent-loop.ts:709-754              finalizeExecutedToolCall —— 唯一触发 afterToolCall(extension tool_result) 的地方
packages/agent/src/agent-loop.ts:596-606              prepareToolCall 先 find(tool)，未命中即 return immediate ⇒ beforeToolCall(extension tool_call) 不被调用
```
⇒ 扩展**既拿不到也改不了**这条模型可见文本；连「拦截未知工具的 tool_call」都不成立（hook 在 tool 命中之后才执行）。故：

- **可改面（要做）**：`worker-file-tool.ts` 的 `description`/`promptGuidelines`（A9/A10）、`renderWriteSurfaceContract` 的契约段（B5）、`writeIntentRefusal` 的 Fix 清单（B3）、以及 PM 可见的 `[TOOL_ERR]` 行的 `rule=` 字段（A4/A16）。
- **不可改面（不改，也不假装改）**：pi 核心的 `Tool write not found`；因此 AC-007 走 (a) 支「该错误不再产生」+ (b) 支只作**观测**（trace 里能看出替代通道）。

**8.2 用例文件与夹具**：

- 文案层级断言（扩展地）→ 放在 `packages/coding-agent/test/suite/woc-t24-write-face-evidence.test.ts`；用 `createHarness`（`test/suite/harness.ts:101`，faux provider）驱动一个 writeless 角色 worker，脚本化的 assistant 消息发出一个 `write` 工具调用，断言：(i) trace 出现 `[TOOL_ERR] write Tool write not found`（证明该文本来自核心、扩展只旁观）；(ii) 断言 `renderWriteSurfaceContract(type, scope)` 与 `worker_file` 的 `description` 都已点出替代通道。**（i）是本 AC 的「层级」证据，(ii) 是「事前指引存在」的证据，两者不可互相顶替。**
- 端到端形态（AC-007 的正式验收）：取 `wfg-rq-d1` / `wfg-rq2-enforcement` / `wfg-rq3-safety` 三份历史 `task.md`（`git show` 或工作树原件，字节纯净复制到 `test/suite/fixtures/` 或直接在用例内内联其 `## 唯一证据文件` 段）作为夹具；用 faux provider 让 agent 直接调用 `worker_file` 写卡片声明的路径，断言 3/3 成功 + trace 无 `Tool write not found`。
- 前置检查（避免假绿）：先确认这 3 份 `task.md` 的声明行确实是 `evidence/**` 形状（P2 的描述 + `wfg-rq-d1` 退回任务目录的事实），若某份声明的其实不是 evidence 路径，则换 `mwg-qg-review-20261010` / `wjg-qg-evidence-closure`（t02 语料里已确认的 evidence 声明形态）——**用例注释里必须写清选了哪 3 份与依据**。

**8.3 不做的测试形态**：不加「模型在同一回合改用正确通道」的行为断言（无真模型可判定；faux provider 的脚本是我们自己写的，断言它等于自证）。这一条写进 `## 残留与未验证`。

### §9 AC-016 测试形态（要求 5）

**用例文件**：扩 `packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`（该文件就是 `judgeWriteTarget` 的行为主场，且已有 `axisCtx()` 带 keyDir 夹具与 `:694` 的 deny 断言）。

**夹具与断言**：

1. 两张卡片文本（1 research + 1 review），各含 `## 唯一证据文件` 写法两种：`evidence/research/x.md` 与 `.agenticdoc/k/evidence/research/x.md`。调 `judgeWriteIntent({type, description, taskDir, projectRoot, keyDir, trueRoot})` ⇒ `ok === true`、`violations === []`（**review 形态是今天的红例；research 今天已因 shell 角色提前 return 而通过，注释里必须写明**）。
2. 越界 3/3 仍拒：`../..`、`.agenticdoc/other/evidence/x.md`、`packages/coding-agent/src/x.ts` ⇒ `rule === "deny"` 或 `"scope"`，`ok === false`。
3. **同源断言（两种，缺一不可）**：
   - 行为面：同一 token×ctx 矩阵在 `isWhitelistedWriteTarget`（派发期）与 `writeWorkerFile`（运行期）上 `allowed` 逐行相同（`evidence/x.md` 一行按 §11 记为已知例外并在用例里显式列出）。
   - 结构面：源码级断言「`src/extensions/agent-team-loop/**` 内 `evidence` 路径正则字面量只有 1 处」。实现建议：`shared/write-surface.ts` 导出 `WORKER_FILE_EVIDENCE_ALT`；用例断言 `WORKER_FILE_PATH_RE.source` 包含它，并另加一条「其它模块不得再声明 evidence 路径正则」的 grep 式检查（读源文件 + 正则计数 === 1）。
4. 现状基线对照（写进用例注释，不设红/绿）：`test/suite/mwds-t02-write-intent.test.ts:580-582` 的 `false` 断言与 `:346` 的 `truePositive=1` 就是 C5/C6 要翻的那两处。

### §10 不应做的改动（要求 6）

1. **不把 `worker_file` 加进 `TOOL_ALLOWLISTS`**（`worker-mode.ts:73-106`）：`test_autopilot_l0.py:233-260` 对 7 键做 order-exact 源码文本对比、`test_mwpp_collection_parity.py:66-90` 对 11 键做全表快照 ⇒ 双红，且 `activeToolsForType`（`worker-mode.ts:145`）的追加语义会让写角色也拿到它。
2. **不给 writeless 角色注册同名 `write` 桩工具**：与 GC-5 字面冲突，改动 active set 会让 C8/C9 的 parity 断言重写，并掩盖核心那条诚实的「not found」。
3. **不改 pi 核心** `packages/agent/src/agent-loop.ts`（GC-2；AC-007 已把它钉为不可改面）。
4. **不放宽 `WORKER_FILE_NAME_RE` 去接受路径**（§1.3/§3.1：会同时打开 `deliverable-evidence.findNonEmptyReport` 与 `ui-bridge` basename 通道的目录盲区）。
5. **不动 `READ_TOOLS`/`WRITE_TOOLS`**（A13）：它们是工具族语义常量，不是账本聚合器。
6. **不放宽 deny 表、不把 `evidence` 变成 glob 前缀**：`isSameOrUnder(evidenceDir, target)` 的段边界是隔离红线；一旦改成前缀字符串比较，`.agenticdoc/k/evidence-evil/x.md` 会穿透。
7. **不新增 `write_scope` 之外的配置键、不新增可写共享文件**（GC-4；也让 `_autopilot/config.json` 的 parity 面不动）。
8. **不让壳层 bash 通道收 (b) 基准**（`evidence/x.md` 解释成 key 相对）：那是给 shell 说谎；今天是 fail-closed 的已知例外，写进用例白名单。
9. **不给非 shell 的 writeless 角色渲染 `write_scope:`**（B4）：改 `task.md` 字节、收益为零。
10. **不放宽 `WORKER_FILE_MAX_BYTES`**（64 KiB，A3 保持不变）：evidence 是报告面不是产物仓；真正的大产物走 bash。
11. **不把 evidence 写事件塞进 `run.json.artifacts`**：越出本 key 范围（`deliverable-evidence.nonOutputArtifacts` 的 artifact 通道由 run-store 的另一套写入负责）。

### §11 反向对照矩阵（同一 token 两通道一致）

| token | `writeWorkerFile`（运行期通道） | `checkBashWriteScopeTarget`（壳层） | 一致性 |
|---|---|---|---|
| `report.md` / `progress.md` / `report-x.md` | allow（taskDir） | allow | 一致（今天也一致） |
| `.agenticdoc/k/evidence/x.md` | allow（evidence，(a) 基准） | allow | 一致（**今天通道侧拒、壳层侧收**——本设计修的就是这条） |
| `.agenticdoc/k/evidence/research/x.md` | allow | allow | 一致 |
| `evidence/x.md` | allow（(b) 基准） | deny(scope) | **已知例外**（§2.1 末；fail-closed） |
| `../..` | deny(scope) | deny(scope) | 一致 |
| `evidence/../../x.md` | deny(scope) | deny(scope) | 一致 |
| `.agenticdoc/other/evidence/x.md` | deny(deny: other key dir) | deny(deny) | 一致 |
| `packages/a.ts` | deny(deny: packages/**) | deny(deny) | 一致 |
| `.git/config` | deny(deny: .git/**) | deny(deny) | 一致 |
| `.agenticdoc/k/pm-state.md` | deny(deny) | deny(deny) | 一致 |
| `.agenticdoc/k/workers/_workers.parallel` | deny(deny) | deny(deny) | 一致 |
| `.agenticdoc/_index.parallel` | deny(deny) | deny(deny) | 一致 |
| `.agenticdoc/k/design.md` | deny(scope) | deny(scope) | 一致 |
| `.agenticdoc/k/workers/other/report.md` | deny(scope) | deny(scope) | 一致 |
| `C:\abs\x.md` / `\\unc\share\x.md` / `/etc/x.md` | deny(scope) | deny(scope) | 一致 |
| `evidence/x.txt` | deny(scope)（扩展名） | allow（壳层不限扩展名） | **已知例外**（通道更严：evidence 只收 `.md`） |

（最后一行是第二个显式例外：它在**允许**方向上是壳层更宽、通道更严，属于 fail-closed，且在 AC-006 用例里登记。）

### 未覆盖面声明

- 未跑任何测试（vitest/pytest 都没跑），因此本文件所有「修好后应为绿」都是静态推断，不是实测；11 项 C 清单的「实测现状」（HEAD 既存 2/1 例红、t03 63/63、change-ledger+checkpoint 22/22）沿用 RQ-2 的证据，本轮未复核。
- 未实现任何改动、未重建 dist、未做真实 provider 端到端。
- 未验证 `pi` 的 `tool_result` 钩子在 `kind:"immediate"` 路径上的行为（只做了静态代码路径追踪：`prepareToolCall` → immediate → `emitToolExecutionEnd`，不经 `finalizeExecutedToolCall`）。
- 未评估 `collectArtifacts`/`findNonEmptyReport` 对 evidence 产物的收集语义（R3「evidence 只放产物」未验证）；**只写 `evidence/x.md` 而不写 `report.md`/`output.md` 的 worker，今天仍会在 `hasDeliverableEvidence` 判 `delivered=false`**（`deliverable-evidence.ts` 的 channel 1/2/3 都不读「本 worker 新写的 evidence 文件」）——这是本 key 修完通道后**仍然存在**的 PM 吸收缺口，属另一条链路。
- 未测多窗口/并发对 `write_scope` 与 `task.md` 的写入（GC-4 面）。
- 未核 Emoji/行号：本文件行号取自当前工作树，`pm/ui-bridge.ts` 与 HEAD 有 +2 偏移（§1.1）。

## 残留与未验证

1. **AC-007 的 (b) 支无法机械验收**：「收到 `Tool write not found` 后同一回合改用正确通道」需要真模型行为；faux provider 的脚本是我们写的，断言它等于自证。本设计只验收 (a) 支（错误不再产生：3/3 `worker_file` 调用成功）+ 扩展可改面文案存在。
2. **`evidence/x.txt` 类型的非 `.md` 产物**：worker_file 收窄为 `.md`；非 shell 的 writeless 角色（review/verifier/reviewer/rag-research）若被要求产出 `.txt/.json` 会在通道侧被拒（fail-closed）。这是一个新的「声明不可满足」形态，PM 侧要不要一并判（如 `judgeWriteTarget` 也拒 `.txt`）尚未定；本设计选择「运行期拒、派发期不判」，会在 AC-016 的一致矩阵里留下第三个语义缺口（未列入 §11 表）。
3. **`write_scope:` 收窄对 worker_file 的连坐**（A15）：今天零影响，但若将来有 key 给 review 卡手写更窄的 `write_scope:`，`progress.md` 也会被挡。未为这种形态设计文案。
4. **不写 `report.md` 的 worker 仍然被 `hasDeliverableEvidence` 判未交付**（见未覆盖面声明末条）：通道修好 ≠ PM 吸收修好，需在 spec 的 S1/S5 链路里处理或另开条目。
5. **`test/extensions/agent-team-loop.test.ts` 的行号锚表相对当前工作树已失配**（§1.1）：静态断定，未实跑；实现 B1 会再叠加偏移。若该测试在本机基线里是绿的，说明我读错了口径，需在实现期实测校正。
6. **`WORKER_FILE_PATH_RE` 的正则细节**（负向前瞻、`.md` 大小写敏感度、schema 是否该加 `i`）只做了纸面推演，未用 TypeBox `Compile` 实测 12 例 + evidence 例；实现期必须先跑该 unit 文件再改行为。
7. **dist 重建的验证方式**（`pi-dist-content` 类 bundle 内容检查）未调研。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worker-output-contract/tasks/T-DR1-write-face-channel.md`（+ 本任务目录 `task.md` 的 envelope）
- spec：`.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P2、§1.6 S4、§1.7 第 3 条、§2.3、§3 AC-006/AC-007/AC-016、§4 R3/R7/R8）
- 上游研究：`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq2-write-face-20261014.md`（A1-A16/B1-B6/C1-C11/D1、§2 worker_file 全貌、§3 壳层全貌、§5 反向对照、§6 文案链）
- 目标锚点：`.agenticdoc/goal.md`（GC-1…GC-7；「文件驱动的去中心化协调」「工具白名单按任务类型」）
- 源码：`worker/worker-file-tool.ts`、`worker/worker-mode.ts`、`worker/read-scope.ts`、`worker/output-writer.ts`、`shared/deliverable-evidence.ts`、`shared/change-ledger.ts`、`shared/paths.ts`、`pm/ui-bridge.ts`、`packages/agent/src/agent-loop.ts`、`packages/multi-workers/autopilot/dispatch.py`（经 RQ-2 转引）
- 测试：`test/extensions/agent-team-loop-worker-file-tool.test.ts`、`test/extensions/agent-team-loop-checkpoint-wiring.test.ts`、`test/extensions/agent-team-loop.test.ts`（锚表 `:6253`/`:6297`）、`test/suite/mwds-t02-write-intent.test.ts`、`test/suite/mwds-t03-bash-write-scope.test.ts`、`test/suite/change-ledger.test.ts`、`test/suite/harness.ts`

[VERIFY] A_items=16 (adopted/rewritten=13, kept=2 [A1,A7], rejected=1 [A13]) B_items=6 (adopt=5, reject=1 [B4]) C_items=11 (adopt=9, rewritten=2 [C3,C6]) D_items=1 deny_rules=6 evidence_files=547 evidence_name_charset_violations=0 evidence_max_depth_segments=9 evidence_md_share=397/547 worker_file_name_importers=3 (+2 test imports, +5 dist bytes) shared_module_new=1 (shared/write-surface.ts) known_channel_asymmetries=2 (evidence-key-relative-in-bash; evidence-non-md-extension) tests_run=0 files_modified=0 method=static-only
