# T6: 全量回归 + 真机冒烟 + 补登记

- 状态: done（主窗口直做）
- 产物/结果:
  - 全量套件：`python -m pytest -q` → **722 passed, 9 deselected**（708 既有 + 14 新增）。
  - `npm run check` → exit 0（本 key 无 TS 改动，合规跑全量检查）。
  - 真机冒烟（fabricated dual 项目 + `python -c` 模拟命令）：targets 列出 `ProjEditor (editor)`；run 渲染含 `--args=-MaxParallelActions=16` 转发、run dir `20260921-204041-build_editor`、`exit=0 error_lines=0 watched_drift=0/1 — OK`；hash 输出 EOL 归一化摘要。冒烟临时脚本/日志用后即删（AGENTS.md 纪律），结论记录于 evidence/runs。
  - 补登记本 key（spec/design/plan/tasks/evidence/achieved + phase 推进）。
- 佐证: evidence/runs/validation-2026-09-21.md；evidence/quality-gate-report-2026-09-21.md。
