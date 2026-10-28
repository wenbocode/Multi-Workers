# R 入口与历史功能闭环合并验收

type: review

## 上下文
- goal `.agenticdoc/goal.md`；本key spec.md AC001、002、003、005、006，design.md两页签。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4496` decide入口。
- `packages/multi-workers/decision_monitor.py:1541` assets和history API；decision_dashboard.js:1 页面。
- workers/dd-command-closure/report.md与workers/dd-history-functional-ui/report.md全文；evidence/runs/T12a-command-closure及T11a-history-functional-ui。
- 用户要求功能闭环优先，合并review不滚动开非阻塞修复。T08a仅mw补monitor命令，T06仅playground，当前不争assets/TS写面。

## 审计目标
真正窗口dp list真实Python25项且无key可用，写执行参数spawn前拒绝，旧show/sign不退化，保留他人diff。monitor仅转发当前Python缺口由T08a负责，不能宣称真实开窗已闭合。
历史页面bootstrap token仅内存清fragment、列表筛选分页详情真正消费安全JSON，stored与output omitted分层、来源/unknown/inferred/未记录/usage缺值不補0。filters marks真实转发，XSS不注入DOM，无页面打开刷新模型请求。资产固定路由/CSP无安全回退，dp页签仅待接入诚实。
核RED真实性与10+12入口、112+skip和9资产/249邻接日志，Node最小DOM的fetch回放来源和真实HTTP区别，真实browser未验。UI接wire数据遗漏或使用性阻塞具体指出，不单开文案类研究债。T05q相邻资产失败归因只证并发时点不能直接无条件称伪失败，后续稳定联合验收保留。
只依据当前与归档相关函数核查，T08a正在mw命令接线不将未交付当成果。发现明确安全泄漏或主功能不可用标阻塞，其余集中账，给下一步T11b最小接口需求。

## 要求
PASS或CHANGES_REQUIRED，按入口和历史两交付关闭表，功能阻塞与非阻塞分列，证据边界。纯静态只自身report不源测试，不真实凭证，不运行浏览器模型服务build。旧日志非本人实跑，hash未重算明说。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-entry-history/**`

## 写入禁止面
所有源测试、旧证据报告、任务相位、真实凭证生产、其他worker。

## 未覆盖面声明
真实browser/Jev/平台/完整check未验，T08a和T06进行中，DP测试页签未交付。

## 交付格式
worker_file report.md最多110行，关闭表、阻塞和非阻塞、测试真实性、功能下一步。
