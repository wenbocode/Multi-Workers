# Mini-Spec: mw-rg-download-403-fallback

- Date: 2026-09-16
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop（无扩展改动；本次为 pi core utils 修复）
- 来源：用户报告——新机器部署最新代码后开 pi 报
  `Failed to download ripgrep: GitHub API error: 403`。

## Problem

新机器（及本机）无凭据访问 `api.github.com` 直接 403（未认证 60 次/小时/IP，
CN 网络常态）。pi 启动时 `ensureTool("rg"/"fd")` 走
`tools-manager.getLatestVersion()`（API `releases/latest`）→ 403 → 下载放弃，
grep/find 工具不可用。本机此前能用是因为 `~/.pi/agent/bin/rg.exe` 早已下载，
根本不触发 API。

验证（本机，node fetch = pi 同路径）：

- `api.github.com/repos/BurntSushi/ripgrep/releases/latest` → 403
- 直链 `github.com/BurntSushi/ripgrep/releases/download/14.1.0/...zip`
  → 200（重定向 release-assets.githubusercontent.com）

## Change

`packages/coding-agent/src/utils/tools-manager.ts`：

1. `PINNED_VERSIONS`（rg 14.1.0、fd 10.2.0）：`getLatestVersion` 抛错时退回
   固定版本，直链下载不经过 API；无 pin 的工具维持原样重抛。
2. `getLatestVersion` 携带 `GITHUB_TOKEN`（存在时）的 Bearer 头。
3. `downloadTool(tool, silent)` 透传 silent，fallback 时打 dim 日志
   （`GitHub API unavailable (…); using pinned ripgrep 14.1.0`）。

## Files

- packages/coding-agent/src/utils/tools-manager.ts
- packages/coding-agent/CHANGELOG.md（[Unreleased] → Fixed）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 403 网络下 rg 可完整下载并可用 | 沙箱 e2e |
| AC-002 | 403 网络下 fd 可完整下载并可用 | 沙箱 e2e |
| AC-003 | `npm run check` 全绿 | exit 0 |
| AC-004 | API 可用时行为不变（仍取 latest） | 代码路径 + check |

## Result

- AC-001：沙箱（`PI_CODING_AGENT_DIR=<tmp>`、PATH 剥离 `~/.pi/agent/bin`）
  跑 dist 的 `ensureTool("rg")`：`GitHub API unavailable (GitHub API error:
  403); using pinned ripgrep 14.1.0` → 下载 5.3MB → `rg --version` =
  `ripgrep 14.1.0 (rev e50df40a19)`。
- AC-002：同沙箱 `ensureTool("fd")`：pinned fd 10.2.0 → `fd --version` =
  `fd 10.2.0`。
- AC-003：`npm run check` exit 0。
- AC-004：API 成功路径逻辑未变（try 分支原样）；仅失败时新增 fallback。
- 部署：`mw build --install` 已重建 dist + 重装全局 bundle；本机验证用的
  即为新 dist。
- 状态：完成。
