# Quality Gate Report: mw-dual-workspace

**任务指定文件名**: `.agenticdoc/mw-dual-workspace/evidence/quality-gate-report-2026-09-11.md`
**报告生成时间**: 2026-10-09（对当前 HEAD `10446aefb` + 工作树的只读复验）
**触发**: 12/12 task 完成，合入前质检 + 代码审查（reviewer + quality-gate worker）
**范围**: AC-001..009 / VC-001..016 / Coverage F1–F9 / 交叉场景 / 改动面代码审查（TS 6 文件 + Py 5 文件）
**执行**: qg-review worker（独立只读复验 + 证据账本交叉核对）

> 硬约束遵守：未修改任何 src/test/evidence/agenticdoc 源文件（唯一写面=本报告 + `%TEMP%` 探针，探针已删）；未跑全量测试套件，抽查复跑全部为单文件 vitest/pytest（各 ≤2 分钟）；未运行 `npm run check`（其 `biome check --write` 会改写其他会话文件），改用等价的只读命令；结论三态；发现缺陷只给行动计划不修改。
>
> 会话叠加说明：本 key 于 2026-09-17 已有一份 `quality-gate-report-2026-09-17.md`（已提交）。本报告为对当前 HEAD 的独立重跑 + 重判，结论与上一版独立收敛（同样落到 CR-8 与 done 门禁两项处置）。

---

## 0. 前置门禁

| # | 检查项 | 结果 | 备注 |
|---|--------|------|------|
| G-1 | spec AC 编号 | ✅ | AC-001..009，spec.md 状态 locked（2026-09-11T15:01:58+08:00，AC-007 修订） |
| G-2 | design VC 编号 | ✅ | VC-001..016，§7 定义 + §8 映射齐全（机械提取 = 16 个唯一 ID） |
| G-3 | AC→VC 覆盖 100% | ✅ | §8 映射 9/9 AC 全覆盖；16/16 VC 均归属某 AC；design 全文 AC 集合 == spec AC 集合（无缺无多） |
| G-4 | evidence-requirement.md 存在 | ✅ | 逐 AC/VC 充分性标准 + 质检门禁使用说明齐全 |
| G-5 | ac_fingerprint 一致 | ⚠️ **需注意（已文档化）** | 任务书期望值 `e9719d9067b2`；本机 canonical 管道 `grep -oE 'AC-[0-9]{3}' spec.md \| sort -u \| sha1sum \| cut -c1-12`（Node SHA1 等价实现）重算 = **`f5b29879fad4`**，与 evidence-requirement.md 现记录值一致。本机另试 17 种哈希变体（含重复出现序列、CRLF、逗号/管道/制表符分隔、JSON、反引号、表格形、ac_ids 文案、追加空行等）均不能复现 `e9719d9067b2`——与 `ac_fingerprint_note` 所述「原值口径不可复现」吻合。**AC 集合零漂移已独立证实**：spec 提取集恰为 AC-001..009，与表内 `ac_ids` 逐项一致，spec 自锁定后 AC 表未变。属元数据层缺陷，非 AC 漂移 |
| G-6 | evidence/runs 非空 | ✅ | 001..012 共 12 份，全部有测试命令 + [VERIFY] 摘录 |
| G-7 | 每 task ac_refs/vc_refs 非空 | ✅（1 例外已注明） | 001–011 均非空；012（文档收尾）vc_refs 为空但任务书内注明理由（无运行时断言）。task vc_refs 并集 = VC-001..016 全集，无缺口 |
| G-8 | tasks Error Fingerprint 无 open 错误 | N/A（模板差异） | 本 key 任务模板无「Error Fingerprint」节（旧 key 惯例，12 个 task 全 0 命中）；实现偏差记录内嵌于各 evidence/runs「实现偏差记录」节，均为已闭环项 |

**前置门禁小结**：7 项通过，1 项 ⚠️（指纹，已按既有重锚先例闭环），1 项 N/A。

---

## 1. 问题清单

