# DRQ-3：角色解析单源 + key 身份判据 设计定稿

- key: `mw-guard-form-hardening`｜phase: DESIGN｜type: research（**只读**：未改任何源码/测试/task.md；唯一写入 = 本文件）
- 基线 commit: `ab546bb649b1c3a4394d52065bb0e57cb5965be8`（`git rev-parse HEAD`；工作树有 73 项他人未提交改动，本报告全部只读）
- 上游输入：`evidence/research/spec-taskmd-corpus-20261011.md`（RQ-4）、`evidence/research/spec-key-identity-20261011.md`（RQ-5）、`spec.md` §3 AC-005/AC-006 + §7/§8、`design.md` §2/§3/§5、QG-B `mw-dispatch-settle-gates/evidence/quality-gate-code-adversarial-20261011.md` ⑤
- 纪律遵守：未运行 vitest / `npm run check` / `npm run build` / `mw build`；未调 `mw` CLI 写面命令；未用 `switch_key`/`advance_phase`。所有实测均用 `node --input-type=module`（import `src/*.ts` 或 `dist/*.js`）与 stdin Python（无临时文件）只读完成。

## 0. 结论摘要（8 条）与锚点

1. **共享解析函数落点** = 新建纯模块 `packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts`（TS 侧唯一实现）+ `packages/multi-workers/mw_common.py` 新增 `read_task_type()`（Python 侧同语义副本），两者由同一 golden 语料差分锁定（§2.3）。
2. **头部区边界**：`---` fence（首行判定 + 首个闭合）→ 否则首个空行 → 否则头部键文法截断；**首个 `type:` 胜出**；剥 BOM（TS `trim()` 天然吃 `\uFEFF`，Python 必须显式剥）。全语料 **0 个** fence、**0 个**无空行 ⇒ 退化分支良定义。
3. **正文 `type:` 的处置 = 能力升级才拒绝，其余审计**（两层：PM 写入前 `description` 扫描 + worker 启动 `dispatchRefusal`）；判据 = power-tool 集合（`write`/`edit`/`bash`）非子集。存量 308 本：**4 本有正文 `type:` 行，0 本触发升级拒绝**（唯一翻转书 `review-mw-worker-tree-kill/task.md` 的正文值 `review` 是**降权**，走审计）。
4. **fail-closed 定稿**：头部 `type:` 缺失或值非法 ⇒ **所有 origin 一律拒绝**（把 `isRegisteredType` 门从 `origin === "conductor"` 后移出，`worker-mode.ts:545`）。存量影响 = **1 本被拒**（`smoke-ac016b`，已终态）。**代价必须登记**：`autopilot-protocol.test.ts:353-354`（`type: mystery-type` 期望 fallback 全工具集且 `exitSpy` 未调用）与 `:362` 的反向断言会翻，见 §3.3。
5. **key 豁免清单定稿 = 显式 12 名 + 2 名补正**（`_impl_gate.log` 由 `implementation-gate.ts:69` 证明是框架自有、RQ-5 漏列；`_incidents` 非框架但磁盘已存在、须一并保留）；前缀豁免删除；`_scratch` 是**唯一** owner-放行的保留名。`exempt_live_key` 与 `case_mismatch_bypass` 当前仍为可复现漏洞（§0.2 实测），语料 0 例。
6. **大小写归一**：`index-store.ts:164-166`（读）/ `:73`（upsert）/ `:101`（claim）三处统一 `normalizeKey`（trim + `toLowerCase()` 比较，**存盘保留首写大小写**）；`_index.md` 回退（`ui-bridge.ts:82`）**必须**补 claim 检查 + 保留名/形态检查，且**不得**新增第 4 个 `foreignLiveClaimRefusal(` 调用点（否则 `mwds-t01-worker-guard.test.ts:269-272` 的 `guardSites.length === 3` 断言变红）——回退降级用 `claimState` 原语（与 `:77-81` 同族）。
7. **新证据（RQ-4/RQ-5 均未报）**：UTF-8 BOM 使 **Python 侧两个解析器（`launcher.py:155`/`mw.py:1794`）对 7 本现存任务书读不到 `type:`**（返回空），而 TS worker 读得到 ⇒ 这 7 本在 spawn 期落 `TASK_TYPE_TO_ROLE.get("", "coding")`（`mw_common.py:315`）拿到 **coding 角色模型**，其中 1 本实际是 `review`。spec §1.2 把 PM=297 / RQ-4=304 的差解释为「header 边界定义差异」是**错的**，差就是这 7 个 BOM 文件（§0.2 E-1）。
8. **收敛后跨语言等价已实测**：同一算法在 308 本上 `py_md5 == ts_md5 == a12dc0a7e6e779693638f134deeaad9a`；worker 侧行为变化 **1/308**（具名翻转书），Python 侧行为变化 **7/308**（BOM 修复）。该 md5 只作本报告证据，**不得**写成测试断言（P-08 增长敏感情形）。

### 0.1 锚点快照（AC-011：所有行级数值只对本快照成立）

| 项 | 值 |
|---|---|
| 基线 commit | `ab546bb649b1c3a4394d52065bb0e57cb5965be8` |
| `task.md` 总数 | **308**（RQ-4/PM 口径 305 + 本 key 新增 3 本 DRQ 任务书；新增 3 本均为 `type: research`） |
| `.agenticdoc/_index.parallel` | sha256 `11684D3F5E91F1D5AEA49E3CE3C04077330F56A55B1AA6B579270700D8A813DB`（Python 全字节）；`IndexStore.readAll()` rows=**52**（`-----` 分隔行被 `index-store.ts:36-38` 的 `key.startsWith("-")` 过滤）；mtime `2026-10-11T15:31:13Z`；长度 8727 B |
| 前缀 key / 大小写重名 / active 行 | `prefix_keys=[]`、`case_only_dups=[]`、`active=[]`（三条均为实测） |
| `_index.md active:` | `xkey-repair-mechanism`（`readIndexMdActive` 实测） |
| 语言/工具 | Python 3.14.3、Node v24.19.0 |

### 0.2 本次新增/复现的实测证据（可直接作为 VC 前值）

**E-1（BOM 跨语言分歧，新发现）** 命令（Python stdin，只读）：遍历 308 本，对每本比较「不去 BOM 的 `^type:[ \t]*(\S+)[ \t\r]*$`」（= `launcher.py:155` 现语义）与「剥 BOM 后同正则」：

```
bom_task_md_count= 7
launcher_view_files= 308  launcher_delta= 7
  .agenticdoc/_scratch/workers/mw-dr-autodispatch/task.md            '' -> coding
  .agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac015-ac016/task.md '' -> coding
  .agenticdoc/mw-dispatch-reliability/workers/mw-dr-glm53/task.md    '' -> coding
  .agenticdoc/mw-dispatch-reliability/workers/mw-dr-keyed-probe/task.md '' -> coding
  .agenticdoc/mw-dispatch-reliability/workers/mw-dr-live-claude/task.md '' -> review   ← 角色模型错配
  .agenticdoc/mw-dispatch-reliability/workers/mw-dr-live-ok/task.md  '' -> coding
  .agenticdoc/mw-dispatch-reliability/workers/mw-dr-pi-timi-test/task.md '' -> coding
```

对照：`node` 直接 import `dist/.../worker-mode.js` 的**真实** `parseTaskMd` 对 `mw-dr-live-claude/task.md` 返回 `review`（`trim()` 吃掉 `\uFEFF`），对 `mw-dr-autodispatch/task.md` 返回 `coding` ⇒ **同一文件 TS 读 review、Python 读空**。另 7 本 task.md 含 CRLF（`\r\n`），与 `\r` 处理同族，一并纳入 golden fixture。
⇒ 这不只是「潜在分歧」：`launcher.py:133-137` 用该值调 `mw_common.resolve_dispatch_model`（`mw_common.py:296-321`），空 type 落 `TASK_TYPE_TO_ROLE.get("", "coding")`（`:315`）⇒ `review` 书拿到 `coding` 角色模型。**spec §1.2 的「口径差 = header 边界定义差异」应改为「口径差 = BOM 未剥」**（304-297 = 7 = BOM 文件数，机器吻合）。

**E-2（RQ-4 计数在本快照复现）** 头部区 = 「首行 `---`? 取 fenced : 首个空行」规则下：`hdr_val_coding=198`、`hdr_val_research=81`、`hdr_val_review=27`、`hdr_val_vision=1`、`header_no_type=1`（`smoke-ac016b`）、`body_type_files=4`、`body_differs=1`、`fenced=0`、`no_blank/truncated=0`、`header_dup_type=0`、`anomalous_type_lines=[]`（即无 `type :`、无前后空格、无大小写变体）。**308 本全部头部值都是 `TOOL_ALLOWLISTS` 已注册键**，未注册值 0 例。
**E-3（新算法即前值 + 1）** 用我的 `extractTaskHeader`+`readTaskType` 对 308 本与**真实** `parseTaskMd` 逐本比较：`task_md_total=308 delta=1 truncated=0 fenced=0`，唯一 delta = `.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md | review -> coding`。
**E-4（今日 A5/A6/A7 复现，真实 `src` 模块）**：

```
_tmp                 row=null guard=ALLOW     ← A5：前缀豁免在 findByKey 之前
_workers.parallel    row=null guard=ALLOW
.mw                  row=null guard=ALLOW
_index.parallel      row=null guard=ALLOW
_scratch             row=null guard=ALLOW
mw-guard-form-hardening  row=WENBOZHOU-PC4:117296 guard=REFUSE   ← 同一 store 上 held-live 会被拒
MW-GUARD-FORM-HARDENING  row=null guard=ALLOW                   ← A6：大小写变体绕过
activeEntry= undefined ; indexMdActive= xkey-repair-mechanism
implicit_ownerKey= xkey-repair-mechanism guard=REFUSE docGaps=[]  ← A7：隐式路径落在他人 live key，docs 门禁放行
```

`ui-bridge.ts:1676-1679` 的 `if ((key ?? "").trim())` 使隐式分支**根本不调用**守卫 ⇒ A7 今日即可写进 `.agenticdoc/xkey-repair-mechanism/workers/`。
**E-5（行号漂移）** QG-B ⑤-13 写的 `index-store.ts:159-161` 在当前工作树是 `:164-166`（`findByKey`）；`:159-161` 落在 `writeRows` 内。本报告一律用当前行号。
**E-6（保留名清单漏项）** RQ-5 §2.1 的 12 名漏了 `_impl_gate.log`（框架自有：`shared/implementation-gate.ts:69` `const GATE_LOG_FILE = "_impl_gate.log"`，`:732` 写入）；磁盘上还存在非框架的 `_incidents`（`_index.parallel` 前缀 key 0 例、`_incidents` 未见框架代码引用）。二者都必须是保留名（否则 `key: _impl_gate.log` 会在框架日志同级建目录）。
**E-7（fail-closed 的既有契约代价，PM 必须知情）** `autopilot-protocol.test.ts:341-367` 显式锁定「manual（无 origin）未知类型走 GC-8 fallback + 不拒绝」：`{ taskKey: "m-unknown", md: "type: mystery-type\n\nwork\n", expected: PY_CODING_TOOLS }`（`:354`）与 `expect(exitSpy).not.toHaveBeenCalled()`（`:362`）；另有 `agent-team-loop-checkpoint-wiring.test.ts:319-320` 锁定 `toolsForType("mystery-type") === ALLOWLIST_SNAPSHOT.fallback`。§3.3 给出三种处置的代价对比与推荐。

## 1. 共享解析函数定稿（AC-005 单源）

### 1.1 落点与签名（TS）

