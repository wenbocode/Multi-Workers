# T04 dp-contracts

type: coding
status: needs-clarification-resolved-by-T04b
code_status: 代码交付
verification_status: 专项119通过，完整验收44失败待T04b
deps: 无（与T01独立写面）
ac_refs: [AC-009, AC-011]
vc_refs: [VC-009]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `decision_points.py:1131 REQUIRED_STATE_FIELDS；decision_book.py:615 _check_state_closed`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：无（与T01独立写面）；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-009 AC-011；VC验收：VC-009，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
全25DP typed业务契约按design §4.5逐字段声明required/optional/type/description/enum/max_items/元素长度，dp1/2/3/25保留现有功能。dp2实际progress可选字段纳闭集，book校验/evidence/生成物同源。新增21DP身份态拒绝零发送，合法事实可过；dp17 17AC通过/max_items=128，普通32，signed snapshot.delta_bytes允许负数；整体2000B总预算仍独立，必填事实不静默裁。迁移本卡允许面内身份态旧测试，不放宽门；发现其他测试需改报告PM，不越面。生成TS导出保持type安全，不any、不inline imports。只实现契约，观察seam由T05负责。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## 写入允许面
- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_book.py`
- `packages/multi-workers/scripts/gen_decide_registry_ts.py`
- `packages/multi-workers/decide_registry.json`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`
- `packages/multi-workers/test_decision_dashboard_contracts.py`
- `packages/multi-workers/test_decide_registry_contract.py`
- `packages/multi-workers/test_decide_registry_export.py`
- `packages/multi-workers/test_decide_registry_ts_lock.py`
- `packages/multi-workers/test_decision_points.py`
- `packages/multi-workers/test_decision_book.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-dp-contracts/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T04-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_dashboard_contracts.py test_decide_registry_contract.py test_decide_registry_export.py test_decide_registry_ts_lock.py test_decision_points.py test_decision_book.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。
- worker交付后44失败来自本卡漏列的probe/template，PM以T04b明确授权两面，不靠disabled dp19求裁决。119专项绿不等于T04验收通过；报告回读ack。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
