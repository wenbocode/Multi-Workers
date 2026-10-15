# Design: 变更账本抽取器加固（T-DR3 / AC-008 / AC-017）

- Key: `mw-worker-output-contract`；worker: `woc-dr3-ledger-hardening`；card: `.agenticdoc/mw-worker-output-contract/tasks/T-DR3-ledger-hardening.md`
- 目标锚点：`.agenticdoc/goal.md`（文件驱动的去中心化协调）。
- 只读边界：**未修改仓库任何文件**；未跑 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`。写面：本任务目录 + `evidence/`。
- 方法：`read`/`grep` 全量读源码；Node v24.19.0 `require()` `packages/coding-agent/dist/extensions/agent-team-loop/**`（只读执行）复跑抽取器 + 守卫 + `diffLedger`；PowerShell 5.1 直接观察守卫拦截（见 §0.5 实例）；真实命令取自 pi 会话 JSONL（`~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-13T17-10-*.jsonl`）而非 `[TOOL]` 行（后者被 `truncLine(…,80)` 截断）。探针脚本：本任务目录 `report-probe-rq3.md` / `report-probe-rq3b.md` / `report-probe-rq3c.md`（`Get-Content -Raw <f> | node -`，不写仓库）。
- 术语：**有效事件** = 抽取器分类为「写动词 + 可静态解析目标」并落盘的 `[WRITE_FILE]`；**非 verbatim 目标** = 目标词含 live 展开（`$` 反引号 `*` `?` `[` `{` 或词首 `~`），即 `BashWriteCandidate.verbatim === false`。

## 0. 结论与标签处置表

### 0.1 六问结论（各一句话）

1. **正信号** = `(写动词/写 API 节点) × (该节点的目标操作数) × (目标静态可解析)` 三者同时成立；目标只能从语法树的「写位」取值（数据流），永远不从「文本里像路径的子串」取值。
2. **标签表**：现有 **41 个 label 全部保留**（一个都不删——每个都是 AC-005b 守卫的 miss 面），**新增 1 个 label `net-file-api`**（`.NET File API`，弥补 spec 点名的 `WriteAllText/AppendAllText` 缺口）；`Set-Content/Out-File/New-Item`-族 12 个 label 已在表内（实测覆盖，见 §0.5 P5）。此外新增 1 个**账本侧**分流谓词（不进 label 表）：目标为 `.`/`..`/`/` 时不落账本事件（守卫仍消费）。
3. **非 verbatim 目标**：既不静默丢弃、也不冒充写入 ⇒ 落**新事件** `[WRITE_UNRESOLVED]`（语法同 `[WRITE_FILE]` 家族，`change-ledger.ts:111/:123` 旁新增同源 `format/append/parse` 三件套）；`[WRITE_FILE]` 只收 verbatim 目标。消费者侧新增 `ChangeLedger.unresolved: string[]`（**新字段**，不是新事件类型之外的第二种形状）。
4. **`unjudgeable` 语义**：由「`recorded.length === 0`」改为「**有效事件**（verbatim `[WRITE_FILE]`）为 0 且存在 judgeable 声明」；6 个消费者逐个行为变化见 §4.3。实测该闸现在可被一条乱码事件关闭（§4.1）。
5. **误拦面**：抽取器与守卫共用**同一个候选集**（`worker-mode.ts:2222` 守卫、`:2356-2359` 账本），修法是「候选集不动、消费谓词分流」：守卫对 `verbatim=false` 一律 `allow-unknown`（现状已如此），账本只消费 `verbatim=true && 目标非 `.``；派生写入（`.NET`/解释器）因此**不被拦**，越界 verbatim 写入**仍被拦**（判据 C1–C5，§5.3）。
6. **测试形态**：AC-017 四段判据落在 **2 个既有文件**（`mwds-t03-bash-write-scope.test.ts` 抽 (a)(b)(c) 单位层、`change-ledger.test.ts` + `dispatch-recovery-terminal.test.ts` 落 (d) 与端到端）+ 1 个新夹具文件；12 个既有 vitest 文件的影响面与不回归方法见 §6.3/§6.4。

### 0.2 41 个 label 处置表（完整枚举，实测 `batteryPatterns=41`，见 §0.5 P5）

| # | pattern | 定义位置 | 处置 | 说明 |
|---|---|---|---|---|
| 1 | `redirect` | `worker-mode.ts:1222` | 保留·记账 | 数据区预剥离后不再从正文取值 |
| 2 | `redirect-clobber` | `:1227` | 保留·记账 | `>\|` 形态 |
| 3 | `redirect-fd-target` | `:1229` | 保留·记账 | `>& <非 fd>` 形态 |
| 4 | `inline-script` | `:1274` | 保留·记账 | 仅 `-c/-e` 载荷；stdin（`\|` python）列缺口 G-1 |
| 5 | `perl -i` | `:1327`/`:1328` | 保留·记账 | |
| 6 | `tee` | `:1350` | 保留·记账 | |
| 7 | `cp` | `:1357`/`:1362` | 保留·记账 | `-t` 时取目录 |
| 8 | `mv` | `:1357`/`:1362` | 保留·记账 | 同上 |
| 9 | `rm` | `:1369` | 保留·记账 | |
| 10 | `mkdir` | `:1369` | 保留·记账 | 目录本身是真实变更 |
| 11 | `touch` | `:1369` | 保留·记账 | |
| 12 | `truncate` | `:1369` | 保留·记账 | |
| 13 | `install -t` | `:1376` | 保留·记账 | |
| 14 | `install` | `:1377`/`:1379` | 保留·记账 | |
| 15 | `ln -t` | `:1386` | 保留·记账 | |
| 16 | `ln` | `:1390` | 保留·记账 | |
| 17 | `rsync` | `:1395` | 保留·记账 | |
| 18 | `dd of=` | `:1401` | 保留·记账 | |
| 19 | `tar -C` | `:1444` | 保留·记账 | 解包目的地 |
| 20 | `tar -x` | `:1445` | 保留·**守卫专用** | 目标恒为 `.`：守卫要拦「解包到仓库根」，账本不记 `path=.` |
| 21 | `tar -c` | `:1446` | 保留·记账 | |
| 22 | `sed -i` | `:1471`/`:1472` | 保留·记账 | 含 `-i$SUFFIX` 第二目标 |
| 23 | `find -delete` | `:1498` | 保留·记账 | |
| 24 | `git checkout` | `:1505`/`:1506` | 保留·记账 | |
| 25 | `git apply` | 同上 | 保留·记账 | |
| 26 | `git clean` | 同上 | 保留·**守卫专用** | 无 path 时目标 `.`，同 #20 |
| 27 | `git restore` | 同上 | 保留·记账 | |
| 28 | `curl -o` | `:1514`/`:1516` | 保留·记账 | |
| 29 | `wget -O` | `:1526`/`:1528` | 保留·记账 | |
| 30 | `set-content` | `:1545` | 保留·记账 | 已在表内，非新增 |
| 31 | `add-content` | `:1545` | 保留·记账 | 同上 |
| 32 | `clear-content` | `:1545` | 保留·记账 | 同上 |
| 33 | `out-file` | `:1545` | 保留·记账 | 同上 |
| 34 | `new-item` | `:1545` | 保留·记账 | 同上 |
| 35 | `remove-item` | `:1545` | 保留·记账 | 同上 |
| 36 | `set-content -Path` | `:1539` | 保留·记账 | `-path/-literalpath/-filepath/-destination` |
| 37 | `add-content -Path` | `:1539` | 保留·记账 | |
| 38 | `clear-content -Path` | `:1539` | 保留·记账 | |
| 39 | `out-file -Path` | `:1539` | 保留·记账 | |
| 40 | `new-item -Path` | `:1539` | 保留·记账 | |
| 41 | `remove-item -Path` | `:1539` | 保留·记账 | |
| 42 | **`net-file-api`（新增）** | 新分支，插在 `default:`（`:1531`）之前 | 新增·记账 | `[System.IO.File]::WriteAllText/AppendAllText/WriteAllLines/WriteAllBytes/WriteAllTextAsync/AppendAllTextAsync/Delete/Move/Replace/Copy` |

### 0.3 处置面（新增 / 修改 / 删除）

新增：
- `net-file-api` label + 成员表 `NET_FILE_API_TARGETS`（成员名 → 目标实参下标）。
- `change-ledger.ts`：`UNRESOLVED_WRITE_EVENT = "[WRITE_UNRESOLVED]"`、`format/append/parseUnresolvedWriteEvents`、`ChangeLedger.unresolved: string[]`。
- `worker-mode.ts`：`stripDataRegions(command)`（PowerShell here-string `@'…'@` / `@"…"@` 数据区，行级状态机，与 heredoc 同一趟扫描）；`classifyLedgerTargets(command)`（纯函数：`{ recorded, unresolved }`）；小型字面量赋值环境 `env`（`$x = "lit"` / `$x = 'lit'` / `VAR=lit`）。
- `output-writer.ts`：`TerminalGaps.unresolvedFiles: string[]`（warn-only，`## Ledger Unresolved` + `[FLOW] ledger-unresolved`）。

修改：
- `extractBashWriteCandidates`（`:1554`）：入口先 `stripDataRegions`，再 `tokenizeShellCommand`；`.NET` 分支用 `env` 解析目标。
- `tool_execution_end`（`:2383-2385`）：由「无条件 append」改为「`classifyLedgerTargets` 分流」。
- `diffLedger`（`:827`）：`recorded` 只取 verbatim 事件；`unjudgeable` 由有效事件数为零派生。
- `readTerminalGaps`（`output-writer.ts:208-238`）：`unjudgeableFiles` 派生条件显式引用「有效事件 = 0」；新增 warn 通道。
- `finishSuccess`（`worker-mode.ts:2756-2760`）：reason 文案区分「零有效事件」与「存在 N 条不可判定写入」。

删除：**无**。明确不改 `BashWriteCandidate` 三字段形状（`{target, pattern, verbatim}`）——`mwds-t03` 有约 20 处 `toEqual([{target,pattern,verbatim}])` 深比较，加字段会破坏它们；分流谓词放在抽取器**之外**。

### 0.4 与 spec 的一处实测偏差（须由 design/实现阶段回写 AC 措辞）

AC-017(c) 写「`[WRITE_SCOPE_SUMMARY]` 由 `allow=0 deny=3` 变为 `allow=3 deny=0`」。逐条复算 rq1 的 122 条 bash 后：被守卫拦下的 3 条**工具调用**里只有 **2 条**是真写（`[System.IO.File]::WriteAllText`，`$path=.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md`），第 3 条是 `cd H:\git\Multi-Workers Write-Output a <term> --glob x`（54 字符，无任何写 API，实测 `writeApi=false`）。按本设计修完后该命令产 **0** 候选 ⇒ 不产生任何计数行，故 summary 应为 **`allow=2 deny=0 allow-unknown=0`**，不是 `allow=3`。建议 AC-017(c) 改为「`deny=0`（从 3 降到 0），且 2 条真写命令各产恰好 1 条 `[WRITE_FILE]`」，数字由夹具定死（§6.2）。

### 0.5 本次实测的关键数字（命令见本任务目录探针；`node` 读 dist）

```
P1 rq1 {"bash":122,"ioFileWriteCalls":24,"candidates":8,"targetSet":["--glob","`","--arg`（`"]}
P1 rq2 {"bash":69,"ioFileWriteCalls":4,"candidates":2,"targetSet":["`:1175","`:1184"]}
P1 rq3 {"bash":95,"ioFileWriteCalls":0,"candidates":6}   # 含 6,277 / 2,239 字符级乱码 target
P2 liveCounts {"allowDetermined":0,"deny":3,"allowUnknown":0}   # 与 trace.log:384 完全一致
P3 min13 :: [{"target":"`:1175","pattern":"redirect","verbatim":false}]
P3 rq2_55 :: [{"target":"`:1175",...},{"target":"`:1184",...}]
P3 net_write_dq/net_write_sq/net_append/net_var/ps_heredoc_glob/python_dash_heredoc :: []
P3 python_c_inline :: [{"target":"evidence/x.md","pattern":"inline-script","verbatim":true}]
P5 batteryPatterns=41 batteryMissing=[]
```
本会话的自然实例（`…/woc-dr3-ledger-hardening/trace.log:74-75`）：`[WRITE_SCOPE] … blocked=true rule=scope pattern=redirect target=a.txt)))` + 对应 `[TOOL_ERR] write-scope: blocked bash write to a.txt)))` —— 抽取器把 `node -e "…require(""…"")…"` 的反引号/引号错位解析成 `a.txt)))`，**拦下了一条只读探针命令**。

## 1. 正信号定义

### 1.1 判据（三条件同时成立才配写 `[WRITE_FILE]`）

- **V（写动词节点）**：命令位置（`extractCommand` 的 `commandName`，`:1291-1553`）或重定向算符位（`:1220-1230`）或 `.NET`/解释器写 API 位（`:1272-1290` + 新增分支）被识别为写；
- **T（目标位）**：目标只从该节点的**目标操作数位**取（`add()` 的 `source` 实参：redirect 的 `next`、`cp/mv` 的 `positionals` 末位、PS `-Path` 的后一位、`.NET` 成员表的实参下标……），不从「同一命令文本里任何像路径的子串」取；
- **R（可解析）**：该词 `verbatim === true`（无 live 展开、无 opaque 占位符），且在 `env` 里解析为字面量。

满足 V∧T∧R ∧ 目标 ∉ {`.` , `..`, `/`} ⇒ `[WRITE_FILE] path=<repo-relative>`。
满足 V∧T∧¬R ⇒ `[WRITE_UNRESOLVED] pattern=<label> target=<单行化>`。
V 不成立（未识别的命令、纯读）⇒ 无候选、无记录、无守卫审计行（现状的 fail-open 层，保持不变）。

### 1.2 判定伪码

```
resolveTargets(command) -> { recorded: string[], unresolved: (label,target)[] }
  src   = stripDataRegions(command)          # ① 数据区先剥离（here-string / heredoc）
  env   = literalBindings(src)               # ② 仅 $x="lit" / $x='lit' / VAR=lit，单命令内
  toks  = tokenizeShellCommand(src)          # ③ 逐字词法（现有实现）
  out   = extractFromTokens(toks, 0, ...)    # ④ 只产 {target, pattern, verbatim}
  for c in out:
      if c.target in NON_FILE_TARGETS: continue                  # "." ".." "/"
      v = c.verbatim ? literalOf(c.target, env) : undefined      # ⑤ 值环境解析
      if v is a literal string: recorded += normalize(v)
      else:                     unresolved += (c.pattern, oneLine(c.target))
  return { recorded, unresolved }
```

### 1.3 与「正文片段」的区别如何在实现上由数据流（而非再补正则）保证

三层，全部是**结构**而不是对 target 形状的再匹配：

1. **数据区在词法之前被删除**（新增 `stripDataRegions`，行级状态机；PowerShell 规则：一行以 `@'`/`@"` 结尾开启数据区，直到出现以 `'@`/`"@` 开头的行；POSIX heredoc 由现有 `dropHeredocBodies`（`:2927-2976`）在同状态机内处理）。数据区不存在 token，就不存在算符节点，`->` 里的 `>` 不可能成为 `redirect`。
2. **目标只能来自 `add()` 的调用位**：`extractFromTokens` 在遇到 `>`/`>>` 时只把 `list[i+1]` 交给 `add`（`:1216-1231`）；`extractCommand` 的每个 `add` 都绑定一个已识别的 verb/flag。文本里出现「像路径」的子串但没有写节点时，没有任何 `add` 调用点可以到达它——这是**调用图约束**，不是正则。
3. **`verbatim` + `env` 是唯一的值通道**：`verbatim=false` 的词永远进不了 `[WRITE_FILE]`（新分流），所以「语法错位后残留的片段」（反引号/`+`/`,`）即使侥幸成了某写节点的目标，也只能降级成 `[WRITE_UNRESOLVED]`，不会冒充写入。
   补一句边界（对齐风险 R9）：形状校验（`PATH_SHAPE_RE` 类）在本设计里**只用于报告声明侧**，不用于抽取器目标侧——否则会把正文里合法的 `H:\…`/`Program Files` 路径判死，正是 R9 的坑。

## 2. 标签表处置（含 `.NET File API` 纳入）

- 完整 41 行见 §0.2；无删除、无合并（合并会丢失 `[WRITE_SCOPE]` 审计行的 `pattern=` 定位能力，T-03/AC-007 依赖它）。
- **`.NET File API` 纳入方式**（新增 `net-file-api`）：`.NET` 静态方法名是**写 API 位**，实参下标即目标位，`Set-Content`/`Out-File`/`New-Item` 族已在表内（12 label）。新分支伪码：
  ```
  NET_FILE_API_TARGETS = { WriteAllText:0, WriteAllLines:0, WriteAllBytes:0, AppendAllText:0,
                           AppendAllLines:0, Create:0, Delete:0, Move:0, Replace:0, Copy:1 }
  case "<command is [System.IO.File]::X or [System.IO.Directory]::Y>":
      if X in NET_FILE_API_TARGETS:
          arg = operands[NET_FILE_API_TARGETS[X]]
          add(resolveLiteralOrRaw(arg), "net-file-api", arg.verbatim && resolvable(arg, env))
  ```
  命令位置的识别：`skipWrapperPrefix` 之后命令词形如 `[System.IO.File]::WriteAllText`（含 `::`）。目标为字面量 ⇒ 1 条有效事件；目标为 `$path` 且 `env` 有字面量绑定 ⇒ 解析后仍算有效（rq1 形态）；目标为 `$path` 无绑定 ⇒ 1 条 `[WRITE_UNRESOLVED]`。
- 实测基线：四段 `.NET` 探针现在**全部 0 候选**（§0.5 P3），这是 spec 点名的 24/122 漏报第一因；`Set-Content -Path a.txt` 现在就能取到 `a.txt|set-content -Path|true`（§0.5 P3），故「纳入」只针对 `[System.IO.*]::` 静态方法。

## 3. 非 verbatim 目标的策略

**选择：降级为显式 `unjudgeable` 事件（选项 c），不忽略（选项 a）、不按写入记账（现状选项 b）。**

理由（实测支撑）：现状把非 verbatim 目标**照样**写 `[WRITE_FILE]`（`worker-mode.ts:2383-2385` 无条件 append），于是 rq2/rq3 的乱码 target 成了账本事件；`parseWriteFileEvents`（`change-ledger.ts:148`）只做 `normalizePath`，乱码即「有效路径」。忽略则回到 rq1 的静默 0 行。

`change-ledger.ts:111/:123` 侧兼容设计（同源三件套，形状镜像现有实现）：

```ts
// 新增（紧邻 :111 的 WRITE_FILE_EVENT）
export const UNRESOLVED_WRITE_EVENT = "[WRITE_UNRESOLVED]";
export function formatUnresolvedWriteEvent(pattern: string, target: string): string {
  return `${UNRESOLVED_WRITE_EVENT} pattern=${pattern} target=${oneLine(target)}`;
}
export function appendUnresolvedWriteEvent(tracePath: string, pattern: string, target: string): void { /* 同 :123 的 best-effort append */ }
const UNRESOLVED_WRITE_LINE_RE = /^\[WRITE_UNRESOLVED\][ \t]+pattern=(\S+)[ \t]+target=(.*)$/;
export function parseUnresolvedWriteEvents(traceText: string): { pattern: string; target: string }[] { /* 逐行锚定，永不抛 */ }
/** 单行化：把 CR/LF 与其它控制字符折成 `\n` 文本，杜绝 rq3 的换行注入
 *  （trace.log:308 的记录值只是首行、:309-314 是污染续行）。 */
