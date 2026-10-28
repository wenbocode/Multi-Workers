/**
 * split-manifest.test.ts — split manifest build / verify / serialize (card
 * T-07, key `claim-driven-review-orchestration`).
 *
 * Locks the pure contract of `shared/split-manifest.ts` (design §2.3/§2.4):
 * the `sha256Hex` recipe (EOL-normalized, so `parentSha256` equals the
 * `card_sha256:` header of the same card), the fixed key order of
 * `selfSha256`, the build-time id-set validation (throws on a programming
 * error), the no-throw `verify` gap vocabulary
 * (`split:manifest:self-sha|parent-sha|unit-sha:<taskKey>|id-set:<missing|extra>:<id>|packing-unit:<n>`),
 * and the canonical 2-space / trailing-newline serialization.
 *
 * Digest fixtures that compare against `cardDigest()` write real card files
 * under `os.tmpdir()`; everything else is an inline literal. No clock, no model.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { cardDigest } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import {
	buildSplitManifest,
	type SplitManifest,
	type SplitManifestInput,
	serializeSplitManifest,
	sha256Hex,
	splitManifestSelfSha256,
	verifySplitManifest,
} from "../../src/extensions/agent-team-loop/shared/split-manifest.ts";

const PARENT_TEXT = "# review task parent\n\n<!-- mw-claims: v1 -->\n";
const UNIT1_TEXT = "# unit 1\n\nC-01, C-02\n";
const UNIT2_TEXT = "# unit 2\n\nC-03\n";

/** The same parent card as it comes back from a `core.autocrlf=true` checkout. */
const PARENT_TEXT_CRLF = "# review task parent\r\n\r\n<!-- mw-claims: v1 -->\r\n";

/** Temp roots of the file-backed digest cases, removed after the run. */
const temporaryDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-split-manifest-"));
	temporaryDirs.push(dir);
	return dir;
}

