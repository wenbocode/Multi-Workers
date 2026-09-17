# Quality Gate Report: mw-dual-workspace

**时间**: 2026-09-17T16:34:00+08:00
**触发**: 12/12 task 完成，合入前质检 + 代码审查
**范围**: AC-001..009 / VC-001..016 / Coverage F1–F9 / 改动面代码审查（TS 6 文件 + Py 5 文件）
**执行**: qg-review worker（独立只读复验 + worker 证据交叉核对；未修改任何 src/test/evidence 文件）

## 前置门禁

| 检查项 | 结果 | 备注 |
|--------|------|------|
| spec AC 编号 | ✅ | AC-001..009，locked at 2026-09-11T15:01:58+08:00 |
| design VC 编号 | ✅ | VC-001..016，§7/§8 齐全 |
| AC→VC 覆盖 100% | ✅ | §8 映射 9/9 AC 全覆盖；反向 16/16 VC 均归属 AC；机械比对通过 |
| evidence-requirement.md | ✅ | 存在，逐 AC/VC 充分性标准 + 质检门禁使用说明 |
| ac_fingerprint 一致 | ⚠️ **失配** | 记录值 `e9719d9067b2`；本机以 canonical QG 管道（git-bash `grep -oE 'AC-[0-9]{3}' spec.md \| sort -u \| sha1sum \| cut -c1-12`）重算得 `f5b29879fad4`。另试 12 种哈希变体（comma/newline/space/CRLF/无分隔/JSON/去前缀/小写/md5 等）均不能复现记录值——与 goal-autopilot v1/v2、mw-widget-terminal-lifecycle 重锚前同型的「早期 ad-hoc 口径不可复现」。**AC 集合零漂移已独立证实**：evidence-requirement 的 ac_ids 逐项等于 spec 提取集（恰 AC-001..009），spec 自锁定后 AC 表未变。指纹失配是元数据缺陷，非 AC 漂移；处置走既有重锚先例（见行动计划 P-1） |
| evidence/runs/ 非空 | ✅ | 001..012 共 12 份 |
| task ac_refs/vc_refs 非空 | ⚠️ | 001–011 均非空且引用正确；012（文档收尾）vc_refs 为空但理由在任务书内注明（无运行时断言，VC 账本由 001–011 承载），ac_refs 全 9 项非空。task vc_refs 并集 = VC-001..016 全集，无遗漏 |
| tasks Error Fingerprint | N/A（模板差异） | 本 key 任务模板无「Error Fingerprint」节（旧 key 惯例）；偏差记录内嵌于 evidence/runs 各「实现偏差记录」节。12/12 task 验证状态=通过，无 open 错误 |

## 问题清单与核查结果

