# Task T-18: 独立验证与证据采集（第三方视角）

## 元信息
- Stage: 4
- 依赖: T-15、T-16、T-17 全部完成（证据必须落在最终源码上）
- 风险等级: 中（重型验证，注意输出预算）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-107, AC-108]
- vc_refs: [VC-101, VC-102, VC-103, VC-104, VC-105, VC-106, VC-107, VC-108, VC-109, VC-110, VC-111]
- pattern_refs: []

## 背景

父 key 的教训（P-005/P-006/P-007）：证据行必须可被第三方复现、必须落在最终源码上、必须在一个任务内落盘
（不要攒到最后一条消息）。本任务产出的文件是：

`.agenticdoc/mw-rag-integration-fix/evidence/verify-run-2026-09-22.md`

## 必须做

### 1) 落盘协议（防流中断）
- 先用 `write` 落骨架（各节标题 + 结论占位），随后每节一次 `edit` 填充；
- **只允许写这一个文件**（其余只读）；不改源码/测试/文档；不 commit。

### 2) 命令与实测（逐条记录命令 + 结果，截图式粘贴关键行）
1. TS：`test/suite/rag-*.test.ts`（13 个文件，基线 `105 passed | 1 skipped`）+ `test/extensions/agent-team-loop*.test.ts`
   + `test/suite/autopilot-*.test.ts`
2. Python：`python -m pytest -q`（记 passed/deselected/失败项）
3. Python 定向：`test_rag_audit.py test_rag_config.py test_rag_phase.py test_rag_cli.py test_rag_launcher.py test_rag_research.py`
4. golden：`sha256(test/fixtures/rag-block.golden.md)` 与 `test_rag_config.py::...test_golden_block_and_idempotent`
5. `test_autopilot_l0.py` 的 `git diff`（须为零）
6. 仓根 `npm run check`（exit code + 文件数）
7. bundle：**跟踪产物是 `packages/multi-workers/dist/extensions/agent-team-loop.js`**（T-17 已重建，基线 888791 B）。
   记录体积 + `Self-check OK` 输出 + `rg -c 'resolveDefaults' <bundle>`（基线 3）+ **新鲜度**：
   该文件 mtime 必须晚于 `rag/config.ts`、`rag/tools.ts`、`rag/block.ts`、`worker/worker-mode.ts` 的 mtime（产物比源码旧 = 假交付）。
8. 反例试验（**至少三条**，必须做并记录还原 + 每条 sha256 前后一致）：
   - 反例 A（默认值真的有在起作用）：把 fixture 里 `roles.<研究角色>` 的 rewrite 配置反转（或把 `default_server` 换到无
     rewrite 能力的 server）→ `rag-role-defaults`/`rag-parity` 应变红，`[VERIFY] VC-008` 的 `rewrite_tool` 值应随之变化。
   - 反例 B（VC-106 的运行时判定是**真的**consult 了那份文档，而不是「永远不打 marker」）：临时断掉
     `worker/worker-mode.ts` 里把 key 目录交给 `validateResearchDoc`/research-doc 判定的那条路径（例如让它恒返回 null）
     → VC-106 第一个用例（有文档 → 无 marker）**必须变红**（第二个用例仍绿）。这条是把 VC-106 从「可能是弱证据」变成
     「反例可证伪」的关键，必须做；若变不红，说明该用例是装饰，**在报告里如实写明并降级其强度**。
   - 反例 C（跨语言对齐是真的）：把 `mw_common.py` 的 `RAG_RESEARCH_PHASES` 改回空集（只留角色兜底）
     → Python `test_vc111_phase_only_default_parity` **必须变红**，TS 侧不受影响（证明 VC-111 真的钉住了两侧）。
   - 每条记录：改了什么、看到什么（失败用例名/断言）、还原后 `git status --porcelain` 是否干净、sha256 是否复原。

### 3) 逐 VC 表
VC-101~VC-111 每行给：断言原文摘要 | 发射位置 `file:line` | **实测行原文** | 证据强度（强/弱/装饰，口径见复核报告 A 节）
| 若为弱/装饰必须写明原因。缺失的 VC 必须显式列出「未覆盖 + 原因」。
**VC-018/VC-106 层级必须单独判一次**（T-17 选了「优先路径：补运行时用例、维持 L2」）：你要独立判断这对
「有文档 → 无 marker / 无文档 → 有 marker」的用例是否够 L2，写出理由（同源反例、真实 key 布局、运行时路径），
并明确给出「维持 L2」或「应降 L1」。这是上位复核 F-3 的直接呼应，不能含糊。

### 4) 归属与限制
- 列出所有失败项并逐条归属：本 key 缺陷 / 本机环境基线（Windows `packages/agent` 基线、`packages/ai/src/providers/data/` 本地生成目录）/ 其他会话。
- 如实写「未做」：真实 rag-mcp 线上联调、K3 硬门禁、多份调研文档遍历、`rag_chat` 重复计费语义。
- 记录 `rg -n 'MW_RAG_ENABLED'` 的结果时注意口径：**代码与 env 文档路径必须零命中**；
  `packages/multi-workers/CHANGELOG.md` 里有**一处刻意的字面提及**（PM 明确要求：移除项必须能被用户按变量名 grep 到），
  这不是残留读写方，别据此判失败。

## 验收
- 文件存在且包含：§0 复现命令表、§1 VC 汇总表、§2 逐 VC 明细、§3 零回归与改动面、§4 失败归属、§5 反例试验记录、§6 未覆盖与限制。
- 每个 `[VERIFY]` 行都能在文件里找到对应命令与输出。
- 报告长度可控（建议 ≤ 300 行）；结论与表格放前面，证据粘贴在后。
