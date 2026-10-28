# T11 dashboard-ui

type: coding
status: pending
code_status: 未开始
verification_status: 未验证
deps: T06 T07 T10
ac_refs: [AC-002, AC-003, AC-004, AC-005, AC-006, AC-011, AC-013]
vc_refs: [VC-002, VC-003, VC-004, VC-005, VC-006, VC-011, VC-013, VC-015]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `decision_book.py:362 scaffold_book；design.md:1 用户确认两页签`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T06 T07 T10；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-002 AC-003 AC-004 AC-005 AC-006 AC-011 AC-013；VC验收：VC-002 VC-003 VC-004 VC-005 VC-006 VC-011 VC-013 VC-015，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
两页签历史/DP测试，typed契约编辑/validate/显式submit/详情与retry，book调用wire/candidate/pending/来源真实展示；token内存、fragment清除、安全textContent、禁innerHTML/inline/eval，严格CSP，无任何打开刷新自动模型。旧版本记录限制/字段与总预算/记录失败明确。UI测试静态安全+本地HTTP，不借真实Jev；需要截图验收另派vision。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## 写入允许面
- `packages/multi-workers/decision_dashboard.html`
- `packages/multi-workers/decision_dashboard.js`
- `packages/multi-workers/decision_dashboard.css`
- `packages/multi-workers/test_decision_dashboard_assets.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-dashboard-ui/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T11-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_dashboard_assets.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 历史输出最终契约（T07d）
- `workers/dd-review-history-final/report.md` PASS，history安全序列化只用page/record.as_dict，raw属性不得渲染。显示filters_withheld/filters_basis；当前monitor未转发两键，开工前报PM派monitor单写者最小接线，不在本卡越面改monitor。
- capture_status/stored_len/sha描述存储，text_omitted/output_omitted/byte_exact=False及capture-output-omitted描述本次输出，不能据capture_status=ok称正文完整。结构/自由字段marks省略不同于无答案，缺usage键未记录不补0。
- PM已独立复跑history/archive/signoff/monitor 213 passed+1skip，6依赖hash前后不变；非真实浏览器验收。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。
- PM吸收T07d PASS，最终输出/省略与状态分层契约入本卡，T06仍待T05c。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