### AC 功能正确性（Q-AC-*）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | 无配置时 single 缺省回落、零回归 | ✅ 充分 | VC-001（runs/001、002，[VERIFY] 行 + 14 parity fixture）+ VC-002（runs/011 check 0/0/0 全文 + test.sh 89 例基线对照表 new-failures=0，逐文件 ⊂/= 对照） | 复跑：target-config 36/36（TS）+ Py 5/5；biome 1048 文件 0 issue（只读模式）、tsgo --noEmit exit 0、multi-workers 全量 433 passed 8 deselected（0 失败）、agent-team-loop 6 文件 198 passed 1 skipped。全量 ./test.sh 未在本次 QG 重跑（时间盒约束），采信 runs/011 的完整留档对照表 |
| Q-AC-002 | 目标树零污染（跨盘） | ✅ 充分 | VC-003（runs/008：双跑——无 env skip 原因可见 + 真实 F:/E: 全链 target-tree-hits=0 control-files=complete；扫描模式含 trace.log/output.md/phase-*.md 误锚探针） | 复跑无 env 路径：1 passed 1 skipped，skip 行可见；真卷路径依赖本机 F:/E: 卷，采信留档 |
| Q-AC-003 | worker cwd=game + 协调文件落控制根 | ✅ 充分 | VC-004（runs/005，Popen cwd=game 断言 + single 回归 + broken yml 拒绝 spawn）+ VC-005（runs/005，控制根写前缀 + game 树零文件扫描） | 复跑：launcher/dispatch/serve 93 passed；dual-root-worker 4/4 |
| Q-AC-004 | Game+Engine 双目录渲染 + fail-closed | ✅ 充分 | VC-006/007/008（runs/001、002：渲染含 engine 绝对路径无残留、缺 engine 非零失败不回退、uproject 唯一/0/2 三态）+ VC-009（双根授权/根外拦截） | 复跑 target-config 套件全绿，[VERIFY] 行实测 stdout 可见；Py/TS 同 14 fixture parity |
| Q-AC-005 | 配置/指令切换模式（不重建） | ✅ 充分 | VC-010（runs/003：dual-root=game / single-root=control / write-scope=target-yml-only / dist-mtime-unchanged） | 复跑 test_mw_target 12/12；`_worker_cwd` 每次 spawn 重读 target.yml（模式切换下次 spawn 即时生效）；后续 commit 80f5aa58d 增补 `/mw target` 窗口指令（薄封装 mw.py，复跑 agent-team-loop.test.ts 全绿）进一步覆盖指令通道 |
| Q-AC-006 | deny globs 防火墙（100% 拦截 + block 原因） | ✅ 充分 | VC-011（runs/004：`**/*.uasset` + `DerivedDataCache/**` 两形态 × read/ls/find/grep = 6 调用 100% block，trace 6 行 rule=deny-glob）+ VC-012（deny 优先于 allow） | 复跑 autopilot-read-scope 24/24；含 D-003 [EXEC 注记] 的尾部 `/**` 目录自匹配修正（裸目录 ls/find 漏洞被首跑测试抓出后修复——L1 漏洞闭环证据在案） |
| Q-AC-007 | target.yml 三节注入 task.md | ✅ 充分 | VC-013（runs/007：三特征标记全 true；幂等哨兵、任务级 deny_globs 不覆盖、节缺失跳过不阻断；runs/006 Py 侧注入 + single 快照逐字节一致） | 复跑 profile-injection 7/7 + dispatch 17/17；`renderProfileBlock` 行前缀刻意非 `key:` 形避免 parseTaskMd 误读——设计考量正确 |
| Q-AC-008 | goal mtime 双根不变 | ✅ 充分 | VC-014（runs/009：双根 fixture goal check 通过 + [GOAL_CHECK] 落控制根 trace 且 mtime 为控制根 goal.md 真实值（非 0 反断言锁错根）） | 复跑 dual-root-worker 4/4 |
| Q-AC-009 | serve 根绑定控制工作区 | ✅ 充分 | VC-015（runs/010：mw.pid/serve.meta/mw.stop/workers.lock 全部前缀=控制根，game 树零文件，零代码改动锁定）+ VC-016（runs/009：staleness 只看控制根源码 mtime） | 复跑 test_serve_meta 4/4 |

### VC 证据充分性（Q-VC-*）

16/16 VC 在 evidence/runs/ 均有 `[VERIFY] VC-xxx` PASS 行（grep 计数：VC-001×2、VC-003×2、VC-006/007/008/009 各×2、VC-010×3、VC-013×5、其余各×1），与 evidence-requirement 的期望输出逐条对得上。抽查复跑（单文件 vitest/pytest，各 ≤2 分钟）：