### 1.1 AC 功能正确性（Q-AC-*）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | 无 target 配置时 single 缺省回落、零回归 | ✅ 充分 | VC-001（runs/001、002）+ VC-002（runs/011） | 本次复跑：target-config 68/68 `[VERIFY] VC-001`；Py 17/17；single 快照逐字节断言在案 |
| Q-AC-002 | 双工作区下目标树零框架污染（跨盘） | ✅ 充分 | VC-003（runs/008 双跑） | **本次独立真卷复跑（`MW_TEST_CROSS_DRIVE_ROOTS=F:/;E:/`）：2/2 passed，`[VERIFY] VC-003: target-tree-hits=0 control-files=complete`**；无 env 时 1 passed 1 skipped 且 skip 原因可见（D-009 门控正确） |
| Q-AC-003 | worker cwd=game + 协调文件落控制根 | ✅ 充分 | VC-004（runs/005）+ VC-005（runs/005） | 本次复跑 Py `test_launcher` → `[VERIFY] VC-004: spawn-cwd=<tmp>\game`；TS `dual-root-worker` → `[VERIFY] VC-005: write-prefix=control-root` |
| Q-AC-004 | Game+Engine 双目录渲染 + fail-closed | ✅ 充分 | VC-006/007/008（runs/001、002）+ VC-009（runs/005、006） | 本次复跑 `[VERIFY] VC-006/007/008` 实测可见；Py/TS 同 14→44 fixture parity；`[PARITY] target-config cases=44` |
| Q-AC-005 | 配置/指令切换模式（不重建 bundle） | ✅ 充分 | VC-010（runs/003） | 本次复跑 Py `test_mw_target` → `[VERIFY] VC-010: dual-root=game / single-root=control / write-scope=target-yml-only dist-mtime-unchanged=true`；launcher `_worker_cwd` 每次 spawn 重读（切换下次 spawn 生效） |
| Q-AC-006 | deny_globs 防火墙（100% 拦截 + block 原因） | ✅ 充分 | VC-011（runs/004）+ VC-012（runs/004） | 本次复跑 `[VERIFY] VC-011: deny-block-rate=100 trace-has-reason=true (blocks=6, trace-lines=6)` + `[VERIFY] VC-012: precedence=deny`；含尾部 `/**` 目录自匹配修正 |
| Q-AC-007 | target.yml 三节注入 task.md | ✅ 充分 | VC-013（runs/007 + runs/006 生成侧） | 本次复跑 `[VERIFY] VC-013: toolchain-mark=true ignore-mark=true contract-mark=true`；Py 生成侧 5 条 VC-013 行复现。**注意 CR-8：注入后 target.yml deny_globs 变更不再传播（本次独立复现）** |
| Q-AC-008 | goal mtime 双根不变 | ✅ 充分 | VC-014（runs/009） | 本次复跑 `[VERIFY] VC-014: goal-check-pass=true trace-has-goalcheck=true`；goal_mtime=0 反断言锁错根 |
| Q-AC-009 | serve 根绑定控制工作区 | ✅ 充分 | VC-015（runs/010）+ VC-016（runs/009） | 本次复跑 `[VERIFY] VC-015: serve-meta-prefix=control-mw` + `[VERIFY] VC-016: staleness-detect=true` |

### 1.2 VC 证据充分性（Q-VC-*）

`evidence/runs/*.md` grep `[VERIFY] VC-xxx` 计数：VC-001×2、VC-002×1、VC-003×2、VC-004×1、VC-005×1、VC-006×2、VC-007×2、VC-008×2、VC-009×2、VC-010×3、VC-011×1、VC-012×1、VC-013×5、VC-014×1、VC-015×1、VC-016×1 —— **16/16 VC 均有 PASS 行**，与 evidence-requirement 的期望输出逐条对得上。抽查复跑（本次独立执行）：

