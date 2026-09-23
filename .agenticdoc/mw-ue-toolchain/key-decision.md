# KDR: mw-ue-toolchain

## R（需求）
- 技术栈: Python stdlib（mw.py CLI）+ pytest + Markdown
- 边界: 只吸收实践指南通用部分（§9.B）；exclusive_files 检查、TS 转发、非 UE 签名可配置不做
- 关键约束: 复用 target.yml 既有配置面；定义域 = dual UE 游戏开发；Windows/PS 5.1 主环境
- 指南来源: AssetImportGate 前线实践（WXWork 缓存原件 → 入仓 `docs/dual-toolchain-practice-guide.md` 固化）

## A（架构）
- 三动词：`run`（执行留证+合成判定）、`targets`（目标现查）、`hash`（EOL 归一化）
- 三个纯函数下沉 mw_common：sha256_eol_normalized / discover_build_targets / scan_build_error_lines
- run 目录默认 `<control>/.mw/toolchain-runs/<YYYYMMDD-HHMMSS>-<name>/`，`--out` 可归档进 key evidence
- 合成判定：mw 退出码 = exit 0 ∧ 错误签名行 0 ∧ --watch 漂移 0
- 命名：`ue-toolchain`（kebab，与 update-env/pull-agentictask 一致）；target.yml 键保留 `toolchain:`
- `--args` 单字符串 + 等号形式（argparse REMAINDER 吞 `--project` 的坑，见 research）

## I（实施）
- [流程偏差记录] 需求讨论（映射表确认）后未走实施准入门禁：未建 key、未派发 worker，主窗口直做全部 6 个任务；本 key 为事后补登记。后续 follow-up（exclusive_files / TS 转发）必须按 spec → key → claim → dispatch 流程走。
- 阶段执行实况：mw_common 3 助手 → mw.py CLI+argparse → test_toolchain_cli.py 14 用例 → 指南入仓+README/CHANGELOG → 定义域钉死 + 改名 ue-toolchain（真机派发验证四项 PASS，旧动词 rc=2 拒绝）
- 验证：全量 722 passed / 9 deselected；`npm run check` exit 0；真机冒烟（targets/run/hash/dispatch）
