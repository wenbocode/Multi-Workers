/**
 * dispatch-claims-render.test.ts — T-02 PM dispatch layer: claims gate, caps
 * rendering and claims-block injection (key `claim-driven-review`, design §3.2 /
 * §4 / §5 G1, D-002 / D-006).
 *
 * What is pinned here:
 *
 * 1. **caps follow the claims** — `claimBudgetCaps` (fileCap = Σ(manual?2:1),
 *    byteCap = 65536 × n) is rendered into the task.md frontmatter through
 *    `writeDispatchTaskMd`;
 * 2. **field order** — `read_scope:` block list, then `l2_read_file_cap:`, then
 *    `l2_read_byte_cap:` (the same carrier `dispatch.py::render_task_md` emits,
 *    and the one `worker/worker-mode.ts` parses);
 * 3. **claims-block injection** — the card's `<!-- mw-claims: v1 -->` block
 *    reaches task.md verbatim INSIDE the `mw-dispatch-card: v1` marker region,
 *    so the settle layer never has to re-read the (mutable) card file (D-002);
 * 4. **advisory receipt** — `[claims] <mode> claims=<n> caps=<f>/<b>
 *    warnings=[…]` is appended only when the card declares claims, so the
 *    pre-claims receipt stays byte-identical (`triage-dispatch.test.ts` pins the
 *    full string);
 * 5. **grey release** — `MW_CLAIM_GATE=enforce` refuses soft gaps under the
 *    `dispatch-claims` code with zero side effects; an illegal value falls back
 *    to `advisory`;
 * 6. **no-claims cards are byte-identical** to the pre-T-02 render (no
 *    `read_scope:`, no caps, no interception change).
 *
 * Fixtures are self-contained temp trees; the real repo is never written. No
 * provider APIs or network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { VERSION } from "../../src/config.ts";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	CARD_SEED_DISCLAIMER,
	CARD_SEED_MARKER,
	CARD_SEED_MARKER_END,
	claimGateMode,
	claimReadScope,
	claimsReceiptLine,
	DISPATCH_PRODUCER_ID,
	ENVELOPE_PRODUCER_KEY,
	extractClaimsBlockText,
	readDispatchCard,
	registerWorkerCommands,
	registerWorkerTools,
	renderCardSeedSections,
	writeDispatchTaskMd,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { cardDigest } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import { parseClaimsBlock } from "../../src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const temporaryDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwc-t02-"));
	temporaryDirs.push(dir);
	return dir;
}

afterEach(() => {
	delete process.env.MW_CLAIM_GATE;
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

function fakePi(): { pi: ExtensionAPI; tools: Map<string, ToolDouble> } {
	const tools = new Map<string, ToolDouble>();
	const pi = {
		registerCommand: () => {},
		registerTool: (tool: { name: string } & ToolDouble) => {
			tools.set(tool.name, tool);
		},
		appendEntry: () => {},
		sendUserMessage: () => {},
		sendMessage: () => {},
	} as unknown as ExtensionAPI;
	return { pi, tools };
}

function fakeCtx(): ExtensionContext {
	return {
		hasUI: false,
		ui: { notify: () => {}, setWidget: () => {} },
	} as unknown as ExtensionContext;
}

// ── card fixtures ───────────────────────────────────────────────────────────

const CARD_NAME = "T-02-claims.md";
const CARD_CONTEXT =
	"任务投递链无人读卡，所以生成端必须注入信封；种子不是探索上界。锚点 .agenticdoc/goal.md；判据 pm/ui-bridge.ts:1969。";
const CARD_REQUIREMENTS = "AC-001 要求 claims 块随 task.md 一起注入，结算期不回读卡文件。";
const CARD_DELIVERABLES = "产物 report.md；回收命令 vitest --run test/suite/dispatch-claims-render.test.ts。";

const CLAIMS_HEADER = [
	"<!-- mw-claims: v1 -->",
	"| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |",
	"| --- | --- | --- | --- | --- | --- | --- |",
];
const CLAIMS_CLOSE = "<!-- /mw-claims -->";

/** `grep` row: weight 1. Locator `src/app.ts` exists in the fixture root. */
const ROW_GREP =
	"| C-01 | grep | 派发层不再吞掉 claims 块 | 出现 claims 块但 claims=[] | src/app.ts | grep: count=0 | 2 |";
