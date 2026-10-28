# quality-gate-report-20261013 — mw-worktree-junction-guard 收口期独立质检

> **产物路径偏差声明**：任务卡指定唯一产物为 `.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md`，但本 worker 的运行期写面（mw-write-surface v1 + 工具集）只允许在本任务目录写 `progress.md | report.md | report-<slug>.md`。因此全文写在 `workers/wjg-qg-evidence-closure/report-quality-gate-report-20261013.md`，内容与指定结构逐节对应；**请 PM 将本文件原样提升/复制到 evidence 路径**。除此之外未写任何路径。

- **审计者**：`wjg-qg-evidence-closure`（卡 `tasks/T-QG-evidence-closure.md`，type: review）
- **时间**：2026-10-14（本 key 收口期）
- **范围**：AC-001..AC-013 逐条证据链闭合判定；P-025 类反假证据抽样复核（≥8 条，实际 16 条）；AC-003/AC-009 反向对照定位；design D-4/D-10/D-11/D-12 决策-实现一致性；achieved.md 遗留表时效性；AC 间交互漏项扫描。
- **输入清单**：
  - 基准：`spec.md`（AC + §7 决策 D-1/D-2/D-9..D-12）、`design.md`（§3.5 D-4、§5.3 巡检域、§9 验证矩阵、§4.3 模板）、`achieved.md`。
  - 证据：`evidence/T-W01..T-W08-*.md`（9 份，含 T-W05b）、`evidence/research/design-*-20261013.md`（6 份 RQ）与 3 份 20261009 spec 级 RQ（存在性核对）。
  - 实现：`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`（全文）、`shared/bash-segments.ts`、`shared/implementation-gate.ts`、`index.ts`；`packages/multi-workers/worktree_cmd.py`（全文）、`worktree_registry.py`（全文）、`worktree_doctor.py`（全文）、`tree_watch.py`、`launcher.py`、`mw.py`、`mw_common.py`（相关段）；`scripts/diff-model-catalog.mjs`（全文）。
  - 测试：`worktree-junction-guard-decide.test.ts`（全文）、`worktree-junction-guard-coverage.test.ts`（全文）、`agent-team-loop-bash-segments.test.ts`、`test_worktree_cmd.py`、`test_worktree_doctor.py`、`test_worktree_e2e.py`、`test_tree_watch.py`；`package-lock.json`（期望集直数）。
  - PM 门禁输入（作为输入，不替代执行）：`npm run check` exit 0（1154 files）；pytest 四文件 72 passed；vitest 23 + 9 passed；真机只读复检 = 1 worktree / 0 deleted tracked / 14 reparse points / 注册表文件不存在。
- **只读限制（未覆盖面声明）**：本角色工具面为 read/find/grep/ls，**不能执行任何命令**。所有"实跑结果"（pytest / vitest / `npm run check` / `node --check` / 真机 `mw doctor` 与 git 计数 / T-W07 夹具复演输出）**均无法独立复现**，本文只做**坐标与内容一致性核对**（声称的断言、行号、用例、输出是否真实存在于源码与证据文件中），此类判定一律标注 `[无法独复现]`，不写"已复现"。本审计不覆盖：Windows 环境既有测试基线失败（AGENTS.md 89 例 + test_launcher 1 例语料缺失）、其它 key 的孤儿目录、spec/design/achieved 之外的文档。发现实现与设计不一致处只记录 `文件:行号`，不改任何文件。

---

## 问题清单与核查结果

> 三态：✅ 充分 / ⚠️ 不足 / ❌ 无证据。凡最强证据为实跑输出的，已在备注标 `[无法独复现]`（坐标与断言本身均已逐条核对存在且相符）。

