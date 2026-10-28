# KDR: mw-decision-dashboard

## R（需求）
- 用户明确要求独立新 key，不合并旧 key。
- 已定：项目决策历史看板；人工/模型自动来源区分；决策本、实际调用、返回、吸收、应答详情；独立 DP 测试页签走内部真实 Jev 调用。
- 用户已确认：测试真实调用但不执行业务动作、不改变授权；人工含回答/覆盖/授权调整/签收；历史缺失显示未记录。
- 用户指定：`mw decide monitor` 开启看板。
- 用户最终确认：浏览器独立应用窗口，端口非常规；测试独立记录不影响生产签收；补齐全部 DP 输入契约，允许人工观察关闭/P0 DP但不改授权/不执行。
- spec 已按逐轮确认锁定 AC-001..017；非常规端口的具体高位范围、服务生命周期和访问校验由 design 决定，不以非常规端口冒充安全。
- 根因初步事实：ui-bridge.ts:4474-4533 窗口 parser 仅 show/sign，因此 dp 被拒绝；Python CLI 实测 dp list 返回 25 DP、rc=0。
- 已派三组独立研究 dd-rq1-command / dd-rq2-trace / dd-rq3-playground。
- RQ-1 已完整回读并 ack：窗口缺口自首版存在，serve 重启不会修复；只读 dp 转发必须先于 key 解析，禁止通用透传 on/off/set/apply 绕过守卫。RQ-2 已完整回读并 ack，RQ-3 已完整回读并 ack。
- 修正 PM 先前成本说法：浏览器只可复用静态 HTML 样式/发布资产，可提交测试必须新增交互接口；不再断言浏览器整体成本更低。
- RQ-3 新增决策点：测试落账隔离生产签收；21 DP 业务字段契约未声明；disabled/P0 人工观察测试的授权边界。
- RQ-3 的“settle 无生产 writer”与 RQ-2 的 pm-orchestrator.ts:986-1024 证据矛盾，后者有明确调用位置；不采纳 RQ-3 此条。其“重新 build_payload 即实际载荷”建议不足以证明实际发出，必须在发送边界采集。
- 三组 SPEC 研究完成并 ack；最终范围经用户确认，进入设计准备，不进入编码。
- RQ-2 对范围的重要修正：现有档案不存请求/返回原文，人工覆盖无生产写入者、吸收在 TS 旁证里；本需求须包含向前采集链补齐，不能只渲染既有 JSONL。
- 区分调用与决策 ID：dp1 历史同 key 折叠多次调用；新链需独立调用标识及明确关联，旧数据不得伪造补齐。
- 来源标注：refresh 是机器动作；自动签收不是人工；mode/available/task 头不等于采纳执行。
- 初次派发被 research evidence 门禁拒绝，补写真实已读事实后通过；并行派发因未声明写面被拒绝，RQ-2/3 补唯一证据与自身 worker 目录后通过。

## A（架构）
- D001 独立monitor/Chromium app：否serve耦合（凭证与可用性隔离）；43170..43269独占绑定，认证复用不误杀。
- D002 独立生产wire/lifecycle旁账及test scope：否扩旧archive（幂等签收不变）；实际bytes边界采集，call/attempt/decision/submission区分。
- D003 typed required+optional registry与内部观察seam：否业务散文/复制client门（单一输入判定）；全局disabled仍零请求，不执行业务动作。
- D004 显式人工记录/消费元事件：否无来源推断（补AC-003/014真实链）；record answer/override只是记录型入口，不授权/不执行，具体契约待RQ4。
- 三组设计已回读ack，合并18VC与17AC映射；并行补RQ4人工/根归属、RQ5安全采集/短时锁/context。未冻结前不编码。
- PM纠错：dp21/dp22研究ID正确；attempt-start不证明送达；model回答来源不可只看HTTP2xx/available。

- 设计独立复审PASS（8/8 closed），全部报告已ack；经advance_phase由DESIGN进入PLAN。
- plan.md五阶段候选DAG：根/旁账→typed契约/观察→生产消费来源→安全窗口→真实链与部署验收。四条非阻塞建议落实到计划；编码卡与EXECUTE门禁尚未完成。

## I（实施）
无代码修改。用户提示 stale serve，使用 CLI stop/start 等效重启；后续 status 确认 running PID 39568、serve code fresh。这是独立运维处理，不是 dp 报错修复。
