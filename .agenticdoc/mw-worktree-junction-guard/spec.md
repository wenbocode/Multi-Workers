# spec — mw-worktree-junction-guard

## 0. Goal Alignment（goal.md）

**对齐**：`.agenticdoc/goal.md` 的并行承诺建立在「多 Worker 共享同一工作树而不互相破坏」之上。2026-10-09 的实证事故（`git worktree remove --force` 穿透 junction，删掉 8 个包整树 **3,300** 个已跟踪文件（+ `packages/tui` 被删 156 ⇒ **3,456**）、丢弃他人未提交改动、约 5.5 分钟无人报警）直接证伪了这一前提，并让一个 key 的 QG 判定建立在损坏过的树上。

**预期收益**：
1. 危险路径**不可达**（执行前拦截），正确顺序**只由代码保证**，不依赖 agent 自觉；
2. 隔离验证（worktree）从"高危捷径"变成"有唯一正规入口的常规操作"；
3. 同类事故可被**机器发现**而非靠人撞见。

## 1. 事实基础（实证，非推算）

> 口径注（2026-10-13）：本表与 §0 原有两处「3,448」为 v1 陈旧值，已按 `mw-workspace-incident-probe` 的独立 QG 报告（`…evidence/quality-gate-report-20261009.md` §3.5/E1）与 v3 timeline 修正为 **3,456 = 3,300（8 包）+ 156（`packages/tui` 被删）**。

| 事实 | 出处 |
|---|---|
| `git worktree remove --force` **穿透** junction（双层链可穿两层） | `mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`（含 `%TEMP%` 最小复现） |
| `cmd /c rmdir <link>`（无 `/S`）与 PS `Remove-Item -Recurse` **不穿透** | 同上（对照实验） |
| 事故命令原文/时刻/会话 | `…evidence/incidents-timeline-20261009.md` §1（jsonl L142/L144） |
| 受害面 3,456 文件 = 8 包整树 3,300 + `packages/tui` 被删 156（原物幸存 80/236） | `…evidence/in2-file-vanish-incident-20261009.md`（§2.1/§2.2）＋修正后 `…evidence/incidents-timeline-20261009.md`（v3 §2，已吸独立 QG 的 E1/E2） |
| 未提交改动被静默丢弃（写入证据齐全） | 同上（AC-007） |
| 现有 **12 道执行前门禁**对 `git worktree remove` **全部零命中**（含 worker write-scope 的 git 子命令词表只有 `checkout\|apply\|clean\|restore`） | `evidence/research/design-necessity-rq1-equivalent-guard-20261013.md` §1、§2 |
| 端到端实测：三种模式（every / PM / worker）**今天仍能得手**（阳性对照 rc=0；同轮 `rm -rf <面外>` 被拦 ⇒ 守卫自身生效，是 git 形态漏过） | `evidence/research/design-necessity-rq2-reachability-20261013.md` §3/§4 |
| 事故面仍在：仓内 **14 条** Junction + 仓外活雷 `%TEMP%\mwvg-t5\node_modules` + `package-lock.json` 恰 **14 条** `"link": true`（结构性对应） | `evidence/research/design-necessity-rq3-live-surface-20261013.md` §1/§2 |
| **仓库自带复刻路径**：`npm run diff:model-catalog`（`scripts/diff-model-catalog.mjs:148`/`:155-157`/`:235`）默认 `worktree add` + 建 junction + `worktree remove --force`，且不经 agent bash 工具 ⇒ G1 看不见 | 同上 §3.2（PM 已逐行复核） |

## 2. 验收标准

