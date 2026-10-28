# W-04 证据：Python 侧 `write_face` 算子修正（D-111 优先级 + D-112 条目切分）

- key: mw-write-face-guard
- 卡: `workers/wfg-i04-operator-py-fix/task.md`（card_sha256 `bdf17177a979ea393d293921e4b027cbecd375696a39ae37d39e11545936ab51`）
- 角色: 修正（只写允许面两文件 + 本报告）
- 依据: `design.md` D-111 / D-112；`evidence/PM-parity-differential-20261014.md`（§3 定位矩阵、§4 裁定）
- 语料（只读）: `packages/multi-workers/test/fixtures/write-face-corpus.json`（PM 冻结，`parse` 23 / `overlap` 58）
- 采集时间: 2026-10-14
- 平台: Windows dev（Python 3.14.3，pytest 9.0.2，`sys.platform=win32`）

## TL;DR

1. 三处修正全部落地：D-112 语法无感条目切分、D-111 parse 期硬违规优先、D-111 overlap 期先证冲突。
2. 冻结语料全过：`parse` 23/23、`overlap` 58/58（overlap 33 / none 13 / reject 8 / serial_only 1 / unsupported 3）。
3. 验收 `python -m pytest test_write_face.py -q` = `128 passed`（修正前同一命令 = `10 failed, 105 passed`）。
4. 旧行、`deny` 不参与判定（V37/V38）、无 `fnmatch`/`pathlib`/新依赖等约束全部保持。
5. 公开 API 名称与返回形状未变；未新增字段。
6. 发现一处**跨卡集成风险**（非本卡范围，报回 PM）：W-03 的 `render_write_face_line`（`autopilot/dispatch.py:1059-1067`）用单行 `, ` 拼接条目，与 D-112 的单行语法无感切分叠加后，含逗号的 brace 条目会在线路回读时被拆开（详见「残留与未验证」R-1）。

## 验收输出（实跑原文）

命令：`cd packages/multi-workers; python -m pytest test_write_face.py -q`

修正后（当前工作树）：

```
........................................................................ [ 56%]
........................................................                 [100%]
128 passed in 0.25s
```

修正前（本会话首次实跑、未改动任何文件时的原文，节选尾部）：

```
FAILED test_write_face.py::test_corpus_parse[P21 unclosed brace is not a parse error]
FAILED test_write_face.py::test_corpus_parse[P22 unsupported entry keeps position next to a valid one]
FAILED test_write_face.py::test_corpus_parse[P23 comma is never pattern content]
FAILED test_write_face.py::test_corpus_overlap[V49 illegal class with nothing provable]
FAILED test_write_face.py::test_corpus_overlap[V50 extglob negation on side b]
FAILED test_write_face.py::test_corpus_overlap[V51 unclosed brace with nothing provable]
FAILED test_write_face.py::test_corpus_overlap[V54 hard invalid-entry wins over an earlier unsupported entry]
FAILED test_write_face.py::test_corpus_overlap[V55 hard outside-base wins over an earlier unsupported entry]
FAILED test_write_face.py::test_corpus_overlap[V57 provable conflict wins over an unsupported entry]
FAILED test_write_face.py::test_corpus_counts_frozen - AssertionError: assert...
10 failed, 105 passed in 0.20s
```

> 其中 V49/V50/V51 的失败是**旧测试驱动**没处理 `unsupported` kind（走到了 `assert result is None`），不是算子缺陷；算子当时已返回 `Unsupported`（下方 BEFORE 对照实测证实）。P21/P22/P23、V54/V55/V57 是真实算子缺陷。

### 全语料通过计数

驱动脚本（`C:\Users\wenbozhou\AppData\Local\Temp\wf-w04\before_after.py`，按 `corpus.counts` 逐行实跑）原文：

```
[BEFORE] corpus parse 20/23  overlap 55/58
[BEFORE] failing rows: parse=['P21 unclosed brace is not a parse error', 'P22 unsupported entry keeps position next to a valid one', 'P23 comma is never pattern content'] overlap=['V54 hard invalid-entry wins over an earlier unsupported entry', 'V55 hard outside-base wins over an earlier unsupported entry', 'V57 provable conflict wins over an unsupported entry']
[AFTER]  corpus parse 23/23  overlap 58/58
[AFTER]  failing rows: parse=[] overlap=[]
```

