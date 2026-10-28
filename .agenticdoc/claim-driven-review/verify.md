# VERIFY：claim-driven-review 验收核对（2026-10-22）

依据 `spec.md` §3 的 AC-001…AC-008，逐条给判据、证据、结论。**未达成的条目照样列出来**，
不把"测了别的东西"说成"这一条过了"。

## 总览

| AC | 结论 | 一句话 |
|---|---|---|
| AC-001 | 达成 | claims 块契约 + 派发期校验（advisory 只告警 / enforce 拒绝且零副作用） |
| AC-002 | 达成 | 七列表结算 + 覆盖判据 + 一次 self-check + `exit 2` |
| AC-003 | 达成 | `fileCap = min(30, 6×n)`、`byteCap = min(393216, 65536n)`，实测承载 |
| AC-004 | **未达成** | 只做了单单元（5 条）；`triage → 扇出 → merge` 与 20-claim 卡的 4+1 编排未实现、未实跑 |
| AC-005 | 部分 | 度量与 `n/a` 降级已实现；(a) 的 1×20 vs 4×5 并排比较依赖 AC-004，未做 |
| AC-006 | 部分 | advisory 默认与开关同名同义已实现；"advisory 前后退出码分布不变"无基线对比样本 |
| AC-007 | 达成 | 无 claims 卡逐字节不变；`l2_read_*` 旧默认值未动；平价锁全绿 |
| AC-008 | 达成 | 六条反绕过判据各带负例；⑥ 的判据在实跑后被替换（见下） |

## 逐条

### AC-001 达成

- 契约与解析：`shared/dispatch-card.ts:535`（`CLAIM_TYPES`）、`:547`（`UNVERIFIED_REASONS`）、
  `:565`（`CLAIM_GATE_DEFAULT`）、`:573`（`CLAIM_BUDGET`）、`:724`（`parseClaimsBlock`）、
  `:985`（`claimsGaps`）、`:1034`（`claimBudgetCaps`）。
- Python 镜像：`autopilot/dispatch.py:474-490`（常量）、`:654`（`parse_claims_block`）、
  `:711`（`claim_budget_caps`）、`:735`（`claim_gate`，`:742` 唯一 `MW_CLAIM_GATE` 读取）、`:805`（`_read_scope_caps`）。
- 零副作用拒绝：`test_claim_dispatch.py` 9 例（含拒派后无 taskDir / 无 task.md / 无队列行）。
- **偏离**：id 实际只接受 `C-<2+ 位数字>`，卡内写成 `C-A1` / `C-1` 会整行丢弃；且**声明了块但解析出
  0 条**在 T-07 首轮是静默降级（无 read_scope、无 caps）。已修：`claimsDeclared` 区分"无块"与"有块零解析"，
  后者回执行输出 `claims=0(unparsed)` 并把解析错误写进 warnings（D-013）。

### AC-002 达成

- `worker/output-sections.ts:259`（`VerdictRow`）、`:274`（`VerdictTable`）、`:374`（`parseVerdictTable`）、
  `:625`（`claimCoverage`，12 个 gap token）。
- `worker/output-writer.ts:82`（`TerminalGaps.claimGaps`）、`:394`（`readTerminalGaps({claims})`）、
  `:449`（`ok` 折叠）、`:466`（`claimGapNote`）。
- 一次 self-check steer 复用既有 `selfCheckSent`：`worker-mode.ts:4464`（`settleOrSelfCheck`）。
- **偏离（已修）**：`证据` 分隔符原只认 ASCII `;`，实跑产出用全角 `；`，一次造出两个假 gap。
  现 `splitEvidenceRefs` 与 `claimEvidencePaths` 都按 `/[;；]/` 切（P-048）。

### AC-003 达成

- 公式：`dispatch-card.ts:1042`；Python `dispatch.py:711`；两侧常量单源（`CLAIM_PER_CLAIM=6`、`CLAIM_CALL_CAP=30`）。
- 实测：5 条 claim → `l2_read_file_cap: 30` / `l2_read_byte_cap: 327680`（三轮 e2e 的 task.md 头部）。
- 预算耗尽的 claim 记为 `unverified: budget`：第一轮 C-04/C-05 即此形态（`report.md` 可查）。

