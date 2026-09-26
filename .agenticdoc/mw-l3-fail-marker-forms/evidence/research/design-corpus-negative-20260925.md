# RQ-3 研究：FAIL 负样本面（false-positive surface）

- 日期: 2026-09-25
- Key: `mw-l3-fail-marker-forms`（design 阶段 RQ-3）
- 授权输出（唯一写文件）: `H:\git\Multi-Workers\.agenticdoc\mw-l3-fail-marker-forms\evidence\research\design-corpus-negative-20260925.md`
- 语言/编码: UTF-8、LF、无 BOM
- 范围: E2Feature 语料 + multi-workers 框架测试语料；全部为只读扫描

## 0. 结论摘要（TL;DR）

1. **扫描面现状**：L3 裁决只读 `workers/<l3-aN>/{output.md,report.md}` 的 `## Quality Gate Report` 节。`_md_section` 在下一个 `## ` 行截断，因此 **TL;DR、`## Achieved`、key 级 `l3-report.md`、`_autopilot/stages/*.md` 都不在当前扫描面内**（conductor.py:1076-1089, 1145-1148, 1188-1189）。
2. **E2 语料规模**：20 个 `l3-aN` 轮，15 轮含 `fail` 文本。现行 `_L3_FAIL_RE` 在 10 轮判 `meets`、5 轮判 `below`。10 个 meets 轮的 QG 节内共有 **50 条 FAIL-相邻行**（这正是必须存活 false-positive 面）。
3. **粗放宽的误伤量化**（对 10 个 meets 轮）：
   - `\bFAIL\b`（大小写敏感）扫 QG → **6/10 翻转**成 below；
   - `(?i)\bfail\b` 扫 QG → **10/10 翻转**；
   - 仅 `^\s*[-*]\s*\**\s*FAIL\b` 项目符扫 QG → **1/10 翻转**，即 `feature-tier-a-closeout` l3-a2 `report.md:53` 的 `- FAIL：0`；
   - 行首散文 `^[^|\n]*FAIL\s*[—–-]` 扫 QG/whole-file → **0/10 翻转**（语料中该形态只出现在真 FAIL 轮）。
4. **召回对照（冻结 legacy 路径 `_parse_l3_output`，仅 output.md、无加粗）**：8 轮为 meets；其中 marker a3 / readcap a1 的 `| **FAIL** |` 已由现行 `_L3_FAIL_RE` 修正，**唯一仍漏的真 false-meet 是 `feature-sampling-human-channel` l3-a1**，其 QG 内标记是项目符 `- **FAIL：9**`。→ 项目符形态是 corpus 召回的必要项；行首散文 `FAIL —` 在语料中**没有独立承载轮**（0 轮 prose-only），属 spec 要求的预防性形态。
5. **框架测试翻转风险 2 处**（详见 §3）：`test_autopilot_verdict_source_fallback.py` 的 superset 探针硬编码 `new_only == 4`（`FAILED` 样本会变 5）；`test_autopilot_verdict_freshness.py:634-638` 与 `test_autopilot_verdict_source_fallback.py:536-542` 用区域 sha256 钉死 `_parse_l3_output` 源码字节。
6. **最硬 FP 形态**（详见 §4）：`- FAIL：0`（全角冒号 + 值 0）、`FAIL=0`/`FAIL 0`/`0 FAIL`、`fail_items=[]`/`failed=0`/`fail_total=0`/`internal_failures=0`/`k3_fail=0`/`tier_rows_on_fail=0`、`fail-closed`（连字符复合词，`\bfail\b` 会命中）、`3005 passed / 9 failed`、`tamper_failures=4`、`drift_fails=true`、`逐条 VC PASS/FAIL`（meta）。

---

## 1. 负样本编目（negative-surface catalog）

### 1.1 扫描面基线事实（读源码，非推断）

| 事实 | 证据 |
|---|---|
| 裁决源只含 output.md / report.md，有序 | `packages/multi-workers/autopilot/conductor.py:1145` `_L3_SOURCE_ORDER = ("output.md", "report.md")`；`conductor.py:1159` `_l3_source_paths` 拼 `workers/<task_key>/<name>` |
| 现行 FAIL 判据（含加粗管道） | `conductor.py:1148` `_L3_FAIL_RE = re.compile(r"\|\s*\**\s*FAIL\b")` |
| 扫描范围 = `## Quality Gate Report` 节 | `conductor.py:1188-1189` `qg = _md_section(text, "## Quality Gate Report") or ""` → `if _L3_FAIL_RE.search(qg)` |
| `_md_section` 在下一个 `## ` 截断 | `conductor.py:1076-1089`（`if line.startswith("## "): break`） |
| 冻结 legacy（无加粗、仅 output.md） | `conductor.py:1091-1108` `_parse_l3_output`，内部 `re.search(r"\|\s*FAIL\b", qg)`（无 `\**`） |
| `l3-report.md` 是派生输出，不是扫描输入 | done 门禁只查其存在/字节（`conductor.py:1396-1401`）；`_persist_l3_verdict(... l3_report_src ...)`（`conductor.py:1499` 附近）从决定源复制 |

**结论（对应任务 A.3）**：`.agenticdoc/*/l3-report.md` 与 `.agenticdoc/_autopilot/stages/*.md` **今天不被 parser 扫描**。前者是决定源的字节复制（display/门禁用），后者是 closeout dossier；两者都不参与 verdict 判定。

