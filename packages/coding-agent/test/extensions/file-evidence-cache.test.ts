import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
	checkFileEvidence,
	type FileEvidenceDependency,
	parseFileEvidence,
} from "../../src/extensions/agent-team-loop/pm/file-evidence-cache.ts";

const temporaryRoots: string[] = [];
afterEach(() => {
	for (const root of temporaryRoots.splice(0)) {
		const resolved = path.resolve(root);
		if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep))
			fs.rmSync(resolved, { recursive: true, force: true });
	}
});

function project(): string {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-file-evidence-"));
	temporaryRoots.push(root);
	fs.mkdirSync(path.join(root, ".mw"));
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: true }));
	return root;
}

function evidence(file: string): FileEvidenceDependency {
	try {
		return {
			path: file,
			canonical_path: fs.realpathSync(file),
			sha256: createHash("sha256").update(fs.readFileSync(file)).digest("hex"),
		};
	} catch {
		return { path: file, canonical_path: null, sha256: null, status: "missing" };
	}
}

describe("authorized file evidence freshness", () => {
	it("hashes actual contents, ignores mtime changes, and detects same-size edits", () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "old evidence\n");
		const dependency = evidence(file);
		fs.utimesSync(file, new Date(0), new Date(0));
		expect(checkFileEvidence([dependency]).changed).toBe(false);
		fs.writeFileSync(file, "new evidence\n");
		fs.utimesSync(file, new Date(0), new Date(0));
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});

	it("rejects malformed metadata without interpreting material paths", () => {
		expect(parseFileEvidence({})).toBeUndefined();
		expect(parseFileEvidence({ file_evidence: [{ path: "relative.md", sha256: "0".repeat(64) }] })).toBeNull();
		expect(parseFileEvidence({ file_evidence: [{ path: path.resolve("safe.md"), sha256: "invalid" }] })).toBeNull();
		expect(parseFileEvidence({ file_evidence: [] })).toEqual([]);
	});

	it("accepts all 67 source/config/card dependencies but refuses an unbounded array", () => {
		const file = path.resolve("safe.md");
		const dependency: FileEvidenceDependency = { path: file, canonical_path: null, sha256: null, status: "missing" };
		expect(parseFileEvidence({ file_evidence: Array.from({ length: 67 }, () => dependency) })).toHaveLength(67);
		expect(parseFileEvidence({ file_evidence: Array.from({ length: 68 }, () => dependency) })).toBeNull();
	});

	it("detects missing-to-created dependencies without reading newly authorized contents", () => {
		const root = project();
		const file = path.join(root, "report.md");
		const dependency = evidence(file);
		expect(checkFileEvidence([dependency]).changed).toBe(false);
		fs.writeFileSync(file, "new proof\n");
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});

	it("retargeted aliases are invalidated before content reads", () => {
		const root = project();
		const oldTarget = path.join(root, "old.md");
		const newTarget = path.join(root, "new.md");
		const alias = path.join(root, "alias.md");
		fs.writeFileSync(oldTarget, "old\n");
		fs.writeFileSync(newTarget, "new\n");
		const dependency: FileEvidenceDependency = {
			path: alias,
			canonical_path: oldTarget,
			sha256: evidence(oldTarget).sha256,
		};
		// An ordinary file at the old alias path also differs from the expected
		// canonical target, so this does not need Windows symlink privileges.
		fs.writeFileSync(alias, "new target must not be read\n");
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});

	it("binary, removed, and oversized replacement evidence invalidate old results", () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "valid text\n");
		const dependency = evidence(file);
		fs.writeFileSync(file, Buffer.from([0, 255, 0]));
		expect(checkFileEvidence([dependency]).changed).toBe(true);
		fs.truncateSync(file, 8 * 1024 * 1024 + 1);
		expect(checkFileEvidence([dependency]).changed).toBe(true);
		fs.unlinkSync(file);
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});
});
