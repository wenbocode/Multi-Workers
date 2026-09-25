# Plan: mw-done-closure-repair

> Key: mw-done-closure-repair · 阶段: plan · 2026-09-25
> 上游: spec.md（AC-001..011，含 5 处 [REVISED]）· design.md（D-001..D-007）· 证据: evidence/research/design-{return-path,marker-mechanics,reprompt-loop}-20260925.md + dcr-review-spec-design 报告
> 执行方式：T-02 派 coding worker（新文件独占）；其余 PM 本窗口直执（conductor.py 为并发争用文件，不派 worker）

## 并行性分析（PM 规则 1）

- 可并行单元：`autopilot/closure.py` + `test_autopilot_closure.py`（全新文件，签名已钉死于 design §2，零文件冲突）→ 派 worker A（`dcr-t02-closure-module`）。
- 必须串行的理由：`conductor.py` 正被另一会话修改（L3 verdict source fallback，工作树 +93/-30 未提交）——同文件同刻单写者；且 L2 测试与 conductor 改动同脑模型强耦合。`test_autopilot_conductor_exec.py` 同理归 PM。
- 共享资源面：`packages/multi-workers/.pytest_cache`（无害）；`.gitignore`（PM 在 T-10 独占写）；closure.py 的消费集成点（T-04/T-05）在 worker A 落地后由 PM reconcile。
- 时序：worker A 与 PM 的 T-03（纯 conductor 内部改动，不 import closure）真并行；T-04 起消费 closure API。

## 任务表

| 任务 | 目标 | 产出 | 覆盖 AC | 依赖 | 验证 |
|------|------|------|---------|------|------|
| T-00-baseline-sync | 并发基线对齐：确认 verdict-source-fallback 已提交、conductor.py 工作树净空；以现行树重定位 D-005 全部锚点并记录漂移映射 | `evidence/plan-baseline-drift-map-20260925.md` | 全部（前置） | - | git status 净空 + 锚点逐条重验 |
| T-01-prefix-e2e-evidence | 修复前 e2e_l2 全链跑一次，观察 done 门禁是否实际对 stub 词表缺口 gate-block（F-12 为代码级推断，须实证） | `evidence/plan-prefix-e2e-20260925.md` | AC-001（前置） | - | `python -m pytest -m e2e_l2 -q` + achieved.md/timeline 观察 |
| T-02-closure-module | closure.py 纯逻辑模块 + L0/L1 单测（**worker A**） | `autopilot/closure.py`、`test_autopilot_closure.py` | AC-002(VC-003)/AC-003(VC-004/005)/AC-011(VC-013-L1) | design §2 契约（无代码依赖） | `python -m pytest test_autopilot_closure.py -q` |
| T-03-return-tuple | D-001：`_done_transaction` 返回 `(verdict, err)` + 唯一调用点适配 | conductor.py diff | AC-010 保持 | T-00 | 现有 exec 用例全绿（9 return 点逐一携带 err） |
| T-04-marker-guard | D-003/D-004：step-2 三条件覆盖 + 原子写（tmp+os.replace）+ 同锁删；step-5 advance exit≠0 时 marker 落盘（锁内）；exit=0 惰性清理；`_mark_key_done`/`_apply_stalled_rejections` 终态清扫 | conductor.py diff | AC-003/004/011 | T-03, T-02 | 单测真值表 4 否定例 + 全真例（VC-004/005/013） |
| T-05-reprompt-branch | D-005/D-006/D-002：meets 分支四路展开（含 meets∧无源回退归 below 路径映射）；gate-blocked(achieved.md) → 自持预算 `used < l3_limit` → 派 `l3:{key}` a{N+1}（prompt = `_l3_prompt` + `REPROMPT_INSTRUCTION` + 失败行逐字）；耗尽 → mark_stalled（verdict 保真 meets）；`l3-reprompt` 限长 timeline 事件 | conductor.py diff | AC-001/002/005/006/007 | T-03, T-02 | 与 T-06..T-08 的 L2 用例一起验 |
| T-06-l2-tests-a | exec 夹具升级：fake advance 逐字节复刻 advance_phase.py:584-591 stderr 形状（`GATE BLOCKED:`/`Current phase`/`   - ` 前缀/exit 1）；标准词表 fixture 场景 A（AC-001）+ 第二词表 fixture「行为影响」「未了事项」（AC-008）+ 逐字转写（AC-010） | test_autopilot_conductor_exec.py 扩展 | AC-001/008/010 | T-04, T-05 | VC-001/VC-010/VC-012 绿 |
| T-07-l2-tests-b | 场景 B/C/D 用例：人工修稿保护（AC-004）、预算耗尽 stall（AC-005）、非 achieved.md 失败分流（AC-006）、in-flight 零 advance（AC-007） | 同上 | AC-004/005/006/007 | T-06 | VC-006/007/008/009 绿 |
| T-08-l2-tests-c | 洪泛回归（AC-009，30 tick 混合场景，锁 4e874f5cc 行为）+ marker 生命周期 L2（AC-011） | 同上 | AC-009/011 | T-06 | VC-011/VC-013 绿 |
| T-09-e2e-postfix | 修复后 e2e_l2 全链 + autopilot 全套件回归 | 测试运行记录入 evidence | AC-001/008 | T-06..T-08 | `-m e2e_l2` 绿 + `python -m pytest -q` 对照基线（241 passed + 1 既有无关失败 test_baseline_left_end_readcap 外部锚） |
| T-10-gitignore-docs | `.gitignore` 增 `.agenticdoc/**/.mw-achieved-baddraft.json`；multi-workers CHANGELOG [Unreleased]；`_pitfalls.md` 沉淀（stderr 丢弃类缺口=回传通道须最小充分） | 三个文件 diff | - | T-09 | diff 自检 + CHANGELOG 段落规范 |

