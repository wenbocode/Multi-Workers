# Task T-01-WORKER-EXIT-KILL: worker-mode.ts 退出路径树杀

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: 本窗口 PM 自执（pm-mind：无 Task tool 时 PM 可自执简单 task）
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005]（实现基础，验证在 T-02/T-03）
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005]
- pattern_refs: []

## 描述

`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`：

1. 顶层新增值导入：`import { killTrackedDetachedChildren } from "../../../utils/shell.ts";`（与 bash 工具同模块实例，读 tracked pid Set 的唯一途径）。
2. 四个 `process.exit(1)` 位点在 exit 前一行调用 `killTrackedDetachedChildren()`：
   - existsCheck（taskPath 不存在，~:413，此时 Set 必空，为机械不变量而设）
   - dispatchRefusal 启动拒绝（~:439，同上）
   - `timeoutExit()`（idle/wall 共用，~:670，主修复点；调用必须在 appendTimeout/writeOutputGuarded/recordEnd 同步写盘之后）
   - agent_settled catch（~:870）
3. `process.on("exit")` 安全网 hook（~:475）在 output 补写**之前**调用 `killTrackedDetachedChildren()`（硬崩溃兜底）。

## 验收
- `npm run check` 全绿（无错误/警告/信息）
- 机械不变量：文件内每个 `process.exit(` 调用向上 2 行内存在 `killTrackedDetachedChildren()`（grep 证据留 evidence/runs/）
- 不改动 watchdog 判定语义、trace/output 格式、退出码