function oneLine(v: string): string { return v.replace(/[\r\n\u0000-\u001f]+/g, "\\n"); }
```

- `WRITE_FILE_EVENT` 语法**不变**，`formatWriteFileEvent`/`appendWriteFileEvent`/`parseWriteFileEvents` 的签名与行为不变 ⇒ 现有 trace 文本夹具（12 个文件里手写 `[WRITE_FILE] path=…` 的用例）零改动。
- `ChangeLedger` 增 `unresolved: string[]`（存放单行化后的 `pattern:target`，供 warn 通道与测试断言）；不新增「第二种 `[WRITE_FILE]` 形状」，旧的消费者读到新行时按「非事件行」忽略（`WRITE_FILE_LINE_RE` 不匹配），不会误算。

## 4. `unjudgeable` 语义改造与 6 个消费者

### 4.1 现状缺陷（实测，`report-probe-rq3c.md`）

| report 声明 | trace | 现状 `unjudgeable` | 现状 `extra` | 语义 |
|---|---|---|---|---|
| 存在文件 `packages/coding-agent/package.json` | 空 | **true** | [] | 正确：不可判 |
| 同上 | `[WRITE_FILE] path=\`:1175`（乱码） | **false** | `[package.json]` | **错**：乱码事件关闭闸门，且把诚实声明判红 |
| 幻影声明 `update_index.py` | 乱码事件 | **false** | [] | **最危险**：乱码事件把「不可判」变成**全绿** |
| 同上 | 空 | false | [] | 现状即绿（unresolvable 豁免），不变 |

