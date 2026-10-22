# KDR: mw-console-storm-hardening

## R（需求）

- 技术栈: Python（packages/multi-workers：mw.py + 新 runner/guard 模块 + pytest）；TypeScript（agent-team-loop 扩展仅入口暴露层）
- 边界: 不做 FeatureMigrator 项目侧修复（移交）、不改终端委托注册表、不散改测试文件、不动 launcher/serve 已正确的 flag 用法、不改 pi 核心
- 关键约束: win32 硬禁止 DETACHED_PROCESS；guard 仅 env 激活、零全局副作用、不改写显式 console flag；GC-2（扩展 API）/GC-3（进程树隔离）/GC-4（无新调度组件）
- 输入: `H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md` §8-B（框架层修复建议）+ 本 session 框架 spawn 面普查（见 evidence/research/ 两份 note）
- 用户决策（2026-10-15 确认）:
  1. key 开在当前工作目录（H:\git\Multi-Workers），事故文件以路径引用
  2. L2 注入机制选 sitecustomize（PYTHONPATH），非 conftest 注入
  3. `mw run-detached` 需要 TS 扩展侧暴露给 worker/PM

## A（架构）← system-design 追加

- 四层交付：L0 cmd_start 除雷（去 DETACHED + serve-console.log 重定向）；L1 console_run.py 两层结构（CLI 立即返回 + 隐藏控制台监督进程写 heartbeat/marker，run_dir 沿用 ue-toolchain 惯例）；L2 mw_console_guard/ 包（sitecustomize 激活 + 58 行 RQ-3 骨架为实现基线，env 开关 + fail-open）；L3 守卫测试（DETACHED=0 grep + flags 断言 + guard 单测）+ README checklist；TS 双激活路径 mw_run_detached 工具 + /mw run-detached 子命令共用 runDetachedMw()（仅 shell 角色，不进 TOOL_ALLOWLISTS）
- 关键实证：M1 隐藏控制台继承成立（判据=GetConsoleProcessList 非 GetConsoleWindow）；M4 sitecustomize 在 pytest 链加载；M7 off/on 端到端 4 窗/0 窗
- 详见 design.md §1/§2 + evidence/research/ 三份 design note + design-spawn-site-audit-20261015.md

## I（实施）← PM 执行中追加

## J. 质量门与快修波次追加（2026-10-15）

- QG 审读（review worker，glm-5.3）判 PASS：blockers=0 majors=0 minors=4 notes=5（evidence/review/qg-console-storm-20261015.md）。
- 裁定：F1（run_dir TOCTOU）/F2a/F2b（正数下界双侧）/F3（VC-008 恒真断言）+ N2/N4 本 key 快修（W-06，17+13 全绿复跑）；N1/N2 的 QG 命中点在 mw.py（本 key 写面）PM 直执修复并复验 17 passed；F4（渲染缺陷）不在本 key 修复面，移交框架。
- bundle 构建裁定：tracked artifact（dist/extensions/agent-team-loop.js）从 HEAD 隔离 worktree 构建（bf2547cce），避免并行 WIP 入库；提交后工作树 bundle 被并行会话以其自身构建覆盖（mtime 保留 20:42）——归并行会话，不互踩，运行时由并行窗口 build 收敛（用户确认）。
