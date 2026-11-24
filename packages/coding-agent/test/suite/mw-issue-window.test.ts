/**
 * mw-issue-window.test.ts — T-05 of key `mw-issue-feedback`: the pi-window
 * `/mw issue` WIRING in `pm/ui-bridge.ts` (real host facts, scrollable FULL-text
 * TUI overlay, dev-root gating, worker/RPC/no-UI refusal).
 *
 * Frozen T-01..T-04 modules are consumed, never forked. This suite proves the
 * wiring's OWN surface, which T-04 deliberately left to T-05 (see its report
 * §7/§8):
 *  - `issueWindowFacts` derives role/trustedWindow/writeAuthorized from the REAL
 *    window (PM registration path, non-worker env, mode=tui, hasUI) — no default
 *    true, no model/argv self-assertion, no RPC/print/no-UI trust.
 *  - `issueDevRootForSub` enables a dev actor ONLY when the canonical current
 *    project root equals the VALIDATED dev root; an ordinary project holding a
 *    pointer to the dev repo stays external and cannot register dev progress.
 *  - `runMwIssueCommand` / the `/mw` handler feed the frozen T-04 module a real
 *    `ctx.ui` adapter whose `present` is a scrollable FULL-text overlay (not a
 *    truncating notify), preserve the exact preview/confirm digest contract, and
 *    leave BOTH authority and local index untouched on cancel/exception/refusal.
 *
 * Evidence shape (per card): `test/suite/harness.ts` + faux provider (one real
 * command-dispatch integration case: no real/paid provider, zero provider
 * requests) + real `IssueStore` over temporary dev-repo/project/pointer fixtures
 * (no machine pointer, no shared table, no network, no bundle, no serve). A
 * no-call / sentinel spy store is used ONLY for pure call-level boundaries; the
 * positive submit/update evidence uses the real store. Worker/RPC/no-UI and the
 * PM-only registration path get explicit negative cases.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { visibleWidth } from "@earendil-works/pi-tui";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	createIssueCommandStore,
	type IssueCommandStore,
} from "../../src/extensions/agent-team-loop/pm/issue-command.ts";
import {
	ISSUE_PREVIEW_VIEWPORT_LINES,
	type IssueWireDeps,
	issueDevRootForSub,
	issueWindowFacts,
	MW_COMMAND_DESCRIPTION,
	registerMwCommands,
	runMwIssueCommand,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import type { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { REDACTION_MARK } from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	bindIssueDevRoot,
	ISSUE_DEV_ROOT_POINTER_BASENAME,
	ISSUE_DEV_ROOT_POINTER_DIR,
} from "../../src/extensions/agent-team-loop/shared/issue-root.ts";
import {
	ISSUE_EVENTS_DIR_BASENAME,
	ISSUE_LOCAL_DIR_PARTS,
	ISSUE_PENDING_DIR_BASENAME,
	type IssueIncomingListRequest,
	type IssueIncomingReadRequest,
	type IssueListRequest,
	type IssueProgressRequest,
	type IssueReplyRequest,
	type IssueRetryRequest,
	type IssueStatusRequest,
	IssueStore,
	type IssueSubmitRequest,
	issueAuthorityBasePath,
	issueLocalIndexPath,
	issueTextSha256,
} from "../../src/extensions/agent-team-loop/shared/issue-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, getAssistantTexts, type Harness } from "./harness.ts";

function verify(line: string): void {
	process.stdout.write(`[VERIFY] ${line}\n`);
}

// ── Synthetic constants (all offline, no real credential/version reading) ────

const NOW = "2026-11-12T21:15:00+08:00";
const VALID_ID = "fb-0123456789abcdef0123456789abcdef";
const BEARER_TOKEN = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const ENV_SENTINEL = "PLAIN-ENV-SENTINEL-7788";
const LONG_STEP = `1. 运行 /mw status；2. 重启 serve；3. 再查询 ${"step-".repeat(400)} END-OF-REPRO-STEPS`;
const LONG_ERROR = `ERROR serve-stale: ${"E".repeat(700)} Bearer ${BEARER_TOKEN} ${ENV_SENTINEL} END-OF-KEY-ERROR`;
const LONG_IMPACT = `影响：${"影响-".repeat(300)} END-OF-IMPACT`;

// ── Temp fixtures: a real dev repo + an ordinary project + an injected pointer ─

const tmpRoots: string[] = [];
const harnesses: Harness[] = [];
let savedWorkerTask: string | undefined;

beforeEach(() => {
	savedWorkerTask = process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_TASK; // default = clean PM window env
});

afterEach(() => {
	if (savedWorkerTask === undefined) delete process.env.PI_WORKER_TASK;
	else process.env.PI_WORKER_TASK = savedWorkerTask;
	delete process.env.MW_T05_ENV_SENTINEL;
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tmpRoots.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface Fixture {
	top: string;
	pointerFile: string;
	devRoot: string;
	projectA: string;
}

function makeDevRepo(root: string): void {
	fs.mkdirSync(path.join(root, "packages", "multi-workers"), { recursive: true });
	fs.writeFileSync(path.join(root, "packages", "multi-workers", "mw.py"), "# offline fixture\n", "utf8");
	fs.mkdirSync(path.join(root, "packages", "coding-agent", "src", "extensions", "agent-team-loop"), {
		recursive: true,
	});
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".agenticdoc", "goal.md"), "# Project Goal\n", "utf8");
}

function fixture(): Fixture {
	const top = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "mw-issue-window-")));
	tmpRoots.push(top);
	const home = path.join(top, "machine-home");
	fs.mkdirSync(path.join(home, ISSUE_DEV_ROOT_POINTER_DIR), { recursive: true });
	const devRoot = path.join(top, "mw-dev");
	makeDevRepo(devRoot); // creates the repo root + all three markers
	const projectA = path.join(top, "project-a");
	fs.mkdirSync(path.join(projectA, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(projectA, ".agenticdoc", "goal.md"), "# Project A goal\n", "utf8");
	return {
		top,
		pointerFile: path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME),
		devRoot: fs.realpathSync(devRoot),
		projectA: fs.realpathSync(projectA),
	};
}

/** Real T-02 binder from the dev repo's OWN window: writes exactly one pointer. */
function bindPointer(fx: Fixture): void {
	const result = bindIssueDevRoot({
		callerProjectRoot: fx.devRoot,
		candidateRoot: fx.devRoot,
		userConfirmed: true,
		pointerFile: fx.pointerFile,
		now: () => new Date(NOW),
	});
	if (!result.ok) throw new Error(`fixture bind failed: ${result.code}: ${result.reason}`);
}

