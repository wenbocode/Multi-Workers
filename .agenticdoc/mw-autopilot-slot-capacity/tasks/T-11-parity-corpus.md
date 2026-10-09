# T-11: parity 语料重冻（`auto_gate_mode` 两侧镜像 + 计数断言）

- 波次: **2** · 依赖: T-03, T-09
- 写面（独占）: 
  - `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`
  - `packages/multi-workers/test_autopilot_config_parity.py`
  - `packages/coding-agent/test/suite/autopilot-config-parity.test.ts`
  - `packages/coding-agent/test/suite/autopilot-config-sync.test.ts`
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（**配置镜像段**：类型 `:87` 邻域、`DEFAULT_CONFIG` `:111` 邻域、取值域 `:141` 邻域、键联合 `:260` 邻域、parse `:276` 邻域、serialize `:301` 邻域） —— T-09 实测上报：TS 侧**尚未声明** `auto_gate_mode`（当前只在 `monitor.ts` 里 raw read 用于显示）。本卡必须把它加进 TS 配置镜像，否则两侧键数断言与 parity 用例无法成立。
- AC: AC-010, AC-018 · VC: VC-011, VC-022
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

新键 `auto_gate_mode` 上线的跨语言代价必须一次付清：语料新增用例、冻结 sha/计数重算、两侧键数断言从 13 改 14。

## 交付物

- **TS 配置镜像补齐 `auto_gate_mode`**（type / DEFAULT_CONFIG / 取值域闭集 / 键联合 / parse / serialize 六处），与 Python `config.py` 逐项对齐（T-09 上报的缺口）。
- 语料**新增**（不替换）2 例：合法值（`off|shadow|live` 各一）+ 非法值（fail-closed 断言）。
- `FROZEN_CORPUS_SHA256` / `FROZEN_CORPUS_COUNT`（`test_autopilot_config_parity.py:60-61`）重算。
- 键数断言 `13 → 14`（`:423-431` 与 TS `:356/:359`），并保持 `covered == KNOWN_FIELDS` 语义。
- 两侧都跑（P-021）；记录实际计数到卡内证据。

## 契约（不得重定义）

- **只增例不改语料语义**；不得为了让断言过而删既有用例。
- 重新冻结前逐例 diff 打印（防止掩盖回归）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_config_parity.py -q`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts`

## 非空洞对照（必须附在回执里）

- 删掉新增的一例 ⇒ count 断言必须红。
- 非法值例必须是 fail-closed（静默取默认 ⇒ 用例红）。

## 风险与注意

- 该文件是跨语言共享冻结语料：只允许本卡与 T-03 触碰；改 sha 前确认两侧实现已就绪。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-11-parity-corpus/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
