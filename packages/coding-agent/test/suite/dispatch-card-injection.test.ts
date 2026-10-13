/**
 * dispatch-card-injection.test.ts — T-02 generator injection + tool-layer gate
 * (key `mw-dispatch-card-gate`, design §4 G-1/G-2, AC-001 / AC-006 / AC-007).
 *
 * What is pinned here:
 *
 * 1. **positive** — a compliant card dispatches; the generated `task.md` is
 *    asserted byte-for-byte, including the injected `## 上下文` / `## 要求` /
 *    `## 交付格式` seed block, the seed disclaimer, and the bare
 *    `card_path:` / `card_sha256:` header lines in the same prologue as
 *    `type:` (no `---` fence);
 * 2. **negative** — no `card_path`, an unreadable card, and a card missing an
 *    envelope section all refuse with the missing items + card path named and
 *    zero storage growth (no task dir, no queue row);
 * 3. **idempotency** — re-applying the seed block is a byte-level fixed point;
 * 4. **cross-language digest parity** — TS `card-digest` equals Python
 *    `mw_common.sha256_eol_normalized` byte-for-byte, CRLF/LF are equivalent,
 *    and an equal-length tamper changes the digest.
 *
 * Fixtures are self-contained temp trees; the real repo is never written. No
 * provider APIs or network.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { VERSION } from "../../src/config.ts";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	applyCardSeedSections,
	CARD_SEED_DISCLAIMER,
	CARD_SEED_MARKER,
	CARD_SEED_MARKER_END,
	DISPATCH_PRODUCER_ID,
	ENVELOPE_PRODUCER_KEY,
	extractCardSections,
	registerWorkerCommands,
	registerWorkerTools,
	renderCardSeedSections,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { cardDigest, sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

const temporaryDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwd-t02-"));
	temporaryDirs.push(dir);
	return dir;
}

afterEach(() => {
	while (temporaryDirs.length > 0) {
		const dir = temporaryDirs.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
});

// ── fake pi (tools only) ────────────────────────────────────────────────────

interface ToolDouble {
	execute: (
		id: string,
		params: unknown,
		signal: undefined,
		onUpdate: undefined,
		ctx: ExtensionContext,
	) => Promise<{ content: Array<{ type: string; text: string }> }>;
}

function fakePi(): {
	pi: ExtensionAPI;
	tools: Map<string, ToolDouble>;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void> | void>;
} {
	const tools = new Map<string, ToolDouble>();
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void> | void>();
	const pi = {
		registerCommand: (
			name: string,
			command: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> | void },
		) => {
			commands.set(name, command.handler);
		},
		registerTool: (tool: { name: string } & ToolDouble) => {
			tools.set(tool.name, tool);
		},
		appendEntry: () => {},
		sendUserMessage: () => {},
		sendMessage: () => {},
	} as unknown as ExtensionAPI;
	return { pi, tools, commands };
}

function fakeCommandCtx(): { ctx: ExtensionCommandContext; notifications: string[] } {
	const notifications: string[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => {
				notifications.push(message);
			},
			setWidget: () => {},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

function fakeCtx(): ExtensionContext {
	return {
		hasUI: false,
		ui: { notify: () => {}, setWidget: () => {} },
	} as unknown as ExtensionContext;
}

// ── card fixtures ───────────────────────────────────────────────────────────

const CARD_TYPE = "coding";
const CARD_NAME = "T-02-fixture.md";
const CARD_CONTEXT =
	"任务投递链无人读卡，所以生成端必须注入信封；种子不是探索上界。锚点 .agenticdoc/goal.md；判据 pm/ui-bridge.ts:1969。";
const CARD_REQUIREMENTS = "AC-001 要求环境变量为空时返回默认值，并覆盖 CRLF/LF 两种输入。";
const CARD_DELIVERABLES = "产物 report.md；回收命令 vitest --run test/suite/dispatch-card-injection.test.ts。";

const ACCEPTANCE_COMMAND =
	"node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-injection.test.ts";

/** A fully compliant `coding` card (type + three sections + four extras). */
const COMPLIANT_CARD = [
	`type: ${CARD_TYPE}`,
	"",
	"# T-02 fixture",
	"",
	"## 上下文",
	"",
	CARD_CONTEXT,
	"",
	"## 要求",
	"",
	CARD_REQUIREMENTS,
	"",
	"## 交付格式",
	"",
	CARD_DELIVERABLES,
	"",
	"## 写入允许面",
	"",
	"仅本任务目录。",
	"",
	"## 写入禁止面",
	"",
	"其他 key、packages/**。",
	"",
	"## 验收命令",
	"",
	ACCEPTANCE_COMMAND,
	"",
	"## 改动历史",
	"",
	"见 trace.log 写入事件与 report.md 改动清单。",
	"",
].join("\n");

