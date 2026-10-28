# RQ-N2 调研报告：危险路径今天是否仍可达（必要性调研，T-N2）

- key: `mw-worktree-junction-guard` · worker: `wjg-n2-reachability` · type: research
- 采集时刻: 2026-10-13（UTC+8）
- 代码基准: HEAD `55be3d960bb8402a262fb3fcccdcc27fda3f2ed9`
- 环境（实测）: Windows `10.0.26100.0` / PowerShell `5.1.26100.9168` / `git 2.53.0.windows.1` / `node v24.19.0` / `Python 3.14.3`
- **只读合规**：真树 `H:\git\Multi-Workers` 零写入（未改任何生产文件、未在真树建/删 worktree 或 junction）；所有 fixture 在 `%TEMP%\wjg-n2-*` 且链接目标全部在 fixture 内；清理走"先逐条 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）再 `cmd /c rmdir /S /Q <root>`"，收尾删除。
- 本文件是本 worker 唯一写入物。脚本/夹具只存在于 `%TEMP%\wjg-n2-probe`、`%TEMP%\wjg-n2-rq2*`，收尾已删。

---

## 0. 结论先行

**一句话判定（"今天可达性"）：今天 agent（PM 或 worker 模式）经 bash 工具执行 `git worktree remove --force <含 reparse point 的 worktree>` 依然能得手 —— 当前 HEAD 的守卫栈里没有任何一条门拦它（唯一拦住的东西是 git 自己的参数合法性，而这与守卫无关）。**

- 阳性对照（直连 git）**仍穿透**：rc=0 / 89 ms，假真树 A 的 6 个已跟踪包文件全部消失、`@scope` 3 条 junction 清零。
- 全管线端到端实测（faux provider → agent loop → `ExtensionRunner.emitToolCall` → 真 `activate()` 的完整 guard 注册）三种模式（仅 every-mode 守卫 / 完整 PM 分支 / 完整 worker 分支）**命令均被真正执行**（`BashOperations` 记录器命中 1 次、toolResult `isError=false`）。
- worker 分支同一次运行里，同一 guard 注册下 `rm -rf <surface 外路径>` **被 `write-scope` 拦下** —— 证明 worker write-surface guard 确实处于激活态，而 `git worktree remove` 是"漏过"而非"没装门"。
- 现有写动词集不含 `git worktree remove`：`shared/implementation-gate.ts:79`（`WRITE_VERBS = {tee,cp,mv,rm,sed}`）与 `worker/worker-mode.ts:1501-1505`（`case "git"` 只认 `checkout|apply|clean|restore`）两处**均不识别**该动词（卡内事实复核成立）。
- **对 G1 的挂钩结论：G1 仍然必须做。** 若不做，事故形态今天依旧 100% 可达，且没有任何可见性（无 block、无 trace、无告警）。design §3 的 G1 不是"补漏"，而是当前唯一缺失的层。

---

## 1. 阳性对照：穿刺是否仍在（%TEMP% 夹具，直连 git）

夹具（每次重建，链接目标全在夹具内）：

```
%TEMP%\wjg-n2-rq2\<channel>\
  A\                                   git init + 1 commit
    packages\pkgA\{a1,a2}.txt  pkgB\b1.txt  pkgC\{c1,c2,c3}.txt   <- 6 个已跟踪
    .gitignore = node_modules
    node_modules\@scope\link{A,B,C} -> A\packages\pkg{A,B,C}       <- 3 条 junction
  B\                                   git -C A worktree add --detach B HEAD
    node_modules -> A\node_modules                                  <- 第 1 层 junction
```

命令与原始结果：