| 问题 ID | VC | 状态 | 证据引用 |
|--------|----|------|---------|
| Q-VC-001 | VC-001 single 缺省 | ✅ | runs/001、002；本次 `agent-team-loop-target-config.test.ts --silent=false` 实测 stdout |
| Q-VC-002 | VC-002 check/回归 | ✅ | runs/011（check 全文 + 89 例基线逐文件 ⊂/= 对照 new-failures=0）；本次仅只读复核（见 Q-GATE-002，未重跑 `npm run check`） |
| Q-VC-003 | VC-003 跨盘零污染 | ✅ | runs/008；**本次 F:/E: 真卷独立复跑 2/2** |
| Q-VC-004 | VC-004 spawn cwd=game | ✅ | runs/005；本次 Py `test_launcher` 复现 |
| Q-VC-005 | VC-005 写前缀=控制根 | ✅ | runs/005；本次 `dual-root-worker` 复现 |
| Q-VC-006 | VC-006 engine 渲染 | ✅ | runs/001、002；本次复现 |
| Q-VC-007 | VC-007 缺 engine 非零退出 | ✅ | runs/001、002；本次复现 |
| Q-VC-008 | VC-008 uproject 唯一/0/2 | ✅ | runs/001、002；本次复现 |
| Q-VC-009 | VC-009 双根 scope 放行/拦截 | ✅ | runs/005、006；本次双侧复现（TS `[VERIFY] VC-009` + Py `[VERIFY] VC-009: game_abs=true engine_abs=true`） |
| Q-VC-010 | VC-010 set/clear + 写面 + dist mtime | ✅ | runs/003；本次 Py 复现 |
| Q-VC-011 | VC-011 deny 100% block + trace | ✅ | runs/004；本次 `autopilot-read-scope` 复现 |
| Q-VC-012 | VC-012 deny 优先 | ✅ | runs/004；本次复现 |
| Q-VC-013 | VC-013 三节注入 | ✅ | runs/006、007；本次双侧复现 |
| Q-VC-014 | VC-014 goal check 双根 | ✅ | runs/009；本次复现 |
| Q-VC-015 | VC-015 serve 前缀=控制根 | ✅ | runs/010；本次 `test_serve_meta` 复现 |
| Q-VC-016 | VC-016 staleness 检测 | ✅ | runs/009；本次复现 |

### 1.3 Coverage Matrix（Q-COV-*，design §6）

| 问题 ID | 功能点（正常/边界/异常） | 状态 | 证据 | 备注 |
|--------|------------------------|------|------|------|
| Q-COV-F1 | 单目录缺省 / env 优先级 / 配置损坏 fail-closed | ✅ 充分 | VC-001 + fixture 010/011 + invalid-yaml + dispatch reject `target-config-rejected` + launcher 拒 spawn + PM 逐任务隔离 | 异常路径三层（解析/派发/生成）均 fail-closed |
| Q-COV-F2 | 目标树零污染 / 跨盘 / 误锚探针 | ✅ 充分 | VC-003 真卷 + VC-005；扫描模式含 trace.log/output.md/phase-*.md 探针 | |
| Q-COV-F3 | worker 双根 / 同盘跨盘 / PI_WORKER_TASK 缺失 | ✅ 充分 | VC-004/005；缺失=既有早退路径（代码审查确认未改） | |
| Q-COV-F4 | 双根渲染 / {uproject} 唯一性 / engine·uproject 缺失非零退出 | ✅ 充分 | VC-006/007/008（双侧 fixture 集） | |
| Q-COV-F5 | 模式切换 / env 临时覆盖 / 未知 YAML 节不破坏 | ⚠️ 子项（不降级） | VC-010 + fixture 010/011；未知顶层节容错由「仅读已知键 + 行级更新保全节体/注释」构造保证 + `test_set_existing_file_line_updates_preserve_sections` 间接覆盖 | 无专门「未知顶层节」fixture；行为正确性由构造 + 保留测试覆盖 |
| Q-COV-F6 | deny 防火墙 / allow+deny 冲突 / 遍历洪泛有界 | ✅（L1）/ ⚠️（洪泛） | VC-011/012 锁 L1 调用级强制；遍历洪泛→截断+caps 无专门测试 | D-004 已知限制显式记录，design §9 接受；非本 key 可测缺陷（核心工具行为） |
| Q-COV-F7 | profile 注入 / docs 引用 / 节缺失跳过 | ✅ 充分 | VC-013 + runs/007 节缺失用例 + docs 引用行 | |
| Q-COV-F8 | goal 一致性 / goal.md 移动 | ✅ 充分 | VC-014 + goal_mtime=0 反断言；goal.md 不存在=既有失败路径 | |
| Q-COV-F9 | serve 根绑定 / staleness 双根 / serve 异常退出 | ✅ 充分 | VC-015/016；serve 异常退出=既有 pid 检测路径未改 | |

