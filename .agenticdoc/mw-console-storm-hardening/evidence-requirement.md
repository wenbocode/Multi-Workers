# evidence-requirement — mw-console-storm-hardening

> 每个 VC 的证据形态与判定；全部 [VERIFY] 行最终汇入 `evidence/runs/verify-mw-console-storm-hardening-20261015.md`（W-05 创建）

| VC | AC | 证据要求（原始输出级） | 产生者 |
|----|----|------------------------|--------|
| VC-001 | AC-001 | 单测：monkeypatch 捕获 cmd_start 的 Popen kwargs → flags 集合恰 {CREATE_NO_WINDOW, CREATE_NEW_PROCESS_GROUP} + serve-console.log 重定向断言；[VERIFY] 行 | W-04 |
| VC-002 | AC-002 | 守卫 grep：非测试 .py `DETACHED_PROCESS` 命中 = 0（命令 + 计数）+ design-spawn-site-audit 文件存在断言 | W-04 |
| VC-003 | AC-003 | 集成：run-detached 真实短命令 → Popen 捕获 flags 契约 + marker.json rc/started_at_ms/ended_at_ms/wall_sec 与真实退出码一致 | W-01(冒烟) + W-04(断言) |
| VC-004 | AC-004 | 集成：短心跳间隔下 heartbeat.ts_ms 单调更新；timeout seam 注入 → marker rc=124 + timed_out=true | W-04 |
| VC-005 | AC-005 | 单测（观测入参）：creationflags=0 被 OR；CREATE_NEW_CONSOLE 原样；kwargs 透传 | W-04 |
| VC-006 | AC-006 | 单测：MW_CONSOLE_GUARD 未设 → Popen.__init__ 原对象（零改写） | W-04 |
| VC-007 | AC-007 | 单测（platform seam）：posix 分支 start_new_session=True 无 creationflags；guard 非 nt no-op | W-04 |
| VC-008 | AC-008 | suite 测试（faux provider）：双激活路径注册存在 + shell-role 门控 + cmd/cwd 透传到 spawn 参数 | W-03 |
| VC-009 | AC-009 | README 新节含三事实字面断言（测试 grep 或人工核对 + 引用行号） | W-05 |
| VC-010 | AC-010 | 包既有套件 + 相关 TS suite 对照基线的完整输出 tail（截取汇总行），零新增失败判定 | W-05 |
| VC-001E | AC-001(verify) | EnumWindows 差分实测：`mw start` 后 60s 观测窗内 owner∈{WindowsTerminal,OpenConsole,conhost} 的新可见窗口 = 0（**跑前弹窗预告义务**；本项 0 弹窗，无需预告豁免） | W-05(PM 协助) |

判定规则：每条 [VERIFY] 行必须来自真实命令原始输出（pytest `-s` / vitest stdout / python -c），禁止"应该绿"；无法取证写明缺失原因并停止（P-016 惯例）。
