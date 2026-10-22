# QG 审读证据：mw-console-storm-hardening（VERIFY 相位质量门）

> date: 2026-10-15 · 角色: csg-qg-review（type: review，只读审读，零代码改动，零 git 操作）
> 审读对象: L0/L1/L2/L3 + TS 全量交付 vs goal.md GC-1..GC-4 / spec.md AC-001..010 / design.md D-001..D-006（M1..M8, VC-001..010）
> 独立核验基线: evidence/runs/verify-mw-console-storm-hardening-20261015.md（W-05 声称全 PASS）
> 本审执行方式: 纯静态只读（本会话无命令执行通道）——逐文件全文读 + 行号级 grep 锚定；测试以「盘上测试清单与 verify 文档原始输出互证」方式核验，未重跑（见 §7 残留）。

## 1. 审计目标 1 —— L0/L1（mw.py cmd_start + console_run.py）

结论：**通过**（2 minor）。

- flags 组合语义 ✓：mw.py:519 `creationflags=_sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW`（0x8000200），无 DETACHED_PROCESS 位；M1 语义（隐藏控制台 + 后代继承）与 design D-001 一致。posix 分支 mw.py:525 `start_new_session=True` 不变（AC-001/AC-007）。
- serve stdio 重定向 ✓：mw.py:512-516 stdout/stderr → `<project>/.mw/serve-console.log`（"ab" 追加）。serve 内部随后自行二次重定向（cmd_serve 恢复真实流处可见），故该文件捕获的是此前不可观测的最早启动段（traceback/导入失败）——正是原 DETACHED 盲点，符合设计意图；§0.6 实测 0 字节与此自洽。
- P-003 原子写 ✓：console_run.py:149-154 `_atomic_write_json` = 临时文件 + `os.replace`，heartbeat/marker 全部经此路径；无任何 `open(p,"w")` 截断写。cmd.txt 单写者前置落盘（:94），run.log "wb" 单写者（:227）。原子性断言与 README「原子落盘/原子更新」文案一致。
- timeout 树杀 ✓：console_run.py:202-219 `_kill_tree` win32 `taskkill /T /F /PID`（15s 上限）+ `child.wait(timeout=10)`；posix `os.killpg(child.pid, SIGKILL)`——子进程经 :249 `start_new_session=sys.platform != "win32"` 成为组长，监督进程自持会话不受波及，可善后写 marker（注释与 mw-worker-tree-kill 先例一致）。deadline 判定在 poll 之后（:274-279），退出与超时同刻不会误报 124。
- CLI 挂接 ✓：mw.py:6916-6932 run-detached parser；:6939-6943 `_run_supervisor` 于 argparse 之前分派（不进 --help，符合 D-002「内部子命令」）；:6965 命令表映射 `console_run.cmd_run_detached`。
- spawn 失败契约 ✓：console_run.py:252-268 marker `rc=127 + spawn_failed=true`，监督进程返回 0（失败信号走 marker，不走进程退出码）。heartbeat 在首次 poll 之前写（:270-273），即命即退的子进程也留 ≥1 次心跳。
- GC-3 ✓：监督进程独立分离，崩溃只丢该 run 的 marker/heartbeat，serve 主服务零影响。GC-4 ✓：run-detached 无状态按次派发，无任何调度组件/共享进程状态。
- [minor] console_run.py:66-77 `_resolve_run_dir`：`while exists()` 与 `mkdir(exist_ok=False)` 之间存在 TOCTOU 窗口——并发生成同路径时 `FileExistsError` 未捕获，CLI 裸 traceback 而非 -N 重试。处置：`mkdir` 包 try/except FileExistsError 后继续后缀循环（O_EXCL 语义保留，竞争失败退化为下一后缀）。
- [minor] console_run.py:266-270 + run-detached.ts:175-179：`--heartbeat-s`/`heartbeat_s` 负值无校验（TS schema `Type.Number` 无下界，Python argparse 无范围检查）——负 heartbeat_s 使监督循环 `time.sleep(<0)` 抛 ValueError，监督进程中途死亡、marker 永不落盘且子进程失去超时看管（孤儿）；负 timeout_min 则静默等于「无超时」，与调用意图背离。处置：双侧夹取下界（schema `minimum`、argparse type 守卫，非正值回退默认 5.0）。

