# T-W-D1 — 写面 glob 归一语义与交集算子（RQ-D1）

- type: research
- key: mw-write-face-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 总问题：**"两个写面是否有交集"这个判定，今天在仓里没有算子；要新建时必须先定死 glob 语义，否则两条通道（Python/TS）会给出不同答案。**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 读面三段式（唯一完整范式）：渲染 `packages/multi-workers/autopilot/dispatch.py:748`（`read_scope: Sequence[str] = ()`）与 `:749`（`deny_globs`）→ 解析 `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:259` → 运行期消费 `:167`（`checkReadScopeCall`）。
  - 既有匹配实现的关键行（必读）：`worker/read-scope.ts:89`（`isSameOrUnder`）、`:100`（`normalizeForCompare`）、`:118`（`isWithinScope`）、`:141`（`matchedDenyGlob`，**双基** `:146`）、`:147-153`（尾 `/ **` 也 deny 目录自身）。
  - 既有算子只有"路径 ∈ 集合"，实测 minimatch 10.2.5 行为样例：`minimatch("A/B/C.TS","a/b/c.ts")=false`、`minimatch("a","a/**")=false`、`minimatch("A/B","a/b",{nocase:true})=true`（见 `evidence/research/spec-write-face-enforcement-20261014.md` §3）。
  - 待处置的 4 个写面载体见 `evidence/research/spec-write-face-sources-20261014.md`（W1..W4）；W2 的异语义消费点在 `packages/multi-workers/autopilot/conductor.py:6518`。
  - 派发卡（本 key 已用格式）：`.agenticdoc/mw-write-face-guard/tasks/T-W2-write-face-enforcement.md`。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `dist/`、其它 key、`.mw/`）。

## 要求

1. **差异点穷举**：把现有读面匹配实现（`worker/read-scope.ts`、`shared/read-scope` 若存在、Python 侧任何等价物）与 minimatch 的语义逐项对比，至少覆盖：大小写（平台差异）、`**` 段中/段的语义、`a/**` 是否含 `a`、多 base/根锚定、realpath vs 词法比较、相对 vs 绝对、`|` 或 `,` 分隔符、反斜杠。每项给 `file:line` + 原文 + 判定。
2. **归一建议**：对每个差异点，指出 `write_face` 应取哪一侧，并给出**理由**（与 Windows 目标、与既有 `read_scope` 兼容、与 `deny_globs` 的优先关系）。必须明确：deny 优先还是 allow 优先？交集判定里 deny 如何参与（例如 A 的 deny 面遮盖了 B 的 allow 面时是否算不重叠）。
3. **交集算子规范**：给出 `write_faces_overlap(a, b) -> 冲突样例 | None` 的精确定义（伪码级），必须可被判为"无交集"而不需要枚举真实文件系统（纯词法 + 有限约束求解即可，或明确说明何时必须回退到"保守视为重叠"）。
4. **边界向量集**：给一份可直接用于测试的向量表（≥ 20 条，含跨目录 `**`、大小写、同文件不同写法、目录 vs 文件、`a/**` vs `a/b`、`a/**/*.ts` vs `a/b.ts`、空面、未声明面），每条标明期望判定与理由。标注哪些向量在 Python/TS 两侧实现时最容易分叉。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件: `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`（结论先行 + 差异点表 + 规范化建议 + 伪码 + 向量表 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印（例：实跑 minimatch 的样例输出）。