function eventsDir(fx: Fixture): string {
	return path.join(issueAuthorityBasePath(fx.devRoot), ISSUE_EVENTS_DIR_BASENAME);
}

function authorityLogCount(fx: Fixture): number {
	if (!fs.existsSync(eventsDir(fx))) return 0;
	return fs.readdirSync(eventsDir(fx)).filter((name) => name.endsWith(".jsonl")).length;
}

function pendingCount(projectRoot: string): number {
	const dir = path.join(projectRoot, ...ISSUE_LOCAL_DIR_PARTS, ISSUE_PENDING_DIR_BASENAME);
	if (!fs.existsSync(dir)) return 0;
	return fs.readdirSync(dir).filter((name) => name.endsWith(".json")).length;
}

function localIndexBytes(projectRoot: string): string {
	const file = issueLocalIndexPath(projectRoot);
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
}

// ── Stores: a no-call spy for boundaries, a real-store recorder for writes ────

/** Boundary-only spy. Any method records + throws, so a reached write is provable
 * at call level AND surfaces as a store-failure text (never a silent write). */
class NoCallStore implements IssueCommandStore {
	readonly calls: string[] = [];
	private boom(method: string): never {
		this.calls.push(method);
		throw new Error(`NO_CALL:${method}`);
	}
	submit(): never {
		return this.boom("submit");
	}
	retry(): never {
		return this.boom("retry");
	}
	status(): never {
		return this.boom("status");
	}
	list(): never {
		return this.boom("list");
	}
	appendProgress(): never {
		return this.boom("appendProgress");
	}
	reply(): never {
		return this.boom("reply");
	}
	listIncoming(): never {
		return this.boom("listIncoming");
	}
	readIncoming(): never {
		return this.boom("readIncoming");
	}
}

/** Wraps the REAL IssueStore over temp fixtures and records the exact submit
 * request, so host facts / knownSecrets / preview digest are provable. */
class RecordingStore implements IssueCommandStore {
	readonly inner: IssueStore;
	readonly submitRequests: IssueSubmitRequest[] = [];
	constructor(projectRoot: string, pointerFile: string) {
		this.inner = new IssueStore({ projectRoot, env: {}, pointerFile });
	}
	submit(request: IssueSubmitRequest) {
		this.submitRequests.push(request);
		return this.inner.submit(request);
	}
	retry(request: IssueRetryRequest) {
		return this.inner.retry(request);
	}
	status(request: IssueStatusRequest) {
		return this.inner.status(request);
	}
	list(request: IssueListRequest) {
		return this.inner.list(request);
	}
	appendProgress(request: IssueProgressRequest) {
		return this.inner.appendProgress(request);
	}
	reply(request: IssueReplyRequest) {
		return this.inner.reply(request);
	}
	listIncoming(request: IssueIncomingListRequest) {
		return this.inner.listIncoming(request);
	}
	readIncoming(request: IssueIncomingReadRequest) {
		return this.inner.readIncoming(request);
	}
}