| 复跑项 | 结果 |
|--------|------|
| agent-team-loop-target-config.test.ts | 36/36，[VERIFY] VC-001/006/007/008 + [PARITY] cases=14 实测 stdout |
| autopilot-read-scope.test.ts + dual-root-worker.test.ts | 28/28，[VERIFY] VC-005/009/014/016 stdout 可见 |
| cross-drive-worker.test.ts（无 env） | 1 passed 1 skipped（skip 原因可见，D-009 门控语义正确） |
| profile-injection.test.ts | 7/7 |
| Py：test_common_target_config + test_mw_target | 17/17 |
| Py：test_autopilot_dispatch + test_serve_meta + test_launcher | 93/93 |
| Py：test_autopilot_l0（T-17 parity）+ autopilot-protocol.test.ts | 5/5 + 10/10 |

VC-003 按 task 规定以跨盘门控用例记 skip（本机无 MW_TEST_CROSS_DRIVE_ROOTS 时 1 skipped 原因可见；真卷 F:/E: 全链留档 runs/008）。**Q-VC-001..016 全部 ✅ 充分。**

### Coverage Matrix（Q-COV-*，design §6）

| 问题 ID | 功能点（正常/边界/异常） | 状态 | 证据 | 备注 |
|--------|------------------------|------|------|------|
| Q-COV-F1 | 单目录缺省回落 / env 优先级 / 配置损坏 fail-closed | ✅ 充分 | VC-001 + cases 010/011 + case 012 invalid-yaml + dispatch reject `target-config-rejected`（runs/006 broken_yml_rows=0 fail_closed=true）+ launcher 拒绝 spawn（runs/005）+ PM 扫描逐任务隔离（runs/007） | 异常路径三层（解析/派发/生成）均 fail-closed |
| Q-COV-F2 | 目标树零污染 / 跨盘 / 误锚探针 | ✅ 充分 | VC-003 真卷 + 同盘 VC-005 game 树扫描 + AC-002 扫描模式含 trace/output/phase 探针 | |
| Q-COV-F3 | worker 双根 / 同盘跨盘 / PI_WORKER_TASK 缺失 | ✅ 充分 | VC-004/005；PI_WORKER_TASK 缺失=既有行为（workerModeActivate 早退路径未改，代码审查确认零改动） | |
| Q-COV-F4 | 双根渲染 / {uproject} 唯一性 / engine·uproject 缺失非零退出 | ✅ 充分 | VC-006/007/008（TS+Py 双侧 14 fixture） | |
| Q-COV-F5 | 模式切换 / env 临时覆盖 / 未知 YAML 节不破坏 | ✅ 充分（⚠️ 子项） | VC-010 + cases 010/011；未知节容错由构造保证（双侧仅读已知键；`_apply_bootstrap_line` 行级更新保全节体/注释，test_set_existing_file_line_updates_preserve_sections 断言注释与 deny_globs 原样保留） | 无专门「未知顶层节」fixture 用例——行为正确性由构造+保留测试间接覆盖，评级不降 |
| Q-COV-F6 | deny 防火墙 / allow+deny 冲突 / 遍历洪泛有界 | ✅（L1）/ ⚠️（洪泛） | VC-011/012 锁 L1 调用级强制；遍历洪泛→截断+caps 无专门测试 | D-004 已知限制显式记录（P4 无 .gitignore 时输出截断+caps 限流有界非阻断），design §9 接受；非本 key 可测缺陷（核心工具行为） |
| Q-COV-F7 | profile 注入 / docs 引用 / 节缺失跳过 | ✅ 充分 | VC-013 + runs/007 节缺失用例（只配 toolchain → 无报错）+ docs 渲染引用行 | |
| Q-COV-F8 | goal 一致性 / goal.md 移动 | ✅ 充分 | VC-014 + goal_mtime=0 反断言；goal.md 不存在=既有失败路径（goalMtime 返 0 记录） | |
| Q-COV-F9 | serve 根绑定 / staleness 双根 / serve 异常退出 | ✅ 充分 | VC-015/016；serve 异常退出=既有行为（pid 检测路径未改） | |

### 交叉场景（Q-X-*）