⇒ 闸门必须以「有效事件数为零」为输入，而不是 `recorded.length`。

### 4.2 新派生规则

```
valid     = parseWriteFileEvents(trace)                    // 只含 verbatim 落盘
unres     = parseUnresolvedWriteEvents(trace)
judgeable = declared \ (infra ∪ unresolvable)
unjudgeable = valid.length === 0 && judgeable.length > 0     // 语义：这一次跑，账本没有能力判
warnUnresolved = unres.length > 0                            // 单独 warn，不参与 ok
```
`unres` 不单独置 `unjudgeable`：若已有有效事件判定了声明，则声明仍可判；此时 `unres` 是「另有 N 条看不清的写入」的 warn。

### 4.3 逐消费者行为变化（6 处）

| # | 消费者 | 现状 | 改后 | 变化性质 |
|---|---|---|---|---|
| 1 | `parseWriteFileEvents`（`change-ledger.ts:148`） | 解析 `[WRITE_FILE]` | 同左；新增兄弟 `parseUnresolvedWriteEvents` | 加法，旧解析行为字节不变 |
| 2 | `diffLedger`（`:827`，闸在 `:875-877`） | `recorded.length === 0` | `valid.length === 0`；`unresolved` 入返回值 | 语义变化：乱码事件不再关闸（§4.1 后两行） |
| 3 | `readTerminalGaps`（`output-writer.ts:172`，`:220-222`/`:238`） | `unjudgeableFiles` = declared \ infra/unresolvable（当布尔为真） | 同左，但布尔来自有效事件；新增 `unresolvedFiles`（warn，不进 `ok`） | `ok` 公式不变；新增 warn 字段 |
| 4 | `writeOutput`（`:257-315`，`:349-356`） | `## Ledger Unjudgeable` 参与首行 `terminalNote` | 不变；新增 `## Ledger Unresolved`（warn 段 + `[FLOW] ledger-unresolved count=N`），**不进** `terminalNote` | 形状镜像 `## Ledger Infra` |
| 5 | settle `exit`/reason（`worker-mode.ts:2740`/`:2746`/`:2756-2760`） | `exit = delivered && gaps.ok ? 0 : 2`；reason 写「trace has no `[WRITE_FILE]` event」 | 公式不变；reason 文案分两支：「零有效事件」与「另有 N 条不可判定写入（已 warn）」 | 文案/可读性，`exit` 语义不变 |
| 6 | PM 回读 `readTerminalDetail`（`ui-bridge.ts:585`，用点 `:789`） | 读 `## Questions` 首行（含 `未记录写入（不可判）：…`） | 首行不变（`unjudgeableFiles` 非空时仍出现）；warn 段在其后 | 无需改代码；`[TOOL]`/widget 面零改动 |