// ── Fake ExtensionUIContext: records full previews + captures the custom FULL
// ── text component so its scrolling/no-truncation behaviour is testable ───────

interface PreviewComponent {
	fullText: string;
	readonly lineCount: number;
	render(width: number): string[];
	invalidate(): void;
	handleInput?(data: string): void;
}

interface CapturedCustom {
	options: unknown;
	component: PreviewComponent;
}

interface ConfirmCall {
	title: string;
	message: string;
}

type PreviewFactory = (
	tui: { requestRender(): void },
	theme: unknown,
	keybindings: { matches(data: string, id: string): boolean },
	done: (result: undefined) => void,
) => unknown | Promise<unknown>;

class FakeIssueUI {
	hasUI: boolean;
	mode: string;
	readonly notifications: Array<{ message: string; type?: string }> = [];
	readonly confirms: ConfirmCall[] = [];
	readonly customs: CapturedCustom[] = [];
	readonly matchedKeybindings: string[] = [];
	readonly doneResults: unknown[] = [];
	renderRequests = 0;
	readonly confirmAnswers: boolean[] = [];
	readonly inputAnswers: string[] = [];
	readonly editorAnswers: string[] = [];
	readonly selectAnswers: string[] = [];
	confirmThrow?: Error;
	customThrow?: Error;

	constructor(opts: { hasUI?: boolean; mode?: string } = {}) {
		this.hasUI = opts.hasUI ?? true;
		this.mode = opts.mode ?? "tui";
	}

	notify(message: string, type?: "info" | "warning" | "error"): void {
		this.notifications.push({ message, type });
	}

	async confirm(title: string, message: string): Promise<boolean> {
		this.confirms.push({ title, message });
		if (this.confirmThrow) throw this.confirmThrow;
		return this.confirmAnswers.shift() ?? false;
	}

	async input(): Promise<string | undefined> {
		return this.inputAnswers.shift() ?? "";
	}

	async editor(): Promise<string | undefined> {
		return this.editorAnswers.shift() ?? "";
	}

	async select(): Promise<string | undefined> {
		return this.selectAnswers.shift();
	}

	/** Real `ctx.ui.custom` seam: invokes the factory with a fake TUI/keybindings
	 * manager (matches() records every consulted, CONFIGURABLE keybinding id) and
	 * captures the returned FULL-text component. `present` resolves to void. */
	async custom(factory: unknown, options?: unknown): Promise<void> {
		if (this.customThrow) throw this.customThrow;
		const fn = factory as PreviewFactory;
		const tui = {
			requestRender: () => {
				this.renderRequests += 1;
			},
		};
		const keybindings = {
			matches: (data: string, id: string): boolean => {
				this.matchedKeybindings.push(id);
				return data === id; // tests feed the keybinding id directly
			},
		};
		const done = (result: undefined): void => {
			this.doneResults.push(result);
		};
		const component = (await fn(tui, undefined, keybindings, done)) as PreviewComponent;
		this.customs.push({ options, component });
	}
}

function fakeCtx(ui: FakeIssueUI, projectDir: string): ExtensionCommandContext {
	return { mode: ui.mode, hasUI: ui.hasUI, cwd: projectDir, ui } as unknown as ExtensionCommandContext;
}

interface MwCommand {
	handler: (args: string, ctx: ExtensionCommandContext) => Promise<void>;
	summaries: string[];
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
}

/** Fake `pi` (registerCommand + sendMessage only): the real registerMwCommands
 * registers exactly the `mw` command here, so the issue branch is driven through
 * the ACTUAL registered handler (same pattern as decide-command.test.ts). */
function makeMw(projectDir: string, deps: IssueWireDeps): MwCommand {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const summaries: string[] = [];
	const pi = {
		registerCommand: (
			name: string,
			def: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, def.handler);
		},
		sendMessage: (message: { content: string }) => {
			summaries.push(message.content);
		},
	} as unknown as ExtensionAPI;
	registerMwCommands(
		pi,
		projectDir,
		new WorkerStore(projectDir),
		{} as AckStore,
		{ key: undefined },
		projectDir,
		deps,
	);
	const handler = commands.get("mw");
	if (!handler) throw new Error("/mw command not registered");
	return { handler, summaries, commands };
}

function field(key: string, value: string): string {
	return `${key}="${value.replaceAll('"', "'")}"`;
}

function reportArgs(): string {
	return [
		"issue",
		"report",
		field("title", "/mw status 重启后显示旧 serve"),
		field("impact", LONG_IMPACT),
		field("steps", LONG_STEP),
		field("error", LONG_ERROR),
	].join(" ");
}

