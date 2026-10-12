# T-14 — Python 侧调用点接线（`launcher.py` / `mw.py` 改用同一解析函数）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**：`design.md` §4.4.2（6 份解析器矩阵 P4/P5 行）+ §4.4.4（fail-closed 范围裁定，仅 origin 标记任务）；`spec.md` AC-005（「派发期判据与执行期角色判定必须来自同一解析函数」）；`evidence/research/design-role-key-identity-20261011.md` §2/§3
- 证据: `evidence/research/spec-taskmd-corpus-20261011.md`（6 分解析器语义分歧实测）；T-08 的 `workers/mwgf-t08-python-parity/report.md`（本卡的上游缺口报告）
- **唯一允许改的路径**: `packages/multi-workers/launcher.py`；`packages/multi-workers/mw.py`；`packages/multi-workers/test_launcher.py`；`packages/multi-workers/test_mw_autopilot_cli.py`（仅补用例）；外加自身目录 `report.md`
- 禁止: 运行全量 pytest / `npm run check` / 全量 vitest / `mw build`；修改 `mw_common.py`（T-08 已定稿）、TS 源码、`spec.md`/`design.md`/`plan.md`/其他卡片；git 操作

## 背景（PM 实测，勿再声称未验证）

- T-08 已把 `mw_common.py` 的 `read_task_type` / `read_task_header_region` / `read_task_header_scalar` / `scan_body_type_lines` 实现成 `shared/task-frontmatter.ts` 的**逐字段镜像**（BOM 剥除、首个 `type:`、fence/空行/键文法边界、ES 兼容 trim），并交付 18 条 golden fixture 与 node 反向差分测试（7 passed；`py_vs_fixture=18/18`、`corpus_py_md5_eq_ts_md5=313/313`、`bom_books_readable=7/7`）。
- **但调用点未接线**：`launcher.py` 仍自带 `^type:` 正则且**不调用** `read_task_type`；`mw.py` 同样不调用。⇒ BOM 修复只在函数级生效，**worker 生成期拿到的角色仍是旧语义**（历史 7 本 BOM 任务书中 1 本实为 `review`，旧语义下会退化成默认角色）。这正是 AC-005「同一解析函数」的未闭合部分。
- 注：`mw_common.read_task_type` 返回 `TaskTypeReading` **对象**（`{ type, source, bomStripped }`），不是字符串 ⇒ 调用点按 `.type` 取值（或先取 `type` 再判空），并按 `source` 决定审计措辞。

## 必须实现

1. **`launcher.py` 接线**：把自带的 `type:` 提取替换为 `mw_common.read_task_type(...)` 调用，角色取值语义与 TS 一致（首个 `type:` 胜出；正文行不得决定角色）。保留既有默认角色与该文件原有的日志/审计行为（只换判据来源，不改输出协议）。
2. **`mw.py` 接线**：同上；若 `mw.py` 的 `type:` 判据嵌在别处（如 autopilot 子命令或 doctor/status 输出），逐处替换为同一函数。
3. **不得改调用协议**：`read_task_type` 的签名/返回结构不得为了让调用点好写而改动（T-08 已定稿并由一致性测试锁定）。若发现必须改，**停下报告**，不得自行改 `mw_common.py`。
4. **行为等价 + 修复证据**：对全部真实语料（当前 313 本 `task.md`，会增长）做前后对照：`type` 取值变化只允许出现在 BOM 本（7 本，具名），且变化方向 = 「旧=默认/None、新=头部真实值」；其余本零变化。断言不得依赖语料计数上限。
5. **测试**：`test_launcher.py`（+ `test_mw_autopilot_cli.py` 如需）新增：① BOM 任务书 ⇒ 角色正确；② 正文 `type:` 不影响角色；③ 无 `type:` ⇒ 既有默认行为不变；④ origin 标记 vs 无标记两条路径行为对照（按 design §4.4.4 裁定：仅 origin 标记任务 fail-closed，无标记保持现行为）。
6. 先构造能失败的断言（红：BOM 本角色错/默认），再接线（绿），报告红→绿证据。

## 验收命令（PM 执行，worker 不得自行运行全量）

- 单文件：`cd packages/multi-workers && python -X utf8 -m pytest test_launcher.py -q`
- 相关：`cd packages/multi-workers && python -X utf8 -m pytest test_mw_autopilot_cli.py test_task_type_parity.py -q`

## 交付

`report.md`：改动文件清单（逐文件 + 函数/行区间）、语料前后对照（变化仅 BOM 7 本 + 具名）、红→绿证据、origin/无标记两路径行为对照、未完成项与原因（若有）。
