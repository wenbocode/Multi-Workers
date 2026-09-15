# Evidence Run: 005-worker-dual-root

- Date: 2026-09-11T18:55:00+08:00
- Task: 005-worker-dual-root（S2）
- Deliverables:
  - `packages/multi-workers/launcher.py`: `_worker_cwd()`（dual→game root，single→project_dir；target.yml 不可用时抛错 → _spawn 隔离 handler 记 worker.log + 队列 failed，fail-closed）+ spawn cwd 改为 `_worker_cwd(project_dir)`；list args/无 shell/绝对 PI_WORKER_TASK 全部不变
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/paths.ts`: `controlRootFromTaskPath()` 显式化（5 层形状剥离，供新消费者使用；worker-mode 既有推导零改动，用例锁等价）
  - `packages/multi-workers/test_launcher.py`: `TestDualWorkspaceSpawnCwd` 3 用例
  - `packages/coding-agent/test/suite/dual-root-worker.test.ts`: 双根 fixture 全链用例（新增文件）

## 测试命令与结果

```
# Py（launcher）
python -m pytest test_launcher.py -k DualWorkspace -v
  3 passed（single 回归 cwd=project_dir / dual cwd=game / broken yml 拒绝 spawn）

python -m pytest -q                # 全量
  394 passed, 8 deselected（391 基线 + 3 新增，零回归）

# TS（双根 fixture：chdir(game) 模拟 launcher cwd 保证，同盘双 fixture）
node ../../node_modules/vitest/dist/cli.js --run test/suite/dual-root-worker.test.ts
  Tests 2 passed (2)

npm run check → exit 0
```

## [VERIFY] 行

```
[VERIFY] VC-004: spawn-cwd=C:\...\game   （dual 模式 Popen kwargs.cwd=game 绝对路径）
[VERIFY] VC-005: write-prefix=control-root
[VERIFY] VC-009: game-allow=true engine-allow=true outside-block=true
```

- VC-005 全链断言：cwd=game 下运行 worker——被 block 的读在**控制根** task dir 写 trace.log（rule=scope 行）、退出写 output.md 同目录；game 树无 `.agenticdoc`/trace.log/output.md/`_workers.parallel`/`.mw`；`controlRootFromTaskPath` 与实际写根一致
- VC-009 断言：相对条目 `Content` 锚 cwd=game 放行、engine 绝对条目跨根放行、两根外 `secret.txt` block
- fail-closed 链：broken target.yml → spawn 拒绝（worker.log 含 "target.yml"、队列状态 failed、不产生进程）

## 语义说明

- `_worker_cwd` 每次 spawn 解析一次 target.yml——模式切换（`mw target set/clear`）对**下一次 spawn** 即时生效，无需重启 launcher/serve（与 AC-005 配套）
- 同盘双 fixture 覆盖逻辑语义；跨盘语义（真 F:/E:）由 Task 008 的 env 门控用例承载
