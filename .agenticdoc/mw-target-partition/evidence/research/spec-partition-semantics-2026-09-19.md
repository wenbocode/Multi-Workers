# Research: partition 模式语义与现有 target 表面（spec）

## 决策问题
回答 spec §1（范围：partition 模式语义、字段命名）、§2（约束：fail-closed 与 parity）、§4（风险：改动面清单）。

## 调研方法与出处
- 现有 target 表面通读（代码事实）：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/target-config.ts`（全文，resolveWorkspaceConfig/discoverUproject/renderToolchainCommand，single/dual 两模式、{game}/{engine}/{uproject} 占位符、fail-closed 哲学 AC-004）
  - `packages/multi-workers/mw_common.py:1675-1830`（load_target_config 镜像、discover_uproject、render_toolchain_command、probe_target_toolchain、_doctor_target 含 .mw/toolchain.json 探测缓存）
  - `packages/multi-workers/launcher.py:627-680`（_worker_cwd：dual → game root，spawn cwd 语义）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`（dispatchTask 时 injectWorkspaceProfile：PROFILE_MARK 幂等、toolchain 渲染、firewall、contract 注入 task.md）
  - `packages/multi-workers/autopilot/dispatch.py:146-170`（_expand_read_scope：dual 模式相对条目锚定 game root + 追加 control root，AC-012 红线"只扩大已声明的 containment"）
  - `packages/multi-workers/mw.py:584-680`（target set/show/clear CLI：--project 为控制根、--game/--engine/--vcs/--uproject bootstrap 字段、_apply_bootstrap_line 行级改写、三手工段不碰）
  - `packages/multi-workers/README.md:118-181`（双工作区文档：配置方式、优先级 env > yml > single）
- 用户对话输入（2026-09-18/19，本 session）：
  - 初始诉求：target 模式只支持 UE 游戏项目，需要适配任意项目的新模式
  - 修正 1：核心语义是"大项目拆子目标、独立迭代、要能区分 single、像派生"，非单纯"非 UE"
  - 修正 2：命名用 `partition`
  - 修正 3：分片根**不是子目录**，是独立目录（project 必填、显式指向；控制工作区与分片目录分离，同 dual 的 control/game 关系）
  - 未反对的默认（按推荐执行）：parent 只做只读上下文（v1 无 merge-back）；保留任意命名 `roots:`

## 发现
1. dual 模式的机制层（worker cwd 切换、read_scope 锚定、deny_globs 防火墙、contract/toolchain 注入、fail-closed、doctor 探测缓存）全部与 UE 无关；UE 绑定点仅是词汇：`game`/`engine` 字段、`uproject` 发现、`{game}/{engine}/{uproject}` 占位符。
2. `mode` 当前校验仅接受 `dual|single`（target-config.ts:238、mw_common.py:1694）；新增模式值是受控扩展点。
3. CLI 的 `--project` 已被控制根占用（所有 mw 子命令一致），partition 分片根字段不能用同名 flag。
4. TS/Py 两侧 1:1 parity 由 `test_common_target_config.py` 按错误 kind + 字段锁定——新模式的每个错误路径必须双侧同 kind。
5. `_expand_read_scope` 的 AC-012 红线：只追加 control root（worker 机械需要读 task 上下文）；parent root 不是机械需要 → 不自动追加，任务显式声明才可达。

## 结论 → 决策映射
- 支撑 §1：`mode: partition` 第三模式，`parent`（大项目根，必填）+ `partition`（独立分片根，必填 = worker cwd）+ 可选 `roots:` 命名根 + 沿用 vcs/toolchain/ignore/contract；占位符 `{parent}/{partition}/{roots名}`，未知占位符 fail-closed。
- 支撑 §1 范围（不做什么）：不实现 merge-back/写回父项目（parent 只读上下文）；不改 dual/single 行为（零回归）；roots 仅 partition 模式合法（dual 沿用旧占位符，避免词汇混用）。
- 支撑 §2：沿用 env > yml 优先级（MW_TARGET_PARENT/MW_TARGET_PARTITION）；UE 字段（game/engine/uproject）在 partition 下报 invalid-config（fail-closed）；错误 kind 双侧 parity。
- 支撑 §4：改动面 = target-config.ts、mw_common.py、launcher.py(_worker_cwd)、task-dispatcher.ts、dispatch.py(_expand_read_scope)、mw.py(CLI)、ui-bridge/mw-runner(转发本就透传)、doctor 探测、README/CHANGELOG、两侧测试 + parity 扩展。

## 修订（2026-09-19 对话）：独立命令族 + 独立配置文件