**G1 · 确定性拦截**
- **AC-001** 对含 reparse point 的 worktree 执行 `git worktree remove`（含 `--force`）时，**执行前被 block**，命令未真正运行（以副作用为零证明）。
- **AC-002** block 的报错文本**包含可直接照抄的正规命令**（G2 形式），且含被检出的链接路径与目标。扩展（决策 **D-11**，2026-10-13）：对**非 worktree 目标**的穿透形态（`rm -rf <dir>/`、`rm -rf <dir>/*`、`Remove-Item -Recurse <dir>\*`）被拦时，文本给出的是可照抄的 `cmd /c rmdir "<link>"`（无 `/S`）而不是 `mw worktree rm`——后者只适用于已注册 worktree。
- **AC-003** 对**不含** reparse point 的 worktree，`git worktree remove` **不被误拦**（零副作用放行），并有反向对照。

**G2 · 唯一正规命令 `mw worktree rm <path>`**
- **AC-004** 六步顺序固定且不可跳步：枚举 → 校验目标在仓库内 → 只摘链 → 复核主树 `node_modules/@earendil-works/*` 链接目标逐条未变 → `git worktree remove --force` → 打印前后对照。
- **AC-005** 含链 worktree：**只摘链、主树零损伤**（以主树 `node_modules` 与 8 个包的文件清单/哈希前后一致证明）。
- **AC-006**（决策 D-1，2026-10-13 用户确认）链接目标按**三分类**处置：① 目标在 `repo_root` 内 ⇒ 摘链 → 复核 → `remove`；② 目标在**待删 worktree 子树内**（自指链，如 worktree 内 `npm ci` 生成的仓内自举）⇒ 摘链；③ 其它（真正的仓库外）⇒ **fail-closed 拒绝执行**，不摘任何链。
- **AC-007** 任一步失败 ⇒ **中止并保留现场**，明确输出"未降级继续"；不得部分摘链后继续 remove。

