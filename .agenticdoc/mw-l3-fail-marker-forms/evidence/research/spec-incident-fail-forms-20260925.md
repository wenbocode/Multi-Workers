# Research: spec-incident-fail-forms（事故与现状审计）

日期: 2026-09-25 · 作者: PM（源自 E2Feature reflect 台账 + 本仓代码审计）

## 事故（E2Feature，2026-09-25 确证）

来源: `H:\git\E2Feature\.agenticdoc\_autopilot\reflect\l3-fail-marker-detection-too-narrow.md`（status: open，归因 框架-代码）

reviewer 明写 **FAIL**，框架判 `meets` → key 被机械结案 DONE。**结论与 reviewer 相反**，且 `l3-verdict.txt=meets`、roadmap `done`、pm-state `DONE` 全部自洽地错下去：

| key | 轮次 | reviewer 真实结论（原文） | 框架裁决 | 结案状态 |
|---|---|---|---|---|
| feature-inline-marker-patchkit | l3-a3 | output.md 表格 8 处 `\| **FAIL** \|`（28 PASS / 8 FAIL，5 needs-rerun）；report.md 13 处 | meets | **DONE** |
| feature-sampling-human-channel | l3-a1 | TL;DR：`FAIL — 21/30 VC 通过，9 项失败`；汇总 `- **FAIL：9**`、needs-rerun 9 | meets | **DONE** |

## 现状审计（本仓，2026-09-25 16:15 实测）

- `packages/multi-workers/autopilot/conductor.py`：`_L3_FAIL_RE = re.compile(r"\|\s*\**\s*FAIL\b")` —— 只匹配「管道符（+可选加粗）+ FAIL 词边界」。
- 三种受害形态 vs 现正则：
  1. 加粗单元格 `| **FAIL** |` —— **已覆盖**（a0c36fcce 的 `\**` 段）；
  2. 中文冒号项目符 `- **FAIL：9**` —— **漏检**（行首 `-`，无 `\|`）；
  3. TL;DR 散文 `FAIL — 21/30 VC 通过` —— **漏检**（无 `\|`）。
- 判定源回退链（a0c36fcce）：`_L3_SOURCE_ORDER = ("output.md", "report.md")`，FAIL 扫描在两个源上语义应一致（design 阶段核实扫描范围是全文还是提取节）。
- 反例（为什么以前没炸）：多数轮次 reviewer 恰好写朴素 `\| FAIL`（mvp-closeout l3-a1 report.md 38 处朴素 `| FAIL` 被正确判 below）⇒ **非确定性 bug，是产出形态随机**。

## 同型轮次登记（E2 source-fallback key 的 SPEC F-3/F-4）

- F-3（应 below→实 meets）4 轮：cigate a1 / mvp a2 / tier-a a1+a2；
- F-4（应 meets→实 below）3 轮：readcap a1 / marker a3 / sampling a1。
⇒ 系统性误判，非个案。

## 危害分级（为什么 P0）

- stalled 损失时间；**false-meets 污染事实面**：
  - 2 个 Stage 3 key 系 false-meets 结案（marker 8 FAIL、sampling 9 FAIL）；
  - 依赖图污染：`feature-switch-readiness-closeout` deps 含这两个 key，切换就绪对账会把 17 项未达成当已达成；
  - 闭卷 dossier 失真（l3-verdict.txt=meets + achieved.md 自动草稿一路写进归档）。
- 下游依赖：E2 侧 `feature-false-meets-remediation`（全量复算 + append-only 更正）**被本修复阻塞**。

## 边界事实

- 受害轮的 achieved.md 已由 E2 侧 PM 派 repair 重写为如实版本（`counted_as_done=false`）——工程侧止血，框架根因仍在。
- E2 reflect 判据（节选）：① 三类 FAIL 写法全部触发 below；② 固定口径全量复算产出稳定产物（CSV/JSON+哈希），marker a3 与 sampling a1 必为 below；③ 不存在「reviewer 写 FAIL、框架判 meets」残留；④ 已结案被纠正 key 有 append-only 更正记录。

## 置信度

- 正则现状、source order：本仓代码直读，高。
- 事故细节与语料指针：E2 reflect 台账转引，语料原文待 design 阶段 RQ 逐行核验（file:line 级）。
