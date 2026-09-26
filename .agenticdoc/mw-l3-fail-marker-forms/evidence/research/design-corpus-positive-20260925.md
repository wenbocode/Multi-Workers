# RQ-2 evidence: FAIL-positive corpus (E2Feature L3 reviewer outputs)

- Key: `mw-l3-fail-marker-forms` · RQ: **RQ-2** (design phase, FAIL-positive corpus)
- Date: 2026-09-25 · Role: research (read-only over `H:\git\E2Feature`)
- Inputs read: reflect ledger `_autopilot/reflect/l3-fail-marker-detection-too-narrow.md`, spec `mw-l3-fail-marker-forms/spec.md`, sibling ledger `feature-l3-verdict-source-fallback/evidence/l3-source-real-verdicts-20260925.json`
- Detector under study (live): `_L3_FAIL_RE = re.compile(r"\|\s*\**\s*FAIL\b")` — `H:\git\Multi-Workers\packages\multi-workers\autopilot\conductor.py:1148`
- Frozen detector (must stay byte-identical): `re.search(r"\|\s*FAIL\b", qg)` — `conductor.py:1108` inside `_parse_l3_output` (`conductor.py:1091`, sha `b0348c4f…`)
- Scan surface actually used today: `qg = _md_section(text, "## Quality Gate Report")` only — `conductor.py:1189` inside `_l3_resolve_source` (`conductor.py:1180`); `## Achieved` is only an eligibility test (`_l3_qualifies`, `conductor.py:1172`), never scanned for FAIL
- Source order: `_L3_SOURCE_ORDER = ("output.md", "report.md")` — `conductor.py:1145`
- Read-only statement: no file under `H:\git\E2Feature` was created, modified or deleted. All extraction was via read + a throwaway analysis script in `%TEMP%`.

## 0. Method and quantitative result

Method: enumerated all `workers/ap-<key>-l3-a<N>/` task dirs under `.agenticdoc/*/` (20 rounds / 10 keys), then for every `output.md` / `report.md`:

1. listed every line containing `FAIL` (case-sensitive) and every line containing `fail` (case-insensitive) with file line numbers;
2. re-implemented `_md_section` and replayed both regexes (`_L3_FAIL_RE`, frozen `\|\s*FAIL\b`) per line, whole-file and inside the `## Quality Gate Report` slice;
3. mapped each line to its section via the H2 header offsets of the same file.

Measurements (all reproducible from the citations below):

| metric | value |
|---|---|
| L3 rounds inspected | 20 (10 keys) |
| rounds containing uppercase `FAIL` | 12 |
| files containing uppercase `FAIL` | 21 (`output.md` 10, `report.md` 11) |
| lines containing uppercase `FAIL` | 121 |
| uppercase `FAIL` token occurrences | 128 |
| lines matched by live `_L3_FAIL_RE` (whole file) | **80** (all of them pipe-table cells) |
| lines matched by frozen `\|\s*FAIL\b` (whole file) | 42 (`feature-mvp-closeout` a1 report.md 40, `feature-gui-time-mvp-board` a2 report.md 1, `feature-l3-readcap-injection` a1 report.md 1) |
| **positive** FAIL lines that are NOT pipe cells | **25** |
| FAIL lines that are negation / zero-count / data-descriptor (must NOT fire) | 16 |
| `## Quality Gate Report` slice match count equals whole-file match count? | yes, for every file (no pipe-FAIL line sits outside a QG slice) |

Headline: **all 80 lines the live regex matches are pipe cells; all 25 positive non-pipe FAIL lines are missed.** The two confirmed false-meets incidents are both explained by source×shape, not shape alone:

- `feature-inline-marker-patchkit` a3: deciding source `output.md` contained 8 `| **FAIL** |` cells — missed by the then-live `\|\s*FAIL\b` (frozen still misses them: 0 matches).
- `feature-sampling-human-channel` a1: deciding source `output.md` contained the only positive marker as `- **FAIL：9**` (non-pipe) — missed by both regexes. The round is only rescued today because the fallback source `report.md` happens to carry 9 `| **FAIL** |` cells.

## 1. Per-round table (required)

Citation convention: `path:line` for markdown; `rounds[i]` for the sibling probe JSON at `H:\git\E2Feature\.agenticdoc\feature-l3-verdict-source-fallback\evidence\l3-source-real-verdicts-20260925.json`; reflect table rows cited as `reflect:15` / `reflect:16`.

### 1.1 The six rounds named in the task

| # | key | round | FAIL forms present (file:line) | framework verdict | correct verdict | evidence |
|---|---|---|---|---|---|---|
| R2-1 | `feature-inline-marker-patchkit` | `l3-a3` | 8 × bold pipe cell in `output.md` (22,30,31,36,38,44,48,50); 14 × bold pipe cell in `report.md` (16,24,25,30,32,38,42,44,53,54,55,56,57,58); prose conclusion `output.md:3,7`, `report.md:3`; bold summary `report.md:60` | **`meets` (WRONG)** | **`below`** | `reflect:15` (`| **FAIL** |` 8 处 / report 13 处 → 框架裁决 `meets`, DONE); probe `rounds[4]`: `legacy_output_only=meets`, `legacy_report_only=meets`, `real_parse_l3_output=meets`, `candidate=below/fail-cell` |
| R2-2 | `feature-sampling-human-channel` | `l3-a1` | TL;DR+Summary prose `FAIL — 21/30 …` (`output.md:3,7`); Chinese-colon bullet `- **FAIL：9**` (`output.md:12`); 9 × bold pipe cell in `report.md` (15,17,23,24,29,35,38,40,44); prose conclusion `report.md:3`; Chinese-colon summary `report.md:49`; needs-rerun line `report.md:50` | **`meets` (WRONG)** | **`below`** | `reflect:16`; probe `rounds[13]`: `legacy_output_only=meets`, `legacy_report_only=meets`, `real_parse_l3_output=meets`, `candidate=below/report/fail-cell`; key `l3-verdict.txt` = `meets` and key `l3-report.md` sha256 `f607fb61f9ba3987…` == `workers/ap-feature-sampling-human-channel-l3-a1/output.md` sha256 (the missed-marker source is the persisted dossier source) |
| R2-3 | `feature-mvp-closeout` | `l3-a1` | 38 × naive pipe cell `\| VC-0NN \| FAIL \| yes \|` in `report.md` (26–63); 2 × `\| … \| FAIL / needs-rerun \|` in `report.md` (16,17); prose `output.md:3,7`; prose conclusion `report.md:3,72`; inline prose `report.md:22`; Chinese-colon bullet `- FAIL：38` `report.md:69` | **`below` (CORRECT)** | **`below`** | `reflect:25` (「38 处朴素 `| FAIL`，被正确判 `below`」); probe `rounds[7]`: `legacy_output_only=below`, `candidate=below/report/fail-cell` |
| R2-4 | `feature-cigate-install-kit` | `l3-a1` | **no FAIL-positive marker**; only negated/zero forms: `FAIL=0` (`output.md:3,7`), `FAIL 0` (`report.md:50`) | **`below` (WRONG)** | **`meets`** | probe `rounds[0]`: `legacy_output_only=below` (output.md has no QG/`Achieved` sections → `report.md` only candidate), `legacy_report_only=meets`, `candidate=meets/report/no-fail`; reflect:40 F-3 |
| R2-5 | `feature-tier-a-closeout` | `l3-a1` | **no FAIL-positive marker**; only `PASS/FAIL` wording (`output.md:12`) and `0 FAIL` (`report.md:44`) | **`below` (WRONG)** | **`meets`** | probe `rounds[14]`: `legacy_output_only=below`, `legacy_report_only=meets`, `candidate=meets/report/no-fail`; `report.md:47` reviewer `- **复评结论：PASS（证据记录口径）…**`; reflect:40 F-3 |
| R2-6 | `feature-tier-a-closeout` | `l3-a2` | **no FAIL-positive marker**; only `- FAIL：0` (`report.md:53`) and `0 failed` (`output.md:3,7`) | **`below` (WRONG)** | **`meets`** | probe `rounds[15]`: `legacy_output_only=below`, `legacy_report_only=meets`, `candidate=meets/report/no-fail`; `output.md:3` reviewer `PASS — 32/32 VC 通过…`; reflect:40 F-3 |

