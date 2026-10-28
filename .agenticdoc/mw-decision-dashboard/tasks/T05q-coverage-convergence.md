# T05q 覆盖判定阻塞修复（有界收敛）

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358 全输出known秘密保护。
- `packages/multi-workers/decision.py:1118` _redactor_covers；`decision_points.py:4297` 同语义副本。
- workers/dd-review-redactor-contract/report.md F1明确静态触发，F2协议缺失导致capture静默停摆。用户质疑任务不收敛，PM要求仅此明确阻塞修复，不顺带扩大研究债。

## 要求
完整读必要改动文件，保存未改基线，先真实RED测试：hits虚报且原值仍在、仅加前缀、部分替换留secret尾部、无hits文本变化；client与points入口均覆盖。真实loopback仅tmp合成凭证，证明实际raw落盘或实际错误放行，静态trigger不冒称已实测。
注意review建议value not in output仅能挡完整原值残留，不能挡部分替换后尾部，不能照抄然后声称关闭F1。选最小可证明安全实现：对已知集合使用独立可信边界清洗，或明确验证并拒绝不满足完整清洗契约的回调。保持caller回调不替换与合法回调功能；任意有状态回调探测不能被当安全证明。若在允许面无法保证使用时输出安全，停并报告所需最小wire边界写面，不自报GREEN整体关闭，不再自行扩大任务。
F2合并协议检查：缺scrub_tail_prefix的回调明确安全拒绝或capture错误可观测，不能默默0行却称完整采集。不能因协议错移除合法用户回调功能。完整值与长secret尾部在正文/任意metadata键值/失败输出全部验，无secret日志自由文本泄漏。
保留无scope显式key0额外auth、production once发现、retry稳定、下call刷新、完整pin/crosscfg冻结、ContextVar复位、sink失败best-effort。禁typed/required/预算/ref/registry变动。
所有测试tmpHOME/USERPROFILE/auth、env后缀清理、真实读路径前spy，HTTP只隔离127.0.0.1。不读真实凭证，不模型外网。

## 写入允许面
- `packages/multi-workers/decision.py`（覆盖安全）
- `packages/multi-workers/decision_points.py`（同一覆盖安全消费）
- `packages/multi-workers/test_decision_coverage_safety.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-coverage-convergence/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05q-*`

## 写入禁止面
其他源测试、wire、旧报告、相位、真实凭证生产、依赖锁、生成物、typed、required、预算、ref。

## 验收命令
包目录 `python -m pytest test_decision_coverage_safety.py test_decision_redactor_contract.py test_decision_pin_contract.py test_decision_full_value_freeze.py test_decision_credential_seam.py test_decision_wire_transport.py -q`，完整argv/cwd/UTC/exit/hash日志。root只读check子步与biome，不跑write完整check/build/commit/全包pytest/服务/browser。

## 改动历史
- PM完整吸收ack T05p CHANGES_REQUIRED。仅明确泄漏F1阻塞修复，F2合并；不得将value不在output当尾部安全证明。最多一轮交付，不能收口则给最小写面需求由PM决定。

## 交付格式
report最多100行：真RED、实际漏洞与修复、完整值和尾部安全、协议观察、验收或明确阻塞、未覆盖。不自报reviewPASS/T06放行。
