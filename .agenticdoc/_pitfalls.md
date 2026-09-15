# Pitfalls — 坑点台账

> 项目级记忆文档之一（pm-mind Hook 2：spec 生成前必读，§5「需规避坑点」取源；同一坑点跨 key 复现时升级 [高危]）。

## P-001 PowerShell 文本管道损坏无 BOM UTF-8 文件（2026-09-11，mw-dual-workspace）

- 现象：`.agenticdoc/mw-dual-workspace/spec.md` 全文中文变 mojibake；`_index.parallel` 7 处 `—` 变 `鈥?`。
- 根因：Windows PowerShell 5.1 的 `Get-Content -Raw` 对无 BOM 的 UTF-8 文件按系统 ANSI 代码页（cp936/GBK）解码，`[System.IO.File]::WriteAllText` 再按 UTF-8 回写——双重编码；GBK 解码遇无效序列按 best-fit 替换为 `?`，部分字节不可逆丢失（`—` 的第三字节 0x94 丢失后无法机械反解）。
- 硬规则（规避）：
  1. 对 `.agenticdoc/` 及一切 UTF-8 文本的程序化改写：一律用 edit 工具，或 Python 显式 `encoding="utf-8"`（字节级 `read_bytes`/`write_bytes` 最稳）。
  2. 禁止 PS `Get-Content`/`Set-Content`/`WriteAllText` 对无 BOM UTF-8 文件做读-改-写往返；控制台输出的乱码与文件真实损坏不可区分，须用 read 工具（正确解码）判定。
  3. 修复手段备忘：确定性 mojibake（如 `—`→`鈥?`）可字节级反向替换；全文损坏从完整修改历史重建（mw-dual-workspace spec.md 即此法恢复，0 内容损失）。
- 关联：mw-dual-workspace spec 锁定时间戳插入时触发（2026-09-11 15:01），同轮已修复并验证（read 工具抽查 + mojibake 检索 0 命中 + audit PASS）。
