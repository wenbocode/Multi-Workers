# 独立验证报告（T-6）：mw-worker-progress-persist

- Key: `mw-worker-progress-persist`
- Task: `T-6-VERIFY`（`.agenticdoc/mw-worker-progress-persist/tasks/T-6-VERIFY.md`）
- 执行角色: coding worker（工具面 `read/write/edit/bash/find/grep/ls`），任务 `mwpp-t6-independent-verify`
- 判定: **PASS-with-gaps**（VC-001~VC-011 全绿；3/3 变异反例均变红；4 条残留/缺口见 §5）
- 证据时间: 2026-09-23 16:52–16:58 (+08:00)
- 性质: 独立复核（不信 `[VERIFY]` 转述，全部命令在本机重跑；被审文件除 M-1/M-2/M-3 临时变异外未改）
- 源文件冻结哈希（本任务开始/结束均为同一值，见 §3.0）

结论单行：**11/11 VC 复现通过，3/3 变异反例变红并逐字节复原；无 FAIL，4 条低危缺口（schema 层真管道未覆盖、T-5 证据字节数笔误、pm 告警措辞陈旧、窄工具不计 writes）。**

---

## 0. 约束遵守与环境

- 本任务唯一写入的仓库文件 = 本报告；对源文件的改动仅 M-1/M-2/M-3 的临时变异，且已手工反向 `edit` 复原（§3 逐条给 sha256 相等证据）。
- 未 commit / 未 `git checkout|restore|stash|add -A`；未改 `dist/**`、未改 Python、未启停 `mw serve`、未跑 `mw build`；未跑 `./test.sh`、未跑全量 vitest。
- `git status --short` 在本任务开始与结束逐行相同（11 个已改路径 + 8 个未跟踪路径，无新增/缺失）。
- 工具链：`node v24.19.0`、`python 3.14.3`、`rg` = `C:\Users\wenbozhou\.pi\agent\bin\rg.exe`。
- 命令所在目录按任务书：vitest 在 `packages/coding-agent`，pytest 在 `packages/multi-workers`，`npm run check` 在仓库根。

---

## 1. VC 逐条表（VC-001~VC-011）

### VC-001 / VC-002 / VC-003 / VC-004 / VC-007

判定命令（原文，`packages/coding-agent` 下）：

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts test/extensions/agent-team-loop-worker-progress.test.ts
```

命令输出关键行（逐字复制）：

```
[VERIFY] VC-001: progress_exists=true machine_lines=1
[VERIFY] VC-002: machine_lines=2 sentinel_first=true
[VERIFY] VC-001: progress_exists=true machine_lines=1
[VERIFY] VC-002: machine_lines=1 sentinel_first=true
[VERIFY] VC-003: machine_lines=0
[VERIFY] VC-002: machine_lines=3 sentinel_first=true
[VERIFY] VC-004: writeless_write_instr=false coding_identical=true
[VERIFY] VC-007: table_unchanged=true extra_only_writeless=true types=10

 Test Files  2 passed (2)
      Tests  14 passed (14)
