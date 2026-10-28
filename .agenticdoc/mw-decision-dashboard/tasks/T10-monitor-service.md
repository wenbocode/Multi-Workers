# T10 monitor-service

type: coding
status: running
code_status: 进行中
verification_status: 未验证
deps: T01 T02（HTTP整合T06 T07）
ac_refs: [AC-006, AC-007, AC-015, AC-017]
vc_refs: [VC-006, VC-007, VC-015, VC-018]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `mw_common.py:2388 acquire_lock；decision_backends.py:246 HTTP边界`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T01 T02（HTTP整合T06 T07）；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-006 AC-007 AC-015 AC-017；VC验收：VC-006 VC-007 VC-015 VC-018，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
独立Python monitor/high ports43170..43269/bind-and-hold/Windows exclusive/health身份项目版本/PID start。start lock owner确死才恢复，stale json/secret分步身份检查，unknown附恢复说明。控制/page角色、60s单次boot、长期秘密不进argv/url、Host/Origin/Sec-Fetch-Site闭集、256KiB body、无CORS/Cookie、shutdown control-only。两项目零串扰；只local server与模拟浏览器argv，不运行真实浏览器/服务。页面模型仅显式submit；不实现任意文件路由或act。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## T03 review 下游观测契约
- workers/dd-review-transport/report.md的F1/F4/F5必须承接：wire模块不可用与未启用采集分别展示，测试缺安全模块零调用、不fallback；按call/attempt行取capture_status，scope聚合只作总警告；logical zero_call不算实际模型请求。
- probe当前零写靠无CallState，如未来在绑定上下文调用probe，必须显式解绑call，不能混入业务调用记录；monitor打开/health/轮询不主动probe付费模型。

## 当前依赖与安全边界
- 基础T01/T02/T02b/T02c和T03均已独立复审安全通过，T07已交付API但history正文安全审查并行，T05在产/T06未开始。可实现服务/认证/lifecycle基础及依赖注入路由，不用占位逻辑冒充真实playground完整集成。
- 未审历史正文不得直接暴露：旧archive/signoff/gate不保证已脱敏，HTML转义不是脱敏；响应JSON/失败详情须统一注入真实credential redactor或fail-closed omit。history缺可信链接不猜最近call，opaque-id不拼路径。
- 无真实浏览器/共享服务起停，仅隔离测试local HTTP、argv模拟；运行不写真实project .mw，所有monitor状态在tmp fixture。T07/T05 API未稳定报PM，不越面改依赖。

## 写入允许面
- `packages/multi-workers/decision_monitor.py`
- `packages/multi-workers/test_decision_monitor.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-monitor-service/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T10-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_monitor.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
