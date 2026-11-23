import * as fs from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, expect, it, vi } from "vitest";
import { emitSessionShutdownEvent } from "../../src/core/extensions/runner.ts";
import { PARALLEL_PROTOCOL, pmActivate } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { WATCH_ENTRY_TYPE } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { appendKeyGoal } from "../../src/extensions/agent-team-loop/shared/key-goal.ts";
import { readRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const goalA = "Deliver Alpha. The project gains a verified Alpha path.";
const goalB = "Deliver Beta. The project gains a verified Beta path.";
const marker = "## [mw] Current key goal";
const harnesses: Harness[] = [];
const roots: string[] = [];

function write(file: string, text: string): void {
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(file, text);
}

function project(): string {
	const root = fs.mkdtempSync(path.join(tmpdir(), "mw-key-spec-goal-"));
	roots.push(root);
	// A live process in the isolated fixture keeps PM startup from launching a service.
	write(path.join(root, ".mw", "mw.pid"), String(process.pid));
	return root;
}

function spec(goal: string): string {
	return `# Specification\n\n## §0 Goal Alignment\n\n### spec_goal\n\n${goal}\n\n### Constraints\n\nInternal details.\n`;
}

async function closeHarness(harness: Harness): Promise<void> {
	await emitSessionShutdownEvent(harness.session.extensionRunner, { type: "session_shutdown", reason: "quit" });
	harness.cleanup();
}

afterEach(async () => {
	for (const harness of harnesses.splice(0)) await closeHarness(harness);
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
	vi.unstubAllEnvs();
	vi.restoreAllMocks();
});

async function capturePrompt(harness: Harness): Promise<string> {
	let systemPrompt: string | undefined;
	harness.setResponses([
		(context) => {
			systemPrompt = context.systemPrompt;
			return fauxAssistantMessage("Done.");
		},
	]);
	await harness.session.prompt("Continue the current work.");
	expect(systemPrompt).toBeDefined();
	return systemPrompt ?? "";
}

it("reads only the goal of the selected workflow and preserves it across a replan", () => {
	const docRoot = path.join(project(), ".agenticdoc");
	const keyDir = path.join(docRoot, "alpha");
	const specFile = path.join(keyDir, "spec.md");
	write(specFile, `# Example\n\n~~~markdown\n${spec("Example goal.")}\n~~~\n\n${spec(goalA)}`.replace(/\n/g, "\r\n"));
	const before = appendKeyGoal("Base", docRoot, "alpha");
	expect(before).toBe(`Base\n\n${marker} (alpha)\n\n${goalA}`);
	expect(appendKeyGoal(before, docRoot, "alpha")).toBe(before);

	fs.mkdirSync(path.join(keyDir, "evidence", "replan"), { recursive: true });
	fs.renameSync(specFile, path.join(keyDir, "evidence", "replan", "spec.md"));
	write(specFile, spec(goalA).replace("Internal details.", "Revised design reference."));
	write(path.join(keyDir, "plan.md"), "Reorder implementation.");
	expect(appendKeyGoal("Base", docRoot, "alpha")).toBe(before);

	write(
		path.join(keyDir, "codex_doc.md"),
		`# Record\n\n- Workflow: codex-lite\n\n## 目标\n\n<!-- template -->\n\n${goalB}\n\n## 接续须知\n\nPM data.\n`,
	);
	expect(appendKeyGoal("Base", docRoot, "alpha")).toBe(`Base\n\n${marker} (alpha)\n\n${goalB}`);
});

it("omits the goal on a legacy, unrelated, or unbound key", () => {
	const docRoot = path.join(project(), ".agenticdoc");
	write(path.join(docRoot, "legacy", "spec.md"), "## §0 Goal Alignment\n\nExisting scope.\n");
	write(path.join(docRoot, "other", "spec.md"), "## Details\n\n### spec_goal\n\nWrong section.\n");
	write(path.join(docRoot, "_scratch", "spec.md"), spec(goalA));
	write(path.join(docRoot, "blank", "spec.md"), spec("<!-- Write a goal. -->"));
	for (const key of ["legacy", "other", "_scratch", "blank", "missing", undefined]) {
		expect(appendKeyGoal("Base", docRoot, key)).toBe("Base");
	}
});

it("sends one stable PM goal through tool continuations, compaction, and watch restoration", async () => {
	const root = project();
	const docRoot = path.join(root, ".agenticdoc");
	write(path.join(docRoot, "alpha", "spec.md"), spec(goalA));
	write(path.join(docRoot, "beta", "spec.md"), spec(goalB));
	const startPm = async () => {
		const harness = await createHarness({
			initialActiveToolNames: ["switch_key"],
			settings: { compaction: { keepRecentTokens: 1 } },
			extensionFactories: [(pi) => pmActivate(pi, root)],
		});
		harnesses.push(harness);
		return harness;
	};
	const harness = await startPm();
	await harness.session.bindExtensions({});
	for (const key of ["alpha", "beta"]) {
		const previous = await capturePrompt(harness);
		const requests: Array<string | undefined> = [];
		harness.setResponses([
			(context) => {
				requests.push(context.systemPrompt);
				return fauxAssistantMessage(fauxToolCall("switch_key", { key }), { stopReason: "toolUse" });
			},
			(context) => {
				requests.push(context.systemPrompt);
				return fauxAssistantMessage("Switched.");
			},
		]);
		await harness.session.prompt(`Switch to ${key}.`);
		expect(requests).toEqual([previous, previous]);
		const current = await capturePrompt(harness);
		expect(current.split(marker)).toHaveLength(2);
		expect(current).toContain(PARALLEL_PROTOCOL);
		expect(current).toMatch(key === "alpha" ? /Deliver Alpha/ : /Deliver Beta/);
		expect(current).not.toContain(key === "alpha" ? goalB : goalA);
		if (key === "alpha") {
			write(path.join(docRoot, key, "plan.md"), "New order. Same goal.");
			write(path.join(docRoot, key, "pm-state.md"), "- Phase: spec\n\nProgress changed.");
			harness.setResponses([
				fauxAssistantMessage("Compacted work history."),
				fauxAssistantMessage("Compacted current turn prefix."),
			]);
			await harness.session.compact();
			expect(harness.sessionManager.getEntries().some((entry) => entry.type === "compaction")).toBe(true);
			expect(await capturePrompt(harness)).toBe(current);
		}
	}
	const beforeRestart = await capturePrompt(harness);
	const watch = harness.sessionManager
		.getEntries()
		.filter((entry) => entry.type === "custom" && entry.customType === WATCH_ENTRY_TYPE)
		.at(-1);
	if (watch?.type !== "custom") throw new Error("PM did not persist a watch entry");
	await closeHarness(harness);
	harnesses.splice(harnesses.indexOf(harness), 1);

	const restarted = await startPm();
	restarted.sessionManager.appendCustomEntry(watch.customType, watch.data);
	await restarted.session.bindExtensions({});
	const restored = await capturePrompt(restarted);
	// The harness gives each session its own cwd in the base system prompt.
	expect(restored.split(PARALLEL_PROTOCOL)[1]).toBe(beforeRestart.split(PARALLEL_PROTOCOL)[1]);
	expect(restored).toContain(goalB);
	expect(restored).not.toContain(goalA);

	const index = new IndexStore(docRoot);
	const row = index.readAll().find((entry) => entry.key === "beta");
	if (!row) throw new Error("PM did not claim beta");
	await index.upsert({ ...row, status: "idle", claimId: "—" });
	const afterRelease = await capturePrompt(restarted);
	expect(afterRelease).toContain(PARALLEL_PROTOCOL);
	expect(afterRelease).not.toContain(marker);
});

it("binds a Worker and its continuation to their owning lite key and preserves the card's write boundary", async () => {
	const root = project();
	const docRoot = path.join(root, ".agenticdoc");
	write(path.join(docRoot, "alpha", "spec.md"), spec(goalA));
	write(
		path.join(docRoot, "beta", "codex_doc.md"),
		`# Record\n\n- Workflow: codex-lite\n\n## 目标\n\n${goalB}\n\n## 接续须知\n\nPM data.\n`,
	);
	const exitListeners = new Set(process.listeners("exit"));
	const initialExitCode = process.exitCode;
	vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
	const forbidden = path.join(root, "outside-card.txt");
	const requests: Array<string | undefined> = [];
	let parentRun: string | undefined;
	try {
		for (const task of ["original", "continuation"]) {
			const file = path.join(docRoot, "beta", "workers", task, "task.md");
			write(
				file,
				"type: coding\nwrite_face: allowed.txt\nwrite_scope: allowed.txt\n" +
					(parentRun ? `parent_worker_run: ${parentRun}\n` : "") +
					"\nCarry out the card.\n",
			);
			vi.stubEnv("PI_WORKER_TASK", file);
			const harness = await createHarness({
				initialActiveToolNames: ["write"],
				extensionFactories: [(pi) => workerModeActivate(pi)],
			});
			harnesses.push(harness);
			await harness.session.bindExtensions({});
			harness.setResponses([
				(context) => {
					requests.push(context.systemPrompt);
					return fauxAssistantMessage(fauxToolCall("write", { path: forbidden, content: "outside" }), {
						stopReason: "toolUse",
					});
				},
				(context) => {
					requests.push(context.systemPrompt);
					return fauxAssistantMessage("The card leaves this path out of scope.");
				},
			]);
			await harness.session.prompt("Proceed with the card.");
			const result = harness.session.messages.find((message) => message.role === "toolResult");
			expect(getMessageText(result)).toMatch(/write.?scope|write.?face|outside.*allowed|outside.*scope/i);
			expect(fs.existsSync(forbidden)).toBe(false);
			const run = readRunState(path.dirname(file));
			expect(run?.parent_worker_run).toBe(parentRun);
			expect(run?.run_id).toBeDefined();
			parentRun = run?.run_id;
		}
	} finally {
		for (const listener of process.listeners("exit")) {
			if (!exitListeners.has(listener)) process.off("exit", listener);
		}
		process.exitCode = initialExitCode;
	}
	expect(requests).toHaveLength(4);
	for (const request of requests) {
		expect(request?.split(marker)).toHaveLength(2);
		expect(request).toContain(goalB);
		expect(request).not.toContain(goalA);
		expect(request).not.toContain("PM data.");
	}
	expect(requests[1]).toBe(requests[0]);
	expect(requests[3]).toBe(requests[2]);
});