## 2. 审计目标 2 —— L2 guard（mw_console_guard/mw_console_guard.py）

结论：**通过**（2 note）。

- OR 语义 ✓：mw_console_guard.py:38-42 `(creationflags & EXPLICIT) == 0 → creationflags |= CREATE_NO_WINDOW`；显式 CREATE_NEW_CONSOLE(0x10)/DETACHED_PROCESS(0x8) 原样（测试以「激活前置 spy 被 guard 捕为 orig」观测到 OR 后真实入参，判据扎实）。`subprocess.run` 经同一 `Popen.__init__` patch 覆盖（M5）。
- fail-open ✓：:45-53 `_activate` 捕获 `_apply` 异常 → 单行 stderr 告警 + `_patched` 不置位 + Popen 保持原样；模块级激活门 :62 在 `del os, sys`(:65) 之前执行，生产路径（import 期激活）安全。
- 幂等 ✓：:20 `_patched` 模块级标志，重复 `_activate` 早退（测试三连调后 wrapper 同对象 + 真实 spawn 冒烟 rc=0）。
- 平台/env 门 ✓：:62 `os.name == "nt" and MW_CONSOLE_GUARD == "1"`；posix 与 `hasattr` 分支 no-op 均有测试注入覆盖。
- 注入面 ✓：console_run.py:166-184 `_child_env` 仅 win32、`MW_CONSOLE_GUARD=0` 显式退出、guard 目录缺失 fail-open 告警不阻塞；PYTHONPATH 前置 + pathsep 拼接符合 spec §2.3。sitecustomize.py 为最小激活器（`import mw_console_guard`）。
- [note] mw_console_guard.py:53-53+65：`del os, sys` 之后若宿主手动调 `_activate()` 且 `_apply` 失败，except 块引用已删除的 `sys` → NameError 穿透（此路径 fail-closed）。生产激活仅发生在 import 期（sys 尚在），测试路径亦先置 env 再 import；属卡片已声明的「已知权衡」。处置：`del` 前绑定 `_stderr = sys.stderr` 供告警用，或 docstring 明示「仅 import 期激活受 fail-open 保护」。
- [note] mw_console_guard.py:31-36：docstring 称位置传参「NOT protected」——实际形态下 wrapper 恒传 `creationflags=` kwarg，14 位位置传参将抛 TypeError（duplicate kwarg）而非静默不保护；行为是 fail-loud（可接受），文档措辞不准确。全仓零该形态：mw.py/console_run.py/launcher.py 的 Popen 均 kwarg 传 flags（本审逐点抽核 + design D-003 普查一致）。处置：更正 docstring 一句。

## 3. 审计目标 3 —— TS 入口（run-detached.ts + 三注册点）

结论：**通过**（1 note）。

