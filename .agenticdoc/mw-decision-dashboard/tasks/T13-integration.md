# T13 integration

type: coding
status: pending
code_status: 未开始
verification_status: 未验证
deps: T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11 T12
ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017]
vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `decide_signoff.py:287 collect；decision_backends.py:246 _http_post`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11 T12；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-001 AC-002 AC-003 AC-004 AC-005 AC-006 AC-007 AC-008 AC-009 AC-010 AC-011 AC-012 AC-013 AC-014 AC-015 AC-016 AC-017；VC验收：VC-001 VC-002 VC-003 VC-004 VC-005 VC-006 VC-007 VC-008 VC-009 VC-010 VC-011 VC-012 VC-013 VC-014 VC-015 VC-016 VC-017 VC-018，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
孤立project真实CLI→内部链→stdlib HTTP→真实生产消费入口→先sign后测试byte/hash不变；多进程scope/双root/多project/crash恢复/安全负向/旧report不读lifecycle。不能手造事件代替验证的生产接线，不能mock掉_http_post或真实消费者。只测试允许面，发现实现缺陷回报PM派单写者修复，不越面。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## 写入允许面
- `packages/multi-workers/test_decision_dashboard_integration.py`
- `packages/coding-agent/test/suite/decision-dashboard-integration.test.ts`
- `.agenticdoc/mw-decision-dashboard/workers/dd-integration/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T13-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_dashboard_integration.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## T10b复审补充验收
- `workers/dd-review-monitor-fixes/report.md` N3：独立模拟旧state移动后仅secret被改写、未出现新state，验证abort分支保留fresh secret，零误移。
- N5：shutdown响应后无关listener抢绑，stop必须False/明确未证停；端口refused的stopped=True仅端口关闭不证明进程退出。不kill，不假造真实平台证据。
- T07d/T05b/T06最终稳定后history+monitor+provider联合复验，记录依赖hash；旧137+skip是并行快照不能替代最终绿。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。
- PM吸收T10b PASS，N3/N5非阻塞测试补强转此卡；只允许integration测试，不越面修monitor。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
