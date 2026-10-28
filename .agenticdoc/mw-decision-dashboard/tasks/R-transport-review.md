# R T03 真实传输接线审查

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design及evidence-requirement全文。
- `packages/multi-workers/decision_backends.py:246` _http_post；`packages/multi-workers/decision.py:829` client（行漂移按函数定位）；T03卡/report/verify-summary。
- T02b基础修复worker当前独占decision_wire.py/mw_common.py；可只读其API，不将中间RED视为外部噪声。

## 审计目标
完整读取decision.py/backend/T03新增测试，独立检查真实HTTP边界、HTTPError/读取失败/timeout、call/attempt/重试计数与scope finally重置、记录异常不改变传输语义、实际Authorization注入/嵌套usage与metadata脱敏、凭证轮换新鲜性、test evidence真正脱敏且绝无生产fallback、probe零写及冻dict/四参契约。确认是否有默认生产scope根归属错误、可选import静默掩盖采集失败、raw_len/byte_exact/响应失败措辞虚报、捕获影响业务吞错误。T03变异测试是否确能证明真实接线。P0/P1精确path:line/AC-VC/触发/后果/最小修复，PASS或CHANGES_REQUIRED。

## 要求
只读无代码/配置/档案修改，不跑模型/外网/服务/build；可静态读证据，来源完整区分。基础修复未完的新失败是本key依赖债；未实施的T05不能扣实现缺陷，但T03提供不安全下游契约要报告。

## 未覆盖面声明
只审T03，不声称真实Jev/浏览器/全AC；说明已读与未验证行为。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-transport/**`

## 写入禁止面
- 所有代码/测试/相位任务文档/其他key/生产记录。

## 交付格式
report≤180行，结论/Findings/证据/风险/上下文与未覆盖；摘要≤30行，不复述worker自报passed替代核实。
