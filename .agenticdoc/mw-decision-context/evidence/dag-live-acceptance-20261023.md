# 真实dp1派发与DAG验收记录

用户明确授权一次真实Jev dp1和只读worker，服务由用户重启；PM检查mw PID43656、phase EXECUTE audit PASS。通过正常dispatch_worker入口派发dc-dag-acceptance-20261023，未直接写生命周期事实。

## 实际记录
- key: mw-decision-context
- task: dc-dag-acceptance-20261023
- decision_id: dp1-dispatch-type:562d4262-e6e5-40be-9764-d39062722c00
- opaque_id: h-9d42ba57fcdb943c920f
- logical_id: 562d4262-e6e5-40be-9764-d39062722c00
- 发起时间：2026-10-23T07:49:38.877Z
- Jev真实POST返回HTTP200，research，confidence0.62，latency1659ms。
- 请求1441B，响应329B，reader capture均ok、byte_exact=true，truncated=false。
- 请求含model/state/questions。state只含合成任务目标要求交付，无凭证正文。

## 十节点读回
通过evidence/inspect-dag-acceptance.py调用正式decision_history.load_history/as_dict(detail=True)，未注入空secret替代生产安全策略。
key/role/dp/input/request/model/response共7节点observed；decide为failed（low-confidence）；receipt/action为missing。processing_state=failed。
模型HTTP成功不等可消费决策；低置信度被策略升级，不能降低阈值或补造消费/执行。未额外发模型请求。

## worker结果
18秒needs-clarification；唯一研究证据真实存在且四段标题齐全，但worker自身report/output未按恢复契约成节，故终态不改done。已全文读output与唯一证据并ack。任务事实是字段调查完成，不代表DAG通过。

## 用户验收入口
monitor生产记录筛选key=mw-decision-context、DP=dp1-dispatch-type，找task=dc-dag-acceptance-20261023。本记录用于检验真实请求/响应与失败/缺失节点，不是十节点全成功案例。

## 后续
日志精简/完整questions测试页为用户批准设计修订，尚未实施。本次还暴露实际dp1 criteria旧说明：coding为“需要写代码或改代码或跑命令”，research为“只做检索取证不改代码”，review为“审计别人已完成的产出”；留作与已批准业务说明核对，不在此次验证擅自修改。若要再发成功链必须说明低置信度事实并获追加真实调用许可，不以重试掩盖本记录。
