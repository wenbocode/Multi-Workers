# Design: mw-write-face-guard

> Key: mw-write-face-guard
> Phase: DESIGN
> 上游: `spec.md`（AC 已锁 14 条）、`evidence/research/spec-write-face-{sources,enforcement,safety}-20261014.md`
> 状态: draft（决策 D-001..D-009 由 PM 依 spec 研究与用户确认起草；待 design 阶段调研回读后复核）

## §0 Goal Alignment

- 来源 `.agenticdoc/goal.md`：多 Worker 共享同一工作树而不互相破坏；文件驱动协调。
- 本 design 的判定面：**并发放开后同文件多写者对 = 0**（对照基线：IN-3 的 81 份覆写、IN-2 的不可逆误删、D-050 的 429 行混合态队列）。
- 不做（spec §1.4）：并发本身、内容级合并、跨 key 协调、读面语义变更。

## §1 架构（三层护栏 + 单载体）

spec 研究（RQ-W3 §5）已证明最小充分集是 A/B/C 三条必要项，且 **C 不能替代 B**：

```
作者面（人/PM 写卡）                        运行期
   │                                           │
   ▼                                           ▼
[卡 envelope 写入允许面]              [worker-mode 写面闸]
   │  (authoring, 唯一人读面)            │  全可写角色 + bash 写目标
   ▼                                    │  G1 deny 优先 → G2 默认面 → G3 声明面
[task.md 头 write_face:]  ──解析──► 写面结构
   │                                    ▲
   ▼                                    │
[派发层重叠闸]  =  B                      │
   conductor dispatch.dispatch           │
   PM dispatchTask / WorkerStore.upsert  │
   （判定 + append 同一临界区）           │
```

- **A 声明机器可读**：权威载体 = task.md 头部 `write_face:`（一行 glob 列表）；作者面入口 = 任务卡 envelope 的「写入允许面 / 写入禁止面」槽位（`shared/dispatch-card.ts` 已有槽位，今天只做存在性检查）。
- **B 派发层重叠拒绝**：两条通道各自在自己的入队点判定；判定与 append 必须在 `.mw/workers.lock` **同一临界区**内。
- **C 运行期越界拦截**：扩到全可写角色（今天只有 `research`+bash），复用读面 `read_scope`/`deny_globs` 的三段式（渲染→解析→运行期）。

## §2 决策表

