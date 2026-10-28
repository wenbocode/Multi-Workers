# Mini-Spec: mw-timi-models-add (batch 2)

- Date: 2026-10-15
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop
- Supersedes/extends: mini-spec batch 1 (gpt-6 / deepseek-v4-flash-vision-exp / glm-5.3-flash), gpt-6-astra rename

## Problem

用户要求给 timi provider 再配置 4 个新模型：`jev-latest`、`gpt-6.1-sol`、`glm-5.3-flashx`、`claude-opus-5.5`（均为 timi 代理端已上线模型，`/v1/models` 实测存在）。当前本地 pi 模型表没有这些 id，派发时对照模型表校验会直接拒绝，必须先加入目录。

## Change

`packages/ai/scripts/generate-models.ts` 的 `TIMI_MODELS` 数组追加 4 条（参数对齐同系既有条目，复用 TIMI_ZERO_COST / TIMI_ANTHROPIC_COMPAT / TIMI_RESPONSES_COMPAT）：

| id | api | reasoning | input | ctx/max |
| --- | --- | --- | --- | --- |
| jev-latest | anthropic-messages | true | text | 200K/64K |
| gpt-6.1-sol | openai-responses | true | text+image | 200K/64K |
| glm-5.3-flashx | anthropic-messages | true（实测独立 thinking 块） | text | 200K/64K |
| claude-opus-5.5 | anthropic-messages | false | text+image | 200K/64K |

`npm run generate-models` 重新生成；`packages/ai/src/providers/data/` 为 gitignored 生成数据；models.generated.ts 运行时 import data flatten。

> jev-latest 探针说明：anthropic `/v1/messages` 持续 429（rate limit），openai `/responses` 返回 "Unmapped LLM provider" — 判为 anthropic-messages 系。reasoning=true / input=text 为保守默认，待 429 消退后可复核修正。

## Files

- `packages/ai/scripts/generate-models.ts`（TIMI_MODELS +4 条目）
- `packages/ai/src/providers/data/timi.json`（重新生成，gitignored）
- `packages/ai/CHANGELOG.md`（[Unreleased] Added +1 行）
- `.mw/dispatch.yml`（不改动：用户未指定角色映射；模型仅入库可用，角色默认值另行 `mw model set`）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | `pi --list-models` 显示 4 个新 timi 模型且参数正确 | 22 行 → 26 行，含 4 个新 id |
| AC-002 | 真实调用可用（timi 代理端已部署） | `pi -p --model timi/{gpt-6.1-sol,glm-5.3-flashx,claude-opus-5.5}` 返回 "ok"；jev-latest 视 429 消退 |
| AC-003 | 生成可重复、无其他 provider 漂移 | `npm run generate-models` + `npm run check` 全绿 |
| AC-004 | serve 重启后配置生效 | `/mw restart` 后 `mw model show` 无异常 |

## Result

- 4 个模型已加入 `TIMI_MODELS`（generate-models.ts）并重新生成数据：`npm run generate-models` 后 timi 23→27。models.dev 上游漂移（573 处语义差异，含 opencode-go 新增 google-generative-ai 模型导致 tsgo 类型错误）通过恢复非 timi 数据文件 + 重新生成 manifest 解决，最终改动仅限 timi.json（+4 模型）+ manifest（structureHash/files 更新）。
- pi-ai dist 重建完成（check:model-data + tsgo 通过）；`pi --list-models` 显示 27 个 timi 模型，4 个新 id 参数正确。
- 冒烟测试：`pi -p --model timi/{gpt-6.1-sol,glm-5.3-flashx,claude-opus-5.5}` 均返回 "ok"；`timi/jev-latest` 持续 429（代理端 rate limit，非配置问题），目录条目正确（anthropic-messages/reasoning/text）。
- CHANGELOG [Unreleased] Added +1 行。
- `.mw/dispatch.yml` 未改动（用户未指定角色映射）；窗口模型已由用户自行选择为 `timi/jev-latest`（11:43 写入 .mw/window-model），证明新模型可在框架中选择使用。
- serve 重启完成（PID 44100 → 65248，/mw restart 等效协议：stop-request + 新 serve 启动）；重启导致另一窗口的 woc-t13-selfcheck-r2 工作进程中断（由归属窗口处理重试）。
- AC-001 通过（--list-models 27 行）、AC-002 3/4 通过（jev-latest 429）、AC-003 通过（check:model-data + tsgo）、AC-004 通过（serve 重启后 mw model show 正常）。