| 问题 ID | 描述（AC 断言摘要） | 状态 | 证据坐标 | 备注 |
|---|---|---|---|---|
| Q-001 (AC-001) | 含 reparse point 的 worktree 执行 `git worktree remove`（含 `--force`）执行前被 block，命令零副作用 | ✅ | `test/suite/worktree-junction-guard-coverage.test.ts:254-277`（worker 模式：isError=true、`executedBashCommands===[]`、trace 1 行）、`:279-295`（PM/交互模式同拦）、`worktree-junction-guard-decide.test.ts:143-160`（插值事故形态 block，basis=reparse-point） | 真链路经真实 `activate(pi)`（coverage:161），注册断链会假绿失效（P-002 靶心成立）。实跑结果 `[无法独复现]`，断言坐标齐全 |
| Q-002 (AC-002) | block 文本含可照抄正规命令 + 链接路径与目标；D-11 非	worktree 穿透形态给第二套文本（`cmd /c rmdir`） | ✅ | `worktree-junction-guard.ts:657-667`（§4.3 模板逐字：`mw worktree rm "<target>"`）、`:707-741`（第二套：`cmd /c rmdir "<link>"`、MAX_PENETRATION_LINES=3、总数尾注）；decide 测试 `:324-338`（第二套逐字断言 + `not.toContain("mw worktree rm")`）、`:367-375`（注册 worktree 走 §4.3 文本）；coverage `:297-315`（真实 tool_call 层文本断言） | 模板与 design §4.3 逐字一致（已逐字比对） |
| Q-003 (AC-003) | 不含 reparse point 的 worktree 不被误拦，有反向对照 | ✅ | decide `:178-195`（干净字面 + 四种可解析插值 allow）、`:284-304`（裸名无匹配 / 目标不存在 allow）；coverage `:318-334`（clean 目标放行**且真执行** `executedBashCommands===[command]`）、`:336-352`（只读命令 3 条全执行）；fail-closed 面反向用例 `:205-227`（unknown-var/glob/尾分隔符 = block） | 不误报侧定位到具体用例（纯函数层 + 真链路层双层） |
| Q-004 (AC-004) | 六步顺序固定不可跳步，无跳步开关 | ✅ | `worktree_cmd.py` STEP_NAMES（enumerate/validate/unlink/recheck/remove/report）+ `remove_worktree`；`test_worktree_cmd.py:331-362`（断言 steps==[1..6]、名称序、`step N/6` 日志 6 行）；`mw.py:6608-6613`（rm 子命令仅 path/--project/--json）+ `test_rm_has_no_step_skipping_switch:675` | 步 2 先全量判定、步 2→3 零写入由冻结列表实现（`worktree_cmd.py` remove_worktree 步 2 注释与代码） |
| Q-005 (AC-005) | 只摘链、主树零损伤（清单/哈希前后一致） | ✅ | `test_worktree_cmd.py:331-362`（manifest before==after、victim 内容不变、主链仍在）；`test_worktree_e2e.py:297-367`（manifest 6/6 逐字段一致：size/sha256/mtime_ns + 链目标内容哈希）；阳性对照 `test_worktree_cmd.py:492-516`、`test_worktree_e2e.py:401-427`（裸 remove 删 3 文件） | 阳性对照非空过（夹具成立性有机器证明） |
| Q-006 (AC-006) | 链接目标三分类（D-1）；foreign ⇒ fail-closed 零摘链 | ✅ | `worktree_cmd.py:87-107`（`classify_link_target`：worktree > repo > foreign）；`test_worktree_cmd.py:143-203`（TestClassification 6 例：repo/worktree/foreign、嵌套、短名/junction 别名）；`:363-390`（foreign + repo 混合 ⇒ `unlinked==[]`、两链仍在、remove 未调用、"ABORT at step 2/6"+"未降级继续"） | 备注：class ②（自指链）为纯函数级用例 + 与 class ① 共享同一事务路径（均摘链后继续）；npm ci 自指链语料是 design §7-2 声明的外推，未实跑（设计允许） |
| Q-007 (AC-007) | 任一步失败 ⇒ 中止保留现场，明示"未降级继续"，无补偿写 | ✅ | `test_worktree_cmd.py:363-390`（步 2）、`:393-409`（步 3：unlinked=[]、链仍在）、`:410-439`（步 4：已摘链不回写、remove 未调用、现场保留）、`:440-449`（步 5：现场保留） | 四条中止路径全部注入失败并断言 git remove 从未被调用（RecordingGit.calls） |
| Q-008 (AC-008) | `add` 默认不建链；`--link-deps` 建链并登记（target/created_at/created_by） | ✅ | `worktree_cmd.py` add_worktree；`worktree_registry.py`（REQUIRED_FIELDS 含 target/created_at/created_by；锁 + tmp + os.replace + 读回验证）；`test_worktree_cmd.py:536-554`（默认无链且**不写注册表**）、`:556-581`（--link-deps 建链 + 三字段断言 + rm 注销）、`:519-535`（dry-run 零落盘） | 反向对照"不建链不写注册表"有显式断言（`registry_path(...).exists()` 为 False） |
| Q-009 (AC-009) | `mw doctor` 报遗留链且不误报；D-2 三域 + D-10 期望集减法 + D-12 跳过存活链 | ✅ | `worktree_doctor.py`（`_registry_domain:138`/`_repo_local_domain:174`+`expected_link_keys:110`/`_scan_roots_domain:211`+`_link_key:193`）；`mw_common.py:3750-3762`（issue，可翻 rc）、`:3771`（签名）、`:3809-3812`（唯一函数内 import + 装配）、`:3948-3956`（count 非零才打印）；`mw.py:599-611`+`:6328`（--worktree-scan-roots）；`test_worktree_doctor.py` 14 例（减法两态 `:191`、前缀 `:245`、短名 `:227`、域 c 开关 `:269`、D-12 两例 `:294`/`:318`、预算 `:365`、干净夹具 rc 不变 `:391`、本仓 14==14 `:448`） | 本仓实测（rc=1 既有、零 worktree_links 行）为 PM/W-03 实跑 `[无法独复现]`；`test_this_repo_reports_no_worktree_links` 把该反向对照固化为常驻用例 |
| Q-010 (AC-010) | 骤降触发 / 正常波动不触发 | ✅ | `tree_watch.py:107-116`（`max(20, floor(1%·n+0.5))` round-half-up，非 ceil）、`:44`（DEFAULT_INTERVAL_POLLS=6）、`:68-90`（PI_TREE_WATCH_SEC，0=关）；`test_tree_watch.py:103-206`（公式/dist 面/触发(600→300)/单文件/git rm/dist clean/两样本门槛）；`launcher.py:1707-1735`（挂点，异常吸收）+`:1886` | 阈值公式与 design §6.1 口径一致（2756→28、2822→28 均 round-half-up）。design §6.1 动作(3) 的 doctor-issue 升级未实现（见 F-02，非 AC 文本要求） |
| Q-011 (AC-011) | 断链触发并给路径 / 完好链不触发 | ✅ | `test_tree_watch.py:218-278`（goodlink 不触发 / brokenlink 触发含路径 / 真目录+清单迁移）、`:280-292`（PI_TREE_WATCH_SEC=0 零 git 子进程）；`tree_watch.py` `scan_links`/`resolve_link_target`（lstat/lexists 语义） | 反向对照（完好链、真目录）定位到具名用例 |
| Q-012 (AC-012) | 端到端：新流程清理后主树 mtime 与内容零变化，全程无误放行；夹具两向 | ✅ | `test_worktree_e2e.py:269-399`（manifest 6/6 逐字段一致；事件序 `git_removes[0] > max(unlink_indexes)`、`:351` `remove_checks==[False]`；注册表事务后为空；doctor count==0）；`:401-427`（阳性对照删 2 tracked + 1 链目标） | 已记录偏离：走 `cmd_worktree` DI 面（真实 CLI 因 `mw.py:4502 _repo_root()` 返回安装仓无法指向夹具，遗留 6 / P-029）；DI 面即 CLI 实际入口（`mw.py:6283`）。实跑 `[无法独复现]` |
| Q-013 (AC-013) | `diff-model-catalog.mjs` remove 前摘链（或不建链）；夹具两向 + manifest 全 0 | ✅ | `scripts/diff-model-catalog.mjs:161-187`（`detachBaselineNodeModulesLink`：lstat 判链、win32 `cmd /c rmdir` 无 /S、自检必须 ENOENT）、`:281-305`（finally：摘链失败 ⇒ exitCode=1 + 手工提示 + 保现场 + 跳过 remove 与 rmSync）；T-W07 证据 §3（POS 复刻事故 / NEG manifest 全 0 / ABORT 复演，manifest 键与 AC-012 原语一致） | 生产改动逐行核对相符。夹具复演与 `node --check` 为一次性运行 `[无法独复现]`；无常驻回归测试（见 F-05 跟进项） |

