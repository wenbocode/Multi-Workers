type: coding
key: mw-dynamic-concurrency
batch: B3
card: T-C-M05-tests-python
phase: execute
goal: .agenticdoc/goal.md

# T-C-M05 · MDC 测试（Python 半边：VC-101/102/103/104）

## 上下文

- 目标（本 key）：把 autopilot 并发从"静态上限 2 的 key 层"改成**依赖前沿驱动、按前沿动态最大化**（key 层上界 + per-key 上界），且**写面判定先行**（D-018，前置 key `mw-write-face-guard` 已 DONE）。
- 本卡是 MDC 的 **B3（Python 半边）**：只加**测试**，不改任何生产代码。TS 半边由并行卡片 `T-C-M05-tests-ts.md` 负责（VC-107/108），两边文件集互不相交。
- 已落地的生产行为（**你只做验证，不改它**）：
  - key 层上界：`packages/multi-workers/autopilot/conductor.py:752` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"]))`；在飞集合 `:706-712`（`_is_in_flight ∧ _row_belongs_to`）。
  - per-key 上界（M-02，已落地）：`conductor.py:1989` `cap = max(1, int(cfg.get("max_workers_per_key", 4)))`，实起 = `min(cap, |任务前沿|)`；前沿由 `autopilot/task_graph.py`（M-01）从卡头 `deps:` 计算；V-problem ⇒ 整 key 串行回退 + 去重审计行；写面拒绝 ⇒ 等待下一 tick（**不 stall**）。
  - 配置值（M-03，已落地）：`autopilot/config.py:91` `"max_parallel_keys": 8`、`:92` `"max_workers_per_key": 4`、`:127-128` 范围均 `(1, None)`。
- **重要：`dispatch.py` 此刻正被并行卡片 `mdc-m04-dispatch-dedup` 修改**（加 identity 级去重 + `conductor.py` 一行等待集合）。因此：
  - **不得**断言"同一 `task_key` 可被重复派发"的旧行为；
  - **不得**断言 `duplicate-dispatch` 拒绝（那是 M-06/VC-106 的判据）；
  - 若你的测试因该并行改动而红，**记录到证据并报告**，不要改生产代码去迁就。
- 度量参照：`_scratch/evidence/mdc-m02-probe-a-inplace-out-20261014.txt`（PM 亲跑 M-02 探针的原始输出，含前沿恒等/V-problem/AC-006 全节）。

## 要求

新增**一个**测试文件，把下列四条 VC 各写成**具名测试**（不要合成一个大 test，红的时候要能一眼看出是哪条 VC）：

1. **VC-101 前沿恒等**：≥3 组构造语料（key 层 roadmap + key 内任务图），逐 tick 复算 `实起 = min(层上界, |前沿|)`。必须驱动**真实** `conductor.tick`/`execute_loop`，并从**真实队列文件** `.agenticdoc/<key>/workers/_workers.parallel`（`mw_common.parse_workers_file`）数实测派发行数——**不得**在测试里自己重算一遍前沿公式当"期望值"（那就成了自证）。
2. **VC-102 窄前沿不放大**：前沿恒为 1（链任务 `T-2 deps T-1`）时，即便上界为 4/8，实起 = 1。
3. **VC-103 上界=1 即串行、且**无需重启**：同一进程内先以上界 8/4 跑一 tick（实起 >1），再改写 config 为 `max_parallel_keys=1` + `max_workers_per_key=1` 再跑一 tick（两层实起 ≤1），证明配置每 tick 热读。
4. **VC-104 fail-closed**：以下任一种情况 ⇒ 该层实起 = 1，**且**有审计行（timeline 事件），**不得**默认放大：
   - 任务依赖不可解析 / 悬空 `deps:`（例：`T-2` 依赖不存在的 `T-99`）；
   - 依赖成环；
   - 卡头写面未声明（WFG D-003 = serial-only）；
   - 写面互相重叠（第二条必须被拒且**不 mark_stalled**）。

约束：测试必须用**显式文件参数**运行（P-032）；不得 `pytest.mark.skip`/`xfail`/`only` 规避；不得放宽既有断言；不得写任何生产文件。

## 交付格式

- 新测试文件 `packages/multi-workers/test_mdc_concurrency.py`（唯一代码写面）。
- 唯一证据文件 `.agenticdoc/mw-dynamic-concurrency/evidence/M-05-tests-python.md`，含：
  1. 四条 VC 的**原始 pytest 输出**（`python -m pytest -q test_mdc_concurrency.py` 的 tail + 通过数）；
  2. **全量** `python -m pytest -q` 的原始 tail + 退出码，并与基线对比（基线：`6 failed, 2206 passed, 10 deselected`；6 条红是既有外部红——含外部 E2Feature 基线、别的 key 任务书缺失、TS 子进程 runner 返回 None）；
  3. 每条 VC 的**观察点**说明（从哪个真实文件/事件读的实测值）；
  4. 新增测试数 = 文件行数分布（避免"一条测试覆盖四条 VC"）。
- `output.md` 按五段契约（含 `[VERIFY]` 行）。

## 写入允许面

- `packages/multi-workers/test_mdc_concurrency.py`（新建）
- `.agenticdoc/mw-dynamic-concurrency/evidence/M-05-tests-python.md`（唯一证据文件）
- 临时探针脚本（`packages/multi-workers/` 下，跑完删除）

## 写入禁止面

- **任何生产代码**：`packages/multi-workers/autopilot/**`（含 `conductor.py`、`dispatch.py`、`config.py`、`task_graph.py`）、`packages/multi-workers/mw_common.py`、`mw.py`、`launcher.py`（后三者是**另一 session 的活跃写面**，只读）
- **任何既有测试文件**（`test_*.py` 已存在者一律不改；要加断言就加到你的新文件里）
- `packages/multi-workers/test/fixtures/*.json`（冻结语料，只读）
- 所有 `packages/coding-agent/**`、`dist/**`
- `npm run check`（P-017）、无文件参数 vitest（P-032）、任何 git 写操作
- 不得删除/跳过/放宽既有断言

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q test_mdc_concurrency.py
python -m pytest -q
```

## 改动历史

- `packages/multi-workers/autopilot/conductor.py:706-712` 在飞集合（`_is_in_flight ∧ _row_belongs_to`）——VC-101/102 的 layer 口径来源
- `packages/multi-workers/autopilot/conductor.py:752` key 层上界判定——VC-101/103
- `packages/multi-workers/autopilot/conductor.py:1989` `cap = max(1, int(cfg.get("max_workers_per_key", 4)))`——VC-101/102 的 per-key 上界
- `packages/multi-workers/autopilot/config.py:91-92` 与 `:127-128` 默认值/范围——VC-103 的热读对象
- `packages/multi-workers/autopilot/task_graph.py`（M-01 前沿模块）——VC-101/104 的图输入
