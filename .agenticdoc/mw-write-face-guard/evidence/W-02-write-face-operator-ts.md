# W-02 · `write_face` 交集算子（TS 侧，B0）

- key: mw-write-face-guard
- 卡: `tasks/T-W-I02-write-face-operator-ts.md`（card_sha256 `e2820297ee5f787d8771ade0c969c3ed64b576b90181b974884d41891e641c55`）
- 角色: coding（本文件是本卡唯一报告写面）
- 平台: Windows dev（`process.platform=win32`）

## TL;DR

- 新建 `shared/write-face.ts`：三态解析（缺头/`-` → 未声明；有头空 → `write-face-empty`；非空 → 归一 WriteFace）+ §4.4 面级算子 `writeFacesOverlap`。交集是自写 ε-NFA 乘积（`**` 自环 + 零段 ε 迁移），**没有**调用 minimatch。
- 冻结语料 65 行全过：`parse` 16/16、`overlap` 49/49（kind：overlap 32 / none 13 / reject 3 / serial_only 1）；每条 overlap 行的 witness 均为 glob-free。
- 两个硬验收点实测：`**` vs 两段路径 `x/y` → `x/y`；`a/**/b` vs `a/b` → `a/b`。
- 与 Python 侧同语料逐行对照：65 行 **0 mismatch**（两侧 kind/code 完全相同）。
- 保守回退 6 类逐条可触发（extglob `+()/*()/?()/!()`、非法 class、brace 深度、段 token 上限、glob 乘积状态上限、跨 base），命中即 `{ unsupported }`（调用方按重叠处置）。
- 类型检查：`tsgo --noEmit -p tsconfig.json` 无 `write-face` 相关错误。未跑根 `npm run check`（卡明确禁止：多 session 会 `biome --write` 别的窗口文件）。

## 交付物

| 文件 | 内容 |
|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`（新建，835 行） | 拒绝码常量 / `parseWriteFace` / `parseWriteFaceEntries` / `writeFacesOverlap` / `isWriteFaceOverlap`；§4.2 段级字符模式乘积、§4.3 glob ε-NFA 乘积、§4.4 面级算子 |
| `packages/coding-agent/test/suite/write-face.test.ts`（新建，406 行） | 读冻结语料（只读）+ 92 个断言用例；纯函数、无 provider/凭证 |

导出面（`file:line`）：

- `WRITE_FACE_EMPTY` / `WRITE_FACE_INVALID_ENTRY` / `WRITE_FACE_ESCAPE` / `WRITE_FACE_OUTSIDE_BASE` — `write-face.ts:40-43`
- `WriteFaceGlob` / `WriteFace` / `WriteFaceParseOptions` / `WriteFaceParseResult` / `WriteFaceConflict` / `WriteFaceUnsupported` / `WriteFaceOverlapResult` — `write-face.ts:106-150`
- `parseWriteFace(text, opts)` — `write-face.ts:616`
- `parseWriteFaceEntries(entries, opts, denyEntries?)` — `write-face.ts:635`
- `writeFacesOverlap(a, b)` — `write-face.ts:815`
- `isWriteFaceOverlap(result)` — `write-face.ts:834`

## 验收输出

验收命令（原文）：

```
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts
```

vitest 原文：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

····························································································

 Test Files  1 passed (1)
      Tests  92 passed (92)
   Start at  11:06:24
   Duration  262ms (transform 49ms, setup 0ms, import 70ms, tests 20ms)
```

`--reporter=verbose` 的 92 个用例（名称逐条列出，全部 passed）：

