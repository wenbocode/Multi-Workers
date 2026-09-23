# Spec: mw-target-partition

> Key: mw-target-partition
> 创建时间: 2026-09-19 00:05 (+08:00)
> 状态: confirmed（AC 已锁定）
> 修订记录: 2026-09-19 v2 —— 用户需求转向：多文件改**单配置文件 target.yml（模式块 + active 键）**，partition 保持独立命令族；同时吸收两份评审（design/spec review）处置：BLOCKER 级矛盾修正、parent 无写防火墙措辞、撕裂校验、根关系校验、roots 键名约束、v1 兼容与自动迁移。受影响 AC 按 [REVISED]/[OBSOLETE] 标注，新增 AC-017~AC-020、AC-022、AC-023（编号 021 未分配）。

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（存量项目，无 status 行，三段有真内容，视为已确立）

- 对齐：本 spec 服务于 goal「PM Agent 管理多个 Worker Agent 并行开发同一个项目」中的**适用面扩展**——把 worker 编排从 UE 项目（dual 词汇）推广到任意大项目的子目标拆分场景；文件驱动协调与 goal 锚点机制不变。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心，全部经扩展 API（TS）+ mw Python 实现（goal 原文约束）
  - GC-2: Worker 进程级隔离——partition 只改 spawn cwd 指向，不改隔离/看门狗模型（goal 原文约束）
  - SC-1（本 spec 新增约束，非 goal 继承）：target.yml 模式块 bootstrap 字段由 CLI 单写者管理，写盘原子
- 冲突：无
- 预期收益（done 时对照判定）：
  - 任意大项目可按子目标拆出独立目录迭代（此前仅 UE dual 词汇可表达）；判定 = 全部生效 AC（AC-001~013、016~020、022、023；AC-014/015 已 OBSOLETE）全绿 + 一次 partition 模式 E2E 冒烟（spawn cwd = 分片根、task.md profile 含 parent/partition、on/off 切换生效）

## §1 功能概述

### 1.1 目标

在**单配置文件 `.agenticdoc/target.yml`** 内以模式块表达多目标配置：`dual:` 块（UE 双根）、`partition:` 块（大项目子目标独立分片）由顶层唯一 `active:` 键激活（single | dual | partition）。partition 配置声明"本控制工作区是大项目的一个切分分片，独立迭代"：控制工作区与分片目录分离，**必须**声明父项目根 `parent`（派生来源、只读上下文）与独立分片根 `partition`（= worker cwd，独立目录，不是父项目的子目录）。

**parent 只读语义**：框架不提供向 parent 的写回/合并流程（profile 注入、contract/docs 引用、doctor 探测）；**不做写路径防火墙**——与 dual 对 engine root 的现状一致（框架无写拦截层，deny_globs 仅为读防火墙）。写防护需求记入 §4 欠债，如需另立 key。

命令族保持独立扁平（`mw target` / `mw partition`，无多级参数）。

### 1.2 技术栈 / 语言

TypeScript（pi 扩展，Node strip-only 可擦除语法）+ Python（mw 框架）+ YAML。TS/Py 双实现 1:1 parity（T-17 模式）。

### 1.3 核心用户场景

1. 场景 A（配置）：开发者把大项目 `D:\BigProject` 的子目标"combat 重构"拆到独立目录 `D:\combat`，执行 `mw partition set --parent D:\BigProject --partition D:\combat`（可加 `--root sdk=D:\SDK`、`--vcs git`；`--partition` 省略则默认控制根绝对路径落盘）。已有 v1 格式 target.yml 时自动迁移 v2（dual 字段与手维护段迁入 dual 块、写 `target.yml.bak` 备份、提示）。
2. 场景 B（派发）：PM 窗口派发任务，worker 进程 cwd = 分片根；toolchain 占位符 `{parent}/{partition}/{root名}` 渲染为绝对路径；task.md 注入 profile 块（记录 active 模式），worker 可引用父项目上下文（contract/docs）。
3. 场景 C（切换）：`mw partition on` / `mw partition off`（对称 `mw target on` / `mw target off`）切换 active 键；块驻留不删除，配置可来回切。
4. 场景 D（诊断）：`mw doctor` 探测 parent/partition/roots 可达性；`mw target show` 与 `mw partition show` 按 active 模式互斥守卫。
5. 场景 E（误配防护）：混格式、白名单外字段、非法 roots 键名、根关系违规（相等/互嵌）、交叉 env、派发后 active 被切的撕裂，均 fail-closed 拒绝并指明原因。

配置形态（v2，单文件）：