```

| VC | 独立判定 | 依据 |
|----|----------|------|
| VC-001 | **PASS** | 真 `writeCheckpoint` 闭包 + fake timers：`type: review` 过锚点后 `<taskDir>/progress.md` 存在且机器行匹配 `^CKPT \d+m \[machine\] ts=\S+ reads=\d+ writes=\d+ phases=(\d+\/\d+\|-) repeat_top=\d+ risk=(low\|mid\|high)$`；断言原文 `expect(machineLines(content)).toHaveLength(1)` + `.toMatch(MACHINE_LINE_RE)`（`checkpoint-wiring.test.ts:194-219`）。 |
| VC-002 | **PASS** | append-only 半侧由 `appendProgressLine` 直调 3 次锁定：预置 sentinel 后 `expect(lines).toEqual([sentinel, first, second])`、`content.length === sentinel.length+first.length+second.length+3`（无截断，P-003 规避）；集成半侧 1 个检查点 = 1 行机器行。 |
| VC-003 | **PASS** | `type: coding` 同锚点 `machineLines(codingContent)` 长度 0；且 steer 与 `checkpointSteerText({hasWriteTools:true,...})` 渲染结果 `toBe` 相等、`deliverAs==="followUp"`。**额外**：变异 M-2 让该用例变红（§3.2），证明断言真的在测该门禁。 |
| VC-004 | **PASS** | 渲染层双分支：writeless 文本 `not.toMatch(/追加到.*progress\.md/)`、含 `worker_file` 与 `converging=yes\|no`、含机器证据路径、`deliverAs==="followUp"`；coding 文本 `toBe(CODING_STEER_BASELINE)`。**独立复核基线**：我用 `git show HEAD:...worker-mode.ts` 抽出改前 steer 模板，与当前 `checkpointSteerText` 的 `hasWriteTools` 分支做「插值归一化」比较 → `NORMALIZED_EQUAL: true`（两段均 132 字符，逐字相同，仅 `${...}` 内表达式不同）。 |
| VC-007 | **PASS** | `toolsForType(type)` 对 10-key 快照 `toEqual`；`activeToolsForType(type)` = 快照 +（无 `write` 时）`worker_file`；未知 type 走 fallback；另有「每个已登记 type 在 `before_agent_start` **之后**读最终 active 集」的集成断言，且注册以 `worker.registered.includes(WORKER_FILE_TOOL) === expectsNarrow` 做结构性门禁。**额外**：变异 M-3 让 parity/一致性用例变红（§3.3）。 |

### VC-005 / VC-006

判定命令（原文，`packages/coding-agent` 下）：

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts
```

命令输出关键行（逐字复制）：

```
[VERIFY] VC-005: append_ok=true report_ok=true bytes_ok=true
[VERIFY] VC-006: rejections=12 new_files=0 schema_rejections=12
[VERIFY] D-102/D-109: schema_pattern_single_source=true additional_properties_rejected=true

 Test Files  1 passed (1)
      Tests  9 passed (9)
```

| VC | 独立判定 | 依据 |
|----|----------|------|
| VC-005 | **PASS** | 单元：`progress.md` append 到预置 sentinel 后（内容 === sentinel+appended）、`report.md`/`report-f1.md`/`report.r1.md` write 建/重写、字节数 = `Buffer.byteLength(..., "utf8")`。真管道（`createHarness` + faux provider，T-3 用例）：合法调用后 `results[0].isError===false`、文件内容 `"note 1\n"`、`trace.log` 出现含 `worker_file` 且含 `progress.md` 的 `[TOOL]` 行。 |
| VC-006 | **PASS**（结构性说明见下） | 12 项非法名逐项在**四层**断言：`isAllowedWorkerFile()===false`、`writeWorkerFile().ok===false`、`await expect(tool.execute(...)).rejects.toThrow(/rejected/)`、`Compile(pattern).Check()===false`；计数 `execRejections===12 && schemaRejections===12`；目录集合 `after===before`、`progress.md` 内容保持 `"sentinel\n"`；另有「execute 抛 `Error` 实例」「非法名/超容不创建 taskDir」。 |

**VC-006 的「独立 case」核对（任务书要求逐项列出实际存在的 name）**：`rejects.toThrow` **确实存在**（`worker-file-tool.test.ts:204-207`，循环内每项一次，带 per-item message）。但**不存在**「12 项反例各自一个 `it`」——全部 12 项落在**同一个** `it` 内用循环逐项断言（外加 schema 层用例 `:310` 再循环一次）。实际存在的 `it` name（共 9 个，`describe > it`）：

