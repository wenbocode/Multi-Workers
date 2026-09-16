# Mini-Spec: mw-protected-config-guard

- Date: 2026-09-15
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

2026-09-15 事故：一个运行中的 pi 会话为测试 timi key 环境清掉了 `~/.pi/agent/auth.json`。
auth.json 是所有 pi 窗口共享的活跃凭据存储（AuthStorage 按文件 revision 热重载）——
清掉后每个运行中窗口立即报 `Error: Provider is not configured: timi`，多窗口死机。
此类跨窗口活跃配置文件在 agent 工具层毫无防护：任何会话里的 write/edit/bash 都能
直接改掉它们，运行期间绝不能被会话内工具修改。新 key 而非并入 mw-timi-models-add
（该 key 已完成，属独立交付）。

## Change

Agent 工具层硬拦截（全模式注册，含 PM / Worker / 普通 interactive 窗口）：

- 新模块 `agent-team-loop/shared/protected-config.ts`：纯判定逻辑 + `registerProtectedConfigGuard(pi)`
  - 保护对象：pi agentDir（`PI_CODING_AGENT_DIR` 环境覆盖，镜像 core `getAgentDir()`；
    默认 `~/.pi/agent`）下 `auth.json` / `models.json` / `settings.json` / `oauth.json`
    及 agentDir 目录本身
  - write/edit 工具：path（绝对 / `~` / `$HOME` 形式）解析命中保护集 → block
  - bash 工具：命令文本含保护路径引用（`~` / `$HOME` / `%USERPROFILE%` /
    `$env:USERPROFILE` / env 覆盖 / 绝对路径，归一展开后匹配）且含写类结构
    （rm/del/mv/cp 等动词、PowerShell cmdlet、`sed -i`、`find -delete/-exec`、
    重定向目标为保护路径、`python -c`/`node -e` 内联写）→ block，fail-closed
    （读+写混排等边界宁可误拒，agent 重跑纯读命令即可恢复）
  - 读操作不拦截；worker 模式（`PI_WORKER_TASK`）block 时向任务 trace.log 追加
    `[PROTECTED_CONFIG]` 行（PM watch 实时可见）
- `agent-team-loop/index.ts`：activate() 在双加载防重入 flag 之后、PM/Worker 分支
  之前注册（三模式覆盖；同进程不会重复监听）

Python 侧同规则（框架代码永远不写这些文件，用户在 pi 外自行操作不受影响）：

- `mw_common.py`：`PROTECTED_AGENT_CONFIG_FILES` / `agent_config_dir(env)` /
  `is_protected_agent_config(path, env)` / `assert_not_protected_agent_config(...)`

范围边界：不修改 pi core（`/login` 等用户主动流程不在拦截范围）；`~/.pi/agent/extensions/`
下的扩展 bundle 为 startup 时加载，mid-run 替换不破坏活跃窗口，不在保护集内。

## Files

- packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts（新增）
- packages/coding-agent/src/extensions/agent-team-loop/index.ts
- packages/coding-agent/test/extensions/agent-team-loop-protected-config.test.ts（新增）
- packages/multi-workers/mw_common.py
- packages/multi-workers/test_protected_config.py（新增）
- packages/coding-agent/CHANGELOG.md、packages/multi-workers/CHANGELOG.md

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | write/edit 指向 auth.json（绝对 / `~` / `$HOME` 形式）被 block；其它路径不受影响 | vitest |
| AC-002 | bash 写类命令（rm / Set-Content / `>` / sed -i / find -delete / 内联 python 写）指向保护路径被 block；纯读（cat / rg / 重定向到别处 / 项目内相对路径）放行 | vitest |
| AC-003 | worker 模式 block 时 trace.log 落 `[PROTECTED_CONFIG]` 行 | vitest |
| AC-004 | Python 守卫：protected 路径 raise，非保护路径放行；PI_CODING_AGENT_DIR 覆盖生效 | pytest |
| AC-005 | 扩展 bundle 可构建且 self-check 通过（build-extension.sh） | 构建日志 |
| AC-006 | `npm run check` 全绿 | check 输出 |

## Result

- 实现完成：`shared/protected-config.ts`（纯判定 + register，三模式注册于 index.ts，worker 模式 trace.log 记录）；Python 侧 `mw_common` 四个守卫符号 + `ProtectedConfigError`。
- AC-001/002/003：vitest 11/11 通过（新文件 agent-team-loop-protected-config.test.ts）；extensions 目录回归 193/193（6 文件）。
- AC-004：pytest 8/8 通过（test_protected_config.py）；multi-workers 全量 430 passed, 8 deselected。
- AC-005：`mw._build_bundle()` 构建 + jiti self-check OK（activate）。
- AC-006：`npm run check` exit 0，无 error/warning/info。
- CHANGELOG（coding-agent + multi-workers）已记；坑点台账 P-002 已记。
- 生效条件（未执行，待用户）：`mw setup --build`（含 dist 重建）+ 重启 pi 窗口；serve 无需变更即可（新代码不进 serve 路径），但建议 /mw restart 清 stale。
- 状态：完成。