/** The pre-T-09 recipe (raw UTF-8 bytes): the falsifier of the CRLF cases. */
function sha256RawUtf8(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

afterAll(() => {
	while (temporaryDirs.length > 0) {
		const dir = temporaryDirs.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
});

/** Two units, three claims, one locator cluster plus one order-only cluster. */
function fixtureInput(): SplitManifestInput {
	return {
		parent: "review-task",
		mode: "plan",
		parentText: PARENT_TEXT,
		ids: ["C-01", "C-02", "C-03"],
		units: [
			{
				k: 1,
				taskKey: "review-task-u1",
				ids: ["C-01", "C-02"],
				budgetSum: 3,
				slots: 3,
				writeFace: "workers/review-task-u1",
				text: UNIT1_TEXT,
			},
			{
				k: 2,
				taskKey: "review-task-u2",
				ids: ["C-03"],
				budgetSum: 2,
				slots: 2,
				writeFace: "workers/review-task-u2",
				text: UNIT2_TEXT,
			},
		],
		packing: [
			{ cluster: ["C-01", "C-02"], unit: 1, why: "locator" },
			{ cluster: ["C-03"], unit: 2, why: "order" },
		],
		l0: { asks: 3, mapped: 3, unmapped: [] },
	};
}

/** Intact manifest plus the matching card texts (a verify that must be clean). */
function fixture(): { manifest: SplitManifest; texts: { parentText: string; unitTexts: Record<string, string> } } {
	return {
		manifest: buildSplitManifest(fixtureInput()),
		texts: {
			parentText: PARENT_TEXT,
			unitTexts: { "review-task-u1": UNIT1_TEXT, "review-task-u2": UNIT2_TEXT },
		},
	};
}

describe("sha256Hex", () => {
	it("is lower-case hex sha256 over UTF-8, matching the card-digest recipe", () => {
		expect(sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
		expect(sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
		expect(sha256Hex("申请 C-01")).toMatch(/^[0-9a-f]{64}$/);
		// Hex is lower-case and stable: same text, same digest.
		expect(sha256Hex("申请 C-01")).toBe(sha256Hex("申请 C-01"));
	});
});

describe("EOL-normalized digest (card_sha256 parity)", () => {
	it("gives a CRLF card the same parentSha256 and unit sha256 as cardDigest", () => {
		const dir = mkdtemp();
		const parentPath = path.join(dir, "task.md");
		const unitPath = path.join(dir, "review-task-u1.md");
		const crlfUnitText = UNIT1_TEXT.replace(/\n/g, "\r\n");
		fs.writeFileSync(parentPath, PARENT_TEXT_CRLF, "utf8");
		fs.writeFileSync(unitPath, crlfUnitText, "utf8");

		const input = fixtureInput();
		input.parentText = PARENT_TEXT_CRLF;
		input.units[0].text = crlfUnitText;
		const manifest = buildSplitManifest(input);

		// The chain a merge gate actually walks: card_sha256 header vs manifest.
		expect(manifest.parentSha256).toBe(cardDigest(parentPath));
		expect(manifest.units[0].sha256).toBe(cardDigest(unitPath));
		// The old raw-UTF-8 recipe would have missed the parent by the CRLF bytes.
		expect(manifest.parentSha256).not.toBe(sha256RawUtf8(PARENT_TEXT_CRLF));
	});

	it("ignores the line-ending flavour: CRLF and LF card text share one parentSha256", () => {
		const crlfManifest = buildSplitManifest({ ...fixtureInput(), parentText: PARENT_TEXT_CRLF });
		const lfManifest = buildSplitManifest({ ...fixtureInput(), parentText: PARENT_TEXT });
		expect(lfManifest.parentSha256).toBe(crlfManifest.parentSha256);

		const dir = mkdtemp();
		const lfPath = path.join(dir, "task.md");
		fs.writeFileSync(lfPath, PARENT_TEXT, "utf8");
		expect(cardDigest(lfPath)).toBe(lfManifest.parentSha256);
	});

	it("still separates two cards that differ by one character", () => {
		const substituted = PARENT_TEXT.replace("parent", "Parent");
		expect(substituted).not.toBe(PARENT_TEXT);
		// Equal-length substitution: only the content changed, never the layout.
		expect(substituted.length).toBe(PARENT_TEXT.length);

		const base = buildSplitManifest({ ...fixtureInput(), parentText: PARENT_TEXT });
		const edited = buildSplitManifest({ ...fixtureInput(), parentText: substituted });
		expect(edited.parentSha256).not.toBe(base.parentSha256);
		expect(verifySplitManifest(base, { parentText: substituted })).toContain("split:manifest:parent-sha");
	});
});

describe("buildSplitManifest", () => {
	it("seals unit texts, the parent text and the manifest body deterministically", () => {
		const first = buildSplitManifest(fixtureInput());
		const second = buildSplitManifest(fixtureInput());
		expect(second).toEqual(first);
		expect(second.selfSha256).toBe(first.selfSha256);
		expect(first.v).toBe(1);
		expect(first.parent).toBe("review-task");
		expect(first.mode).toBe("plan");
		expect(first.ids).toEqual(["C-01", "C-02", "C-03"]);
		expect(first.parentSha256).toBe(sha256Hex(PARENT_TEXT));
		expect(first.units.map((unit) => unit.sha256)).toEqual([sha256Hex(UNIT1_TEXT), sha256Hex(UNIT2_TEXT)]);
		expect(first.units.map((unit) => unit.taskKey)).toEqual(["review-task-u1", "review-task-u2"]);
		expect(first.selfSha256).toBe(splitManifestSelfSha256(first));
		expect(first.selfSha256).toMatch(/^[0-9a-f]{64}$/);
	});

	it("passes its own verification with the live card texts", () => {
		const { manifest, texts } = fixture();
		expect(verifySplitManifest(manifest, texts)).toEqual([]);
		// Without the live texts no digest is compared, so no gap is invented.
		expect(verifySplitManifest(manifest)).toEqual([]);
	});

	it("throws on a duplicate claim id (programming error, not user input)", () => {
		const input = fixtureInput();
		input.units[1]?.ids.push("C-01");
		input.ids.push("C-01");
		expect(() => buildSplitManifest(input)).toThrow(/duplicate claim id 'C-01'/);
	});

	it("throws when ids is not the unit id union in unit order", () => {
		const missing = fixtureInput();
		missing.ids = ["C-01", "C-02"];
		expect(() => buildSplitManifest(missing)).toThrow(/ids must equal the unit id union in unit order/);

		const reordered = fixtureInput();
		reordered.ids = ["C-02", "C-01", "C-03"];
		expect(() => buildSplitManifest(reordered)).toThrow(/unit id union in unit order/);
	});
});

describe("verifySplitManifest", () => {
	it("reports unit-sha:<taskKey> when a unit card text changed", () => {
		const { manifest, texts } = fixture();
		const gaps = verifySplitManifest(manifest, {
			...texts,
			unitTexts: { ...texts.unitTexts, "review-task-u2": "# unit 2 edited\n" },
		});
		expect(gaps).toContain("split:manifest:unit-sha:review-task-u2");
		expect(gaps).not.toContain("split:manifest:unit-sha:review-task-u1");
	});

	it("reports parent-sha when the parent card text changed", () => {
		const { manifest, texts } = fixture();
		const gaps = verifySplitManifest(manifest, { ...texts, parentText: `${PARENT_TEXT}\nadded after the split\n` });
		expect(gaps).toContain("split:manifest:parent-sha");
	});

	it("reports id-set:missing:<id> when the manifest lost an id", () => {
		const { manifest, texts } = fixture();
		const tampered = structuredClone(manifest);
		tampered.ids = tampered.ids.filter((id) => id !== "C-03");
		const gaps = verifySplitManifest(tampered, texts);
		expect(gaps).toContain("split:manifest:id-set:missing:C-03");
		// Removing a field also breaks the self seal; the id gap is the specific one.
		expect(gaps[0]).toBe("split:manifest:self-sha");
	});

	it("reports id-set:extra:<id> when the manifest carries an id no unit owns", () => {
		const { manifest, texts } = fixture();
		const tampered = structuredClone(manifest);
		tampered.ids = [...tampered.ids, "C-09"];
		const gaps = verifySplitManifest(tampered, texts);
		expect(gaps).toContain("split:manifest:id-set:extra:C-09");
		expect(gaps).not.toContain("split:manifest:id-set:missing:C-09");
	});

	it("reports self-sha when only the seal was tampered with", () => {
		const { manifest, texts } = fixture();
		const tampered = structuredClone(manifest);
		tampered.selfSha256 = sha256Hex("not the manifest body");
		expect(verifySplitManifest(tampered, texts)).toEqual(["split:manifest:self-sha"]);
	});

	it("reports packing-unit:<n> for a packing row pointing at an unknown unit", () => {
		const { manifest, texts } = fixture();
		const tampered = structuredClone(manifest);
		tampered.packing.push({ cluster: ["C-99"], unit: 9, why: "order" });
		const gaps = verifySplitManifest(tampered, texts);
		expect(gaps).toContain("split:manifest:packing-unit:9");
	});

	it("never throws on a structurally broken manifest", () => {
		const broken = {} as SplitManifest;
		expect(() => verifySplitManifest(broken)).not.toThrow();
		expect(verifySplitManifest(broken)).toContain("split:manifest:self-sha");
	});
});

describe("serializeSplitManifest", () => {
	it("round-trips, uses 2-space indent, a trailing newline and canonical key order", () => {
		const { manifest } = fixture();
		const text = serializeSplitManifest(manifest);
		expect(text.startsWith('{\n  "v": 1,\n  "parent": "review-task",')).toBe(true);
		expect(text.endsWith("}\n")).toBe(true);
		expect(text.includes("\n\t")).toBe(false);
		expect(JSON.parse(text)).toEqual(manifest);
	});

	it("is byte-stable across a parse/serialize round trip", () => {
		const { manifest } = fixture();
		const text = serializeSplitManifest(manifest);
		const reparsed = JSON.parse(text) as SplitManifest;
		expect(serializeSplitManifest(reparsed)).toBe(text);
		// Canonicalization does not depend on the caller's key insertion order.
		const reordered = Object.fromEntries(Object.entries(manifest).reverse()) as SplitManifest;
		expect(serializeSplitManifest(reordered)).toBe(text);
	});
});