```
 ✓ test/suite/write-face.test.ts > write_face corpus — parse (16 rows) > P01 single entry
 ✓ … > write_face corpus — parse (16 rows) > P02 missing head
 ✓ … > P03 dash only
 ✓ … > P04 present but empty
 ✓ … > P05 two entries
 ✓ … > P06 empty entries ignored
 ✓ … > P07 strip leading ./
 ✓ … > P08 collapse empty segment
 ✓ … > P09 backslash is a separator
 ✓ … > P10 strip trailing slash
 ✓ … > P11 collapse repeated **
 ✓ … > P12 absolutize inside base
 ✓ … > P13 negated entry refused
 ✓ … > P14 parent escape refused
 ✓ … > P15 absolute outside base refused
 ✓ … > P16 quoted comma refused
 ✓ … > write_face corpus — overlap (49 rows) > sanity: counts and kind distribution are frozen
 ✓ … > V01 … V48（49 行逐条 passed；V04 拆 ci/cs 两行）
 ✓ … > hard acceptance points (§4.3, card requirement 2) > 6 条
 ✓ … > conservative fallbacks (§3.2, card requirement 4) > 7 条
 ✓ … > deny never participates (§3.2) > 2 条
 ✓ … > §3.3 three states and normalization > 8 条
 ✓ … > bare minimatch is not the contract (evidence: §3.1 vs minimatch) > 2 条
```

硬验收点与保守回退实测（`[VERIFY]` 原样输出）：

```
[VERIFY] W02-hard-1  writeFacesOverlap(parse(["**"]), parse(["x/y"])) = {"sample":"x/y","rule":"**","other":"x/y","reason":"write-face-overlap"}
[VERIFY] W02-hard-2  writeFacesOverlap(parse(["a/**/b"]), parse(["a/b"])) = {"sample":"a/b","rule":"a/**/b","other":"a/b","reason":"write-face-overlap"}
[VERIFY] W02-a-star-includes-a  parse(["a/**"]) x parse(["a"]) = {"sample":"a","rule":"a/**","other":"a"}
[VERIFY] W02-a-star-slash-star  parse(["a/**/*"]) x parse(["a"]) = null
[VERIFY] W02-deny-monotone  parse(["a/**"], deny=["a/**"]) x parse(["a/b"]) = {"sample":"a/b",...}  (与无 deny 相同)
[VERIFY] W02-fb-extglob  parse(["a/+(b)/**"]) x parse(["a/b"]) = {"unsupported":"unsupported-syntax"}
[VERIFY] W02-fb-illegal-class  parse(["a/[bc/**"]) x parse(["a/b"]) = {"unsupported":"unsupported-syntax"}
[VERIFY] W02-fb-token-run  parse(["a/" + "*"*300]) x parse(["a/b"]) = {"unsupported":"unsupported-syntax"}
[VERIFY] W02-fb-state-limit  parse(["x/"*300]) x parse(["x/"*300]) = {"unsupported":"glob-product-state-limit"}
[VERIFY] W02-fb-base  face(base=REPO) x face(base=$OUTSIDE) = {"unsupported":"incomparable-base"}
[VERIFY] W02-fb-case-mode  face(base="/repo", cs) x face(base="/repo", ci) = {"unsupported":"incomparable-case-mode"}
[VERIFY] W02-typecheck: tsgo --noEmit -p tsconfig.json → 0 条 write-face 相关错误
```

类型检查命令与结果（可选项；卡里的 `tsconfig.json` 在本包不存在，改用仓库根 `tsconfig.json`）：

```
cd H:/git/Multi-Workers; node node_modules/@typescript/native-preview/bin/tsgo.js --noEmit -p tsconfig.json
# 过滤 write-face：0 命中
```

## 与 Python 侧的同语料对照表

两侧驱动同一份冻结语料 `packages/multi-workers/test/fixtures/write-face-corpus.json`（只读）。Python 侧模块 `packages/multi-workers/autopilot/write_face.py`（W-01 在飞产物，本卡只读它）；驱动方式与 TS 侧同构：

- `parse` 行：`head` 逐行拼成 task 头文本，`$REPO` = 仓根、`$OUTSIDE` = 仓外临时目录；TS `parseWriteFace` / Python `parse_write_face`。
- `overlap` 行：以缩进块列表 `write_face:\n  - <entry>`（`a_deny` 走 `write_face_deny:` 块）构造同一个面；TS `parseWriteFaceEntries`（entries 数组原生形态）/ Python `parse_write_face`，再各自 `writeFacesOverlap` / `overlap`。
- Python 列实测于 2026-10-14，脚本：临时目录 `wf-py-parity.py`（`sys.path` 指向 `packages/multi-workers`，`base` = 仓根）。
- 逐行断言：`TS` 列与 `Python` 列必须相等（kind；reject 行比 code）。结果 **65 行 0 mismatch**，两列逐行相等。

