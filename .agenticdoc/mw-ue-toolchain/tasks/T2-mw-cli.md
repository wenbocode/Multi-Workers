# T2: mw.py ue-toolchain CLI

- 状态: done（主窗口直做）
- 产物: `_toolchain_run_dir`（同秒后缀防冲突）、`_toolchain_load_config`（fail-closed）、`_toolchain_run`（执行留证 + 合成判定 + --watch 前后哈希 + --args 转发 + --json）、`_toolchain_targets`、`_toolchain_hash`、`cmd_toolchain`；argparse 子子解析器（run/targets/hash）；派发 dict 注册 `ue-toolchain`。
- 关键决策: `--args` 单字符串等号形式（REMAINDER 会吞 name 后的 `--project`，真机复现命中；见 evidence/research/design-cli-shape）。
- 佐证: `packages/multi-workers/mw.py`（toolchain 节，partition 节之前）；`test_toolchain_cli.py::TestToolchainRun` 7 用例 + TargetsAndHash 4 用例。
