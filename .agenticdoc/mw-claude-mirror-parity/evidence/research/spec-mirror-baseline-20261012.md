# SPEC 阶段研究基线（mw-claude-mirror-parity）

- key：`mw-claude-mirror-parity`｜阶段：SPEC｜日期：2026-10-12
- 状态：**PM 基线声明**（本文件先于 3 个 RQ 落盘，用于满足派发门禁「research note 存在」；RQ 回收后本文件不替代 RQ 证据）

## 1. 已确认基线（来自上一 key 的实测，非本 key 重做）

| 事实 | 数值/坐标 | 来源（对上一 key 只读） |
|---|---|---|
| 活跃的分发副本缺口 | `.claude/scripts/update_index.py`（22,026 B）无门禁 | `.agenticdoc/mw-guard-form-hardening/design.md` §4.6 C-9 行 |
| 活链 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2345` → `packages/coding-agent/src/extensions/agent-team-loop/pm/agentic-scripts.ts:21-30` → `advance_phase.py`（set-phase 附近 `:599`/`:602`） | 上一 key T-13 报告 |
| 分发点 | `.agents/skills/agentic-task/install.py` 的 `sync_script_mirrors`（`install.py:41`）与 `install_claude`（`install.py:71`） | 上一 key D-047 撤回记录（引用有效） |
| 上一 key 的副本计数 | 「6 份副本 gate=0」（未逐条给出路径/差异/消费者） | 上一 key QG-B3 残余账本 |

## 2. 本 key 的待取证清单（由 3 个 RQ 覆盖，互不重叠）

| RQ | 问题 | 唯一证据文件 |
|---|---|---|
| RQ-1 | 全量清点：权威/副本/门禁符号/消费者与活链/分发点 | `evidence/research/spec-mirror-inventory-20261012.md` |
| RQ-2 | 语义等价：golden 语料两侧逐条比对 + 分歧成因 + 格式分档 + 「只装副本是否 fail-open」实测 | `evidence/research/spec-mirror-semantics-20261012.md` |
| RQ-3 | 分发路径行为：触发点/映射/覆盖规则/幂等/参数/唯一正确命令/gitignore | `evidence/research/spec-distribution-path-20261012.md` |

## 3. 不可复用的前提（必须在 RQ 中实测推翻或确认）

- **不得假设**副本 = 权威的旧版本（可能是历史分叉）⇒ RQ-2 必须逐条给差异成因。
- **不得假设** `.claude/scripts` 被版本控制跟踪 ⇒ RQ-3 必须给 `git check-ignore` 原始输出。
- **不得假设**在仓库内跑 `install.py` 是幂等且只写仓库内 ⇒ RQ-3 必须给覆盖规则与参数分析。
