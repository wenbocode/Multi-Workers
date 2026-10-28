# Quality Gate Report: claim-driven-review

**时间**: 2026-10-22T17:05+08:00
**触发**: T-07f 端到端 `exit=0` 后收口质检（VERIFY → done）
**范围**: AC-001…AC-008 + §0 预期收益 B1…B4
**执行**: PM（本窗口），独立复算 + worker 证据交叉核对
**结论**: `PASS（scope=narrow）` —— 机制四层达成且实测有效；AC-004/005(a)/006 与 B4 移交
`claim-driven-review-orchestration`，不在本 key 的 done 结论里算达成。

## 前置门禁

| 检查项 | 结果 |
|---|---|
| spec AC 编号 | ✅ AC-001…008 |
| evidence-requirement | ✅ `verify.md` / `achieved.md` / `evidence/t07-e2e-results-20261022.md` |
| 三份 research 落地 | ✅ RQ-1 41,535 B / RQ-2 47,700 B / RQ-3 66,195 B |
| 端到端实跑 | ✅ `cdr-t07f-e2e-review-a` done，`exit=0`，`claims=5 closed=5 unverified=0` |

## AC 核查

| AC | 描述 | 状态 | 证据 |
|---|---|---|---|
| AC-001 | claims 契约 + 派发期校验（advisory/enforce，拒绝零副作用） | 已充分 | `test_claim_dispatch.py` 9 例；`dispatch-card.ts:724/985` |
| AC-002 | 七列表结算 + 覆盖判据 + 一次 self-check + `exit 2` | 已充分 | `claim-coverage.test.ts` 33 it；`claim-bypass.test.ts` 23 it；`output-sections.ts:625` |
| AC-003 | 预算承载 `min(30,6n)` / `min(393216,65536n)` | 已充分 | 三轮 task.md 头部实测（5 → 30/327680）；`test_claim_parity.py::test_claim_budget_caps_formula_parity` |
| AC-004 | `triage → 扇出 → merge` + 20-claim 4+1 | **未达成（移交）** | 本 key 只做单单元；见 `verify.md` §AC-004 |
| AC-005 | 度量 + `n/a` 降级 | 部分（(b) 达成 / (a) 依赖 AC-004） | `test_claim_metrics.py` 11 例；实测三轮 `n/a`+`attributable=false` |
| AC-006 | advisory 默认 + 开关同名同义 | 部分（开关达成 / 对照样本不足） | `test_claim_parity.py`；`CLAIM_GATE_DEFAULT` 双侧各一处读取 |
| AC-007 | 零回归（无 claims 卡逐字节不变；旧默认值不动） | 已充分 | 462 B 逐字节用例；`l2_read_file_cap=8`/`65536` 未改 |
| AC-008 | 六条反绕过 + 负例 | 已充分 | `claim-bypass.test.ts`；⑥ 判据经实测替换（D-014①） |

## §0 预期收益核查

| # | 目标 | 实测 | 判定 |
|---|---|---|---|
| B1 | 取数次数 159 → ≤60 | 基线 52（n=32）/ 断言卡 16（13/16/23） | 达成（-69%） |
| B2 | 死亡上下文 214k → ≤120k | 基线 110,666（max 253,273）/ 断言卡 35,782（max 41,377） | 达成（-68% / -84%） |
| B3 | 降级链归零 | 断言卡 run 上 `[MODEL_FALLBACK]` = 0 | 达成 |
| B4 | `tokens_per_closed_claim` 可比 | 恒 `n/a`，`rows with claims = 0` | 未达成（wiring，移交） |

## 测试与静态检查

| 面 | 结果 |
|---|---|
| TS（8 套，claims 相关） | **159 passed**（claim-block 24 / claim-coverage 33 / claim-bypass 23 / dispatch-claims-render 17 / dispatch-card-injection + triage-dispatch 46 / dispatch-recovery-terminal 16） |
| Python（3 文件） | **27 passed**（claim_dispatch 9 / claim_parity 7 / claim_metrics 11） |
| `tsgo --noEmit` | rc=0 |
| `npm run check` | rc=1，仅 5 条已知基线诊断（`mwoc-matrix-t07` ×3、`mwoc-w2` ×1、`mwoc-w3` ×1），本 key 无新增 |
| 改动文件 biome | 0 诊断 |

## 问题清单

| ID | 描述 | 状态 |
|---|---|---|
| Q-1 | `carried-from` 原 mtime 判据精度 0%（C-01/C-02/C-03 全误报） | 已修（D-014①：改为"本轮未放行读过"） |
| Q-2 | `fileCap` 少 6 倍（`Σ预算` 而非 `perClaim×n`） | 已修（D-014②） |
| Q-3 | `fetches` 误计被拒调用 | 已修（D-014③：`allowedReads`） |
| Q-4 | 证据分隔符只认 ASCII `;`，全角 `；` 造两个假 gap | 已修（`/[;；]/`，P-048） |
| Q-5 | `claims=0` 静默降级 | 已修（D-013 `claimsDeclared`） |
| Q-6 | launcher `end` 不写 `claims` → 头号指标恒 `n/a` | 移交新 key AC-010c |
| Q-7 | spec §0「159」基线口径混用 | 记入 `_pitfalls.md` |

## 交付物

- `spec.md` / `design.md` / `plan.md` / `key-decision.md`（D-001…D-016）/ `verify.md` / `achieved.md`
- `evidence/t07-e2e-results-20261022.md`、三份 `evidence/research/spec-rq*.md`
- 代码：`shared/dispatch-card.ts`、`pm/ui-bridge.ts`、`worker/{read-scope,worker-mode,output-sections,output-writer}.ts`、
  `autopilot/dispatch.py`、`usage.py`、`status-model.ts` + 6 套测试 + README/CHANGELOG
