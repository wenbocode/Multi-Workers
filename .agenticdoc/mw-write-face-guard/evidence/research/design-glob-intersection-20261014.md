# RQ-D1 证据：写面 glob 归一语义与交集算子

- key: mw-write-face-guard
- 卡: `tasks/T-W-D1-glob-intersection.md`（card_sha256 `ea9abd2ed377bc927663f0cf318fb250f3d92d55aa85eddfb724c9af4410fd8e`）
- 角色: 只读取证；唯一写面 = 本文件
- 采集时间: 2026-10-14
- 取证范围: 全仓只读（含 `dist/`、其它 key、`.mw/`）；未改任何生产文件
- 平台: Windows dev（`process.platform=win32`，`os.name=nt`）

---

## 0. 结论先行

1. **仓里今天有 5 套互不相同的"字符串 → 路径集合"实现，没有一套"集合 ∩ 集合"算子。**
   写面交集必须新建，且新建时必须**先冻结一套规范语法**，否则两端（Python/TS）必然分叉。

2. **最大的跨语言分叉不是 `**`，而是 `*` 是否跨 `/`。**
   仓内唯一的 Python glob 匹配器是 `xkey.py:1084 fnmatch.fnmatch`：`*` 跨 `/`（实测 `fnmatch("a/b/c.ts","a/*.ts")=True`），
   且 win32 上 `normcase` 大小写不敏感（实测 `fnmatch("A/B.TS","a/b.ts")=True`）。
   TS 侧全部走 minimatch 10.2.5：`*` **不**跨 `/`（`minimatch("a/b/c.ts","a/*.ts")=False`），默认大小写敏感。
   任何"Python 用 fnmatch、TS 用 minimatch"的实现都会给出相反答案。

3. **同一字符串在三处被三种语义处理（必须归一，否则算子无法定义）：**
   - `read_scope` **allow** 项：**不是 glob**，只做 `isSameOrUnder` 目录包含性（`read-scope.ts:118-121`）；
   - `write_scope` 项：`GLOB_MAGIC_RE.test(entry)` 为真才走 minimatch，否则退回 `isSameOrUnder` 包含性（`worker-mode.ts:1564/1587/1598`）；
   - `deny_globs` 项：**总是** minimatch（`read-scope.ts:141-146`）。
   实测 `minimatch("packages/x/y.ts","packages*")=False`，但同一字符串作为字面项时 `isSameOrUnder` 语义会覆盖整棵子树——同名不同义。

4. **`a/**` 不含 `a` 是 minimatch 的真实行为，两处消费者各自打了补丁。**
   实测 `minimatch("a","a/**")=False`；`read-scope.ts:147-153` 与 `worker-mode.ts:1592-1594` 都加了"尾 `/**` 也匹配目录自身"特例。
   交集算子必须与这两处补丁同向（建议：规范语法直接定义 `a/**` **包含** `a`）。

5. **minimatch 本身不是干净的归一器，不能把原始字符串直接喂进去算交集。**
   实测 `minimatch("./a/b","a/b")=False`、`minimatch("a/../a/b","a/b")=True`、`minimatch("a//b","a/b")=True`、`minimatch("src/a.ts","src\\\\*.ts")=False`。
   算子必须先做一层显式词法归一（`\`→`/`、去 `./`、并 `//`、拒绝 `..`、去尾 `/`），再进匹配。

6. **minimatch 默认 `dot:false`：`*` 与 `**` 都不匹配 `.` 开头的段。**
   实测 `minimatch("a/.x/b","a/**")=False`、`minimatch("a/.x/b","a/**",{dot:true})=True`。
   仓内没有任何调用点显式设置 `dot`（`read-scope.ts:146`、`worker-mode.ts:1591` 都是默认）。
   写面覆盖 `.agenticdoc/**`、`.pi`、`.github` 这类真实目录，建议 `write_face` 显式取 `dot:true`（见 §3）。

7. **deny 优先是既有语义（`read-scope.ts:167-183`、`worker-mode.ts:1624-1662`、`README.md:145`）。**
   但**交集判定的推荐语义是：deny 不参与**——`A.deny` 完全遮盖 `A.allow ∩ B.allow` 时仍判**重叠**（保守）。
   理由见 §3.2（fail-closed、判定对 deny 单调、避免用安全网放宽并发容量）。

8. **算子可判定性：** 纯词法下用"两条 glob 的 ε-NFA 乘积做可达性"即可判定无交集，**不需要**枚举文件系统；
   仅在语法不受支持 / 绝对路径越基 / 递归上限触发时回退为"保守视为重叠"。伪码见 §4。

9. **归一建议一句话：** 单一语法（`/` 分隔、无 `!`、无 `..`、无 `,`）、`**` 零或多段且含裸前缀、win32 大小写不敏感、`dot:true`、字面项 = 精确节点（目录须显式写 `/**`）、相对单一 base。

---

## 1. 取证对象与既有实现现状

### 1.1 唯一完整三段式（读面）

| 段 | 位置 | 原文 |
|---|---|---|
| 渲染 | `packages/multi-workers/autopilot/dispatch.py:748` | `    read_scope: Sequence[str] = (),` |
| 渲染 | `packages/multi-workers/autopilot/dispatch.py:749` | `    deny_globs: Sequence[str] = (),` |
| 渲染 | `dispatch.py:857-866` | `if read_scope:` → `lines.append("read_scope:")` + `  - {item}`；`if deny_globs:` → `"deny_globs:"` + `  - '{item}'` |
| 展开 | `dispatch.py:880-921` | `_expand_read_scope`：dual/partition 模式把相对项按 game/partition root 绝对化，再追加 control root（partition 另加 parent root） |
| 解析 | `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:406-414`（read_scope）、`:421-431`（deny_globs） | YAML 块列表；deny 项去一对引号 |
| 运行期 | `worker/read-scope.ts:167-215` | `checkReadScopeCall`：deny → containment → cap-file → cap-byte |

复核确认：不存在 `shared/read-scope.ts`（`Get-ChildItem -Recurse ... -Filter "*read-scope*"` 只返回 `worker/read-scope.ts`）。

### 1.2 仓内 5 套"字符串→路径集合"实现

