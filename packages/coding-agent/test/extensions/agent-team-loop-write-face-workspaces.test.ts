import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { parseWriteFaceEntries, writeFacesOverlap } from "../../src/extensions/agent-team-loop/shared/write-face.ts";
import { parseTaskMd, workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const KEY = "workspace-face";
const temporary: string[] = [];
const cwd = process.cwd();
const exitListeners = new Set(process.listeners("exit"));

afterEach(() => {
	process.chdir(cwd);
	vi.unstubAllEnvs();
	for (const listener of process.listeners("exit")) {
		if (!exitListeners.has(listener)) process.removeListener("exit", listener);
	}
	for (const dir of temporary.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function fixture(mode: "dual" | "partition") {
	for (const name of ["MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"])
		vi.stubEnv(name, "");
	const top = fs.mkdtempSync(path.join(os.tmpdir(), "mw-rooted-face-"));
	temporary.push(top);
	const control = path.join(top, "control");
	const target = path.join(top, "target");
	const extra = path.join(top, "extra");
	const named = path.join(top, "sdk");
	for (const root of [control, target, extra, named]) fs.mkdirSync(root);
	const agenticdoc = path.join(control, ".agenticdoc");
	fs.mkdirSync(agenticdoc);
	const config =
		mode === "dual"
			? { mode, game: target, engine: extra }
			: { active: mode, partition: { parent: extra, partition: target, roots: { sdk: named } } };
	fs.writeFileSync(path.join(agenticdoc, "target.yml"), JSON.stringify(config));
	return { top, control, target, extra, named, agenticdoc };
}

type Fixture = ReturnType<typeof fixture>;

function task(fx: Fixture, name: string, entries: string[] | undefined, extra: string[] = [], type = "coding") {
	const dir = path.join(fx.agenticdoc, KEY, "workers", name);
	fs.mkdirSync(dir, { recursive: true });
	const taskPath = path.join(dir, "task.md");
	fs.writeFileSync(
		taskPath,
		[
			"---",
			`type: ${type}`,
			"card_path: tasks/test.md",
			...extra,
			...(entries === undefined ? [] : ["write_face:", ...entries.map((entry) => `  - ${entry}`)]),
			"---",
			"Do the task.",
		].join("\n"),
	);
	return taskPath;
}

async function worker(taskPath: string, target: string) {
	const handlers = new Map<string, Array<(event: unknown) => unknown>>();
	const pi = {
		on(name: string, handler: (event: unknown) => unknown) {
			const list = handlers.get(name) ?? [];
			list.push(handler);
			handlers.set(name, list);
		},
		sendUserMessage() {},
		setActiveTools() {},
		registerTool() {},
	};
	vi.stubEnv("PI_WORKER_TASK", taskPath);
	process.chdir(target);
	await workerModeActivate(pi as unknown as ExtensionAPI);
	return {
		call(toolName: string, input: Record<string, unknown>) {
			for (const handler of handlers.get("tool_call") ?? []) {
				const result = handler({ type: "tool_call", toolCallId: "probe", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
		settle() {
			for (const handler of handlers.get("agent_end") ?? []) handler({ messages: [] });
			for (const handler of handlers.get("agent_settled") ?? []) handler({});
		},
	};
}

describe.each(["dual", "partition"] as const)("%s separated write roots", (mode) => {
	it("dispatch accepts configured roots, rejects overlap and outside roots without queue mutation", async () => {
		const fx = fixture(mode);
		const store = new WorkerStore(fx.agenticdoc);
		const send = (name: string, entries: string[]) =>
			dispatchTask(
				{
					taskKey: name,
					status: "pending",
					cli: "pi",
					provider: "timi",
					model: "",
					taskPath: task(fx, name, entries),
				},
				store,
			);
		const file = path.join(fx.target, "src", "a.cpp");
		expect(await send("one", [file])).toEqual({ ok: true });
		const before = fs.readFileSync(store.queuePath, "utf8");
		expect(await send("same", [file.replaceAll("\\", "/")])).toMatchObject({ ok: false, code: "write-face-overlap" });
		expect(fs.readFileSync(store.queuePath, "utf8")).toBe(before);
		expect(await send("outside", [path.join(fx.top, "outside.cpp")])).toMatchObject({
			ok: false,
			code: "write-face-outside-base",
		});
		expect(fs.readFileSync(store.queuePath, "utf8")).toBe(before);
		expect(await send("escape", [`${fx.target}/../outside.cpp`])).toMatchObject({
			ok: false,
			code: "write-face-escape",
		});
		expect(fs.readFileSync(store.queuePath, "utf8")).toBe(before);
		expect(await send("control", ["src/a.cpp"])).toEqual({ ok: true });
		expect(await send("extra", [path.join(fx.extra, "src", "a.cpp")])).toEqual({ ok: true });
		if (mode === "partition") expect(await send("named", [path.join(fx.named, "sdk.h")])).toEqual({ ok: true });
		process.stdout.write(
			`[VERIFY] VC-001/002/005 ${mode}: configured roots accepted; overlap/escape/outside rejected\n`,
		);
	});

	it("runtime keeps the six-file face and bookkeeping paths with foreign-write enabled", async () => {
		const fx = fixture(mode);
		const files = Array.from({ length: 6 }, (_, index) => path.join(fx.target, "Plugin", `${index}.cpp`));
		const taskPath = task(fx, "six", files, ["allow_foreign_write: true"]);
		const guard = await worker(taskPath, fx.target);
		try {
			for (const file of files) {
				expect(guard.call("write", { path: file, content: "x" })).toBeUndefined();
				expect(guard.call("edit", { path: file, edits: [] })).toBeUndefined();
			}
			for (const file of [
				path.join(fx.target, "Plugin", "seventh.cpp"),
				path.join(fx.extra, "outside.cpp"),
				path.join(fx.top, "foreign.cpp"),
			]) {
				expect(guard.call("write", { path: file, content: "x" })?.block, file).toBe(true);
				expect(guard.call("edit", { path: file, edits: [] })?.block, file).toBe(true);
				expect(guard.call("bash", { command: `echo x > "${file}"` })?.block, file).toBe(true);
			}
			for (const file of [
				path.join(path.dirname(taskPath), "output.md"),
				path.join(fx.agenticdoc, KEY, "evidence", "case.json"),
			])
				expect(guard.call("write", { path: file, content: "x" })).toBeUndefined();
			for (const file of [
				path.join(fx.agenticdoc, "other-key", "x.md"),
				path.join(fx.agenticdoc, KEY, "pm-state.md"),
				path.join(fx.agenticdoc, "_index.parallel"),
				...[fx.control, fx.target, fx.extra, ...(mode === "partition" ? [fx.named] : [])].map((root) =>
					path.join(root, ".git", "config"),
				),
			])
				expect(guard.call("write", { path: file, content: "x" })?.reason, file).toContain("rule=deny");
		} finally {
			guard.settle();
		}
		process.stdout.write(
			`[VERIFY] VC-004/006 ${mode}: six-file face enforced; own artifacts allowed; hard denials preserved\n`,
		);
	});

	it("runtime never reinterprets control-relative declarations at the target cwd", async () => {
		const fx = fixture(mode);
		const controlFile = path.join(fx.control, "src", "a.cpp");
		for (const root of [fx.control, fx.target]) {
			fs.mkdirSync(path.join(root, "src"));
			fs.writeFileSync(path.join(root, "src", "a.cpp"), `// ${path.basename(root)}\n`);
		}
		const extraFile = path.join(fx.extra, "src", "b.cpp");
		const entries = ["src/a.cpp", extraFile, ...(mode === "partition" ? [path.join(fx.named, "sdk.h")] : [])];
		const taskPath = task(fx, "identity", entries);
		const meta = parseTaskMd(taskPath);
		expect(meta.writeFaceEntries?.[0]).toBe(controlFile.replaceAll("\\", "/"));
		const guard = await worker(taskPath, fx.target);
		try {
			for (const file of [controlFile, extraFile, ...(mode === "partition" ? [path.join(fx.named, "sdk.h")] : [])])
				expect(guard.call("write", { path: file, content: "x" }), file).toBeUndefined();
			expect(guard.call("write", { path: "src/a.cpp", content: "x" })?.block).toBe(true);
			expect(guard.call("write", { path: path.join(fx.control, "src", "b.cpp"), content: "x" })?.block).toBe(true);
		} finally {
			guard.settle();
		}
		process.stdout.write(`[VERIFY] VC-003 ${mode}: declaration identity survives target cwd\n`);
	});

	it("junction aliases cannot split file identity, escape roots or bypass control denials", async () => {
		const fx = fixture(mode);
		const alias = path.join(fx.control, "alias");
		const foreign = path.join(fx.top, "foreign");
		fs.mkdirSync(foreign);
		fs.symlinkSync(fx.target, alias, "junction");
		fs.symlinkSync(foreign, path.join(fx.control, "foreign"), "junction");
		const store = new WorkerStore(fx.agenticdoc);
		const send = (name: string, entry: string) =>
			dispatchTask(
				{
					taskKey: name,
					status: "pending",
					cli: "pi",
					provider: "timi",
					model: "",
					taskPath: task(fx, name, [entry]),
				},
				store,
			);
		expect(await send("alias", "alias/src/a.cpp")).toEqual({ ok: true });
		expect(await send("physical", path.join(fx.target, "src", "a.cpp"))).toMatchObject({
			ok: false,
			code: "write-face-overlap",
		});
		expect(await send("foreign", "foreign/file.cpp")).toMatchObject({ ok: false, code: "write-face-outside-base" });
		const controlAlias = path.join(fx.top, "control-alias");
		fs.symlinkSync(fx.control, controlAlias, "junction");
		const denyEntries = [
			`.agenticdoc/${KEY}/pm-state.md`,
			".agenticdoc/_index.parallel",
			".agenticdoc/other/x.md",
			`.agenticdoc/${KEY}/workers/_workers.parallel`,
		];
		const physicalTask = task(fx, "denials", denyEntries, ["allow_foreign_write: true"]);
		const taskAlias = path.join(controlAlias, path.relative(fx.control, physicalTask));
		const guard = await worker(taskAlias, fx.target);
		try {
			for (const entry of denyEntries) {
				const file = path.join(controlAlias, entry);
				expect(guard.call("write", { path: file, content: "x" })?.reason, file).toContain("rule=deny");
			}
		} finally {
			guard.settle();
		}
		process.stdout.write(
			`[VERIFY] VC-003/004/005 ${mode}: real junction aliases share identity; root escapes and control denials blocked\n`,
		);
	});

	it("legacy foreign-write only opens an undeclared face; write_scope still narrows rooted declarations", async () => {
		const fx = fixture(mode);
		const legacy = await worker(task(fx, "legacy", undefined, ["allow_foreign_write: true"]), fx.target);
		try {
			expect(legacy.call("write", { path: path.join(fx.top, "foreign.cpp"), content: "x" })).toBeUndefined();
			expect(legacy.call("write", { path: path.join(fx.control, ".git", "config"), content: "x" })?.block).toBe(
				true,
			);
		} finally {
			legacy.settle();
		}
		const file = path.join(fx.control, "src", "a.cpp");
		const narrowed = await worker(
			task(
				fx,
				"scope",
				[file, path.join(fx.extra, "b.cpp")],
				["write_scope: src/a.cpp", "allow_foreign_write: true"],
			),
			fx.target,
		);
		try {
			expect(narrowed.call("write", { path: file, content: "x" })).toBeUndefined();
			expect(narrowed.call("write", { path: path.join(fx.extra, "b.cpp"), content: "x" })?.block).toBe(true);
		} finally {
			narrowed.settle();
		}
	});

	it("research write_scope stays anchored to control evidence at a separated cwd", async () => {
		const fx = fixture(mode);
		const taskPath = task(
			fx,
			"research",
			undefined,
			[`write_scope: .agenticdoc/${KEY}/evidence, .agenticdoc/${KEY}/workers/research`],
			"research",
		);
		const guard = await worker(taskPath, fx.target);
		try {
			for (const file of [
				path.join(fx.agenticdoc, KEY, "evidence", "research.md"),
				path.join(path.dirname(taskPath), "report.md"),
			])
				expect(guard.call("bash", { command: `echo x > "${file}"` }), file).toBeUndefined();
			expect(guard.call("bash", { command: "echo x > README.md" })?.block).toBe(true);
		} finally {
			guard.settle();
		}
		process.stdout.write(`[VERIFY] VC-004 ${mode}: research write_scope retains control-root evidence identity\n`);
	});
});

it("TS/Python agree on rooted identities including nested and literal root prefixes", () => {
	const base = "E:/Control[one]";
	const roots = [base, "D:/Game", "D:/Game/Plugin", "F:/Parent"];
	const entries = ["src/a.cpp", "D:/Game/Plugin/{a,b}.cpp", "F:/Parent/src/a.cpp"];
	const options = { base, roots, caseInsensitive: true };
	const face = parseWriteFaceEntries(entries, options);
	if (face.kind !== "declared") throw new Error("expected rooted face");
	const same = parseWriteFaceEntries([`${base}/src/a.cpp`], { ...options, roots: [base, "D:/Game", "F:/Parent"] });
	const different = parseWriteFaceEntries(["E:/Controlo/src/a.cpp"], { ...options, roots: ["E:/Controlo"] });
	const nested = parseWriteFaceEntries(["D:/Game/Plugin/a.cpp"], {
		...options,
		roots: [base, "D:/Game", "F:/Parent"],
	});
	if (same.kind !== "declared" || different.kind !== "declared") throw new Error("probe parse failed");
	if (nested.kind !== "declared") throw new Error("nested probe parse failed");
	const nestedOverlap = writeFacesOverlap(face.face, nested.face);
	expect(nestedOverlap).not.toBeNull();
	const cases = {
		base,
		roots,
		entries,
		actual: face.face.entries,
		overlap: writeFacesOverlap(face.face, same.face),
		different: writeFacesOverlap(face.face, different.face),
	};
	const script = fileURLToPath(new URL("../../../multi-workers/test/rooted_face_probe.py", import.meta.url));
	const result = spawnSync("python", ["-B", script], { input: JSON.stringify(cases), encoding: "utf8" });
	expect(result.status, result.stderr).toBe(0);
	expect(JSON.parse(result.stdout)).toEqual({ entries: face.face.entries, overlap: true, different: false });
	process.stdout.write("[VERIFY] VC-003 rooted TS/Python parity; literal and nested prefixes\n");
});
