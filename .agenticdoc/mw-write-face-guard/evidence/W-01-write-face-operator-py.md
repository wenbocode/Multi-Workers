# W-01 证据：Python 侧写面交集算子 `autopilot/write_face.py`

- key: mw-write-face-guard
- 卡: `workers/wfg-i01-operator-py-r2/task.md`（card_sha256 `9cd6f01e74b91a1b6adcf9f32e0605db827d7e0388666abf0ca6df3e3bb2ecd4`）
- 角色: 实现（只写允许面两文件 + 本报告）
- 冻结契约: `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md` §3.1/§3.2/§3.3/§4.2/§4.3/§4.4
- 语料（只读）: `packages/multi-workers/test/fixtures/write-face-corpus.json`
- 采集时间: 2026-10-14
- 平台: Windows dev（Python 3.14.3，`sys.platform=win32`）

## TL;DR

1. 新建 `autopilot/write_face.py`（954 行）：`parse_write_face(text, *, base, case_insensitive)` 三态 + `overlap(a, b) -> Conflict | None | Unsupported`。
2. 交集算子按 §4.3 实现为**两条段序列 ε-NFA 的乘积**：`**` 同时有零段 ε 迁移与吞 1 段自环；接受条件 = 到达 `(|A|,|B|)` 且路径至少 1 条消费边（`consumed` 位）。
3. 冻结语料全过：`parse` 16/16、`overlap` 49/49（overlap 32 / none 13 / reject 3 / serial_only 1）。
4. 硬验收点：`globs_overlap(["**"],["x","y"])` 重叠（自环），`globs_overlap(["a/**/b"],["a/b"])` 重叠（零段展开）。
5. witness 为具体路径且 glob-free（`*?[]{}` 全部替换为具体字符；无 `<unknown>` 占位符）。
6. §3.2 保守回退清单逐条有触发点；全部返回 `Unsupported`（或解析期 `Refused`），无静默 `None`。
7. deny 不参与判定：V37/V38 加 deny 前后结论恒为 `Conflict`（单调）。
8. 全程禁用 `fnmatch` / `pathlib`（AST 断言：模块仅 import `__future__`/`dataclasses`/`re`/`collections`/`collections.abc`）。
9. 验收命令 `python -m pytest test_write_face.py -q` = `99 passed`。

## 交付物

| 文件 | 行数 | 内容 |
|---|---|---|
| `packages/multi-workers/autopilot/write_face.py` | 954 | 解析期常量/拒绝码、`parse_write_face`、`overlap`、`globs_overlap`、段级字符模式交集、glob ε-NFA 乘积、§3.2 限制常量 |
| `packages/multi-workers/test_write_face.py` | 368 | 冻结语料驱动（16+49）+ 边界/保守回退/deny 单调性/无 fnmatch 断言 |

导出 API（`autopilot/write_face.py`）：

- 拒绝码常量：`WRITE_FACE_EMPTY` / `WRITE_FACE_INVALID_ENTRY` / `WRITE_FACE_ESCAPE` / `WRITE_FACE_OUTSIDE_BASE`（`:40-43`）
- 保守回退上限常量：`MAX_TOKEN_RUN` / `MAX_GLOB_SEGMENTS` / `MAX_PRODUCT_STATES` / `MAX_SEG_BFS_STATES` / `MAX_BRACE_DEPTH` / `MAX_BRACE_EXPANSIONS`（`:50-55`）
- 数据模型：`WriteFace` / `Undeclared` / `Refused` / `Conflict` / `Unsupported`（`:122-173`）
- `parse_write_face(text, *, base, case_insensitive=False)`（`:636`）
- `overlap(a, b) -> Conflict | None | Unsupported`（`:898`）
- `globs_overlap(entries_a, entries_b, *, case_insensitive=False)`（`:860`，段序列级，用于边界实测）

## 验收输出

验收命令（原文）：`cd packages/multi-workers; python -m pytest test_write_face.py -q`

```
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 0.10s
```

语料全过计数（实测，逐条驱动 corpus JSON）：

```
[VERIFY] corpus-parse: rows=16 kinds={'entries': 9, 'unknown': 2, 'reject': 5}
[VERIFY] corpus-overlap: rows=49 kinds={'overlap': 32, 'none': 13, 'reject': 3, 'serial_only': 1}
```

> `parse` 16/16；`overlap` 49/49（overlap 32 / none 13 / reject 3 / serial_only 1），与 `corpus.counts` 冻结值逐项相等（`test_corpus_counts_frozen`）。

`globsOverlap` 两条硬验收点（§4.3 的两个坑，实测原文）：

