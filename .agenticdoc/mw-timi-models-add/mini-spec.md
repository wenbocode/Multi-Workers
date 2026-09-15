# Mini-Spec: mw-timi-models-add

- Date: 2026-09-14
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

用户要求给 timi provider 增加模型配置：gpt-6、deepseek-v4-flash-vision-exp、glm-5.3-flash。

## Change

`packages/ai/scripts/generate-models.ts` 的 `TIMI_MODELS` 数组追加 3 条（参数对齐同系既有条目）：

| id | api | reasoning | input | ctx/max |
| --- | --- | --- | --- | --- |
| gpt-6 | openai-responses | true | text+image | 200K/64K |
| deepseek-v4-flash-vision-exp | anthropic-messages | false | text+image（vision 实验，同代理 vision 系） | 200K/64K |
| glm-5.3-flash | anthropic-messages | false | text | 200K/64K |

均 TIMI_ZERO_COST + 同系 compat 常量。`npm run generate-models` 重新生成（timi 19→22）；`packages/ai/src/providers/data/` 为 gitignored 生成数据；models.generated.ts 运行时 import data flatten，无 diff 属预期。

## Files

- `packages/ai/scripts/generate-models.ts`（TIMI_MODELS +3 条目）
- `packages/ai/src/providers/data/timi.json`（重新生成，gitignored）
- `packages/ai/CHANGELOG.md`（[Unreleased] Added）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | `pi --list-models` 显示 3 个新 timi 模型且参数正确 | 已验证（22 行，新 3 行 ctx/max/reasoning/image 列正确） |
| AC-002 | 真实调用可用（timi 代理端已部署） | `pi -p --model timi/{gpt-6,deepseek-v4-flash-vision-exp,glm-5.3-flash}` 均返回 "ok" |
| AC-003 | 生成脚本可重复运行，无其他 provider 数据漂移 | `npm run generate-models` + `check:model-data` 通过；`npm run check` 全绿 |

## Result

- 生成 + pi-ai dist 重建 + mw build --install 完成；冒烟 3/3 通过。
- 状态：完成。
