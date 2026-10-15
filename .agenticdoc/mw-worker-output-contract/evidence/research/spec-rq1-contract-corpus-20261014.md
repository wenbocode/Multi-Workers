# RQ-1: 契约判定全貌与历史语料统计入口（research 取证）

- key: `mw-worker-output-contract` ／ 阶段: SPEC ／ worker: `woc-rq1-contract-corpus`
- 卡: `.agenticdoc/mw-worker-output-contract/tasks/T-RQ1-contract-corpus.md`（card_sha256 `b5de5530d090744352d396dc8a8bc2a6aed85c5912068c7bb7fe149e14159bf4`）
- 仓库基线: 本机 HEAD（工作区含并行会话的未提交改动；本报告只读，未写任何仓库文件）
- 方法边界: **全静态检索 + 只读脚本统计**。实跑了 4 个只读 Python 统计脚本（语料清点/标题结构/别名 vs 标题判定），输出落 `%TEMP%`。**未跑** vitest / pytest / `npm run check` / `npm run build` / `./test.sh` / `npm install`；**未跑** `mw-dispatch-card-gate` 的 `scan4.py` / `scan_like_rq2.py`（它们会在各自 worker 目录写 3 个文件，出本任务写面，故只给命令）。
- 工具: `read`（全文阅读）、`git grep --untracked`、PowerShell 5.1、Python 3.14（`pathlib`/`re`，脚本经 `Out-File -Encoding utf8` 落地以避开 P-001 的内联 CJK 损坏）。

## 0. 结论先行

1. **判定链只有一条**：`checkRecovery()`（`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:87`）只被 `readTerminalGaps()`（`worker/output-writer.ts:203`）调用；`readTerminalGaps` 只有两个调用点——settle 主路径 `worker/worker-mode.ts:2740` 和 `writeOutput` 的默认路径 `worker/output-writer.ts:257-259`。exit code 在 `worker/worker-mode.ts:2746`（`exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2`）。**卡片里写的 `:2745` 是行漂移，实际是 `:2746`。**
2. **被判定不是 `output.md` 本身**：`agentProductText()`（`output-writer.ts:140-145`）先取 `report.md`，非空即用；否则取 `output.md`；两者都空才退回 settle summary。因此「`output.md` 缺段」在 `report.md` 存在时根本不参与判定（本仓实测 423 个受判对象里 239 个读的是 `report.md`）。
3. **匹配语义**：对**整篇文本**做 `text.toLowerCase()` 后逐别名 `haystack.includes(alias.toLowerCase())`（`output-sections.ts:63-64, 89-90`）——不看标题、不剥空白、不分段、不要求大小写（ASCII 因双方都 lower 而等价）、中文逐字面匹配。
4. **契约段表当前值**：base 4 = `结论 / 证据 / 残留与未验证 / 上下文来源`；`coding` 追加 `改动清单`、`review` 追加 `未覆盖面声明`，其余 type 只有 base 4（`output-sections.ts:30, 34-37, 56-61`）。别名表 6 组共 **45** 条（逐字见 §2）。
5. **AC-010 的关键结论：`output.md` 恢复契约不存在历史语料统计**。「99.4% / 87.2%」是 `mw-dispatch-card-gate` 的**派发卡信封**（三槽：上下文/要求/交付物）统计——99.4% = `spec-dispatch-input-format-20261012.md:142,534`（341/343 派发输入），87.2% = `spec-card-format-corpus-20261012.md:281`（301/345 卡片）。`worker/output-sections.ts:19-20` 的「the historical corpus is the measured proof (99.4% / 87.2%)」是**跨 key 转引**；原出处是 `shared/dispatch-card.ts:19-20`，其语料源在文档里点名（`dispatch-card.ts:26-27`）。**没有**任何脚本/测试/fixture 对 `output.md` 跑过段契约统计。
6. **AC-010 降级方案的现成输入（本轮实测）**：`.agenticdoc/**/output.md` = **425** 份、`.agenticdoc/**/report*.md` = **290** 份；带 `task.md` header `type:` 的真实判决对象 = **423** 份。现行整篇别名判定通过 **142/423 = 33.6%**；若改「只认 H2 标题」，通过 **29/423 = 6.9%**（alias_ok→heading_fail 翻转 113 例，heading_ok→alias_fail 0 例）——**S1 单独上线会让语料通过率再降 26.7 个百分点**，这是 AC-010「差异 ≤ 2pp」在当前语料上不可能达成的硬约束。

## 1. 判定链全貌（从 product 文本到 `exitCode`，再往后谁消费）

### 1.1 文本产生 → 判定对象选择

| 步骤 | 坐标 | 原文片段 |
|---|---|---|
| ① agent 自写产物（`output.md` / `report.md`） | `worker/output-writer.ts:242-246` | `export function writeOutput(opts: WriteOutputOpts): void {` … `const outputPath = path.join(dir, "output.md");` |
| ② harness block 追加（**判定之后**才追加，不参与自身判定） | `output-writer.ts:318-321`, `:351`, `:364-368` | `sections.push(\`## TL;DR\n\n${headline(opts.summary)}\`);` … `if (gapNote) sections.push(\`## Recovery Gaps\n\n${gapNote}\`);` … `fs.writeFileSync(outputPath, existing.trim() === "" ? body : \`${existing.trimEnd()}\n\n---\n\n${body}\`, "utf8");` |
| ③ 判定文本选择 | `output-writer.ts:140-145` | `function agentProductText(dir: string, summary: string): string {` / `for (const name of ["report.md", "output.md"]) {` / `const text = readFileSafe(path.join(dir, name));` / `if (text.trim() !== "") return text;` / `return summary;` |
| ④ 取 type | `output-writer.ts:190-191` | `const type = opts.type ?? typeFromTaskMd(dir);` / `if (type === undefined)` |
| ⑤ 迁移豁免 | `output-writer.ts:191-200` | `return { judged: false, missingSections: [], … ok: true };`（无 header `type:` ⇒ 完全不判，`missingSections` 恒空） |

### 1.2 `gaps` 的计算，`gaps.ok` / `gapsReason`

