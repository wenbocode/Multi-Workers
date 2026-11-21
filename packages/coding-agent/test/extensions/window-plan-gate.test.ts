import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, expect, it } from "vitest";
import { inspectPlanGate, runAgenticScript } from "../../src/extensions/agent-team-loop/shared/agentic-scripts.ts";

const roots: string[] = [];
afterEach(() => {
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});
it("checks the effective installation even with a newer fallback and an obsolete mirror", () => {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "window-gate-"));
	roots.push(root);
	const mirror = path.join(root, ".claude", "scripts");
	const clone = path.join(root, ".agents", "skills", "agentic-task", "claude", "scripts");
	for (const dir of [mirror, clone]) fs.mkdirSync(dir, { recursive: true });
	const wired = `from plan_closure import problems as verify_plan
GATES = {"tasks": [("plan.md", "plan_closure", None, "plan")]}
def check_gate(key, target):
    return verify_plan(key)
`;
	fs.writeFileSync(path.join(clone, "advance_phase.py"), wired);
	fs.writeFileSync(path.join(clone, "plan_closure.py"), "def problems(key): return []");
	expect(inspectPlanGate(root)).toEqual({ ok: true, output: path.join(clone, "advance_phase.py") });
	fs.writeFileSync(path.join(mirror, "advance_phase.py"), "# old");
	expect(inspectPlanGate(root)).toMatchObject({ ok: false, output: expect.stringContaining(mirror) });
	fs.copyFileSync(path.join(clone, "plan_closure.py"), path.join(mirror, "plan_closure.py"));
	expect(runAgenticScript(root, "advance_phase.py", ["fixture", "tasks"])).toMatchObject({
		ok: false,
		output: expect.stringContaining(mirror),
	});
	fs.writeFileSync(path.join(mirror, "advance_phase.py"), wired);
	expect(inspectPlanGate(root)).toEqual({ ok: true, output: path.join(mirror, "advance_phase.py") });
});
