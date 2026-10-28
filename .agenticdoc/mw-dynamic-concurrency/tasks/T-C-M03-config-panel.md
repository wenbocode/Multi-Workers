# T-C-M03 · 配置上界放宽 + per-key 上界键 + 面板三量（MDC B0 剩余）

- type: coding
- key: mw-dynamic-concurrency

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— key 层上界与 per-key 上界都必须是**配置里的上界**（默认值放开、下限允许 1），并**两侧语言镜像一致**；面板要能同时看见"配置上界"与"本 tick effective 并发"。
- **spec AC**: AC-004（`max_parallel_keys` 作为 key 层上界：默认值/floor/取值域两侧镜像；新增 per-key 上界键且既有 materialized config 不因此非法）、AC-005（monitor 同时显示"配置上界"与"本 tick effective 并发"，同快照可复算一致）、AC-006（上界配 1 ⇒ 两层都串行，无需重启 serve）、AC-007（两语言配置镜像逐字段一致，parity 语料）。
- **design**: D-102（`max_workers_per_key` 默认 **4**、下限 1）；`evidence/research/design-cap-and-status-20261014.md` §2 有**预期翻转清单**（先读它，别自己猜）。
- **计划**: `plan.md` §2 M-03（本卡）+ §3.3/§3.4 串行点（`status-model.ts` 跨 key 热文件；parity 语料单一写者）+ §5。
- **定位锚点（以 symbol 为准，实现前先 grep）**:
  - `packages/multi-workers/autopilot/config.py`: `:16` 文档串 `max_parallel_keys int 2 (floor 2)`、`:87` `"max_parallel_keys": 2`、`:122` 取值域 `(2, None)`；键表结构在 `:80-140` 一带（**新区键要插在 `max_parallel_keys` 之后的 index 4 位，不是追加表尾**——RQ-D5 实测两侧键序断言共 9 条会翻）。
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`: `:136` `max_parallel_keys: 2`、`:196` `max_parallel_keys: [2, null]`、`:328-354`（键名表/解析）、`:1606`/`:1742`/`:1794`（消费点）。
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`: `:232-233` `slotsUsed`/`slotsMax`、`:932` `slotsUsed: busyKeys.size`（**今天只数 `running`，实测与 conductor 含 `pending` 差 1**，AC-012 的子问题"`pending` 算不算在飞"要在此显式对齐到 conductor 同源）。
  - parity 语料: `packages/multi-workers/test/fixtures/autopilot-config-corpus.json:292` `range-max-parallel-low`（payload `{"max_parallel_keys": 1}` **期望 reject → 现在应变 accept**）、`:305` `range-max-parallel-min`（`{"max_parallel_keys": 2}` 保持 accept）、`:357`/`:368` 两个 bigint 行（**只改期望值，不要动 payload**）。
  - 计数锁（20 键）：`packages/multi-workers/test_autopilot_config.py:117/153/154/188`（`== 20` 四处）、`test_mwgal_t12_stage_close_auto.py:656-679`、`test_mwgal_t15_reattest_confirm.py:717-741`、`packages/coding-agent/test/suite/autopilot-console.test.ts:911/1276`（`toHaveLength(20)` 两处）+ `:943` 一带的键名清单 + `:394/425/451/485` 的 `max_parallel_keys: 2` 等值断言。

## 写入允许面

