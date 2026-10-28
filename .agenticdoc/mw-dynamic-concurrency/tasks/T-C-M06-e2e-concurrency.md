type: coding
key: mw-dynamic-concurrency
batch: B4
card: T-C-M06-e2e-concurrency
phase: execute
goal: .agenticdoc/goal.md

# T-C-M06 · 端到端并发反证（VC-105/106/109）+ AC-002 顶配空窗量化

## 上下文

- 目标（本 key）：autopilot 并发从"静态上限 2 的 key 层"改成**依赖前沿驱动、按前沿动态最大化**（key 层 + per-key 两层上界），且**写面判定先行**（D-018）。前置 key `mw-write-face-guard` 已 DONE；B0–B3 全部落地（M-01 任务图、M-02 conductor 前沿、M-03 配置+面板、M-04 identity 去重、M-05 两侧测试）。
- 本卡是 **B4**：只做**端到端反证与量化**，不新增功能、不改生产语义。
- 已落地的关键事实（PM 已复核，行号以当前工作树为准）：
  - per-key 上界与前沿消费：`packages/multi-workers/autopilot/conductor.py:1989` `cap = max(1, int(cfg.get("max_workers_per_key", 4)))`，实起 = `min(cap, |前沿|)`；key 层 `:752`。
  - 写面闸与 identity 守卫：`autopilot/dispatch.py:1463-1505`（锁内、零副作用；`duplicate-dispatch:` 拒绝）；等待类元组 `conductor.py:1857` 含 `"duplicate-dispatch"`（3b，已落地）。
  - 写面判定与序列化：`autopilot/write_face.py`（`parse_write_face` / `overlap`），TS 镜像 `shared/write-face.ts`。
  - 面板三量：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:968/991/994-995`（`cap` / `slotsUsed`（key 数）/ `eff=min(cap,|F|)`）。
  - `advance` 墙钟已由 M-02 打进 `advance` 事件的 `data={"ms": n}`（`conductor.py:1583-1600`，**无新事件名**）；M-02 与 PM 已各自测到 `window_share≈0.99`、`74–257×`。
- **PM 已记录的未闭合边界（本卡必须量化，不必修）**：跨 tick **顶配（top-up）未开** —— 任一在飞 key 仍跳过 `_advance_key`，因此同 tick 批次内 `min(cap,|F|)` 成立，但批内 N 个 worker **全部完成前不补派**。见 `plan.md` §7.2 残留①。

## 要求

新增**一个** Python e2e 测试文件 + 一份证据，完成下列反证与量化（每条都要**原始输出**，不是结论复述）：

1. **VC-105（N≥4 并发安全反证）**：构造一个 fixture 项目（`_roadmap.md` + 1 个 running key + ≥5 个任务卡，其中 ≥4 张声明**互不重叠**的 `write_face:` 且依赖前沿足够宽），驱动**真实** `conductor.tick` 让实起 ≥4；随后从**真实队列** `.agenticdoc/_workers.parallel` 取在飞行，用**写面判定本体**（`autopilot.write_face.overlap` / `dispatch._write_face_verdict` 的同一路径，不得自写第二个重叠算法）复算**同文件多写者对 = 0**，并给出复算所用的行集与判定次数。
2. **VC-106（注入并发下 identity 唯一）**：对同一 `task_key` 注入并发（双进程 direct 入口 + conductor 入口；M-04 已给对拍 harness 的先例 `_scratch/evidence/mdc-m04-probe-pm-rerun-20261014.txt`），断言 **恰好 1 行**、**恰好 1 个 `dispatch` 事件**、**恰好 1 次 `ok=True`**，并断言被拒方的 reason 前缀是 `duplicate-dispatch:`。
3. **VC-109（性能量化）**：用真实 `advance_phase.py` 子进程采样（M-02 §6/附录 A 的 harness 先例，注意探针必须放在 `packages/multi-workers/` 下运行，`FRAMEWORK` 由 `__file__` 推导），给出 `window_share = Σadvance_ms / (Σadvance_ms + n×idle_tick_ms)` 的**原始三样本 + 中位数 + 倍率**；并回答"N≥4 时 tick stall 是否可接受"。
4. **AC-002 顶配空窗量化（新增要求，来自 PM 的 §7.2 残留）**：测出"批内 N 个 worker 全部完成 → 下一批启动"的空窗（同一 tick 批次内 N≥4 全部终态后再 tick 的实起行为），给出**实测数字与判定**（可接受 / 需开顶配）。**只量化，不改** `orchestrate`/`execute_loop` 的跳过逻辑。
5. **失败模式诚实性**：若上述任一步无法在 fixture 下稳定复现，**记录并说明不确定性**（不得用"应该"、不得伪造样本）。

约束：不得改任何生产文件；不得放宽任何既有断言；`vitest`/`pytest` 必须带显式文件参数（P-032）；不得 `npm run check`（P-017，B4 批次门禁由 PM 在收口时自己跑）；不得任何 git 写操作。

## 交付格式

- 新测试/探针文件：`packages/multi-workers/test_mdc_e2e.py`（唯一代码写面）。
- 唯一证据文件 `.agenticdoc/mw-dynamic-concurrency/evidence/M-06-e2e.md`，含：
  1. VC-105 的原始输出：实起行数、复算用行集、overlap 判定次数、多写者对 = 0；
  2. VC-106 的双入口对拍原始输出（`grants/refusals/rows/dispatch_events`）；
  3. VC-109 的三个真实 `advance` 样本（ms）+ idle tick ms + `window_share` + 倍率；
  4. AC-002 顶配空窗的实测数字与判定；
  5. 全量 `python -m pytest -q` 的原始 tail + 退出码（若与我记录的基线不同，逐条说明差异；**注意：全量套件不得与其它全量跑并发**）。
- `output.md` 按五段契约（含 `[VERIFY]` 行）。

## 写入允许面

- `packages/multi-workers/test_mdc_e2e.py`（新建）
- `.agenticdoc/mw-dynamic-concurrency/evidence/M-06-e2e.md`（唯一证据文件）
- 临时探针脚本（`packages/multi-workers/` 下，跑完删除）

## 写入禁止面

- **任何生产代码**：`packages/multi-workers/autopilot/**`、`mw_common.py`、`mw.py`、`launcher.py`（后三者是另一 session 的活跃写面，只读）
- 任何既有测试文件；冻结语料 `test/fixtures/*.json`
- 所有 `packages/coding-agent/**`、`dist/**`
- `npm run check`（P-017）、无文件参数 vitest/pytest（P-032）、任何 git 写操作
- 不得删除/跳过/放宽既有断言

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest -q test_mdc_e2e.py
python -m pytest -q test_mdc_concurrency.py test/test_write_face_dispatch.py test_write_face.py test_task_graph.py
python -m pytest -q
```

## 改动历史

- `packages/multi-workers/autopilot/conductor.py:1989` per-key 上界（M-02）——VC-105/AC-002 空窗的观测点
- `packages/multi-workers/autopilot/conductor.py:1857` `_WRITE_FACE_WAIT_REFUSALS`（含 `duplicate-dispatch`，M-04/3b）——VC-106 等待类判据
- `packages/multi-workers/autopilot/dispatch.py:1463-1505` identity 守卫（M-04）——VC-106 的被测本体
- `packages/multi-workers/autopilot/write_face.py`（`overlap`）——VC-105 复算必须复用的判定本体
- `packages/multi-workers/autopilot/conductor.py:1583-1600` `advance` 事件的 `data={"ms": n}`（M-02）——VC-109 的样本来源
