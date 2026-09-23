# Task T-03-LIVE-REGRESSION: live 进程树测试 + 全量回归 + dist 重建

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: 本窗口 PM 自执
- ac_refs: [AC-006, AC-001~005（回归）]
- vc_refs: [VC-006]
- pattern_refs: [mw-stale-builtin-fix 教训：TS 改动必须重建 dist 才对 worker 生效]

## 描述

1. 新建 `packages/coding-agent/test/extensions/agent-team-loop-worker-tree-kill-live.test.ts`（**不 vi.mock**，真实进程）：
   - 用 node child_process spawn 一棵真实挂起树：父进程（如 powershell/python sleeper）自身再 spawn 孙进程并把孙 pid 写入临时文件；`trackDetachedChildPid(父pid)`
   - 以短 PI_WORKER_IDLE_MS 激活 workerModeActivate（fake pi）→ fake timers 推进触发 idle watchdog（真实 killTrackedDetachedChildren → 真实 taskkill /T 或 kill(-pid)）
   - 轮询探活（process.kill(pid, 0)）≤60s：父与孙均消失 → [VERIFY] VC-006: orphan_count=0
   - 平台分支：win32 用 cmd/powershell 树，POSIX 用 sh sleep 树；探活失败即达标
2. 回归：`./test.sh`（repo 根，非 e2e）+ `npm run check` 全绿，new-failures=0（对照 Windows 基线 89 环境失败）
3. dist bundle 重建（按 mw 框架既有构建入口），确认 worker-mode 变更进入 bundle；记录重建命令与产物时间戳
4. 提示用户 `/mw restart`（serve PID 4448 stale code，重启后修复对后续 worker 生效）

## 验收
- live 用例 PASS（orphan_count=0）+ test.sh/check 全绿 + dist 重建记录，证据留 evidence/runs/
