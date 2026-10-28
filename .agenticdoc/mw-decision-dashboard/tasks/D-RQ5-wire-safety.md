# D-RQ5 传输脱敏与上下文负空间核查

type: research

## 上下文
- goal `.agenticdoc/goal.md`；spec `.agenticdoc/mw-decision-dashboard/spec.md` AC-005/008/011/012/016；design合并稿§4.4/9待核查。
- `packages/multi-workers/decision_backends.py:246` _http_post（request data、response.read先decode）；`packages/multi-workers/decision.py:518` _redact；`packages/multi-workers/decision.py:1182` _emit；`packages/multi-workers/mw_common.py:2388` acquire_lock，按函数定位复核。
- 已有 D-RQ2/3研究说明call/attempt不同、archive=False仍可能写triage；先读已有证据，不重复泛泛调研。

## 要求
只读核查并给具体设计：(1) 实际response bytes在decode前采集，脱敏str/json/非JSON/secret片段/invalidUTF8，现有_redact是否够用，先脱敏后限长与64KiB行界如何保真不泄露，sha命名与raw_len语义；不能存raw secrets或重build payload。(2) client logical call context与backend retries/zero-network决定/outcome如何关联，不在_http_post每次新call_id；contextvar对线程/嵌套/显式record_scope与测试triage证据隔离的真实接线。(3) 既有锁默认100s会侵入决策预算，<=250ms总等待方案是否复用现有API，不偷删活锁；O_APPEND短写/错误/并发read策略；捕获失败best-effort真实可见，test start写失败零HTTP。指出合并design错误/未验证项，给函数path:line、最小参数/状态、writer-reader、局部真实HTTP与多进程VC。禁止代码/配置/档案改动，不网络/真实模型。

## 唯一证据文件
.agenticdoc/mw-decision-dashboard/evidence/research/design-wire-safety-gap-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/evidence/research/design-wire-safety-gap-20261022.md`
- `.agenticdoc/mw-decision-dashboard/workers/dd-drq5-wire-safety/**`

## 写入禁止面
- 所有源代码/配置/生产档案/其他key/相位文档。

## 交付格式
唯一证据≤220行：结论、真实函数链、脱敏/限长/锁/context方案、矛盾修正、VC、未覆盖；report.md四段结论/证据/残留/上下文来源≤50行。先骨架落盘。每次read≤150行，完整阅读相关函数，不全量dump、不执行测试/网络；研究可提出验证但不能声称已通过。
