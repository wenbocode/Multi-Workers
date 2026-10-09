# T-01 Python 侧注册（角色 `vision` / 类型 `vision` / REGISTRY）

- key: mw-vision-role · 波 0 · 独占写面：`packages/multi-workers/mw_common.py`（表段）、`packages/multi-workers/autopilot/dispatch.py`（REGISTRY 段）
- ac_refs: AC-004, AC-019 · vc_refs: VC-004, VC-019
- 依赖: 无 · 预估: 30-45min

## 目标

让 Python 侧认识 `vision` 角色与 `vision` 任务类型，并让 conductor 允许派发该类型。

## 契约（逐字遵守，不得重定义）

- `mw_common.py:138 DISPATCH_ROLES` 追加**末尾**：`("main","coding","review","research","vision")`
- `mw_common.py:139 TASK_TYPE_TO_ROLE` 新增 `"vision": "vision"`（**不重排**既有 13 键）
- `autopilot/dispatch.py:57-71 REGISTRY` 新增 `"vision"` 条目：`tools` = `["read","write","edit","bash","find","grep","ls"]`（与 `coding` 同序）、`conductor_dispatchable = True`、`cli/provider` 口径与 `coding` 条目一致
- 不新增 provider、不改 `providers.json`、不碰 launcher

## 步骤

1. `mw_common.py` 表段追加两处（只加不改）。
2. `dispatch.py` REGISTRY 加 `vision` 条目（追加在字典末尾）。
3. 自检：`python -c "import mw_common; print(mw_common.DISPATCH_ROLES, mw_common.TASK_TYPE_TO_ROLE['vision'])"`
4. 自检：`python -c "from autopilot import dispatch as d; print(d.REGISTRY['vision']['tools'], d.REGISTRY['vision']['conductor_dispatchable'])"`
5. 自检：`python -c "from autopilot.dispatch import dispatch; r=dispatch(task_type='vision', prompt='x', loop='L', attempt=1); print(r.reason if hasattr(r,'reason') else r)"` —— 期望**不**返回 `not-conductor-dispatchable`；`dispatch(task_type='nope', ...)` 仍返回 `unknown-type`。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_autopilot_dispatch.py -q -s      # T-03 重冻前预期：键集断言红（属预期）
python -c "import mw_common as m; assert m.DISPATCH_ROLES[-1]=='vision' and m.TASK_TYPE_TO_ROLE['vision']=='vision'; print('[VERIFY] VC-004: role_for_vision=%s' % m.TASK_TYPE_TO_ROLE['vision'])"
```

## 证据格式

`[VERIFY] VC-004: role_for_vision=vision` / `[VERIFY] VC-019: conductor_dispatchable=True`

## 非空洞对照

临时把 `conductor_dispatchable` 改为 `False` ⇒ VC-019 必须变红（`not-conductor-dispatchable`）；把 `TASK_TYPE_TO_ROLE["vision"]` 改回缺键 ⇒ VC-004 变红。

## 交付

仅源码两处 + 本卡 `[VERIFY]` 原始输出（写入 task output，不新建文件）。

## 卡缺陷更正（2026-09-26 实测，语义不变）

1. VC-019 / 步骤 4 的下标写法 `REGISTRY["vision"]["conductor_dispatchable"]` **必然 TypeError**：`REGISTRY: dict[str, DispatchType]`（`dispatch.py:71`），值是 frozen dataclass（`:54`）。**正确取证 = 属性访问** `REGISTRY["vision"].conductor_dispatchable`。
2. 步骤 5 的 `dispatch(task_type=..., prompt=..., loop=..., attempt=...)` 缺必填位置参数，真实签名为 `dispatch(project_root, owner, stem, task_type, prompt, *, loop, attempt)`。
3. `TASK_TYPE_TO_ROLE` 追加前实际为 **9** 键（非 13），追加后 10 键，`vision` 末位。

以上三点已由 T-01 worker 按代码事实等价取证（`[VERIFY] VC-019: conductor_dispatchable=True`、`dispatch(vision)` 返回 `reason=''`、`nope` 仍 `unknown-type`）。
