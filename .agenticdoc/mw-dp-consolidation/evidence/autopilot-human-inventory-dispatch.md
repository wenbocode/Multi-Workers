# Autopilot全量人工决策盘点：派发记录

## 用户原则与范围

最新要求：默认先尝试DP自动决策，每项上报人必须证明人工必要性；先列全量当前决策，再判断dp7/dp15/dp20覆盖，讨论合并或增加。目标态不再默认保留旧人工面。这里只研究，不据原则直接写入授权、改变硬门或部署。

## 并行分析与派发

当前无其他running worker；现有RQ1/2/3已终态并ack。新增问题彼此只读共享源文件，写面按唯一证据区分；PM串行合并、去重、交叉核验，不将原RQ2的局部取证冒充完整清单。

| 任务 | 范围 | 唯一证据 |
|---|---|---|
| dpc-rq4-autopilot-human-gates | 六类显式gate生产/问题/消费/自动面，不仅kind名称 | research/spec-autopilot-human-gates.md |
| dpc-rq5-autopilot-human-recovery | 非普通gate、失败恢复、pending-review、reattest、合同变更、xkey深链 | research/spec-autopilot-human-recovery.md |
| dpc-rq6-autopilot-human-pm-framework | TS PM/框架phase/质量/签收的人类选择，以及三DP实际材料/动作覆盖 | research/spec-autopilot-human-pm-framework.md |

全部type=research、images=no、pi、按dispatch.yml默认research=timi/deepseek-v4.1-flash；不pin模型。明确全文审计所覆盖文件、15分钟预算、报告<=220行、正文与最终回复均四节。不授权worker真实decision/provider探针、测试、服务/签收/源码写。

## 实际派发及保留的拒绝

- RQ4正常派发，工具报告dp1 API置信度0.97；consumed/executed/settled written。task.md decision=`dp1-dispatch-type:46a0b6c2-e2f2-4f1e-bd77-e5b058884844`。
- RQ5正常派发，工具报告dp1 API置信度0.85；consumed/executed/settled written。task.md decision=`dp1-dispatch-type:69142b5b-733d-49cb-9edb-a54f41d1f082`。
- RQ6首次被write-face-overlap拒绝，sample=仅唯一证据文件，明确无task目录/queue副作用。原因是卡“写入允许面”正文使用泛指而非路径，解析后与RQ5文字相同；不是研究问题实际重叠。仅修未派发的RQ6卡允许面为完整唯一文件路径，未关守卫/扩大权限，随后正常派发。
- RQ6成功工具回执未附dp1建议/id/收据；task.md也无decision行，不猜测第三次请求或第三组收据。
- 已全文回读三生成task.md：RQ4/RQ5 write_face分别解析为泛指词，RQ6含完整路径及附带正文；此载体不精确，保留原快照/card hash，不静默修改在途任务。任务指令与write_scope仍明确独有证据文件；若后续发生写入拒绝，以真实错误处理，不豁免守卫。

## 验证边界

派发与running不代表研究完成或全量覆盖。最终需逐份读回原output/run/证据并ack，标阅读覆盖与未覆盖；调查报告不直接批准接口/权限/合并方案。
PM本轮全文补读advance.py与closure.py：前者仅包装规范phase脚本，后者已有拒绝achieved草稿的内容哈希授权修复；不能把机械整改全部算成人类决策。尚未据此完成全链结论。
