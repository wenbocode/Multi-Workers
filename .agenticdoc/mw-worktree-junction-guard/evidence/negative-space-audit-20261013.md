# negative-space-audit-20261013 — mw-worktree-junction-guard 第二份独立审计（负空间 + 危害面）

- **审计者**：`wjg-w12-negative-space-audit`（卡 `tasks/T-W12-negative-space-audit.md`，type: review）
- **时间**：2026-10-14（收口期，晚于独立 QG 报告 `quality-gate-report-20261013.md`）
- **范围**：① 先验工件清单 vs 仓库实际的负空间差集（该有而没有 / 有而无人引用）；② 全仓「能到达穿透式删除的路径」危害面全量清单（三态，不留空）；③ 对既有 QG 结论的复核（确认/推翻分开）；④ P-025 类反假抽样复核（≥6 条，实际 12 条）。**不做** QG 已完成的逐 AC 证据链表。
- **输入清单**：
  - 被审基准：`spec.md`（AC-001..AC-013 + §7 决策 D-1/D-2/D-9..D-12）、`design.md`（§3.3 规则表、§3.5 D-4 边界、§5.3 巡检域、§6.1 动作 (3)、§9 验证矩阵、§4.3 模板）、`achieved.md`。
  - 实现面（全文读）：`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`、`shared/bash-segments.ts`、`index.ts`、`worker/worker-mode.ts`（相关段）、`core/extensions/runner.ts`（emitToolCall/emitUserBash）、`core/extensions/types.ts`（事件契约）；`packages/multi-workers/worktree_cmd.py`、`worktree_registry.py`、`worktree_doctor.py`、`tree_watch.py`、`mw_common.py`（doctor 段 + W-09 消费点）、`mw.py`（worktree/build/doctor 段）、`launcher.py`（采样挂点）；`scripts/diff-model-catalog.mjs`、`scripts/detach-node-modules-link.mjs`；测试（TS decide/coverage、Python 5 文件、scripts 测试）。
  - 对照（证据面，仅作对照不作第一来源）：`evidence/quality-gate-report-20261013.md`（全文）、`evidence/T-W09/T-W10/T-W11-*.md`（全文）；`mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`（穿透/不穿透实测口径）。
  - 运行时工件（只读）：`packages/multi-workers/dist/extensions/agent-team-loop.js`（tracked bundle）、`C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`（全局部署副本）、`.mw/`（serve.meta、mw.pid、launcher.log、beat 文件清单）、`.gitignore`、`package-lock.json`、`.github/workflows/**`、根 `package.json`、`packages/coding-agent/package.json`。
- **只读限制**：本角色工具面 = read/find/grep/ls，**不能执行任何命令**（pytest/vitest/`npm run check`/真机 git 与 doctor 计数一律 `[无法独复现]`，只做存在性与内容一致性核对）。未修改任何被审文件；唯一产物为本报告。

---

## 方法

1. **先验清单先行**：在读任何 `evidence/T-W*.md` 或 QG 报告**之前**，仅依据 spec/design/achieved 与派发卡给定的实现面起点，逐条推导 AC-001..AC-013 与 D-1/D-2/D-9..D-12 要求存在的工件（文件/符号/注册点/测试/常量开关/文档条目），落到 `workers/wjg-w12-negative-space-audit/progress.md`（27 项，P1..P27，其中 P22/P24/P25 标注为派发卡口径而非 spec 推导）。
2. **枚举方法**（只读）：
   - 文件面：`find`/`ls` over `shared/`、`packages/multi-workers/`、`scripts/`、`.github/workflows/`、`.pi/`、`.mw/`（本工具遵守 .gitignore：被忽略文件不进结果；未跟踪未忽略文件包含在结果内 —— P-030 关注的未跟踪面由此覆盖；`git grep --untracked` / `git ls-files` 本角色不可执行，未用）。
   - 机制面 grep：`"tool_call"`（全部注册点）、`worktree (remove|rm|prune)`、`rmtree|rmdir|robocopy|Remove-Item|rm -rf|rmSync`、`"user_bash"`、`PI_TREE_WATCH_SEC|TREE_WATCH|tree-watch`、`worktree_links`、`"link": true`（直数 14）、`iter_entries|sample_and_record`（孤儿检测）。
   - 运行时工件核对：tracked bundle 与全局部署副本的内容 grep（G1 是否在产物内）；`.mw/serve.meta`（serve 身份/commit）与 `mw.pid`、`launcher.log`（TREE-WATCH 行）、`.mw/` 文件清单（tree-watch.json / worktree-registry.json 是否存在）。
   - 全文读：5 个新 Python 模块、TS guard、两个 TS 测试、`diff-model-catalog.mjs` finally 段、detach 模块、mw.py/mw_common.py/launcher.py 相关段。
