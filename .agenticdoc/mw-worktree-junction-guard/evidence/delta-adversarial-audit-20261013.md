# T-W15 Δ 对抗性审计 — 证伪 G6 三 AC 与部署宣告（mw-worktree-junction-guard）

- 任务卡：`tasks/T-W15-delta-adversarial-audit-a.md`（card_sha256: 7ff704b90cb63b10a36191764a7868031e54f8b3b7285cd537ba000326efb114）
- 日期：2026-10-14
- 类型：review（对抗性证伪）
- 方法（与前两次审计正交）：QG=引用闭包、W-12=负空间/危害面清单；**本卡 = 攻击者视角，目标是推翻结论**。默认「实现与证据链都可能是错的/可绕过的」，每条结论给最强反例或最强攻击尝试；「没找到反例」一律写「本次尝试未找到」，不写「不存在」。
- **工具边界（先声明，影响下文所有「实测」字样）**：本 worker 会话的工具面为 read / grep / find / ls / worker_file，**没有 shell**。卡片的验收命令（`vitest --run`、`python -m pytest`、`mw doctor`、`git grep --untracked`、`node -e`）全部无法执行。因此：① 未跑任何既有测试（不是副作用判断，是能力缺失）；② 所有「拦/放」结论均为**静态代码路径推演**（引用 lexer/判定函数行号）+ 既有测试断言的复读，未做执行型反例；③ 字节数与部分计数无法用工具复算（见未覆盖面声明）。下文「复算」均指只读 grep/read 复算。
- 引用坐标以**符号 + 当前行号**为准；卡片给的行号已有漂移（`:78 decideWorktreeRemove` → 实为 `:92`；`:291 decideDeletePenetration` → `:332`；`:453 expandToken` → `:609`；`:506 parseDeleteInvocation` → `:549`；`:539 notRemove` → `:695`；`:544 reparsePointVerdict` → `:700`；`:202 tool_call` / `:217 user_bash` 未漂）。
- 攻击尝试计数口径：下文编号向量合计 **43 条**（A 系 18 + B 系 12 + C 系 9 + D 系 4），逐条见各节。

## 结论

### 1. AC-014（user_bash 通道）：站稳（枚举面全拦、零副作用、无误拦、通道对等成立），附 6 条新发现判定面逃逸（同伤 tool_call 面；其中 1 条落在 AC-014 并入的 D-11 动词面上，构成该面的裂缝）

**1a. 最想被证伪的一条 —「返回 `{result}` 是否真的让命令体不被 spawn」：未被证伪。** 三层独立核验（全部只读）：

- 派发侧 `core/extensions/runner.ts:955-978`：`emitUserBash` 对每个已注册 handler `await handler(event, ctx)`，`if (handlerResult) return handlerResult`（首个真值整体返回），异常被 catch 后 `emitError` 并**继续循环**（→ 攻击 A16：handler 抛异常 = fail-open，命令照跑；`decideWorktreeRemove` 内部的 fs/spawn 错误均被自身 try/catch 折叠成 fail-closed verdict，静态找不到会抛到 runner 的路径）。
- 消费侧两条出口**都只认 `eventResult?.result`**，且短路于「Normal execution path」之前：
  - TUI：`modes/interactive/interactive-mode.ts:6277-6314` —— `if (eventResult?.result) { …recordBashResult…; return; }`，`return` 在 `:6326 session.executeBash` 之前；
  - RPC：`modes/rpc/rpc-mode.ts:561-573` —— `if (eventResult?.result) { session.recordBashResult(…); return success(id, "bash", eventResult.result); }`，其后才是 `:575 session.executeBash`。
  - spawn 只发生在 `executeBash → executeBashWithOperations → operations.exec`（`core/bash-executor.ts:108`）——短路路径不经过它。
- **运行时产物**（不是源码自证）：mw setup 把全局 pi 钉为本仓 npm link（`mw.py:5153-5161`），bin → `dist/cli.js`（`packages/coding-agent/package.json:9-11`）。我直接读了运行时会执行的 dist 消费者代码：`node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/interactive-mode.js:5289-5317` 与 `packages/coding-agent/dist/modes/interactive/interactive-mode.js` **同行号同内容**，均为 `if (eventResult?.result) { … return; } // Normal execution path`。

