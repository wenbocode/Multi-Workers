# T05k required拒绝零快照与p0_open数组契约

type: coding
status: pending
deps: T05j code-complete（同文件串行，未满足不得dispatch）

## 上下文
- goal `.agenticdoc/goal.md`；design §4.5 typed数组界/非法材料零发送。
- `packages/multi-workers/decision_points.py:4476` required拒绝分支/:1576 p0_open metadata（按函数定位）。
- workers/dd-review-dp25-empty/report.md N1/N5，原用户确认empty值规则P1已closed；T05j当前唯一points/mw写者，本卡仅在其终态后取得points写权。

## 要求
保存当前未修基线/hash，先新增行为测试真实RED，再实现GREEN。
N1 required缺失/null/空字符串拒绝设置material_refused，与typed/book拒绝同策略：0backend/attempt/book-snapshot、book_ref=None；decision-end事实保留。不要删除拒绝事件/改变授权/预算/oversize候选保留语义。覆盖book与非book观察、生产隔离fixture。
N5 p0_open正式声明item_type=string/max_items=STATE_ARRAY_MAX_ITEMS/item_max_bytes=STATE_ARRAY_ITEM_MAX_BYTES，真实生产者sorted P0 dp-id string ≤25，保持empty_is_value=true及[]合法。非字符串/33项/超128B拒绝0发送/快照，真实[]/合法dp-id列表不退化，不自造enum限制。
现有生成器重导JSON/TS必要派生，不手写mirror；旧测试固定[1]/33items通过的现状如存在按已锁typed目标精确修正，不能删intentional业务功能。
T05h报告勘误另文件：missing/null RED实际失败于后续快照/null book断言，不能全称pin-GREEN；secret原P0已closed；62失败与monitor2/4无失败日志，只有mtime相关性和复跑结果，不推环境根因。
运行依赖hash包括decision/backends/points/book/mw/monitor及测试，稳定快照联合窄复验；遇flake先保留完整失败输出再重跑，不改monitor越面。所有测试tmpHOME/auth/delenv后缀、读前spy，不真实凭证。

## 写入允许面
- `packages/multi-workers/decision_points.py`（required拒绝标记/p0_open metadata）
- `packages/multi-workers/test_decision_required_refusal.py`（新专项）
- `packages/multi-workers/test_decision_dp25_empty_value.py`（精确typed断言）
- `packages/multi-workers/decide_registry.json`（生成）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`（生成）
- `.agenticdoc/mw-decision-dashboard/workers/dd-refusal-array-contract/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05k-*`

## 写入禁止面
- T05j运行期间任何源写入；其他源测试/mw/book/decision/backends/monitor/placeholder/ref/旧报告/任务相位/真实凭证生产/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_required_refusal.py test_decision_dp25_empty_value.py test_decision_input_contract_migration.py test_decision_observation.py test_decision_dashboard_contracts.py test_decide_registry_export.py test_decide_sign_auto.py -q` 全日志exit，生成器--check；monitor邻接只读失败先留档。
root全仓只读biome --error-on-warnings/check子步，完整check未整跑明确不等价，禁全包pytest/build/commit/外网/Jev/服务/browser。

## 改动历史
- PM吸收T05h条件PASS，原用户empty规则closed；N1/N5待串行修复，本卡不得抢T05j写权。N2证据归因继续欠，不据复跑通过排除。

## 交付格式
report≤110行，真实RED/GREEN/required零快照与数组非法拒绝/生成API/依赖hash/勘误/未覆盖，不自报T06放行。
