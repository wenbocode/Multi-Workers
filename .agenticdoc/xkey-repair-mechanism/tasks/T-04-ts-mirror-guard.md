# T-04 TS 镜像 + gate 目录写拦截（W4 单写者）

key: `xkey-repair-mechanism` · 依赖: 冻结契约（kind 名 `xkey-authorize`） · 覆盖: VC-004

## 目标（两件，同一卡）

### (1) gate kind 闭集镜像（D-009）

- Python 侧：`packages/multi-workers/autopilot/gates.py:52` `GATE_KINDS` 加入 `"xkey-authorize"`。
- TS 侧：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:467` `export const GATE_KINDS = ["stage-confirm","stage-close","stalled","budget-exhausted","goal-change"] as const;` 同步加入 `"xkey-authorize"`。
- 闭合性：`:595` 的 `includes(kind)` 校验与放行路径（`:217/:407/:595` 附近）应自动覆盖；逐条确认无其它 kind 白名单遗漏（全仓搜 `stage-confirm` 找硬编码列表）。
- 部署顺序（写进报告）：旧 TS 窗口遇未知 kind 仅降级显示（`status-model.ts:663-666` 附近逐文件 catch；monitor 不校验 kind），**但旧 Python conductor 会因 `GateFormatError` 每 tick skip** ⇒ conductor 必须与 kind 同版本上线。

### (2) gate 目录写拦截（D-008 的"可观测拒绝"落点）

新建 `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`，**形状镜像** `shared/protected-config.ts`（纯判定函数 + `registerXxxGuard(pi)`）：

- `pi.on("tool_call", ...)`：对 `write` / `edit` / `bash` 三类调用，若目标路径（或 bash 命令串中的路径）落在 **gate 目录** `<project>/.agenticdoc/_autopilot/gates/` 前缀内 ⇒ **硬拦截**（fail-closed，与 protected-config 同样：相对 cwd 与 `~` 展开均须覆盖），并留可观测记录（可复用 protected-config 的提示语风格）。
- **只拦 gate 目录**：`.agenticdoc/_autopilot/xkey/evidence/**`（提案/验证产物，worker 必须可写）与 `xkey/ledger.json`、`xkey/tickets/**` **一律放行**（design D-005/D-004：worker 只产提案；ledger/tickets 由 conductor 写，但本卡不拦它们——避免误伤提案路径。报告须写明该边界是有意为之）。
- 注册点：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:41` `registerProtectedConfigGuard(pi);` 旁（并遵守该文件 `:49` 注释的 "EVERY mode, same position" 约束——worker 窗口也必须生效）。

## 验收

- `npm run check`（全量输出，不 tail）本次改动相关包干净。
- 该扩展既有 guard 测试全绿（找 protected-config / implementation-gate 相关测试跑一遍，报告给出命令与结果）。
- 手动/单测证明：构造一次 `write` 到 `.agenticdoc/_autopilot/gates/x.md` ⇒ 被拦（gate 目录文件 sha 不变）；一次 `write` 到 `.agenticdoc/_autopilot/xkey/evidence/r1/proposal.md` ⇒ 放行。

## 纪律

- **只写**：`gates.py:52`（1 行）、`status-model.ts:467`（1 行）、新文件 `shared/xkey-gate-guard.ts`、`index.ts`（注册 2-3 行 + import）。
- 不改 `protected-config.ts`（只参照其形状）；不改其它扩展；不跑 `npm run build`/`npm test`；不 commit。
- 报告须含：`git diff --stat`、`npm run check` 输出（完整）、拦截/放行两个方向的手动证据。
