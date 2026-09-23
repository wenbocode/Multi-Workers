# Validation runs: mw-implementation-gate（2026-09-21/22）

> 执行环境: Windows / PowerShell 5.1；PM 复跑记录（worker 报告之外独立复验——验证纪律：成功断言前必须自见输出）。

## 1. 守卫 suite 测试（真实工具调用层）

```
$ cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/agent-team-loop-implementation-gate.test.ts
Test Files  1 passed (1)
     Tests  9 passed (9)
```

9 场景：AC-001 write/edit 拦（文件未建/内容未变 + reason 指引 + blocked 审计行）、AC-002 本窗口 claim 放行（claim 行移除后同批再写被拦，证明门中介）+ 他窗口 claim 仍拦、mini 放行（留 mini-pass 审计）与 25h 衰减、worker env 放行/撤销后拦、AC-004 白名单路径过而同批对照 .py 拦、bash 重定向目标拦而 payload 引用过。

## 2. 回归

```
$ node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-protected-config.test.ts
Test Files  1 passed (1)
     Tests  11 passed (11)      # 词法修复未影响 protected-config（独立词法器）

$ npm run check（仓库根，全链）
check-exit=0                    # biome 1056 files / tsgo / pinned-deps / shrinkwrap 等
```

## 3. 接线敏感性（worker 实证，PM 采信并记录）

去掉 index.ts:51 `registerImplementationGate(pi)` 单行 → 9/9 红（初版 6/9，三个纯放行场景补批内对照后全敏感）；恢复后全绿。P-002 反面教材（纯函数测试全绿而接线断）不能在本 key 复发。

## 4. 真缺陷发现与修复（T3 worker）

- 缺陷：bash 词法器把 Windows 反斜杠路径按 POSIX 转义丢弃（`H:\...\mw.py` → `H:...mw.py`）→ 主平台主拼写形态漏拦。探针先证后修。
- 修复：`parseBashSegments` 反斜杠按真实 POSIX 转义集（引号外仅元字符；双引号内仅 `` $ ` " \ `` 换行）。
- 回归：13 必中（含三种 Windows 拼写）/ 10 必避误报全部符合；protected-config 11/11 不受影响。
- 已登记坑点台账 P-004。

## 5. 部署生效面（未验证部分，如实声明）

- 守卫活在 agent-team-loop 扩展 bundle 内：需 `mw setup --build` 重建 dist + 窗口重启后生效；本会话（及当前所有窗口）跑的是旧 bundle，重启前不受门禁——真机拦截体验延后到重启后。
- AC-005（框架仓）：commit `e9360db` 已 push origin/master；`diff-installed.py` exit 0（PM 复核：clone clean、单文件入栈）。
