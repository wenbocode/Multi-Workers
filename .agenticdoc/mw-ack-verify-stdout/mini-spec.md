# mini-spec: mw-ack-verify-stdout

> Key: mw-ack-verify-stdout
> 建立: 2026-10-10（用户指令：“要重做”，指 IN-2 覆盖式丢失中被抹掉的 ack 测试修复）
> 型态：trivial-fix fast path（单文件、单调用点、无 dist/changelog 影响）

## 目标

恢复并固化 `test/extensions/agent-team-loop-ack.test.ts` 里那条被 IN-2 批量 `git checkout --` 覆盖掉的修复：
把 `[VERIFY] VC-004` 埋点从 `console.log` 改为直写 stdout，使该机器判据行在 `vitest` 的
`silent: "passed-only"` 下仍能到达真实 stdout（否则通过用例的 console 输出被 vitest 缓冲吞掉，
验证通道 grep 不到证据行）。

## 依据（丢失前的记录，重跑稿已整体回退，全文见 patch）

- `.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md` 轮次 2（2026-10-09T12:13:31Z）与轮次 3（2026-10-10T03:03:50Z）：
  “受 vitest `silent:"passed-only"` 影响，原用例的 `console.log` 在静默时段被吞；改为 `process.stdout.write`（+ `verify()` 助手），
  保持 agent-team-loop 验证输出契约”；轮次 3 记录复验发现 HEAD 版本埋点回退为 `console.log`（round 2 修正未提交），再次替换。
- 该记录的原文保存在 `.agenticdoc/_incidents/in3-queue-reenqueue-20261010/rewrites-81-20261010.patch`（已按用户指令不入库）。
- 配置实测：`packages/coding-agent/vitest.config.ts` → `silent: "passed-only"`。

## 范围

- 做：`packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts` 的埋点通道（单文件）。
- 不做：其余 10 个测试文件里的约 40 处同类 `console.log("[VERIFY] ...")` 埋点（本轮不扩散，仅在证据里枚举，作为后续 key 的输入）。
- 不做：`ack-store.ts` 生产代码（与该修复无关，HEAD 未改动）。
- 不做：dist 重建（测试文件不进 dist）、CHANGELOG（测试侧可观测性修复，无用户可见行为变化）。

## 验收（AC / VC）

| 编号 | 判据 |
|---|---|
| AC-1 | 在 `vitest` 默认配置（`silent: "passed-only"`）下运行 `test/extensions/agent-team-loop-ack.test.ts`，**真实 stdout** 包含 `[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes`，且命令退出码 0、5 个用例全绿 |
| AC-2 | 该文件的埋点不再走 `console`（`console.log` 调用数 = 0），改为直写 stdout 的 `verify()` 助手；`biome check` 对该文件 0 告警，`tsgo --noEmit` 无本文件告警 |
| VC-1 | 修改前后的同一命令 stdout 对比：改前无 `VC-004` 行、改后有（负向对照 + 正向实测，两次原始输出均存档） |

## 证据

- `evidence/verify-run-20261010.md`：两次原始命令、完整 stdout 抓取、marker 计数、5/5 结果。
- 枚举面：同类埋点异常清单（文件 + 行号 + 计数）。

## 完成判据

AC-1/AC-2/VC-1 三项均有原始命令输出为证；不留未提交的中间态（是否提交由用户决定）。
