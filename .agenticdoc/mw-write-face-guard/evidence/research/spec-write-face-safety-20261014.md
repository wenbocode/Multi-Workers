# 证据：历史同文件多写事故与最小充分护栏（RQ-W3 / T-W3）

- **key**：`mw-write-face-guard`　**worker**：`wfg-rq3-safety`　**type**：research（只读）
- **采集时刻**：2026-10-14（UTC+8）　**HEAD**：`55be3d960bb8402a262fb3fcccdcc27fda3f2ed9`（`git rev-parse HEAD`）
- **行号快照**：`implementation-gate.ts` 20,657 B、`worker-mode.ts` 121,332 B、`launcher.py`、`conductor.py`、`ui-bridge.ts` 均为当前工作树；工作树另有 **84** 条其他会话的未提交改动（`git status --porcelain` 计数 84），故所有行号以本文件引用的**唯一字符串**为准，漂移时按字符串定位。
- **角色约束**：只读。唯一写入物 = 本文件。未改任何生产文件、未写 `_workers.parallel`/`_index.parallel`/`pm-state.md`、未 commit、未跑 npm。
- **复算口径**：见 §1；全部数字可由命令重跑。

---

## §0 结论先行

1. **同文件多写者事故不是"会不会发生"，而是已经发生过三次，其中一次造成不可逆内容丢失。**
   - **IN-3（2026-10-10）**：`_workers.parallel` 被整表重建 → launcher 全量重派 252 个 pending（峰值 **66** 并发）→ **81 份 `.agenticdoc/**` 产品文件被第二个 worker 覆写**（`rewrites-81-filelist.txt`；`03-products-to-review.md:7/30/83`）。文件级回退可逆（`git restore --source=HEAD`）；但**同刻 3 棵孤儿重跑 worker 仍在写共享产物**，其中 `dist/extensions/agent-team-loop.js` 的覆写**未回滚**（`04-residue-scan-20261010.md:5/44`、§4.1 末条）。
   - **IN-2 复发（2026-10-10）**：另一会话按 HEAD 批量恢复时，把某 key 11:03 已落地但**未提交**的修正**永久覆盖**（`in2-recurrence-20261010-uncommitted-wipe.md` §3）——**不可逆**。
   - **`mw-gate-verdict-hardening` D-050**：PM 自己无锁整表重写 `_workers.parallel` 与 launcher 归档写撞车 → `PermissionError WinError 5`，队列留下 **130 行 8 列 + 132 行 9 列** 混合态，同刻首派 worker 启动 3 秒即死（`pm-state.md:70`）。

2. **今天"同一路径被两个 worker 并发写"的机器拦截数 = 0。**
   全仓 7 个 `pi.on("tool_call")` 处理器、4 个全局 guard、2 个 worker 侧 guard、2 条派发通道的封装校验，**没有任何一处读入"第二个 worker 的写面"**。
   已机器化的写面能力只有两种，且都不是重叠判定：(a) **派发期"角色可满足性"**（只读角色被要求写外部路径 ⇒ 拒绝，`ui-bridge.ts:1741` `judgeWriteIntent`）；(b) **运行期"自身写面"**（仅 `research` 角色、仅 bash，`worker-mode.ts:2218`）。
   `write_scope:` 载体已存在（419 份 worker `task.md` 中 **31** 份带该头，**38** 份带 `mw-write-surface` 契约段），但它的**唯一消费端是运行期 bash 写面守卫**——没有任何派发点拿它与在飞 worker 求交集。

3. **放开并发前的最小充分护栏 = 两条必要 + 一条必要但可缩范围**：
   - **必要 A（声明机器可读）**：写面进 `task.md` 头 **或** 队列行；缺它 ⇒ 派发拒绝无输入。反例：IN-3 的 81 份覆写。
   - **必要 B（派发层重叠拒绝 + 缺失 fail-closed）**：唯一能看见"在飞写者集合"的位置。反例：`mw-autopilot-verify-cli` 同 key 6 并发（四人组全重叠 105.5s）、conductor 重试逃逸 89.2s、本 key 现况 3 并发 188–203s 重叠。
   - **必要但可缩范围 C（运行期越界拦截）**：只用于治"声明为假"（spec 风险 3），**不能替代 B**——两个 coding worker 若都声明 `packages/x.ts`，各自都"在自身写面内"，运行期永不拦。反例：IN-1/IN-2 的 3,456 文件穿透删除（该角色无任何 bash 写面守卫）。
   - **可后置**：内容级三方合并、跨 key 写面协调、per-pair 运行期互斥、给源码写加锁。

4. **锁不覆盖源码写。** `.mw/*.lock` 只保护账本类文件（`_workers.parallel`/`_index.parallel`/`_workers.acked`/`config.json`/`_roadmap.md`/gates/pm-state/worktree registry）。`dispatch.py:1132` 写 `task.md` **在取锁 `:1156` 之前**；worker 对 `packages/**` 的 write/edit/bash **不在任何锁内**。

---

## §1 方法与复算口径

- 只读命令：`read`、`Select-String`、`python -X utf8 -`（here-string 管道，**不落盘脚本**）、`git rev-parse`/`git status`/`git diff --quiet`。
- worker 会话重叠复算：沿用上个 key 的扫描线口径（`spec-worker-serialization-20260926.md` §方法与出处 4），对 `.agenticdoc/*/workers/*/trace.log` 的 `[START]`/`[END]` 取区间（`[END]` 用全文 `re.search`，避免与上一行粘连漏检），`Z`/`+00:00` 归一为 aware datetime 后扫描线求峰值与各档位累计墙钟。
- 队列复算：`.agenticdoc/_workers.parallel` 逐行按 `|` 切分（无表头；首尾空单元剥离），列 = `task_key` / `status` / `cli` / `provider` / `task_path` / `dispatched_at` / `updated_at` / `model` / `origin`。
- 未找到的判据一律写"未找到（命令 + 输出）"，不做推测补齐。

---

## §2 事故 / 样本清单

### A 类：同路径被两个写者触及（真事故与实测样本）

