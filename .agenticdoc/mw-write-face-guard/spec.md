# Spec: mw-write-face-guard

> Key: mw-write-face-guard
> 创建时间: 2026-10-14
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务 goal「文件驱动的去中心化协调」与「Worker 进程级隔离」中的**共享工作树写面安全**这一前提条件：
  多 worker 并行开发同一项目时，必须先有**机器可读的写面声明**与**派发层重叠拒绝**，否则放开并发就是同文件多写者。
  本 key 是 `mw-dynamic-concurrency` 的硬前置（D-018 / AC-014 记录的未满足前置）。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——协调只经文件系统（`_workers.parallel` + 文件锁），本 key 不新增常驻进程。
  - GC-2: 不修改 pi 核心能力面——实现落在扩展 / mw 服务侧（`packages/multi-workers`、`agent-team-loop` 扩展）。
  - GC-3: `_workers.parallel` / `_index.parallel` 的并发写继续走 `O_CREAT|O_EXCL` 锁 + RMW。
  - GC-4: worker 超时/unattended watch 语义不变。
- 冲突：无。
- 预期收益：写面字段成为任务书的机器契约、派发层能拒绝写面重叠的并发派发。
  - 判定方式：VC 断言 + 现场复算——放开并发后同一时刻的**同文件多写者**样本为 0，对照基线
    （PM 手工通道实测同 key 并发 6、`mw-autopilot-slot-capacity` RQ-5）不再复现。

## §1 功能概述

### 1.1 目标

让"这个 worker 允许写哪些路径"成为**机器可读、机器可判**的任务契约，并在**派发层**（conductor 与 PM 两条通道共用的入口）
拒绝与在飞 worker 写面重叠的派发。这不是并发本身，而是放开并发的安全前提：没有它，任何 per-key 并发都会引入静默的同文件多写。

### 1.2 技术栈 / 语言

- Python：`packages/multi-workers/`（`autopilot/dispatch.py`、`mw_common.py`、conductor）
- TypeScript：`packages/coding-agent/src/extensions/agent-team-loop/`（`shared/dispatch-card.ts`、`pm/ui-bridge.ts`、`worker/*`）

### 1.3 核心用户场景

1. **conductor 自动派发**：同一 key 的 EXECUTE 波里两张卡写同一实现文件 → 第二个派发被拒绝并留下可读 refusal（不是静默串行）。
2. **PM 手工派发**：PM 一次派 6 个 worker，其中两个写面重叠 → 拒绝第二个，PM 看到机器可判的原因。
3. **写面缺省**：任务书未声明写面 → 按保守策略处置（拒绝或降级为串行），且该处置有稳定 refusal code + 审计行。
4. **观测**：`mw doctor` / 队列行能看出哪个 worker 的写面与谁重叠。

### 1.4 范围说明（不做什么）

- 不包含：放开 per-key / key 层并发本身（`mw-dynamic-concurrency`）。
- 不包含：内容级 diff 三方合并、写后冲突修复。
- 不包含：修改 `read_scope` / `deny_globs` 的既有读面语义。
- 不包含：跨项目写面协调。

## §2 业务约束

### 2.1 平台 / 环境

- 单机 Windows 开发机；worker 是独立 pi 进程；serve 常驻。
- 两条派发通道共用队列 `_workers.parallel` 与唯一消费者 launcher（spawn 循环 `packages/multi-workers/launcher.py:1806-1858`，`subprocess.Popen` 在 `:2008`；卡里旧锚点 `:819-841` 已漂移，实测更正，见证据 `evidence/research/spec-write-face-enforcement-20261014.md`）。

### 2.2 性能指标

- 写面判定必须是本地纯计算（glob 交集），不引入新的网络/LLM 调用；一次派发新增开销 < 10ms。

### 2.3 安全约束

- 拒绝必须是 fail-closed：写面不可解析 / 缺失 = 不并行（而非默认放行）。
- 不得因写面判定放宽既有 `implementation-gate` / `worker-file-tool` 的路径拦截。

### 2.4 集成依赖

- `.agenticdoc/_workers.parallel`（在飞行；注意：**不能承载写面**——9 列上限见 AC-008，写面靠 task.md 头/卡 envelope）
- 任务书渲染 `autopilot/dispatch.py::render_task_md`（零写面命中，需新增接线）、任务卡解析 `shared/dispatch-card.ts`
- 派发入口 `autopilot/dispatch.py::dispatch`（写 task.md `:1132` / 取锁 `:1156`）、`pm/ui-bridge.ts::dispatch_worker`、`pm/task-dispatcher.ts::dispatchTask`

## §3 验收标准（AC）