/** `manual` row: weight 2 (design §4). */
const ROW_MANUAL =
	"| C-02 | manual | 未引入新的 fail-open | 枚举出任意新 fail-open | src/app.ts:1 | manual: 由 PM 裁决 | 1 |";
/** `struct` row: weight 1. */
const ROW_STRUCT = "| C-03 | struct | 三段种子齐全 | 缺任一段 | src/app.ts | shape: 3/3 | 1 |";

function claimsBlock(rows: string[]): string {
	return [...CLAIMS_HEADER, ...rows, CLAIMS_CLOSE].join("\n");
}

/** A compliant `coding` card; a claims block is appended only when rows are
 * given (an empty row list is the "card without claims" shape). */
function codingCard(rows: string[]): string {
	const card = [
		"type: coding",
		"",
		"# T-02 claims fixture",
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
		"node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-claims-render.test.ts",
		"",
		"## 改动历史",
		"",
		"见 trace.log 写入事件与 report.md 改动清单。",
		"",
	];
	if (rows.length > 0) card.push(claimsBlock(rows), "");
	return card.join("\n");
}

// ── dispatch fixture ────────────────────────────────────────────────────────

interface DispatchFixture {
	root: string;
	store: WorkerStore;
	tool: ToolDouble;
	cardRelPath: string;
	cardAbsPath: string;
}

function setupDispatch(rows: string[]): DispatchFixture {
	const root = mkdtemp();
	// The claims locator must resolve inside projectDir: create the file the
	// rows point at (locator-unresolved is a soft gap, but a clean fixture makes
	// the caps/order assertions unambiguous).
	fs.mkdirSync(path.join(root, "src"), { recursive: true });
	fs.writeFileSync(path.join(root, "src", "app.ts"), "export const app = 1;\n", "utf8");
	const store = new WorkerStore(root);
	const { pi, tools } = fakePi();
	registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: "_scratch" }, root);
	const tool = tools.get("dispatch_worker");
	if (!tool) throw new Error("dispatch_worker not registered");
	const cardDir = path.join(root, "_scratch", "tasks");
	fs.mkdirSync(cardDir, { recursive: true });
	const cardAbsPath = path.join(cardDir, CARD_NAME);
	fs.writeFileSync(cardAbsPath, codingCard(rows), "utf8");
	return { root, store, tool, cardRelPath: `_scratch/tasks/${CARD_NAME}`, cardAbsPath };
}

function taskDirOf(root: string, taskKey: string): string {
	return path.join(root, "_scratch", "workers", taskKey);
}

async function dispatch(fx: DispatchFixture, params: Record<string, unknown>): Promise<string> {
	const result = await fx.tool.execute("id", params, undefined, undefined, fakeCtx());
	return result.content[0]?.text ?? "";
}

/** Frontmatter of a task.md (the prologue before the first blank line). */
function prologueOf(taskMd: string): string[] {
	return (taskMd.split("\n\n")[0] ?? "").split("\n");
}

// ── 1. caps follow the claims, in a fixed field order ───────────────────────

