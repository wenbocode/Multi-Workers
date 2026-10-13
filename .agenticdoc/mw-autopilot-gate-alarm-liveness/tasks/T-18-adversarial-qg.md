# T-18 — 对抗式质量门（逐条 AC 对账 + 反例构造 + 运行期证据）

type: review
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: 全量 AC-001…AC-016（审计而非实现）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`（E1–E10 / AC-001…AC-016 / §5 坑点）、`design.md`（D1–D10）、`plan.md`（5 批计划 + 收口判据）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守时阻塞必须可见；派发不得以“有人 watch/接管”为前置；能自动放行的门禁不留给人）。
- **审计对象（已冻结的基线）**：本 key 已落的全部实现（实现卡已全部终态）。可直接使用的已核实锚点：
  - `packages/multi-workers/autopilot/conductor.py:5742 proposition_stage_close_credentials`、`:5922 STAGE_CLOSE_AUTO_RULE_ID`、`:6292 _stage_close_facts`、`:3880 reattest_gate`、`:3933 _apply_reattests`、`:7193 answer_gate_confirmed`、`:225 SYNTHETIC_CLAIM_HEARTBEAT_SEC`、`:236 synthetic_claim_owner`、`:263 _synthetic_claim_stale`；
  - `packages/multi-workers/autopilot/gates.py:190 _SCALAR_EXTENSION_FIELDS`、`:197 BLOCKER_CLASSES`；
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:167 BOOL_FIELDS`（含 `OPTIONAL_CONFIG_KEYS`）、`autopilot/monitor.ts`（`~D`/`R:*`/`J`/`P` 与 fit ladder）；
  - `.../shared/change-ledger.ts:804 unresolvable`、`.../worker/output-writer.ts:76 unresolvableFiles`、`.../pm/ui-bridge.ts:251 ClaimState`、`.../pm/pm-orchestrator.ts:319 tookOverFromConductor`。
- 已登记的过程发现（审计时应特别核验是否真的修好）：C-36 六子类（过判 / taskDir 外漏计 / 路径污染 / 系统写入误归因 / 幽灵文件名 / 代码标识符）；上一 key `b65380d1b` 新增配置键未同步 TS 注册表**与放行集合**。

## 要求

对 **`mw-autopilot-gate-alarm-liveness` 本 key 已落的全部实现**做对抗式审计。**零写入**：只读代码/测试/运行期状态，唯一产物是本 worker 目录下的 `report.md`。

**核心命题（本 key 的三条第一性目标）**：① 无人值守时**阻塞必须可见**；② **派发不得以"有人 watch/接管"为前置**；③ **能自动放行的门禁不留给人**。审计必须回答：**这三条在什么情况下仍会失效**。

**必做对账**：逐条给出 `AC-NNN → 判定（成立 / 部分成立 / 不成立）→ 证据（`path:line` 或可复现实测输出）→ 反例或缺口`。**禁止**只复述文档；每条判定必须有**可独立复现**的证据。

## 必须覆盖的 10 项对抗探针

1. **`infra` 白名单宽度（C-37，最高优先级）**：`shared/change-ledger.ts` 现在把 `_autopilot` / `.mw` 整树 path 豁免出 `extra`（`isInfrastructurePath:298`）。请构造反例：**worker 往 `_autopilot/` 树内写入**是否因此不再被判为未记录写入？若可构造，给出最小复现；若不可达，给出**证明**（指出拦住它的其它机制与 `path:line`）。
2. **"无静默丢弃"**：`_workers.parallel`/队列**不可读**时，三面（Python conductor / monitor `scanPendingGate` / TS `status-model`）是否仍可能显示"0 pending"？给出三面实测。
3. **抑制留痕与重启后可见**：被抑制的 gate 是否在 timeline 留下 `remind-suppressed`（含 reason/bucket）？**serve 重启后**该事实是否仍可查（对照 ledger 的 `gate_file_sha256_before/after`）？给出实测。
4. **漂移自证**：活 serve 是否被判 `STALE CODE`（新入口 `mw status` / `mw doctor`）；**commit 不等但 digest 相等**时是否为 `history-only`（不告警，D-009）；**短 OID 是否被误用于相等判定**。
5. **`stage-close` 自动放行安全性（D-011/D-014）**：能否构造"**证据未齐却被自动 approve**"的反例（五判据之一被绕过）？能否构造"**缺 `l3-verdict.txt`/`l3-report.md` 却仍放行**"的反例？复核回落是否**点名缺失项**。
6. **48h 兜底不闭合**：`_process_deferred_reviews` 是否**确实**只升级、从不闭合 stage、从不重写 key-status（给出源码证据 + 测试证据）；是否与 `stage-close` 自动放行**冲突或重复**。
7. **re-attest**：编号是否**绝不复用**；原 gate 判定是否**字节不变**；证据刷新后是否**真的可重评**（不继承旧判定）；destructive reject 未确认时是否**零写盘**。
8. **`blocker_class` fail-closed**：五形态（非法值 / 枚举外 / 类型错 / v1 缺字段 / 与 `stalled` 并存）是否**全部 fail-closed**；`None` 是否被折叠为"**未分类 ⇒ 不自动放行**"（而非"无阻塞"）；Python 与 TS 折叠方向是否**一致**；**漏注册点**会导致什么（对照 `conductor.py:2692-2694` 提醒 / `:509-512` 阶段跃迁 / `:2905-2908` goal-change 闸门 的停摆面）。
9. **合成 claim（若本轮已落）**：人工 `switch_key` 是否**优先且不被抢回**；serve pid 变后旧合成 claim 是否**失效**；idle 无产物 key 是否**仍被跳过**（不误接管）；是否引入了**第二个 claim 写者**。
10. **AC 覆盖缺口清单**：16 条 AC 中哪些**没有对应的可复现实测**（只有文档声明）；哪些实现**没有负例测试**。
11. **人工优先级与可见性的端到端（`held-conductor` 面）**：① 本机 conductor 合成 claim 存在时，人工非强制接管是否**真的成功且不被抢回**；② **外机**合成 claim 是否**仍按 `held-live` 处理**（不得被顺手放宽）；③ **`pm/pm-orchestrator.ts::restoreWatch`** 在窗口重启时是否会**静默认领**被 conductor 接管的 key（T-16b 自报该副作用方向正确但无痕迹）——若会，判定它是否违反 AC-001/AC-002 的可见性要求；④ 跨 key 守卫与 owner 解析对合成 claim 是否**行为不变**（T-16b 声称未放宽，须独立验证）。

## 反例构造要求

至少给出 **5 条**对抗用例（可以是"我用 X 输入跑 Y 得到 Z"这种运行期复现，也可以是可判定为不可达的证明）。每条必须：输入 → 预期（按本 key 的 AC）→ 实测 → 结论（缺陷 / 已防住 + 防住它的机制 `path:line`）。**发现缺陷不得修复**（本卡零写入），只需给出最小复现与影响面。

## 未覆盖面声明

必须显式声明本卡**未覆盖**的范围（例如：未在真实多项目并发下长跑、未验证 TS 侧 console 交互路径、未覆盖 Windows 之外的平台、未跑的验收命令等）。

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 逐条 AC 对账`、`## 反例与反证`、`## 运行期证据`、`## 未覆盖面声明`、`## 上下文来源`。
