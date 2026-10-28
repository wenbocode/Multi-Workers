# T-W3 — 历史同文件多写事故与最小充分护栏（RQ-W3）

- type: research
- key: mw-write-face-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-safety-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**已发生过什么同文件多写事故？现有护栏覆盖到哪？放开并发前"最小充分护栏"是什么？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 上个 key 记录：PM 手工通道同 key 并发峰值 6、重叠样本 306s / 105.5s（`.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md`）。
  - 上个 key 决策：D-018「per-key 只做观测，不放开」；前置 = 写面声明→机器可读→重叠拒绝（`.agenticdoc/mw-autopilot-slot-capacity/design.md`、`achieved.md` §5 R4）。
  - 现存护栏：`implementation-gate.ts`（`WRITE_VERBS`）、`worker-file-tool.ts`、`xkey-gate-guard.ts`、`protected-config.ts`。
  - 关键锚点（可引用）：`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:79`（`WRITE_VERBS`）、`packages/multi-workers/launcher.py:819`（唯一 spawn 点）、`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2201`（PM 派发入口）、`packages/multi-workers/autopilot/conductor.py:744`（key 层闸）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `_pitfalls.md`、`_incidents/`、其它 key 的 evidence）。

## 要求

1. **事故清单**：从 `.agenticdoc/_pitfalls.md`、`.agenticdoc/_incidents/`、各 key 的 evidence 中穷举"同文件/同路径多写者"事故或样本，每条给出处 `file:line` + 事实（谁写谁、结果、可逆性）。
2. **护栏覆盖面矩阵**：对每个现存护栏，给出拦截的写动词/路径面 + 是否拦"同一路径被两个 worker 并发写" + 判定原文 `file:line`；明确空缺面。
3. **锁与原子性**：列出 `.agenticdoc` 下与工作树文件的写锁（`workers.lock`、`index.lock`、`roadmap.lock` 等）各自保护什么，指出"源码文件写"是否在任何锁内。
4. **最小充分护栏论证**：给出"够用的最小护栏集合"（声明 + 派发拒绝 + 运行期拦截三者的哪几条必要/哪几条可后置），每条附反例（缺它会怎样）。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-safety-20261014.md`（结论先行 + 事故表 + 护栏矩阵 + 最小护栏论证 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印。