### 1.4 交叉场景（Q-X-*）

| 问题 ID | 场景 | 状态 | 证据 |
|--------|------|------|------|
| Q-X-001 | dual + deny（跨盘 scope 内 deny 命中、deny 优先、`path.relative` 退化时 abs 基准兜底） | ✅ 充分 | runs/008（`Content/DDC/x.uasset` scope 内 deny 拦截，跨盘退化路径） |
| Q-X-002 | dispatch + profile 注入顺序（frontmatter vs profile 块、幂等、任务级覆盖） | ✅ 充分（CR-8 例外） | runs/006/007（PROFILE_MARK 哨兵；`ownDenyGlobs` 时 frontmatter 保持原样）。**例外：CR-8** |
| Q-X-003 | single + target.yml ignore 注入（单根 UE 也需 DDC 防火墙；scopeless 不强加 scope） | ✅ 充分 | runs/006（`scopeless_deny_injected=true no_scope_forced=true`）+ `test_deny_globs_and_sections_in_single_mode` |
| Q-X-004 | 模式切换 ↔ spawn 生效时序（免重启） | ✅ 充分 | VC-010 + launcher `_worker_cwd` 每 spawn 重读 + `/mw target` 提示语 |
| Q-X-005 | fail-closed 分层（config 损坏拒派/拒 spawn vs task.md 不可读仅警告） | ✅ 充分 | runs/005/006/007（broken yml 拒派/拒 spawn；假路径 task.md 跳过注入仅警告、入队照常） |
| Q-X-006 | TS/Py deny_globs 渲染 ↔ 解析回环一致性（单引号块列表） | ✅ 充分 | 双侧同形（`deny_globs:` + `  - '<glob>'`）；`parseTaskMd` 剥引号；两侧测试各自锁形 |
| Q-X-007 | env 覆盖交互（env game 覆盖文件 single；env engine 无 game） | ✅ 充分 | fixture 010/011（TS+Py parity） |
| Q-X-008 | TOOL_ALLOWLISTS ↔ autopilot REGISTRY T-17 L0 parity 未破坏 | ✅ 充分 | 本次复跑 `autopilot-protocol.test.ts` 10/10 + Py `test_autopilot_l0.py` 6/6 |

### 1.5 spec 约束二次核对（Q-S-*）

| 问题 ID | 约束 | 状态 | 备注 |
|--------|------|------|------|
| Q-S-001 | §2.1 平台（Windows 跨盘、erasable TS） | ✅ | 真卷 F:/E: 本次复现；只读 biome 检查 6 个改动面 TS 文件 0 issue |
| Q-S-002 | §2.2 trace 追加延迟（p95<1ms / max<50ms） | ✅ | 机制未变（本 key 未触碰 output-writer.ts），沿用调研实测锚定（p95 ≤ 0.2ms 跨盘） |
| Q-S-003 | §2.2 read-scope 每调用无可感知新增开销 | ✅（已闭环） | 上轮 ⚠️：deny 判定新增一次归一化。现 design §9 已加 [EXEC 注记 2026-09-17]：deny-glob 任务最 2 次 realpath/调用，增量 ≈ 0.088ms（既有实测值），无可感知影响；CR-1 归一化复用登记为后续候选 |
| Q-S-004 | §2.3 安全（凭证隔离、空 scope fail-closed、deny 优先、四工具拦截） | ✅ | 凭证隔离 `_build_env` 零改动；VC-011/012 + 既有空 scope 用例 |
| Q-S-005 | §2.4 集成依赖（Extension API 零核心改动、T-17 parity、serve/conductor 语义） | ✅ | 全部经扩展层实现；T-17 本次复跑绿 |

### 1.6 代码审查（改动面全读后评审）

TS：`shared/target-config.ts`、`shared/paths.ts`、`worker/read-scope.ts`、`worker/worker-mode.ts`（拦截器 / `parseTaskMd` 段）、`pm/task-dispatcher.ts`、`pm/pm-orchestrator.ts`（`dispatchNewTasks` 段）
Py：`mw_common.py`（`load_target_config` / `render_toolchain_command` / `discover_uproject` / `_decide_active_mode` 段）、`launcher.py`（`_worker_cwd` / `_spawn`）、`mw.py`（target 子命令 + doctor）、`autopilot/dispatch.py`、`autopilot/timeline.py`