```
[VERIFY] B10-bare-double-star-vs-two-segments: a='**' b='x/y' ci=False -> witness=x/y
[VERIFY] B2-mid-double-star-zero-seg: a='a/**/b' b='a/b' ci=False -> witness=a/b
```

## 边界与保守回退

以下均为实测原文（`globs_overlap([a],[b],ci)` / `parse_write_face` 的真实输出）。

### 六组边界

```
[VERIFY] B1-trailing-double-star-includes-bare-dir: a='a/**' b='a' ci=False -> witness=a
[VERIFY] B2-mid-double-star-zero-seg: a='a/**/b' b='a/b' ci=False -> witness=a/b
[VERIFY] B3-mid-double-star-consumes: a='a/**/b' b='a/c/b' ci=False -> witness=a/c/b
[VERIFY] B4-in-segment-double-star-as-star: a='a/**b' b='a/x/b' ci=False -> None
[VERIFY] B5-in-segment-double-star-star: a='a/**b' b='a/xxb' ci=False -> witness=a/xxb
[VERIFY] B6-dot-true: a='**' b='.agenticdoc/k/x.md' ci=False -> witness=.agenticdoc/k/x.md
[VERIFY] B6b-dot-true: a='a/**/*.ts' b='a/.x/b.ts' ci=False -> witness=a/.x/b.ts
[VERIFY] B7-case-insensitive-true: a='a/**' b='A/B' ci=True -> witness=a/B
[VERIFY] B8-case-sensitive-false: a='a/**' b='A/B' ci=False -> None
[VERIFY] B9-star-star-requires-one-seg: a='a/**/*' b='a' ci=False -> None
[VERIFY] B10-bare-double-star-vs-two-segments: a='**' b='x/y' ci=False -> witness=x/y
```

| 组 | 输入 | 期望 | 实测 |
|---|---|---|---|
| `a/**` vs `a` | `a/**` / `a` | 重叠（§3.1 `a/**` 含裸 `a`） | `witness=a` |
| 中段 `**` | `a/**/b` / `a/b`；`a/**/b` / `a/c/b` | 均重叠（零段 + 吞段） | `witness=a/b` / `witness=a/c/b` |
| 段内 `**` | `a/**b` / `a/xxb`；`a/**b` / `a/x/b` | 重叠 / 不重叠（按 `*`，不跨 `/`） | `witness=a/xxb` / `None` |
| `dot:true` | `**` / `.agenticdoc/k/x.md`；`a/**/*.ts` / `a/.x/b.ts` | 均重叠（点段普通化） | `witness=.agenticdoc/k/x.md` / `witness=a/.x/b.ts` |
| win32 大小写两模式 | `a/**` / `A/B`，ci=true；ci=false | 重叠 / 不重叠 | `witness=a/B` / `None` |
| `a/**/*` vs `a` | `a/**/*` / `a` | 不重叠（`*` 段至少需 1 段） | `None` |

补充（段内 `**` 与自环的交叉验证）：`a/**` vs `a/b/c/d.ts`、`a/**` vs `a/**/*`、`a/**/**` vs `a/b`、`a/b/**` vs `a/b`、`packages/**` vs `packagesx/**` 均由语料 V34/V35/V47/V48/V39 覆盖并通过。

### §3.2 保守回退清单逐条命中

```
[VERIFY] F1-extglob-negate: a='!(a|b)' b='x/y' -> Unsupported(reason=unsupported-syntax rule='!(a|b)' other=None)
[VERIFY] F2-extglob-plus: a='+(a|b)' b='x/y' -> Unsupported(reason=unsupported-syntax rule='+(a|b)' other=None)
[VERIFY] F3-extglob-star: a='*(a|b)' b='x/y' -> Unsupported(reason=unsupported-syntax rule='*(a|b)' other=None)
[VERIFY] F4-extglob-qmark: a='?(a|b)' b='x/y' -> Unsupported(reason=unsupported-syntax rule='?(a|b)' other=None)
[VERIFY] F5-invalid-class: a='[abc' b='x/y' -> Unsupported(reason=unsupported-syntax rule='[abc' other=None)
[VERIFY] F6-nested-brace-depth: pattern='{a,{a,{a,{a,{a,{a,{a,{a,{a,{a,p}}}}}}}}}}' -> Unsupported(reason=unsupported-syntax rule='a')
[VERIFY] F7-brace-branch-count: pattern='{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}{a,b}' -> Unsupported(reason=unsupported-syntax rule='aaaaaaaa{a,b}{a,b}{a,b}{a,b}')
[VERIFY] F8-segment-token-length: a='aaaa...(MAX_TOKEN_RUN+4)' b='x/y' -> Unsupported(reason=unsupported-syntax)
[VERIFY] F9-glob-product-states: a='a/a/...(max segs/2)' b='a/a/...(max segs/2)' -> Unsupported(reason=glob-product-state-limit rule=None other=None)
[VERIFY] F10-absolute-outside-base -> Refused(code=write-face-outside-base)
[VERIFY] F11-cross-base -> Unsupported(reason=incomparable-base)
[VERIFY] F12-case-mode-mismatch -> Unsupported(reason=incomparable-case-mode)
[VERIFY] F13-segment-state-limit -> Unsupported(reason=segment-pattern-state-limit)
[VERIFY] F14-segment-probe-exhausted -> Unsupported(reason=segment-pattern-probe-exhausted)
```

