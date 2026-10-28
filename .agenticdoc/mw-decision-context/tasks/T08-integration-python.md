# T08 Python/工作台集中集成（固定T08子写面）
type: coding
write_face:
  - packages/multi-workers/decision_points.py
  - packages/multi-workers/decision_context.py
  - packages/multi-workers/decision_lifecycle.py
  - packages/multi-workers/decision_wire.py
  - packages/multi-workers/decision_history.py
  - packages/multi-workers/decision_signoff_result.py
  - packages/multi-workers/decide_signoff.py
  - packages/multi-workers/mw.py
  - packages/multi-workers/decision_monitor.py
  - packages/multi-workers/decision_playground.py
  - packages/multi-workers/decision_dashboard.js
  - packages/multi-workers/decision_dashboard.html
  - packages/multi-workers/decision_dashboard.css
  - packages/multi-workers/test_decision_context_integration.py
  - packages/multi-workers/test_decision_context_contract.py
  - packages/multi-workers/test_decision_context_lifecycle.py
  - packages/multi-workers/test_decision_context_history.py
  - packages/multi-workers/test_decision_context_signoff_cli.py
  - packages/multi-workers/test_decision_context_workbench.py
  - packages/multi-workers/test_decide_registry_contract.py
  - packages/multi-workers/test_decision_book.py
  - packages/multi-workers/test_decision_input_contract_migration.py
  - packages/multi-workers/test_decision_context.py
  - packages/multi-workers/test_decision_dashboard_contracts.py
  - packages/multi-workers/test_decision_dashboard_assets.py
  - packages/multi-workers/test_decision_monitor.py
  - packages/multi-workers/test_decision_dashboard_playground.py
  - packages/multi-workers/test_decide_signoff.py
  - packages/multi-workers/test_decide_sign_auto.py
  - packages/multi-workers/test_decide_run_authority.py
ac_refs: AC-001, AC-002, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020
vc_refs: VC-001, VC-002, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020

## 上下文
目标`.agenticdoc/goal.md:1`；批准spec/design/plan。种子`packages/multi-workers/decision_history.py:2277` _signoff_fact（符号锚）；`mw.py:915` _decide_versioned_run/新sign path。T01/T02/T05/T06/T07均终态已ack，report需完整分页读。必须读`.agenticdoc/mw-decision-context/evidence/integration-handoff.md`固定缺口，非泛审计。T08另一TS写面会并行，不争写Python/UI。

## 要求
只实现批准设计闭环，不泛研究/不扩矩阵/不滚动碎修。
1. 新记录包含失败/disabled/反馈关联失败仍精确logical_id↔decision_id，不legacy误判，不靠key时间猜；最小record_start接受真实decision_id由CLI提前传或现调用入口显式桥，独立ID仍真实。
2. history读取T05 validate_signoff(expected本次logical_id+snapshot)精确有效签收文件，finalize实际文件才completed；文件成功反馈失败仍completed并诚实错误。不能signoff反馈声明就完成。文件历史事实与当前材料重判分列，hash不豁免安全父链。
3. 四完整case编辑→实际观察submit→真实loopback `/v1/decisions`正文精确断言，不hash代正文；单次history/test DAG真实请求返回且行动未执行/生产授权archive/signoff不变。现T07 UI自DAG/独立playgroundmeta接线若需修在允许面，不能10节点空壳或UI伪反馈。旧数据保留无DAG，其余25通用操作保留。
4. T01 _fit_state2000B vs T03真实卡2559B（TS不拦不等Python允许）：用四完整case和实际原文材料实测统一预算，必要按现transport真实预算支持完整材料、超预算明确拒绝不截断；不任意新增字段限额/不关闭原transport门。先测RED后按证据改；发布最终预算给TS lane report，TS不可写Python。
5. mw dp verify四DP探针新schema，旧sign无stdin不能留主入口悄悄坏；明确材料要求/新入口提示，禁止复活计数判断/旧schema兼容。framework gate不在许可内，禁止改/关闭/伪continue；作为结案阻塞报告，不绕过。
6. 迁移允许面旧测试fixtures到新契约，保留不相关安全测试，不删测试为绿。早行为RED→最小修GREEN，collection/修后回放不先行。无凭证测试tmp HOME/USERPROFILE/PI_CODING_AGENT_DIR+合成auth/env清理/读前spy，HTTP only loopback，禁真实Jev/browser/service/build/install/commit。
7. 所有worker已停，本写面首写原文/hash/diff快照包括untracked，保留外来diff。大文件完整分页≤120行；10分钟内列出定点测试RED，不反复读研究。最终逐文件专项+邻接串行完整UTF8日志/UTC/exit，不要pytest全包。npm run check PM稳定后统一不worker全仓写。

