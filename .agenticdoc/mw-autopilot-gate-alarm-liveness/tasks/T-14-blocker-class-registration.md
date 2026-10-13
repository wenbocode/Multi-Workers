# T-14 — `blocker_class` 序外标量注册 + fail-closed 五形态

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-007, AC-012
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D6；`spec.md` AC-007/AC-012/§5 坑点 1；
      `evidence/research/design-drq1-field-registration-20261013.md`（**冻结名序 40 名 / 7 代码登记点 / 漏注册后果 / 缺省语义 / 五形态 T-A…T-E**）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（阻塞必须**可分类**：现有 `stalled` 门无法说明"卡在谁手里"，导致无人值守时无法判断该自动放行还是必须等人）。
- 已核实锚点（自行复核）：
  - **冻结名序（40 名）**：`packages/multi-workers/autopilot/gates.py:95-139`；TS 镜像 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:660-701`。
  - **标量先例（不得复用列表机制）**：`gates.py:160 _JSON_LIST_FIELDS`（**这是列表集**）、`:190 _AMBIGUOUS_SCALARS`、`:276 _render_scalar`、`:171 "authorizes"` 的注册先例。
  - **缺省语义**：parser 保留 `None`（`gates.py:546`；TS 侧 `status-model.ts:873`）⇒ 判定层折叠：Python `conductor.py:6083-6091`（`gate_facts` 的 stalled 分支）+ `auto_decision_for_rule:5831`；TS `status-model.ts:1467-1475`（`deriveStatusModel`）。
  - **硬红断言（现值 40）**：`test_autopilot_gates.py:224`、`test_autopilot_gate_schema_v2.py:143`、`test_autopilot_contract_guard.py:187`（三处 `assert len(...) == 40`，**已实测**）、`test/suite/autopilot-gate-presentation.test.ts:227-228` 与 `:253`。
  - **零改动面**：`gates.create()`、`gate-writer.ts`、`contract_guard.py`（本卡不得碰）。
- **漏注册的后果（T-05 已逐条推演，本卡必须避免）**：Python 解析面漏 ⇒ `GateFormatError` ⇒ `enumerate/pending_gates` 整体抛 ⇒ 提醒（`conductor.py:2692-2694`）/阶段跃迁（`:509-512`）/goal-change 闸门（`:2905-2908`）**一起停摆**；TS 面漏 ⇒ `listGates` 剔除 + errors；**monitor `scanPendingGate` 漏 ⇒ 静默消失**。

## 要求

1. **新标量 `blocker_class`（值域封闭）**：`human` / `evidence` / `authorization` / `unknown`（or 等效封闭枚举，须自我一致并写入报告）。**必须新开平行标量集**，**不得**复用 `_JSON_LIST_FIELDS`（列表）语义。
2. **7 个代码登记点全部登记**（Py 4 / TS 3）：在报告中**逐点给出 `path:line`**，并对每点写明"漏了会怎样"（引用上面的后果链）。另加 1 个 materialize 点。
3. **缺省语义（P-03 关键）**：parser 对缺失/空值保留 `None`；**判定层必须把 `None` 折叠为"未分类 ⇒ 不自动放行"**，而不是当作"无阻塞"。即：`blocker_class` 为 `None` 的 gate **不得**被自动 approve；TS `deriveStatusModel` 与 Python `gate_facts`/`auto_decision_for_rule` 折叠方向必须**一致**（给出两侧对照）。
4. **fail-closed 五形态（测试必须覆盖 T-A…T-E）**：
   - T-A：值**格式非法**（如空白/含换行/超长）⇒ 报错或归 `unknown`，**不静默降级为健康**；
   - T-B：值**不在封闭枚举内** ⇒ 同上；
   - T-C：**类型错**（如被写成列表）⇒ 显式失败而非"忽略该字段"；
   - T-D：**旧 v1 gate 缺该字段**（真实存量 51/56 是 v1）⇒ `None` ⇒ 不自动放行，且**不报格式错**（向后兼容可读）；
   - T-E：`blocker_class` 与既有 `stalled` 判定**同时存在**时，不得互相覆盖（给出优先级与理由）。
5. **测试锁更新（这是本卡的写入面，不是放宽）**：三处 `== 40` 断言改为新计数，**必须保留"精确名序"断言**（不得改成 `>= 40` 之类），并在断言旁注明新计数与原因。`autopilot-gate-presentation.test.ts:227-228/:253` 同样处理，且**不得删除既有可见性语义断言**。
6. **不新增 config 键**（AC-011）；`gates.create()` / `gate-writer.ts` / `contract_guard.py` **零改动**；不得改动既有 40 名的相对顺序（新字段只能按设计定好的位置插入，并在报告中说明位置与理由）。

## 写入允许面

- `packages/multi-workers/autopilot/gates.py`
- `packages/multi-workers/autopilot/conductor.py`（仅判定层折叠：`gate_facts` stalled 分支、`auto_decision_for_rule`；**不得动 T-12 stage-close 与 T-15 re-attest 已落区段**）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- **测试锁（必须包含，否则不得改断言）**：`packages/multi-workers/test_autopilot_gates.py`、`test_autopilot_gate_schema_v2.py`、`test_autopilot_contract_guard.py`、`packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts`
- 新增：`packages/multi-workers/test_mwgal_t14_blocker_class.py`、`packages/coding-agent/test/suite/mwgal-t14-blocker-class.test.ts`

## 写入禁止面

- `autopilot/card_audit.py`、`gates.py` 的 `create()` 与既有 40 名相对顺序
- `packages/coding-agent/src/extensions/agent-team-loop/worker/**`、`shared/change-ledger.ts`、`shared/worker-store.ts`（属 T-17b）
- 其他 key 目录、其他项目仓库只读

## 验收命令

Python（从 `packages/multi-workers`）：`python -m pytest test_autopilot_gates.py test_autopilot_gate_schema_v2.py test_autopilot_contract_guard.py test_mwgal_t14_blocker_class.py -q`
TS（从 `packages/coding-agent`）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t14-blocker-class.test.ts test/suite/autopilot-gate-presentation.test.ts`

## 改动历史

（填写：新字段在名序中的位置与理由、7 个登记点的 path:line、五个 fail-closed 形态的实测输出、`None` 折叠的两侧对照、被判为"不得复用列表机制"的理由。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