/** The four §1.2 coding extras the compliant card declares (document order). */
const EXPECTED_EXTRAS = [
	{ title: "写入允许面", body: "仅本任务目录。" },
	{ title: "写入禁止面", body: "其他 key、packages/**。" },
	{ title: "验收命令", body: ACCEPTANCE_COMMAND },
	{ title: "改动历史", body: "见 trace.log 写入事件与 report.md 改动清单。" },
];

/** The seed sections the compliant card yields (extraction input). */
const EXPECTED_SECTIONS = {
	context: CARD_CONTEXT,
	requirements: CARD_REQUIREMENTS,
	deliverables: CARD_DELIVERABLES,
	extras: EXPECTED_EXTRAS,
};

/** Write a card under `<root>/<key>/tasks/<name>` and return its absolute path. */
function writeCard(root: string, key: string, name: string, bytes: string): string {
	const dir = path.join(root, key, "tasks");
	fs.mkdirSync(dir, { recursive: true });
	const cardPath = path.join(dir, name);
	fs.writeFileSync(cardPath, bytes, "utf8");
	return cardPath;
}

interface DispatchFixture {
	root: string;
	store: WorkerStore;
	tool: ToolDouble;
	/** Relative card path from the repo root (projectDir === root). */
	cardRelPath: string;
	cardAbsPath: string;
}

/** `_scratch` dispatch fixture: no phase docs needed, tool + queue available. */
function setupDispatch(): DispatchFixture {
	const root = mkdtemp();
	const store = new WorkerStore(root);
	const { pi, tools } = fakePi();
	registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: "_scratch" }, root);
	const tool = tools.get("dispatch_worker");
	if (!tool) throw new Error("dispatch_worker not registered");
	const cardAbsPath = writeCard(root, "_scratch", CARD_NAME, COMPLIANT_CARD);
	return { root, store, tool, cardRelPath: `_scratch/tasks/${CARD_NAME}`, cardAbsPath };
}

function taskDirOf(root: string, taskKey: string): string {
	return path.join(root, "_scratch", "workers", taskKey);
}

async function dispatch(fx: DispatchFixture, params: Record<string, unknown>): Promise<string> {
	const result = await fx.tool.execute("id", params, undefined, undefined, fakeCtx());
	return result.content[0]?.text ?? "";
}

// ── 1. positive: byte-level injection ───────────────────────────────────────

