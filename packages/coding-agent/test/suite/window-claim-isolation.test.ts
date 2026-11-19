/**
 * mw-window-claim-isolation T-01: authoritative multi-window claim scope,
 * full active_keys projection, and owner resolution from exact self claims.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	foreignLiveClaimRefusal,
	resolveOwnerKeyWithSync,
	takeOverKey,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	IndexAuthorityError,
	type IndexEntry,
	type IndexStatus,
	IndexStore,
	readIndexMdActiveKeys,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { createHarness, type Harness } from "./harness.ts";

const roots: string[] = [];
let harness: Harness | undefined;

beforeAll(async () => {
	harness = await createHarness();
});

afterAll(() => {
	harness?.cleanup();
});

afterEach(() => {
	for (const root of roots.splice(0)) {
		fs.rmSync(root, { recursive: true, force: true });
	}
});

function activeHarness(): Harness {
	if (!harness) throw new Error("faux harness not initialized");
	return harness;
}

function mkRoot(): string {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-window-claim-isolation-"));
	roots.push(root);
	return root;
}

function row(
	key: string,
	status: IndexStatus,
	claimId: string,
	updated: string,
	phase = "EXECUTE",
	deps = "-",
	desc = "row",
): IndexEntry {
	return { key, status, phase, claimId, deps, desc, updated };
}

function line(entry: IndexEntry): string {
	return `| ${[entry.key, entry.status, entry.phase, entry.claimId, entry.deps, entry.desc, entry.updated].join(" | ")} |`;
}

function seedRows(root: string, rows: IndexEntry[]): void {
	fs.writeFileSync(path.join(root, "_index.parallel"), `${rows.map(line).join("\n")}\n`, "utf8");
}

/** Raw authority bytes: T-07 needs legacy 5-column / malformed / header-only
 * tables that `seedRows` cannot express. */
function seedRaw(root: string, content: string): void {
	fs.writeFileSync(path.join(root, "_index.parallel"), content, "utf8");
}

/** Both products of an index mutation, for byte-level zero-write assertions. */
function snapshot(root: string): { authority: string; projection: string | null } {
	const mdPath = path.join(root, "_index.md");
	const projection = fs.existsSync(mdPath) && fs.statSync(mdPath).isFile() ? fs.readFileSync(mdPath, "utf8") : null;
	return { authority: readAuthority(root), projection };
}

function canonicalIndexMd(keys: readonly string[]): string {
	return `# AgenticTask Index\n\nactive_keys: [${keys.map((key) => JSON.stringify(key)).join(", ")}]\n`;
}

function readIndexMd(root: string): string {
	return fs.readFileSync(path.join(root, "_index.md"), "utf8");
}

function readAuthority(root: string): string {
	return fs.readFileSync(path.join(root, "_index.parallel"), "utf8");
}

function fakePi(messages: string[]): ExtensionAPI {
	return {
		sendMessage: (message: string | { content?: string }) => {
			messages.push(typeof message === "string" ? message : (message.content ?? ""));
		},
	} as unknown as ExtensionAPI;
}

