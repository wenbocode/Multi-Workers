# T05c dp25单权威迁移与seam剩余安全门

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec25DP typed单权威/AC-005/010/011/012。
- `packages/multi-workers/decision_points.py:2085` LEGACY_PRODUCER_STATE_PATHS/:2174 enum detail/:4364 step5b。
- `packages/multi-workers/decide_signoff.py:353` signoff_state真实三字段类型，workers/dd-review-observation-fixes/report.md全文dp25迁移面/N1..N4（原review标题无P1但表格称新P1，以具体缺陷为准）。
- T05b代码及独立审查已终态，当前本卡points/book/tests/export唯一写者。T07d可能仍活只history面，不争用。

## 要求
保存当前实现/测试基线及hash，先新增测试实跑正确RED再实现GREEN，不能为追绿放宽typed或保存错误旧行为。
dp25三生产字段从临时LEGACY_PRODUCER_STATE_PATHS迁入OPTIONAL_STATE_FIELDS+STATE_FIELD_DESCRIPTIONS，真实integer>=0/array[string]与明确max_items/item_max_bytes遵既有契约预算。读signoff_state真实产物，不得猜enum或伪造数据；将临时兼容白名单替换为正式声明（非删除业务功能），删allow_paths调用与临时专表，不再seam/book分裂。
通过项目现有export生成器重导出JSON/TS/template，只允许派生本次声明所需变化，不手造冻结mirror，不改mw.py。若生成器触未允许面/不适用于本变化立即报PM不越面。
新测试直接真实signoff_state(collect(tmp fixture))无豁免过共享typed/unknown门，合法真实dp25 state可建合法book且与发送state一致；非法三字段类型/数组界/secret book零发送。全25DP契约与export字节不退化。
N1 typed/unknown拒绝路径零book-snapshot断言，真实scope/sink测试；oversize是否保存当次候选明示与typed非法的安全差异，不能笼统称所有拒绝零快照。
N2非book三身份值等于dp registry/schema版本，缺失按builder既有默认语义处理，显式错值零发送/零非法快照；与book共享纯检查不另造版本权威。
N3 enum detail移除原始value!r，输出仅field path/类型/允许集合等安全闭集，已知合法形状secret/任意自由文本不echo，禁止改注释为允许泄漏追绿。
N4 register_book_validator可重复同一合法注册但拒绝不合法/任意覆盖，保持无inline/dynamic import；book未导入failclosed保持，T06必须顶层import decision_book写报告（不改T06卡）。针对冷启动仅points拒与points+book合法用独立隔离脚本验证，不真实模型。
同scope重复snapshot_ref唯一性先测/记录若缺陷给PM，不擅改wire owner。无全包pytest、真实Jev/服务/浏览器/外网/build/commit。

## 写入允许面
- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_book.py`（共享纯身份检查/validator必要调整）
- `packages/multi-workers/test_decision_observation.py`
- `packages/multi-workers/test_decision_input_contract_migration.py`（新回归）
- `packages/multi-workers/decide_registry.json`（现有生成器派生）
- `packages/multi-workers/decide_book_template.json`（现有生成器必要派生）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（现有生成器派生）
- `.agenticdoc/mw-decision-dashboard/workers/dd-unified-input-contract/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05c-*`

## 写入禁止面
- 其他源/测试/TS/shared/dist/其他报告/任务相位/真实生产签收授权/凭证/依赖锁；不改decide_signoff生产者。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_input_contract_migration.py test_decision_observation.py test_decision_dashboard_contracts.py test_decision_points.py test_decision_book.py test_decide_sign_auto.py test_decide_registry_export.py -q` 全输出/exit，必要CLI隔离tmp no send。
root严格只读biome --error-on-warnings与check各子步，未整跑完整check必须声明，分步不等价。新增测试运行至真绿，既有失败记录迁移债不越面追全仓。

## 改动历史
- PM吸收T05b条件PASS，dp25明确非最终契约，精确授权生成物补单权威；N2/N3在T06前关闭，其他安全条件先测试再实现。

## 交付格式
report≤130行，逐迁移/N1..4实际RED/GREEN，dp25真实生产者无豁免/helper/book/导出指标、API变化/生成命令、残留/未覆盖；不自报reviewPASS。
