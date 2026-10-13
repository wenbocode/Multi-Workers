# T-19 — 收口：changelog / 文档勘误 / 质量门证据 / 生效清单

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: 全量（收口与文档面，不改行为）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`（AC-001…AC-016）、`design.md`、`plan.md` §5 全局约束与收口判据

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守下的可见性与自动放行；文档必须让运维知道**哪些面变了、怎么生效**）。
- 本 key 已落的可观测面（收口文档必须覆盖，逐项给出 `path:line`）：
  1. **常驻状态面**：pending 行 + **stage 主闸行** + 六值抑制原因（`autopilot/monitor.ts`、`status-model.ts`）；
  2. **编码与预算**：`~D` 漂移记号、`R:*` 原因短码、紧凑 age、末列 `+N`、`J`/`P`（blocker 类）与 110 列 fit ladder（`monitor.ts`）；
  3. **抑制可视**：per-key 抑制 + `remind-suppressed` 留痕 + cap 降级文案 + 双通道（`autopilot/conductor.py`）；
  4. **serve 漂移自证**：`serve.meta` 身份 + `code_digest` + `mw status`/`mw doctor` 判 `STALE CODE` + `history-only` 收窄（`packages/multi-workers/mw.py`、`shared/mw-runner.ts`）；
  5. **`stage-close` 自动收证放行**：五判据 + `answered_by="conductor-auto:<rule>"` + `phase:"decide"` 台账 + 回落点名缺失项（`conductor.py`）；
  6. **re-attest / reject 二次确认**：`mw autopilot answer --confirm-destructive`（`conductor.py`、`mw.py`）；
  7. **`blocker_class`**：序外标量、`None → judgment` 折叠、`monitor` 面 `J`/`P`；
  8. **合成 claim**：`autopilot@<host>:<pid>` 创建/续期/失效回收 + 人工让位（`conductor.py`、`autopilot/index_parallel.py`、`shared/index-store.ts`、`pm/ui-bridge.ts`）；
  9. **回收契约**：角色分流 + infra 白名单 + `## Ledger Unresolvable`（`shared/change-ledger.ts`、`worker/output-writer.ts`）。
- **生效前置（必须写进文档）**：Python 侧改动需 `/mw restart`；TS 扩展改动需 `build --install` + `/mw restart` + `/reload`。**运行期实证**：TS 账本修复在旧 bundle 下无效（T-16 终态仍报 4 条已修误判）。
- **已知过程发现（须写入 `evidence/` 的收口报告）**：C-36 六子类；上一 key（`b65380d1b`）新增配置键未同步 TS 注册表**与放行集合** ⇒ P5 锁红着出厂；根因 `npm run check` 不跑测试。

已核实锚点（收口文件必须逐项引用 `path:line`）：`packages/multi-workers/autopilot/conductor.py:5742 proposition_stage_close_credentials`、`:225 SYNTHETIC_CLAIM_HEARTBEAT_SEC`、`:263 _foreign_synthetic_claim`、`:7193 answer_gate_confirmed`、`:3933 _apply_reattests`；`packages/multi-workers/autopilot/gates.py:190 _SCALAR_EXTENSION_FIELDS`、`:197 BLOCKER_CLASSES`、`:373 queue_entries`；`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:167 BOOL_FIELDS`；`shared/change-ledger.ts:804 unresolvable`；`worker/output-writer.ts:76 unresolvableFiles`；`pm/ui-bridge.ts:251 ClaimState`；`pm/pm-orchestrator.ts:319 tookOverFromConductor`。

## 要求

1. **文档勘误/新增**：把上面 9 项可观测面写进**既有文档的正确位置**（先查清本仓文档惯例：`packages/multi-workers/` 与 `packages/coding-agent/` 的 README/`docs/`；**若 `packages/multi-workers/CHANGELOG.md` 不存在，不得凭空空造**，改为写入实际存在的文档并在报告中说明）。文档须写明**运维动作**（哪些面需要 `/mw restart`、哪些需要 `build --install` + `/reload`）。
2. **CHANGELOG**：若 `packages/coding-agent/CHANGELOG.md` 存在且本 key 触及 TS 面（是），在 `## [Unreleased]` 的既有子节内**追加**条目（读全文、不得重复子节、不得改动已发布段）。
3. **质量门证据**：新增 `evidence/quality-gate-report-20261013.md`，逐条 AC-001…AC-016 给出：判定 + 证据（`path:line` 或**逐字实测输出**）+ 未覆盖/残留。**不得**只写"通过"。
4. **生效清单**：新增 `evidence/runs/closeout-runtime-actions-20261013.md`：列出你**实际验证过存在**的入口（命令名 + 实测输出片段），以及**必须由人类执行**的动作（`/mw restart`、`build --install`、`/reload`）与每个动作生效的改动面。
5. **不得改行为**：本卡**不得修改**任何源码/测试逻辑（只允许文档与 `evidence/`）；若发现行为缺陷，**报告**而不是修（另开卡）。
6. **全局检查**：在本卡**独占**（无其他 worker 运行）时运行仓库级 `npm run check` 并附逐字输出（若仍有红，逐条判定归属并说明）。

## 写入允许面

- `packages/coding-agent/CHANGELOG.md`、`packages/multi-workers/CHANGELOG.md`（若存在）
- `packages/multi-workers/README.md`、`packages/multi-workers/docs/**`、`packages/coding-agent/README.md`、`packages/coding-agent/docs/**`（按实际存在者）
- 新增：`.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/quality-gate-report-20261013.md`
- 新增：`.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/runs/closeout-runtime-actions-20261013.md`

## 写入禁止面

- 任何 `src/**`、任何 `test/**`（含新增测试）—— 本卡零行为改动
- `spec.md`、`design.md`、`plan.md`、`achieved.md`、`pm-state.md`（PM 面）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从仓库根：`npm run check`（须在无其他 worker 运行时执行，附逐字输出）
文档面自查：`git status --porcelain`（确认只动了本卡写入面内的文件）

## 改动历史

（填写：文档落点与理由、发现的文档/现实不一致处、`npm run check` 的归属判定、未覆盖的残留。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