### 1.2 meets 轮 QG 节内的负样本（真正的 FP 面，50 行）

分类口径（每条可多标签）：`NEG_ZERO`=零/否定计数；`COMPOUND`=`fail-closed` 复合词；`COUNT_POS`=正计数或无关套件失败数；`META`=规则/口径/指令文本；`TRAP_BULLET`=`- FAIL：0`；`OTHER`=其他嵌入 token。

| key / 轮 | 行 | 类别 | verbatim（截断至 ~200 字符） |
|---|---|---|---|
| citgate-install-kit l3-a1 | report.md:9 | NEG_ZERO | `- 最终 \`build-runs/ci/exports/verify_report.json#summary\`：\`verify_items=35\`、\`verify_rows=34\`、\`verify_ok=true\`、\`fail_items=[]\`、\`pending_items=[]\`、\`missing_items=[]\`。` |
| citgate-install-kit l3-a1 | report.md:50 | NEG_ZERO | `**汇总**：PASS 35，FAIL 0，needs-rerun 0。质量门禁结论为 **PASS（有非阻断证据维护遗留）**。` |
| citgate-install-kit l3-a1 | report.md:53 | COMPOUND | `- Function Flow：输入/参数 fail-closed、三门禁、安装回滚、fixture E2E 的正常与异常节点均被 VC-005～024、VC-031～033 覆盖。` |
| citgate-install-kit l3-a2 | output.md:41 | NEG_ZERO | `- \`build-runs/ci/exports/verify_report.json#summary\`：...\`fail_items=[]\`、\`pending_items=[]\`...` |
| citgate-install-kit l3-a2 | output.md:42 | NEG_ZERO+COUNT_POS | `- \`regression_report.json\`：\`tests/featureci\` **337 passed / 0 failed**；全量 **3005 passed / 9 failed**，失败集合逐条等于已登记 9 条，\`subset=true\`、\`no_deselect=true\`。` |
| citgate-install-kit l3-a2 | output.md:53 | COMPOUND | `| VC-006 | 缺输入 fail-closed 100、无半成品 | PASS | 否 | \`verify_report.json#items[VC-006]\`... |` |
| citgate-install-kit l3-a2 | output.md:55 | COMPOUND | `| VC-008 | 归属来源可读，冲突反例 fail-closed | PASS | 否 | ...` |
| citgate-install-kit l3-a2 | output.md:61 | COMPOUND | `| VC-014 | layer 缺失/越域 fail-closed | PASS | 否 | ...` |
| citgate-install-kit l3-a2 | output.md:84 | NEG_ZERO | `**汇总**：**PASS 35 / FAIL 0 / needs-rerun 0**。` |
| citgate-install-kit l3-a2 | report.md:9,10,21,23,29,52 | 同 output.md 上列 | （report.md 与 output.md 同文，逐行一一对应） |
| l3-verdict-freshness l3-a1 | output.md:18 | NEG_ZERO+COMPOUND+COUNT_POS | `| VC-012 | PASS | no | 11 tests、4 fail-closed、AC-001～006 全覆盖、0 failed |` |
| l3-verdict-freshness l3-a1 | output.md:25 | NEG_ZERO | `**总计：19 PASS / 0 FAIL / 1 needs-rerun。**` |
| l3-verdict-freshness l3-a1 | report.md:21 | META | `| VC-011 | PASS | no | T-005 audit：既有文件 hash 未变，命名四文件 71 passed，全量 failed 集合未新增。...PASS 采用 ...“无新增失败”口径。 |` |
| l3-verdict-freshness l3-a1 | report.md:22 | NEG_ZERO+COMPOUND+COUNT_POS | `| VC-012 | PASS | no | T-003 \`pytest_result_20260924.json\`：11 tests、4 fail-closed、AC-001…006 全覆盖、0 failed，stdout 已归档。 |` |
| l3-verdict-freshness l3-a1 | report.md:31 | NEG_ZERO | `**门禁总判定：PASS（19 PASS / 0 FAIL / 1 needs-rerun）。** ...` |
| l3-verdict-freshness l3-a1 | report.md:36 | NEG_ZERO+COUNT_POS+META | `2. **全量套件仍非全绿**：记录为 \`1 failed, 867 passed\`，失败节点是既有 ... 但 spec AC-010 原始字面中的“0 failed”并未发生；...` |
| l3-verdict-source-fallback l3-a1 | report.md:13 | COMPOUND+META | `| VC-003 | PASS | no | 同上：output 通过而 report 含失败单元格时 fail-closed 为 \`below\`，决定源指向 report，dossier 同步为 below。 |` |
| l3-verdict-source-fallback l3-a1 | report.md:23 | NEG_ZERO+COMPOUND+COUNT_POS | `| VC-013 | PASS | no | ...：新增 15 用例、0 failed、5 个反向/fail-closed 场景、14 个 AC 覆盖、无真实树依赖。 |` |
| mvp-closeout l3-a2 | report.md:35 | COMPOUND | `| VC-019 | PASS | 否 | packet L115；6 子命令、JSON/computed-at 支持、稳定 fail-closed 码、无半成品 |` |
| mvp-closeout l3-a2 | report.md:44 | NEG_ZERO | `| VC-028 | PASS | 否 | packet L124；本 key failed=0，全量失败集为登记集子集，collected=2159 |` |
| mvp-closeout l3-a3 | output.md:45 | COMPOUND | `| VC-019 | PASS | 否 | T-011 output；6 子命令、固定时间参数及 fail-closed 码成立 |` |
| mvp-closeout l3-a3 | output.md:54 | NEG_ZERO | `| VC-028 | PASS | 否 | T-013 output；本 key failed=0，全量失败集为登记集子集 |` |
| params-service l3-a3 | output.md:12 | NEG_ZERO | `> 总结：**PASS 24 / FAIL 0 / needs-rerun 0**。` |
| params-service l3-a3 | output.md:37 | NEG_ZERO | `| VC-022 | PASS | 否 | \`verify_params.py --json\`：\`param_vcs=24 pass=24 fail=0 exit=0\`；\`evidence_clean=true\` |` |
| params-service l3-a3 | output.md:43 | NEG_ZERO | `- 最终验证：\`param_vcs=24 pass=24 fail=0 exit=0\`。` |
| tier-a-closeout l3-a1 | report.md:16 | COMPOUND | `| VC-008 | PASS | 否 | T-004 worker \`[VERIFY]\`；固定 \`hotspots_top20.csv\` 记录。...缺失/行数错误的 fail-closed 反向路径有记录。 |` |
| tier-a-closeout l3-a1 | report.md:32 | COUNT_POS | `| VC-024 | PASS | 否 | ...三类篡改均被检出（\`tamper_failures=4\`、\`tamper_exit=1\`）。 |` |
| tier-a-closeout l3-a1 | report.md:33 | NEG_ZERO+COUNT_POS+META | `| VC-025 | PASS（基线契约） | **是** | ...但它**不能证明当前全量 \`pytest\` 为 0 failed**。... |` |
| tier-a-closeout l3-a1 | report.md:44 | NEG_ZERO | `- VC：**32 PASS / 0 FAIL**（按冻结的 VC 与已记录 EXECUTE 证据）。` |
| tier-a-closeout l3-a1 | report.md:45 | NEG_ZERO+COUNT_POS+META | `- \`needs-rerun\`：**1 项（VC-025 的“当前全量 0 failed”字面口径）**。` |
| tier-a-closeout l3-a1 | report.md:46 | NEG_ZERO | `- ...\`k7_vcs=32 pass=32 fail=0\`、\`pass_total=64 fail_total=0\`、\`protected_equal=true\`、\`degraded=false\`。` |
| tier-a-closeout l3-a1 | report.md:47 | NEG_ZERO+COUNT_POS+META | `- **复评结论：PASS（证据记录口径）...** 此结论不授权把项目级 AC-025 的字面“全量测试 0 failed”写成已达成。` |
| tier-a-closeout l3-a1 | report.md:51 | NEG_ZERO+COUNT_POS | `1. **全量 pytest 静态窗口复跑**：...验收必须明确记录 \`passed>=1017\` 且 \`failed=0\`；当前 before/after 同为 4 failed 只能证明本 key 无新增回归。...` |
| tier-a-closeout l3-a2 | report.md:10 | NEG_ZERO | `- 主证据：...（记录 \`k7_vcs=32 pass=32 fail=0\`、\`pass_total=64 fail_total=0\`、\`protected_equal=true\`、\`degraded=false\`）...` |
| tier-a-closeout l3-a2 | report.md:19 | COMPOUND | `| VC-004 | PASS | 否 | \`[VERIFY] VC-004\`；FK/dangling 检查与不存在 feature 注入的 fail-closed 记录已纳入 K7 报告。 |` |
| tier-a-closeout l3-a2 | report.md:24 | COMPOUND | `| VC-009 | PASS | 否 | ...U3 缺失保持 \`not_evaluable\`，越界输入 fail-closed，禁用依赖扫描为 0。 |` |
| tier-a-closeout l3-a2 | report.md:40 | NEG_ZERO+COUNT_POS | `| VC-025 | PASS | 否 | ...全量 suite \`1573 passed / 0 failed / exit 0\`...live 记录为 \`1602 passed / 2 failed\`...本 key \`internal_failures=0\`... |` |
| **tier-a-closeout l3-a2** | **report.md:53** | **TRAP_BULLET** | `- FAIL：0` |
| tier-a-closeout l3-a3 | output.md:47 | NEG_ZERO+COUNT_POS | `| VC-025 | PASS | 否 | 隔离窗口 1573 passed / 0 failed；live 外部失败 2、本 key 内部 0 |` |
| tier-a-closeout l3-a3 | report.md:8 | NEG_ZERO+COUNT_POS | `- **主证据**：...\`k7_vcs=32 pass=32 fail=0\`、\`pass_total=64 fail_total=0\`...\`tamper_failures=4 tamper_exit=1\`...` |
| tier-a-closeout l3-a3 | report.md:23 | NEG_ZERO | `| VC-008 | PASS | 否 | \`[VERIFY] VC-008: ... tier_rows_on_fail=0 ok=true\` |` |
| tier-a-closeout l3-a3 | report.md:39 | OTHER | `| VC-024 | PASS | 否 | \`[VERIFY] VC-024: ... tamper_failures>=1 tamper_exit!=0 ok=true\` |` |
| tier-a-closeout l3-a3 | report.md:40 | NEG_ZERO+COUNT_POS | `| VC-025 | PASS | 否 | \`[VERIFY] VC-025: passed>=1017 failed=0 ...\` + \`[VERIFY] VC-025-live: passed=1602 failed=2 internal_failures=0 external_failures=2 ...\` |` |
| tier-a-closeout l3-a3 | report.md:43 | OTHER | `| VC-028 | PASS | 否 | \`[VERIFY] VC-028: ... drift_fails=true ok=true\` |` |
| tier-a-closeout l3-a3 | report.md:46 | NEG_ZERO | `| VC-031 | PASS | 否 | \`[VERIFY] VC-031: ... parent_writes=0 ok=true\` + ... + \`[VERIFY] K7: k7_vcs=32 pass=32 fail=0 ...\` |` |