function deps(fx: Fixture, store: IssueCommandStore): IssueWireDeps {
	return { store, pointerFile: fx.pointerFile, now: () => NOW };
}

// ── 1. issueWindowFacts — REAL TUI PM provenance ──────────────────────────────

describe("issueWindowFacts — real PM/TUI window provenance (no default true)", () => {
	it("a tui+hasUI PM window is the only granting combination", () => {
		const ok = issueWindowFacts({ mode: "tui", hasUI: true }, {});
		expect(ok).toEqual({ role: "pm", trustedWindow: true, writeAuthorized: true, reason: null });
		// Forged model/argv claims on the context are NOT read (signature is a
		// Pick of mode|hasUI); identity never comes from a caller assertion.
		const forged = issueWindowFacts(
			{ mode: "tui", hasUI: true, role: "worker", trustedWindow: false } as unknown as {
				mode: "tui";
				hasUI: boolean;
			},
			{},
		);
		expect(forged.trustedWindow).toBe(true);
		verify("facts: tui+hasUI=grant forged-fields-ignored");
	});

	it("a worker window (PI_WORKER_TASK) is refused even with tui+hasUI+forged pm", () => {
		const refused = issueWindowFacts({ mode: "tui", hasUI: true } as unknown as { mode: "tui"; hasUI: boolean }, {
			PI_WORKER_TASK: "E:/fixture/worker/task.md",
		});
		expect(refused.role).toBe("unknown");
		expect(refused.trustedWindow).toBe(false);
		expect(refused.writeAuthorized).toBe(false);
		expect(refused.reason).toContain("worker");
		verify("facts: worker=refuse");
	});

	it("RPC / print / json / unknown modes are refused even with hasUI", () => {
		for (const mode of ["rpc", "print", "json", "headless-mode"]) {
			const refused = issueWindowFacts({ mode, hasUI: true } as unknown as { mode: "tui"; hasUI: boolean }, {});
			expect(refused.role).toBe("unknown");
			expect(refused.writeAuthorized).toBe(false);
			expect(refused.reason).toContain("mode=tui");
		}
		verify("facts: non-tui modes=refuse");
	});

	it("a tui window without UI is refused", () => {
		const refused = issueWindowFacts({ mode: "tui", hasUI: false }, {});
		expect(refused.trustedWindow).toBe(false);
		expect(refused.reason).toContain("UI");
		verify("facts: no-UI=refuse");
	});
});

// ── 2. issueDevRootForSub — validated dev root only ───────────────────────────

describe("issueDevRootForSub — dev actor only from the validated dev root's own window", () => {
	it("an ordinary project holding a pointer to the dev repo stays external: update refused, bind is only a candidate", () => {
		const fx = fixture();
		bindPointer(fx);
		// projectA != bound devRoot => mode=external => NO devRoot for update.
		expect(issueDevRootForSub("update", fx.projectA, fx.pointerFile)).toBeNull();
		// bind returns the CURRENT project root as an explicit first-time
		// candidate; it is never silently promoted to the authority root.
		expect(issueDevRootForSub("bind", fx.projectA, fx.pointerFile)).toBe(fx.projectA);
		// the dev repo's own window resolves mode=local => a real canonical devRoot
		// (compare via native realpath: the returned long path and the fixture's
		// short-path alias are the SAME directory on Windows).
		const local = issueDevRootForSub("update", fx.devRoot, fx.pointerFile);
		expect(local).not.toBeNull();
		expect(fs.realpathSync.native(local ?? "")).toBe(fs.realpathSync.native(fx.devRoot));
		verify("devRoot: external-update=null bind=candidate local-update=canonicalRoot");
	});

	it("an unconfigured pointer grants no devRoot (no cwd/root guessing)", () => {
		const fx = fixture();
		const missing = path.join(fx.top, "no-such-pointer.json");
		expect(issueDevRootForSub("update", fx.devRoot, missing)).toBeNull();
		verify("devRoot: unconfigured-pointer=null");
	});

	it("report / retry / status / reply never receive a devRoot", () => {
		const fx = fixture();
		bindPointer(fx);
		for (const sub of ["report", "retry", "status", "reply"] as const) {
			expect(issueDevRootForSub(sub, fx.devRoot, fx.pointerFile)).toBeNull();
		}
		expect(issueDevRootForSub(null, fx.devRoot, fx.pointerFile)).toBeNull();
		verify("devRoot: read/report subs=null");
	});
});

// ── 3. /mw issue dispatch + real-store temp fixtures ─────────────────────────