describe("window claim isolation (T-01)", () => {
	it("VC-001: two windows coexist and the other window's row and fields stay unchanged", async () => {
		const root = mkRoot();
		const foreign = row("win-a", "active", "host-a:101", "2026-01-01T00:00:00Z", "VERIFY", "dep-a", "foreign work");
		const target = row("win-b", "idle", "", "2026-01-01T01:00:00Z", "SPEC", "dep-b", "target");
		seedRows(root, [foreign, target]);
		const foreignLine = line(foreign);

		const store = new IndexStore(root);
		const outcome = await store.claim("win-b", "host-b:202", () => false);
		expect(outcome.ok).toBe(true);
		expect(store.findByKey("win-a")).toEqual(foreign);
		expect(readAuthority(root).split("\n")).toContain(foreignLine);
		expect(store.findByKey("win-b")?.claimId).toBe("host-b:202");
		expect(store.findByKey("win-b")?.status).toBe("active");
		expect(readIndexMd(root)).toBe(canonicalIndexMd(["win-a", "win-b"]));
		expect(readIndexMdActiveKeys(root)).toEqual(["win-a", "win-b"]);
		expect(activeHarness().getPendingResponseCount()).toBe(0);
		console.log("[VERIFY] VC-001: coexist=true other_window_fields_unchanged=true projection_full=true");
	});

	it("VC-002: one claim demotes only multiple exact-self active rows", async () => {
		const root = mkRoot();
		const self = "host-me:303";
		const ownOld1 = row("own-old-1", "active", self, "2026-01-01T00:00:00Z", "SPEC", "d1", "old one");
		const ownOld2 = row("own-old-2", "active", self, "2026-01-01T01:00:00Z", "DESIGN", "d2", "old two");
		const foreign = row("foreign-live", "active", "host-other:404", "2026-01-01T02:00:00Z", "VERIFY", "d3", "other");
		const legacy = row(
			"legacy-active",
			"active",
			"20260808-142655-3496",
			"2026-01-01T03:00:00Z",
			"EXECUTE",
			"d4",
			"legacy",
		);
		const target = row("new-self", "idle", "", "2026-01-01T04:00:00Z", "SPEC", "d5", "new");
		seedRows(root, [ownOld1, ownOld2, foreign, legacy, target]);

		const store = new IndexStore(root);
		const outcome = await store.claim("new-self", self, () => false);
		expect(outcome.ok).toBe(true);
		expect(store.findByKey("own-old-1")?.status).toBe("idle");
		expect(store.findByKey("own-old-2")?.status).toBe("idle");
		expect(store.findByKey("foreign-live")).toEqual(foreign);
		expect(store.findByKey("legacy-active")).toEqual(legacy);
		expect(readAuthority(root).split("\n")).toContain(line(foreign));
		expect(readAuthority(root).split("\n")).toContain(line(legacy));
		expect(readIndexMd(root)).toBe(canonicalIndexMd(["foreign-live", "legacy-active", "new-self"]));
		console.log("[VERIFY] VC-002: demote_scope=self multiple_own_rows=2 foreign_untouched=true");
	});

	it("VC-003: a foreign live claim without force writes neither authority, projection nor pm-state", async () => {
		const root = mkRoot();
		const target = "foreign-live-zero-write";
		const foreignClaim = "other-host:4242";
		seedRows(root, [row(target, "active", foreignClaim, "2026-01-01T00:00:00Z")]);
		fs.writeFileSync(path.join(root, "_index.md"), `active: ${target}\n`, "utf8");
		fs.mkdirSync(path.join(root, target), { recursive: true });
		const pmStatePath = path.join(root, target, "pm-state.md");
		fs.writeFileSync(pmStatePath, `- Claim-Id: ${foreignClaim}\n`, "utf8");
		const authorityBefore = readAuthority(root);
		const projectionBefore = readIndexMd(root);
		const pmStateBefore = fs.readFileSync(pmStatePath, "utf8");

		const store = new IndexStore(root);
		const outcome = await takeOverKey(store, target, false, root);
		expect(outcome.ok).toBe(false);
		expect(outcome.blockedBy).toBe(foreignClaim);
		expect(readAuthority(root)).toBe(authorityBefore);
		expect(readIndexMd(root)).toBe(projectionBefore);
		expect(fs.readFileSync(pmStatePath, "utf8")).toBe(pmStateBefore);
		expect(foreignLiveClaimRefusal(store, target)).not.toBeNull();

		const messages: string[] = [];
		const pi = fakePi(messages);
		expect(resolveOwnerKeyWithSync(pi, store, { key: undefined }, target, root)).toBe(target);
		expect(resolveOwnerKeyWithSync(pi, store, { key: "_scratch" }, undefined, root)).toBe("_scratch");
		console.log("[VERIFY] VC-003: conflict_zero_write=true explicit_key_preserved=true scratch_preserved=true");
	});

	it("T-07/TS-subset: quiet restore keeps all other active rows and projects the full set (not VC-004)", async () => {
		const root = mkRoot();
		const self = windowClaimId();
		const target = row("restore-target", "active", "old-self:1", "2026-01-01T00:00:00Z", "EXECUTE", "d1", "target");
		const own = row("own-other", "active", self, "2026-01-01T01:00:00Z", "DESIGN", "d2", "own");
		const foreign = row(
			"foreign-other",
			"active",
			"other-host:505",
			"2026-01-01T02:00:00Z",
			"VERIFY",
			"d3",
			"foreign",
		);
		seedRows(root, [target, own, foreign]);

		const store = new IndexStore(root);
		const outcome = await store.claim("restore-target", self, () => false, { demoteOthers: false, activate: false });
		expect(outcome.ok).toBe(true);
		expect(store.findByKey("restore-target")?.status).toBe("active");
		expect(store.findByKey("restore-target")?.claimId).toBe(self);
		expect(store.findByKey("own-other")).toEqual(own);
		expect(store.findByKey("foreign-other")).toEqual(foreign);
		expect(readIndexMd(root)).toBe(canonicalIndexMd(["restore-target", "own-other", "foreign-other"]));
		console.log(
			"[VERIFY] T-07/TS-subset: quiet_restore=true projection_full=true; VC-004 still needs real locked contention",
		);
	});

	it("VC-006: upsert writes exact 0/1/N projections and dedupes by normalizeKey preserving first spelling", async () => {
		const emptyRoot = mkRoot();
		const store = new IndexStore(emptyRoot);
		await store.upsert(row("idle-only", "idle", "", "2026-01-01T00:00:00Z"));
		expect(readIndexMd(emptyRoot)).toBe(canonicalIndexMd([]));
		await store.upsert(row("one", "active", "", "2026-01-01T01:00:00Z"));
		expect(readIndexMd(emptyRoot)).toBe(canonicalIndexMd(["one"]));
		await store.upsert(row("two", "active", "", "2026-01-01T02:00:00Z"));
		expect(readIndexMd(emptyRoot)).toBe(canonicalIndexMd(["one", "two"]));
		expect(readIndexMdActiveKeys(emptyRoot)).toEqual(["one", "two"]);

		const duplicateRoot = mkRoot();
		seedRows(duplicateRoot, [
			row("Alpha", "active", "", "2026-01-01T00:00:00Z"),
			row("alpha", "active", "", "2026-01-01T01:00:00Z"),
			row("Beta", "active", "", "2026-01-01T02:00:00Z"),
		]);
		await new IndexStore(duplicateRoot).upsert(row("Gamma", "idle", "", "2026-01-01T03:00:00Z"));
		expect(readIndexMd(duplicateRoot)).toBe(canonicalIndexMd(["Alpha", "Beta"]));
		console.log("[VERIFY] VC-006: active_keys=0/1/N exact_utf8_lf=true first_spelling=true");
	});

	it("VC-007: missing, old scalar, malformed, duplicate and reserved projections fail closed", () => {
		const root = mkRoot();
		const mdPath = path.join(root, "_index.md");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/missing or unreadable/);
		fs.writeFileSync(mdPath, "active: old-scalar\n", "utf8");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/UTF-8\/LF active_keys/);
		fs.writeFileSync(mdPath, '# AgenticTask Index\n\nactive_keys: ["a",]\n', "utf8");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/not valid JSON/);
		fs.writeFileSync(mdPath, '# AgenticTask Index\n\nactive_keys: ["a", "a"]\n', "utf8");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/duplicate key/);
		fs.writeFileSync(mdPath, '# AgenticTask Index\n\nactive_keys: ["Alpha", "alpha"]\n', "utf8");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/duplicate key/);
		fs.writeFileSync(mdPath, '# AgenticTask Index\n\nactive_keys: ["_index.parallel"]\n', "utf8");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/invalid key/);
		fs.writeFileSync(mdPath, "# AgenticTask Index\n\nactive_keys: []\r\n", "utf8");
		expect(() => readIndexMdActiveKeys(root)).toThrow(/UTF-8\/LF active_keys/);
		console.log("[VERIFY] VC-007: collection_fail_closed=true scalar_fallback=false");
	});

	it("T-07/TS-subset: projection failure is visible and the next write recovers (not VC-008)", async () => {
		const root = mkRoot();
		const store = new IndexStore(root);
		const blockedProjection = path.join(root, "_index.md");
		fs.mkdirSync(blockedProjection, { recursive: true });

		await expect(store.upsert(row("authority-first", "active", "", "2026-01-01T00:00:00Z"))).rejects.toThrow(
			/_index\.parallel was written/,
		);
		expect(readAuthority(root)).toContain("| authority-first | active |");
		expect(fs.statSync(blockedProjection).isDirectory()).toBe(true);

		fs.rmSync(blockedProjection, { recursive: true, force: true });
		await store.upsert(row("recovered-second", "active", "", "2026-01-01T01:00:00Z"));
		expect(readIndexMd(root)).toBe(canonicalIndexMd(["authority-first", "recovered-second"]));
		expect(readIndexMdActiveKeys(root)).toEqual(["authority-first", "recovered-second"]);
		console.log(
			"[VERIFY] T-07/TS-subset: projection_failure=visible recovery=next_write; VC-008 still needs mirror/workflow alignment",
		);
	});

	it("T-01: owner resolution chooses the exact self active row, not the globally-latest active row", () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRows(root, [
			row("own-older", "active", self, "2026-01-01T00:00:00Z"),
			row("other-newer", "active", "20260808-142655-3496", "2026-12-01T00:00:00Z"),
		]);
		const store = new IndexStore(root);
		expect(store.activeEntry()?.key).toBe("other-newer");
		const messages: string[] = [];
		const owner = resolveOwnerKeyWithSync(fakePi(messages), store, { key: undefined }, undefined, root);
		expect(owner).toBe("own-older");
		expect(messages.some((message) => message.includes("owner-key mismatch"))).toBe(false);
		console.log("[VERIFY] T-01: owner_self_exact=true globally_latest_guess=false");
	});

	it("T-01: multiple own active rows are ambiguous and never guess a latest winner", () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRows(root, [
			row("own-first", "active", self, "2026-01-01T00:00:00Z"),
			row("own-second", "active", self, "2026-12-01T00:00:00Z"),
		]);
		const store = new IndexStore(root);
		const messages: string[] = [];
		const owner = resolveOwnerKeyWithSync(fakePi(messages), store, { key: undefined }, undefined, root);
		expect(owner).toBe("_scratch");
		expect(store.activeEntry()?.key).toBe("own-second");
		expect(messages.some((message) => message.includes("multiple active keys with this window's claim"))).toBe(true);
		expect(messages.every((message) => !message.includes("own-second"))).toBe(true);
		console.log("[VERIFY] T-01: multiple_self_ambiguous=true latest_guess=false warning_generic=true");
	});

	it("T-01: idle/foreign/missing authority rows and stale Markdown pointers cannot grant an owner", () => {
		const self = windowClaimId();
		const cases: Array<{
			name: string;
			rows: IndexEntry[];
			watch: string | undefined;
			md: string;
			leaked: string;
		}> = [
			{
				name: "idle watch",
				rows: [row("idle-watch", "idle", self, "2026-01-01T00:00:00Z")],
				watch: "idle-watch",
				md: canonicalIndexMd(["idle-watch"]),
				leaked: "ghost-only",
			},
			{
				name: "foreign live active row",
				rows: [row("foreign-active", "active", "other-host:606", "2026-01-01T00:00:00Z")],
				watch: undefined,
				md: canonicalIndexMd(["foreign-active"]),
				leaked: "ghost-only",
			},
			{
				name: "nonexistent authoritative row",
				rows: [],
				watch: "missing-authority-row",
				md: canonicalIndexMd(["missing-authority-row"]),
				leaked: "ghost-only",
			},
			{
				name: "stale scalar",
				rows: [],
				watch: undefined,
				md: "active: ghost-only\n",
				leaked: "ghost-only",
			},
			{
				name: "valid Markdown array is not authorization",
				rows: [],
				watch: undefined,
				md: canonicalIndexMd(["ghost-only"]),
				leaked: "ghost-only",
			},
		];
		for (const testCase of cases) {
			const root = mkRoot();
			seedRows(root, testCase.rows);
			fs.writeFileSync(path.join(root, "_index.md"), testCase.md, "utf8");
			const store = new IndexStore(root);
			const messages: string[] = [];
			const owner = resolveOwnerKeyWithSync(fakePi(messages), store, { key: testCase.watch }, undefined, root);
			expect(owner, testCase.name).toBe("_scratch");
			expect(
				messages.some((message) => message.includes(testCase.leaked)),
				testCase.name,
			).toBe(false);
		}
		const arrayRoot = mkRoot();
		seedRows(arrayRoot, []);
		fs.writeFileSync(path.join(arrayRoot, "_index.md"), canonicalIndexMd(["ghost-only"]), "utf8");
		expect(readIndexMdActiveKeys(arrayRoot)).toEqual(["ghost-only"]);
		const messages: string[] = [];
		expect(
			resolveOwnerKeyWithSync(fakePi(messages), new IndexStore(arrayRoot), { key: undefined }, undefined, arrayRoot),
		).toBe("_scratch");
		expect(messages.every((message) => !message.includes("ghost-only"))).toBe(true);
		console.log(
			"[VERIFY] T-01: idle_watch_refused=true markdown_not_authorization=true warning_no_unrelated_content=true",
		);
	});

	// ── T-07: strict authority, duplicate identity and owner fail-closed ──────

	it("T-07: legacy 5-column / malformed authority rows refuse TS mutations with zero writes", async () => {
		const root = mkRoot();
		const legal = row("anchor", "active", "other-host:1", "2026-01-01T00:00:00Z");
		const raw = `${[
			"# Index Parallel",
			"",
			"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
			"|-----|--------|-------|---------|------|------|---------|",
			"| legacy | active | oldhost:1 | legacy-desc | 2026-01-01 00:00 |",
			"| broken | active |",
			line(legal),
		].join("\n")}\n`;
		seedRaw(root, raw);
		fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["STALE"]), "utf8");
		const before = snapshot(root);
		const store = new IndexStore(root);

		await expect(store.upsert(row("anchor", "active", "self:2", "2026-01-02T00:00:00Z"))).rejects.toThrow(
			/unsupported/,
		);
		const forced = await store.claim("anchor", "self:2", () => false, { force: true });
		expect(forced.ok).toBe(false);
		expect(forced.refusal).toBe("unsupported-authority-row");
		expect(snapshot(root)).toEqual(before);
		expect(readIndexMdActiveKeys(root)).toEqual(["STALE"]);
		console.log("[VERIFY] T-07: legacy_bad_zero_write=true authority_and_projection_bytes_unchanged=true");
	});

	it("T-07: a supported table keeps its header lines and every legal row on a successful write", async () => {
		const root = mkRoot();
		const legal = row("anchor", "active", "other-host:1", "2026-01-01T00:00:00Z");
		seedRaw(
			root,
			`${[
				"# Index Parallel",
				"",
				"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
				"|-----|--------|-------|---------|------|------|---------|",
				line(legal),
			].join("\n")}\n`,
		);
		const store = new IndexStore(root);
		const outcome = await store.claim("new-self", "self:2", () => false);
		expect(outcome.ok).toBe(true);
		const after = readAuthority(root);
		expect(after).toContain("# Index Parallel");
		expect(after).toContain("| Key | Status | Phase | ClaimId | Deps | Desc | Updated |");
		expect(after).toContain(line(legal));
		expect(after).toContain("| new-self | active |");
		expect(readIndexMd(root)).toBe(canonicalIndexMd(["anchor", "new-self"]));
		console.log("[VERIFY] T-07: supported_header_preserved=true legal_rows_preserved=true");
	});

	it("T-07: duplicate normalized target rows are refused by claim/guard/owner, never a forced first row", async () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRows(root, [
			row("Ambiguous", "idle", self, "2026-01-01T00:00:00Z"),
			row("ambiguous", "active", "other-host:900", "2026-01-01T01:00:00Z"),
		]);
		fs.writeFileSync(path.join(root, "_index.md"), canonicalIndexMd(["STALE"]), "utf8");
		const before = snapshot(root);
		const store = new IndexStore(root);

		expect(foreignLiveClaimRefusal(store, "Ambiguous")).not.toBeNull();
		const outcome = await store.claim("Ambiguous", self, () => true, { force: true });
		expect(outcome.ok).toBe(false);
		expect(outcome.refusal).toBe("duplicate-target-key");
		const takeover = await takeOverKey(store, "ambiguous", true, root);
		expect(takeover.ok).toBe(false);
		expect(takeover.refusal).toBe("duplicate-target-key");
		expect(snapshot(root)).toEqual(before);

		const messages: string[] = [];
		expect(resolveOwnerKeyWithSync(fakePi(messages), store, { key: "Ambiguous" }, undefined, root)).toBe("_scratch");
		console.log("[VERIFY] T-07: duplicate_target_refused=true force_no_first_row=true owner_scratch=true");
	});

	it("T-07/D-003: a valid watch is an explicit choice even with several own active rows", () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRows(root, [
			row("own-first", "active", self, "2026-01-01T00:00:00Z"),
			row("own-second", "active", self, "2026-01-01T01:00:00Z"),
			row("foreign-live", "active", "other-host:900", "2026-01-01T02:00:00Z"),
		]);
		const messages: string[] = [];
		const owner = resolveOwnerKeyWithSync(
			fakePi(messages),
			new IndexStore(root),
			{ key: "own-first" },
			undefined,
			root,
		);
		expect(owner).toBe("own-first");
		expect(messages.some((message) => message.includes("ambiguous"))).toBe(false);
		console.log("[VERIFY] T-07: valid_watch_explicit_choice=true multiple_self_preserved=true");
	});

	it("T-07/D-003: an invalid watch with several own active rows degrades to _scratch", () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRows(root, [
			row("own-first", "active", self, "2026-01-01T00:00:00Z"),
			row("own-second", "active", self, "2026-01-01T01:00:00Z"),
			row("foreign-live", "active", "other-host:900", "2026-01-01T02:00:00Z"),
		]);
		const messages: string[] = [];
		const owner = resolveOwnerKeyWithSync(
			fakePi(messages),
			new IndexStore(root),
			{ key: "foreign-live" },
			undefined,
			root,
		);
		expect(owner).toBe("_scratch");
		expect(messages.some((message) => message.includes("multiple active keys with this window's claim"))).toBe(true);
		expect(messages.every((message) => !message.includes("own-second"))).toBe(true);
		console.log("[VERIFY] T-07: invalid_watch_multiple_self_scratch=true latest_guess=false");
	});

	it("T-07: duplicate watch rows are ambiguous in both orders and never grant a namespace", () => {
		const self = windowClaimId();
		const foreign = "other-host:900";
		const cases = [
			{
				name: "self active first + foreign live second",
				rows: [
					row("Dup", "active", self, "2026-01-01T00:00:00Z"),
					row("dup", "active", foreign, "2026-01-01T01:00:00Z"),
				],
			},
			{
				name: "foreign live first + self active second",
				rows: [
					row("Dup", "active", foreign, "2026-01-01T00:00:00Z"),
					row("dup", "active", self, "2026-01-01T01:00:00Z"),
				],
			},
			{
				name: "two own active rows with the same normalized key",
				rows: [
					row("Dup", "active", self, "2026-01-01T00:00:00Z"),
					row("dup", "active", self, "2026-01-01T01:00:00Z"),
				],
			},
		];
		for (const testCase of cases) {
			const root = mkRoot();
			seedRows(root, testCase.rows);
			const messages: string[] = [];
			const owner = resolveOwnerKeyWithSync(fakePi(messages), new IndexStore(root), { key: "Dup" }, undefined, root);
			expect(owner, testCase.name).toBe("_scratch");
			expect(
				messages.some((message) => message.includes("duplicate")),
				testCase.name,
			).toBe(true);
		}
		console.log("[VERIFY] T-07: duplicate_watch_ambiguous=true both_orders=true");
	});

	it("T-07: reserved / bad-shape authoritative active rows never become an owner namespace", () => {
		const self = windowClaimId();
		for (const bad of ["_index.md", "bad?key"]) {
			const root = mkRoot();
			seedRows(root, [row(bad, "active", self, "2026-01-01T00:00:00Z")]);
			const messages: string[] = [];
			const owner = resolveOwnerKeyWithSync(
				fakePi(messages),
				new IndexStore(root),
				{ key: undefined },
				undefined,
				root,
			);
			expect(owner, bad).toBe("_scratch");
			expect(
				messages.every((message) => !message.includes(bad)),
				bad,
			).toBe(true);
		}
		console.log("[VERIFY] T-07: illegal_authority_name_refused=true namespace_leak=0");
	});

	it("T-07: corrupt authority makes owner resolution fail closed without an unhandled exception", () => {
		const root = mkRoot();
		const self = windowClaimId();
		seedRaw(
			root,
			`${line(row("own-legal", "active", self, "2026-01-01T00:00:00Z"))}\n` +
				"| legacy | active | oldhost:1 | legacy-desc | 2026-01-01 00:00 |\n",
		);
		const messages: string[] = [];
		let owner: string | undefined;
		expect(() => {
			owner = resolveOwnerKeyWithSync(fakePi(messages), new IndexStore(root), { key: undefined }, undefined, root);
		}).not.toThrow();
		expect(owner).toBe("_scratch");
		expect(messages.some((message) => message.includes("unavailable or ambiguous"))).toBe(true);
		console.log("[VERIFY] T-07: corrupt_owner_fail_closed=true unhandled_exception=0");
	});

	it("T-07: explicit keys still reach the real write-permission guard; scratch exception is unchanged", () => {
		const root = mkRoot();
		seedRows(root, [row("foreign-live", "active", "other-host:4242", "2026-01-01T00:00:00Z")]);
		const store = new IndexStore(root);
		const messages: string[] = [];
		expect(resolveOwnerKeyWithSync(fakePi(messages), store, { key: undefined }, "foreign-live", root)).toBe(
			"foreign-live",
		);
		expect(foreignLiveClaimRefusal(store, "foreign-live")).not.toBeNull();
		expect(resolveOwnerKeyWithSync(fakePi(messages), store, { key: undefined }, "_scratch", root)).toBe("_scratch");
		expect(resolveOwnerKeyWithSync(fakePi(messages), store, { key: "_scratch" }, undefined, root)).toBe("_scratch");
		expect(foreignLiveClaimRefusal(store, "_scratch")).toBeNull();
		console.log("[VERIFY] T-07: explicit_key_guard_preserved=true scratch_exception_preserved=true");
	});

	it("T-07: strict identity read refuses a legacy row while the set-level read stays tolerant", () => {
		const root = mkRoot();
		seedRaw(
			root,
			`${line(row("good", "active", "self:1", "2026-01-01T00:00:00Z"))}\n` +
				"| legacy | active | oldhost:1 | legacy-desc | 2026-01-01 00:00 |\n",
		);
		const store = new IndexStore(root);
		// D-002 SET reads stay tolerant; identity reads and the guard do not.
		expect(store.readAll().map((entry) => entry.key)).toEqual(["good"]);
		expect(() => store.readAuthorityRows()).toThrow(IndexAuthorityError);
		expect(() => store.readAuthorityRows()).toThrow(/5 columns/);
		expect(store.authorityRefusalFor("good")).toBe("unsupported-authority-row");
		console.log("[VERIFY] T-07: strict_identity_read_fail_closed=true set_read_tolerant=true");
	});

	it("T-07: upsert refuses an ambiguous duplicate target with zero writes", async () => {
		const root = mkRoot();
		seedRows(root, [
			row("Twin", "active", "", "2026-01-01T00:00:00Z"),
			row("twin", "idle", "", "2026-01-01T01:00:00Z"),
		]);
		const before = snapshot(root);
		await expect(new IndexStore(root).upsert(row("TWIN", "idle", "", "2026-01-02T00:00:00Z"))).rejects.toThrow(
			/duplicate/,
		);
		expect(snapshot(root)).toEqual(before);
		console.log("[VERIFY] T-07: duplicate_upsert_zero_write=true");
	});

	it("T-07/D-002: set-level projection still dedupes duplicate normalized active rows", async () => {
		const root = mkRoot();
		seedRows(root, [
			row("Alpha", "active", "", "2026-01-01T00:00:00Z"),
			row("alpha", "active", "", "2026-01-01T01:00:00Z"),
		]);
		await new IndexStore(root).upsert(row("Gamma", "idle", "", "2026-01-01T02:00:00Z"));
		expect(readIndexMd(root)).toBe(canonicalIndexMd(["Alpha"]));
		expect(readIndexMdActiveKeys(root)).toEqual(["Alpha"]);
		console.log("[VERIFY] T-07: projection_dedupe_set_level=true first_spelling=true");
	});
});