按标签统计（meets QG，重叠计数）：`NEG_ZERO` 32、`COMPOUND` 16、`COUNT_POS` 15、`META` 4、`TRAP_BULLET` 1、`OTHER` 2；**去重后 50 行**。

### 1.3 非 QG 节的负样本（当前不在扫描面，若设计扩到 TL;DR/Achieved/whole-file 才暴露）

| key/轮 | 位置 | verbatim |
|---|---|---|
| citgate-install-kit l3-a1 | output.md:3,7 (TL;DR) | `PASS（有非阻断遗留）——35/35 条 VC 均有 PASS 证据，FAIL=0，needs-rerun=0。` |
| citgate-install-kit l3-a2 | output.md:3,7 (TL;DR) | `PASS —— 二轮 L3 质检确认 35/35 VC 通过、FAIL=0、needs-rerun=0，首轮 3 项可修证据遗留均已闭合。` |
| mvp-closeout l3-a2 | output.md:10 (TL;DR) | `- 质量门禁：38 PASS、0 FAIL、0 needs-rerun。` |
| tier-a-closeout l3-a2 | output.md:3,7 (TL;DR) | `PASS — 32/32 VC 通过，VC-025 隔离回归为 1573 passed / 0 failed，当前 needs-rerun=0。` |
| l3-verdict-freshness l3-a1 | output.md:37 (Achieved) | `- 新增 11 个测试，其中 4 个反向/fail-closed；记录结果全部通过。` |
| l3-verdict-source-fallback l3-a1 | report.md:44 (Achieved) | `- **目标收益**：...对所有合格源执行 fail-closed 失败扫描...历史语料预期纠正 4 个 false-below 与 3 个 false-meets，复算后 \`false_meets=0\`。` |
| tier-a-closeout l3-a2 | report.md:64 (Achieved) | `- 针对上一轮唯一 \`needs-rerun\` 的 VC-025，核验 ...：1573 passed、0 failed；同时保留 live 1602 passed、2 个外部失败的真实状态。` |
| tier-a-closeout l3-a3 | output.md:71,73 / report.md:62,63,75 (Achieved) | `pass_total=64 fail_total=0` / `1573 passed / 0 failed` / `1602 passed / 2 failed` 等 |

