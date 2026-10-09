# T-17: TS 计数锁刷新（T-11 协调缺口修补）

- 波次: **2** · 依赖: T-03, T-11（均已完成）
- 写面（独占）: `packages/coding-agent/test/suite/autopilot-console.test.ts`
- AC: AC-018, AC-026 · VC: VC-011, VC-024
- **来源**：T-11 回执上报（`autopilot-console.test.ts` 2 条红，不在其写面内）。PM 独立复算：确为计数/形状锁，非真回归。

## 目标

`auto_gate_mode` 落地后，`autopilot-console.test.ts` 两处硬编码 13 键断言变红（与 T-15 在 Python 侧处理的是**同一类**）：

- `:870`：`expected [ 'enabled', 'paused', …(12) ] to have a length of 13 but got 14`
- `:871`（同族）
- `:1181-1196`：whole-object deep-equal 断言里少了 `auto_gate_mode`

正确处置 = **刷新期望值并保持断言强度**（不许 `>=`、不许 skip、不许删断言）。

## 交付物

- 三处计数/形状锁刷新为 14 键（含 `auto_gate_mode`），并逐处补一行注释：`# Count changed 13 -> 14 in mw-autopilot-slot-capacity (T-03 added auto_gate_mode).`
- 新增一条**显式负断言**：TS 侧 `EFFECTIVE_KEYS`（或等价导出）仍**只有 2 个 xkey 键**、且不含 `auto_gate_mode`（YAML/Python 侧已有同款锁，本卡补 TS 侧）。
- 若发现测试里还有其它被前序失败遮蔽的同族锁（如 T-15 遇到的隐藏尾序锁），一并刷新并在回执里逐个列出。

## 契约（不得重定义）

- 只改**期望值**。断言形态（长度相等 / whole-object 相等）保持不变 —— 刷新后把 `14` 改成 `15` 必须立刻红。
- 不动 `status-model.ts` / `config` 实现 / parity 语料（T-11 已收口）。
- 不做"把测试改成动态读常量算期望值"的改写（那会把锁变成恒真）。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts`（必须 37/37 绿）

## 非空洞对照（必须附）

- 把任一处 `14` 改成 `15` ⇒ 对应断言必须立刻红。
- 负断言对照：把 `auto_gate_mode` 临时塞进 TS 的 `EFFECTIVE_KEYS` ⇒ 负断言必须红（随后还原）。

## 风险与注意

- 该文件属 `mw-autopilot-verify-cli` 的 AC 邻域（AC-015/016/025 用例），刷新时**不得**改动用例语义，只改期望值。
- 若某处断言无法在不弱化的前提下刷新（例如它锁的是"命令写回配置的完整形状"），停下来报 PM。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t17-ts-count-locks/report.md`（含 `[VERIFY]` 原文与输出、每处刷新前/后值与注释、两条反向对照的红/绿、若发现隐藏锁则逐个列出）。