| # | 实现 | 位置 | glob 语义 |
|---|---|---|---|
| M1 | `isSameOrUnder` 目录包含性 | `worker/read-scope.ts:89-93` | 段边界前缀；win32 `toLowerCase()` |
| M2 | `isWithinScope`（read_scope allow） | `worker/read-scope.ts:118-121` | **只调 M1**，两项都过 `normalizeForCompare`（realpath）；**不含 minimatch** |
| M3 | `matchedDenyGlob`（deny_globs） | `worker/read-scope.ts:141-160` | 双基 minimatch（abs + rel）+ 尾 `/**` 特例 |
| M4 | `matchesWriteScopeEntry`（write_scope） | `worker/worker-mode.ts:1584-1600` | 有 `GLOB_MAGIC_RE` → 双基 minimatch（rel + forward）+ 尾 `/**` 特例；无 magic → M1（realpath 包含） |
| M5 | `_matches_path`（Python，xkey untouchable） | `packages/multi-workers/autopilot/xkey.py:1075-1084` | `target==pattern` / `pattern.endswith("/")` 前缀 / `pattern.endswith("/**")` 前缀 / **`fnmatch.fnmatch`** |

原文（逐条）：

```ts
// M1  worker/read-scope.ts:84-93
const IS_WIN32 = process.platform === "win32";

export function isSameOrUnder(prefix: string, candidate: string): boolean {
	const a = IS_WIN32 ? prefix.toLowerCase() : prefix;
	const c = IS_WIN32 ? candidate.toLowerCase() : candidate;
	return c === a || c.startsWith(`${a}${path.sep}`);
}
```

```ts
// M3  worker/read-scope.ts:141-160
export function matchedDenyGlob(projectRoot: string, denyGlobs: string[], rawPath: string): string | null {
	if (denyGlobs.length === 0) return null;
	const abs = normalizeForCompare(projectRoot, rawPath);
	const rel = path.relative(projectRoot, abs).replaceAll("\\", "/");
	for (const glob of denyGlobs) {
		if (minimatch(abs, glob) || minimatch(rel, glob)) return glob;
		if (glob.endsWith("/**")) {
			const stripped = glob.slice(0, -3);
			if (stripped !== "" && minimatch(rel, stripped)) return glob;
		}
	}
	return null;
}
```

```ts
// M4  worker/worker-mode.ts:1564, 1584-1600
const GLOB_MAGIC_RE = /[*?[\]{}]/;
...
function matchesWriteScopeEntry(config: BashWriteScopeConfig, entry: string, absoluteTarget: string): boolean {
	const normalized = entry.trim();
	if (normalized === "") return false;
	if (GLOB_MAGIC_RE.test(normalized)) {
		const relative = path.relative(config.projectRoot, absoluteTarget).replaceAll("\\", "/");
		const forward = absoluteTarget.replaceAll("\\", "/");
		const glob = normalized.replaceAll("\\", "/");
		if (minimatch(relative, glob) || minimatch(forward, glob)) return true;
		if (glob.endsWith("/**")) {
			const stripped = glob.slice(0, -3);
			if (stripped !== "" && (minimatch(relative, stripped) || minimatch(forward, stripped))) return true;
		}
		return false;
	}
	return isSameOrUnder(normalizeForCompare(config.projectRoot, normalized), absoluteTarget);
}
```

```python
# M5  packages/multi-workers/autopilot/xkey.py:1075-1084
def _matches_path(target: str, pattern: str) -> bool:
    if not pattern:
        return False
    if target == pattern:
        return True
    if pattern.endswith("/") and target.startswith(pattern):
        return True
    if pattern.endswith("/**") and target.startswith(pattern[:-3].rstrip("/") + "/"):
        return True
    return fnmatch.fnmatch(target, pattern)
```

### 1.3 没有交集算子

全仓 grep `overlap|intersect` 于 `packages/multi-workers/**/*.py` + `packages/coding-agent/src/extensions/agent-team-loop/**/*.ts`：
仅 2 条命中，都是散文（`worker-mode.ts:320` 与 `:1604` 的注释"the task's `write_scope:` intersection"），**无任何 glob×glob 交集实现**。
`write_scope` 在 `dispatch.py` 命中 **0** 次（conductor 不渲染写面，与 `spec-write-face-sources-20261014.md` §1.3a 一致）。

### 1.4 异语义同名物（不得混入算子）

- gate v2 `write_scope`（JSON list，语义 `blast_radius ⊆ write_scope`）：`gates.py:175`（`_JSON_LIST_FIELDS`）、`gates.py:790`（`optional_json("write_scope")`）、消费 `conductor.py:6514-6526`。
  与任务书写面**同名不同义**，`spec.md` AC-009 已锁"不复用该名"。
- 卡 envelope `写入允许面`/`写入禁止面`：`shared/dispatch-card.ts:185`（槽位名）、`:251-252`（宽正则，含 `write_scope` 别名）、`:457-484`（`typeExtrasMissing` 只判存在性，从不抽值）。
- C2 契约块 `<!-- mw-write-surface: v1 -->`：`worker-mode.ts:355-362` 只判 marker 结构。

### 1.5 版本与安装事实

- `packages/coding-agent/package.json:61` → `"minimatch": "10.2.5"`（精确 pin）。
- 实装 `node_modules/minimatch/dist/commonjs/index.js`，`require("minimatch/package.json").version === "10.2.5"`。
- Python 侧无 minimatch；唯一近义物是标准库 `fnmatch`（`xkey.py:46 import fnmatch`）。

---

## 2. 差异点穷举（`file:line` + 原文 + 判定）

> 每条：现象 → 原文证据 → 实测 → 判定。实测命令见 `[VERIFY]`。

### D-1 大小写敏感度：同一"读面"入口内两种敏感度

- 证据：`read-scope.ts:89-92`（win32 `toLowerCase()`）对 allow containment；`read-scope.ts:146` `if (minimatch(abs, glob) || minimatch(rel, glob)) return glob;`（无 `nocase`）对 deny。
- 实测：`minimatch("A/B/C.TS","a/b/c.ts")=False`、`minimatch("A/B","a/b",{nocase:true})=True`；win32 `isSameOrUnder("H:\\Repo","h:\\repo\\sub")=True`（该断言已冻结于 `test/suite/autopilot-read-scope.test.ts`）。
- 判定：**同一字符串在两个子判定里敏感度相反**。写面必须二者取一。

