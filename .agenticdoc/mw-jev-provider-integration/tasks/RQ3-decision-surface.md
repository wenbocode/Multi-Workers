# RQ-3 — 决策面调研:jev 进入框架调度/回退/反馈链的接入点

- key: mw-jev-provider-integration · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（.agenticdoc/goal.md）mw 后台服务（调度器 + 决策）。目标第 2 条：「框架需要决策的时候正确调用及有效反馈」= 模型在 conductor/launcher 的选型、回退、错误反馈三条链上行为正确。**强相关在飞 key**：`mw-model-fallback-cli`（active/SPEC，他窗持有——本调研只读其对齐，不写不改）；`mw-model-error-perception`（DONE，f551f1c90 已提交 retry/fallback 链）。锚点: `packages/multi-workers/autopilot/conductor.py:1`（调度决策）、`packages/multi-workers/.mw/dispatch.yml`（role→model 映射实例）、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3601`（judgeRecoveryHere 一带的模型错误感知/回退触发面）。

## 审计目标（调研问题）

- Q1 选型链：conductor/launcher 从哪里读 role→model（dispatch.yml 的 schema、role 清单：coding/research/review/verifier…）、模型字符串如何解析到 provider+model、非法/不可用模型 id 的失败形态
- Q2 回退链：f551f1c90 落地的 retry/fallback chain 的配置面（fallback_models?每 role 独立?）与触发判据；新模型接入时要配哪些键才「正确调用」
- Q3 反馈链：模型层错误的传播路径（[MODEL_ERR]/run 记录/widget 可见性/PM triggerTurn 升级）——「有效反馈」的现有机制清单与新模型需满足的假设（如错误响应形状按 anthropic-messages 协议解析）
- Q4 mw-model-fallback-cli 的 spec 范围（只读 `.agenticdoc/mw-model-fallback-cli/spec.md`）：它做什么、jev key 应该**复用**它什么、边界怎么划（避免两 key 改同一文件冲突）
- Q5 决策时刻盘点：框架里「需要决策」的点全列（conductor 派发选模、worker 重试换模、PM escalation、/mw model 手动切换）——每处的模型来源与 jev 接入所需配置
- Q6 凭据面：jev 调用用什么凭据（timi auth.json 条目?独立 env?）、per-task 凭据隔离(mw-dispatch-reliability 交付)对 jev 的要求

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-decision-surface-20261016.md`（新建，全文中文，每条结论附 文件:行号；mw-model-fallback-cli 只读引用）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-decision-surface-20261016.md`

## 写入禁止面

- 一切源码/配置；`.agenticdoc/mw-model-fallback-cli/**` 只读；禁止 git add/commit

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\spec-jev-decision-surface-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件 + 六问逐条结论 + 「jev 决策面接入清单」一节（配置键/代码点/与 fallback-cli 的分工边界）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