**量化**：whole-file 扫描下 `\bFAIL\b` 仍翻 6 轮；`(?i)\bfail\b` 翻 10 轮；仅 TL;DR `\bFAIL\b` 翻 1 轮（citgate a2，`FAIL=0`）；行首散文 `FAIL —` whole-file 翻 0 轮。

### 1.4 below 轮内的真标记 + 否定共存（豁免表标定用）

真标记形态（below 轮）：
- 朴素管道：`feature-mvp-closeout` l3-a1 `report.md:26-63` 共 38 个 `| VC-0NN | FAIL |` 行（另有 `report.md:16,17` 两行 `FAIL / needs-rerun`）；无加粗。
- 加粗管道：`feature-inline-marker-patchkit` l3-a3 `output.md:22,30,31,36,38,44,48,50` 8 处 `| VC-0NN | **FAIL** | ...`；`feature-l3-readcap-injection` l3-a1 `output.md:18` `| VC-006 | **FAIL** | **YES** | ...`。
- 中文冒号项目符：`feature-sampling-human-channel` l3-a1 `output.md:12` `- **FAIL：9**`；同轮 `report.md:49` `- **FAIL：9**：VC-001、003、009、010、015、021、024、026、030。`；`feature-mvp-closeout` l3-a1 `report.md:69` `- FAIL：38`。
- 行首散文：`feature-sampling-human-channel` l3-a1 `output.md:3,7` `FAIL — 21/30 VC 通过，9 项失败；...`；`feature-inline-marker-patchkit` l3-a3 `output.md:3,7` `状态：❌ FAIL — 36 项 VC 中 28 PASS、8 FAIL；...`；`feature-mvp-closeout` l3-a1 `output.md:3,7` `❌ FAIL — 38 个 VC ...`；`feature-l3-readcap-injection` l3-a1 `output.md:3,7` `FAIL — VC-006 未达成：...`。

同轮否定共存（说明豁免必须同时作用于 below 轮，不能只对 meets 轮生效）：
- `feature-sampling-human-channel` l3-a1 `report.md:23` `- **VC-024**：验收回归实际为 exit 1，\`2 failed / 1142 passed\`，...`（真 FAIL 轮里的“2 failed”是证据计数，不是第二遍 FAIL）。
- `feature-mvp-closeout` l3-a1 `report.md:67` `- PASS：0`（无 `0 FAIL`，故该轮不存在“自我抵消”）。
- `feature-inline-marker-patchkit` l3-a3 `report.md:44` `| VC-034 | **FAIL** | yes | \`regression_report.json\` 记录 featuremark 0 fail、全量 9=registered 9、...`（真 FAIL 行里嵌 `0 fail`）。

