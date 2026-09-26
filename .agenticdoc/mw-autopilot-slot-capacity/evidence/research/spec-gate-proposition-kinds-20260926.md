# PM 自采证据：gate 命题的两分 与 case-1 已有原型（2026-09-26）

**采集人**：PM（本窗口）／**性质**：代码事实 + 交叉验证，非 worker 产出
**用途**：为 AC-025（三处置模式判定）提供 PM 侧事实底座，约束 RQ-12/13/14 的解读
**只读**：未改任何代码；本文件是唯一写面

---

## F1（事实）case 1"机器自举验证 → 放行"在现有代码里**已有原型**

xkey 修复链路的第 S4 步就是"机器验证后自动放行"，锚点：

- `packages/multi-workers/autopilot/conductor.py:3595-3660+` `_xkey_run_verify()`，docstring 原文：
  > `"""S4: targeted rerun, red before→after; not green → rollback + no close.`
- 放行判据是**机器复算的布尔条件**（`:3647`）：
  > `if not (red_after == 0 and not timed_out and returncode == 0):`
  不满足即走 `_xkey_verify_failed(...)` 并 `return None`（`:3648-3657`），**不关闭 ticket**。
- 只有在 green 之后才落证据并闭合：`:3885-3891`
  > `if not _xkey_write_evidence(...): return` ／ `_xkey_close(...)`
- **四处 fail-closed**（全部"无法证明即不放行"）：
  - `:3617-3625` target.yml/cwd 不可用 → "must never fall back to a guessed root"
  - `:3626-3631` `xkey_verify_cmd` 为空 → 原文 `"xkey_verify_cmd is empty (cannot prove green)"`
  - `:3637-3642` 异常 → `"fail-closed, never close on doubt"`
  - `:3647-3657` 非 green → `f"not green: red {red_before}->{red_after} rc={returncode} timed_out={timed_out}"`

**意义**：case 1 不需要新造机制；它是既有范式的**推广**。且它给出的判据语言（`cannot prove green` / `never close on doubt` / red_before→red_after 单调归零）可以直接作为 AC-025 第 (1) 类的判据模板。

## F2（分析）命题应两分：**事实性命题**（可自举）vs **政策性授权**（必须人给）

xkey 链路把这两者**拆开**了：
1. `xkey-authorize` gate —— **人**给"允许动手"的授权（**政策**决定，RQ-10 判定"绝不可自动"）；
2. `_xkey_run_verify` —— **机器**自证"缺陷是否真的修好"（**事实**命题）；
3. `_xkey_close` —— 机器按事实结果闭合。

⇒ 结论：**case 1 只适用于事实性命题**。"目标要不要改"（`goal-change`）、"允许不允许修"（`xkey-authorize`）是政策决定，**证据再充分也不能自举**——这不是数据不足，而是命题类型不同。AC-025 的三分判定必须先做这层区分，否则会把"政策题"错误地期望成"等证据齐了就能自动"。

## F3（事实）护栏缺陷 D1 与 6684 门洪泛**事故同源**，且 FM 已逼近阈值

- `conductor.py:310` 实际代码：
  > `m = re.match(r"(gate-\d{4})\b", str(ev.get("detail", "")))`
  `re.match` 从串首锚定 + `\d{4}` 恰 4 位 + `\b` 词边界。对 `gate-10000`：`\d{4}` 吃掉 `"1000"` 后下一个字符是 `"0"`（词字符）⇒ **无词边界 ⇒ 不匹配 ⇒ 该 id 不进 `consumed`** ⇒ 该门被当作"从未消费过"，**可被重复应用**。即 RQ-11 所称的"静默失效"，机制已由代码逐字确认。
- 这段守卫的由来写在 `_apply_stalled_approvals` 的注释里（`:2320-2329`，原文摘要）：
  > `# 2026-09-24 (FeatureMigrator incident): consumption is durable — ... Measured: 6684 pending stalled gates + 6685 stalled/gate-answered/resume events in ~12 h, all from two approved gates, with the key oscillating stalled→running→stalled every tick.`
- ⇒ **同一个守卫既防洪泛、又是 D1 的失效点**：洪泛机制（重放）与守卫失效机制（5 位 id）叠加时，正是"自动 approve 无上界"的灾难路径。FM 当前最大 id 已到 `gate-6687`，洪泛速率 585.8 门/h（RQ-11 实测）。
- ⇒ 定级：**D1 必须在任何自动决策上线之前修完**（AC-022 的顺序约束不是形式要求）。

## F4（事实）现有 fail-closed 表达习惯（可复用的术语基线）

| 原文 | 位置 | 语义 |
|---|---|---|
| `cannot prove green` | `:3629` | 缺少验证手段 ⇒ 不放行 |
| `never close on doubt` | `:3637` | 异常 ⇒ 不放行 |
| `must never fall back to a guessed root` | `:3620` | 定位不可靠 ⇒ 不执行 |
| `red {before}->{after}` | `:3652` | 用单调归零的计数表述"修好了" |

---

## 数据缺口

- 未验证：`gates.py` 里的 id 生成格式是否保证单调递增到 5 位（若 id 生成可回绕/重用，D1 的影响面还需修正）——留给 RQ-12/AC-022。
- 未验证：`_consumed_gate_ids` 之外是否还有第二处按 id 匹配的实现（本次只核了 `:310` 一处）。