### D-2 `**` 段语义与 `a/**` 是否含 `a`

- 证据：`read-scope.ts:147-153`（注释原文 "A trailing /** also denies the directory itself: plain minimatch leaves `ls`/`find` on the bare directory ... unblocked — a firewall hole."）；`worker-mode.ts:1592-1594` 同构。
- 实测：`minimatch("a","a/**")=False`、`minimatch("a/b","a/**")=True`、`minimatch("a/b/c.ts","a/**/*.ts")=True`、`minimatch("a","a/**/*")=False`。
- 判定：`a/**` 的"裸目录"缺口是真实行为，两处消费者各自打补丁。交集算子必须同向。

### D-3 点段（隐藏文件）：minimatch 默认 `dot:false`

- 证据：`read-scope.ts:146`、`worker-mode.ts:1591` 均只传两个位置参数，**无 options**（无 `dot:true`）。
- 实测：`minimatch("a/.x/b","a/**")=False`；`minimatch("a/.x/b","a/**",{dot:true})=True`；`minimatch("a/.x","*")=False`。
- 判定：`.git`/`.agenticdoc` 作为**字面段**仍能匹配（模式里写了点），但 `*`/`**` 永不跨/不匹配点段。写面覆盖 `.github/**`、`.pi/**` 等真实目录时会静默变窄。

### D-4 多基（绝对/相对）与 realpath 在三个匹配器里不一致

- 证据：
  - M3 `read-scope.ts:142-146`：`abs = normalizeForCompare(...)`（realpath）、`rel = path.relative(projectRoot, abs).replaceAll("\\","/")`，**双基**；
  - M4 `worker-mode.ts:1588-1591`：`relative` + `forward`（**未 realpath**），双基；
  - M2 `read-scope.ts:118-121`：两侧都 `normalizeForCompare`，**单基 realpath**。
- 判定：三个匹配器的基、归一化深度都不同。算子必须显式声明单一基。

### D-5 realpath vs 词法

- 证据：`read-scope.ts:100-116 normalizeForCompare`（`path.resolve` → `fs.realpathSync`，缺失尾段回挂最近存在祖先的 realpath）；`shared/target-config.ts:145` `fs.realpathSync.native(resolved)`（`normalizeRoot`）。
- 判定：glob 模式**无法** realpath（模式里没有真实 inode）。算子只能是词法的；symlink/junction 是残余风险（§6）。

### D-6 同一字符串的三种处理（字面/条件 glob/总 glob）

- 证据：M2 `isWithinScope` **不调** minimatch；M4 `worker-mode.ts:1564` `GLOB_MAGIC_RE = /[*?[\]{}]/` + `:1587` 分支；M3 总是 minimatch。
- 实测：`minimatch("packages/x/y.ts","packages*")=False`（`*` 不跨 `/`）；但字面项 `packages` 走 M1 → `isSameOrUnder(realpath("packages"), target)=True`（覆盖整棵子树）。
- 判定：**"有没有 magic"决定语义分支**是最大的人为分叉源。写面应取消该分支。

### D-7 字面目录项的隐式 `/**`

- 证据：`worker-mode.ts:1598` `return isSameOrUnder(normalizeForCompare(config.projectRoot, normalized), absoluteTarget);`。
- 判定：字面项 `a` 覆盖 `a/b`；minimatch 下 `a` 只匹配精确节点。`write_scope: a` 与 `write_scope: a/**` 在**不同分支**里几乎等价，但在**同一 glob 分支**里不等价。

### D-8 分隔符：`,` / YAML 块 / 队列 `|` / JSON list

- 证据：`worker-mode.ts:441-449`（单行 `rest.split(",")`）；`:456-466`（块列表）；`dispatch.py:865`（deny_globs `'{item}'` 加引号）；`gates.py:175/790`（JSON list）；`mw_common.py:1747`（队列 `split("|")`）。
- 判定：写面进队列列会与 `|` 冲突（AC-008 已禁）；单行 `,` 形式**无转义**，glob 内含 `,` 即不可表达。

### D-9 反斜杠：路径侧是分隔符，模式侧是转义符

