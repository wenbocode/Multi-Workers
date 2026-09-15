# Task 005: worker 双根执行（launcher cwd=game + 控制根写路径 + 双根 read-scope 用例）

- Stage: S2
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，Py 3/3+全量 394、TS 2/2、check exit=0，证据 evidence/runs/005-worker-dual-root.md）
- ac_refs: [AC-003]
- vc_refs: [VC-004, VC-005, VC-009]
- pattern_refs: []
- deps: [002]
- 预估: ~2h

## 交付物

- `packages/multi-workers/launcher.py`: dual 模式 spawn cwd=game（`load_target_config` 判定模式；list args、无 shell、`PI_WORKER_TASK` 绝对路径全部不变，仅 cwd 值来自配置）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/paths.ts`: `controlRootFromTaskPath()` 显式化（现 worker-mode.ts:229 dirname 推导抽出为函数，行为不变）
- 双根 fixture 用例（agent-team-loop 测试 + `test_launcher.py` 扩展 spawn cwd 断言）

## AC 摘录（spec.md §3）

- AC-003: worker 进程 cwd=Game 根；trace.log/output.md/phase 文件全部写控制根；PI_WORKER_TASK 机制不变、零新增 env

## 实现要点（design.md D-001/D-007）

- launcher.py:522-524 spawn 处: `cwd = game_root if mode == "dual" else project_dir`
- 控制根写路径零改动: worker-mode 从 PI_WORKER_TASK 推导（:229）——本 task 将推导显式化为函数 + 用例锁行为（VC-005 防回归）
- AC-023 语义不变: 无 shell、list args（launcher.py:125/153 既有绝对路径注入照旧）
- 同盘双 fixture 即可（跨盘语义验证归 Task 008）

## 验证方式（VC 断言）

- VC-004: spawn cwd = target.yml game 绝对路径 → `[VERIFY] VC-004: spawn-cwd=<game>`
- VC-005: trace.log/output.md/phase-*.md 写路径前缀=控制根 → `[VERIFY] VC-005: write-prefix=control-root`
- VC-009: read_scope 授权 game+engine 双根时两根 read 放行、根外 block → `[VERIFY] VC-009: game-allow=true engine-allow=true outside-block=true`
- single 模式回归: spawn cwd 与写路径与现状一致
- 证据落盘: `evidence/runs/005-worker-dual-root.md`

## 依赖与阻塞

- 依赖 002（Py 配置层）。与 004 无依赖关系，可并行。
