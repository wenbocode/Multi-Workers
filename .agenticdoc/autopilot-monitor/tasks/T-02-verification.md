# Task: T-02 L0 静态扫描 + changelog + 构建部署 + L2 双 widget 验证

> key: autopilot-monitor | type: research | deps: T-01
> 必读前置：`.agenticdoc/autopilot-monitor/spec.md`、`design.md` §7 VC-009/VC-010、`evidence-requirement.md`、T-01 的 progress.md

## 目标

为 T-01 产出的 monitor 代码补齐 L0/L2 证据、changelog、构建部署，把 `[VERIFY]` 证据落盘到 evidence/runs/。

## 交付物

### 1. L0 静态扫描（VC-009）

在 `packages/coding-agent` 下用 rg 证明并记录输出：

```
rg -n "writeFile|appendFile|writeSync|rmSync|mkdirSync|renameSync|openSync" src/extensions/agent-team-loop/autopilot/monitor.ts
rg -n "writeFile|appendFile|writeSync|rmSync" src/extensions/agent-team-loop/autopilot/console.ts   # monitor case 路径人工确认无写
rg -n "config.json" src/extensions/agent-team-loop/autopilot/monitor.ts src/extensions/agent-team-loop/autopilot/console.ts
```

期望：monitor.ts 零匹配；console.ts 匹配处均在既有 enable/disable 写路径（非 monitor case）。结论写入证据文件。

### 2. CHANGELOG（coding-agent）

`packages/coding-agent/CHANGELOG.md` 的 `## [Unreleased]` → `### Added`（若无该节则新建，保持节序 Breaking/Added/Changed/Fixed/Removed）追加：

```
- Added `/autopilot monitor [on|off]`: a live bottom panel for the orchestration stack — mw serve (PID, fresh/stale, uptime), conductor (alive, enabled/paused), running workers across all keys with elapsed minutes, and pending gates with the approve/reject hint. Read-only file sources (pid/meta/config/workers/gates), 4s refresh, per-window in-memory toggle; headless sessions degrade to a notice.
```

### 3. 构建部署

`python mw.py build --install`（packages/multi-workers 下）成功，记录最后三行输出。

### 4. L2 双 widget 验证（VC-010）

优先方案（harness 级）：在 `test/suite/autopilot-monitor.test.ts` 追加一条测试——fake pi 上同时驱动 watch widget 渲染（或直接对 watch 的 widget id 再 setWidget 一帧）与 monitor 首帧，断言两次 setWidget 的 id 不同且互不覆盖（`agent-team-loop-monitor` vs `agent-team-loop-watch`）。

若 watch widget 驱动在测试中不可行（需要 pmActivate 全链）：退化为 RPC/实窗手动验证步骤文档（写清命令序列：打开窗口 → /pm-key watch 某 key → /autopilot monitor → 预期两块面板并存），标注 `pending manual`，交 PM/用户执行。

### 5. 证据落盘

写 `.agenticdoc/autopilot-monitor/evidence/runs/t02-verification.md`：

```markdown
# T-02 Verification Run (2026-09-11)

## L0
[VERIFY] VC-009: write_api_calls=0, persist_writes=0
（附 rg 实际输出）

## L2
[VERIFY] VC-010: distinct_widget_ids=2
（附测试名/输出，或 pending manual + 步骤）

## Build
mw build --install 最后三行输出
```

## 硬约束

- rg 输出原样贴证据（不许转述）；测试若追加，跑绿后再写证据
- 不 commit；不改 src/ 源码（发现代码问题 → 写进 progress.md 报 PM，不自行改）
- 中文内容文件禁 PowerShell 字符串替换（用 edit/write 工具或临时 python 脚本）

## 完成判据（progress.md 记录）

1. VC-009 证据（rg 输出）
2. CHANGELOG diff 摘要
3. build --install 成功输出
4. VC-010 证据或 pending manual 步骤文档