| 问题 ID | 场景 | 状态 | 证据 |
|--------|------|------|------|
| Q-X-001 | dual + deny（跨盘下 scope 内 deny 命中、deny 优先、path.relative 退化时 abs 基准兜底） | ✅ 充分 | runs/008（`Content/DDC/x.uasset` scope 内 deny 拦截，跨盘退化路径） |
| Q-X-002 | dispatch + profile 注入顺序（deny_globs frontmatter vs profile 块、幂等、任务级覆盖） | ✅ 充分 | runs/006/007（PROFILE_MARK 哨兵幂等；ownDenyGlobs 时 frontmatter 保持原样且 profile 块跳过 ignore 节——防「谎称强制」修正有案） |
| Q-X-003 | single + target.yml ignore 注入（单根 UE 同样需要 DDC 防火墙；scopeless 不强加 scope） | ✅ 充分 | runs/006（scopeless_deny_injected=true no_scope_forced=true）+ test_deny_globs_and_sections_in_single_mode |
| Q-X-004 | 模式切换 ↔ spawn 生效时序（免重启） | ✅ 充分 | VC-010 + launcher `_worker_cwd` 每 spawn 重读 + /mw target 提示语（80f5aa58d） |
| Q-X-005 | fail-closed 分层（config 损坏拒派/拒 spawn vs task.md 不可读仅警告） | ✅ 充分 | runs/006/007（yml 损坏→拒派不入队、stderr 可见、修复自愈）+ runs/007（task.md 假路径→跳过注入仅警告、入队照常）+ runs/005（broken yml→spawn 拒绝、worker.log 记录、队列 failed） | 
| Q-X-006 | TS/Py deny_globs 渲染↔解析回环一致性（单引号块列表） | ✅ 充分 | 双侧渲染同形（`deny_globs:` + `  - '<glob>'`）；parseTaskMd 剥引号；两侧测试各自锁形 |
| Q-X-007 | env 覆盖交互（env game 覆盖文件 single；env engine 无 game） | ✅ 充分 | cases 010/011（TS+Py parity） |
| Q-X-008 | TOOL_ALLOWLISTS ↔ REGISTRY T-17 L0 parity 未破坏 | ✅ 充分 | 复跑 autopilot-protocol 10/10 + test_autopilot_l0 5/5 |

### spec 约束二次核对（Q-S-*）

| 问题 ID | 约束 | 状态 | 备注 |
|--------|------|------|------|
| Q-S-001 | §2.1 平台（Windows 跨盘、erasable TS） | ✅ | 真卷 F:/E: 用例留档；tsgo --noEmit exit 0、biome 0 issue（1048 文件） |
| Q-S-002 | §2.2 trace 追加延迟（p95<1ms/max<50ms） | ✅ | 机制未变：本 key 未触碰 output-writer.ts（commit 文件清单核实），沿用调研实测锚定（p95≤0.2ms 跨盘） |
| Q-S-003 | §2.2 read-scope 每调用无可感知新增开销 | ⚠️ 证据不足 | 见代码审查 CR-1：量级安全（realpath 实测 mean 0.088ms）但 spec 指定的「read-scope 套件改造前后同机耗时对照（实施时取证）」未在 evidence/runs 留档；design §9「双根不新增每调用 realpath」对 deny-glob 任务不精确（deny 判定新增一次归一化，scope 模式下同调用最多 2 次 realpath） |
| Q-S-004 | §2.3 安全（凭证隔离、空 scope fail-closed、deny 优先、四工具拦截） | ✅ | 凭证隔离路径（launcher _build_env）零改动；VC-011/012 + 既有空 scope 用例（read-scope 套件 20 既有用例全绿） |
| Q-S-005 | §2.4 集成依赖（Extension API 零核心改动、T-17 parity、serve/conductor 语义） | ✅ | 全部经扩展层实现；T-17 复跑绿 |

## 代码审查（改动面全读后评审）

