# Mini-Spec: mw-timi-gpt6-astra-rename

- Date: 2026-09-23
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: mw-timi-models-add

## Problem

用户要求把当前 `timi/gpt-6` 模型配置换成 `timi/gpt-6-astra`（timi 代理端模型名变更）。

## Change

`packages/ai/scripts/generate-models.ts` TIMI_MODELS 中 `gpt-6` 条目重命名：id `gpt-6` → `gpt-6-astra`，name `GPT-6` → `GPT-6 Astra`（对齐 GPT-5.6 Luna/Sol/Terra 命名风格）。其余参数不变（openai-responses、reasoning、text+image、200K/64K、TIMI_ZERO_COST、TIMI_RESPONSES_COMPAT）。

`npm run generate-models` 重新生成；`packages/ai/src/providers/data/` 为 gitignored 生成数据。

CHANGELOG `[Unreleased] > Added` 条目中 `gpt-6` 未发布，直接修正为 `gpt-6-astra`。

## Files

- `packages/ai/scripts/generate-models.ts`（TIMI_MODELS 1 条目重命名）
- `packages/ai/CHANGELOG.md`（[Unreleased] Added 条目修正）
- `packages/ai/src/providers/data/timi.json`（重新生成，gitignored）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | `timi/gpt-6-astra` 出现在生成数据中，`timi/gpt-6` 不再存在 | timi.json 检查 |
| AC-002 | 生成可重复、无其他 provider 漂移 | `npm run generate-models` + `npm run check` 通过 |
| AC-003 | 真实调用可用 | `pi -p --model timi/gpt-6-astra` 返回 ok（代理端已部署 astra） |

## Result

- `generate-models.ts` 重命名完成；`npm run generate-models`（timi 22→23 条含 astra，无其他 provider 漂移）+ pi-ai dist 重建；全局 pi 为 workspace junction，无需 mw build --install（模型数据经 pi-ai dist 解析，agent-team-loop bundle 不含模型表）。
- AC-001 通过：`--list-models` 显示 `timi/gpt-6-astra`（200K/64K/reasoning/image），`gpt-6` 不存在。
- AC-002 通过：`npm run check` 全绿。
- AC-003 通过：`pi -p --model timi/gpt-6-astra` 返回 ok。
- 状态：完成。
