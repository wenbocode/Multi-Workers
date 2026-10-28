import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mw_common  # noqa: E402
from autopilot import config, conductor, timeline  # noqa: E402


def _project(tmp):
    (tmp / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (tmp / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp, cfg)


def _roadmap(p):
    (p / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n## Stage 1: work\n"
        "> goal: deliver\n> status: running\n> key-status: k1=running\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n| k1 | worker | - |\n",
        encoding="utf-8",
    )
    (p / ".agenticdoc" / "_index.parallel").write_text(
        "| k1 | active | EXECUTE | — | - | d | 2026-09-10T00:00:00 |\n", encoding="utf-8"
    )


def _card(p, stem, faces=None):
    d = p / ".agenticdoc" / "k1" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}", ""]
    if faces:
        lines += ["## 写入允许面", ""] + [f"- `{f}`" for f in faces] + [""]
    lines += ["## 上下文", "", "x", "", "## 要求", "", "y", "", "## 交付格式", "", "z", ""]
    (d / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def run(label, cards):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="m02mix_")) / "proj"
    _project(tmp)
    _roadmap(tmp)
    for stem, faces in cards:
        _card(tmp, stem, faces)
    cfg = config.load_config(tmp)
    cfg["max_workers_per_key"] = 4
    config.save_config(tmp, cfg)
    conductor.advance.advance = lambda key, phase, root, summary=None: (0, "", "")
    st = conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(tmp)), conductor.goal_mtime_ns(tmp)
    )
    conductor.tick(tmp, st)
    rows = [
        r["task_key"] for r in mw_common.parse_workers_file(mw_common.workers_path(tmp))
        if r["task_key"].startswith("ap-k1-")
    ]
    events = [
        e["detail"] for e in timeline.query_events(timeline.timeline_path(tmp)).events
        if e["ev"].startswith("write-face")
    ]
    print(f"{label}: started={len(rows)} rows={rows}")
    for e in events:
        print("    ", e)


run("all declared disjoint (T1 src/a, T2 src/b, T3 src/c)",
    [("T-1", ["src/a/**"]), ("T-2", ["src/b/**"]), ("T-3", ["src/c/**"])])
run("all undeclared",
    [("T-1", None), ("T-2", None), ("T-3", None)])
run("mixed: T1 undeclared first, T2 declared",
    [("T-1", None), ("T-2", ["src/b/**"])])
run("mixed: T1 declared first, T2 undeclared",
    [("T-1", ["src/a/**"]), ("T-2", None)])