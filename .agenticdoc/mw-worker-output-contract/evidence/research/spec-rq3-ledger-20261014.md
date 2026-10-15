# RQ3：变更账本（change-ledger）与 `[WRITE_FILE]` 的全部消费者（research 取证）

- Key: `mw-worker-output-contract`；worker: `woc-rq3-ledger`；card: `.agenticdoc/mw-worker-output-contract/tasks/T-RQ3-ledger.md`
- 目标锚点：`.agenticdoc/goal.md`（文件驱动的去中心化协调）。
- 只读边界：**未修改仓库任何文件**；未跑 `npm install/ci`、`git checkout|reset|clean|stash`、`npm run build`、全量 `./test.sh`。
- 方法：`read` 全量读源码 + `rg` 定位；Node v24.19.0 直接 `import` `packages/coding-agent/dist/extensions/agent-team-loop/**`（已构建产物，只读执行）复跑抽取器与账本判据；Python 3.14 只读脚本统计；真实命令从 pi 会话 JSONL（`~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-13T17-10-*.jsonl`）取出。
- **重要取证前提**：`trace.log` 的 `[TOOL]` 行**不是命令的可靠来源**（`output-writer.ts:431` `truncLine(target, 80)`，且 `toolTarget()` 只取命令首行，`worker-mode.ts:539-558`）；`[WRITE_SCOPE]` 的 `cmd=` 也只保留 `command.replace(/\s+/g," ").trim().slice(0,200)`（`worker-mode.ts:1699`）。本报告用会话 JSONL 的 `arguments.command` 原文复跑。

---

## 0. 结论先行

1. **抽取器只有一处实现**：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:1554 extractBashWriteCandidates()`（dist 侧为 `worker-mode.js:1337`）；它把 token 流交给 `extractFromTokens`（`:1181`）与 `extractCommand`（`:1251`），产出 `{target, pattern, verbatim}`。**pattern 标签共 41 种**（3 个 redirect 族 + `inline-script` + ~37 个命令/flag 形态），完整清单见 §1。**没有 `--glob`/带空格/`+`/坐标片段的形状校验**，也没有 `python -`（stdin）与 PowerShell here-string 的专门处理。
2. **伪行机制是“shell 词法状态被 PowerShell here-string 打乱 + 目标原样记账”**：`tokenizeShellCommand`（`:791`）不知道 `@'…'@`；`@'` 的 `'` 打开一个 shell 单引号串，之后 `'`/`"` 的配对整体错位，Python 源码里的 `->` 被当成重定向操作符（`:1222 add(next,"redirect")`），其后的反引号/`+` 片段成为 target。随后 `tool_execution_end`（`:2383-2385`）**对非 verbatim（allow-unknown）目标也照样** `appendWriteFileEvent`，于是乱码进账本。
3. **rq1 的 0 行是双重原因**：(a) 真实写入用的是 `[System.IO.File]::WriteAllText/AppendAllText`（122 条 bash 里 24 条），抽取器无任何 .NET 写 API 分支；(b) 记录到该文件的 3 条命令反而因 here-string 正文里的 `--glob '!node_modules'` 被误判为重定向目标而 **被写面守卫 blocked**（`[WRITE_SCOPE_SUMMARY] allow=0 deny=3`），命令报错、不落事件。成功写入的那些命令抽取候选 = 0。
4. **消费者共 7 处**（全部在 TS 侧，无 Python）：`parseWriteFileEvents`（`change-ledger.ts:148`）→ `diffLedger`（`:827`，`:875-877` 的 zero-event `unjudgeable` 闸）→ `readTerminalGaps`（`output-writer.ts:172`，`:220-222`/`:238`）→ `writeOutput` 的 `## Ledger Gaps`/`## Ledger Unjudgeable` 等段与 `## Questions` 首行（`output-writer.ts:257-315, :351-356`）→ settle 的 exit code / reason（`worker-mode.ts:2740-2760`）→ PM 回读 `readTerminalDetail`（`pm/ui-bridge.ts:585`，用点 `:789`）。**`mw doctor` 与 Python 侧完全未解析 `[WRITE_FILE]`**（见“未找到清单”）。
5. **`unjudgeable` 现状是“零事件 trace 的派生布尔”**，不是 trace 事件：`diffLedger` 在 `recorded.length === 0` 且存在 judgeable 声明时置 `unjudgeable: true`（`change-ledger.ts:875-877`）；`readTerminalGaps` 再把它展开成 `unjudgeableFiles`（`output-writer.ts:220-222`）。**因此当前实现里“有乱码 `[WRITE_FILE]`”会被当成有记录**（`recorded.length > 0`），根本进不了 `unjudgeable` 分支——这正是 AC-008 要修的语义缺口。
6. **形状校验过严的现实对照**：仓库**文件名**层面含空格/`+`/中文/`@`/`~` 的路径 = **0**（walk 7921 项）；但 `.agenticdoc` **内容**里真实出现且会被 `PATH_SHAPE_RE`/`isPathCandidate` 拒绝的形态很多：`H:\git\...`（382 行）、`C:\Users\...`（1720 行）、`C:\Users\WENBOZ~1\...`（87 行）、`D:\Program Files\...`（12 行）、`~/.pi`（190 行）、`~/.agents`（51 行）、`workers-ai/@cf/...`（5 行）。dist 复跑确认：反斜杠/空格/`~`/`@`/中文/`+` 全部落 `malformed`，只有正斜杠盘符形式（`H:/git/...`）被判为声明。

---

## 1. 壳层写目标抽取器：实现位置与完整规则

### 1.1 入口与签名

| 项 | 位置 | 原文 |
|---|---|---|
| 入口 | `worker-mode.ts:1554-1558` | `export function extractBashWriteCandidates(command: string): BashWriteCandidate[] {` / `const out: BashWriteCandidate[] = [];` / `extractFromTokens(tokenizeShellCommand(command), 0, out, new Set(["{}"]));` / `return out;` |
| 返回类型 | `worker-mode.ts:729-744` | `export interface BashWriteCandidate {` / `target: string;` / `pattern: string;` / `verbatim: boolean;` |

### 1.2 Token 词法（`ShellToken.verbatim` 的唯一来源）