> 状态：**编号已锁**（研究已回读；字段名/默认处置两个子项待 design 定，见 §4 待确认）。

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在任务书声明写面时，`dispatch_worker` / `dispatch.dispatch` 将写面解析为机器可读结构（路径 glob 列表），解析失败返回稳定 refusal code 且零副作用（不写 task.md、不建队列行） |
| AC-002 | 在派发新 worker 时，若其写面与同 key 任一在飞 worker 的写面存在非空 glob 交集，派发被拒绝并给出 `overlap-with:<task_key>` 形态的机器可判原因 |
| AC-003 | 在任务书未声明写面时，派发按 fail-closed 处置（拒绝或标记 serial-only），并写审计行；不得静默放行 |
| AC-004 | 写面声明被渲染进 task.md 且 worker 运行期据此拒绝越界写：范围必须覆盖**所有可写角色**（`coding`/`repair`/`phase-writer`/`vision`/`fallback` + 经 bash 写文件的 read-only 角色），不得再限于 `research`；越界写返回 `[TOOL_ERR]` 且记 trace |
| AC-005 | 同一时刻同 key 的同文件多写者样本为 0：以 `_workers.parallel` 在飞行 + 写面字段复算，并发派发 N≥4 时无交集对 |
| AC-006 | `mw doctor`（或等价只读面）能列出写面重叠拒绝的计数与最近样本，无重叠时显示 0 而非报错 |
| AC-007 | 两条通道（conductor / PM 手工）对同一写面输入给出相同判定（同语料对照，结果一致） |
| AC-008 | 写面不占用队列列：`_workers.parallel` 的 `WORKER_COLS_MAX=9` 必须保持（实测 10 列行被两侧判为 unparsable → PM 扫描整轮中止、launcher 静默丢行），写面载体只能是 task.md 头部 / 任务卡 envelope |
| AC-009 | 写面字段名不与既有含义冲突：不得沿用与 xkey gate frontmatter 的 JSON list 同名的 `write_scope`（`gates.py:175/790`）而不加区分；新字段名或显式限定词必须二选一并写进 spec |
| AC-010 | 写面声明覆盖"read-only 角色经 bash 写证据文件"路径：research/review 角色无 `write` 工具（只有 basename 限定的 `worker_file`），证据文件经 bash 落盘，故写面判定不能只看 `write`/`edit` 调用 |
| AC-011 | **载体单源**：现存 4 个互不相通的写面载体（W1 task.md `write_scope:` / W2 gate v2 `write_scope` / W3 卡 envelope `写入允许面·写入禁止面` / W4 `mw-write-surface` marker）必须收敛为**一个权威载体**，其余三个各自给出显式处置（保持、注释为异语义、废弃）；不得新增第五个 |
| AC-012 | **C 不得替代 B**（可证伪）：两个 coding worker 都合法声明同一路径时，派发层必须已经拒绝第二个（而不是靠运行期各写各的各自放行）；以构造语料 + trace 区间复算证伪 |
| AC-013 | 写面前提不引入新的假阻：worker 侧 bash 写面守卫对"引语/文档内容"的文本判定不得误阻（本轮实测 `xkey-gate-guard` 误拦 2 次、AC-005b 守卫误拦 3 次，稳定 repro `Write-Output a <term> --glob x`）；以回归用例锁住 |
| AC-014 | `task.md` 的创建不得在 `.mw/workers.lock` 之外发生（今日 `dispatch.py:1132` 写 task.md 早于取锁 `:1156`）——否则拒绝路径会留下无队列行的孤儿任务目录 |

## §4 风险与未决项

