# T-W-I07 · 渲染器（Python）：逗号条目走块列表载体，锁死 parse(render(E)) == E（D-113）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 核心交付是「一个常驻 mw 服务 + 让 Worker 并行开发同一个项目」，其前提是"同文件多写者对 = 0"。渲染器是这条链的**写侧**：它把写面写进 task.md，读侧（派发闸门）再把同一行解析回来判定重叠。若 `parse(render(E)) != E`，闸门判定的是一个**作者没写过**的写面。
- **缺陷定位**: `packages/multi-workers/autopilot/dispatch.py:1055`（`render_write_face_line`）——永远用 `", ".join(...)` 拼单行；而 `autopilot/write_face.py` 的解析侧按 **D-112** 无条件按 `,` 切分（逗号永不作为模式内容）⇒ 含逗号条目必然被撕开。唯一调用点是 `dispatch.py:892`（写 task.md 头）。
- **PM 实测（`evidence/PM-roundtrip-probe-20261014.md`）**：

| 输入 entries | `render_write_face_line` 输出 | 再解析 | 恒等？ |
|---|---|---|---|
| `["a/{b,c}/**"]` | `write_face: a/{b,c}/**` | `["a/{b","c}/**"]` | **否（缺陷）** |
| `["src/x.ts"]` | `write_face: src/x.ts` | `["src/x.ts"]` | 是 |
| `["src/[a-","src/ok.ts"]` | `write_face: src/[a-, src/ok.ts` | 同左（2 条目） | 是 |

- **裁定（design.md D-113）**：渲染器契约 = `parse(render(entries)) == entries`；因为 D-112 让 `,` 成为无条件分隔符，含逗号条目**不能**走单行载体 ⇒ 必须回退到 design **§3.1 已允许的块列表形态**（每个列表项一个条目）。此契约必须由**测试锁住**，不能靠字符串形状断言。
- **块列表载体的既有先例（只读参考）**: `packages/multi-workers/test_write_face.py:53` 的 `_render_head`（`write_face:\n  - <entry>\n  - <entry>\n`）与语料行 `V20`（`a = ["a/{b,c}/**"]`）。
- **语料（PM 冻结，只读）**: `packages/multi-workers/test/fixtures/write-face-corpus.json`，`sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`、19996 B、`parse 23 / overlap 59`。含 `expect.kind == "entries"` 的 parse 行共 16 条（P01/P05–P12/P17–P23），它们的 `expect.entries` 就是**归一化后的**条目表。

## 写入允许面

- `packages/multi-workers/autopilot/dispatch.py`
- `packages/multi-workers/test/test_write_face_dispatch.py`

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/autopilot/write_face.py` 与 `packages/multi-workers/test_write_face.py` 只读（T-W-I06 正在并行改同一包）；`packages/multi-workers/test/fixtures/write-face-corpus.json` **只读**（PM 冻结契约，认为语料有错就报回 PM）；`packages/coding-agent/**` 只读；`mw_common.py` 只读（别的会话在写）；禁止 `npm run check`（全仓 `biome --write`，多会话下破坏性）。

## 要求

1. **渲染器改法**：任一条目含 `,` 时，返回块列表形态 `write_face:\n  - <entry>\n  - <entry>\n`（与 `_render_head`/`parse_write_face` 已接受的载体一致）；否则保持现有单行形态**逐字节不变**。函数返回的字符串可能含换行，请在 docstring 里写明，并核对唯一调用点 `dispatch.py:892` 的用法（作为 `lines` 的一个元素 append，仍是合法的 task.md 头，不需要改调用点；若你发现必须改调用点，就在 `残留与未验证` 里说明并给出证据）。
2. **修正测试的判据（关键）**：`test_render_and_parse_are_the_same_source`（`test/test_write_face_dispatch.py:153`）现在的判据是"渲染结果 == 单行 join 再解析"，对含逗号条目是**坏对坏**的假绿。改成**恒等契约**：`parse(render(entries)).allow_entries == entries`（`entries` 用归一化条目）。参数表必须补上含逗号条目（至少：`["a/{b,c}/**"]`、`["packages/x/**", "a/{b,c}/**"]`）。
3. **语料驱动的往返锁**：新增一条测试，遍历冻结语料里所有 `expect.kind == "entries"` 的 parse 行，断言 `parse(render(row["expect"]["entries"])).allow_entries == row["expect"]["entries"]`（16 条；只读语料，不写入）。这是 D-113 的强形式，也是"语料 + 渲染器同源"的机器锁。
4. **端到端一条**：走一次真实 `dispatch(...)`（或复用 `:164` 的 card 渲染往返测试风格），让一张**含逗号条目**的卡生成 task.md，再从磁盘上的 task.md 解析回来，断言条目与声明完全一致（含顺序）。
5. 不许在 `dispatch.py` 里复制粘贴一份解析逻辑来"绕过"（同源锁要求 render 与 parse 共用 `write_face` 模块的语义）；不许为具体语料值特判。
6. `git diff --stat` 收尾时只应出现上述两个文件。

## 交付格式

`output.md` 必须包含框架要求的五段：`结论`、`证据`、`残留与未验证`、`上下文来源`、`改动清单`。`证据` 段要给**可直接复跑的原始命令与原始输出**（至少包含 `["a/{b,c}/**"]` 的 render 输出、再解析结果、以及 16 条语料往返的计数），不要只写"已通过"。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test/test_write_face_dispatch.py -q      # 基线 25 passed；本卡后必须全绿且条数≥28
python -c "import sys; sys.path.insert(0,'.'); from autopilot import dispatch, write_face as wf; s=dispatch.render_write_face_line(['a/{b,c}/**']); print(repr(s)); print(wf.parse_write_face(s, base=r'H:/git/Multi-Workers', case_insensitive=False).allow_entries)"
git diff --stat -- packages/multi-workers/autopilot/dispatch.py packages/multi-workers/test/test_write_face_dispatch.py
```

## 改动历史

- 2026-10-14 PM 实测基线：`python -m pytest test/test_write_face_dispatch.py -q` = **25 passed**（W-03 交付时）。
- 2026-10-14 PM 实测缺陷：`render_write_face_line(["a/{b,c}/**"])` 的往返恒等为 False（见 `evidence/PM-roundtrip-probe-20261014.md`），据此立 D-113。
- 2026-10-14 语料 v3 已冻结（parse 23 / overlap 59，`sha256=b39f8925…`）；本卡只读语料。

## 硬约束

- 不跑 `npm run check`（AGENTS.md P-017）。不碰冻结语料。不改 `write_face.py`。不改 TS。
- `dispatch.py` 只有本卡一个写者（W-03 已终态，不要在本卡外并发改它）。
- 只改本卡声明允许面的两个文件；发现别处也要改就写进 `残留与未验证` 并回报。
