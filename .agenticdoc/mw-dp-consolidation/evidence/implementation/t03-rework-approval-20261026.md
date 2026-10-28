# T03定点返工人工批准（2026-10-26）

## 批准依据
用户对PM具体问题“是否批准在原T03隔离副本写面内定点返工这三项？不扩大范围、不改活源码或部署。”回复：**批准**。
三项为：缺失角色仍通过请求校验；prepared_at接受非ISO时间；永久锁旧TS入口的测试阻碍T04八入口生成。
这是本轮具体人工处理决定，不是假造dp4成功裁决。上一轮UNAVAILABLE/input-incomplete及meta.task_before问题、原请求时间勘误保留于t03-pm-handoff-20261026/report.md；没有decision_id，不写服务executed/settled回执。不重复询问dp4或修活工具链。

## 范围与并行性
仅原T03的四个副本exact文件；返工证据唯一写入evidence/implementation/dpc-t03-protocol/rework-r2/**（原T03证据允许面的严格子集）。原worker task/run/output/report/红绿日志、原卡和原implementation-dag.json均不改。新增tasks/isolated/T03-protocol-r2.md作为同一逻辑T03的执行尝试；7stage/36逻辑任务/原deps/53AC-VC不变。
当前全key队列无running（11:24:23轮恢复的实际list_tasks）；纯注册/validator与本卡测试共享同文件，返工一个coding writer串行，T04仍等待实际交接。不能把未列TS文件/生成器/CLI/框架加入本卡。不同文件未来任务仍按原DAG并行，不为填满槽位破依赖。

## 验证与禁止面
保存当前T03产物作为本轮before，按PM已实测hash核对；编码前读当前副本EOF，先补行为红测再绿测，不拿旧采集期rc2冒充各新反例。明确请求前准备与模型返回阶段：缺角色拒绝，但不提前要求尚未发生的choice/basis回答，不引入身份自报授权或强制人审。
时间按已有ISO/时区契约校验，不新设传输预算。交接断言不永久固定旧TS/全部unwired/旧材料矩阵；保留有效字节锁、字段/位置/非法输入校验及旧历史分类，不无条件skip/xfail/删除验收换绿，不将临时fixture当T04生成或跨层parity。
测试仅原卡两文件，私有fixture home/TEMP/project、最小env、禁pycache/plugin/cache、fake backend/零网络；源码/生成/子进程路径绑定副本，脚本与日志限新证据子目录。快照仅必要时用既有纯Python接口离线生成本卡JSON，绝不运行T04/T05生成器。
仍不授活源码/部署/安装/check/build/restart/config/policy/gate/brake/ledger/grant/预算/watchdog/凭证/goal/spec/其他key/commit/push或phase/QG/签收权。新派发默认coding角色配置，不pin模型，不提前写running/done。

## 后续
返工终态全文回读及实际差异/反例/红绿/hash核对后ack，再判断T04交接。批准返工不是三项已修复或S1通过；真实人面/H12/vision/TS依赖等价性和全L2仍各自门禁。