副作用（须在 plan 里列为测试点）：`## Ledger Unresolved` 会让 `readOutputSections` 多一个块；`readTerminalDetail(...,"needs-clarification")` 只取 `Questions` 首行，故不受影响（`output-recovery-contract.test.ts:154` 的断言面不变）。

## 5. 误拦面（AC-005b 守卫）的耦合点与判据

### 5.1 耦合点（一处实现、两处消费，实测行号）

- 守卫：`worker-mode.ts:2216-2260`（`pi.on("tool_call")`），`:2222` `for (const candidate of extractBashWriteCandidates(command))` → `checkBashWriteScopeTarget` → `allow-unknown` 直接 continue、否则审计并可能 `return { block: true }`。
- 账本：`:2356-2359` `pendingBashWrites.set(id, extractBashWriteCandidates(command).map(c => c.target))` → `:2383-2385` 无条件 `appendWriteFileEvent`。
- 现状的**不对称**正是缺陷根源：守卫把 `verbatim=false` 当 `allow-unknown`（不拦），账本却把同一候选当真实写入（记账）⇒「乱码进账本 + 真写入被 `--glob` 伪 target 拦」。

### 5.2 修法（候选集不动，消费谓词分流）

```
extractBashWriteCandidates(cmd)            // 形状不变，两处消费
  ├─ 守卫：verdict = check(c, target, verbatim)      // 不变
  └─ 账本：{recorded, unresolved} = classifyLedgerTargets(cmd)   // 新纯函数
          recorded   = verbatim ∧ 目标 ∉ {"." , ".." , "/"}
          unresolved = ¬verbatim（附 pattern）
```
`classifyLedgerTargets` 由 `tool_execution_end` 调用；两个消费点仍然共用 `extractBashWriteCandidates`，所以「守卫看得见的写入，账本一定见过」这一不变式可由测试锁死（§5.3 C3）。

