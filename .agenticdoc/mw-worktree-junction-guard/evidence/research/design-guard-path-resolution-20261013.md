# RQ-D1 证据：G1 guard 的命令解析与路径解析可行性（design 期）

- key: `mw-worktree-junction-guard` · 卡: `T-D1-guard-path-resolution` · worker: `wjg-d1-guard-path-r2` · type: research
- 采集时刻: 2026-10-13（UTC+8）。环境实测: Windows `10.0.26100`；PowerShell `5.1.26100.9168`；`node v24.19.0`；`git version 2.53.0.windows.1`；`TEMP=C:\Users\WENBOZ~1\AppData\Local\Temp`。
- 方法: 生产源码只读；全部实测在 `%TEMP%\wjg-d1-probe\**` 内（fixture 含 junction 与临时 git 仓库），真树 `H:\git\Multi-Workers` 零触碰（未建/删 worktree、未动 `node_modules`/junction、未跑任何破坏性命令）。本文是本卡唯一写入物。
- 直接引用的已坐实事实: 事故原文 `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` §1（元凶命令 = `cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"`）；删除 API 矩阵 `.agenticdoc/mw-worktree-junction-guard/evidence/research/spec-junction-semantics-20261009.md` §2.1（RQ-1 已坐实，不重做）。

## TL;DR

1. hook 能拿到**命令原文**（`event.input.command`，schema 只声明 string）、**cwd**（handler 第二参 `ctx.cwd`）、**工具名**（`event.toolName`）；env 不在 event/ctx 里，只能读 `process.env`（与 shell 的 `getShellEnv()` 同基）。
2. hook 内可**同步**做 fs 枚举（handler 可为同步或 async，runner `await` 且**无超时**）；handler **抛出异常 = 工具不执行**（fail-closed），不是崩溃。
3. `parseBashSegments` 能原样取出事故命令的目标 token `$env:TEMP\qg-head`（引号剥离、插值**不展开**），但它的消费方 `checkBashWriteTarget` **不处理任何 env/变量插值**、不跟踪 `Set-Location`、且 `git worktree remove` 不在其写动词集里 ⇒ 对本次事故**零覆盖**。
4. 能拦下事故命令（形态 b）的最小规则 = **对 `git worktree remove` 的操作数展开已知 env 拼写（`$env:N`/`%N%`/`$N`/`${N}`）后解析并扫描；查不到的变量、glob、裸名歧义一律 block**。本卡用 fixture 原型实测：17 例全部按预期判定（含命中/反向对照）。
5. 顶层目标**不存在**时的判据是 **allow**（git 自己会 `fatal: '<p>' is not a working tree`，rc=128、零副作用）；其余枚举不确定态（权限/竞态/断裂链）一律 **block**。
6. junction 检测用 `lstatSync(...).isSymbolicLink()`（断裂链也报 true），**禁用** `readdirSync(..., {recursive:true})`——实测它会跟进 junction。
7. 裸名操作数（如 `git worktree remove wtE`）**不按 cwd 解析**：git 按 worktree id/basename 在注册表里匹配（实测 cwd=`C:\Windows` 也能删掉注册在别处的 `wtE`）⇒ 解析模型必须包含注册表。
8. 未坐实项见末节（TOCTOU、嵌套 `bash -c`、spawnHook/commandPrefix、shell 家族未判定、G2 命令尚不存在等）。

## 事实

### 事实组 1 — `tool_call` hook 能拿到什么 / 能做什么

