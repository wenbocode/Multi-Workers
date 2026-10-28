"""Verify exact CLI edits and unchanged source outside declared lifecycle regions."""
import difflib
import hashlib
import json
import pathlib

key = pathlib.Path(__file__).resolve().parent.parent
root = key.parent.parent
package = root / "packages/multi-workers"
baseline = key / "evidence/baseline"
rows = {}
for name in ("mw.py", "decision_monitor.py"):
    before = (baseline / name).read_bytes()
    after = (package / name).read_bytes()
    rows[name] = {"before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": hashlib.sha256(after).hexdigest(), "before_bytes": len(before), "after_bytes": len(after), "before_crlf": before.count(b"\r\n"), "after_crlf": after.count(b"\r\n")}
    (key / "evidence" / (name + ".session.diff")).write_text("".join(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True), after.decode("utf-8").splitlines(keepends=True), fromfile="frozen/"+name, tofile="current/"+name)), encoding="utf-8", newline="")
    if name == "mw.py":
        expected = before
        for old, new in (
            (b"root, starter=starter, health_wait_s=_MONITOR_HEALTH_WAIT_S", b"root, starter=starter, health_wait_s=_MONITOR_HEALTH_WAIT_S, replace_incompatible=True"),
            (b'"recovery": getattr(instance, "recovery", None),', b'"recovery": getattr(instance, "recovery", None),\r\n        "replacement": getattr(instance, "replacement", None),'),
            (b'mode = "reused" if reused else "started"', b'mode = "reused" if reused else "replaced" if payload["replacement"] else "started"'),
        ):
            assert expected.count(old) == 1
            expected = expected.replace(old, new)
        assert expected == after, "CLI edit changed bytes beyond the three declared replacements"
        rows[name]["exact_three_edit_replay"] = True
    else:
        before = before.replace(b"  malformed or version-incompatible state is never touched. ``recover_stale``", b"  malformed state is never touched. Live incompatible instances are replaced\n  only by an explicit CLI open after authenticated shutdown and process-exit\n  proof under the start lock. ``recover_stale``")
        before = before.replace(b'``instance-unknown``, ``incompatible-instance``, ``health-failed``.', b'``instance-unknown``, ``incompatible-instance``, ``stop-failed``,\n``starter-failed``, ``health-failed``.')
        for start, end in ((b"def _compute_code_fingerprint()", b"def _mw_dir("), ("# ── Orchestration".encode(), b"def _default_starter("), (b"def ensure_instance(", b"def serve(")):
            def outside(body):
                left = body.index(start)
                right = body.index(end, left)
                return body[:left] + body[right:]
            before = outside(before)
            after = outside(after)
        assert before == after, "monitor bytes outside fingerprint/orchestration/ensure/docs changed"
        rows[name]["outside_declared_regions_equal"] = True
(key / "evidence/source-integrity.json").write_text(json.dumps(rows, indent=2), encoding="utf-8", newline="\n")
print(json.dumps(rows, indent=2))
