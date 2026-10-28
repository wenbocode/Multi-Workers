# R T08a/T06/T11b 稳定功能联合审查

type: review

## 上下文
- goal `.agenticdoc/goal.md`；本key spec/design/evidence-requirement主功能闭环。
- `packages/multi-workers/decision_playground.py:1` submission持久化，`decision_monitor.py:1` default_monitor_deps/serve及API，`mw.py:4946` 私有starter serve(root)。
- workers/dd-monitor-command/report.md、dd-playground/report.md、dd-dp-test-closure/report.md完整回读。PM独立复跑evidence/runs/T13-pm-functional-recheck/pytest.log：119P+skip rc0，9hash前后一致，非真实browser/Jev。

## 审计目标
一次合并核真实CLI默认starter→serve→惰性单provider/redactor→全部25typed→显式submit真实HTTP→独立记录→轮询/答案/请求返回精确id。窗口路由此前T12a/T11a合并PASS，当前无争写者。
重点安全审新submission-results/<submit_id>.json：id/path containment/symlink/atomic/权限与写失败诚实、完整known键值脱敏/结构回显、当前读时是否安全、hash仅完整性非脱敏保证；不要凭完整原值消失豁免长secret尾部。用户目标实际请求/返回能看，token/metadata/失败输出无secret。
卡要求submission-end内保存但wire闭集导致另文件，PM认可合理结构方向但安全和失败事实未免审。默认deps工厂放serve/ensure vs显式裸deps保留，真实CLI链必须核，不只default instance mock。显式加载按钮是PM接受功能取舍；保留“待接入”文字不能误标已交付DP流程。
T06 context不发送有披露接受既有设计，RED最终行为回放是修后补证非实现前TDD，未跟踪不等无法保存基线。真实HTTP vs Node DOM vs真实browser边界清楚。history自由文本failclosed与惰性redactor具体可用性，不读生产auth。
T08a窗口失败exit0与卡要求冲突需明确最小修复建议；无浏览器/not-opened不能成功闭环。对抗caller wire硬防线仍T13债，本可信链是否引入该面判断明确。
只把明确泄漏/违规发送/业务误执行/实际主流程不可用列阻塞；其他集中账，不追加矩阵/研究循环。

## 要求
只读静态review完整分页审相关新文件与测试、核PM新日志/worker在档日志，未本人实跑/hash重算说明。不要真实browser/Jev/凭证/服务/build。不要改源/旧证据。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-functional-integration/**`

## 写入禁止面
全部源测试/其他worker/旧证据/任务相位/生产凭证。

## 未覆盖面声明
真实browser/Jev/Linux/部署/完整check/全部17AC未验，T08/T09来源生命周期和dispatch迁移仍债，不借功能切片PASS关闭整体。

## 交付格式
worker_file report.md最多140行，PASS或CHANGES_REQUIRED，主流程闭合表/具体阻塞最小写面/非阻塞集中账/证据及偏差。
