import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { dispatchTask, type ImageCapabilityLookup } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function fixture(
	type: string,
	images = "yes",
): {
	store: WorkerStore;
	entry: Omit<WorkerEntry, "dispatchedAt" | "updatedAt">;
	queuePath: string;
} {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-t14-"));
	tempDirs.push(project);
	const agenticdoc = path.join(project, ".agenticdoc");
	const taskDir = path.join(agenticdoc, "fixture", "workers", "vision-task");
	fs.mkdirSync(taskDir, { recursive: true });
	const taskPath = path.join(taskDir, "task.md");
	fs.writeFileSync(
		taskPath,
		`type: ${type}\nimages: ${images}\nmodel: image-model\nwrite_face: packages/fixture/**\n\nfixture\n`,
		"utf8",
	);
	return {
		store: new WorkerStore(agenticdoc),
		entry: {
			taskKey: "vision-task",
			status: "pending",
			cli: "pi",
			provider: "faux",
			model: "faux/image-model",
			taskPath,
		},
		queuePath: path.join(agenticdoc, "_workers.parallel"),
	};
}

function fauxCapability(value: "yes" | "no" | "unknown"): ImageCapabilityLookup {
	return ({ model, provider, taskType, imagesRequired }) => {
		expect(model).toBe("image-model");
		expect(provider).toBe("faux");
		expect(taskType).toBe("vision");
		expect(imagesRequired).toBe(true);
		return value;
	};
}

describe("dp-w-type vision dispatch hard gate", () => {
	it("offers exactly the four consolidated business task types", () => {
		expect(DECIDE_REGISTRY["dp-w-type"].fixedChoiceIds).toEqual(["coding", "research", "review", "vision"]);
	});

	it("starts one vision worker only when image capability is proven", async () => {
		const { store, entry } = fixture("vision");
		expect(await dispatchTask(entry, store, { imageCapability: fauxCapability("yes") })).toEqual({ ok: true });
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["vision-task"]);
	});

	it.each(["no", "unknown"] as const)("does not start vision when capability is %s", async (capability) => {
		const { store, entry, queuePath } = fixture("vision");
		const outcome = await dispatchTask(entry, store, { imageCapability: fauxCapability(capability) });
		expect(outcome).toMatchObject({
			ok: false,
			code: "image-capability-unproven",
			capability,
		});
		expect(store.readAll()).toEqual([]);
		expect(fs.existsSync(queuePath)).toBe(false);
	});

	it("does not downgrade a refused vision dispatch to coding", async () => {
		const { store, entry } = fixture("vision");
		const outcome = await dispatchTask(entry, store, { imageCapability: fauxCapability("no") });
		expect(outcome.ok).toBe(false);
		expect(fs.readFileSync(entry.taskPath, "utf8")).toContain("type: vision");
		expect(store.readAll()).toEqual([]);
	});

	it("preserves existing framework task types outside the four-choice business menu", async () => {
		const { store, entry } = fixture("repair", "no");
		const lookup: ImageCapabilityLookup = () => {
			throw new Error("non-image task must not query image capability");
		};
		expect(await dispatchTask(entry, store, { imageCapability: lookup })).toEqual({ ok: true });
		expect(store.readAll()).toHaveLength(1);
	});

	it("rejects an unproven vision route when no running model registry supplied its capability", async () => {
		const { store, entry } = fixture("vision");
		fs.writeFileSync(entry.taskPath, "type: vision\nimages: yes\nmodel: codex/gpt-5.4\n\nfixture\n");
		expect(await dispatchTask(entry, store)).toMatchObject({ ok: false, capability: "unknown" });
		expect(store.readAll()).toEqual([]);
	});

	it("uses the launcher's fallback when another role invalidates the whole model configuration", async () => {
		const { store, entry } = fixture("vision");
		const controlRoot = path.dirname(path.dirname(store.queuePath));
		fs.mkdirSync(path.join(controlRoot, ".mw"), { recursive: true });
		fs.writeFileSync(entry.taskPath, "type: vision\nimages: yes\n\nfixture\n");
		fs.writeFileSync(
			path.join(controlRoot, ".mw/dispatch.yml"),
			"models:\n  vision: codex/image-model\n  spurious: broken\n",
		);
		fs.writeFileSync(path.join(controlRoot, ".mw/window-model"), "codex/text-model\n");
		const outcome = await dispatchTask(entry, store, {
			imageCapability: ({ model }) => (model === "codex/image-model" ? "yes" : "no"),
		});
		expect(outcome).toMatchObject({ ok: false, capability: "no" });
		expect(store.readAll()).toEqual([]);
	});

	it("uses the task model instead of the queue display label", async () => {
		const { store, entry } = fixture("vision");
		entry.model = "faux/text-only-label";
		const observed: string[] = [];
		const outcome = await dispatchTask(entry, store, {
			imageCapability: (facts) => {
				observed.push(facts.model);
				return facts.model === "image-model" ? "yes" : "no";
			},
		});
		expect(outcome).toEqual({ ok: true });
		expect(observed).toEqual(["image-model"]);
	});

	it("keeps the proven model when the role default changes before the launcher reads the card", async () => {
		const { store, entry } = fixture("vision");
		const project = path.dirname(path.dirname(store.queuePath));
		const config = path.join(project, ".mw/dispatch.yml");
		fs.mkdirSync(path.dirname(config), { recursive: true });
		fs.writeFileSync(config, "models:\n  vision: codex/image-model\n");
		fs.writeFileSync(entry.taskPath, "---\r\ntype: vision\r\nimages: yes\r\n---\r\n\r\nRead the reference.\r\n");
		const outcome = await dispatchTask(entry, store, {
			imageCapability: ({ model }) => {
				fs.writeFileSync(config, "models:\n  vision: codex/text-model\n");
				return model === "codex/image-model" ? "yes" : "no";
			},
		});
		expect(outcome.ok).toBe(true);
		expect(fs.readFileSync(entry.taskPath, "utf8")).toContain("model: codex/image-model\r\n");
	});

	it("does not authorize from a capable queue label when the task model is incapable", async () => {
		const { store, entry, queuePath } = fixture("vision");
		fs.writeFileSync(
			entry.taskPath,
			"type: vision\nimages: yes\nmodel: text-model\nwrite_face: packages/fixture/**\n\nfixture\n",
			"utf8",
		);
		entry.model = "faux/image-model";
		const observed: string[] = [];
		const outcome = await dispatchTask(entry, store, {
			imageCapability: (facts) => {
				observed.push(facts.model);
				return facts.model === "image-model" ? "yes" : "no";
			},
		});
		expect(outcome).toMatchObject({ ok: false, code: "image-capability-unproven", capability: "no" });
		expect(observed).toEqual(["text-model"]);
		expect(fs.existsSync(queuePath)).toBe(false);
	});
});