| 步骤 | 坐标 | 原文片段 |
|---|---|---|
| `gaps` 计算点 A（settle 主路径） | `worker/worker-mode.ts:2740-2745` | `const gaps = readTerminalGaps({ taskKey: meta.taskKey, agenticdocRoot: meta.agenticdocRoot, summary: buildSummary(), judgeRecovery: isWritelessRole(meta.type) \|\| reportProduct, });` |
| `gaps` 计算点 B（writer 默认路径） | `worker/output-writer.ts:257-259` | `const gaps = opts.terminalGaps ?? readTerminalGaps({ taskKey: opts.taskKey, agenticdocRoot: opts.agenticdocRoot, summary: opts.summary });` |
| 契约缺口 | `output-writer.ts:203` | `const missingSections = opts.judgeRecovery === false ? [] : checkRecovery(productText, type).missing;` |
| `gaps.ok` | `output-writer.ts:238` | `ok: missingSections.length === 0 && ledger.extra.length === 0 && unjudgeableFiles.length === 0,` |
| `checkRecovery` 本体 | `output-sections.ts:87-91` | `export function checkRecovery(text: string, type: string \| undefined): RecoveryVerdict {` / `const required = recoverySectionsFor(type);` / `const haystack = text.toLowerCase();` / `const missing = required.filter((name) => !containsAlias(haystack, RECOVERY_SECTION_ALIASES[name] ?? [name]));` / `return { ok: missing.length === 0, missing, required };` |
| `exitCode` | `worker-mode.ts:2746` | `const exitCode: 0 \| 2 = evidence.delivered && gaps.ok ? 0 : 2;` |
| `gapsReason`（三段拼装） | `worker-mode.ts:2752-2760` | `const gapReason = gaps.missingSections.length > 0 ? \`missing section(s): ${gaps.missingSections.join(", ")}\` : "";` … `const gapsReason = [gapReason, ledgerReason, unjudgeableReason].filter((part) => part !== "").join("; ");` |
| `questions`（回读原文） | `worker-mode.ts:2773-2777` | `questions: evidence.delivered ? gaps.ok ? undefined : \`recovery-incomplete: ${gapsReason}\` : \`no-product: ${evidence.detail}\`,` |
| `exitReason`（`## Exit Reason`） | `worker-mode.ts:2765-2772` | `: \`Agent settled after ${toolCallCount} tool call(s) without a recoverable product (${gapsReason}). ${effort}\`` |

判定时机：`readTerminalGaps` 在 `finishSuccess()`（`worker-mode.ts:~2703-2790`）里、**唯一一次** `writeOutputGuarded` 之前执行（同函数注释 `worker-mode.ts:2725-2733`：「judged HERE, before the single write-out, and folded into the exit code」）。settle 之后无法自查——这与 FW-001 的判断一致。

### 1.3 `exitCode = 2` 之后谁消费

| 消费者 | 坐标 | 原文片段 |
|---|---|---|
| ① 内存态 → run status | `worker-mode.ts:1980-1986`, `:1994-1995` | `function writeOutputGuarded(opts: WriteOutputOpts): void {` / `markOutcome(opts.exitCode);` … `function markOutcome(exitCode: number): RunStatus {` / `runState.status = exitCode === 0 ? "done" : exitCode === 2 ? "needs-clarification" : "failed";` |
| ② output.md 首行 marker | `shadow run-store.ts::runMarker`（`worker-mode.ts:1985`） | `writeOutput({ ...opts, runMarker: runMarker(runState) });` |
| ③ trace `[END] exit=2` | `worker-mode.ts:2412-2419` | `function recordEnd(exitCode: 0 \| 1 \| 2): void {` / `const status = markOutcome(exitCode);` / `appendEnd(meta.taskKey, meta.agenticdocRoot, { exitCode, … });` |
| ④ `run.json` 持久化 | `worker-mode.ts:2005-2010` | `function finishRun(status: RunStatus, exit?: number): void {` / `runState.status = status;` / `runState.artifacts = collectArtifacts(taskDir);` / `writeRunState(taskDir, runState);` |
| ⑤ Python launcher 映射（进程退出码） | `packages/multi-workers/launcher.py:409-415` | `def _exit_to_status(exit_code: int) -> str:` / `if exit_code == 2:` / `return "needs-clarification"` |
| ⑥ Python launcher 重扫（product 优先） | `launcher.py:429-439` | `def _reap_status(...)` … `from_exit = _exit_to_status(exit_code)`（run.json 的终态 status 覆盖退出码） |
| ⑦ 孤儿行 reconcile | `launcher.py:1478-1513` | `status = _exit_to_status(end_exit)` / `elif (task_dir / "output.md").exists(): status = "failed"` |
| ⑧ PM 轮询 → 回读注入对话 | `pm/pm-orchestrator.ts:1435-1444`, `:1457-1459` | `if (notified.has(entry.taskKey) \|\| !isTerminal(entry.status)) continue;` / `notified.add(entry.taskKey);` / `if (!watch.key \|\| ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;` … `const body = readOutputBody(taskDir);` / `deliverWorkerResult(pi, \`${header}:\n\n${body}\n\n${PM_CONTINUE_HINT}\`);` |
| ⑨ widget 行 detail | `pm/ui-bridge.ts:585-598`, `:789` | `export function readTerminalDetail(taskDir: string, status: WorkerStatus): string {` … `firstLine(readLastProductSectionBody(taskDir, ["Questions"])) ?? readWorkerLogTail(taskDir) ?? "no output.md"` / `detail = readTerminalDetail(path.dirname(e.taskPath), e.status);` |
| ⑩ 回读行本身 | `output-writer.ts:339-342`（exit 2 分支）, `ui-bridge.ts:478-488` | `sections.push(\`## Questions\n\n${opts.questions \|\| "(no questions provided)"}${terminalNote ? \` \| ${terminalNote}\` : ""}\`);` / `readOutputSection(taskDir, section)` 用 `## Questions` 正则取首段正文 |

（FW-001 引用的 `:2745` / `:2776` 两处：`:2746` 与 `:2776` 命中，`:2745` 偏一行。）

## 2. 契约段与别名表（逐字）与匹配算法确切语义

### 2.1 `RECOVERY_SECTIONS` — `worker/output-sections.ts:30`

```ts
export const RECOVERY_SECTIONS = ["结论", "证据", "残留与未验证", "上下文来源"] as const;
```

### 2.2 `RECOVERY_TYPE_SECTIONS` — `worker/output-sections.ts:34-37`（各 type 的额外段）

```ts
export const RECOVERY_TYPE_SECTIONS: Readonly<Record<string, readonly string[]>> = {
	coding: ["改动清单"],
	review: ["未覆盖面声明"],
};
```

`recoverySectionsFor` — `output-sections.ts:56-61`：

```ts
export function recoverySectionsFor(type: string | undefined): string[] {
	const required: string[] = [...RECOVERY_SECTIONS];
	if (type !== undefined) required.push(...(RECOVERY_TYPE_SECTIONS[type] ?? []));
	return required;
}
```

⇒ 表外 type（含 `research` / `vision` / `rag-research` / `verifier` …）**只有 base 4**；`undefined` 同 base 4。

### 2.3 `RECOVERY_SECTION_ALIASES` — `worker/output-sections.ts:46-53`（逐字全文，45 条）