| row | corpus expects | TS | Python | equal |
|---|---|---|---|---|
| P01 single entry | entries | declared | declared | yes |
| P02 missing head | unknown | undeclared | undeclared | yes |
| P03 dash only | unknown | undeclared | undeclared | yes |
| P04 present but empty | reject | rejected | rejected | yes |
| P05 two entries | entries | declared | declared | yes |
| P06 empty entries ignored | entries | declared | declared | yes |
| P07 strip leading ./ | entries | declared | declared | yes |
| P08 collapse empty segment | entries | declared | declared | yes |
| P09 backslash is a separator | entries | declared | declared | yes |
| P10 strip trailing slash | entries | declared | declared | yes |
| P11 collapse repeated ** | entries | declared | declared | yes |
| P12 absolutize inside base | entries | declared | declared | yes |
| P13 negated entry refused | reject | rejected | rejected | yes |
| P14 parent escape refused | reject | rejected | rejected | yes |
| P15 absolute outside base refused | reject | rejected | rejected | yes |
| P16 quoted comma refused | reject | rejected | rejected | yes |
| V01 deep segment | overlap | overlap | overlap | yes |
| V02 first segment differs | none | none | none | yes |
| V03 trailing /** includes the bare dir | overlap | overlap | overlap | yes |
| V04-ci case folded | overlap | overlap | overlap | yes |
| V04-cs case sensitive | none | none | none | yes |
| V05 mid ** zero segments | overlap | overlap | overlap | yes |
| V06 star does not cross slash | none | none | none | yes |
| V07 single segment wildcard | overlap | overlap | overlap | yes |
| V08 mid ** consumes a suffix | overlap | overlap | overlap | yes |
| V09 mid ** zero segments | overlap | overlap | overlap | yes |
| V10 bare ** matches everything | overlap | overlap | overlap | yes |
| V11 bare ** covers dot segments | overlap | overlap | overlap | yes |
| V12 live evidence shape | overlap | overlap | overlap | yes |
| V13 literal is an exact node | none | none | none | yes |
| V14 same file | overlap | overlap | overlap | yes |
| V15 ** covers a file | overlap | overlap | overlap | yes |
| V16 different extension | none | none | none | yes |
| V17 identity | overlap | overlap | overlap | yes |
| V18 disjoint extensions | none | none | none | yes |
| V19 non empty intersection | overlap | overlap | overlap | yes |
| V20 brace alternation | overlap | overlap | overlap | yes |
| V21 star inside segment | overlap | overlap | overlap | yes |
| V22 qmark is one char | overlap | overlap | overlap | yes |
| V23 class membership | overlap | overlap | overlap | yes |
| V24 negated class | none | none | none | yes |
| V25 first segment anchoring | none | none | none | yes |
| V26 parent escape refused on side b | reject | write-face-escape | write-face-escape | yes |
| V27 absolute path relativized | overlap | overlap | overlap | yes |
| V28 leading ./ stripped | overlap | overlap | overlap | yes |
| V29 empty segment collapsed | overlap | overlap | overlap | yes |
| V30 trailing slash literal stays exact | none | none | none | yes |
| V31 backslash separator | overlap | overlap | overlap | yes |
| V32 negation refused on side a | reject | write-face-invalid-entry | write-face-invalid-entry | yes |
| V33 trailing /** bare dir (short form) | overlap | overlap | overlap | yes |
| V34 deep descent | overlap | overlap | overlap | yes |
| V35 subset relation | overlap | overlap | overlap | yes |
| V36 /** requires one segment | none | none | none | yes |
| V37 deny does not subtract (whole) | overlap | overlap | overlap | yes |
| V38 deny does not subtract (exact) | overlap | overlap | overlap | yes |
| V39 segment boundary not prefix | none | none | none | yes |
| V40 case folded | overlap | overlap | overlap | yes |
| V41 case sensitive | none | none | none | yes |
| V42 dot segments are ordinary | overlap | overlap | overlap | yes |
| V43 present but empty refused | reject | write-face-empty | write-face-empty | yes |
| V44 undeclared is serial-only | serial_only | serial_only | serial_only | yes |
| V45 literal is not a directory | none | none | none | yes |
| V46 basic shape | overlap | overlap | overlap | yes |
| V47 repeated ** collapsed | overlap | overlap | overlap | yes |
| V48 trailing /** bare dir (long form) | overlap | overlap | overlap | yes |

```
rows=65 mismatches=[]
```

注意：语料只锁 `kind`（+ witness glob-free），不锁 witness 文本；上表两列在 reject 行比的是**稳定 code**，在 overlap 行比的是 kind。两侧 witness 文本可不同（如 V35 TS `a/x` / Python `a/x` 恰好一致，V17 TS `a` / Python `a` 恰好一致），不影响逐行相等。

## 裸 minimatch 差异对照

语义基准是 minimatch 的**单路径匹配**，但交集运算 minimatch 没有；下面这些向量里，`minimatch(witness, pattern)` 会给出与 §3.1 相反的结论——这正是"不能把交集实现成对 minimatch 的重复调用"的证据。脚本：临时目录 `wf-minimatch.mjs`（`minimatch` 10.2.5，ESM 入口）遍历全部 overlap 行，对算子返回的 witness 逐一做裸调用。

自动扫出的差异行（witness 由 TS 算子返回）：

| row | witness | pattern | bare minimatch | §3.1 | 原因 |
|---|---|---|---|---|---|
| V03 | `packages/x` | `packages/x/**` | false | overlap | 裸 minimatch 的尾 `/**` 不含裸目录（D-2；仓内两处消费者各打补丁） |
| V04-ci | `packages/x` | `packages/x/**` | false | overlap | 同上 |
| V04-ci | `packages/x` | `packages/X/**` | false | overlap | 裸 minimatch 默认大小写敏感；§3.1 用显式 `caseInsensitive`（D-1/D-14） |
| V11 | `.agenticdoc/k/x.md` | `**` | false | overlap | 裸 minimatch 默认 `dot:false`；§3.1 取 `dot:true`（D-3） |
| V17 | `a` | `a/**` | false | overlap | 同 V03 |
| V17 | `a` | `a/**` | false | overlap | 同 V03 |
| V33 | `a` | `a/**` | false | overlap | 同 V03 |
| V40 | `a/B` | `A/B` | false | overlap | 大小写折半（D-1/D-14） |
| V42 | `a/.x/b.ts` | `a/**/*.ts` | false | overlap | `dot:false`（D-3） |
| V48 | `a/b` | `a/b/**` | false | overlap | 同 V03 |

补充：词法归一向量（语料只给原始声明串，witness 已经是归一后的路径，所以自动扫描扫不到；实测裸调用）：

| 语料向量 | 裸 minimatch 实测 | §3.1 | 原因 |
|---|---|---|---|
| V28 `./packages/x/y.ts` | `minimatch("./packages/x/y.ts", "packages/x/**") = false` | overlap | minimatch 自身不归一前导 `./`（D-10），算子必须先显式归一 |
| V31 `src\x\**` | `minimatch("src/x/y.ts", "src\\x\\**") = false` | overlap | minimatch 把模式里的 `\` 当转义（D-9），算子按"一律分隔符"处理 |

反例（两侧一致，说明基准确实是 minimatch 的段语义，而不是 `fnmatch` 的 `*` 跨 `/`）：

```
minimatch("a/b/c.ts", "a/*.ts") = false   # 与 §3.1 V06 的 none 一致；Python fnmatch 会给 True（D-14 核心分叉）
minimatch("a/b.ts", "a/**/*.ts") = true   # 与 §3.1 V05 的 overlap 一致；fnmatch 给 False
minimatch("packages/x/y.ts", "packages*") = false  # 与 §3.1 的段边界一致；fnmatch 给 True
```

结论：minimatch 只能做"单路径 vs 单模式"的点对照（本卡 `write-face.test.ts` 的 `bare minimatch is not the contract` 用例把它固化成断言），glob×glob 的交集必须由 `write-face.ts` 的 ε-NFA 乘积判定。

## 残留与未验证

- **R-1** 只做词法判定。symlink/junction 可使两条词法不相交的面在磁盘上指向同一文件（设计 RQ-D1 §6 R-1）；运行期 realpath 复算属 W-05（B2），不在本卡。
- **R-2** 段级 `segOverlap` 的字符类/brace 组合在 >256 字符、深嵌套 brace 下只保证"触发 unsupported 保守回退"，未做穷举性能/正确性对拍（与 Python 侧同策略：超限即 unsupported）。
- **R-3** witness 的**具体文本**未与 Python 侧对齐（语料不锁文本）。若下游（B1 的 refusal 样例）希望两侧打印逐字相同的样例路径，需要在 B0 收口时另加一条 witness 对齐约束；当前只保证 kind 与 glob-free。
- **R-4** `parseWriteFace` 的 head 检测按 Python 镜像扫全文档（不限定 header region），并支持缩进块列表；一个位于 task **正文**的 `write_face:` 行也会被采到。task.md 约定头在前，且 B1 渲染器只会写头部；未做"正文误命中"反证。
- **R-5** `@(a|b)` 按 §3.1 语法展开（不是保守回退），但语料无 `@()` 行；`+()`/`*()`/`?()`/`!()` 归 unsupported。`{a}`（单分支 brace）在两侧都判 unsupported（与 minimatch 的"字面 `{a}`"不同），语料未覆盖。
- **R-6** 本卡未改任何下游接线：`write_face` 尚未被 `pm/task-dispatcher.ts` / `pm/ui-bridge.ts` / `worker/worker-mode.ts` 使用（B1/B2 的卡负责）。因此"上游渲染格式 == 本模块 head 语法"只在语料与人工样例上验证，端到端对拍属 W-07。
- **R-7** 未跑根 `npm run check`（卡禁止）；只跑了 `tsgo -p tsconfig.json` 的过滤检查与包内 vitest。biome 格式未单独跑，但代码按仓内 tab/双引号风格书写。

## 上下文来源

- 冻结契约：`.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md` §3.1/§3.2/§3.3/§4.2/§4.3/§4.4。
- 决策：`.agenticdoc/mw-write-face-guard/design.md` D-001/D-006/D-009；批次：`plan.md` §1（W-02 独占这两个文件）。
- 冻结语料：`packages/multi-workers/test/fixtures/write-face-corpus.json`（只读；`counts.parse=16`、`counts.overlap=49`、`protocol` 占位符 `$REPO`/`$OUTSIDE`）。
- Python 对照模块：`packages/multi-workers/autopilot/write_face.py`（W-01 在飞产物，本卡只读；对照脚本在临时目录运行，未改任何 Python 文件）。
- 既有"单路径 vs 模式"实现（只作反例证据，未复用）：`worker/read-scope.ts:89/118/141`、`worker/worker-mode.ts:1564/1584-1600`、`packages/multi-workers/autopilot/xkey.py:1075-1084`。
- 测试基座：`packages/coding-agent/test/suite/autopilot-config-parity.test.ts` 的"读 `packages/multi-workers/test/fixtures/*.json` + `fileURLToPath`"惯例；vitest 配置 `packages/coding-agent/vitest.config.ts`。

## 改动历史

| 文件 | 位置 | before → after |
|---|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts` | 全文件（835 行） | 新建（`write-face.ts:1-835`）：拒绝码常量 `:40-43`、数据模型 `:106-150`、head 检测/归一 `:250-460`、brace/@() 展开 `:300-390`、charpat 分词 `:400-590`、§4.2 段级乘积 `:660-750`、§4.3 ε-NFA 乘积 `:760-810`、§4.4 面级算子 `:815-836` |
| `packages/coding-agent/test/suite/write-face.test.ts` | 全文件（406 行） | 新建（`write-face.test.ts:1-406`）：语料加载/占位符 `:33-40`、corpus 类型 `:42-66`、parse 16 行 `:95-119`、overlap 49 行 `:121-168`、硬验收点 `:170-213`、保守回退 `:215-276`、deny 单调性 `:278-305`、三态与归一 `:307-369`、裸 minimatch 对照 `:371-405` |

```
[VERIFY] W02-change-history: git status 只含本卡两个文件的新增（untracked）
         packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts
         packages/coding-agent/test/suite/write-face.test.ts
```
