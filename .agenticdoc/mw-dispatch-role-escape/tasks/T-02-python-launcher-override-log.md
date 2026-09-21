# T-02 Python launcher 观测行 + role map parity

- 依赖: T-01（`model-reason:` 键名与 `model-override` 文案口径）
- 覆盖: AC-009；VC-009、VC-011
- 设计: D-008

## 改动文件

1. `packages/multi-workers/launcher.py`
   - `_resolve_entry_model` 返回值扩展（携带 role 名与配置值），或等价的最小改动；
   - `_spawn` 在既有 `[launcher] <key>: model=... source=...` 行后，追加
     `[launcher] <task_key>: model-override task=<X> config:<role>=<Y>`（仅当 `source == "task"`、
     配置存在该 role 默认值且与 task 值不同）。
2. `packages/multi-workers/test_dispatch_models.py`
   - 新增用例：task.md `model:` 与 dispatch.yml role 默认值不同 → 日志行出现；
     相同 → 不出现；无配置 → 不出现；
   - role map 双侧 parity 断言（TS `DISPATCH_ROLE_BY_TYPE` 镜像字面量 == `TASK_TYPE_TO_ROLE`）。

## 硬约束

- 派发行为零变化：显式 task.md 值仍获胜，`effective`/`cmd` 构造不变（VC-009 断言）。
- 不得改动 `_read_task_md_fields` 的正则语义（`model-reason:` 必须仍不匹配）。