describe("/mw issue command wiring (registered handler + real IssueStore fixtures)", () => {
	it("help/description documents issue without dropping any existing /mw subcommand", async () => {
		const fx = fixture();
		const spy = new NoCallStore();
		const mw = makeMw(fx.projectA, deps(fx, spy));
		const ui = new FakeIssueUI();
		await mw.handler("bogus", fakeCtx(ui, fx.projectA));
		const usage = ui.notifications.at(-1)?.message ?? "";
		expect(usage).toContain("issue report|retry|status|update|reply|bind");
		// MW_COMMAND_DESCRIPTION still lists every original subcommand; the usage
		// line never carried context/concurrency/proxy, so only assert those that
		// were already present there (no existing /mw behaviour removed).
		for (const original of ["context", "concurrency", "proxy", "decide", "rag", "run-detached", "ack"]) {
			expect(MW_COMMAND_DESCRIPTION).toContain(original);
		}
		for (const inUsage of ["decide", "rag", "run-detached", "ack"]) {
			expect(usage).toContain(inUsage);
		}
		expect(MW_COMMAND_DESCRIPTION).toContain("issue");
		expect(spy.calls).toEqual([]);
		verify("help: issue documented, original subcommands preserved");
	});

	it("PM TUI report: exact multi-KB FULL preview in a scrollable custom overlay + real store write + digest contract", async () => {
		const fx = fixture();
		bindPointer(fx);
		process.env.MW_T05_ENV_SENTINEL = ENV_SENTINEL; // must NOT be auto-collected as a secret
		const store = new RecordingStore(fx.projectA, fx.pointerFile);
		const mw = makeMw(fx.projectA, deps(fx, store));
		const ui = new FakeIssueUI();
		ui.confirmAnswers.push(true);
		await mw.handler(reportArgs(), fakeCtx(ui, fx.projectA));

		// (1) exact FULL preview == confirm message == overlay fullText == request.preview
		expect(ui.confirms).toHaveLength(1);
		const preview = ui.confirms[0].message;
		expect(preview.length).toBeGreaterThan(3000); // several KB, not a summary
		for (const marker of ["END-OF-REPRO-STEPS", "END-OF-KEY-ERROR", "END-OF-IMPACT"]) {
			expect(preview).toContain(marker); // no truncation
		}
		expect(store.submitRequests).toHaveLength(1); // real store write happened
		const request = store.submitRequests[0];
		expect(preview).toBe(request.preparation.preview);
		expect(ui.customs.length).toBeGreaterThanOrEqual(1);
		expect(ui.customs[0].component.fullText).toBe(preview); // scrollable overlay got the EXACT text

		// (2) T-04 exact preview/confirmation digest contract preserved.
		expect(request.confirmation.previewSha256).toBe(request.preparation.previewSha256);
		expect(request.confirmation.previewSha256).toBe(issueTextSha256(preview));
		expect(request.confirmation.confirmed).toBe(true);

		// (3) REAL host facts flowed to the store actor (no default/mock true).
		expect(request.actor.role).toBe("pm");
		expect(request.actor.scope).toBe("project");
		expect(request.actor.trustedWindow).toBe(true);
		expect(request.actor.writeAuthorized).toBe(true);

		// (4) knownSecrets is ONLY caller-supplied transient data (empty here):
		// no auth/env scan, so an env-sentinel value is NOT auto-redacted, while
		// high-confidence token shapes ARE scrubbed by the frozen model.
		expect(request.knownSecrets).toEqual([]);
		expect(preview).toContain(ENV_SENTINEL);
		expect(preview).not.toContain(BEARER_TOKEN);
		expect(preview).toContain(REDACTION_MARK);

		// (5) no fabricated install/serve/bundle readings: every window-observed
		// environment fact is an explicit unknown (fail-closed).
		const observed = request.preparation.card.scene.observedEnvironment;
		for (const obs of Object.values(observed)) {
			expect(obs.source).toBe("unknown");
			expect(obs.value).toBeNull();
		}

		// (6) the FULL-text surface is a real scrollable overlay (not just notify).
		const opts = ui.customs[0].options as {
			overlay?: boolean;
			overlayOptions?: { width?: unknown; maxHeight?: unknown; anchor?: unknown };
		};
		expect(opts.overlay).toBe(true);
		expect(opts.overlayOptions?.width).toBe("92%");
		expect(opts.overlayOptions?.maxHeight).toBe(ISSUE_PREVIEW_VIEWPORT_LINES + 4);
		expect(opts.overlayOptions?.anchor).toBe("center");

		// (7) scroll reaches the tail, via configurable keybinding ids, with no
		// loss and every rendered line wrapped within the requested width.
		const comp = ui.customs[0].component;
		expect(comp.lineCount).toBeGreaterThan(30);
		const width = 60;
		const frames: string[] = [];
		const seenHeaders = new Set<string>();
		for (let i = 0; i < 300; i++) {
			const frame = comp.render(width);
			frames.push(...frame);
			const header = frame[0] ?? "";
			if (seenHeaders.has(header)) break; // scrollTop clamped at the bottom
			seenHeaders.add(header);
			comp.handleInput?.("tui.select.pageDown");
		}
		const allRendered = frames.join("\n");
		expect(allRendered).toContain("END-OF-REPRO-STEPS");
		expect(allRendered).toContain("END-OF-KEY-ERROR");
		for (const line of frames) expect(visibleWidth(line)).toBeLessThanOrEqual(width + 2);
		expect(ui.matchedKeybindings).toContain("tui.select.pageDown");
		expect(ui.renderRequests).toBeGreaterThan(0); // live re-render while scrolling
		// Esc/Enter/interrupt close the overlay through the same keybinding API.
		comp.handleInput?.("tui.select.cancel");
		expect(ui.doneResults).toHaveLength(1);

		// (8) a REAL authority record was written to the temp dev repo.
		expect(authorityLogCount(fx)).toBeGreaterThanOrEqual(1);
		verify(`report: preview_bytes=${preview.length} lineCount=${comp.lineCount} writes=1 digest=ok envScan=none`);
	});

	it("cancel (confirm !== true) performs ZERO writes", async () => {
		const fx = fixture();
		bindPointer(fx);
		const store = new RecordingStore(fx.projectA, fx.pointerFile);
		const mw = makeMw(fx.projectA, deps(fx, store));
		const ui = new FakeIssueUI();
		ui.confirmAnswers.push(false); // explicit cancel
		await mw.handler(reportArgs(), fakeCtx(ui, fx.projectA));
		expect(store.submitRequests).toEqual([]);
		expect(authorityLogCount(fx)).toBe(0);
		expect(pendingCount(fx.projectA)).toBe(0);
		expect(localIndexBytes(fx.projectA)).toBe("");
		// The unconfirmed result's FULL text ("未提交") is delivered through the
		// present()/custom surface; notify() carries only the short reason.
		const fullText = ui.customs.map((c) => c.component.fullText).join("\n");
		expect(fullText).toContain("未提交");
		expect(fullText).toContain("共享端新增记录数为 0");
		verify("cancel: zero authority/pending/local-index writes");
	});

	it("a thrown confirm dialog performs ZERO writes", async () => {
		const fx = fixture();
		bindPointer(fx);
		const store = new RecordingStore(fx.projectA, fx.pointerFile);
		const mw = makeMw(fx.projectA, deps(fx, store));
		const ui = new FakeIssueUI();
		ui.confirmThrow = new Error("dialog exploded");
		await mw.handler(reportArgs(), fakeCtx(ui, fx.projectA));
		expect(store.submitRequests).toEqual([]);
		expect(authorityLogCount(fx)).toBe(0);
		expect(pendingCount(fx.projectA)).toBe(0);
		verify("exception(confirm): zero writes");
	});

	it("a thrown full-text preview surface performs ZERO writes", async () => {
		const fx = fixture();
		bindPointer(fx);
		const store = new RecordingStore(fx.projectA, fx.pointerFile);
		const mw = makeMw(fx.projectA, deps(fx, store));
		const ui = new FakeIssueUI();
		ui.customThrow = new Error("overlay exploded");
		await mw.handler(reportArgs(), fakeCtx(ui, fx.projectA));
		expect(store.submitRequests).toEqual([]);
		expect(authorityLogCount(fx)).toBe(0);
		expect(pendingCount(fx.projectA)).toBe(0);
		verify("exception(preview): zero writes");
	});

	it("worker / RPC / print / unknown-mode / no-UI windows are refused with ZERO store calls", async () => {
		const cases: Array<{ label: string; worker?: boolean; mode: string; hasUI: boolean }> = [
			{ label: "worker", worker: true, mode: "tui", hasUI: true },
			{ label: "rpc", mode: "rpc", hasUI: true },
			{ label: "print", mode: "print", hasUI: true },
			{ label: "json", mode: "json", hasUI: true },
			{ label: "unknown-mode", mode: "weird", hasUI: true },
			{ label: "no-UI", mode: "tui", hasUI: false },
		];
		for (const c of cases) {
			const fx = fixture();
			const spy = new NoCallStore();
			const mw = makeMw(fx.projectA, deps(fx, spy));
			const ui = new FakeIssueUI({ mode: c.mode, hasUI: c.hasUI });
			if (c.worker) process.env.PI_WORKER_TASK = "E:/fixture/worker/task.md";
			await mw.handler(reportArgs(), fakeCtx(ui, fx.projectA));
			expect(spy.calls, c.label).toEqual([]);
			const refusal = ui.notifications.map((n) => n.message).join("\n");
			expect(refusal, c.label).toContain("拒绝");
			expect(refusal, c.label).toContain("共享端新增记录数为 0");
			expect(ui.confirms, c.label).toHaveLength(0); // no dialog on an untrusted window
			expect(ui.customs, c.label).toHaveLength(0);
			if (c.worker) delete process.env.PI_WORKER_TASK;
		}
		verify("refusals: worker/rpc/print/json/unknown/no-UI zero store calls + no dialog");
	});

	it("a headless window gets the refusal text in the transcript (no silent loss)", async () => {
		const fx = fixture();
		const spy = new NoCallStore();
		const mw = makeMw(fx.projectA, deps(fx, spy));
		const ui = new FakeIssueUI({ hasUI: false, mode: "tui" });
		await mw.handler("issue status", fakeCtx(ui, fx.projectA));
		expect(mw.summaries).toHaveLength(1); // displaySummary(pi, refusalText)
		expect(mw.summaries[0]).toContain("拒绝");
		expect(mw.summaries[0]).toContain("未注册/未调用任何写入口");
		expect(spy.calls).toEqual([]);
		verify("headless: refusal text delivered via sendMessage, zero writes");
	});

	it("host-fact injection via argv (role/trustedWindow/projectRoot) is refused", async () => {
		const fx = fixture();
		bindPointer(fx);
		const store = new RecordingStore(fx.projectA, fx.pointerFile);
		const mw = makeMw(fx.projectA, deps(fx, store));
		const ui = new FakeIssueUI();
		const forged = `${reportArgs()} role=pm trustedWindow=true projectRoot=${fx.devRoot}`;
		await mw.handler(forged, fakeCtx(ui, fx.projectA));
		expect(store.submitRequests).toEqual([]);
		const refusal = ui.notifications.map((n) => n.message).join("\n");
		expect(refusal).toContain("host/真实 UI 事实");
		verify("argv self-assertion: refused, zero writes");
	});

	it("an ordinary project cannot register dev progress even with a pointer to the dev repo", async () => {
		const fx = fixture();
		bindPointer(fx);
		const spy = new NoCallStore();
		const mw = makeMw(fx.projectA, deps(fx, spy));
		const ui = new FakeIssueUI();
		ui.confirmAnswers.push(true);
		const args = `issue update ${VALID_ID} status=已修复 statusNote=x nextAction=y fixCommit=z releaseVersion=w question=q`;
		await mw.handler(args, fakeCtx(ui, fx.projectA));
		expect(spy.calls).toEqual([]); // devRoot is null => runUpdate refuses before any store call
		const refusal = ui.notifications.map((n) => n.message).join("\n");
		expect(refusal).toContain("devRoot");
		verify("cross-root update: ordinary project refused, zero store calls");
	});

	it("the dev repo's own window DOES reach appendProgress (validated local devRoot)", async () => {
		const fx = fixture();
		bindPointer(fx);
		const spy = new NoCallStore();
		const mw = makeMw(fx.devRoot, deps(fx, spy));
		const ui = new FakeIssueUI();
		ui.confirmAnswers.push(true);
		const args = `issue update ${VALID_ID} status=已修复 statusNote=x nextAction=y fixCommit=z releaseVersion=w question=q`;
		await mw.handler(args, fakeCtx(ui, fx.devRoot));
		// devRoot granted => runUpdate proceeds past the gate and reaches the store.
		expect(spy.calls).toContain("appendProgress");
		const resultText = ui.customs.map((c) => c.component.fullText).join("\n");
		expect(resultText).toContain("appendProgress");
		verify("dev-root update: reached appendProgress (dev actor granted)");
	});

	it("bind works first-time from the dev repo's own window; cancel zero-writes; an ordinary project is never the authority", async () => {
		// (a) first-time explicit bind from the dev repo's own window.
		const fx = fixture();
		const spy = new NoCallStore();
		const mwOk = makeMw(fx.devRoot, deps(fx, spy));
		const uiOk = new FakeIssueUI();
		uiOk.confirmAnswers.push(true);
		await mwOk.handler("issue bind", fakeCtx(uiOk, fx.devRoot));
		expect(fs.existsSync(fx.pointerFile)).toBe(true);
		expect(spy.calls).toEqual([]); // bind writes ONLY the pointer, never the store
		const pointer = JSON.parse(fs.readFileSync(fx.pointerFile, "utf8")) as { canonical_dev_root: string };
		expect(pointer.canonical_dev_root.toLowerCase()).toContain("mw-dev");
		expect(uiOk.confirms[0].message).toContain("不是 OS 权限授予");

		// (b) cancel leaves NO pointer.
		const fx2 = fixture();
		const mwCancel = makeMw(fx2.devRoot, deps(fx2, new NoCallStore()));
		const uiCancel = new FakeIssueUI();
		uiCancel.confirmAnswers.push(false);
		await mwCancel.handler("issue bind", fakeCtx(uiCancel, fx2.devRoot));
		expect(fs.existsSync(fx2.pointerFile)).toBe(false);

		// (c) an ordinary project's own window cannot declare itself the authority.
		const fx3 = fixture();
		const mwForeign = makeMw(fx3.projectA, deps(fx3, new NoCallStore()));
		const uiForeign = new FakeIssueUI();
		uiForeign.confirmAnswers.push(true);
		await mwForeign.handler("issue bind", fakeCtx(uiForeign, fx3.projectA));
		expect(fs.existsSync(fx3.pointerFile)).toBe(false); // marker validation rejects it
		verify("bind: dev-window=written cancel=zero foreign-project=never-authority");
	});
});

