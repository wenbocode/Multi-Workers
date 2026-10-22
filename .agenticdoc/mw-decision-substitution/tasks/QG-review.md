# QG 复审：mw-decision-substitution

- key: mw-decision-substitution · type: review
- 审计目标：本 key EXECUTE 全部交付的**有效性与诚实性**，不是再跑一遍测试

## 上下文

本 key 把 24 个决策点（dp）注册表化，配置表（`.mw/decide-points.json`）是唯一授权权威（DS-9 唯配置论），
并按 D-001..D-042 落地：注册表/控制流（`decision_points.py`）、档案（`decide_archive.py`）、
CLI（`mw decide dp|run|report`）、TS 侧（`triage-client.ts`、`decision-tool.ts`、`worker-mode.ts` dp3 消费、
`pm-orchestrator.ts` dp2 收窄与 settle、`ui-bridge.ts` dp1 结构化 + `decision:` 头行、`shared/xkey-gate-guard.ts` 签收写守卫）、
门禁（`advance_phase.py` done 两条规则）。

实现过程中已由 PM 裁定 42 条契约（design.md D-001..D-042），其中 D-023..D-042 是**实现暴露契约缺陷后补的**。
按 PM 经验，这类 key 最可能的失败模式不是"测试红"，而是**测试绿但生产不可达**（本轮已实测发生 3 次：
T-05 的 TS 镜像配置表、T-09 的守卫放错位置未注册、T-04c 的生产 dp1 走 legacy 分支导致关联链断）。请重点打这三类。

## 审计要求（逐项给结论 + path:line 证据）

1. **AC 覆盖矩阵**：spec.md 的 AC-001..AC-015，逐条指出"由哪个测试/证据证明"，标注 `covered / partial / missing`。
   特别核对：
   - AC-001 关闭态零 spawn、零档案写、产品逐字节同构 —— 在 **CLI 路径**与 **TS 路径**是否都成立？
   - AC-007 `decision:` 头行 —— 生产路径（`computeDispatchTriage` 结构化分支）是否真的写出？
   - AC-011 每次决策一行档案 —— legacy 请求路径是否落行？若否，这是否已被显式记录为缺口？
   - AC-012/013 P0 三门槛（`--i-understand-p0` + `authority-change(by=human:p0-confirm)` + 签收必列 P0）。
2. **单一权威**：全仓搜索是否存在第二处"读 `.mw/decide-points.json` 判断 enabled/mode"的实现（D-036 禁止）。
   `pm/triage-client.ts`、`worker/worker-mode.ts`、`pm/decision-tool.ts`、`pm/pm-orchestrator.ts` 逐处看。
3. **测试有效性抽样（至少 3 处）**：挑你认为最关键的 3 个测试，判断它证的是**生产行为**还是**自己伪造的输入**
   （例：是否直接构造 `TriageResult` 而不经过 `triageDispatch`？是否 stub 掉了被测函数？）。
   已有反例范式：T-07b 用变异测试自证（删掉消费者 → 4 条红）。
4. **契约-实现一致性**：抽查 D-011（dp2 auto 只允许 narrow）、D-012（`decision:` 仅 acted=true）、
   D-014（签收固定名 `sign-final.md`）、D-021/D-028（`input-incomplete` vs `input-oversize`）、
   D-030（七值词表单一）、D-041（acted 由消费侧给出，不由 mode 反推）。指出任何偏离。
5. **安全与隔离**：L2 凭据/密钥是否有路径进入 state（`decision_points` 的 state 构造与 `triage-client` 的 L1 白名单）；
   写守卫是否只覆盖 agent 工具通道（写清楚威胁边界）；`dp apply` 的 agent 会话拒绝是否可用环境变量绕过。
6. **失败模式 vs 文档声明**：`docs/decision-substitution.md` 声称的行为与代码是否一致（抽查 3 条：热生效、
   `dp refresh` 幂等、`revoke` 语义）。

## 不覆盖声明（写进报告，不得含糊）

- 不评估真实 LLM 答案质量（无凭据、且 jev 底座 key 已另行验收）。
- 不评估 `mw build --install` 之后的 L5 真派发路径（本 key 未执行该步骤）。
- 不评估其它 key 的并行改动、Windows 环境类既有失败。
- 不重写实现；发现问题只记录，不改代码。

## 交付格式

- 结论：`PASS` / `PASS-WITH-FINDINGS` / `FAIL`，一句话说明判定依据。
- §A AC 覆盖矩阵（15 行表格：AC / 结论 / 证据 `path:line`）。
- §B 发现清单：按 `blocker / major / minor / nit` 分级，每条含 现象、证据、影响面、建议动作。
- §C 未覆盖面声明（见上）。
- §D 若判 FAIL：列出必须修的条目与最小修复范围。

## 审计目标文件

- `packages/multi-workers/decision_points.py`、`decide_archive.py`、`mw.py`（`_decide_*`、`_dp_*` 段）
- `packages/coding-agent/src/extensions/agent-team-loop/{pm/triage-client.ts,pm/decision-tool.ts,pm/ui-bridge.ts,pm/pm-orchestrator.ts,worker/worker-mode.ts,shared/xkey-gate-guard.ts,index.ts}`
- `packages/multi-workers/test_decision_points.py`、`test_decide_archive.py`、`test_decide_dp_cli.py`、`test_decide_run_authority.py`、`test_decide_report.py`
- `packages/coding-agent/test/suite/{triage-client-state,triage-dispatch,decision-tool,dp3-answer,dp2-narrow,decision-association,decision-signoff}.test.ts`
- `.agenticdoc/mw-decision-substitution/{spec.md,design.md}`、`docs/decision-substitution.md`

## 种子

- goal 锚点：`.agenticdoc/goal.md`
- `packages/multi-workers/decision_points.py:1372`（`decide_for` 11 步，唯一控制流）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:236`（生产 dp1 入口）
- `.agenticdoc/mw-decision-substitution/design.md`（D-001..D-042）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md`（新建，唯一写入）

## 写入禁止面

- 除上列文件外的一切文件（含源码、测试、文档、其它 key 目录）；禁止任何 git 写操作

## 改动历史

- 2026-10-20 创建
