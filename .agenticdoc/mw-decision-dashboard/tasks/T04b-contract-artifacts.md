# T04b 契约产物收口

type: coding
status: code-complete-ledger-absorbed
code_status: 代码完成
verification_status: 完整T04验收395通过，全仓check未通过
ac_refs: [AC-009, AC-011]
vc_refs: [VC-009]

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/plan与T04卡全文；`packages/multi-workers/mw.py:1` _DP_VERIFY_STATE_VALUES、`packages/multi-workers/decide_book_template.json:1`。
- 原workers/dd-dp-contracts/report.md和evidence/runs/T04-dp-contracts/red-green.md，119专项通过但验收44失败，proposed文件只是待核实建议。

## 要求
PM明确批准精确写面增量：mw.py只改_DP_VERIFY_STATE_VALUES纯数据，模板通过真实既有renderer重生成。独立验证proposed数据，不盲复制；先确认现有43+1失败，再修正跑完整T04验收至全通过。不能以dp19/ask_decision当授权来源；本卡权限来自用户开工和PM任务分配，不调用付费模型求裁决。原T04 ledger漏decide_registry.json已为原卡允许面，报告明确实际生成写入以补追溯。TS漂移旧行不能当mirror无漂移，把冻结旧词汇测试标迁移债，不默默放宽校验。其他TS/dispatch写面不动、报告缺口给PM。npm run check非绿如实报告，不越面改lint。

## 写入允许面
- `packages/multi-workers/mw.py`（仅_DP_VERIFY_STATE_VALUES块）
- `packages/multi-workers/decide_book_template.json`
- `.agenticdoc/mw-decision-dashboard/workers/dd-contract-artifacts/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T04b-*`

## 写入禁止面
- mw.py其他逻辑/CLI路由、points/book/所有TS/dispatch、其他所有源和配置、任务和相位文档、生产档案、dist、凭证、依赖锁文件。

## 验收命令
cwd packages/multi-workers：`python -m pytest test_decision_dashboard_contracts.py test_decide_registry_contract.py test_decide_registry_export.py test_decide_registry_ts_lock.py test_decision_points.py test_decision_book.py -q`。
root `npm run check` 全输出（会触及其他面formatter时报告PM，不能自行更改禁止文件）。禁止build/npm test/全vitest/真实网络/commit。

## 改动历史
- PM因原T04漏探针/模板精确扩大两产物写面，mw.py当前无其他live worker写者；后续T08需等本卡结束。

## 交付格式
四段report，RED/全GREEN命令退出码日志、实际修改与生成路径、ledger补记、剩余TS/dispatch债与未验证面；不宣称全AC完成。
