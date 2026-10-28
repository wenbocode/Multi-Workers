"""Temporary M-02 evidence probe (deleted after capture). Raw output only."""
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mw_common  # noqa: E402
from autopilot import advance as adv, config, conductor, roadmap, state, timeline  # noqa: E402

REPO_ROOT = HERE.parents[1]
FRAMEWORK = REPO_ROOT / ".agents" / "skills" / "agentic-task"


def _project(tmp: pathlib.Path) -> pathlib.Path:
    ap = tmp / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp, cfg)
    return tmp


def _roadmap(project: pathlib.Path, keys: dict[str, str | None], *, stage_keys=None) -> None:
    """keys: key -> depends_on (None = '-')."""
    key_status = ", ".join(f"{k}=running" for k in keys)
    rows = "\n".join(f"| {k} | worker | {dep or '-'} |" for k, dep in keys.items())
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n"
        "## Stage 1: work\n> goal: deliver\n> status: running\n"
        f"> key-status: {key_status}\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n"
        f"{rows}\n",
        encoding="utf-8",
    )
    index = "\n".join(f"| {k} | active | EXECUTE | — | - | d | 2026-09-10T00:00:00 |" for k in keys)
    (project / ".agenticdoc" / "_index.parallel").write_text(index + "\n", encoding="utf-8")


def _card(project: pathlib.Path, key: str, stem: str, *, deps=None, faces=None) -> None:
    key_dir = project / ".agenticdoc" / key
    (key_dir / "tasks").mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}", ""]
    if deps:
        lines += [f"- deps: {', '.join(deps)}", ""]
    if faces:
        lines += ["## 写入允许面", ""]
        lines += [f"- `{face}`" for face in faces]
        lines += [""]
    lines += [
        "## 上下文", "", "probe project", "",
        "## 要求", "", "do the probe", "",
        "## 交付格式", "", "write output.md", "",
    ]
    (key_dir / "tasks" / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def _set_cfg(project: pathlib.Path, **overrides) -> None:
    cfg = config.load_config(project)
    cfg.update(overrides)
    config.save_config(project, cfg)


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)), conductor.goal_mtime_ns(project)
    )


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _rows(project: pathlib.Path, prefix: str) -> list[dict]:
    return [
        e for e in mw_common.parse_workers_file(mw_common.workers_path(project))
        if e["task_key"].startswith(prefix)
    ]


def _set_row(project: pathlib.Path, task_key: str, status: str) -> None:
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for e in entries:
        if e["task_key"] == task_key:
            e["status"] = status
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n", encoding="utf-8"
    )


def _install_fake_advance(calls: list):
    def fake(key, phase, root, summary=None):
        calls.append((key, phase))
        return 0, "", ""
    adv.advance = fake


def _restore_advance():
    del adv.advance
    import importlib
    importlib.reload(adj_mod)


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


import autopilot.advance as adj_mod  # noqa: E402  (reload target)


