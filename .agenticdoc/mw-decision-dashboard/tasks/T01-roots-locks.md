# T01 roots-locks

type: coding
status: code-complete
code_status: 代码完成
verification_status: 局部验证通过，全仓检查待协调
deps: 无
ac_refs: [AC-007, AC-008, AC-015]
vc_refs: [VC-007, VC-017, VC-018]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `mw_common.py:2388 acquire_lock；:2533 PID存活；:5085 load_target_config`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：无；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-007 AC-008 AC-015；VC验收：VC-007 VC-017 VC-018，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
根/锁基础：实现resolve_control_root(require_control=True)拒绝未知/多义根，保留已存在project/.agenticdoc/key规范路径；独立target不能猜control。acquire_lock增加可选monotonic deadline，不改变现有默认调用语义；为新monitor锁提供owner PID/start身份安全观测辅助，未知不抢锁。完整阅读相关函数后局部编辑，不广泛重构。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## 写入允许面
- `packages/multi-workers/mw_common.py`
- `packages/multi-workers/test_decision_roots_locks.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-roots-locks/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T01-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_roots_locks.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。
- 2026-10-22 dd-roots-locks交付mw_common.py及27测试，RED25 failed/2 passed→GREEN27 passed；report和verify-summary完整回读ack。全仓check非绿（越面lint/邻接失败），不判全VC完成；T02可依赖实际接口继续。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
