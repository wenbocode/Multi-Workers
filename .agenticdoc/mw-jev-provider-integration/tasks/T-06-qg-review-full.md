# T-06 — QG 验收门 + 代码 review（最终状态复审）

- key: mw-jev-provider-integration · type: review · W6 · timeout: 45

## 上下文

用户指令：在**最终状态**（含 QG minor 快修 M1/M2/M3 之后）再起 review worker，做 QG 与 review 两层。goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」。本 key 已 DONE；本轮是**完成后复审**，产出独立证据；若发现 blocker/major，由 PM 决定快修（走 mini-spec 或修复任务）。

必读（按需读，避免重复通读）：
- `.agenticdoc/mw-jev-provider-integration/spec.md:1`（§2 业务约束 / §3 AC-001..012 / §4 D-1）
- `.agenticdoc/mw-jev-provider-integration/design.md:1`（D-002 B2 模板与禁止字段 / D-004 错误类别与置信度硬规则 / D-005 反馈三层 / D-006 覆盖面 / D-008 配置与脱敏 / D-009 并发避让）
- `.agenticdoc/mw-jev-provider-integration/plan.md:1`（§2 波次与验收）
- 上一轮产出：`.agenticdoc/mw-jev-provider-integration/evidence/quality-gate-report-20261016.md:1`（含「PM 处置」节，列出 M1/M2/M3 修法与 M4 闭合）与 `evidence/runs/verify-mw-jev-provider-integration-20261016.md:1`
- 实现：`packages/multi-workers/decision.py:1`、`packages/multi-workers/decision_backends.py:1`、`packages/multi-workers/mw.py:953`（`cmd_decide`）、`packages/multi-workers/mw_common.py:1599`（`_doctor_decide`）、`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:1`、`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1257`（`planDispatchFrontmatter`）、`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:532`（alarm kind 段）
- 测试：`packages/multi-workers/test_decide.py:1`、`test_decide_backends.py:1`、`test_decide_cli.py:1`、`packages/coding-agent/test/suite/triage-dispatch.test.ts:1`

## 审计目标

两部分：第一部分是 QG 验收门（AC 层，10 项），第二部分是代码 review（实现质量层，5 项）。每项给结论 + 复现命令 + 输出要点。

### 第一部分：QG 验收门（AC 层，逐条给结论 + 复现命令 + 输出要点）

1. **AC-001 契约**：CLI = API；`choice` / `score` / `noul` / `box` 四型问题的校验与取值强制；`confidence_source` 由后端声明并如实传播。
2. **AC-002 fail-soft**：除参数非法（exit 2）外任何异常都不得外泄；请**自跑**三条：缺 `questions`、未知问题类型、未配置项目下的 `run`。
3. **AC-003 传输抽象**：三后端可切换（B1 显式 `entry-unavailable`、B2 默认、B3 保留位）；**自跑** `mw decide probe --json` 并核对矩阵与 D-1 现状一致。
4. **AC-005 凭据最小面**：**自跑** `mw decide set --json`、`show --json`、`probe`，确认无明文 key（注意：M2 快修新增了 `_decide_redact_secrets`，要验证**修复真的生效**且落盘值未被误改）。
5. **AC-007 默认关闭等价**：**自跑**未配置项目的 `mw decide show`（预期 disabled）与 `mw doctor`（预期**没有** `triage:` 行）。
6. **AC-009 默认零行为变化**：读 `triage-dispatch.test.ts` 的"逐字节等价"断言，判断是**真断言**还是仅"未抛异常"。
7. **AC-011 测试真实性**：跑 131 Python + 21 TS；并**读测试代码**判断是否存在恒真断言、自证式断言（上一轮发现 M3 已修——请核对修法是否真的建立了不变量）、未覆盖分支。
8. **诚实性与上游表述**：覆盖面 2/15 与 13 个未接入的 conductor 派发点是否如实声明；B1 是否任何路径都不会返回 `available=true`；`model-self-report` 是否固定带"不用于门控"标注。
9. **他窗写入面**：`git status --porcelain` + `git diff --stat` 核对本 key 改动是否只在声明面内——特别确认 `mw.py` 的 `_goal_gate_install` / `cmd_model` 段与 `ui-bridge.ts` 的 `/mw model` 段（`:3302-3391`）**未**被本 key 触碰。
10. **快修 delta 复核**（M1/M2/M3）：核对四处改动是否真的修好且无回归——`mw.py` 的 `_decide_redact_secrets`、`test_decide_cli.py` 的新用例、`test_decide_backends.py` 的断言替换、`packages/multi-workers/README.md` 新增「覆盖面与数据流」节。