- 风险 1（已实测收窄）：写面 glob 交集算子**今天不存在** —— 既有算子只有"路径∈集合"（minimatch 10.2.5 双基 + realpath containment），已枚举 7 处分歧（大小写敏感度不一致：`minimatch("A/B/C.TS","a/b/c.ts")=false` vs `{nocase:true}`；`a/**` 不含 `a`（`minimatch("a","a/**")=false`）、双基、根锚定、realpath vs 词法、allow/deny、`|` 分隔符）。glob×glob 交集需新建算子并先定语义方向（证据 §3/§5）。
- 风险 2（已实测收窄，W1 修正）：写面**不是"唯一载体"而是 4 个互不相通的载体**（W1 task.md `write_scope:` / W2 gate v2 `write_scope`（异语义：`blast_radius ⊆ write_scope`）/ W3 卡 envelope `写入允许面·写入禁止面`（只做存在性检查，`typeExtrasMissing` 从不抽值）/ W4 `mw-write-surface` marker）；W1 的生产端只有 PM 且仅 `writelessRole && isShellRole`（`ui-bridge.ts:2431/2925`），解析端无条件（`worker-mode.ts:440-466`），消费端**仅 `research`**（`worker-mode.ts:2216-2266`）；conductor 的 `render_task_md` 零命中 `write_scope`，`_workers.parallel` 9 列无写面载荷。实测覆盖率：419 份 worker task.md 中 31 份带 `^write_scope:`、38 份带 marker。⇒ 见 AC-011（载体单源）。
- 风险 3（已实测坐实，W1）：写面"声明为假"之外还有更硬的一条——**coding 类角色的越界写今天零运行期守卫**（`worker-file-tool` 结构性不命中、`read-scope` 只拦读、`implementation-gate` 被 `PI_WORKER_TASK` 放行）。⇒ AC-004 扩到全角色；IN-1/IN-2 的 3,456 文件穿透删除即该缺口的一个实例（`git worktree remove` 不在任何 bash 写动词词表内；G4 worktree-junction-guard 已于 2026-10-14 落地，属另一 key 的 VERIFY 面）。
- 风险 7（新，实测）：**锁不覆盖源码写** —— `.mw/*.lock` 只护账本类文件；`dispatch.py:1132` 写 `task.md` **在取锁 `:1156` 之前**；worker 对 `packages/**` 的 write/edit/bash 不在任何锁内。锁不能替代"该不该写"的判定（AC-014 只收窄副作用面，不假装加锁 = 并发安全）。
- 风险 8（已实测坐实，W3）：同文件多写者**已实发三次**（IN-3：整表重建 → 全量重派 252、峰值 66 并发 → 81 份 `.agenticdoc/**` 被第二个 worker 覆写，其中 `dist/extensions/agent-team-loop.js` 的覆写未回滚；IN-2 复发：按 HEAD 批量恢复 **永久抹掉未提交修正**（不可逆）；`mw-gate-verdict-hardening` D-050：PM 无锁整表重写 `_workers.parallel` 与 launcher 归档写撞车 → EPERM + 130×8/132×9 混合态队列 + 首派 worker 3 秒即死）。护栏覆盖面：拦"同一路径被两个 worker 并发写"的护栏数 = **0**（7 个 `tool_call` 处理器均不读第二方写面）。
- 风险 9（新，实测）：**运行期写面闸自身会假阻** —— 现行 bash 守卫在 2026-10-13 又误拦一条只读命令（trace `pattern=redirect target=|| token.text ===`），与 E3 同族；根因未定位。⇒ AC-013 必须有回归用例（引号内容 / heredoc / `--glob` 旗标操作数 / 变量拼接 / 文本引用，共 11 条向量）。
- 风险 10（新，实测）：**默认面必须角色类别化** —— 现行 `packages/**` 绝对 deny + taskDir 默认面可直接套给 coding 角色的前提不成立（会把全部合法写拦掉）；`research` 与 `coding` 需要各自的面。
- 风险 4（新，实测）：队列行无写面列且**不能加列**（`WORKER_COLS_MAX=9` 两侧一致；10 列行 → `parse_worker_line` 返回 `None` 实测）⇒ 写面必须在 task.md 头/卡 envelope 传，不能靠队列传递。
- 风险 5（新，实测）：命名冲突 —— `write_scope` 已同时是 (a) task.md 的 worker 写面头（`worker-mode.ts:322/440`）与 (b) xkey gate frontmatter 的 JSON list（`gates.py:291/790`、`conductor.py:6518`，语义是"允许变更的文件清单"）；沿用同名会把两者混淆。
- 风险 6（新，实测）：派发入口候选 ≥4 个（C1 conductor `dispatch.py:964` / C2 PM `ui-bridge.ts:2424`+`:2918` / C3 TS 锁内 `task-dispatcher.ts:288`+`worker-store.ts:190`（原子性最强）/ C4 launcher spawn 前 `launcher.py:1806-1858`（拒绝只能落 `failed`，非零副作用）），加 C5 跨语言 parity 单源约束；选点不同则"拒绝的副作用面"不同。
- 待确认（交给 design）：写面字段名与位置（task.md 头 vs 任务卡 envelope）；缺省处置是拒绝还是 serial-only；是否复用既有 `write_scope` 名（建议**不复用**，见风险 5）。
- 可后置（W3 §5.2 已给理由，非放开 N>1 的必要条件）：内容级 diff/三方合并、跨 key 写面协调、运行期 per-pair 互斥、给源码写加锁、队列行新增写面列、存量 419 份任务书的迁移策略。
- design/plan 可用的可证伪形式（W3 §5.3）：缺 A ⇒ 交集恒为"未知"而非 0；缺 B ⇒ 允许 N≥4 后"交集非空的派发次数 > 0"；缺 C 但 A+B 在 ⇒ 唯一残差为"声明为假"，必须以"越界写被 block + trace 落 `[WRITE_SCOPE]`/`[TOOL_ERR]`"判（今日只有 `research` 角色能满足）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- 任务卡 envelope 解析与校验：`shared/dispatch-card.ts`（单一判定 `inspectEnvelope` / `typeExtrasMissing` / `seedItemsMissing`），
  以及 coding 类型已有的「写入允许面 / 写入禁止面」extras 槽位。