**新文件** `packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts`（纯函数、零 import，除 `node:path` 也不需要 ⇒ 无循环依赖风险；`worker/` 与 `pm/` 都只 import 它，方向与现有 `shared/read-scope.ts` 同构）。可擦除 TS 语法，无 `any`，无内联 import。

```ts
/** 头部区（frontmatter 区）内的行索引，含界。 */
export interface TaskHeaderRegion {
	startLine: number;   // 0-based，含
	endLine: number;     // 0-based，含（无头部时 startLine > endLine）
	fenced: boolean;     // 首行 `---` 且找到闭合 `---`
	truncated: boolean;  // 无 fence 且无空行：区域由头部键文法截断（退化分支）
	byteOrderMark: boolean; // 原文首字节为 U+FEFF（审计用；解析行为不受影响）
}

export function extractTaskHeader(text: string): TaskHeaderRegion;
/** 头部区内第一个 `key:` 的值（trim 后）；头部区内没有该键 ⇒ undefined。 */
export function readTaskHeaderScalar(text: string, key: string): string | undefined;
/** `readTaskHeaderScalar(text, "type")`；本 key 只要求 type 走头部区。 */
export function readTaskType(text: string): string | undefined;
/** 正文区内 `type:` 行的行号(1-based)/值，按出现顺序；审计与升级判据的输入。 */
export function scanBodyTypeLines(text: string): Array<{ line: number; value: string }>;
/** power-tool 非子集判据：body 的 {write,edit,bash} ⊄ header 的 ⇒ 返回该行。 */
export function findTypeEscalation(
	bodyLines: ReadonlyArray<{ line: number; value: string }>,
	headerType: string,
	toolsFor: (type: string) => readonly string[],
): { line: number; value: string } | undefined;
```

**返回值语义（决定的理由）**
- `readTaskType` 返回 `undefined` = 「头部区无 `type:`」。**不**在此函数内做注册校验（校验是消费者的策略，两个消费者各有不同的拒绝文案：worker 用 `TOOL_ALLOWLISTS` 键集，PM 用 `DISPATCHABLE_TYPES`）——避免把 spec §5.3 里「运行期白名单 ≠ 派发期白名单」的差异塞进解析层。
- `TaskMeta.type` 保持 `string`（`worker-mode.ts:274-306` 接口不变）：`parseTaskMd` 内 `let taskType = readTaskType(content) ?? "default";`（替换 `:312` 与 `:332-334`）⇒ **零类型面改动**，`default` 由 `isRegisteredType`（`:107-109`）判否 ⇒ 与「非法值」合并成同一条 fail-closed 规则（RQ-4 §5.2 的「单值化」）。
- 不复用 `status-model.ts:1236` 的 `TASK_FM_LINE_RE` 做键文法：它是 `^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$` 且无行首锚（`line.trim()` 后才匹配），语义等价但归属 autopilot；`task-frontmatter.ts` 自带同一正则字面量并在注释里指名 `status-model.ts:1236`，由 §2.3 的一致性测试锁等价。

### 1.2 头部区边界算法（定稿伪代码）

```
extractTaskHeader(text):
  bom  = text.startsWith("\uFEFF")
  t    = bom ? text.slice(1) : text
  lines[i] = t.split("\n")[i].replace(/\r$/, "").trim()      # \r 显式剥（TS trim 也吃 \r，但 Python 侧必须显式）
  1) if lines[0] === "---":                                   # 只认第 1 行，避免 read-scope fixture 的裸 `---` 误判
       close = lines.indexOf("---", 1)                        # 首个闭合
       if close > 0: return {start:1, end:close-1, fenced:true, truncated:false}
       # 无闭合 ⇒ 落到 2)（不静默返回空：RQ-4 §5.1 第 2 步）
  2) blank = lines.indexOf("")
     if blank >= 0: return {start:0, end:blank-1, fenced:false, truncated:false}
  3) k = 0; while k < lines.length and (HEADER_KEY_RE.test(lines[k]) or /^-\s/.test(lines[k])): k++
     return {start:0, end:k-1, fenced:false, truncated:true}
HEADER_KEY_RE = /^[A-Za-z_][A-Za-z0-9_-]*:/
readTaskHeaderScalar(text, key): 头部区 [start..end] 内第一个 trim 后以 `${key}:` 开头的行 ⇒ slice(len(key)+1).trim()
```

**逐条理由**
- **fence 只认第 1 行**：`test/suite/autopilot-read-scope.test.ts:378` 的 fixture 是裸头部 + 头部内一行裸 `---`（`"type: verifier\nread_scope:\n---\n\nwork\n"`），「出现 `---` 就当 fence」会误判边界。第 1 行判定下该 fixture 的 `type` 仍为 `verifier`（本报告规则实测：start=0,end=2）。
- **首个空行**：与框架自己的锚点同义 —— `applyWriteSurfaceContract`（`ui-bridge.ts:1507`）用 `cleaned.search(/\n\s*\n/)` 定位 leading frontmatter block；`paths/` 生产者（`ui-bridge.ts:1148+1563` 的 `${frontmatter}\n${body}\n`、`dispatch.py:347-374` 的 `["---",...,"---","",prompt,""]`）都保证头部与正文之间有空行。
- **无空行退化只用头部键文法**：现存 0 例（§0.2 E-2），且「绝不把整个文件当头部」（首行不匹配则 `start=0,end=-1` ⇒ 无 `type:` ⇒ fail-closed）。文法允许缩进块项 `^\s*-\s` 是为了 `read_scope:`/`deny_globs:` 块列表尾随不空行时不把列表项切出头部。
- **BOM**：TS 侧 `trim()` 已覆盖，但算法显式 `slice(1)` 并回填 `byteOrderMark` 供审计；Python 侧 `str.strip()` **不**吃 `\uFEFF`，必须显式 `lstrip("\ufeff")`（§0.2 E-1 是这条的代价证明）。
- **CRLF**：逐行 `replace(/\r$/,"")`（Python `str.split("\n")` + `strip()`）。

### 1.3 `type:` 取值规则（定稿）

1. **首个命中胜出**（消除 last-wins 的自我翻转面）；头部区内第 2 个及以后的 `type:` ⇒ 记录 `dupType` 标志，取值仍取首个（存量 0 例；写侧两处生产者恒写一行：`ui-bridge.ts:1145`、`dispatch.py:347`）。
2. 值处理 = `trim()`（顺带吃 `\r`）；**不做大小写归一、不做引号剥离、不把 `type : x` 当命中**（`anomalous_type_lines=[]` 实测 0 例；`type :` 将落「缺失」⇒ fail-closed，是安全方向）。
3. **头部区缺失/非法 ⇒ 不读正文**（单值化，§3）。

### 1.4 正文 `type:` 的处置（定稿：能力升级才拒绝，其余审计）

**判定（两层，同一谓词）**

```
# powerT(t) = activeToolsForType(t) ∩ {write, edit, bash}
escalation(bodyType, headerType) := exists p ∈ powerT(bodyType) : p ∉ powerT(headerType)
```

未注册的 `bodyType` ⇒ `activeToolsForType` 落 `fallback`（`worker-mode.ts:111-113`，含 write/edit/bash）⇒ 自动算升级。

**层 1（PM，零副作用，主防线）**：`dispatch_worker` 工具（`ui-bridge.ts:1733` 之后、`:1741` 的 writeless 判定之前）与 `/worker`（`:2167` 之后、`:2197` 之前）各加一次 `findTypeEscalation(scanBodyTypeLines(description), typeField, activeToolsForType)`；命中 ⇒ 拒绝派发，**在任何 mkdir/task.md/队列行之前**，文案带稳定 code（新增 `export const ROLE_ESCALATION_BLOCKED = "role-escalation-blocked"`，放 `ui-bridge.ts:223` 的 `CROSS_KEY_READ_ONLY` 同族位置），并给出修复指引（把该行删掉 / 用 `--type` 声明；正文里的示例文本请用反引号或代码块包裹，`collectWriteIntentHits` 已证明正则会被围栏去掉）。理由：`description` 是**业务文本**，PM 是它的作者，在写入前拒绝的代价 = 0（无 taskDir、无队列行、无 worker 启动）；而 worker 启动期拒绝的代价 = 一条 failed 行 + 一次 loop budget 升级。
**层 2（worker，防御手工书，`dispatchRefusal` 内）**：`worker-mode.ts:544-557` 增加同一谓词（输入 = `scanBodyTypeLines` 于 task.md 正文区、`meta.type` 于头部区）；命中 ⇒ 走既有 fail-closed 出口（`:1222-1236`：`writeOutput` exit 1 + `finishRun("failed",1)` + `writeWorkerLogLine` 带同一 code）。理由：launcher 只信 Python 侧；手工书/越权生产者不经 PM。
**审计（非升级的正文 `type:` 行）**：worker 启动 `parseTaskMd` 之后（`:1184` 后）写一条 trace 行，格式与 `appendStartPidLine`（`:526-538`）/`appendReadScopeTraceLine`（`:572-588`）同族，新增 `appendHeaderTraceLine(taskKey, agenticdocRoot, line)`：

```
[HEADER] body-type-ignored count=<n> lines=3 values=review escaped=false role=coding
[HEADER] dup-type-ignored lines=1,3 value=review role=coding      # 头部重复键（表头第二行）时
[HEADER] BOM detected                                          # byteOrderMark=true 时（一次性、可见化 E-1 类问题）
```

`escaped=true` 表示该行**会**升级（此时已被层 2 拒绝，行仅作证据）；`count` 最多列 4 组 `lines=`/`values=`，超出只报 count。

**为什么不是「一律拒绝正文 `type:`」**：存量 4 本有正文 `type:` 行、其中 3 本与头部同值（`ga-spec-design-review-2`、`mwppe-quality-gate`、`smoke-tree-kill-1`）⇒ 一律拒绝会新增 3 个纯误拦（且未来任何讨论本特性的任务书都会自撞：本 DRQ 的任务书正文里就有以反引号包裹的 `type:`）。**为什么不是「纯审计」**：A8 的攻击方向是**升权**（正文写 `type: coding` 去拿 write/edit/bash），纯审计会让攻击在 trace 里留痕但仍需人工发现；升级谓词把「唯一有危害的方向」变成硬拒绝，成本 0（§0.2：0 本存量触发）。

### 1.5 `parseTaskMd` 接入点（逐行）

| 行 | 现状 | 改为 |
|---|---|---|
| `worker-mode.ts:309` | `const content = fs.readFileSync(taskPath, "utf8");` | 不变（`readTaskType` 吃 text） |
| `:310` | `const lines = content.split("\n");` | 不变（其余头部键仍走全行扫描，见 §8 边界） |
| `:312` | `let taskType = "default";` | `const headerType = readTaskType(content);`（后面 `:454` 回填处 `type: headerType ?? "default"`） |
| `:332-334` | `if (trimmed.startsWith("type:")) { taskType = trimmed.slice(5).trim(); }` | **删除**（唯一 last-wins 点） |
| `:544-557`（`dispatchRefusal`） | `if (meta.origin !== "conductor") return undefined;` 后判 `isRegisteredType` | 升级检查 + 正文升级检查移到 `origin` 门**之前**；`verifier` + 空 `read_scope` 的检查**保持** conductor-only（`autopilot-protocol.test.ts:367` 锁定 manual verifier 可运行） |
| `:1184` 之后 | — | 新增 `appendHeaderTraceLine(...)`（正文 `type:` 行 / 头部重复 / BOM） |

### 1.6 Python 侧同语义副本（定稿）

`packages/multi-workers/mw_common.py` 新增（与 `worker_mode` 同文件族，`launcher.py`/`mw.py` 都已 `import mw_common`）：

