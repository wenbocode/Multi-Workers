"""Build MDC's quality-gate prerequisites (re-runnable; run again after late workers land):

  1. .agenticdoc/mw-dynamic-concurrency/evidence-requirement.md
     (header table incl. the mechanical ac_fingerprint + one section per AC)
  2. evidence/baseline/  -- frozen PASS baselines
  3. evidence/runs/      -- [VERIFY]/[FLOW] entries extracted from each worker's output.md

Fingerprint method (verbatim from workflow-quality-gate.md):
  sha1( sort -u( grep -oE 'AC-[0-9]{3}' spec.md ) ) [:12]
i.e. the sorted unique AC ids, one per line, trailing newline each.
"""

import hashlib
import pathlib
import re

REPO = pathlib.Path(r"H:\git\Multi-Workers")
KEY = "mw-dynamic-concurrency"
DOC = REPO / ".agenticdoc" / KEY
EVID = DOC / "evidence"
BASELINE = EVID / "baseline"
RUNS = EVID / "runs"

spec_text = (DOC / "spec.md").read_text(encoding="utf-8")
ac_ids = sorted(set(re.findall(r"AC-\d{3}", spec_text)))
payload = "".join(f"{ac}\n" for ac in ac_ids).encode()
fingerprint = hashlib.sha1(payload).hexdigest()[:12]

vc_ids = sorted({m for m in re.findall(r"VC-\d{3}", (DOC / "design.md").read_text(encoding="utf-8"))})

# AC -> (title, VC mapping, evidence carriers, sufficiency criterion)
ED = "evidence"
PM = ".agenticdoc/_scratch/evidence"
AC_ROWS = [
    ("AC-001", "key 层前沿恒等（实起 = min(配置上界, |前沿|)）", "VC-101, VC-102",
     f"{ED}/M-02-conductor-frontier.md §3 B；{PM}/mdc-m02-probe-a-inplace-out-20261014.txt（PM 亲跑）",
     "≥3 组构造语料复算，键层实起数与 `min(cap,|F|)` 恒等；原始输出可复算"),
    ("AC-002", "per-key 实起 = min(per-key 上界, |任务前沿|)，且无写面重叠", "VC-101, VC-102, VC-105",
     f"{ED}/M-02-conductor-frontier.md §3 A/A2、§4 C2/C3；VC-105 归 {ED}/M-06-e2e.md（待）",
     "per-key 实起恒等 + 写面重叠对 = 0（N≥4 端到端反证在 M-06）"),
    ("AC-003", "依赖/写面缺失或不可解析 ⇒ 该层串行 + 审计行，不默认放大", "VC-104",
     f"{ED}/M-02-conductor-frontier.md §4 C/C2/C3、§5 D；{ED}/M-05-tests-python.md（待）",
     "四类 fail-closed（悬空/环/未声明/重叠）各实测实起 = 1 且有 timeline 事件；去重可证"),
    ("AC-004", "配置语义（key 层上界 + 新 per-key 键，两侧镜像）", "VC-108",
     f"{ED}/M-03-config-panel.md；{ED}/M-05-tests-ts.md",
     "默认 8/4、范围 (1,None)/[1,null] 两侧逐字段相等；materialized config 仍合法"),
    ("AC-005", "monitor 同显配置上界与本 tick effective 并发，同快照可复算", "VC-107",
     f"{ED}/M-03-config-panel.md；{ED}/M-05-tests-ts.md",
     "同一快照复算 cap / eff=min(cap,|F|) / |F| 三量一致，渲染行可读"),
    ("AC-006", "上界=1 ⇒ 两层串行，无需重启 serve", "VC-103",
     f"{ED}/M-02-conductor-frontier.md §7 E；{ED}/M-05-tests-python.md（待）",
     "同进程改配置即生效，两层实起 ≤1"),
    ("AC-007", "两语言配置镜像逐字段一致（parity 语料）", "VC-108",
     f"{ED}/M-03-config-panel.md（TS 44 passed）；{ED}/M-05-tests-ts.md",
     "冻结语料具名 case 判决一致且非空洞（含反例）"),
    ("AC-008", "任务级 `deps:` 载体 + 新增独立解析器（不得复用 `card_audit._header_value`）", "**无 VC（映射缺口，见下）**",
     "packages/multi-workers/test_task_graph.py（M-01，71 passed）；spec 实测 5/5 空串证据；M-02 `_read_task_cards`",
     "解析器对真实卡抽样复现；H1 首行 + 卡头区域规则；5/5 旧解析器空串已实测"),
    ("AC-009", "任务级依赖图校验（悬空/自依赖/环/跨 key）⇒ 整 key 串行 + timeline；数字核心 join", "VC-104",
     "packages/multi-workers/test_task_graph.py（V1-V7）；" + f"{ED}/M-02-conductor-frontier.md §4 C",
     "每类 V-problem 各有用例；117/125 数字核心命中可复算；整 key 串行不永锁"),
    ("AC-010", "key 层 roadmap 语义校验在 tick 内执行（只观察，不改 fail-closed）", "**无 VC（映射缺口，见下）**",
     f"{ED}/M-02-conductor-frontier.md §5 D（原始事件 + 去重）",
     "校验事件在 tick 内产生且同 problem 只写一次；代码只观察、不抑制/不授权派发"),
    ("AC-011", "派发判定与队列写入同临界区；同一 `task_key` 不可被两进程各 append", "VC-106",
     f"{ED}/M-04-dispatch-dedup.md（待）；VC-106 归 {ED}/M-06-e2e.md（待）",
     "判据 = `ok=True` 次数 == 1 且 timeline `dispatch` 事件数 == 1（不是行数）；双入口对拍 5 连跑"),
    ("AC-012", "在飞口径单源（`_is_in_flight`/`_row_belongs_to` 一处导出，服务全部消费点）", "VC-107",
     f"{ED}/M-02-conductor-frontier.md（代码面审计：谓词未动）；PM 复核 {PM}/mdc-m02-code-audit-20261014.txt；{ED}/M-05-tests-ts.md",
     "谓词与面板逐点同形（TS `workerBelongsToKey` vs Python `row_belongs_to`）；无静默滞后消费点"),
    ("AC-013", "`advance.advance()` 不得成为并发瓶颈，或给实测量化", "VC-109",
     f"{ED}/M-02-conductor-frontier.md §6 + PM 复现；VC-109 归 {ED}/M-06-e2e.md（待）",
     "`data.ms` 打点落地且不新增事件名；window_share 有原始采样（PM 复现 0.9914 / 81x）"),
]

