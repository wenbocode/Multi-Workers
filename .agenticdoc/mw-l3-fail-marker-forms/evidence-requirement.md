# Evidence Requirement: mw-l3-fail-marker-forms

| 项 | 值 |
|---|---|
| ac_fingerprint | `435c9b5d12ff`（门禁口径：sorted-unique AC ID 集 sha1 前 12 位） |
| 基线 commit | `d20a270d5`（conductor.py 2468 行，R1 全读锚点） |
| 语料 | E2Feature 20 轮 / 10 key / 121 uppercase-FAIL 行（R2pos 附录 A 可复算） |

## 各 AC 充分性判定标准

| AC | 充分判定（单次 PASS 即闭环） | 证据形态 |
|---|---|---|
| AC-001 | 四形态真实锚点（S1 `mvp a1 report.md:26` / S2 `marker a3 output.md:22` / S4 `sampling a1 output.md:12` / S6 `sampling a1 output.md:3`）在判定器单测中全部判 FAIL-命中，且 sampling 型场景（决定源仅 bullet、无 report.md）轮级 below | L1 真值表 + L2 场景 ①，verbatim 逐字回放 + 出处注释 |
| AC-002 | 负锚点 11 条（R2neg §6 / R2pos §6 清单）全部不触发；`FAILED` 样本三规则不命中；行内 `0 fail` 不豁免真 FAIL 行（marker a3 report.md:44 锚点）；构造双 token 行 `- FAIL 9 项，其中 FAIL：0` 首 token 触发（零值豁免 token 锚定，评审 NIT-3） | L1 真值表 + L2 场景 ⑤ |
| AC-003 | 默认套件 = 927 passed + 2 外域先在（readcap baseline / verdict-freshness true-below，均 d20a270d5 前已红）；e2e_l2 全绿（含新 e2e 用例）；superset/分类计数测试按新口径重标后绿 | 运行日志落 evidence/runs/ |
| AC-004 | 洗白洞场景（非合规 output.md 带 FAIL + 干净合规 report.md）判 below；双源 FAIL 语义一致；缺节仍 below；`EVENT_TYPES == 17` 断言绿 | L2 场景 ② + timeline 锁测试 |
| AC-005 | fail_line 在 stall reason / `l3-verdict` timeline detail / provenance sidecar / repair prompt 四消费面可观测（各自断言） | L2 场景 ③ |
| AC-006 | e2e full_chain：round-1 stub 写 `- **FAIL：1**` ⇒ below（无 false-meets DONE）+ repair 派发 + round-2 合规 ⇒ DONE | e2e 运行日志 |
| AC-007 | CHANGELOG [Unreleased] Fixed 条目含形态+豁免判据表与语料锚点；`_pitfalls.md` 新条目（判据 vs 表达措辞差 / 值感知豁免） | 文件 diff |

## 反向红线（任何一条出现即 FAIL）

1. 任一 meets 轮锚点被误翻（尤其 `- FAIL：0`、`0 FAIL / 1 needs-rerun`、`PASS 35 / FAIL 0`）。
2. 冻结原语 region-SHA 变红（`_parse_l3_output`/`_md_section` 被改动）。
3. timeline 事件类型集变化。
4. sampling 场景①依赖 report.md 才 below（G3 红线：必须由 output.md 独立触发）。
