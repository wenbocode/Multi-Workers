# W-05 — 文档 + 审计终稿 + 全量 verify（B3 收尾束）

- key: mw-console-storm-hardening · type: coding · 波次 3（串行尾；W-01/02/03a/03b/04a/04b 全部终态）
- ac_refs: AC-002, AC-009, AC-010 · vc_refs: VC-002, VC-009, VC-010
- timeout: 90

## 上下文

goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」；spec.md AC-002/009/010；design.md D-004/D-006。实现面已全落地：`mw.py` cmd_start L0 + `console_run.py`（W-01）、`mw_console_guard/`（W-02）、TS `shared/run-detached.ts` + 双激活注册 + shell 门控（W-03a）、`/mw run-detached` + USAGE（W-03b）、测试 `test_mw_console_guard.py`（W-04a，11 passed）+ `test_console_storm_guard.py`（W-04b，6 passed）+ TS suite 13 passed（W-03b）。机制依据 M1（判据 = GetConsoleProcessList）/M2/M3（evidence/research/design-win32-console-semantics-20261015.md）。锚点: `packages/multi-workers/README.md:1`（CLI 参考表所在）、`packages/multi-workers/UPDATE.md:1`（指令矩阵）、`.agenticdoc/mw-console-storm-hardening/evidence/research/design-spawn-site-audit-20261015.md`（审计表待复核）、`packages/multi-workers/CHANGELOG.md:1` 与 `packages/coding-agent/CHANGELOG.md:1`（[Unreleased] 节）

## 要求

1. **README 新节**（`packages/multi-workers/README.md`，放 CLI 参考之后）：「Windows detached-run checklist」——三事实（DETACHED_PROCESS×CREATE_NO_WINDOW 互斥；组合时 DETACHED 静默生效；后代进程窗口外溢）+ 判据（GetConsoleProcessList 计数区分隐藏控制台与无控制台，GetConsoleWindow 不可用）+ `mw run-detached` 用法（4 行 handoff、marker/heartbeat 契约、`MW_CONSOLE_GUARD=0` 退出）+ guard 机制一句话（env 激活 sitecustomize、显式 flag 不动）。文案与 spec AC-009 字面对齐。
2. **UPDATE.md**：指令矩阵补 `run-detached` 行（版本锚点格式照现有行）。
3. **CHANGELOG**（两包）：读各自 `[Unreleased]` 全节后**追加**（Added 小节），不新开重复小节、不动已发布版本节：mw 包 = L0 除雷 + run-detached + console guard + 守卫测试；coding-agent 包 = mw_run_detached 工具 + /mw run-detached + shell 门控。
4. **审计表终稿复核**：逐行对照当前代码核 `design-spawn-site-audit-20261015.md`（mw.py:506 区域、console_run.py、mw_console_guard/ 是否与表一致），不一致处改表并标注复核时间。
5. **全量 verify**（原始输出留盘 `evidence/runs/verify-mw-console-storm-hardening-20261015.md`，新建）：
   - Python：`python -m pytest test_console_storm_guard.py test_mw_console_guard.py -q -s`（17 passed 预期）+ 包全套 `python -m pytest -q 2>&1 | tail`（对照零新增失败；既有红列清单并归类非本 key）
   - TS：`node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-run-detached.test.ts`（13 passed）+ `npx tsgo --noEmit`（0）+ biome 三文件（干净）
   - 冒烟：`python mw.py run-detached --run-dir %TEMP%\mw-csg-w05 -- cmd /c ping -n 3 127.0.0.1 >nul` → marker rc=0 + heartbeat ≥1 次更新
   - **AC-001E EnumWindows 实测**：复用 `%TEMP%\mw-csg-rq1\winwatch.py`（若在）或重写同款（250ms 轮询、新窗按 hwnd 去重、owner exe 过滤 WindowsTerminal/OpenConsole/conhost）→ 临时目录 project 下 `python mw.py start --project <tmp>` → 观察 60s → 断言终端属主新可见窗 = 0 → `python mw.py stop --project <tmp>`。**本项预期零弹窗**（serve 树全隐藏控制台）；若实测出现窗口即为 FAIL 需上报
   - 汇总 `[VERIFY] VC-001..VC-010` 每条一行（VC-005/006/007 引用 W-04a 输出、VC-003 引用 W-04b 输出、VC-008 引用 W-03b 输出——抄原始行，不重跑）
6. 输出卫生（硬性）：每命令 stdout ≤30 行，长输出落文件取 tail；**禁止**全量 `npm test` / `npm run build`；禁 git add/commit。

## 写入允许面

- `packages/multi-workers/README.md`、`packages/multi-workers/UPDATE.md`、`packages/multi-workers/CHANGELOG.md`、`packages/coding-agent/CHANGELOG.md`
- `.agenticdoc/mw-console-storm-hardening/evidence/research/design-spawn-site-audit-20261015.md`（终稿复核）
- `.agenticdoc/mw-console-storm-hardening/evidence/runs/verify-mw-console-storm-hardening-20261015.md`（新建）
- `%TEMP%/mw-csg-w05/`（冒烟现场，仓库外）

## 写入禁止面

- 一切源码/测试（全部只读复核）；pi 核心；禁止 git add/commit

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_console_storm_guard.py test_mw_console_guard.py -q -s 2>&1 | Select-Object -Last 4
python mw.py run-detached --run-dir $env:TEMP\mw-csg-w05 -- cmd /c ping -n 3 127.0.0.1 ^>nul 2>&1 | Select-Object -First 4
Get-Content $env:TEMP\mw-csg-w05\marker.json
grep -c "VERIFY" ..\..\.agenticdoc\mw-console-storm-hardening\evidence\runs\verify-mw-console-storm-hardening-20261015.md
```

## 改动历史

- 2026-10-15 W-05 首派（收尾束；实现束全部终态后）。

## 交付格式

- 文档 diff 摘要（README 节/UPDATE 行/两 CHANGELOG 追加段）+ 审计表复核结论（一致/已改行）+ verify 文档全文 + 全部 `[VERIFY]` 行。
- 输出卫生：每条命令 stdout ≤30 行。