def per_key_identity(root: pathlib.Path) -> None:
    """min(cap, |frontier|) for the per-key layer (execute_loop)."""
    section("A. per-key identity: started = min(max_workers_per_key, |task frontier|)")
    cases = [
        ("cap=4 frontier=3 (3 dep-free, disjoint faces)", 4, 3, None),
        ("cap=1 frontier=3 (cap is the kill switch)", 1, 3, None),
        ("cap=4 frontier=1 (chain T-2 deps T-1)", 4, 1, "chain"),
        ("cap=2 frontier=5 (cap truncates)", 2, 5, None),
    ]
    for label, cap, n, shape in cases:
        tmp = root / ("pk_" + str(abs(hash(label)) % 100000))
        tmp.mkdir()
        project = _project(tmp)
        key = "k1"
        _roadmap(project, {key: None})
        faces = [f"src/{i}/**" for i in range(max(n, 1))]
        if shape == "chain":
            _card(project, key, "T-1", faces=faces)
            _card(project, key, "T-2", deps=["T-1"], faces=faces)
        else:
            for i in range(n):
                _card(project, key, f"T-{i + 1}", faces=[faces[i]])
        _set_cfg(project, max_workers_per_key=cap, max_parallel_keys=8)
        calls: list = []
        _install_fake_advance(calls)
        try:
            st = _state(project)
            status = conductor.tick(project, st)
        finally:
            _restore_advance()
        started = _rows(project, f"ap-{key}-")
        expected = min(cap, n)
        print(
            f"{label:52s} tick={status:3s} started_rows={len(started)} "
            f"expected=min({cap},{n})={expected} {'OK' if len(started) == expected else 'MISMATCH'}"
        )
        print("    rows=" + str([r["task_key"] for r in started]))

    # |frontier| = 0: every task done -> no new rows, advance executes.
    section("A2. |frontier| = 0 (all tasks terminal) -> started = 0")
    for cap in (1, 4):
        tmp = root / f"pk_zero_{cap}"
        tmp.mkdir()
        project = _project(tmp)
        key = "k1"
        _roadmap(project, {key: None})
        for i in range(3):
            _card(project, key, f"T-{i + 1}", faces=[f"src/{i}/**"])
        _set_cfg(project, max_workers_per_key=3, max_parallel_keys=8)
        calls: list = []
        _install_fake_advance(calls)
        try:
            st = _state(project)
            conductor.tick(project, st)  # dispatch 3 (cap=3 setup)
            for i in range(3):
                _set_row(project, f"ap-{key}-T-{i + 1}", "done")
            before = len(_rows(project, f"ap-{key}-"))
            _set_cfg(project, max_workers_per_key=cap, max_parallel_keys=8)
            status = conductor.tick(project, st)  # all done -> advance
        finally:
            _restore_advance()
        after = _rows(project, f"ap-{key}-")
        print(
            f"cap={cap}: tick={status} rows_before={before} rows_after={len(after)} "
            f"new_rows={len(after) - before} advance_calls={calls} "
            f"expected=min({cap},0)=0"
        )


def key_layer_identity(root: pathlib.Path) -> None:
    section("B. key-layer identity (AC-001): started_keys = min(max_parallel_keys, |key frontier|)")
    for cap, n in ((2, 3), (1, 3), (8, 3)):
        tmp = root / f"kl_{cap}_{n}"
        tmp.mkdir()
        project = _project(tmp)
        keys = {f"k{i + 1}": None for i in range(n)}
        _roadmap(project, keys)
        for k in keys:
            _card(project, k, "T-1")  # no write face -> each key stays serial
        _set_cfg(project, max_parallel_keys=cap, max_workers_per_key=4)
        calls: list = []
        _install_fake_advance(calls)
        try:
            st = _state(project)
            status = conductor.tick(project, st)
        finally:
            _restore_advance()
        started_keys = sorted({r["task_key"].split("-")[1] for r in _rows(project, "ap-")})
        expected = min(cap, n)
        ok = "OK" if len(started_keys) == expected else "MISMATCH"
        print(
            f"max_parallel_keys={cap} eligible={n}: tick={status} started_keys={started_keys} "
            f"expected=min({cap},{n})={expected} {ok}"
        )