- [VERIFY] **工具名 / 调用 id / 输入对象**：`packages/coding-agent/src/core/extensions/types.ts:853-856` `interface ToolCallEventBase { type: "tool_call"; toolCallId: string }`；`:858-861` `interface BashToolCallEvent extends ToolCallEventBase { toolName: "bash"; input: BashToolInput }`；`:904-912` `type ToolCallEvent = BashToolCallEvent | ... | CustomToolCallEvent`。类型收窄 helper `isToolCallEventType` 在 `:1018-1030`（`BashToolCallEvent.toolName` 是字面量 `"bash"`，但 union 里的 `CustomToolCallEvent.toolName: string` 会污染直接 `===` 收窄，故用 helper 更稳）。
- [VERIFY] **命令原文**：`packages/coding-agent/src/core/tools/bash.ts:41-45` `const bashSchema = Type.Object({ command: Type.String({ description: "Bash command to execute" }), timeout: ... }); export type BashToolInput = Static<typeof bashSchema>;` —— schema 无 transform，`command` 就是模型给出的原字符串。handler 收到的是**校验后**参数：`packages/agent/src/agent-loop.ts:617-620` `const validatedArgs = validateToolArguments(tool, preparedToolCall); if (config.beforeToolCall) { const beforeResult = await config.beforeToolCall({ ..., args: validatedArgs, ... }, signal); }`。
- [VERIFY] **cwd**：handler 第二参 `ctx: ExtensionContext`（`types.ts:1188` `export type ExtensionHandler<E, R = undefined> = (event: E, ctx: ExtensionContext) => Promise<R | void> | R | void;`），`ExtensionContext.cwd` 定义在 `types.ts:307-313`（注释 `/** Current working directory */`）。实现侧 `runner.createContext()`（`core/extensions/runner.ts:673+`）的 `get cwd(){ return runner.cwd }`，`runner.cwd` 在 `runner.ts:309` `this.cwd = cwd;` 由 loader 注入 = 会话工作目录。
- [VERIFY] **环境变量**：event 与 ctx 都**不带** env。现有两个 guard 直接读 `process.env`：`shared/protected-config.ts:247-249`（`resolveAgentDir()` 默认 `process.env`）与 `shared/implementation-gate.ts:765-766`（`gateDecision(event.toolName, event.input, process.env)`）。bash 工具给子进程的 env = `{ ...getShellEnv() }` 减去 `PI_SESSION_*`、按需加 `PI_PROVIDER/PI_MODEL/PI_SESSION_ID`（`core/tools/bash.ts:158-184`），而 `getShellEnv()` = `{ ...process.env, [pathKey]: binDir+PATH }`（`utils/shell.ts:181-193`）⇒ **shell 看到的 `$env:TEMP` 等与 guard 读到的 `process.env` 同源**（差异只在 PATH 与 PI_*）。
- [VERIFY] **异步限制 / 超时**：`runner.emitToolCall` 对每个 handler `await handler(event, ctx)`（`runner.ts:940-944`），对 handler 无任何超时包装（`runner.ts` 全文无 `timeout` 命中）。handler 返回 `Promise<R|void> | R | void`，**同步 fs 完全合法**。
- [VERIFY] **handler 内做 fs 的仓内先例**：`shared/implementation-gate.ts:247` `entries = fs.readdirSync(path.join(root, AGENTICDOC_DIR), { withFileTypes: true });`、`:107` `fs.statSync(absPath).isDirectory()`、`:257` `fs.statSync(candidate).mtimeMs`；`shared/protected-config.ts:224-243` `recordProtectedBlockTrace` 用 `fs.mkdirSync` + `fs.appendFileSync`。注册入口 `registerImplementationGate`（`:760-775`）→ `gateDecision`（`:686-730`）→ 上面这些同步 fs。
- [VERIFY] **多 handler 的短路路径**：`runner.ts:932-950`，按 extension 注册序、每个 extension 内 handler 顺序 `await`；`if (handlerResult) { result = handlerResult as ToolCallEventResult; if (result.block) { return result; } }` ⇒ 首个 `block=true` **立即 return，后续 handler 不再执行**；非 block 的结果只是覆盖 `result`，最后一个生效。
- [VERIFY] **block 的结果语义**：`packages/agent/src/agent-loop.ts:619-645`，`beforeResult?.block` ⇒ `return { kind: "immediate", result: createErrorToolResult(beforeResult.reason || "Tool execution was blocked"), isError: true }`；`kind: "immediate"` 表示**工具不执行**，reason 作为工具错误文本回给模型。
- [VERIFY] **抛出语义（fail-closed）**：`emitToolCall` 内部**没有** try/catch；异常沿 `core/agent-session.ts:480-498` 冒泡（非 Error 被改写成 `Extension failed, blocking execution: ${String(err)}` 再抛），最终被 `packages/agent/src/agent-loop.ts:657-661` 的 `catch (error)` 接住 → 同样返回 `kind:"immediate"` 错误结果 ⇒ **handler 抛异常 = 工具不执行**（不是进程崩溃）。
- [VERIFY] **无结构化错误码**：`types.ts:1071-1075` `export interface ToolCallEventResult { block?: boolean; reason?: string; }`。G1 的机器可判据只能落在 `reason` 文本（或另写 trace/审计文件，如 `protected-config.ts:224-243` 的 `[PROTECTED_CONFIG]` 行）。
- [VERIFY] **注册位置范式**：`extensions/agent-team-loop/index.ts:42` `registerProtectedConfigGuard(pi);`、`:49` `registerXkeyGateGuard(pi);`、`:59` `registerImplementationGate(pi);`，均在双加载 flag 之后、`if (process.env.PI_WORKER_TASK) workerModeActivate / else pmActivate`（`:62/:64`）之前 ⇒ 三种模式全覆盖。新 guard 应落同位置。
- [VERIFY] **交互式 `!cmd` 不在同一通道**：`types.ts:813-821` `UserBashEvent { command; excludeFromContext; cwd }`，其 result `UserBashEventResult`（`:1078-1083`）只有 `{ operations?, result? }`，**没有 block 字段** ⇒ G1 的"执行前 block"语义只覆盖 agent 的 `tool_call`（本次事故即 agent tool call，jsonl L142）。
- [VERIFY] **`event.input` 可变**：`types.ts:901-902` 注释 `event.input is mutable ... Later tool_call handlers see earlier mutations. No re-validation is performed after mutation.` —— 本 guard 不需要改写，只需读。

### 事实组 2 — 从命令文本取出 `<path>`（PowerShell 为主）