### AC-004 未达成 —— 本 key 的剩余缺口

- 已实现：`claims > 5` 时派发拒绝（GT 的 `claims:budget-sum` 与拆卡规则在卡级校验里），单单元 e2e 全绿。
- **未实现**：`triage → 扇出 → merge` 三步编排；merge 单元只读各单元裁决文件；20-claim 卡的 4+1 编排实跑。
  这是 L2 编排层（PM 侧），与已交付的契约/结算/度量三层正交，但**不能声称本 key 覆盖了 AC-004**。

### AC-005 部分

- `usage.py:926`（`parse_claims_line`）、`:957`（`_run_claims_counts`）、`:1007`（`claims_metrics`）、`:1255`（`_run_detail_row`）；
  `status-model.ts:1552`（`ClaimMetricsView`）、`:1717`（`readRunClaims`）、`:1750`（`keyClaims`）、`:1901`（面板行）。
- 实测回读：`tokens_per_closed_claim="n/a"` + `attributable=false`（token 不可 join 时诚实降级，非近似值）。
- 缺：AC-005(a) 的"两种拆法并排比较"——依赖 AC-004。

### AC-006 部分

- `CLAIM_GATE_DEFAULT="advisory"`、`MW_CLAIM_GATE=enforce`，TS/Python 同名同义（平价锁 `test_claim_parity.py`）。
- 缺：advisory 期间"既有 review run 的退出码分布相对基线不变"——本轮没有产出基线对照样本，
  只证了 advisory 不拒绝（7 条零副作用用例 + 实跑三轮都未因 claims 被判拒）。

### AC-007 达成

- 无 claims 卡的派发输出与 HEAD 逐字节相同（462 B，`test_claim_dispatch.py` 一条用例锁住）。
- `l2_read_file_cap=8` / `l2_read_byte_cap=65536` 旧默认值未改（verifier 饥饿线保留）。
- 回归：`claim-block` 24 / `claim-bypass` 23 / `claim-coverage` 32 / `dispatch-claims-render` 17 /
  `dispatch-card-injection` + `triage-dispatch` 46 / `dispatch-recovery-terminal` 16 = **159 passed**；
  Python **27 passed**；平价锁 7 例（含新加的 `claimBudgetCaps` 公式锁）。
- `npm run check` rc=1，诊断只有已知基线 5 条（`mwoc-matrix-t07` ×3、`mwoc-w2` ×1、`mwoc-w3` ×1），
  无新增；`tsgo --noEmit` rc=0；改动文件 biome 0 诊断。

### AC-008 达成（⑥ 判据已替换）

- ①②③④⑤ 各有负例（`claim-bypass.test.ts`）；③ 的 `fetches` 口径改为**只计放行**调用，
  实测第一轮 `fetches=12 > fileCap=5` 的异常已消失（第三轮 13 次放行调用 ≤ 30）。
- ⑥ 原判据「证据文件 mtime < task.md mtime」在真实样本上精度 **0%**（两条真裁决被误判复用），
  改为「该行引用的文件本轮未被放行读过」（D-014①）。负例仍在：引用未读文件 → `claim:<id>:carried-from`，
  引用读过文件 → 无 gap。

## 实跑证据

`evidence/t07-e2e-results-20261022.md`：同一张 5-claim 卡三轮对照（5 caps → 30 caps → `exit=0`），
含 `[CLAIMS]` 行原文、`run.json.claims`、被拒调用明细、`tokens_per_closed_claim=n/a` 回读。

## 结论

契约、预算、结算、度量四层已交付并端到端验证（`exit=0`，5/5 closed，13 次放行取数）。
**AC-004 的编排层与 AC-005(a)/AC-006 的对照样本未完成**，建议单独开 key 承接（`claim-driven-review-orchestration`），
不并入本 key 的 done 结论。