- 证据：`worker-mode.ts:1588-1590`（路径与 glob 都 `replaceAll("\\","/")`）；`read-scope.ts:144`（**只**对 rel 路径 replace，glob 原样传入）。
- 实测：`minimatch("src/a.ts","src\\\\*.ts")=False`（模式里的 `\` 是 escape）；`minimatch("src\\\\a.ts","src/*.ts")=True`（路径里的 `\` 是分隔符）；`minimatch("a\\\\b","a/b")=True`、`minimatch("a/b","a\\\\b")=False`。
- 判定：M3 的 deny glob 若含 `\` 会静默失配；M4 有 replace 兜底，M3 没有。算子必须双替换后再匹配。

### D-10 minimatch 自身不是干净的归一器

- 实测：`minimatch("./a/b","a/b")=False`、`minimatch("a/../a/b","a/b")=True`、`minimatch("a/b","a/../b")=False`、`minimatch("a//b","a/b")=True`、`minimatch("a/b/..","a")=False`。
- 判定：不能把原始声明串直接当输入。必须先归一（否则两条实现各自的 `..`/`./` 巧合会产生不同结论）。

### D-11 前导 `!` 取反

- 实测：`minimatch("foo/bar","!foo")=True`、`minimatch("foo","!foo")=False`（minimatch 支持 `!pattern` 取反）。
- 判定：仓内**没有任何**调用点禁止前导 `!`。一个 `write_scope: !foo` 会匹配几乎所有路径（语义反转）。写面语法应显式拒绝。

### D-12 尾 `/` 与目录形式

- 实测：`minimatch("src","src/")=False`、`minimatch("src/a.ts","src/")=False`；而 `path.resolve` 会去掉尾 `/`（M1/M4 字面分支受益），M4 的 glob 分支**不**去尾 `/`。
- 判定：`write_scope: src/`（含 `/` 但仍可能无 magic → 走字面分支）与 `write_scope: src/*/`（magic → glob 分支，尾 `/` 保留）行为不同。

### D-13 扩展语法覆盖不一致

- 证据：`GLOB_MAGIC_RE = /[*?[\]{}]/` **不含 `(`**；`isWithinScope` 不用 minimatch。
- 实测：`minimatch("a","@(a|b)")=True`、`minimatch("a/b","{a,b}/b")=True`、`minimatch("a.ts","a.{ts,tsx}")=True`。
- 判定：`@(a|b)` 会被 M4 判为**无 magic 字面项**（整体当一个路径），而 M3 会当 minimatch 处理；`read_scope` allow 项则永远当字面路径。

### D-14 Python fnmatch vs TS minimatch（跨语言核心分叉）

- 证据：`xkey.py:1084 return fnmatch.fnmatch(target, pattern)`；对照 `read-scope.ts:146` minimatch。
- 实测对照表：

| path | glob | `fnmatch` (Py, win32) | `minimatch` (TS 10.2.5) |
|---|---|---|---|
| `a/b/c.ts` | `a/*.ts` | **True** | **False** |
| `a/b.ts` | `a/*.ts` | True | True |
| `A/B.TS` | `a/b.ts` | **True**（normcase） | **False**（默认敏感） |
| `a/.x/b` | `a/**` | **True**（无 dot 概念） | **False**（`dot:false`） |
| `packages/x/y.ts` | `packages*` | **True** | **False** |
| `a/b` | `a/**/*` | **False**（`**`→`.*`，多要一段） | **True**（`**` 可零段） |
| `a/b.ts` | `a/**/*.ts` | **False** | **True** |
| `a` | `a/**` | False | False（两处都打补丁） |

- 判定：**Python 侧绝不能用 `fnmatch` 实现写面匹配**；必须自写标准归一 + 段匹配，或引入与 minimatch 等价的实现。这是 `spec.md` 风险 1 的最硬实例。

### D-15 空面 / 未声明面的三态

- 证据：`read-scope.ts:48-51`（"A present-but-empty list blocks every read-ish call (fail-closed on a misconfigured task). null = deny-only mode"）；`worker-mode.ts:1648-1662`（`writeScope !== undefined && !writeScope.some(...)` → block）。
- 判定：读面有 `undefined`（零拦截）/ `[]`（fail-closed 全拦）/ 非空 三态；写面 `write_face` 需要自己的三态定义（建议见 §3.3）。

### D-16 allow 与 deny 的优先关系（既定）

- 证据：`read-scope.ts:167-183`（deny 先于 containment，`rule=deny-glob`）；`worker-mode.ts:1624-1662`（deny → 默认面 → `write_scope` 交集）；`packages/multi-workers/README.md:145`（"`ignore.deny_globs` 作为上下文防火墙（deny 优先于 allow）"）。
- 判定：**deny 优先**已是全仓一致语义，写面沿用。

---

## 3. 归一建议（每差异取哪一侧 + 理由）

### 3.1 规范语法（`write_face` 唯一定义）

```
write_face := entry ("," entry)*        # 单行；或 YAML 块列表（两者等义）
entry      := segment ("/" segment)*
segment    := "**" | charpat
charpat    := (LIT | "*" | "?" | "[" class "]" | "{" alt ("," alt)* "}" | "@(" alt ("|" alt)* ")")+
```

解析期规则（fail-closed，违反即拒绝派发，零副作用）：

| 规则 | 处置 | 理由 |
|---|---|---|
| `\` | 一律视为分隔符并转 `/`（**不是**转义） | D-9；Windows 主平台，防止 M3 式静默失配 |
| 前导/内嵌 `!` | 拒绝（`write-face-invalid-entry`） | D-11；取反会让集合语义反转 |
| `..` 段 | 拒绝（`write-face-escape`） | D-5；越过 base 无法词法比较 |
| 绝对路径 | 若在 base 下则相对化，否则拒绝（`write-face-outside-base`） | D-4；根锚定必须单义 |
| 尾 `/` | 去掉 | D-12；`src/` 在 minimatch 下几乎匹配不到东西 |
| 前导 `./`、空段（`//`） | 归一掉 | D-10；minimatch 自身不归一 |
| 空 entry（`,,`） | 忽略 | 与 `write_scope` 解析一致（`worker-mode.ts:449` `.filter((item) => item.length > 0)`） |
| `,` 出现在 entry 内 | 拒绝（无转义语法） | D-8 |

| 语义点 | 取值 | 理由 |
|---|---|---|
| 段分隔 | `/` | 与既有渲染/解析一致 |
| `**` | **标准零或多段**；`a/**` **包含** `a` | 与 D-2 两处既有补丁同向；用户直觉 |
| 中段 `**` | `a/**/b` 含 `a/b` | 实测 `minimatch("a/c","a/**/c")=True` |
| 段内 `**`（如 `a**b`） | 按 `*` 处理（不跨段） | 实测 `minimatch("axb","a**b")=True`、`minimatch("a/x/b","a/**b")=False` |
| 字面项 | **精确节点**；目录必须显式写 `/**` | 取消 D-6/D-7 的"magic 分支"；算子才能用一套语法。代价：存量 `write_scope: <dir>` 语义不同，但 `write_face` 是新字段，不影响存量（`write_scope` 保持原行为） |
| 大小写 | win32 **不敏感**，其它平台敏感；以**显式参数** `caseInsensitive` 传入 | 与 D-1 的 `isSameOrUnder` 侧一致；Windows fs 不敏感（`Packages/Foo.ts` vs `packages/foo.ts` 真会撞）。显式参数让 parity 语料可同时锁两种模式 |
| 点段 | **`dot:true`**（`.` 开头段按普通段处理） | `.agenticdoc`/`.pi`/`.github` 是真实目录；`dot:false` 会让 `**` 静默变窄（D-3），且与"写真实路径"的语义不符。范围仅限新字段，不改 read_scope/deny_globs 默认 |
| 基 | 单一 base（相对仓库根 / worker cwd）；两侧 base 不同则**不能判"无交集"** | D-4；`_expand_read_scope` 已证明相对项的根在多模式下不同义 |

> 注：`read_scope` / `deny_globs` 的既有语义**不改**（spec §1.4 / AC-012）。本节只定义 `write_face`。

### 3.2 deny 优先？交集里 deny 如何参与？（明确回答）

**运行时：deny 优先（沿用 `read-scope.ts:167-183` 与 `worker-mode.ts:1624-1636`）。**
有效写集 `W(face) = (∪ allow) \ (∪ deny)`。

**交集判定：推荐 deny 不参与——`A.deny` 遮盖 `A.allow ∩ B.allow` 时仍判"重叠"。**

理由：

1. **方向必须是 fail-closed**（`spec.md §2.3`：写面判定不得放宽既有拦截）。把 deny 当"扣减项"去主张"不重叠"，等于让一道**安全网**去放宽**并发容量**——语义耦合。
2. **判定对 deny 单调**：加/删一条 deny 永远不改变 `write_faces_overlap` 的结论。这使判定结果可缓存、可复现，也避免了"同一批卡在不同 tick、target.yml 改一行 deny 后判出不同结果"。
3. **deny 的来源是多变的**（`dispatch.py:922-928 _resolve_deny_globs` 默认取 `target.yml ignore.deny_globs`；PM 侧 `task-dispatcher.ts:212-213/270-271` 也会注入）。把它纳入并发 gate 会让并发度随配置漂移。
4. **成本可接受**：deny 通常是"更窄的额外禁令"（`DerivedDataCache/**`、`**/*.uasset`）。allow∩allow 为空才是真正的强证据；deny 只影响极少数"allow 面几乎重合、deny 恰好完全遮盖"的边角。

**可选精化（记为 residual，不作为 RQ-D1 结论）：** 若将来要减少假阳，可加一个 glob-containment 子判定：仅当能**证明** `A.allow∩B.allow ⊆ A.deny ∪ B.deny` 时才降级为"不重叠"。这需要新的 `globSubset(g1,g2)` 算子（同样可用 §4 的 NFA 补集/包含技巧），不在本 RQ 交付范围。

**保守回退清单**（任一触发即判"重叠"，不判"无交集"）：

- 任一侧 face **未声明**（`write_face` 头缺失）→ 由 D-003 的 serial-only 处置，算子**不**返回 None；
- 任一侧含**不受支持语法**（extglob 取反 `!(...)`、`+()`/`*()`/`?()`、非法 class、嵌套 brace 深度超限）；
- 任一侧含**绝对路径且不在同一 base 下**；
- 段级字符模式交集触发**递归/长度上限**；
- 两侧 base 经 `normcase` 不等。

### 3.3 三态定义

| `write_face` 头 | 语义 | 处置 |
|---|---|---|
| 缺失 | 未声明 | D-003 serial-only：不得与同 key 任一在飞并行；写审计行 `write-face-undeclared`；**不拒绝** |
| 存在但空 | 空写集（misconfig） | **解析拒绝** `write-face-empty`（零副作用）。理由：空面 worker 什么也写不了，若当作"空集=无交集"会让两个坏 worker 静默并行（与 `read_scope` 的 present-but-empty fail-closed 同向，`read-scope.ts:48-51`） |
| 非空 | 正常 | 走 §4 算子 |

---

## 4. 交集算子规范 `write_faces_overlap`

### 4.1 输入模型

```ts
interface WriteFace {
  allow: string[];          // 已按 §3.1 归一/校验的 glob（段数组形式，见下）
  deny: string[];           // 同上；算子默认不使用（§3.2）
  base: string;             // 绝对路径，单一根
  caseInsensitive: boolean; // win32 传 true
}
type Segment = "**" | CharPattern;         // CharPattern = token 序列
type Glob = Segment[];
```

预处理器 `parseFace(entry, base, caseInsensitive) -> Glob | REFUSE`：按 §3.1 执行全部解析期规则。
**只在同一 base + 同一 `caseInsensitive` 下比较**；否则返回 `UNKNOWN`（保守重叠）。

### 4.2 段级字符模式交集

```text
segOverlap(a: CharPattern, b: CharPattern) -> witness:string | NONE | UNKNOWN
  # token 集合：LIT(c) | STAR | QMARK | CLASS(charset, negated)
  # 记忆化窗口匹配（两模式同时消耗一个段内的字符流）
  #   - LIT/LIT：按 caseInsensitive 折半比较，相等则消耗一个字符
  #   - LIT/CLASS、QMARK/CLASS：成员判定（negated 取反；caseInsensitive 下折半比较）
  #   - STAR：可吞 0..n 个字符；用记忆化避免指数（|a|,|b| <= 256 时总是可行）
  #   - CLASS/CLASS：两集合交非空时取任一公共字符
  # 返回：两模式都能生成的**具体字符串**（LIT→原字符；STAR→"x"；QMARK→"x"；CLASS→首个允许字符）
  # 上限：递归深度/步数超限 → UNKNOWN（调用方保守视为重叠）