---

## 抽样复核机器证据（P-025 反假证据，16 条）

> 方法：对每条"已机器校验/有断言/实测输出"类声称，回到源码/测试/证据文件核对坐标存在性与内容相符性。结论 = 相符 / 不符（不符者记 ❌ 并给反例坐标）。实跑输出本身 `[无法独复现]`，但**声称的坐标与内容全部核对**。

| # | 声称 | 核对坐标 | 结论 |
|---|---|---|---|
| S-01 | coverage 测试 block 组 `executedBashCommands === []`（零执行） | `worktree-junction-guard-coverage.test.ts:272`（用例 a）、`:294`（b）、`:314`（c）三条 `toEqual([])`；反向 `:323` `toEqual([command])`、`:344` `toEqual(commands)` | **相符**（BashOperations 记录器 stub 于 `:141-149`，真实 activate 于 `:161`） |
| S-02 | e2e `remove_checks == [False]`（remove 时链已摘） | `test_worktree_e2e.py:351`（`assert recorder.remove_checks == [False]`；记录器 `:241-248` 在 git remove 回调内当场 `lexists`） | **相符** |
| S-03 | 真机 `worktree_links` 计数 0（干净仓零行输出） | `test_worktree_doctor.py:448-468`（count==0、stdout 无 worktree_links、rc==healthy 三角断言）；`mw_common.py:3948-3950`（`if worktree_links and worktree_links.get("count")` 才打印） | **相符**（断言常驻；真机实跑 `[无法独复现]`） |
| S-04 | D-10 期望集 14 条（= 磁盘 14 条） | `package-lock.json` 直数：`"link": true` 恰 **14** 处（`:785-820` 9 条 `node_modules/@earendil-works/*` + `:4299-4318` 5 条 `node_modules/pi-extension-*`）；`worktree_doctor.py:110-134` `expected_link_keys` 读 `packages[*].link===true` | **相符**（14=9+5，与 design §1 口径一致；本审计直接复算） |
| S-05 | delete-penetration 两套文本（任务卡指向 guard `:712` 附近） | `worktree-junction-guard.ts:707`（MAX_PENETRATION_LINES=3）、`:709-741`（第二套：`穿透 reparse point` + 逐条 `cmd /c rmdir`）、`:657-667`（§4.3 模板）；decide `:324-338` 逐字断言两套（含 `not.toContain("mw worktree rm")`） | **相符** |
| S-06 | T-W07 `node --check` 退出码 0 | T-W07 证据 §2（`NODE_CHECK_EXIT=0`）；本审计通读 `scripts/diff-model-catalog.mjs` 全文，try/finally 配对与函数结构完整 | **[无法独复现]**；无反例，结构与声称一致 |
| S-07 | G4 阈值公式 = `max(20, round_half_up(1%·n))`（非 ceil） | `tree_watch.py:107-116`（`max(MIN_COLLAPSE_THRESHOLD, int(math.floor(scaled + 0.5)))`）；`test_tree_watch.py:103`（`test_collapse_threshold_formula` 固定口径） | **相符** |
| S-08 | G4 默认 6-poll 节奏（30s）、`PI_TREE_WATCH_SEC` 覆盖、0=关 | `tree_watch.py:44`（DEFAULT_INTERVAL_POLLS=6）、`:68-90`（watch_interval_polls：未设=6、≤0=0、正数 ceil 换算）；`test_tree_watch.py:294`（默认 6 poll）、`:280`（env=0 零 git 子进程）、`:360`（秒覆盖） | **相符** |
| S-09 | G1 注册点（卡：`index.ts:61` + guard `:180`） | 实测：调用在 `index.ts:70`（`registerWorktreeJunctionGuard(pi)`），`:61-69` 为其注释块；guard 侧 `worktree-junction-guard.ts:179`（函数）+ `:180`（`pi.on("tool_call"`）；T-W06 证据实测值即 `:70` | **相符**（注册存在、三模式覆盖：worker/PM 分支之前）；achieved.md 的 `:61` 指注释块起点，调用行微偏 → 记 F-01，非假证据 |
| S-10 | 注册点计数 6→7（`.on("tool_call")`） | grep `packages/coding-agent/src`：恰 **7** 处（worker-mode 2、implementation-gate 1、protected-config 1、pm-state-guard 1、worktree-junction-guard 1、xkey-gate-guard 1） | **相符** |
| S-11 | pytest 72 passed 的构成 | 逐文件清点用例数：`test_worktree_cmd.py` 37 + `test_worktree_doctor.py` 14 + `test_worktree_e2e.py` 2 + `test_tree_watch.py` 19 = **72** | **相符**（实跑 `[无法独复现]`，构成自洽） |
| S-12 | vitest 23 + 9 passed | decide 测试 `it(` 计数 = **23**（8+8+6+1）；coverage 测试 = **9**（4 纯函数 + 5 真链路） | **相符** |
| S-13 | 真仓注册表文件不存在（尚无 mw 建的链） | `ls .mw/`：无 `worktree-registry.json`（有 dispatch.yml/beat/mw.pid/serve.meta/window-model） | **相符**（本审计直接核验） |
| S-14 | launcher `_poll_once` 挂点（`launcher.py:1706` 附近） | `launcher.py:1707`（def）、`:1714`（tree_watcher 形参，默认 None）、`:1725-1729`（tick + emit_alarms，异常吸收）、`:1886`（TreeWatch 构造）、`:1915-1918`（主循环 7 实参） | **相符**（T-W04 表格坐标逐一命中） |
| S-15 | T-W02 六步步序与 `--json` 契约 | `worktree_cmd.py` STEP_NAMES 1-6；`test_worktree_cmd.py:343-346`（steps==[1..6]+名称）；`:622-640`（rm --json 六步报告）；`mw.py:6582-6617`（add/rm/list 二级 parser） | **相符**（T-W02 的 mw.py 行号 6271/6564/6717 相对当前树漂到 6283/6582/6734，属 spec §6 坑 1 预告的漂移，符号全部可定位，非假证据） |
| S-16 | mw_common doctor 三处挂载（issue/签名/装配/条件文本） | `mw_common.py:3750-3762`（worktree issue 块）、`:3766-3772`（doctor_report 签名 + worktree_scan_roots）、`:3809-3812`（唯一函数内 import + report["worktree_links"]）、`:3948-3956`（format_doctor_text 条件打印） | **相符**（T-W03 坐标 3745-3762/3766-3772/3804-3812/3946-3957 全部落在实测区间内） |