- 决策：partition 不复用 `mw target` 命令与 target.yml，改为独立 `mw partition set/show/clear` 命令族 + 独立 `.agenticdoc/partition.yml`（用户提出，PM 认可：partition 是独立语义，不该挤在 target 词汇表里）。
- 依据（代码事实）：mw-dispatch-models 已有独立子命令+独立 yml 范式先例（mw.py `model` + dispatch.yml，`_model_write` 整段重写）；解析层单一 choke point（resolveWorkspaceConfig/load_target_config）可内部分流两文件，下游（launcher/dispatcher/doctor）不见分支细节。
- 语义变化：
  - 文件存在性即模式声明（partition.yml 无 `mode:` 字段）
  - “字段混用”错误类换成“交叉冲突”类：两文件共存、逐文件未知字段、env 交叉（MW_PARTITION_* vs MW_TARGET_*）均 fail-closed
  - env：MW_PARTITION_PARENT / MW_PARTITION_ROOT（齐备可临时激活；仅其一 → invalid-config）
  - target 命令族与 target.yml 解析路径零改动（比 --mode 扩展方案更彻底的零回归）
- spec 影响：AC-001/002/003/005/010/011/012 重写，§1.1/§1.3/§1.4/§2.4 同步。

## 追加澄清（2026-09-19 对话）

- **双文件共存行为**（用户问）：fail-closed 全链路——解析层抛 invalid-config 指名两文件；派发拒（dispatchTask / dispatch.py target-config-unusable）、spawn 拒（launcher _worker_cwd 按任务隔离失败）、doctor 报 issue、两命令 show 均 exit 1。入口防护：mw partition set 在 target.yml 存在时拒绝；唯一入口是 target set 无前置检查（零改动取舍）或手编。→ AC-003(a)
- **--partition 默认**（用户提）：可省略，默认分片根 = 控制根（当前打开的项目目录）。语义：默认只在 CLI set 层展开，落盘绝对路径；解析层 partition: 仍必填（手编缺失 → AC-002 报错）；形态 = single 布局 + parent 声明。→ AC-010/011 修订

## 补全：两 yml 处理总规则（2026-09-19 对话，用户指出未说清）

- 单一活跃文件原则 + 模式判定决策表（→ AC-014）：(1) 共存报错；(2)(3) env 交叉报错；(4) 无文件且 EP 齐备 → env 激活；(5) EP 恰其一报错；(6) 无 partition 输入时现行 single/dual + MW_TARGET_* 语义逐字节不变。行内覆盖：P 存在时 EP 任意子集覆盖对应字段；非活跃文件内容（含手维护段）不参与解析。
- 由此暴露并补定的三点：
  1. source 枚举扩展 {env, target-yml, partition-yml, default}（→ AC-005）
  2. `mw target show` 必须加活跃文件守卫（现打印机不识 parent/partition 字段，否则 partition 活跃时打印残缺视图）——target 命令族唯一改动，AC-013 措辞相应收紧（set/clear 与解析零改动，show 守卫在 dual/single 下输出不变）
  3. `.mw/toolchain.json` 探测缓存现按 target.yml mtime 判新鲜，须改为绑定活跃文件路径+mtime，文件切换后强制重探测（→ AC-015c）

## 补全：env 存储与升级零感知（2026-09-19 对话）

- **MW_xxx 存哪**（用户问）：哪都不存——纯进程环境变量，mw 不落盘不持久化；生效位置 = 做解析的进程（PM 窗口 TS 侧 / mw serve、launcher Py 侧）及其派发链；未设置永远走文件路径。→ spec §2.4 补充说明
- **不能影响 dual/single**（用户强调：已有项目在跑）：新增 AC-016 升级基线冒烟——dual 完整样例 + single 样例在合入前后的解析/cwd/scope 展开/注入块/show/doctor 输出逐字节一致，用例先行录制 main 基线。与 AC-013（既有用例零修改）、AC-014 行 5/9/10（无 partition 输入时现行语义逐字节不变）构成三层保障。诚实说明：load_target_config/resolveWorkspaceConfig 入口会加 partition.yml 存在性检查，但 dual/single 分支逻辑零改动。

## 需求转向 v3：单配置文件（2026-09-19 对话，用户指令）

- 指令：多文件改回**单配置文件 target.yml**；partition 保持独立命令族；不同模式是文件内独立配置块，每块标明是否激活，可切换；命令保持扁平无多级参数。
- 动机（PM 分析）：两文件方案的两份评审暴露了一整类问题（共存错误、活跃文件感知、缓存 active-file 绑定、profile 切换残留、show 守卫/schema 冲突）——单文件 + 唯一 active 键直接消灭该问题类。
- 定型：顶层 `active: single|dual|partition` 唯一激活点（不用每块 active 标志，避免双活冲突）；模式块 dual:/partition: 各自带 toolchain/ignore/contract；v1 文件（无 active 键）原样解析零感知，仅 `mw partition set` 触发一次性迁移 v2（.bak 备份）；切换原语 `mw partition on/off`（对称 target on/off，v1 上报错）；env 只覆盖激活模式字段不翻转 active；source 枚举收敛回 {env, target-yml, default}（单文件不新增枚举）。
- 同轮拍板（用户确认 A/A/A）：parent 措辞改“无写回/合并流程，不做写路径防火墙”（欠债）；撕裂校验 fail-closed（AC-020）；parent/partition 根关系校验并入 AC-003(g)。
- spec 影响：§1 全量重写（v2 格式/场景/范围/§1.5 规则表 12 行）；AC-014/015 标 OBSOLETE，新增 AC-017/018/019/020/022/023，其余 AC 全部 [REVISED]。
