# T-03: gate schema v2 字段 + `auto_gate_mode` 配置键

- 波次: **0** · 依赖: 无
- 写面（独占）: 
  - `packages/multi-workers/autopilot/gates.py`
  - `packages/multi-workers/autopilot/config.py`
  - `packages/multi-workers/test_autopilot_gate_schema_v2.py`（新建）
- AC: AC-018, AC-019, AC-026 · VC: VC-011, VC-024, VC-038
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

把 28 个新字段（D6 的 26 + 消费记录 2）以**纯可选、纯追加**方式落进解析器与渲染器，并加入 `auto_gate_mode` 键。老门文件必须照旧解析成功。

## 交付物

- `gates.py:68-81` `FRONTMATTER_FIELDS` 追加 28 名，顺序 = D6 §D1.1 的 1..26（`reason_code` … `gate_schema`）+ `consumed_at` / `consumed_seq`（紧随 `evidence_refs` 组）。
- `_LIST_FIELDS = {"context_refs", "evidence_refs"}`（把 `:354-364` 的单名特判改成集合特判）；其余结构化字段按**单行 JSON 子串**解析（`json-list`/`json-obj`），坏 JSON ⇒ `GateFormatError`（**不是**静默空值）。
- `_REQUIRED_FIELDS`（`:86-89`）**一格不加**（加断言锁住其集合与长度）。
- 渲染器（`:159-200`）对新门写 `gate_schema: 2`；缺省按 1 处理（legacy）。
- `config.py`：`auto_gate_mode`（str，闭集 `off|shadow|live`，默认 `off`，非法值 fail-closed）；**不加入** `EFFECTIVE_KEYS`。

## 契约（不得重定义）

- 不重排底座 12 项；`consumed_at`/`consumed_seq` 由 T-05 写入，本卡只做字段定义与解析。
- 不做历史回填（34 个已答门永保 v1）；`unknown (no field)` 是唯一缺失哨兵。
- 不引入 pyyaml；不依赖 YAML 嵌套（`gates.py:38-45` docstring 是硬约束）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_schema_v2.py test_autopilot_config.py test_autopilot_gates.py -q`

## 非空洞对照（必须附在回执里）

- 用**真实历史门文件**（无任何新字段）做 fixture ⇒ 必须 `parse()` 成功（老文件兼容）。
- 加一行 `bogus_field: x` ⇒ 必须抛 `GateFormatError` 且消息含未知字段名。
- `evidence_refs` 写成坏 JSON ⇒ fail-closed 抛错，**不得**当成空列表。
- 断言 `_REQUIRED_FIELDS` 集合未变（长度与逐项相等）⇒ 若加了字段立刻红。

## 风险与注意

- TS 侧字段镜像在 T-09（同波不同文件）；两侧漏一侧 = 一侧停摆（`gates.py:345-347` / `status-model.ts:660-661`）。
- D6 §D1.5 只列举 `evidence_refs` 为新增具名列表字段；`constraints`/`write_scope`/`out_of_band_actions` 属 P2，本 key 不写，若将来实现按 json-list 表达。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-03-gate-schema-v2/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