## 写入允许面
- packages/multi-workers/decision_points.py
- packages/multi-workers/decision_context.py
- packages/multi-workers/decision_lifecycle.py
- packages/multi-workers/decision_wire.py
- packages/multi-workers/decision_history.py
- packages/multi-workers/decision_signoff_result.py
- packages/multi-workers/decide_signoff.py
- packages/multi-workers/mw.py
- packages/multi-workers/decision_monitor.py
- packages/multi-workers/decision_playground.py
- packages/multi-workers/decision_dashboard.js
- packages/multi-workers/decision_dashboard.html
- packages/multi-workers/decision_dashboard.css
- packages/multi-workers/test_decision_context_integration.py
- packages/multi-workers/test_decision_context_contract.py
- packages/multi-workers/test_decision_context_lifecycle.py
- packages/multi-workers/test_decision_context_history.py
- packages/multi-workers/test_decision_context_signoff_cli.py
- packages/multi-workers/test_decision_context_workbench.py
- packages/multi-workers/test_decide_registry_contract.py
- packages/multi-workers/test_decision_book.py
- packages/multi-workers/test_decision_input_contract_migration.py
- packages/multi-workers/test_decision_context.py
- packages/multi-workers/test_decision_dashboard_contracts.py
- packages/multi-workers/test_decision_dashboard_assets.py
- packages/multi-workers/test_decision_monitor.py
- packages/multi-workers/test_decision_dashboard_playground.py
- packages/multi-workers/test_decide_signoff.py
- packages/multi-workers/test_decide_sign_auto.py
- packages/multi-workers/test_decide_run_authority.py

## 写入禁止面
所有TS及生成物/其余测试/框架脚本/项目配置/依赖锁/dist/真实凭证/其它key/PM phase文档；不可越面追绿，必要问题集中report。

## 验收命令
`cd packages/multi-workers; python -m pytest test_decision_context_integration.py -q`；所有修改测试逐文件执行，先定向RED，后相关邻接逐文件串行避免全suite和端口冲突；保存完整stdout不是tail，UTF8 subprocess capture。`python mw.py decide dp verify`仅隔离无凭证路径，CLI actual submit真loopback fixture。

## 改动历史
固定T08收口，非新增需求/泛研究；基础六卡局部GREEN并不整体验收，T07原needs-clarification因dp1写登记已核hash。review/PM独立复验在本卡终态后稳定快照进行。
2026-10-23首尝试因分类文字/标点污染生成写面，业务BLOCKED零源码/测试改动；原worker修task.md不改变activation缓存。实体卡改显式30路径、正文同30路径后重派同T08，不修改门禁、不扩面。旧报告方案仅供参考，16384B建议未运行证明且token估算需实测核实，不预定预算；有效文件发现不能依赖signoff反馈行存在。

## 交付格式
report.md/evidence明确实现缺口是否闭合、原RED/GREEN/UTC/exit/hash、真实HTTP/fixture/未验平台分层、每AC/VC断言真实证据、不以预写VERIFY冒充；剩余真正阻塞单列（framework gate仍需授权），低影响细节集中账不派碎研究。给TS lane精确接口与预算，若接口变发PM而非双写。