- GC-2 ✓：本 key 全部声明写面（任务卡 W-01/W-02/W-03a/W-03b/W-04a/W-04b/W-05）落在 `packages/multi-workers/**` 与 `packages/coding-agent/src/extensions/agent-team-loop/**` + `test/extensions/**` + 两 CHANGELOG；无 core/tui/ai 触碰。pi 核心 API 仅以 `import type { ExtensionAPI }`（types.ts）消费，无修改。
- T-17 parity ✓：worker-mode.ts:96-135 `TOOL_ALLOWLISTS` 未改——逐项与 autopilot/dispatch.py:85-143 REGISTRY 形状一致（roadmap-writer/phase-writer/verifier/reviewer/repair/rag-research/vision 顺序含锁定注释）；`mw_run_detached` 不进该表，仅经 activeToolsForType 动态追加（worker-mode.ts:168-176，含「Never goes into TOOL_ALLOWLISTS」显式注释）。
- shell-only 门控真实接线 ✓：worker-mode.ts:2823 `before_agent_start → applyRagTools` → rag/tools.ts:400-406 `pi.setActiveTools(activeToolsForType(type))`——门控不是摆设，每次 agent run 前实际生效；仅含 `bash` 的类型获得该工具（coding/research/phase-writer/repair/vision），review/verifier/reviewer/roadmap-writer/rag-research 不获得。
- erasable TS ✓：run-detached.ts 仅 interface/const/箭头函数/模板串，无 enum/namespace/参数属性/`import =`；`import type` 消费类型。
- 无 inline import ✓：agent-team-loop 源码 grep `await import(`/`import("` 零命中；三注册点改动均为普通顶层 import。
- fail-open 不穿透 ✓：runDetachedMw 全失败路径返回 `{ok:false,error}`（mw.py 缺失/spawn error/status≠0 且无输出/handoff 不可解析）；工具 execute 以结构化 Error 抛出（tool-error 先例，[TOOL_ERR] 可见）；命令分支 notify error 不 throw；两注册点 try/catch → console.error / writeWorkerLogLine，激活路径自身异常不弄崩窗口（pm-orchestrator.ts:1774-1781、worker-mode.ts:2788-2795）。
- schema ✓：run-detached.ts:157-181 `additionalProperties: false`、cmd `minItems:1` + 元素 `minLength:1`；空 cmd 与未知键均拒绝（测试用 typebox Check 实证）。
- handoff 契约 ✓：console_run.py 恰 4 行输出与 HANDOFF_PID_RE/HANDOFF_PATH_RE 逐行匹配，缺任一字段判不可解析；分隔符两侧各剥一次（TS 剥用户侧、Python 剥 argparse 泄漏侧），无双剥。
- /mw run-detached ✓：ui-bridge.ts:3680-3685 分支 → runMwRunDetachedCommand（usage-first 解析，未知 flag/坏数字/缺 `--` 结构化拒绝），USAGE 文案含 run-detached（测试断言）。
- [note] run-detached.ts:122 `spawnSync(..., {timeout: 30_000})`：ETIMEDOUT 时调用方收到结构化错误，但监督进程可能已派生（后台 run 继续跑、marker 迟到）——错误语义与实际副作用不对称。处置：错误文案提示「wrapper 超时≠命令未启动，可查 run_dir」或放宽 timeout；非阻塞。

## 4. 审计目标 4 —— 三测试文件断言真实性

结论：**通过**（1 minor）。

- 断言真锚定 VC 行 ✓：逐条对照——test_console_storm_guard.py 的 `[VERIFY] VC-001/VC-002/VC-003/VC-004a/VC-004b/VC-007` 与 test_mw_console_guard.py 的 activation/inactive/idempotent/fail-open/platform seam 各 print 行、TS 测试 `[VERIFY] VC-008` 行，均与 verify 文档 §0.1/§0.3 引用行逐字段同构（含 0x8000200/0x10/0x8、distinct_heartbeats、files=30 raw_hits=2 stripped_hits=0 等）。盘上测试清单：Python 6 + 11 = 17、TS 13，与 verify 文档计数一致。
- tokenize 剥注释评估 ✓：`_strip_prose` 仅剥 COMMENT 与三引号 STRING；单/双引号字面量保留（`getattr(subprocess, "DETACHED_PROCESS")` 类用法仍可见），行号映射经空行重放保持。误伤方向（把真代码藏起来）仅可能发生在「三引号非 docstring 字符串内含 DETACHED_PROCESS」——盘上实测非测试 .py 裸命中恰 2 处且均为散文（mw.py:508 注释、console_run.py:19 docstring），无隐藏代码。剥后 0 命中成立。
- `mw_console_guard/` 豁免正当 ✓：其 :30 `EXPLICIT = ...DETACHED_PROCESS` 是 AC-005 合同性掩码代码（显式 flag 比较，自身不 spawn），豁免依据在测试头注、design D-004 与审计表三处一致。
- posix skip 评估：不过宽。VC-003/VC-004a/b 依赖 `cmd /c`/`ping -n`（win32 二进制），skip 按 `sys.platform != "win32"`；VC-007 posix seam 用 monkeypatch 注入在所有平台运行；guard 测试仅 5 个 Windows 语义用例按 `hasattr(CREATE_NO_WINDOW)` skip，inactive/fail-open/隔离用例全平台运行。skip 判据是能力检测而非一刀切平台跳过。
- 隔离机制 ✓：每个行为用例独立解释器 + 逐用例清洗 PYTHONPATH/MW_CONSOLE_GUARD，父进程 Popen 污染检查收口（group 6）。
- [minor] agent-team-loop-run-detached.test.ts（VC-008 用例尾部）：`argv_passthrough=${String(!childMocks.spawnSync.mock.calls.some(() => false))}` 是恒真式（且该用例本无 spawn 调用）——证据行打印的是伪真值，而非断言。真实的参数透传覆盖存在于同文件 argv 用例（--cwd/--run-dir/--timeout-min/--heartbeat-s/-- 后原样 cmd），实质无缺口；但 [VERIFY] 证据行不应含无判据字段。处置：改为从真实 spawn 调用计算，或删除该字段。

