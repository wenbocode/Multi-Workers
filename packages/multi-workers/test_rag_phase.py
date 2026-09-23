"""test_rag_phase.py — mw-rag-integration T-14 (AC-015/VC-020): the task.md
`phase:` header, write side (Python) + read side (T-10 audit).

Covered:
  * `render_task_md(..., phase=...)` writes `phase: <P>` right after `type:`;
    `phase=""` (and the omitted kwarg) is byte-identical to the pre-T-14
    renderer — the golden pins it so existing task.md files never churn;
  * conductor `dispatch()` derives the header from the owner key's
    pm-state.md interface line, and omits it for `_scratch` / a key without a
    readable phase (never guessed);
  * the T-10 audit consumes exactly the written header: a phase-only require
    with no citation lands in `required_missing`.

The audit fixture/builders come from `test_rag_audit` (T-10) — no assertion
logic is copied here.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402

import test_rag_audit as t10  # noqa: E402

from autopilot import dispatch  # noqa: E402


class RenderPhaseTest(unittest.TestCase):
    """`render_task_md`'s phase header (empty = zero byte change)."""

    # Pre-T-14 output for this exact call, pinned byte for byte.
    GOLDEN = (
        "---\n"
        "type: verifier\n"
        "origin: conductor\n"
        "loop: 1\n"
        "attempt: 1\n"
        "read_scope:\n"
        "  - src\n"
        "---\n"
        "\n"
        "do it\n"
        "\n"
    )

    def test_phase_empty_is_byte_identical_to_the_golden(self) -> None:
        omitted = dispatch.render_task_md(
            "verifier", "do it", loop="1", attempt=1, read_scope=["src"]
        )
        explicit_empty = dispatch.render_task_md(
            "verifier", "do it", loop="1", attempt=1, read_scope=["src"], phase=""
        )
        self.assertEqual(omitted, explicit_empty)
        self.assertEqual(omitted, self.GOLDEN)
        self.assertNotIn("phase:", omitted)
        print("[VERIFY] VC-020: phase_empty_byte_identical=true golden_match=true")

    def test_phase_written_after_type(self) -> None:
        text = dispatch.render_task_md(
            "verifier", "do it", loop="1", attempt=1, read_scope=["src"], phase="DESIGN"
        )
        self.assertIn("type: verifier\nphase: DESIGN\n", text)
        # Everything after the injected header line is the unchanged render.
        self.assertEqual(text.replace("phase: DESIGN\n", ""), self.GOLDEN)
        print("[VERIFY] VC-020: phase_written=true value=DESIGN")


class ConductorPhaseTest(unittest.TestCase):
    """`dispatch()` reads the owner key's pm-state.md; unknown -> no header."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        (self.root / ".agenticdoc").mkdir(parents=True)

    def _dispatch(self, owner: str):
        return dispatch.dispatch(
            self.root, owner, "stem", "phase-writer", "work", loop="1", attempt=1
        )

    def test_scratch_and_unknown_owner_omit_the_header(self) -> None:
        scratch = self._dispatch(dispatch.SCRATCH_OWNER)
        self.assertTrue(scratch.ok)
        self.assertNotIn("phase:", scratch.task_md.read_text(encoding="utf-8"))

        # A real key with no pm-state.md: phase unknown, header omitted.
        (self.root / ".agenticdoc" / "K").mkdir(parents=True)
        unknown = self._dispatch("K")
        self.assertTrue(unknown.ok)
        self.assertNotIn("phase:", unknown.task_md.read_text(encoding="utf-8"))
        print("[VERIFY] VC-020: unknown_phase_omitted=true scratch_omitted=true")

    def test_owner_phase_is_written_verbatim(self) -> None:
        keydir = self.root / ".agenticdoc" / "K"
        keydir.mkdir(parents=True)
        (keydir / "pm-state.md").write_text(
            "# PM State: K\n\n## Section 1: Snapshot\n"
            "- Key: K\n- Claim-Id: 1\n- Phase: EXECUTE\n- Updated: t\n",
            encoding="utf-8",
        )
        result = self._dispatch("K")
        self.assertTrue(result.ok)
        text = result.task_md.read_text(encoding="utf-8")
        self.assertIn("type: phase-writer\nphase: EXECUTE\n", text)
        # The audit's own reader agrees with the written header.
        self.assertEqual(mw._rag_task_meta(result.task_md)["phase"], "EXECUTE")
        print(
            "[VERIFY] VC-020: phase_written=true worker_reads_phase=true "
            "audit_consistent=true"
        )


class PhaseAuditConsistencyTest(unittest.TestCase):
    """T-10's audit (reused builders) sees the phase header and requires it."""

    def setUp(self) -> None:
        self.case = t10.RagAuditTest("test_vc020_phase_only_required_without_citation")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_phase_only_require_without_citation_is_required_missing(self) -> None:
        self.case._write_servers()
        self.case._write_roots()
        self.case._write_target(t10.TARGET_DESIGN_PHASE_REQUIRED)
        self.case._worker("K", "w-design", task_type="coding", phase="design")
        code, report = self.case._report()
        self.assertEqual(code, 1)
        record = report["required_missing"][0]
        self.assertEqual(record["role"], "coding")
        self.assertEqual(record["phase"], "design")
        self.assertEqual(record["server"], "S")

        task_md = self.case.agenticdoc / "K" / "workers" / "w-design" / "task.md"
        self.assertIn("phase: design", task_md.read_text(encoding="utf-8"))
        print(
            "[VERIFY] VC-020: audit_consistent=true phase=design "
            "required_missing=1"
        )


if __name__ == "__main__":
    unittest.main()
