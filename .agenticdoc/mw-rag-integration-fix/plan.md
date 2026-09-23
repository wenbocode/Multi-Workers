# Plan: `mw-rag-integration-fix`

- spec：AC-101~AC-108；design：D-101~D-108、VC-101~VC-110
- 阶段：1 接线（T-15）→ 2 证据与对齐（T-16）→ 3 文档与重建（T-17）→ 4 验证（T-18）→ 5 质检收尾（PM）

## 阶段与交付

| 阶段 | 目标 | 任务 | 交付 |
|---|---|---|---|
| 1 | role/phase 默认真正接线到运行时 | T-15 | `rag/tools.ts` 注入面 + 工具描述/注入块一致性 + fixture 级证据 |
| 2 | 未起服务两子句 + 跨语言 role 对齐 | T-16 | 集成断言 + Python 回落对齐 + 对照用例 |
| 3 | 证据层级与文档一致 + 捆绑重建 | T-17 | VC-018 层级落定 + README/env/help/退出码 + `dist` 重建 |
| 4 | 独立验证（第三方视角复跑） | T-18 | `evidence/verify-run-*.md`：VC-101~VC-110 实测行 |
| 5 | 质检 + 结案 | PM | `evidence/quality-gate-report-*.md`、`achieved.md`、phase → DONE |

## 任务表

| 任务 | 阶段 | 内容 | ac_refs | vc_refs | 依赖 |
|---|---|---|---|---|---|
| T-15 | 1 | role/phase 默认注入 `callRag`（D-101/102/103）+ 注入块 `[mw] Rewrite:` 与行为一致（D-104）+ fixture 级证据行 | AC-101, AC-102, AC-107 | VC-101, VC-102, VC-103, VC-109, VC-110 | 无 |
| T-19 | 1 | 默认解析收敛为单一 `resolveDefaults`（D-109）+ Python rewrite 兕底对齐 + 跨语言对照 fixture（VC-111） | AC-101, AC-107 | VC-101, VC-102, VC-110, VC-111 | T-15（收尾，在 T-17 之前） |
| T-16 | 2 | 未起服务两子句断言（F-2）+ Python role 回落对齐 TS（D-105）+ `type: foobar` 两侧对照 | AC-103, AC-104 | VC-104, VC-105 | 无（文件不重叠） |
| T-17 | 3 | VC-018 层级落定（D-107）+ README/env/probe help/退出码（D-108）+ 删 `MW_RAG_ENABLED`（D-106）+ `dist` 重建 | AC-105, AC-106, AC-107 | VC-106, VC-107 | T-15（重建须在 TS 改动之后） |
| T-18 | 4 | 全量复跑与证据采集（含反例试验）：TS `rag-*`、`test_rag_*.py`、`test_autopilot_l0.py` 零 diff、`npm run check`、bundle self-check | AC-107, AC-108 | VC-101~VC-110 | T-15, T-16, T-17 |

## 并行与所有权

- T-15（TS：`rag/*.ts`、`worker/*`、`pm/*`）与 T-16（Python：`mw.py` + 两侧测试）文件不重叠 → 并行。
- T-19 串行在 T-15 之后（同区域：`rag/config.ts`/`rag/block.ts`/`rag/tools.ts`），并在 T-17 之前（T-17 要基于最终 TS 源码重建 dist）。
- T-17 必须在 T-15 之后（`dist` 重建 + README 描述运行时行为），可与 T-16 并行（文件不重叠）。
- T-18 串行在全部实现之后（证据必须落在最终源码上）。

## 收尾要求（父 key 的教训）

- 证据行一律 `process.stdout.write`（TS）/ `print` + `pytest -s`（Python），且至少一个字段取自被测数据（P-006 + VC-109）。
- 不得以「函数存在 + 单测绿」判定完成（P-005）；每条 AC 的判据写「谁在运行时调用它」。