> 变更面核实：`git diff --stat` 确认本 key 双工作区核心文件（上述 TS 6 文件 + Py `launcher.py` / `dispatch.py` / `timeline.py` / `mw_common.py`）在工作树中**无未提交改动**；`mw.py` 的未提交 hunk 位于 `cmd_model`（3183-3184）与 `_ap_verify_show`（3479-3490），与 `_target_set/_clear/_show`（624-810）无关。审查基于已提交状态。

**总体判断：核心路径（deny 判定 / read-scope / dispatch 注入 / target-config 解析 / 控制根推导）未发现 High 缺陷；fail-closed 分层、同配置幂等、锁与并发路径实现与文档一致。** 发现如下：

| ID | 严重度 | 位置 | 发现 | 影响 |
|----|--------|------|------|------|
| CR-8 | **Medium（本次独立复现）** | `pm/task-dispatcher.ts` `injectWorkspaceProfile` / `insertDenyGlobs` | `ownDenyGlobs = /^deny_globs:/m.test(base)` 在**注入后**被重新识别为「任务自带」。此后 target.yml `ignore.deny_globs` 的任何变更都不会再注入该 task.md（`insertDenyGlobs` 仅在 `!ownDenyGlobs` 时调用），且 `ignoreEnforced = !ownDenyGlobs` 变为 false 使 profile 块 `Context firewall` 节被整段删掉。**独立复现**（`%TEMP%` Node 探针，已删）：single/dual + `deny_globs:['**/*.old']` 首派 → frontmatter=`'**/*.old'` + firewall 节；改 yml 为 `['**/*.new1','**/*.new2']` 重派 → 实测 `oldGlobStillPresent=true newGlobInjected=false firewallSection=false`（新 glob 完全未生效、firewall 节消失）。conductor 路径（Py `render_task_md` 每次整体重写）不受影响 | 上下文防火墙陈旧：配置新增的 deny 形态对被重派的同一 task 不生效；profile 渲染自相矛盾 |
| CR-1 | Low（延续，已登记） | `read-scope.ts` `checkReadScopeCall` | deny 判定先 `matchedDenyGlob`（内部 `normalizeForCompare`→`realpathSync`），未命中再 `isWithinScope`（再次归一同一路径）：deny-glob 任务每次读取类调用最多 2 次 realpath（改造前 1 次）。量级 ~0.088ms/调用，无可感知影响；design §9 已按此修订 | 已登记可选微优化（归一化结果传两处），不阻断 |
| CR-2 | Low（延续） | `pm-orchestrator.ts` `dispatchNewTasks` | `const taskContent = fs.readFileSync(taskMdPath, "utf8")`（第 460 行）在逐任务 `try`（自 463 行）**之外**：TOCTOU 窗口内 task.md 消失会抛出并中断本轮整个扫描（调用点 `dispatchNewTasks(...).catch(() => {})` 静默吞掉），剩余任务本轮跳过、下轮重试 | 竞态窗口极窄、自愈；与「task.md 不可读仅警告」的分层意图不一致。建议移入 try |
| CR-3 | Info（延续） | `worker-mode.ts` `parseTaskMd` | phase prompt 正文中行首裸 `deny_globs:`（列表项受 `!inPhasePrompt` 保护，但字段复位本身不受保护）会重置已解析的 denyGlobs | 仅病态 task.md 可触发；dispatch 渲染产物无此形态 |
| CR-4 | Info（延续） | `task-dispatcher.ts` `insertDenyGlobs` | 无闭合 `---` 的文件走前置插入（块在 frontmatter 之前）；worker 解析器全文扫描所以功能正确，但 YAML 纯度上 frontmatter 不再起始于字节 0 | 注释已声明兼容 ui-bridge 手写形态 |
| CR-5 | Info（延续） | TS `insertDenyGlobs` / Py `render_task_md` | deny glob 内嵌单引号时单引号包裹不转义（`'**/foo'bar/**'`） | 病态 glob；TS/Py 渲染与 TS 解析剥引号对称退化，两侧不发散 |
| CR-6 | Info（延续） | `mw.py` `_target_set` | 先写引导字段、后整配置校验（坏 section 时文件已改、exit 1 + warning） | 注释声明；下次 set 自愈 |
| CR-7 | Info（延续） | `launcher.py` `_worker_cwd` | 每次 spawn 重读 target.yml：编辑中途的瞬时损坏会拒绝该次 spawn | 与 fail-closed + 逐任务隔离一致，换免重启切换（设计取舍已文档化） |

