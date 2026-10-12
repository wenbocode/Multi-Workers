# T-11 — AC-008：上一 key 文档勘误（6 处，纯文档，不改码）

- key: `mw-dispatch-settle-gates`｜AC: **AC-008**｜VC: **VC-034…VC-039**｜波次 **2**｜独立卡
- 角色: coding（需要 write/edit 改文档）
- **唯一允许改的路径**：`.agenticdoc/mw-gate-verdict-hardening/` 下的 **`spec.md` / `plan.md` / `design.md` / `pm-state.md` / `evidence-requirement.md`（新建） / `tasks/T-18-*.md`、`tasks/T-19-*.md`、`tasks/T-20-*.md`（仅卡头 VC 行）**；② 自身目录 `report.md`
- 上游：缺口清单 G-h；本 key 的 `spec.md` AC-008

## 必须修的 6 处（逐条改完在报告里贴 diff 摘要）
1. **`spec.md` AC-021 措辞**：与反向用例不一致（"应当"表述与机器判据不符）⇒ 改为与反向用例口径一致的可执行措辞（不得改 AC 编号，不得弱化语义）。
2. **`spec.md` §2.3 与 AC-025⑤ 字面冲突** ⇒ 二者对齐（保留较严的一侧，并注明以哪条为准）。
3. **`plan.md` §2.5 值域**：`1..50` ⇒ **`1..64`**（与 `autopilot/config.py` 的 `launcher_max_workers` 值域 `(1, 64)` 一致）。
4. **`design.md`**：§0 的 `ac_count: 24` ⇒ **25**；§8 的 AC 映射表**补到 AC-025**（现止于 AC-018）。
5. **缺失的 `evidence-requirement.md`** ⇒ 新建（格式参照 `.agenticdoc/autopilot-monitor/evidence-requirement.md`：逐 VC 一行 `| [VERIFY] VC-0NN | 证据层级 | 判据 | 结果 |`）；若判定某条不适用，必须显式写"不适用 + 理由"，不得省略。
6. **`tasks/T-18/T-19/T-20` 卡头 VC 少报** ⇒ 补齐实际覆盖的 VC 号（对照 `evidence/runs/t-18-*.md` / `t-20-*.md` / `t-21-*.md` 里出现过的 `[VERIFY]` 行）；**pm-state.md** 里的 `1406` vs `1407` 计数取**真值**（用脚本复算后写实测值 + 复算命令）。

## 硬约束
- **纯文档**：不得改任何 `packages/**` 代码；不得改已发布版本段落；不得重写冻结的 evidence 产物（`evidence/runs/*.md`、`evidence/*.md`）的既有内容（勘误只落在字段/表格/措辞级，必要时在文末追加 `## 勘误（2026-10-11）` 段）。
- 计数/值域类的每一处修改都必须在报告里给出**复算命令 + 实测输出**（不得凭记忆）。
- 不得改本 key（`mw-dispatch-settle-gates`）的任何文件，除自身 `report.md`。

## 反向用例（必须真跑并贴输出）
- (a) 用脚本复算 §2.5 值域来源（`autopilot/config.py` 的 `launcher_max_workers` 范围）⇒ 输出 = `(1, 64)`；
- (b) 复算 pm-state 的 1406/1407 真值（给出命令与数字）；
- (c) `rg` 断言：`design.md` 中 `ac_count` 行 = 25，§8 表包含 `AC-025`；
- (d) `grep` 断言：`plan.md` 中不再存在 `1..50`。

## 对照协议（`plan.md §5`）
文档卡以"摘除即红"等价形式执行：A 把第 3 处改回 `1..50` ⇒ (d) 转红；B 把 `ac_count` 改回 24 ⇒ (c) 转红；C 删掉 `evidence-requirement.md` ⇒ 文件存在断言转红。每组贴命令与输出。

## 证据
```
[VERIFY] VC-034: spec_ac021_aligned=true
[VERIFY] VC-035: spec_2_3_vs_ac025_conflict=resolved
[VERIFY] VC-036: plan_section_2_5_range=1..64 recompute=(1,64)
[VERIFY] VC-037: design_ac_count=25 map_includes=AC-025
[VERIFY] VC-038: evidence_requirement_exists=true rows=N
[VERIFY] VC-039: card_headers_updated=3 pmstate_counts=1406/1407-><实测值>
```

## 禁止
不改上一 key 的 `evidence/**` 既有内容（只允许文末追加勘误段）；不改本 key 文件；不 build；不 commit；不跑全量套件；不重启进程。