3. **证据只作对照**：仓库正文与运行时工件是第一来源；证据文件（QG、T-W09/W10/W11、in1）在枚举完成后才读，用于反假抽样与既有结论复核。
4. **被差集推翻的先验假设**：
   - A1「源代码 + 测试落地 ⇒ 运行时防护已生效」——**被推翻**（N-01：部署产物与常驻 serve 均滞后）。
   - A2「achieved.md 验证入口数字反映当前 HEAD」——**被推翻**（N-02：W-09/W-10 落地后计数漂移未回写）。
   - A3「agent 相关的命令执行通道只有 bash tool_call」——**被推翻**（N-06：pi 另有 `!`/`!!` 的 `user_bash` 通道，守卫与全部扩展均未挂钩）。
   - A4（必查项 2 的先验）「新文件需检查构建/发布/白名单纳入」——**部分推翻预期方向**：不存在任何按文件的白名单（tsgo 全量编译 `src/**`，esbuild 从 `index.ts` 全量打包），真正的门槛不是「纳入」而是「重建 + 部署」（见 N-01）。
   - A5「QG 的 ✅ 可能存在假证据坐标」——**未成立**：抽到的坐标全部真实存在且内容相符；被推翻的不是证据链，而是「13/13 ✅ ⇒ INV-1/INV-4 运行时达成」的隐含推论。

---

## 先验工件清单 vs 仓库实际

先验清单共 27 项（P1..P27，存于本任务目录 `progress.md`）。逐项与仓库求差集后：**21 项全部存在且内容与 spec/design 相符**（G1 文件与判定流水线、D-11 两套文本、bash-segments 下沉 + implementation-gate 改 import、index.ts 注册、decide/coverage 两套 TS 测试、mw.py worktree parser 与 dispatch、六步事务与三分类、注册表 API 与原子写、doctor 三处挂载 + 函数内 import + 循环回归测试、tree_watch 判据/状态文件/PI_TREE_WATCH_SEC、launcher 挂点、5 个 Python 测试文件、G5 摘链 + 自检 + abort 保现场、W-09 窗口升级、W-11 detach 模块 + 测试、W-10 处方 allow、双 CHANGELOG、.gitignore `.mw/`）。差集如下。

### 表 1：该有而没有（6）

| # | 该有什么 | 依据（AC/决策/不变量） | 仓库实际 | 对应新发现 |
|---|---|---|---|---|
| 1 | **含 G1 的已部署扩展 bundle**（tracked `packages/multi-workers/dist/extensions/agent-team-loop.js` + 全局 `~/.pi/agent/extensions/agent-team-loop.js`）；以及**已重启、跑当前代码的常驻 serve**（G4 采样生效的证据：`.mw/tree-watch.json` 存在或告警行） | INV-1「没有任何执行通道」/ INV-4「可被机器发现」；achieved.md 自己声明了两道激活门槛（`mw build --install` + `/reload`；`mw serve` 重启后生效） | 两份 bundle 均 **0 处** `worktree` 命中、activate 仅注册 3 个旧 guard（bundle `:28541-28543`）；`.mw/` 无 `tree-watch.json`、`launcher.log` 零 `[TREE-WATCH]` 行、serve.meta（pid 49540，commit `604a95b5…`，dirty_tracked 49）≠ 证据记录的 HEAD（`55be3d960`）且 T-W09 §4 已实测 doctor 报 STALE CODE ⇒ 常驻 serve 跑的是 G4 之前的代码，**采样从未产出过一个样本** | N-01 |
| 2 | achieved.md「验证入口」的**现行**计数（vitest 25 + 9；pytest 四文件 73 / 五文件 84） | AGENTS「验证入口复核者可直接照跑」的承诺 | 验证入口写死 `23 + 9` 与 `72`：W-10 追加 2 例（decide 现 25 例）、W-09 在 `test_tree_watch.py` 追加 1 例（现 20 例 ⇒ 四文件 73）并新建 `test_tree_watch_doctor.py`（11 函数 / 23 项），全部未回写 | N-02 |
| 3 | design §3.2 `basis` 词表中的 **`delete-penetration`** 值 | D-11 扩了动词面 ⇒ 新 basis 值（实现与 decide 测试大量断言 `basis === "delete-penetration"`） | design §3.2 词表仍为旧 8 值清单（无 `delete-penetration`）；仅实现文件 docstring 与测试携带新值 | N-03 |
| 4 | doctor 对**注册表读取失败**（`registry_error`）的文本行或 issue | design §5.1「坏文件 ⇒ 抛错，**绝不静默当空表**」；doctor 是人看的主面 | `_registry_domain` 把 `WorktreeRegistryError` 折进 `scanned.registry_error`（`worktree_doctor.py:152-166`）；`format_doctor_text` 只在 `count>0` 时打印 leftover/stale（`mw_common.py:4025-4033`），`_doctor_issues` 不消费 `registry_error` ⇒ 注册表损坏时文本面零输出、rc 不变，仅 `--json` 可见 | N-04 |
| 5 | `.mw/tree-watch.json` 的**并发防护**（或多 launcher 下的采样隔离） | 盲区必查项 5；launcher 多实例是真实形态（`.mw/` 有 27 个 `launcher-beat.<pid>`） | `tree_watch.write_state` 只有 tmp+`os.replace`（原子但无锁，`tree_watch.py:434-460`）；每个 launcher 各自维护 poll 计数器却共享同一状态文件 ⇒ 交错采样可对错基线算 delta（漏报/误报窗口） | N-05 |
| 6 | `!`/`!!` 用户直敲 bash 通道的护栏（或规格对其的显式边界修订） | spec INV-1 措辞「含 reparse point 的 worktree **没有任何执行通道**能把它连同目标一起删掉」 | pi 的用户直敲通道走 `emitUserBash`（`interactive-mode.ts:6270-6278`、`rpc-mode.ts:562`、`runner.ts:955-985`）；G1 只挂 `tool_call`（`worktree-junction-guard.ts:179-190`），全仓无任何 `.on("user_bash")` ⇒ `! git worktree remove --force <含链 wt>` 直达 shell | N-06 |