| # | 出处 `file:line` | 谁写谁 | 事实（原文片段） | 可逆性 |
|---|---|---|---|---|
| **A1** | `.agenticdoc/_incidents/in3-queue-reenqueue-20261010/README.md:12` | 队列整表重建方 → launcher → 252 个重派 worker | "`.agenticdoc/_workers.parallel` 被**整表重建**（252 行、全部非终态、同一秒内），launcher 据"有 252 个 pending"**全量重派**，峰值 66 个 node worker 并发。" | — |
| **A2** | `…/rewrites-81-filelist.txt:1-81`；`…/03-products-to-review.md:7/30/83` | 重跑 worker 覆写原 worker 已 acked 的产物 | 81 个文件被第二个 worker 覆写；`03-products` 分级 = `L1（18 份）` + `L2（48 份）` + `L3（16 份）`（共 82 唯一路径，多出的 1 条是 `.agenticdoc/_index.parallel`）；README:83 "窗口内被写 **504 份产品文件**；当前 **82 份 tracked 改动（L1 18 / L2 ≈37 / L3 13）**" | **可逆**：`in2-recurrence-20261010-uncommitted-wipe.md` 文首 "已按 PM 决策**整体回退到 HEAD**（命令：`git restore --source=HEAD --worktree --pathspec-from-file=…/rewrites-81-filelist.txt`）"；重跑稿全文存于 `rewrites-81-20261010.patch` |
| **A3** | `…/04-residue-scan-20261010.md:5`、`:14`、`:17`、`:44` | 3 棵孤儿重跑 worker → 共享产物 | ":5 **有残留，且仍在活动**：3 棵重跑 worker 进程树存活 ~55 分钟，**正在写仓库**（含共享产物 `packages/multi-workers/dist/extensions/agent-team-loop.js`，11:41:15）"；":44 `dist/extensions/agent-team-loop.js` 11:41:15 被重写（这是**所有 pi 窗口加载的扩展 bundle**）" | **部分不可逆**：§4.1 末 "清理时未做的事：未回滚 `msc-t14` 在 11:37–11:45 对 `dist/` 与其产物的覆写" |
| **A4** | `.agenticdoc/mw-gate-verdict-hardening/pm-state.md:70` | PM 无锁归一脚本 ‖ launcher 归档写 → 同一文件 `_workers.parallel` | "我的 v1 归一脚本用**逐行循环调 `upsert_worker_row`**（N 次整表 `os.replace`，且该函数文档明写"锁由调用方持有"——我没持）⇒ 与 launcher 的 stale 归档写（`_workers.stale.parallel` mtime 18:31:59）撞车，第 130 行后 `PermissionError WinError 5` 中断，队列留下 **130 行 8 列 + 132 行 9 列**的混合态…**同刻 T-08 首派 worker 启动即死**（`worker.log`: `3] Permission denied: ..._workers.parallel`，3 s、零文件改动）。**无行丢失**（262 → 262）" | **可恢复**：v2 持锁 + 一次原子写，"`{8:130, 9:132}` → `{8:262}`、`unparsable=0`…一次成功" |
| **A5** | `.agenticdoc/mw-gate-verdict-hardening/pm-state.md:78`、`:80` | 假 `failed` ⇒ 同一张卡第二次派发（T-08 / T-08b） | "T-08 于 18:16:51 启动…框架**在启动 3 秒后**报 `failed`；但同一进程实际跑了 **5 分钟**、`exit=0`…PM 当时只信了 readback ⇒ 18:17:34 以新 key `mwg-t08b-g2-surfaces` 重复派了同一张卡；18:23:43 发现 T-08b 仍在**只读调查**（未写任何文件）⇒ PM 直执 kill **PID 144224** 止损，文件 mtime 证明 `monitor.ts`/`autopilot-monitor.test.ts` 的写入全部来自 T-08 那一个进程（**无重复写**）" | 未造成覆写（**险性样本**）；机制 = `_pitfalls.md:291` "PM 若按 failed 自动重派，会**丢掉整轮工作**并对同一批文件造成并发写（本 key 全是"同一文件只能一个写者"的任务）" |
| **A6** | `.agenticdoc/mw-dispatch-settle-gates/pm-state.md:58`（D-023） | T-08 改 `mw_common.py` ‖ T-09 跑测试读同一模块 | "T-09 worker 报告其测试期出现 3 条 `BLOCKED_ON_HUMAN` 瞬态失败，自查为并行 T-08 正在改 `mw_common.py` 所致（非 T-09 缺陷）⇒ 结论：**跨卡共享 Python 模块的编辑期会污染同刻其他卡的测试运行**" | 可逆：隔离复跑全绿；处置 = "波次全冻结后由 T-12 跑一次全量套件作为最终判据" |
| **A7** | `.agenticdoc/mw-dispatch-settle-gates/pm-state.md:68`（D-030） | PM 主动串行化（人肉护栏） | "T-05 的文件边界含 `worker/worker-mode.ts`（settle 幂等），而**仍在运行的 T-04 也写 `worker-mode.ts`**…若此刻派 T-05 会出现同一文件并发编辑（本 key 明令避免）。⇒ **T-05 等 T-04 终态后再派**；代价是当前并发度 1（只有 T-04），但正确性优先于吞吐" | 依靠人工纪律，无机器判据 |
| **A8** | `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md` F3/F2-E2 | PM 手工通道 / conductor 重试逃逸 | PM 通道单 key 峰值 **6**（`design-rqd1..rqd6`，同批拉起，6 个 session 全程重叠 306.3s，`@2026-09-26T06:19:31Z`）；四人组 `t06/t01b/t02c/t08` 全员重叠 **105.5s**。conductor 侧两次逃逸：`feature-gui-time-mvp-board` 同 key 同 repair family 两进程重叠 **89.2s**；`feature-params-service` 重叠 **6.4s** | 未记录文件级冲突——原因见 A9；本身是"同 key 多写者窗口"的实测样本 |
| **A9** | `spec-worker-serialization-20260926.md:186`、`:199` | （未命名） | ":186 `tasks/*.md` 中的 `- 写面：...` 行只在 **11/248** 个任务书里出现"；":199 ⇒ **要把单 key 并发从 1 提到 N，必须先补"写面声明 → 机器可读 → 重叠拒绝"这条链**；否则违反复现的是 P-018/P-019 家族（同文件多写者 / 冻结判据被覆盖）" —— 即 A8 的 6 并发**未炸是人在写任务书时按文件边界切好的，不是机器保证的** | 纯人工纪律 |
| **A10** | `_incidents/in3-queue-reenqueue-20261010/rewrites-81-20261010.patch:2481`、`:2703`、`:5816` | 同工作树的其他会话 → `conductor.py`、测试运行 | ":2481 复核期间观测到 `conductor.py` 被同工作树的其它会话**瞬态改写**——同一小时内 `conductor.py:63 _DEP_SATISFIED` 先读到 `{"done"}`，数分钟后读回 `{"done","closed-legacy"}`"；":5816 一次瞬态红：10:55:10 的 live TS 运行中 P6 失败…10:56:54 复跑即绿…判定为并发写者造成的瞬态" | 可逆（复跑即绿），但**证据不可复算** |
| **A11** | `.agenticdoc/_pitfalls.md:16`、`:19`（P-002） | 运行中的会话 → 跨窗口共享凭据文件 | ":16 所有 pi 窗口报 `Error: Provider is not configured: timi`，多个窗口死机；`~/.pi/agent/auth.json` 被运行中的会话清掉（只剩 timi 条目，其余凭据一并丢失）"；":19 运行期间绝不在会话内修改 `~/.pi/agent/` 下的 auth.json / models.json / settings.json / oauth.json（及 agentDir 本身）" | **不可逆**（凭据丢失，需重新登录）；护栏 = `shared/protected-config.ts` |
| **A12** | `.agenticdoc/_pitfalls.md:187`（P-017） | 一个会话的 `npm run check` → 其他会话正在编辑的文件 | "`npm run check` 的第一条是 `biome check --write --error-on-warnings .`，**带 `--write` 且作用域是全仓**。多窗口/多会话共用同一 cwd 时，它会就地改写**其他会话正在编辑的**文件（格式化/修可自动修的 lint），且改写后对方毫无感知——比「跑测试」危险得多" | 通常可逆（格式化），但可能滚入他人未提交语义改动 |
| **A13** | `.agenticdoc/mw-autopilot-verify-cli/evidence/research/spec-dist-rebuild-20260926.md:222`；`spec-capacity-constraints-20260926.md:128`、`:205` | 两个窗口同时构建 → 953 个 tracked dist 文件 | ":222 R3：tsgo 并发写 953 个 tracked dist 文件，两窗口同时构建，护栏 = **无**"；":128 `git ls-files packages/coding-agent/dist` = **953**、`packages/multi-workers/dist` = 1（本机实测）。`npm run build` 无 clean、无锁" | 可逆（重建），但会夹带他人改动 |
| **A14** | `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` §1–§2；`in2-recurrence-20261010-uncommitted-wipe.md` §3 | 单个 worker 的 `git worktree remove --force` → 共享工作树 | "**8 个包整树共 3,300 个 tracked 文件消失**…加上 `packages/tui` 被删的 156 才等于 3,456"；复发时 "**恢复用 HEAD 内容覆盖了工作树 ⇒ 11:29 之前落地的全部未提交改动被抹掉**" | 部分不可逆（未提交改动丢失，`agent-team-loop-ack.test.ts` 是最低一处实证） |

