# D-RQ3 all DP input contracts and isolated observation

type: research

## 上下文
- Goal `.agenticdoc/goal.md`；锁定 `.agenticdoc/mw-decision-dashboard/spec.md` AC-004/008/009/010/011/017；design.md 是候选不编码。
- `packages/multi-workers/decision_book.py:626` closed state 校验；`decision_points.py:2278` decide_for；`mw.py:911` _decide_run；`decide_signoff.py:287` collect。
- 25 DP 中21缺业务 required_state_fields；用户确认全 DP 字段契约、人工可观察 disabled/P0、独立测试记录且不改生产门禁。

## 要求
只读设计每个 DP 的真实最小业务输入字段（名称/类型/意义/证据要求），基于注册问题和现有生产触发事实，不凭 dp 标题编业务。给25行矩阵：现状、建议字段、证实/待设计声明、是否影响生产 validator 与 TS镜像、生成漂移契约。比较 (A) registry 引入 required+optional 业务输入闭集与 (B)统一受控 context 表达；要求骨架可填写业务事实且不是3身份字段虚测。设计人工观察调用：复用 book gate、state builder、questions/backend/client、答案/置信度/生产判定；显式仅观察才能跨 enabled 门，不临时改授权表、不写生产archive、不调用executor、不假造采纳成功。比较观察入口共用 decide_for 内部 seam与独立应用层调用真实 client两案，明确谁执行生产预览判定、哪些门仅预览。提出独立 test record 接口、每次唯一调用标识、重复点击/重试/超时、disabled transport/缺凭证处理、签收隔离验证、worker不可用验证。说明配置全局 disabled是否仍禁止发送或仅显式人工观察绕过，给推荐理由。
禁止代码/配置/档案修改、禁真实模型网络调用、服务启停、依赖安装。与 D-RQ2不抢事件schema，以建议接口边界协作。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/design-dp-observation-contract-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/design-dp-observation-contract-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-drq3-contract/**`

## 写入禁止面
- 所有代码、配置、其他 key/任务、相位文档。

## 交付格式
证据 ≤300 行，结论/出处 path:line/25 DP字段矩阵/两案 pros cons/推荐边界/VC/风险未覆盖。report.md 四段结论/证据/残留与未验证/上下文来源 ≤80行，先写骨架。大文件按函数锚分页完整读上下文，单次 read≤150行/命令stdout≤30行。不得把设计建议标为已验证。
