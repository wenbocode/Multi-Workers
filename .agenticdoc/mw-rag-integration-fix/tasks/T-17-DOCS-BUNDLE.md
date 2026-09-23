# Task T-17: VC-018 证据层级落定 + 文档与实现一致 + 删死变量 + 重建 bundle

## 元信息
- Stage: 3
- 依赖: **T-15 必须先完成**（本任务要重建 `dist/extensions/agent-team-loop.js`，必须在最终 TS 源码上重建）
- 风险等级: 低
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-105, AC-106, AC-107]
- vc_refs: [VC-106, VC-107]
- pattern_refs: []

## 背景

复核 F-3/F-5（含 D-1~D-8）：

- F-3：`evidence-requirement.md` 声明 VC-018 需 **L2** 证据，实际只有对测试自写文档跑纯函数 validator 的 L1 证据。
- F-5/D-1：README `packages/multi-workers/README.md:272-275` 的四个 `mw rag` 子命令都缺必填 `--project`
  （`mw.py:4620-4638` 全部 `required=True`），且 `probe [--server X]` 的 `--server` 在 argparse 里**不存在**。
- D-2：`mw.py:4623` 的 probe help 写「never a non-zero exit」，实际配置错误时 `return 1`（`mw.py:1426-1428`）；
  exit code 口径（list/probe/sync = 1，audit = 0/1/2）未文档化。
- D-3：README 把「开了多轮 → `rag_search_multi_rounds`」与「服务端改写**失败**的降级标记 → `rag-rewrite-degraded`」写成一件事。
- D-4：`launcher.py:351-353` 注入 `MW_RAG_ENABLED` 且注释称 worker 侧扩展据此门控注册；**全仓无读取方**
  （只有 `test_rag_launcher.py:157,171` 断言其存在）→ 死变量 + 不实注释。
- D-7/D-8：README 的映射表未说明为何是 6 行（`RAG_TOOL_MAP` 有 7 条，含 `rag_chat`）；`audit` 未提 `--key`/`--json`。

设计：`design.md` D-106/D-107/D-108、VC-106/VC-107。

## 必须实现

### 1) VC-018 证据层级落定（D-107，二选一，必须落定）

- **优先**：补运行时用例——在 `packages/coding-agent/test/suite/` 用既有 `workerModeActivate` + 假 pi 装置
  （见 `rag-required.test.ts`）驱动一个 key 布局，预置 `rag/<server>-<slug>.md`，断言 `validateResearchDoc`
  在真实 key 路径下取到该文档并判 ok（`[VERIFY] VC-106: runtime_doc_found=true sections=6 verdict=ok`）。
- **退路**：把 VC-018 的层级声明从 L2 改为 L1，并同步 `design.md` 的层级标注。**层级声明在哪**：上位 key 的文件
  `.agenticdoc/mw-rag-integration/evidence-requirement.md:26`（现为 `| AC-014 | VC-018 | VC-018 需 L2 证据 |`）。
  该文件属已 DONE 的 key → **不要重写它的历史**，只在该行末尾追加修订标记
  （形如 `[REVISED @ 2026-09-22 → L1, superseded by mw-rag-integration-fix T-17]`）；本 key 自己的
  `evidence-requirement.md` 由质检阶段生成，其 VC-018 层级必须与本次落定结果一致（选退路就写 L1）
  （`[REVISED @ 2026-09-22]` 注明原因：无真实 rag-research 产出文档的运行时证据）。选了退路就在报告里写明。
- 无论选哪条，`evidence/verify-run-*.md`（T-18 生成）与 `design.md`/`evidence-requirement.md` 的层级声明必须一致；
  **在报告里明确写「选了哪条 + 依据」**，不要让 T-18/T-19 去猜。

### 2) README 用法段以 argparse 为唯一真源（D-108）

- 四条命令全部带 `--project <dir>`；`rag probe` 删掉 `--server X`；补上 `--json`（list/probe/audit）、
  `--key <KEY>`、`--out FILE`（audit）。