// ── 4. Faux-provider harness: real registered command, no real provider ───────

describe("/mw issue — faux-provider suite harness integration", () => {
	it("dispatching /mw issue makes ZERO provider requests and a print/headless window is refused with zero writes", async () => {
		const fx = fixture();
		const spy = new NoCallStore();
		const captured: string[] = [];
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					// REAL /mw command wiring on the harness's ExtensionAPI.
					registerMwCommands(
						pi,
						fx.projectA,
						new WorkerStore(fx.projectA),
						{} as AckStore,
						{ key: undefined },
						fx.projectA,
						deps(fx, spy),
					);
					// Probe captures runMwIssueCommand's return text from a REAL command ctx.
					pi.registerCommand("issueprobe", {
						description: "probe",
						handler: async (args, ctx) => {
							captured.push(await runMwIssueCommand(ctx, fx.projectA, args, deps(fx, spy)));
						},
					});
				},
			],
		});
		harnesses.push(harness);
		harness.setResponses([fauxAssistantMessage("MODEL-SHOULD-NOT-RUN")]);

		await harness.session.prompt("/issueprobe status");
		await harness.session.prompt("/mw issue status");

		// A registered command is dispatched immediately; the faux model response
		// is never consumed => no real/paid provider request was made.
		expect(harness.getPendingResponseCount()).toBe(1);
		expect(getAssistantTexts(harness).join("\n")).not.toContain("MODEL-SHOULD-NOT-RUN");
		// The harness command ctx is print/headless: the trusted-window gate refuses.
		expect(captured).toHaveLength(1);
		expect(captured[0]).toContain("拒绝");
		expect(captured[0]).toContain("不是可信人类窗口");
		expect(spy.calls).toEqual([]); // zero writes from BOTH driven commands
		verify("harness: /mw dispatched via faux provider, zero provider requests, headless refused, zero writes");
	});
});

