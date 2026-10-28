# W-05 回执：TS 侧 `write_face` 算子与测试对齐扩展冻结语料（D-111 / D-112）

> 卡面：`.agenticdoc/mw-write-face-guard/workers/wfg-i05-operator-ts-fix/task.md`
> 写入面：`packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`、
> `packages/coding-agent/test/suite/write-face.test.ts`（本文件为卡面指定的唯一证据文件）。
> 语料 `packages/multi-workers/test/fixtures/write-face-corpus.json` 只读、未改动。
> Python 侧属并行卡 T-W-I04，本卡未改动 `packages/multi-workers/**` 任何文件。

## 0. 结论

- TS 侧 D-111 overlap 期已修正：先在受支持条目之间求可证冲突，证不出冲突且任一侧有不受支持语法时才 `Unsupported`。
- 测试文件补齐 `unsupported` 的 `expect.kind` 分支，counts 冻结断言更新为 `parse 23 / overlap 58`。
- 验收：`Tests 108 passed (108)`；扩展语料 81 行（parse 23 + overlap 58）全过。
- 与 Python 侧同语料逐行对照：**81/81 行 verdict 相等，0 mismatch**。
- parse 期既有性质保住：V52–V56 的硬违规优先与顺序无关全部通过；V37/V38 deny 不参与判定通过。

---

## 1. 修正前后实测对照（V57 / V49 / V50 / V51）

### 1.1 算子级 before/after

方法：把修正前的 `writeFacesOverlap` 原样回填到当前模块的一份临时副本
`write-face-before.ts`（只回填这一个函数，其余字节相同），再用同一个探针把
`corpus.overlap` 中 V49–V57 行分别喂给 before/after 模块。语料数组按「块列表载体」
（每个数组元素一行 `- entry`）喂入，避免把数组元素重新按逗号切分（D-112 的切分只作用于
单行头部值）。base=`H:/git/Multi-Workers`，`$OUTSIDE` 替换为临时目录。

命令（临时目录内）：

```bash
node H:/git/Multi-Workers/node_modules/tsx/dist/cli.mjs probe_before_after.ts
```

原文输出：

```text
V49 illegal class with nothing provable	before={"unsupported":"unsupported-syntax"}	after={"unsupported":"unsupported-syntax"}
V50 extglob negation on side b	before={"unsupported":"unsupported-syntax"}	after={"unsupported":"unsupported-syntax"}
V51 unclosed brace with nothing provable	before={"unsupported":"unsupported-syntax"}	after={"unsupported":"unsupported-syntax"}
V52 hard escape wins over an earlier unsupported entry	before=parse:{"kind":"rejected","code":"write-face-escape"}	after=parse:{"kind":"rejected","code":"write-face-escape"}
V53 same face, hard escape first (order independence)	before=parse:{"kind":"rejected","code":"write-face-escape"}	after=parse:{"kind":"rejected","code":"write-face-escape"}
V54 hard invalid-entry wins over an earlier unsupported entry	before=parse:{"kind":"rejected","code":"write-face-invalid-entry"}	after=parse:{"kind":"rejected","code":"write-face-invalid-entry"}
V55 hard outside-base wins over an earlier unsupported entry	before=parse:{"kind":"rejected","code":"write-face-outside-base"}	after=parse:{"kind":"rejected","code":"write-face-outside-base"}
V56 same face, hard outside-base first (order independence)	before=parse:{"kind":"rejected","code":"write-face-outside-base"}	after=parse:{"kind":"rejected","code":"write-face-outside-base"}
V57 provable conflict wins over an unsupported entry	before={"unsupported":"unsupported-syntax"}	after={"sample":"src/x.ts","rule":"src/x.ts","other":"src/x.ts","reason":"write-face-overlap"}
```

逐项读法：