**审查确认的关键正确性点（抽查无问题）**：
- deny 优先于 allow（VC-012 纯函数 + wiring 用例）；尾部 `/**` 目录自匹配修正后的边界（`stripped !== ""` 防 `/**` 退化）正确
- deny-only（scope=null）不含 caps/containment——scopeless 全访问红线不破；两类字段全无→零拦截（legacy 行为）
- `resolveWorkspaceConfig` 文件内矛盾（mode single+game / dual 无 game）先于优先级判定（Task 001 首版死代码 bug 被测试抓出后修正，用例在案）
- 同配置重派幂等（PROFILE_MARK / `blockIsFresh`）；控制根附加仅非空 scope（`not scope` 守卫，首跑测试抓出后修正）
- `dispatch()` 写序（task.md → lock → 队列行 → 回读验证）与孤儿自愈不变；`EVENT_TYPES` 含 `target-config-rejected`
- `renderProfileBlock` 行前缀非 `key:` 形——避免 `parseTaskMd` 全文扫描误读
- `_apply_bootstrap_line` 行级更新保全手写节/注释/行尾；`^key\s*:` 不误匹配缩进/前缀相似的键
- `controlRootFromTaskPath` 4 次 dirname 与 worker-mode `trueAgenticdocRoot` 推导等价（`<control>/.agenticdoc/{owner}/workers/{task}/task.md → <control>`）

### 1.7 门禁 / 环境项（Q-GATE-*、Q-ENV-*）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-GATE-001 | `audit_phase.py mw-dual-workspace` 的 `done` 门禁 FAIL | ❌ **不复现任务书「audit_phase.py PASS」参考事实** | 本次实跑 `.agents/skills/agentic-task/scripts/audit_phase.py mw-dual-workspace`：design/plan/tasks/execute 均 PASS，**done: FAIL — achieved.md missing pattern '系统行为变化'**，VERDICT FAIL exit=1 | 框架 schema 漂移：skill 侧 done 门禁现要求 `achieved.md` 含 `## 系统行为变化` 节，本 key 于 2026-09-17 关闭时该要求尚不存在（新旧同代 key 对照：2026-09 前关闭的 key 多缺该节）。属文档完备性缺口，非功能/代码缺陷 |
| Q-GATE-002 | `npm run check` 的 biome 段在当前 HEAD 非 0 | ⚠️ 非本 key 引入 | 只读 `npx biome check packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`：Found **1 error**（`ui-bridge.ts:1061-1065` ternary 格式），属后续 key mw-vision-role。**本 key 改动面 6 个 TS 文件**其只读检查 `Checked 6 files ... No fixes applied`（0 issue） | 本 key 改动面无 biome 违规；未运行 `npm run check`（`--write` 会改写其他会话文件），故 AC-001「check 0/0/0」在当前 HEAD 无法逐字复现——阻塞方是后续 key |
| Q-ENV-001 | 工作树含其他会话的未提交改动 | ⚠️ 环境噪声 | `git diff --stat`：`rag/adapter.ts`、`rag-parity.test.ts`、`test_common.py`、`autopilot/conductor.py`、`effective_config.py` 等 16 文件；核心双工作区文件无未提交改动 | 已核对不落本 key 改动面；复跑均在只读语义下进行 |

---

## 2. 汇总

