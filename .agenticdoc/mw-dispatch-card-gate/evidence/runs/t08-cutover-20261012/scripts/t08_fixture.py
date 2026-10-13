"""T-08 cutover runtime-evidence fixture builder (mw-dispatch-card-gate).

Builds three hermetic project fixtures used to prove, at the service layer:

* ``pos``        — a CARD-FORM dispatch of this very task card (T-08): the
                   producer renderer writes ``card_path:`` + ``card_sha256:``
                   + ``envelope_producer:``, the three canonical sections and
                   the four ``coding`` extras; the service gate lets it spawn.
* ``neg-skew``   — a post-boundary dispatch whose producer identity is
                   provably older than the service baseline and whose envelope
                   is incomplete -> the new T-14 branch: row
                   ``failed(producer-skew ...)`` + ``[ENVELOPE-SKEW]`` alarm,
                   ``spawned=[]``.
* ``neg-legacy`` — a post-boundary dispatch with no producer identity line ->
                   T-09 ``envelope missing`` refusal + loud upgrade guidance,
                   ``spawned=[]``.

Nothing here touches the real ``.agenticdoc`` tree or any tracked source; all
fixtures live under this evidence run directory.

Run (repo root):
    python -X utf8 .agenticdoc/mw-dispatch-card-gate/evidence/runs/t08-cutover-20261012/scripts/t08_fixture.py
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parents[6]
RUN = pathlib.Path(__file__).resolve().parents[1]
KEY = "mw-dispatch-card-gate"
STEM = "T-08-cutover-and-runtime-evidence"
CARD_SRC = REPO / ".agenticdoc" / KEY / "tasks" / f"{STEM}.md"

sys.path.insert(0, str(REPO / "packages" / "multi-workers"))

import mw_common  # noqa: E402
from autopilot import dispatch  # noqa: E402

_PROVIDERS = {
    "credentials": {"timi": {"sources": [{"env": "TIMI_API_KEY"}]}},
    "providers": {"timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"}},
}


def _reset(name: str) -> pathlib.Path:
    root = RUN / "fixture" / name
    if root.exists():
        shutil.rmtree(root)
    (root / ".agenticdoc" / KEY / "tasks").mkdir(parents=True)
    (root / "providers.json").write_text(json.dumps(_PROVIDERS, indent=2), encoding="utf-8")
    return root


def _write_task_and_row(root: pathlib.Path, worker: str, text: str) -> pathlib.Path:
    task_dir = root / ".agenticdoc" / KEY / "workers" / worker
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text(text, encoding="utf-8", newline="\n")
    row = {
        "task_key": worker,
        "status": "pending",
        "cli": "pi",
        "provider": "timi",
        "task_path": str(task_md),
        "dispatched_at": mw_common.iso_now(),
        "updated_at": mw_common.iso_now(),
        "model": "",
        "origin": "conductor",
    }
    mw_common.upsert_worker_row(mw_common.workers_path(root), row)
    return task_md


def build_pos() -> pathlib.Path:
    """Card-form dispatch of the real T-08 card, via the real producer renderer."""
    root = _reset("pos")
    card_dst = root / ".agenticdoc" / KEY / "tasks" / f"{STEM}.md"
    shutil.copy2(CARD_SRC, card_dst)

    card = dispatch.dispatch_card(root, KEY, STEM)
    assert card is not None, "producer must resolve the copied card"
    prompt = (
        f"Execute card {CARD_SRC.name} end to end. "
        "Seed only; the card is authoritative."
    )
    text = dispatch.render_task_md(
        "coding",
        prompt,
        loop=f"exec:{KEY}:{STEM}",
        attempt=1,
        card=card,
    )
    task_md = _write_task_and_row(root, STEM, text)
    print(f"[fixture pos] card          = {card_dst}")
    print(f"[fixture pos] card_sha256   = {card['sha256']}")
    print(f"[fixture pos] task.md       = {task_md}")
    print(f"[fixture pos] envelope_producer emitted: {'envelope_producer:' in text}")
    return root


def build_neg_skew() -> pathlib.Path:
    root = _reset("neg-skew")
    text = (
        "type: coding\n"
        "envelope_producer: autopilot-conductor@0.60.0\n"
        "Do something useful.\n"
    )
    task_md = _write_task_and_row(root, "mwd-neg-skew", text)
    print(f"[fixture neg-skew] task.md = {task_md}")
    return root


def build_neg_legacy() -> pathlib.Path:
    root = _reset("neg-legacy")
    text = "type: coding\nDo something useful.\n"
    task_md = _write_task_and_row(root, "mwd-neg-legacy", text)
    print(f"[fixture neg-legacy] task.md = {task_md}")
    return root


if __name__ == "__main__":
    build_pos()
    build_neg_skew()
    build_neg_legacy()
    print("[fixture] done")
