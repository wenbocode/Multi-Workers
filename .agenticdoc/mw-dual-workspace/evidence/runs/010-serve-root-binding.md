# Evidence Run: 010-serve-root-binding

- Date: 2026-09-11T21:50:00+08:00
- Task: 010-serve-root-binding（S4）
- Deliverables:
  - `packages/multi-workers/test_serve_meta.py` 增 `test_serve_paths_anchor_control_root_in_dual_mode`：dual fixture（target.yml 指向外部 game 根）下断言全部 serve 侧路径锚控制根——`mw.pid`/`serve.meta`/`mw.stop`（`.mw/`）、`_workers.parallel`（`.agenticdoc/`）、`workers.lock`（`.mw/`）；`code_dir`=控制侧 mw 源码目录；game 树零文件
  - **零代码改动**（符合预期：serve 路径全部由 `--project` 推导，dual 只移动 worker cwd）——用例锁定不变量防回归

## 测试命令与结果

```
python -m pytest test_serve_meta.py -q -s
  4 passed（3 既有 + 1 新增）

python -m pytest -q                # 全量
  402 passed, 8 deselected（401 基线 + 1 新增，零回归）
```

## [VERIFY] 行

```
[VERIFY] VC-015: serve-meta-prefix=control-mw
```

## 手动冒烟记录（serve 重启）

- 2026-09-11 21:11 用户指示重启：旧 serve PID 90292（14:35 启动，S2 前代码）已终止（确认无在跑 worker 后杀整树）；新 serve **PID 76684** 21:11:53 启动，加载 S1–S3 全部代码
- 重启后实证：`serve.meta` = `{"pid": 76684, ...}`、`mw.pid`=76684、launcher 90148 beat 正常刷新（21:14:03）、conductor/launcher 日志新会话截断
- staleness 机制验证（AC-009 关联）：serve.meta `started_at_ms` 晚于全部 mw 源码 mtime → 重启后 `serveStaleness` 应报 fresh；下次 mw 源码改动后又会提示重启（VC-016 单测已锁该机制）

## 断言细节修正

- 首跑一处失败为测试预期值错误：`mw_common.lock_path` 实际为 `<control>/.mw/workers.lock`（非 `.agenticdoc/` 下）——同样是控制根锚定，修正断言后全绿；实现零改动，符合 task 预期