### 表 2：有而无人引用（2）

| # | 工件 | 现状 | 判定 |
|---|---|---|---|
| 1 | `worktree_registry.iter_entries`（`worktree_registry.py:100-103`） | 生产面零调用（仅 `test_worktree_cmd.py:224` 一处测试断言）；`read_registry`/`find_entry` 已覆盖全部生产语义 | 只读便捷 API，测试专用面；非死代码（有测试消费），但生产无人引用——若求精简可并入测试内联；无需动作 |
| 2 | `.git/hooks/sendemail-validate.sample:75`（含 `git worktree remove -ff "$worktree"` 的 git 模板样例钩子） | `.sample` 后缀 ⇒ git 不激活；非仓库跟踪内容（在 `.git/` 内）；无引用 | 不可达，无风险；列此仅因危害面枚举承诺不留空 |

---

## 危害面全量清单

> 三态：**守住**（G1/G2/G5）/ **不在覆盖面且有理由**（含「目标域无 junction、机理不穿透」的不在危害路径）/ **未守住（新发现）**。枚举方法：机制面 grep + 文件面 find/ls + 运行时产物核对（见 §方法）。「源面守住」指源代码与常驻测试层判定成立；其运行时前提单独见 H-28。

| # | 机制 | 入口路径 | 三态 | 证据坐标 | 备注 |
|---|---|---|---|---|---|
| H-01 | `git worktree remove\|rm [--force] <字面路径>` | agent bash tool_call | 守住（G1，源面） | `worktree-junction-guard.ts:127-171`（parse→resolve→显式栈扫描→reparse-point verdict）；decide:162；coverage:254（worker 真链路零执行）/279（PM/交互同拦）/318（干净反向且真执行） | 运行面前提见 H-28 |
| H-02 | 插值形态 `$env:N`/`${N}`/`$N`/`%N%` + 命令内赋值（**事故原形态**） | 同上 | 守住（G1） | `expandToken :526-602`、`readAssignmentStatement :476-498`；decide:143（事故形态 block）/196（`$t=` 赋值）/205（未知变量 fail-closed）/187（可解析干净 allow） | 断链也命中（lstat，decide:170） |
| H-03 | `git -C <dir>` / `cd` / `Set-Location` 基准 | 同上 | 守住（G1） | `parseGitInvocation :405-458`、`readLocationTarget :481-496`；decide:248/:259/:268 | `-C` 优先于 cd 基准 |
| H-04 | 通配 / 尾分隔符 / 命令替换操作数 | 同上 | 守住（G1 fail-closed） | `globVerdict :674-682`；decide:212（`<wt>/*`、`<wt>/`、`$(…)` 三形态 block） | design §3.3 (c) 修订后口径一致（尾分隔符不剥离） |
| H-05 | 裸名操作数（worktree id/basename） | 同上 | 守住（G1） | `decideBareName :313-340`（`git worktree list --porcelain` 唯一匹配）；decide:268（唯一匹配指向链 ⇒ block）/277（歧义 block）/284（零匹配 allow，git rc=128） | spawnSync git 失败 ⇒ block（scan-error） |
| H-06 | 多/零操作数 | 同上 | 守住（G1 fail-closed） | `worktree-junction-guard.ts:135-145`（`operands.length !== 1` ⇒ block，basis=bare-name-ambiguous） | |
| H-07 | `rm -rf <dir>/`、`rm -rf "<dir>/*"`、`Remove-Item -Recurse "<dir>\*"`、`"<dir>/"`（D-11 穿透形态） | 同上 | 守住（G1） | `decideDeletePenetration :263-310`；decide:324/:340/:350/:359（两套文本各就位）；coverage:207/:297（真链路 + 处方 `cmd /c rmdir`） | 非 worktree 目标给第二套文本（前 3 条 + 总数） |
| H-08 | worker 窗口 read-scope / write-scope 对 worktree remove 零命中 | worker-mode 两个 tool_call | 守住（由 G1 兜住） | `worker-mode.ts:1499-1507`（git 词表仅 `checkout\|apply\|clean\|restore`）、:2165（read-scope）、:2218（write-scope，`Remove-Item -Recurse`/`rmdir /S` 提取 0 候选 ⇒ allow-unknown）；G1 注册在 `workerModeActivate` 之前（`index.ts:70`）+ `runner.ts:943-950` 首个 block 短路 | design §3.3 第 5 点的判定成立 |
| H-09 | Python 正规通道 `mw worktree rm`（六步事务） | `python mw.py worktree rm <path>` | 守住（G2） | `worktree_cmd.py` `remove_worktree`（步 2 先全量三分类、foreign 零摘链、无 `--force`/`--continue`、ABORT at step N/6 + 未降级继续）；`mw.py:6283/6581-6617/6734`；`test_worktree_cmd.py` 37 例（含正向对照 :492） | 唯一正规删除入口；G1 处方与其互为闭环 |
| H-10 | 仓库自带脚本 `npm run diff:model-catalog`（subprocess，G1 天然看不见） | `node scripts/diff-model-catalog.mjs` | 守住（G5） | finally 段 `:249-272`：先 `detachNodeModulesLink`（`detach-node-modules-link.mjs`，win32 `cmd /c rmdir` 无 /S + `lstatSync` 自检必须 ENOENT），失败 ⇒ `exitCode=1` + 手工处方 + **跳过** remove 与 `rmSync(temporaryRoot)` 保现场 | abort 保现场会在 `%TEMP%` 留 mwvg-t5 同类活雷（achieved 遗留 4，已登记；仅 `--worktree-scan-roots` 可见） |
| H-11 | 无尾分隔符/无通配 `rm -rf <link>`、`Remove-Item -Recurse <dir>` | agent bash | 不在覆盖面（D-4 rule 3：实测不穿透） | decide:306/:390/:396（显式 allow pin）；实测依据 in1 §3.1（MSYS rm / PS Remove-Item 不穿透）`[无法独复现]` | 设计决策，接受 |
| H-12 | `rmdir /S /Q <dir>` | agent bash + 测试夹具清理 | 不在覆盖面（实测不穿透） | decide:396 pin；夹具清理先逐条摘链、`/S /Q` 仅施于夹具根（coverage afterEach；design §9） | 设计决策，接受 |
| H-13 | `robocopy <src> <dst> /MIR` | agent bash | 不在覆盖面（实测不穿透） | decide:311 pin `[无法独复现]` | 设计决策，接受 |
| H-14 | `cmd /c rmdir "<link>"`（G1 处方二） | agent bash | 不在覆盖面（处方本身；实测不穿透） | decide:407（allow pin，含前导 `cd` 组合）；in1:119（`rc=0` 只摘链目标完好）`[无法独复现]` | 尾分隔符误拼形态 allow（decide:432 pin）：guard verdict 已实测，**该形态本身的穿透性未在本 key 任何证据中实测**（rmdir 无 /S 不递归，机制上低危；见残留） |
| H-15 | `git worktree prune` | agent bash / G5 手工提示 | 不在覆盖面且有理由 | guard 只认 `remove\|rm`（`:127`）；`diff-model-catalog.mjs:161` 手工提示含 prune | prune 只清 `.git/worktrees` 管理项、不递归删工作树目录（**机理推断，未实测** `[无法独复现]`） |
| H-16 | 人肉终端直接执行 `git worktree remove --force` | OS shell | 不在覆盖面且有理由 | G1 是 tool_call 层（design §1 非目标：非沙箱；§7 已知绕过面） | 事故形态 = agent 直写命令；人肉通道靠 G2 正规命令 + G3 巡检兜底 |
| H-17 | 其它 key 归档文档中的可照抄指令（`.agenticdoc/ai-baseline-repair/plan.md:51`、`tasks/T-05-attribution.md:14`「worktree 用后 `git worktree remove`」） | 文档 → 人/agent 照抄 | 不在覆盖面（同 H-16） | 本审计 grep 命中（仅此两处非本 key 文档含该指令） | agent 走 bash（部署后）由 G1 拦并给处方；人照抄不拦。建议后续把归档措辞换 `mw worktree rm`（低价值，非本 key 写面） |
| H-18 | `npm run clean` / `prepublishOnly` ⇒ 各包 `shx rm -rf dist` | npm scripts | 不在危害路径 | 根 `package.json` scripts；coding-agent `clean` | 目标为真实目录；G4 判据显式排除 dist 面（`tree_watch.is_dist_path`） |
| H-19 | scripts 内 `rmSync(recursive)` 清理（`local-release.mjs:130/:164`、`publish-model-catalog.mjs:301`、`profile-coding-agent-node.mjs:418/:520`、`release-notes.mjs:300`、`detach-node-modules-link.test.mjs:56`） | node scripts | 不在危害路径 | 本审计 grep 全量命中即此 | 临时目录无仓内 junction；node `fs.rmSync(recursive)` 实测不穿透（in1 §3.1）`[无法独复现]` |
| H-20 | `_rmtree_robust`（`mw.py:4208-4221`） | `mw pull-agentictask --force`（框架缓存 `packages/multi-workers/.tmp/`） | 不在危害路径 | 调用面仅 `:4227/:4329`（框架源缓存拷贝） | 目标无仓内 junction；`shutil.rmtree` 实测不穿透（in1 §3.1）`[无法独复现]` |
| H-21 | TS 侧 `rmSync(recursive)`（`external-editor.ts:40`、`windows-self-update.ts:56`、`tools-manager.ts:342-343`、`package-manager.ts:1820-1967`） | pi 自管目录 | 不在危害路径 | 本审计 grep 全量命中即此 | 编辑器临时目录/更新隔离区/扩展安装目录，均非仓内 junction 面 |
| H-22 | CI `rm -rf "${build_root}"` | `.github/workflows/build-binaries.yml:72` | 不在危害路径 | `mktemp -d` 于 Linux runner，随后 `tar -xzf` 源码包 | 无 Windows junction 语义；CI 全量 grep 仅此一处删除命令 |
| H-23 | 测试夹具清理与正向对照 | TS/Python 测试执行 | 不在真树危害路径 | coverage afterEach（先 `cmd /c rmdir` 摘链再 `rmdir /S /Q` 夹具根）；`test_worktree_e2e.py:208-227` `_rmdir_all_links`；正向对照 bare remove 仅在 `%TEMP%` 夹具（`test_worktree_e2e.py:401`、`test_worktree_cmd.py:492`） | 链接目标全在夹具内（design §9 硬约束） |
| H-24 | git 模板样例钩子 `.git/hooks/sendemail-validate.sample:75`（`git worktree remove -ff`） | （无） | 不在覆盖面（不可达） | `.sample` 后缀不激活 | git 自带模板，非仓库内容 |
| H-25 | G2 步 1→步 5 之间的 TOCTOU（并发新建链后 remove） | `mw worktree rm` 执行窗 | 不在覆盖面且有理由 | design §7「已知绕过面（明确不承诺闭环）：TOCTOU 窗口」 | 步 4 复核面仅主树 `@earendil-works/*`；设计已声明 |
| H-26 | `mw doctor --fix` / `archive_stale_entries` | mw CLI | 不在危害路径 | `mw_common.py:2345-2348`（只归档队列条目 + 删 PID 文件）；全量 grep 无目录删除 | |
| H-27 | launcher / conductor / autopilot 的删除面 | 常驻服务 | 不在危害路径 | 本审计对 `packages/multi-workers` 全量 grep（`rmtree\|worktree remove\|rm -rf\|rmdir\|robocopy`）：生产命中仅 H-09/H-10/H-20 所列 | |
| H-28 | **现役 pi 窗口内执行 H-01..H-07 任一形态**（旧 bundle） | agent bash（加载全局/项目扩展副本） | **未守住（N-01a）** | 全局副本与 tracked bundle 均 0 处 `worktree` 命中；activate 仅注册 3 个旧 guard（两份 `agent-team-loop.js:28541-28543`）；项目 `.pi/extensions/` 无 agent-team-loop ⇒ 窗口加载的就是全局旧副本 | 源面与测试层 AC-001..003 成立，但未 `mw build --install` + `/reload` 的窗口**没有 G1** |
| H-29 | **pi 的 `!`/`!!` 用户直敲 bash 通道** | `emitUserBash`（interactive-mode.ts:6270-6278、rpc-mode.ts:562、runner.ts:955-985） | **未守住（N-06）** | G1 只挂 `tool_call`（`worktree-junction-guard.ts:179-190`）；全仓 grep 无任何 `.on("user_bash")` ⇒ `! git worktree remove --force <含链 wt>` 不经任何守卫直达 shell | 事件契约支持拦截（handler 返回 result 即短路执行）；spec INV-1「没有任何执行通道」措辞与事实不符 |

