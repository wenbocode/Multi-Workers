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

## P-002 会话内修改跨窗口共享配置文件（2026-09-15，mw-protected-config-guard 前置事故）
- 现象：所有 pi 窗口报 `Error: Provider is not configured: timi`，多个窗口死机；`~/.pi/agent/auth.json` 被运行中的会话清掉（只剩 timi 条目，其余凭据一并丢失）。
- 根因：auth.json 是所有窗口共享的活跃凭据存储（AuthStorage 按文件 revision 热重载）——任何会话内 write/edit/bash 直接改它，等于在其它窗口脚下抽掉凭据；会话工具层此前无任何防护。
- 硬规则（规避）：
  1. 运行期间绝不在会话内修改 `~/.pi/agent/` 下的 auth.json / models.json / settings.json / oauth.json（及 agentDir 本身）。agent-team-loop 扩展已在 tool_call 层硬拦截（`shared/protected-config.ts`，PM/Worker/交互三模式全覆盖）；mw 框架 Python 侧同规则（`mw_common.assert_not_protected_agent_config`）。
  2. 需要改凭据：关闭 pi 窗口后在普通终端编辑，或用 `pi /login`（core 流程，不在拦截范围）。
  3. 读不受限；worker 模式被拦截时向任务 trace.log 落 `[PROTECTED_CONFIG]` 行（PM watch 实时可见）。
- 关联：2026-09-15 事故（全窗口凭据丢失，多窗口死机）；guard 落地与验证见 mw-protected-config-guard/mini-spec.md。

## P-003 `open(p, "w")` 先截断后求值——写/改文件静默清零（2026-09-21，PM 自身缺陷登记 #50）

- 现象：PM 用 `io.open(p, "w")` 改脚本时，内层表达式（替换/序列化）抛错 → 文件已被截断成 0 B；而空 .py 文件 `py_compile` 仍通过 ⇒ 复验一度「静默成功」。
- 根因：Python `open(path, "w")` 在 open 时立即截断文件，而 `f.write(expr)` 的实参在截断之后才求值；表达式抛异常时文件已是 0 B。空文件是合法空模块，只看 `py_compile`/退出码的复验无法发现内容丢失（假阳性）。
- 硬规则（规避）：
  1. 程序化改写一律「先算后写」：把最终内容完整算进变量，再 `pathlib.Path.write_text(content, encoding="utf-8")` —— 实参先求值再开文件，异常时原文件不动。框架生产代码已全部此风格（advance_phase.py / update_index.py / conductor.py 等，2026-09-21 审计确认）。
  2. 需要防半写/并发读时用「临时文件 + `os.replace` 原子改名」（`mw_common._write_workers_file`、mw.py `_atomic_write_yml` 即此法；autopilot/dispatch.py 队列写入已于 2026-09-21 对齐，序列化生成器不再在截断后求值）。
  3. ad-hoc 一次性脚本同样遵守；确实要原地改且无版本控制兑底时，先 `shutil.copy2` 备份。
  4. 复验禁止只看 `py_compile` / 退出码：必须断言文件非空 + 关键内容锚点（grep 关键行）。
- 关联：PM 自身缺陷登记 #47~#52（2026-09-21，另一窗口引述；登记原文不在本仓）；#50 为本条来源，涉事脚本已由当事 PM 重写。
