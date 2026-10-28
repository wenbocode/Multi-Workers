---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/t10-handoff-audit-20261027.md
execution: worker
logical_id: T10
---
# T10交接资格补核 — 生命周期/旧断言/合法fixture路径

## 上下文
项目目标 `.agenticdoc/goal.md:5`；原卡 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`；当前 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py:1`，decision_wire.py/decision_task_state.py/test_decision_context_lifecycle.py/test_decision_task_state.py同目录。原36逻辑任务/7stage不变，仅T10原交接补证，不提前正式T33审计或新增实现任务。
原dpc-t10-lifecycle-state已done/exit0/acked，worker三次116P/before31F85P仅待独立资格；证据 evidence/implementation/dpc-t10-lifecycle-state/。PM保护五当前产品SHA在 evidence/implementation/t05-r2-envelope-pm-handoff-20261027/check.json 和 t05-r2-envelope-pre-dispatch-20261027/T10-products-protection.json，T05 writer已终态稳定。
外部OS测试sink尚未授权，禁止创建/复用；原scope guard拒绝.agenticdoc目录、worker越面OS TEMP写及首次40setup stdout覆盖丢失必须保留，不为绿测试改guard/伪恢复/事后授权。

## 要求
1. 当前五产品/测试完整分段read到实际EOF，截断继续，记录真实行数及未覆盖面。先读原report/baseline/after/完整五diff及保存的before(通过真实目录/metadata定位，不猜文件名)；读current production书/协议必要关联，主要采用源文件EOF或明确范围，不能拿AST/搜索/旧worker声明当EOF。
2. 独立静态核原37生命周期函数及22taskstate函数保留；7 fixture ID迁移是否合法、不弱assert/skip/xfail；新增request/note/terminal函数及原executed/settled链的关联/校验。给old/current path:line和实质assert差异，不以函数计数代强度。纯只读AST/文本对照可用bash，任何Python-B和PYTHONDONTWRITEBYTECODE=1，不import产品、不生成pyc或多行python-c/额外脚本。
3. 逐链核prepare/request/PM note/model basis/consumed/executed/settled/terminal关联：同key/task/logical_id，basis单源digest/合法choice/applies_to/material refs，真正未记录null与[]、creation snapshot同值再声明、未知角色/后继/失败执行/时序、PM only note、secret redaction。重点原executed/settled是否只核before而terminal核before/after；具体counterexample输入形状与触发函数可作为PM下一fake probe材料，不运行/伪造实际已发生。
4. 静态核decision_wire的测试scope合法性：它为什么拒绝.agenticdoc路径，哪些谓词是否允许key evidence内合法普通目录且不绕guard？若没有合法内置sink，明确必须等待具体外部目录人工许可。不将名称fixture/预算/token/role转换成授权、不改变环境归属使实际OS写看似面内。给最小安全PM验证计划：两assigned suites、真实import定位、前后hash、fake backend/child网络拒绝、最小env、-B/cache/autoload、唯一运行label全日志；仅计划，不执行测试/创建任何fixture。
5. 核worker evidence时间与缓存线索/失日志使用限制，明确净hash不能证明瞬时无写/独占作者；原14pyc中1漂移禁止清理/复原/重取基线抹偏差。分开产品当前正确性和原过程违规，不把116P或done/acked当完整交接。
6. 不运行产品测试、static product import、generator、CLI/服务/HTTP/决策/模型/浏览器；不读活config/gate/ledger/凭证/其他key文件或图片；不创建OS目录/工具脚本/fixture/cache。只读采用材料，发现工程缺陷给原T10 exact面修复建议或具体未列面，不实现、不改DAG/目标/模型/预算/timeout/watchdog。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-handoff-audit-20261027.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/implementation/t10-handoff-audit-20261027.md

## 写入禁止面
唯一证据以外全部：全部产品/原卡/worker run-output/原PM证据/state/DAG/缓存/OS目录/脚本。本卡不是外部sink授权，不能先写OS对象再披露。

## 交付格式
唯一证据和最终回复含五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。给五源码EOF真范围、原函数/assert对照、真实路径关联/缺陷严重性/PM probe输入、合法fixture谓词/待许可、明确未运行验证范围。改动清单表头“文件”，仅新唯一证据；回读确认完整。非正式QG/签收，不造PASS/receipt，PM终态吸收后ack。
