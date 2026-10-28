# R T05i transport凭证快照复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design §9凭证/实际HTTP安全。
- `packages/multi-workers/decision.py:1` CredentialSnapshot/_decide/_ensure_wire_redactor；`decision_backends.py:981` _authorization_key。
- workers/dd-timi-credential-snapshot/report.md全文/evidence/runs/T05i-timi-credential-snapshot/基线/RED/GREEN/measure；test_decision_timi_credential_snapshot全文。

## 审计目标
每逻辑调用解析一次、client/backend重试Authorization同快照、下次刷新；ContextVar finally复位/并发作用域/root安全，snapshot repr/错误/日志不secret。缺凭证快照绑定不能fallthrough活resolve，standalone容错导入不绕过。
wire production自注入redactor更新与caller-owned策略明确，门未接线正确披露，T05j仅mw/points在产不要判其最终PASS。_http_post四参/client8键冻结/probe/credential_status全局活解析保留。
RED7F2P真实实现前时序与tmp副本基线证据，147/197/172绿；loopback实际headers/capture泄漏与measure无值输出证据，不能当真实Jev。全check仅4子步缺tsgo/browser不称全部。

## 要求
PASS/CHANGES_REQUIRED，逐关闭表/新P0/P1/P2/path:line/最小owner面，只自身report，不源/test/服务/外网/build/真实凭证读取。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-timi-snapshot/**`

## 写入禁止面
- 所有源/测试/任务相位/旧证据/真实生产凭证/其他worker。

## 未覆盖面声明
门/caller-owned最终接线T05j未完成，真实Jev/平台/全仓check未验，静态日志非本人复跑。

## 交付格式
report≤110行，切片关闭/新项/证据边界/接线义务/未覆盖。
