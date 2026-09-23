# Plan: mw-worker-visibility-gate

> 输入：`spec.md`（AC-001…013）、`design.md`（D-101…D-109、VC-001…013）
> 目标相位：plan → tasks → execute → verify → done

## 1. 并行性分析（拆解前必做）

### 1.1 可并行单元

| 单元 | 交付物 | 依赖 |
|------|--------|------|
| T-1 | `shared/phase-docs.ts`（`gateTierOf` + `phaseDocGaps(status,tier)` + `dispatchDocGaps(root,key,phase?)`） + 新测试 | 无 |
| T-2 | `shared/pm-state-claim.ts`（新：`syncPmStateClaimId`） + 新测试 | 无 |
| T-3 | 接线：`pm/ui-bridge.ts` + `pm/pm-orchestrator.ts`（门禁传相位、面板聚合行、claim 同步两处调用点） + 新测试 | T-1 + T-2（import 两个新 API） |
| T-4 | 文档：两包 CHANGELOG、`_pitfalls.md` P-011 | 无（内容由 design 锁定） |
| T-5 | 独立验证：VC-001…013 复现 + 变异反例 | T-1…T-4（+T-6） |

### 1.2 共享资源与冲突面

- 文件所有权（同一文件同一时刻只允许一个 worker）：
  - T-1 → `shared/phase-docs.ts`、`test/extensions/agent-team-loop-phase-docs-gate.test.ts`
  - T-2 → `shared/pm-state-claim.ts`、`test/extensions/agent-team-loop-pm-state-claim.test.ts`
  - T-3 → `pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`test/extensions/agent-team-loop-watch-aggregate.test.ts`、`test/extensions/agent-team-loop-pm-state-sync.test.ts`
  - T-4 → `packages/coding-agent/CHANGELOG.md`、`packages/multi-workers/CHANGELOG.md`、`.agenticdoc/_pitfalls.md`
  - 既有共享测试文件 `test/extensions/agent-team-loop.test.ts`：**本 key 不改**（新断言一律进 T-1/T-2/T-3 的新文件），避免两个 worker 争同一大文件。
- 跨 worker 的编译面：T-1 的 `dispatchDocGaps` 第三参数设计为**可选缺省 `""` → spec 层**（设计 D-101b），因此 T-1 独立合入时 `ui-bridge.ts` 两处既有调用点仍可编译 → 波形 1 内不会出现瞬时 typecheck 红。
- T-3 必须同时改两个 `dispatchDocGaps` 调用点（`ui-bridge.ts:1093`、`:1498`），否则两条派发入口行为分叉（design §4.1 已列为约束）。

### 1.3 必须串行的理由

1. T-3 依赖 T-1 与 T-2 的新 API 存在（`import` 不存在的模块 = 直接 typecheck 失败）→ T-3 排在波形 2。
2. T-5 是独立验证，必须在被验代码冻结后进行（否则复现对象漂移）→ 排最后。
3. T-4 文档与代码无文件冲突，但 CHANGELOG 语义需反映最终行为 → 与 T-3 同波或之后执行，本 plan 排在波形 2（PM 直执）。

## 2. 波次与派发方式

| 波次 | 任务 | 方式 | 并行度 |
|------|------|------|--------|
| W1 | T-1、T-2 | 各派 1 个 `type: coding` worker（文件互不重叠） | 2 |
| W2 | T-3（worker）+ T-4（PM 直执，文档） | 1 worker + PM | 1 |
| W2.5 | T-6（D-111 语义修订：缺 Claim-Id 行时插行） | 1 个 `type: coding` worker | 1 |
| W3 | T-5 独立验证 worker | 1 个 `type: coding` worker（只读被验代码、只写自己的报告） | 1 |

派发纪律：一律 `type: coding`（P-007：审查/调研任务也走 coding 以获得落盘通道）；每个 worker 的 task.md 必须写明**唯一文件面**、`[VERIFY] VC-xxx:` 证据行写法、以及"不得修改分配面之外的文件"。

## 3. 验证策略

- 分层：L1 集成断言为主（走真实工具入口：`dispatch_worker` schema/execute、`switch_key`/`takeOverKey`、`renderWatchLines`），L0 文档检查 1 条（AC-013）。
- 每条 VC 的 `[VERIFY]` 行必须由 worker 写进自己的 `output.md`，PM/验证方在原始输出里 grep 复核（P-006）。
- 变异反例（T-5）：至少 3 个（门禁层边界、聚合行缺 risk 段、claim 同步被短路），要求"改坏即红 + 复原后逐字节相等"。
- 回归面：`npm run check` + 既有 `test/extensions/agent-team-loop*.test.ts` 与 `test/suite/**` 定向复跑（Windows 环境失败按 89 项基线比对增量）。

## 4. 风险与缓解

| 风险 | 缓解 | 归属 |
|------|------|------|
| 门禁放宽后被用于绕过"先写 spec" | spec 侧四项缺一即拒（AC-005）；DESIGN 起 design 侧两项仍硬拦（AC-002/003） | T-1 |
| 面板聚合行破坏既有面板断言 | 新参数可选 + 聚合行只追加在末尾（AC-007 + 既有 12 处调用零改动） | T-3 |
| claim 同步写坏 pm-state 模板 | 单行原地替换 + 换行探测 + 原子写 + 缺行不重建（AC-010/011），并以"二级标题数与 Updated 行数不变"做机器判定 | T-2/T-3 |
| 两个 dispatch 入口分叉 | T-3 必须在同一任务内改完两处调用点，且 VC-002 走工具入口 | T-3 |

## 5. 完成定义（DoD）

- 13 条 AC 全部有可机械判定的证据行（VC-001…013）；T-5 复现 0 FAIL。
- `npm run check` exit 0；被触碰文件面之外无 diff（`git status` 守卫）。
- 质量门禁报告（`evidence/quality-gate-report-*.md`）+ `achieved.md` + `pm-state.md`（含 PASS 证据）齐备后 `done`。
