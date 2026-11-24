"""Module-spec gap checks for the UE frame install contract (T-01/AC-002/AC-003)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MW = Path(__file__).resolve().parent
sys.path.insert(0, str(MW))
import mw  # noqa: E402

TERMS_HEADER = "term_id,term,alias,definition,unit,owner,path,symbol,ast_id\n"
TERMS_FRAMEWORK = TERMS_HEADER + "T-ASK,query,,framework self check,,query,agent/ask.py,query,agent/ask.py#FunctionDef:query\n"
TERMS_MODULE = TERMS_FRAMEWORK + "T-EXEC,execute,,Increment one value,,execute,Source/Logic.cpp,execute,Source/Logic.cpp#FunctionDef:execute\n"
TESTCASE_HEADER = "case_id,term_id,name,path,preconditions,steps,expected,command,status,decision_ref\n"
TESTCASE_ROW = TESTCASE_HEADER + "C-SMOKE,T-EXEC,Plugin.Smoke,Source/Test.cpp,fixture,run,true,Automation RunTests Plugin.Smoke,proposed,\n"
GATES_HEADER = "gate_id,term_id,requirement,case_id,selection,trigger,runner,args,artifacts,status,decision_ref\n"
GATES_ROW = GATES_HEADER + "G-EXEC,T-EXEC,Smoke stays green,,always,logic change,agent/gates/check.py,[],exit code,proposed,\n"


class GapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "agent").mkdir()
        self.write_config("draft")
        self.write_text("agent/terms.csv", TERMS_FRAMEWORK)
        self.write_text("agent/testcase.csv", TESTCASE_HEADER)
        self.write_text("agent/gates.csv", GATES_HEADER)
        self.write_text("DESIGN.md", "# Plugin 设计（草稿）\n")

    def write_text(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8-sig" if name.endswith(".csv") else "utf-8")

    def write_config(self, status):
        config = {"schema_version": 1, "module": "Plugin", "source_roots": ["Source"], "design_status": status}
        self.write_text("agent/module.json", json.dumps(config))

    def test_framework_only_draft_reports_every_gap(self):
        gaps = mw._ue_frame_gaps(self.root)
        self.assertTrue(any("Source" in gap for gap in gaps), gaps)
        self.assertTrue(any("testcase.csv" in gap for gap in gaps), gaps)
        self.assertTrue(any("gates.csv" in gap for gap in gaps), gaps)
        self.assertTrue(any("design_status" in gap for gap in gaps), gaps)
        self.assertTrue(any("DESIGN.md" in gap for gap in gaps), gaps)

    def test_complete_module_spec_has_no_gap(self):
        self.write_config("ready")
        self.write_text("agent/terms.csv", TERMS_MODULE)
        self.write_text("agent/testcase.csv", TESTCASE_ROW)
        self.write_text("agent/gates.csv", GATES_ROW)
        self.write_text("DESIGN.md", "# Plugin 设计\n\n## 主要 Flow\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
        self.assertEqual(mw._ue_frame_gaps(self.root), [])

    def test_module_terms_with_draft_design_still_gap(self):
        self.write_text("agent/terms.csv", TERMS_MODULE)
        self.write_text("agent/testcase.csv", TESTCASE_ROW)
        self.write_text("agent/gates.csv", GATES_ROW)
        gaps = mw._ue_frame_gaps(self.root)
        self.assertFalse(any("terms.csv" in gap for gap in gaps), gaps)
        self.assertTrue(any("design_status" in gap for gap in gaps), gaps)
        self.assertTrue(any("DESIGN.md" in gap for gap in gaps), gaps)

    def test_counts_read_generated_catalogs(self):
        self.write_text("agent/terms.csv", TERMS_MODULE)
        self.write_text("agent/testcase.csv", TESTCASE_ROW)
        self.write_text("agent/gates.csv", GATES_ROW)
        self.assertEqual(mw._ue_frame_counts(self.root), {"terms": 2, "testcases": 1, "gates": 1})

    def test_missing_module_json_is_a_gap(self):
        (self.root / "agent/module.json").unlink()
        self.assertTrue(any("module.json" in gap for gap in mw._ue_frame_gaps(self.root)))


UE_CPP = '''#include "CoreMinimal.h"
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FMyPluginSmoke, "MyPlugin.Smoke", 0)
bool FMyPluginSmoke::RunTest(const FString&) { return true; }
int Execute(int Value) { return Value + 1; }
'''


def _needs_tree_sitter():
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_cpp  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("tree-sitter-cpp not installed (agent/requirements-source.txt)")


class CliContractTests(unittest.TestCase):
    """AC-001/002/003/AC-004 against the real CLI and a disposable dual project."""

    def setUp(self):
        _needs_tree_sitter()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.control = base / "ctrl"
        self.game = base / "game"
        self.plugin = self.game / "Plugins/MyPlugin"
        (self.control / ".agenticdoc").mkdir(parents=True)
        (base / "engine").mkdir()
        (self.plugin / "Source").mkdir(parents=True)
        (self.plugin / "MyPlugin.uplugin").write_text('{"FileVersion": 3}\n', encoding="utf-8")
        (self.plugin / "Source/Logic.cpp").write_text(UE_CPP, encoding="utf-8")
        (self.control / ".agenticdoc/target.yml").write_text(
            "active: dual\n"
            f"dual:\n  game: {self.game.as_posix()}\n  engine: {(base / 'engine').as_posix()}\n",
            encoding="utf-8",
        )

    def run_mw(self, *args):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(MW / "mw.py"), "ue-continue-develop-frame", *args,
             "--project", str(self.control)],
            capture_output=True, encoding="utf-8", cwd=str(self.control),
        )

    def test_invalid_targets_write_nothing(self):
        for args in (("install",), ("install", "--module", "Plugins/Missing"),
                     ("install", "--module", "Plugins/MyPlugin/Source"),
                     ("verify", "--module", "Plugins/MyPlugin")):
            result = self.run_mw(*args)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse((self.plugin / "agent").exists())
        self.assertFalse((self.game / "Plugins/ue-continue-develop-frame").exists())
        self.assertFalse((self.plugin / "GOAL.md").exists())

    def test_install_reports_draft_then_verify_passes_after_generation(self):
        result = self.run_mw("install", "--module", "Plugins/MyPlugin")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("模块规范尚未针对该插件生成", result.stdout)
        self.assertNotIn("完整规范包检查通过", result.stdout)
        self.assertTrue((self.plugin / "agent/terms.csv").is_file())

        self.generate_plugin_spec()
        terms = (self.plugin / "agent/terms.csv").read_bytes()
        design = (self.plugin / "DESIGN.md").read_bytes()
        repeated = self.run_mw("install", "--module", "Plugins/MyPlugin")
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual((self.plugin / "agent/terms.csv").read_bytes(), terms)
        self.assertEqual((self.plugin / "DESIGN.md").read_bytes(), design)

        verified = self.run_mw("verify", "--module", "Plugins/MyPlugin")
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertIn("terms", verified.stdout)
        self.assertIn("REVIEW.md", verified.stdout)

    def generate_plugin_spec(self):
        catalog_path = self.plugin / "agent/catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        catalog["terms"].append({"term_id": "T-EXEC", "path": "Source/Logic.cpp", "symbol": "Execute",
                                 "definition": "Increment one value", "unit": ""})
        catalog["testcases"].append({"case_id": "C-SMOKE", "term_id": "T-EXEC", "name": "MyPlugin.Smoke",
                                     "path": "Source/Logic.cpp", "preconditions": "fixture",
                                     "steps": "run Execute(1)", "expected": "2",
                                     "command": "Automation RunTests MyPlugin.Smoke"})
        catalog["gates"].append({"gate_id": "G-EXEC", "term_id": "T-EXEC", "requirement": "Execute(1) stays 2",
                                 "case_id": "C-SMOKE", "selection": "conditional", "trigger": "logic change",
                                 "runner": "agent/gates/check_logic.py", "args": "[]", "artifacts": "exit code"})
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (self.plugin / "agent/gates/check_logic.py").write_text("print('PASS')\n", encoding="utf-8")
        config_path = self.plugin / "agent/module.json"
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        config["design_status"] = "ready"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        design_path = self.plugin / "DESIGN.md"
        design = design_path.read_text(encoding="utf-8")
        design = design.replace("（草稿）", "").replace("## 主要 Flow", "[T-EXEC] [N:Execute]\n\n## 主要 Flow")
        design = design.replace("## 生命周期", "[N:Execute]\n\n## 生命周期")
        design_path.write_text(design, encoding="utf-8")
        written = subprocess.run([sys.executable, "-B", str(self.plugin / "agent/catalog.py"), "--write"],
                                 capture_output=True, encoding="utf-8", cwd=str(self.plugin))
        self.assertEqual(written.returncode, 0, written.stdout + written.stderr)


if __name__ == "__main__":
    unittest.main()
