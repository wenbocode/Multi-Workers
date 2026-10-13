# Spec: worker 任务投递与回收契约（mw-dispatch-card-gate）

- Key: `mw-dispatch-card-gate`｜阶段: SPEC｜日期: 2026-10-12｜基线 commit: `6c5189831`
- 上游：`mw-guard-form-hardening`（DONE）的 T-20 实测事件；`.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md`
- 相关：`.agenticdoc/mw-claude-mirror-parity`（PAUSED，见其 `pm-state.md` D-002）
- 本文状态：**定稿**（4 个 spec RQ 已回收；用户已确认范围与原则）

## §0 Goal Alignment

**goal.md 锚点**：本项目要「一个 PM + 多 Worker 并行开发同一项目」，前提是每个 worker 拿到**正确、必要的上下文 + 任务内容 + 交付格式**，并能被**可靠回收**（goal.md：*goal.md 目标对齐*、*工具白名单按任务类型*、*文件驱动去中心化协调*、*Worker 执行过程中追踪 goal 一致性*）。

**两条原则（用户裁定）**：
1. **投递优先**：机制第一职责是**把该给的给到**，限制只是副产品（不是先把 worker 管起来）。
2. **不设探索限制**：投递的是**种子**，worker 应能**启发式自行寻找上下文**（全仓只读），并记录发现。

**预期收益（可量化，done 判据）**：
1. 派发信封齐备率：工具生成的 `task.md` **100%**（现：`workers/*/task.md` 三段齐备 2/343 = 0.6%）。
2. 误拒 = **0**（在有语料上）；历史卡登记不回填。
3. 回收契约生效：`output.md` 缺段被判 `needs-clarification` 并**指名缺失段**（现：内容齐全却因占位段被判，3/4 实例）。
4. coding 可归属：报告改动清单 **⊆** trace 写入事件（现：无任何按 worker 的改动记录）。
5. 探索不被限制：种子未覆盖但仓库可检索的信息，worker 能自行发现（实测检索命令 + 命中）。

## §1 问题陈述（实测）

| # | 缺口 | 性质 | 实测坐标/数值 |
|---|---|---|---|
| E1 | 派发链上**没有任何一层检查卡**；`dispatch_worker` 参数面**没有卡片路径** | 投递无载体 | `pm/ui-bridge.ts` 全文 0 处读 `tasks/`；卡存在性无检查（T-20 实例） |
| E2 | 投递物正文 = **PM 描述原文** ⇒ 格式=PM 写成什么样 | 结构性无格式 | `pm/ui-bridge.ts:2028 writeDispatchTaskMd` → `:2054`（锚点以基线 commit `6c5189831` 为准）；343 张派发卡中 **259/343（75.5%）连一个二级标题都没有**；三段齐备 **2/343** |
| E3 | 上下文基本缺失：`goal.md` 与相位切片不在投递物里 | 投递不足 | 同上（投递物只有 frontmatter + description） |
| E4 | 回收契约未成文 | 回收不可靠 | 4 个 worker 中 3 个内容齐全却因 `output.md` 占位段被判 `needs-clarification` |
| E5 | coding 无改动归属记录 | 不可追溯 | 全仓无 task.md/卡的 hash 与按 worker 的文件记录；`write_scope:` 仅 8/343 |
| E6 | 四个生产者，工具层只能拦 2 个 | 覆盖不足 | `dispatch_worker`/`/worker` vs conductor 直写（`packages/multi-workers/autopilot/dispatch.py`）+ 手写队列行 |
| E7 | 逃生舱形同虚设 | 审计无效 | `allow_foreign_write: true` 只写不读（TS/Python 均无消费者） |
| E8 | **生产者瘫痪**：门禁要求 producer 侧注入，而 producer 代码在各项目的 framework 副本里、门禁在**全局服务**里 ⇒ 版本偏移即整条 autopilot 零产出 | 投递机制反噬 | 实测 `H:\git\E2Feature`：队列 675 done / 33 failed / **0 pending / 0 running**，`_workers.parallel` mtime `10-10 20:45`（**2 天零派发**），全部 worker 无重启迹象；详见 `evidence/incidents/autopilot-producer-paralysis-20261012.md` |
| E9 | **无人认领时无投递归属**：窗口的自动重派扫描只覆盖自身 watch 的 key + `_scratch`，而 conductor 驱动的 key **禁止被 claim**（AUTOPILOT-HANDOFF §5 #13：claim ⇒ `CLAIM_LIVE` ⇒ conductor 跳过 ⇒ 卡死）⇒ conductor 停摆即**无人拥有重派权**，操作者唯一合规动作是“什么都不做”；另有 35 个 key 被煽入 `out-of-scope` 告警且该告警在 autopilot 下**按构造永不清空**（清空条件是 claim，而 claim 被禁） | 归属缺口 | `pm-orchestrator.ts:1201`（告警前缀硬编码为 `dispatch 已拒绝：`，把 notice 显示为 refusal）+ `dispatchNewTasks(scope:"pm")` 扫描范围；实测 E2Feature 队列 2 天零写入、0 pending/0 running、**无 `run.json`**（旧格式） |