describe("claims-derived read scope (T-02 requirement 2)", () => {
	it("renders read_scope + caps in the fixed order, sized by the claims", async () => {
		const fx = setupDispatch([ROW_GREP, ROW_MANUAL, ROW_STRUCT]);
		const before = fx.store.readAll().length;
		const message = await dispatch(fx, { task_key: "c-three", card_path: fx.cardRelPath, description: "work" });
		expect(message).toContain("Dispatched worker 'c-three'");
		expect(fx.store.readAll()).toHaveLength(before + 1);

		const taskMd = fs.readFileSync(path.join(taskDirOf(fx.root, "c-three"), "task.md"), "utf8");
		const sha = cardDigest(fx.cardAbsPath);
		// D-014: fileCap = min(callCap 30, perClaim 6 × n 3) = 18; byteCap = 65536 × 3.
		expect(prologueOf(taskMd)).toEqual([
			"type: coding",
			"read_scope:",
			"  - .agenticdoc/_scratch",
			"  - .agenticdoc/goal.md",
			// T-02 requirement 2: the claims' own locators drive the scope, so the
			// review unit can read exactly the files it must falsify (`src/app.ts:1`
			// dedupes onto the bare `src/app.ts` entry).
			"  - src/app.ts",
			"l2_read_file_cap: 18",
			"l2_read_byte_cap: 196608",
			`card_path: tasks/${CARD_NAME}`,
			`card_sha256: ${sha}`,
			`${ENVELOPE_PRODUCER_KEY}: ${DISPATCH_PRODUCER_ID}@${VERSION}`,
			"write_face: 仅本任务目录。",
		]);
	});

	it("one claim yields fileCap 6 / byteCap 65536 (caps are cardinal, not constant)", () => {
		const fx = setupDispatch([ROW_GREP]);
		const gate = readDispatchCard({
			cardPath: fx.cardAbsPath,
			ownerKey: "_scratch",
			agenticdocRoot: fx.root,
			projectDir: fx.root,
		});
		expect(gate.ok).toBe(true);
		expect(gate.claims.map((claim) => claim.id)).toEqual(["C-01"]);
		expect(gate.caps).toEqual({ fileCap: 6, byteCap: 65536 });
		expect(gate.warnings).toEqual([]);
	});

	it("claimReadScope is the key tree plus the goal anchor when there are no locators", () => {
		expect(claimReadScope("k1", [])).toEqual([".agenticdoc/k1", ".agenticdoc/goal.md"]);
	});

	it("claimReadScope adds the claims' own locators, without spans, dupes or escapes", () => {
		// A claim-driven review must be able to READ the files its claims are about:
		// scope = anchors + locators. `:12` / `:12-30` are span suffixes, not paths;
		// `..` and absolute entries are dropped so a card cannot widen its own scope.
		const claim = (locator: string) => ({
			id: "C-01",
			type: "grep",
			parent: "",
			statement: "s",
			falsifier: "f",
			locator,
			judgement: "grep: x",
			budget: 1,
			row: 1,
		});
		expect(
			claimReadScope("k1", [
				claim("packages/coding-agent/src/a.ts:120"),
				claim("packages/coding-agent/src/a.ts:120-140"),
				claim("packages\\coding-agent\\src\\b.ts"),
				claim("./docs/c.md:1"),
				claim("evidence/claims/t07.md#C-01"),
				claim("../outside.ts"),
				claim("C:/abs/path.ts"),
				claim("  "),
			]),
		).toEqual([
			".agenticdoc/k1",
			".agenticdoc/goal.md",
			"packages/coding-agent/src/a.ts",
			"packages/coding-agent/src/b.ts",
			"docs/c.md",
			// D-005: a `cmd` locator's `#<claim-id>` fragment names the row, not a path.
			"evidence/claims/t07.md",
		]);
	});
});

// ── 2. the claims block rides inside the card-seed marker region ────────────