TS：target-config.ts / paths.ts / read-scope.ts / worker-mode.ts / task-dispatcher.ts / pm-orchestrator.ts（+后续 commit 80f5aa58d 的 ui-bridge.ts /mw target 与 mw-runner.ts targetMw）
Py：mw_common.py（target-config 节）/ launcher.py（_worker_cwd）/ mw.py（target 子命令 + doctor）/ autopilot/dispatch.py / autopilot/timeline.py

**总体判断：核心路径（deny 判定 / read-scope / dispatch 注入 / target-config 解析 / 控制根推导）未发现正确性缺陷；fail-closed 分层、幂等、锁与并发路径实现与文档一致。** 发现如下（无阻断项）：

| ID | 严重度 | 位置 | 发现 | 影响 |
|----|--------|------|------|------|
| CR-1 | Low | read-scope.ts `checkReadScopeCall` | deny 判定先 `matchedDenyGlob`（内部 normalizeForCompare→realpathSync），未命中再 `isWithinScope`（再次 normalize 同一路径）：deny-glob 任务每次读取类调用最多 2 次 realpath（改造前 1 次）；deny-only 任务从 0→1 次。量级 ~0.1ms/调用，实际无可感知影响，但 spec 指定的前后耗时对照证据未留档，design §9 措辞不精确 | 性能证据缺口（Q-S-003 ⚠️）；可顺手把归一化结果传两处以消重复 |
| CR-2 | Low | pm-orchestrator.ts `dispatchNewTasks` | `taskContent = fs.readFileSync(taskMdPath)` 在逐任务 try/catch 之外：TOCTOU 窗口内 task.md 消失会抛出并中断本轮整个扫描（被外层 `.catch(()=>{})` 静默吞掉，无警告），剩余任务本轮跳过、下轮重试 | 竞态窗口极窄、自愈；与「task.md 不可读仅警告」的分层意图不完全一致（该意图在 injectWorkspaceProfile 内实现）。建议移入 try |
| CR-3 | Info | worker-mode.ts `parseTaskMd` | phase prompt 正文中若出现行首裸 `deny_globs:`（列表项受 `!inPhasePrompt` 保护，但字段复位本身不受保护），会重置已解析的 denyGlobs | 仅病态 task.md 内容可触发；dispatch 渲染产物无此形态 |
| CR-4 | Info | task-dispatcher.ts `insertDenyGlobs` | 无闭合 `---` 的文件走前置插入（块在 frontmatter 之前）；worker 解析器全文扫描所以功能正确，但 YAML 纯度上该文件 frontmatter 不再起始于字节 0 | 代码注释已声明兼容意图；ui-bridge 手写形态兼容 |
| CR-5 | Info | TS insertDenyGlobs / Py render_task_md | deny glob 内嵌单引号时单引号包裹不转义（`'**/foo'bar/**'`） | 病态 glob；TS/Py 渲染与 TS 解析剥引号对称退化，两侧不发散 |
| CR-6 | Info | mw.py `_target_set` | 先写引导字段、后整配置校验（坏 section 时文件已改、exit 1 + warning） | 行为在代码注释声明；下次 set 自愈 |
| CR-7 | Info | launcher.py `_worker_cwd` | 每次 spawn 重读 target.yml：编辑中途的瞬时损坏会拒绝该次 spawn | 与 fail-closed + 逐任务隔离一致（worker.log 记录、队列 failed）；换来免重启切换（设计取舍已文档化） |

