# T-W-I05 · 算子修正（TS）：D-111 优先级 + 语料新 kind（B0 返工）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` — 核心交付是「一个常驻 mw 服务 + 多 Worker 并行开发同一个项目」，其前提是同文件多写者对 = 0。本卡修的是该前提的**判定层**：B0 的 TS 算子在两语言一致性上的实测缺陷。判定错了，PM/TS 侧的派发闸门就建在错的判定上。
- B0 的 TS 算子 `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts` 已交付（92 用例全绿），但 PM 用**随机差分 + 定位矩阵**独立复算后发现了缺陷，并把契约锁进扩展后的语料（`parse` 16→23、`overlap` 49→58）。证据：`.agenticdoc/mw-write-face-guard/evidence/PM-parity-differential-20261014.md`（§1–§5 是实测，§4 是裁定）。
- **定位锚点**: `shared/write-face.ts:616`（`parseWriteFace`）、`shared/write-face.ts:635`（`parseWriteFaceEntries`）、`shared/write-face.ts:815`（`writeFacesOverlap`）、`shared/write-face.ts:834`（`isWriteFaceOverlap`）。
- 裁定条目（`design.md`，必须逐条实现）：
  - **D-111 parse 期**：硬规则违规（`write-face-escape` / `write-face-invalid-entry` / `write-face-outside-base`）**优先**，且**与条目顺序无关**（TS 现状已经满足，`V52`–`V56` 全过，属于要**保住**的性质）。
  - **D-111 overlap 期**：**先证冲突**——能给出 glob-free witness 就返回 `Conflict`；只有证不出冲突且任一侧含不受支持语法时才返回 `Unsupported`。**TS 现状违反此条**（`V57` 红）。
  - **D-112 切分**：头部值先 `split(',')` 切字段、逐个 trim 后各自解析；**切分语法无感**（TS 现状已满足：`P21` 期望 `["src/{a", "b"]` 与 `P22`/`P23` 均已符合——**注意 `P21` 的期望值被 PM 修正过，见语料 `note`**）。
- PM 实测的 TS 现状（红项来自 `evidence/PM-parity-differential-20261014.md` §3 + 扩展语料实跑）：

| 语料行 | 期望 | TS 现状 |
|---|---|---|
| `V57`（`["src/[a-","src/x.ts"]` × `["src/x.ts"]`） | `overlap`（`src/x.ts` 可证） | `unsupported` |
| `V49`/`V50`/`V51` | `unsupported` | 行为正确，但**测试文件**不认识 `unsupported` 这个 kind（断言 `expect(result !== null && !("unsupported" in result))` 直接判红） |
| counts 冻结断言 | `parse 23 / overlap 58` | 硬编码 `16 / 49` |

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`
- `packages/coding-agent/test/suite/write-face.test.ts`

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/test/fixtures/write-face-corpus.json` **只读**（PM 冻结的契约，本卡是让代码满足它，而不是让语料适应代码——认为语料本身有错就报回 PM）；`packages/multi-workers/**` 全只读（Python 侧属 T-W-I04，正在并行改）；`worker/read-scope.ts`、`worker/worker-mode.ts`、`pm/ui-bridge.ts` 只读（别的卡拥有）。

## 要求

1. 满足冻结语料的**全部**新行（`P17`–`P23`、`V49`–`V57`），且不许改动任何旧行的既有期望。
2. overlap 期改为 D-111：先在**受支持** glob 之间求可证冲突并返回带 glob-free witness 的 `Conflict`；证不出冲突且任一侧存在不受支持条目时返回 `Unsupported`；否则 `null`。
3. 测试文件补齐 `unsupported` 这个 `expect.kind` 分支（语料 `protocol.expect_kinds.unsupported` 已给出语义），并把 counts 冻结断言更新为 `parse 23 / overlap 58`。
4. 保住 parse 期的既有性质：硬违规优先且**与条目顺序无关**（`V52`–`V56` 全过）；`P21`/`P22`/`P23` 的切分语义必须与 D-112 一致（语法无感切分；未闭合 `[` 不吞后续字段）。
5. `deny` 依旧**不参与**判定（V37/V38 必须继续通过）。
6. 保持既有公开 API 名称/返回类型形状不变（`parseWriteFace` / `parseWriteFaceEntries` / `writeFacesOverlap` / `isWriteFaceOverlap` / 相关类型）；需要新字段只许**可选追加**。
7. 不新引依赖（`minimatch` 仍是既有依赖，本卡不要求也不禁止使用它做对照）；不写 `any`；不写内联动态 import；只用可擦除 TS 语法。

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-write-face-guard/evidence/W-05-operator-ts-fix.md`，必须包含：① 修正前后对 `V57`/`V49`/`V50`/`V51` 的**实测**输出对照（命令 + 原文）；② 全语料通过计数与 `Tests N passed` 原文；③ 与 Python 侧**同语料逐行对照表**（两列，必须逐行相等）；④ `## 改动历史`
- 代码：`shared/write-face.ts` + `test/suite/write-face.test.ts`
- 测试结论必须是实跑原文（命令 + 尾部计数）

## 验收命令

```bash
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts
```

## 改动历史

证据文件里必须给出 `## 改动历史`：每个改动点的 `file:line` before→after（不许写"见 diff"）。

## 硬约束

- 本卡是**修正卡**：不许顺手扩大范围（不碰 `worker-mode.ts`、不碰 `ui-bridge.ts`、不改语料、不改 Python）。
- **不要跑仓库根 `npm run check`**（多 session 下它会全仓 `biome --write`，会改到别的 session 正在编辑的文件）。若需类型检查，只跑 `tsgo --noEmit -p tsconfig.json` 并只看本模块相关输出。