describe("claims-block injection (T-02 requirement 2, D-002)", () => {
	it("injects the block verbatim inside the seed region, before the disclaimer", async () => {
		const fx = setupDispatch([ROW_GREP, ROW_MANUAL]);
		await dispatch(fx, { task_key: "c-inject", card_path: fx.cardRelPath, description: "work" });
		const taskMd = fs.readFileSync(path.join(taskDirOf(fx.root, "c-inject"), "task.md"), "utf8");
		const block = claimsBlock([ROW_GREP, ROW_MANUAL]);

		expect(taskMd).toContain(block);
		const seedStart = taskMd.indexOf(CARD_SEED_MARKER);
		const claimsStart = taskMd.indexOf("<!-- mw-claims: v1 -->");
		const disclaimer = taskMd.indexOf(CARD_SEED_DISCLAIMER);
		const seedEnd = taskMd.indexOf(CARD_SEED_MARKER_END);
		expect(seedStart).toBeGreaterThanOrEqual(0);
		expect(claimsStart).toBeGreaterThan(seedStart);
		expect(disclaimer).toBeGreaterThan(claimsStart);
		expect(seedEnd).toBeGreaterThan(disclaimer);
		// The settle path re-parses task.md, never the card (D-002).
		expect(parseClaimsBlock(taskMd).claims.map((claim) => claim.id)).toEqual(["C-01", "C-02"]);
		// Delivered exactly once: the block sits under the card's last H2, so the
		// heading-sliced extra body would otherwise carry a second copy.
		expect(taskMd.split("<!-- mw-claims: v1 -->").length - 1).toBe(1);
	});

	it("closes an unterminated block so the injected copy cannot swallow the body", () => {
		const unterminated = ["<!-- mw-claims: v1 -->", "| claim | 类型 |", "| --- | --- |", "| C-01 | grep |"].join(
			"\n",
		);
		const text = extractClaimsBlockText(`${unterminated}\n\n## 后续\n\n正文\n`);
		expect(text.endsWith(CLAIMS_CLOSE)).toBe(true);
		expect(text).not.toContain("## 后续");
		expect(extractClaimsBlockText(codingCard([ROW_GREP]))).toContain(CLAIMS_CLOSE);
		expect(extractClaimsBlockText("no claims here\n")).toBe("");
	});
});

// ── 3. advisory receipt line ────────────────────────────────────────────────

describe("advisory claims receipt (design §5 G1)", () => {
	it("appends the [claims] line only when the card declares claims", async () => {
		const fx = setupDispatch([ROW_GREP, ROW_MANUAL, ROW_STRUCT]);
		const withClaims = await dispatch(fx, { task_key: "c-receipt", card_path: fx.cardRelPath, description: "work" });
		expect(withClaims).toContain("[claims] advisory claims=3 caps=18/196608 warnings=[none]");

		const bare = setupDispatch([]);
		const withoutClaims = await dispatch(bare, {
			task_key: "c-bare",
			card_path: bare.cardRelPath,
			description: "work",
		});
		expect(withoutClaims).not.toContain("[claims]");
	});

	it("renders the soft findings as warnings without refusing (advisory)", async () => {
		// 类型 grep but 判据 prefix `shape:` -> claim:C-01:type-prefix (soft, AC-001).
		const fx = setupDispatch(["| C-01 | grep | 卡不再吞 claims | 出现空块 | src/app.ts | shape: 3/3 | 1 |"]);
		const message = await dispatch(fx, { task_key: "c-soft", card_path: fx.cardRelPath, description: "work" });
		expect(message).toContain("Dispatched worker 'c-soft'");
		expect(message).toContain("warnings=[claim:C-01:type-prefix]");
		expect(fs.existsSync(taskDirOf(fx.root, "c-soft"))).toBe(true);
	});

	it("claimsReceiptLine is empty for a card without claims", () => {
		const gate = {
			ok: true,
			code: "dispatch-card" as const,
			resolvedPath: "",
			missing: [],
			headerPath: "",
			sha256: "",
			sections: { context: "", requirements: "", deliverables: "", extras: [] },
			claims: [],
			caps: null,
			warnings: [],
			claimsDeclared: false,
		};
		expect(claimsReceiptLine(gate)).toBe("");
	});

	it("a declared claims block that parses to nothing shouts instead of staying silent (T-07)", async () => {
		// `C-A1` is not a claim id (`C-<2+ digits>`), so every row is unparsable.
		// Before this guard the receipt said nothing, no read_scope was rendered and
		// the review ran unbudgeted — the gate looked green while doing nothing.
		const fx = setupDispatch(["| C-A1 | grep | s | f | src/app.ts | grep: x | 2 |"]);
		const message = await dispatch(fx, { task_key: "c-unparsed", card_path: fx.cardRelPath, description: "work" });
		expect(message).toContain("Dispatched worker 'c-unparsed'");
		expect(message).toContain("claims=0(unparsed)");
		expect(message).toContain(":unparsable");
	});
});

// ── 4. grey release: MW_CLAIM_GATE ─────────────────────────────────────────

