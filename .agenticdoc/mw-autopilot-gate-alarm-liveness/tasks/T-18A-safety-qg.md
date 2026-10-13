# T-18A — 对抗式质量门（安全面分拆：自动放行可否被绕过 / 白名单宽度 / fail-closed）

type: review
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-007, AC-012, AC-013, AC-015（安全面）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md`、`design.md`（D1/D6/D10/D11）、`tasks/T-18-adversarial-qg.md`（原 11 项探针中的安全面子集）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（**能自动放行的门禁不留给人** —— 所以"自动放行是否可能放过本该等人的门"是本 key 最危险的失效模式；比"没放行"危险得多）。
- 审计对象（已冻结基线）与已核实锚点：
  - 自动放行：`packages/multi-workers/autopilot/conductor.py:5742 proposition_stage_close_credentials`、`:5922 STAGE_CLOSE_AUTO_RULE_ID`、`:6292 _stage_close_facts`；回落可见面 `:7193 answer_gate_confirmed`（人工路径对照）。
  - 48h 兜底：`conductor.py` 的 `_process_deferred_reviews`（文档串明写 never closes the stage / never rewrites a key）。
  - fail-closed 标量：`packages/multi-workers/autopilot/gates.py:190 _SCALAR_EXTENSION_FIELDS`、`:197 BLOCKER_CLASSES`；TS `.../autopilot/status-model.ts:167 BOOL_FIELDS`（含 `OPTIONAL_CONFIG_KEYS`）。
  - 回收契约宽度：`.../shared/change-ledger.ts` 的 `isInfrastructurePath` / `INFRA_BASENAMES` / `INFRA_DIR_SEGMENTS`（`["_autopilot", ".mw"]`）与 `unresolvable`；`.../worker/output-writer.ts` 的 `## Ledger Infra` / `## Ledger Unresolvable`。

## 审计目标

对**安全面**做对抗式审计。**零写入**（唯一产物是本目录 `report.md`）。逐条给出：判定（成立 / 部分成立 / 不成立）+ **可独立复现**的证据（`path:line` 或实测输出）+ 反例或缺口。**禁止**只复述文档；**发现缺陷不得修复**，只给最小复现与影响面。

## 要求

1. **`stage-close` 自动放行可否被绕过（最高优先级）**：尝试构造"**证据未齐却被自动 approve**"的反例（五判据：全 key 终态 / 无在飞 / reconciliation 未阻断 / dossier 已写 / 每 key `_done_credentials_present`，逐一尝试绕过：伪造 key 目录、race、dossier 陈旧、空 key、多 stage 交错等）。**必须**单独验证"缺 `l3-verdict.txt`/`l3-report.md` 仍放行"这一现实场景（对应 JCodingAss `gate-0008`）**不可能**发生。给出"已防住 ⇒ 防住它的机制 `path:line`"或"可绕过 ⇒ 最小复现"。
2. **48h 兜底不闭合**：证明 `_process_deferred_reviews` 只升级、**从不**闭合 stage、**从不**重写 key-status；并证明它与 `stage-close` 自动放行**不冲突、不重复**（两条自动路径不得互相触发）。
3. **`blocker_class` fail-closed 五形态**：非法值 / 枚举外 / 类型错 / v1 缺字段（真实存量 51/56 是 v1）/ 与 `stalled` 并存 ⇒ 全部 fail-closed；`None` 是否折叠为"**未分类 ⇒ 不自动放行**"；Python 与 TS 折叠方向是否**一致**；**漏注册**会让哪些面停摆（对照提醒 `conductor.py` 提醒链与阶段跃迁、goal-change 闸门）。
4. **`infra` 白名单宽度（C-37）**：`_autopilot` / `.mw` **整树**豁免是否会掩盖**真实越界写入**（worker 往 `_autopilot/` 树内写）？给出**最小复现**或**不可达证明**（指出拦住它的其它机制与 `path:line`）。同时验证 T-17c 的"**不存在 ⇒ 非写入**"规则**不是**放宽：真实越界文件（存在于磁盘）**仍必须报红**。

## 反例构造要求

至少 **4 条**反例（输入 → 预期 → 实测 → 结论：缺陷或"已防住 + 机制 `path:line`"）。允许"证明不可达"替代实测，但必须给出**完整推理链**。

## 未覆盖面声明

必须显式声明未覆盖的范围（例如：未做真实多进程 race、未在真实陈旧项目上跑、未覆盖 Windows 之外平台、未跑的验收命令等）。

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 逐条对账`、`## 反例与反证`、`## 未覆盖面声明`、`## 上下文来源`。
