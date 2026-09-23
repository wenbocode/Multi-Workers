# T3: test_toolchain_cli.py

- 状态: done（主窗口直做）
- 产物: 14 hermetic 用例——TestHelpers（EOL 等价 / 目标发现含非 UE 空返回 / 签名扫描含噪声排除）+ TestToolchainRun（OK 五工件+verdict / 签名+坏退出 / drift fail-even-on-exit-0 / --args 转发 / --out 归档 / 未知名 fail / 缺 engine fail-closed）+ TestToolchainTargetsAndHash（targets 双 kind / 无 Source / hash EOL 等价 / 缺文件 fail）。
- 夹具: 仿 `test_common_target_config.py`（`<control>/.agenticdoc/target.yml`，YAML 单引号 `''` 转义）。
- 途中修的测试 bug: drift 用例先写 w.txt 后建 game 目录（pathlib write_bytes 不建父目录）→ 顺序对调。
- 佐证: `packages/multi-workers/test_toolchain_cli.py`；本会话 `python -m pytest test_toolchain_cli.py -q` → 14 passed。
