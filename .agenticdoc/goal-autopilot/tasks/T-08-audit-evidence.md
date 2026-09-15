# Task T-08: audit_evidence.py（L1 证据审计）

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-t08-audit
- ac_refs: [AC-007]
- vc_refs: [VC-009]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/audit_evidence.py`（L1 审计层）。

- CLI：`python autopilot/audit_evidence.py --key <key> [--project <dir>]` → stdout JSON dossier
- dossier schema：`{key, phase_edge, ac_list[], decision_map[{decision, evidence_files[]}], gaps[{item, rule, severity}], generated_at}`
- 输入：`{key}/spec.md`（AC 清单提取）+ `{key}/evidence/` 目录（research 留底等）+ `{key}/design.md`（决策点清单，供 decision_map 键集）
- 判定规则：
  - AC 清单 ← spec §3 表格行提取
  - decision_map ← design 决策点（D-xxx）→ evidence/ 下引用该决策或被决策引用的文件
  - gaps ← 缺 research 留底、决策无证据映射等，每项含 rule 与 severity（blocking/non-blocking）
- exit 码：证据齐全 → 0；有缺口 → 1
- 独立 CLI（不依赖 conductor 运行；conductor 在 phase 边界调用）

## 输入
- 依赖文件: 目标 key 的 spec.md / design.md / evidence/
- 依赖 Task: T-02（包结构）
- AC 约束:
  > AC-007: 在给定 `{key}/spec.md` 与 `evidence/` 目录的条件下，L1 审计脚本输出 JSON dossier，含 AC 清单、决策点→证据文件映射、缺口列表三部分；对证据齐全样例 exit 0，对缺失 research 留底样例 exit 1 且缺口列表非空
- 设计约束:
  > D-102: L1 = 机械审计，不做语义判断（语义判断归 L2 verifier）
  > VC-009: 齐全样例 exit 0 且 JSON 含 ac_list/decision_map/gaps 三键；缺失样例 exit 1 且 gaps 非空

## 预期产出
- `packages/multi-workers/autopilot/audit_evidence.py`
- `packages/multi-workers/test_autopilot_audit.py`（fixture：齐全样例 + 缺失样例 key 目录）：
  - 齐全样例 exit 0 + 三键存在（VC-009）
  - 缺 research 留底样例 exit 1 + gaps 非空（VC-009）
  - spec AC 提取正确（含 errata 格式的锁定 spec）
  - decision_map 键集 = design 决策点集
- 验证方式: `[VERIFY] VC-009: audit_complete=0 audit_missing=1 gaps_nonempty=true`
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 11:55 | T-08 实现与验证（worker-t08-audit） | `autopilot/audit_evidence.py` + `test_autopilot_audit.py` 落盘；`python -m pytest test_autopilot_audit.py -v` → 7 passed（齐全样例 exit 0 三键 / 缺失样例 exit 1 gaps 非空 / 锁定 errata AC 提取 / decision_map 键集=design 决策集 / phase_edge null / spec-missing / 真实 key 指纹）；[VERIFY] VC-009: audit_complete=0 / audit_missing=1 gaps_nonempty=true / ac_extract=correct / decision_map_parity=true；真实 key goal-autopilot 跑批 exit 1（D-113/D-115 决策无证据映射，non-blocking，正常缺口输入，dossier 见下）。备注：`npm run check` 的 tsgo --noEmit 在 packages/ai 报存量错误（git status 无 packages/ai 改动，非本任务 Python-only 改动引入；biome/pinned-deps/ts-imports/shrinkwrap/install-lock 全过） |
| 2 | 2026-09-10 13:10 | PM 验收：亲跑 7 passed + [VERIFY] ×4 复核；代码走查（AC 表行提取排除 blockquote errata/围栏代码块跳过/双向映射/占位符模板引用跳过/phase 边界 gated 规则镜像 advance_phase GATES/utf-8-sig 容错不崩溃均合规）；真实 key dossier 实战验证：25 AC 全提取 + D-101~116 全映射 + D-113/115 non-blocking 缺口 exit 1，语义正确 | 验收通过 |

#### 真实 key 跑批 dossier（2026-09-10T03:55:34Z，exit 1）

命令：`python autopilot/audit_evidence.py --project H:/git/Multi-Workers --key goal-autopilot`

```json
{
  "key": "goal-autopilot",
  "phase_edge": "EXECUTE",
  "ac_list": [
    "AC-001",
    "AC-002",
    "AC-003",
    "AC-004",
    "AC-005",
    "AC-006",
    "AC-007",
    "AC-008",
    "AC-009",
    "AC-010",
    "AC-011",
    "AC-012",
    "AC-013",
    "AC-014",
    "AC-015",
    "AC-016",
    "AC-017",
    "AC-018",
    "AC-019",
    "AC-020",
    "AC-021",
    "AC-022",
    "AC-023",
    "AC-024",
    "AC-025"
  ],
  "decision_map": [
    {
      "decision": "D-101",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-102",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-103",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-104",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-105",
      "evidence_files": [
        "evidence/research/design-gate-l2-worker-protocol-2026-09-08.md"
      ]
    },
    {
      "decision": "D-106",
      "evidence_files": [
        "evidence/research/design-gate-l2-worker-protocol-2026-09-08.md"
      ]
    },
    {
      "decision": "D-107",
      "evidence_files": [
        "evidence/research/design-gate-l2-worker-protocol-2026-09-08.md"
      ]
    },
    {
      "decision": "D-108",
      "evidence_files": [
        "evidence/research/design-gate-l2-worker-protocol-2026-09-08.md"
      ]
    },
    {
      "decision": "D-109",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-110",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-111",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-112",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-113",
      "evidence_files": []
    },
    {
      "decision": "D-114",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    },
    {
      "decision": "D-115",
      "evidence_files": []
    },
    {
      "decision": "D-116",
      "evidence_files": [
        "evidence/research/design-conductor-mounting-and-state-2026-09-08.md"
      ]
    }
  ],
  "gaps": [
    {
      "item": "D-113",
      "rule": "decision-without-evidence",
      "severity": "non-blocking"
    },
    {
      "item": "D-115",
      "rule": "decision-without-evidence",
      "severity": "non-blocking"
    }
  ],
  "generated_at": "2026-09-10T03:55:34Z"
}
```

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
