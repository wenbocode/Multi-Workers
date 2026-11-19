/**
 * mw-window-claim-isolation T-16: final TS boundary regressions.
 *
 * Finding 1 (index-store.ts::isHeaderish): decorations must be recognized
 * PRECISELY. A 7-column pipe data row whose first cell is `-bad`, `#bad`, empty,
 * or the legal key `Key` must be parsed as a ROW, never hidden as a comment or
 * the table header. Illegal ACTIVE rows (-bad / #bad / empty) must be refused
 * with ZERO writes on claim/upsert (validated on the ORIGINAL active input,
 * before self-demotion), while a legal active `Key` row must be preserved and
 * enter the full projection. Real headers/separators/comments/blank lines and
 * D-002 set dedupe stay supported.
 *
 * Finding 2 (pm/ui-bridge.ts::registerPmKeyCommands "new"): the handler must
 * honor the REAL takeOverKey result.ok. On refusal/blockedBy it must NOT
 * setWindowWatch / append a claimed entry / notify "Created and claimed"; the
 * success control still creates a claimed watch.
 *
 * Fully offline: faux-provider harness (no real model), real IndexStore.claim,
 * real takeOverKey/claimState, real registerPmKeyCommands handler, real shared
 * index.lock. Only `pi` (registerCommand/appendEntry) and `ctx.ui.notify` are
 * stubs; NO identity predicate, claim, permission or model is mocked. No
 * decision/claim/sign tool, no build/install/restart/commit.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import {
	foreignLiveClaimRefusal,
	type PmWatchState,
	registerPmKeyCommands,
	resolveOwnerKeyWithSync,
	WATCH_ENTRY_TYPE,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { acquireLock } from "../../src/extensions/agent-team-loop/shared/file-lock.ts";
import {
	IndexAuthorityError,
	type IndexEntry,
	type IndexStatus,
	IndexStore,
	readIndexMdActiveKeys,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { createHarness, type Harness } from "./harness.ts";

const HEADER = "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |";
const SEPARATOR = "|-----|--------|-------|---------|------|------|---------|";

const bases: string[] = [];
let harness: Harness | undefined;

beforeAll(async () => {
	harness = await createHarness();
});

afterAll(() => {
	harness?.cleanup();
});

afterEach(() => {
	for (const base of bases.splice(0)) fs.rmSync(base, { recursive: true, force: true });
});

/** Nested root => IndexStore's <root>/../.mw/index.lock is PRIVATE per test
 * (no contention with other test files / parallel windows sharing os.tmpdir()). */
function mkRoot(): string {
	const base = fs.mkdtempSync(path.join(os.tmpdir(), "mw-wcfb-"));
	const root = path.join(base, "agenticdoc");
	fs.mkdirSync(root, { recursive: true });
	bases.push(base);
	return root;
}

function lockPathFor(root: string): string {
	return path.join(root, "..", ".mw", "index.lock");
}

function entry(
	key: string,
	status: IndexStatus,
	claimId: string,
	updated = "2026-01-01T00:00:00Z",
	phase = "EXECUTE",
	deps = "-",
	desc = "row",
): IndexEntry {
	return { key, status, phase, claimId, deps, desc, updated };
}

function line(e: IndexEntry): string {
	return `| ${[e.key, e.status, e.phase, e.claimId, e.deps, e.desc, e.updated].join(" | ")} |`;
}

function seedRaw(root: string, content: string): void {
	fs.writeFileSync(path.join(root, "_index.parallel"), content, "utf8");
}

function readAuthority(root: string): string {
	return fs.readFileSync(path.join(root, "_index.parallel"), "utf8");
}

function canonicalIndexMd(keys: readonly string[]): string {
	return `# AgenticTask Index\n\nactive_keys: [${keys.map((k) => JSON.stringify(k)).join(", ")}]\n`;
}

function snapshot(root: string): { authority: string; projection: string | null } {
	const mdPath = path.join(root, "_index.md");
	const projection = fs.existsSync(mdPath) && fs.statSync(mdPath).isFile() ? fs.readFileSync(mdPath, "utf8") : null;
	return { authority: readAuthority(root), projection };
}

function activeHarness(): Harness {
	if (!harness) throw new Error("faux harness not initialized");
	return harness;
}

interface FakePi {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	entries: Array<{ customType: string; data: unknown }>;
}

