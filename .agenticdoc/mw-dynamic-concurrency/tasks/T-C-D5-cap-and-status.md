# T-C-D5 — 配置改动集、parity 重冻、面板口径与 advance 阻塞（RQ-D5）

- type: research
- key: mw-dynamic-concurrency
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-cap-and-status-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（PM 管多 Worker 并行；不引入中心化调度器）。
- 总问题：**把 `max_parallel_keys` 的默认值/floors 改成"上界语义"并新增 `max_workers_per_key`，两侧镜像与 parity 语料要改哪些确切位置；面板"effective 并发"口径怎么统一；`advance()` 同步阻塞整个 tick 这件事怎么量化。**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 生效链单点：定义 `packages/multi-workers/autopilot/config.py:87`（2）→ 取值域 `:122`（`(2, None)`）→ 唯一消费 `packages/multi-workers/autopilot/conductor.py:744`。
  - TS 镜像：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:136`（默认 2）、`:196`（`[2, null]`）。
  - 机器层不可配：`packages/multi-workers/autopilot/effective_config.py:62-65`（`EFFECTIVE_KEYS` 只有两个 xkey 键）。
  - parity 语料与冻结值：`packages/multi-workers/test/fixtures/autopilot-config-corpus.json`（73 cases，含 `:296-302` 的 `max_parallel_keys: 1` → reject）、`packages/multi-workers/test_autopilot_config_parity.py:60-61`（`FROZEN_CORPUS_SHA256`/`FROZEN_CORPUS_COUNT = 73`）、`packages/coding-agent/test/suite/autopilot-config-sync.test.ts:42-43`。
  - 面板：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:933`（`slotsMax`）、`:1217`（`slots ${a.slotsUsed}/${a.slotsMax}`）、`:917-932`（`slotsUsed` 只数 running 的 conductor 行）。
  - advance 阻塞：`packages/multi-workers/autopilot/advance.py:181-188`（同步 `subprocess.run`），超时常量 `:36`；调用点 `conductor.py:1621`、`:1801`、`:2749`。
  - parity 语料重冻三件套与计数锁清单见 `evidence/research/spec-config-mirror-20261014.md` §2.3/§4.3/§4.4/§4.5。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `dist/`、其它 key、`.mw/`）。

## 要求

1. **配置改动集**：给出改造后的完整 diff 清单（Python + TS 两侧），逐条 `file:line` + 改什么 + 为什么。必须覆盖：`DEFAULT_CONFIG`、`_INT_RANGES`、docstring 键表、`intOf` 白名单、merged read、`saveConfig` 有序对象、`StatusConfigView`、`--json` 子对象、文本摘要。并明确新键插在默认表/取值域表的哪个位置（顺序是否被锁断言约束）。
2. **floor 变更的连带断言**：列出所有会因 `max_parallel_keys` floor 2→1 翻转的测试与语料条目（至少覆盖 `test_autopilot_config.py:50` 与语料 `:296-302`），给出每条需要改成什么。
3. **重冻流程**：给出可执行的重冻步骤（改语料 → 重算 sha256/count → 改两侧冻结常量 → 跑哪两个测试文件），并给出"新键必须补的语料用例名"（P6 的 `covered == expected_keys` 要求）。
4. **面板口径统一**：给出"配置上界 / effective 并发 / 前沿大小"三量的确切来源与计算，指出今天 `slotsUsed`（只数 running）与 conductor（含 pending）的差异如何在不改 conductor 语义的前提下统一；给出 AC-005 可复算的等式。
5. **`advance()` 阻塞量化方案**：给出一个可落地的打点方案（在哪打、记什么、怎么从 timeline/log 读出"tick 被 advance 阻塞的墙钟占比"），以及两条备选缓解（独立执行器 / 每 tick 限一次 advance）各自的改动面与风险。
6. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-cap-and-status-20261014.md`（结论先行 + 改动清单 + 翻转断言表 + 重冻步骤 + 面板口径 + 量化方案 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印（例：语料 sha256/reject 用例复核、面板 slotsUsed 计算复算）。