```

### 4.3 glob（段序列）交集：两条 ε-NFA 的乘积

`**` 的 NFA：状态 i 上 `i --ε--> i+1`（吞 0 段）且 `i --ANY--> i`（吞 1 段，自环）。
普通段：`i --seg--> i+1`。

```text
globsOverlap(A: Segment[], B: Segment[]) -> path:string[] | NONE | UNKNOWN
  # 乘积状态 (i,j)，i∈0..|A|, j∈0..|B|
  # 迁移：
  #   ε:     A[i]=="**" -> (i+1, j);  B[j]=="**" -> (i, j+1)
  #   消费:  consumeA(i) = [ (ANY, i) ]           若 A[i]=="**"
  #                       [ (A[i], i+1) ]         否则 (i<|A|)
  #          consumeB(j) 对称
  #          若 symbolCompatible(sa, sb) -> 迁移到 (ia', jb')
  #             sa==ANY 或 sb==ANY        -> 兼容，witness = 另一侧的具体见证段
  #             否则 witness = segOverlap(sa, sb)
  #             segOverlap 返回 UNKNOWN -> 整条搜索标记 UNKNOWN
  # 接受: 到达 (|A|, |B|) 且路径上**至少 1 条消费边**（路径非空）
  # 判定: 达接受 -> 重建见证段序列 = path（非空交集，词法可证）
  #       未达接受且无 UNKNOWN -> NONE（词法可证无交集）
  #       任意 UNKNOWN 且未达接受 -> UNKNOWN（保守）
  # 复杂度: 状态数 (|A|+1)*(|B|+1)，BFS 线性；典型 face < 20 段，单次判定微秒级