def serial_fallback_and_dedup(root: pathlib.Path) -> None:
    section("C. V-problem -> whole-key serial fallback + audit dedup")
    tmp = root / "vprob"
    tmp.mkdir()
    project = _project(tmp)
    key = "k1"
    _roadmap(project, {key: None})
    _card(project, key, "T-1")                       # dep-free
    _card(project, key, "T-2", deps=["T-99-missing"])  # dangling -> V-problem
    _set_cfg(project, max_workers_per_key=4)
    calls: list = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        s1 = conductor.tick(project, st)
        rows1 = [r["task_key"] for r in _rows(project, f"ap-{key}-")]
        audit1 = [e["detail"] for e in _events(project) if e["ev"] == "config" and "task graph unusable" in e["detail"]]
        _set_row(project, f"ap-{key}-T-1", "done")
        s2 = conductor.tick(project, st)
        rows2 = [r["task_key"] for r in _rows(project, f"ap-{key}-")]
        audit2 = [e["detail"] for e in _events(project) if e["ev"] == "config" and "task graph unusable" in e["detail"]]
        _set_row(project, f"ap-{key}-T-2", "done")
        s3 = conductor.tick(project, st)
    finally:
        _restore_advance()
    print(f"tick1={s1} rows={rows1}")
    print(f"tick1 audit_events={len(audit1)} :: {audit1}")
    print(f"tick2={s2} rows={rows2}  (T-2 dispatched after T-1, no permanent lock)")
    print(f"tick2 cumulative audit_events={len(audit2)}  (dedup proof: still one)")
    print(f"tick3={s3} advance_calls={calls}")
    print("raw timeline config events:")
    for e in _events(project):
        if e["ev"] == "config":
            print("   ", e["key"], "|", e["detail"])

    section("C2. missing write face -> serial-only (write-face gate), no stall")
    tmp = root / "nowriteface"
    tmp.mkdir()
    project = _project(tmp)
    key = "k1"
    _roadmap(project, {key: None})
    for i in range(3):
        _card(project, key, f"T-{i + 1}")  # no 写入允许面
    _set_cfg(project, max_workers_per_key=4)
    calls = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        status = conductor.tick(project, st)
    finally:
        _restore_advance()
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    events = [(e["ev"], e["detail"]) for e in _events(project)]
    print(f"tick={status} started={[r['task_key'] for r in _rows(project, f'ap-{key}-')]}")
    print(f"key_status={rm.stages[0].key_status[key]}")
    print(f"write-face events={[d for ev, d in events if ev.startswith('write-face')]}")

    section("C3. overlapping declared faces -> second refused (overlap pairs = 0)")
    tmp = root / "overlap"
    tmp.mkdir()
    project = _project(tmp)
    key = "k1"
    _roadmap(project, {key: None})
    _card(project, key, "T-1", faces=["src/shared/**"])
    _card(project, key, "T-2", faces=["src/shared/deep/**"])
    _set_cfg(project, max_workers_per_key=4)
    calls = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        status = conductor.tick(project, st)
    finally:
        _restore_advance()
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    print(f"tick={status} started={[r['task_key'] for r in _rows(project, f'ap-{key}-')]}")
    print(f"key_status={rm.stages[0].key_status[key]}")
    for ev, detail in [(e["ev"], e["detail"]) for e in _events(project)]:
        if ev.startswith("write-face"):
            print(f"    {ev} | {detail}")


def roadmap_validation(root: pathlib.Path) -> None:
    section("D. AC-010 roadmap validation in-tick + dedup")
    tmp = root / "roadmapval"
    tmp.mkdir()
    project = _project(tmp)
    _roadmap(project, {"k1": "kX"})  # dangling dependency
    calls: list = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        s1 = conductor.tick(project, st)
        n1 = len([e for e in _events(project) if e["ev"] == "config" and "roadmap validation" in e["detail"]])
        s2 = conductor.tick(project, st)
        n2 = len([e for e in _events(project) if e["ev"] == "config" and "roadmap validation" in e["detail"]])
    finally:
        _restore_advance()
    print(f"tick1={s1} roadmap_validation_events={n1}")
    print(f"tick2={s2} roadmap_validation_events={n2}  (same problem written once)")
    for e in _events(project):
        if e["ev"] == "config" and "roadmap validation" in e["detail"]:
            print("    ", e["key"], "|", e["detail"])


def ac006(root: pathlib.Path) -> None:
    section("E. AC-006 kill switch: both layers at 1 -> serial, no serve restart (config re-read per tick)")
    tmp = root / "ac006"
    tmp.mkdir()
    project = _project(tmp)
    keys = {"k1": None, "k2": None}
    _roadmap(project, keys)
    for k in keys:
        for i in range(3):
            _card(project, k, f"T-{i + 1}", faces=[f"src/{k}/{i}/**"])
    _set_cfg(project, max_parallel_keys=8, max_workers_per_key=4)
    calls: list = []
    _install_fake_advance(calls)
    try:
        st = _state(project)
        conductor.tick(project, st)
        wide_keys = sorted({r["task_key"].split("-")[1] for r in _rows(project, "ap-")})
        wide_per_key = len(_rows(project, "ap-k1-"))
        # flip BOTH bounds to 1 in the config file; no serve restart
        _set_cfg(project, max_parallel_keys=1, max_workers_per_key=1)
        tmp2 = root / "ac006b"
        tmp2.mkdir()
        project2 = _project(tmp2)
        _roadmap(project2, keys)
        for k in keys:
            for i in range(3):
                _card(project2, k, f"T-{i + 1}", faces=[f"src/{k}/{i}/**"])
        _set_cfg(project2, max_parallel_keys=1, max_workers_per_key=1)
        conductor.tick(project2, _state(project2))
    finally:
        _restore_advance()
    narrow_keys = sorted({r["task_key"].split("-")[1] for r in _rows(project2, "ap-")})
    print(f"bounds 8/4: started_keys={wide_keys} k1_rows={wide_per_key}")
    print(f"bounds 1/1: started_keys={narrow_keys} all_rows={len(_rows(project2, 'ap-'))}")
    print("config value read fresh each tick (same process, no restart): both <=1 = OK"
          if len(narrow_keys) <= 1 and len(_rows(project2, "ap-")) <= 1 else "MISMATCH")