- `packages/multi-workers/autopilot/config.py`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
- `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`
- 计数锁同步（**只允许 20→21 一类机械同步 + 键名清单补一项 + 默认值 2→8 的期望更新**）：`packages/multi-workers/test_autopilot_config.py`、`test_mwgal_t12_stage_close_auto.py`、`test_mwgal_t15_reattest_confirm.py`、`packages/coding-agent/test/suite/autopilot-console.test.ts`、`packages/coding-agent/test/suite/autopilot-config-parity.test.ts`、`packages/coding-agent/test/suite/autopilot-config-sync.test.ts`，以及全仓 sweep 后发现的**同类计数锁文件**（必须在 output.md 逐条列出 `file:line` 与 before→after，PM 会核对）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/autopilot/conductor.py`（**M-02 正在并行改，唯一写者**）、`autopilot/dispatch.py`、`autopilot/task_graph.py`、`mw_common.py`（其它 session 活动写面）、`packages/coding-agent/src/extensions/agent-team-loop/pm/**`、`autopilot/console.ts`（widget 排序刚落地）。**禁止 `npm run check`**（P-017）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **key 层上界（AC-004）**：`max_parallel_keys` 默认 **2 → 8**、下限 **2 → 1**；`config.py:16` 的文档串、默认值表、取值域三处同步；`status-model.ts:136`/`:196` 与默认值/取值域**逐字段镜像**（同一波改两侧）。
2. **新增 per-key 上界键（AC-004/D-102）**：名字 `max_workers_per_key`，默认 **4**、下限 1；**插在 `max_parallel_keys` 之后的 index 4 位**（不是表尾）；两侧同波；既有 materialized `config.json` 文件**不得因此变非法**（键缺席 ⇒ 默认值，不许报错）。
3. **面板三量（AC-005/AC-012 子问题）**：monitor 同时显示 `cap`（配置上界）、`eff = min(cap, |F|)`（本 tick effective 并发）、`|F|`（前沿大小）；`used` 口径**改为与 conductor 同源**（今天 `slotsUsed` 只数 `running`，实测比 conductor 少 1——把口径对齐并在此显式说明你选了哪一边、为什么）。只加量，**不动既有行序**（面板高度/行序有既有断言）。
4. **回退语义（AC-006）**：上界配 1 ⇒ 两层都串行（`≤1`），且**不需要重启 serve**（配置每 tick 重读）。
5. **parity 与计数锁（AC-007）**：重冻语料——`range-max-parallel-low` 期望 `reject → accept`、新增 `partial-key-max_workers_per_key` 等行（照 `design-cap-and-status-20261014.md` §2 的清单）、计数锁 `20 → 21`（Python 与 TS 两侧全量）；`conductor.py` 里那句"13 键"文案**不要动**（M-02 的面），若它在你扫描时也过期了，只记录不修。
6. **不得回归**：两侧测试全绿（含 parity/sync/console 套件），并给出你 sweep 到的**计数锁文件完整清单**。

## 交付格式

`output.md` 五段齐全。`证据` 段给**可复跑原始命令 + 原始输出**：① 新旧语料 `sha256` 与计数、每张被翻断言文件的 before→after（逐条 `file:line`）；② 默认值/floor 三处的 before→after；③ 面板三量的原始渲染行（含同快照复算：`eff == min(cap, |F|)`）；④ 上界=1 的复算输出；⑤ 你 sweep 到的计数锁文件清单（`file:line` + 新值）。唯一证据文件：`.agenticdoc/mw-dynamic-concurrency/evidence/M-03-config-panel.md`。若出现 `## 路径形态（warn）`/`## Ledger Malformed` 段，它来自 `worker/output-writer.ts`，不影响判定。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test_autopilot_config.py test_mwgal_t12_stage_close_auto.py test_mwgal_t15_reattest_confirm.py -q
python -m pytest -q
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-console.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts
npx tsgo --noEmit
```

## 改动历史

- 2026-10-14 WFG 已 DONE（D-018 的"先判面再放开"前置满足）⇒ 本卡（**就是"放开"这个动作**）才允许开跑；此前 M-03 一直被显式阻断。
- 2026-10-14 M-01（task_graph）已完成（与配置面无关）。
- 本卡与 M-02（`conductor.py`）**文件集不相交**，并行执行；M-02 会以 `cfg.get("max_workers_per_key", 4)` 读你新增的键（缺键也能跑）。

## 硬约束

- 新键插 index 4（不是表尾）；两侧同波，逐字段镜像。
- 既有 materialized config 文件不得变非法（缺席 ⇒ 默认，不报错）。
- 不动 `conductor.py`/`dispatch.py`（并行卡的面）；不新增/改 timeline 事件名。
- 不跑 `npm run check`（P-017）；不跑无文件参数的全量 vitest（P-032）。
- sweep 到的计数锁文件必须在 output.md 逐条列出；**不得**为了绿而删断言、放宽断言或把计数写成通配。
