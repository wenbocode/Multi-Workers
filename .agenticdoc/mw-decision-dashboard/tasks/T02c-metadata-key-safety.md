# T02c 已知凭证 metadata 键旁路收口

type: coding
status: code-complete-review-pass
code_status: 代码完成
verification_status: 304联合/113重复通过，tsgo新时点exit0，窄复审PASS已回读ack，N-1关闭

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/design §9。
- `packages/multi-workers/decision_wire.py:829` _sanitize_metadata；`packages/multi-workers/decision_backends.py:268` _usage_from_body（只读）；`workers/dd-review-foundation-fixes/report.md` N-1/N-2。
- 原P0/P1已复审closed，N-1虽被review评P2，PM认为明确已知secret落盘违反AC-005，必须修复才放行T05。

## 要求
完整读store/test/传输测试与报告，TDD正确RED再GREEN。store对任意usage/policy mapping键执行安全处理：已知secret键不得原值落盘、无redactor不能把任意外部文本键当可信schema字段透传。保持正常token计数可用（确有闭集键可保留）；安全处理碰撞不能覆盖为伪造usage数值，需明确fail-closed冲突策略。嵌套字典/list键同处理，不把schema join id改写，深度/行限不退化。不盲以endpoint“恶意”免除输入信任边界。
先真实本地HTTP响应带已知凭证作为usage键、值/正文同时含secret，断言所有账/evidence原值0；直接store测试policy嵌套secret键/无callback/碰撞，证明RED后GREEN。不要只用sanitizer单元自证。真实HTTP允许127.0.0.1:0，禁止外网/付费。
N-2出具证据更正文件：T03 23项不是33，650日志74.80s不是74.68s；T02b tsgo未留档不可算可复核通过。自己运行tsgo并完整保存输出+exit/cwd补新时点证据，不覆写过去日志。原worker报告不可悄悄改历史，仅更正与引用。

## 写入允许面
- `packages/multi-workers/decision_wire.py`
- `packages/multi-workers/test_decision_wire_store.py`
- `packages/multi-workers/test_decision_wire_transport.py`（T03已结束，仅新增metadata键端到端安全测试，不删弱旧断言）
- `.agenticdoc/mw-decision-dashboard/workers/dd-metadata-key-safety/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T02c-*`

## 写入禁止面
- backend/decision.py/mw_common/所有TS/points/book/mw.py/模板/任务相位/其他worker报告/生产档案/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_wire_store.py test_decision_roots_locks.py test_decision_wire_transport.py test_decide_backends.py test_decide.py -q`，保存全部输出/exit。
root `npx tsgo --noEmit`保存完整输出exit/cwd；npm run check若formatter越禁止面，保持只读子步并明确不等价完整check。
禁build/commit/npm test/全vitest/外网/服务起停。

## 改动历史
- PM吸收foundation fix复审，原严重项关闭，单独收口新已知凭证旁路；T03测试写权串行交本卡。T05/07未派，无写冲突。

## 交付格式
report四段，RED/GREEN与真实HTTP测试名、键碰撞/缺回调策略及下游API变化，证据更正文件路径；不得假报全AC完成。