```

关键正确性点（实测校正过的两个坑）：

- `**` 必须是**自环**，否则 `globsOverlap(["**"], ["x","y"])` 会错判 NONE。
  （对照：`minimatch("a/b","**")=True`。）
- `**` 的**零段**展开必须允许，否则 `a/**/b` vs `a/b` 会错判 NONE。
  （对照：`minimatch("a/c","a/**/c")=True`。）
- `a/**` 在 §3.1 下已被规范化成 `["a","**"]` 且**含裸 `a`**，所以 `globsOverlap(["a","**"],["a"])` 经 `**` 零段展开 → 覆盖 `a`。
  （对照：裸 minimatch 是 False，两处消费者靠补丁补上，见 D-2。）

### 4.4 面级算子

```text
write_faces_overlap(a: WriteFace, b: WriteFace) -> Conflict | None
  # Conflict = { sample: string, rule: string, other: string, reason: string }

  # 0. 前置：两侧都必须已声明（未声明由 D-003 serial-only 处理，不走本函数）
  #    两侧 base 必须 normcase 相等且 caseInsensitive 相同，否则 -> Conflict(reason="incomparable-base")
  # 1. 若 a.allow 为空 或 b.allow 为空 -> return None            # 空写集不可能冲突
  # 2. for ga in a.allow:                                        # 文档序，输出确定
  #       for gb in b.allow:
  #           w = globsOverlap(ga, gb)
  #           if w == NONE: continue
  #           if w == UNKNOWN: return Conflict(sample="<unknown>", reason="unsupported-syntax")
  #           return Conflict(sample=join(w, "/"), rule=ga, other=gb)
  # 3. return None
```

- **deny 不参与**（§3.2）；`Conflict` 的 `sample` 是词法见证（通配符替换成具体字符），**不保证磁盘上存在**，只作 PM 可读的冲突样例（design.md D-008 的"冲突路径样例"）。
- `NONE` 是**可证无交集**（在 §3.1 的词法模型内，搜索穷尽）；`UNKNOWN` 一律当重叠。
- 复杂度：`O(N_inflight × |allowA| × |allowB| × |A| × |B|)`。写面通常 ≤ 5 entry × ≤ 6 段，单次远低于 `spec.md §2.2` 的 10ms 预算。

---

## 5. 边界向量集

> A/B 均为 `allow`（除非注明 deny）；期望列按 §3.1 归一后的语义。涉及 minimatch/fnmatch 的"实测"见 `[VERIFY]`。
> **风险列**标 `Py/TS` 的条目是两端最容易分叉的。

| # | A | B | 期望（§3.1） | 理由 | Py/TS 风险 |
|---|---|---|---|---|---|
| V01 | `packages/x/**` | `packages/x/y.ts` | 重叠 | `**` 跨段 | |
| V02 | `packages/x/**` | `packages/y/**` | 不重叠 | 首段不同（段边界） | |
| V03 | `packages/x/**` | `packages/x` | **重叠**（sample `packages/x`） | §3.1 `a/**` 含裸 `a` | **高**：裸 minimatch=False，需与两处补丁同向 |
| V04 | `packages/x/**` | `packages/X/**` | win32 重叠 / posix 不重叠 | `caseInsensitive` 参数 | **高**：minimatch 默认敏感、fnmatch win32 不敏感 |
| V05 | `a/**/*.ts` | `a/b.ts` | 重叠 | `**` 可零段（实测 minimatch=True） | **高**：fnmatch=False |
| V06 | `a/*.ts` | `a/b/c.ts` | 不重叠 | `*` 不跨 `/`（实测 minimatch=False） | **最高**：fnmatch=True |
| V07 | `a/*.ts` | `a/b.ts` | 重叠 | 单段通配 | |
| V08 | `a/**/b` | `a/c/b` | 重叠 | 中段 `**` | |
| V09 | `a/**/b` | `a/b` | 重叠 | `**` 零段 | |
| V10 | `**` | `packages/x/y.ts` | 重叠 | `**` 全匹配 | |
| V11 | `**` | `.agenticdoc/k/x.md` | 重叠 | §3.1 取 `dot:true` | **高**：minimatch 默认 `dot:false` |
| V12 | `.agenticdoc/k/evidence/**` | `.agenticdoc/k/evidence/report.md` | 重叠 | 实际 live 形状 | |
| V13 | `.agenticdoc/k/evidence` | `.agenticdoc/k/evidence/report.md` | **不重叠** | §3.1 字面=精确节点 | **高**：旧 `write_scope` 字面分支=目录包含 |
| V14 | `a/b.ts` | `a/b.ts` | 重叠 | 同文件不同写法 | |
| V15 | `a/b.ts` | `a/**` | 重叠 | `**` 覆盖 | |
| V16 | `a/b.ts` | `a/b.tsx` | 不重叠 | 文件名不同 | |
| V17 | `a/**` | `a/**` | 重叠（sample `a/x`） | 恒等 | |
| V18 | `**/*.ts` | `packages/**/*.py` | 不重叠 | 扩展名互斥 | |
| V19 | `**/*.ts` | `packages/**/foo.ts` | 重叠 | 交集非空 | |
| V20 | `a/{b,c}/**` | `a/c/x.md` | 重叠 | brace 展开 | **中**：`GLOB_MAGIC_RE` 含 `{}`，但 Python 侧需自实现 |
| V21 | `a/b*/**` | `a/bc/x.ts` | 重叠 | 段内 `*` | |
| V22 | `a/b?/**` | `a/bc/x.ts` | 重叠 | `?` 单字符 | |
| V23 | `a/[bc]/**` | `a/c/x.ts` | 重叠 | 字符类 | **中**：`read_scope` allow 不认 glob |
| V24 | `a/[!bc]/**` | `a/c/x.ts` | 不重叠 | 类取反 | **中** |
| V25 | `DerivedDataCache/**` | `Content/DerivedDataCache/**` | 不重叠 | 首段锚定不同 | |
| V26 | `packages/x/**` | `packages/x/../y/**` | 拒绝（`write-face-escape`）/ 若不拒则保守重叠 | `..` 不可词法判定 | **高**：minimatch `..` 行为不一致 |
| V27 | `packages/x/**` | `H:/git/packages/x/y.ts` | 重叠（若同 base 相对化）否则拒绝 | 绝对路径须可相对化 | **高**：M4 双基、M3 realpath |
| V28 | `packages/x/**` | `./packages/x/y.ts` | 重叠 | 去前导 `./` | **高**：裸 minimatch=False |
| V29 | `packages//x/**` | `packages/x/y.ts` | 重叠 | 并空段 | **中**：minimatch 恰好=True，但不应依赖 |
| V30 | `packages/x/` | `packages/x/y.ts` | **不重叠**（尾 `/` 去掉后为精确节点 `packages/x`） | §3.1 字面=精确 + 去尾 `/` | **高**：`src/` 在 minimatch 恒 False |
| V31 | `src\\x\\**`（反斜杠） | `src/x/y.ts` | 重叠 | `\`→`/` 归一 | **高**：裸 minimatch 把 `\` 当 escape=False |
| V32 | `!packages/x/**` | `packages/x/y.ts` | 拒绝（`write-face-invalid-entry`） | 禁取反 | **高**：minimatch 会当取反=True |
| V33 | `a/**` | `a` | 重叠 | 同 V03，`**` 零段 | **高** |
| V34 | `a/**` | `a/b/c/d.ts` | 重叠 | `**` 深跨段 | |
| V35 | `a/**` | `a/**/*` | 重叠 | 后者是前者子集 | |
| V36 | `a/**/*` | `a` | **不重叠** | 至少需 `a/<seg>`（实测 `minimatch("a","a/**/*")=False`） | **高**：`**` 零段实现差会算错 |
| V37 | `a/**` | `a/b`（deny(A)=`a/**`） | **重叠（保守）** | §3.2 deny 不参与 | **高**：若误把 deny 当扣减会判不重叠 |
| V38 | `a/**` | `a/b`（deny(A)=`a/b`） | **重叠（保守）** | 同上 | **高** |
| V39 | `packages/**` | `packagesx/**` | 不重叠 | 段边界（`packages` 不是 `packagesx` 的前缀单元） | |
| V40 | `a/**` | `A/B`（caseInsensitive=true） | 重叠 | win32 折半比较 | **高** |
| V41 | `a/**` | `A/B`（caseInsensitive=false） | 不重叠 | posix 敏感 | **高** |
| V42 | `a/**/*.ts` | `a/.x/b.ts` | 重叠（`dot:true`） | 点段普通化 | **高**：minimatch 默认 False |
| V43 | ``（present-but-empty） | `packages/x/**` | 拒绝（`write-face-empty`） | §3.3 fail-closed | **中** |
| V44 | 未声明（无头） | `packages/x/**` | serial-only（算子不返回 None） | D-003 | **中** |
| V45 | `a` | `a/b` | **不重叠** | §3.1 字面=精确节点 | **高**：旧 `write_scope` 字面分支=包含 |
| V46 | `packages/x/**` | `packages/x/y.ts` | 重叠（sample `packages/x/y.ts`） | 基本样例格式 | |
| V47 | `a/**` | `a/b`（模式侧 `a/**/**`） | 重叠 | 多 `**` 折叠（实测 `minimatch("a/b","a/**/**")=True`） | **中** |
| V48 | `a/b/**` | `a/b` | 重叠 | 尾 `/**` 含裸目录 | **高**：裸 minimatch=False（实测 `minimatch("a/b","a/b/**")=False`） |

**最容易分叉的 6 类**（按风险降序）：

1. V06 / V22 系：段内 `*` 是否跨 `/`（fnmatch 跨，minimatch 不跨）。
2. V04 / V11 / V40 / V41 / V42：大小写 + 点段（minimatch 默认敏感 + `dot:false`；fnmatch win32 不敏感 + 无点概念）。
3. V03 / V33 / V48：`a/**` 是否含裸 `a`（裸匹配器都是 False，靠补丁；新实现必须显式同向）。
4. V05 / V36：`**` 的零段展开（fnmatch `**`→`.*`，`a/**/*.ts` 多要一段）。
5. V13 / V45：字面项是精确节点还是目录包含（旧 `write_scope` 是后者，新 `write_face` 建议前者）。
6. V26 / V27 / V28 / V29 / V31：`..`/绝对/`./`/`//`/`\` 的词法归一（不能依赖 minimatch 自身的偶然行为）。

