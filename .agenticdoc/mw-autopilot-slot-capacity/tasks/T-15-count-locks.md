# T-15: 计数锁刷新（T-03 协调缺口修补）

- 波次: **1** · 依赖: T-03（已完成）
- 写面（独占）: `packages/multi-workers/test_autopilot_config.py`、`packages/multi-workers/test_autopilot_gates.py`、`packages/multi-workers/test_autopilot_effective_config.py`、`packages/multi-workers/test_mw_autopilot_cli.py`
- AC: AC-018, AC-026 · VC: VC-011, VC-024, VC-038
- 基线: `c3edc20fe` + 已落地的 T-03
- **来源**：T-03 回执主动上报的协调缺口（14 条失败不在 T-11 声明的写面内）。PM 复算确认：**全部是计数锁，无真回归**。

## 目标

T-03 加了 1 个配置键（`DEFAULT_CONFIG` 13→14）与 28 个门字段（`FRONTMATTER_FIELDS` 12→40），使四处**硬编码计数断言**变红。这些断言锁的是**有意变更的契约**，因此正确处置 = **刷新其期望值并保持断言强度**，而不是弱化或删除。

## 交付物

- `test_autopilot_config.py:113`、`:134`：`len(DEFAULT_CONFIG) == 13` → `14`；`:134` 的 `len(cfg.default_config())` 同理。
- `test_autopilot_gates.py:221-222`：`keys == list(FRONTMATTER_FIELDS)` 与长度断言 → 按 T-03 后的真实顺序（base 12 + 26 + `consumed_at`/`consumed_seq` = 40）刷新。
- `test_autopilot_effective_config.py`：7 处 `len(eff.values) == 13` → `14`（含 `:72` 的 `_assert_full_view`、`:205`）。
- `test_mw_autopilot_cli.py`：若含 13 键/键数断言，同步刷新。
- 每条刷新处**补一行注释**说明"计数变化来自 mw-autopilot-slot-capacity"，便于审计。

## 契约（不得重定义）

- **只改期望值，不删除断言、不改成 `>=`、不 `skip`**。每一次刷新后该断言仍须能捕获真实漂移（例如把 `14` 写成 `15` 必须立刻红）。
- `EFFECTIVE_KEYS` 相关断言**必须保持 "机器层仍只有 2 个键"**：`auto_gate_mode` **不得**出现在 `EFFECTIVE_KEYS` 里（若某断言期望它出现，说明 T-03 越界，报给 PM）。
- 不动测试以外的任何文件；不动 `test_autopilot_config_parity.py` 与语料（T-11 的写面）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_config.py test_autopilot_gates.py test_autopilot_effective_config.py test_mw_autopilot_cli.py -q`（必须 0 failed）
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_config_parity.py -q`（**预期仍红**：那属 T-11，不要在本卡修）

## 非空洞对照（必须附）

- 把任一处 `14` 改成 `15` ⇒ 该断言必须立刻红（证明刷新后仍有效，没被弱化成恒真）。
- 断言 `EFFECTIVE_KEYS` 不含 `auto_gate_mode`（显式负断言），并证明若把它加进去该断言会红。

## 风险与注意

- 这些文件属**跨 key 共用面**：`mw-autopilot-verify-cli` 的 13 键 parity 用例就在邻域，改动前先 `git status` 确认无他人未提交改动。
- 若发现某处断言无法在不弱化的情况下刷新（例如它同时锁住了 `EFFECTIVE_KEYS` 语义），**停下来报 PM**，不要自行取舍。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t15-count-locks/report.md`（含 `[VERIFY]` 命令原文与输出、每条刷新处的前后值与注释、非空洞对照的实际红/绿）。