lines = [
    f"# Evidence Requirement: {KEY}",
    "",
    "## 基础信息",
    "",
    "| 字段 | 值 |",
    "|------|-----|",
    f"| spec_path | `.agenticdoc/{KEY}/spec.md` |",
    f"| spec_locked_at | 2026-10-14 |",
    f"| ac_fingerprint | `{fingerprint}` |",
    f"| ac_ids | {', '.join(ac_ids)} |",
    f"| vc_ids | {', '.join(vc_ids)} |",
    f"| generated_at | 2026-10-14 |",
    "",
    f"`ac_fingerprint` 复算方法（与 `workflow-quality-gate.md` 的校验脚本逐字一致）：",
    f"`sha1( sort -u( grep -oE 'AC-[0-9]{{3}}' spec.md ) )[:12]` —— 即上述 AC id 排序去重、每行一个、行尾换行，"
    f"取 sha1 前 12 位。当前 payload 为 {len(ac_ids)} 行，复算值 `{fingerprint}`。",
    "",
    "## 映射缺口声明（诚实记录，不假装 100%）",
    "",
    "| AC | 情况 | 处置 |",
    "|----|------|------|",
    "| AC-008 | design.md 未给对应 VC | 证据载体上移到测试层：`test_task_graph.py`（M-01，71 passed）+ spec 的 5/5 旧解析器空串实测 |",
    "| AC-010 | design.md 未给对应 VC | 证据载体为 M-02 §5 D 的 tick 内事件原始输出 + 只观察实现的代码审计 |",
    "",
    "## 汇总：每个 AC 的充分性判定标准",
    "",
    "| AC | 内容 | VC | 证据载体 | 充分性判定 |",
    "|----|------|----|---------|-----------|",
]
for ac, title, vc, carrier, criterion in AC_ROWS:
    lines.append(f"| {ac} | {title} | {vc} | {carrier} | {criterion} |")
lines.append("")

for ac, title, vc, carrier, criterion in AC_ROWS:
    lines += [
        f"## {ac}: {title}",
        "",
        "| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |",
        "|---------|---------|----------|----------|",
        f"| [VERIFY]/[FLOW] | {carrier} | 见上行判定标准 | 满足 PASS 需现场复算一致 |",
        f"| VC 映射 | {vc} | — | — |",
        "",
    ]

lines += [
    "## 质检门禁使用说明",
    "",
    "`/quality-gate` 读取本文件取得每个 AC/VC 的充分性判定标准；`evidence/baseline/` 存冻结基线，",
    "`evidence/runs/` 存各 worker `output.md` 的 `[VERIFY]`/`[FLOW]` 条目（由",
    "`.agenticdoc/_scratch/evidence/mdc-build-evidence-artifacts-20261014.py` 机械抽取，可重跑）。",
    "",
]
(DOC / "evidence-requirement.md").write_text("\n".join(lines), encoding="utf-8")
print(f"evidence-requirement.md: {len(lines)} lines, ac_fingerprint={fingerprint}, ac_ids={len(ac_ids)}, vc_ids={len(vc_ids)}")