### 5.3 判据（每条都有可机械判定的形式）

- **C1 派生写入不被拦（伪目标消失）**：对 rq1 全部 122 条命令，`extractBashWriteCandidates` 的 target 集合中不含 `/^--/`、不含反引号、不含换行；实测现状集合 = `{"--glob", "`", "--arg`（`"}`（§0.5 P1）。
- **C2 计数**：按守卫的「首个 blocked 即 break」语义复放 rq1 ⇒ `deny=0`；2 条真写命令各 `allow` 一次（现状 `allow=0 deny=3`，§0.5 P2）。
- **C3 集合包含**：`∀cmd: ledgerTargets(cmd) ⊆ candidates(cmd)`，且 `∀c: ¬verbatim(c) ⇒ ledgerTargets(cmd) ∌ normalize(c.target)`（防止「账本记了守卫没见过的目标」）。
- **C4 越界仍拦**（3/3 deny）：`Set-Content -Path ../other-key/x.md`、`[System.IO.File]::WriteAllText("packages/x.ts", …)`、`echo x > .agenticdoc/<other-key>/evidence/y.md` ⇒ `rule ∈ {deny, scope}`。
- **C5 派生写入放行**：rq1 的 2 条 `.NET` 命令 ⇒ `allowed=true`（目标 `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md` 在 `write_scope` 内）；`python -c "open('.agenticdoc/<key>/evidence/x.md','w')"` ⇒ `allowed=true`。
- **C6 守卫 tier 不变**：`verbatim=false` 仍 `allow-unknown`（不引入新的 block 原因）；`checkBashWriteScopeTarget` 的四个 rule 字面量与 `[WRITE_SCOPE_SUMMARY]` 三计数语义不变（AC-007/T-03 回归锁）。

## 6. AC-008 / AC-017 的测试形态

### 6.1 文件与夹具布局

| 新增/修改 | 文件 | 夹具 | 断言要点 |
|---|---|---|---|
| 修改 | `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts` | 新增 describe `T-DR3/AC-017 extractor soundness`；夹具**内联**：13 字符（`@'\n'-> \`:1175`）、55 字符（rq2 两条）、319/336 字符（rq3）；`.NET` 4 形态；heredoc/`<<<` 对照 | (a)(b)(c) 见 §6.2 |
| 新增夹具 | `packages/coding-agent/test/suite/fixtures/ledger/rq1-write-commands.json`（新目录） | 从 rq1 会话 JSONL 抽出的 **3 条**命令原文（2 条 `.NET` 写 + 1 条 `Write-Output … --glob x`），字节纯净、含 `sha256` | C1/C2/C4/C5 的语料来源；避免把 6,277 字符命令内联进测试源码 |
| 修改 | `packages/coding-agent/test/suite/change-ledger.test.ts` | trace 文本夹具 | (d) + 新事件 parse/format/单行化 |
| 修改 | `packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts` | 现有 `makeFixture` + `worker.emit("tool_execution_start"/"tool_execution_end")`（`harness.ts` + faux provider，**不真跑 bash**） | 端到端：乱码 trace → 仍 `exit=2`/`## Ledger Unjudgeable`；`.NET` 写 → `[WRITE_FILE]` |