**Framing correction (important for design).** Three of the six named rounds (R2-4, R2-5, R2-6) contain **no FAIL-positive marker at all** — their FAIL surface is *negation* (`FAIL=0`, `0 FAIL`, `0 failed`, `fail_items=[]`). They are false-**below** rounds whose root cause is the single judgment source (`output.md` lacked the two sections), not the FAIL regex. They belong to the RQ-3 negation corpus; RQ-2 records them as **negative controls** that the widened FAIL detector must not fire on.

### 1.2 Additional FAIL-positive rounds found by the sweep (same incident family)

| # | key | round | FAIL forms present | framework verdict | correct verdict | evidence |
|---|---|---|---|---|---|---|
| R2-7 | `feature-l3-readcap-injection` | `l3-a1` | 1 × bold pipe cell `output.md:18`; 1 × naive pipe cell `report.md:16`; prose `output.md:3,7,36`; prose conclusion `report.md:5`; summary bullet `report.md:36`; gate conclusion `report.md:39` | **`meets` (WRONG)** | **`below`** | probe `rounds[5]`: `legacy_output_only=meets`, `legacy_report_only=below`, `real_parse_l3_output=meets`, `candidate=below/output/fail-cell`; reflect:41 F-4. Key `l3-report.md` sha256 `6d07d711822f7346…` == `output.md` (missed-marker source persisted as dossier) |
| R2-8 | `feature-gui-time-mvp-board` | `l3-a2` | 5 × bold pipe cell `report.md` (25,26,57,61,63); 1 × `\| FAIL \| 5（…） \|` summary row `report.md:15`; 1 × `\| 总裁决 \| **FAIL / below** \|` `report.md:17`; prose `output.md:3,7`; prose conclusion `report.md:3` | **`below`** (but **not for the stated reason** — `output.md` has no QG/`Achieved` sections, so the round fell `below` by missing-section before any FAIL scan; the 7 FAIL cells in `report.md` were never read) | **`below`** | No `l3-verdict.txt` / `l3-report.md` at key root (this key is newer than the 17-round ledger); round verdict derived from `_l3_resolve_source` semantics and cross-checked with probe `legacy_output_only` for the analogous shape. Correctness from `report.md:3` `结论：**FAIL / below** — 42 条 VC 中 **37 PASS、5 FAIL**` |