# ---- baseline/ ----
BASELINE.mkdir(parents=True, exist_ok=True)
full = {p.name for p in BASELINE.iterdir()} if BASELINE.is_dir() else set()
(BASELINE / "full-pytest-baseline-20261014.txt").write_text(
    "MDC baseline: full Python suite before/at MDC B2\n"
    "command: cd packages/multi-workers; python -m pytest -q\n"
    "PM own run 2026-10-14: 6 failed, 2206 passed, 10 deselected in 317.41s\n"
    "the 6 pre-existing reds and their independent attribution:\n"
    "  1. test_autopilot_readcap_injection.py::test_baseline_left_end_bound\n"
    "     -> compares the frozen copy with `git show HEAD:...dispatch.py`; BASELINE_DIR defaults to\n"
    "        ANOTHER repo (H:\\git\\E2Feature\\...\\baseline_20260924, frozen 2026-09-24) => structural.\n"
    "  2. test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below\n"
    "     -> PROVED pre-existing by PM A/B isolation: same failure with HEAD conductor.py in a temp copy.\n"
    "  3-4. test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites\n"
    "       test_task_type_parity.py::test_bom_historical_books\n"
    "     -> another key's task book is missing (mw-dispatch-reliability/workers/mw-dr-glm53/task.md).\n"
    "  5-6. test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge\n"
    "       test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge\n"
    "     -> the TS subprocess runner returns None (proc is None) => dist/** not rebuilt.\n"
    "IMPORTANT: MDC's own acceptance requires zero NEW failures against this list.\n",
    encoding="utf-8",
)
(BASELINE / "ts-suites-baseline-20261014.txt").write_text(
    "MDC baseline: TS suites at MDC B0..B3\n"
    "node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts \\\n"
    "  test/suite/autopilot-config-sync.test.ts test/suite/autopilot-console.test.ts  -> 44 passed (PM own run)\n"
    "node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts  -> 26 passed (PM own run)\n"
    "node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-concurrency-panel.test.ts -> 4 passed (PM own run)\n"
    "node ... --run <new + parity + sync + monitor> -> 36 passed (PM own run)\n"
    "npx tsgo --noEmit -> exit 0 (PM own run)\n",
    encoding="utf-8",
)
(BASELINE / "corpus-baseline-20261014.txt").write_text(
    "MDC baseline: frozen parity corpus (M-03 re-freeze)\n"
    "path: packages/multi-workers/test/fixtures/autopilot-config-corpus.json\n"
    "before M-03: 73 cases; after: 77 cases, 19388 bytes on disk,\n"
    "sha256 (LF-normalized) = f5b60e81cd690930cc9afb4ef1ccdee6bd8d517e6d40521a3f1b84e65a13e9c1  (PM recomputed)\n"
    "key rows: range-max-parallel-low reject -> accept; range-max-parallel-min accept;\n"
    "          partial-key-max_workers_per_key accept; range-max-parallel-below-floor reject (non-vacuous control)\n"
    "NOTE: whole-file sha is deliberately NOT asserted by the M-05 TS test (a re-freeze must not make it brittle).\n",
    encoding="utf-8",
)
print("baseline/: " + ", ".join(sorted(p.name for p in BASELINE.iterdir())))

# ---- runs/ ----
RUNS.mkdir(parents=True, exist_ok=True)
KEYS = ["mdc-i01-task-graph", "mdc-m02-conductor-frontier", "mdc-m03-config-panel",
        "mdc-m04-dispatch-dedup", "mdc-m05-tests-python", "mdc-m05-tests-ts",
        "mdc-m06-e2e-concurrency"]
found = []
for task in KEYS:
    src = DOC / "workers" / task / "output.md"
    if not src.is_file():
        continue
    text = src.read_text(encoding="utf-8", errors="replace")
    kept = [ln.rstrip() for ln in text.splitlines()
            if "[VERIFY]" in ln or "[FLOW]" in ln or re.match(r"\s*\[(VERIFY|FLOW)\]", ln)]
    dest = RUNS / f"run-{task}.txt"
    dest.write_text(f"source: .agenticdoc/{KEY}/workers/{task}/output.md\n"
                    f"extracted: {len(kept)} [VERIFY]/[FLOW] lines\n\n" + "\n".join(kept) + "\n",
                    encoding="utf-8")
    found.append(f"{task}({len(kept)})")
print("runs/: " + ", ".join(found))
