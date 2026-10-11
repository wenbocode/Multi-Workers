# PM State: mw-console-title-clobber

## 1. Snapshot
- Key: mw-console-title-clobber
- Claim-Id: —
- Phase: DONE
- Next Action: 已结案（DONE）。遗留：`interactive-mode.ts` 事后恢复路径（D-001）、其它 CLI 探针审计、`/mw build` + `/mw restart` 使修复生效（D-002）。
- Started: 2026-10-11 23:19
- Updated: 2026-10-11 23:23
- Completed: 2026-10-11 23:23

## 2. Task Status
*(trivial-fix fast path：两侧各 1 处小改 + 1 个 Python 回归测试；未派 worker，PM 直执)*

## 3. Evidence Ledger
| ID | 证据 | 文件 |
|---|---|---|
| E-1 | 受控实验：继承控制台的 `pi --list-models` 子进程把宿主标题改成 `pi`；`CREATE_NO_WINDOW` 与 `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW` 均 safe（哨兵标题法） | `evidence/e2e-sentinel-20261011.txt` |
| E-2 | 代码不对称：`launcher.py:1104` / `mw.py:277` / `mw.py:438` 已隔离 spawn，`mw_common.py:1450` 未隔离 | `mini-spec.md` §依据 3 |
| E-3 | 触发面枚举：`/mw model show`（`mw.py:3257/3272`）、`/mw model set`（`:3183`）、`/mw doctor`（`mw_common._doctor_dispatch:1292`） | `mini-spec.md` §依据 4 |
| E-4 | AC-1 回归：`test_common.py` 78 passed，含 `[VERIFY] AC-1: probe_creationflags=134217728 platform=win32` | `evidence/probe-flags-20261011.txt` |
| E-5 | AC-2 / AC-3 端到端哨兵：旧调用形态 A CLOBBERED→`pi`、修后 `_probe_model_rows()` safe、`mw.py model show` safe；A'（HEAD 版 cli.ts 管道 stdout）CLOBBERED、B'（修后）safe | `evidence/e2e-sentinel-20261011.txt` |
| E-6 | VC-1：`npm run check` exit=0（biome 1119 files 无改写 / tsgo 无输出 / 其它检查全过） | `evidence/check-20261011.txt` |
| E-7 | 交叉：CLI 相关 7 测试文件 82 passed / 3 failed；同 3 个失败在 HEAD 版 `cli.ts` 下同样失败（环境基线） | `evidence/ts-cli-tests-with-change-20261011.txt` + `…-baseline-head-20261011.txt` |
| E-8 | 质检门 **PASS**：5 问 5 充分（AC-1/AC-2/AC-3/VC-1/交叉） | `evidence/quality-gate-report-20261011.md` |

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions
- D-001：pi 侧不做"扩展命令后恢复标题"（需在 core 事件层加钩子，改动面大），改为在源头收窄——`cli.ts` 只在 `process.stdout.isTTY` 时设 `process.title`。理由：子进程（探针 / worker / RPC）的 stdout 都是管道或文件，本就不该改宿主控制台标题；交互直跑行为不变。两者可并存，恢复路径留待需要时另立 key。
- D-002：不改 dist/bundle（需 `/mw build`，由用户执行）；不新增 CHANGELOG 条目（无 API/配置面变化）。

## 6. Turn End Records
*(empty)*

## 7. Process Log
- 23:19：建 key（用户报障：跑 `/mw` 的模型相关命令后窗口标题变 `pi`）。根因用哨兵实验坐实；走 mini-spec 快径。
- 23:2x：两侧实现 + AC-1 回归测试；哨兵端到端（含 HEAD 版 cli.ts 对照）与 `npm run check` 全绿；CLI 相关测试用 HEAD 版做基线 A/B 排除回归；写质检报告与 achieved.md 后 `advance_phase … done`。