```yaml
# .agenticdoc/target.yml
active: partition            # single | dual | partition —— 唯一激活标记
dual:                        # 模式块（配置了才存在）
  game: D:\MyGame
  engine: D:\UE5
  vcs: git
  uproject: ProjectX.uproject
  toolchain: { ... }         # 手维护段，随块
  ignore: { ... }
  contract: { ... }
partition:
  parent: D:\BigProject      # 必填：父项目根（无写回/合并流程）
  partition: D:\combat       # 必填：独立分片目录 = worker cwd
  vcs: git                   # 可选
  roots: { sdk: D:\SDK }     # 可选：命名附加根（仅 partition 块）
  toolchain: { ... }         # 占位符 {parent}/{partition}/{root名}
  ignore: { ... }
  contract: { ... }
```

v1 兼容：**无 `active:` 键**、顶层 `mode/game/engine/...` 的旧文件按现行语义原样解析（在跑的 dual 项目不动文件即零感知）；`mw target set` 在 v1 文件上仍写 v1 行格式（零改动）；仅 `mw partition set` 触发一次性迁移 v2。

### 1.4 范围说明（不做什么）

- 不包含：merge-back / 写回父项目流程（parent 仅上下文引用，见 §1.1 只读语义）
- 不包含：parent 写路径防火墙（欠债见 §4；与 dual 对 engine root 一致）
- 不包含：对 v1 格式文件的主动迁移（仅 `mw partition set` 触发；`mw target set/clear/show` 对 v1 行为零改动）
- 不包含：env 翻转 active 键（env 只覆盖激活模式的字段，不切换模式）
- 不包含：roots 在 dual 块的支持（roots 仅 partition 块合法）
- 不包含：read_scope 自动并入 parent root（任务显式条目才可达）
- 不包含：复杂多级 CLI 参数（命令面保持 `mw <族> <动词> [扁平 flags]`）

### 1.5 单文件解析规则表（替代已废弃的两文件判定表）

记号：F ∈ {无, v1, v2}（v2 = 含 `active:` 键）；A = active 值；EP = {MW_PARTITION_PARENT, MW_PARTITION_ROOT} 有值集合；ET = {MW_TARGET_GAME, MW_TARGET_ENGINE} 有值集合。行序即判定优先级（自上而下首个命中行生效）。字段层校验（AC-002 缺字段 / AC-003 结构校验）在行 6/7/9 命中后继续适用。

| # | 输入 | 结果 |
|---|------|------|
| 1 | F=v2 且同时含 active 键与 v1 顶层字段（mode/game/engine/uproject） | invalid-config：混格式（消息含两形态提示） |
| 2 | F=v2 且 active ∉ {single, dual, partition} | invalid-config（消息含非法值与枚举） |
| 3 | 交叉 env：F=v2 且 A=dual 时 EP 非空；A=partition 时 ET 非空；A=single 时 EP∪ET 非空；F=v1 且 EP 非空；F=无 且 EP、ET 均非空 | invalid-config（消息含冲突 env 名） |
| 4 | F=v2 且 A ∈ {dual, partition} 且对应块缺失 | invalid-config（消息含缺失块名） |
| 5 | F=v2 且 A=single | single（块驻留不解析；source="target-yml"） |
| 6 | F=v2 且 A=dual 且 dual 块有效 | dual（字段取 dual 块；ET 覆盖现行规则） |
| 7 | F=v2 且 A=partition 且 partition 块有效 | partition（EP 子集覆盖对应字段；EP 任一有值 → source="env"，否则 "target-yml"） |
| 8 | F=v1 | 现行 dual/single 语义逐字节不变（ET 覆盖现行；EP 非空已被行 3 拦） |
| 9 | F=无 且 EP 齐备且 ET 空 | partition（env 激活，source="env"，不落盘） |
| 10 | F=无 且 EP 恰其一且 ET 空 | invalid-config：不完整 env 激活（消息含缺失 env 名） |
| 11 | F=无 且 ET 非空且 EP 空 | 现行 env-dual 语义（MW_TARGET_GAME 激活 dual；MW_TARGET_ENGINE 单独沿用现行 "requires dual" 报错） |
| 12 | F=无 且全空 | single（source="default"） |

source 枚举 = {env, target-yml, default}（单文件来源统一 "target-yml"，不新增枚举值）。相对路径（parent/partition/roots/game/engine）一律锚定控制根（与现行 game/engine 同规）。

## §2 业务约束

### 2.1 平台 / 环境

Windows 优先，跨平台语义（realpath / pathlib 归一）。CLI：`python mw.py partition ...`；窗口内：`/mw partition ...` 转发。相对路径一律锚定控制根。