### 6.2 AC-017 四段判据的逐条断言

(a) **最小复现产 0 行**（`mwds-t03` 新 describe）：
```ts
// 夹具按 RQ3 §2.3 逐字重建（探针 report-probe-rq3.md P3 已复现现状输出）
for (const fx of [MIN13, RQ2_55, RQ3_319, RQ3_336])
  expect(extractBashWriteCandidates(fx)).toEqual([]);            // 0 候选
expect(classifyLedgerTargets(RQ2_55)).toEqual({ recorded: [], unresolved: [] }); // 0 行 [WRITE_FILE]
```
(b) **`.NET` 各 1 行**：
```ts
expect(extractBashWriteCandidates('[System.IO.File]::WriteAllText("src/a.ts", "x")'))
  .toEqual([{ target: "src/a.ts", pattern: "net-file-api", verbatim: true }]);
expect(extractBashWriteCandidates('[System.IO.File]::AppendAllText("evidence/x.md", "x")')).toHaveLength(1);
expect(classifyLedgerTargets('$path = "evidence/x.md"\n[System.IO.File]::WriteAllText($path, $c)'))
  .toEqual({ recorded: ["evidence/x.md"], unresolved: [] });      // 值环境解析
const unresolved = classifyLedgerTargets("$p = $args[0]\n[System.IO.File]::AppendAllText($p, $c)");
expect(unresolved.unresolved).toHaveLength(1);                    // 无绑定 ⇒ 显式不可判，不记账
```
(c) **`deny=0`**：读 `fixtures/ledger/rq1-write-commands.json`，逐条跑 `checkBashWriteScopeTarget`（config 用 rq1 的 `write_scope`），按守卫的 break 语义计数：
```ts
expect(counts).toEqual({ allowDetermined: 2, deny: 0, allowUnknown: 0 });   // 见 §0.4 的偏差说明
expect(targets.some((t) => t.startsWith("--") || t.includes("`"))).toBe(false);
```
(d) **`unjudgeable` 由有效事件派生**（`change-ledger.test.ts`）：
```ts
expect(diffLedger(REPORT_EXISTING, "[WRITE_FILE] path=`:1175\n", { projectRoot }).unjudgeable).toBe(true);   // 现状 false
expect(diffLedger(REPORT_EXISTING, "[WRITE_UNRESOLVED] pattern=net-file-api target=`x\n", opts).unjudgeable).toBe(false); // 有有效事件时另走 warn
expect(diffLedger(REPORT_EXISTING, "[WRITE_FILE] path=<declared>\n", opts).unjudgeable).toBe(false);
expect(diffLedger(REPORT_EXISTING, "", opts).unjudgeable).toBe(true);   // 回归锁
```
端到端版（`dispatch-recovery-terminal.test.ts`）：`trace.log` 写成乱码事件 + `report.md` 声明一个**存在**的文件 ⇒ `run.exit=2`、`readTerminalDetail` 含 `未记录写入（不可判）`（现状会被判成 `## Ledger Gaps`）。

### 6.3 12 个既有 vitest 文件的影响面

| 文件 | 它锁什么 | 本设计影响 | 处置 |
|---|---|---|---|
| `test/suite/change-ledger.test.ts` | `diffLedger`/`[WRITE_FILE]` 语法/worker_file 生产者（20 处 `WRITE_FILE` 字面） | (d) 语义变化位；其余不变 | 加 3–4 例；既有 8+2+2 例不动 |
| `test/suite/dispatch-recovery-terminal.test.ts` | settle 端到端 ledger（`:289/:313/:339/:350/:369`） | `:350` 用 `echo x > src/a.ts`（verbatim）仍记账 ⇒ 绿 | 不改既有断言，加 1 例乱码 trace |
| `test/suite/mwds-t03-bash-write-scope.test.ts`（63/63 基线） | 抽取器 19 行必需形态、41 label 覆盖、`verbatim` 36 例、heredoc/`< <<`、AC-007 计数 | 抽取器**返回形状不变**；heredoc 用例（`:1644-1730`）必须继续绿——新数据区规则**只**认 `@'`/`@"`，不碰 `<<<`/`<<EOF` | 加 AC-017 describe；既有全绿为回归闸 |
| `test/suite/mwds-t21-write-intent-soundness.test.ts` | 报告声明侧（`collectMalformedCandidates`/`extra`） | 无（不含抽取器） | 不动 |
| `test/suite/mwds-t23-cutover-recheck.test.ts` | `declared launcher.py` 无事件 ⇒ `extra` | 手写 trace 事件仍有效 | 不动 |
| `test/suite/mwds-t25-version-and-dotless.test.ts` | 无扩展名存在性仲裁 | 无 | 不动 |
| `test/suite/mwds-t26-closeout-verify.test.ts` | 真实文件声明无事件 ⇒ 红 | 同上 | 不动 |
| `test/suite/mwgal-t17-ledger-role-aware.test.ts` | writeless 角色（`:188` 零事件 unjudgeable） | 零事件路径语义不变 | 不动 |
| `test/suite/mwgal-t17b-ledger-infra-writes.test.ts` | infra 豁免（`:315`/`:323` 零事件） | 同上 | 不动 |
| `test/suite/mwgal-t17c-ledger-unresolvable.test.ts` | 不存在路径豁免 | 同上 | 不动 |
| `test/suite/mwgal-t21-qg-fixes.test.ts` | gate 文件 RED + `## Ledger Gaps` 端到端 | 无 | 不动 |
| `test/extensions/agent-team-loop.test.ts` | `writeOutput` exit 0/1/2/130、`readTerminalDetail` 读点（`:443-557`、`:2695-2832`） | 无（不碰 `[WRITE_FILE]`） | 不动 |