**危害面路径合计 29：守住 10 / 不在覆盖面且有理由 17 / 未守住 2。**

---

## 新发现

> 每条：现象 / 反例坐标 / 影响 / 建议动作 / 是否建议新 key。不重复 F-01..F-06（已复核：F-01/F-03/F-04 的文档修订已落实——achieved.md `index.ts:70` ✓、design §3.3 (c) 已改口「尾分隔符不按 (a) 剥离」✓、design §5.1 已用 `worktree-registry.json` ✓；F-02=W-09 ✓、F-05=W-11 ✓、F-06=W-10 ✓ 均落地且内容相符）。

### N-01（高）运行时激活缺口：G1 未部署、G4 从未采样 —— INV-1/INV-4 在运行面当前不成立

- **现象**：五组保证里，G2/G3/G5 是每调用新进程（`mw worktree …`、`mw doctor`、`node scripts/…`），落地即生效；**G1 与 G4 是常驻面**，各有激活门槛，两道门槛都未跨过：
  - **G1**：可加载的扩展产物不含守卫。全局部署副本 `C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js` 与 tracked bundle `packages/multi-workers/dist/extensions/agent-team-loop.js` 内容一致且均为旧代（`git grep -i worktree` **0 命中**；activate 仅注册 protected-config / xkey-gate / implementation-gate 三个旧 guard，`:28541-28543`）。`mw build` 每次都会重建 tracked bundle（`mw.py:4715 _build_bundle()`），其不含 G1 ⇒ 该命令自 G1 落地后从未运行过；`_deploy_bundle` 把这份旧 bundle 拷去全局（`mw.py:4633-4634`）。本项目 `.pi/extensions/` 无 agent-team-loop ⇒ 现役窗口加载的就是这份无 G1 的全局副本。
  - **G4**：常驻 serve 跑的是旧代码。`.mw/serve.meta`（pid 49540、commit `604a95b5…`、dirty_tracked 49、started≈2026-10-13）≠ 证据记录的 HEAD（`55be3d960`，T-W11 §8）；T-W09 §4 已实测 doctor 报 `STALE CODE (content changed)`；`.mw/` **无 `tree-watch.json`**、`launcher.log` **零 `[TREE-WATCH]` 行**（新版采样器健康时也不打印告警，但每 30 s 必写状态文件——文件缺席 + 无 `sample skipped` 行 ⇒ 运行中的 launcher 根本没有 tree_watch 挂钩）。launcher.log 显示同一常驻面连续派发了 wjg-w01…wjg-w12（含写 tree_watch.py 的 W-04 与写 mw_common 消费点的 W-09），即：**派发守卫编写工作的服务自己从未运行过守卫**。
