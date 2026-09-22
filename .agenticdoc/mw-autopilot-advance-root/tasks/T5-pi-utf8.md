# T5: pi 扩展 -X utf8

> Key: mw-autopilot-advance-root | AC-004 | 依赖：无（与 T4 并行）

## 目标

`packages/coding-agent/src/extensions/agent-team-loop/shared/agent-scripts.ts::runAgenticScript` 的 `spawnSync(PYTHON_EXE, [script, ...args], …)` 加 `-X utf8`，与 mw 侧诊断编码一致。

## 证据

- `npm run check` 0/0/0。
- 既有扩展测试全绿。