// ── 5. Production store + PM-only registration path ──────────────────────────

describe("production store + PM-only write-entry registration", () => {
	it("createIssueCommandStore never overrides env (store keeps process.env for its own PI_WORKER_TASK gate)", () => {
		const fx = fixture();
		const store = createIssueCommandStore(fx.projectA) as IssueStore;
		expect(store.env).toBe(process.env);
		verify("production store: env not overridden");
	});

	it("worker-mode activation never registers /mw issue; registerMwCommands is PM-only", () => {
		const srcDir = fileURLToPath(new URL("../../src/extensions/agent-team-loop/", import.meta.url));
		const indexSrc = fs.readFileSync(path.join(srcDir, "index.ts"), "utf8");
		const workerSrc = fs.readFileSync(path.join(srcDir, "worker", "worker-mode.ts"), "utf8");
		const orchestratorSrc = fs.readFileSync(path.join(srcDir, "pm", "pm-orchestrator.ts"), "utf8");
		// worker-mode.ts references neither the registration nor the write entry.
		expect(workerSrc).not.toContain("registerMwCommands");
		expect(workerSrc).not.toContain("runMwIssueCommand");
		// The single call site lives inside pmActivate (PM branch of index.ts).
		expect((orchestratorSrc.match(/registerMwCommands\(/g) ?? []).length).toBe(1);
		const branchStart = indexSrc.indexOf("if (taskPath) {");
		const pmCall = indexSrc.indexOf("pmActivate(pi,", branchStart);
		expect(branchStart).toBeGreaterThanOrEqual(0);
		expect(pmCall).toBeGreaterThan(branchStart);
		const workerBranch = indexSrc.slice(branchStart, pmCall);
		expect(workerBranch).toContain("workerModeActivate");
		expect(workerBranch).not.toContain("pmActivate");
		verify("registration: worker path has no write entry; registerMwCommands only in PM path");
	});
});