**审查确认的关键正确性点**（抽查无问题）：
- deny 优先于 allow（VC-012 纯函数断言 + wiring 用例）；尾部 `/**` 目录自匹配修正后的边界（`stripped !== ""` 防 `/**` 退化）正确
- 尾部 `/**` 剥离后相对基准匹配：`**/DerivedDataCache/**` → `**/DerivedDataCache`，裸目录与子路径双命中
- deny-only（scope=null）不含 caps/containment——AC-012 红线（scopeless 全访问）不被破坏；两类字段全无→零拦截（legacy 行为）
- `resolveWorkspaceConfig` 文件内矛盾（mode single+game / dual 无 game）先于优先级判定——Task 001 首版死代码 bug 被测试抓出后修正，用例在案
- 幂等：PROFILE_MARK 早退使重派发不重复注入（deny 注入同被哨兵覆盖）；`ownDenyGlobs` 正则检测防止任务级列表被 yml 默认覆盖
- 控制根附加仅对非空 scope（`not scope` 守卫）——scopeless 类型不会凭空获得 containment，首跑测试抓出后修正（runs/006）
- `dispatch()` 写序（task.md → lock → 队列行 → 回读验证）与孤儿自愈（D-102）不变；EVENT_TYPES 15 项含 `target-config-rejected`
- `renderProfileBlock` 行前缀非 `key:` 形——避免 parseTaskMd 全文扫描误读，设计正确
- WorkerStore.upsert 在 workers.lock 下原子替换写入；PM 双窗竞态派发同 taskKey 时注入幂等 + upsert 去重兜底
- `_apply_bootstrap_line` 行级更新保全手写节/注释/行尾（CRLF 保留）；`^key\s*:` 不会误匹配缩进/前缀相似的键

## 汇总

- **总问题数**: 34（前置门禁 2 ⚠️ + Q-AC 9 + Q-VC 1 汇总行 + Q-COV 9（含 2 个 ⚠️ 子项）+ Q-X 8 + Q-S 5（含 1 ⚠️）+ 代码审查 7（0 High / 2 Low / 5 Info））
- **充分 ✅**: 30
- **证据不足 ⚠️**: 4（ac_fingerprint 失配、task-012 vc_refs 空档（已注明）、F6 遍历洪泛有界无专门测试（design 已接受）、Q-S-003 read-scope 耗时对照证据缺失）
- **无证据 ❌**: 0

**质检结论**: ⚠️ **有条件通过**

功能、覆盖与代码质量全部达标：16/16 VC 有可复现 [VERIFY] PASS 证据（抽查复跑全绿），9/9 AC 充分，audit_phase.py PASS（本机复跑 exit 0），check/biome/tsgo 复验干净，multi-workers 全量 433 passed 零失败，agent-team-loop 套件复跑零失败，代码审查无阻断缺陷。唯一实质门禁问题是 ac_fingerprint 记录值不可复现（AC 集合本身已独立证明零漂移）——按仓库既有先例（goal-autopilot v3、mw-widget-terminal-lifecycle 重锚）属元数据层缺陷，须在合入前完成重锚（下表 P-1）。

## 未通过/不足问题行动计划表

| ID | 问题 | 行动计划 | 责任 |
|----|------|---------|------|
| P-1 | ac_fingerprint `e9719d9067b2` 不可复现（canonical 重算 `f5b29879fad4`；12 种变体均不匹配） | 按 mw-widget-terminal-lifecycle 重锚先例：在 evidence-requirement.md「锁定指纹」表将 ac_fingerprint 重锚为 canonical 管道值 `f5b29879fad4`，并加 fingerprint_note 注明原值口径不可复现、AC 集合零漂移已独立证实（ac_ids 逐项 == AC-001..009）；不得仅手改哈希绕过门禁——note 必须说明验证链 | PM（system-design / 收尾 owner） |
| P-2 | spec §2.2 指定的 read-scope 套件前后耗时对照未留档；design §9「双根不新增每调用 realpath」对 deny 任务不精确 | 二选一：(a) 补一次同机前后耗时对照留档（对照基线可用 git 父提交跑 autopilot-read-scope 套件）；(b) 修订 design §9 措辞（deny 判定新增一次归一化，实测量级 ~0.1ms/调用）+ 顺手将归一化结果复用传给 deny/scope 两分支（可选微优化） | PM |
| P-3 | F6「遍历洪泛有界」无专门测试（输出截断 + caps 限流） | 已被 design D-004/§9 显式接受为已知限制（P4 无 .gitignore 场景）；建议后续 key 为 L2 有界性补一条洪泛回归用例，本 key 不阻断 | 后续 key |
| P-4 | task-012 vc_refs 为空（模板差异）+ 本 key 任务书无 Error Fingerprint 节 | 无需行动：理由已在任务书内注明，VC 账本完整（001–011 并集 = 16/16）；建议下次 key 模板统一 | 记录在案 |

