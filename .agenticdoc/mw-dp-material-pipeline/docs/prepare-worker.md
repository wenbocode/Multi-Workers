# prepare Worker：统一准备流程与可区分性合同

状态：设计，未部署。完整机器合同见prepare-worker-contract.json。本次所有规范/检查由Codex编制与自验，没有启动prepare Worker。

## 输入、模型与隔离

prepare_dp输入当前DP、原事项/task/run、scope、限定source handles、原budget_ref和prepare_model。真实身份由host既有通道绑定，不能接受调用方自填owner字符串充当授权。原PM/实际Worker可直接准备简单材料，也可委托助手；dp-w-check-task仍只能由实际Worker确认自身状态。

prepare_model通过现有任务卡model头选择注册provider/model，记录请求与实际值；回退只能用已有显式允许列表。决策模型另为jev-latest。读取限定原任务范围、拒绝规则和累计预算，写入只限本prepare run产物目录并由受限host writer执行。禁止任意shell/网络、产品改动、认领变更、扩大权限、改AC/VC、持有决策密钥、写QG/签收或冒充独审。

QG先取得当前版本独立review，再逐适用AC/VC核对；核对完成不代表全部通过。sign带目标/偏差及当前同对象/范围/版本QG业务结论；缺失或过期如实报告，不能补pass。desc最多10句/1000tokens，准备者保留每句来源与未知。

## 工具顺序

| 顺序 | 工具（均为拟议接口） | 产物与出口 |
| --- | --- | --- |
| 1 | prepare.begin | 绑定真实原主体/事项/执行/范围/原预算和指定模型 |
| 2 | prepare.read | 读限定来源正文，记版本、范围、新鲜度和未读限制；可有界补取 |
| 3 | prepare.check_inputs | 核事实、目标、所有合法候选；QG先独审再逐验收/验证项核对；sign核当前同范围QG |
| 4 | prepare.compose | 组织desc、结构化材料和合法单选；不把推荐写成事实 |
| 5 | prepare.check_discriminability | 对冻结草稿逐对核目标取舍、区分证据、反转条件；auto再核路径/信息价值/后继/停止/全程上限 |
| 6 | prepare.validate | 核长度、术语引用、候选覆盖、来源/角色/预算；必须持有与草稿及来源同版本的可区分性报告 |
| 7 | prepare.publish | 原子发布限定目录内产物；未过检查不可发布为ready |
| 8 | absorb_dp_preparation | 原主体核语义和当前绑定；吸收不等于发送、决策或执行 |
| 9 | 原host发送与接回 | 冻结完整请求，按原开关/预算发送一次，反解同一配对，再核真实分支 |

compose后任何内容/目标/候选/来源/预算变更，使可区分性报告和后续校验失效；回同一预算下的相应准备阶段。needs-evidence可回read补取，equivalent由原主体按现有规则确定是否需要调用DP；不能删合理候选、编造概率或为了confidence重发。

## 可区分性报告

报告包括candidate_coverage、decision_unit、priority_source、pairwise比较、reversal_conditions、unknowns、path_bounds、status、具体缺口与可取证方向。两至五个auto候选检查全部无序对，不能只检查作者推荐与一个弱对手。比较不是胜负证明；源忠实性和取舍仍由原主体语义核验。

通用检查保留固定DP闭集。两个fix配对可返回同一fix业务结论但不同原因集合，此时检查原因/范围的差异而不是误判重复业务选项。纯等价候选先由原主体确认是否合并；prepare不能私删已有合法功能。报告/预期答案留本地，模型只看必要目标、证据和完整判据。

## 异常与连续性

越序、报告绑定旧草稿、改源未重验、候选不足、路径超原期限/刷新额度、后继无触发条件/循环、停止缺失、未知当已知、缺关键偏好都要给字段和来源级错误。QG/sign不能因可区分性通过跳过独立review和验收链；准备助手也不能代替真实Worker自评。

当前示例校验器检查机械一致性和已声明的来源支持，不理解任意自然语言，不证明生产工具守卫存在。没有目标模型精确token计量时只记录估计预检，不能称已实现1000-token硬限制。请求/返回记录是合成API实验，真实原身份、授权、新鲜度、取消和执行余量仍需生产host检查。

发布产物包括preparation、desc、material、pair-map、source-manifest、quality-report、discriminability-report和output；字段绑定来源、事实性质、变换与未读限制。原主体通过absorb_dp_preparation核当前事项/范围/模型/来源/候选/预算并吸收，返回preparation_status和真实dp_result或null；接受材料不等于已决策，更不等于执行。

全部读写/模型消耗/等待/返工沿用同一原预算，不因新卡或新turn刷新。助手不可用时原主体可在原权限内直接补取/准备或合法本地处置，不新增全局运行闸或用户审批。

完整机器合同：[prepare-worker-contract.json](prepare-worker-contract.json)。
