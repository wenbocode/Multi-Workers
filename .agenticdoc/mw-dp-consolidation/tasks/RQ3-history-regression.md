---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-history-regression-20261024.md
---

# RQ3: 退役历史与观察回归边界

## 上下文
目标锚点：`.agenticdoc/goal.md:5`。需求：`.agenticdoc/mw-dp-consolidation/spec.md`、`key-decision.md`。八DP保留，其余17DP删除运行能力而历史只读；dp1/dp2/dp3/dp25业务保持。mw-decision-context的十节点观察、真实反馈、task_before/task_after和安全过滤不得由退役迁移破坏。
入口证据：`packages/multi-workers/decide_registry.json:1354`（dp20），`packages/multi-workers/decision_history.py`（历史投影）、`decision_playground.py`（只读观察/显式提交）、`decision_dashboard.js`（工作台）、`test_decision_task_state.py`（历史状态关联）。行号引用按DP id或函数符号复查。
RQ3只负责历史/观察/case/测试和文档依赖，不做25DP运行inventory（RQ1）或四门业务授权设计（RQ2）。

## 要求
1. 追踪历史reader对当前registry、questions_version、退役DP id的依赖，确定删除活跃注册后保持历史只读的最小办法；不改历史或用当前配置/任务状态回填。
2. 列出工作台列表、scaffold、preview、case选择、submit、poll、十节点DAG、实际处理及前后状态展示受影响的准确路径；区分只读历史元数据和可执行活跃入口。
3. 盘点要删除/迁移的活跃DP测试与应保留或新增的历史只读、安全、拒绝、跨语言契约及四DP业务回归。只给具体测试名和用途，不跑测试或修旧失败。
4. 列出当前文档、提示词和生成样例同步范围；历史归档保留原事实，不为了零搜索命中删除历史。独立case仅下拉缺陷和monitor重启不混入本key修复。
5. 点名producer→writer→consumer→projection→DOM所需集成断言，秘密明文、XSS、旧记录无快照、withheld与unrecorded区别、精确关联和时序不可倒退。
6. 时间预算约15分钟，报告<=150行；限制相关源码/测试/文档目录，排除dist/node_modules/内置Python。不能完成的写未覆盖面，不漫游生产ledger。
7. 不运行测试、真实模型请求、共享服务、monitor、sign、build、install、commit；不调用ask_decision；不访问凭证，不改phase。

## 交付格式
唯一证据含：历史依赖表、观察/样例受影响面、测试迁移清单、建议回归断言、当前文档与历史保留边界、风险和未覆盖面。关键结论附路径:行号+符号。先落盘骨架再填证据；可用worker_file按本key的evidence相对路径落盘。最终回复只给摘要和证据路径，不声称实现通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-history-regression-20261024.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-history-regression-20261024.md

## 写入禁止面
源码、registry和生成物、配置、framework、spec/design/plan/pm-state、其他RQ证据、生产ledger和历史记录禁止修改。除框架自动管理的自身worker产物外，不写其他路径。
