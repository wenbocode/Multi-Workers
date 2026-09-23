# T3: 守卫测试（真实工具调用层）

- 状态: done（worker t3-gate-suite-tests，27m）
- 范围: 纯函数单测 + `packages/coding-agent/test/suite/` harness + faux provider 驱动真实 tool_call（覆盖 AC-001/002/004）；MW_IMPL_GATE_ROOT 指向 fixture（临时 _index.parallel / mini-spec）。
- 规格: design.md D-7；反面上教材 = P-002 只测纯函数（W2 缺口①）。
- 验收: AC-001（无 claim 拒 + reason 含指引）/ AC-002（有 claim 放行）/ AC-004（白名单路径不受影响）三场景经真实工具层验证通过。
- 结果: `test/suite/agent-team-loop-implementation-gate.test.ts` 9 用例全绿，走真实派发层（faux provider tool_use → agent-loop → beforeToolCall → ExtensionRunner.emitToolCall → 真实 createExtensionAPI 注册面 → block 处理；仅 bash 后端 stub 为记录器）。接线敏感性实证：去掉 register 行 9/9 红（初版 6/9，三个纯放行场景补了批内对照后达成全敏感）。
- 发现并修复真缺陷：bash 词法器把 Windows 反斜杠全当 POSIX 转义丢弃（`H:\...\mw.py` → `H:...mw.py`，主平台主拼写形态被漏拦）；修复为真实 POSIX 语义（引号外仅转义元字符，双引号内仅 $ ` " \\ 换行），10 项误报必避/13 项必中回归验证。PM 复跑：9/9 + 11/11 + npm run check exit 0。