| 分类 | 行数 | ✅ 充分 | ⚠️ 不足/需处置 | ❌ 无证据/不复现 |
|------|------|--------|----------------|------------------|
| 前置门禁 G-* | 8 | 6 | 1（G-5 指纹，已文档化） | 0（G-8 N/A） |
| Q-AC-* | 9 | 9 | 0 | 0 |
| Q-VC-* | 16 | 16 | 0 | 0 |
| Q-COV-F* | 9 | 7 | 2（F5 间接、F6 已接受） | 0 |
| Q-X-* | 8 | 8 | 0 | 0 |
| Q-S-* | 5 | 5 | 0 | 0 |
| 代码审查 CR-* | 8 | 6（Info 可接受） | 3（CR-8 Medium、CR-1/CR-2 Low） | 0 |
| Q-GATE-* / Q-ENV-* | 3 | 0 | 2（GATE-002、ENV-001） | 1（GATE-001） |
| **合计（66 行）** | **66** | **57** | **8** | **1** |

> 计数口径：按「问题行」计。GATE-001 的 ❌ 指「任务书参考事实（audit PASS）在当前 HEAD 不复现」，不代表功能无证据。功能/证据层（AC/VC/Coverage/交叉/约束）无 ❌。
>
> 任务书「参考事实」逐项对照：12/12 task 验证通过 ✅（任务卡）；16/16 VC 有 [VERIFY] 行 ✅（grep 复核）；multi-workers pytest 402 通过 8 deselect — 属 2026-09-11 账本事实，本次按时间盒未重跑全量；coding-agent agent-team-loop 套件 201 通过 1 skip — 同上；回归基线 new-failures=0 ✅（runs/011 留档）；**audit_phase.py PASS ❌ 不复现**（见 Q-GATE-001）；**npm run check 0/0/0 ⚠️ 在当前 HEAD 不复现**（见 Q-GATE-002，阻塞方为后续 key）。

**质检结论：⚠️ 有条件通过**

- 功能、覆盖与证据层达标：9/9 AC 充分，16/16 VC 有可复现 `[VERIFY]` PASS 证据（含本次真卷 F:/E: 独立复现 VC-003），fail-closed 分层与同配置幂等实现与文档一致，代码审查无 High。
- 两条须处置项（见 §3）：**CR-8**（注入后 target.yml deny_globs 变更不传播——功能性缺陷，本次独立复现）与 **Q-GATE-001**（`achieved.md` 缺 `## 系统行为变化`，当前框架 done 门禁 FAIL）。
- 一条外部项：Q-GATE-002（`ui-bridge.ts` biome error，属 mw-vision-role），不阻断本 key 但使「check 0/0/0」在当前 HEAD 无法逐字复现。

---

## 3. 未通过/不足问题行动计划表

| ID | 问题 | 行动计划 | 责任 | 阻断性 |
|----|------|---------|------|--------|
| P-1 | **CR-8** 首次注入后 target.yml `ignore.deny_globs` 变更不再传播到该 task.md，且 profile 块 firewall 节被删 | 二选一：(a) 在 `injectWorkspaceProfile` 中把「本任务自带 deny_globs」与「上次注入的 deny_globs」区分开（例如：仅当 `deny_globs:` 行出现在原文件（注入前）时才算 own；或对已注入块记录来源哨兵），使配置变更时以新列表整体替换；(b) 若判定为可接受语义，则在 design §9 / D-005 显式记录「注入后 deny_globs 冻结为首派值」并补一条覆盖该语义的回归用例。任一选择都需补测试锁定 | 后续 key / PM | 建议合入前修正 (a) 或显式接受 (b) |
| P-2 | **Q-GATE-001** `achieved.md` 缺 `## 系统行为变化` 节，当前 `done` 门禁 FAIL | 在 `.agenticdoc/mw-dual-workspace/achieved.md` 增补 `## 系统行为变化` 节（新增/修改功能与影响面，面向后续任务；AC/VC 勾销交由 quality-gate-report 承担）；无需改代码 | PM（worker 只读约束） | 恢复 done 门禁通过所必需（框架 schema 已前进） |
| P-3 | **Q-GATE-002** `ui-bridge.ts:1061-1065` biome 格式错误（mw-vision-role） | 由该 key 的 owner 执行一次 `biome check --write` 或手改 ternary 换行；随后复跑 `npm run check` 确认 0/0/0。**不属于 mw-dual-workspace 改动面** | mw-vision-role owner | 非本 key 阻断；影响「check 0/0/0」字面复现 |
| P-4 | **G-5** 任务书期望指纹 `e9719d9067b2` 不可复现（canonical = `f5b29879fad4`，已重锚） | 无需代码行动：`ac_fingerprint_note` 已记录验证链（旧值口径不可复现 + AC 集合零漂移双证 + canonical 管道复算一致）。本报告复核确认 | 记录在案 | 不阻断（已闭环） |
| P-5 | **Q-COV-F6** 遍历洪泛有界无专门测试 | design D-004/§9 已显式接受为已知限制（P4 无 .gitignore 场景）；建议后续 key 为 L2 有界性补一条洪泛回归用例 | 后续 key | 不阻断（登记欠债） |
| P-6 | **Q-COV-F5** 无专门「未知顶层节」fixture | 行为由「仅读已知键 + 行级更新保全节体」构造 + `test_set_existing_file_line_updates_preserve_sections` 间接覆盖；如需直接证据可补一条 fixture | 后续 key | 不阻断 |
| P-7 | **CR-1** deny/scope 双分支归一化结果复用 | 登记为可选微优化（~0.088ms/调用量级）；design §9 已记录实测量级 | 后续 key | 不阻断 |
| P-8 | **CR-2** `dispatchNewTasks` taskContent 读取在 try 之外 | 移入逐任务 try/catch；窗口极窄、下轮自愈 | 后续 key | 不阻断 |

