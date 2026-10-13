# T-22 — 修 QG 缺陷（Python 面）：R-4 路径为文件折叠为空 / R-5 外机合成 claim

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-003, AC-014
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/report.md`（**R-4 / R-5**，含最小复现与 `path:line`）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（**阻塞必须可见**：读不到队列不得表现为"没有队列"；**派发不得以人工接管为前置，但人工优先且跨主机不得双重持有**）。
- QG 判定（`workers/mwgal-t18-adversarial-qg/report.md`）：
  - **R-4（低）**：当 `.agenticdoc/_autopilot/gates` 这个**路径是普通文件**时，Python 侧（`autopilot/gates.py` 的 `enumerate` / conductor 读路径）把它**折叠为空队列**（TS monitor 面对同一对抗输入会判 unreadable）⇒ 两面不一致，且属于"静默 0 pending"家族。
  - **R-5（设计分歧，中）**：**Python conductor 会接管"外机"合成 claim**（`parseClaim("autopilot@OTHER:host")` ⇒ 可让位/可回收），而 TS 面 `claimState` **仅在 `synthetic.host === os.hostname()`** 时才判 `held-conductor`（**不放宽**）⇒ 跨语言行为分歧，风险是**跨主机双重持有**。
- 已落基线（不得回退）：T-16 的合成 claim 生命周期（`conductor.py:225 SYNTHETIC_CLAIM_HEARTBEAT_SEC`、`:236 synthetic_claim_owner`、`:263 _synthetic_claim_stale`），身份回收**只用** host/pid/`serve.meta`（无 TTL）；T-16b 的人工优先让位（`pm/ui-bridge.ts:251 ClaimState`）与 T-16c 的留痕（`pm-orchestrator.ts:319 tookOverFromConductor`）；T-12 的 `stage-close` 自动放行与 T-15 的 re-attest（不得触碰其区段）。

## 要求

1. **R-4：读不到就是读不到**
   - `gates` 路径为**普通文件**、或目录存在但读取失败（非 ENOENT）时，Python 面必须与 TS monitor **同判 unreadable**，并至少留一条**可见**记录（复用既有事件名/timeline `config`，不新造）；**不得**折叠为空队列。
   - 必须区分三种情形：① 目录不存在（合法：0 pending）；② 目录存在且为空（合法：0 pending）；③ 不可读 / 路径类型错（**unreadable，必须可见**）。
2. **R-5：跨主机不双重持有（与 TS 对齐）**
   - 只有**本机**（同 host，且 pid/`serve.meta` 身份一致）的合成 claim 才可被本机 conductor 让位/回收；**外机**合成 claim 必须按"**有 live 持有者**"处理（不得接管）。
   - 给出明确的判定规则与两侧一致性证据（Python 与 TS 判定表逐项对照）。
   - 若你认为 Python 现有行为才是对的（即应接管外机 dead serve 的合成 claim），**不要直接改**：在报告中给出**论证 + 反例分析**（何时会双重持有、何时只有 Python 能修活），留给 PM 裁定 —— 但**默认执行对齐**。
3. **不得回退**：T-16/T-16b/T-16c/T-12/T-15 的既有行为与测试必须保持绿；不得引入 TTL/退避曲线（D-013 明确否决）；不得新增 config 键。
4. **回归测试（必须内建）**：① `gates` 为文件 ⇒ unreadable 且可见；② 目录不存在/为空 ⇒ 合法 0 pending（不得误报）；③ 外机合成 claim ⇒ **不接管**；④ 本机合成 claim ⇒ 仍可让位/回收（T-16 语料绿）；⑤ 判定表两侧一致。

## 写入允许面

- `packages/multi-workers/autopilot/gates.py`
- `packages/multi-workers/autopilot/conductor.py`（仅读路径判定与合成 claim 归属；**不得动 T-12/T-15 已落区段**）
- `packages/multi-workers/mw_common.py`（claim 解析/归属）
- `packages/multi-workers/mw.py`（仅当 doctor/status 需要一致判定）
- 新增：`packages/multi-workers/test_mwgal_t22_qg_fixes.py`
- 既有 Python 测试中因本卡行为必须更新的期望（逐条说明；不得改弱断言）

## 写入禁止面

- `packages/coding-agent/**`（T-21 正在改 TS 面）
- `autopilot/contract_guard.py`、`autopilot/card_audit.py`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/multi-workers`：
`python -m pytest test_mwgal_t22_qg_fixes.py test_mwgal_t16_synthetic_claim.py test_mwgal_t15_reattest_confirm.py test_mwgal_t12_stage_close_auto.py -q`

## 改动历史

（填写：三情形判定落点、与 TS 判定表的逐项对照、外机合成 claim 的处理规则与理由、被否决方案（TTL/退避）为何不采用。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
