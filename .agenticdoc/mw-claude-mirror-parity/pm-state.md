# PM State: 分发包镜像门禁一致性（mw-claude-mirror-parity）

- Phase: SPEC
- Key: mw-claude-mirror-parity
- Claim-Id: WENBOZHOU-PC4:117296
- Created: 2026-10-12
- Updated: 2026-10-12 15:45
- Baseline commit: 6c5189831（本 key 立项时的 HEAD）
- 上游：mw-guard-form-hardening（DONE）遗留 C-9；用户裁定走 (b) 后续 key

## 1. 立项依据

- `mw-guard-form-hardening` 的 C-9：`.claude/scripts/update_index.py`（22,026 B）**无门禁**且位于活链
  （`pm/ui-bridge.ts:2345 → pm/agentic-scripts.ts:21-30 → advance_phase.py:599/602`），并被
  `.agents/skills/agentic-task/install.py`（`sync_script_mirrors`@41、`install_claude`@71）分发给每个用户项目。
- 用户裁定：(b) 提交/推送框架改动 → 重同步镜像 → 重装 `.claude` → **加镜像一致性检查**。

## 2. 用户约束（绑定）

1. **隔离**：本 key 的执行不得影响历史 worker；不写其他 key 的任何文件（只读可见）。
2. **影响评估**：必须给出「副本 → 消费者 → 活链 → 漂移后果 → 处置」。
3. **worker 产物自带状态**：worker 报告须含实测命令与原始输出。
4. PM 可读其他 key，但**不写、不重派**。

## 3. 阶段计划

- SPEC（当前）：3 个 RQ 并行取证（RQ-1 清单 / RQ-2 语义差 / RQ-3 分发路径）→ PM 归纳 → spec 定稿。
- DESIGN：DRQ 并行（判定等价性的检查设计、字节 vs 语义分档）→ design.md（含 mermaid + VC 命名空间 `VC-MWP-0NN`）。
- PLAN/TASKS：卡片化（每卡一片写入面）。
- EXECUTE：按卡派发；重同步走官方路径。
- VERIFY：两轮 QG（对抗 + 证据链），新 task_key。

## 4. 决策记录

### D-001（2026-10-12 15:45）立项与范围

- key 名：`mw-claude-mirror-parity`（镜像 = 分发包副本；parity = 门禁/判定等价）。
- 范围：**只做**「全量清单 + 一致性检查（fail-closed）+ 官方路径重同步 + 判定等价 + 影响评估」。
  **不做**：重开上一 key 的守卫形态问题、新增门禁种类、OS 级隔离。
- 复用资产：`packages/multi-workers/test_update_index_key_refusal.py` 的 66 行 golden 表（AC-004 语料）。
- 规避坑点 P-01…P-06 见 `spec.md` §8（含「不得手改副本」「副本可能有历史差异」「.claude 可能被 gitignore」）。
- 待规避：上一 key 的锚点事故 ⇒ 本文档与后续相位文档的引用一律写**完整可解析路径**，编辑后复跑锚点门禁。

## 5. 下一动作

- 派发 3 个 SPEC 阶段 RQ（`type: research`，并行，各自只写唯一证据文件）；
- 回收后由 PM 归纳进 `spec.md` §1.2 并定稿，再 `advance(spec→design)`。

### D-002（2026-10-12 16:10）**PAUSED**：范围移出本 key，用户裁定另立新 key

- 用户指出：本 key 立错方向。用户要的是 **dispatch 任务卡缺失/无格式/无检查** 这条洞（即本会话记录的事件
  `.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md`），不是 `.claude` 分发副本门禁（C-9）。
- 用户裁定（二选一中的 (b)）：**另立新 key** `mw-dispatch-card-gate`；本 key **封存为 PAUSED**。
- 本 key 状态：`- Phase:` 保持 SPEC（不宣告 done：C-9 洞未修，风险照旧——每个下游项目继续 fail-open）。
- 资产保留（将来重开直接接上）：
  - `evidence/research/spec-mirror-inventory-20261012.md`（79,143 B）：16 权威 + 6 副本目录/96 .py、符号矩阵 1056 次 rg、活链实测（pi 侧跑副本）。
  - `evidence/research/spec-mirror-semantics-20261012.md`：golden 66 行两侧对照（权威 66/66、副本 11/66、`rows_diff=55`）、成因=历史落后（删块重建逐字节相同）、fail-open 实测（3 条越面 CLI rc=0）。
  - `evidence/research/spec-distribution-path-20261012.md`（27,362 B）：唯一正确命令 `python .agents/skills/agentic-task/install.py . --skip-codex`、幂等沙箱实测、`sync_framework.py` 会 push 故排除、`.claude`/`.agents` 被 gitignore、`diff-installed.py` 基准盲区。
  - `evidence/research/spec-mirror-baseline-20261012.md`：PM 基线声明。
- 未修残余（留给重开）：C-9（副本门禁）、`mw update-env` 以 mirror 为基准（`packages/multi-workers/mw.py:5161-5184`）、`diff-installed.py:73-78` 不比 `repo/scripts`、写面守卫把 here-string 内含 `->` 当重定向（假阳性）。