```
CMD> git -C <root>\A worktree remove --force <root>\B
rc=0  elapsed_ms=89
before: tracked(ls-files)=7（6 包文件 + .gitignore）  links=3  pkgs={pkgA:2,pkgB:1,pkgC:3}  B_exists=true
after : ls-files -d=6  deleted_paths=[packages/pkgA/a1.txt, packages/pkgA/a2.txt,
        packages/pkgB/b1.txt, packages/pkgC/c1.txt, packages/pkgC/c2.txt, packages/pkgC/c3.txt]
        links=0  pkgs={pkgA:0,pkgB:0,pkgC:0}  B_exists=false
```

**结论（阳性对照）**：`git worktree remove --force` 依然穿透 junction 并静默清空目标真树（rc=0、无报错）。与 RQ-D3 AC-012 的阳性对照（rc=0 / 70 ms / 5 行 `-d` / 3 条链清零）同构；本次夹具 `pkgA` 有 2 个文件，故删除面是 **6/6** 包文件（RQ-D3 是 5/6）。

---

## 2. 守卫栈可达性（逐门：输入 / 判定 / 手段）

**注册顺序与短路语义（静态，已逐行复核）**：`core/extensions/runner.ts:932-950` `emitToolCall` 按扩展注册顺序 `await` 每个 handler，**首个 `block` 立即 return**；`packages/agent/src/agent-loop.ts:620/636-640` 收到 `block` ⇒ `kind:"immediate"`（工具不执行）。`index.ts` 的注册顺序 = `protected-config`(`:42`) → `xkey-gate`(`:49`) → `implementation-gate`(`:59`) → worker-mode(`:62`)。

统一输入（所有门同一份）：`toolName="bash"`、`args.input.command = git -C <A> worktree remove --force <B>`（另有 `git worktree remove --force <B>`、`... && echo done`、`cd <A>; git worktree remove ... <B>`、`rm -rf <B>` 等形态）、`ctx.cwd = H:\git\Multi-Workers`。

| # | 门 | 落点（当前 HEAD 行号） | 判定结果（该命令） | 手段 |
|---|---|---|---|---|
| 1 | protected-config | `shared/protected-config.ts:247/249`（注册）；`checkProtectedBashCommand` `:191` | `prohibited=false`（命令不引用 `~/.pi/agent` 保护面） | **实测**：导入生产函数 + 用 fake pi 捕获 `registerProtectedConfigGuard` 真 handler 并调用 |
| 2 | xkey-gate-guard | `shared/xkey-gate-guard.ts:255` | 不适用（只拦 `.agenticdoc/_autopilot/**` 引用；命令无该字符串） | **静态推导** |
| 3 | implementation-gate | `shared/implementation-gate.ts:760`（注册）；`gateDecision` `:686`；`checkBashWriteTarget` `:612`；`WRITE_VERBS` `:79` | `blocked=false`，`basis="no-code-path-target"`，`codeTargets=[]`（`git` 不在 `WRITE_VERBS`，写目标=0） | **实测**：导入生产 `gateDecision`/`checkBashWriteTarget` + fake pi 捕获真 handler |
| 4 | pm-state-guard | `shared/pm-state-guard.ts:117/118`；注册于 `pm/pm-orchestrator.ts:1632`（仅 PM 模式） | 不适用（只拦 `write`/`edit` 对 `pm-state.md` 的改动；注释明写 "bash-based edits … are not intercepted"） | **静态推导** |
| 5 | worker read-scope guard | `worker/worker-mode.ts:2165` | 不适用（只对 read 类工具） | **静态推导** |
| 6 | worker bash write-surface（write-scope） | `worker/worker-mode.ts:2218`；config `:2202`；`extractBashWriteCandidates` `:1554`；`case "git"` `:1501` | `candidates=0` ⇒ 循环体不进入 ⇒ 放行（fail-open） | **实测**：导入生产 `extractBashWriteCandidates`/`checkBashWriteScopeTarget`；并见 §5 全管线对照 |
| 7 | mw 侧 launcher `write_scope` 检查 | `launcher.py:770`(`type_extras_missing`)/`:621`; 经 `:896`→`:1094/:1173`→`:1119/:1820` | **不是运行期门**：只在 dispatch 期校验产出的 task.md 是否声明了写入允许面，绝不拦截任何 bash 命令 | **静态推导**（见 §4） |

