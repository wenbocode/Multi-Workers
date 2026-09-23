# PM State: mw-worker-progress-persist

## 1. Snapshot
- Key: mw-worker-progress-persist
- Phase: DONE
- Next Action: —
- Started: 2026-09-23 16:14
- Updated: 2026-09-23 17:05
- Completed: 2026-09-23 17:05

## 2. Task Status

| Task | 状态 | 证据 |
|------|------|------|
| T-1 progress 写入器 | done | 5/5 vitest（PM 独立复跑）；`[VERIFY] VC-001/VC-002` |
| T-2 窄工具 `worker_file` | done | 9/9 vitest；12 反例在 regex/写层/execute/schema 四层全拒 |
| T-3 接线 + 既有测试同步 | done | 10/10 新测试；10 文件 94 passed/1 skipped；parity 28 passed |
| T-4 CHANGELOG/文档 | done | 两包 `[Unreleased]` 各一条；`rg 'progress\.md'` 逐处核对 |
| T-5 真模型冒烟 | done | timi/deepseek-v4.1-flash review 任务：机器行 + 自评行 + exit=0 |
| T-6 独立验证 | done | 11 VC 复现；3 条变异全红 + sha256 复原；PASS-with-gaps |

## 3. Evidence Ledger

| 日期 | 动作 | 结果 | 范围 |
|------|------|------|------|
| 2026-09-23 | `vitest --run test/extensions/agent-team-loop-worker-progress.test.ts` | PASS 5/5 | VC-001/002 |
| 2026-09-23 | 同上 `agent-team-loop-worker-file-tool.test.ts` | PASS 9/9 | VC-005/006 |
| 2026-09-23 | 同上 `agent-team-loop-checkpoint-wiring.test.ts` | PASS 10/10 | VC-001~007 + 真管道 `[TOOL]`/`[TOOL_ERR]` |
| 2026-09-23 | 10 文件定向 vitest（新 3 + 既有 7） | PASS 94 passed / 1 skipped | AC-009 受影响面 |
| 2026-09-23 | `pytest -q test_autopilot_l0.py test_autopilot_dispatch.py test_rag_research.py test_mwpp_collection_parity.py` | PASS 28 passed | VC-008 / AC-008 |
| 2026-09-23 | `npm run check` | PASS EXIT=0 | AC-009 |
| 2026-09-23 | 真模型冒烟（源码扩展 + tsx 直跑 CLI） | PASS：机器行 + 模型自评行 + 终稿无「代为追加」+ exit=0 | VC-011 / AC-011 |
| 2026-09-23 | 变异反例 M-1/M-2/M-3（放宽正则 / 去角色门禁 / 污染 parity） | PASS（三条全部变红；复原后 sha256 逐字节相等） | 守卫有效性 |
| 2026-09-23 | `git show HEAD:` 基线 steer 归一化比对 | PASS `NORMALIZED_EQUAL: true`（132 字符逐字相同） | AC-003 / AC-004 |

## 4. Hypothesis Queue

*(empty)*

## 5. Decisions

- D-101 窄工具 `worker_file`（basename-only，无路径解析）而非通用 `write` + 路径守卫；D-102 白名单只有 `progress.md`/`report.md`/`report[-.]<slug>.md`（`output.md` 不入白名单，D-103）；D-104 机器行只写给无写工具角色；D-105 机器行格式；D-106 新增 `activeToolsForType`（`TOOL_ALLOWLISTS`/`toolsForType` 逐字不动，零 Python 改动）；D-107 纯追加；D-108 窄工具不计入 `WRITE_TOOLS`；D-109 非法请求 `throw`（返回 `isError` 对象无效，见 `agent-loop.ts:696-704`）。
- 设计期修正（来自 RQ-D1/D2/D3 实测）：正则分隔符放宽为 `[-.]`；`mode` 默认值在 `execute` 内落地；64 KiB 用 `Buffer.byteLength`；`additionalProperties:false`；注册点移到 RAG `try/catch` 之后；4 个既有 fake-pi 测试同批补 `registerTool`；新增 10-key TS 白名单快照（既有 parity 只锁 6 key）。
- 残留（接受不处理）：R-4 窄工具不计 `writes` → 只读角色 `risk` 仍可能 `high`（GC-4 判据不变）；R-5 写层不重复校验 `content` 非空（schema 已拦）；另：本机全局扩展 bundle 未重建（未执行 `mw build --install`）。

## 6. Turn End Records

*(empty)*

## 7. Process Log

- 16:14 建 key；SPEC→DESIGN→PLAN→TASKS 门禁全绿（mermaid 0 error，AC↔VC 11/11）。
- 16:20-16:30 并行派 3 个 research worker（RQ-D1 工具契约 / RQ-D2 集合-parity / RQ-D3 测试面）；吸收后修订 design 5 处、T-2/T-3/T-5 任务书重写。
- 16:24 T-1 派发 → 16:29 done（PM 复跑 5/5）。
- 16:29 T-2 派发 → 16:35 done（PM 复跑 9/9）。
- 16:36 T-3 派发 → 16:43 done（PM 复跑 10/10 + parity 28）。
- 16:43-16:45 T-4 PM 直执（两包 CHANGELOG + practice guide §7 + pm-orchestrator 措辞）。
- 16:46 T-5 派发 → 16:50 done（真模型 PASS；发现 `PI_WORKER_TASK` 必须绝对路径）。
- 16:52 EXECUTE→VERIFY；T-6 派发 → 16:59 done（PASS-with-gaps；G1 schema 拒绝路径真管道用例缺失）。
- 17:03 PM 补齐 G1 用例（10/10 绿）、修正 G2/G3，`npm run check` EXIT=0，写质检报告与结案文档。
*(empty)*
