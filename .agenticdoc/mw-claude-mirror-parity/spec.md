# Spec: 分发包镜像门禁一致性（mw-claude-mirror-parity）

- Key: `mw-claude-mirror-parity`｜阶段: SPEC｜日期: 2026-10-12｜基线 commit: `6c5189831`
- 上游遗留：`mw-guard-form-hardening`（DONE）遗留 **C-9**（用户裁定走 **(b) 后续 key**：提交/推送框架改动 → 重同步镜像 → 重装 `.claude` → 加镜像一致性检查）
- 本文状态：**初稿**（spec 阶段 RQ 回收后由 PM 修订；AC 编号一经锁定不回收）

## §0 Goal Alignment

**goal.md 锚点**：本框架「不修改 pi 核心：所有功能通过 Extension API 实现」，而其**协调语义与门禁语义由随框架分发的脚本承载**
（`.agents/skills/agentic-task/scripts/*.py`：`update_index.py`、`advance_phase.py` 等）。这些脚本会被 `install.py` / `sync_framework.py`
**复制到用户项目的 `.claude/scripts/`**，并由 pi 侧的活链消费（`pm/ui-bridge.ts:2345 → agentic-scripts.ts:21-30 → advance_phase.py:599/602`）。

**本 key 与 goal 的对齐点**：
- 「文件驱动协调 + 文件锁」⇒ 键名/保留名的门禁（`keyNameRefusal`、`caseVariantOf`）必须**在所有被分发的副本里同样存在**；
  只修权威副本会让**每个下游项目的 `.claude` 副本继续 fail-open** —— 门禁形同虚设，且用户无法感知。
- 「不修改 pi 核心 + 扩展机制」⇒ 修复必须走**官方分发路径**（`install.py` / `sync_framework.py`），不得手改副本（手改会在下次同步被覆盖，且不可审计）。
- 「goal.md 作为项目级目标锚点 / 每次 gate 都要有可判定证据」⇒ 副本与权威的差异必须**可机器判定**（逐文件 hash + 语义/符号级差分 + 语料级等价判定），
  而不是靠人眼比对。

**预期收益（可量化，作为 done 时的判据）**：
1. 全量镜像差异清单**无遗漏**：发现的副本数 == 逐条比对的副本数（AC-001）。
2. 有一个**fail-closed 的一致性检查**：篡改任一副本 ⇒ 期望变红；一致 ⇒ 绿（AC-002）。
3. 重同步走官方路径，同步后副本含门禁符号（`caseVariantOf`/`keyNameRefusal` 等），且**判定等价**（同一语料两侧结果逐条相等）（AC-003/AC-004）。
4. 影响评估可读：每个副本的消费者与活链坐标可解析（AC-005）。
5. 本 key 不写其他 key 的任何文件（AC-006）。

## §1 问题陈述

### §1.1 已知缺口（来自上一 key 的 C-9 与 T-13/T-15/T-16 的实测）

| # | 缺口 | 性质 | 已知坐标 |
|---|---|---|---|
| E1 | `.claude/scripts/update_index.py`（22,026 B）**无门禁**，但位于活链上：`pm/ui-bridge.ts:2345` → `pm/agentic-scripts.ts:21-30` → `advance_phase.py`（set-phase 处 `:599`/`:602`） | 漏放（fail-open） | `.claude/scripts/update_index.py`；活链见 `mw-guard-form-hardening/design.md` C-9 行 |
| E2 | `install.py` 的 `sync_script_mirrors()` 会把该副本**分发到每个用户项目**⇒ 缺口随分发放大 | 影响面放大 | `.agents/skills/agentic-task/install.py:41`（`sync_script_mirrors`）、`:71`（`install_claude`） |
| E3 | 副本数量与分布未清点（上一 key 只点出「6 份副本 gate=0」，未逐条给出路径/差异/消费者） | 证据缺口 | 需本 key 的 RQ-1 补齐 |
| E4 | 没有「副本 vs 权威」的一致性检查 ⇒ 漂移不可见（上一 key 是**事后**才发现） | 可观测性缺口 | 需本 key 的 RQ-2/AC-002 |

### §1.2 待研究问题（RQs，spec 阶段并行取证；每条只写唯一证据文件）

| RQ | 问题 | 证据文件（唯一） |
|---|---|---|
| RQ-1 | 全量清点：仓内所有权威脚本与其分发副本（路径、字节、hash、`def`/符号清单、门禁相关符号的有无），并给每个副本的消费者与活链坐标 | `evidence/research/spec-mirror-inventory-20261012.md` |
| RQ-2 | 权威与副本在**语义层**的差异：用既有 golden 语料（`test_update_index_key_refusal.py` 的 66 行表 + `caseVariantOf` 用例）在两侧逐条比对，给出「等价/分歧」清单与分歧成因 | `evidence/research/spec-mirror-semantics-20261012.md` |
| RQ-3 | 官方分发路径的行为：`install.py`/`sync_framework.py` 的复制时机、覆盖规则、幂等性、是否会保留用户改动；给出「重同步」的**唯一**正确命令与预期产物清单 | `evidence/research/spec-distribution-path-20261012.md` |

