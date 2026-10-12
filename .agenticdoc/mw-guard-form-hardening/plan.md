# Plan: 守卫形态加固（mw-guard-form-hardening）

- key: `mw-guard-form-hardening`｜阶段: PLAN｜上游: `spec.md`（11 AC, 23,355 B）+ `design.md`（21,719 B, VC-001…VC-046）
- 基线 commit: `ab546bb64`｜写面冻结: 每波内文件两两不相交；同一文件同一时刻仅一张卡
- 证据: `evidence/research/` 10 份（spec 阶段 5 + design 阶段 3 + 前置 2）

## §1 ac_count 与覆盖

| 项 | 值 |
|---|---|
| ac_count | 11 |
| 卡片数 | 13（S1 3 / S2 2 / S3 4 / S4 2 / S5 2）+ QG 2 |
| VC 数 | 46 |
| 回归面 | `mwds-t01…t03`、`worker-crosskey-readonly`、`worker-dispatch-guard`、`autopilot-protocol`、Python `test_autopilot_config_parity` 范式一致性测试 |

## §2 波次与串行链

```mermaid
flowchart LR
    W1["波1 T-01 T-04 T-06"] --> W2["波2 T-02 T-05 T-08"]
    W2 --> W3["波3 T-07 T-09"]
    W3 --> W4["波4 T-03 T-11"]
    W4 --> W5["波5 T-10 T-12"]
    W5 --> W6["波6 T-13 收口"]
    W6 --> QG["QG 对抗 + 证据链"]
```

| 波 | 卡 | 链（文件） | 依赖 |
|---|---|---|---|
| 1 | T-01 形态补全 / T-04 形状判定 / T-06 新模块 | S1 `worker-mode.ts`｜S2 `ui-bridge.ts`｜S3 新增 `shared/task-frontmatter.ts` | — |
| 2 | T-02 `verbatim` / T-05 fixture 与语料回归 / T-08 golden + Python 一致性 | S1 `worker-mode.ts`｜S2 测试面｜S3 `mw_common.py` | T-01 / T-04 / T-06 |
| 3 | T-07 TS 三解析器切换 / T-09 key 身份 | S3 `worker-mode.ts`+`task-dispatcher`+`status-model`｜S3 `index-store`+`ui-bridge` | T-06 / T-04 |
| 4 | T-03 审计行与告警 / T-11 空洞断言 / T-14 Python 调用点接线 | S1 `worker-mode.ts`+`pm-orchestrator`｜S4 测试面 | T-02 / T-05 |
| 5 | T-10 14 条分支 / T-12 契约与文档 | S4 测试面｜S5 文档+`worker-mode.ts` 注释 | T-03 / T-09 |
| 6 | T-13 证据锚定与收口 | S5 文档 | 全部 |

## §3 卡片总表

