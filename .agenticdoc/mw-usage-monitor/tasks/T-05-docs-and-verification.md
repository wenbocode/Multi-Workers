# T-05: 文档与收口验证（CHANGELOG + README + 端到端）

type: coding
phase: execute
key: mw-usage-monitor
覆盖 AC: AC-009, AC-010
依据: `.agenticdoc/mw-usage-monitor/plan.md`（里程碑判据 M4）、`design.md` §9；`spec.md` §3/§4

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（框架可观测性面；文档是操作面的一部分）。
- 已核实起点（自行复核）：
  - `packages/multi-workers/CHANGELOG.md` 的 `## [Unreleased]` 段（新条目一律追加到此，读全文后按小节归位，
    不重复创建小节；已发布版本段落不可改）。
  - `packages/multi-workers/README.md` 的 CLI 命令段落（`mw doctor` / `mw rag` / `mw model` 均在其中有条目，
    照同形态加 `mw stats`）。
  - 验证基线：Windows 上 `packages/agent` / `packages/coding-agent` 有已知环境失败基线（见 AGENTS.md）；
    `packages/multi-workers` 全量 pytest 的 8 个已知红/环境用例见 `_scratch/quality-gate-drift-guard-20260902.md`
    与 `mw-autopilot-gate-alarm-liveness/evidence/quality-gate-report-20261013.md:143`——**本次不得新增红灯**。
- 依赖：T-01、T-02、T-03、T-04 全部合并到工作树。

## 要求

1. `packages/multi-workers/CHANGELOG.md`：`## [Unreleased]` 的 `### Added` 增一条，说明
   `mw stats` + `~/.mw/usage/runs.jsonl` 台账 + `/mw stats`，以及「pi/PM/claude 精确统计、codex 显式未统计」
   的范围边界；不写金额相关表述。
2. `packages/multi-workers/README.md`：在 CLI 命令段落加 `mw stats` 小节：用途、默认窗口、过滤参数表、
   台账位置（含 `MW_USAGE_DIR` 覆盖）、输出样例（与 `format_report_text` 实际形态一致，**必须含 `wall_kind` 的
   `*` 脚注示例**）、隐私声明（只读 usage/model/timestamp，不读正文）。
3. `spec.md`（本 key，`.agenticdoc/mw-usage-monitor/spec.md`）：§3 台账/报告字段描述补上
   `wall_kind=run|session|none` 与「绝不混源」（worker 墙钟 vs PM 会话跨度）一句；不得改 §4 AC 编号。
4. 全量验证并**记录实测数值**：
   ```powershell
   cd H:\git\Multi-Workers\packages\multi-workers
   python -m pytest -q            # 记录 passed/failed，与 8 个已知红对照
   cd H:\git\Multi-Workers
   npm run check                  # 记录 errors/warnings/infos
   ```
   **已知基线（不要“修”它）**：`npm run check` 的 biome 步骤当前 rc=1，告警在
   `packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts`（另一会话未提交改动）与
   `mwoc-w2-contract-judgment.test.ts` / `mwoc-w3-ledger-extractor.test.ts`（此二者 `git status` 干净 =
   已提交基线）。只需在 `output.md` 记录：本次改动文件单独 `npx biome check` 为零告警，链的其余步骤
   （`check:pinned-deps`/`check:ts-imports`/shrinkwrap/install-lock/browser-smoke/`npx tsgo --noEmit`）全 rc=0。
5. 端到端（需用户同意重启 serve 后执行）：`/mw restart` → 派一张最小任务 → 确认台账 start/end 两行 +
   `session_id` 形如 `mw-<key>-<pid>-<seq>` → `mw stats --since 1d` 的该 run tokens 与手工扫会话一致。
   若用户尚未同意重启，把此步留为「待用户执行」并在 `output.md` 明写未验证。
6. 不得改动代码逻辑（只允许文档 + `spec.md`）；发现代码问题时在 `output.md` 记录并交回 PM，不自行修。

## 写入允许面

- `packages/multi-workers/CHANGELOG.md`
- `packages/multi-workers/README.md`
- `.agenticdoc/mw-usage-monitor/spec.md`（仅 §3 字段描述补一句 `wall_kind`）

## 写入禁止面

- 任何代码文件（`usage.py`/`launcher.py`/`mw.py`/TS）
- 已发布版本的 CHANGELOG 段落、其它 key 目录、`.mw/**`

## 验收命令

```powershell
cd H:\git\Multi-Workers
npm run check
cd packages\multi-workers
python -m pytest -q
```

## 改动历史

（首次改动，填写：CHANGELOG 追加位置、README 小节位置、验证实测数值。）