**反向陷阱确认存在（卡片问「tool_call 的 `{block:true}` 用在 user_bash 上会怎样」）：会被静默忽略且命令照跑。** `{block:true, reason}` 是真值 → `emitUserBash` 原样返回 → 消费者取 `eventResult?.result` = undefined → 落入正常执行路径，`reason` 无人消费。即：若有人把 tool_call 形状复制到 user_bash 挂钩上，拦截会**无声失效**。当前实现用的是 `{result:{output, exitCode:1, …}}`（`worktree-junction-guard.ts:217-232`），正确；但这个陷阱没有任何类型层防线（`ExtensionHandler<UserBashEvent, UserBashEventResult>` 允许返回任意真值），只靠实现者知道区别 —— 值得一条注释级防线或后续测试。

**1b. 覆盖缺口逐条「拦/放」（静态推演；标注哪些必须拦否则 INV-1 在该通道不成立）：**

拦（已测形态标注测试坐标）：

| # | 形态 | 结论 | 依据 |
|---|---|---|---|
| A3 | `--force`/`-f` 任意摆位（动作前后）、`--force=true` | 拦 | `collectOperands`（`:529-541`）跳过一切 `-` 开头词，与位置无关 |
| A4 | 多目标 `git worktree rm a b`、零目标、`--` 后混旗标 | 拦（fail-closed `bare-name-ambiguous`） | `decideWorktreeRemove` 操作数 ≠1 即拒（`:118-128`）；**必须拦**（多目标删除面无法定死） |
| A5 | `-C <dir>`/`-C<dir>`、`-c k=v`、`--git-dir X`/`--git-dir=X`、`--work-tree`、`--namespace`、`--exec-path`、未知全局旗标、`GIT_DIR=x git …` 前置赋值 | 拦 | `parseGitInvocation`（`:449-487`）：`GIT_GLOBAL_VALUE_OPTIONS` 吃双词、其余 `-` 词跳过、leadingAssignments 吸收前置赋值；操作数按字面/解析值扫描，与 git 自身解析一致 |
| A6 | `cd <dir>;`、`cd <dir> &&`、`Set-Location [-Path] <dir>;`、`cd $UNSET;` | 拦（$UNSET → `unresolved` fail-closed） | `readLocationTarget`（`:517-525`）+ `effectiveCwd`/`cwdMissing` 跟踪（`:99-116`）；已测（decide.test `:236`/`:248`）；**必须拦** |
| A7 | `;`、`&&`、`\|\|`、`\|`、`&`、子壳 `( … )`、PS `&` 调用操作符分隔 | 拦（逐段判定） | `parseBashSegments` 对每个分隔符 `endSegment`（bash-segments.ts）；`(`/`)` 拆段使子壳内的 git 调用自成一段 |
| A9 | 插值 `$env:X`/`${X}`/`%X%`/`$X`、命令内赋值 `$t = "…"; git worktree remove --force $t` | 拦 | `expandToken`（`:609-668`）四语法全覆盖、未知变量 fail-closed；已测（decide.test `:143-210`）；**必须拦**（事故命令本体就是 `$env:` 插值） |
| A13 | 操作数含 glob/尾分隔符/命令替换（引号内外）、未加引号的 `$( )` | 拦（`glob` verdict） | `hasGlobOrSubstitution`/`hasTrailingSeparator`（`:670-676`）；未引号 `$(…)` 被 `(` 拆段后残余 `"$("` 落进操作数同样触发；已测（decide.test `:212-226`）；**必须拦**（`<link>/`、`<link>/*` 是穿透形态） |
| A14 | 裸名 `git worktree remove qg-head` | 拦（唯一匹配→扫描；歧义→拦；注册表不可读→拦；零匹配→放，git 自身 rc=128 无害） | `decideBareName`（`:376-397`）；已测（decide.test `:268-295`） |
| A15 | 干净命令族（`git status`/`ls`/`npm run check`/`mw worktree rm "<wt>"`/`cmd /c rmdir "<link>"`）、heredoc 体、行首注释 | 放（不误拦） | heredoc 体整段跳过、注释词使头词非 git、处方命令头词非 git/rm；已测（decide.test `:306`/`:390`/`:406-440`、coverage AC-003/处方用例） |
| — | 字面路径（含空格引号）、`git.exe`/全路径 git、`~/` 波浪号、`-- wt` | 拦/正确放行 | lexer 剥引号、`basenameLower` 剥 `.exe`、`expandTilde`、`--` 处理 |

