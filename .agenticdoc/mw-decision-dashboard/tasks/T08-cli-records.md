# T08 cli-records

type: coding
status: pending
code_status: 未开始
verification_status: 未验证
deps: T05（monitor接线T10）
ac_refs: [AC-003, AC-007, AC-014, AC-017]
vc_refs: [VC-003, VC-007, VC-014, VC-018]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `mw.py:911 _decide_run；:3784 _decide_sign；:10735 decide parser`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T05（monitor接线T10）；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-003 AC-007 AC-014 AC-017；VC验收：VC-003 VC-007 VC-014 VC-018，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
CLI唯一写者：record answer/override/event闭集精确ref_seq/版本/调用目标/理由与幂等；动态候选从当次快照校验、缺材料拒绝；人工事件无acted/outcome、不改授权/旧report/signoff。ask actor来源、book加载同bytes快照、sign/refresh/dp apply来源元事件；event固定system。monitor/status/stop接T10，错误非零，root fail-closed。保留原sign授权守卫。可分两轮同owner，record先交付T09协议。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## 写入允许面
- `packages/multi-workers/mw.py`
- `packages/multi-workers/decide_signoff.py`
- `packages/multi-workers/test_decision_dashboard_cli.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-cli-records/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T08-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_dashboard_cli.py test_decide_sign_auto.py test_decide_archive.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