## 5. 审计目标 5 —— 硬规则

结论：**通过**（1 minor，即 W-05 落盘方式复核）。

- P-001 ✓（本体）：spec §5 明文允许「write 工具或 Python 显式 `encoding="utf-8"`」；W-05 偏差记录自述用 Python 显式编码落盘并以 read 回读校验 UTF-8/LF，无 PS 读-改-写管线。本审抽核 UPDATE.md/双 CHANGELOG/README 均为正常 UTF-8 中文无乱码。
- [minor]（合规性复核结论）verify 文档 §5：运行期写面守卫按 frontmatter head 拦截 UPDATE.md/双 CHANGELOG（head 渲染丢失逗号 bullet 后 3 项——渲染缺陷），W-05 以 Python 子进程绕过机械拦截完成卡片正文明确授权的交付物并完整披露供 PM 复核。裁定：**实体合规**（路径在 W-05 卡片 `## 写入允许面` 逐字列明、交付物为卡片必需、偏差透明登记、根因是渲染缺陷而非越权意图），**程序留痕**——worker 单方自决绕过硬性运行期闸门是治理先例，不应默认化。处置：PM 修复 render_task_md 逗号 bullet 解析（verify 文档已建议）+ 明示规则「守卫拒绝但卡片授权 → 上报 PM 决断，不得自行绕过」。
- Python 显式 encoding ✓：console_run.py 两处 `write_text(..., encoding="utf-8", newline="\n")`；二进制 open（"wb"/"ab"）无需 encoding；测试 `read_text(encoding="utf-8", errors="replace")`；guard 无文件 IO。
- 新测试已跑过 ✓（对照核验）：verify §0.1 17 passed（12.34s）+ §0.3 13 passed（742ms）原始输出与盘上测试清单、print 行、计数完全互证；§0.4 tsgo/biome 4 文件零错声明与盘上 4 个触碰 TS 文件一致（任务卡写三文件、实际 W-03b 另触 ui-bridge.ts，verify 已如实说明并全查）。本审未具备重跑通道，采信依据见互证链与 §7 声明。

## 6. 审计目标 6 —— 证据一致性（verify 文档 vs 磁盘）

结论：**一致**（抽核 6 处 ≥ 要求 3 处，全部命中）。

