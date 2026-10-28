# T05 observation-seam

type: coding
status: changes-required-T05b
code_status: 代码完成
verification_status: 原30/36/873绿；独立review发现F1 typed门P1及6P2，T05b修复中；全包两归因待核实
deps: T03 T04
ac_refs: [AC-003, AC-004, AC-008, AC-010, AC-011]
vc_refs: [VC-003, VC-004, VC-008, VC-010, VC-011]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `decision_points.py:2278 decide_for；:2137 _maybe_archive`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T03 T04；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-003 AC-004 AC-008 AC-010 AC-011；VC验收：VC-003 VC-004 VC-008 VC-010 VC-011，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
内部observation成对约束intent=answer/archive=False/独立scope；仅DP关闭绕过，全局disabled/未配置/凭证/输入仍零请求。共享纯授权预览不能假称executor成功；新增decision-end归档信号保留原异常。保存当次book或input-state与渲染候选快照，旧digest不能还原；decide_archive只改错误state_digest文档叙述不改schema/业务。测试client显式evidence_path，所有生产旁账/签收字节不变。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## T03 review 下游硬契约
- `workers/dd-review-transport/report.md` 已独立PASS，5个P2需承接，不能当全链路完成。
- 每次生产decide_for创建新production scope及新鲜credential redactor，禁止跨凭证轮换复用旧scope；test必须显式独立scope/client/evidence_path。
- 可选wire导入缺失/损坏必须以安全观测通道区分module-unavailable与无scope，生产保持业务结果但capture失败明确；观察模块不可用必须拒绝，禁止fallback生产默认路径。
- zero_call=true逻辑client行不能冒充实际HTTP调用，decision-end/candidate/book关联由本卡真实接线，call-end不重复写。
- T02b安全修复与T01/T02/T03联合复验通过才开写本卡；基础中间RED是同key依赖债，不是可排除的外部噪声。

## 基础复审关闭后的硬契约
- 原P0/P1及N-1已独立复审PASS；全文读workers/dd-review-metadata-keys/report.md和T02c report/verify-summary。304联合验收为worker在档证据，真实Jev/平台欠项未完成。
- policy键必须生产者闭集：本卡如写policy，显式定义/验证允许键，不允许自由文本作为键。不需无回调保留时保持已有store文本策略；若需在_FIELD_CLOSED_KEYS登记新闭集，decision_wire.py不在本卡写面，先报告PM由专属owner登记，不越面。
- book_ref/state_digest/retry_of/target/supersedes/archive等豁免结构字段只取内部生成且验证的标识符/枚举，禁止把路径/凭证/任意模型文本塞进这些字段；candidate/input-state/book快照自由文本必须走已注入的redactor路径，缺回调omit且明确状态。
- metadata丢弃/clip/碰撞后缺键=未记录，不是0或上游没给；实际原文只取capture并展示脱敏/截断/省略标记。
- scope.evidence_path/fail_closed等保留seam在本卡/T06必须真正消费；未消费接口作为待清理记录，不为类型错误擅自移除未来功能。

## 写入允许面
- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_book.py`
- `packages/multi-workers/decide_archive.py`
- `packages/multi-workers/test_decision_observation.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-observation-seam/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_observation.py test_decide_run_authority.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 改动历史
- 2026-10-22 PM建卡；设计review PASS仅文档层。
- 基础原严重finding与N-1复审闭合后PM放行；T04 points/book原写者终态，当前本卡唯一写者，T07只新history文件无争用。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