```python
def read_task_header_region(text: str) -> tuple[list[str], dict]:   # (头部区行(已 strip), flags)
def read_task_type(text: str) -> str:                                # 头部区首个 type 的值；缺失 → ""
def scan_body_type_lines(text: str) -> list[tuple[int, str]]         # (1-based 行号, 值)
```

规则与 §1.2/§1.3 **逐字同语义**（含 BOM 显式剥、CRLF、首个胜出、退化文法）；`launcher.py:143-158` 的 `_read_task_md_fields` 改为 `(mw_common.read_task_type(text), model 同现有正则)`，`mw.py:1788-1800` 的 `_rag_task_meta` 改为 `mw_common.read_task_type`。**Python 侧不实现升级拒绝**（worker 侧是权威；PM 侧在第 1 层已拦），只在 §2.3 的差分测试里用 `scan_body_type_lines` 参与 golden 期望比对——把「同语义」变成可测事实而不是注释。

## 2. 6 份解析器收敛/桥接矩阵

### 2.1 矩阵（逐份「改成什么 / 保持什么 / 如何证明同语义」）

| # | 位置 | 现状算法 | 定稿处置 | 共享方式 | 证明 |
|---|---|---|---|---|---|
| P1 | `worker/worker-mode.ts:308-334`（`parseTaskMd`） | 全文逐行 `startsWith("type:")`，**last-wins**，缺省 `"default"` | 改 = `readTaskType(content) ?? "default"`；删 `:332-334`；其余头部键暂不变 | **物理共享**（import `shared/task-frontmatter.ts`） | `mwgf-t14` 注入反例 + §0.2 E-3 的 308 本 delta=1 |
| P2 | `pm/task-dispatcher.ts:115-118`（`parseRagTaskMeta`） | `^type:[ \t]*(.+?)[ \t]*$` /m **first-wins、全文** | 改 = `type: readTaskType(content)`；`phase` 同批改 `readTaskHeaderScalar(content,"phase")`（同一种「正文可注入头部键」的洞，零额外风险，存量正文 `phase:` 0 例） | **物理共享** | `agent-team-loop-profile-injection.test.ts` 回归 + §2.3 golden |
| P3 | `autopilot/status-model.ts:1236-1253`（`parseTaskLabels`） | 仅首行 `---` 时读 fence 内，重复键 last-wins | **保持 fenced-only 语义**；改 = fence 定位复用 `extractTaskHeader`（`region.fenced === true` 才解析），键文法沿用同一 `HEADER_KEY_RE` | **物理共享（仅边界提取）** | 一致性测试：仓库内全部 task.md 上 `parseTaskLabels(f).get("type")` ∈ {`undefined`, `readTaskType(f)`}；fenced fixture 组（`autopilot-console.test.ts:278-286`、`:553-564`）保持绿 |
| P4 | `packages/multi-workers/launcher.py:143-158`（`_read_task_md_fields`） | `^type:[ \t]*(\S+)[ \t\r]*$` /m **first-wins、全文、不剥 BOM** | 改 = `mw_common.read_task_type(content)`（`model:` 保持现正则） | **同语义副本**（同语义 + 差分测试） | §2.3 golden + `test_launcher.py` 回归 + BOM 反例（E-1） |
| P5 | `packages/multi-workers/mw.py:1788-1800`（`_rag_task_meta`） | 逐行 `line.strip().startswith("type:")`，**first-wins、全文** | 改 = `mw_common.read_task_type`（`phase` 同批） | **同语义副本** | §2.3 golden + `test_rag_audit.py` 回归 |
| P6 | `test/suite/mwds-t02-write-intent.test.ts:94-96`（`corpusType`） | `^type:\s*(\S+)\s*$` /m first-wins | 改 = `readTaskType(text) ?? ""`（删本地正则） | **物理共享** | 该测试自己的语料回放断言不变（`FP==0` ∧ 唯一真阳 ⊆ 白名单）；VC-015 的 `books.length >= 24` 不因新算法变化 |

**角色映射表（不在 6 份之列但必须一起锁）**：TS `shared/dispatch-models.ts:58-69` `DISPATCH_ROLE_BY_TYPE` ↔ Python `mw_common.py:144-157` `TASK_TYPE_TO_ROLE` 已由 `test_dispatch_models.py:158` 差分锁定；本 key 只加一条：**golden 的 `expected_role` 由两侧各自的角色映射从 `type` 推出**，改一处映射必须让 §2.3 的 role 列两侧同变（把映射漂移也纳入同一测试）。

### 2.2 「派发期判据复用 worker 解析」的收口（AC-005 明文要求）

现状：PM 判定用**入参**（`resolveDispatchType`，`ui-bridge.ts:1065-1086`，白名单 `DISPATCHABLE_TYPES`，`shared/dispatch-models.ts:75`），worker 用 `parseTaskMd` 重解析文件，两侧只靠「写出的头部字符串」隐式契约对齐。定稿收口为**两条机器可测的等式**（不改 PM 的判定输入，避免把「入参」变成「已写文件」引发新的 TOCTOU）：

1. **回环等式**（unit）：对每个 `type ∈ DISPATCHABLE_TYPES`，`readTaskType(writeDispatchTaskMd(...).content) === type` —— 即用真正写出的字符串跑同一解析函数。实现方式：在测试里调 `planDispatchFrontmatter` + `writeDispatchTaskMd`（写 tmp）再 `readTaskType(fs.readFileSync(path,"utf8"))`；`writeDispatchTaskMd`（`:1539-1566`）是唯一写点，无需埋 hook。
2. **升级等式**（runtime，PM 侧）：`findTypeEscalation(scanBodyTypeLines(description), typeField, activeToolsForType) === undefined`，与 worker 侧 `dispatchRefusal` 的同一调用同参数关系（同一函数、同一 `activeToolsForType`）。
3. **可选加固（推荐但非必需，PM 决策）**：`writeDispatchTaskMd` 写盘后立即 `readTaskType` 复核一次，不一致 ⇒ 返回 `ok:false`（在 `:1565` 的 `writeFileSync` 之后、`dispatchTask` 之前；`writeDispatchTaskMd` 的返回类型需从 `{ok:true,...}` 改为 `{ok:true,...} | {ok:false,message}`，两个调用点 `:1785`/`:2244` 各加一个拒绝分支）。收益：把「写侧恒写一行 + 读侧首行胜出」变成运行时不变量；成本：每次派发多读一个 <2 KB 文件。**建议本轮不做**（回环等式已覆盖；避免动 `writeDispatchTaskMd` 的签名与 T-01/T-03 的字节断言测试），列为 DD-06 的可选加强。

### 2.3 golden fixture 设计（跨语言一致性测试）

**语料**：新文件 `packages/multi-workers/test/fixtures/task-md-header-cases.json`（与既有 `active-mode-table.json`、`autopilot-config-corpus.json` 同目录同形态）。**全部 case 用 base64 内联正文，不落 `.md` 文件** —— 理由：仓库 `.gitattributes` 是 `* text=auto eol=lf`，落盘的 CRLF 会被归一、BOM 也可能在编辑器往返中丢失，字节敏感 case 用 base64 才可复现。

```json
{ "version": 1,
  "cases": [
    {"id":"unfenced-single","content_b64":"...","expected":{"type":"coding","role":"coding","fenced":false,"truncated":false,"body_type_lines":[],"escalates":false}},
    {"id":"unfenced-multi-header", ... "type":"review", "phase":"SPEC", ...},
    {"id":"fenced","content":"---\ntype: research\norigin: conductor\n---\n\nwork\n", "fenced":true},
    {"id":"fenced-unclosed","content":"---\ntype: coding\n\nwork\n", "fenced":false,"truncated":false},
    {"id":"type-not-first","content":"origin: conductor\ntype: verifier\nread_scope:\n  - a\n\nwork\n", "type":"verifier"},
    {"id":"dup-type-in-header","content":"type: coding\nphase: SPEC\ntype: review\n\nwork\n", "type":"coding","dup_header_type":true},
    {"id":"body-equal","content":"type: coding\nmodel: x\n\ntype: coding\n", "type":"coding","body_type_lines":[{"line":4,"value":"coding"}],"escalates":false},
    {"id":"body-narrow","content":"type: coding\n\nwork\n\ntype: review\n", "escalates":false},
    {"id":"body-escalate","content":"type: review\n\nwork\n\ntype: coding\n", "type":"review","escalates":true},
    {"id":"body-escalate-unknown","content":"type: verifier\n\nwork\n\ntype: whatever\n", "escalates":true},
    {"id":"missing-type","content":"# title\n\nwork\n", "type":"","refused":true},
    {"id":"illegal-type","content":"type: mystery-type\n\nwork\n", "type":"mystery-type","refused":true},
    {"id":"near-miss-type-space","content":"type : coding\n\nwork\n", "type":"","refused":true},
    {"id":"bom","content_b64":"77u/dHlwZTogdmlzaW9uCgp3b3JrCg==", "type":"vision","bom":true},
    {"id":"crlf","content_b64":"dHlwZTogcmVwYWlyDQoNCndvcmsNCg==", "type":"repair"},
    {"id":"block-list-no-blank","content":"type: verifier\nread_scope:\n  - a\n  - b\n", "truncated":true},
    {"id":"prose-no-blank","content":"type: coding\nwork without blank line\n", "truncated":true},
    {"id":"empty","content":"", "type":"","refused":true}
  ] }
```

（`content` 与 `content_b64` 二选一；上面的 base64 是示意，落地时由生成脚本产出后人工复核。）

**测试落点（两侧，同一 JSON）**
- TS：`packages/coding-agent/test/suite/mwgf-t14-role-single-source.test.ts` —— 每条 case 断言 ① `readTaskType` == expected.type；② `extractTaskHeader` 的 `fenced`/`truncated` == expected；③ `roleForTaskType(parseTaskMd(tmpFile).type)` == expected.role（把 2 条 case 写成 tmp 文件走**路径入口**，证明 wrapper 委托）；④ `scanBodyTypeLines` 行号/值；⑤ `findTypeEscalation(..., activeToolsForType)` 的命中/不命中。
- Python：`packages/multi-workers/test_task_md_header_parity.py` —— 直接 `json.load` 同一文件，断言 `mw_common.read_task_type` / `scan_body_type_lines` 与 `expected` 一致，`expected.role` 用 `mw_common.TASK_TYPE_TO_ROLE`（未知/空 ⇒ `"coding"` 兜底，与 `mw_common.py:315` 同式）推出后比对。
- **反向差分（真跨语言相等）**：Python 测试内用 `subprocess.run([shutil.which("node"), "--experimental-strip-types", "-e", _TS_SCRIPT])` 跑真实 TS 模块（`shared/task-frontmatter.ts`）对同一 JSON 求 `(id,type,escalates)` 列表，与 Python 结果 `assert ts == py`。**范式照抄 `packages/multi-workers/test_autopilot_config_parity.py:40-51,66-69,218-256`**（含 `pytest.fail("node interpreter not found …")` 的 fail-closed 纪律，P-016；绝不 skip）。node 侧脚本用 `pathToFileURL` + `process.env.MW_TS_MODULE/MW_TS_CORPUS` 传参，`TS_JSON_BEGIN/END` 包裹输出。
- **禁止的断言**（P-08）：不得冻结 md5 / 不得 `cases.length <= N` / 不得对 305/308 这类增长量断上限。规则本身（`FP==0`、两侧相等、具名 case）才是判据。本报告 §0.2 的 `a12dc0a7...` 与 `delta=1` 只作**证据**，若 PM 想要一条运行期回归，写成「`mwgf-t14` 内断言 `review-mw-worker-tree-kill` 这本的 `readTaskType === "coding"`」的**具名**断言，不写成「count == 1」。
- **P3 的边界增量（必须登记）**：`parseTaskLabels` 复用 `extractTaskHeader` 后，**未闭合 fence** 的文件语义由「读到 EOF 的标签」变为「无标签」（`region.fenced=false` ⇒ 提前返回空 Map）。存量 0 例（E-2 `fenced=0`），但这是行为变化 ⇒ 在 `mwgf-t14` 里加 1 条 `fenced-unclosed` 的 P3 用例显式钉住新行为（防未来手写书静默丢标签）。

