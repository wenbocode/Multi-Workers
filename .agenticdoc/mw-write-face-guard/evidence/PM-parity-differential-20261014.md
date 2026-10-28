# PM 独立差分：`write_face` 两语言一致性（2026-10-14，B0 回读后 PM 自造）

> 本文件是 **PM 复核 W-01/W-02 回执时发现的缺陷与语料缺口** 的证据，不是任何 worker 的回执。
> 两个 worker 的回执都如实（各自 99 / 92 用例全绿、65 行语料 0 mismatch），缺陷落在**两边都没覆盖**的区域。

## 0. 方法与可复现命令

| 装置 | 内容 |
|---|---|
| 随机差分 | 600 对条目（字母表 31 项，含合法 glob、`..`、`!a`、`!(a)`、`+(a)`、`@(a)`、`[a-`、`/abs/x`、`a//b`、`./a`、`a/` 等），Python 逐对算判定，TS（临时 vitest）逐对算判定，逐行比对 |
| 定位矩阵 | 10 个 2 条目 face，专门打「硬违规 × 不受支持语法」的位置组合 |
| 单条探针 | 10 个回退清单条目单独解析，两侧逐条对照 |

可复现脚本（保留在 `_scratch/evidence/`）：`wf-parity-diff-20261014.py`（随机差分，须先跑临时 vitest 产出 TS 侧裁定）、`wf-pos-matrix-20261014.py`（定位矩阵）。
**两侧 base 必须显式对齐**（第一版我把 Python 的 base 设成仓根、TS 设成 vitest 的 cwd，制造了 4 处假分歧；用 `WF_DIFF_BASE` 固定成仓根后同样 4 处仍在 ⇒ 不是装置伪影，见 §3）。

## 1. 结论：**allow/refuse 决策零分歧**，分歧全在「拒绝理由的形状」

600 对随机向量里 4 处分歧，逐条复核后**全部落在 refuse 内部**（`reject:<code>` ↔ `unsupported`），没有一处是「一侧放行、另一侧拒绝」。
单条探针（§2）10/10 完全一致，包括 `[a-` 单条 ⇒ 两侧都给 `unsupported`。

⇒ 运行期安全语义（放行/拒绝）**已经一致**；分歧是**可复现的拒绝理由**不一致，而这个理由会出现在 `DispatchResult.reason` 与审计里。

## 2. 单条探针：一致（10/10）

| 条目 | Python | TS |
|---|---|---|
| `[a-` / `!(a)` / `+(a)` / `@(a)` / `a{b` / `{a,b` / `a]b` | 解析通过 → `unsupported` | 同 |
| `[!a]b` | 解析通过 → 与 `a` 无交集 `none` | 同 |
| `..` | `reject:write-face-escape` | 同 |
| `/abs/x` | `reject:write-face-outside-base` | 同 |

## 3. 定位矩阵：分歧区域 = 「同 face 内 ≥2 条目，且有条目命中不受支持语法」

| face（2 条目） | Python | TS |
|---|---|---|
| `[a-, ..` | `unsupported` | `reject:write-face-escape` |
| `.., [a-` | `reject:write-face-escape` | `reject:write-face-escape` |
| `[a-, !a` | `unsupported` | `reject:write-face-invalid-entry` |
| `!a, [a-` | `reject:write-face-invalid-entry` | `reject:write-face-invalid-entry` |
| `[a-, /abs/x` | `unsupported` | `reject:write-face-outside-base` |
| `/abs/x, [a-` | `reject:write-face-outside-base` | `reject:write-face-outside-base` |
| `[a-, a` | `unsupported` | `unsupported` |
| `a, [a-` | `overlap` | `overlap` |

两侧规则因此可写成一句话：

- **Python（W-01）**：entry 循环遇到「不受支持语法」即**截断该 face 的后续校验**（后面的 `..` / `!a` / `/abs/x` 不再被看见），face 标记为 unknown ⇒ 结果 `unsupported`。**顺序敏感**：`[a-, ..]` 与 `[.., a-]` 同一逻辑 face 得到不同 code。
- **TS（W-02）**：**校验全部条目**，任何硬违规胜出（与顺序无关）；只有在没有任何硬违规时，不受支持语法才体现为 `Unsupported`。

## 4. 谁对：两边各对一半（这是我原先想错、被矩阵纠正的地方）

- **parse 期**：应按 **TS** 的规则。理由：`..`（`write-face-escape`）、`!a`（`write-face-invalid-entry`）、跨 base 绝对路径（`write-face-outside-base`）是 §3.1 的**确定性规则违规**；`[a-` 只是「无法判定」（§3.2 回退清单）。用一个"无法判定"去**遮蔽**一个"确定违规"，会让 code 变成条目顺序的函数 —— 这正是 D-006 立"判定必须单调（同一批卡不得因无关改动判出不同结果）"时要避免的那类不稳定，也让运维拿到不可执行的 `unsupported` 而不是"你的第 2 条写成 `..` 了"。
- **overlap 期**：应按 **Python** 的规则。§3.2 的字面是「任一侧含不受支持语法 → **判重叠**」，且只在**证不出重叠**时才需要退化为 `Unsupported`；Python 的 `[a-, a]` × `[a]` 能给出可证 witness（`overlap`），TS 却整对返回 `Unsupported`。逻辑上「先证冲突，证不出再看有没有不受支持语法」既满足保守要求，又保留了 witness。

