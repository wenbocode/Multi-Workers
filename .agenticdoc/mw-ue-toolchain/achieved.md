# Achieved: mw-ue-toolchain

> Key: mw-ue-toolchain
> 结案时间: 2026-09-21

## 系统行为变化

- **新增 `mw ue-toolchain` CLI 动词**（`python mw.py ue-toolchain ...`）：
  - `run <name> [--args=STR] [--watch PATH] [--out DIR] [--json]`——控制根执行 target.yml 的 `toolchain.<name>` 模板并留证（cmd.txt / run.log / exit.txt / errors.txt / meta.json）；mw 退出码为合成判定（exit 0 ∧ 错误签名 0 ∧ watch 漂移 0）；差分验收对比两次 errors.txt 集合。
  - `targets`——`<game>/Source/*.Target.cs` 现查构建目标名（`*Editor`=editor target）。
  - `hash`——EOL 归一化 sha256。
- **mw_common 新增三个纯函数**：`sha256_eol_normalized` / `discover_build_targets` / `scan_build_error_lines`（MSVC/UE 签名集 `error C`/`LNK\d{4}`/`error :`，噪声行天然不命中）。
- **文档面**：实践指南入仓 `packages/multi-workers/docs/dual-toolchain-practice-guide.md`（WXWork 缓存原件固化 + 框架吸收边界声明）；README dual 节「工具链执行纪律」+ 定义域段落 + CLI 表行；CHANGELOG [Unreleased] Added；`_target_template` 注释给 canonical UBT 示例。
- **定义域**：dual UE 游戏开发（游戏仓+引擎源码仓+MSVC/UBT），六处钉死（动词名/help/模板注释/mw_common 节头/README/指南头注）；旧动词 `toolchain` 不留别名。
- **测试**：`test_toolchain_cli.py` 14 hermetic 用例；全仓 722 passed / 9 deselected、`npm run check` exit 0。

影响面：仅 `packages/multi-workers`（mw.py / mw_common.py / docs / README / CHANGELOG / 新测试文件）；无 TS 改动；target.yml 配置键 `toolchain:` 兼容不变。

## 遗留

- **`exclusive_files` 写者唯一性派发检查**（指南 §6.6，harness 工具语义【未验证】）→ 立新 key：需先在派发层验证 `write` clobber / `edit` fail-safe 行为，再设计检查。
- **`/mw` 窗口 TS 转发**（PM 窗口 bash 直跑 CLI 已可用）→ 立新 key：ui-bridge + mw-runner 侧转发，需窗口重启验证。
- **非 UE 工具链错误签名可配置**（将来接 Gradle 等时做对应动词或配置项）→ 接受暂不处理，事实已记录于 help 文本。
- **差分验收真实用例**：待首个真实 UE dual 项目落地（spec §4 待确认项）→ 接受暂不处理。
- **F-1**（multi-word `--reason` 破坏 `/worker` 旗标解析）→ 沿 mw-dispatch-role-escape 遗留，不属本 key。
- **流程债务**：本 key 为野生实施事后补登记 → 已在本 key key-decision.md 留偏差记录；后续一律走 spec → key → claim → dispatch。
