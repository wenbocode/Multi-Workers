# T-05 — 对抗评审（质量门）

- key: mw-jev-provider-integration · type: review · W5 · timeout: 55

## 上下文

本 key（goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」）已交付：Python 决策服务（`decision.py` / `decision_backends.py` / `mw decide`）+ doctor 行 + TS 侧 DP-1 派发前分诊（`triage-client.ts` / `ui-bridge.ts` / `pm-orchestrator.ts`）+ 验证证据与文档。本任务对**最终状态**做对抗评审，目标是找出"看起来能用、实际会破"的路径。

必读：
- `.agenticdoc/mw-jev-provider-integration/spec.md`（§2 业务约束、§3 AC-001..012、§4 D-1）
- `.agenticdoc/mw-jev-provider-integration/design.md`（D-002 后端模板、D-004 错误类别与置信度硬规则、D-005 反馈三层、D-006 覆盖面）
- `.agenticdoc/mw-jev-provider-integration/plan.md`（§2 波次与验收）
- `.agenticdoc/mw-jev-provider-integration/evidence/runs/verify-mw-jev-provider-integration-20261016.md`（T-04 产物）
- 实现：`packages/multi-workers/decision.py:1`、`packages/multi-workers/decision_backends.py:1`、`packages/multi-workers/mw.py`（`cmd_decide` 段）、`packages/multi-workers/mw_common.py`（`_doctor_decide` 段）、`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:1`、`pm/ui-bridge.ts`（`planDispatchFrontmatter` 与派发回执段）、`pm/pm-orchestrator.ts`（`NOTICE_DISPATCH_ALARM_KINDS` 与 `describeDispatchAlarm` 段）

## 审计目标（逐条给结论 + 证据 `文件:行` + 复现命令）

1. **默认关闭等价性**：`.mw/decide.json` 缺失或 `enabled=false` 时，是否真的零 spawn、零文件写入、零 notify 增量、派发回执与改动前一致？核对测试是否**真断言**了这一点（而非仅"未抛异常"），并指出测试未覆盖的分支。
2. **fail-soft 铁律**：穷举异常路径（后端抛异常、超时 kill、非 JSON、非零退出、配置损坏、证据文件不可写、ledger 不可写、doctor 段抛错），确认**都不外泄、都不阻断派发/CLI**；找出任何一条会把异常冒泡到 PM/CLI 的路径。
3. **置信度硬规则**：`confidence_source != "api"` 时，置信度是否被任何门控/阈值/排序消费？grep 全部消费点并给出结论（允许"仅文案展示/弱排序"）。
4. **凭据最小面**：是否存在任何路径把 key 写进文件、stdout/stderr、证据行、ledger `detail`、doctor 输出、错误文本？包括超时/异常路径与 `probe` 输出。
5. **敏感内容外发**：DP-1 的 `state` 取自派发场景描述（可能含用户文本/路径/内部标识）。检查是否有裁剪/上限（`max_state_bytes`），并评估"把 state 发给 B2（timi 网关内模型）"的暴露面，给出风险级别与建议（这是本任务最需要独立判断的一条）。
6. **覆盖面诚实性**：核对文档/回执/ledger 文案是否如实声明"仅 PM 发起派发（2/15）、conductor 的 13 个自动派发点未覆盖"；是否存在任何"全量生效"的暗示。
7. **他窗写入面**：`git diff`/`git status` 核对本 key 改动是否全部落在声明写入面内；特别确认 `mw.py` 的 `_goal_gate_install`/`cmd_model` 段与 `ui-bridge.ts:3302-3391` 未被本 key 触碰。
8. **测试真实性**：TS 用例是否基于 `test/suite/harness.ts` + faux provider、spawn 是否被桩替（不得真实联网/真实派发）；Python 用例是否 hermetic（`tmp_path`/`monkeypatch`）；是否存在"断言自己写的 mock"的自证式测试或恒真断言。
9. **上游现状表述**：`entry-unavailable` / probe 矩阵 / D-1 的描述是否与实测一致（不得把 B1 未暴露写成"已可用"，也不得把 B2 的模型自报置信度写成 api）。
10. **AC 可复现性**：抽查 T-04 证据文件里至少 3 条 AC，**自己重跑命令**确认输出与记录一致（不一致即为 blocker）。

## 未覆盖面声明（必须写进报告）

- 不审 `packages/multi-workers` 之外的既有框架代码（如 conductor 派发链、PM 主循环）本身的设计；
- 不审 D-1 上游（llmproxy/timiai）实现；
- 不做真实生产规模压测（仅按需 1–2 次真实 B2 调用，若凭据不可用则声明为未验证）；
- 不审本轮未交付项：conductor 侧挂点、`mode: async`、B3 真实链路、`box` 问题类型、TS 面板逐字同步 doctor 行。

## 唯一证据文件

`report-qa.md`（任务自目录，用 worker_file 写；PM 收活后归位，不要求评审写任务目录外路径）

## 写入允许面

- `report-qa.md`

## 写入禁止面

- 一切源码/配置/文档/测试/evidence 路径；禁止 `git add`/`commit`；禁止修改任何其它 key 目录

## 验收命令（评审者自己跑）

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
cd H:/git/Multi-Workers && git status --porcelain && git diff --stat
```

## 交付格式

`report-qa.md`：`结论(PASS/FAIL) + blockers/majors/minors/notes 分级清单（每条含 证据文件:行 + 复现命令 + 影响）+ 未覆盖面声明 + 对 T-04 证据的抽查结果`。**不得**只给结论不给证据；发现问题必须给出可复现路径。输出卫生：report 内命令输出 ≤30 行/条。