- 新增退出码小表：`list`/`probe`/`sync` 成功 0、配置错误 1；`audit` 0=无 missing、1=有 missing、2=用法/配置错误
  （以 `mw.py:1957-1977` 的实现为准，**先读代码再写**）。
- 修 `mw.py:4623` 的 probe help 文案，使其与行为一致（保留「配置错误返回 1」的行为）。
- 澄清 `rag-rewrite-degraded`：只在服务端返回 `meta.rewrite_degraded === true`（改写**失败**的降级）时追加，
  与「开了多轮改写」方向相反（对照 `rag/adapter.ts` 的 meta 白名单 + `rag/tools.ts:553`）。
- 映射表补一句：表中 6 行是**六个基工具**的映射，`rag_chat` 只在 `rag-research` 任务注册（`RAG_TOOL_MAP` 里还有一条）。

### 3) 删除死变量 `MW_RAG_ENABLED`（D-106）

- `launcher.py`：删掉 `env["MW_RAG_ENABLED"] = ...` 与其不实注释（保留 enabled 集合的其他用途，勿误删回填逻辑）。
- `test_rag_launcher.py`：删掉两处对它的断言（`:157`、`:171` 附近），其余断言保持。
- `docs/environment-variables.md`：**不登记**该变量（若已登记则删）。
- 证明删除是无害的：在报告里给出 `rg -n 'MW_RAG_ENABLED'` 的**删除后**结果（应为零命中，或仅历史 CHANGELOG 提及）。

### 4) CHANGELOG 与 dist 重建（AC-107）

- 两包 `CHANGELOG.md` 的 `[Unreleased]` 下追加本轮修复条目（`### Fixed` 或 `### Changed`），只追加不新建同名小节。
- 重建跟踪文件：`bash packages/multi-workers/build-extension.sh`（期望形如 `<N> kb` + `Self-check OK`），
  并在报告里给出体积与自检输出。
- **必须验证新代码真的进了 bundle**（不要只看 `Self-check OK`）：跟踪的产物是
  `packages/multi-workers/dist/extensions/agent-team-loop.js`（当前 `git status` 显示 ` M`，属本 key 链路）。
  重建后 `rg -c 'resolveDefaults' packages/multi-workers/dist/extensions/agent-team-loop.js` 必须 >= 1
  （`resolveDefaults` 只在 T-15/T-19 的源码里出现）；为 0 说明 bundle 不是从当前源码构建的，**停下上报**。
  另注意：`packages/coding-agent/dist/extensions/agent-team-loop/` 下**没有** `rag/` 子目录，说明 pi 实际加载的是
  multi-workers 那份 bundle；若两者语义不一致，在报告里写明。

## 验收

1. `cd packages/multi-workers && python -m pytest test_rag_launcher.py test_rag_cli.py -q` 全绿。
2. 四条 README 命令按文档逐条可执行：`python mw.py rag list --project <repo>`、`probe --project <repo>`、
   `audit --project <repo> --json`、`sync --project <repo>`（sync 会写 `<repo>/.pi/skills/mw-rag.md`；
   若不想留痕，用临时 control 目录做，并在报告里说明用了哪个目录）。
3. `rg -n 'MW_RAG_ENABLED' packages/ docs/` 零命中。
4. `git status --porcelain` 显示 `dist/extensions/agent-team-loop.js` 已更新（本任务允许），且 fixtures/golden 无改动。
5. 仓根 `npm run check` exit 0。
6. bundle 内含新代码：`rg -c 'resolveDefaults' packages/multi-workers/dist/extensions/agent-team-loop.js` >= 1。

## 禁止

- 不改 `rag/tools.ts` / `rag/adapter.ts` / `rag/config.ts` / `rag/block.ts`（归 T-15/T-19）；不改 `mw.py:1869` 与 `mw_common.py:903`
  的 role 回落（归 T-16）；不改文本层守护测试；不重生成 golden；不 commit。
- 不做真实 rag-mcp 线上联调（仍属发布前 smoke）。