function fakePi(): FakePi {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const entries: Array<{ customType: string; data: unknown }> = [];
	const pi = {
		registerCommand: (name: string, opts: { handler: (a: string, c: ExtensionCommandContext) => Promise<void> }) => {
			commands.set(name, opts.handler);
		},
		registerTool: () => {},
		appendEntry: (customType: string, data: unknown) => {
			entries.push({ customType, data });
		},
		sendMessage: () => {},
	} as unknown as ExtensionAPI;
	return { pi, commands, entries };
}

function fakeCmdCtx(): { ctx: ExtensionCommandContext; notifications: string[] } {
	const notifications: string[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => notifications.push(message),
			setWidget: () => {},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

function registerNewHandler(
	store: IndexStore,
	root: string,
	watch: PmWatchState,
): { cmd: FakePi; handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> } {
	const cmd = fakePi();
	registerPmKeyCommands(cmd.pi, store, watch, () => {}, root);
	const handler = cmd.commands.get("pm-key");
	if (!handler) throw new Error("pm-key handler not registered");
	return { cmd, handler };
}

// ── Finding 1: strict header recognition + original-active validation ──────

describe("T16 finding 1 — precise header/separator + original active validation (index-store)", () => {
	it("F1-a: illegal active rows (-bad / #bad / empty key) refuse claim+upsert with ZERO writes", async () => {
		for (const badKey of ["-bad", "#bad", ""]) {
			const root = mkRoot();
			const badActive = line(entry(badKey, "active", "foreign:1"));
			const legal = line(entry("good", "idle", ""));
			seedRaw(root, `${[HEADER, SEPARATOR, badActive, legal].join("\n")}\n`);
			fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["STALE"]), "utf8");
			const before = snapshot(root);
			const store = new IndexStore(root);

			const outcome = await store.claim("new-self", "self:2", () => false);
			expect(outcome.ok, `claim bad=${JSON.stringify(badKey)}`).toBe(false);
			expect(outcome.refusal, `claim bad=${JSON.stringify(badKey)}`).toBe("invalid-active-authority-key");

			await expect(store.upsert(entry("other", "idle", ""))).rejects.toThrow(IndexAuthorityError);

			expect(snapshot(root)).toEqual(before);
			expect(readIndexMdActiveKeys(root)).toEqual(["STALE"]);
		}
		console.log(
			"[VERIFY] F1-a: bad_active_zero_write=true claim_refusal+upsert_throw=true projection_unchanged=true",
		);
	});

	it("F1-b: a legal active data row keyed 'Key' is parsed as data and fully projected", async () => {
		const root = mkRoot();
		const keyRow = line(entry("Key", "active", "foreign:1"));
		const good = line(entry("good", "active", "self:1"));
		seedRaw(root, `${[HEADER, SEPARATOR, keyRow, good].join("\n")}\n`);
		const store = new IndexStore(root);

		// Both the tolerant and strict reads must SEE 'Key' as a real data row,
		// not as the table header decoration.
		expect(store.readAll().map((e) => e.key)).toContain("Key");
		expect(store.readAuthorityRows().map((e) => e.key)).toContain("Key");

		await store.upsert(entry("third", "idle", ""));
		expect(readIndexMdActiveKeys(root)).toEqual(["Key", "good"]);
		expect(readAuthority(root)).toContain(keyRow);
		console.log("[VERIFY] F1-b: legal_Key_active_preserved=true full_projection=true header_not_confused=true");
	});

	it("F1-c: ORIGINAL illegal active input is refused BEFORE self-demotion (self AND foreign)", async () => {
		const self = "self-window:1";
		for (const owner of [self, "foreign:9"]) {
			const root = mkRoot();
			const badActive = line(entry("-bad", "active", owner));
			const legal = line(entry("good", "active", "foreign:1"));
			seedRaw(root, `${[HEADER, SEPARATOR, badActive, legal].join("\n")}\n`);
			fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["STALE"]), "utf8");
			const before = snapshot(root);
			const store = new IndexStore(root);

			// demoteOthers defaults true: a self-owned '-bad' active row would be
			// demoted to idle BEFORE the projection, escaping post-write output
			// validation. Validating the original input closes that escape.
			const outcome = await store.claim("new-self", self, () => false);
			expect(outcome.ok, `owner=${owner}`).toBe(false);
			expect(outcome.refusal, `owner=${owner}`).toBe("invalid-active-authority-key");
			expect(snapshot(root)).toEqual(before);
		}
		console.log("[VERIFY] F1-c: original_active_validated=true self_demote_escape_closed=true foreign_closed=true");
	});

	it("F1-g: owner/guard reads see the bad row and fail closed (no namespace leak)", () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRaw(
			root,
			`${[HEADER, SEPARATOR, line(entry("-bad", "active", self)), line(entry("good", "idle", ""))].join("\n")}\n`,
		);
		const store = new IndexStore(root);
		// The header fix makes the row VISIBLE to strict/tolerant reads.
		expect(store.readAll().map((e) => e.key)).toContain("-bad");
		expect(store.readAuthorityRows().map((e) => e.key)).toContain("-bad");

		const messages: string[] = [];
		const pi = {
			sendMessage: (m: string | { content?: string }) => {
				messages.push(typeof m === "string" ? m : (m.content ?? ""));
			},
		} as unknown as ExtensionAPI;
		// Owner read must not grant any namespace; the illegal active is not usable.
		expect(resolveOwnerKeyWithSync(pi, store, { key: undefined }, undefined, root)).toBe("_scratch");
		// Guard read for the illegal name itself is refused.
		expect(foreignLiveClaimRefusal(store, "-bad")).not.toBeNull();
		console.log("[VERIFY] F1-g: bad_row_visible_to_reads=true owner_scratch=true guard_refused=true");
	});

	it("F1-e CONTROL: real header / separator / standalone comment / blank lines still work", async () => {
		const root = mkRoot();
		const legal = line(entry("anchor", "active", "foreign:1"));
		seedRaw(root, `${["# Index Parallel", "", HEADER, SEPARATOR, legal].join("\n")}\n`);
		const store = new IndexStore(root);
		const outcome = await store.claim("new-self", "self:2", () => false);
		expect(outcome.ok).toBe(true);
		const after = readAuthority(root);
		expect(after).toContain("# Index Parallel");
		expect(after).toContain(HEADER);
		expect(after).toContain(SEPARATOR);
		expect(after).toContain(legal);
		expect(readIndexMdActiveKeys(root)).toEqual(["anchor", "new-self"]);
		console.log("[VERIFY] F1-e: header_support_preserved=true comment_blank_separator_ok=true projection_full=true");
	});

	it("F1-f CONTROL: D-002 set dedupe keeps the first spelling; identity duplicate stays refused", async () => {
		const root = mkRoot();
		seedRaw(
			root,
			`${[
				HEADER,
				SEPARATOR,
				line(entry("Alpha", "active", "self:1")),
				line(entry("alpha", "active", "self:1")),
			].join("\n")}\n`,
		);
		const store = new IndexStore(root);
		await store.upsert(entry("Gamma", "idle", ""));
		expect(readIndexMdActiveKeys(root)).toEqual(["Alpha"]); // set dedupe, first spelling
		const dup = await store.claim("Alpha", "self:2", () => false);
		expect(dup.ok).toBe(false);
		expect(dup.refusal).toBe("duplicate-target-key"); // identity duplicate is NOT deduped away
		console.log("[VERIFY] F1-f: set_dedupe_first_spelling=true identity_duplicate_refused=true");
	});
});

