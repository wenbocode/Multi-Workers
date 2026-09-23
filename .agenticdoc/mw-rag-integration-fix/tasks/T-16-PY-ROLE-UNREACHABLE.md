# Task T-16: 未起服务两子句断言 + Python role 回落对齐（F-2 / F-4）

## 元信息
- Stage: 2
- 依赖: 无（可与 T-15 并行；本任务只改 Python `mw.py`/`mw_common.py` 与两侧测试，与 T-15 的 TS 文件零重叠）
- 风险等级: 低-中
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-103, AC-104]
- vc_refs: [VC-104, VC-105]
- pattern_refs: []

- **`[VERIFY]` 行**：TS 用 `process.stdout.write("[VERIFY] ...\n")`（vitest `silent: "passed-only"` 吞 `console.log`）；
  Python 用 `print` + `pytest -q -s`（坑点 P-006）。行内至少一个字段取自被测数据（AC-108）。

## 背景

复核两条缺口：

1. **F-2**：AC-007 要求「服务未启动时 activate 仍注册工具且描述含 `[unreachable at session start]`；首次调用返回
   类型化错误并追加 `rag-unavailable` 证据行」。代码有（`rag/tools.ts:221-223`、`evidence.ts`），但
   `rg 'unreachable at session start'` 在测试里**零命中**，`[VERIFY] VC-009` 行也不含这两项。
2. **F-4**：未登记 `type:` 时 role 回落两侧不一致 —— `shared/dispatch-models.ts:78` 是 `?? "coding"`，
   `mw.py:1866` 是 `?? task_type`（`mw_common.py:901` 同样是 `?? task_type`）→ 同一份 `type: foobar` 的 task.md，
   TS worker 按 `coding` 判 `required`、Python audit 按 `foobar` 判不 required。

设计：`design.md` D-105、VC-104/VC-105。

## 必须实现

### 1) Python role 回落对齐（D-105）

- `mw.py:1866`：`role = mw_common.TASK_TYPE_TO_ROLE.get(task_type, task_type)` → 回落统一为 `"coding"`
  （与 `shared/dispatch-models.ts:78`、`mw_common.py:303` 一致）。
- `mw_common.py:901`（`render_rag_block` 的 role 解析）：同样回落 `"coding"`。
- **硬要求**：`test/fixtures/rag-block.golden.md` 的字节**不得变**（golden fixture 的 `type` 是已登记的 `coding`，
  回落路径不参与）——若变了，停下来说明原因，不要自行重生成。

### 2) F-2 的断言（TS 侧）

在 `packages/coding-agent/test/suite/rag-tools.test.ts` 或新建 `test/suite/rag-unreachable.test.ts` 中补一条集成用例：

- 用 `test/suite/rag-fixture.ts` 把某个 enabled server 指到一个**不可达**端口（或让假传输层的 `initialize` 抛
  `connect` 类错误），跑 `registerRagTools(...)` + `await runtime.ready`；
- 断言 `(captured tool).description` 含 `[unreachable at session start]`；
- 再驱动一次 `rag_search`，断言 `trace.log`（或 hooks 的 evidence 收集器）**增量**里含 `rag-unavailable`（用增量断言，
  不比全文件）；
- 打出 `[VERIFY] VC-104: unreachable_marker=true rag_unavailable_line=true server=<实际 server 名>`。

### 3) F-4 的两侧对照用例（VC-105）

- TS：`test/suite/rag-required.test.ts` 增一条 `type: foobar`（未登记）的用例：断言 worker 判定 role = `coding`，
  且当 `roles.coding.require: true` 时发射 `rag-required-missing`（`[VERIFY] VC-105: ts_role=coding ts_required=true ...`）。
- Python：`test_rag_audit.py` 增一条同形态 task.md（`type: foobar`），断言 audit 报告里该 worker 的 `role == "coding"`
  且 required 结论与 TS 一致（`[VERIFY] VC-105: py_role=coding py_required=true ...`）。
  两侧的 `type:` 取值必须**字面相同**，便于第三方对照。

## 验收

1. TS：新增/相关套件全绿；十套 `test/suite/rag-*.test.ts` 全绿（基线 `97 passed | 1 skipped`）。
2. Python：`cd packages/multi-workers && python -m pytest test_rag_audit.py test_rag_config.py test_rag_phase.py test_rag_cli.py test_rag_launcher.py test_rag_research.py -q` 全绿（基线 76 passed，允许新增）。
3. `test_autopilot_l0.py` 与 `test/fixtures/rag-block.golden.md` **零 diff**（`git status --porcelain` 自查）。
4. `python -m pytest -q` 全量无新增失败（基线 `802 passed, 9 deselected`；本机 `packages/agent`/`ai` 的既有环境噪声不算）。
5. 仓根 `npm run check` exit 0（若 TS 侧有改动）。

## 禁止

- 不改 `rag/tools.ts` 的运行时解析逻辑（归 T-15）；若发现 T-15 与本任务需要同一处改动，**停下来上报**而不是并发修改同一文件。
- 不改 `launcher.py` / README / env 文档（归 T-17）；不改 `test_autopilot_l0.py` 与文本层守护；不重生成 golden；不 commit。