| 行 | 语料期望 | 修正前算子输出 | 修正后算子输出 | 变化点 |
|---|---|---|---|---|
| `V57` | `overlap`（glob-free witness） | `{"unsupported":"unsupported-syntax"}` | `{"sample":"src/x.ts",...}` | overlap 期优先级（本卡唯一语义改动） |
| `V49` | `unsupported` | `{"unsupported":"unsupported-syntax"}` | 同左 | 算子本来就对；红的是测试缺分支 |
| `V50` | `unsupported` | `{"unsupported":"unsupported-syntax"}` | 同左 | 同上 |
| `V51` | `unsupported` | `{"unsupported":"unsupported-syntax"}` | 同左 | 同上 |
| `V52`–`V56` | `reject:<code>` | `reject:<code>`（parse 期不变） | 同左 | 保住既有性质，未回归 |

### 1.2 验收命令 before/after 原文

修正前（当前工作树首次实测，测试文件尚未补 `unsupported` 分支、counts 仍是 16/49）：

命令：

```bash
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts
```

原文（节选，5 红）：

```text
 FAIL  test/suite/write-face.test.ts > write_face corpus — overlap (49 rows) > sanity: counts and kind distribution are frozen
AssertionError: expected 23 to be 16 // Object.is equality
- Expected
+ Received
- 16
+ 23
 ❯ test/suite/write-face.test.ts:123:31
    121| describe("write_face corpus — overlap (49 rows)", () => {
    122| 	it("sanity: counts and kind distribution are frozen", () => {
    123| 		expect(CORPUS.counts.parse).toBe(16);
 FAIL  test/suite/write-face.test.ts > write_face corpus — overlap (49 rows) > V49 illegal class with nothing provable
 FAIL  test/suite/write-face.test.ts > write_face corpus — overlap (49 rows) > V50 extglob negation on side b
 FAIL  test/suite/write-face.test.ts > write_face corpus — overlap (49 rows) > V51 unclosed brace with nothing provable
AssertionError: expected 'unsupported' to be 'overlap' // Object.is equality
 ❯ test/suite/write-face.test.ts:158:28
 FAIL  test/suite/write-face.test.ts > write_face corpus — overlap (49 rows) > V57 provable conflict wins over an unsupported entry
AssertionError: expected false to be true // Object.is equality
 ❯ test/suite/write-face.test.ts:161:58
 Test Files  1 failed (1)
      Tests  5 failed | 103 passed (108)
```

修正后见 §2。

---

## 2. 全语料通过计数与实跑原文

### 2.1 TS 验收命令

命令：

```bash
cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts
```

原文：

```text
 RUN  v4.1.9 H:/git/Multi-Workers

············································································································

 Test Files  1 passed (1)
      Tests  108 passed (108)
```

覆盖：语料 23 parse + 58 overlap = 81 行全过；另有 §4.3/§3.2/§3.3/deny/minimatch 对照等 27 个边界用例。

### 2.2 类型检查（卡面允许的 `tsgo`，只看本模块）

命令（仓根）：

```bash
node node_modules/@typescript/native-preview/bin/tsgo.js --noEmit -p tsconfig.json
```

结果：`EXIT:0`，无输出；本模块（`write-face.ts` / `write-face.test.ts`）0 error。未跑根 `npm run check`。

### 2.2b Biome（仅本卡写入面两文件，局部替代根 `npm run check`）

命令：

```bash
node node_modules/@biomejs/biome/bin/biome check packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts packages/coding-agent/test/suite/write-face.test.ts
```

结果：`Checked 2 files ... No fixes applied.`（exit 0）。首次跑仅报两文件既有格式债务（W-02
遗留：长行未折、import 未排序），**本卡改动区域无任何条目**；已用 `biome format --write` +
`biome check --write` 同步两文件，未修任何 lint 语义规则。

### 2.3 Python 侧同语料（只读观测，属 T-W-I04）

命令：

```bash
cd packages/multi-workers; python -m pytest test_write_face.py -q
```

原文：

```text
........................................................................ [ 56%]
........................................................                 [100%]
128 passed in 0.21s
```

### 2.4 跨语言对照驱动

驱动约定（两侧完全一致）：

- parse 行：直接取语料 `head`（多行文本），走 `parseWriteFace(text)` / `parse_write_face(text)`，测 D-112 单行切分；
- overlap 行：把语料数组渲染成块列表载体（每个元素一行），走同一个公开 parser，使数组元素不被再次按逗号切分；
- base 两侧同为仓根，`$REPO`/`$OUTSIDE` 各自替换为绝对路径；verdict 只取契约钉死的 kind（`entries`/`unknown`/`reject:<code>`/`serial_only`/`overlap`/`none`/`unsupported`，reject 带 side），不比较未钉死的 witness 文本/unsupported reason。