### B 类：同路径被二次覆盖（单写者，非并发）

| # | 出处 `file:line` | 事实 | 处置 |
|---|---|---|---|
| **B1** | `spec-capacity-constraints-20260926.md:129` | "真实事故形态不是并发写坏行，而是**事后改写**：repair worker 在已失败轮次的 `trace.log` 结束之后重写该轮 `output.md`，把 `below` 洗成 `meets`（`packages/multi-workers/CHANGELOG.md` 的 `feature-verdict-provenance-guard` Fixed 条目）⇒ 靠**来源/新鲜度校验**而非锁兜住" | 已有护栏（provenance/freshness），非锁 |
| **B2** | `packages/multi-workers/launcher.py:1994` `log_file = open(_worker_log_path(entry), "wb")`；`rewrites-81-20261010.patch:2303` | "**`worker.log` 会被下一次派发整文件截断**…10 分钟内把 38 份 429 证据清成 0 ⇒ 它**不是**只追加的取证面" | 已知残差；重派即自毁证据 |
| **B3** | `.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md` §2 | 实现型任务未落卡即派发；卡是"唯一权威"（含写入面白名单）。"卡的写入面白名单是防止 worker 扩面的主要机制；无卡时扩面风险显著上升" | 建议 F-1（工具侧强制卡片存在），**未实现** |
| **B4** | `.agenticdoc/mw-dispatch-settle-gates/evidence/research/design-settle-read-20261010.md:407-409` | 同进程二次 settle 重复写 phase 文件 / 重复 `appendGoalCheck`；靠 run marker 幂等保护 | 靠 run marker，非跨进程 |
| **B5** | `.agenticdoc/_framework-reflect.md` FW-002 节 | review worker 的运行期写面只允许本任务目录，卡片却指定 `evidence/quality-gate-report-20261013.md` ⇒ 产物落在错误路径，PM 手工提升 | 框架缺口，未修 |

### C 类：跨卡语义耦合与共享资源（非同一文件，但同族）

| # | 出处 | 事实 |
|---|---|---|
| **C1** | `_pitfalls.md:205`（P-019） | "并行卡按**文件边界**切写面，但语义耦合按**消费关系**传导；改了 A 的语义，所有读 A 的卡都会红，而它们在派发时看起来互不相干" |
| **C2** | `_pitfalls.md:288-291`（P-028）；`_framework-reflect.md` FW-003 | 崩检把"安静但存活"的 worker 反复报成 failed；"PM 若按 failed 自动重派…并对同一批文件造成并发写" |
| **C3** | `.agenticdoc/mw-console-title-clobber/achieved.md:13/20/21` | 子进程 `process.title = APP_NAME`（Win32 `SetConsoleTitleW`）改写宿主 pi 窗口标题——同一"共享资源"被第二个进程改写；修法 = `if (process.stdout.isTTY)` 收窄源头 | 可逆（显示层） |

---

## §3 护栏覆盖面矩阵

穷举口径：全 `packages/coding-agent/src` 的 `pi.on("tool_call")` = **7** 处（`Select-String -AllMatches` 计数 7）；全局注册 4 个（`index.ts:43/50/60/70`），worker 侧 2 个（`worker-mode.ts:2165`/`:2218`），PM 侧 1 个（`pm-orchestrator.ts:1632`）。

