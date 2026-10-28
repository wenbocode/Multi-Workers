# Research dispatch — 2026-10-24

## 权限与并行性
用户确认“按真实触发 就行”，允许正常派发路径触发真实dp1。使用已有dispatch_worker，不改决策配置、不绕过门禁、不额外发起服务探针。
三个研究RQ独立，源码只读，唯一证据文件互不相同；相位文档由PM串行写。均type=research、cli=pi、images=no，模型由dispatch.yml research=timi/deepseek-v4.1-flash解析，无模型覆盖。

## 实际派发结果
| task | decision_id | triage_type / confidence | 状态回读 |
|---|---|---|---|
| dpc-rq1-runtime-inventory | dp1-dispatch-type:45d4d6e4-ecf6-4bcf-bfec-11490075ee5d | research / 0.98，api | running |
| dpc-rq2-gate-authority | dp1-dispatch-type:735e59e6-0ade-4cbd-849c-07323f8cd1a4 | research / 0.94，api | running |
| dpc-rq3-history-regression | dp1-dispatch-type:56ca64ea-c7ff-4570-99ef-310ff194203c | research / 0.95，api | running |

三次派发均返回dp1 consumed=written/executed=written/settled=written。此为派发工具结果，不替代独立ledger/DOM验证，不证明研究完成或正确；HTTP尝试次数未单独取证，不声称恰好三个POST。
随后list_tasks(scope=key)确认三任务running；mw_status只读查询显示服务PID43656运行，未起停服务。

## 信封读回
三份workers/<task>/task.md已全文读回，type、独占write_face、goal.md及路径:行号种子、各type专属段与卡正文完整存在。
- RQ1 card_sha256: f75624ad6e99603b03f59345dd79715e40dd7b3c5fe71a5daa6c3603f7e77a4b
- RQ2 card_sha256: 3d928a3338c0921db6091d9864ea4f56d5c57e35ce6f5d329d85cf599946e79a
- RQ3 card_sha256: ebd8d43f61e3b692f2c6b355ca3ef47cb1539a92765ef6f4b2a520415ca89df0
生成信封write_scope包含本key evidence目录，精确write_face与任务卡约束均各一份唯一证据；未改运行守卫或放宽授权。任务自行额外发起决策服务请求、修改源码、配置、gate和生产ledger均被卡明确禁止。

## 未验证
三份研究报告尚未终态回读，研究结论未吸收；完整能力盘点、四门联合设计、14AC审核、实现和验收均未完成。没有部署、build/install/commit或签收。