- [VERIFY] **可复用解析件的原文位置**：`shared/implementation-gate.ts:361-518` `function parseBashSegments(command: string): BashSegment[]`，**模块私有（未导出）**；`interface BashSegment { words; redirectTargets }` 在 `:273-278`；反斜杠逃逸集 `BACKSLASH_ESCAPES_UNQUOTED`（`:330-350`，含空格、`;`、`&`、`|`、`<`、`>`、`(`、`)`、`'`、`"`、`\`、`$`、反引号）与 `BACKSLASH_ESCAPES_DOUBLE_QUOTED`（`:352`，仅 `$`、反引号、`"`、`\`、换行）；分隔符处理 `;`（`:452`）、`&&`/`&`/`&>`（`:454-468`）、`||`/`|`（`:470-473`）、`(`/`)`（`:475-478`）、`<`/`<<`（`:480-491`）、`>`/`>>` 与 fd 前缀（`:495-500`）；heredoc 跳过 `:292-325`/`:485-498`。
- [VERIFY] **实测：逐字抽取 :273-518 行到 `%TEMP%` 运行**（probe2；抽取首行 `interface BashSegment {`、末行 `}`）。事故命令原文 `cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"` 输出：
  `[{"words":["cd","H:/git/Multi-Workers"]},{"words":["git","worktree","remove","--force","$env:TEMP\\qg-head"]}]`
  ⇒ **`cd` 分段正确，目标 token 完整可取，且插值保持未展开**（token 字面仍是 `$env:TEMP\qg-head`）。
- [VERIFY] **引号三态实测**（probe2）：`git worktree remove --force '$env:TEMP\qg-head'`（单引号）、双引号、无引号三种写法都得到同一个词 `$env:TEMP\qg-head`（引号剥离、双引号内 `\q` 判为字面反斜杠）⇒ 引号不影响 token 提取，但**单引号下 PowerShell 不会插值**（语义差异需在展开阶段按引号态区分，本卡未要求实现）。
- [VERIFY] **`2>&1` 实测**（probe2）：`... "$env:TEMP\qg-head" 2>&1` 产生第 3 个段 `{"words":["1"]}`（`>` 把 fd 数字 `2` 吞掉、`&` 结束段、`1` 成为新段词）⇒ 不产生坏 token，但消费方必须忽略这类残段。
- [VERIFY] **前置赋值实测**（probe2）：`$t = "$env:TEMP\qg-head"; git worktree remove --force $t` → 段1 `["$t","=","$env:TEMP\\qg-head"]`、段2 `[...,"$t"]` ⇒ 赋值与引用可分别取到，但要 guard 自建变量表（`parseBashSegments` 只管切词）。
- [VERIFY] **`Set-Location` 实测**（probe2）：`Set-Location H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"` 分段正确（`["Set-Location","H:/git/Multi-Workers"]`），但**消费方不跟踪它**（见下条）。
- [VERIFY] **`checkBashWriteTarget` 能力边界（probe1 实测，17 例，原始输出见本节末）**：
  - 能：字面相对路径（正/反斜杠）、单/双引号、`cd` 后相对路径跟踪、`>`/`2>&1` 重定向分离、`rm -rf packages/x/*.ts`（glob token 返回且因 `path.extname("*.ts")` 判为代码路径）。
  - **不能（全部 0 命中）**：`"$env:PROBE_ROOT\packages\x\a.ts"`、`$env:PROBE_ROOT\...`（无引号）、`%PROBE_ROOT%\...`、`$PROBE_ROOT/...`、`${PROBE_ROOT}/...`、`$t\...`（前置赋值后引用）。
  - **不跟踪**：`Set-Location <dir>; rm -rf packages/x/a.ts` → 0 命中（只有 `cd` 被 `:625-628` 识别）。
  - **`git worktree remove` 从不命中**：`WRITE_VERBS = new Set(["tee","cp","mv","rm","sed"])`（`:79`），`verbTargets`/`checkBashWriteTarget`（`:539-637`）只认这些动词 ⇒ `git worktree remove --force <literal>` 也返回 `[]`（probe1 `git-worktree-remove-literal`）。
  - 源码自述的已知缺口：`implementation-gate.ts:24-27` `Not a sandbox: python -c inline writes, pre-written script execution, find -delete/-exec, tar, PowerShell cmdlets, and env-var path spellings are known misses, accepted as legacy gaps.`
- [VERIFY] **token → 路径只有 `~` 展开**：`implementation-gate.ts:526-528` `function resolveToken(dir, token) { return path.resolve(dir, expandTildePath(token)); }`，`expandTildePath`（`:93-101`）只处理 `~`/`~/x`，**无 env 展开**。
- [VERIFY] **POSIX / PowerShell 删除动词的现状**：`rm -rf <path>` 是 `checkBashWriteTarget` 唯一覆盖的删除形态；`Remove-Item -Recurse -Force "<path>"` 只能从 `parseBashSegments` 拿到 words（probe2 `["Remove-Item","-Recurse","-Force","$env:TEMP\\qg-head"]`），**没有任何现成消费逻辑**（不在 `WRITE_VERBS`，也无 PowerShell cmdlet 识别）——需要 guard 自己加。
- 实测矩阵（probe1 原始 JSON，节选）：
  ```
  {"label":"literal-rel","hits":["packages/x/a.ts"]}
  {"label":"cd-then-rel","hits":["packages/x/a.ts"]}
  {"label":"set-location-then-rel","hits":[]}
  {"label":"ps-env-double","hits":[]}
  {"label":"cmd-percent","hits":[]}
  {"label":"posix-brace","hits":[]}
  {"label":"preceding-assign","hits":[]}
  {"label":"incident-verbatim","hits":[]}
  {"label":"git-worktree-remove-literal","hits":[]}
  {"label":"rm-glob","hits":["packages/x/*.ts"]}
  ```