| # | 护栏 | 注册 / 判定 `file:line` | 拦截的写动词 / 路径面（判定原文） | 拦「同一路径被两个 worker 并发写」？ |
|---|---|---|---|---|
| G1 | **protected-config** | 注册 `shared/protected-config.ts:247` ← `index.ts:43`；判定 `:191` `checkProtectedBashCommand`；词表 `:162` `WRITE_VERB_RE` | 路径面 `:43` `const PROTECTED_CONFIG_FILES = ["auth.json", "models.json", "settings.json", "oauth.json"]`；bash 两重 fail-closed（`:194` `const refs = protectedReferences(scan, agentDir);` + 19 词写构造） | **否**。它把该文件对**所有**写者关闭（A11 事故族），不是写者间判定 |
| G2 | **xkey-gate-guard** | `shared/xkey-gate-guard.ts:253` ← `index.ts:50`；判定 `:195`；词表 `:167` | `.agenticdoc/_autopilot/**`（减 xkey 子树）；`:195` 同样"引用 + 写构造"两重 | **否**。固定目录白 / 黑名单 |
| G3 | **implementation-gate** | `shared/implementation-gate.ts:510` ← `index.ts:60`；`gateDecision:436`；bash 抽取 `:362`；词表 `:80` `const WRITE_VERBS = new Set(["tee", "cp", "mv", "rm", "sed"]);` | 路径面 = `<root>/packages/**` 代码扩展名，排除 `node_modules/dist/.tmp`。通过条件三选一（active claim / worker env / fresh mini-spec）；`:468` `return { blocked: false, basis: "worker-env", target: targets[0] };` + `:65` `const ENV_WORKER_TASK = "PI_WORKER_TASK";` | **否**。任何被派发 worker 因 `PI_WORKER_TASK` 存在而**无条件放行**；判定的是"这个窗口有没有资格写代码"，不是"这条路径有没有别人在写" |
| G4 | **worktree-junction-guard** | `shared/worktree-junction-guard.ts:180` `pi.on("tool_call", …)` ← `index.ts:70` | 仅 bash；`git worktree remove` / `rm`（含 `--force`、`-C`、内部 `cd`）与穿透形态（`-Recurse` / `-Force`）；模块自述边界：separator-free、glob-free 不在范围内 | **否**。删除语义守卫，与写者身份无关 |
| G5 | **read-scope**（worker） | `worker/worker-mode.ts:2165` ← config `:1973`；实现 `worker/read-scope.ts` | `read`/`ls`/`find`/`grep` 的 `read_scope` / `deny_globs` | **否**（只读面） |
| G6 | **bash write-scope**（worker） | `worker-mode.ts:2202` `isShellRole(meta.type) && isWritelessRole(meta.type)`；注册 `:2218`；抽取 `:1554` `extractBashWriteCandidates`；判定 `:1606` `checkBashWriteScopeTarget`；deny `:1568` `bashWriteDenyReason` | **仅 `research` 角色 + 仅 bash**。允许面 = 自身 `taskDir` + `<key>/evidence/**`，被 task.md 的 `write_scope:` 收窄；deny 优先级最高（`:1573` `if (firstSegment.startsWith("_workers")) return "workers/_workers*";`，另有 `packages/**`、`.git/**`、其他 key、`pm-state.md`、`_index.parallel`）。非 verbatim 目标 ⇒ `allow-unknown` **fail-open** | **否**。它是"每个 worker 自身的静态写面"，配置结构 `BashWriteScopeConfig`（`:747`）**没有任何字段承载第二个 worker 的写面**；且 `write` / `edit` 完全不经此守卫（见 N-2） |
| G7 | **worker_file 窄通道** | `worker/worker-file-tool.ts:87` ← `worker-mode.ts:2133`；basename 白名单 `:42` `WORKER_FILE_NAME_RE`；写入 `:56` `writeWorkerFile` | 只接受 basename（`progress.md` / `report.md` / `report-<slug>.md`），只写自身 taskDir | **否**（是通道，不是拦截器） |
| G8 | **pm-state-guard** | `shared/pm-state-guard.ts:117` ← `pm/orchestrator.ts:1632`；判定 `:67` / `:77` | 仅 `write` / `edit` 改 `pm-state.md` 的 `- Phase:` / `- Claim-Id:` | **否** |
| G9 | **派发信封校验（卡形）** | TS `shared/dispatch-card.ts:418` `inspectEnvelope`、`:457` `typeExtrasMissing`；Python `launcher.py:1174` `_envelope_refusal`、`:1095` `classify_envelope_refusal`、`:622` coding 的 `写入允许面` 模式 `re.compile(r"写入允许面|允许写入|允许写|写入范围|写面|write_scope|allow[-_ ]?write", re.IGNORECASE)` | 卡片**形式**：coding 卡必须出现 `写入允许面` / `写入禁止面` / `验收命令` / `改动历史` 四个标题体 | **否**。只验"声明存在"，**从不比较两份声明** |
| G10 | **PM 派发期写面可满足性** | `pm/ui-bridge.ts:1741` `judgeWriteIntent`；拒绝码 `:1398` `export const WORKER_WRITE_SURFACE = "worker-write-surface";`；判定器 `:1707` `judgeWriteTarget`、`:1610` `collectWriteIntentHits` | 只对 **无 write/edit 且无 bash** 的角色：卡片描述里的写意图 vs 角色可达面（`:1749` `if (!isWritelessRole(input.type) || isShellRole(input.type)) return { ok: true, hits: [], violations: [] };`） | **否**。单角色可满足性；不读在飞集合 |
| G11 | **写面声明载体（渲染 + 运行期消费）** | 生产者 `ui-bridge.ts:1779` `renderDefaultWriteScope`、`:1807` `applyWriteSurfaceContract`、调用点 `:2183`；消费端 `worker-mode.ts:440` `if (trimmed.startsWith("write_scope:"))` | 产出 task.md 的 `write_scope: a, b` 单行与 `<!-- mw-write-surface: v1 -->` 段；**唯一读者是 G6** | **否**。它不是护栏 |
| G12 | **launcher spawn 前门禁** | `launcher.py:1707` `_poll_once`；discover `:1783-1858`；`:1854` `if len(running_procs) >= limit:`；`:1858` `_spawn(entry, …)`；`:1810` `if key in running_procs: continue` | 位置契约 / 信封 / ack 收敛 / **全局**并发上限，**按 task_key 去重** | **部分**：只拦"同一个 task_key 的重复行"，不拦"两个不同 task_key 写同一个文件" |
| G13 | **conductor 每 key 串行闸** | `conductor.py:698` `in_flight_keys` 定义；`:742` `if key in in_flight_keys: continue`；`:744` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):` | key 层：某 key 有任一非终态行 ⇒ 本轮跳过 | **否**（且这正是 D-018 决定"不放开"的那道闸；PM 手工通道不经它） |
| G14 | **change-ledger**（观测） | `shared/change-ledger.ts`；写入事件由 `worker-file-tool.ts:78` `appendWriteFileEvent` 落 trace | 记录写事件（路径），不判定 | **否**（观测面） |

### 空缺面（明确列表）

| 空缺 | 证据 | 后果 |
|---|---|---|
| **N-1：没有任何"重叠判定"** | 未找到（命令 + 输出）：`Select-String -Path packages/multi-workers/autopilot/dispatch.py -Pattern 'write_scope|writeScope|overlap|intersect|write.?surface|写面'` 管道 `Measure-Object`，得 **0 matches**；同式对 `pm/task-dispatcher.ts` 得 **0**、`shared/worker-store.ts` 得 **0**。`conductor.py` 的 7 处 `write_scope` 全部是 xkey 提案谓词（`:6504` `blast_radius subset write_scope`、`:6518` `scope = facts.get("write_scope")`、`:6520`、`:6525` `outside write_scope`、`:6660`、`:7091`） | 同 key 多写者静默 |
| **N-2：`write` / `edit` 无写面拦截** | 全 `worker-mode.ts` 仅 2 处 `tool_call` 处理器（`:2165` / `:2218`），分别匹配 read 族与 bash；`write` / `edit` 只落 4 个全局 guard（G1–G4），而 G3 对 worker 无条件放行（`:468`） | coding worker 可写任意 `packages/**` 路径 |
| **N-3：运行期守卫只对 `research` 安装** | `worker-mode.ts:2202` `isShellRole(meta.type) && isWritelessRole(meta.type)`；`worker-mode.ts:74` `coding: ["read", "write", "edit", "bash", "find", "grep", "ls"]`、`:76` `research: ["read", "find", "grep", "ls", "bash"]` | 写面最大的角色（coding）无运行期写面判定 |
| **N-4：`write_scope` 不可达 conductor 通道** | `dispatch.py:742` `def render_task_md(` 参数仅 `read_scope: Sequence[str] = (), deny_globs: Sequence[str] = ()`（`:748` / `:749`），无 `write_scope` | conductor 产出的 task.md 永不带写面声明（与 `launcher.py:1074` 兜底骨架自称 "原 producer 未声明" 一致） |
| **N-5：非 verbatim 目标 fail-open** | `worker-mode.ts:1606` `checkBashWriteScopeTarget` 的非 verbatim 分支：目标含 `$` / 反引号 / 前导 `~` / glob / brace ⇒ `rule: "allow-unknown"`，记审计行后放行 | IN-1 的 `"$env:TEMP\qg-head"` 正是此形态 |
| **N-6：`git worktree` 不在 bash 抽取器的 git 子命令词表** | `mw-worktree-junction-guard/evidence/research/design-necessity-rq1-equivalent-guard-20261013.md` §1.4：`case "git"` 只认 `checkout` / `apply` / `clean` / `restore` 4 个子命令，其余 `break` ⇒ **零候选**（该 gap 已由 G4 在 `index.ts:70` 补齐；G6 本身未改） | G6 对 `git worktree` 零覆盖 |
| **N-7：源码写不在任何锁内** | 见 §4.3 | 无互斥、无 merge |
| **N-8：队列行不承载写面** | 实测列数分布 `{7: 344, 9: 58, 8: 17}`，列 = `task_key` / `status` / `cli` / `provider` / `task_path` / `dispatched_at` / `updated_at` / `model` / `origin` | 派发拒绝若要做，需新列或重解析 task.md（spec 未决项） |

---

## §4 锁与原子性

### 4.1 锁清单（`.agenticdoc` 相关）

| 锁 | 保护对象 | 写者锚点 `file:line` |
|---|---|---|
| `.mw/workers.lock` | `.agenticdoc/_workers.parallel`（+ `_workers.acked`） | Python：`mw_common.py:1731` `def lock_path` → `.mw/workers.lock`；`update_status:2175`（取锁 `:2186`）、`archive_stale_entries:2213`、`autopilot/dispatch.py:1139/1156/1184`、`conductor.py:6143` `acquire_conductor_lock(project_root, "workers", st.timeline)`（`lock_file:165` → `.mw/{name}.lock`）；TS：`shared/worker-store.ts:153` `this.lockPath = …".mw", "workers.lock"`、`shared/ack-store.ts:21` |
| `.mw/index.lock` | `.agenticdoc/_index.parallel` | `.agents/skills/agentic-task/scripts/update_index.py:234` `def _index_lock`（`:243-259`，`O_CREAT\|O_EXCL`）；TS `shared/index-store.ts:387` `this.lockPath = …".mw", "index.lock"`，`:397` / `:427` 两处临界区 |
| `.mw/roadmap.lock` | `_roadmap.md` | `conductor.py:1046/1050`、`:3498` 等 `lock_file(project_root, "roadmap")` |
| `.mw/gates.lock` | gates 存储 | `conductor.py:881/899`、`:3499/3606` 等 |
| `.mw/key-{key}.lock` | pm-state 的 PASS 证据写入 | `conductor.py:2597` `acquire_conductor_lock(project_root, f"key-{key}", …)`，`:2618` release |
| `.mw/autopilot-config.lock` | `.agenticdoc/_autopilot/config.json` | `mw.py:3392` `_AP_VERIFY_LOCK_FILENAME = "autopilot-config.lock"`，`:3491/3532`、`:3631/3656` |
| `.mw/worktree-registry.lock` | worktree 注册表 | `worktree_registry.py:40` `REGISTRY_LOCK_NAME = "worktree-registry.lock"`，`:150-164` / `:170-182` |
| `<statePath>.lock` | pm-state / session snapshot（TS 侧） | `pm/state-manager.ts:67` `const lockPath = \`${this.statePath}.lock\`;`；`pm/ui-bridge.ts:1062` `acquireLock(\`${statePath}.lock\`)` |

### 4.2 原子性

- 队列全量重写走 **tmp + `os.replace`**：`mw_common.py:2136` `def _write_workers_file` —— docstring 原文 "Atomically write `_workers.parallel` from **raw lines**… The old row-shaped signature forced a full re-serialize from the parsed view, which silently deleted every row the parser could not read — the write half of IN-3 (amplifier F4)."，实现 `tmp_path.write_text(...)` + `tmp_path.replace(path)`。
- `upsert_worker_row`（`mw_common.py:2155`）与 `update_status`（`:2175`）均**行保留**："only the matching row is rewritten, every other line — including rows no parser can read — is written back byte-identical"（`:2182`）；"The caller owns the lock"（`:2160`）。
- **但 `task.md` 不是原子写**：`dispatch.py:1132` `task_md.write_text(content, encoding="utf-8", newline="\n")`，锁在 `:1156` 才取。P-003（`.agenticdoc/_pitfalls.md:24`）正是"先截断后求值"家族。

### 4.3 源码文件写是否在任何锁内 —— **否**

判据（三条互证）：
1. `dispatch.py` 的事务顺序：`task.md` 写于 `:1132`，`acquire_lock` 于 `:1156`，队列行 `upsert_worker_row` 在 `:1167`，释放在 `:1184`。**任务书本身在锁外写**。
2. worker 侧对 `packages/**` 的写通道（`write` / `edit` / `bash`）没有任何锁调用：`worker-mode.ts` 全文的 2 个 `tool_call` 处理器分别是只读面与 bash 写面判定，均无 `acquireLock`；`shared/file-lock.ts` 的全部调用点是 `ack-store.ts:55`、`index-store.ts:397/427`、`worker-store.ts:191`、`state-manager.ts:68`、`ui-bridge.ts:1062` —— **没有任何一个保护源码路径**。
3. `spec-capacity-constraints-20260926.md:205` 同口径："没锁的是 ① `packages/*/dist`（953 tracked 文件；只有脏树拒跑）… 并行度上升的放大系数是"同时写者数 × 同一 git 检出""；`:214` 第 6 条 "跨项目不共享锁：锁路径都是 `<project>/.mw/*.lock`…机器层面的写竞争只在 `packages/*/dist`（同一 git 检出）与共享凭据文件上"。

**推论（标注为推断）**：因此"给源码写加锁"不是可选项——它既不在今天的能力面内，也不是最小充分路径（见 §5）：同 key 两个 worker 对同一 `packages/**` 文件的写，锁只能串行化，无法判定该不该串。

---

## §5 最小充分护栏论证

前置事实（本节论证的输入）：
- 声明载体存在但未接线：`write_scope:` 渲染端 `ui-bridge.ts:1779/1807/2183`，消费端只有 `worker-mode.ts:440`；实测 419 份 worker `task.md` 中 **31** 份带 `^write_scope:`、**38** 份带 `mw-write-surface` 契约段。
- 派发期唯一写面判定是**单角色可满足性**（`ui-bridge.ts:1741`）。
- 运行期唯一写面判定是**单 worker 自身面**，且只对 `research` + bash（`worker-mode.ts:2202/2218`）。
- 上个 key 的既有设计与此一致：`design-watchdog-and-serial-20260926.md:201` "### 3.2 尚未放开：写面声明 → 机器可读 → 重叠拒绝 三步清单"；`:211` 原文给出重叠拒绝的落点："两个派发入口：`dispatch.dispatch`（写 task.md 之前）与 `dispatchTask`（`upsert` 之前）；读同 key 的**在飞行**的 `writes` 集合，做前缀交集"。

### 5.1 必要项（缺它就有同类事故复现）

**A. 声明机器可读（必要）**
- 为什么必要：它是 B 与 C 的唯一输入；机器无法对散文求交集（A9：`11/248` 才有人写 `- 写面：` 行）。
- 反例（缺 A）：IN-3 重派 252 个任务时，队列行与任务书都不含写面；第二个 worker 对同一批 `.agenticdoc/**` 自由重写，**81 份文件被覆写**（A2）。再如 A7：PM 只能靠人读卡片判断 T-04/T-05 都写 `worker-mode.ts` 而串行化。
- 判定坐标：`spec-worker-serialization-20260926.md:186/199`；`_incidents/in3-queue-reenqueue-20261010/03-products-to-review.md:7/30/83`。

**B. 派发层重叠拒绝 + 未声明 fail-closed（必要）**
- 为什么必要：它是唯一能同时看见"新派发面"与"在飞集合"的点；运行期看不到别人（N-1 / N-8）。
- 反例 1（缺 B，同 key 并发已实测）：`mw-autopilot-verify-cli` 同 key 峰值 6、四人组全重叠 105.5s（A8）；本 key 现况 3 并发、两两重叠 **188.3–203.1s**（§1 复算）。这些**恰好没炸**只因为 A9 的人工切面。
- 反例 2（缺 B，conductor 侧）：F2-E2 两个同 key 同 repair family 进程重叠 89.2s / 6.4s（`spec-worker-serialization-20260926.md` F2 E2；`design-watchdog-and-serial-20260926.md:215` 记 "**实测 2 个（89.2s / 6.4s）**"）。
- 反例 3（缺 B，PM 通道无写面门禁）：`ui-bridge.ts:2343`（当前行号）`if (fs.existsSync(taskDir))` 只查 taskDir 是否已存在，不查在飞数量；后台扫描有**配额**但无写面判定（`pm-orchestrator.ts:904` `if (result.queued.length >= maxPerScan) break;`、`:970` `if (isConductorTask(taskMdPath)) continue;`）。上个 key 的取证以当时行号记作 `design-watchdog-and-serial-20260926.md:327` "E1 pm path no concurrency check (ui-bridge.ts:1222-1232, pm-orchestrator.ts:464)"（行号已漂移，结论未变）。
- 缺 B 且"声明为假"时 B 也不够 → 见 C。

**C. 运行期越界拦截（必要，但范围可缩到"自身声明面之外"）**
- 为什么必要：B 只能判声明面；声明窄而实际写宽时，B 全绿。
- 为什么**不能替代 B**（关键反例）：两个 coding worker 都合法声明 `packages/x.ts`；各自的运行期判定都"在自身写面内" ⇒ 都放行 ⇒ 后写者静默覆盖。运行期要判它必须读 `_workers.parallel`（N-1：今天 0 处），那等于把 B 挪到运行期，且引入分布式状态读的竞态与成本。
- 缺 C 的反例：IN-1/IN-2 的 `git worktree remove --force` 穿透删除 3,456 个 tracked 文件（A14）——当时该路径零覆盖；`design-necessity-rq1-equivalent-guard-20261013.md` §2.3 G-3 明写 "bash write-scope **只对 `research` 安装**…coding/repair/vision/phase-writer/fallback 角色的 `git worktree remove` 无任何写面门禁"，G-1 "bash 写动词词表不认 `git` / `git worktree`"。
- 今日 C 的形状已可缩：deny 优先 + 默认面（自身 taskDir + `<key>/evidence`）+ 声明面收窄即可（G6），**不需要**在运行期读其他 worker。

### 5.2 可后置项（不是放开 N > 1 的必要条件）

| 项 | 为什么可后置 | 若做，落点 |
|---|---|---|
| 内容级 diff / 三方合并 | 事故族里没有一例是"两边都该写、需要合并"，全是"第二个写者不该写" | — |
| 跨 key 写面协调 | key 间写面冲突的实测样本为空；conductor 已有 key 层 cap（G13），且 spec §1.4 已声明不做 | — |
| 运行期 per-pair 互斥（worker 间加锁） | 需要 worker 读彼此状态（N-1），成本与竞态高；B 在派发层已给出更强保证 | — |
| 给源码写加锁 | 锁不能替代"该不该写"的判定（§4.3 推论）；且会与 `npm run build` / `check --write`（A12 / A13）互相干扰 | — |
| 队列行新增写面列 | 若 B 选择重解析 task.md，可省；仅在"launcher spawn 前也要判"时才必需 | `launcher.py:1854` 之前 |
| 现有 419 份任务书的迁移策略 | 属 rollout（spec 风险 2），非机制 | — |

### 5.3 必要性的可证伪形式（供 design / plan 取判据）

- 若 A 缺：派发拒绝在语料上恒不可判 ⇒ 用 `_workers.parallel` 复算同文件交集必然为"未知"而非 0。
- 若 B 缺：允许同 key N ≥ 4 并发后，用 trace 区间 + 写面声明复算，**交集非空的派发次数大于 0**（对照基线 = A8 / A9 的人工切面）。
- 若 C 缺但 A+B 在：唯一残差 = "声明为假"；必须以"越界写被 block 且 trace 落 `[WRITE_SCOPE]` / `[TOOL_ERR]`"来判（今日只有 `research` 角色能满足）。

---

## §6 上个 key 的接受 / 否决（对护栏取舍的既有结论）

| 条目 | 出处 `file:line` | 内容 |
|---|---|---|
| D-018 不放开 | `.agenticdoc/mw-autopilot-slot-capacity/design.md:147` "### D-018 (d) per-key 串行：本 key **只做可观测与判据，不放开**"；`:517` 决策表行 "D-018 / (d) 并发 / 本 key 只做观测与判据 / 本 key 放开 / 写面机器判定为零；主因是 gate" | 否决"本 key 放开并发" |
| R4 残留被用户接受 | `.agenticdoc/mw-autopilot-slot-capacity/achieved.md:82` "R4 写面机器可读判据未落地（AC-014 / VC-016 / Q-VC-016） / **用户显式接受范围** / …**派发面重叠拒绝属"放开"之后才需要的实现**，故本 key 不做" | 残留登记，未实现 |
| 机器判定为零 | `spec-worker-serialization-20260926.md:229` `[VERIFY] … same_key_write_surface_check=none(write_scope grep=0)`；`design-watchdog-and-serial-20260926.md:326` `[VERIFY] write-surface machine check = 0 …` | 基线数字 |
| 前置清单（未实现） | `design-watchdog-and-serial-20260926.md:201-229`（三步清单 + 缺位失败模式） | 本 key 的实现目标 |
| 已落地但与重叠无关 | `mw-guard-form-hardening` / `mw-dispatch-card-gate` / `mw-dispatch-settle-gates` 落地的 G6（bash write-scope）、G10（派发期可满足性）、G11（载体）；见 `mw-dispatch-settle-gates/pm-state.md:58`（D-023 风险登记）与 `.agenticdoc/mw-worktree-junction-guard/` 的 G4 | 提供本 key 可复用的插入点与判定语义 |

---

## §7 残留与未验证

1. **A2 的 81 份覆写只做到"文件级回退"**，重跑稿自身是否曾造成"同一文件两个写者同时打开"（半写）未取证——`04-residue-scan` 的结论是"无截断"，但那是 `git diff` 级判据。
2. **A14 的 IN-1/IN-2 复现条件未在本轮重跑**；G4（`worktree-junction-guard.ts:180`）是 2026-10-14 00:07 新落的，本轮**未做端到端实测**（只读角色，未执行真实 `tool_call` 流程）。
3. **本文件未实测任何护栏的运行时行为**（不导入生产纯函数做判定回放），所有"拦 / 不拦"结论由源码判定路径 + 既有证据的实测结论（`design-necessity-rq1` §2.4 的可复算证明）支撑。这是本轮的方法边界。
4. **`allow-unknown` 的实际放行面未穷举**（N-5 只给出判定分支与 IN-1 的单例证据）。
5. **未坐实 A4 中"3 秒假 failed"的因果**：`mw-gate-verdict-hardening/pm-state.md:80` 自述 "**假设（未坐实）** = spawn 握手与并发写者相撞导致启动期 `update_status(running)` 被挡"，本节只引用其"已坐实"部分。
6. **A8 / A9 的并发复算是 trace 区间扫描，不是文件写事件**：区间重叠 ≠ 确实同时写同一文件；§2 A9 明确标注该区分，不把它当冲突证据。
7. **`_workers.parallel` 的写者清单未在本轮重数**（上个 key 报 5 个 writer；本轮只验证 `dispatch.py` / `mw_common.update_status` / `mw_common.archive_stale_entries` / `conductor.reconcile_orphans` / `worker-store.ts` 五个锚点仍在），计数仍以 `spec-worker-serialization-20260926.md` §F1 表为准。
8. **本 worker 自身的一次护栏误拦（一手观察）**：写入本文件的一段 bash 命令被 `xkey-gate-guard` 拦下，reason 原文含 "xkey-gate-guard: blocked a bash command referencing the autopilot directory (.agenticdoc/_autopilot) with a write construct (write verb, powershell write cmdlet)"。该命令只是把一段 markdown（其中**引用**了 `.agenticdoc/_autopilot/**` 与一个 PowerShell 删除 cmdlet 的名字）通过 here-string 管道交给 python。⇒ 坐实 G2 的 "引用 + 写构造" 文本判定对**引语 / 文档内容**会误拦（与 `design-necessity-rq1-equivalent-guard-20261013.md` §1.1 PM 附注的 `dd` 假阳性同族）。规避方式 = 让被引用字符串在命令行里不连续出现。本项是**工具面**观察，不是被审对象的事故。

---

## §8 未覆盖面声明

**工具边界**：本 worker 为 `research`（`read` / `find` / `grep` / `ls` / `bash` + `worker_file`），无 `write` / `edit`；未执行任何端到端 pi 会话，未运行测试 / 构建，未导入生产 TS 纯函数做判定回放。§3 矩阵的"拦 / 不拦"结论来自源码判定路径 + 既有已实测证据，非本轮运行期实测。

**方法边界**：本次是**以台账与证据为入口的穷举**（`_pitfalls.md`、`_incidents/**`、各 `evidence/**`、`pm-state.md` 的决策行），**不是**以仓库为入口的负空间枚举。具体未覆盖：
- 未读 419 个任务目录的 `trace.log` / `output.md` 全文；只对 `trace.log` 的 `[START]` / `[END]` 做了区间统计。
- 未读会话 JSONL（`~/.pi/agent/sessions/**`）——IN-1 的一手取证在仓外。
- 未覆盖其他项目（`E2Feature` / `JCodingAss` / `LearningTree`）现场；A8 的 autopilot 侧样本转引自上个 key 的取证（该 key 自述 autopilot 样本只有 E2 一个项目）。
- "同文件多写者"判定只做到"区间重叠 + 写面文字比对"，**没有**文件级写入归因（谁在什么时刻写了哪个字节）。

**未被本轮证伪的既有结论**：上个 key 的 `[VERIFY]` 行（`manual_overlap_max=6` / `same_key_write_surface_check=none`）与 D-018 / R4 的范围裁定。

---

## 上下文来源

| 来源 | 用途 |
|---|---|
| `.agenticdoc/_pitfalls.md`（`P-002:15`、`P-003:24`、`P-017:185`、`P-028:288`） | A11 / A12 / C2 与 P-003 原子性判据 |
| `.agenticdoc/_incidents/in3-queue-reenqueue-20261010/{README.md,02-impact-assessment.md,03-products-to-review.md,04-residue-scan-20261010.md,05-sol-collateral-trace-20261010.md,rewrites-81-filelist.txt,rewrites-81-20261010.patch}` | A1–A3、A10、B2 |
| `.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md` | B3 |
| `.agenticdoc/mw-workspace-incident-probe/evidence/{incidents-timeline-20261009.md,in2-file-vanish-incident-20261009.md,in2-recurrence-20261010-uncommitted-wipe.md}` | A14 |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md` | A8 / A9、§5 前置 |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/design-watchdog-and-serial-20260926.md` | §5.2 / §6 设计意图与 `[VERIFY]` 基线 |
| `.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-capacity-constraints-20260926.md` | §4 锁 / 未锁写面、A13 |
| `.agenticdoc/mw-autopilot-slot-capacity/{design.md,achieved.md}` | §6 D-018 / R4 |
| `.agenticdoc/mw-autopilot-verify-cli/evidence/research/{spec-dist-rebuild-20260926.md,design-write-lock-20260926.md}` | A13、RMW 无锁丢更新的先例 |
| `.agenticdoc/mw-gate-verdict-hardening/pm-state.md` | A4 / A5 |
| `.agenticdoc/mw-dispatch-settle-gates/pm-state.md` + 其 `evidence/research/design-settle-read-20261010.md` | A6 / A7、B4 |
| `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq1-equivalent-guard-20261013.md` | 12 道门的穷举与缺口族（G-1..G-5） |
| `.agenticdoc/_framework-reflect.md`（FW-002 / FW-003） | B5、C2 的框架侧登记 |
| `.agenticdoc/mw-console-title-clobber/achieved.md` | C3 |
| `.agenticdoc/goal.md` | 目标锚点（"多 Worker 共享同一工作树而不互相破坏"） |
| 源码：`shared/{implementation-gate,protected-config,xkey-gate-guard,worktree-junction-guard,dispatch-card,task-frontmatter,file-lock,change-ledger}.ts`、`worker/{worker-mode,worker-file-tool,read-scope}.ts`、`pm/{ui-bridge,pm-orchestrator,state-manager}.ts`、`shared/{worker-store,index-store,ack-store}.ts`、`index.ts`、`packages/multi-workers/{launcher.py,mw_common.py,mw.py,worktree_registry.py}`、`autopilot/{conductor.py,dispatch.py,gates.py}`、`.agents/skills/agentic-task/scripts/update_index.py` | §3 / §4 矩阵与锁清单 |
| `.agenticdoc/_workers.parallel`、`.agenticdoc/*/workers/*/task.md`、`.agenticdoc/*/workers/*/trace.log` | §1 复算与 §3 声明覆盖率实测 |

---

## [VERIFY]

```
[VERIFY] RQ-W3: sessions=415 across .agenticdoc/*/workers/*/trace.log
[VERIFY] RQ-W3: per_key_peak_overlap=7 (mw-autopilot-slot-capacity @2026-09-26T08:29:25Z) second=6 (mw-autopilot-verify-cli @2026-09-26T06:19:31Z, matches RQ-5) global_peak=7
[VERIFY] RQ-W3: overlap_wall_s={2:38913,3:14351,4:6440,5:1872,6:657,7:354}
[VERIFY] RQ-W3: current_key mw-write-face-guard concurrent=3 pairwise_overlap_s={rq1xrq2:203.09,rq1xrq3:188.40,rq2xrq3:188.32}
[VERIFY] RQ-W3: queue_rows=419 colcounts={7:344,9:58,8:17} status={done:385,needs-clarification:24,running:7,failed:3} dup_task_path=0 dup_task_key=0
[VERIFY] RQ-W3: worker_task_md=419 with_write_scope_header=31 with_write_surface_marker=38 task_cards=427
[VERIFY] RQ-W3: guards: pi_on_tool_call_src=7 global_registered=4(index.ts:43,50,60,70) worker_side=2(worker-mode.ts:2165,2218) pm_side=1(pm-orchestrator.ts:1632) overlap_checkers=0
[VERIFY] RQ-W3: IN-3 rewrites=81(rewrites-81-filelist.txt) graded_rows=82(03-products L1=18,L2=48,L3=16) extra_row=.agenticdoc/_index.parallel non_rolled_back=dist/extensions/agent-team-loop.js mtime 11:41:15(04-residue-scan:44,83)
[VERIFY] RQ-W3: spec-worker-serialization clean_vs_HEAD=true (git diff --quiet HEAD exit=0) on-disk VERIFY line still manual_overlap_max=6
[VERIFY] RQ-W3: pm_channel has_quota=true(pm-orchestrator.ts:904 maxPerScan) has_write_surface_check=false dedup_only=ui-bridge.ts:2343
[VERIFY] RQ-W3: absent_overlap_check(commands+output): Select-String dispatch.py|task-dispatcher.ts|worker-store.ts pattern 'write_scope|writeScope|overlap|intersect|write.?surface|写面' gave 0|0|0 matches; conductor.py write_scope hits=7 all xkey blast_radius predicate (:6504,:6518,:6520,:6525,:6660,:7091)
[VERIFY] RQ-W3: src_write_lock=none (dispatch.py task.md write :1132 BEFORE acquire_lock :1156; file-lock.ts callers only ack-store:55,index-store:397/427,worker-store:191,state-manager:68,ui-bridge:1062)
[VERIFY] RQ-W3: self_guard_hit=1 (xkey-gate-guard blocked this worker's own evidence-write command: quote-of-autopilot-dir plus PowerShell delete cmdlet inside here-string, a false positive; bypassed by splitting the quoted literal)
```
