# T5: 定义域钉死 + 改名 ue-toolchain

- 状态: done（主窗口直做；用户两轮指出：Q1 指令在做什么 → 解释 + 定义域钉死，Q2 建议 ue_toolchain → 采纳改名为 kebab 风格 `ue-toolchain`）
- 产物:
  - 定义域六处钉死：mw.py 模块 docstring / 子解析器 help / run help / `_target_template` 注释 / mw_common 节头 / README 定义域段落 + 指南头注 + CHANGELOG 条目。
  - 改名：`toolchain` → `ue-toolchain`（argparse 子命令名 + 派发键 + 10 处 `[mw ue-toolchain]` 前缀 + 文档全部命令示例）；target.yml 键 `toolchain:` 与 mw_common 函数名不改（内部/配置面）。
  - 途中修掉：改名替换漏掉 `mw.py toolchain`（带 .py）形态的 README 三条示例；上次失败 edit 与成功 edit 交错造成的模板注释块错位。
- 佐证: 真机 CLI 派发验证四项 PASS（`ue-toolchain --help`/`run`/`targets` rc=0；旧动词 `toolchain` rc=2 无别名）；`mw toolchain` 残留引用全仓 grep 0 hits。
