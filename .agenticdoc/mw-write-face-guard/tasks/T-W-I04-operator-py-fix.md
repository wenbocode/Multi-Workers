# T-W-I04 · 算子修正（Python）：D-111 优先级 + D-112 条目切分（B0 返工）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` — 核心交付是「一个常驻 mw 服务 + 多 Worker 并行开发同一个项目」，其前提是同文件多写者对 = 0。本卡修的是该前提的**判定层**：B0 算子在两语言一致性与拒绝形状上的实测缺陷。判定错了，后面所有闸门都建在错的判定上。
- B0 的 Python 算子 `packages/multi-workers/autopilot/write_face.py` 已交付（99 用例全绿），但 PM 用**随机差分 + 定位矩阵**独立复算后发现了缺陷，并把契约锁进扩展后的语料（`parse` 16→23、`overlap` 49→58）。证据：`.agenticdoc/mw-write-face-guard/evidence/PM-parity-differential-20261014.md`（§1–§5 是实测，§4 是裁定）。
- **定位锚点**: `autopilot/write_face.py:122`（`WriteFace` 数据类，含 `allow`/`allow_entries`/`deny`）、`autopilot/write_face.py:152`（`Conflict`）、`autopilot/write_face.py:163`（`Unsupported`）、`autopilot/write_face.py:909`（`overlap()` 内的归一入口）。
- 裁定条目（`design.md`，必须逐条实现）：
  - **D-111 parse 期**：硬规则违规（`write-face-escape` / `write-face-invalid-entry` / `write-face-outside-base`）**优先**，且**与条目顺序无关**；不受支持语法条目只记录，**不得截断后续条目校验**。
  - **D-111 overlap 期**：**先证冲突**——能给出 glob-free witness 就返回 `Conflict`；只有证不出冲突且任一侧含不受支持语法时才返回 `Unsupported`。
  - **D-112 切分**：头部值先 `split(',')` 切字段、逐个 trim 后各自解析；**切分语法无感**。未闭合的 `[` **不得**吞掉后续字段。
- PM 实测的 Python 现状（`evidence/PM-parity-differential-20261014.md` §3 + 语料实测）：

| 语料行 | 期望 | Python 现状 |
|---|---|---|
| `P22`（`write_face: src/[a-, src/ok.ts`） | entries `["src/[a-", "src/ok.ts"]` | 单个合并条目 `"src/[a-, src/ok.ts"`（未闭合 `[` 吃掉了逗号与后一个字段） |
| `P23`（`write_face: src/[a-, src/b].ts, src/ok.ts`） | entries `["src/[a-", "src/b].ts", "src/ok.ts"]` | 被 `[` 吞成 1 个条目 |
| `V52`/`V53` | `reject:write-face-escape`（两种书写顺序同 code） | 已通过 |
| `V54` | `reject:write-face-invalid-entry` | `unsupported`（`!src/x` 被吞掉，从未被校验） |
| `V55`/`V56` | `reject:write-face-outside-base` | `unsupported` |
| `V57` | `overlap`（可证冲突优先） | `unsupported` |

## 写入允许面

- `packages/multi-workers/autopilot/write_face.py`
- `packages/multi-workers/test_write_face.py`

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/test/fixtures/write-face-corpus.json` **只读**（PM 冻结的契约，本卡的实施目标就是让代码满足它，而不是让语料适应代码——发现语料本身有问题就报回 PM，不要改）；`autopilot/dispatch.py`（W-03 在写）、`packages/coding-agent/**`（TS 侧属 T-W-I05）、`mw_common.py`（其它 session 正在追加）。

## 要求

1. 满足冻结语料的**全部**新行（`P17`–`P23`、`V49`–`V57`），并且**不许**为了过语料而改动任何旧行的既有期望。
2. `parse_write_face` 的条目切分改为 D-112：按原始头部值 `split(',')`，逐字段 `strip`，丢空字段；**不得**让 `[`/`{` 影响切分（`P22`/`P23` 是反例，`P21` 证明 `{` 未闭合时逗号**仍**切分）。
3. parse 期校验**遍历全部字段**后再决定结果：任何硬违规胜出（多个硬违规时按**字段顺序**取第一个，保证同 face 任一书写顺序同 code）；不受支持字段只进入 face 的"未知"集合，绝不短路后续字段。
4. overlap 期顺序改为 D-111：先在**受支持**条目之间求可证冲突（返回 glob-free witness 的 `Conflict`）；证不出时若任一侧存在不受支持条目则返回 `Unsupported`；否则 `None`。
5. `deny` 依旧**不参与**判定（旧行 V37/V38 必须继续通过）。
6. 保持既有公开 API 名称/返回类型形状不变（`parse_write_face` / `globs_overlap` / `WriteFace` / `Conflict` / `Unsupported` / `Refused` / `Undeclared`）；若确实需要新增字段，只许**追加**可选字段，不得改既有字段名。
7. 不新增第三方依赖；不用 `fnmatch`/`pathlib`（旧守卫用例必须继续通过）。

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-write-face-guard/evidence/W-04-operator-py-fix.md`，必须包含：① 修正前后对 `P22`/`P23`/`V54`/`V55`/`V56`/`V57` 的**实测**输出对照（命令 + 原文，不许写推算）；② 全语料通过计数；③ 针对 D-112 的反例用例说明（为什么"括号感知切分"是错的）；④ `## 改动历史`
- 代码：`autopilot/write_face.py` + `test_write_face.py`
- 测试结论必须是实跑原文（命令 + 尾部计数）

## 验收命令

```bash
cd packages/multi-workers; python -m pytest test_write_face.py -q
```
（**只跑这个文件**：包级 `pytest -q` 会带上 W-03 正在改的 `dispatch.py` 的测试，那些红/错不由本卡负责，也不要试图去修。）

## 改动历史

证据文件里必须给出 `## 改动历史`：每个改动点的 `file:line` before→after（不许写"见 diff"）；若切分与校验被重构成新函数，列出新函数的行号区间与旧行的去向。

## 硬约束

- 只用顶层 import；不写内联动态 import；不写 `any`（无类型标注的 Python 除外，本卡是 Python）。
- 本卡是**修正卡**：不许顺手扩大范围（不碰 `dispatch.py`、不碰 TS、不动语料）。
- 不跑仓库根 `npm run check`（多 session 下它会全仓 `biome --write`）。