## 3. fail-closed 规则定稿（逐条判定 + 存量影响计数）

计数口径：**当前 308 本**（§0.1）；括号内给 spec 的冻结前值口径 305 本（RQ-4/PM），新增 3 本均为常规 `research` 书、不改变任何一条计数。

| # | 情况 | 现实现 | **定稿判定** | 稳定 code | 308 影响 | 305 影响 |
|---|---|---|---|---|---|---|
| F-1 | 头部区**无** `type:`（含整篇无 `type:`） | `"default"` → 未注册 → 无 origin 时放行且落 `fallback`（全工具集） | **拒绝**（所有 origin） | `unregistered-task-type` | **1**（`.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md`，已终态；今日以 `fallback` 全工具集运行） | 1 |
| F-2 | 头部区 `type:` **值非法/未注册**（含空串、`fallback`、`default`、`mystery-type`） | 仅 `origin: conductor` 拒绝（`worker-mode.ts:544-556`），manual 落 `fallback` | **拒绝**（所有 origin；`fallback`/`default` 视为未注册，与 `isRegisteredType` `:107-109` 一致） | `unregistered-task-type` | **0**（E-2：308 本头部值全部已注册） | 0 |
| F-3 | 头部区 `type:` 值带**大小写/空白差异**（`Coding`、` code `、`type: "coding"`） | `trim()` 后精确匹配 | **保持精确匹配 + trim，不做 case-fold**（RQ-4 §5.2 末条：case-fold 会造第二套键空间；`TASK_TYPE_TO_ROLE`/`isRegisteredType`/`DISPATCHABLE_TYPES` 全是精确键） | `unregistered-task-type` | **0**（`anomalous_type_lines=[]`） | 0 |
| F-4 | 头部**无 `---`**（unfenced） | 305/305 全是此形态 | **不是错误**：按 §1.2 的首个空行规则接受；只有「无空行」才退化到文法截断 | — | 308/308 全 unfenced ⇒ 若把它当错误就是全量误拦 | 305/305 |
| F-5 | 头部**无空行**（退化分支） | 不存在 | 头部 = 头部键文法前缀（`truncated=true` 写 `[HEADER]` 审计行）；首行不匹配文法 ⇒ 空头部 ⇒ 走 F-1 拒绝 | `unregistered-task-type`（若顺带缺 type） | **0**（`truncated=0`） | 0 |
| F-6 | fence **未闭合**（首行 `---` 无闭合） | P1 全文扫；P3 读到 EOF | **落到 unfenced 分支**（不静默返回空）；`fenced=false` 审计 | — | **0**（`fenced=0`） | 0 |
| F-7 | 头部区**重复** `type:` | last-wins | **首个胜出** + `[HEADER] dup-type-ignored` 审计；**不拒绝**（写侧恒写一行，重复只可能来自手工编辑；拒绝会与「首个胜出」的既有语义冲突且存量 0 例，审计已足够可见） | — | **0** | 0 |
| F-8 | 正文有 `type:` 行、值**不升级**（含与头部同值 / 降权） | 正文静默胜出（A8） | **不拒绝**，`[HEADER] body-type-ignored` 审计（§1.4） | — | **4 本**产生审计行（3 同值 + 1 降权） | 4 |
| F-9 | 正文有 `type:` 行、值**升级**（power-tool 非子集） | 正文静默胜出 = 攻击成功 | **拒绝**：PM 写入前（零副作用） + worker 启动（`role-escalation-blocked`） | `role-escalation-blocked` | **0** | 0 |
| F-10 | `type:` 缺失 + 正文有 `type:` | 正文胜出 | **不读正文**（F-1 已拒绝；单值化，杜绝「换个形状放行」） | `unregistered-task-type` | 0 | 0 |
| F-11 | `type:` 前有空格/非 ASCII 冒号（`type : x`、`type：x`） | 不匹配 ⇒ 不被当 `type:`（last-wins 下等价于缺失） | **不匹配 ⇒ 缺失 ⇒ F-1 拒绝**（安全方向；`near_miss_type_lines=0`） | `unregistered-task-type` | 0 | 0 |
| F-12 | 文件带 UTF-8 BOM | TS 读得到、Python 读不到（E-1） | 两侧显式剥 BOM；`byteOrderMark=true` 写一次性审计行 | — | **7**（Python 侧由空恢复为真值；TS 侧不变） | 7 |

**判定合并后的规则单值化（定稿一句话）**：`类型 = 头部区首个 type:（trim）`；`类型 ∉ TOOL_ALLOWLISTS 键集 \ {fallback}` ⇒ 拒绝，**不看 origin、不看正文**。

### 3.1 运行期白名单的确切集合（与 spec §5.3 一致，定稿）

`runtimeWhiteList = Object.keys(TOOL_ALLOWLISTS).filter(t => t !== "fallback")` = `{coding, review, research, roadmap-writer, phase-writer, verifier, reviewer, repair, rag-research, vision}`（10 个）。**不是** `DISPATCHABLE_TYPES`（后端会误杀 conductor 的 `phase-writer`/`repair`/`verifier`：`autopilot-protocol.test.ts:76-82` 的 `PY_REGISTRY` 与 `dispatch.py:71-108` 的 `REGISTRY` 都要求它们可运行）。`resolveDispatchType`（`ui-bridge.ts:1065-1086`）继续用 `DISPATCHABLE_TYPES` 管**入参**（PM 只派 5 类），两者关系：`DISPATCHABLE_TYPES ⊆ runtimeWhiteList`（实测：`coding/review/research/rag-research/vision` 全在 10 元集合内）。

### 3.2 拒绝出口与文案（定稿）

- worker 侧：复用 `dispatchRefusal` 通道（`:544-557` 返回串 → `:1222-1236` 写 `output.md` + `trace.log` + `worker.log`，`exit 1`，`finishRun("failed",1)`），文案模板：
  `Fail-closed (AC-005/DRQ-3): [<code>] task.md <no `type:` header | has type '<v>' with no tool-allowlist entry>. Registered types: <10 个排序清单>.` —— 已注册清单的拼装沿用 `:547-550` 的现写法（`Object.keys(TOOL_ALLOWLISTS).filter(t => t !== "fallback").sort()`）。
- PM 侧：升级拒绝用 `ROLE_ESCALATION_BLOCKED` + `writeIntentRefusal`/`crossKey` 同风格文案（含「该行请用反引号/代码块包裹」的指引），零副作用。
- 审计行：`[HEADER] ...`（§1.4），与 `[START]`/`[READ_SCOPE]`/`[TOOL_ERR]` 同族，落在同一 `trace.log`（唯一写入点 `appendStartPidLine` 同目录）。

### 3.3 F-1/F-2 的**契约代价**（PM 必须显式决策，不能只当作实现细节）

| 方案 | 判定 | 影响的既有断言/契约 | 存量影响 | 我的评价 |
|---|---|---|---|---|
| **(a) 全体 origin 一律拒绝（推荐）** | RQ-4 §5.2 + spec §5 Q3 默认 | `autopilot-protocol.test.ts:353-354`（`m-unknown` 期望 `PY_CODING_TOOLS`）与 `:362`（`expect(exitSpy).not.toHaveBeenCalled()`）必须改写为「m-unknown 被拒、其余三例不拒」；`agent-team-loop-checkpoint-wiring.test.ts:319-320` 只锁 `toolsForType`（**不受影响**，因为我不改 `TOOL_ALLOWLISTS`） | 1 本（F-1） | GC-8/T-13 的「manual 未知类型 = fallback 全工具集」被**退役**（收窄）；换掉一个「未注册即全权限」的隐藏升权面，方向与 AC-005 判据③一致 |
| (b) 保留 GC-8 manual fallback + 强制审计行 | 不改 :362 | 无 | 0 拒绝 | 留一条「缺失/非法 ≠ 拒绝」的放行路径（RQ-4 §5.2 明确反对：同一个洞换形状）；且 `type: mystery-type` 仍是全工具集 |
| (c) 未注册落**只读** bucket（改 `fallback` 表内容） | 不改 :362 | `autopilot-protocol.test.ts:354` + `agent-team-loop-checkpoint-wiring.test.ts:319-320`（`ALLOWLIST_SNAPSHOT.fallback` 冻结快照）都要改 | 0 拒绝，但 1 本从「全工具集」降为只读 | 需要动 `TOOL_ALLOWLISTS`（`worker-mode.ts:68-102`，Python parity 锁 + 直接 import 的测试面）⇒ 改动面最大、最容易触发 parity 红 |

**推荐 (a)**，并在 `design.md` 里把「GC-8 manual fallback 退役」写成一条明确决策（含上表两处测试改写），理由：规格 AC-005 判据③要求 fail-closed 有测试；`dispatch_worker` 与 conductor 两条写侧路径都恒写已注册类型（`ui-bridge.ts:1145`、`dispatch.py:347`）；能走到这里的手工书只有 1 本且已终态；方案 (a) 不需要碰 `TOOL_ALLOWLISTS`（Python parity 快照零风险）。**若 PM 判定「不动 GC-8」优先，则必须选 (b) 并把 `[HEADER] unregistered-type-fallback type=<v>` 审计行 + 「F-1/F-2 不 fail-closed」写进 spec §6 残留**——不能既不拒绝也不审计。

## 4. key 豁免清单定稿（AC-006）

### 4.1 保留名单（逐名 + 依据 `文件:行号`）

spec §3 AC-006 的「共 12 个由 RQ-5 列名」= 下表 **R-01…R-12**（RQ-5 §2.1 中「是否框架自有 = 是」的 12 名）。本次复核发现 **2 名漏项**（E-6），定稿集合是 **14 名**（R-13/R-14），并在 `design.md` 里把「12」更正为「14（含 2 名补正）」。