### 事实组 3 — 目标已不存在时的 git 行为（实测）

- [VERIFY] **fixture git 仓库**（`%TEMP%\wjg-d1-probe\gitrepo`，`git 2.53.0.windows.1`）：`git worktree remove --force <missing-or-unregistered>` → `fatal: '<path>' is not a working tree`，**rc=128**；被指向的普通目录 `Test-Path` 仍为 `True`（零副作用）。同一命令对**已成功移除**的 worktree 再执行也是 rc=128。
- [VERIFY] **尾分隔符可被 git 接受**：`git worktree remove --force "<wt>\"` → rc=0；`"<wt>/"` → rc=0；相对路径 `..\wt4` → rc=0。
- [VERIFY] **`git -C <dir>` 的相对路径基准是 `<dir>`**：cwd=`%TEMP%\wjg-d1-probe`、`-C=%TEMP%\wjg-d1-probe\gitrepo`、`git -C <repo> worktree remove --force "sub/wtG"`（注册于 `<repo>\sub\wtG`）→ rc=0（若按 cwd 解析会失败）。
- [VERIFY] **裸名操作数走注册表（worktree id/basename），与 cwd 无关**：注册 worktree `wtE` 于 `%TEMP%\wjg-d1-probe\wtE`，在 cwd=`C:\Windows` 执行 `git -C <repo> worktree remove --force "wtE"` → rc=0 且目录消失；不存在的裸名 `nonexistent-xyz` → `fatal: 'nonexistent-xyz' is not a working tree` rc=128。**⇒ 静态 `path.resolve(cwd, token)` 不能覆盖裸名形态。**

### 事实组 4 — junction 探测原语（Node，实测）

- [VERIFY] **`lstatSync` 对 junction 恒报 symlink**（probe3，fixture 由 `cmd /c mklink /J` 创建）：
  - `lstat(linkGood).isSymbolicLink()` → `true`，`lstat(linkGood).isDirectory()` → `false`，`stat(linkGood).isDirectory()` → `true`（跟随）。
  - `lstat(linkBroken).isSymbolicLink()` → `true`（**目标已删仍是 reparse point**）；`stat(linkBroken)` → `ENOENT`；`readdir(linkBroken)` → `ENOENT`；`existsSync(linkBroken)` → `false`；`realpath(linkBroken)` → `ENOENT`。
  - `readdir(parent, { withFileTypes: true })` → `[{name:"linkBroken",isSymbolicLink:true,isDirectory:false},{name:"linkGood",isSymbolicLink:true,isDirectory:false}]`。
