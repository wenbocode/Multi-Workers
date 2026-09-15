# 全量回归记录 — mw-widget-terminal-lifecycle T-09（2026-09-10）

## 1. 本 key 文件域（全绿）

| 套件 | 命令 | 结果 | 埋点 |
|------|------|------|------|
| TS 扩展三文件 | `node ../../node_modules/vitest/dist/cli.js --run test/extensions/`（packages/coding-agent） | **119 passed**（agent-team-loop 106 + ack 5 + output 8） | VC-001/002/003/004/005/006/007/008/009/010/011 全部输出 |
| Python 全量 | `python -m pytest -q`（packages/multi-workers） | **358 passed, 6 deselected**（e2e 按配置排除） | VC-009/012/013 输出（test_launcher + test_common） |
| biome | `npx biome check --write <本 key 文件>` | 零告警（修复 3 文件格式后） | — |
| tsgo（本 key 域） | `npx tsgo --noEmit` | 本 key 文件零错误（全部 26 错误在 packages/ai，预存） | — |

## 2. VC 勾销（对照 evidence-requirement.md，13/13）

| VC | 验证方式 | 证据 |
|----|---------|------|
| VC-001 | L1 renderWatchLines 三区用例 | agent-team-loop.test.ts「watch widget sections」+ `[VERIFY] VC-001: live_rows=5/5, fold=history_only` |
| VC-002 | L1 ack 前后分区对比 | 同上 + `[VERIFY] VC-002: unhandled_persist=8/8, after_ack=0` |
| VC-003 | L1 折叠与排序 | 同上 + `[VERIFY] VC-003: history_cap=5, more=+2, order=newest_first` |
| VC-004 | L1 AckStore 往返/幂等/持久化 + 命令通道 | agent-team-loop-ack.test.ts 5 用例 + 「ack channels」用例 + `[VERIFY] VC-004`（存储半+通道半）；bundle 冒烟实录 ack 落盘 |
| VC-005 | L1 PM-only 注册 + 工具等效 | `[VERIFY] VC-005: tool_registered=yes, worker_mode_absent=yes`（workerModeActivate 零工具注册实证） |
| VC-006 | L1 队列快照不变 + dispatchNewTasks 无重派 | `[VERIFY] VC-006: status_unchanged=yes, no_redispatch=yes` |
| VC-007 | L1 failed detail 回退链 + 无标记 | `[VERIFY] VC-007: exit_reason=yes, marker_strip=yes` |
| VC-008 | L1 nc detail 回退链 + size guard | `[VERIFY] VC-008: questions=yes, log_tail=yes, hint=yes, size_guard=yes` |
| VC-009 | L1 TL;DR 写入 + 展示回退 + starter 指令 | agent-team-loop-output.test.ts 8 用例 + `[VERIFY] VC-009`（tldr/headline/steer/starter 四处埋点） |
| VC-010 | L0 PM_CONTINUE_HINT 含 ack 指示 | `[VERIFY] VC-010: hint=ack_worker_result-present` |
| VC-011 | L1 list_tasks 徽标 | `[VERIFY] VC-011: badge=acked-present` + bundle 冒烟实录（wtl-t03/t04 带 acked，其余不带） |
| VC-012 | L1 reconcile 三映射 + own 行不动 | test_launcher.py「reconcile」组 + `[VERIFY] VC-012: map=0-done,1-failed,2-nc, own_row=untouched` |
| VC-013 | L1 静默窗口 + beat 退让 | 同上 + `[VERIFY] VC-013: silence_failed=1, fresh_untouched=1, beat_guard=skipped` |

## 3. bundle 重建 + 生产冒烟（安装产物，非源码）

- `python packages/multi-workers/mw.py build --install` → built + self-check OK，全局安装至 `~/.pi/agent/extensions/agent-team-loop.js`
- mw serve 重启（旧 57036 → 新 89364）：新 launcher 生效，`.mw/launcher-beat.77900` beat 文件出现（D-008 生产实证）
- bundle 级冒烟（`tmp/bundle-smoke.mjs`，已删除）：activate → `/mw ack nonexist` 拒绝提示 ✓；`/mw ack wtl-t04-starter` ack 落盘 ✓；`ack_worker_result` 工具等效 ✓；`list_tasks` 徽标 ✓
- TUI widget 渲染：106 个 renderWatchLines 单测覆盖；真实窗口需重启 pi 加载新 bundle 后生效

## 4. 预存基线漂移（非本 key 引入，记录备查）

| 域 | 现象 | 证据 |
|----|------|------|
| packages/ai tsgo | 26 个类型错误（过时 model ID / ProviderStreams 类型面 / TS1294 非可擦语法） | `npx tsgo --noEmit`；git status 干净（已提交 HEAD 即红）；`npm run generate-models` 重生成后内容零变化（排除生成文件过期） |
| packages/ai 运行时 | 全量 8 个测试失败（model registry 漂移，与 tsgo 同根因） | `bash test.sh` 输出 |
| packages/agent | 2 个失败（TMPDIR POSIX 路径断言 vs Windows） | 同上 |
| packages/coding-agent core | 85 失败 / 1943 过（agent-session 超时、config 自更新命令解析、extensions-runner 等 Windows 环境签名）；**agent-team-loop 域零失败**，25 个失败文件零 import 本 key 模块 | `npm test`（packages/coding-agent）+ grep 交叉验证 |

处置：按预先约定（剩余 >5 → 拆独立 key），建议拆 `ai-baseline-repair` 类 key 处理；本 key 的 npm run check 记录为「biome/pinned-deps/ts-imports/shrinkwrap 全过，tsgo 阻塞于预存 packages/ai 26 错误」。

## 5. 环境副作用记录

- 冒烟 ack 了 `wtl-t04-starter` 与 `wtl-t03-tldr`（真实 `_workers.acked`）——done 行，仅影响展示分区，保留为演示态
- mw serve 由 57036 重启为 89364（重启前确认队列零在飞行）
- pytest.ini 的 e2e_l2 marker 改动属 goal-autopilot 会话未提交工作，本 key 未触碰
