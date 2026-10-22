# T-05b — 对抗评审（质量门，收窄重派）

- key: mw-jev-provider-integration · type: review · W5 · timeout: 40

## 上下文

goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」。本 key 已交付 Python 决策服务（`decision.py` / `decision_backends.py` / `mw decide`）+ doctor 行 + TS 侧 DP-1 派发前分诊（`triage-client.ts` / `ui-bridge.ts` / `pm-orchestrator.ts`）+ 验证证据与文档。本任务对最终状态做**收窄后的**对抗评审（前一轮因范围过宽 + 工具调用形状错误被终止，本轮只审最高价值项）。

必读（按需读，避免重复通读）：
- `.agenticdoc/mw-jev-provider-integration/spec.md`（§2 业务约束、§3 AC-001..012、§4 D-1）
- `.agenticdoc/mw-jev-provider-integration/design.md`（D-002 B2 模板与禁止字段、D-004 错误类别与置信度硬规则、D-005 反馈三层、D-006 覆盖面）
- `.agenticdoc/mw-jev-provider-integration/evidence/runs/verify-mw-jev-provider-integration-20261016.md`
- 实现：`packages/multi-workers/decision.py:1`、`packages/multi-workers/decision_backends.py:1`、`packages/multi-workers/mw.py:953`（`cmd_decide`）、`packages/multi-workers/mw_common.py:1599`（`_doctor_decide`）、`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:1`、同目录 `ui-bridge.ts:1257`（`planDispatchFrontmatter`）与 `ui-bridge.ts:2491`（派发回执）、`pm-orchestrator.ts:532`（alarm kind 段）。

## 审计目标（只审这 4 项 + 1 组抽查，逐条给结论 + `文件:行` + 复现命令）

1. **敏感内容外发**：DP-1 的 `state` 取自派发场景描述，会被发到 B2（timi 网关内模型）。评估：是否裁剪/上限（`max_state_bytes`）；派发描述可能含路径、内部标识、用户原文；给出风险级别与最小缓解建议。这是本轮最需要独立判断的一条，**不要**照抄实现自己的说法。
2. **测试真实性**：是否存在「断言自己写的 mock」的自证式测试、恒真断言、只覆盖 happy path；TS 用例是否基于 `test/suite/harness.ts` + faux provider 且 spawn 被桩替（不得真实联网/真实派发）；Python 用例是否 hermetic（`tmp_path` / `monkeypatch`）。
3. **默认关闭等价性**：`.mw/decide.json` 缺失或 `enabled=false` 时是否真的零 spawn、零文件写入、零 notify 增量、回执与改动前一致；测试是否**真断言**了这一点（而非仅"未抛异常"）。
4. **诚实性与凭据**：文案/文档是否如实声明"仅 PM 发起派发（2/15）、conductor 13 个自动派发点未覆盖"；B1 是否始终 `entry-unavailable`（不得写成可用）；`confidence_source=model-self-report` 是否被标为"不用于门控"；key 是否可能进入文件、stdout/stderr、证据行、ledger `detail`、doctor 输出、错误文本。

5. **抽查**：自己重跑 2 条 AC（必须含「默认关闭等价性」与「fail-soft 退出码」），输出与 T-04 证据记录不一致即 blocker。

## 未覆盖面声明（必须写进报告）

- 不审 conductor 派发链与 PM 主循环本身的既有设计；
- 不审 D-1 上游（llmproxy/timiai）实现；
- 不做压测；不审本轮未交付项（conductor 侧挂点、`mode: async`、B3 真实链路、`box` 问题类型、TS 面板逐字同步 doctor 行）；
- 不重跑 multi-workers 全量套件。

## 唯一证据文件

`report-qa.md`（任务自目录；PM 收活后归位）

### 交付方式（必须严格照此形状，上一轮在这里失败）

调用 `worker_file`，参数**只传 basename**，**不要**传任何目录或绝对路径：

```text
worker_file(file="report-qa.md", mode="write", content="<本次审计报告全文>")
```

- `file` 只接受 `progress.md` / `report.md` / `report-<slug>.md`（basename）或 `evidence/...` 相对路径；传绝对路径会被 schema 拒绝。
- `content` 上限 64 KiB（UTF-8）：报告请控制在 **≤ 300 行 / 40 KiB** 以内；必要时先精简再写。
- 写完后用一次回复给出结论摘要（PASS/FAIL + 分级计数）即可，不需要再写第二个文件。

## 写入允许面

- `report-qa.md`

## 写入禁止面

- 一切源码/配置/文档/测试/evidence 路径；禁止 `git add`、`git commit`；禁止改动其它 key 目录

## 验收命令（评审者自己跑，输出 ≤30 行/条）

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
cd H:/git/Multi-Workers && git status --porcelain
```

## 改动历史

- 2026-10-16 首派 `jev-t05-qg-review` 被终止（范围 10 项 + worker_file 形状错误）；
- 2026-10-16 本卡收窄重派（4 项 + 1 组抽查，显式工具调用形状）。

## 交付格式

`report-qa.md`：`结论(PASS/FAIL) + blockers/majors/minors/notes 分级清单（每条：文件:行 + 复现命令 + 影响）+ 未覆盖面声明 + 抽查结果（2 条 AC）`。不许只给结论。输出卫生：命令输出 ≤30 行/条。