- [VERIFY] **`readdirSync(dir, { recursive: true })` 会跟进 junction**（probe3）：对含 `linkGood -> targetReal` 的目录返回 `["linkBroken","linkGood","linkGood\\sub","linkGood\\sub\\f.txt"]` ⇒ **G1 扫描必须自建显式栈，禁止 `recursive:true`**（否则会走进真树、可能极慢甚至成环）。
- [VERIFY] **顶层目标不存在**：`readdirSync(missing)` → `ENOENT`；`lstatSync(missing)` → `ENOENT`（可据此区分"不存在"与其它错误码）。
- [VERIFY] **引用 RQ-1 已坐实（不重做）**：`spec-junction-semantics-20261009.md` §2.1 —— 只有 `git worktree remove` 自动穿透 junction（任意深度）；`cmd /c rmdir`（无 `/S`）、`rmdir /S /Q <link>`、`Remove-Item -Recurse -Force <link>`、git-bash `rm -rf <link>`、Node `fs.rmSync(recursive)` 默认不穿透；但 `rm -rf <link>/`、`rm -rf <link>/*`、`Remove-Item -Recurse -Force <link>\*`、`rmdir /S /Q <link>\`（尾分隔符/通配）会穿透 1 层。Python 侧 `os.path.isjunction` 在 3.14.3 实测存在（同报告）。

## 对 design 的直接含义

### D1-1 guard 落点与接口草案（可直接写进 design.md）

```
// 新文件 packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts
export interface WorktreeGuardVerdict {
  block: boolean;
  reason?: string;          // AC-002：含链接路径 + 目标 + 可照抄的 mw worktree rm <path>
  target?: string;          // 解析后的 worktree 绝对路径（审计）
  hits: string[];           // 命中的 reparse point 绝对路径
  basis: string;            // 机器可判据：resolved | unresolved:<var> | glob | bare-name-ambiguous
                            //             | reparse-point | target-absent | scan-error:<code> | not-remove
}
export function decideWorktreeRemove(command: string, cwd: string, env: NodeJS.ProcessEnv): WorktreeGuardVerdict;
export function registerWorktreeJunctionGuard(pi: ExtensionAPI): void;
```

- 注册：`extensions/agent-team-loop/index.ts` 双加载 flag 之后、PM/Worker 分支之前（与 `:42/:49/:59` 同位置），只在 `event.toolName === "bash"` 时判定；返回 `{ block: true, reason }`。
- `parseBashSegments` 目前**模块私有**（`:361`）：要么在 `implementation-gate.ts` 加 `export`，要么下沉到 `shared/bash-segments.ts` 由两处共用。**这是 design 需要拍板的一项**（复制一份会留下两套词法漂移）。
- 判定流水线：P1 分段 → P2 识别 `git [-C <dir>] worktree (remove|rm)` 并跟踪 `cd`/`Set-Location`/`sl`/`Push-Location` 更新有效 cwd（`-C` 覆盖 cwd）→ P3 取 `remove` 之后第一个非 `-` token（0 个或多于 1 个 ⇒ block）→ P4 解析 token（R-a..R-d）→ P5 扫描目标（R-4 判据）。
- 扫描实现：`readdirSync(dir,{withFileTypes:true})` + 显式栈 + `lstatSync` 兜底，命中即 block 早退；**禁止 `{recursive:true}`**；建议 entry 预算（例如 20 万条）超限即 block，避免同步阻塞 agent 循环（runner 无 handler 超时，事实组 1）。

### D1-2 路径解析规则草案（要求 3）

| 情形 | 规则 | AC-003 误拦风险 |
|---|---|---|
| **(a) 字面路径可解析** | 无 `$`/`%`/glob/命令替换 ⇒ `path.resolve(base, expandTilde(token))` 后走 R-4 扫描 | 无：probe4 `control-clean-literal` = ALLOW，`junction-literal` = BLOCK |
| **(b) 含插值 `$env:N`/`$N`/`${N}`/`%N%`** | 展开全部拼写（大小写不敏感）+ 命令内 `name=value` / `$t = "..."` 前置赋值，基准 `process.env`；**任一变量查不到 ⇒ block**；全部展开成功则按 (a) 走 | 可解析的干净 worktree 仍放行（probe4 `control-clean-envvar` = ALLOW）；只有"未知变量"小类被误拦，且该类本身不可判定，代价可接受 |
| **(c) 通配 / 尾分隔符** | 尾分隔符 `\`、`/` 剥掉后按 (a)（git 实测接受：`"<wt>\"`、`"<wt>/"` 均 rc=0）；含 `* ? [` 或其它命令替换 ⇒ **block** | 极低：正常 worktree 清理不用通配；依据 RQ-1，`<link>/`+通配正是让"不穿透 API"变穿透的形态，必须拦 |
| **(d) 多段 / `cd` / 相对路径** | 含分隔符或绝对路径 ⇒ `path.resolve(base, token)`，`base = -C 目录 > 命令内 cd/Set-Location 目标 > ctx.cwd`；**裸名（无分隔符）⇒ 必须查注册表**（`<repo>/.git/worktrees/*/gitdir` 或 `spawnSync("git",["-C",repo,"worktree","list","--porcelain"])`）按 basename/id 唯一匹配，无匹配 ⇒ allow（git 会 rc=128 拒绝），歧义或注册表不可读 ⇒ block | 干净 worktree 的绝对/相对路径正常放行；风险集中在"裸名 + 注册表不可读/同名歧义"被 fail-closed 拦下——若 design 不愿在 handler 里读注册表/跑 git，可退化为"裸名一律 block"，需显式记录该 AC-003 让步 |

- **能拦下事故命令（形态 b）的最小规则**（二选一，推荐 R-b 分层）：
  - `R-min`（一行式，成本最低）：`git worktree remove` 的操作数 token 只要含任何插值标记（`$env:` / `%...%` / `$name` / `${...}`）就**无条件 block**。必然拦下事故命令，但会误拦 `git worktree remove "$env:TEMP\<clean>"` 这类可解析的合法调用（AC-003 风险）。
  - `R-rec`（推荐）：先展开再判定（上表 (b)）；展开成功且扫描无 reparse point ⇒ allow，展开失败 ⇒ block。**事故命令 `$env:TEMP` 可解析 → 解析到 `<工作树>\qg-head` → 扫描命中 `node_modules` junction → block**；本卡原型实测 `incident-shape-junction` = BLOCK、`control-clean-envvar` = ALLOW。
  - 两者在"未知变量"处重合，故实现上可把决定权交给展开结果：**展开成功走 R-rec，展开失败即 R-min 的阻塞分支**。

### D1-3 目标已不存在 / 枚举失败（要求 4）

