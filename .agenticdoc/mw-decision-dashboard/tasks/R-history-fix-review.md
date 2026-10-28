# R T07b 历史安全修复复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement。
- `packages/multi-workers/decision_history.py:1`、`test_decision_history.py:1` 全文；workers/dd-review-history/report.md原2P1/5P2；workers/dd-history-fixes/report.md及evidence/runs/T07b-history-fixes/verify-summary.md和日志/变异脚本。
- T10代码完成在独立review，T05尚running，不修改依赖。

## 审计目标
逐finding closed/open表。独立查输出所有carrier/列表/详情/stage/calls/warnings及schema键、结构字段验证是否漏secret（允许标识符不等已可信）；缺redactoromit诚实标记；2048B截断长secret边界完整；不得把omit answer误称无答案来源。路径读取前包含性检查覆盖archive/wire/lifecycle/signoff/gate/test roots，记录key不拼任意路径，symlink/junction拒绝在read前，计数+warning不含外内容且不崩。
来源available无答案unknown、usage last-attempt明确不覆盖为总量、重复settled最后事实一致、gate-only/无key可观测、auto-decide/auto-llm/refresh/authority dp广播的测试是否实锁。
237/39/68+1及五类fixture/真实5carrierhash证据核对，真实生产37/38时点变化分清；历史与monitor新API缺回调/注入安全预条件明确。
证据偏差必须明确：10 mutants是在实现后单点退化，不是原实现前RED；未提交文件不是无法保存基线的理由，不能倒推TDD流程合规。npx biome check .没--error-on-warnings，exit0仍3w2i不等清零/严格只读检查通过，browser-smoke本次未列不得虚报全部子步。

## 要求
只读PASS/CHANGES_REQUIRED，原2P1闭合无新增严重项才安全PASS；流程证据偏差单列不得默改过去日志。新finding实际path:line/触发/AC-VC/最小修复。无shell明确静态旧日志不是自己实测。

## 未覆盖面声明
真实HTTP/browser/跨进程/真实Jev/平台全链与全仓check未完成；不审T05/T10在产。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-history-fixes/**`

## 写入禁止面
- 所有源/测试/任务相位/生产记录/其他worker。

## 交付格式
report≤180行，结论/逐finding表/证据偏差/下游风险/上下文与未覆盖，摘要≤30行。