```ts
const RECOVERY_SECTION_ALIASES: Readonly<Record<string, readonly string[]>> = {
	结论: ["结论", "tldr", "tl;dr", "summary", "摘要", "verdict", "总结"],
	证据: ["证据", "evidence", "原始命令", "命令与输出", "复现", "verification", "验证步骤", "测试结果"],
	残留与未验证: ["残留", "未验证", "未确认", "遗留", "remaining", "residual", "unverified", "limitation", "限制"],
	上下文来源: ["上下文来源", "来源清单", "sources", "references", "参考", "读取", "阅读清单", "context sources"],
	改动清单: ["改动清单", "变更清单", "changed files", "files changed", "改动", "变更", "修改文件"],
	未覆盖面声明: ["未覆盖面", "未覆盖", "coverage", "未审", "未考察", "缺口"],
};
```

条目数：7 + 8 + 9 + 8 + 7 + 6 = **45**。

### 2.4 匹配算法确切语义

`output-sections.ts:63-64`：

```ts
function containsAlias(haystack: string, aliases: readonly string[]): boolean {
	return aliases.some((alias) => haystack.includes(alias.toLowerCase()));
}
```

| 问题 | 答案 | 依据 |
|---|---|---|
| 大小写敏感？ | 否。`text.toLowerCase()` 与 `alias.toLowerCase()` 双方都 lower；中文无影响，ASCII 等价于不敏感 | `:89`, `:64` |
| 去空白？ | 否。无任何 `trim`/`\s` 折叠，`" evidence "` 与 `"evidence"` 都命中，`"evi dence"` 不命中 | `:63-64` 全函数仅 `includes` |
| 只看标题？ | **否**。haystack 是整篇文本（标题与正文同权），所以正文里任一处出现「证据」即算该段满足 | `:89` |
| haystack 是整篇还是分段？ | **整篇**（`text` 为 `agentProductText` 返回值）；无按标题切段 | `:89` + `output-writer.ts:202-203` |
| 空文本？ | 永不抛异常；空文本 → 全部 required 记 missing | `:87-91`（`""` 无命中） |
| CRLF？ | 等价——判据里无锚点/行正则，`\r` 不参与 | `:63-64`（测试 `output-recovery-contract.test.ts:136-139` 断言等价） |
| 词汇 fail-open / 结论 fail-closed？ | 是：命中任一别名即算满足（宽），但一段零命中即记 missing 并把 `ok=false` 折进 `exitCode=2`（严） | `:90` + `worker-mode.ts:2746` |
| 标题数 ≥2 的段（重复）？ | 无关，非结构判定 | 同上 |

## 3. 历史语料统计入口（AC-010 的关键）

### 3.1 「99.4% / 87.2%」真实归属：存在，但**不是** `output.md` 恢复契约

检索命令（实测）：

```powershell
git grep -n --untracked -e "99\.4" -e "87\.2" -- .
```

输出（23 行，去掉 `dist/` 与 `.map` 后的命中）：