### 1.5 语料级 pattern 计数（output.md/report.md，去重行）

| pattern | 命中行数 | 备注 |
|---|---|---|
| `\|\s*\**\s*FAIL\b`（现行判据） | 92 | 其中 80 在 l3 轮内 |
| `(?i)FAIL\s*[:=]\s*0\b` | 103 | 大量为 `pass=N fail=0` |
| `(?i)\b0\s+FAIL\b` | 11 | 摘要行 `0 FAIL` |
| `(?i)fail-closed` | 347 | 复合词，遍布 PASS 行 |
| `(?i)fail_items` | 7 | 指标名 |
| `(?i)\d+\s+failed\b` | 264 | 套件计数 |
| `^\s*[-*]\s*\**\s*FAIL\s*[：:]` | 4 | 3 真标记 + 1 个 `- FAIL：0` |
| `FAIL\s*[—–-]\s` | 15 | 全部为真散文标记（无 meets 轮） |
| `needs-rerun` | 131 | 汇总/表头 |

**未观察到 `FAILED`（大写）出现在任何 l3 轮**；`FAILED` 只出现在框架测试样本里（§3）。
**未观察到 prose-only 真 FAIL 轮**：所有真 FAIL 轮同时含管道或项目符标记。

### 1.6 下游 blast-radius（A.3）

已被 parser 读取的：无。`l3-report.md` 是决定源字节复制（见 §1.1 证据），`stages/*.md` 是 closeout dossier。两者含 FAIL-相邻文本仅为展示面：

| 文件 | 证据 |
|---|---|
| `feature-cigate-install-kit/l3-report.md` | 8 行：`:3,7` `FAIL=0`；`:41` `fail_items=[]`；`:42` `0 failed / 9 failed`；`:53,55,61` `fail-closed`；`:84` `PASS 35 / FAIL 0` |
| `feature-l3-readcap-injection/l3-report.md` | 6 行：`:3,7` `FAIL —`；`:18` `| **FAIL** |`；`:21,23` `fail-closed`；`:36` `**门禁结论：FAIL / below。**` |
| `feature-l3-verdict-freshness/l3-report.md` | 3 行：`:18,25,37` 同轮 QG/Achieved |
| `feature-l3-verdict-source-fallback/l3-report.md` | 3 行：`:13,23,44` |
| `feature-mvp-closeout/l3-report.md` | 2 行：`:45,54` |
| `feature-params-service/l3-report.md` | 3 行：`:12,37,43` |
| `feature-sampling-human-channel/l3-report.md` | 4 行：`:3,7` `FAIL —`；`:12` `- **FAIL：9**`；`:23` `2 failed / 1142 passed` |
| `feature-tier-a-closeout/l3-report.md` | 3 行：`:47,71,73` |
| `feature-inline-marker-patchkit/l3-report.md` | 0 行；该文件是 582B 陈旧通用输出（`l3-verdict.txt=below`），属另一 key（verdict freshness / repair-edits-reviewer-artifact）域 |
| `_autopilot/stages/stage-1-close.md` | `fail` 命中 0（1396 B） |
| `_autopilot/stages/stage-2-close.md` | `fail` 命中 0（1853 B） |

---

## 2. mvp-closeout double-fire check（任务 A.2）

被测轮：`feature-mvp-closeout` l3-a1（reviewer 真判 FAIL；框架现行判 below）。

**朴素计数（`ap-feature-mvp-closeout-l3-a1/report.md`）**
- `\|\s*\**\s*FAIL\b` 命中 **40**；其中精确单元格 `\| FAIL \|`（`report.md:26-63`）**38** 个，另 `report.md:16,17` 两行 `| ... | FAIL / needs-rerun | ...`。
- `(?i)fail` 命中 **44** 行。
- **`0 FAIL` / `FAIL=0` / `FAIL 0` 形态命中 0**（`zeroFAIL=0`）。`report.md:67` 只有 `- PASS：0`（不同 token）。
- 额外项目符：`report.md:69` `- FAIL：38`（在 QG 节内；`## Achieved` 起于 `report.md:73`）。
- `output.md:3,7` TL;DR：`❌ FAIL — 38 个 VC 均因 reviewer read_scope 达到 8/8 上限而无法核验证据，已全部标记 needs-rerun。`

**判定**
- 该轮 **不存在 “0 FAIL”-式否定行**，所以：
  - 粗放宽检测（FAIL anywhere）在这轮只会**多命中**（40→44 量级），不会 double-count 或 mis-exempt；裁决保持 below。**double-fire 风险不在这轮。**
