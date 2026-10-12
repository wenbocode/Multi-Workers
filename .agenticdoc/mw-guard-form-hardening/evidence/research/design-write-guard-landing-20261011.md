# DRQ-1：写面判据的落点与形态补全设计（定稿级）

- Key: `mw-guard-form-hardening`｜阶段 DESIGN｜角色 research（只读，未改任何源码/测试）
- 基线工作树: HEAD `ab546bb64` 之后未提交的当前树（本报告所有行号均为**当前工作树实测**，用 `node` 直接读取 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` 逐行打印取得）
- 输入: RQ-1 `spec-form-inventory-20261011.md`（79 形态，covered 35 / missing 33 / FP 8）、RQ-2 `spec-direction-contract-20261011.md`（verbatim 三档 + P-1…P-6 + 36 条语料）、`spec.md` §3 AC-001/002/007、`pm-state.md` D-002/003/006/007/011、QG-B `mw-dispatch-settle-gates/evidence/quality-gate-code-adversarial-20261011.md` ⑤
- 本文用途：可直接抄进 `design.md` §4（形态/字段/算法/坐标均为定稿级，非方向）
- 本文**不**修改任何源码；`[实测]` = 用 `node --input-type=module` 导入 `dist/.../worker-mode.js` 或跑本文原型脚本得到；`[推导]` = 未跑测的静态结论；`未验证` = 明确标注

**一句话结论**：`verbatim` 必须在 tokenizer 逐字符判定并随 `ShellToken`→`BashWriteCandidate`→`checkBashWriteScopeTarget` 传下去（唯一可行路径，见 §2.5）；33 条缺失形态**全部裁定为「补提取」**，未知档按 **candidate**（非命令）触发；wrapper 递解开箱采用「命令位跳过 + 载荷重 token 化 + 深度上限 3」；审计行加 `blocked=`/`risk=` 两个字段、其余字段与顺序逐字节保留；14 条未覆盖分支逐条给坐标与用例名（其中 6 条属本卡 S1，8 条属其它落点）。

---

## §0 口径与实测设施

| 项 | 值 |
|---|---|
| 目标文件 | `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（2019 行，`node` 实测 LF=2019；注意 `Get-Content`/PowerShell 计数会少 4 行，**一律以 `rg -n` / `node` 行号为准**） |
| 守卫挂载 | `:1467-1498`（`isShellRole && isWritelessRole` 时注册 `tool_call`；循环体 `:1483-1495`，第一个 block 即返回） |
| 只读实测 | 导入 `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js` 的 `tokenizeShellCommand`/`extractBashWriteCandidates`；另在 `node` 里跑了 §2 的 `verbatim` 原型（未落盘） |
| 未运行 | vitest / `npm run check` / `npm run build` / `mw build`（纪律要求，PM 负责） |
| 写入路径 | 仅本目录 `report.md`（过程中本 worker 自己的 bash 调用被守卫拦了 2 次，见 §5.5 现场复现） |

**行号漂移提醒（AC-011）**：RQ-1/RQ-2 报告里的部分坐标与当前树有 ±4 行漂移（例：RQ-2 记 `BashWriteScopeRule` 在 `:629` ✓ 正确；但 Get-Content 口径的 `:625` 是错的）。本报告全部坐标用 `node` 重新锚定，可直接引用。

---

## §1 数据结构改动表（逐字段：现状 → 目标，含唯一构造点）

### 1.1 `ShellToken`（现状 `:659-663`）

| 字段 | 现状 | 目标 | 唯一构造点（当前 `文件:行号`） |
|---|---|---|---|
| `text: string` | 有 | 不变 | `worker-mode.ts:673`（`flush()` push）、`:709`（换行→`;` 算子）、`:720`（控制算子 push） |
| `operator: boolean` | 有 | 不变 | 同上 3 处 |
| `verbatim: boolean` | **无** | **新增，required，无默认值**。语义 = 该 word 不含任何「活」展开成分（活字符表见 §2.1）；算子 token 恒为 `true`（消费方先判 `operator`，该字段对算子无意义但保持总函数） | 必须在上述 3 处**全部**赋值：`:673` 用 `inert`（见 §2.2）、`:709`/`:720` 直接 `verbatim: true` |

> 为什么不能只加「单引号段/转义 span 数组」：`ShellToken` 的消费方（`isCommandPosition`/`shellOperands`/`extractBashWriteCandidates`）只读 `text`，而 `verbatim` 是**整词**判定（跨 span 累积），一个布尔位即可；span 数组会让 `add()` 的签名和测试面同时变宽。RQ-2 P-1 给的括号里「或 `singleQuotedSpans`」是备选，本设计取布尔位（更小）。

### 1.2 `BashWriteCandidate`（现状 `:621-626`）

| 字段 | 现状 | 目标 | 唯一构造点 |
|---|---|---|---|
| `target: string` | 有 | 不变（`trim()` 后的原文，`null` 目标仍在此处被丢弃） | `:802`（`inlineScriptTargets` 内 `targets.push({...})`）、`:815`（`add()` 内 `out.push({...})`） |
| `pattern: string` | 有 | 不变；新增 `pattern` 取值见 §3（`redirect-clobber`、`redirect-fd-target`、`install`、`dd of=`、`tar -x`、`perl -i`、`find -delete`、`shell-payload` 等） | 同上 2 处 |
| `verbatim: boolean` | **无** | **新增，required**。redirect/operand 目标 = 源 token 的 `verbatim`；inline-script 目标 = `scriptToken.verbatim && !/[$\`]/.test(captured)`（RQ-2 P-4，见 §2.6） | 同上 2 处：`:802` 需接收 `scriptVerbatim` 参数；`:815` 改为 `add(token, pattern)` 形态（见 §7.2） |

> `add()` 的最终形态（定稿）：`const add = (source: ShellToken | string, pattern: string, verbatimOverride?: boolean)`。为保持与 `NULL_WRITE_TARGETS`、`trim` 的现有语义逐字节一致，`add` 内部只改「取值与 flush」：`const value = text.trim(); if (value === "" || NULL_WRITE_TARGETS.has(value.toLowerCase())) return; out.push({ target: value, pattern, verbatim: verbatimOverride ?? sourceVerbatim });`。

### 1.3 `BashWriteScopeRule`（现状 `:629`）

| 现状 | 目标 | 消费点 |
|---|---|---|
| `"deny" \| "scope" \| "write-scope"` | 追加 `"allow-unknown"`：`"deny" \| "scope" \| "write-scope" \| "allow-unknown"` | `BashWriteScopeVerdict.rule`（`:650`）、`BashWriteScopeRejection.rule`（`:1006`）、4 处 verdict 字面量（`:967`/`:978`/`:992`/`:1000`）+ 新增的 allow-unknown return（插在 `:960` 之前） |

> 语义边界（必须写进注释，避免误读）：`rule` 同时承载「block 原因」与「非 block 的未知档令牌」。判「是否 block」**只允许**读 `verdict.allowed`（或审计行的 `blocked=`），**禁止**由 `rule === "allow-unknown"` 反推——保持与现状 `if (verdict.allowed) continue;`（`:1485`）同一判据源。

### 1.4 `BashWriteScopeVerdict`（现状 `:647-657`）

| 字段 | 现状 | 目标 | 唯一构造点 |
|---|---|---|---|
| `allowed: boolean` | 有 | 不变 | `:965`(:966? 见注)、`:976`、`:990`、`:1000` + 新增 allow-unknown 返回 |
| `rule?: BashWriteScopeRule` | 3 值 | 4 值（+`allow-unknown`） | 同上 |
| `detail?: string` | block 用 `denied:*` / `outside-allowed-surface` / `outside-declared-write-scope` | 追加 allow-unknown 的固定值 `"target-not-statically-determinable"` | 同上 |
| `reason?: string` | 每个 block 分支都有（人类文案，附允许面） | allow-unknown **不设 `reason`**（不 block，无拒绝文案）；block 三分支文案逐字节不变 | 同上 |
| `target?: string` | block 分支 = `rawTarget` | allow-unknown 同样 = `rawTarget`（不改写、不归一） | 同上 |
| `risk?: "deny-basename"` | **无** | **新增可选**，仅在 allow-unknown 且 raw target 的**末段 basename** 命中 deny-basename 族（`pm-state.md`、`_workers*`）时置位（RQ-2 P-5 / AC-007）。block 分支**不设**该字段 | 新增 allow-unknown 返回处（插在 `:960` 之前） |

> `risk` 的计算放在 `checkBashWriteScopeTarget` 内部（纯函数、无 IO）：`const base = rawTarget.split(/[\\/]/).pop() ?? ""; risk = base === "pm-state.md" || base.startsWith("_workers") ? "deny-basename" : undefined`。F1/F2/F3 与 M18 均命中（§5.4 有真实行示例）。

### 1.5 附带结构

| 结构 | 现状 | 目标 |
|---|---|---|
| `BashWriteScopeConfig`（`:632-644`） | `projectRoot/taskDir/keyDir/trueRoot/writeScope` | **逐字节不变** |
| `BashWriteScopeRejection`（`:1004-1011`） | `ts/rule/detail/target/pattern/command` | 追加 `blocked: boolean`（required）与 `risk?: "deny-basename"`；唯一构造点 = 守卫 handler `:1486-1493`（本卡唯一） |

---

## §2 `verbatim(word)` 定稿算法

### 2.1 定义（与 AC-001 逐字对齐）

