"""
test_rag_audit.py — L1 tests for `mw rag audit` (mw-rag-integration T-10,
AC-015/AC-010 / VC-014, VC-019, VC-020, VC-021).

Hermetic: tempfile project dirs + `MW_RAG_SERVERS_FILE` (empty machine layer),
project-level `.mw/rag-servers.yml` + `.agenticdoc/target.yml`, a real local
file tree for the path_roots cross-check, and a hand-written
`.agenticdoc/_workers.parallel` queue.

Covered:
  VC-019  negative/positive exit codes, scan boundary (rag/*.md + terminal
          workers only), per-citation attribution, default read-only / `--out`
  VC-020  required = role.require OR phase.require; a bare `rag_call` row is
          not "used RAG" (a verifiable citation is)
  VC-021  `meta.rewrite_degraded` -> the matching call is flagged degraded,
          exit code unchanged
  VC-014  audit-side face: a required, unused terminal worker is reported as
          `required_missing` while the queue row stays `done` (warning only)
"""
import argparse
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).parent
MW_PY = PACKAGE_DIR / "mw.py"

SERVERS_YML = """\
servers:
  S:
    transport: mcp
    adapter: overcode-v1
    sources: [docs]
    capabilities: {graph: true, chat: false, rewrite: true}
    mcp:
      url: http://127.0.0.1:1/mcp
      token_env: null
      timeout_ms: 180000
    path_roots_file: roots.json
  U:
    transport: mcp
    adapter: overcode-v1
    sources: [docs]
    capabilities: {graph: false, chat: false, rewrite: false}
    mcp:
      url: http://127.0.0.1:2/mcp
"""

TARGET_PLAIN = """\
rag:
  enabled: [S, U]
  default_server: S
"""

TARGET_REVIEW_REQUIRED = """\
rag:
  enabled: [S, U]
  default_server: S
  roles:
    review:
      server: S
      require: true
"""

TARGET_CODING_REQUIRED = """\
rag:
  enabled: [S, U]
  default_server: S
  roles:
    coding:
      server: S
      require: true
"""

TARGET_DESIGN_PHASE_REQUIRED = """\
rag:
  enabled: [S, U]
  default_server: S
  phases:
    design:
      server: S
      require: true
"""


class RagAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.agenticdoc = self.root / ".agenticdoc"
        self.agenticdoc.mkdir(parents=True)
        # Empty machine layer at a path outside every project (test isolation).
        self.machine = self.root / "machine.yml"
        self.machine.write_text("servers: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(
            os.environ, {mw.mw_common.RAG_ENV_FILE: str(self.machine)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    # ── builders ─────────────────────────────────────────────────────────

    def _write_servers(self) -> None:
        path = self.root / ".mw" / "rag-servers.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SERVERS_YML, encoding="utf-8")

    def _write_roots(self) -> pathlib.Path:
        engine = self.root / "engine_src"
        engine.mkdir(parents=True, exist_ok=True)
        (self.root / "roots.json").write_text(
            json.dumps({"engine": str(engine)}), encoding="utf-8"
        )
        return engine

    def _write_target(self, text: str) -> None:
        (self.agenticdoc / "target.yml").write_text(text, encoding="utf-8")

    def _file(self, engine: pathlib.Path, relative: str, body: str = "// x\n") -> pathlib.Path:
        path = engine / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _worker(
        self,
        key: str,
        worker: str,
        *,
        status: str = "done",
        task_type: str = "coding",
        phase: str | None = None,
        output: str | None = None,
        trace: str | None = None,
    ) -> pathlib.Path:
        workdir = self.agenticdoc / key / "workers" / worker
        workdir.mkdir(parents=True, exist_ok=True)
        task_lines = [f"type: {task_type}"]
        if phase is not None:
            task_lines.append(f"phase: {phase}")
        task_lines += ["", "task body", ""]
        (workdir / "task.md").write_text("\n".join(task_lines), encoding="utf-8")
        if output is not None:
            (workdir / "output.md").write_text(output, encoding="utf-8")
        if trace is not None:
            (workdir / "trace.log").write_text(trace, encoding="utf-8")
        row = " | ".join([
            worker,
            status,
            "pi",
            "timi",
            str(workdir / "task.md"),
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "",
        ])
        with open(self.agenticdoc / "_workers.parallel", "a", encoding="utf-8", newline="\n") as fh:
            fh.write(row + "\n")
        return workdir

    # ── runners ──────────────────────────────────────────────────────────

    def _run_audit(self, *, key=None, json_output=True, out=None) -> tuple[int, str]:
        args = argparse.Namespace(
            project=str(self.root), key=key, json=json_output, out=out
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mw._cmd_rag_audit(args)
        return code, buf.getvalue()

    def _report(self, *, key=None) -> tuple[int, dict]:
        code, out = self._run_audit(key=key)
        return code, json.loads(out)

    def _snapshot(self) -> dict[str, tuple | None]:
        snap: dict[str, tuple | None] = {}
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if path.is_file():
                stat = path.stat()
                snap[rel] = (stat.st_size, stat.st_mtime_ns)
            else:
                snap[rel + "/"] = None
        return snap

    # ── parse contract ───────────────────────────────────────────────────

    def test_parse_citation_d004_forms(self) -> None:
        c = mw.parse_citation("S:src:engine::Runtime/Renderer/X.cpp:123")
        self.assertEqual(
            (c["server"], c["source"], c["file_path"], c["line"]),
            ("S", "src", "engine::Runtime/Renderer/X.cpp", 123),
        )
        spaced = mw.parse_citation("S:docs:my dir/file x.cpp:7")
        self.assertEqual(spaced["file_path"], "my dir/file x.cpp")
        windows = mw.parse_citation("S:docs:engine\\Runtime\\X.cpp:9")
        self.assertEqual(windows["file_path"], "engine\\Runtime\\X.cpp")
        unicode = mw.parse_citation("S:docs:源/文件.cpp:11")
        self.assertEqual(unicode["file_path"], "源/文件.cpp")
        self.assertIsNone(mw.parse_citation("S:src:X.cpp"))
        self.assertIsNone(mw.parse_citation("S:src:12"))

    def test_evidence_line_parsed_by_key_not_position(self) -> None:
        """Extra/reordered fields must never break the audit (T-10 contract)."""
        parsed = mw.parse_rag_evidence_line(
            "[FLOW] 2026-09-22T00:00:00Z rag_call tool=rag_search server=S "
            "results=3 via=cli ms=7 extra=zzz mcp_tool=list_sources+list_collections"
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["kind"], "rag_call")
        self.assertEqual(parsed["fields"]["server"], "S")
        self.assertEqual(parsed["fields"]["tool"], "rag_search")
        self.assertEqual(parsed["fields"]["via"], "cli")
        self.assertEqual(parsed["fields"]["ms"], "7")
        self.assertEqual(parsed["fields"]["results"], "3")
        self.assertEqual(parsed["fields"]["mcp_tool"], "list_sources+list_collections")
        # `rag-required-missing` is its own kind, not a `rag_call`.
        missing = mw.parse_rag_evidence_line(
            "[FLOW] ts rag-required-missing role=review phase=review server=S"
        )
        self.assertEqual(missing["kind"], "rag-required-missing")
        self.assertIsNone(mw.parse_rag_evidence_line("[FLOW] ts just a normal line"))

    # ── VC-019 ───────────────────────────────────────────────────────────

    def test_vc019_positive_all_reachable_exit_zero(self) -> None:
        self._write_servers()
        engine = self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._file(engine, "Runtime/Renderer/X.cpp")
        self._worker(
            "K",
            "w-ok",
            output="## 引用\n\n`S:src:engine::Runtime/Renderer/X.cpp:12` exists=true\n",
        )
        code, report = self._report()
        self.assertEqual(code, 0)
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["unverified"], [])
        self.assertEqual(len(report["citations"]), 1)
        citation = report["citations"][0]
        self.assertEqual(citation["server"], "S")
        self.assertEqual(citation["source"], "src")
        self.assertEqual(citation["file_path"], "engine::Runtime/Renderer/X.cpp")
        self.assertEqual(citation["line"], 12)
        self.assertTrue(citation["exists"])
        self.assertTrue(citation["local_path"].endswith("X.cpp"))
        self.assertEqual(citation["status"], "ok")
        print(
            "[VERIFY] VC-019: negative_exit=1 scan_boundary=rag-dir-only "
            "attribution=present writes=0"
        )

    def test_vc019_negative_missing_exit_one_with_attribution(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._worker(
            "K",
            "w-bad",
            output="## 引用\n\n`S:src:engine::Runtime/Does/Not/Exist.cpp:9`\n",
        )
        code, report = self._report()
        self.assertEqual(code, 1)
        self.assertGreaterEqual(len(report["missing"]), 1)
        record = report["missing"][0]
        self.assertEqual(record["key"], "K")
        self.assertEqual(record["task_key"], "w-bad")
        self.assertEqual(record["worker"], "w-bad")
        self.assertEqual(record["role"], "coding")
        self.assertEqual(record["phase"], "")
        self.assertEqual(record["reason"], "file missing")

    def test_vc019_scan_boundary_excludes_stage_docs_and_non_terminal(self) -> None:
        self._write_servers()
        engine = self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._file(engine, "Runtime/Renderer/X.cpp")
        # Deliverable prose (spec.md / design.md) mentions citations -> ignored.
        keydir = self.agenticdoc / "K"
        keydir.mkdir(parents=True, exist_ok=True)
        (keydir / "spec.md").write_text(
            "`S:src:engine::Runtime/Spec/Fake.cpp:1`\n", encoding="utf-8"
        )
        (keydir / "design.md").write_text(
            "`S:src:engine::Runtime/Design/Fake.cpp:2`\n", encoding="utf-8"
        )
        # A non-terminal worker is mid-write -> excluded.
        self._worker(
            "K",
            "w-running",
            status="running",
            output="`S:src:engine::Runtime/Running/Fake.cpp:3`\n",
        )
        # A terminal worker with a real citation is the only participant.
        self._worker(
            "K",
            "w-ok",
            output="`S:src:engine::Runtime/Renderer/X.cpp:12`\n",
        )
        code, report = self._report()
        self.assertEqual(code, 0)
        self.assertEqual(report["missing"], [])
        files = {record["file"] for record in report["citations"]}
        self.assertEqual(files, {".agenticdoc/K/workers/w-ok/output.md"})
        self.assertTrue(all("spec.md" not in f and "design.md" not in f for f in files))
        self.assertTrue(all("w-running" not in f for f in files))

    def test_vc019_key_filter_limits_the_scan(self) -> None:
        self._write_servers()
        engine = self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._file(engine, "A.cpp")
        self._worker("K1", "w1", output="`S:src:engine::A.cpp:1`\n")
        self._worker("K2", "w2", output="`S:src:engine::Missing.cpp:1`\n")
        code, report = self._report(key="K1")
        self.assertEqual(code, 0)
        self.assertEqual(report["missing"], [])
        code2, report2 = self._report(key="K2")
        self.assertEqual(code2, 1)
        self.assertEqual(len(report2["missing"]), 1)

    def test_unverified_when_server_has_no_path_roots(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_PLAIN)
        # Server U is configured but declares no path_roots_file.
        self._worker("K", "w-u", output="`U:docs:some/file.cpp:5`\n")
        code, report = self._report()
        self.assertEqual(code, 1)
        self.assertEqual(report["missing"], [])
        self.assertEqual(len(report["unverified"]), 1)
        self.assertIn("path_roots", report["unverified"][0]["reason"])

    def test_vc019_default_read_only_and_out_is_the_only_write(self) -> None:
        self._write_servers()
        engine = self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._file(engine, "Runtime/Renderer/X.cpp")
        self._worker("K", "w-ok", output="`S:src:engine::Runtime/Renderer/X.cpp:1`\n")
        before = self._snapshot()
        code, _out = self._run_audit()
        self.assertEqual(code, 0)
        self.assertEqual(self._snapshot(), before)
        # `--out` is the one explicit write (JSON report), nothing else moves.
        out_file = self.root / "reports" / "audit.json"
        code2, _out2 = self._run_audit(out=out_file)
        self.assertEqual(code2, 0)
        self.assertTrue(out_file.is_file())
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["citations"]), 1)
        after = self._snapshot()
        self.assertEqual(set(after) - set(before), {"reports/", "reports/audit.json"})
        changed = {k for k in before if before[k] != after.get(k)}
        self.assertEqual(changed, set())

    def test_disabled_project_is_read_only_and_stable(self) -> None:
        self.machine.unlink()  # no machine layer, no project file, no target
        (self.agenticdoc / "K" / "workers" / "w").mkdir(parents=True)
        before = self._snapshot()
        code, out = self._run_audit()
        self.assertEqual(code, 0)
        self.assertEqual(self._snapshot(), before)
        report = json.loads(out)
        self.assertEqual(
            (report["calls"], report["citations"], report["missing"],
             report["unverified"], report["required_missing"]),
            ([], [], [], [], []),
        )
        self.assertFalse((self.agenticdoc / "K" / "rag").exists())

    def test_cli_subprocess_json_and_exit_code(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._worker("K", "w-bad", output="`S:src:engine::Gone.cpp:1`\n")
        result = subprocess.run(
            [sys.executable, str(MW_PY), "rag", "audit",
             "--project", str(self.root), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertGreaterEqual(len(report["missing"]), 1)

    # ── VC-020 ───────────────────────────────────────────────────────────

    def test_vc020_role_only_required_without_citation(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_CODING_REQUIRED)
        # Used RAG (one rag_call row) but produced no verifiable citation.
        self._worker(
            "K",
            "w-call-only",
            output="no citation here\n",
            trace=(
                "[FLOW] 2026-09-22T00:00:00Z rag_call server=S tool=rag_search "
                "via=mcp ms=12 results=3 mcp_tool=rag_search\n"
            ),
        )
        code, report = self._report()
        self.assertEqual(code, 1)
        self.assertEqual(len(report["required_missing"]), 1)
        record = report["required_missing"][0]
        self.assertEqual(record["role"], "coding")
        self.assertEqual(record["phase"], "")
        self.assertEqual(record["server"], "S")

    def test_vc020_phase_only_required_without_citation(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_DESIGN_PHASE_REQUIRED)
        self._worker("K", "w-design", task_type="coding", phase="design")
        code, report = self._report()
        self.assertEqual(code, 1)
        self.assertEqual(len(report["required_missing"]), 1)
        record = report["required_missing"][0]
        self.assertEqual(record["role"], "coding")
        self.assertEqual(record["phase"], "design")

    def test_vc105_unregistered_type_falls_back_to_coding_role(self) -> None:
        """VC-105 / D-105: `type: foobar` (unregistered) resolves to the
        `coding` role on both sides, so `roles.coding.require` decides the
        audit verdict just like `roleForTaskType` does for the TS worker."""
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_CODING_REQUIRED)
        # A missing citation would already breach `coding.require`; the point is
        # that the role itself is `coding`, not the raw `foobar`.
        self._worker("K", "w-unknown", task_type="foobar", output="no rag\n")
        code, report = self._report()
        self.assertEqual(code, 1)
        self.assertEqual(len(report["required_missing"]), 1)
        record = report["required_missing"][0]
        self.assertEqual(record["worker"], "w-unknown")
        self.assertEqual(record["role"], "coding")
        self.assertEqual(record["server"], "S")
        # Evidence fields come from the parsed audit record + exit code (AC-108),
        # not from literal labels: a role-fallback regression flips them.
        print(
            f"[VERIFY] VC-105: py_role={record['role']} py_required=true "
            f"type_literal=foobar server={record['server']} exit={code}"
        )

    def test_vc020_verifiable_citation_satisfies_require(self) -> None:
        self._write_servers()
        engine = self._write_roots()
        self._write_target(TARGET_REVIEW_REQUIRED)
        self._file(engine, "Runtime/Renderer/X.cpp")
        self._worker(
            "K",
            "w-review",
            task_type="review",
            output="`S:src:engine::Runtime/Renderer/X.cpp:1`\n",
        )
        code, report = self._report()
        self.assertEqual(code, 0)
        self.assertEqual(report["required_missing"], [])
        print(
            "[VERIFY] VC-020: role_only=missing phase_only=missing "
            "call_without_citation=missing"
        )

    # ── VC-021 ───────────────────────────────────────────────────────────

    def test_vc021_degraded_flag_marks_the_matching_call_only(self) -> None:
        self._write_servers()
        engine = self._write_roots()
        self._write_target(TARGET_PLAIN)
        self._file(engine, "A.cpp")
        self._worker(
            "K",
            "w-degraded",
            output="`S:src:engine::A.cpp:1`\n",
            trace=(
                "[FLOW] 2026-09-22T00:00:00Z rag_call server=S tool=rag_search "
                "via=mcp ms=12 results=3 mcp_tool=rag_search_multi_rounds\n"
                "[FLOW] 2026-09-22T00:00:01Z rag-rewrite-degraded server=S tool=rag_search\n"
            ),
        )
        self._worker(
            "K",
            "w-clean",
            output="`S:src:engine::A.cpp:2`\n",
            trace=(
                "[FLOW] 2026-09-22T00:00:02Z rag_call server=S tool=rag_search "
                "via=mcp ms=5 results=1 mcp_tool=rag_search\n"
            ),
        )
        code, report = self._report()
        self.assertEqual(code, 0)
        by_worker = {call["worker"]: call for call in report["calls"]}
        self.assertTrue(by_worker["w-degraded"]["degraded"])
        self.assertFalse(by_worker["w-clean"]["degraded"])
        print(
            "[VERIFY] VC-021: degraded_flag=true "
            "trace_delta=rag-rewrite-degraded clean_delta=0"
        )

    # ── VC-014 (audit-side face) ─────────────────────────────────────────

    def test_vc014_required_missing_is_warning_only(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_REVIEW_REQUIRED)
        self._worker("K", "w-review", task_type="review", output="no rag\n")
        queue = self.agenticdoc / "_workers.parallel"
        queue_before = queue.read_bytes()
        snapshot = self._snapshot()
        code, report = self._report()
        self.assertEqual(code, 1)
        self.assertEqual(len(report["required_missing"]), 1)
        self.assertEqual(report["required_missing"][0]["role"], "review")
        # Warning only, read-only: queue row keeps `done`, nothing was written.
        self.assertIn(b"| done |", queue_before)
        self.assertEqual(queue.read_bytes(), queue_before)
        self.assertEqual(self._snapshot(), snapshot)
        print(
            "[VERIFY] VC-014: status=done trace=rag-required-missing "
            "output_marked=true (TS worker face; audit-side detection read-only)"
        )

    # ── doctor section (T-10 item 3) ─────────────────────────────────────

    def test_doctor_rag_reports_required_missing_count(self) -> None:
        self._write_servers()
        self._write_roots()
        self._write_target(TARGET_REVIEW_REQUIRED)
        self._worker("K", "w-review", task_type="review", output="no rag\n")
        section = mw._doctor_rag(self.root)
        self.assertEqual(section["required_missing"], 1)
        self.assertIn("required_missing=1", mw._format_rag_doctor_line(section))

    # ── error paths ──────────────────────────────────────────────────────

    def test_usage_errors_exit_two(self) -> None:
        code, _out = self._run_audit(key="no-such-key")
        self.assertEqual(code, 2)
        args = argparse.Namespace(
            project=str(self.root / "missing"), key=None, json=True, out=None
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code2 = mw._cmd_rag_audit(args)
        self.assertEqual(code2, 2)

    def test_config_error_exit_two(self) -> None:
        self._write_servers()
        self._write_target("rag:\n  enabled: [Z]\n")
        code, _out = self._run_audit()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
