# T-07: 收尾（check/套件/文档/changelog）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`；AGENTS.md：代码变更后 `npm run check` 全绿；changelog 规范（packages/*/CHANGELOG.md，[Unreleased] 追加）。
- 依赖：T-05（13/13）、T-06（70/70）、T-01b/T-03b 全部合入；PM 直执基线适配已入工作区（checkpoint-wiring VC-007、autopilot-protocol VC-023/GC-8 快照补 `mw_run_detached`，见 key-decision.md 裁决 2）。
- 实现锚点（行号以当前文件为准）：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（activeToolsForType/timeoutExit/modelExhaustedExit）、`worker/output-writer.ts`（exitCode 3 渲染）、`packages/multi-workers/launcher.py:1979` 附近（fallback env/重派）、`packages/multi-workers/mw_common.py`（fallback_models 校验导出）、`packages/mw-orchestrator` 或 pm/pm-orchestrator.ts（model-error 告警）。
- 已知基线噪声（非本 key 产物，报告须逐条列出并豁免，不得为凑全绿而改）：① `test/suite/mwoc-*.test.ts` biome 3 warning + 2 info（HEAD/他窗）；② `test/extensions/agent-team-loop.test.ts` T-17/B-1 anchor integrity（mw-guard-form-hardening 行号位移）；③ pytest `test_bom_historical_books...`（BOM 语料缺失，--deselect 注明）；④ agent/coding-agent 套件 Windows 已知 89 环境失败基线（AGENTS.md）。

## 要求

1. 全量验证：`npm run check` 全绿（无 error/warning/info）；`./test.sh` 相关 TS 套件；`python -m pytest`（multi-workers 全量）。
2. changelog：`packages/coding-agent/CHANGELOG.md` 与 `packages/multi-workers/CHANGELOG.md`（若存在）[Unreleased] 追加本 key 变更（Added/Changed/Fixed 分类，按仓库格式）。
3. 文档：`.mw/dispatch.yml` 的 `fallback_models` 键与 env 契约写入 `packages/multi-workers/README.md`（或既有配置文档节）；`docs/` 下 mw 相关文档若有 worker watchdog 节则同步。
4. 运行时生效说明：dist bundle 需重建 + `/mw restart` 方可对新 worker 生效——写入交付说明（不自行 npm run build，PM 统一安排）。
5. 禁止：改 src 实现逻辑（发现问题报 PM）；改测试期望来迁就失败。

## 写入允许面

- `packages/coding-agent/CHANGELOG.md`、`packages/multi-workers/CHANGELOG.md`（若存在）
- `packages/multi-workers/README.md`、`docs/**`（mw 相关节）
- `.agenticdoc/mw-model-error-perception/evidence/quality-gate-report-*.md`（验证报告）

## 写入禁止面

- src/**、test/**（除验证报告外）、Python 实现、`~/.pi`

## 交付格式

- changelog/README/docs 修改 + `evidence/quality-gate-report-<date>.md` 验证报告（仅限写入允许面）
- 交付说明：各门禁命令输出摘要、基线噪声豁免清单、运行时生效步骤（npm run build + /mw restart，不自行执行）；发现的实现问题仅报告不修

## 验收命令

```
npm run check            # 除已知 mwoc-* biome 基线告警外全绿，逐条列出
./test.sh                # 对照 AGENTS.md Windows 基线（89 环境失败）比较，新增失败为零
python -m pytest packages/multi-workers -q --deselect ".../test_bom_historical_books_read_through_both_callsites"
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-model-error-perception.test.ts
```

- 以上口径全绿；验证报告落 evidence/

## 改动历史

- 2026-10-15 任务创建（T-07，Stage 3，依赖 T-05/T-06）；同日修订：补种子/交付格式、基线噪声豁免口径、PM 直执适配说明
