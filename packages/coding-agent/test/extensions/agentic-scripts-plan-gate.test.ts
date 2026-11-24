import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { inspectPlanGate } from "../../src/extensions/agent-team-loop/shared/agentic-scripts.ts";

const roots: string[] = [];

function installation(imports: string, call = "plan_closure_problems", register = true): string {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-plan-capability-"));
	roots.push(root);
	const scripts = path.join(root, ".claude", "scripts");
	fs.mkdirSync(scripts, { recursive: true });
	fs.writeFileSync(path.join(scripts, "plan_closure.py"), "def problems(key):\n    return []\n");
	fs.writeFileSync(
		path.join(scripts, "advance_phase.py"),
		[
			imports,
			`GATES = {"tasks": [("plan.md", "${register ? "plan_closure" : "file_min_bytes"}", None, "check")]}`,
			"def check_gate(key):",
			`    return ${call}(key)`,
			"raise RuntimeError('capability inspection must never execute this module')",
		].join("\n"),
	);
	return root;
}

afterEach(() => {
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe("AgenticTask PLAN → TASKS capability", () => {
	it.each([
		"from plan_closure import problems as plan_closure_problems",
		"from plan_closure import _AC, _defined_ids, problems as plan_closure_problems",
		"from plan_closure import problems as plan_closure_problems, _AC, _defined_ids",
		"from plan_closure import (\n    _AC,\n    problems as plan_closure_problems,\n    _defined_ids,\n)",
		"from plan_closure import (\n    _AC, # definition matcher\n    problems as plan_closure_problems, # gate\n)",
		"from plan_closure import (\n    _AC, # helper (not the closing bracket)\n    problems as plan_closure_problems,\n)",
	])("recognizes a registered gate with %s without running Python", (imports) => {
		const root = installation(imports);
		expect(inspectPlanGate(root)).toEqual({
			ok: true,
			output: path.join(root, ".claude", "scripts", "advance_phase.py"),
		});
	});

	it("recognizes an unaliased problems import alongside other names", () => {
		const root = installation("from plan_closure import _AC, problems, _defined_ids", "problems");
		expect(inspectPlanGate(root).ok).toBe(true);
	});

	it.each([
		"from plan_closure import _AC, _defined_ids",
		"from plan_closure import other_problems as plan_closure_problems",
		"from another_module import problems as plan_closure_problems",
		"# from plan_closure import problems as plan_closure_problems",
	])("refuses an absent problems binding: %s", (imports) => {
		expect(inspectPlanGate(installation(imports)).ok).toBe(false);
	});

	it("refuses an imported but uncalled gate", () => {
		const root = installation("from plan_closure import _AC, problems as plan_closure_problems", "other_check");
		expect(inspectPlanGate(root).ok).toBe(false);
	});

	it("does not count a commented-out call as a gate invocation", () => {
		const root = installation(
			"from plan_closure import problems as plan_closure_problems\n# plan_closure_problems(key)",
			"other_check",
		);
		expect(inspectPlanGate(root).ok).toBe(false);
	});

	it("does not count a commented-out registration", () => {
		const root = installation("from plan_closure import problems as plan_closure_problems");
		const script = path.join(root, ".claude", "scripts", "advance_phase.py");
		fs.writeFileSync(script, fs.readFileSync(script, "utf8").replace("GATES =", "# GATES ="));
		expect(inspectPlanGate(root).ok).toBe(false);
	});

	it("refuses a missing PLAN → TASKS registration", () => {
		const root = installation("from plan_closure import problems as plan_closure_problems", undefined, false);
		expect(inspectPlanGate(root).ok).toBe(false);
	});

	it("refuses a missing closure script and preserves the actionable warning", () => {
		const root = installation("from plan_closure import problems as plan_closure_problems");
		fs.unlinkSync(path.join(root, ".claude", "scripts", "plan_closure.py"));
		expect(inspectPlanGate(root)).toMatchObject({ ok: false });
		expect(inspectPlanGate(root).output).toContain("PLAN → TASKS gate unavailable");
	});
});
