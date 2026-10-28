# R monitor服务实现安全审查

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement全文。
- `packages/multi-workers/decision_monitor.py:1`（1830行）、`packages/multi-workers/test_decision_monitor.py:1`（38测试）；workers/dd-monitor-service/report.md及evidence/runs/T10-monitor-service/verify-summary.md/原始日志。
- mw_common owner/lock与decision_wire实际API；T07b修复仍在产，T05仍在产，T06未交付，T11未开始。

## 审计目标
完整读monitor/test/接口，独立核查43170..43269 bind-and-hold/Windows exclusive/未绑定外网、端口耗尽不kill；start lock owner确死才恢复且锁内身份重读；stale只有ECONNREFUSED+PID确死+身份重检才移动，健康timeout/permission/PID复用/协议版本/code/project不一致均保留不清理。是否移动state后再次确认secret身份/失败恢复；stop仅当前instance身份且不误关复用PID。
HTTP角色/secret分存、控制secret不入argv/url/log/响应、boot60s单次fragment兑换与重放、并发兑换线程安全、page token内存、Host/Origin/Sec-Fetch-Site闭集/missing行为、无Cookie/CORS、chunked/重复Content-Length/body/JSON闭集、HTTP错误脱敏、CSP/无任意文件act路由、健康被异常状态冒认、shutdown权限和线程关闭。
playground fail-closed无provider/无redactor、打开/health/轮询零模型、跨项目token/端口/profile隔离；history通过已注入redactor/缺回调omit且不利用旧未审数据，依赖中间状态503诚实。STATIC_ASSETS与T11接口只是壳，不算双页签真实完成；浏览器argv/spawn失败不宣称窗口成功。
RED分清模块缺失/fixture错误/实际行为回归，37+1 skip平台面不得声称Windows用户权限隔离；228在档数字/依赖hash/隔离扫描核对。测试不充分/静态安全反例给具体触发。

## 要求
只读，PASS/CHANGES_REQUIRED，P0/P1/P2具path:line/触发/AC-VC/后果/最小修复。无shell说明静态+旧日志，不声称实测。后续未接线不自动扣分，unsafe接口必须报告。

## 未覆盖面声明
真实Chrome/Edge/Windows crash/TIME_WAIT/真实提权/Linux/Jev/T06+UI未验，不声称全AC；T07b/T05并行不审其在产。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-monitor/**`

## 写入禁止面
- 所有代码/测试/生产档案/任务相位/其他worker。

## 交付格式
report≤180行，结论/Findings/证据/下游风险与未覆盖/上下文；摘要≤30行。
