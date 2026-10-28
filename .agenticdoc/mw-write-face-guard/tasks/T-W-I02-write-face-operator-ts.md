# T-W-I02 · `write_face` 交集算子（TS 侧，B0）

- type: coding
- key: mw-write-face-guard

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`（新建）
- `packages/coding-agent/test/suite/write-face.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/test/fixtures/write-face-corpus.json` **只读**（PM 冻结契约）；`packages/multi-workers/**` 全只读；`worker/read-scope.ts`、`worker/worker-mode.ts`、`pm/ui-bridge.ts` 全只读（别的卡拥有）

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` — 多 Worker 并行开发同一项目的前提是**同文件多写者对 = 0**。本卡交付该判定在 TS 侧的**词法算子**（与 Python 侧同语义、同语料）。
- **已冻结的契约（逐条实现，不要重新设计）**: `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md` §3.1（语法与解析期 fail-closed 规则、语义点）、§3.2（**判定里 deny 不参与** + 保守回退清单）、§3.3（三态）、§4.2/§4.3/§4.4（段级交集 / ε-NFA 乘积 / 面级算子）。
- **为什么不能直接拿 minimatch 当算子**: 语义基准确实是 minimatch，但**交集运算**它没有——仓内 5 套既有实现（`worker/read-scope.ts:89` `isSameOrUnder`、`:118` `isWithinScope`、`:141` `matchedDenyGlob`、`worker/worker-mode.ts:1564` `matchesWriteScopeEntry`、Python `autopilot/xkey.py:1084` `fnmatch`）全是"单路径 vs 模式"的谓词，**glob×glob 不存在**。minimatch 可用来做单点对照（`[VERIFY]` 里对 `a/**` vs `a` 等要给出 minimatch 的裸结果与我们的期望值差异），但不能用来实现交集。
- **必须与 Python 侧逐行相等**: 两侧读同一份语料 `packages/multi-workers/test/fixtures/write-face-corpus.json`（只读），期望值逐行相同（P-021）。语料里的 `overlap` 行只断言**结论 kind**（overlap/none/reject/serial_only）与 witness 是否 glob-free，不锁定具体 witness 文本——所以两侧不需要在 witness 选取上互相抄。
- **前置决策**: `design.md` D-001（载体三态）、D-006（算子语义，**deny 方向已按 RQ-D1 修正**）、D-009（两语言一份语义）；`.agenticdoc/mw-write-face-guard/plan.md` §1（本卡独占这两个文件）。
- **下游会用它的地方**（知道即可，不要改）: PM 派发闸 `pm/task-dispatcher.ts` + `pm/ui-bridge.ts` 的 `mergeCardHeader`（渲染 `write_face:`）、运行期闸 `worker/worker-mode.ts`。

## 要求

1. **`shared/write-face.ts`（新建）**，导出：
   - 拒绝码常量：`write-face-empty` / `write-face-invalid-entry` / `write-face-escape` / `write-face-outside-base`；
   - `parseWriteFace(text, opts: { base: string; caseInsensitive: boolean })`：按 §3.1 全部解析期规则归一/校验；**三态**（缺头 → 未声明；有头空值 → `write-face-empty`；`-`（仅横线、允许两侧空白）→ 未声明，与缺头同义）；返回归一段表示；
   - `writeFacesOverlap(a, b)`：按 §4.4 返回 `{ sample, rule, other, reason } | null | { unsupported: string }`；逐 `allow` 对按**文档序**取第一个可证交集；未声明的一侧**不进本函数**。
2. **算法按 §4.3 实现 ε-NFA 乘积**（`**` 自环 + 零段 ε 迁移；接受条件 = 到达终态对且至少 1 条消费边）。两个硬验收点：`["**"]` vs `["x","y"]` 必须重叠；`a/**/b` vs `a/b` 必须重叠。用记忆化/BFS（典型 face < 20 段），不得写成指数回溯。
3. **witness 必须 glob-free**：返回的 `sample` 不含 `* ? [ ] { }`。占位符如 `<unknown>` 不算 witness。
4. **保守回退**（§3.2 清单任一命中 ⇒ 判重叠）：extglob 取反 `!(...)`、`+()`/`*()`/`?()`、非法 class、brace 嵌套超限、跨 base 绝对路径、步数/深度超限。
5. **不新增依赖**；`minimatch` 已在用（`read-scope.ts`），可用于单点对照，但不得把交集判定实现成对 minimatch 的重复调用。
6. **按冻结语料驱动**：`packages/multi-workers/test/fixtures/write-face-corpus.json`（只读）16 条 `parse` + 49 条 `overlap` 全过；`$REPO`/`$OUTSIDE` 按 `protocol.entries_placeholder` 替换（测试里用 `process.cwd()` 与一个仓外临时目录）。

## 交付格式

- 代码：`packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`、`packages/coding-agent/test/suite/write-face.test.ts`
- 唯一证据文件（本卡唯一允许写入的报告路径）: `.agenticdoc/mw-write-face-guard/evidence/W-02-write-face-operator-ts.md`
  结构：`## TL;DR`／`## 交付物`／`## 验收输出`（vitest 原文）／`## 与 Python 侧的同语料对照表`（两列必须逐行相等）／`## 裸 minimatch 差异对照`（哪些向量裸 minimatch 会给出与 §3.1 相反的结论，这正是不能直接复用的证据）／`## 残留与未验证`／`## 上下文来源`／`## 改动历史`（`file:line` before→after）
- 测试必须放在 `test/suite/`，**不得使用真 provider/凭证**（AGENTS.md）；本卡不需要 faux provider（纯函数单测）。

## 验收命令

```
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts
```

类型检查（可选、只对本包）：
```
cd packages/coding-agent; node ../../node_modules/.bin/tsgo --noEmit -p tsconfig.json
```
**不要**跑根 `npm run check`：它在多 session 环境会执行仓库级 `biome --write`，可能改写其它窗口的未提交文件。

## 硬约束

- 只写"写入允许面"里的两个文件。
- 不改 `read-scope.ts` / `worker-mode.ts` / `ui-bridge.ts` / `dispatch-card.ts`（别的卡拥有；`ui-bridge.ts` 的 `mergeCardHeader` 由 B1 的卡负责）。
- 不使用 `any`；不写内联动态 import；只用可擦除 TS 语法（Node strip-only 模式）。

## 改动历史

唯一证据文件里必须给出 `## 改动历史`：每个新增/修改文件的 `file:line` before→after；本卡两个文件均为**新建**（写"新建"）。
