# Evidence: plan-postfix-regression-20260925（T-09）

## 集成修复记录（B/C 落地后 PM 集成时发现）

**H2 子节转录截断坑（P-013）**：首次集成后 e2e full_chain 仍红——round 1 gate-blocked → l3-reprompt ✓ → a2 派发 ✓ → stub 产合规稿 ✓，但 round 2 事务把 achieved.md 覆盖成 12B（`_md_section` 在 `## Achieved` 节内遇 `## 系统行为变化` H2 子节即截断，提取只剩节标题）→ <200B → below → 耗尽 stall（"L3 below 2 rounds"）。修复两处：
1. e2e stub 合规模板子节 `##` → `###`（H3 不触发截断）；
2. closure.py `REPROMPT_INSTRUCTION` 增形状约束句（子标题严格低于 `##` 级）——防真实 reviewer 按门禁描述「必含『## 系统行为变化』」字面照做踩同坑；顺带修正常量换行拆断 `'## Quality Gate Report'` 子串的测试断言。

## 修复后回归（2026-09-25，packages/multi-workers）

| 命令 | 结果 | 对照基线 |
|------|------|---------|
| `python -m pytest -m e2e_l2 -q` | **7 passed**（187s） | 修复前 6 passed + 1 failed（full_chain 词表缺口红） |
| `python -m pytest -q`（默认套件） | **927 passed, 2 failed**（88s） | 2 失败均为外域先在（见下），零新增失败 |
| `python -m pytest test_autopilot_closure.py -q` | 32 passed | 与 T-02 交付一致 |
| `python -m pytest test_autopilot_conductor_exec.py -q` | 29 passed（15 既有 + 14 test_dcr） | 既有 15 不破；14 新用例对 HEAD conductor 红控 12/14 预期红 |

**外域先在失败（worktree 独立判定）**：
- `test_autopilot_readcap_injection.py::test_baseline_left_end_bound`——readcap key 域（冻结 dispatch.py sha vs HEAD blob），1b2a1efde 与 a0c36fcce 上均复现；
- `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`——verdict-freshness/source-fallback key 域，1b2a1efde（该测试的引入提交）与 a0c36fcce 上均复现。
两者在排除本 key 全部改动（HEAD worktree）的树上复现 → 非本 key 回归，另行通报。

## e2e full_chain 行为变化（核心验收）

修复前（T-01 证据）：gate-blocked ×5 → gate-0002 stalled → 死循环（人工关单）。
修复后：gate-blocked ×1 → marker 落盘 → `l3-reprompt` 事件 → a2 派发 → 合规轮 → 三条件覆盖 → advance exit=0 → DONE → stage-close。timeline 关键序列实测（mw-e2e-0233u1_o 修复前中间态 / 集成后测试内）：
```
advance verify->done exit=1 class=gate-blocked
l3-reprompt: gate-blocked on evidence draft; reprompt l3-a2 (1 lines)
dispatch ap-k1-l3-a2 type=reviewer loop=l3:k1 attempt=2
（合规轮）→ advance verify->done exit=0 → phase DONE → stage-close gate
```
零 stalled gate、零人工 gate 应答（AC-001 的 e2e 面）。

## 变更面快照

- `autopilot/conductor.py`（+110/−19：D-001 元组 / step-2 三条件守卫 / step-5 marker + 惰性清理 / 终态清扫 / meets 四分支 + reprompt + 自持预算）
- `autopilot/closure.py`（新，183 行 + 形状约束句）
- `test_autopilot_conductor_exec.py`（+610：14 test_dcr + 夹具）
- `test_autopilot_closure.py`（新，378 行）
- `test_autopilot_e2e.py`（夹具 credentials.timi + stub reviewer reprompt 响应分支 `###` 子节）
- `.gitignore`（marker 忽略行）、`CHANGELOG.md`（Added×1 + Fixed×2）、`.agenticdoc/_pitfalls.md`（P-012/P-013）