### 第二部分：代码 review（实现质量层）

11. **Python 错误分类**：8 类处置是否与 design D-004 一致；是否会对**不可重试**类别重试；退避/`timeout_s`/`max_retries` 边界；过度 fail-soft 是否可能吞掉真实缺陷（静默失败面有多大）。
12. **Python B2 契约**：请求体是否禁带 `response_format`/`state`/`questions`/`store`；`tool_use` 解析、text 回退、thinking/text 块忽略；`box` 是否**不发请求**即拒。
13. **TS 调用面**：`triage-client.ts` 的硬超时是否真的会 kill 子进程；stdin 写法；JSON 解析失败、非零退出、spawn 失败的归一；`state` 截断上限；是否复用 `mw-runner` 的无窗 + `-X utf8` 契约（不得自写裸 spawn）。
14. **TS 反馈语义**：ledger 行/回执文案/降级静默是否与 design D-005 一致；`deliverPmAlert` 是否**只在**"建议类型 ≠ 派发类型"且配置允许时触发；新增 kind 是否进了 `NOTICE_DISPATCH_ALARM_KINDS`（影响 PM 面板可见性）；不可用时是否真的零通知。
15. **可维护性**：`decision.py` 与 `mw_common.py` 是否重复实现证据行读取；死码/未使用导出；命名与注释是否与实现一致。

## 未覆盖面声明（必须写进报告）

- 不审 conductor 派发链与 PM 主循环的既有设计；不审 D-1 上游（llmproxy/timiai）实现；不做压测。
- 不审本轮未交付项：conductor 侧挂点、`mode: async`、B3 真实链路、`box` 真实链路、TS 面板逐字同步 doctor 行。
- 不跑 `npm test` / `npm run build`；不重跑 multi-workers 全量套件（可按需跑决策三套件 + 单个 TS 用例）。
- 真实 B2 调用最多 2 次；凭据不可用则声明为未验证。

## 唯一证据文件

`report-qg.md`（任务自目录；PM 收活后归位为 `evidence/quality-gate-report-20261016-recheck.md`）

### 交付方式（上一轮在这里失败过，严格照此）

```text
worker_file(file="report-qg.md", mode="write", content="<报告全文>")
```

- `file` **只传 basename**（`report-qg.md` 匹配 `report-<slug>.md`）；**不要**传目录或绝对路径——传绝对路径会被 schema 拒绝，且会零产出地耗掉整个预算。
- `content` ≤ 64 KiB（UTF-8）；报告控制在 **≤ 320 行 / 45 KiB**。
- **write-first**：前 20 次工具调用内先写出一版骨架版 `report-qg.md`（含已完成的项），之后用 `mode="append"` 逐项补充；**不要**等到最后一次性写。
- 写完后用一次回复给出结论摘要（PASS/FAIL + 分级计数）。

## 写入允许面

- `report-qg.md`

## 写入禁止面

- 一切源码/配置/文档/测试/evidence 路径；禁止 `git add`、`git commit`；禁止改动其它 key 目录

## 验收命令（评审者自己跑，输出 ≤30 行/条）

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py test_decide_backends.py test_decide_cli.py
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
cd H:/git/Multi-Workers && git status --porcelain
```

## 改动历史

- 2026-10-16 首轮 QG `jev-t05-qg-review` 被终止（范围过宽 + 工具形状错误）；
- 2026-10-16 收窄重派 `jev-t05b-qg-review` → PASS（0B/0M/4m/5n），4 条 minor 由 PM 处置；
- 2026-10-16 本卡：用户指令，最终状态全量复审（QG + 代码 review 两层）。

## 交付格式

`report-qg.md`：`结论(PASS/FAIL) + 分级清单 blockers/majors/minors/notes（每条：文件:行 + 复现命令 + 影响 + 建议处置）+ 两部分小结（QG / 代码 review）+ 未覆盖面声明`。不许只给结论。输出卫生：命令输出 ≤30 行/条。