| 项 | 位置 | 原文 / 规则 |
|---|---|---|
| `ShellToken` | `worker-mode.ts:777-782` | `interface ShellToken { text: string; operator: boolean; verbatim: boolean; }` |
| live 字符集 | `worker-mode.ts:787` | `const LIVE_EXPANSION_CHARS = new Set(["$", "`", "*", "?", "[", "{"]);` |
| 分词器 | `worker-mode.ts:791-864` | `const append = (ch, live) => { word += ch; if (live && (LIVE_EXPANSION_CHARS.has(ch) \|\| (ch === "~" && word.length === 1))) inert = false; }`（`:796-799`） |
| 单/双引号 | `:807-826` | 单引号内 `append(command[i], ch === '"')` → 单引号完全 inert；双引号内仍 live（`$`/反引号/glob） |
| 反斜杠转义 | `:828-833` | `append(command[i + 1], false)` → inert |
| 双引号转义 | `:2890-2898` `appendDoubleQuoteEscape` | 仅 `$`/反引号/`"`/`\` 被消费并 inert，其他反斜杠字面保留 |
| 操作符 | `:841-853` | `> < \| ; & ( )` 各自成 operator token；`\n` 变 `;` 并由 `markLineBreak` 打标（`:2922`） |
| 命令 basename | `:2906-2914` | 去 `.exe`、按 `[\\/]` 取尾、lowercase |

### 1.3 `verbatim` 的计算（逐条）

1. **词法默认**：token 从 `inert = true` 起，遇到未引用的 live 字符（`$` `` ` `` `*` `?` `[` `{`，或词首 `~`）→ `verbatim = false`（`worker-mode.ts:796-799`）。
2. **显式 override**：`add()`（`:1187-1199`）签名 `(source, pattern, verbatimOverride?)`，`let verbatim = verbatimOverride ?? (typeof source === "string" ? true : source.verbatim);`（`:1190`）。
3. **opaque 占位符再降级**：若 `verbatim` 且值包含 `{}` 或 `xargs -I`/`-i` 占位符 → `verbatim = false`（`:1191-1197`；占位符来自 `skipWrapperPrefix`，`:1119-1174`）。
4. **显式 override 的调用点**：
   - `inline-script`：`script.verbatim && !/[$`]/.test(value)`（`:1274`）。
   - `sed -i`/`perl -i` 的带后缀目标：`token.verbatim && suffixVerbatim`（`:1328`、`:1472`）。
   - `dd of=`、`tar -c`、`curl -o --output=`、`wget -O --output-document=` 传 `token.verbatim`（`:1401`、`:1446`、`:1516`、`:1528`）。
   - 其余（`redirect`/`tee`/`cp`/…）不传 override ⇒ 用 `source.verbatim`。

### 1.4 全部 pattern 标签及其判定（以代码为准）

**A. redirect 族（`extractFromTokens`，`:1206-1249`）**

| pattern | 触发条件 | 行号 |
|---|---|---|
| `redirect` | `>`/`>>` operator 且下一 token 非 operator（比较上下文 `((`/`[[` 深度为 0） | `:1220-1222` |
| `redirect-clobber` | `>` 后跟 `\|` operator 再跟非 operator token（`>\|`） | `:1226-1227` |
| `redirect-fd-target` | `>` 后跟 `&` 且再下一个不是纯数字、不是 `-`（`>&`） | `:1228-1230` |

**B. inline 脚本（`extractCommand` 的 `python/python3/py/node`、`perl`、`ruby` 分支）**

| pattern | 判定 | 行号 |
|---|---|---|
| `inline-script` | `matchInline(INLINE_WRITE_PATTERNS \| PERL_INLINE_PATTERNS \| RUBY_INLINE_PATTERNS, script.text)`，且 payload 由 `-c`/`-e`/`--eval`/`-p`/`--print` 旗标给出（`scriptPayloadFlag`，`:1087-1103`）；**`python -`（stdin）与 bash here-doc 不在内** | `:1272-1275`、`:1344`、`:1350-1355`、`:1363-1366` |
| `INLINE_EXEC_PATTERNS` 递归 | `os.system/popen`、`subprocess.*`、`execSync/exec/spawn*` 捕获的字符串再 `recurseShell` | `:1279-1290`、`:1345` |

**C. 命令/flag 形态（`extractCommand` switch，`:1291-1553`）**

| pattern | 判定（要点） | 行号 |
|---|---|---|
| `tee` | 所有非 `-` 开头 operand | `:1348-1351` |
| `cp` / `mv` | `-t`/`--target-directory` 值，否则最后一个 positional | `:1353-1363` |
| `rm` / `mkdir` / `touch` / `truncate` | 所有 positional（`positionals()` 做 arity-aware flag 跳过） | `:1365-1370` |
| `install` / `install -t` | 有 `-t` 时目录 + 所有 positional；否则最后 positional | `:1371-1380` |
| `ln` / `ln -t` | 有 `-t` 时目录；否则需 ≥2 positional 取末 | `:1381-1391` |
| `rsync` | ≥2 positional 取末 | `:1392-1396` |
| `dd of=` | operand 匹配 `/^of=(.*)$/` | `:1398-1402` |
| `tar -c` / `tar -C` / `tar -x` | `-f`/`--file[=]` 为 archive，`-c` 时取 archive；`-x` 且有 `-C` 时取目录，否则 `.` | `:1404-1447` |
| `sed -i` | 有 `-i`/`--in-place[=]` 时，`positionals` 从第 2 个起（跳过脚本参数）；后缀 `-i$S` 另加一个目标 | `:1448-1474` |
| `perl -i` | 同上，perl 版 | `:1291-1332` |
| `find -delete` | roots（非 `-`/`!` 前缀的 operand，缺省 `.`）+ `-delete` | `:1475-1499` |
| `-exec/-execdir` 递归 | 子 token 再 `extractFromTokens`（深度 < 3） | `:1486-1495` |
| `git checkout` / `git apply` / `git clean` / `git restore` | 子命令白名单；无 path 记 `.`，否则每条 path | `:1500-1507` |
| `curl -o` / `curl --output=` | 输出目标 | `:1508-1518` |
| `wget -O` / `--output-document=` | 输出目标 | `:1519-1529` |
| PowerShell 裸名 | `set-content` / `add-content` / `clear-content` / `out-file` / `new-item` / `remove-item`（`POWERSHELL_WRITE_COMMANDS`，`:1036-1042`）：非 flag 且前一 token 不是 flag 的 operand | `:1530-1547` |
| PowerShell `-Path` 形态 | 旗标 `-path`/`-literalpath`/`-filepath`/`-destination`（`POWERSHELL_PATH_FLAGS`，`:1044`）后的值 ⇒ pattern = `${commandName} -Path` | `:1537-1540` |

**D. wrapper 与 heredoc**

| 项 | 位置 | 规则 |
|---|---|---|
| wrapper 集 | `:866-875` | `COMMAND_WRAPPERS`（sudo/env/command/nohup/time/nice/stdbuf/xargs/doas/timeout/setsid）；`bash/sh/zsh/dash/ksh`、`cmd`、`powershell/pwsh` 递归 payload（`:1285-1290`） |
| 深度上限 | `:875`、`:1269` | `MAX_UNWRAP_DEPTH = 3` |
| 空目标 | `:1024-1034` | `NULL_WRITE_TARGETS`（`/dev/null` 等）`add()` 内直接丢弃 |
| heredoc 体 | `:2927-2976` `dropHeredocBodies` | 逐物理行识别 `<<`/`<<-` 分隔符并丢掉体区间；`(( ))` 内的 `<<` 视作移位；`<<<` 不处理 |

**E. 未被识别的真实写入形态**（见 §2 的 rq1）：`[System.IO.File]::WriteAllText/AppendAllText`、`python -`（stdin heredoc）、`$code = @'…'@` here-string 包裹的任何写入、`Set-Content` 之外的 .NET/CMD 写法。

---

## 2. 伪行的确切产生路径（可复现输入 + 推导）

### 2.1 真实命令来源（不是 `[TOOL]` 行）

- `wfg-rq2-enforcement` 的伪行/证据在 `trace.log:252-255`：
  - `:252` `[WRITE_SCOPE] … rule=allow-unknown detail=target-not-statically-determinable pattern=redirect target=`:1175 cmd=$py = @' import pathlib … subs = [ (`
  - `:254` `[WRITE_FILE] path=`:1175`；`:255` `[WRITE_FILE] path=`:1184`
- `wfg-rq3-safety` 在 `trace.log:301/350`（`target=, .agenticdoc/_aut + opilot)`）与 `:308/:357`（`[WRITE_FILE] path=, .agenticdoc/_aut + opilot)`）；`:309-314` 是该 target 里的换行溢出的续行。
- 会话来源：rq2 = `~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-13T17-10-27-550Z_…jsonl`（toolCall id `call_00_1mxTvF8gwpATetKub8789160`，17:17:03）；rq3 = `…/2026-10-13T17-10-42-324Z_…jsonl`（`call_00_UTnPSl2jT1i3j35dDhM07857`，17:19:56；`call_00_E2YFUi9JXvXGnnWGz1B11122`，17:21:58）。

### 2.2 机制（三步）

1. **词法错位**：命令是 PowerShell here-string
   ```powershell
   $py = @'
   …python…
   subs = [ ('-> `:1175 release`', '-> `:1184 release`'), … ]
   '@
   $py | python -
   ```
   shell 分词器把 `@'` 的 `'` 当作单引号起点，直到 Python 源码里的下一个 `'` 才闭合；此后所有 `'`/`"` 的奇偶整体错位。
2. **正文 `->` 被当重定向**：错位后 `-> ` 中的 `>` 显式成为 operator token，紧跟的词 `` `:1175 `` / `` `:1184 `` 成为 `add(next, "redirect")` 的 target。
3. **非 verbatim 仍记账**：反引号是 live 字符 ⇒ `verbatim=false` ⇒ `checkBashWriteScopeTarget` 返回 `allow-unknown`；但 `tool_execution_end`（`worker-mode.ts:2383-2385`）对 `bashWrites` **无条件**逐条 `appendWriteFileEvent(tracePath, repoRelativePath(t))`，`appendWriteFileEvent`（`change-ledger.ts:123-130`）又不做任何形状/非 verbatim 过滤 ⇒ 乱码落成合法 `[WRITE_FILE] path=…`。

### 2.3 最小可复现输入（Node + dist 抽取器实测）

工具：`node` 导入 `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` 的 `extractBashWriteCandidates`（与 src 同算法）。

**rq2（精确复现两条伪行）** —— 55 字符、2 行：

```text
$py = @'
 ('-> `:1175 release`', '-> `:1184 release`'),
```

输出：
```json
{"target":"`:1175","pattern":"redirect","verbatim":false}
{"target":"`:1184","pattern":"redirect","verbatim":false}
```

进一步最小化（单条）—— **13 字符**、1 行可省为 2 行：

```text
@'
'-> `:1175
```
→ `{"target":"`:1175","pattern":"redirect","verbatim":false}`（关键条件：`@'` 制造一个未闭合引号，紧邻 `->` 的那个 `'` 将其闭合，使 `>` 暴露为操作符）。

**rq3（复现 `, .agenticdoc/_aut + opilot)`）** —— 4 行、319 字符（行缩略掉行尾即原命令相关片段）：

```text
$code = @'
[VERIFY] RQ-W3: self_guard_hit=1 (xkey-gate-guard blocked this worker's own evidence-write command: quote-of-autopilot-dir plus PowerShell delete cmdlet inside here-string, a false positive; bypassed by splitting the quoted literal)
"""
CHUNK = CHUNK.replace("<AUTOPILOT_DIR>", ".agenticdoc/_aut" + "opilot")
```

输出 `{"target":", .agenticdoc/_aut + opilot)","pattern":"redirect","verbatim":true}`；把尾行 `$code | python -` 加回（5 行、336 字符）则 `verbatim=false`（与真实 trace 的 allow-unknown 一致），target 为 `", .agenticdoc/_aut + opilot)\n$code | python -"`。
- **注意 `verbatim` 差异**：真实命令的 target 一直延伸到整段命令尾部（含 `$code` 等 live 字符）⇒ `verbatim=false`；最小化到 4 行时未含 live 字符 ⇒ `verbatim=true`。`[WRITE_FILE]` 记录只看 `target`，两种都落同一首行值；`[WRITE_SCOPE]` 的 `allow-unknown` 则依赖 `verbatim=false`。
- **换行注入**：`formatWriteFileEvent`（`change-ledger.ts:115-117`）= `[WRITE_FILE] path=${filePath}`，target 含 `\n` 时 trace 物理行被切开（`trace.log:308` 的记录值只是首行，`:309-314` 是污染续行）；解析器 `WRITE_FILE_LINE_RE`（`:135`）逐行锚定，续行不会二次成事件。

### 2.4 `wfg-rq1-write-face-sources` 为何 0 行（双重原因，实测）

- 会话共 **122** 条 bash toolCall；其中 **24** 条用 `[System.IO.File]::WriteAllText` / `AppendAllText` 写证据文件；`Set-Content` = 0。
- 抽取器对这 122 条命令共产出 **8** 个候选，全部是伪目标：`--glob`（3 条命令）与反引号片段（1 条命令）；**没有一条**指向真实证据文件。
- 这 3 条含 `--glob`（来自 here-string 正文里的 `--glob '!node_modules'`）的命令被写面守卫 **blocked**：`trace.log:266/352/357 [WRITE_SCOPE] blocked=true rule=scope … target=--glob`，`[TOOL_ERR] write-scope: blocked bash write to --glob`，结尾 `[WRITE_SCOPE_SUMMARY] allow=0 deny=3 allow-unknown=0`。
- 结论：**rq1 的 0 行 = 真实写 API（.NET）不可分类 + 3 条写命令被伪目标误 block**；成功写入的批次产出 0 候选。FW-009 只提到前一半，后一半是本次新增的实测事实（对 AC-008 的“0 伪行 + ≥1 unjudgeable”是额外约束：修 `--glob` 伪目标也会顺带解除该误 block）。
- 其余对照：`wfg-rq-d1` 8 行全部真实（`worker_file` 的 `progress.md`/`report.md`）；`wfg-rq-d2` 4 行真实（`report.md` + `evidence/research/design-runtime-guard-20261014.md`）。

---

## 3. `[WRITE_FILE]` 与 `unjudgeable` 的全部消费者

### 3.1 生产端（谁写这行）

| 位置 | 原文 / 语义 |
|---|---|
| `shared/change-ledger.ts:111` | `export const WRITE_FILE_EVENT = "[WRITE_FILE]";` |
| `shared/change-ledger.ts:115-117` | `export function formatWriteFileEvent(filePath) { return \`${WRITE_FILE_EVENT} path=${filePath}\`; }` |
| `shared/change-ledger.ts:123-130` | `appendWriteFileEvent(tracePath, filePath)`：`fs.appendFileSync(tracePath, \`${formatWriteFileEvent(filePath)}\n\`, "utf8")`，best-effort |
| `worker/worker-file-tool.ts:82` | `appendWriteFileEvent(path.join(taskDir, "trace.log"), repoRelativePath(target));`（`worker_file` 通道） |
| `worker/worker-mode.ts:2375-2376` | `write`/`edit` 成功：`appendWriteFileEvent(tracePath, repoRelativePath(writeTarget))` |
| `worker/worker-mode.ts:2383-2385` | 壳层成功：`for (const bashTarget of bashWrites ?? []) { if (bashTarget === "") continue; appendWriteFileEvent(tracePath, repoRelativePath(bashTarget)); }` |
| `worker/worker-mode.ts:2356-2359` | `pendingBashWrites.set(event.toolCallId, extractBashWriteCandidates(command).map((c) => c.target))`（**丢弃 verbatim/pattern**） |

### 3.2 消费者（按调用链）

1. **唯一解析器**：`shared/change-ledger.ts:148-158 parseWriteFileEvents`，正则 `WRITE_FILE_LINE_RE = /^\[WRITE_FILE\][ \t]+path=(.+?)[ \t]*$/`（`:135`）。文本进、路径数组出，绝不抛。
2. **判据（`declared ⊆ recorded`）**：`shared/change-ledger.ts:827-879 diffLedger`。
   - `recordedEvents = parseWriteFileEvents(traceText)`（`:832`）。
   - 三方拆分 `unrecorded → infra / unresolvable / judgeable`（`:855-867`）。
   - **`unjudgeable` 判定点**：`:875-877`
     ```ts
     if (recorded.length === 0) {
       return { declared, recorded, extra: [], infra, unresolvable, unjudgeable: judgeable.length > 0 };
     }
     return { declared, recorded, extra: judgeable, infra, unresolvable, unjudgeable: false };
     ```
     即“**零事件 + 存在已存在且非 infra 的声明** ⇒ `unjudgeable`；有任一事件 ⇒ `unjudgeable=false`（无论事件内容是否为乱码）”。
3. **运行期汇总**：`worker/output-writer.ts:172-240 readTerminalGaps`。
   - `:220-222` `const unjudgeableFiles = ledger.unjudgeable ? ledger.declared.filter((file) => !infraSet.has(file) && !unresolvableSet.has(file)) : [];`
   - `:238` `ok: missingSections.length === 0 && ledger.extra.length === 0 && unjudgeableFiles.length === 0`
   - `:257-259`：`writeOutput` 在未显式传 `terminalGaps` 时自行调用 `readTerminalGaps`。
4. **产物段与回读行**：`worker/output-writer.ts`
   - `:267` `ledgerNote = 未记录写入：…`（红）
   - `:271-272` `unjudgeableNote = 未记录写入（不可判）：…`
   - `:315` `terminalNote = [gapNote, ledgerNote, unjudgeableNote].join("；")`（只这三类进 `## Questions` 首行，供 PM 回读）
   - `:352` `## Ledger Gaps`；`:353` `## Ledger Unjudgeable`；`:354` `## Ledger Malformed`；`:355` `## Ledger Infra`；`:356` `## Ledger Unresolvable`
   - `:282/:296/:312` 三条 `[FLOW] ledger-malformed|ledger-infra|ledger-unresolvable` trace 行（warn 通道）
5. **settle 的 exit code 与 reason**：`worker/worker-mode.ts`
   - `:2740-2745` `const gaps = readTerminalGaps({ …, judgeRecovery: isWritelessRole(meta.type) || reportProduct });`
   - `:2746` `const exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2;`
   - `:2756-2760` `unjudgeableReason = \`unjudgeable write(s) (trace has no [WRITE_FILE] event): …\`` 并并入 `gapsReason`。
6. **PM 回读**：`pm/ui-bridge.ts:585 readTerminalDetail(taskDir, status)` 读 `output.md` 的 `## Questions` 首行（`output-writer.ts:260-262` 注释指明这条契约）；调用点 `pm/ui-bridge.ts:789`（`renderWatchLines`）。
7. **测试/诊断的直接调用**（不是运行期消费者，但读取该 API）：见 §5 清单。

**失败行为**：
- 有 `[WRITE_FILE]` 但内容乱码 ⇒ 只要有一次 `recorded.length > 0`，`unjudgeable=false`，账本按集合比对判红/绿（乱码路径既不等于声明、也不会因不存在而 warn，除非声明本身在磁盘不存在）。rq2/rq3 即此状态。
- 完全零 `[WRITE_FILE]` 且报告有 `改动清单` ⇒ `unjudgeable=true` ⇒ `## Ledger Unjudgeable`、settle reason 点名、`ok=false`、`exit=2`。
- 完全零 `[WRITE_FILE]` 且无声明 ⇒ 平凡绿（`:109` 测试锁定）。

**没有其他消费者**：`mw doctor`（`mw.py`/`mw_common.py`）与 conductor/launcher 的 Python 侧**不解析**这行；`rg "WRITE_FILE" packages/multi-workers` 只命中 `autopilot/dispatch.py:453` 的卡面文案（`改动历史: … trace.log 的写入事件（[WRITE_FILE] / [WRITE_EDIT]）。`）。其中 `[WRITE_EDIT]` 是全仓唯一出现（**幽灵标记**，无任何代码产出——见“未找到清单”）。

---

## 4. `unjudgeable` 的现状语义与新增“解释器写入”事件的改动点

### 4.1 现状语义

- `unjudgeable` **当前不是事件**，是 `diffLedger` 在零记录时的派生布尔（`change-ledger.ts:875-877`）。
- 语义分两层：
  - `ChangeLedger.unjudgeable: boolean`（`:818` 注释：`the report declares files but the trace recorded ZERO write events`）。
  - `TerminalGaps.unjudgeableFiles: string[]`（`output-writer.ts:56`；`:220-222` 展开为 declared 里非 infra/unresolvable 的集合）。
- 与 `[WRITE_FILE]` 的关系：**只有当 `[WRITE_FILE]` 计数为 0 时才会被判 unjudgeable**；任何一行（哪怕乱码）都会让闸关闭。这是 FW-009 的两向失真在判据层的直接后果。

### 4.2 若要新增“解释器写入（python/node heredoc / stdin）落 unjudgeable 事件”，需要改的位置

| # | 位置 | 改动要点 | 现有测试是否需同步 |
|---|---|---|---|
| 1 | `worker-mode.ts:2356-2359`（采集） | `pendingBashWrites` 需保留 `{target, verbatim, pattern}`（现在只 `.map(c => c.target)`，两个判据都被丢） | 无直接单测；`dispatch-recovery-terminal.test.ts:350` 依赖此路径仍产生普通 `[WRITE_FILE]` |
| 2 | `worker-mode.ts:2383-2385`（记账） | 只对 `verbatim === true` 的目标写 `[WRITE_FILE]`；对 `verbatim === false`/识别出的解释器命令写新事件（不能继续无条件 append） | `change-ledger.test.ts:117`（bash write 使其 judgeable）用的是 trace 文本，不受影响；`dispatch-recovery-terminal.test.ts:350`（`echo x > src/a.ts`，verbatim=true）必须继续绿 |
| 3 | `change-ledger.ts:111`（事件语法单一源） | 新事件标记必须在 `WRITE_FILE_EVENT` 旁定义（如 `UNJUDGEABLE_EVENT`），`formatXxx`+`appendXxx`+`parseXxx` 同源 | 需新增单测 |
| 4 | `change-ledger.ts:785-819 / :827-879`（判据） | `ChangeLedger` 增加该事件的计数（或 `unjudgeable: boolean` 改为事件驱动）；`recorded.length === 0` 的派生闸需与显式事件合并，否则显式事件会因 `recorded>0` 反而永远判不了 | `change-ledger.test.ts:92/109/117` 三例语义需复核（零事件⇒unjudgeable 的现状要保持，显式事件⇒unjudgeable 是新增） |
| 5 | `output-writer.ts:220-222 / :238 / :271-272 / :353` | 把新事件并入 `unjudgeableFiles` 与 `## Ledger Unjudgeable` | `mwgal-t17-ledger-role-aware.test.ts:188`、`mwds-t21…` 等零事件 unjudgeable 用例保持 |
| 6 | `worker-mode.ts:2756-2760` | settle reason 文案需区分“零事件不可判”与“显式不可判事件” | 无直接单测 |
| 7 | 抽取器侧（可选，AC-008 语义） | 现无 `python -`/`node -`（stdin）与 `@'…'@` 判定；`scriptPayloadFlag`（`:1087-1103`）只认 `-c`/`-e`。若把 stdin/here-string 识别为解释器写，可让 rq1 形态直接落 unjudgeable 事件，而不是靠修 `--glob` 伪目标 | `mwds-t03-bash-write-scope.test.ts:429`（VC-035 模式表）与 `:477`（AC-002 inventory）需补新行 |

**关键风险**：`readTerminalGaps` 的 `ok`（`output-writer.ts:238`）把 `unjudgeableFiles` 当红。若 AC-008 要求“python heredoc 写入落 unjudgeable 记录”，需明确这是 warn 通道还是红通道——现状 `## Ledger Unjudgeable` 会参与 `ok=false`/`exit=2`，而 `## Ledger Malformed/Infra/Unresolvable` 不参与。spec §1.6 S5 的措辞是“不静默丢弃、不乱猜”，未指定红绿，design 阶段需定。

---

## 5. 现有测试清单（vitest，逐条断言要点）

> Python/pytest 侧：**未找到**与 `[WRITE_FILE]`/`change-ledger`/壳层写面/声明缺口相关的用例（`rg "WRITE_FILE|parseWriteFileEvents|diffLedger" packages/multi-workers` 只命中 `dispatch.py:453` 卡面文案；`test_update_env.py:327` 的 `unjudgeable` 是 repo-bundle anchor 状态，与账本**同名不同物**）。

1. `packages/coding-agent/test/suite/change-ledger.test.ts`（188 行，直测 `diffLedger`/`formatWriteFileEvent`/`appendWriteFileEvent`）
   - `diffLedger — declared ⊆ recorded`（`:65`）
     - `equal sets are green (extra empty)`（`:66`）：`extra=[]`、`unjudgeable=false`（含重复事件去重）。
     - `a declared file with no write event is red and names the file`（`:83`）：`extra=[WORKER_MODE]`。
     - `a trace with no [WRITE_FILE] line and a declaration is unjudgeable, not green (T-12/F-04)`（`:92`）。
     - `a trace with no [WRITE_FILE] line and no declaration is trivially green`（`:109`）。
     - `a bash write event makes a shell-only run judgeable (T-12/F-04)`（`:117`）。
     - `a report without 改动清单 declares nothing`（`:127`）。
     - `absolute trace paths match repo-relative declarations (and windows separators)`（`:144`，trace 用 `H:\git\…` 反斜杠）。
     - `parses only path-shaped statements from the section body`（`:153`）。
   - `[WRITE_FILE] event`（`:170`）：`records the path only, never content`（`:171`）；`ignores non-event lines and blank path values`（`:177`）。
   - `producer — worker_file`（`:195`）：`appends exactly one event per successful write and none for a rejected one`（`:196`）；`appends one line per call without touching the written file's bytes`（`:211`）。
2. `packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts`
   - `a declared-but-unrecorded file flips the run and lands in ## Ledger Gaps`（`:289`）：`run.status="needs-clarification"`、`run.exit=2`、`output` 含 `## Ledger Gaps`+`src/z.ts`、`readTerminalDetail` 含 `未记录写入：src/z.ts`。
   - `T-12/F-04: a trace with no [WRITE_FILE] event and a declaration is unjudgeable, not green`（`:313`）：detail 含 `未记录写入（不可判）`。
   - `migration: no [WRITE_FILE] event and no declaration is not judged`（`:339`）：status=done，无 `## Ledger Gaps`/`## Ledger Unjudgeable`。
   - `T-12/F-04: a successful bash write records a [WRITE_FILE] event`（`:350`）：`echo x > src/a.ts` ⇒ trace 含 `[WRITE_FILE] path=src/a.ts`。
   - `T-12/F-04: a bash-only coding run reconciles green against its declaration`（`:369`）。
3. `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`（抽取器与写面守卫主矩阵）
   - `extractBashWriteCandidates covers the required write patterns with exact targets (VC-035)`（`:429`）：逐条精确 target。
   - `pure reads and unclassifiable commands extract nothing`（`:442`）。
   - `AC-002 write-form inventory`（`:477`）：wrapper/`>|`/`>&`/C 组 operand/`find -exec`/inline exec/不可见类/历史假阳/xargs 占位符。
   - `AC-001 verbatim contract`（`:874`）：36-case corpus（`:892`）、`$` 引号形态（`:953/:973`）、allow-unknown（`:985`）、第 3 个 `verbatim` 实参签名（`:1011`）。
   - `T-19/C-17 heredoc bodies are not redirect sources`（`:1644`）：body `>` 不成为目标（`:1645`）、quoted/dashed 分隔符与 here-string（`:1656`）。
   - `T-20/H-3/H-4`（`:1685/:1700/:1704/:1719`）：混合 EOL heredoc 与同行 `;`。
   - `T-17 F-2 comparison contexts`（`:1487`）、`T-17 F-1 tar / -i suffix`（`:1535`）、`sed/perl -i$SUFFIX`（`:1577`）。
   - `T-17/B-6 forms coverage metric`（`:1457`）：`[FORMS] total/covered/missing`。
4. `packages/coding-agent/test/suite/mwds-t21-write-intent-soundness.test.ts`：五判据（`:102-190`）、T-18/T-19 fixtures（`:216-267`）、真实语料前后对照（`:323-355`）；断言 `extra`/`collectMalformedCandidates`。
5. `packages/coding-agent/test/suite/mwds-t25-version-and-dotless.test.ts`：无扩展名 `scripts/deploy` 的存在性仲裁（`:152-246`），含 `host/pid`/`notice/refusal` 仍不是声明（`:215`）。
6. `packages/coding-agent/test/suite/mwds-t26-closeout-verify.test.ts`：真实文件 `launcher.py` 声明无事件 ⇒ red（`:61-68`）；无扩展名仲裁（`:80-105`）。
7. `packages/coding-agent/test/suite/mwds-t23-cutover-recheck.test.ts`：`diffLedger: declared launcher.py without a [WRITE_FILE] event lands in extra`（`:224`）。
8. `packages/coding-agent/test/suite/mwgal-t17-ledger-role-aware.test.ts`：writeless 角色读取引用（`:113-151`）、P-03 越界仍红（`:153-205`），`writeless role: a zero-event trace with a 改动清单 declaration stays unjudgeable`（`:188`）、malformed（`:207-273`）、`readTerminalGaps folds the outside-taskDir deliverable into a clean verdict`（`:371`）。
9. `packages/coding-agent/test/suite/mwgal-t17b-ledger-infra-writes.test.ts`：infra 文件级豁免（`:88-228`）、`_workers.parallel` 零 findings（`:230`）、warn 通道`readTerminalGaps + writeOutput`（`:276`）、`an infra-only declaration on a zero-event trace is green, not unjudgeable`（`:315`）、`a mixed zero-event declaration names only the non-infra file as unjudgeable`（`:323`）、非 infra 越界仍红（`:365-435`）、live corpus（`:472`）。
10. `packages/coding-agent/test/suite/mwgal-t17c-ledger-unresolvable.test.ts`：`update_index.py`/`os.replace` 零 findings + warn（`:100-149`）、`## Ledger Unresolvable` 可见（`:150`）、存在性判别（`:206-322`）、`infra ownership wins`（`:343`）、T-17/T-17b 不回归（`:380`）、live corpus（`:419`）。
11. `packages/coding-agent/test/suite/mwgal-t21-qg-fixes.test.ts`：R-1 文件级豁免（`:127-291`，含 gate 文件 RED `:128`、`## Ledger Gaps` 端到端 `:146`）。
12. `packages/coding-agent/test/extensions/agent-team-loop.test.ts`：`output-writer writeOutput`（`:443-557`）覆盖 exit 0/1/2/130 与 `## Questions`；`terminal detail sources`（`:2695-2832`）覆盖 `readTerminalDetail` 的 Questions 回读。

---

## 6. 形状校验的现实约束（“校验过严”风险对照）

### 6.1 磁盘文件名层面：0 例

对仓库树（排除 `node_modules`、`.git`、`dist`、`.mw`、`.venv`、`__pycache__`）walk **7921** 个条目，逐文件名检查 `space`/`+`/CJK/`@`/`~`/`()`/`#`/`&`/`%`/`[]`/`$`/`;`/`,`/`=`/`!`/`{}`：**全部计数 = 0**（命令：Python `os.walk` 脚本，见 §证据）。即“含空格/中文目录名”的场景**在本仓库不来自真实文件名**。

### 6.2 `.agenticdoc` 内容层面：大量真实出现（会被 `PATH_SHAPE_RE`/`isPathCandidate` 拒绝）

`PATH_SHAPE_RE = /^(?:[A-Za-z]:)?\/?(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]+\/?$/`（`change-ledger.ts:399` 附近），`isPathCandidate` 显式 `if (token.includes("\\")) return false;`（`:407`）。

| 形态 | 实测行数（`.agenticdoc`，`rg`） | 代表实例（file:line） |
|---|---|---|
| 反斜杠盘符绝对路径 | `H:\git\Multi-Workers` = **382**；`C:\Users\` = **1720** | `.agenticdoc/mw-claude-mirror-parity/evidence/research/spec-mirror-semantics-20261012.md:4` 的 `H:\git\Multi-Workers\.agents\skills\age…` |
| 8.3 短名（`~`） | `WENBOZ~1` = **87** | `.agenticdoc/mw-console-title-clobber/evidence/ts-cli-tests-with-change-20261011.txt:5` = `C:\Users\WENBOZ~1\AppData\Local\Temp\pi-package-commands-…` |
| 含空格路径 | `Program Files` = **12**；`AppData\Local\Temp` = **356** | `.agenticdoc/goal-autopilot/evidence/baseline/baseline-manual-suites.md:13` = `D:\Program Files\Git\bin\bash.exe`；`.agenticdoc/mw-workspace-incident-probe/evidence/in2-file-vanish-incident-20261009.md:153` |
| `~` 家目录 | `~/.pi` = **190**；`~/.agents` = **51** | `.agenticdoc/_pitfalls.md:16` = `~/.pi/agent/auth.json` |
| `@` 片段 | `@cf/` = **5**；`workers-ai/@cf` = **4** | `.agenticdoc/ai-baseline-repair/design.md:36` = `workers-ai/@cf/moonshotai/kimi-k2.6` |
| `+` | 内容里 `+` 常见但**没有真实存在的路径**（磁盘 0 例）；`rg` 的 `plus-in-path-look` 1456 行绝大多数是算术/区间（如 `AC-001~036`、`+32`） | `.agenticdoc/autopilot-monitor/workers/t02-verification/progress.md:39` = `packages/coding-agent/CHANGELOG.md（+1` |
| 中文片段 | `CJK-path-look` 仅 **10** 行，且均非真实路径（叙述文本） | `.agenticdoc/mw-guard-form-hardening/evidence/research/spec-taskmd-corpus-20261011.md:3` |

### 6.3 dist 复跑：形状闸的实际判定（决定性证据）

用 dist 的 `diffLedger`/`collectMalformedCandidates` 对一份 `## 改动清单` 喂入代表性 token（`role: "coding"`）：

| 声明 token | 结果 |
|---|---|
| `H:\git\Multi-Workers\.agents\skills\age\x.md` | `malformed`（`token.includes("\\")`） |
| `C:\Users\WENBOZ~1\AppData\Local\Temp\note.md` | `malformed`（反斜杠 + `~`） |
| `D:\Program Files\Git\bin\bash.exe` | **拆成两个 malformed**：`D:\Program` + `Files\Git\bin\bash.exe`（`TOKEN_SPLIT_RE` 按空白切） |
| `~/.pi/agent/auth.json` | `malformed`（`~` 不在字符集） |
| `workers-ai/@cf/moonshotai/kimi.md` | `malformed`（`@`） |
| `中文/设计.md` | `malformed`（CJK） |
| `packages/coding-agent/src/a+b.ts` | `malformed`（`+`） |
| `H:/git/Multi-Workers/.agents/skills/age/x2.md` | **declared**（正斜杠盘符形式通过 `PATH_SHAPE_RE`）→ 因文件不存在而 `unresolvable`（warn） |

结论：**只有正斜杠形态能通过**；真实 Windows 反斜杠路径与含空格路径在“声明/gate 判定”里一律不可见（malformed warn-only）。若 S5 用同一套 whitelist 校验壳层写目标，rq1 那类 `$path = "…"` 的写目标会被系统性丢弃；若用更严的“非 `:`/数字开头、无空格/`+`”还会把坐标片段保留判定留给别的机制（FW-009 修法①的原文即如此）。**风险 R4 的对照数据在本仓库是：磁盘 0 例，内容大量**——即不能以“仓库没有这类路径”为该 whitelist 辩护。

---

## 证据（命令与原始输出摘要）

- 抽取器复跑（只读、不写仓库）：
  - `node .agenticdoc/.../woc-rq3-ledger/runner.mjs rq2-cmd.json` → `{"target":"`:1175","pattern":"redirect","verbatim":false}` + `{"target":"`:1184",…}`。
  - `node …/runner.mjs rq3-cmd.json` → `target=", .agenticdoc/_aut + opilot)\np = pathlib.Path(…)…" verbatim=false`（首行即 trace 记录值）。
  - `node …/runner.mjs rq1-allbash.json` → 122 条命令共产 8 个候选（全部 `--glob`/反引号）。
  - `node …/minimize.mjs`（行级 delta-debug）→ rq2 最小 55 字符；`minimize2/3.mjs` → rq3 最小 319/336 字符。
- trace 直读（Python，`encoding='utf-8', errors='replace'`）：`[WRITE_SCOPE_SUMMARY]` rq1 `allow=0 deny=3 allow-unknown=0`、rq2 `allow-unknown=2`、rq3 `allow=0 deny=1 allow-unknown=2`；`[WRITE_FILE]` 计数 rq1=0、rq2=2、rq3=2、rq-d1=8、rq-d2=4。
- 会话 JSONL：rq1 `2026-10-13T17-10-27-544Z_…`（122 bash call，24 个 `[System.IO.File]::WriteAllText/AppendAllText`）；rq2 `…17-10-27-550Z_…`；rq3 `…17-10-42-324Z_…`。
- 形状闸：`node …/shape.mjs` 输出 `declared=["H:/git/…/x2.md"] malformed=[反斜杠×2, "D:\Program","Files\Git\bin\bash.exe","~/.pi/…","workers-ai/@cf/…","中文/设计.md","packages/coding-agent/src/a+b.ts"]`。
- 统计：Python `os.walk`（7921 条目）16 类字符全 0；`rg` 行数见 §6.2。
- 会话逐条命令是**缓存证据文件** `.agenticdoc/mw-worker-output-contract/workers/woc-rq3-ledger/{rq1-allbash,rq1-cmd,rq2-cmd,rq3-cmd,cand,cand2}.json` + `{runner,minimize,minimize2,minimize3,tok,shape}.mjs`（均在本任务目录，非仓库源码）。

---

## 残留与未验证

- **dist vs src 一致性**：抽取器/账本用 `packages/coding-agent/dist/**` 复跑（`node` 直接 import）。已人工比对 `dist/extensions/agent-team-loop/worker/worker-mode.js:1337-1340` 与 src `:1554-1558` 同构、`dist/.../shared/change-ledger.js` 与 src 同构；但**未跑 vitest**，不能声明“dist 与当前 src 逐字节等价”。
- **未跑任何测试**（只读边界 + P-032 禁用全量）。§5 的断言要点来自读测试源码，非执行结果。
- **未做端到端复现**（未真正启动 worker）；rq2/rq3 的复现是“抽取器函数级”，与 trace 的账本行做了逐值对照。
- `verbatim` 差异：rq3 最小化输入在 4 行时为 `verbatim=true`，加回 `$code | python -` 后为 `false`；真实命令的 `verbatim=false` 已由 dist 复跑原命令确认，未进一步定位是哪个 live 字符（不止一处）。
- `[WRITE_EDIT]` 幽灵标记的来源（dispatch.py:453 文案）未追溯引入 commit。

## 未找到清单

- 未找到 Python/`mw doctor` 对 `[WRITE_FILE]`/`unjudgeable`（账本语义）的解析：`rg -n "WRITE_FILE|parseWriteFileEvents|diffLedger|unjudgeable" --glob '!**/dist/**' packages/multi-workers` → 仅 `autopilot/dispatch.py:453`（卡面文案）+ `test_update_env.py:327`（同名不同物）。
- 未找到 `[WRITE_EDIT]` 的任何产出代码：`rg -n "WRITE_EDIT" --glob '!**/dist/**' --glob '!node_modules' .` → 仅 `packages/multi-workers/autopilot/dispatch.py:453`。
- 未找到“PR 侧 declaration gap”这一命名的独立消费者：`rg -n -i "declaration gap|声明缺口" .agenticdoc packages --glob '!**/dist/**'` 只命中 spec §1.3/§1.5（P4）的描述文本，无代码符号（该表述即 `diffLedger` 的 `declared ⊆ recorded`，无第二实现）。
- 未找到磁盘文件名含空格/`+`/中文/`@`/`~` 的实例（walk 7921 条目全 0）。

## 未覆盖面声明

- 未覆盖 `packages/coding-agent/src/**` 之外的其他扩展（如 `pm/ui-bridge.ts` 只覆盖到 `readTerminalDetail` 调用点，未穷举 `renderWatchLines` 的所有分支）。
- 未覆盖 `dist` 与源码的行为差异（见“残留”）；未覆盖 `node_modules` 内的实现。
- 未覆盖 autopilot/conductor 的 L3 verdict provenance 路径（它只读 trace 的 `[START]`/mtime，不读 `[WRITE_FILE]`）。
- 未覆盖 `.agenticdoc/mw-write-face-guard/workers/*` 之外其他 key 的账本实例。
- 未覆盖“新增 unjudgeable 事件”的具体实现（那是 design/实现任务，本报告只列改动点与需同步测试）。

## 结论

1. 伪行成因是 shell 词法被 PowerShell here-string 打乱 + 非 verbatim 目标仍无条件记账（`worker-mode.ts:2383-2385`）。
2. 漏报成因是 `.NET File API`/`python -`（stdin）不可分类，且 rq1 的写命令还被伪 `--glob` 目标误 block（`allow=0 deny=3`）。
3. `[WRITE_FILE]` 的唯一判据链是 `parseWriteFileEvents → diffLedger → readTerminalGaps → output.md/settle/PM 回读`；Python/doctor 不消费。
4. `unjudgeable` 当前是“零事件”的派生态，任何乱码事件都会绕开它。

## 证据

见上文“证据”节与 §1–§6 的 `文件:行号` 引用；决定性复跑为 dist 抽取器对 rq2/rq3 真实命令的逐值还原（`` `:1175 ``、`` `:1184 ``、`, .agenticdoc/_aut + opilot)`）。

## 残留与未验证

见上文“残留与未验证”节（未跑测试、未端到端、dist/src 非逐字节校验）。

## 上下文来源

- `tasks/T-RQ3-ledger.md`（dispatch card `mw-dispatch-card: v1`）、`.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P4、§1.6 S5、§3 AC-008、§1.7 第 4 条）、`.agenticdoc/goal.md`。
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/{worker/worker-mode.ts, worker/output-writer.ts, worker/worker-file-tool.ts, shared/change-ledger.ts, pm/ui-bridge.ts}`；构建产物 `packages/coding-agent/dist/extensions/agent-team-loop/**`（只读执行）。
- 语料：`.agenticdoc/mw-write-face-guard/workers/{wfg-rq1-write-face-sources,wfg-rq2-enforcement,wfg-rq3-safety,wfg-rq-d1-glob-intersection,wfg-rq-d2-runtime-guard}/trace.log`；`.agenticdoc/_framework-reflect.md` FW-009。
- 会话：`~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-13T17-10-*.jsonl`（pi 原始 toolCall 命令）。
- 测试：`packages/coding-agent/test/suite/{change-ledger,dispatch-recovery-terminal,mwds-t03-bash-write-scope,mwds-t21-write-intent-soundness,mwds-t23-cutover-recheck,mwds-t25-version-and-dotless,mwds-t26-closeout-verify,mwgal-t17-ledger-role-aware,mwgal-t17b-ledger-infra-writes,mwgal-t17c-ledger-unresolvable,mwgal-t21-qg-fixes}.test.ts`、`packages/coding-agent/test/extensions/agent-team-loop.test.ts`。

[VERIFY] extractor_entry=1(worker-mode.ts:1554) pattern_labels=41 add_callsites=31; redirect_family=3(redirect/redirect-clobber/redirect-fd-target); rq2_repro=55chars→["`:1175","`:1184"] rq2_single_min=13chars; rq3_repro=319chars(verbatim=true)/336chars(verbatim=false)→", .agenticdoc/_aut + opilot)"; rq1_bash_calls=122 io_file_write_calls=24 write_scope_deny=3 write_file_rows=0 extractor_candidates=8(all --glob/backtick); WRITE_FILE_rows={rq1:0,rq2:2,rq3:2,rq-d1:8,rq-d2:4}; runtime_consumers=6(parseWriteFileEvents diffLedger readTerminalGaps writeOutput settle readTerminalDetail) producers=3; python_consumers=0; on_disk_bad_shape_names=0(walk=7921); content_hits={H:\git\:382, C:\Users\:1720, WENBOZ~1:87, ProgramFiles:12, AppData\Local\Temp:356, ~/.pi:190, ~/.agents:51, @cf/:5}; dist_shape_probe declared=1 malformed=8
