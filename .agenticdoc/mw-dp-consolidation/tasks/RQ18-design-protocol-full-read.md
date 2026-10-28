---
type: research
write_face:
  - .agenticdoc/mw-dp-consolidation/evidence/research/design-protocol-full-read-20261026.md
---
# RQ18 — 补核完整协议与生成契约

## 上下文
`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md:20`，完整53AC已锁。当前DESIGN，用户要求继续联合设计，未批准实现或精确源码写面。RQ13只读部分协议，RQ15/16只覆盖部分角色/材料校验。本RQ不重做职责讨论，仅补核协议调用链并提供可实施的设计替代方案。旧研究作为问题线索，不当独立证据。

## 要求
1. 时间盒25分钟。全文分段读 `packages/multi-workers/decision_points.py:1`、`packages/multi-workers/decision_backends.py:1`、`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:1`，续读到实际EOF；主文件未读范围必须明确，不能宣称完成全链审计。引用具体path:line，区分源码事实、目标要求、建议、未验证。
2. 核注册→材料闭集/模型投影→候选构造→发送/答案校验→工具结果/回执。提出八入口统一协议字段候选：业务material、本地identity/meta、PM预拟note、模型理由、实际执行/settled、版本/关联的分层。角色由真实发起主体和工具资格检查，不由route改变；vision不能以unknown推定资格。
3. 至少比较两种合法技术方案并给pros/cons/推荐：现有Python注册单源并生成TS判别契约，或共享纯协议描述由现有注册/工具消费。八行活动表与只读退役解释可以讨论；不得保留旧编号可调用别名或旧dp3运行兼容。旧动态限制不迁移到dp-auto；dp-route用七目标静态枚举是合法候选，不能说七目标天然与所有机制冲突。现有传输大小/资源边界与旧2..5/cN业务限制分开。
4. 逐项给八入口材料/问题/选择校验候选；特别核dp-sign-key三数组[]≠null、dp-w-check-task三固定选项、dp-auto候选来源和理由依据、gate note分列、route选择不代业务结论。失败不默认首项或approve。零业务执行不等于禁止真实安全失败审计。
5. 输出候选文件/生成器/测试接口与AC001～004、012～014、040～044、050～053的隔离测试断言。仅设计，不运行测试、CLI决策、provider/服务探针；不读活配置/gate/ledger/签收/凭证或其他key运行材料，不改源码、配置、框架脚本、旧报告或PM相位文档。

## 交付格式
先用worker_file写唯一证据，再读回核真实文件。证据与最终回复必须分别有独立Markdown标题：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`，不能只写加粗内联标题。最终回复在证据节明确引用完整路径 `.agenticdoc/mw-dp-consolidation/evidence/research/design-protocol-full-read-20261026.md`，另列key内路径 `evidence/research/design-protocol-full-read-20261026.md`；不要只写basename或把落盘说明当机验通过。不造VERIFY/测试成功，不声明设计/AC/QG/签收通过。

## 唯一证据文件
.agenticdoc/mw-dp-consolidation/evidence/research/design-protocol-full-read-20261026.md

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/research/design-protocol-full-read-20261026.md

## 写入禁止面
除此证据外全部文件。不建report.md，不人工改框架回执。使用read读取文件；Windows shell为PowerShell，命令不用&&，不以Get-Content输出源码替代read。禁测试/build/install/commit及服务起停。