### §1.2 RQ 结论（归档于 `evidence/research/`）

| RQ | 结论要点 | 载荷数值 |
|---|---|---|
| RQ-1（`spec-dispatch-path-20261012.md`，32,475 B） | 派发链只检查 `workers/<key>/task.md` 存在（`launcher.py:463 _require_task_file`）；**全链路无人检查卡**；`task.md` 缺失被**静默归档**到 `_workers.stale.parallel`（无消费方）；无 `type:` ⇒ 回退 `default` ⇒ full 工具集且 `dispatchRefusal` 只对 `origin: conductor` 生效（fail-open 实测） | 15 条假设点；`type:` 解析两侧一致 342/342 |
| RQ-2（`spec-card-format-corpus-20261012.md`，94,979 B） | 卡片语料 345 张/37 key；严格三段标题门槛 **44 合规/301 不合规（87.2%）**；宽档 **273/72（20.9%）**；`tasks/*.md` 的 `type:` 头 **0/345** | 命名变体：`描述`116/`输入`92/`目标`90/`预期产出`77/`交付物`74 |
| RQ-2b（`spec-dispatch-input-format-20261012.md`） | 派发输入 343 张：T1 严 **2/341（99.4%）**、宽档 **203/343（59.2%）** 不合格；**75.5% 无任何二级标题**；正文=description 原文；模板注入字段无一项承载三段；**生成端可保证**（复用 `applyWriteSurfaceContract:1745` 幂等注入）；卡内 `type:` vs `trace.log [START]` 330/332 一致（2 例均在非工具生成卡） | 成本 ~100–145 行 + 12 字节金样本 |
| RQ-3（`spec-gate-layer-20261012.md`，37,917 B） | **4 个生产者**：工具层只得 A/B，**服务层 `launcher.py:1267 _poll_once` 才全覆盖**；独立校验器不拦任何派发；一致性建议新增叶子层 `shared/dispatch-card.ts`（调用点 `pm/ui-bridge.ts:2301`/`:2795`）；跨语言沿用「golden 表 + 双实现 + parity」（实测 23 passed） | 方案 A 隐性成本：8 个测试文件/55 处 `dispatch_worker` 引用 |

## §2 范围

**In**：投递信封（§1 格式 + §2 上下文种子）／生成端构造／工具层 + 服务层校验／**回收契约**（`output.md` 必备段 + `_workers.parallel` 状态判据）／coding 改动历史与 ⊆ 校验／追溯（卡 sha256）与一致性／逃生舱真读。
**Out**：C-9 分发副本门禁（mirror key，PAUSED）；上一 key 残余（除与本 key 相关者）；卡片**内容质量**评判；限制 worker 的探索面（明确禁止）。

