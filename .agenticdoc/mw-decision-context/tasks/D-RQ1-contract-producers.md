# D-RQ1 四DP契约与真实producer

type: research

## 上下文
目标锚点 `.agenticdoc/goal.md:1`，锁定需求 `.agenticdoc/mw-decision-context/spec.md` AC001–007/020，读本key两个SPEC研究。
源码种子 `packages/multi-workers/decision_points.py:576`，符号registry/decide_for；`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` buildDp1DispatchState；worker-mode.ts buildDp3State和checkpoint；decision_backends.py TimiDecisionsBackend。

## 要求
只读设计研究，非编码，不调用真实模型、浏览器、服务起停、安装、测试或读取真实用户凭证。
1. 提出四DP简洁输入与原生选项机器标签建议、固定生成提示及具体producer入口；dp3覆盖Worker和PM，不把候选当预存答案。至少两种实现路径比较，推荐最小接线。
2. 找dp2自评真实来源/触发次序，异常计数最小规则和缺自评处理建议；区分现行事实/建议/未决。
3. 枚举旧required/截断/legacy/schema生成物/消费下游，说明四DP替换如何不误删其他21DP或vision/rag；原文不静默裁掉必要内容。
4. 提供每个字段真实writer、reader、拒绝路径及生产路径测试建议；只覆盖契约和输入producer，不研究反馈存储、签收或UI（RQ2/RQ3负责）。Jev仅选择，背景由普通Agent现有上下文生成，不造事实。
输出≤200行；大文件分页完整检查相关范围，单read≤120行，禁止反复整dump mw.py/worker-mode.ts，命令输出≤30行；无需全仓漫游。不能以推断说实测。

## 唯一证据文件
.agenticdoc/mw-decision-context/evidence/research/design-contract-producers-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-context/evidence/research/design-contract-producers-20261022.md`

## 写入禁止面
源码、配置、真实凭证、其它key和spec/design/plan文档。自身report.md可按框架记录回执。

## 交付格式
唯一证据含问题/方法与路径行号和符号/事实/两方案pros-cons/推荐/下游清单/待决，给PM可落设计的接口草案，不生成design.md。
research用worker_file，file传上述evidence相对路径；自身回执file="report.md"，禁止绝对file参数。≤64KiB。