| 情形 | 实测依据 | 判定 | 理由 |
|---|---|---|---|
| 顶层目标 `lstat` 返回 `ENOENT` | `git worktree remove` 对不存在/未注册路径 → `fatal: '<p>' is not a working tree`，rc=128，零副作用 | **allow** | git 在删除前就拒绝，guard 无物可扫；且此时命令不可能造成穿透。前提：路径在 P4 已判定为"完全解析"，未解析变量在 (b) 已 block |
| 顶层目标本身是 reparse point | `lstat.isSymbolicLink()=true` | **block** | 直接命中 G1 判据（AC-001） |
| 树内有**断裂** junction（目标已删） | `lstat(broken).isSymbolicLink()=true`；`stat`/`readdir`/`existsSync` 全部不可用 | **block** | 必须用 `lstat`，不能用 `stat`/`existsSync`；断裂链 = 遗留链接，正是 AC-009 的语料形态 |
| 子目录 `readdir` 报 EACCES/EPERM/EBUSY… | — | **block** | 无法证明"无 reparse point"，fail-closed（与 AC-006 同向） |
| 扫描中途 `ENOENT`（并发删除竞态） | — | **block**（可重试一次，仍失败则 block） | fail-closed |
| 裸名在注册表中无匹配 | git rc=128 | **allow** | 同第一行；git 自身拒绝 |
| 裸名在注册表中多重匹配 / 注册表不可读 | — | **block** | 删除面不可定死 |

- 一句话判据：**"能证明目标树内无 reparse point"才放行；唯一被认可的否定证明是"顶层目标不存在 ⇒ git 自身拒绝"**，其余不确定态一律 block。
- 说明：对"断裂 junction"和"顶层是链接"的 block 是**有意的保守**——这类 worktree 本就没有正常清理价值，一律导向 G2 `mw worktree rm`，不会伤及正常流程。

### D1-4 原型实测（证明规则可执行，非生产代码）

本卡在 `%TEMP%\wjg-d1-probe\probe4.ts` 写了一个规则原型（逐字复用 `implementation-gate.ts:273-518` 的 `parseBashSegments`，自建 env 展开 + lstat 栈扫描），17 例输出：

```
{"label":"incident-shape-junction","block":true,"why":"reparse-point hits=1"}
{"label":"control-clean-envvar","block":false,"why":"clean"}
{"label":"control-clean-literal","block":false,"why":"clean"}
{"label":"junction-literal","block":true,"why":"reparse-point hits=1"}
{"label":"broken-junction","block":true,"why":"reparse-point hits=1"}
{"label":"toplevel-junction","block":true,"why":"reparse-point hits=1"}
{"label":"unknown-var","block":true,"why":"unresolved-var:NOPE_XYZ_123"}
{"label":"cmd-percent","block":true,"why":"reparse-point hits=1"}
{"label":"posix-dollar","block":true,"why":"reparse-point hits=1"}
{"label":"ps-assign-then-ref","block":true,"why":"reparse-point hits=1"}
{"label":"set-location-rel","block":true,"why":"reparse-point hits=1"}
{"label":"cd-rel","block":true,"why":"reparse-point hits=1"}
{"label":"glob","block":true,"why":"unresolved-var:glob"}
{"label":"absent","block":false,"why":"target-absent (git no-op)"}
{"label":"incident-verbatim-qg-head","block":false,"why":"target-absent (git no-op)"}
{"label":"git-C-rel","block":true,"why":"reparse-point hits=1"}
{"label":"plain-rm-junction","block":false,"why":"no-worktree-remove"}
```

- `incident-verbatim-qg-head`（原样事故命令）今天判 allow，因为 `%TEMP%\qg-head` 已不存在 ⇒ 与 D1-3 第一行一致：**现在重放该命令不会造成任何删除**；事故当天该目录存在且含 junction，故命中 `incident-shape-junction` 那一行。
- `plain-rm-junction` 暴露一个**范围问题**：`rm -rf <含 junction 的 worktree>` 不被本规则覆盖。是否需要扩展动词集，取决于 design 对 G1 边界的定义（RQ-1 已坐实 PowerShell `Remove-Item -Recurse` / git-bash `rm -rf` 默认不穿透，但 `<link>/`、`<link>/*` 形态会穿透 1 层）。

### D1-5 测试计划锚点

- 纯函数用例：`decideWorktreeRemove` 直接用 D1-4 的 17 例（正例 + 反向对照），fixture 建在 `os.tmpdir()`，不碰真树。
- 端到端真实派发：照抄 `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts:1-30` 的范式（faux provider → Agent loop → `ExtensionRunner.emitToolCall` → handler 返回 `{block,reason}` → bash 后端用 `BashOperations` recorder 证明**命令未执行**）；与 `test/extensions/agent-team-loop-protected-config.test.ts` 的纯函数层互补。

## 未坐实 / caveat