| 卡 | 标题 | AC | VC | 波 | 唯一写入面（源码/测试） |
|---|---|---|---|---|---|
| T-01 | 写面形态补全（A–F 组 + FP 消除） | AC-002 | VC-006…010 | 1 | `worker-mode.ts`；`test/suite/mwds-t03-bash-write-scope.test.ts` |
| T-02 | `verbatim` 判定与 deny 域收敛 | AC-001 | VC-001…005 | 2 | `worker-mode.ts`；`mwds-t03-*` |
| T-03 | 审计行 + `[WRITE_SCOPE_SUMMARY]` + PM 告警 | AC-007 | VC-029…031 | 4 | `worker-mode.ts`；`pm/pm-orchestrator.ts`；`mwds-t03-*` |
| T-04 | 目标集轴 `judgeWriteTarget`（形状判定） | AC-003/004 | VC-011…019 | 1 | `ui-bridge.ts`；`test/suite/mwds-t02-write-intent.test.ts` |
| T-05 | fixture 语义修正 + 跨目录负例 + 语料回归 | AC-003/004 | VC-014…018, VC-046 | 2 | `mwds-t02-write-intent.test.ts` |
| T-06 | 新模块 `shared/task-frontmatter.ts` | AC-005 | VC-039 | 1 | 新增 `shared/task-frontmatter.ts`；新增 `test/suite/task-frontmatter.test.ts` |
| T-07 | TS 三解析器切换（首 `type:` 胜出） | AC-005 | VC-020…023 | 3 | `worker-mode.ts`；`task-dispatcher.ts`；`autopilot/status-model.ts`；`test/extensions/agent-team-loop.test.ts` |
| T-08 | golden fixture + Python 同语义一致性 | AC-005 | VC-040, VC-042 | 2 | `packages/multi-workers/mw_common.py`；新增 `test/fixtures/task-md-header-cases.json`；新增 Python 一致性测试；`test/suite/mwds-t03-*`（BOM 用例） |
| T-09 | key 豁免 14 名 + 读侧归一 + 回退 + 守卫无条件 | AC-006 | VC-024…028, VC-043, VC-044 | 3 | `shared/index-store.ts`；`ui-bridge.ts`；`mwds-t01-*`/`worker-crosskey-readonly.test.ts` |
| T-10 | 14 条未覆盖分支测试 | AC-008 | VC-032…034 | 5 | `mwds-t03-*`；`worker-crosskey-readonly.test.ts`；`worker-dispatch-guard.test.ts` |
| T-11 | 空洞断言替换 | AC-009 | VC-035 | 4 | `test/suite/`（交付判据与占位符相关用例） |
| T-12 | 契约与文档处置（占位符 16 / 标记消费端） | AC-010 | VC-036/037 | 5 | `shared/deliverable-evidence.ts`（注释）；`worker-mode.ts`（注释）；`packages/coding-agent/CHANGELOG.md` |
| T-13 | 证据锚定与收口 | AC-011 | VC-038 | 6 | `achieved.md`；`evidence/runs/*`；`evidence/quality-gate-report-*.md` |
| T-14 | Python 侧调用点接线（`launcher.py`/`mw.py`） | AC-005 | VC-042 | 4 | `packages/multi-workers/launcher.py`；`mw.py`；`test_launcher.py` |
| T-15 | Python claim 收窄 + 大小写变体审计 | AC-006 | VC-024…028, VC-043 | 5 | `.agents/skills/agentic-task/scripts/update_index.py`；`shared/pm-state-claim.ts`；新增 Python 一致性测试 |
| T-16 | claim/phase 命令族统一 gate + `caseVariantOf` 审计 | AC-006 | VC-024…028, VC-043 | 5 | `shared/index-store.ts`；`pm/ui-bridge.ts`；`.agents/skills/agentic-task/scripts/update_index.py`；两侧测试 |

## §4 每卡验收命令（PM 统一执行，worker 不得自行运行）

- 单卡 TS：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run <files>`
- Python 侧：`cd packages/multi-workers && node ../../node_modules/vitest/dist/cli.js --run` 不适用 ⇒ 用 `python -X utf8 -m pytest test_<name>.py -q`（单个文件）
- 全量门禁（仅收口）：`npm run check`（不足时再看其 rc 与告警）
- 每卡必须给出：改动文件清单 + 前后行为对照表（输入/期望/实测）+ 红→绿证据（先构造失败断言）

## §5 收口

1. 波 6 完成后 `npm run check` + 相关套件全绿 ⇒ `advance(execute→verify)`。
2. verify 阶段派 **2 张 QG 卡**（code-adversarial 攻击面 + evidence-chain 证据链），PM 逐条读源复现，不得只读摘要。
3. QG 吸收后写 `achieved.md`（须含 `## 系统行为变化` 与 `## 遗留`）⇒ `advance(verify→done)`。
4. 运行期生效：源码级验证 ≠ 生效；如需 `mw build --install` 由用户决定（前 key R21-H 已装 bundle，11 个 pi 窗口未重启）。
