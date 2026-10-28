# 联合设计候选文档检查（非设计验收）

## 本轮事实
- RQ18～22五任务实际done，唯一证据与终态回复已吸收/ack；最近list_tasks确认五行done/acked，本key无running。RQ15/16原needs-clarification/exit2保留。
- PM整合design.md的D001～011及F01～03；仍缺完整H场景/签收/恢复Flow、精确接口/角色/授权/版本绑定、Coverage/VC/53AC映射、证据需求与精确候选写面。用户联合设计批准尚无。

## 实际命令与结果
1. `python .agents/skills/agentic-task/scripts/check_mermaid.py .agenticdoc/mw-dp-consolidation/design.md`
   - rc=0：`MERMAID GATE PASS: 0 error(s), 0 warning(s)`。
2. 临时stdlib文档脚本 `dpc-design-doc-check-20261026.py`（只读本keySPEC/锁定快照/design）
   - rc=0：锁定SPEC当前字节SHA256仍 `cfe737d29aed2d0c4e79d8b02107f754f254a225bb21ea8d900eaa5ba289d006`，与锁定快照逐字节相同；AC表恰001～053；D标题恰001～011；3个Mermaid块。
   - 原单行版本rc=1：PowerShell处理反引号使正则三反引号变一反引号，最后块计数断言失败；之前SPEC/AC/D断言已通过。改用临时脚本避免shell转义后重跑rc0，不是源码或SPEC修复，不隐藏原失败。
3. `python .agents/skills/agentic-task/scripts/audit_phase.py mw-dp-consolidation`
   - rc=0：phase=DESIGN，design: PASS，VERDICT: PASS。此为当前相位一致性检查，不是联合设计/VC/53AC语义验收。

## 未验证与边界
没有运行产品测试/build/check/install、真实provider/CLI裁决、浏览器或共享服务起停；未部署、未执行签收/恢复/预算授权，不改源码/框架脚本/活配置/gate/ledger/刹车/旧历史。本keyPhase仍DESIGN，不因上面机械检查进入PLAN。研究文件全文回读不证明PM已独立阅读全文源码或完整caller/安装内存身份核验。独立旧26AC/monitor8AC及其他债不关闭。
