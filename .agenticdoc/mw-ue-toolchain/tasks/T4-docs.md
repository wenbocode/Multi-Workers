# T4: 指南入仓 + 文档

- 状态: done（主窗口直做）
- 产物:
  - `docs/dual-toolchain-practice-guide.md`：45,489 bytes 原文 Copy-Item 入仓 + 头部入仓说明（出处 / §9.B 已吸收 / §9.A 项目层 / 定义域声明）。
  - `README.md`：dual 节 toolchain yml 注释更新 + 「工具链执行纪律」小节（含定义域段落）+ CLI 参考表行。
  - `CHANGELOG.md` [Unreleased] Added 条目。
  - `mw.py` `_target_template`：toolchain 注释块（canonical build_editor/-WaitMutex、build_local/-NoUBA -MaxParallelActions=16 示例 + 指南指针 + 合成判定说明）。
- 佐证: 上述四个文件；`mw.py toolchain --help`（改名后 `ue-toolchain --help`）渲染正常。