- **反例坐标**：上述两份 `agent-team-loop.js`（0 命中 + `:28541-28543`）；`.mw/serve.meta:1`；`.mw/launcher.log`（有 2026-10-13 起的 wjg-* 派发行、无 TREE-WATCH 行）；`.mw/` 文件清单（无 tree-watch.json）；`mw.py:4715/:4633-4634`。
- **影响**：AC-001..003 与 AC-010/011 在**源代码与测试层**成立（QG 判据未受影响），但「事故不可达」（INV-1）与「同类事故可被机器发现」（INV-4）在**当前运行面**不成立：一个未重载的窗口里，2026-10-09 的事故命令仍会得手（10-09 当天 12 道门禁零命中的状态在这些窗口里延续）；主树若再被穿透，无采样、无告警、无 doctor 升级。
- **建议动作**（一次序列，无代码改动）：`mw build --install` → 所有 pi 窗口 `/reload`（或重启）→ `/mw restart`（serve 重启后 `PI_TREE_WATCH_SEC` 默认开，30 s 内 `.mw/tree-watch.json` 应出现）。然后把**激活态**写进验证口径：① 验证入口补两条机器判据（bundle 内 `registerWorktreeJunctionGuard` 可 grep 到；doctor 无 `STALE CODE` / `.mw/tree-watch.json` 出现）；② 把「serve STALE CODE 时 G4 失效」与「bundle 滞后时 G1 失效」登记进 achieved.md 遗留表（当前遗留表没有这条——收口文本只在系统行为变化里各带了一句生效条件，未列为遗留债务）。
- **是否建议新 key**：激活序列本身**不需要**（一条命令链）；但「把 G1/G4 激活态做成 doctor 常驻判据」（如 `_doctor_bundle` 检查全局副本含 G1、serve_code_verdict 已有 STALE CODE 判据可顺势挂『tree-watch 不新鲜 ⇒ issue』）值得一张小卡或并入既有 `mw-dispatch-reliability` 地界。