| §3.2 条目 | 触发点（实现） | 实测结果 |
|---|---|---|
| 任一侧 face 未声明 | 缺头或 `write_face: -` → `Undeclared`；算子不由调用方传入 | `test_undeclared_is_not_passed_to_overlap`；语料 V44 serial_only |
| extglob 取反 `!(...)` | `_tokenize_segment` 见 `!(` → unsupported；`_scan_bangs` 见 `!(` 记为 extglob 而非裸 `!` 拒绝 | `unsupported-syntax` |
| `+()` / `*()` / `?()` | `_tokenize_segment` 见 `+(`/`*(`/`?(` → unsupported | 同上 |
| 非法 class | `_parse_class` 未闭合 / 空 / 反向区间 → unsupported；`]` 游离亦 unsupported | 同上 |
| 嵌套 brace 深度超限 | `_expand_alts` `depth+1 > MAX_BRACE_DEPTH (8)` | 同上（`test_nested_brace_depth_limit`） |
| brace 分支数超限 | `_expand_alts` 展开数 `> MAX_BRACE_EXPANSIONS (256)` | 同上（`test_brace_expansion_count_limit`） |
| 绝对路径且不在同一 base 下 | 解析期 `_to_relative` 返回 None → `write-face-outside-base`；两侧 base 不等 → `incomparable-base` | `Refused(write-face-outside-base)` / `Unsupported(incomparable-base)` |
| 段级交集超长 | `_seg_overlap` `len(tokens) > MAX_TOKEN_RUN (256)`；另 `> MAX_SEG_BFS_STATES (65536)` | F8 输入构造 = `"a" * (MAX_TOKEN_RUN + 4)` = 260 个 token 的单段；`test_segment_pattern_length_limit` → `Unsupported`（`unsupported-syntax`）；F13 `test_segment_pattern_state_limit` → `segment-pattern-state-limit` |
| 段内探测池耗尽 | `_common_char` 双 neg-class 且 `_PROBE` 无公共字符 | `Unsupported(segment-pattern-probe-exhausted)` |
| glob 乘积状态超限 | `_globs_overlap` `(|A|+1)*(|B|+1) > MAX_PRODUCT_STATES (65536)` | F9 输入构造 = `"/".join(["a"] * (MAX_GLOB_SEGMENTS // 2))` = 每侧 256 段，(256+1)^2 = 66049 > 65536；`test_glob_product_state_limit` → `Unsupported(glob-product-state-limit)` |
| 两侧 `caseInsensitive` 不同 | `overlap` 前置校验 | `Unsupported(incomparable-case-mode)` |

### deny 单调性（V37/V38 对照）

```
[VERIFY] deny=None -> Conflict(sample='a/b' rule='a/**' other='a/b') deny_field=[]
[VERIFY] deny=['a/**'] -> Conflict(sample='a/b' rule='a/**' other='a/b') deny_field=['a/**']
[VERIFY] deny=['a/b'] -> Conflict(sample='a/b' rule='a/**' other='a/b') deny_field=['a/b']
```

结论：`A.deny` 完全遮盖交集（`a/**`）或精确遮盖见证（`a/b`）时，`overlap` 仍返回 `Conflict`；加/删 deny 不改变判定（对 deny 单调），`deny` 仅被解析保留、不参与算子。

### 禁用 fnmatch 的证据

```
[VERIFY] module-imports: __future__, dataclasses, re, collections(deque), collections.abc(Iterable, Sequence)
```

`test_module_never_imports_fnmatch_or_pathlib_match`（AST）：无 `fnmatch`、无 `pathlib`、无 `os` 导入；因此 `fnmatch.fnmatch/fnmatchcase`、`pathlib.PurePath.match`、`os.path.normcase` 均不可能被用于匹配。匹配只走自写状态机 + 标准库 `re`（仅用于头行/盘符正则）。

## 残留与未验证

