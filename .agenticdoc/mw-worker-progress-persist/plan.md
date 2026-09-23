# Plan: mw-worker-progress-persist

- key: `mw-worker-progress-persist`
- 依赖: spec.md（AC-001~AC-011）、design.md（D-101~D-109、VC-001~VC-011）
- 写入面纪律（design §3）：只允许改 4 个 TS 源文件（`worker/worker-file-tool.ts`（新）、`worker/worker-mode.ts`、`worker/output-writer.ts`、`rag/tools.ts`）+ TS 测试 + 两个 CHANGELOG 的 `[Unreleased]` + 必要的文档同步；**Python 零改动**（D-106）；不改 `~/.pi/agent`。

## 并行性分析（拆解前强制）

| 单元 | 文件面 | 共享资源/冲突面 | 并行判定 |
|---|---|---|---|
| T-1 写入器 | `worker/output-writer.ts` + 新测试文件 | 仅 T-1 写该源文件 | 可与 T-2 并行 |
| T-2 窄工具 | `worker/worker-file-tool.ts`（新）+ 新测试文件 | 新文件，无他人写入 | 可与 T-1 并行 |
| T-3 接线 | `worker/worker-mode.ts` + `rag/tools.ts` + 新测试文件 | import T-1/T-2 的导出 → 类型检查必须先有对象 | **串行**（T-1、T-2 之后） |
| T-4 文档/变更记录 | 两个 `CHANGELOG.md` + 文档 | 单写者，内容依赖 T-3 最终行为与文本 | 串行（T-3 之后，PM 直执） |
| T-5 bundle + e2e | `dist/extensions/agent-team-loop.js`（构建产物）+ 冒烟证据 | 重活资源：`mw build --install`、live 派发、模型额度 | 串行（T-4 之后） |
| T-6 独立验证 | 仅 `evidence/verify-*.md` | 只读源码；无写冲突 | 串行（T-5 之后，独立 worker） |

- 必须串行的理由：T-3 的 `import` 依赖 T-1/T-2 的导出签名（类型检查是硬依赖）；T-4 的措辞依赖 T-3 落地后的实际 steer/格式文本；T-5 的构建产物是全仓共享资源（`mw build --install` 影响后续所有 spawn）；T-6 需在产物冻结后复现。
- 可并行的窗口：T-1 ∥ T-2（两个互不相交的文件面 + 各自独立测试文件）。

## Stage 1 — 窄工具与写入器（AC-005/AC-006/AC-007 部分）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-1-PROGRESS-WRITER | `worker/output-writer.ts`：新增 `appendProgressLine(taskKey, agenticdocRoot, line)`（复用 `outputDir` 穿越守卫 + `appendFileSync`，纯追加）与 `formatMachineCheckpoint(...)`（格式见 design D-105）；单测覆盖「新建文件/追加不截断/格式字段齐全」 | 代码 + 单测（VC-001/002 的写入器半侧） | coding worker |
| T-2-WORKER-FILE-TOOL | `worker/worker-file-tool.ts`（新）：`WORKER_FILE_TOOL` 常量、`isAllowedWorkerFile(name)` 正则契约、`registerWorkerFileTool(pi, taskDir)`（typebox 参数 `file`/`content`/`mode`）；单测覆盖 VC-005 与 VC-006 的 12 项反例矩阵 | 代码 + 单测（VC-005/VC-006） | coding worker |

退出条件：T-1、T-2 各自单测全绿；`npm run check` 对新增文件无错误；无其它文件被改动（`git status` 只含这两处的预期文件）。

## Stage 2 — 接线与角色分化（AC-001~AC-004/AC-007/AC-008）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-3-CHECKPOINT-WIRING | `worker/worker-mode.ts`：新增导出 `activeToolsForType(type)` + `checkpointSteerText(...)`；仅当角色无 `write` 时在 `:677-697`（RAG try/catch 之后、`before_agent_start` 之前）注册窄工具；`writeCheckpoint()` 按角色分流（无写工具 → `appendProgressLine` 机器行 + 分化 steer，两分支 `deliverAs` 均 `followUp`；有写工具 → 渲染文本逐字不变，基线取 `git show HEAD:<file>`）；`rag/tools.ts`：`:22` import 改 `activeToolsForType` 且 `:402`/`:406` 两分支都改；**既有测试同步**（`autopilot-protocol` / `dual-root-worker` / `cross-drive-worker` / `autopilot-read-scope` 补 `registerTool` stub 与期望集）；新增 `packages/multi-workers/test_mwpp_collection_parity.py`（10-key 快照，复用 `_parse_ts_allowlists`） | 代码 + 单测 + 既有测试同步（VC-001~VC-004、VC-007、VC-008） | coding worker |

