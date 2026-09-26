# RQ-1 — Framework code facts for L3 FAIL-marker detection

Key: `mw-l3-fail-marker-forms` (design-phase research)
Date: 2026-09-25
Method: full read of `packages/multi-workers/autopilot/conductor.py` (2468 lines, 4 chunks), enumerated call sites via `rg`, region attribution via `git blame`/`git log -S`. Read-only except this file.
Citation convention: `path:line`. All line numbers are against working-tree HEAD `d20a270d5`.

---

## 0. Premise correction (read this first)

The task premise "the L3 reviewer verdict parser `_parse_l3_output` decides meets/below for review workers" is **not true at HEAD**.

- The live deciding chain is `_verify_loop` → `_l3_round_verdict` → `_l3_resolve_source` → `_L3_FAIL_RE`
  (`packages/multi-workers/autopilot/conductor.py:1481`, `:1196`, `:1180`, `:1148`).
- `_parse_l3_output` (`conductor.py:1091`) has **zero production call sites**. Repo-wide `rg` for `parse_l3` finds only its definition (`conductor.py:1091`) and test references:
  - `packages/multi-workers/test_autopilot_verdict_source_fallback.py:350, 462, 518, 524, 531, 534`
  - `packages/multi-workers/test_autopilot_verdict_freshness.py:615, 622, 629, 632`
  - `packages/multi-workers/test_autopilot_readcap_injection.py:865, 868, 871`
- `_parse_l3_output` uses a **different, frozen literal** `re.search(r"\|\s*FAIL\b", qg)` (`conductor.py:1108`), not `_L3_FAIL_RE`. The bold form `| **FAIL** |` is still missed by `_parse_l3_output` (pinned intentionally by `test_bold_fail_detected_and_frozen_primitive_differs`, `test_autopilot_verdict_source_fallback.py:336-368`).
- `_parse_l3_output` and `_md_section` bodies are **byte-locked by region SHA** in two test files (see §5.2).

**Design implication:** the marker-detection change must land in `_L3_FAIL_RE` (`conductor.py:1148`) and/or `_l3_resolve_source` (`conductor.py:1180`). Touching `_parse_l3_output`/`_md_section` breaks hash-locked tests and must be an explicit design decision with the locks updated.

---

## 1. Exact current verdict flow

### 1.1 Live chain (per L3 round)

