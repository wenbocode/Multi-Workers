# Evidence Run: 002-py-target-config-parity

- Date: 2026-09-11T17:15:00+08:00
- Task: 002-py-target-config-parity（S1）
- Deliverables:
  - `packages/multi-workers/mw_common.py` 追加 target-config 节（TargetConfigError/load_target_config/discover_uproject/render_toolchain_command，~230 行）+ 顶部 try-import yaml（PyYAML 缺失时 fail-closed 报错而非 ImportError 崩溃）
  - `packages/multi-workers/test/fixtures/target-config-cases/`（14 个共享 fixture：case.json + target.yml + game/engine/envgame 目录）
  - `packages/multi-workers/test_common_target_config.py`（Py runner + 4 个 Py-only 单测）
  - `packages/coding-agent/test/extensions/agent-team-loop-target-config.test.ts` 追加 TS fixture runner（同一 fixture 集）

## 测试命令与结果

```
# Py 侧（packages/multi-workers）
python -m pytest test_common_target_config.py -v
  5 passed（test_parity_fixtures 覆盖 14 case + 4 个 unit）

# TS 侧（packages/coding-agent）
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-target-config.test.ts
  Test Files 1 passed | Tests 36 passed（20 原有 + 16 fixture runner）

# 回归（packages/multi-workers 全量非 e2e）
python -m pytest -x -q
  379 passed, 8 deselected —— mw_common.py 改动零回归
```

## Parity 锁（T-17 模式）

同一 14 fixture 集（001~014：single 默认/单模式节/dual+engine 渲染/缺 engine/uproject 唯一·0·2/mode 矛盾/dual 缺 game/env 覆盖/env engine 无 game/坏 YAML/engine 无 game/full schema）在两侧各自执行，断言按 **kind + 关键事实**（非消息文案）：

- `[PARITY] target-config cases=14` 两侧均输出
- `[VERIFY] VC-001: mode=single roots-equal=true (case 001)`
- `[VERIFY] VC-006: rendered-contains-engine=true unresolved-placeholders=0 (case 003)`
- `[VERIFY] VC-007: exit-nonzero=true fallback=false (case 004)`
- `[VERIFY] VC-008: uproject-resolved=true ambiguous-fail=true (cases 005/006/007)`

## 实现偏差记录

- fixture 生成脚本初版把 target.yml 写到 case 根而非 `.agenticdoc/`——Py runner 第一跑即抓出（case 002 source=default≠target-yml），移动 12 个文件后两侧全绿
- Py runner `_substitute` 初版无条件 discoverUproject——case 003（无 uproject 场景）抛 ambiguous-uproject，加 `if "{uproject}" in out` guard；TS runner 同步采用该 guard
- normalizeRoot parity：TS `realpathSync.native` ↔ Py `pathlib.Path.resolve()`（Windows 两侧都走 GetFinalPathNameByHandle，canonical case 一致）
- check 链：中间一轮 biome 自动修复 5 个 info（import 排序/格式），终态 `npm run check` exit=0

## 全量检查

`npm run check`（repo 根）：exit 0（biome/pinned-deps/ts-imports/shrinkwrap/install-lock/tsgo/browser-smoke 全绿）
