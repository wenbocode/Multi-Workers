# RQ1 dp1/dp2真实上下文

type: research

## 上下文
- goal `.agenticdoc/goal.md`；本key spec.md讨论草案，用户要精简有效context不是实现。
- `packages/multi-workers/decision_points.py:546` dp1注册；:1258 required字段。按函数定位dp2实名和producer。

## 要求
只读核dp1/dp2：真实决策问题/问题选项/实际TS/Pythonproducer传来的材料/最终HTTP模型收到哪些字段；哪些事实真实、哪些摘要推断或审计metadata；缺少任务原文/文件写面/进展原文是否导致模型判断信息不足。引用path:line，列1份现状小样例和1份候选最简context（建议非已确认）。不要广泛audit/安全矩阵/编码/模型请求/凭证读取。≤100行，重点dp1以便PM先讨论。其他key正在改测试/docs，标当前时点与变动不争写。

## 唯一证据文件
- `.agenticdoc/mw-decision-context/evidence/research/spec-dispatch-midflight-20261022.md`

## 写入禁止面
所有源码/其他key/真实凭证/旧证据；唯一研究证据外不写。

## 交付格式
唯一证据文件，来源/事实/现状与候选/待用户确认；报告摘要引用该文件。不改spec相位。
