# T02b foundation-fixes 证据更正（T02c 出具，N-2）

本文件更正 `workers/dd-foundation-fixes/report.md` 与
`evidence/runs/T02b-foundation-fixes/verify-summary.md` 中三处与在档证据不符的叙述。
原 worker 报告按规则**不静默改写历史**：本文件是更正记录，原文件保持原样；PM 收档时
以本文件为准引用 T02b 的这三个数字。

## C1. "T03 全部 33 项通过" → 实为 **23** 项

- 原叙述：`workers/dd-foundation-fixes/report.md:28`（"…650 passed…；T03 全部 33 项通过"）。
- 事实：T03 的 transport 测试文件当时为 **23** 个测试函数、无 parametrize。
  - `evidence/runs/T03-wire-transport/test-names.txt`：**23** 行 test id（逐行统计）。
  - `evidence/runs/T03-wire-transport/verify-summary.md:10` `23 passed`、
    `:12` `23 passed in 10.63s`（repeat）、`:13` `23 test ids`（collect-only）。
- 33 的来源不可复现；650 的总数不受影响（23 与 650 的组成算术相容：
  118 + 151 + 23 + 其他套件函数数及其 parametrize 展开，见 650 日志内嵌
  `[VERIFY]` 行），即 C1 只更正单项计数，不动摇 650 的真实性。
- 补强（新时点）：`test-names.txt`（本目录）= 同一文件今天 `--collect-only` 的 **25** 项
  = T03 的 23 个原名 + 本卡新增 2 个真实 HTTP 元数据键测试；23 项一名不改。

## C2. "650 passed in 74.68s" → 在档日志为 **74.80s**

- 原叙述：`workers/dd-foundation-fixes/report.md:28`、
  `evidence/runs/T02b-foundation-fixes/verify-summary.md:38`。
- 在档日志：`evidence/runs/T02b-foundation-fixes/regression-neighbours-pytest.txt`
  末两行 `650 passed in 74.80s (0:01:14)` / `exit=0`（该文件即上述报告引用的同一路径）。
- 74.68s 无法从被引日志复现（疑为二次运行未注明或转录错误）。**以在档日志 74.80s
  为准**；`650 passed` 与 `exit=0` 本身成立。

## C3. T02b `npx tsgo --noEmit` "0" **未在档**，不计可复核通过

- 原叙述：`workers/dd-foundation-fixes/report.md:30` 与
  `evidence/runs/T02b-foundation-fixes/verify-summary.md:62` 均称 `npx tsgo --noEmit` 为 0。
- 事实：`evidence/runs/T02b-foundation-fixes/npm-check-steps.txt`（38 行）中
  **没有** tsgo 的命令行、stdout 或具名 exit 行；`:27`（install-lock exit=0）之后是
  一次无标题的 `check:ts-imports` 重跑（`:29-33`，两个 `exit=0` 行），随后直接进入
  browser-smoke（`:35-38`）。故 T02b 的 tsgo 通过属**未留档**，不能作为可复核证据，
  也不能算失败——只是不计通过。
- 更正的落实方式（本卡新时点、不覆写过去日志）：
  - `evidence/runs/T02c-metadata-key-safety/tsgo-noemit.txt`：
    cwd `H:\git\Multi-Workers`、cmd `npx tsgo --noEmit`、
    时间 `2026-10-22T12:52:55.0704372+08:00`、stdout/stderr 为空、**exit=0**（完整保存）。
  - 该次运行证明的是 T02c 时点的树 + 本卡（纯 Python）改动，**不是** T02b 当时状态的
    追溯证明；不得据此回填 T02b 的 tsgo 结论。

## 不受影响的部分

- T02b 的 pytest GREEN 实质：`118`（store+roots）、`177`（+backends）均有在档日志；
  `650 passed / exit=0` 有在档日志（仅耗时数字以 C2 更正）。
- 本卡未修改任何 T02b 文件（`workers/dd-foundation-fixes/**` 与
  `evidence/runs/T02b-foundation-fixes/**` 均在写入禁止面之外，本次只读引用）。