**抽样结论：16/16 相符（其中 2 条实跑类 `[无法独复现]`，均无反例）。未发现 P-025 类假证据：所有"已机器校验"声称均能定位到真实存在的断言/代码/输出记录。**

---

## 汇总

| 项 | 数 |
|---|---|
| AC 总数 | 13 |
| ✅ 充分 | **13** |
| ⚠️ 不足 | 0 |
| ❌ 无证据 | 0 |
| 抽样复核机器证据 | 16 条（16 相符 / 0 不符） |

**质检结论：✅ 通过。**

- 13 条 AC 的证据链全部闭合：每条都能定位到常驻测试（TS 23+9、Python 72）或逐行可核的生产代码 + 夹具证据；AC-003/AC-009 的"不误报"侧均有具名反向用例（干净目标放行且真执行、期望集减法后静默、干净夹具 rc 不变、本仓 14==14、域 (c) 跳过存活链）。
- 反假证据（第一优先级）：16 条抽样全部核对相符，无一例"声称有证据而证据不存在"。
- 决策一致性：D-4（动词面边界）、D-10（期望集减法）、D-11（两套文本 + `rmdir /S`/无尾分隔符 `rm -rf <link>` 仍放行，decide `:306-322`/`:390-402` 双处反向用例）、D-12（跳过存活链，`test_worktree_doctor.py:294/:318`）均与代码/测试一致。
- 通过附带 4 项非阻塞跟进（F-01/F-02/F-05/F-06，见下），均不构成 AC 级欠债。