- 真正的 mis-exemption 风险在**同 key 的 meets 轮**与 sampling 轮：
  1. `ap-feature-mvp-closeout-l3-a2/output.md:10`（TL;DR）`- 质量门禁：38 PASS、0 FAIL、0 needs-rerun。`；该轮现行判 meets。若设计扫 TL;DR 且不豁免 `0 FAIL` → 误翻。
  2. `ap-feature-tier-a-closeout-l3-a2/report.md:53` `- FAIL：0`（QG 节内，meets 轮）。这是**唯一一个 meets-QG 项目符陷阱**。
  3. 反向风险：若豁免规则写成“`- FAIL：<n>` 一律视为汇总计数而非裁决”，则会 mis-exempt **真标记** `ap-feature-mvp-closeout-l3-a1/report.md:69` `- FAIL：38` 与 `ap-feature-sampling-human-channel-l3-a1/output.md:12` `- **FAIL：9**`，把真 below 洗成 meets。→ **豁免必须按值（==0）而非按形状**，且需覆盖全角冒号。
- 交叉验证：现行 `_l3_resolve_source` 对 mvp a1 由 `report.md`（38 管道行）判 below；对该 key 的 a2/a3 由 `report.md`/`output.md` 的 PASS 表判 meets。放宽只影响否定行，不影响此结论。

---

## 3. 框架测试编目与翻转风险（任务 B）

方法：`rg -n 'FAIL' packages/multi-workers/**/*.py --glob '!**/.tmp/**'`（73 行上限清单）+ 逐文件通读 L3 fixture。含 `## Quality Gate Report` 的测试文件只有 5 个：`test_autopilot_conductor_exec.py`、`test_autopilot_readcap_injection.py`、`test_autopilot_verdict_freshness.py`、`test_autopilot_verdict_source_fallback.py`、`test_autopilot_e2e.py`。

### 3.1 reviewer stub / fixture report 模板里的 FAIL 字面量

| file:line | verbatim | 当前 vs 放宽后 | 翻转风险 |
|---|---|---|---|
| `test_autopilot_conductor_exec.py:151` | `"| VC-002 | FAIL | (missing) |\n"`（在 `_L3_BELOW` fixture 的 QG 表内，lines 140-158） | 都判 below | 无 |
| `test_autopilot_conductor_exec.py:751` | `rows += "| VC-002 | FAIL | (missing) |\n"`（`_dcr_l3_report(fail=True)`） | 都判 below | 无 |
| `test_autopilot_readcap_injection.py:861` | `qg_fail = "## Quality Gate Report\n| VC | Verdict |\n| VC-001 | FAIL |\n"` | 都判 below（`test_vc012_l3_criteria_still_below`） | 无 |
| `test_autopilot_verdict_freshness.py:162` | `if re.search(r"\|\s*FAIL\b", qg):`（`_mirror_parse_l3_output`，非 import） | mirror 未随 conductor 放宽而变化时，测试只与真实锚点/自身比较 | 低（见 3.2 note） |
| `test_autopilot_verdict_source_fallback.py:109-112` | `_BOLD_FAIL = _L3_BELOW.replace("| VC-002 | FAIL | (missing) |", "| VC-002 | **FAIL** | (missing) |")`；`_OUTPUT_BOLD_FAIL = _BOLD_FAIL + ...` | 都判 below | 无 |
| `test_autopilot_verdict_source_fallback.py:586-592` | 7 个 superset 样本（见 3.2） | 见 3.2 | **有** |
| `test_autopilot_e2e.py:279-305` | e2e reviewer stub 仅 `| VC-901 | PASS |` / `| VC-902 | PASS |`，无 FAIL | 目前无 FAIL stub（AC-006 要求新增 bold-FAIL 轮） | 无（但缺覆盖） |
| `test_autopilot_verdict_freshness.py:627` | `"| VC-1 | FAIL |\n\n## Achieved\n\nok\n"`（`test_l3_criteria_behavior_unchanged` rule 3） | 都判 below | 无 |
| `test_autopilot_verdict_source_fallback.py:529` | `"| VC-1 | FAIL |\n\n## Achieved\n\nok\n"`（`test_frozen_region_sha_and_criteria_passed` rule 3） | 都判 below | 无 |

### 3.2 会因放宽而翻红的现有绿测（flip-risk flags）

**F-1（硬翻转）`test_autopilot_verdict_source_fallback.py` 严格超集探针**
- 样本 `test_autopilot_verdict_source_fallback.py:586-592`：
  - `"| VC | verdict |\n|----|----|\n| VC-1 | FAIL |\n"`（line 586）
  - `...| VC-1 | **FAIL** |\n"`（587）
  - `...| VC-1 |  **FAIL**  |\n"`（588）
  - `...| VC-1 |**FAIL**|\n"`（589）
  - `...| VC-1 | *FAIL* |\n"`（590）
  - `...| VC-1 | PASS |\n"`（591）
  - `...| VC-1 | FAILED |\n"`（592）
- 断言（同文件，`VC-008` 段）：`old_only == 0 and new_only == 4 and superset`（约 `:603-608`）。
- 现行 `_L3_FAIL_RE` 只把 587-590 记为 new-only（4），586 是 old∩new，591/592 不命中。
- **任何会命中 `FAILED` 的放宽（`(?i)fail` 子串、去掉 `\b`、词干匹配）→ `new_only=5` → 该绿测翻红。**
- 另：允许命中 `*FAIL*`（590）与允许命中 `**FAIL**` 都必须保持；`| FAIL |` 也必须保持。