向量表含 **48 条**（要求 ≥ 20），其中标 `Py/TS` 风险 **28 条**。

---

## 6. 残留与未验证

- **R-1（残余风险，未验证）**：算子只做**词法**判定；symlink/junction 可使两条词法不相交的面在磁盘上指向同一文件（`read-scope.ts:100-116` 的 realpath 证明运行期会折叠）。本 RQ 未构造 junction 对拍，属 RQ-D2（运行期闸）面。缓解方向：派发层算子保持保守 + 运行期 realpath 复算（后者未设计）。
- **R-2（未验证）**：`spec.md` 风险 1 列的"7 处分歧"与本文件 D-1..D-16 的映射未逐条对照到 design.md；`spec-write-face-enforcement-20261014.md` §3.4 的 D-1..D-7 与本文件编号不同（本文件更细）。回填 design.md 时以本文件为准。
- **R-3（未验证）**：`fnmatch` 之外的 Python 侧匹配（如 `pathlib.PurePath.match`）未在本仓出现（grep `.match(` 全部命中 `re` 对象）；因此"M5 是仓内唯一 Python glob 匹配器"这一结论限于当前工作树。若未来引入 `pathspec`/`wcmatch` 等库，需要重新核对语义。
- **R-4（未验证）**：`dot:true` 建议对 **Windows 上真实存在的点目录**（`.agenticdoc` 已由字面段覆盖，故影响面主要在其他 `**` 通配）的实际使用率未统计；未对 live `write_scope` 语料做 `**` 统计。
- **R-5（未验证）**：段级 `segOverlap` 的字符类/brace 组合在极端输入（>256 字符、嵌套 brace）下的性能与正确性未跑原型；本 RQ 只给伪码，**未实现也未跑测试**。
- **R-6（未验证）**：`deny` 不参与判定的"可选精化"（glob containment）可行性未验证；需要新算子，未设计。
- **R-7（未验证）**：`caseInsensitive` 显式参数的**传递链**（谁读 `target.yml`/平台并把它送进两条通道的算子）未设计；属 plan/D-009 parity 面。
- **R-8（已知）**：`examples/extensions/sandbox/index.ts` 的 `allowWrite`/`denyWrite`（`spec-write-face-sources-20261014.md` §4bis E1）提供"路径白名单"的既有形态参照（相对根、deny 优先、OS 级兜底），但**与写面链路零耦合**，本 RQ 未复用其代码。

