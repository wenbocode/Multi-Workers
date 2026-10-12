# T-08 — golden fixture + Python 同语义一致性（含 BOM 修复）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.4.3（一致性测试方案）+ §4.6 C-3（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-005 + 下列证据文件
- 证据: `evidence/research/design-role-key-identity-20261011.md` §2/§3；`packages/coding-agent/test/suite/autopilot-config-parity.test.ts`（范式参照）
- **唯一允许改的路径**: `packages/multi-workers/mw_common.py`；`packages/coding-agent/test/fixtures/task-md-header-cases.json`；新增 `packages/multi-workers/test_task_type_parity.py`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-005｜VC: VC-040, VC-042｜波 2｜链 S3（依赖 T-06）
- 验收命令（PM 执行）: `cd packages/multi-workers && python -X utf8 -m pytest test_task_type_parity.py -q`（文件名为建议，按实际新增文件执行）

## 必须实现
1. 新增 `packages/coding-agent/test/fixtures/task-md-header-cases.json`（18 条；内容 **base64 内联**以规避 `.gitattributes` 行尾改写）。
2. `packages/multi-workers/mw_common.py` 的 `read_task_type` 改为与 TS 同语义：**剥 BOM** + 首个 `type:` + 同样的头部边界。 对照基准以 `shared/task-frontmatter.ts` 的**返回对象**为准（`readTaskType` ⇒ `TaskTypeReading`，含 `type`/`source`/`bomStripped`）；Python 侧建议返回 `(type, source)` 或同形结构以便逐字段比对，**不要**只比对 `type` 而忽略 BOM/来源差异。
3. 新增 Python 一致性测试（放 `packages/multi-workers/`），用 **node 反向差分**：调用 node 侧解析同一 fixture 并逐条比对；**node 缺失即 fail**（不得静默 skip），范式照抄 `test_autopilot_config_parity.py`。
4. BOM 断言：7 本历史任务书（`_scratch/workers/mw-dr-autodispatch`、`mw-dispatch-reliability/workers/{mw-dr-glm53,mw-dr-keyed-probe,mw-dr-live-claude,mw-dr-live-ok,mw-dr-pi-timi-test}`、`mw-dispatch-flow-fixes/workers/smoke-ac015-ac016`）在修复后可读到 `type:`；全量 308 本 `py_md5 == ts_md5`。
5. 不得改 `launcher.py`/`mw.py` 的调用协议（只改 `mw_common.read_task_type` 实现）。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
