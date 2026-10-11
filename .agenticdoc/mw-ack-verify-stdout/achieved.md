# Achieved: mw-ack-verify-stdout

- Key: mw-ack-verify-stdout
- 型态：trivial-fix fast path（单文件 / 单调用点，PM 直执，未派 worker）
- 结案：2026-10-11（本地 UTC+8）
- 来源：IN-2 覆盖式丢失中被抹掉的 ack 测试修复（重推导，非字节级复原）

## 交付物

`packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts`（+11 / −1，commit `1a2144163`）：
把 `[VERIFY] VC-004` 埋点从 `console.log` 切到直写 stdout 的 `verify()` 助手
（`process.stdout.write(\`${line}\n\`)`），使该机器判据行在 vitest `silent: "passed-only"` 下仍到达真实 stdout。

## 系统行为变化

- **产品代码：无变化**。`ack-store.ts` 等生产代码未触碰。
- **测试侧可观测性（新增能力）**：`agent-team-loop-ack` 用例的验证通道恢复——在默认 vitest 配置下，
  真实 stdout 现在包含 `[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes`。
  此前 5/5 全绿但 stdout 无该行（`console.log` 被 `silent: "passed-only"` 缓冲吞掉），
  即"用例通过"与"验证通道有证据"当时是脱钩的。
- **影响面**：仅该测试文件；不进 dist（测试文件不打包）；不改 CHANGELOG（无用户可见行为）。
  对下游的直接影响：任何 grep `[VERIFY] VC-004` 作为证据的流程重新可用。

## 验收与证据

| 项 | 判据 | 证据 |
|---|---|---|
| AC-1 | 默认配置下 stdout 含 VC-004 行、5/5 绿、退出码 0 | `evidence/qg-target-test-20261011.txt`（17:42 复跑）、`evidence/ack-test-stdout-after-20261010.txt` |
| AC-2 | 文件内 `console.log` = 0；biome 0 告警；`tsgo --noEmit` 无本文件告警 | `evidence/verify-run-20261010.md`；HEAD 版复核 `console.log` 计数 = 0 |
| VC-1 | 改前 0 行 / 改后 1 行（负向对照 + 正向实测，两次原始输出存档） | `evidence/ack-test-stdout-before-20261010.txt` / `-after-20261010.txt` |
| 质检 | 收口前二次核查（4/4 充分） | `evidence/quality-gate-report-20261011.md` |

## 提交

- `1a2144163` fix(coding-agent): write the ack [VERIFY] marker straight to stdout（本 key 的实现）
- `1550fc310` docs(agentic): 登记本 key 与证据（`.agenticdoc/`）
- `776b82d7f` chore: ignore the local .tmp scratch dir（用户附带项，同批）
- 工作树状态：`git status --porcelain` 对该测试文件为空（已入库、无残留修改）。

## 遗留

1. **同类埋点 37 处 / 8 个文件**未修（`agent-team-loop.test.ts` 14、`-target-config.test.ts` 8、
   `autopilot-read-scope.test.ts` 5、`dual-root-worker.test.ts` 3、`-profile-injection.test.ts` 3、
   `-baseline.test.ts` 2、`-active-mode.test.ts` 1、`-output.test.ts` 1；明细见
   `evidence/verify-run-20261010.md`）→ **去向：另立 key 或并入 `mw-gate-verdict-hardening` 的证据通道议题**。
   本 key 明确不做（D-002：不扩散到跨 key 写面）。
2. **字节级复原不可得**：原丢失版本在 git 中无痕（无 stash / 无 dangling blob；JSONL 检索无法唯一定位）
   → **去向：接受**。已声明为"按记录重推导"，行为等价由 AC-1/VC-1 实测支撑，不声称等同。
3. **`mw-widget-terminal-lifecycle` 的 AC-004 / VC-004 归属不变**（本 key 只恢复其验证通道）
   → **去向：无需动作**。
4. `pm-state.md` 曾缺 `- Phase:` 接口行（模板漂移，2026-10-11 收口时修复）
   → **去向：记入本行，防同类漂移复发**（下次建 mini-spec key 应直接采用框架模板的 Snapshot 段）。