### N-02（中低）achieved.md「验证入口」计数陈旧：照跑必得不同数字

- **现象**：验证入口写 `vitest … 期望 23 + 9 pass`、`pytest … -q 期望 72 pass`。当前 HEAD：decide 测试 **25** 例（W-10 追加处方 allow 2 例，`decide.test.ts:407/:432`）、四文件 **73** 例（W-09 在 `test_tree_watch.py:149` 追加 `test_collapse_event_carries_same_window_link_delta` ⇒ tree_watch 现 20 例）；另 W-09 新建 `test_tree_watch_doctor.py`（11 函数、其中 1 个参数化 13 项 ⇒ 23 项）与 W-11 的 `scripts/detach-node-modules-link.test.mjs`（7 例）均不在入口清单里。QG S-11/S-12 的计数在**其时点**为真（72=37+14+2+19、23+9），W-09/W-10 落地后未回写。
- **反例坐标**：`achieved.md` 验证入口段 vs `test_tree_watch.py:149`、`worktree-junction-guard-decide.test.ts:407/:432`、`test_tree_watch_doctor.py`（11 函数 + `:225` parametrize 13 项）、`scripts/detach-node-modules-link.test.mjs`。
- **影响**：复核者按入口照跑会得到 25+9 / 73（或 84），与记录不符 ⇒ 误判为回归或假证据；这是 QG 之后新落地工件造成的**文档时效债**，非假证据。
- **建议动作**：achieved.md 验证入口更新为现行数字（25 + 9；73 或直接写五文件 84 + scripts 8），并补 `test_tree_watch_doctor.py` 与 scripts 测试两行。
- **是否建议新 key**：否（PM 文档面一行）。

### N-03（低）design §3.2 `basis` 词表缺 `delete-penetration`

- **现象**：D-11 扩动词面后实现新增 basis 值 `delete-penetration`（`WorktreeGuardVerdict` docstring `:59-61`；decide:327 断言 `basis === "delete-penetration"`），design §3.2 的接口词表仍是旧 8 值清单（`resolved | unresolved:<var> | glob | bare-name-ambiguous | reparse-point | target-absent | scan-error:<code> | not-remove`）。
- **反例坐标**：`design.md` §3.2 接口注释 vs `worktree-junction-guard.ts:59-61`。
- **影响**：规格词表与实现漂移；后续按 §3.2 写校验/统计的人会漏一类 verdict。
- **建议动作**：design §3.2 词表补一行 `delete-penetration`（与 F-03/F-04 同类的文档修订）。
- **是否建议新 key**：否。

### N-04（低）注册表损坏在 doctor 文本面零可见、不产生 issue

- **现象**：`worktree_registry.read_registry` 对坏文件抛 `WorktreeRegistryError`（fail-closed，符合 design §5.1）；但 doctor 消费端把它折进 `scanned.registry_error` 后**既不打印也不算 issue**：`_registry_domain` 返回 error（`worktree_doctor.py:152-166`），`format_doctor_text` 只在 `count>0` 打印 leftover/stale（`mw_common.py:4025-4033`），`_doctor_issues` 的 worktree 块不消费 `registry_error`（`mw_common.py:3760-3775`）。⇒ 注册表损坏 = 注册表域检查静默失效（人工 `mw doctor` 文本面看不出任何异常，rc 不变），仅 `--json` 的 `scanned.registry_error` 可见。
- **反例坐标**：`worktree_registry.py:74-78`（「绝不静默当空表」的自述）vs `mw_common.py:4025-4033`（无 registry_error 行）。
- **影响**：与「绝不静默」承诺在消费端形成张力；注册表损坏时 leftover 检查全部丢失而人不知情。低概率（写入走锁 + tmp + 读回验证）。
- **建议动作**：`format_doctor_text` 给 `registry_error` 一行（或 `_doctor_issues` 记一条 suggestion）；或在工作tree-doctor 文档明示「损坏仅 --json 可见」为接受的降级。
- **是否建议新 key**：否（一处小改或一行声明）。

