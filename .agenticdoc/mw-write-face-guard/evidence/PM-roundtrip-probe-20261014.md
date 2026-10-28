# PM 往返恒等探针（2026-10-14）

**动机**：`wfg-i04-operator-py-fix` 在回执里报回一个它允许面**外**的跨卡风险——`autopilot/dispatch.py` 的 `render_write_face_line` 仍把条目用 `", "` 串成单行。D-112 把逗号定为**无条件分隔符**后，"含逗号的合法条目"就无法用单行承载。本探针把该风险从"推断"变成"实测"，并升格为 `design.md` 的 **D-113**（渲染器契约）。

## 装置（在 `packages/multi-workers` 下运行）

```python
import os, sys
sys.path.insert(0, os.path.abspath("."))
from autopilot.dispatch import render_write_face_line
from autopilot.write_face import parse_write_face, Refused
B = os.path.abspath(os.path.join(".", ".."))
for entries in (["src/x.ts"], ["a/{b,c}/**"], ["src/[a-", "src/ok.ts"]):
    line = render_write_face_line(entries)
    r = parse_write_face(line, base=B, case_insensitive=False)
    got = "reject:" + r.code if isinstance(r, Refused) else list(r.allow_entries)
    print(entries, "->", repr(line), "| re-parse ->", got, "| IDENTITY:", got == entries)
```

## 实测输出（`write_face.py` 已按 D-111/D-112 修正后）

| entries（声明面） | render 结果 | 回读结果 | 恒等 |
|---|---|---|---|
| `["src/x.ts"]` | `write_face: src/x.ts` | `["src/x.ts"]` | ✅ |
| `["a/{b,c}/**"]` | `write_face: a/{b,c}/**` | `["a/{b", "c}/**"]` | ❌ **非恒等** |
| `["src/[a-", "src/ok.ts"]` | `write_face: src/[a-, src/ok.ts` | `["src/[a-", "src/ok.ts"]` | ✅ |

## 判定

- 第二行是缺陷：声明的是 1 条目，载体里变成 2 条目，且第一条 `a/{b` 的 `{` 未闭合 ⇒ 该 face 带 unknown 条目 ⇒ 后续重叠判定被推向 `Unsupported`（拒绝）。**方向是 fail-closed**（不会放行不该放行的），但"作者声明的面被静默改写"本身就是载体缺陷，而且它让 V20 这类合法条目的声明在端到端路径上不可表达。
- 修法（D-113）：任一条目含 `,` 时，渲染器改用 §3.1 已允许的 **block-list 形态**（`write_face:` 单独一行，随后 `  - <entry>` 每行一条）；该形态已实测可被正确回读为单条目（`["a/{b,c}/**"]`）。
- 适用面：**两侧渲染器**——conductor 侧 `dispatch.py`（W-03 在写）与 PM 侧 TS 渲染器（卡 envelope → task.md 头，尚未派卡）。
- 判据形态：把"`parse(render(entries)) == entries`"写成锁定用例（含逗号条目 + 多条目 + 顺序保持），不要只测"渲染出来一行字符串长得对"。

## 未覆盖面

- 只测了 3 组条目；未穷举 §3.1 语法面。
- 未测 PM/TS 侧渲染器（尚未实现）。
- 未测 block-list 形态在**卡 envelope 侧**的抽取（`## 写入允许面` 里含逗号条目的作者面输入，属 TS 侧未派卡范围）。