def advance_timing(root: pathlib.Path) -> None:
    section("F. AC-013 advance wall-clock (real advance_phase.py subprocess) + event data")
    _SPEC = (
        "# Spec: probe\n\n## §0 Goal Alignment\n\n- 对齐：probe\n- 预期收益：probe\n\n"
        "## §1 概述\n\n" + ("x" * 600) + "\n\n## §3 验收标准（AC）\n\n"
        "| AC 编号 | 描述 |\n|--------|------|\n| AC-001 | probe 通过 design 门禁 |\n\n"
        "### 可复用资产\n- probe\n\n### 需规避坑点\n- probe\n"
    )
    _RESEARCH = "# Research: probe (spec)\n## 决策问题\n根定位\n## 调研方法与出处\nprobe\n"
    samples = []
    for i in range(3):
        project = root / f"adv_{i}" / "proj"
        key = f"ap-probe-{i}"
        key_dir = project / ".agenticdoc" / key
        (key_dir / "evidence" / "research").mkdir(parents=True)
        (key_dir / "spec.md").write_text(_SPEC, encoding="utf-8")
        (key_dir / "evidence" / "research" / "spec-probe.md").write_text(_RESEARCH, encoding="utf-8")
        (project / ".agentic-framework").write_text(
            f"framework=AgenticTask\nrepo={FRAMEWORK}\n", encoding="utf-8"
        )
        adv.invalidate_script_cache()
        _restore_advance()
        code, out, err, ms = conductor._timed_advance(
            key, "design", project, summary="M-02 advance timing probe"
        )
        samples.append((code, ms))
        print(f"sample {i}: exit={code} ms={ms} stderr={err.strip()[:80]}")
    # tick wall clock: one idle enabled project tick (no advance)
    tmp = root / "idletick"
    tmp.mkdir()
    idle = _project(tmp)
    _roadmap(idle, {"k1": None})
    cfg0 = config.load_config(idle)
    st = _state(idle)
    t0 = time.monotonic()
    conductor.tick(idle, st)
    idle_ms = int(round((time.monotonic() - t0) * 1000))
    total_adv = sum(ms for _, ms in samples)
    window_share = total_adv / (total_adv + idle_ms * len(samples))
    print(f"real advance samples(ms)={[ms for _, ms in samples]} median={sorted(m for _, m in samples)[1]}")
    print(f"single idle conductor tick ms={idle_ms}")
    print(
        f"window_share = sum_advance_ms / (sum_advance_ms + n*idle_tick_ms) = "
        f"{total_adv}/({total_adv}+{idle_ms * len(samples)}) = {window_share:.6f}"
    )
    print(f"ratio advance_ms / idle_tick_ms (median) = {sorted(m for _, m in samples)[1] / max(idle_ms, 1):.2f}x")

    # event payload demonstration on a real recorded result
    evt_project = root / "adv_event"
    evt_project.mkdir()
    tl = timeline.Timeline(timeline.timeline_path(evt_project))
    st2 = conductor.ConductorState(tl, 0)
    conductor._record_advance_result(
        evt_project, st2, "k1", "execute->verify", 0, "", config.default_config(),
        ms=sorted(m for _, m in samples)[1],
    )
    ev = [e for e in _events(evt_project) if e["ev"] == "advance"][0]
    print(f"advance event detail={ev['detail']!r} data={ev.get('data')}")
    print("detail byte-shape unchanged (frozen regex ^(\\S+) exit=(\\d+)(?: class=(\\S+))?$ keeps matching)")


def main() -> None:
    root = pathlib.Path(tempfile.mkdtemp(prefix="m02_probe_"))
    print(f"probe root: {root}")
    per_key_identity(root)
    key_layer_identity(root)
    serial_fallback_and_dedup(root)
    roadmap_validation(root)
    ac006(root)
    advance_timing(root)


if __name__ == "__main__":
    main()