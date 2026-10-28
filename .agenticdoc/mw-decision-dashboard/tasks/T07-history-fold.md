# T07 history-fold

type: coding
status: changes-required-T07b
code_status: 代码完成
verification_status: 原23专项/110邻接绿；独立review发现2P1/5P2，T07b修复中，不放行输出安全
deps: T02（终验T08 T09）
ac_refs: [AC-002, AC-003, AC-012, AC-013, AC-014]
vc_refs: [VC-002, VC-003, VC-013, VC-018]

## 上下文
- Goal `.agenticdoc/goal.md`；本key `spec.md`（AC指纹728632b37572）、`design.md`、`plan.md`、`evidence-requirement.md`必须完整读取，任务自持目标如下。
- path:line `decide_signoff.py:287 collect；decide_archive.py:91 _ROW_FIELDS`（行号可能漂移，按函数定位）。Python引用前缀packages/multi-workers，TS引用前缀packages/coding-agent/src/extensions/agent-team-loop。
- 依赖：T02（终验T08 T09）；依赖未完成不得开写。同文件一次仅一worker。当前为本key任务，不写其他key/框架状态；相位由PM管理。
- AC目标：AC-002 AC-003 AC-012 AC-013 AC-014；VC验收：VC-002 VC-003 VC-013 VC-018，引用design §7精确断言与evidence-requirement，未覆盖剩余AC不宣称完成。

## 要求
只读全key历史archive/wire/lifecycle/sign/gate合并，opaque-id，不以decision_id拼路径；生产/test统计分开，actor与answer_source分开、authority不是human证明。缺失未记录/unknown/inferred，建议/采纳/消费/响应/执行分列，pending明确。筛选分页、坏行/半行/外根ID安全；新lifecycle绝不被旧fold/report/collect消费。
- TDD：先新增行为测试并跑出正确RED，才实现GREEN；修改测试必须运行直至通过。问题先根因调试，不移除 intentional 功能、不猜外部API、不any/inline import。
- 完整读被编辑文件；大文件完整分页，局部编辑，禁止覆盖未读源。已有其他会话diff保留，绝不reset/checkout/stash/clean/宽泛git add、不commit。
- npm run check在代码完成后全输出验证；同时worker修改造成的非本面错误报告PM协调，不能越面“修全仓”。不要npm test/build/全vitest；零外网、零付费模型，不起停共享serve，不更改凭证/锁文件。
- 非本任务代码修复先报PM取得写面，禁止越面；准备先骨架report落盘、记录依赖实际API、checkpoint风险/进度，预算尾段收敛。

## T03 review 下游统计契约
- 完整读workers/dd-review-transport/report.md：client/scope.capture_status是生命周期聚合，per-call/attempt状态从该ID行取，不让前序失败污染后次详情。
- 默认统计显式区分logical_calls与actual_http_attempts；zero_call=true的disabled/unconfigured client行不能算实际模型请求。旧缺字段不回填为1次调用。
- module-unavailable与无scope/未记录区分展示；Capture失败/partial与正文omit不能假称完整原文。

## T02c最新读侧契约
- 完整读workers/dd-metadata-key-safety/report.md及evidence更正；usage/policy键可能redacted/裁剪/丢弃/碰撞，缺键=未记录，不是0或上游没给。原始metadata没有完整性旗标，不宣称它是逐字节原始响应；实际原文只取capture字段且服从脱敏/截断标记。
- 缺可信链接不能猜最近call，结构字段作为opaque id必须验证本项目与事件schema，authority human不证明人工操作。
- T02c已代码完成304联合绿，窄安全复审并行，仅本读模块可开写，最终验收待其PASS与T08/T09完整链。

## 写入允许面
- `packages/multi-workers/decision_history.py`
- `packages/multi-workers/test_decision_history.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-history-fold/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T07-*`（唯一任务前缀证据）

## 写入禁止面
- 其他所有源文件/测试/任务卡/相位文档/其他key；生产.authority/decisions/signoff/triage/wire不能用于验证写入，仅isolated tmp fixture。
- packages/multi-workers/dist/**、pi核心、凭证配置、package/lockfile依赖、共享服务、用户目标工作区。

## 验收命令
- Python命令从packages/multi-workers运行，TS从packages/coding-agent运行（T15明确root）；如列出的既有文件不存在，核实真实名称并报告，不假报passed。
- `python -m pytest test_decision_history.py -q`
- `npm run check` repo root，全stdout/stderr保存不tail。禁止以py_compile/check替代本卡行为断言。
- report给命令、cwd、退出码、测试名/数量、RED→GREEN、[VERIFY]指标真实来源，未运行=未验证，禁止伪造。

## 改动历史
- 2026-10-22 PM建卡；实现未开始，原设计review PASS仅文档层。

## 交付格式
自身report.md四段：结论/改动与证据/风险与未覆盖/上下文来源；实际modified路径与下游API/签名、每AC/VC覆盖、完整验收证据路径，≤150行。只有代码与测试通过可代码完成，目标全部验证需PM整合。任务卡和pm-state由PM更新，worker不改。
