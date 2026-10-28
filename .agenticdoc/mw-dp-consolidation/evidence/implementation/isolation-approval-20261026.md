# 隔离实施边界批准与并行分析

## 结论
用户对上一轮具体问题答“是”，随后两次“继续”。批准在`.agenticdoc/mw-dp-consolidation/implementation-worktree/`独立副本继续既有交付实现/测试，仅映射已批准逐文件面；不授权回移主树、活配置迁移、安装/build/reload/restart/commit/push。直接用户批准，不造模型decision_id/receipt。本key仍EXECUTE，53AC/VC及原设计字节不变。

## 证据
前置：T01/T02实际done/exit0、全文回读并acked；联合校正见preflight-pm-disposition-20261026.md。10:26:10恢复audit EXECUTE各项PASS；switch_key持有本窗claim；scope=all任务列表本次完整输出未见running。当前原工作树新鲜dirty清单与旧报告不同，必须重新byte/hash/diff快照；不得假定没人手动修改。

## 并行性与实施约束
副本构建/路径映射/单源快照由PM串行，避免半副本供worker读取。T03纯协议唯一frontier；T04依赖其同registry/shared test稳定，不能并写。后继仍原7stage/36task DAG，不重开两research或新增重复调研。原卡和manifest作为历史编排保留；新增isolated卡/manifest逐一保留source路径及卡hash、原AC/VC/依赖/测试argv，映射实际cwd和唯一write_face。副本源码是普通独立文件，无硬链接、symlink/junction回活源码；依赖暂不创建链接，后续TS/完整check前验证实际解析及等价性。

## 残留与未验证
S0的活源码与新Python/旧TS即时冲突通过本次用户批准改为不切换活树的副本路线。仅允许证据充分后放行纯协议T03/T04；不宣称真实human/H12来源、运行窗口/bundle或活config验证完成，相关consumer/恢复/signoff及最终S4/S6验收仍受原资格硬门约束。当前构建尚未执行，无产品红绿或通过；新增不可修改原授权外源文件。

## 上下文来源
本轮用户确认、现有联合设计/plan/两preflight、工具switch_key/audit/index/list_tasks及新鲜git状态。只读镜像不复制活账本、凭证或他key运行对象；必要元信息不获产品修改权，框架canonical脚本副本只两文件可变，其他companion只读。
