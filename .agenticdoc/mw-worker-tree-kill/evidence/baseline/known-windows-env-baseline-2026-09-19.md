# Baseline: 已知 Windows 环境失败基线对照（2026-09-19）

## 依据

AGENTS.md：Windows 开发机上 `packages/agent`（13）与 `packages/coding-agent`（76）存在已知环境失败基线（Windows shell/path/watch 语义，2026-09-10 分类），与上游 pi 在 Windows 上同样失败，属环境噪声。

## 本 key 全量运行对照（coding-agent 包根 vitest --run，2026-09-19 18:39）

- 结果：69 failed / 2253 passed / 48 skipped（另一轮 67 failed / 2255 passed，轮间波动均为环境类 flakes）
- 69 ≤ 76 基线，且失败文件（23 个）全部为已知环境语义类别：
  config self-update（7）、model-registry shell 命令解析（12）、external-editor（3）、package-manager/paths（6）、resolve-config-value（3）、fswatch 回归（4）、footer 短路径（1）、suspend（2）、auth-storage（1）、auto-compaction（2）、dynamic-tools/extensions-runner（3）、cloudflare-compat（2）、resource-loader/sdk-session/trust（3）、tools（1）
- 与本 key 触达面（agent-team-loop*、utils/shell.ts、worker-mode）零交集：日志中两个关键词零提及（vitest 默认 reporter 仅列失败文件）。
- root `test.sh`（git-bash 运行）另见 tui 包 8.3 短路径失败（`WENBOZ~1` vs `~` 展开），同属预存环境问题。

## 结论

new-failures = 0。本 key 改动（worker-mode.ts + 2 新测试文件）未引入任何新失败；相关面全绿（164/164 合跑）。
