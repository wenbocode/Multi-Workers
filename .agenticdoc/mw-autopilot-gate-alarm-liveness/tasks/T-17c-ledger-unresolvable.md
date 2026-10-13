# T-17c — 不存在的路径不可能是写入（幽灵文件名 / 代码标识符）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-013（C-36 e/f 两个新子类）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/tasks/T-17-ledger-role-aware.md`（C-36a/b/c/d 已修）、`T-17b-ledger-infra-writes.md`（基础设施白名单已落）；
      T-16 终态回读的运行期实证（见下）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（worker 产物自带可信状态；**假扣分与漏判都会污染 PM 判断**，前者的代价是让 worker 与 PM 都去追查不存在的东西）。
- 已核实锚点（自行复核）：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:12`（`diffLedger`：`declared ? recorded`，`extra` = 声明了但没记录）、`:19`（trace 零 `[WRITE_FILE]` 的迁移门）、`:45`（`malformed` warn-only）、`:64/:68`（`WRITE_FILE_EVENT`/格式化）、`:267 INFRA_BASENAMES`（T-17b 落的白名单）、`:294 INFRA_DIR_SEGMENTS`、`:298 isInfrastructurePath`。
  - `.../worker/output-writer.ts:52/:130/:133/:153/:185`（声明 vs 记录判定链）、T-17b 落 `TerminalGaps.infraFiles` 与 `## Ledger Infra` warn 段。
- **运行期实证（T-16 终态，PM 用四项检验逐条判定）**：被点名"未记录写入"的 4 项**全部为假阳性**，其中 2 项属新子类 ——
  | 被点名 | 存在？ | mtime | 判定 |
  |---|---|---|---|
  | `.mw/serve.meta` | 是 | 窗口之外（10:57:56） | 框架写（T-17b 白名单已覆盖**源码**，但运行中 bundle 旧） |
  | `.agenticdoc/_index.parallel` | 是 | 窗口之前（19:25:11） | 框架写（同上） |
  | `update_index.py` | **不存在** | — | **幽灵文件名**（从被读代码文本里捞出） |
  | `os.replace` | **不存在**（Python 标识符，在 `conductor.py` 出现 **7 次**） | — | **代码标识符当路径** |
- **本卡的判据（原则性、不放宽）**：**"声明了但磁盘上不存在"的路径不可能是一次写入** —— worker 不可能写出一个不存在的文件。因此这类 token 归"不可解析 token"（**可见 warn**），而**不是** falsifying 的 `extra`。真实越界写入必然留下**存在的文件 + 事件**，所以该规则**不削弱**真阳性检测。

## 要求

1. **不存在 ⇒ 非写入**：对"仅出现在声明里、磁盘上不存在"的路径，**不得**计入 `extra`；须归入可见 warn 通道（形态与 T-17b 的 `## Ledger Infra` / T-17 的 `## Ledger Malformed` 一致，另开 `## Ledger Unresolvable` 或复用既有 warn 段，报告中须说明选择并保持"不会静默"）。
2. **代码标识符形态**：点号标识符（如 `os.replace`）、无路径分隔符且**不存在**的 token ⇒ 同样归 warn 通道，不得当文件。
3. **真实性判据**：分类必须以**文件系统事实**为准（存在性），**不得**用"看起来像不像路径"的启发式替代；不得依赖 mtime（框架写与 worker 写的 mtime 都在运行窗内，已由 T-17b 证明不可区分）。
4. **不得放宽（P-03，双向）**：
   - 真阳性：`coding` 角色真实越界写入（文件**存在**）**仍必须报红**（回归语料保留 `packages/coding-agent/src/out-of-scope.ts`）；
   - 不得回退 T-17/T-17b：writeless 语料（`l3-verdict.txt`/`auto-decisions.jsonl`/幽灵名）仍零 findings；`_workers.parallel`/`serve.meta`/`_index.parallel` 仍走 infra 通道。
5. **回归语料（必须内建）**：① `update_index.py`（不存在）⇒ 零 findings + warn 可见；② `os.replace`（不存在、点号标识符）⇒ 同上；③ 真实存在的越界文件 ⇒ 仍报红；④ 存在但属 infra（`serve.meta`/`_index.parallel`）⇒ infra 通道；⑤ T-17b 白名单与 T-17 writeless 语料不回退。
6. 报告须给出：`## Ledger Unresolvable`（或所选 warn 段）的**可见性证据**（实际生成的段落/追踪行），以及"为何存在性判据是可靠的"论证。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- 新增：`packages/coding-agent/test/suite/mwgal-t17c-ledger-unresolvable.test.ts`
- 既有 TS 测试中因本卡行为必须更新的期望（逐条说明；不得改弱断言）

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（T-16b 正在改）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/**`、`pm/pm-orchestrator.ts`
- `packages/multi-workers/**`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t17c-ledger-unresolvable.test.ts test/suite/mwgal-t17b-ledger-infra-writes.test.ts test/suite/mwgal-t17-ledger-role-aware.test.ts`

## 改动历史

（填写：分类落点与 warn 段形态、存在性检查的实现方式与开销、与 infra 白名单的优先级顺序、被否决的替代方案（如"用启发式识别代码标识符"为何不可靠）。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
