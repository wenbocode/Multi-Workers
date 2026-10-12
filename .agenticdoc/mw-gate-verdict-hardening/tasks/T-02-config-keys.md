# T-02: 三个配置键注册（G1 重掷上限 / G2 提醒阈值与上限）

- 波次: **0** · 依赖: —
- 写面（独占）:
  - `packages/multi-workers/autopilot/config.py`（`DEFAULT_CONFIG` `:55` + `_INT_RANGES` `:79`）
- AC: AC-003, AC-005 · VC: VC-019
- 基线: `10446aefb`

## 目标

把 G1/G2 需要的三个阈值注册进**唯一权威配置表**，使 `T-01`/`T-07` 能读、`T-05` 能镜像、`T-14` 能重冻语料。

## 交付物

| 键 | 类型 | 默认 | 值域 | 消费者 |
|---|---|---|---|---|
| `l3_abort_retry_limit` | int | **1** | 0..10 | T-01（专用重掷上限） |
| `gate_reminder_after_min` | int | **30** | 1..1440 | T-07（提醒阈值） |
| `gate_reminder_max` | int | **2** | **1..2** | T-07（同一门提醒上限） |

- `DEFAULT_CONFIG` **17 → 20** 键（T-18 的 `launcher_max_workers` / `dispatch_max_per_scan` / `queue_alarm_delta` 已把 14 → 17 提前落地；本卡只追加这三个 G1/G2 键，不得改动 T-18 三键的默认值与值域）；`_INT_RANGES` 三键齐备（`(0,10)` / `(1,1440)` / `(1,2)`）。
- `gate_reminder_max` 的值域**必须封在 1..2**：它只能把上限**调低**，不能抬高到破坏 AC-005 的"最多 2 次"（用户确认的 D-007）。
- `gate_reminder_after_min` 上限 1440（24 h）是为了让它**严格早于** doctor 的 24h/72h 文本阈值，保证"提醒先于 doctor 出现"。

## 契约（不得重定义）

- 三键**不进** `EFFECTIVE_KEYS`（维持既有 2 个 xkey 键的口径）。
- 默认值与值域**逐字**同本表，`T-05` 的 TS 镜像与 `T-14` 的冻结语料以本表为权威。
- 不得改动任何既有键的默认值或值域。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_config.py -q`
- `cd packages/multi-workers && python -X utf8 -c "from autopilot import config; assert len(config.DEFAULT_CONFIG)==17, len(config.DEFAULT_CONFIG); assert config._INT_RANGES['gate_reminder_max']==(1,2); print('ok')"`

## 非空洞对照（必须附在回执里）

- 三个键各造一条**越界 reject** 用例（`gate_reminder_max=3`、`l3_abort_retry_limit=11`、`gate_reminder_after_min=0`）⇒ 必须被拒且回落到默认值。
- 三个键各造一条**单键 accept** 用例（只写一个键的 payload）⇒ 必须生效（给 `T-14` 的语料当输入）。

## 风险与注意

- `T-14` 会改 `test_autopilot_config_parity.py` 与冻结语料；本卡**只改 `config.py`**，不要顺手改测试计数（避免两卡互踩）。
- 若既有 `test_autopilot_config.py` 里有 `== 14` 之类的计数锁，本卡只做**最小必要**更新并在回执里点名。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-02-config-keys/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