## 顺序与门禁

1. T-00 是硬门禁：conductor.py 工作树非净空不得开工 T-03..T-05（并发会话未提交即等待/协调，绝不叠加写）。
2. T-01 与 T-00 可同批；worker A（T-02）与 T-00/T-01/T-03 并行。
3. T-03 → T-04 → T-05 严格串行（同一函数族，逐步补测试）；T-06 → T-07 → T-08 串行（同文件）；T-09 → T-10 收尾。
4. 全绿判据：`packages/multi-workers` 下 `python -m pytest -q`（pytest.ini 默认排除 e2e_real/e2e_l2）+ `python -m pytest -m e2e_l2 -q` 双跑，对照既有基线零新增失败。

## 验证口径

- Python：package 根 `python -m pytest <file> -q`；不涉 TS，`npm run check` 不适用（无 TS 改动时）；如触碰 dist 重建另议。
- 修复前/后 e2e_l2 证据均落 `evidence/`，含命令、退出码、关键断言观察点。
- 一律文件事实（timeline/achieved.md/marker 存在性），不采信日志口述。

## 风险登记

| 风险 | 缓解 |
|------|------|
| verdict-source-fallback 会话长期不提交，conductor.py 持续脏 | T-00 门禁阻塞时向用户报告协调；不抢写、不 stash |
| worker A 对 design §2 签名偏差 | PM 在 T-04 集成时 reconcile；契约已在 design 钉死，偏差仅限命名级 |
| fake advance stderr 与真实输出漂移 | T-06 夹具逐字节复刻 advance_phase.py:584-591 当前实现，并加一条格式回归断言 |
| 修复前 e2e_l2 不复现词表缺口（stub 恰含「遗留」） | T-01 观察记录实际行为；缺口不触发则以 AC-008 合成词表夹具承担复现（D-007 预案） |
| mark_stalled 追加 achieved.md 使 marker sha 失配（评审 R4 未记载交互） | 无害且方向保守（失配=不覆盖）；T-04 注记 + T-07 用例覆盖该路径 |
| 测试基线噪声（test_baseline_left_end_readcap 外部锚） | 对照基线比较新增失败，不追逐既有失败 |
