# R T05h 用户确认空值规则复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；用户明确确认仅dp25 p0_open=[]无未关闭P0，缺失/null/type错仍拒，其余字段规则不变。
- `packages/multi-workers/decision_book.py:731` _check_placeholders/_placeholder_element_issues；`decision_points.py:1576` p0_open metadata/:2508 metadata validator。
- workers/dd-dp25-empty-value/report.md全文/evidence/runs/T05h-dp25-empty-value/RED/435GREEN/317邻接+skip/生成delta/refusal-snapshots/element-scope/concurrent-write-note。

## 审计目标
字段级唯一empty_is_value消费、无dp硬编码/全局放宽，真实tmp collect/signoff_state无P0 book合法，缺失/null/type错拒、其它dp8/15/17/20空required数组不变；null required全局修正是否intentional规则正确实现，元素占位扫描是否额外误拒合法值（如-1），标明用户授权与typed既定契约。
JSON/TS生成metadata单权威与新API，原注释/test错误固定现状不能当AC覆盖。p0_open [1]/33项通过是typed契约缺口或范围外，参考本key设计required/optional数组上限，给真实元素类型生产源证据与精确修复，不能猜字段值。
missing/null落book-snapshot可能存非法材料/known-secret，明确零发送成立≠零快照，给最小seam修复建议（不改源）。
RED11F53P/GREEN435与pin-GREEN披露、并发62失败原因证据是否成立，不称未定位伪失败；monitor错token stop 4次2失败需真实日志根因区分环境与回归，不将偶发通过当解除债。
数组secret此前T05e已闭合不是仍他人P0，报告过时事实更正；T05i当前仅decision/backends并行，对依赖hash快照明示。

## 要求
PASS/CHANGES_REQUIRED，原空值P1关闭表/新增finding/证据偏差与稳定复验义务。仅自身report，不源/测试/模型/服务/外网/build/真实凭证读取，静态旧日志非自己实测。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-dp25-empty/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告/真实生产凭证/其他worker。

## 未覆盖面声明
真实HTTP/Jev/browser/平台/全仓check未验；账本两个生成物均原卡允许PM已补记ack，无待授权。

## 交付格式
report≤130行，关闭表/新缺口/精确下一卡/并发与flaky证据/未覆盖。
