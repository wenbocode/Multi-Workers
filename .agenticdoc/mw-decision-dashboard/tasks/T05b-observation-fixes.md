# T05b observation安全门与快照契约修复

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement全文。
- `packages/multi-workers/decision_points.py:3775` _validate_observation/:3890 decide_for/step5；`decision_book.py:703` state_field_issues引用（函数定位）。
- workers/dd-review-observation/report.md完整读：F1 P1与F2..F7 P2；原T05 report/verify-summary/测试全文。
- T10b唯一monitor写者、T07c唯一history写者，本卡唯一points/book写者，不争用。

## 要求
systematic-debugging+TDD，保存当前未修基线在证据目录，新增测试对现有实现实际正确RED，保存完整输出，再改实现GREEN。修后mutant不替代实现前RED。
F1：内部decide_for统一typed/enum/数组界/未知业务键/跨字段校验，利用registry单一权威与state_field_issues，不造第二套。必填之后/预算与backend之前拒绝，错误显式input-incomplete或既有合法分类，零HTTP/backend；观察与非book生产路径都守同门，不能只靠T06 check_book。完整读state_field_issues实际覆盖范围，若未知闭集在book层需提取共享纯校验而不循环import，不放宽旧typed测试。合法所有25DP仍可调用，旧生产者缺事实需报告迁移债不伪造值。
F2：Observation.book存在时必须DP一致、合法完整book/check_book含秘密/证据/闭集且state与本次实际发送状态digest一致；避免循环import，可在book模块共享纯校验/由调用前book验证证据契约配合seam自身dp/state验证，不能仅声明T06负责。错误book显式零发送或安全降级input-state并明确不是合法book material，选择记录API理由；绝不保存未知秘密原文或错标book快照。
F4：snapshot_ref/book_ref只在真实written=True才声明，False/异常时None或有明确snapshot_written=false与无悬空引用；capture失败业务结果不变。补record_event False/异常spy与实际行关联。
F5：actor_kind采用真实同一闭集、actor_id非空/合法，非法先拒绝零发送/零账，默认human声明仍不能证明人工操作，不改wire owner源。
F3/F7：另写更正文件：原RED29/GREEN30后补broken_capture单测与fixture漂移不能冒称全终版先RED；policy未写仅指wire decision-end字段，生产archive policy echo已有。不覆写旧报告/日志。
F6：monitor/mwds两条归因待核实保留，不以无直接import判无关，本卡不再全包重跑。限定验收、必要邻接即可。
scope/evidence/全局transport关闭/凭证/生产签收字节不变/长secret脱敏/归档异常原样重抛与preview纯预测不得退化。真实HTTP仅127.0.0.1 fixture，不真实Jev/外网。

## 写入允许面
- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_book.py`（仅共享纯typed/book校验必要重构）
- `packages/multi-workers/test_decision_observation.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-observation-fixes/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05b-*`

## 写入禁止面
- archive/backend/client/store/history/monitor/mw.py/所有TS/其他测试/任务相位/其他报告/真实生产档案/凭证/dist/依赖锁。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_observation.py test_decide_run_authority.py test_decision_dashboard_contracts.py test_decision_points.py test_decision_book.py test_decide_sign_auto.py -q` 全输出/exit；新增真实HTTP测试可放本卡专项，禁改transport测试。
root严格只读biome --error-on-warnings与其余check子步，禁止普通biome exit0当清零，完整check越面风险明确未整跑；禁止全包pytest/npm test/全vitest/build/commit/外网/服务。

## 改动历史
- PM吸收T05 review CHANGES_REQUIRED，F1核心门阻塞T06开工；T05原写者终态，本卡精确单写者修复。

## 交付格式
report≤180行，逐finding实证/修复/RED/GREEN、实际25DP合法/非法零发送指标、book/快照/actor API变更、更正文件/未覆盖，不自报reviewPASS。
