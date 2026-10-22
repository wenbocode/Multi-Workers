# T-03 — DP-1 接入（TS 侧：派发前分诊，旁路建议）

- key: mw-jev-provider-integration · type: coding · W3 · timeout: 55

## 上下文

goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」。W1/W2 已交付可用决策服务（`mw decide run|probe|show|set`）。本任务把第一个决策点 **DP-1「派发前分诊」** 接到 PM 派发路径上：产出 `triage_type` / `triage_risk` 的**旁路建议**，**不改写**派发的 type/角色/模型，也不改 watchdog/checkpoint 策略。

必读锚点：
- `.agenticdoc/mw-jev-provider-integration/design.md`：D-005（**反馈通道三层**：结构化 JSONL 已由 Python 单写、回执 echo、ledger `triage-suggestion` + 仅在"建议与派发类型不一致"时 `deliverPmAlert`）、D-006（挂点与覆盖面：本波仅 `planDispatchFrontmatter`，2/15）、D-004（`confidence_source != api` 时置信度**不得用于任何门控**）、D-009（并发避让）。
- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-dp1-triage-anchors-20261016.md`：`resolveDispatchType`（`ui-bridge.ts:1215-1238`）、`planDispatchFrontmatter`（`:1257`）、两个 PM 入口 `dispatch_worker`（`:2440`）与 `/worker`（`:2938`）、回执点（`:2491-2494` / `:2982`）、worker 模式不注册派发工具（`:2501-2507`）。
- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-feedback-channel-20261016.md`：`recordDispatchAlarm`（`pm-orchestrator.ts:623-641`，best-effort 契约）、notice kinds（`:479-551`）、`describeDispatchAlarm`（`:563-610`）、`deliverPmAlert`（`ui-bridge.ts:188-200`）。
- 既有代码：`pm/shared/mw-runner.ts`（`PYTHON_EXE`/`MW_PY` 与**无窗** spawn 契约，见 W1 证据 Q1）、`pm/ui-bridge.ts:1257`/`:2491`/`:2982`。

## 要求

1. **新模块** `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`：封装同步调用
   `python mw.py decide run --project <dir> --dp dp1 --json`（请求 JSON 走 stdin，含 `state` + `questions`；**不得**用命令行传 state）。必须：
   - 复用**既有** spawn 路径（`shared/mw-runner.ts`，含 `-X utf8`、`PYTHON_EXE`/`MW_PY`、无窗契约），**不要**新写裸 `spawn`；
   - 硬超时（默认 20s，可配；超时 kill 并视为 `available=false reason=timeout`）；
   - 读 `.mw/decide.json` 判定 enabled（未配置 = 完全旁路，**零 spawn、零写入**）；本模块只读配置，不写配置；
   - 解析 stdout JSON；非 JSON / 非零退出 / 异常 → 一律归一为"无建议"，**绝不抛**，不得影响派发；
   - 返回结构化结果：`{ available, reason?, triage_type?, triage_risk?, confidences, confidence_source, latency_ms }`。
2. **挂点**（`pm/ui-bridge.ts`，只在 `planDispatchFrontmatter` 内、任何 fs 写之前）：算出建议后把摘要挂到返回值里供两个入口使用。**禁止**用建议改写 `type`/`role`/`model`/`cli` 或任何派发决策；被派发内容与未开启时逐字节一致。
3. **回执 echo**：在 `dispatch_worker` 工具返回值（`:2491-2494`）与 `/worker` 的 notify（`:2982`）各追加一行建议文案，必须含：
   - 明示「旁路建议，未据此改派发」；
   - `triage_type` / `triage_risk`；
   - 置信度**标注来源**：`confidence_source=model-self-report` 时文案写「模型自报置信度（不用于门控）」，仅 `=api` 时才可作为判据表述。
4. **ledger + 争议唤醒**：
   - `pm/pm-orchestrator.ts` 新增 notice 类 kind `triage-suggestion`（进 `NOTICE_DISPATCH_ALARM_KINDS`）与 `triage-unavailable`，并在 `describeDispatchAlarm` 加文案；
   - 每次**产出建议**时写一行 `triage-suggestion`（保持既有五元组行形状，摘要进 `detail`）；
   - **仅当**"建议类型与派发类型不一致"**且**配置 `points.dp1.alert_on_disagreement !== false` 时，才调 `deliverPmAlert`（唤醒一个 PM turn）；其余情况只写 ledger，不唤醒；
   - 不可用时：默认**不写** ledger、不唤醒、不投文案（完全静默）；仅当 `triage_notify_on_unavailable=true` 时写一行 `triage-unavailable`（仍不唤醒）。
   - **不要**在 TS 侧写 `.agenticdoc/_autopilot/triage-decisions.jsonl`（该文件由 Python 决策客户端**单写**，TS 只读用于展示/诊断）。
5. **默认关闭等价性（硬性验收）**：`.mw/decide.json` 不存在或 `enabled=false` 时——零 spawn、零 ledger 写入、零 notify 增量，派发回执与改动前**逐字节一致**。
6. **测试** `packages/coding-agent/test/suite/`（按该目录既有约定放置，命名自定如 `triage-dispatch.test.ts`）：
   - 关闭态等价（无 spawn、回执不变）；
   - 可用态：回执含建议文案；`confidence_source=model-self-report` 时文案含"不用于门控"；
   - 不一致 → 触发 alert 路径；一致 → 不触发；
   - 不可用/超时/坏 JSON/非零退出 → 静默、派发照常、不抛；
   - ledger 行只在预期条件下出现。
   - 用 `test/suite/harness.ts` + faux provider；**不要**发真实网络请求或真实 provider 调用；spawn 用桩替掉。
7. **禁止**修改 `pm/ui-bridge.ts:3302-3391`（`/mw model` 段，属并行 key `mw-model-fallback-cli`）；禁止改 Python 侧任何文件。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/test/suite/triage-dispatch.test.ts`（新建；若该目录约定要求别的文件名/位置，按约定并在 report 说明）

## 写入禁止面

- `packages/multi-workers/**`（Python 侧已冻结，含 `decision*.py`、`mw.py`、`mw_common.py`）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 的 `:3302-3391` 段
- 其它一切文件；禁止 `git add`/`commit`；禁止写入其它 key 目录

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts
cd packages/coding-agent && npx tsgo --noEmit -p tsconfig.json   # 若该包无此脚本，改跑仓库既有 typecheck 命令并记录
```

## 改动历史

- 新建任务；`ui-bridge.ts` / `pm-orchestrator.ts` 在同波无其它束写入（并行 key 的写入面为 `ui-bridge.ts:3302-3391` 与 `mw.py` cmd_model 段，与本任务不交叠）。

## 交付格式

- 上述文件 + `report.md`（结论 / 证据 / 残留与未验证 / 上下文来源）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**前 10 次写调用内落出 `triage-client.ts` 初版**。
- 明确报告：本波覆盖面（仅 PM 发起派发）、以及"未覆盖 conductor 的 13 个自动派发点"这一事实。
