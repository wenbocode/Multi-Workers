"""Record (a) the W-07 absorption in plan.md section 7.2 with the fingerprint
normalization resolution, and (b) pitfall P-035 for the warn-only path-shape
section produced by worker/output-writer.ts."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard\plan.md")
PITFALLS = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\_pitfalls.md")

PLAN_ADD = """
### 7.2 W-07 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核（不采信自述）**：`python -m pytest test/test_write_face_dispatch.py -q` = **29 passed**（基线 25，卡面 ≥28）；我自己的往返探针 5 例全恒等——`['a/{b,c}/**']` → `'write_face:\\n  - a/{b,c}/**'`、`['packages/x/**','a/{b,c}/**']` → 两行块列表、`['src/[a-','src/ok.ts']` → 单行、`['packages/x/**','packages/y/z.py']` 与 `['dir/']` → **单行逐字节不变**。
- **跨读者风险由 PM 单独核过（卡面未要求）**：`write_face` 的读者只有 `autopilot/dispatch.py`（写+读在飞 task.md）与算子本体；`mw_common.py` 不读它；TS 侧只有 `shared/write-face.ts`（**没有** task.md 的 `write_face` 读者 ⇒ 证实 B1 的 PM 侧确实未开工）。多行块列表在 task.md 头里是**既有形态**：同一头里的 `read_scope:` / `deny_globs:` 早已用 `  - item` 块列表（`dispatch.py:881-889`）⇒ 无读者被破坏。
- **指纹口径的报回项已解决（非缺陷）**：W-07 实测磁盘 `sha256=4acc365d…`、`20126 B` 与卡面 `b39f8925…`、`19996 B` 不符，原因就是 §7.1 记的 CRLF 口径：卡面指纹按 **LF 归一化内容**计，磁盘是 CRLF（130 行）。W-07 未硬编码指纹（只用行数 + 逐行恒等），故不受影响；**后续写卡一律带"LF 归一化"字样**，避免重复报回。
- **warn 段来源（W-07 回读出现 `路径形态（warn，不影响判定）`）**：生产者为 `worker/output-writer.ts` 的 `gaps.malformedFiles` 形态检查（C-36c，warn-only），检查对象是 worker 自报的文件清单；本次因报告里嵌入了写面条目串（含 `,` / 换行 / `{}`）而被列入。**不是** worker 缺陷，也**不是**台账按逗号切分。已记录为 `_pitfalls.md` P-035，并把"报告里嵌入写面条目"的处理义务指向输出契约族（另一窗口的 `mw-worker-output-contract` 正在做 ledger/契约族研究）。
"""

PITFALL_ADD = """
## P-035 回读里的「路径形态（warn，不影响判定）」段不是 worker 缺陷（2026-10-14，mw-write-face-guard W-07 回读）

- 事实：W-07 的终态回读出现 `## 路径形态（warn，不影响判定）：write_face:\\n、\\n、dir/、a/{b、c}/**、packages/x/**`。生产者是 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts` 的 `gaps.malformedFiles` 形态检查（C-36c，**warn-only**，只被列进 `## 路径形态` 段，不参与判定）。被检查的是 worker **自报的文件清单**；本次列表里混进了写面条目串（含 `,`、换行、`{}`），于是被判"形态非法"。
- 危害：容易被读成"worker 报了坏路径"或"台账格式坏了"而去修 worker / 重派；实际判定未受影响。反向风险更大：**任何把写面条目原样嵌进逗号分隔或路径列表的产物**（台账行、审计行、改动清单）都会触发同一类 warn，甚至真的把条目切成多个字段（与 D-112「逗号不是模式内容」同一根因）。
- 硬规则：
  1. 回读里出现该 warn 段时，先看它列的 token 是不是**写面/glob 条目**：是则判为报告形态问题，**不影响 done/failed 判定**，不要据此重派。
  2. 把写面条目写进任何**分隔符承载**的结构（逗号分隔行、路径列表、台账列）之前，必须转义或改走块列表形态（`  - <entry>` / 反引号包裹）；不要假定条目里没有 `,`、换行、`{}`。
  3. 修这条 warn 的形态检查属于输出契约族（`worker/output-writer.ts` 的路径抽取），**不要**在写面族的卡里去改它。
- 关联：D-112/D-113（逗号不作内容、渲染器回退块列表）、P-034（产物被别的 run 写脏的读法）、`plan.md` §7.2。
"""

plan = PLAN.read_text(encoding="utf-8")
if "### 7.2 W-07 终态吸收" not in plan:
    PLAN.write_text(plan.rstrip() + "\n" + PLAN_ADD, encoding="utf-8")
    print("plan: appended 7.2")
else:
    print("plan: already has 7.2")

pit = PITFALLS.read_text(encoding="utf-8")
if "## P-035 " not in pit:
    PITFALLS.write_text(pit.rstrip() + "\n" + PITFALL_ADD, encoding="utf-8")
    print("pitfalls: appended P-035")
else:
    print("pitfalls: already has P-035")

for path in (PLAN, PITFALLS):
    text = path.read_text(encoding="utf-8")
    print(f"{path.name}: lines={len(text.splitlines())} bytes={len(text.encode('utf-8'))}")
