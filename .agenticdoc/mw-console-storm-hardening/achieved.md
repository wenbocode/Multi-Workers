# achieved.md — mw-console-storm-hardening

- key: `mw-console-storm-hardening`（2026-10-15 开窗，当窗关闭）
- 输入：Windows 控制台窗口风暴事故 `H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md` §8-B（实验期 EnumWindows 弹窗风暴：单命令引爆 ~10 个可见终端窗）
- 本 key 目标：四层结构性修复——L0 spawn 除雷 / L1 标准 detached-runner / L2 子树 console guard / L3 文档+守卫测试，外加 TS 扩展侧暴露入口
- AC 覆盖：AC-001..010 全部 PASS（verify 文档 `evidence/runs/verify-mw-console-storm-hardening-20261015.md`，[VERIFY] VC-001..VC-010 逐条含原始行）；QG 审读 **PASS**（blockers=0 majors=0 minors=4 notes=5，`evidence/review/qg-console-storm-20261015.md`），4 minor 已由 W-06 快修波次 + PM 直执全部关闭

## 系统行为变化

**L0（packages/multi-workers/mw.py cmd_start）**
- `mw start` 起 serve 改用 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`（DETACHED_PROCESS 移除）：隐藏控制台被全部后代结构性继承（机制 M1），不再依赖每个 spawn 站点记得打 flag
- serve stdout/stderr 重定向 `.mw/serve-console.log`（finally 显式关闭句柄）
- 守卫：全仓非测试 .py 剥注释/docstring 后 `DETACHED_PROCESS` 命中 = 0（test_console_storm_guard.py 防回潮 grep）

**L1（console_run.py + `mw run-detached`）**
- 后台取证命令唯一入口：隐藏控制台监督进程，stdout 恰 4 行 handoff（pid/marker/heartbeat/log）
- 原子 heartbeat.json + marker.json（schema `mw-run/1`：rc/timed_out/wall_sec；timeout rc=124 + taskkill /T 树杀；spawn 失败 rc=127）
- run-dir `-N` 后缀 O_CREAT|O_EXCL 竞态安全创建；`--heartbeat-s`/`--timeout-min` 正数校验（小数合法）

**L2（mw_console_guard/）**
- sitecustomize 注入（`MW_CONSOLE_GUARD=1` + PYTHONPATH）：对 `creationflags=0` 的 subprocess.Popen/run OR 进 CREATE_NO_WINDOW；显式 CREATE_NEW_CONSOLE/DETACHED_PROCESS 原样不动；env 未设零行为差异；posix no-op；patch 失败 fail-open（单行告警后放行）；幂等

**TS 侧（packages/coding-agent, agent-team-loop）**
- `shared/run-detached.ts`：`runDetachedMw()`（spawn python mw.py run-detached，解析 4 行 handoff → `{pid, marker, heartbeat, log}`，fail-open 结构化错误）+ 正数时长运行时校验
- `mw_run_detached` 工具：typebox schema additionalProperties:false，双激活路径注册（pm-orchestrator + worker-mode，registerRagTools 先例），worker 仅 shell 角色可见（activeToolsForType，不进 TOOL_ALLOWLISTS——T-17 parity 锁未动）
- `/mw run-detached [--cwd] [--run-dir] [--timeout-min] [--heartbeat-s] -- <cmd...>` 手动入口，与工具共用 runner

**文档**：multi-workers README「Windows detached-run checklist」（三事实 + GetConsoleProcessList 判据 + 用法 + guard 一句话）、UPDATE.md 指令矩阵行、双包 CHANGELOG [Unreleased]/Added

## 验收数字

- Python：守卫测试 **17 passed**（test_console_storm_guard 6 + test_mw_console_guard 11）；包全套 2254 passed / 8 failed（逐条归因既有/环境红列，零新增）
- TS：新套件 **13 passed**（双路径注册/shell-only 门控/schema 拒绝/精确 argv 透传/命令分支）；tsgo 0 错；biome 干净
- 冒烟：run-detached marker `rc=0 schema=mw-run/1`；AC-001E EnumWindows 实测：`mw start` 后 75s / 297 轮询，**终端属主新可见窗 = 0**（对照事故复现组 10/10 弹窗）
- 审计表终稿逐行复核一致（10 处行号随 W-01 落地更正）

## 提交（4 个）

- `13a0ce4de` feat(multi-workers): console storm hardening（L0+L1+L2+守卫测试，1216 insertions）
- `4980da301` feat(coding-agent): mw_run_detached tool + /mw run-detached command（786 insertions）
- `3c02d7227` docs: README checklist + UPDATE 矩阵行 + 双 CHANGELOG
- `bf2547cce` feat(multi-workers): rebuild agent-team-loop bundle（**HEAD 隔离 worktree 构建**，防并行 WIP 入库；self-check OK v0.83.0）
- 混合文件（pm-orchestrator/worker-mode/mw.py 与并行 key 同文件改动）走索引级重建提交，他窗未提交工作原样保留

## 遗留与移交

- 运行时 bundle 已由并行窗口 build（用户确认 2026-10-15）；tracked pi dist（packages/coding-agent/dist，1001 文件）待并行 key 提交后统一重建
- F4（dispatch 卡 write_face 渲染缺陷：单 bullet 多路径只取首段）移交框架侧；规避规则已入 `_pitfalls.md`
- posix 长跑与 serve-console.log 轮转行为未实测（win32 本机；posix 由 seam 单测覆盖）
- FeatureMigrator 项目侧修复（事故 §8-A）已移交
- 工作树 bundle 的未提交改动归并行会话（其自行 build），本 key 不追