逐 kind 计数（`test_corpus_counts_frozen` 断言，与 `corpus.counts` 冻结值逐项相等）：

| 语料段 | 行数 | kind 分布 |
|---|---|---|
| `parse` | 23 | entries 16 / unknown 2 / reject 5 |
| `overlap` | 58 | overlap 33 / none 13 / reject 8 / serial_only 1 / unsupported 3 |

## 修正前后对照（实测原文，含命令）

**BEFORE 的取得方式（如实声明）**：`autopilot/write_face.py` 在本会话是**未跟踪文件**（`git status` = `??`），无 VCS 基线可 checkout。因此 BEFORE 侧用「把本卡的三处改动**逆向还原**，得到修正前源码，再实跑」取得；还原文件 954 行（与 W-01 证据自述的 954 行一致），`python -c "ast.parse"` 通过，且函数锚点与 W-01 证据逐条吻合（`_split_single_line:246`、`parse_write_face:636`、`_globs_overlap:809`、`globs_overlap:860`、`overlap:898`）。还原脚本 `C:\Users\wenbozhou\AppData\Local\Temp\wf-w04\reverse.py`。

命令：`cd packages/multi-workers; python C:\Users\wenbozhou\AppData\Local\Temp\wf-w04\before_after.py`

实测原文（`BEFORE` 段 = 修正前，`AFTER` 段 = 修正后；同一脚本、同一 base/输入）：

```
===== BEFORE =====
[BEFORE P22] WriteFace(allow_entries=['src/[a-, src/ok.ts'])
[BEFORE P23] WriteFace(allow_entries=['src/[a-, src/b].ts', 'src/ok.ts'])
[BEFORE V54 a-side] WriteFace(allow_entries=['src/[a-, !src/x'])
[BEFORE V54 overlap] Unsupported(reason='unsupported-syntax', detail='unsupported glob syntax in allow entry', rule='src/[a-, !src/x', other=None)
[BEFORE V55 a-side] WriteFace(allow_entries=['src/[a-, C:/Users/wenbozhou/AppData/Local/Temp/mw-write-face-outside-probe/x'])
[BEFORE V55 overlap] Unsupported(reason='unsupported-syntax', detail='unsupported glob syntax in allow entry', rule='src/[a-, C:/Users/wenbozhou/AppData/Local/Temp/mw-write-face-outside-probe/x', other=None)
[BEFORE V56 a-side] Refused(code='write-face-outside-base', detail="entry 'C:\\\\Users\\\\wenbozhou\\\\AppData\\\\Local\\\\Temp\\\\mw-write-face-outside-probe/x'", entry='C:\\Users\\wenbozhou\\AppData\\Local\\Temp\\mw-write-face-outside-probe/x')
[BEFORE V56 overlap] (not reached: a-side refused)
[BEFORE V57 a-side] WriteFace(allow_entries=['src/[a-, src/x.ts'])
[BEFORE V57 overlap] Unsupported(reason='unsupported-syntax', detail='unsupported glob syntax in allow entry', rule='src/[a-, src/x.ts', other=None)
===== AFTER =====
[AFTER P22] WriteFace(allow_entries=['src/[a-', 'src/ok.ts'])
[AFTER P23] WriteFace(allow_entries=['src/[a-', 'src/b].ts', 'src/ok.ts'])
[AFTER V54 a-side] Refused(code='write-face-invalid-entry', detail="entry '!src/x'", entry='!src/x')
[AFTER V54 overlap] (not reached: a-side refused)
[AFTER V55 a-side] Refused(code='write-face-outside-base', detail="entry 'C:\\\\Users\\\\wenbozhou\\\\AppData\\\\Local\\\\Temp\\\\mw-write-face-outside-probe/x'", entry='C:\\Users\\wenbozhou\\AppData\\Local\\Temp\\mw-write-face-outside-probe/x')
[AFTER V55 overlap] (not reached: a-side refused)
[AFTER V56 a-side] Refused(code='write-face-outside-base', detail="entry 'C:\\\\Users\\\\wenbozhou\\\\AppData\\\\Local\\\\Temp\\\\mw-write-face-outside-probe/x'", entry='C:\\Users\\wenbozhou\\AppData\\Local\\Temp\\mw-write-face-outside-probe/x')
[AFTER V56 overlap] (not reached: a-side refused)
[AFTER V57 a-side] WriteFace(allow_entries=['src/[a-', 'src/x.ts'])
[AFTER V57 overlap] Conflict(sample='src/x.ts', rule='src/x.ts', other='src/x.ts', reason='write-face-overlap')
```