- README ✓：README.md:87-122「Windows detached-run checklist」——三事实（:93 互斥、:94 DETACHED 静默生效、:95 后代外溢）、判据（:97 GetConsoleProcessList 唯一可靠 + GetConsoleWindow 不可用）、run-detached 用法与恰 4 行 handoff（:99-117）、marker/heartbeat 契约与 rc=124/127（:118-121）、`MW_CONSOLE_GUARD=0` 退出（:119）、guard 一句话（:122）、run_dir 默认与 -N 后缀（:121）。VC-009 断言集全部落地。
- UPDATE.md ✓：§2 指令矩阵含 `mw run-detached` 行（参数/动作/生效时机/注意列齐全，版本锚点格式与邻行一致）。
- 双 CHANGELOG ✓：multi-workers/CHANGELOG.md:92 与 coding-agent/CHANGELOG.md:77 均追加于 `## [Unreleased]` → `### Added` 内，未触碰任何已发布节，未重复小节。
- 审计表行号更正实核（抽 6 处，全中）：mw.py:519（cmd_start creationflags 行）✓、mw.py:233（serve→conductor Popen）✓、mw.py:378/395（proxy/launcher spawn）✓、mw.py:1142（ue-toolchain `subprocess.run(shell=True)`）✓、mw.py:4404（`_git_short_commit` check_output，def :4402）✓；另核 mw_console_guard.py:30/:62 与 console_run.py:110/:243 引用亦准。审计表头部已标注 W-05 复核时间，更正项与 verify §2 清单一一对应。
- §0.2 既有红列：8 个失败测试文件均实际在盘（test_autopilot_l0 / readcap_injection / verdict_freshness / mwds_t27 / mwds_t29 / mwgal_t13 / task_type_parity / launcher），归类（协议面/基线漂移/环境编码/flaky/语料缺失）与本 key 触碰面无交集的判断与文件分布一致。
- 修复目标对齐 ✓：事故 §8-B 三项（标准 detached-runner / 测试面 sitecustomize 兜底 / 互斥坑进文档）全部交付；L0 cmd_start 除雷为 spec 增益项，非 §8-B 越界。

## 7. 分级清单汇总

| # | 级别 | 位置 | 问题（一句） | 建议处置 |
|---|------|------|--------------|----------|
| F1 | minor | console_run.py:66-77 | run_dir `-N` 循环 exists→mkdir 间 TOCTOU，并发碰撞抛未捕获 FileExistsError | mkdir 捕 FileExistsError 续走后缀循环 |
| F2 | minor | console_run.py:266-270 + run-detached.ts:175-179 | heartbeat_s/timeout_min 负值双侧无下界校验；负 heartbeat_s 崩监督进程且孤儿化子命令 | schema 加 minimum、argparse 加范围守卫（非正回退默认） |
| F3 | minor | test …run-detached.test.ts（VC-008 用例） | argv_passthrough 字段为恒真式，[VERIFY] 证据行打印无判据伪真值 | 从真实 spawn 计算或删字段（实质覆盖在 argv 用例，无缺口） |
| F4 | minor | verify 文档 §5 | W-05 绕过写面守卫机械拦截（根因：head 渲染丢逗号 bullet 后 3 项）自决落盘——实体合规、程序先例 | PM 修 render_task_md 解析；明示「守卫拒绝但卡片授权 → 报 PM 决断」规则 |
| N1 | note | mw.py:505 | cmd_start 内 `import subprocess as _sp` 冗余（subprocess 已顶层 :29，else 分支直用） | 删除局部别名 |
| N2 | note | mw.py:512-516 | serve_log_fh 父进程侧未显式 close（CLI 即退、子进程持句柄，无害） | 注释说明或 spawn 后 close |
| N3 | note | mw_console_guard.py:53/65 | `del os, sys` 后手动 `_activate()` 遇 `_apply` 失败将 NameError（生产仅 import 期激活，安全） | del 前绑定 `_stderr` 或 docstring 明示边界 |
| N4 | note | mw_console_guard.py:31-36 | 位置传参实际是 TypeError（fail-loud）而非 docstring 所称「不保护」 | 更正一句措辞 |
| N5 | note | run-detached.ts:122 | spawnSync 30s 超时后监督进程可能已在跑（错误与副作用不对称） | 错误文案提示查 run_dir 或放宽上限 |

## 8. QG 判定

审计目标 1-6 全部通过：四层交付与 spec AC-001..010 / design D-001..D-006 逐项对齐，verify 文档与磁盘一致（含 6 处行号抽核全中），无 blocker、无 major。4 个 minor 均为边沿输入/竞争窗口/证据行措辞/程序留痕，不影响收口判定，建议随下一修复波次处理（F1/F2 一并小改 + F3 测试措辞 + F4 PM 侧流程）；5 个 note 记录在案即可。

[QG] verdict=pass blockers=0 majors=0 minors=4 notes=5