### 2.2 性能指标（非验收性说明）

无新增性能面：解析位于派发路径（每次 spawn 一次，单文件读 + 归一，与 dual 等价）；doctor 探测幂等且缓存。本节为设计约束说明，不设 AC。

### 2.3 安全约束

- fail-closed：不可用配置（缺字段/缺块/白名单外字段/非法键名/根关系违规/交叉 env/撕裂）拒绝派发与 spawn，不静默回退 single
- 本特性零接触 `~/.pi/agent/` 下任何文件（P-002 路径规避）
- .agenticdoc 与 UTF-8 文本写盘一律走 write/edit 工具或 Python 显式 utf-8（P-001）
- set 写盘原子（临时文件 + 原子替换），并发 set 不产生截断文件

### 2.4 集成依赖

- 解析层保持单一 choke point：`resolveWorkspaceConfig` / `load_target_config` 内部按 F（v1/v2/无）分流，下游只见统一 WorkspaceConfig（mode ∈ single|dual|partition）
- env 覆盖：`MW_PARTITION_PARENT` / `MW_PARTITION_ROOT`（仅激活 partition 时有效；进程环境变量，不落盘；生效位置 = 解析进程及其派发链）
- TS（target-config.ts、task-dispatcher.ts、ui-bridge/mw-runner）与 Py（mw_common.py、launcher.py、autopilot/dispatch.py、mw.py、doctor）双侧同步，parity 锁测试扩展
- `packages/multi-workers/dist/extensions/agent-team-loop.js` bundle 重建；`packages/coding-agent/dist` 随重建对齐

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-19T00:54:29+08:00，编号永不回收
> 2026-09-19 v2 修订：[REVISED] 原地修订 / [OBSOLETE] 废弃 / 新增 AC-017~020、022、023

