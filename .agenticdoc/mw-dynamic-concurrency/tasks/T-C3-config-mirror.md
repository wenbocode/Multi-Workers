# T-C3 — 配置与镜像（RQ-C3）

- type: research
- key: mw-dynamic-concurrency
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-config-mirror-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**把 `max_parallel_keys` 从硬上限改成上界、并新增 per-key 上界键，要动哪些地方？两侧镜像与既有配置如何兼容？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - Python 配置：`packages/multi-workers/autopilot/config.py`（`DEFAULT_CONFIG` `:87`、`_INT_RANGES` `:122`、`validate_config`）；机器层 `autopilot/effective_config.py`（`EFFECTIVE_KEYS`）。
  - TS 镜像：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（`DEFAULT_CONFIG` `:147` 附近、`INT_RANGES` `:196`、`validate`）。
  - 已知失败模式：对已 materialized 显式写 2 的项目，改默认值是空操作（`.agenticdoc/mw-autopilot-slot-capacity/achieved.md` §3 (c3′)、D-020）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 parity 语料、`.agenticdoc/_autopilot/config.json` 实例、其它 key、`.mw/`）。

## 要求

1. **`max_parallel_keys` 生效链**：定义 → 校验 → 读取 → 消费（消费点 `conductor.py:744`），每条 `file:line`；并给"项目层可配、机器层不可配"的证据（`EFFECTIVE_KEYS`）。
2. **两侧镜像清单**：Python 与 TS 的默认值、取值域、校验语义逐字段对照表（含 `launcher_max_workers` / `dispatch_max_per_scan` 等邻近键），指出任何已有漂移；找出现有 parity 语料/测试 `file:line` 与重冻方式。
3. **既有配置兼容面**：找出会"显式 materialize 全部键"的写路径（TS `saveConfig` / `mw autopilot` CLI），说明语义变更（硬上限→上界 / floor 变更）在既有项目上的实际行为；列出会被影响的现存 `config.json` 实例（只读扫描）。
4. **新增 per-key 键的落点**：给一份"新增键需要改的文件清单"（Python 配置/校验/消费 + TS 镜像/校验 + parity 语料 + README 配置表 + 面板渲染），每项 `file:line`。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-config-mirror-20261014.md`（结论先行 + 镜像对照表 + 兼容面 + 改动清单 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印。