约束：T-3 必须先用 `git show HEAD:...worker-mode.ts` 固定 coding 分支的 steer 基线文本（VC-004 的「逐字不变」判据），不得凭记忆重写。

退出条件：VC-001~VC-004、VC-007、VC-008 全绿；`TOOL_ALLOWLISTS` 逐项与 HEAD 相等；`agent-team-loop` 与 `rag-*` 相关套件无新增失败。

## Stage 3 — 变更记录与文档（AC-010）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-4-DOCS-CHANGELOG | `packages/coding-agent/CHANGELOG.md` 与 `packages/multi-workers/CHANGELOG.md` 的 `[Unreleased]` 各一条（描述窄工具、机器行、角色化 steer、生效需 `mw build --install`）；同步文档中对 `progress.md` 的陈述（`rg -n 'progress\.md'` 命中处逐条核对） | 文档 + 变更记录 | PM 直执 |

退出条件：`rg -n 'progress\.md'` 的每处陈述与实现一致（零悬空符号）；两条 CHANGELOG 条目在正确的 `[Unreleased]` 子小节下。

## Stage 4 — 构建与真实冒烟（AC-011）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-5-BUILD-SMOKE | `mw build --install` 重建 bundle；派一个 `type: review` 短预算任务（task.md 内 `timeout:` 压到可触发检查点的量级）；断言 (a) 任务目录 `progress.md` 含机器行或工具落盘行 (b) 终稿回复不含「无法写入 progress.md / 请编排方代为追加」 (c) `worker.log` `done exit=0` | `evidence/verify-run-*.md` + 产物 | coding worker |

退出条件：VC-011 三项断言成立；若因模型/额度原因无法完成，须给出 trace 级替代证据并明示降级理由（不得静默标 PASS）。

## Stage 5 — 独立验证（AC-009 的回归面 + 全部 VC）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-6-VERIFY | 第三方独立复现 VC-001~VC-011；至少 3 条反例必须变红并复原（反例建议：把 `report-*.md` 正则放宽到 `.*\.md`、把机器行写给 coding 角色、把窄工具加入 `TOOL_ALLOWLISTS` 让 parity 变红）；零回归核对（`npm run check`、定向 pytest、Windows 基线 89 不涨） | `evidence/verify-run-independent-*.md` | coding worker（独立，不参与实现） |

退出条件：报告含逐 VC 表 + 反例记录 + 零回归结论 + 未覆盖项；除报告外不改文件。

## 依赖与顺序

```
T-1 ─┐
     ├─→ T-3 ─→ T-4 ─→ T-5 ─→ T-6
T-2 ─┘
```

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 守卫失效导致只读角色可写被审代码（P-004 同族） | 窄工具不以路径为输入，只接受 basename 正则；VC-006 12 项反例矩阵；T-3 不得引入任何 `path.resolve(用户输入)` |
| coding 分支 steer 文本被顺手改写（静默回归） | VC-004 以 `git show HEAD:` 基线逐字比对；T-3 任务书要求先固定基线 |
| `applyRagTools` 改动波及 PM/其它调用方 | D-2 调研已列调用方清单；T-3 只改集合计算，不改 RAG 语义；VC-007 断言逐 type 相等 |
| 既有测试被 D-106 打破（RQ-D2 F5：4 个 fake-`pi` 测试 + 只读类型期望集） | 纳入 T-3 同批同步（补 `registerTool` stub + 期望集加 `worker_file` + 保留 `test_autopilot_l0.py:313-318` 三个子串）；L0 文件保持逐字节未改 |
| legacy bucket（coding/review/research/fallback）值无 parity 锁 | 新增 `test_mwpp_collection_parity.py` 的 10-key 全量快照（复用 helper，不复制实现） |
| e2e 冒烟受模型/额度影响 | 缩短 `timeout:` 触发检查点；失败时给 trace 级替代证据并显式降级说明 |
| Windows 基线 89 项环境失败被误判为回归 | 只与基线比对增量，不追既有失败（AGENTS.md 口径） |

## 交付节奏

1. 派 T-1 ∥ T-2 → 回读 → PM 跑 `npm run check` + 定向单测；
2. 派 T-3 → 回读 → PM 跑定向测试与 parity 用例；
3. PM 直执 T-4；
4. 派 T-5（构建 + 真实冒烟）→ 回读；
5. 派 T-6（独立验证）→ PM 写质检报告 + `achieved.md` → 推进 DONE。
