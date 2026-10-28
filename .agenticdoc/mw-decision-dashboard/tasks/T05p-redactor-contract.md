# T05p redactor工厂完整快照契约

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358完整known保护。
- `packages/multi-workers/decision.py:965` known_credential_values None-base分支；`:1960` caller-owned production scope。
- workers/dd-review-pin-final/report.md F-R1已确认现存client-only caller误用组合可达，T05o两入口拒绝/异源冻结PASS，所有编码终态。

## 要求
全文分页读源/必要测试，保存未改基线hash，新测试真RED先于实现。known_credential_values对显式None-base快照抛固定安全TypeError，credential_redactor返回None安全omit，known_secret_redactor返回fail_closed门，不能把门工厂返回None当可放行。duck/发现错误/工厂合法快照原安全策略保持；直接类非发送数据构造仍保留，不移除功能。
client-only caller-owned production scope使用None-base工厂结果时全输出安全；新测试实际loopback正文/任意metadata/失败输出，不手造event。检查caller-owned自定义不完整redactor（无None-base但只盖发送值漏legacy）是否现存raw漏洞，若存在用基线真实RED证明并在本卡decision内最小failclosed校验完整known集合（生产采集scope），保持不替换caller-owned回调；不得误变sink失败best-effort、不启用test scope全局注入。若处理需points/mw越面则报PM停。
保留无scope显式key0额外auth、必要production once discovery、retry稳定、下call刷新、完整工厂pin/跨cfg union/ContextVar复位。异常与错误字符串不得回显任何key值或自由异常message。同步_known字段注释首读异源折叠语义，仅必要文档。
测试一律tmpHOME/USERPROFILE/auth与env后缀全集清理，真实路径读前spy阻断，HTTP仅隔离127.0.0.1，不真实凭证/Jev。

## 写入允许面
- `packages/multi-workers/decision.py`（工厂完整性与必要caller-owned采集校验）
- `packages/multi-workers/test_decision_redactor_contract.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-redactor-contract/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05p-*`

## 写入禁止面
所有其他源测试、旧报告、相位、真实凭证生产、依赖锁、生成物、typed、required、预算、placeholder、ref。

## 验收命令
包目录 `python -m pytest test_decision_redactor_contract.py test_decision_pin_contract.py test_decision_full_value_freeze.py test_decision_bare_scope_known_set.py test_decision_known_set_snapshot.py test_decision_credential_seam.py test_decision_timi_credential_snapshot.py test_decision_wire_transport.py -q`，完整argv/cwd/UTC/exit/hash前后，两轮各独立全日志。root只读biome和check子步；完整check未跑不等价，禁全包pytest/build/commit/服务/browser/Jev。

## 改动历史
- PM吸收T05o PASS，F-R1不接受调用方误用免责，单文件最小工厂契约收尾，dispatch迁移仍未关不混本卡。

## 交付格式
report≤110行，真RED/GREEN/三API拒绝/实际caller-only安全或缺口/冻结发现次数/完整验证证据/未覆盖，不自报reviewPASS/T06放行。