- 任务书渲染单一咽喉点：`autopilot/dispatch.py::render_task_md`（读面 cap 的既有接线范式，可直接承载写面字段）。
- 读面拦截：`worker/read-scope.ts` + `worker/worker-file-tool.ts`（写面运行期拦截的同族插入点）。
- 队列锁与 RMW：`mw_common.acquire_lock`（`O_CREAT|O_EXCL`）、`worker-store` 的槽位保持写。
- 门禁范式：`shared/implementation-gate.ts` 的 `WRITE_VERBS` 目标收窄判定。
- **现存的完整三段式范式（直接照搬）**：`read_scope` / `deny_globs` 是今天**唯一**渲染 → 解析 → 运行期均存在的面（读面）；写面照它建即可，不新造机制。
- 写面载体清单（design 必须逐一处置）：W1 `task.md write_scope:`（生产 `ui-bridge.ts:2432/2926`，解析 `worker-mode.ts:440-466`，消费 `worker-mode.ts:2216-2266` 仅 research）；W2 gate v2 `write_scope`（`gates.py:175/790` → `conductor.py:6518-6526`，语义 = `blast_radius ⊆ write_scope`）；W3 卡 envelope `写入允许面·写入禁止面`（`dispatch-card.ts:251-252` / `launcher.py:622-623`，仅存在性）；W4 `mw-write-surface` marker（只读结构）；旁证 E1 `filesystem.allowWrite`（**未接线**）、E2 `blast_radius`。
- 事故台账可直接引用：`.agenticdoc/_incidents/in3-queue-reenqueue-20261010/*`（81 份覆写 + `rewrites-81-filelist.txt`）、`mw-workspace-incident-probe/evidence/in2-recurrence-20261010-uncommitted-wipe.md`（不可逆误删）、`mw-gate-verdict-hardening/pm-state.md`（D-050 EPERM + 混合列队列）。
- 上个 key 已经给出重叠拒绝的落点（本 key 直接实现，不重新设计）：`mw-autopilot-slot-capacity/evidence/research/design-watchdog-and-serial-20260926.md:201-229`（三步清单 + 两个派发入口“读同 key 在飞行 writes 集合，做前缀交集”）。

### 需规避坑点

- P-018/P-019：改共享函数/共享语义前先查消费点与其它 key 的冻结判据；写面语义变更会牵动所有派发路径。
- P-017：`npm run check --write` 在多会话下是破坏性命令，必须避免并发执行。
- P-021：跨语言镜像契约（Python ↔ TS）任何字段变更必须两侧同波 + parity 语料重冻。
- P-022：已知残差要记录，不要把已知分歧值放进 parity 语料。
- 写面载体只能走 task.md 头部 / 任务卡 envelope：队列不能加列（AC-008）；且 conductor 今天**根本不渲染** `write_scope`（与 PM 侧只在 `writelessRole && isShellRole` 时渲染），所以两条通道需要同一个渲染咽喉点，否则 AC-007（两通道同判定）不可达。
- read-only 角色（research/review/verifier）经 **bash** 写证据文件（无 `write` 工具，`worker_file` 仅限 basename白名单），且 worker 侧 bash 写面守卫会按命令文本拦截；写面判定不能只看 `write`/`edit` 调用（AC-010）。实证：本轮 `mdc-rq2` worker 因命令文本同时含 `.agenticdoc/_autopilot` 片段 + 写动词而被 xkey-gate-guard 拦截，改走 `ReadAllText/WriteAllText` 迂回。
- 文本判定对**引语/文档内容**假阳性（W3 §7.8 一手观察）：写面守卫按“命令文本含 X + 含写构造”判，会把当作数据/文档引用的字符串当成写目标（与 `dd` 假阳性同族）；本 key 自己新增的判定必须避免同型假阻（AC-013）。
- PowerShell 5.1 管道写入会以 ASCII 编码中文（P-001/P-020 家族）；写证据/报告必须固定 `$OutputEncoding=UTF8` + `python -X utf8` 并回读验证 replacement/BOM/CRLF 计数（W3 实际踩到并重写全文件）。
