# Research: DESIGN启动约束

## 问题与方法
本key用户确认正式spec，2026-10-22T23:37:55+08:00锁定20AC；这是需求事实，不是运行实验。目标`.agenticdoc/goal.md:1`，现行dp2 id `packages/multi-workers/decision_points.py:576`。

## 并行分析
- RQ-D1契约/输入producer；RQ-D2反馈/签收；RQ-D3UI/API消费者/case，三个独立只读问题，无源码写冲突，各唯一design研究证据。
- 源码共同读取允许；跨问题接口由PM串行对齐，design.md/evidence-requirement.md只由PM写。
- 当前服务已运行，所有worker状态读取未见running；不重启共享服务，不编码。
- 另mw-signoff-decide-only索引DONE，研究核实其当前源码，不据此追认旧dashboard已完成。

## 固定边界与决策映射
- Jev原生只选择，普通Agent生成dp3/dp25材料；不大schema，事实/建议分列。
- dp25可以收尾直接签收，调用前必要本地硬门、phase仍框架门禁；dp2/dp3选择非执行授权。
- 新记录真实关联和自动反馈；旧数据不推断DAG；测试4case只观察。
- 不读取真实用户凭证，不测试/浏览器/真实Jev/安装/构建/commit。
- 调研回读后PM形成候选设计并请用户审核，不滚动新增泛研究。
