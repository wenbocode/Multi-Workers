# W-06 — QG 快修:F1/F2/F3 + N1/N2/N4

- key: mw-console-storm-hardening · type: coding · 波次 4.5（QG PASS 后快修，范围冻结 = 本卡清单）
- timeout: 60

## 上下文

goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」；QG 审读 evidence/review/qg-console-storm-20261015.md §7 分级清单（本卡 = 其中 3 minor + 3 note 的定向修复，其余项维持记录在案）。**写面守卫注意**：每行 bullet 只放一个反引号路径。**红线**：不得削弱既有断言；VC-004a（--heartbeat-s 0.5）与 VC-004b（--timeout-min 0.05）依赖小数/亚秒值合法，下界必须是「> 0」而非整数下限。

## 要求（QG 行号为准，逐项给 diff）

1. **F1** `packages/multi-workers/console_run.py:66`（run_dir exists→mkdir TOCTOU）：改竞态安全创建（`Path.mkdir(parents=True, exist_ok=True)` 或 try/except FileExistsError 收敛），删除先 exists 后 mkdir 的窗口。
2. **F2a** `packages/multi-workers/console_run.py:266`（argparse 无下界）：`--heartbeat-s` 与 `--timeout-min` 加正数校验（自定义 type 或后置检查，值 ≤ 0 → 干净报错退出非 0）；**允许小数**。
3. **F2b** `packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts:175`（schema 无 minimum）：`heartbeat_s`/`timeout_min` 加 `Type.Number({minimum: ...})` 正数下界（与 F2a 语义一致，允许小数）；负值在工具层报结构化错误。
4. **F3** `packages/coding-agent/test/extensions/agent-team-loop-run-detached.test.ts`（VC-008 argv_passthrough 恒真）：把透传断言改为**精确 argv 相等**（mock spawnSync 收到的完整 argv 数组逐元素断言，含旗标与 `--` 后原样段），删除恒真形态；`[VERIFY] VC-008` 行保持打印。
5. **N1** `packages/multi-workers/console_run.py`：删冗余 `import subprocess as _sp`（如存在别名重复导入）。
6. **N2** `packages/multi-workers/console_run.py`：serve_log_fh 用 with/finally 显式关闭（ supervise 路径异常时也不泄漏句柄）。
7. **N4** `packages/multi-workers/mw_console_guard/mw_console_guard.py`：creationflags 位置传参的 docstring 措辞改为实情（位置传参遇 kwonly 化补丁 → TypeError，非静默绕过）。
8. 改后**必须复跑**：Python `python -m pytest test_console_storm_guard.py test_mw_console_guard.py -q -s`（17 passed，VC-003/004a/004b 原值不变）+ TS `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-run-detached.test.ts`（13 passed）+ `npx tsgo --noEmit` + biome 三文件。红 → 修到绿为止。
9. 硬规则：P-003 原子写、显式 `encoding="utf-8"`、erasable TS、top-level import、禁碰 pi 核心/`mw.py`/ui-bridge.ts/注册点文件、禁 PowerShell 改写源文件、禁 git add/commit、禁 `npm run build`、每命令 stdout ≤30 行。

## 写入允许面

- `packages/multi-workers/console_run.py`
- `packages/multi-workers/mw_console_guard/mw_console_guard.py`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts`
- `packages/coding-agent/test/extensions/agent-team-loop-run-detached.test.ts`
- `packages/multi-workers/test_console_storm_guard.py`（仅当 F1/F2 触及其断言时同步，禁削弱）
- `packages/multi-workers/test_mw_console_guard.py`（仅当 N4 触及其断言时同步，禁削弱）

## 写入禁止面

- `mw.py`、ui-bridge.ts、两注册点文件、pi 核心、`shared/dispatch-models.ts`、README/UPDATE/CHANGELOG、`.agenticdoc/**`（证据文件只读）；禁止 git add/commit

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_console_storm_guard.py test_mw_console_guard.py -q -s 2>&1 | Select-Object -Last 4
cd ../coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-run-detached.test.ts 2>&1 | Select-Object -Last 6
npx tsgo --noEmit 2>&1 | Select-Object -Last 3
npx biome check --error-on-warnings src/extensions/agent-team-loop/shared/run-detached.ts test/extensions/agent-team-loop-run-detached.test.ts 2>&1 | Select-Object -Last 3
```

## 改动历史

- 2026-10-15 W-06 首派（QG PASS 后快修波次，范围 = QG §7 的 F1/F2a/F2b/F3 + N1/N2/N4）。

## 交付格式

- 逐项 diff 摘要（F1/F2a/F2b/F3/N1/N2/N4 各一段，标 QG 编号）+ 验收原始输出（≤6 行/命令）+ `[VERIFY] VC-003/004a/004b/008` 复跑行。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
