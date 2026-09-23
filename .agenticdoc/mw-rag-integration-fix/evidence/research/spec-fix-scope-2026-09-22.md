# 调研：`mw-rag-integration-fix` 的缺口定位（spec 阶段留底）

- 日期：2026-09-22
- 触发：`mw-rag-integration` 独立复核（`evidence/quality-gate-review-2026-09-22.md`）判「需修订」
- 出处：复核报告 + PM 亲自 `rg`/`read` 复核（下面每条都给可复现命令或 `file:line`）

## 1. F-1：AC-006 运行时未接线（功能性缺口）

```
$ rg -n 'rewriteDefaults|resolveForRole|resolveForPhase' packages/coding-agent/src packages/coding-agent/test
src/.../rag/adapter.ts:247:export function rewriteDefaults(role, phase, capabilityRewrite, explicit?) {...}
src/.../rag/config.ts:583:export function resolveForRole(...)
src/.../rag/config.ts:595:export function resolveForPhase(...)
test/suite/rag-config.test.ts:303,307,308,309,310
test/suite/rag-adapter.test.ts:247-258
```

生产调用链（读 `rag/tools.ts`）：

- `callRag`（`tools.ts:426`）：`const requested = params.server ?? undefined` → `server = requested ?? runtime.config.defaultServer`（`:434-435`）；
  `const args = {...params 去掉 server}`（`:515-517`）→ `ragToolCalls(tool, args)`（`:526`）。
- `ragToolCalls`（`adapter.ts:311`）只在 `args.multi_rounds === true || args.auto_rewrite === true` 时才把 `rag_search` 映射为 `rag_search_multi_rounds`（`:313`）。
- 结论：`runtime` 上没有 role/phase，适配器**没有任何机会**注入默认 → AC-006 只在单测里成立。

参考服务映射表（`adapter.ts:272-280`）确认 `rag_search` + rewrite → `rag_search_multi_rounds`，`rag_sources` → `list_sources` + `list_collections`。

## 2. F-2：未起服务的两子句无断言

```
$ rg -n 'unreachable at session start' packages/coding-agent/src packages/coding-agent/test
src/.../rag/tools.ts:9   (注释)
src/.../rag/tools.ts:223 (return anyUnreachable ? `${description} [unreachable at session start]` : description)
（测试零命中）
$ rg -n 'rag-unavailable' packages/coding-agent/test
test/suite/rag-evidence.test.ts:291,528,559,603   ← 证据行本身有测试
```

即：`rag-unavailable` 证据行**有**测试；但「activate 后描述带 marker」这条**没有**，且 `[VERIFY] VC-009` 行不含这两项 → 应记为 ⚠️（复核报告表述略宽，PM 已按精确结论记账）。

## 3. F-4：跨语言 role 回落不一致

| 位置 | 表达式 | 未登记 `type:` 时的 role |
|---|---|---|
| `shared/dispatch-models.ts:78` | `DISPATCH_ROLE_BY_TYPE[taskType] ?? "coding"` | `coding` |
| `mw.py:1866` | `mw_common.TASK_TYPE_TO_ROLE.get(task_type, task_type)` | `task_type` 本身 |
| `mw_common.py:303`（模型解析） | `TASK_TYPE_TO_ROLE.get(task_type, "coding")` | `coding` |

→ 同一份 `type: foobar` 的 task.md，TS worker 按 `coding` 判 required、Python audit 按 `foobar` 判不 required（`requiredFor` 是 `roles[r].require || phases[p].require`，两侧实现一致，分歧只在 role 推导）。

## 4. F-5：文档/契约不一致（D-1~D-8 摘录）

- `README.md:272-275` 的四个 `mw rag` 子命令均缺必填 `--project`（`mw.py:4620-4638` 全是 `required=True`），且 `probe [--server X]` 的 `--server` 在 argparse 里**不存在**。
- `mw.py:4623` 的 probe help 写「never a non-zero exit」，实际 `_cmd_rag_probe` 配置错误时 `return 1`（`mw.py:1426-1428`）；退出码口径 list/probe/sync=1、audit=2 未文档化。
- `launcher.py:351-353` 注入 `MW_RAG_ENABLED`，注释称「worker-side extension reads it to gate its RAG tool registration」；全仓无读取方（只有 `test_rag_launcher.py:157,171` 断言存在）→ 死变量 + 不实注释。
- README 把 `rag_search_multi_rounds`（开了多轮）与 `rag-rewrite-degraded`（服务端改写**失败**的降级标记，`adapter.ts` 的 `meta.rewrite_degraded` → `tools.ts:553`）写成同一件事。

## 5. 结论

5 组缺口全部可由「读代码 + 跑定向测试」确认，无需真实服务；修复面集中在
`rag/tools.ts`、`rag/adapter.ts`、`rag/config.ts`、`worker/worker-mode.ts`、`pm/pm-orchestrator.ts`、
`shared/dispatch-models.ts`、`mw.py`、`launcher.py`、`README.md` 与对应测试。设计见 `design.md`。
