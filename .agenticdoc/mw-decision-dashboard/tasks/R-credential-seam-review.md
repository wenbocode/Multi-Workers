# R T05j 凭证门接线独立复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358凭证单权威与完整发送面。
- `packages/multi-workers/decision_points.py:4260` _decide_for新增Step4c/caller coverage/known_secret_superset；`mw.py:1566` book门/client快照（函数定位）。
- workers/dd-credential-seam-wiring/report.md全文与evidence/runs/T05j-credential-seam-wiring/基线/diff/hash/RED/GREEN/measure/mutants；workers/dd-review-timi-snapshot/report.md P2-1/2/3。
- T05k当前将串行修改points required拒绝标记/p0 metadata，不修改T05j快照逻辑；审T05j以归档baseline+diff重建/对应当前函数为准，依赖时点披露，不混入T05k成果。

## 审计目标
门前snapshot、门/capture/client同cfg同snapshot，同次retry固定下次刷新；caller pin若来自另一cfg是否复用遮蔽真实key，caller-owned redactor覆盖实际值 failclosed，跨client共scope陈旧集合是否拒或重建安全，新scope每命令闭合（派发后追加义务worker未必已收到，必须独立核实）。
known_secret_superset额外timi活读是否造成门/capture集合漂移，是否违反decision单权威发现要求；gate/capture/Authorization实际是包含关系非集合相等不得过称。explicit cfg+auth双key仍完整保护，production client _ensure_wire_redactor缺legacy超集是否残留公开泄漏，给准确owner面。
拒绝业务路径不写snapshot的声明与已知required missing/null反例纠正，T05k正修但不追认T05j已零快照。异常resolver/redactor/caller无法pin安全与零发送，finally复位/冻结client接口。
RED5F6P实现前时序/基线副本真实性，186/540与coldstart真loopback证据，mutants修后不RED，4check不完整，旧T05i合成值掩码更正是否落档。

## 要求
PASS/CHANGES_REQUIRED，原owner接线关闭表/新finding/path:line/最小owner面/范围越面与证据偏差。仅自身report不源/test/服务/外网/build/真实凭证读取，不将在档日志当自己实测。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-credential-seam/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告证据/真实生产凭证/其他worker。

## 未覆盖面声明
T05k required/数组另切片未验，真实Jev/browser/平台/全仓check未验；hash不复算须明说。

## 交付格式
report≤130行，关闭表/安全残留与严重度/事实更正/精确下一卡/未覆盖。