- **R-1（未验证）**：算子只做词法判定；symlink/junction 会让词法不相交的两面在磁盘上指向同一文件（沿用 RQ-D1 §6 R-1）。运行期 realpath 复算不在本卡。
- **R-2（未验证）**：`@(a|b)` 与 brace 的组合、`{a,b}` 内含 `/` 的展开顺序（`_expand_alts` 深搜顺序）未逐条与 minimatch 对拍；语料只覆盖 V20（`a/{b,c}/**`）一例。
- **R-3（未验证）**：段级 neg-class 的见证字符取自 511 字符探测池；池耗尽时保守返回 `Unsupported`，未构造"两条 neg-class 合法但池外才有公共字符"的真实输入（测试用 monkeypatch `_PROBE=()` 证明触发点存在）。
- **R-4（未验证）**：单行 `write_face: a/{b,c}/**` 的逗号分割为 brace-aware（`_split_single_line`）；该行为与"entry 内 `,` 拒绝"（D-8）的边界（brace 外逗号）只用 P16 覆盖，未与 PM 复核是否应显式写进契约。
- **R-5（未预期）**：`globs_overlap` 便捷函数在编译失败（如 `..`）时静默丢弃该 entry（返回 `[]`），它是测试辅助入口，生产调用方应走 `parse_write_face` + `overlap`。
- **未跑**：未跑 `packages/multi-workers` 全量 `python -m pytest -q`（本卡只新增文件、未改既有文件，无回归面）；未跑根 `npm run check`（任务明确禁止）。
- **未覆盖面**：`overlap` 的 `Conflict.rule/other` 字段在 brace 展开后取的是**展开后的** entry 串（`CompiledGlob.entry`），语料只断言 kind 与 witness 的 glob-free，未冻结这两个字段的具体取值。

## 上下文来源

- `.agenticdoc/mw-write-face-guard/workers/wfg-i01-operator-py-r2/task.md`（本卡）
- `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`（§0/§3.1/§3.2/§3.3/§4.2/§4.3/§4.4/§5）
- `.agenticdoc/mw-write-face-guard/design.md`（D-001/D-003/D-006/D-009）
- `.agenticdoc/mw-write-face-guard/plan.md`（W-01 交付/验收/证据要求）
- `packages/multi-workers/test/fixtures/write-face-corpus.json`（只读，16+49）
- `packages/multi-workers/autopilot/xkey.py:1075-1084`（只读，反例：仓内唯一 Python `fnmatch` 匹配器，本卡不改）
- `packages/multi-workers/pytest.ini`（`addopts = -m "not e2e_real and not e2e_l2"`）

## 改动历史

| 文件 | 位置 | before | after |
|---|---|---|---|
| `packages/multi-workers/autopilot/write_face.py` | `:1-954` | 新建 | 954 行；关键锚点：拒绝码 `:40-43`、上限常量 `:50-55`、`WriteFace/Conflict/Unsupported` `:122-173`、`_split_single_line` `:246`、`_has_bare_comma` `:278`、`_expand_alts` `:387`、`_compile_normalized` `:552`、`_normalize_entry` `:588`、`parse_write_face` `:636`、`_seg_overlap` `:738`、`_globs_overlap` `:809`、`globs_overlap` `:860`、`overlap` `:898` |
| `packages/multi-workers/test_write_face.py` | `:1-368` | 新建 | 368 行；语料驱动 `:71-152`、ε-NFA 硬验收 `:158-190`、边界 `:196-230`、保守回退 `:236-312`、deny 单调 `:318-334`、witness/无 fnmatch `:340-368` |

卡片内二次修改（均在上述允许面内；最终行号）：

1. `write_face.py:246` `_split_single_line` 由"朴素 `s.split(",")`"改为 **brace/class-aware 分割**：修复 V20 `a/{b,c}/**` 因 entry 内逗号被误拆为两条 entry（初次实测 `Unsupported(rule='a/{b')`）。
2. `write_face.py:278` 新增 `_has_bare_comma`；`write_face.py:588` `_normalize_entry` 的 `,` 拒绝由"任何逗号"收紧为"brace/class 外的裸逗号"，使 V20 的 `{b,c}` 合法、P16 的 `"a,b"` 仍拒。
3. `write_face.py:898` `overlap` 的 base 比较改为"先精确比较、两侧均 caseInsensitive 时才折大小写"，修复 `incomparable-case-mode` 被 base 误判遮蔽（初次实测 `Unsupported(incomparable-base)`）。
4. `test_write_face.py:340` `test_parse_returns_normalized_segments` 断言改为检 `CharPattern(tokens=(Lit('a'),))` 而非字符串 `'a'`。
5. `test_write_face.py:352` `test_module_never_imports_fnmatch_or_pathlib_match` 由源码子串检查改为 AST import 检查（避免文档字符串里 `fnmatch`/`PurePath` 字样造成假阳性）。