## 5. 语料缺口（本 key 自己的冻结契约漏了一整段）

冻结语料 `packages/multi-workers/test/fixtures/write-face-corpus.json`（`sha256=fb710b904cd4bbcb03ffa4f432ebc3b60c0234771b4c5f06c0d3a36a0186b09f`）的问题：

1. **§3.2 回退清单 0 覆盖**：`parse` 16 行里没有 `[a-` / `!(a)` / `+(a)` / `@(a)` / 未闭合 brace 这类条目，`overlap` 49 行的 `kind` 集合是 `{overlap, none, reject, serial_only}`，**没有 `unsupported` 行**。整整一条契约子句（"任一侧含不受支持语法 ⇒ 判重叠"）没有任何向量锁住 —— 两个 worker 都在自己的测试里单独验了回退清单，但**跨语言一致性**没有任何向量约束，所以"两边各自对、合起来不一致"完全可能且已经发生。
2. **混合条目 0 覆盖**：没有一行是「同 face 内既有硬违规又有不受支持语法」，也没有**顺序对照对**（同一逻辑 face 的两种书写顺序）。
3. 后果：`P-021`（跨语言镜像两侧都要跑）在**语料层**失效——两侧都跑绿了，但绿的是不相交的假设集。

## 6. 影响面 / 未覆盖面（本节按 AC 要求逐条声明）

- **影响面**：① W-03（conductor 派发闸）**不受影响**：其卡面已规定 `Conflict` 与 `Unsupported` 都按重叠拒绝，两种形状都落进同一拒绝分支；② 受影响的是**拒绝理由的可复现性与可执行性**（`DispatchResult.reason`、审计行、运维排障），以及 D-006 的单调性要求；③ 语料是 W-04/W-05 的共享输入，扩展语料必须**先于**它们落地（P-021）。
- **未覆盖面**：① 只测了 31 项字母表上的 600 对 + 10 个 2 条目组合，**没有穷举**；② 未测 win32 大小写不敏感模式（`case_insensitive=True`）下的同族分歧；③ 未测嵌套 brace 深度上限、段级字符模式交集递归上限这两条回退项的**跨语言**表现（两侧单测各自有，同样没进语料）；④ 未测 deny 侧条目与 allow 的混合顺序（deny 不参与判定，预期无影响，但未实测）。

## 7. 第二轮：状态机级回退的同族分歧（W-05 上报，PM 复核确认）

**复现装置**（W-05 证据 §5.1 给出，PM 按 block-list 载体重跑两侧）：`a = [huge, "src/x.ts"]`、`b = [huge, "src/x.ts"]`，`huge = "x/"*300 + "x"`。

```text
PY: Unsupported glob-product-state-limit
TS: {"sample":"src/x.ts","reason":"write-face-overlap"}
```

**裁定**：按 **D-111 overlap 期**的字面（先证冲突）——**TS 对，Python 错**。`glob-product-state-limit` / `segment-pattern-probe-exhausted` 属 §3.2 回退清单（“段级字符模式交集触发递归/长度上限”），应只让**那一对**条目变为不可判定，而不是中止整轮遍历；Python 现状是 `except _ConservativeUnknown` 包住了整个 `for ga`/`for gb` 双重循环（`write_face.py:936-952`），于是另一个**可证**冲突被丢弃。这是 V57 的同胞（V57 是“不受支持语法条目”短路，本条是“状态机回退”短路）。

**语料缺口（第三个）**：没有“一个受支持对触发状态机回退、另一个对可证冲突”的向量 ⇒ 81 行对照 0 mismatch 仍遮住了它。待补 **V58**（上方向量 + `expect.kind=overlap`），需重冻语料。

**为何不在本轮立即补**：`wfg-i03` 正在跑**包级** `pytest -q` 验收（卡面要求），PM 此刻改语料会把它的套件弄红（Writer/C 类干扰）。补 V58 + Python 修正卡按“W-03 终态后再执行”挂起；两侧闸门不受影响（`Unsupported` 与 `Conflict` 在调用方都按重叠拒绝）。

## 8. 第二轮的正面结果（两侧修正后的重跑）

同一 600 向量（同一字母表与同一种子）在 W-04/W-05 落地后重跑：**`mismatches=0`**（第一轮 4）。
旁证：kind 直方图里 `overlap` 141→158、`unsupported` 117→100 ⇒ **17/600 = 2.8% 的随机向量从“不可判定”翻成“可证冲突”**，即 D-111 不是收尾性清理，它在真实输入上有可测的发生率。两种形状在调用方都拒绝，所以这是“可复现理由与 witness 可得性”上的修正，不是安全方向的反转。
