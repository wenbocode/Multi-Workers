# Spec: `mw-rag-integration-fix`（关闭独立复核发现的缺口）

- 上位 key：`mw-rag-integration`（已 DONE，但独立复核 `mw-rag-qg-review-c` 判「需修订」）
- 复核依据：`.agenticdoc/mw-rag-integration/evidence/quality-gate-review-2026-09-22.md`
- 性质：**修复 + 证据加固**，不新增 RAG 功能面；K3 硬门禁仍不做

## §0 Goal Alignment

- **对齐 goal.md**：本 key 服务于「Agent Team 协作框架」的可靠性——Worker 的检索行为必须**真的按角色/阶段生效**，
  而不是「有函数、有测试、有证据行但运行时从不调用」（`phase:` 头已经踩过一次同类坑）。
- **GC 继承**：GC-2（不改 pi core）、GC-5（工具白名单跨语言 parity）、GC-7（goal.md 锚点）、
  GC-1（无中心调度器）、K1 的 D-014（未启用 RAG 的项目零影响、不写文件）。
- **冲突**：无。本 key 不改变已交付的对外契约（配置格式、工具名、证据行格式、golden 字节）。
- **预期收益**：AC-006 从「纸面成立」变为「运行时成立」；跨语言 `required` 判定一致；文档可直接照抄执行；
  证据行强度经第三方按 `file:line` + 反例可复核。

## 职责范围

**做**：F-1（AC-006 运行时接线）、F-2（两子句补断言）、F-3（VC-018 证据层级）、F-4（跨语言 role 回落）、
F-5/D-1~D-8（文档与实现不一致）。

**不做**：K3 硬门禁；`rag-research` 的 conductor 派发放开；真实 rag-mcp 线上联调（仍属发布前 smoke）；
`rag_chat` 的重复计费语义；R-4 的多份调研文档遍历。

## 验收标准

| ID | 验收标准 | 来源 |
|---|---|---|
| AC-101 | **role/phase 默认必须在运行时生效**（F-1）：会话角色/阶段已知时，`rag_search` 未显式传 `multi_rounds`/`auto_rewrite` 且适配器解析出的 rewrite 为 true → **实际发出的 MCP 工具名必须是 `rag_search_multi_rounds`**；解析为 false 时必须是 `rag_search`。默认 server/source 同理由「显式参数 > role > phase > `default_server`」解析 | 复核 F-1 / AC-006 |
| AC-102 | **该行为必须有 fixture 级证据**（F-1 测试面）：`[VERIFY] VC-008` 行的值必须取自 fixture 实际观测到的工具名/请求参数，不得来自直调纯函数的返回值 | 复核 F-1 / design §7 VC-008 原期望 |
| AC-103 | **未起服务的两子句有断言**（F-2）：至少一条集成用例断言（a）不可达 server 激活后工具描述含 `[unreachable at session start]`；（b）首次调用后 trace 增量含 `rag-unavailable` | 复核 F-2 |
| AC-104 | **跨语言 role 回落一致**（F-4）：`task.md` 的 `type:` 未登记时，TS worker 与 Python `mw rag audit` 必须按**同一** role（`coding`）判定 `required`；有 `type: <未登记>` 的两侧对照用例 | 复核 F-4 |
| AC-105 | **VC-018 的证据层级声明与事实一致**（F-3）：或补一条运行时用例（真实 key 布局下 validator 取到文档并判 ok），或把 `evidence-requirement.md` 与 design 中的层级声明降为 L1 —— 不得保留 L2 声明而只有纯函数证据 | 复核 F-3 |
| AC-106 | **文档与实现一致**（F-5）：README 的 `mw rag` 用法可直接执行（含必填 `--project`）、不含幻影参数、写清退出码；`MW_RAG_ENABLED` 若不是契约则删除（含不实注释与测试断言）；`rag-rewrite-degraded` 的语义描述与 `adapter.ts` 一致 | 复核 F-5 / D-1~D-8 |
| AC-107 | **零影响与零回归**：未启用 RAG 的项目行为逐字节不变（含 task.md 渲染与 registry）；`packages/coding-agent` 的 `rag-*` 套件与 `packages/multi-workers` 的 `test_rag_*.py` 全绿；golden 字节/指纹不变（有意变更须单列） | D-014 / GC-5 |
| AC-108 | **可复核性**：每条修复的证据行（`[VERIFY]`）可由第三方按 `file:line` 复现，且不得是「期望值与实际值同源」的自证常量；行内至少一个字段来自被测数据 | 复核 A 节口径 |

## 可复用资产

- `mw-rag-integration` 的 28 条 `[VERIFY]` 采集器经验、跨语言 golden 锁（`test/fixtures/rag-block.golden.md`）、
  TS fixture 传输层（`test/suite/rag-fixture.ts`，含 `calls` 计数与故障注入）、Python `test_rag_*.py` 的 `-s` 证据行口径。
- 复核者已验证有效的**反例试验**手法（改被测数据 → 看红 → 还原 + sha256 自检），T-15/T-16 的证据必须能被同样手法推翻。
- `workerModeActivate` + 假 pi 的驱动装置（`test/suite/rag-required.test.ts`）——T-15/T-17 直接复用，不重造。

## 需规避坑点

- **P-005（有实现无调用方）**：本 key 的核心就是它；判据必须是「谁在运行时调用」，不能是「函数存在 + 单测绿」。
- **P-006（绿灯测试里 `console.log` 被吞）**：证据行必须 `process.stdout.write`（TS）/ `print` + `pytest -s`（Python）。
- **P-007（review worker 无落盘通道）**：审查/长报告类任务用 **coding 型 worker + 单文件落盘**。
- 多会话并行：只改本 key 声明的文件；不碰其他会话的未提交改动；不 commit。
- `test_autopilot_l0.py` 的文本层守护（禁 `- Phase:` 字面量等）与 `mw-rag/SKILL` 字面量守护：本 key 不改守护，实现侧绕开。
