# T06 playground

type: coding
status: pending
code_status: 未开始
verification_status: 未验证
deps: T05
ac_refs: [AC-004, AC-008, AC-010, AC-011, AC-012, AC-017]
vc_refs: [VC-004, VC-008, VC-010, VC-011, VC-012, VC-015]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `decision_book.py:362 scaffold_book；decision_points.py:2278 decide_for`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T05主链已交付，T05q列举诚实损坏类修复GREEN；PM按用户功能闭环优先批准本卡编码启动，但生产放行仍须联合验收。必须只构造内部可信decision.credential_redactor，不接受HTTP/第三方redactor或client注入；任意回调wire硬防线仍为T13安全债，不追认T05q整体安全保证。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-004 AC-008 AC-010 AC-011 AC-012 AC-017；VC验收：VC-004 VC-008 VC-010 VC-011 VC-012 VC-015，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
内存book验证/scaffold与显式人工submit，独立test sink/evidence_path、submission锁中去重+start，start写失败零HTTP。每次retry新id，1执行0排队busy409，不因轮询/页面打开付费；线程内部绑定scope，executor=0，非法/凭证/超时/record-failed真实结果。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## 写入允许面
- `packages/multi-workers/decision_playground.py`
- `packages/multi-workers/test_decision_playground.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-playground/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T06-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_playground.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 下游安全验收补充（T10b复审）
- `workers/dd-review-monitor-fixes/report.md` N2：monitor允许dp1 history object子树通过纵深扫描；不能据此认定合法book。T06须在任何submit发送前真实check_book并校验object后代中的执行/授权夹带，合法业务数据不误伤；validate/submit同一安全校验，非法零HTTP。单纯调用现有check_book若其后代规则不满足安全目标，报PM精确owner修复，勿自行猜已覆盖。
- 消费当前T05n/o/p/q seam API，typed/enum/unknown/required零快照/p0_open合法[]。顶层import decision_book；当次cfg生成完整credential_snapshot，并同一snapshot用于check_book(redactor=decision.known_secret_redactor(cfg,snapshot=...))、capture可信credential_redactor及client pin，不要门/发送再次解析。provider义务常量不等真实执行。
- 开工先核对decision_monitor.py现有PlaygroundProvider协议（T11a正改assets/marks，不改provider协议），实现其validate/scaffold/submit/status入口，不独创不兼容UI接口。若需monitor接线，只报告给PM，禁止争写。
- 检查book_ref内容关联歧义时用已生成submission id做显式关联，不猜最近call，不越面改_snapshot_ref。
- 原卡npm run check改为严格只读biome及各check子步留档，完整check未跑明确不等价；不得运行biome --write越面。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。
- PM吸收T10b PASS：原1P1/6P2 closed，N2显式转本卡验收，T05b仍阻塞开工。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