1. `WORKER_FILE_NAME_RE / isAllowedWorkerFile (D-102) > accepts the whitelist set and rejects non-whitelist neighbors`
2. `writeWorkerFile (VC-005) > VC-005: appends progress.md after a sentinel and writes report files; bytes match UTF-8 length`
3. `worker_file rejection (VC-006) > VC-006: all 12 illegal file values rejected at execute and schema layers, dir set unchanged`  ← 12 项循环在此
4. `worker_file rejection (VC-006) > execute throws an Error instance (D-109) and writes nothing`
5. `worker_file rejection (VC-006) > rejects fail-closed: no taskDir is created for an illegal name or oversize content`
6. `size and slug limits > caps content at 64 KiB UTF-8 bytes (multi-byte proof), accepts exactly the cap`
7. `size and slug limits > enforces the slug length boundary (41 allowed, 42 rejected)`
8. `registerWorkerFileTool (D-109 / §4.1) > execute defaults mode to append and reports path/bytes`
9. `registerWorkerFileTool (D-109 / §4.1) > schema layer accepts the legal set, rejects the 12 variants and extra fields, and reuses the regex source`  ← 12 项循环在此

12 项反例值（`REJECTED_FILES`，逐字）：`../x.md`、`a/b.md`、`..\x.md`、`C:\abs\x.md`、`\\unc\share\x.md`、`trace.log`、`task.md`、`output.md`、`worker.log`、`""`、`.md`、`report-.md`。每项均被 `isAllowedWorkerFile` / `writeWorkerFile` / `execute`（rejects.toThrow）/ `Compile(pattern)` 四层拒绝；M-1 反例证明该循环会整体变红。**未发现「有断言但漏项」或「绿但未检查」**。

### VC-008

判定命令（原文，`packages/multi-workers` 下）：

```
python -m pytest -q -s test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py test_mwpp_collection_parity.py
```

命令输出关键行（逐字复制）：

```
[VERIFY] VC-023: registry_parity=per-type-exact types=6 verifier_entry=explicit ts_buckets=['coding', 'fallback', 'research', 'review']
[VERIFY] VC-015: parity_unchanged=pass tools=11 conductor_dispatchable=false
[VERIFY] VC-015: l0_untouched=true
[VERIFY] VC-008: parity_pass=true snapshot_equal=true keys=10
.
28 passed in 1.15s
```

**判定：PASS**。`test_mwpp_collection_parity.py` 复用 `test_autopilot_l0::_parse_ts_allowlists`（未复制实现），锁定全部 10 个 key（含 legacy `coding/review/research` 与 `fallback`），`set(parsed)==set(expected)` 且逐 key `parsed[name]==expected`（保序）。`test_autopilot_l0.py` 的 L0 逐字节未被改动守卫（`test_rag_research.py` 的 `l0_untouched=true`）成立。

### VC-009

判定命令 1（原文，仓库根）：

```
npm run check
```

命令输出（逐字复制，非 tail）：

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1087 files in 550ms. No fixes applied.

> pi-monorepo@0.0.3 check:pinned-deps
> node scripts/check-pinned-deps.mjs

> pi-monorepo@0.0.3 check:ts-imports
> node scripts/check-ts-relative-imports.mjs

> pi-monorepo@0.0.3 check:shrinkwrap
> node scripts/generate-coding-agent-shrinkwrap.mjs --check

packages/coding-agent/npm-shrinkwrap.json is up to date.

> pi-monorepo@0.0.3 check:install-lock:coding-agent
> node scripts/generate-coding-agent-install-lock.mjs --check

packages/coding-agent/install-lock is up to date.

> pi-monorepo@0.0.3 check:browser-smoke
> node scripts/check-browser-smoke.mjs

EXIT=0
```

判定命令 2（受影响面，`packages/coding-agent`）：`test/extensions/agent-team-loop*.test.ts` 全量定向运行：

```
 Test Files  13 passed (13)
      Tests  430 passed (430)
EXIT=0
```

判定命令 3（受 T-3 同步面影响的 `test/suite` 8 文件：`autopilot-protocol` / `autopilot-read-scope` / `cross-drive-worker` / `dual-root-worker` / `rag-research-doc` / `rag-required` / `rag-tools` / `rag-evidence`）：

```
 Test Files  8 passed (8)
      Tests  83 passed | 1 skipped (84)
