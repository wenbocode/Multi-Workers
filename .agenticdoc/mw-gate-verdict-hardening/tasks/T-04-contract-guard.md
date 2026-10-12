# T-04: G3 授权字段 + `contract_guard` 新模块

- 波次: **0** · 依赖: —
- 写面（独占）:
  - `packages/multi-workers/autopilot/gates.py`（允许集段 `:87-165`）
  - `packages/multi-workers/autopilot/contract_guard.py`（**新建**）
- AC: AC-009, AC-011, AC-013 · VC: VC-012, VC-015
- 基线: `10446aefb`

## 目标

把"授权范围"从闸门**自由文本**变成机器字段（闭集），并提供一个**纯函数**的 AC/VC 文本身份锚 + 授权查找，供 `T-10`（conductor done 前检查）与 `T-11`（CLI/doctor）复用。**判定逻辑只写一遍**。

## 交付物

- `gates.py`：`authorizes` 加入 `_JSON_LIST_FIELDS`（单行 JSON 数组）；**不新增 schema v3**、**不动** `_REQUIRED_FIELDS`（6 格）。
- 闭集：`{retry, contract-change}`（**`install` 排除**，无机器消费者）。越界成员 ⇒ 解析期拒（fail-closed）。
- 空数组 = 未授权（显式"本次没授权任何动作"，与"缺字段"同判为未授权）。
- `contract_guard.py`（新模块，**零 IO 副作用**、root 由调用方注入）：
  1. AC 行解析：正则 `^\|\s*(AC-\d{3})\s*\|\s*(.*?)\s*\|\s*$`（逐行扫描 `spec.md` 的 AC 表）。
  2. VC 块解析：复用 `.tmp/msc-gen-evidence-req.py:parse_vcs` 的正则形状（**照抄语义、不照抄路径依赖**）。
  3. canonical sha：对 `{ac_id: ac_text}` 与 `{vc_id: vc_text}` 各自排序后做稳定序列化再 sha256。
  4. freeze sidecar 读写：`<key>/evidence/contract-freeze.json`（形状见 design §2；`closure` marker 同族命名）。
  5. 授权查找：`status == "approved"` ∧ `authorizes ∋ "contract-change"` ∧ `gate.key == key`；**不绑定 kind**；**不读** `gate.note` / `answered_by`。
  6. 变更检测：当前文本 vs freeze ⇒ 变更 AC/VC id 集合。

## 契约（不得重定义）

- **不得**用 `subject_sha256`（无生产写入者，死路）、**不得**用 `git diff`（fail-open：`advance done` 早于 commit）。
- **不得**让 `gates.create()` 渲染 `authorizes`：物化由 `T-10` 的 `_stamp_gate_defaults` 负责，否则破 `test_autopilot_gates.py:216-227` 的"新建门恰好 13 键"锁。
- 模块内不得 `import` conductor（避免循环依赖）；不得有模块级文件读写。
- 无 freeze sidecar ⇒ 返回"无身份锚"而非抛异常（零扰动由 `T-11` 负责表现）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gates.py test_autopilot_gate_schema_v2.py -q`
- `cd packages/multi-workers && python -X utf8 -c "from autopilot import gates, contract_guard; assert 'authorizes' in gates._JSON_LIST_FIELDS; assert gates._REQUIRED_FIELDS.__len__()==6; print('ok')"`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_contract_guard.py -q`（本卡自带的最小用例；完整 10 例见 T-11）

## 非空洞对照（必须附在回执里）

- 把 `authorizes` 从 `_JSON_LIST_FIELDS` 摘掉 ⇒ 数组值必须解析失败（VC-012 转红）。
- 把闭集放宽成任意字符串 ⇒ 越界成员 `install`/`whatever` 必须被接受（VC-012 转红）。
- 只引用 `gate.note` 散文做授权源 ⇒ 授权查找必须返回 false（VC-015 转红）。

## 风险与注意

- `gates.py` 的允许集顺序是两侧 parity 的锁对象：本卡**只在尾部追加**一个名字，不重排、不改既有成员。
- `contract_guard.py` 是本 key 唯一新模块，命名与 `autopilot/` 既有模块风格一致（小写 + 下划线）。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-04-contract-guard/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。


## PM 追记（2026-10-10 20:35，派发后）

- worker 报备 **R1**：design D-011 原写“`authorizes` 追加到 `FRONTMATTER_FIELDS`（索引 40）”，但这会同时打红两处**无人认领**的锁（`test_autopilot_gates.py:224` == 40；TS 跨语言 parity `autopilot-gate-presentation.test.ts:206-235`）。
- **PM 裁决：接受偏离**（判据：解析面成员校验 `gates.py:507` 已接受 `_JSON_LIST_FIELDS` 名；渲染路径 `_gate_file_content`（`gates.py:283`）是手写字面量、不遍历该名单 ⇒ 无“重渲染丢字段”路径；40 名顺序保持冻结反而免掉了 T-14 的两处锁刷新）。design D-011 已打 `[REVISED @ 2026-10-10 20:35]` 并附完整理由。
- **连带硬要求（已写入 T-12 卡）**：TS 侧必须镜像同一形状（`GATE_JSON_LIST_FIELDS` 加 `authorizes` + 未知字段检查放宽 + 闭集校验），否则出现“Python 可解析、TS 面板跳过”的新双语言分叉。
- PM 独立复核：`authorizes ∈ gates._JSON_LIST_FIELDS` ✓、`len(_REQUIRED_FIELDS) == 6` ✓、`AUTHORIZES_ACTIONS == {contract-change, retry}` ✓、`test_autopilot_gates.py + test_autopilot_gate_schema_v2.py + test_autopilot_contract_guard.py` = **80 passed** ✓、`contract_guard.py` 37 个公开符号。