逐行裁定（`V54`/`V55`/`V56` 期望 parse 期 `reject`，故「overlap 不进入」正是期望形状）：

| 语料行 | 期望 | BEFORE 实测 | AFTER 实测 |
|---|---|---|---|
| `P22` | entries `["src/[a-", "src/ok.ts"]` | `['src/[a-, src/ok.ts']`（`[` 吞掉逗号+后字段） | `['src/[a-', 'src/ok.ts']` |
| `P23` | entries `["src/[a-", "src/b].ts", "src/ok.ts"]` | `['src/[a-, src/b].ts', 'src/ok.ts']`（吞成 2 条） | `['src/[a-', 'src/b].ts', 'src/ok.ts']` |
| `V54` | `reject:write-face-invalid-entry` | `Unsupported(rule='src/[a-, !src/x')`（`!src/x` 从未被校验） | `Refused(code='write-face-invalid-entry', entry='!src/x')` |
| `V55` | `reject:write-face-outside-base` | `Unsupported(rule='src/[a-, <OUTSIDE>/x')` | `Refused(code='write-face-outside-base', entry='<OUTSIDE>/x')` |
| `V56` | `reject:write-face-outside-base` | `Refused(code='write-face-outside-base')`（顺序碰巧对） | `Refused(code='write-face-outside-base')`（顺序无关） |
| `V57` | `overlap`（可证冲突优先） | `Unsupported(rule='src/[a-, src/x.ts')` | `Conflict(sample='src/x.ts', rule='src/x.ts', other='src/x.ts')` |

补充实测（新加单测断言的核心行为，`pytest` 内已覆盖）：

- `P21` `write_face: src/{a,b` -> `WriteFace(allow_entries=['src/{a', 'b'])`（`{` 未闭合时逗号仍切分；碎片 `b` 是合法字面量，只**增加** allow 条目）。
- `P16` `write_face: "a,b"` -> `Refused(write-face-invalid-entry)`（首字段 `"a` 先被拒，与 D-112 note 一致）。
- `P17`–`P20` -> `WriteFace`，unsupported 条目原样保留在 `allow_entries`（`src/[a-` / `src/!(x)` / `src/+(x)` / `src/@(x)`）。
- `V52`/`V53`（escape 的两种书写顺序）-> 同 code `write-face-escape`。
- `V49`/`V50`/`V51` -> `Unsupported`（证不出冲突且含 unsupported）。

## D-112 反例说明：为什么「括号感知切分」是错的

修复前的切分器（`_split_single_line`，`:246-276`）会跟踪 `in_class`：见到 `[` 就认为进入字符类，其后的 `,` 不再是分隔符，直到 `]` 才退出。这正是 D-112 明令禁止的「语法感知切分」，带来的后果是可实测的**丢条目（fail-open）**：

输入 `write_face: src/[a-, src/b].ts, src/ok.ts`（P23）：

- 括号感知切分：`[` 打开字符类 -> `a-, src/b]` 被当作类内内容 -> 整个值切成 **1** 个条目 `src/[a-, src/b].ts`（其后再无逗号）-> 声明的 `src/ok.ts` **被吞掉，从 face 消失**。若在飞 worker 恰好写 `src/ok.ts`，重叠闸看不见这条声明，两个 writer 落到同一文件——正是 `write_face` 要防的那个失效。
- 语法无感切分（本修正）：`split(',')` -> 3 个字段 `src/[a-`、`src/b].ts`、`src/ok.ts`，逐字段独立解析。`src/[a-` 作为 unsupported 保留在「未知集合」，其余两条正常生效。

反例断言固定在 `test_write_face.py::test_d112_bracket_aware_split_would_merge_three_entries_into_one`：显式给出「括号感知会合并成的单条目」并断言实际结果**不等于**它、且长度恰为 3、`src/ok.ts` 仍在末尾。