**锚点基线**：本文与 `design.md` 内的 `路径:行号` 引用以基线 commit `6c5189831` 为准；T-02/T-03/T-05/T-07/T-09/T-10/T-12/T-14 落地后行号会继续漂移，复核时以**符号名**（函数/常量名）定位为准（QG F-09 登记）。

## §3 验收标准（AC）

> 每条都须有反例（防恒真）；引用写完整可解析路径；数值机器可读。

- **AC-001 投递齐备**：工具生成的 `task.md` 必含 §1 四项 + 类型附加项 + §2 种子，且含"种子非上界"声明。判据：12 个字节金样本逐字节通过；现有工具生成语料误拒 = 0。
- **AC-002 上下文与探索**：① 种子四项在投递物中齐备；② 投递物含可解析的相位切片引用；③ **反方向**：构造"种子未覆盖但仓库可检索"的问题，worker 能自行发现（给检索命令 + 命中证据）；④ 报告的「上下文来源清单」非空。
- **AC-003 回收契约**：`output.md` 五段判据（结论/证据含原始命令/改动清单或未覆盖面/**残留与未验证**/上下文来源）；缺段 ⇒ `needs-clarification` 且**指名缺失段**；齐备 ⇒ `done`。
- **AC-004 coding 可归属**：报告改动清单 **⊆** trace 写入事件；不等 ⇒ 红并列出差集（anti：不允许只靠自报）。
- **AC-005 review 不设输入限制且必填未覆盖面**：`review` 派发物不得含"允许阅读范围"这类限制；**缺未覆盖面声明 ⇒ 拒绝**；验证工具集含 bash（可执行验证）。**[REVISED @ 2026-10-12] 本子项撤回**——`review` 保持只读（无 bash）：该形态被两处固定测试与 TS/Python 角色注册表 parity 约束（`packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`、`packages/coding-agent/test/extensions/agent-team-loop.test.ts`），为 PM 的调度选择而放宽既定契约属过度改动（违反 P-02/P-05 精神）；「验证须可执行」改由 (1) 未覆盖面声明必填、(2) 需要执行验证的任务改派具备 bash 的角色（如 `coding`）来满足。
- **AC-006 追溯与一致性**：每卡记 `card_path` + sha256（`mw_common.sha256_eol_normalized`）；**等长替换篡改 ⇒ 红**⇒ 恢复 ⇒ 绿；卡片集合 ⊉ 派发集合 ⇒ 红并列差集。
- **AC-007 失败方向与逃生舱**：默认 fail-closed；逃生舱显式声明**且真被读取**（`rg` 可检索到读取点 + 审计行）。
- **AC-008 隔离**：不写其他 key 路径；对其他 key 只读。
- **AC-009 生产者不瘫痪**（[ADDED @ 2026-10-12]，用户裁定：conductor 事实上已被瘫痪，必须本 key 内修复）：本 key 的门禁**不得**使任一投递生产者（工具层 `dispatch_worker`／`/worker`、conductor 自动派发、PM 手写队列行）失去产出能力。判据：(a) 四条生产者路径的端到端产物都必须**可 spawn**——conductor 路径判据为 `packages/multi-workers/autopilot/dispatch.py render_task_md` 的产物喂给 `launcher._envelope_refusal` 后返回 `None`；(b) **版本偏移**（全局 launcher 已 enforce而项目 framework 副本未升级）不得表现为「静默零派发」或不可解释的硬拒，必须给出「缺什么 + 怎么修」的可操作提示；(c) 无卡合成派发（L3/repair/roadmap）与 PM 手写派发同样不得被误拒。**反例**：把项目的 `dispatch.py` 换回旧版（无注入）后跑 conductor 路径，断言**不是**零产出/静默，而是明确的升级指引 + 单行可见告警，且不使该 key 的全部派发同时失效。
- **AC-010 自注入之物不得触发自身守卫**（[ADDED @ 2026-10-12]，T-15 发现 C-29）：本 key 注入到产物里的框架标记（如 `<!-- mw-write-surface: v1 -->`）**不得**被本 key 自己的守卫/判据误读为写入目标或意图。判据：(a) 对**真实语料**（当前 `corpus=357`）跑写入意图判定，`false_positives == 0`；(b) HTML 注释内的 `-surface:` 一类文本不得被当作目标（剥离注释后再匹配）；反例：把 marker 原文喂入 hit 收集器，断言结果为空集；同时断言去掉注释剥离后原本的真实目标仍能命中（防过修）。
- **AC-011 无人认领时的投递归属**（[ADDED @ 2026-10-12]，用户裁定：E2Feature 此刻即瘫痪，属本 key 投递契约面、本 key 内修）：
  - **(a) 归属可机器判定**：对每个 key 能判定四态并输出 `ORPHANED = 存在未派发工作 ∧ 无活 claim ∧ 无活运行`（活运行 = `run.json` running 或该 task_key 的进程存活）；
  - **(b) 响亮且可操作**：`ORPHANED` 必须产生**可见、可操作**的告警（指名 key、未派发工作、可执行动作），不得表现为“什么都不做”的静默；告警前缀不得把所有 kind 都说成“已拒绝”；
  - **(c) 修复路径不得制造死锁（核心）**：窗口对 `ORPHANED` key 的**修复派发不得写入 claim 字段**——派发后 conductor 对该 key **仍可**派发（反例断言：`CLAIM_LIVE` 未因本次修复而被置上 / conductor 的跳过条件未被触发）；
  - **(d) 不得越权**：**有活 claim** 的 key 仍归其窗口，其它窗口不得写入（现状不变，AC-019 隔离语义保持）；
  - **(e) 历史派发与旧形态不阻碍修复**：修复派发所依赖的目录/卡为旧形态时，不得因工具层严格门禁而**彻底无路可走**（至少要有一条**服务层合成信封**的可行路径，且该路径留审计）。