**F-2（硬翻转）`_parse_l3_output` 区域 sha 锚**
- `test_autopilot_verdict_freshness.py:45` `_PARSE_L3_SHA = "b0348c4f...c98"`；`:634-638` `parse_sha = _conductor_region_sha("def _parse_l3_output(")` + `assert rules == 4 and parse_ok and md_ok`。
- `test_autopilot_verdict_source_fallback.py:69` 同值；`:536-542` 同断言。
- 区域算法 `_func_source` 从 `def _parse_l3_output(` 到下一个 `def `/`class `/`# ──` 行（`test_autopilot_verdict_source_fallback.py:195-207`），**包含 `:1108` 的 `re.search(r"\|\s*FAIL\b", qg)`**。
- `_L3_FAIL_RE`（`:1148`）位于 `_parse_l3_output` 区域之外，仅改它 **不** 动 sha；但 AC-004 要求两源语义一致，若设计把 `_parse_l3_output` 也切到 widened 判据，**两处 sha 断言必红**，需同步更新锚值（属设计有意变更，非意外回归，但必须显式处理）。

**F-3（软）`_mirror_parse_l3_output` 与真值锚**
- `test_autopilot_verdict_freshness.py:153-165` mirror 用 `re.search(r"\|\s*FAIL\b", qg)`；`:329` 用它在真实 E2 key `feature-l3-verdict-freshness` l3-a1 上复算，并与 `evidence/exec-l3-verdict-freshness-recompute-20260924.json` 的 `reverse_anchor` 对比（`:331-338`）。
- 该真实轮是**真 PASS 轮**（§1.2）。因此即使 conductor 放宽，只要 mirror 不误报，`live_last` 仍为 meets，测试保持绿。**风险低，但 mirror 是独立副本**：若未来把 mirror 也放宽且判据误伤 freshness a1 的 `0 FAIL`/`fail-closed`，这些绿测会连带翻红（同一豁免表必须覆盖 mirror 所用口径）。

**非风险（已核查，不 flip）**
- `test_autopilot_conductor_exec.py` 的 `_L3_BELOW`/`_dcr_l3_report(fail=True)`：期望 below，放宽后仍 below。
- `test_autopilot_readcap_injection.py:861` + 控制组 `qg_pass + achieved`（`healthy == "meets"`）：控制组文本无 fail 词，放宽后仍 meets。
- `test_autopilot_verdict_source_fallback.py:870-885`（`test_change_classes_fixture_reproduce_4_plus_3`，`false_meets == 0`）：`_L3_MEETS` 及其派生文本不含 fail 词。
- `test_autopilot_closure.py:112` `assert "PASS/FAIL" in instruction`：源为 `autopilot/closure.py:57` 的提示词文本，不进入 L3 判据。
- `test_autopilot_l0.py:314` `assert "fails closed" in ts_test`：TS worker 契约，不进入 L3 判据。
- `test_autopilot_stall.py`：全文件无大写 `FAIL` 字面量，只有 `failed` 状态串与 `_advance_failure_streak` 命名。
- `test_autopilot_e2e.py:1084` `print(f"FAIL {test.__name__}: ...")`：测试 harness 自身输出，非 fixture。

**测试语料中不存在**（新豁免用例不能凭空自证，须从 §1 语料取）：
- 无 `0 FAIL` / `FAIL=0` / `fail_items=[]` / `fail-closed` / `FAILED` 出现在任何 QG fixture 字符串里。→ AC-002 的否定用例必须来自 E2 真实语料（§1.2），并在框架测试里以“注入真实行”的方式钉死。

---

## 4. 放宽后必须存活的最硬 false-positive 形态（按硬度排序）

1. **`- FAIL：0`（全角冒号 `：` + 值 0）** — `feature-tier-a-closeout` l3-a2 `report.md:53`。这是唯一一个“项目符形状正确、值却为 0”的 meets-QG 行；ASCII-only 的 `[:=]` 豁免正则（如 `FAIL\s*[:=]\s*0`）**不会命中**，会让该真 PASS 轮翻红。豁免必须同时吃 `:`、`：`、`=`、空格，并允许 `**` 包裹。
2. **`FAIL=0` / `FAIL = 0` / `FAIL 0` / `0 FAIL`** — citgate a1 `report.md:50`、citgate a2 `output.md:84`、freshness a1 `output.md:25`、params a3 `output.md:12`、tier-a a1 `report.md:44`、tier-a a2 `output.md:10`。分隔符有空格、`=`、全角逗号；必须按“0 值”判否，不能按“有数字”判否。
3. **小写指标 token**：`fail_items=[]`、`failed=0`、`fail_total=0`、`internal_failures=0`、`k3_fail=0`、`tier_rows_on_fail=0`、`failed=[]`。若检测大小写不敏感或做子串匹配，这些全中；必须保留 `\b` 或改用“大写 FAIL / `**FAIL**` / 行首 FAIL”的形态判据。
4. **`fail-closed`（连字符复合词）** — 347 命中行。`\bfail\b` 在此**会**命中，因为 `-` 是非词字符。出现位置包括 PASS VC 行的描述列（如 citgate a2 `output.md:53` `| VC-006 | 缺输入 fail-closed 100 ... | PASS |`）。检测需排除 `fail-closed`/`failclosed`。
5. **无关套件正计数**：`3005 passed / 9 failed`、`1 failed, 867 passed`、`2 failed / 1142 passed`、`tamper_failures=4`、`tamper_failures>=1`、`drift_fails=true`。这些是证据/指标，不是本轮裁决。
6. **meta/instructional**：`逐条 VC PASS/FAIL`（tier-a a1 `output.md:12`）、`fail-closed 为 below`（source-fallback `report.md:13`，PASS 行）、`FAIL 正则超集`（plan-writer，非 l3 目录）、`缺节 / | FAIL 仍 below`（execute 目录，非 l3）。
7. **真 FAIL 行内嵌的负样本**：`| VC-034 | **FAIL** | yes | ... featuremark 0 fail ...`（marker a3 `report.md:44`）。豁免按行级生效会导致该行被整行豁免 → 漏检。**豁免必须是行内局部否定（看 FAIL 邻近的值），不能整行丢弃**。
8. **`FAILED` 词形陷阱** — E2 l3 语料 0 命中，但框架 superset 测试 `test_autopilot_verdict_source_fallback.py:592` 明确把它作为“不得命中”的样本（F-1）。
9. **中文“失败”**：大量出现（`9 项失败`、`2 个失败`、`失败集合未新增`），既有真 FAIL 行也有否定行。检测应坚持 ASCII `FAIL` token，不要扩到 `失败`——否则无可避免地误伤。
10. **`false_meets=0` / `false-below`**（source-fallback `report.md:44`）：meta 计数，含 `fail` 子串的变体（`false_meets` 不含，但 `false-below` 含）。