## 未通过问题行动计划

无未通过（❌=0）问题。以下为发现的偏差与跟进项（非阻塞）：

| ID | 发现 | 根因 | 所需动作 | 建议负责面 |
|---|---|---|---|---|
| F-01 | achieved.md「注册点 `index.ts:61`」坐标微偏：实际调用在 `index.ts:70`，`:61-69` 是注释块（T-W06 实测 `:70` 正确） | 多会话并发编辑下行号漂移，achieved.md 取了注释块起点 | achieved.md 收口时把坐标改为 `index.ts:70`（或写"index.ts:61-70 注册块"） | PM（文档面） |
| F-02 | design §6.1 AC-010 动作(3)「骤降 + 同窗口 link_inventory delta ⇒ 升级为 doctor issue（`_doctor_issues`）、mw doctor rc=1」**未实现**：tree_watch 只落 stderr 告警 + 状态文件（T-W04 残留 5 自认移交 T-W03 写域，T-W03 未接）；mw_common 无任何 tree-watch 消费点（grep 无引用） | 该升级横跨 W-04（采样）与 W-03（doctor 段）两张卡的写面，双方都未认领，掉进卡缝 | 二选一：(a) 在 achieved.md「遗留」表登记该项（声明为接受的设计降级，注明 AC-010/011 文本不含此项）；(b) 立 follow-up：`.mw/tree-watch.json` 的 alarms/events 被 `mw doctor` 读取并入 `_doctor_issues` | PM（决策）+ 后续 key（multi-workers Python 面） |
| F-05 | AC-013 是唯一无常驻回归测试的 G（T-W07 复演脚本在 %TEMP% 已按夹具硬约束清理，验证输出仅存于证据文件） | 卡片允许"夹具内等价步骤复演"，未要求入库测试 | 建议补一条 pytest（复用 `test_worktree_e2e` 夹具原语，对 `detachBaselineNodeModulesLink` 源码做 NEG/ABORT 断言），或在遗留表声明"证据归档即闭环" | 后续 key（multi-workers 测试面） |
| F-06 | 无用例固定「处方命令本身被 G1 放行」：`mw worktree rm "<wt>"`、`cmd /c rmdir "<link>"` 两条 allow 断言缺失。结构上成立（guard 只覆盖 git worktree remove/rm 与 rm/Remove-Item 穿透形态，`mw`/`cmd` 头词 ⇒ `notRemove`），但无回归锚 | W-05/W-05b 用例面未含处方命令 | decide 测试补 2 条 allow 断言（防未来动词面扩张误拦处方） | 后续 key（coding-agent 测试面） |
| F-03（文档） | design §3.3 规则表 (c) 写「尾分隔符剥掉后按 (a)」，实现是尾分隔符一律 `glob` block（与同文件流水线图 P6 及卡片一致，取 fail-closed）；W-05 残留 2 已记录 | 设计文档内部两处表述不一致，实现择严 | 修订 design §3.3 规则表 (c) 文本对齐实现（或明示"以流水线图为准"） | PM（文档面） |
| F-04（文档） | design §5.1 注册表文件名 `worktrees.json` 与实现 `worktree-registry.json` 不一致（design §5.3 已自行改口为后者） | 文档早期草案残留 | 修订 §5.1 文件名 | PM（文档面） |

