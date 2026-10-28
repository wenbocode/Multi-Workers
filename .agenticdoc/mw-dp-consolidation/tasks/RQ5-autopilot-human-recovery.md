---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-recovery.md
---
# RQ5 — Autopilot非普通gate、失败恢复和跨key人工决策

## 上下文
目标锚点 `.agenticdoc/goal.md:5`。用户要求autopilot默认先尝试DP自动决策，所有上报人都要证明人工必要性；先完整清单再看dp7/dp15/dp20覆盖、合并或新增。本轮研究不改变真实授权/硬门，也不受旧“当前人工面永不改变”限制去提出目标态候选。
入口：`packages/multi-workers/autopilot/conductor.py:3771`tick、`:4276`pending-review、`:5127`xkey gate、`:6367`mark_stalled，`packages/multi-workers/autopilot/contract_guard.py:323`。RQ4负责六类gate主表（xkey仅gate层），本RQ负责故障原因对应的实质人类选择、绕过普通gate的升级、pending-review重启/复核、xkey ticket深链及合同变更。

## 要求
1. 审计前完整分段读conductor.py、contract_guard.py、xkey.py，以及实际依赖的advance/closure/review_split等模块。不得以rg片段声称全覆盖；未完整覆盖就如实标记。
2. 搜索所有halt/stall/refused/manual/human/escalate/pending-review/reattest/reopen等生产点并跟踪恢复入口。列真实人类需要作的选择及当前执行路径，不把14条stall原因误列成14个不同决策。
3. 对每项列触发、人工问题/选择、作用对象、现有机器/自动处理、何时仍报人、最终消费者与状态变化（path:line+symbol）。区分必要业务判断、机械缺证、失败通知与需要输入材料。
4. ticket/跨key：证明谁授权什么、授权前后proposal/apply的关系，不照抄旧报告“追认”用词；合同变更是否需要人类同意与retry是否真实消费分别核验。
5. 对每项初步标dp7/15/20候选覆盖及缺失（包括是否其实dp2/dp3/dp6/dp25负责）；不擅自修改四DP业务、不先锁合并/增加。列是否适合先DP与剩余人工必要性，建议/事实分列。
6. 15分钟预算，唯一证据<=220行。不得测试、运行autopilot、读凭证/活ledger/gate、服务操作、真实provider/decision探针、sign/build/install/commit、改phase或源文件。

## 交付格式
唯一证据四节：`## 结论`、`## 证据`（B-01等清单）、`## 残留与未验证`、`## 上下文来源`；附完整阅读/未覆盖范围、与RQ4重复条目的明确关联。最终回复也必须直接含四节，不仅摘要/路径，防恢复输出缺节。原研究报告不改写。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-recovery.md

## 写入允许面
仅唯一证据文件（worker_file/evidence），以及框架自动维护的自身worker回执。不另建report.md。

## 写入禁止面
源码、配置、registry、生成物、spec/design/plan/pm-state、其他RQ证据、活gate/ledger、凭证/服务。
