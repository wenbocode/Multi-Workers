---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-pm-framework.md
---
# RQ6 — Autopilot PM/框架侧上报人决策与DP覆盖

## 上下文
目标锚点 `.agenticdoc/goal.md:5`。用户新原则：autopilot要放权，原则上先DP自动判断、确需人时才升级。任务先列当前全部人工决策，再评估dp7/15/20覆盖，合并或新增仍未决定。
入口：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts:169`、`.agents/skills/agentic-task/scripts/advance_phase.py:1`、`packages/multi-workers/autopilot/advance.py:1`。RQ4核Python gate主表，RQ5核Python失败/xkey深链；本RQ核TS命令/PM消息与框架phase/L1/L2/L3/签收上报人路径及真实DP问项/材料/动作契约。

## 要求
1. 全文读取实际审计文件，再沿引用跟踪必要消费者；优先TS autopilot console/commands/monitor/gate writer、Python advance/closure和框架advance_phase、质量/签收入口。不能无界扫描pi核心、不改核心。完整阅读范围/未读范围必须声明。
2. 区分控制命令start/stop/status（人工操作不一定是被上报的业务决策）、通知/硬检查拒绝（不等于需要人选择）、真正请求人决定。找出不进六kind gate的PM触发/消息/收尾决定，不以文件名存在作完成证据。
3. 每条给触发、人工问题/实际选择、当前自动途径、消费者动作、人工必要性候选，path:line+symbol；C-01标签并标RQ4/RQ5对应条目避免重复。
4. 读取dp7/dp15/dp20实际registry定义/required fields/执行器及调用者；给覆盖表：能表达/材料不足/动作未接线/不适用，明确当前可问不等于能推进。其他保留DP只核必要交叉，特别dp2/dp3/dp6/dp25业务不改，阶段关闭与key签收不是一回事。
5. 对人工审批判断只列当前事实+新原则下候选，不把旧manual默认当不可改变目标，也不直接宣称所有硬门可模型绕过。
6. 15分钟预算，证据<=220行；不运行测试/框架命令/共享服务/签收/build/install/commit，不读凭证/生产ledger，不调用真实决策或provider探针，不写源文件。

## 交付格式
唯一证据含`## 结论`、`## 证据`（决策清单+三个DP覆盖）、`## 残留与未验证`、`## 上下文来源`；最终回复同样直接四节，不能只摘要+路径。对未核完直接声明，不推断已覆盖全部。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-pm-framework.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-pm-framework.md

自身worker回执仅由框架自动维护，不另建report.md。

## 写入禁止面
源码、配置、registry/生成物、phase/PM相位文档、其他RQ证据、活gate/ledger、凭证与服务。
