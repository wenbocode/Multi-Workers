# T-12: 归属语义统一（`origin` 列）与 `worker_timeout_min` 接线

- 波次: **1** · 依赖: T-03
- 写面（独占）: 
  - `packages/multi-workers/autopilot/dispatch.py`（`render_task_md`）
  - `packages/coding-agent/src/extensions/agent-team-loop/worker-store.ts`
  - `packages/multi-workers/mw_common.py`（workers 解析段）
  - `packages/multi-workers/test_autopilot_attribution.py`（新建）
- AC: AC-013, AC-021 · VC: VC-015, VC-027, VC-028
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

消除三套归属口径分歧（`conductor.py:2135-2138` 前缀 OR path / `monitor.ts:509-513` 仅前缀 / `mw.py:1801-1820` 仅 path），并把静默空操作 `worker_timeout_min` 接上真链。

## 交付物

- `_workers.parallel` 行新增 `origin` 列（conductor 派发行 = `conductor`；PM 手工行 = `manual`），由写者在写行时填。
- 统一 `owner_key` 判据：`origin` 存在则以其为准；缺失（旧行）按 `path` 兜底；**不得**再用 `ap-` 前缀单独判定（实测 6 行带前缀但无 `origin: conductor` ⇒ 假信号）。
- `render_task_md`（`dispatch.py:262-331`）渲染 `timeout: <worker_timeout_min>` 头，接上真链 `task.md timeout:` > `PI_WORKER_TIMEOUT_MS` > 60m。
- 新测试：归属三口径一致 + timeout 头渲染。

## 契约（不得重定义）

- **不动配置键集合**（不加、不删键）⇒ 不影响 parity 语料（T-11 只处理 `auto_gate_mode`）。
- 旧行不迁移不重写（读侧兜底）。
- `monitor.ts` 属 T-09，本卡不碰 TS 观测面；`worker-store.ts` 的行结构变更需两侧一致（TS 写入者）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_attribution.py -q`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts`

## 非空洞对照（必须附在回执里）

- 构造 6 行"带 `ap-` 前缀但无 `origin`"的旧行 ⇒ 归属必须判为 `manual`（不会被误算进槽位）。
- 去掉 `timeout:` 渲染 ⇒ task.md 头断言必须红（该键恢复静默空操作）。

## 风险与注意

- `mw_common.py` 与 T-13 同文件 ⇒ 串行；本卡只碰 workers 解析段。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-12-attribution-timeout/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