**`git` 动词提取（原始输出，实测）**：

```
$ node probe-guards.mjs
{"command":"git -C ...\\A worktree remove --force ...\\B","implGate":{"blocked":false,"basis":"no-code-path-target","codeTargets":[]},"protectedConfig":{"prohibited":false},"workerWriteScope":{"candidates":0,"scopeVerdicts":[]}}
{"command":"git worktree remove --force ...\\B",          "implGate":{"blocked":false,"basis":"no-code-path-target"},"protectedConfig":{"prohibited":false},"workerWriteScope":{"candidates":0}}
{"command":"rm -rf ...\\B",                               "implGate":{"blocked":false,...},"protectedConfig":{"prohibited":false},"workerWriteScope":{"candidates":1,"scopeVerdicts":[{"pattern":"rm","verbatim":true,"rule":"scope"}]}}
{"command":"Remove-Item -Recurse -Force ...\\B",          "implGate":{"blocked":false,...},"protectedConfig":{"prohibited":false},"workerWriteScope":{"candidates":0}}
{"command":"cmd /c rmdir /S /Q ...\\B",                   "implGate":{"blocked":false,...},"protectedConfig":{"prohibited":false},"workerWriteScope":{"candidates":0}}
```

**逐 handler 实测（fake pi，PM 与 worker-env 两种 env；原始输出节选）**：

```
{"workerEnv":false,"command":"git -C \"...\\A\" worktree remove --force \"...\\B\"","verdicts":[{"handler":0,"block":false},{"handler":1,"block":false}],"finalBlocked":false}
... 同上（git worktree remove --force / && echo / cd A; git ... / rm -rf）全部 finalBlocked:false
{"workerEnv":true, ... 同样 5 个形态全部 finalBlocked:false}
```

（`handler:0` = protected-config，`handler:1` = implementation-gate；worker-env 只让 implementation-gate 走 `basis=worker-env` 分支，对本命令无差别，因为本命令根本不在其写目标集内。）

---

## 3. 其它删除通道的现状（RQ-1 结论今天是否仍成立）

同一夹具，每个通道独立重建。判据 = 假真树 A 侧：`git ls-files -d` 计数 / `@scope` 链数 / `pkgX` 文件数。

### 3.1 删除整个 worktree（父目录形态）

| 命令原文 | rc | ms | A 侧 deleted | A 链数 | A 包文件 | 穿透 |
|---|---|---|---|---|---|---|
| `git -C A worktree remove --force B` | 0 | 89 | **6** | 3→**0** | 6→**0** | **是** |
| `rm -rf B`（git-bash `rm.exe`） | 0 | 59 | 0 | 3→3 | 6→6 | 否 |
| `rm -rf B/`（尾斜杠） | 0 | 38 | 0 | 3→3 | 6→6 | 否 |
| `Remove-Item -Recurse -Force B` | 0 | 677 | 0 | 3→3 | 6→6 | 否 |
| `cmd /c rmdir /S /Q B` | 0 | 24 | 0 | 3→3 | 6→6 | 否 |

### 3.2 链接本身的显式分隔符/通配形态（RQ-1 的"穿透一层"形态）