| 文件:行 | 原文片段 | 含义 |
|---|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:19-20` | `semantics. A strict-heading criterion would reject 87.2% of the historical` / `card corpus and 99.4% of the dispatch corpus (P-03: over-blocking is as much` | **原出处**（信封判定宽档的理由） |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:20` | `* measured proof that strictness misfires (99.4% / 87.2%). The gate is` | **转引**（把卡片语料的数字搬进恢复契约的注释） |
| `.agenticdoc/mw-dispatch-card-gate/spec.md:42,43,82` | `严格三段标题门槛 **44 合规/301 不合规（87.2%）**` / `派发输入 343 张：T1 严 **2/341（99.4%）** 不合格` / `**过拦同样违约**：严格标题档会误拒 87.2%/99.4%` | key 级结论 |
| `.agenticdoc/mw-dispatch-card-gate/evidence/research/spec-card-format-corpus-20261012.md:281` | `| **T1 严**（背景族 + req族 + deliv族 三个显式 H2） | ctx ∧ req ∧ deliv | **44** | **301** | **87.2%** |` | **87.2% 的原始数字**（分母 345 张 `tasks/*.md`） |
| `.agenticdoc/mw-dispatch-card-gate/evidence/research/spec-dispatch-input-format-20261012.md:142` | `| **T1 严**（背景族 + req族 + deliv族 三个显式 H2，节正文非空）| pass **2** / fail **341** = **99.4% 不合格** | pass 44 / fail 301 = 87.2% |` | **99.4% 的原始数字**（分母 343 张 `workers/*/task.md`） |
| `.agenticdoc/mw-dispatch-card-gate/evidence/research/design-envelope-selection-20261012.md:16` | `严格档会误拒 **87.2%** 卡片（spec-card-format-corpus）与 **99.4%** 派发卡（spec-dispatch-input-format）` | 两数字的接线说明 |

（另注：`spec-card-format-corpus-20261012.md:133` 的 `deliv 301/345 = 87.2%` 是单槽命中率，与 `:281` 的 T1 严口径**数值偶然相同**但口径不同，引用时不要混淆。）

### 3.2 可复跑命令与语料来源

| 统计 | 脚本（**已存在**） | 语料来源与份数（脚本硬编码 glob） | 复跑命令 |
|---|---|---|---|
| 87.2% | `.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2-card-corpus/scan4.py`（配套 `scan1.py`/`scan2.py`/`scan3.py`） | `H:\git\Multi-Workers\.agenticdoc\*\tasks\*.md`；**2026-10-12 时 345 张 / 37 key**（`scan1-out.txt: card_count: 345`），本轮实测已涨到 **443 张** | `python "H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2-card-corpus\scan4.py"` |
| 99.4% | `.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2b-dispatch-input-format/scan_like_rq2.py` | `H:\git\Multi-Workers\.agenticdoc\*\workers\*\task.md`；**2026-10-12 时 343 张**，本轮实测 **438 张** | `python "H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2b-dispatch-input-format\scan_like_rq2.py"` |

**副作用（未实跑的原因）**：`scan4.py` 末尾 `with open(os.path.join(OUT, "scan4-report.txt"), "w", …)` 等 3 处会写回该 worker 目录（`scan4-report.txt` / `scan4-variants.txt` / `scan4-cards.tsv`），出本任务写面且违反本卡「不得修改仓库任何文件」，故**只给命令不执行**。

### 3.3 `output.md` 恢复契约的语料统计：**不存在**

检索命令与输出（实测，两条均为全仓含未跟踪文件）：

```powershell
git grep -rn -e "RECOVERY_SECTIONS" -e "recoverySectionsFor" -e "checkRecovery" -- .
```

命中面（去掉 `dist/` 与 `.map` 后共 3 类，**无脚本、无 fixture、无语料目录**）：

```
.agenticdoc/mw-dispatch-card-gate/tasks/T-04-recovery-contract.md:10   （需求卡，不是统计）
packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:30,32,56,57,87,88
packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:6,203
packages/coding-agent/test/suite/output-recovery-contract.test.ts:26,27,28,96,98,…
```

第二条检索（是否存在「扫 output.md 语料」的脚本）：

```powershell
git grep -rln -e "output\.md" -- .agenticdoc | Select-String -Pattern "\.(py|mts|mjs|ps1|sh)$"
```

输出 7 个脚本，逐个核对后**均与恢复契约无关**：

- `.agenticdoc/_incidents/in3-queue-reenqueue-20261010/scripts/in3-impact-audit.py`（队列重入影响面；`PRODUCT_NAMES = {"output.md","report.md",…}` 只做产物存在性/时间戳）
- `.agenticdoc/mw-gate-verdict-hardening/evidence/scripts/{in3-impact-audit.py,t20-controls.ps1,t23-pmstate-qg2.py,t23-pmstate-t12.py,t23-pmstate-t23.py,t23-quality-gate-report.py}`（gate verdict 计数锁，非段契约）
- `.agenticdoc/mw-dispatch-settle-gates/evidence/scripts/{mwds-controls.ps1,t24-newkey-pmstate.py}`（测试清单/PM 状态文本）

**结论（不存在）**：仓库内没有对 `output.md` 跑过「契约段满足率」或「exit=2 率」的脚本、测试或 fixture。`worker/output-sections.ts:19-20` 的「历史语料」措辞是**无 output.md 语料支撑的转引**——这是本卡第 3 问的核心答案，也是 AC-010 必须降级的直接依据（spec §4 R1 的降级分支已预见）。

### 3.4 AC-010 降级方案的现成输入：`output.md` 语料清单（本轮实测）

计数命令（Python，只读）：

```python
files = sorted(pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc").rglob("output.md"))   # 425
reports = sorted(ROOT.rglob("report*.md"))                                              # 290
```

| 语料 | 份数 | 说明 |
|---|---|---|
| `.agenticdoc/**/output.md` | **425** | 含 `_scratch/` |
| `.agenticdoc/**/report*.md` | **290** | 与 output.md 重叠 239 个 worker 目录 |
| **受判对象**（`workers/<task>/` 且有 `task.md` header `type:`，取 `report.md` -> `output.md`） | **423** | 与 `readTerminalGaps` 的 `agentProductText` 选择规则同构 |
| 受判对象中 `type=` 分布 | coding 272 / research 120 / review 30 / vision 1 | 实测 |

**标题结构（425 份 output.md 的 H2 标题集合签名，Top 8；双竖线为文件内多 block 顺序）**：

```
51  TL;DR | Summary | Deliverables | Verification Steps | Exit Reason
41  TL;DR | Summary | Changed Files | Verification Steps | Exit Reason | TL;DR | Summary | Changed Files | Verification Steps | Exit Reason | TL;DR | Summary | Changed Files | Verification Steps | Exit Reason | TL;DR | Summary | Changed Files | Verification Steps | Exit Reason
24  TL;DR | Summary | Changed Files | Verification Steps | Exit Reason
12  TL;DR | Summary | Questions | Recovery Gaps
11  TL;DR | Summary | Verification Steps | Exit Reason
 9  TL;DR | Summary | Changed Files | Verification Steps | Exit Reason | TL;DR | Summary | Changed Files | Verification Steps | Exit Reason
 4  Summary | Changed Files | Verification Steps | Exit Reason | TL;DR | …（4 个 block）
 3  TL;DR | Summary | Exit Reason | Recovery Gaps | TL;DR | Summary | Exit Reason | TL;DR | Summary | Questions | Ledger Gaps
```

**「最后一个 harness block」的标题签名（= PM 回读看到的形态）**：

```
169  TL;DR | Summary | Changed Files | Verification Steps | Exit Reason
 61  TL;DR | Summary | Deliverables | Verification Steps | Exit Reason
 16  TL;DR | Summary | Verification Steps | Exit Reason
 12  TL;DR | Summary | Questions | Recovery Gaps
  7  TL;DR | Summary | Questions | Ledger Gaps
  4  TL;DR | Changed Files | Verification Steps | Exit Reason
```

**核心矛盾数据**（同一 425 份语料）：

| 判据 | 通过 | 说明 |
|---|---|---|
| 整篇别名（现行 `checkRecovery` 口径，仅 base 4） | **90/425 = 21.2%** | 走别名 fail-open 的虚高 |
| **只认 H2 标题**（S1 口径，仅 base 4） | **4/425 = 0.9%** | 4 份 = `mwgal-t16-synthetic-claim`、`mwgal-t03-rq3-serve-drift`、`wjg-w15-delta-adversarial`（PM 补录后）等 |
| 模板四段 `TL;DR/Summary/Questions/Recovery Gaps` 齐全 | **22/425 = 5.2%** | 澄清模板不等于契约段 |
| `task.md` 有 header `type:` 且五段标题齐全（按 type 计额外段） | coding 3/272、research 0/119、review 1/30 | 见 §3.4 表下说明 |

**受判对象（423 份）上的前后对比**（同一批文本、同一别名表，只换 haystack）：

| 判据 | ok | fail | 通过率 |
|---|---|---|---|
| 整篇别名（现行） | 142 | 281 | **33.6%** |
| 只认 H2 标题（S1） | 29 | 394 | **6.9%** |

翻转矩阵：`alias_fail→heading_fail = 281`、`alias_ok→heading_fail = 113`、`alias_ok→heading_ok = 29`、`heading_ok→alias_fail = 0`。标题口径缺失频次：`上下文来源 360/423`、`残留与未验证 311/423`、`证据 138/423`、`结论 93/423`、`改动清单 68/423`、`未覆盖面声明 25/423`。

⇒ **AC-010 的「差异 ≤ 2 个百分点」在该语料上只有两种可能达成路径**：要么入口取 §3.2 的信封统计（但那与本 key 的改动正交，差异恒为 0，是**空洞满足**），要么把 S1 与 S2/S3（前置清单 + 机械段自动补齐）绑定在同一批复跑里（否则单 S1 会让通过率掉 26.7pp）。

## 4. 澄清模板的来源

**生成点唯一**：`worker/output-writer.ts::writeOutput`。

| 段 | 坐标 | 原文片段 |
|---|---|---|
| `## TL;DR` | `output-writer.ts:318-320` | `// TL;DR first section (D-005): single-line conclusion on every exit path,` / `sections.push(\`## TL;DR\n\n${headline(opts.summary)}\`);` |
| `## Summary` | `:321` | `sections.push(\`## Summary\n\n${opts.summary \|\| "(no summary)"}\`);` |
| `## Questions` | `:337-339` | `} else if (opts.exitCode === 2) {` / `sections.push(\`## Questions\n\n${opts.questions \|\| "(no questions provided)"}${terminalNote ? …}\`);` |
| `## Recovery Gaps` | `:348-351` | `// named gaps are product sections on EVERY exit path (T-07 requirements 1/6).` / `if (gapNote) sections.push(\`## Recovery Gaps\n\n${gapNote}\`);` |

**走这条路径的条件**：`writeOutput` 是**每个终态**（exit 0/1/2/130）唯一的产品写出点；`## TL;DR`/`## Summary` 无条件写（`:320-321`）；`## Questions` 仅 `exitCode===2`（`:337-339`）；`## Recovery Gaps` 仅当 `gaps.missingSections.length > 0`（`:263`, `:351`）。因此「NC 型 `output.md` 只有澄清模板四段」正是 `exitCode=2` 时的确定性产物，不是 agent 自由发挥。

**与契约段名的映射关系：没有一一映射**（这是 FW-001 修法 4 的事实前提）：

| 模板段 | 是否命中某个契约段的别名 | 命中哪个 |
|---|---|---|
| `## TL;DR` | 命中 | `tldr` → `结论` |
| `## Summary` | 命中 | `summary` → `结论` |
| `## Questions` | **不命中任何别名** | —（`questions` 不在任何别名表里） |
| `## Recovery Gaps` | **不命中任何别名** | —（`recovery`/`gaps` 均不在别名表里） |

即：这套模板最多覆盖 4 个必需段中的 **1 个**（`结论`，且靠 `TL;DR`/`Summary` 两个别名）。W-12（五段全缺）与 QG（唯一缺 `上下文来源`）都由此产生。

补充（**前置告知的现存实现**，与 S2 相关）：conductor 合成 task.md 时已把必备段写进交付说明——`packages/multi-workers/autopilot/dispatch.py:358-362`：

```python
_DEFAULT_DELIVERABLES = (
    "按任务书交付：report.md / output.md 必备段（结论 / 证据（含原始命令与输出）/ "
    "改动清单（coding）或未覆盖面声明（review）/ 残留与未验证 / 上下文来源清单）；"
    "coding 同时记录 trace.log 的写入事件。"
)
```

以及 `dispatch.py:655-663` 的 card-less 变体（同段清单）、`autopilot/conductor.py:1854-1863` 的 L3 reviewer 专属两段（`## Quality Gate Report` + `## Achieved`，判定链在 `conductor.py:1900-1904 _L3_SOURCE_ORDER = ("output.md", "report.md")`）。这些是**另一套**段名，与 `RECOVERY_SECTIONS` 不共享常量。

## 5. `output.md` 的全部消费者

| # | 消费者 | 坐标 | 按什么结构读 | 缺段/缺文件时的行为 |
|---|---|---|---|---|
| 1 | 契约判定（写侧） | `worker/output-writer.ts:140-145, 202-203` | 整篇文本别名子串（`report.md` 优先） | 命中不了即 `missingSections`，折进 `exitCode=2` |
| 2 | settle 出口 | `worker/worker-mode.ts:2740-2790` | 同上 | `exit=2` / `needs-clarification` / marker / run.json 同步 |
| 3 | PM 终态回读（全篇注入对话） | `pm/pm-orchestrator.ts:1457-1459`；`pm/ui-bridge.ts:504-518`（`readOutputBody`） | 读**整个文件**，超 20 000 字符截断并附路径 | 返回 `undefined` → 退回 spawn-failure / 「无 output.md 摘要」提示（`pm-orchestrator.ts:1460-1474`） |
| 4 | widget 行 detail（done） | `pm/ui-bridge.ts:606-611` | **最后一个非占位 `## TL;DR` ?? `## Summary`** block 的首行 | 返回 `""`（只渲染 key） |
| 5 | widget 行 detail（needs-clarification） | `ui-bridge.ts:595-598` | 最后一个非占位 `## Questions` 首行 → `worker.log` 尾行 → 字面 `"no output.md"` | 同上 |
| 6 | widget 行 detail（failed / lost） | `ui-bridge.ts:586-593`, `:599-604` | spawn-failure 行 ?? `## Exit Reason` 首行 ?? log 尾行 | 同上 |
| 7 | widget 装配点 | `ui-bridge.ts:789`（`renderWatchLines`） | 调 #4-#6 | — |
| 8 | 通用段读（首匹配，冻结语义） | `ui-bridge.ts:478-488`（`readOutputSection`）、`:493-494`（`readOutputSummary` → `## Summary`） | 首个 `## <section>` 正则 | 返回 `undefined` |
| 9 | 段结构读（末匹配） | `shared/output-sections.ts:84-131, 140-147`（`readOutputSections` / `readLastProductSection` / `readLastProductSectionBody`） | 全部 `## ` 块，**从末块向前**取首个非占位块；占位集来自 `shared/deliverable-evidence.ts`（15/16 条字面） | 全占位 → `undefined` |
| 10 | 交付证据判定（C5/C6） | `shared/deliverable-evidence.ts:187-220` | channel 1 `report.md` → channel 2 磁盘 `output.md`（覆盖 reply）→ 机器行/引用/artifacts | `delivered:false` → `exit=2` + `no-product` alarm |
| 11 | 写面拒绝记录追加 | `worker/worker-mode.ts:694-711` | 追加 `## Read Scope Rejections` 到既有 `output.md` 末尾 | 无条件追加（在 writeOutput 之后） |
| 12 | RAG 缺失标记 | `worker/worker-mode.ts:1827-1840` | 追加 `## RAG` 标记一次 | — |
| 13 | Python launcher 终态 reconcile | `launcher.py:1490-1513` | 只看**存在性**（`(task_dir / "output.md").exists()`） | 不存在 → 走 silence rule（`lost` 或继续等待） |
| 14 | RAG 审计 CLI | `packages/multi-workers/mw.py:1907-1919`（`_rag_terminal_workers`） | 只对 `_workers.parallel` **终态**行的 worker 读 `output.md`/`trace.log` 的 `rag_*` key=value 行 | 非终态行显式跳过（`D-008`） |
| 15 | conductor C-35 判别 | `autopilot/conductor.py:344-366` | 只看存在性：`if (task_md.parent / "output.md").is_file():` ⇒ 「已是终态产物，属历史」不重派 | 不存在 ⇒ 可能是候选 work |
| 16 | L3 轮次判定 | `autopilot/conductor.py:1827-1831, 1900-1904, 2054-2090` | 自己的两段契约（`## Quality Gate Report` + `## Achieved`），`output.md` → `report.md` 回退；FAIL 标记三形态 | 无合格源 ⇒ fail-closed `below`（`l3-no-verdict`） |
| 17 | artifact 清单 | `autopilot/evidence.py:282` | basename 过滤（`output.md` 不算证据产物） | — |
| 18 | 运行身份锚 | `shared/run-store.ts:110-152` | `output.md`/`report.md`/`progress.md` mtime/first-line 关联 run_id | — |

**注意**：#3/#4/#5/#9/#10 的读法都依赖 **harness block 的段名**（`TL;DR`/`Summary`/`Questions`/`Exit Reason`），而契约判定依赖**另一套段名**（`结论`/`证据`/…）。这正是 FW-005「两套结构并存」在代码层的形态：同一文件、同一写入者、两套互不映射的段名消费协议。

## 6. 现有测试清单（含「改按标题结构后」的翻转面）

### 6.1 vitest（`packages/coding-agent/test/**`）

| 文件 | 相关用例（`:行` + 名） | 标题化后是否翻转 |
|---|---|---|
| `test/suite/output-recovery-contract.test.ts`（17 例） | `:99 RECOVERY_SECTIONS is the documented base four`；`:103 complete research report => ok`；`:110 missing 上下文来源 => ok=false…`；`:116 coding adds 改动清单; review adds 未覆盖面声明`；`:126 undefined/unknown type carries the base four only`；`:132 empty text is missing every required section`；`:136 CRLF and LF are equivalent`；`:145 needs-clarification path: the read-back names the missing sections`；`:165 done path with a complete report`；`:186 done path with gaps`；`:202/:212 migration`；`:270 complete report => done`；`:282 missing section => needs-clarification…` | **不翻转**（fixture `:52-84` 全用真标题 `## 结论`/`## 证据`/`## 残留与未验证`/`## 上下文来源`）。**新增** AC-001 的 8 例矩阵后，`:103`/`:270` 需补「仅正文含别名而无标题 ⇒ 缺」的反例 |
| `test/suite/dispatch-recovery-terminal.test.ts`（20 例） | `:162 a delivered but incomplete report flips done -> needs-clarification`；`:178 a complete report settles done`；`:189 migration:…never judged`；`:391 readTerminalGaps is the single verdict…`（断言 `:406 expect(gaps.missingSections).toEqual([])`） | **不翻转**（fixture `:66-85` `COMPLETE_RESEARCH`/`MISSING_CONTEXT_SOURCES` 全真标题） |
| `test/suite/mwds-t05-output-sections.test.ts`（15 例，AC-010 读侧） | `:81 AC-010 read side: last non-placeholder block`；`:176 AC-010 single block unchanged`；`:304 settle idempotence`；`:345 command surface unchanged`；`:346/:357` 首匹配 vs 末匹配锁定 | **不翻转**（测 `shared/output-sections.ts` 读侧，与 `checkRecovery` 无共享符号） |
| `test/suite/mwds-t04-deliverable.test.ts`（26 例） | `:111 AC-006 corpus replay (VC-025)`；`:153 channel order`；`:399 AC-006 settle fold`；`:541 AC-008 branches` | **不翻转**（走 `hasDeliverableEvidence`，不是契约判定） |
| `test/suite/mwds-t12-regression.test.ts`（17 例） | `:192 seam C5/C6: T-04 verdict and T-07 python reap agree`；`:228 seam C7: T-06 section generation and the T-05 read side` | **不翻转**（fixture 真标题；测跨模块一致性） |
| `test/suite/mwgal-t17-ledger-role-aware.test.ts`（21 例） | `:246`, `:392` 调 `readTerminalGaps(..., judgeRecovery: false)` | **不翻转**（显式关闭恢复判定） |
| `test/suite/mwgal-t17b-ledger-infra-writes.test.ts`（22 例） | `:281`, `:349`, `:399` 同 `judgeRecovery: false` | **不翻转** |
| `test/suite/mwgal-t17c-ledger-unresolvable.test.ts`（22 例） | `:161`, `:279` 同 | **不翻转** |
| `test/suite/mwgal-t21-qg-fixes.test.ts`（23 例） | `:153` 同 | **不翻转** |
| `test/suite/mwds-t23-cutover-recheck.test.ts`（15 例） | `:103` 帮助函数写死 `judgeRecovery: false`；`:194`/`:233` 走该帮助函数 | **不翻转** |
| `test/suite/mwds-t21-write-intent-soundness.test.ts`（15 例） | `:323 T-21 requirement 6 — real corpus`、`:355` | **不翻转**（账本抽取，不碰恢复段） |
| `test/suite/rag-research-doc.test.ts` | `:213`, `:235`, `:274` 断言 `report.missingSections` | **不翻转但需区分**：这是 **RAG 研究文档**自己的段契约（`快照`/`查询`/`引用`…），与 `RECOVERY_SECTIONS` 同名不同源 |
| `test/extensions/agent-team-loop.test.ts`（232 例） | `:494 exit 2 writes Questions`；`:2695 terminal detail sources (T-05)`；`:2727 VC-007 failed detail`；`:2751 VC-008 needs-clarification detail`；`:2778 VC-009 done detail = TL;DR ?? Summary`；`:2797 renderWatchLines wires readTerminalDetail` | **不翻转**（测 harness 模板段名与读侧，S1 不改这些段名） |

**结论**：`packages/coding-agent/test/**` 里**没有一个现存用例会因「判定改按标题结构」而翻转**——所有契约 fixture 都已经是真标题，账本类用例显式 `judgeRecovery:false`，live-corpus 守卫（`mwgal-t17*:4xx`、`mwgal-t21:262`）直接调 `diffLedger` 而非 `readTerminalGaps`。AC-001 的「翻转面」是**新增矩阵用例**（尤其「仅正文含别名而无标题」与「标题在引用块内」两例在当前实现下必然判 `ok=true`，新规则下必须判 missing），不是既有回归。

### 6.2 pytest（`packages/multi-workers/test_*.py`）

| 文件 | 相关用例（`:行` + 名） | 标题化后是否翻转 |
|---|---|---|
| `test_autopilot_verdict_source_fallback.py` | `test_*` 15 例（`output.md` → `report.md` 回退、`_l3_qualifies`、白洗闭包） | **不翻转**（用 L3 自己的两段契约 `## Quality Gate Report`/`## Achieved`，`conductor.py:1900-1904`） |
| `test_autopilot_fail_marker_forms.py` | 30 例 L1 真值表（`output.md:12` bullet FAIL 等 5 个语料锚点） | **不翻转**（同一条 L3 链） |
| `test_autopilot_verdict_provenance_guard.py` | 16 例（T1/T2 时间指纹、写侧禁令、done-credential gate） | **不翻转** |
| `test_launcher.py` | `:693`（`output.md` 的存在性是 writeOutput fallback）、`:795-797`（老 bundle 无 `[END]` 但有 `output.md`）、`:1341/:1368-1382`（run.json 终态 vs `output.md`） | **不翻转**（只判 file existence / run.json） |
| `test_mwds_t07_reap_productfirst.py` | reap 时 run.json status 优先 | **不翻转** |
| `test_rag_audit.py` | `:156`, `:318`（RAG 证据行解析） | **不翻转** |
| `test_autopilot_conductor_exec.py` | `:1425`, `:1606`（L3 轮次判定端到端） | **不翻转** |

⇒ **无 pytest 用例翻转**；`packages/multi-workers` 侧完全没有恢复契约的判定实现（判定只在 TS 侧）。

## 未找到清单

1. **`output.md` 恢复契约的语料统计入口：不存在**。检索命令与输出见 §3.3 两条 `git grep`；`RECOVERY_SECTIONS`/`checkRecovery` 的命中面只有 1 个需求卡（`.agenticdoc/mw-dispatch-card-gate/tasks/T-04-recovery-contract.md:10`）、1 个实现文件、1 个测试文件，无脚本/无 fixture。
2. **`worker/output-sections.ts:19-20` 所声称的「历史语料实测」在 `output.md` 上：不存在**。可追溯到的只有 `shared/dispatch-card.ts:19-20` 转引的**信封**统计（§3.1）。
3. **`99.4%` 与 `output.md` 的任何关联：不存在**。`git grep -n -e "99\.4" -- .` 的全部 23 行命中里，与本 key 有关的只有 `output-sections.ts:20` 与 `dispatch-card.ts:20` 两处注释；语料侧只出现在 `mw-dispatch-card-gate`（派发输入）与一处无关事故补丁（`.agenticdoc/_incidents/in3-queue-reenqueue-20261010/rewrites-81-20261010.patch:4933` 的 `path.resolve() 99.41`，性能数字）。
4. **`shared/output-sections.ts` 与 `worker/output-sections.ts` 之间的共享符号：不存在**（前者是读侧，后者是写侧；`worker/output-sections.ts:6-9` 明说「same file name, opposite direction, no shared symbols」）。不存在即「读侧不会因写侧判定改结构而失效」。
5. **`## Questions` / `## Recovery Gaps` 到契约段名的映射：不存在**（§4 表；两个名字都不在任何别名表项里）。
6. **6 次历史实例的「判定前」`output.md` 原始字节：部分不存在**。`wjg-qg-evidence-closure` / `wjg-w12-negative-space-audit` / `wjg-w15-delta-adversarial` / `wfg-rq-d2-runtime-guard` 的 `output.md` 现已被 PM byte-pure 补录，盘上版本**含补录段**（标题带「（PM-补录，2026-10-1x）」）；`wfg-rq2/rq3-d2` 的补录落在 `report.md`。判前字节只在 `_framework-reflect.md` FW-001 的记录里（3,266 B / 914 B / 2,658 B / 3,745 B / 2,907 B），**盘上无原件**，无法直接重放。

## 未覆盖面声明

- **未实跑任何测试**（vitest / pytest / `npm run check` / `./test.sh` 全部未跑，遵循本卡只读边界与 P-032）。§6 的「不翻转」是**静态判据**（fixture 文本 + 代码路径），不是运行结果；真正的翻转确认需要跑 `test/suite/output-recovery-contract.test.ts` 与 `dispatch-recovery-terminal.test.ts`。
- **未执行 `scan4.py` / `scan_like_rq2.py`**（会写 3 个文件到 `mw-dispatch-card-gate` worker 目录）。§3.2 的「可复跑命令」未经本轮验证；两个脚本的 glob 与 `ROOT` 硬编码为 `H:\git\Multi-Workers`，换机器需改。
- **未做跨时间的一致性核对**：`87.2%` 的文档数字对应 2026-10-12 的 345 卡语料，本轮实测已 443 卡；**没有**在本报告里重算历史口径的复现率（那需要跑 §3.2 的脚本）。
- **未覆盖 `dist/` 分发包**：`packages/coding-agent/dist/**` 有同名编译产物（含 `output-sections.js`/`.d.ts`/`.map`），本报告所有坐标均为 `src/` 源码；dist 与 src 是否同版本**未核**。
- **未覆盖 PM 侧的 `renderCardSeedSections` 注入面**：`pm/ui-bridge.ts` 里「卡面注入契约段清单」的现状（FW-004 相关）只做了 `_DEFAULT_DELIVERABLES`（Python conductor 侧）的核对，TS 侧派发卡模板未逐行审。
- **未覆盖 `mw-serve` / `mw doctor` 对 `output.md` 的读取**：`mw.py` 只核到 `:1913`（RAG 终态 worker 分组）与 `:1997`（`output.md`/`trace.log` 读取），其余 CLI 面（`mw doctor`、`mw serve` 状态推送）未逐条排查。
- **未覆盖 `_scratch/` 之外的临时/已删除产物**：语料清点以当前盘上文件为准，历史被清理的 worker 目录不在 425 份里。
- **`_framework-reflect.md` FW-001 的「99.4%/87.2% 的语料统计」这一表述本身**：本报告判定它是转引误读，但**没有**回溯当时的对话/上下文去确认 FW-001 作者是否有另一处未落盘的统计（盘上检索为负）。

## 证据

- **实跑命令（只读，4 条）**：
  1. `git grep -n --untracked -e "99\.4" -e "87\.2" -- .` → 23 行（§3.1）
  2. `git grep -rn -e "RECOVERY_SECTIONS" -e "recoverySectionsFor" -e "checkRecovery" -- .` → 3 类命中（§3.3）
  3. `git grep -rln -e "output\.md" -- .agenticdoc | Select-String "\.(py|mts|mjs|ps1|sh)$"` → 7 个脚本，逐个核对无关（§3.3）
  4. Python 只读统计（3 个脚本，输出落 `%TEMP%\corpus-analysis.txt` / `flip-matrix.txt` / `sig.txt`）→ 425 / 290 / 423 / 142 / 29 等全部计数
- **计数复核命令（可直接重跑）**：
  ```powershell
  (Get-ChildItem -Recurse -File -Filter output.md .agenticdoc).Count          # 425
  (Get-ChildItem -Recurse -File -Filter "*.md" .agenticdoc | Where-Object { $_.DirectoryName -like "*\tasks" }).Count   # 443
  (Get-ChildItem -Recurse -File -Filter task.md .agenticdoc | Where-Object { $_.DirectoryName -like "*\workers\*" }).Count # 438
  ```
- **6 次历史实例盘上复核（本轮实测，`run.json` + 标题结构）**：

| task | key | type | output.md | report.md | run.json |
|---|---|---|---|---|---|
| `wjg-qg-evidence-closure` | mw-worktree-junction-guard | review | 4,945 B；`TL;DR｜Summary｜Questions｜Recovery Gaps｜上下文来源（PM-补录，2026-10-13）` | 无 | `status=needs-clarification exit=2` |
| `wjg-w12-negative-space-audit` | mw-worktree-junction-guard | review | 5,442 B；`TL;DR｜Summary｜Questions｜Recovery Gaps｜结论｜证据｜残留与未验证｜上下文来源｜未覆盖面声明`（均带「PM-补录，2026-10-14」） | 无 | `status=needs-clarification exit=2` |
| `wjg-w15-delta-adversarial` | mw-worktree-junction-guard | review | 8,721 B；`TL;DR｜Summary｜Questions｜Recovery Gaps｜结论｜残留与未验证｜上下文来源` | 无 | `status=needs-clarification exit=2` |
| `wfg-rq2-enforcement` | mw-write-face-guard | research | 2,658 B；`TL;DR｜Summary｜Questions｜Recovery Gaps` | 4,105 B；`TL;DR｜残留与未验证｜上下文来源` | `status=needs-clarification exit=2` |
| `wfg-rq3-safety` | mw-write-face-guard | research | 3,745 B；同上四段 | 4,145 B；`TL;DR｜残留与未验证｜上下文来源` | `status=needs-clarification exit=2` |
| `wfg-rq-d2-runtime-guard` | mw-write-face-guard | research | 2,907 B；同上四段 | 4,476 B；`TL;DR｜残留与未验证｜上下文来源` | `status=needs-clarification exit=2` |

（6/6 与 `_framework-reflect.md` FW-001 的记录一致，且可解释：`wfg-rq2/rq3/d2` 的 `report.md` 在 settle 时不存在，`agentProductText` 取的是 `output.md` 的四段模板 → 缺 `结论`/`证据`/`残留与未验证`/`上下文来源` 中除别名命中外的全部。）

## 残留与未验证

1. **AC-010 的入口定性是本报告最关键的未验证传导**：我判定「入口不存在」，依据是 `git grep` 负空间（含 `--untracked`）；但 `_framework-reflect.md` FW-001 是 PM 写的，若 PM 手里有未落盘的口头统计，本报告无法反驳。**建议 design 阶段把这一步当作已决**（spec §4 R1 已给出降级分支）。
2. **`alias_ok→heading_fail = 113` 的语义**：这 113 份在现行判定下 `ok=true`、在 S1 下 `ok=false`，是 **fail-open 的反向风险面**（正文偶然含别名即算满足）。它们的 `exit` 现在可能是 `0`；S1 上线后同一批会变 `exit=2`——**需要 S2/S3 兜底，否则是净退化**。
3. **`#4/#5` 读侧段名与契约段名不映射这一事实的后果未量化**：`readTerminalDetail` 依赖 `TL;DR`/`Summary`/`Questions`/`Exit Reason`，S3 若自动插入 `## 上下文来源` 桩，对 widget 无影响（不同段名）；但 S1 若顺手把 harness 模板段名改成契约段名，`readTerminalDetail`、`readOutputSummary`、`shared/deliverable-evidence.ts`（占位集 + 机器行）会同时失效。本报告**只指出风险，未验证影响面**。
4. **`judgeRecovery` 的默认值语义易踩**：`readTerminalGaps` 中 `opts.judgeRecovery === false ? [] : checkRecovery(...)`（`output-writer.ts:203`）——**默认判**。所有账本类测试靠显式 `false` 隔离；任何新调用点若忘记传参就会被恢复契约的 `exit=2` 拖累。本报告**未统计**生产代码里除了 `worker-mode.ts:2745` 之外是否还有别的 `readTerminalGaps` 调用点（已核：只有 `output-writer.ts:259`，其 `judgeRecovery` 恒为 `undefined` ⇒ **默认判**，这是 writer 直接调用路径与 settle 路径的语义差）。
5. **`exitCode: 0 | 2` 的类型域**（`worker-mode.ts:2746`）：`finishSuccess` 只能产出 0 或 2，而 `writeOutput` 接受 `0|1|2|130`。故障/超时路径走另一处 `writeOutputGuarded`（`worker-mode.ts:2045`, `:2490`, `:2862`）——本报告**未逐条核**这些路径是否也会被 `gaps` 影响（读到的 `:2045` / `:2490` / `:2862` 调用点未传 `terminalGaps`，因此会走 writer 内的默认 `readTerminalGaps`）。

## 上下文来源

- 卡：`.agenticdoc/mw-worker-output-contract/tasks/T-RQ1-contract-corpus.md`（sha256 `b5de5530…`）
- 规格：`.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P1/P3、§1.6 S1/S2/S3、§3 AC-001…AC-005、AC-010、§4 R1）
- 台账：`.agenticdoc/_framework-reflect.md` FW-001（含 6 次实例的现象与坐标）
- 信封语料源：`.agenticdoc/mw-dispatch-card-gate/evidence/research/spec-card-format-corpus-20261012.md` §0.2/§3.2/§1.1、`spec-dispatch-input-format-20261012.md` §（T1 表 / :142 / :481 / :534）、`design-envelope-selection-20261012.md:16`、`spec-gate-layer-20261012.md:17,295,396`、`spec.md:42,43,82`
- 信封脚本：`.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2-card-corpus/{scan1..scan4}.py`、`workers/mwd-rq2b-dispatch-input-format/scan_like_rq2.py`
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/{worker/output-sections.ts, worker/output-writer.ts, worker/worker-mode.ts, shared/output-sections.ts, shared/deliverable-evidence.ts, shared/dispatch-card.ts, pm/ui-bridge.ts, pm/pm-orchestrator.ts}`；`packages/multi-workers/{launcher.py, mw.py, autopilot/conductor.py, autopilot/dispatch.py, autopilot/evidence.py}`
- 测试：`packages/coding-agent/test/suite/{output-recovery-contract,dispatch-recovery-terminal,mwds-t04-deliverable,mwds-t05-output-sections,mwds-t12-regression,mwds-t21-write-intent-soundness,mwds-t23-cutover-recheck,mwgal-t17-ledger-role-aware,mwgal-t17b-ledger-infra-writes,mwgal-t17c-ledger-unresolvable,mwgal-t21-qg-fixes,rag-research-doc}.test.ts`、`packages/coding-agent/test/extensions/agent-team-loop.test.ts`；`packages/multi-workers/test_autopilot_*.py`、`test_launcher.py`、`test_mwds_t07_reap_productfirst.py`、`test_rag_audit.py`
- 本轮实测脚本与中间输出（**不在仓库内**，位于 `%TEMP%`）：`corpusinv.py`/`corpus-inventory.txt`、`corpusan.py`/`corpus-analysis.txt`、`judged.py`/`judged-corpus.txt`、`flip.py`/`flip-matrix.txt`、`sig.py`/`sig.txt`

[VERIFY] counts: output_md_corpus=425 report_md_corpus=290 judged_targets=423 alias_ok=142 alias_fail=281 heading_only_ok=29 heading_only_fail=394 all4_heading=4 alias_ok_to_heading_fail=113 aliases=45 sections=6 recovery_contract_corpus_stat=0 dispatch_card_stat_87.2=301/345 dispatch_card_stat_99.4=341/343 historical_instances_confirmed=6/6 tasks_md_now=443 worker_task_md_now=438
