# 设计调研：接线点与替代方案（design 阶段留底）

- 日期：2026-09-22
- 出处：`rag/tools.ts`、`rag/config.ts`、`rag/adapter.ts`、`worker/worker-mode.ts`、`shared/dispatch-models.ts` 实读

## 1. 为什么选 `callRag` 作为唯一接线点

- 所有 7 个工具 handler（`rag/tools.ts:226-368`）都在最后一行调用 `callRag(runtime, <logical>, params, signal, onUpdate)`，签名统一 → 一处修改覆盖全部工具。
- `callRag` 已经是 server 解析（`:434-435`）、capability（`:461`）、熔断（`:457`）、预算（`:464-512`）的收口点，role/phase 默认属于同一层。
- 参数转 wire 工具名发生在 `ragToolCalls(tool, args)`（`:526`）+ `RAG_TOOL_MAP`（`adapter.ts:272-280`），因此注入必须发生在 `:515-517` 的 `args` 构造之前/之中。

## 2. 与既有函数的关系（避免第二套判定）

- `resolveForRole`（`config.ts:584`）返回 `{server, source, rewrite}`，内部已做 `spec.server ?? defaultServer` 与
  `spec.rewrite ?? (capabilities.rewrite && isResearchRole(role))`。
- `resolveForPhase`（`config.ts:596`）同理，研究阶段 = `spec`/`design`。
- `rewriteDefaults(role, phase, capabilityRewrite, explicit?)`（`adapter.ts:247`）是**已存在的**开关判定函数，
  单测（`rag-adapter.test.ts:247-258`）覆盖了 research/spec/rag-research/coding/review 五类；
  本 key 把它从「只有单测调用」变为「生产调用」，**不新增函数**。
- 因此 D-102 的实现是：`role`/`phase` 非空时先算 `roleRes`/`phaseRes`，再用 `rewriteDefaults` 决定是否给
  `rag_search` 注入 `multi_rounds: true`；`source` 同理由 role 优先解析。

## 3. 两个必须保留的既有行为（回归面）

1. **未启用/无 role/phase → 零变化**：现有 `rag-config.test.ts:303-310` 与 `rag-required.test.ts` 的用例直接构造
   `runtime`，若不传 `role`/`phase` 字段，实现必须退化为旧行为（`server = params.server ?? defaultServer`、
   `args` 原样）。这是 T-15 的回归红线（VC-110）。
2. **`[mw] Rewrite:` 注入行**：现有渲染在无 role/phase 时必须逐字节不变（父 key 的 VC-001/VC-022 与
   `test_rag_launcher.py`/`test_rag_phase.py` 的字节断言都吃这条），因此 D-104 采用「未知不写」。

## 4. Python 侧对齐的边界

- `mw.py:1866` 的 role 只用于 audit 的 `required` 判定与报告归属（`role` 字段），不参与任何写操作 → 改回落值安全。
- `mw_common.TASK_TYPE_TO_ROLE` 是唯一映射表；`mw_common.py:303` 已用 `coding` 兜底 → 改后三处一致，无需新表。
