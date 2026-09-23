# Task T-5: 增量独立验证（T-3B / T-3C 之后的 delta）

## 元信息
- Stage: 3（T-4 之后）
- 依赖: T-4 已完成（PASS）；T-3B/T-3C 是 T-4 之后的 PM 直执修复
- Agent: coding worker（独立视角）
- ac_refs: [AC-301, AC-302, AC-303, AC-304, AC-306]
- vc_refs: [VC-301~VC-312, VC-305b, VC-308b, VC-309b]

## 背景：T-4 之后的两次 PM 直执改动

1. **T-3B**（T-4 的「反例 D」目标）：`formatDoctorReport` 的 RAG 行门控改为镜像 `mw.py:523` 的
   `exists or enabled`，新增导出谓词 `shouldShowRagDoctorRow`（`pm/ui-bridge.ts`）；新增 VC-309b。
2. **T-3C**（T-4 的「发现 3」+「反例 B 不变红」）：
   - `rag/config.ts`：新增 `optionalTrimmedString` 并用于 `mcp.url`、`mcp.token_env`、`skill.dir`、
     `skill.cli_entry`（镜像 Python `_rag_finalize_mcp`/`_rag_finalize_skill` 的 `.strip()`），
     新增测试文件 `test/suite/rag-trim-parity.test.ts`（VC-305b，与 Python 子进程逐字比对 + 空白值双侧拒绝）。
   - `rag-window.test.ts`：新增 VC-308b —— 用 `MW_PY` 指向 stub 脚本，**真 spawn** 断言
     argv 为 `["rag", <sub>, ...args, "--project=<controlRoot>"]` 且 exit 1 被保留（T-4 报告反例 B 不变红＝缺这条）。
   - **未修**（需你实测确认并作为遗留 R-6）：`path_roots_file` 仍不 trim —— 因为 Python 的
     `path_roots_file` 字段被 strip、但 `path_roots_digest` 用的是**未 strip** 的串（`mw_common.py:636-637`）。

## 交付物

`.agenticdoc/mw-rag-window-parity/evidence/verify-run-delta-2026-09-23.md`（**唯一允许写的文件**；只读其余一切）

落盘：先 write 骨架（§0~§5），再逐节 edit。建议 ≤ 200 行。

## 必须做

### 1) 零回归（记原始输出/exit code）

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-config.test.ts test/suite/rag-parity.test.ts test/suite/rag-tools.test.ts test/suite/rag-required.test.ts test/suite/rag-role-defaults.test.ts test/suite/rag-trim-parity.test.ts test/suite/rag-window.test.ts test/suite/rag-adapter.test.ts test/suite/rag-transport.test.ts test/suite/rag-budget.test.ts test/suite/rag-evidence.test.ts test/suite/rag-toolmap.test.ts test/suite/rag-unreachable.test.ts test/suite/rag-research-doc.test.ts`
- `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts`
- `cd packages/multi-workers && python -m pytest -q`
- 仓根 `npm run check`（记 exit code）
- `git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py`（应为空）
- 记录 `[VERIFY] VC-305b:*` / `VC-308b:*` / `VC-309b:*` 的原文

### 2) 反例（逐条：改了什么 / 什么红 / 还原 / sha256 自检）

- **A（trim 真的必要）**：把 `rag/config.ts` 的 4 处 `optionalTrimmedString` 改回 `optionalString`
  → `rag-trim-parity.test.ts` 至少 2 例必须红。
- **B（`--project` 拼接真的被钉住）**：把 `shared/mw-runner.ts` 里 `runMwCliRaw` 的
  `` `--project=${projectDir}` `` 改成 `"--project=."` → `VC-308b` 必须红（T-4 报告此反例当时**全绿**，
  即当时无钉住用例；现在应红）。
- **C（doctor 门控）**：把 `if (shouldShowRagDoctorRow(report.rag))` 改回 `if (report.rag)` → VC-310 必须红。
- **D（fingerprint 真的被比）**：把 `rag/block.ts` 或 `rag/config.ts` 里 canonical JSON 的某一键改名（如
  `path_roots_file` → `path_roots_files`）→ `rag-parity.test.ts` 的 VC-027 或 `rag-trim-parity.test.ts` 必须红。

> 任一条不变红 ⇒ 该断言是装饰：如实降级并写明原因。

### 3) R-6 实测（不得只复述我的说法）

自建 fixture：`servers: {S: {transport: mcp, mcp: {url: ...}, path_roots_file: " .mw/rag-roots.json "}}`
（padding 前后各一空格；`.mw/rag-roots.json` 真实存在），分别取两侧加载结果，记录：

- TS：`pathRootsFile` 实测值、`pathRootsDigest` 实测值、`fingerprint`
- Python：`load_rag_config` 的 `path_roots_file` 实测值、`path_roots_digest` 实测值、`rag_fingerprint`
- 结论：两侧 fingerprint 是否相等；若不等，差异是否**仅**来自 `path_roots_file` 这一键（用改动该键的最小实验证明）

### 4) 逐 VC 表（只覆盖本次 delta 涉及的）

| VC | 断言 | 发射位置 file:line | 实测行原文 | 强度 |
（VC-305b / VC-308b / VC-309b / VC-310 / VC-301~303 复跑即可）

### 5) 未覆盖与限制

如实写：真实 RAG 服务联调、pi TUI 手工操作、`/mw rag init` 的写盘副作用至今**未**在窗口里人工跑过等。

## 验收

- 报告含上述 §0~§5；除报告外零写入；反例改动全部 sha256 复原；未 commit。