| AC 编号 | 描述 |
|--------|------|
| AC-001 [REVISED] | 在 v2 target.yml（active: partition、partition 块 parent/partition 指向存在目录且根关系合法）下，resolveWorkspaceConfig（TS）与 load_target_config（Py）均返回 mode="partition"，parentRoot/partitionRoot 为 realpath 归一（相对路径锚定控制根，相对 roots 同规），且两侧 13 项逐字段相等：mode、control_root、game_root（null）、engine_root（null）、parent_root、partition_root、roots、vcs、uproject（null）、toolchain、ignore、contract、source |
| AC-002 [REVISED] | 在 v2 active: partition 且 partition 块缺失 parent 或 partition 字段（env 亦未补齐）时，两侧均抛 kind="invalid-config" 且消息包含缺失字段名（"parent" 或 "partition"）；在 active: partition 且 partition 块整体缺失时（行 4），两侧抛 invalid-config 且消息含 "partition" |
| AC-003 [REVISED] | 在结构层冲突下双侧均抛 kind="invalid-config" 且消息包含对应要素：(a) v1 文件含 active 键（混格式）；(b) active 值 ∉ {single,dual,partition}；(c) v2 顶层白名单（active/dual/partition）外任意键；(d) partition 块白名单（parent/partition/vcs/roots/toolchain/ignore/contract）外任意键（含 game/engine/uproject/mode）；(e) dual 块含 parent/partition/roots；(f) roots 键名非法（空、非 [A-Za-z0-9_-]+、保留名 parent/partition/game/engine/uproject）；(g) parent 与 partition 相等或互为祖先（realpath 判定，含 --partition 省略默认控制根形态） |
| AC-004 [REVISED] | 占位符按 mode 分派：partition 块 toolchain 含 {parent}/{partition}/已定义 {root名} 时，renderToolchainCommand 双侧渲染为对应归一路径；含未定义占位符（含 {game}/{engine}/{uproject}）时双侧抛 kind="missing-field"，消息含占位符名与原命令文本；dual/single（v1 与 v2 dual 块）沿用现行 {game}/{engine}/{uproject} 渲染零变化 |
| AC-005 [REVISED] | 在 env 设置 MW_PARTITION_PARENT/MW_PARTITION_ROOT 且 active: partition 时（双侧被测对象：resolveWorkspaceConfig 与 load_target_config）：EP 任意子集覆盖对应字段（另一字段取块值），EP 任一有值时 source="env"，否则 "target-yml"；空白字符串视为未设置（与 MW_TARGET_GAME 语义一致）；source 枚举为 {env, target-yml, default}（不新增枚举值） |
| AC-006 [REVISED] | 在 active: partition 下 launcher spawn 任一 worker 任务时，子进程 cwd = partition root（_worker_cwd 返回分片目录），且该任务的 trace.log/output.md 写回控制根 .agenticdoc 任务目录（协调写入不落分片目录） |
| AC-007 [REVISED @ 2026-09-19：注入标记版本] | 在 active: partition 下派发任务时，task.md 注入含 `<!-- mw-profile: v2 -->` 标记的 profile 块（v2 标记仅用于 partition 注入；dual/single 维持现行 v1 标记与文本零变化，保 AC-016d），块内包含 active 模式行（partition）、parent root、partition root、各 roots 路径、占位符已渲染的 toolchain 行、firewall 段（deny_globs 非空且任务无自身 deny_globs 时）与 contract 段；同 active 同配置重复派发后文件内容不变（幂等） |
| AC-008 [REVISED] | 在 active: partition 下任务 read_scope 含相对条目（如 "src/"）时，_expand_read_scope 将其锚定为 partition root 下的绝对路径并在结果中追加 control root（若未包含）；不因 parent 身份额外追加路径（三根互异前提下 parent root 不出现在展开结果） |
| AC-009 [REVISED] | 在 active: partition 下执行 `mw doctor --json` 时，target 段对 parent_root、partition_root、每个 roots 条目各产出一条 {name, ok, detail} check（isdir 判定），不产出名字含 uproject/engine 的 check；探测缓存以 resolved-config 指纹（active 模式 + 归一根集合）+ 文件 mtime 判新鲜，active 键切换或 env 覆盖值变化后重新探测 |
| AC-010 [REVISED] | 在 parent/partition/roots 路径均存在且根关系合法、无交叉 env 时，执行 `mw partition set --project <控制根> --parent <父> [--partition <分片>] [--root k=v ...] [--vcs git]` 后 exit 0：target.yml 为 v2 且 partition 块含 parent、partition、roots 与 vcs（--partition 省略时写入控制根绝对路径；--root 按首个 = 切分、键名校验、同名重复报错；省略的键不落盘），active: partition；`mw partition show` 输出解析视图；控制根已有 v1 target.yml 时先自动迁移 v2（dual 字段与手维护段内容迁入 dual 块、target.yml.bak 备份、stdout 提示）再写块；parent/partition/roots 路径不存在、根关系违规或交叉 env 时 exit 1、stderr 含原因且文件不变（不产生 .bak、不迁移） |
| AC-011 [REVISED] | 在执行 `mw partition set` 缺少 --parent 参数时 exit 1、stderr 指明缺失参数，且已存在文件内容不变（不产生 .bak）；`mw partition clear`（前置：无两族 env）删除 partition 块并将 active 置 single，若无剩余模式块则删除文件；块不存在时提示并 exit 0 |
| AC-012 [REVISED] | 在 pi 窗口执行 `/mw partition set --parent <p> --partition <q>`（p、q 互异独立目录）时，参数透传至 mw.py，产生的 target.yml 字节内容与 CLI 直调完全一致；`/mw partition show` 输出与 CLI 一致；`/mw partition on/off/clear` 转发行为与 CLI 一致 |
| AC-013 [REVISED] | 零回归：v1 格式文件解析对既有合法 v1 配置零行为变化（解析代码仅新增 v2 检测分支与 v2 路径）；`mw target set` 在 v1 文件上仍写 v1 行格式；`mw target show` 仅在 active: partition 时 exit 1 指向 `mw partition show`（v1/dual/single 下输出与现状逐字节一致）；既有 target 用例零修改全绿；`npm run check` 输出 0 error / 0 warning / 0 info |
| AC-014 [OBSOLETE @ 2026-09-19] | 两文件与两族 env 判定表——随单文件方案废弃，由 AC-017（单文件解析规则表）取代 |
| AC-015 [OBSOLETE @ 2026-09-19] | 活跃文件感知——随单文件方案废弃（无活跃文件概念），由 AC-018（active 模式感知）取代 |
| AC-016 [REVISED] | 升级基线：v1 dual 完整样例（mode/game/engine/vcs/toolchain/ignore/contract）与无文件 single 样例在合入前后，以下输出与合入前基线（main 上先行录制）完全一致：(a) 解析结果的 legacy 字段投影（mode/control_root/game_root/engine_root/vcs/uproject/toolchain/ignore/contract/source）逐字段；(b) _worker_cwd 返回值；(c) _expand_read_scope 样例 scope 展开结果；(d) task.md profile 注入块完整文本；(e) `mw target show` 输出与 doctor target 段 JSON（零新增键，除时间戳字段） |
| AC-017 | 在单文件解析规则表（§1.5）的全部输入组合下（文件形态 F × active 值 × EP/ET 状态，参数化全枚举），模式判定逐行符合规则表（行序即优先级）且双侧（TS/Py）行为一致（含错误 kind 与消息要素：行 1 混格式、行 3 冲突 env 名、行 4 缺失块名、行 10 缺失 env 名）；行 5 命中时块内容不解析不校验；行 8 命中时现行 v1 语义零变化 |
| AC-018 | 在 active 模式感知上：(a) active: partition 时 `mw target show` exit 1 并提示改用 `mw partition show`，active 非 partition 时 `mw partition show` exit 1 提示当前 active 模式与 on/set 切换命令；(b) task.md profile 块含 active 模式行（AC-007）；(c) `mw doctor --json` target 段 config 在 partition 激活时含 parent_root/partition_root/roots 键（partition-only 新键；dual/single/v1 下 doctor 段 JSON 零新增键，保 AC-016e）；(d) 探测缓存指纹随 active 切换失效重探测（AC-009） |
| AC-019 | 在 active 模式切换后重派同一 task.md 时，profile 块（标记行到文件尾）被整体替换为新 active 模式的注入内容；同 active 同配置重派后文件字节不变（与 AC-007 幂等一致） |
| AC-020 | 在派发后、spawn 前 active 模式被切换时（task.md profile 块记录的模式 ≠ launcher spawn 时解析的 active 模式），该任务被标记 failed（状态与日志含 "config torn" 与两侧模式名），不以新 cwd 静默 spawn |
| AC-022 | 在 set 写盘安全上：相同参数重复 `mw partition set` 后 target.yml 字节不变；bootstrap/roots 字段变更后块内手维护段（toolchain/ignore/contract）与注释逐字节保留；写盘经临时文件 + 原子替换，并发 set 后文件总是完整可解析的 v2；v1→v2 迁移后 `target.yml.bak` 与 v2 内容完整包含原 v1 全部字段 |
| AC-023 | 在模式切换上：`mw partition on`（v2 且 partition 块存在 → active: partition；块缺失 → exit 1 提示先 set）；`mw partition off`（active: partition → active: single，块保留）；`mw target on/off` 对称（v2）；v1 文件上 on/off → exit 1 提示 v1 需经 set 迁移；`/mw partition on|off` 转发与 CLI 一致 |