## 二次印证结论（漏项扫描）

1. **G1/G2 同版本要求**：满足——同一工作树共存（`index.ts:70` 注册 + `mw.py:6582-6617` 子命令 + `mw.py:6734` dispatch），阻断文本引用的 `mw worktree rm` 命令真实存在（parser 契约有测试 `test_parser_contract:661`）。无单一测试同时断言两者存在，属发布协调属性而非可测单元；achieved.md 已注明"G1/G2 同版本发布"，无需动作。
2. **AC-013 复用 AC-012 原语**：成立——T-W07 夹具复演的 manifest 判据键（`removed/added/content_changed/mtime_changed/missing_after`）与 `test_worktree_e2e.py::_manifest`（:176-205）的对照键一致；摘链原语（`cmd /c rmdir` 无 /S 无尾分隔符）与 G2 步 3 同构。
3. **`mw doctor` 退出码与既有 doctor 断言的交互**：已覆盖——worktree issue 进 `_doctor_issues`（`mw_common.py:3750-3762`）可翻 rc；干净面"rc 不变"有 `test_clean_fixture_zero_findings_zero_lines_rc_unchanged:391`（rc_off==rc_on + 零行输出）与 `test_this_repo_reports_no_worktree_links:448`（rc==healthy 逻辑）双锚；翻转面有 T-W03 §5 CLI 级实测（干净 rc=0 / 加链 rc=1）`[无法独复现]` + issue 路径代码核对。既有 doctor 回归（65 passed）为 W-03 实跑 `[无法独复现]`，已记录。
4. **遗留表时效性**：逐条核对 achieved.md 遗留 1-10，**未发现已被本轮实现解决的过时条目**：#2/#3（不穿透动词放行、处方前 3 条）与代码现状一致（decide 反向用例 + MAX_PENETRATION_LINES=3）；#4（G5 中止保现场 = 活雷）与 `diff-model-catalog.mjs:281-305` finally 行为一致；#6（`_repo_root` 返回安装仓）与 `mw.py:4502` 一致；#7（未登记孤儿链不在默认域）与域 (c) opt-in 一致。
5. **新发现漏项**：F-02（design §6.1 动作(3) 跨卡缝未实现未登记）是本次审计唯一实质漏项；F-06（处方命令放行无断言）为加固建议。其余交互面（G1 注册面三模式、G5 中止路径、D-12 与域 (a) 的重复报告）均已在对应证据/残留中显式记录。
6. **时间线自洽性**：T-W07 的 `npm run check` Run#2/#3 因并发会话文件（decide.test.ts 在 W-05b 会话写入中）报 1 条 biome warning 退出 1，行号漂移（:158→:172）与"另一会话正在编辑"解释自洽；该文件随后由 W-05b/W-06 定稿，PM 终局门禁 `npm run check` exit 0（1154 files）`[无法独复现]`，与 W-06 证据（1154 files clean）一致。

---

**审计者只读声明（复）**：本报告全部结论基于源码/测试/证据文件的坐标与内容核对；所有实跑结果（pytest/vitest/npm run check/node --check/真机计数/夹具复演）无法独立复现，均标注 `[无法独复现]`；未修改任何文件（本报告文件除外）。

QG: 通过 | AC 总数 13 | ✅ 13 | ⚠️ 0 | ❌ 0 | 抽样复核 16 条
