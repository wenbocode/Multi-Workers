type: coding
deps: [T03, T04, T05]

# T06 冻结发送、反解与continuity接回

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。读spec AC-009/010/011/013、design §4/5/7、docs详细设计§10—12。依赖T03/T04/T05；实施前核mw-pm-dp-continuity与相关活key的完整源码/未提交写面，不碰其认领。

## 目标及对应AC

AC-010、AC-011、AC-013，支撑AC-009和012。真实发送使用冻结完整body，返回按同版全部原因反解，原身份/权限/预算/停止语义保持。

## 工作项与交付

1. 使用既有后端builder/headers及原启用模式，保存与Request.data相同的字节；不在最后一层重新截断材料。
2. 原matter identity、semantic fingerprint、wire hash分别管理；仅prepared_at变化不生成请求，并发同语义只有一次真实发送。
3. 原预算跨准备/等待/返工/模型调用连续；已发未获完整响应保留transport-unknown，不盲目补发或因confidence重试。
4. 官方解码后按同版pair-map恢复choice/basis和全部原因/剩余项；未知wire/错revision拒绝业务采纳。
5. 接回再核当前身份/范围、来源、取消/余量与分支条件；available/decode_valid/business_accepted/executed分开。关闭/不可用/准备失败沿原continuity合法接回，不新增审批/全局等待。

## 写入允许面

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。沿用 logical_id 回放、来源漂移拒绝、原预算、手工控制、handoff 和既有写者。验证客户端与后端的重试计数，区分未发、明确拒绝和已发结果未知；后者在无幂等证据时不重发。按冻结配对增加结构化全部原因/剩余项，保持现有 choice/basis 接回合同。

- packages/multi-workers/decision.py、decision_backends.py、decision_wire.py、decision_validity.py、decision_lifecycle.py及本任务新增冻结/接回适配模块。
- `packages/multi-workers/mw.py` 的 lifecycle CLI 只在现有业务 writer 前查同次请求和当前调用身份。`packages/multi-workers/autopilot/conductor.py` 只补默认 PM gate 客户端的调用捕获归属。
- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts、decision-followup.ts及shared/decision-handoff.ts的相关接线；写面须与活key协调。
- 新测试packages/multi-workers/test/test_dp_material_transport_v1.py及必要TS continuity定向suite。

## 写入禁止面

原业务writer准入规则、其它key索引/认领、pi核心、全局配置/凭证/依赖、docs及历史原始响应。不得为修通链路删除意图明确的旧功能。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_transport_v1.py"]
```

## 补充验证与完成判据

Python测试用隔离本地替身传输；TS指定suite从coding-agent包根运行harness/faux。VC-010/011/013值须来自真实发送/接回链，并含并发/锁等待/取消/源漂移/不足余量/结果未知/DP关闭正反例。保存请求响应原字节及无密钥捕获；禁止访问真实远端。交output.md说明原continuity差异为0及实际未跑项；未来代码交付运行npm run check。

## v0.5范本引用与逐项对比（必验）

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。复用窗口控制、claim 拒绝、原 PM 分类和预算连续性。离线核禁用、未配置、DNS、接回 task_after 错绑，观察实际尝试数及原主体接回。两条历史补录保留事后审计来源。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例，重点dp-QG与dp-w-check-task。对照冻结决策本/同版映射、body、原始返回/官方及本地反解和真实接回；全部原因/剩余项、原权限预算及未执行须保留。新payload只绑定该次faux返回。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