| # | 决策 | 取值 | 依据 |
|---|------|------|------|
| D-001 | 权威载体 | task.md 头部 `write_face:`（**三态**：缺头 = 未声明；有头但空 = 解析拒绝 `write-face-empty`；非空 = 正常）；卡 envelope「写入允许面」为作者面输入，渲染进 `write_face:` | spec 风险 2/5（4 载体互不相通；`write_scope` 撞名）；RQ-D1 §3.3；AC-011 |
| D-002 | 名字 | `write_face:`（不复用 `write_scope`）；gate v2 的同名字段在文档与代码注释中显式标注"异语义：`blast_radius ⊆ write_scope`"，不改其行为 | spec 风险 5、AC-009 |
| D-003 | 未声明处置 | **serial-only**（快照 `write_face = unknown`）：不得与同 key 任何在飞 worker 并行，但**不拒绝**派发；写审计行 `write-face-undeclared` | spec 风险 2（419 份存量卡）、AC-003 |
| D-004 | 队列 | 不加列（`WORKER_COLS_MAX=9` 保持）；在飞集合在判定时由 `_workers.parallel` 重算 | spec 风险 4、AC-008；实测 10 列行两侧判 unparsable |
| D-005 | 判定位置 | 两条通道各自：conductor = `dispatch.dispatch` 内、写 task.md **之前**，且 `task.md` 的创建移到取锁之后；PM = `dispatchTask` → `WorkerStore.upsert` 的现有锁内 RMW | spec 风险 7、AC-014；W2 §4 C1/C3 |
| D-006 | glob 交集算子 | 新建 `write_faces_overlap(a, b)`；语义 = **写面专用归一**（单一 `/` 语法、无前导/内嵌 `!`、无 `..`、无 entry 内 `,`；`a/**` **含** `a`；段内 `**`（如 `a**b`）按 `*` 处理不跨段；win32 大小写不敏感但**显式参数** `caseInsensitive` 传入；`dot:true`；base = 仓根；`\` 一律视为分隔符不转义；尾 `/` 去掉）。**判定里 deny 不参与**（RQ-D1 §3.2 定论）：`A.deny` 完全遮盖 `A.allow ∩ B.allow` 时**仍判重叠**——理由：把安全网当作放宽并发的证据是方向错误，且判断必须对 deny 单调（否则同一批卡在改一行 `target.yml` 后判出不同结果）；运行期 deny 优先（`read-scope.ts:167-183`）不变，两者是不同层面。判定可离线完成（正则编译 → glob∩glob → ε-NFA 乘积），**不枚举文件系统**。**禁止在 Python 侧用 `fnmatch` 做写面匹配**（`*` 跨 `/`、win32 `normcase` 折大小写，与 minimatch 不一致） | spec 风险 1；RQ-D1 §0/§2/§3.1/§3.2/§4（证据 `design-glob-intersection-20261014.md`；**本条已按 RQ-D1 修正原先写反的方向**） |
| D-007 | 运行期范围 | 全可写角色（coding/repair/phase-writer/vision/fallback）+ 经 bash 写文件的 read-only 角色；插入点 = **IP-1b**（留在 `workerModeActivate` 闭包：新增 `write`/`edit` 分支 + bash 条件由 `isShellRole && isWritelessRole` 放宽到 `isShellRole`，复用 `extractBashWriteCandidates`/`checkBashWriteScopeTarget`；meta 已缓存，零额外 I/O）；**自建一份写面 lexer，不复用 `implementation-gate` 的 target lexer**（后者目标是"仓库代码路径"，自述漏 `python -c`/预写脚本/`find -delete`/tar/PowerShell cmdlets）；`worker_file` 的 basename 白名单保持不变；**默认面/deny 面必须角色类别化**（今天的 `packages/**` 绝对 deny + taskDir 默认面直接套到 coding 会误拦全部合法写）；`research` 行为逐字保持 | spec 风险 3、AC-004/AC-010；RQ-D2（前一轮写错：design.md 的 D-007 需按此更新） |
| D-008 | refusal 面 | 稳定 code `write-face-overlap` + `overlap-with:<task_key>` + 冲突路径样例；零副作用（不写 task.md、不建队列行、不建 taskDir）；审计行写 `.agenticdoc/_autopilot/timeline.jsonl`（conductor 侧）与派发返回值（PM 侧） | AC-001/002/003 |
| D-009 | 两语言一致性 | 交集算子与字段解析各实现一次（Python + TS），共享同一份语料并 parity 锁（P-021）；不允许两套语义 | AC-007；P-021 |
| D-111 | 拒绝形状的优先级（PM 差分实测后裁定） | **parse 期：硬规则违规优先且与条目顺序无关**（`write-face-escape` / `write-face-invalid-entry` / `write-face-outside-base` 是确定性违规，不受「先遇到一个不受支持语法条目」遮蔽；不受支持条目只记录，不截断后续校验）。**overlap 期：先证冲突，证不出再看有没有不受支持语法**——能给出 glob-free witness 就返回 `Conflict`，否则任一侧含不受支持语法返回 `Unsupported`（D-006 的「任一触发即判重叠」在调用方仍然成立：两种形状都拒绝）。裁定依据：① 用「无法判定」遮蔽「确定违规」会让拒绝 code 成为条目**书写顺序**的函数，违反 D-006 的单调性；② `Unsupported` 的语义应是“判不出来”，不是“判得出来但懒得给 witness”。实测来源：`evidence/PM-parity-differential-20261014.md`（600 随机向量 4 处分歧 + 10 例定位矩阵）；**allow/refuse 决策两侧本来就零分歧**，本条只锁拒绝形状 | AC-007；P-021；语料新增 P17–P23 / V49–V57 |
| D-112 | 条目切分（PM 差分二轮裁定；同时修正我第一版语料里 P21 的错误期望） | 头部值先按 `split(',')` 切字段，逐个 trim 后各自解析；**切分语法无感**——`[` / `{` / 引号都不保护逗号，**未闭合的 `[` 不得吞掉后续字段**（实测 Python 现状把 `src/[a-, src/ok.ts` 合并成单个 entry，丢掉了一个已声明的有效条目）。反面同样成立：`{` 未闭合时逗号仍切分（`src/{a,b` → `["src/{a", "b"]`），碎片 `b` 是合法字面量、只会**增加** allow 条目 ⇒ 误差方向是 fail-closed。放弃“括号感知切分”的理由与 D-110 同族：多一条语法感知规则就多一个 fail-open 面，而收益为零。P16（`"a,b"`）在本规则下仍得 `write-face-invalid-entry`（首字段 `"a` 先被拒） | AC-007；P-021；语料 P21/P22/P23 |
| D-113 | 载体往返恒等 | 渲染器必须满足 `parse(render(entries)) == entries`。D-112 把逗号定为无条件分隔符，故含逗号的合法条目（V20 `a/{b,c}/**`）不能用单行承载 ⇒ 任一条目含逗号时改用 §3.1 允许的 **block-list** 形态。实测：`render_write_face_line(["a/{b,c}/**"])` → `write_face: a/{b,c}/**` → 回读得 `["a/{b", "c}/**"]`（非恒等；方向 fail-closed 但声明面被静默改写）。两侧渲染器（conductor W-03 / PM 侧）都必须锁这条；证据 `evidence/PM-roundtrip-probe-20261014.md` | AC-011/AC-014 |

## §3 接口

### 3.0 现状事实（RQ-D1 实测，决定归一取值）

- 仓内已有 **5 套** "字符串/路径匹配"实现：`M1 isSameOrUnder`、`M2 isWithinScope`、`M3 matchedDenyGlob`（`worker/read-scope.ts:89/118/141`）、`M4 matchesWriteScopeEntry`（`worker/worker-mode.ts:1564/1587/1598`）、`M5` Python `fnmatch`（`packages/multi-workers/autopilot/xkey.py:1084`）；**glob×glob 交集算子不存在**（全仓 `overlap|intersect` 仅 2 处散点命中）。
- **主要分歧 = `*` 是否跨 `/`**：`fnmatch("a/b/c.ts","a/*.ts")=True`（Python 侧）vs minimatch 10.2.5 `=False`（TS 侧）。⇒ 语义基准取 **minimatch**；Python 侧必须自写匹配器，不得用 `fnmatch`。
- **同一字符串在三处不同待遇**：`read_scope` allow = 纯词法 glob（`read-scope.ts:118-121`）；`write_scope` = 必含 glob magic（`GLOB_MAGIC_RE`）；`deny_globs` = minimatch（`read-scope.ts:141-146`）。新算子取 **minimatch defaults + 魔法字符归一**，并把全部归一写成显式参数（不做隐式“魔法分支”，RQ-D1 §3.1）。

### 3.1 载体格式

task.md **头部普通行**（与既有 `^write_scope:` 同区位，**不是** YAML frontmatter）：

```markdown
# <task title>

- 写入允许面: ...   （作者面；卡 envelope）

write_face: packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts, packages/coding-agent/test/suite/autopilot-console.test.ts
```

- 分隔符 `,`（与 roadmap `depends_on` 同构，去掉两侧空格）；**三态**（RQ-D1 §3.3）：缺头 = 未声明（D-003 serial-only）；有头但空 = 解析拒绝 `write-face-empty`；非空 = 正常。
- 可选 YAML 块列表形态与之等义（仅列表形式，语义相同）；相对仓库根；`**` 跨目录；不含盘符（绝对路径在 base 下则相对化，否则拒绝 `write-face-outside-base`）。
- `\` 一律视为分隔符（不转义）；尾 `/` 去掉；前导 `./`/空段归一掉。

### 3.2 判定 API

| 侧 | 函数 | 返回 |
|---|---|---|
| Python | `autopilot.write_face.parse_write_face(text) -> 三态` / `overlap(a, b) -> str \| None`（返回冲突样例） | 解析失败 → 拒绝码（fail-closed）；不可判 → **判重叠**（保守回退清单，RQ-D1 §3.2） |
| TS | `shared/write-face.ts::parseWriteFace` / `writeFacesOverlap` | 同上 |

### 3.3 refusal 载荷

```json
{"code": "write-face-overlap", "overlap_with": "ap-<key>-<stem>", "sample": "packages/.../ui-bridge.ts"}
```

## §4 验证计划（VC）

| VC | 判据 |
|---|---|
| VC-001 | 交集算子语料：与 `read_scope` 同语义的向量集 + 边界（`a/**` vs `a`、大小写、`**` 中段、deny 优先）双语言一致 |
| VC-002 | 两通道同输入同判定（同语料过 Python 与 TS 入口，比较 refusal code 与 overlap_with） |
| VC-003 | 零副作用：被拒绝的派发不产生 taskDir/task.md/队列行（实测目录快照 diff） |
| VC-004 | serial-only：未声明写面的卡在存在同 key 在飞时被延迟（不进 `in_flight`，且不拒绝）；无在飞时正常派发 |
| VC-005 | 临界区：双进程对拍（或注入 sleep）下同 `task_key` 只产生 1 行 |
| VC-006 | 运行期：coding 角色越界 `write`/`edit`/bash 写目标被 block 并落 `[WRITE_SCOPE]` |
| VC-007 | 假阻回归：`Write-Output a <term> --glob x` 型命令不被写面闸误判（AC-013） |
| VC-008 | `mw doctor` 计数：无重叠显示 0，有拒绝显示计数 + 最近样本 |

## §5 风险与缓解

| 风险 | 缓解 |
|---|---|
| 存量 419 份任务书无写面 | D-003 serial-only（不中断派发）；提供一次性生成脚本把卡 envelope 的「写入允许面」渲染进 `write_face:`（可后置，见 spec 风险表"可后置"列） |
| 声明为假 | C 层运行期拦截 + `[WRITE_SCOPE]` 审计；不假装 A 够用 |
| 两语言漂移 | D-009 parity 语料 + 冻结计数（P-021/P-022） |
| 加锁粒度过大导致吞吐下降 | 只在入队临界区加一次交集计算（O(N_in-flight) 次 glob 比较，N 默认 ≤ 8）；不在 worker 运行期加锁 |

## §6 待确认 / 交给 design 调研

- RQ-D1：交集算子的最终语义与向量集（含 `read_scope` 现有实现的 7 处分歧如何归一）。
- RQ-D2：运行期全角色闸的插入点与 bash 写目标词法（复用 `implementation-gate` 的 target 侧 lexer 还是新写）。

## 追加裁定（2026-10-14，B1 收口后）

- **D-114（队列文件单写者）**：`.agenticdoc/_workers.parallel` 的任何写入**必须经由 `WorkerStore` 的同一实现**，包括在已持 `.mw/workers.lock` 时的写入路径。W-08 在 `pm/task-dispatcher.ts` 内复制了一份 `WorkerStore.upsert` 的字节镜像（`upsertQueueRowLocked`：9 列 ` | `、origin 末列、原地替换、`# mw-queue:v2`）以满足"判定与写行同一临界区"——判定与写行同临界区是**对的**（AC-008/AC-014），但复制写实现**违反 D-005 的精神**：行格式一旦在两侧漂移，队列文件就会出现两种合法形态，而解析器只有一份。**要求**：`shared/worker-store.ts` 暴露一个"已持锁时可用"的写入入口（命名如 `upsertWithinLock`，语义与 `upsert` 逐字节一致，只跳过取锁），`task-dispatcher.ts` 删掉镜像并改调该入口；不得以"结构化读私有字段"替代正式入口。跟进卡：`wfg-i09-queue-single-writer`。
- **AC-003 在 PM 通道的落地方式 —— 已裁定（2026-10-14，PM；取代本节原"未决"两条候选）**：采用 **(a')**：由调用方消费 `DispatchOutcome`，并把拒绝落成 `.agenticdoc/_autopilot/auto-decisions.jsonl` 的一行（复用**既有** `pm/pm-orchestrator.ts:556` 的 `recordDispatchAlarm`，`phase: "dispatch-alarm"` 家族，best-effort）。理由：**D-008 早就把 PM 侧的审计出口定为派发返回值**，缺的只是"有人消费它"；原候选 (b)（TS 另写 `.autopilot/timeline.jsonl`）会新增该文件的第二个写者并与 Python 侧的 timeline 轮转（`.1/.2`）冲突，代价与风险都高于收益。同一次修复顺带修掉计数不诚实：`pm-orchestrator.ts:1243→1254` 的"无条件 `queued += 1`"（`dispatchTask` 拒绝不抛异常）改为按 `ok !== true` 判定。落地卡：`wfg-i13-pm-refusal-audit`（T-W-I13）。原两条候选记录如下，仅供追溯：
：PM 通道今日对拒绝**不留任何持久审计记录**（事实与证据见 `plan.md` §7.3）。候选：
  - (a) 由 `pm/pm-orchestrator.ts` 消费 `DispatchOutcome`，在 PM 可见面（watch/日志）落一条拒绝记录。**阻塞点**：该文件正处另一 key（读回投递 scope）话题范围内，需等其释放写权。
  - (b) 在 TS 侧补一个 conductor 同形的 timeline 写入口（`.autopilot/timeline.jsonl`，事件名逐字同 `write-face-rejected`/`-overlap`/`-undeclared`），PM 拒绝直接落同一条时间线；与 (a) 不互斥。
  - PM 倾向 (b) 直接消除通道差异，但 (b) 会新增"谁写 `.autopilot/**`"的写者（今日只有 Python conductor 写），需先确认不与 `.autopilot` 的既有所有权冲突。

- **D-115（载体收敛：`write_face:` 为唯一权威 allow 载体，PM 裁定，AC-011）**：B2 落地后实测出集成漏洞——PM 通道渲染的是 `write_face:`，而运行期闸门只读 `write_scope:`，于是 writable 角色的声明面在运行期**完全失效**（只剩默认面 + deny 红线）。裁定：
  1. **`write_face:`（task.md 头，由卡 envelope 的「写入允许面」经同一渲染器生成）是唯一权威的 allow 载体**；两条派发通道共用它。
  2. **`write_scope:`（W1）= legacy 载体**：只对 **writeless 角色**（research）仍作声明面，逐字保持既有行为；writable 角色在**存在** `write_face:` 时以 `write_face:` 为准。
  3. 两者**同时存在且不等**时取**交集**（fail-closed，D-006 家族）并写一条审计行——交集使 legacy 载体只能收窄、不能放宽，也不允许出现两个载体给出两个不同允许集而无痕。
  4. writable 角色**没有** `write_face:`（存量卡未迁移）时回落到 `write_scope:`（只读兼容）；`write_face:` 的**生产端不再新增**（PM/conductor 渲染器已是唯一生产端，legacy 载体自然排空）。
  5. **不得新增第五个载体**。W2 gate v2 的 `write_scope`（异语义 `blast_radius`）与 W4 `mw-write-surface` marker 各自保持既有行为并**标注为异语义/仅标记**，不参与 allow 判定。
  6. **闸门安装条件补洞**：守卫必须覆盖"有 `write`/`edit` 工具"的角色（`hasWriteTools || isShellRole`），而不是只覆盖 shell 角色——`roadmap-writer` 这类 writable 但无 bash 的角色今天完全没有运行期闸门（W-10 残留 R3）；bash 子判定仍只在角色确有 bash 时启用。
  7. 书面口径变化（W-10 残留 R2）：`mwds-t03` 的 VC-024「coding/repair/vision 不装闸」与「summary 只给 writeless 角色」是 D-007 明确反转的**旧口径断言**，必须按新语义重写（"有闸且不误拦合法写"/"每个 shell 角色各一行 summary"），**不得删除或放宽**。