// ── Finding 2: /pm-key new must respect takeOverKey result.ok ──────────────

describe("T16 finding 2 — real /pm-key new handler honors takeOverKey result.ok", () => {
	it("F2-a: bad table => refusal visible, ZERO watch/persistence/success-notice/index change", async () => {
		const root = mkRoot();
		seedRaw(
			root,
			`${[HEADER, SEPARATOR, line(entry("-bad", "active", "foreign:1")), line(entry("good", "idle", ""))].join(
				"\n",
			)}\n`,
		);
		fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["STALE"]), "utf8");
		const before = snapshot(root);
		const store = new IndexStore(root);
		const watch: PmWatchState = { key: "prior-key" };
		const { cmd, handler } = registerNewHandler(store, root, watch);
		const { ctx, notifications } = fakeCmdCtx();

		await handler("new fresh", ctx);

		expect(notifications.some((n) => n.includes("Created and claimed"))).toBe(false);
		expect(notifications.some((n) => n.includes("invalid-active-authority-key"))).toBe(true);
		expect(watch.key).toBe("prior-key"); // original watch unchanged
		expect(cmd.entries.length).toBe(0); // no persistence (appendEntry) write
		expect(snapshot(root)).toEqual(before); // index + projection unchanged
		expect(fs.existsSync(path.join(root, "fresh", "pm-state.md"))).toBe(false); // pm-state unchanged
		expect(activeHarness().getPendingResponseCount()).toBe(0); // no real model usage
		console.log(
			"[VERIFY] F2-a: new_refusal_zero_watch=true no_success_notice=true persistence/index/pmstate_unchanged=true",
		);
	});

	it("F2-b: /pm-key new honors a refusal that ALREADY exists pre-fix (legacy 5-column row)", async () => {
		const root = mkRoot();
		seedRaw(
			root,
			`${[
				"# Index Parallel",
				"",
				HEADER,
				SEPARATOR,
				"| legacy | active | oldhost:1 | legacy-desc | 2026-01-01 00:00 |",
			].join("\n")}\n`,
		);
		fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["STALE"]), "utf8");
		const before = snapshot(root);
		const store = new IndexStore(root);
		const watch: PmWatchState = { key: "prior-key" };
		const { cmd, handler } = registerNewHandler(store, root, watch);
		const { ctx, notifications } = fakeCmdCtx();

		await handler("new fresh", ctx);

		expect(notifications.some((n) => n.includes("Created and claimed"))).toBe(false);
		expect(notifications.some((n) => n.includes("unsupported-authority-row"))).toBe(true);
		expect(watch.key).toBe("prior-key");
		expect(cmd.entries.length).toBe(0);
		expect(snapshot(root)).toEqual(before);
		expect(activeHarness().getPendingResponseCount()).toBe(0);
		console.log("[VERIFY] F2-b: new_honors_preexisting_refusal=true no_watch/no_success=true");
	});

	it("F2-c: foreign-live blockedBy after findByKey precheck (real shared-lock barrier)", async () => {
		const root = mkRoot();
		const legal = line(entry("unrelated", "active", "self:1"));
		seedRaw(root, `${[HEADER, SEPARATOR, legal].join("\n")}\n`);
		fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["unrelated"]), "utf8");
		const store = new IndexStore(root);
		const watch: PmWatchState = { key: "prior-key" };
		const { cmd, handler } = registerNewHandler(store, root, watch);
		const { ctx, notifications } = fakeCmdCtx();

		const release = await acquireLock(lockPathFor(root));
		let released = false;
		try {
			// Calling the async handler runs findByKey('fresh') (a MISS on the
			// pre-injection table) synchronously, then blocks in claim's
			// acquireLock on the lock THIS test holds. No predicate is mocked.
			const pending = handler("new fresh", ctx);
			// Simulate a second live window committing a foreign-live claim on
			// 'fresh' between the precheck and the locked claim.
			const foreignLine = line(entry("fresh", "active", "other-host:4242"));
			fs.writeFileSync(
				path.join(root, "_index.parallel"),
				`${[HEADER, SEPARATOR, legal, foreignLine].join("\n")}\n`,
				"utf8",
			);
			release();
			released = true;
			const afterForeignCommit = snapshot(root);
			await pending;
			expect(snapshot(root)).toEqual(afterForeignCommit); // handler made no further write
		} finally {
			if (!released) release();
		}

		expect(notifications.some((n) => n.includes("Created and claimed"))).toBe(false);
		expect(notifications.some((n) => n.includes("other-host:4242"))).toBe(true);
		expect(watch.key).toBe("prior-key");
		expect(cmd.entries.length).toBe(0);
		expect(activeHarness().getPendingResponseCount()).toBe(0);
		console.log(
			"[VERIFY] F2-c: foreign_live_blockedBy_zero_watch=true no_success_notice=true lock_barrier_real=true",
		);
	}, 20000);

	it("F2-d CONTROL: /pm-key new on a clean table still creates a CLAIMED watch", async () => {
		const root = mkRoot();
		seedRaw(root, `${[HEADER, SEPARATOR, line(entry("anchor", "active", "self:1"))].join("\n")}\n`);
		const store = new IndexStore(root);
		const watch: PmWatchState = { key: undefined };
		const { cmd, handler } = registerNewHandler(store, root, watch);
		const { ctx, notifications } = fakeCmdCtx();

		await handler("new fresh", ctx);

		expect(store.findByKey("fresh")?.status).toBe("active");
		expect(watch.key).toBe("fresh");
		expect(cmd.entries.length).toBe(1);
		expect(cmd.entries[0]?.customType).toBe(WATCH_ENTRY_TYPE);
		expect((cmd.entries[0]?.data as { claimed: boolean }).claimed).toBe(true);
		expect(notifications.some((n) => n.includes("Created and claimed key: fresh"))).toBe(true);
		expect(readIndexMdActiveKeys(root)).toContain("fresh");
		expect(activeHarness().getPendingResponseCount()).toBe(0);
		console.log("[VERIFY] F2-d: success_creates_claimed_watch=true control_passes_pre_and_post_fix=true");
	});
});
