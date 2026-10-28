"""Pre-delivery behaviour emulation for T11b RED evidence (verification only).

The delivered source tree is never modified: this pytest plugin patches the
*pre-T11b* semantics in memory for one run, so the delivered tests are executed
against the behaviour this card is supposed to add. It exists to produce honest
RED evidence on a source tree whose pre-card state was never committed (the
dashboard/playground/monitor files are untracked in this key), and it is not
part of the shipped suite.

Modes (``T11B_RED_MODE``):
  wiring      - no lazy provider resolution (only an injected provider counts)
  projection  - no result projection: answers are not persisted/read back
  busy409     - a concurrent submission answers HTTP 200 (the pre-card shape)
  ui          - the pre-card placeholder page (no DP test controls)
"""

from __future__ import annotations

import os
import pathlib

import decision_monitor

MODE = os.environ.get("T11B_RED_MODE", "")


def pytest_configure(config) -> None:
    del config
    if MODE == "wiring":

        def resolve_playground(self, control_root):
            del control_root
            return self.playground

        decision_monitor.MonitorDeps.resolve_playground = resolve_playground
    elif MODE == "projection":
        import decision_playground

        empty = {
            "answer_persisted": False,
            "projection_status": "not-recorded",
            "projection_sha256": None,
            "projection_redactions": None,
            "projection_truncated_fields": [],
            "result_projection": None,
        }

        def persist(self, **kwargs):
            del self, kwargs
            return dict(empty)

        def read(self, submission_id):
            del self, submission_id
            return None

        decision_playground.DecisionPlayground._persist_projection = persist
        decision_playground.DecisionPlayground._read_projection = read
    elif MODE == "busy409":
        original = decision_monitor._ApiError.__init__

        def init(self, status, code, message, issues=None, data=None):
            if code == "busy":
                status = 200
            original(self, status, code, message, issues, data)

        decision_monitor._ApiError.__init__ = init
    elif MODE == "ui":
        # The DOM harness reads the shipped files from ASSET_DIR; point it at a
        # copy whose HTML is the pre-card placeholder page (JS/CSS unchanged).
        import shutil
        import tempfile

        page = pathlib.Path(__file__).with_name("pre-t11b-dashboard.html").read_text(
            encoding="utf-8"
        )
        stage = pathlib.Path(tempfile.mkdtemp(prefix="t11b-red-ui-"))
        for name in (
            "decision_dashboard.html",
            "decision_dashboard.js",
            "decision_dashboard.css",
        ):
            source = decision_monitor.ASSET_DIR / name
            if source.exists():
                shutil.copy2(source, stage / name)
        (stage / "decision_dashboard.html").write_text(
            page, encoding="utf-8", newline="\n"
        )
        decision_monitor.ASSET_DIR = stage
