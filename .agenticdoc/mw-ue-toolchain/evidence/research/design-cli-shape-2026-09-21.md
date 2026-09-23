# Research: CLI 形态与两个 argparse 坑（design）

## 决策问题
design 的动词/参数形态、run 目录位置、`--args` 转发机制、命名风格。

## 调研方法与出处
- 复现实验：真机 `mw.py toolchain run build_editor --project X --watch F`（本会话冒烟脚本，输出已删除，结论记录于此）
- 对照仓内既有子命令风格：`update-env`、`pull-agentictask`（kebab-case）
- 对照单测绕过层：`test_toolchain_cli.py` 直接构造 `argparse.Namespace` 调 `cmd_toolchain`，不经 argparse 解析层

## 发现
- **argparse REMAINDER 坑（复现命中）**：`run` 子解析器定义 `extra=nargs=REMAINDER` 时，`run build_editor --project X` 里跟在 name 之后的 `--project` 被 REMAINDER 吞掉 → "the following arguments are required: --project"。真机冒烟抓到；单测因直接构造 Namespace 未覆盖此层。
- **argparse 负号值坑（复现命中）**：`--args "-MaxParallelActions=16"` 的值以 `-` 开头被当未知旗标 → 必须 `--args=...` 等号形式。
- run 目录默认位置权衡：落 key evidence 目录会污染 git status（大日志），落机器本地 `.mw/toolchain-runs/` 是审计轨迹、`--out` 由 PM 主动归档——与指南"证据契约"两档（会话级 vs 归档级）一致。
- 子命令命名：仓内多词子命令均为 kebab（update-env / pull-agentictact）→ `ue-toolchain` 而非 `ue_toolchain`。

## 结论 → 决策映射
- REMAINDER 弃用 → `--args` 单字符串选项（design D-2）；help 文本写明等号形式要求。
- 单测盲区 → 真机 CLI 派发验证四项进验证清单（AC-008）。
- run 目录默认 `.mw/toolchain-runs/` + `--out` 归档（design D-1）。
- 命名 `ue-toolchain`（design D-7；定义域由动词名承载，防非 UE 误用假 OK）。