describe("dispatch card injection (G-2)", () => {
	it("dispatches a compliant card and injects the three sections byte-for-byte", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		const description = "实现信封注入并写测试。";

		const message = await dispatch(fx, {
			task_key: "t-inject",
			card_path: fx.cardRelPath,
			description,
		});
		expect(message).toContain("Dispatched worker 't-inject'");
		expect(fx.store.readAll()).toHaveLength(before + 1);

		const sha = cardDigest(fx.cardAbsPath);
		// T-18/VC-003: the producer identity line, id distinct from the Python
		// conductor's `autopilot-conductor`; version is the existing source
		// (`packages/coding-agent/package.json` via config.ts VERSION).
		const producerLine = `${ENVELOPE_PRODUCER_KEY}: ${DISPATCH_PRODUCER_ID}@${VERSION}`;
		const frontmatter = `type: coding\ncard_path: tasks/${CARD_NAME}\ncard_sha256: ${sha}\n${producerLine}\n`;
		const seed = renderCardSeedSections(EXPECTED_SECTIONS);
		const expected = `${frontmatter}\n${seed}\n\n${description}\n`;

		const taskMdPath = path.join(taskDirOf(fx.root, "t-inject"), "task.md");
		const actual = fs.readFileSync(taskMdPath, "utf8");
		// Byte-level equality: header region, seed block and disclaimer together.
		expect(actual).toBe(expected);
		// The identity line matches the Python service-layer shape (T-13/T-14:
		// `dispatch.py` `_PRODUCER_LINE_RE` value part `[^\s@|]+@[^\s|]+`,
		// `launcher.py` `_ENVELOPE_PRODUCER_LINE_RE` value part `(\S+)`).
		expect(producerLine).toMatch(new RegExp(`^${ENVELOPE_PRODUCER_KEY}: [^\\s@|]+@[^\\s|]+$`));
		expect(actual).toContain(`\n${producerLine}\n`);
		// The seed disclaimer is a literal, single line.
		expect(actual).toContain(`\n${CARD_SEED_DISCLAIMER}\n`);
		// Bare header lines share the type: prologue; no `---` fence anywhere.
		const prologue = actual.split("\n\n")[0] ?? "";
		expect(prologue.split("\n")).toEqual([
			"type: coding",
			`card_path: tasks/${CARD_NAME}`,
			`card_sha256: ${sha}`,
			producerLine,
		]);
		expect(actual.split("\n").some((line) => line.trim() === "---")).toBe(false);
		// Section bodies are the card's bodies, not the description.
		expect(actual).toContain(`## 上下文\n\n${CARD_CONTEXT}`);
		expect(actual).toContain(`## 要求\n\n${CARD_REQUIREMENTS}`);
		expect(actual).toContain(`## 交付格式\n\n${CARD_DELIVERABLES}`);
		expect(actual).toContain(`${CARD_SEED_MARKER}\n`);
		expect(actual).toContain(`${CARD_SEED_MARKER_END}\n`);
		process.stdout.write(
			`[VERIFY] VC-t02-inject: queue_delta=${fx.store.readAll().length - before} bytes=${Buffer.byteLength(actual, "utf8")}\n`,
		);
	});

	it("accepts an absolute card path and records the normalized tasks/<name>.md id", async () => {
		const fx = setupDispatch();
		const message = await dispatch(fx, {
			task_key: "t-abs",
			card_path: fx.cardAbsPath,
			description: "work",
		});
		expect(message).toContain("Dispatched worker 't-abs'");
		const md = fs.readFileSync(path.join(taskDirOf(fx.root, "t-abs"), "task.md"), "utf8");
		expect(md).toContain(`card_path: tasks/${CARD_NAME}\n`);
	});

	it("is idempotent: the seed block is a byte-level fixed point", () => {
		const once = applyCardSeedSections("原始正文。", EXPECTED_SECTIONS);
		const twice = applyCardSeedSections(once, EXPECTED_SECTIONS);
		expect(twice).toBe(once);
		// Exactly one marker pair, even after re-application.
		expect(once.split(CARD_SEED_MARKER).length - 1).toBe(1);
		expect(once.split(CARD_SEED_MARKER_END).length - 1).toBe(1);
	});

	it("extracts heading variants and falls back to the whole body for headingless cards", () => {
		const variant = `type: research\n\n## 目标\n\n动机。\n\n## 验收标准\n\nAC-001。\n\n## 预期产出\n\nreport.md。\n`;
		expect(extractCardSections(variant)).toEqual({
			context: "动机。",
			requirements: "AC-001。",
			deliverables: "report.md。",
			extras: [],
		});
		// A card the wide gate accepts via paragraph semantics has no heading
		// slice; the post-prologue body is delivered rather than dropped.
		const headingless = `type: research\n\n# X\n\n因为历史卡无标题。\n\n判据 AC-007。\n\n产物 report.md。\n`;
		const sections = extractCardSections(headingless);
		expect(sections.context).not.toBe("");
		expect(sections.context).toBe(sections.deliverables);
		expect(sections.extras).toEqual([]);
	});

	it("carries the card's §1.2 extras sections into the seed (F-02)", () => {
		const sections = extractCardSections(COMPLIANT_CARD);
		expect(sections.extras).toEqual(EXPECTED_EXTRAS);
		const seed = renderCardSeedSections(sections);
		for (const extra of EXPECTED_EXTRAS) {
			expect(seed).toContain(`## ${extra.title}\n\n${extra.body}`);
		}
	});
});

// ── 2. negative: fail-closed, zero side effects ─────────────────────────────

