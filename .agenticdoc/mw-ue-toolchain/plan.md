# Plan: mw ue-toolchain

> Key: mw-ue-toolchain
> 创建时间: 2026-09-21

## 任务分解（实施实况：全部主窗口完成，未派发 worker——流程偏差记录于 key-decision.md）

| # | 任务 | 产物 | 依赖 |
|---|------|------|------|
| T1 | mw_common 三纯函数 + hashlib 导入 | `sha256_eol_normalized` / `discover_build_targets` / `scan_build_error_lines`（含 `_BUILD_ERROR_RE`） | - |
| T2 | mw.py `cmd_toolchain` 三动词 + argparse 子子解析器 + 派发 | `_toolchain_run_dir` / `_toolchain_load_config` / `_toolchain_run` / `_toolchain_targets` / `_toolchain_hash` / `cmd_toolchain` | T1 |
| T3 | 测试 `test_toolchain_cli.py` | 14 用例（助手单测 + run/targets/hash 端到端，hermetic） | T1,T2 |
| T4 | 指南入仓 + README/CHANGELOG/_target_template 注释 | `docs/dual-toolchain-practice-guide.md`（含头注）、README dual 节 + CLI 表、CHANGELOG [Unreleased] | T2 |
| T5 | 定义域钉死 + 改名 `ue-toolchain` | help/docstring/模板注释/README/CHANGELOG/指南头注统一定义域；动词改名；真机派发验证 | T2,T4 |
| T6 | 全量回归 + 真机冒烟 + 补登记 key | 722 passed / 9 deselected；`npm run check` exit 0；CLI 派发四项 PASS；本 key 全套文档 | T5 |

## 顺序与验证点

T1 → T2 →（T3 与 T4 可并行）→ T5 → T6。每步验证点：T3 单测 14 过；T5 真机 CLI 层（单测绕过 argparse，必须实跑）；T6 全量。