命令（临时目录内，TS 侧用仓内 `tsx` 加载未编译的 `write-face.ts`）：

```bash
python py_drive.py py.txt
node H:/git/Multi-Workers/node_modules/tsx/dist/cli.mjs ts_drive.ts ts.txt
python make_table.py   # 行数对齐 + 逐行相等断言
```

驱动原文：

```text
python: 81 rows -> py.txt
ts: 81 rows -> ts.txt
rows 81 mismatches 0
```

---

## 3. 与 Python 侧同语料逐行对照表（81 行，逐行相等）

| row | TS verdict | Python verdict | equal |
|---|---|---|---|
| P01 single entry | `entries:["packages/x/**"]` | `entries:["packages/x/**"]` | yes |
| P02 missing head | `unknown` | `unknown` | yes |
| P03 dash only | `unknown` | `unknown` | yes |
| P04 present but empty | `reject:write-face-empty` | `reject:write-face-empty` | yes |
| P05 two entries | `entries:["a/**","b/c.ts"]` | `entries:["a/**","b/c.ts"]` | yes |
| P06 empty entries ignored | `entries:["a/**"]` | `entries:["a/**"]` | yes |
| P07 strip leading ./ | `entries:["packages/x/**"]` | `entries:["packages/x/**"]` | yes |
| P08 collapse empty segment | `entries:["packages/x/**"]` | `entries:["packages/x/**"]` | yes |
| P09 backslash is a separator | `entries:["src/x/**"]` | `entries:["src/x/**"]` | yes |
| P10 strip trailing slash | `entries:["packages/x"]` | `entries:["packages/x"]` | yes |
| P11 collapse repeated ** | `entries:["a/**"]` | `entries:["a/**"]` | yes |
| P12 absolutize inside base | `entries:["packages/x/**"]` | `entries:["packages/x/**"]` | yes |
| P13 negated entry refused | `reject:write-face-invalid-entry` | `reject:write-face-invalid-entry` | yes |
| P14 parent escape refused | `reject:write-face-escape` | `reject:write-face-escape` | yes |
| P15 absolute outside base refused | `reject:write-face-outside-base` | `reject:write-face-outside-base` | yes |
| P16 quoted comma refused | `reject:write-face-invalid-entry` | `reject:write-face-invalid-entry` | yes |
| P17 illegal class is not a parse error | `entries:["src/[a-"]` | `entries:["src/[a-"]` | yes |
| P18 extglob negation is not a parse error | `entries:["src/!(x)"]` | `entries:["src/!(x)"]` | yes |
| P19 extglob plus() is not a parse error | `entries:["src/+(x)"]` | `entries:["src/+(x)"]` | yes |
| P20 extglob at() is not a parse error | `entries:["src/@(x)"]` | `entries:["src/@(x)"]` | yes |
| P21 unclosed brace is not a parse error | `entries:["src/{a","b"]` | `entries:["src/{a","b"]` | yes |
| P22 unsupported entry keeps position next to a valid one | `entries:["src/[a-","src/ok.ts"]` | `entries:["src/[a-","src/ok.ts"]` | yes |
| P23 comma is never pattern content | `entries:["src/[a-","src/b].ts","src/ok.ts"]` | `entries:["src/[a-","src/b].ts","src/ok.ts"]` | yes |
| V01 deep segment | `overlap` | `overlap` | yes |
| V02 first segment differs | `none` | `none` | yes |
| V03 trailing /** includes the bare dir | `overlap` | `overlap` | yes |
| V04-ci case folded | `overlap` | `overlap` | yes |
| V04-cs case sensitive | `none` | `none` | yes |
| V05 mid ** zero segments | `overlap` | `overlap` | yes |
| V06 star does not cross slash | `none` | `none` | yes |
| V07 single segment wildcard | `overlap` | `overlap` | yes |
| V08 mid ** consumes a suffix | `overlap` | `overlap` | yes |
| V09 mid ** zero segments | `overlap` | `overlap` | yes |
| V10 bare ** matches everything | `overlap` | `overlap` | yes |
| V11 bare ** covers dot segments | `overlap` | `overlap` | yes |
| V12 live evidence shape | `overlap` | `overlap` | yes |
| V13 literal is an exact node | `none` | `none` | yes |
| V14 same file | `overlap` | `overlap` | yes |
| V15 ** covers a file | `overlap` | `overlap` | yes |
| V16 different extension | `none` | `none` | yes |
| V17 identity | `overlap` | `overlap` | yes |
| V18 disjoint extensions | `none` | `none` | yes |
| V19 non empty intersection | `overlap` | `overlap` | yes |
| V20 brace alternation | `overlap` | `overlap` | yes |
| V21 star inside segment | `overlap` | `overlap` | yes |
| V22 qmark is one char | `overlap` | `overlap` | yes |
| V23 class membership | `overlap` | `overlap` | yes |
| V24 negated class | `none` | `none` | yes |
| V25 first segment anchoring | `none` | `none` | yes |
| V26 parent escape refused on side b | `reject:b:write-face-escape` | `reject:b:write-face-escape` | yes |
| V27 absolute path relativized | `overlap` | `overlap` | yes |
| V28 leading ./ stripped | `overlap` | `overlap` | yes |
| V29 empty segment collapsed | `overlap` | `overlap` | yes |
| V30 trailing slash literal stays exact | `none` | `none` | yes |
| V31 backslash separator | `overlap` | `overlap` | yes |
| V32 negation refused on side a | `reject:a:write-face-invalid-entry` | `reject:a:write-face-invalid-entry` | yes |
| V33 trailing /** bare dir (short form) | `overlap` | `overlap` | yes |
| V34 deep descent | `overlap` | `overlap` | yes |
| V35 subset relation | `overlap` | `overlap` | yes |
| V36 /** requires one segment | `none` | `none` | yes |
| V37 deny does not subtract (whole) | `overlap` | `overlap` | yes |
| V38 deny does not subtract (exact) | `overlap` | `overlap` | yes |
| V39 segment boundary not prefix | `none` | `none` | yes |
| V40 case folded | `overlap` | `overlap` | yes |
| V41 case sensitive | `none` | `none` | yes |
| V42 dot segments are ordinary | `overlap` | `overlap` | yes |
| V43 present but empty refused | `reject:a:write-face-empty` | `reject:a:write-face-empty` | yes |
| V44 undeclared is serial-only | `serial_only` | `serial_only` | yes |
| V45 literal is not a directory | `none` | `none` | yes |
| V46 basic shape | `overlap` | `overlap` | yes |
| V47 repeated ** collapsed | `overlap` | `overlap` | yes |
| V48 trailing /** bare dir (long form) | `overlap` | `overlap` | yes |
| V49 illegal class with nothing provable | `unsupported` | `unsupported` | yes |
| V50 extglob negation on side b | `unsupported` | `unsupported` | yes |
| V51 unclosed brace with nothing provable | `unsupported` | `unsupported` | yes |
| V52 hard escape wins over an earlier unsupported entry | `reject:a:write-face-escape` | `reject:a:write-face-escape` | yes |
| V53 same face, hard escape first (order independence) | `reject:a:write-face-escape` | `reject:a:write-face-escape` | yes |
| V54 hard invalid-entry wins over an earlier unsupported entry | `reject:a:write-face-invalid-entry` | `reject:a:write-face-invalid-entry` | yes |
| V55 hard outside-base wins over an earlier unsupported entry | `reject:a:write-face-outside-base` | `reject:a:write-face-outside-base` | yes |
| V56 same face, hard outside-base first (order independence) | `reject:a:write-face-outside-base` | `reject:a:write-face-outside-base` | yes |
| V57 provable conflict wins over an unsupported entry | `overlap` | `overlap` | yes |

`make_table.py` 对每行断言两侧 verdict 字符串相等；上表 81 行全部 `yes`，脚本输出 `mismatches 0`。

---

## 改动历史

### 4.1 `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`

`L809-811`（`writeFacesOverlap` doc 注释）before：

```ts
 * Returns a conflict with a concrete glob-free witness, `null` for a
 * lexically-provable empty intersection, or `{ unsupported }` for any
 * conservative fallback — callers MUST treat `unsupported` as overlap.
```

`L838-841` after（追加 D-111 优先级）：

```ts
 * D-111 precedence: a provable conflict among *supported* entries wins; a
 * conservative fallback (`{ unsupported }`) is returned only when no conflict
 * is provable and at least one side carries syntax the product cannot decide.
 * Callers MUST treat `unsupported` as overlap.
```

`L821-830`（函数体循环）before：

```ts
	for (const ga of a.allow) {
		for (const gb of b.allow) {
			if (ga.unsupported || gb.unsupported) return { unsupported: "unsupported-syntax" };
			const witness = globsOverlap(ga.segments, gb.segments, caseInsensitive);
			if (witness.kind === "unsupported") return { unsupported: witness.reason };
			if (witness.kind === "none") continue;
			return { sample: witness.value.join("/"), rule: ga.text, other: gb.text, reason: "write-face-overlap" };
		}
	}
	return null;
```

`L849-869` after（deferred 先证冲突）：

```ts
	// D-111 overlap phase: prove a conflict first. A pair that cannot be decided
	// (unsupported syntax, or a state-machine fallback) is deferred, never
	// short-circuits the search, so a provable conflict always wins.
	let deferred: string | null = null;
	for (const ga of a.allow) {
		for (const gb of b.allow) {
			if (ga.unsupported || gb.unsupported) {
				deferred = deferred ?? "unsupported-syntax";
				continue;
			}
			const witness = globsOverlap(ga.segments, gb.segments, caseInsensitive);
			if (witness.kind === "unsupported") {
				deferred = deferred ?? witness.reason;
				continue;
			}
			if (witness.kind === "none") continue;
			return { sample: witness.value.join("/"), rule: ga.text, other: gb.text, reason: "write-face-overlap" };
		}
	}
	if (deferred !== null) return { unsupported: deferred };
	return null;
```

公开 API 名称/返回类型形状不变（`parseWriteFace` / `parseWriteFaceEntries` / `writeFacesOverlap` /
`isWriteFaceOverlap` / `WriteFaceGlob` 等均未改签名）；无新依赖、无 `any`、无可擦除语法之外构造。

### 4.2 `packages/coding-agent/test/suite/write-face.test.ts`

`L5-8` before：

```ts
 * (read-only) is the single contract both language sides must satisfy: 16
 * `parse` rows and 49 `overlap` rows. `overlap` rows only pin the conclusion
 * kind (`overlap` / `none` / `reject` / `serial_only`) plus "the witness is
 * glob-free", so the two sides do not have to agree on the witness text.
```

`L5-10` after：

```ts
 * (read-only) is the single contract both language sides must satisfy: 23
 * `parse` rows and 58 `overlap` rows. `overlap` rows only pin the conclusion
 * kind (`overlap` / `none` / `reject` / `serial_only` / `unsupported`) plus
 * "the witness is glob-free", so the two sides do not have to agree on the
 * witness text. D-111: at intersection time a provable conflict wins over an
 * unsupported-syntax entry; `unsupported` means "cannot decide".
```

`L95` before：

```ts
describe("write_face corpus — parse (16 rows)", () => {
```

`L104` after：

```ts
describe("write_face corpus — parse (23 rows)", () => {
```

`L121` before：

```ts
describe("write_face corpus — overlap (49 rows)", () => {
```

`L130` after：

```ts
describe("write_face corpus — overlap (58 rows)", () => {
```

`L122-130` before：

```ts
	it("sanity: counts and kind distribution are frozen", () => {
		expect(CORPUS.counts.parse).toBe(16);
		expect(CORPUS.counts.overlap).toBe(49);
		expect(CORPUS.parse.length).toBe(16);
		expect(CORPUS.overlap.length).toBe(49);
		const kinds: Record<string, number> = { overlap: 0, none: 0, reject: 0, serial_only: 0 };
		for (const row of CORPUS.overlap) kinds[row.expect.kind] = (kinds[row.expect.kind] ?? 0) + 1;
		expect(kinds).toEqual({ overlap: 32, none: 13, reject: 3, serial_only: 1 });
	});
```

`L131-139` after：

```ts
	it("sanity: counts and kind distribution are frozen", () => {
		expect(CORPUS.counts.parse).toBe(23);
		expect(CORPUS.counts.overlap).toBe(58);
		expect(CORPUS.parse.length).toBe(23);
		expect(CORPUS.overlap.length).toBe(58);
		const kinds: Record<string, number> = { overlap: 0, none: 0, reject: 0, serial_only: 0, unsupported: 0 };
		for (const row of CORPUS.overlap) kinds[row.expect.kind] = (kinds[row.expect.kind] ?? 0) + 1;
		expect(kinds).toEqual({ overlap: 33, none: 13, reject: 8, serial_only: 1, unsupported: 3 });
	});
```

`L154-158` before（在 `none` 分支之后直接要求 overlap）：

```ts
			if (row.expect.kind === "none") {
				expect(result).toBeNull();
				return;
			}
			expect(row.expect.kind).toBe("overlap");
```

`L163-173` after（插入 `unsupported` 分支；overlap 断言下移）：

```ts
			if (row.expect.kind === "none") {
				expect(result).toBeNull();
				return;
			}
			if (row.expect.kind === "unsupported") {
				// §3.2 fallback / D-111: no conflict is provable and at least one
				// side carries unsupported syntax; callers treat this as overlap.
				expect(result !== null && "unsupported" in result).toBe(true);
				return;
			}
			expect(row.expect.kind).toBe("overlap");
```

（`expect(row.expect.kind).toBe("overlap")` 由原 L158 移至现 L173，其后断言不变。）

### 4.3 仅格式化（无语义）

`biome format --write` + `biome check --write`（organizeImports）作用于上述两文件：折行
（如 `ExampleResult` / `CompileResult` 联合类型、`globsOverlap` 签名）与 import 排序。这些均为
W-02 遗留的既有格式债务，非本卡逻辑改动；本卡新增代码（loop 的 deferred 分支）本身不在
biome 报错内。格式化后重跑验收仍为 `Tests 108 passed (108)`、`tsgo` exit 0。

---

## 5. 未覆盖面 / 上报 PM（不在本卡范围）

- **chunk 5.1（未覆盖的跨语言细节，非语料错误）**：状态机级保守回退（如
  `glob-product-state-limit` / `segment-pattern-probe-exhausted`）发生时，TS 侧本次实现选择
  「defer 后继续遍历其余条目」，即仍可能给出可证 `Conflict`；Python 侧 `overlap()` 在
  `_ConservativeUnknown` 上直接返回 `Unsupported`（`write_face.py:936-952` 的 `except` 包住整个
  `for ga`/`for gb` 循环）。语料没有覆盖「一个受支持对触发状态机回退、另一个对可证冲突」的向量，
  因此 81 行对照仍 0 mismatch。按 D-111「先证冲突」的字面，TS 行为更贴合；该差异属 T-W-I04
  的 Python 侧范围，本卡不改，报回 PM 决定是否需要补语料向量。

  已实测该未覆盖向量（`a=[huge,"src/x.ts"]`、`b=[huge,"src/x.ts"]`，`huge="x/"*300+"x"`，块列表载体）：

  ```text
  PY: Unsupported glob-product-state-limit
  TS: {"sample":"src/x.ts","rule":"src/x.ts","other":"src/x.ts","reason":"write-face-overlap"}
  ```
- 未跑根 `npm run check`（卡面硬约束，多 session 全仓 `biome --write`）；类型检查只用 `tsgo`。
- 未改动：冻结语料、Python 侧、`worker-mode.ts`、`ui-bridge.ts`、`read-scope.ts`。

## 6. 复现脚本落点

临时脚本曾位于仓外 `%TEMP%/mw-wf-parity/`：`py_drive.py`、`ts_drive.ts`、`make_table.py`、
`probe_before_after.ts`、`probe_statelimit.ts`、`write-face-before.ts`（回填修正前
`writeFacesOverlap` 的模块副本）。均为仓外临时文件，未进入任何写入面，任务完成后已清理；
§1/§2/§3/§5 的命令与输出即为可复现证据。
