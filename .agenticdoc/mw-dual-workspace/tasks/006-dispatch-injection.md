# Task 006: dispatch.py 注入（read_scope 展开 + deny_globs 注入 + 控制根授权）

- Stage: S3
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，dispatch 17/17 + 全量 401 + check exit=0；空 scope 控制根附加 bug 被首跑抓出后修正，证据 evidence/runs/006-dispatch-injection.md）
- ac_refs: [AC-004, AC-006, AC-007]
- vc_refs: [VC-013, VC-009]
- pattern_refs: []
- deps: [002, 004]
- 预估: ~1.5h

## 交付物

- `packages/multi-workers/autopilot/dispatch.py`:
  - 相对 read_scope 条目按 game 根展开为绝对路径（dual 模式；single 模式行为不变）；展开失败（dual 但 game 未配置）显式报错退出，不静默
  - task.md frontmatter 注入 `deny_globs:`：默认取 target.yml `ignore.deny_globs`；任务级已显式写则不覆盖
  - read_scope 自动附加控制根（授权 worker 读 target.yml profile 全文）
- `packages/multi-workers/test_autopilot_dispatch.py` 扩展

## AC 摘录（spec.md §3）

- AC-007: dispatch 时 profile（toolchain/ignore/contract 三配置节）注入 task.md；deny globs 经 ignore 节进 frontmatter，worker 只读 task.md 即自包含
- AC-006（生成侧）: deny_globs 缺省来自 ignore 节

## 实现要点（design.md D-005/D-007）

- 展开规则: 条目非绝对路径 → `game_root + 条目`（realpath 归一后写入）；控制根附加为绝对条目（去重）
- deny_globs 与 Task 004 的消费格式严格对齐（frontmatter `deny_globs:` YAML 列表）
- 双侧 Y 一致性: TS task-dispatcher（Task 007）与 Py dispatch 对同一 target.yml 的注入要点一致（parity 精神，不强制逐字节）

## 验证方式（VC 断言）

- VC-013 生成侧: 渲染后 task.md 含 deny_globs 行 + 控制根 scope 条目
- VC-009 生成侧: dispatch 产出的 read_scope 含 game+engine 双根绝对路径
- 回归保护: single 模式（无 target.yml）下 dispatch 产出与现状一致（快照断言）
- 证据落盘: `evidence/runs/006-dispatch-injection.md`

## 依赖与阻塞

- 依赖 002（Py 配置层）、004（deny_globs 消费格式）。
