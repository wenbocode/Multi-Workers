# 规划交付（当前v3，v1/v2为保留历史）

当前交付入口：[v0.5八DP四段范本](docs/reference-records/index.md)。8类DP、原版八例加优化auto共9例，含完整本地决策本、实际请求、真实回包/同版反解和当前PM参考裁定，另有9份expected-checks供开发校验。v2强制新增真实采集要求已撤回。

2026-11-19按用户“新建key但先不实现”完成。本key仍是Codex-lite SPEC，规划后释放认领，不标DONE、不推进执行。

- docs/是当前v05设计与必要依赖的原字节快照，共150文件/1,515,377字节；复制清单/哈希一致，未复制html.qa截图目录。
- spec.md为14条实现AC的draft；design.md为架构/接口/状态/14 VC及100% AC映射；没有伪造用户锁定、实现完成或独立复核。
- plan.md、task-index.md和tasks/T01—T09覆盖合同/来源/投影/prepare/业务比较/传输continuity/monitor/集成/独立复核；任务全部planned、not-dispatched、verification not-run。
- evidence-requirement.md逐AC明确未来需要什么源码/验证/独立证据，历史API实验不代验收；QG缺reopen、精确token计量未确认等原设计缺口继续保留。
- 仅做副本、链接、AC/VC/任务覆盖与无环、Mermaid机械检查；结果见evidence/planning/verification.json。临时检查器原文留checker-source.txt，不作为产品代码。

未改产品源码/测试/依赖，未派工、构建安装或调用模型，未运行任务卡验收命令。后续继续时claim本key并先核现场，再按当前PM流程进入实施；本文件不授予实施权限。

## v2补充：八DP真实样例与派发/业务结果

用户反馈后追加AC/VC-015—018，补acceptance-sample-design.md和8个待采集场景；增加T10样例/分支/比较验收合同、T11原PM未来真实采集，T09等T08+T11后再最终独审。规划现为18 AC/VC、11张卡。

每DP真实闭环要求完整请求/原始jev返回、实际task/run/Worker结果/PM接回或适用业务writer及零派发观测；另有28固定业务分支、auto路径/八DP边界离线覆盖和8份逐项对比。当前真实0/8，结果字段为空；本轮没有采集、调用或派发。v1原文和报告保留在evidence/planning/revisions/v1。

## v3用户澄清：现有v0.5四段全记录

已交付docs/reference-records及原v05图表中的8DP/9案例：本地决策本、实际输入、真实原始返回/反解、当前PM参考裁定与开发校验向量。PM部分是现在撰写的参考意见，未伪造历史生产执行。T11和live8强制前置撤回，保留旧版本；10待执行卡+1撤回记录，SPEC不变。无新API/派发或产品实现。

文档/参考资产自查通过：9例请求/回包与来源逐字节一致，111个原案例/捕获文件和150个冻结副本哈希不变；18 AC/VC映射完整、10待执行卡无环、T11撤回。原图表23页/70页签，桌面和移动无横向溢出/断锚，PM参考及真实返回可见。证据见[evidence/reference-records/verification.json](evidence/reference-records/verification.json)与visual/；这些检查不代表产品实现验收或独立复核。
