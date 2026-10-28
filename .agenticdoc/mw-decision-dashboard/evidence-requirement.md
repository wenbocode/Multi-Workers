# Evidence Requirement: mw-decision-dashboard

> DESIGN审核稿推导；不是已通过实现证据。RQ4/RQ5修订已吸收，待用户设计审核。

## 锁定指纹
- spec_path: `.agenticdoc/mw-decision-dashboard/spec.md`
- spec_locked_at: 2026-10-22
- ac_ids: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017
- vc_ids: VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018
- generated_at: 2026-10-22
- ac_fingerprint: `728632b37572`（spec全部17条AC原文按顺序换行连接，UTF-8 SHA1前12位；机械校验17/17映射）

## 全量证据清单
| AC | VC | 证据来源与充分性判定 |
|---|---|---|
| AC-001 | VC-001 | 窗口parser+runner真实入口无watched key、CLI集合对比；25项相等、unknown=0；不能只测helper |
| AC-002 | VC-002/018 | 实际history HTTP跨key筛选、dual/partition resolver同根；测试记录排除、完整旧载体 |
| AC-003 | VC-003/014/016 | 真CLI --book与本地HTTP/TS消费接线，book/call/decision/lifecycle显式ID；不是手拼事件fixture |
| AC-004 | VC-004 | 本地HTTP内部链测试+人工显式实际Jev提交证据，executor spy=0；本地server不能替代Jev |
| AC-005 | VC-005/015 | 全输出/持久化secret负向扫描与DOM XSS检查，原值0，明确脱敏标记 |
| AC-006 | VC-006 | Windows实际Chrome/Edge独立应用窗口证据、2页签、监听地址/端口；argv单测不足 |
| AC-007 | VC-007 | 实际占用端口/全占用/复用/旧实例/无浏览器；占用PID不变、零误杀、零假成功 |
| AC-008 | VC-008/017/018 | 隔离项目先真实sign再多种测试，生产所有文件前后字节/collect/hash相同；并发scope隔离/根归属 |
| AC-009 | VC-009 | 全25 typed registry骨架合法/非法/身份态/optional/生成物锁测试；不能只有样本dp |
| AC-010 | VC-010/008 | disabled/P0真实POST观察、executor0、授权不变；生产disabled及全局disabled零POST |
| AC-011 | VC-011/009/017 | 校验/凭证/HTTP失败/超时/记录失败真实路径；零非法请求、无模拟答案 |
| AC-012 | VC-012/003/013 | 真实两call一decision、多层重试attempt计数、duplicate submit零发送；mode/available不可替代消费事件 |
| AC-013 | VC-013/002 | 旧无原文/ID/来源载体，逐项未记录unknown/inferred；零重建原文 |
| AC-014 | VC-014 | 真人工answer/override/auth/sign入口与refresh/auto-sign各一次；理由/应答目标关联、机器误判human0 |
| AC-015 | VC-015/018 | 实际HTTP Origin/Host/令牌/角色/重放/超体/XSS与被动刷新负向，零模型调用/越根读写 |
| AC-016 | VC-016/012/005/011/017 | 真_http_post收到bytes与响应解码前bytes对比、成功/429/重试/超时/采集失败/invalidUTF8逐次记录；usage不估 |
| AC-017 | VC-001/010/015 | 窗口授权子命令拒绝、提交act/executor/archive参数拒绝；授权写入/业务动作0、旧sign回归 |

## 独立review增补证据
- VC-007：崩溃后残留实例/带owner启动锁的恢复，ECONNREFUSED+PID确死；超时/权限未知/PID复用/身份TOCTOU不清理，零误杀；双control项目同时开/独立停，端口和令牌零串扰。
- VC-009：dp17完整17条AC通过，按字段max_items测试上界及超界；dp23负delta合法，总state预算仍独立验证。
- VC-003：pending_stages_labelled=true，不能由无响应推断业务完成；CSP的default/base-uri/form-action严格基线；旧问题版本人工记录拒绝文案明确。

## Flow与异常证据
- §5.1 命令→白名单→实例健康→绑定→开窗，以及拒绝/冲突/浏览器失败。
- §5.2 HTTP→Host/Origin/token角色→只读或显式submit；无token/boot重放/坏Origin不能入模型链。
- §5.3 submit→独立start→校验→配置→内部非执行链→独立finish；每个拒绝/失败出口均有零调用或实际attempt事实。
- §5.4 生产入口→真实捕获→消费者→显式生命周期；人工入口只记录不授权，旧缺失不补写。
- 未finish的start只证明attempt started；不能声称已送达或未收费。

## 质检门禁使用说明
补充RQ4/RQ5负向验收：人工记录ref_seq/call/project/版本错误与无当次动态候选材料必须拒绝；新增当次候选快照后可合法校验，旧record不影响report/collect/verdict。成功与HTTPError/read失败均捕获；非env实际Authorization/config凭证零泄漏，序列化后行长受限，短写/锁超时不改变生产结果；test evidence_path不能落生产triage。未知根拒绝且无第二套档案，TS事件通过Python单写者入口，不能直接追加。

每条VC须有完整命令/退出码/输出与测试名，L2真实入口证据；不得仅依赖[VERIFY]文字或自报PASS。真实模型只人工明确提交，自动check/测试不付费。修改测试必须运行；代码check按仓库规则全输出，禁止未请求build/全量npm test/提交。未验证部署行为不得关闭AC-004/006/007。图、映射与指纹在设计冻结时机器校验。