## §7 可复用资产

`pm/ui-bridge.ts:1752 applyWriteSurfaceContract`（幂等段注入）、`shared/task-frontmatter.ts:141 readTaskType` + Python 镜像、`worker-mode.ts:364 parseTaskMd`、`shared/index-store.ts:67 keyNameRefusal` ↔ `packages/multi-workers/update_index.py:118 key_name_refusal`（golden+parity 范式）、`mw_common.sha256_eol_normalized`、`packages/multi-workers/autopilot/conductor.py:2417/2433`（差集）、`output-sections.ts`、`mergeAllowForeignWrite`。

## §8 需规避坑点

- **P-01** 派发路径属驻留服务 ⇒ 改动需 cutover（`mw build --install` + 重启服务/窗口），不能假设改源码即生效。
- **P-02** 不得变成纸面要求：必须可执行且有判别力（篡改⇒红）。
- **P-03** **过拦同样违约**：严格标题档会误拒 87.2%/99.4% ⇒ 必须宽档 + 新派发强制 + 历史豁免。
- **P-04** 两个以上入口必须**同一判据**（工具层 + 服务层兜底），否则等于没拦。
- **P-05** 不得写其他 key 文件；**不得以 gate 之名缩小 worker 的读探索面**。
- **P-06** 不重开 mirror key 范围与上一 key 残余。
- **P-07** 历史卡不回填不判死（登记 + 迁移指引）。
- **P-08** `type:` 词汇表不一致：工具 5 值 vs worker 运行时 10 值 + fallback（`verifier`/`repair`/`phase-writer` 等工具拒、worker 用）⇒ 由 design 定为"收口到单一词汇表"，本 key 内最小化改动。
- **P-09** `output.md` 段落契约与现状不符（3/4 实例）⇒ 迁移期须避免一次性把全部历史派发判红。
- **P-10** 门禁（全局服务）与注入（每项目 framework 副本）分处**两个版本域** ⇒ 任何「要求 producer 先满足」的门禁都必须自带**版本协商或服务层兜底**，否则升级全局服务即瘫痪所有尚未同步的项目（见 E8/AC-009）。