工作集外的相关基线（spec R8，HEAD 既存红，不得算本次引入）：`worker-file-tool` 7/9、`mwds-t02-write-intent` 38/39；`change-ledger` + checkpoint 22/22、`mwds-t03` 63/63 全绿。

### 6.4 不回归证明方法

1. 逐文件跑（包根，禁全量 `./test.sh`，P-032）：
   `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/<file>.test.ts`
2. 改动前用**同一命令**取基线，用 `--reporter=json`（或默认输出）导出**用例名列表**，改动后 diff 用例名集合；只允许新增，不允许消失/改名。
3. 对 HEAD 既存红（`worker-file-tool` 2 例、`mwds-t02` 1 例）以「失败用例名集合相等」为准，不追平。
4. 端到端两条：`dispatch-recovery-terminal.test.ts`（settle 判据）+ 1 例真实 worker 重放 rq1 形态（可选，落在 `evidence/` 的复现记录里，不进 CI 断言）。

## 未覆盖面声明

- 未跑任何 vitest（只读 + P-032 边界）——§6.3 的「影响面」来自读测试源码与 `grep`，**不是执行结果**；「不回归」以 §6.4 的方法在实现阶段落实。
- 未做端到端 worker 复现；`.NET`/here-string 结论是**函数级**（dist 抽取器 + 守卫），与 `trace.log` 的账本行做了逐值对照（rq1 的 `allow=0 deny=3`、rq2 的 2 行、rq3 的 2 行）。
- 未覆盖 dist 与当前 src 的逐字节等价（`dist` 是已构建产物）；probe 用的是 dist（`require`），源码坐标为 src 行号并已人工对齐（`:1554`/`:2382`/`:2385`）。
- 未覆盖解释器 stdin 载荷的写入识别（`$code | python -`、`python - <<PY`）：本设计只记录 `[WRITE_UNRESOLVED]`，不解析载荷内的写调用（缺口 G-1，AC-008 只要求「≥1 条 unjudgeable 记录」）。
- 未覆盖 PowerShell 其它写形态：`Tee-Object`、`Copy-Item`（非 `cp` 别名）、`[System.IO.StreamWriter]`、`Add-Type` 等（缺口 G-2；属 AC-005b 的既有 fail-open 面，本设计不扩充）。
- 未覆盖 `env` 值环境的作用域边界细节（`$global:`、`$env:`、`Set-Variable`、跨行赋值）；伪码只承诺「单命令、字面量、无展开」。
- 未覆盖多窗口/并发下 trace 追加的原子性（沿既有 best-effort append，GC-4 不变）。
- 未覆盖 `pm/ui-bridge.ts` 中 `readTerminalDetail` 之外的回读分支（`renderWatchLines` 其余路径未穷举）。

## 结论

账本失真的两个方向（伪行 + 漏行）都是同一个结构性缺陷：**抽取器把「文本里出现的类路径片段」当目标，且非 verbatim 目标照样记账**。修法是三条数据流约束——(1) 数据区（PowerShell here-string / heredoc 体）在词法前剥离，正文里的 `>` 不再成为算符；(2) 目标只能取自写动词节点的目标位，并经 `verbatim` + 单命令字面量值环境解析；(3) `[WRITE_FILE]` 只收已解析目标，未解析目标落 `[WRITE_UNRESOLVED]`，`unjudgeable` 改由「有效事件数为零」派生。41 个 label 全部保留（守卫 miss 面），新增 `net-file-api`（`.NET` 静态写方法），新增 1 条 warn 通道，不改任何既有事件语法、不改 `BashWriteCandidate` 形状、不改 `ok` 公式。实测：rq1 的 8 个乱码候选与 `deny=3`、rq2/rq3 的 4 条乱码 `[WRITE_FILE]`、以及「一条乱码事件把 unjudgeable 变全绿」都可被逐条复现并逐条断言。一处 spec 措辞需回写：AC-017(c) 的 `allow=3` 实测应为 `allow=2`（第 3 条被拦命令不是写命令）。

## 证据

