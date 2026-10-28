# T-W-I06 · 算子修正（Python）：状态机回退必须按「对」延迟，不得中止整轮（B0 返工 3）

- type: coding
- key: mw-write-face-guard

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 核心交付是「一个常驻 mw 服务 + 让 Worker 并行开发同一个项目」，其前提是"同文件多写者对 = 0"。本卡修的是该前提的**判定器**：Python 算子在"不可判定"与"可证冲突"并存时把可证冲突丢掉，等于让拒绝理由变成输入书写顺序的函数。
- **缺陷定位**: `packages/multi-workers/autopilot/write_face.py:936-952` —— `try:` 包住了**整个** `for ga` / `for gb` 双重循环，`except _ConservativeUnknown` 一旦命中就 `return Unsupported(...)`，于是同一个 face 里**后面那个可证的冲突对**永远不会被检查。
- **相关锚点**: `write_face.py:915`（`overlap` 入口）、`write_face.py:871-895`（`globs_overlap`，状态机回退的抛出点）。
- **TS 侧参考实现（已是正确形状，本卡要求 Python 与之对齐语义）**: `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts:844`（`writeFacesOverlap`）——单槽 `deferred`（`deferred ?? reason`，首个遇到者胜）、冲突立即返回、循环结束后才回报 deferred。
- **语料（PM 冻结，只读）**: `packages/multi-workers/test/fixtures/write-face-corpus.json`，当前 `sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`、19996 B、`parse 23 / overlap 59`。新增行 **V58** 就是本卡要转绿的红项。
- **PM 实测（同一向量跑两侧）**: 脚本 `_scratch/evidence/wf-v58-probe-20261014.py`（Python 侧）+ `_scratch/evidence/wf-v58-ts-out.json`（TS 侧）。其中 `huge = "x/" × 300 + "x"`（601 字符）：

| 向量 | Python 现状 | TS 现状 | 裁定 |
|---|---|---|---|
| V58 `[huge, "src/x.ts"]` × `[huge, "src/x.ts"]` | `Unsupported(reason="glob-product-state-limit", detail="(301+1)*(301+1) > 65536")` | `Conflict sample="src/x.ts"` | **TS 对**（design.md D-111：overlap 期先证冲突） |
| V59 `["src/[a-", huge]` × `[huge]` | `Unsupported(glob-product-state-limit)` | `unsupported: unsupported-syntax` | 只差 reason 字符串，语料**不锁** reason |
| V60 `[huge, "src/[a-"]` × `[huge]` | `Unsupported(glob-product-state-limit)` | `unsupported: glob-product-state-limit` | 同上 |

## 写入允许面

- `packages/multi-workers/autopilot/write_face.py`
- `packages/multi-workers/test_write_face.py`

## 写入禁止面

其余一切路径。特别地：`packages/multi-workers/test/fixtures/write-face-corpus.json` **只读**（PM 冻结的契约，本卡是让代码满足它，不是让语料适应代码；认为语料本身有错就报回 PM）；`packages/multi-workers/autopilot/dispatch.py` 与 `packages/multi-workers/test/test_write_face_dispatch.py` 只读（T-W-I07 正在并行改同一包）；`packages/coding-agent/**` 全只读（TS 侧已达标）；`packages/multi-workers/mw_common.py` 只读（别的会话正在写）；禁止 `npm run check`（全仓 `biome --write`，多会话下破坏性）。

## 要求

1. **按对延迟**：把 `except _ConservativeUnknown` 从双重循环外层移进 `_globs_overlap` 调用点；命中后**记录**（首个遇到的 `reason`/`detail`/`(ga.entry, gb.entry)`）并 `continue`，**绝不允许** `return`。
2. **冲突优先**：任何一对给出 witness 就立即 `return Conflict(...)`（与现状的返回形状一致，`sample` 必须是 glob-free 的拼接路径）。
3. **循环结束后**才回报：deferred 非空 → `return Unsupported(reason=…, detail=…, rule=…, other=…)`；否则保持现状 `return None`（`None` 仍表示"可证不相交"）。
4. **与 TS 的语义对齐（对齐项）**：`ga.unsupported` / `gb.unsupported` 的条目必须**进入同一个 deferred 槽**（`unsupported-syntax`，首个遇到者胜），而不是像现状那样在循环之后单独判定并覆盖 deferred。语料不断言 reason，但两个实现必须同族；请在代码注释里写明这一条与 TS `writeFacesOverlap` 的对应关系。
5. **不得特判**：不许为 601 字符条目、不许为 `src/x.ts` 或任何语料具体值写分支；不许引入新依赖（AST 导入里仍不得出现 `fnmatch`，现有 no-fnmatch 守卫要保持绿）。
6. **测试文件同步**：`test_corpus_counts_frozen` 里的 `58` → `59`（两处）与 kind 直方图 `overlap: 33` → `34`；**不要**给 V58 加 reason 断言（reason 不在契约里）；语料驱动的 `parametrize` 结构保持不变。
7. **新增一条独立回归测试**（不依赖语料行，防止"语料行被误改后缺陷复现"）：同一个 face 里"先一个不可判定对、后一个可证冲突对"必须返回 `Conflict` 且 witness 为 glob-free；反向（只有不可判定对）必须仍是 `Unsupported` 且 `is_overlap()` 为真。
8. `git diff --stat` 收尾时只应出现上述两个文件。

## 交付格式

`output.md` 必须包含框架要求的五段：`结论`、`证据`、`残留与未验证`、`上下文来源`、`改动清单`。`证据` 段要给**可直接复跑的原始命令与原始输出**（验收命令的完整输出、V58 的 witness 值），不要只写"已通过"。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test_write_face.py -q                                 # 期望 129 passed（当前 2 failed, 127 passed）
python -m pytest test_write_face.py -q -k "corpus_counts or v58"       # 期望全绿
python H:/git/Multi-Workers/.agenticdoc/_scratch/evidence/wf-v58-probe-20261014.py   # V58 必须给出 Conflict sample="src/x.ts"
git diff --stat -- packages/multi-workers/autopilot/write_face.py packages/multi-workers/test_write_face.py
```

## 改动历史

- 2026-10-14 PM：语料 v1（parse 16 / overlap 49）→ v2（23 / 58）→ **v3（23 / 59，新增 V58）**，本卡基线 `sha256=b39f8925…`、19976 B 附近（精确 19996 B）。
- 2026-10-14 PM 实测本文件修复前基线：`2 failed, 127 passed`（红项 = V58 语义 + 计数冻结）。
- 2026-10-14 上一轮 W-04（本文件）交付 `128 passed`；本轮是同一文件上的第二轮返工。

## 硬约束

- 不跑 `npm run check`（AGENTS.md P-017）。不碰冻结语料。不改 `dispatch.py`。不改 TS。
- 只改本卡声明允许面的两个文件；发现别处也要改就写进 `残留与未验证` 并回报。