EXIT=0
```

基线对照（89 项 = agent 13 + coding-agent 76，AGENTS.md）：本 key 触达源文件 = `worker/worker-file-tool.ts`（新增）、`worker/worker-mode.ts`、`worker/output-writer.ts`、`rag/tools.ts`。冻结基线失败清单（`tmp/baseline-coding-agent.log` 53 failed/19 files、`tmp/coding-agent-vitest-full.log` 69 failed/23 files）的失败类别为 config self-update、model-registry shell 解析、external-editor、package-manager/paths、resolve-config-value、fswatch、footer、suspend、auth-storage、auto-compaction、dynamic-tools/extensions-runner、cloudflare-compat、resource-loader/sdk-session/trust、tools；对 `agent-team-loop` 的 grep 命中数为 **0**（`rg -c "agent-team-loop" tmp/*.log` 无输出）。→ **本 key 触达文件不在基线清单内，定向套件 0 新增失败（430+83+28 全绿）。** 受约束（禁 `./test.sh`/禁全量 vitest）未做 89 的全量重跑，故该点以「定向面 + 基线清单交集」判定，不宣称 89 全量复核。

**判定：PASS**（`check` exit 0；受影响测试全绿；触达面与基线清单零交集）。

### VC-010

判定命令（原文）：

```
rg -n 'progress\.md' packages/coding-agent/src packages/multi-workers --glob '!node_modules' --glob '!dist' --glob '!.agenticdoc'
```

逐命中判定：

| # | 位置 | 原文要点 | 陈述是否仍成立 |
|---|------|----------|----------------|
| 1 | `packages/multi-workers/CHANGELOG.md:41` | 发散判据改为「absence of a self-assessment line」；无 Python 行为变更 | **成立**（本 key 新增条目） |
| 2 | `packages/multi-workers/docs/dual-toolchain-practice-guide.md:367` | 表格行判据 = 「progress.md 无自评行（只有机器行）」 | **成立**（已按新语义改写） |
| 3 | `...practice-guide.md:369` | 只读角色机器行由框架写、`worker_file` 不计入 `writes`、发散只看是否有自评行/`repeat_top` | **成立**（与 D-104/D-105/D-108 及实现一致） |
| 4 | `worker-mode.ts:108` | 注释：有写工具角色「agent appends its own CKPT line … with its write tool」 | **成立**（`hasWriteTools===true` 分支确实如此） |
| 5 | `worker-mode.ts:991` | `progressPath: path.join(taskDir, "progress.md")` | **成立**（steer 指向的路径） |
| 6 | `worker-file-tool.ts:36` | 白名单单一来源含 `progress.md` | **成立** |
| 7-9 | `worker-file-tool.ts:87,93,100` | 工具描述/prompt/参数描述：`progress.md \| report.md \| report-<slug>.md`（basename） | **成立** |
| 10-12 | `output-writer.ts:213,226,234` | `formatMachineCheckpoint`/`appendProgressLine` 写入 `progress.md`，纯追加 | **成立** |
| 13 | `pm/pm-orchestrator.ts:556` | 告警证据行：`progress.md`（worker 自评） | **部分陈旧**：改造后只读角色的 `progress.md` 首行是框架机器行，可能**没有**自评行；此处仍把该文件概括为「worker 自评」。见 §5-G3。 |

CHANGELOG 核对（两包 `[Unreleased]`）：

- `packages/coding-agent/CHANGELOG.md` `[Unreleased] > ### Added` 含 1 条本 key 条目（窄工具 + 机器行 + 角色分化 steer + 需 `mw build --install` + `writes` 语义）。
- `packages/multi-workers/CHANGELOG.md` `[Unreleased] > ### Changed` 含 1 条本 key 条目（practice guide §7 发散判据更新、无 Python 行为变更）。
- 两处均为**追加**到既有子小节，未重开/重复小节。

**判定：PASS-with-note**（AC-010 明文范围 `packages/multi-workers` 内零悬空、0 处陈述失效；跨包 `pm-orchestrator.ts:556` 有 1 处措辞陈旧，记入 §5-G3）。

### VC-011

判定命令（原文，PowerShell，针对 T-5 保留的临时项目）：

```powershell
$dir = "C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5/.agenticdoc/_scratch/workers/mwpp-smoke-review-b"
[System.IO.File]::ReadAllText("$dir/progress.md")   # 机器行 + 自评行
[System.IO.File]::ReadAllText("$dir/trace.log")     # [CHECKPOINT] / [TOOL] worker_file / [END] exit=0
[System.IO.File]::ReadAllText("$dir/output.md")     # 禁词扫描
```

关键输出（逐字）：

```
# progress.md（UTF-8，第 1 行）
CKPT 1m [machine] ts=2026-09-23T08:49:18.818Z reads=16 writes=0 phases=- repeat_top=2 risk=high

# trace.log 中段
[CHECKPOINT] 2026-09-23T08:49:18.817Z elapsed=30s reads=16 writes=0 phases=- uniq_targets=0 repeat_top=2 risk=high
[FLOW] 2026-09-23T08:49:25.855Z tool_call worker_file
[TOOL] 2026-09-23T08:49:25.856Z worker_file progress.md
[END] 2026-09-23T08:49:28.058Z exit=0 elapsed=39s tools=18 phases=-

# worker.log
[worker] done exit=0 elapsed=39s tools=18 tool_errors=1

# output.md 禁词扫描
if ($out -match '无法写入|代为追加|PM 代记') { "MATCH (bad)" } else { "NO MATCH (good)" }
NO MATCH (good)
```

独立判定：T-5 的三条断言**在磁盘上有真实产物支撑**（非转述）：
- (a) `progress.md` 存在且含 `^CKPT \d+m \[machine\]` 行 —— 直接读文件命中（另含该 review worker 经 `worker_file` append 的自评行）。
- (b) `output.md` / `worker.log` 均不含 `无法写入|代为追加|PM 代记`。
- (c) `trace.log` `[END] … exit=0` 与 `worker.log` `done exit=0` 一致；模型 `deepseek-v4.1-flash`（`[MODEL]` 行）。
- run-1 假阴性目录（`…\workers\mwpp-smoke-review\`）也在盘上，`output.md` 存在但无 `progress.md`，与报告 §5.1「未命中检查点」自洽。

**一处转录偏差（见 §5-G2）**：T-5 报告 §3/§8 三次把自评文本写作 `（append，672 B）`，但磁盘 `output.md` 实际为 `（append，572 B）`（UTF-8 字节 `append\xef\xbc\x8c572 B`）。不影响 (a)(b)(c)。

**判定：PASS-with-note**（产物真实、三断言成立；报告字节数笔误 1 处）。

### PM 指定的三个待独立复核点

1. **schema 层拒绝（非法文件名）是否也落 `[TOOL_ERR]`（`agent-loop.ts:508-514`）**：代码路径逐段核实成立——
   - `packages/agent/src/agent-loop.ts:618` `validateToolArguments(tool, preparedToolCall)` 抛错 → 同函数 `catch` 返回 `{ kind: "immediate", result: createErrorToolResult(...), isError: true }`；
   - `:507-520` 的 `preparation.kind === "immediate"` 分支构造 `finalized = { …, isError: preparation.isError }` 并 `await emitToolExecutionEnd(finalized, emit)`；
   - `:763-771` `emitToolExecutionEnd` 发 `{ type: "tool_execution_end", …, isError: finalized.isError }`；
   - `worker-mode.ts:841-844` `tool_execution_end` 里 `if (!event.isError) return;` → `appendToolError(...)` 写 `[TOOL_ERR]`。
   → 结论：**schema 层拒绝与 execute 抛错走同一条 isError → `[TOOL_ERR]` 通路**。但**现有真管道用例只覆盖了 execute 抛错（oversize）**，schema 层经真管道未被覆盖 → 记 §5-G1。
2. **T-3 的真管道用例只覆盖 oversize 路径**：确认属实。`checkpoint-wiring.test.ts` 的真管道 `[TOOL_ERR]` 用例（`:414-437`）用 `"a".repeat(64*1024+1)`（过 schema、在 `execute` 内被 64 KiB 字节上限拒绝）；非法**文件名**的真管道路径没有用例（非法名只在 `worker-file-tool.test.ts` 直调 `execute`/`Compile` 层验证）。
3. **read-scope 拦截器对 `read/ls/find/grep` 之外的 tool 直接放行（`worker-mode.ts:761-790`）**：确认属实。`:763-770` 首个判断对非 `read/ls/find/grep` 的 `event.toolName` `return undefined`（不拦截）。因此 `worker_file` 不受 read-scope 约束——但 `worker_file` 只能写 worker 自身目录、无读能力，不构成「被审代码可被读/写」的破口（设计有意为之，非缺陷）。

---

## 2. 缺口与残留

### G1（中低）schema 层拒绝经真管道未被测试覆盖
`[TOOL_ERR]` 的 schema 分支（非法 `file` 名）只有静态代码路径证据（§1 复核点 1），真管道用例只走了 execute 抛错（oversize）。建议后续补一个「非法文件名 + 真 harness」用例；当前不构成 FAIL（execute 层已有直调断言，且两层共用同一 `WORKER_FILE_NAME_RE.source`）。

### G2（低）T-5 冒烟证据有 1 处字节数笔误
`evidence/verify-run-2026-09-23.md` 第 179/305/309 行写 `（append，672 B）`，磁盘 `output.md` 实际为 `572 B`。三断言 (a)(b)(c) 不受影响，但「逐字复制」声明应更正。

### G3（低）PM 发散告警对 `progress.md` 的措辞陈旧
`pm/pm-orchestrator.ts:556` 仍把 `progress.md` 括注为「worker 自评」。改造后只读角色该文件首行是框架机器行，可能完全没有自评行；措辞宜改为「机器行 +（可选）worker 自评」。该文件在 `packages/coding-agent`，不在 AC-010 明文范围（`packages/multi-workers`）内，故 VC-010 不因此降级。

### G4（设计残留，非缺陷）窄工具写入不计 `writes` → 只读角色 `risk` 偏高
D-108 有意让 `writes` 只统计 `write/edit`（保住「零产出」信号）。副作用：只读角色**确实**通过 `worker_file` 落了报告，`writes` 仍为 0，`computeRisk` 在锚点后仍判 `high`，PM 会收到一次发散升级（每个 taskKey 一次，`escalated` 去重）。spec §9 已明示该残留，判定靠 PM 上下文；此处仅记录。

### 其他观察（不构成缺口）
- `report.<slug>.md` 与 `report-<slug>.md` 双形式：spec/AC 只要求 `progress.md` + 报告文件，双分隔符是 T-2 合法用例（`report.r1.md`）逼出的放宽；可写作「最小面」，但无安全问题（仍仅 basename、仍禁 `task.md`/`trace.log`/`output.md`/`worker.log`）。
- 机器行与自评行的交错顺序：机器行在检查点时刻由框架写入，自评行随后（steer 为 `followUp`）。若 worker 跨多个检查点不回复 steer，会出现连续机器行；AC-002 的「K 检查点 = K 机器行」集成侧只覆盖 K=1，K>1 的 append-only 由单元 3 连追加覆盖。行为正确，覆盖略保守。
- `research` 角色同时有 `bash` 与 `worker_file`：其「只读」本来就非绝对（bash 可写盘），本 key 未改变该既有语义。

---

## 3. 变异反例（M-1 / M-2 / M-3）

### 3.0 源文件冻结哈希

| 文件 | 改前 sha256（= 本任务开始与结束） |
|------|-----------------------------------|
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts` | `14BB5229AE84B3C9EB8CA80B6586901EAED6A17AD2438081A39504311CD89ED9` |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | `93E34050526FA406434B19D4EA59A7F63175FF8FD2DD673A18B0D1C33AF59085` |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts` | `103E6A1E10CC2B77396C26041DD9A39A8FC3C60AA9A6332F889CE38ADF9EA975` |
| `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts` | `1FDC684ED6B498381F904C39D6E799F4F56EDAC51D9044C35E5CA52898D48561` |

（全部为 LF 行尾：`worker-file-tool.ts` 120 LF/0 CRLF、`worker-mode.ts` 1170 LF/0 CRLF；变异与复原用同一 `edit` 工具逐字反向改回。）

### 3.1 M-1 放宽白名单 → worker-file-tool 测试必须变红

- 改动：`WORKER_FILE_NAME_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/` → `/^.+\.md$/`（`worker-file-tool.ts:41`）。
- 改后 sha256：`1EFAEA780B8472166C2EBDD3AB35544D093EC86C709CB6D1FBEFA52CD195BCD5`
- 命令（原文，`packages/coding-agent`）：

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts
```

- 输出关键行（逐字复制）：

```
 Test Files  1 failed (1)
      Tests  6 failed | 3 passed (9)
EXIT=1
FAIL  test/extensions/agent-team-loop-worker-file-tool.test.ts > WORKER_FILE_NAME_RE / isAllowedWorkerFile (D-102) > accepts the whitelist set and rejects non-whitelist neighbors
FAIL  test/extensions/agent-team-loop-worker-file-tool.test.ts > worker_file rejection (VC-006) > VC-006: all 12 illegal file values rejected at execute and schema layers, dir set unchanged
FAIL  test/extensions/agent-team-loop-worker-file-tool.test.ts > worker_file rejection (VC-006) > execute throws an Error instance (D-109) and writes nothing
FAIL  test/extensions/agent-team-loop-worker-file-tool.test.ts > worker_file rejection (VC-006) > rejects fail-closed: no taskDir is created for an illegal name or oversize content
FAIL  test/extensions/agent-team-loop-worker-file-tool.test.ts > size and slug limits > enforces the slug length boundary (41 allowed, 42 rejected)
FAIL  test/extensions/agent-team-loop-worker-file-tool.test.ts > registerWorkerFileTool (D-109 / §4.1) > schema layer accepts the legal set, rejects the 12 variants and extra fields, and reuses the regex source
```

- **结论：红**（6 failed）。
- 复原后 sha256：`14BB5229AE84B3C9EB8CA80B6586901EAED6A17AD2438081A39504311CD89ED9` = 改前（逐字节相等 ✓）。

### 3.2 M-2 去掉角色判据（无条件写机器行）→ coding 用例必须变红

- 改动：`worker-mode.ts::writeCheckpoint` 内 `if (!hasWriteTools) {` → `if (true) { // MUTANT M-2`（`:967`）。
- 改后 sha256：`AA4F754C4222B0814A8A026E40EA05A4B36A830FF182B1B3BF0791C90AD345B0`
- 命令（原文）：

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts
```

- 输出关键行（逐字复制）：

```
 Test Files  1 failed (1)
      Tests  1 failed | 8 passed (9)
EXIT=1
FAIL  test/extensions/agent-team-loop-checkpoint-wiring.test.ts > checkpoint machine line by role (VC-001/002/003) > VC-003: type=coding writes no [machine] line at the same anchor
AssertionError: expected [ Array(1) ] to have a length of +0 but got 1
 ❯ test/extensions/agent-team-loop-checkpoint-wiring.test.ts:229:40
```

- **结论：红**（失败用例 = `VC-003: type=coding writes no [machine] line at the same anchor`）。
- 复原后 sha256：`93E34050526FA406434B19D4EA59A7F63175FF8FD2DD673A18B0D1C33AF59085` = 改前（逐字节相等 ✓）。

### 3.3 M-3 破坏 parity（把 `worker_file` 加进 `TOOL_ALLOWLISTS.review`）→ Python parity 必须变红

- 改动：`worker-mode.ts:54` `review: ["read", "find", "grep", "ls"],` → `review: ["read", "find", "grep", "ls", "worker_file"],`。
- 改后 sha256：`7A853C6513C4DE04E0A4E5D4C8CB2DAB8967E384D652DD9A2FD5EC6914C32A7B`
- 命令 A（原文，`packages/multi-workers`）：

```
python -m pytest -q -s test_mwpp_collection_parity.py
```

输出关键行（逐字复制）：

```
E           AssertionError: review: ts=['read', 'find', 'grep', 'ls', 'worker_file'] expected=['read', 'find', 'grep', 'ls'] (order-exact required)
FAILED test_mwpp_collection_parity.py::test_vc008_allowlist_snapshot_unchanged
1 failed in 0.11s
PARITY_EXIT=1
```

- 命令 B（原文）：`python -m pytest -q test_autopilot_l0.py`

```
FAILED test_autopilot_l0.py::test_vc023_worker_fail_closed
1 failed, 4 passed in 1.04s
L0_EXIT=1
（内嵌 vitest 失败：test/suite/autopilot-protocol.test.ts > typed tool allowlists (D-107 / VC-023) > GC-8/AC-012: manual and pre-existing types keep their sets — unknown manual types fall back to the full set）；
AssertionError: m-review: expected [ 'read','find','grep','ls', …(2) ] to deeply equal [ 'read','find','grep','ls', …(1) ]  → 收到两份 "worker_file"
```

- **结论：红**（两个 parity 目标均红：`test_mwpp_collection_parity.py::test_vc008_allowlist_snapshot_unchanged` 与 `test_autopilot_l0.py::test_vc023_worker_fail_closed`）。
- 复原后 sha256：`93E34050526FA406434B19D4EA59A7F63175FF8FD2DD673A18B0D1C33AF59085` = 改前（逐字节相等 ✓）。
- **复原后回绿**（原文）：

```
python -m pytest -q -s test_mwpp_collection_parity.py test_autopilot_l0.py
[VERIFY] VC-008: parity_pass=true snapshot_equal=true keys=10
[VERIFY] VC-023: worker_fail_closed=1 ts_suite=autopilot-protocol.test.ts ts_run=passed manual_fallback=full-set
6 passed in 0.98s
PARITY_REGREEN_EXIT=0
```

回绿时 `worker-mode.ts` sha256 仍为 `93E34050526FA406434B19D4EA59A7F63175FF8FD2DD673A18B0D1C33AF59085`。

---

## 4. VC 判定计数

| 判定 | 数量 | VC |
|------|------|----|
| PASS | 9 | VC-001、VC-002、VC-003、VC-004、VC-005、VC-006、VC-007、VC-008、VC-009 |
| PASS-with-note | 2 | VC-010（G3 跨包措辞）、VC-011（G2 字节数笔误） |
| FAIL / 证据不足 | 0 | — |

变异反例：M-1 红、M-2 红、M-3 红（3/3），全部逐字节复原；M-3 复原后 parity 回绿。

---

## 5. 缺口清单（汇总）

- **G1 中低**：schema 层非法文件名拒绝经真管道未被测试覆盖（仅静态代码路径 + 直调 schema 断言）。
- **G2 低**：T-5 冒烟证据 `verify-run-2026-09-23.md` 的 `672 B` 与磁盘 `output.md` 实际 `572 B` 不符（转录笔误，三断言不受影响）。
- **G3 低**：`pm-orchestrator.ts:556` 发散告警仍把 `progress.md` 概括为「worker 自评」，与只读角色「框架机器行为首行」的新形态不完全一致。
- **G4 设计残留**：窄工具写入不计 `writes`（D-108 有意为之）→ 只读角色即便落了报告 `risk` 仍可能 `high`；spec §9 已明示，靠 PM 上下文裁决。

未发现「测试通过但功能未接线」「绿但漏拦」「parity 单侧」类缺陷；未发现任何 VC 证据不足。