## 二次印证结论

1. **spec 全约束 ↔ Q 覆盖**：§2.1/2.2/2.3/2.4 与 §1.4 范围外项（多控制工作区 N:1、UE 专用类型、资产编辑、AGENTS.md 合并、pi 核心）均未越界实现——改动面无一处触碰 pi 核心（GC-1 ✓）、无中心化调度（GC-2 ✓）、Worker 仍独立进程（GC-3 ✓）、_workers.parallel 写仍走 O_CREAT|O_EXCL 锁（GC-4 ✓）、白名单未动（GC-5 ✓）、goal 锚点在控制根（GC-6 ✓）。性能两项：trace 延迟采信机制不变 + 实测锚定（✅）；read-scope 新增开销量级安全但对照证据缺失（⚠️ Q-S-003）。
2. **Function Flow 节点 ↔ Q**：dispatch 读 target.yml（Q-VC-013/009 生成侧）→ 渲染失败非零退出（VC-007 + dispatch reject + PM 拒派）→ task.md 落控制根（VC-005）→ launcher spawn cwd=game（VC-004）→ game/eng 读写（VC-009）→ trace/output/phase 落控制根（VC-005/014）→ deny 命中 block+trace（VC-011）→ PM 吸收（既有 deliverWorkerResult + AC-002 control-files=complete）——每节点均有对应 Q。
3. **Coverage Matrix 异常路径行 ↔ Q-COV**：F1–F9 全部有 Q-COV 行（含异常路径）；唯 F5 未知节与 F6 洪泛为间接/接受性覆盖（见 ⚠️ 子项），其余异常路径均有直接用例。
4. **task vc_refs 空但 AC 有 VC**：仅 task 012（文档收尾），已注明理由；16 VC 与 9 AC 的任务级引用并集完整无缺口。
5. **指纹复核**：本机 canonical 管道复算与 12 变体排查均不能复现记录值（细节见前置门禁行与 P-1）。

**最终判定**: ⚠️ 有条件通过——完成 P-1（指纹重锚，必做）后即可合入；P-2 建议随合入或紧随其后处理；P-3/P-4 记录在案不阻断。

---

## PM 处置记录（2026-09-17，吸收 worker 结果后）

| 项 | 处置 | 结果 |
|----|------|------|
| P-1 指纹重锚 | evidence-requirement.md ac_fingerprint 改为 `f5b29879fad4`，附 ac_fingerprint_note（验证链：12+1 变体不可复现 → AC 集合零漂移双证 → canonical 管道 PM 独立复算一致） | 已完成 |
| P-2 耗时对照 | 选方案：design §9 [EXEC 注记] 修订措辞（deny-glob 任务最 2 次 realpath/调用，增量 ≈ 0.088ms 引用既有实测）；归一化复用登记 CR-1 候选 | 已完成 |
| P-3 F6 洪泛回归用例 | 登记验证欠债（design D-004 已接受有界性） | 记录在案 |
| P-4 task 模板统一 | 登记验证欠债 | 记录在案 |
| task-012 vc_refs 空 | 任务卡已注明理由（文档收尾 task，无运行时断言） | 接受 |

质检结论维持：⚠️ 有条件通过 → P-1/P-2 处置后合入条件满足；P-3/P-4 为不阻断欠债。
