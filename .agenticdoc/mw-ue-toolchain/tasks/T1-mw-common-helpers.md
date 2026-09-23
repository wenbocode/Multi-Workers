# T1: mw_common 三纯函数

- 状态: done（主窗口直做）
- 产物: `sha256_eol_normalized`（CRLF→LF 后 sha256）、`discover_build_targets`（`Source/*.Target.cs` 现查，`*Editor`=editor）、`scan_build_error_lines`（`error C\d{1,5}|LNK\d{4}|error :` 逐行匹配）+ `_BUILD_ERROR_RE` + `import hashlib`；节头 scope 注释（dual UE / MSVC-UBT）。
- 佐证: `packages/multi-workers/mw_common.py`（toolchain_probe_path 之后的纪律助手节）；`test_toolchain_cli.py::TestHelpers` 3 用例。
