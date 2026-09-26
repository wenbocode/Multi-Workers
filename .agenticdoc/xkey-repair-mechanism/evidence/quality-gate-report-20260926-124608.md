# Quality Gate Report: xkey-repair-mechanism

- key: `xkey-repair-mechanism` · 基线 `6d98c5ee3` · ac_fingerprint `b944d7646135`
- 生成时间：2026-09-26T04:46:08Z（本地 2026-09-26 12:46）
- 执行者：PM（本 key 9 个 worker 全部终态并已 ack：t01/t02/t03/t04/t04b/t05/t06/t07/t08）
- 覆盖：AC-001…AC-011（11/11）、VC-001…VC-012（12/12）

## 一、AC → VC 逐条勾销

| AC | VC | 判定 | 证据（本轮实测） |
|---|---|---|---|
| AC-001 账本幂等去重 | VC-001 | **PASS** | L1：同 `(file,test_id,块 sha)` 扫 3 次 ⇒ `rows=1`、`history` 不增长；`ledger_append` 同键重复调用不新增行（`test_autopilot_xkey_registration.py`，26 passed） |
| AC-002 无登记只升级不提案 | VC-002 | **PASS** | L1 10 字形真值表（S-A/S-B/S-D 解析；S-C/S-E/S-F/S-G/S-H/S-I/S-J ⇒ `None`）+ 角色值拒绝；L2 逐字 K-1 散文：`[VERIFY] VC-002: prose_shape=K-1 (no test_id/owner) tickets=0 gates=0 escalations=1 pass=true` |
| AC-003 工单生成 + 未授权零写 + 防洪泛 | VC-003, VC-012 | **PASS** | L1 工单前后目标文件 sha256 相等；`[VERIFY] VC-012: gates_for_ticket=1 ticks=5`；非空洞对照：摘掉 `_gate_open` 守卫 ⇒ 5 tick = 5 gate |
| AC-004 仅人可答（重写版） | VC-004 | **PASS** | 三小项：① worker 模式无该命令 + `hasUI` 门挡住 print/RPC/派生 `pi -p`；② TS guard 硬拦 `write`/`edit`/`bash` 对 gate 目录的写入（拦截记录 + gate 文件 sha 不变：手动证据 `63612a16d9a377d1` → `63612a16d9a377d1`，5 类写构造全部 BLOCKED、提案路径 4 类 ALLOWED）；③ 作答来源与"非密码学证明"披露入证据 |
| AC-005 边界越界零残留 | VC-005 | **PASS** | L1 三类违规（改断言主体 / 触 untouchable / 涉及第二文件）⇒ `"violation"` 且 `apply_block_replace` 调用计数 0；L2 fixture 越界两路 ⇒ `boundary_violation` + 目标文件 sha 不变 + 零 run dir |
| AC-006 证据包五项 + 缺项不闭合 | VC-006 | **PASS** | L1 齐备 ⇒ `closed=True`；五项逐缺 + stdout 缺失 ⇒ `closed=False`；L2 `bundle closed=True missing=[]` |
| AC-007 闭合 + 幂等 + 两 key 标注 | VC-007 | **PASS** | L2 账本 `status=closed`、`closures=2`（source 交接 + owner 遗留，写在账本行，未写受影响 key 文件）；重复 tick 行数/标注/字节/run dir 均不变 |
| AC-008 默认关闭零扰动 + 跨包一致 | VC-008 | **PASS** | `[VERIFY] VC-008: xkey_artifacts=0 xkey_events=0`；关闭实测 4 处门控 + 惰性 import；TS/Python config 校验逐字段一致（7 用例独立对照） |
| AC-009 合成 fixture 全链 | VC-009 | **PASS** | `[VERIFY] VC-009: fixture_red=1->0 chain=detected>ticketed>gate-raised>applied>verified>closed ledger_status=closed idempotent=True relaxed_assertion=False pass=true` |
| AC-010 FM 语料重放（路 b） | VC-010 | **PASS** | `[VERIFY] VC-010: fm_replay_red=1->0 targeted=1 failed -> green relaxed_assertion=False old_sha256=7f6d6462b366 new_sha256=2aef27415e89 pass=true`；FM 工作树零污染（锚点 sha 全等，`git status` 文本留档） |
| AC-011 登记机器可读化 + 散文兼容 | VC-011 | **PASS** | 写侧：`[VERIFY] VC-011-write: machine_line_in_prompt=True in_mandatory_section=True`（`conductor.py:1148-1152` 必含节内）；读侧：10 字形逐条真值表 + 双侧测试锁（写侧 prompt 断言 + 读侧解析真值表） |

**覆盖率：AC 11/11、VC 12/12；无未覆盖 AC、无未绑定 VC。**

## 二、回归与不变量

| 项 | 结果 |
|---|---|
| 默认套件（`python -m pytest -q`，`packages/multi-workers`） | `2 failed, 1007 passed, 10 deselected`（基线 978 passed + 同 2 红 ⇒ **+29 新增，零新增失败**） |
| e2e_l2 重活套件 | `8 passed, 1011 deselected`（marker 迁移后用例数不变） |
| 新增 L1 | `test_autopilot_xkey_registration.py`：`26 passed, 0 skipped` |
| 新增 L2/e2e | `test_autopilot_e2e.py`：`3 passed, 8 deselected`（3 条均为 hermetic，进默认套件） |
| sha 锁 | `_parse_l3_output`/`_md_section` 区零 hunk；`test_autopilot_verdict_source_fallback.py` / `test_autopilot_verdict_freshness.py` 未被修改；region-sha 测试全绿 |
| 4-tuple arity | `test_frozen_anchors_and_criteria_unchanged` 绿（登记经 `registration_out` sink 传出） |
| 真实 FM 文件只读复核 | `locate_frozen_block(tests/test_hitl_channel.py, test_top_level_command_groups_unchanged)` → `TOP_LEVEL_GROUPS [243,244]`，`old_block_sha256=0d08581d…`；错误 test_id ⇒ `None`（降级生效） |
| 写面纪律 | `git status` 核对：9 个 worker 各自只碰其卡面写面；`xkey.py`/`config.py` mtime 早于 T-06/T-08 开工 |

## 三、两条外域先在红（非本 key）

1. `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` — `assert 3 in [2]`（round/report 一致性，外部项目 fixture 漂移）
2. `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` — readcap 域冻结件不一致

归因依据：基线 `6d98c5ee3` 即红（T-01/T-03 各以 pristine `conductor.py`/`config.py` 副本独立复现，且本 key 未触碰其判定链）；与本 key 的 +29 新增测试互不相关。已向对应域会话通报。

## 四、结论

**PASS** — AC 11/11、VC 12/12 勾销；默认套件零新增失败、e2e_l2 8/8；机制默认关闭且关闭时零行为变化；越界零残留、验证失败字节还原、闭合幂等三条不覆盖铁律均有实测证据。残余面（第 5 项：同权限进程绕开工具层可直写 gate）已在 spec §2.3 / design D-008 / achieved.md 如实披露，未声称更强保证。