R2-7 is the extra confirmed false-meets (already in reflect F-4, not in the task's `l3-a1` list). R2-8 is a new FAIL-positive surface not present in the 17-round ledger: 7 live-regex matches in a `report.md` that this framework never read for the FAIL decision.

### 1.3 Scope rounds with no uppercase `FAIL` anywhere

`feature-inline-marker-patchkit` a1/a2 (worker failed, no `report.md`), `feature-params-service` a1/a2 (no `report.md`), `feature-gui-time-mvp-board` a1, `feature-mvp-closeout` a3, `feature-l3-verdict-source-fallback` a1. None contributes a positive FAIL surface; none is a usable AC-001 anchor.

## 2. Verbatim line inventory (required)

Format: `<relative-path>:<line>: <byte-exact line>`. All paths are relative to `H:\git\E2Feature\.agenticdoc\`. Section labels come from the file's own H2 offsets.

### 2.1 `feature-inline-marker-patchkit` / `ap-feature-inline-marker-patchkit-l3-a3`

Sections — `output.md`: TL;DR 1–4, Summary 5–8, QG 9–69, Achieved 70–91. `report.md`: H1 1, QG 7–69 (incl. `### Function Flow / 治理门禁` 48–52), Achieved 70–.

```text
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:3: 状态：❌ FAIL — 36 项 VC 中 28 PASS、8 FAIL；主要阻断为 HEAD 可读范围违规、异常流证据缺失、计数语义不一致及 T-013 证据链不闭合。
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:7: 状态：❌ FAIL — 36 项 VC 中 28 PASS、8 FAIL；主要阻断为 HEAD 可读范围违规、异常流证据缺失、计数语义不一致及 T-013 证据链不闭合。
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:22: | VC-006 | **FAIL** | no | 报告存在 `head_anchored=false`、`head_readable=false`，与“每条记录 HEAD 可读并有有效行界”冲突 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:30: | VC-014 | **FAIL** | yes | 缺 `exit 116 FM_REPLAY_NOT_IDEMPOTENT` 异常流证据 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:31: | VC-015 | **FAIL** | yes | 缺 `exit 117 FM_ROLLBACK_INCOMPLETE` 异常流证据 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:36: | VC-020 | **FAIL** | no | `removed_markers=2`，但 `injected_pairs=1`；不满足锁定的等值语义 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:38: | VC-022 | **FAIL** | yes | 六反例存在，但未按质检规则进入 `verify_report.json#tamper`；T-013 exec evidence 缺失 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:44: | VC-028 | **FAIL** | no | report 中存在带 feature_id 且 HEAD 不可读的文件，检查面被擅自缩至注入目标 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:48: | VC-032 | **FAIL** | yes | VC-032 未进入 `tamper[]`，且缺 tamper-not-detected→119 异常出口记录 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:50: | VC-034 | **FAIL** | yes | T-013 evidence 文件缺失；编码报告是 T-014 收尾前快照，不能证明最终文件集 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:3: **结论：❌ FAIL（28/36 VC PASS，8/36 FAIL；未重跑命令）**
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:16: | VC-006 | **FAIL** | no（先修口径/实现） | verifier 声称 missing_at_head=0，但 `attribution.head.json` 存在 `head_anchored=false`，`region_report.json` 明示 `head_readable=false/head_line_count=null`；T-003/T-004 还登记 136 项中 68 文件不在 HEAD。与“每条记录有有效 HEAD 行界”冲突。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:24: | VC-014 | **FAIL** | yes（补异常流后） | 正常重放断言通过，但 `[FLOW] §5.2` 要求每个异常分支触发；无 `delta != 0 → exit 116 FM_REPLAY_NOT_IDEMPOTENT` 记录。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:25: | VC-015 | **FAIL** | yes（补异常流后） | 正常/no-op/二次回滚有证据；无 `[FLOW] §5.3` 的 `porcelain != 0 → exit 117 FM_ROLLBACK_INCOMPLETE` 反例。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:30: | VC-020 | **FAIL** | no（先修计数语义） | 断言要求 `removed_markers = 注入对数`；`#checks[VC-020].observed` 为 removed_markers=2、removed_pairs=1、injected_pairs=1，却标 PASS。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:32: | VC-022 | **FAIL** | yes | `reverse_report.json` 证明六反例，但 evidence-requirement 质检规则要求 VC-022 的篡改证据进入 `verify_report.json#tamper`；当前 tamper 只 target VC-012/026/007。且要求的 `evidence/research/exec-marker-013-*.md` 不存在。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:38: | VC-028 | **FAIL** | no（先修范围/实现） | 要求 reports 中每个 `(feature_id,file)` 的文件均可由 HEAD 读取；`region_report.json` 存在带 feature_ids 且 `head_readable=false` 的 no-net-change 文件。T-004 未经 AC 变更把检查面缩为“注入目标”。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:41: | VC-031 | PASS | no | `verify_report.json#tamper` 三项 VC-012→114、VC-026→119、VC-007→113，均 detected/FAIL/nonzero。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:42: | VC-032 | **FAIL** | yes | checks 中有 6 反向、4 正向、engine_refs=0、red/green，但质检规则还要求 VC-032 篡改证据位于 `#tamper`；当前无 target VC-032，且 `[FLOW] §5.4` 无“篡改未检出→119”实际异常出口记录。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:44: | VC-034 | **FAIL** | yes | `regression_report.json` 记录 featuremark 0 fail、全量 9=registered 9、subset/no-deselect；但 T-013 exec evidence 文件不存在，且 `encoding_report.json` 是 T-014 前快照（仍列旧 sandbox/verify/pointer/key-decision/task-014 字节），不能证明最终文件集编码。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:53: | §5.2 pack→apply | **FAIL** | 缺 exit 116 实际反例。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:54: | §5.3 rollback | **FAIL** | 缺 exit 117 实际反例。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:55: | §5.4 verify+guard | **FAIL** | 缺 tamper-not-detected→119 实际异常出口；VC-022/032 未按质检规则进入 tamper[]。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:56: | T-013 证据闭环 | **FAIL** | task/JSON 声称存在 `evidence/research/exec-marker-013-*.md`，实际 ENOENT；worker output 只有 checkpoint。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:57: | evidence pointer | **FAIL** | `marker.pointer.json` 不含 exec-marker-013、reverse/regression/encoding 报告，却声明执行证据已追加。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:58: | Agentic 状态 | **FAIL / needs-rerun** | `pm-state.md` 仍把 T-001..014 全列为未开始/未验证；`achieved.md` 仍写 L3 stalled。须由 PM 正规同步后跑 phase audit。 |
feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/report.md:60: **汇总：28 PASS / 8 FAIL / 36；质检未通过，无 override。**
```

Section attribution: `output.md:3` TL;DR · `output.md:7` Summary · `output.md:22–50` QG VC table · `report.md:3` QG preamble （outside QG slice） · `report.md:16–44` QG VC table · `report.md:53–58` QG `### Function Flow / 治理门禁` table · `report.md:60` QG summary bullet · `report.md:41` QG table row, FAIL is data text not a marker.

### 2.2 `feature-sampling-human-channel` / `ap-feature-sampling-human-channel-l3-a1`

Sections — `output.md`: TL;DR 1–4, Summary 5–8, QG 9–28, Achieved 29–44. `report.md`: H1 1, QG 5–52 (`### 复评口径` 7–45, `### Gate 汇总` 46–52), Achieved 53–.

```text
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/output.md:3: FAIL — 21/30 VC 通过，9 项失败；关键阻塞是 append-only 历史违规、回归仍有 2 个失败、禁止写面被改写及最终导出 manifest 漂移。
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/output.md:7: FAIL — 21/30 VC 通过，9 项失败；关键阻塞是 append-only 历史违规、回归仍有 2 个失败、禁止写面被改写及最终导出 manifest 漂移。
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/output.md:12: - **FAIL：9**
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/output.md:23: - **VC-024**：验收回归实际为 exit 1，`2 failed / 1142 passed`，不能声明 `tests_green=true`。
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:3: > 结论：**FAIL（21 PASS / 9 FAIL；9 项 needs-rerun）**。本轮严格采用证据记录制，未重跑任何命令。主要阻塞为：审计库发生过删行/整库替换式“还原”、AC-024 实际仍有 2 个失败、禁止写面 `build-runs/eval/**` 被改写、稳定 CSV 不满足字段契约、失败原子性不成立，以及最终 manifest 已与磁盘产物漂移。
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:15: | VC-001 | **FAIL** | yes* | T-013 仅以 git 未跟踪目录行集得出 `partition_outside_whitelist=0`，但 T-014 明确把报告/指针双落到分片根 `H:\git\E2Feature\evidence\**`；`spec.md §2.1` 的穷举白名单不含该根目录。见 `workers/...-014-.../output.md`“报告双落点”和 `evidence/exec-sampling-pointer.json` 的 `root_evidence` 条目。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:17: | VC-003 | **FAIL** | yes* | T-007 §5.2 记录同包第 2 行产生后，在副本中移除 no-delete trigger、DELETE 该行并 `os.replace` 回生产库；行数实际经历 21→22→21，不能成立 `verdict_rows_monotonic=true`。最终 20 条历史行虽保留，生命周期单调性已被反证。见 `evidence/research/exec-sampling-007-machine-per-stratum-rollup-20260924.md`。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:23: | VC-009 | **FAIL** | yes | 稳定导出 `build-runs/sampling/exports/sampling_package_sp-559bb7c8706b0ae7.csv` 中 `machine_value,machine_judge` 每行为空；这直接违反 AC-009“任一列为空 ⇒ exit≠0”。T-007 也明确登记两列“故意保持 null”。`columns=14` 只证明列名存在，不能证明字段自足。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:24: | VC-010 | **FAIL** | yes | 当前稳定 `sampling_strata.csv` 表头仅为 `stratum_key,N_h,n_h,quota,reason,tier_axis`，缺 AC-010 要求的逐格 `hits_h/p_h` 与三溯源字段。T-007 的内存/SQLite 机判报告不能替代指定稳定 CSV 契约。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:29: | VC-015 | **FAIL** | yes* | append-only 的生命周期断言被 T-007 §5.2 自曝事实直接否证：临时移除 no-delete trigger、DELETE 审计行并整库替换；此外 T-006/T-007 对自有 append-only 库采用“tmp 新库 → `os.replace`”重建已存行。终态触发器正常不能追溯性地修复该违规。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:35: | VC-021 | **FAIL** | yes | T-011 明确记录 Phase C（审计 append）注入失败时“package present”，仅以 `missing_machine_verdict` 暴露；这违反 AC-021“任一步失败 ⇒ 自有库无该 package 行、审计库无新增行”。`failed_step_no_package=true` 只覆盖前置注入点，不能代表所有步骤。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:38: | VC-024 | **FAIL** | yes | 验收命令实际 exit=1，结果 `2 failed, 1142 passed`；因此 `[VERIFY] ... tests_green=true` 与原始记录矛盾。`baseline_not_regressed=true` 不能替代 AC-024 的“全绿”。见 `evidence/research/exec-sampling-tests-20260924.md`。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:40: | VC-026 | **FAIL** | yes | `evidence/exec-sampling-write-surface-20260924.json` 明确记录 AC-024 命令改写 `build-runs/eval/exports/**` 4 个 JSON；该前缀被 AC-026 明令全生命周期写入 0。把副作用“单列并排除”是改验收口径，不会使 `all_zero=true` 成立。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:41: | VC-027 | PASS | no | T-002/T-014 记录 import 白名单违规 0、私有符号 0、复制片段 0、契约不匹配 fail-closed、静默兼容 0。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:44: | VC-030 | **FAIL** | yes | 最终 manifest 已陈旧：`sampling_manifest.json` 记录 `sampling_review.json` 为 4809 B/`fbe4…`、`sampling_verdict.json` 为 6346 B/`e985…`；T-014 最终指针记录同两文件为 4816 B/`4588…`、6353 B/`27ce…`。因此当前 `export_bytes_equal=true` 不成立，且 `summary.json` 也未列入 manifest 的稳定导出集合。 |
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:49: - **FAIL：9**：VC-001、003、009、010、015、021、024、026、030。
feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/report.md:50: - **needs-rerun：9**（均为 FAIL 项；带 `*` 的 VC-001/003/015 还需先做治理裁决或建立新的干净验收窗口，单纯重跑不能消除已发生的生命周期违规）。
```

Section attribution: `output.md:3` TL;DR · `output.md:7` Summary · `output.md:12` QG summary bullet (**the missed marker**) · `output.md:23` QG failure bullet (only lowercase `failed`, not `FAIL`) · `report.md:3` QG preamble （outside QG slice） · `report.md:15–44` QG VC table · `report.md:41` QG table row (lowercase `fail-closed`, control) · `report.md:49–50` QG `### Gate 汇总` bullets.

### 2.3 `feature-mvp-closeout` / `ap-feature-mvp-closeout-l3-a1`

Sections — `output.md`: TL;DR 1–4, Summary 5–14, Changed Files 15–18, Verification Steps 19–22, Exit Reason 23–26, Read Scope 27–37. `report.md`: H1 1, QG 7–80 (`### 前置核查` 9–19, `### VC 断言表` 20–64, `### 汇总` 65–73, `### 遗留与解除阻塞动作` 74–79), Achieved 81–.

```text
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/output.md:3: ❌ FAIL — 38 个 VC 均因 reviewer `read_scope` 达到 8/8 上限而无法核验证据，已全部标记 `needs-rerun`。
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/output.md:7: ❌ FAIL — 38 个 VC 均因 reviewer `read_scope` 达到 8/8 上限而无法核验证据，已全部标记 `needs-rerun`。
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:3: **结论：❌ FAIL（证据不可核验）**
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:16: | spec AC、design VC、AC→VC 覆盖、fingerprint、task refs | FAIL / needs-rerun | 对应文件内容未获准读取，不能核验 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:17: | `[VERIFY]` 结果、退出码与错误指纹 | FAIL / needs-rerun | worker outputs 内容未获准读取；禁止以文件存在代替证据充分性 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:22: 设计中 VC 总数由执行任务名 `012-verify-single-command-38vc-tamper-protected` 表明为 38；由于 `design.md` 和记录内容不可读，下表不臆造断言文本。所有条目均按“未能核验”判 FAIL，并标记 needs-rerun。这里的 needs-rerun 表示：若不能恢复对原始记录的读取，则必须重新生成可读验证证据后才能确认；优先动作仍是恢复读取原记录，而不是无条件重跑。
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:26: | VC-001 | FAIL | yes | `design.md` 与 EXECUTE `[VERIFY]` 记录不可读 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:27: | VC-002 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:28: | VC-003 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:29: | VC-004 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:30: | VC-005 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:31: | VC-006 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:32: | VC-007 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:33: | VC-008 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:34: | VC-009 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:35: | VC-010 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:36: | VC-011 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:37: | VC-012 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:38: | VC-013 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:39: | VC-014 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:40: | VC-015 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:41: | VC-016 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:42: | VC-017 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:43: | VC-018 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:44: | VC-019 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:45: | VC-020 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:46: | VC-021 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:47: | VC-022 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:48: | VC-023 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:49: | VC-024 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:50: | VC-025 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:51: | VC-026 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:52: | VC-027 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:53: | VC-028 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:54: | VC-029 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:55: | VC-030 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:56: | VC-031 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:57: | VC-032 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:58: | VC-033 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:59: | VC-034 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:60: | VC-035 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:61: | VC-036 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:62: | VC-037 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:63: | VC-038 | FAIL | yes | 同上 |
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:69: - FAIL：38
feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:72: - 门禁结论：**❌ FAIL**。不得推进 DONE，也不得引用本报告声称 MVP 验证通过。
```

Section attribution: `output.md:3` TL;DR · `output.md:7` Summary · `report.md:3` QG preamble （outside QG slice） · `report.md:16–17` QG `### 前置核查` table · `report.md:22` QG prose · `report.md:26–63` QG VC table (**38 naive cells**) · `report.md:69,72` QG `### 汇总` bullets.

### 2.4 `feature-cigate-install-kit` / `ap-feature-cigate-install-kit-l3-a1` (negative control)

Sections — `output.md`: TL;DR 1–4, Summary 5–22, Changed Files 23–26, Verification Steps 27–30, Exit Reason 31–34, Read Scope 35–39 (no QG, no Achieved → does not qualify). `report.md`: QG 3–62, Achieved 63–.

```text
feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-l3-a1/output.md:3: PASS（有非阻断遗留）——35/35 条 VC 均有 PASS 证据，FAIL=0，needs-rerun=0。
feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-l3-a1/output.md:7: PASS（有非阻断遗留）——35/35 条 VC 均有 PASS 证据，FAIL=0，needs-rerun=0。
feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-l3-a1/output.md:12: - 最终 verifier：`verify_ok=true`、`fail_items=[]`、`pending_items=[]`
feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-l3-a1/report.md:9: - 最终 `build-runs/ci/exports/verify_report.json#summary`：`verify_items=35`、`verify_rows=34`、`verify_ok=true`、`fail_items=[]`、`pending_items=[]`、`missing_items=[]`。
feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-l3-a1/report.md:50: **汇总**：PASS 35，FAIL 0，needs-rerun 0。质量门禁结论为 **PASS（有非阻断证据维护遗留）**。
feature-cigate-install-kit/workers/ap-feature-cigate-install-kit-l3-a1/report.md:53: - Function Flow：输入/参数 fail-closed、三门禁、安装回滚、fixture E2E 的正常与异常节点均被 VC-005～024、VC-031～033 覆盖。
```

Section attribution: `output.md:3` TL;DR · `output.md:7` Summary · `output.md:12` Summary bullet (`fail_items=[]`) · `report.md:9` QG bullet · `report.md:50` QG summary bullet · `report.md:53` QG bullet (lowercase `fail-closed`). Correct verdict `meets` per `report.md:50`; framework verdict `below` per probe `rounds[0]`.

### 2.5 `feature-tier-a-closeout` / `ap-feature-tier-a-closeout-l3-a1` (negative control)

Sections — `output.md`: TL;DR 1–4, Summary 5–15, Changed Files 16–19, Verification Steps 20–23, Exit Reason 24–27, Read Scope 28–42 (no QG, no Achieved). `report.md`: H1 1, QG 5–53 (`### 汇总与门禁判定` 42–48, `### 遗留 / needs-rerun` 49–53), Achieved 54–.

```text
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a1/output.md:12:   - `## Quality Gate Report`：逐条 VC PASS/FAIL、needs-rerun 与证据引用
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a1/output.md:14: - 关键限制：现有记录只能证明本 key 未新增回归；当前全量测试仍受 sibling key 的 4 个失败影响，不能宣称 AC-025 的字面“0 failed”已经达成。 Tools used: find, grep, read, worker_file (20 calls).
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a1/report.md:44: - VC：**32 PASS / 0 FAIL**（按冻结的 VC 与已记录 EXECUTE 证据）。
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a1/report.md:45: - `needs-rerun`：**1 项（VC-025 的“当前全量 0 failed”字面口径）**。
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a1/report.md:47: - **复评结论：PASS（证据记录口径），附 1 项必须带入后续 closeout 的 rerun 遗留。** 此结论不授权把项目级 AC-025 的字面“全量测试 0 failed”写成已达成。
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a1/report.md:51: 1. **全量 pytest 静态窗口复跑**：待 `feature-trend-two-points` 等 sibling key 停止修改相关测试面，或使用隔离快照，执行 `python -X utf8 -m pytest -q`。验收必须明确记录 `passed>=1017` 且 `failed=0`；当前 before/after 同为 4 failed 只能证明本 key 无新增回归。去向沿用 `achieved.md`：`feature-mvp-closeout`。
```

Other lines in this file pair contain only lowercase `fail`/`failed` (`report.md:16,32,33,46`). Section attribution: `output.md:12,14` Summary bullets · `report.md:44,45,47,51` QG `### 汇总与门禁判定` / `### 遗留` bullets.

### 2.6 `feature-tier-a-closeout` / `ap-feature-tier-a-closeout-l3-a2` (negative control)

Sections — `output.md`: TL;DR 1–4, Summary 5–14, Changed Files 15–18, Verification Steps 19–22, Exit Reason 23–26, Read Scope 27–44 (no QG, no Achieved). `report.md`: H1 1, QG 5–58 (`### 审查口径` 7–48, `### 汇总与门禁结论` 49–58), Achieved 59–.

```text
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a2/output.md:3: PASS — 32/32 VC 通过，VC-025 隔离回归为 1573 passed / 0 failed，当前 needs-rerun=0。
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a2/output.md:7: PASS — 32/32 VC 通过，VC-025 隔离回归为 1573 passed / 0 failed，当前 needs-rerun=0。
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a2/report.md:40: | VC-025 | PASS | 否 | **上一轮缺口已解除**：`vc025_isolation_report.json` 与 repair a2 `[VERIFY] VC-025` 记录认证 12 行决策快照上的全量 suite `1573 passed / 0 failed / exit 0`、`isolation_ok=true`，且 `source_unchanged=true`、`copy_matches_certified=true`。live 记录为 `1602 passed / 2 failed`，两项均位于外部 `tests/featureeval/test_prejudge.py`，本 key `internal_failures=0`；故隔离回归充分，live 外部红不冒充达成。 |
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a2/report.md:53: - FAIL：0
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a2/report.md:64: - 针对上一轮唯一 `needs-rerun` 的 VC-025，核验 repair a2 的隔离快照全量回归：1573 passed、0 failed；同时保留 live 1602 passed、2 个外部失败的真实状态。
feature-tier-a-closeout/workers/ap-feature-tier-a-closeout-l3-a2/report.md:76: 1. **外部 K6 适配**：live 全量仍为 `1602 passed / 2 failed`，均来自 `tests/featureeval/test_prejudge.py` 对 `HISTORICAL_ROWS=12` 的硬编码与 append-only 20 行事实冲突；归属 `feature-mvp-closeout` / K6 侧适配 key。修复后应重跑 live `python -X utf8 -m pytest -q`，但这不是本次 L3 判定所缺证据。
```

Section attribution: `output.md:3,7` TL;DR / Summary · `report.md:40` QG VC table · `report.md:53` QG `### 汇总与门禁结论` · `report.md:64` Achieved (`### 做了什么`) · `report.md:76` Achieved (`### 遗留`). `- FAIL：0` at `report.md:53` is the **only** uppercase FAIL in the whole round and it is a zero-count.

### 2.7 `feature-l3-readcap-injection` / `ap-feature-l3-readcap-injection-l3-a1` (extra false-meets)

Sections — `output.md`: TL;DR 1–4, Summary 5–8, QG 9–42, Achieved 43–49. `report.md`: H1 1, QG 3–40 (`### 门禁汇总` 34–40), Achieved 41–.

```text
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/output.md:3: FAIL — VC-006 未达成：当前真实派发的 L3 reviewer 仍使用旧的 8 次/64 KiB 上限，需重启 conductor 后重新派发复评。
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/output.md:7: FAIL — VC-006 未达成：当前真实派发的 L3 reviewer 仍使用旧的 8 次/64 KiB 上限，需重启 conductor 后重新派发复评。
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/output.md:18: | VC-006 | **FAIL** | **YES** | 当前 `task.md` 无两条 cap；本会话实际触发 8/8 与 65536 B 旧上限。 |
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/output.md:21: | VC-009 | PASS（记录证据） | NO | 非法配置降级及 fail-closed 测试有记录。 |
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/output.md:23: | VC-011 | PASS（记录证据） | NO | 非法 cap 不变成无限值，4 条 fail-closed 用例。 |
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/output.md:36: **门禁结论：FAIL / below。**
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/report.md:5: **结论：FAIL / below。** 当前这次真实派发的 reviewer 仍未收到 cap：`workers/ap-feature-l3-readcap-injection-l3-a1/task.md` 的 frontmatter 在 `read_scope` 后没有 `l2_read_file_cap` / `l2_read_byte_cap`。本次复评随后实际命中旧上限：`cap-byte`（已读 54,312/65,536 B）及 `cap-file`（8/8）。因此 VC-006 不成立，且 L3 无法遍历主要 `[VERIFY]` 原始证据；不得按执行期自报的 22/22 直接判 meets。
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/report.md:16: | VC-006 | conductor 重启后至少一个真实派发任务携带有效 cap | FAIL | **YES**：用户/PM 重启 conductor 后重新真实派发并重跑 L3 复评 | **直接反证**：本 worker 的 `task.md` 无两条 cap；本会话实际触发 65,536 B 与 8 次旧上限。执行期 e2e JSON 也记录 `restarted=false,real_dispatched_tasks=0,blocker_registered=true`。 |
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/report.md:36: - VC：21 条记录证据支持 PASS，1 条 **FAIL（VC-006）**。
feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/report.md:39: - 由于 VC-006 有直接反证，且本轮原始证据遍历被旧 cap 截断，门禁结论为 **FAIL / below**，不能推进完成态。
```

Section attribution: `output.md:3` TL;DR · `output.md:7` Summary · `output.md:18` QG VC table (bold cell, live regex matches, frozen misses) · `output.md:21,23` QG table rows (lowercase `fail-closed`) · `output.md:36` QG gate conclusion · `report.md:5` QG preamble line (inside QG slice) · `report.md:16` QG VC table (naive cell — frozen regex *would* match here, proving the historical miss was source×shape) · `report.md:36,39` QG `### 门禁汇总` bullets.

### 2.8 `feature-gui-time-mvp-board` / `ap-feature-gui-time-mvp-board-l3-a2` (new FAIL-positive surface)

Sections — `output.md`: TL;DR 1–4, Summary 5–21, Changed Files 22–25, Verification Steps 26–29, Exit Reason 30–33, Read Scope 34–38 (no QG, no Achieved). `report.md`: H1 1, QG 5–75 (`### 汇总` 9–20, `### VC 断言表` 21–67, `### 阻塞与 needs-rerun` 68–75), Achieved 76–.

```text
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/output.md:3: FAIL / below — 42 条 VC 复评为 37 PASS、5 FAIL；全生命周期只读约束及未限定 K5 E2E 验收存在明确证据冲突。
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/output.md:7: FAIL / below — 42 条 VC 复评为 37 PASS、5 FAIL；全生命周期只读约束及未限定 K5 E2E 验收存在明确证据冲突。
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:3: 结论：**FAIL / below** — 42 条 VC 中 **37 PASS、5 FAIL**；现有证据明确证明全生命周期只读约束与未限定 K5 E2E 验收未满足，不能以 scoped 运行或事后还原替代原 AC。
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:15: | FAIL | 5（VC-001、VC-002、VC-033、VC-037、VC-039） |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:17: | 总裁决 | **FAIL / below** |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:25: | VC-001 | **FAIL** | no | `spec.md#AC-001` 要求任一命令前后 parent 白名单外 delta=0、`E:\UEMigrator\data\**` 写入=0。T-014 `output.md#口径登记2` 与 `k9_k5_compat_report.json#repo_faces` 记录 parent porcelain **176→175** 且不相等，差异为 `data/uemigrator.db-shm/-wal`；`#db_side_effects.parent_runtime_sidecars` 还记录 sidecar 被运行中 backend 改变/重建。运行时侧车不在 spec 白名单，不能靠“分类为已知”改写 AC。T-018 的短窗口双采样无法抹去全生命周期违例。 |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:26: | VC-002 | **FAIL** | no | `spec.md#AC-002` 要求 `build-runs/{r1-full,eval,sweep}/**` 全生命周期逐文件 sha+bytes 不变。`k9_regression_baseline.json#protected_eval_exports` 在 T-001 已记录 7 个 eval 文件变化、`unchanged_all=false`；`k9_regression_report.json#eval_exports_face` 又记录 7 个 eval 文件相对 step-0 变化、`reproduced=false`；T-014 还记录 sweep SQLite sidecar 创建/删除。`sources_unchanged=18` 只覆盖 board 的 18 条服务源，未覆盖 AC-002 的完整保护集合，因此现有 VC oracle 被不当收窄。 |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:51: | VC-027 | PASS | no | 同报告 VC-027：删源/坏 JSON/截断均 fail-closed，恢复后 200。 |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:57: | VC-033 | **FAIL** | **yes** | 原验收命令是**未限定** `node e2e/feature-slicing-smoke.mjs` 且要求 exit 0；T-014 `output.md` 与 `k9_k5_compat_report.json#runs.after_full` 明确记录实际 **exit 1（8/9）**。只有额外设置 `K5_E2E_ONLY=existing-routes` 的子集运行 exit 0，spec/task/design 未授权用 scoped run 替代全命令。此外任务书字面 `git diff --numstat frontend/e2e/feature-slicing-smoke.mjs` 实际为空，`+1/-1` 来自另行采用的 `--no-index` 快照口径。故 `[VERIFY] VC-033 ... exit=0 numstat=+1/-1` 与原验收不符。 |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:61: | VC-037 | **FAIL** | **yes** | `verify_board.py` 输出 42/42 的前提是把 VC-033/039 的 scoped K5 结果当成 full K5 exit 0，并把 VC-001/002 的全生命周期保护面缩成收尾短窗口/18 源。因此它没有正确“复算全部 AC/VC”；5 类注入本身通过，但总门禁结论不可信。修正 oracle 后应重跑。 |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:63: | VC-039 | **FAIL** | **yes** | `spec.md#AC-028④` 与 T-017 验收命令要求未限定 K5 E2E exit 0；`k9_regression_report.json#k5_e2e` 实际加了 `K5_E2E_ONLY=existing-routes`，而 `k9_k5_compat_report.json#runs.after_full.exit_code=1`。将跨 key 的 `decision-audit` 红登记为遗留是诚实的，但不能同时把原 VC 判绿。pytest 的 9 条失败集合差集为空、tsc/vitest/mount 其余子项可接受。 |
feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:74: 5. 已知但不单独新增 VC 失败：parent pytest 仍为 9 failed（均在登记集合）、`P9-R14` 尚未核销、人工生产样本仍为 0、Phase B 仍未实现。
```

Section attribution: `output.md:3,7` TL;DR / Summary (never read — `output.md` does not qualify) · `report.md:3` QG preamble （outside QG slice） · `report.md:15,17` QG `### 汇总` table · `report.md:25,26,57,61,63` QG VC table · `report.md:51` QG table row (lowercase control) · `report.md:74` QG `### 阻塞与 needs-rerun`.

## 3. Shape classification with character-level regex analysis

Live regex `\|\s*\**\s*FAIL\b` (`conductor.py:1148`); frozen regex `\|\s*FAIL\b` (`conductor.py:1108`). Both are case-sensitive, both require a literal `|` earlier in the line, and `_l3_resolve_source` applies them to the `## Quality Gate Report` slice only.

| id | shape | example (file:line) | live regex | frozen regex | character-level reason |
|---|---|---|---|---|---|
| S1 | naive pipe cell | `mvp a1 report.md:26` `\| VC-001 \| FAIL \| yes \| … \|` | **MATCH** | MATCH | `\|`←`\|`, `\s*`←` `, `\**`←ε, `\s*`←ε, `FAIL`←`FAIL`, `\b` holds before ` ` |
| S2 | bold pipe cell | `marker a3 output.md:22` `\| VC-006 \| **FAIL** \| no \| …` | **MATCH** | **miss** | `\**` consumes `**`; `\b` holds because `*` is a non-word char |
| S3 | pipe cell with slash verdict | `gui-time a2 report.md:17` `\| 总裁决 \| **FAIL / below** \|`; `mvp a1 report.md:16` `\| spec AC… \| FAIL / needs-rerun \| …`; `marker a3 report.md:58` `\| Agentic 状态 \| **FAIL / needs-rerun** \|` | **MATCH** | MATCH only for the unbold variant | same as S1/S2; `/` after `FAIL` is non-word so `\b` holds |
| S4 | Chinese-colon bullet, bold | `sampling a1 output.md:12` `- **FAIL：9**`; `sampling a1 report.md:49` `- **FAIL：9**：VC-001、…` | **miss** | **miss** | no `|` in the line → `\|` cannot match. The full-width colon `：` (U+FF1A, non-word) is *not* the blocker: a hypothetical `\| **FAIL：9** \|` **would** match (`\b` holds before `：`) |
| S5 | Chinese-colon bullet, unbold | `mvp a1 report.md:69` `- FAIL：38`; `tier-a a2 report.md:53` `- FAIL：0` (must NOT fire) | **miss** | **miss** | same as S4. This shape is shared by a positive (38) and a negative (0) — see gap G4 |
| S6 | prose conclusion line | `sampling a1 output.md:3,7` `FAIL — 21/30 …`; `gui-time a2 output.md:3,7` `FAIL / below — …`; `readcap a1 output.md:3,7` `FAIL — VC-006 未达成…`; `mvp a1 output.md:3,7` `❌ FAIL — 38 个 VC …`; `marker a3 output.md:3,7` `状态：❌ FAIL — 36 项 VC …` | **miss** | **miss** | no `|` → `\|` fails. Additionally these lines sit in `## TL;DR` / `## Summary`, outside the QG slice |
| S7 | bold conclusion line | `marker a3 report.md:3` `**结论：❌ FAIL（28/36 VC PASS，8/36 FAIL；未重跑命令）**`; `sampling a1 report.md:3` `> 结论：**FAIL（21 PASS / 9 FAIL；…）**`; `readcap a1 report.md:5` `**结论：FAIL / below。**`; `mvp a1 report.md:3` `**结论：❌ FAIL（证据不可核验）**`; `gui-time a2 report.md:3` `结论：**FAIL / below** — …` | **miss** | **miss** | no `|`. In `report.md` these sit in the pre-QG preamble (lines 3–5) and are excluded by the QG slice anyway; `readcap a1 report.md:5` is the one case that lands *inside* the QG slice (QG starts at line 3) and is still missed |
| S8 | bold summary / gate-conclusion line | `marker a3 report.md:60` `**汇总：28 PASS / 8 FAIL / 36；质检未通过，无 override。**`; `mvp a1 report.md:72` `- 门禁结论：**❌ FAIL**。…`; `readcap a1 output.md:36` `**门禁结论：FAIL / below。**`; `readcap a1 report.md:39` `- …门禁结论为 **FAIL / below**…` | **miss** | **miss** | no `|` |
| S9 | needs-rerun line referencing FAIL | `sampling a1 report.md:50` `- **needs-rerun：9**（均为 FAIL 项；…）` | **miss** | **miss** | no `|`; `FAIL` is preceded by a space in prose |
| S10 | negation / zero / descriptor (must NOT fire) | `FAIL=0` (`cigate a1 output.md:3,7`), `FAIL 0` (`cigate a1 report.md:50`, `cigate a2 report.md:52`, `params a3 output.md:12`, `mvp a2 output.md:10`, `freshness output.md:25`/`report.md:31`), `0 FAIL` (`tier-a a1 report.md:44`), `- FAIL：0` (`tier-a a2 report.md:53`), `fail_items=[]` (`cigate a1 output.md:12`, `report.md:9`), `fail-closed` (`cigate a2 output.md:53,55,61`; `tier-a a1 report.md:16,32`; `tier-a a2 report.md:19,24`; `sampling a1 report.md:41`; `mvp a2 report.md:35`; `gui-time a2 report.md:51,80`), `0 failed` / `2 failed` / `4 failed` / `9 failed`, `pytest_failed=0`, `tamper_failures=4`, `failed=0` | **miss** | **miss** | none has `|` adjacent to `FAIL`; `fail-closed` / `failed` are also lowercase so the case-sensitive regex cannot match |

Additional non-positive form present but not a verdict: `marker a3 report.md:41` (`…均 detected/FAIL/nonzero。`) — a data descriptor inside a table row; no pipe adjacent to `FAIL`, no match, correctly inert.

Where each shape is used (rounds):

- S1: `feature-mvp-closeout` a1 (38), `feature-l3-readcap-injection` a1 report.md, `feature-gui-time-mvp-board` a2 report.md (`| FAIL | 5（…） |`).
- S2: `feature-inline-marker-patchkit` a3 (8 + 14), `feature-sampling-human-channel` a1 report.md (9), `feature-l3-readcap-injection` a1 output.md (1), `feature-gui-time-mvp-board` a2 report.md (5).
- S3: `feature-mvp-closeout` a1 report.md (2), `feature-inline-marker-patchkit` a3 report.md (1), `feature-gui-time-mvp-board` a2 report.md (1).
- S4: `feature-sampling-human-channel` a1 (`output.md:12`, `report.md:49`).
- S5: `feature-mvp-closeout` a1 `report.md:69` (positive), `feature-tier-a-closeout` a2 `report.md:53` (negative).
- S6: marker a3, sampling a1, mvp a1, readcap a1, gui-time-mvp-board a2 (TL;DR + Summary lines each).
- S7: marker a3, sampling a1, mvp a1, readcap a1, gui-time-mvp-board a2 (`report.md` conclusion).
- S8: marker a3, mvp a1, readcap a1.
- S9: sampling a1.
- S10: cigate a1/a2, tier-a a1/a2, mvp a2, params a3, freshness a1, marker a3 (`report.md:41`), sampling a1 (`report.md:41`), gui-time a2, tier-a a3.

Aggregate: **80/80 live-regex matches are S1–S3 (pipe cells); 0/25 positive non-pipe lines (S4–S9) match.**

## 4. Coverage gaps (design input)

**G1 — Non-pipe positive forms are structurally unreachable.** The `|` anchor is the entire discriminator. 25 real positive lines (S4–S9) are missed. Reproduction worth pinning in AC-001: `sampling a1 output.md:12` is a real round's *only* positive marker in its deciding source.

**G2 — QG-slice-only scan excludes the TL;DR/Summary convention.** Every reviewer duplicates its verdict into `## TL;DR` (line 3) and `## Summary` (line 7); 5 rounds do this (marker a3, sampling a1, mvp a1, readcap a1, gui-time a2). Because `qg = _md_section(text, "## Quality Gate Report")` (`conductor.py:1189`), none of those lines is ever scanned. `## Achieved` is likewise unscanned (`conductor.py:1172` only checks presence). If a future reviewer writes FAIL prose + an all-PASS QG table, the round is a false-meets with no compensating pipe cell. Not observed today, but one step away: `sampling a1 output.md` is exactly that shape and was rescued only by `report.md`.

**G3 — The rescue of `sampling a1` is incidental, not designed.** `sampling a1` resolves `below` today only because `report.md` happens to contain 9 bold cells (probe `rounds[13]` → `candidate=below/report/fail-cell`). If that reviewer had used bullet-style FAIL in both files, the round would still be `meets`. This is the single most important regression anchor for the new key: the AC-001 replay must use `output.md`'s `- **FAIL：9**` and must not depend on `report.md`.

**G4 — Shape alone cannot separate S4/S5 positive from negative.** `- **FAIL：9**` (must fire) and `- FAIL：0` (must not fire) differ only by bold + count; `FAIL 0` / `FAIL=0` / `0 FAIL` are the same token with different word order. Any widening of S4/S5 requires a value-aware or negation-aware rule (spec AC-002). Corpus anchors: positives `sampling a1 output.md:12`, `sampling a1 report.md:49`, `mvp a1 report.md:69`; negatives `cigate a1 output.md:3,7`, `cigate a1 report.md:50`, `cigate a2 output.md:3,7,84`, `cigate a2 report.md:1,52`, `tier-a a1 report.md:44`, `tier-a a2 report.md:53`, `mvp a2 output.md:10`, `params a3 output.md:12`, `freshness output.md:25`, `freshness report.md:31`.

**G5 — Negation forms are concentrated in QG tables and summary bullets, not in `## Achieved`.** 16 of the 121 FAIL lines are negation/descriptor, spread over 9 rounds. A widened detector that scans the whole document (rather than the QG slice) must survive all of them; today the QG slice already excludes most of the raw pytest lines (`0 failed`, `2 failed`, `3005 passed / 9 failed`) only when they happen to be outside QG — several are inside (`cigate a2 report.md:10`, `tier-a a2 report.md:40`, `gui-time a2 report.md:74`).

**G6 — Provenance pinpoints the failure.** The dossier source for both confirmed false-meets equals the source that carried the missed marker: `feature-sampling-human-channel/l3-report.md` sha256 `f607fb61f9ba3987…` == `workers/ap-feature-sampling-human-channel-l3-a1/output.md`; `feature-l3-readcap-injection/l3-report.md` sha256 `6d07d711822f7346…` == `workers/ap-feature-l3-readcap-injection-l3-a1/output.md`. `feature-inline-marker-patchkit/l3-report.md` (582 B) instead mirrors `l3-a2/output.md`, i.e. the dossier is stale relative to a3 — separate defect (provenance key domain), noted only so the corpus is not misread.

**G7 — The frozen primitive is strictly narrower than the live one.** Frozen `\|\s*FAIL\b` matches 42 lines; live `_L3_FAIL_RE` matches 80. The 38-line delta is exactly S2 (bold pipe cells). Any AC that asserts "new superset of old" can be pinned on those 38 lines; conversely, a "not-widening" regression test must keep the frozen function byte-identical (spec GC-11).

**G8 — Predicted-but-unobserved shapes to guard in AC-001 fixtures** (do not exist in E2Feature corpus, so they must be justified as constructed variants, not claimed as observed): ASCII colon `FAIL: 9`; parenthesised `FAIL(n=9)`; markdown H3 verdict header `### FAIL`; checked-box `- [x] FAIL`; pipe cell without trailing pipe `| FAIL`; bold title `**FAIL**` alone on a line; `## Summary` section FAIL. None is in the corpus; AC-001 must not claim file:line provenance for them.

## 5. Incidental sweep (`rg -i 'fail'` over all `workers/*l3-a*/output.md|report.md`)

20 rounds inspected; 12 contain uppercase `FAIL`; 8 contain only lowercase. One-line entries for rounds outside §1.1/§1.2:

- `feature-cigate-install-kit` a2 — `output.md:3,7` `PASS —— 二轮 L3 质检确认 …FAIL=0…`, `output.md:84` `**汇总**：**PASS 35 / FAIL 0 / needs-rerun 0**。`; `report.md:1,52` same. Zero-count only, no positive marker. Framework `meets` (key `l3-verdict.txt` = `meets`), correct `meets` (probe `rounds[1]`).
- `feature-mvp-closeout` a2 — `output.md:10` `- 质量门禁：38 PASS、0 FAIL、0 needs-rerun。`; `report.md:35,44` lowercase `fail` only. Framework `below` (false-below, should be `meets`; probe `rounds[8]`, reflect:40 F-3).
- `feature-mvp-closeout` a3 — no uppercase FAIL; `output.md:45,54` lowercase `fail-closed` / `failed=0`. Framework `meets`, correct `meets` (probe `rounds[9]`).
- `feature-params-service` a3 — `output.md:12` `> 总结：**PASS 24 / FAIL 0 / needs-rerun 0**。`; `:37,43` lowercase. Framework `meets`, correct `meets` (probe `rounds[12]`).
- `feature-l3-verdict-freshness` a1 — `output.md:25` `**总计：19 PASS / 0 FAIL / 1 needs-rerun。**`; `report.md:31` `**门禁总判定：PASS（19 PASS / 0 FAIL / 1 needs-rerun）。**`; rest lowercase. Framework `meets`, correct `meets` (probe `rounds[6]`).
- `feature-tier-a-closeout` a3 — no uppercase FAIL (all lowercase `fail=0`); `report.md:8,23,39,40,43,46,62`. Framework `meets`, correct `meets` (probe `rounds[16]`).
- `feature-l3-verdict-source-fallback` a1 — no uppercase FAIL; `report.md:13,23,44` lowercase `fail-closed`. Framework `meets` (current round), correct `meets`.
- `feature-inline-marker-patchkit` a1/a2 — no uppercase FAIL; `output.md` has no QG/`Achieved` and there is no `report.md` (worker died). Framework `below`, correct `below`/`no-verdict` (probe `rounds[2]`, `rounds[3]`; `feature-l3-verdict-source-fallback/spec.md:296` R-6).
- `feature-params-service` a1/a2 — no uppercase FAIL; no `report.md`; not qualified. Framework `below`, correct `below`/`no-verdict` (probe `rounds[10]`, `rounds[11]`).
- `feature-gui-time-mvp-board` a1 — no uppercase FAIL; no `report.md`; no QG/`Achieved`. Framework verdict not recorded (no `l3-verdict.txt` at key root).

## 6. Corpus anchors suggested for this key's acceptance criteria

AC-001 positive replay (must → `below`), one per shape, all with real provenance:

| shape | anchor |
|---|---|
| naive pipe cell | `feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:26` |
| bold pipe cell | `feature-inline-marker-patchkit/workers/ap-feature-inline-marker-patchkit-l3-a3/output.md:22` |
| pipe cell with slash | `feature-gui-time-mvp-board/workers/ap-feature-gui-time-mvp-board-l3-a2/report.md:17` |
| Chinese-colon bullet | `feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/output.md:12` |
| prose conclusion | `feature-sampling-human-channel/workers/ap-feature-sampling-human-channel-l3-a1/output.md:3` |
| bold conclusion | `feature-l3-readcap-injection/workers/ap-feature-l3-readcap-injection-l3-a1/report.md:5` |
| summary/gate line | `feature-mvp-closeout/workers/ap-feature-mvp-closeout-l3-a1/report.md:72` |

AC-002 negative controls (must → not `below`), all from the corpus:

`cigate a1 output.md:3` `FAIL=0` · `cigate a1 report.md:50` `FAIL 0` · `cigate a2 output.md:84` `PASS 35 / FAIL 0` · `tier-a a1 report.md:44` `32 PASS / 0 FAIL` · `tier-a a2 report.md:53` `- FAIL：0` · `mvp a2 output.md:10` `0 FAIL` · `params a3 output.md:12` `FAIL 0` · `freshness report.md:31` `0 FAIL` · `cigate a1 output.md:12` `fail_items=[]` · `cigate a2 output.md:42` `3005 passed / 9 failed` · `gui-time a2 report.md:74` `9 failed`.

## Appendix A — Reproducible counts

| key | round | file | uppercase-FAIL lines | occurrences | live-regex matches | frozen matches |
|---|---|---|---|---|---|---|
| feature-cigate-install-kit | a1 | output.md | 2 | 2 | 0 | 0 |
| feature-cigate-install-kit | a1 | report.md | 1 | 1 | 0 | 0 |
| feature-cigate-install-kit | a2 | output.md | 3 | 3 | 0 | 0 |
| feature-cigate-install-kit | a2 | report.md | 2 | 2 | 0 | 0 |
| feature-gui-time-mvp-board | a2 | output.md | 2 | 4 | 0 | 0 |
| feature-gui-time-mvp-board | a2 | report.md | 8 | 9 | 7 | 1 |
| feature-inline-marker-patchkit | a3 | output.md | 10 | 12 | 8 | 0 |
| feature-inline-marker-patchkit | a3 | report.md | 17 | 18 | 14 | 0 |
| feature-l3-readcap-injection | a1 | output.md | 4 | 4 | 1 | 0 |
| feature-l3-readcap-injection | a1 | report.md | 4 | 4 | 1 | 1 |
| feature-l3-verdict-freshness | a1 | output.md | 1 | 1 | 0 | 0 |
| feature-l3-verdict-freshness | a1 | report.md | 1 | 1 | 0 | 0 |
| feature-mvp-closeout | a1 | output.md | 2 | 2 | 0 | 0 |
| feature-mvp-closeout | a1 | report.md | 44 | 44 | 40 | 40 |
| feature-mvp-closeout | a2 | output.md | 1 | 1 | 0 | 0 |
| feature-params-service | a3 | output.md | 1 | 1 | 0 | 0 |
| feature-sampling-human-channel | a1 | output.md | 3 | 3 | 0 | 0 |
| feature-sampling-human-channel | a1 | report.md | 12 | 13 | 9 | 0 |
| feature-tier-a-closeout | a1 | output.md | 1 | 1 | 0 | 0 |
| feature-tier-a-closeout | a1 | report.md | 1 | 1 | 0 | 0 |
| feature-tier-a-closeout | a2 | report.md | 1 | 1 | 0 | 0 |
| **total** | | **21 files** | **121** | **128** | **80** | **42** |

## Appendix B — Provenance of this note

- Reflect ledger: `.agenticdoc/_autopilot/reflect/l3-fail-marker-detection-too-narrow.md` (硬证据 table rows 15–16, 受害形态 20–23, 反例 24–25, F-3/F-4 40–41).
- Sibling per-round probe: `.agenticdoc/feature-l3-verdict-source-fallback/evidence/l3-source-real-verdicts-20260925.json` (`rounds[0..16]`, `_L3_SOURCE_ORDER` semantics; 17 rounds — newer rounds `feature-gui-time-mvp-board` a1/a2, `feature-l3-verdict-source-fallback` a1 are outside it).
- Key-level dossiers: `.agenticdoc/<key>/l3-verdict.txt`, `.agenticdoc/<key>/l3-report.md` (sha256 compared against each round's `output.md` / `report.md`).
- Detector source: `H:\git\Multi-Workers\packages\multi-workers\autopilot\conductor.py:1076,1091,1108,1145,1148,1162,1172,1180,1189`.
- Extraction was performed by a throwaway `python -X utf8` script under `%TEMP%` re-implementing `_md_section` and both regexes; no E2Feature file was written.
