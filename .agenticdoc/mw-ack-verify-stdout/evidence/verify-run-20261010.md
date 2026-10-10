# Verify run: mw-ack-verify-stdout（2026-10-10）

- Key: mw-ack-verify-stdout
- 变更面：`packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts`（+11 / −1）
- 变更内容：新增 `verify(line: string)` 助手（`process.stdout.write`），把 `[VERIFY] VC-004` 埋点从 `console.log` 切到该助手
- 测试环境：node（本机）+ vitest v4.1.9（输出自带版本行），`packages/coding-agent/vitest.config.ts` → `silent: "passed-only"`

## VC-1（修改前 → 修改后，同一命令）

命令（cwd = `packages/coding-agent`）：

```
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-ack.test.ts
```

| 时刻 | 版本 | 用例结果 | stdout 中 `VC-004` 行数 |
|---|---|---|---|
| 15:25:19 | HEAD（`console.log`） | 5 passed (5) | **0** |
| 15:25:27 | 本次修改（`verify()`） | 5 passed (5) | **1** |

修改前 stdout 抓取（全文）：`evidence/ack-test-stdout-before-20261010.txt`
修改后 stdout 抓取（全文）：`evidence/ack-test-stdout-after-20261010.txt`

修改后真实 stdout 原文（未加工）：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes
·····

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Start at  15:25:27
   Duration  166ms (transform 26ms, setup 0ms, import 35ms, tests 21ms, environment 0ms)
```

修改前同一命令的 stdout 里**没有任何** `VC-004` 行（5/5 全绿但判据行被 vitest 缓冲吞掉）——
这就是负向对照：证明该埋点在 `silent: "passed-only"` 下确实不可达，而不是"本来就该有"。

## AC-1

- 5 个用例全绿、退出码 0（上表、上文原文）。
- 判据行逐字匹配 AC：`[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes`。

## AC-2

- 该文件内 `console.log` 出现次数 = **0**（`Select-String -Pattern 'console\.log' -SimpleMatch`）。
- `npx biome check packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts` → `Checked 1 file in 10ms. No fixes applied.`（0 告警，无需改写）。
- `npm run check`（仓库全量）→ biome `Checked 1105 files … No fixes applied` + pinned-deps / ts-imports / shrinkwrap / install-lock / `tsgo --noEmit`（无输出=无错误）/ browser-smoke 全过。

## 与丢失版本的差异（不作等同比声明）

IN-2 覆盖掉的原始版本在 git 里不可恢复：`git status` 干净、无 stash、无 dangling blob 可对应
（session JSONL 检索命中大量 IN-3 重跑会话，无法唯一定位该次编辑的原文，未继续深挖）。
本条修复是**按记录重推导**：记录要求 = "`console.log` → `process.stdout.write`（+ `verify()` 助手），
保持 agent-team-loop 验证输出契约"（`.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md`
轮次 2 `2026-10-09T12:13:31Z` / 轮次 3 `2026-10-10T03:03:50Z`，原文见
`_incidents/in3-queue-reenqueue-20261010/rewrites-81-20261010.patch`）。
本次改动 +11/−1（丢失版为 8 行改动），行为等价面已由上文 AC-1/VC-1 实证，**不声称字节级复原**。

## 同类残留（本轮范围外，供后续 key 决策）

同一缺陷形态（`console.log("[VERIFY] …")` + `silent: "passed-only"`）在测试树里还有 **37 处 / 8 个文件**：

| 文件 | 处数 |
|---|---|
| `test/extensions/agent-team-loop.test.ts` | 14 |
| `test/extensions/agent-team-loop-target-config.test.ts` | 8 |
| `test/suite/autopilot-read-scope.test.ts` | 5 |
| `test/suite/dual-root-worker.test.ts` | 3 |
| `test/extensions/agent-team-loop-profile-injection.test.ts` | 3 |
| `test/extensions/agent-team-loop-baseline.test.ts` | 2 |
| `test/extensions/agent-team-loop-active-mode.test.ts` | 1 |
| `test/extensions/agent-team-loop-output.test.ts` | 1 |

含义：这些文件里被 worker/PM 当作证据引用的 `[VERIFY]` 行同样到不了真实 stdout。
不在本轮修（用户口径 = 重做丢失的那一处；扩散面另立 key 或并入 `mw-gate-verdict-hardening` 的证据通道议题）。
