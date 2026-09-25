# Research: autopilot done 事务与门禁机制的代码事实（spec）

## 决策问题
支撑 spec §1 范围（改动面 2 处）、§2 约束、§3 AC 的可判定性。

## 调研方法与出处
- 代码核验（本 session，2026-09-24）：`packages/multi-workers/autopilot/conductor.py`（`git diff` 守卫已含）
- 标准模板：`.agents/skills/agentic-task/scripts/advance_phase.py:69-93`（done 门禁规则）
- 事故工程安装实例：`E:\CLI_workspace\FeatureMigrator\.claude\scripts\advance_phase.py`
- 事故 handoff：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\handoff-done-closure-vocab-20260924.md`
- 测试基线：`packages/multi-workers/test_autopilot_conductor{,_exec,_stage}.py`；全量 `pytest test_autopilot_*.py` = 241 passed / 1 pre-existing failure（readcap 外部基线锚点失效，与本 key 无关）

## 发现
- F1 转写词表：`_l3_prompt` 要求 L3 output.md 含 `## Quality Gate Report` 与 `## Achieved`；`_done_transaction` step 2 将 `## Achieved` 节逐字转写为 achieved.md。
- F2 标准模板 done 门禁：achieved.md ≥200B 且含字面量 `系统行为变化`、`遗留`；pm-state.md 含 ≥1 `PASS`；`evidence/quality-gate-report-*.md` ≥1 份。`content_match` 用 `re.search` 全文匹配——`### 子节`标题同样命中。
- F3 覆盖守卫：step 2 `if not (achieved_path.is_file() and st_size >= 200): write`——≥200B 草稿永不覆盖（改动点 2 的对象）。
- F4 失败原文丢弃：advance 失败后 err 经 `_record_advance_result` 记入 timeline `config` 事件，`_done_transaction` 返回 "gated"；`_verify_loop` 收到后仅 `return False`（下 tick 原样重试），err 不进任何 dispatch prompt（改动点 1 的对象）。
- F5 无 done-blocked 修复回路：`_verify_loop` 对 verdict=below 有 repair dispatch；对 transaction 的 gate-blocked 无任何路径。
- F6 streak→stalled：`_record_advance_result` + `_advance_failure_streak`（timeline 尾部派生，400 事件/512KiB 有界）连续 `advance_stall_ticks`（默认 5）次失败 → `mark_stalled`；key 的 dispatch 事件会打断 streak。
- F7 in-flight 守卫已覆盖 l3 前缀：`_verify_loop` 开头 `for prefix in (f"ap-{key}-l3-", f"ap-{key}-repair-")`——reprompt 复用 l3 家族则无需扩守卫。
- F8 l3 预算机制现成：`l3:{key}` loop，budget = round_budget（默认 2）+ `_resume_credits`；轮次由 workers 行 frontmatter（loop/attempt）派生。
- F9 失败分类现成：`_classify_advance_failure` 对含 "missing:"/"gate blocked"/"not met"/"缺少"/"未满足" 的 err 返回 `gate-blocked` 类。
- F10 gate 失败行格式：`check_gate` 产出 `NO MATCH: {path} missing pattern '{pattern}'`、`MISSING: {path}`、`TOO SMALL:` 行（含规则描述文字），经 advance 子进程 stderr 返回。
- F11 转写节边界：`_md_section` 以 `line.startswith("## ")` 截断，`### ` 子节包含在内——L3 在 `## Achieved` 内写合规子节即可完整转写并命中 content_match。
- F12 reviewer 角色只读：REGISTRY 中 reviewer 工具集 = read/find/grep/ls（无 write）——achieved.md 全程唯一写者是框架事务转写。
- F13 pm-state PASS / QG report 转写现状：`_append_pass_line`（`key-{key}` 锁）与 step 1 QG write-once 是 D-108 设计，`test_autopilot_conductor_exec.py` done-transaction 用例锁定该行为——本 key 不改动。
- F14 per-key 锁协议：`acquire_conductor_lock(project_root, f"key-{key}")` + `mw_common.release_lock`，`_append_pass_line` 已示范用法。
- F15 事故证据：FeatureMigrator 4/4 key（gui-shell-spike 31/31 VC、gui-contract-surface 23/23、cli-readonly-snapshot 20/20、gui-contract-mock-tests 18/18）全部 L3 meets 后 verify→done blocked×5 → stalled，人工收口后 exit=0；已批准门重放缺陷已修复并提交（`4e874f5cc`）。
- F16 标准模板无只读 check CLI：`check_gate` 是模块函数，`main()` 仅推进模式；FeatureMigrator PM 人工收口以 import 方式只读调用（`.tmp/pm_closeout_stage1b.py`，一次性脚本）。

## 结论 → 决策映射
- F2+F4+F5 → 改动点 1（失败原文回流 L3 回路）：词表唯一来源 = 失败原文，框架零硬编码。
- F3+F11 → 改动点 2（覆盖守卫）：合规稿必然 ≥200B（门禁自身要求），转写天然含子节，无需内容加工。
- F7+F8+F9 → 零新机制：in-flight 守卫 / 预算 / 失败分类全部现成。
- F12+F13 → 判定不代写、provenance 天然（逐字转写）；pm-state/QG 路径不动。
- F14 → marker 写/读/删走 per-key 锁。
- F16 → `--check` 只读入口不在本 key 范围（升级路径，见 spec §1.4）。