### N-05（低）`.mw/tree-watch.json` 无锁 + 多 launcher 交错采样

- **现象**：`write_state` 只有 tmp+`os.replace`（原子，无锁；`tree_watch.py:434-460`）；每个 launcher 进程独立计 poll 数、却共享同一状态文件。launcher 多实例是真实形态：`.mw/` 有 **27 个** `launcher-beat.<pid>`。两个 launcher 并行时，A 的 `evaluate` 可能拿 B 写的基线算 delta（漏报或误报窗口），且 `PI_TREE_WATCH_SEC` 只在各自进程环境里生效。
- **反例坐标**：`tree_watch.py:434-460`（无锁）vs `.mw/launcher-beat.*`（27 个 pid 文件）。
- **影响**：常态单 launcher 无影响；N-01b 修复（serve 重启）后如果出现新旧 launcher 交叠窗口，首个样本可能对错基线。检测面（非删除面）问题。
- **建议动作**：登记遗留；可选小改——状态文件按 pid 命名或加 `mw_common.acquire_lock` 包采样（复用既有锁原语，符合「不新写锁」纪律）。
- **是否建议新 key**：否（遗留表一行即可；若做激活态判据卡可顺带）。

### N-06（中低）pi 的 `!`/`!!` 用户直敲 bash 通道无任何守卫，spec INV-1 措辞与事实不符

- **现象**：pi 的用户直敲命令（TUI `!`/`!!` 前缀、RPC 同事件）走 `emitUserBash`（`interactive-mode.ts:6270-6278` → `runner.ts:955-985`），不经 bash 工具、不触发 `tool_call`。G1 只挂 `tool_call`（`worktree-junction-guard.ts:179-190`）；全仓 grep **无任何** `.on("user_bash")` 注册（protected-config / implementation-gate / xkey 等也都没挂）。⇒ 在 pi 窗口里人手输入 `! git worktree remove --force <含链 wt>` 会绕过 G1 直达 shell。
- **反例坐标**：`runner.ts:955-985`（emitUserBash 契约：handler 返回 result 即短路执行——**技术上可拦**）vs `worktree-junction-guard.ts:179`（只挂 tool_call）；spec INV-1「含 reparse point 的 worktree **没有任何执行通道**能把它连同目标一起删掉」。
- **影响**：这是一条 pi 内部、事件契约明确支持拦截、且与事故命令完全同构的通道；INV-1 的绝对措辞在它上面不成立。缓解因素：10-09 事故形态是 agent 直写（tool_call），本通道需人手输入，且修复成本低（`decideWorktreeRemove(event.command, event.cwd, process.env)` 可直接复用，返回合成 error result 即短路）。
- **建议动作**：二选一：(a) 给守卫补 `user_bash` 挂钩（约 15 行 + 1 个用例，`emitUserBash` 的 ctx 有 cwd）；(b) 修订 spec INV-1 / design §3.1 边界声明，明写「用户直敲通道不在覆盖面」。
- **是否建议新 key**：若走 (a)，建议并入本 key 收口前的一张小卡（或 PM 直改）；不建议为 (b) 单独立 key。

---

## 对既有 QG 报告的复核意见

### 确认项（不改判）

1. **13/13 ✅ 的坐标抽验全部成立**：Q-001..Q-013 引用的实现/测试坐标在本轮独立枚举中全部可定位且内容相符（decide/coverage 双层、worktree_cmd 六步与三分类、registry 原子写、doctor 三处挂载 + `import` 循环回归（`test_worktree_doctor.py:438`）、tree_watch 判据公式（`max(20, floor(1%·n+0.5))`，`tree_watch.py:107-116`）、launcher 挂点（`:1714-1729/:1886`）、G5 finally、mw parser 契约）。QG 的判据是**证据链闭合**，该判据下无误判。
2. **反假抽样的重验**：QG S-01..S-16 中我独立重验 10 条全部相符——S-04（lockfile `"link": true` 直数恰 14 = 9 `@earendil-works` + 5 `pi-extension-*`，本轮直接复算一致）、S-09（`index.ts:70` 调用、`:62-69` 注释块）、S-10（`.on("tool_call")` 恰 7 处）、S-07/S-08（阈值公式与 6-poll/`PI_TREE_WATCH_SEC=0` 语义）、S-13（`.mw/` 无 `worktree-registry.json`，本轮 ls 复核）、S-14（launcher 挂点）、S-15/S-16（mw.py/mw_common 挂载区间）、S-05（两套文本坐标）。未发现任何「声称有证据而证据不存在」。
3. **F-01/F-03/F-04 已修**（achieved.md `:70` ✓、design §3.3 (c) 已对齐实现（尾分隔符 fail-closed）✓、design §5.1 文件名 ✓）；**F-02/F-05/F-06 已落地**（W-09 窗口升级 + 常量 + 消费点逐字相符；W-11 模块三态结构 + 接缝 + `diff-model-catalog` 接线相符；W-10 处方 allow 2 例存在且含尾分隔符误拼 pin）。派发卡的「已处理清单」与仓库一致。

### 推翻 / 修正项

