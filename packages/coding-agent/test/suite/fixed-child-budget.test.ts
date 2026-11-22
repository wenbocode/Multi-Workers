import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { expect, it } from "vitest";
import { cardDigest } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import { allocationFile, openFixedAllocation } from "../../src/extensions/agent-team-loop/shared/fixed-child-budget.ts";
import { checkBashWriteScopeTarget } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

it("binds the fixed allowance to the judged card and consumes the launch once across task directory recreation", () => {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "fixed-child-"));
	try {
		const key = path.join(root, ".agenticdoc", "owner");
		const task = path.join(key, "workers", "child");
		fs.mkdirSync(task, { recursive: true });
		fs.mkdirSync(path.join(key, "tasks"));
		const card = path.join(key, "tasks", "child.md");
		fs.writeFileSync(card, "- `parent_matter_ref`: `parent`\n");
		const pin = cardDigest(card);
		const deadline = new Date(Date.now() + 60_000).toISOString();
		const envelope = `card_path: tasks/child.md\ncard_sha256: ${pin}\n`;
		const fixed = `fixed_child_steps: 2\nfixed_child_deadline: ${deadline}\n${envelope}`;
		const blocked = { steps: 0, deadline: 0 };
		expect(openFixedAllocation(task, envelope)).toEqual(blocked);
		const target = allocationFile(task);
		expect(target).toBe(path.join(root, ".agenticdoc", "_runtime", "fixed-child-budgets", "owner", "child.json"));
		fs.mkdirSync(path.dirname(target), { recursive: true });
		fs.writeFileSync(target, JSON.stringify({ task: "child", card: "tasks/child.md", pin, steps: 2, deadline }));
		for (const tool of ["bash", "write", "edit"] as const) {
			const verdict = checkBashWriteScopeTarget(
				{
					projectRoot: root,
					taskDir: task,
					keyDir: key,
					trueRoot: path.dirname(key),
					writeScope: ["**"],
					roleClass: "writable",
				},
				target,
				true,
				tool,
			);
			expect(verdict.allowed).toBe(false);
		}
		expect(openFixedAllocation(task, envelope)).toEqual(blocked);
		expect(openFixedAllocation(task, fixed.replace("steps: 2", "steps: 9"))).toEqual(blocked);
		expect(openFixedAllocation(task, fixed)).toEqual({ steps: 2, deadline: Date.parse(deadline) });
		fs.rmdirSync(task);
		fs.mkdirSync(task);
		expect(openFixedAllocation(task, fixed)).toEqual({ ...blocked, alreadyStarted: true });
		fs.writeFileSync(card, "changed");
		expect(openFixedAllocation(task, envelope)).toMatchObject(blocked);
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
});