1. **TOCTOU**：handler 扫描与命令真正执行之间存在时间窗，目标可在其间被并发进程改成含链接的目录。G1 是文本 + fs 启发式，**不是沙箱**（与 `protected-config`/`implementation-gate` 同定位，见 `implementation-gate.ts:24-27`）；结构性闭环依赖 G2。
2. **嵌套执行不可见**：`bash -c "git worktree remove ..."`、`sh -c`、powershell `-Command "..."`、heredoc 载荷都不会被 `parseBashSegments` 展开扫描（heredoc body 被 `:485-498` 整段跳过）⇒ 存在已知绕过形态；同类缺口在 `implementation-gate.ts` 已被接受。
3. **`commandPrefix` 与 `spawnHook`**：bash 工具在 handler 之后才拼 `commandPrefix` 并跑 `spawnHook`（`core/tools/bash.ts:369-370`），guard 看到的是 `event.input.command`；若某会话配置了 `commandPrefix`/`spawnHook` 改写 command/cwd/env，guard 的解析基础会与真实执行不一致。本卡未查仓内是否有这些配置的实际使用。
4. **shell 家族未在 guard 内判定**：Windows 下默认 shell 可能是 WSL bash 或 PowerShell（`utils/shell.ts:114-149`：优先 WSL bash，否则 pwsh/powershell）。同一 token `$env:TEMP` 在 bash 下语义不同；R-b"所有拼写一律展开"是**有意超集**，可能对实际不被 shell 展开的 token（如 PowerShell 里的 `%VAR%`）也做解析 ⇒ 误判方向需在实现期用反向对照确认。
5. **插值语境未区分引号**：单引号内 PowerShell 不插值，但展开器若统一展开会把 `'$env:TEMP\x'` 也解析成路径。本卡未实现引号态感知，未实测其实际影响。
6. **祖先目录是 junction** 未纳入判据（只扫 worktree 子树）。若 `%TEMP%` 自身是指向别处的链，解析结果整体偏移；是否加 `realpath`/前缀比对待 design 决定。
7. **裸名匹配的契约稳定性**：`git worktree remove <裸名>` 按 worktree id/basename 匹配，本轮只在 `git 2.53.0.windows.1` 实测，**未查 git 文档/变更历史**，也未测"多注册项同名 basename"与"suffix 匹配"的确切规则。
8. **注册表解析的替代路径未验证**：直接读 `<repo>/.git/worktrees/*/gitdir` 的可行性（worktree 内 `.git` 是文件、主树是目录；`-C` 目标定位）本轮未实测，仅作为 subprocess 方案之外的备选。
9. **G2 命令当前不存在**：`packages/multi-workers/mw.py` 里 grep 不到 `worktree` 子命令（0 命中）⇒ AC-002 的报错文本现在无法指向一条真正可执行的 `mw worktree rm <path>`；依赖 T-D2。
10. **仅覆盖 `git worktree remove`**：`rm -rf`、`Remove-Item -Recurse`、`rd /s`、`robocopy /MIR` 等其它删除通道不在本规则；其中 `rm -rf <link>/`、`rm -rf <link>/*`、`Remove-Item -Recurse -Force <link>\*`、`rmdir /S /Q <link>\` 的穿透形态由 RQ-1 坐实，是否纳入 G1 是 design 边界决策（见 D1-4 末条）。
11. **`{recursive:true}` 跟进 junction** 是 `node v24.19.0` 实测结论，其它 Node 版本未验。
12. **Python 侧扫描语义**（`os.path.isjunction` 之外的递归/预算/fail-closed 细节）不在本卡范围，属 AC-009/doctor 与 T-D3。
13. **性能数字未实测**：本卡未在真实规模 worktree（数千~数万目录项）上测扫描耗时与 entry 预算取值；"20 万条"只是建议值（推算，非实测）。

## 上下文来源

（本两节由 PM 于吸收卡片结果时补录：worker 交付内容完整，但缺"上下文来源""残留与未验证"两个规范标题，实质内容散见上文 `[VERIFY]` 与 `## 未坐实 / caveat`。补录不改动任何上文原文。）

只读引用清单（逐条取自上文 `[VERIFY]`，均为本卡实际读过并摘录的 `文件:行`）：

| 文件 | 行 | 用途 |
|---|---|---|
| `packages/coding-agent/src/core/extensions/types.ts` | `:853-861`、`:901-902`、`:904-912`、`:1018-1030`、`:1071-1075`、`:1078-1083`、`:1188`、`:307-313`、`:813-821` | `tool_call` 事件与 handler 契约、`ToolCallEventResult` 无结构化错误码、`event.input` 可变性、`ExtensionContext.cwd`、`UserBashEvent` 无 block 通道 |
| `packages/coding-agent/src/core/tools/bash.ts` | `:41-45`、`:158-184`、`:369-370` | `command` 原串、子进程 env 构造（`getShellEnv()` 派生）、`commandPrefix`/`spawnHook` 在 handler 之后才生效 |
| `packages/agent/src/agent-loop.ts` | `:617-620`、`:619-645`、`:657-661` | 校验后参数传给 `beforeToolCall`；`block` → `kind:"immediate"`（工具不执行）；异常同一出口 |
| `packages/coding-agent/src/core/extensions/runner.ts` | `:932-950`、`:940-944`、`:673+`、`:309` | 多 handler 短路、`await handler` 无超时包装、`ctx.cwd` 来源 |
| `packages/coding-agent/src/core/agent-session.ts` | `:480-498` | handler 异常冒泡与文案改写 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts` | `:24-27`、`:79`、`:93-101`、`:107`、`:247`、`:257`、`:273-278`、`:292-350`、`:352`、`:361-518`、`:452-500`、`:526-528`、`:539-637`、`:620`、`:625-628`、`:686-730`、`:760-775` | 词法解析件与写面判定的全部能力边界（私有无导出、写动词集、`~` 展开、同步 fs 先例、注册链） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts` | `:224-243`、`:247-249` | handler 内同步 fs + 审计行先例、`process.env` 读法 |
| `packages/coding-agent/src/extensions/agent-team-loop/index.ts` | `:42`、`:49`、`:59`、`:62/:64` | guard 注册位置范式（双加载 flag 之后、PM/Worker 分支之前） |
| `packages/coding-agent/src/utils/shell.ts` | `:114-149`、`:181-193` | shell 家族选择（WSL bash / pwsh / powershell）、`getShellEnv()` |
| `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` | §1 | 事故命令原文（元凶一行） |
| `.agenticdoc/mw-worktree-junction-guard/evidence/research/spec-junction-semantics-20261009.md` | §2.1 | RQ-1 已坐实的删除 API 穿透矩阵（本卡不重做） |
| `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts` | `:1-30` | 端到端"命令未执行"证明范式 |
| `packages/coding-agent/test/extensions/agent-team-loop-protected-config.test.ts` | 全文 | 纯函数层测试范式 |
| `packages/multi-workers/mw.py` | 全仓 grep `worktree` | 0 命中：G2 命令尚不存在 |

