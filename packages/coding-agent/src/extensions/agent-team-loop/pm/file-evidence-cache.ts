/** Local replay checks for file paths authorized by the Python preparer.
 * This module does not parse model material, discover paths, or grant reads. */
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";

const MAX_FILE_BYTES = 8 * 1024 * 1024;
// 64 citations + target config + Worker card + exact-file evidence policy.
const MAX_DEPENDENCIES = 67;
const SHA256 = /^[a-f0-9]{64}$/;

export interface FileEvidenceDependency {
	path: string;
	canonical_path: string | null;
	sha256: string | null;
	status?: "missing" | "unreadable" | "oversized";
}

function record(value: unknown): Record<string, unknown> | undefined {
	return value !== null && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: undefined;
}

/** undefined means older/no-file response; null means malformed metadata and
 * must never authorize reads or a reusable cached result. */
export function parseFileEvidence(raw: unknown): FileEvidenceDependency[] | undefined | null {
	const response = record(raw);
	if (response === undefined || !Object.hasOwn(response, "file_evidence")) return undefined;
	const values = response.file_evidence;
	if (!Array.isArray(values) || values.length > MAX_DEPENDENCIES) return null;
	const dependencies: FileEvidenceDependency[] = [];
	for (const value of values) {
		const item = record(value);
		if (item === undefined || typeof item.path !== "string" || !path.isAbsolute(item.path)) return null;
		if (item.sha256 !== null && (typeof item.sha256 !== "string" || !SHA256.test(item.sha256))) return null;
		const canonical =
			item.canonical_path === undefined ? (item.sha256 === null ? null : item.path) : item.canonical_path;
		if (canonical !== null && (typeof canonical !== "string" || !path.isAbsolute(canonical))) return null;
		const status = item.status === undefined && item.sha256 === null ? "missing" : item.status;
		if (status !== undefined && status !== "missing" && status !== "unreadable" && status !== "oversized")
			return null;
		if (
			(item.sha256 !== null && (canonical === null || status !== undefined)) ||
			(item.sha256 === null && status === undefined)
		)
			return null;
		dependencies.push({
			path: path.resolve(item.path),
			canonical_path: canonical === null ? null : path.resolve(canonical),
			sha256: item.sha256 as string | null,
			...(status === undefined ? {} : { status }),
		});
	}
	return dependencies;
}

function normalizedPath(value: string): string {
	const resolved = path.resolve(value);
	return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function currentDependency(expected: FileEvidenceDependency): FileEvidenceDependency {
	let canonical: string;
	try {
		canonical = fs.realpathSync(expected.path);
	} catch {
		return { path: expected.path, canonical_path: null, sha256: null, status: "missing" };
	}
	// A missing file appearing or an alias changing targets is a new fact. No
	// contents of that newly resolved target are read before Python authorizes it.
	if (expected.canonical_path === null || normalizedPath(canonical) !== normalizedPath(expected.canonical_path)) {
		return { path: expected.path, canonical_path: canonical, sha256: null, status: "unreadable" };
	}
	let descriptor: number | undefined;
	try {
		const before = fs.statSync(canonical);
		if (!before.isFile())
			return { path: expected.path, canonical_path: canonical, sha256: null, status: "unreadable" };
		if (before.size > MAX_FILE_BYTES)
			return { path: expected.path, canonical_path: canonical, sha256: null, status: "oversized" };
		descriptor = fs.openSync(canonical, "r");
		const buffer = Buffer.alloc(64 * 1024);
		const hash = createHash("sha256");
		let length = 0;
		while (length <= MAX_FILE_BYTES) {
			const count = fs.readSync(descriptor, buffer, 0, Math.min(buffer.length, MAX_FILE_BYTES + 1 - length), null);
			if (count === 0) break;
			hash.update(buffer.subarray(0, count));
			length += count;
		}
		const after = fs.fstatSync(descriptor);
		if (length > MAX_FILE_BYTES)
			return { path: expected.path, canonical_path: canonical, sha256: null, status: "oversized" };
		if (
			before.dev !== after.dev ||
			before.ino !== after.ino ||
			before.size !== after.size ||
			before.mtimeMs !== after.mtimeMs ||
			normalizedPath(fs.realpathSync(expected.path)) !== normalizedPath(canonical)
		)
			return { path: expected.path, canonical_path: canonical, sha256: null, status: "unreadable" };
		return {
			path: expected.path,
			canonical_path: canonical,
			sha256: hash.digest("hex"),
		};
	} catch {
		return { path: expected.path, canonical_path: canonical, sha256: null, status: "unreadable" };
	} finally {
		if (descriptor !== undefined) fs.closeSync(descriptor);
	}
}

function signature(dependencies: FileEvidenceDependency[]): string {
	const canonical = dependencies
		.map((item) => ({
			path: normalizedPath(item.path),
			canonical_path: item.canonical_path === null ? null : normalizedPath(item.canonical_path),
			sha256: item.sha256,
			status: item.status ?? null,
		}))
		.sort((left, right) => left.path.localeCompare(right.path));
	return createHash("sha256").update(JSON.stringify(canonical)).digest("hex");
}

export function checkFileEvidence(dependencies: FileEvidenceDependency[]): { changed: boolean; revision: string } {
	const current = dependencies.map(currentDependency);
	const revision = signature(current);
	return { changed: revision !== signature(dependencies), revision };
}
