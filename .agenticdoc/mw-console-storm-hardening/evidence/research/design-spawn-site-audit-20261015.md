# Spawn 站点审计表（L0 后归属）— design 交付物（AC-002 证据面）

> date: 2026-10-15 · 基线: spec-spawn-site-survey-20261015.md + design.md D-001（L0 改动后状态）
> **终稿复核: 2026-10-15（W-05 收尾束）**：逐行对照当前代码（mw.py / console_run.py / mw_console_guard/ / launcher.py / mw_common.py / autopilot/）。W-01 落地后 mw.py 行号整体下移（cmd_start 新增注释 + serve-console.log 重定向 + run-detached 挂接），本表位置列已按复核时实际行号更正；**归属结论无变化**（每站点的 flag/继承/前台归属保持原判）。复核变更行以粗体标注。
> 归属语义: **flag** = 站点显式设 win32 console flag；**继承** = 祖先隐藏控制台兜底（M1，RQ-1 E1 实证）；**前台** = 仅前台 CLI 路径可达（用户控制台，无弹窗风险）；**隐藏自持** = 自身以 CREATE_NO_WINDOW 获新隐藏控制台（非继承）

| 站点 | 位置 | L0 后归属 | 备注 |
|------|------|-----------|------|
| `mw start` → serve | **mw.py:519**（cmd_start creationflags；`def cmd_start` :485） | flag（CREATE_NO_WINDOW+NEW_GROUP）+ 隐藏自持 | stdio 重定向 `.mw/serve-console.log`（新增，mw.py:512-516） |
| serve → conductor | **mw.py:233** | flag + 继承双保险 | spawn_kwargs（mw.py:338 设 CREATE_NO_WINDOW） |
| serve → proxy | **mw.py:378** | flag + 继承双保险 | on-demand |
| serve → launcher | **mw.py:395** | flag + 继承双保险 | |
| serve 身份采集 `_git` | **mw.py:4456**（creationflags）/4458（subprocess.run）；`def _git` :4440 | flag + 继承双保险 | |
| launcher → worker pi | launcher.py:2007 | flag（隐藏自持）+ 继承双保险 | worker 子树继承 |
| model 探针 | mw_common.py:1580 | flag + 继承双保险 | `_probe_spawn_kwargs` platform seam 先例 |
| ue-toolchain run（shell=True） | **mw.py:1142**（`def _toolchain_run` :1090） | 前台 → L0 后兼继承兜底 | serve 侧若未来调用已安全 |
| `_git_short_commit` | **mw.py:4404**（`def` :4402） | 前台 → 兼继承兜底 | |
| `_install_framework` | **mw.py:4966**（`def` :4942） | 前台 → 兼继承兜底 | |
| `_build_bundle`/node esbuild + `_rebuild_pi_dist` | **mw.py:4752**（`def _build_bundle` :4725）/ **4777**（`def _rebuild_pi_dist` :4764） | 前台 → 兼继承兜底 | |
| `_run_stream`/`_run_capture` | **mw.py:5152/5181**（`def` :5148/5178） | 前台 → 兼继承兜底 | `_run_stream` 刻意继承 stdio 流式输出，不加 flag（有据，非遗漏） |
| `port_owner_pids`（netstat） | mw_common.py:2313 | 前台 → 兼继承兜底 | doctor 路径 |
| autopilot advance/xkey/conductor 子调用 | advance.py:92,181、**conductor.py:2920**（`_set_index_phase`）、xkey.py:1301 | 继承（conductor 隐藏控制台） | 二层 |
| run-detached 监督进程 | **console_run.py:110**（监督进程 spawn；win32 CREATE_NO_WINDOW\|CREATE_NEW_PROCESS_GROUP / posix start_new_session） | flag（隐藏自持） | 用户命令 flags=0 继承之（console_run.py:243） |
| guard 覆盖面 | **mw_console_guard/（新）**：`mw_console_guard.py:30` EXPLICIT 掩码、`:62` env+平台判据 | flag（运行时 OR 注入） | 仅 `MW_CONSOLE_GUARD=1` 子树，且仅 win32（posix no-op） |

**终稿复核结论：一致（位置已更正，归属未变）。** 唯一需要更正的类别是行号下移（W-01 在 mw.py 的 cmd_start 区加了 L0 注释/重定向、在 `_parse_args`/`__main__` 加了 run-detached 挂接），归属判据本身逐行核对无出入：serve 树全站点处于 cmd_start 隐藏控制台之下（继承兜底），前台站点保持前台，`_run_stream` 的"刻意不加 flag"仍成立，run-detached/guard 两个新站点与 design D-002/D-003 一致。

结论：L0 后全树无"无控制台祖先 + 裸 spawn"组合；唯一刻意不设 flag 的 `_run_stream` 有流式输出理由且已处于继承兜底之下。守卫测试断言本表存在且 `DETACHED_PROCESS` 全仓非测试代码 0 命中（`mw_console_guard/` 子包豁免——其引用是 AC-005 合同性代码，见 `test_console_storm_guard.py` 头注）。
