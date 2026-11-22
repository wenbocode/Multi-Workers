# 任务卡 v3

全部planned / not-dispatched。用户要求先规划，当前不执行。控制/未来目标工作区均E:/gitlite/Multi-Workers；每卡在实施前读取完整源码、核其它窗口热文件并确认写面。未来新测试路径是该卡应创建的交付，不代表文件现已存在或已跑过。

| 卡 | 主题 | 依赖 | 主验证 |
| --- | --- | --- | --- |
| [T01](tasks/T01-contracts.md) | 合同/注册表/固定候选 | 无 | VC-001、VC-010 |
| [T02](tasks/T02-sources.md) | 来源正文/追溯/压缩 | T01 | VC-002、VC-004 |
| [T03](tasks/T03-projection.md) | 八DP投影/desc/引用术语 | T01、T02 | VC-003、VC-004、VC-005 |
| [T04](tasks/T04-prepare-worker.md) | prepare隔离/顺序/模型/发布吸收 | T01、T02；默认等待T03释放热文件 | VC-007，支撑011/013 |
| [T05](tasks/T05-business-checks.md) | QG/sign前提、auto比较与路径 | T03、T04 | VC-006、VC-008、VC-009 |
| [T06](tasks/T06-transport-continuity.md) | 发送/去重/预算/反解/接回 | T03、T04、T05 | VC-010、VC-011、VC-013 |
| [T07](tasks/T07-monitor.md) | 四段回放/原始响应及PM接回可见 | T06 | VC-012 |
| [T10](tasks/T10-sample-contracts.md) | 已有v0.5四段范本消费/语义校验 | T01 | VC-015—018 |
| [T08](tasks/T08-integration.md) | 离线生产链、参考消费、必要回归 | T01—T07、T10 | VC-001—013、015—018 |
| [T11](tasks/T11-live-samples.md) | 已撤回，不再强制新真实采集 | 无，不执行 | OBSOLETE |
| [T09](tasks/T09-independent-review.md) | 当前实现和现有参考独立复核 | T08 | VC-014及全部AC |

统一交付：当前源码改动、原始验收输出和本run output.md；明确变更、AC/VC、实际命令/目录/退出码、失败/未跑/遗留。作者自验不称独审。所有副本/历史捕获只读；不得重写旧响应、改全局凭据/依赖锁或顺带修其它key。

结构化规划索引见[tasks/index.json](tasks/index.json)，用于核依赖/覆盖/未派发状态，不是实际队列、授权或运行回执。

待执行卡主验收命令为单个JSON argv；补充命令同样必跑。Python从仓库根、TS从coding-agent包根用harness/faux跑指定suite；T11已撤回，没有可执行验收命令。当前产品测试均未运行，但v0.5已有9份四段参考资产已整理，不能再以未来真实0/8采集阻塞该交付。

用户澄清v3：10项待执行、1项撤回记录；T11不可派发，不存在live8采集前置。现有四段范本已位于docs/reference-records。

## 逐项复核补充（2026-11-19）

直接采用[v0.5范本索引](docs/reference-records/index.json)及[四段逐项对比合同](reference-comparison-contract.md)。T01—T10全部直接引用同一套资产；T01—T07交职责内字段证据，T10定义原件回放及报告校验，T08交9例×4段共36行JSON/Markdown对照与原始观测，T09逐行复核。原件回放、当前实现差异、负例拒绝和PM语义分别核实；缺段/串版/无依据差异/未验证不通过。T11继续撤回，产品测试/实施仍not-run。
