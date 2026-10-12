# T-08 — AC-001：`mw doctor` 的 gates 段补 `blocked_on_human`（三轴口径，零写盘）

- key: `mw-dispatch-settle-gates`｜AC: **AC-001**｜VC: **VC-001…VC-003**｜波次 **1**｜独立卡
- 角色: coding（Python 侧）
- **唯一允许改的路径**：① `packages/multi-workers/mw_common.py`；② 新建 `packages/multi-workers/test_mwds_t08_doctor_blocked.py`；③ 自身目录 `report.md`
- 上游：`design.md` DD-10；证据 `evidence/research/design-settle-read-20261010.md`（面板同源量）；`plan.md §6`（`mw_common.py` 被 14 个项目共用）

## 现状（以符号名为准）
- 缺口 G-a：`rg 'blocked_on_human|BLOCKED_ON_HUMAN' packages/multi-workers/mw_common.py` = **0 命中**（面板侧有 10 处）⇒ 上一 key 的 AC-008 只交付了面板半。
- doctor gates 段落点：`_doctor_gates`（约 `:3064` 读 gates 目录、`:3086` 读 entries）；文本告警 `_gates_text_alerted`（约 `:3140-3146`）；`_doctor_issues`（约 `:3295-3305`）；`format_doctor_text`（约 `:3531-3541`）。
- 面板同源量（对齐口径用）：`autopilot/monitor.ts` 约 `:184`（快照 `blockedOnHuman`）、`:364-369`、`:745-753`。

## 必须实现
1. **JSON 契约新增字段**：gates 段加 **`blocked_on_human`（布尔）**（契约 C8，命名逐字）。三轴口径 = **pending 门 > 0** ∧ **该 key 非终态 worker 行 = 0** ∧ **conductor tick 新鲜**（阈值用现有常量，注释写明依据）；任一条不足 ⇒ `false`。
2. **文本渲染**：`blocked_on_human == true` 时在 gates 行追加后缀 **`BLOCKED_ON_HUMAN`**（仅此一处、非零时出现；`false` 时不得出现该串）；不得改动其余行文本（既有 doctor 文本断言不得回归）。
3. **零写盘（硬约束）**：doctor 是只读面，**不得**创建任何文件（不写快照、不写告警状态文件）。**无状态判据**（不引入新的持久化）。
4. **向后兼容**：只新增字段/后缀；不得改既有字段语义与键名；不得向 stdout 打印非 JSON 内容（`--json` 契约）。
5. 三轴口径必须与面板**同一真相源**：能复用 `monitor.ts` 侧口径常量/函数者优先复用等价值（Python 侧无对应则注释指向 `monitor.ts` 行号）。

## 反向用例（必须真跑并贴输出）
- (a) 有 pending 门 + 无非终态行 + tick 新鲜 ⇒ `blocked_on_human=true` 且文本含后缀；(b) `blocked_on_human=false` ⇒ 文本**无** `BLOCKED_ON_HUMAN`；(c) 非终态行 > 0 ⇒ `false`（哪怕有 pending 门）；(d) tick 陈旧 ⇒ `false`；(e) 没有 pending 门 ⇒ `false`；(f) **零写盘**：运行前后目录树 sha256 集合完全一致（含 `.agenticdoc/_autopilot/`）。

## 对照协议（`plan.md §5`）
A 摘除三轴判定的其一（如只看 pending 门）⇒ (c)/(d) 转红；B 反转默认（恒 true）⇒ (b)/(e) 转红；C 让 doctor 写一个快照文件 ⇒ (f) 转红。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-001: field=blocked_on_human three_axis=true json_rc=0
[VERIFY] VC-002: true_suffix=BLOCKED_ON_HUMAN false_suffix_count=0
[VERIFY] VC-003: files_created=0 tree_hash_equal=true
```
命令：`python -X utf8 -m pytest packages/multi-workers/test_mwds_t08_doctor_blocked.py -q`（贴输出）

## 禁止
不改 `autopilot/monitor.ts`（面板已交付，勿动）；不改 `launcher.py` / `autopilot/*.py`；不改 `test_common.py`；不重启任何进程；不 build；不 commit；不得在 doctor 路径写文件。