为什么语法无感方向的误差是 fail-closed：

- 逗号切出的**碎片**（如 P21 的 `b`、P23 的 `src/b].ts`）只会作为**新增 allow 条目**进入判定。allow 条目变多不会放宽并发（只会更早判定重叠/unsupported），因此方向安全。
- 反向的「保护逗号」规则则需要多一条语法感知分支（`[`/`{`/引号各自的开闭状态机），每一条分支都是一个潜在的 fail-open 面（未闭合时行为未定义），而收益为零——D-112 的裁定原话。
- 唯一真正的语法歧义（balanced `{b,c}` 含逗号，V20）不属于单行头部值，而由 §3.1 的等价 block-list 载体承载：每个 `- item` 本身即一个字段，逗号无需保护。本卡测试驱动据此渲染（见改动历史 `test_write_face.py:51-73`）。

## 改动历史

BEFORE 位置取修正前源码（还原文件，954 行）的行号，与 W-01 证据锚点一致；AFTER 取当前工作树行号（`write_face.py` 970 行 / `test_write_face.py` 500 行）。

### `packages/multi-workers/autopilot/write_face.py`

| 改动点 | before | after |
|---|---|---|
| 模块 docstring 决策清单 | `:9` `(design.md D-001/D-006):`；`:19` 仅 `* ... deny;` 一条 bullet | `:9` `(design.md D-001/D-006/D-111/D-112):`；`:20-24` 追加 3 条 bullet（D-112 切分 / D-111 parse / D-111 overlap） |
| `_split_single_line`（条目切分） | `:246-276`：brace + `in_class` + 引号感知状态机；`[` 未闭合时吞逗号，`"a,b"` 被整体去引号 | `:251-268`：`field.strip() for field in value.split(",")`，丢空字段；docstring 记录 D-112 与等价 block-list 说明。旧 31 行状态机整体删除，无残留（无其它调用点） |
| `parse_write_face` 字段循环 | `:663-665`：`globs` / `norm_entries` 初始化后直接 `for raw in raw_entries:` | `:655-663`：新增 `:658-662` D-111 注释，循环体不变（`_normalize_entry` 对 unsupported 返回 glob 而非 refusal，故「硬违规立即返回」天然等价于「遍历后取字段序第一个硬违规」，与顺序无关） |
| `globs_overlap`（段序列便捷入口） | `:873-879`：遇到任一 `glob.unsupported` 立即 `return Unsupported(unsupported-syntax)`；`:881-891` 才做 witness 搜索 | `:871-877`：先只**记录** `unsupported_rule`；`:878-891` 先在所有 supported 对上证 witness；`:892-895` 证不出时才 `Unsupported` |
| `overlap`（face 级算子） | `:929-936`：pair 循环内 `if ga.unsupported or gb.unsupported: return Unsupported(...)`，短路 | `:934-935`：先取两侧首个 unsupported entry；`:936-951` proof-first（`continue` 跳过 unsupported 对）；`:952-958` 证不出时 `Unsupported(unsupported-syntax, rule, other)` |

> 切分与校验未抽成新函数：`_split_single_line` 保留原名与新签名，`parse_write_face` 的循环结构不变，新增的只是 `overlap` / `globs_overlap` 的排序与两个局部变量。`_has_bare_comma`（BEFORE `:278` / AFTER `:271`）保留，仅服务 block-list 形态的裸逗号拒绝。

### `packages/multi-workers/test_write_face.py`