---

## 5. 假设判据 × 语料翻转矩阵（meets 轮）

| 假设判据 | 扫描面 | meets→below 误翻 | 备注 |
|---|---|---|---|
| `\bFAIL\b` | QG | **6 / 10** | citgate a1/a2, freshness a1, params a3, tier-a a1/a2 |
| `\bFAIL\b` | whole-file | 6 / 10 | 同上（TL;DR 的 `FAIL=0` 未新增） |
| `\bFAIL\b` | TL;DR only | 1 / 10 | citgate a2（`FAIL=0`） |
| `(?i)\bfail\b` | QG | **10 / 10** | 全部 |
| `(?i)\bfail\b` | whole-file | 10 / 10 | 全部 |
| `^\s*[-*]\s*\**\s*FAIL\b` | QG | **1 / 10** | 仅 tier-a a2 `- FAIL：0` |
| `^\s*[-*]\s*\**\s*FAIL\b` | whole-file | 1 / 10 | 同上 |
| `^[^|\n]*FAIL\s*[—–-]` | QG / whole-file | **0 / 10** | 语料中该形态只在真 FAIL 轮 |
| 现行 `\|\s*\**\s*FAIL\b` | QG | 0（基线） | 92 命中，全部真标记 |

**召回（冻结 legacy `_parse_l3_output`，仅 output.md，无加粗）**
- 8 轮 legacy=meets：`cigate a2 / marker a3 / readcap a1 / freshness a1 / mvp a3 / params a3 / sampling a1 / tier-a a3`。
- 现行 `_L3_FAIL_RE` 已把 `marker a3`、`readcap a1` 的 `| **FAIL** |` 修正为 below。
- **剩余真 false-meet：`sampling a1`（`- **FAIL：9**`）。** 项目符判据可召回；行首散文判据对该轮 **0 增量**（同轮已有项目符）。
- 结论：corpus 召回必要时增判据 = **项目符**；行首散文是 spec 要求的预防性形态（真实语料 0 个 prose-only 轮）。

---

## 6. 对 design 的直接约束（由本 RQ 事实导出，非方案）

- **必须**：豁免覆盖全角冒号 `：`（tier-a a2 `- FAIL：0` 是唯一硬陷阱）。
- **必须**：豁免按值 == 0，而非按形状；否则 mis-exempt `- FAIL：38` / `- **FAIL：9**`（真 below 被洗白）。
- **必须**：排除 `fail-closed`、`failed`、`fail_items`、`fail_total`、`internal_failures`、`tamper_failures`、`drift_fails` 等复合/指标 token；`\bFAIL\b` 大小写敏感是最低误伤面（6/10），大小写不敏感会到 10/10。
- **必须**：豁免局部到 token 邻近（真 FAIL 行内的 `0 fail` 不能豁免整行，见 §4.7）。
- **若**扫描面扩到 TL;DR/whole-file：额外处理 citgate a2 `output.md:3,7` `FAIL=0`（1 轮）。
- **若**改动 `_parse_l3_output`：同步 `test_autopilot_verdict_freshness.py:45,634-638` 与 `test_autopilot_verdict_source_fallback.py:69,536-542` 的 sha 锚（F-2）。
- **若**去掉 `\b`/改大小写不敏感：`FAILED` 样本（`test_autopilot_verdict_source_fallback.py:592`）会使 superset 探针 `new_only != 4` 翻红（F-1）。
- AC-002 用例必须逐条引用 §1.2 的 file:line，不得凭空构造（spec §5 已要求）。

## 7. 复现命令（只读）

```
rg -n -i 'fail' <E2>/.agenticdoc -g '**/workers/*/output.md' -g '**/workers/*/report.md'
rg -n 'FAIL' packages/multi-workers --glob '*.py' --glob '!**/.tmp/**'
```

判定复算是本地 Python 脚本，未写入 E2 仓库；结论中的 50/70/186 行、6/10、1/10 等计数均由 `_md_section` + `_L3_FAIL_RE` 的独立副本（非 import）对盘上文件重算得到。