| 判据 | 文件:行号 + 原文片段 | 命令与输出 |
|---|---|---|
| 抽取器唯一实现 | `worker-mode.ts:1554` `export function extractBashWriteCandidates(command: string): BashWriteCandidate[] {` | `rg` 全仓命中 1 处；dist 侧 `require` 成功 |
| 无条件记账 | `worker-mode.ts:2383-2385` `for (const bashTarget of bashWrites ?? []) { … appendWriteFileEvent(tracePath, repoRelativePath(bashTarget)); }` | 与 `:2356-2359` `.map((candidate) => candidate.target)` 组成同一链 |
| 41 label | `worker-mode.ts:1222`…`:1545`（31 个 `add(` 调用位） | probe P5 `batteryPatterns=41 batteryMissing=[]` |
| 伪行复现 | `worker-mode.ts:1206-1231`（redirect 族） + `:791-864`（tokenizer） | probe P3 `min13 → target="`:1175", verbatim=false`；`rq2_55 → 2 条` |
| rq1 8 乱码 / 24 .NET / 0 行 | 会话 JSONL + `trace.log:266/352/357/384` | probe P1 `{"bash":122,"ioFileWriteCalls":24,"candidates":8,"targetSet":["--glob","`","--arg`（`"]}`；`trace.log:384 [WRITE_SCOPE_SUMMARY] allow=0 deny=3 allow-unknown=0` |
| 守卫与账本共用候选集 | `:2222`（守卫 for）+ `:2358`（账本 map） | probe P2 `liveCounts {"allowDetermined":0,"deny":3,"allowUnknown":0}`（与 trace 逐值一致） |
| `.NET` 无分支 | `:1291-1553`（switch 内无 `[System.IO.` 识别） | probe P3 `net_write_dq/net_write_sq/net_append/net_var :: []` |
| `unjudgeable` = 零事件派生 | `change-ledger.ts:875-877` `if (recorded.length === 0) { return { …, unjudgeable: judgeable.length > 0 }; }` | probe P3c `existing/junk {"recorded":["`:1175"],"extra":["packages/coding-agent/package.json"],"unjudgeable":false}`、`ghost/junk {"unjudgeable":false,"extra":[]}` |
| 消费者仅 6 处 | `change-ledger.ts:148/:827`、`output-writer.ts:172/:238/:257`、`worker-mode.ts:2740/:2756`、`ui-bridge.ts:585` | `grep -rn 'unjudgeable|parseWriteFileEvents|diffLedger|readTerminalGaps' src` ⇒ 无第 7 处；Python 侧 0 |
| 形状校验不能单独用 | `.agenticdoc` 内容面 `C:\Users\` 1720 行 / `H:\git\` 382 行（RQ3 §6.2），磁盘面 0 例 | 引 RQ3；本设计据此把形状闸限定在报告声明侧 |
| 本会话自然误拦 | `…/woc-dr3-ledger-hardening/trace.log:74` `[WRITE_SCOPE] … blocked=true rule=scope … pattern=redirect target=a.txt)))`、`:75 [TOOL_ERR] …` | 只读探针被拦（`node -e "…require(""…"")…"` 引号错位） |

## 残留与未验证

- 未跑测试：§6.3 的影响面与 §6.2 的断言均为设计，未经执行验证。
- 未验证 `net-file-api` 分支的 PowerShell 真实命令能否被 `bash` 工具执行（本任务只读，不真跑 worker）；分支设计依据是 `[System.IO.File]::WriteAllText` 在命令位的词法形态（`commandBasename` 对 `::` 不做切分，需在 `:1291` 的 switch 内先做 `[System.IO.` 前缀判定）。
- 未验证 `stripDataRegions` 对「POSIX heredoc 体内出现 `@'`」的交互；设计中把两者放进同一行级状态机，但未实测。
- 未验证 `env` 值环境在多条命令（`;`/换行）下的作用域重置策略（设计取「每命令重置」）。
- 未验证 rq3 的 336 字符变体（含 `$code | python -X utf8 -`）在修后是否既无伪行、又产出 ≥1 条 `[WRITE_UNRESOLVED]`；319 变体的 6 候选已在 probe P1 中列全。
- 未验证 `## Ledger Unresolved` 段与 PM widget 的展示宽度/截断（未读 `WATCH_LINE_MAX` 相关渲染分支）。

## 上下文来源

- 卡片：`.agenticdoc/mw-worker-output-contract/tasks/T-DR3-ledger-hardening.md`（`mw-dispatch-card: v1` + `mw-write-surface: v1`）。
- Spec：`.agenticdoc/mw-worker-output-contract/spec.md` §1.5 P4、§1.6 S5、§3 AC-008/AC-017、§2.4 消费者清单、§4 R4/R9。
- 前序研究证据（必读）：`evidence/research/spec-rq3-ledger-20261014.md`（41 label 全枚举、最小复现、消费者、12 个 vitest 文件、形状闸对照）。
- 只读源码：`packages/coding-agent/src/extensions/agent-team-loop/{worker/worker-mode.ts, worker/output-writer.ts, worker/worker-file-tool.ts, worker/output-sections.ts, shared/change-ledger.ts, shared/output-sections.ts, pm/ui-bridge.ts}`；构建产物 `packages/coding-agent/dist/extensions/agent-team-loop/**`（只读 `require`）。
- 语料：`.agenticdoc/mw-write-face-guard/workers/wfg-rq1-write-face-sources/trace.log:266/352/357/384`、`…/task.md`（`write_scope:` 头）；会话 JSONL `~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-13T17-10-27-544Z_*.jsonl`（rq1，122 条 bash）、`…-550Z_*.jsonl`（rq2）、`…17-10-42-324Z_*.jsonl`（rq3）。
- 本任务目录：`report-probe-rq3.md`、`report-probe-rq3b.md`、`report-probe-rq3c.md`（本次实测探针，均为纯只读、`node -` 执行）、`task.md`、`trace.log`。

[VERIFY] positive_signal=(writeVerb×targetPos×verbatim); labels_existing=41 labels_new=1(net-file-api) labels_deleted=0; candidate_shape_unchanged=1; rq1_bash=122 io_file_write_calls=24 candidates=8 targets={--glob,`,--arg`（`} live_summary=allow0_deny3_unknown0; rq2_candidates=2(both_verbatim_false) rq3_candidates=6; min13_rows=1 current→0 planned; net_api_rows=0 current→1 planned; unjudgeable_current=junk_event_closes_gate(unjudgeable=false,extra=[package.json]) unjudgeable_planned=(valid_events==0 && judgeable>0); new_event=WRITE_UNRESOLVED(pattern,target,one_line); new_fields=ChangeLedger.unresolved+TerminalGaps.unresolvedFiles; consumers=6(parseWriteFileEvents diffLedger readTerminalGaps writeOutput settle readTerminalDetail); ac017c_measured_expected=allow2_deny0_unknown0(spec_says_allow3); tests_touched=2files+1fixture tests_unchanged=10; baseline=HEAD(mwds-t03 63/63, change-ledger+checkpoint 22/22, worker-file-tool 7/9, mwds-t02 38/39)