| 改动点 | before | after |
|---|---|---|
| 模块 docstring | `:1-13`：16/49 计数 | `:1-14`：23/58 计数、kind 分布、D-111/D-112 契约引用 |
| 语料渲染 helper | `:51-55` `_face`：恒为单行 `", ".join(entries)` | `:53-71`：新增 `_render_head`（含逗号的条目走等价 block-list，其余仍走单行以继续压测 D-112 切分）+ 薄封装 `_face` |
| `test_corpus_overlap` | `:120-133`：`overlap` 之外一律 `assert result is None`（不识别 `unsupported`） | `:124-158`：新增 `kind == "unsupported"` 分支断言 `Unsupported` |
| 新增 `test_corpus_unsupported_is_also_overlap` | 无 | `:160-167`：断言 `wf.is_overlap(Unsupported)` 为真（调用方两种形状都拒绝） |
| `test_corpus_counts_frozen` | `:139-150`：16/49、4 kind | `:170-180`：23/58、5 kind（含 `unsupported: 3`） |
| 新增 D-112 反例/回归测试 | 无 | `:183-229`：`test_d112_unterminated_bracket_does_not_swallow_the_next_field` / `test_d112_comma_is_never_pattern_content` / `test_d112_unclosed_brace_still_splits` / `test_d112_bracket_aware_split_would_merge_three_entries_into_one` |
| 新增 D-111 优先级测试 | 无 | `:232-276`：参数化 `test_d111_parse_hard_violation_wins_regardless_of_order`（escape/invalid-entry/outside-base × 两种书写顺序）、`test_d111_provable_conflict_wins_over_unsupported`、`test_d111_unsupported_only_when_no_witness`、`test_d111_unsupported_entry_is_recorded_not_dropped` |

## 约束核对

- 未改语料：`write-face-corpus.json` 本会话零写入（只读）。
- 未改旧行期望：`parse` 旧 16 行、`overlap` 旧 49 行逐条仍过（AFTER 23/23 + 58/58 蕴含）。
- `deny` 不参与判定：V37/V38 与 `test_deny_does_not_change_the_overlap_decision` 全过。
- 无新依赖：模块 import 仍为 `__future__` / `dataclasses` / `re` / `collections`(deque) / `collections.abc`；`test_module_never_imports_fnmatch_or_pathlib_match`（AST）过。
- 公开 API 不变：`parse_write_face` / `globs_overlap` / `WriteFace` / `Conflict` / `Unsupported` / `Refused` / `Undeclared` 名称与返回形状未改，未新增字段。
- 未碰 `dispatch.py`、未碰 `packages/coding-agent/**`、未碰 `mw_common.py`；未跑根 `npm run check`。
- 只跑 `test_write_face.py`（`128 passed`），未跑包级 pytest（W-03 的 dispatch 测试不在本卡范围）。

## 残留与未验证

- **R-1（跨卡集成风险，报回 PM；不在本卡允许面）**：W-03 的 `autopilot/dispatch.py:1059-1067` `render_write_face_line` 仍用 `"write_face: " + ", ".join(entries)` 渲染。若卡面「写入允许面」含 `a/{b,c}/**` 这类**含逗号的条目**，D-112 单行语法无感切分会把它回读成 `a/{b` + `c}/**`（两条 unsupported）⇒ 该 face 变成「全部无法判定」，`overlap` 返回 `Unsupported`（调用方按重叠拒绝）。方向是 fail-closed（不会放行多写者），但会误判为不可判定，且 render→parse 不是恒等。建议 PM 让 W-03 的 renderer 对含逗号条目改用 block-list（§3.1 等价形态），或明确禁止卡面写含逗号条目。本卡未改 `dispatch.py`。
- **R-2（未验证）**：`globs_overlap` 便捷入口在编译失败（如 `..`）时仍静默丢弃该 entry（W-01 的 R-5 遗留）；生产路径走 `parse_write_face` + `overlap`。本卡未改该行为。
- **未覆盖面**：未对拍 TS 侧（T-W-I05）；未穷举 D-112 下「引号 + 逗号」「多个未闭合括号」的碎片组合（P23 为最复杂反例）；未测 `case_insensitive=True` 下方的 new 行（语料本身无）。
- **未跑**：包级 `python -m pytest -q`（会带上 W-03 正在改的 `dispatch.py` 测试）；根 `npm run check`（卡面禁止）。

## 上下文来源

- `.agenticdoc/mw-write-face-guard/workers/wfg-i04-operator-py-fix/task.md`（本卡）
- `.agenticdoc/mw-write-face-guard/design.md` D-111 / D-112
- `.agenticdoc/mw-write-face-guard/evidence/PM-parity-differential-20261014.md` §3–§5
- `.agenticdoc/mw-write-face-guard/evidence/W-01-write-face-operator-py.md`（修正前锚点）
- `packages/multi-workers/test/fixtures/write-face-corpus.json`（只读，23+58）
- `packages/multi-workers/autopilot/dispatch.py:1059-1067`（只读，反例：renderer 与 D-112 的交互）