describe("MW_CLAIM_GATE grey release (T-02 requirement 4, D-006)", () => {
	it("enforce refuses a soft-only gap under dispatch-claims with zero side effects", async () => {
		process.env.MW_CLAIM_GATE = "enforce";
		const fx = setupDispatch(["| C-01 | grep | 卡不再吞 claims | 出现空块 | src/app.ts | shape: 3/3 | 1 |"]);
		const before = fx.store.readAll().length;
		const message = await dispatch(fx, { task_key: "c-enforce", card_path: fx.cardRelPath, description: "work" });
		expect(claimGateMode()).toBe("enforce");
		expect(message).toContain("[dispatch-claims]");
		expect(message).toContain("claim:C-01:type-prefix");
		expect(message).toContain("nothing was written.");
		expect(fs.existsSync(taskDirOf(fx.root, "c-enforce"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});

	it("an illegal value falls back to advisory (fail-open, D-006)", async () => {
		process.env.MW_CLAIM_GATE = "ENFORCED";
		const fx = setupDispatch(["| C-01 | grep | 卡不再吞 claims | 出现空块 | src/app.ts | shape: 3/3 | 1 |"]);
		const message = await dispatch(fx, { task_key: "c-typo", card_path: fx.cardRelPath, description: "work" });
		expect(claimGateMode()).toBe("advisory");
		expect(message).toContain("[claims] advisory");
		expect(message).toContain("Dispatched worker 'c-typo'");
	});

	it("advisory refuses nothing: a structurally incomplete claim rides as a warning (D-006)", async () => {
		// P-048: a gray-release gate that can still reject a card is a new way to
		// lose a dispatch on a table typo, so advisory only reports.
		const fx = setupDispatch(["| C-01 | grep | 卡不再吞 claims | 出现空块 | src/app.ts |  | 1 |"]);
		const before = fx.store.readAll().length;
		const message = await dispatch(fx, { task_key: "c-struct", card_path: fx.cardRelPath, description: "work" });
		expect(message).toContain("Dispatched worker 'c-struct'");
		expect(message).toContain("[claims] advisory");
		expect(message).toContain("warnings=[claim:C-01:judgement]");
		expect(message).not.toContain("[dispatch-claims]");
		expect(fs.existsSync(taskDirOf(fx.root, "c-struct"))).toBe(true);
		expect(fx.store.readAll()).toHaveLength(before + 1);
	});

	it("enforce refuses the same structural gap with zero side effects", async () => {
		process.env.MW_CLAIM_GATE = "enforce";
		const fx = setupDispatch(["| C-01 | grep | 卡不再吞 claims | 出现空块 | src/app.ts |  | 1 |"]);
		const before = fx.store.readAll().length;
		const message = await dispatch(fx, { task_key: "c-struct-e", card_path: fx.cardRelPath, description: "work" });
		expect(message).toContain("[dispatch-claims]");
		expect(message).toContain("claim:C-01:judgement");
		expect(fs.existsSync(taskDirOf(fx.root, "c-struct-e"))).toBe(false);
		expect(fx.store.readAll()).toHaveLength(before);
	});
});

// ── 6. the /worker command path carries the same rendering ────────────────

describe("/worker command path (T-02 requirement 3)", () => {
	it("renders read_scope + caps and appends the [claims] receipt line", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, "src"), { recursive: true });
		fs.writeFileSync(path.join(root, "src", "app.ts"), "export const app = 1;\n", "utf8");
		fs.mkdirSync(path.join(root, "_scratch", "tasks"), { recursive: true });
		fs.writeFileSync(path.join(root, "_scratch", "tasks", CARD_NAME), codingCard([ROW_GREP, ROW_MANUAL]), "utf8");
		const store = new WorkerStore(root);
		const notifications: string[] = [];
		const commands = new Map<string, (args: string, ctx: unknown) => Promise<void> | void>();
		const pi = {
			registerCommand: (
				name: string,
				command: { handler: (args: string, ctx: unknown) => Promise<void> | void },
			) => {
				commands.set(name, command.handler);
			},
			registerTool: () => {},
			appendEntry: () => {},
			sendUserMessage: () => {},
			sendMessage: () => {},
		} as unknown as ExtensionAPI;
		registerWorkerCommands(pi, store, new IndexStore(root), root, { key: "_scratch" }, root);
		const handler = commands.get("worker");
		if (!handler) throw new Error("/worker not registered");
		const ctx = {
			hasUI: true,
			ui: { notify: (message: string) => notifications.push(message), setWidget: () => {} },
		};
		await handler(`pi --type coding --card _scratch/tasks/${CARD_NAME} work`, ctx);
		const receipt = notifications.join("\n");
		expect(receipt).toContain("[claims] advisory claims=2 caps=12/131072");
		const [taskKey] = store.readAll().map((row) => row.taskKey);
		expect(taskKey).toBeDefined();
		const taskMd = fs.readFileSync(path.join(root, "_scratch", "workers", taskKey ?? "", "task.md"), "utf8");
		expect(taskMd).toContain(
			"read_scope:\n  - .agenticdoc/_scratch\n  - .agenticdoc/goal.md\n  - src/app.ts\n" +
				"l2_read_file_cap: 12\nl2_read_byte_cap: 131072\n",
		);
	});
});