| 命令原文（`L` = `B\node_modules`） | rc | ms | A `@scope` 链 | A `packages\pkg*` | B 侧链接 | 穿透 |
|---|---|---|---|---|---|---|
| `rm -rf L/` | 0 | 31 | 3→**0** | 6→6 完好 | 仍在 | **是（1 层）** |
| `rm -rf L/*` | 0 | 336 | 3→**0** | 6→6 完好 | 仍在 | **是（1 层）** |
| `Remove-Item -Recurse -Force L\*` | 0 | 223 | 3→**0** | 6→6 完好 | 仍在 | **是（1 层）** |
| `cmd /c rmdir /S /Q L\`（尾反斜杠） | 0 | 17 | 3→**0** | 6→6 完好 | 已删 | **是（1 层）** |

**结论（RQ-1 今天仍成立）**：
1. 只有 `git worktree remove` 自动穿透（任意深度）；`rm -rf` / `Remove-Item -Recurse` / `rmdir /S /Q` 的**递归枚举型**形态对 junction 只删链接条目、不进入目标。
2. 链接路径上的显式分隔符/通配（`<link>/`、`<link>/*`、`<link>\`、`<link>\*`）仍穿透**一层**：目标目录 `A\node_modules` 本身保留，但其内容 `@scope`（含 3 条 junction）被清空；第二层（`@scope\linkX -> A\packages\pkgX`）因逐条目 reparse 检测而**未**被穿透，`pkgX` 的 6 个文件完好。
3. **D-4 的边界判断（design §3.5）今天仍然成立且必要**：覆盖 `git worktree remove|rm` + 同一目标树上的 `<path>/`、`<path>/*` 两类形态即可；无尾分隔符/无通配的普通 `rm -rf <link>`、`rmdir /S` 继续穿透的说法**不成立**（不穿透），扩大动词集只会引入误拦。

---

## 4. mw 侧 launcher 的 `write_scope` 检查到底是什么

- `packages/multi-workers/launcher.py:770 type_extras_missing` / `:621` 的正则 `写入允许面|…|write_scope|allow[-_ ]?write`，被 `:896 _envelope_missing_items` 调用，最终经 `:1094 classify_envelope_refusal` / `:1173 _envelope_refusal` 在 **dispatch 期** 拒绝**没有声明写入面的 task.md**（`:1119`、`:1820`）。
- `packages/multi-workers/autopilot/conductor.py:6504-6525` 的 `write_scope` 只用于 xkey 提案的 `blast_radius ⊆ write_scope` 事实校验。
- 运行期真正拦 bash 写面的是 **TS 侧** `worker/worker-mode.ts:2218`（见 §2 #6），不是 Python。
- **实证**：`packages/multi-workers/mw.py` 里 grep `worktree` 仅命中 `:5335`/`:5360` 两处"linked worktree 的 git 文件解析"注释，**没有 `mw worktree` 子命令**（`add_parser` 共 11 个，无 worktree）；Python 侧 `worktree|isjunction|reparse` 全域无运行期守卫。⇒ design §7 第 3 条（G2 命令此刻不存在）今天仍未变，G1 的 block 文案仍**指不到可执行命令**。

---

## 5. 全管线端到端实测（faux provider → agent loop → ExtensionRunner → 真 `activate()`）

范式照 `test/suite/xkey-gate-guard-coverage.test.ts`：`createHarness({ tools:[createBashTool(cwd,{operations: recorder})], extensionFactories:[…] })`，用 `fauxAssistantMessage([fauxToolCall("bash",{command})], {stopReason:"toolUse"})` 驱动。脚本在 `%TEMP%`，以明文 node 直接 import 生产模块运行。

```
{"label":"S1-pm-mode-every-mode-guards","executed":1,"toolResultIsError":[false],"promptError":null}
{"label":"S2-full-activate-pm",          "executed":1,"toolResultIsError":[false],"promptError":null}
{"label":"S3-full-activate-worker",      "executed":1,"toolResultIsError":[false],"promptError":null}
toolResultText = "ran: git -C ...\A worktree remove --force ...\B"   # BashOperations 记录器确实被调用
```

S3 的 worker 分支（`PI_WORKER_TASK` = `%TEMP%` 内 `type: research` 的 task.md，故 `isShellRole && isWritelessRole` 成立、write-scope guard 已注册）同一状态下的**对照命令**：

```
CMD1> git -C <root>\A worktree remove --force <root>\B     -> 执行（isError=false，被 recorder 记录）
CMD2> rm -rf <root>\outside_target                          -> 被拦：
  "write-scope: blocked bash write to C:UsersWENBOZ~1AppDataLocalTempwjg-n2-rq2-workerctloutside_target:
   outside the worker write surface [rule=scope]; allowed: ...\taskdir or <key>/evidence"
EXECUTED=["git -C ...\\A worktree remove --force ...\\B"]   # CMD2 未执行
```

**这直接证明**：worker write-surface guard 处于激活态；它拦得住 `rm -rf`，但**拦不住 `git worktree remove`** —— 因为 `worker-mode.ts:1501` 的 `case "git"` 只枚举 `checkout|apply|clean|restore`。

**附带发现的守卫缺口（供 G1 边界参考）**：PowerShell cmdlet 与 `cmd /c rmdir` 的目标提取同样不可靠 ——
`extractBashWriteCandidates` 实测：

```
"Remove-Item -Path C:\temp\x"                    -> candidates=1 (pattern="remove-item -Path", rule=scope)
"Remove-Item -Recurse -Force -Path C:\temp\x"    -> candidates=1 (同上)
"Remove-Item -Recurse -Force C:\temp\x"          -> candidates=0   # 位置操作数不被捕获
"cmd /c rmdir /S /Q C:\temp\x"                   -> candidates=0
"git worktree remove --force C:\temp\x"          -> candidates=0
```

即现有 tokenizer 只认 `-Path/-LiteralPath/-FilePath/-Destination` 显式 flag。若 D-4 第 2 点要求覆盖 `Remove-Item -Recurse -Force <path>\*`，G1 不能依赖现有 `extractBashWriteCandidates`，必须自带词法。

---

## 6. 残留与未验证

1. **`%TEMP%` 路径拼写差异**：夹具用 `C:\Users\WENBOZ~1\AppData\Local\Temp\…`（短名）。守卫判定与路径短名/长名无关（本次命令根本未进入任何路径扫描分支），但 G1 的 reparse-point 扫描实现必须按 design §4.2 的 `normcase+normpath` 处理短名——本卡未验证扫描器。
2. **"agent 是否能拿到 `bash` 工具"未验**：本次只验"拿到后被不被拦"。worker 角色中 `research` 有 `bash`（`isShellRole=true`）；coding 角色同理。工具白名单本身不阻止该命令。
3. **`mw worktree rm` 不存在** ⇒ 若现在落 G1，block 文案指向的命令不可执行（design §2 硬依赖、§7 第 3 条）。本卡未实现 G2，未验。
4. **`Remove-Item`/`cmd rmdir` 的守卫缺口**（§5 末）只做了候选提取实测，未跑全管线；对 G1 无阻塞。
5. **block reason 的 target 文本被词法器吃掉反斜杠**（`C:UsersWENBOZ~1AppData…`）：本次实测在 write-scope 的拒绝文本里可见。不影响判定（仍算出 surface 外），但若 G1 要在 reason 里回显路径，需自行保留原 token。
6. **未验**：`bash -c "<payload>"`、heredoc、`commandPrefix`/`spawnHook` 等改写面（design §7 已列为已知绕过面）；非 Windows 平台 / WSL / PowerShell 7。

---

## 7. 未覆盖面声明

- 本卡**未写任何生产代码**，未新增/修改测试，未碰 G1/G2/G3/G4 的任何落点文件。
- 本卡**未在真树**做任何 before/after 清单、未建删真树 junction/worktree、未跑 `checkout`/`reset`/`clean`/`rm`；真树 `git status` 里的其它改动均非本 worker 所为。
- 所有 fixture 在 `%TEMP%\wjg-n2-rq2*` 且链接目标全部在夹具内，收尾已按"先 `rmdir` 摘链、再 `rmdir /S /Q`"清理并删除 `%TEMP%\wjg-n2-probe`。
- 未覆盖：G2/G3/G4 范围；`--link-deps` 建链产物（`npm ci` 自指链）；注册表竞态；非 junction 的 reparse tag。

## 上下文来源

（PM 补录：worker 交付内容完整，但缺本节规范标题；清单取自本文件各节实际引用的 `文件:行号` 与夹具，不改动任何上文原文。）

| 文件 | 行 | 用途 |
|---|---|---|
| `packages/coding-agent/src/core/extensions/runner.ts` | `:932-950` | 多 handler 顺序 `await`、首个 `block` 立即 return（判定"有没有门能拦"的基础） |
| `packages/agent/src/agent-loop.ts` | `:617-645`、`:657-661` | `block` ⇒ `kind:"immediate"`（工具不执行）；异常同一出口 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts` | `:24-27`、`:79`、`:539-637`、`:686-730`、`:760-775` | 写动词集只含 `tee/cp/mv/rm/sed`；`gateDecision` 对本命令 `blocked=false / basis=no-code-path-target` |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts` | 全文判定路径 | `prohibited=false` 的实测依据 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | `:1044`、`:1501`、write-scope 判定段 | `POWERSHELL_PATH_FLAGS = {-path,-literalpath,-filepath,-destination}`；`case "git"` 只认 `checkout/apply/clean/restore` ⇒ `git worktree remove` 不是写候选（`candidates=0`） |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts` | 全文 | 只作用于读工具，与删除无关 |
| `.agents/skills/agentic-task/scripts/guard_pm_state.py` | 全文 | pm-state guard 只拦 `write/edit` 改 `pm-state.md` |
| `packages/multi-workers/launcher.py` | `write_scope` 校验段、`_poll_once` | launcher 的 `write_scope` 是 **dispatch 期**卡片校验、非运行期门 |
| `packages/multi-workers/mw.py` | grep `worktree` = 0 命中 | 无 `mw worktree` 子命令（G2 未实现） |
| `packages/coding-agent/test/suite/harness.ts` / `test/suite/xkey-gate-guard-coverage.test.ts` | `harness.ts` 全文、`xkey…:121-131` | 全管线端到端实测的范式（faux provider → agent loop → `ExtensionRunner` → 真 `activate()`；`BashOperations` recorder 证明命令是否真被执行） |
| 本 key 前序证据 | — | `evidence/research/design-guard-path-resolution-20261013.md`（RQ-D1 的 R-a..R-d 与写动词结论）、`design-observability-and-verification-20261013.md`（AC-012 阳性/阴性对照）、`spec-junction-semantics-20261009.md`（穿透矩阵） |
| `%TEMP%\wjg-n2-*\**` | — | 本卡全部夹具（假真树 A + worktree B + `@scope` 三条 junction + 链接级形态），链接目标全在夹具内，收尾已删除 |

PM 复核（2026-10-13，一手复看）：`worker-mode.ts:1501` 的 `case "git"` 确实只认 `checkout|apply|clean|restore`（`git worktree remove` 落不进去）；`worker-mode.ts:1044` 的 `POWERSHELL_PATH_FLAGS` 确实是 `-path/-literalpath/-filepath/-destination`（解释"`Remove-Item -Recurse -Force <x>` 提取 0 候选"）；HEAD 确为 `55be3d960`（注意本 key 的 `design.md` 初稿写的是 `cc9a46a1a`，其它会话在此期间有提交）；证据文件 16,267 B / 185 行、sha256 前 16 = `DA887B9298587735`。以下为 worker 实测、PM 未复算：全管线三种模式（every/PM/worker）的 recorder 结果、`rm -rf <surface 外>` 被 write-scope 拦下的同轮对照、四个删除通道与四个链接级形态的 rc 与穿透结果、阳性对照的 89 ms 与 `ls-files -d`=6。
