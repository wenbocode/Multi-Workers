---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-gates.md
---
# RQ4 — Autopilot显式人工gate全清单

## 上下文
目标锚点 `.agenticdoc/goal.md:5`。用户新原则：autopilot要放权；默认先尝试DP自动决策，只有确有人工必要性的事项上报人。本轮只盘点实际当前路径，下一步才讨论dp7/dp15/dp20覆盖、合并或增加；旧“现有人工边界不变”不再是目标态设计前提，但现有机器安全机制和人工批准不能在研究中绕过。
入口：`packages/multi-workers/autopilot/conductor.py:910`消费gate，`:1272`阶段收口，`:6893`RULES，`packages/multi-workers/autopilot/gates.py:75`种类闭集。先读本key旧RQ2及PM复核的限制，不复制旧结论当新证据。与RQ5/RQ6并行，只读共享源码无写冲突。

## 要求
1. 完整读conductor.py/gates.py/config.py再审计，分段读直到末尾；不执行代码、不测试、不读取凭证或活gate/ledger。仅源码与已有脱敏项目文档取证。
2. 本RQ负责六类显式人工gate生产、选择、写入、消费和当前自动面。xkey仅列gate层授权动作；ticket深链归RQ5。逐项列gate实例何时生成、用户真实问题/可选动作、approve/reject实际影响、自动规则/off-shadow-live条件、仍转人工理由，附准确path:line+symbol。
3. 特别区分：当前仅人工处理是实现事实，不等于只有人能判断；事实检查失败不是新的业务决策；告警/通知不是决策。若一个kind有语义不同的人工选择，拆成条目；不得仅交六kind名称。
4. 对每项初步判断是否可按新原则先DP，以及剩余人工必要性是什么（权限外/业务未知/破坏性等），事实与建议分列。对dp7/15/20只标候选覆盖/缺材料/缺动作，不预先锁定归属或合并。
5. 完整列搜索/阅读覆盖范围与未覆盖面，特别核stage-close旧注释与实际规则冲突，不猜全局默认或线上状态。记录所有不经普通_create_gate建立的gate生产者。
6. 15分钟预算，证据<=220行；最终不得以“六类全人工”或旧未接线注释代替实际消费者证据。
7. 不调用ask_decision/真实provider探针；不执行测试/build/install/sign/服务命令，不改源码/配置/phase/历史。对本worker自身模型正常执行不作“零模型”声明。

## 交付格式
唯一证据文件必须包含四节：`## 结论`、`## 证据`（决策清单表）、`## 残留与未验证`、`## 上下文来源`。决策表每条附production→human answer→consumer坐标；以A-01等本地标签便于PM合并。
最终回复也必须直接包含上述四节，不能仅“摘要+证据路径”，避免输出恢复契约缺节。未完成就明确未覆盖，不伪造PASS或模型成功。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/spec-autopilot-human-gates.md

## 写入允许面
仅上述唯一证据文件（worker_file/evidence写入），以及框架自动维护的自身worker回执。不要另建report.md或改PM文档。

## 写入禁止面
所有源码/配置/registry/生成物、活gate/ledger、spec/design/plan/pm-state、其他证据、凭证与服务操作。
