# mw-dp-material-pipeline

状态：仅规划，未实施。用户于2026-11-19要求新建key、复制当前设计，再编写spec/design和规范任务；本轮没有代码改动、派工、产品测试或模型请求。

| 文档 | 用途 |
| --- | --- |
| [spec.md](spec.md) | 需求、范围、18条验收标准；draft，含v0.5四段范本/开发校验 |
| [design.md](design.md) | 架构/接口/状态机、VC、AC映射与实施决策 |
| [plan.md](plan.md) | 任务依赖、写面冲突、阶段交付和后续实施前提 |
| [task-index.md](task-index.md) | 规范任务卡索引；全部待执行，未派发 |
| [证据要求](evidence-requirement.md) | 每个AC需要什么实现/复核证据，当前均未取得 |
| [四段范本规约](acceptance-sample-design.md) | 用户澄清后以v0.5已有完整记录作开发范本 |
| [范本索引](acceptance-samples.json) | 8DP/9已有案例，原版/整合版cohort和PM参考分开 |
| [设计原件](docs/DP材料准备与决策链路详细设计.md) | 当前详细设计逐字节副本，17节 |
| [字段字典](docs/DP字段字典与来源明细.md) | 八DP共464个实际模型字段的来源与发送规则 |
| [真实请求/返回附录](docs/DP完整请求与真实返回附录.md) | 历史合成API实验，不代替本key实现验收 |
| [流程记录](codex_doc.md) | Codex PM轻量生命周期与接续说明 |

## 文档优先级与当前边界

spec规定本key要达到的结果，design规定如何实现，plan/任务卡规定工作分配；docs保存2026-11-19复制时的设计与实验基线。发现差异先记录决定，不改写原捕获。尤其QG历史请求缺reopen，必须作为未来修复与负例，不当成规范豁免。

docs复制了v05中150个文件、原字节和必要相对链接，未复制大体积html.qa截图目录；已有qa.json/manifest仅为历史验证元数据，不能冒充本key复核。复制清单与SHA-256见[evidence/planning/docs-manifest.json](evidence/planning/docs-manifest.json)。

本key使用Codex PM codex-lite，保持SPEC；spec/design/plan/任务卡是用户明确要求的实际规划合同，不代表已走完整MW SDD阶段或获准执行。未修改普通AgenticTask机器阶段。规划完成后释放认领保留SPEC，后续在用户要求继续时claim并核对现场后才进入EXECUTE。

v3纠正范围：现有v0.5记录已组成四段范本，T10负责未来接入离线校验；T11新真实采集要求撤回，10个待执行任务+1撤回记录，T09不再等live采集。前三段实录、第四段当前PM参考均有明确来源，不伪造历史执行。

开发范本：[八DP四段全记录](docs/reference-records/index.md)；[现有v0.5图表](../mw-dp-runtime-reference/v05/DP引用与术语_动态演示.html)按DP查看四个页签。