| # | 名字 | 类型 | 依据（`文件:行号`） | 处置 |
|---|---|---|---|---|
| R-01 | `_scratch` | dir | `shared/paths.ts:16` `SCRATCH_WORKERS_KEY = "_scratch"` | **唯一 owner-放行**（保留名里只有它可作为 ownerKey；`advance_phase` 仍拒，见 §4.3） |
| R-02 | `.mw` | dir | `shared/index-store.ts:60`（`<project>/.mw/index.lock`）；`mw_common.py:217`（`.mw/dispatch.yml`）；`mw_common.py:386`（`.mw/rag-servers.yml`） | 无条件拒绝 |
| R-03 | `_index.parallel` | file | `shared/index-store.ts:59`；`update_index.py:50` `INDEX_FILE` | 无条件拒绝 |
| R-04 | `_index.md` | file | `shared/index-store.ts:219`（读 `active:`）；`.agents/skills/agentic-task/SKILL.md:14`（degraded 指针定义） | 无条件拒绝 |
| R-05 | `_workers.parallel` | file | `mw_common.py:1580` `_workers_parallel_path`；`:1577` 段注释 | 无条件拒绝 |
| R-06 | `_workers.stale.parallel` | file | `mw_common.py:160` `STALE_FILE_NAME`；`:1584` | 无条件拒绝 |
| R-07 | `_workers.acked` | file | `mw_common.py:1587` `ACKED_FILE_NAME`；`:1591` | 无条件拒绝 |
| R-08 | `_autopilot` | dir | `mw_common.py:2552`（`_autopilot/config.json`）；`:2593` `_GATE_DIR_REL = (".agenticdoc","_autopilot","gates")`；`:1584` | 无条件拒绝 |
| R-09 | `_project_log.md` | file | `.agents/skills/agentic-task/scripts/advance_phase.py:28` `MEMORY_DOCS`；`:451` `log_path = root / "_project_log.md"` | 无条件拒绝 |
| R-10 | `_arch_snapshot.md` | file | `advance_phase.py:28` `MEMORY_DOCS` | 无条件拒绝 |
| R-11 | `_pitfalls.md` | file | `advance_phase.py:28` `MEMORY_DOCS`；`:86`（遗留去向文案） | 无条件拒绝 |
| R-12 | `.agenticdoc` | dir | `shared/paths.ts:10` `AGENTICDOC_DIR = ".agenticdoc"`；`:23` | 无条件拒绝（`key: .agenticdoc` 会在 `.agenticdoc/.agenticdoc/workers/` 下建目录） |
| R-13 | `_impl_gate.log` | file | `shared/implementation-gate.ts:69` `const GATE_LOG_FILE = "_impl_gate.log"`；`:732`（写入） | 无条件拒绝（**RQ-5 清单漏项**） |
| R-14 | `_incidents` | dir | 磁盘实测 `.agenticdoc/_incidents` 存在；`rg -F '_incidents' packages/coding-agent/src` **0 命中** ⇒ **非框架**（RQ-5 §2.1 标"否"），但已占根目录 | 无条件拒绝（**防止把既有目录当 key 命名空间**；理由：保留名的判据是「已占用根条目」，不是「框架代码引用过」） |

磁盘实测（`os.listdir('.agenticdoc')` 过滤 `_`/`.`）在锚点快照给出：`.mw, _arch_snapshot.md, _impl_gate.log, _index.md, _index.parallel, _pitfalls.md, _project_log.md, _scratch, _workers.acked, _workers.parallel, _workers.stale.parallel`（11 项；`_autopilot` 当前不存在、`_incidents` 存在）⇒ R-01…R-14 覆盖全部现存条目 + 3 个「当前不存在但框架会创建」的名字（`_autopilot`、`.agenticdoc`、`_workers.*`）。**明确不做「磁盘派生集合」**（理由见 §8）。

### 4.2 判据定稿（替换 `ui-bridge.ts:250` 的无条件前缀豁免）

新文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/key-identity.ts`（纯模块，只 import `./paths.ts` 的 `SCRATCH_WORKERS_KEY`；`pm/ui-bridge.ts` 与 `shared/index-store.ts` 都 import 它）：

```ts
export const RESERVED_INDEX_NAMES: readonly string[] = [ /* R-01…R-14，全部小写存储 */ ];
export const RESERVED_INDEX_NAME_SET: ReadonlySet<string>;       // 便于 O(1) 判定
export function normalizeKey(key: string): string;               // key.trim().toLowerCase()
export function isScratchKey(key: string): boolean;              // normalizeKey(key) === normalizeKey(SCRATCH_WORKERS_KEY)
/** 形态 + 保留名（大小写不敏感）。null = 通过。返回稳定 code：empty-key | key-path-escape |
 *  key-illegal-shape | reserved-key-name。 */
