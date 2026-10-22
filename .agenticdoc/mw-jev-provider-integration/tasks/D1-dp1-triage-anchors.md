# RQ-D1 — DP-1（派发前分诊）的判定链与可接入锚点

- key: mw-jev-provider-integration · type: research · DESIGN 相位调研
- timeout: 40

## 上下文

本 key 要在 **派发前分诊**（判定任务类型 + 风险等级）处接入一个决策服务（Jev，接口形态 `state` + `questions` → `answers` + `confidence`），本波只做**旁路建议**：不改写派发的类型/角色/模型，不改 watchdog/checkpoint 策略，但建议必须能被 PM 看到。

goal.md 第 2 条：框架需要决策的时候正确调用并有效反馈。已知锚点：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1258-1339`（`planDispatchFrontmatter`，派发前的生效模型/能力校验）、`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts:56-69`（`DISPATCH_ROLE_BY_TYPE`）、`packages/multi-workers/mw_common.py:144-156`（`TASK_TYPE_TO_ROLE`）、`packages/multi-workers/autopilot/dispatch.py:615-629`（`RECOVERY_CONTRACT_TYPES` 注入点）、`packages/multi-workers/autopilot/conductor.py:6500`（conductor 写 `model: ""`）。风险等级那一条是 goal.md Key Constraints 里的"30 分钟收敛检查点（[CHECKPOINT] 机器判据 + worker 自评，mid/high risk 经 triggerTurn 升级 PM）"。

## 审计目标（调研问题）

- Q1 任务类型如何确定：TS 侧与 Python 侧各自的判定源与顺序（卡片 frontmatter？`type:` 头？调用参数？），未知类型的兜底。给 path:line。
- Q2 风险等级现状：`mid/high` 等取值由谁产生、在哪些点被消费（checkpoint 升级、watchdog、review 分级？），给 path:line；若风险等级目前并无显式字段，明确说"不存在"并给出最接近的替代（如 phase/复杂度启发式）。
- Q3 派发前一刻可用的输入数据面：能拿到哪些字段（task.md 头字段全集、卡片正文、key/phase、依赖、goal.md 引用），由哪个函数持有；给出 ≥2 个可插入点候选（函数 + 行号 + 入参/返回值）。
- Q4 既有"派发前校验/注入"挂点盘点：`validateModelValue` 调用点、`planDispatchFrontmatter` 调用点、Python 侧卡片信封校验/注入（含 `dispatch.py` 的注入清单）——哪些点天然适合挂一次外部决策调用（同步、失败可忽略、不改变派发结果）。
- Q5 旁路建议的落点候选：若只写一条建议（不改行为），既有可写的面有哪些（worker trace.log 机器行、PM 可见的派发回执、autopilot ledger、launcher.log、`.mw/` 下的报告文件……），每项给出写入 API 的 path:line 与"PM 是否会自然看到"的判断。
- Q6 覆盖面与反例：哪些派发路径**不**经过这些挂点（conductor 自动派发、autopilot L2/L3 verifier/reviewer 派发、PM 手动派发、worker 自我分拆），结论要能回答"DP-1 接入后覆盖多少比例的派发"。

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-dp1-triage-anchors-20261016.md`（新建，全文中文，每条结论附 文件:行号）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-dp1-triage-anchors-20261016.md`

## 写入禁止面

- 一切源码/配置；禁止 git add/commit；禁止写入其它 key 目录

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\design-dp1-triage-anchors-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件：六问逐条结论（含 path:line）+ 「DP-1 可插入点候选表」（候选 / 位置 / 同步成本 / 失败影响 / 是否改变派发行为）+ 「覆盖面结论」一节。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