1. `_verify_loop` (def `conductor.py:1442`) is invoked from `_advance_key` when the key's phase is `verify` (`conductor.py:873-874`).
2. The loop waits for any in-flight `ap-{key}-l3-*` / `ap-{key}-repair-*` row (`conductor.py:1469-1471`).
3. `used = rounds.get(f"l3:{key}", 0)` (`conductor.py:1464`). If `used == 0` it dispatches `l3-a1` and returns (`conductor.py:1472-1480`).
4. `verdict, worker_status, l3_source = _l3_round_verdict(project_root, rows, key, used)` (`conductor.py:1481`).
5. `_l3_round_verdict` (`conductor.py:1196-1225`):
   - `task_key = dispatch.task_key_for(key, f"l3-a{attempt}")` (`:1209`).
   - Worker-status gate **first** (`:1210-1215`): if the queue row status is `failed` or `needs-clarification` → `("no-verdict", status, None)`. This precedes all file reads (I-4: a crashed reviewer's placeholder `output.md` is never read).
   - Build `sources` from `_l3_source_paths` in `_L3_SOURCE_ORDER` order, keeping only readable files (`:1216-1221`; `_l3_read_source` `:1162-1169`).
   - Availability gate (`:1222-1223`): no readable source → `("no-verdict", status or "no-row", None)`.
   - Else `verdict, source = _l3_resolve_source(sources)` (`:1224`), return `(verdict, status, source)` (`:1225`).
6. `_l3_resolve_source` (`conductor.py:1180-1193`):
   - `qualifying = [(p, t) for p, t in sources if _l3_qualifies(t)]` (`:1186`) — **section presence is checked before any FAIL scan**.
   - For each qualifying source **in priority order**: extract `qg = _md_section(text, "## Quality Gate Report") or ""` (`:1188`) and `if _L3_FAIL_RE.search(qg): return "below", path` (`:1189-1190`).
   - If any source qualified and no FAIL was found in any of them → `return "meets", qualifying[0][0]` (`:1192`).
   - If no source qualified → `return "below", None` (`:1193`).
7. `_l3_qualifies` (`conductor.py:1172-1177`): `_md_section(text, "## Quality Gate Report") is not None and _md_section(text, "## Achieved") is not None`.

### 1.2 Scan surface: extracted sections only, never the full file

- FAIL scan input is exactly the extracted `## Quality Gate Report` section (`conductor.py:1188-1189`), for **each** source, including the `report.md` fallback. `## Achieved` is never FAIL-scanned.
- Neither `_l3_resolve_source` nor `_l3_round_verdict` ever passes the full file text to `_L3_FAIL_RE`.
- Consequences (all verified by reading the code, not inferred):
  - FAIL prose in the TL;DR / before the first `## ` heading is invisible (that text is outside both extracted sections; `_md_section` drops pre-header content — see §2).
  - Bullet form `- **FAIL：9**` inside `## Quality Gate Report` is still invisible until the regex is broadened (only the pipe-cell form matches).
  - A FAIL line in `## Achieved` never triggers below.
  - **Fail-closed hole relevant to AC-004:** the loop at `:1187-1190` iterates only `qualifying` sources. If `output.md` carries a FAIL but is missing one of the two sections (thus not qualifying) and `report.md` qualifies without FAIL, the result is `meets` from `report.md` (`:1191-1192`). The existing "no-whitewash" rule (`test_report_fail_not_whitewashed_by_output_pass`, `test_autopilot_verdict_source_fallback.py:297`) only covers FAILs in *qualifying* sources.
- `_L3_SOURCE_ORDER = ("output.md", "report.md")` (`conductor.py:1145`); `report-<slug>.md` is deliberately excluded (`:1141-1144`, pinned by `test_slug_report_is_not_a_fallback_source`, `test_autopilot_verdict_source_fallback.py:774`).

### 1.3 Return values and semantics

| Function | Return | Semantics |
|---|---|---|
| `_l3_resolve_source` (`:1180`) | `("below", path)` | first qualifying source whose QG section matches `_L3_FAIL_RE` |
| | `("meets", path)` | first qualifying source (priority order) when no qualifying source has a FAIL hit |
| | `("below", None)` | no source qualifies (missing section(s) / unreadable) — fail-closed |
| `_l3_round_verdict` (`:1196`) | `("no-verdict", status, None)` | worker row status `failed`/`needs-clarification` (`:1214-1215`) |
| | `("no-verdict", status_or_no-row, None)` | no readable candidate source at all (`:1222-1223`) |
| | `(verdict, status, source)` | else, from `_l3_resolve_source` |

`_verify_loop` dispatch on the result:
- `no-verdict` → `l3-no-verdict` timeline event (`:1494-1497`); re-review, or at `used >= l3_limit` persist below + `mark_stalled` (`:1498-1504`).
- `meets` with `l3_source is not None` → provenance record (`:1513-1515`), suspect fail-closed check (`:1516-1538`), then `_done_transaction` (`:1543`).
- `below` (or `meets` degraded by `_done_transaction` returning `below`, `:1544`/`:1582`) → budget check `if used >= l3_limit` → persist below + stall (`:1583-1589`); else repair dispatch (`:1590-1611`).

Note: for a `below` caused by FAIL, the provenance record at `:1513-1515` **is** written (because `l3_source is not None`); for a `below` caused by missing sections (`l3_source is None`) it is skipped.

---

## 2. `_md_section` extraction semantics (`conductor.py:1076-1088`)

```
1076 def _md_section(text, header):
1079     lines = text.splitlines()
1080     start = next((i for i, l in enumerate(lines) if l.strip() == header), None)
1081     if start is None: return None
1083     out = [lines[start]]
1084     for line in lines[start + 1:]:
1085         if line.startswith("## "): break
1087         out.append(line)
1088     return "\n".join(out)
```

Facts:
- **Locating:** first line whose `line.strip() == header`, i.e. exact string equality after stripping both ends. `header` always carries the `## ` prefix (`"## Quality Gate Report"` / `"## Achieved"`). Trailing/leading whitespace on the heading is tolerated; a decorated heading (`## Quality Gate Report (VC ...)`) or an H3 `### Quality Gate Report` does **not** match.
- **Cut boundary:** the first following line where `line.startswith("## ")` (line-start, exactly `## `). `### x` does **not** break (the first 3 chars are `###`), so H3+ sub-sections stay inside their parent H2 window. A `## ` line with leading indentation does not break either (uses `startswith`, no strip).
- **Return:** header line + body lines joined by `\n`; the trailing newline of the file is not included. If the section runs to EOF it extends to EOF.
- **No byte or line limit.** The full file is read into memory by the caller (`_l3_read_source:1167`, `output.read_text` at `:1101`) and `splitlines()` is applied to all of it; only the sliced section is returned.
- **CRLF:** `splitlines()` removes `\r\n`/`\r` terminators, so CRLF files produce clean `\n` joins (pinned by `test_failure_lines_crlf_input_strips_line_trailing_cr` for a neighbouring parser, `test_autopilot_closure.py:146`).
- **TL;DR is never extracted.** Only the two exact headers are ever requested (`:1104-1105`, `:1175-1176`, `:1188`, `:1690-1691`, `:1230+` provenance T2). Any content before the first `## ` heading (typical TL;DR/结论 line) belongs to no extracted section. This is the P-013-shaped boundary the design must respect: scanning "sections only" cannot see TL;DR; a full-file scan is the only way to include it.
- **Region SHA lock:** the body of `_md_section` is byte-locked (see §5.2). Even whitespace/comment changes inside `def _md_section(` break tests.

---

## 3. Consumers of the verdict and blast radius

### 3.1 Consumer map

| # | Consumer | Location | What it reads | Blast radius: `meets → below` (true or false negative fix) | Blast radius: `below → meets` (detector false positive + broadened regex) |
|---|---|---|---|---|---|
| 1 | Done transaction | `_done_transaction` `conductor.py:1670-1813` | `l3_source` bytes: re-checks both sections (`:1690-1693`) | Never entered; nothing written (see #2..#6) | n/a (below never enters) |
| 2 | QG evidence artifact | `:1699-1712` | `_md_section(l3_source, "## Quality Gate Report")` | Not written | A new `evidence/quality-gate-report-<ts>.md` is written; if one already exists it is reused (`:1699-1700`) |
| 3 | Terminal verdict record | `_persist_l3_verdict` `:619-659`, called `:1715` (meets) / `:1499,1525,1584,1597` (below) | `l3-verdict.txt` + byte-copy `l3-report.md`; timeline `config` event `l3-verdict {before} -> {verdict} (report from {source})` `:656-658` | `l3-verdict.txt` flips/refreshes to `below`; `l3-report.md` becomes a copy of the deciding source (or is left untouched when source is `None`, `:640`) | Freshness is **bidirectional** (`test_autopilot_verdict_freshness.py:396-412`): a later terminal meets overwrites a below, and vice-versa. `l3-verdict.txt` is a derived record, not append-only |
| 4 | Achieved draft | `:1716-1749` (write under `key-{key}` lock, ≥200B post-check at `:1742-1747`) | reviewer `## Achieved` (meets path only) | Draft from the below round is **not** transcribed; `mark_stalled` appends a 遗留问题 block instead (`:2288-2294`) | A meets round overwrites a <200B draft; overwriting a ≥200B draft requires the bad-draft marker (`closure.overwrite_authorized`, `:1730-1732`) |
| 5 | pm-state PASS line | `_append_pass_line` `:1623-1652`, called `:1749` | writes `- PASS: L3 quality gate meets — ...` | Not written | Written once (idempotent: existing `PASS` short-circuits, `:1637`) |
| 6 | Framework advance | `advance.advance(key,"done",...)` `:1752-1754`; streak via `_record_advance_result` | — | Never called for below | Advances key to done; `_mark_key_done` then flips roadmap key-status (see #7) |
| 7 | Roadmap key-status | `_mark_key_done` `:2090-2121` requires `_done_credentials_present` `:1376-1420`, which requires `l3-verdict.txt == "meets"` (`:1386-1395`) | `l3-verdict.txt` | If the key ever reaches phase `done`, roadmap flip is refused with a `config` timeline event (`:2095-2102`) | Enables `done` status → key terminal → dependency satisfaction (`_deps_satisfied` `:2013-2014`) and stage closure |
| 8 | Provenance sidecar | `_l3_provenance_record` `:1230-1317` + `_persist_l3_provenance` `:1320-1374`, called `:1513-1515` | append-only `l3-verdict-provenance.json`, dedup by `task_key` (`:1346-1349`); timeline `config` `l3-provenance ...` `:1364-1371` | A below round is recorded with `raw_verdict/verdict = "below"` (source not None); no FAIL cause is recorded | A meets round with `suspect=True` is fail-closed to below (`:1314-1316`) and re-reviewed rather than repaired (`:1516-1538`) |
| 9 | Timeline events | commit path | `l3-no-verdict` `:1495`; `l3-source-suspect` `:1521`; `l3-reprompt` `:1562`; `config` (l3-verdict / l3-provenance); `stalled` `:2321`; `gate-created` `_create_gate:2043`; `resume`/`gate-answered` `_apply_stalled_approvals:2190-2206`; `advance` `_record_advance_result:831/834` | Below at budget limit adds `stalled`; below under budget adds a repair `dispatch` event, no verdict reason | A false below adds extra `dispatch` events (repair rounds), then potentially `stalled` + human gate |
| 10 | Repair dispatch | `_repair_prompt(key, used, l3_source_rel)` `:1129-1137`, dispatched `:1605-1610` | `l3_source_rel` computed `:1483-1488` (falls back to `.../output.md` when source is None) | Repair worker is tasked with the FAIL/needs-rerun items; consumes one `repair:{key}` attempt | An unnecessary repair round burns worker tokens + an L3 round |
| 11 | Stall four artifacts | `mark_stalled` `:2249-2321` | roadmap key-status (`:2263-2276`), `stalled` gate `:2278-2283`, `achieved.md` 遗留问题 draft `:2286-2294`, `patterns/{key}/stall-lesson.md` `:2296-2317`, `stalled` event `:2321` | Key frozen (orchestrate skips terminal/stalled keys, `orchestrate:232-234`); dependents blocked (`_deps_satisfied`); stage cannot close (`_stage_closure:573-575` requires every key in `("done","closed-legacy")`) | A false below manufactures a human gate and freezes the key |
| 12 | Resume credits | `_resume_credits` `:2123-2143`; approval path `_apply_stalled_approvals` `:2145-2211` | the approved `stalled` gate count | Each approved stall gate grants +1 round on every capped loop (L2 boundary, EXECUTE retry, L3, repair — docstring `:2126-2136`) | A false below → stall → human approval → extra rounds on all loops (time tax) |
| 13 | Closure dossier / stage-close reader | `_closure_dossier_md` `:666-693` via `_l3_verdict` `:603-612`; written by `_stage_closure` `:560-601` to `.agenticdoc/_autopilot/stages/stage-{n}-close.md` (`:579-585`) | persisted `l3-verdict.txt` value (not the round verdict) | A below key is not terminal → no dossier/stage-close at all; if already-written dossier exists it is not rewritten (`:580-582`) | A meets→below flips the dossier `l3 verdict` cell to below (the exact D-002 failure class the freshness key fixed) |
| 14 | `l3_no-verdict` re-review loop | `:1489-1512` | worker status | Not applicable (separate verdict value) | n/a |

No consumer outside `conductor.py` reads `l3-verdict.txt` / `l3-report.md`: repo-wide `rg` for `l3-verdict` matches only `conductor.py` and the three verdict test files. The dossier markdown is human/PM-read; the machine-readable terminal signal is roadmap `key-status`.

### 3.2 Summary of the two error directions

- **False meets (the incident):** full done transaction runs — QG evidence artifact, `l3-verdict.txt=meets`, `l3-report.md`, `achieved.md`, pm-state PASS, advance to done, roadmap key-status done, key terminal, dependents unblocked, stage-close reachable, dossier records `meets`. Nothing in this chain is self-correcting; remediation needs a fresh L3 round or manual correction. This is why false-meets is the trust-base break (§0 of spec).
- **False below (the risk of over-broadening):** no done transaction. Under budget → extra `repair` dispatch (slot + tokens) then possibly extra L3 rounds. At budget → `mark_stalled` four artifacts + human `stalled` gate; key frozen, dependents blocked, stage closure blocked; a human approval grants `+1` credit on every capped loop. Worst case (unattended) is a work item stuck at `stalled` despite being fine.

---

## 4. Below-verdict record granularity today, and where a "first matched FAIL line" sample must thread

### 4.1 Current granularity: FAIL-caused below is NOT distinguished from missing-section below

- The two below causes converge before any recording:
  - FAIL hit: `_l3_resolve_source:1190` returns `("below", path)`; `_l3_round_verdict` returns with `source != None`; `_verify_loop:1513-1515` writes a provenance entry (raw verdict `below`), then `:1583`.
  - Missing section: `_l3_resolve_source:1193` returns `("below", None)`; `_l3_round_verdict` returns with `source = None`; `:1513` guard skips provenance, then `:1583`.
- At `:1583-1589` both write the same record shape:
  - `_persist_l3_verdict(key_dir, "below", l3_source, st=st)` → `l3-verdict.txt = "below"` (no reason), timeline detail `l3-verdict {before} -> below (report from {source})` where `source` is `"output.md"`/`"report.md"` for a FAIL hit and `"-"` for a missing section (`:652-655`). This is the only existing weak discriminator, and it is incidental, undocumented, and absent from the stall reason.
  - `mark_stalled(..., f"L3 below {l3_limit} rounds (budget {l3_budget}, credits {l3_limit - l3_budget})")` (`:1585-1588`) — cause-free. Repository-exhausted variant: `f"repair exhausted {repair_used} attempts at L3 round {used}"` (`:1600`). Suspect-source variant: `f"L3 判定源取证可疑（{round}）达 {used}/{l3_limit} 轮"` (`:1526-1529`).
- No FAIL line text, no match count, no per-round cause is persisted anywhere. The `l3-verdict-provenance.json` record (`:1230-1316`) has `raw_verdict`, `deciding_source`, `suspect`, `reasons` — the `reasons` list is only for provenance staleness (mtime/byte-equal), never the FAIL cause.

### 4.2 Threading path for a FAIL sample (design options)

Minimal threading (round-level, no new event type):

1. `_l3_resolve_source` (`conductor.py:1180-1193`) — the only place the FAIL scan happens. It must return the sample. Today it returns `(str, Path|None)`; adding a third element (e.g. `(verdict, source, fail_line|None)`) or a small dataclass requires updating `_l3_round_verdict:1224` and both test files that call it directly (`test_autopilot_verdict_source_fallback.py:354, 486, 596` use `_L3_FAIL_RE`/`_md_section` directly, not the resolver; the resolver is only called by `_l3_round_verdict`). Note `_L3_FAIL_RE.search` is not MULTILINE, so a line sample means iterating `qg.splitlines()` or switching to `finditer`+line mapping.
2. `_l3_round_verdict` (`conductor.py:1196-1225`) — return tuple grows from 3 to 4 elements. Call sites that must change:
   - production: `_verify_loop:1481` (1 site)
   - tests: 8 tuple-unpack sites in `test_autopilot_verdict_source_fallback.py` (`:241, 275, 310, 347, 385, 464, 580, 793`); 3 index-based sites (`:737, 753, 759` as `v1/v2/v3`) tolerate arity growth but should be checked.
3. `_verify_loop` (`conductor.py:1442`) — consumers of the sample:
   - `mark_stalled` reason at `:1585` (and optionally `:1526`, `:1598`) — add the sample via `_one_line` (`:713-717`) so the gate/stall text names the FAIL item.
   - `_persist_l3_verdict` (`:619`) — add an optional `reason`/`fail_line` parameter appended to the `l3-verdict` timeline detail (`:656-658`). This is where AC-005's "timeline reason can distinguish FAIL-below from missing-section-below" lands.
   - `_repair_prompt` (`:1129`) — add the sample so the repair worker gets the first FAIL line; the dispatch at `:1605-1610` passes it. (Prompt wording is currently also "任一份出现 FAIL 单元格即 below" at `:1123`, which will need updating if the detector broadens beyond cells.)
4. Provenance sidecar — the natural round-level carrier. `_l3_provenance_record` (`:1230`) already builds a per-round dict; adding e.g. `"fail_line"` / `"fail_source_line"` requires no new file and no new event type, and the append-only dedup at `:1344-1347` means an already-recorded round keeps its first record (fine: the round's verdict is immutable once recorded).
5. `_done_transaction` — no change (meets path only).

Files this would touch: `packages/multi-workers/autopilot/conductor.py` and the verdict test files (call-site arity + any count-locked assertions in §5.5). If the design instead avoids signature changes by re-scanning in `_verify_loop`, it duplicates the scan and the "deciding source vs. FAIL source" could diverge (e.g. meets-from-report while output.md has FAIL) — the current resolver semantics make such a divergence real (see §1.2 hole).

---

## 5. Test inventory (regression surfaces)

### 5.1 Commit a0c36fcc's tests — `packages/multi-workers/test_autopilot_verdict_source_fallback.py` (added whole in a0c36fcc, 945 lines)

15 tests; the ones that constrain the detector:

| Test (line) | FAIL-related assertion |
|---|---|
| `test_report_fail_not_whitewashed_by_output_pass` (`:297`) | report.md qualifying with `_REPORT_BELOW` (`_L3_BELOW`, plain `| VC-002 \| FAIL \|`) → `below` even though output.md is `_OUTPUT_MEETS` (`:310-320`) |
| `test_bold_fail_detected_and_frozen_primitive_differs` (`:336`) | `_OUTPUT_BOLD_FAIL` (`| VC-002 \| **FAIL** \|`) → `_l3_round_verdict` `below`, `_parse_l3_output` `meets`, `_L3_FAIL_RE` hit, old literal miss (`:347-360`) |
| `test_change_classes_fixture_reproduce_4_plus_3` (`:421`) | 17 synthetic rounds: exactly 4 below→meets, 3 meets→below (bold FAIL), 10 unchanged; `false_meets == 0` (`:490-500`) |
| `test_frozen_region_sha_and_criteria_passed` (`:509`) | 4 parse rules (missing QG / missing Achieved / `| VC-1 \| FAIL \|` in QG / `_L3_MEETS`) + region SHAs + freshness-file SHA + runs `test_autopilot_verdict_freshness.py::test_l3_criteria_behavior_unchanged` as a subprocess (`:536-556`) |
| `test_config_snapshot_and_fail_regex_superset` (`:568`) | strict-superset probe over 7 QG-section samples; asserts `old_only == 0` and **`new_only == 4`** and `superset` (`:586-604`) |
| `test_repair_prompt_references_deciding_source` (`:686`) | `_repair_prompt` line cites `report.md` vs `output.md` per deciding source (`:706-719`) |
| `test_reviewer_prompt_documents_fallback` (`:856`) | prompt contains `FAIL` + `below` (`:881`) |
| `test_done_transaction_takes_deciding_source` (`:617`) | done transaction consumes the deciding source (`:628-676`) |
| remaining | `:229, :262, :372, :774, :809, :894` — fallback/priority/no-fabrication/slug/zero-write/coverage audit |

FAIL test literals (case-sensitive): `:8`, `:13-14`, `:20`, `:77`, `:109-110`, `:112`, `:334`, `:343`, `:354-355`, `:427`, `:441`, `:486`, `:525`, `:529`, `:586-592`, `:594`, `:596`, `:881`, `:902`.

### 5.2 Region/file SHA locks (hard blockers for touching frozen primitives)

- `test_autopilot_verdict_source_fallback.py:69-71`:
  - `_PARSE_L3_SHA = "b0348c4f...c98"` → asserts `_conductor_region_sha("def _parse_l3_output(")` (`:536-542`)
  - `_MD_SECTION_SHA = "c0926b8d...d2b"` → asserts `_conductor_region_sha("def _md_section(")` (`:537-542`)
  - `_FRESHNESS_FILE_SHA = "1aed6ba0...f7c6"` → asserts the **entire** `test_autopilot_verdict_freshness.py` file hash (`:543`)
- `test_autopilot_verdict_freshness.py:45-46` repeats `_PARSE_L3_SHA` / `_MD_SECTION_SHA` and asserts them in `test_l3_criteria_behavior_unchanged` (`:634-640`).
- `test_autopilot_verdict_source_fallback.py:192-212` implements `_func_source`/`_conductor_region_sha`; the region runs from the `def` line to the next `def `/`class `/`# ──` line.

Consequence: changing `_md_section` or `_parse_l3_output` requires updating 3 constants across 2 files, and changing `test_autopilot_verdict_freshness.py` additionally requires updating `_FRESHNESS_FILE_SHA` in `test_autopilot_verdict_source_fallback.py`. `_L3_FAIL_RE` and `_l3_resolve_source` are **not** hash-locked.

### 5.3 Full case-sensitive `FAIL` literal inventory in `packages/multi-workers/test_*.py`

Detector-relevant (uppercase `FAIL` inside L3 report/QG fixture text or regex probes):

| file:line | literal / role |
|---|---|
| `test_autopilot_conductor_exec.py:151` | `_L3_BELOW`: `"| VC-002 | FAIL | (missing) |"` (plain pipe, in `## Quality Gate Report`) |
| `test_autopilot_conductor_exec.py:751` | `_dcr_l3_report(..., fail=True)`: same plain pipe row (mw-done-closure-repair fixture) |
| `test_autopilot_readcap_injection.py:861` | `qg_fail = "## Quality Gate Report\n| VC | Verdict |\n| VC-001 | FAIL |\n"` |
| `test_autopilot_verdict_freshness.py:162` | mirror parser: `re.search(r"\|\s*FAIL\b", qg)` |
| `test_autopilot_verdict_freshness.py:627` | criteria fixture `| VC-1 | FAIL |` |
| `test_autopilot_verdict_source_fallback.py:8,109-110,334,354-355,427,441,525,529,586-592,594,596` | bold/plain pipe variants, superset probe samples, regex probes |
| `test_autopilot_verdict_source_fallback.py:881` | `fail_to_below_kept = "FAIL" in prompt and "below" in prompt` |

Not detector-relevant (unrelated vocabulary): `test_autopilot_closure.py:49,112,120,162,178,217,222,256,280,307,326,336,347,374` (`EXPECTED_FAILURE_LINES`, done-gate `failure_lines`), `test_autopilot_e2e.py:1084` and `test_autopilot_l0.py:347` (test-runner `print("FAIL ...")`), `FAIL_CLOSED_CASES` names.

Case-insensitive `fail` adds only generic words (`failed` queue status, `failure_lines`, `fail-closed`) — no other L3 QG text forms.

### 5.4 Reviewer stubs / fixtures a broadened detector could change

- **e2e stub reviewer** (`test_autopilot_e2e.py`): stub source starts at `_STUB_WORKER = r'''` (`:174`), `output = task_dir / "output.md"` (`:200`), reviewer branch `elif task_type == "reviewer":` (`:272`). Both branches write a QG table with only `| VC-901 | PASS | output.md |` and `| VC-902 | PASS | trace.log |` (`:279-292` reprompt branch after `if "Rejected lines" in body:` `:273`, and `:293-305` normal branch). **No FAIL form exists in the e2e chain today**, so AC-006's bold-FAIL reviewer round must be added here.
- **L2/exec harness** (`test_autopilot_conductor_exec.py`, imported by `test_autopilot_stall.py:16` and `test_autopilot_verdict_source_fallback.py:4` as `harness`):
  - `_L3_MEETS` (`:130-142`) and `_L3_BELOW` (`:145-155`) — shared by stall/freshness/fallback tests (`test_autopilot_stall.py:29-30`, `test_autopilot_verdict_source_fallback.py:90-91`, `test_autopilot_verdict_freshness.py:82`).
  - `_dcr_l3_report(achieved, *, fail=False)` (`:748-762`) — the done-closure-repair fixture (d20a270d5).
  - `_verify_key_project` (`:388`), `_worker_output` (`:102`), `_set_row` (`:91`), `_rows` (`:84`), `_state` (`:75`) are the fixture verbs used by all verdict tests.
  - L3 verdict assertions that would observe a flip: `:444` (`l3-verdict.txt == meets`), `:528` (`== below`), `:1069` (`== meets`).
- **`test_autopilot_stall.py`**: L3 no-verdict tests `test_l3_worker_failure_is_no_verdict` (`:396`), `test_l3_failed_worker_with_placeholder_output_is_still_no_verdict` (`:420`), plus below-driven stall tests using `_L3_BELOW` (`:320, 354, 360`).
- **`test_autopilot_conductor_stage.py:296`** constructs `conductor.mark_stalled(project, st, "k1", "L3 below twice")` directly (reason string is arbitrary there, so a reason-format change is low-risk but the dossier assertion at `:299-306` reads the persisted verdict).

### 5.5 Which existing assertions a broadened detector / a FAIL-sample field would break

1. `test_config_snapshot_and_fail_regex_superset` (`test_autopilot_verdict_source_fallback.py:568-612`): asserts `new_only == 4`. Any new regex that also matches the `| VC-1 | FAILED |` sample (index 6) or adds forms changes this count. Must be redesigned alongside AC-001/AC-002.
2. `test_frozen_region_sha_and_criteria_passed` (`:509-563`) and `test_l3_criteria_behavior_unchanged` (`test_autopilot_verdict_freshness.py:604-641`): region SHA + file SHA locks — any edit to `_md_section`/`_parse_l3_output` or to the freshness test file breaks these.
3. `test_change_classes_fixture_reproduce_4_plus_3` (`:421-504`): exact class counts 4/3/10.
4. Tuple arity at `_l3_round_verdict` call sites (`:241, 275, 310, 347, 385, 464, 580, 793`) if a FAIL-sample element is added.
5. `test_bold_fail_detected_and_frozen_primitive_differs` (`:336-368`) asserts the frozen `_parse_l3_output` still returns `meets` for bold FAIL — unchanged if the design leaves frozen primitives alone.
6. `test_autopilot_timeline.py:48` locks `len(tl.EVENT_TYPES) == 17`; §5 of the spec's "no new event type" constraint is enforced there, so a FAIL-sample reason must ride an existing event (`config` / `stalled`).

---

## 6. Git anchors

`git log --oneline -8 -- packages/multi-workers/autopilot/conductor.py`:

```
d20a270d5 fix: done-gate closure repair loop for autopilot conductor (mw-done-closure-repair)
a0c36fcce fix(autopilot): read the L3 round verdict from the documented fallback chain (output.md -> report.md) with fail-closed FAIL scan [feature-l3-verdict-source-fallback]
1b2a1efde fix(autopilot): refresh the terminal l3 verdict record on every terminal event [feature-l3-verdict-freshness]
3a9c40d52 fix(autopilot): TASKS->EXECUTE plan-task gap accepts the plan id->file prefix strip
4e874f5cc fix(autopilot): consume approved stalled gates exactly once
0c7754086 feat(multi-workers,coding-agent): bound autopilot retries, resume stalled gates, surface stalls in the monitor panel
5e8ecf39d fix(multi-workers): conductor L3 budget from config + l3 verdict persistence
4c7c07c43 feat(multi-workers): autopilot conductor core with stage machine and done transaction
```

Commit roles, verified with `git blame` / `git log -S` / `git show`:

- `4c7c07c43` (2026-09-10): introduced the frozen primitives `_md_section` (`conductor.py:1076-1088`) and `_parse_l3_output` with the literal `re.search(r"\|\s*FAIL\b", qg)` (`:1108`), plus the fixture stubs `_L3_MEETS`/`_L3_BELOW` (`test_autopilot_conductor_exec.py:130-155`, blame `4c7c07c431`).
- `1b2a1efde` (2026-09-25): freshness — rewrote `_persist_l3_verdict` (`:619-659`); its conductor.py diff contains **no** `FAIL` token (verified by `git show 1b2a1efde | rg -i FAIL` → empty). Added `test_autopilot_verdict_freshness.py`.
- `a0c36fcce` (2026-09-25): introduced `_L3_SOURCE_ORDER` (`:1145`) and `_L3_FAIL_RE = re.compile(r"\|\s*\**\s*FAIL\b")` (`:1148`), the resolver chain `_l3_source_paths/_l3_read_source/_l3_qualifies/_l3_resolve_source` (`:1157-1193`), and `_l3_round_verdict` (`:1196`); added `test_autopilot_verdict_source_fallback.py` (945 lines) and the CHANGELOG entry. `git blame -L 1144,1149` attributes every one of those lines to `a0c36fcced`. **This is the commit whose regex the design broadens.**
- `d20a270d5` (2026-09-25): closure repair — touched `_verify_loop` (`:1539-1581` reprompt branch) and `_done_transaction` (`:1670-1813` returns `(verdict, err)`); its conductor.py diff has no `_L3_FAIL_RE`/`_L3_SOURCE_ORDER` lines (verified by `git show d20a270d5 -- .../conductor.py | rg -i FAIL`). Added the `_dcr_l3_report(..., fail=True)` fixture (`test_autopilot_conductor_exec.py:748-751`) and the e2e reprompt stub branch (`test_autopilot_e2e.py:273-292`). It does **not** change the FAIL regex.

Base for this design: HEAD `d20a270d5`; the marker detector to change is `_L3_FAIL_RE` (a0c36fcce), the resolver to extend is `_l3_resolve_source` (a0c36fcce); `_parse_l3_output`/`_md_section` (4c7c07c4) stay frozen unless explicitly unlocked.

---

## 7. Confidence notes

- Read in full: `packages/multi-workers/autopilot/conductor.py` (all 2468 lines), `test_autopilot_verdict_source_fallback.py` (945 lines), and the cited ranges of the other test files, `timeline.py`. All line numbers were re-confirmed with `python enumerate` on the working tree, not from grep snippets alone (the console garbles CJK output but line content was cross-checked with the `read` tool).
- Verified by execution of read-only commands: `rg` call-site enumeration, `git blame`, `git log -S`, `git show --stat`/diffs. No test suite was run (read-only research task); AC-003's "927 passed + 2 pre-existing" baseline is a CHANGELOG/spec claim, **not re-measured here**.
- E2Feature real-corpus claims (17 rounds, 7 changed, the two victim forms) come from `spec.md` §1 and the `a0c36fcce`/`d20a270d5` CHANGELOG entries; I did not read the E2 project tree (out of scope, and it is a separate partition).
- `_l3_resolve_source` return-arity change impacts: I enumerated test call sites by `rg` over the repo; if the design keeps the 2-tuple and puts the sample elsewhere (e.g. a module-level return object), only `_verify_loop` changes. The 8 unpack sites in `test_autopilot_verdict_source_fallback.py` are the concrete breakage list.
- Not verified: whether any external consumer (outside this repo) parses `stalled` timeline details or the close dossier; within this repo no code reader branches on them.