## §4 风险与未决项

- 风险：TS/Py parity 面大（规则表 12 行 + 字段层校验 7 类，每条错误路径双侧同 kind 与消息要素）——parity 锁参数化测试兜底（AC-017）
- 风险：v1/v2 双格式解析复杂度与迁移重写（yaml 结构搬移可能扰动手维护段排版）——.bak 备份 + AC-022 内容保留断言兜底；在跑项目不触 partition 即永不迁移
- 风险：撕裂校验依赖 profile 块的模式行解析（launcher 读 task.md 匹配标记行）——实现简单但需与 AC-019 的替换语义共用边界定义
- 风险：`mw target set` 在 v2 文件上写 dual 块是新分支（v1 路径零改动，v2 路径新写）——AC-013 区分两形态断言
- 风险：TS `WorkspaceConfig.gameRoot` 可空（partition 下 null）的下游类型波及——调用面按 mode 分支核查（design D-002）
- 风险：dist 重建带出 coding-agent dist 树追赶 diff（此前提交有先例，可接受）
- 欠债（显式）：parent 无写路径防火墙（与 dual 对 engine root 一致；将来需要硬防护另立 key）
- 待确认：无

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- mw-dual-workspace 整条 target 管线：`target-config.ts` / `mw_common.load_target_config`（解析与归一）、`.mw/toolchain.json` 探测缓存、`injectWorkspaceProfile`（PROFILE_MARK 幂等注入）、`test_common_target_config.py` 双实现共享夹具 parity 模式（T-17）
- mw-dispatch-models 的子命令+yml 范式：`mw.py model`（独立 dispatch.yml、整段 yaml 重写 `_model_write`、set/show/clear）——partition 命令族与 roots 段改写仿照
- CLI 校验先例：`_target_set` 存在性校验 + stderr + exit 1 模式（AC-010/011 沿用）

### 需规避坑点

- P-001（PowerShell 文本管道损坏无 BOM UTF-8）：本 key 的 target.yml/spec/测试写盘一律 write/edit 工具或 Python 显式 `encoding="utf-8"`；禁止 PS `Get-Content`/`Set-Content` 读-改-写往返
- P-002（跨窗口共享凭据文件）：本特性实现与测试不得引入对 `~/.pi/agent/` 下 auth.json/models.json/settings.json/oauth.json 的任何写路径
