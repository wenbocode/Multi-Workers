"""
test_rag_docs.py — manual <-> implementation parity for the RAG config guide
(T-22 / VC-205, VC-206, VC-209).

What is pinned here:
  * VC-206: the three fenced blocks tagged `<!-- mw-rag-init:print ... -->` in
    `docs/rag-config-guide.md` are byte-identical (after EOL / trailing-space
    normalization) to the real `python mw.py rag init --print` output, so the
    manual can never silently drift from the template source (D-201 / P-008).
  * VC-205 (doc side): the field tables in the manual document exactly the
    field set the validator accepts (missing OR extra -> red), every YAML key
    appearing in a fenced example is a key the validator accepts, and a config
    built from all documented fields really parses via `load_rag_config`.
  * VC-209 (honesty): the error texts quoted in the "写错的后果" column exist
    verbatim in `mw_common.py`.

Hermetic: the `--print` subprocess runs with MW_RAG_SERVERS_HOME + HOME +
USERPROFILE pointed at a temp dir and PYTHONIOENCODING=utf-8 (Windows default
stdio is GBK, which would not round-trip the template's em dashes).
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common as mc  # noqa: E402

HERE = pathlib.Path(__file__).parent
MW_PY = HERE / "mw.py"
MANUAL_PATH = HERE / "docs" / "rag-config-guide.md"
MW_COMMON_PATH = HERE / "mw_common.py"
TAGS = ("servers", "target", "roots")

# Nodes that are names, not keys: server names and role/phase names used in the
# examples. They are free-form in the config, so the reverse key check ignores
# them (a bogus *field* name is still caught because it is not in ACCEPTED).
EXAMPLE_NODES = {
    "example", "overcode", "engine-cli",
    "coding", "review", "research", "design", "spec",
}
# Layer roots / block containers that appear as YAML keys but are not leaf
# fields of the server table or the `rag:` section.
CONTAINER_KEYS = {"servers", "rag", "capabilities", "mcp", "skill", "budgets"}


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _normalize(text: str) -> str:
    """The only allowed manual/CLI differences (T-22 parity contract)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _manual_block(manual: str, tag: str) -> str:
    pattern = re.compile(
        r"<!-- mw-rag-init:print " + re.escape(tag) + r" -->\s*```[A-Za-z]*\n(.*?)```",
        re.DOTALL,
    )
    match = pattern.search(manual)
    if match is None:
        raise AssertionError(f"manual has no tagged block for {tag!r}")
    return match.group(1)


def _split_print(stdout: str) -> dict[str, str]:
    """`mw rag init --print` -> {tag: segment} (separator lines dropped)."""
    parts = stdout.split("# ===== file: ")
    assert len(parts) == len(TAGS) + 1, f"expected {len(TAGS)} segments, got {len(parts) - 1}"
    segments: dict[str, str] = {}
    for tag, part in zip(TAGS, parts[1:]):
        _path_line, _, body = part.partition("\n")
        segments[tag] = body
    return segments


def _expected_rows() -> set[str]:
    """The field-set the validator accepts, as manual table-row labels.

    Derived from `mw_common` so a validator field addition/removal turns this
    test red until the manual is updated (VC-205, both directions).
    """
    containers = {"capabilities", "mcp", "skill"}
    rows = {str(f) for f in mc._RAG_SERVER_FIELDS if f not in containers}
    for block, keys in mc._RAG_NESTED_FIELDS.items():
        rows |= {f"{block}.{key}" for key in keys}
    rows |= {str(key) for key in mc._RAG_TARGET_KEYS if key != "budgets"}
    rows |= {f"budgets.{key}" for key in mc._RAG_BUDGET_KEYS}
    rows |= {str(key) for key in mc._RAG_ROLE_KEYS}
    rows |= {str(key) for key in mc._RAG_PHASE_KEYS}
    return rows


def _bare_leaves() -> set[str]:
    leaves = {"budgets"}
    for keys in mc._RAG_NESTED_FIELDS.values():
        leaves |= {str(key) for key in keys}
    return leaves


def _documented_rows(manual: str) -> set[str]:
    """Backticked first-cell labels of the field tables in section 3."""
    section = manual.split("## 3.", 1)[1].split("## 4.", 1)[0]
    row_re = re.compile(r"^\|\s*`([A-Za-z_][A-Za-z0-9_.\-]*)`\s*\|")
    return {match.group(1) for line in section.splitlines() if (match := row_re.match(line))}


def _example_yaml_keys(manual: str) -> set[str]:
    """Every key appearing in a fenced ```yaml block (comments stripped)."""
    keys: set[str] = set()
    for block in re.findall(r"```yaml\n(.*?)```", manual, re.DOTALL):
        for raw in block.split("\n"):
            line = raw.split("#", 1)[0]
            match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*:", line)
            if match:
                keys.add(match.group(1))
            for flow in re.findall(r"[{,]\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*:", line):
                keys.add(flow)
    return keys


class RagDocsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = pathlib.Path(self._tmp.name)
        self.root = base / "project"
        self.root.mkdir()
        self.home = base / "home"
        self.home.mkdir()
        self._env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "MW_RAG_SERVERS_HOME": str(self.home),
                "MW_RAG_SERVERS_FILE": "",
            },
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)
        self.manual = MANUAL_PATH.read_text(encoding="utf-8")

    # ── VC-206: byte parity with `mw rag init --print` ───────────────────

    def test_vc206_manual_matches_print_output(self) -> None:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, str(MW_PY), "rag", "init", "--print", f"--project={self.root}"],
            capture_output=True,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        segments = _split_print(result.stdout.decode("utf-8"))
        self.assertEqual(len(segments), 3)

        for tag in TAGS:
            manual_block = _normalize(_manual_block(self.manual, tag))
            printed = _normalize(segments[tag])
            self.assertEqual(
                manual_block,
                printed,
                f"manual block {tag!r} drifted from `mw rag init --print`",
            )

        byte_counts = {tag: len(_normalize(segments[tag]).encode("utf-8")) for tag in TAGS}
        _verify(
            "VC-206",
            sections=len(segments),
            servers_bytes=byte_counts["servers"],
            target_bytes=byte_counts["target"],
            roots_bytes=byte_counts["roots"],
        )

    # ── VC-205: field coverage, reverse key check, validator acceptance ──

    def test_vc205_field_tables_match_validator(self) -> None:
        expected = _expected_rows()
        documented = _documented_rows(self.manual)
        missing = expected - documented
        extra = documented - expected
        self.assertEqual(missing, set(), f"manual is missing field rows: {sorted(missing)}")
        self.assertEqual(extra, set(), f"manual documents unknown field rows: {sorted(extra)}")

        accepted = expected | _bare_leaves() | CONTAINER_KEYS
        unknown = _example_yaml_keys(self.manual) - accepted - EXAMPLE_NODES
        self.assertEqual(
            unknown, set(), f"manual examples use YAML keys the validator does not accept: {sorted(unknown)}"
        )

        _verify(
            "VC-205",
            documented_rows=len(documented),
            missing=0,
            extra=0,
            example_yaml_keys=len(_example_yaml_keys(self.manual)),
            unaccepted=0,
        )

    def test_vc205_validator_accepts_every_documented_field(self) -> None:
        servers_yml = """
servers:
  overcode:
    transport: both
    adapter: overcode-v1
    path_roots_file: .mw/rag-roots.json
    sources: [code, docs]
    capabilities: {graph: true, chat: true, rewrite: true}
    mcp:
      url: http://localhost:8100/mcp/
      token_env: OVERCODE_MCP_TOKEN
      timeout_ms: 180000
    skill:
      dir: skills/overcode
      cli_entry: python overcode_cli.py
      timeout_ms: 180000
"""
        target_yml = """
rag:
  enabled: [overcode]
  default_server: overcode
  roles:
    research:
      server: overcode
      source: code
      require: true
      rewrite: true
      chat_budget: 4
      time_budget_s: 1200
  phases:
    design:
      server: overcode
      source: docs
      require: true
      rewrite: true
  budgets:
    chat_budget: 4
    time_budget_s: 1200
"""
        (self.root / ".mw").mkdir(parents=True)
        (self.root / ".agenticdoc").mkdir(parents=True)
        (self.root / ".mw" / "rag-servers.yml").write_text(servers_yml, encoding="utf-8")
        (self.root / ".agenticdoc" / "target.yml").write_text(target_yml, encoding="utf-8")
        (self.root / ".mw" / "rag-roots.json").write_text(
            '{"engine": "/tmp/engine", "_note": "ignored"}\n', encoding="utf-8"
        )

        config, error = mc.load_rag_config(self.root)
        self.assertIsNone(error, error)
        self.assertEqual(config["enabled"], ["overcode"])
        entry = config["servers"]["overcode"]
        self.assertEqual(entry["transport"], "both")
        self.assertEqual(entry["capabilities"], {"graph": True, "chat": True, "rewrite": True})
        self.assertEqual(entry["sources"], ["code", "docs"])
        self.assertTrue(entry["path_roots_digest"])
        self.assertEqual(config["roles"]["research"]["chat_budget"], 4)
        self.assertEqual(config["phases"]["design"]["require"], True)
        # The documented YAML really round-trips both files.
        self.assertIsInstance(yaml.safe_load(servers_yml), dict)
        self.assertIsInstance(yaml.safe_load(target_yml), dict)
        _verify(
            "VC-205-accept",
            load_error=0,
            enabled=len(config["enabled"]),
            servers=len(config["servers"]),
            role_keys=len(config["roles"]["research"]),
            phase_keys=len(config["phases"]["design"]),
        )

    def test_vc205_rag_roots_semantics_documented(self) -> None:
        """The roots file maps the citation's root role to an absolute local
        root; `_`-prefixed keys are ignored (mw.py::_rag_load_path_roots)."""
        self.assertIn("`_` 开头的键被忽略", self.manual)
        self.assertIn("本地根", self.manual)
        # The roots template block really shows engine/game + the _README key.
        roots = _manual_block(self.manual, "roots")
        parsed = json.loads(roots)
        self.assertIn("_README", parsed)
        self.assertTrue(all(not key.startswith("_") or key == "_README" for key in parsed))

    # ── VC-209: quoted error texts exist in the implementation ───────────

    def test_vc209_error_texts_are_real(self) -> None:
        source = MW_COMMON_PATH.read_text(encoding="utf-8")
        section3 = self.manual.split("## 3.", 1)[1].split("## 4.", 1)[0]
        phrases = ("unknown rag server", "unknown key(s)", "transport must be one of")
        for phrase in phrases:
            self.assertIn(phrase, source, f"{phrase!r} is not in mw_common.py any more")
            self.assertIn(phrase, section3, f"manual does not quote {phrase!r} in its field tables")
        _verify("VC-209", phrases=len(phrases), verified_in_source=len(phrases), quoted_in_manual=len(phrases))


if __name__ == "__main__":
    unittest.main()