describe("dispatch card gate (G-1)", () => {
	it("refuses a missing card_path with missing=[card_path] and writes nothing", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		const message = await dispatch(fx, { task_key: "t-none", description: "work" });
		expect(message).toContain("dispatch-card");
		expect(message).toContain("missing=[card_path]");
		expect(fs.existsSync(taskDirOf(fx.root, "t-none"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("refuses an unreadable card with missing=[file] and the resolved path", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		const missing = path.join(fx.root, "_scratch", "tasks", "does-not-exist.md");
		const message = await dispatch(fx, { task_key: "t-absent", card_path: missing, description: "work" });
		expect(message).toContain("missing=[file]");
		expect(message).toContain(missing);
		expect(fs.existsSync(taskDirOf(fx.root, "t-absent"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("refuses a card missing an envelope section with the section named", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		// Built without a deliverables heading AND without a semantic hint
		// (`report.md` / 产物 / 输出), so the wide-档 judge really reports it
		// missing instead of falling back to paragraph semantics.
		const broken = [
			"type: coding",
			"",
			"## 上下文",
			"",
			"因为需要注入。",
			"",
			"## 要求",
			"",
			"AC-001 成立。",
			"",
			"## 写入允许面",
			"",
			"仅本任务目录。",
			"",
			"## 写入禁止面",
			"",
			"其他 key。",
			"",
			"## 验收命令",
			"",
			"node x.test.ts",
			"",
			"## 改动历史",
			"",
			"trace.log。",
			"",
		].join("\n");
		const brokenAbs = writeCard(fx.root, "_scratch", "T-02-broken.md", broken);
		const message = await dispatch(fx, { task_key: "t-broken", card_path: brokenAbs, description: "work" });
		expect(message).toContain("missing=[deliverables]");
		expect(message).toContain(brokenAbs);
		expect(fs.existsSync(taskDirOf(fx.root, "t-broken"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("refuses a card whose envelope type is missing (type named in missing=[])", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		const noType = COMPLIANT_CARD.replace(`type: ${CARD_TYPE}\n`, "phase: BUILD\n");
		const noTypeAbs = writeCard(fx.root, "_scratch", "T-02-notype.md", noType);
		const message = await dispatch(fx, { task_key: "t-notype", card_path: noTypeAbs, description: "work" });
		expect(message).toContain("missing=[type]");
		expect(message).toContain(noTypeAbs);
		expect(fs.existsSync(taskDirOf(fx.root, "t-notype"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("refuses a coding card missing a per-type extra and names it (F-02)", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		// All three envelope sections + 3/4 extras; only 验收命令 is absent.
		const broken = [
			"type: coding",
			"",
			"## 上下文",
			"",
			CARD_CONTEXT,
			"",
			"## 要求",
			"",
			CARD_REQUIREMENTS,
			"",
			"## 交付格式",
			"",
			CARD_DELIVERABLES,
			"",
			"## 写入允许面",
			"",
			"仅本任务目录。",
			"",
			"## 写入禁止面",
			"",
			"其他 key。",
			"",
			"## 改动历史",
			"",
			"见 trace.log。",
			"",
		].join("\n");
		const brokenAbs = writeCard(fx.root, "_scratch", "T-02-noextra.md", broken);
		const message = await dispatch(fx, { task_key: "t-noextra", card_path: brokenAbs, description: "work" });
		expect(message).toContain("missing=[验收命令]");
		expect(message).toContain(brokenAbs);
		expect(fs.existsSync(taskDirOf(fx.root, "t-noextra"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("refuses a card without the seed minimum and names both items (F-05)", async () => {
		const fx = setupDispatch();
		const before = fx.store.readAll().length;
		const noSeed = COMPLIANT_CARD.replace(CARD_CONTEXT, "没有种子项的上下文。");
		const noSeedAbs = writeCard(fx.root, "_scratch", "T-02-noseed.md", noSeed);
		const message = await dispatch(fx, { task_key: "t-noseed", card_path: noSeedAbs, description: "work" });
		expect(message).toContain("missing=[seed:goal.md, seed:path:line]");
		expect(message).toContain(noSeedAbs);
		expect(fs.existsSync(taskDirOf(fx.root, "t-noseed"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("/worker refuses a missing --card with the same judgement and writes nothing", async () => {
		const root = mkdtemp();
		const { pi, commands } = fakePi();
		const store = new WorkerStore(root);
		registerWorkerCommands(pi, store, new IndexStore(root), root, { key: "_scratch" }, root);
		const handler = commands.get("worker");
		if (!handler) throw new Error("/worker not registered");
		const { ctx, notifications } = fakeCommandCtx();
		await handler("pi --type coding work", ctx);
		expect(notifications.join("\n")).toContain("missing=[card_path]");
		expect(fs.existsSync(path.join(root, "_scratch", "workers"))).toBe(false);
		expect(store.readAll()).toHaveLength(0);
	});
});

// ── 3. cross-language digest parity (AC-006) ────────────────────────────────

const pythonAvailable = (() => {
	try {
		return spawnSync(resolveRagPython(), ["-c", "print(1)"], { encoding: "utf8", timeout: 10_000 }).status === 0;
	} catch {
		return false;
	}
})();

function pythonDigest(cardPath: string): string {
	const script = [
		"import pathlib, sys",
		`sys.path.insert(0, ${JSON.stringify(MULTI_WORKERS_DIR)})`,
		"import mw_common",
		"print(mw_common.sha256_eol_normalized(pathlib.Path(sys.argv[1])))",
	].join("\n");
	const result = spawnSync(resolveRagPython(), ["-c", script, cardPath], {
		encoding: "utf8",
		timeout: 20_000,
	});
	if (result.status !== 0) {
		throw new Error(`python sha256_eol_normalized failed: ${result.stdout ?? ""}${result.stderr ?? ""}`);
	}
	return (result.stdout ?? "").trim();
}

describe("card digest EOL semantics (AC-006)", () => {
	it("hashes bytes with CRLF folded to LF", () => {
		const lf = Buffer.from("type: coding\n\n## 上下文\n\nx\n", "utf8");
		const crlf = Buffer.from(lf.toString("utf8").replace(/\n/g, "\r\n"), "utf8");
		expect(crlf).not.toEqual(lf);
		expect(sha256EolNormalizedBytes(crlf)).toBe(sha256EolNormalizedBytes(lf));
		// Lone CR is not a line ending here (Python replaces only b"\r\n").
		expect(sha256EolNormalizedBytes(Buffer.from("a\rb", "utf8"))).not.toBe(
			sha256EolNormalizedBytes(Buffer.from("a\nb", "utf8")),
		);
	});

	it("golden: a fixed byte string hashes to the recorded hex", () => {
		const bytes = Buffer.from("type: coding\n\n## 上下文\n\nx\n", "utf8");
		expect(sha256EolNormalizedBytes(bytes)).toBe(
			createHash("sha256").update(Buffer.from("type: coding\n\n## 上下文\n\nx\n", "utf8")).digest("hex"),
		);
	});

	it.skipIf(!pythonAvailable)("matches Python sha256_eol_normalized for the same card (LF and CRLF)", () => {
		const root = mkdtemp();
		const lfPath = path.join(root, "lf.md");
		const crlfPath = path.join(root, "crlf.md");
		fs.writeFileSync(lfPath, COMPLIANT_CARD, "utf8");
		fs.writeFileSync(crlfPath, COMPLIANT_CARD.replace(/\n/g, "\r\n"), "utf8");

		const tsLf = cardDigest(lfPath);
		const tsCrlf = cardDigest(crlfPath);
		expect(tsCrlf).toBe(tsLf);
		expect(pythonDigest(lfPath)).toBe(tsLf);
		expect(pythonDigest(crlfPath)).toBe(tsLf);
		process.stdout.write(`[VERIFY] VC-t02-parity: sha256=${tsLf} crlf_equal=true\n`);
	});

	it.skipIf(!pythonAvailable)("T-06 card_audit resolves the generated card_path and digest", async () => {
		const fx = setupDispatch();
		await dispatch(fx, { task_key: "t-trace", card_path: fx.cardRelPath, description: "work" });
		const script = [
			"import json, pathlib, sys",
			`sys.path.insert(0, ${JSON.stringify(MULTI_WORKERS_DIR)})`,
			`sys.path.insert(0, ${JSON.stringify(path.join(MULTI_WORKERS_DIR, "autopilot"))})`,
			"import card_audit",
			"result = card_audit.audit(sys.argv[1], '_scratch')",
			"print(json.dumps({'missing': result['missing_cards'], 'unlisted': result['unlisted_dispatches'], " +
				"'card': [d['card'] for d in result['dispatched']], 'digest': result['digests'].get('tasks/T-02-fixture.md', '')}))",
		].join("\n");
		const out = spawnSync(resolveRagPython(), ["-c", script, fx.root], { encoding: "utf8", timeout: 20_000 });
		expect(out.status, `${out.stdout ?? ""}${out.stderr ?? ""}`).toBe(0);
		const result = JSON.parse((out.stdout ?? "").trim()) as {
			missing: string[];
			unlisted: string[];
			card: string[];
			digest: string;
		};
		expect(result.missing).toEqual([]);
		expect(result.unlisted).toEqual([]);
		expect(result.card).toEqual([`tasks/${CARD_NAME}`]);
		expect(result.digest).toBe(cardDigest(fx.cardAbsPath));
		process.stdout.write(`[VERIFY] VC-t02-trace: card=tasks/${CARD_NAME} digest_match=true\n`);
	});

	it.skipIf(!pythonAvailable)("an equal-length tamper changes the digest on both sides, restore returns it", () => {
		const root = mkdtemp();
		const cardPath = path.join(root, "card.md");
		fs.writeFileSync(cardPath, COMPLIANT_CARD, "utf8");
		const original = cardDigest(cardPath);
		expect(pythonDigest(cardPath)).toBe(original);

		// Same byte length, different content.
		const tampered = COMPLIANT_CARD.replace("AC-001", "AC-002");
		expect(Buffer.byteLength(tampered, "utf8")).toBe(Buffer.byteLength(COMPLIANT_CARD, "utf8"));
		fs.writeFileSync(cardPath, tampered, "utf8");
		const changed = cardDigest(cardPath);
		expect(changed).not.toBe(original);
		expect(pythonDigest(cardPath)).toBe(changed);

		fs.writeFileSync(cardPath, COMPLIANT_CARD, "utf8");
		expect(cardDigest(cardPath)).toBe(original);
		expect(pythonDigest(cardPath)).toBe(original);
	});
});

// ── 4. G-1/G-3 extras sameness (F-02) ───────────────────────────────────────

/** Run the real service-layer refusal on a generated task.md, through python. */
function pythonEnvelopeRefusal(taskMdPath: string): string | null {
	const script = [
		"import json, sys",
		`sys.path.insert(0, ${JSON.stringify(MULTI_WORKERS_DIR)})`,
		"import launcher",
		"entry = {'task_path': sys.argv[1], 'task_key': 'probe', 'dispatched_at': '2026-10-13T00:00:00+00:00'}",
		"print(json.dumps(launcher._envelope_refusal(entry)))",
	].join("\n");
	const result = spawnSync(resolveRagPython(), ["-c", script, taskMdPath], { encoding: "utf8", timeout: 20_000 });
	if (result.status !== 0) {
		throw new Error(`python _envelope_refusal failed: ${result.stdout ?? ""}${result.stderr ?? ""}`);
	}
	return JSON.parse((result.stdout ?? "").trim()) as string | null;
}

describe("G-1/G-3 extras sameness (F-02)", () => {
	it.skipIf(!pythonAvailable)(
		"a compliant card passes G-1 and its derived task.md passes launcher._envelope_refusal",
		async () => {
			const fx = setupDispatch();
			const before = fx.store.readAll().length;
			const message = await dispatch(fx, { task_key: "t-svc", card_path: fx.cardRelPath, description: "work" });
			expect(message).toContain("Dispatched worker 't-svc'");
			expect(fx.store.readAll()).toHaveLength(before + 1);

			const taskMd = path.join(taskDirOf(fx.root, "t-svc"), "task.md");
			const text = fs.readFileSync(taskMd, "utf8");
			for (const extra of EXPECTED_EXTRAS) expect(text).toContain(`## ${extra.title}`);
			expect(pythonEnvelopeRefusal(taskMd)).toBeNull();
			process.stdout.write(`[VERIFY] VC-t12-f02: g1=pass g3=pass extras=${EXPECTED_EXTRAS.length}\n`);
		},
	);
});