**G3 · 对称命令与巡检**
- **AC-008** `mw worktree add <path>` 默认**不创建 junction**；显式 `--link-deps` 时才建链，并**登记注册表**（含目标、创建时刻、创建者）。
- **AC-009**（决策 D-2，2026-10-13 用户确认）`mw doctor` 报出「遗留的、指向仓库内的 junction」并给出路径；判定域**默认 = 注册表域 + 仓库内 `node_modules/*` 顶层**（实测 ~2 ms），`%TEMP%` 等全域猎捕走**显式开关**（不做默认）。「遗留」的判据（决策 **D-10**）：① 注册表登记项 —— `link` 仍在而 `worktree` 已不在 ⇒ `leftover`，`link` 已不在 ⇒ `stale-entry`；② 仓内顶层链 —— 目标规范化（**剥 `\\?\` 前缀**）后落在 `repo_root` 内**且不在 `package-lock.json` 的 `"link": true` 期望集内** ⇒ `leftover`（`node_modules/*` 的 workspace 链是**正常态，必须静默**）。对无遗留的仓库不误报：反向对照 = 本仓实测期望集 14 条 = 磁盘 14 条 ⇒ `count==0`、零行输出、rc 不变；语料锚点 = `%TEMP%\mwvg-t5\node_modules` 现存活雷形态，仅在开关开启时可见。域 (c) 额外遵循决策 **D-12**：不报「worktree 仍存活的已登记链」（那是正常态），只报 worktree 已消失或未登记的链。

**G4 · 可观测**
- **AC-010** 「已跟踪文件数骤降」判据：构造 file-count 骤降（临时仓库）⇒ 触发；正常波动（如单文件编辑）⇒ 不触发。
- **AC-011** 「junction 目标丢失」判据：构造断链 ⇒ 触发并给出路径；完好链 ⇒ 不触发。
- **AC-012** 端到端复现：在 `%TEMP%` 内建 worktree + 链 → 走新流程清理 → **主树 mtime 与内容零变化**（机器对照），且全程无 block 误放行。

**G5 · 仓库自带触发面**
- **AC-013**（决策 D-9，2026-10-13 用户确认）`scripts/diff-model-catalog.mjs` 在 `git worktree remove` 前**必须先摘链**（`cmd /c rmdir <wt>\node_modules`，无 `/S`）**或**改为不建链（worktree 内 `npm ci --ignore-scripts`），使该脚本在含 junction 的真树上跑完**主树零变化**（判据 = manifest 的 `removed/added/content_changed/missing_after` 全 0，复用 AC-012 原语）；反向对照 = **现行**脚本在夹具内必须能复刻事故（否则夹具不成立）。

**G6 · 运行面激活与可见性**（决策 D-13/D-14/D-15，2026-10-14 用户「按建议」确认；依据 = 负空间审计 `evidence/negative-space-audit-20261013.md`）
- **AC-014**（决策 D-13）pi 的**用户直敲命令通道**（TUI `!`/`!!` 与 RPC 同事件，pi 的 `user_bash` 事件）对含 reparse point 的 worktree 执行 `git worktree remove|rm`（含 `--force`、`-C`、`cd`/`Set-Location`、插值形态）时**同样被 block 且零副作用**；判定复用 G1 的同一套 `decideWorktreeRemove` 语义（含 D-4/D-11 的动词面）。反向对照：干净目标上的 `!` 命令照常执行（不得误拦）。边界：**不**覆盖人在 pi 之外的 OS shell 直接执行（design 非目标，见 §3 约束与 design §1）。
- **AC-015**（决策 D-14）注册表文件**损坏/不可读**时，`mw doctor` 必须**可见**：文本面给出明确行（含错误摘要与注册表路径），并作为 issue 影响 rc；反向对照 = 注册表健康时零新增行、rc 不变。
- **AC-016**（决策 D-15）**激活自检**：`mw doctor` 必须能报出「本 key 的拦截能力在当前运行面上未激活」，至少覆盖 ① 已部署扩展 bundle（`packages/multi-workers/dist/extensions/agent-team-loop.js` 与全局 `~/.pi/agent/extensions/agent-team-loop.js`）是否包含 G1 能力；② 常驻 `mw serve` 是否运行含 G4 采样的代码（复用现有 `serve code: STALE CODE` 判据，不新增进程探针）。反向对照 = 两项均满足时零新增行、rc 不变；bundle 文件缺失亦须报出并给可照抄的修复命令（`mw build --install`）。

## 3. 约束

- 不改 pi 核心；TS 侧走 Extension API，Python 侧走 `mw.py`。
- **写面按文件切分**：TS guard / `mw.py worktree` 子命令 / doctor 检查 / 测试，**同一文件同一时刻只允许一个 worker**。
- Guard 与 G2 必须**互为闭环**：被 block 的文本能直接照抄执行。
- 所有判据必须**机器可复算**；数值一律实测化（禁陈旧字面量），并附反向对照。

## 4. 交付物

G1..G5 实现 + 测试（含 5 组反向对照）+ 真机端到端复现记录 + `achieved.md`（含「## 遗留」与未坐实项）。其中 **AC-013 是对现有 `scripts/diff-model-catalog.mjs` 的最小修复**（摘链后再 `remove`，或改 `npm ci`），与 G2 复用同一摘链原语。

## 5. 可复用资产（前馈）

> 实现前先读本节：以下资产已存在并有实测先例，**不得重新发明**。行号以 `design.md` §4.1 的「行号漂移警告」为准（实现前 grep 函数名，不照抄数字）。

| 资产 | 位置 | 用途 |
|---|---|---|
| `parseBashSegments` + `BACKSLASH_ESCAPES_*` | `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:273-518`（模块私有，需 export 或下沉，见 design 决策 D-3） | bash 分段/引号剥离；已实测能原样取出事故 token `$env:TEMP\qg-head`（插值不展开） |
| guard 注册范式 + handler 内同步 fs 先例 | `extensions/agent-team-loop/index.ts:42/:49/:59`；`shared/protected-config.ts:247-274`、`:224-243` | 新 guard 的落点、形状与审计写法 |
| `tool_call` hook 契约 | `core/extensions/types.ts:853-861/:1071-1075/:1188`；`core/extensions/runner.ts:932-950`；`packages/agent/src/agent-loop.ts:617-645/:657-661` | `block` = 工具不执行；handler 抛异常同样 fail-closed；无结构化错误码 ⇒ 机器可判据只能落 `reason` + 自写 trace |
| 六步事务范式 | `packages/multi-workers/mw.py:966-1058`（`_toolchain_run`：前置快照→动作→后置快照→drift→打印对照→退出码）、`:2205-2216`（`_cmd_rag_init`：先全量判定、一条都不写） | G2 的步 2/4/6 直接照抄 |
| 锁原语（Python/TS 同协议） | `mw_common.acquire_lock:2039` / `release_lock:2054`（`O_CREAT\|O_EXCL` @ `:2044`）、`conductor.lock_file:137-139`、`shared/file-lock.ts:12-43` | 注册表与采样状态文件的并发控制；**不新写锁实现** |
| 原子写 | `mw_common._write_workers_file:2063-2075`、`autopilot/config.py:save_config`（校验→tmp→`os.replace`） | 注册表写入 |
| `_run_stream(cmd, *, cwd)` / `_git(...)` / `_repo_root()` | `mw.py:4791` / `:4097` / `:4350` | npm 引导与 git 调用（`Windows Popen` 需绝对可执行路径） |
| 路径面 git status 惯例（天然排除 dist） | `mw.py:4503/:4504/:4507`、`:5175` `_git_dirty`、`:5192` `_claude_adapter_drift`（rel-path 并集 + 逐文件比对） | AC-010 的范围面与两树对照骨架 |
| 状态文件/锁的既有形状 | `.mw/` 实测 15 个文件名（`mw.pid`/`serve.meta`/`launcher-beat.<pid>`/`workers.lock`/`dispatch.yml`…）；`.agenticdoc/_workers.parallel` 第 8/9 列 = `model`/`origin`（“谁写的”语义先例，`autopilot/dispatch.py:1149-1152`） | 注册表落点与 `created_by` |
| 采样/告警/落盘通道 | `launcher._poll_once:1706`、每 poll beat `:1717`、告警形状 `launcher.py:1277`、trace `:1612`；`mw serve` 1 Hz（`mw.py:353/:376`）；conductor 4 s（`conductor.py:7256` + `config.py:86`） | AC-010/011 的采样点与告警 |
| doctor 段注册与 issue 汇聚 | `mw_common.doctor_report`（`:3624-3664`，段赋值 `:3642-3655`）、`_doctor_issues:3401`、`format_doctor_text:3666`、退出码 `mw.py:534` | AC-009 必须挂这里（见 §6 坑点 2） |
| TS 端到端“命令未执行”范式 | `test/suite/harness.ts`（faux provider）、`test/suite/xkey-gate-guard-coverage.test.ts:121-131`（`BashOperations` 记录器） | AC-001/003 的测试 |
| Python CLI 测试范式 | `test_doctor_gates.py`（doctor 段 + `capsys` + 退出码）、`test_rag_cli.py`（真 CLI `subprocess` 退出码） | G2/G3/G4 测试 |
| worktree/链接夹具骨架 | `test/footer-data-provider.test.ts:42/61`（`createReftableWorktree`）、`test/resource-loader.test.ts:943/956`（`linkWorktree`/`setupNestedWorktree`） | AC-012 夹具参考（仓内无现成 junction 夹具） |

## 6. 需规避坑点（前馈）

> 每条都由本阶段实测坐实（证据：`evidence/research/design-*-20261013.md`），实现时**不得**再踩。行号同 §5 的漂移警示。

| # | 坑点 | 规避 |
|---|---|---|
| 1 | **行号漂移**：卡/spec 期行号是 2026-10-09 旧修订（`_parse_args` 5324→5603、`doctor_report` 2957→3624、`_doctor_issues` 2780→3401…） | 一律 grep 函数名，不照抄数字；本 key 的证据与 `design.md` 用实测行号 |
| 2 | **`mw doctor` 注入段永不产生 issue**：`mw.py:522-526` 的注入发生在 `_doctor_issues`（`mw_common.py:3662`）之后 ⇒ 只能 informational、不翻转退出码 | AC-009 挂 `doctor_report` 内部；若确要“只可见”，必须在 design 里显式写明降级 |
| 3 | **`readdirSync(..., {recursive:true})` 会跟进 junction**（实测返回链接内部条目） | 自建显式栈 + 命中 reparse point 不下钻 |
| 4 | **`os.walk` 也会下钻 junction**（`followlinks=False` 亦然） | 全仓扫描必须显式剪枝，否则重复遍历 `packages/**`、病态时成环 |
| 5 | **Node 判不出 junction vs symlink**：`lstatSync` 对 junction 报 `isSymbolicLink()=true`，`Stats` 无 `fileAttributes`/`reparseTag`（实测 `undefined`） | junction 判定与 AC-011 的权威实现放 Python |
| 6 | **不能用 `git ls-files` 当骤降判据**：它只读索引，磁盘文件被删后计数不变（实测 6→6、5001→5001） | 用 `git ls-files -d`（或 `git status --porcelain` 的 ` D` 行）；切分支会让 tracked 总数变（180↔200）却 `-d` 不变，任何用总数的方案都会误报 |
| 7 | **不排除 dist 必误报**：本仓 2,239 个 tracked 在 `*/dist/`（占 `packages/` 58.5%），`npm run clean --workspaces` 会让“总 D”飙到 ~2,170 | 判据按路径面排除 dist（照 `mw.py:4504` 惯例） |
| 8 | **`existsSync`/`stat` 看不见断裂 junction**（断链 `exists=False`，但 `lstat.isSymbolicLink()=true`）；`Test-Path <link>` 对链接本身恒 True | 用 `lstat`/`os.path.lexists`/`isjunction`；判目标完好要判 `<target>` 而非 `<link>` |
| 9 | **`os.readlink` 带 `\\?\` 前缀**（junction）；Windows 短名（`WENBOZ~1`）与长名混用 | 前缀剥掉 + `normcase`+`normpath` 后再做前缀比较 |
| 10 | **PowerShell `FileSystemInfo.Target` 惰性解析**：先删链再读 `.Target` 得空串（`Test-Path ""` 抛错） | 删除前把 `Path/LinkType/Target` 落到普通对象 |
| 11 | **`open("w")` 写注册表会先截断**（序列化异常 ⇒ 文件写空） | tmp + `os.replace` + 读回验证（照 `_write_workers_file:2063-2075`） |
| 12 | **两套锁协议 = 事故温床** | 复用 `mw_common.acquire_lock`/`release_lock` 与既有命名锁规则，不新写 |
| 13 | **G1 的 block 文案必须可执行**：G2 命令此刻还不存在（`mw.py` 的 `worktree` 命中只有 `:5335`/`:5360` 两处只读 docstring，无子命令） | G1/G2 同版本落地；文案与 `design.md` §4.3 契约逐字一致 |
| 14 | **AC-006 字面与“仓库外 worktree + `npm ci` 自指链”死锁**（G2 拒 + G1 拦） | 按 `design.md` §4.4 的三分类判定（决策 D-1，2026-10-13 已确认） |
| 15 | **采样命令可能刷新 `.git/index`**（未观测到变化，但 git 文档允许） | 采样统一 `git --no-optional-locks` / `GIT_OPTIONAL_LOCKS=0`；不并跑其它 git 写操作 |
| 16 | **夹具绝对不能指回真树**，清理也不能用穿透形态 | 链接目标全部在夹具目录内；清理 = 先逐条 `cmd /c rmdir <link>`（无 `/S`、无尾分隔符）再 `rmdir /S /Q <root>` |

## 7. 决策记录（2026-10-13，用户「按建议」确认）

> spec 在 design 期由 PM 持有。以下三项为 design 阶段暴露的规格级决策，已获用户确认，并据此修订 §2 的 AC 文本（AC-006 / AC-009 重写、新增 AC-013）。

| 决策 | 内容 | 依据 |
|---|---|---|
| **D-1** | AC-006 改为**三分类**（`repo_root` 内 / 待删 worktree 子树内 / 其它 fail-closed） | 字面实现会与「仓库外 worktree + `npm ci` 自指链」死锁（G2 拒 + G1 拦） |
| **D-2** | AC-009 判定域默认 = 注册表域 + 仓库内 `node_modules/*`；全域扫描走显式开关 | 全域 5.39 s vs 默认 ~2 ms |
| **D-9** | 新增 **AC-013**：修 `scripts/diff-model-catalog.mjs`（摘链后再 remove / 不建链） | 仓库自带一条与事故同构的默认路径，且 G1 天然看不见 |
| **D-10** | AC-009 的「遗留」判据 = 注册表项（`link` 在而 worktree 不在 / `link` 已不在）+ 仓内顶层链**减去** `package-lock.json` 的 `"link": true` 期望集 | D-2 的字面规则（“目标在仓库内 ⇒ leftover”）会把本仓 5 条正常 workspace 链全报成遗留（PM 实测：剥 `\\?\` 前缀后 5/5 目标落在仓内）⇒ `mw doctor` 永远红，与 AC-009 自己的反向对照（干净仓库 `count==0`）直接矛盾 |
| **D-11** | G1 的动词面补上 `rm -rf <dir>/`、`rm -rf <dir>/*`、`Remove-Item -Recurse <dir>\*`（仅尾分隔符/通配形态），非 worktree 目标用第二套 block 文本（处方 `cmd /c rmdir "<link>"`） | `design.md` D-4 第 2 条本已要求（RQ-1 坐实这些形态穿透 1 层），但 **PM 写卡时把它错归入“不扩大动词集”**，首轮实现因此只覆盖了 git 通道（W-05 报告已显式标为残留）。无尾分隔符/无通配仍 allow |
| **D-12** | AC-009 的域 (c)（`--worktree-scan-roots`）跳过「worktree 仍存活的**已登记**链」，只报 worktree 已消失或**未登记**的链 | 否则 (c) 会把正常态的活 worktree 链报成 `leftover`，与 D-10 同一个道理（正常态不得误报）；而它真正要抓的语料形态（mwvg-t5：worktree 已删、链还在）不受影响 |

### 2026-10-14 追加（负空间审计派生，用户「按建议」确认）

> 来源：`evidence/negative-space-audit-20261013.md`（独立第二审计，方法与 QG 正交）。它确认 QG 逐条证据链无误判，但**推翻**「13/13 ✅ ⇒ INV-1/INV-4 运行时达成」的隐含推论，并给出 6 项差集与 29 条危害面三态清单。以下四项据此把范围从「仓内实现」扩到「运行面成立性」。

| 决策 | 内容 | 依据 |
|---|---|---|
| **D-13** | 新增 **AC-014**：把 G1 判定面补到 pi 的 `user_bash`（`!`/`!!`）通道 | 审计 N-06：全仓 `.on("user_bash")` 为 **0** 处，而 `emitUserBash` 在 TUI/RPC 均有出口、事件契约支持拦截（handler 返回 result 即短路）⇒ `! git worktree remove --force <含链 wt>` 与事故命令同构且不经任何守卫；spec INV-1「没有任何执行通道」的绝对措辞在该通道上不成立 |
| **D-14** | 新增 **AC-015**：注册表损坏必须可见（文本行 + issue 影响 rc） | 审计 N-04：实现把 `WorktreeRegistryError` 折进 `scanned.registry_error`，而文本面仅在 `count>0` 时打印、issue 不消费该字段 ⇒ 损坏时静默零输出、rc 不变，与 design §5.1「坏文件 ⇒ 抛错，**绝不静默当空表**」直接矛盾 |
| **D-15** | 新增 **AC-016**：激活自检（扩展 bundle 是否含 G1 + serve 是否含 G4） | 审计 N-01：两份 bundle `worktree` 命中 **0**（G1 未部署）、常驻 serve 为 STALE CODE 且 `.mw/tree-watch.json` 不存在（G4 **从未采样**）⇒ 代码在仓内正确但运行面未激活，而 doctor 只检查 serve 代码新鲜度、不检查扩展 bundle ⇒ 没有任何一层会告诉运维「护栏没生效」 |
| **D-16** | 审计 N-05（`.mw/tree-watch.json` 无锁 + 多 launcher 交错采样可致基线错配）**接受为债**，记入 `achieved.md` 遗留 | 状态文件是诊断面、告警是建议性（不阻断执行）；多 launcher 是真实形态但漏报/误报窗口窄，修复收益低于成本 |

### 2026-10-14 追加（对抗性审计 W-15 派生：三条缺陷补齐 + 一条边界确认）

> 来源：`evidence/delta-adversarial-audit-20261013.md`（第三审计，方法 = 对抗性证伪；43 条攻击向量）。结论：AC-014 站稳、AC-016 站稳、部署宣告站稳、AC-015 **有裂缝**。以下四项把裂缝补上，并把审计新枚举的逃逸面显式归档。

| 决策 | 内容 | 依据 |
|---|---|---|
| **D-17** | AC-015 裂缝修复：注册表路径为**悬空符号链接**（`lexists` 为真而 `exists` 为假）必须按「不可读」处置 ⇒ issue + 文本行 + rc 变化 | W-15 §2：`worktree_registry.read_registry` 以 `path.exists()` 为门 ⇒ 悬空链跟随后被当成「文件不存在」返回 `[]`，是 12 种坏文件形态中**唯一静默**的一种。AC-015 原文本已含「损坏/不可读 ⇒ 可见」，故属实现缺陷补齐，**非新 AC** |
| **D-18** | AC-016 判据从单标记扩为**多标记**：`reparse-point`（判定面）之外必须同时存在 `"user_bash"`（G6 挂钩面） | W-15 §3 C4②：只删 `pi.on("user_bash")` 挂钩时单标记仍绿、doctor 照报「已激活」，而 `!`/RPC 通道已裸奔；实测 `"user_bash"` 在扩展源 **2** 处、两份 bundle 各 **2** 处 ⇒ 专属且可数。仍属 AC-016「本 key 拦截能力是否在运行面」的实现补齐 |
| **D-19** | D-11 动词面按**实际钉住的 shell** 补全：删除面纳入 PowerShell 别名 `ri`/`del`/`erase`/`rd`/`rmdir`；基准面纳入 `pushd`/`sl`/`chdir` 并跳过 cmd 风格 `/d`、`/D` | W-15 §1b：`mw_common.ensure_pi_shell_path` 把 pi 的 shell 钉在 PowerShell，`ri -r -fo <link>/` 与 `Remove-Item -Recurse <link>/` 同能力，却因头词白名单只有 `rm`/`remove-item` 而放行；`cd /d`/`pushd`/`sl` 同属「基准跟踪」已声明能力内的白名单缺项。**只补动词/基准词表，不动递归+尾分隔符/通配的判定谓词** |
| **D-20** | 其余 4 条静态不可判定逃逸（`\<LF>` 续行拼接、头部/子命令位插值、`bash -c`/`cmd /c`/`env` 前缀包装、PS 反引号转义）**接受为边界**，并入 §7 遗留 1 的清单 | 与 design §3.3 已声明的「嵌套解释器 / 刻意混淆」同族；修法需改共享 lexer（影响 `implementation-gate` 的写面判定）或引入命令级变量展开，收益与误拦风险不成比例 ⇒ 留待后续 key |

**必要性复核（同期）**：三条独立线索（12 道门零命中 / 端到端可复现 / 事故面仍在）结论一致 —— **目标未失效，且优先级提高**（新增 AC-013）。证据见 §1 表末四行。

**未变更项**：AC-001..AC-005、AC-007、AC-008、AC-010..AC-012 文本不变（G6 的 AC-014..AC-016 为 2026-10-14 新增，不改动既有 AC 语义）；D-3..D-8 属 design 内部实现决策（`design.md` §3/§6/§7），不改变 AC 语义。