// ── 5. no-claims cards keep the pre-T-02 bytes (AC-007) ─────────────────────

describe("no-claims byte identity (AC-007)", () => {
	it("a card without a claims block renders the pre-T-02 task.md and receipt", async () => {
		const fx = setupDispatch([]);
		const before = fx.store.readAll().length;
		const description = "实现 claims 渲染并写测试。";
		const message = await dispatch(fx, { task_key: "c-none", card_path: fx.cardRelPath, description });
		expect(fx.store.readAll()).toHaveLength(before + 1);

		const sha = cardDigest(fx.cardAbsPath);
		const frontmatter =
			`type: coding\ncard_path: tasks/${CARD_NAME}\ncard_sha256: ${sha}\n` +
			`${ENVELOPE_PRODUCER_KEY}: ${DISPATCH_PRODUCER_ID}@${VERSION}\nwrite_face: 仅本任务目录。\n`;
		const gate = readDispatchCard({
			cardPath: fx.cardAbsPath,
			ownerKey: "_scratch",
			agenticdocRoot: fx.root,
			projectDir: fx.root,
		});
		expect(gate.ok).toBe(true);
		expect(gate.claims).toEqual([]);
		expect(gate.caps).toBeNull();
		const expected = `${frontmatter}\n${renderCardSeedSections(gate.sections)}\n\n${description}\n`;
		const actual = fs.readFileSync(path.join(taskDirOf(fx.root, "c-none"), "task.md"), "utf8");
		expect(actual).toBe(expected);
		// No new frontmatter fields, no claims carrier, no receipt line.
		expect(actual).not.toContain("read_scope:");
		expect(actual).not.toContain("l2_read_file_cap:");
		expect(actual).not.toContain("l2_read_byte_cap:");
		expect(actual).not.toContain("mw-claims");
		expect(message).not.toContain("[claims]");
	});

	it("writeDispatchTaskMd writes no read-scope lines when no caps are passed", () => {
		const root = mkdtemp();
		const plain = writeDispatchTaskMd(
			{ agenticdocRoot: root, ownerKey: "_scratch" },
			{ taskKey: "c-direct", type: "coding", body: "正文", frontmatter: "type: coding\n" },
		);
		expect(fs.readFileSync(plain.path, "utf8")).toBe("type: coding\n\n正文\n");
		const capped = writeDispatchTaskMd(
			{ agenticdocRoot: root, ownerKey: "_scratch" },
			{
				taskKey: "c-directed",
				type: "coding",
				body: "正文",
				frontmatter: "type: coding\n",
				readScope: [".agenticdoc/_scratch", ".agenticdoc/goal.md"],
				readFileCap: 4,
				readByteCap: 196608,
			},
		);
		expect(fs.readFileSync(capped.path, "utf8")).toBe(
			"type: coding\nread_scope:\n  - .agenticdoc/_scratch\n  - .agenticdoc/goal.md\n" +
				"l2_read_file_cap: 4\nl2_read_byte_cap: 196608\n\n正文\n",
		);
	});
});
