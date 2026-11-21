import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import {
	resolveDispatchWorkspaceConfig,
	resolveWorkspaceConfig,
	TargetConfigError,
	targetYmlPath,
} from "../../src/extensions/agent-team-loop/shared/target-config.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const temporary: string[] = [];

beforeEach(() => {
	for (const name of ["MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"])
		vi.stubEnv(name, "");
});

afterEach(() => {
	vi.unstubAllEnvs();
	for (const root of temporary.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

function fixture() {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "workspace-dispatch-config-"));
	temporary.push(root);
	const control = path.join(root, "control");
	const agenticdoc = path.join(control, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const target = path.join(root, "target");
	const parent = path.join(root, "parent");
	for (const dir of [target, parent]) fs.mkdirSync(dir);
	return { root, control, agenticdoc, target, parent, store: new WorkerStore(agenticdoc) };
}

type Fixture = ReturnType<typeof fixture>;

function configure(fx: Fixture, mode: "single" | "dual" | "partition") {
	const config =
		mode === "single"
			? { active: mode }
			: mode === "dual"
				? { active: mode, dual: { game: fx.target } }
				: { active: mode, partition: { parent: fx.parent, partition: fx.target } };
	fs.writeFileSync(targetYmlPath(fx.control), JSON.stringify(config));
}

function task(fx: Fixture, name: string) {
	const taskPath = path.join(fx.agenticdoc, "config-gate", "workers", name, "task.md");
	fs.mkdirSync(path.dirname(taskPath), { recursive: true });
	fs.writeFileSync(taskPath, "type: coding\nwrite_face: src/a.cpp\n\nPreserve this task.\n");
	return { taskKey: name, status: "pending", cli: "pi", provider: "timi", model: "", taskPath } as const;
}

describe.each(["dual", "partition"] as const)("%s missing configuration dispatch", (mode) => {
	it("blocks first-time omission even when project instructions name the mode", async () => {
		const fx = fixture();
		fs.writeFileSync(path.join(fx.control, "AGENTS.md"), `Workspace mode: ${mode}\n`);
		const entry = task(fx, "first");
		const original = fs.readFileSync(entry.taskPath);
		await expect(dispatchTask(entry, fx.store)).rejects.toThrow("target-config-required");
		expect(fs.readFileSync(entry.taskPath)).toEqual(original);
		expect(fs.existsSync(fx.store.queuePath)).toBe(false);
		expect(fs.existsSync(fx.store.lockFilePath)).toBe(false);
		process.stdout.write(`[VERIFY] VC-001: ${mode} first-missing=blocked side-effects=0\n`);
	});

	it("blocks a second dispatch after configured target.yml is deleted", async () => {
		const fx = fixture();
		configure(fx, mode);
		const previous = task(fx, "previous");
		expect(await dispatchTask(previous, fx.store)).toEqual({ ok: true });
		const previousBytes = fs.readFileSync(previous.taskPath);
		const entry = task(fx, "next");
		const original = fs.readFileSync(entry.taskPath);
		const queue = fs.readFileSync(fx.store.queuePath);
		fs.unlinkSync(targetYmlPath(fx.control));
		await expect(dispatchTask(entry, fx.store)).rejects.toThrow("target-config-required");
		expect(fs.readFileSync(entry.taskPath)).toEqual(original);
		expect(fs.readFileSync(previous.taskPath)).toEqual(previousBytes);
		expect(fs.readFileSync(fx.store.queuePath)).toEqual(queue);
		expect(fs.existsSync(fx.store.lockFilePath)).toBe(false);
		process.stdout.write(`[VERIFY] VC-001: ${mode} deleted-config=blocked side-effects=0\n`);
	});

	it.each(["delete", "switch"] as const)("blocks configuration %s during vision verification", async (mutation) => {
		const fx = fixture();
		configure(fx, mode);
		const entry = task(fx, "vision");
		fs.writeFileSync(entry.taskPath, "type: vision\nimages: yes\nmodel: image-model\n\nRead the reference.\n");
		const original = fs.readFileSync(entry.taskPath);
		let verified = false;
		const result = dispatchTask(entry, fx.store, {
			imageCapability: () => {
				verified = true;
				if (mutation === "delete") fs.unlinkSync(targetYmlPath(fx.control));
				else configure(fx, "single");
				return "yes";
			},
		});
		await expect(result).rejects.toThrow(mutation === "delete" ? "target-config-required" : "target-config-changed");
		expect(verified).toBe(true);
		expect(fs.readFileSync(entry.taskPath)).toEqual(original);
		expect(fs.existsSync(fx.store.queuePath)).toBe(false);
		expect(fs.existsSync(fx.store.lockFilePath)).toBe(false);
		process.stdout.write(`[VERIFY] VC-001: ${mode} vision-${mutation}=blocked side-effects=0\n`);
	});
});

describe("explicit workspace dispatch configuration", () => {
	it.each([undefined, "", " \n\t", "\uFEFF", "{}\n", "vcs: git\n", "toolchain: {}\n"])(
		"rejects implicit default from %j with actionable diagnostics",
		async (contents) => {
			const fx = fixture();
			if (contents !== undefined) fs.writeFileSync(targetYmlPath(fx.control), contents);
			const entry = task(fx, "implicit");
			const original = fs.readFileSync(entry.taskPath);
			const rejection = dispatchTask(entry, fx.store);
			await expect(rejection).rejects.toBeInstanceOf(TargetConfigError);
			for (const detail of [
				"target-config-required",
				fs.realpathSync.native(fx.control),
				targetYmlPath(fx.control),
				"mode=single source=default",
				"active: single",
				"active: dual",
				"active: partition",
			])
				await expect(rejection).rejects.toThrow(detail);
			expect(fs.readFileSync(entry.taskPath)).toEqual(original);
			expect(fs.existsSync(fx.store.queuePath)).toBe(false);
			process.stdout.write("[VERIFY] VC-002: implicit-default=blocked diagnostics=complete\n");
		},
	);

	it.each(["# workspace config pending\n", "null\n", "active: dual\n", "active: partition\n", "active: [bad\n"])(
		"retains fail-closed parsing for %j",
		async (contents) => {
			const fx = fixture();
			fs.writeFileSync(targetYmlPath(fx.control), contents);
			const entry = task(fx, "invalid");
			const original = fs.readFileSync(entry.taskPath);
			await expect(dispatchTask(entry, fx.store)).rejects.toBeInstanceOf(TargetConfigError);
			expect(fs.readFileSync(entry.taskPath)).toEqual(original);
			expect(fs.existsSync(fx.store.queuePath)).toBe(false);
		},
	);

	it.each(["single", "dual", "partition"] as const)("accepts explicitly configured %s", async (mode) => {
		const fx = fixture();
		configure(fx, mode);
		const entry = task(fx, mode);
		expect(await dispatchTask(entry, fx.store)).toEqual({ ok: true });
		expect(fx.store.findByKey(mode)?.taskPath).toBe(entry.taskPath);
		const contents = fs.readFileSync(entry.taskPath, "utf8");
		if (mode === "dual") expect(contents).toContain(`Game root: ${fs.realpathSync.native(fx.target)}`);
		if (mode === "partition")
			expect(contents).toContain(`Partition root (worker cwd): ${fs.realpathSync.native(fx.target)}`);
		process.stdout.write(`[VERIFY] VC-003: explicit-${mode}=queued\n`);
	});

	it("accepts explicit legacy single mode", async () => {
		const fx = fixture();
		fs.writeFileSync(targetYmlPath(fx.control), "mode: single\n");
		expect(await dispatchTask(task(fx, "legacy-single"), fx.store)).toEqual({ ok: true });
	});

	it.each(["dual", "partition"] as const)("accepts complete %s environment activation", async (mode) => {
		const fx = fixture();
		if (mode === "dual") vi.stubEnv("MW_TARGET_GAME", fx.target);
		else {
			vi.stubEnv("MW_PARTITION_PARENT", fx.parent);
			vi.stubEnv("MW_PARTITION_ROOT", fx.target);
		}
		expect(resolveDispatchWorkspaceConfig(fx.control)).toMatchObject({ mode, source: "env" });
		expect(await dispatchTask(task(fx, "environment"), fx.store)).toEqual({ ok: true });
		process.stdout.write(`[VERIFY] VC-003: ${mode}-env=queued\n`);
	});

	it.each(["MW_PARTITION_PARENT", "MW_PARTITION_ROOT", "MW_TARGET_ENGINE"])(
		"rejects incomplete activation through %s",
		async (name) => {
			const fx = fixture();
			vi.stubEnv(name, fx.target);
			const entry = task(fx, "incomplete");
			await expect(dispatchTask(entry, fx.store)).rejects.toBeInstanceOf(TargetConfigError);
			expect(fs.existsSync(fx.store.queuePath)).toBe(false);
		},
	);

	it("keeps the ordinary no-config query single/default without granting dispatch", () => {
		const fx = fixture();
		expect(resolveWorkspaceConfig(fx.control)).toMatchObject({ mode: "single", source: "default" });
		expect(() => resolveDispatchWorkspaceConfig(fx.control)).toThrow("target-config-required");
		expect(fs.existsSync(targetYmlPath(fx.control))).toBe(false);
		process.stdout.write("[VERIFY] VC-004: query-default=preserved\n");
	});

	it("uses the task's own profile when its control root differs from the queue root", async () => {
		const queue = fixture();
		const owner = fixture();
		configure(queue, "dual");
		configure(owner, "dual");
		const entry = task(owner, "separate-owner");
		expect(await dispatchTask(entry, queue.store)).toEqual({ ok: true });
		const contents = fs.readFileSync(entry.taskPath, "utf8");
		expect(contents).toContain(`Game root: ${fs.realpathSync.native(owner.target)}`);
		expect(contents).not.toContain(`Game root: ${fs.realpathSync.native(queue.target)}`);
	});
});