---

## 4. 二次印证结论

1. **spec 全约束 ↔ Q 覆盖**：§2.1/2.2/2.3/2.4 与 §1.4 范围外项（多控制工作区 N:1、UE 专用类型、资产编辑、AGENTS.md 合并、pi 核心）均未越界实现——改动面无一处触碰 pi 核心（GC-1 ✓）、无中心化调度（GC-2 ✓）、Worker 仍独立进程（GC-3 ✓）、`_workers.parallel` 写仍走 O_CREAT|O_EXCL 锁（GC-4 ✓）、白名单未动（GC-5 ✓）、goal 锚点在控制根（GC-6 ✓）。性能两项：trace 延迟（S-002）机制不变 + 实测锚定 ✅；read-scope 新增开销（S-003）已由 design §9 修订闭环 ✅。
2. **Function Flow 节点 ↔ Q**：dispatch 读 target.yml（生成侧 VC-013/009）→ 渲染失败非零退出（VC-007 + dispatch reject + PM 拒派）→ task.md 落控制根（VC-005）→ launcher spawn cwd=game（VC-004）→ game/eng 读写（VC-009）→ trace/output/phase 落控制根（VC-005/014）→ deny 命中 block+trace（VC-011）→ PM 吸收（既有 deliverWorkerResult + AC-002 control-files=complete）——每节点均有对应 Q。
3. **Coverage Matrix 异常路径行 ↔ Q-COV**：F1–F9 全部有 Q-COV 行（含异常路径）；唯 F5 未知节（间接覆盖）与 F6 洪泛（接受性覆盖）为 ⚠️ 子项，均已登记；其余异常路径均有直接用例。
4. **task vc_refs 空但 AC 有 VC**：仅 task 012（文档收尾），理由已注明；16 VC 与 9 AC 的任务级引用并集完整无缺口（001–011 vc_refs 并集 = 全 16）。
5. **指纹复核**：canonical 管道重算 = `f5b29879fad4` = evidence-requirement.md 现记录值（2026-09-17 重锚，附验证链 note）；任务书期望值 `e9719d9067b2` 为重锚前旧值，17 种本机变体均不可复现，但 AC 集合零漂移已双证。**指纹项本身不再是门禁缺口**。
6. **本次独立发现**：① CR-8 deny_globs 配置变更不传播（本机探针复现，Medium）；② 当前框架 `done` 门禁要求 `achieved.md` 含 `## 系统行为变化`，本 key 缺该节（框架 schema 漂移，非代码缺陷）；③ 当前 HEAD 的 biome error 属后续 key（mw-vision-role），非本 key。

**最终判定**: ⚠️ **有条件通过** —— 完成 P-1（CR-8 修正或显式接受 + 回归用例）与 P-2（achieved.md 补 `## 系统行为变化` 节）后合入条件满足；P-3 由相关 key 处置；P-4..P-8 为已登记的元数据/验证欠债，不阻断。

*本报告为 AI 生成的只读质检输出。*
