"""
test_e2e_real.py — L2 E2E: real pi CLI + real timi LLM (AC-013 / VC-014).

Not part of the default run. Execute explicitly:

    python -m pytest test_e2e_real.py -m e2e_real

Skips automatically when no timi credential is resolvable (env TIMI_API_KEY or
pi's own ~/.pi/agent/auth.json). Upstream failures are surfaced with the
worker.log tail so a human can tell "code broken" from "environment unavailable"
(spec §4 risk).
"""
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common

PKG_DIR = pathlib.Path(__file__).parent
LAUNCHER = PKG_DIR / "launcher.py"
_REPO_PROVIDERS = PKG_DIR / "providers.json"

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

pytestmark = pytest.mark.e2e_real


def _timi_available() -> bool:
    config = mw_common.load_providers(_REPO_PROVIDERS)
    value, _source = mw_common.resolve_credential(
        config["credentials"].get("timi"), os.environ
    )
    return value is not None


def _zai_available() -> bool:
    config = mw_common.load_providers(_REPO_PROVIDERS)
    value, _source = mw_common.resolve_credential(
        config["credentials"].get("zai-coding-cn"), os.environ
    )
    return value is not None


@pytest.fixture()
def proj(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / ".agenticdoc").mkdir()
    (tmp_path / ".mw").mkdir()
    return tmp_path


@pytest.fixture()
def launcher_proc(proj: pathlib.Path):
    env = dict(os.environ)
    env.setdefault("FAKE_MARK_DIR", "")  # unused; keeps env shape stable
    proc = subprocess.Popen(
        [
            sys.executable, str(LAUNCHER),
            "--project", str(proj),
            "--poll-interval", "1",
            "--providers", str(_REPO_PROVIDERS),
        ],
        env=env,
        stdout=open(proj / "launcher-out.log", "wb"),
        stderr=subprocess.STDOUT,
        creationflags=_CREATE_NO_WINDOW,
    )
    yield proc
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _make_task(
    proj: pathlib.Path, key: str, prompt: str, model: str = ""
) -> pathlib.Path:
    # Keyed layout contract (launcher._validate_task_path): tasks live under
    # .agenticdoc/{owner}/workers/<task_key>/ or .agenticdoc/_scratch/workers/.
    # The .agenticdoc root belongs to AgenticTask keys and is rejected.
    task_dir = proj / ".agenticdoc" / "_scratch" / "workers" / key
    task_dir.mkdir(parents=True)
    task_md = task_dir / "task.md"
    # Multiline on purpose: the -p argument is flattened by the launcher, and
    # the reply proves the full prompt actually reached the model (Windows
    # .cmd shims truncate multiline args at the first newline otherwise).
    # The optional `model:` interface line is the explicit per-task route —
    # the queue row stays on the PM default (provider timi, model "").
    model_line = f"model: {model}\n" if model else ""
    task_md.write_text(f"type: coding\n{model_line}\n{prompt}\n", encoding="utf-8")
    now = mw_common.iso_now()
    row = mw_common.serialize_entry({
        "task_key": key, "status": "pending", "cli": "pi", "provider": "timi",
        "task_path": str(task_md), "dispatched_at": now, "updated_at": now,
        "model": "",
    })
    with mw_common.workers_path(proj).open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")
    return task_md


def _status(proj: pathlib.Path, key: str) -> str | None:
    return {
        e["task_key"]: e["status"]
        for e in mw_common.parse_workers_file(mw_common.workers_path(proj))
    }.get(key)


class TestRealTimiDispatch:
    def test_say_exactly_ok_full_chain(self, proj: pathlib.Path, launcher_proc) -> None:
        if not _timi_available():
            pytest.skip("no timi credentials (env TIMI_API_KEY or ~/.pi/agent/auth.json)")

        prompt = "Ignore the type line above.\nYour entire reply must be exactly: ok"
        _make_task(proj, "e2e-ok", prompt)

        deadline = time.monotonic() + 120
        status = None
        while time.monotonic() < deadline:
            status = _status(proj, "e2e-ok")
            if status in ("done", "failed", "needs-clarification"):
                break
            time.sleep(1.0)

        task_dir = proj / ".agenticdoc" / "_scratch" / "workers" / "e2e-ok"
        worker_log = task_dir / "worker.log"
        if status is None or status not in ("done", "failed", "needs-clarification"):
            tail = worker_log.read_text(encoding="utf-8", errors="replace")[-2000:] if worker_log.exists() else "(no worker.log)"
            pytest.fail(
                "task did not reach a terminal state within 120s — environment "
                f"unavailable? (status={status})\nworker.log tail:\n{tail}"
            )

        assert status == "done", (
            f"status={status}; worker.log tail:\n"
            f"{worker_log.read_text(encoding='utf-8', errors='replace')[-2000:] if worker_log.exists() else '(none)'}"
        )

        output_md = task_dir / "output.md"
        assert output_md.exists(), "worker finished but wrote no output.md"
        content = output_md.read_text(encoding="utf-8")
        assert "## Summary" in content
        assert len(content.encode("utf-8")) > 50
        # The full (flattened) prompt reached the model: it replied "ok".
        assert "ok" in content.lower()

        trace = task_dir / "trace.log"
        if trace.exists():
            assert "[FLOW]" in trace.read_text(encoding="utf-8", errors="replace")


class TestRealZaiDispatch:
    """L2 e2e: real pi CLI + real zai-coding-cn LLM via the zai/ prefix
    (mw-provider-routing AC-005 / VC-005)."""

    def test_say_exactly_ok_full_chain(self, proj: pathlib.Path, launcher_proc) -> None:
        if not _zai_available():
            pytest.skip("no zai-coding-cn credentials (env ZAI_CODING_CN_API_KEY or auth.json)")

        prompt = "Ignore the type and model lines above.\nYour entire reply must be exactly: ok"
        _make_task(proj, "e2e-zai-ok", prompt, model="zai/glm-5.3")

        deadline = time.monotonic() + 180
        status = None
        while time.monotonic() < deadline:
            status = _status(proj, "e2e-zai-ok")
            if status in ("done", "failed", "needs-clarification"):
                break
            time.sleep(1.0)

        task_dir = proj / ".agenticdoc" / "_scratch" / "workers" / "e2e-zai-ok"
        worker_log = task_dir / "worker.log"
        tail = worker_log.read_text(encoding="utf-8", errors="replace")[-2000:] if worker_log.exists() else "(no worker.log)"
        if status is None or status not in ("done", "failed", "needs-clarification"):
            pytest.fail(
                "task did not reach a terminal state within 180s — environment "
                f"unavailable? (status={status})\nworker.log tail:\n{tail}"
            )

        assert status == "done", f"status={status}; worker.log tail:\n{tail}"

        # The zai/ prefix reached the spawn: launcher log shows the resolved
        # model value and its source.
        launcher_log = (proj / "launcher-out.log").read_text(encoding="utf-8", errors="replace")
        assert "model=zai/glm-5.3" in launcher_log
        assert "source=task" in launcher_log

        # A real model roundtrip happened: output.md carries the reply.
        output_md = task_dir / "output.md"
        assert output_md.exists(), "worker finished but wrote no output.md"
        content = output_md.read_text(encoding="utf-8")
        assert "## Summary" in content
        assert "ok" in content.lower()

        # The worker ran glm-5.3 (trace [MODEL] lifecycle line).
        trace = task_dir / "trace.log"
        if trace.exists():
            trace_text = trace.read_text(encoding="utf-8", errors="replace")
            assert "model=glm-5.3" in trace_text
