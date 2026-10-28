# T-W-I01 · `write_face` 交集算子（Python 侧，B0）

- type: coding
- key: mw-write-face-guard

## 写入允许面

- `packages/multi-workers/autopilot/write_face.py`（新建）
- `packages/multi-workers/test_write_face.py`（新建）

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/test/fixtures/write-face-corpus.json` **只读**（PM 已冻结的契约，改它 = 改契约，必须回到 PM）；`packages/coding-agent/**` 全只读；`packages/multi-workers/autopilot/xkey.py` 只读（那处 `fnmatch` 是另一个语义面，不在本卡范围）

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` — 核心交付是「一个常驻 mw 服务 + 多 Worker 并行开发同一个项目」。并行开发的前提是**同文件多写者对 = 0**；本卡交付该前提的第一层（作者面声明 → 机器可读 → 可判定的重叠检测）里最底层的**词法算子**，没有它就无从判断两个 worker 是否写同一批文件。
- **已冻结的契约（不要重新设计，逐条实现）**: `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`
  - §3.1 规范语法 + 解析期 fail-closed 规则表 + 语义点表（`**` 零或多段、`a/**` **含**裸 `a`、段内 `**` 按 `*`、字面 = 精确节点、`dot:true`、`\` 视为分隔符、尾 `/` 去掉）
  - §3.2 **判定里 deny 不参与**（`A.deny` 完全遮盖 `A.allow ∩ B.allow` 时仍判重叠）+ 保守回退清单
  - §3.3 三态：缺头 = 未声明 / 有头但空 = 拒绝 `write-face-empty` / 非空 = 正常
  - §4.2 段级字符模式交集、§4.3 glob 段序列的 ε-NFA 乘积、§4.4 面级算子（含 witness 与 `rule`/`other` 字段）
- **为什么 Python 侧必须自写，不得用 `fnmatch`**: `packages/multi-workers/autopilot/xkey.py:1084` 是仓内唯一 Python glob 匹配器（`fnmatch`），语义与 TS 侧不一致：`fnmatch("a/b/c.ts","a/*.ts")=True` 而 minimatch 为 `False`（`*` 是否跨 `/`）；win32 下 `fnmatch` 还会折大小写。语义基准 = minimatch（TS 侧 `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:141` 用的就是它）。
- **前置决策**: `.agenticdoc/mw-write-face-guard/design.md` D-001（载体三态）、D-006（算子语义，**已按 RQ-D1 修正 deny 方向**）、D-009（两语言一份语义 + 共享语料）。
- **下游会用它的地方**（只需知道，不要改）: conductor `packages/multi-workers/autopilot/dispatch.py`（写面闸）、doctor 计数、TS 侧 `shared/write-face.ts`（另一张卡，本卡不得碰）。

## 要求

1. **`autopilot/write_face.py`（新建）**，导出：
   - 解析期常量与拒绝码：`write-face-empty` / `write-face-invalid-entry` / `write-face-escape` / `write-face-outside-base`；
   - `parse_write_face(text, *, base, case_insensitive) -> WriteFace | ParseResult`：按 §3.1 全部解析期规则归一/校验；**三态**（缺头 → 未声明；有头空值 → `write-face-empty`；`-`（仅横线，允许两侧空白）→ **未声明**，与缺头同义）；返回已归一的分段表示，便于算子直接用；
   - `overlap(a, b) -> Conflict | None | Unsupported`：实现 §4.4（前置 base/大小写一致校验 → 逐 allow 对按**文档序**取第一个可证交集 → 返回 `Conflict{sample, rule, other, reason}`）；未声明的一侧**不进本函数**（由调用方走 serial-only）。
2. **算法必须按 §4.3 实现，不得退化成"字符串比较 + 特判"**：`**` 有自环（吞 1 段）与零段 ε 迁移；接受条件是到达 `(|A|,|B|)` **且路径至少 1 条消费边**；`**` 自环与零段展开两个坑是本卡的硬验收点（`globsOverlap(["**"],["x","y"])` 必须重叠；`a/**/b` vs `a/b` 必须重叠）。
3. **witness 必须是"具体路径"**：返回的 `sample` 里不得含 `*`/`?`/`[`/`]`/`{`/`}`（语料里每条重叠向量的 `sample_globfree: true` 断言这一点）。`<unknown>` 之类占位符不算 witness。允许重复 `**` 折叠到同一 witness。
4. **保守回退**（§3.2 清单任一命中 ⇒ 判**重叠**，不判无交集）：extglob 取反 `!(...)`、`+()`/`*()`/`?()`、非法 class、嵌套 brace 深度超限、跨 base 的绝对路径、段级交集超过步数/深度上限。每类都要有明确触发点，不得静默返回 `None`。
5. **禁用 `fnmatch`**（含 `fnmatch.fnmatch`/`fnmatchcase`/`pathlib.PurePath.match`）；只允许标准库的 `re` 与自写状态机。
6. **按冻结语料驱动实现**：读 `packages/multi-workers/test/fixtures/write-face-corpus.json`（只读），`parse` 16 行 + `overlap` 49 行必须全过。`$REPO`/`$OUTSIDE` 两个占位符按 `protocol.entries_placeholder` 替换。
7. **证据文件必须带**：语料全过计数（16/16、49/49 逐 kind：overlap 32 / none 13 / reject 3 / serial_only 1）；六组边界（`a/**` vs `a`、中段 `**`、段内 `**`、`dot:true`、win32 大小写两种模式、`a/**/*` vs `a`）的实测原文；§3.2 保守回退清单**逐条**命中样例；**deny 单调性对照**（V37/V38：加 deny 前后结论不变）；残留与未覆盖面。

## 交付格式

- 代码：`packages/multi-workers/autopilot/write_face.py`、`packages/multi-workers/test_write_face.py`
- 唯一证据文件（本卡唯一允许写入的报告路径）: `.agenticdoc/mw-write-face-guard/evidence/W-01-write-face-operator-py.md`
  结构：`## TL;DR`（≤10 行）／`## 交付物`／`## 验收输出`（pytest 原文）／`## 边界与保守回退`（逐条 `[VERIFY]`：输入原文 + 实际输出）／`## 残留与未验证`／`## 上下文来源`
- 报告里必须给出 `## 改动历史`：每个新增/修改文件的 `file:line` before→after（新增文件写"新建"）

## 验收命令

```
cd packages/multi-workers; python -m pytest test_write_face.py -q
```

（若同时想确认不回归既有 Python 套件：`python -m pytest -q`。**不要**跑 `npm run check`——它会在多 session 工作树里跑仓库级 `biome --write`。）

## 硬约束

- 只写"写入允许面"里的两个文件；语料 JSON 只读。
- 不改 `autopilot/xkey.py`、不改 `worker-mode.ts`、不改 `dispatch.py`（那些是别的卡）。
- 证据文件里的数值一律实测；推算值必须标注为推算。

## 改动历史

唯一证据文件里必须给出 `## 改动历史`：每个新增/修改文件的 `file:line` before→after；本卡两个文件均为**新建**（写"新建"）；若因实现需要在本卡写入允许面内做二次修改，按 `file:line` 逐条列出。