```
verbatim(token) := token.text 中不存在「活」的下列字符
  ① $          ② 反引号 `        ③ 词首的 ~       ④ glob/花括号 * ? [ {
「活」= 既不在单引号段内、也不是反斜杠转义的目标。
双引号不提供任何「失活」能力（$ / 反引号 / 词首 ~ / glob 在双引号内仍视为活）；
单引号段与反斜杠转义使其中字符失活。
```

活字符集合（tokenizer 局部常量，**不是** `GLOB_MAGIC_RE:915`）：`{ "$", "`", "*", "?", "[", "{" }`。

- 不含 `]` / `}`：二者单独出现不是 shell 元字符（只在 `[` / `{` 配对时才有意义，而 `[` / `{` 已在集合内）：`> a].txt` 在 bash 中写的就是字面文件 `a].txt`，判 deny 是**正确**行为，不应降级为未知档。这是对 RQ-2 §1.1 中「glob 元字符 (* ? [ {)」枚举的逐字符落实（`GLOB_MAGIC_RE` 是给 `write_scope:` 条目用的**另一个**集合，保持逐字节不变，见 §7.2）。
- `~` 只在**词首**（`word.length === 1` 时刚 append 的那一字符）判活；`a~b` 是普通字面量。
- 判活时字符是否来自双引号**不影响** `$`/反引号/`~`/glob（本设计的裁定，见 §2.4）。

### 2.2 `tokenizeShellCommand` 定稿改动（伪代码，仅列改动面）

```ts
// 新增：tokenizer 局部活字符集（与 GLOB_MAGIC_RE:915 是不同集合，勿合并）
const LIVE_EXPANSION_CHARS = new Set(["$", "`", "*", "?", "[", "{"]);

export function tokenizeShellCommand(command: string): ShellToken[] {
  const tokens: ShellToken[] = [];
  let word = "";
  let hasWord = false;
  let inert = true;                       // 当前 word 迄今无「活」成分
  const append = (ch: string, live: boolean): void => {
    word += ch;
    if (live && (LIVE_EXPANSION_CHARS.has(ch) || (ch === "~" && word.length === 1))) inert = false;
  };
  const flush = (): void => {
    if (hasWord) tokens.push({ text: word, operator: false, verbatim: inert });   // ← 唯一改动
    word = ""; hasWord = false; inert = true;                                     // ← 唯一改动（复位）
  };
  // 各分支的 append 形态：
  //  '...'  单引号段       : append(ch, false)
  //  "..."  双引号段       : append(ch, true)      // $ / ` / glob 在 dq 内仍活（裁定见 §2.4）
  //  dq 内 \x              : append(next, false)
  //  引号外 \x             : append(next, false)
  //  未引用字符            : append(ch, true)
  //  空白/换行/控制算子    : flush()；换行与算子的 push 补 verbatim: true
  flush();
  return tokens;
}
```

改动点清单（逐行）：
- `:673` `tokens.push({ text: word, operator: false })` → `tokens.push({ text: word, operator: false, verbatim: inert })`
- `:674-675` 复位（`word = ""; hasWord = false;`）→ 追加 `inert = true;`
- `:687`/`:689`/`:698`/`:725` 全部 `word += ...` → 改成 `append(..., live)`（活/失活见上表）
- `:709`/`:720` 算子 push → 追加 `verbatim: true`

### 2.3 5 条边界例子（`[实测]`：用 §2.2 原型脚本跑出的逐 token `verbatim`）

| # | 命令 | 目标 token | `verbatim` | 判定结果（契约投影） | shell 语义核对 |
|---|---|---|---|---|---|
| E1 | `printf x > '$T/x'` | `$T/x` | **true** | `deny(scope)`（R2 B12 同形） | 单引号内 `$` 是字面量 ⇒ 路径名真的含 `$T` |
| E2 | `printf x > \$T/x` | `$T/x` | **true** | `deny(scope)`（R2 B13 同形） | 反斜杠转义 ⇒ 同上 |
| E3 | `printf x > "$T/x"` | `$T/x` | **false** | `allow-unknown` + 审计（R2 M2） | dq 内 `$` 仍展开 |
| E4 | `printf x > $T/x` | `$T/x` | **false** | `allow-unknown` + 审计（R2 M1） | 未引用 |
| E5 | `printf x > $'a\tb'` | `$a\tb` | **false** | `allow-unknown` + 审计 | ANSI-C 引用可产生任意字节/换行，且词首 `$` 是活成分 |

原型实测原文（节选，`v=` 即 `verbatim`）：

```
"printf x > '$T/x'"        printf[v=true]  x[v=true]  #>[v=true]  $T/x[v=true]
"printf x > \$T/x"         printf[v=true]  x[v=true]  #>[v=true]  $T/x[v=true]
"printf x > \"$T/x\""      printf[v=true]  x[v=true]  #>[v=true]  $T/x[v=false]
"printf x > $T/x"          printf[v=true]  x[v=true]  #>[v=true]  $T/x[v=false]
"printf x > $'a\tb'"       printf[v=true]  x[v=true]  #>[v=true]  $a\tb[v=false]
```

补充实测（同批，用于「不得误拦」面）：`"a b.txt"` → `v=true`（dq 纯字面量不成未知档）；`'~/x'` → `v=true`（转义/单引号内 `~` 失活 ⇒ 字面目录 `~`）；`~/x` → `v=false`；`"~/x"` → `v=false`；`a~b` → `v=true`；`a].txt` → `v=true`；`"{a,b}.txt"` → `v=false`；`*.txt` → `v=false`；`"\$T/x"` → `v=true`（dq 内 `\$` 失活）；`"\*.txt"` → `v=true`（dq 内转义 glob 失活 ⇒ 字面文件名）。

### 2.4 三条必须落进注释的裁定（否则实现会走偏）

1. **双引号不豁免**（E3/M2/B12/B13 的正确性来源）：`"$T/x"` 与 `$T/x` 目标文本逐字节相同，唯一区分点就是「`$` 是否被单引号/反斜杠失活」。因此**双引号绝不置 `inert`**，单引号/反斜杠**必须**置。这正是 AC-001「引用信息是必需项」的硬要求（`must_block_would_leak_if_quoting_ignored=2`）。
2. **双引号内的 glob 也按「活」处理** = 忠于 AC-001 §1.1 的括注（「未引用」= 不在单引号内、且未被反斜杠转义）。代价：`> "{a,b}.txt"` 归入未知档（多一条审计行），不产生任何误拦。备选（更贴 bash 语义：dq 内 glob 失活 → `"{a,b}.txt"` 判 deny）**被本设计否决**，理由：会让「字面量文件名」与「未知档」的边界多一条例外，且 RQ-2 的语料/投影口径会与实现分叉（§8 第 2 条）。
3. **`~` 只看词首**：`~/x`、`"~/x"` ⇒ `v=false`；`'~/x'`、`\~x`、`a~b` ⇒ `v=true`。**不做 `~` 展开**（RQ-1 R68 的「展开 homedir」方向被 AC-001 覆盖：词首未引用 `~` 属未知档）。

### 2.5 为什么 `verbatim` 必须由 extractor 算出并显式传入（不可在 `checkBashWriteScopeTarget` 内重算）

`checkBashWriteScopeTarget(config, rawTarget)` 只拿到**字符串**，而 `'$T/x'`、`\$T/x`、`"$T/x"`、`$T/x` 四种输入在这一层逐字节相同（§2.3 实测）。所以：
- 计算点 = `tokenizeShellCommand`（唯一能看到引号/转义的位置）；
- 传递链 = `ShellToken.verbatim` → `BashWriteCandidate.verbatim`（§1.2）→ `checkBashWriteScopeTarget(config, candidate.target, candidate.verbatim)`；
- 该参数**required、无默认值**（§7.3 列出必须同步更新的 12 处调用点）。若给默认值 `true`，任何漏传的调用点会静默恢复 P-03 误拦方向，故不采纳。

### 2.6 内联脚本捕获的 `verbatim`（RQ-2 P-4 定稿）

```ts
verbatimOfInlineCapture(script: ShellToken, captured: string): boolean
  = script.verbatim && !/[$\`]/.test(captured)
```

- 保 `open(".git/config","w")` 现行 deny（捕获无 `$` ⇒ 字面量 ⇒ 判定）。
- `python3 -c 'open("$T/x","w")'`（单引号 script，捕获含 `$`）⇒ `allow-unknown`（保守；python 本身不展开 `$`，属**已知漏放**，见 §9）。
- f-string / 变量拼接（`open(f"{p}/x","w")`）⇒ 捕获含 `{` 或 `$` ⇒ 未知档；捕获不到时（如 `open(p + "/x","w")`）⇒ 无 candidate（漏放，登记于 §9）。

### 2.7 `verbatim` 与 `write_scope` 的关系（不动）

`verbatim` 只在 `checkBashWriteScopeTarget` 的**入口**分流；`matchesWriteScopeEntry`（`:935-953`）与 `GLOB_MAGIC_RE`（`:915`）继续用它们自己的 glob 集合匹配 `write_scope:` 条目（条目里 `**`、`*` 是合法 glob）。两者**不得**合并成同一个常量（否则 `write_scope: .agenticdoc/k/evidence/**` 会被 `verbatim` 的活字符判定污染）。注意：`normalizeForCompare` / `isSameOrUnder`（`read-scope.ts`）**不做** `~` 展开（RQ-1 实测），这也是 `~` 必须走未知档的另一半理由。

---

## §3 形态补全清单（RQ-1 的 33 条缺失 + 5 类完全隐形，逐条裁定）

### 3.0 总裁定与未知档的挂载规则（先读这条）

- **33/33 裁定为「补提取」**。理由：这 33 条的写面都是**命令行内可读的字面结构**（白名单命令名 + 固定位 operands + 已知 flag arity + 同串载荷），符合 AC-001 的「可静态确定」；真正的不可判定都出现在 **candidate 的目标 token** 上（含变量/glob/`{}`/占位符），而不是形态本身。
- **未知档是 candidate 级、不是形态级**：`allow-unknown` 只在 `BashWriteCandidate.verbatim === false` 时产生，审计行随之写一条。统一触发条件（全形态共用）：
  1. 目标 token 含活的 `$` / 反引号 / 词首 `~` / glob（§2）；
  2. 目标 token 含 `xargs` 的占位符或 `find -exec` 的 `{}`（§4.5 的 `opaqueTokens`）；
  3. 内联脚本捕获含 `$` / 反引号（§2.6）。
- **不引入「命令级未知档」**：`bash script.sh`、`python x.py`、`node x.js`、`eval "$X"`、`source f`、heredoc body、`-EncodedCommand <base64>`、`-File x.ps1` 一律**不产生 candidate、也不写审计行**（RQ-1 §3 的 ③）。理由：拿不到目标文本，写 `target=<none>` 的审计行既不满足 AC-007 的 `allow_unknown_audited == allow_unknown_count` 口径（会把"无 candidate"算成"未知判定"），也污染审计噪声（RQ-2 C-2 的 `$null` 教训）；这些命令的**完整命令行**已由 `appendTool`（`output-writer.ts:164` 附近）写进 `trace.log`，事后可见。此裁定既是 AC-002 的满足方式（5 类隐形全部"进入判定"，不是"归入未知档"），也必须在 §8/§9 登记为已知漏放。

### 3.1 包装器族（19 条：R01-R05、R06-R11、R14-R16、R18-R20、R23、R25）

统一算法 = §4 的「命令位跳过（`skipWrapperPrefix`）+ 脚本载荷重 token 化递归」；`positive`/`negative` 列给出必须新增的 1 正例 + 1 反例。

| RQ-1 | 形态 | 裁定 | 算法要点（落点） | 正例（期望提取） | 反例（不得误拦 ⇒ 期望 0 候选 / 不 block） |
|---|---|---|---|---|---|
| R01 | `bash -c "…"` | 补提取 | §4.4 脚本载荷；`bash` 进 `SHELL_SCRIPT_WRAPPERS` | `bash -c "echo x > o1.txt"` → `o1.txt (shell-payload)` | `bash -c "rg -n foo ."` → `[]` |
| R02 | `sh -c "…"` | 补提取 | 同上 | `sh -c "echo x > o2.txt"` → `o2.txt` | `sh build.sh` → `[]`（脚本文件内容不可见，不是误拦） |
| R03 | `zsh -c "…"` | 补提取 | 同上 | `zsh -c "echo x > o3.txt"` → `o3.txt` | `zsh -c "cat a > b"`？→ `b`（真写，不算反例）；反例用 `zsh -c "ls > /dev/null"` → `[]`（null 目标） |
| R04 | `dash -c "…"` | 补提取 | 同上 | `dash -c "echo x > o4.txt"` → `o4.txt` | `dash -c "grep -n '>' f"` → `[]` |
| R05 | `ksh -c "…"` | 补提取 | 同上 | `ksh -c "echo x > o5.txt"` → `o5.txt` | `ksh -c "echo hi"` → `[]` |
| R06 | `cmd /c "…"` | 补提取 | §4.4，`cmd` 进 `CMD_SCRIPT_WRAPPERS`，flavor 切 `"cmd"` | `cmd /c "echo x > o6.txt"` → `o6.txt` | `cmd /c "dir"` → `[]` |
| R07 | `powershell -Command "…"` | 补提取 | §4.4，`powershell`/`pwsh` 进 `PS_SCRIPT_WRAPPERS`，`-Command`/`-c` 取载荷（大小写不敏感） | `powershell -Command "Set-Content -Path o7.txt -Value x"` → `o7.txt` | `powershell -Command "Get-Content a.txt"` → `[]` |
| R08 | `pwsh -c "…"` | 补提取 | 同上 | `pwsh -c "Set-Content -Path o8.txt -Value x"` → `o8.txt` | `pwsh -c "Get-ChildItem"` → `[]` |
| R09 | `perl -e "…"` | 补提取 | §3.3 的 perl 内联 pattern 表（只认字符串字面量路径） | `perl -e "open(F,'>','o9.txt')"` → `o9.txt` | `perl -e "print 1"` → `[]`；`grep -rn "open(F,'>'" .` → `[]`（命令名 gate：只有 `perl` 才扫 pattern） |
| R10 | `ruby -e "…"` | 补提取 | §3.3 的 ruby pattern 表 | `ruby -e "File.write('o10.txt','x')"` → `o10.txt` | `ruby -e "puts File.read('x')"` → `[]` |
| R11 | `env VAR=x CMD` | 补提取 | §4.3 `env` 跳过 `NAME=value` 后继续找命令位 | `env FOO=bar cp a b` → `b.txt (cp)` | `env FOO=bar ls` → `[]`；`env` 单独 → `[]` |
| R14 | `sudo -u root cp a b` | 补提取 | §4.3 `sudo` arity 表（`-u` 消耗一个值） | `sudo -u root cp a b` → `b.txt` | `sudo -u root ls` → `[]`；`sudo -n true` → `[]` |
| R15 | `doas cp a b` | 补提取 | `doas` 进 `COMMAND_WRAPPERS`（`-u` 消耗值） | `doas cp a b` → `b.txt` | `doas ls` → `[]` |
| R16 | `xargs -n1 sh -c "…"` | 补提取 | §4.3 xargs flag 跳过 + §4.4 载荷递归；`-I/-i` 记占位符 | `xargs -n1 sh -c "echo x > o11.txt"` → `o11.txt` | `xargs -n1 grep foo` → `[]`；`xargs -I {} sh -c "echo x > {}"` → `{}` 为**未知档**（不 block） |
| R18 | `timeout 5 cp a b` | 补提取 | §4.3 `timeout` 特殊：跳过 flags 后**再吞一个 positional（DURATION）** | `timeout 5 cp a b` → `b.txt`；`timeout -k 5 10 cp a b` → `b.txt` | `timeout 5 grep foo` → `[]`；`timeout 5` → `[]` |
| R19 | `setsid cp a b` | 补提取 | `setsid` 进 `COMMAND_WRAPPERS`（`-c/-f/-w` arity 0） | `setsid cp a b` → `b.txt` | `setsid ls` → `[]` |
| R20 | `stdbuf -o0 cp a b` | 补提取 | §4.3 `stdbuf`：`-o/-i/-e` 消耗值（支持 `-o0` 粘连） | `stdbuf -o0 cp a b` → `b.txt` | `stdbuf -o0 ls` → `[]` |
| R23 | `nice -n 5 cp a b` | 补提取 | §4.3 `nice`：`-n/--adjustment` 消耗值 | `nice -n 5 cp a b` → `b.txt` | `nice -n 5 echo hi` → `[]`；`nice -5 cp a b` → `b.txt`（`-5` arity 0 被跳过） |
| R25 | `time -p cp a b` | 补提取 | §4.3 `time`：`-p/-v/--format/-o` 等 arity 表 | `time -p cp a b` → `b.txt` | `time -p ls` → `[]` |

> R12/R13/R17/R21/R22/R24/R26/R27（现状 COVERED 的 8 条）在新算法下由「`isCommandPosition` 的邻接启发式」升级为「命令位 + 前缀跳过」，行为保持（`env cp a b`、`sudo cp a b`、`xargs rm a`、`stdbuf cp a b`、`nice cp a b`、`time cp a b`、`command cp a b`、`nohup cp a b` 全部仍提取正确目标）。

### 3.2 重定向算子族（2 条：R30、R32）

算法（落点在 `extractBashWriteCandidates` 的 redirect 分支，现 `:820-826`）：当 `tokens[i].operator && tokens[i].text === ">"` 时，按序列解析目标：

```
j = i + 1
if tokens[j] 是 word                         -> target = tokens[j]                  // 现状行为（> >> 2> 1>> <> 的后半 exec 3> 均走此路）
else if tokens[j].text === "|" 且 tokens[j+1] 是 word -> target = tokens[j+1]        // `>|` noclobber
else if tokens[j].text === "&" 且 tokens[j+1] 是 word:
     w = tokens[j+1].text
     if /^\d+$/.test(w) || w === "-"          -> 无 candidate（fd dup / fd close：>&2、2>&1、3>&-）
     else                                     -> target = w                          // bash `>&word` == `&>word`
```

| RQ-1 | 形态 | 裁定 | 算法 | 正例 | 反例（不得误拦） |
|---|---|---|---|---|---|
| R30 | `echo x >| r3.txt` | 补提取 | 上表 `>`+`|` 分支，pattern `redirect-clobber` | `echo x >| r3.txt` → `r3.txt` | `echo x 2>&1` → `[]`（token 序列实测 `["echo","x","2","#>","#&","1"]`） |
| R32 | `echo x >& r5.txt` | 补提取 | 上表 `>`+`&`+非数字分支，pattern `redirect-fd-target` | `echo x >& r5.txt` → `r5.txt` | `echo x >&2` → `[]`；`exec 3>&-` → `[]`（实测 token 序列 `["exec","3","#>","#&","-"]`） |

[实测] token 序列（dist 实跑）：`>|` → `["echo","x","#>","#|","r3.txt"]`；`>&` → `["echo","x","#>","#&","r5.txt"]`；`>&2` → `[...,"#>","#&","2"]`；`2>&1` → `["echo","x","2","#>","#&","1"]`；`&> r6.txt` → `["echo","x","#&","#>","r6.txt"]`（现状已 COVERED）；`<> r4.txt` → `["echo","x","#<","#>","r4.txt"]`（现状已 COVERED）。

> 明确**不做**显式 fd 前缀解析：`2>`/`1>>`/`3>` 的 fd 数字在 token 流里是 `>` 之前的独立 word，既不 `startsWith("-")` 也不在命令位，现状靠副作用已经正确（R34-R36/R39 COVERED）；新增显式解析只会加分支而不改结果。RQ-1 的「建议显式解析 fd 前缀」按最小改动面**不采纳**。

### 3.3 操作数即目标族（7 条：R43、R46、R48、R49、R50、R51、R55）

统一前置：把「`operands.filter(v => !v.startsWith("-"))`」替换为 **flag-arity 感知的 positional 提取**（新增 `positionals(operands, commandName)`，机制见 §4.3 的同一张 arity 表 + `--` 语义），这是 R47/R60 的同一个修复，不是新分支。

| RQ-1 | 形态 | 裁定 | 算法 | 正例 | 反例（不得误拦） |
|---|---|---|---|---|---|
| R43 | `install a.txt b.txt` | 补提取 | `case "install"`：有 `-t/--target-directory DIR` 时 `DIR` + 每个 positional 都是目标；否则 last positional（≥2 个 positional 才取） | `install a.txt b.txt` → `b.txt` | `install -m 755 a.txt b.txt` → `b.txt`（`-m` 吞掉 `755`）；`install a.txt` → `[]` |
| R46 | `dd if=… of=ddf.txt` | 补提取 | `case "dd"`：扫 operands 里 `/^of=(.+)$/` → 目标；`of=` 的**值**为空则跳过 | `dd if=/dev/zero of=ddf.txt bs=1 count=1` → `ddf.txt` | `dd if=a.txt of=/dev/null` → `[]`（null 目标）；`dd if=a.txt` → `[]` |
| R48 | `ln a.txt b.txt` | 补提取 | `case "ln"`：`-t DIR` 时 `DIR` 为目标；否则 ≥2 positional 取 last | `ln a.txt b.txt` → `b.txt` | `ln -s a.txt b.txt` → `b.txt`；`ln a.txt` → `[]`（1 个 positional 是错误用法，不猜） |
| R49 | `rsync a.txt b.txt` | 补提取 | `case "rsync"`：arity 表跳 flags（`-e/--rsh`、`--exclude`、`--include`、`--files-from`、`--chown`、`--chmod`、`--bwlimit`、`--port` 消耗值），≥2 positional 取 last | `rsync a.txt b.txt` → `b.txt`；`rsync -a a.txt b.txt` → `b.txt` | `rsync -a a.txt` → `[]`；`rsync -e ssh a.txt b.txt` → `b.txt`（`-e` 未知时按 arity-0 跳过，`ssh` 落成 positional 但 last 仍是 `b.txt`，fail-safe） |
| R50 | `tar -xf x.tar` | 补提取（受限） | `case "tar"`：解析选项簇字母 + `-f` 的值 + `-C` 的值。有 `-C DIR` → 目标 `DIR`（pattern `tar -C`）；否则 `x` 模式 → 目标 `.`（cwd，pattern `tar -x`）；`c` 模式 → 目标 = `-f` 的值（pattern `tar -c`） | `tar -xf x.tar` → `. (tar -x)`；`tar -xzf x.tgz -C <taskDir>/scratch` → `<taskDir>/scratch`；`tar -czf out.tgz dir` → `out.tgz` | `tar -tzf x.tgz`（列目录=纯读）→ `[]`；`tar -cf out.tar dir` → `out.tar`（真写） |
| R51 | `tar -xzf x.tgz` | 补提取（受限） | 同上（`-xzf` 是同一选项簇） | `tar -xzf x.tgz` → `. (tar -x)` | `tar -xzvf x.tgz` → `. (tar -x)`（真写，非反例）；反例用 `tar -d -f x.tar`（diff）→ `[]` |
| R55 | `perl -i -pe … p1.txt` | 补提取 | `case "perl"`：operands 含 `-i`/`-i<suffix>`/`--in-place[=suffix]` 时，跳过 `-e`/`-E`（及其载荷）后的 positional 全是文件；`-i<suffix>` 时每个文件再加 `<file><suffix>` sidecar（pattern `perl -i`） | `perl -i -pe s/a/b/ p1.txt` → `p1.txt`；`perl -i.bak -pe s/a/b/ p.txt` → `p.txt` + `p.txt.bak` | `perl -pe s/a/b/ p1.txt`（无 `-i`，只输出到 stdout）→ `[]` |

> `tar` 的 `-x` 无 `-C` ⇒ 目标 `.`（= `projectRoot`）在允许面外 ⇒ `deny(scope)`。这是**预期**语义（把归档解到项目根就是越面写），不是误拦；反例列用 `-t` 保证纯读不被拦。若 PM 认为 `tar -x` 无 `-C` 太严，替代方案是归未知档（§8 第 6 条已登记该备选）。

### 3.4 `find` 族（2 条：R56、R57）

| RQ-1 | 形态 | 裁定 | 算法 | 正例 | 反例（不得误拦） |
|---|---|---|---|---|---|
| R56 | `find . -exec rm {} \;` | 补提取（只递归内层） | `case "find"`：取 `-exec` … `;`/`+` 之间的 **token 子数组**（不重新字符串化，保留 token 边界），以 depth+1 递归 `extractFromTokens`；`{}` 进 `opaqueTokens` ⇒ 命中它的 candidate 置 `verbatim=false` | `find <taskDir> -exec rm {} \;` → `<taskDir>` 的 `{}` 目标为未知档但 roots 不参与判定 ⇒ 不 block；`find . -exec rm {} \;` → `{}` 未知档（审计） | `find . -exec grep -l foo {} \;`（纯读）→ `[]`（内层 `grep` 无写目标 ⇒ **不得**因「看到 `-exec` 就当写」而 block，RQ-1 §4.5-4 的教训） |
| R57 | `find . -delete` | 补提取 | `case "find"`：出现 `-delete` ⇒ 把每个搜索根（默认 `.`）作为 candidate（pattern `find -delete`）；只判根、不判匹配集 | `find <taskDir> -name '*.tmp' -delete` → `<taskDir>` ⇒ allow；`find . -name '*.tmp' -delete` → `.` ⇒ deny | `find . -name '*.md' -print` → `[]`（无 `-delete`） |

> R56 的「roots 不参与判定」是刻意的：RQ-1 §4.5-4 的正解是「递归内层命令」而非「把搜索根当写目标」，否则一条纯读 `-exec grep` 会被误拦。`find … -exec rm {} +` 的批处理集合同理走 `{}` 未知档。

### 3.5 其他（3 条：R60、R74、R76）

| RQ-1 | 形态 | 裁定 | 算法 | 正例 | 反例（不得误拦） |
|---|---|---|---|---|---|
| R60 | `rm -- -weird.txt` | 补提取 | `positionals()`：裸 `--` 之后**停止 flag 过滤**，其后全部算 positional（同一机制覆盖 R41 `cp -- a b`、R54 `sed --in-place`） | `rm -- -weird.txt` → `-weird.txt` | `cp -- a.txt b.txt` → `b.txt`；`rm --` → `[]` |
| R74 | `python -c "os.system('cp a b')"` | 补提取（受限） | 新增 `INLINE_EXEC_PATTERNS`（`os.system`/`os.popen`/`subprocess.(run|call|check_call|check_output|Popen)` 的**第一个字符串字面量**参数），捕获串按 §4.2 重 token 化后递归（depth+1）；pattern `shell-payload` | `python3 -c "import os; os.system('cp a b')"` → `b.txt` | `python3 -c "import subprocess; subprocess.run(['ls','-la'])"` → `[]`（列表参数不是字符串字面量）；`grep -rn "os.system" .` → `[]`（命令名 gate） |
| R76 | `node -e "…execSync('cp a b')"` | 补提取（受限） | 同上列表 + `child_process.(execSync|exec|execFileSync|spawnSync|spawn)` | `node -e "require('child_process').execSync('cp a b')"` → `b.txt` | `node -e "console.log(1)"` → `[]`（现状 R77 COVERED）；`node -e "require('child_process').execSync(cmd)"` → `[]`（变量载荷不可确定，不猜） |

### 3.6 PARTIAL 3 条的裁定（R53、R69、R70）

| RQ-1 | 形态 | 裁定 | 说明 |
|---|---|---|---|
| R53 | `sed -i.bak s/a/b/ s2.txt` | **补提取 sidecar** | `-i<suffix>` / `--in-place=<suffix>` ⇒ 除 `s2.txt` 外再提 `s2.txt.bak`（pattern `sed -i`）。正例 `sed -i.bak s/a/b/ s2.txt` → `["s2.txt","s2.txt.bak"]`；反例 `sed -i s/a/b/ s2.txt` → `["s2.txt"]`（无后缀不加） |
| R69 | `cd /tmp && echo x > cd1.txt` | **不修（契约顺延）** | AC-001 把判定定义为 `verbatim` 三档，`cd1.txt` 是 verbatim ⇒ 按 `projectRoot` 解析 ⇒ `deny(scope)`。修 cd 跟踪必须改 `:960` 的 `normalizeForCompare` 实参（RQ-2 P-3「不该改」清单），等于给 AC-001 加第 4 个谓词（`baseStable`）⇒ **需 AC 修订**，本卡不做。见 §8-4、§9 |
| R70 | `cd /tmp && > cd2.txt` | **不修（同上）** | 同上；`>` 无命令的前缀形态在该命令行的 token 流里仍是 redirect（`cd`,`/tmp`,`#&&`,`#>`,`cd2.txt`），目标 `cd2.txt` verbatim ⇒ 现状 deny |

### 3.7 8 条 FP 的消除（AC-002 硬判据 `false_positive_forms == 0`）

| FP 形态（RQ-1 §1） | 消除机制 | 消除后判定 |
|---|---|---|
| `truncate -s 0 F` | flag-arity：`truncate` 的 `-s/--size` 吞掉值 ⇒ positional 只剩 `F` | `F` 判定（surface 内 allow / 面外 deny） |
| `echo x > $(date).txt` | 目标 token `$` 含活 `$` ⇒ `verbatim=false` | `allow-unknown` + 审计 |
| `` echo x > `date`.txt `` | 目标 token 含反引号 ⇒ `verbatim=false` | `allow-unknown` + 审计 |
| `echo x > *.txt` | 活 `*` | `allow-unknown` + 审计 |
| `rm *.txt` | 活 `*` | `allow-unknown` + 审计 |
| `echo x > ~/t1.txt` | 词首活 `~` | `allow-unknown` + 审计 |
| `echo x > {a,b}.txt` | 活 `{` | `allow-unknown` + 审计 |
| `python3 -c "Path(F).write_text('x')"` | **删除** `INLINE_WRITE_PATTERNS` 的裸 `write_(text\|bytes)` pattern（现 `:777`），保留 `Path(...).write_*`（现 `:781`）与 `open(...)`（现 `:776`） | `write_text('x')` 的内容串 `x` 不再成为 candidate；`Path(F)` 走 `:781` ⇒ `F` 判定 |

补充：AC-002 还点名 `> $null`。契约下 `$null` 含活 `$` ⇒ `allow-unknown`（误拦消失，但每次 PowerShell `2>$null` 留一条审计行）。**建议同时采纳 RQ-2 C-2**：`NULL_WRITE_TARGETS`（现 `:753-761`）加一项 `"$null"`（`:814` 已 `toLowerCase()` 比较），使 `$null` 不产生 candidate ⇒ 无审计噪声。这是**提取面收窄**（少一个目标），不违背「不扩大匹配」。

### 3.8 5 类「完全隐形」（AC-002 点名，0 candidate ⇒ 必须进入判定）

| 隐形类 | 现状 [实测] | 目标 | 证据 |
|---|---|---|---|
| `bash -c` / `sh -c` / `zsh -c` / `dash -c` / `ksh -c` | `extractBashWriteCandidates("bash -c \"echo x > o1.txt\"")` = `[]` | 递归提取到 `o1.txt` | §4.4 + [实测] token 序列 `["bash","-c","echo x > o1.txt"]` |
| `cmd /c` | `[]`（RQ-1 说 `cmd /c echo x > P` 因 `>` 仍成 token 而"被抓"，那是**未加引号**形态） | `o6.txt` | §4.4 |
| `powershell -Command` / `pwsh -c` | `[]` | `o7.txt`/`o8.txt`（复用 `POWERSHELL_WRITE_COMMANDS:764-771`） | §4.4 |
| `perl -e` / `ruby -e` | `[]` | `o9.txt`/`o10.txt` | §3.3 |
| `>\|` / `>&` | `>` 后紧跟 operator ⇒ 跳过 ⇒ `[]` | `r3.txt`/`r5.txt` | §3.2 |

### 3.9 额外建议（**超出 RQ-1 的 33 条**，源自 QG-B A1；可被 PM 单独裁掉）

| 形态 | 裁定 | 算法 | 正例 | 反例 |
|---|---|---|---|---|
| `awk '{print > "f"}'` | 建议纳入 | `case "awk"`：对程序的**字符串字面量**跑 `/\bprint\s*>>?\s*(['"])([^'"]+)\1/`，捕获为路径（pattern `awk-print`） | `awk '{print > "o.txt"}' f` → `o.txt` | `awk '{if ($1 > 3) print}' f` → `[]`（`>` 后无字符串字面量） |
| cmd 内建 `copy/move/del/md/rd/ren` | 建议纳入（**仅 flavor==="cmd"**） | `case` 中按 flavor gate：`copy/move/ren` 取 last positional；`del/md/rd` 取全部 positional | `cmd /c "copy a b"` → `b` | `cmd /c "dir"` → `[]`；POSIX 下的 `copy a b`（用户脚本）**不**触发（flavor gate） |
| `eval "…"` | 建议纳入 | 把 `eval` 加进 `SHELL_SCRIPT_WRAPPERS`（第一个 operand 即载荷，递归） | `eval "echo x > f"` → `f` | `eval "$CMD"` → `$CMD` 非写形态 ⇒ `[]`（漏放，登记） |

---

## §4 wrapper 递解开箱算法（定稿）

### 4.0 两个不同概念（不能混成一张表）

| 概念 | 集合 | 语义 | 处理 |
|---|---|---|---|
| **命令位包装器**（后面那个 word 仍是命令） | `sudo` `doas` `env` `command` `nohup` `time` `nice` `stdbuf` `xargs` `timeout` `setsid` | 按已知 flag arity 跳过 flags 后，下一个非 flag word = 内层命令 | `skipWrapperPrefix()`，同一层内解决（**不**递归、不重 token 化） |
| **脚本包装器**（载荷是一段 shell/语言源码） | `bash` `sh` `zsh` `dash` `ksh`（`-c` 及其簇）、`cmd`（`/c`、`/C`、`/k`）、`powershell` `pwsh`（`-Command`/`-c`）、`perl` `ruby` `python` `python3` `py` `node`（`-e`/`-c`） | 载荷**重新 token 化**后进同一套判定（depth+1） | `scriptPayload()` + `extractFromTokens()` 递归 |

`SHELL_WRAPPER_COMMANDS`（现 `:733`）**保持逐字节不变**，作为命令位包装器集合的基底：

```ts
const SHELL_WRAPPER_COMMANDS = new Set(["sudo", "env", "command", "nohup", "time", "nice", "stdbuf", "xargs"]); // 逐字节不变
const COMMAND_WRAPPERS = new Set([...SHELL_WRAPPER_COMMANDS, "doas", "timeout", "setsid"]);
const SHELL_SCRIPT_WRAPPERS = new Set(["bash", "sh", "zsh", "dash", "ksh"]);
const CMD_SCRIPT_WRAPPERS = new Set(["cmd"]);
const PS_SCRIPT_WRAPPERS = new Set(["powershell", "pwsh"]);
const LANG_SCRIPT_WRAPPERS = new Set(["perl", "ruby", "python", "python3", "py", "node"]);
const MAX_UNWRAP_DEPTH = 3;
```

### 4.1 递归核心（签名与主循环重写）

```ts
function extractFromTokens(
  tokens: ShellToken[],
  flavor: "posix" | "cmd",
  depth: number,
  out: BashWriteCandidate[],
  opaqueTokens: Set<string>,      // xargs -I / find -exec 的占位符（默认 {"{}"}）
): void

// 导出函数签名与语义不变（t03/t12 的现有调用点不需要改）
export function extractBashWriteCandidates(command: string): BashWriteCandidate[] {
  const out: BashWriteCandidate[] = [];
  extractFromTokens(tokenizeShellCommand(command), "posix", 0, out, new Set(["{}"]));
  return out;
}
```

主循环（替换现 `:818-826` 的「`token.operator` 分支 + `isCommandPosition` 过滤」）：

```ts
for (let i = 0; i < tokens.length; i++) {
  const token = tokens[i];
  if (token.operator) {                                 // redirect 分支（§3.2，含 >| / >& / fd-dup）
    if (token.text === ">") handleRedirect(tokens, i, out);
    continue;
  }
  const previous = tokens[i - 1];
  const isCommandStart = i === 0 || previous === undefined || previous.operator;  // ; | && || ( ) 换行
  if (!isCommandStart) continue;
  tryCommand(tokens, i, flavor, depth, out, opaqueTokens);   // 内部先 skipWrapperPrefix
}
```

**变化点**：`isCommandPosition`（现 `:735-740`）删去「前一词是 wrapper ⇒ 命令位」这条邻接启发式，包装器改由 `tryCommand` 内部解析。`isCommandPosition` 本身可删除（唯一调用点 `:823`）；`SHELL_WRAPPER_COMMANDS` 保留（被 `COMMAND_WRAPPERS` 引用）。

### 4.2 `skipWrapperPrefix` 与 flag arity 表

```
skipWrapperPrefix(tokens, start) -> commandIndex:
  i = start
  loop:
    if i >= len or tokens[i].operator: return i
    name = basename(tokens[i].text).toLowerCase()
    if !COMMAND_WRAPPERS.has(name): return i
    i = skipWrapperFlags(tokens, i + 1, name)
    continue

skipWrapperFlags(tokens, j, name):
  while j < len and !tokens[j].operator:
    v = tokens[j].text
    if v === "--": j++; continue                     // `--` 之后不再有 flag，等价于立刻返回
    if !v.startsWith("-"):
      if name === "timeout": j++; continue            // timeout 的第一个 positional = DURATION
      if name === "env" and /^[A-Za-z_][A-Za-z0-9_]*=/.test(v): j++; continue   // NAME=value
      break
    // flag：先看是否自带值
    if arity(name, flagBase(v)) === 1:
      j += (flagHasAttachedValue(v) ? 1 : 2)
    else:
      j += 1
  return j

flagBase(v):            v.includes("=") ? v.slice(0, v.indexOf("=")) : (v.startsWith("--") ? v : "-" + v[1])
flagHasAttachedValue(v): (v.includes("=") || (v.startsWith("-") && !v.startsWith("--") && v.length > 2))
arity(name, flag):      WRAPPER_VALUE_FLAGS[name]?.has(flag) ? 1 : 0
```

`WRAPPER_VALUE_FLAGS`（只列**消耗一个值**的 flag；未列出的 flag 一律 arity 0 ⇒ 「不吞值」是安全默认，最坏只造成漏放，不造成误拦）：

| 命令 | 消耗值的 flag |
|---|---|
| `sudo` | `-u/--user` `-g/--group` `-p/--prompt` `-C/--close-from` `-h/--host` `-r/--role` `-t/--type` `-T/--command-timeout` `-U/--other-user` `-R/--chroot` `-D/--chdir` |
| `doas` | `-u` `-C` |
| `env` | `-u/--unset` `-C/--chdir` `-S/--split-string` |
| `nice` | `-n/--adjustment` |
| `stdbuf` | `-i/--input` `-o/--output` `-e/--error` |
| `timeout` | `-k/--kill-after` `-s/--signal` |
| `xargs` | `-n/--max-args` `-I/--replace` `-i` `-d/--delimiter` `-E/--eof` `-P/--max-procs` `-s/--max-chars` `-L/--max-lines` `-a/--arg-file` |
| `time` | `-o/--output` `-f/--format` |
| `command`/`nohup`/`setsid` | （无；`command -p/-v/-V`、`setsid -c/-f/-w/-t` 全 arity 0） |

[实测] 该机制对 RQ-1 缺失行的解析结果（token 序列来自 dist）：`nice -n 5 cp a b` → `["nice","-n","5","cp","a","b"]` ⇒ 跳到 `cp`；`stdbuf -o0 cp a b` ⇒ `-o0` 粘连值 ⇒ 跳到 `cp`；`env FOO=bar cp a b` ⇒ `NAME=value` ⇒ `cp`；`sudo -u root cp a b` ⇒ `-u` 吞 `root` ⇒ `cp`；`timeout 5 cp a b` ⇒ 吞 `5` ⇒ `cp`。

### 4.3 脚本载荷提取（`scriptPayload(operands, name)`）

| 家族 | 载荷定位 | 否定面（必须返回 null） |
|---|---|---|
| POSIX shell | operands 中第一个「flagBase ∈ {`-c`}」的 flag（含 `-lc`/`-ec` 等短簇，**区分大小写**：`-C` 是 noclobber，不是 command）→ 其下一个 operand | `bash script.sh`、`bash`、`bash -x script.sh` |
| `cmd` | `/c`、`/C`、`/k`、`/K` → 下一个 operand | `cmd`、`cmd /?` |
| `powershell`/`pwsh` | 大小写不敏感 `-command`/`-c`（`-commandwithargs` 也可）→ 下一个 operand | `-file`/`-f`（脚本文件）、`-encodedcommand`/`-e`/`-ec`（base64）⇒ null（§3.0 的 ③） |
| `perl`/`ruby`/`python`/`python3`/`py`/`node` | `-c`/`-e`（perl 还需识别 `-pe`/`-ne` 等含 `e` 的短簇）→ 下一个 operand | 无 `-c`/`-e` 时 null |

载荷拿到后：`if (depth < MAX_UNWRAP_DEPTH) extractFromTokens(tokenizeShellCommand(payload), flavorOf(name), depth + 1, out, opaqueTokens)`；`flavorOf(cmd) = "cmd"`，其余 `"posix"`。

### 4.4 占位符（`opaqueTokens`）

- 初始 `new Set(["{}"])`。
- `xargs -I R` / `--replace=R` / `-i R`：把 `R` 加入子递归的 `opaqueTokens`（拷贝后新增，避免污染同级）。
- `find -exec`：以 `{}` 进子递归。
- `add()` 语义：若目标 token 文本**包含**任一 `opaqueTokens` 成员 ⇒ `verbatim = false`（⇒ `allow-unknown` + 审计）。这样 `xargs -I F sh -c "echo x > F.txt"` 也不会被当成字面路径 `F.txt`。

### 4.5 引号已剥离问题（item 4 的核心，5 条规则 + `[实测]`）

载荷是**已被外层 tokenizer 解引用一次**的字符串，重 token 化的正确性靠这 5 条：

1. **丢弃外层 token 的 `verbatim`，不 AND 进去**。反例（必须丢弃）：`bash -c 'echo x > $T/f'` — 外层单引号使外层 token `verbatim=true`，但内层 bash 会展开 `$T`；重 token 化看到未引用的 `$T` ⇒ `v=false` ⇒ `allow-unknown`。若 AND，则 `$T/f` 变 verbatim ⇒ 被 deny（方向违约 + 对 `X=<own>/evidence` 会被合法展开证伪）。**正例对照**：`bash -c "echo x > o1.txt"` ⇒ 内层 `o1.txt` `v=true` ⇒ 正常判定。
2. **载荷内的转义在重 token 化时自动复原**：`bash -c "echo x > \"a b.txt\""` ⇒ 载荷文本 `echo x > "a b.txt"` ⇒ 内层 dq 复原 ⇒ 目标 `a b.txt`。
3. **外层 dq 内的 `\$` 在载荷里变成裸 `$`**：`bash -c "echo \$T > f"` ⇒ 载荷 `echo $T > f` ⇒ 内层 `$T` 活 ⇒ 未知档（正确：内层 bash 确实会展开）。
4. **嵌套 `bash -c "sh -c '…'"` 走同一套** [实测]：`sh -c 'sh -c "echo x > o2.txt"'` → L1 `["sh","-c","sh -c \"echo x > o2.txt\""]` → L2 `["sh","-c","echo x > o2.txt"]` → L3 `["echo","x","#>","o2.txt"]` ⇒ 命中 `o2.txt`。
5. **同引号型的深层嵌套在真实 shell 里本身就是坏的**，tokenizer 的解析与 bash 外层一致，不特殊处理 [实测]：命令文本 `bash -c "bash -c "bash -c "echo x > deep.txt"""` → L1 `["bash","-c","bash -c bash","-c","echo x > deep.txt"]`（外层 dq 在第二个 `"` 处闭合，与 bash 一致）。正确写法（转义或异型引号）在 3 层内可解：`bash -c "bash -c \"echo x > deep.txt\""` → L1 `["bash","-c","bash -c \"echo x > deep.txt\""]` → L2 `["bash","-c","echo x > deep.txt"]` → L3 `["echo","x","#>","deep.txt"]`。

### 4.6 深度上限与成本

- `MAX_UNWRAP_DEPTH = 3`：根调用 depth=0，允许 3 次进箱（覆盖观测到的 `bash -c "sh -c '…'"` 2 层 + 1 层余量）。
- `depth >= MAX_UNWRAP_DEPTH` 时**不再进箱**（载荷里的写面变漏放，方向安全），也不写审计行（无 candidate）。
- 复杂度上界：每层重 token 化一次载荷字符串，嵌套串长度天然递减；无自引用可能（字符串无法包含自身），不存在无界递归；无需环检测。
- 该上限是**成本/可读性**约束，不是正确性约束：真实 shell 也不支持任意深度同型引号嵌套（规则 5）。

### 4.7 heredoc 残余（登记，不在本卡修）

[实测] 现状 `bash <<EOF\ncp a b\nEOF` 会**偶然**提取到 `b`：tokenizer 把换行变成 `;` 算子（现 `:707-711`），于是 body 里的 `cp a b` 落在命令位。副作用是**误拦方向的风险**：`cat <<'EOF'` 的文档体里若出现 `cp a b` 这样的示例文本，会被当真实写命令 ⇒ 可能 deny。本设计**不引入 heredoc body 剥离**（§8-5），原因：需要先做 `<<`/`<<-`/引号形态/终止符的预处理，改动面超出本卡冻结范围，且 RQ-1/AC 的 FP 清单未包含该形态。**登记为残余**（§9）。

---

## §5 审计行定稿

### 5.1 行格式（唯一改动点 = `appendBashWriteScopeTraceLine` 现 `:1017-1027`）

```
[WRITE_SCOPE] <ISO8601 ts> write-scope blocked=<true|false> rule=<deny|scope|write-scope|allow-unknown> detail=<token> [risk=deny-basename ]pattern=<pattern> target=<raw target> cmd=<single-line command ≤200 chars>
```

- 逐字节保留：`[WRITE_SCOPE] ` 前缀、`${ts}`、`write-scope ` 令牌、` rule=` / ` detail=` / ` pattern=` / ` target=` / ` cmd=` 的字段名与顺序、`cmd` 的 `replace(/\s+/g," ").trim().slice(0,200)`（现 `:1021`）、`fs.appendFileSync(...,"utf8")` 与 try/catch 吞错（现 `:1018-1029`）。
- 新增：`blocked=<bool>` 紧跟在 `write-scope ` 之后；`risk=<token>` 作为**可选**字段插在 `rule=` 之前（仅 allow-unknown 且命中 deny-basename 时出现）。
- 字段顺序理由：(a) `write-scope blocked=` 是旧串 `write-scope blocked` 的超串，任何 `includes`/`sed` 前缀式读者继续命中；(b) `blocked` 放最前使「先看有没有被拦」的读者只读第 3 个字段；(c) `risk` 放 `rule`/`detail` 之前，与「严重度标记先于规则细节」的既有 `rule`→`detail` 顺序一致。

### 5.2 字段语义表

| 字段 | 取值 | 语义 | 变化 |
|---|---|---|---|
| `[WRITE_SCOPE]` | 常量 | 守卫审计行标识（AC-005b 契约） | 不变 |
| `<ts>` | `new Date().toISOString()` | 决策时刻 | 不变 |
| `write-scope` | 常量 | 契约令牌（AC-005b 明文要求） | 不变 |
| `blocked` | `true` / `false` | **该 candidate 是否被 block**。唯一权威来源 = `verdict.allowed`（禁止由 `rule` 反推） | **新增** |
| `rule` | `deny`/`scope`/`write-scope`/`allow-unknown` | 触发的判定档（block 三分支语义不变） | 枚举 +1 |
| `detail` | `denied:<reason>` / `outside-allowed-surface` / `outside-declared-write-scope` / `target-not-statically-determinable` | 机器可读原因；沿用 `verdict.detail ?? "blocked"` 的兜底（现 `:1489`） | +1 取值 |
| `risk` | `deny-basename` | 仅 allow-unknown 且 raw target 末段命中 `pm-state.md` / `_workers*` | **新增可选** |
| `pattern` | `candidate.pattern` | 提取模式（`redirect`、`cp`、`shell-payload`、`tar -x` …） | +取值 |
| `target` | `candidate.target`（原文，未归一） | 被判定目标 | 不变 |
| `cmd` | 单行化命令（≤200 字符） | 复现入口 | 不变 |

### 5.3 向后兼容论证（`[实测]` 读者盘点）

[实测] 全仓（含 `-uu --no-ignore`，排除 node_modules/dist）`[WRITE_SCOPE]` 的出现只有 3 处：
- `worker-mode.ts:1024`（写行本体，`rg -n` 锚定）
- `worker-mode.ts:1013`（文档注释里的格式描述，需同步更新）
- `test/suite/mwds-t03-bash-write-scope.test.ts:156`：`filter(line => line.startsWith("[WRITE_SCOPE]"))` ⇒ **加字段不影响**
- Python 侧（`packages/multi-workers/**`）**零命中**：没有任何 launcher/autopilot/monitor/doctor 解析该行（`rg -uu --no-ignore -n "WRITE_SCOPE|write-scope|blocked=" packages/multi-workers` 只命中 `blocked=` 在 gate/auto-decision 里的同名字段，与本行无关）
- `.agenticdoc/**/*.md` 里的出现全部是证据/报告引用文本，不是运行时读者

⇒ 结论：把 `blocked` 从裸词改成 `blocked=<bool>` 只影响「按位置解析第 4 个 token」的读者，而**不存在**这样的读者。AC-005b 的「行含 `write-scope` 令牌 + blocked 命令摘要」继续成立，且 `blocked=<bool>` 让「区分 block / allow-unknown」不再依赖 `rule` 的隐含语义。

### 5.4 2 条真实行示例（block / allow-unknown）

现场复现（本 worker 本次研究被真实拦下 2 次，`target=$null`，命令是 PowerShell 习惯的 `2>$null`）——**block**：
```
[WRITE_SCOPE] 2026-10-11T15:20:51.772Z write-scope blocked=true rule=scope detail=outside-allowed-surface pattern=redirect target=$null cmd=Get-Content a.txt > $null
```
契约后（同一条命令的 `$null` 走 allow-unknown；若采纳 C-2 的 `NULL_WRITE_TARGETS` 新增项则**不产生**该行）：
```
[WRITE_SCOPE] 2026-10-11T15:20:51.772Z write-scope blocked=false rule=allow-unknown detail=target-not-statically-determinable pattern=redirect target=$null cmd=Get-Content a.txt > $null
```
**allow-unknown + risk**（对应 RQ-2 的 F1，AC-007 要求必带 `risk=deny-basename`）：
```
[WRITE_SCOPE] 2026-10-11T15:35:02.104Z write-scope blocked=false rule=allow-unknown detail=target-not-statically-determinable risk=deny-basename pattern=redirect target=$X/pm-state.md cmd=printf x > $X/pm-state.md
```

### 5.5 计数与 AC-007 的可度量出口

在守卫闭包内新增（`bashWriteScopeConfig` 现 `:1467` 附近）：
```ts
const writeScopeCounts = { allowUnknown: 0, allowDetermined: 0, deny: 0 };
```
在 `recordEnd`（现 `:1602`）内、`finishRun(status, exitCode)`（现 `:1613`）之前，仅当守卫已注册时追加一行机器汇总：
```
[WRITE_SCOPE_SUMMARY] allow_unknown=<n> allow_determined=<n> deny=<n>
```
- 满足 AC-001「未知档不是黑箱：必须同时报 `allow_unknown_count` / `deny_count` / `allow_determined_count`」。
- 满足 AC-007 的 `allow_unknown_audited == allow_unknown_count`：左侧 = trace.log 中 `[WRITE_SCOPE]` 且 `blocked=false` 的行数，右侧 = summary 行的 `allow_unknown=`（两个独立来源，可断言不相等即红）。
- 写角色（`bashWriteScopeConfig === undefined`）**零影响**：不注册守卫、不写 summary（VC-024 保持）。
- PM 侧把 `risk=deny-basename` 升级为 `_autopilot/auto-decisions.jsonl` 告警（AC-007 后半）**不在本报告的落点内**（落点是 `pm/pm-orchestrator.ts`/`pm/ui-bridge.ts` 的共享告警出口 `recordDispatchAlarm`/`describeDispatchAlarm`）。本报告只锁定**机器接口**：PM 侧必须按 `blocked=false` ∧ `risk=deny-basename` 两个字段筛选，不许按 `rule=allow-unknown` 单独筛。

### 5.6 守卫 handler 定稿（现 `:1479-1497`）

```ts
pi.on("tool_call", (event) => {
  if (event.toolName !== "bash") return undefined;
  const command = (event.input as { command?: unknown } | undefined)?.command;
  if (typeof command !== "string" || command.trim() === "") return undefined;
  for (const candidate of extractBashWriteCandidates(command)) {
    const verdict = checkBashWriteScopeTarget(config, candidate.target, candidate.verbatim);   // ← 第 3 实参
    if (verdict.rule === "allow-unknown") {                    // 非 block：先审计再继续
      writeScopeCounts.allowUnknown++;
      appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
        ts: new Date().toISOString(), blocked: false, rule: "allow-unknown",
        detail: verdict.detail ?? "target-not-statically-determinable",
        risk: verdict.risk, target: candidate.target, pattern: candidate.pattern, command,
      });
      continue;
    }
    if (verdict.allowed) { writeScopeCounts.allowDetermined++; continue; }
    writeScopeCounts.deny++;
    appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
      ts: new Date().toISOString(), blocked: true, rule: verdict.rule ?? "scope",
      detail: verdict.detail ?? "blocked", target: candidate.target, pattern: candidate.pattern, command,
    });
    return { block: true, reason: verdict.reason };             // 「第一个违规即 block」语义逐字节保留
  }
  return undefined;
});
```

---

## §6 14 条未覆盖分支（QG-B ⑤，逐条：重新锚定的 `文件:行号` + 建议用例名）

坐标全部对**当前工作树**重新锚定（QG-B 报告里有 2 处漂移，已在表内标注）。测试文件命名建议沿用本 key 前缀 `mwgf-`：`packages/coding-agent/test/suite/mwgf-t01-write-guard-forms.test.ts`（BR-01…BR-05、BR-13）、`mwgf-t02-branch-coverage.test.ts`（跨文件分支）。

| # | QG-B 原文坐标 | **重新锚定坐标（当前树）** | 形态 | 建议用例名 | 归属 |
|---|---|---|---|---|---|
| BR-01 | `worker-mode.ts:821` | `worker-mode.ts:820-826`（redirect 分支） | `>\|`、`<>`、`>&`、`&>`、fd 形式 | `it("AC-008/BR-01 redirect operator variants: >| >& fd-dup(2>&1, 3>&-) <> — worker-mode.ts:820-826")` | **本卡 S1** |
| BR-02 | `worker-mode.ts:733` | `worker-mode.ts:733` + `:735-740`（`SHELL_WRAPPER_COMMANDS`/`isCommandPosition`） | 包装器后的命令位（`sudo rm`、`xargs rm`）无测试 | `it("AC-008/BR-02 wrapper command position: sudo rm / xargs -n1 rm — worker-mode.ts:733,735-740")` | **本卡 S1** |
| BR-03 | `worker-mode.ts:835-841` | `worker-mode.ts:835-836`（`case "cp": case "mv":`） | `cp -t DIR` / `mv -t DIR` 目标前置形态（现状提取错位） | `it("AC-008/BR-03 cp -t / mv -t target-directory form — worker-mode.ts:835-836")` | **本卡 S1** |
| BR-04 | `worker-mode.ts:786-803` | `worker-mode.ts:786-793`（`inlineScriptArgument`）、`:796-804`（`inlineScriptTargets`）、`:826-905`（命令 switch）、`:733` | `bash -c`/`sh -c`/`powershell -Command`/`cmd /c`/`perl -e`/`ruby -e`/`dd of=`/`awk`/`install`/`rsync`/cmd 内建 | `it("AC-008/BR-04 wrapper + operand form table: shell/-Command/cmd/perl/ruby/dd/awk/install/rsync — worker-mode.ts:786-905")` | **本卡 S1** |
| BR-05 | `worker-mode.ts:821-824` + `:959-963` | `worker-mode.ts:820-826` + `:959-963`（`checkBashWriteScopeTarget` 入口） | 变量 / `$(…)` 重定向目标的字面判定（A2 误拦方向） | `it("AC-008/BR-05 non-verbatim target gate: $T, \$(date), backtick, glob → allow-unknown — worker-mode.ts:959-963")` | **本卡 S1** |
| BR-06 | `worker-mode.ts:333-335` / `:386-411` | `worker-mode.ts:331-335`（`type:` last-wins）、`:386-402`（`write_scope:` 空值） | 任务书**正文**行覆盖 frontmatter（`type:` 翻角色、`write_scope:` 空值 DoS） | `it("AC-008/BR-06 body line cannot override frontmatter type/write_scope — worker-mode.ts:331-335,386-402")` | S3（DRQ-3 / AC-005） |
| BR-07 | `ui-bridge.ts:250` + `paths.ts:32-34` | `pm/ui-bridge.ts:250`（`startsWith("_")` 豁免）+ `shared/paths.ts:32-34`（`workersDirFor` 拼接未校验 key） | `_`/`.` 前缀 live 外键；key/taskKey 形态零校验（`../` 穿越） | `it("AC-008/BR-07 foreign live key: '_' '.' prefix exemption and '..' key shape — ui-bridge.ts:250, paths.ts:32-34")` | S3（DRQ-3 / AC-006） |
| BR-08 | `ui-bridge.ts:82` | `pm/ui-bridge.ts:82`（`active?.key ?? readIndexMdActive(...)`） | `readIndexMdActive` 隐式兜底不经守卫（A7） | `it("AC-008/BR-08 _index.md active fallback resolves through the claim guard — ui-bridge.ts:82")` | S3（DRQ-3） |
| BR-09 | `deliverable-evidence.ts:121-142` vs `output-sections.ts:66` | `shared/deliverable-evidence.ts:121-142`（`sectionBodies`）vs `shared/output-sections.ts:66`（`SECTION_SPLIT_RE`） | 行中 `## ` 成段差异、`---` 进 oracle 段体、无标题自由文本：parity 测试显式跳过 | `it("AC-008/BR-09 oracle parity: mid-line '## ', '---' body, heading-less free text — deliverable-evidence.ts:121-142 vs output-sections.ts:66")` | S4（AC-009 相邻） |
| BR-10 | `deliverable-evidence.ts:168` | `shared/deliverable-evidence.ts:155-168`（`readRunState(taskDir)?.started_at` → `Number.isFinite(startedAtMs)` 短路） | 无 `run.json` 时反伪造轴关闭（A9） | `it("AC-008/BR-10 no run.json disables the evidence freshness axis — deliverable-evidence.ts:155-168")` | S4 |
| BR-11 | `monitor.ts:704/829` vs `mw_common.py:3117-3120` | `autopilot/monitor.ts:665`（`readTimeline` 尾读）、`:704`（`tickStale`）、`:829`（`blockedOnHuman && !a.tickStale`） vs `packages/multi-workers/mw_common.py:3117-3125`（`_conductor_tick_fresh`） | 无 timeline 角落的面板/doctor 分叉（A10） | `it("AC-008/BR-11 no-timeline corner: panel blockedOnHuman vs doctor not_blocked — monitor.ts:665,704,829 vs mw_common.py:3117")` | S4 |
| BR-12 | `conductor.py:2553-2557` + `roadmap.py:477-483/259-294` | **漂移**：`packages/multi-workers/autopilot/conductor.py:2562-2563`（`stage_of_key.get(gate.key)`）+ `:2620-2627`（`_gate_stage_context`）+ `autopilot/roadmap.py:477-483`（`stage_of_key`，first-wins `setdefault`） | 跨 stage 重复 key 声明 ⇒ 首声明（closed）胜出抑制活跃 stage 的门（A11） | `it("AC-008/BR-12 duplicate key across stages: first declaration wins and suppresses the gate — conductor.py:2562, roadmap.py:477-483")` | S4 |
| BR-13 | `index-store.ts:159-161` | **漂移**：`shared/index-store.ts:164-165`（`findByKey`：`e.key === key` 精确匹配）+ `:101`（精确匹配追加重复行） | 大小写变体 key（A6，Windows） | `it("AC-008/BR-13 case-variant key bypasses findByKey on Windows — index-store.ts:164-165")` | S3（DRQ-3 / AC-006） |
| BR-14 | `ui-bridge.ts:1345-1346/:1402-1404` | `pm/ui-bridge.ts:1345-1346`（`WRITE_INTENT_PATH_RE`）+ `:1299`/`:1402-1404`（`WRITE_INTENT_PATH_WINDOW = 32`、`gapLen > …` 跳过） | 扩展名集外路径、>32 字符间隔的漏放（A3） | `it("AC-008/BR-14 shape-axis: config.toml/Makefile/.env/x.rs and >32-char gaps — ui-bridge.ts:1345,1299,1402-1404")` | S2（DRQ-2 / AC-004） |

> 归属统计：**本卡 S1 承担 5 条**（BR-01…BR-05，全部落 `worker-mode.ts` 写面守卫，本报告 §2-§5 已给出实现蓝图）；BR-06/07/08/13 属 DRQ-3（角色单源 + key 身份），BR-14 属 DRQ-2（目标集轴），BR-09/10/11/12 属 AC-008/AC-009 测试面（无代码落点）。AC-008 的「14 条逐条有测试」由 S4 收口时统一挂 `AC-008/BR-xx` 命名，坐标必须用本表（QG-B 的两处漂移已在表内更正）。

---

## §7 与 deny/scope/write-scope 的交互顺序 + 改动最小面

### 7.1 求值顺序（定稿）

```
checkBashWriteScopeTarget(config, rawTarget, verbatim):
  if (!verbatim)                                   -> { allowed: true, rule: "allow-unknown",
                                                        detail: "target-not-statically-determinable",
                                                        risk?, target: rawTarget }     // 新增，插在 :960 之前
  target = normalizeForCompare(config.projectRoot, rawTarget)      // :960 实参表达式不变，仅位置后移
  denied = bashWriteDenyReason(config, target)                     // :963
  if (denied !== null)                             -> deny   rule="deny"        detail="denied:<denied>"      // :964-974
  if (!isSameOrUnder(taskDir,target) && !isSameOrUnder(evidenceDir,target))
                                                   -> deny   rule="scope"       detail="outside-allowed-surface" // :975-985
  if (writeScope !== undefined && !some(matchesWriteScopeEntry))
                                                   -> deny   rule="write-scope" detail="outside-declared-write-scope" // :986-999
  -> { allowed: true, target: rawTarget }                                                          // :1000
```

**为什么顺序不变**：
1. **verbatim gate 必须在最前**：`normalizeForCompare` 对含 `$`/glob 的 token 给出的是「一个字面名字叫 `$T` 的目录」+ realpath/stat，与实际写入路径无关（P-03 的根因，RQ-1 :823/:953/:960/:975）。先归一就是「对不可判定输入发判定」。
2. **deny 在 verbatim 域内绝对优先**保持不变：`deny` 的定义域是「shell 最终写入的路径」，非 verbatim 的 token 不在该定义域内 ⇒ 二者不是竞争优先级，而是不相交定义域（RQ-2 §1.3，F2 witness）。
3. **scope → write-scope 的次序不变**：`write_scope:` 只是允许面的**交集收窄**（`:986-989` 的表达式与 `:975` 的允许面判定各自逐字节不变），收窄必须在默认面判定之后才有意义。
4. **allow 兜底不变**：`:1000` 仍是唯一 `allowed: true` 的 determined 出口，新增的 allow-unknown 出口是另一个（互斥）分支。

### 7.2 必须逐字节不变（清单，可作 review 勾选表）

| 对象 | 当前坐标 | 状态 |
|---|---|---|
| `bashWriteDenyReason` 6 条子规则 | `:919-933` | 逐字节不变 |
| `matchesWriteScopeEntry` | `:935-953` | 逐字节不变 |
| `GLOB_MAGIC_RE` | `:915` | 逐字节不变（**不**与 `LIVE_EXPANSION_CHARS` 合并） |
| `SHELL_WRAPPER_COMMANDS` 值 | `:733` | 逐字节不变（只被 `COMMAND_WRAPPERS` 展开引用） |
| `NULL_WRITE_TARGETS` | `:753-761` | 唯一允许的改动 = C-2 追加 `"$null"`（可选）；其余逐字节不变 |
| `POWERSHELL_WRITE_COMMANDS` / `POWERSHELL_PATH_FLAGS` | `:764-771` / `:772` | 逐字节不变（`powershell -Command` 的载荷复用它们） |
| `BashWriteScopeConfig` | `:632-644` | 逐字节不变 |
| 三个 block 分支的 `reason` 文案 + `allowedLabel` | `:958`/`:966-972`/`:978-983`/`:992-997` | 逐字节不变 |
| `:975` 允许面判定表达式、`:986-988` write_scope 判定表达式 | — | 表达式不变（仅上面插了一个 gate） |
| `:960` `normalizeForCompare(config.projectRoot, rawTarget)` | — | **实参表达式不变**（RQ-2 P-3「不该改」），只是位置移到 gate 之后 |
| 「第一个违规即 block」 | `:1483-1495` | 语义不变（allow-unknown 的 `continue` 不改变扫描顺序） |
| `INLINE_WRITE_PATTERNS` | `:775-784` | 唯一改动 = **删除** `:777`（裸 `write_(text\|bytes)`，FP 源）；其余逐字节不变，新增 pattern 只追加到新表 |

**被设计改动的对象**（其余全不动）：`ShellToken`、`tokenizeShellCommand`、`BashWriteCandidate`、`extractBashWriteCandidates` 的分支体、`BashWriteScopeRule`/`BashWriteScopeVerdict`/`BashWriteScopeRejection`、`appendBashWriteScopeTraceLine`、`checkBashWriteScopeTarget` 入口、守卫 handler，以及新增的常量/helper（`COMMAND_WRAPPERS`、`WRITE_VALUE_FLAGS`、`SHELL/CMD/PS/LANG_SCRIPT_WRAPPERS`、`extractFromTokens`、`skipWrapperPrefix`、`positionals`、`LIVE_EXPANSION_CHARS`、`MAX_UNWRAP_DEPTH`、`writeScopeCounts`、`appendWriteScopeSummary`）。

### 7.3 必须同步更新的调用点（第 3 实参 `verbatim`）

| 调用点 | 数量 | 改法 |
|---|---|---|
| `worker-mode.ts:1484`（生产，唯一） | 1 | `checkBashWriteScopeTarget(config, candidate.target, candidate.verbatim)` |
| `test/suite/mwds-t03-bash-write-scope.test.ts:438,439,440,441,442,444` | 6 | 直接调用处补第 3 实参 `true`（语料是字面量路径）；另新增 `false` 的用例（VC-004：`'$T/report.md'`/`\$T/report.md` 必须仍 deny） |
| `test/suite/mwds-t12-regression.test.ts:136,137,149,161,173` | 5 | 同上补 `true` |

`extractBashWriteCandidates(command)` 的签名与语义不变（递归核心是内部函数），现有 17 处调用点（t03/t12 等）零改动。

---

## §8 不做什么（被否决的实现路径 + 理由）

| # | 否决项 | 理由 |
|---|---|---|
| 1 | **不调 shell 解释器**（bash dry-run / `bash -n` / `sh -c` 反射解析） | D-003 冻结；且解释器解决不了核心不可判定项（`$VAR`、`$(…)`、glob 结果、脚本文件内容、heredoc body、子 shell 的 `cd` 状态都只在执行期存在）；守卫在 `tool_call` 前置且纯静态（`:1479`），真执行 = 副作用 + TOCTOU；Windows 上真正 shell 是 PowerShell/cmd，用 bash 解析会得到错误语义（RQ-1 §4.4） |
| 2 | 不做 glob 前缀分析（`DIR/prefix*` 可判 ⇒ allow/deny） | RQ-2 C-3 明文不建议：中段 glob（`.../../*/x.md`）会让规则本身变回不可判定，收益远小于新增分支的误拦风险。`*.txt` 等一律 `allow-unknown` |
| 3 | 不做 `~` 展开（`os.homedir()`） | `verbatim` 词首活 `~` ⇒ 未知档（§2.1/§2.4-3）；展开会新增「HOME 可判」的假前提，并让 `write_scope`/deny 的归一基址出现第二条路径。RQ-1 R68 的展开方向被 AC-001 覆盖 |
| 4 | 不做 `cd LITERAL` 基址跟踪 | 需要给 candidate 加基址字段并改 `:960` 的 `normalizeForCompare` 实参（RQ-2 P-3「不该改」），等于给 AC-001 加第 4 个谓词 `baseStable` ⇒ **必须 AC 修订**，不在本卡范围。后果登记：`cd <taskDir> && echo x > report.md` 仍 `deny(scope)`（**已知残余误拦**，见 §9；若 PM 要修，最小 sketch = `BashWriteCandidate.baseDir?: string` + `:960` 改为 `normalizeForCompare(candidate.baseDir ?? config.projectRoot, rawTarget)` + candidate 的 `verbatim` 改为 `staticallyResolvable = verbatim && !baseShifted`） |
| 5 | 不做 heredoc body 剥离 | §4.7：需要 `<<`/`<<-`/引号形态/终止符预处理，改动面超冻结范围；且本 key 的 FP 清单不含该形态。登记为残余（含误拦 witness：`cat <<'EOF'` 的文档体里出现 `cp a b`） |
| 6 | 不做 `source x.sh` / `. x.sh` 展开；`tar -x` 不做成员级判定 | 载荷（脚本内容/归档成员）不在命令行里；`tar` 只判解包根（§3.3），成员路径不可静态判 |
| 7 | 不做 shell function / alias 覆盖追踪（`cp(){ rm -rf …; }`、`alias cp=rm`） | 定义体可能在 profile/rc/上一行，静态不可判；属已知漏放（AC-001 的期望之外） |
| 8 | 不做运行时集合计算（glob 展开集、`{}` 占位符集、`xargs` 输入集、`find -exec {} +` 批处理集） | 目标集由运行期数据决定 ⇒ 一律经 `opaqueTokens` 落 `allow-unknown`（§4.4） |
| 9 | 不引入「命令级未知档」审计（脚本文件调用/`-EncodedCommand`/`eval $VAR`/heredoc 都写审计行） | §3.0：会让 `allow_unknown_audited == allow_unknown_count` 的口径失真（把"无 candidate"算成"未知判定"）+ 审计噪声（RQ-2 C-2 教训）；这些命令的完整文本已进 `trace.log` |
| 10 | 不改 deny 清单语义 / 允许面 / `write_scope` 语义；不把 `<key>/evidence` 并入白名单 | P-05（会让 write-intent 唯一真阳消失）；deny 是绝对优先白名单的既成契约（`:917-933` 注释） |
| 11 | 不显式解析 fd 前缀（`2>`/`1>>`/`3>`） | §3.2 注：现状靠副作用已正确（R34-R36/R39 COVERED），显式解析只加分支不改结果 |
| 12 | 不让 `checkBashWriteScopeTarget` 自己重算 `verbatim` | §2.5：该层拿不到引号/转义信息（四形态在此逐字节相同） |
| 13 | 不新增配置开关 / 不读 env 开关来切换三档 | 契约是行为定义，不是 feature flag；开关会让「未知档必须审计」的 AC-007 等值断言产生未覆盖分支 |
| 14 | 语法纪律 | 只用可擦除 TS（无 enum/namespace/参数属性）、无 `any`、无内联 import；`WRAPPER_VALUE_FLAGS` 用 `Record<string, Set<string>>` 而非 `enum` |

---

## §9 未验证 / 已知漏放 / 残留（诚实登记）

| # | 项 | 状态 |
|---|---|---|
| U-1 | 本设计的「修复后判定」全部是**投影**（本文未改代码、未跑 vitest/check/build）；`verbatim` 算法本身用原型脚本实测（§2.3），但**未集成**到 dist/src | 未验证（按 AC-011 标注） |
| U-2 | 生产 launcher 是否总以 `projectRoot` 为 worker cwd（守卫 `:1470` 注释声称如此） | 未验证（RQ-1 同项）；直接影响 `tar -x` 无 `-C` 的目标 `.`、`cd` 基址残余的严重性 |
| U-3 | `write_scope:` 头存在时第三档（`:986`）与 `verbatim`/未知档的组合行为 | 未验证（推导：未知档在 `:960` 之前返回，不进 `:986`；RQ-2 §6 同项） |
| U-4 | `os.system`/`execSync` 捕获串的**再解析**：python 字面量到 shell 源码之间还有一层转义（`\n`、`\"`、`\$`），本设计直接把捕获文本当 shell 源码 | 未验证；含转义的载荷可能错判（方向：可能多一个未知档，不产生误拦） |
| U-5 | `find -exec` 的 token 子数组递归（不重新字符串化） | 未验证（推导）；RQ-1 未跑真实 `find` |
| U-6 | `--` 语义的完整覆盖面（`cp -- -weird.txt b.txt`、`rm -- -x --`、`sed -- s/a/b/ -- -f`） | 未验证；按「`--` 后全部 positional」的简化规则，多 `--` 会把 `--` 本身当 positional（可能多一个目标，不产生误拦） |
| U-7 | flag arity 表的完备性 | 未列举的 flag 按 arity 0（不吞值）⇒ **漏放方向**（安全）；可能让 flag 的值落成 positional/命令名，不产生误拦 |
| U-8 | perl/ruby/awk 内联 pattern 的覆盖率 | 有限（只认字符串字面量、只认固定调用名）⇒ 漏放；`open(f"{p}/x","w")`/`open(p+"/x","w")` 捕获不到或含 `{` ⇒ 未知档/漏放 |
| U-9 | `verbatim` 原型的 5 条边界只跑了 §2.3 的 15 个用例 | 未跑 fuzz / 未跑 Windows 反斜杠路径（`C:\out\f.md`：`\o`、`\f` 会被 `\` 转义吃掉 ⇒ 文本 `C:outf.md`，与现状 tokenizer 行为一致，属**既有**语义，不是本次引入） |
| U-10 | 11 处测试调用点需补第 3 实参（§7.3） | 未执行（本卡只读）；S4/AC-008 收口时必须一并改，否则 TS 编译失败 |
| U-11 | `[WRITE_SCOPE_SUMMARY]` 在 hard-crash 路径（`process.on("exit")` 兜底，`:1343-1373`）不写 ⇒ 计数丢失 | 设计取「不为 crash 补写」：AC-007 的等值断言只在 `recordEnd` 路径成立；登记 |
| U-12 | **已知残余误拦**：`cd <taskDir> && echo x > report.md`（R69/R70）仍 deny | 契约内（AC-001 三档），修它需要 AC 修订（§8-4）；RQ-1 的 8 条 FP 清单不含该形态，AC-002 的 `false_positive_forms==0` 不受影响 |
| U-13 | 已知漏放（有意保留）：脚本文件调用、heredoc body（含误拦 witness）、`eval $VAR`、`source`、shell function 覆盖、`-EncodedCommand`、`xargs -I` 自定义占位符展开集、glob 展开集 | 见 §3.0/§4.7/§8；`verbatim` 之外的漏放是 fail-open 方向的必然代价（D-002/AC-001 已登记同名代价 F1-F3） |
| U-14 | 契约代价 F1/F2/F3（现状拦 → allow-unknown） | 本设计**确认**该代价（§1.4 的 `risk=deny-basename` + §5.5 的 summary 行 + AC-007 的 PM 侧告警接口）；不可事前阻止，只能事后审计 + run.json 归因 |

**勘误（对本文前段的自我更正）**：§1.4 表中「`:965(:966? 见注)`」应读作 `:965`（`:964` 是 `if (denied !== null) {`，`:965` 是 `return {`，`:966` 是 `allowed: false,`）；四个 `return` 的起始行分别是 `:965`/`:976`/`:990`/`:1000`。

---

## §10 交付物对照、AC 映射、度量与 VC 建议

### 10.1 任务书 8 项交付物 → 章节索引

| 任务书要求 | 本文位置 |
|---|---|
| ① 数据结构改动表（4 个结构，逐字段现状→目标，类型/默认值/唯一构造点） | §1（`ShellToken` §1.1、`BashWriteCandidate` §1.2、`BashWriteScopeRule` §1.3、`BashWriteScopeVerdict` §1.4、附带 §1.5） |
| ② `verbatim` 定稿算法（伪代码 + 单引号/反斜杠/dq 内 `$` 细则 + 5 边界例） | §2（伪代码 §2.2、5 例 §2.3、裁定 §2.4、必需性 §2.5、内联 §2.6） |
| ③ 形态补全清单（33 缺失 + 5 隐形，逐条裁定 + 正/反例） | §3（19 包装器 §3.1、2 重定向 §3.2、7 操作数 §3.3、2 find §3.4、3 其他 §3.5、partial §3.6、8 FP §3.7、隐形 §3.8、额外 §3.9） |
| ④ wrapper 递解开箱算法（含嵌套/引号已剥离/深度上限） | §4（集合 §4.0、递归核心 §4.1、命令位跳过 §4.2、载荷 §4.3、占位符 §4.4、引号 5 规则 §4.5、深度 §4.6、heredoc 残余 §4.7） |
| ⑤ 审计行定稿（字段顺序/语义/向后兼容/2 真实例） | §5（格式 §5.1、语义 §5.2、兼容 §5.3、示例 §5.4、计数出口 §5.5、handler §5.6） |
| ⑥ 14 条未覆盖分支（`文件:行号` + 用例名） | §6（含 2 处漂移更正与归属统计） |
| ⑦ 求值顺序 + 改动最小面 | §7（顺序 §7.1、不变清单 §7.2、调用点 §7.3） |
| ⑧ 不做什么 | §8（14 条否决项 + 理由） |

### 10.2 AC 映射（本报告可交付的判据覆盖）

| AC | 本设计的覆盖 | 判据投影 |
|---|---|---|
| AC-001（方向契约） | §1.3/1.4（rule/risk）、§2（verbatim）、§5.6（gate 位置）、§7.1（顺序） | RQ-2 语料 `false_positives` 16 → **0**（M1-M14/M18/M19 全部 `allow-unknown`，M15-M17 `allow`，逐条投影）；`must_block_currently_allowed` **0**（B1-B14 全部仍 deny：B12/B13 靠 §2.3 E1/E2 的 verbatim=true）；契约代价 F1-F3 登记（§1.4/§5.5/U-14） |
| AC-002（形态覆盖） | §3（33/33 裁定为补提取 + 5 隐形全部进入判定）、§3.7（8 FP 全消除）、§3.9（可选额外） | `forms_missing` 33 → 逐条有裁定；`false_positive_forms` 8 → **0**；5 类 0-candidate 形态 → 全部有 candidate |
| AC-007（可观测性） | §1.4（`risk`）、§5.1-5.6（`blocked=`/`risk=`/summary 行） | `allow_unknown_audited == allow_unknown_count`（两个独立来源，§5.5）；F1-F3 带 `risk=deny-basename`；PM 侧告警接口 = 按 `blocked=false ∧ risk=deny-basename` 筛 |
| AC-008（分支测试化，S1 部分） | §6 的 BR-01…BR-05 | 5/5 给出坐标 + 用例名；其余 9 条给出坐标 + 用例名 + 归属 |
| AC-011（证据标准） | 全文坐标 `node` 重新锚定；§0 漂移提醒；§9 未验证清单；§10.3 勘误 | 所有坐标可被 `rg -n`/`node` 复核 |

### 10.3 勘误（对本文前段的自我更正，AC-011 纪律）

1. §1.4 表格里的「`:965(:966? 见注)`」→ 应读作 `:965`（四个 `return` 起始行：`:965`/`:976`/`:990`/`:1000`；`:964` 是 `if (denied !== null) {`）。
2. §3.0 第 2 条写「这些命令的**完整命令行**已由 `appendTool` 写进 `trace.log`」——**不准确**，实测：`worker-mode.ts::toolTarget`（`:478-497`）只取命令的**第一行**，`output-writer.ts::appendTool`（`:166-172`）再用 `truncLine(target, 80)`（`:128-130`）截到 80 字符。正确表述应为：**这些命令的（首行、≤80 字符）摘要**在 `trace.log` 的 `[TOOL]` 行里可见；多行/长命令的完整文本**不在** trace.log（仅 `worker.log` 有 stdout）。这削弱（但不推翻）「不做命令级未知档审计」的成本论证：该决策的理由 1/2（AC-007 口径不被污染、审计噪声）仍然成立，理由 3（可见性）应降级为「部分可见」。若要补足，最小改法是给命令级未知档单独写 `[WRITE_SCOPE] ... blocked=false rule=allow-unknown detail=opaque-shell-payload pattern=opaque-shell target=-`，但需同时改 AC-007 的计数口径（本设计**不建议**，见 §8-9）。
3. §3.9 的 `awk` 行、§4.0 的 `SHELL_SCRIPT_WRAPPERS` 里未含 `eval`：`eval` 属 §3.9 的「额外建议」，默认**不**在 33 条之内，实现时需 PM 明确采纳。

### 10.4 度量汇总（done 时复测口径）

| 指标 | 前值 | 本设计投影 |
|---|---|---|
| `false_positives`（RQ-2 19 条 must-allow） | 16 | **0** |
| `false_positive_forms`（RQ-1 8 条） | 8 | **0** |
| `must_block_currently_allowed`（RQ-2 14 条） | 0 | **0**（不得回退） |
| `forms_missing`（33） | 33 | **33/33 有裁定（全部补提取）** |
| 完全隐形形态（0 candidate） | 5 类 | **0 类** |
| 契约代价（F1-F3） | — | 3 条登记 + `risk=deny-basename` 审计 |
| 新增审计行字段 | — | `blocked=`（必填）、`risk=`（可选） |
| 新增机器行 | — | `[WRITE_SCOPE_SUMMARY] allow_unknown=/allow_determined=/deny=` |
| 未知档触发点 | 形态级（无） | candidate 级 3 条统一规则（§3.0） |
| 需同步更新的调用点 | — | 12 处（生产 1 + 测试 11，§7.3） |
| 14 条未覆盖分支 | 14 | **14/14 有坐标+用例名**（S1 承担 5，S2 1，S3 4，S4 4） |

### 10.5 VC 建议（供 `design.md` §6 增补，与既有 VC-001…VC-010 对齐）

- VC-001 `verbatim` 判定被 `checkBashWriteScopeTarget` 第 3 实参前置（required，无默认）
- VC-002 `ShellToken`/`BashWriteCandidate` 携带 `verbatim`，3 个 token 构造点 + 2 个 candidate 构造点全部赋值
- VC-003 `BashWriteScopeRule` 含 `allow-unknown`；`BashWriteScopeVerdict` 含可选 `risk`
- VC-004 E1/E2 实测：`'$T/report.md'` 与 `\$T/report.md` 的 token `verbatim=true` 且仍判 `deny(scope)`
- VC-005 RQ-2 投影：`false_positives=0` ∧ `must_block_currently_allowed=0`
- VC-006 33 条形态逐条有判定（本文 §3 的表即实现清单）
- VC-007 5 类隐形形态不再 0 candidate（`bash -c`/`cmd /c`/`powershell`/`perl -e`/`>\|`）
- VC-008 8 条 FP 全消除（含删除 `INLINE_WRITE_PATTERNS:777`）
- VC-009 `>\|`/`>&`/fd-dup 三态正确（`r3.txt` / `r5.txt` / `[]`）
- VC-010 wrapper 递解开箱（命令位 + 载荷 + depth cap 3 + `opaqueTokens`）
- VC-0xx 审计行：`blocked=<bool>` 与 `risk=deny-basename` 存在；`[WRITE_SCOPE_SUMMARY]` 三个计数与 `blocked=false` 行数相等

### 10.6 落点/改动清单（供 `plan.md` 切卡）

| 卡 | 落点 | 变更 | 依赖 |
|---|---|---|---|
| DRQ-1-a | `worker-mode.ts::tokenizeShellCommand` + `ShellToken` | `verbatim` 逐字符判定（§2） | 无 |
| DRQ-1-b | `worker-mode.ts::extractBashWriteCandidates` + 新增 helper | 递归核心 + 命令位跳过 + 载荷 + operand 白名单 + 重定向算子（§3/§4） | a |
| DRQ-1-c | `worker-mode.ts::checkBashWriteScopeTarget` + `BashWriteScopeRule/Verdict` | verbatim gate + `risk`（§1.3/1.4/7.1） | b |
| DRQ-1-d | `worker-mode.ts::appendBashWriteScopeTraceLine`/`BashWriteScopeRejection`/handler/`recordEnd` | `blocked=`/`risk=`/counts/summary（§5） | c |
| DRQ-1-e（测试） | t03/t12 调用点补参 + 新形态用例 + BR-01…BR-05 | VC-001…VC-010 + AC-008 分支 | a-d |

**一句话复核结论**：本设计未引入任何「扩大匹配」的动作（新增形态全部走白名单 + 已知 arity + 字面结构；未知档只增审计不增 block），且 denylist/允许面/`write_scope` 语义逐字节冻结；唯一方向性代价（F1-F3）由 AC-001 明文背书并已给审计标注与 PM 告警接口。

---

## §11 勘误补充（对本文摘要素）

**勘误 #4（摘要行）**：开头「一句话结论」里的「14 条未覆盖分支逐条给坐标与用例名（其中 **6 条属本卡 S1**，8 条属其它落点）」应读作「其中 **5 条**属本卡 S1（BR-01…BR-05），其余 9 条分属 S2 **1** 条（BR-14）/ S3 **4** 条（BR-06/07/08/13）/ S4 **4** 条（BR-09/10/11/12）」，以 §6 表的归属统计为准（5+1+4+4 = 14）。

**勘误 #5（§10.5 的 VC 编号）**：§10.5 最后一项写 `VC-0xx`，落 `design.md` §6 时 PM 应顺延为 `VC-039`（现清单到 VC-038 为止），避免与既有 38 条重号。
