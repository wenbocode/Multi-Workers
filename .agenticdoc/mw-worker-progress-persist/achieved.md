# 结案：mw-worker-progress-persist

## 系统行为变化

只读角色（review / research / verifier / reviewer / rag-research）的 worker 现在由框架保证「检查点一定有落盘证据」，并可用一个受窄约束的工具自己落盘结论：

1. **框架写机器行**：检查点到达时（锚点 `min(30m, budget/2)`），若该角色的 `toolsForType(type)` 不含 `write`，扩展把一行 `CKPT <n>m [machine] ts=… reads=… writes=… phases=… repeat_top=… risk=…` 追加到 `<key>/workers/<task_key>/progress.md`（纯追加，不覆盖、不截断既有内容）。写工具角色行为不变（不写机器行）。
2. **新窄工具 `worker_file`**：仅对无写工具角色注册（注册点在 RAG `try/catch` 之后、`before_agent_start` 之前）。只接受 basename：`progress.md`、`report.md`、`report-<slug>.md`/`report.<slug>.md`（单一来源正则 `WORKER_FILE_NAME_RE`，slug ≤41 字符）；`mode` 默认 `append`；内容按 UTF-8 字节计，上限 64 KiB。非法请求在 `execute` 内 `throw`，因此 trace.log 里与 `[TOOL] worker_file <basename>` 并列出现 `[TOOL_ERR] worker_file <原因>`。没有路径解析 → `task.md`/`trace.log`/`worker.log`/`output.md` 与一切路径变体（`../`、盘符、UNC）在构造上不可达。
3. **steer 按角色分化**：无写工具角色不再收到「把一行追加到 …progress.md」这种它做不到的指令，改为指向 `worker_file` 或「在回复里给一行 CKPT」；有写工具角色的 steer 文本与改造前逐字相同，`deliverAs` 两分支都仍是 `followUp`。
4. **集合单一来源**：`activeToolsForType(type)` 是「角色工具集 + 窄工具」的唯一计算点，被 worker 激活路径与 RAG 工具注册（`rag/tools.ts` 两个分支）共同消费；`TOOL_ALLOWLISTS`/`toolsForType` 与 Python `REGISTRY` 逐字未动。
5. **文档同步**：`dual-toolchain-practice-guide.md` §7 的发散判据由「无 progress.md」改为「progress.md 无自评行（只有机器行）」，并补只读角色口径（`writes=0` 属正常）。

影响面：`packages/coding-agent/src/extensions/agent-team-loop/{worker,rag,pm}` + `packages/coding-agent/test/{extensions,suite}` + `packages/multi-workers/test_mwpp_collection_parity.py` + 两包 CHANGELOG + multi-workers 文档。**零 Python 行为改动**。

修复的现场事故：OverCode `chroma-review-evidence-r1`（146 次工具调用 `writes=0`、终稿请 PM 代为追加结论）——真模型冒烟中同一场景（`type: review`）现在得到框架机器行 + 模型自评行，且终稿不再请求代记。

## 证据

- 逐 AC 证据与判定：`quality-report.md` §3。
- PM 复核日志（含独立复跑与源码级核验）：`evidence/pm-review-log.md`。
- 独立验证（11 VC + 3 变异反例 + sha256 复原）：`evidence/verify-independent-2026-09-23.md`。
- 真模型冒烟：`evidence/verify-run-2026-09-23.md`（临时项目 `C:/Users/wenbozhou/AppData/Local/Temp/mwpp-smoke-t5`，保留未删）。
- 设计期调研：`evidence/research/{spec-progress-persist-baseline,design-worker-progress-persist-baseline,design-verify-collection-parity,design-verify-tool-contract,design-verify-test-harness}-2026-09-23.md`。

## 与计划的偏差

- 测试落点：新增用例放在 `test/extensions/`（T-1/T-2/T-3 各一份 + 既有 4 个 suite 文件同步），未按设计期建议在 `test/suite/` 新建两个文件；包内单一 vitest config，功能等价。
- 真模型冒烟用**源码扩展 + `--no-extensions -e`**（tsx 直跑 CLI）而非 `mw build --install`：避免改动全局扩展目录影响其他窗口；代价是本机全局 bundle 尚未包含本次改动（见遗留）。
- 检查点行为用「`timeout: 1/2` 短预算 + 提示词保证运行时长」触发，而非等 30 分钟真实锚点。
- 机器行只在无写工具角色写（D-104），因此 `type: coding` 的 `machine_lines=0` 是预期而非缺口。

## 遗留

| 遗留项 | 去向 |
|--------|------|
| R-4：窄工具落盘不计 `writes`，只读角色 `risk` 仍可能判 `high` | 接受不处理（GC-4 判据不变），已记录在 design §9、practice guide §7、PM 复核日志 |
| R-5：写层不重复校验 `content` 非空（schema 已拦） | 接受不处理，已记录在 PM 复核日志；若出现绕过 schema 的调用方，另立 key |
| 全局扩展 bundle 未重建（`mw build --install` 未执行） | 需用户决定；执行后本次改动才对真实派发的 worker 生效 |
| `.tmp/` 下 T-3/T-5 的临时产物（steer dump、check log 等） | 属 scratch 目录，未提交；可在用户确认后清理 |