放（新发现逃逸；**全部同伤 tool_call 面**——两挂钩共用 `decideWorktreeRemove`，故「通道对等」未破，但 INV-1「没有任何执行通道」的绝对措辞在 `!`/RPC 通道上经这些形态仍可证伪；已声明边界形态单列在后）：

| # | 逃逸形态 | 机理（file:line） | 判级 |
|---|---|---|---|
| A8 | **`\<LF>` 续行拼接**：`git worktree remove --force wt-\<换行>head` → 守卫放行，真实 shell 执行 `wt-head` | `bash-segments.ts:120-135`：`\`+LF 两个字符**都被保留进词内**（`BACKSLASH_ESCAPES_UNQUOTED` 含 `"\n"`，双引号内同），POSIX 语义是两字符一起删除；操作数变成 `wt-\nhead` → 无分隔符 → 裸名 → 注册表 basename 匹配必然落空 → `target-absent` 放行 | 刻意混淆级；**必须拦**（否则 INV-1 该形态不成立） |
| A9′ | **头部/子命令/动作位变量插值**：`G=git; $G worktree remove wt`、`git $W remove wt`、`git worktree $A wt` → 放行 | 变量展开只作用于操作数与位置目标（`expandToken` 调用点），`words[0]`/subcommand/action 从不展开（`parseGitInvocation:449-487` 直接字符串比较） | 刻意混淆级；**必须拦**（同上） |
| A10 | **前缀包装/嵌套解释器**：`env git worktree remove wt`、`nohup git …`、`timeout 10 git …`、`bash -c "git worktree remove wt"`、`cmd /c "git worktree remove wt"`、`iex "…"` → 放行 | 段首词不是 `git`（`bash -c` 的命令体是**一个含空格的单词**，不会被二次解析） | `cmd /c`/`bash -c` 是常见习惯用法，最可信的非刻意逃逸；**必须拦** |
| A6′ | **基准漂移**：`pushd <dir>; git worktree remove wt`、PS `sl <dir>;`（Set-Location 别名）、`chdir`、cmd `cd /d <dir>;`（`readLocationTarget` 只跳 `-` 开头词，把 `/d` 当成了目标）→ 操作数按原 cwd 解析 → `target-absent` 放行，真实删除发生在 `<dir>` 下 | `readLocationTarget:517-525` 只认 `cd`/`set-location` 头词、只跳 `-` 前缀 | `cd /d` 是 cmd.exe 标准写法；**必须拦**（相对操作数形态） |
| A11 | **PowerShell 默认别名动词面**：`ri -r -fo <wt>\node_modules\`、`rd`/`del`/`erase` 同类穿透形态 → 放行（对照：`rm -r -fo …` 因 PS 里 `rm` 也是 Remove-Item 别名而**命中** `parseDeleteInvocation`） | `parseDeleteInvocation:549-554` 头词白名单只有 `rm`/`remove-item` | **落在 D-11 声称覆盖的动词面内**（AC-014 明文并入「D-4/D-11 的动词面」），且 mw 把 pi shellPath 钉在 PowerShell（`mw_common.py:1434 ensure_pi_shell_path`）——`!` 命令实际就在 PS 里跑，别名形态与 `Remove-Item` 同能力。这是本卡对 AC-014 并入面找到的最强反例；**必须拦** |
| A12 | PS 反引号转义：`` git wo``rktree remove wt `` → PS 见 `worktree`，lexer 把反引号留在词内 → 子命令不匹配 → 放行；（`--%` 停止解析符反而被当旗标跳过 → 命中，`Remove/RM` 大写动作不匹配但 git 自身大小写敏感会拒 → 无害） | lexer 无反引号语义（bash-segments.ts 反引号是普通字符） | 刻意混淆级 |

已声明的边界放行（非新发现，文件头 + D-4 rule 3 + decide.test `:306`/`:390` 反向对照已固化）：`rm -rf <link>`（无尾分隔/无通配）、`rmdir /S`、`robocopy /MIR`。这些对 INV-1 绝对措辞同样是洞，但属 spec/design 已接受的边界，不计入本卡反例。

**1c. 零副作用与误拦（AC-014 反向对照）**：拦截路径只做只读扫描 + `git worktree list --porcelain` spawnSync（仅裸名/穿透命中时）；非拦截返回 `undefined` 不触碰执行路径。测试断言的是**执行后端记录** `executed === []`（coverage.test `runUserBash` 的 `BashOperations` 记录器），不是只断言返回值；反向对照 `executed === [command]` 证明后端真的会跑（非空转阴性对照）。误拦面找到两条边缘：① 换行是空白不是段分隔（bash-segments.ts `:157-163` 只 `flushWord`），多行粘贴会把 `git worktree` + `remove wt` 合并成一次调用判定 —— 只会**过度**阻断（fail-closed 方向，且真实 shell 下该形态本就不会删除）；② 若用户配置了 `shellCommandPrefix`（`agent-session.ts:2779` 在执行时拼 `prefix\ncommand`，守卫看到的是原始 command），前缀含 `cd` 类语句时真实基准与守卫基准可漂移 —— 默认空配置，边缘。`event.cwd` 与 bash 工具 cwd **同源**：两者都取 `sessionManager.getCwd()`（`interactive-mode.ts:6277` ↔ `agent-session.ts:2788`，RPC 同），无语义差。

### 2. AC-015（registry_error 可见）：有裂缝（窄）

全链路静态核验成立：`worktree_registry.read_registry`（`worktree_registry.py:83-97`）对坏文件一律 `raise WorktreeRegistryError` → `worktree_doctor._registry_domain`（`:138-165`）捕获并把 `str(exc)` 放进第五返回位 → `build_section` 顶层镜像 `registry_error`（`:309`）→ `_doctor_issues` 消费为 issue（`mw_common.py:3878-3884`，含错误摘要 + 注册表路径）→ `format_doctor_text` 在 `registry_error` 非空时**无视 `count==0`** 打印 `worktree_links: REGISTRY-ERROR <path>: <error>`（`:4178-4182`）→ `mw.cmd_doctor` `return 0 if report["summary"]["healthy"] else 1`（`mw.py:637`）→ issue 必翻 rc。损坏时 `_registry_domain` 返回空 entries，域 (c) 的 D-12 过滤失去 registered-alive 集 → 扫描根链全报 leftover —— fail-closed 方向放大可见性，正确。

逐形态结论（静态推演，依据 `read_registry:83-97` + `_validate_entry:69-80`）：

| 坏文件形态 | 结果 |
|---|---|
| 文件不存在 | `[]` 静默（by design，健康态） |
| 空文件 / 纯空白 | `json.loads` ValueError → 抛 → issue + 行 + rc1 |
| JSON 合法但顶层是数组 | `isinstance(data, dict)` 不成立 → 抛 → issue + 行 + rc1 |
| 合法 dict 缺 `entries` / `entries` 非 list | 抛 → issue + 行 + rc1 |
| entry 非对象 / 缺必填字段 | `_validate_entry` 抛 → issue + 行 + rc1 |
| 权限不可读（ACL） | `read_text` OSError → 抛 → issue + 行 + rc1 |
| 路径是目录 | `exists()` True → `read_text` IsADirectoryError → 抛 → issue + 行 + rc1 |
| 符号链接指向目录 | `exists()` True（跟随）→ `read_text` IsADirectoryError → 抛 → issue + 行 + rc1 |
| **符号链接悬空（目标已删）** | **`path.exists()` 跟随链接 → False → 按「不存在」返回 `[]` → 静默、零行、rc 不变** ← 本卡找到的唯一静默坏形态 |
| `{"entries": []}` 缺 `version` 键 | 静默接受为健康（报错文案写「expected {'version','entries'}」但代码只检查 `entries`）—— entries 仍被如实消费，非静默空表；属文案-代码偏差，次要 |
| BOM 前缀的有效 JSON | ValueError → 抛（fail-closed 误伤方向，安全） |
| exists→read TOCTOU 竞态 | `read_text` FileNotFoundError → 抛 → fail-closed |

**裂缝**：悬空符号链接形态（`.mw/worktree-registry.json` 是指向已删目标的 symlink）会让「坏文件」被读成「无文件」。触发条件窄（Windows 建符号链接需开发者模式/管理员；mw 自身不会把注册表写成 symlink），但按卡片判据（「找出任何一种坏文件形态仍然静默即为未达成」）成立。修法一行：`read_registry` 里 `exists()` 改 `os.path.lexists()`（悬空 symlink → lexists True → read_text FileNotFoundError → 抛 → 可见），或对「lexists 但 exists 为 False」显式抛错。次级偏差（缺 `version` 被接受）建议对齐文案或补检查。

### 3. AC-016（激活自检）：站稳（声明的判据面内），附 3 条「字符串在 ≠ 能力在」解耦通道（未来回归空间；当前树均不存在，已逐条独立核验）

**假绿攻击（更重要的一侧）**：

| # | 攻击 | 结果 |
|---|---|---|
| C1 | `has_marker=None`（不可读/缺文件）被当 OK | **拦**。`_doctor_issues:3895-3898` 与 `format_doctor_text:4187-4190` 都以 `is not True` 为门——None 落入 issue（`unverifiable (…)` / `UNVERIFIABLE`），`_activation_scan:2806` `if entry["has_marker"] is not True: missing.append`。测试 `test_scan_unreadable_does_not_raise` / `test_scan_invalid_encoding_does_not_raise` / `test_scan_missing_file_is_a_finding` 断言 None ≠ OK |
| C2 | 目录冒充 bundle | 拦（`lexists` True → `read_text` IsADirectoryError → error → issue） |
| C3 | 非法 UTF-8 | 拦（UnicodeError → error → issue） |
| C4 | 标记是字符串字面量、与能力解耦 | **部分成立（本次找到解耦路径，当前树不存在）**。标记唯一性今日成立：扩展源内 `reparse-point` 仅 2 处（`worktree-junction-guard.ts:65` 注释——esbuild 会剥、`:707` `basis` 字面量），我复读两份部署 bundle 均恰 1 处（`:28832`）。但标记证明的是「reparsePointVerdict 的字面量进了 bundle」，对以下三种回归不可见：① **注册断线**——`index.ts` 不再调用 `registerWorktreeJunctionGuard` 但模块仍被其它引用保留在 bundle 里（若 import 完全删除，tree-shaking 会带走标记 → 红 → 能抓到；若调用被挪进死分支/被注释而引用仍在 → 绿 → 抓不到）；② **AC-014 挂钩缺失**——删掉 `pi.on("user_bash")` 而 tool_call 面保留：标记仍绿、doctor 照报「能力已激活」，`!`/RPC 通道裸奔（doctor 只查 `reparse-point`，从不查 `"user_bash"`）；③ **判定逻辑阉割**——`scanTree` 的 `isSymbolicLink` 改恒假：绿但全盲。①③ 是任何字符串代理判据的固有极限；② 是**可行动缺口**：建议给 `_activation_scan` 加第二个标记 `"user_bash"`（源内恰 2 处、bundle 内恰 2 处，已验证可数），让 AC-016 覆盖到 G6 自己的挂钩 |
| C5 | 标记出现在未调用分支 | 本次尝试未找到当前树的实例（标记唯一载体就是 `reparsePointVerdict` 的 return，见 C4） |

**假红攻击**：

| # | 攻击 | 结果 |
|---|---|---|
| C8 | 非本仓项目误报 | 拦：`_activation_bundle_paths:2766-2767` 以 `<project>/packages/coding-agent/src/extensions/agent-team-loop` 存在为门，外部项目 `applicable: False` 全静默（`test_scope_gate_skips_projects_without_the_extension_source`） |
| C9 | 第二个本仓克隆误报 | 部分成立但语义合理：dist 副本随 git 走（tracked），全局 bundle 是机器本地的——新机器/新克隆未 `mw build --install` 时报红是**真实**未部署。真正的文案问题：dist 副本的 issue 文本说「the reparse-point removal guard is not active in the runtime pi loads」，但 pi 从不直接加载 dist（它是 `--install` 的载具/暂存产物；pi 只从 agentDir/extensions 与 cwd/.pi/extensions 发现扩展，见 D2）。建议文案区分两份副本的角色 |
| C10 | `PI_CODING_AGENT_DIR` 自定义目录漂移 | 本次尝试未找到实际漂移路径：doctor（`mw_common.global_ext_dir:2327-2332`）与 pi（`config.ts:531-537`）读同一个 env、同一优先级；mw 全链路（launcher/serve/worker 环境）不设该变量（grep 无 setter）→ 双侧同源。理论边缘：用户只在某一个 shell 导出该变量时 doctor 与运行时可指向不同目录 |
| C11 | 冻结 doctor 测试被污染 | 拦：夹具项目无扩展源目录 → `applicable: False`（设计意图即此，`mw_common.py:2748-2753` 注释明说） |

### 4. 部署宣告：站稳（内容级独立核验通过；字节级沿用 PM 实测数，本会话无法复算——已声明）

- **D1 bundle 内容**：两份部署产物 `packages/multi-workers/dist/extensions/agent-team-loop.js` 与 `C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js` 我都以 grep 复算：`pi.on("user_bash"` 在 **`:28486`**、`recordWorktreeGuardBlockTrace("user_bash"` 在 **`:28491`**、`basis: "reparse-point"` 在 **`:28832`**——两份文件**同行号同内容**（`"user_bash"`=2 行、`reparse-point`=1 行，与 PM 计数一致）。两份 bundle 均为非压缩 esbuild 输出，同行号命中强烈佐证字节一致；1,136,103 B 与 `worktree`=25 无法用本会话工具复算（无 stat/wc），接受 PM 实测值并如实标注。
- **D2 加载路径链**：pi 的扩展发现 = 全局 `<agentDir>/extensions`（`package-manager.ts:2365-2368`，`agentDir = getAgentDir()`）+ 项目 `<cwd>/.pi/extensions`（需 projectTrusted，`:2395-2403`）+ settings.json `extensions` 显式路径。`getAgentDir()` = `PI_CODING_AGENT_DIR` else `~/.pi/agent`（`config.ts:531-537`）。mw 启动 worker 用 PATH 上的 `pi`（`launcher.py:1385-1388`），全链路不设 `PI_CODING_AGENT_DIR` → 运行时 agentDir 就是 `~/.pi/agent` → **全局那份就是 pi 会加载的那份**，与 doctor `global_ext_dir()` 同源。
- **D3 第三位置探查**：仓内 `.pi/extensions/` 实测只有 `import-repro.ts`/`prompt-url-widget.ts`/`redraws.ts`/`tps.ts`——**无 agent-team-loop 副本**（无遮挡/陈旧双载）；全局 `~/.pi/agent/extensions/` 实测 5 个文件（agent-team-loop.js + agentic-status.ts + agentictask-update.ts + goal.ts + `.mw-py-path`）；全局 settings.json grep `extensions|skills|prompts` **零命中** → 无 settings 配置的第三路径。未发现第三个加载位。备注：若扩展从全局+项目两处同时载入，双注册只重复判定不互相削弱（`emitUserBash` 遍历全部 handler，undefined 不中止循环，真值才中止——旧副本的真值返回只会是拦截本身）。
- **D4 运行时身份**：mw setup 步骤 4 断言全局 pi = 本仓 npm link（`mw.py:5153-5161`），bin → `dist/cli.js`（`package.json:9-11`），其 dist 消费者含 `{result}` 短路（见 1a）。npm link 的**当前**状态无 shell 不可验证，属结构证据 + setup 断言。

### 5. 证据可信度复核（读 T-W13/T-W14 全文逐断言判定，未重跑）

**T-W14（user_bash）**：骨架强——`runUserBash` 走**真实** `harness.session.extensionRunner.emitUserBash`（真实 `activate(pi)` 注册面，coverage.test `extensionFactories: [(pi) => activate(pi)]`，非直接调 guard 函数），断言的是执行后端记录 `executed === []` 而非仅返回值；反向对照 `executed === [command]` 非空转；处方命令不吃掉亦有对照。强度不足项见下表 #1/#2/#5。
**T-W13（doctor 两项）**：骨架强——真夹具 + 真实仓只读 doctor 前后对照（部署前 2 条 issue rc=1）+ rc 翻转用「同项目删标记→红、恢复→绿」的非空洞反事实；诚实声明了未跑真实 `mw build --install`。强度不足项 #3/#4。

**证据强度不足的具体断言（5 条）**：

1. T-W14 的短路判据在测试里是 `runUserBash` 对生产消费者（`handleBashCommand`/RPC `bash`）的**复刻**（`if (eventResult?.result)` 手写在测试里），从未驱动真实 TUI/RPC 函数体——pi 核心若改消费者语义（例如不再认 `result`），该套件保持绿。缓解：T-W14 引 dist 源码坐标支撑，且本次审计已在 src+dist 双侧独立复核语义一致；但「消费者语义」这一环仍是引证而非测试锁定。
2. T-W14 的负对照（临时改事件名 → 2 failed → 还原）是**叙述性证据**，不可从已提交树复现（变异已还原，无对应的永久性失败测试）。可信但不可复核。
3. T-W13 的「部署后自动转绿」只用**假 bundle 夹具**证明（rc 1→0），卡内未跑真实 `mw build --install`（卡片明令禁止，PM 后续落地）；本次审计以内容级核验（两份真 bundle 均含标记与挂钩）补强了这一环，但「真实部署后 doctor 归零」的端到端输出仍无人留存。
4. 部署数值（两份各 1,136,103 B、`worktree`=25）是 PM 报告值；本会话工具无法复算字节数（`user_bash`=2、`reparse-point`=1 已复算一致）。字节级同一性未经第三方复算。
5. T-W14/T-W06 的执行后端是 `BashOperations` 记录器 stub——证明「后端未被调用」，不等于「真实本地后端未 spawn 进程」（T-W14 残留 #1 已自行声明；属固有限制，真树删除被硬约束禁止）。

## 未覆盖面声明

**① 工具边界（writeless + 无 shell）**：
- 本会话无 shell 工具：卡片的全部验收命令（vitest 两文件、pytest `test_doctor_activation.py`、`mw doctor`、`git grep --untracked`、`node -e`）**均未执行**；测试通过状态引自 T-W13/T-W14 证据原文，未经本卡复跑。
- **未做执行型反例**：所有「拦/放」结论为静态代码路径推演（引用 `bash-segments.ts`/`worktree-junction-guard.ts`/消费者行号），未在真实 bash/PowerShell 里执行对抗命令验证 shell 侧实际语义（`\<LF>` 拼接、`cd /d`、PS 别名 `ri`、反引号转义的运行时行为按 POSIX/PowerShell 文档语义推断，未实测）。
- 字节数（1,136,103 × 2）与 `worktree`=25 无法复算（无 stat/wc）；npm link 当前状态、`pi` 在 PATH 的解析结果无法验证。
- `find` 工具受 .gitignore 影响：`**/agent-team-loop.js` 全仓搜索返回空（dist 目录被忽略/未索引），改用直接 ls/grep 已知目标路径；**未做全盘无死角扫描**（node_modules 深处副本、其它驱动器、双工作空间 game root 的 `.pi/extensions` 未逐一排除——后者仅在存在 dual-mode target.yml 时才成为加载位）。
- 未建任何夹具、未写任务目录外任何文件（唯一写入 = 本报告 + progress.md）。

**② 方法边界**：
- 本卡只做**对抗性证伪**；未做全量危害面清单（W-12 方法）、未做 AC 声明 ↔ 证据坐标的引用闭包逐条核对（QG 方法）。
- 攻击枚举以「我能静态想到的形态」为上界，**不声称穷尽**；「本次尝试未找到」不等于「不存在」（尤其 AC-016 的解耦通道与 AC-014 的逃逸面）。
- 静态推演的「拦」结论依赖对 lexer/判定函数的阅读正确性；其中已被既有测试覆盖的形态标注了测试坐标，未标注者为纯静态推演（待执行型验证）。

## 上下文来源

- 任务卡：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w15-delta-adversarial/task.md`（内嵌 dispatch card，card_sha256 见文首）
- 规格/决策：`.agenticdoc/mw-worktree-junction-guard/spec.md` §2 G6（AC-014/015/016 原文，`:54-56`）、§7 D-13/D-14/D-15（`:132-134`）；`.agenticdoc/goal.md` INV-1/INV-4
- 被审实现：`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`（`:92` decideWorktreeRemove、`:202`/`:217` 双挂钩、`:332` decideDeletePenetration、`:449` parseGitInvocation、`:517` readLocationTarget、`:549` parseDeleteInvocation、`:609` expandToken、`:695` notRemove、`:700-707` reparsePointVerdict）；`shared/bash-segments.ts`（换行/续行/转义/拆段语义）；`index.ts:70`（无条件注册）
- pi 侧消费者/契约：`core/extensions/runner.ts:955-978`（emitUserBash）、`core/extensions/types.ts:815-824,1080-1085,1241`、`modes/interactive/interactive-mode.ts:6269-6340`、`modes/rpc/rpc-mode.ts:556-580`、`core/agent-session.ts:2770-2796`（executeBash/shellCommandPrefix/cwd）、`core/extensions/loader.ts`（on 无白名单）、`config.ts:531-537`（getAgentDir）、`core/package-manager.ts:2365-2403`（扩展发现路径）；运行时 dist：`node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/interactive-mode.js:5289-5317` 与 `packages/coding-agent/dist/...`（同行号）
- Python 侧：`worktree_registry.py:48-97`、`worktree_doctor.py:138-165,303-325`、`mw_common.py:1294-1300,2327-2332,2745-2830,3878-3908,4027-4030,4176-4198`、`mw.py:587-637,5153-5161`、`launcher.py:1370-1388`
- 部署事实复核对象：`packages/multi-workers/dist/extensions/agent-team-loop.js`、`C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`、`C:\Users\wenbozhou\.pi\agent\settings.json`、仓内 `.pi/extensions/`
- 证据复核对象：`evidence/T-W14-user-bash-guard-20261013.md`、`evidence/T-W13-doctor-visibility-activation-20261013.md`；测试：`packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`（25 例清单复读）、`worktree-junction-guard-coverage.test.ts`（全文精读）、`packages/multi-workers/test_doctor_activation.py`（全文精读）、`test_worktree_doctor.py:494-538`
- 方法正交性对照：`evidence/quality-gate-report-20261013.md`（引用闭包）、`evidence/negative-space-audit-20261013.md`（负空间；grep 确认其未覆盖本卡新发现：pushd/嵌套 shell/头部插值/PS 别名/续行拼接均无命中）

**执行过的命令清单**（全部只读工具调用；含未产出结论的尝试）：
1. `read` task.md / worktree-junction-guard.ts（全文）/ bash-segments.ts（全文）/ interactive-mode.ts（:2975-3019, :6260-6380）/ rpc-mode.ts（:550-630）/ runner.ts（:950-995）/ agent-session.ts（:2770-2835）/ mw_common.py（:2700-2880, :3850-4270）/ worktree_doctor.py（:138-330）/ worktree_registry.py（grep 上下文）/ worktree-junction-guard-coverage.test.ts（全文）/ worktree-junction-guard-decide.test.ts（:142-256 + it() 清单）/ test_doctor_activation.py（全文）/ T-W14、T-W13 证据 / spec.md（grep 上下文）
2. `grep`：emitUserBash|user_bash（coding-agent/src）、handleBashCommand 调用点、executeBash 定义、bash-executor cwd、getAgentDir/extensions 发现、index.ts 注册、PI_CODING_AGENT_DIR（multi-workers 全目录）、launcher pi 启动、cmd_doctor/STALE CODE、reparse-point（扩展源 → 2 处）、"user_bash"（扩展源 → 2 处）、user_bash|reparse-point（两份部署 bundle → 同行号命中）、extensions|skills|prompts（全局 settings.json → 零命中）、负空间审计关键词重叠检查（→ 零命中）
3. `ls`：`.pi/`、`.pi/extensions/`、`C:\Users\wenbozhou\.pi\agent\extensions\`、`packages/multi-workers/dist/extensions/`、evidence/、mw-worktree-junction-guard/
4. `read`（运行时 dist）：`node_modules/@earendil-works/pi-coding-agent/dist/modes/interactive/interactive-mode.js:5289-5326`；`grep` 同文件 emitUserBash + `packages/coding-agent/dist` 同文件比对（同行号）
5. **未产出结论的尝试**：`find **/agent-team-loop.js`（全仓）→ 「No files found」（dist 被 gitignore 语义隐藏），改用直接路径核验；`grep` 寻找 `PI_CODING_AGENT_DIR` setter → 未找到 setter（本身即结论：mw 全链路不设该变量）

ADVERSARIAL: AC-014=站稳 AC-015=有裂缝 AC-016=站稳 部署=站稳 证据强度不足=5 条 | 攻击尝试=43 条