## 7. 未覆盖面声明

1. 未运行任何生产/测试套件；本文件全部结论为静态读码 + 独立复现最小样例（minimatch / fnmatch 直接调用），**未启动 worker、未派发任务**。
2. 未改任何生产文件；唯一写面是本文件（`write_scope` 允许的 `<key>/evidence` 内）。
3. 未覆盖 `packages/coding-agent/test/**` 的既有断言语义（只作为"冻结行为"引用：`test/suite/autopilot-read-scope.test.ts`、`test/suite/mwds-t03-bash-write-scope.test.ts`）。
4. 未覆盖 RQ-D2 的运行期插入点与 bash 写目标词法；未覆盖 `implementation-gate.ts` / `worker-file-tool.ts` 的目标提取算法（只引用其存在与语义）。
5. 未覆盖 `dist/` 构建产物与 `src` 的字节等价性（只把 dist 当滞后副本，未作判据）。
6. 未覆盖 dual/partition 模式下两侧 base 的实际取值链（只引用 `_expand_read_scope` 的既有展开规则）。
7. 未覆盖 xkey gate v2 `write_scope` 的完整消费面（只引用 `gates.py` + `conductor.py:6514-6526` 的 `blast_radius ⊆ write_scope`）。
8. 未实现 §4 的算子原型，因此 §5 向量表的"期望"列是**设计约定**，不是实测；实测列只覆盖 minimatch/fnmatch 的原始行为。

---

## [VERIFY]

实测命令（Windows，repo root `H:/git/Multi-Workers`）：

```
[VERIFY] D1-minimatch-version: minimatch/package.json version=10.2.5; resolve=H:\git\Multi-Workers\node_modules\minimatch\dist\commonjs\index.js
         pin: packages/coding-agent/package.json:61 "minimatch": "10.2.5"
[VERIFY] D1-minimatch-samples (const {minimatch}=require('minimatch')):
  minimatch("a/b/c.ts","a/*.ts")            = false
  minimatch("a/b.ts","a/*.ts")              = true
  minimatch("a","a/**")                     = false
  minimatch("a/b","a/**")                   = true
  minimatch("A/B.TS","a/b.ts")              = false
  minimatch("A/B","a/b",{nocase:true})      = true
  minimatch("a/.x/b","a/**")                = false
  minimatch("a/.x/b","a/**",{dot:true})     = true
  minimatch("a/b","a")                      = false
  minimatch("src/a.ts","src\\*.ts")         = false
  minimatch("src/a.ts","src/*.ts")          = true
  minimatch("a/b","a/../a/b")               = true
  minimatch("./a/b","a/b")                  = false
  minimatch("a//b","a/b")                   = true
  minimatch("a/b/..","a")                   = false
  minimatch("packages/x/y.ts","packages*")  = false
  minimatch("packages/x/y.ts","packages/**")= true
  minimatch("a/b","a/**/*")                 = true
  minimatch("a","a/**/*")                   = false
  minimatch("a/b","a/b/**")                 = false
  minimatch("a/b/c.ts","a/**/*.ts")         = true
  minimatch("a/b.ts","a/**/*.ts")           = true
  minimatch("foo/bar","!foo")               = true
  minimatch("foo","!foo")                   = false
  minimatch("a","@(a|b)")                   = true
  minimatch("a/b","{a,b}/b")                = true
  minimatch("a.ts","a.{ts,tsx}")            = true
  minimatch("C:/x/a.ts","**/*.ts")          = true
  minimatch("axb","a**b")                   = true
  minimatch("a/x/b","a/**b")                = false
  minimatch("a/b","a/**/**")                = true
[VERIFY] D1-python-fnmatch-samples (python -X utf8, platform win32, os.name nt):
  fnmatch("a/b/c.ts","a/*.ts")   = True     # TS minimatch = false  <-- CORE FORK
  fnmatch("a/b.ts","a/*.ts")     = True
  fnmatch("a","a/**")            = False
  fnmatch("a/b","a/**")          = True
  fnmatch("A/B.TS","a/b.ts")     = True     # win32 normcase
  fnmatch("a/.x/b","a/**")       = True     # no dot concept
  fnmatch("a/b","a")             = False
  fnmatch("packages/x/y.ts","packages*")    = True   # TS minimatch = false  <-- FORK
  fnmatch("packages/x/y.ts","packages/**")  = True
  fnmatch("a/b","a/**/*")        = False    # TS minimatch = true   <-- FORK
  fnmatch("a","a/**/*")          = False
  fnmatch("a/b/c.ts","a/**/*.ts")= True
  fnmatch("a/b.ts","a/**/*.ts")  = False    # TS minimatch = true   <-- FORK
  fnmatch.translate("a/*.ts")    = (?s:a/.*\.ts)\z   # '*' -> '.*' crosses '/'
[VERIFY] D1-implementations: read_scope allow = isWithinScope/isSameOrUnder only (read-scope.ts:118-121, no minimatch);
         deny_globs = dual-basis minimatch (read-scope.ts:141-160); write_scope = GLOB_MAGIC_RE branch (worker-mode.ts:1564/1587/1598);
         python glob matcher sites in packages/multi-workers/**/*.py = 1 (xkey.py:1075-1084 fnmatch); no shared/read-scope.ts exists
[VERIFY] D1-intersection-operator-sites: grep 'overlap|intersect' in multi-workers/**/*.py + agent-team-loop/**/*.ts = 2 hits
         (worker-mode.ts:320, :1604), both prose; write_scope hits in dispatch.py = 0
[VERIFY] D1-dot-option-sites: minimatch call sites with an options object in read-scope.ts + worker-mode.ts = 0
         (read-scope.ts:146, :153; worker-mode.ts:1591, :1594 all two positional args)
[VERIFY] D1-frozen-patch-sites: read-scope.ts:147-153 (trailing '/**' also denies the dir itself)
                                 worker-mode.ts:1592-1594 (same patch on the write side)
[VERIFY] D1-vector-count: 48 rows in §5 (requirement >= 20); Py/TS-fork rows marked = 28
[VERIFY] D1-deliverable: .agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md (this file)
```
