#!/usr/bin/env node
// Restore the tracked provider model snapshot into the ignored src/providers/data.
// `hydrate:model-data` reads the live, unpinned models.dev catalog; restoring the
// checked-in release snapshot gives the test suite a reproducible model catalog.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const source = "packages/ai/dist/providers/data";
const target = join(root, "packages/ai/src/providers/data");

const snapshot = JSON.parse(readFileSync(join(root, "packages/ai/model-data-check-snapshot.json"), "utf8"));
if (!/^[a-f0-9]{40}$/.test(snapshot.gitRef)) throw new Error("The check snapshot must name an exact Git commit");
const ref = snapshot.gitRef;
const manifest = JSON.parse(execFileSync("git", ["show", `${ref}:${source}/.manifest.json`], { cwd: root }));
if (manifest.generatedAt !== snapshot.generatedAt || manifest.structureHash !== snapshot.structureHash) {
	throw new Error("The check snapshot manifest does not match its recorded source");
}
const names = execFileSync("git", ["ls-tree", "--name-only", ref, `${source}/`], { cwd: root })
	.toString("utf8")
	.split(/\r?\n/)
	.filter(Boolean)
	.map((line) => line.split("/").pop());
if (names.length === 0 || !names.includes(".manifest.json")) {
	throw new Error(`No tracked provider model snapshot at ${source}`);
}

mkdirSync(target, { recursive: true });
for (const name of names) {
	const bytes = execFileSync("git", ["show", `${ref}:${source}/${name}`], {
		cwd: root,
		maxBuffer: 64 * 1024 * 1024,
	});
	writeFileSync(join(target, name), bytes);
}
console.log(`Restored ${names.length} check files from ${ref} (${source})`);
