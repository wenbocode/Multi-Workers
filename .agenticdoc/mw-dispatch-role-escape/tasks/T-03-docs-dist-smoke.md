# T-03 文档 + dist 重建 + 冒烟

- 依赖: T-01、T-02
- 覆盖: AC-011、AC-010（`npm run check`）；VC-012
- 设计: §6 影响面

## 步骤

1. 文档：
   - `packages/coding-agent/CHANGELOG.md` `[Unreleased] ### Added/Changed`：`dispatch_worker`/`/worker`
     的 `type`、`model_reason` 语义，等值不写 `model:` 行，派发期模型 id 校验（含 fail-closed 例外）；
   - `packages/multi-workers/CHANGELOG.md`、`README.md`：launcher `model-override` 观测行 +
     「dispatch.yml role 值必须可被 pi 模型表解析，否则派发被拒」的说明。
2. `npm run check`（全量输出，0 error / 0 warning / 0 info）。
3. dist 重建：`mw build --install`（或 `python packages/multi-workers/mw.py build --install --project .`），
   确认 agent-team-loop bundle 含新逻辑。
4. tmux 冒烟：`./pi-test.sh` 起窗口，验证 `/worker pi --type review --key _scratch smoke-x <desc>`
   生成 `type: review` 的 task.md 且 notify 回显 role；再用一个非法模型值验证被拒（不落盘）。
   清理冒烟产物（task 目录 + `_workers.parallel` 行）。
5. 证据归档：`evidence/runs/run-2026-09-20.md`（命令 + 输出 + 判定）。
