# Evidence Run: 003-mw-target-cli-doctor

- Date: 2026-09-11T17:50:00+08:00
- Task: 003-mw-target-cli-doctor（S1）
- Deliverables:
  - `packages/multi-workers/mw.py`: `target set/clear/show` 子命令（行级引导字段更新，保全手写节注释；模板写入；fail-closed 路径校验）+ argparse/dispatch 接线 + `import re`
  - `packages/multi-workers/mw_common.py`: `toolchain_probe_path` / `probe_target_toolchain` / `_doctor_target`（探测缓存 `.mw/toolchain.json`，target.yml mtime 新于 probed_at 才重探）+ doctor_report/format_doctor_text/_doctor_issues 集成（config 错误与探测失败进 issues）
  - `packages/multi-workers/test_mw_target.py`: 12 用例

## 测试命令与结果

```
cd packages/multi-workers
python -m pytest test_mw_target.py -v
  12 passed

python -m pytest -q          # 全量回归
  391 passed, 8 deselected（379 基线 + 12 新增，零回归）
```

## [VERIFY] 行（VC-010）

```
[VERIFY] VC-010: dual-root=game
[VERIFY] VC-010: single-root=control
[VERIFY] VC-010: write-scope=target-yml-only dist-mtime-unchanged=true
```

- 写面断言：set 前后全树快照 diff = 仅 `.agenticdoc/target.yml` 新增；clear 后 diff = 仅该文件删除
- dist 快照：`packages/coding-agent/dist` 全树 mtime_ns/size 前后不变（模式切换零重建）

## CLI e2e 冒烟

```
python mw.py target set --project <tmp> --game <tmp>/game --vcs p4  → mode dual, game root 正确
python mw.py target show --project <tmp>                            → 同上
python mw.py target clear --project <tmp>                           → removed ..., single
```

## 关键实现点

- 已存在 target.yml → `_apply_bootstrap_line` 行级替换顶层标量键（保留注释/节体/行尾；缺失键插在头部注释块后），不走 YAML round-trip——手写三节零破坏
- `target set` 校验：game/engine 必须 is_dir、uproject 必须存在（fail-closed，防拼写错路径直接入库）
- doctor 探测缓存：`probed_at_epoch >= target.yml mtime` 判新鲜；二次 doctor 不重写缓存（测试断言 mtime_ns 不变）；yml 重写后强制重探
- single 缺省（无 target.yml）：target 节无 checks、无 issue——存量项目 doctor 行为零变化

## 实现偏差记录

- 测试初版两处缺陷被自纠：`_set_args` Namespace 缺 engine/vcs/uproject 属性（AttributeError）；healthy 断言未排除无关的 "service not running" issue
- 断言前缀陷阱：旧 game 路径是新路径前缀（game/game2），改为带引号边界的整行匹配
