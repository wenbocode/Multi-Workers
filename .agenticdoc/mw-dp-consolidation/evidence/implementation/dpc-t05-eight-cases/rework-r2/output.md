# T05-R2 交付摘要（worker dpc-t05-eight-cases-r2）

## 结论

BLOCKED，产品 0 改动。派发 `task.md` 的 `write_face:` 只含
`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2/**`
一条，卡 frontmatter 的 11 个产品全部在运行时写面之外；第一次产品编辑（给
`test_decision_context_workbench.py` 加两根因红测）被出包守卫
`[rule=write-scope] outside-declared-write-face` 拒绝，写 0 字节。

根因已定位且可机器复现：派发器只把卡的 `## 写入允许面` **段落正文**抽成 write_face 头
（`autopilot/dispatch.py::_card_write_face_entries`）。原 T05 卡该段是 12 条 bullet list →
头 12 条；本 R2 卡把该段写成散文，只剩一个反引号 span（evidence glob）→ 头 1 条 → 11/12
声明产品被拒。同一抽取器/渲染器下原卡 `head_is_the_extracted_list: true`，故这是卡体
回归，不是派发器缺陷。

因此两根因（schema2 老模板；`CASE_PREPARED_AT=2026-10-27T20:56:00+00:00` 未来时刻）**未修**，
红测未加、实现未改、8 case 未重生成、suite 未跑。产品与副本逐字节原样（27 行复验一致、
1891 文件清单零变化、14 pyc 零变化）。

## 证据

- `...\rework-r2\blocker\face-mismatch.json`：frontmatter 12 条；抽取 1 条；task.md 头 1 条；
  `products_outside_dispatched_face` 11/12；`previous_card_control` 12 条且 round-trip 成立。
- `...\rework-r2\blocker\guard-refusal.json`：守卫拒绝原文与 `bytes_written: 0`。
- `...\rework-r2\blocker\unmodified.json`：`all_products_unchanged: true`、
  `inventory_changed: []`（1891）、`pyc_changed: []`（14）。
- `...\rework-r2\before-metadata.json` + `before-bytes\**`（15 份）：11 产品 + 4 旧 case 的
  bytes/SHA/LF/CRLF，与 PM `t05-r2-pre-dispatch-20261027/before-metadata.json` SHA 逐条相同。
- `...\rework-r2\test-functions-before.json`：28 个测试函数的 AST/source/spans 基线。
- `...\rework-r2\inventory-before.json`（1891 文件 SHA）、`pyc-before.json`（14 pyc）。
- 源码读到 EOF：generator 902 行、template 61 行、workbench test 2274 行（分 9 段）。
- 诊断脚本全部 `PYTHONDONTWRITEBYTECODE=1 python -B`，import 根为实施副本，无网络/CLI/服务。

## 残留与未验证

- 两根因仍存在（模板 3 red、8 case prepared_at 未来），本 R2 未取得任何修复。
- 未加红测、未跑 `-k` focused、未跑整文件 suite（真实 rc 不存在）、未跑生成器
  `--out`、无字节比对/四旧重生成/生产 `check_book`/scaffold 比对。
- 28 函数与 12 个已知 monitor/history/DOM 失败未再执行；T10 三模块 before/after 无
  测试轮次（无数据，不虚构）。
- 解除阻断需 PM 把 `## 写入允许面` 恢复成 12 条 bullet（与原 T05 卡同形）并重派；
  重派后可直接照卡执行先红后绿。

## 上下文来源

- 卡 `...\mw-dp-consolidation\tasks\isolated\T05-eight-cases-r2.md`；派发
  `...\workers\dpc-t05-eight-cases-r2\task.md`
- 原 T05 对照卡/任务书（12 条 bullet + 12 条 head）
- PM `t05-pm-handoff-20261027\{probe.json,check.json}`、
  `t05-r2-pre-dispatch-20261027\{check.json,before-metadata.json}`
- 契约 `decision_book.py`（scaffold_book/schema3）、`decision_points.py`
  （preparation_issues）、`autopilot/dispatch.py`、`autopilot/write_face.py`、
  `worker-mode.ts`（checkBashWriteScopeTarget）
- `goal.md:5`、`spec.md:128`、`design.md:201`

## 改动清单

| 文件 | 动作 |
| --- | --- |
| ...\rework-r2\tools\capture_state.py | 新增（before 取证器，8945B） |
| ...\rework-r2\tools\diagnose_face.py | 新增（写面复现，6080B） |
| ...\rework-r2\tools\verify_unchanged.py | 新增（未改动复验，3304B） |
| ...\rework-r2\tools\inspect_inventory.py | 新增（只读分析，1376B） |
| ...\rework-r2\tools\inspect_inventory2.py | 新增（只读分析，1650B） |
| ...\rework-r2\before-metadata.json / before-bytes\** / test-functions-before.json / inventory-before.json / pyc-before.json | 新增（取证快照） |
| ...\rework-r2\blocker\{face-mismatch,guard-refusal,unmodified}.json | 新增（阻断证据） |
| ...\rework-r2\report.md / output.md | 新增（本报告与摘要副本） |
| 11 个产品（generator/template/workbench test/8 case） | 未改（SHA 见 report.md 表） |
| 4 旧 case | 未改（SHA 保持不变） |