export function keyNameRefusal(key: string): { code: string; message: string } | null;
```

**形态文法（定稿）**：`^[A-Za-z0-9][A-Za-z0-9._-]*$`，且额外拒绝 ①前缀路径分隔符/盘符/UNC（`[/\\]`、`^[A-Za-z]:`）、②`.`/`..` 与任何尾随 `.`/空格（Windows 等价类）、③控制字符与 `:`（ADS 流）、④长度 > 64。**存量校验**（只读实测）：`_index.parallel` 的 52 行 key **全部通过**（唯一不通过的是 `-----` 分隔行，它已被 `index-store.ts:36-38` 过滤，不是 key）；308 个 worker task 目录名**全部通过**（`worker_task_dirs=308 violating=[]`）⇒ 该文法对存量零误拦。

**守卫逻辑（`foreignLiveClaimRefusal` 定稿，替换 `:247-262` 的函数体前三行）**

```
t = key.trim()
if (!t) return null                                  # 空 key 由调用方（required 校验）处理，不在此造新语义
if (isScratchKey(t)) return null                     # R-01：唯一 owner-放行（既有行为，测试 :240-248 锁）
shape = keyNameRefusal(t)
if (shape) return refusalText(shape.code, t)         # fail-closed，不看 claim（R-02..R-14 在此被拒）
row = indexStore.findByKey(t)                        # §5.1 后已大小写不敏感
claim = row?.claimId.trim() ?? ""
if (!claim) return null                              # 未在 _index.parallel 出现 ⇒ 新 key 引导路径
if (claimState(claim, windowClaimId()) !== "held-live") return null
return crossKeyText(t, claim)                        # 既有 [cross-key-read-only] 文案（含 3 个 surface）
```

**「未在 `_index.parallel` 出现 ⇒ 新 key 引导路径」的判据（定稿）**：判据是 **`findByKey(t) === undefined`**（任意 status、任意 claim，含 RQ-5 锚点的 9 行空 claim 行），**不是名字前缀、不是 status、不是 claim 是否为空**。理由：`ui-bridge.ts:241-243` 的注释把 bootstrap 定义成「写 spec.md → advance → dispatch」，而 `takeOverKey`（`:283-301`）走 `IndexStore.claim` 时对未索引 key 会 `created: true`；把判据挂在「行是否存在」上与 `claim` 的原子语义一致，且大小写归一后不会把 `mw-key` 的变体误当新 key。

### 4.3 `advance_phase` / `claim` / `/pm-key new` 的放行方向一致化（实现点逐个给）

| 落点 | 现状 | 定稿 | 说明 |
|---|---|---|---|
| `pm/ui-bridge.ts:2045-2053`（`advance_phase` 工具） | `trimmedKey.startsWith("_") \|\| startsWith(".")` ⇒ 拒**所有**前缀名（含 `_scratch`），文案「reserved prefix」 | 改为 `const r = keyNameRefusal(trimmedKey); if (r) return { message: r.code === "reserved-key-name" ? r.message : ... }`；`_scratch` 另给「not a phase-tracked key」的文案（`isScratchKey` 分支） | 与守卫共用**同一份**保留名单 + 同一 `keyNameRefusal`；方向变为「保留名一律拒 + `_scratch` 作为 owner 可派发但不可 advance」，三处语义不再互相矛盾 |
| `shared/index-store.ts::claim`（`:92-136`） | 无形态/保留校验 ⇒ `_tmp`/`../x` 可写成 active 行 | 在取锁**之后**、读 rows 之前 `const r = keyNameRefusal(key); if (r) return { ok:false, entry: {...占位, key}, created:false, refusal:r.code };` | TS 侧唯一 choke point；`ClaimOutcome` 新增可选 `refusal?: string`（可擦除 TS，无 `any`） |
| `pm/ui-bridge.ts:850-871`（`/pm-key new`） | 只查 `findByKey` 存在性 | 先 `keyNameRefusal(keyName)`（给出可读 warning），再由 `takeOverKey` → `claim` 兜底；`takeOverKey`（`:283-301`）把 `outcome.refusal` 映射成 `TakeoverResult.blockedBy`/新字段并在 `/pm-key` 与 `autoTakeOverFromDoc`（`pm-orchestrator.ts:236-256`）里 notify | `/pm-key new _index.parallel` 从「静默建行」变为「拒绝 + 解释」 |
| `.agents/skills/agentic-task/scripts/update_index.py:361-412`（`cmd_claim`） | 无形态/保留校验；`:368`/`:388`/`:391` 精确 `r["key"] == key`（大小写变体追加重复行） | 顶部加同一保留名单的 Python 常量（`RESERVED_INDEX_NAMES`，由 §2.3 的 golden/差分测试与 TS 侧互锁）+ 同一文法拒绝；三处比较改 `key.lower()` | Python 侧唯一 choke point；`claim _tmp` 从「置 active」变为「退出码非 0 + 说明」 |

**方向一致性判据（可机器度量）**：对 `RESERVED_INDEX_NAMES ∪ {"../x","_tmp"}` 每个名字，`foreignLiveClaimRefusal` 返回非 null **且** `keyNameRefusal` 返回非 null **且** `advance_phase` 的 key 校验拒绝 **且** `IndexStore.claim` 返回 `ok:false`；对 `_scratch`：guard 放行、`claim` 拒绝（不作为 key 建行）、`advance_phase` 拒绝（不是 phase-tracked）。用例名：`mwgf-t15-key-identity.test.ts` `"all 14 reserved names are refused by the guard, claim and advance_phase"`、`"_scratch is owner-exempt but never claimable or advanceable"`。

### 4.4 判别性前值（A5）

| 判据 | 前值（今日实测 E-4） | 目标 |
|---|---|---|
| `exempt_live_key`（`foreignLiveClaimRefusal(store,"_tmp")` 在他人 live 持有时是否 ALLOW） | 判据形态成立：`_tmp` 现在**恒** ALLOW（`row=null` 也一样，因为前缀在 `findByKey` 之前返回） | 活持有 `_tmp` ⇒ REFUSE（`reserved-key-name` 或 `cross-key-read-only`）；未索引且非保留名 ⇒ ALLOW |
| `reserved_name_owner_namespace_writes` | `key: "_index.parallel"` 会在 `.agenticdoc/_index.parallel/workers/…` 建目录（守卫放行） | 0（14 名全拒） |
| 语料假阳性（`_index.parallel` 前缀 key） | 0 行 | 仍 0（且 `_scratch` 派发路径保持不变：`mwds-t01-worker-guard.test.ts:240-248`） |
| 收窄 vs 放宽 | 现状 = **任意** `_`/`.` 名全放（含 `_tmp`、`.mw`） | 新 = 14 名全拒 + 其余按 claim 判 ⇒ **净收窄**，不含任何新增放行面（唯一放行仍是既有 `_scratch`） |

## 5. 大小写归一 + `_index.md` 回退定稿（A6/A7）

### 5.1 大小写归一（改哪几行、归一到什么形式）

**结论：比较键归一到 `key.trim().toLowerCase()`；存盘保留首写大小写（不做写面改写、不迁移存量行）。**

| 落点 | 现状 | 定稿改法 |
|---|---|---|
| `shared/index-store.ts:164-166` `findByKey` | `this.readAll().find((e) => e.key === key)` | `find((e) => normalizeKey(e.key) === normalizeKey(key))`（首个匹配行胜出） |
| `:73` `upsert` | `existing.findIndex((e) => e.key === entry.key)` | 归一比较；命中时写入 `{ ...entry, key: existing[idx].key }`（**保留已存行的大小写**，避免同一逻辑 key 的显示名抖动） |
| `:101` `claim` | `rows.findIndex((e) => e.key === key)` | 归一比较；命中时走既有 `{ ...existing, claimId: self, ... }` 分支（天然保留存储大小写），仅未命中才 `push({ key, ... })` |
| `:57-69` `parseIndexLine` / `:46-49` `serializeIndexLine` | 原样 | 不变（**不改写存量 `_index.parallel` 的任何一行**；`-----` 分隔行的过滤（`:36-38`）不变） |
| `:218-228` `readIndexMdActive` | 返回文件里的原样字符串 | 不变（显示大小写来自文件；所有**查找**已归一） |

**归一到 lowercase 的理由**：Windows 文件系统大小写不敏感（RQ-5 实测 `fs.existsSync(".agenticdoc/MW-CONSOLE-TITLE-CLOBBER")===true` 与混合大小写同样 true）⇒ `.agenticdoc/MW-KEY` 与 `.agenticdoc/mw-key` 是同一个物理目录，因此「键空间」也必须同构到小写；同时**不**做 `toUpperCase`（本仓全部存量 key 均为小写风格，`_index.parallel` 52 行 `case_only_dups=[]`）。**为什么还必须配合写入侧**：若只改 `findByKey`，`claim("MW-KEY")` 会因 `:101` 未命中而 **push 第二行**（RQ-5 §1 A6 的「更糟」分支），此后 `findByKey` 取首个、`activeEntry` 取最新 ⇒ 两处读到不同 claim。三处必须同批改（同一张卡，同一文件）。

**大小写变体的可见性**：`claim` 命中「仅大小写不同的既有行」时，`ClaimOutcome` 增加可选 `caseVariantOf?: string`（= 存储侧原名），`takeOverKey`（`:283-301`）把它转成 `audit` 里的一行 `[KEY] case-variant 'MW-KEY' -> stored 'mw-key'`，使 `/pm-key switch MW-KEY` 不再静默；不命中则不产生该字段。

**判据（可机器度量）**：`case_mismatch_bypass == 0`（`MW-KEY` 与磁盘 `mw-key` 同判）；`case_only_dup_rows == 0`（`claim("MW-KEY")` 后 `readAll().filter(r => normalizeKey(r.key) === "mw-key").length === 1`）；语料不恶化（`case_only_dups=[]` 前值 0）。**残留（登记，不在本 key 修）**：`ownerKeyOf`（`ui-bridge.ts:339-342`）与 `mw_common.row_belongs_to`（`mw_common.py:1889-1901`）用原样字符串比较，`list_tasks`/`ack` 的 scope 匹配在「watch 名与行名仅差大小写」时可能不匹配 ⇒ 属读侧可见性、不构成写面漏放，记入 `design.md` §8 残留。

### 5.2 `_index.md` 回退路径（A7）：**必须补 claim 检查 + 保留名/形态检查**

**结论：回退也要过 claim 检查（并在同一分支过 `keyNameRefusal`），失败即降级 `_scratch` + 告警。** 理由：
1. RQ-5 §4.3 明确「修复应在守卫侧，不应假设 [`activeEntry()===undefined`] 不会出现」；今日锚点快照恰好满足该前置（E-4：`activeEntry=undefined`、`_index.md active=xkey-repair-mechanism`、该 key 持 live claim、`docGaps=[]`）⇒ 若不修，隐式派发会写进他人命名空间（`.agenticdoc/xkey-repair-mechanism/workers/`）。
2. `_index.md` 的 `active:` 行**没有 claim 字段**，唯一可信的 liveness 源是 `_index.parallel` 的行 ⇒ 回退分支必须回到 `findByKey` + `claimState`，与上方 `:77-81` 的 `activeEntry` 分支**同构**（同一原语、同一降级动作、同一 `warnForeignActiveOnce` 文案，`:106-117`）。
3. 保留名/形态检查同批做：否则 `_index.md active: _index.parallel`（手改或旧脚本产物）会变成 ownerKey。

**`ui-bridge.ts:77-84` 定稿（替换现有 6 行）**

```ts
const active = indexStore.activeEntry();
if (active && claimState(active.claimId, self) === "held-live") {
    warnForeignActiveOnce(pi, active.key);
    return SCRATCH_WORKERS_KEY;
}
const fallbackKey = active?.key ?? readIndexMdActive(agenticdocRoot);
if (fallbackKey) {
    const shape = keyNameRefusal(fallbackKey);              // 保留名/形态（8.2 后的 _index.md 通道）
    if (!shape) {
        const row = indexStore.findByKey(fallbackKey);      // §5.1 后归一
        if (row && claimState(row.claimId, self) === "held-live") {
            warnForeignActiveOnce(pi, fallbackKey);          // 与 :77-81 同一降级语义 + 同一告警
            return SCRATCH_WORKERS_KEY;
        }
        if (watch.key && watch.key !== fallbackKey) warnOwnerMismatchOnce(pi, watch.key, fallbackKey);
        return fallbackKey;
    }
    warnForeignActiveOnce(pi, fallbackKey);
    return SCRATCH_WORKERS_KEY;
}
if (watch.key) warnOwnerMismatchOnce(pi, watch.key, SCRATCH_WORKERS_KEY);
return SCRATCH_WORKERS_KEY;
```

**`dispatch_worker` 守卫的 `if` 条件（`ui-bridge.ts:1676`）**：**去掉 `if ((key ?? "").trim())`，改为无条件调用**（与 `/worker` `:2188` 同构 = AC-006 的「方向一致」）。论证：修好 `:82` 后隐式分支的 ownerKey 只可能是 `_scratch`（放行）、本窗口自己的 key、或未索引的新 key ⇒ 无条件调用**不会**产生新拒绝；而它把「工具面唯一闸口」从「只挡显式 key」升级为「挡所有写入」。**实现注意（否则会撞既有断言）**：
- 语义等价改写：`const refusal = foreignLiveClaimRefusal(indexStore, ownerKey); if (refusal) return {...}`（**不再**用 `if ((key ?? "").trim())` 包裹）。`mwds-t01-worker-guard.test.ts:269-272` 断言的是 `foreignLiveClaimRefusal(` 出现的**行数 = 3**（`:1677`/`:2188`/`:2058`），本改动**保持 3 行**（同一行去掉外层 if）⇒ 断言不变。
- **不得**在 `resolveOwnerKeyWithSync` 里调用 `foreignLiveClaimRefusal`（会变成第 4 行 ⇒ VC-011 变红）；回退降级只用 `claimState`（§5.2 代码块已按此写）。
- 拒绝文案改造（可选）：把 `:255-262` 的「Pass an explicit key, or switch_key…」保留；隐式分支经 `:82` 不可能命中，故文案无需为隐式路径另写一段。

**判据**：`implicit_foreign_owner_writes == 0`（构造成员：`activeEntry()===undefined` + `_index.md active:` 指向 live claim 的 key + 无 watch key + 无显式 `key` ⇒ 期望 `ownerKey === "_scratch"` 且 `_index.md` 指向的 key 目录**零新增**）；`fallback_live_degrades == 1`（同一构造下告警文本含该 key）；`fallback_reserved_degrades == 1`（构造 `_index.md active: _index.parallel` ⇒ `_scratch`）。用例名见 §7-B3。

## 6. 改动面与串行链

### 6.1 逐文件改动清单

| 文件 | 类型 | 改动点（`文件:行号`） | 归属 AC | 备注 |
|---|---|---|---|---|
| `shared/task-frontmatter.ts` | **新增** | `extractTaskHeader` / `readTaskHeaderScalar` / `readTaskType` / `scanBodyTypeLines` / `findTypeEscalation` | AC-005 | 纯函数，零依赖；唯一读侧单源 |
| `shared/key-identity.ts` | **新增** | `RESERVED_INDEX_NAMES`(14) / `normalizeKey` / `isScratchKey` / `keyNameRefusal` / `taskKeyNameRefusal` | AC-006 | 只 import `./paths.ts` |
| `worker/worker-mode.ts` | 改 | `:312`、`:332-334`、`:454`（type 单源）；`:544-557`（门后移 + 正文升级拒绝）；`:526-538` 附近新增 `appendHeaderTraceLine`；`:1184` 后调用审计 | AC-005 | `:68-102` `TOOL_ALLOWLISTS`、`:107-135` 能力函数**逐字节不变**（parity 锁 + 直接 import 的测试面） |
| `pm/ui-bridge.ts` | 改 | `:77-84`（回退 claim/保留名检查）；`:247-262`（前缀豁免→显式名单，新增文案）；`:1676-1679`（去 `if`，无条件守卫）；`:1733-1741` 与 `:2167-2197`（升级拒绝）；`:2045-2053`（改用 `keyNameRefusal`）；新增 `ROLE_ESCALATION_BLOCKED` 常量（放 `:223` 同族） | AC-005/AC-006 | 唯一 `task.md` 写点（`:1539`/`:1565`）与 `CROSS_KEY_READ_ONLY_SURFACES`（`:231`）不变 |
| `shared/index-store.ts` | 改 | `:73`/`:101`/`:164-166` 归一比较；`claim`/`upsert` 内 `keyNameRefusal`；`ClaimOutcome` 加 `refusal?`/`caseVariantOf?` | AC-006 | 不做存量行迁移；`-----` 过滤不变 |
| `pm/task-dispatcher.ts` | 改 | `:115-118`（`type`/`phase` 走共享读） | AC-005 | RAG 块资格判定与 worker 同步 |
| `autopilot/status-model.ts` | 改 | `:1237-1258`（fence 定位复用 `extractTaskHeader`，fenced-only 语义不变） | AC-005 | 未闭合 fence 语义变化须登记（§2.3 末） |
| `pm/pm-orchestrator.ts` | 改 | `:236-256`（把 `claim` 的 `refusal`/case 审计转成 notify） | AC-006 | 可选（不做则 `claim` 的拒绝只在 `/pm-key` 路径可见） |
| `packages/multi-workers/mw_common.py` | 改 | 新增 `read_task_header_region`/`read_task_type`/`scan_body_type_lines`/`RESERVED_INDEX_NAMES`/`key_name_refusal` | AC-005/AC-006 | Python 侧单一实现 |
| `packages/multi-workers/launcher.py` | 改 | `:143-158`（`_read_task_md_fields` 的 type 走共享读；`model` 保持原正则） | AC-005 | 修复 E-1（7 本 BOM） |
| `packages/multi-workers/mw.py` | 改 | `:1788-1800`（`_rag_task_meta`） | AC-005 | 同上 |
| `.agents/skills/agentic-task/scripts/update_index.py` | 改 | `:361-412`（形态/保留名拒绝）；`:368`/`:388`/`:391` 改 `key.lower()` 比较 | AC-006 | Python 侧 choke point |
| `packages/multi-workers/test/fixtures/task-md-header-cases.json` | **新增** | golden 语料（§2.3，18 条 case，base64 内联） | AC-005 | 不落 `.md`，规避 `.gitattributes` 归一 |
| `packages/multi-workers/test_task_md_header_parity.py` | **新增** | Python 半边 + node 反向差分（照抄 `test_autopilot_config_parity.py` 范式） | AC-005 | node 缺失 = `pytest.fail`（P-016） |
| `test/suite/mwgf-t14-role-single-source.test.ts` | **新增** | golden + 回环等式 + 升级拒绝 + 具名翻转书 + P3 未闭合 fence | AC-005 | VC-020…023 |
| `test/suite/mwgf-t15-key-identity.test.ts` | **新增** | A5/A6/A7 + 保留名单 + 形态穿越 + `claim` 方向一致 | AC-006 | VC-024…028 |
| `test/suite/mwds-t01-worker-guard.test.ts` | 改（只增） | 在现有 3 个 `describe` 后追加 A5/A6/A7 用例 | AC-006 | **不得**改动 `:269-272` 的 `guardSites.length === 3` 断言（守卫调用行数保持 3） |
| `test/suite/mwds-t02-write-intent.test.ts` | 改 | `:94-96` `corpusType` 改共享读 | AC-005(P6) | 断言（`FP==0`、唯一真阳）不变 |
| `test/suite/autopilot-protocol.test.ts` | 改（**仅当选 (a)**） | `:353-354`、`:362` 断言改写 | AC-005(F-1) | §3.3 代价登记；选 (b) 则不改 |

### 6.2 串行链（同文件冻结）

| 链 | 顺序 | 理由 / 冻结规则 |
|---|---|---|
| **S3-0** | `shared/task-frontmatter.ts` + `shared/key-identity.ts`（新建，一张卡） | 无依赖方；完成后才允许改消费者 |
| **S3-1** | `shared/index-store.ts`（A6 归一 + claim 拒绝） | 依赖 S3-0 的 `keyNameRefusal`；本卡独占 `index-store.ts` |
| **S3-2** | `worker/worker-mode.ts`（AC-005 worker 侧：`parseTaskMd` + `dispatchRefusal` + `[HEADER]` 审计） | 依赖 S3-0；**本卡独占 `worker-mode.ts`**（S3-3 只 import 其能力函数，不得编辑该文件） |
| **S3-3a** | `pm/ui-bridge.ts` 的 AC-005 部分（`:1733-1741`、`:2167-2197` 升级拒绝 + `ROLE_ESCALATION_BLOCKED`） | 满足 design.md §5「AC-005 → AC-006」串行语义；与 S3-3b 同文件 ⇒ **必须串行** |
| **S3-3b** | `pm/ui-bridge.ts` 的 AC-006 部分（`:77-84`、`:247-262`、`:1676-1679`、`:2045-2053`） | 依赖 S3-1；**本卡独占 `ui-bridge.ts`**（同文件内含 3 个 guard 调用点，禁止与 S3-3a 并发） |
| **S3-4** | `pm/task-dispatcher.ts` + `autopilot/status-model.ts` + `pm/pm-orchestrator.ts`（不同文件，可并行或一张卡） | 依赖 S3-0/S3-1；三者互不重叠 |
| **S3-5** | Python：`mw_common.py` →（`launcher.py` / `mw.py` / `update_index.py`）+ fixture + `test_task_md_header_parity.py` | 依赖 S3-0 的算法定稿（可早于 S3-3，但**不得**与任何 TS 卡同文件；`update_index.py` 与 TS 卡零重叠） |
| **S3-6** | TS 测试卡（`mwgf-t14`、`mwgf-t15`、`mwds-t01` 追加、`mwds-t02` 改） | 依赖全部 src 卡；`autopilot-protocol.test.ts` 只在选 (a) 时改，且与 S3-6 同批 |

**并发安全判据**：任一时刻 `git status --porcelain` 里被本 key 打开的 `worker-mode.ts`/`ui-bridge.ts`/`index-store.ts`/`mw_common.py` 各**至多 1 张卡**（前 key D-023 的 transient 假红教训；`spec.md` P-07）。

### 6.3 验证计划（PM 执行；本 DRQ 不跑）

1. 单卡：`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgf-t14-role-single-source.test.ts test/suite/mwgf-t15-key-identity.test.ts`（包内）；Python：`cd packages/multi-workers && python -m pytest -q test_task_md_header_parity.py`。
2. 回归面（`design.md` §7）：`mwds-t01…t12`、`autopilot-*`、`agent-team-loop*`、`worker-run-identity`、`checkpoint-wiring`；Python `test_launcher.py`、`test_dispatch_models.py`、`test_rag_audit.py`、`test_common.py`。
3. 全量：`npm run check`（PM）。
4. 语料复测（机器判据，不看上限）：① `readTaskType` 在 308 本上的 `flip` 集合 == `{review-mw-worker-tree-kill}`；② 两侧 golden 差分 `ts == py`；③ 守卫对 `RESERVED_INDEX_NAMES` 的 14 名 + `_tmp` + `../x` 全拒；④ `case_mismatch_bypass == 0`；⑤ `implicit_foreign_owner_writes == 0`。
5. 运行期生效口径（`spec.md` P-10）：以上全部是**源码/测试级**；`mw build --install` 前不生效，收口时按前 key D-026 的口径写 `achieved.md` 残留节。

## 7. 本域归属的未覆盖分支清单（QG-B ⑤ 的 14 条中属本域）

分工判定：QG-B ⑤-1…5 归 DRQ-1（`worker-mode.ts` 的 shell 提取/判据）、⑤-14 归 DRQ-2（`ui-bridge.ts:1345-1346/:1402-1404` 的写意图轴）、⑤-9/10/11/12 属交付判据/conductor/面板（本 key 其他 AC）。**本 DRQ 认领 4 条**：

| # | QG-B 坐标（当前行号） | 形态 | 归属 | 用例名（建议文件） | 断言要点 |
|---|---|---|---|---|---|
| B1 | `worker-mode.ts:332-334`（现 last-wins 点，本设计删除）+ `:386-411`（`write_scope:` 正文注入） | A8：正文行覆盖 frontmatter（`type:` 翻角色；`write_scope:` 空值/加宽 DoS） | DRQ-3（`type:` 部分） | `mwgf-t14-role-single-source.test.ts`：`"body `type:` line cannot change the role (named corpus file review-mw-worker-tree-kill: review -> coding)"`；`"body `type:` that escalates write capability is refused (PM pre-write + worker startup)"` | ① 具名文件 `readTaskType === "coding"` 且 `activeToolsForType("coding")` 含 write/edit/bash；② `dispatch_worker{type:"review", description:"...\ntype: coding\n"}` 零副作用（无 taskDir/无队列行，`snapshotTree` 字节相等，沿用 `mwds-t01:134-160` 的快照法）；③ worker 侧 `dispatchRefusal` 命中 `role-escalation-blocked`；④ 非升级（正文 `review`）⇒ 不拒绝 + `trace.log` 含 `[HEADER] body-type-ignored` |
| B1b | `worker-mode.ts:386-411`（`write_scope:` 空值 DoS） | 同族：正文 `write_scope:` 行被全文扫描吃进（空值 ⇒ `writeScope=[]` ⇒ bash 写面被收死，worker 无法写自己的 taskDir） | **边界登记**（见 §8.1） | `mwgf-t14-role-single-source.test.ts`：`"documented boundary: body `write_scope:` still wins (pin current semantics until the header-region card lands)"` | 钉住**现状**：`parseTaskMd(bodyWithWriteScope).writeScope === []`（DoS 仍可复现）⇒ 该分支被测试覆盖，但修复决策（全键走头部区，代价见 §8.1）留给 PM；**不得**把它当成已修 |
| B2 | `ui-bridge.ts:250`（前缀豁免）+ `shared/paths.ts:37-39`（key/taskKey 形态零校验） | A5：`_`/`.` 活外键 + `../` 穿越 | DRQ-3 | `mwgf-t15-key-identity.test.ts`：`"a live `_tmp` key is refused (exempt_live_key == 0)"`；`"all 14 reserved names are refused (guard + claim + advance_phase)"`；`"key shape refusal blocks `../x` / `C:x` / `a/b` / trailing dot or space"`；`"task_key shape refusal blocks `../x` before mkdir"` | ① 用「他人 live claim」夹具（`mwds-t01:100-120` 的 `writeForeignClaim` 同法）持 `_tmp`/`_index.parallel`/`.mw` ⇒ `foreignLiveClaimRefusal` 非 null；② `_scratch` 仍放行（`:240-248` 保持绿）；③ `workerTaskDir` 不被调用出 `.agenticdoc` 之外（断言 `path.resolve(taskDir).startsWith(resolve(root))`，并在 `writeDispatchTaskMd` 处先拒） |
| B3 | `ui-bridge.ts:82`（`readIndexMdActive` 隐式兜底不经守卫） | A7 | DRQ-3 | `mwgf-t15-key-identity.test.ts`：`"`_index.md` fallback to a held-live key degrades to _scratch with zero writes"`；`"`_index.md` fallback naming a reserved name degrades to _scratch"`；`"implicit dispatch_worker with no active row creates nothing under the _index.md key"` | ① 构造 `activeEntry()===undefined` + `_index.md active: <live foreign key>`（今日快照即此形）⇒ `resolveOwnerKeyWithSync(...,{key:undefined}) === "_scratch"` 且告警文本含该 key；② `.agenticdoc/<foreignKey>/workers` 不存在（`fs.existsSync === false`）+ `_workers.parallel` 无新行；③ 保留名回退同样降级；④ 该 key 的 `dispatchDocGaps` 不再被用来放行 |
| B4 | `index-store.ts:164-166`（`findByKey` 精确匹配；`:73`/`:101` 同族） | A6：Windows 大小写变体 | DRQ-3 | `mwgf-t15-key-identity.test.ts`：`"case-variant key resolves to the same row (findByKey + guard)"`；`"claim('MW-KEY') does not append a second row (case_only_dup_rows == 0)"`；`"upsert preserves the stored key casing"` | ① `findByKey("MW-KEY")` 返回 `mw-key` 行、守卫 REFUSE；② `claim` 后 `readAll().filter(r => normalizeKey(r.key) === "mw-key").length === 1` 且 `claimId` 更新到该行；③ `activeEntry` 与守卫读到同一行（`findByKey(row.key).claimId === activeEntry().claimId`） |

## 8. 不做什么（被否决路径 + 边界）

### 8.1 不大规模重构 6 份解析器（边界定稿）

**做什么**：把 `type:`（P1/P2/P4/P5/P6）与 `phase:`（P2/P5）收敛到共享函数；把 **fence/头部区边界提取** 收敛给 P3；把 Python 两份收敛到 `mw_common` 一份。
**不做什么（本 key）**：不把**其余头部键**（`timeout:/origin:/images:/read_scope:/deny_globs:/write_scope:/l2_read_file_cap:/l2_read_byte_cap:/rag_*`，`worker-mode.ts:340/344/347/352/366/386/414/418/422/426`）改为头部区读取。理由：那是**同一种洞**（正文可注入 `origin: conductor`、`write_scope:` 空值 DoS，见 §7 B1b）但**代价不同** —— 把提取器用于全部头部键会让`.agenticdoc/mw-worker-tree-kill/workers/smoke-tree-kill-1/task.md:4` 的 `timeout: 2` 从头部掉出（wall budget 由 2m 变 60m，RQ-4 §5.4-3 实测），而其余头部键在正文区出现次数 = **0**（本次只读复测：只有 `timeout:` 1 例）。把它塞进本 key 会同时改「角色判定」与「看门狗预算」两个语义面、放大回归面。**决策**：本 key 只做 `type:`；design.md 的残留节登记「其余头部键 = 全文扫描（1 例 `timeout` 行为已登记）」+ 后续卡（建议与 AC-001/AC-002 同域，因为 `origin:` 的正文注入能反向利用 F-1 的 origin 前置条件——本设计已通过「门后移」让该利用失效，故不是 P0）。
**不做**：不新建 Python 包/模块来「物理共享」跨语言（不可能）；不用代码生成为 6 份写样板（生成器本身是第 7 份实现）。
**不做**：不重写 `usedRounds`/`parseTaskLabels` 的消费面（loop/attempt 语义与角色无关）。

### 8.2 其余被否决路径

| 被否决 | 理由 |
|---|---|
| 保留 `_`/`.` 前缀豁免、只在其后加 claim 检查 | 前缀豁免的目的是「放过 `_scratch`」；保留前缀 = 保留 `_tmp`/`.mw`/`_index.parallel` 三类**框架文件同级命名空间**（§4.1），且 `_incidents` 这类既存目录会被当 key。显式名单是唯一能把「放行面」写成可枚举事实的形式（AC-006 的「豁免必须显式」）。 |
| 保留名单从磁盘派生（`readdir('.agenticdoc')` 过滤 `_`/`.`） | `_autopilot` 今日不存在（`Test-Path` False）但框架会按需创建；新项目/新机器上目录可能为空 ⇒ 派生集合会在不同机器给出不同放行面（不可复现）。框架自有性的判据必须来自代码常量（§4.1 依据列）。 |
| 大小写归一 = 落盘时把存量 key 改写成小写 | 触碰 52 行 `_index.parallel`（多窗口并发写目标）+ `pm-state.md` 镜像 + `_index.md`，把「读侧归一」升级为「写侧迁移」，收益（显示一致性）小于风险（同时持有锁 + 跨源同步）。定稿 = 读侧归一 + 首写大小写保留 + `[KEY] case-variant` 审计。 |
| `_index.md` 回退改为「直接删除该回退」 | `_index.md active:` 是 AgenticTask 技能的 degraded 指针（`SKILL.md:14`），删掉会让「无 `_index.parallel` 的项目」失去 owner 解析。定稿 = 保留 + 补 claim/保留名检查（收窄而不删除功能，符合「先问再删」）。 |
| `advance_phase` 保持前缀拒绝、守卫侧只加名单 | 会出现「守卫拒 `_scratch`（作为 key 时）/`advance_phase` 拒所有 `_`」与「守卫放 `_scratch`」的三向矛盾；AC-006 明文要求两处方向一致 ⇒ 必须共用同一 `keyNameRefusal` + 显式 `_scratch` 特例。 |
| 对含展开/引号形态的 `type:` 值做宽松解释（去引号、case-fold） | 会造第二套键空间（`TASK_TYPE_TO_ROLE`/`isRegisteredType`/`DISPATCHABLE_TYPES` 全是精确键）；存量为 0 例。定稿 = `trim()` 后精确匹配，不匹配即 fail-closed。 |
| 把 `fallback` 的定位从「全工具集」改掉（QG-B 方案 (c)） | 触发 `TOOL_ALLOWLISTS` 的 Python parity 锁（`test_dispatch_models.py:158` / L0 parity）与 `agent-team-loop-checkpoint-wiring.test.ts:319-320` 的冻结快照；方案 (a) 用「拒绝」达到同一安全目标且零 parity 风险（§3.3）。 |
| 在 `resolveOwnerKeyWithSync` 内调用 `foreignLiveClaimRefusal` | 会让 `mwds-t01-worker-guard.test.ts:269-272` 的 `guardSites.length === 3` 变红（变成 4），且把「owner 解析」与「写入守卫」两个关注点混在一处。定稿 = 解析只用 `claimState`（§5.2）。 |
| 用 `TaskMeta.type` 新增 `typeSource`/`typeMissing` 字段 | 无消费者（`default` 已经承担「未注册」语义，`isRegisteredType` 判否）；新增字段要同步 `run.json`/trace/测试，收益 0。定稿 = 保持 `string`。 |
| 让 Python 侧也实现「正文升级拒绝」 | Python 不消费 `type:` 做权限判定（只做 model role，`mw_common.py:315`）；双实现会造第二条判定路径与漂移面。定稿 = Python 只做读值单源，拒绝面在 TS 两侧。 |

## 9. 证据、验证方式与未验证项

### 9.1 已验证（本次只读实测，命令可复现）

| 证据 | 方式 |
|---|---|
| 308 本语料、`hdr_val_*` 直方图、`body_type_files=4`、`body_differs=1`、`truncated=0`、`fenced=0`、`header_dup_type=0`、`anomalous_type_lines=[]` | Python（`@'…'@ \| python -`，stdin，无临时文件）+ `node --input-type=module` |
| E-1 BOM 7 本（Python 读空 / TS 读真值） | Python 正则对比 + `node` import `dist/.../worker-mode.js` 的真实 `parseTaskMd` |
| E-3 新算法 delta=1（具名文件） | `node` 同时跑真实 `parseTaskMd` 与本文算法，逐本比较 |
| 跨语言等价 `py_md5 == ts_md5 == a12dc0a7e6e779693638f134deeaad9a`（308 本） | Python `hashlib.md5` 与 `node:crypto` 各自计算 `rel\ttype` 串 |
| E-4 A5/A6/A7 今日复现 | `node --experimental-strip-types` import `src/.../{shared/index-store.ts,pm/ui-bridge.ts,shared/phase-docs.ts}`（真实生产源码，非 dist） |
| 保留名 14 名依据、`_impl_gate.log` | `rg` 逐名定位（§4.1 表格右列） |
| 形态文法对存量零误拦（`index_rows=52` 全过、`task_dirs=308` 全过） | Python 扫描 |
| 语料正文区头部键计数（仅 `timeout:` 1 例） | Python 扫描 |
| QG-B ⑤ 的 14 条 | `read` `mw-dispatch-settle-gates/evidence/quality-gate-code-adversarial-20261011.md`（`:94-110`） |

### 9.2 未验证 / 明确标注

1. **未运行任何测试**：vitest / pytest / `npm run check` / `npm run build` / `mw build` 全部未跑（纪律，PM 负责）。本报告所有「测试保持绿」均为**读码推断**。
2. **§3.3 方案 (a) 的断言改写未实测**：`autopilot-protocol.test.ts:341-367` 的翻转是静态读码；`dispatchNewTasks` 相关用例（`agent-team-loop.test.ts:1357-1425`，含 `type: codex` 这类未注册值）只用于队列路由、不激活 worker，故**推断不受影响**，未逐条跑。是否还有其它「手工未注册类型 + 期望 worker 运行」的用例：只做了 `task.md` 写入点的机器扫描（63 处写入、18 处非字面量表达式），**未逐条判定**。
3. **Python 侧回归未跑**：`test_launcher.py`/`test_rag_audit.py`/`test_common.py` 是否依赖 `_read_task_md_fields` 的「BOM 读空」现状（若有断言钉住空值，则 E-1 修复会让它变红）——**未验证**；S3-5 必须先跑这三个文件再改。
4. **golden fixture 的 18 条 case 正文**（§2.3）是设计稿，未实际生成/复核 base64 内容；落地卡须打印解码后的正文人工核对。
5. **`.gitattributes` 归一**对落盘 BOM fixture 的影响未实测（已用 base64 内联方案规避，但 §2.3 的实现在落地时仍需确认 Python/TS 两侧读同一 JSON 时 `encoding="utf-8"` 不二次损坏）。
6. **`_incidents` 非框架**的依据是 `rg -F '_incidents' packages/coding-agent/src` 0 命中（RQ-5 §2.1）+ 磁盘存在；是否存在 Python/脚本间接写入未验证（保留名处置不受影响，仅影响「框架自有」这一措辞）。
7. **`activeEntry()` 为空的持续性**：E-4 的前置条件是「零 active 行」，它由其他窗口的 claim 行为决定（`spec-key-identity` §4.2 已警示）；本设计的修复不依赖该状态（回退分支恒过 claim 检查），但 §7 B3 的构造用例必须显式造出该状态（用 stub，照 RQ-5 §3 R3）。
8. **`ROLE_ESCALATION_BLOCKED` 文案与 `--allow-foreign-write` 的交互**：本设计未给升级拒绝提供 escape hatch（理由是它只可能出现在被审文本里、没有合法用途）。若 PM 要求与 `allow_foreign_write` 对齐（逃生舱 + 审计），是 1 行参数改动 —— **标记为待裁项**。

## 勘误（交付前逐条复核）

| # | 位置 | 原文 | 正确 |
|---|---|---|---|
| 1 | §5.2 「3 个 guard 调用行」 | `:2058` | **`:2086`**（`advance_phase`）；3 行 = `:1677` / `:2086` / `:2188` |
| 2 | §2.1 P3 / §6.1 | `status-model.ts:1236-1253`（表头正则） | `TASK_FM_LINE_RE` 在 **`:1237`**，`parseTaskLabels` 在 `:1243`（本报告其余引用 `:1243` 均正确） |
| 3 | §1.1 / §6.1 | `paths.ts:38-40`（`workerTaskDir`） | `:37-39`（def 在 `:37`） |
| 4 | §0.2 E-1 与 §4.1 | `launcher.py:155`（正则行） | 正则行确为 `:155`（`type_m = re.search(...)`）；调用侧 `:133-134` |
| 5 | 对 spec §1.2 的更正 | 「PM=297 vs RQ-4=304 = header 边界定义差异」 | 应为 **BOM 未剥**（7 本，§0.2 E-1）：PM 的 297 口径 = 304 - 7 |
| 6 | 对 QG-B ⑤-13 的更正 | `index-store.ts:159-161` | `:164-166`（`findByKey`）；`:159-161` 在 `writeRows` 内 |
| 7 | 对 RQ-5 §2.1 的更正 | 保留名 12 个 | 定稿 **14 个**（+`_impl_gate.log`（`implementation-gate.ts:69`）、+`_incidents`（磁盘既存、非框架）） |

## 附：design.md §2/§4 可直接粘贴的决策条目（DD 编号建议）

| DD | 决策（一行式，可直接落 design.md §2 表） | 依据 |
|---|---|---|
| DD-06a | 角色解析单源：新建 `shared/task-frontmatter.ts`（`extractTaskHeader`/`readTaskHeaderScalar`/`readTaskType`/`scanBodyTypeLines`/`findTypeEscalation`），P1/P2/P6 物理共享，P3 共享边界提取，P4/P5 为 `mw_common.read_task_type` 同语义副本 | §1.1、§2.1 |
| DD-06b | 头部区 = 首行 `---` fence（首个闭合）→ 首个空行 → 头部键文法截断；首个 `type:` 胜出；BOM/CRLF 显式处理；`TaskMeta.type` 保持 `string`，`undefined ⇒ "default"` | §1.2、§1.3 |
| DD-06c | 正文 `type:` 行：power-tool（`write`/`edit`/`bash`）非子集 ⇒ 拒绝（PM 写入前 + worker 启动，`role-escalation-blocked`）；其余 ⇒ `[HEADER] body-type-ignored` 审计 | §1.4 |
| DD-06d | 未注册/缺失 `type:` ⇒ **所有 origin** 一律拒绝（`unregistered-task-type`），`verifier` 无 `read_scope` 的检查保持 conductor-only；运行期白名单 = `TOOL_ALLOWLISTS` 键集 − `fallback`（10 个）；GC-8 manual fallback 退役（含 2 处测试断言改写登记） | §3、§3.3 |
| DD-06e | 一致性证明 = 同一 golden JSON（18 条，base64 内联）+ `mwgf-t14` 回环等式 + `test_task_md_header_parity.py` 的 node 反向差分（fail-closed，不 skip） | §2.2、§2.3 |
| DD-07a | 前缀豁免删除：新建 `shared/key-identity.ts`（14 名保留名单 + `normalizeKey` + `keyNameRefusal`）；`_scratch` 是唯一 owner-放行名 | §4.1、§4.2 |
| DD-07b | 新 key 引导判据 = `findByKey(key) === undefined`（不看前缀/status/claim）；保留名与非法形态**无条件**拒绝 | §4.2 |
| DD-07c | `advance_phase` / `IndexStore.claim` / `/pm-key new` / `update_index.py claim` 共用同一 `keyNameRefusal`（方向一致判据见 §4.3） | §4.3 |
| DD-07d | 大小写归一 = 读侧 `normalizeKey`（`:73`/`:101`/`:164-166` 三处同批），存盘保留首写大小写 + `[KEY] case-variant` 审计；不迁移存量行 | §5.1 |
| DD-07e | `_index.md` 回退必须过 `keyNameRefusal` + `claimState`（失败降级 `_scratch` + 告警）；`dispatch_worker` 守卫改无条件（保持 3 个调用行，`mwds-t01:269-272` 不变） | §5.2 |
| DD-07f | 本 key 不做的边界：其余头部键（`timeout/origin/write_scope/...`）仍全文扫描，`timeout` 1 例行为差登记；`ownerKeyOf`/`row_belongs_to` 的大小写与 `write-then-verify` 自校验列为后续/可选 | §8.1、§5.1 残留、§2.2 可选 3 |