- 实测环境（本轮）：Windows `10.0.26100`、PowerShell `5.1.26100.9168`、`node v24.19.0`、`git 2.53.0.windows.1`；全部 fixture 落 `%TEMP%\wjg-d1-probe\**`，结束时整目录删除。
- PM 复核（2026-10-13，独立于 worker 的第二双眼睛，均为一手复看）：`implementation-gate.ts:79` 写动词集确为 `{tee,cp,mv,rm,sed}`；`:361` `parseBashSegments` 确实未导出（仓内调用点仅 `:620`）；`runner.ts:932-950` 确为"首个 `block` 立即 return"且全文无 `timeout` 包装；`index.ts:42/49/59` 三 guard 注册位置与描述一致；`packages/multi-workers/mw.py` grep `worktree` 0 命中。以下各条为 worker 实测、PM 未复算（无 shell 复现成本高）：probe1..probe4 的 17 例判定矩阵、git rc=128 行为、`readdirSync({recursive:true})` 跟进 junction。

## 残留与未验证

（PM 补录，口径与上文 `## 未坐实 / caveat` 十三条一一对应，不改动原编号；此处只做"对 design 的影响面"归并，便于 design 与 QG 逐条核对。）

| 原编号 | 未坐实项 | 交给谁 / 对 design 的处置 |
|---|---|---|
| 1、2、11 | TOCTOU、嵌套执行绕过（`bash -c`/heredoc）、`recursive:true` 跟进仅单版本实测 | design 的"非沙箱"定位声明；绕过面写进 AC-006 的已知边界，不承诺结构性闭环（闭环靠 G2） |
| 3、4、5 | `commandPrefix`/`spawnHook` 改写、shell 家族未判定、引号态未区分 | design 需拍板"解析基准 = `event.input.command` + `ctx.cwd` + `process.env`"并在误报章节列反向对照；引号态感知列为实现期增强项 |
| 6、8 | 祖先目录是 junction 未纳入判据；注册表直接读 `.git/worktrees/*/gitdir` 未实测 | design 二选一并记录：`realpath` 前缀比对 / 直接读注册表 vs `git worktree list --porcelain` 子进程 |
| 7 | 裸名匹配规则只在 `git 2.53.0.windows.1` 实测，未查文档 | 写进 design 的"契约依赖"节：裸名歧义一律 block，不做版本推断 |
| 9 | G2 `mw worktree rm` 当前不存在（`mw.py` 0 命中，PM 已复核） | AC-002 的报错文案在 G2 落地前无法指向可执行命令 ⇒ design 必须把 G1/G2 的落地顺序写成显式依赖（T-D2 覆盖） |
| 10 | 仅覆盖 `git worktree remove`；`rm -rf`/`Remove-Item`/`rd /s` 等删除通道在范围外（RQ-1 已证 `<link>/`、`<link>/*` 会穿透 1 层） | **design 边界决策**：是否把 `rm -rf`、`Remove-Item -Recurse` 纳入 G1；D1-4 的 `plain-rm-junction` = allow 即此缺口的实测证据 |
| 12、13 | Python 侧扫描语义不在本卡范围；扫描性能与 entry 预算（20 万条）未实测 | 12 归 T-D2/T-D3；13 需在 design 的验证计划里补一条真实规模计时（AC-012 夹具可顺带覆盖） |

未覆盖面声明（本卡明确没做的）：
- 没有在生产树上跑任何删除/`git worktree` 命令，没有碰 `node_modules` 与既有 junction ⇒ RQ-1 的穿透矩阵**未在本卡重测**，直接引用。
- 没有实现任何生产代码（零改动）；D1-4 的规则原型只存在于 `%TEMP%` 且已随 fixture 删除，design 需按 D1-1 的接口草案重写。
- 没有测 WSL bash 语境（本机默认 shell 族未在 guard 内判定），也没有测 `spawnHook`/`commandPrefix` 的真实配置使用。
- 没有查 git 上游文档/变更历史（裸名匹配规则仅单版本实测）。
