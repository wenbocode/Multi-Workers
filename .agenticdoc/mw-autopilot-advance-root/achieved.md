# Achieved: mw-autopilot-advance-root

> Key: mw-autopilot-advance-root
> 完成：2026-09-22

## 系统行为变化

- **autopilot phase-advance 通道恢复可用**：framework 装在项目之外（`.agentic-framework` 的 `repo=` 指向别的 AgenticTask 仓库）时，phase 转换按「cwd = 目标项目」解析 `.agenticdoc`，而不是按脚本自身位置命中 framework 仓库自己的 `.agenticdoc`。conductor 的每个 advance tick 从「永久 exit=1 + 在 framework 仓库 mkdir 空 key 目录」恢复为在目标项目正常推进并更新 `pm-state.md` / `_index.parallel`。
- **错误根不再静默**：mw `autopilot/advance.py::locate_platform_dir()` 逐个候选执行 `detect_root.py --json`，只采纳 `PROJECT_ROOT` 与目标项目一致的候选；全部不一致时抛 `AdvanceError`（列出每个候选的实测根），advance 返回 exit 1 + 可读诊断，绝不写到别的项目。
- **中文门禁诊断可读**：mw 的 detect_root 探测与 advance 调用、pi 扩展 `runAgenticScript` 的子进程均加 `-X utf8`，cp936 stdio 不再被按 UTF-8 解码成 `?`。
- **影响面**：`packages/multi-workers/autopilot/advance.py`（+CHANGELOG）、`packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts`（+CHANGELOG）、AgenticTask framework（`scripts/{advance_phase,detect_root,update_index,migrate_patterns,verify_project_memory}.py` + 镜像 + 测试，跨仓 commit d7004d0）。不改 pi 核心，不改 autopilot 调度语义与门禁业务规则。

## 关键决策

- D-101/D-102：root 定位语义 = cwd 向上专扫 `.agenticdoc` 优先，脚本位置回退；`detect_root.py` 在 CLI 出口应用 cwd 优先（library 函数语义不变，避免破坏 platform-anchored 单测）。
- D-103：mw 用 detect_root 的 `PROJECT_ROOT` 做候选一致性判定（fail-loud），而非重排候选顺序。
- D-104：`-X utf8` 而非 `PYTHONUTF8=1`（只约束子进程，不改变其内部行为面）。
- D-105：否证「项目内副本优先」——实测 E2Feature 项目内副本 a06b4a2 落后 marker clone e9360db，重排会跑旧框架。

## 触达面

- 新增测试 8 例（framework 4 + mw 4，含 e2e）；`npm run check` exit 0；mw pytest 726 passed / 9 deselected；vitest 168 passed。
- 同步：E2Feature marker commit=d7004d0、`.agents` clone + `.claude/scripts` 同 hash；mw 本仓 `.claude`/marker 同步；`diff-installed.py` clean。
- 清理修复前副作用：`H:\git\Multi-Workers\.agenticdoc\{feature-params-service,feature-viewer-mvp}`（空目录）。

## 遗留

- pi 扩展 `dist` bundle 未重建（AGENTS.md 禁未请求的 build）：`agent-scripts.ts` 的 `-X utf8` 待下次正常 bundle 构建/发布后对既有窗口生效。去向：随 mw 下一次 build/release 自然落地（不单独立 key）。
- 其它项目（JCodingAss / LearningTree 等）的项目内 framework 副本未同步到 d7004d0。去向：各自下次 `install.py` / `mw update-env --apply` 同步；未同步也不会被 fail-loud 误拒（其项目内副本仍是 platform-anchored 一致候选），不单独立 key。
- framework 仓库自身无 CI 门禁覆盖 `scripts/test_*.py`（靠手动 `python test_*.py`）。去向：接受现状（沿用仓库既有约定），不本 key 处理。