1. **修正 S-11/S-12 的计数（= N-02）**：`72 passed`（四文件）与 `23 + 9`（vitest）在**当前 HEAD** 分别为 73 与 25 + 9。QG 记录时点为真（W-09/W-10 尚未落地或未计入），非假证据；但 achieved.md 收口文本沿用旧数，构成文档时效债。QG 若被再次引用，应注明计数时点。
2. **推翻「13/13 ✅ ⇒ INV-1/INV-4 运行时达成」的隐含推论（= N-01，本轮核心差集）**：QG 的引用闭包方法以卡片文件清单 + 证据自述坐标为入口，**未检查部署产物与常驻进程**。运行时证据反向：两份扩展 bundle 均无 G1（H-28）、常驻 serve STALE CODE 且零采样（N-01b）。即：QG 的每一条 ✅ 都对，但「不可达 + 可机器发现」这两个**不变量**层面的验收，在审计时刻的运行面上不成立——这正是本任务「以仓库为入口求差集」补上的那块。建议 QG 报告由 PM 附一行勘误（引用本报告 N-01），无需重做。
3. **补充 QG「二次印证」第 1 条（G1/G2 同版本）**：QG 验证的是「同工作树共存」；本轮进一步确认 G1 的**加载面**单点依赖全局 bundle（本项目 `.pi/extensions/` 无副本），同版本承诺的实际执行者是 `mw build --install`，而该步未发生（N-01a）。

---

## 未覆盖面声明

- **只读角色，不能执行命令**：所有实跑结论（pytest/vitest/`npm run check`/`node --check`/真机 git 与 doctor 计数/夹具复演/穿透性实验）**无法独立复现**，一律 `[无法独复现]`；本报告只做坐标与内容一致性核对，以及运行时**产物**（bundle 内容、状态文件存在性、日志行）的只读核对（这部分不是实跑，是盘面证据）。
- 本审计**不覆盖**：Windows 环境既有测试基线失败（AGENTS.md 记载 89 例 + `test_launcher.py` 语料缺失 1 例）；其它 key 的孤儿目录与在飞改动；`spec/design/achieved` 之外的文档措辞；性能与容量（除 G4 采样缺失这类功能性问题）；跨仓（本仓之外）；serve 进程 49540 **此刻是否存活**（无法 tasklist；但「无 post-G4 launcher 完成过任何采样」由 tree-watch.json 缺席 + 零 TREE-WATCH/sample-skipped 日志行在内容层面坐实，与进程存活与否无关——若 serve 已死则 G4 同样失效）；`PI_TREE_WATCH_SEC=0` 显式关闭的可能（无任何配置痕迹支持该解释，且与 doctor STALE CODE 证据相悖，但不能完全排除）。
- **残留小项（不构成新发现，登记备查）**：`cmd /c rmdir "<link>/"`（尾分隔符误拼处方）的 guard verdict 已实测 allow（W-10 pin），但**该形态本身的穿透性**未在本 key 任何证据中实测（in1 只测了无尾分隔符 `cmd rmdir`；RQ-1 的尾分隔符穿透实测针对 `rm -rf`/`Remove-Item`）。机制上 `rmdir` 无 `/S` 不递归，低危；若求完整可补一条对照实验。

---

## 上下文来源

- 卡片：`tasks/T-W12-negative-space-audit.md`、worker 卡 `workers/wjg-w12-negative-space-audit/task.md`（mw-write-surface v1、mw-dispatch-card v1）。
- 被审基准：`spec.md`（AC-001..013、D-1/D-2/D-9..D-12）、`design.md`（§3.1-§3.6、§4.3-§4.4、§5、§6.1-§6.2、§7、§9）、`achieved.md`（系统行为变化 / 遗留 / 验证入口）。
- 实现：`packages/coding-agent/src/extensions/agent-team-loop/{index.ts, shared/worktree-junction-guard.ts, shared/bash-segments.ts, worker/worker-mode.ts}`、`core/extensions/{runner.ts, types.ts}`、`modes/interactive/interactive-mode.ts`、`packages/multi-workers/{worktree_cmd.py, worktree_registry.py, worktree_doctor.py, tree_watch.py, mw_common.py, mw.py, launcher.py}`、`scripts/{diff-model-catalog.mjs, detach-node-modules-link.mjs}`。
- 测试：`test/suite/worktree-junction-guard-{decide,coverage}.test.ts`、`test/suite/agent-team-loop-bash-segments.test.ts`、`packages/multi-workers/test_worktree_{cmd,doctor,e2e}.py`、`test_tree_watch{,_doctor}.py`、`scripts/detach-node-modules-link.test.mjs`。
- 对照证据：`evidence/quality-gate-report-20261013.md`、`evidence/T-W09-tree-watch-doctor-20261013.md`、`evidence/T-W10-prescription-allow-20261013.md`、`evidence/T-W11-detach-module-test-20261013.md`、`mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`。
- 运行时产物：`packages/multi-workers/dist/extensions/agent-team-loop.js`、`C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`、`.mw/{serve.meta, mw.pid, launcher.log, launcher-beat.*}`、`.gitignore`、`package-lock.json`、根/子 `package.json`、`.github/workflows/build-binaries.yml`、`.pi/extensions/`。
- 反假抽样：12 条（10 相符 / 2 条记录时相符现漂移），见「对既有 QG 报告的复核意见」与 N-02。

NEG-SPACE: 新发现 6 | 危害面路径 29（守住 10/不在覆盖面 17/未守住 2）| 该有而没有 6 | 有而无人引用 2 | 反假抽样 12 条
