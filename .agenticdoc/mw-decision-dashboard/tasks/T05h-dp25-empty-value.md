# T05h dp25 p0_open合法空值（用户确认）

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；本key spec17AC/typed单权威。
- `packages/multi-workers/decision_book.py:518` is_placeholder/_check_placeholders；`decision_points.py:1450` dp25 p0_open声明（函数定位）。
- workers/dd-review-unified-input/report.md P1与字段级选项。用户明确同意：仅dp25 p0_open=[]表示没有未关闭P0；缺失/null/类型错拒，其他字段空数组规则不变。不改变签收授权/执行门。
- dd-review-cli-config只读mw链，不争本卡points/book/生成物写面；其他编码worker均终态。

## 要求
完整读被改文件分页<=400行，保存当前基线/hash；先新增行为测试正确RED再实现GREEN。
注册表单权威增加字段级empty_is_value（或等价现有metadata标志），仅dp25 p0_open声明true，book placeholder扫描消费该字段元数据。不得在book硬编码dp25绕过，不能全局改变is_placeholder([])规则。正式typed仍保证p0_open类型/数组元素/长度，缺失/null/错误类型/占位字符串元素不能因flag放行。允许[]代表已填无P0，不推断来源已核实。
真实signoff_state(collect(tmp))无P0状态能构成合法book且观察发送实际state一致；同时缺失/null/type错零发送、零快照，其他required空数组dp8跨key冲突/dp15 pending/dp17问题/dp20blockers仍原拒绝。旧占位符/secret/身份/授权/签收隔离不退化。已有测试固定旧p0_open冲突按已确认新规则精确更正，不降其他断言。
现有生成器导出metadata到JSON/TS/book契约；若生成器不承载新flag，可精确必要调整允许脚本，不手写派生物/不变其他DP语义。template必要重新生成但仅授权规则影响，保留原无关内容。报告指出编辑器scaffold []对于该字段已合法但不能自动批准签收。
Hermetic所有测试外层HOME/USERPROFILE tmp/_auth_json_path tmp/delenv凭证后缀；不读取真实用户凭证/真实生产记录。模型仅FakeBackend或隔离127.0.0.1，无Jev。禁全包pytest/build/commit/外网/服务/browser。

## 写入允许面
- `packages/multi-workers/decision_points.py`（字段metadata）
- `packages/multi-workers/decision_book.py`（字段级placeholder消费）
- `packages/multi-workers/test_decision_input_contract_migration.py`（旧冲突用例精确更新）
- `packages/multi-workers/test_decision_dp25_empty_value.py`（新专项）
- `packages/multi-workers/scripts/gen_decide_registry_ts.py`（仅新metadata必要生成）
- `packages/multi-workers/decide_registry.json`（现有生成器）
- `packages/multi-workers/decide_book_template.json`（必要派生）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（生成器）
- `.agenticdoc/mw-decision-dashboard/workers/dd-dp25-empty-value/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05h-*`

## 写入禁止面
- mw/client/seam控制流/ref/producer/其他源测试/旧报告/任务相位/真实凭证生产账/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_dp25_empty_value.py test_decision_input_contract_migration.py test_decision_book.py test_decision_observation.py test_decision_dashboard_contracts.py test_decide_registry_export.py test_decide_sign_auto.py -q` 全输出exit及生成器--check。
root全仓只读biome --error-on-warnings及check子步，完整check未整跑明确不等价，禁止write越面。

## 改动历史
- 用户已明确同意本规则，范围仅dp25 p0_open，其他同构空数组未授权；PM批准同key现有P1修复不扩17AC范围。

## 交付格式
report≤110行，真实基线RED/GREEN/真无P0 state合法book、其它空数组不变、生成API/metadata契约、未覆盖。不自报reviewPASS/T06放行。