**根因（一句话）**：门禁被实现在**权威副本**里，而运行时链路上跑的是**分发副本**；分发是复制而非引用，且没有一致性检查
⇒ 权威修了、副本继续 fail-open，且漂移不可见。

## §2 范围

**In**：
- 镜像清单与差异（权威 `.agents/skills/agentic-task/scripts/**` ↔ 仓内各副本，含 `.claude/scripts/**`）。
- 一致性检查（测试/校验器）：fail-closed，且能证明「篡改即红」。
- 走官方路径的重同步（`install.py` / `sync_framework.py`），同步后副本含门禁符号。
- 逐条判定等价性验证（golden 语料两侧比对）。
- 影响评估文档（消费者 + 活链 + 后果）。

**Out（非范围）**：
- 重开 `mw-guard-form-hardening` 已关闭的守卫形态问题（C-1…C-8、C-10…C-26 除 C-9 外）。
- 框架脚本的**新功能**（本 key 只做「门禁一致性 + 分发正确性」，不新增门禁种类）。
- P2（OS 级隔离）。
- 其他 key 的任何文件。

## §3 验收标准（AC）

> 证据口径：所有数值机器可读；每条结论带**可解析路径**；引用一律写完整路径（避免上一 key 的 §9.4 锚点事故）。

### AC-001 全量镜像清单无遗漏
产出「权威 ↔ 副本」逐文件清单（路径、字节、sha256、符号清单、门禁符号有无）。
- 判据：清单里的副本数 == RQ-1 独立枚举出的副本数；**每个副本都有一行消费者/活链坐标**；清单本身以机器可读形式落盘（`evidence/runs/`）。

### AC-002 一致性检查存在且 fail-closed
新增检查（测试或校验器）：权威与副本不一致时**失败**。
- 判据：① 一致 ⇒ 绿（给出计数）；② **篡改任一副本（等长替换，避免仅靠长度判定）⇒ 红**，且失败信息指名文件与差异；③ 恢复后 ⇒ 绿。

### AC-003 重同步走官方路径且产物含门禁
- 判据：① 使用的命令是 `install.py` / `sync_framework.py` 的既有入口（报告给出完整命令与原始输出）；② 同步后副本内 `caseVariantOf`、`keyNameRefusal` 等门禁符号**存在**（逐副本给出命中证据）；③ 未手改任何副本（`git diff` 证明改动来自脚本）。

### AC-004 判定等价性（逐条）
用既有 golden 语料在权威与副本上各跑一次，逐条比对判定。
- 判据：`rows_total == rows_equal`（给出两侧计数值），分歧为 0；若存在**不可消除**的分歧（例如副本必须保留历史行为），必须逐条登记并给出理由。

### AC-005 影响评估可读
- 判据：报告含「副本 → 消费者 → 活链坐标 → 漂移后果 → 处置」表，每条坐标可解析（锚点门禁式校验思路复用），且明确列出**不在本 key 修复**的分发点。

### AC-006 隔离
- 判据：`git status` 证明本 key 只改自身证据/文档与 AC-003 允许的同步产物；未写任何其他 key 的路径；对其他 key 只读。

## §7 可复用资产

- `packages/multi-workers/test_update_index_key_refusal.py`（66 行 golden 表 + `caseVariantOf` 用例）——AC-004 的直接语料。
- `mw-guard-form-hardening` 的 C-9 定位证据（`design.md` §4.6、`evidence/runs/qgb2-pm-sync-20261012.md`）。
- 上一 key 的锚点门禁经验（引用写完整路径、编辑后复跑门禁）。
- `install.py:41 sync_script_mirrors` / `:71 install_claude` 既有实现（复用其复制语义，不重写）。

## §8 需规避坑点

- **P-01**：副本可能有**历史差异**（不同 key 时代同步的版本）⇒ 不能假设「副本 = 权威的旧版」，必须逐条给出差异来源。
- **P-02**：`sync_framework.py` / `install.py` 可能带**用户项目路径**参数 ⇒ 在仓库内跑同步要避免写进用户目录（先 `--dry-run`/先读实现）。
- **P-03**：一致性检查若只比字节 hash，会在**格式差异（CRLF/BOM）**上误报 ⇒ 需给出「语义一致但字节不同」的分档，并明确哪一档算失败。
- **P-04**：`.claude/scripts` 可能在 `.gitignore` 内 ⇒ 「同步后产物」可能不进版本控制，需说明交付形态。
- **P-05**：不得手改副本（会被下次同步覆盖，且产生不可审计的差异）。
- **P-06**：不要顺手修 C-9 之外的既有残余（避免范围蔓延）。
